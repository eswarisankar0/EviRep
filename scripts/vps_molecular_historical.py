"""
Full historical reconstruction of the molecular dimension (direct AND pathway components) from inputs dated before
the 2020-12-31 cutoff, using stage 08's formula unchanged (scripts/molecular_agent.py, MolecularAgentConfig).
Read-only; outputs to --out (default data/_runs/molecular_historical_20261020/). Nothing is published.

Inputs (data/cache/opentargets_20.11/, the files the Open Targets 20.11 release itself was built from):
  association_lines_EFO_0002508.jsonl   PD rows of 20.11 association_data.json.gz (Nov 2020)
  uniprot-2020-11-10.xml.gz             UniProt snapshot whose Reactome cross-references were 20.11's
                                        target -> pathway membership (input/mrtarget.data.20.11.yml)
Stage 08 rules reproduced:
  PD module   top 300 PD targets by overall association score, kept when the max over MODULE datatypes
              (genetic_association, genetic_literature, animal_model, somatic_mutation, rna_expression) >= 0.10
  direct      max over the drug's targets of the max ALLOWED-datatype score (module datatypes + affected_pathway)
  pathway     distinct Reactome pathways of the drug's targets that contain >= 1 module gene / all of them
              (TD-042 variant: module genes that are the drug's own targets do not count)
  score       0.6 x direct + 0.4 x pathway; no ChEMBL target -> unmeasured (neutral 0.5 after ranking)
Drug -> targets: today's ChEMBL mechanism targets (as stage 08), and -- when the files are present -- the dated
ChEMBL 2020-06 mechanisms 20.11 used (chembl_mechanism / chembl_target_rest_api-2020-06-01.json.gz; human protein
components with an EnsemblGene cross-reference; matched on molecule or parent ChEMBL ID). The membership SOURCE also differs (20.11: UniProt cross-references; 26.09: Reactome via the Open Targets target index),
so a difference mixes the temporal effect with a source/method effect; per-target pathway Jaccard is reported to
size the latter. A method check first rebuilds the 26.09 components from the persisted stage-08 records.

    ./venv/bin/python scripts/vps_molecular_historical.py [--boot 2000]
"""
import argparse
import gzip
import importlib.util
import json
import os
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("vve", os.path.join(HERE, "vps_validation_experiments.py"))
vve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vve)

D = "data/cache/opentargets_20.11/"
ASSOC = D + "association_lines_EFO_0002508.jsonl"
UNIPROT = D + "uniprot-2020-11-10.xml.gz"
EVIDENCE = "data/molecular_pathway_evidence.jsonl"
PD_2011 = "EFO_0002508"
MODULE_DT = ("genetic_association", "genetic_literature", "animal_model", "somatic_mutation", "rna_expression")
ALLOWED_DT = MODULE_DT + ("affected_pathway",)
MODULE_SIZE, MODULE_MIN, W_DIRECT, W_PATHWAY = 300, 0.10, 0.6, 0.4
UP = "{http://uniprot.org/uniprot}"
MECH_2006 = D + "chembl_mechanism_rest_api-2020-06-01.json.gz"
TARGET_2006 = D + "chembl_target_rest_api-2020-06-01.json.gz"


def chembl_targets_2006(root, chembl_ids):
    """{drug ChEMBL ID: sorted Ensembl genes} from the dated 2020-06 mechanisms (human protein components only)."""
    mech, tgt = {}, {}
    with gzip.open(os.path.join(root, MECH_2006), "rt", encoding="utf-8") as fh:
        for line in fh:
            m = json.loads(line)
            for key in {m.get("molecule_chembl_id"), m.get("parent_molecule_chembl_id")} & chembl_ids:
                if m.get("target_chembl_id"):
                    mech.setdefault(key, set()).add(m["target_chembl_id"])
    wanted = set().union(*mech.values()) if mech else set()
    with gzip.open(os.path.join(root, TARGET_2006), "rt", encoding="utf-8") as fh:
        for line in fh:
            t = json.loads(line)
            if t.get("target_chembl_id") not in wanted or t.get("tax_id") != 9606:
                continue
            tgt[t["target_chembl_id"]] = {x["xref_id"] for c in t.get("target_components") or []
                                          if c.get("component_type") == "PROTEIN"
                                          for x in c.get("target_component_xrefs") or [] if x.get("xref_src_db") == "EnsemblGene"}
    return {d: sorted(set().union(*[tgt.get(t, set()) for t in ts])) for d, ts in mech.items()}


