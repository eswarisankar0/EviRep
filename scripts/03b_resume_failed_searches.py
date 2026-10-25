"""
STEP 3b: resume ClinicalTrials.gov searches that failed with an API error.

Stage 03 has no checkpoint: it holds results in memory and writes once at the
end. A transient network outage therefore leaves a *complete-looking* run whose
audit contains API_FAILURE rows for every compound that could not be searched.
That happened on 2026-10-05 (local DNS failure: "Failed to resolve
'clinicaltrials.gov'"), leaving 84 of 1483 compounds unsearched.

An API_FAILURE is NOT evidence of absence, so those compounds cannot simply be
left out. This script re-queries ONLY them, using the exact same code path as
stage 03 (same alias construction, same two gates, same cutoff logic), and
merges the results into the three stage-03 outputs.

It is a resume, not a rerun: the 1399 compounds that already succeeded are
untouched.

Run from the repository root:
    ./venv/bin/python scripts/03b_resume_failed_searches.py
    ./venv/bin/python scripts/03b_resume_failed_searches.py --dry-run

Safety:
  * refuses to run if the audit contains no recoverable API_FAILURE rows;
  * backs up all three outputs before writing;
  * re-queries only compounds whose SEARCH failed (audit rows with no nct_id);
  * leaves every other audit row byte-identical.
"""

import argparse
import importlib.util
import os
import shutil
import sys
import time
from datetime import datetime

import pandas as pd
from tqdm import tqdm

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import intervention_matcher as im  # noqa: E402

PRE = "data/clinical_maturity_precutoff.csv"
POST = "data/ground_truth_postcutoff.csv"
AUDIT = "data/clinicaltrials_match_audit.csv"
CANDIDATES = "data/pd_candidates_filtered.csv"


