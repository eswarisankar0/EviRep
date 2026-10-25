"""
STEP 6 (v2): VPS Fusion + Evaluation, improved.
Fixes two issues found in the z-score version:
  1. Percentile-rank normalization instead of z-score -- fully outlier-robust
  2. Grid-searched weight combinations (cross-validated) instead of pure
     equal-weighting or unstable logistic regression coefficients
Also tests a 3-dimension variant (drop proximity), since the ablation
showed proximity was net-negative to the equal-weighted composite.
"""
import os
import pandas as pd
import numpy as np
from itertools import product
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

RANDOM_SEED = 42

#: Where outputs are written. A tracked run (scripts/run_stage.py) points this at a staging directory,
#: validates the result, and only then publishes into data/ (atomic, previous version kept).
OUTPUT_DIR = "data"

#: Percentile-rank convention (VPS verification 2026-10-15, D-024):
#:   "legacy" - rank/n, and 1 - rank/n for "lower is better": higher-is-better dimensions span
#:              [1/n, 1], lower-is-better ones [0, 1 - 1/n]. Reproduces the published baseline.
#:   "midrank" - (rank - 0.5)/n, mirrored for "lower is better": both directions span
#:              [0.5/n, 1 - 0.5/n] with mean 0.5, so the neutral rank 0.5 is the true midpoint.
#: The default stays "legacy" until the owner approves replacing the baseline (D-024).
RANK_CONVENTION = "legacy"


