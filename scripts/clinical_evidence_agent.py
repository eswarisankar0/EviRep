"""
Clinical Evidence Agent (architecture 10c) — DIAGNOSTIC layer over stage 03.

Stage 03 already does trial DISCOVERY and INTERVENTION MATCHING (Gate 1
condition, Gate 2 intervention identity; audit in
data/clinicaltrials_match_audit.csv) and produces the VPS clinical-maturity
feature (maximum phase). This agent adds what stage 03 does not:

  * per-trial registry metadata: phase, overall status (completed / stopped /
    withdrawn / ongoing), why stopped, enrolment, design, dates;
  * RESULTS where the registry has them: whether results are posted, when,
    and the posted primary-outcome analyses copied verbatim (p-value, method,
    estimate). Nothing is interpreted as benefit or harm;
  * the ROLE of the compound in each linked trial (scripts/trial_role.py,
    automated; the hand adjudication of D-020 takes precedence where it
    exists);
  * per-compound intervention-matching outcome counts from the stage-03 audit,
    so "no matching trial", "unverifiable" and "API failure" stay distinct.

Registry records are fetched only with --fetch (batched, ~10 requests) and
cached raw in data/cache/ctgov_precutoff_trials.json; analysis is offline.

A registered or completed trial is NOT evidence of efficacy. Results posted
after 2021-01-01 are flagged POST_CUTOFF and must not be used as a pre-cutoff
feature. Nothing here changes stage-03 outputs, labels or VPS (D-020 role
policy remains an owner decision).

    ./venv/bin/python scripts/clinical_evidence_agent.py            # offline, from cache
    ./venv/bin/python scripts/clinical_evidence_agent.py --fetch    # refresh the registry cache
"""

import argparse
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_contract import diag, envelope, input_hashes, now_utc, run_status, validate_envelope  # noqa: E402
from trial_role import classify_trial_role  # noqa: E402

AGENT_VERSION = "10c-1.0"
SCHEMA_VERSION = "1.0"
OUT = "data/clinical_evidence.json"
LINKS = "data/clinical_maturity_precutoff_clean.csv"
AUDIT = "data/clinicaltrials_match_audit.csv"
ROLES = "data/feature_trial_roles_td038.csv"
POOL = "data/vps_scores_v2.csv"
CACHE = "data/cache/ctgov_precutoff_trials.json"
MOL_EVIDENCE = "data/molecular_pathway_evidence.jsonl"   # ChEMBL identity of each compound (stage 08)
API = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = "protocolSection,hasResults,resultsSection.outcomeMeasuresModule"
CUTOFF = "2021-01-01"
BATCH = 20
RESULT_STATES = ("RESULTS_POSTED", "NO_RESULTS_POSTED", "NOT_IN_REGISTRY", "RETRIEVAL_FAILED", "NOT_RETRIEVED")
STATUS_CLASS = {"COMPLETED": "completed", "TERMINATED": "stopped", "SUSPENDED": "stopped", "WITHDRAWN": "withdrawn",
                "RECRUITING": "ongoing", "ACTIVE_NOT_RECRUITING": "ongoing", "ENROLLING_BY_INVITATION": "ongoing",
                "NOT_YET_RECRUITING": "ongoing", "UNKNOWN": "unknown"}


def fetch_registry(ids, get=None):
    """Batched retrieval; every batch's outcome is recorded (failures are kept, never dropped)."""
    if get is None:
        import requests
        get = requests.get
    ids = sorted(set(ids))
    out = {"retrieved_utc": now_utc(), "endpoint": API, "fields": FIELDS, "requested": ids, "studies": [], "batches": []}
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        try:
            r = get(API, params={"filter.ids": ",".join(chunk), "fields": FIELDS, "pageSize": BATCH}, timeout=60)
            if r.status_code != 200:
                out["batches"].append({"ids": chunk, "http_status": r.status_code, "ok": False})
                continue
            studies = r.json().get("studies", [])
            out["studies"] += studies
            out["batches"].append({"ids": chunk, "http_status": 200, "ok": True, "n_returned": len(studies)})
        except Exception as exc:  # recorded per batch
            out["batches"].append({"ids": chunk, "http_status": None, "ok": False, "error_class": type(exc).__name__})
    return out


def _date(struct):
    return (struct or {}).get("date")


