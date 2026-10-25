"""
Offline tests for scripts/literature_credibility_agent.py (architecture 10a).

All records are synthetic fixtures (PMIDs 9000000x are not real papers).
A socket guard asserts the CLI with --xml makes no network connection.
"""

import importlib.util
import json
import pathlib
import os
import shutil
import socket
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("lca", os.path.join(ROOT, "scripts", "literature_credibility_agent.py"))
lca = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lca)


def article(pmid, pub_types=(), mesh=(), abstract=None, year="2019", medline_date=None, title="T"):
    pt = "".join(f"<PublicationType>{p}</PublicationType>" for p in pub_types)
    mh = ("<MeshHeadingList>" + "".join(f"<MeshHeading><DescriptorName>{m}</DescriptorName></MeshHeading>"
                                        for m in mesh) + "</MeshHeadingList>") if mesh else ""
    date = f"<MedlineDate>{medline_date}</MedlineDate>" if medline_date else (f"<Year>{year}</Year>" if year else "")
    ab = f"<Abstract><AbstractText>{abstract}</AbstractText></Abstract>" if abstract else ""
    return (f"<PubmedArticle><MedlineCitation><PMID>{pmid}</PMID><Article><Journal><Title>J</Title>"
            f"<JournalIssue><PubDate>{date}</PubDate></JournalIssue></Journal><ArticleTitle>{title}</ArticleTitle>"
            f"{ab}<PublicationTypeList>{pt}</PublicationTypeList></Article>{mh}</MedlineCitation></PubmedArticle>")


XML = ("<PubmedArticleSet>"
       + article("90000001", ["Randomized Controlled Trial", "Clinical Trial", "Journal Article"], ["Humans", "Male"],
                 "In this RCT, n = 120 patients were randomised.", "2018")
       + article("90000002", ["Review", "Journal Article"], ["Humans"], "We review 45 patients and 300 cases.", "2022")
       + article("90000003", ["Randomized Controlled Trial"], ["Animals", "Rats"], "Rats (n = 12).", "2016")
       + article("90000004", [], [], None, None, medline_date="2020 Nov-Dec")
       + article("90000005", ["Journal Article"], ["Humans"], "Observations.", "2021")
       + article("90000006", ["Retracted Publication", "Randomized Controlled Trial"], ["Humans"], "n = 30.", "2015")
       + article("90000007", ["Case Reports"], ["Humans", "Aged"], "A single patient.", "2010")
       + "</PubmedArticleSet>").encode()


def papers():
    return lca.parse_pubmed_xml(XML)


def by_pmid(report):
    return {p["pmid"]: p for p in report["papers"]}


class TestParsing(unittest.TestCase):
    def test_fields_parsed_and_missing_fields_stay_empty(self):
        p = {x["pmid"]: x for x in papers()}
        self.assertEqual(p["90000001"]["year"], "2018")
        self.assertIn("Randomized Controlled Trial", p["90000001"]["publication_types"])
        self.assertEqual(p["90000004"]["year"], "2020")          # from MedlineDate
        self.assertEqual(p["90000004"]["publication_types"], [])
        self.assertEqual(p["90000004"]["mesh_terms"], [])
        self.assertIsNone(p["90000004"]["abstract"])

    def test_malformed_xml_raises(self):
        with self.assertRaises(Exception):
            lca.parse_pubmed_xml(b"<PubmedArticleSet><PubmedArticle>")


