# Live data and freshness audit

The application now keeps seven properties separate. None of them is inferred from another.

| Property | Where it is shown | Authority | Never inferred from |
|---|---|---|---|
| Server availability | header: "Updated HH:MM:SS" / "Server not responding — last update …" | the `/api/status` poll itself | — |
| Current execution | header pill; Run Center "Runtime"; stage table "Running" with elapsed time and latest log line (no percentage) | `data/run_manifest.json` via `scripts/run_stage.py` | process lists, file dates |
| Outcome of an individual run | stage badges; agent cards ("Run failed" beside "Inputs changed — rerun needed" when an older result is retained) | manifest `last_attempt` / `last_success` | output file existence |
| Stage input freshness | Overview "Results" line; Run Center hero and "Stage freshness" | content fingerprints recorded at the last success | modification times |
| Source retrieval date | Overview "Source data" line; Run Center source table | dates recorded in artefacts only. openFDA labels, Open Targets and Hetionet show **"not recorded"** | file timestamps, run times |
| Saved result matches provenance | "independent recomputation matches"; validation curves drawn only when they reproduce the report | stage-06 verification record; `/api/validation_charts` | — |
| Scientific validity | Overview "Scientific validation" line; Validation section 6; open owner decisions | evaluation report + owner decision list | run success |

## Change in this pass: untracked files are never "current"

**Before.**
- A stage whose last success did not fingerprint one of its declared inputs still counted as CURRENT. This was the case for `eval`, which reads `data/reproducibility.json`.
- The header pill was green.
- The Run Center message described every unfingerprinted file as an input that "would rewrite an approved file", even for stages that rewrite nothing protected.

**Now.**
- `ui/server.py` `_unfingerprinted()` separates unfingerprinted **inputs** from **outputs** (`freshness.untracked_inputs`, `freshness.untracked_outputs`).
- The overall state becomes **`VERIFIED_WITH_GAPS`**, with the headline "Current against recorded inputs, with unverifiable inputs" and a warning colour, not green.
- `/api/status` lists such stages under `by_status.UNVERIFIABLE`. The header pill reads "Current against recorded inputs — some inputs not verifiable".
- The next-step text says "this is the owner's decision" **only** when a re-run would rewrite a protected artefact (`_rewrites_protected`).

**Current repository state:** `VERIFIED_WITH_GAPS`. The VPS evaluation report (`eval`) reads `data/reproducibility.json`, which was not fingerprinted at its last run. Re-running it rewrites the approved evaluation report, so it is left for the owner.

**Regression tests (`tests/test_agent_failure_modes.py`):**
- `test_untracked_input_is_reported_and_blocks_the_current_state` removes one recorded input fingerprint in an isolated copy. It then asserts that:
  - the input is listed;
  - the state is not CURRENT;
  - `/api/status` marks the stage UNVERIFIABLE;
  - a next action names it.

  This test fails on the code before this pass, where the state was CURRENT.
- `test_untracked_output_is_not_described_as_an_input`.

## Stale and failed inputs (real runner, isolated copy)

- **Malformed input.** `test_each_agent_fails_closed_on_a_malformed_input` runs all nine agent stages with a malformed input. Each run is FAILED, the output is byte-identical, last success is unchanged, `latest_attempt_failed` is set, and the overall state is FAILED. The Overview then reads "Last run failed; previous results retained".
- **Upstream failure.** `test_upstream_failure_blocks_dependants_in_a_sequence`: when 10d fails, 10h is BLOCKED.
- **Changed input.** Browser suite drive9 changes an input in the copy; its dependants show "Inputs changed — rerun needed" without a reload.
- **Timeout.** drive13 shows the timeout lifecycle: running, then time limit exceeded, then FAILED, then the partial output restored.

## Polling (measured, drive16)

- **Idle.** In 20 s with no run active, the page made only `/api/status` requests, one about every 4 s. No other request was made.
- **Cost per request.** About 7 ms for `/api/status`. `/api/live` takes about 10 ms warm and is requested only on render of the Overview, Validation and Run Center pages; the Run Center re-renders on each poll.
- **Section loads.** Each section renders in under 2 s on this machine. See `BROWSER_ACCEPTANCE.md` for the measured times.
- **No side effects.** Opening every page, refreshing and polling started no run: manifest history and the launch count were unchanged (drive16, drive9).
- **Back-off.** Polling backs off to 30 s after errors and to 20 s when the tab is hidden; this is unchanged.
