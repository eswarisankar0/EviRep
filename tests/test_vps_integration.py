"""
Integration tests for the molecular dimension inside the VPS fusion step.

Run:  ./venv/bin/python -m unittest discover -s tests -v

No network, no reads from the project's data/ directory, and nothing written to
it. Synthetic frames below match the column schemas that scripts 00-05 and 08
actually emit (taken from their `to_csv` calls).

The most important test here is
`TestNoSilentChange.test_four_dim_scores_identical_with_and_without_molecular`:
adding dimension 5 must not alter any previously reported 4-dimension number.
"""

import importlib.util
import os
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_step06():
    """Load scripts/06_vps_fusion.py — its name starts with a digit, so it
    cannot be imported normally."""
    path = os.path.join(ROOT, "scripts", "06_vps_fusion.py")
    spec = importlib.util.spec_from_file_location("step06_vps_fusion", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["step06_vps_fusion"] = module
    spec.loader.exec_module(module)
    return module


vps = _load_step06()


# ============================================================================
# SYNTHETIC FRAMES (schemas mirror the real pipeline outputs)
# ============================================================================

# 40 compounds / 12 positives: large enough for StratifiedKFold(n_splits=5) to
# produce folds containing both classes. With only 12/4 every fold degenerated
# to a single class, AUROC was undefined everywhere and the grid search
# correctly found no usable weights -- a fixture limit, not a pipeline bug.
N_COMPOUNDS = 40
N_POSITIVES = 12
COMPOUNDS = [f"Compound{i:02d}" for i in range(1, N_COMPOUNDS + 1)]


def _candidates():
    return pd.DataFrame({
        "compound_id": [f"Compound::C{i:02d}" for i in range(1, N_COMPOUNDS + 1)],
        "compound_name": COMPOUNDS,
        "disease_id": "Disease::DOID:14330",
        "disease_name": "Parkinson's disease",
        "existing_edge_type": "predicted_only",
    })


def _proximity():
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "compound_id": [f"Compound::C{i:02d}" for i in range(1, N_COMPOUNDS + 1)],
        "compound_name": COMPOUNDS,
        "n_targets": rng.integers(1, 20, len(COMPOUNDS)),
        "n_targets_in_network": rng.integers(1, 15, len(COMPOUNDS)),
        "d_real": rng.uniform(1, 4, len(COMPOUNDS)),
        "d_rand_mean": rng.uniform(1, 4, len(COMPOUNDS)),
        "d_rand_std": rng.uniform(0.1, 1, len(COMPOUNDS)),
        "proximity_z": np.linspace(-2.5, 1.5, len(COMPOUNDS)),
        "n_random": 100,
    })


def _clinical():
    phases = ["PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA", "EARLY_PHASE1"]
    rows = []
    for i, name in enumerate(COMPOUNDS):
        for t in range(1 + i % 3):
            rows.append({
                "compound_id": f"Compound::C{i+1:02d}", "compound_name": name,
                "nct_id": f"NCT{i:03d}{t}", "phase": phases[i % len(phases)],
                "status": "COMPLETED", "enrollment": 50 + i,
                "first_posted": "2019-05-01",
            })
    return pd.DataFrame(rows)


def _literature():
    return pd.DataFrame({
        "compound_name": COMPOUNDS,
        "raw_paper_count": np.arange(1, N_COMPOUNDS + 1) * 3,
        "effective_independent_count": np.arange(1, N_COMPOUNDS + 1),
        "independence_ratio": np.linspace(0.1, 0.9, N_COMPOUNDS),
        "edges_shared_author": 0, "edges_citation": 0,
    })


def _safety():
    return pd.DataFrame({
        "compound_name": COMPOUNDS,
        "has_label": True,
        "boxed_warning": [i % 4 == 0 for i in range(N_COMPOUNDS)],
        "serious_term_count": np.arange(N_COMPOUNDS),
    })


def _ground_truth():
    # Positives: a deterministic subset, so labels are stable across runs.
    positives = COMPOUNDS[:N_POSITIVES]
    return pd.DataFrame({
        "compound_id": [f"Compound::C{i+1:02d}" for i in range(N_POSITIVES)],
        "compound_name": positives,
        "nct_id": [f"NCT9{i:03d}" for i in range(N_POSITIVES)],
        "phase": "PHASE2", "status": "RECRUITING",
        "enrollment": 60, "first_posted": "2022-03-01",
    })


