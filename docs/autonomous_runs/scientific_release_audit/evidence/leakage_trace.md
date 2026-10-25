# EviRep leakage / data-flow audit (read-only, 2026-10-20)

Scope: Parkinson's repurposing, cutoff 2021-01-01. Outcome = an accepted PD interventional trial first posted on or after 2021-01-01. Predictors should use only information available before the cutoff.
Method: static reading of the code and docs, plus offline pandas reads of persisted `data/` artefacts. No repository file was changed, no stage was run and no network request was made.
Paths are relative to `/Users/thrisha/Drup_Rep_PF/EviRep`. Citations are `file:line`.

---

## 0. Data-flow map (actual reads and writes)

| Script | Reads | Writes |
|---|---|---|
| `scripts/01_get_pd_candidates.py` | Hetionet v1.0.0 zip from Zenodo (`:10`, `:17-27`) | `data/hetionet_nodes.csv`, `data/hetionet_edges.csv` (`:33-34`); `pd_candidates_full.csv` (`:54`); `pd_candidates.csv` = compounds with no CtD/CpD edge to DOID:14330 (`:41-57`) |
| `scripts/00_exclusion_filter.py` | `data/pd_candidates.csv` (`:29`) | `data/pd_candidates_filtered.csv` (`:33`); a hard-coded nutrient/vitamin/amino-acid list (`:11-26`) |
| `scripts/02_network_proximity.py` | `data/hetionet_edges.csv`, `data/pd_candidates_filtered.csv` (`:55-70`) | `data/network_proximity.csv` (`:658`). Uses GiG, DaG/DuG/DdG and CbG edges only (`:84`, `:115-133`, `:144-160`) |
| `scripts/03_clinicaltrials_groundtruth.py` | `data/pd_candidates_filtered.csv` (`:184`); live CT.gov v2 (`:54`, `:66-110`); ChEMBL synonyms and trade names via Open Targets, imported from `molecular_agent` (`:43-49`, `:113-170`) | `clinical_maturity_precutoff.csv`, `ground_truth_postcutoff.csv`, `clinicaltrials_match_audit.csv` (`:319-321`) |
| `scripts/03b_resume_failed_searches.py` | the three 03 outputs and the candidate file (`:45-48`, `:71`, `:82`, `:215-216`) | merges them back into the same files (`:222-224`) |
| `scripts/check_studytype.py` | pre and post CSVs (`:27-28`); live CT.gov per NCT (`:13-24`) | `nct_studytype_check.csv` (`:49`); then runs `filter_by_studytype.py` (`:57`) |
| `scripts/filter_by_studytype.py` | `nct_studytype_check.csv` (`:7`); pre and post CSVs (`:25-26`) | `*_clean.csv` (`:30-31`). Keeps INTERVENTIONAL trials with a DRUG or BIOLOGICAL arm (`:13-17`) |
| `scripts/intervention_matcher.py` | nothing (pure; docstring `:1-62`) | — |
| `scripts/trial_role.py` | nothing (pure; "DIAGNOSTIC ONLY … NOT wired into stage 03", `:2-10`) | — |
| `scripts/clinical_role_review.py` | `clinical_maturity_precutoff_clean.csv`, `data/cache/ctgov_precutoff_trials.json`, `feature_trial_roles_td038.csv` (`:31-33`, `:55-64`); ChEMBL names from `molecular_pathway_evidence.jsonl` (`:14`) | `clinical_role_review.csv` (`:177-186`). Diagnostic only |
| `scripts/04_literature_independence.py` | `clinical_maturity_precutoff_clean.csv` (`:240`); live PubMed (`:59-104`); live Semantic Scholar citations (`:123-178`) | `_literature_checkpoint.jsonl`, `literature_independence.csv` (`:283`, `:297`) |
| `scripts/04p_literature_provenance.py` | the stage-04 compound list (`:46`); PubMed (unbounded sample with retmax 30, plus a date-bounded query with retmax 500, `:10-11`, `:102-105`, `:312`) | `literature_papers.jsonl`, `literature_provenance.csv`. Not used by stage 06 |
| `scripts/05_safety_signal.py` | `clinical_maturity_precutoff_clean.csv` (`:75`); live openFDA label (`:24-32`) | `_safety_checkpoint_v2.jsonl`, `data/cache/openfda_labels/`, `safety_signal.csv` (`:65-72`, `:110`) |
| `scripts/05h_safety_label_history.py` | the openFDA cache and `safety_signal.csv`; DailyMed SPL history (`:36-42`) | `safety_label_history.csv`, `safety_label_history_run.json`. Not used by stage 06 |
| `scripts/08_molecular_pathway.py` + `molecular_agent.py` | `clinical_maturity_precutoff_clean.csv` (`08:62`, `:143`); Open Targets GraphQL (`molecular_agent.py:90`) | `molecular_pathway.csv`, `molecular_pathway_evidence.jsonl` (`08:63-64`, `:357-362`) |
| `scripts/06_vps_fusion.py` | candidates, proximity, clinical, literature, safety and ground truth (`:61-68`); molecular (`:58`, `:71-85`); `label_role_exclusions.csv` (`:313`, `:569-571`); optional `feature_role_exclusions.csv` (`:125`, `:541-543`; the file does not exist) | `vps_scores_v2.csv`, grid logs, baseline, ablation and variant CSVs (`:612-692`) |
| `scripts/vps_verify.py` | the same raw inputs (`:84`, `:116-118`) | a report only |
| `scripts/vps_validation_experiments.py` | the same raw inputs (`:63-108`); `molecular_pathway_evidence.jsonl` for the TD-042 variant (`:79-89`) | `data/_runs/validation_20261019/`, `vps_weighting_20261019/` |
| `scripts/vps_evaluation_report.py` | `vps_scores_v2.csv`, ground truth, exclusions, variant, ablation and bootstrap CSVs (`:5-9`, `:93-94`) | `vps_evaluation_report.json` |
| `scripts/bootstrap_auroc_ci.py` | `vps_scores_v2.csv` only (`:30`) | a CSV only with `--out` |
| `scripts/td038_feature_role_sensitivity.py` | clinical, scores, ground truth, exclusions and roles (`:44-45`, `:149`) | `td038_feature_role_sensitivity.json` |
| Sensitivity scripts | `vps_literature_cutoff_sensitivity.py` (`:39-41`: 04p papers, 05h history); `vps_molecular_snapshot_sensitivity.py` and `vps_molecular_historical.py` (`data/cache/opentargets_20.11/`, `historical:44-56`); `vps_architecture_comparison.py` (`:29`); `vps_weighting_experimental.py`; `vps_evidence_overlap.py` (`:42-44`) | `data/_runs/*` only. Nothing is published |

