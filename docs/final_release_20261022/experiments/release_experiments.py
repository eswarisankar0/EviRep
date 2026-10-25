"""Final-release experiments (2026-10-21/22). READ-ONLY with respect to every approved artefact: it reads
data/vps_scores_v2.csv and saved sensitivity outputs, and writes only to the folder given by --out.

E1  Fully dated 5D: every input dated before the 2021-01-01 cutoff where a dated source exists.
      proximity  = approved r_proximity (Hetionet 2017)
      clinical   = approved r_clinical (pre-cutoff trials)
      literature = cutoff-bounded primary-record count (stage 04p; vps_literature_cutoff_sensitivity.bounded_measures)
      safety     = label version in force at the cutoff (05h); "strict" = others neutral, "mixed" = current label
      molecular  = Open Targets 20.11 + ChEMBL 2020-06 targets (vps_molecular_historical per_drug)
    Equal weights, legacy percentile ranks, neutral 0.5 for unmeasured safety/molecular, median for missing
    literature -- the approved rules. Nothing is tuned.
E2  Weighting under repeated stratified 5-fold CV (20 repeats, seeds 0-19), identical folds for every model:
      equal weights (no fitting) vs L2 logistic regression on the 5 approved ranks, C chosen by inner 4-fold CV
      inside each training fold. Pooled out-of-fold AUROC per repeat; paired differences; coefficient stability.
    Note: the approved ranks are a label-free transform computed on the whole pool (transductive), so no label
    information leaks through them.
E3  Weight sensitivity: AUROC of 2,000 Dirichlet(1) weight vectors on the approved ranks (no selection).

    ./venv/bin/python docs/final_release_20261022/experiments/release_experiments.py --out docs/final_release_20261022/experiments/out
"""
import argparse
import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SEED, N_BOOT = 42, 2000
DIMS = ["r_proximity", "r_clinical", "r_literature", "r_safety", "r_molecular"]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    spec.loader.exec_module(mod)
    return mod


def pct(s, invert=False):
    """Approved legacy convention (06_vps_fusion.percentile_rank): average rank / n over non-missing values."""
    r = s.rank(pct=True, method="average")
    return 1 - r if invert else r


def boot(y, s, fn, n=N_BOOT, seed=SEED):
    rng = np.random.default_rng(seed)
    y, s = np.asarray(y), np.asarray(s)
    vals = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() == y[i].max():
            continue
        vals.append(fn(y[i], s[i]))
    return [round(float(np.percentile(vals, 2.5)), 4), round(float(np.percentile(vals, 97.5)), 4)]


def paired(y, a, b, n=N_BOOT, seed=SEED):
    rng = np.random.default_rng(seed)
    y, a, b = map(np.asarray, (y, a, b))
    d = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() == y[i].max():
            continue
        d.append(roc_auc_score(y[i], a[i]) - roc_auc_score(y[i], b[i]))
    d = np.array(d)
    return {"diff": round(float(roc_auc_score(y, a) - roc_auc_score(y, b)), 4),
            "ci95": [round(float(np.percentile(d, 2.5)), 4), round(float(np.percentile(d, 97.5)), 4)],
            "p_diff_gt_0": round(float((d > 0).mean()), 3)}


def metrics(y, s):
    return {"auroc": round(float(roc_auc_score(y, s)), 4), "auroc_ci95": boot(y, s, roc_auc_score),
            "auprc": round(float(average_precision_score(y, s)), 4), "auprc_ci95": boot(y, s, average_precision_score)}


def e1(v):
    lit = _load("lcs", "scripts/vps_literature_cutoff_sensitivity.py")
    bm = lit.bounded_measures(ROOT).reindex(v.compound_name)
    mixed, strict, n_scored = lit.bounded_safety(ROOT, v.compound_name)
    with open(os.path.join(ROOT, "data/_runs/molecular_historical_20261020/molecular_historical.json"), encoding="utf-8") as fh:
        mh = pd.DataFrame(json.load(fh)["per_drug"]).set_index("compound_name").reindex(v.compound_name)
    d = pd.DataFrame({"compound_name": v.compound_name.values, "label": v.label.values,
                      "r_proximity": v.r_proximity.values, "r_clinical": v.r_clinical.values})
    litc = bm["lit_bounded_count"].values
    litc = np.where(np.isnan(litc), np.nanmedian(litc), litc)
    d["r_literature_bounded"] = pct(pd.Series(litc))
    for name, s in (("strict", strict), ("mixed", mixed)):
        d[f"r_safety_cutoff_{name}"] = pct(pd.Series(s.values), invert=True).fillna(0.5).values
    mol = mh["molecular_2020_chembl2006"].astype(float)
    no_target = mh["n_targets_chembl2006"].fillna(0).astype(float) == 0
    mol = mol.where(~no_target.values)
    d["r_molecular_dated"] = pct(pd.Series(mol.values)).fillna(0.5).values
    y = d.label.values
    out = {"n": int(len(d)), "positives": int(y.sum()), "safety_labels_scored_at_cutoff": int(n_scored),
           "molecular_dated_no_target": int(no_target.sum()), "models": {}}
    approved = v.VPS_equal_5d.values
    for name, cols in {
        "approved 5D (reference)": None,
        "fully dated 5D (safety strict)": ["r_proximity", "r_clinical", "r_literature_bounded", "r_safety_cutoff_strict", "r_molecular_dated"],
        "fully dated 5D (safety mixed)": ["r_proximity", "r_clinical", "r_literature_bounded", "r_safety_cutoff_mixed", "r_molecular_dated"],
        "fully dated 4D (no molecular, safety mixed)": ["r_proximity", "r_clinical", "r_literature_bounded", "r_safety_cutoff_mixed"],
        "dated pair (proximity + clinical)": ["r_proximity", "r_clinical"],
    }.items():
        s = approved if cols is None else d[cols].mean(axis=1).values
        m = metrics(y, s)
        if cols is not None:
            m["paired_vs_approved"] = paired(y, s, approved)
        out["models"][name] = m
    out["prevalence"] = round(float(y.mean()), 4)
    return out, d


