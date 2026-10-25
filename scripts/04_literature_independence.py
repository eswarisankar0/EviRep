"""
STEP 4: PubMed literature evidence + co-dependency graph.
Two edge types link papers into dependency clusters:
  1. Shared authorship (same author on both papers)
  2. Citation lineage (one paper cites the other, via Semantic Scholar)
Effective independent evidence count = number of connected components
after both edge types are applied, instead of trusting raw paper count.
"""
import os, time, json, random, requests, pandas as pd, networkx as nx
import xml.etree.ElementTree as ET
import re
from tqdm import tqdm

os.makedirs("data", exist_ok=True)

def _valid_api_key(value):
    """
    Reject obvious placeholders.

    Any truthy string was previously attached as `api_key`, so an environment
    exporting NCBI_API_KEY='your_key' made EVERY PubMed request return HTTP 400.
    The per-compound `except Exception` then swallowed it and the stage reported
    success while writing an empty literature dimension. Observed for real on
    2026-10-05 (ERRORS_AND_BLOCKERS E-008 / TECHNICAL_DEBT TD-016).

    Real NCBI keys are 36-character lowercase hex-ish tokens; anything short or
    matching a known placeholder is treated as absent, which falls back to the
    documented unauthenticated path rather than failing every request.
    """
    v = (value or "").strip()
    if not v:
        return ""
    placeholders = {"your_key", "yourkey", "your-key", "changeme", "xxx",
                    "none", "todo", "placeholder", "<your_key>", "api_key"}
    if v.lower() in placeholders or len(v) < 20:
        print(f"WARNING: NCBI_API_KEY looks like a placeholder ({v[:4]}...); "
              f"ignoring it and using the unauthenticated PubMed path.")
        return ""
    return v


NCBI_API_KEY = _valid_api_key(os.environ.get("NCBI_API_KEY", ""))
NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
S2_BASE = "https://api.semanticscholar.org/graph/v1/paper"
MAX_PAPERS_PER_COMPOUND = 30
# Semantic Scholar unauthenticated throughput. Raised from 0.4s after the
# 2026-10-05 throttling incident (E-009).
S2_SLEEP = float(os.environ.get("S2_SLEEP", "1.1"))
CHECKPOINT_FILE = "data/_literature_checkpoint.jsonl"


def _ncbi_params(extra):
    p = {"retmode": "xml", **extra}
    if NCBI_API_KEY:
        p["api_key"] = NCBI_API_KEY
    return p


def search_pmids(compound_name, disease="Parkinson Disease", max_date=None):
    """PMIDs for the compound/disease query (up to MAX_PAPERS_PER_COMPOUND).

    max_date ("YYYY/MM/DD") bounds the PUBLICATION date (PubMed `pdat`), which
    is how a cutoff would be enforced for this dimension (TD-021). Default None
    keeps the original, unbounded query. It is deliberately NOT wired into
    main(): a bounded run must write a separate checkpoint/output, otherwise it
    would resume from and mix with the unbounded checkpoint. Owner decision.
    """
    query = f'"{compound_name}"[Title/Abstract] AND "{disease}"[Title/Abstract]'
    fields = {"db": "pubmed", "term": query, "retmax": MAX_PAPERS_PER_COMPOUND}
    if max_date:
        if not re.fullmatch(r"\d{4}/\d{2}/\d{2}", str(max_date)):
            raise ValueError(f"max_date must be YYYY/MM/DD, got {max_date!r}")
        fields.update({"datetype": "pdat", "mindate": "1800/01/01", "maxdate": max_date})
    params = _ncbi_params(fields)
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


# Accounting for Semantic Scholar lookups. Without this, a rate-limited run is
# INDISTINGUISHABLE from a run where no paper cites any other -- the original
# code returned an empty set on any non-200. That silently inflates
# effective_independent_count / independence_ratio. Observed for real on
# 2026-10-05: S2 began returning HTTP 429 after ~12 compounds and the stage
# still reported "0 errors". See ERRORS_AND_BLOCKERS E-009 / TECHNICAL_DEBT TD-009.
S2_STATS = {"ok": 0, "rate_limited": 0, "failed": 0, "empty": 0}

S2_MAX_RETRIES = 5
S2_BACKOFF_BASE = 2.0


class SemanticScholarUnavailable(RuntimeError):
    """Raised when S2 cannot be reached for a paper after retries."""


