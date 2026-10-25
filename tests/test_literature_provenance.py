"""
Tests for scripts/04p_literature_provenance.py (TD-021): same query as stage 04, date parsing and cutoff
status at every precision, book chapters, duplicate detection, bounded retries, failure semantics
(RETRIEVAL_FAILED is never NO_RESULTS), cache validation and deterministic output. No network.
"""

import importlib.util
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("lit04p", os.path.join(ROOT, "scripts", "04p_literature_provenance.py"))
lp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lp)


def article(pmid, year="2019", month="Mar", day=None, doi=None, title=None, ptypes=("Journal Article",),
            edate=None, links=()):
    d = f"<Day>{day}</Day>" if day else ""
    m = f"<Month>{month}</Month>" if month else ""
    e = (f"<ArticleDate DateType='Electronic'><Year>{edate[:4]}</Year><Month>{edate[5:7]}</Month>"
         f"<Day>{edate[8:10]}</Day></ArticleDate>") if edate else ""
    ids = f"<ArticleId IdType='doi'>{doi}</ArticleId>" if doi else ""
    pts = "".join(f"<PublicationType>{p}</PublicationType>" for p in ptypes)
    cc = "".join(f"<CommentsCorrections RefType='{t}'><PMID>{p}</PMID></CommentsCorrections>" for t, p in links)
    return (f"<PubmedArticle><MedlineCitation><PMID>{pmid}</PMID><Article><Journal><Title>J</Title><JournalIssue>"
            f"<PubDate><Year>{year}</Year>{m}{d}</PubDate></JournalIssue></Journal>"
            f"<ArticleTitle>{title or 'Paper ' + pmid + ' about levodopa and Parkinson disease'}</ArticleTitle>"
            f"<AuthorList><Author><LastName>Smith</LastName><Initials>J</Initials></Author></AuthorList>{e}"
            f"<PublicationTypeList>{pts}</PublicationTypeList></Article>"
            f"<CommentsCorrectionsList>{cc}</CommentsCorrectionsList></MedlineCitation>"
            f"<PubmedData><ArticleIdList>{ids}</ArticleIdList></PubmedData></PubmedArticle>")


BOOK = ("<PubmedBookArticle><BookDocument><PMID>900</PMID><Book><BookTitle>StatPearls</BookTitle>"
        "<PubDate><Year>2017</Year></PubDate></Book><ArticleTitle>Drug X</ArticleTitle>"
        "<AuthorList Type='authors'><Author><LastName>Doe</LastName><Initials>A</Initials></Author></AuthorList>"
        "<PublicationType>Review</PublicationType></BookDocument></PubmedBookArticle>")


def xmlset(*arts):
    return "<PubmedArticleSet>" + "".join(arts) + "</PubmedArticleSet>"


class Resp:
    def __init__(self, code=200, payload=None, text=""):
        self.status_code, self._payload, self.content = code, payload, text.encode()

    def raise_for_status(self):
        if self.status_code != 200:
            raise RuntimeError(self.status_code)

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakePubMed:
    """esearch/efetch over an in-memory corpus {compound: [(pmid, xml), ...]}; bounded = pmid listed in `pre`."""

    def __init__(self, corpus, pre=(), fail=None, script=None):
        self.corpus, self.pre, self.fail, self.script, self.calls = corpus, set(pre), fail or set(), script, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params)))
        if self.script:
            return self.script.pop(0)
        if "esearch" in url:
            comp = params["term"].split('"')[1]
            if comp in self.fail:
                return Resp(500)
            ids = [p for p, _ in self.corpus.get(comp, [])]
            if "maxdate" in params:
                ids = [p for p in ids if p in self.pre]
            return Resp(200, {"esearchresult": {"count": str(len(ids)), "idlist": ids[:int(params["retmax"])],
                                                "querytranslation": params["term"]}})
        want = params["id"].split(",")
        arts = [x for comp in self.corpus.values() for p, x in comp if p in want]
        return Resp(200, text=xmlset(*arts))


def nosleep(_):
    return None


