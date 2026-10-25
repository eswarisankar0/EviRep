# Remaining blockers, untested items and owner decisions

## Owner-only scientific decisions (untouched; shown on Overview and Run Center)

| Decision | State | Where it appears |
|---|---|---|
| TD-042: corrected molecular-dimension rule | An unapproved alternative result set exists (independently verified) and is **not adopted**. Its identifier appears only in technical details. | Overview › Technical details; Run Center › Scientific validation |
| TD-033: temporal validity | Literature, safety and molecular evidence are current snapshots, so the evaluation is not leakage-free. | Overview, Validation § 6 |
| B-003: evaluation reproducibility | A from-source rerun gives AUROC 0.7763 versus the approved 0.7754. | Validation § 5 |
| 28 clinical-trial role links | Await human adjudication. The application shows them and never decides. | Evidence › Trial-role review; Overview "What needs attention" |
| Label re-freeze policy | Open. | — |
| Untracked input of `eval` | `data/reproducibility.json` was not fingerprinted at the last evaluation-report run. Re-running rewrites the approved report, so it is left for the owner. | Overview "Results" line; Run Center |

## Pipeline defects found by the agent audit (not fixed: pipeline code, outside the UI scope)

These are A-1 to A-7 in `AGENT_CONTRACT_AUDIT.md`:
- partial results of 04p, 05h and 10a-all are discarded;
- 10g accepts a header-only literature CSV as SUCCESS;
- 10d silently skips malformed molecular lines;
- 10h uses data from FAILED upstream outputs and ignores 10b;
- stage 08 has no timeout;
- several writes are non-atomic;
- absent inputs are not fingerprinted.

Each fails safe or is limited in effect today. Reproduction steps and suggested fixes are in that file.

## Not tested, or tested only partly

| Item | Status | Why / how to test |
|---|---|---|
| Full online runs of 04p, 05h, `10c --fetch`, `10f --fetch` | NOT TESTED | About 250–600 requests each. Client functions were verified on one compound instead (`ONLINE_INTEGRATION_RESULTS.md`). To test: `./venv/bin/python scripts/run_stage.py 04p --root <isolated copy>` after confirming. |
| Network stages 01, 03, 03c, 04, 05, 08 | NOT TESTED (by policy) | They rewrite protected artefacts. Owner decision. |
| Semantic Scholar | BLOCKED | HTTP 429 anonymously; no API key is configured. |
| Production-length timeouts (04p 7200 s, 10h 900 s) | NOT TESTED | Only the 20 s copy timeout was exercised (drive13). |
| Rate-limit and backoff behaviour against live services | NOT TESTED online | Covered only by **mocked** unit tests. |
| Screen readers | NOT TESTED | Tested instead: keyboard order, `aria-current`, `aria-sort`, `aria-live` counts, chart data-table alternatives, and colour plus symbol for status (✓ / ! / ✕). |
| Browsers other than Chrome | NOT TESTED | Only headless Chrome was used. |
| Colour contrast of new styles | Partly tested | The new CSS uses only the existing tokens, which `tests/test_ui.py::TestAccessibleContrast` checks. No new colour values were added. |

## Recommended next actions (owner)

1. Review the new navigation and wording on the live app: `./venv/bin/python ui/server.py`, then open http://127.0.0.1:8765/.
2. Decide TD-042, TD-033, B-003 and the 28 trial-role links.
3. Decide whether to re-run `eval` to fingerprint `data/reproducibility.json`. This rewrites the approved evaluation report.
4. Schedule fixes A-1 to A-4, which affect data quality signals, ahead of A-5 to A-7.
5. If a Semantic Scholar key exists, set it in the shell environment (never in the repository) and re-run the online check.
6. Review and stage the changes yourself. Nothing was staged or committed.
