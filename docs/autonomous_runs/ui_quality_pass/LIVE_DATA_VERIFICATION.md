# Live data verification

## Polling
- **Requests.** The page polls `/api/status` and `/api/live` in a single flight, with backoff on errors. It polls faster while a run or launch is active.
- **No side effects.** Opening or refreshing a page never starts a stage, test or network request. drive9 checks this ("opening and reloading pages starts nothing"): manifest history and the launch count stay unchanged.
- **Render skip.** Identical HTML is not re-rendered (E-043), so clicks are not swallowed. The per-poll time is shown in the header `#refreshed`, outside `#main`.
- **Lost connection.** If the server stops, the header shows "Server not responding — last update HH:MM:SS". On reconnect a still-running stage is shown as running again (drive9 restart scenario).
- **Poll cost.** `/api/live` takes about 12 ms (was about 400 ms) because the runner's fingerprint cache is reused. Staleness is checked by content fingerprint, never by modification time.

## Freshness facts and where they come from

| Fact shown | Source | Test |
|---|---|---|
| Last successful run (UTC) | max `last_success.finished_utc` in the tracker | `test_freshness_comes_from_the_tracker`; drive15 |
| Inputs changed | stages with status STALE / MODIFIED / MISSING | same |
| Code not fingerprinted | stages with a last success but no recorded code fingerprint | same |
| Untracked inputs | declared inputs not fingerprinted at the last success | `_next_actions` wording; drive15 hero |
| Source retrieval dates | recorded in artefacts only; otherwise "not recorded" | `test_sources_never_invent_a_retrieval_time` |
| AUROC / AUPRC / CI | `vps_evaluation_report.json` | drive15; unit tests |
| Reviews awaiting / adjudicated | `build_review` (`n_unresolved` 28, `n_adjudicated` 9) | `test_science_counts_match_the_artefacts` |
| Live run activity | elapsed time and the latest log line; no percentage | drive9, drive11, drive13 |

## Failure states are never shown as success
- **Timeout.** It is shown as "Run failed" (`FAILED`, `TIMEOUT` in the tooltip) and the previous output is restored (drive13).
- **Corrupt manifest.** The headline reads "Freshness could not be verified", the reason is given, and launches are disabled (drive8, drive9, drive12).
- **Failed attempt with the previous output kept.** The agent card shows "Inputs changed" **and** "Run failed" (drive11 6b).
- **Server restart during a run.** The launch is shown as "started before this server; see the run table". Completion is not guessed.
