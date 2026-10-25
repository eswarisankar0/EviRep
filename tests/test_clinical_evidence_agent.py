"""
Tests for the Clinical Evidence Agent (10c), scripts/clinical_evidence_agent.py.
Synthetic registry records and fake HTTP; plus checks on the persisted output. Offline.
"""

import importlib.util
import json
import pathlib
import os
import shutil
import socket
import tempfile
import unittest

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("ce10c", os.path.join(ROOT, "scripts", "clinical_evidence_agent.py"))
ce = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ce)
_real_connect = socket.socket.connect


def setUpModule():
    def refuse(*a, **k):
        raise AssertionError("tests must not open network connections")
    socket.socket.connect = refuse


def tearDownModule():
    socket.socket.connect = _real_connect


def study(nct, status="COMPLETED", results=False, analyses=None, res_date="2015-01-01", arms=True, drug="Alpha"):
    s = {"protocolSection": {
        "identificationModule": {"nctId": nct, "briefTitle": f"{drug} in PD"},
        "statusModule": {"overallStatus": status, "resultsFirstPostDateStruct": {"date": res_date} if results else None},
        "designModule": {"phases": ["PHASE2"], "enrollmentInfo": {"count": 40, "type": "ACTUAL"},
                         "designInfo": {"primaryPurpose": "TREATMENT"}},
        "armsInterventionsModule": {
            "interventions": [{"type": "DRUG", "name": drug}, {"type": "DRUG", "name": "Placebo"}],
            "armGroups": [{"label": "A", "type": "EXPERIMENTAL", "interventionNames": [f"Drug: {drug}"]},
                          {"label": "P", "type": "PLACEBO_COMPARATOR", "interventionNames": ["Drug: Placebo"]}]} if arms else {}},
        "hasResults": results}
    if results:
        s["resultsSection"] = {"outcomeMeasuresModule": {"outcomeMeasures": [
            {"type": "PRIMARY", "title": "UPDRS III", "timeFrame": "12 weeks", "analyses": analyses or []},
            {"type": "SECONDARY", "title": "sleep", "analyses": [{"pValue": "0.01"}]}]}}
    return s


class FakeResp:
    def __init__(self, status, body=None):
        self.status_code, self._b = status, body

    def json(self):
        return self._b


class TestNormalise(unittest.TestCase):
    def test_results_copied_verbatim_primary_only(self):
        t = ce.normalise_study(study("NCT00000001", results=True,
                                     analyses=[{"pValue": "0.32", "statisticalMethod": "ANCOVA", "paramType": "Mean Difference",
                                                "paramValue": "-1.2", "ciLowerLimit": "-3.5", "ciUpperLimit": "1.1"}]))
        r = t["results"]
        self.assertEqual(r["state"], "RESULTS_POSTED")
        self.assertEqual(r["n_primary_analyses"], 1)                      # secondary analysis not counted
        self.assertEqual(r["primary_analyses"][0]["p_value"], "0.32")       # string as posted, not reinterpreted
        self.assertEqual(r["temporal"], "PRE_CUTOFF")

    def test_post_cutoff_results_flagged_and_no_analysis_noted(self):
        r = ce.normalise_study(study("NCT00000002", results=True, res_date="2022-03-01"))["results"]
        self.assertEqual(r["temporal"], "POST_CUTOFF")
        self.assertEqual((r["n_primary_analyses"], r["n_primary_outcomes_without_analysis"]), (0, 1))

    def test_no_results_is_not_negative(self):
        r = ce.normalise_study(study("NCT00000003", status="TERMINATED"))
        self.assertEqual(r["results"]["state"], "NO_RESULTS_POSTED")
        self.assertIn("not a negative finding", r["results"]["detail"])
        self.assertEqual(r["status_class"], "stopped")


class TestFetch(unittest.TestCase):
    def test_failed_batches_are_recorded(self):
        calls = []

        def get(url, params=None, timeout=None):
            calls.append(params)
            if len(calls) == 1:
                return FakeResp(200, {"studies": [study("NCT00000001")]})
            raise TimeoutError("slow")
        ids = [f"NCT{i:08d}" for i in range(1, 25)]                       # 2 batches of <=20
        out = ce.fetch_registry(ids, get=get)
        self.assertEqual([b["ok"] for b in out["batches"]], [True, False])
        self.assertEqual(out["batches"][1]["error_class"], "TimeoutError")


