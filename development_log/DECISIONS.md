# EviRep — Decision Log

One entry per material decision. **V** = verified fact (file, test or response observed in
this repository), **I** = reasoned inference, **H** = unverified hypothesis. A recorded
decision is not proof that it is correct; confidence and open uncertainty are stated.

---

## D-001 · 2026-10-15 · What the evaluation claims (objective and endpoint)

**Question.** Does the evaluation measure therapeutic efficacy or evidence-based prioritisation, and what does a label mean?

**Evidence.**
- V `README.md` §1 describes the project as candidates "scored on independent evidence dimensions … evaluated against post-cutoff ClinicalTrials.gov entries".
- V `scripts/06_vps_fusion.py::merge_dimensions` builds the pool from compounds with an accepted *pre-cutoff* PD trial (90).
- V `build_labels` + `apply_label_exclusions`: positive = an accepted *post-cutoff* PD trial (14/90).
- V `data/ground_truth_postcutoff_clean.csv`: trials first posted 2021-01-13 … 2026-09-08; md5 `c83e30bb…` is pinned in `tests/test_pipeline_safety_contracts.py`.
- V TD-035: 24 of 41 ground-truth compounds are outside the pool.

**Alternatives.**
- (a) Present AUROC as efficacy prediction.
- (b) Present it as prediction of subsequent PD trial activity among compounds already trialled in PD.
- (c) Redefine the endpoint (efficacy outcomes, or first-ever PD trial).

**Decision: (b).** No document or artefact measures efficacy, and the pool excludes first-time candidates. (c) would change the endpoint, and that is the owner's call.

The claim used everywhere is: *"Among 90 compounds with a pre-2021 PD trial, an evidence score ranks those that received a further qualifying PD trial (first posted 2021-01-01 … 2026-09-08, the last observed date) above chance."* **Corrected by D-010:** the window ends at the 2026-10-05 registry snapshot; 2026-09-08 is only the latest first-posted date observed. A negative means only that no qualifying trial was found in that window.

