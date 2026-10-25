# EviRep end-to-end architecture audit (2026-10-20)

**Sources and method.** This map is generated from the live stage registry (`ui/server.py` `STAGES`), the single source the runner (`scripts/run_stage.py`) and the dashboard both use. It was checked against the scripts by `tests/test_ui.py::TestRegistryMatchesCode` and `tests/test_run_tracking.py::TestRealRegistry`.

It complements, and does not replace:
- `docs/RUNS_AND_LIVE_UI.md`
- `docs/AGENT_CONTRACT.md`
- `docs/VPS_FEATURE_CONTRACT.md`

## 1. Stage dependency map
Legend:
- **Net:** live network needed for a full (non-cached) run.
- **VPS:** output feeds the approved score directly.
- **Rerun safety:** what a tracked rerun touches.

| Stage | Script | Depends on | Main outputs | Net | VPS | Rerun safety |
|---|---|---|---|---|---|---|
| 01 | `01_get_pd_candidates.py` | — | `hetionet_*`, `pd_candidates*.csv` (protected) | Zenodo (155 MB) | input | rewrites protected candidate files; validated live in an isolated copy (2026-10-19, byte-identical) |
| 00 | `00_exclusion_filter.py` | 01 | `pd_candidates_filtered.csv` (protected) | no | pool | deterministic, local |
| 02 | `02_network_proximity.py` | 00 | `network_proximity.csv` (protected) | no | **proximity** | Monte Carlo, seeded (E-031); rerun gives a new draw. Run it only through the runner (backs up and validates) |
| 03 | `03_clinicaltrials_groundtruth.py` | 00 | clinical maturity + ground truth + match audit (protected) | CT.gov (~1,500 requests) | **clinical** + labels | can change labels (registry drift). Isolated copy only, unless the owner approves a re-freeze |
| 03c | `check_studytype.py` | 03 | `*_clean.csv` (protected) | CT.gov | **clinical** + labels | same as 03 |
| 04 | `04_literature_independence.py` | 03c | `literature_independence.csv` (protected) | PubMed + Semantic Scholar (hours; S2 429 without a key) | **literature** | checkpointed; isolated copy only |
| 04p | `04p_literature_provenance.py` | 03c, 04 | `literature_papers.jsonl`, provenance | PubMed (cached) | no (sensitivity) | `--offline` replays the cache byte-identically |
| 04b | `04b_export_literature_graph.py` | 04 (checkpoint) | `literature_graph_droxidopa.json` | PubMed / S2 | no (figure) | provenance guard refuses on content drift (by design) |
| 05 | `05_safety_signal.py` | 03c | `safety_signal.csv` (protected) | openFDA (~90 requests) | **safety** | label drift changes the score; isolated copy only |
| 05h | `05h_safety_label_history.py` | 05 | `safety_label_history.csv` | DailyMed (cached) | no (sensitivity; feeds 10f) | `--offline` safe |
| 08 | `08_molecular_pathway.py` | 03c | `molecular_pathway.csv`, `_evidence.jsonl` (protected) | Open Targets (cached) | **molecular** | replays the cache with the approved rule; TD-042 stays off unless approved |
| 06 | `06_vps_fusion.py` | 02, 03c, 04, 05, 08 | `vps_scores_v2.csv` (protected, approved) + variant/ablation tables | no | **the score** | staged: `--output-dir`, then schema checks + independent `vps_verify`, then `os.replace`; previous outputs kept |
| eval | `vps_evaluation_report.py` | 06 | `vps_evaluation_report.json` (protected) | no | report | offline |
| 07 | `07_generate_figures.py` | 06, 04b | figures | no | no | offline |
| diag | `check_intervention_match.py` | 03c | `intervention_match_check.csv` | CT.gov | no | diagnostic |
| 10a / 10a-all | `literature_credibility_agent.py` | — / 04p | `literature_credibility_*.json` | no | no (diagnostic) | offline |
| 10b | `molecular_run_record.py` | 08, **06** | `molecular_agent_run.json` | no | via 08 | offline re-validation |
| 10c | `clinical_evidence_agent.py` | 03c, 08, **06** | `clinical_evidence.json` | CT.gov (`--fetch` only, ~9 requests) | via 03 | offline from cache |
| review | `clinical_role_review.py` | 10c | `clinical_role_review.csv`, worklist | no | no (human gate) | never decides; 28 links await adjudication |
| 10d | `conflict_context_agent.py` | 05, 08, **06** | `conflict_context.json` | no | no (diagnostic) | offline |
| 10e | `reproducibility_agent.py` | 10d | `reproducibility.json` | no | no (diagnostic) | offline |
| 10f | `safety_evidence_agent.py` | 05, 05h, **06** | `safety_evidence.json` | openFDA (`--fetch` only) | via 05 | offline from cache |
| 10g | `evidence_independence_agent.py` | 10c, 04, 08, 04p, **06** | `evidence_independence.json` | no | via 04 (diagnostic layer) | offline |
| 10h | `completeness_gap_agent.py` | 06, 10c, 10d, 10e, 10f, 10g, 10a-all | `completeness_gaps.json` | no | no (annotation) | offline |

