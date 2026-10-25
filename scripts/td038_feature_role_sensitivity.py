"""
TD-038 sensitivity analysis: what happens to the clinical dimension and the
evaluation if pre-cutoff trial links where the compound is not tested for PD
are excluded? (DECISIONS D-020)

    ./venv/bin/python scripts/td038_feature_role_sensitivity.py

Offline. Inputs: data/feature_trial_roles_td038.csv (per-link adjudication of
the 17 trials credited to more than one pool compound), the cached registry
records data/cache/ctgov_td038_shared_trials.json (one ClinicalTrials.gov v2
request, 2026-10-14), and the stage-06 inputs. Output:
data/td038_feature_role_sensitivity.json, stamped with input md5s.

Nothing here changes the primary outputs: data/vps_scores_v2.csv,
the ground truth and the label exclusions are only read. Each scenario is
recomputed in memory with the stage-06 functions themselves, and the current
scenario must reproduce the persisted scores exactly or the script fails.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from bootstrap_auroc_ci import paired_bootstrap  # noqa: E402
from trial_role import classify_trial_role  # noqa: E402

VERSION = "td038-1.0"
SEED, N_BOOT = 42, 2000
ROLES = "data/feature_trial_roles_td038.csv"
REGISTRY = "data/cache/ctgov_td038_shared_trials.json"
OUT = "data/td038_feature_role_sensitivity.json"
CATEGORIES = ("DRUG_SPECIFIC_ARM", "ALTERNATIVES_IN_ONE_ARM", "FIXED_COMBINATION", "PROCEDURAL",
              "AUXILIARY_AGENT", "UNVERIFIABLE")
INPUTS = ("data/clinical_maturity_precutoff_clean.csv", "data/vps_scores_v2.csv",
          "data/ground_truth_postcutoff_clean.csv", "data/label_role_exclusions.csv", ROLES, REGISTRY)


def _md5(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def _fusion():
    spec = importlib.util.spec_from_file_location("vps_fusion", os.path.join(HERE, "06_vps_fusion.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_roles(clinical, registry):
    """Read the adjudication and check it against the data it describes."""
    roles = pd.read_csv(os.path.join(ROOT, ROLES), keep_default_na=False)
    bad = sorted(set(roles["category"]) - set(CATEGORIES))
    if bad:
        raise ValueError(f"unknown categories {bad}")
    links = clinical.assign(phase=clinical["phase"].fillna("NA"))
    shared = links.groupby("nct_id")["compound_name"].nunique()
    expected = set(map(tuple, links[links["nct_id"].isin(shared[shared > 1].index)][["nct_id", "compound_name"]]
                       .values))
    got = set(zip(roles["nct_id"], roles["compound_name"]))
    if got != expected:
        raise ValueError(f"adjudication does not cover the shared links: missing {sorted(expected - got)}, "
                         f"extra {sorted(got - expected)}")
    phase = dict(zip(zip(links["nct_id"], links["compound_name"]), links["phase"]))
    alias = {(n, c): [c, a, m] for n, c, a, m in links[["nct_id", "compound_name", "matched_alias",
                                                         "matched_intervention"]].values}
    for r in roles.itertuples():
        if phase[(r.nct_id, r.compound_name)] != r.phase:
            raise ValueError(f"{r.nct_id}/{r.compound_name}: phase {r.phase} != {phase[(r.nct_id, r.compound_name)]}")
        live = classify_trial_role(registry[r.nct_id], [str(x) for x in alias[(r.nct_id, r.compound_name)]])
        if live["verdict"] != r.annotator_verdict:
            raise ValueError(f"{r.nct_id}/{r.compound_name}: annotator now says {live['verdict']}")
    return roles


def score(fusion, clinical, keep_lost_as_no_trial=()):
    """Stage-06 equal-weight scores for one version of the clinical table."""
    fc, prox, _, lit, saf, gt = fusion.load_data()
    mol = fusion.load_molecular()
    cm = fusion.build_clinical_maturity(clinical)
    if keep_lost_as_no_trial:
        extra = pd.DataFrame({"compound_name": list(keep_lost_as_no_trial), "max_phase_rank": 0.0, "n_trials": 0})
        cm = pd.concat([cm, extra], ignore_index=True)
    df = fusion.merge_dimensions(fc, prox, cm, lit, saf, mol)
    df = fusion.impute_missing(df)
    df, _ = fusion.impute_molecular(df)
    df = fusion.build_standardized_scores(df)
    gt, _ = fusion.apply_label_exclusions(gt, pd.read_csv(fusion.LABEL_EXCLUSIONS_CSV))
    df = fusion.build_labels(df, gt)
    df = fusion.compute_weighted_vps(df, {d: 0.25 for d in fusion.BASE_DIMENSIONS}, "VPS_equal")
    df = fusion.compute_weighted_vps(df, {d: 0.2 for d in fusion.ALL_DIMENSIONS}, "VPS_equal_5d")
    return df.set_index("compound_name")


def _ci(y, s, metric):
    rng = np.random.default_rng(SEED)
    vals = []
    for _ in range(N_BOOT):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() != y[i].max():
            vals.append(metric(y[i], s[i]))
    return [round(float(np.percentile(vals, 2.5)), 3), round(float(np.percentile(vals, 97.5)), 3)]


def metrics(df):
    y = df["label"].values
    out = {"n": len(df), "positives": int(y.sum())}
    for col, key in (("VPS_equal", "4d"), ("VPS_equal_5d", "5d")):
        s = df[col].values
        out[key] = {"auroc": round(roc_auc_score(y, s), 3), "auroc_ci": _ci(y, s, roc_auc_score),
                    "auprc": round(average_precision_score(y, s), 3),
                    "auprc_ci": _ci(y, s, average_precision_score)}
    p = paired_bootstrap(y, df["VPS_equal_5d"].values, df["VPS_equal"].values, n_boot=N_BOOT, seed=SEED)
    out["5d_minus_4d"] = {k: (round(v, 3) if isinstance(v, float) else [round(x, 3) for x in v])
                          for k, v in p.items() if k in ("diff", "ci_diff", "p_diff_gt_0")}
    return out


def compare(old, new, col="VPS_equal_5d"):
    """Same compounds, old vs new score: paired AUROC difference and rank changes."""
    common = old.index.intersection(new.index)
    o, n = old.loc[common], new.loc[common]
    y = o["label"].values
    p = paired_bootstrap(y, n[col].values, o[col].values, n_boot=N_BOOT, seed=SEED)
    r_old = old[col].rank(ascending=False, method="min")
    r_new = new[col].rank(ascending=False, method="min")
    moved = [{"compound": c, "label": int(o.loc[c, "label"]), "rank_old": int(r_old[c]), "rank_new": int(r_new[c])}
             for c in common if abs(r_old[c] - r_new[c]) >= 3]
    pos = [{"compound": c, "rank_old": int(r_old[c]), "rank_new": int(r_new[c])}
           for c in common if o.loc[c, "label"] == 1]
    return {"score": col, "n_common": len(common), "paired_new_minus_old": p,
            "positives_rank": sorted(pos, key=lambda x: x["rank_new"]),
            "moved_3_or_more_ranks": sorted(moved, key=lambda x: x["rank_new"])}


def build():
    os.chdir(ROOT)
    fusion = _fusion()
    clinical = pd.read_csv("data/clinical_maturity_precutoff_clean.csv")
    with open(REGISTRY) as fh:
        registry = {s["protocolSection"]["identificationModule"]["nctId"]: s for s in json.load(fh)["studies"]}
    roles = load_roles(clinical, registry)

    base = score(fusion, clinical)
    persisted = pd.read_csv("data/vps_scores_v2.csv").set_index("compound_name")
    for col in ("VPS_equal", "VPS_equal_5d", "label"):
        if not np.allclose(base.loc[persisted.index, col].values, persisted[col].values, atol=1e-12):
            raise RuntimeError(f"current scenario does not reproduce persisted {col}")

    def sel(mask):
        return roles[mask][["nct_id", "compound_name"]]

    no = roles["p1_qualifies"] == "NO"
    adjunct = roles["combination_role"] == "ADJUNCT"
    combo_or_unver = roles["category"].isin(["FIXED_COMBINATION", "UNVERIFIABLE"])
    scen_defs = {
        "S1_exclude_P1_NO": ("exclude PROCEDURAL and AUXILIARY_AGENT links (P1 criterion); compounds left "
                             "with no link leave the pool", sel(no)),
        "S2_S1_plus_combination_adjuncts": ("S1 and also the adjunct component of fixed-dose combinations "
                                            "(naloxone, quinidine)", sel(no | adjunct)),
        "S3_S1_plus_all_combinations_and_unverifiable": ("S1 and every FIXED_COMBINATION and UNVERIFIABLE link",
                                                         sel(no | combo_or_unver)),
    }
    scenarios = {"S0_current": {"definition": "persisted inputs (no exclusion)", "excluded_links": 0,
                                "compounds_leaving_pool": [], **metrics(base)}}
    clin_changes = {}
    frames = {}
    for key, (desc, excl) in scen_defs.items():
        kept, lost = fusion.apply_feature_exclusions(clinical, excl)
        df = score(fusion, kept)
        frames[key] = df
        scenarios[key] = {"definition": desc, "excluded_links": len(excl), "compounds_leaving_pool": lost,
                          "labels_of_leaving": {c: int(base.loc[c, "label"]) for c in lost}, **metrics(df),
                          "cohort_effect_only": metrics(base.loc[df.index]),
                          "vs_current_same_compounds": compare(base, df)}
        ch = []
        for c in df.index:
            if df.loc[c, "max_phase_rank"] != base.loc[c, "max_phase_rank"]:
                ch.append({"compound": c, "max_phase_rank_old": float(base.loc[c, "max_phase_rank"]),
                           "max_phase_rank_new": float(df.loc[c, "max_phase_rank"])})
        clin_changes[key] = ch
        scenarios[key]["max_phase_changes_in_pool"] = ch
    # Alternative to leaving the pool: keep the compound, clinical evidence = lowest phase rank.
    kept, lost = fusion.apply_feature_exclusions(clinical, sel(no))
    alt = score(fusion, kept, keep_lost_as_no_trial=lost)
    scenarios["S1k_exclude_P1_NO_keep_in_pool"] = {
        "definition": "as S1, but compounds with no remaining link stay in the pool with max_phase_rank 0",
        "excluded_links": int(no.sum()), "compounds_leaving_pool": [], **metrics(alt),
        "vs_current_same_compounds": compare(base, alt)}

    tally = roles.groupby(["category", "p1_qualifies"]).size().reset_index(name="links")
    return {"version": VERSION, "seed": SEED, "n_boot": N_BOOT,
            "inputs": {p: _md5(p) for p in INPUTS},
            "status": "SENSITIVITY ONLY - primary outputs unchanged; policy pending owner decision (D-020)",
            "shared_trials": int(roles["nct_id"].nunique()), "shared_links": len(roles),
            "affected_compounds": int(roles["compound_name"].nunique()),
            "adjudication_tally": tally.to_dict(orient="records"),
            "reproduces_persisted_scores": True,
            "scenarios": scenarios}


def main(argv=None):
    ap = argparse.ArgumentParser(description="TD-038 feature-link role sensitivity analysis (offline)")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(argv)
    rep = build()
    path = os.path.join(ROOT, args.out)
    with open(path + ".tmp", "w") as fh:
        json.dump(rep, fh, indent=1, default=float)
    os.replace(path + ".tmp", path)
    for k, s in rep["scenarios"].items():
        print(f"{k}: n={s['n']} pos={s['positives']} 4d {s['4d']['auroc']} {s['4d']['auroc_ci']} "
              f"5d {s['5d']['auroc']} {s['5d']['auroc_ci']} AUPRC5d {s['5d']['auprc']} leave={s['compounds_leaving_pool']}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