**Uncertainty.** The window end is the retrieval date, not a protocol date (I: it was stage 03's run date, not recorded). The frozen file defines it until the owner fixes a date. Confidence: high that (a) is unsupported.

**Action.** Wording used in `docs/CASE_STUDIES.md` §10 and the UI label text (`ui/server.py`). No data change.

---

## D-002 · 2026-10-15 · Primary analysis and how metrics are reported

**Question.** Which model is primary, and which numbers count as estimates of generalisation?

**Evidence.**
- V Equal-weight scores involve no fitting: the formula is verified against persisted scores (`TestEqualWeightFormula`).
- V Grid weights are selected on all labelled data, so their reported AUROC is in-sample.
- V Nested CV selects on training folds only (`TestGridSearchSelectsOnTrainingFoldsOnly`).
- V A single-split nested-CV estimate varies widely across repeated splits (TD-036).

**Alternatives.** (a) Report the best variant. (b) Equal-weight 4d and 5d as primary, paired bootstrap for 5d−4d; grid models exploratory, reported with repeated nested CV.

**Decision: (b).** (a) selects on the evaluation labels.

**Limitation.** This specification is made *after* results were seen (it is retrospective), so it is a reporting rule, not a pre-registration.

**Action.**
- Report in-sample and held-out values separately, everywhere.
- Figure 1 already distinguishes them (C-24).
- No code change.

---

## D-003 · 2026-10-15 · Safety stage ignored the warnings section of PLR-format labels

**Question.** Is `serious_term_count` = 0 for most labelled compounds a measurement or an artefact? (Hypothesis raised in TD-031.)

**Evidence.**
- V Smallest test first: 5 openFDA label requests (Donepezil, Varenicline, Lidocaine, Mirabegron, Quetiapine).
  - 4 of 5 labels have no `warnings` key; their warnings are in `warnings_and_cautions`.
  - The stage-05 code counted 0 there, but the section contains 2 / 25 / 1 / 27 term hits.
  - Lidocaine (old format) was correctly scored 0.
- V The stage-05 docstring says it "counts serious-sounding terms in the warnings section". So the method was right and the implementation wrong.

**Alternatives.**
- (a) Keep the v1 data, documented as invalid.
- (b) Fix the field list and re-query (about 90 requests, no key).
- (c) Drop safety from the score. That changes the model, so it would be the owner's call.

**Decision: (b).** It is a defect against the documented method, cheap and reversible.

**Implementation.**
- `scripts/05_safety_signal.py` reads `boxed_warning`, `warnings` and `warnings_and_cautions`.
- It records `warning_fields`, `label_set_id` and `label_effective_time`, and caches each raw label in `data/cache/openfda_labels/`.
- Records go to the new `data/_safety_checkpoint_v2.jsonl`; the v1 checkpoint is untouched (md5 `ba2cc25c…` before and after).

**Result.**
- V The same 7 compounds have no label.
- V Labelled compounds with 0 terms: 52 → 16.
- V Spearman correlation of v1 vs v2 safety ranks among labelled compounds: 0.76.
- V Safety-only AUROC among labelled compounds: 0.629 → 0.540. Part of safety's earlier apparent signal came from label format.

**Uncertainty.**
- Term counting remains crude; longer PLR sections may collect more hits.
- `limit=1` takes an arbitrary label (product or formulation).
- Labels are current (effective dates 2018–2026), so not cutoff-bounded (TD-022 stays OPEN).
- Confidence that v2 is a better measurement than v1: high. Confidence that it is a good safety measure: low.

**Verification.**
- `tests/test_safety_missingness.py`: PLR field counted, plus a real Varenicline label subset fixture.
- External requests: openFDA 5 + 90.

---

## D-004 · 2026-10-15 · Rule for unmeasured dimensions (TD-031 safety, TD-024 molecular)

**Question.** How should a compound with no openFDA label, or with no ChEMBL mechanism target, enter the fused score?

**Evidence.**
- V Old rule:
  - Safety: median imputation of a zero-inflated count gave all 7 unlabelled compounds the pool-maximum safety rank.
  - Molecular: 16 no-target compounds were fused as a measured 0.0.
- V The project's standing rule: "never equate missing evidence with negative evidence, safety, efficacy or zero risk".

**Alternatives** (all computed; AUROC was *not* the selection criterion, because all 7 unlabelled compounds are negatives, so any rule that downgrades "missing" raises AUROC by construction):
- (A) Median as before. Violates the standing rule.
- (B) Available-case: average only the measured dimensions. Implemented and run first, then **rejected**: Lisuride (safety and molecular both unmeasured) rose to **rank 1 of 90** on 3 of 5 dimensions. Dropping dimensions lets missingness amplify the remaining ones, and every single-dimension weight vector became unable to score some compounds.
- (C3) Worst rank. Equates missing with harmful.
- (C1) Neutral rank 0.5, the midpoint of the [0, 1] percentile scale, plus visible coverage.

**Decision: (C1).**
- It treats "not measured" as neither favourable nor unfavourable.
- It does not let a compound rise on fewer dimensions: Lisuride is rank 5.
- It keeps every weight vector valid.

**Implementation** (`scripts/06_vps_fusion.py`):
- `NEUTRAL_RANK = 0.5`.
- Safety is no longer imputed.
- Measured compounds are ranked among themselves.
- New columns: `dimensions_missing`, `n_dimensions_measured`, `molecular_evidence_missing`.
- Raw values are kept as they were (the no-target 0.0 stays in `molecular_plausibility_score`).

**Assumptions and limitations.**
- I: Unmeasured compounds are assumed exchangeable with the median measured compound. That is untestable here.
- V: The inverted percentile scale is not exactly symmetric, so with heavy ties the "best" tied group can sit below 0.5. This does not occur on current data: zero-risk labelled compounds rank about 0.90.
- Not covered by this rule:
  - Proximity's 2 missing values remain median-imputed, which lands near the mid rank in effect.
  - Compounds absent from `molecular_pathway.csv` would still be median-imputed (0 such compounds).
- Confidence: moderate. This is a defensible convention, not a verified truth.

**Verification.**
- 06 rerun; 312 tests passed.
- Regression tests: `TestFusionSafetyMissingness` (neutral rank, zero-inflated case, ranking among measured only) and `TestNoTargetMolecularIsMissing`.
- Old outputs archived in `data/_archive_pre_D003_D004_2026-10-15/` with MD5SUMS.

---

## D-005 · 2026-10-15 · Lidocaine and Galantamine labels

**Question.** Should the two unresolved positives change?

**Evidence.**
- V `docs/CASE_STUDIES.md` §9.2.
- V The owner decided on 2026-10-14 to keep both as positive.

**Decision.** No change. This is an owner decision, and no new evidence has appeared. They are reported as positive-but-unresolved, and sensitivity results are kept in §9.1.

**Uncertainty.** These two labels move the 5d−4d gap by up to about 0.04 (§9.1).

---

## D-006 · 2026-10-15 · Cutoff-bounded literature re-retrieval (TD-021 / B-002)

**Question.** Is it needed now?

**Evidence.**
- V TD-021 dry-run: about 180 NCBI and up to 2,700 Semantic Scholar requests, 1–2 h, with a history of throttling.
- V The bounded sample would still be truncated at 30 papers.

**Decision.** Defer, and restrict the claim instead: the literature dimension is labelled not cutoff-bounded in every report and figure. The cost and the cap/sort policy need the owner.

**Consequence.** No result can be called leakage-free (TD-033).

---

## D-007 · 2026-10-15 · Status of the molecular/pathway agent (dimension 5)

**Evidence.**
- V 90/90 compounds are scored by stage 08 (06 log).
- V No-target compounds are now treated as missing (D-004).
- V 5d−4d +0.075, 95% CI [−0.025, +0.176].
- V Open Targets snapshot 26.09 is not cutoff-bounded (B-001).

**Decision.** Engineering integration is complete: the agent is in the default fusion, with the 4d model reported alongside. Its incremental predictive value is **not established**, and no claim of improvement is made.

**Remaining.** B-001 (no historical snapshot) cannot be fixed with available data.

---

## D-008 · 2026-10-15 · Basic UI

**Question.** Does the dashboard show the current scientific state?

**Evidence.** V Before this change, the UI listed the excluded label trials without marking them, and did not show unmeasured dimensions.

**Decision.** Show the following, read from the persisted artefacts only:
- Label exclusions per post-cutoff trial.
- The label meaning: trial activity, not efficacy.
- Dimensions not measured, with their neutral-rank note.
- Stage 05 v2 details.

**Verification.**
- V `tests/test_ui.py`: 44 tests.
- V Live loopback server on port 8799: endpoints returned 200; Dexmedetomidine's trial is marked excluded; Lisuride shows safety and molecular as not measured.
- Rendering in a browser was **not** verified.
- A pre-existing server process (PID 98598, port 8765, started 2026-10-13) was left running; it serves the old code until restarted.

---

## D-009 · 2026-10-15 · Literature credibility agent (10a)

**Decision.** It stays diagnostic. Integration preconditions are in `docs/LITERATURE_CREDIBILITY_AGENT.md` (cutoff-bounded input, deduplication against the clinical dimension, a pre-registered test). D-006 defers the first of these.

---

## D-010 · 2026-10-15 · Frozen endpoint and label window

**Question.** Is 2026-09-08 the data-retrieval cutoff for the current labels?

**Evidence.**
- V **No.** 2026-09-08 is the largest `first_posted` value in `ground_truth_postcutoff_clean.csv`.
- V The labels come from the stage-03 "clean rerun" logged in `development_log/CHANGES.md`,
  "2026-10-05 (afternoon) — ClinicalTrials.gov intervention-collision fix (E-010) + clean
  rerun" (`03 → 03b → check_studytype → filter_by_studytype …`).
- V Output mtimes: `ground_truth_postcutoff.csv` and `clinicaltrials_match_audit.csv` at
  2026-10-05 15:40:25; `_clean.csv` at 15:44:04. E-017 did not touch stage-03 files.
- I The exact query start time was not recorded. The registry snapshot is therefore
  "ClinicalTrials.gov v2 as queried on 2026-10-05".

**Decision. Frozen endpoint:**
- A compound in the 90-compound pool is **positive** if ClinicalTrials.gov v2, as queried on 2026-10-05, holds at least one interventional study that:
  - names it as an intervention (Gate 2 MATCHED);
  - has a Parkinson's condition;
  - was first posted 2021-01-01 or later;
  - passes the study-type filter;
  - is not listed in `data/label_role_exclusions.csv`.
- The frozen artefact is `data/ground_truth_postcutoff_clean.csv` (md5 `c83e30bb…`, pinned by a test). Labels were not regenerated.
- The latest qualifying trial observed is 2026-09-08.

**Uncertainty.** A trial first posted shortly before 2026-10-05 may have been indexed late. That affects completeness, not validity, of the frozen definition.

---

## D-011 · 2026-10-15 · Lidocaine and Galantamine against the P1 criterion

**Criterion** (approved 2026-10-14, §9.1): a positive needs at least one post-cutoff trial in which the compound is an active agent tested for Parkinson's disease or a PD symptom. Anaesthesia/procedural, comparator-only and actuator roles do not qualify.

**Evidence** (registry records saved 2026-10-13, scratch `label_trials/`; no new requests):
- **Lidocaine.**
  - NCT06301724, NCT06319625 and NCT06370195 are all RANDOMIZED, QUADRUPLE-masked, primary purpose TREATMENT.
  - Condition is Parkinson disease (one trial: "Parkinson's Syndrome").
  - Experimental arm: stellate-ganglion block with 2% lidocaine (+ vitamin B12).
  - PLACEBO_COMPARATOR arm: the same injection procedure with saline / "no drugs".
  - Primary outcomes are PD symptoms (Penetration-Aspiration Scale; drooling amount).
- **Galantamine.**
  - NCT07284290 is NON_RANDOMIZED, unmasked, primary purpose BASIC_SCIENCE ("Elucidating the Role of Cholinergic Degeneration…").
  - Galantamine is given only to an open 8-week sub-cohort of about 20 patients with "DLB or PDD".
  - Conditions: DLB, PD dementia, healthy controls.

**Decision.**
- **Lidocaine: CONFIRMED (resolved).** The placebo arm controls for the procedure, so the drug is the tested active agent for a PD symptom. This differs from the rejected procedural cases, where the drug served a surgery and not the disease. Caveats: the injection is co-formulated with vitamin B12, and the action is local, not systemic. Confidence: moderate–high.
- **Galantamine: remains UNRESOLVED.** The registry declares a mechanistic purpose, and the population is not PD-specific (DLB and PDD are pooled). The documented criterion cannot decide it. The label stays 1 by the 2026-10-14 owner decision. Not changed.

**Sensitivity** (current data; paired bootstrap n=2000, seed 42):

| Scenario | Positives | 4d AUROC | 5d AUROC | 5d − 4d [95% CI] |
|---|---|---|---|---|
| Current | 14 | 0.700 | 0.775 | +0.075 [−0.025, +0.176] |
| Galantamine → 0 | 13 | 0.728 | 0.781 | +0.053 [−0.052, +0.152] |
| Galantamine excluded | 13 | 0.725 | 0.782 | +0.058 [−0.050, +0.159] |
| Lidocaine → 0 (for reference) | 13 | 0.692 | 0.756 | +0.064 [−0.041, +0.174] |

No scenario changes a conclusion. Galantamine ranks 34/90, so its positive label lowers the 4d AUROC.

---

## D-012 · 2026-10-15 · Is cutoff-bounded literature re-retrieval needed for the planned claim?

**Planned claim (D-001/D-010).** The equal-weight evidence score ranks later-trialled compounds above chance. It is explicitly not leakage-free.

**Evidence** (unfitted equal-weight subsets, bootstrap 95% CI, n=2000, seed 42; exploratory, computed after results were known):

| Dimensions | AUROC [95% CI] |
|---|---|
| All 5 (primary) | 0.775 [0.656, 0.881] |
| 5 minus literature | 0.740 [0.623, 0.855] |
| 4d minus literature | 0.679 [0.534, 0.812] |
| Literature only | 0.645 [0.463, 0.825] |
| Proximity + clinical (best-bounded) | 0.653 [0.474, 0.816] |
| Clinical only | 0.672 [0.498, 0.835] |

**Decision. Not needed now; not launched.**
- The above-chance claim does not depend on the unbounded literature dimension (0.740, CI excludes 0.5).
- Re-retrieval would not make the claim leakage-free, because safety and molecular are also current snapshots (B-001) and cannot be fixed with available data.
- With only the best-bounded dimensions, the CI includes 0.5. So the claim rests on dimensions that are not cutoff-bounded, and must say so.

**When it becomes necessary.** For the question "does literature carry pre-cutoff signal?", or for any claim about the literature dimension's contribution. The scope and cost plan for that is in TD-021 (dry run).

---

## D-013 · 2026-10-15 · Objective: continued clinical investigation; first-time repurposing is separate

**Evidence.**
- V No approved protocol document exists in the repository beyond `README.md`, whose framing ("evaluated against post-cutoff ClinicalTrials.gov entries") matches the current endpoint.
- V TD-035 / TD-027: the pool requires a pre-cutoff PD trial; 24 of 41 ground-truth compounds are outside it.

**Decision.** Keep the current endpoint, "continued clinical investigation in PD", stated as **not therapeutic efficacy**. First-time repurposing (compounds with no pre-cutoff PD trial) is recorded as **separate research question RQ-2**. It is not added to this cohort. RQ-2 would need:
- a new pool definition that does not require a prior trial;
- a clinical-maturity dimension redefined (it would be empty for that pool);
- its own label audit.

---

## D-014 · 2026-10-15 · UI framework: extend the existing dashboard, not Streamlit

**Question.** Which UI implementation gives a usable interactive research dashboard fastest and most maintainably?

**Evidence.**
- V `streamlit` is not installed in `venv` (`ModuleNotFoundError`). Adding it brings a large dependency tree.
- V `ui/` (standard-library server plus vanilla JS) already had pipeline, agents, drug explorer, case-study and validation views.
- V It has a loopback-only server, a strict CSP and 44 security/accessibility tests (`tests/test_ui.py`).

**Alternatives.**
- (a) Streamlit rewrite: new dependency, and it would duplicate the existing views and their security tests.
- (b) Extend the existing UI.

**Decision: (b).** One UI only. Added:
- an Overview landing page;
- a sortable ranked-candidate table with search;
- per-dimension evidence states (measured / measured zero / not measured / not retrieved);
- a 10a–10h agent inventory with status derived from files, plus a per-candidate agent inspector;
- 10d panels in the explorer, agent inspector and case studies;
- primary CIs on Overview and Validation;
- a single restrained dark palette (the previously WCAG-tested dark tokens);
- a 204 response for `/favicon.ico`.

Charts use native `<meter>` elements, because the CSP forbids inline styles.

**Verification.**
- V `tests/test_ui.py`: 50 tests.
- V A real headless Chrome was driven over the DevTools protocol with real mouse clicks and keyboard text input (script and screenshots in the session scratchpad). All 18 checks passed: landing page, navigation through all 6 views, search filtering, row selection updating details, header sorting, Lisuride missing-evidence states, Donepezil molecular targets and PMIDs/NCT IDs, the agent inspector switching candidates, 4 figures loading, and zero console errors after the favicon fix.
- Limitation: headless. The Claude-in-Chrome extension cannot reach loopback (L-003), and an on-screen interactive session was not performed. The agent-inspector `<select>` change was dispatched as a DOM `change` event, not a native picker interaction.

---

## D-015 · 2026-10-15 · Next specialised agent: 10d Conflict & Context

**Inventory (verified from files; 06 integration checked by its input path in `06_vps_fusion.py`).**
- 10a: implemented and tested, diagnostic (Droxidopa only).
- 10b: integrated (dimension 5).
- 10c: partial (connector, Gate 2 and max phase; no assessment of trial results).
- 10d: **absent** (no conflict logic outside 10a's curated-direction flag).
- 10e: absent.
- 10f: partial (openFDA label terms; no FAERS).
- 10g: integrated (stage 04 independence = the "literature" dimension).
- 10h: absent as an agent (coverage columns only).

**Why 10d.**
- It is the documented architecture's preferred next agent and is confirmed missing.
- Source-linked evidence for it already exists: case-study PMIDs, 83 cached FDA labels from D-003, and 10b evidence chains.
- It needs no API calls.
- It adds information no VPS dimension carries: null results, harms, and why sources disagree.
- It can be tested offline without touching labels or VPS.

10e and 10h would need either re-retrieval (10e) or would duplicate D-004's coverage columns (10h).

**Design.** See `docs/CONFLICT_CONTEXT_AGENT.md`.
- Deterministic rules only.
- Curated claims are transcribed only from `docs/CASE_STUDIES.md`; a test checks that every PMID appears there.
- Classes separate direct contradiction from significance-only, context, cross-domain and non-comparable differences.
- Flags mark non-independent sources, quality asymmetry and post-cutoff evidence.
- `INSUFFICIENT` is never presented as agreement.
- Output is written atomically, as structured `synthesis_inputs` for Stage 11.

**Result.** 0 direct contradictions; Melatonin is a significance-only disagreement between overlapping meta-analyses; Donepezil is a context difference; 8 benefit–risk or mechanism–safety tensions; 72/91 compounds insufficient.

**Not done.** No integration into VPS and no claim of incremental predictive value. Coverage is too thin (4 curated compounds), and labels are not cutoff-bounded.

**Verification.** 21 offline tests (socket guard, determinism, schema, traceability); full suite 341 OK.

---

## D-016 · 2026-10-15 · Streamlit migration re-evaluated: not justified

**Evidence.**
- V `streamlit` is still not installed.
- V The existing dashboard now covers all six required areas: overview, registry, explorer,
  case studies, validation, and run/audit status.
- V It has 55 UI tests, a strict CSP, loopback-only binding and host validation.
- V A real-browser check passes 28/28, including keyboard-only sorting and a 390-px phone
  viewport without page overflow.

**Alternatives.**
- (a) Streamlit migration: adds a large dependency stack, needs a websocket server and a
  different security model, and loses the CSP and route tests; parity work for no new capability.
- (b) Improve the existing dashboard.

**Decision: (b).** Streamlit would have a net benefit only for interactive plotting widgets,
which the scientific views do not need (tables, `<meter>` bars, PNG figures).

**Limitation.** The browser checks were headless (Chrome DevTools protocol); there was no
on-screen session.

## D-017 · 2026-10-15 · Agent 10e (Reproducibility) design

**Question.** How can replication be assessed without duplicating 10g or 10d and without
inventing relationships?

**Evidence.**
- V 10g merges papers by shared author or citation and counts components; it is paper-level and
  direction-blind.
- V 10d classifies disagreement.
- V Author lists exist only in cached efetch XML.

**Decision.**
- Assess at the finding level, with deterministic rules.
- A citation is not a data dependency.
- Syntheses never count as replicates.
- Independence is categorical, and at best PLAUSIBLY_INDEPENDENT.
- No score.

**Cost.** One targeted PubMed efetch (14 PMIDs), justified because author and trial metadata
decide independence and verify the claims' identifiers and dates.

**Result.** 1 REPLICATED (Propranolol tremor), 6 SINGLE_STUDY, 7 SECONDARY_ONLY; 21 trials
shared across compounds (TD-038).

**Not done.** Integration into VPS: coverage is 4 compounds plus 1 paper sample.

## D-018 · 2026-10-15 · VPS evaluation additions

**Decision.**
- Persist a reproducible evaluation report: input md5s, seed, and exact reproduction of every
  persisted AUROC.
- Add AUPRC with bootstrap CIs and lift over prevalence.
- Report 20-repeat nested CV for the fitted models.
- Add dimension correlations, all imputation paths and duplicate trial evidence.
- **Calibration is not assessed**, because VPS is a rank score and there are only 14 positives.

**Evidence.** `docs/VPS_EVALUATION.md`; all 6 persisted AUROCs reproduced; the bootstrap is
bit-identical on rerun and equals the persisted CI file.

No weights, labels, cohort or missing-data rules were changed.

## D-019 · 2026-10-15 · Case-study completion criteria

**Decision.** A fixed seven-item checklist:
1. identifiers verified
2. trial roles checked
3. both sides of the evidence recorded
4. temporal position stated
5. overlap checked
6. safety noted
7. gaps listed

It is kept separate from the documented verdict, so the ledger cannot silently upgrade or
downgrade a case. Remaining partial items are listed in CASE_STUDIES §11.

## D-020 · 2026-10-14 · Shared pre-cutoff trials (TD-038): role policy for feature links — **PROPOSED, awaiting owner**

**Question.** 17 pre-cutoff trials are linked to more than one pool compound (35 links, 31
compounds). Which links are valid clinical-maturity evidence for which compound?

**What the score actually does.** `r_clinical` is the percentile rank of each compound's maximum
phase. `n_trials` is computed but not scored. A trial shared by two compounds is therefore not
counted twice for either one, so down-weighting shared trials would penalise legitimate
multi-arm trials and is **rejected**. The question is only the role of each compound in each trial.

**Evidence.**
- One ClinicalTrials.gov v2 request (2026-10-14, 17/17 records, HTTP 200), cached at
  `data/cache/ctgov_td038_shared_trials.json`.
- Annotator `scripts/trial_role.py`, plus a manual reading of interventions, arms, descriptions,
  primary purpose, population and outcomes.
- Per-link table: `data/feature_trial_roles_td038.csv`. The ground truth and
  `clinical_maturity_precutoff_clean.csv` are unchanged.

| Trial | Compounds | Design (registry) | Category | Meets P1? |
|---|---|---|---|---|
| NCT00062738 | Nortriptyline, Paroxetine | separate EXPERIMENTAL arms vs placebo; depression in PD | drug-specific arm | yes |
| NCT00086190 | Paroxetine, Venlafaxine | separate arms vs placebo; depression in PD | drug-specific arm | yes |
| NCT03652870 | Nortriptyline, Escitalopram | separate arms vs placebo; depression in PD | drug-specific arm | yes |
| NCT00892450 | Darifenacin, Oxybutynin | randomised crossover, each drug alone for 4 weeks; cognitive side effects of overactive-bladder treatment in PD | drug-specific arm | yes |
| NCT02879136 | Atomoxetine, Methylphenidate | physical therapy (PT) + each drug vs PT alone; gait in PD | drug-specific arm | yes |
| NCT02897063 | Droxidopa, Midodrine | single dose of each vs placebo; BASIC_SCIENCE; mixed autonomic failure including PD | drug-specific arm (flag) | yes |
| NCT03440112 | Clarithromycin, Flumazenil | each vs placebo as a GABA-A modulator in PD; clarithromycin arm stopped 4/2020 | drug-specific arm (flag) | yes |
| NCT01489982 | Doxepin, Zopiclone | one arm: doxepin *or* zopiclone, individualised; PD insomnia | alternatives in one arm | yes |
| NCT00664209 | Amoxicillin, Omeprazole | one triple-therapy intervention vs placebo for OFF time | fixed combination (all components) | undecided |
| NCT01439100 | Oxycodone, Naloxone | oxycodone/naloxone PR tablet vs placebo; PD pain | fixed combination (principal / adjunct) | undecided |
| NCT01767129 | Dextromethorphan, Quinidine | AVP-923 capsule vs placebo; levodopa-induced dyskinesia | fixed combination (principal / adjunct) | undecided |
| NCT02857244 | Duloxetine, Donepezil | WITHDRAWN, 0 enrolled; one sequential open arm | unverifiable | undecided (no score effect) |
| NCT00615472 | Isoflurane, Propofol, Remifentanil | IV vs inhalational anaesthesia; primary purpose DIAGNOSTIC | procedural | no |
| NCT02256319 | Dexmedetomidine, Propofol | sedation during DBS recordings; SUPPORTIVE_CARE | procedural | no |
| NCT03970798 | Midazolam, Rosuvastatin | probe substrates in a KW-6356 interaction study, healthy men | auxiliary agent | no |
| NCT04070495 | Clarithromycin, Rifampicin | CYP3A inhibitor/inducer in a KW-6356 interaction study, healthy men | auxiliary agent | no |
| NCT04127578 | Methylprednisolone, Sirolimus | concomitant immunosuppression for AAV9 gene therapy | auxiliary agent | no |

The adjunct roles of naloxone and quinidine are pharmacology, not something the registry
records state. Without the "no" links, 7 compounds have no pre-cutoff PD link left: Isoflurane,
Remifentanil, Propofol, Midazolam, Rosuvastatin, Methylprednisolone and Sirolimus, all label 0.
No compound that stays in the pool changes maximum phase.

**Alternatives** (`scripts/td038_feature_role_sensitivity.py` → `data/td038_feature_role_sensitivity.json`;
2000 resamples, seed 42; S0 reproduces the persisted scores exactly):

| Scenario | n / pos | 4d AUROC | 5d AUROC [95% CI] | 5d AUPRC | 5d − 4d [95% CI] |
|---|---|---|---|---|---|
| S0 current | 90 / 14 | 0.700 | 0.775 [0.656, 0.881] | 0.424 | +0.075 [−0.025, +0.176] |
| S1 exclude "no" links; compounds without a link leave the pool | 83 / 14 | 0.684 | 0.765 [0.628, 0.876] | 0.407 | +0.081 [−0.019, +0.184] |
| S2 = S1 + adjunct components (naloxone, quinidine) | 81 / 14 | 0.680 | 0.765 [0.644, 0.874] | 0.414 | +0.085 [−0.024, +0.190] |
| S3 = S1 + all combination and unverifiable links | 79 / 14 | 0.679 | 0.767 [0.639, 0.879] | 0.420 | +0.088 [−0.014, +0.202] |
| S1k = S1, but those compounds stay with phase rank 0 | 90 / 14 | 0.704 | 0.779 [0.654, 0.886] | 0.427 | +0.075 [−0.027, +0.184] |

S1 decomposition:
- old scores on the same 83 compounds give 5d 0.762, so the shift is almost entirely the pool change;
- on identical compounds the paired change is +0.003 [−0.012, +0.019].

Every scenario is a **corrected measurement, not better prediction**. No conclusion changes.

**Recommendation (not applied).**
1. Adopt the P1 criterion for feature links as well as labels. That gives symmetric definitions
   of a "qualifying PD trial".
2. Compounds left with no qualifying pre-cutoff link **leave the pool** (S1). The pool is defined
   by such a trial, so keeping them with an invented phase rank (S1k) has no basis.
3. **Keep fixed-combination links** for every listed active ingredient. The combination is the
   tested intervention. Splitting principal from adjunct needs outside pharmacology, and S2/S3
   change nothing material.
4. Leave the withdrawn trial; it has no effect.
5. Apply the rule only after auditing **all 195** feature links, not just the 35 shared ones.
   About 8 batched registry requests would cover the other 160. Otherwise the policy covers
   only links that happen to be shared (for example Lisuride's background-therapy link, TD-023,
   is not shared).

The mechanism is in place but inactive: `apply_feature_exclusions()` in `06_vps_fusion.py`
reads `data/feature_role_exclusions.csv` **only if it exists**, and it has not been created.

**Owner decisions needed:** (a) P1 for features yes/no; (b) leave pool (S1) vs keep (S1k);
(c) combinations keep / drop adjuncts / drop all; (d) full 195-link audit before applying.

## D-021 · 2026-10-15 · Next agent: 10h Completeness & Gap (diagnostic)

**Repository state checked first.**
- 10a, 10d and 10e exist and are tested.
- 10b, and 10c/10f partially, are in VPS; 10g is the literature dimension.
- 10h existed only as stage-06 coverage columns, with no module (the dashboard registry said
  "not implemented").

**Why 10h.** The candidate explorer has to tell a researcher whether a low or neutral value
means a measured zero, no record at source, never retrieved, or a failed retrieval. No
existing component did this.

**Design.**
- Deterministic and offline: reads only persisted outputs.
- Eleven domains and nine states.
- Gaps carry the remedy and the open research questions.
- Fails if its view of the VPS dimensions disagrees with stage 06.
- No score; not read by stage 06.

**Evidence.** `docs/COMPLETENESS_GAP_AGENT.md`. 12 tests. Counts were cross-checked against the
raw CSVs.

**New finding (not acted on).** Two compounds' proximity values are median-imputed without a
`dimensions_missing` flag. This differs from the D-004 rule for safety and molecular. It is
recorded here, and nothing was changed.

## D-022 · 2026-10-15 · Researcher-facing dashboard structure

**Decision.** Keep the existing standard-library server and vanilla JavaScript (D-014/D-016).
Make the primary navigation research-oriented: Overview, Candidates, Evidence, Mechanism,
Conflicts, Compare, Validation & Methods, and Technical details. The former developer pages
(pipeline, agents, case studies and logs) move under Technical details.

**Rules kept.**
- Read-only, loopback only, strict CSP, no request on page load.
- External identifier links are built only from strict patterns (NCT, PMID, DailyMed set id,
  Ensembl, ChEMBL, Reactome) and open only on click.
- The candidate summary is assembled from persisted values and 10d claims. Trial registrations
  are not listed as supporting evidence.

**Verification.** Headless Chrome over the DevTools protocol, 42/42 checks (listed in CHANGES
C-44). There was no on-screen interactive session.

## D-023 · 2026-10-15 · Shared agent contract; 10c, 10f and 10g completed as diagnostic layers

**Decision.**
- One envelope for all agent outputs (`scripts/agent_contract.py`, `docs/AGENT_CONTRACT.md`).
  STALE is derived from input hashes at read time.
- 10c, 10f and 10g are separate modules layered over stages 03, 05 and 04. The stage outputs stay
  the VPS inputs, unchanged, and the new layers are diagnostic.
- 10b gets an offline run record that re-validates its persisted output instead of re-running it.

**Why not change VPS.**
- FAERS counts, posted trial results, automated trial roles and cross-source dependence are new
  evidence. None has a pre-specified, leakage-aware evaluation.
- FAERS and results are mostly post-2021.
- Adding any of them to VPS and evaluating on the same 90 compounds would be tuning on the test set.

**External requests this sprint:**
- 2 FAERS connector checks, then 88 × 4 openFDA count queries: 0 failures.
- 9 ClinicalTrials.gov batched requests: 177/177 trials returned.

No label, cohort, weight or missing-data rule changed. `vps_scores_v2.csv` and the ground truth are
byte-identical. TD-038/D-020 is not applied.

## D-024 · 2026-10-15 · VPS verified independently; formula unchanged; agent contributions unchanged

**Evidence.**
- `scripts/vps_verify.py` re-implements the scoring from the written rules without importing
  stage 06. It reproduces the published `vps_scores_v2.csv` exactly (90/90; max |diff| 2.2e-16;
  same ranks, flags and labels).
- Hand-computed fixtures: `tests/test_vps_correctness.py`.

**Fixed (latent or metadata only; every published score identical, verified on
`data/_candidates/vps_legacy_fixed/`):**
- duplicate input rows now raise;
- non-finite raw values are treated as not computed;
- a `dimensions_imputed` flag is added, and `n_dimensions_measured` excludes imputed dimensions
  (Deferiprone and Trimethobenzamide: 5 → 4);
- the evaluation report now fingerprints all 7 inputs.

The published baseline file was not replaced. These changes take effect at the next tracked run
of stage 06.

**Not decided (owner): the rank convention, TD-040.**
- "legacy" (the current baseline) versus "midrank" (symmetric; neutral 0.5 is the true midpoint).
- The candidate is at `data/_candidates/vps_midrank/`: AUROC 5d 0.7754 → 0.7744, 5 adjacent rank swaps.
- Switching changes every published number slightly, so it needs approval: run
  `scripts/run_stage.py 06 -- --rank-convention midrank`, or change the `RANK_CONVENTION` default.

**Agent contribution.** VPS remains the equal-weight 5 dimensions; no diagnostic agent output is
added (matrix in `docs/AGENT_CONTRACT.md`). Reasons:
- coverage;
- post-cutoff availability (FAERS, posted results);
- D-020 dependence for trial roles and de-duplication;
- the risk of tuning on 14 positives.

## D-025 · 2026-10-15 · Run tracking and live dashboard: one manifest, content fingerprints, polling

**Decision.**
- `scripts/run_stage.py` with `data/run_manifest.json` as the single run record.
- The stage graph stays in `ui/server.py` `STAGES`, which now includes the agents and the eval report.
- Freshness comes from content fingerprints and dependencies, never from timestamps.
- Stage 06 publishes only after an independent re-computation passes.
- The dashboard polls `/api/status` every 4 s and re-renders in place when the data version changes.

**Rejected.**
- SSE or WebSockets: one-way, low-frequency state needs no push channel.
- Streamlit: a rerun model does not provide dependency-aware freshness. The existing UI met every
  requirement in the browser workflow.
- A database: a JSON manifest under a file lock is sufficient for one machine.

**Verification.**
- Live browser workflow on a fixture copy of the data: 17/17 checks.
- Regression browser suite: 53/53.
- Tests: `tests/test_run_tracking.py` and `tests/test_ui.py::TestLiveStatus`.
