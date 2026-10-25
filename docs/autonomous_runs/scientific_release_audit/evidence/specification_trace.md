# EviRep VPS: scientific specification as found in code, docs and data (read-only audit, 2026-10-20)

Scope: `/Users/thrisha/Drup_Rep_PF/EviRep`. No repository files were changed. Data facts come from read-only
pandas/csv reads of `data/` (no pipeline stage was run, no network). The citation `file:N` means a line in the
working tree as of this audit. "VVE" means `scripts/vps_validation_experiments.py`.

---

## 1. Specification table

| Item | What the code actually does (with citations) | Docs and notes |
|---|---|---|
| **Scientific question** | Among compounds with an accepted pre-cutoff PD trial, does an equal-weight evidence score rank the compounds that later got a qualifying PD trial above those that did not? Labels are attached after the features (`06_vps_fusion.py:568-572`). | D-001 (`DECISIONS.md:25-27`, alternative (b)); D-013 (`DECISIONS.md:301`): "continued clinical investigation", **not efficacy**, not first-time repurposing (that is RQ-2). TD-035 (`TECHNICAL_DEBT.md:625-639`). |
| **Unit of analysis** | A compound, identified by `compound_name`. There is one row per compound, and duplicate rows raise an error (`06:157-163, 166-171`). Bootstrap and CV resample compounds (`VVE:381` "resampling unit = compound"). | Compounds are not independent: 17 pre-cutoff trials are shared across 31 pool compounds (TD-038; `VPS_EVALUATION.md:40-41`). Grouped folds are used only in the weighting experiment (`VVE:219-235`). |
| **Candidate universe** | Hetionet v1.0 Compounds with **no** CtD/CpD edge to `Disease::DOID:14330` (`01_get_pd_candidates.py:11,37-57`): 1552 → 1524 (`pd_candidates.csv`). | `existing_edge_type=="predicted_only"` (`01:56`). |
| **Exclusion list (vitamins, electrolytes, metabolites)** | A hard-coded `EXCLUSION_LIST` in `scripts/00_exclusion_filter.py:11-26`: 17 vitamins, 17 amino acids/SAMe, and 13 cofactors/electrolytes/metabolites including "Caffeine" and "Nicotine" (marked "borderline"). Matching is an exact `compound_name` match (`00:31`). 1524 → 1483 (41 removed; e2e log in `data/_runs/e2e_final_20261020/e2e_offline_full.json`). The list's only source is this file. The rationale is in its docstring (`00:1-8`); no external reference is cited. | The comment "borderline -- see note below" (`00:25`) refers to a note that does not exist in the file. TD-010 (`TECHNICAL_DEBT.md:108`). |
| **Evaluable pool (inclusion)** | `merge_dimensions` keys the pool on compounds that appear in `clinical_maturity_precutoff_clean.csv` **and** in `pd_candidates_filtered.csv` (`06:172-174`). An optional `feature_role_exclusions.csv` can remove links first (`06:541-543`); the file does not exist (D-020 `DECISIONS.md:527-528`). Result: **90 compounds**. | Contract test `tests/test_ground_truth_contract.py:53-58`. A compound whose first PD trial is post-cutoff is never evaluable (TD-027 `TECHNICAL_DEBT.md:429-436`): 24 of the 41 ground-truth compounds lie outside the pool (verified). |
| **Trial acceptance (features and labels)** | Stage 03: `query.intr=<name>`, `query.cond="Parkinson Disease"`, **`pageSize: 20` with no pagination** (`03:75-79`). Gate 1: the trial's conditions contain "parkinson" (`03:172-177, 235`). Gate 2: `intervention_matcher.match_trial` accepts a trial only on MATCHED (`03:253, 275`). The matcher uses structured name and otherName fields plus ChEMBL synonyms, with whole-token matching (`intervention_matcher.py:20-55`). The 03c filter then keeps a trial only if it is INTERVENTIONAL **and** at least one of its interventions is DRUG or BIOLOGICAL (`filter_by_studytype.py:13-17`). | Not documented anywhere: 12 compounds returned exactly 20 studies and may be truncated (Benzocaine, Carboplatin, Cisplatin, Docetaxel, Dopamine, Fluorouracil, **Ioflupane I 123 (in the pool, label 0)**, Methyldopa, Norepinephrine, Paclitaxel, Pemetrexed, Phenol; computed from `clinicaltrials_match_audit.csv`). |
| **Observation / index date** | A single calendar cutoff for every compound, `CUTOFF_DATE = "2021-01-01"` (`03:53`). There is no per-compound index date. | Stage 03's README and contract use "2021-01-01, exclusive" (`README.md:7`). Stages 04p and 05h, the weighting doc and the UI use "2020-12-31, inclusive" (`04p:44`, `05h:37`, `VPS_WEIGHTING_DECISION:10`, `ui/server.py:1976`). The two define the same day boundary but are named differently (see §3). |
| **Predictor windows** | **Proximity:** Hetionet v1.0 (2017) PPI and CbG edges (`02:12-22`). **Clinical:** every accepted trial with `first_posted < 2021-01-01` (`03:300`). The data run from 2000-02-25 to 2020-11-25 (verified). Phase, interventions and conditions come from the **current** registry record (queried 2026-10-05). **Literature:** PubMed `"<name>"[Title/Abstract] AND "Parkinson Disease"[Title/Abstract]` with `retmax 30`, PubMed default (recency) order, and **no date bound** (`04:68-69`; a `max_date` exists but is not wired in, `04:62-66`). **Safety:** the current openFDA label, `limit=1` (`05:25`). **Molecular:** Open Targets 26.09 plus current ChEMBL mechanisms (`MOLECULAR_AGENT.md:272-276`). | Only proximity and clinical are cutoff-bounded (TD-033; `VPS_FEATURE_CONTRACT.md:31`; `VPS_WEIGHTING_DECISION:94`). |
| **Outcome and window** | Label = 1 iff the compound has ≥1 accepted trial in `ground_truth_postcutoff_clean.csv` (that is, `first_posted >= "2021-01-01"`, `03:304`) **after** dropping the trials listed in `label_role_exclusions.csv` (`06:569-572, 316-342`). The window end is the stage-03 query date. | D-010 (`DECISIONS.md:224-232`) freezes the window to the 2026-10-05 snapshot. The latest observed `first_posted` is 2026-09-08. The md5 `c83e30bb…` is pinned by the manifest and a test. |
| **Positive / negative / indeterminate** | Binary only: `df["label"] = isin(positives).astype(int)` (`06:338-342`). **Negative = every other pool compound**, including those that lost their label trial to P1, those whose post-cutoff trials were UNVERIFIABLE or NO_MATCH, and those affected by the 20-result cap. **No "indeterminate" class exists in code** (grep finds none in 06, VVE or `vps_*`). | Galantamine is "UNRESOLVED" but kept at label 1 by owner decision (D-005 `DECISIONS.md:148-150`; D-011 `:256`). "Excluded" and "→0" variants exist only as sensitivity rows (D-011 `:260-265`; CASE_STUDIES §9.1). Counts: **14 positive / 76 negative** (`vps_evaluation_report.json` cohort). |
| **Dimension 1: proximity** | Raw `proximity_z = (d_real − mean(d_rand))/sd(d_rand)`. `d_real` is the mean over targets of the BFS distance to the nearest PD gene (`02:263-291`). There are 100 degree-matched random sets (`02:45, 542-569`), seed 42 (`02:48, 391-396`). If sd = 0, z = 0.0, which counts as measured (`02:601-610`). **Direction:** lower is better. `percentile_rank(df["proximity_z"], invert=True)` (`06:274`) calls `series.rank(pct=True, method="average")` (pandas default `ascending=True`) and returns `1 - ranks` (`06:263-264`). **Missing:** median-imputed **before** ranking (`06:218-220`) and flagged in `dimensions_imputed` (`06:212-217`). In the data this is 2 compounds (Deferiprone and Trimethobenzamide, both z = −0.837629). | TD-041 (`TECHNICAL_DEBT.md:717-720`) leaves median versus neutral open. Of 1483 compounds, 161 have no CbG target, 6 have no distance and 2 have fewer than 10 random samples (e2e log). |
| **Dimension 2: clinical** | Raw `max_phase_rank` = the maximum over accepted pre-cutoff trials of `PHASE_RANK` {NA 0, EARLY_PHASE1 1, PHASE1 2, PHASE2 3, PHASE3 4, PHASE4 5}. Unknown phases get 0 (`06:110-118`). `phase = phases[0]` (`03:285-286`), so a "PHASE1/PHASE2" trial scores as PHASE1. `n_trials` is computed but **not scored** (`06:275`). **Direction:** higher is better, `invert=False` (`06:275`), average ties (6 levels, so heavy ties). **Missing:** the median-imputation code exists (`06:218-220`) but never fires, because the pool is keyed on this table. | README calls the clinical dimension "max trial phase, trial count" (`README.md:15`), but trial count is not used (see C-7). |
| **Dimension 3: literature** | Raw `effective_independent_count` = the number of connected components of a graph over ≤30 PMIDs. Edges are a shared author, or failing that a Semantic Scholar citation (`04:181-221, 273`). 0 papers gives 0, which counts as measured. **Direction:** higher is better (`06:276`). **Missing:** median-imputed (`06:218-220`); no pool compound is missing. | `literature_independence.csv` has 141 rows (stale rows outside the pool, ignored by the left merge). |
| **Dimension 4: safety** | Raw risk = `serious_term_count + 5·boxed_warning` (`06:278-279`). Terms are 8 substrings counted in `boxed_warning`, `warnings` and `warnings_and_cautions` (`05:20-22, 40-43`). **Direction:** lower is better, `invert=True` (`06:280`). **Missing:** if `has_label != True`, the value is set to NaN (`06:87-107`), left unranked, and given `NEUTRAL_RANK = 0.5` (`06:254, 302`). 7 compounds, all negatives. | D-003 (field fix) and D-004 (neutral rule) (`DECISIONS.md:58-139`). |
| **Dimension 5: molecular** | Raw `molecular_plausibility_score = 0.6·direct + 0.4·pathway` (`molecular_agent.py:194-195, 993-1003`). `direct` is the maximum, over the drug's targets, of the Open Targets PD association restricted to the allowed datatypes (`:155-162`). `pathway` = (# distinct target pathways containing ≥1 PD-module gene) / (# distinct target pathways) (`:995-998`). The module is the top 300 genes with a score ≥ 0.10 on the module datatypes (`:185-204`). **The TD-042 flag `pathway_excludes_drug_targets` defaults to False** (`:210`, used at `:875-876`). **Direction:** higher is better (`06:292`). **Missing:** if `n_targets == 0`, the value is set to NaN and given neutral 0.5 (`06:286-291, 302`); 16 compounds, 2 of them positive. A compound absent from the CSV is median-imputed (`06:224-246`); there are 0 such compounds. | TD-042 is HIGH and OPEN (`TECHNICAL_DEBT.md:722-729`). |
| **Fusion** | `compute_weighted_vps` = Σ w·r_d (`06:368-392`). `VPS_equal` uses 0.25 × 4 dimensions (`06:577`). `VPS_equal_5d` uses 0.2 × 5 (`06:598-599`). The rank convention is `"legacy"` (`06:29`); `"midrank"` is selectable with `--rank-convention` (`06:709-712`). | The primary score is `VPS_equal_5d` (contract test `:11`; `VPS_WEIGHTING_DECISION:15-17`). D-002 makes **both** 4d and 5d primary (`DECISIONS.md:45-47`); see C-11. |
| **AUROC** | Stage 06 uses `sklearn.roc_auc_score`, rounded to 3 dp, and returns NaN on ValueError (`06:354-361`). The tests use a hand Mann-Whitney with ties = ½ (`test_ground_truth_contract.py:38-39`). VVE uses `auroc_cols` (§7). The approved value is **0.775376** (5D) and 0.700188 (4D) (`test_ground_truth_contract.py:113-114`). | |
| **AUPRC / average precision** | The report uses `sklearn.average_precision_score`, the step-wise AP that groups ties by threshold (`vps_evaluation_report.py:30, 123`). VVE uses its own `auprc`: Σ precision@i over positives / n_pos, with a **stable mergesort order, so ties are broken by row order** (index = alphabetical compound name) (`VVE:119-124`). The two agree only without ties. The contract test asserts that `VPS_equal_5d` has 90 distinct values (`test_ground_truth_contract.py:93`). Approved AUPRC = 0.424315. | Tied scores (single dimensions, molecular-only with 16×0.5, clinical) make VVE's AUPRC depend on row order. |
| **Precision@k** | Stage 06 uses `sort_values(score, ascending=False).head(k)`, which has an arbitrary order at a tied boundary (`06:349-352`). VVE `p_at` averages over tie orders (`VVE:127-132`). | The P@10 values in `VPS_EVALUATION.md:109-117` come from 06; the TD-042 P@10 values come from VVE. |
| **Bootstrap A: `bootstrap_auroc_ci.paired_bootstrap`** | **Not stratified.** `rng.integers(0,n,n)` with `default_rng(seed=42)` and n = 2000. Single-class draws are **skipped and counted** (`n_skipped`). The interval is a percentile interval from `np.quantile(linear)`. The difference CI is **paired** (same indices for a and b) (`bootstrap_auroc_ci.py:33-70`). | Used for the persisted `bootstrap_ci_equal5d_vs_4d.csv` and for `paired_5d_vs_4d` in the report (`vps_evaluation_report.py:131-140`): +0.0752 [−0.0250, +0.1761]. |
| **Bootstrap B: `vps_evaluation_report.boot_metric`** | **Not stratified.** A fresh `default_rng(42)` for each call, `rng.integers`, n = 2000, single-class draws skipped and counted, `np.percentile` 2.5/97.5 (`vps_evaluation_report.py:55-66`). | Gives the approved CIs: AUROC 5D [0.656, 0.881], 4D [0.567, 0.834]. |
| **Bootstrap C: VVE `bootstrap`** | **Stratified.** Positives and negatives are resampled separately (`VVE:140-150`), with seed 20261019 (`VVE:36`) and one `rng` shared sequentially across all experiments. This is paired across scores and cannot produce a single-class draw. CI = `np.percentile` 2.5/97.5 (`VVE:153-154`). Paired difference = the percentile of `boot[x]-boot[z]` (`VPS_VALIDATION:440-443`). | 5D [0.6513, 0.8806] differs from Bootstrap B's [0.656, 0.881]: same point estimate, different CI procedure. |
| **Grid search / nested CV (stage 06, persisted)** | `cv_grid_search_weights`: `StratifiedKFold(5, shuffle, random_state=42)`, **one split** (`06:447`). The grid has all weights on a `step` lattice that sum to 1 (`06:399-406`): step 0.25 for 4d and 5d, **0.1 for 3d** (`06:581-603`). In each fold, the weights maximising training-fold AUROC are chosen; the first maximum wins because the comparison is strict `>` (`06:409-420`). Those weights are scored on the test fold. The reported value is the **mean of fold AUROCs** (`06:451-462`). Final weights are chosen on all labels and are in-sample (`06:465`). If every fold is single-class the 5d search returns None, and the code falls back to equal weights (`06:604-607`). Percentile ranks and imputation are computed once on all 90 compounds (transductive; TD-036). | Persisted held-out values: 4d 0.607, 3d 0.584, 5d 0.639 (`vps_variant_results.csv`). |
| **Repeated nested CV (report)** | The same `_best_weights_on` and grid as stage 06. `StratifiedKFold(5, seeds 0..19)`; per repeat, the mean of 5 fold AUROCs. The output is the mean and the 2.5/97.5 percentiles over the 20 repeat means (`vps_evaluation_report.py:69-82`). Results: 4d 0.574, 3d 0.571, 5d 0.648. | `VPS_EVALUATION.md:31-32`. |
| **Repeated nested CV (VVE, default mode)** | Outer: a custom `stratified_folds` (round-robin within class after a permutation; `VVE:163-168`), 5 folds × 20 repeats. Inner: 4 folds on the training rows. The selected weights maximise the **sum of inner-fold AUROCs** over a simplex with step 0.1 (`VVE:158-160, 171-192`); ties go to the first lexicographic vector. Output is the mean of outer-fold AUROCs (`VVE:195-208`). | 5d 0.688 versus equal 0.763 (fold-mean); stored in `vps_validation.json`. |
| **Weighting matrix (VVE `--matrix`)** | `evaluate_fitted`: outer `StratifiedKFold(5, random_state=seed+rep)` or `StratifiedGroupKFold` on shared-trial components (`VVE:238-240, 288-307`). Four model kinds: equal, simplex (inner 4-fold), shrink-to-equal λ ∈ {0, .25, .5, .75, 1}, and L2-logistic C ∈ {.01, .1, 1, 10} with the scaler fitted in-fold (`VVE:247-285`). **Out-of-fold scores are pooled per repeat** and then scored (`VVE:305-306`). Seed 20261019, 20 repeats. | `VPS_WEIGHTING_DECISION_2026-10-19.md:35-55`. |
| **Approved result and provenance** | `data/run_manifest.json` `stages["06"].last_success`: `run_id = adopted-20261015T015501Z-06`, `status = ADOPTED` ("outputs existed before run tracking; fingerprinted, not re-run"), `scoring.baseline_lineage = "published baseline 2026-10-14 07:50:56"`, `rank_convention = legacy`, `script = scripts/06_vps_fusion.py`. **No code fingerprint** is recorded (TD-046 `TECHNICAL_DEBT.md:788-798`). It covers 8 inputs and 8 outputs (`vps_scores_v2.csv`, `vps_variant_results.csv`, `baseline_results_v2.csv`, `ablation_results_v2.csv`, `ablation_results_5d.csv`, `grid_search_{3,4,5}d_log.csv`). **All 16 md5s match the current files** (verified). Output mtimes are 2026-10-14 02:20:56 UTC, which is 07:50:56 local, matching the lineage label. The companion stages are also ADOPTED: `adopted-…-02`, `-03`, `-03c`, and `adopted-20261015T015502Z-eval`. The producing code is "06 as of 2026-10-14" (after D-003/D-004, before the D-024 `dimensions_imputed` change). The approved file **lacks `dimensions_imputed`** (verified), consistent with B-003 (`ERRORS_AND_BLOCKERS.md:636-640`). | The current 06 reproduces it from the persisted inputs only through the independent `vps_verify` (equal-weight columns, ranks, missing flags, labels; `vps_verify.py:131-160`). |
| **Unresolved decisions** | See the list below. | |

