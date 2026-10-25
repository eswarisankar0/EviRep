# Commit readiness (final audit 2026-10-22)

**Verdict: READY. The change set is prepared and verified; execution needs owner authorisation, after the presentation.** Nothing was staged, committed or pushed.

## 1. What this audit changed
- **Code, tests and registers:** 21 files, delivered as one patch, `final_audit_20261022.patch` (375 insertions, 52 deletions).
- **Patch checks:**
  - `git apply --check` passes against the primary;
  - applying it to a copy of the primary reproduces the verified work copy exactly (`diff -r` clean);
  - full list: `records/changed_files_vs_primary.txt`.
- **Audit deliverables:** this folder.
- **Data:** none of the approved data (19 protected sha256 unchanged in both trees).

## 2. Why the audit's patch cannot be committed in isolation
The primary repository already holds large uncommitted, earlier-verified work:
- [AM] 10 · [MM] 5 · [ M] 6 · [A ] 10 · [??] 95;
- ui/, `scripts/run_stage.py`, seven agents and most tests are **untracked**;
- 15 staged files carry *older* versions than the working tree (`docs/autonomous_runs/ui_e2e_release_audit_20261021T0244Z/COMMIT_READINESS.md`).

Six of the 21 patched files are untracked. So a coherent commit must include the verified working tree. The full suite (771 tests) and the browser suites (138/138) were run on exactly that tree plus this patch.

## 3. Hygiene checks (executed)
| Check | Result |
|---|---|
| Credential patterns in all 902 commit-candidate files (incl. untracked) | 0 matches |
| `.env` | git-ignored, not a candidate |
| `.tmp` / `.orig` / `.rej` files | 0 |
| `git diff --check` (work copy) | clean |
| Protected / approved data | unchanged (sha256 19/19); `data/` is git-ignored |
| Generated artefacts | `docs/final_audit_20261022/experiments/candidates/` (7.0 MB, regenerable) **excluded**; `docs/autonomous_runs/` (46 MB, 513 files, logs, screenshots, data copies) **curated**: Markdown reports only |
| Merge conflicts | none (single branch `main`, 0 ahead / 0 behind `origin/main` from local refs; no fetch performed) |

## 4. Exact plan (run in the primary repository AFTER the presentation)
```bash
cd /Users/thrisha/Drup_Rep_PF/EviRep
# 0. Safety: a snapshot exists at ~/EviRep_recovery_finalmission_20261022T1504Z (sha256-verified). Make a fresh one if anything changed since.
# 1. Bring the audit deliverables and the code patch in
rsync -a --exclude experiments/candidates ~/EviRep_work_20261022T1504Z/docs/final_audit_20261022/ docs/final_audit_20261022/
git apply --check docs/final_audit_20261022/final_audit_20261022.patch && git apply docs/final_audit_20261022/final_audit_20261022.patch
# 2. Verify on the primary
./venv/bin/python -m unittest discover -s tests          # expect 771 OK
./venv/bin/python scripts/vps_verify.py                    # expect MATCH, 90 compounds
./venv/bin/python scripts/run_stage.py --check-manifest    # expect ok
#    then restart the UI server (the restart banner will ask for it): stop it, then ./venv/bin/python ui/server.py
# 3. Commits, staging EXPLICIT paths only (never `git add -A`); `git add` refreshes the 15 stale staged versions
git add scripts/ requirements.txt .env.example
git commit -m "Pipeline: agents, run tracker, verifier and final-audit fixes

Adds the eight diagnostic agents, scripts/run_stage.py and the result-set tools.
Final audit 2026-10-22: class-phrase guard in intervention matching (E-064),
vps_verify follows stage 06 for feature exclusions and absent molecular rows
(E-065), highest listed trial phase (E-066), N_RANDOM 1000 (TD-011), main
guards and data/ creation (TD-012/013), exit 1 on FAILED for 10d/10e/10h/10a
(E-067). Approved scores unchanged (vps_verify MATCH)."
git add ui/
git commit -m "UI: research dashboard, Run Center and launch policy; timeouts for every stage (E-067)"
git add tests/
git commit -m "Tests: 771 unit/integration tests incl. final-audit regressions"
git add README.md TECHNICAL_DEBT.md development_log/ docs/*.md
git commit -m "Docs: methods, registers and decision log (C-125, E-064..E-067)"
git add docs/final_audit_20261022/*.md docs/final_audit_20261022/*.csv docs/final_audit_20261022/PROVENANCE_MANIFEST.json \
        docs/final_audit_20261022/experiments/*.py docs/final_audit_20261022/experiments/*.json \
        docs/final_audit_20261022/records docs/final_audit_20261022/logs \
        docs/final_release_20261022/*.md docs/presentation_20261022/*.md
git commit -m "Audit reports: final research and commit-readiness audit 2026-10-22"
# optional, owner's choice: curated earlier audit reports only
#   git add $(git ls-files --others --exclude-standard docs/autonomous_runs | grep '\.md$')
git status --short    # review what remains untracked
# 4. Do NOT push until reviewed.
```
**Notes on the commits:**
- The commit messages carry no AI attribution lines. Add the project's convention if it has one.
- Pushing, and any change to approved data, are separate owner decisions (`FINAL_RELEASE_DECISION.md`).

## 5. Rollback
- **Before commit:** `git apply -R docs/final_audit_20261022/final_audit_20261022.patch`.
- **After commit:** `git revert <sha>` per commit.
- **Full recovery** (index, working-tree tarballs and diffs): `~/EviRep_recovery_finalmission_20261022T1504Z/` (`SHA256SUMS`).
