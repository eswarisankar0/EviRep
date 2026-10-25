"""
Evidence overlap between VPS dimensions (mission Step B; 10g asks the same question per compound). Read-only:
every input is a persisted artifact or the stage-04p PubMed cache; outputs go to --out
(default data/_runs/evidence_overlap_20261020/).

1. Trial-paper overlap. A paper is linked to a trial when its PubMed record lists the NCT ID in the
   ClinicalTrials.gov DataBank (registry link deposited with the record) or the NCT ID appears in the title or
   abstract. For every compound, papers in
     - the stage-04 sample (the 30 most recent hits, which the APPROVED literature dimension is built from), and
     - the cutoff-bounded 04p set,
   are classified as reporting
     - a pre-cutoff FEATURE trial of the same compound (clinical_maturity_precutoff_clean.csv): the same study
       counted by the clinical and the literature dimension (double counting);
     - a post-cutoff LABEL trial of the same compound (ground_truth_postcutoff_clean.csv minus exclusions):
       label leakage into a feature.
   NCT IDs found only in text are a lower bound on linkage (many trial reports cite no registry number).
2. Dimension dependence: Spearman correlation between the five percentile-ranked dimensions.
3. Sensitivity (equal weights, nothing tuned): the cutoff-bounded literature count with papers that report a
   feature trial of the same compound removed, so a trial is counted by the clinical dimension only.

    ./venv/bin/python scripts/vps_evidence_overlap.py [--boot 2000]
"""
import argparse
import glob
import importlib.util
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("vve", os.path.join(HERE, "vps_validation_experiments.py"))
vve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vve)

PAPERS = "data/literature_papers.jsonl"
CACHE = "data/cache/pubmed_lit"
FEATURES = "data/clinical_maturity_precutoff_clean.csv"
LABELS = "data/ground_truth_postcutoff_clean.csv"
EXCLUSIONS = "data/label_role_exclusions.csv"
NCT_RE = re.compile(r"\bNCT\s?(\d{8})\b", re.I)


def trial_links(xml_text):
    """{pmid: {"databank": set, "text": set}} of NCT IDs for every article in one efetch payload."""
    out = {}
    root = ET.fromstring(xml_text)
    for art in root.iter("PubmedArticle"):
        pmid = art.findtext("MedlineCitation/PMID")
        if not pmid:
            continue
        bank = set()
        for db in art.iter("DataBank"):
            if (db.findtext("DataBankName") or "").strip().lower() == "clinicaltrials.gov":
                bank |= {a.text.strip().upper() for a in db.iter("AccessionNumber") if a.text}
        text = " ".join(filter(None, [art.findtext("MedlineCitation/Article/ArticleTitle")] +
                                     ["".join(t.itertext()) for t in art.iter("AbstractText")]))
        found = {"NCT" + m for m in NCT_RE.findall(text)}
        out[pmid] = {"databank": bank, "text": found - bank}
    return out


