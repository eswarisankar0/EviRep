# Visualization → data map

Every chart is drawn from a persisted artefact or the run tracker. Nothing is invented, smoothed or extrapolated.

Each chart has a data-table alternative under "Data table".

| View | Chart | API field | Source of truth | Verified by |
|---|---|---|---|---|
| Dashboard | Pipeline dependency graph | `/api/live` `stages[].depth`, `upstream`, `status` | `ui/server.py` STAGES registry + `data/run_manifest.json` via `scripts/run_stage.py` | drive15: one node per stage, one arrow per dependency |
| Dashboard | Stage-state bars | `/api/live` stage statuses | run tracker | drive15 hero/tiles; drive11 |
| Dashboard | Recent runs timeline | `/api/live` `history` (start/finish) | `run_manifest.json` history | drive15 renders; data table |
| Dashboard | AUROC/AUPRC with 95% CI | `science.primary_metric` | `data/vps_evaluation_report.json` (copied, not recomputed) | drive15 "dashboard AUROC equals the approved report"; `test_science_counts_match_the_artefacts` |
| Dashboard | Source data table | `sources[]` | `literature_provenance_run.json` (PubMed); ClinicalTrials.gov snapshot date and cutoff 2020-12-31 (the code's exclusive bound 2021-01-01); Open Targets data version 26.09; Hetionet v1.0 (2017). openFDA, Open Targets and Hetionet show **retrieval: not recorded**. | `test_sources_never_invent_a_retrieval_time` |
| Live Pipeline | Dependency graph, run history | `/api/status`, `/api/live` | run tracker | drive9, drive11 |
| Candidates | Top-25 ranked bars | `/api/ranking` rows `VPS_equal_5d` | `data/vps_scores_v2.csv` (approved) | drive15 "first bar is the rank-1 compound with its persisted score"; click and Enter open the candidate |
| Candidates | Dimension bars (selected) | ranking row `r_*`, `dimensions_missing`, `dimensions_imputed` | `vps_scores_v2.csv`; imputation from raw `data/network_proximity.csv` (missing → median) | `test_ranking_marks_imputed_values` (Deferiprone, Trimethobenzamide) |
| Compare | Grouped dimension bars | same as above, for the selection | `vps_scores_v2.csv` | drive15 compare |
| Validation | ROC and PR curves | `/api/validation_charts` `roc`, `pr` | computed from `vps_scores_v2.csv` (`VPS_equal_5d`, `label`), ties handled; **withheld** unless AUROC and AP equal the report within 1e-9 | `test_curves_reproduce_the_approved_report`; `test_independent_recomputation_of_the_roc_area` (Mann-Whitney); `test_mismatch_withholds_the_curves`; drive15 vertex count |
| Validation | Model comparison | `models[]` | report `primary[]` | `test_model_comparison_and_missingness_are_copied_from_the_report` |
| Validation | Paired 5D−4D difference | `paired_5d_vs_4d` | report | same test; drive15 zero reference |
| Validation | Ablation / baselines | `ablation`, `baselines` | report; grid-search row flagged in-sample | rendering hatched; `grid_search_note` |
| Validation | Missing / imputed by dimension | `missing_by_dimension`, `imputed_by_dimension` | report `missing_data.not_measured_by_dimension`; proximity imputation from raw file | drive15 (7 safety, 16 molecular, 2 proximity imputed) |
| Mechanism | Drug → target → disease chain | `/api/mechanism` record | `data/molecular_pathway_evidence.jsonl` (saved record) | drive15: one node per target (max 10) |
| Review | Counts by reason, search, filter | `/api/review` | `data/clinical_review_worklist.csv` | drive15 counts equal the artefact; `test_science_counts_match_the_artefacts` |

**New scientific numbers.** None. The only computed values are the ROC/PR curve vertices. They reproduce the already-approved AUROC (0.775376) and AUPRC (0.424315) exactly, and are refused otherwise.