**Unresolved IDs (one line each):**
- TD-004 / TD-027 / TD-035: the pool requires a pre-cutoff PD trial; the endpoint is "continued investigation"; 24 ground-truth compounds are unevaluable.
- TD-006 / B-001: Open Targets is not cutoff-bounded.
- TD-007: pathway overlap is unweighted.
- TD-009: script 04 fails silently.
- TD-011: `N_RANDOM = 100` is a "quick test" value.
- TD-014: boxed-warning detection uses key presence.
- TD-017: drugs that share a target set get identical molecular scores.
- TD-019: stage 03 has no checkpoint.
- TD-020: low power (CIs ±0.15).
- TD-021 / B-002(a): literature is unbounded and truncated to 30 recency-ordered hits.
- TD-022: safety uses the current label.
- TD-023: Gate 2 checks identity, not role.
- TD-025: the ablation reference row is in-sample while the "Without X" rows are equal-weight.
- TD-032: the feature-side role re-audit is open; Galantamine is unresolved (D-005, D-011).
- TD-033: temporal validity by dimension; with a dated molecular dimension, 5D = 0.704 ≈ 4D.
- TD-036: the persisted nested CV is a single split.
- TD-038 / D-020 (PROPOSED): role policy for shared feature trials; `feature_role_exclusions.csv` is absent.
- TD-039: annotator verdict alias list (cosmetic).
- TD-040 / D-024: legacy versus midrank convention (owner).
- TD-041: proximity missing → median versus neutral.
- TD-042: the molecular pathway credit counts the drug's own target (owner); candidate `td042_v1`.
- TD-043: 10c role heuristics misfire.
- TD-046: no code fingerprint for 02, 06 and eval.
- TD-048: superseded metrics in `CASE_STUDIES.md`.
- B-002(b): live-only stages keep no response cache. This is a **duplicate ID**: there are two different B-002 entries, `ERRORS_AND_BLOCKERS.md:413` and `:547`.
- B-003: from-source rerun 0.7763 versus approved 0.7754.
- E-014: residual Gate-2 false match through background-therapy otherNames.
- E-055: agent pipeline defects.

