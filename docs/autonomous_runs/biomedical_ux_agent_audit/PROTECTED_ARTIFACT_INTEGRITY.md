# Protected artefact and Git integrity

**Recovery snapshot taken before any edit:** `~/EviRep_recovery_bux_20261020T1535Z`.

It holds:
- HEAD, the index file and staged diff;
- the worktree diff and untracked list;
- a tarball of all 331 changed or untracked files;
- protected sha256 hashes.

**Protected artefacts.**
- `shasum -a 256 -c logs/hashes_before.txt` gives **19 / 19 OK** (`logs/hashes_after_check.txt`).
- This covers:
  - frozen ground truth and labels;
  - the candidate pools;
  - every score dimension;
  - `vps_scores_v2.csv` and `vps_evaluation_report.json`;
  - trial-role files;
  - the ClinicalTrials.gov cache.
- `scripts/vps_verify.py`: MATCH.

**Git.**
- HEAD `576bc7f` (6 commits) is unchanged. Stashes: 0.
- **`.git/index` is byte-identical** to the snapshot. The staged diff md5 `d04e97371800f54cc28abbb6a383742b` is unchanged.
- Unstaged files: 21, **the same list** as the snapshot.
- Untracked files: 300 → 354. The additions are only:
  - this report folder (reports, logs, screenshots, evidence);
  - `tests/test_agent_failure_modes.py`;
  - `tests/test_biomedical_ux.py`.

  No file was removed.
- Nothing was staged, committed, pushed, reset, cleaned, stashed or checked out.

**Edited in place (already untracked or user-modified before this pass):**
- `ui/server.py`, `ui/app.js`, `ui/style.css`, `ui/index.html`;
- `tests/test_live_app.py`, `tests/test_ui.py`, `tests/test_ui_quality.py`;
- `development_log/CHANGES.md` and `development_log/ERRORS_AND_BLOCKERS.md` (appended).

**No agent or pipeline script was modified.** All defects found in pipeline code are documented, not patched.

**Scientific outputs.** No approved output, label, score, evaluation report or adjudication file was modified:
- `td042_v1` was not adopted;
- TD-042, TD-033 and B-003 were not decided;
- the 28 trial links remain unresolved.

**Where runs and requests went.**
- All destructive, fault-injection, timeout and launch tests ran on scratchpad copies (`uxcopy`, `livecopy`, `uicopy8`, `gatecopy4`, temp dirs) served on port 8799.
- The online checks wrote only to the scratchpad.
- The live server on 8765 was restarted once, with the final code. It was this session's own process and is still bound to 127.0.0.1.
