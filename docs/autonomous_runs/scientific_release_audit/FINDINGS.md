# Findings ledger: scientific release audit (2026-10-20)

**Severity scale**
- **BLOCKER:** prevents sign-off.
- **HIGH:** changes or can change a scientific conclusion, the cohort or a label.
- **MEDIUM:** a validity or reliability risk with bounded impact.
- **LOW:** documentation or provenance.

**Status values**
- **FIXED:** code or documentation changed, regression-tested, verified.
- **OPEN-OWNER:** needs a scientific decision; not changed.
- **OPEN:** a known limitation, documented.
- **VERIFIED-OK:** the claim was independently confirmed.

Evidence paths are relative to this folder.

## Summary

| ID | Severity | Title | Status |
|---|---|---|---|
| S-01 | HIGH | Stage 03 kept only the first 20 search results per compound (no pagination) | FIXED in code; approved outputs unchanged; re-run is OPEN-OWNER |
| S-02 | HIGH | Lithium's negative label depends on the registry's intervention-type field | OPEN-OWNER |
| S-03 | MEDIUM | Token matching credits class phrases and background-therapy "other names" to a compound | OPEN (TD-023 / E-014) |
| S-04 | MEDIUM | Disputed label roles: Galantamine unresolved; Rifaximin is a regimen component; Lidocaine owner-confirmed | OPEN-OWNER |
| S-05 | MEDIUM | Molecular PD module selected by overall Open Targets score (includes outcome-related datatypes) before the datatype filter | OPEN-OWNER |
| S-06 | HIGH | Literature, safety and molecular evidence are current snapshots; trial phase comes from 2026 records | OPEN (TD-033), quantified |
| S-07 | MEDIUM | Several analysis choices were made with the full labelled cohort in view | OPEN, documented |
| S-08 | LOW | The "legacy" rank convention is asymmetric for inverted dimensions | OPEN-OWNER (D-024 / TD-040) |
| S-09 | LOW | Bootstrap described as stratified but ordinary; two CI procedures coexist | FIXED (documentation) |
| S-10 | LOW | `p_diff_gt_0` is a share of bootstrap draws, not a p-value | OPEN, documented |
| S-11 | MEDIUM | `auroc_cols` silently selected the first weight vector when every validation fold was single-class; one test was vacuous | FIXED + tests |
| S-12 | LOW | UI stage registry still said "17 positives / 90" | FIXED + test |
| S-13 | MEDIUM | Evaluation report input `data/reproducibility.json` not fingerprinted | OPEN-OWNER (re-run reproduces byte-identically) |
| S-14 | LOW | Approved runs 02/06/eval have no code fingerprint | OPEN (TD-046) |
| S-15 | LOW | 0.7754 vs 0.7763: same estimand, different Monte-Carlo draw of the proximity null | VERIFIED, documented (B-003) |
| S-16 | LOW | 14 vs historical 17 positives: different labels and features, not a conflict | VERIFIED, documented |
| S-17 | MEDIUM | Agent pipeline defects A-1 to A-7 | FIXED + tests; outputs regenerated with identical content |
| S-18 | LOW | 25 code/documentation contradictions | 9 FIXED; the rest documented or owner decisions |
| S-19 | LOW | Core stages 00–06 have no runner timeout (08 now has one) | OPEN |
| S-20 | LOW | 4 alias searches rejected by the registry (special characters) | OPEN (unverified aliases) |
| S-21 | MEDIUM | No "indeterminate" label class; contested labels counted as 0/1 | OPEN-OWNER, sensitivity reported |
| S-22 | MEDIUM | 17 pre-cutoff trials are shared by 31 compounds, so compounds are not independent units | OPEN (TD-038) |
| S-23 | MEDIUM | `td042_v1` independently re-verified on the identical cohort | VERIFIED; NOT ADOPTED (owner) |
| S-24 | LOW | The audit's alias lookups wrote 9 Open Targets cache files into `data/cache/molecular` | FIXED (files moved out; audit tools use an isolated cache) |
| V-01 | — | Approved ranks, scores, AUROC, AUPRC, intervals, paired difference | VERIFIED-OK (independent implementation) |
| V-02 | — | All 90 labels re-derived and re-ascertained against the live registry | VERIFIED-OK except S-02 and S-04 |
| V-03 | — | Cross-file integrity (keys, joins, ranges, raw values, fingerprints) | VERIFIED-OK |

