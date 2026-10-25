# EviRep overnight mission — final report (2026-10-20)

**Time.** The session started at 2026-10-19T18:45:42Z and ended at about 07:00Z on 2026-10-20. For most of that window the session was paused on a usage limit, not working. Actual working time was roughly **45 minutes**, nowhere near the six hours the brief allowed. Everything below was produced in that time and was verified.

**Integrity at the end:**
- Nothing was staged, committed or pushed. The index diff md5 is still `d04e97371800f54cc28abbb6a383742b`.
- All 19 protected files match their sha256.
- `git diff --check` is clean.
- TD-042 was verified only; it was not published.
- No weight was tuned.
- The 28 unresolved clinical links are untouched.

Recovery checkpoint: `~/EviRep_recovery_20261019T1845Z/` (git status, worktree and index diffs, protected hashes, tarball).

## 1. Summary
| Area | Outcome |
|---|---|
| Runner defect | **E-035 fixed.** Conflicting concurrent launches (same, upstream or downstream stage) were allowed. They are now refused atomically (exit 3, nothing written). Reproduced: 4 of 6 new tests fail on the old runner. |
| Live UI | The run table now shows: duration, elapsed time while running (no fabricated percentage), upstream states, warnings, and the log tail on demand (`/api/log`: run id validated, confined to `data/_runs`, redacted). Browser checks passed 15/15 at desktop 1440 px and mobile 390 px, including a real RUNNING run and refused launches in an isolated copy. No JS exceptions. |
| VPS feature contract | `docs/VPS_FEATURE_CONTRACT.md`, checked against `06_vps_fusion.build_standardized_scores`. `vps_verify`: MATCH. |
| Double counting | For 20 compounds, the literature dimension includes a paper reporting a trial the clinical dimension already counts. 10g D2 finds the same 20 with independent code. No paper reports a label trial. Removing the duplicates changes AUROC by +0.002. |
| Weights | Equal weights are confirmed on the new cutoff-bounded feature sets: learned weights beat equal in ≤ 10% of repeats, and their weights are unstable. |
| Temporal validity | **The molecular dimension was rebuilt from inputs that all predate the cutoff** (Open Targets 20.11, UniProt 2020-11, ChEMBL 2020-06). The approved 5D AUROC falls from 0.775 to 0.704, which equals the 4D model (0.700). The TD-042 rule gives 0.703. |

## 2. Agents 10a–10h
Every agent's latest run is SUCCESS and fresh (`run_stage.py --status`: 12 SUCCESS, 13 ADOPTED, 0 STALE/FAILED). `tests/test_eight_agents_integration.py` reproduces every persisted agent output from its inputs.

| Agent | Latest run | Coverage / state | Failure ≠ negative (tested) | This session |
|---|---|---|---|---|
| 10a Literature credibility | `…124258Z-10a-all-72df` | 89/90 assessed; 1 absent at source | yes | — |
| 10b Molecular | `…075441Z-10b-9e7a` | 74 with targets; 16 unmeasured (neutral) | yes | full 20.11 rebuild (§4) |
| 10c Clinical | `…095729Z-10c-a607` | 28 links awaiting human adjudication (not touched) | yes (API failure = failure) | — |
| 10d Conflict & context | `…075440Z-10d-707a` | curated claims only; registry p-values not used (arms and direction unlabelled) | yes (missing context = uncertain) | not expanded: no traceable direction source |
| 10e Reproducibility | `…075441Z-10e-c8c4` | 4 compounds with outcome-level claims | yes (missing metadata = undetermined) | not expanded, same reason |
| 10f Safety | `…170230Z-10f-ad2e` | label at the cutoff: 31 scored, 52 unknown, 7 no record | yes | — |
| 10g Evidence independence | `…124433Z-10g-d0f6` | D2 assessable 89/90 (20 DEPENDENCE_FOUND) | yes (no PMIDs → NOT_ASSESSABLE) | D2 cross-validated (§3) |
| 10h Completeness & gaps | `…170757Z-10h-bf87` | 90 × all domains | yes | — |

## 3. VPS
**Approved baseline (unchanged):**
- equal-weight mean of 5 percentile ranks;
- AUROC 0.775 [0.651, 0.881], AUPRC 0.424;
- n = 90, 14 positives (prevalence 0.156).

### Dimension dependence
Spearman between ranked dimensions is at most |0.44| (proximity–literature).

