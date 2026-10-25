"""
Safety Evidence Agent (architecture 10f) — DIAGNOSTIC, not part of VPS.

Two sources, kept separate:
  1. FDA drug LABEL (openFDA drug/label). Read from the stage-05 outputs
     (data/safety_signal.csv) and the raw labels stage 05 cached
     (data/cache/openfda_labels/). No new label request is made here.
  2. FAERS spontaneous adverse-event REPORTS (openFDA drug/event). Retrieved
     only with --fetch (4 small count queries per compound), cached raw in
     data/cache/openfda_faers/, and normalised offline from that cache.

Per compound and source the state is one of
  RETRIEVED       evidence present (label found / >= 1 FAERS report)
  NO_RECORD       the source answered and holds nothing (label: no US label;
                  FAERS: openFDA "NOT_FOUND", i.e. zero matching reports)
  FAILED          a request was made and failed (recorded, never hidden)
  NOT_RETRIEVED   never requested (no cache / no stage-05 row)
A NO_RECORD is not evidence of safety, and FAERS counts are not incidence:
there is no denominator, reporting is voluntary and biased, and a report does
not establish causation. Nothing here is a score; the VPS safety dimension
(stage 05) is unchanged.

    ./venv/bin/python scripts/safety_evidence_agent.py            # offline, from caches
    ./venv/bin/python scripts/safety_evidence_agent.py --fetch    # FAERS requests for uncached compounds
"""

import argparse
import json
import os
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_contract import diag, envelope, input_hashes, now_utc, run_status, validate_envelope  # noqa: E402

AGENT_VERSION = "10f-1.0"
SCHEMA_VERSION = "1.0"
OUT = "data/safety_evidence.json"
POOL = "data/vps_scores_v2.csv"
LABEL_CSV = "data/safety_signal.csv"
LABEL_CACHE = "data/cache/openfda_labels"
LABEL_FAILURES = "data/_safety_failures.jsonl"
FAERS_CACHE = "data/cache/openfda_faers"
LABEL_HISTORY = "data/safety_label_history.csv"       # stage 05h: label version in effect at the cutoff
CUTOFF_YYYYMMDD = "20201231"
FAERS_URL = "https://api.fda.gov/drug/event.json"
CUTOFF = "20201231"
STATES = ("RETRIEVED", "NO_RECORD", "FAILED", "NOT_RETRIEVED")


def safe_name(name):
    """Same filename rule as stage 05's label cache."""
    return "".join(ch if ch.isalnum() else "_" for ch in name)


def faers_queries(name):
    """The four count queries for one compound (search matches the harmonised generic name or the
    reported product name)."""
    who = f'(patient.drug.openfda.generic_name:"{name}" OR patient.drug.medicinalproduct:"{name}")'
    return {
        "serious": {"search": who, "count": "serious"},
        "deaths": {"search": f"{who} AND seriousnessdeath:1", "limit": 1},
        "pre_cutoff": {"search": f"{who} AND receivedate:[19000101 TO {CUTOFF}]", "limit": 1},
        "top_reactions": {"search": who, "count": "patient.reaction.reactionmeddrapt.exact", "limit": 10},
    }


def fetch_faers(name, get=None, pause=0.3):
    """Run the four queries; return a cache record holding each raw response or its failure."""
    if get is None:
        import requests
        get = requests.get
    rec = {"compound_name": name, "retrieved_utc": now_utc(), "endpoint": FAERS_URL, "responses": {}}
    for key, params in faers_queries(name).items():
        try:
            r = get(FAERS_URL, params=params, timeout=30)
            body = r.json() if r.headers.get("Content-Type", "").startswith("application/json") else None
            rec["responses"][key] = {"params": params, "http_status": r.status_code, "body": body}
        except Exception as exc:  # recorded per query; the run continues and reports PARTIAL
            rec["responses"][key] = {"params": params, "http_status": None, "error_class": type(exc).__name__}
        time.sleep(pause)
    return rec