The pool is built at `06_vps_fusion.py:172-174`: compounds with at least one accepted pre-cutoff PD trial, and in the filtered candidate list. That gives 90 compounds.
Labels are built at `06:338-342`: membership in `ground_truth_postcutoff_clean.csv` minus `label_role_exclusions.csv`. That gives 14 of 90 positive.

---

## Q1. Does any label-generation code read VPS scores, dimension values, ranks, literature counts or molecular evidence?

**In code: no.**
- Stage 03 decides pre or post only from `studyFirstPostDateStruct` (`03:284`, `:300-311`). Trial acceptance depends only on the condition gate (`:172-177`, `:235`) and the intervention gate (`:251-253`, via `intervention_matcher.match_trial`).
- Stage 03 imports `molecular_agent` (`03:43-49`), but only to fetch ChEMBL **synonyms and trade names** (`03:139-160`). It calls `get_drug_mechanisms`, which also returns MoA targets, but only the `synonyms`/`tradeNames` labels are used. No molecular score, datatype score or target evidence enters labels.
- `filter_by_studytype.py` uses only study type and intervention type (`:13-20`).
- In `06`, `build_labels` (`:338-342`) reads only the ground-truth compound set. `apply_label_exclusions` (`:316-335`) reads only NCT and compound pairs. Labels are attached after `build_standardized_scores` (`:568-572`); `vps_validation_experiments.py:102-105` attaches them after every feature too.

**By people: yes, partly.** The curated label inputs were decided while scores and AUROCs were visible:
- `data/label_role_exclusions.csv` (3 rows, approved "2026-10-14 owner") comes from `docs/CASE_STUDIES.md` §9–9.1 (`:426-509`).
  - That audit covered only the **24 label-defining trials of the 17 positives**. Negatives were not audited for missed positives (`CASE_STUDIES.md:428-431`).
  - Its impact table (P0 AUROC 0.747 → P1 0.781 for 5d) was computed before the owner applied P1 (`:486-500`).
  - So the policy was chosen with knowledge of its AUROC effect. The direction of label change was one-sided (positive → 0 only).
- The Gate-2 matching rules (TD-018) came from verifying the **top-ranked** compounds of the 2026-10-05 run, ranked by `VPS_grid_3d` (`CASE_STUDIES.md:1-17`, `:92-150`).
  - The fix is a general structural rule, not a per-compound list (`intervention_matcher.py:15-62`, `:80-107`).
  - It removed high-ranked positives (Phenol, Norepinephrine, Dopamine), which likely lowered rather than raised AUROC.
- Lidocaine and Galantamine were decided with a sensitivity table in hand (`DECISIONS.md` D-005 `:142-154`; D-011 `:238-269`).
- `DECISIONS.md` D-002 (`:35-56`) itself states the analysis specification was made after results were seen.

