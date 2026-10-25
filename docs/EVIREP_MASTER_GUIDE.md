# EviRep master guide: from source code to final output

*Written 2026-10-21 from the code and data in this repository. Line numbers refer to the current working tree. When the docs and the code disagree, this guide says what the **code** does.*

---

## Quick reference (one page)

| Question | Answer |
|---|---|
| **What does EviRep ask?** | Among existing drugs that were already tested in Parkinson's disease (PD) before 2021, which ones look most worth further investigation, judged only on evidence available before 2021? |
| **Inputs** | Hetionet knowledge graph, ClinicalTrials.gov, PubMed + Semantic Scholar, openFDA labels, Open Targets / ChEMBL / Reactome. |
| **What comes out?** | `data/vps_scores_v2.csv`: 90 compounds, each with 5 percentile ranks and a score `VPS_equal_5d`. `data/vps_evaluation_report.json` holds the metrics. |
| **What is VPS?** | "Validated Plausibility Score". Here it is simply the **mean of five percentile ranks**, one per evidence dimension (`06_vps_fusion.py:598-599`). |
| **Approved result** | Run `adopted-20261015T015501Z-06`: AUROC **0.775** [0.656, 0.881], AUPRC **0.424** (chance 0.156), 90 compounds = 14 positives + 76 negatives. |
| **What the label means** | 1 = a qualifying PD interventional trial naming the drug was **first posted on or after 2021-01-01**. It measures *continued trial activity*, **not efficacy** (D-010, `DECISIONS.md:210-234`). |
| **Can / cannot conclude** | It orders compounds better than chance against later PD trial activity. It **cannot** show that any drug works, and the score is not a probability. |
| **Start the UI** | `./venv/bin/python ui/server.py` → http://127.0.0.1:8765/ |
| **Verify the score** | `./venv/bin/python scripts/vps_verify.py` (read-only). |

```
 Hetionet ─01─► candidates ─00─► filtered (1,483)
                                 │
                 ┌───────────────┼──────────────────────────────┐
                 ▼               ▼                              │
           02 proximity    03 ClinicalTrials.gov ─03c─► pre-2021 trials (FEATURE, defines the 90)
                                               └──────► post-2021 trials (LABEL, 14 positives)
                                 │
          04 literature   05 safety label   08 molecular (all keyed on the 90)
                 └──────┬─────────┴─────────────┘
                        ▼
              06 fusion: 5 percentile ranks → mean = VPS_equal_5d → vps_scores_v2.csv
                        ▼
              eval: AUROC / AUPRC / bootstrap CIs → vps_evaluation_report.json
                        ▼
     agents 10a–10h (diagnostics and annotations only; none changes the score) → UI
```

---

## A. The project in one page

**The problem.** Whether a repurposed drug truly helps patients is rarely known, so EviRep uses a **checkable proxy**. It freezes the evidence on 1 January 2021, scores each candidate with only that evidence, and asks whether the higher-ranked drugs were more often the ones that later got *new* PD trials.

**VPS in this code.** Each of five raw measurements becomes a percentile rank between 0 and 1 within the 90-compound pool, where higher means more favourable. The five ranks are averaged with weights of 0.2.

**What it can and cannot claim.**
- It **can** say the ranking beats chance against a later-trial proxy (AUROC 0.775; CI excludes 0.5).
- It **cannot** say any drug works.
- It **cannot** generalise beyond drugs that already had a pre-2021 PD trial.

---

## B. The data journey

The **authoritative** files are marked ★. The UI and the evaluation trust these; other CSVs are intermediates or diagnostics.

| # | Input | Code | Transformation | Output | Next consumer |
|---|---|---|---|---|---|
| 1 | Hetionet v1.0 zip (Zenodo) | `01_get_pd_candidates.py:14-57` | keep `kind=="Compound"`; drop compounds with a CpD (palliates) edge to PD `DOID:14330` | `pd_candidates.csv` (1,524) | 00 |
| 2 | `pd_candidates.csv` | `00_exclusion_filter.py:11-33` | drop 41 nutrients/vitamins/electrolytes by exact name | ★`pd_candidates_filtered.csv` (1,483) | 02, 03, 06 |
| 3 | filtered list + CT.gov API | `03_clinicaltrials_groundtruth.py:202-344` | search trials per compound; PD-condition gate; intervention match; split at 2021-01-01 | `clinical_maturity_precutoff.csv` (207 links), `ground_truth_postcutoff.csv` (67), `clinicaltrials_match_audit.csv` (951) | 03c |
| 4 | both trial files | `check_studytype.py`, `filter_by_studytype.py:13-31` | keep INTERVENTIONAL trials with a DRUG/BIOLOGICAL intervention | ★`clinical_maturity_precutoff_clean.csv` (195 links, **90 compounds**), ★`ground_truth_postcutoff_clean.csv` (57 links, 41 compounds) | 04, 05, 08, 06 |
| 5 | Hetionet PPI + targets | `02_network_proximity.py` | z-score of target-to-PD-gene distance | ★`network_proximity.csv` | 06 |
| 6 | PubMed / Semantic Scholar | `04_literature_independence.py` | independent paper clusters | ★`literature_independence.csv` | 06 |
| 7 | openFDA labels | `05_safety_signal.py` | serious-term count, boxed warning | ★`safety_signal.csv` | 06 |
| 8 | Open Targets / ChEMBL / Reactome | `08_molecular_pathway.py` + `molecular_agent.py` | 0.6·direct + 0.4·pathway | ★`molecular_pathway.csv`, `molecular_pathway_evidence.jsonl` | 06, agents |
| 9 | all ★ above + `label_role_exclusions.csv` | `06_vps_fusion.py` | pool, ranks, imputation, mean, labels | ★`vps_scores_v2.csv` | eval, 07, agents, UI |
| 10 | scores + labels | `vps_evaluation_report.py` | AUROC, AUPRC, bootstrap CIs | ★`vps_evaluation_report.json` | UI Validation |