**Bold dependencies** were added in this audit (F-01).

**Why F-01 mattered:** these agents read `data/vps_scores_v2.csv`, but the registry did not declare stage 06. A STALE stage 06 therefore left 10b, 10d and 10f reported as fresh. This was reproduced in an isolated copy and is now covered by `TestRealRegistry` (two tests that fail on the old registry). The only other undeclared edge is 04b → 04, which goes through 04's checkpoint file and is declared intentionally.

## 2. Data classes
| Class | Files | Rule |
|---|---|---|
| Protected / approved (sha256-checked) | ground truth (raw + clean), clinical maturity (raw + clean), `label_role_exclusions.csv`, `pd_candidates*.csv`, `network_proximity.csv`, `safety_signal.csv`, `literature_independence.csv`, `molecular_pathway.{csv,_evidence.jsonl}`, `feature_trial_roles_td038.csv`, `clinicaltrials_match_audit.csv`, `vps_scores_v2.csv`, `vps_evaluation_report.json`, `conflict_claims_curated.json`, `cache/ctgov_precutoff_trials.json` (19 files) | never edited by hand; a rewrite only through a tracked run that the owner approves |
| Human-curated | `conflict_claims_curated.json`, `feature_trial_roles_td038.csv`, `label_role_exclusions.csv`, `docs/CASE_STUDIES.md` | changed only by human decision |
| Candidate (unapproved) | `data/_candidates/td042_v1/` | verify only; never run `publish_td042.sh` without approval |
| Generated, reproducible | agent outputs, `literature_papers.jsonl`, `safety_label_history.csv`, figures | rerun through the runner |
| Run history | `data/_runs/<run_id>/` (log, previous outputs), `data/run_manifest.json` | append-only; never deleted |
| Caches | `data/cache/` (297 MB: PubMed XML, DailyMed, openFDA, Open Targets 20.11 inputs) | provenance-checked; no cleanup policy (see the readiness checklist) |

`data/` is git-ignored, so artifacts are versioned only by the run manifest, `data/_runs/*/previous/` and the external recovery snapshots.

## 3. UI ↔ backend
The dashboard is read-only:
- `ui/server.py` (stdlib `ThreadingHTTPServer`, loopback bind and Host check, GET only);
- `ui/app.js` (vanilla JS, hash routing);
- `ui/index.html`, `ui/style.css`.

**Live updates:** the page polls `/api/status`, a cheap fingerprint of the manifest and outputs. It backs off on failures, slows down while the tab is hidden, and refreshes immediately when the tab becomes visible again. On a `data_version` change it re-renders. It never starts a stage.

**Routes:**
- views: `/api/{pipeline,dimensions,compounds,compound,validation,overview,ranking,agents,conflicts,case_status,evaluation,risks,gaps,evidence,review}`
- run state: `/api/status`, `/api/runmeta`, `/api/log` (validated run id, confined to `data/_runs`, redacted tail)
- documents and figures: `/api/doc`, `/figure/<name>`

**Score publication flow:**
1. Stages 02/03c/04/05/08 write their inputs.
2. Stage 06 writes to `data/_runs/<id>/out`.
3. Schema and finiteness checks run, plus the independent `vps_verify` recomputation.
4. The files are moved into place with `os.replace`, and the manifest is updated under its lock.
5. Downstream stages become STALE through fingerprints and dependencies.
6. The dashboard shows the approved `VPS_equal_5d` and lists pending candidates without displaying them.
