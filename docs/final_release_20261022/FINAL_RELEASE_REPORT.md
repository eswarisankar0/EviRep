# EviRep: final submission and release report (2026-10-21/22)

## Recommendation

| Use | Verdict | Why |
|---|---|---|
| **Research submission** (as a retrospective, hypothesis-generating method) | **GO, with the stated limitations** | The approved result reproduces exactly. The UI shows it faithfully. Limitations are measured and disclosed, and no claim of efficacy or external validation is made. |
| **Live demonstration** (local) | **GO** | 756 tests pass; 159/159 browser scenarios pass; protected outputs cannot be rewritten from the UI. |
| **Production deployment** | **NO-GO** | No authentication, TLS or multi-user support; loopback-only by design. Owner decisions are open (below). |

**The headline number must be reported with its temporal caveat.** The approved AUROC 0.775 uses literature, safety and molecular data that are not frozen at the 2021 cutoff. With every input dated before the cutoff, AUROC is **0.689 [0.548, 0.819]**. Present 0.775 as an upper estimate.

## 1. Purpose and prediction target
- **Purpose:** rank existing drugs already tried in Parkinson's disease (PD) by how much independent pre-2021 evidence supports them.
- **Target:** a **positive** is a pool drug with at least one qualifying PD interventional drug trial **first posted on or after 2021-01-01** (D-010). This is a proxy for continued clinical investigation, **not proof of efficacy**. A negative means no qualifying trial was found.

## 2. Cohort
- **90 compounds:** Hetionet drugs that were not already PD palliatives, minus nutrients, minus non-drug studies, that have at least one accepted pre-2021 PD trial.
- **14 positive, 76 negative;** prevalence 0.156.
- Positives fell from 17 to 14 after three owner-approved exclusions (anaesthesia during DBS surgery ×2, a gene-therapy actuator).
- **Cutoff:** 2021-01-01 (`scripts/03_clinicaltrials_groundtruth.py:53`).

## 3. Score (VPS) and weights
- **Dimensions:** five percentile ranks, with higher meaning more favourable:
  - network proximity (Hetionet PPI z-score);
  - clinical maturity (highest pre-2021 trial phase);
  - literature independence (independent PubMed paper clusters);
  - safety (FDA label: serious terms + 5 × boxed warning);
  - molecular plausibility (0.6 × Open Targets direct + 0.4 × Reactome pathway).
- **Weights:** equal, 0.2 each (`scripts/06_vps_fusion.py:598-599`).
- **Missing data:** safety or molecular gets the neutral rank 0.5; missing proximity gets the pool median.
- **Weights retained** (`WEIGHTING_DECISION.md`):
  - learned weightings are worse on held-out data (logistic regression 0.596, worse than equal weights in 20/20 repeats; constrained grid 0.639);
  - learned coefficients are unstable (SD ≈ mean);
  - 2,000 unselected random weightings range 0.61–0.78, so the result is weight-sensitive and equal weights sit near the top of that range.

## 4. Results

| Model | AUROC [95% CI] | AUPRC [95% CI] |
|---|---|---|
| **Approved 5D** (run `adopted-20261015T015501Z-06`) | **0.775 [0.656, 0.881]** | **0.424 [0.226, 0.679]** |
| Chance | 0.500 | 0.156 (prevalence) |
| Approved 4D (no molecular) | 0.700 | 0.358 |
| Fully dated 5D (all inputs pre-2021 where a dated source exists; not approved) | 0.689 [0.548, 0.819] | 0.334 [0.155, 0.561] |
| TD-042 corrected molecular rule (not approved) | 0.699 [0.557, 0.830] | 0.307 |

**How these were computed:** 2,000-resample percentile bootstrap, seed 42. 5D vs 4D: +0.075 [−0.025, 0.176], **not significant**.

**What AUROC 0.775 means:** a random positive is ranked above a random negative 77.5% of the time. It is **not** a probability that a drug works.

## 5. Validation design and limitations
- **Internal, retrospective, temporal split only. No external validation.**
- **Confirmed leakage:**
  - literature, safety and molecular evidence are current snapshots;
  - the share of post-2020 papers in a drug's literature sample alone predicts the label (AUROC 0.722, p = 0.009).
- **Small sample:** 14 positives, so wide intervals.
- **Selection:** the pool contains only previously-tried drugs.
- Full classification: `SCIENTIFIC_AUDIT.md`.

## 6. Reproducibility and provenance
- **Approved artefacts:**
  - `data/vps_scores_v2.csv`
  - `data/vps_evaluation_report.json`
  - `data/clinical_maturity_precutoff_clean.csv`
  - `data/ground_truth_postcutoff_clean.csv`
  - `data/label_role_exclusions.csv`

  These and 14 other files are protected (`ui/live_runs.py:31-38`); sha256 19/19 unchanged.
- **Independent recomputation:** `scripts/vps_verify.py` gives MATCH (max |diff| 2.2e-16).
- **Manifest:** `scripts/run_stage.py --check-manifest` ok; 12 ADOPTED + 13 SUCCESS stages.
- **Gaps (disclosed in the UI as "some inputs not verifiable"):**
  - adopted stages carry no code fingerprint;
  - `eval` never fingerprinted `data/reproducibility.json`;
  - the bootstrap CI file is produced outside the registry;
  - the approved CSV predates the `dimensions_imputed` flag, so 2 imputed proximity values are unflagged.
- **A from-source rebuild would differ:** live APIs have changed, and the pagination fix adds Dopamine.

