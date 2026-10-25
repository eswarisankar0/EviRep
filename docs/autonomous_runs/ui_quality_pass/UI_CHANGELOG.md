# UI changelog: quality pass (2026-10-20)

**Scope.** Only these files changed:
- `ui/server.py`: +148 / −4 lines;
- `ui/app.js`: +322 / −71;
- `ui/style.css`: +37;
- `ui/index.html`: +2 / −1;
- new `tests/test_ui_quality.py` (11 tests).

The architecture is unchanged:
- Python stdlib server, vanilla JS, no new dependencies or build step.
- No pipeline script, data file, score, label or report was modified.

## Wording and labels (A1, A7, A9)
- A single `LABELS` map plus `human()` covers every status, policy, conflict, replication, review, severity and temporal code. Examples:
  - `SUCCESS` → "Run completed"
  - `ADOPTED` → "Baseline (recorded)"
  - `STALE` → "Inputs changed"
  - `NOT_RUN` → "Not yet run"
  - `KEYWORD_DECIDED` → readable reason text
- Badges show the readable label and keep the exact code in the tooltip (`title`). The codes remain available for technical checking.
- Launch policy column ("can it run here?"):
  - "Can run here"
  - "Runs after confirmation"
  - "Unavailable from this screen", with the reason; the files it would rewrite are behind a `<details>`.
- Candidate table headers are renamed, and the outcome is shown as text instead of 1/0. The "Found in" file lists moved into Technical details.
- Tagline: "Parkinson's drug-repurposing evidence · runs start only when you click Run".

## Truthful freshness (A2, A3, A4)
- The Dashboard headline is derived from the tracker state:
  - "Current against tracked inputs"
  - "Inputs changed — rerun required"
  - "Freshness could not be verified"
  - "A run failed"
  - "Some stages have never run"
  - "Running"
- "All results current" was removed. A test asserts it is not reintroduced.
- **"Is it up to date?"** has four separate panels:
  1. **Runtime:** running, failed, latest run.
  2. **Stage freshness:** inputs changed, code not fingerprinted, untracked inputs, and the last successful run time.
  3. **Source data:** a table of each external source with its recorded retrieval or version date, or "not recorded".
  4. **Scientific validation:** the approved run, the independent recomputation, AUROC/AUPRC with intervals, open owner decisions (TD-042, TD-033, B-003) and the 28 trial links awaiting human review.
- Next-step text explains untracked inputs in plain words: re-running would rewrite an approved file, so the owner decides.
- The header `#refreshed` shows "Updated HH:MM:SS", or "Server not responding — last update …". It sits outside `#main`, so it does not break the identical-render skip.
- Agent cards show "Run failed" next to "Inputs changed" when the latest attempt failed (`latest_attempt_failed`).

## Charts (A5, A10, A11)
- All charts are inline SVG with no library. Each has a data-table alternative (`<details>`), a caption and a legend.
- **Dashboard:**
  - pipeline dependency graph (layered by depth, arrows, node colour by state);
  - stage-state bars;
  - recent-runs timeline;
  - AUROC/AUPRC interval chart.
- **Live Pipeline:** dependency graph and run-history timeline.
- **Candidate explorer:**
  - top-25 ranked bars, clickable and Enter-key accessible;
  - per-candidate dimension bars, with not-measured values hatched and imputed values marked.
- **Compare:** grouped dimension bars for the selected candidates.
- **Validation:**
  - ROC and PR curves, computed from `vps_scores_v2.csv` and served only when their areas equal the approved report within 1e-9;
  - model comparison intervals;
  - paired 5D−4D difference with a zero reference line;
  - ablation, with the in-sample (grid-search) row hatched and labelled;
  - missing and imputed counts by dimension.
- **Mechanism:** drug → target → disease chain. Solid edges are direct associations; dashed edges are shared pathways.
- **Review queue:** counts by reason (chart), a search box, a reason filter and a live count.

## Size and controls (A6, A8)
- Evidence shows 100 rows plus "Show 100 more". The source-file column is hidden behind "Show source files (technical)".
- Review queue: search (`#rq`), reason filter (`#rflag`), count (`#rcount`).

## Server
- New `GET /api/validation_charts` (read-only).
- `/api/live` adds `freshness`, `sources` and `science`.
- `build_ranking` rows add `dimensions_imputed`.
- Agent cards add `latest_attempt_failed`.
- Staleness reuses the runner's fingerprint cache (`_stale_cached`): a `/api/live` poll dropped from about 400 ms to about 12 ms. The result is identical to `agent_contract.stale_inputs` for all 8 agents.
- The server still never reads `os.environ` (TD-029) and still binds to loopback only.
