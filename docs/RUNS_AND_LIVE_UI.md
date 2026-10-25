# Tracked runs, freshness and the live dashboard

## Commands (repository root)
```bash
./venv/bin/python scripts/run_stage.py --status          # freshness of every stage
./venv/bin/python scripts/run_stage.py 06                # recompute VPS: staged -> validated -> published
./venv/bin/python scripts/run_stage.py 10h               # any stage id: 01 00 02 03 03c 04 05 08 06 eval 04b 07 diag 10a-10h
./venv/bin/python scripts/run_stage.py 06 -- --rank-convention midrank   # args after -- go to the stage
./venv/bin/python scripts/run_stage.py --adopt           # fingerprint pre-existing outputs (once; done 2026-10-15)
./venv/bin/python ui/server.py                           # dashboard at http://127.0.0.1:8765
```
Running a stage script directly (`python scripts/06_vps_fusion.py`) still works, but it is not a
tracked run. The dashboard then shows the changed outputs as **MODIFIED (unvalidated)**.

**Order after a change:** `03c → 04 / 05 / 08 → 06 → eval`, then the agents
`10c → 10f → 10a → 10d → 10e → 10b → 10g → 10h`. `--status` names every stage that is stale.

## Single source of truth
- **Dependency graph:** `ui/server.py` `STAGES` (inputs, outputs, `depends_on`). The dashboard
  shows the same registry, and `tests/test_ui.py` checks it against the scripts.
- **Run records:** `data/run_manifest.json`. `scripts/run_stage.py` is its only writer, and
  writes it atomically under a file lock. Per stage it keeps `last_attempt`, `last_success` and a
  200-entry history. Each record holds:
  - run id, start and finish times, exit code, status;
  - input and output fingerprints (md5);
  - validation result and redacted diagnostics;
  - for 06, the scoring model and rank convention.
- **Test runs:** remain in `data/test_run_metadata.json` (`scripts/record_test_run.py`).

## Freshness rules (derived at read time, `run_stage.status`)
| Status | Rule |
|---|---|
| RUNNING | the latest attempt is in progress and its process is alive |
| SUCCESS / PARTIAL / ADOPTED | the last success's recorded input and output fingerprints equal the current files, and no upstream stage is STALE |
| STALE | an input's content changed since the last success, or an upstream stage is STALE |
| MODIFIED | an output's content changed outside a tracked run (unvalidated). This does **not** propagate: a dependant that already consumed the file is consistent with it, but it is flagged `unvalidated_upstream` |
| FAILED | the latest attempt failed or was interrupted; the last good output (if any) is retained and named, never shown as fresh. `latest_attempt_failed` stays true even when the stage is also STALE |
| UNTRACKED / NOT_RUN | outputs exist without a record / no outputs |

Content, not timestamps, decides. Rewriting identical content does not invalidate anything.
md5 values are cached by size and modification time, so a poll costs a few `stat` calls.

## Publication
- **Stage 06:** runs with `--output-dir data/_runs/<run_id>/out`. Each file is written via
  tmp + `os.replace`. The result is validated:
  - all 8 outputs parse;
  - the required columns are present, with no duplicate compounds;
  - ranks and scores are finite and in [0, 1];
  - labels are binary;
  - `scripts/vps_verify.py` independently recomputes every score and rank.

  Only then is each file moved into `data/` with `os.replace`, and the manifest updated last.
  The previous files stay in `data/_runs/<run_id>/previous/`. A failed validation leaves `data/`
  untouched.
- **Other stages:** these write into `data/` themselves. Outputs under 50 MB are copied to
  `previous/` first. On failure the new files move to `failed/` and the previous ones are restored.
  Stages 04 and 05 exit 1 when some compounds failed (E-021); with valid outputs that is PARTIAL.
- **Coherence limit:** a reader could see a mix of old and new files during the few milliseconds of a
  multi-file publish. The page re-renders when the data version changes, which settles it.

## Live dashboard
- **Polling:** the page polls `GET /api/status` every 4 s (20 s when the tab is hidden; exponential
  backoff up to 30 s after errors). The endpoint returns the dependency-aware statuses, the VPS run
  in use, and a `data_version`: a hash of size and mtime of every registered output and the
  manifest. It reads no large artefact and never runs anything.
- **Indicator:** the header shows Running / N failed / N stale / current, and links to the run table.
  A banner explains a STALE, MODIFIED, FAILED or RUNNING VPS and names the run whose result is
  displayed.
- **Refresh:** when `data_version` changes, cached data is dropped and the current view re-renders
  in place, keeping the scroll position. Rankings, candidate pages and the comparison then come
  from the same files, and each shows "Scores from run …".
- **Connection loss:** shows "Connection to the local server lost — retrying", never success. On
  recovery the view reloads.
- **Why polling:** SSE, WebSockets and Streamlit were not needed. One cheap request every 4 s
  satisfies the requirements without a push channel or a new framework (D-025).

## Live pipeline (2026-10-20)
`#live` in the dashboard starts allow-listed stages through `scripts/run_stage.py` (single stage, or "run all permitted"
= `run_stage.py --sequence ...` in dependency order, fresh stages skipped, dependants of a failure BLOCKED).
- Policy (server-enforced, `ui/live_runs.py`): stages that rewrite protected/approved artefacts are refused; 04p, 05h
  and diag need a second confirming click (they may contact external services); offline agent stages are allowed.
- Requests: `POST /api/run` only, same-origin `Origin`, per-server nonce from `/api/session` in `X-EviRep-Nonce`,
  JSON body <= 1 KB. Every other POST is 405; no GET route starts anything.
- Launches are detached (they survive a server restart) and recorded in `data/_runs/_ui_launches/`; the run manifest
  stays authoritative. No cancellation (stopping the runner mid-stage would skip its restore-on-failure step).
- Progress: elapsed time and the stage's latest log line; no percentages.

## Dashboard (2026-10-20)
The application opens on the Dashboard (`/` or `#dashboard`), built only from `GET /api/live` (run tracker state, agent
output envelopes, run history, dashboard launches; never Markdown). Agent detail: `#agent/<id>` from `GET /api/agent`.
Research views (Candidates, Evidence, Mechanism, Conflicts, Review queue, Compare, Validation, Results summary) and
Diagnostics are secondary tabs. Updates: bounded polling (1.5 s while work is active, 4 s idle, backoff on errors,
slower in hidden tabs); a new `server_instance` makes an open page renew its run-control session after a restart.