class TestPaperAssessment(unittest.TestCase):
    def setUp(self):
        self.r = by_pmid(lca.assess_pair("DrugX", "Parkinson's disease", papers()))

    def test_rct_in_humans(self):
        a = self.r["90000001"]
        self.assertEqual((a["design"], a["population"], a["credibility_tier"]), ("RCT", "HUMAN", "A"))
        self.assertEqual(a["sample_size"], 120)
        self.assertEqual(a["sample_size_candidates"][0]["span"], "n = 120")   # traceable span
        self.assertEqual(a["design_source"], "PublicationType 'Randomized Controlled Trial'")

    def test_animal_study_capped_even_if_tagged_rct(self):
        a = self.r["90000003"]
        self.assertEqual(a["population"], "PRECLINICAL_ANIMAL")
        self.assertEqual(a["credibility_tier"], "C")
        self.assertIn("preclinical only", a["limitations"])

    def test_unknown_design_is_unknown_not_zero(self):
        a = self.r["90000004"]
        self.assertEqual(a["credibility_tier"], "U")
        self.assertIsNone(a["credibility_score"])
        self.assertEqual(a["population"], "UNKNOWN")
        a5 = self.r["90000005"]                                   # only 'Journal Article'
        self.assertEqual(a5["design"], "UNKNOWN")
        self.assertIsNone(a5["credibility_score"])

    def test_ambiguous_sample_size_not_chosen(self):
        a = self.r["90000002"]
        self.assertIsNone(a["sample_size"])
        self.assertEqual(sorted(c["value"] for c in a["sample_size_candidates"]), [45, 300])

    def test_retraction_overrides_design(self):
        a = self.r["90000006"]
        self.assertEqual((a["design"], a["credibility_tier"], a["credibility_score"]), ("RETRACTED", "X", 0.0))

    def test_cutoff_classification(self):
        self.assertEqual(self.r["90000001"]["temporal"], "PRE_CUTOFF")
        self.assertEqual(self.r["90000005"]["temporal"], "POST_CUTOFF")   # 2021 is on/after 2021-01-01
        self.assertEqual(self.r["90000002"]["temporal"], "POST_CUTOFF")
        mid = lca.assess_paper({"pmid": "1", "year": "2021"}, cutoff_date="2021-06-30")
        self.assertEqual(mid["temporal"], "UNKNOWN")                       # year granularity cannot decide
        self.assertEqual(lca.assess_paper({"pmid": "1", "year": "20x1"})["temporal"], "UNKNOWN")

    def test_direction_never_inferred_from_text(self):
        for a in self.r.values():
            self.assertEqual(a["direction"], "NOT_ASSESSED")
            self.assertIsNone(a["direction_source"])

    def test_comparative_study_tag_alone_does_not_imply_design(self):
        a = lca.assess_paper({"pmid": "1", "publication_types": ["Journal Article", "Comparative Study"],
                              "mesh_terms": ["Humans"]})
        self.assertEqual(a["design"], "UNKNOWN")
        self.assertIsNone(a["credibility_score"])

    def test_case_report_tag_conflicting_with_count_is_flagged_not_reclassified(self):
        a = lca.assess_paper({"pmid": "1", "publication_types": ["Case Reports"], "mesh_terms": ["Humans"],
                              "abstract": "A retrospective review of 101 patients."})
        self.assertEqual(a["design"], "CASE_REPORT")
        self.assertTrue(any("conflicts" in l for l in a["limitations"]))


class TestPairSynthesis(unittest.TestCase):
    def test_summary_excludes_unknown_from_mean(self):
        rep = lca.assess_pair("DrugX", "PD", papers())
        s = rep["summary_all"]
        self.assertEqual(s["n_papers"], 7)
        self.assertEqual(s["n_design_known"], 5)              # 0004 and 0005 unknown
        expected = round((1.0 + 0.3 + 0.3 + 0.0 + 0.3) / 5, 3)
        self.assertEqual(s["mean_credibility_score_known"], expected)
        self.assertEqual(rep["efficacy"], "NOT_ASSESSED")

    def test_pre_cutoff_summary_only_counts_pre_cutoff(self):
        rep = lca.assess_pair("DrugX", "PD", papers())
        pre = {p["pmid"] for p in rep["papers"] if p["temporal"] == "PRE_CUTOFF"}
        self.assertEqual(rep["summary_pre_cutoff"]["n_papers"], len(pre))
        self.assertNotIn("90000005", pre)

    def test_conflict_needs_curated_directions(self):
        ps = papers()
        for p in ps:
            if p["pmid"] == "90000001":
                p.update(direction="SUPPORTS", direction_source="curated: CASE_STUDIES §x")
        self.assertFalse(lca.assess_pair("D", "PD", ps)["summary_all"]["conflict"])
        ps.append({"pmid": "90000009", "publication_types": ["Randomized Controlled Trial"], "mesh_terms": ["Humans"],
                   "year": "2017", "direction": "OPPOSES", "direction_source": "curated"})
        rep = lca.assess_pair("D", "PD", ps)
        self.assertTrue(rep["summary_all"]["conflict"])
        self.assertEqual(by_pmid(rep)["90000009"]["direction_source"], "curated")

    def test_invalid_direction_is_not_assessed(self):
        a = lca.assess_paper({"pmid": "1", "direction": "probably works", "direction_source": "llm"})
        self.assertEqual(a["direction"], "NOT_ASSESSED")
        self.assertIsNone(a["direction_source"])

    def test_malformed_and_duplicate_records_are_rejected_not_scored(self):
        ps = papers() + [{"title": "no pmid"}, "junk", None, dict(papers()[0])]
        rep = lca.assess_pair("D", "PD", ps)
        self.assertEqual(rep["summary_all"]["n_papers"], 7)
        reasons = [r["reason"] for r in rep["rejected_records"]]
        self.assertEqual(reasons.count("duplicate PMID"), 1)
        self.assertEqual(len(reasons), 4)

    def test_replication_indicator_uses_supplied_components_only(self):
        ps = papers()
        self.assertIsNone(lca.assess_pair("D", "PD", ps)["summary_all"]["replication_indicator"]
                          ["distinct_components_among_human_A_B"])
        for p in ps:
            p["component"] = 0
        rep = lca.assess_pair("D", "PD", ps)
        self.assertEqual(rep["summary_all"]["replication_indicator"]["distinct_components_among_human_A_B"], 1)

    def test_empty_input(self):
        rep = lca.assess_pair("D", "PD", [])
        self.assertEqual(rep["summary_all"]["n_papers"], 0)
        self.assertIsNone(rep["summary_all"]["coverage"])
        with self.assertRaises(ValueError):
            lca.assess_pair("", "PD", [])

    def test_deterministic_and_order_independent(self):
        a = lca.assess_pair("D", "PD", papers())
        b = lca.assess_pair("D", "PD", list(reversed(papers())))
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_validate_output_contract(self):
        rep = lca.assess_pair("D", "PD", papers())
        lca.validate_output(rep)
        bad = json.loads(json.dumps(rep))
        bad["efficacy"] = "LIKELY"
        with self.assertRaises(ValueError):
            lca.validate_output(bad)
        bad = json.loads(json.dumps(rep))
        bad["papers"][0].update(credibility_tier="U", credibility_score=0.5)
        with self.assertRaises(ValueError):
            lca.validate_output(bad)


