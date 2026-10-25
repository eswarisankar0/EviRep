"""
STEP 4p: persist the literature evidence behind stage 04 with stable identifiers and dates (TD-021).

Stage 04 keeps only per-compound counts; its PMIDs, publication dates and the size of the
truncation (retmax 30) were never stored, so the literature dimension cannot be audited, deduplicated
or bounded at the cutoff. This stage re-runs the SAME PubMed query for every evaluable compound and
persists what it returns. It writes new files only; it never changes stage 04's outputs or VPS.

Per compound, three PubMed E-utilities calls (cached raw responses under data/cache/pubmed_lit/):
  1. esearch, the stage-04 query, retmax 30, PubMed default order   -> the sample stage 04 sees today
  2. esearch, same query bounded to publication date <= cutoff (pdat), retmax 500
                                                                    -> the cutoff-eligible literature
  3. efetch of the union of PMIDs                                    -> ids, dates, types, authors

Outputs
  data/literature_papers.jsonl      one record per (compound, PMID): DOI, dates + precision, cutoff status,
                                    publication types, MeSH, authors, sample membership, duplicate group
  data/literature_provenance.csv    one row per compound: hit counts, truncation, pre/post/unknown counts,
                                    duplicates, agreement with the stage-04 checkpoint count, status
  data/literature_provenance_run.json   run record (status, counts, failures, retrieval times)

Failure semantics: a compound whose retrieval fails is recorded as RETRIEVAL_FAILED (never as "no
literature"), nothing is written for it in the paper file, and the stage exits 1 so the runner marks
it PARTIAL. NO_RESULTS means PubMed answered with zero hits.

    ./venv/bin/python scripts/04p_literature_provenance.py            # cache first, network for misses
    ./venv/bin/python scripts/04p_literature_provenance.py --offline  # cache only
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import pandas as pd

NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
MAX_PAPERS_PER_COMPOUND = 30          # stage 04's sample size
BOUNDED_RETMAX = 500
CUTOFF = "2020-12-31"                 # last day of the pre-cutoff window (stage 03 cutoff)
CACHE_DIR = "data/cache/pubmed_lit"
COMPOUNDS_FILE = "data/clinical_maturity_precutoff_clean.csv"   # stage 04's input
STAGE04_CHECKPOINT = "data/_literature_checkpoint.jsonl"
PAPERS_OUT = "data/literature_papers.jsonl"
SUMMARY_OUT = "data/literature_provenance.csv"
RUN_OUT = "data/literature_provenance_run.json"
CACHE_VERSION = 1                     # raw responses; parsing changes do not invalidate it
NOT_PRIMARY_TYPES = {"Published Erratum", "Retraction of Publication", "Comment", "Duplicate Publication",
                     "Expression of Concern", "Editorial", "Letter", "News", "Book Chapter"}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                      "nov", "dec"], 1)}


class RetrievalError(Exception):
    """PubMed did not give a usable answer. Never to be read as 'no literature'."""


def _api_key():
    v = (os.environ.get("NCBI_API_KEY") or "").strip()
    return v if len(v) >= 20 and v.lower() not in {"your_key", "changeme", "placeholder"} else ""


def stage04_query(compound, disease="Parkinson Disease"):
    """Identical to scripts/04_literature_independence.search_pmids (checked by a test)."""
    return f'"{compound}"[Title/Abstract] AND "{disease}"[Title/Abstract]'


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


# ---------------------------------------------------------------------------
# HTTP with bounded retries
# ---------------------------------------------------------------------------

def _get(session, endpoint, params, retries=3, backoff=2.0, sleep=None):
    key = _api_key()
    if key:
        params = {**params, "api_key": key}
    last = None
    for attempt in range(retries + 1):
        try:
            r = session.get(f"{NCBI_BASE}/{endpoint}", params=params, timeout=30)
        except Exception as exc:                       # network-level failure
            last = f"{type(exc).__name__}"
        else:
            if r.status_code == 200:
                (sleep or time.sleep)(0.11 if key else 0.35)
                return r
            last = f"HTTP {r.status_code}"
            if r.status_code not in (429, 500, 502, 503, 504):
                break
        if attempt < retries:
            (sleep or time.sleep)(backoff * (2 ** attempt))
    raise RetrievalError(f"{endpoint}: {last} after {attempt + 1} attempt(s)")


def esearch(session, term, retmax, maxdate=None, sleep=None):
    params = {"db": "pubmed", "term": term, "retmax": retmax, "retmode": "json"}
    if maxdate:
        params.update({"datetype": "pdat", "mindate": "1800/01/01", "maxdate": maxdate})
    r = _get(session, "esearch.fcgi", params, sleep=sleep)
    try:
        res = r.json()["esearchresult"]
    except (ValueError, KeyError) as exc:
        raise RetrievalError(f"esearch: unparseable response ({type(exc).__name__})")
    if "ERROR" in res or "count" not in res:
        raise RetrievalError(f"esearch: error in response: {str(res.get('ERROR'))[:120]}")
    ids = [str(i) for i in res.get("idlist", [])]
    return {"count": int(res["count"]), "idlist": ids, "querytranslation": res.get("querytranslation"),
            "warnings": res.get("warninglist") or None}


def efetch(session, pmids, sleep=None):
    chunks = []
    for i in range(0, len(pmids), 200):
        r = _get(session, "efetch.fcgi", {"db": "pubmed", "id": ",".join(pmids[i:i + 200]), "retmode": "xml"},
                 sleep=sleep)
        chunks.append(r.content.decode("utf-8"))
    return chunks


# ---------------------------------------------------------------------------
# Parsing (pure; offline-testable)
# ---------------------------------------------------------------------------

def _date(el):
    """(iso, precision) from a PubMed date element; None when absent or unparseable."""
    if el is None:
        return None
    y = (el.findtext("Year") or "").strip()
    if not re.fullmatch(r"\d{4}", y):
        m = re.match(r"\s*(\d{4})", el.findtext("MedlineDate") or "")
        return (m.group(1), "year") if m else None
    mo = (el.findtext("Month") or "").strip()
    mnum = int(mo) if mo.isdigit() else MONTHS.get(mo[:3].lower())
    if not mnum or not 1 <= mnum <= 12:
        return (y, "year")
    d = (el.findtext("Day") or "").strip()
    if d.isdigit() and 1 <= int(d) <= 31:
        return (f"{y}-{mnum:02d}-{int(d):02d}", "day")
    return (f"{y}-{mnum:02d}", "month")


def cutoff_status(iso, cutoff=CUTOFF):
    """PRE_CUTOFF / POST_CUTOFF / UNKNOWN for a date of any precision; a partial date straddling the cutoff
    (e.g. year == cutoff year at year precision is fine, since the cutoff is the year's last day)."""
    if not iso:
        return "UNKNOWN"
    n = len(iso)
    c = cutoff[:n]
    if iso < c:
        return "PRE_CUTOFF"
    if iso > c:
        return "POST_CUTOFF"
    # equal at this precision: the cutoff is the period's last day only if the period ends on it
    return "PRE_CUTOFF" if cutoff.endswith("12-31") or n == 10 else "UNKNOWN"


def parse_articles(xml_text):
    out = {}
    root = ET.fromstring(xml_text)
    for art in root.findall(".//PubmedArticle"):
        pmid = (art.findtext(".//MedlineCitation/PMID") or "").strip()
        if not pmid:
            continue
        journal = _date(art.find(".//Article/Journal/JournalIssue/PubDate"))
        electronic = _date(art.find(".//Article/ArticleDate"))
        entrez = _date(art.find(".//PubmedData/History/PubMedPubDate[@PubStatus='pubmed']"))
        candidates = [d for d in (journal, electronic) if d]
        # Earliest public availability: the earlier of the print and electronic dates. Compare on the shared
        # precision so a year-only print date never beats a day-precision electronic date spuriously.
        earliest = min(candidates, key=lambda d: d[0]) if candidates else None
        doi = None
        for aid in art.findall(".//PubmedData/ArticleIdList/ArticleId"):
            if aid.get("IdType") == "doi" and aid.text:
                doi = aid.text.strip().lower()
        title_el = art.find(".//Article/ArticleTitle")
        title = "".join(title_el.itertext()).strip() if title_el is not None else None
        authors = []
        for a in art.findall(".//AuthorList/Author"):
            last, init = a.findtext("LastName"), a.findtext("Initials")
            if last:
                authors.append(f"{last}_{init or ''}")
            elif a.findtext("CollectiveName"):
                authors.append(f"COLLECTIVE:{a.findtext('CollectiveName').strip()}")
        links = [{"type": c.get("RefType"), "pmid": c.findtext("PMID")}
                 for c in art.findall(".//CommentsCorrectionsList/CommentsCorrections")
                 if c.get("RefType") in ("ErratumFor", "RepublishedFrom", "UpdateOf", "RetractionOf",
                                         "DuplicateOf", "ReprintOf") and c.findtext("PMID")]
        ptypes = [p.text for p in art.findall(".//PublicationTypeList/PublicationType") if p.text]
        out[pmid] = {
            "pmid": pmid, "doi": doi, "title": title, "journal": art.findtext(".//Article/Journal/Title"),
            "journal_pub_date": journal[0] if journal else None,
            "electronic_pub_date": electronic[0] if electronic else None,
            "pubmed_entry_date": entrez[0] if entrez else None,
            "earliest_pub_date": earliest[0] if earliest else None,
            "earliest_pub_date_precision": earliest[1] if earliest else None,
            "publication_types": ptypes,
            "mesh_terms": [d.text for d in art.findall(".//MeshHeadingList/MeshHeading/DescriptorName") if d.text],
            "authors": authors,
            "linked_records": links,
            "record_type": "JOURNAL_ARTICLE",
        }
    for book in root.findall(".//PubmedBookArticle"):
        # Book chapters (GeneReviews, StatPearls, LiverTox ...). Stage 04 never counted them (it parses
        # PubmedArticle only). Living books are revised continuously and the Book/PubDate is the series start,
        # so only an explicit ContributionDate dates the chapter; otherwise the date is UNKNOWN.
        pmid = (book.findtext(".//BookDocument/PMID") or "").strip()
        if not pmid:
            continue
        contributed = _date(book.find(".//BookDocument/ContributionDate"))
        revised = _date(book.find(".//BookDocument/DateRevised"))
        title_el = book.find(".//BookDocument/ArticleTitle")
        if title_el is None:
            title_el = book.find(".//BookDocument/Book/BookTitle")
        authors = [f"{a.findtext('LastName')}_{a.findtext('Initials') or ''}"
                   for a in book.findall(".//BookDocument/AuthorList[@Type='authors']/Author") if a.findtext("LastName")]
        out[pmid] = {
            "pmid": pmid, "doi": None,
            "title": "".join(title_el.itertext()).strip() if title_el is not None else None,
            "journal": "".join(book.find(".//BookDocument/Book/BookTitle").itertext()).strip()
            if book.find(".//BookDocument/Book/BookTitle") is not None else None,
            "journal_pub_date": None, "electronic_pub_date": None,
            "pubmed_entry_date": revised[0] if revised else None,
            "earliest_pub_date": contributed[0] if contributed else None,
            "earliest_pub_date_precision": contributed[1] if contributed else None,
            "publication_types": sorted({"Book Chapter"} | {p.text for p in book.findall(".//BookDocument/PublicationType")
                                                            if p.text}),
            "mesh_terms": [], "authors": authors, "linked_records": [],
            "record_type": "BOOK_CHAPTER",
        }
    return out


def _norm_title(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def duplicate_groups(papers):
    """Group records that are the same publication: shared DOI, identical normalised title, or an explicit
    PubMed link (erratum/republication/duplicate). Returns {pmid: group_id} with group_id = smallest PMID."""
    parent = {p["pmid"]: p["pmid"] for p in papers}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            lo, hi = sorted((ra, rb), key=int)
            parent[hi] = lo
    by_doi, by_title = {}, {}
    for p in sorted(papers, key=lambda p: int(p["pmid"])):
        if p.get("doi"):
            by_doi.setdefault(p["doi"], []).append(p["pmid"])
        t = _norm_title(p.get("title"))
        if len(t) >= 20:
            by_title.setdefault(t, []).append(p["pmid"])
        for link in p.get("linked_records", []):
            if link["pmid"] in parent:
                union(p["pmid"], link["pmid"])
    for groups in (by_doi, by_title):
        for ids in groups.values():
            for other in ids[1:]:
                union(ids[0], other)
    return {pm: find(pm) for pm in parent}


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _cache_path(root, compound):
    return os.path.join(root, CACHE_DIR, f"{slug(compound)}.json")


def load_cache(root, compound):
    """The cached retrieval, or None when absent, for another query, or corrupt (then it is refetched)."""
    path = _cache_path(root, compound)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            c = json.load(fh)
        if c.get("cache_version") != CACHE_VERSION or c.get("query") != stage04_query(compound) \
                or c.get("cutoff") != CUTOFF:
            return None
        papers = {}
        for chunk in c["efetch_xml"]:
            papers.update(parse_articles(chunk))
        wanted = set(c["sample"]["idlist"]) | set(c["bounded"]["idlist"])
        if hashlib.sha256("".join(c["efetch_xml"]).encode()).hexdigest() != c["efetch_sha256"]:
            return None
        if not wanted <= set(papers) | set(c.get("efetch_missing", [])):
            return None
        return c
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError):
        return None


def retrieve(session, compound, sleep=None):
    q = stage04_query(compound)
    sample = esearch(session, q, MAX_PAPERS_PER_COMPOUND, sleep=sleep)
    bounded = esearch(session, q, BOUNDED_RETMAX, maxdate=CUTOFF.replace("-", "/"), sleep=sleep)
    pmids = sorted(set(sample["idlist"]) | set(bounded["idlist"]), key=int)
    xml = efetch(session, pmids, sleep=sleep) if pmids else []
    got = {}
    for chunk in xml:
        try:
            got.update(parse_articles(chunk))
        except ET.ParseError as exc:
            raise RetrievalError(f"efetch: unparseable XML ({exc})")
    missing = sorted(set(pmids) - set(got), key=int)
    if pmids and len(missing) == len(pmids):
        raise RetrievalError(f"efetch returned none of {len(pmids)} requested PMIDs")
    joined = "".join(xml)
    return {"cache_version": CACHE_VERSION, "compound": compound, "query": q, "cutoff": CUTOFF,
            "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sample": sample, "bounded": bounded, "efetch_xml": xml,
            "efetch_sha256": hashlib.sha256(joined.encode()).hexdigest(), "efetch_missing": missing}


def write_json_atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def compound_records(c):
    papers = {}
    for chunk in c["efetch_xml"]:
        papers.update(parse_articles(chunk))
    sample, bounded = set(c["sample"]["idlist"]), set(c["bounded"]["idlist"])
    groups = duplicate_groups(list(papers.values()))
    rows = []
    for pm in sorted(papers, key=int):
        p = papers[pm]
        status = cutoff_status(p["earliest_pub_date"])
        rows.append({"compound_name": c["compound"], **p,
                     "cutoff_status": status,
                     "cutoff_basis": ("earliest of journal and electronic publication date"
                                      if p["record_type"] == "JOURNAL_ARTICLE" else "book ContributionDate only"),
                     "in_stage04_sample": pm in sample,
                     "in_cutoff_bounded_search": pm in bounded,
                     "duplicate_group": groups[pm],
                     "is_primary_record": groups[pm] == pm,
                     "not_primary_evidence_type": sorted(set(p["publication_types"]) & NOT_PRIMARY_TYPES) or None,
                     "retrieved_utc": c["retrieved_utc"]})
    return rows


def summarise(c, rows, stage04_count):
    s = [r for r in rows if r["in_stage04_sample"]]
    b = [r for r in rows if r["in_cutoff_bounded_search"]]
    count = lambda rs, st: sum(1 for r in rs if r["cutoff_status"] == st)
    n_hits = c["sample"]["count"]
    return {
        "compound_name": c["compound"],
        "status": "SUCCESS" if n_hits else "NO_RESULTS",
        "pubmed_total_hits": n_hits,
        "sample_n": len(c["sample"]["idlist"]),
        "sample_truncated": n_hits > len(c["sample"]["idlist"]),
        "sample_pre_cutoff": count(s, "PRE_CUTOFF"),
        "sample_post_cutoff": count(s, "POST_CUTOFF"),
        "sample_date_unknown": count(s, "UNKNOWN"),
        "sample_duplicate_records": sum(1 for r in s if not r["is_primary_record"]),
        "sample_not_primary_evidence": sum(1 for r in s if r["not_primary_evidence_type"]),
        "cutoff_bounded_hits": c["bounded"]["count"],
        "cutoff_bounded_retrieved": len(c["bounded"]["idlist"]),
        "cutoff_bounded_truncated": c["bounded"]["count"] > len(c["bounded"]["idlist"]),
        "cutoff_bounded_primary_records": sum(1 for r in b if r["is_primary_record"] and
                                              not r["not_primary_evidence_type"]),
        "sample_book_chapters": sum(1 for r in s if r["record_type"] == "BOOK_CHAPTER"),
        # requested but not parsed (recomputed with the current parser, not read from the cache)
        "efetch_missing": len((set(c["sample"]["idlist"]) | set(c["bounded"]["idlist"])) - {r["pmid"] for r in rows}),
        "stage04_raw_paper_count": stage04_count,
        "sample_size_matches_stage04": (None if stage04_count is None else len(c["sample"]["idlist"]) == stage04_count),
        "retrieved_utc": c["retrieved_utc"],
    }


def _stage04_counts(root):
    out = {}
    p = os.path.join(root, STAGE04_CHECKPOINT)
    if os.path.exists(p):
        with open(p) as fh:
            for line in fh:
                if line.strip():
                    r = json.loads(line)
                    out[r["compound_name"]] = r.get("raw_paper_count")
    return out


def main(argv=None, session=None, root=".", sleep=None):
    ap = argparse.ArgumentParser(description="Persist PMIDs, dates and cutoff status behind stage 04 (TD-021).")
    ap.add_argument("--offline", action="store_true", help="cache only; a cache miss is a recorded failure")
    ap.add_argument("--refresh", action="store_true", help="ignore the cache and re-query PubMed")
    ap.add_argument("--compound", action="append", help="restrict to these compounds (testing)")
    args = ap.parse_args(argv)
    j = lambda p: os.path.join(root, p)
    compounds = sorted(pd.read_csv(j(COMPOUNDS_FILE))["compound_name"].dropna().unique())
    if args.compound:
        unknown = sorted(set(args.compound) - set(compounds))
        if unknown:
            ap.error(f"not in {COMPOUNDS_FILE}: {unknown}")
        compounds = sorted(args.compound)
    if session is None and not args.offline:
        import requests
        session = requests.Session()
    os.makedirs(j(CACHE_DIR), exist_ok=True)
    s04 = _stage04_counts(root)
    rows, summary, failures = [], [], []
    n_cache, n_net = 0, 0
    for comp in compounds:
        c = None if args.refresh else load_cache(root, comp)
        if c is not None:
            n_cache += 1
        elif args.offline:
            failures.append({"compound_name": comp, "error": "offline and no valid cache entry"})
        else:
            try:
                c = retrieve(session, comp, sleep=sleep)
                write_json_atomic(_cache_path(root, comp), c)
                n_net += 1
            except RetrievalError as exc:
                failures.append({"compound_name": comp, "error": str(exc)[:200]})
        if c is None:
            summary.append({"compound_name": comp, "status": "RETRIEVAL_FAILED"})
            continue
        recs = compound_records(c)
        rows.extend(recs)
        summary.append(summarise(c, recs, s04.get(comp)))
    status = "FAILED" if len(failures) == len(compounds) else ("PARTIAL" if failures else "SUCCESS")
    if status == "FAILED":
        print(f"FAILED: no compound retrieved ({failures[:3]}); nothing written", file=sys.stderr)
        return 1
    df = pd.DataFrame(summary)
    tmp = j(SUMMARY_OUT) + ".tmp"
    df.to_csv(tmp, index=False)
    os.replace(tmp, j(SUMMARY_OUT))
    tmp = j(PAPERS_OUT) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")
    os.replace(tmp, j(PAPERS_OUT))
    ok = df[df["status"] != "RETRIEVAL_FAILED"]
    run = {"stage": "04p", "status": status, "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "cutoff": CUTOFF, "n_compounds": len(compounds), "n_retrieved": int(len(ok)),
           "n_failed": len(failures), "failures": failures, "from_cache": n_cache, "from_network": n_net,
           "n_paper_records": len(rows),
           "n_no_results": int((ok["status"] == "NO_RESULTS").sum()) if len(ok) else 0,
           "n_sample_size_mismatch_vs_stage04": int((ok.get("sample_size_matches_stage04") == False).sum())
           if len(ok) else 0,
           "limitations": [
               "PubMed is queried today: the sample may differ from the one stage 04 used when it ran "
               "(new papers, re-indexing); sample_size_matches_stage04 flags count differences only",
               "the cutoff-bounded search uses PubMed's publication date (pdat); cutoff_status uses the earliest "
               "of the journal and electronic dates and may differ for papers near the cutoff",
               "duplicate detection covers shared DOI, identical title and explicit PubMed links only"]}
    write_json_atomic(j(RUN_OUT), run)
    print(f"04p: {len(ok)}/{len(compounds)} compounds, {len(rows)} paper records "
          f"(cache {n_cache}, network {n_net}); failures {len(failures)}; status {status}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