def pd_rows_2011(root):
    """{ensembl: (overall, datatypes)} for PD; the indirect row preferred (26.09 associatedTargets are indirect)."""
    best = {}
    with open(os.path.join(root, ASSOC), encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if (r.get("disease") or {}).get("id") != PD_2011:
                continue
            a = r.get("association_score") or {}
            tid, direct = r["target"]["id"], bool(r.get("is_direct"))
            prev = best.get(tid)
            if prev is None or (prev[2] and not direct):
                best[tid] = (float(a.get("overall") or 0.0), {k: float(v) for k, v in (a.get("datatypes") or {}).items()},
                             direct)
    return {k: (v[0], v[1]) for k, v in best.items()}


def module_2011(rows):
    top = sorted(rows, key=lambda t: (-rows[t][0], t))[:MODULE_SIZE]
    return {t for t in top if max([rows[t][1].get(k, 0.0) for k in MODULE_DT] or [0.0]) >= MODULE_MIN}


def uniprot_reactome(path, wanted):
    """{ensembl gene: {R-HSA}} from the UniProt XML, for the wanted genes only (streamed)."""
    out = {}
    with gzip.open(path, "rb") as fh:
        for _, el in ET.iterparse(fh, events=("end",)):
            if el.tag != UP + "entry":
                continue
            genes, paths = set(), set()
            for ref in el.iter(UP + "dbReference"):
                t = ref.get("type")
                if t == "Reactome":
                    paths.add(ref.get("id"))
                elif t == "Ensembl":
                    for p in ref.iter(UP + "property"):
                        if p.get("type") == "gene ID":
                            genes.add(p.get("value").split(".")[0])
            for g in genes & wanted:
                out.setdefault(g, set()).update(paths)
            el.clear()
    return out


def components(target_ids, path_of, module_genes, rows, exclude_own):
    if not target_ids:
        return np.nan, np.nan, 0
    direct = max([max([rows.get(t, (0, {}))[1].get(k, 0.0) for k in ALLOWED_DT] or [0.0]) for t in target_ids])
    tp = set().union(*[path_of.get(t, set()) for t in target_ids])
    mod = module_genes - (set(target_ids) if exclude_own else set())
    mod_paths = set().union(*[path_of.get(g, set()) for g in mod]) if mod else set()
    pathway = len(tp & mod_paths) / len(tp) if tp else 0.0
    return direct, pathway, len(tp)


def current_check(rec):
    """Rebuild the persisted 26.09 pathway component from the record (method check)."""
    by = {}
    for p in rec.get("pathways") or []:
        by[p["pathway_id"]] = by.get(p["pathway_id"], False) or bool(p.get("in_disease_module"))
    return (sum(by.values()) / len(by)) if by else 0.0, {p["pathway_id"] for p in rec.get("pathways") or []}


def run(root=".", n_boot=2000, seed=vve.SEED):
    rows = pd_rows_2011(root)
    module = module_2011(rows)
    recs = {}
    with open(os.path.join(root, EVIDENCE), encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            recs[r["drug"]] = r
    targets = {d: sorted({t["ensembl_id"] for t in r.get("targets") or [] if t.get("ensembl_id")}) for d, r in recs.items()}
    dated = os.path.exists(os.path.join(root, MECH_2006)) and os.path.exists(os.path.join(root, TARGET_2006))
    t2006 = {}
    if dated:
        by_chembl = chembl_targets_2006(root, {r.get("chembl_id") for r in recs.values() if r.get("chembl_id")})
        t2006 = {d: by_chembl.get(r.get("chembl_id"), []) for d, r in recs.items()}
    wanted = module | set().union(*targets.values()) | set().union(*t2006.values()) if t2006 else \
        module | set().union(*targets.values())
    path_of = uniprot_reactome(os.path.join(root, UNIPROT), wanted)
    per, jac, method = {}, [], []
    for d, r in recs.items():
        tids = targets[d]
        sc = (r.get("scoring") or {}).get("components") or {}
        cur_pw, cur_paths = current_check(r)
        if sc.get("pathway_overlap") is not None and tids:
            method.append(abs(cur_pw - float(sc["pathway_overlap"])))
        for t in tids:                                        # per-target membership drift (source + time)
            now = {p["pathway_id"] for p in r.get("pathways") or [] if p.get("ensembl_id") == t}
            then = path_of.get(t, set())
            if now or then:
                jac.append(len(now & then) / len(now | then))
        dir_, pw, n_tp = components(tids, path_of, module, rows, False)
        _, pw_td, _ = components(tids, path_of, module, rows, True)
        extra = {}
        if dated:
            t6 = t2006[d]
            d6, p6, _ = components(t6, path_of, module, rows, False)
            _, p6td, _ = components(t6, path_of, module, rows, True)
            extra = {"n_targets_chembl2006": len(t6), "targets_same_as_today": set(t6) == set(tids),
                     "molecular_2020_chembl2006": W_DIRECT * d6 + W_PATHWAY * p6 if t6 else np.nan,
                     "molecular_2020_chembl2006_td042": W_DIRECT * d6 + W_PATHWAY * p6td if t6 else np.nan}
        per[d] = {**extra, "n_targets": len(tids), "n_target_pathways_2020": n_tp, "direct_2020": dir_, "pathway_2020": pw,
                  "pathway_2020_td042": pw_td,
                  "molecular_2020": W_DIRECT * dir_ + W_PATHWAY * pw if tids else np.nan,
                  "molecular_2020_td042": W_DIRECT * dir_ + W_PATHWAY * pw_td if tids else np.nan,
                  "direct_2609": sc.get("direct_target_disease"), "pathway_2609": sc.get("pathway_overlap"),
                  "molecular_2609_published": r.get("molecular_plausibility_score")}
    P = pd.DataFrame.from_dict(per, orient="index")
    base = vve.build(root)
    cor = vve.build(root, molecular="td042_own_target")
    P = P.reindex(base.index)
    y = base["label"].to_numpy()
    r20 = vve.pct(P["molecular_2020"].astype(float), False, "legacy")
    r20td = vve.pct(P["molecular_2020_td042"].astype(float), False, "legacy")
    S = {"5D published (approved)": base[vve.DIMS5].mean(axis=1),
         "5D TD-042 (candidate)": cor[vve.DIMS5].mean(axis=1),
         "5D, molecular rebuilt at 20.11": base[vve.DIMS5].assign(r_molecular=r20).mean(axis=1),
         "5D TD-042, molecular rebuilt at 20.11": cor[vve.DIMS5].assign(r_molecular=r20td).mean(axis=1),
         "molecular alone: published 26.09": base["r_molecular"], "molecular alone: 20.11": r20,
         "molecular alone: TD-042 26.09": cor["r_molecular"], "molecular alone: TD-042 20.11": r20td}
    if dated:
        r6 = vve.pct(P["molecular_2020_chembl2006"].astype(float), False, "legacy")
        r6td = vve.pct(P["molecular_2020_chembl2006_td042"].astype(float), False, "legacy")
        S["5D, molecular rebuilt at 20.11, ChEMBL 2020-06 targets"] = base[vve.DIMS5].assign(r_molecular=r6).mean(axis=1)
        S["5D TD-042, molecular rebuilt at 20.11, ChEMBL 2020-06 targets"] = cor[vve.DIMS5].assign(r_molecular=r6td).mean(axis=1)
    S = {k: v.to_numpy() for k, v in S.items()}
    rng = np.random.default_rng(seed)
    boot = vve.bootstrap(S, y, n_boot, rng)
    pairs = {"5D, molecular rebuilt at 20.11": "5D published (approved)",
             "5D TD-042, molecular rebuilt at 20.11": "5D TD-042 (candidate)",
             "molecular alone: 20.11": "molecular alone: published 26.09",
             "molecular alone: TD-042 20.11": "molecular alone: TD-042 26.09",
             "5D, molecular rebuilt at 20.11, ChEMBL 2020-06 targets": "5D published (approved)",
             "5D TD-042, molecular rebuilt at 20.11, ChEMBL 2020-06 targets": "5D TD-042 (candidate)"}
    res = []
    for k, s in S.items():
        m = vve.metrics(s, y)
        ref = pairs.get(k)
        res.append({"model": k, **{x: round(v, 4) for x, v in m.items()}, "auroc_ci": vve.ci(boot[k]["auroc"]),
                    "reference": ref,
                    "delta_auroc": None if not ref else round(m["auroc"] - vve.metrics(S[ref], y)["auroc"], 4),
                    "delta_auroc_ci": None if not ref else vve.ci(boot[k]["auroc"] - boot[ref]["auroc"])})
    meas = P["n_targets"] > 0
    return {"n": int(len(y)), "positives": int(y.sum()), "n_boot": n_boot, "seed": seed,
            "pd_rows_2011": len(rows), "module_genes_2011": len(module),
            "module_genes_with_2020_pathways": sum(1 for g in module if path_of.get(g)),
            "drug_targets": len(set().union(*targets.values())),
            "drug_targets_with_2020_pathways": sum(1 for t in set().union(*targets.values()) if path_of.get(t)),
            "method_check_max_abs_pathway_2609_rebuilt_vs_published": round(max(method), 6) if method else None,
            "per_target_pathway_jaccard_2020_vs_2609_median": round(float(np.median(jac)), 3) if jac else None,
            "per_target_pathway_jaccard_2020_vs_2609_iqr": [round(float(q), 3) for q in np.percentile(jac, [25, 75])] if jac else None,
            "spearman_molecular_2020_vs_published": round(float(spearmanr(P.loc[meas, "molecular_2020"],
                                                                           P.loc[meas, "molecular_2609_published"])[0]), 3),
            "spearman_pathway_2020_vs_2609": round(float(spearmanr(P.loc[meas, "pathway_2020"],
                                                                    P.loc[meas, "pathway_2609"])[0]), 3),
            "dated_chembl_targets": None if not dated else {
                "drugs_with_targets_today": int((P["n_targets"] > 0).sum()),
                "drugs_with_targets_chembl2006": int((P["n_targets_chembl2006"] > 0).sum()),
                "drugs_same_target_set": int(P.loc[P["n_targets"] > 0, "targets_same_as_today"].astype(bool).sum())},
            "per_drug": P.reset_index(names="compound_name").round(4).to_dict("records"), "results": res}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="data/_runs/molecular_historical_20261020")
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args(argv)
    for rel in (ASSOC, UNIPROT):
        if not os.path.exists(os.path.join(a.root, rel)):
            print(f"{rel} missing (see docstring for the 20.11 source)", file=sys.stderr)
            return 1
    res = run(a.root, a.boot)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "molecular_historical.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, default=float)
    print({k: v for k, v in res.items() if k not in ("per_drug", "results")})
    for r in res["results"]:
        d = "" if r["delta_auroc"] is None else f"  d={r['delta_auroc']:+.3f} {r['delta_auroc_ci']} vs {r['reference']}"
        print(f"{r['model']:<62} AUROC {r['auroc']:.3f} {r['auroc_ci']} AUPRC {r['auprc']:.3f}{d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
