"""Compare a candidate (unapproved) result set with the approved one on the identical cohort and labels.

Writes a comparison JSON next to the candidate. It never touches the approved files and never adopts anything.
Procedure (identical to scripts/vps_evaluation_report.py so the numbers are comparable):
  * AUROC: Mann-Whitney statistic, ties counted 1/2 (pair counting).
  * AUPRC: step-wise average precision with tied scores grouped (= sklearn average_precision_score).
  * 95% CI: ordinary percentile bootstrap over compounds, numpy default_rng(42), 2,000 draws, single-class draws
    skipped and counted.
  * Paired differences: the same resampled indices for both scores; difference per draw; 2.5/97.5% quantiles.
    The share of draws above zero is reported as such; it is not a p-value.
Refuses to compare when the compounds or the labels differ.

  ./venv/bin/python scripts/compare_result_sets.py --candidate data/_candidates/td042_v1/root/data/vps_scores_v2.csv \
      --out data/_candidates/td042_v1/comparison.json --name td042_v1 --rule "..."
"""
import argparse
import csv
import hashlib
import json
import os
from datetime import datetime, timezone

import numpy as np

N_BOOT, SEED = 2000, 42


def _md5(p):
    with open(p, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def auroc(y, s):
    pos = [v for v, t in zip(s, y) if t == 1]
    neg = [v for v, t in zip(s, y) if t == 0]
    if not pos or not neg:
        return None
    return sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))


def auprc(y, s):
    npos = sum(y)
    if npos == 0:
        return None
    order = sorted(range(len(s)), key=lambda i: -s[i])
    tp = fp = 0; prev = out = 0.0; k = 0
    while k < len(order):
        j = k
        while j + 1 < len(order) and s[order[j + 1]] == s[order[k]]:
            j += 1
        for t in range(k, j + 1):
            tp += y[order[t]]; fp += 1 - y[order[t]]
        out += (tp / npos - prev) * tp / (tp + fp); prev = tp / npos; k = j + 1
    return out


def _draws(n):
    rng = np.random.default_rng(SEED)
    return [rng.integers(0, n, n) for _ in range(N_BOOT)]


def ci(y, s, metric):
    ya, sa = np.asarray(y), np.asarray(s); vals = []; skipped = 0
    for i in _draws(len(y)):
        if ya[i].min() == ya[i].max():
            skipped += 1; continue
        vals.append(metric(list(ya[i]), list(sa[i])))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))], skipped


def paired(y, a, b):
    ya, aa, ba = map(np.asarray, (y, a, b)); d = []
    for i in _draws(len(y)):
        if ya[i].min() == ya[i].max():
            continue
        d.append(auroc(list(ya[i]), list(aa[i])) - auroc(list(ya[i]), list(ba[i])))
    d = np.asarray(d)
    return {"diff": auroc(y, a) - auroc(y, b), "ci95": [float(np.quantile(d, .025)), float(np.quantile(d, .975))],
            "share_draws_above_0": float((d > 0).mean()), "n_draws": int(len(d))}


def compare(baseline_csv, candidate_csv):
    with open(baseline_csv, newline="", encoding="utf-8") as fa, open(candidate_csv, newline="", encoding="utf-8") as fb:
        A = {r["compound_name"]: r for r in csv.DictReader(fa)}
        B = {r["compound_name"]: r for r in csv.DictReader(fb)}
    if sorted(A) != sorted(B):
        raise SystemExit("refusing to compare: the candidate's compounds differ from the approved cohort")
    names = sorted(A)
    y = [int(float(A[c]["label"])) for c in names]
    if y != [int(float(B[c]["label"])) for c in names]:
        raise SystemExit("refusing to compare: the candidate's labels differ from the approved labels")
    a5 = [float(A[c]["VPS_equal_5d"]) for c in names]
    b5 = [float(B[c]["VPS_equal_5d"]) for c in names]
    a4 = [float(A[c]["VPS_equal"]) for c in names]
    rank = lambda s: {names[i]: r + 1 for r, i in enumerate(sorted(range(len(s)), key=lambda i: (-s[i], names[i])))}
    ra, rb = rank(a5), rank(b5)
    dims = ("r_proximity", "r_clinical", "r_literature", "r_safety", "r_molecular")
    changed = {d: [c for c in names if abs(float(A[c][d]) - float(B[c][d])) > 1e-12] for d in dims}
    out = {"cohort": {"n": len(names), "positives": sum(y), "negatives": len(y) - sum(y), "compounds_identical": True, "labels_identical": True},
           "dimensions_changed": {d: len(v) for d, v in changed.items()},
           "metrics": {}, "paired": {}, "ranks": []}
    for key, s in (("approved_5d", a5), ("candidate_5d", b5), ("approved_4d", a4)):
        c_auc, sk = ci(y, s, auroc); c_ap, _ = ci(y, s, auprc)
        out["metrics"][key] = {"auroc": auroc(y, s), "auroc_ci95": c_auc, "auprc": auprc(y, s), "auprc_ci95": c_ap, "skipped_draws": sk}
    out["paired"] = {"approved_minus_candidate": paired(y, a5, b5), "candidate_minus_4d": paired(y, b5, a4),
                     "approved_minus_4d": paired(y, a5, a4)}
    out["top10_overlap"] = len({c for c, r in ra.items() if r <= 10} & {c for c, r in rb.items() if r <= 10})
    out["ranks"] = [{"compound": c, "label": y[names.index(c)], "rank_approved": ra[c], "rank_candidate": rb[c],
                     "molecular_approved": float(A[c]["molecular_plausibility_score"]), "molecular_candidate": float(B[c]["molecular_plausibility_score"]),
                     "changed_dimensions": [d[2:] for d in dims if c in changed[d]]} for c in sorted(names, key=lambda c: ra[c])]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--baseline", default="data/vps_scores_v2.csv")
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--rule", required=True, help="one sentence: what the candidate changes")
    ap.add_argument("--decision", default="", help="the open decision id, e.g. TD-042")
    a = ap.parse_args(argv)
    res = compare(a.baseline, a.candidate)
    res.update({"name": a.name, "rule": a.rule, "decision": a.decision, "status": "NOT APPROVED",
                "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "procedure": {"auroc": "Mann-Whitney, ties 1/2", "auprc": "step-wise average precision, ties grouped",
                              "ci": f"ordinary percentile bootstrap, numpy default_rng({SEED}), {N_BOOT} draws, single-class draws skipped",
                              "paired": "same indices per draw; 2.5/97.5% quantiles of draw-wise differences; share above 0 is not a p-value"},
                "inputs": {a.baseline: _md5(a.baseline), a.candidate: _md5(a.candidate)}})
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    os.replace(tmp, a.out)
    m = res["metrics"]
    print(f"{a.name}: approved 5D {m['approved_5d']['auroc']:.4f}, candidate 5D {m['candidate_5d']['auroc']:.4f}, 4D {m['approved_4d']['auroc']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
