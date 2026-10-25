# Test evidence

**Environment**
- Python 3.13 (`./venv`). numpy, pandas, scipy, scikit-learn and requests from `requirements.txt`; nothing installed or changed.
- Headless Chrome 155 for the browser checks.

## Commands, exit codes, counts

| Check | Command | Before | After | Log |
|---|---|---|---|---|
| Full suite | `./venv/bin/python -W default -m unittest discover -s tests` | 697 tests OK, exit 0, **1 RuntimeWarning** (`vps_validation_experiments.py:116`) | **723 tests OK, exit 0, 0 warnings** | `logs/tests_baseline.log`, `logs/tests_after.log` |
| New statistical / ranking / provenance / pagination / leakage tests | `-m unittest tests.test_scientific_audit` | — | 23 / 23 | — |
| Agent failure modes (real runner and agents, isolated copy, no mocks) | `-m unittest tests.test_agent_failure_modes` | 4 | 7 / 7 | — |
| Repaired nested-CV test | `-W error::RuntimeWarning -m unittest tests.test_vps_validation_experiments` | passed **vacuously** | 10 / 10 | — |
| Run manifest | `./venv/bin/python scripts/run_stage.py --check-manifest` | 0 | 0 | `logs/check_manifest.txt` |
| Score verification | `./venv/bin/python scripts/vps_verify.py` | MATCH | MATCH, max abs diff 2.22e-16 | `logs/vps_verify.txt` |
| Protected artefacts | `shasum -a 256 -c logs/hashes_before.txt` | — | 19 / 19 OK | `logs/hashes_after_check.txt` |
| Whitespace | `git diff --check` | — | clean | — |
| JavaScript syntax | `node --check ui/app.js` | — | OK | — |
| Browser (real Chrome, isolated copy) | drive16 / drive15 / drive7 | — | 44/44, 24/24, 21/21 | `../biomedical_ux_agent_audit/evidence/` (drivers) |

The test count grew by 26: 23 new scientific-audit tests and 3 new agent-defect tests. The vacuous test was repaired, not added. One existing test was updated to the new contract: `test_safety_evidence_agent::test_stale_inputs`, now that absent inputs are recorded as `null`.

## Independent recomputations (audit tools, no production imports)

| Tool | Output | Result |
|---|---|---|
| `scripts/independent_math.py` | `records/independent_math_summary.json`, `records/independent_scores.csv` | ranks diff 0; scores ≤ 2.2e-16; AUROC, AP, CIs and paired difference equal |
| `scripts/data_integrity.py` | `records/data_integrity_*` | 0 HIGH, 2 MEDIUM (the 2 imputed proximity rows), 19 INFO |
| `scripts/ground_truth_audit.py` | `records/ground_truth_row_audit.csv` | 14/76 reproduced; 1 unresolved, 1 disputed |
| `scripts/label_sensitivity.py` | `records/label_sensitivity.json` | 5D 0.757–0.800 |
| weighting matrix, original vs fixed code | scratch outputs vs `data/_runs/vps_weighting_20261019` | byte-identical; 0 warnings |
| `eval` re-run (isolated copy) | `vps_evaluation_report.json` | **byte-identical** to the approved report |

## Fault injection (isolated copies)
- **34-run matrix** (`../biomedical_ux_agent_audit/evidence/agent_fault_matrix.json`, previous pass): 27 FAILED with the output restored byte-identical, 6 PARTIAL with a diagnostic, 1 silent SUCCESS (10g). **That case is now fixed** and covered by `test_10g_header_only_literature_is_partial_not_success`.
- **Upstream failure:** `--sequence 10d 10h` with a corrupt 10d input gives 10h BLOCKED (test).
- **FAILED upstream envelope:** 10h marks those domains NOT_COMPUTED (test).
- **Failed second registry page:** the whole search fails (test).
- **Offline tests:** no network access. Pagination is tested with mocked `requests.get`; the agent tests run offline agents.

## Online checks performed (read-only)
- **ClinicalTrials.gov API v2:**
  - 101 paginated searches (90 cohort + 11 truncated compounds);
  - 691 alias searches for the 76 negatives (4 rejected, HTTP 400);
  - 2026-10-20, about 15:55–17:20 UTC.
- **Open Targets GraphQL:** 9 alias-resolution requests, written to a cache that was afterwards moved out of `data/` (S-24).
- **Previous pass:** PubMed, openFDA label and FAERS, DailyMed, Open Targets, Zenodo (HEAD). Semantic Scholar blocked (HTTP 429).

## Not performed
- Online stages 01, 03, 03c, 04, 05, 08 (they rewrite protected files).
- 04p and 05h full runs.
- Production-length timeouts.
- Re-execution of the historical time-bounded sensitivity scripts (their saved results are cited).