All ★ score-side files are in `PROTECTED_ARTEFACTS` (`ui/live_runs.py:31-38`), so the dashboard can never rewrite them.

---

## C. Pipeline stages

The registry is the `STAGES` list in `ui/server.py:57`. `scripts/run_stage.py` loads it from there (`load_stages`, `:82-87`), so **this list is the single source of truth for dependencies**. To print every stage's inputs, outputs and dependencies, see section I.

### C1. Score-producing stages

**01 · Candidate extraction** (`scripts/01_get_pd_candidates.py`)
- **Purpose:** keep only drugs that are *not already* PD treatments.
- **Operation:** `fetch_and_extract_hetionet()` (:14); PD edges with metaedge in `["CtD","CpD"]` (:41); keep `predicted_only` (:47).
- **Output:** `pd_candidates.csv` (1,524 of 1,552). Consumer: stage 00.
- **Note:** the data has **no CtD edges to PD**, only 28 CpD (L‑DOPA, pramipexole, …). Leaving known PD drugs in would inflate the evaluation.

**00 · Exclusion filter** (`scripts/00_exclusion_filter.py`)
- Exact-name removal of 41 "mechanistically non-specific" substances (`EXCLUSION_LIST`, :11-26) → 1,483. **00 runs after 01** despite its number.
- The list is hand-written (Caffeine and Nicotine are "borderline"); 6 entries match nothing.

**03 · ClinicalTrials.gov ground truth** (`scripts/03_clinicaltrials_groundtruth.py`)
- **Purpose:** produces both a **feature** (pre-2021 trials) and the **labels** (post-2021 trials).
- **Operation, in order:**
  1. `build_alias_map` (:136-193) fetches ChEMBL synonyms and trade names; names shared with another compound are blocked as ambiguous.
  2. `search_trials` (:68-90) runs a paginated v2 API search `query.intr=<name>`, `query.cond="Parkinson Disease"` (:93-133). It retries 4× (:60-61). More than 50 pages counts as a failure, not a silent truncation.
  3. **Gate 1** `is_actually_pd` (:195): a condition string must contain "parkinson".
  4. **Gate 2** `intervention_matcher.match_trial` (:250-387): see section E.
  5. Split on `first_posted < "2021-01-01"` (:53, :323) → pre; otherwise → post.
  6. Any failed search aborts the stage before writing (:337-341).
- **Output:** pre/post link files plus a full audit of every decision (MATCHED 274, NO_MATCH 289, CONDITION_REJECTED 352, UNVERIFIABLE 36).
- **Significance:** it defines the pool, the clinical dimension *and* the answer key.
- ⚠ **The saved files predate the pagination fix (E-056):** they come from a 2026-10-05 run with 20 results per page and no paging. The current code would add **Dopamine**. The rebuild is an owner decision.

**03c · Study-type filter** (`scripts/check_studytype.py` → `scripts/filter_by_studytype.py`)
- **Operation:** fetches `studyType` and intervention types for all 252 NCT IDs. It aborts on any fetch error (:44-48). `keep_trial` (:13-17) keeps `INTERVENTIONAL` trials with a `DRUG` or `BIOLOGICAL` intervention. 22 NCTs are dropped.
- **Side effects:**
  - **Mannitol** leaves the pool (91 → 90): its only trial is a DIETARY_SUPPLEMENT.
  - **Lithium** loses its three post-2021 trials (typed DIETARY_SUPPLEMENT), so it stays label 0 (B‑004, open).

**02 · Network proximity** (`scripts/02_network_proximity.py`). See D1.

**04 · Literature independence** (`scripts/04_literature_independence.py`). See D3.

**05 · Safety signal** (`scripts/05_safety_signal.py`). See D4.

**08 · Molecular / pathway** (`scripts/08_molecular_pathway.py`, `scripts/molecular_agent.py`). See D5. It has `timeout_s` 14400; responses are cached in `data/cache/molecular/`.

**06 · VPS fusion** (`scripts/06_vps_fusion.py`). See section F.
- Besides `VPS_equal_5d` it also writes:
  - `VPS_equal` (4 dimensions);
  - grid-searched variants with 5-fold nested CV (`cv_grid_search_weights`, :423-480);
  - baselines (:487-501) and ablations (:508-527).
