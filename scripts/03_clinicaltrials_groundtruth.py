"""
STEP 3: ClinicalTrials.gov evidence, split into pre/post cutoff.

Two client-side gates. Never trust the API filter alone.

  Gate 1 (CONDITION)     - the trial's own conditions must mention Parkinson's.
                           Added earlier: the unquoted multi-word query was
                           OR'd by Essie, so "Disease" alone pulled in cancer
                           trials. The phrase is now quoted AND verified.

  Gate 2 (INTERVENTION)  - NEW. The trial must actually administer the queried
                           compound. `query.intr` expands by chemical class,
                           prodrug/metabolite relation, pharmacological class,
                           excipient content and registry catch-alls, so the
                           search alone returned trials of entirely different
                           drugs:

                               Phenol         -> levodopa/carbidopa trials
                               Norepinephrine -> droxidopa trials
                               Dopamine       -> sarizotan/safinamide/pramipexole
                               Mannitol       -> droxidopa (excipient)

                           Matching policy lives in scripts/intervention_matcher.py
                           and uses ONLY structured intervention fields plus
                           ChEMBL-verified synonyms. See ERRORS_AND_BLOCKERS
                           E-010 and TECHNICAL_DEBT TD-018.

The cutoff methodology is UNCHANGED: pre-cutoff trials are a feature,
post-cutoff trials are ground truth only. Gate 2 changes which trials belong to
a compound, not what "positive" means.

Outputs:
    data/clinical_maturity_precutoff.csv
    data/ground_truth_postcutoff.csv
    data/clinicaltrials_match_audit.csv   <- every accept/reject decision
"""
import os, sys, requests, pandas as pd, time
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import intervention_matcher as im
from molecular_agent import (
    MolecularAgentConfig,
    OpenTargetsClient,
    OpenTargetsUnavailable,
    get_drug_mechanisms,
    normalize_drug_batch,
)

os.makedirs("data", exist_ok=True)

CUTOFF_DATE = "2021-01-01"
API_BASE = "https://clinicaltrials.gov/api/v2/studies"
AUDIT_FILE = "data/clinicaltrials_match_audit.csv"

# Transport accounting. An API failure must never be silently recorded as
# "this compound has no trials" -- see ERRORS_AND_BLOCKERS E-010.
SEARCH_STATS = {"ok": 0, "failed": 0, "retries": 0}
MAX_RETRIES = 4
BACKOFF_BASE = 1.0
#: Consecutive failed searches after which the registry is treated as unreachable. Without this an outage
#: retried every one of ~1500 compounds (~15 s each, ~6 h) before reporting failure (found 2026-10-19).
MAX_CONSECUTIVE_FAILURES = 10
PAGE_SIZE = 100          # registry maximum is 1000; 100 keeps responses small
MAX_PAGES = 50           # 5,000 studies per compound; more is treated as a failed search, never truncated silently

def search_trials(drug_name, disease_phrase='"Parkinson Disease"'):
    """
    Returns (studies, ok). `ok` is False when the search could not be completed.

    Previously this returned [] on any exception, making an API failure
    indistinguishable from "this compound has no PD trials" -- silently
    converting an outage into evidence of absence. Retries 429/5xx with
    exponential backoff before giving up.
    """
    # Every page is fetched (audit 2026-10-20, S-03): with pageSize 20 and no pagination, 12 compounds were
    # silently truncated (Dopamine 280 hits, Phenol 137, Ioflupane I 123 27, ...), so trials beyond the first page
    # were never seen. A failed page fails the whole search: a partial result is never returned as complete.
    studies, token = [], None
    for _ in range(MAX_PAGES):
        page, ok, token = _search_page(drug_name, disease_phrase, token)
        if not ok:
            return [], False
        studies += page
        if not token:
            return studies, True
    SEARCH_STATS["failed"] += 1
    print(f"  SEARCH FAILED for {drug_name}: more than {MAX_PAGES} pages")
    return [], False


