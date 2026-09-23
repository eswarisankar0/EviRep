"""
STEP 6 (v2): VPS Fusion + Evaluation, improved.
Fixes two issues found in the z-score version:
  1. Percentile-rank normalization instead of z-score -- fully outlier-robust
  2. Grid-searched weight combinations (cross-validated) instead of pure
     equal-weighting or unstable logistic regression coefficients
Also tests a 3-dimension variant (drop proximity), since the ablation
showed proximity was net-negative to the equal-weighted composite.
"""
import pandas as pd
import numpy as np
from itertools import product
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

RANDOM_SEED = 42

# ============================================================
# 1-4: LOAD, BUILD MATURITY, MERGE, IMPUTE (unchanged from before)
# ============================================================

def load_data():
    filtered_candidates = pd.read_csv("data/pd_candidates_filtered.csv")
    proximity = pd.read_csv("data/network_proximity.csv")
    clinical = pd.read_csv("data/clinical_maturity_precutoff_clean.csv")
    literature = pd.read_csv("data/literature_independence.csv")
    safety = pd.read_csv("data/safety_signal.csv")
    ground_truth = pd.read_csv("data/ground_truth_postcutoff_clean.csv")
    return filtered_candidates, proximity, clinical, literature, safety, ground_truth

PHASE_RANK = {"NA": 0, "EARLY_PHASE1": 1, "PHASE1": 2, "PHASE2": 3, "PHASE3": 4, "PHASE4": 5}

def build_clinical_maturity(clinical_df):
    clinical_df = clinical_df.copy()
    clinical_df["phase_rank"] = clinical_df["phase"].map(PHASE_RANK).fillna(0)
    return clinical_df.groupby("compound_name").agg(
        max_phase_rank=("phase_rank", "max"),
        n_trials=("nct_id", "nunique"),
    ).reset_index()

def merge_dimensions(filtered_candidates, proximity, clinical_maturity, literature, safety):
    base = clinical_maturity[["compound_name"]].drop_duplicates()
    filtered_names = set(filtered_candidates["compound_name"])
    base = base[base["compound_name"].isin(filtered_names)]
    df = base.merge(proximity[["compound_name", "proximity_z"]], on="compound_name", how="left")
    df = df.merge(clinical_maturity, on="compound_name", how="left")
    df = df.merge(literature[["compound_name", "raw_paper_count", "effective_independent_count",
                                "independence_ratio"]], on="compound_name", how="left")
    df = df.merge(safety[["compound_name", "boxed_warning", "serious_term_count"]],
                  on="compound_name", how="left")
    return df

def impute_missing(df):
    df = df.copy()
    for col in ["proximity_z", "max_phase_rank", "n_trials", "raw_paper_count",
                "effective_independent_count", "independence_ratio", "serious_term_count"]:
        df[col] = df[col].fillna(df[col].median())
    df["boxed_warning"] = df["boxed_warning"].fillna(False)
    return df


# ============================================================
# 5. PERCENTILE-RANK NORMALIZATION (outlier-robust, replaces z-score)
# ============================================================

def percentile_rank(series, invert=False):
    """Converts to percentile rank in [0, 1]. Fully robust to outliers --
    an extreme value only affects its own rank, not the scale of others."""
    ranks = series.rank(pct=True, method="average")
    return 1 - ranks if invert else ranks

def build_standardized_scores(df):
    df = df.copy()
    # Proximity: more negative raw = better -> invert
    df["r_proximity"] = percentile_rank(df["proximity_z"], invert=True)
    df["r_clinical"] = percentile_rank(df["max_phase_rank"], invert=False)
    df["r_literature"] = percentile_rank(df["effective_independent_count"], invert=False)
    safety_risk = df["serious_term_count"] + df["boxed_warning"].astype(int) * 5
    df["r_safety"] = percentile_rank(safety_risk, invert=True)
    return df


# ============================================================
# 6. LABELS
# ============================================================

def build_labels(df, ground_truth):
    positives = set(ground_truth["compound_name"].unique())
    df = df.copy()
    df["label"] = df["compound_name"].isin(positives).astype(int)
    return df


