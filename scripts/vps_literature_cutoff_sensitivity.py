"""
Cutoff-bounded literature sensitivity for VPS (TD-021 / TD-033). Read-only with respect to every published
artifact; outputs go to --out (default data/_runs/literature_cutoff_20261019/).

The published literature dimension (stage 04) counts dependency components among PubMed's 30 MOST RECENT hits,
with no date bound, so post-cutoff papers -- including reports of the very trials that define the labels -- feed a
pre-cutoff prediction. Stage 04p persisted the cutoff-bounded literature. This script replaces r_literature with
cutoff-bounded measures and re-evaluates, everything else unchanged:

  lit_bounded_count        primary pre-cutoff records (journal articles; duplicates, errata, comments, letters,
                           editorials and book chapters removed)
  lit_bounded_author_comp  connected components of those records under shared authorship (no citation edges:
                           Semantic Scholar is rate-limited without a key, so this is an UPPER bound on independence)

Variants are evaluated for the published molecular dimension and the TD-042 candidate, and for the model whose
three inputs are all cutoff-bounded (proximity + clinical + bounded literature). Equal weights throughout (the
weighting decision); no parameter is tuned here.

    ./venv/bin/python scripts/vps_literature_cutoff_sensitivity.py [--boot 2000]
"""
import argparse
import importlib.util
import json
import os
import sys

import networkx as nx
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("vve", os.path.join(HERE, "vps_validation_experiments.py"))
vve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vve)

PAPERS = "data/literature_papers.jsonl"
SAFETY_HISTORY = "data/safety_label_history.csv"
SUMMARY = "data/literature_provenance.csv"