def _search_page(drug_name, disease_phrase, token):
    """One page of the search: (studies, ok, next_page_token)."""
    params = {
        "query.intr": drug_name,
        "query.cond": disease_phrase,   # quoted = exact phrase, not OR'd words
        "pageSize": PAGE_SIZE,
    }
    if token:
        params["pageToken"] = token
    last = "unknown"
    for attempt in range(MAX_RETRIES + 1):
        if attempt:
            time.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))
            SEARCH_STATS["retries"] += 1
        try:
            r = requests.get(API_BASE, params=params, timeout=25)
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            continue
        if r.status_code == 429 or r.status_code >= 500:
            last = f"HTTP {r.status_code}"
            retry_after = r.headers.get("Retry-After")
            if retry_after:
                try:
                    time.sleep(min(float(retry_after), 60.0))
                except ValueError:
                    pass
            continue
        if r.status_code != 200:
            last = f"HTTP {r.status_code}"
            break
        try:
            j = r.json()
            SEARCH_STATS["ok"] += 1
            return j.get("studies", []), True, j.get("nextPageToken")
        except ValueError as e:
            last = f"invalid JSON: {e}"
            continue
    SEARCH_STATS["failed"] += 1
    print(f"  SEARCH FAILED for {drug_name}: {last}")
    return [], False, None


def build_alias_map(compounds):
    """
    Retrieve VERIFIED synonyms and trade names for each compound from ChEMBL,
    via the Open Targets API already used by the molecular agent (batched and
    cached). Nothing is invented: a compound that cannot be resolved simply
    keeps its own name as its only alias.

    Returns {compound: [alias dicts]} plus a coverage report.
    """
    config = MolecularAgentConfig()
    client = OpenTargetsClient(config)
    aliases, resolved = {}, 0

    # Any name belonging to ANOTHER study compound is an ambiguous alias and is
    # refused (see intervention_matcher.build_alias_set). ChEMBL synonym lists
    # contain related-but-distinct drugs, e.g. "citalopram" under Escitalopram
    # and "doxycycline" under Tetracycline.
    all_names = {im.normalise(c) for c in compounds}

    try:
        resolutions = {}
        BATCH = 100
        for start in range(0, len(compounds), BATCH):
            chunk = compounds[start:start + BATCH]
            resolutions.update(normalize_drug_batch(chunk, client))

        chembl_ids = [r["chembl_id"] for r in resolutions.values() if r.get("chembl_id")]
        details = {}
        for start in range(0, len(chembl_ids), 50):
            details.update(get_drug_mechanisms(chembl_ids[start:start + 50], client))
    except OpenTargetsUnavailable as exc:
        print(f"  WARNING: synonym retrieval unavailable ({exc}). "
              f"Falling back to compound names only -- matching will be STRICTER, "
              f"never looser, so no false match can be introduced.")
        return ({c: im.build_alias_set(c, ambiguous_names=all_names - {im.normalise(c)})
                 for c in compounds},
                {"resolved": 0, "total": len(compounds), "source": "unavailable"})

    for compound in compounds:
        res = resolutions.get(compound) or {}
        cid = res.get("chembl_id")
        drug = details.get(cid) if cid else None
        syns, trades = [], []
        if drug:
            resolved += 1
            syns = [e["label"] for e in (drug.get("synonyms") or [])
                    if isinstance(e, dict) and e.get("label")]
            trades = [e["label"] for e in (drug.get("tradeNames") or [])
                      if isinstance(e, dict) and e.get("label")]
        aliases[compound] = im.build_alias_set(
            compound, syns, trades,
            ambiguous_names=all_names - {im.normalise(compound)},
        )

    return aliases, {"resolved": resolved, "total": len(compounds),
                     "source": "ChEMBL via OpenTargets",
                     "api_requests": client.stats["network"],
                     "cache_hits": client.stats["cache_hits"]}

def is_actually_pd(study):
    """Client-side safety net: verify Parkinson's actually appears in the
    study's own conditions list, regardless of what the API returned."""
    proto = study.get("protocolSection", {})
    conditions = proto.get("conditionsModule", {}).get("conditions", [])
    return any("parkinson" in c.lower() for c in conditions)

