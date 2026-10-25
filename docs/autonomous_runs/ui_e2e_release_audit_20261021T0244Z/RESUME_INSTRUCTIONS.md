# Resume instructions

**Current state:**
- `main` at `576bc7f`, 0 ahead / 0 behind.
- The index is byte-identical to the audit baseline (backup: `~/EviRep_recovery_e2e_20261021T0244Z/git_index.bin`).
- The live server runs on the final code at http://127.0.0.1:8765/.

## Verify everything again (about 3 min, offline)
```
cd /Users/thrisha/Drup_Rep_PF/EviRep
./venv/bin/python -W default -m unittest discover -s tests        # expect 751 OK, 0 warnings
./venv/bin/python scripts/run_stage.py --check-manifest           # ok: true
./venv/bin/python scripts/vps_verify.py                           # MATCH, 90 compounds
shasum -a 256 -c docs/autonomous_runs/ui_e2e_release_audit_20261021T0244Z/logs/protected_sha256_baseline.txt   # 19 OK
git diff --check && node --check ui/app.js
curl -s http://127.0.0.1:8765/api/status | python3 -c "import json,sys;print(json.load(sys.stdin)['server_code_changed'])"   # False
```
If the last command prints `True`, restart the server: stop the `ui/server.py` process on 8765, then run `./venv/bin/python ui/server.py`.

## Owner decisions, in suggested order (none executed)
1. **Commit scope** (`COMMIT_READINESS.md`): stage explicit paths only, never `git add -A`; export the index with `git checkout-index` and run the full suite on it before committing.
2. **TD-042:** adopt or reject `td042_v1`. If adopting, run `data/_candidates/td042_v1/publish_td042.sh`, then `scripts/run_stage.py eval`.
3. **Stage-03 rebuild (E-056)** in an isolated copy (Dopamine joins the cohort), compare with `scripts/compare_result_sets.py`, then decide.
4. **`eval` fingerprint:** `./venv/bin/python scripts/run_stage.py eval`.
5. **Lithium (B-004), Galantamine/Rifaximin, the 28 trial-role links** (human review queue in the UI: Evidence → Trial-role review).

## Re-running the browser suites
The suites need Chrome with `--remote-debugging-port=9333`. They live in the session scratchpad (`scratchpad/run_suites.sh`, `scratchpad/cdp/drive*.py`); scratchpad files may not persist after the session ends.
Each suite runs against a fresh rsync copy on port 8799. The scripts never stop the live server, because they kill only `ui/server.py --` processes.
