# EviRep

Evidence-based drug repurposing for **Parkinson's disease**. Candidate compounds are
scored on independent evidence dimensions, fused into a Validated Plausibility Score
(VPS), and evaluated against post-cutoff ClinicalTrials.gov entries as ground truth.

> Cutoff discipline: `CUTOFF_DATE = 2021-01-01`. Pre-cutoff trials are a **feature**;
> post-cutoff trials are **ground truth only** and are never used as a feature.

## Evidence dimensions

| # | Dimension | Stage | Signal |
|---|---|---|---|
| 1 | Network proximity | `02` | Hetionet PPI distance to the PD gene module, degree-matched z-score |
| 2 | Clinical maturity | `03` + filters | highest pre-cutoff trial phase (`max_phase_rank`; the trial count is recorded but not scored) |
| 3 | Literature independence | `04` | connected components of a paper co-dependency graph |
| 4 | Safety signal | `05` | openFDA boxed warnings, serious-term counts |
| 5 | **Molecular / pathway** | `08` | drug→target→gene→pathway→PD chain ([docs](docs/MOLECULAR_AGENT.md)) |

Fusion, baselines and ablation: `06`. Figures: `07`.

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env        # optional; every API works unauthenticated
```

Only `NCBI_API_KEY` is read anywhere, and only to raise PubMed's rate limit (script 04).
Open Targets, ClinicalTrials.gov, openFDA and Semantic Scholar are called without
authentication.

## Pipeline order

**Run every script from the repository root** — all paths are relative to the working
directory.

```bash
./venv/bin/python scripts/01_get_pd_candidates.py        # 155 MB Hetionet download
./venv/bin/python scripts/00_exclusion_filter.py         # despite the 00 prefix, runs AFTER 01
./venv/bin/python scripts/02_network_proximity.py        # CPU-heavy
./venv/bin/python scripts/03_clinicaltrials_groundtruth.py   # ~1,500 API calls

# MANDATORY, and not obvious from the filenames: these are the only producers
# of the *_clean.csv files that stages 04/05/06/08 all read.
./venv/bin/python scripts/check_studytype.py      # also runs filter_by_studytype.py (stage 03c)

./venv/bin/python scripts/04_literature_independence.py  # slowest stage; resumable
./venv/bin/python scripts/05_safety_signal.py            # resumable
./venv/bin/python scripts/08_molecular_pathway.py        # resumable + cached
./venv/bin/python scripts/06_vps_fusion.py

# Figure 3 is drawn from a real paper co-dependency graph. Export it first,
# otherwise step 07 SKIPS Figure 3 (it never draws synthetic data).
env -u NCBI_API_KEY S2_SLEEP=2.5 ./venv/bin/python \
    scripts/04b_export_literature_graph.py --compound Droxidopa

./venv/bin/python scripts/07_generate_figures.py
```

Recovery / diagnostic helpers (not part of the normal run):

```bash
# Re-query only the compounds whose ClinicalTrials.gov search failed (stage 03
# has no checkpoint, so a transient outage otherwise needs a full rerun).
./venv/bin/python scripts/03b_resume_failed_searches.py --dry-run

# Independent audit: does each matched trial actually name the compound?
./venv/bin/python scripts/check_intervention_match.py

