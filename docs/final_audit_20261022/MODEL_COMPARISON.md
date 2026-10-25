# Model comparison (final audit 2026-10-22)

**Methodology (identical for every row):**
- Score: equal-weight mean of legacy percentile ranks (`VPS_equal_5d`; 4D = without molecular).
- Each candidate is the real stage-06 code on substituted inputs (`experiments/build_candidates.py`), independently checked by `scripts/vps_verify.py`: **MATCH for all 18 candidates** (9 per cohort) (`experiments/candidates/*/*/build_summary.json`).
- Metrics: AUROC/AUPRC with a 2,000-resample percentile bootstrap (seed 42); the paired difference vs approved is on shared compounds (`experiments/evaluate_candidates.py`).
- **Every number below was computed today.** Nothing was tuned on labels; no candidate was chosen by its metric.

## Approved cohort (90 compounds, 14 positives; prevalence 0.156)

| Candidate | n/pos | 5D AUROC [95% CI] | 5D AUPRC | 4D AUROC | 5D − 4D [95% CI] | Δ vs approved [95% CI] |
|---|---|---|---|---|---|---|
| Approved (reproduced) | 90/14 | 0.775 [0.656, 0.881] | 0.424 | 0.700 | +0.075 [−0.025, 0.176] | 0 |
| TD-042 | 90/14 | 0.699 [0.557, 0.830] | 0.307 | 0.700 | −0.001 [−0.075, 0.080] | −0.076 [−0.158, −0.014] |
| P1 feature links | 76/13 | 0.746 [0.608, 0.867] | 0.396 | 0.671 | +0.075 [−0.036, 0.193] | +0.012 [−0.008, 0.035] (n=76) |
| Max phase | 90/14 | 0.769 [0.649, 0.874] | 0.418 | 0.700 | +0.069 | −0.007 [−0.021, 0.004] |
| Dated | 90/14 | 0.689 [0.548, 0.819] | 0.334 | 0.679 | +0.010 [−0.045, 0.070] | −0.087 [−0.206, 0.030] |
| Dated + TD-042 | 90/14 | 0.686 [0.544, 0.816] | 0.314 | 0.679 | +0.007 | −0.089 [−0.208, 0.026] |
| Dated + TD-042 + P1 | 76/13 | 0.643 [0.479, 0.806] | 0.325 | 0.672 | −0.029 | −0.090 [−0.231, 0.058] |
| All corrections (+ max phase, N_RANDOM 1000) | 76/13 | 0.646 [0.476, 0.808] | 0.365 | 0.669 | −0.023 [−0.079, 0.035] | −0.088 [−0.232, 0.069] |

## Rebuilt cohort (E-056 + class-phrase fix; 91 compounds, 15 positives; prevalence 0.165)

| Candidate | n/pos | 5D AUROC [95% CI] | 5D AUPRC | 4D AUROC | 5D − 4D [95% CI] |
|---|---|---|---|---|---|
| Approved rules | 91/15 | 0.787 [0.672, 0.884] | 0.440 | 0.719 | +0.068 [−0.025, 0.167] |
| TD-042 | 91/15 | 0.716 [0.575, 0.832] | 0.337 | 0.719 | −0.004 [−0.081, 0.075] |
| P1 | 77/14 | 0.755 [0.619, 0.872] | 0.418 | 0.690 | +0.065 [−0.034, 0.172] |
| Max phase | 91/15 | 0.781 [0.663, 0.879] | 0.438 | 0.720 | +0.060 |
| Dated | 91/15 | 0.709 [0.557, 0.833] | 0.404 | 0.699 | +0.010 [−0.042, 0.067] |
| Dated + TD-042 | 91/15 | 0.705 [0.557, 0.831] | 0.382 | 0.699 | +0.006 |
| Dated + TD-042 + P1 | 77/14 | 0.669 [0.510, 0.819] | 0.401 | 0.696 | −0.027 |
| **All corrections — recommended primary** | **77/14** | **0.667 [0.506, 0.815]** | **0.409** (prevalence 0.182) | **0.693** | **−0.026 [−0.081, 0.027]** |

## Supporting sensitivity analyses (approved cohort)
- **Weights** (`docs/final_release_20261022/WEIGHTING_DECISION.md`):
  - L2 logistic regression under nested repeated CV: 0.596, worse than equal weights in 20/20 repeats;
  - constrained grid held-out: 0.639;
  - 2,000 random weightings: 0.607–0.784.
  - **Equal weights retained.**
- **Proximity Monte Carlo** (`experiments/proximity_seed_sensitivity.json`): 100 draws, seeds 1–3, 0.769–0.783; 1,000 draws, seeds 42 and 7, 0.775 and 0.776.
- **Boxed-warning multiplier** k ∈ {0, 1, 3, 5, 10}: 0.767–0.779 (`experiments/constants_sensitivity.json`).
- **Direct-only molecular** (not adopted; see MOLECULAR_CORRECTION_REPORT): 0.759.
- **From-source reproduction with current code** (02 → 06 → eval): 0.776 vs approved 0.775.

## Conclusions
1. **Each correction moves the result in the same direction or not at all.** The approved 0.775 is an **upper estimate**.
2. **The fully corrected, cutoff-respecting score** ranks above chance (0.667; the CI lower bound is 0.506, just above 0.5). Evidence for discrimination is **weak**.
3. **The molecular dimension adds nothing** once double counting and dating are fixed (5D − 4D ≈ −0.03, CI spans 0).
4. **Validation is internal and retrospective.** No external validation dataset exists. AUROC is a ranking statistic, **not** a probability that a drug works; the label measures later trial activity, not efficacy.
