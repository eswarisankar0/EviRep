"""Exploratory label-sensitivity analysis (NOT an approved result). Same approved scores (data/vps_scores_v2.csv),
same 90 compounds; only the disputed/unresolved labels are varied. AUROC by explicit Mann-Whitney pair counting,
95% CI by the report's own procedure (ordinary percentile bootstrap, 2,000 draws, seed 42)."""
import csv, json, os, sys
import numpy as np
R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
OUT = sys.argv[1]
rows = list(csv.DictReader(open(os.path.join(R, "data/vps_scores_v2.csv"))))
base = {r["compound_name"]: int(float(r["label"])) for r in rows}
s5 = {r["compound_name"]: float(r["VPS_equal_5d"]) for r in rows}
s4 = {r["compound_name"]: float(r["VPS_equal"]) for r in rows}


def auc(y, s):
    pos = [v for v, t in zip(s, y) if t == 1]; neg = [v for v, t in zip(s, y) if t == 0]
    return sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg)) if pos and neg else None


def boot(y, s, n=2000, seed=42):
    rng = np.random.default_rng(seed); y, s = np.asarray(y), np.asarray(s); v = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() != y[i].max(): v.append(auc(list(y[i]), list(s[i])))
    return [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)]


SCEN = [("approved (reference)", {}, set()),
        ("Lithium = 1 (dietary-supplement-typed trials count)", {"Lithium": 1}, set()),
        ("Galantamine = 0 (D-011 unresolved)", {"Galantamine": 0}, set()),
        ("Galantamine excluded", {}, {"Galantamine"}),
        ("Lidocaine = 0 (stellate block as procedure)", {"Lidocaine": 0}, set()),
        ("Rifaximin = 0 (regimen component)", {"Rifaximin": 0}, set()),
        ("all disputed resolved against (Lithium 0; Galantamine, Lidocaine, Rifaximin 0)", {"Galantamine": 0, "Lidocaine": 0, "Rifaximin": 0}, set()),
        ("all disputed resolved for (Lithium 1; others 1)", {"Lithium": 1}, set()),
        ("all disputed excluded (Lithium, Galantamine, Lidocaine, Rifaximin)", {}, {"Lithium", "Galantamine", "Lidocaine", "Rifaximin"})]
out = []
for name, change, drop in SCEN:
    lab = {**base, **change}; names = [c for c in lab if c not in drop]
    y = [lab[c] for c in names]
    a5, a4 = auc(y, [s5[c] for c in names]), auc(y, [s4[c] for c in names])
    out.append({"scenario": name, "n": len(names), "positives": sum(y), "auroc_5d": round(a5, 4), "auroc_5d_ci95": boot(y, [s5[c] for c in names]),
                "auroc_4d": round(a4, 4), "diff_5d_4d": round(a5 - a4, 4)})
    print(out[-1])
json.dump({"note": "exploratory; approved labels unchanged", "results": out}, open(os.path.join(OUT, "label_sensitivity.json"), "w"), indent=1)
