"""Stage 03 must never publish features or labels built while ClinicalTrials.gov searches failed, and must stop
quickly when the registry is unreachable (2026-10-19: an outage meant ~6 h of retries, then exit 0 with the
failed compounds silently missing from the pool)."""

import importlib.util
import os
import tempfile
import unittest
from unittest import mock

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("st03", os.path.join(ROOT, "scripts", "03_clinicaltrials_groundtruth.py"))
st03 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(st03)


class Stage03Failures(unittest.TestCase):
    def run_main(self, n, search, **kw):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "data"))
            pd.DataFrame({"compound_id": [f"C{i}" for i in range(n)], "compound_name": [f"Drug{i}" for i in range(n)]}).to_csv(
                os.path.join(tmp, "data/pd_candidates_filtered.csv"), index=False)
            calls = []

            def counted(drug, *a, **k):
                calls.append(drug)
                return search(drug)
            try:
                os.chdir(tmp)
                with mock.patch.object(st03, "build_alias_map", lambda c: ({}, {"resolved": 0, "total": len(c), "source": "stub"})), \
                     mock.patch.object(st03, "search_trials", counted), mock.patch.object(st03.time, "sleep", lambda s: None), \
                     mock.patch("builtins.print"), self.assertRaises(SystemExit) as cm:
                    st03.main(**kw)
                written = [f for f in ("clinical_maturity_precutoff.csv", "ground_truth_postcutoff.csv")
                           if os.path.exists(os.path.join(tmp, "data", f))]
            finally:
                os.chdir(cwd)
        return cm.exception, calls, written

    def test_unreachable_registry_aborts_after_a_few_failures_and_writes_nothing(self):
        exc, calls, written = self.run_main(200, lambda d: ([], False))
        self.assertEqual(len(calls), st03.MAX_CONSECUTIVE_FAILURES)
        self.assertIn("unreachable", str(exc.code))
        self.assertEqual(written, [])

    def test_any_failed_search_blocks_publication(self):
        exc, calls, written = self.run_main(5, lambda d: ([], d != "Drug2"))      # one isolated failure
        self.assertEqual(len(calls), 5)
        self.assertIn("Drug2", str(exc.code))
        self.assertEqual(written, [])


    def test_explicit_opt_in_publishes_with_failures_recorded(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "data"))
            pd.DataFrame({"compound_id": ["C0", "C1"], "compound_name": ["Drug0", "Drug1"]}).to_csv(
                os.path.join(tmp, "data/pd_candidates_filtered.csv"), index=False)
            try:
                os.chdir(tmp)
                with mock.patch.object(st03, "build_alias_map", lambda c: ({}, {"resolved": 0, "total": 2, "source": "stub"})), \
                     mock.patch.object(st03, "search_trials", lambda d: ([], d != "Drug1")), \
                     mock.patch.object(st03.time, "sleep", lambda s: None), mock.patch("builtins.print"):
                    st03.main(accept_failed_searches=True)
                audit = pd.read_csv(os.path.join(tmp, st03.AUDIT_FILE))
            finally:
                os.chdir(cwd)
        self.assertEqual(list(audit.loc[audit["compound_name"] == "Drug1", "outcome"]), [st03.im.API_FAILURE])


if __name__ == "__main__":
    unittest.main()


class Stage03cFailures(unittest.TestCase):
    """2026-10-19: a failed study-type lookup was stored as 'ERROR' and the filter then dropped the trial."""

    def setUp(self):
        spec = importlib.util.spec_from_file_location("cst", os.path.join(ROOT, "scripts", "check_studytype.py"))
        self.cst = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cst)
        self.cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.tmp, "data"))
        for f, ids in (("clinical_maturity_precutoff.csv", ["NCT1", "NCT2"]), ("ground_truth_postcutoff.csv", ["NCT3"])):
            pd.DataFrame({"compound_id": ["C"] * len(ids), "nct_id": ids}).to_csv(os.path.join(self.tmp, "data", f), index=False)
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.cwd)
        import shutil
        shutil.rmtree(self.tmp)

    def run_with(self, info):
        with mock.patch.object(self.cst, "get_study_info", info), mock.patch.object(self.cst.time, "sleep", lambda s: None), \
             mock.patch("builtins.print"):
            self.cst.main()

    def test_any_failed_lookup_writes_nothing(self):
        with self.assertRaises(SystemExit):
            self.run_with(lambda n: ("ERROR", ["ConnectionError"]) if n == "NCT2" else ("INTERVENTIONAL", ["DRUG"]))
        self.assertEqual(sorted(os.listdir("data")), ["clinical_maturity_precutoff.csv", "ground_truth_postcutoff.csv"])

    def test_success_also_produces_the_clean_files(self):
        self.run_with(lambda n: ("INTERVENTIONAL", ["DRUG"]) if n != "NCT2" else ("OBSERVATIONAL", ["OTHER"]))
        pre = pd.read_csv("data/clinical_maturity_precutoff_clean.csv")
        self.assertEqual(list(pre["nct_id"]), ["NCT1"])
        self.assertTrue(os.path.exists("data/ground_truth_postcutoff_clean.csv"))

    def test_filter_refuses_a_check_file_with_errors(self):
        pd.DataFrame({"nct_id": ["NCT1"], "study_type": ["ERROR"], "intervention_types": ["x"]}).to_csv(
            "data/nct_studytype_check.csv", index=False)
        import runpy
        with self.assertRaises(SystemExit), mock.patch("builtins.print"):
            runpy.run_path(os.path.join(ROOT, "scripts", "filter_by_studytype.py"))
        self.assertFalse(os.path.exists("data/clinical_maturity_precutoff_clean.csv"))