def bounded_measures(root):
    """Per compound: primary pre-cutoff record count and shared-author components. Compounds without a 04p
    record are NaN (median-imputed later, like the published literature dimension); NO_RESULTS is a true 0."""
    j = lambda p: os.path.join(root, p)
    summ = pd.read_csv(j(SUMMARY)).set_index("compound_name")
    by = {}
    with open(j(PAPERS), encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if (r["in_cutoff_bounded_search"] and r["cutoff_status"] == "PRE_CUTOFF" and r["is_primary_record"]
                    and not r["not_primary_evidence_type"] and r.get("record_type", "JOURNAL_ARTICLE") == "JOURNAL_ARTICLE"):
                by.setdefault(r["compound_name"], []).append(r)
    rows = {}
    for name, st in summ["status"].items():
        if st == "RETRIEVAL_FAILED":
            rows[name] = (np.nan, np.nan)
            continue
        recs = by.get(name, [])
        g = nx.Graph()
        g.add_nodes_from(r["pmid"] for r in recs)
        owners = {}
        for r in recs:
            for a in r["authors"]:
                owners.setdefault(a, []).append(r["pmid"])
        for pm in owners.values():
            for other in pm[1:]:
                g.add_edge(pm[0], other)
        rows[name] = (len(recs), nx.number_connected_components(g) if recs else 0)
    return pd.DataFrame.from_dict(rows, orient="index", columns=["lit_bounded_count", "lit_bounded_author_comp"])


def bounded_safety(root, index):
    """Stage-05h label at the cutoff, scored as stage 06 scores safety (serious terms + 5 x boxed; lower is better).
    Returns (mixed, strict): mixed keeps the current label where no pre-cutoff version was found; strict treats
    those as unmeasured (neutral 0.5 after ranking). No label today stays unmeasured in both."""
    h = pd.read_csv(os.path.join(root, SAFETY_HISTORY)).set_index("compound_name").reindex(index)
    cur = np.where(h["stage05_has_label"].astype(str) == "True",
                   h["stage05_serious_term_count"].astype(float) + 5 * (h["stage05_boxed_warning"].astype(str) == "True"),
                   np.nan)
    scored = h["state"] == "PRE_CUTOFF_VERSION_SCORED"
    cut = h["cutoff_serious_term_count"].astype(float) + 5 * (h["cutoff_boxed_warning"].astype(str) == "True")
    mixed = pd.Series(np.where(scored, cut, cur), index=index)
    strict = pd.Series(np.where(scored, cut, np.nan), index=index)
    return mixed, strict, int(scored.sum())


def run(root=".", n_boot=2000, seed=vve.SEED):
    rng = np.random.default_rng(seed)
    base = vve.build(root)
    td = vve.build(root, molecular="td042_own_target")
    meas = bounded_measures(root).reindex(base.index)
    n_missing = int(meas["lit_bounded_count"].isna().sum())
    y = base["label"].to_numpy()
    scores, ranks = {}, {}
    for feat in ("lit_bounded_count", "lit_bounded_author_comp"):
        v = meas[feat].fillna(meas[feat].median())
        ranks[feat] = vve.pct(v, False, "legacy")
    r_lit_pub = base["r_literature"]
    scores["5D published (approved)"] = base[vve.DIMS5].mean(axis=1)
    scores["5D TD-042 (candidate)"] = td[vve.DIMS5].mean(axis=1)
    scores["4D published literature"] = base[vve.DIMS4].mean(axis=1)
    for feat, label in (("lit_bounded_count", "count"), ("lit_bounded_author_comp", "author components")):
        rb = ranks[feat]
        scores[f"5D published, literature = bounded {label}"] = base[vve.DIMS5].assign(r_literature=rb).mean(axis=1)
        scores[f"5D TD-042, literature = bounded {label}"] = td[vve.DIMS5].assign(r_literature=rb).mean(axis=1)
        scores[f"4D, literature = bounded {label}"] = base[vve.DIMS4].assign(r_literature=rb).mean(axis=1)
        scores[f"cutoff-bounded trio (proximity + clinical + bounded {label})"] = \
            pd.concat([base["r_proximity"], base["r_clinical"], rb], axis=1).mean(axis=1)
    scores["literature alone: published"] = r_lit_pub
    for feat, label in (("lit_bounded_count", "count"), ("lit_bounded_author_comp", "author components")):
        scores[f"literature alone: bounded {label}"] = ranks[feat]
    scores["cutoff-bounded pair (proximity + clinical)"] = base[["r_proximity", "r_clinical"]].mean(axis=1)
    n_safety_scored = None
    if os.path.exists(os.path.join(root, SAFETY_HISTORY)):
        mixed, strict, n_safety_scored = bounded_safety(root, base.index)
        r_mixed, r_strict = vve.pct(mixed, True, "legacy"), vve.pct(strict, True, "legacy")
        rb = ranks["lit_bounded_count"]
        scores["5D published, safety = label at cutoff where available"] = base[vve.DIMS5].assign(r_safety=r_mixed).mean(axis=1)
        scores["5D published, safety = label at cutoff only (others neutral)"] = \
            base[vve.DIMS5].assign(r_safety=r_strict).mean(axis=1)
        scores["4D, literature bounded + safety at cutoff where available"] = \
            base[vve.DIMS4].assign(r_literature=rb, r_safety=r_mixed).mean(axis=1)
        scores["5D published, literature bounded + safety at cutoff where available"] = \
            base[vve.DIMS5].assign(r_literature=rb, r_safety=r_mixed).mean(axis=1)
    S = {k: v.to_numpy() for k, v in scores.items()}
    boot = vve.bootstrap(S, y, n_boot, rng)
    ref_for = lambda k: ("5D TD-042 (candidate)" if "TD-042" in k else
                         "4D published literature" if k.startswith("4D,") else
                         "4D published literature" if k.startswith("4D") else
                         "cutoff-bounded pair (proximity + clinical)" if k.startswith("cutoff-bounded trio") else
                         "literature alone: published" if k.startswith("literature alone") else
                         "5D published (approved)")
    rows = []
    for k, s in S.items():
        m = vve.metrics(s, y)
        ref = ref_for(k)
        d = boot[k]["auroc"] - boot[ref]["auroc"]
        rows.append({"model": k, **{x: round(v, 4) for x, v in m.items()},
                     "auroc_ci": vve.ci(boot[k]["auroc"]), "auprc_ci": vve.ci(boot[k]["auprc"]),
                     "reference": ref if ref != k else None,
                     "delta_auroc_vs_reference": None if ref == k else round(m["auroc"] - vve.metrics(S[ref], y)["auroc"], 4),
                     "delta_auroc_ci": None if ref == k else vve.ci(d)})
    raw = pd.read_csv(os.path.join(root, "data/literature_independence.csv")).set_index("compound_name").reindex(base.index)
    corr = {feat: round(float(spearmanr(meas[feat], raw["effective_independent_count"], nan_policy="omit")[0]), 3)
            for feat in ("lit_bounded_count", "lit_bounded_author_comp")}
    return {"n": int(len(y)), "positives": int(y.sum()), "prevalence": round(float(y.mean()), 4),
            "n_boot": n_boot, "seed": seed, "n_compounds_without_04p_record": n_missing,
            "n_safety_labels_scored_at_cutoff": n_safety_scored,
            "spearman_vs_published_literature": corr,
            "measures": meas.reset_index(names="compound_name").to_dict("records"),
            "results": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="data/_runs/literature_cutoff_20261019")
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args(argv)
    res = run(a.root, a.boot)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "literature_cutoff_sensitivity.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    pd.DataFrame(res["results"]).to_csv(os.path.join(a.out, "literature_cutoff_sensitivity.csv"), index=False)
    print(f"n={res['n']} positives={res['positives']} boot={res['n_boot']} "
          f"spearman vs published literature {res['spearman_vs_published_literature']}")
    for r in res["results"]:
        d = "" if r["delta_auroc_vs_reference"] is None else \
            f"  d={r['delta_auroc_vs_reference']:+.3f} {r['delta_auroc_ci']} vs {r['reference']}"
        print(f"{r['model']:<75} AUROC {r['auroc']:.3f} {r['auroc_ci']} AUPRC {r['auprc']:.3f} P@10 {r['p_at_10']:.2f}{d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
