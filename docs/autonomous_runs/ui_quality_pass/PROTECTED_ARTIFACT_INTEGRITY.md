# Protected artefact and Git integrity

**Protected files.** `shasum -a 256 -c logs/hashes_before.txt` gives **all OK**. The 20-line list covers the 19 protected artefacts and their checksums, as taken before the pass. Output: `logs/hashes_after_check.txt`. This includes:
- frozen ground truth and labels;
- `vps_scores_v2.csv` and `vps_evaluation_report.json`;
- the candidate pools and score dimensions;
- trial-role files and the ClinicalTrials.gov cache.

**Score verification.**
- `scripts/vps_verify.py` reports `MATCH`: 90 compounds, max |diff| 2.22e-16 (`logs/vps_verify.txt`).
- The ground-truth contract test passes.

**Run tracker.** `scripts/run_stage.py --check-manifest` exits 0, and `--status` exits 0 (`logs/check_manifest.txt`, `logs/status_after.txt`).

**Git, compared with `~/EviRep_recovery_uiq_20261020T1153Z`:**
- HEAD `576bc7f`, 6 commits: unchanged.
- Staged files: 25. Staged diff md5 `d04e97371800f54cc28abbb6a383742b` is identical to the baseline.
- Unstaged files: 21, the same list.
- Stashes: 0.
- Untracked files: 254 → 264. The only additions are `tests/test_ui_quality.py` and files under `docs/autonomous_runs/ui_quality_pass/`.
- `ui/` was already untracked; its files were edited in place.
- Nothing was staged, committed, pushed, reset, cleaned, stashed or deleted.

**Not adopted, not decided:**
- `td042_v1` stays a pending candidate. It is shown by its readable name with the exact id beside it, and is never displayed as a score.
- TD-042, TD-033 and B-003 are shown as open owner decisions.
- The 28 trial links stay unresolved. The review queue is read-only.

**Verification runs.** All destructive and timeout scenarios ran only on isolated scratchpad copies served on port 8799. These covered the hang, corrupt manifest, corrupt input and server kill.
