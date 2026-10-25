"""
Molecular-dimension temporal sensitivity: Open Targets 20.11 (released November 2020, before the cutoff) versus the
26.09 snapshot used by stage 08. Read-only; outputs to --out (default data/_runs/molecular_snapshot_20261019/).

Only the DIRECT drug-target -> Parkinson's component can be recomputed from the 20.11 association file (pathway
membership of every module gene is not persisted, so the pathway component is not rebuilt). To isolate the snapshot
date, both sides use the same direct-only formula:

  direct(drug) = max over the drug's ChEMBL targets of the max allowed-datatype score for Parkinson's disease
                 (allowed = stage 08's allowed datatypes that exist in 20.11; clinical/literature/known_drug excluded)

  current  : the persisted stage-08 `datatype_scores_used` per target (MONDO_0005180, 26.09)
  at 20.11 : the 20.11 association row for the same Ensembl ID and EFO_0002508 (the 2020 PD identifier)

No target -> unmeasured (neutral 0.5 after ranking, D-004), as in the approved dimension. Drug->target mapping is
today's ChEMBL mechanism list for both sides (not dated; a limitation). Input: the PD lines of 20.11
association_data.json.gz under data/cache/opentargets_20.11/.

    ./venv/bin/python scripts/vps_molecular_snapshot_sensitivity.py [--boot 2000]
"""
import argparse
import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("vve", os.path.join(HERE, "vps_validation_experiments.py"))
vve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vve)

OT2011 = "data/cache/opentargets_20.11/association_lines_EFO_0002508.jsonl"
EVIDENCE = "data/molecular_pathway_evidence.jsonl"
PD_2011 = "EFO_0002508"
ALLOWED = ("genetic_association", "genetic_literature", "animal_model", "affected_pathway", "somatic_mutation",
           "rna_expression")                       # stage 08 MolecularAgentConfig.allowed_datatypes


def load_2011(root):
    """{ensembl_id: allowed-datatype max score} for Parkinson's disease rows; indirect preferred (as the 26.09
    associatedDiseases rows stage 08 reads), direct used when it is the only row."""
    best = {}
    with open(os.path.join(root, OT2011), encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if (r.get("disease") or {}).get("id") != PD_2011:
                continue
            dt = (r.get("association_score") or {}).get("datatypes") or {}
            score = max([float(dt[k]) for k in ALLOWED if k in dt] or [0.0])
            tid = r["target"]["id"]
            direct = bool(r.get("is_direct"))
            prev = best.get(tid)
            if prev is None or (prev[1] and not direct):         # replace a direct row by the indirect one
                best[tid] = (score, direct)
    return {k: v[0] for k, v in best.items()}


def direct_components(root, ot2011):
    rows = {}
    with open(os.path.join(root, EVIDENCE), encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            tids = [t["ensembl_id"] for t in r.get("targets") or [] if t.get("ensembl_id")]
            if not tids:
                rows[r["drug"]] = (np.nan, np.nan, np.nan)
                continue
            cur = {dl.get("target_id") or dl.get("ensembl_id"): max([float(v) for k, v in
                                                                      (dl.get("datatype_scores_used") or {}).items()
                                                                      if k in ALLOWED] or [0.0])
                   for dl in r.get("disease_links") or []}
            cur_direct = max([cur.get(t, 0.0) for t in tids] or [0.0])
            then = max([ot2011.get(t, 0.0) for t in tids] or [0.0])
            published = ((r.get("scoring") or {}).get("components") or {}).get("direct_target_disease")
            rows[r["drug"]] = (cur_direct, then, published)
    return pd.DataFrame.from_dict(rows, orient="index", columns=["direct_current", "direct_2011", "direct_published"])


def run(root=".", n_boot=2000, seed=vve.SEED):
    rng = np.random.default_rng(seed)
    base = vve.build(root)
    ot = load_2011(root)
    d = direct_components(root, ot).reindex(base.index)
    y = base["label"].to_numpy()
    rc = vve.pct(d["direct_current"], False, "legacy")
    rt = vve.pct(d["direct_2011"], False, "legacy")
    S = {"5D published (approved)": base[vve.DIMS5].mean(axis=1),
         "5D, molecular = direct component, 26.09": base[vve.DIMS5].assign(r_molecular=rc).mean(axis=1),
         "5D, molecular = direct component, 20.11 (pre-cutoff)": base[vve.DIMS5].assign(r_molecular=rt).mean(axis=1),
         "direct component alone, 26.09": rc, "direct component alone, 20.11": rt}
    S = {k: v.to_numpy() for k, v in S.items()}
    boot = vve.bootstrap(S, y, n_boot, rng)
    pairs = {"5D, molecular = direct component, 20.11 (pre-cutoff)": "5D, molecular = direct component, 26.09",
             "direct component alone, 20.11": "direct component alone, 26.09",
             "5D, molecular = direct component, 26.09": "5D published (approved)"}
    rows = []
    for k, s in S.items():
        m = vve.metrics(s, y)
        ref = pairs.get(k)
        rows.append({"model": k, **{x: round(v, 4) for x, v in m.items()}, "auroc_ci": vve.ci(boot[k]["auroc"]),
                     "reference": ref,
                     "delta_auroc": None if not ref else round(m["auroc"] - vve.metrics(S[ref], y)["auroc"], 4),
                     "delta_auroc_ci": None if not ref else vve.ci(boot[k]["auroc"] - boot[ref]["auroc"])})
    measured = d["direct_current"].notna()
    agree = (d.loc[measured, "direct_current"] - d.loc[measured, "direct_published"]).abs()
    return {"n": int(len(y)), "positives": int(y.sum()), "n_boot": n_boot, "seed": seed,
            "n_targets_in_2011_pd_rows": len(ot), "n_drugs_with_targets": int(measured.sum()),
            "n_drugs_direct_changed": int((d.loc[measured, "direct_current"] - d.loc[measured, "direct_2011"]).abs()
                                          .gt(1e-9).sum()),
            "max_abs_recompute_vs_published_direct": round(float(agree.max()), 6) if len(agree) else None,
            "spearman_direct_2011_vs_current": round(float(spearmanr(d.loc[measured, "direct_current"],
                                                                     d.loc[measured, "direct_2011"])[0]), 3),
            "per_drug": d.reset_index(names="compound_name").round(4).to_dict("records"), "results": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="data/_runs/molecular_snapshot_20261019")
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args(argv)
    if not os.path.exists(os.path.join(a.root, OT2011)):
        print(f"{OT2011} missing: download the 20.11 association file first (see docstring)", file=sys.stderr)
        return 1
    res = run(a.root, a.boot)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "molecular_snapshot_sensitivity.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    print({k: v for k, v in res.items() if k not in ("per_drug", "results")})
    for r in res["results"]:
        d = "" if r["delta_auroc"] is None else f"  d={r['delta_auroc']:+.3f} {r['delta_auroc_ci']} vs {r['reference']}"
        print(f"{r['model']:<58} AUROC {r['auroc']:.3f} {r['auroc_ci']} AUPRC {r['auprc']:.3f}{d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
