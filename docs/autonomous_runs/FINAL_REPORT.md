# Autonomous runs, final report (2026-10-19)

This file covers two runs:
- **Part 2**, the continuation sprint, below;
- **Part 1**, the first autonomous run, further down.

# Part 2: continuation sprint (16:50:51Z–17:28Z, about 37 minutes of active work)

**Elapsed time.** Active work ran from 16:50:51Z to 17:28Z, about 37 minutes, not four hours. I stopped there because:
- every remaining item needs an owner decision, human adjudication, curation or credentials;
- the remaining code items would change approved stages, which requires owner sign-off (§2.7).

Checkpoints: [`CHECKPOINT.md`](CHECKPOINT.md).

## 2.1 Changes (C-85 to C-90)
| Change | Files |
|---|---|
| **Stage 05h: safety label at the cutoff.** Follows each current label's set ID through DailyMed's version history and scores the version published on or before 2020-12-31 with stage 05's exact rule. Its parser is checked against stage 05 on every current label. Per-compound states: SCORED / UNKNOWN / NO_CURRENT_LABEL / RETRIEVAL_FAILED. | `scripts/05h_safety_label_history.py`, registry |
| **10f: label at the cutoff.** Adds `label.at_cutoff` (version, date, boxed warning, terms, changed since the cutoff) and `temporal` for the current label. The coverage block counts the at-cutoff states. | `scripts/safety_evidence_agent.py` |
| **10h.** Safety domain annotated with the label-at-cutoff state; the domain state itself is unchanged. | `scripts/completeness_gap_agent.py` |
| **UI.** The safety panel shows the label at the cutoff, or states it is unknown. Compound pages now use the 90-compound 10a output. | `ui/app.js`, `ui/server.py` |
| **Isolated live re-run of the network stages** | `data/_runs/live_stages_20261019/live_stage_check.py` |
| **Molecular snapshot sensitivity** (Open Targets 20.11 versus 26.09) | `scripts/vps_molecular_snapshot_sensitivity.py`; data in `data/cache/opentargets_20.11/` |
| **Safety-at-cutoff variants** added to the leakage sensitivity | `scripts/vps_literature_cutoff_sensitivity.py` |
| **TD-008 fixed:** the debug helper's disease–gene edge direction | `scripts/debug_step2.py` |
| **One integration test across all eight agents** | `tests/test_eight_agents_integration.py` |
| New tests | `test_safety_label_history.py` (5), `test_molecular_snapshot_sensitivity.py` (2), `test_debug_step2.py` (1), `test_eight_agents_integration.py` (7), plus 10f (+2), 10h (+1), sensitivity (+1), UI (+1) |

## 2.2 Agents
| Agent | Status | This sprint | Evidence |
|---|---|---|---|
| 10a | SUCCESS (`10a-all` 20261019T124258Z) | now shown on compound pages | integration test reproduces its output; offline repro equal to live |
| 10b | SUCCESS | verified, not changed: the recompute equals the published direct component (≤ 1e-6); the TD-042 candidate is still isolated (verifier exit 0; UI shows the approved baseline) | integration test; `test_td042_pathway_rule` |
| 10c | SUCCESS | review state checked: 28 UNRESOLVED and 9 ADJUDICATED; nothing auto-adjudicated | live browser check; `TestReviewQueue` |
| 10d | SUCCESS, 19/91 assessed | **not expanded** (see below) | integration test |
| 10e | SUCCESS, 4 compounds | **not expanded**: needs curated outcome-level claims | integration test |
| 10f | SUCCESS `20261019T170230Z-10f-ad2e` | label at the cutoff: 31 scored (10 changed since the cutoff), 52 unknown, 7 no record, 0 failed | tests; live UI |
| 10g | SUCCESS | consumes 04p (D2 assessable for 89 compounds) | integration test |
| 10h | SUCCESS `20261019T170757Z-10h-bf87` | 10a and 10f integration. The integration test caught 10h stale after 10f was re-run, and the runner also showed STALE; re-running 10h fixed it | integration test 7/7 |

**Why 10d was not expanded.** Registry results would be its only new directional source. Of their primary analyses, 26 carry p-values, and none says which arm is the drug or which direction is favourable (some compare doses with each other). Deriving SUPPORTS or OPPOSES from them would invent certainty.