def load_stage03():
    """Import stage 03 by path (its name starts with a digit)."""
    path = os.path.join(HERE, "03_clinicaltrials_groundtruth.py")
    spec = importlib.util.spec_from_file_location("stage03", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["stage03"] = module
    spec.loader.exec_module(module)
    return module


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be re-queried, change nothing")
    args = ap.parse_args()

    for path in (PRE, POST, AUDIT, CANDIDATES):
        if not os.path.exists(path):
            raise SystemExit(f"Missing {path}. Run scripts/03_clinicaltrials_groundtruth.py first.")

    audit = pd.read_csv(AUDIT)
    # A SEARCH-level failure has no nct_id. (A trial-level API_FAILURE would.)
    failed = audit[(audit.outcome == im.API_FAILURE) & (audit.nct_id.isna())]
    compounds = failed.compound_name.dropna().unique().tolist()

    print(f"Audit rows            : {len(audit)}")
    print(f"Search-level failures : {len(failed)} rows / {len(compounds)} compounds")
    if not compounds:
        print("\nNothing to resume - no recoverable API_FAILURE rows. Exiting.")
        return

    candidates = pd.read_csv(CANDIDATES)
    id_by_name = dict(zip(candidates.compound_name, candidates.compound_id))
    all_names = {im.normalise(c) for c in candidates.compound_name.dropna().unique()}

    print(f"Compounds to re-query : {len(compounds)}")
    if args.dry_run:
        for c in compounds[:20]:
            print(f"   {c}")
        if len(compounds) > 20:
            print(f"   ... and {len(compounds) - 20} more")
        print("\n--dry-run: nothing written.")
        return

    stage03 = load_stage03()

    # Alias sets must use the FULL candidate name set for ambiguity filtering,
    # exactly as the main run does -- not just the 84 being resumed.
    print("\nBuilding alias sets (ChEMBL via OpenTargets, cached)...")
    alias_map, report = stage03.build_alias_map(compounds)
    print(f"  resolved: {report['resolved']}/{report['total']} ({report['source']})")

    new_pre, new_post, new_audit = [], [], []
    still_failed = []
    counts = {"accepted": 0, "condition_rejected": 0,
              "intervention_rejected": 0, "unverifiable": 0}

    print()
    for compound in tqdm(compounds, desc="resuming"):
        cid = id_by_name.get(compound, "")
        studies, ok = stage03.search_trials(compound)
        time.sleep(0.34)

        if not ok:
            still_failed.append(compound)
            new_audit.append({
                "compound_name": compound, "compound_id": cid, "nct_id": "",
                "brief_title": "", "conditions": "", "interventions": "",
                "outcome": im.API_FAILURE, "match_type": "",
                "matched_intervention": "", "matched_alias": "", "match_source": "",
                "qualifies": False, "cohort": "",
                "reason": "ClinicalTrials.gov search failed again on resume",
            })
            continue

        aliases = alias_map.get(compound) or im.build_alias_set(
            compound, ambiguous_names=all_names - {im.normalise(compound)})

        for study in studies:
            proto = study.get("protocolSection", {})
            ident = proto.get("identificationModule", {})
            status_mod = proto.get("statusModule", {})
            design_mod = proto.get("designModule", {})
            conditions = proto.get("conditionsModule", {}).get("conditions", []) or []
            nct_id = ident.get("nctId", "")

            if not stage03.is_actually_pd(study):
                counts["condition_rejected"] += 1
                new_audit.append({
                    "compound_name": compound, "compound_id": cid, "nct_id": nct_id,
                    "brief_title": (ident.get("briefTitle") or "")[:160],
                    "conditions": "; ".join(conditions)[:160], "interventions": "",
                    "outcome": "CONDITION_REJECTED", "match_type": "",
                    "matched_intervention": "", "matched_alias": "",
                    "match_source": "", "qualifies": False, "cohort": "",
                    "reason": "trial conditions do not mention Parkinson's",
                })
                continue

            arms = proto.get("armsInterventionsModule")
            interventions = arms.get("interventions") if arms is not None else None
            verdict = im.match_trial(compound, interventions, aliases)
            iv_names = "; ".join((i.get("name") or "")
                                 for i in (interventions or []))[:200]

            row = {
                "compound_name": compound, "compound_id": cid, "nct_id": nct_id,
                "brief_title": (ident.get("briefTitle") or "")[:160],
                "conditions": "; ".join(conditions)[:160],
                "interventions": iv_names,
                "outcome": verdict["outcome"],
                "match_type": verdict["match_type"] or "",
                "matched_intervention": verdict["matched_intervention"] or "",
                "matched_alias": verdict["matched_alias"] or "",
                "match_source": verdict["match_source"] or "",
                "qualifies": verdict["qualifies"], "cohort": "",
                "reason": verdict["reason"] or "",
            }

            if not verdict["qualifies"]:
                if verdict["outcome"] == im.UNVERIFIABLE:
                    counts["unverifiable"] += 1
                else:
                    counts["intervention_rejected"] += 1
                new_audit.append(row)
                continue

            first_posted = status_mod.get("studyFirstPostDateStruct", {}).get("date", "")
            phases = design_mod.get("phases", [])
            record = {
                "compound_id": cid, "compound_name": compound, "nct_id": nct_id,
                "phase": phases[0] if phases else "NA",
                "status": status_mod.get("overallStatus", ""),
                "enrollment": design_mod.get("enrollmentInfo", {}).get("count", None),
                "first_posted": first_posted,
                "match_type": verdict["match_type"],
                "matched_intervention": verdict["matched_intervention"],
                "matched_alias": verdict["matched_alias"],
                "match_source": verdict["match_source"],
            }
            if first_posted and first_posted < stage03.CUTOFF_DATE:
                row["cohort"] = "pre"; new_pre.append(record); counts["accepted"] += 1
            elif first_posted and first_posted >= stage03.CUTOFF_DATE:
                row["cohort"] = "post"; new_post.append(record); counts["accepted"] += 1
            else:
                row["cohort"] = "no_date"; row["qualifies"] = False
                row["reason"] = "accepted on intervention but has no first-posted date"
            new_audit.append(row)

    # --- backup before writing -------------------------------------------
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"data/_backup_pre_resume_{stamp}"
    os.makedirs(backup, exist_ok=True)
    for path in (PRE, POST, AUDIT):
        shutil.copy2(path, backup)
    print(f"\nBacked up pre-resume outputs to {backup}/")

    # --- merge ------------------------------------------------------------
    resumed = set(compounds)
    audit_keep = audit[~audit.compound_name.isin(resumed)]
    merged_audit = pd.concat([audit_keep, pd.DataFrame(new_audit)], ignore_index=True)
    merged_audit = merged_audit.sort_values(["compound_name", "nct_id"],
                                            na_position="last")

    pre = pd.read_csv(PRE)
    post = pd.read_csv(POST)
    merged_pre = pd.concat([pre[~pre.compound_name.isin(resumed)],
                            pd.DataFrame(new_pre)], ignore_index=True)
    merged_post = pd.concat([post[~post.compound_name.isin(resumed)],
                             pd.DataFrame(new_post)], ignore_index=True)

    merged_pre.to_csv(PRE, index=False)
    merged_post.to_csv(POST, index=False)
    merged_audit.to_csv(AUDIT, index=False)

    print("\n" + "=" * 62)
    print("STEP 3b RESUME COMPLETE")
    print("=" * 62)
    print(f"Compounds re-queried              : {len(compounds)}")
    print(f"  still failing after resume      : {len(still_failed)}")
    print(f"Newly accepted compound-trial links: {counts['accepted']}")
    print(f"  rejected - condition            : {counts['condition_rejected']}")
    print(f"  rejected - intervention         : {counts['intervention_rejected']}")
    print(f"  unverifiable                    : {counts['unverifiable']}")
    print(f"\nPre-cutoff : {len(merged_pre)} rows, "
          f"{merged_pre.compound_name.nunique()} compounds")
    print(f"Post-cutoff: {len(merged_post)} rows, "
          f"{merged_post.compound_name.nunique()} compounds")
    print(f"Audit      : {len(merged_audit)} rows "
          f"({int((merged_audit.outcome == im.API_FAILURE).sum())} API_FAILURE remaining)")
    if still_failed:
        print(f"\nSTILL UNVERIFIED (not evidence of absence): {still_failed}")


if __name__ == "__main__":
    main()
