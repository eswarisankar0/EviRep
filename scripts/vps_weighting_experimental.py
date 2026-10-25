"""
Learned versus equal weights for the EXPERIMENTAL cutoff-bounded feature sets (mission Step C/D). Read-only;
outputs to --out (default data/_runs/vps_weighting_experimental_20261020/). Nothing here is published.

Same protocol as the approved weighting matrix (scripts/vps_validation_experiments.py --matrix,
docs/VPS_WEIGHTING_DECISION_2026-10-19.md): repeated 5-fold outer CV, 4-fold inner CV on the outer training rows
only (simplex grid step 0.1, shrinkage toward equal weights, L2 logistic regression), standard and
evidence-grouped folds (compounds sharing a pre-cutoff trial stay together), out-of-fold scores pooled per
repeat and paired with equal weights on the same splits.

Feature sets (each dimension a label-free percentile rank over the 90 compounds, so the transform uses no label):
  td042_bounded_lit_safety   5D with the TD-042 molecular rule, literature = 04p cutoff-bounded primary-record
                             count, safety = label at the cutoff where 05h found one (current label otherwise)
  bounded_4d                 proximity, clinical, bounded literature, safety at cutoff (no molecular: the
                             Open Targets snapshot cannot be made cutoff-bounded, see molecular_snapshot run)
  bounded_trio               proximity, clinical, bounded literature (every input bounded at the cutoff)

    ./venv/bin/python scripts/vps_weighting_experimental.py [--repeats 20]
"""
import argparse
import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vve = _load("vve", "vps_validation_experiments.py")
lit = _load("vlcs", "vps_literature_cutoff_sensitivity.py")

KINDS = ["equal", "simplex", "shrink", "logit_l2"]


def feature_sets(root):
    cor = vve.build(root, molecular="td042_own_target")
    meas = lit.bounded_measures(root).reindex(cor.index)
    v = meas["lit_bounded_count"]
    r_lit = vve.pct(v.fillna(v.median()), False, "legacy")
    mixed, _, _ = lit.bounded_safety(root, cor.index)
    r_saf = vve.pct(mixed, True, "legacy")
    f = cor.assign(r_literature=r_lit, r_safety=r_saf)
    sets = {"td042_bounded_lit_safety": f[vve.DIMS5],
            "bounded_4d": f[vve.DIMS4],
            "bounded_trio": f[["r_proximity", "r_clinical", "r_literature"]]}
    return sets, cor["label"].to_numpy(), cor.index


def run(root=".", repeats=20, seed=vve.SEED):
    sets, y, index = feature_sets(root)
    groups = vve.trial_groups(root, index)
    out = {}
    for name, F in sets.items():
        R = F.to_numpy()
        dims = [c.replace("r_", "") for c in F.columns]
        for gname, g in (("stratified", None), ("grouped_by_shared_trials", groups)):
            per_rep, fw, fs = vve.evaluate_fitted(R, y, KINDS, repeats, seed, g)
            eq = np.array([m["auroc"] for m in per_rep["equal"]])
            res = {}
            for k in KINDS:
                a = np.array([m["auroc"] for m in per_rep[k]])
                W = np.array(fw[k])
                stab = [vve._rank_agreement(s, R.mean(axis=1)) for s in fs[k]]
                res[k] = {"oof_auroc_mean": round(float(a.mean()), 4), "oof_auroc_2.5_97.5": vve.ci(a),
                          "oof_auprc_mean": round(float(np.mean([m["auprc"] for m in per_rep[k]])), 4),
                          "oof_p_at_10_mean": round(float(np.mean([m["p_at_10"] for m in per_rep[k]])), 4),
                          "minus_equal_mean": round(float((a - eq).mean()), 4), "minus_equal_2.5_97.5": vve.ci(a - eq),
                          "share_repeats_better_than_equal": round(float((a > eq).mean()), 3),
                          "weights_mean": dict(zip(dims, W.mean(0).round(3).tolist())),
                          "weights_sd": dict(zip(dims, W.std(0).round(3).tolist())),
                          "rank_spearman_vs_equal_mean": round(float(np.mean([x[0] for x in stab])), 3),
                          "top10_overlap_vs_equal_mean": round(float(np.mean([x[1] for x in stab])), 3)}
            out[f"{name}|{gname}"] = res
    return {"generated_by": "scripts/vps_weighting_experimental.py", "seed": seed, "repeats": repeats,
            "cohort": {"n": int(len(y)), "positives": int(y.sum()), "prevalence": round(float(y.mean()), 4)},
            "n_trial_groups": int(len(set(groups))), "fitted_nested_cv": out,
            "note": "experimental, cutoff-bounded variants; not the approved baseline; not published"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="data/_runs/vps_weighting_experimental_20261020")
    ap.add_argument("--repeats", type=int, default=20)
    a = ap.parse_args(argv)
    res = run(a.root, a.repeats)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "weighting_experimental.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    rows = [{"features|folds": fk, "method": m, **v} for fk, r in res["fitted_nested_cv"].items() for m, v in r.items()]
    pd.DataFrame(rows).to_csv(os.path.join(a.out, "weighting_experimental.csv"), index=False)
    for r in rows:
        print(f"{r['features|folds']:<52} {r['method']:<9} AUROC {r['oof_auroc_mean']:.3f} {r['oof_auroc_2.5_97.5']} "
              f"d_eq {r['minus_equal_mean']:+.3f} better {r['share_repeats_better_than_equal']:.2f} "
              f"top10 {r['top10_overlap_vs_equal_mean']:.2f} w_sd {r['weights_sd']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
