# EviRep 4-hour hardening sprint: industry-readiness report (2026-10-20)

## 1. Executive summary
**Verdict: DEVELOPMENT READY**, unchanged. The engineering base is stronger, but authentication, HTTPS, monitoring, scheduled backups and a vulnerability scan are still missing, and the scientific owner decisions are still open.

**Defects:** 7 found and fixed (E-037–E-041, plus code-drift visibility and a readiness probe). Each has regression tests, and every runner/UI defect test was shown to fail on the pre-sprint code.

**Most important finding:** stages read and wrote files the run tracker did not know about (E-037). As a result:
- human TD-038 role decisions and 10e's output could change without any consumer becoming STALE;
- three of 10a's outputs were never fingerprinted, validated or backed up.

**Also fixed:**
- a corrupt manifest crashed the dashboard API (E-038);
- an 89 MB output could not be restored after a failed run (E-039);
- the status pill could claim "current" for unknown states (E-040);
- concurrent polls (E-041).

**Added:**
- a verified backup tool, with one verified backup made;
- `/api/health`;
- `--check-manifest`;
- 0 ResourceWarnings (from 126).

**Tests:** 604 → **628, all passing**. Offline end-to-end run passes. Browser checks 20/20 + 8/8. Write containment 10/10 agents.

## 2. Starting repository state
- branch `main` = `origin/main`; HEAD `576bc7f`; 6 commits; no tags or stashes;
- 25 staged, 21 unstaged and 118 untracked paths (97 at the previous audit's start; the difference is files added by the last two sessions);
- index-diff md5 `d04e97371800f54cc28abbb6a383742b`;
- approved VPS sha256 `718f2a7c…`;
- protected files 19/19.

**Baseline (07:46:48–07:47:38Z):**
- `unittest discover` 604 OK, exit 0;
- `run_stage.py --status`, `vps_verify.py`, the TD-042 verifier and `git diff --check` all exit 0;
- 126 ResourceWarning lines.

## 3. Recovery snapshot
`~/EviRep_recovery_4h_20261020T0746Z/` holds:
- `HEAD.txt`, `git_log.txt`, `branches.txt`, `tags.txt`, `stashes.txt`, `git_status.txt`, `counts.txt`;
- `index.diff` (staged) and `worktree.diff` (unstaged), stored separately;
- `git_index.bin` plus its sha256;
- `untracked.txt`, `protected_sha256.txt`, `protected_check.txt` (19/19);
- the VPS and manifest sha256 and a manifest copy;
- `worktree_snapshot.tgz` (433 entries, listing verified).

Additionally, a data backup: `~/EviRep_backups/evirep_data_20261020T075410Z.tar.gz` (+ `.sha256.json`), member-verified.

## 4. Active execution time
**2026-10-20T07:46:36Z → about 08:12Z: roughly 26 minutes** of continuous work. This is not four hours. The sprint ended when the identified defects were fixed and verified, and the remaining items are owner or deployment decisions (§20–21). Checkpoints: `CHECKPOINT_4H_20261020T0746Z.md`.

## 5. Architecture and dependencies
See `END_TO_END_ARCHITECTURE_AUDIT.md`. This sprint changed the registry:
- **06:** + `data/feature_role_exclusions.csv` (optional input).
- **07:** + `data/vps_scores_v2.csv`.
- **eval:** + `data/reproducibility.json`, and a dependency on 10e.
- **10a:** declares all four `--curated` outputs (donepezil, domperidone, melatonin, propranolol).
- **10f:** + `data/_safety_failures.jsonl`.
- **10g:** + `data/cache/pubmed_efetch_{droxidopa,case_claims}.xml`.
- **10h:** + `clinical_maturity_precutoff_clean.csv`, `feature_trial_roles_td038.csv`, both failure logs, five `literature_credibility_*.json` files; plus a dependency on 10a.

**Publication mode per stage:**
- 06 is staged (`--output-dir`, then validation and independent `vps_verify`, then `os.replace`).
- Every other stage writes in place, behind a pre-run backup of each output (≤ 512 MB) that is restored on failure.
- A run whose outputs cannot be backed up is refused.

## 6. Eight-agent status
All eight envelopes are valid. Every agent is SUCCESS with fresh tracked state. Each agent run via the runner in an isolated copy wrote only its declared outputs (10/10, including 10a-all and review).

| Agent | Coverage | Re-run this sprint | VPS role |
|---|---|---|---|
| 10a | 4 case files + 89/90 all-mode | yes (outputs had predated C-80's `temporal_source` field) | diagnostic |
| 10b | 90 records, 74 with targets | yes, identical | via stage 08 |
| 10c | 90 compounds, 177 trials, 0 failures | yes, identical | via stage 03; 28 links await human review (untouched) |
| 10d | 19/91 assessed | yes, identical | diagnostic |
| 10e | 14 findings, 4 compounds | yes, identical | diagnostic |
| 10f | label 83/7/0 failed; at cutoff 31/52 unknown | no (fresh) | via stage 05 |
| 10g | D2 89/90 assessable | yes, identical | via stage 04 |
| 10h | 90 × 12 domains | yes, identical | annotation |

"Identical" means equal excluding timestamps and input-hash maps.

## 7–10. Defects, root causes, fixes, tests
| ID | Severity | Root cause | Fix | Regression test | Verification | Status |
|---|---|---|---|---|---|---|
| E-037a | MEDIUM | Registry omitted files that stages read (incl. human TD-038 roles and 10e output), so changes never made consumers STALE | declared inputs + `eval → 10e`, `10h → 10a` | `test_every_data_file_a_stage_script_names_is_declared`, `test_10h_declares_every_credibility_file_it_globs` | fails on snapshot code; passes | PASS |
| E-037b | MEDIUM | 10a wrote 4 files, declared 1: 3 outputs never fingerprinted, validated or backed up | 10a declares all four | write-containment run (isolated copy); `test_every_output_has_exactly_one_producing_stage` | 10/10 agents contained | PASS |
| E-037c | MEDIUM | `_changed` compared only files recorded at the last success, so newly declared inputs and outputs were never checked | warnings for declared-but-unrecorded files; a re-run records them | `test_input_declared_after_last_success…`, `test_output_declared_after_last_success…` | fails on snapshot code | PASS |
| E-038 | MEDIUM | `json.load` errors propagated: `/api/status` 500, CLI traceback | `ManifestError`; UNKNOWN status; refusal without overwrite; `--check-manifest`; fsync before rename; `manifest_error` in the API | `TestCorruptManifest` (4), `TestCorruptManifestInUI` (2) | 6/6 fail on snapshot code; browser corrupt → "Run records unreadable" → recovers on restore | PASS |
| E-039 | MEDIUM (latent) | 50 MB backup limit < stage 01's 89 MB output; failure could not restore it | limit 512 MB; unrestorable runs refused (exit 4) | `TestBackupLimit` (3) | 2/3 fail on snapshot code | PASS |
| E-040 | MEDIUM | Pill counted only failed, stale and running stages | unknown/untracked/not-run counted; manifest error shown; VPS UNKNOWN banner | `TestCorruptManifestInUI.test_pill_logic…` + browser | browser 8/8 | PASS |
| E-041 | LOW | `visibilitychange` called `poll()` while one was in flight | single-flight guard with coalesced follow-up | `TestPollingSingleFlight` + browser Fetch-hold | browser: 1 request held, 1 follow-up | PASS (not reproduced in a browser on old code) |
| F-07 | LOW | 16 last successes had no code fingerprint, so code drift was invisible (it hid the stale 10a outputs) | `code_fingerprint_recorded` + run-table note; 5 offline agents re-run | `test_code_fingerprint_recorded_flag` | 12 ADOPTED + eval remain (protected; TD-046) | PARTIAL |
| W-01 | LOW | unclosed files in `clinical_role_review.py` and 9 test files | `with` / `pathlib` | full suite | 126 → 0 warnings; `review` re-run byte-identical | PASS |

**New capabilities:**
- `/api/health` (`TestHealth`, 2 tests);
- `scripts/backup_data.py` (`test_backup_data.py`, 6 tests);
- `run_stage.py --check-manifest`.

**My own test gap, caught by the suite:** declaring 10a's outputs broke the existing `TestRegistryMatchesCode`. Fixed by extending its `DERIVED_PATHS` mechanism with exact alternative needles; no assertion was removed.

**Files changed this sprint:**
- runner and UI: `scripts/run_stage.py`, `ui/server.py`, `ui/app.js`;
- scripts: `scripts/clinical_role_review.py`, new `scripts/backup_data.py`;
- tests: `tests/test_run_tracking.py`, `tests/test_ui.py`, new `tests/test_backup_data.py`, and pathlib-only edits in `test_{evidence_independence,vps_correctness,safety_evidence,clinical_evidence,literature_credibility,literature_date_bound,reproducibility,conflict_context}_agent/…`;
- logs (appended): `development_log/CHANGES.md` (C-102–C-110), `ERRORS_AND_BLOCKERS.md` (E-037–E-041), `TECHNICAL_DEBT.md` (TD-044 update, TD-045 resolved, TD-046, TD-047);
- docs: `docs/autonomous_runs/` (this report, the 4H checklist, the 4H checkpoint, evidence, logs).

**Regenerated through the tracked runner:**
- 10a, 10b, 10c, 10d, 10e, 10g, 10h, 07 and review outputs, plus `run_manifest.json`;
- no protected file was rewritten.

## 11. Tests run
| Command | Start–end (UTC) | Exit | Result | Log | Class |
|---|---|---|---|---|---|
| `./venv/bin/python -m unittest discover -s tests` (baseline) | 07:46:48–07:47:38 | 0 | 604 OK | `logs/4h_baseline_tests.log` | offline |
| same (mid) | ≈07:52 | 0 | 612 OK, 0 warnings | `logs/4h_mid_tests.log` | offline |
| same (first final) | 08:03:26–08:04:19 | **1** | 628 run, **1 failure** (`TestRegistryMatchesCode`, see above) | overwritten by the rerun; recorded here | offline |
| same (final) | 08:05:14–08:06:07 | 0 | **628 OK, 0 skipped, 0 ResourceWarnings** | `logs/4h_final_tests.log` | offline |
| `./venv/bin/python scripts/run_stage.py --status` | 08:08:22 | 0 | 13 SUCCESS + 12 ADOPTED | `logs/4h_final_status.log` | offline |
| `./venv/bin/python scripts/run_stage.py --check-manifest` | 08:08 | 0 | ok, no problems | `logs/4h_final_check_manifest.log` | offline |
| `./venv/bin/python scripts/vps_verify.py` | 08:08 | 0 | MATCH, max abs diff 2.22e-16 | `logs/4h_final_vps_verify.log` | offline |
| `./venv/bin/python scripts/vps_verify.py --root data/_candidates/td042_v1/root` | 08:08 | 0 | MATCH (not published) | `logs/4h_final_vps_verify_candidate.log` | offline |
| `./venv/bin/python data/_candidates/td042_v1/verify_td042_candidate.py` | 08:08 | 0 | verified | `logs/4h_final_td042.log` | offline |
| `git diff --check` | 08:08 | 0 | clean | `logs/4h_final_summary.log` | — |
| offline end-to-end run (`data/_runs/continuation_20261019/e2e_offline.py`, isolated copy, proxy-blocked) | 08:03:26–08:04:39 | 0 | 20 SUCCESS; 01, 03, 03c, 04b and diag BLOCKED (live-only, by design); 25 fresh; vps_verify MATCH | `data/_runs/e2e_4h_final_20261020/` | offline |
| (an earlier end-to-end run overlapped a runner edit and was set aside as superseded) | 07:57–07:59 | 0 | not counted | `data/_runs/e2e_4h_20261020_superseded_mixed_code/` | — |
| agent write containment (each offline agent via the runner, isolated copy) | ≈08:02 | — | 10/10 (first pass 9/10 → E-037b) | `evidence/agent_write_containment_4h.json` | offline |
| live smoke | 07:57:49 | — | PubMed, CT.gov, openFDA, DailyMed, Zenodo, Open Targets (26.09): 200 | `logs/4h_live_smoke.log` | **live** |
| backup + verify | 07:54 | 0 | 1,389 files, verified | `logs/4h_backup.log` | local |
| browser (Chrome via CDP, real backend) | 08:06–08:08 | — | 20/20 general + 8/8 polling/manifest | `evidence/ui_browser_checks_4h_*.json` | local |

**Not run:**
- full live stages 01/03/03c/04/05 (costly, rate-limited, or able to change labels);
- Semantic Scholar (known 429; not retried);
- pip-audit (not installed).

## 12. Offline versus live
- **Live this sprint:** the smoke requests only.
- **Earlier live checks:** stages 01/00/03/03c/diag (isolated copy, 2026-10-19) and the 10c refetch (identical, 07:23Z today).
- **Everything else:** offline, on persisted inputs and caches.

## 13. Browser / UI
**20/20 general checks:**
- all views at 1440 px, 6 views at 390 px with no horizontal overflow;
- the agent panel shows tracked freshness and VPS role;
- every table's headers align with its cells;
- review queue shows 28;
- keyboard focus is visible;
- no failed requests, JS exceptions or console errors;
- no stage started by viewing.

**8/8 targeted checks:**
- single-flight polling;
- corrupt manifest → "Run records unreadable" and an UNKNOWN banner, recovering without a reload;
- the eval warning is visible;
- no JS exceptions.

**Read-only surface kept:** no launch endpoint was added.

## 14. Security audit
| Area | Status |
|---|---|
| Exposure | loopback bind, Host check, GET-only, CSP and frame/sniff/referrer headers — re-verified in the earlier audit; unchanged |
| Inputs | `/api/log` and `/api/doc` validation unchanged; new `/api/health` takes no input and reveals no paths |
| Deserialization / shell | no pickle, yaml, eval, exec or `shell=True`; subprocess with argument lists |
| XML | ElementTree does not resolve external entities; expat 2.7.3 |
| Secrets | TD-029 kept (the server never reads the environment) |
| Dependencies | `pip check` clean; installed = pins; **vulnerability scan BLOCKED** (pip-audit not installed; not added without approval) |

## 15. Resource warnings
126 → 0:
- **production:** `clinical_role_review.py`, plus the earlier 05h/10g/10h fixes;
- **tests:** pathlib read/write in 9 files.

04p/05h `requests.Session` is left process-lifetime (TD-047, accepted).

## 16–17. Scientific findings; approved vs candidate
`scripts/vps_architecture_comparison.py` reproduces the previous results byte-for-byte (`data/_runs/vps_architecture_4h_20261020/`). Population: 90 compounds, 14 positives / 76 negatives.

| Model | AUROC |
|---|---|
| A, approved | 0.775 |
| 4D | 0.700 |
| dated molecular | 0.704 |
| TD-042 (dated) | 0.703 |

Unchanged this sprint:
- the approved formula, weights, pool, labels, cutoff, missing-value policy and rank convention;
- TD-042 verified but **not published**;
- no weights fitted;
- no agent added as a dimension;
- no clinical decision made.

## 18. Integrity (compared with the snapshot at 08:08Z)
- HEAD `576bc7f` = start; `git log` identical (6 commits); branches, tags and stashes identical.
- `.git/index` **byte-identical**; the staged diff is byte-identical (md5 `d04e9737…`). Nothing staged, committed or pushed.
- Unstaged tracked paths: the **same 21**. This sprint's edits to tracked files were appends to `CHANGES.md`, `ERRORS_AND_BLOCKERS.md` and `TECHNICAL_DEBT.md`; the UI and runner files are untracked.
- Protected files 19/19 sha256 OK; approved `vps_scores_v2.csv` sha256 unchanged.

## 19. Remaining risks
| Risk | Severity | Mitigation / owner | Status |
|---|---|---|---|
| Temporal validity of the 5D headline (0.775 vs 0.704 dated) | High | owner molecular-policy decision | open |
| Label drift on 03/03c re-runs | High | isolated-copy re-runs only; re-freeze decision | controlled |
| 28 unadjudicated clinical links | Medium | human reviewer | open |
| No code fingerprints for 12 ADOPTED stages + eval | Low | owner-approved re-runs | open (TD-046) |
| eval's untracked input `reproducibility.json` | Low | re-run eval (rewrites a protected file) | owner |
| No authentication/HTTPS, monitoring or scheduled backup | High if shared | deployment work | open (TD-044) |
| Unscanned dependency CVEs | Medium | pip-audit with approval | blocked |

## 20. Deployment blockers
- authentication and HTTPS;
- structured logs and monitoring;
- scheduled backups (the tool exists; a scheduler must be chosen);
- a dependency vulnerability scan;
- retention enforcement (a proposal exists).

## 21. Next actions, in priority order
1. **Owner:**
   - molecular dimension policy (TD-042 / drop / keep with caveats);
   - bounded literature/safety adoption;
   - label re-freeze;
   - approve re-running `eval` (records its input fingerprint) and, optionally, the ADOPTED stages, to gain code-drift detection.
2. **Human:** adjudicate the 28 links (`#review`).
3. **Approval to install:** `./venv/bin/pip install pip-audit && ./venv/bin/pip-audit -r requirements.txt`.
4. **Ops:** schedule `./venv/bin/python scripts/backup_data.py --dest ~/EviRep_backups` (launchd/cron) after each stage-06 publication; adopt the retention proposal (`--retention-report`).
5. **External:** a Semantic Scholar API key for a live stage 04 (isolated copy first).
6. **Deployment, only if it will be shared:** authentication, an HTTPS reverse proxy, structured logging and monitoring.

## 22. Reproducing the verification
```
./venv/bin/python -m unittest discover -s tests
./venv/bin/python scripts/run_stage.py --status
./venv/bin/python scripts/run_stage.py --check-manifest
./venv/bin/python scripts/vps_verify.py
./venv/bin/python scripts/vps_verify.py --root data/_candidates/td042_v1/root
./venv/bin/python data/_candidates/td042_v1/verify_td042_candidate.py
./venv/bin/python scripts/vps_architecture_comparison.py --out <new dir>
./venv/bin/python data/_runs/continuation_20261019/e2e_offline.py <empty scratch dir> <out.json>
./venv/bin/python scripts/backup_data.py --dry-run   # or --dest <dir outside the repo>, then --verify <archive>
git diff --check
curl -s http://127.0.0.1:8765/api/health
```
Browser drivers: `docs/autonomous_runs/evidence/drive{,7,8}.py`. They need Chrome with remote debugging on port 9333 and an isolated copy served on port 8799. Write containment: `docs/autonomous_runs/evidence/write_containment.py <isolated copy> <out.json>`.
