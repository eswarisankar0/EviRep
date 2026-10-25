"""
VPS evaluation report — reproduces and extends the persisted evaluation, offline.

Reads only persisted artefacts (no pipeline stage is run, nothing in data/ other
than the report is written):
  data/vps_scores_v2.csv, data/vps_variant_results.csv, data/baseline_results_v2.csv,
  data/ablation_results_5d.csv, data/bootstrap_ci_equal5d_vs_4d.csv,
  data/ground_truth_postcutoff_clean.csv, data/label_role_exclusions.csv,
  data/reproducibility.json (10e, for trials shared across compounds)

Writes data/vps_evaluation_report.json:
  * reproduction check of every persisted AUROC from the scores file
  * primary (unfitted, equal-weight) AUROC and AUPRC with bootstrap CIs, prevalence
  * paired 5d-4d comparison, re-run twice to prove the seeded bootstrap is reproducible
  * held-out estimate for grid-searched models over 20 repeated nested-CV splits
  * Spearman correlation between dimension ranks
  * missing-data paths and coverage; duplicate (shared) trial evidence
  * calibration applicability (VPS is a rank score, not a probability)
"""

import argparse
import hashlib
import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bootstrap_auroc_ci import paired_bootstrap  # noqa: E402

REPORT_VERSION = "vps-eval-1.0"
OUT = "data/vps_evaluation_report.json"
SEED, N_BOOT, N_REPEATS = 42, 2000, 20
R5 = ["r_proximity", "r_clinical", "r_literature", "r_safety", "r_molecular"]


def _load_fusion():
    spec = importlib.util.spec_from_file_location("vps_fusion", os.path.join(HERE, "06_vps_fusion.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _md5(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def boot_metric(y, s, metric, n=N_BOOT, seed=SEED):
    """Percentile bootstrap CI of a single-score metric; single-class resamples skipped and counted."""
    rng = np.random.default_rng(seed)
    y, s = np.asarray(y), np.asarray(s)
    vals, skipped = [], 0
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() == y[i].max():
            skipped += 1
            continue
        vals.append(metric(y[i], s[i]))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))], skipped


def repeated_nested_cv(v, fusion, dims, step, repeats=N_REPEATS):
    grid = fusion._build_weight_grid(dims, step)
    y = v["label"].values
    means = []
    for s in range(repeats):
        folds = []
        for tr, te in StratifiedKFold(5, shuffle=True, random_state=s).split(v, y):
            w, _ = fusion._best_weights_on(v.iloc[tr], grid)
            sc = fusion.compute_weighted_vps(v.iloc[te], w, "_s")
            folds.append(roc_auc_score(sc["label"], sc["_s"]))
        means.append(float(np.mean(folds)))
    return {"mean": float(np.mean(means)), "p2_5": float(np.percentile(means, 2.5)),
            "p97_5": float(np.percentile(means, 97.5)), "min": float(min(means)), "max": float(max(means)),
            "repeats": repeats, "seeds": f"0..{repeats - 1}", "folds": 5}


