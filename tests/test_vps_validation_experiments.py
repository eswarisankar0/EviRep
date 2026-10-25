"""
Tests for scripts/vps_validation_experiments.py: the second-path VPS rebuild reproduces the
published scores, metric helpers are correct on hand-checked cases, nested CV selects weights from
training folds only, and the TD-042 variant changes nothing but the molecular dimension.
"""

import importlib.util
import os
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("vve", os.path.join(ROOT, "scripts", "vps_validation_experiments.py"))
vve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vve)


class TestMetrics(unittest.TestCase):
    def test_auroc_ties_and_perfect(self):
        y = np.array([1, 0, 1, 0])
        self.assertEqual(vve.auroc_cols(np.array([[4.], [3.], [2.], [1.]]), y)[0], 0.75)
        self.assertEqual(vve.auroc_cols(np.array([[1.], [1.], [1.], [1.]]), y)[0], 0.5)

    def test_precision_at_k_averages_boundary_ties(self):
        s = np.array([3., 2., 2., 1.])
        self.assertAlmostEqual(vve.p_at(s, np.array([0, 1, 0, 0]), k=2), 0.25)   # one of the two tied slots

    def test_simplex_weights_are_nonnegative_and_sum_to_one(self):
        W = vve.simplex(5, 0.1)
        self.assertEqual(len(W), 1001)
        self.assertTrue(np.all(W >= 0) and np.allclose(W.sum(1), 1))


class TestNestedCV(unittest.TestCase):
    def test_selection_ignores_test_fold_labels(self):
        from unittest import mock
        rng = np.random.default_rng(0)
        R = rng.random((48, 3))
        # Labels must not be aligned with the fixed folds: with np.tile([1,0,0,0]) and `% 4` folds every positive
        # sat in outer fold 0, every inner fold was single-class, and both runs silently fell back to W[0], so the
        # assertion below was vacuous (audit 2026-10-20, S-11). Positives every 3rd row give both classes everywhere.
        y = (np.arange(48) % 3 == 0).astype(int)
        fixed = lambda yy, k, r: np.arange(len(yy)) % k        # folds independent of the labels
        for f in range(4):                                      # every outer training set has both classes in each inner fold
            ytr = y[np.arange(48) % 4 != f]
            for g in range(3):
                self.assertEqual(len(set(ytr[np.arange(len(ytr)) % 3 == g])), 2)
        with mock.patch.object(vve, "stratified_folds", fixed):
            a = vve.nested_cv(R, y, 1, rng, outer_k=4, inner_k=3, step=0.5)
            y2 = y.copy()
            f0 = np.arange(48) % 4 == 0
            y2[f0] = 1 - y[f0]                                  # rewrite every label in outer fold 0
            b = vve.nested_cv(R, y2, 1, rng, outer_k=4, inner_k=3, step=0.5)
        self.assertEqual(a[0]["weights"], b[0]["weights"])      # fold 0's weights come from folds 1-3 only
        # while its test score is computed from the (flipped) test labels: flipping every label gives 1 - AUROC
        self.assertAlmostEqual(b[0]["auroc_fitted"], 1 - a[0]["auroc_fitted"], places=12)


class TestWeightingMatrix(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(3)
        self.R = rng.random((60, 3))
        self.y = np.tile([1, 0, 0, 0, 0, 0], 10)

    def test_weights_for_a_fold_ignore_that_folds_labels(self):
        from unittest import mock

        class Fixed:                                      # label-independent folds: row index mod k
            def __init__(self, k):
                self.k = k

            def split(self, X, y, groups=None):
                f = np.arange(len(X)) % self.k
                for i in range(self.k):
                    yield np.where(f != i)[0], np.where(f == i)[0]
        kinds = ["simplex", "shrink", "logit_l2"]
        with mock.patch.object(vve, "_splitter", lambda k, seed, grouped: Fixed(k)):
            _, wa, _ = vve.evaluate_fitted(self.R, self.y, kinds, 1, 0, step=0.25)
            y2 = self.y.copy()
            te0 = np.arange(60) % 5 == 0
            y2[te0] = 1 - y2[te0]                         # rewrite every label in outer fold 0
            _, wb, _ = vve.evaluate_fitted(self.R, y2, kinds, 1, 0, step=0.25)
        for k in kinds:
            self.assertTrue(np.allclose(wa[k][0], wb[k][0]), k)            # fold 0 fitted on folds 1-4 only
            self.assertFalse(all(np.allclose(a, b) for a, b in zip(wa[k][1:], wb[k][1:])), k)  # others did see it

    def test_equal_weight_model_is_the_mean_rank(self):
        fn, w = vve.fit_model("equal", self.R, self.y, None, 0, vve.simplex(3, 0.5))
        self.assertTrue(np.allclose(fn(self.R), self.R.mean(axis=1)))

    def test_grouped_outer_folds_keep_groups_together(self):
        groups = np.repeat(np.arange(20), 3)
        for tr, te in vve._splitter(5, 1, True).split(self.R, self.y, groups):
            self.assertFalse(set(groups[tr]) & set(groups[te]))


@unittest.skipUnless(os.path.exists(os.path.join(ROOT, "data", "vps_scores_v2.csv")), "published scores absent")
class TestOnPersistedArtefacts(unittest.TestCase):
    def test_baseline_reproduces_published_scores(self):
        import pandas as pd
        base = vve.build(ROOT)
        saved = pd.read_csv(os.path.join(ROOT, "data", "vps_scores_v2.csv")).set_index("compound_name").loc[base.index]
        for d in vve.DIMS5:
            self.assertLess((base[d] - saved[d]).abs().max(), 1e-12, d)
        self.assertTrue((base["label"] == saved["label"]).all())

    def test_trial_groups_join_compounds_that_share_a_feature_trial(self):
        import pandas as pd
        base = vve.build(ROOT)
        g = dict(zip(base.index, vve.trial_groups(ROOT, base.index)))
        links = pd.read_csv(os.path.join(ROOT, "data", "clinical_maturity_precutoff_clean.csv"))
        for _, comps in links[links["compound_name"].isin(base.index)].groupby("nct_id")["compound_name"]:
            self.assertEqual(len({g[c] for c in comps}), 1)

    def test_td042_variant_changes_only_the_molecular_dimension(self):
        base, var = vve.build(ROOT), vve.build(ROOT, molecular="td042_own_target")
        for d in ("r_proximity", "r_clinical", "r_literature", "r_safety", "label"):
            self.assertTrue((base[d] == var[d]).all(), d)
        changed = (base["molecular_raw"] - var["molecular_raw"]).abs() > 1e-6
        self.assertEqual(int(changed.sum()), 21)
        self.assertTrue((var["molecular_raw"][changed] < base["molecular_raw"][changed]).all())


if __name__ == "__main__":
    unittest.main()
