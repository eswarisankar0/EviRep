"""
Reproducibility Agent (architecture 10e) — DIAGNOSTIC, not part of VPS.

Question: is a finding supported by INDEPENDENT studies, or by several
publications of the same study, the same group, the same dataset, or by
syntheses of the same evidence?

How it differs from neighbouring components
  * 10g / stage 04 (evidence independence) merges papers into co-dependency
    components (shared author OR citation) and counts components. It does not
    look at what a paper found, whether it is a primary study, or trial IDs.
  * 10d (conflict & context) classifies disagreement between claims.
  * 10e works at the level of a FINDING (compound x outcome x direction): it
    counts independent primary-study clusters behind it. A citation is recorded
    but does not make two studies' data dependent; a review or meta-analysis is
    never counted as a replicate.

Inputs (persisted; no network):
  data/cache/pubmed_efetch_case_claims.xml   authors, years, PublicationTypes, DataBank NCT IDs
  data/cache/pubmed_efetch_droxidopa.xml     same, Droxidopa paper sample (stage 04/04b)
  data/conflict_claims_curated.json          findings (direction, outcome, overlap_group) from CASE_STUDIES
  data/literature_graph_droxidopa.json       citation edges (informational) and 10g components
  data/clinical_maturity_precutoff_clean.csv, data/ground_truth_postcutoff_clean.csv
                                             trials linked to more than one compound

Output: data/reproducibility.json (schema REPRODUCIBILITY_SCHEMA_VERSION).
No numeric score is produced. Independence is categorical:
  DEPENDENT              a hard dependency was found (same record, shared trial ID,
                         documented shared data, or at least one shared author)
  PLAUSIBLY_INDEPENDENT  author lists and trial IDs are present for both and share
                         nothing, and no documented data overlap — independence is
                         plausible, NOT proven (populations/datasets are not persisted)
  UNDETERMINED           required metadata (authors) is missing for either record
"""

import argparse
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from itertools import combinations

import pandas as pd

AGENT_VERSION = "10e-0.1"
REPRODUCIBILITY_SCHEMA_VERSION = "1.0"
DISEASE = {"name": "Parkinson's disease", "id": "MONDO_0005180"}

XML_FILES = ["data/cache/pubmed_efetch_case_claims.xml", "data/cache/pubmed_efetch_droxidopa.xml"]
CURATED = "data/conflict_claims_curated.json"
GRAPHS = "data/literature_graph_{slug}.json"
TRIAL_FILES = ["data/clinical_maturity_precutoff_clean.csv", "data/ground_truth_postcutoff_clean.csv"]
OUT = "data/reproducibility.json"

# PublicationType -> design; mirrors 10a's DESIGN_PRIORITY (kept local so 10e stays independently testable)
DESIGN_PRIORITY = [("Retracted Publication", "RETRACTED"), ("Meta-Analysis", "META_ANALYSIS"),
                   ("Systematic Review", "SYSTEMATIC_REVIEW"), ("Randomized Controlled Trial", "RCT"),
                   ("Controlled Clinical Trial", "CONTROLLED_TRIAL"), ("Clinical Trial", "CLINICAL_TRIAL"),
                   ("Observational Study", "OBSERVATIONAL"), ("Case Reports", "CASE_REPORT"),
                   ("Review", "NARRATIVE_REVIEW"), ("Editorial", "OPINION"), ("Comment", "OPINION"),
                   ("Letter", "OPINION")]
SECONDARY = {"META_ANALYSIS", "SYSTEMATIC_REVIEW", "NARRATIVE_REVIEW", "OPINION"}
PRIMARY = {"RCT", "CONTROLLED_TRIAL", "CLINICAL_TRIAL", "OBSERVATIONAL", "CASE_REPORT"}
CURATED_DESIGN = {"rct": "RCT", "observational": "OBSERVATIONAL", "open_label": "CLINICAL_TRIAL",
                  "meta_analysis": "META_ANALYSIS", "systematic_review": "SYSTEMATIC_REVIEW"}
NCT_RE = re.compile(r"\bNCT\d{8}\b")


# ------------------------------------------------------------ records ----

def _author_key(a):
    last = (a.findtext("LastName") or a.findtext("CollectiveName") or "").strip()
    ini = (a.findtext("Initials") or "").strip()
    return f"{last.lower()} {ini[:1].lower()}".strip() if last else None


