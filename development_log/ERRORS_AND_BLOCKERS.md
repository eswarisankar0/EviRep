# ERRORS AND BLOCKERS

Actual errors, failed tests, API failures, unavailable data, assumptions and unresolved
issues. Entries are never deleted once recorded; a later fix is marked **RESOLVED** with the
original error preserved.

Severity: **BLOCKER** (stops work) · **ISSUE** (real defect, worked around) ·
**ASSUMPTION** (choice not supported by a cited source) · **LIMITATION** (known, accepted).

---

## 2026-10-05

### E-001 · ISSUE · RESOLVED · Missing declared dependencies
- **File/cmd:** `scripts/06_vps_fusion.py`, `scripts/07_generate_figures.py`;
  `./venv/bin/python -c "import sklearn, matplotlib"`
- **Error:** `ModuleNotFoundError: No module named 'sklearn'` and `'matplotlib'`.
  Both are imported by existing committed code, so stages 06 and 07 could not execute at all.
- **Why it blocked this task:** VPS fifth-dimension integration cannot be smoke-tested
  without `sklearn` (`roc_auc_score`, `StratifiedKFold`).
- **Resolution:** installed into the existing `venv/` and recorded in a new `requirements.txt`
  (the repo previously had no dependency metadata). Original error preserved above.

### E-002 · ISSUE · RESOLVED · Guessed ChEMBL ID resolved to the wrong drug
- **Cmd:** Open Targets GraphQL `drug(chemblId: "CHEMBL1200539")` — an ID recalled from
  general knowledge as "ropinirole".
- **Error:** returned `{"name": "CALCIUM CARBONATE"}`.
- **Impact:** confirms that drug identifiers must never be written from model memory.
- **Resolution:** all drug identity now resolved at runtime through the API
  (`mapIds` / `search`), never hardcoded. Ropinirole verified as `CHEMBL589` *by query*.

### E-003 · ISSUE · Open Targets name resolution returns fuzzy, non-identical hits
- **Cmd:** `mapIds(queryTerms: ["Simvastatin"], entityNames: ["drug"])`
- **Observed:** returns `CHEMBL1064/SIMVASTATIN` **plus** `CHEMBL1144/PRAVASTATIN` and
  `CHEMBL2220442/FLUVASTATIN` — different drugs.
- **Impact:** blindly taking `hits[0]` (or any ranked hit) would fabricate drug→target
  relationships for the wrong molecule.
- **Mitigation:** `normalize_drug()` accepts a hit only on case/punctuation-insensitive
  equality against the returned `name` or an explicit synonym/trade name; otherwise the
  drug is reported unresolved with `limitations` populated. Enforced by test
  `test_normalize_rejects_fuzzy_nonidentical_match`.

### E-004 · LIMITATION · `associationDatasources()` returned an empty list
- **Cmd:** `{ associationDatasources { datasource datatype } }` → `[]`
- **Impact:** the official datasource→datatype mapping could not be retrieved from the API,
  so the leakage allowlist could not be grounded in an API-provided mapping.
- **Mitigation:** the datatype allowlist is defined explicitly in
  `MolecularAgentConfig.allowed_datatypes` from datatype IDs **observed in live responses**
  (`genetic_association`, `genetic_literature`, `animal_model`, `affected_pathway`,
  `somatic_mutation`, `rna_expression`, `clinical`, `literature`) and is fully configurable.
  It is not derived from an authoritative static list.

### E-005 · ISSUE · RESOLVED · HTTP 400: `Drug.synonyms`/`tradeNames` need a sub-selection
- **File/cmd:** `scripts/molecular_agent.py` `_DRUG_DETAIL_QUERY`;
  `./venv/bin/python scripts/08_molecular_pathway.py --compounds "Ropinirole,..."`
- **Error:** every compound returned
  `Target retrieval failed (API unavailable): HTTP 400`. Direct reproduction gave:
  `Field 'synonyms' of type '[DrugLabelAndSource!]!' must have a sub selection`
  (same for `tradeNames`).
