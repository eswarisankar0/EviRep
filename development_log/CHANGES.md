# CHANGES

Chronological record of modifications **actually made** to the EviRep repository.
Only completed, verified changes are recorded here. Planned work lives in the task plan,
not in this file.

---

## 2026-10-05 — Session start

**Baseline inspected (no modifications):** branch `main`, HEAD `576bc7f`, working tree clean,
in sync with `origin/main`.

Confirmed before any edit:
- Four evidence dimensions implemented: network proximity (`02`), clinical maturity
  (`03` + `check_studytype.py` + `filter_by_studytype.py`), literature independence (`04`),
  safety signal (`05`); fused in `06_vps_fusion.py`.
- **Molecular / Pathway Agent absent** — `grep -rniE "pathway|kegg|reactome|wikipathways|gene.ontology|enrich" scripts/`
  returned zero matches.
- **No repository documentation exists** — `find` for `*.md|*.rst|*.txt|*.ipynb|*.pdf|*.docx`
  outside `.git/` and `venv/` returned zero files. There is no README, handoff document,
  methodology note, or architecture doc. Per the task's source-priority rules, the
  **existing implementation and its CSV schemas are therefore the source of truth**;
  no design intent was inferred beyond what the code states.
- `data/` is empty (0 files) — no pipeline output exists in this working copy.

## 2026-10-05 — Molecular / Pathway Agent: library + offline tests

**Added `scripts/molecular_agent.py`** (new, importable library — no leading digit so
the pipeline stage and the tests can both import it).

Implements the chain `DRUG -> TARGET -> GENE -> PATHWAY -> PD MECHANISM` against the
Open Targets Platform GraphQL API. Every API field used was verified by live probe before
being coded against (API v26.9, data version 26.09, probed 2026-10-05); the verified facts
are recorded in the module docstring.

Components:
- `OpenTargetsClient` — on-disk SHA-256-keyed cache, 0.25 s self-throttle, exponential
  backoff with jitter on 429/5xx/network errors, honours `Retry-After`, atomic cache writes.
  GraphQL query errors are *not* retried (they are query defects).
- `normalize_drug_batch` — batched `mapIds` name resolution with **exact** normalised
  name/synonym verification (see E-003).
- `get_drug_mechanisms` / `extract_targets` — ChEMBL mechanisms of action → Ensembl genes,
  carrying per-edge `references` as provenance; de-duplicated and deterministically sorted.
- `get_target_details` — batched (25/request) Reactome pathways + PD association.
- `build_disease_module` — the PD end of the chain: PD-associated genes filtered to allowed
  datatypes and a minimum score, plus their Reactome pathways. Built once per run.
- `filtered_disease_link` — **leakage control**: drops `clinical` and `literature`
  datatypes and ignores Open Targets' composite `score`.
- `build_mechanistic_chain` — tiered DIRECT / INDIRECT / INFERRED / MISSING evidence.
- `score_molecular_plausibility` — `0.6*direct + 0.4*pathway_overlap`, a priori weights,
  configurable, with a human-readable `explanation` and all intermediates retained.
- `compute_confidence` — separate availability axis, so "no link" is distinguishable
  from "could not look".
- `validate_output` — raises `MalformedEvidenceChain`; rejects a non-zero score that has
  no direct/indirect evidence behind it.

**Added `tests/test_molecular_agent.py`** — 61 offline tests, stdlib `unittest`, fully
mocked transport (`FakeSession`), zero network calls. Fixture values are synthetic and are
never written to `data/` nor reported as results.

- **Command:** `./venv/bin/python -m unittest discover -s tests -v`
- **Result:** `Ran 61 tests ... OK` (0 failures, 0 errors), 0.019 s.

Covers all eleven areas required by the task: imports, syntax, data schema, drug
normalization, target extraction, pathway extraction, evidence/provenance structure,
scoring, missing-data behaviour, API-failure behaviour, determinism/reproducibility —
plus caching/batching economy and leakage control.

**Added `requirements.txt`** — the repository previously had no dependency metadata at all.

## 2026-10-05 — Pipeline stage 08 + two defects found by running it

**Added `scripts/08_molecular_pathway.py`** — resumable pipeline wrapper following the
conventions already used by scripts 04/05 (append-only JSONL checkpoint, `tqdm`, relative
`data/` paths, run from repo root). Adds `--compounds`, `--limit`, `--input`, `--dry-run`,
`--fresh`, `--no-cache` and weight overrides so small controlled runs are possible without
touching the full cohort. Refuses to proceed if the PD module comes back empty, rather than
emitting zeros that would read as evidence of absence.

Outputs: `data/molecular_pathway.csv` (tabular, for step 06),
`data/molecular_pathway_evidence.jsonl` (full chains), `data/_molecular_checkpoint.jsonl`.

**Fixed `scripts/molecular_agent.py` — E-005** (HTTP 400): `Drug.synonyms`/`tradeNames` are
`[{label, source}]` objects, not strings. Query now sub-selects them; new `_alias_labels()`
extracts labels. Found by running the stage, not by inspection.

**Fixed `scripts/molecular_agent.py` — E-006** (circular pathway evidence): added
`MolecularAgentConfig.module_datatypes`, excluding `affected_pathway` from PD-module
membership so pathway annotation is not counted twice. Caffeine's pathway component fell
0.8333 → 0.3333 as a result.

**Added `requirements.txt`, `.env.example`.** `.env` and `data/` (hence the API cache) were
already covered by the existing `.gitignore` — verified with `git check-ignore -v`; no
`.gitignore` change was needed.

- **Command:** `./venv/bin/python -m unittest discover -s tests`
- **Result:** `Ran 69 tests ... OK`.
- **Command:** `./venv/bin/python scripts/08_molecular_pathway.py --compounds
  "Ropinirole,Rasagiline,Isradipine,Caffeine,NotARealDrugXyz" --out data/sample_... `
- **Result:** 5/5 scored, 0 errors, 4/5 resolved to ChEMBL, 5 API requests + 10 cache hits.

## 2026-10-05 — VPS fifth-dimension integration

**Modified `scripts/06_vps_fusion.py`** (the only substantive change to pre-existing code).

- Added a **dimension registry** (`BASE_DIMENSIONS`, `ALL_DIMENSIONS`, `MOLECULAR_CSV`).
  The four dimensions had been hardcoded in six separate places; a future agent now needs
  one registry entry plus a loader.
- `load_molecular()` — returns `None` if `data/molecular_pathway.csv` is absent, so step 06
  still runs the original 4-dimension analysis unchanged. Validates required columns.
- `merge_dimensions(..., molecular=None)` — optional merge, renaming the agent's
  `confidence` to `molecular_confidence` to avoid collision.
- `impute_molecular()` — **new, separate from `impute_missing`**: a 0.0 produced by the
  agent is a real measurement and is preserved; only compounds absent from the CSV are
  median-imputed, matching the existing convention. Returns the imputed count, which
  `main()` prints rather than hides.
- `build_standardized_scores()` — adds `r_molecular` (percentile rank, not inverted).
- `run_ablation(df, weights, dims=None, label=None)` — generalised over `dims`. The default
  reproduces the original 4-dimension behaviour **including the exact row label**.
- `main()` — adds `VPS_equal_5d`, `VPS_grid_5d`, `VPS_molecular_only`, a 5-dimension grid
  search, and `data/ablation_results_5d.csv`. The existing `VPS_equal` / `VPS_grid_4d` /
  `VPS_grid_3d` computations are untouched.
- Now also writes `data/vps_variant_results.csv` (previously these metrics were printed
  only), so figures can be generated from measured values.
- **Bug fix (latent, now reachable):** `compute_weighted_vps` raised an opaque
  `AttributeError` when `cv_grid_search_weights` returned `None` (possible when every CV
  fold is single-class). It now raises a named error, and `main()` falls back to equal
  5-dim weights with a printed notice. Found by `test_grid_search_handles_five_dimensions`.

**Modified `scripts/07_generate_figures.py`** — figures 1 and 2 now read measured metrics
from the CSVs script 06 writes, instead of hardcoded AUROC literals. Fixed only because
the molecular dimension could not otherwise be plotted without hardcoding a new number,
i.e. without fabricating a result. Added `_read_metrics()` (clear failure if the metrics
file is missing) and `_wrap()`; axis limits now derive from the data; a 5-dimension
ablation figure is emitted when `data/ablation_results_5d.csv` exists.
**Figure 3 was deliberately left untouched** — its synthetic reconstruction is a separate
pre-existing issue, recorded as TECHNICAL_DEBT TD-002.

**Added `tests/test_vps_integration.py`** — 24 tests. The load-bearing one is
`test_four_dim_scores_identical_with_and_without_molecular`, which asserts via
`pd.testing.assert_series_equal` that adding dimension 5 changes no previously reported
4-dimension number.

**Added `README.md`** (pipeline order, cost warnings, the non-obvious mandatory position of
`check_studytype.py` / `filter_by_studytype.py`), **`docs/MOLECULAR_AGENT.md`**, and
**`TECHNICAL_DEBT.md`** (15 recorded issues, 13 left unfixed by design).

### Tests actually executed
- `./venv/bin/python -m unittest discover -s tests` → **`Ran 93 tests ... OK`**.
- End-to-end smoke of scripts 06 and 07, run in a scratchpad working directory with
  synthetic inputs so **nothing synthetic was written into the project's `data/`**:
  - without `molecular_pathway.csv` → 4-dimension analysis, as before.
  - with it (36/40 coverage) → 5-dimension variants + `ablation_results_5d.csv`; the
    4-dimension numbers printed identically in both runs
    (`VPS_equal` 0.838, `VPS_grid_4d` 0.999, `VPS_grid_3d` 0.999).
  - script 07 produced all four PNGs from measured CSVs.
- Live 5-compound sample of script 08 (see previous entry).

> The smoke-test AUROC values above are artifacts of a synthetic fixture and are **not**
> research results. No real-cohort evaluation of the molecular dimension has been run,
> because `data/` contains no pipeline outputs (TD-005).

### Reconciliation against `git status`
Tracked files modified: `scripts/06_vps_fusion.py`, `scripts/07_generate_figures.py` — both
intended, no others. New untracked files: `scripts/molecular_agent.py`,
`scripts/08_molecular_pathway.py`, `tests/test_molecular_agent.py`,
`tests/test_vps_integration.py`, `README.md`, `TECHNICAL_DEBT.md`, `requirements.txt`,
`.env.example`, `docs/MOLECULAR_AGENT.md`, `development_log/*`. No secrets committed
(`.env` absent and gitignored); `data/` including the API cache is gitignored in full.
**No commit was made** — no push or commit was requested.

## 2026-10-05 — Candidate-flow fix (TD-010) before the real pipeline run

**Modified `scripts/02_network_proximity.py`** — `load_data()` now reads
`data/pd_candidates_filtered.csv` instead of the unfiltered `data/pd_candidates.csv`;
module docstring corrected to match.

**Modified `scripts/03_clinicaltrials_groundtruth.py`** — `main()` now reads
`data/pd_candidates_filtered.csv`.

Measured against the real Stage 01/00 outputs now present in `data/`: 1,524 → 1,483
candidates (41 excluded), of which 39 have Hetionet CbG targets and were therefore being
scored by stage 02 unnecessarily (1,361 → 1,322 compounds scored). Stage 03 was issuing up
to 41 unnecessary ClinicalTrials.gov query sets, which also propagated excluded compounds
into stages 04/05/08 via `clinical_maturity_precutoff_clean.csv`.

No prior `data/network_proximity.csv` existed, so the stage-02 RNG-stream shift this causes
is not a reproducibility regression; the filtered input is the baseline for the real run.
Full analysis in TECHNICAL_DEBT.md TD-010.

**Added `tests/test_candidate_flow.py`** — 11 static regression tests (AST-based, no data
or network required) so the bypass cannot silently reappear.

- **Command:** `./venv/bin/python -m unittest discover -s tests`
- **Result:** `Ran 104 tests ... OK`.

Not added to ERRORS_AND_BLOCKERS.md: corrected before producing any research output, so it
never caused an actual error. TD-010 reclassified LOW → MEDIUM and marked FIXED.

## 2026-10-05 — REAL PIPELINE RUN (no synthetic data)

All counts below come from actual command output. Stage logs retained in the session
scratchpad.