---

## 2. Pipeline DAG (`ui/server.py` `STAGES`, `:57-~430`; protected set `ui/live_runs.py:31-38`)

"P" marks an output listed in `PROTECTED_ARTEFACTS`. The UI refuses to launch a stage whose outputs include a P
file (`live_runs.py:52-55`).

| id | script | depends_on | inputs | outputs (P = protected) |
|---|---|---|---|---|
| 01 | 01_get_pd_candidates.py | – | – | hetionet_nodes.csv, hetionet_edges.csv, pd_candidates_full.csv **P**, pd_candidates.csv **P** |
| 00 | 00_exclusion_filter.py | 01 | pd_candidates.csv | pd_candidates_filtered.csv **P** |
| 02 | 02_network_proximity.py | 00 | hetionet_edges.csv, pd_candidates_filtered.csv | network_proximity.csv **P** |
| 03 | 03_clinicaltrials_groundtruth.py | 00 | pd_candidates_filtered.csv | clinical_maturity_precutoff.csv **P**, ground_truth_postcutoff.csv **P**, clinicaltrials_match_audit.csv **P** |
| 03c | check_studytype.py (runs filter_by_studytype.py via runpy, `check_studytype.py:57`) | 03 | clinical_maturity_precutoff.csv, ground_truth_postcutoff.csv | nct_studytype_check.csv, clinical_maturity_precutoff_clean.csv **P**, ground_truth_postcutoff_clean.csv **P** |
| 04 | 04_literature_independence.py | 03c | clinical_maturity_precutoff_clean.csv | literature_independence.csv **P** |
| 05 | 05_safety_signal.py | 03c | clinical_maturity_precutoff_clean.csv | safety_signal.csv **P** |
| 08 | 08_molecular_pathway.py | 03c | clinical_maturity_precutoff_clean.csv | molecular_pathway.csv **P**, molecular_pathway_evidence.jsonl **P** |
| 06 | 06_vps_fusion.py | 02, 03c, 04, 05, 08 | pd_candidates_filtered, network_proximity, clinical_maturity_precutoff_clean, literature_independence, safety_signal, ground_truth_postcutoff_clean, label_role_exclusions **P (curated, no producer)**, molecular_pathway, feature_role_exclusions (absent) | vps_scores_v2.csv **P**, vps_variant_results.csv, baseline_results_v2.csv, ablation_results_v2.csv, ablation_results_5d.csv, grid_search_{4d,3d,5d}_log.csv |
| 04b | 04b_export_literature_graph.py (`--compound Droxidopa`) | 04 | _literature_checkpoint.jsonl | literature_graph_droxidopa.json |
| 05h | 05h_safety_label_history.py | 05 | safety_signal.csv | safety_label_history.csv, safety_label_history_run.json |
| 04p | 04p_literature_provenance.py | 03c, 04 | clinical_maturity_precutoff_clean.csv, _literature_checkpoint.jsonl | literature_papers.jsonl, literature_provenance.csv, literature_provenance_run.json |
| 07 | 07_generate_figures.py | 06, 04b | baseline_results_v2, vps_variant_results, ablation_results_v2, ablation_results_5d, literature_graph_droxidopa.json, vps_scores_v2 | figure1..3 PNGs |
| diag | check_intervention_match.py | 03c | both *_clean.csv | intervention_match_check.csv |
| 10d | conflict_context_agent.py | 05, 08, 06 | conflict_claims_curated.json **P**, molecular_pathway_evidence.jsonl, clinical_maturity_precutoff_clean, vps_scores_v2 | conflict_context.json |
| 10e | reproducibility_agent.py | 10d | pubmed caches, conflict_claims_curated, both *_clean | reproducibility.json |
| eval | vps_evaluation_report.py | 06, 10e | vps_scores_v2, gt_clean, label_role_exclusions, vps_variant_results, baseline_results_v2, ablation_results_5d, bootstrap_ci_equal5d_vs_4d.csv (**no producing stage**), reproducibility.json | vps_evaluation_report.json **P** |
| 10b | molecular_run_record.py | 08, 06 | molecular_pathway, evidence.jsonl, vps_scores_v2 | molecular_agent_run.json |
| 10c | clinical_evidence_agent.py | 03c, 08, 06 | precutoff_clean, match_audit, feature_trial_roles_td038 **P**, vps_scores_v2, ctgov_precutoff_trials.json **P**, evidence.jsonl | clinical_evidence.json |
| 10f | safety_evidence_agent.py | 05, 05h, 06 | vps_scores_v2, safety_signal, safety_label_history, _safety_failures.jsonl | safety_evidence.json |
| 10g | evidence_independence_agent.py | 10c, 04, 08, 04p, 06 | (9 files) | evidence_independence.json |
| 10a | literature_credibility_agent.py | – | case-claim caches | literature_credibility_{donepezil,domperidone,melatonin,propranolol}.json |
| 10a-all | literature_credibility_agent.py | 04p | literature_provenance.csv, literature_papers.jsonl | literature_credibility_all.json |
| review | clinical_role_review.py | 10c | precutoff_clean, ctgov_precutoff_trials, feature_trial_roles_td038, evidence.jsonl | clinical_role_review.csv, clinical_review_worklist.csv |
| 10h | completeness_gap_agent.py | 06, 10c, 10d, 10e, 10f, 10g, 10a-all, 10a | (20 files) | completeness_gaps.json |

