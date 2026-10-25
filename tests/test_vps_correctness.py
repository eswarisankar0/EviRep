"""
VPS correctness (2026-10-15, D-024). Expected values are computed BY HAND in the
comments below, not taken from the implementation under test. Offline.
"""

import importlib.util
import math
import pathlib
import os
import re
import shutil
import tempfile
import unittest

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vps = _load("vps06", "scripts/06_vps_fusion.py")
ver = _load("vpsverify", "scripts/vps_verify.py")


class TestRankConventions(unittest.TestCase):
    def test_legacy_by_hand(self):
        # values -2,-1,0,1 have ranks 1..4 of n=4: rank/n = .25,.5,.75,1 ; inverted 1-rank/n = .75,.5,.25,0
        s = pd.Series([-2.0, -1.0, 0.0, 1.0])
        self.assertEqual(vps.percentile_rank(s, convention="legacy").tolist(), [0.25, 0.5, 0.75, 1.0])
        self.assertEqual(vps.percentile_rank(s, invert=True, convention="legacy").tolist(), [0.75, 0.5, 0.25, 0.0])

    def test_midrank_by_hand_is_symmetric_with_mean_half(self):
        # (rank - .5)/4 = .125,.375,.625,.875 ; inverted = .875,.625,.375,.125 ; both have mean .5
        s = pd.Series([-2.0, -1.0, 0.0, 1.0])
        up = vps.percentile_rank(s, convention="midrank").tolist()
        down = vps.percentile_rank(s, invert=True, convention="midrank").tolist()
        self.assertEqual(up, [0.125, 0.375, 0.625, 0.875])
        self.assertEqual(down, [0.875, 0.625, 0.375, 0.125])
        self.assertAlmostEqual(sum(up) / 4, 0.5)
        self.assertAlmostEqual(sum(down) / 4, 0.5)

    def test_ties_average_and_nan_unranked(self):
        # 1,1,2 -> ranks 1.5,1.5,3 of n=3 -> .5,.5,1 ; NaN stays NaN and does not count in n
        s = pd.Series([1.0, 1.0, 2.0, np.nan])
        r = vps.percentile_rank(s, convention="legacy").tolist()
        self.assertEqual(r[:3], [0.5, 0.5, 1.0])
        self.assertTrue(math.isnan(r[3]))
        self.assertEqual(ver.pct_rank({"a": 1.0, "b": 1.0, "c": 2.0, "d": None}), {"a": 0.5, "b": 0.5, "c": 1.0})

    def test_unknown_convention_rejected(self):
        with self.assertRaises(ValueError):
            vps.percentile_rank(pd.Series([1.0]), convention="zscore")


def frames(prox=(-1.0, 0.0, 1.0), dup=None):
    names = ["A", "B", "C"]
    fc = pd.DataFrame({"compound_name": names})
    p = pd.DataFrame({"compound_name": names, "proximity_z": list(prox)})
    if dup:
        p = pd.concat([p, p[p.compound_name == dup]])
    cm = pd.DataFrame({"compound_name": names, "max_phase_rank": [1.0, 2.0, 3.0], "n_trials": [1, 1, 1]})
    lit = pd.DataFrame({"compound_name": names, "raw_paper_count": [3, 3, 3], "effective_independent_count": [1.0, 2.0, 3.0],
                        "independence_ratio": [1, 1, 1]})
    saf = pd.DataFrame({"compound_name": names, "has_label": [True, True, False], "boxed_warning": [True, False, None],
                        "serious_term_count": [0.0, 2.0, None]})
    mol = pd.DataFrame({"compound_name": names, "molecular_plausibility_score": [0.2, 0.0, 0.9], "confidence": [1, 1, 1],
                        "n_targets": [2, 0, 3]})
    return fc, p, cm, lit, saf, mol


def score(prox=(-1.0, 0.0, 1.0)):
    df = vps.merge_dimensions(*frames(prox))
    df = vps.impute_missing(df)
    df, _ = vps.impute_molecular(df)
    df = vps.build_standardized_scores(df)
    df = vps.compute_weighted_vps(df, {d: 0.2 for d in vps.ALL_DIMENSIONS}, "VPS_equal_5d")
    return df.set_index("compound_name")