## 7. Eight-agent architecture
- **Score inputs:** stages 02, 03/03c, 04, 05 and 08 produce the five dimensions. **No agent output enters the score** (enforced by `tests/test_vps_correctness.py::TestIsolation`).
- **Paired agents:** 10b, 10c, 10f and 10g *check* the stage behind a score dimension. The UI now says so ("checks a score input; does not change the score"); it previously said "feeds the score" (E-061, fixed).
- **Diagnostics only:** 10a, 10d, 10e and 10h (10h is an annotation).
- **What agent status means:** SUCCESS = every unit processed, not scientific validation. The runner reads each agent's own `run_status`, so a FAILED or PARTIAL output is never recorded as SUCCESS even when the process exits 0.

## 8. Tests executed (actual results)

| Check | Result | Log |
|---|---|---|
| Full suite, baseline | 751 OK, 0 warnings, exit 0 | `logs/tests_baseline.log` |
| Full suite, final | **756 OK, 0 failed, 0 skipped, 0 warnings, exit 0** | `logs/tests_after_fixes.log` |
| Browser suites (real Chrome, isolated copies) | **159/159** (drive7/8/9/11/12/13/14/15/16) | `records/browser/suites_release.out` |
| Accessibility tree, 16 routes | 0 unnamed controls; 23/23 charts with label + data table | same |
| Live badge / review-count check | all pass; 0 JS errors; no stage started | `records/browser/drive21.out` |
| Security probes (14) | baseline 200; all 13 attacks refused as designed; loopback only; no `shell=True`; 0 credential matches | `logs/security_probes.txt` |
| Gates | manifest ok; vps_verify MATCH; protected 19/19; `diff --check` clean; `node --check` ok; index unchanged | `logs/gates_final.log` |

## 9. UI workflows verified (this release and the 2026-10-21 audits)
- Overview, Candidates (sort, search, filters, clear, candidate pages), Evidence (all evidence, mechanism, conflicts, trial-role review), Validation (curves, intervals, TD-042 shown as "not approved"), and Run Center (health, stages, runs, agents).
- **Run lifecycle:**
  - launch; RUNNING with log line;
  - failure → FAILED with output restored byte-identical;
  - timeout;
  - server restart mid-run;
  - double click and two tabs → one run;
  - corrupt manifest → launches disabled;
  - frozen server.
- 186 controls operated one by one in the previous audit (0 dead).

## 10. Defects fixed in this release
| ID | Fix | Regression test |
|---|---|---|
| E-061 | Misleading "feeds the score" badge reworded | `test_ui_quality.py::test_no_agent_is_described_as_feeding_the_score` |
| E-062 | Hard-coded "28" review count now read from the worklist | `tests/test_review_count.py` (3) |
| E-063 | 10h "x/4 checks" denominator → actual number of checks (5) | `test_completeness_gap_agent.py::test_independence_denominator_counts_all_five_checks` |
| – | Review stage writes CSVs atomically | output byte-identical on re-run (isolated copy, then real tree) |
| – | Doc corrections: `docs/VPS_EVALUATION.md` imputation flag; dated notes on TD-009/021/031/033 | – |

## 11. Unresolved issues and blockers (owner decisions; none hidden)
1. **TD-042** (P0): molecular double-count; the corrected rule drops AUROC to 0.699. Candidate in `data/_candidates/td042_v1/`, unpublished.
2. **E-056** (P0): stage-03 data predates the pagination fix; a rebuild would add Dopamine.
3. **TD-021/022/033** (P1): leakage in non-dated dimensions. The fully dated estimate is 0.689; decide whether to report or adopt a dated score.
4. **B-004 Lithium; D-011 Galantamine; 28 unresolved trial-role links; D-020 feature exclusions** (P1).
5. **Provenance gaps** (P1): `eval` fingerprint, adopted-stage code fingerprints, missing `dimensions_imputed` column.
6. **Undocumented constants** (P2): ×5 boxed weight, N_RANDOM 100, σ = 0 → z = 0, `phases[0]`.
7. **Engineering** (P2): stages 06/eval have no timeout (CLI-only, refused in the UI); agents 10d/10e/10a-curated exit 0 on PARTIAL when run by hand (the runner still records PARTIAL).
8. **Deployment** (release): authentication, TLS and an audit log are needed before any non-local use.

## 12. Commands
```
./venv/bin/python ui/server.py                                   # UI at http://127.0.0.1:8765/
./venv/bin/python scripts/vps_verify.py                          # independent score check (read-only)
./venv/bin/python scripts/run_stage.py --status                  # stage freshness (read-only)
./venv/bin/python scripts/run_stage.py --check-manifest          # manifest integrity (read-only)
./venv/bin/python -m unittest discover -s tests                  # 756 tests
./venv/bin/python docs/final_release_20261022/experiments/release_experiments.py --out /tmp/evirep_exp   # experiments (writes only to --out)
```

## 13. Changes and recovery
- **Changed files:** `records/changed_files.txt`. The code diff is +35/−9 lines across 4 files; 3 test files (2 extended, 1 new); docs +27/−1, plus development-log entries.
- **Data:** `data/completeness_gaps.json` (10h text only) and `data/run_manifest.json` (2 new runs). No approved or protected file changed.
- **Git:** nothing staged, committed or pushed. HEAD `576bc7f`, 0 ahead / 0 behind; the index is byte-identical to the snapshot.
- **Recovery snapshot:** `~/EviRep_recovery_final_20261021T1713Z/` (worktree and data tarballs, git index, diffs, `SHA256SUMS`). To undo this release's code and doc changes, restore the tracked files listed in `records/changed_files.txt` from `worktree_snapshot.tgz`, delete `tests/test_review_count.py`, and restore `data/completeness_gaps.json` from `data_snapshot.tgz`.