- **Root cause (verified by introspecting `DrugLabelAndSource`):** these fields are
  `{label, source}` **objects**, not strings. The query requested them as scalars, and the
  synonym-matching code also treated them as strings — which would have silently matched
  zero aliases even once the query was fixed.
- **Observable first-run symptom:** 4/5 compounds resolved to ChEMBL yet all reported
  `n_targets = 0`, `confidence = 0.0`.
- **Resolution:** query now selects `synonyms{ label source }` / `tradeNames{ label source }`;
  new helper `_alias_labels()` extracts `label` (and tolerates a plain-string shape).
  Regression tests: `test_alias_labels_handles_real_object_shape`,
  `test_drug_detail_query_subselects_label_objects`.
- **Note:** the agent's graceful-degradation path behaved correctly throughout — it
  recorded an explicit limitation and emitted zero evidence rather than fabricating
  targets. The failure was visible, not silent.

### E-006 · ISSUE · RESOLVED · Circular pathway evidence via `affected_pathway`
- **Found by:** manual inspection of the first successful sample run
  (`data/sample_molecular_evidence.jsonl`, compound `Caffeine`).
- **Observed:** gene `ADORA2B` entered the PD module on `affected_pathway = 0.437` as its
  *only* permitted evidence. The pathway component then credited caffeine for sharing
  Reactome pathways with ADORA2B — including the biologically irrelevant
  `"Surfactant metabolism"` (R-HSA-5683826).
- **Why this is a defect, not a nuisance:** Open Targets `affected_pathway` evidence is
  itself derived from pathway/systems-biology sources. Using it to define module
  membership and then measuring Reactome overlap against that gene counts the same
  annotation twice, inflating the pathway component with no independent information.
- **Resolution:** added `MolecularAgentConfig.module_datatypes`, a narrower allowlist for
  *module membership only*, omitting `affected_pathway`. It remains available to the direct
  component, where no double-count arises. Rationale documented inline at the field.
- **Measured effect (same 5-compound sample, cache reused):** `Caffeine` pathway component
  0.8333 → 0.3333; score 0.5957 → 0.3957. No other compound's component changed.
- **Tests:** `test_affected_pathway_alone_cannot_create_module_gene`,
  `test_affected_pathway_still_allowed_for_direct_component`,
  `test_module_datatypes_cannot_include_leaky_types`.

### B-001 · BLOCKER (documented, not resolvable here) · Open Targets snapshot is not cutoff-bounded
- **Issue:** EviRep's methodology separates evidence at `CUTOFF_DATE = 2021-01-01`
  (`scripts/03_clinicaltrials_groundtruth.py`), using post-cutoff trials **only** as ground
  truth. The Open Targets Platform API serves a single *current* snapshot
  (data version 26.09); it exposes no as-of-date parameter. Evidence published after
  2021-01-01 is therefore included in this dimension.
- **Mitigation applied (the safe boundary):** the two datatypes that most directly encode
  the label are excluded — `clinical` (drug-trial precedence) and `literature` (co-mention).
  Verified non-trivially on live data: ADORA2A's composite PD score is 0.610 driven by
  `clinical`=0.957 and `literature`=0.922, but its permitted score is **0.0**.
- **Residual risk:** genetic / animal-model / expression evidence accumulated after the
  cutoff still contributes. This is temporal optimism, not direct label leakage.
- **Not invented:** no cutoff-faithful score is estimated or imputed.
- **Remedy requiring a decision not taken autonomously:** pin to an archived
  pre-2021 Open Targets release (their FTP/BigQuery archives) and rebuild the module from
  it. That changes the data source for the whole dimension and should be an explicit
  methodological choice. Recorded in TECHNICAL_DEBT.md TD-006.
- **Status:** OPEN. Stated in every agent record's `limitations`, and surfaced in
  `docs/MOLECULAR_AGENT.md`.

