# EviRep end-to-end audit and production readiness report (2026-10-20)

**Mission window:** 2026-10-20T07:18:36Z to about 07:40Z, roughly 25 minutes of continuous work. It did not run overnight.

**Supporting documents:**
- [END_TO_END_ARCHITECTURE_AUDIT.md](END_TO_END_ARCHITECTURE_AUDIT.md)
- [EIGHT_AGENT_VPS_CONTRIBUTION_AUDIT.md](EIGHT_AGENT_VPS_CONTRIBUTION_AUDIT.md)
- [PRODUCTION_READINESS_CHECKLIST.md](PRODUCTION_READINESS_CHECKLIST.md)

Earlier reports are preserved unchanged: OVERNIGHT_FINAL_REPORT.md, FINAL_REPORT.md, CHECKPOINT.md (appended only).

## A. Executive summary
**Overall: DEVELOPMENT READY.** EviRep is reliable for local, single-user, read-only use. It is not ready for pilot, staging or production; see K.

**Work completed:**
- **4 defects found and fixed, with regression tests.**
  - One was a real freshness defect (E-036).
  - One was a display defect I introduced and caught in the browser (F-03).
- **All eight agents audited** against their persisted outputs: every envelope is valid and no inputs are stale.
- **One table of candidate score architectures** (A–D) on the same population, reproducing the earlier reported values.
- **Pipeline runs:** live smoke tests of every external source, one live agent refetch, and an offline end-to-end run.
- **20/20 browser checks** at desktop and mobile widths.

**Highest-risk findings:**
1. **(Scientific, owner decision)** The approved 5D AUROC of 0.775 depends on a molecular dimension that is neither cutoff-bounded nor free of double counting. With dated inputs it falls to 0.704, the same as the 4D model.
2. **(Engineering, fixed)** E-036: five agents stayed "fresh" when stage 06 became stale.
3. **(Deployment)** There is no authentication, HTTPS, monitoring, scheduled backup or vulnerability scan. These block any shared deployment (TD-044).

**Remaining blockers:**
- owner decisions on the molecular dimension and on bounded dimensions;
- 28 clinical links awaiting human adjudication;
- a Semantic Scholar API key;
- deployment controls.

## B. Starting state (recovery `~/EviRep_recovery_20261020T0718Z/`, verified readable)
**Git state:**
- branch `main`, in sync with `origin/main`;
- HEAD `576bc7f`, 6 commits, no tags, no stashes;
- remote `github.com/eswarisankar0/EviRep`.

**Pre-existing changes (all owned by the user or earlier sessions; none by this mission):**
- index: 25 files staged (md5 of `git diff --cached` = `d04e97371800f54cc28abbb6a383742b`; `.git/index` copied);
- worktree: 21 modified tracked files;
- untracked: 97 files.

**Snapshot contents:** `git_status.txt`, `worktree.diff`, `index.diff`, `git_index.bin`, `untracked.txt`, `protected_sha256.txt` (19 files, 19/19 OK), the sha256 of the approved VPS file and manifest, and `worktree_snapshot.tgz` (410 entries, listing verified).

**Baseline gates (07:18:59–07:19:49Z):**
- `unittest discover` 598 OK, exit 0;
- `run_stage.py --status`, `vps_verify.py`, the TD-042 verifier and `git diff --check` all exit 0;
- 208 ResourceWarning lines (unclosed files).

pytest is not installed; the project uses unittest.

**Environment:** Python 3.13.9; pandas 3.0.6, numpy 2.5.3, scipy 1.18.1, scikit-learn 1.9.1, networkx 3.7.

## C. Architecture
See the architecture audit for:
- the full stage table (inputs, outputs, dependencies, network, VPS role, rerun safety);
- data classes (protected, curated, candidate, generated, run history, caches);
- the UI ↔ backend flow and the score-publication flow.

**Stage graph:** 01 → 00 → {02, 03 → 03c} → {04 → 04p/04b, 05 → 05h, 08} → 06 → {eval, 07, agents}.

**Agent graph:**
- 10a-all ← 04p
- 10b ← 08, 06
- 10c ← 03c, 08, 06; and review ← 10c
- 10d ← 05, 08, 06; and 10e ← 10d
- 10f ← 05, 05h, 06
- 10g ← 10c, 04, 08, 04p, 06
- 10h ← 06, 10a-all, 10c–10g

## D. Eight-agent audit matrix (persisted outputs verified 2026-10-20)
All eight envelopes validate (`agent_contract.validate_envelope`) and none has stale inputs. Every agent is SUCCESS in the tracker; its upstream is SUCCESS or ADOPTED.