def _molecular(subset=None, with_nan=False):
    """Mirrors scripts/08_molecular_pathway.py CSV_COLUMNS."""
    names = subset if subset is not None else COMPOUNDS
    n = len(names)
    scores = np.linspace(0.0, 0.8, n)
    frame = pd.DataFrame({
        "compound_name": names,
        "chembl_id": [f"CHEMBL{i}" for i in range(n)],
        "resolved": True,
        "molecular_plausibility_score": scores,
        "confidence": [1.0] * n,
        "direct_component": scores,
        "pathway_component": scores,
        "n_targets": 3,
        "n_genes": 3,
        "n_pathways": 6,
        "n_pathways_in_disease_module": 2,
        "n_direct_disease_links": 1,
        "n_evidence_direct": 3,
        "n_evidence_indirect": 2,
        "n_evidence_inferred": 1,
        "n_evidence_missing": 0,
        "n_limitations": 5,
    })
    if with_nan:
        frame.loc[0, "molecular_plausibility_score"] = np.nan
    return frame


def build_df(molecular=None):
    """Run the real step-06 pipeline functions over synthetic inputs."""
    clinical_maturity = vps.build_clinical_maturity(_clinical())
    df = vps.merge_dimensions(_candidates(), _proximity(), clinical_maturity,
                              _literature(), _safety(), molecular)
    df = vps.impute_missing(df)
    if molecular is not None:
        df, _ = vps.impute_molecular(df)
    df = vps.build_standardized_scores(df)
    df = vps.build_labels(df, _ground_truth())
    return df


# ============================================================================
# REGISTRY / LOADING
# ============================================================================


class TestRegistry(unittest.TestCase):
    def test_dimension_registry_shape(self):
        self.assertEqual(vps.BASE_DIMENSIONS,
                         ["proximity", "clinical", "literature", "safety"])
        self.assertEqual(vps.ALL_DIMENSIONS,
                         ["proximity", "clinical", "literature", "safety", "molecular"])

    def test_load_molecular_absent_returns_none(self):
        self.assertIsNone(vps.load_molecular("data/__definitely_absent__.csv"))

    def test_load_molecular_rejects_bad_schema(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "m.csv")
            pd.DataFrame({"compound_name": ["A"]}).to_csv(path, index=False)
            with self.assertRaises(ValueError):
                vps.load_molecular(path)

    def test_load_molecular_accepts_real_schema(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "m.csv")
            _molecular().to_csv(path, index=False)
            frame = vps.load_molecular(path)
            self.assertEqual(len(frame), N_COMPOUNDS)


# ============================================================================
# MERGE / IMPUTE / STANDARDISE
# ============================================================================


class TestMergeAndStandardise(unittest.TestCase):
    def test_merge_adds_molecular_columns(self):
        df = build_df(_molecular())
        for col in ("molecular_plausibility_score", "molecular_confidence"):
            self.assertIn(col, df.columns)

    def test_merge_without_molecular_omits_columns(self):
        df = build_df(None)
        self.assertNotIn("molecular_plausibility_score", df.columns)
        self.assertNotIn("r_molecular", df.columns)

    def test_r_molecular_created_and_in_unit_interval(self):
        df = build_df(_molecular())
        self.assertIn("r_molecular", df.columns)
        self.assertTrue(((df["r_molecular"] >= 0) & (df["r_molecular"] <= 1)).all())

    def test_higher_molecular_score_gets_higher_rank(self):
        df = build_df(_molecular()).sort_values("molecular_plausibility_score")
        ranks = df["r_molecular"].tolist()
        self.assertEqual(ranks, sorted(ranks), "r_molecular must not be inverted")

    def test_partial_coverage_is_imputed_and_counted(self):
        """Compounds absent from molecular_pathway.csv are median-imputed, and
        the count is returned rather than hidden."""
        partial = _molecular(subset=COMPOUNDS[: N_COMPOUNDS - 4])
        clinical_maturity = vps.build_clinical_maturity(_clinical())
        df = vps.merge_dimensions(_candidates(), _proximity(), clinical_maturity,
                                  _literature(), _safety(), partial)
        df = vps.impute_missing(df)
        df, n_imputed = vps.impute_molecular(df)
        self.assertEqual(n_imputed, 4)
        self.assertFalse(df["molecular_plausibility_score"].isna().any())

    def test_measured_zero_is_not_treated_as_missing(self):
        """A 0.0 produced by the agent is a real measurement and must survive
        imputation unchanged."""
        mol = _molecular()
        mol.loc[:, "molecular_plausibility_score"] = 0.0
        clinical_maturity = vps.build_clinical_maturity(_clinical())
        df = vps.merge_dimensions(_candidates(), _proximity(), clinical_maturity,
                                  _literature(), _safety(), mol)
        df = vps.impute_missing(df)
        df, n_imputed = vps.impute_molecular(df)
        self.assertEqual(n_imputed, 0)
        self.assertTrue((df["molecular_plausibility_score"] == 0.0).all())

    def test_impute_molecular_noop_without_column(self):
        df = build_df(None)
        out, n = vps.impute_molecular(df)
        self.assertEqual(n, 0)
        self.assertNotIn("molecular_plausibility_score", out.columns)