def parse_records(xml_bytes, source):
    """PubMed efetch XML -> {pmid: record}. Malformed XML raises; missing fields stay empty."""
    root = ET.fromstring(xml_bytes)
    out = {}
    for art in root.findall(".//PubmedArticle"):
        pmid = art.findtext(".//MedlineCitation/PMID")
        if not pmid:
            continue
        authors = [k for k in (_author_key(a) for a in art.findall(".//AuthorList/Author")) if k]
        pts = [p.text for p in art.findall(".//PublicationTypeList/PublicationType") if p.text]
        abstract = " ".join("".join(e.itertext()) for e in art.findall(".//Abstract/AbstractText"))
        banks = [n.text for n in art.findall(".//DataBankList/DataBank/AccessionNumberList/AccessionNumber") if n.text]
        year = (art.findtext(".//Article/Journal/JournalIssue/PubDate/Year")
                or (art.findtext(".//Article/Journal/JournalIssue/PubDate/MedlineDate") or "")[:4] or None)
        design = next((d for tag, d in DESIGN_PRIORITY if tag in pts), "UNKNOWN")
        out[pmid] = {"pmid": pmid, "year": year, "authors": sorted(set(authors)),
                     "n_authors": len(set(authors)), "publication_types": pts, "design": design,
                     "design_source": "PubMed PublicationType" if design != "UNKNOWN" else "unmapped PublicationType",
                     "trial_ids": sorted(set(NCT_RE.findall(abstract)) | {b for b in banks if b.startswith("NCT")}),
                     "source": source}
    return out


# ------------------------------------------------------- relationships ----

def relate(a, b, cites=frozenset()):
    """Classify the relationship of two publication records (first matching rule wins)."""
    ra = {"pmids": sorted([a["pmid"], b["pmid"]]), "cites": (a["pmid"], b["pmid"]) in cites or (b["pmid"], a["pmid"]) in cites}
    if a["pmid"] == b["pmid"]:
        return dict(ra, relation="SAME_RECORD", independence="DEPENDENT", rationale="same PMID")
    shared_trials = sorted(set(a["trial_ids"]) & set(b["trial_ids"]))
    if shared_trials:
        return dict(ra, relation="SHARED_TRIAL", independence="DEPENDENT",
                    rationale=f"both report trial(s) {', '.join(shared_trials)}")
    if a.get("overlap_group") and a.get("overlap_group") == b.get("overlap_group"):
        return dict(ra, relation="DOCUMENTED_SHARED_DATA", independence="DEPENDENT",
                    rationale=f"documented overlap: {a['overlap_group']}")
    if a["authors"] and b["authors"]:
        shared = sorted(set(a["authors"]) & set(b["authors"]))
        if shared:
            return dict(ra, relation="SHARED_AUTHORS", independence="DEPENDENT", n_shared_authors=len(shared),
                        rationale=f"{len(shared)} shared author(s): same group; independence not established")
    else:
        return dict(ra, relation="METADATA_MISSING", independence="UNDETERMINED",
                    rationale="author list missing for at least one record")
    return dict(ra, relation="NO_SHARED_INDICATOR", independence="PLAUSIBLY_INDEPENDENT",
                rationale="no shared author, trial ID or documented data overlap; populations/datasets not "
                          "persisted, so independence is plausible, not proven")


def clusters(records, relations):
    """Union-find over DEPENDENT relations -> list of sorted PMID clusters."""
    parent = {r["pmid"]: r["pmid"] for r in records}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for rel in relations:
        if rel["independence"] == "DEPENDENT":
            a, b = (find(p) for p in rel["pmids"])
            if a != b:
                parent[max(a, b)] = min(a, b)
    groups = {}
    for p in parent:
        groups.setdefault(find(p), []).append(p)
    return sorted((sorted(g) for g in groups.values()), key=lambda g: g[0])


# ------------------------------------------------------------ findings ----