class TestRun(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "data", "cache"))
        pd.DataFrame({"compound_name": ["Alpha", "Alpha", "Beta"], "nct_id": ["NCT00000001", "NCT00000009", "NCT00000030"],
                      "phase": ["PHASE2", "PHASE3", None], "matched_alias": ["Alpha", "Alpha", "Beta"],
                      "matched_intervention": ["Alpha", "Alpha", "Beta"]}).to_csv(os.path.join(self.root, ce.LINKS), index=False)
        pd.DataFrame({"compound_name": ["Alpha", "Alpha", "Beta"], "outcome": ["MATCHED", "UNVERIFIABLE", "MATCHED"]}).to_csv(
            os.path.join(self.root, ce.AUDIT), index=False)

    def tearDown(self):
        shutil.rmtree(self.root)

    def _cache(self, studies, batches):
        with open(os.path.join(self.root, ce.CACHE), "w") as fh:
            json.dump({"retrieved_utc": "t", "studies": studies, "batches": batches}, fh)

    def test_missing_failed_and_retrieved_are_distinct(self):
        self._cache([study("NCT00000001", results=True)],
                    [{"ids": ["NCT00000001", "NCT00000009"], "ok": True}, {"ids": ["NCT00000030"], "ok": False, "http_status": 503}])
        out = ce.run(self.root)
        self.assertTrue(ce.validate_output(out))
        st = {k: v["results"]["state"] for k, v in out["trials"].items()}
        self.assertEqual(st, {"NCT00000001": "RESULTS_POSTED", "NCT00000009": "NOT_IN_REGISTRY", "NCT00000030": "RETRIEVAL_FAILED"})
        self.assertEqual(out["run_status"], "PARTIAL")
        a = {c["compound"]: c for c in out["compounds"]}["Alpha"]
        self.assertEqual(a["matching_audit_outcomes"], {"MATCHED": 1, "UNVERIFIABLE": 1})
        self.assertEqual(a["links"][0]["role_auto"], "THERAPEUTIC_TEST")
        self.assertEqual(a["links"][1]["role_auto"], "UNDETERMINED")      # no record -> no verdict invented

    def test_no_cache_is_failed_not_empty_success(self):
        out = ce.run(self.root)
        self.assertEqual(out["run_status"], "FAILED")
        self.assertTrue(all(t["results"]["state"] == "NOT_RETRIEVED" for t in out["trials"].values()))

    def test_background_othername_alias_not_counted_as_test(self):
        s = study("NCT00000001", drug="Safinamide")
        s["protocolSection"]["armsInterventionsModule"]["interventions"].append(
            {"type": "DRUG", "name": "Dopamine agonist", "otherNames": ["Alpha"]})
        self._cache([s], [{"ids": ["NCT00000001"], "ok": True}])
        out = ce.run(self.root)
        a = {c["compound"]: c for c in out["compounds"]}["Alpha"]
        self.assertEqual(a["links"][0]["role_auto"], "BACKGROUND_OTHERNAME")


