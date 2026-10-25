# Test results

| Check | Command | Before | After | Log |
|---|---|---|---|---|
| Python suite | `./venv/bin/python -m unittest discover -s tests` | 684 OK | **697 OK** | `logs/tests_before.log`, `logs/tests_after.log` |
| New: agent failure modes (real runner, isolated copy, **no mocks**) | `-m unittest tests.test_agent_failure_modes` | — | 4 / 4 | — |
| New: five-section navigation, evidence nature, wording | `-m unittest tests.test_biomedical_ux` | — | 9 / 9 | — |
| Ground-truth contract | `-m unittest tests.test_ground_truth_contract` | OK | OK | — |
| Score verification | `scripts/vps_verify.py` | MATCH | MATCH, 90 compounds, max abs diff 2.22e-16 | `logs/vps_verify.txt` |
| Run manifest | `scripts/run_stage.py --check-manifest` / `--status` | — | exit 0 / exit 0 | `logs/check_manifest.txt`, `logs/status_after.txt` |
| JS syntax | `node --check ui/app.js` | — | OK | — |
| Whitespace | `git diff --check` | — | clean | — |
| Browser | 9 CDP suites | — | **156 / 156** | `BROWSER_ACCEPTANCE.md` |
| Agent fault matrix | `evidence/agent_faults.py` (34 real-runner runs) | — | 27 FAILED and restored, 6 PARTIAL with diagnostics, 1 silent SUCCESS (defect A-2) | `evidence/agent_fault_matrix.json` |
| Online checks | `evidence/online_check.py` | — | 8 sources: 7 PASS (Zenodo reachability only), Semantic Scholar BLOCKED (429) | `ONLINE_INTEGRATION_RESULTS.md` |

## Failures during the pass and their resolution

- **Four existing tests encoded the old design and were updated to the new one; none was relaxed.**
  - `test_live_app.test_default_route_and_nav`: default route is now `overview`; exactly five sections in order; the live Run Center is still re-rendered on every poll.
  - `test_ui.test_client_polls_only_the_status_endpoint`: the pill links to `#run`.
  - `test_ui_quality.test_no_blanket_current_claim`: new wording, plus the new `VERIFIED_WITH_GAPS` headline.
  - `test_ui.test_status_endpoint_reports_error_not_500_and_never_current`: this one was fixed in the **server**, not the test. The `UNVERIFIABLE` group is now added only when it is non-empty, so a corrupt manifest still reports only `UNKNOWN`.
- **Harness errors (my scripts, not the product):**
  - online check: wrong `sleep` argument type; module loaded the wrong way;
  - drive16: four issues (see `BROWSER_ACCEPTANCE.md`).

  All were corrected and re-run.

## Mocked versus real

- **Mocked HTTP:** the agent unit tests for 10a, 10b, 10c and 10f, and the 04p and 05h tests, use injected fake sessions. They are **not** counted as online evidence.
- **Real execution, offline:** `test_agent_failure_modes`, the fault matrix and the browser suites use the real runner and real stage processes on isolated copies.
- **Real network:** only the online checks.