DAG notes:
- `label_role_exclusions.csv` and `feature_trial_roles_td038.csv` are human-curated. They are protected and no stage produces them.
- `bootstrap_ci_equal5d_vs_4d.csv` is read by `eval` but produced only by a manual `bootstrap_auroc_ci.py --out`, which is not a registered stage.
- `scripts/run_stage.py 06` publishes only after `vps_verify` passes (`run_stage.py:35-36, 476-500`).
- The validation and sensitivity scripts (`vps_validation_experiments.py`, `vps_weighting_experimental.py`, `td038_*`, `vps_molecular_historical.py`, etc.) are **not in the DAG**. They write to `data/_runs/*` or `data/_candidates/*`.

---

## 3. Cutoff semantics in code

- `03_clinicaltrials_groundtruth.py:53`: `CUTOFF_DATE = "2021-01-01"`.
- The date field is **`protocolSection.statusModule.studyFirstPostDateStruct.date`**, stored as `first_posted` (`03:284`). It is not the start date, primary completion date or results date.
- The comparison is a **string** comparison: pre/feature if `first_posted and first_posted < CUTOFF_DATE` (`03:300`); post/label if `first_posted and first_posted >= CUTOFF_DATE` (`03:304`). An empty date is recorded as `cohort="no_date"` and does not qualify (`03:308-311`).
- String comparison is only correct for full `YYYY-MM-DD` dates. A month-only value such as `"2021-01"` would compare as `< "2021-01-01"` and be placed **pre-cutoff**. All stored dates currently have length 10 (verified), so this is latent.
- The tests confirm the boundary: `tests/test_temporal_and_ranking.py:43-50` and `tests/test_ground_truth_contract.py:22, 60-63`. There is no NCT ID in both sets.
- Observed ranges: features 2000-02-25…2020-11-25; labels 2021-01-13…2026-09-08.
- The auxiliary stages use an inclusive "2020-12-31": `04p_literature_provenance.py:44` (bounded PubMed `maxdate`, `:312`; partial dates ending in "12-31" count as PRE, `:161`) and `05h_safety_label_history.py:37` (`version_at` ≤ cutoff).
- Everything else is post-cutoff by construction (unbounded literature, current label, OT 26.09). Phase and status of pre-cutoff trials are as of the 2026-10-05 query.

