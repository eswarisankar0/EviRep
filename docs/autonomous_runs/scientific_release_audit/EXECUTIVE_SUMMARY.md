# Executive summary: scientific, mathematical, data and release audit (2026-10-20)

## Recommendation: **CONDITIONALLY READY**
- The code, tests and documentation fixes are ready for human review and commit.
- The approved result set (`adopted-20261015T015501Z-06`) is correctly computed for its documented specification and reproduces exactly.
- Full scientific sign-off depends on owner decisions and known limitations (below), including one data defect in the cohort (S-01) that needs a deliberate re-build.

## A. Scientific correctness
- **Candidate identities:** 90 of 90 checked. They have unique DrugBank and ChEMBL IDs, no duplicates or near-duplicates, and are all inside the eligible cohort.
- **Labels:**
  - 88 confirmed under the documented rules (13 positive, 75 negative);
  - 1 unresolved: **Galantamine**, D-011, kept positive by owner decision;
  - 1 disputed: **Lithium**, whose three PD trials of lithium aspartate are dropped because the registry types them DIETARY_SUPPLEMENT;
  - **0 labels changed.**
- **How the labels were checked:**
  - live, fully paginated registry search using stage 03's own gates: all 90 label sets reproduce exactly;
  - alias searches for all 76 negatives (691 queries): no missed qualifying trial;
  - 4 alias queries unverifiable (HTTP 400).
- **Trial-role links:** every label trial was reviewed. The 28 + 9 review-queue links are all pre-cutoff feature links. **28 still await a human decision; none was resolved by the audit.**
- **New defects:**
  - **S-01:** stage 03 kept only 20 results per compound. It missed **Dopamine** as a cohort member (genuine A-dopamine trials in 2020 and 2025) and one Phase-3 feature trial for Ioflupane I 123, with no rank change. The code is fixed; the cohort re-build is an owner decision.
  - **S-03:** the matcher credits class phrases ("dopamine agonists") and background-therapy otherNames.
  - **S-05:** the molecular PD module is selected by an overall Open Targets score that includes outcome-related datatypes.

## B. Mathematical correctness
- Formula-by-formula specification (`MATHEMATICAL_AUDIT.md`): equal-weight mean of five average-tie percentile ranks; neutral 0.5 for missing safety (7) and molecular (16); median imputation for proximity (2).
- **Independent implementation:** ranks equal exactly; scores within 2.2e-16.

| Statistic | Approved | Independent |
|---|---|---|
| AUROC 5D | 0.775376 | 0.775376 |
| AUROC 4D | 0.700188 | 0.700188 |
| AUPRC | 0.424315 | 0.424315 |
| 95% CI | [0.656, 0.881] | [0.656, 0.881] (ordinary bootstrap, seed 42) |
| Paired 5D−4D | +0.075 [−0.025, +0.176] | identical |

  The paired interval includes 0 because the difference (0.075) is smaller than its bootstrap SD (0.051).
- **The RuntimeWarning (S-11):** `auroc_cols` divided by zero on single-class folds, and the selection then silently chose the first weight vector. The only occurrence was a **vacuous test**. Fixed: undefined AUROC is explicit, selection skips undefined folds, and the test is repaired. Persisted analyses re-run byte-identically.
- **Reconciled numbers:**
  - 0.7754 vs 0.7763 is the same estimand with a different Monte-Carlo draw of the proximity null;
  - 14 vs 17 positives reflects owner policy P1 plus later feature fixes;
  - equal-weight vs grid and the two CI procedures are different estimands or procedures;
  - `td042_v1` is the same cohort with a different molecular rule (0.699; not approved).

## C. Data integrity
- **Protected files:** 19 inventoried (sha256, bytes, rows, schema), 19/19 unchanged.
- **Keys and joins:** no duplicate keys; every pool join is complete (2 proximity rows absent, imputed and flagged).
- **Values:** 0 raw-value mismatches; all ranks finite and in [0, 1]; feature dates < 2021-01-01 ≤ label dates ≤ 2026-10-05; no trial in both windows.
- **Fingerprints:** the approved run's 16 fingerprints and the report's 7 input fingerprints all match.
- **Provenance gaps:**
  - the `eval` input `reproducibility.json` is unfingerprinted; a re-run reproduces the report **byte-identically** and awaits owner approval;
  - historical runs have no code fingerprints.

