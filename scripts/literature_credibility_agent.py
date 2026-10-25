"""
Literature Credibility / Evidence Quality Agent (architecture component 10a).

Answers ONE question per drug-disease pair: "what KIND of literature evidence
is this, and how much can its design be trusted?" It deliberately does NOT
answer efficacy, clinical relevance in the scoring sense, or independence:

  credibility   - study design / population / retraction, from curated PubMed
                  fields (PublicationType, MeSH check tags). Computed here.
  independence  - consumed from stage 04/04b component labels when supplied
                  (replication indicator); NOT recomputed here.
  direction     - supporting / opposing is NOT inferred from text. It is taken
                  only from a curated annotation passed in with the paper
                  (e.g. docs/CASE_STUDIES.md verdicts); otherwise NOT_ASSESSED.
  efficacy      - never assessed. Every output says so.

Determinism and traceability
  * No LLM, no heuristic free-text judgement. Design comes from PubMed
    PublicationType; population from MeSH check tags; sample size only from an
    explicit "n = N" / "N patients|participants|subjects" span in the
    abstract, recorded with the matched text.
  * Missing input stays unknown (None / "UNKNOWN"), is counted, and is excluded
    from averages - it is never scored as low quality or as zero.

Integration boundary
  * Library + CLI; it reads paper records and writes a JSON report. It is NOT
    read by 06_vps_fusion.py and must not be until its semantics, leakage
    behaviour (publication dates) and tests are independently reviewed.

CLI (one batched PubMed efetch for the PMIDs in a persisted 04b graph):
    env -u NCBI_API_KEY ./venv/bin/python scripts/literature_credibility_agent.py \\
        --graph data/literature_graph_droxidopa.json --out data/literature_credibility_droxidopa.json
"""

import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

AGENT_VERSION = "10a-0.1 (2026-10-13)"
CUTOFF_DATE = "2021-01-01"   # mirrors scripts/03_clinicaltrials_groundtruth.py

# ---------------------------------------------------------------------------
# Explicit, fixed criteria
# ---------------------------------------------------------------------------
# PubMed PublicationType -> design, checked in this priority order (a paper
# tagged both "Randomized Controlled Trial" and "Clinical Trial" is an RCT).
DESIGN_PRIORITY = [
    ("Retracted Publication", "RETRACTED"),
    ("Retraction of Publication", "RETRACTION_NOTICE"),
    ("Meta-Analysis", "META_ANALYSIS"),
    ("Systematic Review", "SYSTEMATIC_REVIEW"),
    ("Randomized Controlled Trial", "RCT"),
    ("Controlled Clinical Trial", "CONTROLLED_TRIAL"),
    ("Clinical Trial, Phase IV", "CLINICAL_TRIAL"),
    ("Clinical Trial, Phase III", "CLINICAL_TRIAL"),
    ("Clinical Trial, Phase II", "CLINICAL_TRIAL"),
    ("Clinical Trial, Phase I", "CLINICAL_TRIAL"),
    ("Clinical Trial", "CLINICAL_TRIAL"),
    ("Observational Study", "OBSERVATIONAL"),
    # "Comparative Study" is deliberately NOT mapped: PubMed applies it to lab,
    # computational and clinical work alike (e.g. PMID 41520443, a molecular
    # interaction study), so it says nothing about human study design.
    ("Case Reports", "CASE_REPORT"),
    ("Review", "NARRATIVE_REVIEW"),
    ("Editorial", "OPINION"),
    ("Comment", "OPINION"),
    ("Letter", "OPINION"),
]
# Credibility tier by design (design quality ONLY - not relevance or efficacy).
TIER = {
    "META_ANALYSIS": "A", "SYSTEMATIC_REVIEW": "A", "RCT": "A",
    "CONTROLLED_TRIAL": "B", "CLINICAL_TRIAL": "B", "OBSERVATIONAL": "B",
    "CASE_REPORT": "C", "NARRATIVE_REVIEW": "C",
    "OPINION": "D",
    "RETRACTED": "X", "RETRACTION_NOTICE": "X",
}
TIER_SCORE = {"A": 1.0, "B": 0.6, "C": 0.3, "D": 0.1, "X": 0.0}
# Preclinical work has no PublicationType; it is identified from MeSH check
# tags (Animals without Humans) and capped at tier C whatever its design tag.
PRECLINICAL_CAP = "C"