def e2(v, repeats=20):
    X, y = v[DIMS].values, v.label.values
    res, coefs, chosen_c = [], [], []
    for rep in range(repeats):
        skf = StratifiedKFold(5, shuffle=True, random_state=rep)
        oof_eq, oof_lr = np.zeros(len(y)), np.zeros(len(y))
        for tr, te in skf.split(X, y):
            oof_eq[te] = X[te].mean(axis=1)
            best_c, best = None, -1
            for c in (0.01, 0.1, 1.0, 10.0):              # inner CV inside the training fold only
                inner = StratifiedKFold(4, shuffle=True, random_state=rep)
                sc = []
                for itr, ite in inner.split(X[tr], y[tr]):
                    m = LogisticRegression(C=c, max_iter=1000).fit(X[tr][itr], y[tr][itr])
                    if y[tr][ite].min() != y[tr][ite].max():
                        sc.append(roc_auc_score(y[tr][ite], m.decision_function(X[tr][ite])))
                if sc and np.mean(sc) > best:
                    best, best_c = float(np.mean(sc)), c
            m = LogisticRegression(C=best_c, max_iter=1000).fit(X[tr], y[tr])
            oof_lr[te] = m.decision_function(X[te])
            coefs.append(m.coef_[0].tolist())
            chosen_c.append(best_c)
        res.append({"repeat": rep, "auroc_equal": roc_auc_score(y, oof_eq), "auroc_logreg": roc_auc_score(y, oof_lr)})
    r = pd.DataFrame(res)
    r["diff"] = r.auroc_logreg - r.auroc_equal
    co = pd.DataFrame(coefs, columns=DIMS)
    return {
        "design": "repeated stratified 5-fold CV x20 (seeds 0-19); identical folds for both models; logistic C in {0.01,0.1,1,10} chosen by inner 4-fold CV within each training fold; pooled out-of-fold AUROC per repeat",
        "equal_weights_oof_auroc": {"mean": round(r.auroc_equal.mean(), 4), "min": round(r.auroc_equal.min(), 4), "max": round(r.auroc_equal.max(), 4)},
        "logreg_oof_auroc": {"mean": round(r.auroc_logreg.mean(), 4), "min": round(r.auroc_logreg.min(), 4), "max": round(r.auroc_logreg.max(), 4)},
        "diff_logreg_minus_equal": {"mean": round(r["diff"].mean(), 4), "min": round(r["diff"].min(), 4), "max": round(r["diff"].max(), 4),
                                     "repeats_logreg_better": int((r["diff"] > 0).sum()), "repeats": repeats},
        "coefficients_across_100_fits": {d: {"mean": round(co[d].mean(), 3), "sd": round(co[d].std(), 3),
                                              "share_negative": round(float((co[d] < 0).mean()), 2)} for d in DIMS},
        "chosen_C_counts": {str(k): int(v) for k, v in pd.Series(chosen_c).value_counts().items()},
        "note_equal_weights": "equal weights are not fitted, so their pooled OOF AUROC equals the in-sample 0.775 (ranks are label-free)",
    }, r


def e3(v, n=2000):
    rng = np.random.default_rng(SEED)
    X, y = v[DIMS].values, v.label.values
    au = np.array([roc_auc_score(y, X @ w) for w in rng.dirichlet(np.ones(5), n)])
    return {"n_weight_vectors": n, "distribution": "Dirichlet(1,1,1,1,1) over the 5 approved ranks; no selection",
            "auroc_percentiles": {p: round(float(np.percentile(au, p)), 4) for p in (2.5, 10, 25, 50, 75, 90, 97.5)},
            "equal_weights_auroc": round(float(roc_auc_score(y, X.mean(axis=1))), 4),
            "share_of_vectors_beating_equal": round(float((au > roc_auc_score(y, X.mean(axis=1))).mean()), 3)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    v = pd.read_csv(os.path.join(ROOT, "data/vps_scores_v2.csv"))
    assert len(v) == 90 and int(v.label.sum()) == 14
    r1, d1 = e1(v)
    r2, t2 = e2(v)
    r3 = e3(v)
    with open(os.path.join(a.out, "release_experiments.json"), "w", encoding="utf-8") as fh:
        json.dump({"E1_fully_dated_5d": r1, "E2_weighting_cv": r2, "E3_weight_sensitivity": r3}, fh, indent=1)
    d1.to_csv(os.path.join(a.out, "E1_fully_dated_ranks.csv"), index=False)
    t2.to_csv(os.path.join(a.out, "E2_per_repeat.csv"), index=False)
    print(json.dumps({"E1": {k: (m["auroc"], m["auroc_ci95"], m.get("paired_vs_approved")) for k, m in r1["models"].items()},
                      "E2": {k: r2[k] for k in ("equal_weights_oof_auroc", "logreg_oof_auroc", "diff_logreg_minus_equal")},
                      "E3": r3["auroc_percentiles"]}, indent=1))


if __name__ == "__main__":
    main()