## 2.3 Live re-run of the network stages (real services, isolated copy; protected files untouched)
| Stage | Result | Compared with the protected live outputs |
|---|---|---|
| 01 (Hetionet from zenodo) | SUCCESS, 180 s | all 4 outputs byte-identical |
| 00 | SUCCESS | byte-identical |
| 03 (1483 CT.gov searches) | SUCCESS, 1310 s, 0 failed | same 67 label links and same key set. Differences: registry drift in 2 statuses (Terazosin NCT07288450 now WITHDRAWN; Terazosin keeps 4 other label trials, so no label would change); empty phase written as "NA" instead of ""; Ioflupane I 123 feature links changed |
| 03c | SUCCESS | clean labels: same 57 links. Clean features: +1 Ioflupane link (PHASE3; its maximum phase is unchanged) |
| diag | SUCCESS | +1 row (the Ioflupane link) |
| 04b | exit 1 **by design** | provenance guard: today's content gives 17 components and 2 shared-author edges versus 16 and 4 in the checkpoint. Nothing was written, and the persisted graph is unchanged. Stage 04's PMIDs were never persisted (TD-021), so the old sample can't be rebuilt |

These runs validate the live code paths. The live baseline was **not** replaced; doing so would be an owner decision about re-freezing the ground truth.

## 2.4 VPS: cutoff-bounded sensitivity for every dimension
n = 90, 14 positives. Stratified paired bootstrap, 2000 draws. Equal weights. Nothing published.

| Dimension, made cutoff-bounded | Source | 5D AUROC | Δ vs reference [95% CI] |
|---|---|---|---|
| — (approved) | — | 0.775 [0.651, 0.881] | — |
| literature | 04p, papers published ≤ cutoff | 0.757 | −0.019 [−0.067, 0.030] |
| safety, at-cutoff label where available | 05h (31/83) | 0.773 | −0.003 [−0.012, 0.006] |
| safety, at-cutoff label only (others neutral) | 05h | 0.768 | −0.007 [−0.079, 0.071] |
| literature + safety | 04p + 05h | 0.752 | −0.024 [−0.073, 0.026] |
| molecular, direct component only: 26.09 | stage 08 | 0.758 | reference for the next row |
| molecular, direct component only: **20.11** (Nov 2020) | Open Targets FTP | 0.672 | **−0.086 [−0.169, −0.011]** |
| proximity and clinical | already bounded | — | — |

How to read this:
- Literature and safety leakage barely move discrimination.
- The molecular snapshot is the only change whose interval excludes 0.
- That molecular figure is an **upper bound** on leakage, not a clean estimate. It combines newer evidence with Open Targets method changes (new datatypes such as genetic_literature; MONDO versus EFO disease IDs).
- In 2020, the drug targets had almost no evidence in the allowed datatypes (e.g. ACHE scored 0.0 then, 0.58 now).
- The pathway component couldn't be rebuilt for 2020, because Reactome gene sets were never persisted.

Equal weights are retained. The label is continued PD clinical investigation, not efficacy.

**Historical snapshots.**
- **Open Targets:** every release since 16.04 is on the EBI FTP; 20.11 is the last before the cutoff.
- **FDA labels:** DailyMed has version history and versioned label downloads, but only per set ID. 52 current set IDs start after 2020.
- **Alternate labels:** not used. A name search mixes formulations and OTC products.

## 2.5 Commands and exit codes (this sprint)
| Command | Exit / result |
|---|---|
| `run_stage.py 05h` (live) | 0, SUCCESS |
| `run_stage.py 10f`; `10h` (×2) | 0, 0, 0 |
| `live_stage_check.py` (isolated, live) | 01, 00, 03, 03c, diag: 0. 04b: 1 (guard) |
| `e2e_offline.py` full mode (network blocked) | every runnable stage SUCCESS; 25 stages fresh; `vps_verify` MATCH |
| `e2e_offline.py` reproduction mode (published 02 kept) | all SUCCESS. Every agent and provenance output equals live apart from timestamps and input maps. `vps_scores_v2.csv` differs only in the known stage-06 metadata (`dimensions_imputed`, 2 imputed compounds) |
| `vps_literature_cutoff_sensitivity.py`; `vps_molecular_snapshot_sensitivity.py` | 0; 0 |
| Live browser checks (port 8765) | 9/9 (`evidence/ui_live_checks_continuation.json`) |
| `./venv/bin/python -m unittest discover -s tests` | **581 tests, OK, exit 0** (560 at the start) |
| `vps_verify.py` live / candidate; `verify_td042_candidate.py` | 0 / 0; 0 |
| `git diff --check` | 0 |

