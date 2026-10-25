"""Independent comparison of the approved result set and the TD-042 candidate (td042_v1). Offline, read-only.

No production code is imported. AUROC = Mann-Whitney pair counting (ties 1/2); AP = step-wise, tied scores grouped;
CIs = the report's procedure (ordinary percentile bootstrap, default_rng(42), 2,000 draws, single-class draws
skipped); paired differences use the same indices for both scores. Writes OUT/td042_comparison.json and
OUT/td042_rank_changes.csv.
"""
import csv, json, math, os, sys
import numpy as np

R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
OUT = sys.argv[1]
A = {r["compound_name"]: r for r in csv.DictReader(open(os.path.join(R, "data/vps_scores_v2.csv")))}
B = {r["compound_name"]: r for r in csv.DictReader(open(os.path.join(R, "data/_candidates/td042_v1/root/data/vps_scores_v2.csv")))}
f = float
names = sorted(A)
assert sorted(B) == names, "cohorts differ"
y = [int(f(A[c]["label"])) for c in names]
assert y == [int(f(B[c]["label"])) for c in names], "labels differ"


def auc(y, s):
    pos = [v for v, t in zip(s, y) if t]; neg = [v for v, t in zip(s, y) if not t]
    return sum((p > q) + .5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))


def ap(y, s):
    o = sorted(range(len(s)), key=lambda i: -s[i]); npos = sum(y); tp = fp = 0; prev = 0.0; out = 0.0; k = 0
    while k < len(o):
        j = k
        while j + 1 < len(o) and s[o[j + 1]] == s[o[k]]:
            j += 1
        for t in range(k, j + 1):
            tp += y[o[t]]; fp += 1 - y[o[t]]
        out += (tp / npos - prev) * tp / (tp + fp); prev = tp / npos; k = j + 1
    return out


def boot(y, s, m):
    g = np.random.default_rng(42); ya, sa = np.array(y), np.array(s); v = []
    for _ in range(2000):
        i = g.integers(0, len(y), len(y))
        if ya[i].min() != ya[i].max():
            v.append(m(list(ya[i]), list(sa[i])))
    return [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)]


def paired(y, a, b):
    g = np.random.default_rng(42); ya, aa, ba = map(np.array, (y, a, b)); d = []
    for _ in range(2000):
        i = g.integers(0, len(y), len(y))
        if ya[i].min() != ya[i].max():
            d.append(auc(list(ya[i]), list(aa[i])) - auc(list(ya[i]), list(ba[i])))
    return {"diff": round(auc(y, a) - auc(y, b), 4), "ci95": [round(float(np.quantile(d, .025)), 4), round(float(np.quantile(d, .975)), 4)],
            "share_draws_above_0": round(float((np.array(d) > 0).mean()), 3)}


def spearman(a, b):
    ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


dims = ["r_proximity", "r_clinical", "r_literature", "r_safety"]
unchanged = {d: max(abs(f(A[c][d]) - f(B[c][d])) for c in names) for d in dims}
a5 = [f(A[c]["VPS_equal_5d"]) for c in names]; b5 = [f(B[c]["VPS_equal_5d"]) for c in names]
s4 = [f(A[c]["VPS_equal"]) for c in names]
am = [f(A[c]["molecular_plausibility_score"]) for c in names]; bm = [f(B[c]["molecular_plausibility_score"]) for c in names]
changed_mol = [c for c in names if abs(f(A[c]["molecular_plausibility_score"]) - f(B[c]["molecular_plausibility_score"])) > 1e-12]
rank = lambda s: {names[i]: r + 1 for r, i in enumerate(sorted(range(len(s)), key=lambda i: -s[i]))}
ra, rb = rank(a5), rank(b5)
top = lambda r, k: {c for c, v in r.items() if v <= k}
out = {
    "cohort": {"n": len(names), "positives": sum(y), "labels_identical": True, "compounds_identical": True},
    "other_dimensions_max_abs_diff": unchanged,
    "molecular_score_changed_compounds": len(changed_mol), "molecular_changed_positives": sum(y[names.index(c)] for c in changed_mol),
    "spearman_molecular_score": round(spearman(am, bm), 4), "spearman_vps5": round(spearman(a5, b5), 4),
    "approved": {"auroc_5d": round(auc(y, a5), 4), "auroc_5d_ci95": boot(y, a5, auc), "auprc_5d": round(ap(y, a5), 4), "auprc_ci95": boot(y, a5, ap)},
    "td042_v1": {"auroc_5d": round(auc(y, b5), 4), "auroc_5d_ci95": boot(y, b5, auc), "auprc_5d": round(ap(y, b5), 4), "auprc_ci95": boot(y, b5, ap)},
    "auroc_4d": round(auc(y, s4), 4),
    "paired_approved_minus_td042": paired(y, a5, b5), "paired_td042_minus_4d": paired(y, b5, s4),
    "top10_overlap": len(top(ra, 10) & top(rb, 10)), "top20_overlap": len(top(ra, 20) & top(rb, 20)),
    "max_abs_rank_change": max(abs(ra[c] - rb[c]) for c in names),
}
with open(os.path.join(OUT, "td042_rank_changes.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["compound", "label", "molecular_approved", "molecular_td042", "vps5_approved", "vps5_td042", "rank_approved", "rank_td042", "rank_change"])
    for c in sorted(names, key=lambda c: ra[c]):
        w.writerow([c, A[c]["label"], A[c]["molecular_plausibility_score"], B[c]["molecular_plausibility_score"], A[c]["VPS_equal_5d"], B[c]["VPS_equal_5d"], ra[c], rb[c], rb[c] - ra[c]])
json.dump(out, open(os.path.join(OUT, "td042_comparison.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