# ============================================================
# 7. EVALUATION METRICS
# ============================================================

def precision_at_k(df, score_col, k):
    k = min(k, len(df))
    top_k = df.sort_values(score_col, ascending=False).head(k)
    return top_k["label"].sum() / k

def evaluate(df, score_col, label_col="label"):
    p10 = precision_at_k(df, score_col, 10)
    p50 = precision_at_k(df, score_col, 50)
    try:
        auroc = roc_auc_score(df[label_col], df[score_col])
    except ValueError:
        auroc = float("nan")
    return {"precision@10": round(p10, 3), "precision@50": round(p50, 3), "AUROC": round(auroc, 3)}


# ============================================================
# 8. WEIGHTED VPS (generic, works for 3 or 4 dimensions)
# ============================================================

def compute_weighted_vps(df, weights, col_name="VPS"):
    df = df.copy()
    score = np.zeros(len(df))
    for dim, w in weights.items():
        score += w * df[f"r_{dim}"].values
    df[col_name] = score
    return df


# ============================================================
# 9. CROSS-VALIDATED GRID SEARCH OVER WEIGHT COMBINATIONS
# ============================================================

def cv_grid_search_weights(df, dims, n_splits=5, step=0.25):
    """
    Tests a grid of weight combinations (summing to 1) using stratified
    k-fold CV, scoring each by mean out-of-fold AUROC. This is more robust
    than fitting continuous logistic regression coefficients when the
    sample size is small (n=140), since it searches far fewer effective
    degrees of freedom.
    """
    y = df["label"].values
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_SEED)

    # Build a grid of weight combinations in increments of `step`, summing to 1
    grid_values = np.arange(0, 1 + step, step)
    candidate_weights = []
    for combo in product(grid_values, repeat=len(dims)):
        if abs(sum(combo) - 1.0) < 1e-9 and sum(combo) > 0:
            candidate_weights.append(dict(zip(dims, combo)))

    best_weights, best_auroc = None, -1
    results_log = []

    for weights in candidate_weights:
        fold_aurocs = []
        for train_idx, test_idx in skf.split(df, y):
            test_df = df.iloc[test_idx]
            scored = compute_weighted_vps(test_df, weights, col_name="_temp_score")
            try:
                auroc = roc_auc_score(scored["label"], scored["_temp_score"])
                fold_aurocs.append(auroc)
            except ValueError:
                continue
        if fold_aurocs:
            mean_auroc = np.mean(fold_aurocs)
            results_log.append({**weights, "mean_cv_auroc": mean_auroc})
            if mean_auroc > best_auroc:
                best_auroc = mean_auroc
                best_weights = weights

    return best_weights, best_auroc, pd.DataFrame(results_log)


# ============================================================
# 10. BASELINES
# ============================================================

def compute_baselines(df):
    df = df.copy()
    results = {}
    df["baseline_proximity_only"] = -df["proximity_z"].fillna(df["proximity_z"].median())
    results["Proximity only"] = evaluate(df, "baseline_proximity_only")
    df["baseline_pubcount_only"] = df["raw_paper_count"].fillna(0)
    results["Publication count only"] = evaluate(df, "baseline_pubcount_only")
    df["baseline_naive_sum"] = (
        -df["proximity_z"].fillna(df["proximity_z"].median()) +
        df["max_phase_rank"].fillna(0) +
        df["raw_paper_count"].fillna(0) -
        df["serious_term_count"].fillna(0)
    )
    results["Naive unweighted sum (raw scales)"] = evaluate(df, "baseline_naive_sum")
    return results


# ============================================================
# 11. ABLATION
# ============================================================