- When it runs through the runner, its outputs go to a staging folder and are **published only if `validate_vps` independently recomputes them** (`run_stage.py:483-512`, :624-626).

**eval · Evaluation report** (`scripts/vps_evaluation_report.py`)
- Computes AUROC, AUPRC, 2,000-resample bootstrap CIs (seed 42, `:39`), the paired 5D-vs-4D comparison and repeated nested CV.
- It depends on 10e only to count trials shared across compounds (section 8 of the report, :178-190).

**07 · Figures** (`scripts/07_generate_figures.py`): Figure 1 (AUROC comparison), Figure 2 (ablation), Figure 3 (Droxidopa literature graph).

### C2. Helper and audit stages (not in the score)

| Stage | Script | What it does | Used by |
|---|---|---|---|
| 04b | `04b_export_literature_graph.py` | Rebuilds one compound's paper graph and refuses to write if the counts differ from stage 04 (:132-142) | Figure 3 |
| 04p | `04p_literature_provenance.py` | Re-queries PubMed (with and without a ≤2020 date bound); dates every paper PRE/POST cutoff (`cutoff_status`, :149) | 10a-all, 10g, sensitivity scripts |
| 05h | `05h_safety_label_history.py` | Finds the drug label version in force on 2020-12-31 via DailyMed (`version_at`, :95) | 10f, sensitivity scripts |
| diag | `check_intervention_match.py` | Checks that each trial's intervention list really names the compound: 244 MATCHED, 1 partial, 7 NAME_NOT_FOUND | nothing (review aid) |

### C3. The eight agents, plus the review stage

**No agent output enters the score.** `06_vps_fusion.py:61-85` reads only the stage files listed in section B. `tests/test_vps_correctness.py:155-169` (`test_stage06_reads_only_registered_inputs`) asserts that stage 06 mentions no agent output file.

The UI's "Feeds the score" badge (`ui/server.py:1910-1911`) only means the agent is *paired with* a scoring stage. The more precise wording is in `AGENT_VPS_ROLE` (`ui/server.py:915-924`).

| Agent | Paired stage | Kind | What it actually does | Current output |
|---|---|---|---|---|
| 10a Literature Credibility | – | diagnostic | Rates **study design** from PubMed publication types (tier A = RCT/meta-analysis … D = editorial; :75-82). Efficacy is never assessed. | 89/90 compounds, 4,191 papers |
| 10b Molecular run record | 08 | validates a score dimension | Offline re-validation of stage 08 records; CSV vs JSONL scores must agree within 1e-6 | 90 valid, 16 without targets |
| 10c Clinical Evidence | 03/03c | diagnostic on a score dimension | Registry details per trial, automated trial roles, 35 hand-adjudicated links take precedence | 177 trials, 195 links |
| 10d Conflict & Context | – | diagnostic | Compares directional claims (curated, label, molecular, trial) and classifies disagreements | 72 of 91 INSUFFICIENT; Donepezil CONTEXT_DIFFERENCE |
| 10e Reproducibility | – | diagnostic | Is a finding replicated by independent primary studies? (union-find clusters, :129) | 14 findings, 1 REPLICATED |
| 10f Safety Evidence | 05 | diagnostic on a score dimension | Label excerpt, label at cutoff (from 05h), FAERS counts (not incidence) | labels 83/90; at cutoff 31 scored |
| 10g Evidence Independence | 04 | diagnostic | Checks D1–D5 for the same study counted twice | e.g. D2 found for 20 compounds |
| 10h Completeness & Gap | – | annotation | 12 evidence domains × 90 compounds; MEASURED / ABSENT_AT_SOURCE / NOT_COMPUTED …; cross-checks stage 06's missingness | 361 gaps |
| review | 10c | human work queue | Lists the trial-role links needing a human; writes plain CSVs, no envelope | 37 flagged, **28 unresolved** |

All agents share an output **envelope** (`scripts/agent_contract.py:40-41`): `run_status`, `generated_utc`, `inputs` (md5 per file), `coverage`, `limitations` and `diagnostics`.
- `run_status` (:87-97) is SUCCESS, PARTIAL, NO_EVIDENCE or FAILED.
- **SUCCESS means every unit was processed. It does not mean the evidence is good or scientifically valid.**

---

## D. The five scoring dimensions

All five become percentile ranks in `build_standardized_scores` (`06_vps_fusion.py:271-303`). Donepezil is the running example.

### D1. Network proximity (stage 02)
- **Idea:** do the drug's protein targets sit close to PD genes in the protein–protein interaction network?
- **Rule:**
  - `d_real` = mean over targets of each target's shortest distance to its nearest PD gene (`calculate_real_distance`, :263).
  - 100 degree-matched random target sets (`N_RANDOM`, :45; seed 42) give μ and σ.
  - **z = (d_real − μ)/σ**, set to 0 if σ = 0 (:601-610).
