# VPS weighting decision (2026-10-19)

Evidence:
- `data/_runs/vps_weighting_20261019/` (`weighting_matrix.json`, `unfitted_models.csv`, `fitted_models.csv`), from `./venv/bin/python scripts/vps_validation_experiments.py --matrix` (seed 20261019, 2000 bootstrap draws, 20 repeats);
- `data/_runs/mission_20261019/proximity_seed_sensitivity.csv`.

All metrics are on the 90-compound evaluable pool with 14 positives (prevalence 0.156). A random ranking expects AUROC 0.5, AUPRC 0.156 and P@10 0.156.

## 1. What the VPS estimates
The label is 1 when the compound has an accepted ClinicalTrials.gov Parkinson's trial first posted after the 2020-12-31 cutoff. The snapshot was queried on 2026-10-05; label trials run from 2021-01-13 to 2026-09-08, minus the D-020/TD-032 exclusions.

So the VPS ranks compounds by **evidence associated with continued Parkinson's clinical investigation**. It does not estimate efficacy, benefit or approval. The label definition and cutoff are unchanged.

## 2. Decision
**Equal weights are retained.** The primary score is the equal-weight mean of the five percentile-ranked dimensions:

`VPS = (r_proximity + r_clinical + r_literature + r_safety + r_molecular) / 5`

- `r_d` is the percentile rank. Ties are averaged (rank / n). Lower-is-better dimensions use 1 − rank.
- Unmeasured safety (no label) or molecular (no target) gets the neutral rank 0.5.
- Missing proximity is median-imputed and flagged.

These conventions are D-002, D-004 and D-024. The molecular dimension must use the TD-042 rule (own targets excluded from pathway credit). That correction exists as the verified candidate `data/_candidates/td042_v1/` and **is not yet approved**.

Until it is approved:
- the live baseline is the same formula with the double-counted molecular dimension;
- its 5D metrics (AUROC 0.775) overstate the model and must not be reported as an improvement over 4D.

Reconstruction from source artefacts: `./venv/bin/python scripts/vps_verify.py [--root <root>]`, an independent implementation that does not import stage 06.

**Sensitivity models, reported alongside and never in place of the primary:**
- 4D equal weight (no molecular);
- the cutoff-bounded pair proximity + clinical.

## 3. Why equal weights (nested CV)
Setup:
- 20 repeats; outer 5-fold; inner 4-fold on outer training rows only;
- also evidence-grouped folds (StratifiedGroupKFold on 72 shared-trial components, largest 4 compounds);
- out-of-fold scores pooled per repeat and paired with equal weights on the same splits.

AUROC by method, mean over repeats [2.5–97.5%]. "Better" is the share of repeats where the method beat equal weights.

| Features / folds | Equal | Simplex grid | Shrink toward equal | L2 logistic | Better (simplex · shrink · logistic) |
|---|---|---|---|---|---|
| 4D / stratified | 0.700 | 0.602 [0.518, 0.674] | 0.687 [0.632, 0.700] | 0.562 [0.501, 0.615] | 0 · 0 · 0 |
| 5D original / stratified | 0.775 | 0.712 [0.634, 0.773] | 0.761 [0.732, 0.775] | 0.643 [0.568, 0.712] | 0.05 · 0 · 0 |
| 5D TD-042 / stratified | 0.699 | 0.599 [0.515, 0.673] | 0.688 [0.650, 0.699] | 0.527 [0.466, 0.588] | 0 · 0 · 0 |
| 5D TD-042 / grouped | 0.699 | 0.571 [0.483, 0.630] | 0.672 [0.570, 0.703] | 0.533 [0.459, 0.593] | 0 · 0.05 · 0 |

What the table shows:
- **Learned weights never reliably beat equal weights**: in 0–5% of repeats, under every feature set and fold scheme.
- **Fitted weights are unstable.** Simplex weight SD across folds is 0.08–0.20 per dimension, and their rankings reach Spearman 0.72–0.87 against the equal-weight ranking.
- **Shrinkage almost always chose λ ≈ 0**, i.e. equal weights; its mean weights are within 0.02 of 0.2.

With 14 positives, about 3 per test fold, the data cannot support estimating weights. Equal weighting is the evidence-based choice, not a default.

