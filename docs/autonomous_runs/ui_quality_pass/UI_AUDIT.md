# UI audit: before the quality pass (2026-10-20)

**Method.** A headless Chrome inventory was taken of all 16 routes on the live server, before any change. It counted headings, badges, buttons, links, table headers, selects, characters, raw machine codes and file paths per route (`scratchpad/cdp/inventory.py` → `inventory.json`).

**Baseline.**
- Git: HEAD `576bc7f`; 25 staged, 21 unstaged and 254 untracked files; no stashes.
- Recovery snapshot: `~/EviRep_recovery_uiq_20261020T1153Z`, restore verified byte-identical.
- Python tests: 673 OK.

## Findings

| # | Area | Finding | Severity |
|---|---|---|---|
| A1 | All routes | Status badges showed raw machine codes, for example `SUCCESS`, `ADOPTED`, `CROSS_DOMAIN_TENSION`, `KEYWORD_DECIDED` and `STRUCTURE_INSUFFICIENT`. Raw-code count per route: Dashboard 15, Live 33, Candidates 76, Conflicts 113, Review 110, Pipeline 130, Cases 108. | High (readability) |
| A2 | Dashboard | The headline said **"All results current"** whenever no tracked stage was stale. This merged four different facts into one claim: runtime success, input freshness, source-data age and scientific validation. Untracked inputs (e.g. `data/reproducibility.json` for `eval`) were only mentioned in the next-step text. | High (truthfulness) |
| A3 | Dashboard | Data-source retrieval dates were not shown anywhere. openFDA, Open Targets and Hetionet have no recorded retrieval time in any artefact. | Medium |
| A4 | Dashboard | The "checked HH:MM:SS" time was inside the re-rendered `#main` area. A per-poll timestamp in `#main` defeats the identical-render skip (E-043), so it has to live outside `#main`. | Medium |
| A5 | All | There were no charts: no dependency graph, metric intervals, ROC/PR curves, ranking bars or mechanism chain. | Medium (requested) |
| A6 | Evidence | 74,482 characters and 400 file paths were rendered at once (first 400 rows, plus a "source file" column on every row). | Medium |
| A7 | Candidates | 48,823 characters; column headers were codes (`prox`, `clin`, `lit`, `10d status`); the label was shown as `1` / `0`. | Medium |
| A8 | Review queue | 28 unresolved links with no search, no filter by reason and no counts by reason. | Medium |
| A9 | Live Pipeline | The policy column showed `ALLOWED` / `CONFIRM` / `REFUSED` with the full list of protected file names inline. | Low |
| A10 | Candidates | The two median-imputed proximity values (Deferiprone, Trimethobenzamide) looked the same as measured values. | Medium (truthfulness) |
| A11 | Validation | The 5D–4D paired difference and the in-sample ablation were shown only as table text. The in-sample (grid-search) result was not visually separated from the primary result. | Low |
| A12 | Performance | Each `/api/live` poll re-hashed 485 files (about 400 ms). | Low |

## What was already correct (kept)

- The runtime state comes from `data/run_manifest.json` (tracker), never from file times.
- Launch policy is enforced server-side (ALLOWED / CONFIRM / REFUSED), with nonce and same-origin checks.
- There is no cancel button. Cancelling would skip the restore step.
- The review queue is read-only. Nothing in the UI adjudicates.
- The pending candidate `td042_v1` is listed as pending, never displayed as a score.