def chembl_names(root="."):
    """{compound: ChEMBL preferred name} where stage 08 resolved the compound by exact name or synonym and the
    preferred name differs from ours (e.g. Rifampicin -> RIFAMPIN). The registry often uses that name, so it
    is a source-backed alias for recognising the compound's own intervention; nothing else is inferred."""
    p = os.path.join(root, MOL_EVIDENCE)
    out = {}
    if not os.path.exists(p):
        return out
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            name, pref = r.get("drug"), r.get("drug_normalized")
            if (pref and name and pref.lower() != name.lower()
                    and (r.get("normalization") or {}).get("match_type") in ("exact_name", "exact_synonym")):
                out[name] = pref
    return out


def compound_aliases(name, matched_alias, chembl):
    """Compound name, the alias stage 03 matched, and the ChEMBL preferred name. NOT matched_intervention
    (a registry intervention name, e.g. a background "dopamine agonist" whose otherNames list the compound - E-014)."""
    return [str(x) for x in (name, matched_alias, chembl.get(name)) if isinstance(x, str)]


def normalise_study(study):
    ps = study.get("protocolSection") or {}
    ident, status = ps.get("identificationModule") or {}, ps.get("statusModule") or {}
    design = ps.get("designModule") or {}
    info = design.get("designInfo") or {}
    overall = status.get("overallStatus")
    res_first = _date(status.get("resultsFirstPostDateStruct"))
    rec = {"nct_id": ident.get("nctId"), "title": ident.get("briefTitle"),
           "url": f"https://clinicaltrials.gov/study/{ident.get('nctId')}",
           "phases": design.get("phases") or [], "overall_status": overall,
           "status_class": STATUS_CLASS.get(overall, "unknown"), "why_stopped": status.get("whyStopped"),
           "enrollment": (design.get("enrollmentInfo") or {}).get("count"),
           "enrollment_type": (design.get("enrollmentInfo") or {}).get("type"),
           "primary_purpose": info.get("primaryPurpose"), "allocation": info.get("allocation"),
           "masking": (info.get("maskingInfo") or {}).get("masking"),
           "start_date": _date(status.get("startDateStruct")),
           "primary_completion_date": _date(status.get("primaryCompletionDateStruct")),
           "first_posted": _date(status.get("studyFirstPostDateStruct")),
           "conditions": (ps.get("conditionsModule") or {}).get("conditions") or []}
    if study.get("hasResults"):
        analyses = []
        for om in ((study.get("resultsSection") or {}).get("outcomeMeasuresModule") or {}).get("outcomeMeasures", []):
            if om.get("type") != "PRIMARY":
                continue
            for a in om.get("analyses") or []:
                analyses.append({"outcome": om.get("title"), "time_frame": om.get("timeFrame"),
                                 "p_value": a.get("pValue"), "method": a.get("statisticalMethod"),
                                 "estimate_type": a.get("paramType"), "estimate": a.get("paramValue"),
                                 "ci": [a.get("ciLowerLimit"), a.get("ciUpperLimit")] if a.get("ciLowerLimit") else None,
                                 "groups": a.get("groupIds")})
            if not om.get("analyses"):
                analyses.append({"outcome": om.get("title"), "time_frame": om.get("timeFrame"), "p_value": None,
                                 "note": "primary outcome data posted without a statistical analysis"})
        rec["results"] = {"state": "RESULTS_POSTED", "results_first_posted": res_first,
                          "temporal": ("UNKNOWN" if not res_first else
                                       "POST_CUTOFF" if res_first >= CUTOFF else "PRE_CUTOFF"),
                          "primary_analyses": analyses[:12],
                          "n_primary_analyses": sum(1 for a in analyses if "note" not in a),
                          "n_primary_outcomes_without_analysis": sum(1 for a in analyses if "note" in a)}
    else:
        rec["results"] = {"state": "NO_RESULTS_POSTED",
                          "detail": "registry record has no posted results (common; not a negative finding)"}
    return rec