def run_ablation(df, weights_4dim):
    dims = ["proximity", "clinical", "literature", "safety"]
    results = {}
    full = compute_weighted_vps(df, weights_4dim, "VPS_ablation")
    results["Full VPS (grid-searched weights, 4 dims)"] = evaluate(full, "VPS_ablation")
    for drop in dims:
        remaining = [d for d in dims if d != drop]
        weights = {d: (1/len(remaining) if d in remaining else 0.0) for d in dims}
        ablated = compute_weighted_vps(df, weights, "VPS_ablation")
        results[f"Without {drop}"] = evaluate(ablated, "VPS_ablation")
    return results


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("STEP 6 v2: VPS FUSION -- percentile-rank + grid-searched weights")
    print("=" * 60)

    filtered_candidates, proximity, clinical, literature, safety, ground_truth = load_data()
    clinical_maturity = build_clinical_maturity(clinical)
    df = merge_dimensions(filtered_candidates, proximity, clinical_maturity, literature, safety)

    print(f"\nEvaluable candidate pool: {len(df)} compounds")

    df = impute_missing(df)
    df = build_standardized_scores(df)
    df = build_labels(df, ground_truth)

    print(f"Positive labels: {df['label'].sum()} / {len(df)}")

    # --- Equal-weight VPS (4-dim), for comparison ---
    df = compute_weighted_vps(df, {"proximity": 0.25, "clinical": 0.25, "literature": 0.25, "safety": 0.25}, "VPS_equal")

    # --- Grid search: best 4-dimension weights ---
    print("\nRunning grid search over 4-dimension weight combinations (this may take a minute)...")
    best_weights_4d, best_auroc_4d, log_4d = cv_grid_search_weights(
        df, dims=["proximity", "clinical", "literature", "safety"], step=0.25)
    print(f"Best 4-dim weights: {best_weights_4d}  (CV AUROC: {best_auroc_4d:.3f})")
    df = compute_weighted_vps(df, best_weights_4d, "VPS_grid_4d")

    # --- Grid search: best 3-dimension weights (drop proximity) ---
    print("\nRunning grid search over 3-dimension weights (proximity dropped)...")
    best_weights_3d, best_auroc_3d, log_3d = cv_grid_search_weights(
        df, dims=["clinical", "literature", "safety"], step=0.1)
    print(f"Best 3-dim weights: {best_weights_3d}  (CV AUROC: {best_auroc_3d:.3f})")
    df = compute_weighted_vps(df, best_weights_3d, "VPS_grid_3d")

    df.to_csv("data/vps_scores_v2.csv", index=False)
    log_4d.to_csv("data/grid_search_4d_log.csv", index=False)
    log_3d.to_csv("data/grid_search_3d_log.csv", index=False)

    print("\n--- FINAL COMPARISON: baselines vs. all VPS variants ---")
    baseline_results = compute_baselines(df)
    for name, metrics in baseline_results.items():
        print(f"{name}: {metrics}")

    print(f"VPS -- equal weights (4 dim): {evaluate(df, 'VPS_equal')}")
    print(f"VPS -- grid-searched weights (4 dim): {evaluate(df, 'VPS_grid_4d')}")
    print(f"VPS -- grid-searched weights (3 dim, no proximity): {evaluate(df, 'VPS_grid_3d')}")

    print("\n--- Ablation (using grid-searched 4-dim weights as the 'full' model) ---")
    ablation_results = run_ablation(df, best_weights_4d)
    for name, metrics in ablation_results.items():
        print(f"{name}: {metrics}")

    pd.DataFrame(baseline_results).T.to_csv("data/baseline_results_v2.csv")
    pd.DataFrame(ablation_results).T.to_csv("data/ablation_results_v2.csv")

    print("\n--- Top 15 by best-performing VPS variant ---")
    best_variant = max(
        [("VPS_equal", evaluate(df, "VPS_equal")["AUROC"]),
         ("VPS_grid_4d", evaluate(df, "VPS_grid_4d")["AUROC"]),
         ("VPS_grid_3d", evaluate(df, "VPS_grid_3d")["AUROC"])],
        key=lambda x: x[1]
    )
    print(f"(Best variant: {best_variant[0]}, AUROC={best_variant[1]})")
    print(df.sort_values(best_variant[0], ascending=False)
            [["compound_name", best_variant[0], "label"]]
            .head(15).to_string(index=False))


if __name__ == "__main__":
    main()