- **Direction:** more negative = closer. The rank is inverted (`06:274`), so closer scores higher.
- **Missing:** no targets or no reachable distance → no row → stage 06 uses the **pool median** (2 compounds: Deferiprone, Trimethobenzamide).
- **Bias:** PD genes come from Hetionet 2017 (637, TD-008). 100 draws is a "quick test" setting (TD-011). The minimum of 10 draws and the σ = 0 rule are **undocumented**.
- **Example:** Donepezil d_real 1.5, μ 1.573, σ 0.203 → z −0.361 → `r_proximity` 0.411, its weakest dimension.

### D2. Clinical maturity (stages 03 → 03c → 06)
- **Idea:** how far did the drug's pre-2021 PD trials get?
- **Rule:** `PHASE_RANK` (`06:110`): NA 0, EARLY_PHASE1 1, PHASE1 2, PHASE2 3, PHASE3 4, PHASE4 5. Take `max_phase_rank` over accepted pre-cutoff trials (`build_clinical_maturity`, :112-118). The trial count is not ranked.
- **Missing:** impossible; the pool requires at least one such trial.
- **Bias:** phase is not quality (a terminated Phase 3 still scores 4). Only `phases[0]` is stored (`03:309`). Shared trials raise every compound they name (TD-023).
- **Example:** Donepezil, 11 trials, max PHASE4 = 5. **23 compounds tie** at 5, so each gets average position 79 / 90 = **0.878**.

### D3. Literature independence (stage 04)
- **Idea:** how many *independent research groups* published on drug + PD?
- **Rule:**
  - Take up to 30 PubMed papers (`search_pmids`, :59).
  - Link two papers if they share an author string (`Last_Initials`) or one cites the other (Semantic Scholar) (`build_dependency_graph`, :181-220).
  - `effective_independent_count` = number of connected components; only this is ranked (`06:276`).
- **Missing:** 0 papers is a measured 0.
- **Bias:** **not cutoff-bounded** (TD-021); all 30 of Donepezil's sampled papers are post-2020 (04p). Author-name collisions can merge groups (undocumented). The 30-paper cap saturates popular drugs. A bounded version changes AUROC by −0.019.
- **Example:** Donepezil, 30 papers forming 25 components → `r_literature` 1.0.

### D4. Safety (stage 05; risk formula in 06)
- **Idea:** how alarming is the current FDA label?
- **Rule:**
  - `serious_term_count` = substring count of 8 terms (`05:21`) over the warning fields.
  - **Risk = serious_term_count + 5 × boxed_warning** (`06:278-280`), inverted so lower risk scores higher.
  - **The ×5 has no documented justification.**
- **Missing:** no label → rank **0.5** (D-004), never "safest" (7 compounds). Ranks are computed over the 83 labelled compounds.
- **Bias:** the current label, not the 2020 one (TD-022; the 05h test shows −0.003 AUROC). Substring matching counts "deaths" and ignores negation.
- **Example:** Donepezil, 2 terms, no boxed warning → risk 2 → `r_safety` 0.645.

### D5. Molecular plausibility (stage 08)
- **Idea:** is there non-clinical evidence linking the drug's targets to PD?
- **Rule:** **score = 0.6 × direct + 0.4 × pathway** (`molecular_agent.py:959`, :1000-1003).
  - `direct` = max Open Targets target–PD score over *allowed* datatypes (genetic, animal model, pathway, somatic, expression). `clinical` and `literature` are excluded to avoid leakage.
  - `pathway` = share of the target's Reactome pathways containing at least one gene from a 300-gene PD module.
  - The weights are set a priori.
- **Missing:** no ChEMBL target → rank **0.5** (16 compounds, `06:286-292`).
- **Open issue TD‑042 (owner decision):** the pathway step can count the drug's *own* target as the shared PD gene, double-counting direct evidence (Donepezil's ACHE). The fix `td042_v1` gives 5D AUROC 0.699 and is **not approved**. The data is also not cutoff-bounded (TD-006).
- **Example:** Donepezil → ACHE: direct 0.581, pathway 3/3 → score 0.748 → `r_molecular` 0.932 (0.348 under TD-042).

---

## E. Ground truth and the 90-compound cohort

### The funnel (verified counts)

| Step | Count |
|---|---|
| Hetionet compounds | 1,552 |
| minus 28 already palliating PD (CpD) | 1,524 |
| minus 41 exclusion-list substances | 1,483 |
| compounds with ≥1 accepted pre-2021 PD trial (stage 03) | 91 |
| minus Mannitol (non-drug study type, 03c) | **90 = the pool** |
| pool compounds with an accepted post-2021 trial | 17 |
| minus 3 owner-approved label exclusions (TD-032) | **14 positives**; 90 − 14 = **76 negatives** |

**Pool rule:** the pool is the set of compounds in the pre-cutoff clean file, intersected with the filtered list (`merge_dimensions`, `06:172-174`).
**Label rule:** `label = compound in post-cutoff clean file` (`build_labels`, `06:338-342`). There is **no date logic in 06**; the 2021 split happens only in stage 03 (:323).

**The 14 positives:** Acetylcysteine, Atomoxetine, Donepezil, Galantamine, Levetiracetam, Lidocaine, Melatonin, Methylphenidate, Mirabegron, Pyridostigmine, Quetiapine, Rifaximin, Terazosin, Varenicline.

