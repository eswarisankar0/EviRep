# Mission report, 2026-10-19 (09:40Z–10:11Z, about 30 minutes of execution)

Continues [`SPRINT_REPORT_2026-10-19.md`](SPRINT_REPORT_2026-10-19.md) and
[`SPRINT_REPORT_2026-10-19_CONTINUATION.md`](SPRINT_REPORT_2026-10-19_CONTINUATION.md).

The weighting decision is in [`VPS_WEIGHTING_DECISION_2026-10-19.md`](VPS_WEIGHTING_DECISION_2026-10-19.md). The checkpoint and all evidence are in `data/_runs/mission_20261019/`.

The session stopped because every remaining item needs one of three things:
- an owner decision (TD-042 publication);
- human adjudication (28 trial links);
- live network access (5 stages).

None of these was worth padding the session for.

## 1. Verified starting state and approval
- 519 tests OK; protected hashes 19/19 unchanged; git index unchanged; all stages fresh.
- **No owner approval for TD-042 publication exists.** DECISIONS.md has none, and the task text is conditional. The live baseline was therefore **not** changed: it is still `adopted-20261015T015501Z-06`, the double-counting 5D. Candidate `data/_candidates/td042_v1/` still verifies (`vps_verify` exit 0, `verify_td042_candidate.py` exit 0).

## 2. Work completed
| Area | Result | Evidence |
|---|---|---|
| **Weighting** | repeated nested CV (20 × 5 outer, 4 inner; standard and shared-trial-grouped folds). Simplex, shrinkage and L2-logistic weights never reliably beat equal weights (0–5% of repeats); fitted weights are unstable. **Equal weights retained.** Ablations: clinical matters most (−0.080); with TD-042, molecular adds nothing (4D = 5D ± 0.001) | `vps_weighting_20261019/`, decision doc |
| **Eight-agent composite** | not defensible: 3 agents already feed dimensions; the other 5 fail on coverage, scale or independence | decision doc §7 |
| **E-031: stage 02 not reproducible** | set iteration under PYTHONHASHSEED changed seeded draws (Δz up to 2.0). Fixed: 3 hash seeds give identical output. Over 10 seeds, 5D AUROC ranges 0.769–0.783 and ranks Spearman ≥ 0.995 | `test_proximity_determinism.py` (fails on the old code); `proximity_seed_sensitivity.csv` |
| **E-033: stage 03** | a failed search published a silently smaller pool with exit 0; an outage meant ~6 h of retries. Fixed: write nothing and exit 1, breaker after 10 consecutive failures, explicit opt-in | `test_stage03_failure_handling.py` |
| **E-034: stage 03c** | a failed lookup became "not interventional"; the stage never produced its declared clean files. Fixed: same guards; the filter refuses ERROR rows; 03c runs the filter, which reproduces the protected clean CSVs byte for byte | same test file |
| **E-032: stage 04b** | could not run under the runner (missing required `--compound`). Fixed; a registry test checks required arguments for every stage | `TestRegistryRunArgs` |
| **Runner** | records a script fingerprint; warns (does not mark STALE) when a stage's code changes after its last success; `--skip-fresh` re-runs such stages | `test_run_tracking.py` |
| **Offline end-to-end pipeline** | fixture copy, network blocked. Full mode: every runnable stage SUCCESS, all 21 fresh, `vps_verify` MATCH. Reproduction mode (02 kept): every live value reproduced; the only differences are timestamps, input hashes, the stage-06 metadata column and the intended Rifampicin role change | `e2e_offline_full.json`, `e2e_offline_repro.json` |
| **External blockers (B-002)** | 01 (zenodo), 03, 03c, diag (ClinicalTrials.gov), 04b (PubMed/S2): live-only, no response cache. Not re-executed | ERRORS_AND_BLOCKERS B-002 |
| **Clinical review** | ChEMBL preferred name added as an alias in 10c and the review tool (one shared helper). Exactly 1 verdict changed: Rifampicin NCT02174250, BACKGROUND_OTHERNAME → CO_ADMINISTERED, a drug-interaction study. It stays on the list as CHEMBL_ALIAS/UNRESOLVED. **28 unresolved** (5 keyword, 2 alias, 1 ChEMBL-alias, 20 no arm data); 9 adjudications retained | `clinical_review_20261019/review_worklist_flagged.csv` |
| **Agents** | all 8 deterministic on identical inputs; 10a–10f reproduce persisted output exactly; 10g/10h differ only in the input hashes of upstream files regenerated in the copy | `agent_determinism_check.py` |
| **UI** | live server restarted with the documented command (PID 29826 → new). Live: approved baseline and run ID shown; candidate listed as pending, never displayed (Donepezil rank 1 = approved); 390 px fine; 0 JS errors (6/6). Fixtures: 12/12 + 8/8 (RUNNING seen, publish without reload, FAILED/STALE/MODIFIED/MISSING, recovery, 390/1366 px) | `mission_20261019/ui_acceptance/` |

