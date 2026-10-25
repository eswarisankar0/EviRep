"""Sensitivity of the approved result to undocumented constants (final audit 2026-10-22). Read-only; prints JSON.
Each analysis changes ONE input of the approved 90-compound result and recomputes that dimension's legacy percentile
rank exactly as stage 06 does; every other rank is the approved one. Equal weights. Nothing is selected.
  C1 boxed-warning multiplier k in safety risk = serious_term_count + k * boxed_warning, k in {0,1,3,5,10}
  C2 phase per trial: phases[0] (stage 03) vs max of the listed phases (registry cache)
  C3 safety term negation: share of serious-term hits preceded by a negation word within 3 tokens (cached labels)
"""
import glob
import json
import os
import re
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
PH = {"NA": 0, "EARLY_PHASE1": 1, "PHASE1": 2, "PHASE2": 3, "PHASE3": 4, "PHASE4": 5}
v = pd.read_csv(os.path.join(ROOT, "data/vps_scores_v2.csv"))
y = v.label.values
R = ["r_proximity", "r_clinical", "r_literature", "r_safety", "r_molecular"]
auc = lambda r: round(float(roc_auc_score(y, r[R].mean(axis=1))), 4)
out = {"approved_auroc": auc(v)}

# C1
res = {}
for k in (0, 1, 3, 5, 10):
    w = v.copy()
    risk = (w.serious_term_count + k * w.boxed_warning.astype(float)).where(~w.safety_label_missing.astype(bool))
    w["r_safety"] = (1 - risk.rank(pct=True, method="average")).fillna(0.5)
    res[k] = {"auroc_5d": auc(w), "r_safety_spearman_vs_k5": round(float(w.r_safety.corr(v.r_safety, method="spearman")), 4)}
out["C1_boxed_multiplier"] = res
out["C1_check_k5_reproduces_approved"] = res[5]["auroc_5d"] == out["approved_auroc"]

# C2
c = json.load(open(os.path.join(ROOT, "data/cache/ctgov_precutoff_trials.json")))
phases = {s["protocolSection"]["identificationModule"]["nctId"]: s["protocolSection"].get("designModule", {}).get("phases") or []
          for s in c["studies"]}
clin = pd.read_csv(os.path.join(ROOT, "data/clinical_maturity_precutoff_clean.csv"), keep_default_na=False)
clin = clin[clin.compound_name.isin(v.compound_name)]
clin["rank_first"] = clin.phase.map(lambda p: PH.get(p, 0))
clin["rank_max"] = [max([PH.get(p, 0) for p in phases.get(n, [])] or [PH.get(ph, 0)]) for n, ph in zip(clin.nct_id, clin.phase)]
multi = clin[[len(phases.get(n, [])) > 1 for n in clin.nct_id]]
mx = clin.groupby("compound_name").rank_max.max()
w = v.copy()
w["max_phase_rank"] = w.compound_name.map(mx)
w["r_clinical"] = w.max_phase_rank.rank(pct=True, method="average")
out["C2_phase"] = {"links_with_multiple_phases": int(len(multi)),
                   "links_where_max_differs_from_first": int((multi.rank_max != multi.rank_first).sum()),
                   "compounds_whose_max_phase_changes": int((w.max_phase_rank != v.max_phase_rank).sum()),
                   "trials_not_in_cache": int(sum(n not in phases for n in clin.nct_id)),
                   "auroc_5d_with_max_phase": auc(w)}

# C3
TERMS = ["death", "fatal", "life-threatening", "suicide", "seizure", "hepatotoxicity", "cardiac arrest", "stroke"]
NEG = re.compile(r"\b(no|not|without|none|never|nor|absence)\b")
hits = neg = 0
for f in glob.glob(os.path.join(ROOT, "data/cache/openfda_labels/*.json")):
    lab = json.load(open(f))
    lab = lab.get("results", [lab])[0] if isinstance(lab, dict) else lab
    text = " ".join(" ".join(lab.get(k) or []) if isinstance(lab.get(k), list) else str(lab.get(k) or "")
                    for k in ("boxed_warning", "warnings", "warnings_and_cautions")).lower()
    for t in TERMS:
        for m in re.finditer(re.escape(t), text):
            hits += 1
            if NEG.search(" ".join(text[:m.start()].split()[-3:])):
                neg += 1
out["C3_negation"] = {"serious_term_hits": hits, "preceded_by_negation_within_3_tokens": neg,
                      "share": round(neg / hits, 4) if hits else None, "labels_scanned": len(glob.glob(os.path.join(ROOT, "data/cache/openfda_labels/*.json")))}
print(json.dumps(out, indent=1))