### E-007 · ISSUE · RESOLVED · 5-dimension grid search returned `None` weights
- **Cmd:** `./venv/bin/python -m unittest discover -s tests`
- **Error:** `FAIL: test_grid_search_handles_five_dimensions ... AssertionError: unexpectedly None`
- **Cause (two distinct problems):**
  1. *Test fixture too small.* 12 compounds / 4 positives cannot support
     `StratifiedKFold(n_splits=5)`; every fold was single-class, `roc_auc_score` raised
     `ValueError` for all of them, and the search correctly found no usable weights.
  2. *Latent defect in pre-existing code.* `cv_grid_search_weights` returns
     `(None, -1, empty_log)` in that case, and `compute_weighted_vps` would then fail with
     an opaque `AttributeError`. The 4-dimension path could hit this too; the new 5-dim
     path merely made it reachable in testing.
- **Resolution:** fixture enlarged to 40 compounds / 12 positives; `compute_weighted_vps`
  now raises a named `ValueError` naming the cause (and a second one for a missing
  `r_<dim>` column), and `main()` falls back to equal 5-dim weights with a printed notice
  rather than crashing.

### A-001 · ASSUMPTION · `max` re-aggregation of permitted datatype scores
- Open Targets' official target-disease score is a harmonic sum with per-datatype weights
  that the API response does not expose. Those weights were **not** invented.
- `max` over permitted datatypes is used instead: conservative, interpretable
  ("strongest permitted evidence type"), and the full per-datatype breakdown is retained
  in every record so any other aggregation can be recomputed without re-querying.
- Stated in each record's `limitations` and in `docs/MOLECULAR_AGENT.md`.

### A-002 · ASSUMPTION · Scoring weights 0.6 (direct) / 0.4 (pathway)
- Chosen **a priori** to encode one ordering only: direct target-disease evidence is
  stronger than pathway co-membership. No label-based search was run to select them —
  doing so would be leakage.
- Not claimed to be optimal. Configurable via `--weight-direct` / `--weight-pathway` so
  sensitivity can be tested as an explicit, reported experiment.

### A-003 · ASSUMPTION · Self-imposed request throttle of 0.25 s (≤4 req/s)
- Open Targets publishes no specific numeric rate limit for the GraphQL endpoint. **No
  limit value is asserted.** 0.25 s is a deliberately conservative ceiling, combined with
  on-disk caching and batching so repeat runs issue no network calls.

### L-001 · LIMITATION · Molecular dimension not evaluated on the real cohort
- `data/` contains no pipeline outputs (`TD-005`), so stages 01–05 have not been run in
  this working copy. The molecular dimension has been validated against:
  (a) 93 offline tests, (b) a live 5-compound sample, (c) synthetic integration fixtures.
- It has **not** been scored against the real candidate pool, and **no AUROC or other
  performance claim for dimension 5 is made**. Any number appearing in smoke-test output
  is a synthetic-fixture artifact.

### E-008 · ISSUE · RESOLVED (workaround) · `NCBI_API_KEY` is set to the placeholder `your_key`
- **Discovered:** 2026-10-05, while verifying references against PubMed, *before* stage 04 ran.
- **Cmd:** `GET eutils/esearch.fcgi?...&api_key=$NCBI_API_KEY`
- **Error:** `HTTP 400 {"error":"API key invalid","api-key":"your_key","type":"invalid"}`
- **Environment value:** `NCBI_API_KEY='your_key'` — a literal placeholder, not a real key.
- **Why this mattered:** `scripts/04_literature_independence.py:15` does
  `os.environ.get("NCBI_API_KEY", "")` and `:24` attaches it whenever the string is
  truthy. `"your_key"` is truthy, so **every** PubMed request in stage 04 would have
  returned HTTP 400, `raise_for_status()` would have raised, and the bare
  `except Exception` in `main()` would have swallowed it per compound
  (`print(...); time.sleep(2)`). The stage would have "completed" while writing a
  literature file that was empty or missing almost every compound — a silent, total
  failure of the heaviest stage. This interacts with TD-009.
