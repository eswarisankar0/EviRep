# Scientific and VPS audit (2026-10-21)

Detailed row-level evidence from the previous pass (2026-10-20) is in `../scientific_release_audit/`. This file records what was re-verified and what is new in this session.

## What "VPS" means here
- **VPS = "Validated Plausibility Score"** (`README.md:4`). The mission brief's "Vulnerability/Priority Score" does not occur anywhere in the repository.
- It is a research-priority ranking of drugs already tested in Parkinson's disease. It is **not a probability and not efficacy**.

## Canonical formula, verified against the protocol and the code
- **Protocol:** `docs/VPS_FEATURE_CONTRACT.md:10`: `VPS = mean(r_proximity, r_clinical, r_literature, r_safety, r_molecular)` over the 90-compound pool. Decisions D-002 (equal weights) and D-004 (missing data).
- **Code:** `scripts/06_vps_fusion.py` `build_standardized_scores` + `VPS_equal_5d = 0.2 × Σ r_d`.

| Dimension | Raw value | Orientation | Missing |
|---|---|---|---|
| Proximity | `proximity_z` | lower is better (inverted) | pool median, flagged (2 compounds) |
| Clinical | `max_phase_rank` 0–5 | higher is better | never missing in the pool |
| Literature | `effective_independent_count` | higher is better | never missing |
| Safety | serious terms + 5·boxed warning | lower is better (inverted) | no FDA label → neutral 0.5 (7) |
| Molecular | 0.6·direct + 0.4·pathway | higher is better | no target → neutral 0.5 (16) |

- **Ranks:** pandas `rank(pct=True, method="average")` over the non-missing values of the 90-compound pool ("legacy" convention). Raw values are not otherwise normalised.
- **Precision:** scores are stored as full doubles and shown to 3 decimals. 90 distinct values, so there are no ties in the ordering.
- **One version:** every candidate is scored by the same run (`adopted-20261015T015501Z-06`). Components and the total come from the same file, and the UI reads that file; it never recomputes VPS.

**Independent verification (this session):**
- `tests/test_vps_independent_agreement.py` (new, 9 tests) runs the **production** `build_standardized_scores` on the saved raw values. All five ranks and the total agree with a pure-Python implementation written from the specification **within 1e-12**, the documented tolerance; the observed difference is 2.2e-16.
- The same tests cover the missingness flags, determinism, uniqueness, all-tied input, the neutral 0.5, a single compound and infinite values.
- Re-run of the previous audit's `independent_math.py`: ranks differ by 0; AUROC 0.775376, AUPRC 0.424315 and the CIs are identical (`records/independent_math_summary.json`).

## Approved result (unchanged)

| Item | Value |
|---|---|
| Cohort | 90 compounds, 14 positives / 76 negatives |
| Outcome | a qualifying PD interventional trial first posted 2021-01-01 to 2026-10-05 (continued clinical investigation, not efficacy) |
| Evidence cutoff | trials first posted before 2021-01-01 |
| Score version | equal-weight 5D, legacy ranks, D-004 missing policy |
| AUROC 5D | 0.7754 [0.656, 0.881] |
| AUPRC | 0.424 (chance 0.156) |
| 4D | 0.700 [0.567, 0.834] |
| Paired 5D−4D | +0.075 [−0.025, +0.176]: **not significant** |
| Bootstrap | ordinary, seed 42, 2,000 draws |

## TD-042: the molecular double count
- **What is double-counted:** `molecular_agent.py` marks a target pathway as a "PD pathway" when any PD-module gene is in it, **including the drug's own target**. The direct component already credits that same target–PD association, so a target that is itself a module gene makes every one of its pathways count again (`TECHNICAL_DEBT.md:722-740`).
- **Status:**
  - implemented behind a flag (`MolecularAgentConfig.pathway_excludes_drug_targets`, default **off**);
  - tested and independently verified (`data/_candidates/td042_v1/verification.json`, `all_pass`);
  - **not approved** (owner decision, TD-042 OPEN).
