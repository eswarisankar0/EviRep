"""
Check study type + intervention type for ALL unique NCT IDs across
BOTH pre-cutoff and post-cutoff files, so the later filter step has
type info for every trial, not just the post-cutoff ones.
"""
import os, runpy
import requests, pandas as pd, time
from tqdm import tqdm

#: Consecutive failed lookups after which the registry is treated as unreachable (abort, write nothing).
MAX_CONSECUTIVE_FAILURES = 10

def get_study_info(nct_id):
    url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        proto = r.json().get("protocolSection", {})
        study_type = proto.get("designModule", {}).get("studyType", "UNKNOWN")
        interventions = proto.get("armsInterventionsModule", {}).get("interventions", [])
        intr_types = [i.get("type", "UNKNOWN") for i in interventions]
        return study_type, intr_types
    except Exception as e:
        return "ERROR", [str(e)]

def main():
    pre = pd.read_csv("data/clinical_maturity_precutoff.csv")
    post = pd.read_csv("data/ground_truth_postcutoff.csv")

    all_ncts = pd.concat([pre["nct_id"], post["nct_id"]]).unique()
    print(f"Checking {len(all_ncts)} unique trials (pre + post combined)...")

    results, consecutive = [], 0
    for nct in tqdm(all_ncts):
        study_type, intr_types = get_study_info(nct)
        consecutive = consecutive + 1 if study_type == "ERROR" else 0
        if consecutive >= MAX_CONSECUTIVE_FAILURES:
            raise SystemExit(f"ClinicalTrials.gov unreachable: {consecutive} consecutive lookups failed. "
                             "Aborted before writing any output; the previous files are unchanged.")
        results.append({"nct_id": nct, "study_type": study_type, "intervention_types": ";".join(intr_types)})
        time.sleep(0.15)

    df = pd.DataFrame(results)
    errors = df.loc[df["study_type"] == "ERROR", "nct_id"].tolist()
    if errors:
        # The filter would drop these trials as "not interventional": a lookup failure must not remove evidence.
        raise SystemExit(f"{len(errors)} study-type lookup(s) failed (e.g. {errors[:5]}); nothing written. "
                         "Re-run when ClinicalTrials.gov is reachable.")
    df.to_csv("data/nct_studytype_check.csv", index=False)

    print("\n--- Study type breakdown ---")
    print(df["study_type"].value_counts())
    print("\n--- Intervention type breakdown (rough) ---")
    all_types = df["intervention_types"].str.split(";").explode()
    print(all_types.value_counts())
    # The stage's declared outputs include the *_clean.csv files: produce them from this check.
    runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "filter_by_studytype.py"))

if __name__ == "__main__":
    import argparse
    # No options yet: parse anyway so --help or a stray argument exits before any
    # work is done (TD-034; incident E-017 ran stages 05/06 via --help).
    argparse.ArgumentParser(description=__doc__.strip().splitlines()[0] if __doc__ else None).parse_args()
    main()