| Agent | Coverage | Error semantics (tests) | UI | Limitations / outstanding |
|---|---|---|---|---|
| 10a | 89/90 assessed, 1 NO_RESULTS, 0 failed; 4,191 papers, 29 duplicates removed | NO_RESULTS ≠ failure; post-cutoff flagged (`test_literature_credibility_agent`, `test_literature_provenance`) | agent panel, compound page | categorical; not a score input |
| 10b | 90 records, 74 with targets, 16 unmeasured | Open Targets outage = RETRIEVAL_FAILED, never 0 (`test_molecular_agent`) | panel, compound page | agent version "unrecorded": the protected stage-08 evidence never stored it (truthful); TD-042 pending |
| 10c | 90 compounds, 177 trials, 195 links, 0 retrieval failures | API failure = failure (`test_clinical_evidence_agent`, `test_stage03_failure_handling`); registry p-values copied, never judged | panel, compound page, review queue | 28 links await human adjudication (untouched) |
| 10d | 19 of 91 assessed (Propranolol is a curated case outside the pool, flagged `in_evaluable_pool: false`), 72 insufficient | missing context = uncertain; stopped trial ≠ negative | panel, conflicts view | no direction source for registry results |
| 10e | 14 findings, 4 compounds | missing metadata = undetermined | panel, compound page | coverage limited by curated outcome claims |
| 10f | label 83 / 7 no record / 0 failed; at the cutoff 31 scored, 52 unknown | no label ≠ safe; FAERS ≠ incidence | panel, safety panel (label at the cutoff) | not cutoff-bounded in the VPS (sensitivity only) |
| 10g | D2 assessable 89/90 (20 dependence found) | no PMIDs → NOT_ASSESSABLE | panel, compound page | **D2 equals the independent overlap analysis** (same 20 compounds) |
| 10h | 90 × 12 domains, 361 gaps | failure / absent / not computed kept distinct | panel, gaps view | annotation only |

**Integration coverage:**
- `test_eight_agents_integration` (7): reproduction of every output, envelopes, pool coverage, 10h freshness, no writes.
- New this mission:
  - registry dependency and stale propagation (2);
  - agent panel freshness (3);
  - concurrency (6, from E-035).

**Live:** the 10c ClinicalTrials.gov refetch (177 trials) in an isolated copy was identical to the persisted output, apart from timestamps.

## E. VPS validation
Details are in the contribution audit and `docs/VPS_FEATURE_CONTRACT.md`. Population: 90 compounds, 14 positives / 76 negatives.

**Approved formula:** `VPS = mean(r_proximity, r_clinical, r_literature, r_safety, r_molecular)`.
- Legacy percentile ranks.
- Neutral 0.5 for unmeasured safety or molecular.
- Median-imputed proximity (2 compounds).

**Result:** 0.775 [0.651, 0.881], reproduced by `vps_verify` (max abs diff 2.2e-16).

| Architecture | AUROC | Δ vs A [95% CI] |
|---|---|---|
| B bounded literature + safety | 0.752 | −0.024 [−0.073, 0.026] |
| C 4D | 0.700 | −0.075 [−0.176, 0.024] |
| D TD-042 | 0.699 | −0.076 [−0.155, −0.015] |
| A-dated / D-dated molecular | 0.704 / 0.703 | −0.071 / −0.072 (CIs include 0) |
| B + D-dated | 0.686 | −0.089 [−0.209, 0.027] |

**Learned weights** (nested CV, grouped and stratified folds) beat equal weights in at most 10% of repeats, and their weights are unstable. Equal weights stay.

**Overlap:** the same trial is counted by both the clinical and the literature dimension for 20 compounds; the effect is +0.002. No label trial appears inside any feature.

**Recommendation and owner decisions:**
- molecular policy: TD-042, drop it, or keep it with caveats;
- whether to adopt bounded literature and safety;
- whether to re-freeze labels.

No agent-derived numeric dimension is defensible (contract grounds; not tested on the labels).

**Nothing changed:** the approved score, weights, pool, labels, cutoff and TD-042 state.

## F. UI and operations audit
**Routes:** all 27 routes were probed.
- 200 for valid requests; 400 for an empty compound name; 404 for unknown documents, logs, figures and paths.
- 405 for non-GET methods; 403 for a foreign Host.
- All traversal attempts were rejected.
- Security headers: CSP, frame denial, nosniff, no-referrer, no-store.
- Slowest routes: `/api/agents` 0.44 s, `/api/compound` 0.24 s.

**Refresh mechanism:** polling of `/api/status` with backoff, visibility awareness and a cheap fingerprint. It is kept: Server-Sent Events or WebSockets are not justified for a single-user local tool.

