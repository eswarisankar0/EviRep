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
| 2 | Clinical maturity | `03` + filters | max trial phase, trial count (pre-cutoff only) |
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
./venv/bin/python scripts/check_studytype.py
./venv/bin/python scripts/filter_by_studytype.py

./venv/bin/python scripts/04_literature_independence.py  # slowest stage; resumable
./venv/bin/python scripts/05_safety_signal.py            # resumable
./venv/bin/python scripts/08_molecular_pathway.py        # resumable + cached
./venv/bin/python scripts/06_vps_fusion.py
./venv/bin/python scripts/07_generate_figures.py
```

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

## Tests

No network, no writes to `data/`:

```bash
./venv/bin/python -m unittest discover -s tests -v
```

93 tests: 69 for the molecular agent, 24 for its VPS integration. The integration suite
asserts that adding dimension 5 leaves every previously reported 4-dimension number
unchanged.

## Repository layout

```
scripts/            pipeline stages + molecular_agent.py library
tests/              offline unit + integration tests
docs/               MOLECULAR_AGENT.md
development_log/    CHANGES.md, ERRORS_AND_BLOCKERS.md
TECHNICAL_DEBT.md   known issues, recorded not fixed
data/               all inputs/outputs/cache — gitignored in full
```

## Before publishing

Read [`TECHNICAL_DEBT.md`](TECHNICAL_DEBT.md). Several items affect conclusions —
in particular **TD-002** (Figure 3 is synthetic data titled as a result) and **TD-003**
(the weight grid search is not true cross-validation, so reported AUROCs are
optimistically biased).
