"""
Tests for TD-032 label exclusions in scripts/06_vps_fusion.py
(apply_label_exclusions + the curated data/label_role_exclusions.csv). Offline.
"""

import importlib.util
import os
import unittest

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("vps", os.path.join(ROOT, "scripts", "06_vps_fusion.py"))
vps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vps)


def gt():
    return pd.DataFrame({"compound_name": ["A", "B", "B", "C"],
                         "nct_id": ["NCT1", "NCT2", "NCT3", "NCT4"]})


class TestApplyLabelExclusions(unittest.TestCase):
    def test_compound_with_only_excluded_trials_loses_label(self):
        kept, lost = vps.apply_label_exclusions(gt(), pd.DataFrame({"nct_id": ["NCT1"], "compound_name": ["A"]}))
        self.assertEqual(lost, ["A"])
        df = vps.build_labels(pd.DataFrame({"compound_name": ["A", "B", "C", "D"]}), kept)
        self.assertEqual(df["label"].tolist(), [0, 1, 1, 0])

    def test_exclusion_is_per_trial_not_per_compound(self):
        kept, lost = vps.apply_label_exclusions(gt(), pd.DataFrame({"nct_id": ["NCT2"], "compound_name": ["B"]}))
        self.assertEqual(lost, [])
        self.assertIn("B", set(kept["compound_name"]))

    def test_empty_or_missing_exclusions_change_nothing(self):
        for ex in (None, pd.DataFrame(columns=["nct_id", "compound_name"])):
            kept, lost = vps.apply_label_exclusions(gt(), ex)
            self.assertTrue(kept.equals(gt()))
            self.assertEqual(lost, [])

    def test_mismatched_exclusion_raises(self):
        for n, c in (("NCT9", "A"), ("NCT1", "B")):
            with self.assertRaises(ValueError):
                vps.apply_label_exclusions(gt(), pd.DataFrame({"nct_id": [n], "compound_name": [c]}))


class TestCuratedExclusionFile(unittest.TestCase):
    """The persisted P1 policy: exactly the three rejected labels of CASE_STUDIES §9.1."""

    def test_file_matches_approved_policy_and_ground_truth(self):
        ex = pd.read_csv(os.path.join(ROOT, vps.LABEL_EXCLUSIONS_CSV))
        self.assertEqual(sorted(ex["compound_name"]), ["Clozapine", "Dexmedetomidine", "Remifentanil"])
        truth = pd.read_csv(os.path.join(ROOT, "data", "ground_truth_postcutoff_clean.csv"))
        kept, lost = vps.apply_label_exclusions(truth, ex)
        self.assertEqual(lost, ["Clozapine", "Dexmedetomidine", "Remifentanil"])
        self.assertEqual(len(truth) - len(kept), 3)
        for unresolved in ("Lidocaine", "Galantamine"):        # kept positive by the owner decision
            self.assertIn(unresolved, set(kept["compound_name"]))


if __name__ == "__main__":
    unittest.main()
