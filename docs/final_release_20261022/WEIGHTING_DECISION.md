# VPS weighting: controlled experiments and decision (final release, 2026-10-21/22)

**Decision: retain the approved equal weights (0.2 × 5).** No artefact, default or UI value was changed.

**Script:** `experiments/release_experiments.py`. It reads `data/vps_scores_v2.csv` and saved sensitivity outputs, and writes only to `experiments/out/`.

## Baseline (reproduced)
- **Five ranks:** legacy percentile ranks; proximity and safety inverted; unmeasured safety and molecular get the neutral 0.5; missing proximity gets the pool median.
- **Score:** VPS = mean of the five ranks.
- **Reproduction:** `scripts/vps_verify.py` gives MATCH, max |diff| 2.2e-16 (`logs/baseline.txt`).
- **Metrics:** AUROC 0.7754 [0.656, 0.881]; AUPRC 0.4243 [0.226, 0.679]; prevalence 0.156.

## Alternatives tested (small, pre-specified set; no unrestricted search)

| # | Alternative | Design | Result |
|---|---|---|---|
| 1 | Equal weights | not fitted, so in-sample = out-of-fold | AUROC **0.775** |
| 2 | Constrained non-negative weights summing to 1 (existing stage-06 grid) | nested 5-fold CV, weights chosen inside training folds | held-out 5D **0.639** (vs in-sample 0.774): overfit (`vps_variant_results.csv`) |
| 3 | L2-regularised logistic regression on the 5 ranks | repeated stratified 5-fold ×20, C ∈ {0.01, 0.1, 1, 10} chosen by inner 4-fold CV **within** each training fold; identical folds for all models; pooled out-of-fold AUROC | mean **0.596** (range 0.505–0.659); worse than equal weights in **20 of 20** repeats (Δ mean −0.179, range −0.271 to −0.117) |
| 4 | Sensitivity analysis | 2,000 Dirichlet(1) weight vectors, **no selection** | AUROC median 0.705; 95% range 0.607–0.784; equal weights exceed 95.3% of draws |

**Weight instability (alternative 3, 100 fits):**

| Dimension | Coefficient mean | SD | Share negative |
|---|---|---|---|
| Proximity | 0.15 | 0.39 | 18% |
| Clinical | 1.09 | 0.98 | 0% |
| Literature | 0.90 | 0.89 | 0% |
| Safety | 0.44 | 0.56 | 18% |
| Molecular | 1.00 | 0.94 | 0% |

The chosen regularisation strength was spread across all four values (1.0: 36, 10: 31, 0.01: 22, 0.1: 11).

## Reasoning
1. **The data cannot identify stable weights.** With 14 positives, coefficients vary as much as their size, and the selected regularisation is unstable.
2. **Every learned weighting is worse on held-out data** than equal weights: 0.596–0.639 vs 0.775.
3. **The weights matter a lot** (alternative 4: 0.61–0.78). Equal weights sit near the top of that range. Because they were fixed a priori and not selected, this is not overfitting, but it means **0.775 should not be read as weight-independent**. A reviewer could fairly call it a favourable draw.
4. **Under the decision rule** (leakage-controlled, held-out gain, stable, interpretable, reproducible, governance-approved), no alternative qualifies.

## Caveats
- **Rank features:** the percentile ranks are label-free and computed on the whole pool (transductive). They carry no label information, but test-fold compounds do influence the training-fold rank values. This is standard for rank-transformed features and is noted for completeness.
- **Out-of-fold vs in-sample:** the equal-weight "out-of-fold" AUROC equals its in-sample value, because nothing is fitted.
- **No causal reading:** none of these results implies a causal contribution of any dimension.
