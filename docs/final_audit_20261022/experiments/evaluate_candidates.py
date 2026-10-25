"""Evaluate candidate result sets with one methodology (final audit 2026-10-22).
AUROC / AUPRC on VPS_equal_5d (and VPS_equal = 4D), 2,000-resample percentile bootstrap (seed 42, as the approved
evaluation), paired difference vs the approved score on the compounds both contain. No model is tuned; nothing is
selected by its metric (the primary is chosen by validity criteria fixed in SCIENTIFIC_DECISION_LOG.md).

    evaluate_candidates.py APPROVED_SCORES CANDIDATE_DIR [CANDIDATE_DIR ...] --out FILE.json
"""
import argparse
import json
import os

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

SEED, N = 42, 2000


def ci(y, s, fn):
    rng = np.random.default_rng(SEED)
    y, s = np.asarray(y), np.asarray(s)
    v = []
    for _ in range(N):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() != y[i].max():
            v.append(fn(y[i], s[i]))
    return [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)]


def paired(y, a, b):
    rng = np.random.default_rng(SEED)
    y, a, b = map(np.asarray, (y, a, b))
    d = []
    for _ in range(N):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() != y[i].max():
            d.append(roc_auc_score(y[i], a[i]) - roc_auc_score(y[i], b[i]))
    return {"diff": round(float(roc_auc_score(y, a) - roc_auc_score(y, b)), 4),
            "ci95": [round(float(np.percentile(d, 2.5)), 4), round(float(np.percentile(d, 97.5)), 4)]}


def evaluate(df, approved=None):
    y = df.label.values
    out = {"n": int(len(df)), "positives": int(y.sum()), "prevalence": round(float(y.mean()), 4)}
    for col, key in (("VPS_equal_5d", "5d"), ("VPS_equal", "4d")):
        s = df[col].values
        out[key] = {"auroc": round(float(roc_auc_score(y, s)), 4), "auroc_ci95": ci(y, s, roc_auc_score),
                    "auprc": round(float(average_precision_score(y, s)), 4), "auprc_ci95": ci(y, s, average_precision_score)}
    out["5d_minus_4d"] = paired(y, df.VPS_equal_5d.values, df.VPS_equal.values)
    if approved is not None:
        m = df.merge(approved[["compound_name", "VPS_equal_5d", "label"]], on="compound_name", suffixes=("", "_appr"))
        same_label = bool((m.label == m.label_appr).all())
        out["vs_approved_on_shared_compounds"] = {"n_shared": int(len(m)), "labels_identical": same_label,
                                                   **(paired(m.label.values, m.VPS_equal_5d.values, m.VPS_equal_5d_appr.values)
                                                      if same_label and m.label.nunique() == 2 else {})}
        top = lambda d: list(d.sort_values("VPS_equal_5d", ascending=False).compound_name.head(10))
        out["top10"] = top(df)
        out["top10_overlap_with_approved"] = len(set(top(df)) & set(top(approved)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("approved")
    ap.add_argument("candidates", nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    appr = pd.read_csv(a.approved)
    res = {"approved_reference": evaluate(appr)}
    for c in a.candidates:
        df = pd.read_csv(os.path.join(c, "out", "vps_scores_v2.csv"))
        res[os.path.relpath(c, os.path.dirname(os.path.dirname(c)))] = evaluate(df, appr)
    with open(a.out, "w") as fh:
        json.dump(res, fh, indent=1)
    for k, v in res.items():
        p = v.get("vs_approved_on_shared_compounds", {})
        print(f"{k:42s} n={v['n']:3d} pos={v['positives']:2d} 5D AUROC {v['5d']['auroc']:.3f} {v['5d']['auroc_ci95']} "
              f"AUPRC {v['5d']['auprc']:.3f} | 4D {v['4d']['auroc']:.3f} | 5D-4D {v['5d_minus_4d']['diff']:+.3f} {v['5d_minus_4d']['ci95']}"
              + (f" | vs appr {p.get('diff', 'n/a')} {p.get('ci95', '')} (n={p.get('n_shared')})" if p else ""))


if __name__ == "__main__":
    main()