## 2.6 Integrity
- **Protected files: 19/19 sha256 unchanged.**
- Index diff md5 `d04e97371800f54cc28abbb6a383742b`, unchanged; nothing staged, committed or pushed.
- The live baseline is still `adopted-20261015T015501Z-06`; TD-042 is not published.
- Every stage is fresh.
- The dashboard was restarted with `./venv/bin/python ui/server.py`.

## 2.7 Remaining blockers and next actions, by impact
1. **Owner:** TD-042 publication.
2. **Owner:** whether to adopt cutoff-bounded literature (04p) and safety (05h) dimensions; the data and sensitivities exist.
3. **Owner:** the molecular dimension. It carries the largest temporal effect (§2.4). Options: rebuild stage 08 on Open Targets 20.11 (needs Reactome gene sets and a datatype mapping), or keep it as a sensitivity.
4. **Human:** adjudicate the 28 links in the Review queue.
5. **Owner:** whether to re-freeze labels to today's registry. Only status drift was seen; no label link changed.
6. **Curation:** outcome-level directional claims, to extend 10d and 10e.
7. **Credentials:** a Semantic Scholar API key, for citation edges.
8. **Engineering:** a response cache for stages 03 and 03c, and TD-037 (stage 06 writes non-atomically). The runner already stages and validates stage 06 before publishing, and editing 06 would require re-running an approved stage.

---

# Part 1: first autonomous run

**Elapsed time.** Wall clock 12:24:52Z–16:21Z. That is **not** four hours of work.
- Active work: about 12:25–12:50Z and 16:15–16:21Z, roughly 35 minutes.
- In between, from about 12:50Z to 16:15Z, the session sat idle until the owner's "try".

I stopped when the tasks that could be finished and verified offline, or with the available network, were done. What remains needs owner decisions, human adjudication or credentials (§7).

Checkpoints: [`CHECKPOINT.md`](CHECKPOINT.md). Logs: `logs/`. Evidence: `evidence/`.

Recovery checkpoint, taken before any edit: `~/EviRep_recovery_20261019T1225Z/`. It holds the git status, the worktree and index diffs, the protected sha256 list and a tarball.

## 1. What was implemented
| Change | Files |
|---|---|
| **Stage 04p, literature provenance (TD-021).** Re-runs the stage-04 PubMed query for every compound, both unbounded (retmax 30) and bounded at publication date ≤ 2020-12-31. Persists PMID, DOI, print/electronic/entry dates with precision, cutoff status, publication types, MeSH, authors, book chapters, duplicate groups (DOI, title, erratum link) and truncation. Retries are bounded (429/5xx only). An HTTP 200 with an error payload counts as a failure. A failure is recorded as `RETRIEVAL_FAILED`, never as "no literature", and the stage exits 1. The cache is validated by sha256 and refetched if corrupt; `--offline` mode is available. | `scripts/04p_literature_provenance.py`, registry in `ui/server.py` |
| **10a `--all`.** Design-credibility tiers for every compound: the stage-04 sample, plus the cutoff-bounded set as the leakage-safe view. Duplicate publications are rated once. 04p's day-precision dates replace the issue-year rule. | `scripts/literature_credibility_agent.py`, stage `10a-all` |
| **10g.** D2 ("same study counted as a trial and as a paper") now uses the 04p PMIDs. New D5 flags duplicate publications in the literature sample. | `scripts/evidence_independence_agent.py`, `ui/app.js` |
| **10h.** Reads the 10a-all output: assessed, absent at source and retrieval failure stay distinct. 10a staleness is tracked. | `scripts/completeness_gap_agent.py` |
| **VPS sensitivity: cutoff-bounded literature** (isolated, nothing published) | `scripts/vps_literature_cutoff_sensitivity.py` → `data/_runs/literature_cutoff_20261019/` |
| **Review queue.** A tracked stage `review` writes `data/clinical_review_worklist.csv`. Read-only `/api/review` endpoint and a "Review queue" view; the page never records or implies a decision. | `scripts/clinical_role_review.py`, `ui/server.py`, `ui/app.js`, `ui/index.html` |