---

## Details

### S-01 · HIGH · Search truncated at 20 results
- **Files:** `scripts/03_clinicaltrials_groundtruth.py:75-79` (old `pageSize: 20`, no `nextPageToken`).
- **Evidence:** `records/reascertain/reascertain_summary.json`. Twelve compounds returned exactly 20 rows in `clinicaltrials_match_audit.csv`. The live registry total hit counts are: Dopamine 280, Phenol 137, Benzocaine 65, Cisplatin 55, Paclitaxel 51, Carboplatin 49, Methyldopa 37, Fluorouracil 29, **Ioflupane I 123 27** (in the cohort), Docetaxel 25, Norepinephrine 25, Pemetrexed 21.
- **Re-ascertainment** (all pages, stage 03's own gates, read-only) found:
  - **Ioflupane I 123:** one missed pre-cutoff trial (NCT04193527, Phase 3, 2019). Its clinical dimension is already Phase 3, so no rank changes.
  - **Dopamine:** not in the approved cohort, but has a genuine pre-cutoff trial (NCT04332276, A-dopamine, 2020) and a genuine post-cutoff trial (NCT07214285, 2025). Several other "Dopamine" matches are false (see S-03). With full pagination Dopamine would join the cohort, probably as a positive, once the false matches are removed.
  - **No label of the 90 changes.** Every post-cutoff label set reproduces exactly (`ground_truth_row_audit.csv`, `post_saved_equals_reascertained` = True for all 90).
- **Impact:** the approved cohort is incomplete by at least one compound (Dopamine). The 90 labels are unaffected.
- **Correction:** `search_trials` now follows every page (100 per page, at most 50 pages; any failed page fails the whole search). Tests: `TestStage03Pagination` (both cases).
- **Not done:** re-running stage 03. That needs about 1,500 online searches and rewrites protected cohort and label files, which is a scientific change for the owner.

### S-02 · HIGH · Lithium label
- **Evidence:** NCT06099886 ("Repurposing Lithium for Parkinson's Disease", Phase 1, 2023), NCT06339034 (RCT, Phase 1/2, 2024) and NCT06592014 (extension, 2024). All are interventional, with Parkinson's conditions and lithium aspartate in the experimental (or treatment) arm. The registry types the intervention `DIETARY_SUPPLEMENT`, so `filter_by_studytype.py` (which keeps DRUG/BIOLOGICAL only) drops them and Lithium = 0.
- **Background:** TD-023 notes this filter effect for Melatonin (whose label is unchanged) but says no checked label changed. Lithium was not among the checked compounds.
- **Impact:** under the content-based reading of "qualifying PD interventional trial", Lithium would be 1. AUROC 5D would go 0.7754 → 0.7573 (`records/label_sensitivity.json`).
- **Status:** not changed. The study-type rule is the documented approved rule, and changing it is an inclusion-criterion change. **Owner decision.**

### S-03 · MEDIUM · Matcher class collisions
- **Dopamine:** matched on "Bromocriptine and other dopamine agonists", "Cerebral Dopamine Neurotrophic Factor", "embryonic dopamine cell implant", "dopamine progenitor cell" (`reascertain_trials.csv`).
- **In the cohort:**
  - Lisuride gets NCT00605683 (a safinamide trial) through a background-therapy otherName list. This is known as E-014; Lisuride keeps its other qualifying trials.
  - Donepezil gets two `[11C]donepezil PET` imaging studies (pre-cutoff features). They are a diagnostic, not a therapeutic, role.
- **Impact on approved numbers:** none found. Pool membership and max phase are unchanged for Lisuride and Donepezil, which have other qualifying trials. The general feature-role audit is open (TD-023 / TD-038).

### S-04 · MEDIUM · Contested label roles

| Compound | Situation | Decision |
|---|---|---|
| Galantamine | NCT07284290 is BASIC_SCIENCE, DLB/PDD, with galantamine in an ACTIVE_COMPARATOR open sub-cohort | UNRESOLVED (D-011) |
| Lidocaine | Stellate-ganglion block trials | CONFIRMED by the owner (D-011) |
| Rifaximin | NCT04730245 gives rifaximin inside a microbiota-modification regimen (enema + rifaximin + PEG) | "CONFIRMED" in the CASE_STUDIES table, but the combination role is not separately adjudicated |
| Methylphenidate, Mirabegron, Quetiapine | Arms typed ACTIVE_COMPARATOR | Confirmed as the investigated drug (CASE_STUDIES §9) |

Sensitivity: 5D AUROC ranges 0.757–0.800 across every resolution of the disputed labels (`records/label_sensitivity.json`).

### S-05 · MEDIUM · Molecular module selection
- `molecular_agent.py:728-760` takes the first 300 associated targets in the API's overall-score order, then keeps only genes with allowed datatypes.
- Membership in the top 300 can depend on `clinical` / `literature` evidence, which is excluded from scoring but not from selection.
- Fixing this changes the molecular dimension. **Owner decision** (relates to TD-042 / B-001).

### S-06 · HIGH · Temporal validity (TD-033)
- **Current snapshots:** literature has no date bound (`04:62-69`); safety uses the current openFDA label (78 of 83 effective after 2020); molecular uses Open Targets 26.09.
- **Clinical phase:** read from 2026 records. 65 of 177 pre-cutoff feature trials were last updated on or after 2021-01-01 (verified from `data/cache/ctgov_precutoff_trials.json`).
- **Recorded time-bounded sensitivities** (same 90 compounds, 14 positives; `evidence/leakage_trace.md` §9):

  | Variant | 5D AUROC |
  |---|---|
  | Literature bounded | 0.757 |
  | Safety label at the cutoff | 0.773 |
  | Molecular, Open Targets 20.11 | 0.690 (0.704 with 2020 ChEMBL) |
  | All bounded except phase | 0.686 [0.544, 0.821] |

- **Conclusion:** the approved 0.775 is **not leakage-free**. The time-bounded estimate is about 0.69, and the 5D gain over 4D disappears.

### S-07 · MEDIUM · Choices made with the labelled cohort in view
These were all decided on the full 90 labelled compounds:
- the final grid weights (`06:465`, in-sample, labelled as such);
- the 3-dimension variant (from a full-cohort ablation);
- the D-004 missing-data rule;
- the P1 label policy (adjudicated after its AUROC effect, 0.747 → 0.781, had been computed; positives only);
- the intervention-matching revisions (made after ranking).

None is hidden, but the equal-weight AUROC is not a pre-registered estimate.

### S-08 · LOW · Rank convention
- Legacy `rank(pct=True)` gives non-inverted dimensions the range [1/n, 1] and inverted ones [0, (n−1)/n].
- The midrank convention changes the ordering (AUROC 0.7744 vs 0.7754; `records/independent_math_summary.json`).
- Owner decision D-024 / TD-040.

### S-09 · LOW · Bootstrap description
- The approved CIs use an **ordinary** percentile bootstrap: `default_rng(42)`, 2,000 draws, single-class draws skipped (0 occurred).
- The traceability matrix said "stratified". It is corrected.
- `vps_validation_experiments.py` uses a *stratified* bootstrap with seed 20261019. Its CIs (5D [0.651, 0.881]) are a different procedure, not a conflict.

### S-10 · LOW · `p_diff_gt_0`
- It is the share of paired bootstrap draws with a positive difference: 0.935 in the report, 0.934 by exact pair counting.
- The 0.001 difference is one draw whose difference is exactly 0 in exact arithmetic but positive in floating point.
- It is not a p-value. The UI says "share of bootstrap draws above zero".

### S-11 · MEDIUM · AUROC on single-class samples (fixed)
- **Defect:** `auroc_cols` divided by zero, giving NaN plus a RuntimeWarning. The selection loops summed NaN and `np.argmax` returned 0, silently choosing the first weight vector.
- **Vacuous test:** `tests/test_vps_validation_experiments.py::test_selection_ignores_test_fold_labels` built every training fold single-class, so it compared two arbitrary defaults.
- **Fix:**
  - an explicit NaN for undefined samples;
  - errors for non-binary labels, non-finite scores and shape mismatches;
  - `best_index` skips undefined folds and raises `UndefinedSelection` if none is defined;
  - single-class outer test folds raise.
- **Test repaired:** both classes in every fold; it now also checks that flipping the test labels gives 1 − AUROC.
- **Persisted results unaffected:** the weighting matrix re-run with the fixed code is byte-identical to `data/_runs/vps_weighting_20261019/*`. The original code also gave 0 warnings on the persisted analyses; the warning came only from the vacuous test.
- **Tests:** `TestAurocCols` (4), `TestSelectionNeverFallsBackSilently` (3).

### S-13 · MEDIUM · Evaluation provenance
- Stage `eval` declares `data/reproducibility.json` as an input, but its adopted run did not fingerprint it.
- Re-running `eval` in an isolated copy gives a **byte-identical** `vps_evaluation_report.json`, and the new run fingerprints all 8 inputs.
- Closing the gap in the main repository needs `./venv/bin/python scripts/run_stage.py eval`. That replaces eval's adopted run record (the content stays identical), so it is left for the owner.

### S-15 · B-003 reconciliation
- 0.7763 comes from re-running stage 02 with seed 42 after the deterministic-ordering fix (E-031).
- Over 10 seeds the 5D AUROC ranges from 0.769 to 0.783 (`data/_runs/mission_20261019/proximity_seed_sensitivity.csv`).
- This is the same estimand with Monte-Carlo variability. The approved value reproduces exactly from its saved inputs, not from source.

### S-17 · Agent defects (fixed)

| Defect | Fix | Test |
|---|---|---|
| A-1 | `PARTIAL_ON_EXIT1` += 04p, 05h, 10a-all | `TestRunnerPartialPolicy` |
| A-2 | 10g header-only literature CSV → `INPUT_EMPTY`, PARTIAL | `test_10g_header_only_literature_is_partial_not_success` |
| A-3 | 10d malformed molecular lines counted → `MALFORMED_LINE`, PARTIAL | `test_10d_reports_malformed_molecular_lines` |
| A-4 | 10h: a FAILED upstream output → domains NOT_COMPUTED + `UPSTREAM_FAILED`; 10b added to inputs and dependencies | `test_10h_does_not_read_a_failed_upstream_output_as_data` |
| A-5 | stage 08 `timeout_s` 14400 | `test_stage08_has_a_timeout` |
| A-6 | atomic writes in 10b, 10a, 10f cache, 05, 08 | (write path; content unchanged) |
| A-7 | absent inputs recorded as `null`; one staleness rule in `agent_contract.input_changed` and the server | `TestEnvelopeProvenance` (2) + updated `test_safety_evidence_agent::test_stale_inputs` |

All agents were re-run, first in an isolated copy and then in the repository through the tracked runner. Output **content** is identical, apart from the new `null` input entries and 10b appearing in 10h's agent list.

### S-18 · Contradictions
- **Fixed:**
  - C-1: the stratification claim in `SCIENTIFIC_CONTRACT_TRACEABILITY.md`;
  - C-3: the UI "17 positives";
  - C-4: the README TD-031 text;
  - C-5: the `MOLECULAR_AGENT.md` imputation text;
  - C-7: the README "trial count";
  - C-8: the `vps_verify.py` docstring;
  - C-9: the `VPS_FEATURE_CONTRACT.md` assert location;
  - C-22: the README step list;
  - C-24: the duplicate ID, renamed B-002b.
- **Documented, unchanged:**
  - C-2: two CI procedures;
  - C-6: n-dimensions metadata;
  - C-10 / C-11: TD-042 "must use" and 4D primary versus sensitivity. **Owner decision.**
  - C-12: stage 06 prints a "best variant";
  - C-13: superseded metrics (TD-048);
  - C-14: cutoff wording;
  - C-15: per-trial exclusions;
  - C-16: the candidate location;
  - C-17: four held-out figures;
  - C-18 to C-21, C-23.
- Full list with citations: `evidence/specification_trace.md` §6.

### S-24 · Audit side effect (fixed)
- `build_alias_map` writes Open Targets responses into `data/cache/molecular`. The first two audit runs added 5 + 4 files.
- All 9 were moved to `records/alias_cache_written_by_audit/`. The cache is back to 311 files, matching the recovery snapshot.
- The audit scripts now use a temporary copy of the cache.