### Stage 02 — network proximity · COMPLETED + VALIDATED
`./venv/bin/python scripts/02_network_proximity.py`

| | |
|---|---|
| PPI network | 15,165 nodes / 147,164 edges (Hetionet GiG) |
| PD-associated genes | 637 total, 594 present in PPI |
| Drugs with CbG targets | 1,389 |
| Candidates in (filtered) | **1,483** |
| Scored | **1,314** |
| Skipped — no targets | 161 |
| Skipped — no network distance | 6 |
| Skipped — insufficient random samples | 2 |

Validation: `data/network_proximity.csv`, 1,314 rows, 0 NaN `proximity_z`, range
−6.936 … +3.990 (median −0.050), `n_random` 98–100. **Zero excluded compounds present in
the output**, confirming the TD-010 fix end to end. The scored count matches the TD-010
prediction exactly (1,322 candidates with targets − 6 no-distance − 2 insufficient-random
= 1,314).

Biological sanity check (not a result, a smoke signal): the most PD-proximal compounds are
Methamphetamine (−6.94), Dopamine (−6.37), Furazolidone (−5.82), Isocarboxazid (−5.53),
Fluphenazine (−5.51) — i.e. dopaminergic agents, MAO inhibitors and D2 antagonists. The
proximity measure is recovering dopaminergic/monoaminergic biology, as expected.

