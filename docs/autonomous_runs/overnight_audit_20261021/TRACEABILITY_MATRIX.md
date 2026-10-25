# Traceability matrix (2026-10-21)

**Precedence:** protocol → owner decisions → schemas and manifests → approved outputs → code → UI.

| # | Requirement or claim | Canonical source | Implementation | Data / schema | Verification | Observed | Status | Correction / impact |
|---|---|---|---|---|---|---|---|---|
| 1 | VPS = mean of 5 percentile ranks, equal weights | `docs/VPS_FEATURE_CONTRACT.md:10`; D-002 | `06_vps_fusion.py` `build_standardized_scores`, `VPS_equal_5d` | `data/vps_scores_v2.csv` | `tests/test_vps_independent_agreement.py` (production vs independent, 1e-12) | max diff 2.2e-16 | verified | — |
| 2 | Rank orientation: proximity and safety inverted | contract; D-003 | `06:274-280` | raw columns | same tests + `independent_math.py` | ranks diff 0 | verified | — |
| 3 | Unmeasured safety/molecular → neutral 0.5; missing proximity → median, flagged | D-004; TD-041 | `06:198-302` | `dimensions_missing` / `dimensions_imputed` | `test_missing_target_and_label_get_neutral_half_not_extremes`; data integrity | 7 + 16 neutral, 2 imputed | verified | approved file lacks `dimensions_imputed` (B-003), so the UI derives it from raw data |
| 4 | Cohort = filtered ∩ compounds with a pre-cutoff accepted trial; 90 | D-001; contract test | `06:172-174` | pool CSVs | `data_integrity.py` | 90, equality true | verified within the stated rules | incomplete because of S-01 (Dopamine) → blocker 2 |
| 5 | Label = qualifying PD trial first posted 2021-01-01 to 2026-10-05, minus P1 exclusions | D-010, TD-032 | `03:300-304`, `filter_by_studytype.py`, `06:338-342` | `ground_truth_postcutoff_clean.csv`, `label_role_exclusions.csv` | live paginated re-ascertainment (previous pass); re-derivation | 14/76 reproduced | verified; 1 unresolved, 1 disputed | blockers 4 and 5 |
| 6 | AUROC/AUPRC/CI from continuous scores; ordinary bootstrap, seed 42 | `vps_evaluation_report.py`; D-018 | `boot_metric`, `paired_bootstrap` | `vps_evaluation_report.json` | `independent_math.py`; `test_scientific_audit` | identical | verified | traceability doc previously said "stratified"; corrected in the previous pass |
| 7 | Paired 5D−4D not significant | report | `bootstrap_auroc_ci.py` | same | independent paired bootstrap | +0.075 [−0.025, 0.176] | verified | UI says the "interval includes zero" |
| 8 | Learned weights not adopted (held-out worse than equal) | D-002; `VPS_WEIGHTING_DECISION` | `vps_validation_experiments.py` (nested) | `data/_runs/vps_weighting_20261019/*` | re-run byte-identical (previous pass); rows read this session | all learned methods below equal | verified | — |
| 9 | TD-042 correction status | `TECHNICAL_DEBT.md:722-740` | `molecular_agent.py` flag (default off) | `data/_candidates/td042_v1/` | `verification.json` + `compare_result_sets.py` + independent `td042_comparison.py` | 0.699 vs 0.775; difference CI excludes 0 | verified; **NOT APPROVED** | shown as an alternative in Validation §7 → blocker 1 |
| 10 | Diagnostic agents do not affect VPS | contract; AGENT_VPS_ROLE | stage 06 inputs | manifest | data-flow trace; sentinel tests | stage 06 reads no agent output | verified | — |
| 11 | No stale output masquerades as fresh | `RUNS_AND_LIVE_UI.md` | `run_stage.py` restore, `agent_contract.input_changed` | manifest, envelopes | `test_agent_failure_modes` (7, real runner) | holds | verified | — |
| 12 | Every consumed input fingerprinted | runs doc | `run_stage.status` | manifest | `/api/result_set` | `eval` input `reproducibility.json` not fingerprinted | **failed (open)** | blocker 7 |
| 13 | UI never recomputes VPS | UI design | `ui/app.js` reads `/api/ranking` | `vps_scores_v2.csv` | code inspection; drive15/16 (score shown = file) | holds | verified | — |
| 14 | Server loopback-only; protected stages not launchable; no secrets | `ui/server.py` docstring; `live_runs.py` | Host/Origin/nonce checks, PROTECTED_ARTEFACTS | — | active probes (this session); credential scan | all refused; no secrets | verified | — |
| 15 | Every visible control works | brief §8.8 | `ui/app.js` | — | drive17 (event listeners on 2,118 controls; 1,378 internal links) | 0 dead, 0 failing | verified | — |
| 16 | Evidence links open the intended record | brief §8.4 | `extLink` patterns | evidence index | 15 live identifier checks | 15/15 resolve and contain the identifier | verified (sample) | — |
| 17 | 28 trial links await review; none auto-resolved | D-020 | review worklist | `clinical_review_worklist.csv` | count and key join | 28 unresolved, all feature links | verified | blocker 6 |
| 18 | Times displayed consistently | brief §10 | `ui/app.js` | — | inspection | header used local time | fixed (UTC) | — |
| 19 | "VPS" means "Vulnerability/Priority Score" (brief) | `README.md:4` says "Validated Plausibility Score" | — | — | text search | the brief's expansion is not in the repository | ambiguous → repository wording kept | — |
