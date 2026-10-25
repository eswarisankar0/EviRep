"""Tests for scripts/bootstrap_auroc_ci.py (E-015). Offline, synthetic data only."""

import importlib.util
import os
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("bootstrap_auroc_ci",
                                               os.path.join(ROOT, "scripts", "bootstrap_auroc_ci.py"))
boot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(boot)


def _data(n=60, seed=0):
    rng = np.random.default_rng(seed)
    y = np.r_[np.ones(n // 4, int), np.zeros(n - n // 4, int)]
    a = y * 0.6 + rng.random(n)
    b = y * 0.3 + rng.random(n)
    return y, a, b


class TestPairedBootstrap(unittest.TestCase):
    def test_same_seed_same_result(self):
        y, a, b = _data()
        self.assertEqual(boot.paired_bootstrap(y, a, b, 300, seed=7), boot.paired_bootstrap(y, a, b, 300, seed=7))

    def test_different_seed_changes_ci_not_point_estimate(self):
        y, a, b = _data()
        r1, r2 = boot.paired_bootstrap(y, a, b, 300, seed=1), boot.paired_bootstrap(y, a, b, 300, seed=2)
        self.assertEqual(r1["diff"], r2["diff"])
        self.assertNotEqual(r1["ci_diff"], r2["ci_diff"])

    def test_identical_scores_give_zero_width_paired_difference(self):
        y, a, _ = _data()
        r = boot.paired_bootstrap(y, a, a.copy(), 200)
        self.assertEqual(r["ci_diff"], (0.0, 0.0))
        self.assertEqual(r["diff"], 0.0)

    def test_point_estimate_inside_ci(self):
        y, a, b = _data()
        r = boot.paired_bootstrap(y, a, b, 500)
        self.assertLessEqual(r["ci_diff"][0], r["diff"])
        self.assertGreaterEqual(r["ci_diff"][1], r["diff"])

    def test_single_class_resamples_are_counted(self):
        y = np.array([1, 0, 0, 0, 0, 0])
        s = np.arange(6.0)
        r = boot.paired_bootstrap(y, s, s[::-1].copy(), 400, seed=3)
        self.assertGreater(r["n_skipped"], 0)
        self.assertEqual(r["n_used"] + r["n_skipped"], 400)

    def test_rejects_nan_and_one_class_and_length_mismatch(self):
        y, a, b = _data()
        a[0] = np.nan
        with self.assertRaises(ValueError):
            boot.paired_bootstrap(y, a, b, 10)
        with self.assertRaises(ValueError):
            boot.paired_bootstrap(np.zeros(5, int), np.arange(5.0), np.arange(5.0), 10)
        with self.assertRaises(ValueError):
            boot.paired_bootstrap(y[:-1], b, b, 10)

    def test_records_procedure_parameters(self):
        y, a, b = _data()
        r = boot.paired_bootstrap(y, a, b, 50, seed=11, alpha=0.1)
        for k, v in {"n_boot": 50, "seed": 11, "alpha": 0.1, "rng": "numpy.random.default_rng",
                     "interval": "percentile"}.items():
            self.assertEqual(r[k], v)


if __name__ == "__main__":
    unittest.main()
