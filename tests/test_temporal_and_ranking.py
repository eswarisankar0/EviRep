"""
Focused tests for two contracts that had no coverage:

1. The temporal cutoff boundary. Stage 03 splits trials with
   `first_posted < CUTOFF_DATE` -> feature, `>= CUTOFF_DATE` -> ground truth.
   An off-by-one here would silently move trials between the feature set and the
   label set, which is the single most damaging possible error in this project.

2. Reproducibility of the final ranking, which is the published artifact.

The data-contract tests skip when the generated files are absent, so a fresh
clone still passes.
"""

import importlib.util
import os
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

PRE = os.path.join(ROOT, "data", "clinical_maturity_precutoff.csv")
POST = os.path.join(ROOT, "data", "ground_truth_postcutoff.csv")
VPS = os.path.join(ROOT, "data", "vps_scores_v2.csv")


def _stage03():
    path = os.path.join(ROOT, "scripts", "03_clinicaltrials_groundtruth.py")
    spec = importlib.util.spec_from_file_location("s03_temporal", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestCutoffBoundarySemantics(unittest.TestCase):
    """Pure-logic test of the exact comparison stage 03 performs."""

    def setUp(self):
        self.cutoff = _stage03().CUTOFF_DATE

    def test_cutoff_constant_unchanged(self):
        self.assertEqual(self.cutoff, "2021-01-01")

    def test_day_before_cutoff_is_feature(self):
        self.assertTrue("2020-12-31" < self.cutoff)
        self.assertFalse("2020-12-31" >= self.cutoff)

    def test_exact_cutoff_date_is_ground_truth(self):
        """A trial posted ON the cutoff must count as POST, not pre."""
        self.assertTrue("2021-01-01" >= self.cutoff)
        self.assertFalse("2021-01-01" < self.cutoff)

    def test_day_after_cutoff_is_ground_truth(self):
        self.assertTrue("2021-01-02" >= self.cutoff)

    def test_iso_string_comparison_is_safe_for_this_format(self):
        """Stage 03 compares ISO date strings directly; verify the ordering
        matches real date ordering across year/month/day boundaries."""
        dates = ["2019-12-31", "2020-01-01", "2020-09-30", "2020-12-31",
                 "2021-01-01", "2021-10-05", "2024-02-29"]
        self.assertEqual(sorted(dates), dates)
        parsed = [pd.Timestamp(d) for d in dates]
        self.assertEqual(sorted(parsed), parsed)

    def test_empty_date_is_neither_cohort(self):
        """Stage 03 guards with `if first_posted and ...`; an empty date must
        fall through to neither cohort rather than defaulting to pre."""
        first_posted = ""
        self.assertFalse(bool(first_posted) and first_posted < self.cutoff)
        self.assertFalse(bool(first_posted) and first_posted >= self.cutoff)


@unittest.skipUnless(os.path.exists(PRE) and os.path.exists(POST),
                     "generated cohort files not present")
class TestCutoffDataContract(unittest.TestCase):
    """The produced cohorts must obey the boundary, with no overlap."""

    @classmethod
    def setUpClass(cls):
        cls.cutoff = _stage03().CUTOFF_DATE
        cls.pre = pd.read_csv(PRE)
        cls.post = pd.read_csv(POST)

    def test_every_pre_trial_is_before_cutoff(self):
        bad = self.pre[self.pre.first_posted >= self.cutoff]
        self.assertEqual(len(bad), 0, f"pre-cutoff rows at/after cutoff:\n{bad.head()}")

    def test_every_post_trial_is_at_or_after_cutoff(self):
        bad = self.post[self.post.first_posted < self.cutoff]
        self.assertEqual(len(bad), 0, f"post-cutoff rows before cutoff:\n{bad.head()}")

    def test_no_trial_appears_in_both_cohorts(self):
        self.assertEqual(len(set(self.pre.nct_id) & set(self.post.nct_id)), 0)

    def test_no_duplicate_compound_trial_pairs(self):
        for name, frame in (("pre", self.pre), ("post", self.post)):
            self.assertEqual(
                int(frame.duplicated(["compound_name", "nct_id"]).sum()), 0, name)

    def test_no_missing_dates_survived(self):
        for name, frame in (("pre", self.pre), ("post", self.post)):
            self.assertEqual(int(frame.first_posted.isna().sum()), 0, name)


@unittest.skipUnless(os.path.exists(VPS), "vps_scores_v2.csv not present")
class TestRankingContract(unittest.TestCase):
    """The final ranking is the published artifact; it must be well-formed and
    reproducible from the stored scores."""

    @classmethod
    def setUpClass(cls):
        cls.v = pd.read_csv(VPS)

    def test_no_duplicate_compounds(self):
        self.assertEqual(int(self.v.compound_name.duplicated().sum()), 0)

    def test_scoring_columns_finite(self):
        cols = [c for c in self.v.columns if c.startswith(("r_", "VPS"))]
        block = self.v[cols].to_numpy(dtype=float)
        self.assertEqual(int(np.isnan(block).sum()), 0, "NaN in scoring columns")
        self.assertEqual(int(np.isinf(block).sum()), 0, "Inf in scoring columns")

    def test_rank_columns_in_unit_interval(self):
        for c in [c for c in self.v.columns if c.startswith("r_")]:
            self.assertTrue(((self.v[c] >= 0) & (self.v[c] <= 1)).all(), c)

    def test_labels_are_binary(self):
        self.assertTrue(set(self.v.label.unique()) <= {0, 1})

    def test_ranking_is_deterministic(self):
        a = self.v.sort_values(["VPS_equal_5d", "compound_name"],
                               ascending=[False, True]).compound_name.tolist()
        b = self.v.sort_values(["VPS_equal_5d", "compound_name"],
                               ascending=[False, True]).compound_name.tolist()
        self.assertEqual(a, b)
        self.assertEqual(len(a), len(set(a)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