# ============================================================================
# THE CRITICAL GUARANTEE: NO SILENT CHANGE TO EXISTING RESULTS
# ============================================================================


class TestNoSilentChange(unittest.TestCase):
    def test_four_dim_scores_identical_with_and_without_molecular(self):
        weights = {"proximity": 0.25, "clinical": 0.25,
                   "literature": 0.25, "safety": 0.25}
        without = vps.compute_weighted_vps(build_df(None), weights, "VPS_equal")
        with_mol = vps.compute_weighted_vps(build_df(_molecular()), weights, "VPS_equal")
        merged = without[["compound_name", "VPS_equal"]].merge(
            with_mol[["compound_name", "VPS_equal"]], on="compound_name",
            suffixes=("_a", "_b"))
        self.assertEqual(len(merged), len(COMPOUNDS))
        pd.testing.assert_series_equal(
            merged["VPS_equal_a"], merged["VPS_equal_b"], check_names=False)

    def test_existing_four_dim_rank_columns_unchanged(self):
        a, b = build_df(None), build_df(_molecular())
        for col in ("r_proximity", "r_clinical", "r_literature", "r_safety"):
            merged = a[["compound_name", col]].merge(
                b[["compound_name", col]], on="compound_name", suffixes=("_a", "_b"))
            pd.testing.assert_series_equal(
                merged[f"{col}_a"], merged[f"{col}_b"], check_names=False)

    def test_ablation_default_is_still_four_dimensional(self):
        """Default call signature must reproduce the original behaviour."""
        df = build_df(None)
        weights = {d: 0.25 for d in vps.BASE_DIMENSIONS}
        results = vps.run_ablation(df, weights)
        self.assertIn("Full VPS (grid-searched weights, 4 dims)", results)
        self.assertEqual(
            sorted(k for k in results if k.startswith("Without ")),
            ["Without clinical", "Without literature", "Without proximity",
             "Without safety"])

    def test_labels_unaffected_by_new_dimension(self):
        a, b = build_df(None), build_df(_molecular())
        self.assertEqual(a["label"].sum(), b["label"].sum())


# ============================================================================
# 5-DIMENSION FUSION
# ============================================================================


class TestFiveDimensionFusion(unittest.TestCase):
    def setUp(self):
        self.df = build_df(_molecular())

    def test_equal_weight_five_dim_scores_computed(self):
        weights = {d: 0.2 for d in vps.ALL_DIMENSIONS}
        out = vps.compute_weighted_vps(self.df, weights, "VPS_equal_5d")
        self.assertIn("VPS_equal_5d", out.columns)
        self.assertFalse(out["VPS_equal_5d"].isna().any())
        # Weights sum to 1 and each rank is in [0,1], so the score must be too.
        self.assertTrue(((out["VPS_equal_5d"] >= 0) &
                         (out["VPS_equal_5d"] <= 1)).all())

    def test_five_dim_score_equals_manual_weighted_sum(self):
        weights = {d: 0.2 for d in vps.ALL_DIMENSIONS}
        out = vps.compute_weighted_vps(self.df, weights, "S")
        manual = sum(0.2 * self.df[f"r_{d}"] for d in vps.ALL_DIMENSIONS)
        np.testing.assert_allclose(out["S"].values, manual.values)

    def test_molecular_only_variant_is_just_the_molecular_rank(self):
        weights = {d: (1.0 if d == "molecular" else 0.0) for d in vps.ALL_DIMENSIONS}
        out = vps.compute_weighted_vps(self.df, weights, "M")
        np.testing.assert_allclose(out["M"].values, self.df["r_molecular"].values)

    def test_grid_search_handles_five_dimensions(self):
        best, auroc, log = vps.cv_grid_search_weights(
            self.df, dims=vps.ALL_DIMENSIONS, step=0.25)
        self.assertIsNotNone(best)
        self.assertEqual(set(best), set(vps.ALL_DIMENSIONS))
        self.assertAlmostEqual(sum(best.values()), 1.0, places=9)
        self.assertGreater(len(log), 0)

    def test_five_dim_ablation_has_one_row_per_dimension(self):
        weights = {d: 0.2 for d in vps.ALL_DIMENSIONS}
        results = vps.run_ablation(weights_full=weights, df=self.df,
                                   dims=vps.ALL_DIMENSIONS)
        self.assertIn("Full VPS (grid-searched weights, 5 dims)", results)
        self.assertIn("Without molecular", results)
        self.assertEqual(len([k for k in results if k.startswith("Without ")]), 5)

    def test_ablation_metrics_are_well_formed(self):
        weights = {d: 0.2 for d in vps.ALL_DIMENSIONS}
        results = vps.run_ablation(self.df, weights, dims=vps.ALL_DIMENSIONS)
        for name, metrics in results.items():
            self.assertIn("AUROC", metrics)
            self.assertIn("precision@10", metrics)

    def test_evaluate_returns_finite_auroc(self):
        weights = {d: 0.2 for d in vps.ALL_DIMENSIONS}
        out = vps.compute_weighted_vps(self.df, weights, "S")
        metrics = vps.evaluate(out, "S")
        self.assertFalse(np.isnan(metrics["AUROC"]))
        self.assertTrue(0.0 <= metrics["AUROC"] <= 1.0)


