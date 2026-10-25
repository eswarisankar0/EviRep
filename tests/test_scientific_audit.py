"""Scientific release audit (2026-10-20): statistical, ranking, provenance and pipeline-contract regression tests.

Expectations come from definitions written out in each test (Mann-Whitney by pair counting, average-tie percentile
ranks, explicit bootstrap draws), not from current production output. Offline; no network; no repository writes.
"""
import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest
import warnings
from unittest import mock

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


vve = _load("audit_vve", "scripts/vps_validation_experiments.py")
fusion = _load("audit_06", "scripts/06_vps_fusion.py")
report = _load("audit_report", "scripts/vps_evaluation_report.py")
bci = _load("audit_bci", "scripts/bootstrap_auroc_ci.py")
s03 = _load("audit_s03", "scripts/03_clinicaltrials_groundtruth.py")
import agent_contract as ac  # noqa: E402
import run_stage  # noqa: E402


def mw(y, s):
    """Mann-Whitney AUROC by explicit pair counting (ties count 1/2); None when undefined."""
    pos = [v for v, t in zip(s, y) if t == 1]
    neg = [v for v, t in zip(s, y) if t == 0]
    if not pos or not neg:
        return None
    return sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))


class TestAurocCols(unittest.TestCase):
    def test_agrees_with_pair_counting_including_ties_and_reversal(self):
        rng = np.random.default_rng(7)
        for _ in range(25):
            n = int(rng.integers(6, 40))
            y = rng.integers(0, 2, n)
            if y.min() == y.max():
                y[0] = 1 - y[0]
            s = rng.integers(0, 5, n).astype(float)          # coarse values -> many ties
            got = vve.auroc_cols(s[:, None], y)[0]
            self.assertAlmostEqual(got, mw(list(y), list(s)), places=12)
            self.assertAlmostEqual(vve.auroc_cols(-s[:, None], y)[0], 1 - got, places=12)   # reversed scores

    def test_known_values(self):
        y = np.array([0, 0, 1, 1])
        self.assertEqual(vve.auroc_cols(np.array([[1.], [2.], [3.], [4.]]), y)[0], 1.0)
        self.assertEqual(vve.auroc_cols(np.array([[4.], [3.], [2.], [1.]]), y)[0], 0.0)
        self.assertEqual(vve.auroc_cols(np.array([[1.], [1.], [1.], [1.]]), y)[0], 0.5)   # all tied = 1/2

    def test_single_class_is_undefined_not_half_and_silent(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")                    # the old code raised a RuntimeWarning here
            out = vve.auroc_cols(np.array([[1., 2.], [2., 1.], [3., 0.]]), np.array([1, 1, 1]))
        self.assertTrue(np.isnan(out).all())
        self.assertTrue(np.isnan(vve.auroc_cols(np.zeros((0, 1)), np.zeros(0, int))).all())

    def test_bad_inputs_are_errors(self):
        with self.assertRaises(ValueError):
            vve.auroc_cols(np.array([[1.], [2.]]), np.array([0, 2]))           # non-binary
        with self.assertRaises(ValueError):
            vve.auroc_cols(np.array([[1.], [np.nan]]), np.array([0, 1]))      # non-finite
        with self.assertRaises(ValueError):
            vve.auroc_cols(np.array([[1.], [2.], [3.]]), np.array([0, 1]))    # shape mismatch


class TestSelectionNeverFallsBackSilently(unittest.TestCase):
    def test_undefined_folds_are_skipped(self):
        self.assertEqual(vve.best_index([[np.nan, np.nan, np.nan], [0.4, 0.9, 0.6], [0.5, 0.7, 0.8]]), 1)

    def test_all_undefined_raises_instead_of_choosing_the_first_candidate(self):
        with self.assertRaises(vve.UndefinedSelection):
            vve.best_index([[np.nan, np.nan], [np.nan, np.nan]])

    def test_ties_go_to_the_first_candidate(self):
        self.assertEqual(vve.best_index([[0.7, 0.7]]), 0)


class TestPercentileRanks(unittest.TestCase):
    def test_average_ties_inversion_missing(self):
        s = pd.Series([10, 20, 20, 30, np.nan])
        r = fusion.percentile_rank(s, convention="legacy")
        # average 1-based ranks among the 4 non-missing values: 1, 2.5, 2.5, 4 -> /4
        self.assertEqual(r.iloc[:4].tolist(), [0.25, 0.625, 0.625, 1.0])
        self.assertTrue(np.isnan(r.iloc[4]))
        inv = fusion.percentile_rank(s, invert=True, convention="legacy")
        self.assertEqual(inv.iloc[:4].tolist(), [0.75, 0.375, 0.375, 0.0])

    def test_midrank_is_symmetric(self):
        s = pd.Series([1, 2, 3, 4])
        m = fusion.percentile_rank(s, convention="midrank")
        mi = fusion.percentile_rank(s, invert=True, convention="midrank")
        self.assertEqual(m.tolist(), [0.125, 0.375, 0.625, 0.875])
        self.assertEqual(mi.tolist(), [0.875, 0.625, 0.375, 0.125])

    def test_identical_values_and_single_value(self):
        self.assertEqual(fusion.percentile_rank(pd.Series([5, 5, 5])).tolist(), [2 / 3] * 3)
        self.assertEqual(fusion.percentile_rank(pd.Series([7])).tolist(), [1.0])


class TestBootstrap(unittest.TestCase):
    def test_report_bootstrap_is_deterministic_and_ordinary(self):
        rng = np.random.default_rng(1)
        y = np.array([1] * 6 + [0] * 24); s = rng.random(30)
        a = report.boot_metric(y, s, report.roc_auc_score if hasattr(report, "roc_auc_score") else (lambda yy, ss: mw(list(yy), list(ss))), n=300)
        b = report.boot_metric(y, s, report.roc_auc_score if hasattr(report, "roc_auc_score") else (lambda yy, ss: mw(list(yy), list(ss))), n=300)
        self.assertEqual(a, b)
        # reproduce the draws by hand: ordinary (not stratified) resampling with default_rng(42)
        g = np.random.default_rng(42); vals = []
        for _ in range(300):
            i = g.integers(0, 30, 30)
            if y[i].min() != y[i].max():
                vals.append(mw(list(y[i]), list(s[i])))
        self.assertAlmostEqual(a[0][0], float(np.percentile(vals, 2.5)), places=12)
        self.assertAlmostEqual(a[0][1], float(np.percentile(vals, 97.5)), places=12)

    def test_single_class_draws_are_skipped_and_counted(self):
        y = np.array([1] + [0] * 9); s = np.arange(10.)
        ci, skipped = report.boot_metric(y, s, lambda yy, ss: mw(list(yy), list(ss)), n=200)
        g = np.random.default_rng(42)
        expected = sum(1 for _ in range(200) if (lambda i: y[i].min() == y[i].max())(g.integers(0, 10, 10)))
        self.assertEqual(skipped, expected)
        self.assertGreater(skipped, 0)

    def test_paired_difference_is_computed_draw_by_draw(self):
        rng = np.random.default_rng(3)
        y = np.array([1] * 8 + [0] * 32); a = rng.random(40); b = a + rng.normal(0, .3, 40)
        out = bci.paired_bootstrap(y, a, b, n_boot=400, seed=11)
        g = np.random.default_rng(11); d = []
        for _ in range(400):
            i = g.integers(0, 40, 40)
            if y[i].min() != y[i].max():
                d.append(mw(list(y[i]), list(a[i])) - mw(list(y[i]), list(b[i])))
        self.assertAlmostEqual(out["ci_diff"][0], float(np.quantile(d, .025)), places=10)
        self.assertAlmostEqual(out["ci_diff"][1], float(np.quantile(d, .975)), places=10)
        self.assertAlmostEqual(out["diff"], mw(list(y), list(a)) - mw(list(y), list(b)), places=12)


class TestEnvelopeProvenance(unittest.TestCase):
    def test_absent_inputs_are_recorded_and_their_appearance_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "a.csv"), "w") as fh:
                fh.write("x\n1\n")
            h = ac.input_hashes(d, ["a.csv", "b.csv"])
            self.assertIsNone(h["b.csv"])
            self.assertEqual(ac.stale_inputs(d, h), [])                      # still absent: not stale
            with open(os.path.join(d, "b.csv"), "w") as fh:
                fh.write("y\n")
            self.assertEqual(ac.stale_inputs(d, h), ["b.csv"])               # appeared: stale
            os.remove(os.path.join(d, "a.csv"))
            self.assertEqual(sorted(ac.stale_inputs(d, h)), ["a.csv", "b.csv"])

    def test_server_uses_the_same_rule(self):
        ui = _load("audit_ui", "ui/server.py")
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "data"))
            h = {"data/x.json": None}
            self.assertEqual(ui._stale_inputs(d, h), [])
            self.assertEqual(ui._stale_cached(d, h), [])
            with open(os.path.join(d, "data/x.json"), "w") as fh:
                fh.write("{}")
            self.assertEqual(ui._stale_inputs(d, h), ["data/x.json"])
            self.assertEqual(ui._stale_cached(d, h), ["data/x.json"])


