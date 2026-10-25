# EviRep final live-runtime gate (2026-10-20, 10:36Z–11:08Z)

## Decision
**PASS for local, single-user research use on loopback.**

**Not a production release:** there is no authentication, HTTPS or multi-user isolation, and the owner's scientific decisions are still open.

Every check below was run. Results use PASS / FAIL / BLOCKED / NOT TESTED. "Error-free" is not claimed.

## 1. Python tests
| Run | Command | Window | Exit | Result |
|---|---|---|---|---|
| before | `./venv/bin/python -m unittest discover -s tests` | 10:36:07–10:37:14Z | 0 | 670 OK |
| after | same | 11:05:00–11:05:52Z | 0 | **673 OK**, 0 skipped, 0 ResourceWarnings |

Gates after changes, each exit 0:
- `run_stage.py --status`
- `run_stage.py --check-manifest`
- `vps_verify.py`
- the ground-truth contract (9/9)
- `git diff --check`

Logs are in `logs/`.

## 2. Real-browser acceptance
Real Chrome (CDP) → real server → real `scripts/run_stage.py` → real stage processes, on isolated copies.

| Suite | Result | Evidence |
|---|---|---|
| timeout lifecycle (new) | **9/9** | `TIMEOUT_BROWSER_TEST.json`, `evidence/browser_drive13.json` |
| frozen server, next step, validity labels (new) | **9/9** | `evidence/browser_drive14.json` |
| acceptance | 16/16 | `evidence/browser_drive11.json` |
| reliability | 10/10 | `evidence/browser_drive12.json` |
| general | 21/21 | `evidence/browser_drive7.json` |
| polling / corrupt manifest | 8/8 | `evidence/browser_drive8.json` |
| stage control | 15/15 | `evidence/browser_drive9.json` |
| **Total** | **88/88** | |

## 3. Timeout and recovery
**Setup:** an isolated code + data copy. Stage 10h was given a 20 s timeout and a controlled hang **in the copy only**; production stays at 900 s.

**Result:** browser launch → RUNNING with the real log line → real partial write → TIMEOUT at about 21 s → FAILED shown without a refresh. Then:
- the output was restored **byte-identical**;
- the child and runner are gone (runner reaped);
- an unrelated sentinel process and the server were untouched;
- no orphan or RUNNING record remains;
- the next run recovered. **PASS.**

**Timeout appropriateness** (`evidence/timeout_appropriateness.json`, measured against recorded runs):
| Stages | Timeout | Slowest observed | Headroom |
|---|---|---|---|
| offline agents, review, 07 | 900 s | ≤ 5 s | ≥ 180× |
| 05h | 3600 s | 178 s | 20× |
| 04p | **raised 3600 → 7200 s** | 570 s live | 12.6× (was 6.3×) |
| diag | 3600 s | never run under the tracker | estimate |
| protected / long live stages | none | — | refused from the dashboard |

**Killed runner:** interrupted run, orphan reported, md5-verified `--restore`. PASS (`TestRunnerKilledMidStage`, browser drive12).

## 4. Network stages (`NETWORK_STAGE_VERIFICATION.json`)
| Stage(s) | Result | Detail |
|---|---|---|
| 04p | **PASS (live)** | forced PubMed re-query, isolated copy; pre-cutoff PMID sets identical (2/2, 308/308) |
| 05h | **PASS (live)** | DailyMed history fetched live for Lovastatin; row identical; parser 83/83 |
| diag | NOT TESTED | about 250 requests; not needed for this gate |
| 01, 03, 03c, 04, 05, 08, 04b | BLOCKED | dashboard policy: they rewrite protected artefacts or need live services. 04 additionally lacks a Semantic Scholar key |

**Credentials** (checked by name only): `NCBI_API_KEY` and the Semantic Scholar key are absent. The NCBI key is optional; the Semantic Scholar key blocks stage 04.

**Connectivity:** PubMed, ClinicalTrials.gov, openFDA and DailyMed return 200. Semantic Scholar was not retried (known 429).

## 5. Defects found this pass
| ID | Reproduction | Fix | Regression test | Status |
|---|---|---|---|---|
| D8 | a finished runner stayed a **zombie**, and its exit code was recorded only when a page polled | a daemon reaper thread per launch: waits, reaps and records the exit code immediately | `TestRunnerReaped` (fails before) + browser drive13 | FIXED, PASS |
| D9 | the 04p timeout had only 6.3× headroom over its real 570 s live run | raised to 7200 s (raised, never lowered) | `timeout_appropriateness.json` | FIXED |
| O1 | the Dashboard did not say what to do next, or separate process success from scientific validity | `next_actions` from tracked state (who: anyone / owner / operator); cards show "run" status separately from "output contract valid"; results panel states that process success is not scientific validation | `TestNextActions`, browser drive14 | DONE, PASS |

**Re-verified with no defect:** truncated or invalid-UTF-8 logs (new test), a frozen or slow server (single-flight polling, timeout, recovery), multiple tabs, double-clicks, malformed manifests, path confinement, HTML escaping, server restart with session renewal, permission errors.

**Harness issues, all mine and fixed:** a sentinel inheriting the output pipe, a variable collision in the CDP driver, reuse of a deleted path by a still-running runner, and 34 accumulated headless tabs. None reflected product behaviour; where one affected a result it was re-run cleanly.

## 6. Artefact integrity (`ARTIFACT_INTEGRITY.json`)
- **20 tracked artefacts:** the 19 protected files (ground truth, approved scores, evaluation report and others) plus `run_manifest.json`. All have **identical sha256** before and after.
- **Git:** HEAD, history, `.git/index`, the staged diff and the unstaged path set are unchanged; nothing was staged, committed or pushed.
- **Discrepancy B-003:** documented separately and not corrected.

## 7. Files changed this pass
- `ui/live_runs.py`: reaper (D8).
- `ui/server.py`: `_next_actions`, `output_envelope_valid` / `output_stale_inputs`, 04p timeout 7200.
- `ui/app.js`: Next-step panel, "run" vs "output contract valid", validity statement.
- `ui/style.css`: Next-step styles.
- `tests/test_live_runs.py`: +1.
- `tests/test_live_app.py`: +1.
- `tests/test_run_tracking.py`: +1.
- Logs (appended): `development_log/CHANGES.md` (C-118), `development_log/ERRORS_AND_BLOCKERS.md` (E-051).

## 8. Restart and owner acceptance
```
pkill -f "ui/server.py"; ./venv/bin/python ui/server.py      # then open http://127.0.0.1:8765/
```
1. Dashboard: the **Next step** panel names exactly one owner follow-up today (eval's untracked input). The 8 agent cards show "run SUCCESS/ADOPTED" and "output contract valid".
2. Open agent 10e → click **Run 10e** once. Within seconds Recent runs gains a row with its duration; no reload is needed.
3. Click **Run all permitted stages**. The launch line lists "skipped (fresh)" for unchanged stages.
4. Stop the server (Ctrl-C) with the page open. Within about 20 s the pill says "connection lost — retrying". Start it again and the page recovers by itself.
5. Use back/forward between Dashboard, an agent page and Candidates.
6. Optional, on a copy only: `./venv/bin/python scripts/run_stage.py --restore <stage>` restores only md5-verified outputs.
