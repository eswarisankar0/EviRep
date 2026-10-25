"""Monte Carlo sensitivity of the proximity dimension (TD-011, B-003; final audit 2026-10-22). Read-only.
For each stage-02 output (different RANDOM_SEED / N_RANDOM, current code), replace r_proximity in the approved 90-compound
result with stage 06's rule (pool median for a missing z, inverted legacy percentile rank) and recompute AUROC.
    proximity_seed_sensitivity.py APPROVED_ROOT LABEL=path/to/network_proximity.csv ...
"""
import json
import os
import sys

import pandas as pd
from sklearn.metrics import roc_auc_score

v = pd.read_csv(os.path.join(sys.argv[1], "data/vps_scores_v2.csv"))
y = v.label.values
R5 = ["r_proximity", "r_clinical", "r_literature", "r_safety", "r_molecular"]
R4 = R5[:4]
out = {"approved": {"auroc_5d": round(roc_auc_score(y, v[R5].mean(axis=1)), 4),
                    "auroc_4d": round(roc_auc_score(y, v[R4].mean(axis=1)), 4), "proximity_alone": round(roc_auc_score(y, v.r_proximity), 4)}}
for arg in sys.argv[2:]:
    label, path = arg.split("=", 1)
    p = pd.read_csv(path).set_index("compound_name")
    z = v.compound_name.map(p.proximity_z)
    z = z.fillna(z.median())
    w = v.copy()
    w["r_proximity"] = 1 - z.rank(pct=True, method="average")
    out[label] = {"auroc_5d": round(roc_auc_score(y, w[R5].mean(axis=1)), 4), "auroc_4d": round(roc_auc_score(y, w[R4].mean(axis=1)), 4),
                  "proximity_alone": round(roc_auc_score(y, w.r_proximity), 4),
                  "spearman_z_vs_approved": round(float(z.corr(v.proximity_z, method="spearman")), 4)}
print(json.dumps(out, indent=1))