**The three label exclusions** (`data/label_role_exclusions.csv`, approved by the owner on 2026-10-14):
- Dexmedetomidine and Remifentanil: anaesthesia during DBS surgery.
- Clozapine: actuator of a gene therapy.

In each case the drug was in the trial but was not being tested *for PD*.

### Trial matching (`scripts/intervention_matcher.py`, rules in `docs/INTERVENTION_MATCHING.md`)
- **Pass 1, exact normalised match** (:306-321) on the compound name or ChEMBL synonym/trade name, in intervention names or otherNames.
- **Pass 2, whole-token match** (:323-347), using the compound's own name only. Synonyms are too noisy, e.g. "Medopa" is listed under Dopamine.
- **Control arms are skipped** (`is_control_intervention`, :201-213). Example: Placebo listing "Mannitol" as an otherName.
- **Excluded:** aliases under 4 characters, aliases shared with another compound, and class, prodrug or description-text matches.
- **Outcomes:** MATCHED / NO_MATCH / UNVERIFIABLE (e.g. observational trials with no interventions listed) / API_FAILURE.

### Human adjudication
- Label exclusions (above) are applied.
- **D‑020** (35 shared trial links, per-link table `data/feature_trial_roles_td038.csv`) is **proposed, not applied**: `data/feature_role_exclusions.csv` does not exist, so `apply_feature_exclusions` (`06:128-149`) does nothing.
- The review worklist has 28 unresolved links. The "28" in the UI is **hard-coded** text (`ui/server.py:918`); it matches the current CSV but is not computed from it.
- Lidocaine is kept positive (D-011, confirmed). **Galantamine remains UNRESOLVED** (D-011).

### Why a negative is not "ineffective"
A 0 means only that no qualifying trial was *found*. Possible reasons:
- nobody tried it;
- the registry typed it differently (Lithium);
- the trial is outside ClinicalTrials.gov;
- the paging limit hid it (E‑056, Dopamine).

Equally, a positive trial may fail. **The label measures research interest, not benefit** (D-001, `DECISIONS.md:25-27`).

### Threats to validity
- **Selection bias:** only "previously tried" drugs are ranked; 24 of 41 ground-truth compounds are outside the pool (TD-035).
- **False matches:** combination products count for both drugs; shared trials inflate both feature and label.
- **Temporal leakage:** literature, label and molecular data are current, not frozen (TD-021/022/006).
- **Small numbers:** 14 positives.
- **NOT ESTABLISHED FROM THE REPOSITORY:** why 2021-01-01 was chosen. It is only stated as a constant (README:7). Also the exact date and time of the 2026-10-05 stage-03 query.

---

## F. The mathematics

### F1. Ranks (`percentile_rank`, `06:257-269`)
`rank = series.rank(pct=True, method="average")`: each value's average position divided by the number of non-missing values. Ties share the average position. Inverted dimensions use `1 − rank`. This is the "legacy" convention; an alternative "midrank" formula `(rank − 0.5)/n` exists but is not approved.

**Hypothetical example** (illustrative numbers, not real data) with 4 drugs and clinical phases [5, 3, 3, 1]:
- Positions are 4, 2.5, 2.5, 1.
- Ranks are 1.0, 0.625, 0.625, 0.25.

### F2. Missing values

| Dimension | Missing handling | Flag |
|---|---|---|
| proximity / clinical / literature | pool median raw value, then ranked | `dimensions_imputed` — **not present** in the approved file (see G) |
| safety (no label) | rank 0.5 | `safety_label_missing`, `dimensions_missing` |
| molecular (no target) | rank 0.5 | `molecular_evidence_missing`, `dimensions_missing` |

### F3. The score
`VPS_equal_5d = 0.2·(r_proximity + r_clinical + r_literature + r_safety + r_molecular)` (`06:598-599`).

**Real example, Donepezil** (saved values):
(0.411 + 0.878 + 1.000 + 0.645 + 0.932)/5 = **0.773** → rank 1 of 90, label 1.

The tuned-weight variants score lower on held-out data than on the data they were tuned on:

| Variant | In-sample AUROC | Held-out AUROC |
|---|---|---|
| 5D | 0.774 | 0.639 |
| 4D | 0.725 | 0.607 |
| 3D | 0.720 | 0.584 |

That gap is overfitting, which is why equal weights are the approved score.

### F4. Metrics (`vps_evaluation_report.py`)
- **AUROC** (`sklearn roc_auc_score`): the probability that a randomly chosen positive is ranked above a randomly chosen negative. 0.5 = chance, 1.0 = perfect. **0.775 is not "a 77.5% chance the drug works"**: it is a statement about *ordering* against a *trial-activity* label.
- **AUPRC** (`average_precision_score`, :123): precision averaged over the ranking. Its chance level equals **prevalence** = 14/90 = 0.156. Observed 0.424 ≈ 2.7× chance. In the top 10, 5 compounds are positives (chance ≈ 1.6).
- **95% CIs** (`boot_metric`, :55-66): 2,000 resamples of the 90 rows with replacement (not stratified; seed 42), taking the 2.5th and 97.5th percentiles. AUROC [0.656, 0.881]; AUPRC [0.226, 0.679]. The intervals are wide because of the 14 positives.
- **5D vs 4D:** +0.075, CI [−0.025, 0.176]. **Not significant**, so the molecular dimension's added value is unproven.
- **Baselines** (report `baselines`): proximity only 0.578; publication count 0.629; naive raw sum 0.641.
- **Calibration** is explicitly "not applicable": VPS is not a probability (`calibration`, :193-197).

