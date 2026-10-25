# Scientific validity audit (final release, 2026-10-21/22)

**Classification key:**
- **CD** = confirmed defect
- **ML** = methodological limitation
- **UR** = unverified risk
- **R** = recommendation

Every number below was recomputed in this audit from saved files, or read from a saved output whose script is named. **No approved artefact was changed:** protected sha256 19/19 before and after (`logs/`).

## A. Prediction target and cohort

| Item | Verified fact | Source |
|---|---|---|
| Positive | Pool compound with ≥1 qualifying PD interventional trial **first posted ≥ 2021-01-01**: Gate-2 intervention match, PD condition, INTERVENTIONAL with a DRUG/BIOLOGICAL intervention, not in `label_role_exclusions.csv` | `03_clinicaltrials_groundtruth.py:323-330`, `filter_by_studytype.py:13-17`, `06_vps_fusion.py:316-342`, D-010 |
| What the label measures | **Continued clinical investigation, not efficacy** (D-001, D-010). A positive trial may fail; a negative means "no qualifying trial found". | `DECISIONS.md:9-31, 210-234` |
| Cohort | 1,552 Hetionet compounds → 1,524 (no PD palliation edge) → 1,483 (exclusion list) → 91 with an accepted pre-2021 trial → **90** (Mannitol: non-drug study type). Positives 17 → **14** after 3 owner-approved exclusions; 76 negatives; prevalence 0.156. | `vps_scores_v2.csv` (90; label counts 76/14) |
| Duplicates | 0 duplicate compounds (`_require_unique`, `06:157`; eval `cohort.duplicate_compounds` 0) | eval report |
| **ML-1** | The pool contains only drugs **already tried** in PD, so the model ranks "which tried drugs get tried again". 24 of 41 ground-truth compounds lie outside the pool (TD-035). | TD-035 |
| **CD-1 (open, owner)** | The saved stage-03 files predate the pagination fix (E-056). The current code would add **Dopamine**, and Ioflupane gains a trial. The approved cohort was **not** regenerated. | E-056 |
| **ML-2 (open, owner)** | Label edge cases: Lithium (B-004, registry typed DIETARY_SUPPLEMENT), Galantamine (D-011 unresolved), 28 unresolved trial-role links, D-020 feature exclusions proposed but not applied. | worklist; D-011; D-020 |
| **UR-1** | Combined phases keep only `phases[0]` (`03:309`); not quantified. | code |

## B. Temporal and methodological leakage

**Feature availability matrix:**

| Feature | Source date | Respects the 2021 boundary? | Measured effect of a dated replacement on 5D AUROC |
|---|---|---|---|
| Proximity | Hetionet v1.0 (2017) | **yes** | – |
| Clinical maturity | trials first posted < 2021-01-01 (registry queried 2026) | **yes** for trial selection; registry fields (phase/status) are as of 2026 (**UR-2**) | – |
| Literature | PubMed queried 2026 with **no date bound**; 30 most recent hits | **no** (TD-021) | −0.019 [−0.067, 0.030] (bounded count) |
| Safety | current openFDA label | **no** (TD-022) | −0.003 (label at cutoff where available) |
| Molecular | Open Targets 26.09; ChEMBL current | **no** (TD-006/TD-033) | −0.071 (20.11 + ChEMBL 2020-06) |
| Label | trials first posted 2021-01-13 … 2026-09-08 | n/a (outcome) | – |

**New finding, CD-2 (leakage confirmed and quantified):**
- **Result:** the share of post-cutoff papers in each compound's literature sample predicts the label on its own: **AUROC 0.722** (positives median 71% post-2020 vs negatives 40%; Mann-Whitney p = 0.009).
- **What it is not:** no stored sample record contains a label-trial NCT ID, so this is not a copy of the label.
- **What it is:** indirect leakage. Research activity after 2020 tracks the later trials.

**New result, E1: all dated inputs combined** (`experiments/release_experiments.py`; equal weights, approved rules, nothing tuned):