**Run state:**
- states come from the tracker: RUNNING, SUCCESS, PARTIAL, STALE, FAILED, MODIFIED, MISSING, ADOPTED, UNTRACKED, NOT_RUN;
- elapsed time is shown, never a fabricated percentage;
- log tails are redacted and confined to `data/_runs`.

**Browser** (Chrome via CDP, real backend; `docs/autonomous_runs/evidence/ui_browser_checks_e2e_audit.json` and `agents_panel_desktop_e2e_audit.png`): **20/20**.
- **Coverage:** all views at 1440 px; six views at 390 px with no horizontal scroll.
- **Agent panel:** 8 agents with tracked freshness and VPS role.
- **Review queue:** 28 awaiting adjudication.
- **Compound page:** states that a ranking is not an efficacy claim.
- **Accessibility:** keyboard focus visible; `lang`/`main`/`nav`/labels/alt present; header and cell counts aligned in every table.
- **Clean run:** no failed requests, JS exceptions or console errors, and no stage started by viewing.

**Not checked:** a screen-reader or contrast-ratio audit (no tool).

## G. Changes made (this mission only)
| ID | Files | Root cause | Fix | Regression test | Score / protected data affected? |
|---|---|---|---|---|---|
| E-036 / C-97 | `ui/server.py` registry | 06 omitted from `depends_on` of 10b, 10c, 10d, 10f, 10g | added | `TestRealRegistry` (+2; both fail on the old registry) | no |
| F-02 / C-98 | `ui/server.py`, `ui/app.js` | agent panel used the envelope status only, so it could show SUCCESS with a stale upstream | `tracked_runs` / `tracked_status` / `vps_role`; unreadable manifest → UNKNOWN | `TestAgentPanelTrackedFreshness` (+3) | no |
| F-03 / C-98 | `ui/app.js`, `ui/style.css` | **my first F-02 edit put the new header on the wrong table** (one table got an extra header, the other a missing one); ids and badges broke mid-word | fixed both tables; badges break only between words; id cells `nowrap` | browser check: header/cell alignment on every view | no |
| F-04 / C-99 | `completeness_gap_agent.py`, `evidence_independence_agent.py`, `05h_safety_label_history.py` | files opened without being closed | `with open` | affected suites; 05h/10g/10h re-run via runner, outputs identical excluding timestamps | no |
| C-100 | `scripts/vps_architecture_comparison.py`, `tests/test_vps_architecture_comparison.py` (new) | architectures A–D compared | — | A equals the published `VPS_equal_5d` | no (read-only) |
| C-101 | 4 new docs; appended `CHECKPOINT.md`, `CHANGES.md`, `ERRORS_AND_BLOCKERS.md` (E-036), `TECHNICAL_DEBT.md` (TD-044, TD-045) | — | — | — | no |

**Regenerated through the tracked runner (not protected):**
- `data/safety_label_history.csv` (byte-identical) and `_run.json`;
- `data/evidence_independence.json`, `data/completeness_gaps.json`;
- `data/run_manifest.json`.

**New run outputs:**
- `data/_runs/vps_architecture_20261020/`, `data/_runs/e2e_audit_20261020/`;
- three tracked run directories, named `20261020T0731*`.

## H. Verification ledger
| Command | Time (UTC) | Exit | Result |
|---|---|---|---|
| `./venv/bin/python -m unittest discover -s tests` (baseline) | 07:18:59 | 0 | 598 OK |
| same (final) | 07:34:24–07:35:14 | 0 | **604 OK**, 0 skipped reported; `logs/e2e_audit_final_tests.log` |
| `./venv/bin/python scripts/run_stage.py --status` (final) | 07:35 | 0 | 12 SUCCESS + 13 ADOPTED; no warnings |
| `./venv/bin/python scripts/vps_verify.py` | 07:35 | 0 | MATCH, 90, max abs diff 2.22e-16 |
| `./venv/bin/python scripts/vps_verify.py --root data/_candidates/td042_v1/root` | 07:35 | 0 | MATCH (candidate verified, **not published**) |
| `./venv/bin/python data/_candidates/td042_v1/verify_td042_candidate.py` | 07:35 | 0 | verified |
| `git diff --check` | 07:35 | 0 | clean |
| offline end-to-end run (`data/_runs/continuation_20261019/e2e_offline.py`, isolated copy, proxy-blocked) | 07:24:17–07:25:31 | 0 | 20 SUCCESS; 01, 03, 03c, diag and 04b BLOCKED by design (live-only); 25 fresh; `vps_verify` MATCH |
| live smoke (`logs/e2e_audit_live_smoke.log`) | 07:23 | — | PubMed, CT.gov, openFDA, DailyMed, Zenodo, Open Targets: 200 (OT data version 26.09 = the snapshot); **Semantic Scholar 429 → BLOCKED** |
| live 10c `--fetch` in an isolated copy (`logs/e2e_audit_live_10c.log`) | 07:23 | 0 | 177/177 trials; identical to persisted output (excluding timestamps) |
| `run_stage.py 05h -- --offline`, `10g`, `10h` | 07:31 | 0 | SUCCESS; content identical |
| browser (CDP) | 07:28–07:30 | — | 20/20 |
| protected sha256 | 07:35 | — | 19/19 OK |
| git integrity | 07:35 | — | HEAD unchanged; 6 commits; `.git/index` byte-identical to the snapshot; index-diff md5 unchanged; 0 stashes; nothing staged, committed or pushed |

