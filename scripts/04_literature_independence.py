"""
STEP 4: PubMed literature evidence + co-dependency graph.
Two edge types link papers into dependency clusters:
  1. Shared authorship (same author on both papers)
  2. Citation lineage (one paper cites the other, via Semantic Scholar)
Effective independent evidence count = number of connected components
after both edge types are applied, instead of trusting raw paper count.
"""
import os, time, json, requests, pandas as pd, networkx as nx
import xml.etree.ElementTree as ET
from tqdm import tqdm

os.makedirs("data", exist_ok=True)

NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")
NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
S2_BASE = "https://api.semanticscholar.org/graph/v1/paper"
MAX_PAPERS_PER_COMPOUND = 30
CHECKPOINT_FILE = "data/_literature_checkpoint.jsonl"


def _ncbi_params(extra):
    p = {"retmode": "xml", **extra}
    if NCBI_API_KEY:
        p["api_key"] = NCBI_API_KEY
    return p


def search_pmids(compound_name, disease="Parkinson Disease"):
    query = f'"{compound_name}"[Title/Abstract] AND "{disease}"[Title/Abstract]'
    params = _ncbi_params({"db": "pubmed", "term": query, "retmax": MAX_PAPERS_PER_COMPOUND})
    r = requests.get(f"{NCBI_BASE}/esearch.fcgi", params=params, timeout=20)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    return [id_el.text for id_el in root.findall(".//Id")]


def fetch_paper_details(pmids):
    """Batch fetch authors, title for a list of PMIDs."""
    if not pmids:
        return {}
    params = _ncbi_params({"db": "pubmed", "id": ",".join(pmids)})
    r = requests.get(f"{NCBI_BASE}/efetch.fcgi", params=params, timeout=30)
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
        title = article.findtext(".//ArticleTitle", "")
        year = article.findtext(".//PubDate/Year", "")
        result[pmid] = {"authors": authors, "title": title, "year": year}
    return result


def fetch_citing_pmids(pmid):
    """Returns the set of PMIDs that cite this paper, via Semantic Scholar."""
    url = f"{S2_BASE}/PMID:{pmid}/citations"
    try:
        r = requests.get(url, params={"fields": "externalIds"}, timeout=15)
        if r.status_code != 200:
            return set()
        data = r.json()
        cited_by = set()
        for item in data.get("data", []):
            ext = item.get("citingPaper", {}).get("externalIds", {}) or {}
            if "PubMed" in ext:
                cited_by.add(str(ext["PubMed"]))
        return cited_by
    except Exception:
        return set()


def build_dependency_graph(paper_details):
    """
    Builds the co-dependency graph using two edge types:
    shared author and citation lineage.
    """
    G = nx.Graph()
    pmids = list(paper_details.keys())
    G.add_nodes_from(pmids)

    edge_reasons = {"shared_author": 0, "citation": 0}

    citation_cache = {}
    for pmid in pmids:
        citation_cache[pmid] = fetch_citing_pmids(pmid)
        time.sleep(0.4)

    for i in range(len(pmids)):
        for j in range(i + 1, len(pmids)):
            p1, p2 = pmids[i], pmids[j]
            edge_added = False

            a1 = set(paper_details[p1]["authors"])
            a2 = set(paper_details[p2]["authors"])
            if a1 & a2:
                G.add_edge(p1, p2, reason="shared_author")
                edge_reasons["shared_author"] += 1
                edge_added = True

            if not edge_added:
                if p2 in citation_cache.get(p1, set()) or p1 in citation_cache.get(p2, set()):
                    G.add_edge(p1, p2, reason="citation")
                    edge_reasons["citation"] += 1

    components = list(nx.connected_components(G))
    return len(components), edge_reasons


def main():
    candidates = pd.read_csv("data/clinical_maturity_precutoff_clean.csv")
    compounds = candidates["compound_name"].unique()
    print(f"Processing {len(compounds)} unique compounds (co-dependency graph: authorship + citation)...")

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
                time.sleep(0.34 if not NCBI_API_KEY else 0.11)
                paper_details = fetch_paper_details(pmids)
                time.sleep(0.34 if not NCBI_API_KEY else 0.11)

                raw_count = len(paper_details)
                if raw_count == 0:
                    n_components = 0
                    edge_reasons = {"shared_author": 0, "citation": 0}
                else:
                    n_components, edge_reasons = build_dependency_graph(paper_details)

                record = {
                    "compound_name": compound,
                    "raw_paper_count": raw_count,
                    "effective_independent_count": n_components,
                    "independence_ratio": round(n_components / raw_count, 3) if raw_count > 0 else 0.0,
                    "edges_shared_author": edge_reasons["shared_author"],
                    "edges_citation": edge_reasons["citation"],
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
    print("\nTop 15 by lowest independence ratio (among compounds with >=5 papers):")
    filtered = out[out["raw_paper_count"] >= 5]
    print(filtered.sort_values("independence_ratio").head(15).to_string())
    print("\nEdge type totals across all compounds:")
    print(f"  Shared author: {out['edges_shared_author'].sum()}")
    print(f"  Citation:      {out['edges_citation'].sum()}")


if __name__ == "__main__":
    main()