---

## Q2. Does feature code read post-cutoff label files or post-cutoff trial records?

**Direct reads: no.**
- Feature stages 02, 04, 05 and 08 read only `pd_candidates_filtered.csv` or `clinical_maturity_precutoff_clean.csv` (`02:66-68`; `04:240`; `05:75`; `08:62`).
- In `06`, `ground_truth` is loaded together with the features (`06:67`), but it is used only in `build_labels`, after ranking (`06:569-572`).
- Ranks and medians are label-free but computed on all 90 compounds, i.e. transductively (`06:201-221`, `:257-303`; documented at `vps_validation_experiments.py:212-214`).
- Only evaluation and diagnostic scripts read `ground_truth_postcutoff*` or `label_role_exclusions.csv`: `vps_verify`, `vps_validation_experiments`, `vps_evaluation_report`, `td038`, `vps_evidence_overlap`, `check_intervention_match`.

**Indirect post-cutoff influence on the clinical-maturity feature: yes, possible.**
1. **Phase and fields come from the 2026 registry record.**
   - The phase is `design_mod.phases[0]` from the record returned by the query run on 2026-10-05 (`03:285-286`). It is not the phase as of 2020.
   - In the cached pre-cutoff records (`data/cache/ctgov_precutoff_trials.json`, retrieved 2026-10-15), **65 of 177 have `lastUpdatePostDate` ≥ 2021-01-01**. 21 posted results after 2021. 9 have a start date in 2021 or later (e.g. NCT04373317, first posted 2020-05-04, start 2022-10-24, RECRUITING).
   - Phase changes after the cutoff are therefore possible. They cannot be detected from persisted data, because no version history is stored.
   - The persisted phase equals the 2026-10-15 cache for all 195 links (0 mismatches). So the feature is "phase in the 2026 record".
   - TD-033 records this as "phase … from today's registry record" (`TECHNICAL_DEBT.md:609-616`).
2. **`phases[0]` takes the lower phase of a combined phase.** 16 trials are PHASE1/PHASE2 or PHASE2/PHASE3 (`03:286`). This is a bias, not leakage.
3. **Which pre-cutoff trials count is decided with 2026 information.** The Gate-1 conditions, Gate-2 interventions and otherNames, study type (`check_studytype.py:13-24`) and ChEMBL 26.09 alias sets (`03:113-170`) are all read today. A record edited after the cutoff (for example a condition or arm added) can change feature links and pool membership.
4. **Feature-role adjudication (D-020/TD-038)** used 2026-10-14 registry records and was evaluated against labels (S0–S3 table, `DECISIONS.md:500-511`). It is proposed and not applied: `feature_role_exclusions.csv` does not exist (`06:125`, `:541`).
5. **Separation is otherwise clean.** Max pre `first_posted` is 2020-11-25 and min post is 2021-01-13, with 0 NCT overlap (`TECHNICAL_DEBT.md:604-606`).
6. **Same query, both sides, with truncation (new finding).** `search_trials` requests `pageSize: 20` and never pages (`03:75-79`, `:104`).
   - 12 compounds returned exactly 20 studies.
   - One is in the pool: **Ioflupane I 123** (20 returned: 7 pre-cutoff MATCHED, 11 NO_MATCH, 2 UNVERIFIABLE, 0 post; label 0).
   - Its label (and possibly its phase) may be a truncation artefact. Because the result order is not date-sorted, the cap can also hide post-cutoff trials. This is not documented in TECHNICAL_DEBT.

---

## Q3. Molecular dimension (stage 08 / `molecular_agent.py`)

**Release used.** Open Targets Platform GraphQL API v26.9, data **26.09**, probed 2026-10-05.
- Docstring: `molecular_agent.py:52-53`. Endpoint: `:90`.
- Disease ID `MONDO_0005180` (`:93`). The 20.11 release used `EFO_0002508` (`vps_molecular_historical.py:47`).
- `data/molecular_agent_run.json` has `agent_version: "unrecorded"`. The OT data version is recorded only in docs: the docstring and `docs/REFERENCES.md:58`, `:116`.

**Datatypes** (config `molecular_agent.py:155-165`, `:185-191`):
- Allowed for the direct component: `genetic_association, genetic_literature, animal_model, affected_pathway, somatic_mutation, rna_expression` (`:155-162`).
- Excluded: `clinical` (datasource `clinical_precedence`, the former `known_drug`) and `literature` (europepmc) (`:165`). The rationale is at `:25-38`.
- Module membership uses the same allowed datatypes minus `affected_pathway` (`:185-191`).
- Exclusion is enforced per association row: `filtered_disease_link` (`:632-673`) keeps only allowed datatype scores and records the dropped ones.
- The overall OT `score` is not used for the gene score (`:37-38`).
- Validation `__post_init__` refuses overlap between allowed and excluded datatypes (`:227-233`).
- `known_drug`, `drug(...).indications`, `knownDrugs` and `maximumClinicalTrialPhase` are **not queried**. The drug query fetches only identity, synonyms and MoA targets (`:401-416`). The target query fetches pathways and associations (`:597-604`).

