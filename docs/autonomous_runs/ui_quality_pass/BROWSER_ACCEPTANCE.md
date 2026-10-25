# Browser acceptance (real headless Chrome via CDP)

**Setup.** Chrome on port 9333 drove a server on an isolated scratchpad copy (port 8799) with the real `scripts/run_stage.py` and real stage processes. Each suite started on a fresh copy.

**Result: 112 / 112 checks pass, across 8 suites, on the final code.** Raw results: `evidence/browser_drive*.json`, console output `evidence/drive*.out`, driver scripts `evidence/drive*.py`.

| Suite | What it exercises | Result |
|---|---|---|
| drive15 (new) | UI quality: 13 routes, no raw codes, hero from the tracker, last-run time, dependency graph, AUROC equals the report, source table "not recorded", header refresh time, ROC/PR vertices, missing-data chart, paired-difference zero line, ranking bars (click + Enter), search, sort, compare add/remove + grouped chart, evidence paging and toggles, mechanism chain, review counts / search / filter, back navigation, 390 px no overflow on 7 views, no JS errors / console errors / failed requests | **24 / 24** |
| drive11 | Dashboard live: launch from an agent page, RUNNING with elapsed time, failure shown (hero, counter, card "Run failed") | **16 / 16** |
| drive12 | Malformed manifest: "Freshness could not be verified" plus reason, `/api/live` 200 | **10 / 10** |
| drive14 | Agent cards: run state and output checks shown separately; "neither is a scientific validation" note | **9 / 9** |
| drive7 | Navigation, keyboard focus, review queue (28 awaiting human review, none auto-decided), accessibility | **21 / 21** |
| drive8 | Corrupt manifest: run table "Unknown" with reason; launches disabled | **8 / 8** |
| drive9 | Live Pipeline end to end: page loads start nothing; confirm/back; upstream change → "Inputs changed" live; Run all; real paused stage shown running without a percentage; second launch refused (409); server restart mid-run → connection lost → reconnect; resumed completion; real failure → "Run failed" with the previous output byte-identical; corrupt manifest; 390 px | **15 / 15** |
| drive13 | Timeout lifecycle on an isolated code+data copy (10h `timeout_s` 20 **in the copy only**; production stays 900 s): launch → running → timeout → failed → partial output restored; no zombie; unrelated process untouched | **9 / 9** |

## Expectation updates in older suites (test text only, no product behaviour relaxed)

Older suites were updated because the visible wording or structure changed. Each update still checks the same fact.

| Suite | Old expectation | New expectation | Same fact checked |
|---|---|---|---|
| drive11 | `.fnode` | `.dag .node` | dependency graph present |
| drive11 | "running 10g" | "running" + elapsed time | run shown as running |
| drive12 | hero "Run records unreadable" | hero "Freshness could not be verified" (the banner still says "Run records unreadable" with the reason) | unreadable manifest is not shown as current |
| drive14 | "contract valid" | "Output checks: passed" | output validity shown separately from run status |
| drive7 | "Awaiting adjudication (28)" | "Awaiting human review (28)" | 28 links still unresolved |
| drive8 | "UNKNOWN" | "Unknown" (the code is still in the tooltip) | unknown state shown |

drive9's `row()` helper now selects rows from the stage table only. The dependency graph's data-table alternative has rows with the same stage ids and was being matched first.

Product fix found by drive11 6b: a stage whose inputs changed **and** whose latest attempt failed showed only "Inputs changed" on its agent card. The card now also shows "Run failed".

## Not exercised in a browser
- Network-dependent stages (04p PubMed, 05h DailyMed, diag ClinicalTrials.gov): only the confirm/back flow was clicked; no real network run.
- Long production timeouts (04p 7200 s, 10h 900 s): only the 20 s copy timeout was exercised.
- Screen readers. Tested: keyboard focus, `title` tooltips and the data-table alternatives.
- Browsers other than Chrome.
