"""
Evidence Independence Agent (architecture 10g) — cross-source dependence, DIAGNOSTIC.

Stage 04 (the VPS "literature" dimension) measures dependence WITHIN one
compound's PubMed sample (shared authors / citations -> components). It does
not ask whether the same underlying study is counted more than once ACROSS the
evidence that reaches synthesis. This agent does, deterministically:

  D1 SHARED_TRIAL_ACROSS_COMPOUNDS  one registered trial credited to several
     candidates' clinical evidence (their clinical evidence is not independent
     of each other; TD-038, roles from 10c / D-020)
  D2 SAME_STUDY_IN_TWO_DIMENSIONS   a paper in the compound's literature sample
     or curated claims reports a trial (NCT ID in PubMed DataBank or abstract)
     that is also one of its clinical-feature trials -> one study, two dimensions
  D3 DUPLICATED_OR_POOLED_CLAIMS    curated claims from the same PMID, or from
     sources documented to pool the same data (overlap_group), or reporting
     the same trial -> collapsed into source clusters (union-find)
  D4 MOLECULAR_DATATYPE_REUSE       whether the molecular score used Open
     Targets datatypes that re-encode clinical or literature evidence
     (clinical / literature datatypes are excluded by stage 08; verified here)
  D5 DUPLICATE_PUBLICATION_IN_SAMPLE  the same publication counted more than once
     in the compound's stage-04 literature sample (shared DOI, identical title,
     or a PubMed erratum/republication link; from stage 04p)

How it differs from 10e: 10e asks whether a FINDING is replicated by
independent primary studies. 10g asks, per CANDIDATE, how many independent
evidence units actually feed synthesis once duplicates are collapsed. It does
not re-cluster papers (that is stage 04) and produces no score.

Coverage: D2 and D5 need the PMIDs behind stage 04, which stage 04 does not
persist (TD-021). Stage 04p re-runs the stage-04 query and persists them, so D2
and D5 are assessed for every compound it retrieved; compounds without a 04p
record stay NOT_ASSESSABLE — never "independent". D3 needs curated claims.
"""

import argparse
import json
import os
import sys
from collections import defaultdict

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_contract import diag, envelope, input_hashes, run_status, validate_envelope  # noqa: E402
from reproducibility_agent import parse_records  # noqa: E402

AGENT_VERSION = "10g-1.1"
SCHEMA_VERSION = "1.0"
OUT = "data/evidence_independence.json"
POOL = "data/vps_scores_v2.csv"
LINKS = "data/clinical_maturity_precutoff_clean.csv"
LIT = "data/literature_independence.csv"
CURATED = "data/conflict_claims_curated.json"
CLINICAL = "data/clinical_evidence.json"
MOL_EVIDENCE = "data/molecular_pathway_evidence.jsonl"
XMLS = {"data/cache/pubmed_efetch_droxidopa.xml": "Droxidopa", "data/cache/pubmed_efetch_case_claims.xml": None}
GRAPH = "data/literature_graph_{slug}.json"
PROV_PAPERS = "data/literature_papers.jsonl"
PROV_CACHE = "data/cache/pubmed_lit/{slug}.json"
LEAKY_DATATYPES = ("clinical", "literature")
CHECK_STATES = ("DEPENDENCE_FOUND", "NONE_FOUND", "NOT_ASSESSABLE")


def _slug(name):
    import re
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def _pmid(source_id):
    s = str(source_id or "")
    return s.split("PMID", 1)[1].strip() if "PMID" in s else None