---

## G. Reproducibility and scientific integrity

**Confirmed facts**
- The approved score is the manifest record `stages["06"].last_success = adopted-20261015T015501Z-06` (status **ADOPTED**).
  - ADOPTED = the files existed before run tracking; they were fingerprinted (06 independently verified) but not re-run. There is **no code fingerprint**, so code drift is undetectable for 8 adopted stages.
- `scripts/vps_verify.py` rebuilds `r_*`, `VPS_equal` and `VPS_equal_5d`, the pool and the labels **from the raw stage CSVs**, without importing stage 06 (:4-7). It compares them with tolerance 1e-9 (`compare`, :132-161). Result today: MATCH, max difference 2.2e-16.
  - It does **not** check grid variants, baselines, AUROC values, raw columns, or whether the raw CSVs are themselves correct.
- `data/run_manifest.json` records each run's inputs and outputs as **md5 + size + mtime** (`fingerprint`, `run_stage.py:90-104`), the script md5, the status and the log (`data/_runs/<run_id>/log.txt`). `status()` (:295-399) marks a stage STALE when a fingerprinted input changes; staleness propagates downstream.
- **Failure safety:** before a stage runs, its outputs are backed up to `previous/`. On failure they are restored byte-identical. Stage 06 writes to a staging folder and publishes only after `validate_vps` passes.

**Why a from-source run can differ.** `vps_verify` reuses the *saved* raw CSVs. Re-running 02–08 re-queries live APIs that change over time: new trials (and the pagination fix adds Dopamine), new papers, updated labels, and new Open Targets releases (on 20.11 the 5D advantage disappears, TD-033). So "recomputes identically" ≠ "reproducible from source".

**Documented discrepancies (read the code, not the doc)**
- The approved CSV has **no `dimensions_imputed` column**. It was written 2026-10-14, before that code change (`vps_verify.py:20-21`).
  - The two median-imputed proximity values (Deferiprone, Trimethobenzamide) are therefore unflagged. Their `n_dimensions_measured` counts proximity as measured.
  - `docs/VPS_EVALUATION.md:80` ("now flagged") describes what a re-run would produce, not the approved file.
- README TD-020 (:178-183) quotes 17 positives and a 5D−4D difference of +0.059. These are historical; the current values are 14 and +0.075.
- `data/bootstrap_ci_equal5d_vs_4d.csv` is read by eval but **produced by no registry stage**. It was made by running `scripts/bootstrap_auroc_ci.py` by hand.
- The eval record never fingerprinted `data/reproducibility.json`. That is why the dashboard says "not verifiable".

**Open owner decisions:** TD-042 (candidate in `data/_candidates/td042_v1/`, unpublished); the E-056 stage-03 rebuild; B-004 Lithium; Galantamine; the 28 review links; D-020 feature exclusions; temporal validity; re-running `eval` to fingerprint its input.

**Protected outputs.** 19 files (`PROTECTED_ARTEFACTS`) can be rewritten only by the owner from the command line. The dashboard REFUSES stages 01, 00, 02, 03, 03c, 04, 05, 08, 06, 04b and eval.

---

## H. The UI and live execution

**Start the app:** `./venv/bin/python ui/server.py` (standard library only; loopback only; `--port 8765`, `--root .`). Open http://127.0.0.1:8765/.

**Navigation** (`ui/app.js` `VIEWS` :1561, sections :1565):

| Section | Shows | API |
|---|---|---|
| Overview | purpose, cohort, headline metrics | `/api/overview`, `/api/evaluation` |
| Candidates | ranking table, filters, candidate pages | `/api/ranking`, `/api/compound` |
| Evidence | evidence, mechanism, conflicts, trial-role review | `/api/evidence`, `/api/conflicts`, `/api/review` |
| Validation | ROC/PR curves, CIs, baselines, TD-042 comparison (marked "not approved") | `/api/validation_charts`, `/api/alternatives` |
| Run Center | pipeline health, stages and runs, agents | `/api/live`, `/api/status`, `/api/launches` |

**What happens when you click Run:**
1. `app.js` `livePost` (:1469-1503) sends `POST /api/run {"stage": "10h"}` with a per-session nonce header.
2. `server.py` `do_POST` (:2430-2463) checks a loopback Host, a same-origin Origin, the nonce, JSON content and size.
3. `live_runs.launch` (:85-132):
   - `policy()` (:50-62): 403 if REFUSED, 428 if CONFIRM without confirmation; 409 if anything is running;
   - otherwise starts `python scripts/run_stage.py 10h --root <repo>`, records it in `data/_runs/_ui_launches/` and returns 202.