| Model | AUROC [95% CI] | AUPRC [95% CI] | Paired Δ vs approved [95% CI] |
|---|---|---|---|
| Approved 5D (reference) | 0.775 [0.656, 0.881] | 0.424 [0.226, 0.679] | – |
| **Fully dated 5D** (safety: label at cutoff, else current) | **0.689 [0.548, 0.819]** | 0.334 [0.155, 0.561] | −0.087 [−0.206, 0.030] |
| Fully dated 5D (safety strict: at cutoff, else neutral) | 0.685 [0.528, 0.832] | 0.342 [0.163, 0.588] | −0.091 [−0.245, 0.062] |
| Fully dated 4D (no molecular) | 0.679 [0.540, 0.818] | 0.316 [0.149, 0.549] | −0.097 [−0.211, 0.016] |
| Dated pair (proximity + clinical only) | 0.653 [0.474, 0.816] | 0.314 [0.161, 0.591] | −0.122 [−0.306, 0.069] |

**Cross-check:** the dated 4D (0.6786) and the pair (0.6532) reproduce the independently computed values in `data/_runs/literature_cutoff_20261019/` exactly.

**Interpretation:**
- The approved 0.775 is best read as an **upper estimate**. With every feature restricted to pre-2021 data, the score still ranks above chance (lower CI bound about 0.53–0.55) but at about 0.69.
- The molecular dimension's apparent added value disappears (fully dated 5D ≈ 4D).

**Other leakage checks:**
- **Shared evidence between predictor and label:** a single trial cannot be both a feature and a label, because the split is by date. However, 17 pre-cutoff trials are shared across compounds and inflate several compounds' clinical feature (TD-023). Shared label trials: 4 pairs (eval `duplicate_evidence`).
- **Molecular datatype leakage:** Open Targets `clinical` and `literature` datatypes are excluded (`molecular_agent.py:165`). D4 reuse check: 0 compounds (10g).
- **TD-042 (CD-3, open, owner):** the pathway credit double-counts a drug's own target. The corrected rule gives 0.699; it is not approved.

## C. Evaluation integrity

| Check | Result |
|---|---|
| Positives / negatives / prevalence | 14 / 76 / 0.1556, from the approved CSV |
| AUROC, AUPRC, CIs | recomputed exactly in the previous audit (`docs/autonomous_runs/ui_e2e_release_audit_20261021T0244Z/VPS_AND_SCIENTIFIC_VALIDATION.md`) and again here (E1 reference row: same values, seed 42, 2,000 resamples) |
| Same cohort and labels across models | yes: variants, baselines and ablations are computed from one data frame in stage 06; experiments assert n = 90 and 14 positives |
| Grid-searched weights | the `VPS_grid_*` columns are **in-sample** (weights chosen on all data). Honest held-out values: 5D 0.639, 4D 0.607, 3D 0.584 (nested CV, `06:423-480`). Figure 1 hatches them as in-sample. |
| Bootstrap | percentile, not stratified, single-class resamples skipped (0 skipped) |
| Validation type | **internal, retrospective, temporal split only. No external validation dataset exists.** Nothing in the UI or docs claims external validation. The name "Validated Plausibility Score" (README:4) should not be read as external validation (**R-1**). |
| Small sample | 14 positives; AUROC CI width ≈ 0.22; 5D-vs-4D difference not significant (+0.075 [−0.025, 0.176]) |

## D. Dimension-level findings

| ID | Class | Finding |
|---|---|---|
| D-prox | ML | 100 degree-matched draws ("quick test"; TD-011). The minimum of 10 draws and z = 0 when σ = 0 are undocumented. Seed fixed (42); a global RNG stream means pool changes re-draw every compound (TD-010). |
| D-lit | ML + CD-2 | Components of a shared-author/citation graph measure **independence, not study quality** (quality is the separate diagnostic 10a). Not cutoff-bounded; recency-ordered 30-paper cap; author-string collisions undocumented. |
| D-safe | ML | Risk = terms + **5 × boxed warning**; the 5 is undocumented (R-2). Substring matching, no negation. Unlabelled → neutral 0.5 (7 compounds, all negatives; 10h flags "missingness associated with the label", UR-3). |
| D-mol | ML + CD-3 | 0.6/0.4 weights set a priori. Not cutoff-bounded. TD-042 open. 16 no-target compounds → neutral 0.5. |
| TD-009 | resolved in code | Saved literature data shows 0 citation-lookup failures for all 90 compounds (note added to TD-009). |

## Summary for reviewers
- The **target is a proxy** (later trial activity), and the evaluation is **internal and retrospective**.
- Leakage is **confirmed** for the literature, safety and molecular dimensions.
- With all inputs dated, **AUROC ≈ 0.69** (CI lower bound ≈ 0.53–0.55); the approved 0.775 is an upper estimate.
- None of this changes approved artefacts. Adopting a dated score, TD-042 or a cohort rebuild are **owner decisions**.
