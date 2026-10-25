"""
Tests for scripts/trial_role.py (diagnostic trial-role annotator, TD-032).

Synthetic study records cover each verdict; two real ClinicalTrials.gov v2
records (fetched 2026-10-13, saved under tests/fixtures/) pin the procedural
cases found in the label audit. Offline.
"""

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import trial_role as tr  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")


def study(interventions, arms, title="A trial in Parkinson's disease", outcomes=("UPDRS-III change",),
          purpose="TREATMENT", nct="NCT00000000"):
    return {"protocolSection": {
        "identificationModule": {"nctId": nct, "briefTitle": title},
        "designModule": {"designInfo": {"primaryPurpose": purpose}},
        "outcomesModule": {"primaryOutcomes": [{"measure": o} for o in outcomes]},
        "armsInterventionsModule": {"interventions": interventions, "armGroups": arms}}}


def iv(name, typ="DRUG", other=()):
    return {"name": name, "type": typ, "otherNames": list(other)}


def arm(label, typ, *names):
    return {"label": label, "type": typ, "interventionNames": [f"Drug: {n}" for n in names]}


class TestVerdicts(unittest.TestCase):
    def test_therapeutic_test(self):
        s = study([iv("Terazosin"), iv("Placebo")],
                  [arm("TZ", "EXPERIMENTAL", "Terazosin"), arm("PBO", "PLACEBO_COMPARATOR", "Placebo")])
        self.assertEqual(tr.classify_trial_role(s, ["Terazosin"])["verdict"], "THERAPEUTIC_TEST")

    def test_background_therapy_only_in_othernames(self):
        # E-014 pattern: lisuride listed among permitted background agonists of another drug
        s = study([iv("Safinamide"), iv("Dopamine agonist", other=["pramipexole", "lisuride"])],
                  [arm("S", "EXPERIMENTAL", "Safinamide", "Dopamine agonist")])
        self.assertEqual(tr.classify_trial_role(s, ["Lisuride"])["verdict"], "BACKGROUND_OTHERNAME")

    def test_active_comparator_only(self):
        s = study([iv("DA-9701"), iv("Domperidone")],
                  [arm("New", "EXPERIMENTAL", "DA-9701"), arm("Ref", "ACTIVE_COMPARATOR", "Domperidone")])
        self.assertEqual(tr.classify_trial_role(s, ["Domperidone"])["verdict"], "COMPARATOR_ONLY")

    def test_placebo_is_not_a_cotherapy(self):
        s = study([iv("Melatonin"), iv("Placebo")],
                  [arm("M", "EXPERIMENTAL", "Melatonin", "Placebo")])
        self.assertEqual(tr.classify_trial_role(s, ["Melatonin"])["verdict"], "THERAPEUTIC_TEST")

    def test_co_administered_with_study_drug(self):
        s = study([iv("NS2330"), iv("Levodopa")],
                  [arm("A", "EXPERIMENTAL", "NS2330", "Levodopa")])
        self.assertEqual(tr.classify_trial_role(s, ["Levodopa"])["verdict"], "CO_ADMINISTERED")

    def test_anaesthesia_context(self):
        s = study([iv("Propofol"), iv("Dexmedetomidine")],
                  [arm("P", "ACTIVE_COMPARATOR", "Propofol"), arm("D", "EXPERIMENTAL", "Dexmedetomidine")],
                  title="Dexmedetomidine vs propofol sedation during DBS surgery",
                  outcomes=("Microelectrode recording quality",))
        r = tr.classify_trial_role(s, ["Dexmedetomidine"])
        self.assertEqual(r["verdict"], "PROCEDURAL_CONTEXT")
        self.assertTrue(r["procedural_hits"])

    def test_dbs_as_the_therapy_is_not_procedural(self):
        # a drug trial in DBS-treated patients is not anaesthesia
        s = study([iv("Safinamide")], [arm("S", "EXPERIMENTAL", "Safinamide")],
                  title="Safinamide in patients with deep brain stimulation")
        self.assertEqual(tr.classify_trial_role(s, ["Safinamide"])["verdict"], "THERAPEUTIC_TEST")

    def test_metabolite_or_class_name_not_matched(self):
        s = study([iv("Levodopa/carbidopa")], [arm("L", "EXPERIMENTAL", "Levodopa/carbidopa")])
        self.assertEqual(tr.classify_trial_role(s, ["Dopamine"])["verdict"], "NOT_NAMED")

    def test_missing_arm_data_is_undetermined_never_therapeutic(self):
        for s in (study([], []), study([iv("X")], []), {}, None):
            self.assertEqual(tr.classify_trial_role(s, ["X"])["verdict"], "UNDETERMINED")

    def test_compound_in_no_arm_is_undetermined(self):
        s = study([iv("X")], [arm("Other", "EXPERIMENTAL", "Y")])
        self.assertEqual(tr.classify_trial_role(s, ["X"])["verdict"], "UNDETERMINED")

    def test_every_verdict_carries_evidence_or_reason(self):
        s = study([iv("Terazosin")], [arm("TZ", "EXPERIMENTAL", "Terazosin")])
        r = tr.classify_trial_role(s, ["Terazosin"])
        self.assertTrue(r["evidence"])
        self.assertIn(r["verdict"], tr.VERDICTS)

    def test_deterministic(self):
        s = study([iv("Terazosin")], [arm("TZ", "EXPERIMENTAL", "Terazosin")])
        self.assertEqual(tr.classify_trial_role(s, ["Terazosin"]), tr.classify_trial_role(s, ["Terazosin"]))

    def test_sole_active_arm_typed_comparator_vs_placebo_is_a_test(self):
        # NCT05669170 pattern: 'Treatment' arm typed ACTIVE_COMPARATOR vs placebo
        s = study([iv("Psychosocial intervention", "BEHAVIORAL"), iv("Methylphenidate")],
                  [{"label": "Treatment", "type": "ACTIVE_COMPARATOR",
                    "interventionNames": ["Behavioral: Psychosocial intervention", "Drug: Methylphenidate"]},
                   {"label": "Placebo", "type": "PLACEBO_COMPARATOR",
                    "interventionNames": ["Behavioral: Psychosocial intervention"]}])
        self.assertEqual(tr.classify_trial_role(s, ["Methylphenidate"])["verdict"], "THERAPEUTIC_TEST")

    def test_head_to_head_comparators_are_tests(self):
        s = study([iv("Pimavanserin"), iv("Quetiapine")],
                  [arm("q", "ACTIVE_COMPARATOR", "Quetiapine"), arm("p", "ACTIVE_COMPARATOR", "Pimavanserin")])
        self.assertEqual(tr.classify_trial_role(s, ["Quetiapine"])["verdict"], "THERAPEUTIC_TEST")

    def test_chemogenetic_actuator_is_co_administered(self):
        s = study([iv("gene therapy", "GENETIC"), iv("clozapine")],
                  [{"label": "all", "type": "EXPERIMENTAL",
                    "interventionNames": ["Genetic: gene therapy", "Drug: clozapine"]}])
        self.assertEqual(tr.classify_trial_role(s, ["Clozapine"])["verdict"], "CO_ADMINISTERED")

    def test_nerve_block_agent_is_procedure_delivered(self):
        s = study([iv("Stellate ganglion block", "PROCEDURE"), iv("Lidocaine hydrochloride")],
                  [arm("SGB", "EXPERIMENTAL", "Lidocaine hydrochloride")],
                  title="Effectiveness of Stellate Ganglion Block in Parkinson's Disease")
        self.assertEqual(tr.classify_trial_role(s, ["Lidocaine"])["verdict"], "PROCEDURE_DELIVERED")

    def test_single_arm_typed_other_is_undetermined(self):
        s = study([iv("Pyridostigmine Bromide")], [arm("P", "OTHER", "Pyridostigmine Bromide")])
        self.assertEqual(tr.classify_trial_role(s, ["Pyridostigmine"])["verdict"], "UNDETERMINED")


class TestRealRecords(unittest.TestCase):
    """Registry records retrieved 2026-10-13 (label trials of two positives)."""

    def _load(self, nct):
        with open(os.path.join(FIX, f"ctgov_{nct}_role.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_dexmedetomidine_label_trial_is_procedural(self):
        r = tr.classify_trial_role(self._load("NCT05376761"), ["Dexmedetomidine"])
        self.assertEqual(r["verdict"], "PROCEDURAL_CONTEXT")

    def test_remifentanil_label_trial_is_procedural_despite_treatment_purpose(self):
        r = tr.classify_trial_role(self._load("NCT06658132"), ["Remifentanil"])
        self.assertEqual(r["primary_purpose"], "TREATMENT")   # registry field alone would not catch it
        self.assertEqual(r["verdict"], "PROCEDURAL_CONTEXT")


if __name__ == "__main__":
    unittest.main()
