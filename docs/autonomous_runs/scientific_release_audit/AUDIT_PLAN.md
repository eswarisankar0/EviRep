# Audit plan and phase record

**Change-control rules followed throughout**
- No staging, commits, pushes, resets, stashes or cleans.
- Protected artefacts are never written. The adopted pointer (`adopted-20261015T015501Z-06`) is unchanged.
- Online access was read-only and small, through the project's own clients.
- All fault injection ran on isolated copies.

**Recovery snapshot:** `~/EviRep_recovery_sci_20261020T1608Z`. It contains HEAD, the index, the staged and unstaged diffs, a list and tarball of 428 changed or untracked files, and a 65 MB tarball of `data/` (excluding caches over 100 MB and run folders).

| Phase | What was done | Status |
|---|---|---|
| 1 Baseline and inventory | git state (HEAD `576bc7f`, 25 staged / 21 unstaged / 85 untracked entries, no stash), running processes, baseline tests (697 OK, 1 RuntimeWarning), protected inventory (`records/protected_inventory.json`: sha256, bytes, rows, schema for 19 files), recovery snapshot | DONE |
| 2 Specification | independent read-only trace of code and documentation with file:line citations (`evidence/specification_trace.md`); table in `MATHEMATICAL_AUDIT.md` and `GROUND_TRUTH_AUDIT.md`; 25 contradictions listed | DONE |
| 3 Ground truth | all 90 labels; live, fully paginated registry re-ascertainment using stage 03's own gates; alias searches for the 76 negatives (691 requests); role review of every label trial; prior human decisions cited (`GROUND_TRUTH_AUDIT.md`, `records/ground_truth_row_audit.csv`) | DONE |
| 4 Data lineage | cross-file keys, joins, ranges, raw-value equality, cutoff dates, fingerprints (`records/data_integrity_*`); identity uniqueness (DrugBank and ChEMBL) | DONE |
| 5 Independent mathematics | ranks, scores, AUROC, AP, bootstrap, paired difference, rank convention (`scripts/independent_math.py`, no production imports) | DONE |
| 6 Leakage and validity | data-flow trace (`evidence/leakage_trace.md`), verified samples, existing time-bounded sensitivities, label sensitivity (`records/label_sensitivity.json`) | DONE |
| 7 Defect correction | S-01, S-09, S-11, S-12, S-18 (partial) | DONE |
| 8 Pipeline reliability | A-1 to A-7, stage-08 timeout, staleness rule | DONE |
| 9 End-to-end validation | 723 tests (0 warnings), gates, browser suites, agent re-runs (isolated, then tracked) | DONE (see `TEST_EVIDENCE.md`) |
| 10 Candidate-result review | no new candidate result set was produced: no approved label, feature or score was changed. Label and rule alternatives are evaluated as **exploratory** sensitivities on the identical cohort; `td042_v1` was re-checked | DONE (exploratory only) |
| 11 Release gate | `RELEASE_CHECKLIST.md` | DONE |