def assess_finding(compound, key, claims, recs):
    """One finding = compound x domain x outcome. claims: curated claims; recs: pmid -> record."""
    missing = [c["source_id"] for c in claims if _pmid(c) not in recs]
    used = []
    for c in claims:
        r = recs.get(_pmid(c))
        if not r:
            continue
        r = dict(r, overlap_group=c.get("overlap_group"), direction=c["direction"], claim_id=c["claim_id"])
        if r["design"] == "UNKNOWN" and c.get("design") in CURATED_DESIGN:
            r["design"], r["design_source"] = CURATED_DESIGN[c["design"]], "curated claim (docs/CASE_STUDIES.md)"
        used.append(r)
    primary = [r for r in used if r["design"] in PRIMARY]
    secondary = [r for r in used if r["design"] in SECONDARY]
    rels = [relate(a, b) for a, b in combinations(sorted(used, key=lambda r: r["pmid"]), 2)]
    prim_rels = [r for r in rels if all(p in {x["pmid"] for x in primary} for p in r["pmids"])]
    cl = clusters(primary, prim_rels)
    by_dir = {}
    for group in cl:
        dirs = {x["direction"] for x in primary if x["pmid"] in group}      # every claim, not the first per PMID
        for d in dirs:
            by_dir.setdefault(d, []).append(group)
    undetermined = any(r["independence"] == "UNDETERMINED" for r in prim_rels)
    if missing and not used:
        status = "INSUFFICIENT_METADATA"
    elif not primary:
        status = "SECONDARY_ONLY" if secondary else "INSUFFICIENT_METADATA"
    elif undetermined:
        status = "UNDETERMINED"
    else:
        top = max(by_dir.values(), key=len)
        others = [d for d, g in by_dir.items() if g is not top]
        if len(top) >= 2:
            status = "REPLICATED_WITH_DISAGREEMENT" if others else "REPLICATED"
        elif len(by_dir) > 1 and len(cl) < 2:
            status = "INCONSISTENT_WITHIN_GROUP"
        elif len(by_dir) > 1:
            status = "INCONSISTENT_SINGLE_STUDIES"
        else:
            status = "SINGLE_STUDY"
    levels = {r["independence"] for r in prim_rels}
    cluster_independence = ("UNDETERMINED" if "UNDETERMINED" in levels else
                            "PLAUSIBLY_INDEPENDENT" if "PLAUSIBLY_INDEPENDENT" in levels else
                            ("DEPENDENT" if levels else None))
    return {
        "compound": compound, "finding": key, "status": status,
        "cluster_independence": cluster_independence,
        "directions_by_cluster": {d: g for d, g in sorted(by_dir.items())},
        "n_records": len(used), "n_primary": len(primary), "n_secondary": len(secondary),
        "n_independent_primary_clusters": len(cl),
        "records": [{k: r.get(k) for k in ("pmid", "claim_id", "year", "design", "design_source", "direction",
                                         "n_authors", "trial_ids", "overlap_group")} for r in used],
        "relationships": rels, "missing_records": missing,
        "status_caveat": (f"{len(missing)} source record(s) not available offline; the status is computed from "
                          f"the remaining records and could change" if missing and used else None),
        "note": ("secondary syntheses (reviews/meta-analyses) are listed but never counted as replicates; "
                 "replication here means independent primary studies agreeing in direction, not efficacy"),
    }


def _pmid(claim):
    m = re.fullmatch(r"PMID (\d+)", str(claim.get("source_id", "")))
    return m.group(1) if m else None


def publication_structure(compound, recs, graph):
    """Paper-sample structure (no directions available): primary-study clusters vs 10g components."""
    pm = [n["pmid"] for n in graph.get("nodes", [])]
    have = [recs[p] for p in pm if p in recs]
    cites = {(e["source"], e["target"]) for e in graph.get("edges", []) if e.get("reason") == "citation"}
    rels = [relate(a, b, frozenset(cites)) for a, b in combinations(sorted(have, key=lambda r: r["pmid"]), 2)]
    primary = [r for r in have if r["design"] in PRIMARY]
    prim_set = {r["pmid"] for r in primary}
    cl = clusters(primary, [r for r in rels if set(r["pmids"]) <= prim_set])
    designs = {}
    for r in have:
        designs[r["design"]] = designs.get(r["design"], 0) + 1
    return {
        "compound": compound, "source": graph.get("source"), "n_papers_in_graph": len(pm),
        "n_with_metadata": len(have), "missing_metadata": sorted(set(pm) - set(recs)),
        "designs": dict(sorted(designs.items())), "n_primary": len(primary),
        "primary_clusters": cl, "n_independent_primary_clusters": len(cl),
        "n_10g_components": len({n.get("component") for n in graph.get("nodes", [])}),
        "relation_counts": {k: sum(1 for r in rels if r["relation"] == k) for k in
                            ("SHARED_TRIAL", "SHARED_AUTHORS", "METADATA_MISSING", "NO_SHARED_INDICATOR")},
        "citation_pairs_between_records": sum(1 for r in rels if r["cites"]),
        "finding_replication": "NOT_ASSESSED: no curated outcome directions for these papers",
    }