def fetch_citing_pmids(pmid):
    """
    Returns the set of PMIDs that cite this paper, via Semantic Scholar.

    Retries on 429/5xx with exponential backoff, honouring Retry-After. Raises
    SemanticScholarUnavailable when the lookup genuinely could not be completed,
    so the caller can distinguish "no citations" from "could not check".
    """
    url = f"{S2_BASE}/PMID:{pmid}/citations"
    last = "unknown"
    for attempt in range(S2_MAX_RETRIES + 1):
        if attempt:
            delay = S2_BACKOFF_BASE * (2 ** (attempt - 1))
            time.sleep(delay + random.uniform(0, 0.5 * delay))
        try:
            r = requests.get(url, params={"fields": "externalIds"}, timeout=20)
        except Exception as exc:  # network-level failure
            last = f"{type(exc).__name__}: {exc}"
            continue

        if r.status_code in (429,) or r.status_code >= 500:
            last = f"HTTP {r.status_code}"
            S2_STATS["rate_limited"] += 1
            retry_after = r.headers.get("Retry-After")
            if retry_after:
                try:
                    time.sleep(min(float(retry_after), 60.0))
                except ValueError:
                    pass
            continue

        if r.status_code == 404:
            # Paper genuinely not in S2 -- a real "no citation data", not a failure.
            S2_STATS["empty"] += 1
            return set()

        if r.status_code != 200:
            last = f"HTTP {r.status_code}"
            break

        try:
            data = r.json()
        except ValueError as exc:
            last = f"invalid JSON: {exc}"
            continue

        cited_by = set()
        for item in data.get("data", []):
            ext = item.get("citingPaper", {}).get("externalIds", {}) or {}
            if "PubMed" in ext:
                cited_by.add(str(ext["PubMed"]))
        S2_STATS["ok"] += 1
        return cited_by

    S2_STATS["failed"] += 1
    raise SemanticScholarUnavailable(f"PMID {pmid}: {last}")


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
    citation_lookup_failures = 0
    for pmid in pmids:
        try:
            citation_cache[pmid] = fetch_citing_pmids(pmid)
        except SemanticScholarUnavailable:
            # Record the gap instead of pretending the paper has no citations.
            citation_cache[pmid] = set()
            citation_lookup_failures += 1
        time.sleep(S2_SLEEP)

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
    return len(components), edge_reasons, citation_lookup_failures


FAILURES_FILE = "data/_literature_failures.jsonl"


def record_failure(compound_name, exc, path=FAILURES_FILE):
    """Persist a per-compound failure (was print-only, E-021). The compound is not checkpointed, so a
    re-run retries it; agents 10g/10h read this file to report RETRIEVAL_FAILED, not 'never queried'."""
    from datetime import datetime, timezone
    msg = re.sub(r"(api_key=)[^&\s]+", r"\1<redacted>", str(exc))[:300]
    rec = {"compound_name": compound_name, "error_class": type(exc).__name__, "message": msg,
           "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with open(path, "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    return rec


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

    failures = []
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
                    cit_failures = 0
                else:
                    n_components, edge_reasons, cit_failures = build_dependency_graph(paper_details)

                record = {
                    "compound_name": compound,
                    "raw_paper_count": raw_count,
                    "effective_independent_count": n_components,
                    "independence_ratio": round(n_components / raw_count, 3) if raw_count > 0 else 0.0,
                    "edges_shared_author": edge_reasons["shared_author"],
                    "edges_citation": edge_reasons["citation"],
                    # Provenance: how many citation lookups could NOT be completed
                    # for this compound. >0 means independence_ratio is an
                    # UPPER BOUND for this compound, not a measurement.
                    "citation_lookup_failures": cit_failures,
                    "citation_coverage_complete": cit_failures == 0,
                }
                ckpt.write(json.dumps(record) + "\n")
                ckpt.flush()
            except Exception as e:
                record_failure(compound, e)
                failures.append(compound)
                print(f"  error for {compound}: {type(e).__name__} (recorded in {FAILURES_FILE})")
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

    # Citation-coverage report. A silently throttled run previously looked
    # identical to a clean one (E-009); it cannot any more.
    print("\nSemantic Scholar citation coverage:")
    print(f"  lookups OK:           {S2_STATS['ok']}")
    print(f"  404 (no S2 record):   {S2_STATS['empty']}")
    print(f"  rate-limit responses: {S2_STATS['rate_limited']}")
    print(f"  lookups FAILED:       {S2_STATS['failed']}")
    if "citation_lookup_failures" in out.columns:
        incomplete = int((out["citation_lookup_failures"] > 0).sum())
        print(f"  compounds with INCOMPLETE citation coverage: {incomplete} / {len(out)}")
        if incomplete:
            print("  WARNING: independence_ratio is an UPPER BOUND for those compounds "
                  "(missing citation edges inflate the component count).")
    if failures:
        print(f"\nINCOMPLETE: {len(failures)} compound(s) failed and have no row: {failures}. Re-run to retry.")
        raise SystemExit(1)


if __name__ == "__main__":
    import argparse
    # No options yet: parse anyway so --help or a stray argument exits before any
    # work is done (TD-034; incident E-017 ran stages 05/06 via --help).
    argparse.ArgumentParser(description=__doc__.strip().splitlines()[0] if __doc__ else None).parse_args()
    main()