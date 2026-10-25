"""
VPS validation experiments (2026-10-19). Read-only with respect to every published artifact.

Rebuilds the equal-weight VPS from the raw stage outputs with pandas/scipy (a second path,
independent of scripts/06_vps_fusion.py and scripts/vps_verify.py), asserts that the baseline
reproduces data/vps_scores_v2.csv, then evaluates isolated, versioned variants:

  baseline        published policy (legacy percentile rank, median-imputed proximity, neutral 0.5
                  for unmeasured safety/molecular)
  td042_own_target  molecular pathway credit excludes the drug's own targets/genes from the
                  "shared PD module gene" set (TD-042)
  td041_neutral_proximity  missing proximity -> neutral 0.5 instead of the median (TD-041)
  td040_midrank   midrank percentile convention (TD-040, D-024)
  leakage subsets dimensions whose inputs are cutoff-bounded (TD-033)

Also: stratified bootstrap CIs (AUROC, AUPRC, precision@10), paired differences, and repeated
nested CV for nonnegative weights on the simplex (selection inside training folds only).
Nothing here is published; outputs go to --out (default data/_runs/validation_20261019/).

    ./venv/bin/python scripts/vps_validation_experiments.py [--out DIR] [--boot 2000] [--repeats 20]
"""

import argparse
import itertools
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import rankdata, spearmanr

PHASE = {"": 0, "NA": 0, "EARLY_PHASE1": 1, "PHASE1": 2, "PHASE2": 3, "PHASE3": 4, "PHASE4": 5}
DIMS5 = ["r_proximity", "r_clinical", "r_literature", "r_safety", "r_molecular"]
DIMS4 = DIMS5[:4]
SEED = 20261019


# ------------------------------------------------------------------ build
def pct(x, invert, convention):
    """Percentile rank over measured values (ties averaged); unmeasured -> 0.5."""
    out = pd.Series(0.5, index=x.index)
    ok = x.notna()
    n = int(ok.sum())
    r = rankdata(x[ok])
    q = r / n if convention == "legacy" else (r - 0.5) / n
    out[ok] = 1 - q if invert else q
    return out


def own_target_pathway_component(rec):
    """Pathway component with the drug's own targets/genes removed from the shared-gene sets."""
    own = {t.get("gene_symbol") for t in rec.get("targets") or []} | {g.get("gene_symbol") for g in rec.get("genes") or []}
    by = {}
    for p in rec.get("pathways") or []:
        by.setdefault(p["pathway_id"], []).append(p)
    if not by:
        return 0.0, 0, 0
    shared = sum(any(set(x.get("disease_module_genes_in_pathway") or []) - own for x in ps) for ps in by.values())
    return shared / len(by), shared, len(by)