**Residual outcome-leakage channels:**
1. **The PD module is truncated by the overall score, which contains the excluded datatypes.**
   - `build_disease_module` requests `associatedTargets(page:{index:0,size:300})` (`:683-693`, `:728-731`). Its rows come in OT's default order, i.e. by **overall** association score, which includes `clinical` and `literature`.
   - Only afterwards are rows filtered to module datatypes ≥ 0.10 (`:742-760`).
   - So the excluded datatypes still decide *which* 300 genes are candidates. Genes that are targets of drugs in PD clinical trials (clinical precedence) are favoured for module entry, and through the pathway component (and the direct component, where a target is a module gene) they raise those drugs' scores.
   - The comment "re-ranked using allowed datatypes only" (`:198-200`) describes filtering after the truncation, not before it.
   - `vps_molecular_historical.py:9` reproduces the same rule ("top 300 PD targets by overall association score"). The 20.11 rebuild therefore carries the same channel, with `known_drug` from 2020.
2. **Current-snapshot evidence.** 26.09 genetic, animal-model and expression evidence includes everything published up to 2026. The temporal drift is large: Spearman 0.26 between the 20.11-rebuilt and the published molecular score (`data/_runs/molecular_historical_20261020/molecular_historical.json`).
3. **Drug → target mapping is today's ChEMBL MoA.** ChEMBL 2020-06 mechanisms give 70 drugs with targets against 74 today; 62 have the same target set (same json, `dated_chembl_targets`). MoA curation could follow clinical activity.
4. **`genetic_literature` and `affected_pathway`** are literature- and pathway-derived evidence with current dates. They are not outcome datatypes, but they are not cutoff-bounded.
5. **The 0.6/0.4 weights are stated as a priori and not fitted** (`:134-148`, `:194-195`). However, the molecular agent was built on 2026-10-05, after the 4-dimension VPS with labels already existed (git `c99a850`, 2026-09-23). TD-042 (own-target double counting) was found after evaluation, and adopting it remains an owner decision made with labels known (`VPS_WEIGHTING_DECISION_2026-10-19.md` §2; `TECHNICAL_DEBT.md:722`). Its correction lowers AUROC (0.775 → 0.699), so it is not optimistic tuning.

**Measured effect.**
- 5D approved: 0.775. With molecular rebuilt at 20.11: 0.690 (Δ −0.086 [−0.186, 0.020]).
- With 20.11 plus ChEMBL 2020-06 targets: 0.704 (Δ −0.071 [−0.173, 0.030]).
- Molecular alone: 0.627 → 0.516.
- With dated inputs, the 5D advantage over 4D disappears (`TECHNICAL_DEBT.md:565-581`).

---

## Q4. Literature dimension (stage 04)

**Date bounds: none in the scored dimension.**
- The query is `"<compound>"[Title/Abstract] AND "Parkinson Disease"[Title/Abstract]` with `retmax=30` (`04:45`, `:68-69`).
- The `max_date` / `mindate` / `maxdate` (pdat) option exists (`:59-73`) but is deliberately **not wired into `main()`**. `main` calls `search_pmids(compound)` without a date (`:257`).
- ESearch default ordering returns the most recent records first. The project itself calls the sample "the 30 MOST RECENT hits" (`vps_literature_cutoff_sensitivity.py:5-7`; `TECHNICAL_DEBT.md:312-333`).

**Current snapshot.** PubMed was queried at stage-04 run time (outputs dated 2026-10-05). No per-record retrieval date, PMID or publication date is stored in `literature_independence.csv`. Provenance was reconstructed later by 04p (2026-10-19; `literature_provenance_run.json`).

**Semantic Scholar citations are current.** `/paper/PMID:{id}/citations` is a live call (`04:131-138`). Citing papers include post-cutoff papers, so citation edges, and therefore `effective_independent_count`, depend on the 2026 citation graph. Lookup failures are recorded as missing edges (`:192-200`, `:277-281`).

**Measured leakage** (from `data/literature_provenance.csv`, joined to labels):
- 40 of 90 samples are truncated at 30.
- The mean post-cutoff fraction of the sample is **0.67 for positives (median 0.71) vs 0.43 for negatives (median 0.40)**.
- The share of recent literature differs strongly by outcome, which is a direct route for the outcome to enter the feature (research activity after 2021 correlates with new trials).
- Stage-04 samples contain no paper that reports a label trial by NCT ID. This is a lower bound, because many reports cite no NCT (`evidence_overlap.json`: `compounds_sample_reports_label_trial 0`).
- Replacing literature with cutoff-bounded measures: 5D Δ −0.019 [−0.067, 0.030] (count) and −0.027 [−0.073, 0.016] (shared-author components) (`data/_runs/literature_cutoff_20261019/literature_cutoff_sensitivity.csv`).

