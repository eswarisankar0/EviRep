# EviRep runtime reliability and regression verification (2026-10-20, 10:10Z–10:32Z)

**Scope.** This covers the local app on loopback: Python stdlib server, vanilla-JS Dashboard and `scripts/run_stage.py`. Each check is classified as follows.

| Class | Meaning |
|---|---|
| PASS | directly verified |
| FAIL | reproducible defect |
| BLOCKED | could not verify |
| NOT TESTED | not attempted |

Evidence: [`TEST_RESULTS.json`](TEST_RESULTS.json), [`LIVE_RUN_ACCEPTANCE.json`](LIVE_RUN_ACCEPTANCE.json), [`ARTIFACT_INTEGRITY_REPORT.json`](ARTIFACT_INTEGRITY_REPORT.json), [`BASELINE.md`](BASELINE.md), `logs/`, `evidence/`.

**Not claimed:** this is not "error-free". It reports which behaviours were exercised and which were not.

## 1. Baseline (before changes)
- `main` @ `576bc7f`, 6 commits; 25 staged, 21 unstaged, 188 untracked; no stashes.
- Recovery snapshot `~/EviRep_recovery_rr_20261020T1010Z` (512 entries).
- Protected artefacts 19/19 OK.
- The running server's `app.js`, `style.css` and `index.html` are byte-identical to disk, and the process started after the last server change.
- Baseline suite: **660 tests OK**. **Six defects were reproduced** before any change; none was caught by those 660 tests (`BASELINE.md`).

## 2. Defects found, root causes, fixes
| ID | Reproduction | Root cause | Fix (smallest safe) | Regression test | Status |
|---|---|---|---|---|---|
| D1 | manifest that is valid JSON with the wrong structure (stage record a string, `last_success` a list, history entry not an object) | `read_manifest` checked JSON syntax only; `status()` dereferenced fields, so `AttributeError` reached the browser as HTTP 500 | `_structure_problem()`: every dereferenced field is type-checked, giving `ManifestError`, so every stage is UNKNOWN with the exact reason | `TestMalformedManifestStructure` (6 shapes); browser drive12 | FIXED, PASS |
| D2 | RUNNING record with `run_dir` outside `data/_runs` | `_last_activity` joined the manifest path without confinement | realpath confinement to `data/_runs/<run>/log.txt` | `TestPathConfinement.test_manifest_run_dir_outside_runs_is_ignored` | FIXED, PASS |
| D3 | launch record with `log` pointing elsewhere | `launches()` followed the stored path | the log path is derived from the validated launch id only | `TestPathConfinement.test_launch_record_log_path_is_not_followed` | FIXED, PASS |
| D4 | stage process hangs | `subprocess.run` without a timeout, so RUNNING forever | `timeout_s` per stage (900 s offline launchable stages, 3600 s confirm stages, unlimited for the long live stages). On timeout only this run's child is killed, the run is FAILED with a `TIMEOUT` diagnostic, and the previous outputs are restored | `TestStageTimeout` (real hung process; every launchable stage has a timeout) | FIXED, PASS |
| D5 | launch directory not writable | `OSError` surfaced only as "launch failed (PermissionError)" | `LaunchError` names what could not be written or started, and what to check; nothing starts | `TestLaunchEnvironmentErrors` | FIXED, PASS |
| D6 | runner SIGKILLed mid-stage | stage pid not recorded; the half-written output was reported as an *outside edit*; orphan process untracked; no recovery | `child_pid` recorded; status says the interrupted run caused the change and the orphan is still running; new `run_stage.py --restore STAGE` restores only md5-verified copies of the last success, refuses while any process of the run is alive, writes nothing on mismatch | `TestRunnerKilledMidStage` (real SIGKILL, real orphan); browser drive12 | FIXED, PASS |
| D7 | "Run all" with a failed prerequisite | BLOCKED dependants appeared only inside the launch log | the runner's `SEQUENCE` line is parsed; the Dashboard shows ran / skipped (fresh) / failed / blocked per launch | `TestSequenceOutcome`; browser drive12 | FIXED, PASS |

**Proof that the tests detect the defects:** 8 of the 9 new runner/server tests fail on the pre-mission code. The ninth (a missing runner is reported as a failed launch, not success) characterises behaviour that was already correct.

## 3. Live run lifecycle
Real browser, real server, real `run_stage.py`, isolated copies.

| Behaviour | Result | Evidence |
|---|---|---|
| Initial load opens the live Dashboard; agent states equal `run_stage.py --status` | PASS | drive11 #1, #2 |
| Launch one stage from an agent page and from the Dashboard | PASS | drive11 #3–5, drive12 |
| Run-all: dependency order, fresh stages skipped, failed prerequisite gives downstream BLOCKED (shown) | PASS | drive11 #3, drive12 |
| Double/triple click: 1 request, 1 launch. Two tabs firing together: 202 + 409, 1 launch. 20 concurrent POSTs: 1 × 202 | PASS | drive12; `logs` probe |
| RUNNING / SUCCESS / FAILED / STALE / BLOCKED / SKIPPED / never run / UNKNOWN shown truthfully | PASS | drive11, drive12, drive8, `test_live_app` |
| Elapsed time, latest log line, exit code and errors match the real process; no percentages | PASS | drive11 #5c, #6; drive9 |
| Hung process: killed after `timeout_s`, FAILED + TIMEOUT, outputs restored | PASS (unit test with a real process) | `TestStageTimeout` |
| Hung process shown in the browser at the moment of timeout | NOT TESTED | 900 s budget; the timeout path is covered by the real-process unit test |
| Runner killed: never RUNNING forever; orphan reported; `--restore` verified; page updates live | PASS | drive12, `TestRunnerKilledMidStage` |
| Malformed or unparseable manifest, missing outputs, invalid JSON input, truncated or HTML logs, permission failure, missing runner | PASS | drive8, drive12, unit tests |
| Server restart / connection loss mid-run: no invented success; the run is still tracked; session renewed without a 403 | PASS | drive11 #8, drive9 |
| Failed run keeps the previous valid output byte-identical | PASS | drive11 #7, drive9 |
| Opening pages and polling never launch work | PASS | drive11 #9, drive9, `TestRequestGuards` |

