"""
STEP 3 (FIXED): ClinicalTrials.gov data, split into pre/post cutoff.
Fix: quote "Parkinson Disease" to force exact-phrase match (Essie treats
unquoted multi-word queries as OR on individual words — "Disease" alone
matches almost everything, which is why v1 pulled in cancer trials).
Also added a client-side verification: never trust the API filter alone,
explicitly check the conditions field contains "parkinson".
"""
import os, requests, pandas as pd, time
from tqdm import tqdm

os.makedirs("data", exist_ok=True)

CUTOFF_DATE = "2021-01-01"
API_BASE = "https://clinicaltrials.gov/api/v2/studies"

def search_trials(drug_name, disease_phrase='"Parkinson Disease"'):
    params = {
        "query.intr": drug_name,
        "query.cond": disease_phrase,   # quoted = exact phrase, not OR'd words
        "pageSize": 20,
    }
    try:
        r = requests.get(API_BASE, params=params, timeout=20)
        r.raise_for_status()
        return r.json().get("studies", [])
    except Exception as e:
        print(f"  error for {drug_name}: {e}")
        return []

def is_actually_pd(study):
    """Client-side safety net: verify Parkinson's actually appears in the
    study's own conditions list, regardless of what the API returned."""
    proto = study.get("protocolSection", {})
    conditions = proto.get("conditionsModule", {}).get("conditions", [])
    return any("parkinson" in c.lower() for c in conditions)

def main():
    candidates = pd.read_csv("data/pd_candidates.csv")
    pre_rows, post_rows = [], []
    rejected_count = 0

    for _, row in tqdm(candidates.iterrows(), total=len(candidates)):
        drug = row["compound_name"]
        studies = search_trials(drug)
        time.sleep(0.34)

        for s in studies:
            if not is_actually_pd(s):
                rejected_count += 1
                continue  # API returned it, but it's not really a PD trial — drop it

            proto = s.get("protocolSection", {})
            ident = proto.get("identificationModule", {})
            status_mod = proto.get("statusModule", {})
            design_mod = proto.get("designModule", {})

            first_posted = status_mod.get("studyFirstPostDateStruct", {}).get("date", "")
            phase_list = design_mod.get("phases", [])
            phase = phase_list[0] if phase_list else "NA"
            enrollment = design_mod.get("enrollmentInfo", {}).get("count", None)
            nct_id = ident.get("nctId", "")
            overall_status = status_mod.get("overallStatus", "")

            record = {
                "compound_id": row["compound_id"], "compound_name": drug,
                "nct_id": nct_id, "phase": phase, "status": overall_status,
                "enrollment": enrollment, "first_posted": first_posted,
            }

            if first_posted and first_posted < CUTOFF_DATE:
                pre_rows.append(record)
            elif first_posted and first_posted >= CUTOFF_DATE:
                post_rows.append(record)

    pd.DataFrame(pre_rows).to_csv("data/clinical_maturity_precutoff.csv", index=False)
    pd.DataFrame(post_rows).to_csv("data/ground_truth_postcutoff.csv", index=False)
    print(f"Rejected (API matched but NOT actually PD-related): {rejected_count}")
    print(f"Pre-cutoff trials (feature): {len(pre_rows)}")
    print(f"Post-cutoff trials (ground truth, NEVER used as a feature): {len(post_rows)}")

if __name__ == "__main__":
    main()