---

## 4. `*_clean.csv` versus raw, and label exclusions

- **Producer.** `scripts/filter_by_studytype.py`, executed at the end of `check_studytype.py` (`check_studytype.py:56-57`; stage 03c). It refuses to run if any lookup is `ERROR` (`filter_by_studytype.py:7-11`).
- **Rule.** Keep an NCT iff `study_type == "INTERVENTIONAL"` and any `intervention_types` ∈ {DRUG, BIOLOGICAL} (`:13-17`). The filter is applied **by `nct_id` across all compounds** (`:20, 28`).
- **Nuance: the type check covers any intervention in the trial, not the matched compound's own intervention.** A DIETARY_SUPPLEMENT compound arm in a trial that also has a DRUG arm is kept.
- `nct_studytype_check.csv`: 252 NCTs (242 INTERVENTIONAL, 10 OBSERVATIONAL).
- **Pre-cutoff: 207 → 195 rows; 91 → 90 compounds.** The only compound lost is Mannitol. The 12 dropped rows (verified):
  - NCT01796483 Clonidine (DEVICE)
  - NCT03823638 Mannitol (DIETARY_SUPPLEMENT)
  - NCT00355927 Propofol (PROCEDURE)
  - NCT04502550 Propofol (OBS)
  - NCT01877538 and NCT02012595 Donepezil (OBS)
  - NCT02500108 Domperidone (OBS)
  - Ioflupane I 123: NCT02138682, NCT03019757, NCT02572713, NCT03022357 (OBS) and NCT04653688 (DEVICE/RADIATION)
- **Post-cutoff: 67 → 57 rows; 48 → 41 compounds** (lost: Inulin, Lithium, Promethazine, Propofol, Ropivacaine, Vancomycin, Yohimbine). The 10 dropped rows:
  - NCT05353764 Ropivacaine (OTHER)
  - NCT06647277 Vancomycin (COMBINATION_PRODUCT)
  - NCT06697626 Inulin (DIETARY_SUPPLEMENT)
  - NCT05895019 Propofol (OBS)
  - NCT05307770 Melatonin (DIETARY_SUPPLEMENT)
  - NCT06456684 Promethazine (OBS)
  - Lithium: NCT06099886, NCT06339034, NCT06592014 (DIETARY_SUPPLEMENT)
  - NCT07127146 Yohimbine (OTHER)
- **Effect on positives:**
  - Raw ground-truth compounds in the pool: 20.
  - After 03c: 17 (Lithium, Propofol and Yohimbine are lost).
  - After `label_role_exclusions.csv` (3 rows: NCT05376761 Dexmedetomidine, NCT06658132 Remifentanil, NCT07085195 Clozapine; policy "TD-032 P1", approved "2026-10-14 owner"): **14**.
- **How the exclusions are applied.** `06:569-571` calls `apply_label_exclusions`. That function first validates that each `(nct_id, compound_name)` pair exists in the ground truth, else raises (`06:328-332`). It then drops **every ground-truth row whose `nct_id` is listed, for every compound** (`06:333`), not per `(nct, compound)` link. The same is true in `vps_verify.py:117-119` and `VVE:103-104`.
- None of the 3 excluded NCTs is shared with another compound (verified; 4 label trials are shared overall), so this is latent. The CSV is applied **after** `build_standardized_scores` and affects only labels. The ground-truth CSV itself is unchanged.

---

## 5. Origin of the numbers, and whether they are the same estimand