4. `run_stage.run()` (:516-652) fingerprints inputs, backs up outputs, runs the script with its `timeout_s`, validates the result, and writes the manifest record and the log.
5. The page polls `/api/status` every 1.5 s while a stage runs and every 4 s otherwise (:1186-1200). `build_live()` (`server.py:2186`) turns the manifest into the stage table and hero state.

**Viewing vs running.** Viewing pages only *reads* saved files and never starts work (browser-tested). **Run all** uses `--sequence` with `skip_fresh`, so unchanged stages are skipped. A single-stage **Run** always executes.

**Safe vs unsafe for a demo:**
- **ALLOWED:** 07, 10a, 10a-all, 10b–10h, review. These only write diagnostics or figures.
- **CONFIRM:** 04p, 05h and diag make network calls (`live_runs.py:40-42`).
- **REFUSED:** everything that writes approved data.

**The yellow badge** (overall state `VERIFIED_WITH_GAPS`): no *tracked* input changed, but `eval` reads `data/reproducibility.json`, which its adopted record never fingerprinted, and 8 adopted stages have no code fingerprint.

"Fresh against recorded inputs" means the **files** are unchanged since their last run. It does **not** mean ClinicalTrials.gov, PubMed, FDA or Open Targets are current. Each source's retrieval date is shown under *Source data* on Pipeline health.

---

## I. Developer operations (verified commands)

The **read-only** commands are:

```
./venv/bin/python ui/server.py                                # start UI (reads only, until you click Run)
./venv/bin/python scripts/run_stage.py --status               # freshness of every stage (--json for detail)
./venv/bin/python scripts/run_stage.py --check-manifest       # manifest integrity (exit 2 on problems)
./venv/bin/python scripts/vps_verify.py                       # independent recomputation of the approved score
./venv/bin/python -m unittest discover -s tests               # test suite
python3 -c "import json;m=json.load(open('data/run_manifest.json'));print(json.dumps(m['stages']['10h']['last_success'],indent=1))"
cat data/_runs/<run_id>/log.txt                               # a run's log
```

To list every stage's input/output contract (read-only):

```
./venv/bin/python -c "import importlib.util as u;s=u.spec_from_file_location('s','ui/server.py');m=u.module_from_spec(s);s.loader.exec_module(m);[print(x['id'],x['depends_on'],x['inputs'],x['outputs']) for x in m.STAGES]"
```

The following commands **⚠ write files**:

```
./venv/bin/python scripts/run_stage.py 10h                    # safe diagnostic: rewrites data/completeness_gaps.json only
./venv/bin/python scripts/run_stage.py --restore 10h          # restore last validated outputs after an interrupted run
```

**Isolated experiment** (never touches the approved baseline; this is the pattern used by the TD-042 candidate):

```
rsync -a --exclude venv --exclude .git ./ /tmp/evirep_exp/ && mkdir -p /tmp/evirep_exp/data/_runs
./venv/bin/python scripts/run_stage.py <stage> --root /tmp/evirep_exp
./venv/bin/python scripts/compare_result_sets.py --candidate /tmp/evirep_exp/data/vps_scores_v2.csv \
    --out /tmp/cmp --name exp1 --rule "what changed"
```

**Never casually run** 03, 04, 05 or 08 against the real root. They query live APIs and rewrite protected inputs.

---

## J. Limitations and future work (prioritised)

**Existing defects and validity risks:**

| # | Type | Issue | Consequence | Evidence that would resolve it |
|---|---|---|---|---|
| 1 | Science | TD-042 molecular double-count | The 5D advantage may be an artefact (0.775 → 0.699) | Owner decision; mechanistic justification |
| 2 | Science | Stage-03 data predates pagination (E-056) | Cohort incomplete (Dopamine) | Rebuild in an isolated copy + compare |
| 3 | Science | Literature, safety and molecular data not cutoff-bounded | Possible temporal leakage | Bounded rebuilds (partly measured: −0.019, −0.003; molecular 20.11 removes the 5D gain) |
| 4 | Science | 14 positives; label = trial activity | Wide CIs; no efficacy claim possible | Larger or alternative endpoints (RQ-2) |
| 5 | Science | Label edge cases (Lithium, Galantamine, 28 links, D-020) | Labels or features may shift | Human adjudication |
| 6 | Provenance | No code fingerprint for adopted stages; eval input unfingerprinted; bootstrap CSV not produced by any stage | Drift is undetectable | Owner-approved re-runs |
| 7 | Provenance | Approved CSV lacks `dimensions_imputed` | 2 imputed values unflagged | Owner-approved 06 re-run |
| 8 | Engineering | Undocumented constants (×5 boxed weight, N_RANDOM 100, σ = 0 → 0, phases[0]) | Arbitrary choices affect ranks | Sensitivity analysis + documented rationale |
| 9 | Engineering | Stages 06 and eval have no timeout; some agents exit 0 on PARTIAL; review writes non-atomically | Hung runs; misleading exit codes | Code fixes |
| 10 | UI | "Feeds the score" badge overstates agent roles; "28" is hard-coded | Misreadings | Wording change; compute from CSV |
| 11 | Security | No authentication or TLS; loopback-only single user | Not deployable | Auth, TLS, audit log |

