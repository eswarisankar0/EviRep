"""
Tests for TD-038: per-link feature exclusions (apply_feature_exclusions in
scripts/06_vps_fusion.py), the curated adjudication
data/feature_trial_roles_td038.csv, and the persisted sensitivity report.
Offline; the report itself is not re-run here (about 70 s).
"""

import hashlib
import importlib.util
import json
import os
import sys
import unittest

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vps = _load("vps", "scripts/06_vps_fusion.py")
sens = _load("td038", "scripts/td038_feature_role_sensitivity.py")


def clinical():
    return pd.DataFrame({"compound_name": ["A", "B", "B", "C"], "nct_id": ["NCT1", "NCT1", "NCT2", "NCT3"],
                         "phase": ["PHASE3", "PHASE3", "PHASE1", "PHASE2"]})


class TestApplyFeatureExclusions(unittest.TestCase):
    def test_exclusion_is_per_link_so_a_multi_arm_trial_survives_for_the_other_compound(self):
        kept, lost = vps.apply_feature_exclusions(clinical(), pd.DataFrame({"nct_id": ["NCT1"],
                                                                            "compound_name": ["B"]}))
        self.assertIn(("NCT1", "A"), set(zip(kept["nct_id"], kept["compound_name"])))
        self.assertEqual(lost, [])
        cm = vps.build_clinical_maturity(kept).set_index("compound_name")
        self.assertEqual(cm.loc["B", "max_phase_rank"], vps.PHASE_RANK["PHASE1"])
        self.assertEqual(cm.loc["A", "max_phase_rank"], vps.PHASE_RANK["PHASE3"])

    def test_compound_with_no_remaining_link_is_reported(self):
        _, lost = vps.apply_feature_exclusions(clinical(), pd.DataFrame({"nct_id": ["NCT3"], "compound_name": ["C"]}))
        self.assertEqual(lost, ["C"])

    def test_unknown_link_raises(self):
        with self.assertRaises(ValueError):
            vps.apply_feature_exclusions(clinical(), pd.DataFrame({"nct_id": ["NCT3"], "compound_name": ["A"]}))

    def test_empty_is_a_no_op(self):
        kept, lost = vps.apply_feature_exclusions(clinical(), pd.DataFrame(columns=["nct_id", "compound_name"]))
        self.assertEqual(len(kept), 4)
        self.assertEqual(lost, [])


class TestAdjudication(unittest.TestCase):
    def setUp(self):
        reg = os.path.join(ROOT, sens.REGISTRY)
        if not os.path.exists(reg):
            self.skipTest("registry cache absent")
        with open(reg) as fh:
            registry = {s["protocolSection"]["identificationModule"]["nctId"]: s for s in json.load(fh)["studies"]}
        clin = pd.read_csv(os.path.join(ROOT, "data/clinical_maturity_precutoff_clean.csv"))
        self.roles = sens.load_roles(clin, registry)     # raises if coverage, phase or annotator verdict drift

    def test_covers_the_17_shared_trials(self):
        self.assertEqual(self.roles["nct_id"].nunique(), 17)
        self.assertEqual(self.roles["compound_name"].nunique(), 31)

    def test_verdicts_follow_categories(self):
        by = self.roles.groupby("p1_qualifies")["category"].apply(set).to_dict()
        self.assertLessEqual(by["NO"], {"PROCEDURAL", "AUXILIARY_AGENT"})
        self.assertLessEqual(by["YES"], {"DRUG_SPECIFIC_ARM", "ALTERNATIVES_IN_ONE_ARM"})
        self.assertLessEqual(by["UNDECIDED"], {"FIXED_COMBINATION", "UNVERIFIABLE"})
        combo = self.roles[self.roles["category"] == "FIXED_COMBINATION"]
        self.assertTrue((combo["combination_role"] != "").all())
        self.assertTrue((self.roles["rationale"].str.len() > 20).all())


class TestPersistedSensitivity(unittest.TestCase):
    PATH = os.path.join(ROOT, sens.OUT)

    def setUp(self):
        if not os.path.exists(self.PATH):
            self.skipTest("report not generated")
        with open(self.PATH) as fh:
            self.r = json.load(fh)

    def test_report_is_current_for_its_inputs(self):
        for rel, md5 in self.r["inputs"].items():
            with open(os.path.join(ROOT, rel), "rb") as fh:
                self.assertEqual(hashlib.md5(fh.read()).hexdigest(), md5, f"{rel} changed: re-run the report")

    def test_current_scenario_reproduces_and_is_labelled_sensitivity_only(self):
        self.assertTrue(self.r["reproduces_persisted_scores"])
        self.assertTrue(self.r["status"].startswith("SENSITIVITY ONLY"))
        s0 = self.r["scenarios"]["S0_current"]
        self.assertEqual((s0["n"], s0["positives"]), (90, 14))

    def test_cohort_and_score_effects_are_separated(self):
        s1 = self.r["scenarios"]["S1_exclude_P1_NO"]
        self.assertIn("cohort_effect_only", s1)
        self.assertIn("paired_new_minus_old", s1["vs_current_same_compounds"])
        self.assertEqual(s1["positives"], 14)                       # only negatives leave the pool
        self.assertTrue(all(v == 0 for v in s1["labels_of_leaving"].values()))

    def test_no_scenario_claims_5d_beats_4d(self):
        for k, s in self.r["scenarios"].items():
            self.assertLess(s["5d_minus_4d"]["ci_diff"][0], 0, k)

    def test_policy_not_applied_to_primary_outputs(self):
        if os.path.exists(os.path.join(ROOT, vps.FEATURE_EXCLUSIONS_CSV)):
            self.skipTest("feature exclusions adopted; primary outputs are expected to change")
        scores = pd.read_csv(os.path.join(ROOT, "data/vps_scores_v2.csv"))
        self.assertEqual(len(scores), 90)


if __name__ == "__main__":
    unittest.main()