def run(root="."):
    j = lambda p: os.path.join(root, p)
    links = pd.read_csv(j(LINKS))
    pool = set(pd.read_csv(j(POOL))["compound_name"]) if os.path.exists(j(POOL)) else set(links["compound_name"])
    audit = pd.read_csv(j(AUDIT)) if os.path.exists(j(AUDIT)) else None
    manual = {}
    if os.path.exists(j(ROLES)):
        for r in pd.read_csv(j(ROLES), keep_default_na=False).itertuples():
            manual[(r.nct_id, r.compound_name)] = {"category": r.category, "p1_qualifies": r.p1_qualifies,
                                                   "rationale": r.rationale}
    cache = None
    if os.path.exists(j(CACHE)):
        with open(j(CACHE), encoding="utf-8") as fh:
            cache = json.load(fh)
    studies = {s["protocolSection"]["identificationModule"]["nctId"]: s for s in (cache or {}).get("studies", [])}
    failed_ids = {i for b in (cache or {}).get("batches", []) if not b.get("ok") for i in b["ids"]}
    requested = set((cache or {}).get("requested") or
                    [i for b in (cache or {}).get("batches", []) for i in b["ids"]])
    diags = []
    if cache is None:
        diags.append(diag("error", "NO_REGISTRY_CACHE", f"{CACHE} absent: run with --fetch"))
    for b in (cache or {}).get("batches", []):
        if not b.get("ok"):
            diags.append(diag("warn", "BATCH_FAILED", f"{len(b['ids'])} trial(s): HTTP {b.get('http_status')} "
                              f"{b.get('error_class') or ''}".strip()))

    trials = {}
    for nct in sorted(set(links["nct_id"])):
        if nct in studies:
            trials[nct] = normalise_study(studies[nct])
        else:
            state = ("RETRIEVAL_FAILED" if nct in failed_ids else
                     "NOT_IN_REGISTRY" if cache and nct in requested else "NOT_RETRIEVED")
            trials[nct] = {"nct_id": nct, "url": f"https://clinicaltrials.gov/study/{nct}",
                           "results": {"state": state}}
    if cache is not None:
        unrequested = [n for n, t in trials.items() if t["results"]["state"] == "NOT_RETRIEVED"]
        if unrequested:
            diags.append(diag("warn", "CACHE_STALE", f"{len(unrequested)} linked trial(s) were never requested by the "
                              f"cached retrieval (stage-03 links changed since): {unrequested[:10]}; run with --fetch"))
    missing = [n for n, t in trials.items() if t["results"]["state"] == "NOT_IN_REGISTRY"]
    if missing:
        diags.append(diag("warn", "NOT_IN_REGISTRY", f"{len(missing)} requested trial(s) not returned: {missing[:10]}"))

    chembl = chembl_names(root)
    compounds = []
    for name, grp in links.groupby("compound_name"):
        link_recs = []
        for r in grp.itertuples():
            t = trials[r.nct_id]
            aliases = compound_aliases(name, r.matched_alias, chembl)
            auto = classify_trial_role(studies[r.nct_id], aliases)["verdict"] if r.nct_id in studies else "UNDETERMINED"
            m = manual.get((r.nct_id, name))
            link_recs.append({"nct_id": r.nct_id, "phase_in_feature": None if pd.isna(r.phase) else r.phase,
                              "role_auto": auto, "role_manual": m,
                              "role_source": "hand adjudication (D-020)" if m else "automated (scripts/trial_role.py)",
                              "results_state": t["results"]["state"], "status_class": t.get("status_class")})
        a = {}
        if audit is not None:
            sub = audit[audit["compound_name"] == name]
            a = {k: int(v) for k, v in sub["outcome"].value_counts().items()}
        tr = [trials[x["nct_id"]] for x in link_recs]
        posted = [t for t in tr if t["results"]["state"] == "RESULTS_POSTED"]
        auto_test = [x for x in link_recs if (x["role_manual"] or {}).get("p1_qualifies") == "YES"
                     or (not x["role_manual"] and x["role_auto"] == "THERAPEUTIC_TEST")]
        compounds.append({
            "compound": name, "in_evaluable_pool": name in pool, "links": link_recs,
            "n_trials": len(link_recs),
            "status_counts": {**{k: sum(t.get("status_class") == k for t in tr)
                                 for k in ("completed", "stopped", "withdrawn", "ongoing", "unknown")},
                              "no_registry_record": sum("status_class" not in t for t in tr)},
            "n_results_posted": len(posted),
            "n_results_posted_pre_cutoff": sum(t["results"].get("temporal") == "PRE_CUTOFF" for t in posted),
            "n_primary_analyses_posted": sum(t["results"].get("n_primary_analyses", 0) for t in posted),
            "role_counts_auto": {v: sum(x["role_auto"] == v for x in link_recs) for v in sorted({x["role_auto"] for x in link_recs})},
            "n_links_drug_tested": len(auto_test),
            "matching_audit_outcomes": a,
            "interpretation": ("Trial registration and completion show investigation, not benefit. Posted analyses "
                               "are copied verbatim and not judged."),
        })
    n_units = len(trials)
    n_failed = sum(t["results"]["state"] in ("RETRIEVAL_FAILED", "NOT_RETRIEVED") for t in trials.values())
    status = run_status(n_units, n_failed, sum(t["results"]["state"] != "NOT_IN_REGISTRY" for t in trials.values()))
    if cache is None:
        status = "FAILED"
    if status == "SUCCESS" and missing:
        status = "PARTIAL"
    inputs = input_hashes(root, [LINKS, AUDIT, ROLES, POOL, CACHE, MOL_EVIDENCE])
    res_counts = {s: sum(t["results"]["state"] == s for t in trials.values()) for s in RESULT_STATES}
    env = envelope("10c", "Clinical Evidence", AGENT_VERSION, SCHEMA_VERSION, status, inputs,
                   {"trials": n_units, "links": len(links), "compounds": len(compounds), "results": res_counts,
                    "registry_retrieved_utc": (cache or {}).get("retrieved_utc")},
                   ["Covers pre-cutoff trials accepted by stage 03 only; post-cutoff (label) trials are not analysed "
                    "here to keep features and labels apart.",
                    "Roles are automated except the 35 hand-adjudicated shared links (D-020); automated verdicts are "
                    "not applied to scoring.",
                    "Posted primary analyses are copied verbatim; no benefit, harm or significance is inferred.",
                    "Results posted after 2021-01-01 are flagged POST_CUTOFF.",
                    "Discovery and matching are stage 03 (ClinicalTrials.gov only; no EU-CTR/ISRCTN/WHO ICTRP)."],
                   diags)
    return {**env, "results_state_meaning": {
        "RESULTS_POSTED": "the registry holds posted results", "NO_RESULTS_POSTED": "record retrieved; no results posted",
        "NOT_IN_REGISTRY": "requested but not returned by the registry", "RETRIEVAL_FAILED": "request failed (recorded)",
        "NOT_RETRIEVED": "never requested"},
        "trials": trials, "compounds": compounds}


