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
