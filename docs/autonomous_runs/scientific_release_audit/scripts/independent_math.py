"""Independent recomputation of ranks, VPS scores and evaluation statistics (audit tool; offline, read-only).

Written from the specification, not from the production code: it does not import scripts/06_vps_fusion.py,
scripts/vps_verify.py or scripts/vps_evaluation_report.py. Ranks use a hand-written average-tie percentile rank;
AUROC is the Mann-Whitney U statistic computed by explicit pair counting; average precision is the step-wise
definition with tied scores grouped. sklearn is used only as a second, external reference.
Writes per-compound and summary results to OUT.
"""
import csv, json, math, os, sys
import numpy as np
from sklearn.metrics import roc_auc_score, average_precision_score

R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
OUT = sys.argv[1]
rows = list(csv.DictReader(open(os.path.join(R, "data/vps_scores_v2.csv"))))
rep = json.load(open(os.path.join(R, "data/vps_evaluation_report.json")))
f = lambda v: float(v) if v not in ("", None) and v.lower() != "nan" else math.nan


def pct_rank_avg(values):
    """pandas rank(pct=True, method='average') semantics: average 1-based rank among non-missing values / count."""
    idx = [i for i, v in enumerate(values) if not math.isnan(v)]
    srt = sorted(idx, key=lambda i: values[i])
    ranks, k = {}, 0
    while k < len(srt):
        j = k
        while j + 1 < len(srt) and values[srt[j + 1]] == values[srt[k]]:
            j += 1
        avg = (k + 1 + j + 1) / 2
        for t in range(k, j + 1):
            ranks[srt[t]] = avg / len(srt)
        k = j + 1
    return [ranks.get(i, math.nan) for i in range(len(values))]


n = len(rows)
names = [r["compound_name"] for r in rows]
assert len(set(names)) == n, "duplicate compounds"
raw = {
    "proximity": [f(r["proximity_z"]) for r in rows],
    "clinical": [f(r["max_phase_rank"]) for r in rows],
    "literature": [f(r["effective_independent_count"]) for r in rows],
    "safety": [math.nan if r["safety_label_missing"] == "True" else f(r["serious_term_count"]) + 5 * (r["boxed_warning"] == "True") for r in rows],
    "molecular": [math.nan if r["molecular_evidence_missing"] == "True" else f(r["molecular_plausibility_score"]) for r in rows],
}
invert = {"proximity": True, "clinical": False, "literature": False, "safety": True, "molecular": False}
# proximity: missing raw values are median-imputed before ranking (spec; the saved file already holds the imputed value)
mine = {}
for d, vals in raw.items():
    pr = pct_rank_avg(vals)
    mine[d] = [0.5 if math.isnan(p) else (1 - p if invert[d] else p) for p in pr]
vps = [sum(mine[d][i] for d in raw) / 5 for i in range(n)]
vps4 = [sum(mine[d][i] for d in ("proximity", "clinical", "literature", "safety")) / 4 for i in range(n)]
y = [int(float(r["label"])) for r in rows]

per = []
for i, r in enumerate(rows):
    rec = {"compound": names[i], "label": y[i]}
    for d in raw:
        stored = f(r["r_" + d]); rec[f"r_{d}_stored"] = stored; rec[f"r_{d}_recomputed"] = mine[d][i]
        rec[f"r_{d}_absdiff"] = abs(stored - mine[d][i])
    rec.update({"vps5_stored": f(r["VPS_equal_5d"]), "vps5_recomputed": vps[i], "vps5_absdiff": abs(f(r["VPS_equal_5d"]) - vps[i]),
                "vps4_stored": f(r["VPS_equal"]), "vps4_recomputed": vps4[i], "vps4_absdiff": abs(f(r["VPS_equal"]) - vps4[i]),
                "n_neutral": sum(1 for d in ("safety", "molecular") if math.isnan(raw[d][i])),
                "all_ranks_finite_in_0_1": all(0 <= mine[d][i] <= 1 for d in raw)})
    per.append(rec)
with open(os.path.join(OUT, "independent_scores.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(per[0])); w.writeheader(); w.writerows(per)


def auroc_mw(y, s):
    pos = [v for v, t in zip(s, y) if t == 1]; neg = [v for v, t in zip(s, y) if t == 0]
    if not pos or not neg:
        return None                                   # undefined, never 0.5
    return sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))


