# Executive summary: EviRep end-to-end UI verification and commit-readiness gate (2026-10-21)

## What was verified, by execution
- **UI controls:** 16 routes and 186 controls were operated one by one in real Chrome, with 0 dead controls and 0 JS exceptions.
- **Browser scenarios:** 159/159 passed across 9 suites. They cover run launch, failure, restore, timeout, server restart mid-run, concurrency, corrupt manifest, frozen server and mobile width.
- **Accessibility tree:** 0 unnamed controls; every chart has a label and a data table.
- **Python suite:** 751 tests OK with 0 warnings (baseline was 741).
- **Science:** the approved VPS was reproduced independently.
  - Results: AUROC 0.775376 [0.656, 0.881], AUPRC 0.424, 4D 0.700; max score difference 2.2e-16.
  - The API and UI equal the artefact for all 90 compounds.
  - Weight vectors are valid for every variant; grid weights are overfitted (held-out AUROC is 0.12–0.14 lower).
  - 5D vs 4D: +0.075, CI [−0.025, 0.176], **not significant**.
- **Agents:** all eight are valid and current; their failure modes were tested.
- **Security:** 16 active probes were all refused as designed. No credentials appear anywhere, including git history.
- **Protected data:** 19/19 protected artefacts unchanged. The git index is byte-identical to the baseline. Nothing was staged, committed or pushed.

## Fixed (minimal, reversible, tested)
- **A-5:** a failed dependency is now flagged on its dependants.
- **A11Y-1:** a chart without a text alternative now has one.
- **UI-1:** the cramped Run Center stage table now wraps stage names.
- **OPS-1:** a live server running stale code was detected by its own flag and restarted.
- **REG-1:** a new stage-graph integrity test.

## Verdict 1: commit readiness — **CONDITIONAL, not recommended as-is**
The current index (25 entries) passes its own tests (160) and contains no secrets. However:
- it lacks `ui/`, the run tracker, 7 of the 8 agents and 591 of the 751 tests;
- 15 of its files are older than the working tree, including stage 03 without the pagination fix.

The owner should choose the scope, stage by explicit paths and re-run the full suite on the exported index (`COMMIT_READINESS.md`).

## Verdict 2: release readiness — **NOT READY**
- **Engineering:** research-grade and verified for local, single-user use.
- **Scientific blockers (owner decisions):** TD-042, the stage-03 cohort rebuild (Dopamine joins), temporal validity, Lithium, Galantamine/Rifaximin, 28 trial-role links awaiting human review, and the `eval` input fingerprint.
- **Deployment blockers:** no authentication, TLS or multi-user support; loopback-only by design.

## Highest-priority blockers
1. TD-042 decision (P0)
2. Stage-03 cohort rebuild, E-056 (P0)
3. Commit scope (P1)
4. `eval` fingerprint run (P1)
5. 28 human reviews (P1)
6. Lithium / Galantamine / temporal validity (P1)
7. Authentication and TLS before any non-local use

## Reports
`docs/autonomous_runs/ui_e2e_release_audit_20261021T0244Z/`:
- `ROUTE_AND_CONTROL_MATRIX.md`
- `RUN_CENTER_AUDIT.md`
- `VPS_AND_SCIENTIFIC_VALIDATION.md`
- `EIGHT_AGENT_INTEGRATION.md`
- `DATA_PROVENANCE_AND_FRESHNESS.md`
- `SECURITY_AND_ACCESSIBILITY.md`
- `TEST_RESULTS.md`
- `COMMIT_READINESS.md`
- `ISSUES_AND_REMEDIATION.md`
- `CHANGELOG.md`
- `RESUME_INSTRUCTIONS.md`
- `logs/`, `records/` (including `records/browser/drivers/`), `screenshots/`
