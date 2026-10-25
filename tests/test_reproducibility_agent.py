"""
Offline tests for scripts/reproducibility_agent.py (architecture 10e).

Synthetic PubMed XML (PMIDs 9100000x are not real) covers independent studies,
duplicate records, shared trials, shared authors, documented overlap, missing
metadata, malformed input and determinism; persisted-output checks pin the
real findings. A socket guard proves the CLI makes no network connection.
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
_spec = importlib.util.spec_from_file_location("rep", os.path.join(ROOT, "scripts", "reproducibility_agent.py"))
rep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rep)


def art(pmid, authors=(), pts=("Randomized Controlled Trial",), year="2015", abstract="", banks=()):
    au = ("<AuthorList>" + "".join(f"<Author><LastName>{a.split()[0]}</LastName><Initials>{a.split()[1]}</Initials></Author>"
                                   for a in authors) + "</AuthorList>") if authors else ""
    pt = "".join(f"<PublicationType>{p}</PublicationType>" for p in pts)
    db = ("<DataBankList><DataBank><DataBankName>ClinicalTrials.gov</DataBankName><AccessionNumberList>"
          + "".join(f"<AccessionNumber>{b}</AccessionNumber>" for b in banks)
          + "</AccessionNumberList></DataBank></DataBankList>") if banks else ""
    return (f"<PubmedArticle><MedlineCitation><PMID>{pmid}</PMID><Article><Journal><JournalIssue><PubDate>"
            f"<Year>{year}</Year></PubDate></JournalIssue></Journal><ArticleTitle>T</ArticleTitle>"
            f"<Abstract><AbstractText>{abstract}</AbstractText></Abstract>{au}"
            f"<PublicationTypeList>{pt}</PublicationTypeList>{db}</Article></MedlineCitation></PubmedArticle>")


XML = ("<PubmedArticleSet>"
       + art("91000001", ["Smith A", "Jones B"])
       + art("91000002", ["Lee C", "Kim D"])
       + art("91000003", ["Smith A", "Park E"])                         # shares an author with 1
       + art("91000004", ["Wu F"], abstract="Registered as NCT01234567.")
       + art("91000005", ["Ng G"], banks=["NCT01234567"])               # same trial as 4
       + art("91000006", [])                                            # no author list
       + art("91000007", ["Roe H"], pts=("Meta-Analysis", "Systematic Review"))
       + "</PubmedArticleSet>").encode()


def recs():
    return rep.parse_records(XML, "fixture")


def claim(cid, pmid, direction="SUPPORTS", **kw):
    return dict({"claim_id": cid, "compound": "DrugX", "source_id": f"PMID {pmid}", "direction": direction,
                 "domain": "efficacy", "endpoint_domain": "tremor"}, **kw)


class TestParsing(unittest.TestCase):
    def test_fields(self):
        r = recs()
        self.assertEqual(r["91000001"]["authors"], ["jones b", "smith a"])
        self.assertEqual(r["91000004"]["trial_ids"], ["NCT01234567"])     # from abstract text
        self.assertEqual(r["91000005"]["trial_ids"], ["NCT01234567"])     # from DataBank
        self.assertEqual(r["91000006"]["authors"], [])
        self.assertEqual(r["91000007"]["design"], "META_ANALYSIS")
        self.assertEqual(r["91000001"]["design"], "RCT")

    def test_malformed_xml_raises(self):
        with self.assertRaises(Exception):
            rep.parse_records(b"<PubmedArticleSet><PubmedArticle>", "x")


class TestRelationships(unittest.TestCase):
    def setUp(self):
        self.r = recs()

    def test_rules(self):
        r = self.r
        self.assertEqual(rep.relate(r["91000001"], r["91000001"])["relation"], "SAME_RECORD")
        self.assertEqual(rep.relate(r["91000004"], r["91000005"])["relation"], "SHARED_TRIAL")
        self.assertEqual(rep.relate(r["91000001"], r["91000003"])["relation"], "SHARED_AUTHORS")
        self.assertEqual(rep.relate(r["91000001"], r["91000006"])["independence"], "UNDETERMINED")
        x = rep.relate(r["91000001"], r["91000002"])
        self.assertEqual((x["relation"], x["independence"]), ("NO_SHARED_INDICATOR", "PLAUSIBLY_INDEPENDENT"))
        a, b = dict(r["91000001"], overlap_group="g"), dict(r["91000002"], overlap_group="g")
        self.assertEqual(rep.relate(a, b)["relation"], "DOCUMENTED_SHARED_DATA")

    def test_citation_is_recorded_but_not_a_dependency(self):
        x = rep.relate(self.r["91000001"], self.r["91000002"], frozenset({("91000001", "91000002")}))
        self.assertTrue(x["cites"])
        self.assertEqual(x["independence"], "PLAUSIBLY_INDEPENDENT")

    def test_different_pmids_alone_never_mean_independent(self):
        # missing authors on one side -> UNDETERMINED, even though PMIDs differ
        self.assertEqual(rep.relate(self.r["91000002"], self.r["91000006"])["independence"], "UNDETERMINED")

    def test_clusters(self):
        r = self.r
        rels = [rep.relate(r["91000001"], r["91000003"]), rep.relate(r["91000004"], r["91000005"])]
        cl = rep.clusters([r[p] for p in ("91000001", "91000003", "91000004", "91000005", "91000002")], rels)
        self.assertEqual(cl, [["91000001", "91000003"], ["91000002"], ["91000004", "91000005"]])


class TestFindings(unittest.TestCase):
    def setUp(self):
        self.r = recs()

    def status(self, claims):
        return rep.assess_finding("DrugX", "efficacy:tremor", claims, self.r)

    def test_two_independent_studies_replicate_with_plausible_independence(self):
        f = self.status([claim("a", "91000001"), claim("b", "91000002")])
        self.assertEqual((f["status"], f["cluster_independence"]), ("REPLICATED", "PLAUSIBLY_INDEPENDENT"))

    def test_two_papers_of_one_trial_are_a_single_study(self):
        f = self.status([claim("a", "91000004"), claim("b", "91000005")])
        self.assertEqual(f["status"], "SINGLE_STUDY")
        self.assertEqual(f["n_independent_primary_clusters"], 1)

    def test_same_group_is_not_replication(self):
        self.assertEqual(self.status([claim("a", "91000001"), claim("b", "91000003")])["status"], "SINGLE_STUDY")

    def test_duplicate_claims_on_one_record(self):
        self.assertEqual(self.status([claim("a", "91000001"), claim("b", "91000001")])["status"], "SINGLE_STUDY")

    def test_meta_analysis_is_not_a_replicate(self):
        self.assertEqual(self.status([claim("a", "91000007")])["status"], "SECONDARY_ONLY")
        f = self.status([claim("a", "91000001"), claim("b", "91000007")])
        self.assertEqual((f["status"], f["n_secondary"]), ("SINGLE_STUDY", 1))

    def test_missing_metadata_is_undetermined(self):
        self.assertEqual(self.status([claim("a", "91000001"), claim("b", "91000006")])["status"], "UNDETERMINED")
        f = self.status([claim("a", "99999999")])
        self.assertEqual((f["status"], f["missing_records"]), ("INSUFFICIENT_METADATA", ["PMID 99999999"]))

    def test_disagreement_between_independent_studies(self):
        f = self.status([claim("a", "91000001"), claim("b", "91000002", "NULL_RESULT")])
        self.assertEqual(f["status"], "INCONSISTENT_SINGLE_STUDIES")
        f = self.status([claim("a", "91000001"), claim("b", "91000002"), claim("c", "91000004", "NULL_RESULT")])
        self.assertEqual(f["status"], "REPLICATED_WITH_DISAGREEMENT")

    def test_curated_design_fills_unknown_publication_type(self):
        r = dict(self.r, **{"91000008": dict(self.r["91000002"], pmid="91000008", design="UNKNOWN",
                                             authors=["zed z"])})
        f = rep.assess_finding("DrugX", "k", [claim("a", "91000008", design="rct")], r)
        self.assertEqual(f["records"][0]["design_source"], "curated claim (docs/CASE_STUDIES.md)")


class TestAuditRegressions(unittest.TestCase):
    """Sprint 2026-10-19 audit of 10e."""

    def setUp(self):
        self.r = recs()

    def test_disagreement_inside_one_group_is_not_independent(self):
        f = rep.assess_finding("DrugX", "efficacy:tremor",
                               [claim("a", "91000001", "SUPPORTS"), claim("b", "91000003", "OPPOSES")], self.r)
        self.assertEqual(f["n_independent_primary_clusters"], 1)            # shared author
        self.assertEqual(f["status"], "INCONSISTENT_WITHIN_GROUP")

    def test_all_directions_of_a_repeated_pmid_are_kept(self):
        f = rep.assess_finding("DrugX", "efficacy:tremor",
                               [claim("a", "91000002", "SUPPORTS"), claim("b", "91000002", "OPPOSES")], self.r)
        self.assertEqual(set(f["directions_by_cluster"]), {"SUPPORTS", "OPPOSES"})

    def test_missing_records_are_flagged_on_the_finding_and_the_run(self):
        f = rep.assess_finding("DrugX", "efficacy:tremor", [claim("a", "91000001"), claim("b", "91000002"),
                                                            claim("c", "999", "OPPOSES")], self.r)
        self.assertEqual(f["status"], "REPLICATED")
        self.assertIn("1 source record", f["status_caveat"])
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "data", "cache"))
            with open(os.path.join(tmp, rep.XML_FILES[0]), "wb") as fh:
                fh.write(XML)
            with open(os.path.join(tmp, rep.CURATED), "w") as fh:
                json.dump({"claims": [claim("a", "91000001"), claim("b", "91000002"), claim("c", "999", "OPPOSES"),
                                      dict(claim("d", "1"), source_id="PMID:3619710")]}, fh)
            out = rep.run(tmp)
            codes = [d["code"] for d in out["diagnostics"]]
            self.assertIn("MISSING_SOURCE_RECORDS", codes)
            self.assertIn("CLAIMS_SKIPPED", codes)
            self.assertIn("INPUT_MISSING", codes)                           # trial files absent
            self.assertEqual(out["run_status"], "PARTIAL")
        finally:
            shutil.rmtree(tmp)


class TestRunOffline(unittest.TestCase):
    def test_run_is_offline_deterministic_and_valid(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "data", "cache"))
            with open(os.path.join(tmp, rep.XML_FILES[0]), "wb") as fh:
                fh.write(XML)
            with open(os.path.join(tmp, rep.CURATED), "w") as fh:
                json.dump({"claims": [claim("a", "91000001"), claim("b", "91000002"), {"claim_id": "bad"}]}, fh)
            with open(os.path.join(tmp, "data", "literature_graph_drugx.json"), "w") as fh:
                json.dump({"compound": "DrugX", "nodes": [{"pmid": "91000001", "component": 0},
                                                          {"pmid": "91000003", "component": 0},
                                                          {"pmid": "99999999", "component": 1}],
                           "edges": [{"source": "91000001", "target": "91000003", "reason": "shared_author"}]}, fh)

            def no_net(*a, **k):
                raise AssertionError("network used")
            with mock.patch.object(socket.socket, "connect", no_net), mock.patch("builtins.print"):
                rep.main(["--root", tmp])
                first = pathlib.Path(os.path.join(tmp, rep.OUT)).read_text()
                rep.main(["--root", tmp])
            self.assertEqual(first, pathlib.Path(os.path.join(tmp, rep.OUT)).read_text())
            out = json.loads(first)
            rep.validate_output(out)
            self.assertEqual(out["finding_status_counts"], {"REPLICATED": 1})
            s = out["publication_structures"][0]
            self.assertEqual(s["missing_metadata"], ["99999999"])
            self.assertEqual(s["n_independent_primary_clusters"], 1)          # 1 and 3 share an author
            self.assertEqual(out["shared_trials_across_compounds"]["status"], "trial files missing")
        finally:
            shutil.rmtree(tmp)

    def test_validate_rejects_score(self):
        out = {"schema_version": rep.REPRODUCIBILITY_SCHEMA_VERSION, "finding_status_meaning": {"SINGLE_STUDY": ""},
               "independence_scale": {}, "findings": [{"status": "SINGLE_STUDY", "relationships": [], "score": 1}]}
        with self.assertRaises(ValueError):
            rep.validate_output(out)


class TestPersistedOutput(unittest.TestCase):
    PATH = os.path.join(ROOT, "data", "reproducibility.json")

    def setUp(self):
        if not os.path.exists(self.PATH):
            self.skipTest("data/reproducibility.json not generated")
        with open(self.PATH) as fh:
            self.out = json.load(fh)
        self.f = {(x["compound"], x["finding"]): x for x in self.out["findings"]}

    def test_known_findings(self):
        rep.validate_output(self.out)
        trem = self.f[("Propranolol", "efficacy:tremor")]
        self.assertEqual((trem["status"], trem["cluster_independence"]), ("REPLICATED", "PLAUSIBLY_INDEPENDENT"))
        mel = self.f[("Melatonin", "efficacy:daytime_sleepiness")]
        self.assertEqual(mel["status"], "SECONDARY_ONLY")
        self.assertEqual(mel["relationships"][0]["relation"], "DOCUMENTED_SHARED_DATA")
        drox = self.out["publication_structures"][0]
        self.assertEqual((drox["compound"], drox["n_papers_in_graph"], drox["n_with_metadata"]), ("Droxidopa", 26, 26))
        self.assertNotIn("reproducibility", pathlib.Path(os.path.join(ROOT, "scripts", "06_vps_fusion.py")).read_text())

    def test_inputs_are_checksummed(self):
        self.assertTrue(all(len(i["md5"]) == 32 for i in self.out["input_files"]))
        self.assertTrue(all(len(h) == 32 for h in self.out["inputs"].values()))   # shared envelope (agent_contract)


if __name__ == "__main__":
    unittest.main()