class TestStage03Pagination(unittest.TestCase):
    class _Resp:
        def __init__(self, code, body):
            self.status_code, self._b, self.headers = code, body, {}

        def json(self):
            return self._b

    def test_every_page_is_fetched(self):
        pages = [self._Resp(200, {"studies": [{"id": i} for i in range(100)], "nextPageToken": "t2"}),
                 self._Resp(200, {"studies": [{"id": i} for i in range(100, 137)]})]
        calls = []

        def get(url, params=None, timeout=None):
            calls.append(dict(params)); return pages[len(calls) - 1]
        with mock.patch.object(s03.requests, "get", get):
            studies, ok = s03.search_trials("Phenol")
        self.assertTrue(ok)
        self.assertEqual(len(studies), 137)
        self.assertNotIn("pageToken", calls[0]); self.assertEqual(calls[1]["pageToken"], "t2")

    def test_a_failed_later_page_fails_the_whole_search(self):
        seq = [self._Resp(200, {"studies": [{"id": 1}], "nextPageToken": "t2"})] + [self._Resp(500, {})] * 10

        def get(url, params=None, timeout=None):
            return seq.pop(0)
        with mock.patch.object(s03.requests, "get", get), mock.patch.object(s03.time, "sleep", lambda s: None):
            studies, ok = s03.search_trials("X")
        self.assertEqual((studies, ok), ([], False))                         # never a silently partial list


