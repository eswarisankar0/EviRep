"""
Tests for the Evidence Independence Agent (10g), scripts/evidence_independence_agent.py.
Synthetic fixture repository + checks on the persisted output. Offline.
"""

import importlib.util
import json
import pathlib
import os
import shutil
import socket
import sys
import tempfile
import unittest

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
_spec = importlib.util.spec_from_file_location("ei10g", os.path.join(ROOT, "scripts", "evidence_independence_agent.py"))
ei = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ei)
from agent_contract import stale_inputs  # noqa: E402

_real_connect = socket.socket.connect

XML = b"""<PubmedArticleSet>
<PubmedArticle><MedlineCitation><PMID>11111111</PMID><Article><Journal><JournalIssue><PubDate><Year>2010</Year></PubDate></JournalIssue></Journal>
<Abstract><AbstractText>Results of NCT00000001 in PD.</AbstractText></Abstract><AuthorList><Author><LastName>Roe</LastName><Initials>J</Initials></Author></AuthorList>
<PublicationTypeList><PublicationType>Randomized Controlled Trial</PublicationType></PublicationTypeList></Article></MedlineCitation></PubmedArticle>
<PubmedArticle><MedlineCitation><PMID>22222222</PMID><Article><Journal><JournalIssue><PubDate><Year>2012</Year></PubDate></JournalIssue></Journal>
<Abstract><AbstractText>Secondary analysis of NCT00000001.</AbstractText></Abstract><AuthorList><Author><LastName>Doe</LastName><Initials>A</Initials></Author></AuthorList>
<PublicationTypeList><PublicationType>Journal Article</PublicationType></PublicationTypeList></Article></MedlineCitation></PubmedArticle>
</PubmedArticleSet>"""


def setUpModule():
    def refuse(*a, **k):
        raise AssertionError("tests must not open network connections")
    socket.socket.connect = refuse


def tearDownModule():
    socket.socket.connect = _real_connect


