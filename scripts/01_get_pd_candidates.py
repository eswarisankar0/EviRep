"""
STEP 1: Pull Hetionet, build PD candidate compound list.
Output: data/hetionet_nodes.csv, data/hetionet_edges.csv, data/pd_candidates.csv
"""
import gzip, io, zipfile, requests, pandas as pd

# raw.githubusercontent.com only serves a git-lfs POINTER for the edges file
# (a known, widely-reported issue). Use the permanent Zenodo mirror instead —
# a plain, non-LFS zip of the full v1.0.0 release.
ZENODO_ZIP_URL = "https://zenodo.org/records/268568/files/dhimmel/hetionet-v1.0.0.zip"
PD_DISEASE_ID = "Disease::DOID:14330"

#download dataset
def fetch_and_extract_hetionet():
    print("Downloading Hetionet v1.0.0 from Zenodo (~155MB)...")
    r = requests.get(ZENODO_ZIP_URL, timeout=300)
    r.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    nodes_name = next(n for n in names if n.endswith("hetionet-v1.0-nodes.tsv"))
    edges_name = next(n for n in names if n.endswith("hetionet-v1.0-edges.sif.gz"))
    #extract nodes and edges 
    with zf.open(nodes_name) as f:
        nodes = pd.read_csv(f, sep="\t")
    with zf.open(edges_name) as f:
        with gzip.open(f, "rt") as gf:
            edges = pd.read_csv(gf, sep="\t", names=["source","metaedge","target"], header=0)
    return nodes, edges

def main():
    nodes, edges = fetch_and_extract_hetionet()
    #convert to csv
    nodes.to_csv("data/hetionet_nodes.csv", index=False)
    edges.to_csv("data/hetionet_edges.csv", index=False)
    print(f"Saved: {len(nodes)} nodes, {len(edges)} edges")
    # Takes huge hetionet table and only keeps kind==Compund, then checks if it has an existing edge to PD disease module. If not, it's a candidate.
    compounds = nodes[nodes["kind"]=="Compound"][["id","name"]].rename(
        columns={"id":"compound_id","name":"compound_name"})
    #ctD is compound treats disease, cpD is compound palliates disease, both are edges from compound to  disease. Both are existing edges to PD disease module.
    #looks for existing PD drug relationships
    pd_edges = edges[(edges["target"]==PD_DISEASE_ID) & (edges["metaedge"].isin(["CtD","CpD"]))]
    existing = set(pd_edges["source"])#checks whether a compound already has existing PD relationship

    rows = []
    for _, row in compounds.iterrows():
        cid = row["compound_id"]
        etype = pd_edges[pd_edges["source"]==cid]["metaedge"].iloc[0] if cid in existing else "predicted_only"
        rows.append({"compound_id":cid, "compound_name":row["compound_name"],
                     "disease_id":PD_DISEASE_ID, "disease_name":"Parkinson's disease",
                     "existing_edge_type":etype})

    out = pd.DataFrame(rows)
    # There is no existing CtD/CpD relationship for this compound in Hetionet.
    out.to_csv("data/pd_candidates_full.csv", index=False)
    #This removes compounds that already have known CtD/CpD relationships.
    candidates = out[out["existing_edge_type"]=="predicted_only"]
    candidates.to_csv("data/pd_candidates.csv", index=False)
    print(f"Candidates (no existing edge): {len(candidates)} / {len(out)}")

if __name__ == "__main__":
    main()