class TestCLIOffline(unittest.TestCase):
    def test_cli_with_saved_xml_makes_no_network_call(self):
        tmp = tempfile.mkdtemp()
        try:
            graph = {"compound": "DrugX", "nodes": [{"pmid": "90000001", "component": 0},
                                                    {"pmid": "90000002", "component": 1},
                                                    {"pmid": "99999999", "component": 2}]}
            gp, xp, op = (os.path.join(tmp, f) for f in ("g.json", "x.xml", "o.json"))
            pathlib.Path(gp).write_text(json.dumps(graph))
            pathlib.Path(xp).write_bytes(XML)

            def no_net(*a, **k):
                raise AssertionError("network used")
            with mock.patch.object(socket.socket, "connect", no_net), mock.patch("builtins.print"):
                lca.main(["--graph", gp, "--xml", xp, "--out", op])
            rep = json.loads(pathlib.Path(op).read_text())
            self.assertEqual(rep["provenance"]["missing_pmids"], ["99999999"])   # reported, not invented
            self.assertEqual(by_pmid(rep)["90000002"]["component"], 1)
            self.assertEqual(rep["provenance"]["source"], "saved PubMed efetch XML")
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()


class TestCuratedModeAndContract(unittest.TestCase):
    """2026-10-15: offline rating of the curated case-study PMIDs + shared agent envelope."""

    def test_curated_reports_from_cached_xml(self):
        import os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not os.path.exists(os.path.join(root, "data/cache/pubmed_efetch_case_claims.xml")):
            self.skipTest("cached XML absent")
        reps = lca.curated_reports(root)
        self.assertEqual(sorted(reps), ["Domperidone", "Donepezil", "Melatonin", "Propranolol"])
        for name, r in reps.items():
            lca.validate_output(r)
            self.assertEqual(r["agent_id"], "10a")
            self.assertEqual(r["efficacy"], "NOT_ASSESSED")
            self.assertIn(r["run_status"], ("SUCCESS", "PARTIAL"))
            for p in r["papers"]:
                if p["direction"] != "NOT_ASSESSED":
                    self.assertIn("curated claim", p["direction_source"])
        # Donepezil: PMID 25224676 has claims in both directions -> not collapsed into one
        don = {p["pmid"]: p for p in reps["Donepezil"]["papers"]}
        self.assertEqual(don["25224676"]["direction"], "NOT_ASSESSED")

    def test_missing_pmids_make_the_run_partial(self):
        rep = lca.assess_pair("X", "PD", [{"pmid": "1", "publication_types": ["Randomized Controlled Trial"]}])
        out = lca._contract(rep, ".", [], ["999"])
        self.assertEqual(out["run_status"], "PARTIAL")
        self.assertEqual(out["diagnostics"][0]["code"], "PMID_NOT_RETURNED")
        empty = lca._contract(lca.assess_pair("X", "PD", []), ".", [], [])
        self.assertEqual(empty["run_status"], "NO_EVIDENCE")