def cluster_claims(claims, records):
    """Union-find over curated claims: same PMID, same overlap_group, or a shared reported trial."""
    parent = list(range(len(claims)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    reasons = []
    for i in range(len(claims)):
        for k in range(i + 1, len(claims)):
            a, b = claims[i], claims[k]
            pa, pb = _pmid(a["source_id"]), _pmid(b["source_id"])
            why = None
            if pa and pa == pb:
                why = "same PMID"
            elif a.get("overlap_group") and a.get("overlap_group") == b.get("overlap_group"):
                why = f"documented shared data ({a['overlap_group']})"
            else:
                ta = set((records.get(pa) or {}).get("trial_ids", []))
                tb = set((records.get(pb) or {}).get("trial_ids", []))
                if ta & tb:
                    why = f"same trial {sorted(ta & tb)}"
            if why:
                parent[find(i)] = find(k)
                reasons.append({"a": a["claim_id"], "b": b["claim_id"], "reason": why})
    groups = defaultdict(list)
    for i, c in enumerate(claims):
        groups[find(i)].append(c["claim_id"])
    return sorted(groups.values(), key=lambda g: g[0]), reasons


def run(root="."):
    j = lambda p: os.path.join(root, p)
    pool = pd.read_csv(j(POOL))
    links = pd.read_csv(j(LINKS))
    lit = pd.read_csv(j(LIT)).set_index("compound_name") if os.path.exists(j(LIT)) else pd.DataFrame()
    claims = []
    if os.path.exists(j(CURATED)):
        with open(j(CURATED), encoding="utf-8") as fh:
            claims = json.load(fh).get("claims", [])
    roles = {}
    if os.path.exists(j(CLINICAL)):
        with open(j(CLINICAL), encoding="utf-8") as fh:
            clinical = json.load(fh)
        for c in clinical.get("compounds", []):
            for l in c["links"]:
                roles[(l["nct_id"], c["compound"])] = ((l.get("role_manual") or {}).get("category") or l["role_auto"])
    records, sample_owner, diags = {}, {}, []
    for rel, owner in XMLS.items():
        if os.path.exists(j(rel)):
            with open(j(rel), "rb") as fh:
                recs = parse_records(fh.read(), rel)
            records.update(recs)
            if owner:
                for p in recs:
                    sample_owner.setdefault(owner, set()).add(p)
        else:
            diags.append(diag("warn", "XML_MISSING", f"{rel} absent: D2/D3 coverage reduced"))
    prov, prov_inputs = {}, []
    if os.path.exists(j(PROV_PAPERS)):
        with open(j(PROV_PAPERS), encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    r = json.loads(line)
                    if r.get("in_stage04_sample"):
                        prov.setdefault(r["compound_name"], {})[r["pmid"]] = r
        for name in sorted(prov):
            rel = PROV_CACHE.format(slug=_slug(name))
            try:
                with open(j(rel), encoding="utf-8") as fh:
                    chunks = json.load(fh)["efetch_xml"]
                for chunk in chunks:
                    records.update(parse_records(chunk.encode("utf-8"), rel))
                prov_inputs.append(rel)
            except (OSError, ValueError, KeyError) as exc:
                diags.append(diag("warn", "CACHE_UNREADABLE", f"{rel}: {type(exc).__name__}; D2 for {name} uses "
                                  "PMIDs without trial metadata"))
            sample_owner.setdefault(name, set()).update(prov[name])
    else:
        diags.append(diag("warn", "INPUT_MISSING", f"{PROV_PAPERS} absent (run stage 04p): D2/D5 only for the "
                          "Droxidopa sample and curated claims"))
    mol = {}
    if os.path.exists(j(MOL_EVIDENCE)):
        with open(j(MOL_EVIDENCE), encoding="utf-8") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    diags.append(diag("warn", "MALFORMED_LINE", f"{MOL_EVIDENCE}: unparseable line skipped"))
                    continue
                mol[r.get("drug")] = r

    for rel in (LIT, CURATED, CLINICAL, MOL_EVIDENCE):
        if not os.path.exists(j(rel)):
            diags.append(diag("warn", "INPUT_MISSING", f"{rel} absent: the checks that use it are reduced"))
    if os.path.exists(j(LIT)) and lit.empty:       # header-only: present but empty is not "no literature" (E-055 A-2)
        diags.append(diag("warn", "INPUT_EMPTY", f"{LIT} has no rows: literature fields are unknown, not zero"))
    if links.empty:
        diags.append(diag("error", "INPUT_EMPTY", f"{LINKS} has no rows: D1/D2 cannot be assessed"))
    by_trial = links.groupby("nct_id")["compound_name"].apply(lambda s: sorted(set(s))).to_dict()
    out_recs = []
    for name in pool["compound_name"]:
        trials = sorted(set(links.loc[links["compound_name"] == name, "nct_id"]))
        shared = [{"nct_id": t, "also_credited_to": [c for c in by_trial[t] if c != name],
                   "role_here": roles.get((t, name), "not role-audited")} for t in trials if len(by_trial[t]) > 1]
        d1 = {"state": "DEPENDENCE_FOUND" if shared else "NONE_FOUND", "shared_trials": shared,
              "detail": (f"{len(shared)} of {len(trials)} clinical trial(s) also credited to other candidates"
                         if shared else f"none of {len(trials)} trial(s) is credited to another candidate")}
        cc = [c for c in claims if c.get("compound") == name]
        papers = sorted(sample_owner.get(name, set()) | {p for p in (_pmid(c["source_id"]) for c in cc) if p})
        if papers:
            hits = [{"pmid": p, "trial": t} for p in papers for t in (records.get(p) or {}).get("trial_ids", [])
                    if t in trials]
            no_meta = [p for p in papers if p not in records]
            d2 = {"state": "DEPENDENCE_FOUND" if hits else "NONE_FOUND", "papers_checked": len(papers),
                  "papers_without_record": no_meta, "same_study": hits,
                  "detail": (f"{len(hits)} paper(s) report one of this candidate's clinical-feature trials"
                             if hits else f"no checked paper ({len(papers)}) reports one of its {len(trials)} trial(s) "
                             "by NCT ID (pre-2005 trials rarely carry registry IDs)")}
        else:
            d2 = {"state": "NOT_ASSESSABLE", "detail": "no persisted PMIDs for this candidate (TD-021)"}
        if len(cc) >= 2:
            groups, reasons = cluster_claims(cc, records)
            d3 = {"state": "DEPENDENCE_FOUND" if reasons else "NONE_FOUND", "claims": len(cc),
                  "independent_source_clusters": len(groups), "clusters": groups, "links": reasons,
                  "detail": f"{len(cc)} curated claims from {len(groups)} independent source cluster(s)"}
        elif cc:
            d3 = {"state": "NONE_FOUND", "claims": 1, "independent_source_clusters": 1, "clusters": [[cc[0]["claim_id"]]],
                  "links": [], "detail": "a single curated claim"}
        else:
            d3 = {"state": "NOT_ASSESSABLE", "detail": "no curated outcome claims for this candidate"}
        m = mol.get(name)
        if m is None:
            d4 = {"state": "NOT_ASSESSABLE", "detail": "no molecular evidence record"}
        else:
            used = sorted({k for dl in m.get("disease_links") or [] for k in (dl.get("datatype_scores_used") or {})})
            reuse = [k for k in used if k in LEAKY_DATATYPES]
            excluded = sorted({k for dl in m.get("disease_links") or []
                               for k in (dl.get("datatype_scores_excluded_for_leakage") or {})})
            d4 = {"state": "DEPENDENCE_FOUND" if reuse else "NONE_FOUND", "datatypes_used": used,
                  "datatypes_excluded": excluded, "reused": reuse,
                  "detail": (f"molecular score uses {reuse}, which re-encode clinical/literature evidence" if reuse else
                             "molecular score uses no clinical or literature datatype" + (
                                 f" ({', '.join(excluded)} excluded)" if excluded else "")) if used else
                  "no target-disease datatype used (no target or no association)"}
        sample = prov.get(name)
        if sample:
            dups = sorted(({"pmid": pm, "duplicate_of": r["duplicate_group"]} for pm, r in sample.items()
                           if r["duplicate_group"] != pm), key=lambda d: int(d["pmid"]))
            d5 = {"state": "DEPENDENCE_FOUND" if dups else "NONE_FOUND", "papers_checked": len(sample),
                  "duplicates": dups,
                  "detail": (f"{len(dups)} of {len(sample)} sample record(s) duplicate another record in the sample"
                             if dups else f"no duplicate publication among {len(sample)} sample record(s)")
                  + " (sample re-queried by stage 04p)"}
        else:
            d5 = {"state": "NOT_ASSESSABLE", "detail": "no stage-04p literature record for this candidate"}
        raw = {"clinical_trials": len(trials),
               "literature_papers": None if name not in lit.index else int(lit.loc[name, "raw_paper_count"]),
               "literature_components_stage04": None if name not in lit.index else int(lit.loc[name, "effective_independent_count"]),
               "curated_claims": len(cc)}
        indep_trials = len(trials) - len({h["trial"] for h in d2.get("same_study", [])})
        out_recs.append({"compound": name, "label": int(pool.loc[pool["compound_name"] == name, "label"].iloc[0]),
                         "checks": {"D1_shared_trial_across_compounds": d1, "D2_same_study_in_two_dimensions": d2,
                                    "D3_duplicated_or_pooled_claims": d3, "D4_molecular_datatype_reuse": d4,
                                    "D5_duplicate_publication_in_sample": d5},
                         "raw_units": raw,
                         "clinical_trials_not_also_counted_as_literature": indep_trials if d2["state"] != "NOT_ASSESSABLE" else None,
                         "n_checks_assessable": sum(c["state"] != "NOT_ASSESSABLE" for c in (d1, d2, d3, d4, d5))})
    tally = {k: {s: sum(r["checks"][k]["state"] == s for r in out_recs) for s in CHECK_STATES}
             for k in out_recs[0]["checks"]} if out_recs else {}
    status = run_status(len(out_recs), 0, len(out_recs))
    if links.empty:
        status = "FAILED"            # an empty upstream stage is not "no shared trial found"
    if any(d["level"] == "warn" for d in diags) and status == "SUCCESS":
        status = "PARTIAL"
    inputs = input_hashes(root, [POOL, LINKS, LIT, CURATED, CLINICAL, MOL_EVIDENCE, *XMLS, PROV_PAPERS, *prov_inputs])
    env = envelope("10g", "Evidence Independence", AGENT_VERSION, SCHEMA_VERSION, status, inputs,
                   {"compounds": len(out_recs), "checks": tally,
                    "trials_shared_across_compounds": sum(len(v) > 1 for v in by_trial.values())},
                   ["D2/D5 use the stage-04 sample as re-queried by stage 04p (PubMed today; it can differ from the "
                    "sample stage 04 scored). D3 needs curated claims. Unassessable checks are NOT_ASSESSABLE, "
                    "never 'independent'.",
                    "Trial-paper links rely on NCT IDs in PubMed DataBank or abstracts; older trials and papers that "
                    "do not cite the registry ID are missed (false negatives possible).",
                    "Patient-level overlap between different trials (shared cohorts) cannot be detected from registry "
                    "or bibliographic metadata.",
                    "Stage 04's within-literature dependence (shared authors / citations) is consumed, not recomputed.",
                    "Diagnostic only: nothing is de-duplicated in VPS (D-020 policy pending)."], diags)
    return {**env, "check_state_meaning": {
        "DEPENDENCE_FOUND": "the same underlying study is counted more than once (details listed)",
        "NONE_FOUND": "checked; no dependence of this kind found (not proof of independence)",
        "NOT_ASSESSABLE": "required identifiers are not persisted for this candidate"}, "records": out_recs}


def validate_output(out):
    validate_envelope(out)
    for r in out["records"]:
        for k, c in r["checks"].items():
            if c["state"] not in CHECK_STATES:
                raise ValueError(f"{r['compound']}/{k}: bad state")
        if any(k in r for k in ("score", "independence_score")):
            raise ValueError("10g produces no score")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="Evidence Independence Agent (10g) - cross-source, offline, diagnostic")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(argv)
    out = run(args.root)
    validate_output(out)
    path = os.path.join(args.root, args.out)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, default=str)
    os.replace(path + ".tmp", path)
    print(f"Saved {args.out}: run_status {out['run_status']}")
    for k, v in out["coverage"]["checks"].items():
        print(f"  {k}: {v}")
    return 0 if out["run_status"] != "FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