def validate_output(out):
    validate_envelope(out)
    for nct, t in out["trials"].items():
        if t["results"]["state"] not in RESULT_STATES:
            raise ValueError(f"{nct}: bad results state")
    for c in out["compounds"]:
        if any(k in c for k in ("efficacy", "score")):
            raise ValueError("10c never scores or infers efficacy")
    return True


def main(argv=None, get=None):
    ap = argparse.ArgumentParser(description="Clinical Evidence Agent (10c) - diagnostic layer over stage 03")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--fetch", action="store_true", help="(re)build the registry cache with batched requests")
    args = ap.parse_args(argv)
    if args.fetch:
        ids = pd.read_csv(os.path.join(args.root, LINKS))["nct_id"].tolist()
        cache = fetch_registry(ids, get=get)
        if not any(b.get("ok") for b in cache["batches"]) and os.path.exists(os.path.join(args.root, CACHE)):
            # Nothing came back: keep the only offline copy instead of replacing it with an empty one.
            print(f"registry: every batch failed ({len(cache['batches'])}); previous cache kept, output not rebuilt")
            return 1
        with open(os.path.join(args.root, CACHE) + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(cache, fh)
        os.replace(os.path.join(args.root, CACHE) + ".tmp", os.path.join(args.root, CACHE))
        print(f"registry: {len(cache['studies'])}/{len(cache['requested'])} returned; "
              f"failed batches {sum(not b['ok'] for b in cache['batches'])}")
    out = run(args.root)
    validate_output(out)
    path = os.path.join(args.root, args.out)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, default=str)
    os.replace(path + ".tmp", path)
    print(f"Saved {args.out}: run_status {out['run_status']}; results {out['coverage']['results']}")
    return 0 if out["run_status"] != "FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