def ap_stepwise(y, s):
    """Average precision = sum over distinct thresholds of (R_k - R_{k-1}) * P_k, tied scores grouped."""
    npos = sum(y)
    if npos == 0:
        return None
    order = sorted(range(len(s)), key=lambda i: -s[i])
    tp = fp = 0; ap = 0.0; prev_r = 0.0; k = 0
    while k < len(order):
        j = k
        while j + 1 < len(order) and s[order[j + 1]] == s[order[k]]:
            j += 1
        for t in range(k, j + 1):
            tp += y[order[t]]; fp += 1 - y[order[t]]
        rcl = tp / npos; prc = tp / (tp + fp)
        ap += (rcl - prev_r) * prc; prev_r = rcl; k = j + 1
    return ap


def boot_unstrat(y, s, metric, n=2000, seed=42):
    rng = np.random.default_rng(seed); ya, sa = np.asarray(y), np.asarray(s); vals, sk = [], 0
    for _ in range(n):
        i = rng.integers(0, len(ya), len(ya))
        if ya[i].min() == ya[i].max():
            sk += 1; continue
        vals.append(metric(list(ya[i]), list(sa[i])))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))], sk, len(vals)


def paired(y, a, b, n=2000, seed=42):
    rng = np.random.default_rng(seed); ya, aa, ba = map(np.asarray, (y, a, b)); d, sk = [], 0
    for _ in range(n):
        i = rng.integers(0, len(ya), len(ya))
        if ya[i].min() == ya[i].max():
            sk += 1; continue
        d.append(auroc_mw(list(ya[i]), list(aa[i])) - auroc_mw(list(ya[i]), list(ba[i])))
    d = np.asarray(d)
    return {"diff": auroc_mw(y, a) - auroc_mw(y, b), "ci95": [float(np.quantile(d, .025)), float(np.quantile(d, .975))],
            "share_draws_above_0": float((d > 0).mean()), "n_used": len(d), "skipped": sk}


s5 = [f(r["VPS_equal_5d"]) for r in rows]; s4 = [f(r["VPS_equal"]) for r in rows]
prim = {p["column"]: p for p in rep["primary"]}
summary = {
    "n": n, "positives": sum(y), "negatives": n - sum(y),
    "max_abs_diff_rank": max(per[i][f"r_{d}_absdiff"] for i in range(n) for d in raw),
    "max_abs_diff_vps5": max(p["vps5_absdiff"] for p in per), "max_abs_diff_vps4": max(p["vps4_absdiff"] for p in per),
    "all_ranks_finite_in_0_1": all(p["all_ranks_finite_in_0_1"] for p in per),
    "n_distinct_vps5": len(set(s5)), "neutral_safety": sum(math.isnan(v) for v in raw["safety"]), "neutral_molecular": sum(math.isnan(v) for v in raw["molecular"]),
    "rank_ranges": {d: [min(mine[d]), max(mine[d])] for d in raw},
    "auroc5_mw": auroc_mw(y, s5), "auroc5_sklearn": roc_auc_score(y, s5), "auroc5_report": prim["VPS_equal_5d"]["auroc"],
    "auroc4_mw": auroc_mw(y, s4), "auroc4_report": prim["VPS_equal"]["auroc"],
    "ap5_stepwise": ap_stepwise(y, s5), "ap5_sklearn": average_precision_score(y, s5), "ap5_report": prim["VPS_equal_5d"]["auprc"],
    "prevalence": sum(y) / n,
}
ci5, sk5, used5 = boot_unstrat(y, s5, auroc_mw)
cia, ska, useda = boot_unstrat(y, s5, ap_stepwise)
summary.update({"auroc5_ci_recomputed": ci5, "auroc5_ci_report": prim["VPS_equal_5d"]["auroc_ci95"], "auroc5_boot_used": used5, "auroc5_boot_skipped": sk5,
                "ap5_ci_recomputed": cia, "ap5_ci_report": prim["VPS_equal_5d"]["auprc_ci95"],
                "paired_recomputed": paired(y, s5, s4), "paired_report": rep["paired_5d_vs_4d"]})
# legacy vs midrank: does the 1/n offset of inverted dimensions change the ordering? (midrank = (rank - 0.5)/n, symmetric)
def midrank(vals, inv):
    pr = pct_rank_avg(vals); cnt = sum(not math.isnan(v) for v in vals)
    return [0.5 if math.isnan(p) else ((1 - (p * cnt - 0.5) / cnt) if inv else (p * cnt - 0.5) / cnt) for p in pr]
mid = {d: midrank(raw[d], invert[d]) for d in raw}
vmid = [sum(mid[d][i] for d in raw) / 5 for i in range(n)]
summary["auroc5_midrank_convention"] = auroc_mw(y, vmid)
summary["rank_order_identical_legacy_vs_midrank"] = sorted(range(n), key=lambda i: -vps[i]) == sorted(range(n), key=lambda i: -vmid[i])
json.dump(summary, open(os.path.join(OUT, "independent_math_summary.json"), "w"), indent=1)
print(json.dumps(summary, indent=1))