class TestRunnerPartialPolicy(unittest.TestCase):
    def test_partial_on_exit1_covers_the_partial_capable_stages(self):
        self.assertTrue({"04", "05", "04p", "05h", "10a-all"} <= run_stage.PARTIAL_ON_EXIT1)

    def test_stage08_has_a_timeout(self):
        ui = _load("audit_ui2", "ui/server.py")
        s08 = next(s for s in ui.STAGES if s["id"] == "08")
        self.assertGreater(s08.get("timeout_s") or 0, 0)


class TestLeakageSentinels(unittest.TestCase):
    """Static data-flow sentinels: label producers never read scores; feature producers never read labels."""
    LABEL_PRODUCERS = ["scripts/03_clinicaltrials_groundtruth.py", "scripts/check_studytype.py", "scripts/filter_by_studytype.py",
                       "scripts/intervention_matcher.py"]
    FEATURE_PRODUCERS = ["scripts/02_network_proximity.py", "scripts/04_literature_independence.py", "scripts/05_safety_signal.py",
                         "scripts/08_molecular_pathway.py", "scripts/molecular_agent.py"]

    def _src(self, rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            return fh.read()

    def test_label_producers_never_read_scores_or_dimensions(self):
        for rel in self.LABEL_PRODUCERS:
            src = self._src(rel)
            for bad in ("vps_scores", "VPS_", "literature_independence.csv", "safety_signal.csv", "network_proximity.csv"):
                self.assertNotIn(bad, src, f"{rel} references {bad}")

    def test_feature_producers_never_read_labels(self):
        for rel in self.FEATURE_PRODUCERS:
            src = self._src(rel)
            for bad in ("ground_truth_postcutoff", "label_role_exclusions", "clinical_review_worklist"):
                self.assertNotIn(bad, src, f"{rel} references {bad}")

    def test_molecular_scoring_excludes_outcome_encoding_datatypes(self):
        import molecular_agent as ma
        cfg = ma.MolecularAgentConfig()
        self.assertFalse({"clinical", "literature"} & set(cfg.allowed_datatypes))


class TestUiConsistency(unittest.TestCase):
    def test_no_stale_positive_count(self):
        with open(os.path.join(ROOT, "ui", "server.py"), encoding="utf-8") as fh:
            src = fh.read()
        with open(os.path.join(ROOT, "data", "vps_evaluation_report.json"), encoding="utf-8") as fh:
            rep = json.load(fh)
        self.assertNotIn("17 positives / 90", src)
        self.assertIn(f"{rep['cohort']['positives']} positives / {rep['cohort']['n']} compounds", src)


if __name__ == "__main__":
    unittest.main()
