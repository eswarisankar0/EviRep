# Run Center audit (audit 2026-10-21)

All runs in this audit were executed against **isolated rsync copies** on port 8799 (`uxcopy`, `livecopy`, `uicopy8`, `gatecopy4`). `run_suites.sh` builds each copy fresh. The real repository's manifest was untouched:
- `manifest_updated_utc` is still `2026-10-20T18:44:42+00:00`;
- the read-only live-server suites (drive7, `shots20.py`) assert "history unchanged";
- protected hashes 19/19; 0 leftover runner processes (`logs/post_suite_check.txt`).

## 1. Stage discovery and registry integrity
Registry: `ui/server.py` `STAGES`, with 25 stages.

| Policy | Stages | Meaning |
|---|---|---|
| REFUSED (11) | 01, 00, 02, 03, 03c, 04, 05, 08, 06, 04b, eval | rewrite approved/protected artefacts; owner runs them from the CLI in an isolated copy |
| CONFIRM (3) | 05h, 04p, diag | network or long stage; needs an explicit second click |
| ALLOWED (11) | 07, 10a, 10a-all, 10b, 10c, 10d, 10e, 10f, 10g, 10h, review | offline diagnostics; "Run all 11 permitted stages" |

Executed checks (`tests/test_stage_registry_integrity.py`, **new**, 8 tests):
- unique IDs, and every script exists;
- dependencies exist and are acyclic;
- one producer per output;
- every stage reads only outputs of its ancestors;
- the runner's topological order respects every dependency;
- protected writers are REFUSED, and launchable stages have timeouts;
- the score reads no agent output;
- launch commands come from the registry, never from the request.

Of the 22 scripts outside the registry, none is a pipeline stage. They are:
- libraries: `agent_contract`, `intervention_matcher`, `molecular_agent`, `trial_role`, `run_stage`;
- analysis and verification tools: `compare_result_sets`, `vps_verify`, `bootstrap_auroc_ci`, `vps_validation_experiments`, the sensitivity scripts, `backup_data`, `record_test_run`;
- legacy/debug scripts: `debug_step2`, `check_groundtruth`, `test_openfda`, `03b_resume_failed_searches`.

## 2. Executed run-lifecycle scenarios (real Chrome → `ui/server.py` → `scripts/run_stage.py` → manifest → UI)

| Scenario | Suite | Result |
|---|---|---|
| Opening and reloading pages starts nothing | drive9, drive11, drive7 (live, read-only) | PASS |
| Network stage needs a second click; Back cancels without launching | drive9 | PASS |
| An upstream input change shows dependants STALE live, without a reload | drive9, drive11, drive14 | PASS |
| Run all → pipeline completes; skipped vs re-run is correct | drive9, drive11 | PASS |
| A running stage shows RUNNING with elapsed time and its log line (no fake percentage) | drive9, drive13 | PASS |
| Server restarted mid-run → the run resumes and is shown on completion; a stale nonce is renewed | drive9, drive11 | PASS |
| A real failure propagates: FAILED shown on the page, the agent card and the dashboard; previous output byte-identical | drive9, drive11 | PASS |
| Double or triple click → one request and one launch; two tabs at once → one run (409 for the other) | drive12, drive11 | PASS |
| Run all with a failed prerequisite → dependants BLOCKED | drive12; `test_upstream_failure_blocks_dependants_in_a_sequence` | PASS |
| Runner killed mid-stage → `--restore` verifies and restores the output | drive12 | PASS |
| Corrupt or structurally malformed manifest → launches disabled, diagnostic shown | drive9, drive12 | PASS |
| HTML injected into a log renders as text | drive12 | PASS |
| Timeout: RUNNING → timeout (20 s, copy only) → FAILED → output restored; only the stage's own child killed; no orphan | drive13 | PASS |
| Frozen or slow server → the UI reports it and recovers | drive14 | PASS |
| Refusals are distinguished: owner approval (protected data, e.g. 06) vs command line only (live services) | drive16 | PASS |
| 390px layout, no JS exceptions or console errors | all suites | PASS |
| **New:** a failed dependency is flagged on single-stage dependants | `test_a_failed_dependency_is_flagged_on_its_dependants` (runner level); the UI renders `warnings` in the state cell (static) | PASS |

## 3. Live server version and stale-code detection (executed)
1. **Before the restart:** live PID 8655 (started 01:43 local) reported `server_code_changed: true`, correctly detecting that `scripts/run_stage.py` and `ui/app.js` had changed after it started.
2. **Restart:** this audit's own process was stopped and the server relaunched with the canonical command `./venv/bin/python ui/server.py`.
3. **After the restart:** PID 16836 reports `server_code_changed: false`, on `127.0.0.1:8765` only. The isolated server on 8799 was not affected.
4. **Scope:** the flag covers server-side Python. `app.js` and `style.css` are read from disk per request, so they can never be stale (verified: after the later CSS/JS edit the flag stayed `false` and the new markup was served).

## 4. Timestamps
All run records carry ISO-8601 UTC times (`started_utc`, `finished_utc`, `+00:00`), and the UI labels displayed times "UTC" (`DATA_PROVENANCE_AND_FRESHNESS.md`).

## 5. UI defects fixed in the Run Center
- **Stage warnings:** the stage table did not show `warnings`. It now does, in the state cell (the A-5 dependency warning and the unfingerprinted-input warning).
- **State chart:** the "Stages by tracked state" chart had no data-table alternative (A11Y-1). Fixed, and covered by a regression test.
- **Stage-table layout (UI-1, P3):**
  - **Problem:** the stage-name column was `nowrap`, so long names ("Clinical trial-role review worklist (human adjudication queue)") squeezed the state, activity and action columns into 1–3 words per line.
  - **Fix:** now only the stage ID is `nowrap`.
  - **Evidence:** `screenshots/before_stage_table_fix/live_1440.png` vs `screenshots/live_1440.png`.
