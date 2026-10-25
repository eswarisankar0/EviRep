# Changelog (final audit 2026-10-22)

All changes are in `final_audit_20261022.patch`, verified in the isolated work copy. The primary tree and its live server were not modified.

## Code
| File | Change | Issue |
|---|---|---|
| `scripts/intervention_matcher.py` | `CLASS_FOLLOWERS` + `_token_run_names_the_compound`: a token hit followed by a class or entity word is not the compound | E-064 (N-01) |
| `scripts/vps_verify.py` | Applies `data/feature_role_exclusions.csv` like stage 06; compounds absent from the molecular CSV are median-imputed (D-004) | E-065 (N-02, N-03) |
| `scripts/03_clinicaltrials_groundtruth.py` | `highest_phase()` replaces `phase_list[0]` | E-066 (N-04) |
| `scripts/02_network_proximity.py` | `N_RANDOM = 1000` | TD-011 |
| `scripts/filter_by_studytype.py` | `main()` + `__main__` guard; atomic `*_clean.csv` writes (output byte-identical) | TD-012 |
| `scripts/check_studytype.py` | runs the filter with `run_name="__main__"`; `makedirs("data")` | TD-012 / 013 |
| `scripts/00_exclusion_filter.py`, `scripts/01_get_pd_candidates.py` | `makedirs("data")` | TD-013 |
| `scripts/test_openfda.py`, `scripts/check_groundtruth.py` | `main()` + guard (no network or reads on import) | TD-012 |
| `scripts/conflict_context_agent.py`, `scripts/reproducibility_agent.py`, `scripts/completeness_gap_agent.py`, `scripts/literature_credibility_agent.py` | exit 1 only on FAILED (the 10b/c/f/g convention) | E-067 |
| `ui/server.py` | `timeout_s` for 01, 00, 02, 03, 03c, 04, 05, 04b, 06, eval (generous: 03 measured about 25 min, cap 14,400 s) | E-067 |

## Tests
- `tests/test_final_audit_fixes.py` (new, 13 tests): verifier feature exclusions ×3; absent molecular; agent exit codes ×4; timeouts; import safety ×3; highest phase.
- `tests/test_intervention_matcher.py`: +3 class-phrase tests using real registry strings.
- `tests/test_stage03_failure_handling.py`: the filter is invoked as in production (`run_name="__main__"`); the assertions are unchanged.

## Registers and documentation
- `TECHNICAL_DEBT.md`: dated updates on TD-011, 012, 013, 036, 037, 038, 042 and 046.
- `development_log/CHANGES.md`: C-125.
- `development_log/ERRORS_AND_BLOCKERS.md`: E-064 to E-067.

## Not changed (deliberately)
- **Approved data:** `data/vps_scores_v2.csv`, the evaluation report, the cohort and labels, all 19 protected artefacts, and the UI's default result set.
- **Weights:** equal weights retained.
- **Not created:** `data/feature_role_exclusions.csv`. Its creation is the adoption step for P1 (see `candidate_feature_role_exclusions.csv`).
- **Dependencies:** no upgrades (SEC-1/2 recommended after the presentation).