## 4. Frontend
**Checked, PASS:**
- desktop 1440 and mobile 390 with no horizontal overflow (Dashboard, agent, stages and research views);
- back/forward and repeated visits;
- disconnected / reconnecting messages;
- loading, empty and error states;
- no uncaught JS errors, and no failed requests other than the intentional 409 probe;
- duplicate or unauthorised execution impossible from buttons;
- stale results never shown as current (hero, cards, flow, status pill).

**Browser totals:** 70/70 across five suites (`LIVE_RUN_ACCEPTANCE.json`).

**NOT TESTED:** screen-reader output and contrast tooling.

## 5. Scientific reproducibility
| Check | Result |
|---|---|
| sha256 of 19 protected artefacts + evaluation report + run manifest | **identical** before and after (`ARTIFACT_INTEGRITY_REPORT.json`) |
| `vps_verify` | MATCH |
| ground-truth contract (independent stdlib) | 9/9 |
| Displayed score | the approved `VPS_equal_5d` ranking, labelled as not a probability of efficacy |
| Operational vs scientific validity | operational success (agent SUCCESS) is shown separately from scientific validity (envelope validation, stale inputs, unapproved candidates not displayed) |

Nothing scientific was changed: no artefact regenerated, and no formula, label, feature, protocol or frozen data touched. Owner and clinical decisions are untouched.

Previously documented reproducibility discrepancy B-003 (the from-source rerun gives AUROC 0.7763 against 0.7754) is unchanged and not resolved here.

## 6. Security and process safety (local only)
**Execution:**
- Only same-origin requests with the per-server nonce and a JSON body can launch (`TestRequestGuards`, browser).
- Stage ids are allow-listed, and arguments are fixed by the registry: no user-supplied paths or commands.

**Paths and rendering:**
- Log and launch paths are confined (D2/D3).
- Logs are HTML-escaped (browser test with an injected `<img onerror>` / `<script>`).
- Children write only their declared outputs (10/10 containment, earlier sprint; agent code unchanged since).

**Process handling:**
- The runner kills only its own child on timeout.
- `--restore` never kills anything; it refuses while processes of the run are alive.

**Not implemented:** authentication, HTTPS and multi-user isolation. The application must stay on loopback.

## 7. Files changed this mission
- `scripts/run_stage.py`:
  - D1: `_structure_problem`.
  - D2: confined `_last_activity`.
  - D4: `timeout_s` handling.
  - D6: `child_pid`, interrupted-run reasons, `restore`, `--restore`.
- `ui/live_runs.py`: D3 (`_launch_log`), D5 (actionable `LaunchError`), D7 (`_sequence`).
- `ui/server.py`: `timeout_s` on 14 launchable stages; `sequence` field in `/api/live`.
- `ui/app.js`: `seqSummary`.
- `ui/style.css`: `.seq`.
- `tests/test_run_tracking.py`: +5 tests.
- `tests/test_live_runs.py`: +5 tests.
- Logs (appended): `development_log/CHANGES.md` (C-117), `development_log/ERRORS_AND_BLOCKERS.md` (E-044–E-050).

## 8. Final results
| Check | Result |
|---|---|
| `./venv/bin/python -m unittest discover -s tests` | **670 tests OK**, exit 0, 0 skipped, 0 ResourceWarnings |
| browser | **70/70** |
| status, check-manifest, vps_verify, contract, `git diff --check` | all exit 0 |
| git | HEAD, history, `.git/index`, staged diff, unstaged path set and previously untracked files unchanged; nothing staged, committed or pushed |

## 9. Restart and manual acceptance (owner)
```
pkill -f "ui/server.py"; ./venv/bin/python ui/server.py      # then open http://127.0.0.1:8765/
```
1. The page opens on the Dashboard. The hero should say "All results current" (or name what is stale or failed), with 8 agent cards.
2. Open agent 10e → click **Run 10e** once. The Dashboard shows the launch; within seconds the run appears under Recent runs with its duration, without a reload.
3. Double-click **Run 10e** again. Only one launch appears.
4. Click **Run all 11 permitted stages**. The launch line lists "skipped (fresh)" for unchanged stages and "ran" for any re-run.
5. Restart the server while the page is open. The pill shows "connection lost — retrying", then recovers by itself.
6. Use back/forward between Dashboard, an agent and Candidates. Each view re-renders correctly.
7. Optional, interrupted-run recovery: `./venv/bin/python scripts/run_stage.py --restore <stage>` only ever restores md5-verified copies. Try it on a copy, not on the approved data.
