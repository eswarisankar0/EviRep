"""
Filter ground truth using the study-type check results.
Keeps only INTERVENTIONAL trials with at least one DRUG/BIOLOGICAL arm.
"""
import pandas as pd

checked = pd.read_csv("data/nct_studytype_check.csv")

def keep_trial(row):
    if row["study_type"] != "INTERVENTIONAL":
        return False
    types = str(row["intervention_types"]).split(";")
    return any(t in ("DRUG", "BIOLOGICAL") for t in types)

checked["keep"] = checked.apply(keep_trial, axis=1)
good_ncts = set(checked[checked["keep"]]["nct_id"])

print(f"Trials kept: {len(good_ncts)} / {len(checked)}")

# Apply to both pre and post cutoff files
for fname in ["data/clinical_maturity_precutoff.csv", "data/ground_truth_postcutoff.csv"]:
    df = pd.read_csv(fname)
    before = df["compound_id"].nunique()
    filtered = df[df["nct_id"].isin(good_ncts)]
    after = filtered["compound_id"].nunique()
    out_name = fname.replace(".csv", "_clean.csv")
    filtered.to_csv(out_name, index=False)
    print(f"{fname}: {before} -> {after} unique compounds. Saved to {out_name}")