## 2. The eight agents
| Agent | Status (runner) | This session | Coverage now | End-to-end evidence |
|---|---|---|---|---|
| 10a Literature credibility | SUCCESS (10a curated; 10a-all `20261019T124258Z`) | `--all` mode | **89/90 assessed + 1 absent at source** (was 5); 4191 papers | 04p live → 10a-all → 10h → UI; offline rebuild identical |
| 10b Molecular | SUCCESS | unchanged | 90 records, 74 with targets | earlier verification; suite passes |
| 10c Clinical evidence | SUCCESS | review queue exposed in the UI | 195 links; 28 unresolved, 9 adjudicated | stage `review` → `/api/review` → browser |
| 10d Conflict & context | SUCCESS | unchanged | 19/91 assessed | suite passes |
| 10e Reproducibility | SUCCESS | unchanged | 4 compounds (needs curated outcome claims) | suite passes |
| 10f Safety | SUCCESS | unchanged | labels 83 + 7 no record; FAERS 90/90 | suite passes |
| 10g Evidence independence | SUCCESS `20261019T124433Z` | D2 from 04p, new D5 | D2 assessable **89/90** (was 4): 20 compounds count one study as both a trial and a paper. D5: 9 compounds have duplicate publications | runner → 10h → UI (D5 shown on compound pages) |
| 10h Completeness & gap | SUCCESS `20261019T124535Z` | 10a-all integration | 90 × 12 domains | runner, UI |

Agents 10b–10f were not changed this session. Their earlier verification stands, and their tests pass in the full suite. I did not re-run them live.

## 3. Defects fixed and regression tests
| Defect | Test |
|---|---|
| Literature PMIDs, dates and truncation were never persisted, so leakage and duplicates could not be audited (TD-021) | `tests/test_literature_provenance.py` (13): same query as stage 04, date precision and cutoff edges, book chapters, duplicates, retry bounds, HTTP-200 error payload, failure ≠ no results, all-fail writes nothing, corrupt cache refetched, offline byte-identical |
| Stage 04 silently ignores PubMed book chapters (PubmedBookArticle), part of the 30-vs-26 discrepancy; 04p parses them and flags them as non-primary evidence | same file (`test_book_chapter_is_parsed_undated_and_not_primary`) |
| 10a dated e-pub-ahead-of-print papers by their later issue year | `TestAllCompoundsMode.test_report` |
| 10g D2 was not assessable for 86 compounds | `test_provenance_makes_d2_and_d5_assessable`, `test_unreadable_provenance_cache_is_reported` |
| 10h reported literature credibility NOT_RETRIEVED although the data now exists | `TestCredibilityState` |
| Unresolved review items were not visible in the UI | `TestReviewQueue` (missing or malformed artefact; counts match; no decision field) |

## 4. Commands and results (executed this session)
| Command | Result |
|---|---|
| `./venv/bin/python -m unittest discover -s tests` (start) | 535 tests, OK, exit 0 |
| `./venv/bin/python scripts/run_stage.py 04p` | 1st run: exit 1, PARTIAL. Ondansetron hit a transient efetch HTTP 400; it was reproduced as 200 a minute later. 2nd run: exit 0, SUCCESS, 4220 records |
| `run_stage.py 10a-all` / `10g` / `10h` / `review` | each exit 0, SUCCESS |
| Offline 04p rerun on a copy, network blocked | exit 0; `literature_papers.jsonl` and `literature_provenance.csv` byte-identical |
| `scripts/vps_literature_cutoff_sensitivity.py` | exit 0 (2000 bootstrap draws) |
| Live browser checks (headless Chrome, port 8765) | 7/7 (`evidence/ui_live_checks.json`). One check first failed because my script inspected the wrong page; it passed once pointed at the pipeline view |
| `./venv/bin/python -m unittest discover -s tests` (end) | **560 tests, OK, exit 0**, 0 skipped |
| `scripts/vps_verify.py` live / `--root data/_candidates/td042_v1/root` | exit 0 / exit 0 |
| `data/_candidates/td042_v1/verify_td042_candidate.py` | exit 0 |
| `git diff --check` | exit 0 |

