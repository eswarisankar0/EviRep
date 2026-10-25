# Scientific contract: traceability matrix (2026-10-20)

**How this was built.** Every rule below was reconstructed from code and approved artefacts, not from documentation alone. Each row is enforced by a test that runs in `./venv/bin/python -m unittest discover -s tests`.

`tests/test_ground_truth_contract.py` deliberately re-derives the contract **independently** of the project code: standard-library `csv`/`json` only, plus a frozen fixture of the approved labels. It checks the pipeline against it.

| Rule | Source of truth (code / artefact) | Value verified 2026-10-20 | Test(s) |
|---|---|---|---|
| Candidate pool | stage 00 → `pd_candidates_filtered.csv` (1,483); evaluable pool = filtered ∩ compounds with ≥ 1 accepted pre-cutoff PD trial (`clinical_maturity_precutoff_clean.csv`) | **90 compounds**, one row each | `test_population_size_and_construction`; `test_temporal_and_ranking.test_no_duplicate_compounds` |
| Cutoff semantics | `scripts/03_clinicaltrials_groundtruth.py`: `CUTOFF_DATE = "2021-01-01"`; feature if `first_posted < CUTOFF`, label if `>=` | features ≤ 2020-11-25; labels ≥ 2021-01-13; no NCT in both | `test_cutoff_semantics_on_every_trial`; `test_temporal_and_ranking` (day before, exact cutoff, day after, empty date) |
| Label definition | label = ≥ 1 accepted post-cutoff PD trial not excluded; outcome = continued clinical investigation (D-010), not efficacy | **14 positives / 76 negatives** (prevalence 0.1556) | `test_every_label_follows_the_rule`; `test_labels_equal_the_frozen_approved_set` |
| Trial-role exclusions | `label_role_exclusions.csv` (TD-032 / D-020 policy P1), applied per trial in `06_vps_fusion.apply_label_exclusions` | 3 compounds lose their label (Clozapine, Dexmedetomidine, Remifentanil) | `test_exclusions_refer_to_existing_label_trials`; `test_label_role_exclusions` |
| Ambiguous intervention matching | `intervention_matcher.py`; match audit `clinicaltrials_match_audit.csv` (protected); unresolved roles go to the human review queue | 28 links await adjudication, **untouched** | `test_intervention_matcher`; `test_trial_role`; review queue in UI |
| Post-cutoff outcomes outside the pool | compounds with a label trial but no pre-cutoff trial are not evaluable | 24 compounds (by design) | recomputed in the independent check |
| Feature temporal validity | proximity: Hetionet 2017; clinical: pre-cutoff trials (phase from the current record); literature, safety, molecular: **current snapshots** | not leakage-free (TD-033); dated sensitivities: literature −0.019, safety −0.003, molecular 0.775 → 0.704 | `test_vps_correctness.test_feature_stages_never_read_post_cutoff_labels`; sensitivity scripts |
| No label leakage into scores | stage 06 attaches labels after features; VPS = mean of `r_*` columns only | holds for all 90 rows | `test_label_never_enters_the_score`; `test_ground_truth_only_used_for_labels_and_after_features` |
| Missing / imputed / zero | unmeasured safety (no label) and molecular (no target) get neutral rank 0.5 (D-004); missing proximity is median-imputed and flagged; clinical and literature are always present | 21 compounds with a missing dimension, all at 0.5 | `test_missing_dimensions_are_neutral_not_negative`; `test_safety_missingness` |
| Approved formula | `VPS_equal_5d = mean(r_proximity, r_clinical, r_literature, r_safety, r_molecular)`, legacy rank/n with average ties (D-002, D-024) | reproduced exactly (`vps_verify` max abs diff 2.2e-16) | `test_vps_correctness`; `vps_verify.py` |
| Ties | average rank (`method="average"`) | no ties in the final VPS (90 distinct values) | `test_ties_average_and_nan_unranked`; contract test |
| Metrics | AUROC (Mann-Whitney), AUPRC (average precision), **ordinary (not stratified)** percentile bootstrap, 2,000 draws, seed 42, single-class draws skipped and counted (0 occurred); no calibration. *Corrected 2026-10-20: this row said "stratified"; only `vps_validation_experiments.py` (seed 20261019) stratifies.* | **AUROC 0.775376 [0.656, 0.881]; AUPRC 0.424315**; 4D 0.700188 | `test_evaluation_report_matches_the_data`; `test_auroc_reference_values` |
| Report ↔ data consistency | `vps_evaluation_report.json` `inputs` md5s | all 7 match the current files | `test_evaluation_report_matches_the_data` |
| Human adjudication | only humans write `feature_trial_roles_td038.csv` and `label_role_exclusions.csv`; the review queue never decides | protected sha256 unchanged | protected-hash check |
| Protected artefacts | 19 files, sha256 list in the recovery snapshot | 19/19 OK | integrity gate |

**Conflicts and ambiguities found:** this matrix originally said "none". The 2026-10-20 scientific release audit found 25 documentation/code contradictions (none changing an approved number); see `docs/autonomous_runs/scientific_release_audit/FINDINGS.md`.

**Open scientific decisions (owner):**
- the temporal validity of the molecular dimension (TD-042 / TD-033);
- the label re-freeze policy.
