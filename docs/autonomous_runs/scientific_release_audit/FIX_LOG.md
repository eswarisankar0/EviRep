# Fix log

Every change is minimal and covered by a regression test. **No approved output, label, cohort member, score or evaluation number was changed.**

| # | Finding | Files | Change | Test | Verified |
|---|---|---|---|---|---|
| 1 | S-11 | `scripts/vps_validation_experiments.py` | `auroc_cols`: explicit NaN for single-class samples; input validation. New `best_index` and `UndefinedSelection`: skip undefined folds, raise if none is defined; single-class outer test folds raise | `test_scientific_audit::TestAurocCols` (4), `TestSelectionNeverFallsBackSilently` (3) | weighting matrix re-run byte-identical to the persisted outputs |
| 2 | S-11 | `tests/test_vps_validation_experiments.py` | the vacuous fixture (all positives in one fold) replaced; asserts both classes in every inner fold and that label flips give 1 − AUROC | same test | passes with RuntimeWarning promoted to error |
| 3 | S-01 | `scripts/03_clinicaltrials_groundtruth.py` | `search_trials` follows `nextPageToken` (100 per page, at most 50 pages); a failed page fails the search | `TestStage03Pagination` (2) | live paginated re-ascertainment (audit tool) |
| 4 | S-12 | `ui/server.py` | stage-06 limitation text: 17 → 14 positives, CI width updated | `TestUiConsistency` | — |
| 5 | A-1 | `scripts/run_stage.py` | `PARTIAL_ON_EXIT1` += 04p, 05h, 10a-all | `TestRunnerPartialPolicy` | — |
| 6 | A-2 | `scripts/evidence_independence_agent.py` | header-only literature CSV → `INPUT_EMPTY` warning → PARTIAL | `test_agent_failure_modes::TestAgentDefectsFixed` | real agent, isolated copy |
| 7 | A-3 | `scripts/conflict_context_agent.py` | malformed molecular lines counted → `MALFORMED_LINE` | same | same |
| 8 | A-4 | `scripts/completeness_gap_agent.py`, `ui/server.py` (10h inputs and dependencies) | a FAILED upstream envelope → its domains NOT_COMPUTED + `UPSTREAM_FAILED`; 10b listed for staleness/failure | same | same |
| 9 | A-5 | `ui/server.py` | stage 08 `timeout_s` = 14400 | `test_stage08_has_a_timeout` | — |
| 10 | A-6 | `scripts/molecular_run_record.py`, `safety_evidence_agent.py`, `05_safety_signal.py`, `literature_credibility_agent.py`, `08_molecular_pathway.py` | atomic `.tmp` + `os.replace` writes | existing agent tests | outputs re-generated, content identical. **Update 2026-10-21:** the 05 and 08 edits were reverted and deferred (they made two protected stages show "code changed"); see `../overnight_audit_20261021/CHANGELOG.md` and E-059 |
| 11 | A-7 | `scripts/agent_contract.py`, `ui/server.py` | absent inputs recorded as `null`; one `input_changed` rule used by agents, the report check and the poll cache | `TestEnvelopeProvenance` (2); `test_safety_evidence_agent::test_stale_inputs` updated | — |
| 12 | S-09, S-18 | `docs/autonomous_runs/SCIENTIFIC_CONTRACT_TRACEABILITY.md`, `README.md`, `docs/MOLECULAR_AGENT.md`, `docs/VPS_FEATURE_CONTRACT.md`, `scripts/vps_verify.py` (docstring), `development_log/ERRORS_AND_BLOCKERS.md` (B-002b) | corrected statements | — | — |
| 13 | S-24 | `data/cache/molecular` (9 audit-created files) | moved to `records/alias_cache_written_by_audit/`; audit tools use a temporary cache copy | assertion in `alias_search_negatives.py` | cache = 311 files = snapshot |

## Re-generated outputs (tracked runs, not approved artefacts)
- **Stages re-run:** `run_stage.py --sequence 10a 10a-all 10b 10c 10d 10e 10f 10g review 10h` after the agent code changes. Stages with unchanged code and inputs were skipped as fresh.
- **Isolated rehearsal first:** the outputs' scientific content was identical to the previous outputs. The only differences were the new `null` entries for absent inputs and 10b appearing in 10h's agent list.
- **Protected artefacts:** 19/19 sha256 unchanged before and after.

## Not changed (owner decisions)
- Stage 03 was not re-run (S-01), so the cohort and labels are not updated.
- The study-type rule (Lithium, S-02), the Galantamine and Rifaximin roles (S-04), the molecular module selection (S-05) and the rank convention (S-08) are unchanged.
- `eval` was not re-run, although it reproduces byte-identically (S-13).
- `td042_v1` was not adopted (S-23).