class TestQueryAndParsing(unittest.TestCase):
    def test_query_is_stage04s(self):
        spec = importlib.util.spec_from_file_location("s04", os.path.join(ROOT, "scripts", "04_literature_independence.py"))
        s04 = importlib.util.module_from_spec(spec)
        cwd = os.getcwd()
        tmp = tempfile.mkdtemp()
        try:
            os.chdir(tmp)                     # stage 04 creates data/ on import
            spec.loader.exec_module(s04)
        finally:
            os.chdir(cwd)
            shutil.rmtree(tmp)
        captured = {}

        def fake_get(url, params=None, timeout=None):
            captured.update(params)
            return Resp(200, text="<eSearchResult><IdList/></eSearchResult>")
        with mock.patch.object(s04.requests, "get", fake_get):
            s04.search_pmids("Droxidopa")
        self.assertEqual(captured["term"], lp.stage04_query("Droxidopa"))
        self.assertEqual(captured["retmax"], lp.MAX_PAPERS_PER_COMPOUND)

    def test_dates_and_precision(self):
        p = lp.parse_articles(xmlset(article("1", "2020", "Dec", "31"), article("2", "2021", None),
                                     article("3", "2020", "Nov", edate="2021-01-04"),
                                     article("4", "2021", "Jan", edate="2020-12-20")))
        self.assertEqual((p["1"]["earliest_pub_date"], p["1"]["earliest_pub_date_precision"]), ("2020-12-31", "day"))
        self.assertEqual(p["2"]["earliest_pub_date_precision"], "year")
        self.assertEqual(p["3"]["earliest_pub_date"], "2020-11")          # print date earlier than e-pub
        self.assertEqual(p["4"]["earliest_pub_date"], "2020-12-20")       # e-pub ahead of print counts
        st = {k: lp.cutoff_status(v["earliest_pub_date"]) for k, v in p.items()}
        self.assertEqual(st, {"1": "PRE_CUTOFF", "2": "POST_CUTOFF", "3": "PRE_CUTOFF", "4": "PRE_CUTOFF"})

    def test_cutoff_status_edges(self):
        self.assertEqual(lp.cutoff_status("2020"), "PRE_CUTOFF")         # the cutoff is the year's last day
        self.assertEqual(lp.cutoff_status("2020-12"), "PRE_CUTOFF")
        self.assertEqual(lp.cutoff_status("2021-01-01"), "POST_CUTOFF")
        self.assertEqual(lp.cutoff_status(None), "UNKNOWN")
        self.assertEqual(lp.cutoff_status("2020-06", cutoff="2020-06-15"), "UNKNOWN")   # straddles a mid-month cutoff

    def test_book_chapter_is_parsed_undated_and_not_primary(self):
        p = lp.parse_articles(xmlset(BOOK))["900"]
        self.assertEqual(p["record_type"], "BOOK_CHAPTER")
        self.assertIsNone(p["earliest_pub_date"])                  # series start year is not the chapter's date
        self.assertIn("Book Chapter", p["publication_types"])

    def test_duplicates_by_doi_title_and_link(self):
        p = lp.parse_articles(xmlset(article("10", doi="10.1/A"), article("11", doi="10.1/a"),
                                     article("20", title="Exactly the same title about drug x in PD"),
                                     article("21", title="Exactly the same title, about drug X in PD!"),
                                     article("30"), article("31", ptypes=("Published Erratum",), links=[("ErratumFor", "30")]),
                                     article("40")))
        g = lp.duplicate_groups(list(p.values()))
        self.assertEqual(g["11"], "10")
        self.assertEqual(g["21"], "20")
        self.assertEqual(g["31"], "30")
        self.assertEqual(g["40"], "40")