---

## Q5. Safety dimension (stage 05 / 05h)

- **Stage 05 scores the current openFDA label.**
  - The search is `openfda.generic_name:"<name>"` with `limit=1`, which picks an arbitrary product label (`05:24-32`).
  - It records `label_effective_time` and `label_set_id` (`05:45-47`). Effective-time years in `safety_signal.csv`: 2018:1, 2019:3, 2020:1, 2022:4, 2023:9, 2024:13, 2025:27, 2026:25, none:7. So **78 of 83 labels took effect after 2020**.
  - File mtime is 2026-10-14 (v2 re-query, D-003 `DECISIONS.md:58-97`).
- **05h (label at cutoff) is diagnostics and sensitivity only.**
  - Its docstring says "New files only; stage 05 and VPS unchanged" (`05h:2`). Stage 06 never reads `safety_label_history.csv`: `06:61-68` reads `safety_signal.csv` only.
  - It is used only by `vps_literature_cutoff_sensitivity.py:40`, `vps_weighting_experimental.py` and `vps_architecture_comparison.py`.
  - States: 31 PRE_CUTOFF_VERSION_SCORED, 52 NO_PRE_CUTOFF_VERSION, 7 NO_CURRENT_LABEL.
  - Effect on 5D: −0.003 [−0.012, 0.006] when the current label is kept where none exists at the cutoff; −0.007 [−0.079, 0.071] when those are set neutral.
- The 05h cutoff is `"2020-12-31"`, inclusive (`05h:36`), which is consistent with `< 2021-01-01`.
- Missing labels get neutral rank 0.5 (`06:87-107`, `:277-302`; D-004). D-004 was chosen knowing that "all 7 unlabelled compounds are negatives" (`DECISIONS.md:107-108`). The project explicitly says AUROC was not the criterion, but the choice was label-aware.

---

## Q6. Network proximity (Hetionet v1.0, 2017)

- **Source.** The Zenodo v1.0.0 archive (`01:10`). Local copies are dated 2026-10-05 01:13. No checksum or version is stored with the file (`TECHNICAL_DEBT.md:609-611`).
- **Edges used for proximity.** GiG (PPI), DaG/DuG/DdG (PD genes) and CbG (drug targets) (`02:78-160`). The underlying sources date from 2016 or earlier, so there is no post-cutoff information. Hetionet's DaG edges include literature co-mention-based DISEASES/DisGeNET associations from before 2017. That is not outcome leakage.
- **Candidate pool and `existing_edge_type`.**
  - `01:41-57` removes compounds with a `CtD` or `CpD` edge to PD. These come from PharmacotherapyDB, 2016, so they are pre-cutoff.
  - In `pd_candidates_full.csv`: 28 CpD, 0 CtD, 1524 `predicted_only`.
  - This removes established PD drugs, which would probably have had both pre- and post-cutoff trials. It shapes the population (continued-investigation endpoint among non-indicated compounds) and lowers base rates. It is not temporal leakage, because the edges are from 2016.
  - The CtD/CpD edges themselves never enter any score.
- **Monte-Carlo noise.** `N_RANDOM = 100` with a seed (`02:45-48`). A 10-seed spread of 0.769–0.783 is documented (`VPS_WEIGHTING_DECISION` §5).

---

## Q7. Cohort selection

Inclusion in the 90-compound pool requires all of the following (`06:172-174`):
- the compound is in `pd_candidates_filtered.csv` (Hetionet 2017 plus the hand exclusion list);
- it has at least one accepted pre-cutoff link in `clinical_maturity_precutoff_clean.csv`;
- (proposed only) it survives feature-role exclusions.

Post-cutoff dependencies:
1. **Discovered by a 2026 query.**
   - CT.gov expansion, Gate 1/2 and study type run on 2026 record content. ChEMBL aliases come from OT 26.09 (`03:113-170`).
   - Trials first posted before the cutoff but edited later (conditions, arms, intervention names, otherNames) can enter or leave. 65 of 177 pre-cutoff records were updated after 2021.
   - Truncation at `pageSize: 20` (`03:78`) can hide pre-cutoff trials for very prolific compounds (Q2.6).