def build(root=".", convention="legacy", proximity_missing="median", molecular="published"):
    j = lambda p: os.path.join(root, p)
    cand = set(pd.read_csv(j("data/pd_candidates_filtered.csv"))["compound_name"])
    clin = pd.read_csv(j("data/clinical_maturity_precutoff_clean.csv"), keep_default_na=False)
    clin = clin[clin["compound_name"].isin(cand)]
    phase = clin.assign(p=clin["phase"].map(lambda v: PHASE.get(v, 0))).groupby("compound_name")["p"].max()
    df = pd.DataFrame(index=phase.index)
    df["clinical"] = phase
    df["proximity"] = pd.read_csv(j("data/network_proximity.csv")).set_index("compound_name")["proximity_z"].reindex(df.index)
    df["literature"] = pd.read_csv(j("data/literature_independence.csv")).set_index("compound_name")[
        "effective_independent_count"].reindex(df.index)
    s = pd.read_csv(j("data/safety_signal.csv")).set_index("compound_name").reindex(df.index)
    has = s["has_label"].astype(str) == "True"
    df["safety"] = np.where(has, s["serious_term_count"] + 5 * (s["boxed_warning"].astype(str) == "True"), np.nan)
    m = pd.read_csv(j("data/molecular_pathway.csv")).set_index("compound_name").reindex(df.index)
    mol = m["molecular_plausibility_score"].astype(float)
    if molecular == "td042_own_target":
        recs = {}
        with open(j("data/molecular_pathway_evidence.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                recs[r["drug"]] = r
        for c in df.index:
            r = recs.get(c)
            if r and r.get("scoring"):
                pc, _, _ = own_target_pathway_component(r)
                mol[c] = 0.6 * r["scoring"]["components"]["direct_target_disease"] + 0.4 * pc
    df["molecular"] = np.where(m["n_targets"] > 0, mol, np.nan)
    prox_missing = df["proximity"].isna()
    for c in ("clinical", "literature"):
        df[c] = df[c].fillna(df[c].median())
    if proximity_missing == "median":
        df["proximity"] = df["proximity"].fillna(df["proximity"].median())
    out = pd.DataFrame(index=df.index)
    out["r_proximity"] = pct(df["proximity"], True, convention)
    out["r_clinical"] = pct(df["clinical"], False, convention)
    out["r_literature"] = pct(df["literature"], False, convention)
    out["r_safety"] = pct(df["safety"], True, convention)
    out["r_molecular"] = pct(df["molecular"], False, convention)
    gt = pd.read_csv(j("data/ground_truth_postcutoff_clean.csv"))
    excl = set(pd.read_csv(j("data/label_role_exclusions.csv"))["nct_id"])
    pos = set(gt.loc[~gt["nct_id"].isin(excl), "compound_name"])
    out["label"] = out.index.isin(pos).astype(int)        # attached after every feature is computed
    out["molecular_raw"] = df["molecular"]
    out["proximity_missing"] = prox_missing
    return out


# ------------------------------------------------------------------ metrics
def auroc_cols(scores, y):
    """Mann-Whitney AUROC for each column of scores (n x k); ties count 1/2 (average ranks).

    AUROC is undefined when the sample has no positive or no negative: the result is then NaN for every
    column, explicitly, never 0.5 (audit 2026-10-20, S-11). Non-binary labels, non-finite scores and shape
    mismatches are errors, not values."""
    scores, y = np.asarray(scores, float), np.asarray(y)
    if scores.ndim != 2 or y.ndim != 1 or scores.shape[0] != y.shape[0]:
        raise ValueError(f"auroc_cols: scores {scores.shape} and labels {y.shape} do not align")
    if y.size and not np.isin(y, (0, 1)).all():
        raise ValueError("auroc_cols: labels must be 0/1")
    if not np.isfinite(scores).all():
        raise ValueError("auroc_cols: scores contain NaN or infinity")
    npos = int((y == 1).sum()); nneg = int(y.size - npos)
    if npos == 0 or nneg == 0:
        return np.full(scores.shape[1], np.nan)
    r = rankdata(scores, axis=0)
    return (r[y == 1].sum(axis=0) - npos * (npos + 1) / 2) / (npos * nneg)


class UndefinedSelection(ValueError):
    """No validation fold contained both classes, so no weight/hyper-parameter choice is defined."""


def best_index(fold_aucs):
    """Index of the candidate with the highest summed AUROC over the validation folds where AUROC is defined.

    `fold_aucs` is (n_folds, n_candidates). A fold with one class is undefined for every candidate and is
    skipped (and counted by the caller); summing NaN would otherwise make every total NaN and np.argmax would
    silently return 0, i.e. the first candidate. Ties go to the first candidate (documented)."""
    a = np.atleast_2d(np.asarray(fold_aucs, float))
    valid = ~np.isnan(a).all(axis=1)
    if not valid.any():
        raise UndefinedSelection("every validation fold is single-class")
    if np.isnan(a[valid]).any():
        raise ValueError("partially undefined fold: AUROC is defined for some candidates only")
    return int(np.argmax(a[valid].sum(axis=0)))


def auprc(score, y):
    o = np.argsort(-score, kind="mergesort")
    ys = y[o]
    tp = np.cumsum(ys)
    prec = tp / np.arange(1, len(ys) + 1)
    return float((prec * ys).sum() / ys.sum())


def p_at(score, y, k=10):
    """Precision@k with ties at the boundary averaged (expected value over tie orders)."""
    thr = np.sort(score)[::-1][k - 1]
    above, at = score > thr, score == thr
    need = k - above.sum()
    return float((y[above].sum() + need * y[at].mean()) / k)


def metrics(score, y):
    score, y = np.asarray(score, float), np.asarray(y, int)
    return {"auroc": float(auroc_cols(score[:, None], y)[0]), "auprc": auprc(score, y), "p_at_10": p_at(score, y)}


def bootstrap(scores, y, n_boot, rng):
    """Stratified bootstrap (positives and negatives resampled separately); paired across scores."""
    y = np.asarray(y, int)
    pi, ni = np.where(y == 1)[0], np.where(y == 0)[0]
    draws = {k: {m: [] for m in ("auroc", "auprc", "p_at_10")} for k in scores}
    for _ in range(n_boot):
        idx = np.concatenate([rng.choice(pi, len(pi)), rng.choice(ni, len(ni))])
        for k, s in scores.items():
            for m, v in metrics(np.asarray(s)[idx], y[idx]).items():
                draws[k][m].append(v)
    return {k: {m: np.array(v) for m, v in d.items()} for k, d in draws.items()}


def ci(a):
    return [round(float(np.percentile(a, 2.5)), 4), round(float(np.percentile(a, 97.5)), 4)]


# ------------------------------------------------------------------ nested CV
def simplex(k, step):
    n = int(round(1 / step))
    return np.array([c for c in itertools.product(range(n + 1), repeat=k) if sum(c) == n], float) / n


def stratified_folds(y, k, rng):
    folds = np.empty(len(y), int)
    for cls in (0, 1):
        idx = rng.permutation(np.where(y == cls)[0])
        folds[idx] = np.arange(len(idx)) % k
    return folds


def nested_cv(R, y, repeats, rng, outer_k=5, inner_k=4, step=0.1):
    """Outer AUROC of simplex weights chosen by mean inner-fold AUROC (training data only).
    Equal weights are scored on the same outer folds for a paired comparison."""
    W = simplex(R.shape[1], step)
    eq = np.full(R.shape[1], 1 / R.shape[1])
    res = []
    for rep in range(repeats):
        outer = stratified_folds(y, outer_k, rng)
        for f in range(outer_k):
            tr, te = outer != f, outer == f
            Rtr, ytr = R[tr], y[tr]
            inner = stratified_folds(ytr, inner_k, rng)
            inner_auc = [auroc_cols(Rtr[inner == g] @ W.T, ytr[inner == g]) for g in range(inner_k)]
            w = W[best_index(inner_auc)]                    # ties -> first (lexicographic) weight vector
            yte = y[te]
            res.append({"repeat": rep, "fold": f, "weights": w.round(2).tolist(), "n_pos_test": int(yte.sum()),
                        "auroc_fitted": float(auroc_cols((R[te] @ w)[:, None], yte)[0]),
                        "auroc_equal": float(auroc_cols((R[te] @ eq)[:, None], yte)[0])})
    return res


def summarise_cv(res, names):
    f = np.array([r["auroc_fitted"] for r in res])
    e = np.array([r["auroc_equal"] for r in res])
    W = np.array([r["weights"] for r in res])
    per_rep = pd.DataFrame(res).groupby("repeat")[["auroc_fitted", "auroc_equal"]].mean()
    if np.isnan(f).any() or np.isnan(e).any():          # a single-class outer test fold: AUROC undefined, reported
        raise UndefinedSelection(f"{int(np.isnan(f).sum())} outer test fold(s) have one class; AUROC undefined")
    return {"n_outer_folds": len(res),
            "outer_auroc_fitted_mean": round(float(f.mean()), 4),
            "outer_auroc_equal_mean": round(float(e.mean()), 4),
            "repeat_mean_auroc_fitted_2.5_97.5": ci(per_rep["auroc_fitted"]),
            "repeat_mean_auroc_equal_2.5_97.5": ci(per_rep["auroc_equal"]),
            "fitted_minus_equal_mean": round(float((f - e).mean()), 4),
            "share_folds_fitted_better": round(float((f > e).mean()), 3),
            "weights_mean": dict(zip(names, W.mean(0).round(3).tolist())),
            "weights_sd": dict(zip(names, W.std(0).round(3).tolist()))}


# ------------------------------------------------------------------ weighting matrix
# Added for the 2026-10-19 weighting decision. Every learned model is fitted inside the outer training
# folds only (inner CV for its hyper-parameter); out-of-fold scores are pooled per repeat. Percentile
# ranks are label-free and computed once on all 90 compounds (transductive; documented).
SHRINK = (0.0, 0.25, 0.5, 0.75, 1.0)
LOGIT_C = (0.01, 0.1, 1.0, 10.0)


def trial_groups(root, index):
    """Connected components of compounds that share a pre-cutoff feature trial (evidence dependence)."""
    links = pd.read_csv(os.path.join(root, "data/clinical_maturity_precutoff_clean.csv"))
    links = links[links["compound_name"].isin(index)]
    parent = {c: c for c in index}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for _, g in links.groupby("nct_id")["compound_name"]:
        g = sorted(set(g))
        for o in g[1:]:
            parent[find(o)] = find(g[0])
    ids = {r: i for i, r in enumerate(sorted({find(c) for c in index}))}
    return np.array([ids[find(c)] for c in index])


def _splitter(k, seed, grouped):
    from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold
    return StratifiedGroupKFold(k, shuffle=True, random_state=seed) if grouped else StratifiedKFold(k, shuffle=True, random_state=seed)


def _fit_simplex(R, y, W):
    return W[best_index([auroc_cols(R @ W.T, y)])]


def fit_model(kind, R, y, groups, seed, W):
    """Return a scoring function fitted on (R, y) only; hyper-parameters chosen by inner 4-fold CV."""
    d = R.shape[1]
    eq = np.full(d, 1 / d)
    if kind == "equal":
        return (lambda X: X @ eq), eq
    inner = list(_splitter(4, seed, groups is not None).split(R, y, groups))
    if kind == "simplex":
        w = W[best_index([auroc_cols(R[va] @ W.T, y[va]) for tr, va in inner])]
        return (lambda X: X @ w), w
    if kind == "shrink":
        tot = []
        for tr, va in inner:
            ws = _fit_simplex(R[tr], y[tr], W)
            tot.append([auroc_cols((R[va] @ ((1 - l) * eq + l * ws))[:, None], y[va])[0] for l in SHRINK])
        lam = SHRINK[best_index(tot)]
        w = (1 - lam) * eq + lam * _fit_simplex(R, y, W)
        return (lambda X: X @ w), w
    if kind == "logit_l2":
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        def fit(Xa, ya, c):
            sc = StandardScaler().fit(Xa)                     # fitted on training rows only
            m = LogisticRegression(C=c, max_iter=5000).fit(sc.transform(Xa), ya)
            return sc, m
        tot = []
        for tr, va in inner:
            row = []
            for c in LOGIT_C:
                sc, m = fit(R[tr], y[tr], c)
                row.append(auroc_cols(m.decision_function(sc.transform(R[va]))[:, None], y[va])[0])
            tot.append(row)
        c = LOGIT_C[best_index(tot)]
        sc, m = fit(R, y, c)
        coef = m.coef_[0] / sc.scale_                          # effect per rank unit
        return (lambda X: m.decision_function(sc.transform(X))), coef
    raise ValueError(kind)


def evaluate_fitted(R, y, kinds, repeats, seed, groups=None, step=0.1):
    """Repeated nested CV. Per repeat: pooled out-of-fold AUROC/AUPRC/P@10 for every model, on the same
    outer splits (paired). Also per-fold weights and the ranking each fold's model gives all compounds."""
    W = simplex(R.shape[1], step)
    per_rep = {k: [] for k in kinds}
    fold_w = {k: [] for k in kinds}
    full_scores = {k: [] for k in kinds}
    for rep in range(repeats):
        oof = {k: np.zeros(len(y)) for k in kinds}
        for f, (tr, te) in enumerate(_splitter(5, seed + rep, groups is not None).split(R, y, groups)):
            g = None if groups is None else groups[tr]
            for k in kinds:
                fn, w = fit_model(k, R[tr], y[tr], g, seed + 1000 * rep + f, W)
                s = fn(R)
                oof[k][te] = s[te]
                fold_w[k].append(np.asarray(w, float))
                full_scores[k].append(s)
        for k in kinds:
            per_rep[k].append(metrics(oof[k], y))
    return per_rep, fold_w, full_scores


def _rank_agreement(a, b, k=10):
    top = lambda s: set(np.argsort(-np.asarray(s), kind="mergesort")[:k])
    return float(spearmanr(a, b)[0]), len(top(a) & top(b)) / k


def weighting_matrix(root, out, repeats=20, n_boot=2000, seed=SEED):
    """The experiment matrix behind the weighting decision (docs/VPS_WEIGHTING_DECISION_2026-10-19.md)."""
    os.makedirs(out, exist_ok=True)
    rng = np.random.default_rng(seed)
    base = build(root)
    cor = build(root, molecular="td042_own_target")
    y = base["label"].to_numpy()
    names = {"r_proximity": "proximity", "r_clinical": "clinical", "r_literature": "literature",
             "r_safety": "safety", "r_molecular": "molecular"}
    sets = {"4d": (base, DIMS4), "5d_original_double_count": (base, DIMS5), "5d_td042_corrected": (cor, DIMS5)}
    # --- unfitted equal-weight models on the full cohort (bootstrap CIs, paired to the corrected 5D) ---
    unfitted = {k: v[d].mean(axis=1).to_numpy() for k, (v, d) in sets.items()}
    for d in DIMS5:                                       # leave-one-dimension-out, corrected 5D
        unfitted[f"lodo_without_{names[d]}"] = cor[[x for x in DIMS5 if x != d]].mean(axis=1).to_numpy()
    for d in DIMS5:                                       # each dimension alone
        unfitted[f"single_{names[d]}{'_td042' if d == 'r_molecular' else ''}"] = cor[d].to_numpy()
    unfitted["single_molecular_original"] = base["r_molecular"].to_numpy()
    unfitted["pair_proximity+clinical_cutoff_bounded"] = cor[["r_proximity", "r_clinical"]].mean(axis=1).to_numpy()
    unfitted["group_clinical+literature"] = cor[["r_clinical", "r_literature"]].mean(axis=1).to_numpy()
    unfitted["group_proximity+molecular_mechanism"] = cor[["r_proximity", "r_molecular"]].mean(axis=1).to_numpy()
    boot = bootstrap(unfitted, y, n_boot, rng)
    ref = "5d_td042_corrected"
    tab = {}
    for k, s in unfitted.items():
        m = metrics(s, y)
        sp, top = _rank_agreement(s, unfitted[ref])
        d = boot[k]["auroc"] - boot[ref]["auroc"]
        tab[k] = {**{m_: round(v, 4) for m_, v in m.items()},
                  "auroc_ci95": ci(boot[k]["auroc"]), "auprc_ci95": ci(boot[k]["auprc"]), "p_at_10_ci95": ci(boot[k]["p_at_10"]),
                  "auroc_minus_ref": round(m["auroc"] - metrics(unfitted[ref], y)["auroc"], 4),
                  "auroc_minus_ref_ci95": ci(d), "spearman_vs_ref": round(sp, 4), "top10_overlap_vs_ref": top,
                  "cutoff_bounded": k in ("single_proximity", "single_clinical", "pair_proximity+clinical_cutoff_bounded")}
    # --- learned weights under repeated nested CV (standard and evidence-grouped folds) ---
    groups = trial_groups(root, base.index)
    kinds = ["equal", "simplex", "shrink", "logit_l2"]
    fitted = {}
    for setname, (v, dims) in sets.items():
        R = v[dims].to_numpy()
        for gname, g in (("stratified", None), ("grouped_by_shared_trials", groups)):
            per_rep, fw, fs = evaluate_fitted(R, y, kinds, repeats, seed, g)
            eqfull = R.mean(axis=1)
            res = {}
            for k in kinds:
                a = np.array([m["auroc"] for m in per_rep[k]])
                e = np.array([m["auroc"] for m in per_rep["equal"]])
                stab = [_rank_agreement(s, eqfull) for s in fs[k]]
                W_ = np.array(fw[k])
                res[k] = {"oof_auroc_mean": round(float(a.mean()), 4), "oof_auroc_2.5_97.5": ci(a),
                          "oof_auprc_mean": round(float(np.mean([m["auprc"] for m in per_rep[k]])), 4),
                          "oof_p_at_10_mean": round(float(np.mean([m["p_at_10"] for m in per_rep[k]])), 4),
                          "minus_equal_mean": round(float((a - e).mean()), 4), "minus_equal_2.5_97.5": ci(a - e),
                          "share_repeats_better_than_equal": round(float((a > e).mean()), 3),
                          "weights_mean": dict(zip([names[d] for d in dims], W_.mean(0).round(3).tolist())),
                          "weights_sd": dict(zip([names[d] for d in dims], W_.std(0).round(3).tolist())),
                          "rank_spearman_vs_equal_mean": round(float(np.mean([x[0] for x in stab])), 3),
                          "top10_overlap_vs_equal_mean": round(float(np.mean([x[1] for x in stab])), 3)}
            fitted[f"{setname}|{gname}"] = res
    report = {"generated_by": "scripts/vps_validation_experiments.py --matrix", "seed": seed, "n_boot": n_boot,
              "repeats": repeats, "cohort": {"n": int(len(y)), "positives": int(y.sum()), "prevalence": round(float(y.mean()), 4)},
              "random_ranking_expectation": {"auroc": 0.5, "auprc": round(float(y.mean()), 4), "p_at_10": round(float(y.mean()), 4)},
              "n_trial_groups": int(len(set(groups))), "largest_trial_group": int(np.bincount(groups).max()),
              "reference_model": ref, "unfitted": tab, "fitted_nested_cv": fitted,
              "protocol": {"outer": "5-fold stratified (or StratifiedGroupKFold on shared-trial components), repeated",
                           "inner": "4-fold on the outer training rows; chooses simplex weights / shrinkage lambda / C",
                           "pooled": "out-of-fold scores pooled per repeat; paired with equal weights on the same splits",
                           "p_at_10": "precision among the 10 highest scores, ties at the boundary averaged",
                           "bootstrap": "stratified by label, paired across models, resampling unit = compound"}}
    with open(os.path.join(out, "weighting_matrix.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    rows = [{"model": k, **{x: v[x] for x in ("auroc", "auroc_ci95", "auprc", "p_at_10", "auroc_minus_ref", "auroc_minus_ref_ci95",
                                              "spearman_vs_ref", "top10_overlap_vs_ref", "cutoff_bounded")}} for k, v in tab.items()]
    pd.DataFrame(rows).to_csv(os.path.join(out, "unfitted_models.csv"), index=False)
    pd.DataFrame([{"features|folds": fk, "method": m, **{x: v[x] for x in ("oof_auroc_mean", "oof_auroc_2.5_97.5", "minus_equal_mean",
                   "minus_equal_2.5_97.5", "share_repeats_better_than_equal", "rank_spearman_vs_equal_mean",
                   "top10_overlap_vs_equal_mean", "weights_mean", "weights_sd")}}
                  for fk, r in fitted.items() for m, v in r.items()]).to_csv(os.path.join(out, "fitted_models.csv"), index=False)
    return report


