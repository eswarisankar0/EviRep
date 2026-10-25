# Remaining blockers and owner actions

The UI is improved and verified, but the application is **not** "fully ready": the open scientific decisions below are the owner's, and the UI only displays them.

## Owner-only scientific decisions (unchanged, shown on the Dashboard)
- **TD-042.** Corrected molecular rule. The candidate output `td042_v1` was verified independently but **not adopted**. It is shown as pending only.
- **TD-033.** Temporal validity of the literature, safety and molecular features (current snapshots, not leakage-free).
- **B-003.** Evaluation reproducibility discrepancy (open).
- **Trial-role review.** 28 trial links await human adjudication (9 adjudicated). The UI is read-only; decisions are recorded by a person in `data/feature_trial_roles_td038.csv`.
- **Label re-freeze policy.**

## Freshness items that need an owner decision
- **Untracked inputs.** Some stages (e.g. `eval`, which reads `data/reproducibility.json`) were last run before those inputs were fingerprinted. Their freshness cannot be fully verified. Re-running them rewrites approved files, so the Dashboard says this and leaves the choice to the owner.
- **Missing retrieval dates.** openFDA, Open Targets and Hetionet have no recorded retrieval time in any artefact. The UI shows "not recorded". Recording these needs a pipeline change, not a UI change.

## Technical limitations (documented, not defects)
- No stage reports a trustworthy percentage, so the UI shows elapsed time and the latest log line only.
- Cancellation is not offered: it would skip the runner's restore step.
- Network stages and long production timeouts were not exercised in this pass.
- The server is loopback-only. Any other deployment needs a separately authorized plan.

## Owner actions
1. Review the new wording and charts (launch command below) and confirm the readable labels are acceptable.
2. Decide on TD-042 / TD-033 / B-003 and the 28 trial-role links. The UI will reflect the decisions from the artefacts.
3. Decide whether to re-run the stages with untracked inputs; this rewrites approved files.
4. Review and stage the changes yourself. Nothing was staged or committed.

**Launch:** `./venv/bin/python ui/server.py`, then open http://127.0.0.1:8765/