## 4. Ablations and single dimensions (full cohort; reference = 5D TD-042, AUROC 0.699)
| Model | AUROC [95% CI] | Δ vs reference [CI] | Top-10 overlap |
|---|---|---|---|
| without proximity | 0.692 | −0.008 [−0.116, 0.092] | 0.7 |
| without clinical | 0.619 | −0.080 [−0.192, 0.024] | 0.5 |
| without literature | 0.662 | −0.038 [−0.124, 0.050] | 0.3 |
| without safety | 0.686 | −0.013 [−0.086, 0.068] | 1.0 |
| without molecular (= 4D) | 0.700 | +0.001 [−0.078, 0.078] | 0.9 |
| clinical alone | 0.673 [0.492, 0.829] | | |
| literature alone | 0.645 [0.466, 0.821] | | |
| proximity alone | 0.578 [0.411, 0.743] | | |
| safety alone | 0.543 [0.349, 0.711] | | |
| molecular (TD-042) alone | 0.460 [0.297, 0.620] | −0.239 [−0.415, −0.061] | |
| molecular (original) alone | 0.627 [0.442, 0.812] | | |
| proximity + clinical (cutoff-bounded) | 0.653 [0.480, 0.808] | | |

All differences between multi-dimension models have CIs that include 0. With TD-042 applied, the molecular dimension adds no discrimination: 4D and 5D are equal within 0.001.

The molecular dimension is **retained in the primary model**. It is pre-specified (D-002/D-024), and dropping it because of its evaluation-set AUROC would be tuning on the test labels. The 4D model is reported as a sensitivity, and the owner may decide to drop molecular on scientific grounds (it is not cutoff-bounded; see §6).

## 5. Dimension audit
| Dimension | Hypothesis | Lineage | Direction | Coverage (of 90) | Missing | Temporal | Spearman with others |
|---|---|---|---|---|---|---|---|
| proximity | targets near the PD module in the PPI network | Hetionet v1.0 PPI; stage 02, 100 degree-matched random sets | lower z is better | 88 measured | median (2), flagged | 2017 network (bounded by documentation) | literature 0.43, clinical 0.25 |
| clinical | prior trial maturity predicts continuation | ClinicalTrials.gov, pre-cutoff accepted trials | higher phase is better | 90 | — | first_posted ≤ 2020-11-25; phase from the current record | ≤ 0.25 |
| literature | independent PD literature | PubMed + citation graph (stage 04) | more components is better | 90 | — | **not bounded** (no PMIDs or dates persisted) | proximity 0.43, safety −0.36 |
| safety | lower label risk | openFDA label: serious terms + 5×boxed | lower is better | 83 | neutral 0.5 (7) | **not bounded** (78/83 labels effective > 2020) | literature −0.36, molecular 0.33 |
| molecular (TD-042) | target and pathway link to PD genes | Open Targets 26.09 (allowed datatypes) | higher is better | 74 | neutral 0.5 (16) | **not bounded** | safety 0.33 |

**Monte Carlo noise in proximity.** Stage 02 was not reproducible run to run (E-031, fixed). Across 10 seeds:
- 5D original AUROC ranges 0.769–0.783 and 5D TD-042 0.684–0.705;
- proximity_z Spearman vs published is ≥ 0.991;
- top-10 overlap vs published is ≥ 0.9.

The published proximity file is one draw. Its noise is small next to the bootstrap CI width (±0.12).

## 6. Leakage
Only proximity and clinical are bounded at the cutoff, so the 5D and 4D results are **current-snapshot** evaluations, not leakage-free.

The cutoff-bounded restriction (proximity + clinical, AUROC 0.653 [0.480, 0.808]) is a restricted sensitivity analysis, not a better model. Historical snapshots of literature, labels and Open Targets are not available offline, and none was simulated.

## 7. Eight agents
| Agent | Class | Eligible as an independent numeric dimension? |
|---|---|---|
| 10b Molecular | numeric (dimension 5) | yes, after TD-042; not cutoff-bounded |
| 10c Clinical | numeric via stage 03 (dimension 2); roles diagnostic | already used; roles unresolved (D-020/TD-043) |
| 10f Safety | numeric via stage 05 (dimension 4); FAERS diagnostic | already used; FAERS counts are not incidence |
| 10g Evidence independence | overlapping-evidence diagnostic | no: it describes dependence between dimensions 2 and 3 |
| 10a Literature credibility | categorical, 5/90 | no (coverage) |
| 10e Reproducibility | categorical, 4/90 | no (coverage) |
| 10d Conflict & context | categorical, 19/91 assessed | no (no scale, sparse) |
| 10h Completeness & gap | completeness/confidence | no: it annotates rankings and adds no evidence |

**An eight-agent weighted composite is not defensible.** Three agents already feed the five dimensions. The other five fail on coverage, scale or independence. Even for the five eligible dimensions, nested CV shows weights cannot be learned (§3).
