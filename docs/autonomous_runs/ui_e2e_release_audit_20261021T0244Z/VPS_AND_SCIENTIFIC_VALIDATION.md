# VPS and scientific validation (audit 2026-10-21)

Every number below was recomputed in this audit or read from a log this audit wrote.
Approved files were read, never written. The protected-artefact hashes were 19/19 unchanged before and after (`logs/protected_sha256_baseline.txt`, `logs/gates_final.log`).

## 1. Independent recomputation of the approved result

Source: `records/independent_math_summary.json`, `records/independent_scores.csv`, `logs/independent_math.log`.
The recomputation reads the five dimension inputs, ranks them with pandas `rank(pct=True, method="average")` over non-missing values, inverts proximity and safety, applies neutral 0.5 / pool-median imputation, and averages.

| Check | Recomputed | Approved report | Status |
|---|---|---|---|
| Cohort | 90 (14 positive / 76 negative, prevalence 0.156) | 90 (14 / 76) | MATCH |
| Max \|rank diff\| (5 dimensions × 90) | 0.0 | – | MATCH |
| Max \|VPS_equal_5d diff\| | 2.22e-16 | – | MATCH |
| Max \|VPS 4D diff\| | 1.11e-16 | – | MATCH |
| AUROC 5D (Mann-Whitney and sklearn) | 0.775376 | 0.775376 | MATCH |
| AUROC 5D 95% CI (2,000 bootstraps, 0 skipped) | [0.6559, 0.8809] | [0.6559, 0.8809] | MATCH |
| AUPRC 5D (stepwise and sklearn) | 0.42431 | 0.42431 | MATCH |
| AUPRC 95% CI | [0.2263, 0.6792] | [0.2263, 0.6792] | MATCH |
| AUROC 4D | 0.700188 | 0.700188 | MATCH |
| Paired 5D − 4D | +0.0752, CI [−0.0250, +0.1761], 93.4% of draws > 0 | +0.0752, CI [−0.0250, +0.1761]; recorded as `significant: false` | MATCH; **not significant** |
| Distinct scores / ranks in [0,1] | 90 distinct; all finite in [0,1] | – | PASS |
| Neutral imputation | safety 7 compounds, molecular 16 compounds | – | consistent with 10f and 10b coverage |

`scripts/vps_verify.py` (production verifier) was re-run on the final code: **MATCH, 90 compounds, max |diff| 2.22e-16** (`logs/gates_final.log`).
Its "median-imputed (unflagged)" proximity note (Deferiprone, Trimethobenzamide) refers to the raw input. The published score flags both in `dimensions_imputed` (`docs/VPS_EVALUATION.md:80`). This is a known item, not a new defect.

There is a rank-convention sensitivity. The midrank convention gives 5D AUROC 0.774436 instead of 0.775376 and a slightly different rank order. The approved result uses the legacy convention throughout, and the verifier offers both (`--rank-convention`).

## 2. UI and API equal the artefact

Source: `records/api_artifact_consistency.json`.
- `/api/ranking`: 90 rows, max |diff| against `data/vps_scores_v2.csv` = 0.0, 0 issues.
- Candidate pages: 90 of 90 checked, max |diff| 0.0, 0 mismatches.
- Metric surfaces against the evaluation report:
  - live primary AUROC: diff 0.0;
  - validation chart AUROC: diff 0.0;
  - validation chart AUPRC: diff 5.6e-17;
  - "approved" row of the alternatives view: diff 0.0;
  - result-set cohort: equal.

## 3. Weights of every scoring variant

Source: `records/weights_audit.txt`.

| Variant | Vectors | Weight sums | Negative weights | In-sample AUROC (recomputed = logged) | Held-out AUROC (logged) | Selected weights |
|---|---|---|---|---|---|---|
| Equal 5D (approved) | 1 | 1.0 (0.2 × 5) | 0 | 0.7754 | – | equal |
| Grid 4D | 35 | 1.000000 | 0 | 0.7246 | 0.6072 | proximity 0, clinical 0.5, literature 0.25, safety 0.25 |
| Grid 3D | 66 | 1.000000 | 0 | 0.7199 | 0.5840 | clinical 0.6, literature 0.2, safety 0.2 |
| Grid 5D | 70 | 1.000000 | 0 | 0.7740 | 0.6392 | proximity 0, clinical 0.5, literature 0.25, safety 0, molecular 0.25 |

For every grid, the recomputed and logged in-sample AUROC differ by 0.0, and recomputed and saved scores differ by 0.0.
Every grid's held-out AUROC is 0.12–0.14 lower than its in-sample AUROC. Grid-searched weights are therefore overfitted to this cohort, which supports keeping equal weights (`docs/VPS_WEIGHTING_DECISION_2026-10-19.md`).

## 4. Open scientific items (verified status, owner decisions)

| Item | Evidence | State in this audit |
|---|---|---|
| **TD-042: corrected molecular rule `td042_v1`** | candidate AUROC 0.699 [0.557, 0.830]; approved − corrected = +0.076 [0.014, 0.158] | **Not approved, not adopted.** Shown only as a read-only alternative (Validation §7). The publish script exists but was not run. |
| **Stage-03 cohort rebuild (E-056, pagination)** | read-only re-ascertainment: all 90 labels unchanged; **Dopamine would join the cohort**; Ioflupane gains one trial | Code fixed. Rebuilding rewrites protected files, so it is the **owner's decision**. Not run. |
| **Lithium label (B-004)** | 3 lithium-aspartate trials are typed DIETARY_SUPPLEMENT, so the label is 0 (a content-based reading gives 1: AUROC 0.7754 → 0.7573) | Open, owner. |
| **Galantamine / Rifaximin** | listed in the previous overnight `REMAINING_BLOCKERS.md` | Open, owner. |
| **28 trial-role links** | `review` stage worklist | Human review pending. **Not auto-adjudicated.** |
| **Evaluation input fingerprint** | `eval` last success did not fingerprint `data/reproducibility.json`; the dashboard shows "not fingerprinted" and the overall state is `VERIFIED_WITH_GAPS`, not `CURRENT` | Needs an owner-approved `run_stage.py eval` (`eval` rewrites a protected report). |
| **Temporal validity** | the evidence cutoff is unchanged; label and literature date provenance are tracked by 04p/05h | Open methodological limitation (`TECHNICAL_DEBT.md`). |
| **Evidence cutoff, molecular rule, labels** | unchanged; protected hashes 19/19 | Not touched. |

## 5. Missing data
- **Safety:** labels exist for 83 of 90 compounds; 7 receive the neutral 0.5. At the cutoff, 31 compounds are scored and 52 have unknown label history (agent 10f; a diagnostic layer, not in the score).
- **Molecular:** 74 of 90 compounds have targets; 16 receive the neutral 0.5.
- **Proximity:** 2 compounds are imputed with the pool median and flagged.
- Neutral imputation pulls scores toward the middle. It is disclosed on each candidate page ("imputed" markers) and in the data contract panel.

## Verdict
The approved result is **reproduced exactly** and displayed faithfully.
The scientific open items above are **owner decisions**, and none was taken in this audit.