## 5. VPS results (n = 90, 14 positives, prevalence 0.156; stratified paired bootstrap, 2000 draws)
| Model | AUROC [95% CI] | AUPRC | P@10 |
|---|---|---|---|
| 5D approved (live) | 0.775 [0.651, 0.881] | 0.424 | 0.50 |
| 5D, literature = cutoff-bounded count | 0.757 [0.635, 0.864]; Δ −0.019 [−0.067, 0.030] | 0.384 | 0.40 |
| 5D, literature = bounded author components | 0.748 [0.619, 0.858]; Δ −0.027 [−0.073, 0.016] | 0.380 | 0.40 |
| 5D TD-042 candidate (not approved) | 0.699 [0.557, 0.830] | 0.307 | 0.40 |
| 5D TD-042, bounded count | 0.687 [0.537, 0.822] | 0.294 | 0.30 |
| Cutoff-bounded trio (proximity + clinical + bounded literature) | 0.671 [0.512, 0.822] | 0.360 | 0.40 |

How to read this:
- **Literature leakage is real but does not drive the result.** The median sample is 43% post-cutoff. Bounding literature at the cutoff moves AUROC by −0.02 to −0.03, and every CI includes 0.
- The bounded measures correlate with the published one at Spearman 0.85–0.87.
- Safety labels and Open Targets remain current snapshots, so no evaluation is leakage-free.
- Equal weights are kept (`docs/VPS_WEIGHTING_DECISION_2026-10-19.md`). Nothing was tuned, and nothing was published.
- The label means continued PD clinical investigation. It does not mean efficacy or approval.

## 6. Live versus offline
| Live (network, this session) | Offline / fixture |
|---|---|
| PubMed esearch/efetch via 04p: 90 compounds | 04p offline rerun (byte-identical); all new unit tests use fakes, with sockets refused in the 10g tests |
| Connectivity: PubMed, CT.gov, openFDA return 200; Semantic Scholar 429 without a key; Open Targets reachable | 10a-all, 10g, 10h, review and the sensitivity analysis run from persisted files |

Stages 01, 03, 03c, diag and 04b were **not** re-run live this session (B-002 is unchanged).

## 7. Remaining blockers
| Item | Needs |
|---|---|
| TD-042 publication (`sh data/_candidates/td042_v1/publish_td042.sh`) | **owner decision**; not published |
| 28 unresolved clinical links (now in the UI Review queue) | **human adjudication** (D-020 file) |
| Whether the VPS literature dimension should become cutoff-bounded (data now exists) | **owner decision** (changes an approved dimension) |
| Citation edges for bounded-literature independence (Semantic Scholar 429) | **credentials**: an S2 API key (none configured) |
| 10e/10d coverage: needs outcome-level directional claims | **human curation**; nothing was fabricated |
| Live replay of stages 03/03c/01 | network time, plus a response cache (B-002) |

## 8. Git and integrity
- Branch `main`. 92 porcelain entries; all earlier user work is preserved.
- New untracked files: `scripts/04p_literature_provenance.py`, `scripts/vps_literature_cutoff_sensitivity.py`, two test files, `docs/autonomous_runs/`.
- New data: `data/literature_*`, `data/cache/pubmed_lit/`, `data/clinical_review_worklist.csv`, `data/clinical_role_review.csv`.
- Index diff md5 `d04e97371800f54cc28abbb6a383742b`, identical to the start. Nothing was staged, committed or pushed.
- **Protected files: 19/19 sha256 unchanged** (ground truth, VPS scores, clinical inputs, exclusions, D-020 roles, candidates, stage outputs).
- The live baseline is still `adopted-20261015T015501Z-06`.
- The dashboard was restarted with `./venv/bin/python ui/server.py` and serves on 8765. Status: 13 ADOPTED and 13 SUCCESS stages, none stale.

## 9. Next actions, by impact
1. **Owner:** decide TD-042. Until then, do not present 5D 0.775 as an improvement over 4D.
2. **Human review:** adjudicate the 28 links in the UI Review queue, keyword-decided first.
3. **Owner:** decide whether to adopt a cutoff-bounded literature dimension. Evidence: `data/_runs/literature_cutoff_20261019/`, TD-021 update.
4. **D2 finding:** 20 compounds count the same trial as both clinical and literature evidence. Decide a de-duplication policy together with TD-038.
5. With an S2 API key, add citation edges to the bounded-literature independence measure.