2. **Matching rules tuned after seeing outcomes and scores.**
   - Gate 2 came from top-ranked case studies (`CASE_STUDIES.md:1-17`, `:92-150`; `development_log/CHANGES.md:480-529`, 2026-10-05 afternoon). The rules are generic, but their trigger was the outcome-ranked list.
   - Alias rules (ambiguous-name refusal, `03:126-131`; `MIN_ALIAS_CHARS`, `PROSE_NAME_CHARS`, `CONTROL_TOKENS`, `intervention_matcher.py:80-107`) were added in the same session.
   - Effect: positives changed from 30 of the 141-compound pool to 17 of 90 (`CASE_STUDIES.md:128-140`, `:196-200`).
3. **Exclusion list (`00_exclusion_filter.py:11-26`).**
   - Committed 2026-09-20 16:17 (git `694dbe5`), after stage 03 was committed (2026-09-18, `3ffb585`) and stage 04 (2026-09-19), but before VPS fusion (2026-09-23). It is unchanged since.
   - Its docstring justifies it by scores ("inflate network-proximity and literature scores", `:5-6`), so it was decided after at least feature outputs were seen.
   - Whether labels were inspected cannot be verified: all backups were produced after the filter.
   - Several excluded compounds (caffeine, nicotine, creatine, vitamin D, glutathione) have well-known PD trial histories, so the list may be label-relevant. That cannot be verified from the artefacts.
4. **Role adjudications.**
   - Label exclusions (Q1) were decided after AUROCs were known and audited positives only.
   - Feature-role exclusions are proposed (D-020, `DECISIONS.md:453-531`) with S0–S3 AUROC tables, so any adoption will be label-aware.
5. **Pool design.** Requiring a pre-cutoff PD trial excludes first-time candidates. 24 of 41 ground-truth compounds fall outside the pool (TD-027/TD-035, `TECHNICAL_DEBT.md:429-435`, `:625-640`). This is a scope limit, not leakage.
6. **Label window end.** The window ends at the 2026-10-05 retrieval date, not a protocol date (D-010, `DECISIONS.md:210-236`).

---

## Q8. Evaluation: in-sample selection and nested CV

**In-sample selections on the full labelled cohort:**
- **Grid-searched final weights.** `best_weights` are chosen on all 90 labelled compounds (`06:464-465`). `VPS_grid_*` AUROCs are therefore in-sample. This is flagged `weights_fitted: True` (`06:655-682`) and documented (D-002).
- **The 3-dim variant (no proximity)** was defined "since the ablation showed proximity was net-negative" (`06:7-8`, `:586-591`). That ablation was on the full cohort. The 3d nested-CV figure does not include this dimension-set selection, so it is optimistic.
- **Case studies** used `VPS_grid_3d`, described as "best-performing variant on this cohort" (`CASE_STUDIES.md:3-4`). `06:694-699` prints the top 15 by the in-sample best variant. This is descriptive, but the variant was selected in-sample.
- **Baselines and ablations** (`06:487-527`) are in-sample, using in-sample 4d weights as "full". The figure caption notes this (`07_generate_figures.py:160-179`).
- **Equal weights as primary** (D-002) and **retaining equal weights** (`VPS_WEIGHTING_DECISION_2026-10-19.md` §2–3) were decided after the results were seen, as the docs acknowledge (`DECISIONS.md:49`).
  - Comparing equal vs learned by nested CV on all 90 is a method choice made on the evaluation labels.
  - The chosen method is the zero-parameter one, and it is reported with in-sample CIs, so the optimism is small.
- **Rank convention** (legacy vs midrank, D-024 `:598-628`) and proximity imputation (TD-041) remain undecided. Candidate AUROCs have been computed (0.7754 vs 0.7744), so any switch is label-aware. The effect is negligible.
- **Missing-data rule D-004** was selected with label knowledge, as in Q5. Alternative B was rejected after its ranks were inspected (Lisuride, a negative, ranked first).
- **Label policy P1** was chosen with its AUROC impact computed (Q1).
- **Ranks and imputation are transductive** over all 90 compounds (label-free): `06:220`, `:257-303`; `vps_validation_experiments.py:212-214`. This is acceptable for unsupervised transforms.

**Nested CV is properly nested:**
- In `06:446-462`, weights are chosen on `train_df` and scored on `test_df`. This is the leakage fix of 2026-10-05 (TD-003, `CHANGES.md:554-571`). It uses a single 5-fold split (TD-036).
- `vps_evaluation_report.py:69-81` repeats nested CV 20 times with `fusion._best_weights_on(v.iloc[tr])`.
- `vps_validation_experiments.py:171-192`: the outer split, then the inner folds of the training rows only (`:181-187`).
- In `fit_model` (`:247-283`), the simplex, shrinkage λ and logistic C are chosen by inner CV on outer-train rows. `StandardScaler` is fitted on training rows only (`:269-271`). OOF scores are pooled per repeat (`:286-305`).
- `vps_weighting_experimental.py:1-20` uses the same protocol.
- Grouped folds (StratifiedGroupKFold on shared-trial components) are available (`:219-240`).
- Caveat: the feature *sets*, dimension definitions and variants compared inside CV were themselves fixed after full-cohort results.

