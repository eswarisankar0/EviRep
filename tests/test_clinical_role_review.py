"""Tests for scripts/clinical_role_review.py (read-only review table for TD-038 / D-020 / TD-043)."""

import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("crr", os.path.join(ROOT, "scripts", "clinical_role_review.py"))
crr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(crr)


def study(title, arm_type="EXPERIMENTAL"):
    return {"protocolSection": {
        "identificationModule": {"nctId": "NCT00000001", "briefTitle": title},
        "armsInterventionsModule": {
            "interventions": [{"type": "DRUG", "name": "Alpha"}],
            "armGroups": [{"label": "A", "type": arm_type, "interventionNames": ["Drug: Alpha"]}]}}}


class TestStructuralVerdict(unittest.TestCase):
    def test_keyword_rule_is_disabled_only_for_the_structural_reading(self):
        s = study("Alpha for Daytime Sedation in PD")
        self.assertEqual(crr.trial_role.classify_trial_role(s, ["Alpha"])["verdict"], "PROCEDURAL_CONTEXT")
        self.assertEqual(crr.structural_verdict(s, ["Alpha"]), "THERAPEUTIC_TEST")
        self.assertEqual(crr.trial_role.classify_trial_role(s, ["Alpha"])["verdict"], "PROCEDURAL_CONTEXT")  # restored


@unittest.skipUnless(os.path.exists(os.path.join(ROOT, crr.CACHE)), "registry cache absent")
class TestOnPersistedArtefacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = crr.review(ROOT)

    def test_every_link_reviewed_and_adjudication_wins(self):
        self.assertEqual(len(self.df), 195)
        adj = self.df[self.df["adjudicated_category"].fillna("") != ""]
        self.assertEqual(len(adj), 35)
        self.assertTrue((adj["confidence"] == "adjudicated (D-020)").all())

    def test_keyword_decided_links_are_never_given_a_role(self):
        kw = self.df[self.df["review_flags"].fillna("").str.contains("KEYWORD_DECIDED")
                     & (self.df["adjudicated_category"].fillna("") == "")]
        self.assertGreater(len(kw), 0)
        self.assertTrue(kw["proposed_interpretation"].str.startswith("human review").all())
        q = self.df[(self.df["nct_id"] == "NCT04164758") & (self.df["compound"] == "Quetiapine")].iloc[0]
        self.assertEqual((q["auto_verdict"], q["structural_verdict"]), ("PROCEDURAL_CONTEXT", "COMPARATOR_ONLY"))

    def test_worklist_orders_by_priority_and_resolves_nothing(self):
        wl = crr.worklist(self.df)
        self.assertEqual(len(wl), 37)
        self.assertEqual(list(wl["priority"]), sorted(wl["priority"]))
        self.assertEqual((wl["flag"] == "KEYWORD_DECIDED").sum(), 10)
        self.assertTrue((wl["priority"].head(10) == 1).all())
        adj = wl[wl["current_role_adjudicated"] != ""]
        import pandas as pd
        roles = pd.read_csv(os.path.join(ROOT, crr.ROLES), keep_default_na=False).set_index(["nct_id", "compound_name"])
        for r in adj.itertuples():                       # every adjudication shown verbatim from the D-020 file
            self.assertTrue(r.current_role_adjudicated.startswith(roles.loc[(r.nct_id, r.compound), "category"] + " "))
        self.assertTrue(adj["status"].str.startswith("ADJUDICATED (D-020)").all())
        rest = wl[wl["current_role_adjudicated"] == ""]
        self.assertTrue((rest["status"] == "UNRESOLVED - awaiting human adjudication").all())
        self.assertTrue((wl[["reviewer", "decision", "decision_date", "decision_source"]] == "").all().all())


if __name__ == "__main__":
    unittest.main()