| Number | Origin | Same estimand as approved 0.775376? |
|---|---|---|
| **0.775376** (0.7754) | `roc_auc_score(label, VPS_equal_5d)` on the approved `vps_scores_v2.csv` (run `adopted-20261015T015501Z-06`): 90 compounds, 14 positives, legacy ranks. Verified. | Reference. |
| **0.7763 / 4D 0.7049** (B-003) | The same formula, cohort and labels, but `network_proximity.csv` regenerated by the **current** stage 02 (seeded, sorted iteration after E-031) with seed 42. Row `seed=42` of `data/_runs/mission_20261019/proximity_seed_sensitivity.csv` = 4d 0.7049, 5d 0.7763. Across 10 seeds, 5D ranges 0.769–0.783. | The same estimand (population, label, formula) with a different Monte Carlo realisation of the proximity null. The approved file was one earlier draw made under hash-dependent order (E-031). It is not reproducible from source (B-003); it is reproducible only from the persisted inputs. |
| **17 positives** (0.747 5D / 0.689 4D, AUPRC 0.479; +0.059 [−0.024, +0.150]) | The 2026-10-05 Gate-2-corrected cohort **before** the P1 label exclusions (and before the D-003 safety re-query and the D-004 neutral rule). 17 = 20 raw − 3 removed by 03c (computed). Quoted in `README.md:179-183`, `TECHNICAL_DEBT.md:278-282, 302-306`, `CASE_STUDIES.md:198`, `ui/server.py:189, 1723-1726`. | **No.** The labels differ (Dexmedetomidine, Remifentanil and Clozapine were positive), the safety feature differs (v1 fields), and the missing-data rule differs (median versus neutral). An intermediate state, "14 positives, AUROC 4d 0.724 / 5d 0.781" (TD-032 `:561`, `CASE_STUDIES.md:509`), has the approved labels but pre-D-003/D-004 features. |
| **5d versus 4d** | `VPS_equal_5d` (mean of 5 ranks) versus `VPS_equal` (mean of 4; `06:577, 599`) on the same 90/14. Paired difference +0.0752: Bootstrap A gives [−0.0250, +0.1761], P = 0.935; Bootstrap C gives [−0.0235, +0.1758]. | The same population and label. They are different models. The 5D gain depends on TD-042 double counting and on an undated molecular dimension: TD-042 5D 0.6992 and dated-molecular 5D 0.704 are both ≈ 4D (TD-033 `:565-583`). |
| **Equal-weight versus grid-searched** | The `VPS_grid_*` AUROCs (4d 0.725, 3d 0.720, 5d 0.774) are **in-sample**, because the weights were selected on all 90 labels (`06:465, 584-611`). The held-out values differ by procedure. **Persisted single split:** 0.607 / 0.584 / 0.639 (seed 42, mean of fold AUROCs, step 0.25 or 0.1). **Report:** 20 repeats, seeds 0–19, 0.574 / 0.571 / 0.648. **VVE default:** inner-CV simplex step 0.1, fold-mean 5d 0.688 / 4d 0.575. **VVE matrix:** pooled OOF, simplex 5D 0.712 / 4D 0.602 (`VPS_WEIGHTING_DECISION:45-48`). **TD-036 (older data):** 0.636 / 0.669 / 0.710. | **Not the same estimand.** In-sample and held-out values are not comparable. The held-out values differ by grid, inner selection, aggregation (fold-mean versus pooled) and seeds. The equal-weight models fit nothing, so their "OOF" AUROC equals the full-cohort AUROC. |
| **td042_v1** | Directory `data/_candidates/td042_v1/` (`README.md` there). **Rule:** `MolecularAgentConfig.pathway_excludes_drug_targets=True` (`molecular_agent.py:206-210, 875-876`) via stage 08 `--exclude-drug-targets-from-pathways --offline --fresh --resolutions-from <frozen>`. A pathway counts as PD only through a module gene that is **not** one of the drug's own targets. Isolated root `root/data/` (manifest runs `20261019T090542Z-08-c629`, `20261019T090603Z-06-7b62`). Second-path check: `verify_td042_candidate.py`, which uses `VVE.build(molecular="td042_own_target")` (`VVE:51-60, 79-89`). `verification.json`: `all_pass: true`; 21 compounds changed (6 positives); `labels_equal_baseline: true`; n = 90; non-molecular ranks unchanged. Metrics: 5D 0.6992, AUPRC 0.3068, P@10 0.4; 4D 0.7002. **Status: NOT APPROVED, NOT PUBLISHED** (`publish_td042.sh:2`). An older staging copy is `data/_candidates/2026-10-19_sprint/10b_own_target_excluded_variant.csv` (TD-042 `:728`). | **Same cohort and same labels** (verified), different dimension-5 definition. The VVE re-implementation excludes the symbols of `targets ∪ genes` (`VVE:53`); stage 08 excludes the Ensembl IDs of the drug's targets (`molecular_agent.py:875`). Their 5D scores agree to 1.7e-16. |

---

## 6. Contradictions (numbered)

Format: Side A ↔ Side B. **Assessment** names the rule that is documented and approved where one exists.

1. **Bootstrap stratification.**
   - Side A: the traceability matrix says "stratified bootstrap 2,000 draws (seed 42 in the report)" (`docs/autonomous_runs/SCIENTIFIC_CONTRACT_TRACEABILITY.md:20`).
   - Side B: the report's bootstrap is **not stratified** (`vps_evaluation_report.py:55-66`, `rng.integers(0,len(y),len(y))`; `bootstrap_auroc_ci.py:48-54`). Only VVE is stratified, and it uses seed 20261019 (`VVE:140-150, 36`).
   - Assessment: the approved CIs [0.656, 0.881] come from the unstratified percentile bootstrap with seed 42. The traceability text is wrong. The same document's "Conflicts … none" (`:25`) and `final_verification_summary.json` "conflicts_found_in_contract": 0 are therefore incorrect.
2. **Two sets of CIs for the same models.**
   - `VPS_EVALUATION.md:23-24` and D-012 (`DECISIONS.md:279-284`), unstratified seed 42: 5D [0.656, 0.881]; prox+clin [0.474, 0.816]; literature-only [0.463, 0.825].
   - `VPS_WEIGHTING_DECISION:65-71` and `vps_validation.json`, stratified seed 20261019: 5D [0.6513, 0.8806]; prox+clin [0.480, 0.808]; literature [0.466, 0.821]; clinical-only 0.673 versus D-012 0.672.
   - Assessment: the CI procedures differ. Neither document says the other uses a different procedure.
3. **Positive count shown in the UI.**
   - `ui/server.py:189` (stage 06 limitations: "17 positives / 90 compounds") and the HISTORICAL panel `:1723-1726` ↔ the data, which has 14 (`vps_evaluation_report.json`; `README.md:172`; contract test `:27-29`).
   - Assessment: 14 is approved (TD-032 P1, owner 2026-10-14). Line 189 is stale. The HISTORICAL panel is labelled "historical" (`:1721, 1729`).
4. **README TD-031 text is stale.**
   - Side A: `README.md:195-197` says "the existing median rule still ranks those compounds level with the safest … policy is an open decision".
   - Side B: the code applies neutral 0.5 and no imputation (`06:201-209, 254, 277-280, 302`), as D-004 decided (`DECISIONS.md:115-125`) and TD-031 marks FIXED (`TECHNICAL_DEBT.md:497`).
   - Assessment: D-004 neutral 0.5 is approved.
5. **No-target molecular 0.0.**
   - Side A: `docs/MOLECULAR_AGENT.md:263-266` says "A 0.0 produced by the agent is a real measurement and is left alone … median-imputed to match the convention the other four dimensions already use".
   - Side B: no-target 0.0 is treated as missing and given neutral 0.5 (`06:283-291`; D-004; TD-024 FIXED, `TECHNICAL_DEBT.md:398`). The "other four" no longer all use the median (safety uses neutral).
   - Assessment: D-004 is approved. The MOLECULAR_AGENT doc is stale.
6. **D-024 versus data on `n_dimensions_measured`.**
   - Side A: `DECISIONS.md:610-611` ("Deferiprone and Trimethobenzamide: 5 → 4") and `VPS_EVALUATION.md:93` ("was 5 for 2 compounds").
   - Side B: the approved file has **4** for both, because their molecular dimension is also missing (`dimensions_missing = molecular`). Under current code they would be **3**. The report shows `n_dimensions_measured {'3': 2, '4': 19, '5': 69}`. The two 3s are the safety|molecular compounds, so it already counts imputed proximity as measured.
   - Assessment: a metadata-only error in the docs. No score is affected.