class TestFixture(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        d = os.path.join(self.root, "data")
        os.makedirs(os.path.join(d, "cache"))
        pd.DataFrame({"compound_name": ["Alpha", "Beta", "Gamma"], "label": [1, 0, 0]}).to_csv(os.path.join(self.root, ei.POOL), index=False)
        pd.DataFrame({"compound_name": ["Alpha", "Beta", "Gamma"], "nct_id": ["NCT00000001", "NCT00000001", "NCT00000003"],
                      "phase": ["PHASE2"] * 3}).to_csv(os.path.join(self.root, ei.LINKS), index=False)
        pd.DataFrame({"compound_name": ["Alpha", "Beta", "Gamma"], "raw_paper_count": [5, 3, 2],
                      "effective_independent_count": [3, 2, 2]}).to_csv(os.path.join(self.root, ei.LIT), index=False)
        claims = [{"claim_id": "A1", "compound": "Alpha", "source_id": "PMID 11111111"},
                  {"claim_id": "A2", "compound": "Alpha", "source_id": "PMID 22222222"},
                  {"claim_id": "A3", "compound": "Alpha", "source_id": "PMID 33333333", "overlap_group": "g"},
                  {"claim_id": "A4", "compound": "Alpha", "source_id": "PMID 44444444", "overlap_group": "g"}]
        pathlib.Path(os.path.join(self.root, ei.CURATED)).write_text(json.dumps({"claims": claims}))
        pathlib.Path(os.path.join(self.root, "data/cache/pubmed_efetch_case_claims.xml")).write_bytes(XML)
        with open(os.path.join(self.root, ei.MOL_EVIDENCE), "w") as fh:
            fh.write(json.dumps({"drug": "Alpha", "disease_links": [{"datatype_scores_used": {"animal_model": 0.5},
                                 "datatype_scores_excluded_for_leakage": {"clinical": 0.9}}]}) + "\n")
            fh.write(json.dumps({"drug": "Beta", "disease_links": [{"datatype_scores_used": {"literature": 0.4}}]}) + "\n")
            fh.write("not json\n")

    def tearDown(self):
        shutil.rmtree(self.root)

    def write_provenance(self):
        """Stage-04p records for Gamma: one paper reporting Gamma's trial, plus a duplicate of another."""
        xml = ("<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>55</PMID><Article><Abstract><AbstractText>"
               "NCT00000003 results</AbstractText></Abstract></Article></MedlineCitation></PubmedArticle>"
               "<PubmedArticle><MedlineCitation><PMID>56</PMID><Article/></MedlineCitation></PubmedArticle>"
               "<PubmedArticle><MedlineCitation><PMID>57</PMID><Article/></MedlineCitation></PubmedArticle>"
               "</PubmedArticleSet>")
        os.makedirs(os.path.join(self.root, "data/cache/pubmed_lit"), exist_ok=True)
        with open(os.path.join(self.root, "data/cache/pubmed_lit/gamma.json"), "w") as fh:
            json.dump({"efetch_xml": [xml]}, fh)
        with open(os.path.join(self.root, ei.PROV_PAPERS), "w") as fh:
            for pm, grp, in_sample in (("55", "55", True), ("56", "56", True), ("57", "56", True), ("58", "58", False)):
                fh.write(json.dumps({"compound_name": "Gamma", "pmid": pm, "duplicate_group": grp,
                                     "in_stage04_sample": in_sample}) + "\n")

    def test_provenance_makes_d2_and_d5_assessable(self):
        before = {r["compound"]: r["checks"] for r in ei.run(self.root)["records"]}
        self.assertEqual(before["Gamma"]["D2_same_study_in_two_dimensions"]["state"], "NOT_ASSESSABLE")
        self.assertEqual(before["Gamma"]["D5_duplicate_publication_in_sample"]["state"], "NOT_ASSESSABLE")
        self.write_provenance()
        out = ei.run(self.root)
        ei.validate_output(out)
        g = {r["compound"]: r["checks"] for r in out["records"]}["Gamma"]
        d2 = g["D2_same_study_in_two_dimensions"]
        self.assertEqual(d2["state"], "DEPENDENCE_FOUND")
        self.assertEqual(d2["same_study"], [{"pmid": "55", "trial": "NCT00000003"}])
        self.assertEqual(d2["papers_checked"], 3)                       # only sample records, not 58
        d5 = g["D5_duplicate_publication_in_sample"]
        self.assertEqual((d5["state"], d5["duplicates"]), ("DEPENDENCE_FOUND", [{"pmid": "57", "duplicate_of": "56"}]))
        self.assertIn(ei.PROV_PAPERS, out["inputs"])

    def test_unreadable_provenance_cache_is_reported(self):
        self.write_provenance()
        with open(os.path.join(self.root, "data/cache/pubmed_lit/gamma.json"), "w") as fh:
            fh.write("{broken")
        out = ei.run(self.root)
        self.assertIn("CACHE_UNREADABLE", [d["code"] for d in out["diagnostics"]])
        self.assertEqual(out["run_status"], "PARTIAL")

    def test_checks(self):
        out = ei.run(self.root)
        self.assertTrue(ei.validate_output(out))
        b = {r["compound"]: r["checks"] for r in out["records"]}
        self.assertEqual(b["Alpha"]["D1_shared_trial_across_compounds"]["shared_trials"][0]["also_credited_to"], ["Beta"])
        self.assertEqual(b["Gamma"]["D1_shared_trial_across_compounds"]["state"], "NONE_FOUND")
        d2 = b["Alpha"]["D2_same_study_in_two_dimensions"]
        self.assertEqual(d2["state"], "DEPENDENCE_FOUND")              # paper reports the clinical-feature trial
        self.assertEqual({h["pmid"] for h in d2["same_study"]}, {"11111111", "22222222"})
        self.assertEqual(d2["papers_without_record"], ["33333333", "44444444"])
        d3 = b["Alpha"]["D3_duplicated_or_pooled_claims"]
        self.assertEqual(d3["independent_source_clusters"], 2)          # {A1,A2} by trial, {A3,A4} by overlap
        self.assertEqual(b["Gamma"]["D3_duplicated_or_pooled_claims"]["state"], "NOT_ASSESSABLE")
        self.assertEqual(b["Gamma"]["D2_same_study_in_two_dimensions"]["state"], "NOT_ASSESSABLE")
        self.assertEqual(b["Alpha"]["D4_molecular_datatype_reuse"]["state"], "NONE_FOUND")
        self.assertEqual(b["Beta"]["D4_molecular_datatype_reuse"]["reused"], ["literature"])
        self.assertEqual(b["Gamma"]["D4_molecular_datatype_reuse"]["state"], "NOT_ASSESSABLE")
        self.assertEqual(out["run_status"], "PARTIAL")                   # malformed line + missing Droxidopa XML
        codes = {d["code"] for d in out["diagnostics"]}
        self.assertTrue({"MALFORMED_LINE", "XML_MISSING"} <= codes)

    def test_no_score_allowed(self):
        out = ei.run(self.root)
        out["records"][0]["independence_score"] = 1
        with self.assertRaises(ValueError):
            ei.validate_output(out)


class TestPersisted(unittest.TestCase):
    def test_real_output(self):
        path = os.path.join(ROOT, ei.OUT)
        if not os.path.exists(path):
            self.skipTest("10g not run")
        out = json.loads(pathlib.Path(path).read_text())
        self.assertTrue(ei.validate_output(out))
        self.assertEqual(stale_inputs(ROOT, out["inputs"]), [])
        self.assertEqual(out["coverage"]["checks"]["D1_shared_trial_across_compounds"]["DEPENDENCE_FOUND"], 31)
        mel = {r["compound"]: r for r in out["records"]}["Melatonin"]["checks"]["D3_duplicated_or_pooled_claims"]
        self.assertEqual(mel["independent_source_clusters"], 1)      # two meta-analyses of one RCT pool



class TestMissingInputsAreNotFindings(TestFixture):
    """Sprint 2026-10-19 audit: empty or absent inputs read as 'checked, nothing found'."""

    def test_header_only_links_is_failed_not_none_found(self):
        with open(os.path.join(self.root, ei.LINKS), "w") as fh:
            fh.write("compound_name,nct_id,phase\n")
        out = ei.run(self.root)
        self.assertEqual(out["run_status"], "FAILED")
        self.assertIn("INPUT_EMPTY", [d["code"] for d in out["diagnostics"]])

    def test_absent_inputs_are_reported(self):
        for rel in (ei.LIT, ei.MOL_EVIDENCE):
            os.remove(os.path.join(self.root, rel))
        out = ei.run(self.root)
        missing = " ".join(d["message"] for d in out["diagnostics"] if d["code"] == "INPUT_MISSING")
        for rel in (ei.LIT, ei.MOL_EVIDENCE, ei.CLINICAL):
            self.assertIn(rel, missing)
        self.assertEqual(out["run_status"], "PARTIAL")

if __name__ == "__main__":
    unittest.main()