def normalise_faers(rec):
    """Cache record -> state + numbers. 404 with error code NOT_FOUND is a real 'zero reports'."""
    if rec is None:
        return {"state": "NOT_RETRIEVED", "detail": "FAERS not requested for this compound"}
    out = {"retrieved_utc": rec.get("retrieved_utc"), "endpoint": rec.get("endpoint")}
    failed, values = [], {}
    for key, resp in (rec.get("responses") or {}).items():
        st, body = resp.get("http_status"), resp.get("body")
        body = body if isinstance(body, dict) else {}
        if st == 200 and "results" in body:
            values[key] = body
        elif st == 200:                                          # not JSON, or JSON without results
            failed.append(f"{key}: HTTP 200 without a result body")
        elif st == 404 and (body.get("error") or {}).get("code") == "NOT_FOUND":
            values[key] = None                                   # no matching report
        else:
            failed.append(f"{key}: HTTP {st}" if st else f"{key}: {resp.get('error_class')}")
    if len(failed) == len(rec.get("responses") or {}) or "serious" not in values:
        return {**out, "state": "FAILED", "detail": "; ".join(failed) or "no responses recorded", "failed_queries": failed}
    ser = values.get("serious")
    if ser is None and "serious" in values:
        return {**out, "state": "NO_RECORD", "detail": "openFDA returned NOT_FOUND: no FAERS report matches this "
                "name (not evidence of safety; name matching may miss reports)", "failed_queries": failed,
                "total_reports": 0}
    counts = {str(r.get("term")): int(r.get("count", 0)) for r in (ser or {}).get("results", [])}
    total = sum(counts.values()) if ser else None
    total_of = lambda key: (0 if values.get(key) is None and key in values else
                            ((values.get(key) or {}).get("meta") or {}).get("results", {}).get("total"))
    norm = {**out, "state": "RETRIEVED" if total else "NO_RECORD",
            "total_reports": total, "serious_reports": counts.get("1"), "non_serious_reports": counts.get("2"),
            "death_reports": total_of("deaths"), "reports_received_by_2020": total_of("pre_cutoff"),
            "top_reactions": [{"term": r.get("term"), "count": r.get("count")}
                              for r in (values.get("top_reactions") or {}).get("results", [])][:10],
            "failed_queries": failed}
    norm["detail"] = (f"{total} reports ({norm['serious_reports']} serious, {norm['death_reports']} with death "
                      f"as an outcome); {norm['reports_received_by_2020']} received by {CUTOFF}"
                      + (f"; failed: {', '.join(failed)}" if failed else ""))
    if failed:
        norm["state"] = "RETRIEVED" if total else "FAILED"
    return norm


def label_evidence(name, row, failures, cache_dir):
    if name in failures and row is None:
        return {"state": "FAILED", "detail": f"stage-05 request failed ({failures[name]['error_class']}) and was recorded"}
    if row is None:
        return {"state": "NOT_RETRIEVED", "detail": "no stage-05 row and no recorded failure"}
    if not bool(row["has_label"]):
        return {"state": "NO_RECORD", "detail": "openFDA returned no US label (HTTP 404 or empty result)"}
    path = os.path.join(cache_dir, safe_name(name) + ".json")
    raw = None
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    boxed_text = " ".join((raw or {}).get("boxed_warning") or [])[:400] if raw else None
    set_id = row.get("label_set_id")
    return {"state": "RETRIEVED", "label_set_id": set_id,
            "url": f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={set_id}" if isinstance(set_id, str) else None,
            "effective_time": None if pd.isna(row.get("label_effective_time")) else str(int(row["label_effective_time"])),
            "boxed_warning": bool(row["boxed_warning"]), "boxed_warning_excerpt": boxed_text or None,
            "serious_term_count": None if pd.isna(row["serious_term_count"]) else int(row["serious_term_count"]),
            "warning_fields": row.get("warning_fields") if isinstance(row.get("warning_fields"), str) else None,
            "has_contraindications": bool((raw or {}).get("contraindications")) if raw else None,
            "raw_label_cached": raw is not None,
            "temporal": (None if pd.isna(row.get("label_effective_time")) else
                         "POST_CUTOFF" if str(int(row["label_effective_time"])) > CUTOFF_YYYYMMDD else "PRE_CUTOFF"),
            "detail": "current label (not cutoff-bounded)"}