# ============================================================================
# DETERMINISM
# ============================================================================


class TestGridSearchNoLeakage(unittest.TestCase):
    """TD-003: cv_grid_search_weights previously bound `train_idx` but never used
    it -- every candidate weight vector was scored on each TEST fold and the max
    taken, so selection saw the data it was measured on."""

    def _noise_df(self, n=120, seed=0):
        """Labels independent of every feature. An honest estimator must land
        near 0.5; an in-sample maximiser will not."""
        rng = np.random.default_rng(seed)
        df = pd.DataFrame({f"r_{d}": rng.random(n) for d in vps.ALL_DIMENSIONS})
        df["label"] = rng.integers(0, 2, n)
        df["compound_name"] = [f"C{i}" for i in range(n)]
        return df

    def test_train_fold_is_actually_used(self):
        import inspect
        src = inspect.getsource(vps.cv_grid_search_weights)
        self.assertIn("train_idx", src)
        self.assertIn("df.iloc[train_idx]", src,
                      "weights must be selected on the training fold")

    def test_nested_estimate_is_lower_than_in_sample_on_pure_noise(self):
        """The core leakage assertion: with labels independent of all features,
        selecting on the full data inflates AUROC, nested CV does not."""
        df = self._noise_df()
        best, nested, log = vps.cv_grid_search_weights(
            df, dims=vps.ALL_DIMENSIONS, step=0.25)
        in_sample = log["selected_model_in_sample_auroc"].iloc[0]
        self.assertGreater(in_sample, nested,
                           "in-sample selection must be optimistic vs nested CV")
        self.assertLess(nested, in_sample - 0.02)

    def test_nested_estimate_near_chance_on_pure_noise(self):
        df = self._noise_df(seed=7)
        _, nested, _ = vps.cv_grid_search_weights(df, dims=vps.ALL_DIMENSIONS, step=0.25)
        self.assertLess(abs(nested - 0.5), 0.20,
                        f"nested CV on noise should be near chance, got {nested}")

    def test_log_separates_in_sample_from_nested(self):
        df = self._noise_df()
        _, nested, log = vps.cv_grid_search_weights(df, dims=vps.ALL_DIMENSIONS, step=0.25)
        for col in ("in_sample_auroc_full_data", "nested_cv_auroc_for_selected_model",
                    "selected_model_in_sample_auroc", "n_cv_folds_used"):
            self.assertIn(col, log.columns)
        self.assertAlmostEqual(log["nested_cv_auroc_for_selected_model"].iloc[0],
                               nested, places=12)

    def test_returned_weights_still_valid(self):
        df = self._noise_df()
        best, _, _ = vps.cv_grid_search_weights(df, dims=vps.ALL_DIMENSIONS, step=0.25)
        self.assertEqual(set(best), set(vps.ALL_DIMENSIONS))
        self.assertAlmostEqual(sum(best.values()), 1.0, places=9)

    def test_equal_weight_path_untouched(self):
        """Equal-weight variants involve no selection and must be unaffected."""
        df = build_df(_molecular())
        w = {d: 0.2 for d in vps.ALL_DIMENSIONS}
        a = vps.compute_weighted_vps(df, w, "S")["S"].values
        manual = sum(0.2 * df[f"r_{d}"] for d in vps.ALL_DIMENSIONS).values
        np.testing.assert_allclose(a, manual)


class TestDeterminism(unittest.TestCase):
    def test_pipeline_is_deterministic(self):
        a = build_df(_molecular())["r_molecular"].tolist()
        b = build_df(_molecular())["r_molecular"].tolist()
        self.assertEqual(a, b)

    def test_grid_search_is_deterministic(self):
        df = build_df(_molecular())
        b1, a1, _ = vps.cv_grid_search_weights(df, dims=vps.ALL_DIMENSIONS, step=0.25)
        b2, a2, _ = vps.cv_grid_search_weights(df, dims=vps.ALL_DIMENSIONS, step=0.25)
        self.assertEqual(b1, b2)
        self.assertAlmostEqual(a1, a2, places=12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