**Not run:**
- live stages 01/03/03c/04/05/diag in full (costly or rate-limited; last validated live 2026-10-19 in an isolated copy, apart from 04 and 05);
- pip-audit (not installed);
- screen-reader and contrast tools.

**Remaining warnings:** test-only ResourceWarnings (TD-045).

## I. Risk register
| Risk | Severity | Likelihood | Impact | Mitigation | Owner / dependency | Status |
|---|---|---|---|---|---|---|
| The cited 5D AUROC overstates temporally valid performance | High | certain (measured) | misleading claims | report A-dated/D-dated; decide molecular policy | owner | open |
| Registry drift changes labels on a re-run of 03/03c | High | likely over time | silent label change | isolated-copy re-runs only; re-freeze decision | owner | open (controlled) |
| 28 unresolved clinical roles | Medium | certain | feature or label noise | review queue | human adjudicator | open |
| Literature stage cannot run live | Medium | certain without a key | stale literature dimension | S2 API key | external | blocked |
| Dashboard exposed beyond loopback | High if it happens | low (bind refused) | data exposure | loopback-only bind; auth + HTTPS before deployment | engineering | mitigated locally |
| Loss of git-ignored `data/` | High | low | loss of results | manual snapshots; add scheduled backup | engineering | open (TD-044) |
| Corrupt manifest | Medium | very low (atomic writes) | dashboard 500, CLI exit 1 | repair or restore from snapshot | engineering | open (TD-044) |
| Unscanned dependency vulnerabilities | Medium | unknown | — | pip-audit | engineering | open |
| Conflicting concurrent runs | High | — | corrupt outputs | E-035 lock | — | **mitigated** |
| Stale agents shown as fresh | Medium | — | wrong trust signal | E-036 + F-02 | — | **mitigated** |

## J. Production-readiness scorecard (qualitative; no numeric maturity score: no documented method exists)
| Dimension | Assessment |
|---|---|
| Correctness | Good: verifiers match; 604 tests; agents reproduce from inputs |
| Reproducibility | Good: offline end-to-end run reproduces; pinned dependencies; seeded Monte Carlo |
| Scientific validity | **Limited**: small sample (14 positives); molecular dimension temporal and double-counting issues; owner decisions pending |
| Security | Good for loopback; **insufficient** for deployment (no auth or HTTPS) |
| Reliability | Good: concurrency lock, staged publication for 06, retained outputs, failure ≠ negative |
| Observability | Basic: run manifest, per-run logs, live status; no monitoring or structured logs |
| UI usability | Good: live, truthful states; desktop and mobile; automated accessibility subset |
| Deployment readiness | **Not ready** |
| Recovery | Partial: snapshots and `previous/` copies; no scheduled backups or drills |
| Documentation | Good: contracts, decisions, architecture, debt, changes, reports |

## K. Final recommendation: **DEVELOPMENT READY**
EviRep is suitable for local use by its owner as a read-only research dashboard over a tracked, reproducible pipeline. It is not pilot ready:
- the score's headline performance awaits a scientific decision;
- 28 clinical links are unadjudicated;
- there is no authentication or HTTPS for any other user.

## L. Next actions
1. **Owner approval:**
   - molecular dimension policy (TD-042 / drop / keep with caveats);
   - adopting bounded literature (04p) and safety (05h) via a new stage-06 lineage;
   - label re-freeze policy.
2. **Human adjudication:** the 28 links in the review queue (`#review`).
3. **External:** a Semantic Scholar API key (then a live stage 04 in an isolated copy).
4. **Safe engineering:**
   - pip-audit, with approval to install it in the venv;
   - fix the test-only file leaks (TD-045);
   - a manifest repair command;
   - a retention policy for `data/cache` and `data/_runs`.
5. **Deployment and operations (only if it is to be shared):** authentication, HTTPS reverse proxy, structured logging and monitoring, scheduled backups of `data/`.