def _write_csv(df, rel, **kw):
    """Atomic write of data/<file> into OUTPUT_DIR: a reader never sees a half-written file."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, os.path.basename(rel))
    df.to_csv(path + ".tmp", **kw)
    os.replace(path + ".tmp", path)

# ============================================================
# DIMENSION REGISTRY
# ============================================================
# Added when the molecular/pathway agent became dimension 5. Previously the
# four dimensions were hardcoded in six separate places (load, merge, impute,
# standardise, grid search, ablation), so adding one meant editing all of them.
# A future evidence agent should only need a new entry here plus a loader.
#
# `invert=True` means "a LOWER raw value is better", so the percentile rank is
# flipped (proximity_z and safety risk are both better when low).

BASE_DIMENSIONS = ["proximity", "clinical", "literature", "safety"]
MOLECULAR_DIMENSION = "molecular"

#: Dimensions used by the 5-dimension variants. Order is fixed for determinism.
ALL_DIMENSIONS = BASE_DIMENSIONS + [MOLECULAR_DIMENSION]

#: Optional dimension files. A missing file degrades to the 4-dimension model
#: rather than failing, so the original pipeline still runs end to end.
MOLECULAR_CSV = "data/molecular_pathway.csv"


def load_data():
    filtered_candidates = pd.read_csv("data/pd_candidates_filtered.csv")
    proximity = pd.read_csv("data/network_proximity.csv")
    clinical = pd.read_csv("data/clinical_maturity_precutoff_clean.csv")
    literature = pd.read_csv("data/literature_independence.csv")
    safety = pd.read_csv("data/safety_signal.csv")
    ground_truth = pd.read_csv("data/ground_truth_postcutoff_clean.csv")
    return filtered_candidates, proximity, clinical, literature, safety, ground_truth


def load_molecular(path=MOLECULAR_CSV):
    """
    Load the molecular/pathway dimension (script 08), or None if absent.

    Returning None rather than raising keeps script 06 backwards compatible:
    without the file it reproduces exactly the previous 4-dimension analysis.
    """
    if not os.path.exists(path):
        return None
    frame = pd.read_csv(path)
    required = {"compound_name", "molecular_plausibility_score", "confidence"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    return frame

def mask_unlabelled_safety(safety):
    """
    Treat "no openFDA label" as MISSING safety evidence (TD-031).

    Step 05 historically wrote serious_term_count=0 / boxed_warning=False for a
    compound with no label; after the inverted percentile rank that is the
    BEST possible safety score, i.e. absence of evidence was scored as safety.
    Rows with has_label != True are blanked here so they follow the same
    missing-value path as every other dimension (impute_missing). This works
    for legacy checkpoints (zeros) and new ones (nulls) alike. The added
    `safety_label_missing` column keeps the missingness visible downstream.
    """
    safety = safety.copy()
    if "has_label" in safety.columns:
        labelled = safety["has_label"].astype(str).str.strip().str.lower().isin(["true", "1"])
    else:
        labelled = pd.Series(True, index=safety.index)
    safety["boxed_warning"] = safety["boxed_warning"].astype(object)
    safety.loc[~labelled, ["serious_term_count", "boxed_warning"]] = np.nan
    safety["safety_label_missing"] = ~labelled
    return safety


PHASE_RANK = {"NA": 0, "EARLY_PHASE1": 1, "PHASE1": 2, "PHASE2": 3, "PHASE3": 4, "PHASE4": 5}

def build_clinical_maturity(clinical_df):
    clinical_df = clinical_df.copy()
    clinical_df["phase_rank"] = clinical_df["phase"].map(PHASE_RANK).fillna(0)
    return clinical_df.groupby("compound_name").agg(
        max_phase_rank=("phase_rank", "max"),
        n_trials=("nct_id", "nunique"),
    ).reset_index()


#: Pre-cutoff (feature) trial links in which the compound is not tested for PD
#: (TD-038 / TD-023). Proposed, NOT approved: the file does not exist until the
#: owner adopts a policy (DECISIONS D-020). Adjudication per link is in
#: data/feature_trial_roles_td038.csv.
FEATURE_EXCLUSIONS_CSV = "data/feature_role_exclusions.csv"


def apply_feature_exclusions(clinical_df, exclusions):
    """
    Drop (nct_id, compound_name) links listed in `exclusions` from the
    pre-cutoff clinical table.

    Unlike apply_label_exclusions this is per LINK, not per trial: a multi-arm
    trial can stay valid evidence for one compound and be excluded for another.
    Every exclusion must match an existing link; a mismatch raises. Returns
    (filtered table, compounds left with no pre-cutoff link). Those compounds
    leave the pool, because merge_dimensions keys the pool on this table.
    """
    if exclusions is None or exclusions.empty:
        return clinical_df, []
    pairs = set(zip(clinical_df["nct_id"], clinical_df["compound_name"]))
    drop = set(zip(exclusions["nct_id"], exclusions["compound_name"]))
    unknown = sorted(drop - pairs)
    if unknown:
        raise ValueError(f"feature exclusions not found in clinical table: {unknown}")
    keep = [(n, c) not in drop for n, c in zip(clinical_df["nct_id"], clinical_df["compound_name"])]
    kept = clinical_df[keep]
    lost = sorted(set(clinical_df["compound_name"]) - set(kept["compound_name"]))
    return kept, lost


#: Raw value columns per source; non-finite values are treated as not computed (never as extreme).
RAW_COLUMNS = ["proximity_z", "max_phase_rank", "n_trials", "raw_paper_count", "effective_independent_count",
               "independence_ratio", "serious_term_count", "molecular_plausibility_score"]


def _require_unique(frame, source):
    """A duplicated compound row would silently duplicate a candidate in the merge (VPS check D1)."""
    if frame is None or "compound_name" not in frame:
        return
    dup = sorted(frame.loc[frame["compound_name"].duplicated(), "compound_name"].unique())
    if dup:
        raise ValueError(f"{source}: duplicate compound rows {dup[:10]} - refusing to merge")


def merge_dimensions(filtered_candidates, proximity, clinical_maturity, literature, safety,
                     molecular=None):
    for frame, source in ((proximity, "network_proximity"), (clinical_maturity, "clinical maturity"),
                          (literature, "literature_independence"), (safety, "safety_signal"),
                          (molecular, "molecular_pathway")):
        _require_unique(frame, source)
    base = clinical_maturity[["compound_name"]].drop_duplicates()
    filtered_names = set(filtered_candidates["compound_name"])
    base = base[base["compound_name"].isin(filtered_names)]
    df = base.merge(proximity[["compound_name", "proximity_z"]], on="compound_name", how="left")
    df = df.merge(clinical_maturity, on="compound_name", how="left")
    df = df.merge(literature[["compound_name", "raw_paper_count", "effective_independent_count",
                                "independence_ratio"]], on="compound_name", how="left")
    safety = mask_unlabelled_safety(safety)
    df = df.merge(safety[["compound_name", "boxed_warning", "serious_term_count", "safety_label_missing"]],
                  on="compound_name", how="left")
    # No safety row at all (stage 05 error / not queried) is missing too.
    df["safety_label_missing"] = df["safety_label_missing"].astype(object).where(
        df["safety_label_missing"].notna(), True).astype(bool)
    if molecular is not None:
        cols = ["compound_name", "molecular_plausibility_score", "confidence"]
        extra = [c for c in ("direct_component", "pathway_component", "n_targets",
                             "n_pathways_in_disease_module", "resolved")
                 if c in molecular.columns]
        df = df.merge(
            molecular[cols + extra].rename(
                columns={"confidence": "molecular_confidence"}),
            on="compound_name", how="left",
        )
    for col in RAW_COLUMNS:          # +/-inf is "not computed", not the best/worst value (VPS check D2)
        if col in df.columns:
            vals = pd.to_numeric(df[col], errors="coerce")
            df[col] = vals.where(np.isfinite(vals))
    return df

def impute_missing(df):
    """
    Median-impute the proximity, clinical and literature raw values (unchanged).

    Safety is NOT imputed (DECISIONS D-004). With a zero-inflated risk
    distribution, the median of serious_term_count is 0, so median imputation
    gave every no-label compound the best safety rank (TD-031). Missing safety
    stays NaN, is ranked among nobody, and receives NEUTRAL_RANK in
    build_standardized_scores.
    """
    df = df.copy()
    # Record which ranked dimensions are imputed BEFORE filling (VPS check D3: previously the two
    # compounds without a proximity value looked measured; scores are unchanged by this flag).
    imputed = {"proximity": df["proximity_z"].isna(), "clinical": df["max_phase_rank"].isna(),
               "literature": df["effective_independent_count"].isna()}
    df["dimensions_imputed"] = [
        "|".join(d for d, m in imputed.items() if m.iloc[i]) for i in range(len(df))]
    for col in ["proximity_z", "max_phase_rank", "n_trials", "raw_paper_count",
                "effective_independent_count", "independence_ratio"]:
        df[col] = df[col].fillna(df[col].median())
    return df


def impute_molecular(df):
    """
    Impute the molecular dimension, distinguishing "measured as zero" from
    "never measured".

    The molecular agent already separates these: a compound it scored but found
    no evidence for has score 0.0 with confidence > 0, which is a real
    measurement and is left alone. Only compounds ABSENT from
    molecular_pathway.csv are NaN here, and those are median-imputed to match
    the convention the other four dimensions already use (see impute_missing).

    Returns (df, n_imputed) so the count can be reported rather than hidden.
    """
    df = df.copy()
    if "molecular_plausibility_score" not in df.columns:
        return df, 0
    n_imputed = int(df["molecular_plausibility_score"].isna().sum())
    df["molecular_plausibility_score"] = df["molecular_plausibility_score"].fillna(
        df["molecular_plausibility_score"].median()
    )
    if "molecular_confidence" in df.columns:
        df["molecular_confidence"] = df["molecular_confidence"].fillna(0.0)
    return df, n_imputed


# ============================================================
# 5. PERCENTILE-RANK NORMALIZATION (outlier-robust, replaces z-score)
# ============================================================

#: Rank given to a dimension that was not measured for a compound (D-004).
NEUTRAL_RANK = 0.5


def percentile_rank(series, invert=False, convention=None):
    """Converts to percentile rank in [0, 1]. Fully robust to outliers --
    an extreme value only affects its own rank, not the scale of others.
    NaN stays NaN (not ranked). See RANK_CONVENTION for the two conventions."""
    convention = convention or RANK_CONVENTION
    if convention == "legacy":
        ranks = series.rank(pct=True, method="average")
        return 1 - ranks if invert else ranks
    if convention == "midrank":
        n = series.notna().sum()
        ranks = (series.rank(method="average") - 0.5) / n if n else series * np.nan
        return 1 - ranks if invert else ranks
    raise ValueError(f"unknown rank convention {convention!r}")

def build_standardized_scores(df):
    df = df.copy()
    # Proximity: more negative raw = better -> invert
    df["r_proximity"] = percentile_rank(df["proximity_z"], invert=True)
    df["r_clinical"] = percentile_rank(df["max_phase_rank"], invert=False)
    df["r_literature"] = percentile_rank(df["effective_independent_count"], invert=False)
    # NaN risk (no openFDA label) is ranked among measured compounds only, then neutral.
    boxed_points = df["boxed_warning"].map({True: 5, False: 0, 1: 5, 0: 0})
    safety_risk = df["serious_term_count"] + boxed_points
    df["r_safety"] = percentile_rank(safety_risk, invert=True)
    # Molecular (dimension 5): higher plausibility = better. Percentile-ranked
    # like every other dimension so it enters the fusion on the same scale.
    # A compound with no ChEMBL mechanism target (n_targets == 0) has no
    # molecular evidence, which is not evidence against it (D-004, TD-024).
    # Its 0.0 is kept in the raw column but not ranked; it gets NEUTRAL_RANK.
    if "molecular_plausibility_score" in df.columns:
        mol = df["molecular_plausibility_score"]
        if "n_targets" in df.columns:
            no_target = df["n_targets"].fillna(-1) == 0
            df["molecular_evidence_missing"] = no_target
            mol = mol.where(~no_target)
        df["r_molecular"] = percentile_rank(mol, invert=False)
    # Unmeasured dimensions get the uninformative midpoint rank (D-004): not
    # "safest", not "no evidence", and not dropped (dropping let a compound with
    # few measured dimensions rise on those alone). Coverage is kept visible.
    r_cols = [c for c in df.columns if c.startswith("r_")]
    df["dimensions_missing"] = df[r_cols].isna().apply(
        lambda row: "|".join(c[2:] for c, miss in row.items() if miss), axis=1)
    n_imputed = (df["dimensions_imputed"].map(lambda x: len([d for d in str(x).split("|") if d]))
                 if "dimensions_imputed" in df.columns else 0)
    df["n_dimensions_measured"] = df[r_cols].notna().sum(axis=1) - n_imputed
    df[r_cols] = df[r_cols].fillna(NEUTRAL_RANK)
    return df


# ============================================================
# 6. LABELS
# ============================================================

#: Curated post-cutoff trials that do not test the compound for PD (TD-032,
#: policy P1 approved 2026-10-14; adjudication in docs/CASE_STUDIES.md §9.1).
#: The ground-truth CSV is left untouched; these trials are dropped here.
LABEL_EXCLUSIONS_CSV = "data/label_role_exclusions.csv"


def apply_label_exclusions(ground_truth, exclusions):
    """
    Drop ground-truth trial rows listed in `exclusions` (by nct_id).

    A compound stays positive if any other qualifying trial remains, so the
    exclusion is per trial, not per compound. Every exclusion must match an
    existing (nct_id, compound_name) row; a mismatch raises rather than being
    silently ignored. Returns (filtered ground truth, compounds that lost all
    their label trials).
    """
    if exclusions is None or exclusions.empty:
        return ground_truth, []
    gt_pairs = set(zip(ground_truth["nct_id"], ground_truth["compound_name"]))
    unknown = [(n, c) for n, c in zip(exclusions["nct_id"], exclusions["compound_name"])
               if (n, c) not in gt_pairs]
    if unknown:
        raise ValueError(f"label exclusions not found in ground truth: {unknown}")
    kept = ground_truth[~ground_truth["nct_id"].isin(set(exclusions["nct_id"]))]
    dropped = sorted(set(ground_truth["compound_name"]) - set(kept["compound_name"]))
    return kept, dropped


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
    # Guard added with the 5-dimension work: cv_grid_search_weights returns
    # None when every CV fold is single-class (possible with small/imbalanced
    # label sets). Previously that None flowed straight into this function and
    # failed with an opaque AttributeError; now it names the cause.
    if weights is None:
        raise ValueError(
            f"compute_weighted_vps({col_name!r}) got weights=None. The weight "
            f"search found no usable combination -- typically every CV fold "
            f"contained a single class. Check the positive-label count."
        )
    missing = [d for d in weights if f"r_{d}" not in df.columns]
    if missing:
        raise ValueError(
            f"compute_weighted_vps({col_name!r}): no standardized column for "
            f"dimension(s) {missing}. Expected r_{missing[0]} -- was "
            f"build_standardized_scores() run, and is the dimension's input "
            f"file present?"
        )
    df = df.copy()
    score = np.zeros(len(df))
    for dim, w in weights.items():
        score += w * df[f"r_{dim}"].values
    df[col_name] = score
    return df


# ============================================================
# 9. CROSS-VALIDATED GRID SEARCH OVER WEIGHT COMBINATIONS
# ============================================================

def _build_weight_grid(dims, step):
    """All weight combinations on a `step` grid that sum to 1 (and are non-zero)."""
    grid_values = np.arange(0, 1 + step, step)
    out = []
    for combo in product(grid_values, repeat=len(dims)):
        if abs(sum(combo) - 1.0) < 1e-9 and sum(combo) > 0:
            out.append(dict(zip(dims, combo)))
    return out


def _best_weights_on(frame, candidate_weights):
    """Weight combination maximising AUROC on `frame` alone. (weights, auroc)."""
    best, best_auc = None, -1.0
    for weights in candidate_weights:
        scored = compute_weighted_vps(frame, weights, col_name="_sel_score")
        try:
            auc = roc_auc_score(scored["label"], scored["_sel_score"])
        except ValueError:
            continue
        if auc > best_auc:
            best_auc, best = auc, weights
    return best, best_auc


def cv_grid_search_weights(df, dims, n_splits=5, step=0.25):
    """
    Select fusion weights by grid search, and estimate performance HONESTLY.

    Returns (best_weights, nested_cv_auroc, log).

    LEAKAGE FIX (2026-10-05). The previous implementation bound `train_idx` but
    never used it: it scored every candidate weight vector on each *test* fold,
    averaged, and took the maximum. Selection therefore saw every fold's test
    labels, so the reported figure was selected on the same data it was measured
    on and was optimistically biased. (TECHNICAL_DEBT TD-003.)

    Now:
      * `nested_cv_auroc` - for each fold, weights are chosen on the TRAINING
        fold only and evaluated on the held-out fold. This is the number to
        report as performance.
      * `best_weights`    - chosen on all labelled data, because a single final
        model has to be emitted. Its own in-sample AUROC is recorded in the log
        as `in_sample_auroc_full_data` and must NOT be reported as performance.

    The equal-weight variants are untouched: they involve no selection and so
    were never affected by this bias.
    """
    y = df["label"].values
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_SEED)
    candidate_weights = _build_weight_grid(dims, step)

    # --- honest estimate: select on train fold, evaluate on held-out fold ---
    fold_aurocs = []
    for train_idx, test_idx in skf.split(df, y):
        train_df, test_df = df.iloc[train_idx], df.iloc[test_idx]
        fold_weights, _ = _best_weights_on(train_df, candidate_weights)
        if fold_weights is None:
            continue
        scored = compute_weighted_vps(test_df, fold_weights, col_name="_cv_score")
        try:
            fold_aurocs.append(roc_auc_score(scored["label"], scored["_cv_score"]))
        except ValueError:
            continue
    nested_cv_auroc = float(np.mean(fold_aurocs)) if fold_aurocs else float("nan")

    # --- final model weights, selected on all labelled data -----------------
    best_weights, in_sample_auroc = _best_weights_on(df, candidate_weights)

    results_log = []
    for weights in candidate_weights:
        scored = compute_weighted_vps(df, weights, col_name="_log_score")
        try:
            auc = roc_auc_score(scored["label"], scored["_log_score"])
        except ValueError:
            continue
        results_log.append({**weights, "in_sample_auroc_full_data": auc})
    log = pd.DataFrame(results_log)
    log["nested_cv_auroc_for_selected_model"] = nested_cv_auroc
    log["n_cv_folds_used"] = len(fold_aurocs)
    log["selected_model_in_sample_auroc"] = in_sample_auroc

    return best_weights, nested_cv_auroc, log


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

def run_ablation(df, weights_full, dims=None, label=None):
    """
    Leave-one-dimension-out ablation.

    Generalised over `dims` so the same function serves the 4-dimension and
    5-dimension models. Default `dims` reproduces the original 4-dimension
    behaviour exactly, including the "Full VPS (grid-searched weights, 4 dims)"
    row label, so previously generated outputs stay comparable.
    """
    dims = list(dims) if dims is not None else list(BASE_DIMENSIONS)
    label = label or f"Full VPS (grid-searched weights, {len(dims)} dims)"
    results = {}
    full = compute_weighted_vps(df, weights_full, "VPS_ablation")
    results[label] = evaluate(full, "VPS_ablation")
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
    molecular = load_molecular()
    if os.path.exists(FEATURE_EXCLUSIONS_CSV):
        clinical, lost = apply_feature_exclusions(clinical, pd.read_csv(FEATURE_EXCLUSIONS_CSV))
        print(f"Feature exclusions ({FEATURE_EXCLUSIONS_CSV}): compounds leaving the pool {lost}")
    clinical_maturity = build_clinical_maturity(clinical)
    df = merge_dimensions(filtered_candidates, proximity, clinical_maturity, literature,
                          safety, molecular)

    print(f"\nEvaluable candidate pool: {len(df)} compounds")
    print(f"Safety evidence missing (no openFDA label or no record): "
          f"{int(df['safety_label_missing'].sum())} -> neutral rank {NEUTRAL_RANK} (D-004), not zero risk")

    df = impute_missing(df)

    has_molecular = molecular is not None
    if has_molecular:
        df, n_mol_imputed = impute_molecular(df)
        covered = len(df) - n_mol_imputed
        print(f"Molecular dimension: {covered}/{len(df)} compounds scored by step 08 "
              f"({n_mol_imputed} absent -> median-imputed)")
        if "molecular_confidence" in df.columns:
            print(f"  mean molecular confidence (scored only): "
                  f"{df.loc[df['molecular_confidence'] > 0, 'molecular_confidence'].mean():.3f}")
    else:
        print(f"Molecular dimension: {MOLECULAR_CSV} not found -> running the "
              f"original 4-dimension analysis only. Run scripts/08_molecular_pathway.py "
              f"to enable the 5-dimension variants.")

    df = build_standardized_scores(df)
    if os.path.exists(LABEL_EXCLUSIONS_CSV):
        ground_truth, lost = apply_label_exclusions(ground_truth, pd.read_csv(LABEL_EXCLUSIONS_CSV))
        print(f"Label exclusions ({LABEL_EXCLUSIONS_CSV}): positives -> 0 for {lost}")
    df = build_labels(df, ground_truth)

    print(f"Positive labels: {df['label'].sum()} / {len(df)}")

    # --- Equal-weight VPS (4-dim), for comparison ---
    df = compute_weighted_vps(df, {"proximity": 0.25, "clinical": 0.25, "literature": 0.25, "safety": 0.25}, "VPS_equal")

    # --- Grid search: best 4-dimension weights ---
    print("\nRunning grid search over 4-dimension weight combinations (this may take a minute)...")
    best_weights_4d, best_auroc_4d, log_4d = cv_grid_search_weights(
        df, dims=["proximity", "clinical", "literature", "safety"], step=0.25)
    print(f"Best 4-dim weights: {best_weights_4d}  (nested-CV AUROC: {best_auroc_4d:.3f})")
    df = compute_weighted_vps(df, best_weights_4d, "VPS_grid_4d")

    # --- Grid search: best 3-dimension weights (drop proximity) ---
    print("\nRunning grid search over 3-dimension weights (proximity dropped)...")
    best_weights_3d, best_auroc_3d, log_3d = cv_grid_search_weights(
        df, dims=["clinical", "literature", "safety"], step=0.1)
    print(f"Best 3-dim weights: {best_weights_3d}  (nested-CV AUROC: {best_auroc_3d:.3f})")
    df = compute_weighted_vps(df, best_weights_3d, "VPS_grid_3d")

    # --- 5-dimension variants (molecular agent added as dimension 5) ---
    # These are ADDITIONAL columns. The 4-dim and 3-dim variants above are
    # computed exactly as before, so previously reported numbers are unchanged.
    best_weights_5d = None
    if has_molecular:
        equal_5 = {d: 0.2 for d in ALL_DIMENSIONS}
        df = compute_weighted_vps(df, equal_5, "VPS_equal_5d")

        print("\nRunning grid search over 5-dimension weight combinations...")
        best_weights_5d, best_auroc_5d, log_5d = cv_grid_search_weights(
            df, dims=ALL_DIMENSIONS, step=0.25)
        if best_weights_5d is None:
            print("  grid search found no usable weight combination (every CV "
                  "fold was single-class); falling back to equal 5-dim weights.")
            best_weights_5d = equal_5
        else:
            print(f"Best 5-dim weights: {best_weights_5d}  "
                  f"(nested-CV AUROC: {best_auroc_5d:.3f})")
        df = compute_weighted_vps(df, best_weights_5d, "VPS_grid_5d")
        _write_csv(log_5d, "data/grid_search_5d_log.csv", index=False)

        # Molecular dimension alone, as a baseline for the new dimension.
        df = compute_weighted_vps(
            df, {d: (1.0 if d == MOLECULAR_DIMENSION else 0.0) for d in ALL_DIMENSIONS},
            "VPS_molecular_only")

    _write_csv(df, "data/vps_scores_v2.csv", index=False)
    _write_csv(log_4d, "data/grid_search_4d_log.csv", index=False)
    _write_csv(log_3d, "data/grid_search_3d_log.csv", index=False)

    print("\n--- FINAL COMPARISON: baselines vs. all VPS variants ---")
    baseline_results = compute_baselines(df)
    for name, metrics in baseline_results.items():
        print(f"{name}: {metrics}")

    print(f"VPS -- equal weights (4 dim): {evaluate(df, 'VPS_equal')}")
    print(f"VPS -- grid-searched weights (4 dim): {evaluate(df, 'VPS_grid_4d')}")
    print(f"VPS -- grid-searched weights (3 dim, no proximity): {evaluate(df, 'VPS_grid_3d')}")

    variant_scores = [
        ("VPS_equal", evaluate(df, "VPS_equal")["AUROC"]),
        ("VPS_grid_4d", evaluate(df, "VPS_grid_4d")["AUROC"]),
        ("VPS_grid_3d", evaluate(df, "VPS_grid_3d")["AUROC"]),
    ]
    if has_molecular:
        print(f"VPS -- molecular dimension only: {evaluate(df, 'VPS_molecular_only')}")
        print(f"VPS -- equal weights (5 dim): {evaluate(df, 'VPS_equal_5d')}")
        print(f"VPS -- grid-searched weights (5 dim): {evaluate(df, 'VPS_grid_5d')}")
        variant_scores += [
            ("VPS_equal_5d", evaluate(df, "VPS_equal_5d")["AUROC"]),
            ("VPS_grid_5d", evaluate(df, "VPS_grid_5d")["AUROC"]),
        ]

    print("\n--- Ablation (using grid-searched 4-dim weights as the 'full' model) ---")
    ablation_results = run_ablation(df, best_weights_4d)
    for name, metrics in ablation_results.items():
        print(f"{name}: {metrics}")

    _write_csv(pd.DataFrame(baseline_results).T, "data/baseline_results_v2.csv")
    _write_csv(pd.DataFrame(ablation_results).T, "data/ablation_results_v2.csv")

    # Persist the VPS variant metrics that were previously only printed, so
    # script 07 can plot measured numbers instead of hardcoded literals.
    # Grid-searched variants have their weights chosen on ALL labelled data, so
    # their AUROC here is IN-SAMPLE and is not comparable to the equal-weight
    # rows (which fit nothing). The honest held-out figure is the nested-CV
    # value from cv_grid_search_weights. Both are recorded explicitly so the
    # distinction cannot be lost downstream. See TECHNICAL_DEBT TD-003.
    variant_results = {
        "VPS equal weights (4 dim)": {**evaluate(df, "VPS_equal"),
                                      "weights_fitted": False,
                                      "heldout_nested_cv_auroc": None},
        "VPS grid-searched (4 dim)": {**evaluate(df, "VPS_grid_4d"),
                                      "weights_fitted": True,
                                      "heldout_nested_cv_auroc": round(best_auroc_4d, 3)},
        "VPS grid-searched (3 dim)": {**evaluate(df, "VPS_grid_3d"),
                                      "weights_fitted": True,
                                      "heldout_nested_cv_auroc": round(best_auroc_3d, 3)},
    }
    if has_molecular:
        variant_results["Molecular dimension only"] = {
            **evaluate(df, "VPS_molecular_only"),
            "weights_fitted": False, "heldout_nested_cv_auroc": None}
        variant_results["VPS equal weights (5 dim)"] = {
            **evaluate(df, "VPS_equal_5d"),
            "weights_fitted": False, "heldout_nested_cv_auroc": None}
        variant_results["VPS grid-searched (5 dim)"] = {
            **evaluate(df, "VPS_grid_5d"),
            "weights_fitted": True,
            "heldout_nested_cv_auroc": round(best_auroc_5d, 3)}
    out = pd.DataFrame(variant_results).T
    out.index.name = "model"
    _write_csv(out, "data/vps_variant_results.csv")

    if has_molecular:
        print("\n--- Ablation, 5 dimensions (grid-searched 5-dim weights as 'full') ---")
        ablation_5d = run_ablation(df, best_weights_5d, dims=ALL_DIMENSIONS)
        for name, metrics in ablation_5d.items():
            print(f"{name}: {metrics}")
        _write_csv(pd.DataFrame(ablation_5d).T, "data/ablation_results_5d.csv")

    print("\n--- Top 15 by best-performing VPS variant ---")
    best_variant = max(variant_scores, key=lambda x: x[1])
    print(f"(Best variant: {best_variant[0]}, AUROC={best_variant[1]})")
    print(df.sort_values(best_variant[0], ascending=False)
            [["compound_name", best_variant[0], "label"]]
            .head(15).to_string(index=False))


if __name__ == "__main__":
    import argparse
    # No options yet: parse anyway so --help or a stray argument exits before any
    # work is done (TD-034; incident E-017 ran stages 05/06 via --help).
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0] if __doc__ else None)
    ap.add_argument("--output-dir", default=OUTPUT_DIR,
                    help="write outputs here instead of data/ (tracked runs stage, validate, then publish)")
    ap.add_argument("--rank-convention", choices=("legacy", "midrank"), default=RANK_CONVENTION,
                    help="percentile-rank convention (D-024); default reproduces the published baseline")
    _args = ap.parse_args()
    OUTPUT_DIR, RANK_CONVENTION = _args.output_dir, _args.rank_convention
    main()