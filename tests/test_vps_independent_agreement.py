"""The production scoring function agrees with an independent implementation (audit 2026-10-21).

Tolerance: 1e-12 absolute. The two implementations differ only in floating-point summation order (observed max
difference 2.2e-16 on the approved data); 1e-12 is four orders above that and far below any displayed precision
(3 decimals). The independent ranks are written from the specification (average-tie percentile rank over the
non-missing values; inverted dimensions = 1 - rank; unmeasured safety/molecular = 0.5), not copied from production.
"""
import importlib.util
import math
import os
import unittest

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("evirep_06_agree", os.path.join(ROOT, "scripts", "06_vps_fusion.py"))
fusion = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fusion)
TOL = 1e-12
SCORES = os.path.join(ROOT, "data", "vps_scores_v2.csv")


def pct_rank(values):
    """Average-tie percentile rank among non-missing values (1-based rank / count); NaN stays NaN."""
    idx = [i for i, v in enumerate(values) if not math.isnan(v)]
    order = sorted(idx, key=lambda i: values[i])
    out, k = [math.nan] * len(values), 0
    while k < len(order):
        j = k
        while j + 1 < len(order) and values[order[j + 1]] == values[order[k]]:
            j += 1
        for t in range(k, j + 1):
            out[order[t]] = ((k + 1 + j + 1) / 2) / len(order)
        k = j + 1
    return out


def independent_vps(df):
    def col(name): return [float(x) for x in df[name]]
    safety = [math.nan if miss else s + 5 * bool(b) for s, b, miss in zip(col("serious_term_count"), df["boxed_warning"], df["safety_label_missing"])]
    mol = [math.nan if n == 0 else m for m, n in zip(col("molecular_plausibility_score"), col("n_targets"))]
    dims = {"proximity": (col("proximity_z"), True), "clinical": (col("max_phase_rank"), False),
            "literature": (col("effective_independent_count"), False), "safety": (safety, True), "molecular": (mol, False)}
    ranks = {}
    for d, (vals, inv) in dims.items():
        r = pct_rank(vals)
        ranks[d] = [0.5 if math.isnan(x) else (1 - x if inv else x) for x in r]
    return ranks, [sum(ranks[d][i] for d in dims) / 5 for i in range(len(df))]


def production_input(df):
    """The raw columns stage 06 ranks, with unmeasured safety as NaN exactly as stage 06 prepares them."""
    x = df.copy()
    x.loc[x["safety_label_missing"].astype(str) == "True", "serious_term_count"] = np.nan
    x["boxed_warning"] = x["boxed_warning"].astype(str).map({"True": True, "False": False})
    return x[["compound_name", "proximity_z", "max_phase_rank", "effective_independent_count", "boxed_warning",
              "serious_term_count", "molecular_plausibility_score", "n_targets"]]


@unittest.skipUnless(os.path.exists(SCORES), "needs the approved scores")
class TestProductionAgreesWithIndependent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = pd.read_csv(SCORES)
        cls.saved["safety_label_missing"] = cls.saved["safety_label_missing"].astype(str) == "True"
        cls.prod = fusion.build_standardized_scores(production_input(cls.saved))
        cls.ind_ranks, cls.ind_vps = independent_vps(cls.saved)

    def test_every_rank_agrees(self):
        for d in ("proximity", "clinical", "literature", "safety", "molecular"):
            diff = np.abs(self.prod["r_" + d].to_numpy() - np.array(self.ind_ranks[d])).max()
            self.assertLess(diff, TOL, d)

    def test_total_agrees_with_production_and_saved(self):
        prod_vps = self.prod[[f"r_{d}" for d in ("proximity", "clinical", "literature", "safety", "molecular")]].mean(axis=1).to_numpy()
        self.assertLess(np.abs(prod_vps - np.array(self.ind_vps)).max(), TOL)
        self.assertLess(np.abs(self.saved["VPS_equal_5d"].to_numpy() - np.array(self.ind_vps)).max(), TOL)

    def test_missingness_flags_agree(self):
        self.assertEqual(list(self.prod["dimensions_missing"].fillna("")), list(self.saved["dimensions_missing"].fillna("")))

    def test_ordering_is_deterministic_and_unique(self):
        a = fusion.build_standardized_scores(production_input(self.saved))
        self.assertTrue(a.equals(self.prod))
        self.assertEqual(len(set(np.round(self.ind_vps, 15))), len(self.saved))        # no ties in the approved ordering
        self.assertFalse(self.saved["compound_name"].duplicated().any())

    def test_all_scores_finite_and_in_range(self):
        v = np.array(self.ind_vps)
        self.assertTrue(np.isfinite(v).all() and (v >= 0).all() and (v <= 1).all())


class TestEdgeCases(unittest.TestCase):
    def _df(self, **cols):
        n = len(next(iter(cols.values())))
        base = {"compound_name": [f"c{i}" for i in range(n)], "proximity_z": [0.0] * n, "max_phase_rank": [1.0] * n,
                "effective_independent_count": [1.0] * n, "boxed_warning": [False] * n, "serious_term_count": [0.0] * n,
                "molecular_plausibility_score": [0.5] * n, "n_targets": [1] * n, "safety_label_missing": [False] * n}
        base.update(cols)
        return pd.DataFrame(base)

    def test_all_tied_gives_identical_scores(self):
        df = self._df(proximity_z=[1.0, 1.0, 1.0])
        out = fusion.build_standardized_scores(production_input(df))
        self.assertEqual(out["r_proximity"].nunique(), 1)

    def test_missing_target_and_label_get_neutral_half_not_extremes(self):
        df = self._df(n_targets=[0, 1, 1], molecular_plausibility_score=[0.0, 0.2, 0.9],
                      safety_label_missing=[True, False, False], serious_term_count=[0.0, 3.0, 1.0])
        out = fusion.build_standardized_scores(production_input(df))
        self.assertEqual(out.loc[0, "r_molecular"], 0.5)
        self.assertEqual(out.loc[0, "r_safety"], 0.5)
        self.assertEqual(out.loc[0, "dimensions_missing"], "safety|molecular")
        ranks, _ = independent_vps(df)
        self.assertEqual(ranks["molecular"][0], 0.5)

    def test_single_compound(self):
        out = fusion.build_standardized_scores(production_input(self._df(proximity_z=[2.0])))
        self.assertEqual(out.loc[0, "r_clinical"], 1.0)
        self.assertEqual(out.loc[0, "r_proximity"], 0.0)            # inverted legacy rank of the only value

    def test_infinite_raw_value_never_escapes_the_unit_interval(self):
        # The ranking step alone treats +inf as the farthest value (rank 0 after inversion, never NaN or > 1). The real
        # guard is upstream: stage 06's merge turns non-finite raw values into "not computed" before ranking
        # (06_vps_fusion.py, `vals.where(np.isfinite(vals))`; tested in test_vps_correctness::test_nonfinite_is_not_computed_and_flagged).
        df = self._df(proximity_z=[float("inf"), 0.0, -1.0])
        out = fusion.build_standardized_scores(production_input(df))
        self.assertEqual(out.loc[0, "r_proximity"], 0.0)
        self.assertTrue(((out["r_proximity"] >= 0) & (out["r_proximity"] <= 1)).all())


if __name__ == "__main__":
    unittest.main()
