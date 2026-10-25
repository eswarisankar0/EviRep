"""
One table comparing candidate VPS architectures on the same population, paired against the approved baseline
(2026-10-20 end-to-end audit, docs/autonomous_runs/EIGHT_AGENT_VPS_CONTRIBUTION_AUDIT.md). Read-only; outputs to
--out (default data/_runs/vps_architecture_20261020/). Nothing is published and no weight is fitted: every
architecture is the pre-specified equal-weight mean of its percentile-ranked dimensions.

  A   approved 5D (published dimensions)
  B   A with cutoff-bounded literature (04p count) and safety at the cutoff (05h, current label where none found)
  C   4D without molecular (published dimensions) and C-bounded (B without molecular)
  D   TD-042 candidate 5D; D-dated: TD-042 rule with every molecular input dated (OT 20.11, UniProt 2020-11,
      ChEMBL 2020-06; data/_runs/molecular_historical_20261020/); A-dated: approved rule, same dated inputs
  B+D-dated  every dimension except clinical phase fields bounded at the cutoff
Agent-derived dimensions (architecture E) are not scored here: none meets the data contract (see the audit).

    ./venv/bin/python scripts/vps_architecture_comparison.py [--boot 2000]
"""
import argparse
import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = "data/_runs/molecular_historical_20261020/molecular_historical.json"


def _load(name, fn):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


vve = _load("vve", "vps_validation_experiments.py")
lit = _load("vlcs", "vps_literature_cutoff_sensitivity.py")


def architectures(root):
    base = vve.build(root)
    cor = vve.build(root, molecular="td042_own_target")
    meas = lit.bounded_measures(root).reindex(base.index)
    v = meas["lit_bounded_count"]
    r_lit = vve.pct(v.fillna(v.median()), False, "legacy")
    mixed, _, _ = lit.bounded_safety(root, base.index)
    r_saf = vve.pct(mixed, True, "legacy")
    A = base[vve.DIMS5]
    B = A.assign(r_literature=r_lit, r_safety=r_saf)
    out = {"A approved 5D": A, "B bounded literature + safety": B,
           "C 4D (no molecular)": base[vve.DIMS4], "C-bounded 4D": B[vve.DIMS4],
           "D TD-042 5D (candidate)": cor[vve.DIMS5]}
    hp = os.path.join(root, HIST)
    if os.path.exists(hp):
        with open(hp, encoding="utf-8") as fh:
            per = pd.DataFrame(json.load(fh)["per_drug"]).set_index("compound_name").reindex(base.index)
        r_a = vve.pct(per["molecular_2020_chembl2006"].astype(float), False, "legacy")
        r_d = vve.pct(per["molecular_2020_chembl2006_td042"].astype(float), False, "legacy")
        out["A-dated: approved rule, dated molecular inputs"] = A.assign(r_molecular=r_a)
        out["D-dated: TD-042 rule, dated molecular inputs"] = A.assign(r_molecular=r_d)
        out["B+D-dated: all bounded except clinical phase fields"] = B.assign(r_molecular=r_d)
    return out, base["label"].to_numpy()


def run(root=".", n_boot=2000, seed=vve.SEED):
    arch, y = architectures(root)
    S = {k: F.mean(axis=1).to_numpy() for k, F in arch.items()}
    boot = vve.bootstrap(S, y, n_boot, np.random.default_rng(seed))
    ref = "A approved 5D"
    rows = []
    for k, s in S.items():
        m = vve.metrics(s, y)
        sp, top = vve._rank_agreement(s, S[ref])
        rows.append({"architecture": k, "n_dimensions": arch[k].shape[1], "n": int(len(y)), "positives": int(y.sum()),
                     "negatives": int(len(y) - y.sum()), **{x: round(v, 4) for x, v in m.items()},
                     "auroc_ci95": vve.ci(boot[k]["auroc"]), "auprc_ci95": vve.ci(boot[k]["auprc"]),
                     "p_at_10_ci95": vve.ci(boot[k]["p_at_10"]),
                     "delta_auroc_vs_A": None if k == ref else round(m["auroc"] - vve.metrics(S[ref], y)["auroc"], 4),
                     "delta_auroc_vs_A_ci95": None if k == ref else vve.ci(boot[k]["auroc"] - boot[ref]["auroc"]),
                     "spearman_vs_A": round(sp, 3), "top10_overlap_vs_A": top})
    return {"generated_by": "scripts/vps_architecture_comparison.py", "seed": seed, "n_boot": n_boot,
            "random_expectation": {"auroc": 0.5, "auprc": round(float(y.mean()), 4), "p_at_10": round(float(y.mean()), 4)},
            "calibration": "not reported: the VPS is a mean of percentile ranks, not a probability",
            "results": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="data/_runs/vps_architecture_20261020")
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args(argv)
    res = run(a.root, a.boot)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "architecture_comparison.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    pd.DataFrame(res["results"]).to_csv(os.path.join(a.out, "architecture_comparison.csv"), index=False)
    for r in res["results"]:
        d = "" if r["delta_auroc_vs_A"] is None else f" d={r['delta_auroc_vs_A']:+.3f} {r['delta_auroc_vs_A_ci95']}"
        print(f"{r['architecture']:<52} AUROC {r['auroc']:.3f} {r['auroc_ci95']} AUPRC {r['auprc']:.3f} "
              f"P@10 {r['p_at_10']:.2f} top10 {r['top10_overlap_vs_A']:.1f}{d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