class TestFusionByHand(unittest.TestCase):
    def test_three_compound_example(self):
        d = score()
        # proximity -1,0,1 inverted legacy: 1-1/3, 1-2/3, 0      clinical 1,2,3: 1/3, 2/3, 1
        # literature 1,2,3: 1/3, 2/3, 1
        # safety risk A = 0 + 5 (boxed) = 5, B = 2, C no label -> ranked among A,B: B rank 1, A rank 2 of 2
        #   inverted: B = 1 - 1/2 = .5, A = 1 - 2/2 = 0, C neutral .5 (missing)
        # molecular: B has no target -> missing (neutral .5); A .2 rank 1, C .9 rank 2 of 2 -> .5, 1
        exp = {"A": [2 / 3, 1 / 3, 1 / 3, 0.0, 0.5], "B": [1 / 3, 2 / 3, 2 / 3, 0.5, 0.5], "C": [0.0, 1.0, 1.0, 0.5, 1.0]}
        for c, vals in exp.items():
            got = [d.loc[c, f"r_{k}"] for k in ("proximity", "clinical", "literature", "safety", "molecular")]
            for g, e in zip(got, vals):
                self.assertAlmostEqual(g, e)
            self.assertAlmostEqual(d.loc[c, "VPS_equal_5d"], sum(vals) / 5)
        self.assertEqual(d.loc["C", "dimensions_missing"], "safety")
        self.assertEqual(d.loc["B", "dimensions_missing"], "molecular")
        self.assertEqual(d.loc["A", "n_dimensions_measured"], 5)

    def test_nonfinite_is_not_computed_and_flagged(self):
        d = score(prox=(-1.0, float("inf"), 1.0))
        # B's +inf is treated as missing -> pool median of (-1, 1) = 0 -> same ranks as the example above
        self.assertEqual(d.loc["B", "dimensions_imputed"], "proximity")
        self.assertAlmostEqual(d.loc["B", "r_proximity"], 1 / 3)
        self.assertEqual(d.loc["B", "n_dimensions_measured"], 3)   # molecular neutral + proximity imputed

    def test_duplicate_input_row_refused(self):
        with self.assertRaises(ValueError):
            vps.merge_dimensions(*frames(dup="A"))

    def test_changing_one_input_moves_only_that_dimension(self):
        a, b = score(), score(prox=(1.5, 0.0, 1.0))           # A goes from closest to farthest
        for col in ("r_clinical", "r_literature", "r_safety", "r_molecular"):
            self.assertTrue((a[col] == b[col]).all(), col)
        self.assertAlmostEqual(b.loc["A", "r_proximity"], 0.0)
        self.assertAlmostEqual(b.loc["B", "r_proximity"], 2 / 3)


class TestBaselineIntegrity(unittest.TestCase):
    def test_independent_recompute_matches_saved_baseline(self):
        if not os.path.exists(os.path.join(ROOT, "data/vps_scores_v2.csv")):
            self.skipTest("no baseline")
        expected, imputed = ver.recompute(ROOT)
        res = ver.compare(expected, os.path.join(ROOT, "data/vps_scores_v2.csv"))
        self.assertTrue(res["ok"], res["problems"][:5])
        self.assertLess(res["max_abs_diff"], 1e-12)
        self.assertEqual(imputed["proximity"], ["Deferiprone", "Trimethobenzamide"])

    def test_verifier_detects_a_perturbed_score(self):
        tmp = tempfile.mkdtemp()
        try:
            s = pd.read_csv(os.path.join(ROOT, "data/vps_scores_v2.csv"))
            s.loc[0, "VPS_equal_5d"] += 1e-6
            p = os.path.join(tmp, "s.csv")
            s.to_csv(p, index=False)
            expected, _ = ver.recompute(ROOT)
            self.assertFalse(ver.compare(expected, p)["ok"])
        finally:
            shutil.rmtree(tmp)


class TestIsolation(unittest.TestCase):
    """Labels and diagnostic-agent outputs must not reach the features."""

    def test_feature_stages_never_read_post_cutoff_labels(self):
        for rel in ("scripts/02_network_proximity.py", "scripts/04_literature_independence.py",
                    "scripts/05_safety_signal.py", "scripts/08_molecular_pathway.py", "scripts/molecular_agent.py"):
            self.assertNotIn("ground_truth", pathlib.Path(os.path.join(ROOT, rel)).read_text(), rel)

    def test_stage06_reads_only_registered_inputs(self):
        src = pathlib.Path(os.path.join(ROOT, "scripts/06_vps_fusion.py")).read_text()
        read = set(re.findall(r'"(data/[^"]+\.(?:csv|json|jsonl))"', src))
        allowed = {"data/pd_candidates_filtered.csv", "data/network_proximity.csv",
                   "data/clinical_maturity_precutoff_clean.csv", "data/literature_independence.csv",
                   "data/safety_signal.csv", "data/ground_truth_postcutoff_clean.csv", "data/molecular_pathway.csv",
                   "data/label_role_exclusions.csv", "data/feature_role_exclusions.csv",
                   # outputs written by stage 06 (via _write_csv)
                   "data/vps_scores_v2.csv", "data/grid_search_3d_log.csv", "data/grid_search_4d_log.csv",
                   "data/grid_search_5d_log.csv", "data/baseline_results_v2.csv", "data/ablation_results_v2.csv",
                   "data/ablation_results_5d.csv", "data/vps_variant_results.csv"}
        self.assertLessEqual(read, allowed, sorted(read - allowed))
        for diag in ("clinical_evidence.json", "safety_evidence.json", "evidence_independence.json",
                     "completeness_gaps.json", "conflict_context.json", "reproducibility.json", "literature_credibility"):
            self.assertNotIn(diag, src)

    def test_ground_truth_only_used_for_labels_and_after_features(self):
        src = pathlib.Path(os.path.join(ROOT, "scripts/06_vps_fusion.py")).read_text()
        body = src[src.index("def main():"):]
        uses = [l.strip() for l in body.splitlines() if re.search(r"\bground_truth\b", l)]
        self.assertEqual(len(uses), 3, uses)               # load, label exclusions, build_labels - nothing else
        self.assertTrue(uses[0].startswith("filtered_candidates, proximity, clinical, literature, safety, ground_truth"))
        self.assertIn("apply_label_exclusions(ground_truth", uses[1])
        self.assertTrue(uses[2].startswith("df = build_labels(df, ground_truth)"))
        # labels are attached only after every feature/standardisation step
        self.assertLess(body.index("df = build_standardized_scores(df)"), body.index("df = build_labels(df, ground_truth)"))

if __name__ == "__main__":
    unittest.main()
