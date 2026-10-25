# Eight-agent VPS contribution audit (2026-10-20)

**Question:** which agent outputs belong in the numeric VPS?

**Population** (every experiment below): the 90-compound evaluable pool, 14 positives / 76 negatives (prevalence 0.156). The label is an accepted ClinicalTrials.gov PD trial first posted after 2020-12-31.

**Random expectation:** AUROC 0.5, AUPRC 0.156, P@10 0.156.

Nothing here changes the approved score.

## 1. Agent-to-score contribution matrix
| Agent | In approved VPS? | Kind | Coverage (persisted, verified 2026-10-20) | Direction interpretable? | Overlap | Verdict |
|---|---|---|---|---|---|---|
| 10a Literature credibility | no | categorical per paper (study-design tier) | 89/90 assessed, 1 NO_RESULTS, 0 failed | no pre-specified direction for "predicts continued investigation" | the same papers as literature (04/04p) | **diagnostic** |
| 10b Molecular | **yes**, via stage 08 (dimension 5) | numeric | 74 with targets; 16 unmeasured (neutral) | yes (higher = more PD-linked biology) | own-target double counting (TD-042); not cutoff-bounded | **contributing; policy decision pending** |
| 10c Clinical | **yes**, via stage 03 (dimension 2); agent layer no | numeric (max phase) + diagnostic roles/results | 90 compounds, 177 trials, 0 failed | phase yes; registry p-values not used | the same trials appear in the literature for 20 compounds | **contributing; 28 links await human review** |
| 10d Conflict & context | no | categorical (pairwise claim relations) | 19/91 assessed (72 insufficient) | no; arms and directions are unlabelled in the registry | curated claims shared with 10e | **diagnostic** |
| 10e Reproducibility | no | categorical per finding | 14 findings, 4 compounds | no | 10d claims | **diagnostic** |
| 10f Safety | **yes**, via stage 05 (dimension 4); FAERS no | numeric (label risk) + diagnostic | label 83 retrieved, 7 no record, 0 failed; at the cutoff 31 scored / 52 unknown | yes (lower risk = higher rank); FAERS counts are not incidence | Spearman −0.36 with literature | **contributing** |
| 10g Evidence independence | **yes** for literature (stage 04 components); cross-source checks no | dependence diagnostics | D2 assessable 89/90 | no: it describes dependence, not plausibility | it *measures* overlap | **diagnostic / overlap gate** |
| 10h Completeness & gaps | no | completeness annotation | 90 × 12 domains, 361 gaps | no: completeness ≠ biology | aggregates the others | **annotation only** |

Three agents (10b, 10c, 10f) plus 10g's literature measure already feed the five dimensions.

**Architecture E** (adding agent-derived numeric dimensions) is **rejected on contract grounds**, before any label is looked at:
- **10d / 10e:** coverage of 4–19 compounds.
- **10a:** no pre-specified direction, and the same papers already feed the literature dimension.
- **10g / 10h:** they describe the evidence rather than the compound.

Fitting such a dimension and keeping it if its AUROC looked good would select the formula on the evaluation labels, so this was deliberately not done.

**Architecture F** (hybrid) is the current design, and the recommended one:
- every agent runs and reports;
- the numeric score uses only the defensible dimensions;
- 10c's review queue is a human gate;
- 10h annotates completeness;
- 10g flags overlap.

## 2. Candidate architectures (equal weights; paired bootstrap 2000 draws, seed 20261019)
Source: `scripts/vps_architecture_comparison.py` → `data/_runs/vps_architecture_20261020/`.

| Architecture | AUROC [95% CI] | AUPRC | P@10 | Δ AUROC vs A [CI] | Top-10 overlap with A |
|---|---|---|---|---|---|
| **A approved 5D** | 0.775 [0.651, 0.881] | 0.424 | 0.50 | — | 1.0 |
| B bounded literature + safety at cutoff | 0.752 [0.629, 0.861] | 0.381 | 0.40 | −0.024 [−0.073, 0.026] | 0.9 |
| C 4D (no molecular) | 0.700 [0.560, 0.830] | 0.358 | 0.40 | −0.075 [−0.176, 0.024] | 0.9 |
| C-bounded 4D | 0.679 [0.536, 0.816] | 0.316 | 0.30 | −0.097 [−0.210, 0.013] | 0.7 |
| D TD-042 5D (candidate) | 0.699 [0.557, 0.830] | 0.307 | 0.40 | −0.076 [−0.155, −0.015] | 0.9 |
| A-dated (approved rule, molecular inputs dated ≤ cutoff) | 0.704 [0.573, 0.831] | 0.296 | 0.20 | −0.071 [−0.173, 0.030] | 0.6 |
| D-dated (TD-042 rule, dated inputs) | 0.703 [0.571, 0.831] | 0.295 | 0.20 | −0.072 [−0.173, 0.029] | 0.6 |
| B + D-dated (everything bounded except clinical phase fields) | 0.686 [0.544, 0.821] | 0.314 | 0.20 | −0.089 [−0.209, 0.027] | 0.7 |

These reproduce the previous report's values (0.775 / 0.700 / 0.704 / 0.703).

D is the only architecture whose interval excludes 0. That is expected, not a defect of TD-042: A counts the drug's own target twice (direct component and pathway credit). The drop measures how much of A depends on that double count.

**Calibration** is not reported: the VPS is a mean of percentile ranks, not a probability.

### Learned weights
Nested CV with stratified and trial-grouped folds, inner-fold selection only; see `docs/VPS_WEIGHTING_DECISION_2026-10-19.md` §3 and `data/_runs/vps_weighting_experimental_20261020/`. Simplex, shrinkage and L2-logistic weights beat equal weights in 0–10% of repeats, on both the approved and the cutoff-bounded feature sets. Their weights are unstable (fold SD up to 0.27). **Equal weights stay.**

### Overlap and leakage
| Check | Result |
|---|---|
| Clinical ↔ literature: same-trial papers | 20 compounds (10g D2 = the independent `vps_evidence_overlap.py`). Removing them: +0.002 [−0.004, 0.009] |
| Label-trial reports inside features | 0 |
| Temporal: literature bounded | −0.019 |
| Temporal: safety at cutoff | −0.003 |
| Temporal: molecular with every input dated | −0.071 (approved rule) / +0.004 (TD-042 rule vs D) |

Temporal and Open Targets *method* changes cannot be separated (TD-033).

**Seed sensitivity:** across 10 proximity seeds, the 5D AUROC ranges 0.769–0.783 (decision document §5).

## 3. Interpretation and recommendation
- **No architecture is statistically better than A.** Every CI on Δ against A includes 0, except D, which is lower by construction.
- **A's lead over the 4D model is not robust to temporal validity.** With dated molecular inputs, 5D (0.704) equals 4D (0.700) under either molecular rule.
- **With 14 positives, a single repeated evaluation cannot separate architectures** whose AUROC differs by less than about 0.1. Selecting among A–D on these labels would itself be tuning.

**Recommendation (owner decision; nothing changed):**
1. Keep the equal-weight design (architecture F around the numeric core).
2. Replace the molecular rule with TD-042, or drop molecular from the primary score. Either way, report A-dated / D-dated as the honest temporal estimate. The current A figure (0.775) should not be cited without its caveats.
3. Adopt cutoff-bounded literature (04p) and safety (05h) as the reported sensitivity. Promote them to primary only through a new validated stage-06 lineage.
4. Do not add numeric dimensions from 10a, 10d, 10e, 10g or 10h.

**Owner decisions required:** the molecular policy (TD-042 / drop / keep); whether to adopt bounded literature and safety; whether to re-freeze labels (registry drift).
