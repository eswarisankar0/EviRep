# Mathematical audit

**Independent implementation:** `scripts/independent_math.py`.
- It does not import the production fusion, verification or report code.
- Percentile ranks are hand-written (average ties, missing values excluded from the denominator).
- AUROC is computed by explicit pair counting; average precision with tied scores grouped.
- sklearn is used only as a second, external reference.
- **Results:** `records/independent_scores.csv` (per compound, every rank and score) and `records/independent_math_summary.json`.

## Specification (from the code, cited in `evidence/specification_trace.md` §1)

| Item | Definition | Direction / handling |
|---|---|---|
| Proximity | z = (d_real − mean d_rand) / sd d_rand; 100 degree-matched random sets, seed 42 | lower z = closer = better, **inverted** rank; missing raw value → pool median, flagged in `dimensions_imputed` (2: Deferiprone, Trimethobenzamide) |
| Clinical | `max_phase_rank` ∈ {0..5} over accepted pre-cutoff trials (`phases[0]`) | higher = better; heavy ties; `n_trials` recorded, not scored |
| Literature | connected components of the ≤30-PMID author/citation graph | higher = better |
| Safety | `serious_term_count + 5·boxed_warning` | lower = better, **inverted**; no FDA label → NaN → neutral 0.5 (7) |
| Molecular | 0.6·direct + 0.4·pathway | higher = better; no mechanism target → NaN → neutral 0.5 (16) |
| Rank | pandas `rank(pct=True, method="average")` over non-missing values ("legacy"); inverted dimensions use 1 − rank | non-inverted range [1/n, 1], inverted range [0, (n−1)/n] (S-08) |
| Score | `VPS_equal_5d` = (r_prox + r_clin + r_lit + r_safety + r_mol) / 5; `VPS_equal` = mean of the first four | every compound has all five ranks (neutral counts as a rank); denominator always 5 (or 4) |
| AUROC | Mann-Whitney U / (n_pos · n_neg), ties counted ½ | 14 positives, 76 negatives |
| AUPRC | sklearn `average_precision_score` (step-wise AP, ties grouped by threshold) | chance level = prevalence 0.1556 |
| CI | ordinary percentile bootstrap: `default_rng(42)`, 2,000 draws of n rows with replacement, single-class draws skipped and counted, `np.percentile` 2.5/97.5 | 0 draws skipped |
| Paired 5D−4D | same indices for both scores; difference per draw; `np.quantile` 2.5/97.5 | `p_diff_gt_0` = share of draws > 0 (not a p-value) |

## Per-compound verification
- All 450 ranks are recomputed independently. **Max absolute difference: 0** against the stored `r_*` columns.
- `VPS_equal_5d`: max |diff| 2.2e-16 (floating-point summation order). `VPS_equal`: 1.1e-16.
- All ranks are finite and in [0, 1]. There are 90 distinct 5D scores, so no ties affect the ordering. There are no duplicate compounds.
- Rank ranges observed:

  | Dimension | Range |
  |---|---|
  | Proximity | [0, 0.989] |
  | Clinical | [0.056, 0.878] (ties at the top phase) |
  | Literature | [0.011, 1] |
  | Safety | [0, 0.904] (ranked among 83 labelled compounds) |
  | Molecular | [0.074, 0.986] |

- Raw values in the score file equal their source files for every compound and dimension (0 mismatches; `records/data_integrity_summary.json`).
- The UI shows the same file (unchanged; covered by browser checks).

## Statistics

| Quantity | Saved | Independent | Difference |
|---|---|---|---|
| AUROC 5D | 0.775375939849624 | 0.775375939849624 (pair count; sklearn identical) | 0 |
| AUROC 4D | 0.7001879699248119 | 0.700187969924812 | 1e-16 |
| AUPRC 5D | 0.4243147574234414 | 0.42431475742344144 (step-wise) | 0 |
| AUROC 5D 95% CI | [0.6559117720760206, 0.8809429295366793] | [0.6559117720760205, 0.8809429295366794] | 1e-16 |
| AUPRC 5D 95% CI | [0.22629135578499396, 0.6791546701153208] | [0.22629135578499393, 0.6791546701153208] | 3e-17 |
| Paired 5D−4D | +0.07519 [−0.024980, +0.176064] | +0.07519 [−0.024980, +0.176064] | ~1e-16 |
| Share of draws > 0 | 0.935 | 0.934 | one draw exactly 0 in exact arithmetic (S-10) |
| Bootstrap draws used / skipped | 2000 / 0 | 2000 / 0 | — |

