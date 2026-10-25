"""
Tests for the Completeness & Gap Agent (10h), scripts/completeness_gap_agent.py.
Synthetic rows for each state, plus checks on the real persisted artefacts.
Offline: sockets are refused for the whole module.
"""

import hashlib
import importlib.util
import json
import os
import socket
import unittest

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("gap", os.path.join(ROOT, "scripts", "completeness_gap_agent.py"))
gap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gap)

_real_socket = socket.socket


def setUpModule():
    def refuse(*a, **k):
        raise AssertionError("10h must not open network connections")
    socket.socket = refuse


def tearDownModule():
    socket.socket = _real_socket


def row(**kw):
    return pd.DataFrame([kw])


class TestStates(unittest.TestCase):
    def test_safety_absent_label_vs_measured_zero_vs_no_row(self):
        absent = gap.assess_safety(row(has_label=False, boxed_warning=None, serious_term_count=None))
        zero = gap.assess_safety(row(has_label=True, boxed_warning=False, serious_term_count=0, label_set_id="x"))
        measured = gap.assess_safety(row(has_label=True, boxed_warning=True, serious_term_count=2, label_set_id="y"))
        norow = gap.assess_safety(pd.DataFrame())
        self.assertEqual(absent["state"], "ABSENT_AT_SOURCE")
        self.assertIn("neutral rank", absent["vps_treatment"])
        self.assertEqual(zero["state"], "MEASURED_ZERO")
        self.assertIn("not evidence of safety", zero["detail"])
        self.assertEqual(measured["state"], "MEASURED")
        self.assertEqual(norow["state"], "NOT_COMPUTED")
        self.assertIn("cannot be told apart", norow["detail"])

    def test_molecular_no_target_is_missing_but_zero_score_with_targets_is_measured(self):
        base = dict(resolved=True, chembl_id="C1", n_evidence_missing=0)
        self.assertEqual(gap.assess_molecular(row(**base, n_targets=0, molecular_plausibility_score=0.0))["state"],
                         "ABSENT_AT_SOURCE")
        self.assertEqual(gap.assess_molecular(row(**base, n_targets=3, molecular_plausibility_score=0.0))["state"],
                         "MEASURED_ZERO")
        self.assertEqual(gap.assess_molecular(row(resolved=False, chembl_id=None, n_evidence_missing=0, n_targets=0,
                                                  molecular_plausibility_score=0.0))["state"], "ABSENT_AT_SOURCE")
        partial = gap.assess_molecular(row(resolved=True, chembl_id="C", n_targets=2, molecular_plausibility_score=0.4,
                                           n_evidence_missing=3))
        self.assertEqual(partial["state"], "PARTIAL")

    def test_literature_failed_lookups_zero_papers_and_capped_sample(self):
        mk = lambda n, eff, f: row(raw_paper_count=n, effective_independent_count=eff, citation_lookup_failures=f)
        self.assertEqual(gap.assess_literature(mk(10, 4, 2))["state"], "PARTIAL")
        self.assertEqual(gap.assess_literature(mk(0, 0, 0))["state"], "MEASURED_ZERO")
        self.assertEqual(gap.assess_literature(mk(30, 12, 0))["state"], "PARTIAL")
        self.assertEqual(gap.assess_literature(mk(12, 5, 0))["state"], "MEASURED")

    def test_proximity_missing_row_is_imputed_not_neutral(self):
        s = gap.assess_proximity(pd.DataFrame())
        self.assertEqual(s["state"], "NOT_COMPUTED")
        self.assertIn("median-imputed", s["vps_treatment"])

    def test_clinical_phase_na_only_is_measured_zero(self):
        s = gap.assess_clinical(pd.DataFrame({"nct_id": ["N1", "N2"], "phase": [None, None]}))
        self.assertEqual(s["state"], "MEASURED_ZERO")

    def test_measured_zero_is_not_listed_as_a_gap(self):
        rec = {"domains": {"safety": {"state": "MEASURED_ZERO", "detail": "d"},
                           "molecular": {"state": "ABSENT_AT_SOURCE", "detail": "d", "vps_treatment": "neutral"}}}
        gaps = gap.gaps_for(rec)
        self.assertEqual([g["domain"] for g in gaps], ["molecular"])
        self.assertEqual(gaps[0]["severity"], "affects VPS")

    def test_validate_rejects_scores_and_unknown_states(self):
        out = {"schema_version": gap.COMPLETENESS_SCHEMA_VERSION, "domains": gap.DOMAINS,
               "state_meaning": gap.STATES, "stage06_agreement": True,
               "records": [{"compound": "X", "domains": {"safety": {"state": "MADE_UP"}}}]}
        with self.assertRaises(ValueError):
            gap.validate_output(out)
        out["records"] = [{"compound": "X", "domains": {}, "completeness_score": 0.4}]
        with self.assertRaises(ValueError):
            gap.validate_output(out)


