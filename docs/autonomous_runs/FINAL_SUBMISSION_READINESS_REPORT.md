# EviRep final submission-readiness report (2026-10-20)

**Window:** 08:40:46Z → about 09:16Z, roughly 35 minutes of active work.

**Machine-readable summary:** [`final_verification_summary.json`](final_verification_summary.json).

**Readiness:**

| Dimension | Verdict | Why |
|---|---|---|
| Research submission | **NOT YET** | The code and evaluation are reproducible and verified, but owner decisions remain open (molecular dimension, bounded dimensions, label re-freeze), submission documents carry superseded metrics (TD-048), and no manuscript exists in the repository |
| Application | **DEVELOPMENT READY** | Local, single-user, real-time; not for shared deployment (no authentication, HTTPS or monitoring) |

## 1. What changed in code
| Area | Change |
|---|---|
| Live pipeline (new) | **`ui/live_runs.py`:** launch policy plus detached launches of `scripts/run_stage.py`; launch records in `data/_runs/_ui_launches/`.<br>**`ui/server.py`:** `GET /api/session` (per-server nonce + policy), `GET /api/launches`, and `POST /api/run`, guarded by loopback Host, same-origin `Origin`, the nonce header, JSON content type and a 1 KB body limit. Every other POST stays 405.<br>**`ui/app.js` + `index.html`:** the "Live pipeline" view, with Run, Run… (confirm) and Run-all controls, a launches panel and fast polling while active. |
| Runner | `--sequence` (dependency order, fresh stages skipped, dependants of a failure BLOCKED); `last_activity` (latest log line and its age) for RUNNING stages; `attest` / `--attest-from` (code fingerprint only after a byte-identical isolated reproduction) |
| UI robustness (found by the browser run) | **E-042:** stale nonce after a server restart is now renewed and retried once.<br>**E-043:** an identical background re-render leaves the DOM alone, so clicks aren't swallowed. |
| Tests (new) | `test_ground_truth_contract.py` (9, independent stdlib implementation + frozen label fixture); `test_live_runs.py` (8, including a **real** runner launch); runner (+6); UI (+3) |
| Provenance | 00, 04, 05 and 08 now carry attested code fingerprints. The live manifest was backed up first, to `run_manifest_before_attest.json` in the snapshot. |
| Docs | `SCIENTIFIC_CONTRACT_TRACEABILITY.md`, `RUNS_AND_LIVE_UI.md` (appended), `evidence/agent_validation_matrix.json`; logs C-111–C-115, E-042, E-043, B-003, TD-046 update, TD-048 |

## 2. What works in the actual UI
Existing views are preserved: Overview, Candidates, Evidence, Mechanism, Conflicts, Review queue, Compare, Validation & Methods, Technical details. **Live pipeline is new.**

Browser evidence (Chrome via CDP against the real server; `docs/autonomous_runs/evidence/`):
- **General, 21/21:**
  - every view at 1440 px, plus 7 views at 390 px (including Live pipeline) with no horizontal overflow;
  - table headers aligned with cells; keyboard focus visible;
  - no failed requests, JS exceptions or console errors; no stage started by browsing.
- **Polling and corrupt manifest, 8/8:**
  - single-flight polling;
  - a corrupt manifest shows "Run records unreadable" and an UNKNOWN banner, then recovers without a reload.
- **Live Pipeline end-to-end, 15/15.** Real runner, real stages, isolated full copy:
  1. opening and reloading pages starts nothing;
  2. the policy is shown for every stage;
  3. a confirm-class stage needs a second click, and Back cancels;
  4. an upstream input change shows dependants STALE live;
  5. **Run all** returns 202, then stale stages re-run in dependency order and become fresh; the launch shows EXITED, exit 0, without a reload;
  6. **a real stage paused mid-run (SIGSTOP on its process) is shown RUNNING** with elapsed time and activity, and no percentage;
  7. while it runs, the controls are disabled and a direct POST gets 409;
  8. **the server restarts mid-run:** the page shows connection lost, reconnects, and still shows RUNNING;
  9. after SIGCONT the run completes and the page updates;
  10. the first click after the restart launches (nonce renewed); **a real failure** shows FAILED with the retained result, and the previous output stays byte-identical;
  11. a corrupt manifest disables launches;
  12. at 390 px there is no overflow, and there are no JS exceptions.
- **Candidate traceability** (Acetylcysteine, Agomelatine) — every page shows:
  - rank, all five dimensions, the formula/version, the confidence interval, and "not efficacy";
  - PMIDs, NCT IDs, dates and source links, plus cutoff status;
  - missing/neutral states, conflicts and review status.

  These are text-presence checks.