- **Resolution (no fabrication):** stage 04 is run with `NCBI_API_KEY` explicitly cleared,
  so the script takes its documented unauthenticated path (`0.34 s` sleep, PubMed's 3 req/s
  limit) instead of sending an invalid key. No key was invented, and no code was changed.
- **Cost of the workaround:** stage 04 runs at 3 req/s rather than 10 req/s.
- **Follow-up for the user:** obtain a real key from
  https://account.ncbi.nlm.nih.gov/settings/ and put it in `.env`, or unset the variable.
  Leaving the placeholder in the environment will break any future stage-04 run.
- **Status:** RESOLVED for this run by clearing the variable. The underlying environment
  misconfiguration is **still present in the user's shell** and is recorded as TD-016.

### E-009 · ISSUE · **PRODUCED WRONG DATA** · Semantic Scholar 429 silently zeroed citation edges
- **Discovered:** 2026-10-05, by comparing an interim checkpoint against the final output.
- **Cmd:** `./venv/bin/python scripts/04_literature_independence.py` (ran to completion,
  exit 0, **"0 errors" reported**).
- **Symptom:** the stage reported success. Shared-author edges scaled normally with cohort
  size (351 at 67 compounds → 748 at 141), but citation edges were **frozen at exactly 68**
  across both checks.
- **Diagnosis (evidence, not inference):**
  - Citation edges accrued only for checkpoint positions 0–11. Last compound with any
    citation edge: **Isradipine (position 11 of 140)**.
  - **110 subsequent compounds had ≥2 papers**, so citation edges were possible for them
    and none were found.
  - Live probe during diagnosis: `GET api.semanticscholar.org/graph/v1/paper/PMID:*/citations`
    → **`HTTP 429 {"message":"Too Many Requests"}`**.
- **Root cause:** `fetch_citing_pmids()` (`scripts/04_literature_independence.py:64`) does
  `if r.status_code != 200: return set()` inside a bare `except Exception: return set()`.
  A 429 is therefore indistinguishable from "this paper has no citations". This is exactly
  the failure mode predicted in TECHNICAL_DEBT TD-009 — now observed in a real run.
- **Scientific impact — this one DID corrupt output.** Missing citation edges mean fewer
  graph edges, hence MORE connected components, hence an inflated
  `effective_independent_count` and `independence_ratio`. The bias applies to ~129/141
  compounds but **not** to the first 12 — so the distortion is *inconsistent across the
  cohort*, which is worse than a uniform bias. The "lowest independence ratio" ranking in
  the stage output (Isradipine 0.333, Desmopressin 0.400, Sildenafil 0.500,
  Alpha-Linolenic Acid 0.571, Succinic acid 0.556) is dominated by early-position compounds
  and is therefore partly an artefact of **processing order, not literature structure**.
- **Evidence preserved:** `data/_literature_checkpoint_THROTTLED_EVIDENCE.jsonl` and
  `data/literature_independence_THROTTLED_EVIDENCE.csv` (both gitignored).