## D. Pipeline and UI reliability
- **Fixed:**
  - stage-03 pagination;
  - single-class AUROC handling;
  - A-1 to A-7: partial results kept; 10g empty input; 10d malformed lines; 10h failed upstream outputs and its missing 10b dependency; stage-08 timeout; atomic writes; absent inputs fingerprinted with one staleness rule;
  - the UI's stale "17 positives".
- **Tests:** 26 regression tests added; 1 vacuous test repaired; 1 test updated to the new contract.
- **Agents:** re-run first in isolation and then through the tracked runner. Their content is identical.
- **UI:** 89/89 browser checks pass; UI counts and scores match the approved files.

## E. Reproducibility
- **Python suite:** 697 → **723 tests, exit 0, 0 warnings**. Gates (manifest check, score verification, protected hashes, whitespace) all pass.
- **Environment:** Python 3.13.9, numpy 2.5.3, pandas 3.0.6, scipy 1.18.1, scikit-learn 1.9.1, requests 2.34.2.
- **Online checks:** read-only ClinicalTrials.gov searches (101 paginated searches + 691 alias searches). The previous pass covered PubMed, openFDA, DailyMed, Open Targets and Zenodo; Semantic Scholar was blocked (HTTP 429).
- **Not run:** the protected online stages, 04p/05h full runs, production-length timeouts, and re-execution of the historical time-bounded sensitivity scripts (their saved results are cited).

## Validity of the conclusions
- **Defensible:** a retrospective association with *continued clinical investigation*. It is above chance in every case examined:
  - every label resolution: 5D 0.757–0.800;
  - time-bounding where recorded: about 0.686 [0.544, 0.821].
- **Not defensible:**
  - a leakage-free or prospective 0.775;
  - efficacy or safety;
  - added value of the molecular dimension (it disappears when dated or under TD-042);
  - label-tuned weights.

## Owner decisions required
1. Re-build the cohort with paginated searches (S-01). It adds at least Dopamine and changes the approved result.
2. Lithium and the study-type rule (S-02 / B-004).
3. Galantamine and Rifaximin roles (S-04); the 28 feature-trial roles (D-020).
4. Molecular module selection (S-05) and `td042_v1` (S-23).
5. Temporal validity (S-06 / TD-033): adopt time-bounded features or keep the caveat.
6. Rank convention (S-08) and an indeterminate-label policy (S-21).
7. Approve the `eval` re-run (S-13), which is byte-identical.

## Repository state (nothing staged, committed or pushed)
- HEAD `576bc7f`. The index file is byte-identical to the pre-audit snapshot `~/EviRep_recovery_sci_20261020T1608Z`. Staged files: 25 (diff md5 unchanged); unstaged: 21 (same list); no stashes.
- **Changed by this audit (23 files):**
  - `scripts/` (13): 03, 05, 08, agent_contract, completeness_gap_agent, conflict_context_agent, evidence_independence_agent, literature_credibility_agent, molecular_run_record, run_stage, safety_evidence_agent, vps_validation_experiments, vps_verify (docstring);
  - `ui/server.py`;
  - tests (3): `test_agent_failure_modes`, `test_safety_evidence_agent`, `test_vps_validation_experiments`;
  - docs (6): `README.md`, `docs/MOLECULAR_AGENT.md`, `docs/VPS_FEATURE_CONTRACT.md`, `docs/autonomous_runs/SCIENTIFIC_CONTRACT_TRACEABILITY.md`, `development_log/CHANGES.md`, `development_log/ERRORS_AND_BLOCKERS.md`.
- **New:** `tests/test_scientific_audit.py` and this folder (`records/` holds the machine-readable audits; it was renamed from `data/` because `.gitignore` ignores any `data/` directory).
- **Regenerated diagnostic outputs** (git-ignored `data/`, not protected): the agent outputs of 10a, 10a-all, 10b, 10d, 10f, 10g and 10h, and their manifest run records. 10c, 10e and review were skipped as fresh. 06 and eval remain ADOPTED and unchanged.
- **Rerun the release checks:** see `RELEASE_CHECKLIST.md`.