def at_cutoff(hist_row):
    """Stage-05h view of the label at the cutoff. Absence of a pre-cutoff version under this set ID is UNKNOWN
    (an older label may exist under another set ID), never 'no label' or 'no risk'."""
    if hist_row is None:
        return {"state": "NOT_RETRIEVED", "detail": "stage 05h has not been run for this compound"}
    st = hist_row["state"]
    if st == "PRE_CUTOFF_VERSION_SCORED":
        cur_b, cut_b = str(hist_row.get("stage05_boxed_warning")) == "True", bool(hist_row["cutoff_boxed_warning"])
        cur_n, cut_n = hist_row.get("stage05_serious_term_count"), hist_row["cutoff_serious_term_count"]
        return {"state": "SCORED", "version": int(hist_row["cutoff_version"]),
                "version_date": hist_row["cutoff_version_date"], "boxed_warning": cut_b,
                "serious_term_count": int(cut_n),
                "changed_since_cutoff": bool(cur_b != cut_b or (pd.notna(cur_n) and int(cur_n) != int(cut_n))),
                "detail": "DailyMed version published on or before 2020-12-31, scored with stage 05's rule"}
    if st == "NO_PRE_CUTOFF_VERSION":
        return {"state": "UNKNOWN", "detail": str(hist_row.get("detail") or "no pre-cutoff version of this set ID")}
    if st == "NO_CURRENT_LABEL":
        return {"state": "NO_RECORD", "detail": "no current openFDA label to follow"}
    return {"state": "FAILED", "detail": str(hist_row.get("detail") or "stage 05h retrieval failed")}


def run(root="."):
    j = lambda p: os.path.join(root, p)
    pool = list(dict.fromkeys(pd.read_csv(j(POOL))["compound_name"].tolist()))
    records, diags = [], []
    if os.path.exists(j(LABEL_CSV)):
        lab = pd.read_csv(j(LABEL_CSV))
    else:
        lab = pd.DataFrame(columns=["compound_name"])
        diags.append(diag("warn", "INPUT_MISSING", f"{LABEL_CSV} is missing: no label evidence was read"))
    by = {r["compound_name"]: r for r in lab.to_dict("records")}
    failures = {}
    if os.path.exists(j(LABEL_FAILURES)):
        with open(j(LABEL_FAILURES)) as fh:
            for line in fh:
                rec = json.loads(line)
                failures[rec["compound_name"]] = rec
    hist = {}
    if os.path.exists(j(LABEL_HISTORY)):
        hist = {r["compound_name"]: r for r in pd.read_csv(j(LABEL_HISTORY)).to_dict("records")}
    else:
        diags.append(diag("info", "LABEL_HISTORY_MISSING", f"{LABEL_HISTORY} absent (run stage 05h): no label-at-cutoff view"))
    faers_files, label_files = [], []
    for name in pool:
        fp = os.path.join(FAERS_CACHE, safe_name(name) + ".json")
        cached = None
        if os.path.exists(j(fp)):
            faers_files.append(fp)
            with open(j(fp), encoding="utf-8") as fh:
                cached = json.load(fh)
        rec = {"compound": name, "label": label_evidence(name, by.get(name), failures, j(LABEL_CACHE)),
               "faers": normalise_faers(cached)}
        if rec["label"]["state"] == "RETRIEVED" or hist:
            rec["label"]["at_cutoff"] = at_cutoff(hist.get(name)) if hist else {"state": "NOT_RETRIEVED",
                                                                                 "detail": "stage 05h not run"}
        if rec["label"].get("raw_label_cached"):
            label_files.append(os.path.join(LABEL_CACHE, safe_name(name) + ".json"))
        if rec["faers"]["state"] != "FAILED" and rec["faers"].get("failed_queries"):
            diags.append(diag("warn", "FAERS_QUERY_FAILED",
                              f"{name}: some FAERS queries failed ({', '.join(rec['faers']['failed_queries'])})"))
        for src in ("label", "faers"):
            if rec[src]["state"] == "FAILED":
                diags.append(diag("warn", f"{src.upper()}_FAILED", f"{name}: {rec[src]['detail']}"))
        records.append(rec)
    counts = {src: {s: sum(r[src]["state"] == s for r in records) for s in STATES} for src in ("label", "faers")}
    n_failed = sum(r["faers"]["state"] == "FAILED" or r["label"]["state"] == "FAILED" for r in records)
    n_ev = sum(r["faers"]["state"] == "RETRIEVED" or r["label"]["state"] == "RETRIEVED" for r in records)
    if counts["faers"]["NOT_RETRIEVED"]:
        diags.append(diag("info", "FAERS_NOT_RETRIEVED",
                          f"{counts['faers']['NOT_RETRIEVED']} compound(s) have no FAERS cache; run with --fetch"))
    if counts["label"]["NOT_RETRIEVED"]:
        diags.append(diag("warn", "LABEL_NOT_RETRIEVED",
                          f"{counts['label']['NOT_RETRIEVED']} compound(s) have no stage-05 label row and no recorded failure"))
    status = run_status(len(records), n_failed, n_ev)
    if status == "SUCCESS" and counts["faers"]["NOT_RETRIEVED"]:
        status = "PARTIAL"
        diags.append(diag("warn", "FAERS_INCOMPLETE", "FAERS coverage incomplete"))
    if status == "SUCCESS" and any(d["level"] == "warn" for d in diags):
        status = "PARTIAL"
    inputs = input_hashes(root, [POOL, LABEL_CSV, LABEL_FAILURES, LABEL_HISTORY] + faers_files + label_files)
    at = [r["label"].get("at_cutoff", {}).get("state") for r in records]
    env = envelope("10f", "Safety Evidence", AGENT_VERSION, SCHEMA_VERSION, status, inputs,
                   {"compounds": len(records), "label": counts["label"], "faers": counts["faers"],
                    "label_at_cutoff": {k: at.count(k) for k in ("SCORED", "UNKNOWN", "NO_RECORD", "FAILED",
                                                                   "NOT_RETRIEVED")}},
                   ["FAERS counts are spontaneous reports: no denominator, reporting bias, no causality.",
                    "FAERS matching uses the harmonised generic name or reported product name; misspelled or "
                    "brand-only reports are missed and combination products may be included.",
                    "Labels are current versions (not cutoff-bounded); label.at_cutoff gives the DailyMed version in "
                    "effect at the cutoff where one exists under the same set ID (stage 05h). FAERS totals are "
                    "all-time; reports_received_by_2020 is the cutoff-bounded count.",
                    "Nothing here enters VPS; the safety dimension is stage 05 (label only)."], diags)
    return {**env, "state_meaning": {
        "RETRIEVED": "evidence present", "NO_RECORD": "source answered and holds nothing (not evidence of safety)",
        "FAILED": "request made and failed (recorded)", "NOT_RETRIEVED": "never requested"},
        "records": records}