class TestAuditRegressions(unittest.TestCase):
    """Sprint 2026-10-19 audit of 10a."""

    def test_nothing_returned_for_requested_pmids_is_failed_not_no_evidence(self):
        out = lca._contract(lca.assess_pair("X", "PD", []), ".", [], ["111", "222"])
        self.assertEqual(out["run_status"], "FAILED")

    def test_graph_mode_assesses_only_papers_in_the_graph(self):
        tmp = tempfile.mkdtemp()
        try:
            graph = {"compound": "DrugX", "nodes": [{"pmid": "90000001", "component": 0}]}
            gp, xp, op = (os.path.join(tmp, f) for f in ("g.json", "x.xml", "o.json"))
            pathlib.Path(gp).write_text(json.dumps(graph))
            pathlib.Path(xp).write_bytes(XML)
            with mock.patch("builtins.print"):
                lca.main(["--graph", gp, "--xml", xp, "--out", op])
            rep = json.loads(pathlib.Path(op).read_text())
            self.assertEqual([p["pmid"] for p in rep["papers"]], ["90000001"])
            self.assertIn("NOT_IN_GRAPH", [d["code"] for d in rep["diagnostics"]])
        finally:
            shutil.rmtree(tmp)


class TestAllCompoundsMode(unittest.TestCase):
    """--all: every compound from stage 04p; duplicates rated once; 04p dates override issue years; failures kept."""

    def setUp(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        import test_literature_provenance as tlp
        self.tlp = tlp
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "data"))
        with open(os.path.join(self.root, tlp.lp.COMPOUNDS_FILE), "w") as fh:
            fh.write("compound_name,nct_id\nAlpha,NCT1\nBeta,NCT2\nGamma,NCT3\n")
        a = tlp.article
        corpus = {"Alpha": [("1", a("1", "2018", ptypes=("Randomized Controlled Trial",))),
                            ("2", a("2", "2021", "Jan", edate="2020-12-20")),          # e-pub before the cutoff
                            ("3", a("3", "2019", doi="10.1/x")), ("4", a("4", "2019", doi="10.1/X"))],   # duplicate
                  "Beta": [("5", a("5", "2023"))], "Gamma": []}
        self.fake = tlp.FakePubMed(corpus, pre={"1", "2", "3", "4"}, fail={"Beta"})
        tlp.lp.main([], session=self.fake, root=self.root, sleep=tlp.nosleep)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_report(self):
        rep = lca.all_compounds_report(self.root)
        c = rep["compounds"]
        self.assertEqual(c["Beta"]["status"], "RETRIEVAL_FAILED")           # never "no literature"
        self.assertEqual(c["Gamma"]["status"], "NO_RESULTS")
        self.assertEqual(rep["run_status"], "PARTIAL")
        alpha = c["Alpha"]
        self.assertEqual(sorted(p["pmid"] for p in alpha["papers"]), ["1", "2", "3"])
        self.assertEqual(alpha["duplicates_removed"][0]["record"], "4")
        temporal = {p["pmid"]: p["temporal"] for p in alpha["papers"]}
        self.assertEqual(temporal["2"], "PRE_CUTOFF")                       # 04p date, not the 2021 issue year
        self.assertEqual(alpha["summary_cutoff_bounded"]["n_papers"], 3)
        self.assertEqual(alpha["summary_stage04_sample"]["by_tier"].get("A"), 1)

    def test_unreadable_cache_is_a_failure_not_an_empty_result(self):
        with open(os.path.join(self.root, self.tlp.lp.CACHE_DIR, "alpha.json"), "w") as fh:
            fh.write("{not json")
        c = lca.all_compounds_report(self.root)
        self.assertEqual(c["compounds"]["Alpha"]["status"], "RETRIEVAL_FAILED")
        self.assertIn("CACHE_UNREADABLE", [d["code"] for d in c["diagnostics"]])

    def test_deterministic(self):
        a, b = lca.all_compounds_report(self.root), lca.all_compounds_report(self.root)
        for r in (a, b):
            r.pop("generated_utc")
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