---

## Q9. Existing time-bounded sensitivity analyses

All are on the **same 90 compounds and 14 positives**, using the published labels:
- `n: 90`, `positives: 14` in each JSON;
- every script builds labels through `vps_validation_experiments.build` (`:102-105`);
- seed 20261019, 2000 bootstrap draws.

| Analysis | Script | Output | Recorded result (AUROC [95% CI]; Δ paired) |
|---|---|---|---|
| Literature bounded to pdat ≤ 2020-12-31 (04p primary records; shared-author components; no citations) | `vps_literature_cutoff_sensitivity.py` (+ `04p_literature_provenance.py`) | `data/_runs/literature_cutoff_20261019/literature_cutoff_sensitivity.{csv,json}` | 5D 0.775 → 0.757 (Δ −0.019 [−0.067, 0.030]) for the count; 0.748 (Δ −0.027 [−0.073, 0.016]) for components. 4D 0.700 → 0.681. Spearman with published literature 0.85 / 0.87 |
| Safety label at cutoff (DailyMed versions) | `05h_safety_label_history.py`; evaluated in the same literature script | same CSV, rows "safety = label at cutoff …" | 5D 0.773 (Δ −0.003 [−0.012, 0.006]) when the current label is kept where unknown; 0.768 (Δ −0.007 [−0.079, 0.071]) when set neutral. 31 of 83 labels scored at the cutoff |
| Molecular direct component at OT 20.11 | `vps_molecular_snapshot_sensitivity.py` | `data/_runs/molecular_snapshot_20261019/molecular_snapshot_sensitivity.json` | 5D with the direct component: 0.759 (26.09) vs 0.672 (20.11), Δ −0.087 [−0.169, −0.011]. Direct component alone 0.622 → 0.460 |
| Full molecular at 20.11 (+ UniProt 2020-11 Reactome, + ChEMBL 2020-06 targets) | `vps_molecular_historical.py` | `data/_runs/molecular_historical_20261020/molecular_historical.json`, `stdout.log` | 5D 0.690 (Δ −0.086 [−0.186, 0.020]). With ChEMBL 2020-06: 0.704 (Δ −0.071 [−0.173, 0.030]). Molecular alone 0.516. TD-042 variants are unchanged (Δ ≈ 0) |
| Architectures (B bounded literature+safety, C 4D, dated molecular, all-bounded) | `vps_architecture_comparison.py` | `data/_runs/vps_architecture_4h_20261020/architecture_comparison.csv` (also `vps_architecture_20261020`) | A 0.775; B 0.752; C 0.700; C-bounded 0.679; A-dated 0.704; **B+D-dated (all bounded except clinical phase fields) 0.686 [0.544, 0.821]**, Δ vs A −0.089 [−0.209, 0.027] |
| Learned vs equal on bounded sets | `vps_weighting_experimental.py` | `data/_runs/vps_weighting_experimental_20261020/weighting_experimental.csv` | Equal-weight OOF: bounded 4D 0.679, bounded trio 0.670, TD-042 bounded 5D 0.681. Learned weights never beat equal |
| Cutoff-bounded pair (proximity + clinical) | `vps_validation_experiments.py` / literature script | `literature_cutoff_sensitivity.csv` | 0.653 [0.480, 0.808] |
| Evidence overlap (papers reporting label trials) | `vps_evidence_overlap.py` | `data/_runs/evidence_overlap_20261020/evidence_overlap.json` | 0 compounds whose sample cites a label NCT (lower bound); 20 cite a feature trial |

Caveats:
- No analysis bounds the clinical phase or status fields, the CT.gov record content used for matching, Semantic Scholar citations (the bounded literature drops them), or the OT top-300 truncation by overall score.
- The 20.11 comparison mixes temporal change with method change (EFO vs MONDO IDs, new datatypes) (`TECHNICAL_DEBT.md:583-590`).

---

## Q10. Per-dimension provenance and reconstruction feasibility

