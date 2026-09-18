import pandas as pd

PD_DISEASE_ID = "Disease::DOID:14330"

edges = pd.read_csv("data/hetionet_edges.csv")
candidates = pd.read_csv("data/pd_candidates.csv")

print("\n========== BASIC INFO ==========")
print("Total edges:", len(edges))
print("Total candidates:", len(candidates))

print("\n========== METAEDGE TYPES ==========")
print(edges["metaedge"].value_counts())

print("\n========== CbG EDGES ==========")
cbg = edges[edges["metaedge"] == "CbG"]
print("CbG edges:", len(cbg))
print(cbg.head())

print("\n========== CANDIDATE TARGET CHECK ==========")

candidate_ids = set(candidates["compound_id"])
cbg_compounds = set(cbg["source"])

matched = candidate_ids & cbg_compounds

print("Candidates:", len(candidate_ids))
print("Candidates having CbG targets:", len(matched))
print("Candidates WITHOUT CbG targets:", len(candidate_ids - cbg_compounds))

print("\n========== DISEASE GENE CHECK ==========")

disease_edges = edges[
    (edges["target"] == PD_DISEASE_ID) &
    (edges["metaedge"].isin(["DaG", "DuG", "DdG"]))
]

print("PD disease-gene edges:", len(disease_edges))
print(disease_edges.head())

disease_genes = set(disease_edges["source"])

print("PD genes:", len(disease_genes))

print("\n========== SAMPLE CANDIDATE ==========")

if len(candidates) > 0:
    sample = candidates.iloc[0]
    cid = sample["compound_id"]

    print("Compound ID:", cid)
    print("Compound name:", sample["compound_name"])

    targets = cbg[cbg["source"] == cid]["target"].tolist()

    print("Targets found:", len(targets))
    print("Targets:", targets[:20])