**Not offered:** cancellation (stopping the runner mid-stage would skip its restore-on-failure step). **No fabricated progress:** elapsed time and the latest log line only.

## 3. Eight agents
`evidence/agent_validation_matrix.json` is generated from the registry, run state, envelopes and evidence.

| Agent | Role | Envelope | Status | Execution evidence |
|---|---|---|---|---|
| 10a | literature/study-design credibility (diagnostic) | valid | SUCCESS | integration test reproduces the output; isolated runner execution; Live-pipeline real run |
| 10b | molecular/pathway (via stage 08) | valid | SUCCESS | same |
| 10c | clinical trials (via stages 03/03c); 28 links await human review | valid | SUCCESS | same; live CT.gov refetch identical (earlier today) |
| 10d | conflicting-evidence diagnostics | valid | SUCCESS | same, including a real Live-pipeline run |
| 10e | replication diagnostics | valid | SUCCESS | same |
| 10f | safety (via stage 05) | valid | SUCCESS | same |
| 10g | cross-source independence | valid | SUCCESS | same; paused, real RUNNING run in the browser test |
| 10h | completeness annotation | valid | SUCCESS | same; real FAILED run with output preserved |

**Registry and containment:**
- every consumed file is declared, and every output has exactly one producer (static-scan tests);
- each agent writes only its declared outputs (10/10, isolated runner execution; agent code unchanged since);
- concurrency (E-035), stale propagation (E-036/E-037) and corrupt-manifest handling (E-038) are all tested.

## 4. Ground truth and scoring
Independent stdlib recomputation (`tests/test_ground_truth_contract.py`; matrix in `SCIENTIFIC_CONTRACT_TRACEABILITY.md`):
- **Pool:** 90 compounds = filtered candidates ∩ compounds with a pre-cutoff trial.
- **Dates:** every feature trial < 2021-01-01 (latest 2020-11-25); every label trial ≥ 2021-01-01 (earliest 2021-01-13); no trial in both sets.
- **Labels:** 14 positives, equal to the frozen approved set. Exclusions remove three (Clozapine, Dexmedetomidine, Remifentanil).
- **Metrics:** AUROC 0.775376 [0.656, 0.881], AUPRC 0.424315 (no ties), 4D 0.700188. The evaluation report's input md5s match the current files.
- **No leakage or bias:** labels never enter the score (every row equals the mean of its five ranks); 21 missing dimensions are all neutral (0.5).
- **Conflicts** between code, artefacts and documented rules: **none found**.

**Reproducibility (B-003, new finding):**
- The approved scores reproduce **exactly** from persisted inputs (`vps_verify`, max abs diff 2.2e-16).
- A **from-source** rerun with current code (stage 02 re-draws its Monte Carlo proximity, seeded since E-031) gives AUROC **0.7763 / 0.7049**, against 0.7754 / 0.7002. The positives are the same and the top-10 set is the same.
- Stage 06 now also writes a `dimensions_imputed` column that the approved file lacks.
- So 02, 06 and eval cannot be code-attested; re-publishing them is an owner decision.

**Temporal validity (unchanged):** with dated molecular inputs, 5D = 0.704, equal to 4D. The approved 0.775 is not leakage-free (TD-033).

## 5. Test commands and results
| Command | Start–end (UTC) | Exit | Result |
|---|---|---|---|
| `./venv/bin/python -m unittest discover -s tests` (baseline) | 08:40:59–08:41:54 | 0 | 628 OK |
| same (final) | 09:07:14–09:08:16 | 0 | **654 OK**, 0 skipped, 0 ResourceWarnings |
| `./venv/bin/python scripts/run_stage.py --status` | 09:12 | 0 | 13 SUCCESS + 12 ADOPTED |
| `./venv/bin/python scripts/run_stage.py --check-manifest` | 09:12 | 0 | ok |
| `./venv/bin/python scripts/vps_verify.py` | 09:12 | 0 | MATCH |
| `./venv/bin/python scripts/vps_verify.py --root data/_candidates/td042_v1/root` | 09:12 | 0 | MATCH (candidate **not published**) |
| `./venv/bin/python data/_candidates/td042_v1/verify_td042_candidate.py` | 09:12 | 0 | verified |
| `./venv/bin/python -m unittest tests.test_ground_truth_contract` | 09:12 | 0 | 9 OK |
| `git diff --check` | 09:12 | 0 | clean |
| offline end-to-end run (isolated copy, proxy-blocked) | 09:05:13–09:06:27 | 0 | 20 SUCCESS; 01/03/03c/04b/diag BLOCKED by design; 0 not fresh; vps_verify MATCH |
| `./venv/bin/python scripts/run_stage.py --attest-from <e2e copy> 00 01 02 03 03c 04 04b 05 06 08 diag eval` | 09:06 | 1 (expected: 8 not attestable) | 4 ATTESTED, 8 refused with reasons (`logs/final_attest.log`) |