def shared_trials(root):
    """Trials linked to more than one compound (the same trial counted as evidence twice)."""
    rows = []
    for rel in TRIAL_FILES:
        p = os.path.join(root, rel)
        if os.path.exists(p):
            df = pd.read_csv(p, usecols=["compound_name", "nct_id"])
            df["file"] = rel
            rows.append(df)
    if not rows:
        return {"status": "trial files missing", "trials": []}
    df = pd.concat(rows)
    multi = df.groupby(["file", "nct_id"])["compound_name"].apply(lambda s: sorted(set(s))).reset_index()
    multi = multi[multi["compound_name"].apply(len) > 1]
    return {"n_shared": int(len(multi)),
            "trials": [{"file": r.file, "nct_id": r.nct_id, "compounds": r.compound_name}
                       for r in multi.sort_values(["file", "nct_id"]).itertuples()]}


# ------------------------------------------------------------------ run ----

def _md5(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def run(root="."):
    j = lambda p: os.path.join(root, p)
    inputs, recs = [], {}
    for rel in XML_FILES:
        if os.path.exists(j(rel)):
            with open(j(rel), "rb") as fh:
                recs.update(parse_records(fh.read(), rel))
            inputs.append({"path": rel, "md5": _md5(j(rel)), "retrieved_utc":
                           datetime.fromtimestamp(os.path.getmtime(j(rel)), timezone.utc).isoformat(timespec="seconds")})
    claims = []
    if os.path.exists(j(CURATED)):
        with open(j(CURATED), encoding="utf-8") as fh:
            all_claims = json.load(fh).get("claims", [])
        claims = [c for c in all_claims if _pmid(c)]
        skipped = [str(c.get("claim_id")) for c in all_claims if not _pmid(c)]
        inputs.append({"path": CURATED, "md5": _md5(j(CURATED))})
    by_finding = {}
    for c in claims:
        key = f"{c.get('domain')}:{c.get('endpoint_domain')}"
        by_finding.setdefault((c["compound"], key), []).append(c)
    findings = [assess_finding(comp, key, cl, recs) for (comp, key), cl in sorted(by_finding.items())]

    structures = []
    for path in sorted(os.listdir(j("data"))) if os.path.isdir(j("data")) else []:
        m = re.fullmatch(r"literature_graph_([a-z0-9_]+)\.json", path)
        if m:
            with open(j(os.path.join("data", path)), encoding="utf-8") as fh:
                g = json.load(fh)
            structures.append(publication_structure(g.get("compound", m.group(1)), recs, g))
            inputs.append({"path": f"data/{path}", "md5": _md5(j(os.path.join("data", path)))})

    status_counts = {}
    for f in findings:
        status_counts[f["status"]] = status_counts.get(f["status"], 0) + 1
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from agent_contract import diag, envelope, run_status
    for rel in TRIAL_FILES:
        if os.path.exists(j(rel)):
            inputs.append({"path": rel, "md5": _md5(j(rel))})
    diags = [diag("warn", "INPUT_MISSING", f"{rel} absent")
             for rel in XML_FILES + [CURATED] + TRIAL_FILES if not os.path.exists(j(rel))]
    if os.path.exists(j(CURATED)) and skipped:
        diags.append(diag("info", "CLAIMS_SKIPPED", f"{len(skipped)} curated claim(s) without a 'PMID <n>' source id "
                          f"are not assessed here (labels, Open Targets, other ids)"))
    part = [f"{f['compound']} {f['finding']}" for f in findings if f.get("status_caveat")]
    if part:
        diags.append(diag("warn", "MISSING_SOURCE_RECORDS", f"{len(part)} finding(s) assessed without all their source "
                          f"records: {', '.join(part[:5])}"))
    n_meta = sum(1 for f in findings if f["status"] == "INSUFFICIENT_METADATA")
    if n_meta:
        diags.append(diag("warn", "INSUFFICIENT_METADATA", f"{n_meta} finding(s) lack offline source records"))
    status = run_status(len(findings) + len(structures), 0, len(findings) - n_meta + len(structures))
    if status == "SUCCESS" and diags:
        status = "PARTIAL"
    if not findings and not structures:
        status = "FAILED"
        diags.append(diag("error", "NOTHING_TO_ASSESS", "no curated findings and no paper graph found"))
    env = envelope("10e", "Reproducibility", AGENT_VERSION, REPRODUCIBILITY_SCHEMA_VERSION, status,
                   {i["path"]: i["md5"] for i in inputs},
                   {"findings": len(findings), "paper_structures": len(structures), "publication_records": len(recs)},
                   [], diags)
    return {
        **env,
        "agent": "10e Reproducibility", "agent_version": AGENT_VERSION,
        "schema_version": REPRODUCIBILITY_SCHEMA_VERSION, "disease": DISEASE,
        "integration": "diagnostic only; not read by scripts/06_vps_fusion.py",
        "independence_scale": {
            "DEPENDENT": "same record, shared trial ID, documented shared data, or >=1 shared author",
            "PLAUSIBLY_INDEPENDENT": "metadata present and nothing shared; populations/datasets not persisted, so not proven",
            "UNDETERMINED": "author metadata missing for at least one record"},
        "finding_status_meaning": {
            "REPLICATED": (">=2 primary-study clusters with no shared author/trial/documented data agree in direction; "
                           "none disagrees. Independence is at best PLAUSIBLE (see cluster_independence); "
                           "sample size and design quality are not assessed here (10a)"),
            "REPLICATED_WITH_DISAGREEMENT": ">=2 agreeing primary clusters, but another independent cluster differs",
            "SINGLE_STUDY": "one primary-study cluster",
            "INCONSISTENT_SINGLE_STUDIES": "independent single studies point in different directions",
            "INCONSISTENT_WITHIN_GROUP": ("primary studies that are not independent of each other (shared author, "
                                          "trial or data) point in different directions"),
            "SECONDARY_ONLY": "only reviews/meta-analyses; replication depends on included studies (not resolvable here)",
            "UNDETERMINED": "metadata missing for a primary-study pair",
            "INSUFFICIENT_METADATA": "source records not available offline"},
        "input_files": inputs, "n_publication_records": len(recs),
        "finding_status_counts": dict(sorted(status_counts.items())),
        "findings": findings, "publication_structures": structures,
        "shared_trials_across_compounds": shared_trials(root),
        "limitations": [
            "Coverage: findings exist only for case-study compounds with curated claims; the 90-compound pool has "
            "no persisted per-compound PMIDs (TD-021).",
            "Author matching uses last name + first initial: homonyms can create false dependencies; name variants "
            "can hide true ones.",
            "Institutions and funding are not used (affiliations are inconsistently present in PubMed records).",
            "Trial IDs are found only when PubMed lists them (DataBank) or the abstract quotes them; pre-2005 "
            "trials rarely have one.",
            "Independence is about study identity, not quality (10a) and not efficacy.",
        ],
    }


def validate_output(out):
    if out.get("schema_version") != REPRODUCIBILITY_SCHEMA_VERSION:
        raise ValueError("schema version mismatch")
    allowed = set(out["finding_status_meaning"])
    for f in out["findings"]:
        if f["status"] not in allowed:
            raise ValueError(f"bad status {f['status']}")
        for r in f["relationships"]:
            if r["independence"] not in out["independence_scale"]:
                raise ValueError("bad independence value")
        if any(k in f for k in ("score", "penalty")):
            raise ValueError("10e produces no score")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="Reproducibility Agent (10e) - diagnostic, offline, not in VPS")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(argv)
    out = run(args.root)
    validate_output(out)
    path = os.path.join(args.root, args.out)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    os.replace(path + ".tmp", path)
    print(f"Saved {args.out}: {len(out['findings'])} findings {out['finding_status_counts']}; "
          f"{len(out['publication_structures'])} paper structure(s); "
          f"{out['shared_trials_across_compounds'].get('n_shared')} trials shared across compounds")


if __name__ == "__main__":
    main()
