# Remaining blockers (2026-10-21)

| # | Severity | Blocker | Evidence | Reproduce | Owner decision | Safest next action |
|---|---|---|---|---|---|---|
| 1 | HIGH | **TD-042, molecular double count.** The approved 5D AUROC 0.775 depends on crediting a drug's own target twice; the corrected rule gives 0.699 (= 4D) | `SCIENTIFIC_AND_VPS_AUDIT.md`; `data/_candidates/td042_v1/comparison.json`; approved − corrected +0.076 [0.014, 0.158] | `./venv/bin/python scripts/compare_result_sets.py --candidate data/_candidates/td042_v1/root/data/vps_scores_v2.csv --out /tmp/c.json --name td042_v1 --rule x` | adopt the corrected rule or keep the original with the caveat | decide; if adopted, run `data/_candidates/td042_v1/publish_td042.sh` (rehearsed) |
| 2 | HIGH | **Cohort incomplete.** Stage 03 truncated searches at 20 results; Dopamine is missing (code fixed, cohort not rebuilt) | `../scientific_release_audit/FINDINGS.md` S-01 | `docs/autonomous_runs/scientific_release_audit/scripts/reascertain_ctgov.py` (online, read-only) | approve a stage-03 rebuild (about 1,500 online searches; rewrites protected files) | run 03 → 03c → 06 → eval in an isolated copy, compare, then decide |
| 3 | HIGH | **Temporal validity (TD-033).** Literature, safety and molecular evidence are current snapshots; the time-bounded estimate is about 0.69 | `../scientific_release_audit/LEAKAGE_AND_VALIDATION_AUDIT.md` | sensitivity outputs cited there | adopt time-bounded features or keep the caveat | keep the caveat (shown in the UI) until decided |
| 4 | MEDIUM | **Lithium label** depends on the registry intervention type (DIETARY_SUPPLEMENT) | S-02 / B-004 | `records/` and the previous pass's `ground_truth_row_audit.csv` | content-based or type-based rule | decide; the sensitivity result is 0.757 |
| 5 | MEDIUM | **Galantamine** (D-011) unresolved; Rifaximin's regimen role not adjudicated | S-04 | CASE_STUDIES §9 | adjudicate | human review |
| 6 | MEDIUM | **28 feature-trial roles** await human review (D-020) | `data/clinical_review_worklist.csv` | Evidence › Trial-role review | review in `data/feature_trial_roles_td038.csv` (protected; outside the app) | see the design option below |
| 7 | MEDIUM | **Evaluation input unfingerprinted** (`data/reproducibility.json`) | `/api/result_set` `unfingerprinted` | Run Center | approve `./venv/bin/python scripts/run_stage.py eval` (reproduces byte-identically) | approve |
| 8 | MEDIUM | **Molecular module selection** uses the overall Open Targets score | S-05 | `molecular_agent.py:728-760` | change the selection rule | decide together with TD-042 |
| 9 | LOW | Atomic writes for stages 05 and 08 deferred | `records/deferred_atomic_write_05_08.patch` | — | apply when 05/08 are next re-run with approval | apply the patch at that time |
| 10 | LOW | Core stages 00–06 have no runner timeout | `ui/server.py` STAGES | — | choose durations | add timeouts with the next owner-approved run |
| 11 | LOW | Semantic Scholar cannot be verified (HTTP 429, no key) | previous online check | — | provide a key via the environment (never the repository) | — |
| 12 | LOW | Rank convention (legacy vs midrank) and an indeterminate-label policy | D-024, TD-040, S-21 | — | decide | — |

## Requirements the brief asked for that were not implemented, and why

**In-app review decisions** (brief §9: "a review action persists its result").
- **Why not:** the documented workflow (D-020) has a named human record decisions in the protected `data/feature_trial_roles_td038.csv`. The app has no authentication, so a reviewer's identity cannot be attributed. A previous instruction also forbids adding edit features over scientific evidence.
- **Current state:** the Review page is read-only and says so.
- **Design option for the owner:** an append-only `data/review_submissions.jsonl`, with a required reviewer name, decision and rationale, marked "submitted, not applied". It would never change the score until the owner applies it to the protected file.
- **Not built without approval.**

**Documents named in the brief that do not exist in the repository:** `SECUREDOC_CURRENT_STATE_REPORT.md` and `TOP_20_ACTIONS_TO_REACH_ENTERPRISE_GRADE.md` (searched the whole tree).

## Production readiness
**Not production-ready.**
- Blockers 1–3 are open scientific decisions.
- The server is a single-user, loopback-only research tool with no authentication, by design.
- Any network deployment needs an authentication and authorisation plan first.
