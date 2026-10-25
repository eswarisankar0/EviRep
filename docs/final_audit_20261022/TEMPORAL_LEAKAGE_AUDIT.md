# Temporal leakage audit (final audit 2026-10-22)

**Prediction time:** 2021-01-01 (`CUTOFF_DATE`, `scripts/03_clinicaltrials_groundtruth.py:53`). A feature is temporally valid only if the information it encodes was available before that date.

**Status: QUANTIFIED, PARTLY ELIMINATED in a candidate.** A fully dated candidate exists and verifies, but one residual leakage path and one unverified risk remain (§3).

## 1. Feature availability by dimension

| Dimension | Source / publication date | Record creation | Record update | Retrieval | Available at the cutoff? | Dated replacement in the candidate |
|---|---|---|---|---|---|---|
| Network proximity | Hetionet v1.0, published 2017 (Himmelstein et al., eLife 2017; 10.7554/eLife.26726) | 2017 | none (frozen release) | Zenodo archive (stage 01) | **Yes** | – (already valid) |
| Clinical maturity | ClinicalTrials.gov; links selected by `studyFirstPostDate` < 2021-01-01 | per trial, all < 2021 | **65 of 177 trials last updated after 2020-12-31** | 2026-10-05 (stage 03); cache 2026-10-15 | **Trial selection yes; field values (phase) as of 2026** | – (see UR-1) |
| Literature independence | PubMed, no date bound, 30 most recent hits (TD-021) | per paper | – | 2026 | **No.** Approved sample: 915 of 1,806 records post-cutoff; the post-cutoff share alone predicts the label (AUROC 0.722, p = 0.009) | 04p cutoff-bounded primary records (earliest journal/e-pub date ≤ 2020-12-31) |
| Safety | openFDA *current* label (TD-022) | label set | current version | 2026 | **No** | 05h: DailyMed version in force on 2020-12-31 for **31/83** labels; 52 have no retrievable pre-cutoff version (current label kept, "mixed") |
| Molecular plausibility | Open Targets 26.09 + current ChEMBL targets (TD-006) | – | 2026 releases | 2026 | **No** | Open Targets 20.11 (released Nov 2020, before the cutoff) + ChEMBL 2020-06 targets. Not available for Dopamine (rebuilt cohort) |
| Label | trials first posted 2021-01-13 … 2026-09-08 (frozen window ends at the 2026-10-05 query, D-010) | – | – | 2026-10-05 / 2026-10-22 | n/a (outcome) | – |

## 2. Measured effect (same cohort, labels and bootstrap; `experiments/model_comparison_*.json`)

| Model | Approved cohort | Rebuilt cohort |
|---|---|---|
| Approved (undated literature, safety, molecular) | 0.775 [0.656, 0.881] | 0.787 [0.672, 0.884] |
| Fully dated 5D (literature, safety-mixed, molecular dated) | 0.689 [0.548, 0.819] | 0.709 [0.557, 0.833] |
| Fully dated + TD-042 | 0.686 [0.544, 0.816] | 0.705 [0.557, 0.831] |
| Fully dated strict safety (from the release audit) | 0.685 [0.528, 0.832] | – |
| Fully dated 4D | 0.679 | 0.699 |
| Dated pair (proximity + clinical only) | 0.653 [0.474, 0.816] | – |
| **All corrections** (dated + TD-042 + P1 + max phase + N_RANDOM 1000) | 0.646 [0.476, 0.808] | **0.667 [0.506, 0.815]** |

**Interpretation:** about 0.08–0.09 AUROC of the approved result depends on information not available at the cutoff. The fully dated estimate is about 0.69–0.71.

## 3. Residual temporal risks (not hidden)
- **Safety ("mixed"):** 52 of 83 labelled compounds have no retrievable pre-cutoff label version, so their current label is used. The strict alternative (those set to neutral) gives 0.685, so the effect is small. Status: **ACCEPTED LIMITATION — DOCUMENTED.**
- **UR-1, clinical phase and status:** 65 of 177 pre-cutoff trial records were updated after the cutoff. Phase is a design attribute and rarely changes, but registry version history was not retrieved, so it is not proven unchanged. Status: **UNRESOLVED — INSUFFICIENT EVIDENCE.** It is resolvable with the ClinicalTrials.gov record-history pages for those 65 trials.
- **Open Targets 20.11 methods:** scoring methods changed between releases, so temporal and method effects cannot be separated (TD-033). Status: **ACCEPTED LIMITATION.**
- **Dopamine molecular** (rebuilt cohort only): not in the 20.11 data, so the current score is kept for 1 of 77 compounds.
- **Label-window end:** the query date (D-010), not a fixed calendar date. A later query can add positives.

## 4. Which score can be the primary scientific result
**Selection criteria, fixed before comparing metrics:**
1. Every feature dated before the cutoff where a dated source exists.
2. No known double counting (TD-042).
3. Feature links meet the same P1 criterion as labels.
4. Cohort built with complete retrieval (E-056 and class-phrase fix).
5. Equal weights.

The candidate meeting all five is **"all corrections" on the rebuilt cohort: AUROC 0.667 [0.506, 0.815], AUPRC 0.409** (prevalence 0.182; n = 77, 14 positives).

The approved 0.775 remains the **historical, undated** result and must be presented as an upper estimate. Adoption is an owner decision (`FINAL_RELEASE_DECISION.md`).
