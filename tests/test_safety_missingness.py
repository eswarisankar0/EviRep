"""
Regression tests for TD-031: a missing openFDA label must be MISSING safety
evidence, never "zero risk".

Before the fix, step 05 wrote serious_term_count=0 / boxed_warning=False for
a compound with no label, and step 06's inverted percentile rank turned that
into the best safety score in the pool (7 of 90 compounds, all label 0).

Offline: requests are mocked; nothing touches the project's data/.
Run:  ./venv/bin/python -m unittest tests.test_safety_missingness -v
"""

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", fname))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


safety05 = _load("safety_signal_05", "05_safety_signal.py")
vps = _load("vps_fusion_06", "06_vps_fusion.py")


def _resp(status, payload=None):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = payload or {}
    if status >= 400 and status != 404:
        r.raise_for_status.side_effect = RuntimeError(f"HTTP {status}")
    else:
        r.raise_for_status.return_value = None
    return r


class TestStep05Scoring(unittest.TestCase):
    def test_no_label_is_recorded_as_missing_not_zero(self):
        out = safety05.score_safety(None)
        self.assertFalse(out["has_label"])
        self.assertIsNone(out["serious_term_count"])
        self.assertIsNone(out["boxed_warning"])

    def test_valid_label_is_scored(self):
        label = {"warnings": ["Risk of seizure and stroke. Seizure reported."], "boxed_warning": ["Fatal"]}
        out = safety05.score_safety(label)
        self.assertEqual({k: out[k] for k in ("has_label", "boxed_warning", "serious_term_count")},
                         {"has_label": True, "boxed_warning": True, "serious_term_count": 4})

    def test_label_without_warnings_is_a_measured_zero(self):
        out = safety05.score_safety({"indications_and_usage": ["x"]})
        self.assertEqual({k: out[k] for k in ("has_label", "boxed_warning", "serious_term_count")},
                         {"has_label": True, "boxed_warning": False, "serious_term_count": 0})

    def test_plr_warnings_and_cautions_section_is_counted(self):
        # D-003: PLR-format labels have no "warnings" key; v1 scored them as 0.
        out = safety05.score_safety({"warnings_and_cautions": ["5.1 Seizures. Fatal outcomes and stroke."]})
        self.assertEqual(out["serious_term_count"], 3)
        self.assertEqual(out["warning_fields"], "warnings_and_cautions")

    def test_real_plr_label_is_not_scored_zero(self):
        # Subset of the openFDA varenicline label fetched 2026-10-15 (set_id/effective_time kept).
        with open(os.path.join(ROOT, "tests", "fixtures", "openfda_varenicline_label_subset.json")) as fh:
            label = json.load(fh)
        self.assertNotIn("warnings", label)
        out = safety05.score_safety(label)
        self.assertEqual(out["serious_term_count"], 25)
        self.assertEqual(out["label_effective_time"], "20250508")

    def test_404_means_no_label(self):
        with mock.patch.object(safety05.requests, "get", return_value=_resp(404)):
            self.assertIsNone(safety05.query_label("Nothingamide"))

    def test_http_failure_raises_instead_of_returning_no_label(self):
        with mock.patch.object(safety05.requests, "get", return_value=_resp(503)):
            with self.assertRaises(RuntimeError):
                safety05.query_label("Flakyamide")

    def test_empty_result_list_means_no_label(self):
        with mock.patch.object(safety05.requests, "get", return_value=_resp(200, {"results": []})):
            self.assertIsNone(safety05.query_label("Emptyamide"))