class TestAuditRegressions(TestRun):
    """Sprint 2026-10-19 audit of 10c."""

    def test_results_without_a_posting_date_are_not_pre_cutoff(self):
        s = study("NCT00000001", results=True)
        s["protocolSection"]["statusModule"]["resultsFirstPostDateStruct"] = None
        self.assertEqual(ce.normalise_study(s)["results"]["temporal"], "UNKNOWN")

    def test_link_absent_from_an_older_cache_is_not_retrieved_not_a_registry_miss(self):
        self._cache([study("NCT00000001"), study("NCT00000009")],
                    [{"ids": ["NCT00000001", "NCT00000009"], "ok": True}])        # NCT00000030 never requested
        out = ce.run(self.root)
        self.assertEqual(out["trials"]["NCT00000030"]["results"]["state"], "NOT_RETRIEVED")
        self.assertEqual(out["run_status"], "PARTIAL")
        self.assertIn("CACHE_STALE", [d["code"] for d in out["diagnostics"]])

    def test_status_counts_keep_trials_without_a_record(self):
        self._cache([study("NCT00000001")], [{"ids": ["NCT00000001"], "ok": True},
                                             {"ids": ["NCT00000009", "NCT00000030"], "ok": False, "http_status": 503}])
        c = {c["compound"]: c for c in ce.run(self.root)["compounds"]}
        self.assertEqual(sum(c["Alpha"]["status_counts"].values()), c["Alpha"]["n_trials"])
        self.assertEqual(c["Beta"]["status_counts"]["no_registry_record"], 1)

    def test_all_batches_failed_writes_failed_output(self):
        self._cache([], [{"ids": ["NCT00000001", "NCT00000009", "NCT00000030"], "ok": False, "http_status": 503}])
        out = ce.run(self.root)
        self.assertEqual(out["run_status"], "FAILED")
        self.assertTrue(ce.validate_output(out))

    def test_failed_fetch_keeps_the_previous_cache(self):
        self._cache([study("NCT00000001")], [{"ids": ["NCT00000001"], "ok": True}])
        before = pathlib.Path(os.path.join(self.root, ce.CACHE)).read_text()
        def down(*a, **k):
            raise ConnectionError("down")
        rc = ce.main(["--root", self.root, "--fetch"], get=down)
        self.assertEqual(rc, 1)
        self.assertEqual(pathlib.Path(os.path.join(self.root, ce.CACHE)).read_text(), before)


class TestChemblAlias(unittest.TestCase):
    """2026-10-19: the registry may name the compound by its ChEMBL preferred name (Rifampin for Rifampicin)."""

    def test_aliases_add_the_chembl_name_but_never_the_matched_intervention(self):
        self.assertEqual(ce.compound_aliases("Rifampicin", "rifampicin", {"Rifampicin": "RIFAMPIN"}),
                         ["Rifampicin", "rifampicin", "RIFAMPIN"])
        self.assertEqual(ce.compound_aliases("Alpha", None, {}), ["Alpha"])

    def test_chembl_names_only_from_exact_resolutions(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "data"))
            with open(os.path.join(tmp, ce.MOL_EVIDENCE), "w") as fh:
                for drug, pref, mt in (("Rifampicin", "RIFAMPIN", "exact_synonym"), ("Alpha", "ALPHA", "exact_name"),
                                       ("Beta", "GAMMA", "unresolved")):
                    fh.write(json.dumps({"drug": drug, "drug_normalized": pref, "normalization": {"match_type": mt}}) + "\n")
            self.assertEqual(ce.chembl_names(tmp), {"Rifampicin": "RIFAMPIN"})
        finally:
            shutil.rmtree(tmp)

    def test_registry_name_matches_through_the_chembl_alias(self):
        s = study("NCT00000001", drug="Rifampin")
        self.assertEqual(ce.classify_trial_role(s, ["Rifampicin"])["verdict"], "NOT_NAMED")
        self.assertEqual(ce.classify_trial_role(s, ce.compound_aliases("Rifampicin", None, {"Rifampicin": "RIFAMPIN"}))["verdict"],
                         "THERAPEUTIC_TEST")


class TestPersisted(unittest.TestCase):
    def test_real_output_valid_current_and_lisuride_background(self):
        path = os.path.join(ROOT, ce.OUT)
        if not os.path.exists(path):
            self.skipTest("10c not run")
        out = json.loads(pathlib.Path(path).read_text())
        self.assertTrue(ce.validate_output(out))
        sys_path = os.path.join(ROOT, "scripts")
        import sys
        sys.path.insert(0, sys_path)
        from agent_contract import stale_inputs
        self.assertEqual(stale_inputs(ROOT, out["inputs"]), [])
        lis = {c["compound"]: c for c in out["compounds"]}["Lisuride"]
        self.assertEqual({l["nct_id"]: l["role_auto"] for l in lis["links"]}["NCT00605683"], "BACKGROUND_OTHERNAME")


if __name__ == "__main__":
    unittest.main()