| Dimension | Source snapshot / version | Publication or effective date field | Retrieval date (where recorded) | Earliest info date | Possible post-cutoff info | Historical reconstruction |
|---|---|---|---|---|---|---|
| **Proximity** | Hetionet v1.0.0 (Zenodo 268568); GiG/DaG/DuG/DdG/CbG (`01:10`, `02:78-160`) | none per edge; release 2017 | accessed 2026-10-05 (`docs/REFERENCES.md:118`); file mtime 2026-10-05 01:13; no checksum | sources ≤ 2016 | none (only 2016-era sources); integrity unverified without a checksum | **Feasible / already historical.** Pin the Zenodo md5 |
| **Clinical maturity** | CT.gov API v2 live; Gate 1/2; study-type filter; ChEMBL aliases via OT 26.09 | `studyFirstPostDateStruct` (pool and cutoff); phase from `designModule.phases[0]` with no date (`03:284-287`) | 2026-10-05 query (D-010; mtimes 15:40/15:44); pre-cutoff record cache `retrieved_utc` 2026-10-15 | first_posted 2000-02-25 | yes: phase, status, conditions and interventions in the current record; 65/177 updated ≥ 2021; aliases from 2026 ChEMBL; 20-result cap | **Feasible to partial.** CT.gov keeps per-record version history (website "record history"), so phase and arms as of 2020-12-31 can be recovered per NCT, but not in bulk through the v2 API. Alias sets can be rebuilt from ChEMBL 27/28 (2020). The 2026 search expansion cannot be replayed |
| **Literature** | PubMed live ESearch (retmax 30, recency order) + Semantic Scholar live citations (`04:45`, `:59-78`, `:123-178`) | pdat is available but **not used** in stage 04; 04p records `earliest_pub_date` and `cutoff_status` | stage 04 not recorded per record (outputs 2026-10-05); 04p `retrieved_utc` 2026-10-19 | 1800/01/01 lower bound in the 04p bounded query | yes: about 43–67% of samples are post-cutoff; citing papers are current | **Partial.** The pdat bound is feasible (04p already done). Citation graph limited to pre-cutoff citing papers: feasible by filtering S2 citing-paper years (not done). Exact 2020 PubMed indexing state: infeasible |
| **Safety** | openFDA `/drug/label.json`, current label, `limit=1` (`05:24-32`) | `effective_time` recorded per compound (`05:45-47`) | v2 re-query 2026-10-14/15 (D-003; mtime 2026-10-14); 05h 2026-10-19/20 | label effective 2018 … 2026 | yes: 78/83 labels effective after 2020 | **Partial.** 05h recovers the at-cutoff version for 31/83 set IDs. 52 set IDs start after 2020; their predecessors need other set IDs or products (not attempted). 7 have no label |
| **Molecular** | Open Targets API v26.9 / data 26.09; ChEMBL MoA current; Reactome via OT target index (`molecular_agent.py:52-53`, `:90`) | none per evidence item; release 26.09 | 2026-10-05 (docstring, `REFERENCES.md:116`); `agent_version` unrecorded | not tracked | yes: 2026 association evidence; current MoA; top-300 module ordered by an overall score that includes `clinical`/`literature` | **Feasible / partly done.** OT 20.11 files, UniProt 2020-11-10 and ChEMBL 2020-06 are cached (`data/cache/opentargets_20.11/`); `vps_molecular_historical.py` rebuilt it. Remaining gaps: the method differs between releases, and the module is still ranked by an overall score that includes `known_drug`/`literature` (should re-rank by allowed datatypes before the top-300 cut) |
| **Labels** (for reference) | CT.gov v2, 2026-10-05; `label_role_exclusions.csv` (owner 2026-10-14) | `studyFirstPostDateStruct` ≥ 2021-01-01 | 2026-10-05 | 2021-01-13 … 2026-09-08 | n/a (outcome); 20-result cap may hide trials (Ioflupane I 123) | Fixed end date needed (draft policy `CASE_STUDIES.md:540-546`) |

---

## Key findings (ranked)

1. **Literature is the most direct leak.** It has no date bound (`04:257`), and the sample is the 30 most recent papers. Positives' samples are 67% post-cutoff vs 43% for negatives. Measured AUROC effect is small (−0.02 to −0.03).
2. **Molecular is current-snapshot, and its exclusion of `clinical`/`literature` is incomplete.** The datatypes are removed from scoring but still decide the top-300 module through OT's overall-score ordering (`molecular_agent.py:683-693`, `:728-760`). Dating the molecular inputs removes its whole 5D-over-4D gain (0.775 → about 0.69–0.70).
3. **Clinical phase and the matching fields come from 2026 records.** 65 of 177 pre-cutoff trials were updated after the cutoff. No analysis bounds them.
4. **Safety uses current labels.** 05h is diagnostic only, and its measured effect is negligible.
5. **Analytic choices were label-aware**, which the project partly acknowledges: label policy P1, Gate-2 triggered by top-ranked positives, D-004, the 3d variant, and the equal-weight decision. Each is likely small or conservative, but none was pre-registered.
6. **New issue: no pagination with `pageSize: 20`** (`03:78`). One pool compound (Ioflupane I 123) hit the cap with 0 post-cutoff trials, so its label of 0 may be an artefact.
7. **Nested CV is correctly nested in all three implementations.** Grid-searched AUROCs reported from `06` remain in-sample and are labelled as such.