# ------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="data/_runs/validation_20261019")
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--repeats", type=int, default=20)
    ap.add_argument("--matrix", action="store_true", help="run the weighting experiment matrix instead")
    a = ap.parse_args(argv)
    if a.matrix:
        out = a.out if a.out != "data/_runs/validation_20261019" else "data/_runs/vps_weighting_20261019"
        rep = weighting_matrix(a.root, out, a.repeats, a.boot)
        print(json.dumps({k: rep[k] for k in ("cohort", "n_trial_groups", "largest_trial_group")}))
        return 0
    os.makedirs(a.out, exist_ok=True)
    rng = np.random.default_rng(SEED)

    base = build(a.root)
    saved = pd.read_csv(os.path.join(a.root, "data/vps_scores_v2.csv")).set_index("compound_name").loc[base.index]
    diff = float(max((base[d] - saved[d]).abs().max() for d in DIMS5))
    assert diff < 1e-12 and (base["label"] == saved["label"]).all(), f"baseline not reproduced ({diff})"
    y = base["label"].to_numpy()

    variants = {"baseline": base,
                "td042_own_target": build(a.root, molecular="td042_own_target"),
                "td041_neutral_proximity": build(a.root, proximity_missing="neutral"),
                "td040_midrank": build(a.root, convention="midrank")}
    scores = {}
    for k, v in variants.items():
        scores[f"{k}:5d"] = v[DIMS5].mean(axis=1).to_numpy()
    scores["baseline:4d"] = base[DIMS4].mean(axis=1).to_numpy()
    scores["td042_own_target:molecular_only"] = variants["td042_own_target"]["r_molecular"].to_numpy()
    scores["baseline:molecular_only"] = base["r_molecular"].to_numpy()
    # TD-033: only proximity (Hetionet 2017) and clinical (pre-cutoff trials) are cutoff-bounded
    scores["leakage_bounded:proximity+clinical"] = base[["r_proximity", "r_clinical"]].mean(axis=1).to_numpy()
    scores["leakage_bounded:proximity+clinical+molecular"] = base[["r_proximity", "r_clinical", "r_molecular"]].mean(axis=1).to_numpy()

    point = {k: {m: round(v, 4) for m, v in metrics(s, y).items()} for k, s in scores.items()}
    boot = bootstrap(scores, y, a.boot, rng)
    for k in scores:
        for m in ("auroc", "auprc", "p_at_10"):
            point[k][m + "_ci95"] = ci(boot[k][m])
    pairs = [("baseline:5d", "baseline:4d"), ("baseline:5d", "td042_own_target:5d"), ("td042_own_target:5d", "baseline:4d"),
             ("baseline:5d", "td041_neutral_proximity:5d"), ("baseline:5d", "td040_midrank:5d"),
             ("baseline:5d", "leakage_bounded:proximity+clinical")]
    paired = {}
    for x, z in pairs:
        d = boot[x]["auroc"] - boot[z]["auroc"]
        paired[f"{x} - {z}"] = {"auroc_diff": round(point[x]["auroc"] - point[z]["auroc"], 4), "ci95": ci(d),
                                "share_boot_gt0": round(float((d > 0).mean()), 3)}

    # TD-042 lineage detail
    v42 = variants["td042_own_target"]
    lineage = []
    with open(os.path.join(a.root, "data/molecular_pathway_evidence.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["drug"] not in base.index or not r.get("scoring"):
                continue
            comp = r["scoring"]["components"]
            pc2, sh2, n = own_target_pathway_component(r)
            if abs(pc2 - comp["pathway_overlap"]) > 1e-6:          # published components are rounded to 6 dp
                own = sorted({t.get("gene_symbol") for t in r["targets"]})
                lineage.append({"compound": r["drug"], "label": int(base.loc[r["drug"], "label"]), "targets": "|".join(own),
                                "direct_component": comp["direct_target_disease"],
                                "pathway_component_published": comp["pathway_overlap"],
                                "pathway_component_excl_own_target": round(pc2, 6), "n_pathways": n,
                                "score_published": r["molecular_plausibility_score"],
                                "score_excl_own_target": round(0.6 * comp["direct_target_disease"] + 0.4 * pc2, 6),
                                "rank_published": round(float(base.loc[r["drug"], "r_molecular"]), 4),
                                "rank_excl_own_target": round(float(v42.loc[r["drug"], "r_molecular"]), 4)})
    lin = pd.DataFrame(lineage).sort_values("score_published", ascending=False)
    lin.to_csv(os.path.join(a.out, "td042_lineage.csv"), index=False)
    mol_measured = base["molecular_raw"].notna()
    comps = []
    with open(os.path.join(a.root, "data/molecular_pathway_evidence.jsonl"), encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("scoring"):
                c = r["scoring"]["components"]
                comps.append((c["direct_target_disease"], c["pathway_overlap"],
                              own_target_pathway_component(r)[0]))
    comps = np.array(comps)
    td042 = {"n_compounds_changed": len(lin), "positives_among_changed": int(lin["label"].sum()) if len(lin) else 0,
             "n_changed_with_pathway_component_1_published": int((lin["pathway_component_published"] == 1).sum()),
             "n_changed_with_pathway_component_0_after": int((lin["pathway_component_excl_own_target"] == 0).sum()),
             "spearman_direct_vs_pathway_published": round(float(spearmanr(comps[:, 0], comps[:, 1])[0]), 3),
             "spearman_direct_vs_pathway_excl_own_target": round(float(spearmanr(comps[:, 0], comps[:, 2])[0]), 3),
             "n_scored_records": int(len(comps)), "n_molecular_measured_in_pool": int(mol_measured.sum())}

    # TD-041 / TD-040 detail
    td041 = {"compounds": sorted(base.index[base["proximity_missing"]]),
             "r_proximity_median_imputed": base.loc[base["proximity_missing"], "r_proximity"].round(4).tolist(),
             "r_proximity_neutral": variants["td041_neutral_proximity"].loc[base["proximity_missing"], "r_proximity"].round(4).tolist()}
    rk = lambda s: pd.Series(s, index=base.index).rank(ascending=False, method="first")
    td040 = {"rank_changes_top20": int((rk(scores["baseline:5d"]).le(20) != rk(scores["td040_midrank:5d"]).le(20)).sum()),
             "max_abs_rank_change": int((rk(scores["baseline:5d"]) - rk(scores["td040_midrank:5d"])).abs().max()),
             "spearman_vs_baseline": round(float(spearmanr(scores["baseline:5d"], scores["td040_midrank:5d"])[0]), 4)}

    # repeated nested CV (selection on training folds only)
    cv = {}
    for name, var, dims in (("5d", base, DIMS5), ("4d", base, DIMS4), ("5d_td042", v42, DIMS5)):
        res = nested_cv(var[dims].to_numpy(), y, a.repeats, rng)
        cv[name] = summarise_cv(res, dims)
        pd.DataFrame(res).to_csv(os.path.join(a.out, f"nested_cv_{name}.csv"), index=False)

    report = {"generated_by": "scripts/vps_validation_experiments.py", "seed": SEED, "n_boot": a.boot,
              "cv": {"repeats": a.repeats, "outer_k": 5, "inner_k": 4, "weight_grid": "simplex step 0.1, nonnegative, sum 1"},
              "cohort": {"n": int(len(y)), "positives": int(y.sum()), "prevalence": round(float(y.mean()), 4)},
              "baseline_reproduction_max_abs_diff": diff,
              "metrics": point, "paired_auroc": paired, "td042": td042, "td041": td041, "td040": td040,
              "nested_cv": cv,
              "notes": ["Percentile ranks and imputation are computed once on all 90 compounds (label-free, transductive).",
                        "precision@10 averages over tie orders at the boundary.",
                        "Bootstrap is stratified by label; differences are paired on the same resamples."]}
    with open(os.path.join(a.out, "vps_validation.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    pd.DataFrame({k: v for k, v in scores.items()}, index=base.index).assign(label=y).to_csv(
        os.path.join(a.out, "variant_scores.csv"))
    print(json.dumps({k: report[k] for k in ("cohort", "metrics", "paired_auroc", "td042", "td041", "td040", "nested_cv")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
