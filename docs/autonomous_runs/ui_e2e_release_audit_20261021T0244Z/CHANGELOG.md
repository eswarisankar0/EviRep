# Changelog (audit 2026-10-21)

All changes are in the working tree; **none is staged**. No approved data, label, cohort, score, cutoff or report changed: protected hashes are 19/19.

| File | Change | Reason |
|---|---|---|
| `scripts/run_stage.py` | `status()` warns when a dependency's latest attempt failed | A-5 |
| `ui/app.js` | the Run Center stage table shows each stage's `warnings`; the state chart keeps its data table (`noTable` removed); the stage-name cell wraps (only the ID is `nowrap`) | A-5, A11Y-1, UI-1 |
| `ui/style.css` | `.nowrap` usable on inline elements | UI-1 |
| `tests/test_stage_registry_integrity.py` | **new**, 8 tests: DAG integrity, launch policy, registry-only commands | REG-1 |
| `tests/test_agent_failure_modes.py` | +1 test: failed-dependency warning appears and clears | A-5 |
| `tests/test_ui_quality.py` | +1 test: no chart opts out of its data table | A11Y-1 |
| `development_log/CHANGES.md`, `development_log/ERRORS_AND_BLOCKERS.md` | C-123; E-060 | log |
| `docs/autonomous_runs/ui_e2e_release_audit_20261021T0244Z/` | this report set, logs, records, screenshots | deliverables |

**Operational:** the live server (this session's own process) was restarted on the final code.

**Outside the repository:** browser drivers `drive18.py`, `drive18b.py`, `drive19.py` and `shots20.py` were written in the session scratchpad. Copies of their results are in `records/browser/`.

**Rollback:** revert the five code and test files listed above to drop the changes. They are independent of the approved data.