7. **The clinical dimension "trial count".**
   - Side A: `README.md:15` says "max trial phase, trial count".
   - Side B: only `max_phase_rank` is ranked (`06:275`). `n_trials` is unused, as D-020 itself states (`DECISIONS.md:458-460`).
   - Assessment: the code is the approved rule (`VPS_FEATURE_CONTRACT.md:26-27`).
8. **The `vps_verify` docstring versus stage 06.**
   - Side A: `vps_verify.py:19-20` says "median … (imputed, then ranked; stage 06 does not flag these)".
   - Side B: the current 06 flags them in `dimensions_imputed` (`06:212-217`). `VPS_EVALUATION.md:80` says "It is now flagged". The approved file has no such column (B-003).
   - Assessment: docs, code and data are out of step. The published artefact predates the flag (D-024 `:614-615`).
9. **Where the baseline reproduction assert lives.**
   - Side A: `VPS_FEATURE_CONTRACT.md:5` says "`vps_validation_experiments.py`, whose `build()` asserts the same reproduction".
   - Side B: the assertion is in `main()` (`VVE:411-414`), not in `build()`. The `--matrix` path returns before it (`VVE:403-407`), so the weighting-decision run never asserted reproduction.
   - Assessment: a documentation error. The matrix numbers equal the asserted numbers in `vps_validation.json` (0.7754), so the risk is low.
10. **TD-042 is "must use" yet the live baseline does not.**
    - Side A: `VPS_WEIGHTING_DECISION:23` says "The molecular dimension must use the TD-042 rule".
    - Side B: the live code defaults to `pathway_excludes_drug_targets=False` (`molecular_agent.py:206-210`). The approved file uses the original rule. The contract test pins 0.775376 as "approved 5D" (`test_ground_truth_contract.py:113`). `td042_v1` README says "NOT APPROVED".
    - Assessment: the approved published rule is the **original** (non-TD-042) rule. The weighting doc's own lines 25-27 say that 0.775 "overstate[s] the model and must not be reported as an improvement".
11. **Is 4D primary or a sensitivity analysis?**
    - Side A: D-002 says "Equal-weight 4d and 5d as primary" (`DECISIONS.md:45-47`). `VPS_EVALUATION.md:20-25` and `vps_evaluation_report.py:118-119` label both "(primary)".
    - Side B: `VPS_WEIGHTING_DECISION:15-17, 31-33` says the primary is 5D and 4D is a "sensitivity" analysis. The contract test says `VPS_equal_5d` is "the approved primary score" (`test_ground_truth_contract.py:11`). The UI ranks by `VPS_equal_5d (primary, unfitted)` (`ui/server.py:1036`).
    - Assessment: D-002 is the only logged decision. The weighting doc (2026-10-19) re-states it without an owner sign-off line.
12. **Stage 06 still selects a "best variant" on the evaluation labels.**
    - Side A: `06:694-699` picks `max(variant_scores)` by AUROC across in-sample grid and equal variants and prints its top 15. The docstring presents grid-searched weights as the improvement (`06:2-8`). The UI stage purpose is "fuse (equal and grid-searched weights)" (`ui/server.py:176`).
    - Side B: D-002 rejects reporting the best variant ("(a) selects on the evaluation labels", `DECISIONS.md:45-47`).
    - Assessment: the console print does not reach the published scores, but the narrative contradicts the approved rule. `CASE_STUDIES.md:3-4` likewise ranks by `VPS_grid_3d` "best-performing … 0.750" (TD-048 `TECHNICAL_DEBT.md:800-804`).
13. **Superseded metrics in CASE_STUDIES.**
    - Side A: `CASE_STUDIES.md:198` ("17 positives … 0.747") and `:509` ("AUROC 4d 0.724 / 5d 0.781").
    - Side B: the approved 0.700 / 0.775 (`README.md:173-176`). The same applies to `TECHNICAL_DEBT.md:561` (TD-032 rerun values).
    - Assessment: superseded. This is open as TD-048.
14. **Three different cutoff wordings.**
    - Side A: `CUTOFF_DATE="2021-01-01"` with `<`/`>=` (`03:53, 300-304`; README `:7`).
    - Side B: "trials first posted ≤ cutoff" (`VPS_FEATURE_CONTRACT.md:31`); "cutoff: 2020-12-31 … first posted before the cutoff are evidence" (`ui/server.py:1976-1977`); "first posted after the 2020-12-31 cutoff" (`VPS_WEIGHTING_DECISION:10`); `CUTOFF = "2020-12-31"` inclusive (`04p:44`, `05h:37`).
    - Assessment: the code (stage 03) is authoritative. "≤ cutoff" read with cutoff = 2021-01-01, or "before 2020-12-31", would each be off by one day. No data are affected (latest feature trial is 2020-11-25; earliest label is 2021-01-13).
15. **Label exclusions: per trial or per link.**
    - Side A: the CSV has an `(nct_id, compound_name)` key and the docstring says "per trial, not per compound" (`06:316-325`); the D-020 feature policy is per link (`06:128-134`).
    - Side B: the code drops every row with the listed `nct_id` for all compounds (`06:333`; also `vps_verify.py:117-119`, `VVE:103-104`).
    - Assessment: consistent with "per trial", but the compound column is used only for validation. This is latent: none of the 3 NCTs is shared.
16. **TD-042 candidate location.**
    - Side A: `TECHNICAL_DEBT.md:728` says "Staged in `data/_candidates/2026-10-19_sprint/10b_own_target_excluded_variant.csv`".
    - Side B: `VPS_WEIGHTING_DECISION:23` and `VPS_FEATURE_CONTRACT.md:42` say `data/_candidates/td042_v1/`.
    - Assessment: two artefacts. `td042_v1` is the verified candidate (`verification.json` all_pass).
17. **Nested-CV figures quoted without stating the procedure.**
    - The values are 0.639 (persisted), 0.648 (report), 0.688 (VVE default) and 0.712 (VVE matrix) for "5D grid, held-out". Sources: `vps_variant_results.csv`, `VPS_EVALUATION.md:32`, `vps_validation.json`, `VPS_WEIGHTING_DECISION:46`.
    - Each document presents its own figure as "the" held-out estimate.
    - Assessment: D-002 requires repeated nested CV. The report's 0.648 is the one documented in the approved evaluation record (D-018).