def load_links(root):
    links = {}
    for path in sorted(glob.glob(os.path.join(root, CACHE, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            c = json.load(fh)
        for x in c.get("efetch_xml") or []:
            links.update(trial_links(x))
    return links


def overlap(root):
    j = lambda p: os.path.join(root, p)
    links = load_links(root)
    feat = pd.read_csv(j(FEATURES)).groupby("compound_name")["nct_id"].apply(set).to_dict()
    gt = pd.read_csv(j(LABELS))
    gt = gt[~gt["nct_id"].isin(set(pd.read_csv(j(EXCLUSIONS))["nct_id"]))]
    lab = gt.groupby("compound_name")["nct_id"].apply(set).to_dict()
    rows, papers = {}, []
    with open(j(PAPERS), encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            c, pm = r["compound_name"], r["pmid"]
            lk = links.get(pm)
            ncts = (lk["databank"] | lk["text"]) if lk else set()
            f, l_ = ncts & feat.get(c, set()), ncts & lab.get(c, set())
            row = rows.setdefault(c, {k: 0 for k in (
                "sample_papers", "sample_feature_trial_papers", "sample_label_trial_papers", "sample_any_nct_papers",
                "bounded_papers", "bounded_feature_trial_papers", "bounded_label_trial_papers")} | {"xml_missing": 0})
            if lk is None:
                row["xml_missing"] += 1
            bounded = (r["in_cutoff_bounded_search"] and r["cutoff_status"] == "PRE_CUTOFF" and r["is_primary_record"]
                       and not r["not_primary_evidence_type"]
                       and r.get("record_type", "JOURNAL_ARTICLE") == "JOURNAL_ARTICLE")
            if r["in_stage04_sample"]:
                row["sample_papers"] += 1
                row["sample_feature_trial_papers"] += bool(f)
                row["sample_label_trial_papers"] += bool(l_)
                row["sample_any_nct_papers"] += bool(ncts)
            if bounded:
                row["bounded_papers"] += 1
                row["bounded_feature_trial_papers"] += bool(f)
                row["bounded_label_trial_papers"] += bool(l_)
            if f or l_:
                papers.append({"compound_name": c, "pmid": pm, "feature_trials": sorted(f), "label_trials": sorted(l_),
                               "via_databank": sorted((f | l_) & (lk["databank"] if lk else set())),
                               "in_stage04_sample": r["in_stage04_sample"], "in_bounded_set": bounded,
                               "cutoff_status": r["cutoff_status"], "earliest_pub_date": r.get("earliest_pub_date")})
    return pd.DataFrame.from_dict(rows, orient="index"), papers, len(links)


def run(root=".", n_boot=2000, seed=vve.SEED):
    rng = np.random.default_rng(seed)
    base = vve.build(root)
    ov, papers, n_xml = overlap(root)
    ov = ov.reindex(base.index)
    y = base["label"].to_numpy()
    corr = base[vve.DIMS5].corr(method="spearman").round(3)
    # bounded count, and the same with feature-trial reports removed (counted by the clinical dimension only)
    cnt = ov["bounded_papers"].astype(float)
    dedup = (ov["bounded_papers"] - ov["bounded_feature_trial_papers"]).astype(float)
    r_cnt = vve.pct(cnt.fillna(cnt.median()), False, "legacy")
    r_dedup = vve.pct(dedup.fillna(dedup.median()), False, "legacy")
    S = {"5D published (approved)": base[vve.DIMS5].mean(axis=1),
         "5D, literature = bounded count": base[vve.DIMS5].assign(r_literature=r_cnt).mean(axis=1),
         "5D, literature = bounded count without feature-trial reports":
             base[vve.DIMS5].assign(r_literature=r_dedup).mean(axis=1)}
    S = {k: v.to_numpy() for k, v in S.items()}
    boot = vve.bootstrap(S, y, n_boot, rng)
    ref = "5D, literature = bounded count"
    res = []
    for k, s in S.items():
        m = vve.metrics(s, y)
        r = ref if k.endswith("feature-trial reports") else ("5D published (approved)" if k != "5D published (approved)" else None)
        res.append({"model": k, **{x: round(v, 4) for x, v in m.items()}, "auroc_ci": vve.ci(boot[k]["auroc"]),
                    "reference": r, "delta_auroc": None if not r else round(m["auroc"] - vve.metrics(S[r], y)["auroc"], 4),
                    "delta_auroc_ci": None if not r else vve.ci(boot[k]["auroc"] - boot[r]["auroc"])})
    lab = base["label"].astype(bool)
    summ = {
        "n": int(len(y)), "positives": int(y.sum()), "n_boot": n_boot, "seed": seed, "pubmed_records_parsed": n_xml,
        "compounds_sample_reports_feature_trial": int((ov["sample_feature_trial_papers"] > 0).sum()),
        "compounds_sample_reports_label_trial": int((ov["sample_label_trial_papers"] > 0).sum()),
        "positives_sample_reports_label_trial": int(((ov["sample_label_trial_papers"] > 0) & lab).sum()),
        "compounds_bounded_reports_feature_trial": int((ov["bounded_feature_trial_papers"] > 0).sum()),
        "compounds_bounded_reports_label_trial": int((ov["bounded_label_trial_papers"] > 0).sum()),
        "papers_in_sample": int(ov["sample_papers"].sum()),
        "papers_in_sample_with_any_nct": int(ov["sample_any_nct_papers"].sum()),
        "papers_without_cached_xml": int(ov["xml_missing"].sum()),
    }
    return {**summ, "spearman_between_dimensions": corr.to_dict(), "results": res,
            "per_compound": ov.assign(label=base["label"]).reset_index(names="compound_name").to_dict("records"),
            "linked_papers": papers}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="data/_runs/evidence_overlap_20261020")
    ap.add_argument("--boot", type=int, default=2000)
    a = ap.parse_args(argv)
    res = run(a.root, a.boot)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "evidence_overlap.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, default=int)
    print({k: v for k, v in res.items() if k not in ("per_compound", "linked_papers", "results",
                                                     "spearman_between_dimensions")})
    print(pd.DataFrame(res["spearman_between_dimensions"]))
    for r in res["results"]:
        d = "" if r["delta_auroc"] is None else f"  d={r['delta_auroc']:+.3f} {r['delta_auroc_ci']} vs {r['reference']}"
        print(f"{r['model']:<62} AUROC {r['auroc']:.3f} {r['auroc_ci']} AUPRC {r['auprc']:.3f}{d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