### Double counting (`scripts/vps_evidence_overlap.py`)
| | Result |
|---|---|
| Compounds whose stage-04 sample reports one of their own pre-cutoff feature trials | 20 (21 in the cutoff-bounded set) |
| Compounds whose papers report a post-cutoff label trial | 0 |
| 5D, bounded literature with those papers removed vs bounded literature | +0.002 [−0.004, 0.009] |

### Learned weights on the experimental, cutoff-bounded sets (`scripts/vps_weighting_experimental.py`)
Protocol: nested CV, 20 repeats; stratified / trial-grouped folds.

Mean out-of-fold AUROC:

| Feature set | Equal | Simplex | Shrink | L2 logistic | Learned beats equal (share of repeats) |
|---|---|---|---|---|---|
| 5D TD-042 + bounded lit. + safety at cutoff | 0.681 | 0.599 / 0.559 | 0.664 / 0.650 | 0.525 / 0.526 | ≤ 0.05 |
| bounded 4D (no molecular) | 0.679 | 0.605 / 0.573 | 0.665 / 0.652 | 0.553 / 0.551 | ≤ 0.10 |
| bounded trio (proximity, clinical, bounded lit.) | 0.670 | 0.624 / 0.614 | 0.640 / 0.642 | 0.581 / 0.577 | ≤ 0.05 |

Simplex weight SD across folds is 0.12–0.27. **Equal weights stay. No fitted weight is defensible with 14 positives.**

### Temporal validity (5D, paired bootstrap 2000 draws, seed 20261019)
| Dimension rebuilt at the cutoff | Δ AUROC |
|---|---|
| literature (04p, papers ≤ cutoff) | −0.019 [−0.067, 0.030] (earlier run) |
| safety (05h label at the cutoff) | −0.003 [−0.012, 0.006] (earlier run) |
| **molecular, full rebuild at OT 20.11 (approved rule)** | **−0.086 [−0.186, 0.020]** → 0.690 |
| molecular, full rebuild at OT 20.11 (TD-042 rule) | −0.009 [−0.087, 0.071] → 0.690 |
| **molecular, every input dated (+ ChEMBL 2020-06 targets), approved rule** | **−0.071 [−0.173, 0.030] → 0.704** |
| molecular, every input dated, TD-042 rule | +0.004 [−0.065, 0.082] → 0.703 |

**Method check:** rebuilding the 26.09 pathway component from the persisted records gives an exact match (max abs 0.0).

**Source vs time:**
- Reactome membership barely changed between 2020 UniProt and 26.09: 262 of 307 drug–target pairs are identical, and the rest differ by about one pathway.
- So the drift comes from Open Targets' PD evidence (module genes and scores). Spearman between the 2020 and published molecular dimension is 0.26.
- Open Targets scoring methods also changed, so temporal and method effects cannot be separated.
- **Dated targets:** 70 drugs have a human ChEMBL 2020-06 mechanism target (74 today), and 62 have an identical target set.

**Conclusion:** the approved 5D's lead over 4D (0.775 vs 0.700) does not survive a pre-cutoff molecular dimension. With every molecular input dated, 5D equals 4D under either rule. This strengthens the case for TD-042, or for dropping molecular from the primary score. That is an owner decision; nothing was changed.

## 4. Defects fixed and tests added
| ID | Defect | Fix | Regression test |
|---|---|---|---|
| E-035 | concurrent conflicting launches both wrote `data/` | atomic check-and-claim under the manifest lock; `StageBusy`, exit 3 | `TestConcurrentLaunch` (6) |
| — | the UI hid run durations, elapsed time, upstream states and logs | status fields + `/api/log` + run table | runner (+1), `TestRunLog` (3), browser 15/15 |
| — | pre-existing ResourceWarning (unclosed file) in a registry test | `with open` | — |

New tests:
- `test_evidence_overlap.py` (2), `test_vps_weighting_experimental.py` (1), `test_molecular_historical.py` (4);
- `test_run_tracking.py` (+7), `test_ui.py` (+3).

One idea was rejected on purpose: showing whether optional credentials are set. An existing TD-029 test forbids the server reading the environment, and that rule was kept.