class TestNewSources(unittest.TestCase):
    """2026-10-15: 10c results, 10f FAERS, 10g independence and recorded stage failures."""

    def test_recorded_failures_are_retrieval_failed_not_not_computed(self):
        s = gap.assess_safety(pd.DataFrame(), {"error_class": "HTTPError"})
        self.assertEqual(s["state"], "RETRIEVAL_FAILED")
        self.assertIn("neutral rank", s["vps_treatment"])
        self.assertEqual(gap.assess_literature(pd.DataFrame(), {"error_class": "Timeout"})["state"], "RETRIEVAL_FAILED")
        self.assertEqual(gap.assess_literature(pd.DataFrame())["state"], "NOT_COMPUTED")

    def test_trial_outcomes_from_10c(self):
        link = lambda st: {"results_state": st}
        posted = {"n_trials": 3, "n_results_posted": 1, "n_results_posted_pre_cutoff": 1, "n_primary_analyses_posted": 2,
                  "links": [link("RESULTS_POSTED"), link("NO_RESULTS_POSTED"), link("NO_RESULTS_POSTED")]}
        self.assertEqual(gap.assess_outcomes([], posted)["state"], "MEASURED")
        none = dict(posted, n_results_posted=0, links=[link("NO_RESULTS_POSTED")] * 3)
        self.assertEqual(gap.assess_outcomes([], none)["state"], "ABSENT_AT_SOURCE")
        failed = dict(none, links=[link("RETRIEVAL_FAILED")] + [link("NO_RESULTS_POSTED")] * 2)
        self.assertEqual(gap.assess_outcomes([], failed)["state"], "RETRIEVAL_FAILED")
        self.assertEqual(gap.assess_outcomes([], None)["state"], "NOT_RETRIEVED")

    def test_faers_and_independence_mapping(self):
        f = lambda st: {"faers": {"state": st, "detail": "d"}}
        self.assertEqual(gap.faers_state(f("NO_RECORD"))["state"], "ABSENT_AT_SOURCE")
        self.assertEqual(gap.faers_state(f("FAILED"))["state"], "RETRIEVAL_FAILED")
        self.assertEqual(gap.faers_state(None)["state"], "NOT_RETRIEVED")
        rec = {"checks": {"D1_shared_trial_across_compounds": {"state": "DEPENDENCE_FOUND"},
                          "D2_same_study_in_two_dimensions": {"state": "NOT_ASSESSABLE"},
                          "D3_duplicated_or_pooled_claims": {"state": "NOT_ASSESSABLE"},
                          "D4_molecular_datatype_reuse": {"state": "NONE_FOUND"}}}
        s = gap.independence_state(rec)
        self.assertEqual(s["state"], "PARTIAL")
        self.assertIn("shared trial across compounds", s["detail"])
        self.assertIn("(2/4 checks assessable)", s["detail"])

    def test_independence_denominator_counts_all_five_checks(self):
        # audit 2026-10-21: 10g runs D1-D5; the denominator was hard-coded 4 ("4/4" with all five assessable)
        ok = {k: {"state": "NONE_FOUND"} for k in ("D1_a", "D2_b", "D3_c", "D4_d", "D5_e")}
        self.assertIn("(5/5 checks assessable)", gap.independence_state({"checks": ok})["detail"])
        ok["D5_e"] = {"state": "NOT_ASSESSABLE"}
        self.assertIn("(4/5 checks assessable)", gap.independence_state({"checks": ok})["detail"])


class TestBrokenUpstreamIsReported(unittest.TestCase):
    """Sprint 2026-10-19 audit: an empty stage CSV or a missing agent output read as per-compound states only."""

    def setUp(self):
        import shutil, tempfile
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "data"))
        for rel in list(gap.F.values()) + list(gap.AGENT_OUTPUTS.values()):
            if os.path.exists(os.path.join(ROOT, rel)):
                shutil.copy2(os.path.join(ROOT, rel), os.path.join(self.root, rel))
        self.addCleanup(shutil.rmtree, self.root)

    def header_only(self, rel):
        with open(os.path.join(ROOT, rel)) as fh:
            header = fh.readline()
        with open(os.path.join(self.root, rel), "w") as fh:
            fh.write(header)

    def test_empty_stage_csv_and_missing_agent_output_are_warnings(self):
        self.header_only(gap.F["literature"])
        os.remove(os.path.join(self.root, gap.F["safety_evidence"]))
        out = gap.run(self.root)
        lv = {d["code"]: d["level"] for d in out["diagnostics"]}
        self.assertEqual(lv.get("INPUT_EMPTY"), "warn")
        self.assertEqual(lv.get("AGENT_OUTPUT_ABSENT"), "warn")
        self.assertEqual(out["run_status"], "PARTIAL")

    def test_pool_compound_without_clinical_rows_is_not_called_out_of_pool(self):
        self.header_only(gap.F["clinical"])
        r = gap.run(self.root)["records"][0]["domains"]["clinical"]
        self.assertEqual(r["state"], "NOT_COMPUTED")
        self.assertNotIn("not in the evaluable pool", r["detail"])


class TestOnPersistedArtefacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.exists(os.path.join(ROOT, gap.F["vps"])):
            raise unittest.SkipTest("stage-06 output absent")
        cls.out = gap.run(ROOT)
        cls.by = {r["compound"]: r for r in cls.out["records"]}

    def test_valid_and_agrees_with_stage06(self):
        self.assertTrue(gap.validate_output(self.out))
        self.assertEqual(self.out["cohort"]["n"], 90)

    def test_known_cases(self):
        self.assertEqual(self.by["Domperidone"]["domains"]["safety"]["state"], "ABSENT_AT_SOURCE")
        self.assertEqual(self.by["Glycerol Phenylbutyrate"]["domains"]["literature"]["state"], "MEASURED_ZERO")
        self.assertEqual(self.by["Deferiprone"]["domains"]["proximity"]["state"], "NOT_COMPUTED")
        self.assertEqual(self.by["Deferiprone"]["vps_dimensions_imputed_not_flagged"], ["proximity"])
        self.assertEqual(self.by["Paroxetine"]["domains"]["molecular"]["state"], "MEASURED_ZERO")
        self.assertEqual(self.by["Droxidopa"]["domains"]["literature_credibility"]["state"], "ASSESSED")
        self.assertEqual(self.by["Propofol"]["domains"]["trial_roles"]["roles"], {"PROCEDURAL": 2})   # D-020, via 10c
        self.assertEqual(self.by["Lisuride"]["domains"]["trial_roles"]["roles"].get("BACKGROUND_OTHERNAME"), 1)
        self.assertEqual(self.by["Domperidone"]["domains"]["adverse_events"]["state"], "MEASURED")

    def test_envelope_and_agent_staleness_reported(self):
        self.assertEqual(self.out["agent_id"], "10h")
        for aid in ("10c", "10d", "10e", "10f", "10g"):
            self.assertIn(aid, self.out["agent_outputs"])

    def test_safety_missingness_is_flagged_as_label_associated(self):
        s = next(m for m in self.out["missingness_vs_label"] if m["dimension"] == "safety")
        self.assertEqual((s["missing"], s["positives_among_missing"]), (7, 0))
        self.assertIn("associated with the label", s["note"])

    def test_synthesis_inputs_match_gaps(self):
        self.assertEqual(len(self.out["synthesis_inputs"]), sum(len(r["gaps"]) for r in self.out["records"]))

    def test_persisted_output_is_current(self):
        path = os.path.join(ROOT, gap.OUT)
        if not os.path.exists(path):
            self.skipTest("not generated")
        with open(path) as fh:
            saved = json.load(fh)
        for rel, md5 in saved["inputs"].items():
            with open(os.path.join(ROOT, rel), "rb") as fh:
                self.assertEqual(hashlib.md5(fh.read()).hexdigest(), md5, f"{rel} changed: re-run 10h")



class TestCredibilityState(unittest.TestCase):
    """10a --all states: failure, empty source and assessment stay distinct."""

    def test_states(self):
        self.assertEqual(gap.credibility_state({"status": "RETRIEVAL_FAILED"})["state"], "RETRIEVAL_FAILED")
        self.assertEqual(gap.credibility_state({"status": "NO_RESULTS"})["state"], "ABSENT_AT_SOURCE")
        summ = {"n_papers": 30, "n_human_tier_A_or_B": 4}
        st = gap.credibility_state({"status": "ASSESSED", "summary_stage04_sample": summ, "n_sample_post_cutoff": 12,
                                    "summary_cutoff_bounded": {"n_papers": 70, "n_human_tier_A_or_B": 9}})
        self.assertEqual((st["state"], st["sample_post_cutoff"], st["cutoff_bounded_human_A_B"]), ("ASSESSED", 12, 9))


class TestLabelAtCutoffAnnotation(unittest.TestCase):
    def test_annotation_keeps_state(self):
        st = gap.with_label_at_cutoff({"state": "MEASURED", "detail": "x"},
                                      {"label": {"at_cutoff": {"state": "SCORED", "changed_since_cutoff": True}}})
        self.assertEqual((st["state"], st["label_at_cutoff"], st["label_changed_since_cutoff"]), ("MEASURED", "SCORED", True))
        st = gap.with_label_at_cutoff({"state": "ABSENT_AT_SOURCE"}, None)
        self.assertNotIn("label_at_cutoff", st)

if __name__ == "__main__":
    unittest.main()
