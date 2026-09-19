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
CHECKPOINT_FILE = "data/_safety_checkpoint.jsonl"
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
    if label is None:
        return {"has_label": False, "boxed_warning": False, "serious_term_count": 0}

    boxed = "boxed_warning" in label
    warnings_text = " ".join(label.get("warnings", []) + label.get("boxed_warning", []))
    warnings_text = warnings_text.lower()
    serious_count = sum(warnings_text.count(term) for term in SERIOUS_TERMS)

    return {"has_label": True, "boxed_warning": boxed, "serious_term_count": serious_count}

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

    with open(CHECKPOINT_FILE, "a") as ckpt:
        for compound in tqdm(compounds):
            if compound in done:
                continue
            try:
                label = query_label(compound)
                result = score_safety(label)
                result["compound_name"] = compound
                ckpt.write(json.dumps(result) + "\n")
                ckpt.flush()
            except Exception as e:
                print(f"  error for {compound}: {e}")
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

if __name__ == "__main__":
    main()