## 5. Commands and exit codes
| Command | Result |
|---|---|
| `./venv/bin/python -m unittest discover -s tests` (start) | 581 tests OK, exit 0 |
| same (mid) | 594 OK, exit 0 |
| same (final) | see §7 |
| `./venv/bin/python scripts/vps_verify.py` | MATCH, exit 0 |
| `./venv/bin/python scripts/vps_verify.py --root data/_candidates/td042_v1/root` | MATCH, exit 0 |
| `./venv/bin/python data/_candidates/td042_v1/verify_td042_candidate.py` | exit 0 (not published) |
| `./venv/bin/python scripts/vps_evidence_overlap.py` | exit 0 |
| `./venv/bin/python scripts/vps_weighting_experimental.py` | exit 0 (22 s) |
| `./venv/bin/python scripts/vps_molecular_historical.py` | exit 0 (about 20 s; the reruns reproduced the earlier numbers exactly) |
| `data/_runs/continuation_20261019/e2e_offline.py <copy> data/_runs/overnight_20261020/e2e_offline_full.json` | see §7 |
| browser (CDP, Chrome headless) | 15/15, `docs/autonomous_runs/evidence/ui_live_checks_overnight.json` |

**Live vs fixture:**
- **Live network this session:** the Open Targets 20.11 FTP file downloads only.
- **Offline:** every other analysis used persisted artifacts or caches.
- **Isolated copies:** the browser RUNNING scenario and the end-to-end run, never the live root.

## 6. Changed and new files (this session)
**Modified:**
- `scripts/run_stage.py`, `ui/server.py`, `ui/app.js`;
- `tests/test_run_tracking.py`, `tests/test_ui.py`;
- `development_log/CHANGES.md` (C-91..C-96), `development_log/ERRORS_AND_BLOCKERS.md` (E-035), `TECHNICAL_DEBT.md` (TD-033);
- `docs/autonomous_runs/CHECKPOINT.md`.

**New:**
- scripts: `vps_evidence_overlap.py`, `vps_weighting_experimental.py`, `vps_molecular_historical.py`;
- tests: `test_evidence_overlap.py`, `test_vps_weighting_experimental.py`, `test_molecular_historical.py` (4);
- docs: `docs/VPS_FEATURE_CONTRACT.md`, this report;
- run outputs: `data/_runs/{evidence_overlap,vps_weighting_experimental,molecular_historical,overnight}_20261020/`;
- cache: `data/cache/opentargets_20.11/{uniprot-2020-11-10.xml.gz, ReactomePathways-2020-11-10.txt, ReactomePathwaysRelation-2020-11-10.txt, chembl_mechanism_rest_api-2020-06-01.json.gz, chembl_target_rest_api-2020-06-01.json.gz}`.

## 7. Final verification (2026-10-20T06:55Z)
| Gate | Result |
|---|---|
| `./venv/bin/python -m unittest discover -s tests` | **598 tests, OK, exit 0** (log `docs/autonomous_runs/logs/overnight_final_tests.log`) |
| Offline end-to-end run (network blocked, isolated copy, new runner) | every runnable stage SUCCESS; 5 live-only stages BLOCKED by design (01, 03, 03c, diag, 04b); 25/25 fresh; vps_verify MATCH; exit 0 (`data/_runs/overnight_20261020/e2e_offline_full.{log,json}`) |
| `vps_verify` (live and candidate) / TD-042 verifier | MATCH / MATCH / exit 0 |
| Protected files (sha256) | 19/19 OK |
| Git index | md5 `d04e97371800f54cc28abbb6a383742b`, unchanged (nothing staged, committed or pushed) |
| `git diff --check` | clean, exit 0 |
| Stage freshness (`run_stage.py --status`) | 12 SUCCESS + 13 ADOPTED; 0 STALE, FAILED or MODIFIED |
| Dashboard | `./venv/bin/python ui/server.py` restarted on the new code (port 8765); browser 15/15 |

## 8. Blockers (owner or human decisions; nothing done without approval)
1. **Molecular dimension policy.** Options: approve TD-042, drop molecular from the primary score, or keep it with the temporal caveat. The new evidence: the approved 5D advantage disappears with a pre-cutoff rebuild.
2. **Adopting cutoff-bounded literature and safety** as published dimensions (04p / 05h).
3. **Adjudicating the 28 unresolved clinical links** (review queue).
4. **10d/10e coverage.** Needs curated outcome direction per trial arm; registry p-values cannot provide it safely.
5. **A Semantic Scholar API key** for citation edges (stage 04 is rate-limited without one).

## 9. Next steps, in priority order
1. Owner decision on item 1, using `data/_runs/molecular_historical_20261020/molecular_historical.json`.
2. If cutoff-bounded dimensions are adopted, publish through `run_stage.py 06` with a new, validated input lineage, never by editing the files.
3. Done this session: drug → target mapping dated with ChEMBL 2020-06 (see §3). Remaining current-snapshot inputs in the evaluation: clinical phase fields (today's registry record) and the unbounded literature and safety dimensions.
