"""
Pipeline safety and scoring contracts (2026-10-15 validation sprint).

  * `--help` / stray arguments exit before any stage work (TD-034, E-017)
  * the original ground-truth file is unchanged (TD-032 keeps it untouched)
  * equal-weight VPS is the plain mean of the percentile-ranked dimensions
  * grid-search weights are selected on training folds only (TD-003)
  * Figure 1's uncertainty caption is computed from persisted scores

Offline: the --help subprocesses run in an empty temp directory with an
unroutable proxy, so a regression could neither touch data/ nor reach an API.
"""

import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vps = _load("vps_contract", "06_vps_fusion.py")

STAGES = ["00_exclusion_filter.py", "01_get_pd_candidates.py", "02_network_proximity.py",
          "03_clinicaltrials_groundtruth.py", "04_literature_independence.py", "05_safety_signal.py",
          "06_vps_fusion.py", "07_generate_figures.py", "check_studytype.py",
          "check_intervention_match.py"]


def _files_under(path):
    return [os.path.join(d, f) for d, _, fs in os.walk(path) for f in fs]


class TestHelpDoesNotRunStages(unittest.TestCase):
    def _run(self, script, *args):
        tmp = tempfile.mkdtemp()
        env = {k: v for k, v in os.environ.items() if not k.endswith("API_KEY")}
        env.update(HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9", MPLBACKEND="Agg")
        try:
            r = subprocess.run([sys.executable, "-W", "ignore", os.path.join(SCRIPTS, script), *args],
                               cwd=tmp, env=env, capture_output=True, text=True, timeout=120)
            return r, _files_under(tmp)
        finally:
            shutil.rmtree(tmp)

    def test_help_exits_cleanly_without_writing(self):
        for script in STAGES:
            with self.subTest(script=script):
                r, written = self._run(script, "--help")
                self.assertEqual(r.returncode, 0, r.stderr[-500:])
                self.assertIn("usage:", r.stdout)
                self.assertEqual(written, [])

    def test_unknown_argument_is_rejected_before_work(self):
        for script in ("05_safety_signal.py", "06_vps_fusion.py", "07_generate_figures.py"):
            with self.subTest(script=script):
                r, written = self._run(script, "--no-such-flag")
                self.assertEqual(r.returncode, 2)
                self.assertEqual(written, [])


class TestOriginalGroundTruthUnchanged(unittest.TestCase):
    # md5 recorded at sprint start 2026-10-13 and re-verified 2026-10-15. If stage 03 is
    # deliberately re-run, update this pin in the same change and log it.
    PIN = "c83e30bbb44f37e5aeb51a6010d7af5e"

    def test_ground_truth_md5(self):
        path = os.path.join(ROOT, "data", "ground_truth_postcutoff_clean.csv")
        if not os.path.exists(path):
            self.skipTest("data/ground_truth_postcutoff_clean.csv not present")
        with open(path, "rb") as fh:
            self.assertEqual(hashlib.md5(fh.read()).hexdigest(), self.PIN)


class TestEqualWeightFormula(unittest.TestCase):
    def test_equal_weights_are_plain_means_of_ranked_dimensions(self):
        rng = np.random.default_rng(0)
        df = pd.DataFrame({f"r_{d}": rng.random(12) for d in vps.ALL_DIMENSIONS})
        out = vps.compute_weighted_vps(df, {d: 0.2 for d in vps.ALL_DIMENSIONS}, "v")
        np.testing.assert_allclose(out["v"], df[[f"r_{d}" for d in vps.ALL_DIMENSIONS]].mean(axis=1))
        self.assertEqual(vps.ALL_DIMENSIONS,
                         ["proximity", "clinical", "literature", "safety", "molecular"])

    def test_persisted_equal_weight_scores_match_formula(self):
        path = os.path.join(ROOT, "data", "vps_scores_v2.csv")
        if not os.path.exists(path):
            self.skipTest("data/vps_scores_v2.csv not present")
        v = pd.read_csv(path)
        r4 = [f"r_{d}" for d in vps.BASE_DIMENSIONS]
        np.testing.assert_allclose(v["VPS_equal"], v[r4].mean(axis=1), atol=1e-12)
        if "VPS_equal_5d" in v.columns:
            np.testing.assert_allclose(v["VPS_equal_5d"], v[r4 + ["r_molecular"]].mean(axis=1), atol=1e-12)


class TestNoTargetMolecularIsMissing(unittest.TestCase):
    """D-004 / TD-024: no ChEMBL mechanism target is missing evidence, not a measured 0."""

    def test_no_target_is_unranked_and_flagged_but_raw_value_kept(self):
        df = pd.DataFrame({"compound_name": list("ABCD"), "proximity_z": [-1.0, 0.0, 1.0, 2.0],
                           "max_phase_rank": [1, 2, 3, 4], "effective_independent_count": [1, 2, 3, 4],
                           "serious_term_count": [0, 1, 2, 3], "boxed_warning": [False] * 4,
                           "molecular_plausibility_score": [0.0, 0.2, 0.0, 0.6], "n_targets": [0, 3, 2, 5]})
        out = vps.build_standardized_scores(df).set_index("compound_name")
        self.assertEqual(out.loc["A", "r_molecular"], vps.NEUTRAL_RANK)
        self.assertTrue(out.loc["A", "molecular_evidence_missing"])
        self.assertEqual(out.loc["A", "molecular_plausibility_score"], 0.0)
        self.assertEqual(out.loc["A", "dimensions_missing"], "molecular")
        # B, C, D measured (0.2, 0.0, 0.6): ranked among themselves; C's 0.0 is a real measurement.
        self.assertAlmostEqual(out.loc["C", "r_molecular"], 1 / 3)
        self.assertAlmostEqual(out.loc["B", "r_molecular"], 2 / 3)
        self.assertEqual(out.loc["A", "n_dimensions_measured"], 4)


class TestGridSearchSelectsOnTrainingFoldsOnly(unittest.TestCase):
    def test_selection_frames_exclude_the_held_out_fold(self):
        rng = np.random.default_rng(1)
        n = 40
        df = pd.DataFrame({f"r_{d}": rng.random(n) for d in vps.BASE_DIMENSIONS})
        df["label"] = [1] * 10 + [0] * 30
        seen = []
        real = vps._best_weights_on

        def spy(frame, cands):
            seen.append(set(frame.index))
            return real(frame, cands)

        with mock.patch.object(vps, "_best_weights_on", spy):
            vps.cv_grid_search_weights(df, vps.BASE_DIMENSIONS, n_splits=5, step=0.5)
        folds = list(vps.StratifiedKFold(5, shuffle=True, random_state=vps.RANDOM_SEED)
                     .split(df, df["label"]))
        self.assertEqual(len(seen), 6)                       # 5 fold selections + final model
        for chosen, (train, test) in zip(seen[:5], folds):
            self.assertEqual(chosen, set(train))
            self.assertFalse(chosen & set(test))
        self.assertEqual(seen[5], set(range(n)))             # final weights: all data (in-sample)


class TestFigureUncertaintyCaption(unittest.TestCase):
    def test_caption_is_computed_from_persisted_scores(self):
        figs = _load("figs_contract", "07_generate_figures.py")
        from bootstrap_auroc_ci import paired_bootstrap
        rng = np.random.default_rng(3)
        y = np.array([1] * 8 + [0] * 32)
        frame = pd.DataFrame({"label": y, "VPS_equal": rng.random(40),
                              "VPS_equal_5d": rng.random(40) + 0.2 * y})
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "s.csv")
            frame.to_csv(path, index=False)
            note = figs._uncertainty_note(path)
            r = paired_bootstrap(frame["label"], frame["VPS_equal_5d"], frame["VPS_equal"])
            self.assertIn("8 positive / 40", note)
            self.assertIn(f"{r['diff']:+.3f}", note)
            self.assertIn(f"[{r['ci_diff'][0]:+.3f}, {r['ci_diff'][1]:+.3f}]", note)
            self.assertIsNone(figs._uncertainty_note(os.path.join(tmp, "absent.csv")))
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
