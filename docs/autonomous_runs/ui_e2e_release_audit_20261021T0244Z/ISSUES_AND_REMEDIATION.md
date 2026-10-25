# Issues and remediation (audit 2026-10-21)

**Priority scale:**
- **P0:** blocks release or risks a wrong scientific claim.
- **P1:** must be resolved before anything is presented as current or production-ready.
- **P2:** defect with a workaround.
- **P3:** polish.

"Owner" means the item needs an explicit decision or authorisation. This audit did not act on it (mission rules 4, 5 and 8).

## Open, owner decisions

| ID | P | Issue | Evidence | Remediation (not executed) |
|---|---|---|---|---|
| TD-042 | P0 | The approved molecular rule is under question; the corrected rule `td042_v1` scores AUROC 0.699 [0.557, 0.830] vs approved 0.775; difference +0.076 [0.014, 0.158] | `VPS_AND_SCIENTIFIC_VALIDATION.md` §4; Validation §7 in the UI | Owner decides. If adopted: `data/_candidates/td042_v1/publish_td042.sh` (rehearsed), then `run_stage.py eval` |
| E-056 | P0 | Stage-03 pagination: the cohort rebuild is pending; **Dopamine would join the cohort** | `development_log/ERRORS_AND_BLOCKERS.md` E-056 | Owner approves a stage-03 rebuild in an isolated copy, then compares with `scripts/compare_result_sets.py` |
| TEMP | P1 | Temporal validity of the evidence against the cutoff is an open methodological limitation | `TECHNICAL_DEBT.md` | Owner / methodology |
| B-004 | P1 | Lithium label depends on the registry intervention type (0 now; content-based reading gives 1, AUROC → 0.7573) | E-log B-004 | Owner decides the labelling rule |
| GAL | P1 | Galantamine / Rifaximin items | previous `overnight_audit_20261021/REMAINING_BLOCKERS.md` | Owner |
| REV-28 | P1 | 28 trial-role links await human adjudication (never auto-decided; drive7 asserts "Awaiting human review (28)") | `review` stage | Human reviewer |
| EVAL-FP | P1 | `eval` last success did not fingerprint `data/reproducibility.json`, so the overall state is `VERIFIED_WITH_GAPS` | `/api/live` freshness | Owner approves `./venv/bin/python scripts/run_stage.py eval` (output byte-identical expected) |
| COMMIT | P1 | The staged index is an older, partial snapshot: no `ui/`, run tracker or 591 of the tests; 15 staged files are older than the working tree | `COMMIT_READINESS.md` | Owner chooses the commit scope; stage by explicit paths; re-run the suite on the exported index |
| SEC-PROD | P1 (release) | No authentication, TLS, multi-user support or rate limiting; loopback-only by design | `SECURITY_AND_ACCESSIBILITY.md` | Required before any non-local deployment |
| DEF-05/08 | P2 | Deferred atomic-write patch for protected stages 05/08 | E-059; `overnight_audit_20261021/records/deferred_atomic_write_05_08.patch` | Apply with the next owner-approved run of 05/08 |

## Found and fixed in this audit (minimal, reversible, tested)

| ID | P | Issue | Fix | Verification |
|---|---|---|---|---|
| A-5 | P2 | A single-stage re-run after a dependency's failed attempt silently used the restored output | `scripts/run_stage.py` `status()` adds a warning naming the failed dependency; `ui/app.js` shows stage `warnings` in the Run Center state cell | `test_a_failed_dependency_is_flagged_on_its_dependants` (warning shown, then cleared after a successful re-run) |
| A11Y-1 | P2 | The Run Center chart "Stages by tracked state" had no data-table alternative | removed `noTable: true` (`ui/app.js`) | drive19: 23/23 charts labelled with tables (before: 1 missing); `test_every_chart_keeps_its_data_table_alternative` |
| UI-1 | P3 | Run Center stage table: a `nowrap` stage-name column squeezed the other columns | only the stage ID is `nowrap` (`ui/app.js`, `ui/style.css`) | before/after screenshots; Run Center browser suites re-run (`TEST_RESULTS.md`) |
| OPS-1 | P2 | The live server ran code older than the working tree (`server_code_changed: true`) | restarted the audit's own server process with the canonical command | `server_code_changed: false`; single instance on 127.0.0.1:8765 |
| REG-1 | P3 | No test guarded the stage-graph integrity | new `tests/test_stage_registry_integrity.py` (8 tests) | passes |

## Investigated, not defects
- **drive18 "Clear filters" NO_EFFECT:** there was nothing to clear on a clean page. A targeted re-test (set filters, then clear) passed: 90 → 1 → 90 rows (`records/browser/results18b.json`).
- **30 ALREADY_ACTIVE controls:** these are navigation items for the current page (`aria-current=page`); clicking one does nothing by design.
- **vps_verify "median-imputed (unflagged)":** this refers to the raw input; the published score flags both compounds (`docs/VPS_EVALUATION.md:80`).
- **Midrank vs legacy rank convention:** 0.7744 vs 0.7754. The approved convention is legacy, used consistently.