class TestStep05Main(unittest.TestCase):
    """API failure -> no checkpoint row (missing); no label -> blank values."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="evirep_safety_")
        os.makedirs(os.path.join(self.tmp, "data"))
        pd.DataFrame({"compound_name": ["Alpha", "Beta", "Gamma"]}).to_csv(
            os.path.join(self.tmp, "data", "clinical_maturity_precutoff_clean.csv"), index=False)
        self.cwd = os.getcwd()
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_failure_and_absence_stay_distinguishable(self):
        def fake(name):
            if name == "Alpha":
                return {"warnings": ["seizure"]}
            if name == "Beta":
                return None
            raise RuntimeError("HTTP 503")
        with mock.patch.object(safety05, "query_label", side_effect=fake), \
                mock.patch.object(safety05.time, "sleep"), mock.patch("builtins.print"):
            with self.assertRaises(SystemExit) as cm:          # E-021: a partial run exits non-zero
                safety05.main()
        self.assertEqual(cm.exception.code, 1)
        with open(safety05.CHECKPOINT_FILE) as fh:
            recs = {json.loads(l)["compound_name"]: json.loads(l) for l in fh}
        self.assertNotIn("Gamma", recs)                      # failure: no checkpoint row, so a re-run retries it
        with open(safety05.FAILURES_FILE) as fh:             # ...but it is recorded, not silently dropped (E-021)
            fails = [json.loads(l) for l in fh]
        self.assertEqual([(f["compound_name"], f["error_class"]) for f in fails], [("Gamma", "RuntimeError")])
        self.assertIsNone(recs["Beta"]["serious_term_count"])  # absence: recorded as null
        out = pd.read_csv("data/safety_signal.csv")
        beta = out[out.compound_name == "Beta"].iloc[0]
        self.assertTrue(pd.isna(beta["serious_term_count"]))
        self.assertEqual(int(out[out.compound_name == "Alpha"].iloc[0]["serious_term_count"]), 1)


def _frames(safety_rows):
    names = [r["compound_name"] for r in safety_rows]
    n = len(names)
    cands = pd.DataFrame({"compound_name": names})
    prox = pd.DataFrame({"compound_name": names, "proximity_z": np.linspace(-1, 1, n)})
    clin = pd.DataFrame({"compound_name": names, "max_phase_rank": np.arange(n) % 5, "n_trials": 1})
    lit = pd.DataFrame({"compound_name": names, "raw_paper_count": 10,
                        "effective_independent_count": np.arange(n), "independence_ratio": 0.5})
    return cands, prox, clin, lit, pd.DataFrame(safety_rows)


class TestFusionSafetyMissingness(unittest.TestCase):
    def _scored(self, safety_rows):
        cands, prox, clin, lit, saf = _frames(safety_rows)
        df = vps.merge_dimensions(cands, prox, clin, lit, saf)
        df = vps.impute_missing(df)
        return vps.build_standardized_scores(df).set_index("compound_name")

    ROWS = [
        {"compound_name": "Measured0", "has_label": True, "boxed_warning": False, "serious_term_count": 0},
        {"compound_name": "Risky", "has_label": True, "boxed_warning": True, "serious_term_count": 9},
        {"compound_name": "Mid1", "has_label": True, "boxed_warning": False, "serious_term_count": 2},
        {"compound_name": "Mid2", "has_label": True, "boxed_warning": False, "serious_term_count": 4},
        # legacy checkpoint encoding of "no label" (the defect)
        {"compound_name": "NoLabelLegacy", "has_label": False, "boxed_warning": False, "serious_term_count": 0},
        # new encoding
        {"compound_name": "NoLabelNew", "has_label": False, "boxed_warning": None, "serious_term_count": None},
    ]

    def test_no_label_gets_neutral_rank_not_a_measured_one(self):
        # D-004: missing safety is ranked neither best nor worst; it gets NEUTRAL_RANK.
        df = self._scored(self.ROWS)
        self.assertEqual(df.loc["Measured0", "r_safety"], df["r_safety"].max())
        for name in ("NoLabelLegacy", "NoLabelNew"):
            self.assertEqual(df.loc[name, "r_safety"], vps.NEUTRAL_RANK, name)
            self.assertIn("safety", df.loc[name, "dimensions_missing"].split("|"))
            self.assertEqual(df.loc[name, "n_dimensions_measured"], 3)

    def test_zero_inflated_pool_no_longer_ties_missing_with_safest(self):
        """TD-031 regression on the real-data shape: median risk 0 used to give a
        no-label compound the best safety rank."""
        rows = [dict(r) for r in self.ROWS]
        rows[1].update(serious_term_count=0, boxed_warning=False)   # measured risks 0, 0, 2, 4
        df = self._scored(rows)
        self.assertLess(df.loc["NoLabelNew", "r_safety"], df.loc["Measured0", "r_safety"])
        self.assertGreater(df.loc["NoLabelNew", "r_safety"], df.loc["Mid1", "r_safety"])
        self.assertEqual(df.loc["NoLabelNew", "r_safety"], vps.NEUTRAL_RANK)
        self.assertTrue(df.loc["NoLabelNew", "safety_label_missing"])

    def test_measured_compounds_are_ranked_among_measured_only(self):
        df = self._scored(self.ROWS)
        measured = df.loc[["Measured0", "Risky", "Mid1", "Mid2"], "r_safety"]
        self.assertEqual(sorted(measured.round(6)), [0.0, 0.25, 0.5, 0.75])   # 1 - pct rank of 4

    def test_legacy_and_new_encodings_are_equivalent(self):
        df = self._scored(self.ROWS)
        self.assertEqual(df.loc["NoLabelLegacy", "r_safety"], df.loc["NoLabelNew", "r_safety"])

    def test_missingness_flag_is_visible(self):
        df = self._scored(self.ROWS)
        self.assertEqual(set(df.index[df["safety_label_missing"]]), {"NoLabelLegacy", "NoLabelNew"})

    def test_compound_without_any_safety_row_is_flagged_missing(self):
        cands, prox, clin, lit, saf = _frames(self.ROWS)
        cands = pd.concat([cands, pd.DataFrame({"compound_name": ["Unqueried"]})])
        prox = pd.concat([prox, pd.DataFrame({"compound_name": ["Unqueried"], "proximity_z": [0.0]})])
        clin = pd.concat([clin, pd.DataFrame({"compound_name": ["Unqueried"], "max_phase_rank": [1],
                                              "n_trials": [1]})])
        df = vps.merge_dimensions(cands, prox, clin, lit, saf).set_index("compound_name")
        self.assertTrue(df.loc["Unqueried", "safety_label_missing"])

    def test_labelled_compounds_raw_values_unchanged(self):
        cands, prox, clin, lit, saf = _frames(self.ROWS)
        df = vps.merge_dimensions(cands, prox, clin, lit, saf).set_index("compound_name")
        for r in self.ROWS[:4]:
            self.assertEqual(df.loc[r["compound_name"], "serious_term_count"], r["serious_term_count"])
            self.assertEqual(bool(df.loc[r["compound_name"], "boxed_warning"]), r["boxed_warning"])

    def test_missing_safety_is_not_imputed(self):
        df = self._scored(self.ROWS)
        self.assertTrue(np.isnan(df.loc["NoLabelNew", "serious_term_count"]))

    def test_string_has_label_values_from_csv(self):
        rows = [dict(r, has_label=str(r["has_label"])) for r in self.ROWS]
        df = self._scored(rows)
        self.assertEqual(set(df.index[df["safety_label_missing"]]), {"NoLabelLegacy", "NoLabelNew"})


if __name__ == "__main__":
    unittest.main()