> `N_RANDOM = 100` (TD-011, the script's own "quick test" setting) was left unchanged — no
> methodology was altered during this run.

### Data-integrity cross-check — Hetionet artefact
`data/hetionet_edges.csv` / `hetionet_nodes.csv` verified against the published description
in reference M1 (Himmelstein et al., eLife 2017, PMID 28936969):

| | Local file | Paper |
|---|---|---|
| Edges | 2,250,197 | 2,250,197 ✔ |
| Nodes | 47,031 | 47,031 ✔ |
| Metaedge types | 24 | 24 ✔ |
| Node types | 11 | 11 ✔ |

Exact match on all four — the downloaded artefact is the genuine Hetionet v1.0.0 release.

### References — `docs/REFERENCES.md` created
The repository had **no** pre-existing references, citations, or bibliography of any kind,
so there was nothing to review or correct. Seven methodological references were established
from what the code demonstrably uses and **each was verified live against the NCBI
E-utilities API**, with the returned `ArticleTitle` string-matched to the intended title;
PMIDs/DOIs/journal/volume/pages are copied from API responses, not written from memory.

Verified: M1 Hetionet (28936969), M2 network proximity (26831545), M3 Open Targets
(36399499), M4 Reactome (37941124), M5 ChEMBL (37933841), M6 Disease Ontology (30407550),
M7 NCBI E-utilities (37994677).

Claim-support checked by reading abstracts for the two load-bearing ones: Guney et al.
describes a "drug-disease proximity measure" that works "by correcting for the known biases
of the interactome" (the degree-matched null stage 02 builds) and explicitly discusses
Parkinson's; Himmelstein et al. matches the downloaded artefact exactly.

Honest attribution note recorded in the file: stage 02 contains **no** citation, so M2 is
the canonical published description of the method implemented, not evidence the original
author consulted it. Semantic Scholar's platform paper is not indexed in PubMed and is
therefore cited as an API URL only — no bibliographic details were invented.

### Stage 03 — ClinicalTrials.gov ground truth · COMPLETED + VALIDATED
`./venv/bin/python scripts/03_clinicaltrials_groundtruth.py`

| | |
|---|---|
| Candidates queried (filtered) | 1,483 |
| Rejected by the client-side PD check | 352 |
| Pre-cutoff trial rows (feature) | 425 → **147** unique compounds |
| Post-cutoff trial rows (ground truth) | 174 → **93** unique compounds |

Validation: cutoff discipline holds exactly — pre-cutoff `max(first_posted)` = 2020-12-24,
post-cutoff `min(first_posted)` = 2021-01-13, straddling `CUTOFF_DATE = 2021-01-01` with no
overlap. Zero excluded compounds present in either file (TD-010 fix holds through stage 03).

### check_studytype.py + filter_by_studytype.py · COMPLETED
459 unique NCT IDs checked: 415 INTERVENTIONAL, 44 OBSERVATIONAL. Trials kept
(INTERVENTIONAL with a DRUG/BIOLOGICAL arm): **326 / 459**.

| File | Before → after |
|---|---|
| `clinical_maturity_precutoff_clean.csv` | 147 → **141** unique compounds (evaluable pool) |
| `ground_truth_postcutoff_clean.csv` | 93 → **67** unique compounds (positives) |

### Stage 08 — Molecular / Pathway Agent, REAL COHORT · COMPLETED + VALIDATED
`./venv/bin/python scripts/08_molecular_pathway.py`

| | |
|---|---|
| Compounds processed | **141** |
| Errors during scoring | **0** |
| Resolved to ChEMBL | **140 / 141** (unresolved: `Alpha-Linolenic Acid`) |
| API requests / cache hits | 213 / 48 |
| With ≥1 ChEMBL target | 107 |
| With a **permitted** (non-leaky) direct PD gene link | **67** |
| With pathway overlap | 74 |
| Score > 0 | 94 · Score = 0 | 47 |

Score: mean 0.285, median 0.239, max 0.854.
Confidence: 1.0 for 107 compounds, 0.5 for 33, 0.0 for 1.
Evidence tiers across the cohort: 708 direct, 551 indirect, 671 inferred, 34 missing.

Zero-score breakdown — the score/confidence separation working as designed: of the 47
zero-score compounds, **34 are evidence-ABSENT** (no ChEMBL target; confidence 0.5) and
**13 are measured zero** (targets retrieved, no qualifying PD link; confidence 1.0).

PD module used: **108 genes / 263 Reactome pathways**, led by PRKN, PINK1, ATP13A2, DNAJC6,
LRRK2, SNCA, PLA2G6 — the canonical monogenic PD genes.

**Bug found and fixed by inspecting the real output — `n_direct_disease_links`.**
`flatten()` counted every `disease_links` row, including rows whose evidence was entirely
`clinical`/`literature` and therefore scored 0 under the leakage exclusion. It reported
**107** compounds with a "direct PD gene link" when only **67** have permitted evidence
(e.g. Riluzole: 10 rows, only 4 with permitted evidence). Fixed to count
`score_allowed_datatypes > 0`, with `n_disease_link_rows` added for transparency. The CSV
was regenerated from the existing checkpoint — **no re-querying**. The *score* was never
affected; only this descriptive column was.

**Verified, not a bug: identical scores within drug classes.** Zonisamide / Lidocaine /
Quinidine / Riluzole / Lamotrigine all score 0.854442 because ChEMBL gives them an
*identical* 10-gene sodium-channel target set (SCN1A–SCN11A); likewise the ACHE inhibitors
(Galantamine, Isoflurophate, Pyridostigmine, Donepezil) and the α1-adrenergics (Midodrine,
Terazosin, Phenylephrine). Confirmed by comparing target sets directly. This is an inherent
property of a target-based score and is recorded as TD-017.

Riluzole's direct component (0.757) traces to **SCN8A `animal_model` = 0.757** — a
permitted, non-leaky datatype, not clinical precedence.

### Stage 05 — safety signal · COMPLETED + VALIDATED
`./venv/bin/python scripts/05_safety_signal.py`

141 compounds; 121 with an openFDA label, 20 without; 40 flagged `boxed_warning`;
`serious_term_count` mean 2.13, max 31. Highest serious-term counts: Naloxone (31),
Codeine (20), Methylprednisolone (17), Oxycodone (17), Clozapine (16), Valproic Acid (16)
— consistent with drugs that genuinely carry boxed warnings.

> TD-014 still applies: `boxed_warning` is detected by key presence, so the 40 count may be
> inflated. Not fixed — out of scope, and it affects only an existing dimension.

### Stage 04 — literature independence · FIRST RUN DISCARDED, re-run in progress
First run completed with exit 0 and reported "0 errors", but produced **corrupted data**:
Semantic Scholar began returning HTTP 429 after ~12 compounds and `fetch_citing_pmids`
silently converted every throttled response into "no citations". Citation edges accrued
only for checkpoint positions 0–11 while 110 later compounds with ≥2 papers got none.
Full diagnosis in ERRORS_AND_BLOCKERS E-009.

**Modified `scripts/04_literature_independence.py`** (retry/backoff honouring `Retry-After`,
`SemanticScholarUnavailable` raised on genuine failure, `S2_STATS` accounting, new
`citation_lookup_failures` / `citation_coverage_complete` columns, end-of-run coverage
report, configurable `S2_SLEEP` defaulting to 2.5 s). Fix unit-tested against a mocked
transport before the re-run. Scientific methodology unchanged — only transport reliability
and failure visibility.

Contaminated outputs preserved as evidence (gitignored):
`data/_literature_checkpoint_THROTTLED_EVIDENCE.jsonl`,
`data/literature_independence_THROTTLED_EVIDENCE.csv`.

**Step 06 was NOT run on the contaminated literature data, and no metric was computed from it.**

### Stage 04 — literature independence · RE-RUN COMPLETED + VALIDATED
`env -u NCBI_API_KEY S2_SLEEP=2.5 ./venv/bin/python scripts/04_literature_independence.py`

| | Corrupted first run | Clean re-run |
|---|---|---|
| Citation edges | 68 | **1,137** |
| Shared-author edges | 748 | 748 (unchanged — that leg never failed) |
| S2 lookups OK | not tracked | 2,391 |
| S2 genuine 404s | not tracked | 24 |
| S2 rate-limit responses | silent | 279, **all recovered by backoff** |
| S2 lookups FAILED | ~2,400 silent | **0** |
| Compounds with incomplete coverage | ~129 (invisible) | **0 / 141** |

The corruption was material, not cosmetic: Terazosin's `independence_ratio` moved
0.542 → 0.167, Ursodeoxycholic acid (absent from the old top-15) became the most
literature-dependent compound at 0.100, and Isradipine fell from rank 1 to rank 8. The
original "least independent" leaderboard was substantially an artefact of processing order.

### Stage 06 — VPS fusion · COMPLETED (real data)
`./venv/bin/python scripts/06_vps_fusion.py`

Evaluable pool **141** compounds; molecular coverage **141/141** (0 imputed), mean molecular
confidence 0.882; **30 positive labels**.

**Measured AUROC / precision@10 / precision@50 — real cohort, no synthetic data:**

| Model | AUROC | P@10 | P@50 |
|---|---|---|---|
| Proximity only (baseline) | 0.613 | 0.2 | 0.30 |
| Publication count only (baseline) | 0.686 | 0.2 | 0.34 |
| Naive unweighted sum (baseline) | 0.727 | 0.3 | 0.38 |
| **Molecular dimension only** | **0.581** | 0.4 | 0.28 |
| VPS equal weights (4 dim) | 0.727 | 0.7 | 0.38 |
| VPS grid-searched (4 dim) | 0.744 | 0.6 | 0.38 |
| **VPS grid-searched (3 dim, no proximity)** | **0.750** | 0.6 | 0.38 |
| VPS equal weights (5 dim) | 0.736 | 0.6 | 0.38 |
| VPS grid-searched (5 dim) | 0.730 | 0.5 | 0.40 |

Grid-searched weights: 4-dim {prox 0.0, clin 0.25, lit 0.5, safety 0.25} (CV 0.743);
3-dim {clin 0.3, lit 0.5, safety 0.2} (CV 0.760);
5-dim {prox 0.0, clin 0.25, lit 0.25, safety 0.25, molecular 0.25} (CV 0.744).

**5-dimension ablation:** full 0.730; without proximity 0.730; without clinical 0.717;
without literature 0.686; without safety 0.728; **without molecular 0.727** (P@10 rises
0.5 → 0.7).

> **The molecular dimension did NOT improve performance on this cohort.** Alone it reaches
> AUROC 0.581, barely above chance. Added to the grid-searched 4-dim model it *reduces*
> AUROC 0.744 → 0.730; added to the equal-weight model it changes it 0.727 → 0.736, within
> noise at n=141/30 positives. Removing it from the 5-dim model costs 0.003 AUROC and
> *gains* 0.2 precision@10. No improvement is claimed. Weights were not tuned to improve
> this result.

### Stage 07 — figures · COMPLETED (from measured CSVs)
All four PNGs regenerated from `baseline_results_v2.csv`, `vps_variant_results.csv`,
`ablation_results_v2.csv`, `ablation_results_5d.csv`. Figure 3 remains the pre-existing
synthetic reconstruction (TD-002) — untouched and still must not be published as-is.

### Case-study verification · COMPLETED → `docs/CASE_STUDIES.md`
Candidates taken from the real 2026-10-05 ranking (`VPS_grid_3d`). All trial records fetched
from the ClinicalTrials.gov API; all PMIDs/DOIs/statistics copied from PubMed API responses.

- **Donepezil (rank 1)** — identifier GENUINE. Two RCTs verified, **both missed their primary
  endpoints**: DASH-PD (PMID 35860451, n=201, 4 yr) HR 0.609 (95% CI 0.240–1.547, ns) for PDD
  incidence; Mancini 2019 (PMID 31675664, n=49 crossover) no effect on sway (p=0.28) or gait
  variability (p=0.31). Genuine research target; **efficacy not demonstrated**.
- **Melatonin (rank 4)** — identifier GENUINE. SR/MA of 8 RCTs, n=409 (PMID 40588412):
  PSQI −1.75 (p=0.004) and ESS −1.07 (p=0.009) improved, but **no significant effect on
  objective sleep parameters** and RBDSQ ns. Narrow, partly subjective symptomatic benefit;
  no disease modification.
- **Lisuride (rank 6, label 0)** — genuine; label 0 only because its three PD trials predate
  the cutoff. Illustrates that the ground truth encodes "newly trialled after 2021", not
  "works in PD" (relates to TD-004).
- **Norepinephrine (2), Phenol (3), Dopamine (5)** — **IDENTIFIER ARTEFACTS**, see E-010.

### New diagnostic · `scripts/check_intervention_match.py`
Read-only; changes no stage's behaviour and no existing output. Verifies, per
(compound, trial) pair, whether any intervention actually names the matched compound.
Writes `data/intervention_match_check.csv`.

Result over all 451 pairs: 255 MATCHED + 3 MATCHED_PARTIAL, **177 NAME_NOT_FOUND (39%)**,
16 CATCH_ALL_STUDY; 60/178 compounds with no naming trial; **48/141 of the evaluable pool
(34%)** and **7/30 positives (23%)** affected. Recorded as E-010 / TD-018.

### References · `docs/REFERENCES.md`
Seven methodological references verified live against PubMed (title string-matched; PMIDs,
DOIs, journal/volume/pages copied from API responses). Data APIs without a PubMed-indexed
paper are cited by URL only — no bibliographic details invented.

## 2026-10-05 — Final reconciliation

**Tracked files modified (5):** `02_network_proximity.py`, `03_clinicaltrials_groundtruth.py`
(TD-010 fix), `04_literature_independence.py` (E-009 fix), `06_vps_fusion.py` (5th dimension),
`07_generate_figures.py` (data-driven figures). No other tracked file touched.

**New files:** `scripts/molecular_agent.py`, `scripts/08_molecular_pathway.py`,
`scripts/check_intervention_match.py`, `tests/` (3 files, 104 tests), `README.md`,
`TECHNICAL_DEBT.md`, `requirements.txt`, `.env.example`, `docs/` (3 files),
`development_log/` (2 files).

**Tests:** `./venv/bin/python -m unittest discover -s tests` → `Ran 104 tests ... OK`.

**Secrets:** none. `.env` absent; the only match for a key-like pattern is the *documented*
placeholder `your_key` in TD-016, which is the defect being reported, not a credential.

**Synthetic data in `data/`:** none. The `sample_molecular_*` files are output of the real
5-compound **live API** run, not fixtures. All synthetic integration fixtures live in
`tests/` and were executed only in a scratchpad working directory.

**Every metric in this log traces to a command recorded above.** No metric was computed from
the contaminated stage-04 output (E-009) or reported from a smoke test.

**No commit was made** — none was requested.

## 2026-10-05 (afternoon) — ClinicalTrials.gov intervention-collision fix (E-010) + clean rerun

### Code
- **NEW `scripts/intervention_matcher.py`** — pure, deterministic, network-free matching
  library. Policy in `docs/INTERVENTION_MATCHING.md`. Four mutually exclusive outcomes
  (`MATCHED` / `NO_MATCH` / `UNVERIFIABLE` / `API_FAILURE`); only `MATCHED` qualifies.
  Whole-token matching (never raw substrings), control-arm exclusion, ChEMBL-verified
  synonyms with exact-only matching, ambiguous-alias refusal.
- **MODIFIED `scripts/03_clinicaltrials_groundtruth.py`** — Gate 2 (intervention identity)
  added alongside the pre-existing Gate 1 (condition). `search_trials` now returns
  `(studies, ok)` with retry/backoff, so an API failure is no longer silently returned as
  `[]`. Writes a full decision audit to `data/clinicaltrials_match_audit.csv`.
- **NEW `scripts/03b_resume_failed_searches.py`** — targeted resume for compounds whose
  search failed, so a transient outage does not force a full rerun.
- **NEW `tests/test_intervention_matcher.py`** — 46 tests built from verbatim live API
  payloads. Suite total: **151 tests, all passing**.

### Defects found and fixed during this work (all by running, not inspection)
| ID | Defect | Resolution |
|---|---|---|
| E-010 | `query.intr` expansion credited compounds with other drugs' trials | Gate 2 |
| E-011 | observational studies misreported as `API_FAILURE` | reclassified `UNVERIFIABLE` |
| E-012 | ChEMBL synonyms reintroduced class collisions (`citalopram`→Escitalopram, `doxycycline`→Tetracycline — the latter a **false positive label**) | ambiguous-alias filter |
| — | Mannitol matched droxidopa trials via the **placebo arm's** `otherNames` (inert filler) | control-arm exclusion |

### Clean rerun (stage 02 NOT recomputed — no ClinicalTrials dependency)
`03 → 03b → check_studytype → filter_by_studytype → 04 → 05 → 08 → 06 → 07`.
Stages 04/05/08 resumed from existing checkpoints (their per-compound values depend on
compound identity, not trial matching) — **0 new API calls**, verified to cover the new pool.

| Measure | Contaminated | Corrected |
|---|---|---|
| Accepted compound-trial links | not gated | 274 |
| Rejected — wrong intervention | 0 (no gate) | 289 |
| Rejected — wrong condition | 352 | 352 |
| Unverifiable | — | 36 |
| API failures remaining | — | **0** |
| Evaluable compounds | 141 | **90** |
| Positive labels (in pool) | 30 | **17** |

Diagnostic (`check_intervention_match.py`), independent of the matcher:
unsupported trial links **177/451 (39%) → 7/252 (2.8%)**; compounds with no naming trial
**60/178 → 1/114**; and all 7 residuals are explained by legitimate ChEMBL trade
names/synonyms. **Unexplained collisions: NONE.**

### Phase 11 leakage audit (all verified on final data)
temporal split intact (pre max 2020-11-25 < 2021-01-01 ≤ post min 2021-01-13); zero
trial overlap pre/post; post-cutoff trials never used as a feature; molecular dimension
excludes `clinical` + `literature` datatypes (confirmed none used); zero imputation
touching labels; class balance 17/90 = 0.189.

## 2026-10-05 (evening) — P0 Figure 3 + P1 grid-search leakage

### P0 — Figure 3 replaced with real data
`scripts/07_generate_figures.py::figure3_droxidopa_graph` generated a RANDOM graph
(`np.random`, hardcoded `cluster_sizes=[8,6,5,4,3]`) and was captioned "26 Papers -> 5
Independent Evidence Clusters". The real Droxidopa value is **16** clusters, so the figure
also misstated the result it claimed to show.

- **NEW `scripts/04b_export_literature_graph.py`** — re-derives one compound's paper
  co-dependency graph using stage 04's own functions and persists real nodes/edges.
  Contains a **provenance guard**: it refuses to write unless the re-derived aggregate
  counts match the stage-04 checkpoint exactly.
- Run: `env -u NCBI_API_KEY S2_SLEEP=2.5 ./venv/bin/python scripts/04b_export_literature_graph.py --compound Droxidopa`
  → `PROVENANCE CHECK PASSED`; derived {papers 26, components 16, author edges 4,
  citation edges 10} == checkpoint exactly. Wrote `data/literature_graph_droxidopa.json`
  (26 nodes, 14 edges, component sizes `[10, 2, 1×14]`).
- **MODIFIED `scripts/07_generate_figures.py`** — `figure3_literature_graph()` draws only
  from that JSON, asserts node/component counts match, distinguishes shared-author (red,
  solid) from citation (blue, dashed) edges, and states the real counts in the caption.
  If the JSON is absent it **skips** the figure rather than drawing anything synthetic.
  Output renamed `data/figure3_droxidopa_literature_graph.png`; the old synthetic PNG was
  deleted. No figure in this repository now contains synthetic or hardcoded values.

### P1 — grid-search cross-validation leakage fixed (TD-003)
`cv_grid_search_weights` bound `train_idx` but never used it: every candidate weight vector
was scored on each **test** fold and the maximum taken, so selection saw the data it was
measured on.

- **MODIFIED `scripts/06_vps_fusion.py`** — added `_build_weight_grid` and
  `_best_weights_on`; `cv_grid_search_weights` now computes a genuine **nested** estimate
  (weights chosen on the TRAINING fold, evaluated on the held-out fold) and returns that as
  the performance figure. Final model weights are still chosen on all labelled data because
  one model must be emitted, but that model's in-sample AUROC is recorded separately as
  `selected_model_in_sample_auroc` and must not be reported as performance.
  **Equal-weight variants were not modified** — they involve no selection.
- **Effect (this is large):** reported CV AUROC for grid-searched models falls to the
  honest nested value: 4-dim 0.706 → **0.631**, 3-dim 0.716 → **0.648**,
  5-dim 0.743 → **0.660**.
- **Tests:** `TestGridSearchNoLeakage` (6 tests) — asserts `df.iloc[train_idx]` is used,
  that on pure noise the nested estimate is both lower than in-sample and near chance, that
  the log separates the two quantities, and that the equal-weight path is unchanged.

### Validation actually executed
- `./venv/bin/python -m unittest discover -s tests` → **`Ran 157 tests ... OK`**
- All scripts parse; `molecular_agent` and `intervention_matcher` import.
- Integrity on `data/vps_scores_v2.csv`: 90 rows, 0 duplicate compounds, **0 NaN/inf in any
  scoring or label column** (the only 32 NaN are `direct_component`/`pathway_component` for
  the 16 compounds with no ChEMBL target — correctly "absent", not zero), labels align
  exactly with ground truth ∩ pool, temporal split intact
  (2020-11-25 < 2021-01-01 ≤ 2021-01-13), 0 pre/post trial overlap, and **0 pre/post links
  absent from the post-fix accepted audit** (no contaminated data reused). Phenol,
  Norepinephrine and Dopamine are absent from the pool.

## 2026-10-05 (final audit) — pre-publication regression audit

Verified against the pre-Molecular baseline (HEAD `576bc7f`):
- `05_safety_signal.py`, `00_exclusion_filter.py`, `01_get_pd_candidates.py`,
  `check_studytype.py`, `filter_by_studytype.py` are **byte-identical** (`git diff --quiet`).
- `02_network_proximity.py`: ONLY the input path changed
  (`pd_candidates.csv` → `pd_candidates_filtered.csv`, TD-010). Grep confirms no change to
  `N_RANDOM`, `RANDOM_SEED`, degree-matching, `random.choice`, or the z-score.
- `04_literature_independence.py`: changes are transport/reporting only. Grep confirms no
  change to edge creation (`a1 & a2`, citation), `connected_components`,
  `independence_ratio`, `effective_independent_count`, or the PubMed query.
- `03_clinicaltrials_groundtruth.py`: `is_actually_pd` gate and `CUTOFF_DATE` comparisons
  preserved; Gate 2 added.
- `02`, `04`, `05` have **no** import of the molecular agent. `03` imports it only as a
  ChEMBL synonym source; it reads no molecular score and no study label.

### Fixes applied during this audit
| File | Change | Reason |
|---|---|---|
| `scripts/molecular_agent.py` | removed unused `asdict`, `Iterable` imports | dead code |
| `scripts/03_clinicaltrials_groundtruth.py` | removed unused `_alias_labels` import | dead code |
| `scripts/04_literature_independence.py` | `_valid_api_key()` rejects placeholder keys | E-008/TD-016 was a *verified* failure that silently emptied the literature dimension |
| `scripts/06_vps_fusion.py` | `vps_variant_results.csv` gains `weights_fitted` + `heldout_nested_cv_auroc` | in-sample grid AUROCs were reported beside unfitted ones with no marker |
| `scripts/07_generate_figures.py` | Figure 1 hatches fitted models, suffixes "(in-sample)", overlays held-out nested-CV | same risk in the publication figure |

Tests: `Ran 160 tests ... OK` (3 new API-key guard tests).

## 2026-10-12 — Read-only dashboard, molecular/VPS audit, case-study verification

**Baseline (before any edit):** branch `main`, HEAD `576bc7f`; 25 staged files from the
2026-10-05 work, unstaged README edits and untracked `tests/test_temporal_and_ranking.py`
(user work — preserved, not modified). `./venv/bin/python -m unittest discover -s tests`
→ `Ran 176 tests ... OK`. No commit, push or `git` state change was made in this session.

| ID | Files | Previous behaviour / defect | Change and rationale | Verification | Status |
|---|---|---|---|---|---|
| C-01 | `ui/server.py`, `ui/index.html` (new) | No UI; pipeline state only visible in terminal output | Stdlib-only, read-only local dashboard: Pipeline, Agents & Data Sources, Drug Explorer, Case Studies, Validation. File-derived status only; no external calls, no `.env`, credential values redacted, GET-only, 127.0.0.1 | 23 tests; live curl against real `data/`; page JS executed in Node against the live API. Not viewed in a browser (L-002) | PASS |
| C-02 | `tests/test_ui.py` (new) | — | Missing/partial/stale artefacts, malformed rows, non-finite values, redaction, no sockets, no third-party resources, read-only server, path traversal, registry ↔ script-source consistency | Found and fixed a crash on a non-string `drug` field in the evidence JSONL before release | PASS |
| C-03 | `tests/test_molecular_vps_audit.py` (new, written by an audit sub-agent, reviewed) | Untested: target-retrieval API failure, corrupt cache, `flatten`, stage 08 `--fresh` | 12 offline tests | Included in the 211 | PASS |
| C-04 | `scripts/08_molecular_pathway.py` | `--fresh` emitted stale checkpoint records (E-013) | Collect keeps the LAST record per drug; checkpoint never truncated | `TestStep08FreshRun` (was expectedFailure) passes; current outputs unaffected (no duplicate drugs) | PASS |
| C-05 | `scripts/07_generate_figures.py`; `data/figure2_ablation*.png`, `data/figure3_droxidopa_literature_graph.png` regenerated | Fig 2 compared an unmarked in-sample fitted bar with equal-weight bars; Fig 3 said "independent evidence clusters" and reused colours across 16 components | Fig 2: hatch + "(in-sample)" + footnote on weighting. Fig 3: "connected components (publication clusters, not independent trials)", singletons grey, sample caveat. Only these figures regenerated (Fig 1 unchanged); old PNGs copied to the session scratchpad | Images inspected; Fig 3 asserts on node/component counts still pass | PASS |
| C-06 | `TECHNICAL_DEBT.md` | — | TD-020 addendum; new TD-021 … TD-028 | Each entry cites the file:line, record or computation behind it | PASS |
| C-07 | `development_log/ERRORS_AND_BLOCKERS.md` | L-001 stale | L-001 SUPERSEDED note (original kept); E-013, E-014, E-015, L-002 | — | PASS |
| C-08 | `docs/CASE_STUDIES.md` | NCT00605683 mis-cited as lisuride; melatonin "objective null" and "corroborating" overstated; CI inconsistent | Corrections marked inline with date; new §7 Droxidopa, §8 seven-candidate records | Every new identifier copied from API responses (≈62 requests, all HTTP 200) | PASS |
| C-09 | `docs/REFERENCES.md`, `docs/MOLECULAR_AGENT.md`, `README.md` | Test counts stale; confidence table grouped evidence-absent with "found no link" | §6 re-verification audit; corrected counts/table; dashboard section; new caveats | 13/13 PMIDs re-verified | PASS |

**Recomputed, not changed:** AUROC VPS_equal_5d 0.7474, VPS_equal 0.6886, diff +0.0588,
AUPRC 0.4790 (from persisted `data/vps_scores_v2.csv`); 4-dimension columns identical with
and without dimension 5. Persisted metrics were not overwritten.

**External requests this session:** 2 reachability probes (PubMed, ClinicalTrials.gov) +
≈62 verification requests by case-study sub-agents (PubMed E-utilities with
`env -u NCBI_API_KEY`; ClinicalTrials.gov v2). No Open Targets, Semantic Scholar or openFDA
call; no pipeline stage was run.

**Tests:** `./venv/bin/python -m unittest discover -s tests` → `Ran 211 tests ... OK`.
`data/` changes: only the three regenerated figure PNGs.

## 2026-10-13 — Dashboard security / accessibility audit

**Baseline:** working tree as left on 2026-10-12 (nothing committed); `Ran 211 tests ... OK`.
No commit, push, discard or pipeline run; no external API request; `data/` not modified.

| ID | Files | Previous behaviour / defect | Change and rationale | Verification | Status |
|---|---|---|---|---|---|
| C-10 | `ui/server.py` | Error responses exposed absolute paths; non-loopback bind allowed; any Host header served; graph path built from raw query; weak CSP/headers; Python version in `Server`; HTML 501 pages; NaN emitted | Class-only errors + `sanitize()` on every JSON payload; `--host` restricted to 127.0.0.1/localhost; Host-header allowlist (403); slug-whitelisted graph path; realpath check on `/figure/`; strict CSP + nosniff/DENY/no-referrer/COOP/CORP; JSON 405 for all non-GET; `allow_nan=False` (TD-029) | `TestSecurityHardening` (17 tests); live probes: traversal/`.env`/source paths 404, foreign Host 403, POST/PUT/DELETE/PATCH/OPTIONS 405, `lsof` → `127.0.0.1:8765` only | PASS |
| C-11 | `ui/index.html`, `ui/app.js` (new), `ui/style.css` (new) | Inline script/style required `'unsafe-inline'`; Drug Explorer list never rendered (listener race); malformed hash hung the page; click-only list; low-contrast badges | JS/CSS externalised; views return `{html, after}` and listeners attach after insertion; safe hash decoding + stale-render guard; list items are links; `aria-current`, skip link, focus ring; WCAG-AA token colours; in-app links between docs | `TestAccessibleContrast`; Node run of `ui/app.js` against the live server (list 400 items, filter "dopa" → 4, empty state, selection). **Not seen in a browser (L-003)** | PASS (visual check outstanding) |
| C-12 | `tests/test_ui.py` | — | 19 new tests (above); third-party-resource and confidence-wording checks extended to `app.js`/`style.css` (strengthened, none weakened) | — | PASS |
| C-13 | `TECHNICAL_DEBT.md`, `ERRORS_AND_BLOCKERS.md`, `README.md` | — | TD-029, TD-030; E-016, L-003; README dashboard/test count | — | PASS |

**Exposure sweep (live server, real data):** 16 static/doc/API routes + `/api/compound` for all
1,327 compounds — no absolute path, username, credential pattern or `.env` value in any
response (no `.env` exists); 6 credential-like values in docs shown as `[REDACTED]`.

**Tests:** `./venv/bin/python -m unittest discover -s tests` → `Ran 230 tests ... OK`;
`py_compile` and `node --check ui/app.js` clean; `git diff --check` clean.

## 2026-10-13 — Research sprint: safety missingness, label roles, reproducible CI, agent 10a

**Baseline:** working tree as left after the dashboard audit (nothing committed);
`Ran 230 tests ... OK`; md5 of every `data/` file recorded. The pre-change stage 06 was run in
a scratch copy of its inputs and reproduced all 8 persisted outputs **byte-for-byte**.

| ID | Files | Finding / defect (evidence) | Change and rationale | Verification | Status |
|---|---|---|---|---|---|
| C-14 | `scripts/05_safety_signal.py`, `scripts/06_vps_fusion.py`, `tests/test_safety_missingness.py` (new) | No openFDA label → `serious_term_count=0` → best `r_safety` (7/90, TD-031) | 05 writes null; 06 `mask_unlabelled_safety()` + `safety_label_missing`; missing follows the existing median convention (no new policy) | 15 tests (8 fail on pre-fix code); old vs new 06 in scratch: metric files byte-identical, scores unchanged (median risk = 0) | PASS — policy OPEN |
| C-15 | `scripts/bootstrap_auroc_ci.py` (new), `tests/test_bootstrap_ci.py` (new) | CI not reproducible (E-015) | Versioned paired percentile bootstrap; seed, n, skips recorded; read-only unless `--out` | 7 tests; two runs identical; +0.0588 [−0.0241, +0.1456] | PASS |
| C-16 | `scripts/04_literature_independence.py`, `tests/test_literature_date_bound.py` (new) | Literature not cutoff-bounded (TD-021) | Opt-in `search_pmids(max_date=…)` (PubMed `pdat`); default query byte-identical; not wired into `main()` | 4 tests | PASS — enforcement OPEN (B-002) |
| C-17 | `scripts/trial_role.py` (new), `tests/test_trial_role.py` (new), `tests/fixtures/ctgov_NCT0*_role.json` (new) | Gate 2 checks identity, not role (TD-023/TD-032) | Diagnostic role annotator; rules refined after first real run exposed comparator-typing and nerve-block false calls | 19 tests incl. 2 real registry records | PASS (diagnostic, not wired) |
| C-18 | `scripts/literature_credibility_agent.py` (new), `tests/test_literature_credibility_agent.py` (new), `docs/LITERATURE_CREDIBILITY_AGENT.md` (new); outputs `data/literature_credibility_droxidopa.json`, `data/cache/pubmed_efetch_droxidopa.xml` (new) | Architecture 10a missing | Deterministic credibility agent (PublicationType/MeSH; unknown ≠ 0; efficacy never assessed; not in VPS). "Comparative Study" mapping removed after the real run mis-tiered PMID 41520443 | 21 tests; offline rerun identical | PASS (diagnostic, not integrated) |
| C-19 | `docs/CASE_STUDIES.md` | Dexmedetomidine follow-up open; Propranolol publication unsearched | §8.4 follow-up resolved; §8.7 update; §8.9 Droxidopa credibility; §9 label-trial role audit | registry/PubMed responses this session | PASS |
| C-20 | `TECHNICAL_DEBT.md`, `ERRORS_AND_BLOCKERS.md`, `README.md` | — | TD-020 addendum 2, TD-031…TD-034; E-015 resolved, E-017, B-002 | — | PASS |
| C-21 | `docs/CASE_STUDIES.md` §9.1, `TECHNICAL_DEBT.md` TD-032 | TD-032 labels not adjudicated per compound | Adjudicated all 17 positives from the saved 24 registry records (no new requests): 12 confirmed / 3 rejected / 2 unresolved; impact of policies P0–P3x with paired-bootstrap CIs (in memory) | no data/label/VPS file changed | DOCUMENTED — awaiting owner approval |
| C-22 | `data/label_role_exclusions.csv` (new), `scripts/06_vps_fusion.py` (`LABEL_EXCLUSIONS_CSV`, `apply_label_exclusions`), `tests/test_label_role_exclusions.py` (new, 5 tests); archive `data/_archive_pre_td032_2026-10-14/` | TD-032 owner decision P1 | Per-trial label exclusion (mismatch raises); ground-truth CSV untouched; stage 06 rerun; bootstrap rerun | 14/90 positives; AUROC 4d 0.689→0.724, 5d 0.747→0.781; nested-CV 4d 0.631→0.560, 3d 0.648→0.686, 5d 0.660→0.717; 5d−4d +0.058 [−0.038, +0.159], P 0.872; `Ran 301 tests ... OK` | PASS — TD-032 feature side OPEN; figures stale |
| C-23 | `scripts/00_exclusion_filter.py`, `01_get_pd_candidates.py`, `02_network_proximity.py`, `03_clinicaltrials_groundtruth.py`, `04_literature_independence.py`, `05_safety_signal.py`, `06_vps_fusion.py`, `07_generate_figures.py`, `check_studytype.py`, `check_intervention_match.py` | TD-034 / E-017: `--help` ran stages | Option-free argparse guard in each `__main__` block | `TestHelpDoesNotRunStages` (10 scripts, no files written, unknown flag → exit 2) | PASS — TD-034 FIXED |
| C-24 | `scripts/07_generate_figures.py` (`_uncertainty_note`), `tests/test_pipeline_safety_contracts.py` (new, 7 tests) | Figure 1 showed no labels/uncertainty; contracts untested | Caption computed from persisted `vps_scores_v2.csv` (label count, paired-bootstrap 5d−4d CI); tests for ground-truth md5, equal-weight formula, training-fold-only selection, caption | `Ran 308 tests ... OK` | PASS |
| C-25 | `data/figure1_auroc_comparison.png`, `figure2_ablation.png`, `figure2_ablation_5d.png`, `figure3_droxidopa_literature_graph.png` regenerated; previous PNGs + MD5SUMS + input MD5s in `data/_archive_figures_pre_2026-10-15/` | Figures predated TD-032 P1 (Figure 1 dated 2026-10-05) | Ran stage 07 after backup; metric inputs verified unchanged by md5 | Figure 1: 14/90, 5d−4d +0.058 [−0.038, +0.159], "not significant" | PASS |
| C-26 | `TECHNICAL_DEBT.md` (TD-021 dry-run plan, TD-024/TD-031/TD-033 addenda, TD-034 fixed, TD-035, TD-036), `docs/CASE_STUDIES.md` §9.2, `docs/LITERATURE_CREDIBILITY_AGENT.md`, `README.md` | Validation sprint audit | Documentation of verified findings only; no label, weight, pool, cutoff or missing-data policy changed | in-memory analyses only; 0 external API calls | DOCUMENTED |
| C-27 | `scripts/05_safety_signal.py`, `tests/test_safety_missingness.py`, `tests/fixtures/openfda_varenicline_label_subset.json` (new); data: `data/safety_signal.csv` (rewritten), `data/_safety_checkpoint_v2.jsonl`, `data/cache/openfda_labels/` (83 files, new) | D-003: PLR `warnings_and_cautions` ignored | Read all warning fields; record set_id/effective_time; cache raw labels; separate v2 checkpoint (v1 untouched) | 5 + 90 openFDA requests; zero-term labelled 52 → 16 | PASS — TD-022 still OPEN |
| C-28 | `scripts/06_vps_fusion.py` (`NEUTRAL_RANK`, `impute_missing`, `build_standardized_scores`), `tests/test_safety_missingness.py`, `tests/test_pipeline_safety_contracts.py` | D-004 / TD-031 / TD-024 | Unmeasured safety and no-target molecular → neutral rank 0.5 + `dimensions_missing`, `n_dimensions_measured`, `molecular_evidence_missing` | 06 rerun; see metrics below | PASS — TD-031, TD-024 FIXED |
| C-29 | `ui/server.py`, `ui/app.js`, `tests/test_ui.py` (+2 tests) | D-008: UI hid label exclusions and missing dimensions | Mark excluded label trials; label meaning; not-measured notes; stage-05 v2 metadata | 44 UI tests; live loopback smoke test (port 8799) | PASS — browser rendering not verified |
| C-30 | `development_log/DECISIONS.md` (new), `TECHNICAL_DEBT.md` (TD-022, TD-024, TD-031, TD-036, TD-037), `ERRORS_AND_BLOCKERS.md` (E-018), `docs/CASE_STUDIES.md` §10, `README.md`; figures regenerated; archive `data/_archive_pre_D003_D004_2026-10-15/` | Decision log and case-study completion | — | `Ran 314 tests ... OK` | DOCUMENTED |
| C-31 | `TECHNICAL_DEBT.md`, `development_log/ERRORS_AND_BLOCKERS.md`, `docs/CASE_STUDIES.md` | E-019: Claude's newline-trim command truncated the three files | Rebuilt from the staged versions plus 22 transcript-recorded edits; verified against recorded line counts and section positions | restored md5 TD `1d9e758d…`, ERRORS `72494c13…`, CASE `693753d3…` | RESTORED (residual risk in E-019) |
| C-32 | `development_log/DECISIONS.md` (D-010…D-013), `docs/CASE_STUDIES.md` §9.2, §10, §10.1, `TECHNICAL_DEBT.md` TD-035, `ERRORS_AND_BLOCKERS.md` L-003 | Endpoint, disputed labels, re-retrieval need, objective | Endpoint frozen to the 2026-10-05 registry snapshot (2026-09-08 = latest trial, not retrieval date); Lidocaine CONFIRMED; Galantamine unresolved, sensitivity reported; literature re-retrieval not required for the qualified claim; RQ-2 separate | in-memory analyses; no labels or data changed; 0 API calls | DOCUMENTED |
| C-33 | UI server restarted (old PID 98598 → new process on 127.0.0.1:8765) | Dashboard served pre-D-004 code | Restart only; no code change | headless Chrome rendered `#drugs/Lisuride`, `#drugs/Dexmedetomidine`, `#drugs/Donepezil` with the new fields; the Chrome extension cannot reach loopback (L-003) | PASS |
| C-34 | `scripts/conflict_context_agent.py` (new), `data/conflict_claims_curated.json` (new), `tests/test_conflict_context_agent.py` (new, 21), `docs/CONFLICT_CONTEXT_AGENT.md` (new); output `data/conflict_context.json` (new) | Architecture 10d missing (D-015) | Offline, deterministic conflict/context classification of curated (CASE_STUDIES PMIDs), openFDA-label and 10b claims; atomic write; not in VPS | 21 tests OK; real run: 0 DIRECT, 1 STATISTICAL, 1 CONTEXT, 8 CROSS_DOMAIN, 72 INSUFFICIENT; 0 API calls | PASS (diagnostic) |
| C-35 | `ui/server.py` (`/api/overview`, `/api/ranking`, `/api/agents`, `/api/conflicts`, 10d stage, 10a/10d blocks per compound, `/favicon.ico` 204), `ui/app.js`, `ui/index.html`, `ui/style.css`, `tests/test_ui.py` (+6; contrast test now checks the single dark palette); derived artefact `data/bootstrap_ci_equal5d_vs_4d.csv` (new, from `bootstrap_auroc_ci.py --out`) | D-014: interactive dashboard | Overview, sortable ranking, evidence states, agent inventory/inspector, case-study ledger, primary CIs; dark palette | 50 UI tests OK; headless-Chrome CDP run: 18/18 checks, 0 console errors | PASS (headless browser) |
| C-36 | `development_log/DECISIONS.md` (D-014, D-015), `README.md` | — | — | full suite `Ran 341 tests ... OK`; `git diff --check` clean; ground truth md5 unchanged | DOCUMENTED |
| C-37 | `scripts/reproducibility_agent.py` (new), `tests/test_reproducibility_agent.py` (new, 18), `docs/REPRODUCIBILITY_AGENT.md` (new); data: `data/cache/pubmed_efetch_case_claims.xml` (new, 1 PubMed efetch, 14 PMIDs), `data/reproducibility.json` (new) | Architecture 10e missing (D-017) | Finding-level replication with categorical independence; no score; atomic write; inputs md5-stamped | 18 tests OK; 1 REPLICATED / 6 SINGLE_STUDY / 7 SECONDARY_ONLY; 21 shared trials | PASS (diagnostic) |
| C-38 | `data/conflict_claims_curated.json` (dates for PMIDs 35718329, 40200766 from efetch); `data/conflict_context.json` regenerated | Two curated claims undated | Verified years filled with `date_source` | 10d rerun: status counts unchanged | PASS |
| C-39 | `scripts/vps_evaluation_report.py` (new), `tests/test_vps_evaluation_report.py` (new, 5), `docs/VPS_EVALUATION.md` (new); output `data/vps_evaluation_report.json` (new) | D-018 | Reproduced metrics, AUPRC CIs, repeated nested CV, correlations, missingness, duplicate trials, calibration N/A | all 6 AUROCs reproduced; bootstrap bit-identical; 5 tests OK | PASS |
| C-40 | `scripts/record_test_run.py` (new) → `data/test_run_metadata.json`; `data/case_study_status.json` (new); `ui/server.py` (10e stage/registry; `/api/case_status`, `/api/evaluation`, `/api/risks`, `/api/runmeta`; output schemas; latest test run; risk panel reads error-log RESOLVED markers), `ui/app.js` (risks, runs & audit, case-status table, evaluation report, 10e panels; ledger-overwrite fix E-020), `ui/index.html`, `ui/style.css`, `tests/test_ui.py` (+5, 10e assertion updated) | D-016, D-019 | Dashboard upgrades | 55 UI tests OK; headless-Chrome CDP 28/28 (keyboard, 390-px phone, 0 console errors) | PASS (headless browser) |
| C-41 | `development_log/ERRORS_AND_BLOCKERS.md` (E-010 resolution note — record was stale; E-020), `TECHNICAL_DEBT.md` (TD-038), `docs/CASE_STUDIES.md` §11, `development_log/DECISIONS.md` (D-016…D-019), `README.md` | Logs | — | line counts checked before/after each edit; final `scripts/record_test_run.py`: 369 tests, 0 failures, 0 errors, 0 skipped | DOCUMENTED |
| C-42 | `data/cache/ctgov_td038_shared_trials.json` (new, 1 ClinicalTrials.gov request, 17/17 records), `data/feature_trial_roles_td038.csv` (new, 35 adjudicated links), `scripts/td038_feature_role_sensitivity.py` (new) → `data/td038_feature_role_sensitivity.json`, `scripts/06_vps_fusion.py` (`apply_feature_exclusions`, inactive unless `data/feature_role_exclusions.csv` exists; not created), `tests/test_td038_feature_roles.py` (new), TD-038 addendum, D-020, `docs/VPS_EVALUATION.md` | D-020 | TD-038 investigation; policy proposed, not applied | S0 reproduces persisted scores exactly; `scripts/record_test_run.py`: 380 tests, 0 failures, 0 errors, 0 skipped; primary outputs unchanged | SENSITIVITY ONLY |
| C-43 | `scripts/completeness_gap_agent.py` (new, 10h) → `data/completeness_gaps.json`; `tests/test_completeness_gap_agent.py` (new, 12); `docs/COMPLETENESS_GAP_AGENT.md` | D-021 | Agent 10h, diagnostic | 12 tests OK; stage-06 agreement 90/90; counts match raw CSVs (31/31, 7/7, 15/15, 16/16, 10/10) | PASS |
| C-44 | `ui/server.py` (10h registry entry; `/api/gaps`, `/api/evidence`; candidate `summary`, `completeness`, mechanism chain/pathways), `ui/app.js` (Overview, Candidates with filters, Evidence, Mechanism, Conflicts, Compare, Validation & Methods, Technical details; source links; 10h panel), `ui/index.html`, `ui/style.css`, `tests/test_ui.py` (+6, 10h status assertion updated), `README.md` | D-022 | Researcher-facing UI | UI 61 + 10h 12 tests OK; headless-Chrome CDP 42/42 (nav, search, filters, sort, selection, evidence links, mechanism, conflicts, compare add/remove, error states, keyboard, 390-px phone on 6 pages, 0 unexpected console errors); full `scripts/record_test_run.py`: 398 tests, 0 failures, 0 errors, 0 skipped | PASS (headless browser) |
| C-45 | `scripts/agent_contract.py` (new); envelopes added to 10a (`literature_credibility_agent.py`, plus `--curated` offline mode → 4 new `data/literature_credibility_*.json`), 10d, 10e (input list kept as `input_files`), 10h; `scripts/molecular_run_record.py` (new, 10b) → `data/molecular_agent_run.json`; `docs/AGENT_CONTRACT.md` | D-023 | Shared agent contract | the 10d/10e status counts are unchanged after regeneration; Droxidopa 10a output only gained envelope fields | PASS |
| C-46 | `scripts/clinical_evidence_agent.py` (new, 10c) → `data/clinical_evidence.json`, cache `data/cache/ctgov_precutoff_trials.json`; `scripts/safety_evidence_agent.py` (new, 10f) → `data/safety_evidence.json`, cache `data/cache/openfda_faers/`; `scripts/evidence_independence_agent.py` (new, 10g) → `data/evidence_independence.json`; `scripts/completeness_gap_agent.py` (10h-1.0: reads 10c/10f/10g, failure files, agent staleness); tests: 4 new modules, plus updates to the 10h, 10a and 10e tests | D-023, E-022 | Agents 10c, 10f, 10g; 10h extended | targeted tests OK (see C-48) | PASS |
| C-47 | `scripts/05_safety_signal.py`, `scripts/04_literature_independence.py` (failures recorded and exit 1; not re-run); `tests/test_safety_missingness.py` updated | E-021 | Silent-failure fix | stage outputs unchanged | PASS |
| C-48 | `ui/server.py` (agent registry: 10c/10f/10g modules, envelope-derived run status, STALE, diagnostics, 10b run record; candidate blocks `clinical_evidence`, `safety_evidence`, `evidence_independence`; results note in the evidence index), `ui/app.js` (10c/10f/10g panels, run-status column, E-023 fix), `ui/style.css`, `tests/test_ui.py` (+3) | D-023, E-023 | UI integration | headless-Chrome CDP 53/53 incl. a failure fixture server (missing 10c/10g, FAILED + STALE 10f); full suite in the final report | PASS (headless browser) |
| C-49 | `scripts/vps_verify.py` (new, independent VPS re-computation, legacy + midrank); `scripts/06_vps_fusion.py` (duplicate guard, non-finite guard, `dimensions_imputed`, `--output-dir` with atomic writes, `--rank-convention`, default legacy); `scripts/vps_evaluation_report.py` (all 7 inputs fingerprinted; report regenerated); `tests/test_vps_correctness.py` (new, 13); candidates `data/_candidates/vps_legacy_fixed/`, `data/_candidates/vps_midrank/` | D-024, E-025, E-026, TD-040, TD-041 | VPS verification | baseline reproduced exactly (max diff 2.2e-16); legacy-fixed candidate identical in every score; `data/vps_scores_v2.csv` not replaced | PASS |
| C-50 | `scripts/run_stage.py` (new: run manifest, dependency-aware freshness, staged validated publication, restore on failure, adopt); `ui/server.py` (STAGES + eval, 10a, 10b, 10c, 10f, 10g, 10h; `/api/status`); `data/run_manifest.json` (adopted 21 stages); `tests/test_run_tracking.py` (new, 14) | D-025, E-024 | Run tracking | all 21 real stages ADOPTED and fresh | PASS |
| C-51 | `ui/app.js` (polling with visibility and backoff, header run indicator, VPS banner, in-place refresh, run table, provenance line), `ui/index.html`, `ui/style.css`, `tests/test_ui.py` (+4; `/api/status` added to the read-only route test) | D-025 | Live dashboard | live workflow 17/17 on a fixture copy; regression 53/53 | PASS (headless browser) |
| C-52 | `docs/RUNS_AND_LIVE_UI.md` (new), `docs/VPS_EVALUATION.md` (verified formula, precision@k), `docs/AGENT_CONTRACT.md` (lineage matrix), README | D-024, D-025 | Docs | — | DOCUMENTED |

**Metrics 2026-10-15 (14/90; before → after D-003 + D-004):** equal 4d AUROC 0.724 → **0.700**
[0.567, 0.834]; equal 5d 0.781 → **0.775** [0.656, 0.881]; AUPRC 4d 0.358 → 0.358, 5d 0.439 → 0.424;
5d−4d +0.058 → **+0.075 [−0.025, +0.176]**, P 0.935, not significant. Grid in-sample 4d/3d/5d
0.750/0.761/0.793 → 0.725/0.720/0.774; held-out single split 0.560/0.686/0.717 → 0.607/0.584/0.639;
20-repeat 0.636/0.669/0.710 → 0.574/0.571/0.648. D-003 alone (old missing rule): 4d 0.701.

**External requests:** ClinicalTrials.gov v2 — 2 (NCT05376761: one HTTP 400 from a wrong
field name, then 200), 1 (NCT06658132), 24 (label audit); PubMed — 1 esearch (NCT07113015 →
0 records), 1 efetch (26 Droxidopa PMIDs). No openFDA, Open Targets or Semantic Scholar call;
no pipeline stage run intentionally (see incident E-017).

**Metrics (all from persisted `data/vps_scores_v2.csv`, unchanged):** AUROC VPS_equal 0.6886,
VPS_equal_5d 0.7474, AUPRC 0.4790. Sensitivities in TD-031 / TD-032 are in-memory
re-evaluations under alternative policies, not replacements.

**Incident:** E-017 — `--help` on 05/06 ran both stages; `data/vps_scores_v2.csv` restored
byte-identical; no API call.

**Tests:** `./venv/bin/python -m unittest discover -s tests` → `Ran 296 tests ... OK`
(230 + 66 new). `py_compile` clean on all changed files; `git diff --check` clean.

## 2026-10-19 — Reliability sprint: eight agents, VPS verification, live UI

| ID | Files | Trigger | Area | Verification | Status |
|---|---|---|---|---|---|
| C-53 | `scripts/run_stage.py` (non-staged stage that exits without rewriting outputs → PARTIAL + `NOT_REWRITTEN`; stages 04/05 PARTIAL only on exit 1 with every output rewritten), `tests/test_run_tracking.py` (+3) | E-027 | Run tracking | crash of 04/05 now FAILED, last good retained | PASS |
| C-54 | `ui/app.js` (15 s request timeout via AbortController; poll loop reschedules in `finally`; 10d filter knows `NO_COMPARABLE_PAIR`), `tests/test_ui.py` (+1) | E-028 | Live UI | headless Chrome: suspended server detected in 17.9 s, recovered after resume | PASS |
| C-55 | `scripts/agent_contract.py` (`envelope()` adds `RUN_FAILED` error when every unit failed and warnings explain why) | E-029 | Agent contract | 10c/10d/10f all-failed paths now write a FAILED envelope instead of crashing | PASS |
| C-56 | `scripts/safety_evidence_agent.py` (HTTP 200 without a result body = failed query; per-query failures and missing label rows → PARTIAL; `needs_fetch` retries failed caches; label cache files hashed as inputs; pool de-duplicated), `tests/test_safety_evidence_agent.py` (+6) | E-030 (10f) | Agent 10f | real output identical except 83 newly tracked label inputs | PASS |
| C-57 | `scripts/reproducibility_agent.py` (`INCONSISTENT_WITHIN_GROUP`; all directions of a repeated PMID; `status_caveat` + `MISSING_SOURCE_RECORDS`; skipped non-PMID claims and missing trial files reported), `tests/test_reproducibility_agent.py` (+3) | E-030 (10e) | Agent 10e | real findings unchanged (14) | PASS |
| C-58 | `scripts/clinical_evidence_agent.py` (results without a posting date → temporal `UNKNOWN`; links never requested by the cache → `NOT_RETRIEVED` + `CACHE_STALE`; `status_counts.no_registry_record`; an all-failed `--fetch` keeps the previous cache and exits 1), `tests/test_clinical_evidence_agent.py` (+5) | E-030 (10c) | Agent 10c | real trials identical (177; 67 with results) | PASS |
| C-59 | `scripts/conflict_context_agent.py` (`NO_COMPARABLE_PAIR`; ratio measures compared with 1; relative paths; duplicate `claim_id` rejected; label cache checked as an input), `tests/test_conflict_context_agent.py` (+4), `docs/CONFLICT_CONTEXT_AGENT.md` (status definition) | E-030 (10d) | Agent 10d | 8 compounds NO_DISAGREEMENT_DETECTED → NO_COMPARABLE_PAIR (Buspirone, Citalopram, Duloxetine, Escitalopram, Nortriptyline, Paroxetine, Sertraline, Venlafaxine) | PASS |
| C-60 | `scripts/evidence_independence_agent.py` (missing inputs warn; header-only links → FAILED), `scripts/completeness_gap_agent.py` (empty/missing stage CSVs and absent agent outputs are warnings; pool compound without a clinical row is NOT_COMPUTED), tests (+2, +2) | E-030 (10g/10h) | Agents 10g/10h | real outputs SUCCESS; 10h stage-06 agreement true | PASS |
| C-61 | `scripts/literature_credibility_agent.py` (nothing returned for requested PMIDs → FAILED; graph mode ignores records outside the graph), `scripts/molecular_agent.py` (`is_retrieval_failure`), `scripts/08_molecular_pathway.py` (resume retries API-failure records; exits 1 if any remain), `scripts/molecular_run_record.py` (flags API-failure records and blank CSV scores), tests (+2, +4) | E-030 (10a/10b) | Agents 10a/10b | real evidence has 0 API-failure records; persisted outputs unchanged | PASS |
| C-62 | Tracked re-runs of 10c, 10f, 10d, 10e, 10g, 10b, 10a, 10h (`data/_runs/20261019T0754*`); candidates `data/_candidates/2026-10-19_sprint/` | — | Outputs | all SUCCESS; VPS, labels, ground truth and stage 01–08 outputs untouched | PASS |

**VPS (independent re-computation, pandas/scipy/sklearn, not `vps_verify.py`):** 90 compounds,
14 positives; max |diff| ≤ 1.7e-16 on every rank and score; labels identical; 5D AUROC 0.7754,
AUPRC 0.4243, P@10 0.50; 4D AUROC 0.7002. Stage 06 re-run from current code into staging:
every score identical; `n_dimensions_measured` differs for Deferiprone and Trimethobenzamide
(4 published vs 3 now) and the published file lacks `dimensions_imputed` (published before
E-026's fix). `data/vps_scores_v2.csv` not replaced.

## 2026-10-19 (second session) — VPS validation, clinical role review, runner/UI states
Full report: `docs/SPRINT_REPORT_2026-10-19.md`; outputs `data/_runs/validation_20261019/`.

| ID | Files | Trigger | Area | Verification | Status |
|---|---|---|---|---|---|
| C-63 | `scripts/vps_validation_experiments.py` (new), `tests/test_vps_validation_experiments.py` (new, 6) | TD-042, TD-040, TD-041, TD-033, TD-036 | VPS validation | baseline reproduced (< 1e-12); bootstrap CIs; nested CV (fitted 0.688 vs equal 0.763) | PASS |
| C-64 | `scripts/clinical_role_review.py` (new), `tests/test_clinical_role_review.py` (new, 3) | TD-038, TD-043, D-020 | Clinical roles | 195 links reviewed; 37 flagged; nothing relabelled | PASS |
| C-65 | `scripts/run_stage.py` (`MISSING` status; `--skip-fresh`), `tests/test_run_tracking.py` (+2) | runner integrity | Run tracking | deleted output → MISSING; identical inputs → no run | PASS |
| C-66 | `ui/server.py` (`stale` file heuristic → `input_newer` hint), `ui/app.js` (stage badges from the run tracker; MISSING banner; live-monitoring wording), `ui/style.css`, `tests/test_ui.py` (1 updated) | freshness must not rest on timestamps | Live UI | headless Chrome 12/12 + 8/8 on fixture copies | PASS |

**Tests:** `./venv/bin/python -m unittest discover -s tests` → `Ran 509 tests ... OK`; `git diff --check` clean.

## 2026-10-19 (continuation) — TD-042 corrected candidate, clinical-role worklist
Report: `docs/SPRINT_REPORT_2026-10-19_CONTINUATION.md`. Candidate: `data/_candidates/td042_v1/` (not approved, not published).

| ID | Files | Trigger | Area | Verification | Status |
|---|---|---|---|---|---|
| C-67 | `scripts/molecular_agent.py` (`pathway_excludes_drug_targets`, default off), `scripts/08_molecular_pathway.py` (`--exclude-drug-targets-from-pathways`, `--offline`, `--resolutions-from`), `tests/test_td042_pathway_rule.py` (new, 8) | TD-042 | Molecular agent | flag off: offline replay byte-identical to published files; flag on: 21 compounds change, as predicted | PASS |
| C-68 | `data/_candidates/td042_v1/` (isolated root; tracked 08 + 06 runs; `verify_td042_candidate.py`; `publish_td042.sh`; README) | TD-042 | Candidate baseline | vps_verify MATCH; second-path all_pass; publication and rollback rehearsed on fixtures | VERIFIED, AWAITING APPROVAL |
| C-69 | `ui/server.py` (`approved_baseline`, `pending_candidates` in `/api/status`), `ui/app.js` (approved-baseline label; pending candidates never displayed), `tests/test_ui.py` (+1) | candidate must not look approved | Live UI | approved values served for Donepezil (0.773, rank 1) | PASS |
| C-70 | `scripts/clinical_role_review.py` (`--worklist`), `tests/test_clinical_role_review.py` (+1); `data/_runs/clinical_review_20261019/` | TD-043, D-020 | Clinical roles | 37 flagged: 9 adjudicated and retained, 28 unresolved | PASS |

**Tests:** `./venv/bin/python -m unittest discover -s tests` → `Ran 519 tests ... OK`; `git diff --check` clean.

## 2026-10-19 (mission) — weighting decision, offline end-to-end pipeline, reproducibility fixes
Reports: `docs/VPS_WEIGHTING_DECISION_2026-10-19.md`, `docs/MISSION_REPORT_2026-10-19.md`.

| ID | Files | Trigger | Area | Verification | Status |
|---|---|---|---|---|---|
| C-71 | `scripts/vps_validation_experiments.py` (`--matrix`: ablations, single dimensions, simplex, shrinkage, L2 logistic, grouped folds, rank stability), `tests/test_vps_validation_experiments.py` (+4) | weighting decision | VPS | learned weights never beat equal (0–5% of repeats) | PASS |
| C-72 | `scripts/02_network_proximity.py` (sorted iteration), `tests/test_proximity_determinism.py` (new) | E-031 | Stage 02 | identical output under 3 hash seeds | PASS |
| C-73 | `ui/server.py` (04b `run_args`; 10c depends on 08 and reads its evidence), `tests/test_run_tracking.py` (+1) | E-032 | Runner | offline end-to-end: every runnable stage SUCCESS | PASS |
| C-74 | `scripts/clinical_evidence_agent.py` (ChEMBL preferred name as alias; `compound_aliases`, `chembl_names`), `scripts/clinical_role_review.py` (same aliases; `CHEMBL_ALIAS` flag), tests (+3) | TD-043 | 10c / review | 1 verdict changed (Rifampicin NCT02174250 → CO_ADMINISTERED); kept on the review list | PASS |
| C-75 | `data/_runs/mission_20261019/` (`e2e_offline_smoke.py` + results, `proximity_seed_sensitivity.*`, `agent_determinism_check.py`, `ui_acceptance/`) | end-to-end proof | Pipeline | full and reproduction modes: all stages fresh, vps_verify MATCH | PASS |
| C-76 | Live UI server restarted with the documented command (PID 29826 → new PID) | load the server-side changes | UI | live checks 6/6 | PASS |
| C-77 | `scripts/03_clinicaltrials_groundtruth.py` (no partial publication; consecutive-failure breaker; `--accept-failed-searches`), `scripts/check_studytype.py` (same; runs the filter), `scripts/filter_by_studytype.py` (refuses ERROR rows), `tests/test_stage03_failure_handling.py` (new, 6) | E-033, E-034 | Stages 03/03c | filter reproduces the protected clean CSVs byte-for-byte | PASS |
| C-78 | `scripts/run_stage.py` (script fingerprint per run; "stage code changed" warning), `tests/test_run_tracking.py` (+1) | freshness ignored code changes | Runner | warning shown, cleared by a re-run | PASS |
| C-79 | `scripts/04p_literature_provenance.py` (new stage 04p), `tests/test_literature_provenance.py` (new, 13), `ui/server.py` registry | TD-021 (PMIDs, dates, truncation never persisted) | Literature | live run 20261019T124053Z-04p-67c4 SUCCESS: 89 SUCCESS + 1 NO_RESULTS, 4220 records; offline rerun byte-identical; first attempt PARTIAL on a transient efetch HTTP 400 (reported, not swallowed) | PASS |
| C-80 | `scripts/literature_credibility_agent.py` (`--all`, 04p dates override issue year), registry stage `10a-all`, tests (+3) | 10a covered 5 compounds | 10a | 89/90 assessed (1 absent at source), 4191 papers, 29 duplicates removed | PASS |
| C-81 | `scripts/evidence_independence_agent.py` (D2 from 04p PMIDs; new D5 duplicate publications), `ui/app.js` label, tests (+2) | 10g D2 assessable for 4 compounds | 10g | D2 assessable 89/90 (20 DEPENDENCE_FOUND), D5 9 found | PASS |
| C-82 | `scripts/completeness_gap_agent.py` (`credibility_state`, 10a-all staleness), tests (+1) | 10h reported literature credibility NOT_RETRIEVED for 85 compounds | 10h | 89 ASSESSED + 1 ABSENT_AT_SOURCE | PASS |
| C-83 | `scripts/vps_literature_cutoff_sensitivity.py` (new), `tests/test_literature_cutoff_sensitivity.py` (new, 2) → `data/_runs/literature_cutoff_20261019/` | TD-033 literature leakage unquantified | VPS validation | bounded literature changes 5D AUROC by −0.019 [−0.067, 0.030]; nothing published | PASS |
| C-84 | registry stage `review`, `scripts/clinical_role_review.py` defaults, `ui/server.py` `/api/review`, `ui/app.js` + `ui/index.html` "Review queue" view, `tests/test_ui.py` (+2) | 28 unresolved links not visible in the UI | UI / 10c | 28 unresolved + 9 adjudicated shown read-only; live browser checks 7/7 | PASS |
| C-85 | `scripts/05h_safety_label_history.py` (new stage 05h), `tests/test_safety_label_history.py` (new, 5), registry | TD-022/TD-033 safety not cutoff-bounded | Safety | live run 20261019T165836Z-05h-272f SUCCESS; parser = stage 05 on 83/83; 31 scored at cutoff, 52 unknown, 7 no label | PASS |
| C-86 | `data/_runs/live_stages_20261019/live_stage_check.py` (isolated live re-run of 01, 00, 03, 03c, diag, 04b) | B-002 | Pipeline | 01/00/03/03c/diag SUCCESS; 04b guard refused on content drift (by design); protected files untouched | PASS |
| C-87 | `scripts/vps_molecular_snapshot_sensitivity.py` (new), `tests/test_molecular_snapshot_sensitivity.py` (new, 2); Open Targets 20.11 PD rows cached in `data/cache/opentargets_20.11/` | TD-006/TD-033 | VPS validation | direct component 20.11 vs 26.09: 5D AUROC −0.086 [−0.169, −0.011]; recompute = published (≤1e-6) | PASS |
| C-88 | `scripts/safety_evidence_agent.py` (label.at_cutoff, temporal), `scripts/completeness_gap_agent.py` (label_at_cutoff annotation), `scripts/vps_literature_cutoff_sensitivity.py` (safety-at-cutoff variants), `ui/app.js` (safety panel), `ui/server.py` (10a-all on compound pages, 10f deps), tests (+6) | 10f provenance/temporal | 10f/10h/UI | live browser 9/9 | PASS |
| C-89 | `scripts/debug_step2.py`, `tests/test_debug_step2.py` (new) | TD-008 | Diagnostics | 637 PD genes (was 0), equals stage 02 | PASS |
| C-90 | `tests/test_eight_agents_integration.py` (new, 7): every agent's persisted output reproduced from its inputs; envelopes; pool coverage; 10h freshness | single all-agent integration test | Agents | caught 10h stale after the 10f re-run (fixed by re-running 10h) | PASS |

## 2026-10-20 (overnight mission) — runner concurrency, live run detail, evidence overlap, historical molecular
Report: `docs/autonomous_runs/OVERNIGHT_FINAL_REPORT.md`.

| ID | Files | Trigger | Area | Verification | Status |
|---|---|---|---|---|---|
| C-91 | `scripts/run_stage.py` (`StageBusy`, `_related`, atomic check-and-claim under the manifest lock; CLI exit 3), `tests/test_run_tracking.py` (+6) | E-035: concurrent launches of the same / upstream / downstream stage were allowed | Runner | 4/6 new tests fail on the pre-change runner, 6/6 pass; live: second launch and upstream launch refused (exit 3) in an isolated copy | PASS |
| C-92 | `scripts/run_stage.py` (`duration_s`, `log`, `elapsed_s`, `upstream` in status), `ui/server.py` (`/api/log`, run-id validated, confined to data/_runs, redacted), `ui/app.js` (run table: upstream, durations, elapsed while running, log tail on demand), tests (+1 runner, +3 UI) | UI lacked durations, elapsed time, upstream state, logs | UI | browser 15/15 (desktop 1440 + mobile 390, live RUNNING in an isolated copy, no JS exceptions) | PASS |
| C-93 | `scripts/vps_evidence_overlap.py` (new), `tests/test_evidence_overlap.py` (new, 2) → `data/_runs/evidence_overlap_20261020/` | mission Step B: double counting between dimensions | VPS validation | same-trial papers for 20 compounds (identical to 10g D2, independent code); 0 label-trial reports; removal d=+0.002 [-0.004, 0.009] | PASS |
| C-94 | `scripts/vps_weighting_experimental.py` (new), `tests/test_vps_weighting_experimental.py` (new, 1) → `data/_runs/vps_weighting_experimental_20261020/` | mission Step C on cutoff-bounded feature sets | VPS validation | learned weights beat equal in <= 10% of repeats in all 3 sets x 2 fold schemes | PASS |
| C-95 | `scripts/vps_molecular_historical.py` (new), `tests/test_molecular_historical.py` (new, 4); 20.11 input files `uniprot-2020-11-10.xml.gz`, `ReactomePathways*-2020-11-10.txt`, `chembl_{mechanism,target}_rest_api-2020-06-01.json.gz` cached in `data/cache/opentargets_20.11/` → `data/_runs/molecular_historical_20261020/` | TD-033 molecular: pathway component not rebuilt for 2020 | VPS validation | method check exact (26.09 pathway component rebuilt, max abs 0.0); 5D approved 0.775 -> 0.690 at 20.11 (d=-0.086 [-0.186, 0.020]); TD-042 0.699 -> 0.690 (d=-0.009); with dated ChEMBL 2020-06 targets 0.704 / 0.703 (4D 0.700) | PASS |
| C-96 | `docs/VPS_FEATURE_CONTRACT.md` (new) | mission Step A | VPS | checked against `06_vps_fusion.build_standardized_scores`; vps_verify MATCH | PASS |

## 2026-10-20 (end-to-end production-readiness audit)
Report: `docs/autonomous_runs/END_TO_END_PRODUCTION_READINESS_REPORT.md`.

| ID | Files | Trigger | Area | Verification | Status |
|---|---|---|---|---|---|
| C-97 | `ui/server.py` registry (`depends_on` + "06" for 10b, 10c, 10d, 10f, 10g), `tests/test_run_tracking.py` (+2) | E-036 | Runner / freshness | reproduced in an isolated copy (STALE 06, agents fresh); 2 new tests fail on the old registry; live statuses unchanged | PASS |
| C-98 | `ui/server.py` (`AGENT_STAGES`, `AGENT_VPS_ROLE`, `tracked_runs`/`tracked_status` in `/api/agents`), `ui/app.js` (`trackedCell`, both agent tables), `ui/style.css` (badge word-break), `tests/test_ui.py` (+3) | agent panel ignored dependency-aware freshness | UI | unreadable manifest -> UNKNOWN; browser 20/20 incl. header/cell alignment on every view | PASS |
| C-99 | `scripts/completeness_gap_agent.py`, `scripts/evidence_independence_agent.py`, `scripts/05h_safety_label_history.py` (files closed with `with`) | ResourceWarnings from production code | Agents | 05h (`--offline`), 10g, 10h re-run via runner: outputs identical excluding timestamps | PASS |
| C-100 | `scripts/vps_architecture_comparison.py` (new), `tests/test_vps_architecture_comparison.py` (new, 1) -> `data/_runs/vps_architecture_20261020/` | audit Phase 3 (architectures A-D) | VPS validation | A reproduces the published VPS_equal_5d exactly; values match the previous report | PASS |
| C-101 | `docs/autonomous_runs/{END_TO_END_ARCHITECTURE_AUDIT,EIGHT_AGENT_VPS_CONTRIBUTION_AUDIT,PRODUCTION_READINESS_CHECKLIST,END_TO_END_PRODUCTION_READINESS_REPORT}.md` | audit deliverables | Docs | — | PASS |

## 2026-10-20 (4-hour hardening sprint)
Report: `docs/autonomous_runs/FOUR_HOUR_INDUSTRY_READINESS_REPORT.md`.

| ID | Files | Trigger | Area | Verification | Status |
|---|---|---|---|---|---|
| C-102 | `scripts/run_stage.py` (declared inputs/outputs missing from the last success -> warning), `tests/test_run_tracking.py` (+2) | E-037: inputs/outputs added to the registry after a run were never compared | Runner | test fails on snapshot code | PASS |
| C-103 | `ui/server.py` registry (06, 07, eval(+dep 10e), 10f, 10g, 10h inputs; 10a outputs; 10h dep 10a), `tests/test_run_tracking.py` (+3), `tests/test_ui.py` DERIVED_PATHS | E-037: undeclared reads/writes found by a source scan and an isolated write-containment run | Registry | static scan + write containment 10/10 agents; 10a/10b-10e/10g/10h/07/review re-run offline | PASS |
| C-104 | `scripts/run_stage.py` (`ManifestError`, `check_manifest`, `--check-manifest`, fsync), `ui/server.py` (`manifest_error`), `ui/app.js` (pill + UNKNOWN banner), tests (+6) | E-038 corrupt manifest -> HTTP 500 / traceback; E-040 pill said "current" for unknown states | Runner/UI | 6 tests fail on snapshot code; browser 8/8 incl. corrupt manifest | PASS |
| C-105 | `scripts/run_stage.py` (BACKUP_LIMIT 512 MB; `UnsafeRun`, exit 4), tests (+3) | E-039 stage 01 output (89 MB) exceeded the 50 MB backup limit | Runner | 2 of 3 tests fail on snapshot code | PASS |
| C-106 | `ui/app.js` (single-flight polling), `tests/test_ui.py` (+1) | E-041 concurrent polls on visibilitychange | UI | browser: held request -> 1 request, 1 coalesced follow-up | PASS |
| C-107 | `scripts/run_stage.py` (`code_fingerprint_recorded`), `ui/app.js` note, tests (+1) | 10a outputs predated their code (no fingerprint before C-78) | Runner/UI | 16 stages lacked fingerprints; 5 offline agents re-run (10a differed: `temporal_source` added by C-80; 10b-10e identical) | PASS |
| C-108 | `ui/server.py` `/api/health` (200 ready / 503 not ready), tests (+2) | readiness probe | UI/ops | live: ready | PASS |
| C-109 | `scripts/backup_data.py` (new), `tests/test_backup_data.py` (new, 6) | TD-044 backups/retention | Ops | backup `~/EviRep_backups/evirep_data_20261020T075410Z.tar.gz` verified (1389 files) | PASS |
| C-110 | `scripts/clinical_role_review.py`, 9 test files (pathlib read/write) | ResourceWarnings 126 -> 0 | Hygiene | `review` re-run byte-identical; suite 0 warnings | PASS |

## 2026-10-20 (final submission-readiness mission)
Report: `docs/autonomous_runs/FINAL_SUBMISSION_READINESS_REPORT.md`; summary `docs/autonomous_runs/final_verification_summary.json`.

| ID | Files | Trigger | Area | Verification | Status |
|---|---|---|---|---|---|
| C-111 | `tests/test_ground_truth_contract.py` (new, 9), `docs/autonomous_runs/SCIENTIFIC_CONTRACT_TRACEABILITY.md` | independent ground-truth/evaluation contract | Science | stdlib-only recomputation: 90 / 14, every label, cutoff, exclusions, AUROC 0.775376, AUPRC 0.424315, report md5s | PASS |
| C-112 | `ui/live_runs.py` (new), `ui/server.py` (`/api/session`, `/api/launches`, guarded `POST /api/run`), `ui/app.js` (Live pipeline view), `ui/index.html`, `tests/test_live_runs.py` (new, 8), `tests/test_ui.py` (+3) | real-time run controls via scripts/run_stage.py | UI | browser 15/15 incl. real runs, paused real stage, server restart mid-run, real failure with output kept | PASS |
| C-113 | `scripts/run_stage.py` (`--sequence`, `run_sequence`, `last_activity`), tests (+4) | dependency-ordered "run all"; real activity instead of percentages | Runner | tests; browser | PASS |
| C-114 | `scripts/run_stage.py` (`attest`, `--attest-from`), tests (+2); live manifest: 00, 04, 05, 08 attested | TD-046 code fingerprints for ADOPTED stages | Provenance | byte-identical isolated reproduction by current code; outputs untouched; 8 refused with reasons | PASS |
| C-115 | `ui/app.js` (stale-nonce renewal + retry; identical background render leaves DOM alone; fast poll while a launch is alive) | E-042, E-043 found by the browser run | UI | browser 15/15 | PASS |

## 2026-10-20 (live application redesign)
| ID | Files | Trigger | Area | Verification | Status |
|---|---|---|---|---|---|
| C-116 | `ui/server.py` (`/api/live`, `/api/agent`, `SERVER_INSTANCE`), `ui/app.js` (Dashboard default view, agent detail view, session reset on server change), `ui/index.html` (nav: Dashboard, Stages, research views, Results summary, Diagnostics), `ui/style.css` (dashboard, compact mobile header), `tests/test_live_app.py` (new, 6) | the entry point was a static report (default `#overview`, Markdown-derived risks); live controls hidden in a 10th tab | UI | browser acceptance 16/16 (`docs/autonomous_runs/evidence/ui_live_app_acceptance.json`); regressions 21/21, 8/8, 15/15; 660 tests OK | PASS |

## 2026-10-20 (runtime reliability verification)
| ID | Files | Trigger | Area | Verification | Status |
|---|---|---|---|---|---|
| C-117 | `scripts/run_stage.py`, `ui/live_runs.py`, `ui/server.py`, `ui/app.js`, `ui/style.css`, `tests/test_run_tracking.py` (+5), `tests/test_live_runs.py` (+5) | E-044..E-050 reproduced before changes | Runner / UI | 8 of 9 new tests fail on pre-mission code; 670 tests OK; browser 70/70; artefact hashes unchanged (`docs/autonomous_runs/runtime_reliability_20261020T1010Z/`) | PASS |

## 2026-10-20 (final live-runtime gate)
| ID | Files | Trigger | Area | Verification | Status |
|---|---|---|---|---|---|
| C-118 | `ui/live_runs.py` (reaper), `ui/server.py` (next actions, output validity fields, 04p timeout 7200), `ui/app.js`, `ui/style.css`, tests (+3) | E-051; timeout headroom; observability | Runner / UI | 673 tests OK; browser 88/88 incl. timeout lifecycle 9/9; artefact hashes unchanged (`docs/autonomous_runs/final_runtime_gate_20261020T1036Z/`) | PASS |

## 2026-10-20 (UI quality pass)
| ID | Files | Trigger | Area | Verification | Status |
|---|---|---|---|---|---|
| C-119 | `ui/server.py` (`/api/validation_charts`; `/api/live` freshness / sources / science; `dimensions_imputed`; agent `latest_attempt_failed`; fingerprint-cached staleness), `ui/app.js` (readable labels with codes in tooltips; four-part freshness; dependency-free SVG charts with data tables; review search/filter; evidence paging), `ui/style.css`, `ui/index.html`, `tests/test_ui_quality.py` (new, 11) | UI audit A1–A12 (raw codes, blanket "All results current", no charts, unpaged evidence) | UI | 684 tests OK; browser 112/112 (8 suites); vps_verify MATCH; protected hashes unchanged; index unchanged (`docs/autonomous_runs/ui_quality_pass/`) | PASS |

## 2026-10-20 (biomedical UX redesign and eight-agent audit)
| ID | Files | Trigger | Area | Verification | Status |
|---|---|---|---|---|---|
| C-120 | `ui/index.html` (5 sections), `ui/app.js` (Overview landing page, section sub-navigation with all old addresses kept, candidate table + separate candidate page, evidence stance/basis, 6-section Validation, Run Center, distinct refusal reasons, provenance behind "Source and provenance"), `ui/server.py` (`VERIFIED_WITH_GAPS` state, untracked inputs vs outputs, evidence `stance`/`basis`, agent ids removed from result notes), `ui/style.css`, tests (+13: `test_agent_failure_modes`, `test_biomedical_ux`; 3 existing tests updated) | biomedical UX mission; untracked input shown as current | UI | 697 tests OK; browser 156/156; vps_verify MATCH; protected 19/19; index unchanged (`docs/autonomous_runs/biomedical_ux_agent_audit/`) | PASS |

## 2026-10-20 (scientific release audit)
| ID | Files | Trigger | Area | Verification | Status |
|---|---|---|---|---|---|
| C-121 | `scripts/03_clinicaltrials_groundtruth.py` (pagination), `scripts/vps_validation_experiments.py` (undefined AUROC, `best_index`), `scripts/run_stage.py` (`PARTIAL_ON_EXIT1`), `scripts/evidence_independence_agent.py`, `scripts/conflict_context_agent.py`, `scripts/completeness_gap_agent.py`, `scripts/agent_contract.py` (absent inputs recorded), atomic writes in 10b/10a/10f/05/08, `ui/server.py` (14 positives, 08 timeout, 10h inputs, staleness rule), docs corrections; tests `test_scientific_audit.py` (new, 23), `test_agent_failure_modes.py` (+3), repaired `test_vps_validation_experiments.py`, updated `test_safety_evidence_agent.py` | scientific release audit S-01..S-24 | Pipeline / statistics / docs | 723 tests OK, 0 warnings; approved result reproduced independently; protected 19/19; agent outputs regenerated with identical content (`docs/autonomous_runs/scientific_release_audit/`) | PASS |

## 2026-10-21 (overnight audit)
| ID | Files | Trigger | Area | Verification | Status |
|---|---|---|---|---|---|
| C-122 | `scripts/compare_result_sets.py` (new), `ui/server.py` (`/api/alternatives`, `/api/result_set`, `server_code_changed`), `ui/app.js` (Validation §7 alternative scoring, data-contract panel, readable dependency graph, UTC header, restart banner), tests `test_alternative_result_sets.py` (6), `test_vps_independent_agreement.py` (9), `test_server_code_change.py` (3), `test_ui.py` (expectation); `scripts/05_safety_signal.py`, `scripts/08_molecular_pathway.py` restored to pre-2026-10-20 bytes | overnight audit: TD-042 comparison, data contract, UI defects, stale live server | Scoring display / UI / provenance | 741 tests OK, 0 warnings; browser suites + interaction audit (2,118 controls, 0 dead); protected 19/19; approved result unchanged (`docs/autonomous_runs/overnight_audit_20261021/`) | PASS |

## 2026-10-21 (end-to-end UI verification and commit-readiness gate)
| ID | Files | Trigger | Area | Verification | Status |
|---|---|---|---|---|---|
| C-123 | `scripts/run_stage.py` (failed-dependency warning), `ui/app.js` (stage warnings shown in the Run Center; state chart keeps its data table; stage names wrap), `ui/style.css` (`.nowrap`), tests `test_stage_registry_integrity.py` (new, 8), `test_agent_failure_modes.py` (+1), `test_ui_quality.py` (+1) | E2E UI audit: A-5, A11Y-1, UI-1, REG-1; stale live server restarted | Run Center / accessibility / registry | 751 tests OK, 0 warnings; browser 159/159 + 186-control behavioural audit (0 dead) + accessibility tree (0 unnamed, 23/23 charts with tables); vps_verify MATCH; protected 19/19; index byte-identical (`docs/autonomous_runs/ui_e2e_release_audit_20261021T0244Z/`) | PASS |

## 2026-10-21/22 (final submission and release audit)
| ID | Files | Trigger | Area | Verification | Status |
|---|---|---|---|---|---|
| C-124 | `ui/app.js` (agent badge: "checks a score input; does not change the score" replaces "feeds the score"), `ui/server.py` (`agent_vps_role`: unresolved review count read from the worklist, was hard-coded 28), `scripts/completeness_gap_agent.py` (independence denominator counts D1-D5, was 4), `scripts/clinical_role_review.py` (atomic CSV writes), tests `test_review_count.py` (new, 3), `test_ui_quality.py` (+1), `test_completeness_gap_agent.py` (+1 and 1 assertion); `TECHNICAL_DEBT.md` (dated notes on TD-009, TD-021, TD-031, TD-033), `docs/VPS_EVALUATION.md` (imputation-flag correction); stages `review` (byte-identical output) and `10h` re-run | final release audit E-061..E-063; fully dated 5D and weighting experiments | UI wording / agents / docs | 756 tests OK, 0 warnings; browser 159/159 + accessibility tree + live badge check; vps_verify MATCH; protected 19/19; index unchanged (`docs/final_release_20261022/`) | PASS |