def build(root="."):
    j = lambda p: os.path.join(root, p)
    v = pd.read_csv(j("data/vps_scores_v2.csv"))
    y = v["label"].values
    fusion = _load_fusion()
    n, pos = len(v), int(y.sum())
    out = {"report_version": REPORT_VERSION, "seed": SEED, "n_boot": N_BOOT,
           # every file read below, so a change to any of them marks the report stale
           "inputs": {p: _md5(j(p)) for p in ("data/vps_scores_v2.csv", "data/ground_truth_postcutoff_clean.csv",
                                             "data/label_role_exclusions.csv", "data/vps_variant_results.csv",
                                             "data/baseline_results_v2.csv", "data/ablation_results_5d.csv",
                                             "data/bootstrap_ci_equal5d_vs_4d.csv") if os.path.exists(j(p))},
           "cohort": {"n": n, "positives": pos, "negatives": n - pos, "prevalence": pos / n,
                      "duplicate_compounds": int(v["compound_name"].duplicated().sum()),
                      "label_definition": "continued clinical investigation (D-010), not efficacy"}}

    # 1. reproduction of persisted AUROCs (rounded to 3 dp as stored)
    var = pd.read_csv(j("data/vps_variant_results.csv"), index_col=0)
    col = {"VPS equal weights (4 dim)": "VPS_equal", "VPS grid-searched (4 dim)": "VPS_grid_4d",
           "VPS grid-searched (3 dim)": "VPS_grid_3d", "Molecular dimension only": "VPS_molecular_only",
           "VPS equal weights (5 dim)": "VPS_equal_5d", "VPS grid-searched (5 dim)": "VPS_grid_5d"}
    repro = []
    for row, c in col.items():
        if row in var.index and c in v:
            got = round(roc_auc_score(y, v[c]), 3)
            repro.append({"model": row, "column": c, "persisted": float(var.loc[row, "AUROC"]), "recomputed": got,
                          "match": abs(got - float(var.loc[row, "AUROC"])) < 1e-9,
                          "type": "in-sample (weights fitted on all labels)" if str(var.loc[row, "weights_fitted"]) == "True"
                          else "unfitted"})
    out["reproduction"] = {"all_match": all(r["match"] for r in repro), "rows": repro}

    # 2. primary metrics
    prim = []
    for c, label in (("VPS_equal_5d", "equal-weight 5d (primary)"), ("VPS_equal", "equal-weight 4d (primary)"),
                     ("VPS_molecular_only", "molecular only (baseline)")):
        if c not in v:
            continue
        auc_ci, sk1 = boot_metric(y, v[c], roc_auc_score)
        ap = average_precision_score(y, v[c])
        ap_ci, sk2 = boot_metric(y, v[c], average_precision_score)
        prim.append({"model": label, "column": c, "auroc": roc_auc_score(y, v[c]), "auroc_ci95": auc_ci,
                     "auprc": ap, "auprc_ci95": ap_ci, "auprc_over_prevalence": ap / (pos / n),
                     "skipped_resamples": max(sk1, sk2)})
    out["primary"] = prim

    # 3. paired comparison, run twice: the seeded bootstrap must be bit-identical
    a = paired_bootstrap(y, v["VPS_equal_5d"], v["VPS_equal"], N_BOOT, SEED)
    b = paired_bootstrap(y, v["VPS_equal_5d"], v["VPS_equal"], N_BOOT, SEED)
    persisted = pd.read_csv(j("data/bootstrap_ci_equal5d_vs_4d.csv")).iloc[0].to_dict() \
        if os.path.exists(j("data/bootstrap_ci_equal5d_vs_4d.csv")) else None
    out["paired_5d_vs_4d"] = {
        "diff": a["diff"], "ci95": list(a["ci_diff"]), "p_diff_gt_0": a["p_diff_gt_0"],
        "significant": not (a["ci_diff"][0] <= 0 <= a["ci_diff"][1]),
        "rerun_identical": a == b,
        "matches_persisted_ci_file": (persisted is not None and abs(persisted["ci_diff_low"] - a["ci_diff"][0]) < 1e-12
                                      and abs(persisted["ci_diff_high"] - a["ci_diff"][1]) < 1e-12)}

    # 4. fitted models: in-sample vs held-out
    out["grid_search"] = {
        "note": "weights are selected on training folds only inside CV; the persisted single split is one draw",
        "persisted_single_split": {r: float(var.loc[r, "heldout_nested_cv_auroc"]) for r in var.index
                                   if pd.notna(var.loc[r, "heldout_nested_cv_auroc"])},
        "repeated_nested_cv": {k: repeated_nested_cv(v, fusion, d, s) for k, d, s in
                               (("4d", fusion.BASE_DIMENSIONS, 0.25), ("3d", ["clinical", "literature", "safety"], 0.1),
                                ("5d", fusion.ALL_DIMENSIONS, 0.25))}}

    # 5. ablation and baselines (persisted, same protocol as 06)
    out["baselines"] = pd.read_csv(j("data/baseline_results_v2.csv"), index_col=0)["AUROC"].to_dict()
    if os.path.exists(j("data/ablation_results_5d.csv")):
        out["ablation_5d"] = {"rows": pd.read_csv(j("data/ablation_results_5d.csv"), index_col=0)["AUROC"].to_dict(),
                              "caveat": "reference row is in-sample (grid weights); 'Without X' rows are equal-weight (TD-025)"}

    # 6. correlated dimensions
    cm = v[R5].corr(method="spearman")
    out["dimension_spearman"] = {a_: {b_: round(float(cm.loc[a_, b_]), 3) for b_ in R5} for a_ in R5}
    out["max_offdiagonal_abs_spearman"] = round(float((cm.abs() - np.eye(5)).max().max()), 3)

    # 7. missing data and imputation paths
    miss = v.get("dimensions_missing", pd.Series([""] * n)).fillna("")
    out["missing_data"] = {
        "not_measured_by_dimension": {d: int(miss.str.split("|").apply(lambda xs: d in xs).sum())
                                      for d in ("proximity", "clinical", "literature", "safety", "molecular")},
        "n_dimensions_measured": {str(k): int((v.get("n_dimensions_measured") == k).sum()) for k in (5, 4, 3)},
        "imputation_paths": [
            "proximity_z missing -> median of the pool (06 impute_missing); rank lands near the middle",
            "no openFDA label -> safety not imputed; neutral rank 0.5 + safety_label_missing (D-004)",
            "no ChEMBL mechanism target -> molecular neutral rank 0.5 + molecular_evidence_missing (D-004)",
            "compound absent from molecular_pathway.csv -> median (0 such compounds now)",
            "clinical, literature: always present for pool compounds (pool requires a pre-cutoff trial)"],
        "positives_among_missing": {d: int(v.loc[miss.str.split("|").apply(lambda xs: d in xs), "label"].sum())
                                    for d in ("safety", "molecular")}}

    # 8. duplicate evidence across compounds (10e)
    rp = j("data/reproducibility.json")
    if os.path.exists(rp):
        with open(rp) as fh:
            st = json.load(fh).get("shared_trials_across_compounds", {})
        pool = set(v["compound_name"])
        pre = [t for t in st.get("trials", []) if "precutoff" in t["file"]]
        both_in_pool = [t for t in pre if sum(c in pool for c in t["compounds"]) > 1]
        out["duplicate_evidence"] = {
            "feature_trials_shared": len(pre), "feature_trials_shared_by_pool_compounds": len(both_in_pool),
            "pool_compounds_affected": sorted({c for t in both_in_pool for c in t["compounds"] if c in pool}),
            "label_trials_shared": [t for t in st.get("trials", []) if "ground_truth" in t["file"]],
            "meaning": "the same pre-cutoff trial raises clinical maturity for every compound it names "
                       "(combination arms, comparators, multi-drug protocols); see TD-023"}

    # 9. calibration
    out["calibration"] = {
        "applicable": False,
        "reason": (f"VPS is a mean of percentile ranks used for ordering, not a probability; with {pos} positives "
                   "a reliability curve would rest on very few events per bin. Report discrimination (AUROC, "
                   "AUPRC) only; do not read a VPS value as a probability.")}
    out["temporal_validity"] = ("Not leakage-free: literature, safety and molecular use current data (TD-033, B-001, "
                                "B-002). Without literature the score stays above chance; proximity + clinical alone "
                                "do not (D-012).")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Reproduce and extend the VPS evaluation from persisted artefacts (offline)")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(argv)
    rep = build(args.root)
    path = os.path.join(args.root, args.out)
    with open(path + ".tmp", "w") as fh:
        json.dump(rep, fh, indent=1, sort_keys=True)
    os.replace(path + ".tmp", path)
    print(f"Saved {args.out}: reproduction all_match={rep['reproduction']['all_match']}; "
          f"5d-4d {rep['paired_5d_vs_4d']['diff']:+.3f} CI {[round(x, 3) for x in rep['paired_5d_vs_4d']['ci95']]}; "
          f"bootstrap rerun identical={rep['paired_5d_vs_4d']['rerun_identical']}")


if __name__ == "__main__":
    main()
