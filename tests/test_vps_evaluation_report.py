"""
Tests for scripts/vps_evaluation_report.py. The unit tests are synthetic; the
persisted-report checks pin the reproducibility guarantees without re-running
the 20-repeat nested CV (about 30 s).
"""

import importlib.util
import json
import os
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("ver", os.path.join(ROOT, "scripts", "vps_evaluation_report.py"))
ver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ver)


class TestBootMetric(unittest.TestCase):
    def test_deterministic_and_counts_single_class_resamples(self):
        from sklearn.metrics import roc_auc_score
        y = np.array([1, 0, 0, 0, 0, 0, 0, 0])
        s = np.linspace(1, 0, 8)
        a = ver.boot_metric(y, s, roc_auc_score, n=200, seed=1)
        self.assertEqual(a, ver.boot_metric(y, s, roc_auc_score, n=200, seed=1))
        self.assertGreater(a[1], 0)                       # one positive in 8: many single-class resamples


class TestPersistedReport(unittest.TestCase):
    PATH = os.path.join(ROOT, ver.OUT)

    def setUp(self):
        if not os.path.exists(self.PATH):
            self.skipTest("report not generated")
        with open(self.PATH) as fh:
            self.r = json.load(fh)

    def test_reproduces_persisted_metrics_and_bootstrap(self):
        self.assertTrue(self.r["reproduction"]["all_match"])
        p = self.r["paired_5d_vs_4d"]
        self.assertTrue(p["rerun_identical"])
        self.assertTrue(p["matches_persisted_ci_file"])
        self.assertFalse(p["significant"])                # never claim 5d > 4d while the CI spans 0

    def test_report_is_current_for_its_inputs(self):
        import hashlib
        for rel, md5 in self.r["inputs"].items():
            with open(os.path.join(ROOT, rel), "rb") as fh:
                self.assertEqual(hashlib.md5(fh.read()).hexdigest(), md5, f"{rel} changed: re-run the report")

    def test_in_sample_and_held_out_are_separated(self):
        types = {row["column"]: row["type"] for row in self.r["reproduction"]["rows"]}
        self.assertTrue(types["VPS_grid_5d"].startswith("in-sample"))
        self.assertEqual(types["VPS_equal_5d"], "unfitted")
        self.assertEqual(self.r["grid_search"]["repeated_nested_cv"]["5d"]["repeats"], 20)

    def test_calibration_not_claimed_and_missingness_reported(self):
        self.assertFalse(self.r["calibration"]["applicable"])
        self.assertEqual(self.r["missing_data"]["not_measured_by_dimension"]["safety"], 7)
        self.assertEqual(self.r["cohort"]["duplicate_compounds"], 0)


if __name__ == "__main__":
    unittest.main()