**Why the paired interval includes zero.** The point difference (+0.075) is smaller than its sampling spread: SD 0.051 over 2,000 paired resamples of 90 compounds with 14 positives. In 6.5% of draws (report computation) 4D ranks at least as well as 5D. The interval is a percentile interval of draw-wise differences, so it is not computed from the two marginal intervals.

## AUROC function and the RuntimeWarning (S-11)
- **Formula:** `scripts/vps_validation_experiments.py:auroc_cols` is the rank-sum (Mann-Whitney) AUROC with average ranks, so ties count ½. That is correct for 0/1 labels where higher scores mean positive.
- **Defect:** with no positives or no negatives it divided by zero, giving NaN plus a RuntimeWarning. The weight-selection loops then added NaN into their totals and `np.argmax` returned 0, silently choosing the first weight vector.
- **Fixed behaviour:** undefined is an explicit NaN; bad inputs raise; undefined folds are skipped in selection; all-undefined raises; single-class outer test folds raise. It never substitutes 0.5.
- **Tests:**
  - agreement with pair counting on 25 random tie-heavy samples, plus reversed scores giving 1 − AUROC;
  - known values;
  - single-class and empty samples, with warnings promoted to errors;
  - each kind of bad input.
- **Source of the warning:** it came only from a vacuous test, now repaired. Persisted weighting results re-run byte-identically (S-11).

## Cross-validation and tuned weights
- **Nesting:** weights are fitted only on training folds in `06:446-462`, `vps_evaluation_report.py:69-81` and `vps_validation_experiments.py` (nested and matrix modes). The logistic scaler is fitted in-fold. Verified by repaired tests: fold-0 weights do not depend on fold-0 labels.
- **Transductive step:** percentile ranks and imputation are computed once on all 90 compounds. They are label-free but still transductive (documented, TD-036).
- **In-sample results are labelled so:** `VPS_grid_*` = in-sample. Four different "held-out" 5D figures exist (0.639 single split, 0.648 report, 0.688 VVE default, 0.712 VVE matrix); they come from different procedures (C-17). The approved evaluation record uses the report's 0.648.
- **Comparisons:** all are on the identical 90/14 cohort.

## Reconciliation of conflicting numbers

| Metric | Estimand / cohort | Inputs | Method | Seed | Saved | Recomputed | Root cause |
|---|---|---|---|---|---|---|---|
| AUROC 0.7754 vs 0.7763 | 5D, 90/14, same labels | approved vs re-generated `network_proximity.csv` | Mann-Whitney | proximity null, seed 42 | 0.775376 / 0.7763 | 0.775376 from the saved inputs | different Monte-Carlo draw of the proximity null (B-003); 10 seeds give 0.769–0.783 |
| 14 vs 17 positives | 90 compounds | pre- vs post-P1 labels; v1 safety; median missing rule | — | — | 0.747 (17 pos) | not recomputed (superseded inputs) | owner policy P1 removed 3 procedural labels, plus feature fixes D-003/D-004; not a conflict |
| 5D vs 4D | same 90/14 | same file | Mann-Whitney | — | 0.7754 / 0.7002 | identical | different models |
| Equal vs grid | same 90/14 | same | in-sample vs held-out | 42 / 0–19 / 20261019 | 0.774 in-sample, 0.639–0.712 held-out | — | different estimands (in-sample vs held-out) and procedures |
| CI [0.656, 0.881] vs [0.651, 0.881] | same | same | ordinary vs stratified bootstrap | 42 vs 20261019 | both | ordinary reproduced exactly | different interval procedures (S-09) |
| Approved vs `td042_v1` | same 90/14, `labels_equal_baseline` = true | molecular dimension with the drug's own targets excluded from pathway credit | Mann-Whitney | — | 0.7754 / 0.6992 | VVE path agrees to 1.7e-16 (`verification.json`) | different dimension-5 definition, not approved |

## Missing-data alternatives (exploratory, recorded elsewhere)
- Neutral proximity instead of the median: 5D −0.0047 (`vps_validation.json`).
- Midrank convention: 0.7744.
- Missingness is associated with the label: all 7 compounds without a label, and 14 of 16 without a target, are negatives. The neutral rank is therefore not label-free in effect (10h `missingness_vs_label`).