SAMPLE_RE = re.compile(
    r"\b(?:n\s*=\s*(\d[\d,]*)|(\d[\d,]*)\s+(?:patients|participants|subjects|individuals|cases|people))\b",
    re.I)
DIRECTIONS = ("SUPPORTS", "OPPOSES", "NEUTRAL")


# ---------------------------------------------------------------------------
# Parsing PubMed efetch XML (pure; offline-testable)
# ---------------------------------------------------------------------------

def _year(article) -> Optional[str]:
    for path in (".//Article/Journal/JournalIssue/PubDate/Year", ".//Article/ArticleDate/Year",
                 ".//PubmedData/History/PubMedPubDate[@PubStatus='pubmed']/Year"):
        y = article.findtext(path)
        if y and re.fullmatch(r"\d{4}", y.strip()):
            return y.strip()
    medline = article.findtext(".//Article/Journal/JournalIssue/PubDate/MedlineDate") or ""
    m = re.match(r"\s*(\d{4})", medline)
    return m.group(1) if m else None


def parse_pubmed_xml(xml_bytes: bytes) -> List[Dict]:
    """PubmedArticleSet XML -> paper records. Absent fields are None/[], never guessed."""
    root = ET.fromstring(xml_bytes)
    papers = []
    for art in root.findall(".//PubmedArticle"):
        pmid = art.findtext(".//MedlineCitation/PMID")
        if not pmid:
            continue
        abstract_parts = ["".join(el.itertext()) for el in art.findall(".//Article/Abstract/AbstractText")]
        papers.append({
            "pmid": pmid.strip(),
            "title": "".join(art.find(".//Article/ArticleTitle").itertext()).strip()
            if art.find(".//Article/ArticleTitle") is not None else None,
            "journal": art.findtext(".//Article/Journal/Title"),
            "year": _year(art),
            "publication_types": [pt.text for pt in art.findall(".//PublicationTypeList/PublicationType") if pt.text],
            "mesh_terms": [d.text for d in art.findall(".//MeshHeadingList/MeshHeading/DescriptorName") if d.text],
            "abstract": " ".join(p for p in abstract_parts if p).strip() or None,
        })
    return papers


# ---------------------------------------------------------------------------
# Per-paper assessment
# ---------------------------------------------------------------------------

def classify_design(publication_types: Optional[Iterable[str]]) -> Dict:
    pts = list(publication_types or [])
    for tag, design in DESIGN_PRIORITY:
        if tag in pts:
            return {"design": design, "source": f"PublicationType '{tag}'"}
    if not pts:
        return {"design": "UNKNOWN", "source": "no PublicationType in record"}
    return {"design": "UNKNOWN", "source": f"no mapped PublicationType among {sorted(pts)}"}


def classify_population(mesh_terms: Optional[Iterable[str]]) -> Dict:
    mesh = set(mesh_terms or [])
    if not mesh:
        return {"population": "UNKNOWN", "source": "no MeSH headings (record may not be indexed yet)"}
    if "Humans" in mesh:
        return {"population": "HUMAN", "source": "MeSH check tag 'Humans'"}
    if "Animals" in mesh:
        return {"population": "PRECLINICAL_ANIMAL", "source": "MeSH 'Animals' without 'Humans'"}
    return {"population": "UNKNOWN", "source": "MeSH present but neither 'Humans' nor 'Animals'"}