def main(accept_failed_searches=False):
    # Exclusion-filtered candidates (scripts/00_exclusion_filter.py). Reading
    # the unfiltered list here previously sent up to 41 unnecessary query sets
    # to ClinicalTrials.gov and let excluded compounds propagate into stages
    # 04/05/08 via clinical_maturity_precutoff_clean.csv. See TD-010.
    candidates = pd.read_csv("data/pd_candidates_filtered.csv")
    compounds = candidates["compound_name"].dropna().unique().tolist()

    print(f"Building verified alias sets for {len(compounds)} compounds "
          f"(ChEMBL synonyms + trade names via OpenTargets)...")
    alias_map, alias_report = build_alias_map(compounds)
    print(f"  resolved to ChEMBL: {alias_report['resolved']} / {alias_report['total']} "
          f"(source: {alias_report['source']})")
    if "api_requests" in alias_report:
        print(f"  OpenTargets requests: {alias_report['api_requests']}, "
              f"cache hits: {alias_report['cache_hits']}")

    pre_rows, post_rows, audit_rows = [], [], []
    counts = {"condition_rejected": 0, "intervention_rejected": 0,
              "unverifiable": 0, "api_failure_compounds": 0, "accepted": 0}

    consecutive_failures = 0
    for _, row in tqdm(candidates.iterrows(), total=len(candidates)):
        drug = row["compound_name"]
        studies, ok = search_trials(drug)
        time.sleep(0.34)
        consecutive_failures = 0 if ok else consecutive_failures + 1
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            raise SystemExit(f"ClinicalTrials.gov unreachable: {consecutive_failures} consecutive searches failed. "
                             "Aborted before writing any output; the previous files are unchanged.")

        if not ok:
            # NOT "no evidence" -- the search itself failed.
            counts["api_failure_compounds"] += 1
            audit_rows.append({
                "compound_name": drug, "compound_id": row["compound_id"],
                "nct_id": "", "brief_title": "", "conditions": "",
                "interventions": "", "outcome": im.API_FAILURE,
                "match_type": "", "matched_intervention": "", "matched_alias": "",
                "match_source": "", "qualifies": False, "cohort": "",
                "reason": "ClinicalTrials.gov search failed after retries",
            })
            continue

        aliases = alias_map.get(drug) or im.build_alias_set(drug)

        for s_ in studies:
            proto = s_.get("protocolSection", {})
            ident = proto.get("identificationModule", {})
            status_mod = proto.get("statusModule", {})
            design_mod = proto.get("designModule", {})
            cond_mod = proto.get("conditionsModule", {})
            nct_id = ident.get("nctId", "")
            conditions = cond_mod.get("conditions", []) or []

            # --- Gate 1: condition must really be Parkinson's (pre-existing) ---
            if not is_actually_pd(s_):
                counts["condition_rejected"] += 1
                audit_rows.append({
                    "compound_name": drug, "compound_id": row["compound_id"],
                    "nct_id": nct_id,
                    "brief_title": (ident.get("briefTitle") or "")[:160],
                    "conditions": "; ".join(conditions)[:160],
                    "interventions": "", "outcome": "CONDITION_REJECTED",
                    "match_type": "", "matched_intervention": "",
                    "matched_alias": "", "match_source": "", "qualifies": False,
                    "cohort": "",
                    "reason": "trial conditions do not mention Parkinson's",
                })
                continue

            # --- Gate 2 (NEW): intervention must really be this compound ------
            arms = proto.get("armsInterventionsModule")
            interventions = arms.get("interventions") if arms is not None else None
            verdict = im.match_trial(drug, interventions, aliases)

            iv_names = "; ".join(
                (i.get("name") or "") for i in (interventions or [])
            )[:200]

            audit = {
                "compound_name": drug, "compound_id": row["compound_id"],
                "nct_id": nct_id,
                "brief_title": (ident.get("briefTitle") or "")[:160],
                "conditions": "; ".join(conditions)[:160],
                "interventions": iv_names,
                "outcome": verdict["outcome"],
                "match_type": verdict["match_type"] or "",
                "matched_intervention": verdict["matched_intervention"] or "",
                "matched_alias": verdict["matched_alias"] or "",
                "match_source": verdict["match_source"] or "",
                "qualifies": verdict["qualifies"],
                "cohort": "",
                "reason": verdict["reason"] or "",
            }

            if not verdict["qualifies"]:
                if verdict["outcome"] == im.UNVERIFIABLE:
                    counts["unverifiable"] += 1
                else:
                    counts["intervention_rejected"] += 1
                audit_rows.append(audit)
                continue

            # --- Accepted: classify by cutoff (methodology UNCHANGED) ---------
            first_posted = status_mod.get("studyFirstPostDateStruct", {}).get("date", "")
            phase_list = design_mod.get("phases", [])
            phase = phase_list[0] if phase_list else "NA"
            enrollment = design_mod.get("enrollmentInfo", {}).get("count", None)
            overall_status = status_mod.get("overallStatus", "")

            record = {
                "compound_id": row["compound_id"], "compound_name": drug,
                "nct_id": nct_id, "phase": phase, "status": overall_status,
                "enrollment": enrollment, "first_posted": first_posted,
                "match_type": verdict["match_type"],
                "matched_intervention": verdict["matched_intervention"],
                "matched_alias": verdict["matched_alias"],
                "match_source": verdict["match_source"],
            }

            if first_posted and first_posted < CUTOFF_DATE:
                audit["cohort"] = "pre"
                pre_rows.append(record)
                counts["accepted"] += 1
            elif first_posted and first_posted >= CUTOFF_DATE:
                audit["cohort"] = "post"
                post_rows.append(record)
                counts["accepted"] += 1
            else:
                audit["cohort"] = "no_date"
                audit["qualifies"] = False
                audit["reason"] = "accepted on intervention but has no first-posted date"
            audit_rows.append(audit)

    if counts["api_failure_compounds"] and not accept_failed_searches:
        # A failed search would silently drop the compound from the features, the labels and the VPS pool.
        failed = sorted(r["compound_name"] for r in audit_rows if r["outcome"] == im.API_FAILURE)
        raise SystemExit(f"{len(failed)} compound search(es) failed (e.g. {failed[:5]}); nothing written, the "
                         "previous files are unchanged. Re-run when ClinicalTrials.gov is reachable.")
    pd.DataFrame(pre_rows).to_csv("data/clinical_maturity_precutoff.csv", index=False)
    pd.DataFrame(post_rows).to_csv("data/ground_truth_postcutoff.csv", index=False)
    pd.DataFrame(audit_rows).to_csv(AUDIT_FILE, index=False)

    print("\n" + "=" * 62)
    print("STEP 3 COMPLETE  (intervention identity now verified)")
    print("=" * 62)
    print(f"Accepted compound-trial links            : {counts['accepted']}")
    print(f"Rejected - condition not Parkinson's     : {counts['condition_rejected']}")
    print(f"Rejected - intervention is NOT the drug  : {counts['intervention_rejected']}")
    print(f"Unverifiable intervention fields         : {counts['unverifiable']}")
    print(f"Compounds whose SEARCH failed (API)      : {counts['api_failure_compounds']}")
    print(f"ClinicalTrials searches ok/failed/retried: "
          f"{SEARCH_STATS['ok']}/{SEARCH_STATS['failed']}/{SEARCH_STATS['retries']}")
    print(f"\nPre-cutoff trials (feature)   : {len(pre_rows)} rows, "
          f"{len({r['compound_name'] for r in pre_rows})} compounds")
    print(f"Post-cutoff trials (ground truth, NEVER a feature): {len(post_rows)} rows, "
          f"{len({r['compound_name'] for r in post_rows})} compounds")
    print(f"\nFull decision audit: {AUDIT_FILE}")
    if counts["api_failure_compounds"]:
        print("\nWARNING: some compounds could not be searched. They are recorded as "
              "API_FAILURE in the audit and are NOT evidence of absence.")


if __name__ == "__main__":
    import argparse
    # Parse before any work so --help or a stray argument exits first (TD-034; incident E-017).
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0] if __doc__ else None)
    ap.add_argument("--accept-failed-searches", action="store_true",
                    help="publish even though some searches failed (they stay API_FAILURE in the audit and those "
                         "compounds are absent from features and labels); default: write nothing and exit 1")
    _args = ap.parse_args()
    main(accept_failed_searches=_args.accept_failed_searches)