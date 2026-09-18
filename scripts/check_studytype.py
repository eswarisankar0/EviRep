"""
Check study type + intervention type for ALL unique NCT IDs across
BOTH pre-cutoff and post-cutoff files, so the later filter step has
type info for every trial, not just the post-cutoff ones.
"""
import requests, pandas as pd, time
from tqdm import tqdm

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

    results = []
    for nct in tqdm(all_ncts):
        study_type, intr_types = get_study_info(nct)
        results.append({"nct_id": nct, "study_type": study_type, "intervention_types": ";".join(intr_types)})
        time.sleep(0.15)

    df = pd.DataFrame(results)
    df.to_csv("data/nct_studytype_check.csv", index=False)

    print("\n--- Study type breakdown ---")
    print(df["study_type"].value_counts())
    print("\n--- Intervention type breakdown (rough) ---")
    all_types = df["intervention_types"].str.split(";").explode()
    print(all_types.value_counts())

if __name__ == "__main__":
    main()