"""
STEP 5: Safety signal via openFDA drug label endpoint.
For each compound, checks for a boxed warning and counts serious-sounding
terms in the warnings section. Simplified by design -- full FAERS adverse
event mining was scoped out to protect the timeline.
"""
import os, time, json, requests, pandas as pd
from tqdm import tqdm

os.makedirs("data", exist_ok=True)

BASE = "https://api.fda.gov/drug/label.json"
# v2 (2026-10-15, DECISIONS D-003): the v1 checkpoint data/_safety_checkpoint.jsonl
# counted terms only in `warnings`, which newer-format (PLR) labels do not have,
# so it is kept untouched for provenance and v2 records are written separately.
CHECKPOINT_FILE = "data/_safety_checkpoint_v2.jsonl"
LABEL_CACHE_DIR = "data/cache/openfda_labels"
#: Label sections whose text is searched. PLR labels use `warnings_and_cautions`;
#: older labels use `warnings`. Reading only `warnings` scored PLR labels as 0.
WARNING_FIELDS = ("boxed_warning", "warnings", "warnings_and_cautions")
SERIOUS_TERMS = ["death", "fatal", "life-threatening", "suicide", "seizure",
                  "hepatotoxicity", "cardiac arrest", "stroke"]

def query_label(compound_name):
    params = {"search": f'openfda.generic_name:"{compound_name}"', "limit": 1}
    r = requests.get(BASE, params=params, timeout=20)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    data = r.json()
    results = data.get("results", [])
    return results[0] if results else None

def score_safety(label):
    # No openFDA label means the safety evidence is MISSING, not that the drug
    # is safe: record it as null (blank in the CSV), never as 0 risk (TD-031).
    if label is None:
        return {"has_label": False, "boxed_warning": None, "serious_term_count": None}

    boxed = "boxed_warning" in label
    fields = [f for f in WARNING_FIELDS if label.get(f)]
    warnings_text = " ".join(" ".join(label[f]) for f in fields).lower()
    serious_count = sum(warnings_text.count(term) for term in SERIOUS_TERMS)

    return {"has_label": True, "boxed_warning": boxed, "serious_term_count": serious_count,
            "warning_fields": "|".join(fields), "label_set_id": label.get("set_id"),
            "label_effective_time": label.get("effective_time")}


FAILURES_FILE = "data/_safety_failures.jsonl"


def record_failure(compound_name, exc, path=FAILURES_FILE):
    """Persist a per-compound failure (was print-only: a failed compound silently had no row, E-021).
    The compound is NOT checkpointed, so a re-run retries it; agent 10h/10f read this file to report
    RETRIEVAL_FAILED instead of 'never queried'."""
    from datetime import datetime, timezone
    rec = {"compound_name": compound_name, "error_class": type(exc).__name__,
           "message": str(exc)[:300], "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with open(path, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


def cache_label(compound_name, label):
    """Keep the raw label so the score can be recomputed offline (reproducibility)."""
    if label is None:
        return
    os.makedirs(LABEL_CACHE_DIR, exist_ok=True)
    safe = "".join(ch if ch.isalnum() else "_" for ch in compound_name)
    with open(os.path.join(LABEL_CACHE_DIR, f"{safe}.json"), "w") as fh:
        json.dump(label, fh)

def main():
    candidates = pd.read_csv("data/clinical_maturity_precutoff_clean.csv")
    compounds = candidates["compound_name"].unique()
    print(f"Checking safety signal for {len(compounds)} compounds...")

    done = set()
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            for line in f:
                done.add(json.loads(line)["compound_name"])
        print(f"Resuming: {len(done)} already done.")

    failures = []
    with open(CHECKPOINT_FILE, "a") as ckpt:
        for compound in tqdm(compounds):
            if compound in done:
                continue
            try:
                label = query_label(compound)
                cache_label(compound, label)
                result = score_safety(label)
                result["compound_name"] = compound
                ckpt.write(json.dumps(result) + "\n")
                ckpt.flush()
            except Exception as e:
                record_failure(compound, e)
                failures.append(compound)
                print(f"  error for {compound}: {type(e).__name__} (recorded in {FAILURES_FILE})")
            time.sleep(0.3)

    rows = []
    with open(CHECKPOINT_FILE) as f:
        for line in f:
            rows.append(json.loads(line))

    out = pd.DataFrame(rows).drop_duplicates("compound_name")
    out.to_csv("data/safety_signal.csv", index=False)
    print(f"\nSaved {len(out)} compounds to data/safety_signal.csv")
    print(f"Compounds with boxed warning: {out['boxed_warning'].sum()}")
    print(f"Compounds with no label found: {(~out['has_label']).sum()}")
    print(out.sort_values('serious_term_count', ascending=False).head(10).to_string())
    if failures:
        # A partial run must not look like a successful one.
        print(f"\nINCOMPLETE: {len(failures)} compound(s) failed and have no row: {failures}. Re-run to retry.")
        raise SystemExit(1)

if __name__ == "__main__":
    import argparse
    # No options yet: parse anyway so --help or a stray argument exits before any
    # work is done (TD-034; incident E-017 ran stages 05/06 via --help).
    argparse.ArgumentParser(description=__doc__.strip().splitlines()[0] if __doc__ else None).parse_args()
    main()