# Reproducible paired bootstrap CI for AUROC (reads data/vps_scores_v2.csv only)
./venv/bin/python scripts/bootstrap_auroc_ci.py
```

Diagnostic modules, **not part of VPS**: `scripts/trial_role.py` (trial role / intent
annotator, TD-032), `scripts/literature_credibility_agent.py` (architecture 10a,
[docs](docs/LITERATURE_CREDIBILITY_AGENT.md)) and `scripts/conflict_context_agent.py`
(architecture 10d, offline, [docs](docs/CONFLICT_CONTEXT_AGENT.md)):
`./venv/bin/python scripts/conflict_context_agent.py` → `data/conflict_context.json`; and
`scripts/reproducibility_agent.py` (architecture 10e, offline, [docs](docs/REPRODUCIBILITY_AGENT.md))
→ `data/reproducibility.json`; `scripts/clinical_evidence_agent.py` (10c), `scripts/safety_evidence_agent.py` (10f, FAERS) and `scripts/evidence_independence_agent.py` (10g) — all agents share one output envelope, see [docs/AGENT_CONTRACT.md](docs/AGENT_CONTRACT.md) for the run order; and `scripts/completeness_gap_agent.py` (architecture 10h, offline,
[docs](docs/COMPLETENESS_GAP_AGENT.md)) → `data/completeness_gaps.json`.

Evaluation record (offline, ~35 s; [docs](docs/VPS_EVALUATION.md)):
`./venv/bin/python scripts/vps_evaluation_report.py` → `data/vps_evaluation_report.json`.

Stages 02 and 03 are independent of each other; 04, 05 and 08 are independent of each
other. Steps 04, 05 and 08 checkpoint to `data/_*_checkpoint.jsonl` and resume safely
after an interruption — **do not delete those files**, they represent hours of API work.

Step 06 runs with or without the molecular dimension: if `data/molecular_pathway.csv` is
absent it prints a notice and produces the original 4-dimension analysis.

## Cost warning

| Stage | Cost |
|---|---|
| `01` | 155 MB download, held in memory |
| `03` | ~1,500 requests @ 0.34 s (10–20 min) |
| `check_studytype.py` | one request per unique NCT ID |
| `04` | **heaviest** — up to 30 Semantic Scholar calls per compound; hours |
| `05` | ~140 requests |
| `08` | batched + cached; a re-run of the same cohort issues no network calls |
| `02` | CPU-bound, minutes to tens of minutes |

## Dashboard (read-only)

```bash
./venv/bin/python ui/server.py              # http://127.0.0.1:8765  (--port to change)
./venv/bin/python scripts/run_stage.py --status   # tracked runs + freshness (see docs/RUNS_AND_LIVE_UI.md)
./venv/bin/python scripts/run_stage.py 06         # recompute VPS: staged, independently verified, then published
```
An open page polls `/api/status` every 4 s and refreshes itself when a tracked run publishes new
results; stale, modified and failed states are shown in a banner.

Standard library only. Loopback only: `--host` accepts only `127.0.0.1`/`localhost`, and requests
with a non-loopback `Host` header are refused. It reads the persisted artefacts in `data/` and
the docs. Researcher-facing pages: **Overview** (purpose, cohort, primary findings with CIs,
evidence coverage by agent 10h); **Candidates** (filterable, sortable ranking; per candidate a
summary of why it ranks there, supporting / null-or-opposing findings and safety concerns with
source links, and the 10h completeness-and-gaps panel); **Evidence** (every persisted trial,
paper, FDA label and target with its identifier, date and source file); **Mechanism** (10b
drug → target → gene → pathway → PD chain); **Conflicts** (10d); **Compare** (up to 4
candidates); **Validation & Methods**; and **Technical details** (pipeline, agents 10a–10h,
case studies, logs). Identifier links open the public record only when clicked.
Verified in a real (headless) Chrome via the DevTools protocol on 2026-10-15 (D-014, D-022). It never runs a stage, calls an external API, reads `.env`, or writes
to `data/`. Status shows what is on disk ("outputs present"), never "ran successfully".

## Tests

No network, no writes to `data/`:

```bash
./venv/bin/python -m unittest discover -s tests -v
```

461 tests (as of 2026-10-15; record a run for the dashboard with
`./venv/bin/python scripts/record_test_run.py`) covering the molecular agent, ClinicalTrials intervention
matching, candidate flow, VPS integration, the temporal-cutoff / ranking contracts, the
molecular/VPS audit checks, and the read-only dashboard. Notable guarantees
asserted by the suite: adding dimension 5 leaves every previously reported 4-dimension
number unchanged; grid-search weights are selected on training folds only; and known
ClinicalTrials.gov name collisions (chemical class, prodrug, excipient, registry catch-all)
are rejected.

## Repository layout

```
scripts/            pipeline stages + molecular_agent.py library
tests/              offline unit + integration tests
ui/                 read-only dashboard (server.py, index.html, app.js, style.css)
docs/               MOLECULAR_AGENT.md, INTERVENTION_MATCHING.md,
                    CASE_STUDIES.md, REFERENCES.md, LITERATURE_CREDIBILITY_AGENT.md, CONFLICT_CONTEXT_AGENT.md,
                    REPRODUCIBILITY_AGENT.md, COMPLETENESS_GAP_AGENT.md, AGENT_CONTRACT.md, RUNS_AND_LIVE_UI.md, VPS_EVALUATION.md