def extract_sample_size(abstract: Optional[str]) -> Dict:
    if not abstract:
        return {"sample_size": None, "candidates": [], "source": "no abstract"}
    cands = []
    for m in SAMPLE_RE.finditer(abstract):
        raw = (m.group(1) or m.group(2)).replace(",", "")
        cands.append({"value": int(raw), "span": m.group(0)})
    values = sorted({c["value"] for c in cands})
    if len(values) == 1:
        return {"sample_size": values[0], "candidates": cands, "source": "single explicit count in abstract"}
    return {"sample_size": None, "candidates": cands,
            "source": "no explicit count" if not cands else "several different counts - ambiguous, not chosen"}


def assess_paper(paper: Dict, cutoff_date: str = CUTOFF_DATE) -> Dict:
    if not isinstance(paper, dict) or not paper.get("pmid"):
        raise ValueError("paper record must be a dict with a 'pmid'")
    d = classify_design(paper.get("publication_types"))
    p = classify_population(paper.get("mesh_terms"))
    s = extract_sample_size(paper.get("abstract"))
    tier = TIER.get(d["design"])
    if tier and p["population"] == "PRECLINICAL_ANIMAL" and tier in ("A", "B"):
        tier = PRECLINICAL_CAP
    year = paper.get("year")
    year = str(year) if year is not None and re.fullmatch(r"\d{4}", str(year)) else None
    temporal = "UNKNOWN" if year is None else ("PRE_CUTOFF" if year < cutoff_date[:4] else
                                                ("POST_CUTOFF" if year > cutoff_date[:4] or cutoff_date[5:] == "01-01"
                                                 else "UNKNOWN"))
    temporal_source = "publication year"
    if paper.get("cutoff_status") in ("PRE_CUTOFF", "POST_CUTOFF", "UNKNOWN"):
        # Stage 04p dates papers at day/month precision from the earliest of the print and electronic dates;
        # it supersedes the year-only rule (which reads an e-pub-ahead-of-print paper by its later issue year).
        temporal, temporal_source = paper["cutoff_status"], "stage 04p earliest publication date"
    direction = paper.get("direction")
    if direction not in DIRECTIONS:
        direction = "NOT_ASSESSED"
    limitations = []
    if d["design"] == "UNKNOWN":
        limitations.append("study design unknown")
    if p["population"] == "UNKNOWN":
        limitations.append("population unknown (not MeSH-indexed)")
    if p["population"] == "PRECLINICAL_ANIMAL":
        limitations.append("preclinical only")
    if tier == "X":
        limitations.append("retracted / retraction notice")
    if d["design"] in ("NARRATIVE_REVIEW", "SYSTEMATIC_REVIEW", "META_ANALYSIS"):
        limitations.append("secondary literature - may duplicate primary studies")
    if not paper.get("abstract"):
        limitations.append("no abstract")
    if s["sample_size"] is None:
        limitations.append("sample size not determinable from abstract")
    if d["design"] == "CASE_REPORT" and (s["sample_size"] or 0) > 10:
        limitations.append(f"PublicationType 'Case Reports' conflicts with an abstract count of "
                           f"{s['sample_size']}; design tag may be wrong (kept as indexed)")
    if temporal == "POST_CUTOFF":
        limitations.append(f"published after the {cutoff_date} cutoff")
    return {
        "pmid": str(paper["pmid"]), "title": paper.get("title"), "year": year, "temporal": temporal,
        "temporal_source": temporal_source,
        "design": d["design"], "design_source": d["source"],
        "population": p["population"], "population_source": p["source"],
        "credibility_tier": tier or "U",
        "credibility_score": TIER_SCORE.get(tier) if tier else None,
        "sample_size": s["sample_size"], "sample_size_candidates": s["candidates"],
        "sample_size_source": s["source"],
        "component": paper.get("component"),
        "direction": direction, "direction_source": paper.get("direction_source") if direction != "NOT_ASSESSED" else None,
        "limitations": limitations,
    }


