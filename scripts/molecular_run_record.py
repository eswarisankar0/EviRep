"""
Run record for the Molecular Plausibility Agent (architecture 10b), offline.

Stage 08 / scripts/molecular_agent.py write a CSV (the VPS dimension) and an
evidence JSONL, but no shared agent envelope. This script does NOT re-run the
agent and makes no request: it re-validates every persisted evidence record
with molecular_agent.validate_output, checks that the CSV and the JSONL agree,
and writes the envelope (scripts/agent_contract.py) to data/molecular_agent_run.json.

    ./venv/bin/python scripts/molecular_run_record.py
"""

import argparse
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_contract import diag, envelope, input_hashes, run_status, validate_envelope  # noqa: E402

CSV = "data/molecular_pathway.csv"
JSONL = "data/molecular_pathway_evidence.jsonl"
POOL = "data/vps_scores_v2.csv"
OUT = "data/molecular_agent_run.json"


def build(root="."):
    from molecular_agent import is_retrieval_failure, validate_output  # lazily: needs only the module, no network
    j = lambda p: os.path.join(root, p)
    diags, recs, bad = [], {}, 0
    with open(j(JSONL), encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            try:
                rec = json.loads(line)
                validate_output(rec)
            except Exception as exc:  # each invalid record is reported, none is dropped silently
                bad += 1
                diags.append(diag("warn", "INVALID_RECORD", f"line {n}: {type(exc).__name__}: {str(exc)[:160]}"))
                continue
            recs[rec["drug"]] = rec
    csv = pd.read_csv(j(CSV))
    pool = set(pd.read_csv(j(POOL))["compound_name"]) if os.path.exists(j(POOL)) else set(csv["compound_name"])
    missing_csv = sorted(pool - set(csv["compound_name"]))
    missing_ev = sorted(pool - set(recs))
    if missing_csv:
        diags.append(diag("warn", "POOL_COMPOUND_WITHOUT_ROW", f"{len(missing_csv)}: {missing_csv[:10]}"))
    if missing_ev:
        diags.append(diag("warn", "POOL_COMPOUND_WITHOUT_EVIDENCE", f"{len(missing_ev)}: {missing_ev[:10]}"))
    mismatch = [r.compound_name for r in csv.itertuples() if r.compound_name in recs
                and (pd.isna(r.molecular_plausibility_score)          # a blank score is not "equal"
                     or abs(float(recs[r.compound_name]["molecular_plausibility_score"])
                            - float(r.molecular_plausibility_score)) > 1e-6)]
    api_failed = sorted(n for n, r in recs.items() if n in pool and is_retrieval_failure(r))
    if api_failed:
        diags.append(diag("warn", "RETRIEVAL_FAILED_RECORD", f"{len(api_failed)} record(s) written while Open Targets "
                          f"was unavailable; their 0.0 is a failure, not a measurement: {api_failed[:10]}"))
    if mismatch:
        diags.append(diag("error", "CSV_JSONL_MISMATCH", f"score differs for {mismatch[:10]}"))
    in_pool = csv[csv["compound_name"].isin(pool)]
    n_target = int((in_pool["n_targets"] > 0).sum())
    status = run_status(len(pool), len(missing_ev) + bad + len(api_failed), n_target)
    if mismatch:
        status = "FAILED"
    versions = sorted({(r.get("provenance") or {}).get("agent_version") or "" for r in recs.values()} - {""})
    return envelope("10b", "Molecular Plausibility", ",".join(versions) or "unrecorded", "1.0", status,
                    input_hashes(root, [CSV, JSONL, POOL]),
                    {"pool_compounds": len(pool), "evidence_records_valid": len(recs), "invalid_records": bad,
                     "resolved": int(in_pool["resolved"].astype(bool).sum()), "with_targets": n_target,
                     "without_targets": int((in_pool["n_targets"] == 0).sum()),
                     "with_unretrievable_evidence_items": int((in_pool["n_evidence_missing"] > 0).sum())},
                    ["Open Targets is a current snapshot (not cutoff-bounded, B-001); clinical and literature "
                     "association datatypes are excluded from the score.",
                     "This record re-validates persisted output; it does not re-run retrieval."], diags)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write the 10b run record (offline re-validation)")
    ap.add_argument("--root", default=".")
    args = ap.parse_args(argv)
    out = build(args.root)
    validate_envelope(out)
    dest = os.path.join(args.root, OUT)
    with open(dest + ".tmp", "w", encoding="utf-8") as fh:       # atomic: a killed run never leaves a truncated file
        json.dump(out, fh, indent=1, sort_keys=True)
    os.replace(dest + ".tmp", dest)
    print(f"Saved {OUT}: run_status {out['run_status']}; {out['coverage']}")
    return 0 if out["run_status"] != "FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
