# Leakage and validation audit

**Sources**
- Data-flow trace with file:line citations: `evidence/leakage_trace.md`, a read-only sub-audit. Its key claims were re-checked; the checks are marked ✔ below.
- Static sentinels: `tests/test_scientific_audit.py::TestLeakageSentinels`.

## Direct leakage: none found
- ✔ **Label producers read no score or dimension file.** Checked in stage 03, `check_studytype`, `filter_by_studytype` and `intervention_matcher`, by sentinel test and trace. Labels are attached after ranking (`06:568-572`).
- ✔ **Feature producers read no label file.** Checked in 02, 04, 05, 08 and `molecular_agent` for `ground_truth_postcutoff`, `label_role_exclusions` and the review worklist.
- ✔ **The molecular score excludes the `clinical` and `literature` Open Targets datatypes** (sentinel test on `allowed_datatypes`).
- ✔ **Post-cutoff trials cannot enter features:** feature rows are filtered by first-posted date before 2021-01-01, every feature row checked; no NCT is in both windows.

## Indirect and temporal leakage (quantified, not fixed)

| Dimension | Source / version | Date field | Retrieval recorded | Post-cutoff information possible | Historical reconstruction |
|---|---|---|---|---|---|
| Proximity | Hetionet v1.0 (2017) | — | release fixed | no outcome information (CtD/CpD edges only remove 28 palliative compounds) | **already historical** |
| Clinical | ClinicalTrials.gov, queried 2026-10-05 | first posted (< 2021-01-01) | yes | **yes:** phase, conditions and interventions read from the 2026 record; ✔ 65 of 177 feature trials last updated on or after 2021; matching rules and aliases are current | partial (registry record history) |
| Literature | PubMed, 30 most recent hits, no date bound; Semantic Scholar citations current | publication year | yes (04p) | **yes:** ✔ `max_date` exists but is unused (`04:62-69`); positives' samples are 67% post-cutoff vs 43% for negatives (trace) | feasible (04p cutoff-bounded query exists) |
| Safety | openFDA current label (`limit=1`) | label effective time | not recorded | **yes:** 78 of 83 labels effective after 2020; 05h label-at-cutoff is diagnostic only | partial (31 of 83 labels have a version at the cutoff) |
| Molecular | Open Targets 26.09, ChEMBL current | — | data version recorded | **yes:** current targets and associations; ✔ the PD module is selected by overall score, which includes outcome-related datatypes (S-05) | feasible (Open Targets 20.11 snapshot cached; module selection must be fixed) |

**A. Reproduction of the approved result from saved inputs.** Exact (`MATHEMATICAL_AUDIT.md`): AUROC 0.775376 [0.656, 0.881].

**B. Time-bounded analyses already recorded** (same 90/14):

| Variant | 5D AUROC |
|---|---|
| Literature bounded | 0.757 |
| Safety at the cutoff | 0.773 |
| Molecular, Open Targets 20.11 | 0.690 (0.704 with 2020 ChEMBL) |
| Everything bounded except phase fields | **0.686 [0.544, 0.821]** |
| Proximity + clinical only | 0.653 |

These were not re-executed in this audit; the values are taken from the saved sensitivity outputs cited in the trace.

**C. Sensitivity of the conclusion.**
- The approved current-snapshot figure (0.775) **is not leakage-free and must not be presented as historical**.
- The best time-bounded estimate (about 0.69) is still above chance, but its interval reaches 0.54.
- **The 5D gain over 4D disappears when the molecular dimension is dated** (≈ 0.70 vs 0.70). The same happens under `td042_v1` (0.699 vs 0.700).

## Selection on the labelled cohort (S-07)
These are design choices made with the 90 labels in view: the final grid weights (in-sample, labelled), the 3-dimension variant, the D-004 missing rule, the P1 label exclusions (adjudicated after their AUROC effect was computed; only positives audited), and intervention-matching revisions. **The equal-weight AUROC is therefore not a pre-registered, untouched estimate.** There is no external validation cohort.

## Missingness and the label
- All 7 compounds without a safety label are negatives, and 14 of 16 without a molecular target are negatives.
- The neutral rank is label-free in construction but not in effect (10h `missingness_vs_label`).

## Cross-validation leakage
- Nested selection is confined to training folds (verified, with repaired tests).
- Percentile ranks and imputation are computed once on all 90 (transductive, label-free; TD-036).
- Compounds that share a trial (S-22) can fall on both sides of a split. Grouped folds are used only in the weighting experiment.

## What remains defensible
- **Defensible:** a retrospective association between the equal-weight evidence score and *continued clinical investigation* in Parkinson's disease. It is above chance under every label resolution examined (0.757–0.800) and under time-bounding (about 0.69), with wide intervals because there are only 14 positives.
- **Not defensible:**
  - efficacy or safety claims;
  - a historical / prospective accuracy claim at 0.775;
  - a claim that the molecular dimension adds value;
  - weights tuned on these labels.