# ---------------------------------------------------------------------------
# Pair-level synthesis
# ---------------------------------------------------------------------------

def _summary(assessed: List[Dict]) -> Dict:
    n = len(assessed)
    known = [a for a in assessed if a["credibility_score"] is not None]
    counts = lambda key: {k: sum(1 for a in assessed if a[key] == k) for k in sorted({a[key] for a in assessed})}
    strong = [a for a in assessed if a["credibility_tier"] in ("A", "B") and a["population"] == "HUMAN"]
    comps = {a["component"] for a in strong if a["component"] is not None}
    dirs = {a["direction"] for a in strong}
    return {
        "n_papers": n,
        "n_design_known": len(known),
        "coverage": round(len(known) / n, 3) if n else None,
        "mean_credibility_score_known": round(sum(a["credibility_score"] for a in known) / len(known), 3)
        if known else None,
        "by_tier": counts("credibility_tier"), "by_design": counts("design"), "by_population": counts("population"),
        "n_human_tier_A_or_B": len(strong),
        "replication_indicator": {
            "distinct_components_among_human_A_B": len(comps) if all(a["component"] is not None for a in strong)
            and strong else None,
            "note": "components come from the stage 04/04b graph (shared author/citation); None when not supplied",
        },
        "conflict": ("SUPPORTS" in dirs and "OPPOSES" in dirs),
        "n_direction_assessed": sum(1 for a in assessed if a["direction"] != "NOT_ASSESSED"),
    }


def assess_pair(drug: str, disease: str, papers: List[Dict], cutoff_date: str = CUTOFF_DATE,
                retrieval: Optional[Dict] = None) -> Dict:
    if not drug or not disease:
        raise ValueError("drug and disease are required")
    assessed, rejected = [], []
    seen = set()
    for raw in papers or []:
        try:
            a = assess_paper(raw, cutoff_date)
        except ValueError as exc:
            rejected.append({"record": str(raw)[:120], "reason": str(exc)})
            continue
        if a["pmid"] in seen:
            rejected.append({"record": a["pmid"], "reason": "duplicate PMID"})
            continue
        seen.add(a["pmid"])
        assessed.append(a)
    assessed.sort(key=lambda a: a["pmid"])
    pre = [a for a in assessed if a["temporal"] == "PRE_CUTOFF"]
    summary_all = _summary(assessed)
    return {
        "agent": "literature_credibility", "agent_version": AGENT_VERSION,
        "pair": {"drug": drug, "disease": disease}, "cutoff_date": cutoff_date,
        "scope": ("credibility of study DESIGN only. Not efficacy, not clinical relevance, not independence "
                  "(independence consumed from stage 04 components when supplied)."),
        "efficacy": "NOT_ASSESSED",
        "criteria": {"design_priority": DESIGN_PRIORITY, "tier_by_design": TIER, "tier_score": TIER_SCORE,
                     "preclinical_cap": PRECLINICAL_CAP, "sample_size_regex": SAMPLE_RE.pattern},
        "summary_all": summary_all,
        "summary_pre_cutoff": _summary(pre),
        "n_temporal_unknown": sum(1 for a in assessed if a["temporal"] == "UNKNOWN"),
        "uncertainty": [
            f"{summary_all['n_papers'] - summary_all['n_design_known']} of {summary_all['n_papers']} papers have "
            "no mapped design and are excluded from the mean, not scored as 0",
            "tiers rank DESIGN only; a tier-A study can be small, negative or irrelevant to PD",
            "input sample is whatever retrieval supplied (stage 04 caps at 30, recency-ordered, TD-021)",
        ],
        "papers": assessed, "rejected_records": rejected,
        "provenance": retrieval or {"source": "caller-supplied records"},
    }


