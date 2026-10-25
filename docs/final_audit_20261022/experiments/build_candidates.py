"""Candidate result sets for the final audit (2026-10-22). Each candidate is the REAL stage-06 code run on substituted
inputs in its own directory; nothing under the base root is written.

    build_candidates.py BASE_ROOT OUT_DIR [--cohort NAME]

Options combined per candidate:
  td042     molecular_pathway.csv from data/_candidates/td042_v1/root (pathway step excludes the drug's own targets)
  p1        data/feature_role_exclusions.csv = TRIAL_ROLE_ADJUDICATION 'NO' links (P1 symmetric with labels, D-020 S1)
  dated     literature = 04p cutoff-bounded primary-record count; safety = 05h label in force at the cutoff (current
            label where no pre-cutoff version: "mixed"); molecular = Open Targets 20.11 + ChEMBL 2020-06 targets
            (td042 rule when td042 is also set). Missing dated values follow stage 06's own rules.
"""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
COHORT_FILES = {"clinical_maturity_precutoff_clean.csv", "ground_truth_postcutoff_clean.csv", "network_proximity.csv",
                "literature_independence.csv", "safety_signal.csv", "molecular_pathway.csv"}
INPUTS = ["pd_candidates_filtered.csv", "network_proximity.csv", "clinical_maturity_precutoff_clean.csv",
          "literature_independence.csv", "safety_signal.csv", "ground_truth_postcutoff_clean.csv",
          "label_role_exclusions.csv", "molecular_pathway.csv"]
VARIANTS = {
    "approved_rules": dict(),
    "td042": dict(td042=True),
    "p1": dict(p1=True),
    "td042_p1": dict(td042=True, p1=True),
    "dated": dict(dated=True),
    "dated_td042": dict(dated=True, td042=True),
    "dated_td042_p1": dict(dated=True, td042=True, p1=True),
    "maxphase": dict(maxphase=True),
    "corrected_all": dict(dated=True, td042=True, p1=True, maxphase=True),
}


def _mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(path))
    spec.loader.exec_module(m)
    return m