class TestRun(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "data"))
        with open(os.path.join(self.root, lp.COMPOUNDS_FILE), "w") as fh:
            fh.write("compound_name,nct_id\nAlpha,NCT1\nBeta,NCT2\nGamma,NCT3\n")
        with open(os.path.join(self.root, lp.STAGE04_CHECKPOINT), "w") as fh:
            fh.write(json.dumps({"compound_name": "Alpha", "raw_paper_count": 3}) + "\n")
        self.corpus = {"Alpha": [("1", article("1", "2018")), ("2", article("2", "2022")), ("3", article("3", "2020", "Dec"))],
                       "Beta": [("5", article("5", "2023"))], "Gamma": []}
        self.pre = {"1", "3"}

    def tearDown(self):
        shutil.rmtree(self.root)

    def run_main(self, argv=(), session=None):
        return lp.main(list(argv), session=session, root=self.root, sleep=nosleep)

    def raw(self):
        out = []
        for rel in (lp.PAPERS_OUT, lp.SUMMARY_OUT):
            with open(os.path.join(self.root, rel), "rb") as fh:
                out.append(fh.read())
        return out

    def read(self):
        import pandas as pd
        s = pd.read_csv(os.path.join(self.root, lp.SUMMARY_OUT)).set_index("compound_name")
        with open(os.path.join(self.root, lp.PAPERS_OUT)) as fh:
            papers = [json.loads(l) for l in fh]
        return s, papers

    def test_success_counts_and_no_results(self):
        self.assertEqual(self.run_main(session=FakePubMed(self.corpus, self.pre)), 0)
        s, papers = self.read()
        self.assertEqual(s.loc["Alpha", "sample_pre_cutoff"], 2)
        self.assertEqual(s.loc["Alpha", "sample_post_cutoff"], 1)
        self.assertEqual(s.loc["Alpha", "cutoff_bounded_hits"], 2)
        self.assertTrue(bool(s.loc["Alpha", "sample_size_matches_stage04"]))
        self.assertEqual(s.loc["Gamma", "status"], "NO_RESULTS")
        self.assertEqual(sorted(p["pmid"] for p in papers), ["1", "2", "3", "5"])

    def test_failed_compound_is_retrieval_failed_not_no_results(self):
        rc = self.run_main(session=FakePubMed(self.corpus, self.pre, fail={"Beta"}))
        self.assertEqual(rc, 1)
        s, papers = self.read()
        self.assertEqual(s.loc["Beta", "status"], "RETRIEVAL_FAILED")
        self.assertNotIn("Beta", {p["compound_name"] for p in papers})
        with open(os.path.join(self.root, lp.RUN_OUT)) as fh:
            run = json.load(fh)
        self.assertEqual((run["status"], run["n_failed"]), ("PARTIAL", 1))

    def test_all_failed_writes_nothing(self):
        rc = self.run_main(session=FakePubMed(self.corpus, self.pre, fail={"Alpha", "Beta", "Gamma"}))
        self.assertEqual(rc, 1)
        self.assertFalse(os.path.exists(os.path.join(self.root, lp.SUMMARY_OUT)))
        self.assertFalse(os.path.exists(os.path.join(self.root, lp.PAPERS_OUT)))

    def test_retries_are_bounded_and_429_recovers(self):
        ok = Resp(200, {"esearchresult": {"count": "0", "idlist": []}})
        s = FakePubMed({}, script=[Resp(429), ok])
        self.assertEqual(lp.esearch(s, "q", 30, sleep=nosleep)["count"], 0)
        s = FakePubMed({}, script=[Resp(503)] * 10)
        with self.assertRaises(lp.RetrievalError):
            lp.esearch(s, "q", 30, sleep=nosleep)
        self.assertEqual(len(s.calls), 4)                                   # 1 + 3 retries
        s = FakePubMed({}, script=[Resp(400)] * 10)
        with self.assertRaises(lp.RetrievalError):
            lp.esearch(s, "q", 30, sleep=nosleep)
        self.assertEqual(len(s.calls), 1)                                   # client errors are not retried

    def test_error_payload_with_http_200_is_a_failure(self):
        s = FakePubMed({}, script=[Resp(200, {"esearchresult": {"ERROR": "Invalid query"}})])
        with self.assertRaises(lp.RetrievalError):
            lp.esearch(s, "q", 30, sleep=nosleep)

    def test_offline_uses_cache_and_reports_misses(self):
        self.run_main(["--compound", "Alpha"], session=FakePubMed(self.corpus, self.pre))
        with mock.patch.object(FakePubMed, "get", side_effect=AssertionError("network")):
            rc = self.run_main(["--offline"])
        self.assertEqual(rc, 1)                                             # Beta, Gamma not cached
        s, _ = self.read()
        self.assertEqual(s.loc["Alpha", "status"], "SUCCESS")
        self.assertEqual(s.loc["Beta", "status"], "RETRIEVAL_FAILED")

    def test_corrupt_cache_is_refetched(self):
        self.run_main(["--compound", "Alpha"], session=FakePubMed(self.corpus, self.pre))
        path = os.path.join(self.root, lp.CACHE_DIR, "alpha.json")
        with open(path) as fh:
            c = json.load(fh)
        c["efetch_xml"] = [c["efetch_xml"][0].replace("<PMID>3</PMID>", "<PMID>99</PMID>")]   # tampered
        with open(path, "w") as fh:
            json.dump(c, fh)
        self.assertIsNone(lp.load_cache(self.root, "Alpha"))
        fake = FakePubMed(self.corpus, self.pre)
        self.run_main(["--compound", "Alpha"], session=fake)
        self.assertTrue(fake.calls)
        self.assertIsNotNone(lp.load_cache(self.root, "Alpha"))

    def test_rerun_from_cache_is_byte_identical(self):
        self.run_main(session=FakePubMed(self.corpus, self.pre))
        a = self.raw()
        self.run_main(["--offline"])
        b = self.raw()
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