**Stale documentation:** TD-009 (marked OPEN but fixed in code); TD-031 (still describes median safety imputation); `CONFLICT_CONTEXT_AGENT.md` (old counts); `AGENT_CONTRACT.md` (old 10a/10g coverage); the 10h docs ("11 domains"; there are 12).

---

## K. Defend the project

### 15 likely questions
1. **What is VPS?** The equal-weight mean of five percentile ranks (§F3).
2. **What is a positive?** A pool drug with a qualifying PD drug trial first posted on or after 2021-01-01, after 3 approved exclusions (§E).
3. **Why 90?** Compounds with ≥1 accepted, study-type-clean pre-2021 PD trial: 91, minus Mannitol.
4. **Why 14 + 76?** 17 had a post-2021 trial; 3 were not tested *for PD* (DBS anaesthesia, gene-therapy actuator); 90 − 14 = 76.
5. **AUROC 0.775?** A random positive outranks a random negative 77.5% of the time. It is not a success probability.
6. **Why AUPRC?** With 15.6% positives, it shows how well positives concentrate at the top (0.424 vs a chance level of 0.156).
7. **Why wide CIs?** With only 14 positives, resampling changes the result a lot.
8. **Why equal weights?** Tuned weights lose 0.12–0.14 AUROC on held-out folds (overfitting).
9. **How is leakage avoided?** Trials are split by date, and Open Targets clinical/literature datatypes are excluded. Literature, label and molecular data are *not* time-frozen; this is acknowledged.
10. **Do agents change the score?** No; a test enforces this (§C3).
11. **How do you know it's computed correctly?** `vps_verify.py` recomputes it independently (difference 2.2e-16), and stage 06 publishes only after that check.
12. **Missing data?** Safety/molecular get 0.5; proximity is median-imputed (2 compounds).
13. **Why is Donepezil #1?** Phase-4 trials, the most independent literature, strong molecular evidence. TD-042 would move it to #7, and a large RCT found a null cognition result (10d).
14. **The yellow warning?** One eval input was never fingerprinted; no tracked input changed (§H).
15. **Can the UI change approved results?** No: protected writers get 403, and the server is loopback-only with nonce and origin checks.

### 5 hard scientific questions
1. **Is trial activity a valid proxy?** Only partly: it also reflects funding and interest. Hence the claim is *ordering against later investigation*, never efficacy.
2. **Does molecular add value?** Not demonstrably: +0.075 with a CI crossing 0, and it vanishes under TD-042.
3. **Literature leakage?** A real limitation. The measured sensitivity is small (−0.019), but the dimension is not bounded.
4. **Are feature and label circular?** Both come from one registry and one set of matching rules, and shared trials affect both. The date split prevents direct reuse, not shared bias.
5. **Would a rebuild change results?** Possibly (Dopamine; newer Open Targets releases). **NOT ESTABLISHED** until an approved rebuild is compared.

### 5 implementation questions
1. **Pool definition?** `merge_dimensions`, `06_vps_fusion.py:166-199`.
2. **Date split?** `03_clinicaltrials_groundtruth.py:323-330`.
3. **Ties?** `percentile_rank`, `06:257-269` (`method="average"`).
4. **Failed-run safety?** `run_stage.run` (:516-652): back up, restore; stage 06 is staged and validated first.
5. **Staleness?** `run_stage.status` (:295-399) compares md5 fingerprints; `build_live` (`server.py:2186`) derives the overall state.

### Glossary

| Term | Meaning |
|---|---|
| Cutoff | 2021-01-01. Evidence before it is a feature; trials after it are the label. |
| Pool | The 90 evaluable compounds. |
| Percentile rank | A value's position in the pool scaled to 0–1. |
| ADOPTED | Pre-existing output, fingerprinted and verified but not re-run. |
| Fingerprint | md5 + size + mtime of a file at run time. |
| PROTECTED_ARTEFACTS | 19 files the dashboard can never rewrite. |
| Envelope | The standard agent output wrapper (`agent_contract.py`). |
| TD / D / E / B IDs | Technical-debt, decision, error and blocker log entries. |

### Suggested reading order
1. `README.md`.
2. `ui/server.py:57` (`STAGES`).
3. `scripts/06_vps_fusion.py`: `main` and `build_standardized_scores`.
4. `scripts/vps_verify.py`, the short independent version.
5. `scripts/03_clinicaltrials_groundtruth.py` + `scripts/intervention_matcher.py`.
6. `docs/INTERVENTION_MATCHING.md`.
7. `scripts/vps_evaluation_report.py`.
8. `scripts/run_stage.py`: `run` and `status`.
9. `ui/live_runs.py`.
10. One agent: `scripts/completeness_gap_agent.py`.
11. `TECHNICAL_DEBT.md` (TD-042, TD-021, TD-022) and `development_log/DECISIONS.md` (D-001, D-010, D-020).