development_log/    CHANGES.md, ERRORS_AND_BLOCKERS.md
TECHNICAL_DEBT.md   known issues, recorded not fixed
data/               all inputs/outputs/cache — gitignored in full
```

## Before publishing

Read [`TECHNICAL_DEBT.md`](TECHNICAL_DEBT.md).

TD-002 (synthetic Figure 3) and TD-003 (grid search was not true cross-validation) are
both **fixed**. The items that still affect conclusions are:

- **TD-032 — labels (policy P1 applied 2026-10-14).** Three positives whose only label
  trial was not a PD test (Dexmedetomidine, Remifentanil: DBS anaesthesia; Clozapine:
  gene-therapy actuator) are set to 0 via `data/label_role_exclusions.csv`; the ground-truth
  CSV is unchanged. **14 positives / 90.**
- **Current results (2026-10-15, after D-003 safety fix and D-004 missing-evidence rule; see
  `development_log/DECISIONS.md` and `docs/CASE_STUDIES.md` §10):** AUROC VPS_equal 0.700,
  VPS_equal_5d 0.775; 5d − 4d **+0.075, 95% CI [−0.025, +0.176] — not significant**. The label
  measures continued PD trial activity in the ClinicalTrials.gov snapshot of 2026-10-05 (D-010),
  not efficacy. Old outputs are archived in
  `data/_archive_pre_td032_2026-10-14/` and `data/_archive_pre_D003_D004_2026-10-15/`.
- **TD-020 — statistical power.** The corrected cohort had **17 positives in 90
  compounds** (14 after TD-032). Bootstrap 95% CIs on AUROC span roughly ±0.15, and the equal-weight
  5-dimension model's advantage over the 4-dimension model is **+0.059, 95% CI
  [-0.024, +0.150] — not statistically significant.** (That CI could not be reproduced
  exactly on 2026-10-12; recomputations give [-0.024, +0.146] or [-0.025, +0.151]. All span 0.) Do not claim the molecular
  dimension improves performance.
- **Report nested-CV, not in-sample, for any grid-searched variant.** Weights are selected
  on all labelled data, so those AUROCs are in-sample. `data/vps_variant_results.csv`
  marks them with `weights_fitted` and carries `heldout_nested_cv_auroc`; Figure 1 hatches
  them and overlays the held-out value.
- **TD-021 — the literature dimension is not cutoff-bounded either**, and uses only the
  ~30 most recently returned PubMed hits (for Droxidopa, 18 of 26 papers are post-cutoff and
  no pivotal RCT is in the sample).
- **TD-023 / TD-027 — clinical-maturity and pool caveats** found by case-study
  verification (background-therapy, comparator and anaesthesia trial links; compounds first
  trialled after the cutoff cannot be evaluated).
- **TD-031 — missing safety labels (fixed, D-004).** No openFDA label is treated as missing and
  given the neutral rank 0.5 (flagged in `dimensions_missing`), not ranked with the safest.
- **TD-032 — some positive labels are not repurposing trials** (DBS anaesthesia, a
  chemogenetic actuator); see docs/CASE_STUDIES.md §9.
- **TD-006 — the molecular dimension is not cutoff-bounded.** Open Targets serves a current
  snapshot, so residual temporal optimism remains even though the two label-encoding
  datatypes are excluded.