18. **The bootstrap docstring and README quote the unreproducible old CI.**
    - Side A: `README.md:181-183` and `TECHNICAL_DEBT.md:280-282` quote "+0.059 [-0.024, +0.150]".
    - Side B: `bootstrap_auroc_ci.py:4-6` says this "cannot be reproduced". The current approved value is +0.075 [−0.025, +0.176].
    - Assessment: the README flags it as historical, so this is only a mild inconsistency.
19. **Molecular "imputation" rule in the report versus D-004 scope.**
    - Side A: `vps_evaluation_report.py:172` says absent → median.
    - Side B: D-004 says "never equate missing with negative" and applies neutral only to safety and molecular-no-target (`DECISIONS.md:130-132`). Proximity missing is median (TD-041).
    - Assessment: three different missing-data rules coexist; this is documented as open (TD-041). VVE shows that neutral proximity changes 5D by −0.0047 [0.0, 0.015] (`vps_validation.json`).
20. **Bootstrap estimate "matches" while the stratification claim is wrong.**
    - Side A: the contract test checks only that `lo < auroc < hi` (`test_ground_truth_contract.py:100-101`).
    - Side B: the traceability doc asserts a stratified procedure (see C-1).
    - Assessment: no test pins the bootstrap procedure, so the stratification claim was never tested.
21. **Interpretation of the safety-v1 Spearman figure.**
    - `D-003` (`DECISIONS.md:84`) says 0.76, while `VPS_WEIGHTING_DECISION:83` and `VPS_FEATURE_CONTRACT.md:32` quote safety Spearman values with other dimensions. These are different quantities, not a conflict.
    - E-031 says "ranks Spearman ≥ 0.995 vs published" (`ERRORS_AND_BLOCKERS.md:540`), while `VPS_WEIGHTING_DECISION:88` says "proximity_z Spearman vs published is ≥ 0.991". The CSV shows proximity_z ≥ 0.9912 and VPS5 ≥ 0.9946. E-031's wording mislabels which rank is meant.
22. **Pipeline step list.**
    - Side A: `README.md:47-48` lists `check_studytype.py` **and** `filter_by_studytype.py` as separate mandatory steps.
    - Side B: `check_studytype.py:56-57` already runs `filter_by_studytype.py`. The UI registers a single stage 03c with `related_scripts` (`ui/server.py:111-119`).
    - Assessment: running both is harmless (idempotent). The README is outdated.
23. **Mannitol.**
    - Side A: `INTERVENTION_MATCHING.md:77-78` says "the genuine mannitol trial (NCT03823638) is still accepted".
    - Side B: Gate 2 accepts it, but 03c removes it (DIETARY_SUPPLEMENT). Mannitol leaves the pool (91 → 90).
    - Assessment: not a code conflict, but the doc implies Mannitol contributes evidence. It does not.
24. **Duplicate blocker ID.**
    - B-002 is used for two different blockers (`ERRORS_AND_BLOCKERS.md:413` literature/safety re-retrieval; `:547` live stages without cache). Any reference to "B-002" (for example `vps_evaluation_report.py:198`) is ambiguous.
25. **The 20-result cap is undocumented.**
    - `03:78` uses `pageSize: 20` with no `nextPageToken` handling. 12 compounds hit the cap, including pool member Ioflupane I 123.
    - No TD, B or E entry mentions truncation. The INTERVENTION_MATCHING and README cost notes are silent on it.
    - Assessment: a potential silent loss of feature or label trials. It needs an owner entry.

---

## 7. The AUROC function `auroc_cols` (`scripts/vps_validation_experiments.py:112-116`)

```python
def auroc_cols(scores, y):
    r = rankdata(scores, axis=0)
    npos, nneg = y.sum(), len(y) - y.sum()
    return (r[y == 1].sum(axis=0) - npos * (npos + 1) / 2) / (npos * nneg)
```

**Inputs**
- `scores`: an n × k array, one column per model or weight vector. Callers pass `score[:, None]` for one model, or `R @ W.T` to score every simplex weight vector at once.
- `y`: a 0/1 (or bool) numpy array of length n.

**Rank computation**
- `scipy.stats.rankdata(..., axis=0)` with the default `method="average"`, which gives tied scores their mid-rank.
- The result is the Mann-Whitney U of the positives divided by n_pos·n_neg. This is the probability that a random positive outranks a random negative, with **ties counted as ½**.
- Higher score means more likely positive. There is no direction flag.
- Checked: `[[1],[1],[2]]` with y = `[1,0,0]` gives 0.25. `tests/test_vps_validation_experiments.py:22-23` asserts 0.75 and an all-ties value of 0.5.

**Zero positives or zero negatives**
- There is no guard. The denominator is 0, so numpy emits `RuntimeWarning: invalid value encountered in divide` and returns **NaN** for every column. This was verified with y = `[0,0]` and y = `[1,1]`.
- In `_fit_simplex`, `fit_model` and `nested_cv`, `np.argmax` over an array containing NaN returns the **index of the first NaN**. That is weight vector 0, `(0, …, 0, 1)` (all weight on the last dimension), and it is selected **silently**.
- This cannot happen with VVE's custom `stratified_folds` at 14 positives, because round-robin assignment guarantees at least 2 positives per inner fold.
- It can happen in the grouped scheme (`StratifiedGroupKFold` in `evaluate_fitted`/`fit_model`), if a group-constrained inner validation fold has no positives.
- In `bootstrap`, stratification guarantees both classes, so this never arises.

**Callers inside VVE**
- `metrics` (`:137`), used by `bootstrap` (`:148`), `weighting_matrix` (`:339, 344`), `evaluate_fitted` (`:306`) and `main` (`:431`)
- `nested_cv` (`:186, 190, 191`)
- `_fit_simplex` (`:244`)
- `fit_model`: simplex (`:257`), shrink (`:264`), logit_l2 (`:280`)

**Callers outside VVE** (indirect, through `vve.metrics`, `vve.bootstrap` or `vve.evaluate_fitted`)
- `scripts/vps_architecture_comparison.py:69-80`
- `scripts/vps_weighting_experimental.py:67`
- `scripts/vps_evidence_overlap.py:134-142`
- `scripts/vps_literature_cutoff_sensitivity.py:127-143`
- `scripts/vps_molecular_historical.py:204-218`
- `scripts/vps_molecular_snapshot_sensitivity.py:95-106`
- `data/_candidates/td042_v1/verify_td042_candidate.py:47`

**Direct test callers**
- `tests/test_vps_validation_experiments.py:22-23` (direct)
- The same file at `:43-47, 71-81` (indirect, through `nested_cv`, `evaluate_fitted` and `fit_model`)

**Not used by**
- The approved artefacts (stage 06 and the evaluation report use `sklearn.roc_auc_score`)
- The contract test (uses its own Mann-Whitney)

The functions agree numerically. Without ties, `auroc_cols` equals `roc_auc_score` exactly. With ties, both use the ½ convention.