## 3. Agent coverage (current artefacts)
| Agent | Coverage | Kind |
|---|---|---|
| 10a Literature credibility | 5/90 compounds, 40 papers | categorical |
| 10b Molecular | 90/90 records; 74 with targets | numeric (dimension 5) |
| 10c Clinical evidence | 90 compounds; 195 links; 177 trials; 67 with posted results | numeric via stage 03; roles diagnostic |
| 10d Conflict & context | 91 compounds; 19 assessed | categorical |
| 10e Reproducibility | 4 compounds, 14 findings | categorical |
| 10f Safety evidence | labels 83 + 7 no record; FAERS 90/90 | numeric via stage 05; FAERS diagnostic |
| 10g Evidence independence | D1/D4 90; D2 4; D3 3 | overlap diagnostic |
| 10h Completeness & gap | 90 × 12 domains | completeness |

## 4. VPS status
| | Formula | 5D AUROC | State |
|---|---|---|---|
| Live (approved) | equal-weight 5D; molecular double-counts its own target | 0.775 [0.651, 0.881] | published; **known inflated** |
| TD-042 corrected | equal-weight 5D, corrected molecular | 0.699 [0.557, 0.830] | verified candidate, **awaiting approval** |
| 4D sensitivity | equal-weight, no molecular | 0.700 [0.560, 0.830] | — |
| Cutoff-bounded sensitivity | proximity + clinical | 0.653 [0.480, 0.808] | restricted, not a better model |

Prevalence is 0.156. P@10 is precision in the top 10, with boundary ties averaged. All CIs come from a stratified, paired bootstrap (2000 draws) with the compound as the resampling unit. The 5D vs 4D difference is inconclusive in every version. No evaluation is leakage-free (literature, labels and Open Targets are current snapshots).

## 5. Tests and integrity (final)
| Check | Result |
|---|---|
| `./venv/bin/python -m unittest discover -s tests` | 535 tests, exit 0, 0 skipped, 0 failures |
| `scripts/vps_verify.py` live / candidate | exit 0 / exit 0 |
| `data/_candidates/td042_v1/verify_td042_candidate.py` | exit 0 |
| `git diff --check` | clean |
| Protected hashes | 19/19 unchanged |
| `git diff --cached` | unchanged; nothing staged, committed or pushed |

Rollback: all code changes are in the files listed in CHANGES C-71 to C-77 plus the runner fingerprint. No protected data file was written. Experiment outputs are new folders under `data/_runs/`.

## 6. Owner decisions and next actions
1. **TD-042.** Approve and run `sh data/_candidates/td042_v1/publish_td042.sh`, or decline. Until then, never report the live 5D AUROC as an improvement over 4D.
2. **Optional**, bundled with (1): re-run stage 02 with the deterministic code. Proximity changes within Monte Carlo noise (E-031).
3. **Human adjudication** of the 28 unresolved trial links, keyword-decided first.
4. **When network access is available:** cache stage 03/03c registry responses so those stages can be replayed offline (B-002).