def validate_output(out):
    validate_envelope(out)
    for r in out["records"]:
        for src in ("label", "faers"):
            if r[src]["state"] not in STATES:
                raise ValueError(f"{r['compound']}/{src}: bad state")
        f = r["faers"]
        if f["state"] == "NO_RECORD" and f.get("total_reports") not in (0, None):
            raise ValueError(f"{r['compound']}: NO_RECORD with reports")
        if any(k in r for k in ("score", "safety_score")):
            raise ValueError("10f produces no score")
    return True


def needs_fetch(root, pool):
    """Compounds without a FAERS cache, or whose cached request failed in whole or in part (retried)."""
    todo = []
    for n in pool:
        p = os.path.join(root, FAERS_CACHE, safe_name(n) + ".json")
        if not os.path.exists(p):
            todo.append(n)
            continue
        with open(p, encoding="utf-8") as fh:
            norm = normalise_faers(json.load(fh))
        if norm["state"] == "FAILED" or norm.get("failed_queries"):
            todo.append(n)
    return todo


def main(argv=None):
    ap = argparse.ArgumentParser(description="Safety Evidence Agent (10f) - diagnostic, not in VPS")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--fetch", action="store_true", help="request FAERS counts for compounds without a cache file")
    ap.add_argument("--limit", type=int, default=None, help="fetch at most N compounds (connector check)")
    args = ap.parse_args(argv)
    if args.fetch:
        os.makedirs(os.path.join(args.root, FAERS_CACHE), exist_ok=True)
        pool = pd.read_csv(os.path.join(args.root, POOL))["compound_name"].tolist()
        todo = needs_fetch(args.root, list(dict.fromkeys(pool)))
        for n in todo[:args.limit]:
            rec = fetch_faers(n)
            dest = os.path.join(args.root, FAERS_CACHE, safe_name(n) + ".json")
            with open(dest + ".tmp", "w", encoding="utf-8") as fh:   # atomic: a truncated cache would crash run()
                json.dump(rec, fh)
            os.replace(dest + ".tmp", dest)
            print(f"  {n}: " + ", ".join(f"{k}={v.get('http_status')}" for k, v in rec["responses"].items()))
    out = run(args.root)
    validate_output(out)
    path = os.path.join(args.root, args.out)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, default=str)
    os.replace(path + ".tmp", path)
    print(f"Saved {args.out}: run_status {out['run_status']}; label {out['coverage']['label']}; "
          f"FAERS {out['coverage']['faers']}")
    return 0 if out["run_status"] != "FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