def validate_output(report: Dict) -> None:
    """Structural contract; raises ValueError on violation."""
    for key in ("agent", "pair", "efficacy", "summary_all", "summary_pre_cutoff", "papers", "provenance"):
        if key not in report:
            raise ValueError(f"missing key {key}")
    if report["efficacy"] != "NOT_ASSESSED":
        raise ValueError("efficacy must never be assessed by this agent")
    for p in report["papers"]:
        if p["credibility_tier"] == "U" and p["credibility_score"] is not None:
            raise ValueError(f"{p['pmid']}: unknown tier must have no score")
        if p["direction"] == "NOT_ASSESSED" and p["direction_source"] is not None:
            raise ValueError(f"{p['pmid']}: direction source without a direction")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

DIRECTION_MAP = {"SUPPORTS": "SUPPORTS", "OPPOSES": "OPPOSES", "NULL_RESULT": "NEUTRAL"}
CURATED = "data/conflict_claims_curated.json"
CURATED_XML = "data/cache/pubmed_efetch_case_claims.xml"


def _contract(report, root, inputs, missing, not_in_sample=()):
    """Attach the shared agent envelope (scripts/agent_contract.py) to a pair report."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from agent_contract import diag, envelope, input_hashes
    n = report["summary_all"]["n_papers"]
    diags = [diag("warn", "PMID_NOT_RETURNED", f"{len(missing)} PMID(s) not in the PubMed response: {missing[:10]}")] \
        if missing else []
    diags += [diag("warn", "RECORD_REJECTED", f"{r['record']}: {r['reason']}") for r in report["rejected_records"]]
    if not_in_sample:
        diags.append(diag("warn", "NOT_IN_GRAPH", f"{len(not_in_sample)} returned record(s) not in the requested "
                          f"sample were ignored: {sorted(not_in_sample)[:10]}"))
    if n == 0 and missing:              # PMIDs were requested and none came back: a failure, not an empty finding
        diags.append(diag("error", "NO_RECORD_RETURNED", f"none of the requested PMIDs was returned ({len(missing)})"))
        status = "FAILED"
    else:
        status = "NO_EVIDENCE" if n == 0 else ("PARTIAL" if diags else "SUCCESS")
    env = envelope("10a", "Literature Credibility", AGENT_VERSION, "1.0", status, input_hashes(root, inputs),
                   {"papers": n, "design_known": report["summary_all"]["n_design_known"],
                    "human_tier_A_or_B": report["summary_all"]["n_human_tier_A_or_B"]},
                   report["uncertainty"] + ["direction is copied from curated annotations only; efficacy is never assessed"],
                   diags)
    report.update(env)
    return report


def curated_reports(root="."):
    """Offline: rate the curated case-study PMIDs (cached efetch XML) per compound, with curated directions."""
    j = lambda p: os.path.join(root, p)
    with open(j(CURATED_XML), "rb") as fh:
        papers = {p["pmid"]: p for p in parse_pubmed_xml(fh.read())}
    with open(j(CURATED), encoding="utf-8") as fh:
        claims = json.load(fh).get("claims", [])
    by = {}
    for c in claims:
        pm = str(c.get("source_id", "")).split("PMID", 1)[-1].strip() if "PMID" in str(c.get("source_id")) else None
        if pm:
            by.setdefault(c["compound"], {}).setdefault(pm, set()).add(DIRECTION_MAP.get(c.get("direction"), "NOT_ASSESSED"))
    reports = {}
    for compound, pmids in sorted(by.items()):
        recs, missing = [], []
        for pm, dirs in sorted(pmids.items()):
            if pm not in papers:
                missing.append(pm)
                continue
            rec = dict(papers[pm])
            if len(dirs) == 1 and "NOT_ASSESSED" not in dirs:
                rec["direction"] = next(iter(dirs))
                rec["direction_source"] = "curated claim (docs/CASE_STUDIES.md via data/conflict_claims_curated.json)"
            else:
                rec["direction"] = None          # mixed directions across outcomes -> not collapsed
            recs.append(rec)
        report = assess_pair(compound, "Parkinson's disease", recs, retrieval={
            "source": "saved PubMed efetch XML", "path": CURATED_XML, "claims": CURATED, "missing_pmids": missing,
            "note": "papers are the curated case-study sources, not a literature search"})
        validate_output(report)
        reports[compound] = _contract(report, root, [CURATED_XML, CURATED], missing)
    return reports


PROVENANCE_PAPERS = "data/literature_papers.jsonl"
PROVENANCE_SUMMARY = "data/literature_provenance.csv"
PROVENANCE_CACHE = "data/cache/pubmed_lit"
ALL_OUT = "data/literature_credibility_all.json"


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def provenance_reports(root="."):
    """Offline: rate every compound's literature from stage 04p (PMIDs, dates, duplicates) and its cached XML.

    Per compound two summaries are reported: the stage-04 sample (what the literature dimension counted,
    recency-ordered and capped at 30) and the cutoff-bounded set (every paper published on or before the cutoff,
    the leakage-safe view). Duplicate publications (shared DOI/title/erratum link) are rated once; the copies are
    listed as rejected records, never counted as independent papers. Returns (compounds, diagnostics, inputs)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from agent_contract import diag
    import csv
    j = lambda p: os.path.join(root, p)
    with open(j(PROVENANCE_SUMMARY), encoding="utf-8") as fh:
        status = {r["compound_name"]: r for r in csv.DictReader(fh)}
    meta = {}
    with open(j(PROVENANCE_PAPERS), encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                meta.setdefault(r["compound_name"], {})[r["pmid"]] = r
    compounds, diags, inputs = {}, [], [PROVENANCE_SUMMARY, PROVENANCE_PAPERS]
    for name in sorted(status):
        st = status[name]["status"]
        if st == "RETRIEVAL_FAILED":
            compounds[name] = {"status": "RETRIEVAL_FAILED"}
            diags.append(diag("warn", "RETRIEVAL_FAILED", f"{name}: stage 04p could not retrieve its literature"))
            continue
        if st == "NO_RESULTS":
            compounds[name] = {"status": "NO_RESULTS", "note": "PubMed returned no record for the stage-04 query"}
            continue
        cache_rel = os.path.join(PROVENANCE_CACHE, f"{_slug(name)}.json")
        try:
            with open(j(cache_rel), encoding="utf-8") as fh:
                cached = json.load(fh)
            parsed = {}
            for chunk in cached["efetch_xml"]:
                parsed.update({p["pmid"]: p for p in parse_pubmed_xml(chunk.encode("utf-8"))})
        except (OSError, ValueError, KeyError, ET.ParseError) as exc:
            compounds[name] = {"status": "RETRIEVAL_FAILED"}
            diags.append(diag("warn", "CACHE_UNREADABLE", f"{name}: {cache_rel} unreadable ({type(exc).__name__})"))
            continue
        inputs.append(cache_rel)
        m = meta.get(name, {})
        recs, dup = [], []
        for pm, info in sorted(m.items(), key=lambda kv: int(kv[0])):
            if not info["is_primary_record"]:
                dup.append({"record": pm, "reason": f"duplicate publication of PMID {info['duplicate_group']}"})
                continue
            rec = dict(parsed.get(pm) or {"pmid": pm, "title": info.get("title"),
                                           "publication_types": info.get("publication_types"),
                                           "mesh_terms": info.get("mesh_terms")})
            rec["year"] = (info.get("earliest_pub_date") or "")[:4] or rec.get("year")
            rec["cutoff_status"] = info["cutoff_status"]
            recs.append((rec, info))
        if not recs:
            compounds[name] = {"status": "NO_RESULTS", "note": "no primary record after de-duplication"}
            continue
        report = assess_pair(name, "Parkinson's disease", [r for r, _ in recs], retrieval={
            "source": "stage 04p cache (PubMed efetch XML)", "path": cache_rel,
            "retrieved_utc": cached.get("retrieved_utc")})
        validate_output(report)
        by_pm = {a["pmid"]: a for a in report["papers"]}
        sample = [by_pm[r["pmid"]] for r, i in recs if i["in_stage04_sample"]]
        bounded = [by_pm[r["pmid"]] for r, i in recs if i["in_cutoff_bounded_search"]]
        compounds[name] = {
            "status": "ASSESSED",
            "retrieved_utc": cached.get("retrieved_utc"),
            "summary_stage04_sample": _summary(sample),
            "summary_cutoff_bounded": _summary(bounded),
            "n_sample_post_cutoff": sum(1 for a in sample if a["temporal"] == "POST_CUTOFF"),
            "duplicates_removed": dup,
            "papers": [{k: a[k] for k in ("pmid", "year", "temporal", "design", "population", "credibility_tier",
                                          "sample_size")} | {"in_stage04_sample": m[a["pmid"]]["in_stage04_sample"],
                                                             "in_cutoff_bounded_search":
                                                                 m[a["pmid"]]["in_cutoff_bounded_search"]}
                       for a in report["papers"]],
        }
    return compounds, diags, inputs


def all_compounds_report(root="."):
    """Envelope + per-compound summaries for every compound stage 04p covers."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from agent_contract import diag, envelope, input_hashes, run_status
    compounds, diags, inputs = provenance_reports(root)
    n = len(compounds)
    failed = sum(1 for c in compounds.values() if c["status"] == "RETRIEVAL_FAILED")
    assessed = [c for c in compounds.values() if c["status"] == "ASSESSED"]
    if n == 0:
        diags.append(diag("error", "INPUT_EMPTY", f"{PROVENANCE_SUMMARY} lists no compound"))
    status = run_status(n, failed, len(assessed))
    report = {"scope": ("credibility of study DESIGN only, for every compound's stage-04 literature sample and its "
                        "cutoff-bounded literature. Not efficacy, not relevance, not independence."),
              "efficacy": "NOT_ASSESSED", "cutoff_date": CUTOFF_DATE,
              "criteria": {"design_priority": DESIGN_PRIORITY, "tier_by_design": TIER, "tier_score": TIER_SCORE,
                           "preclinical_cap": PRECLINICAL_CAP},
              "compounds": compounds}
    report.update(envelope(
        "10a", "Literature Credibility", AGENT_VERSION, "1.1", status, input_hashes(root, inputs),
        {"compounds": n, "assessed": len(assessed), "retrieval_failed": failed,
         "no_results": sum(1 for c in compounds.values() if c["status"] == "NO_RESULTS"),
         "papers_rated": sum(len(c["papers"]) for c in assessed),
         "duplicates_removed": sum(len(c["duplicates_removed"]) for c in assessed)},
        ["tiers rate DESIGN only; a tier-A study can be small, negative or irrelevant to PD",
         "the stage-04 sample is PubMed's 30 most recent hits (TD-021); summary_cutoff_bounded is the leakage-safe view",
         "PubMed was queried by stage 04p, not at stage 04's run time; samples may differ slightly",
         "direction is not assessed in this mode (no curated annotation); efficacy is never assessed"],
        diags))
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="Literature credibility agent (10a) - diagnostic, not in VPS")
    ap.add_argument("--curated", action="store_true",
                    help="offline: rate the curated case-study PMIDs per compound -> data/literature_credibility_<slug>.json")
    ap.add_argument("--graph", help="persisted 04b graph JSON (supplies PMIDs + components)")
    ap.add_argument("--disease", default="Parkinson's disease")
    ap.add_argument("--xml", help="use a saved PubMed efetch XML instead of fetching (offline)")
    ap.add_argument("--save-xml", help="save the fetched XML here (for offline reruns)")
    ap.add_argument("--out")
    ap.add_argument("--all", action="store_true",
                    help=f"offline: rate every compound from stage 04p (literature provenance) -> {ALL_OUT}")
    args = ap.parse_args(argv)
    if args.all:
        report = all_compounds_report()
        tmp = ALL_OUT + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1, sort_keys=True)
        os.replace(tmp, ALL_OUT)
        cov = report["coverage"]
        print(f"10a --all: {cov['assessed']}/{cov['compounds']} compounds assessed, {cov['papers_rated']} papers, "
              f"{cov['duplicates_removed']} duplicates removed; status {report['run_status']} -> {ALL_OUT}")
        return 1 if report["run_status"] in ("FAILED", "PARTIAL") else 0
    if args.curated:
        for compound, rep in curated_reports().items():
            slug = re.sub(r"[^a-z0-9]+", "_", compound.lower()).strip("_")
            path = f"data/literature_credibility_{slug}.json"
            if os.path.exists(path) and json.load(open(path)).get("provenance", {}).get("graph"):
                print(f"skip {path}: holds a stage-04 graph assessment")   # never overwrite the sample-based report
                continue
            with open(path + ".tmp", "w", encoding="utf-8") as fh:   # atomic write (E-055 A-6)
                json.dump(rep, fh, indent=1)
            os.replace(path + ".tmp", path)
            print(f"{compound}: {rep['summary_all']['n_papers']} curated papers, tiers {rep['summary_all']['by_tier']}, "
                  f"status {rep['run_status']} -> {path}")
        return None
    if not args.graph or not args.out:
        ap.error("--graph and --out are required unless --curated")

    with open(args.graph, encoding="utf-8") as fh:
        graph = json.load(fh)
    nodes = {str(n["pmid"]): n for n in graph.get("nodes", []) if isinstance(n, dict) and n.get("pmid")}
    if not nodes:
        sys.exit(f"{args.graph}: no PMIDs")
    if len(nodes) > 200:
        sys.exit("refusing to fetch more than 200 PMIDs in one call")
    if args.xml:
        with open(args.xml, "rb") as fh:
            xml = fh.read()
        retrieval = {"source": "saved PubMed efetch XML", "path": args.xml}
    else:
        import requests  # only needed for the single live call
        r = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                         params={"db": "pubmed", "id": ",".join(sorted(nodes)), "retmode": "xml"}, timeout=60)
        r.raise_for_status()
        xml = r.content
        retrieval = {"source": "PubMed E-utilities efetch", "n_requested": len(nodes),
                     "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if args.save_xml:
            with open(args.save_xml, "wb") as fh:
                fh.write(xml)
            retrieval["saved_xml"] = args.save_xml
    papers = parse_pubmed_xml(xml)
    extra = sorted({p["pmid"] for p in papers} - set(nodes))
    papers = [p for p in papers if p["pmid"] in nodes]      # never credit a paper outside the requested sample
    got = {p["pmid"] for p in papers}
    retrieval.update({"graph": args.graph, "n_returned": len(papers),
                      "missing_pmids": sorted(set(nodes) - got)})
    for p in papers:
        p["component"] = nodes.get(p["pmid"], {}).get("component")
    report = assess_pair(graph.get("compound") or "unknown", args.disease, papers, retrieval=retrieval)
    validate_output(report)
    _contract(report, ".", [os.path.relpath(x) for x in [args.graph] + ([args.xml] if args.xml else [])],
              retrieval["missing_pmids"], extra)
    with open(args.out + ".tmp", "w", encoding="utf-8") as fh:   # atomic write (E-055 A-6)
        json.dump(report, fh, indent=1)
    os.replace(args.out + ".tmp", args.out)
    s = report["summary_all"]
    print(f"{report['pair']['drug']}: {s['n_papers']} papers; design known {s['n_design_known']}; "
          f"tiers {s['by_tier']}; populations {s['by_population']}; human A/B {s['n_human_tier_A_or_B']}; "
          f"missing PMIDs {retrieval['missing_pmids']}")
    print(f"wrote {args.out}")
    return report


if __name__ == "__main__":
    rc = main()
    sys.exit(rc if isinstance(rc, int) else 0)
