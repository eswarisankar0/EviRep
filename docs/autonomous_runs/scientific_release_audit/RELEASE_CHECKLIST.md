# Release checklist

| # | Gate | Result | Evidence |
|---|---|---|---|
| 1 | Approved result reproduces exactly from its saved inputs (ranks, scores, AUROC, AUPRC, CIs, paired difference) | PASS | `MATHEMATICAL_AUDIT.md` |
| 2 | Independent implementation agrees within 1e-15 | PASS | `records/independent_math_summary.json` |
| 3 | All 90 labels have a documented decision or an explicit unresolved status | PASS (1 unresolved, 1 disputed) | `GROUND_TRUTH_AUDIT.md` |
| 4 | Labels re-ascertained against the live registry with full pagination | PASS (all 90 label sets reproduce) | `records/reascertain/` |
| 5 | Cohort complete under the stated rules | **FAIL** (S-01: Dopamine missed through search truncation; code fixed, cohort not re-built) | `FINDINGS.md` S-01 |
| 6 | No direct label leakage | PASS | `LEAKAGE_AND_VALIDATION_AUDIT.md` |
| 7 | Temporal validity of predictors | **NOT MET** (TD-033: current snapshots; time-bounded estimate about 0.69) | same |
| 8 | Cross-file integrity (keys, joins, ranges, raw values, dates, fingerprints) | PASS | `DATA_POINT_AUDIT.md` |
| 9 | Every consumed input fingerprinted | **PARTIAL** (eval: `reproducibility.json`; re-run reproduces byte-identically, awaiting owner; historical runs have no code fingerprints) | S-13, S-14 |
| 10 | Pipeline failure behaviour (fail-closed, no stale-as-fresh, partial handled, atomic writes) | PASS (A-1 to A-7 fixed and tested) | `FIX_LOG.md` |
| 11 | Statistical edge cases (single-class samples, ties, reversal, bad inputs) | PASS | `tests/test_scientific_audit.py` |
| 12 | Test suite | PASS: 723 OK, 0 warnings | `TEST_EVIDENCE.md` |
| 13 | Browser / UI consistency | PASS: 89/89; UI counts match the report | same |
| 14 | Protected artefacts unchanged; adopted pointer unchanged | PASS: 19/19; `adopted-20261015T015501Z-06` | `logs/hashes_after_check.txt` |
| 15 | Human adjudication untouched | PASS: 28 review links unresolved; Galantamine unresolved | — |
| 16 | No secrets in code, logs or reports | PASS: credential names only; no `.env` present | — |
| 17 | Git state preserved | PASS: index byte-identical, no staging or commits (see `EXECUTIVE_SUMMARY.md`) | — |

## Recommendation: **CONDITIONALLY READY**
- The code, tests and documentation corrections are ready for human review and commit.
- The approved scientific result is reproducible and correctly computed for its documented specification.
- Full scientific sign-off is prevented by owner decisions and known limitations:
  - S-01: re-build the cohort with full search pagination;
  - S-02: the Lithium / study-type rule;
  - S-04: Galantamine and Rifaximin roles;
  - S-05: molecular module selection;
  - S-06: temporal validity (TD-033);
  - S-08: rank convention;
  - S-13: approve the `eval` re-run;
  - S-21: indeterminate-label policy;
  - S-23: `td042_v1`.

**Re-run the release checks:**
```
./venv/bin/python -W default -m unittest discover -s tests && ./venv/bin/python scripts/run_stage.py --check-manifest && ./venv/bin/python scripts/vps_verify.py && shasum -a 256 -c docs/autonomous_runs/scientific_release_audit/logs/hashes_before.txt && ./venv/bin/python docs/autonomous_runs/scientific_release_audit/scripts/independent_math.py /tmp/evirep_math && ./venv/bin/python docs/autonomous_runs/scientific_release_audit/scripts/data_integrity.py /tmp/evirep_integrity
```
(Create the two `/tmp` output directories first. The re-ascertainment and alias scripts make online requests and are not part of the offline gate.)
