# Test results (audit 2026-10-21)

Every line below was executed in this audit and its output saved. Nothing is reported as passed without a log.

## Python suite

| Run | Tests | Result | Warnings | Log |
|---|---|---|---|---|
| Baseline (before any change) | 741 | OK, exit 0 | 0 | `logs/tests_baseline.log` |
| Exported staged index only (`git checkout-index`) | 160 | OK | 0 (only placeholder-key notices from fixtures) | `logs/tests_staged_tree.log` |
| **Final code** (after every fix) | **751** | **OK, exit 0** | **0** | `logs/tests_final.log` |

The 10 new tests are:
- `test_stage_registry_integrity.py`: 8 tests;
- `test_agent_failure_modes.py`: +1 test;
- `test_ui_quality.py`: +1 test.

## Gates (final, `logs/gates_final.log`)
- `run_stage.py --check-manifest`: ok.
- `vps_verify.py`: MATCH, 90 compounds, max |diff| 2.22e-16.
- Protected sha256: 19/19 OK.
- `git diff --check`: clean. `node --check ui/app.js`: OK.
- Git index: byte-identical to the baseline; staged md5 unchanged.
- Live server: `server_code_changed: false`.
- Leftover runners: 0.

## Browser suites (real Chrome via CDP)

| Suite | Scope | Final-code result |
|---|---|---|
| drive16 | biomedical UX acceptance, refusals, runs | 47/47 (run twice: before and after UI-1) |
| drive15 | UI quality: routes, charts vs data, labels | 24/24 |
| drive11 | live application acceptance, run lifecycle | 16/16 (re-run after UI-1; one earlier attempt lost its Chrome websocket after 12 passes, see note) |
| drive12 | runtime reliability: double click, two tabs, kill, malformed manifest, injection | 10/10 |
| drive14 | slow/frozen server, next-step guidance | 9/9 |
| drive7 | live server :8765, read-only | 21/21 (twice) |
| drive8 | UI copy checks | 8/8 |
| drive9 | live pipeline end to end, restart mid-run, failure restore | 15/15 (twice) |
| drive13 | timeout lifecycle (20 s timeout in the copy only) | 9/9 |
| **Total scenario suites** | | **159/159** |
| drive18 | behavioural audit: 186 controls operated one by one | 155 effect, 30 already active, 1 no-effect re-tested → PASS; 0 JS exceptions |
| drive18b | targeted "Clear filters" re-test | PASS (90 → 1 → 90 rows) |
| drive19 | accessibility tree on 16 routes | 0 unnamed controls; 23/23 charts labelled with tables (1 missing before the fix) |

drive12, drive14, drive15, drive8 and drive13 were not re-run after UI-1, a CSS/markup change limited to the Run Center stage-name cell. They passed on the code immediately before it. drive16, drive9, drive11, drive7 and drive19, which cover the Run Center table, all passed after it.

**Harness note:** the first post-UI-1 drive11 run ended with `websockets ConnectionClosedError` (the CDP connection to Chrome dropped) after 12 passing scenarios and 0 failures. The immediate re-run passed 16/16. This was classified as a harness connection failure, not an application failure. The log is kept in `records/browser/suites_final2.out`.

## Security probes
16 probes, all as expected (`logs/security_probes.txt`). Credential scan: 0 matches (`logs/credential_scan.txt`).

## Not executed
- Online stages against live APIs.
- Screen readers; browsers other than Chrome.
- Load testing.
- The full drive17 link crawl. It last ran in the previous audit on earlier code: 2,118 controls, 1,378 links, 0 dead.
