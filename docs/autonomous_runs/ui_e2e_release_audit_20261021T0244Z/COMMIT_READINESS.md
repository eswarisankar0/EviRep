# Commit-readiness gate (audit 2026-10-21)

**Nothing was staged, committed or pushed.**
The git index is **byte-identical** to the baseline copy taken at the start (`cmp .git/index ~/EviRep_recovery_e2e_20261021T0244Z/git_index.bin`, `logs/gates_final.log`).

## Baseline vs now

| Item | Baseline (`logs/git_baseline.txt`) | Final |
|---|---|---|
| Branch / HEAD | `main` / `576bc7f` | `main` / `576bc7f` |
| Ahead / behind `origin/main` | 0 / 0 | 0 / 0 (from local refs; no fetch was run) |
| Staged diff md5 | `d04e9737…b742b` | `d04e9737…b742b` (unchanged) |
| Staged entries | 25 (20 A, 5 M; 7,622 insertions, 153 deletions) | 25 |
| Staged entries with later working-tree edits (AM/MM) | 15 | 15 |

This audit's own edits are all in the working tree, none in the index:
- `scripts/run_stage.py`
- `ui/app.js`
- `tests/test_stage_registry_integrity.py` (new, untracked)
- `tests/test_agent_failure_modes.py`
- `tests/test_ui_quality.py`
- this report folder

## What a commit of the current index would contain
The staged tree was exported with `git checkout-index -a --prefix=<tmp>/`, which leaves the index unchanged: 34 files (`records/staged_tree_files.txt`).
- **The staged tree is internally consistent.** The 4 staged test modules (`test_candidate_flow`, `test_intervention_matcher`, `test_molecular_agent`, `test_vps_integration`) pass on the exported tree alone: **160 tests OK** (`logs/tests_staged_tree.log`).
- **No credentials:**
  - 0 matches in the staged diff, in tracked files and across all history (`logs/credential_scan.txt`);
  - `.env` is git-ignored and untracked;
  - `.env.example` contains names only.
- **Whitespace:** `git diff --cached --check` is clean.

## Why the staged set does not represent the verified system
1. **It lacks the application.** No file under `ui/` is staged. Also unstaged: `scripts/run_stage.py`, seven of the eight agent scripts (only `molecular_agent.py` is indexed) and most of the test suite (591 of the 751 tests live in untracked files; 160 are in indexed ones). A commit of the index alone would not contain the dashboard, the run tracker or the tests this audit verified.
2. **Staged versions are older.** 15 staged files have since changed in the working tree:
   - 7 documents: README, TECHNICAL_DEBT, CHANGES, ERRORS_AND_BLOCKERS, CASE_STUDIES, MOLECULAR_AGENT, REFERENCES;
   - 8 scripts: 02, 03, 04, 06, 07, 08, `check_intervention_match`, `molecular_agent`.
   Committing the index would record the older versions. For example, the staged `scripts/03_clinicaltrials_groundtruth.py` predates the pagination fix (E-056). `nextPageToken` appears 0 times in the staged blob and once in the working tree.
3. **Unstaged modifications.** 6 tracked files have unstaged edits only (`00`, `01`, `05`, `check_studytype`, `debug_step2`, `filter_by_studytype`).

## Verdict: **CONDITIONALLY READY. Not recommended as-is.**
The current index can be committed without breaking its own tests, and it exposes no secrets. However, it is an older, partial snapshot of the verified system.

**Recommendation for the owner** (not executed; needs explicit authorisation):
1. Decide the commit scope. Recommended: the full verified working tree, minus `data/` artefacts governed by the protected-file policy, `venv/` and scratch outputs.
2. Stage by explicit path lists, never `git add -A`. Review `git diff --cached --stat`.
3. Re-run the gate on the exact staged contents:
   ```
   git checkout-index -a --prefix=/tmp/evirep_stage/
   cd /tmp/evirep_stage && <venv>/bin/python -m unittest discover -s tests
   ```
4. Commit only after the full suite (751) passes on the exported index.