- **Action:** minimal fix to `fetch_citing_pmids` (retry/backoff honouring `Retry-After`,
  plus explicit failure accounting so throttling can never again masquerade as "no
  citations"), then a full re-run of stage 04. **Step 06 was NOT run on the contaminated
  data**; no metric was computed from it.
- **Status:** see E-009-FIX below.

### E-009-FIX · RESOLVED · Stage 04 hardened and re-run
- **Diagnosis of rate:** probed Semantic Scholar at 2.5 s spacing → **6/6 HTTP 200**
  (100 citations each). The original `time.sleep(0.4)` was simply too aggressive for the
  unauthenticated endpoint; the service is reachable, it was being throttled.
- **Minimal fix applied to `scripts/04_literature_independence.py`:**
  1. `fetch_citing_pmids()` now retries 429/5xx with exponential backoff + jitter, honours
     `Retry-After`, and **raises `SemanticScholarUnavailable`** when a lookup cannot be
     completed — instead of returning `set()`, which was indistinguishable from
     "this paper has no citations".
  2. HTTP 404 is still treated as a genuine empty result (paper not in S2), which it is.
  3. Module-level `S2_STATS` accounting (`ok` / `empty` / `rate_limited` / `failed`).
  4. New per-compound output fields `citation_lookup_failures` and
     `citation_coverage_complete`, so a partially-covered compound is identifiable in the
     CSV rather than silently wrong.
  5. End-of-run coverage report with an explicit WARNING that `independence_ratio` is an
     **upper bound** for any compound with incomplete coverage.
  6. `S2_SLEEP` (default 2.5 s, env-overridable) replaces the hardcoded 0.4 s.
- **Fix tested before re-running** (mocked transport, no network):
  persistent 429 → raises after 6 attempts ✔; 404 → genuine `set()` ✔; 429-then-200 →
  recovers ✔; `S2_STATS` accounting correct ✔.
- **Re-run:** contaminated checkpoint deleted (evidence copies retained), stage 04 relaunched
  with `S2_SLEEP=2.5`.
- **Methodology unchanged:** `MAX_PAPERS_PER_COMPOUND`, the two edge types, and the
  connected-component definition of independence are all untouched. Only transport
  reliability and failure visibility changed.

### E-010 · BLOCKER · **CONTAMINATED RESULTS** · ClinicalTrials.gov intervention-name collisions
- **Discovered:** 2026-10-05, during case-study verification of the real top-ranked candidates.
- **Finding:** `scripts/03_clinicaltrials_groundtruth.py` queries `query.intr=<compound>` and
  verifies client-side that the trial's **condition** is Parkinson's (`is_actually_pd`), but
  performs **no equivalent check on the intervention**. ClinicalTrials.gov expands
  intervention queries by chemical class, prodrug/metabolite relation, pharmacological class
  and excipient content, so a query returns trials of entirely different drugs.
- **Verified instances (primary records fetched from the API):**
  - `Phenol` → NCT06596876 (HRG2010 carbidopa/levodopa), NCT04380142 (ABBV-951),
    NCT00399477 (rasagiline), NCT02577523 (ND0612). Levodopa is chemically a phenol.
  - `Norepinephrine` → NCT03567447, NCT02897063, NCT03173781 — **all Droxidopa** (an NE prodrug).
  - `Dopamine` → NCT00105508 (Sarizotan), NCT01264861 (Safinamide), NCT00666653 (pramipexole).
  - `Mannitol` → NCT01927055, NCT01176240 — **Droxidopa** (mannitol = excipient).
  - `Acetylsalicylic acid`, `Pregabalin` → NCT02670161, a registry study whose intervention
    field reads "Listed for each disorder below, up to three drugs per disorder".
- **Quantified** by the new diagnostic `scripts/check_intervention_match.py` over all 451
  (compound, trial) pairs: **177 (39%) of trial links have no intervention naming the
  compound**; 16 are catch-all registry studies; **60 of 178 compounds have no naming trial
  at all**; **48 of the 141-compound evaluable pool (34%)** and **7 of the 30 positive
  labels (23%)** are affected.
- **Scientific impact:** this contaminates BOTH the clinical-maturity feature AND the
  ground-truth labels. Because positives are affected, it biases the AUROC measurements
  themselves, not merely the ordering. **Three of the top five ranked candidates
  (Norepinephrine #2, Phenol #3, Dopamine #5) are artefacts.**
- **NOT fixed, deliberately.** The obvious fix mirrors the existing `is_actually_pd` pattern
  (verify the compound name appears among the trial's interventions / otherNames), but
  applying it would change the project's inclusion criteria and therefore its ground-truth
  label set. That is a methodological decision for the project owner, not an autonomous one,
  and it would invalidate the metrics reported for this run rather than repair them.
- **Delivered instead:** a read-only diagnostic (`check_intervention_match.py` →
  `data/intervention_match_check.csv`) that quantifies the contamination per compound and
  per trial without altering any stage's behaviour.
- **Status:** OPEN — recorded as TECHNICAL_DEBT TD-018. **The 2026-10-05 ranking and AUROC
  figures must not be published until this is resolved.**

### E-011 · ISSUE · RESOLVED · `API_FAILURE` misapplied to observational studies
- **Cmd:** `./venv/bin/python scripts/03_clinicaltrials_groundtruth.py` (corrected run,
  2026-10-05 08:45)
- **Symptom:** stage summary reported `ClinicalTrials searches ok/failed/retried: 1483/0/0`
  and "Compounds whose SEARCH failed (API): 0", yet the audit contained **19 rows with
  `outcome = API_FAILURE`** — an internal contradiction.
- **Diagnosis:** all 19 rows carried an `nct_id`, so the search had succeeded. Live probe of
  5 of them (NCT07402928, NCT03538262, NCT01316666, NCT06161636, NCT02860338) returned
  **HTTP 200** with `studyType = OBSERVATIONAL`. The search response simply carries no
  structured intervention list for these records. `intervention_matcher.match_trial` mapped
  `interventions is None` to `API_FAILURE`.
- **Why it matters:** conflating "record retrieved but has no intervention data" with
  "record could not be retrieved" overstates outage rates and understates genuine data gaps
  — exactly the distinction Phase 5 requires be kept.
- **Fix:** `interventions is None` with `fetch_ok=True` now yields `UNVERIFIABLE`.
  `API_FAILURE` is reserved strictly for `fetch_ok=False`.
- **Tests:** `test_missing_interventions_field_is_unverifiable_not_api_failure`,
  `test_api_failure_requires_fetch_failure`. Suite: `Ran 146 tests ... OK`.
- **Impact on scientific output: none.** Neither outcome qualifies as evidence, so the
  pre/post cohort CSVs were identical either way. Only the audit labelling was wrong.
  Stage 03 was re-run anyway so the audit provably matches the code.
### E-012 · ISSUE · RESOLVED · ChEMBL synonym lists reintroduced class collisions
- **Discovered:** 2026-10-05, by running the independent diagnostic
  (`scripts/check_intervention_match.py`) against the CORRECTED stage-03 output and
  verifying that every residual flag was explained rather than assuming it was benign.
- **Context:** the diagnostic flagged 9 residual `NAME_NOT_FOUND` links. Seven were benign
  (legitimate trade names the crude diagnostic cannot see: Premarin, Zonegran, Rifadin,
  Ursonorm, Datscan, L-DOPS, n-acetyl cysteine). **Two were genuine false positives:**
  - `Escitalopram` matched NCT04590612 via ChEMBL synonym **"citalopram"**. Citalopram is a
    *different drug* (racemate vs the S-enantiomer). 3 accepted links, all pre-cutoff.
  - `Tetracycline` matched NCT05492019 via ChEMBL synonym **"doxycycline"**. Doxycycline is
    a *different drug* of the same class. 1 accepted link, **post-cutoff — i.e. a false
    POSITIVE LABEL.**
- **Root cause:** ChEMBL synonym lists (via Open Targets) sometimes contain the name of a
  related-but-distinct drug. Using them as match aliases reintroduced exactly the
  class-collision problem the matcher exists to prevent — arriving through the synonym
  source rather than through ClinicalTrials.gov search expansion.
- **Fix (general, no blacklist):** `build_alias_set` gained `ambiguous_names`. Stage 03
  passes the normalised names of every OTHER study compound; an alias that is itself
  another compound's name is ambiguous by construction and is refused. The compound's own
  name is never filtered.
- **Verified discrimination:** of the 9 residuals, exactly the 2 problematic aliases
  ("citalopram", "doxycycline") collide with another candidate name; all 7 legitimate trade
  names do not. The rule separates them without naming any compound.
- **Tests:** `TestAmbiguousAliasFilter` (5 tests), including a before/after assertion that
  the Escitalopram/Citalopram link flips MATCHED → NO_MATCH. Suite: `Ran 151 tests ... OK`.
- **Action:** stage 03 re-run with the filter; downstream regenerated.