**Mocked vs real:**
- `test_live_runs.TestConflicts` uses a stand-in sleeper runner and is labelled so.
- `TestRealLaunch` and the browser Live-pipeline suite use the real runner and real stages.

## 6. Browser acceptance
See §2. The drivers are `evidence/drive{,7,8,9}.py` and `catch_stop.py`. They need Chrome with remote debugging on port 9333, and isolated copies served on port 8799.

## 7. Scientific and submission-readiness findings
- **No manuscript, LaTeX, bibliography or submission template** exists in the repository, so the manuscript itself could not be checked.
- **README metrics are consistent** with the evaluation report (14/90, 0.700 / 0.775, +0.075 [−0.025, 0.176], not significant).
- **TD-048:** `docs/CASE_STUDIES.md` line 4 presents `VPS_grid_3d` (fitted on the labels, so in-sample) as "best-performing, AUROC 0.750", and line 509 gives superseded 0.724 / 0.781. Not edited: this is owner narrative. Fix before submission.
- **Figures:** produced by stage 07 from tracked, verified outputs (07 fresh).
- **Calibration:** correctly not reported (the VPS is a ranking, not a probability).
- **Statistical power:** with 14 positives, no model comparison is statistically supported, and documents say so.

## 8. Remaining defects, limitations, owner decisions
| Item | Who |
|---|---|
| Molecular dimension policy (TD-042 / drop / keep with caveats); bounded literature/safety adoption | owner |
| Label re-freeze; re-publish 02/06/eval to close B-003 and code attestation | owner |
| `docs/CASE_STUDIES.md` superseded metrics (TD-048) | owner |
| 28 clinical-link adjudications | human reviewer |
| `pip-audit` installation (vulnerability scan not run) | approval |
| Semantic Scholar API key (live literature stage) | external |
| Authentication, HTTPS, monitoring, scheduled backups before any sharing (TD-044) | deployment |

**Not tested:**
- full live stages 01/03/03c/04/05/04b/diag;
- a clean-environment install (needs approval to download dependencies);
- screen-reader and contrast tools.

**Known residual:** launches started by an earlier server process show "UNKNOWN" in the launches panel. Their outcome is in the run table, which is authoritative.

## 9. Integrity (compared with `~/EviRep_recovery_final_20261020T0840Z/` at 09:12Z)
- HEAD `576bc7f`; 6 commits, identical history; branches, tags and stashes unchanged.
- **`.git/index` byte-identical; staged diff byte-identical; nothing staged, committed or pushed.**
- Same 21 unstaged paths. The only tracked-file edits were **append-only**, verified byte-for-byte against the snapshot: `development_log/CHANGES.md`, `development_log/ERRORS_AND_BLOCKERS.md`, `TECHNICAL_DEBT.md`.
- All previously untracked files are still present (176 now vs 147; the additions are this mission's files).
- **Protected files 19/19 sha256 OK; approved `vps_scores_v2.csv` sha256 unchanged.** The formula, weights, pool, labels, exclusions and cutoff are unchanged; TD-042 is not published; no clinical decision was made.

## 10. Startup and reproduction
```
./venv/bin/python ui/server.py                      # http://127.0.0.1:8765/  (loopback only; Live pipeline at #live)
./venv/bin/python -m unittest discover -s tests     # 654 tests
./venv/bin/python scripts/run_stage.py --status
./venv/bin/python scripts/run_stage.py --check-manifest
./venv/bin/python scripts/vps_verify.py
./venv/bin/python -m unittest tests.test_ground_truth_contract
./venv/bin/python scripts/run_stage.py --sequence 10a 10a-all 10b 10c 10d 10e 10f 10g 10h review 07   # allow-listed stages
./venv/bin/python data/_runs/continuation_20261019/e2e_offline.py <empty scratch dir> <out.json>      # offline end-to-end
./venv/bin/python scripts/backup_data.py --dest ~/EviRep_backups                                     # verified backup
```
**What was executed this mission:**
- the launch command, the test, status, check-manifest, `vps_verify` and contract commands, and the offline end-to-end run, with the results in §5;
- `--sequence`, through the Live pipeline against isolated copies only (not on the live repository).

`backup_data.py` was executed and verified in the previous sprint (`~/EviRep_backups/evirep_data_20261020T075410Z.tar.gz`).
