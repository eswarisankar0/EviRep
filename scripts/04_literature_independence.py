"""
STEP 4: PubMed literature evidence + co-dependency graph.
"""
import os, time, json, requests, pandas as pd, networkx as nx
import xml.etree.ElementTree as ET
from tqdm import tqdm

os.makedirs("data", exist_ok=True)

NCBI_API_KEY = ""
BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
MAX_PAPERS_PER_COMPOUND = 30
CHECKPOINT_FILE = "data/_literature_checkpoint.jsonl"

def _params(extra):
    p = {"retmode": "xml", **extra}
    if NCBI_API_KEY:
        p["api_key"] = NCBI_API_KEY
    return p

def search_pmids(compound_name, disease="Parkinson Disease"):
    query = f'"{compound_name}"[Title/Abstract] AND "{disease}"[Title/Abstract]'
    params = _params({"db": "pubmed", "term": query, "retmax": MAX_PAPERS_PER_COMPOUND})
    r = requests.get(f"{BASE}/esearch.fcgi", params=params, timeout=20)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    return [id_el.text for id_el in root.findall(".//Id")]

def fetch_authors(pmids):
    if not pmids:
        return {}
    params = _params({"db": "pubmed", "id": ",".join(pmids)})
    r = requests.get(f"{BASE}/efetch.fcgi", params=params, timeout=30)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    result = {}
    for article in root.findall(".//PubmedArticle"):
        pmid_el = article.find(".//PMID")
        if pmid_el is None:
            continue
        pmid = pmid_el.text
        authors = []
        for author in article.findall(".//AuthorList/Author"):
            last = author.findtext("LastName", "")
            init = author.findtext("Initials", "")
            if last:
                authors.append(f"{last}_{init}")
        result[pmid] = {"authors": authors}
    return result

def effective_independent_count(paper_authors):
    G = nx.Graph()
    pmids = list(paper_authors.keys())
    G.add_nodes_from(pmids)
    for i in range(len(pmids)):
        for j in range(i + 1, len(pmids)):
            a1 = set(paper_authors[pmids[i]]["authors"])
            a2 = set(paper_authors[pmids[j]]["authors"])
            if a1 & a2:
                G.add_edge(pmids[i], pmids[j])
    components = list(nx.connected_components(G))
    return len(components)

def main():
    candidates = pd.read_csv("data/clinical_maturity_precutoff_clean.csv")
    compounds = candidates["compound_name"].unique()
    print(f"Processing {len(compounds)} unique compounds...")

    done = set()
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            for line in f:
                done.add(json.loads(line)["compound_name"])
        print(f"Resuming: {len(done)} compounds already done.")

    with open(CHECKPOINT_FILE, "a") as ckpt:
        for compound in tqdm(compounds):
            if compound in done:
                continue
            try:
                pmids = search_pmids(compound)
                time.sleep(0.34)
                paper_authors = fetch_authors(pmids)
                time.sleep(0.34)
                raw_count = len(paper_authors)
                n_components = 0 if raw_count == 0 else effective_independent_count(paper_authors)
                record = {
                    "compound_name": compound,
                    "raw_paper_count": raw_count,
                    "effective_independent_count": n_components,
                    "independence_ratio": round(n_components / raw_count, 3) if raw_count > 0 else 0.0,
                }
                ckpt.write(json.dumps(record) + "\n")
                ckpt.flush()
            except Exception as e:
                print(f"  error for {compound}: {e}")
                time.sleep(2)

    all_rows = []
    with open(CHECKPOINT_FILE) as f:
        for line in f:
            all_rows.append(json.loads(line))

    out = pd.DataFrame(all_rows).drop_duplicates("compound_name")
    out.to_csv("data/literature_independence.csv", index=False)
    print(f"\nSaved {len(out)} compounds to data/literature_independence.csv")
    print(out.sort_values("raw_paper_count", ascending=False).head(10).to_string())

if __name__ == "__main__":
    main()