def build(base, out, name, td042=False, p1=False, dated=False, maxphase=False, td042_root=None, adjud=None, cohort_root=None,
          proximity=None):
    d = os.path.join(out, name)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(os.path.join(d, "data"))
    for f in INPUTS:
        src = cohort_root if (cohort_root and f in COHORT_FILES) else base
        shutil.copy(os.path.join(src, "data", f), os.path.join(d, "data", f))
    if proximity:
        shutil.copy(proximity, os.path.join(d, "data", "network_proximity.csv"))
    if maxphase:      # highest listed phase per trial (stage-03 fix 2026-10-22), from the registry cache
        c = json.load(open(os.path.join(base, "data/cache/ctgov_precutoff_trials.json")))
        ph = {x["protocolSection"]["identificationModule"]["nctId"]: x["protocolSection"].get("designModule", {}).get("phases") or []
              for x in c["studies"]}
        extra = os.path.join(HERE, "..", "records", "new_links_phases.json")      # rebuilt-cohort trials not in the cache
        if os.path.exists(extra):
            ph.update({k: v for k, v in json.load(open(extra)).items() if not k.startswith("_")})
        order = ("NA", "EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4")
        f = os.path.join(d, "data", "clinical_maturity_precutoff_clean.csv")
        cl = pd.read_csv(f, keep_default_na=False)
        cl["phase"] = [max([p for p in ph[n] if p in order], key=order.index) if ph.get(n) else old
                       for n, old in zip(cl.nct_id, cl.phase)]
        cl.to_csv(f, index=False)
    if td042:
        shutil.copy(os.path.join(td042_root, "data", "molecular_pathway.csv"), os.path.join(d, "data", "molecular_pathway.csv"))
    if p1:
        a = pd.read_csv(adjud)
        clin = pd.read_csv(os.path.join(d, "data", "clinical_maturity_precutoff_clean.csv"))
        pairs = set(zip(clin.nct_id, clin.compound_name))
        ex = a[a.p1_qualifies == "NO"][["nct_id", "compound_name"]]
        ex = ex[[p in pairs for p in zip(ex.nct_id, ex.compound_name)]]        # rebuilt cohorts may lack some links
        ex.to_csv(os.path.join(d, "data", "feature_role_exclusions.csv"), index=False)
    if dated:
        lit = _mod("lcs", os.path.join(base, "scripts", "vps_literature_cutoff_sensitivity.py"))
        src = cohort_root or base          # 04p / 05h outputs of the cohort being scored
        bm = lit.bounded_measures(src)
        li = pd.read_csv(os.path.join(d, "data", "literature_independence.csv"))
        li["effective_independent_count"] = li.compound_name.map(bm["lit_bounded_count"])   # NaN -> stage-06 median
        li.to_csv(os.path.join(d, "data", "literature_independence.csv"), index=False)
        h = pd.read_csv(os.path.join(src, "data", "safety_label_history.csv")).set_index("compound_name")
        s = pd.read_csv(os.path.join(d, "data", "safety_signal.csv"))
        sc = s.compound_name.map(h["state"]) == "PRE_CUTOFF_VERSION_SCORED"
        s.loc[sc, "serious_term_count"] = s.loc[sc, "compound_name"].map(h["cutoff_serious_term_count"]).astype(float)
        s.loc[sc, "boxed_warning"] = s.loc[sc, "compound_name"].map(h["cutoff_boxed_warning"]).astype(str) == "True"
        s.to_csv(os.path.join(d, "data", "safety_signal.csv"), index=False)
        with open(os.path.join(base, "data/_runs/molecular_historical_20261020/molecular_historical.json"), encoding="utf-8") as fh:
            mh = pd.DataFrame(json.load(fh)["per_drug"]).set_index("compound_name")
        col = "molecular_2020_chembl2006_td042" if td042 else "molecular_2020_chembl2006"
        m = pd.read_csv(os.path.join(d, "data", "molecular_pathway.csv"))
        known = m.compound_name.isin(mh.index)
        m.loc[known, "molecular_plausibility_score"] = m.loc[known, "compound_name"].map(mh[col]).astype(float)
        m.loc[known, "n_targets"] = m.loc[known, "compound_name"].map(mh["n_targets_chembl2006"]).fillna(0).astype(int)
        m.loc[known & (m.n_targets == 0), "molecular_plausibility_score"] = 0.0
        m.to_csv(os.path.join(d, "data", "molecular_pathway.csv"), index=False)
    os.makedirs(os.path.join(d, "out"))
    r = subprocess.run([PY, os.path.join(base, "scripts", "06_vps_fusion.py"), "--output-dir", "out"], cwd=d,
                       capture_output=True, text=True)
    with open(os.path.join(d, "stage06.log"), "w") as fh:
        fh.write(r.stdout + r.stderr)
    if r.returncode != 0:
        raise SystemExit(f"{name}: stage 06 failed, see {d}/stage06.log")
    v = subprocess.run([PY, os.path.join(base, "scripts", "vps_verify.py"), "--root", d, "--scores", "out/vps_scores_v2.csv"],
                       capture_output=True, text=True)
    return pd.read_csv(os.path.join(d, "out", "vps_scores_v2.csv")), v.stdout.strip()[:120]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("out")
    ap.add_argument("--cohort", default="approved_cohort")
    ap.add_argument("--td042-root", default=None)
    ap.add_argument("--adjudication", required=True)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--cohort-root", default=None, help="take cohort-defining stage outputs from this root (rebuild)")
    ap.add_argument("--proximity", default=None, help="network_proximity.csv for corrected_all (N_RANDOM=1000)")
    a = ap.parse_args()
    td_root = a.td042_root or os.path.join(a.base, "data/_candidates/td042_v1/root")
    out = os.path.join(a.out, a.cohort)
    os.makedirs(out, exist_ok=True)
    summary = {}
    for name, opts in VARIANTS.items():
        if a.only and name not in a.only:
            continue
        df, verify = build(a.base, out, name, td042_root=td_root, adjud=a.adjudication, cohort_root=a.cohort_root,
                           proximity=a.proximity if name == "corrected_all" else None, **opts)
        summary[name] = {"n": int(len(df)), "positives": int(df.label.sum()), "vps_verify": verify}
        print(a.cohort, name, summary[name], flush=True)
    with open(os.path.join(out, "build_summary.json"), "w") as fh:
        json.dump(summary, fh, indent=1)


if __name__ == "__main__":
    main()
