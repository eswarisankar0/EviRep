# Data freshness and provenance audit (2026-10-21)

## Centralised data contract (new)
- **`GET /api/result_set`** (`ui/server.py` `build_result_set`) is the single contract for the approved result set shown everywhere in the UI. It is read from the run manifest, the evaluation report and file fingerprints; nothing is recomputed. It gives:
  - the score file and the producing run (`adopted-20261015T015501Z-06`, ADOPTED, recorded 2026-10-15 01:55 UTC; lineage "published baseline 2026-10-14 07:50:56");
  - the scoring model and rank convention, the primary-score definition and the missing-data policy;
  - the cohort (90 / 14 / 76, label definition) and the cutoff;
  - the evaluation run, report version, seed and draws;
  - independent recomputation: **true**;
  - code fingerprint: **not recorded**;
  - every recorded file with its recorded and current md5: **24 of 24 match**;
  - the unfingerprinted inputs: `eval` reads `data/reproducibility.json`.
- **Where it is shown:** Validation §5 (a summary line plus an expandable contract) and Overview › Technical details.
- **`GET /api/alternatives`** serves unapproved result sets. It reads only their persisted, fingerprinted comparison and **withholds a stale one** (test `test_withheld_when_an_input_changed`).

## Freshness states (meaning verified from code)

| State | Meaning (source) | UI wording |
|---|---|---|
| NOT_RUN / UNTRACKED | no tracked run (`run_stage.py`) | Not yet run / Not tracked |
| RUNNING | `child_pid` live in the manifest | Running (elapsed time, latest log line, no percentage) |
| SUCCESS | exit 0, outputs validated | Run completed |
| PARTIAL | exit 0 with a PARTIAL envelope, or exit 1 for partial-capable stages | Completed with gaps |
| FAILED | non-zero exit or validation problem; outputs restored | Run failed / "Last run failed; previous results retained" |
| STALE | an input fingerprint changed (dependency-propagated) | Inputs changed — rerun needed |
| VERIFIED_WITH_GAPS (overall) | a declared file was not fingerprinted at the last success | Current against recorded inputs, with unverifiable inputs |
| BLOCKED | an upstream stage failed in a sequence | Blocked by a failed prerequisite |
| ADOPTED | outputs existed before tracking; fingerprinted, not re-run | Recorded baseline (before run tracking) |
| contract valid | the agent envelope passes `validate_envelope` | Output checks: passed (shown separately from the run state) |

## Current state (live server, after this session)
- **Overall: VERIFIED_WITH_GAPS.**
- **Only remaining unverifiable input:** `eval` reads `data/reproducibility.json`. A re-run reproduces the approved report byte-identically (previous pass); it awaits owner approval.
- **Fixed this session:** stages 05 and 08 briefly showed "code changed after its last successful run". The cause was this audit's atomic-write edit, and both scripts were restored to their pre-audit bytes. The remaining warning is genuine.
- **Code changes undetectable** for 8 stages recorded before code fingerprints existed (01, 02, 03, 03c, 06, 04b, diag, eval). This is stated in the UI.

## Sources

| Source | Version / snapshot | Retrieval recorded | Cutoff-bounded? |
|---|---|---|---|
| ClinicalTrials.gov | API v2, queried 2026-10-05 | yes (`ctgov_precutoff_trials.json`) | first-posted date bounds trials; phase from 2026 records (65 of 177 updated on or after 2021) |
| PubMed (04p) | E-utilities | yes (04p run record) | 04p bounded query exists; stage 04 sample is not bounded |
| openFDA label | current label | **not recorded** | no |
| DailyMed history (05h) | SPL history | yes | label at the cutoff (31/83), diagnostic only |
| Open Targets | 26.09 | data version recorded; retrieval date **not recorded** | no |
| Hetionet | v1.0 (2017) | release fixed | yes |

## Times shown in the UI
- **Every time is UTC.** The header refresh time was local time and is now UTC (`utcTime`).
- **The UI distinguishes:**
  - source retrieval time (Source data table);
  - artefact generation time (provenance boxes);
  - last successful run (Overview / Run Center);
  - last UI refresh (header).
- No current timestamp is presented as evidence retrieval.

## Integrity re-check (this session)
`records/data_integrity_summary.json`:
- 0 HIGH findings;
- 2 MEDIUM: the two compounds without a network-proximity row, median-imputed and flagged;
- 0 raw-value mismatches;
- pool = filtered ∩ compounds with a pre-cutoff trial;
- protected artefacts 19/19 unchanged.