- **New this session:**
  - `scripts/compare_result_sets.py` compares any candidate with the approved set on the identical cohort and labels, using the report's own bootstrap. It refuses different compounds or labels.
  - Its output `data/_candidates/td042_v1/comparison.json` is fingerprinted. An independent re-implementation in this folder (`scripts/td042_comparison.py`) agrees.

| | Approved (original rule) | `td042_v1` (corrected rule) | 4D |
|---|---|---|---|
| AUROC | **0.7754** [0.6559, 0.8809] | 0.6992 [0.5570, 0.8299] | 0.7002 [0.5674, 0.8343] |
| AUPRC | 0.4243 [0.226, 0.679] | 0.3068 [0.160, 0.564] | 0.358 |

- **Paired differences:**
  - approved − corrected = **+0.076 [+0.014, +0.158]**: the interval excludes 0;
  - corrected − 4D = −0.001 [−0.075, +0.080].
- **Changes:** 21 molecular scores change (6 positives), which moves 43 molecular ranks. Top-10 overlap is 9 of 10; the largest rank move is 33. Spearman between the two 5D scores is 0.971.
- **Conclusion:** the approved 5D score's apparent advantage over 4D comes from the double-counted pathway credit. With the correction, the molecular dimension adds nothing measurable.
- **What changed and what did not:** this is shown in the UI as a clearly labelled **"Not approved"** alternative (Validation, section 7). The approved result was **not** changed, and the decision stays with the owner.
- **Leakage:** both rules use the same Open Targets 26.09 snapshot with clinical and literature datatypes excluded from scoring. Module selection still uses the overall score, which is an indirect-leakage finding (S-05 in the previous pass).

## Equal versus learned weights (saved held-out results)
Source: `data/_runs/vps_weighting_20261019/fitted_models.csv`. Repeated nested CV: 5 outer folds, 4 inner, weights and scalers fitted in-fold, 20 repeats, out-of-fold scores pooled.

**Held-out AUROC by weighting method:**

| Feature set / folds | Equal | Simplex weights | Shrinkage | L2 logistic |
|---|---|---|---|---|
| 4D stratified | 0.700 | 0.602 | 0.687 | 0.562 |
| 5D original stratified | 0.775 | 0.712 | 0.761 | 0.643 |
| 5D TD-042 stratified | 0.699 | 0.599 | 0.688 | 0.527 |
| 5D TD-042 grouped by shared trials | 0.699 | 0.571 | 0.672 | 0.533 |

- **Every learned method underperforms equal weights out of fold,** in every feature set and both fold schemes. Most intervals of (learned − equal) lie entirely below 0.
- **Equal weights are retained** (D-002). No new weights were introduced.
- In-sample grid AUROCs (e.g. 0.774) are labelled in-sample in the UI and never presented as held-out.

## Evaluation and statistics (re-verified)
- AUROC is computed from continuous scores (Mann-Whitney).
- AUPRC and its chance level use the same 90/14 cohort.
- CIs use the documented ordinary bootstrap; paired comparisons use the same indices.
- **The 14 vs 17 positives** are different label sets, not a conflict. Owner policy P1 (2026-10-14) removed three procedural label trials, after which D-003/D-004 feature fixes followed. 17 is historical only and is shown so labelled.
- **0.7754 vs 0.7763** is the same estimand with a different Monte-Carlo draw of the proximity null (B-003).
- **The leakage limitation remains:**
  - literature, safety and molecular evidence are current snapshots;
  - the time-bounded estimate is about 0.69;
  - the UI states this on the Overview and in Validation §6.
- **No efficacy, benefit or safety claim** is made.

## Ground truth and trial matching (from the previous pass; not re-queried)
- 88 labels are confirmed, Galantamine is unresolved and Lithium is disputed.
- The 28 unresolved review links are all **pre-cutoff feature** links (confirmed by a key join in the previous pass). None is a label trial.
- The intervention-matching policy and its tests are intact (`docs/INTERVENTION_MATCHING.md`, `tests/test_intervention_matcher.py`, `tests/test_trial_role.py`, all passing).
