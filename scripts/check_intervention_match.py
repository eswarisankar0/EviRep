"""
DIAGNOSTIC: does each matched trial actually test the compound it was matched to?

Script 03 queries ClinicalTrials.gov with `query.intr=<compound>` and then verifies
client-side that the trial's CONDITION really is Parkinson's (`is_actually_pd`).
It does NOT verify that the trial's INTERVENTION really is the queried compound.

ClinicalTrials.gov expands intervention queries by chemical class, prodrug/metabolite
relationship and excipient content, so a query can return trials of a completely
different drug. Observed on the 2026-10-05 real run:

    query.intr="Phenol"          -> levodopa/carbidopa trials (levodopa is a phenol)
    query.intr="Norepinephrine"  -> Droxidopa trials (droxidopa is an NE prodrug)
    query.intr="Dopamine"        -> Sarizotan / Safinamide / pramipexole trials
    query.intr="Mannitol"        -> Droxidopa trials (mannitol is an excipient)
    query.intr="Pregabalin"      -> a registry study listing many drugs

This script quantifies how far that contamination reaches. It is READ-ONLY with respect
to the pipeline: it writes one new diagnostic CSV and changes no stage's behaviour and no
existing output. Whether to tighten script 03's inclusion criteria is a methodological
decision for the project owner -- see TECHNICAL_DEBT TD-018.

Run from the repository root:
    ./venv/bin/python scripts/check_intervention_match.py

Output:
    data/intervention_match_check.csv
"""

import os
import time

import pandas as pd
import requests
from tqdm import tqdm

PRE = "data/clinical_maturity_precutoff_clean.csv"
POST = "data/ground_truth_postcutoff_clean.csv"
OUT = "data/intervention_match_check.csv"
SLEEP = 0.35

#: Trials that enumerate many drugs at once (registries, quality-improvement
#: cohorts) match almost any compound query. Detected by this phrase appearing
#: in an intervention name rather than hardcoding NCT IDs.
CATCH_ALL_MARKERS = ("listed for each disorder", "up to three drugs")


def normalise(text):
    return "".join(ch for ch in str(text).lower() if ch.isalnum() or ch == " ")


def fetch_interventions(nct_id):
    """Return (brief_title, [intervention names]) or (None, None) on failure."""
    url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
    try:
        r = requests.get(url, timeout=25)
        r.raise_for_status()
        proto = r.json().get("protocolSection", {})
    except Exception as exc:  # noqa: BLE001 - diagnostic, keep going
        return None, [f"__ERROR__ {type(exc).__name__}: {exc}"]
    title = proto.get("identificationModule", {}).get("briefTitle", "")
    names = []
    for item in proto.get("armsInterventionsModule", {}).get("interventions", []):
        names.append(item.get("name", ""))
        names.extend(item.get("otherNames", []) or [])
    return title, names


def classify(compound, title, names):
    """
    Conservative verdict for one (compound, trial) pair.

    A compound is only called MATCHED when its name appears in an intervention
    name or an officially listed otherName. Anything else is reported as
    NAME_NOT_FOUND, which is a *flag for review*, not proof of error -- a trial
    may legitimately use a synonym this check does not know about.
    """
    if any(n.startswith("__ERROR__") for n in names):
        return "FETCH_ERROR"
    if not names:
        return "NO_INTERVENTIONS_LISTED"
    blob = normalise(" | ".join(names))
    if any(marker in blob for marker in CATCH_ALL_MARKERS):
        return "CATCH_ALL_STUDY"
    needle = normalise(compound)
    if needle and needle in blob:
        return "MATCHED"
    # Single-word compounds may appear as a stem inside a longer name.
    head = needle.split()[0] if needle.split() else ""
    if len(head) >= 6 and head in blob:
        return "MATCHED_PARTIAL"
    return "NAME_NOT_FOUND"


def main():
    if not (os.path.exists(PRE) and os.path.exists(POST)):
        raise SystemExit(
            f"Missing {PRE} or {POST}. Run stage 03 then filter_by_studytype.py first."
        )

    pre = pd.read_csv(PRE).assign(cohort="pre")
    post = pd.read_csv(POST).assign(cohort="post")
    trials = pd.concat([pre, post])[["compound_name", "nct_id", "cohort"]].drop_duplicates()

    print(f"Checking {len(trials)} (compound, trial) pairs "
          f"across {trials.compound_name.nunique()} compounds...")

    # One fetch per NCT, reused across compounds that matched the same trial.
    cache = {}
    rows = []
    for _, row in tqdm(trials.iterrows(), total=len(trials)):
        nct = row.nct_id
        if nct not in cache:
            cache[nct] = fetch_interventions(nct)
            time.sleep(SLEEP)
        title, names = cache[nct]
        rows.append({
            "compound_name": row.compound_name,
            "nct_id": nct,
            "cohort": row.cohort,
            "verdict": classify(row.compound_name, title, names),
            "brief_title": (title or "")[:120],
            "interventions": "; ".join(names)[:220],
        })

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)

    print("\n--- verdict counts (trial level) ---")
    print(out.verdict.value_counts().to_string())

    # Compound level: a compound is "unsupported" when NO trial names it.
    good = {"MATCHED", "MATCHED_PARTIAL"}
    per = out.groupby("compound_name").agg(
        n_trials=("nct_id", "nunique"),
        n_supported=("verdict", lambda s: sum(v in good for v in s)),
    ).reset_index()
    per["fully_unsupported"] = per.n_supported == 0

    print("\n--- compound level ---")
    print(f"compounds checked            : {len(per)}")
    print(f"with >=1 naming trial        : {int((~per.fully_unsupported).sum())}")
    print(f"with NO naming trial (REVIEW): {int(per.fully_unsupported.sum())}")

    print("\nCompounds whose entire clinical evidence is unsupported by intervention name:")
    flagged = per[per.fully_unsupported].sort_values("n_trials", ascending=False)
    print(flagged.head(30).to_string(index=False))

    # Ground-truth impact: positives resting only on unverified trials.
    post_only = out[out.cohort == "post"]
    gt = post_only.groupby("compound_name").agg(
        n_post=("nct_id", "nunique"),
        n_supported=("verdict", lambda s: sum(v in good for v in s)),
    ).reset_index()
    bad_gt = gt[gt.n_supported == 0]
    print(f"\n--- GROUND TRUTH impact ---")
    print(f"post-cutoff (positive) compounds           : {len(gt)}")
    print(f"whose positive label rests on NO naming trial: {len(bad_gt)}")
    if len(bad_gt):
        print(bad_gt.to_string(index=False))

    print(f"\nSaved {OUT}")
    print("\nNOTE: NAME_NOT_FOUND is a REVIEW FLAG, not proof of error -- a trial may use "
          "a synonym this check does not recognise. Inspect before acting.")


if __name__ == "__main__":
    import argparse
    # No options yet: parse anyway so --help or a stray argument exits before any
    # work is done (TD-034; incident E-017 ran stages 05/06 via --help).
    argparse.ArgumentParser(description=__doc__.strip().splitlines()[0] if __doc__ else None).parse_args()
    main()
