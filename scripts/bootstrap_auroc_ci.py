"""
Reproducible bootstrap confidence intervals for VPS AUROC (E-015 / TD-020).

The CIs quoted in README / TECHNICAL_DEBT (difference +0.059, 95% CI
[-0.024, +0.150]) were produced by code that was never committed and cannot be
reproduced. This script is the canonical, versioned procedure from 2026-10-13:

  * paired, non-parametric percentile bootstrap over COMPOUNDS (rows);
  * each resample draws n rows with replacement using
    numpy.random.default_rng(seed); resamples containing a single class are
    skipped and COUNTED (reported as n_skipped), not silently replaced;
  * the same resample indices are used for every column, so the difference
    CI is paired;
  * percentile interval: [alpha/2, 1 - alpha/2] quantiles (numpy "linear").

Read-only: it reads data/vps_scores_v2.csv and prints; it writes a CSV only
when --out is given. No network.

    ./venv/bin/python scripts/bootstrap_auroc_ci.py
    ./venv/bin/python scripts/bootstrap_auroc_ci.py --a VPS_equal_5d --b VPS_equal --n 2000 --seed 42
"""

import argparse
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

DEFAULT_SCORES = "data/vps_scores_v2.csv"


def paired_bootstrap(labels, score_a, score_b, n_boot=2000, seed=42, alpha=0.05):
    """Return a dict with point estimates and percentile CIs for AUROC(a),
    AUROC(b) and AUROC(a) - AUROC(b), plus the procedure's parameters."""
    y = np.asarray(labels, dtype=int)
    a = np.asarray(score_a, dtype=float)
    b = np.asarray(score_b, dtype=float)
    if not (len(y) == len(a) == len(b)):
        raise ValueError("labels and scores must have equal length")
    if np.isnan(a).any() or np.isnan(b).any():
        raise ValueError("scores contain NaN; refusing to bootstrap over missing values")
    if len(set(y)) != 2:
        raise ValueError("labels must contain both classes")
    rng = np.random.default_rng(seed)
    n = len(y)
    auc_a, auc_b, skipped = [], [], 0
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        if y[idx].min() == y[idx].max():
            skipped += 1
            continue
        auc_a.append(roc_auc_score(y[idx], a[idx]))
        auc_b.append(roc_auc_score(y[idx], b[idx]))
    auc_a, auc_b = np.array(auc_a), np.array(auc_b)
    diff = auc_a - auc_b
    q = [alpha / 2, 1 - alpha / 2]

    def ci(x):
        lo, hi = np.quantile(x, q)
        return float(lo), float(hi)

    return {
        "n": n, "n_positive": int(y.sum()), "n_boot": n_boot, "n_used": len(diff), "n_skipped": skipped,
        "seed": seed, "alpha": alpha, "rng": "numpy.random.default_rng", "interval": "percentile",
        "auroc_a": float(roc_auc_score(y, a)), "auroc_b": float(roc_auc_score(y, b)),
        "diff": float(roc_auc_score(y, a) - roc_auc_score(y, b)),
        "ci_a": ci(auc_a), "ci_b": ci(auc_b), "ci_diff": ci(diff),
        "p_diff_gt_0": float((diff > 0).mean()),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--scores", default=DEFAULT_SCORES)
    ap.add_argument("--a", default="VPS_equal_5d", help="score column A")
    ap.add_argument("--b", default="VPS_equal", help="score column B (A - B is reported)")
    ap.add_argument("--label", default="label")
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--out", default=None, help="optional CSV to write the result row to")
    args = ap.parse_args(argv)

    df = pd.read_csv(args.scores)
    missing = [c for c in (args.a, args.b, args.label) if c not in df.columns]
    if missing:
        sys.exit(f"{args.scores} lacks columns {missing}")
    if df["compound_name"].duplicated().any() if "compound_name" in df.columns else False:
        sys.exit(f"{args.scores} has duplicate compound rows; refusing to bootstrap")
    r = paired_bootstrap(df[args.label], df[args.a], df[args.b], args.n, args.seed, args.alpha)
    pct = int(round((1 - args.alpha) * 100))
    print(f"{args.scores}: n={r['n']} ({r['n_positive']} positive); {r['n_used']}/{r['n_boot']} resamples used "
          f"({r['n_skipped']} single-class skipped); default_rng(seed={r['seed']}); percentile interval")
    print(f"AUROC {args.a}: {r['auroc_a']:.4f}  {pct}% CI [{r['ci_a'][0]:.4f}, {r['ci_a'][1]:.4f}]")
    print(f"AUROC {args.b}: {r['auroc_b']:.4f}  {pct}% CI [{r['ci_b'][0]:.4f}, {r['ci_b'][1]:.4f}]")
    print(f"Paired difference: {r['diff']:+.4f}  {pct}% CI [{r['ci_diff'][0]:+.4f}, {r['ci_diff'][1]:+.4f}]  "
          f"P(diff>0) = {r['p_diff_gt_0']:.3f}")
    if args.out:
        row = {k: v for k, v in r.items() if not isinstance(v, tuple)}
        for k in ("ci_a", "ci_b", "ci_diff"):
            row[k + "_low"], row[k + "_high"] = r[k]
        row.update({"a": args.a, "b": args.b, "scores": args.scores})
        pd.DataFrame([row]).to_csv(args.out, index=False)
        print(f"wrote {args.out}")
    return r


if __name__ == "__main__":
    main()
