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
- **Update 2026-10-15 — RESOLVED (record was stale).** Fixed the same day by Gate 2
  (`scripts/intervention_matcher.py`) and the clean rerun (CHANGES.md "2026-10-05 (afternoon)";
  TECHNICAL_DEBT TD-018 "RESOLVED": unsupported links 177/451 → 7/252, all explained aliases).
  Residual role/intent issues are tracked separately (TD-023, TD-032).

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

## 2026-10-12

### L-001 note · SUPERSEDED
L-001 ("molecular dimension not evaluated on the real cohort") is no longer true: the
2026-10-05 runs evaluated it on the 141- and then the corrected 90-compound cohort
(CHANGES.md). The original entry is kept unchanged above, per this log's no-delete rule.

### E-013 · ISSUE · RESOLVED · Stage 08 `--fresh` kept stale checkpoint records
- **Found by:** offline audit test (`tests/test_molecular_vps_audit.py::TestStep08FreshRun`),
  run as an `expectedFailure` that reproduced it (stale score 0.1 emitted, new 0.9 dropped).
- **Cause:** `scripts/08_molecular_pathway.py` — `--fresh` skips loading the checkpoint but
  appends to it; the collect loop kept the first record per drug.
- **Fix:** collect keeps the last record per drug. No file truncation, so no checkpoint work
  can be lost. Current data unaffected (no duplicate drugs in `data/_molecular_checkpoint.jsonl`).
- **Test:** `expectedFailure` removed; suite `Ran 211 tests ... OK`. TECHNICAL_DEBT TD-028.

### E-014 · ISSUE · OPEN · Residual Gate-2 false match via background-therapy otherNames
- **Cmd:** `GET https://clinicaltrials.gov/api/v2/studies/NCT00605683` (2026-10-12).
- **Observed:** NCT00605683 (MOTION) tests **safinamide** as add-on to a dopamine agonist;
  "Lisuride (not approved in US)" appears only among permitted background agonists. The
  audit accepts it for Lisuride (`token_othername`, qualifies=True) and it is Lisuride's
  phase-3, n=679 entry in `clinical_maturity_precutoff_clean.csv`.
- **Impact:** inflates Lisuride's clinical-maturity feature; Lisuride's label (0) is unaffected.
  Same class as the Mannitol/placebo case already handled by control-arm exclusion.
- **Not fixed:** changing the matching policy changes inclusion criteria (owner decision).
  `docs/CASE_STUDIES.md` §4, which cited it as a lisuride trial, is corrected. TD-023.

### E-015 · ISSUE · UNVERIFIED · Bootstrap CIs in the docs cannot be reproduced
Neither `[-0.024, +0.150]` (TD-020/README) nor `[-0.025, +0.148]` (CASE_STUDIES) is
reproduced by default_rng or RandomState paired percentile bootstraps (2000, seed 42); no
script exists. Point estimate +0.0588 reproduced exactly. Details in the TD-020 addendum.

### L-002 · LIMITATION · UI not visually inspected in a browser
- The Claude-in-Chrome extension was not connected (`tabs_context_mcp` → "Browser extension
  is not connected"), so the dashboard was not viewed in a browser this session.
- **Verified instead:** server launched locally; every `/api/*` endpoint queried with curl
  against the real `data/`; every view's HTML generated by running the page's own JS in
  Node against the live API (no `undefined`/`NaN`/error output); 23 unit tests.

## 2026-10-13

### E-016 · ISSUE · RESOLVED · Dashboard security and rendering defects
Path disclosure in error responses, silent non-loopback bind, no Host-header check,
query-steered graph read, permissive CSP / missing headers, invalid JSON on NaN, Drug
Explorer list never rendered (listener race), low-contrast badges. Each reproduced, fixed
and covered by a regression test — details in TECHNICAL_DEBT.md TD-029.

### L-003 · LIMITATION · Browser cannot reach the local server (supersedes the L-002 cause)
- The Chrome extension connected this time, but navigation to `http://127.0.0.1:8765/`
  returned `ERR_CONNECTION_REFUSED` twice, both with the server sandboxed and unsandboxed,
  while `curl` from the same machine got HTTP 200 and `lsof` showed the listener on
  `127.0.0.1:8765`. The automated browser evidently does not share this host's loopback.
  Not retried further.
- **Verified instead:** real `ui/app.js` executed in Node with a DOM stub against the live
  server (Drug Explorer list 400 items, search filter, empty state, selection); endpoint sweep
  of all static/doc/API routes plus all 1,327 compounds.
- **Outstanding:** visual check at desktop and mobile width — to be done by the owner.

## 2026-10-13 (research sprint)


**Update 2026-10-15:** still reproduces. The Claude-in-Chrome tab gets an error page for
`http://127.0.0.1:8765/`. **Workaround used:** the local Google Chrome in headless mode
(`--headless=new --dump-dom` / `--screenshot`) rendered the dashboard with its JavaScript
executed. That is browser rendering on this machine, but not an interactive session.

### E-015 · RESOLVED (procedure) · Bootstrap CI now reproducible
The original numbers came from uncommitted code and cannot be regenerated exactly; the
versioned procedure (`scripts/bootstrap_auroc_ci.py`) reproduces them within Monte-Carlo
variation (TECHNICAL_DEBT.md TD-020 addendum 2).

### E-017 · INCIDENT · RESOLVED · Stages 05 and 06 executed by a `--help` check
- During final verification, `python scripts/05_safety_signal.py --help` and
  `python scripts/06_vps_fusion.py --help` were run to check CLIs. Neither parses arguments,
  so both stages ran in the repository; the output filter hid it.
- **Effect:** 05 rebuilt `data/safety_signal.csv` from its checkpoint (content unchanged; all
  90 compounds already checkpointed, so **no openFDA request**). 06 rewrote its 8 outputs with
  the TD-031 code: 7 byte-identical; `data/vps_scores_v2.csv` gained the
  `safety_label_missing` column.
- **Recovery:** `data/vps_scores_v2.csv` restored from a scratch copy byte-identical to the
  sprint baseline (md5 `2744e746…`). All `data/` files re-checked against the baseline
  checksums: identical except the two new files of this sprint. File mtimes of the 9 files
  changed (content did not), which can affect the dashboard's mtime-based "stale" status.
- Prevention: TD-034.

### B-002 · BLOCKER · Literature and safety cutoff enforcement need re-retrieval
Stage 04 persists no per-paper dates and stage 05 no label dates (TD-033). Enforcing the
cutoff requires re-running stage 04 (hours, Semantic Scholar) with a separate checkpoint and
re-querying label versions — methodology decisions for the owner, not done.

### E-018 · ERROR · RESOLVED · Stage 06 crashed mid-run under the first D-004 implementation
- The first (available-case) implementation raised `ValueError` in the grid search: weight
  vectors such as safety = 1.0 cannot score the 7 unlabelled compounds. After a guard was
  added, it raised again for the molecular-only baseline (16 no-target compounds).
- **Effect:** the second run had already rewritten `data/grid_search_5d_log.csv` before
  crashing (non-atomic outputs, TD-037). No other output changed (checked by md5).
- **Resolution:** the available-case rule was replaced by the neutral rank (D-004). The final
  06 run completed and rewrote all outputs consistently. Pre-change outputs are in
  `data/_archive_pre_D003_D004_2026-10-15/`.

### E-019 · INCIDENT · RESOLVED · Three documentation files truncated by a newline-trimming command
- **Cause (Claude's error):** the command was
  `python3 -c "open(p,'w').write(open(p).read().rstrip('\n')+'\n')"`. Python evaluates
  `open(p,'w')` (which truncates the file) before the argument `open(p).read()`, so
  `TECHNICAL_DEBT.md`, `development_log/ERRORS_AND_BLOCKERS.md` and `docs/CASE_STUDIES.md`
  were each reduced to a single newline (2026-10-15). The tests do not read these files,
  so the next 314-test run did not detect it.
- **Detected:** the next sprint's grep found no content.
- **Recovery:**
  1. Base = the staged (index) versions. These are verified **byte-identical** to the content
     captured by `cat` at the start of the 2026-10-12 session (TECHNICAL_DEBT +
     ERRORS_AND_BLOCKERS), and equal in content and line count for CASE_STUDIES.
  2. All 22 later edit commands were replayed from the session transcript, restricted to these
     three files.
- **Verification:**
  - The reconstruction reproduces every line count that `git diff --check` reported during
    the sessions (TD 579/606, ERRORS 417, CASE 546/595 before trimming).
  - Section line numbers match earlier grep outputs (E-017 at 389, §8.9 at 413, §9 at 426).
  - Restored md5: TD `1d9e758d…`, ERRORS `72494c13…`, CASE `693753d3…`.
- **Residual risk:** an edit made outside the recorded commands between 2026-10-12 and
  2026-10-15 (for example, by hand) would not be recovered. No evidence of such an edit was found.
- **Prevention:** read and write as separate statements; check line counts after every
  bulk documentation edit.

### E-020 · ERROR · RESOLVED · Dashboard case-status table overwritten by the 10d ledger
- **Found by:** the real-browser (Chrome DevTools-protocol) check, 2026-10-15. `viewCases`
  assigned `ledger = …` for the 10d ledger after building the status table, which discarded the
  table. API tests passed because the defect was in client rendering only.
- **Fix:** append (`ledger += …`). Regression test
  `tests/test_ui.py::TestCaseStatusEvaluationRisks::test_cases_view_appends_panels_instead_of_overwriting`.
  The browser check then passed (28/28).

### E-021 · HIGH · Stages 04 and 05 silently dropped a compound whose request failed — RESOLVED 2026-10-15
- **What:** the per-compound `except Exception` printed the error and continued. The failed compound
  had no row, the stage finished with exit 0, and downstream code could not tell "failed" from
  "never queried".
- **Fix:** `record_failure()` appends `{compound_name, error_class, message, time_utc}` to
  `data/_safety_failures.jsonl` or `data/_literature_failures.jsonl` (API keys redacted). The
  compound is still not checkpointed, so a re-run retries it. The stage prints INCOMPLETE and exits 1.
  Agents 10f and 10h report such compounds as RETRIEVAL_FAILED.
- **Tests:** `tests/test_safety_evidence_agent.py::TestStageFailureRecording`;
  `tests/test_safety_missingness.py::TestStep05Main` was updated to expect exit 1 and the
  failure record. Neither stage was re-run; existing outputs are unchanged.

### E-022 · MEDIUM · Agent 10c first passed the registry intervention name as a compound alias — RESOLVED 2026-10-15 (before persistence)
- **What:** passing `matched_intervention` (for example "Safinamide (as add-on therapy)", whose
  otherNames list lisuride) as an alias made `trial_role` call background-therapy matches
  THERAPEUTIC_TEST (Lisuride's NCT00605683, the E-014 pattern).
- **Fix:** aliases are now the compound name plus the matched alias only. Regression test
  `test_clinical_evidence_agent.py::test_background_othername_alias_not_counted_as_test`, and the
  persisted Lisuride check.
- **Related, not changed:** the `annotator_verdict` column of `data/feature_trial_roles_td038.csv`
  (D-020) was computed with the same three aliases. Its hand adjudication (category and P1 verdict)
  came from reading the records and is unaffected; see TD-039.

### E-023 · LOW · Dashboard called a missing 10h output "inputs unchanged" — RESOLVED 2026-10-15
Found by the headless-browser fixture check (failure states on a copy of the data). With
`completeness_gaps.json` absent, the panel still printed the green freshness note. The note is now
shown only when an output exists (browser check 14).

### E-024 · MEDIUM · Run tracker propagated MODIFIED downstream and hid a failed attempt behind STALE — RESOLVED 2026-10-15 (before release)
Found by the live browser workflow on a fixture copy of the data.
1. After a hand edit of an upstream output, VPS stayed STALE even after a successful re-run that
   consumed that exact file. **Fix:** only STALE propagates. A dependant built on a MODIFIED output
   gets an `unvalidated_upstream` warning instead.
2. When a run failed and its inputs had also changed, the banner showed only STALE. **Fix:** a
   separate `latest_attempt_failed` flag drives "Latest VPS attempt FAILED".

Regression tests: `tests/test_run_tracking.py::TestPropagationRules`.

### E-025 · LOW · Evaluation report fingerprinted 3 of the 7 files it reads — RESOLVED 2026-10-15
A change to `vps_variant_results.csv`, `baseline_results_v2.csv`, `ablation_results_5d.csv` or
`bootstrap_ci_equal5d_vs_4d.csv` did not mark the report stale. It now records all 7. The report
was regenerated; every reproduced metric is unchanged.

### E-026 · MEDIUM · Stage 06 robustness and flag defects (latent; no published score affected) — RESOLVED 2026-10-15
- Duplicate compound rows in any input duplicated a candidate.
- ±inf raw values were ranked as extremes.
- Median-imputed proximity was reported as measured.

Fixed in `scripts/06_vps_fusion.py`; tests in `tests/test_vps_correctness.py`; see D-024.

### E-027 · MEDIUM · A crashed stage 04/05 could be recorded as a fresh PARTIAL success — RESOLVED 2026-10-19
`run_stage.py` treated any non-zero exit of 04/05 as PARTIAL. A traceback also exits 1 and leaves
the previous outputs in place, which validated, so the crash became a new `last_success` built on
the new input fingerprints. Now PARTIAL requires exit 1 and every output rewritten; an exit-0 run
that rewrote nothing is PARTIAL with `NOT_REWRITTEN`. Tests: `tests/test_run_tracking.py`.

### E-028 · MEDIUM · Live polling could hang forever on a non-answering server — RESOLVED 2026-10-19
`fetch` had no timeout. A suspended server accepts the TCP connection and never answers, so the
poll awaited indefinitely and live updates stopped silently. `api()` now aborts after 15 s and
the poll loop always reschedules.

### E-029 · MEDIUM · Agents crashed instead of writing FAILED when every unit failed — RESOLVED 2026-10-19
10c, 10d and 10f reported per-unit failures as warnings, so `envelope()` rejected the FAILED
status and nothing was written; the previous output stayed, looking current.

### E-030 · MEDIUM · Agent audit 2026-10-19: failures and gaps read as findings — RESOLVED 2026-10-19 (except TD-042, TD-043)
- 10f: an unparseable HTTP 200 was NO_RECORD; partial query failures gave SUCCESS; failed caches were never retried.
- 10e: disagreement inside one dependent group was labelled as independent studies.
- 10c: a failed `--fetch` replaced the cache with an empty one.
- 10d: sources with nothing comparable were reported as agreeing; ratio estimates were compared with 0.
- 10g/10h: empty or missing inputs gave SUCCESS.
- 10a: no returned PMID gave NO_EVIDENCE; graph mode credited unrelated papers.
- 10b: Open Targets failure records (score 0.0) were checkpointed as done and accepted as measured.
No published VPS value was affected: the real data contain none of these failure records.

### E-031 · MEDIUM · Stage 02 proximity was not reproducible between runs — RESOLVED 2026-10-19 (code); published file unchanged
`generate_random_target_set` iterated a `set` of target IDs. Set order depends on per-process
string hashing (PYTHONHASHSEED), so the seeded random draws differed between otherwise identical
runs. proximity_z moved by up to 2.0 and `n_random` by 2.
- Fix: iterate in sorted order and sort the degree bins. Three hash seeds now give byte-identical output. Test: `tests/test_proximity_determinism.py`; the unfixed code gives 3 distinct outputs.
- Impact, measured over 10 seeds: 5D AUROC range 0.769–0.783; ranks Spearman ≥ 0.995 vs published.
- `data/network_proximity.csv` (a protected VPS input) is one earlier draw and is not regenerated.

### E-032 · LOW · Stage 04b could not run under the runner (exit 2) — RESOLVED 2026-10-19
Its required `--compound` was not in the registry. Added `run_args: ["--compound", "Droxidopa"]`.
Test `test_run_tracking.py::TestRegistryRunArgs` checks every stage's required arguments.

### B-002b · EXTERNAL · Stages 01, 03, 03c, 04b and diag need live services and keep no response cache — OPEN
*(ID was a duplicate of B-002 above; renamed B-002b on 2026-10-20 so references are unambiguous.)*

**Update 2026-10-19 (C-86): all five re-run LIVE in an isolated copy** (`data/_runs/live_stages_20261019/`,
`live_stage_check.py`): 01 SUCCESS and 00 SUCCESS (outputs byte-identical to the protected files); 03 SUCCESS
(1483/1483 searches, 0 failed; the 67 label links and the 57 clean label links are the same sets as the frozen ground
truth; registry drift: 2 status changes, e.g. Terazosin NCT07288450 now WITHDRAWN, Terazosin keeps 4 other label
trials; Ioflupane I 123 feature links changed, max phase unchanged; empty phase written as "NA" vs "" in the frozen
file, same meaning); 03c SUCCESS; diag SUCCESS; 04b exit 1 by design: its provenance guard refused because today's
PubMed/Semantic Scholar content gives 17 components / 2 shared-author edges vs the checkpoint's 16 / 4 (content drift;
stage 04's PMIDs were never persisted, TD-021). Nothing protected was overwritten. Still no response cache for 03/03c.
- Stage 01 downloads Hetionet from zenodo.org.
- Stages 03, 03c and diag query ClinicalTrials.gov per compound or trial.
- Stage 04b queries PubMed and Semantic Scholar.

With the network unavailable, 03 would retry 1483 searches at about 15 s each. These stages could not be re-executed offline. Their persisted outputs are the inputs for the offline end-to-end runs (`data/_runs/mission_20261019/e2e_offline_*.json`).

### E-033 · HIGH (latent) · Stage 03 published features and labels without the compounds whose search failed — RESOLVED 2026-10-19
After retries, a failed ClinicalTrials.gov search was recorded as API_FAILURE in the audit. The
stage still wrote `clinical_maturity_precutoff.csv` and `ground_truth_postcutoff.csv` without those
compounds and exited 0, so a tracked run would publish a silently smaller pool. An outage also meant
about 6 h of retries (~15 s × 1483 compounds).
- Fix: when any search failed, nothing is written and the stage exits 1; the runner keeps the last valid files.
- `--accept-failed-searches` is an explicit opt-in to publish anyway.
- After 10 consecutive failures the registry is treated as unreachable and the stage aborts in about a minute.
- Tests: `tests/test_stage03_failure_handling.py`.
- The current outputs are unaffected: the published audit records how the existing outputs were produced.

### E-034 · HIGH (latent) · Stage 03c turned failed study-type lookups into "not interventional" — RESOLVED 2026-10-19
`check_studytype.py` stored a failed lookup as study type `ERROR`. `filter_by_studytype.py` then
dropped that trial from the clean features and labels as non-interventional. A tracked 03c run also
never produced its declared `*_clean.csv` outputs.
- Fix: any failed lookup means nothing is written and exit 1, with a 10-consecutive-failure breaker.
- The filter refuses a check file containing `ERROR` rows.
- On success, 03c now runs the filter.
- The persisted check file has 0 ERROR rows (252 trials). On it, the filter reproduces both protected clean CSVs byte for byte.

### E-035 · MEDIUM (latent) · The runner allowed conflicting concurrent launches — RESOLVED 2026-10-20
`scripts/run_stage.py` recorded a new RUNNING attempt without checking for one already in progress. Two launches
of the same stage (or of a stage and its upstream/downstream) both wrote into `data/`, and the second overwrote
the first's `last_attempt`; the dashboard could not show the conflict.
- Fix: the check and the claim happen under one manifest lock; a conflicting launch raises `StageBusy`
  (CLI exit 3), records nothing and creates no run directory. A dead process does not block (it is reported as an interrupted attempt).
- Tests: `tests/test_run_tracking.py::TestConcurrentLaunch` (6; 4 fail on the old runner).
- Live check in an isolated copy: second launch of a running 10h and a launch of its upstream 10g both refused.

### E-036 · MEDIUM · Five agents were not invalidated when stage 06 went stale — RESOLVED 2026-10-20
10b, 10c, 10d, 10f and 10g read `data/vps_scores_v2.csv` but the registry did not list 06 in `depends_on`. When an
input of 06 changed (06 STALE), those agents stayed SUCCESS/fresh on the dashboard and in `run_stage.py --status`
until 06 was re-run and rewrote the file; the E-035 concurrency guard also could not see the 06 relationship.
- Fix: "06" added to their `depends_on` (no status change on the live root: 06 is ADOPTED and unchanged).
- Tests: `TestRealRegistry::test_every_consumed_stage_output_is_an_upstream_dependency` and
  `::test_stale_vps_propagates_to_every_agent_that_reads_it` (both fail on the old registry).
- Reproduction: isolated copy, one byte appended to `label_role_exclusions.csv` -> 06 STALE, 10b/10d/10f SUCCESS (before);
  all STALE (after).

### E-037 · MEDIUM · Stages read and wrote files the registry did not declare — RESOLVED 2026-10-20
A source scan and an isolated write-containment run (each agent via the runner; every changed file compared with its
declared outputs) found: 06 `feature_role_exclusions.csv` (optional), 07 `vps_scores_v2.csv`, eval `reproducibility.json`
(10e output, no dependency on 10e), 10f `_safety_failures.jsonl`, 10g two cached XMLs, 10h clinical clean, **human
TD-038 roles**, failure logs and five credibility files (10h depended on 10a-all only), and 10a writing four case files
while declaring one. Changes to any of them never made the consumer STALE; three 10a outputs were never fingerprinted,
validated or backed up. Also, inputs/outputs added to the registry after a stage's last success were never compared.
- Fix: declarations + dependencies (C-103); runner warns about declared files absent from the last success (C-102).
- Tests: static scan of every stage script; 10h glob coverage; one producer per output; runner warnings.
- Re-runs: 10a (content changed only by C-80's `temporal_source` field — the old outputs predated that code), 10b-10e,
  10g, 10h, 07, review (identical excluding timestamps). `eval` NOT re-run: it rewrites the protected
  `vps_evaluation_report.json`; its untracked-input warning stays visible for the owner.

### E-038 · MEDIUM · A corrupt run manifest broke the dashboard and CLI — RESOLVED 2026-10-20
`json.load` errors propagated: `/api/status` HTTP 500, CLI traceback, no diagnostic. Now `ManifestError`; every stage
UNKNOWN (never fresh); runs refused without touching the file; `--check-manifest` (read-only, exit 2); fsync before the
atomic rename. Tests: `TestCorruptManifest` (4), `TestCorruptManifestInUI` (2).

### E-039 · MEDIUM (latent) · Outputs above the 50 MB backup limit were overwritten without a restore path — RESOLVED 2026-10-20
Stage 01 writes `hetionet_edges.csv` (89 MB) in place; the runner skipped its backup with a warning. Limit raised to
512 MB; a non-staged run whose existing outputs still exceed it is refused (`UnsafeRun`, exit 4). Tests: `TestBackupLimit`.

### E-040 · MEDIUM · Status pill said "Pipeline results current" for UNKNOWN/UNTRACKED/NOT_RUN stages — RESOLVED 2026-10-20
### E-041 · LOW · Two concurrent polls when the tab became visible during a poll — RESOLVED 2026-10-20


### E-042 · LOW · First launch after a server restart was rejected (stale session nonce) — RESOLVED 2026-10-20
The page kept the previous server's nonce; the click got 403 and the user had to click again. The client now renews
the session and retries once (a cross-site page still cannot read a nonce). Found by the browser end-to-end run.

### E-043 · LOW (latent) · Live refresh could swallow a click — RESOLVED 2026-10-20
The Live pipeline view re-rendered on every poll, replacing buttons that a user might be pressing. A background
refresh that produces identical markup now leaves the DOM alone.

### B-003 · OPEN · The approved scores are not byte-reproducible from raw sources with the current code
An isolated from-source rerun (stage 02 re-drawn by the now-seeded Monte Carlo, E-031) gives AUROC 0.7763 / 4D 0.7049
vs the approved 0.7754 / 0.7002 (same 14 positives, same top-10 set). The approved scores ARE reproduced exactly from
the persisted inputs (`vps_verify`). The current stage 06 also writes a `dimensions_imputed` column the approved file
lacks. Re-publishing 06/02/eval is an owner decision (protected outputs).

### E-044 · MEDIUM · Structurally malformed manifest crashed the dashboard (HTTP 500) — RESOLVED 2026-10-20
### E-045 · MEDIUM · Manifest run_dir could make the dashboard display any log.txt (path traversal) — RESOLVED 2026-10-20
### E-046 · MEDIUM · Launch-record log path followed blindly (path traversal) — RESOLVED 2026-10-20
### E-047 · MEDIUM · No stage timeout: a hung stage stayed RUNNING forever — RESOLVED 2026-10-20 (timeout_s)
### E-048 · LOW · Unwritable launch directory gave a non-actionable error — RESOLVED 2026-10-20
### E-049 · MEDIUM · Killed runner: half-written output reported as an outside edit, orphan untracked, no recovery — RESOLVED 2026-10-20 (child_pid, --restore)
### E-050 · LOW · Run-all BLOCKED dependants visible only inside the launch log — RESOLVED 2026-10-20
Details, reproductions and tests: `docs/autonomous_runs/runtime_reliability_20261020T1010Z/RUNTIME_RELIABILITY_REPORT.md`.

### E-051 · LOW · Finished dashboard launches stayed zombie processes until polled — RESOLVED 2026-10-20
The server reaped a launched runner (and recorded its exit code) only when /api/launches or a new launch polled it.
A reaper thread per launch now waits, reaps and records immediately. Test: `TestRunnerReaped`; browser timeout lifecycle.

### E-052 · MEDIUM · Dashboard headline claimed "All results current" beyond what the tracker verifies — RESOLVED 2026-10-20
The headline merged runtime success, input freshness, source-data age and scientific validation, and ignored untracked inputs.
It now comes from the tracker state, and the four facts are shown separately; source dates that were not recorded are shown as "not recorded". Test: `tests/test_ui_quality.py`.

### E-053 · LOW · Agent card hid a failed latest attempt when the inputs had also changed — RESOLVED 2026-10-20
A stage showed "Inputs changed" only. Its latest attempt had failed and the previous output was kept.
The card now also shows "Run failed". Found by browser suite drive11 (6b).

### E-054 · MEDIUM · A stage input never fingerprinted still counted as "current" — RESOLVED 2026-10-20
`eval` reads `data/reproducibility.json`, which its last success did not fingerprint; the overall state and header pill were CURRENT (green).
Now `VERIFIED_WITH_GAPS` with explicit wording; untracked outputs are no longer described as inputs. Test: `tests/test_agent_failure_modes.py::TestUnfingerprintedInputIsNotCurrent`.

### E-055 · MEDIUM · Agent pipeline defects found by the eight-agent audit — OPEN (owner)
A-1 partial 04p/05h/10a-all results discarded (exit 1 → FAILED); A-2 10g accepts a header-only literature CSV as SUCCESS; A-3 10d skips malformed molecular lines silently; A-4 10h uses FAILED upstream outputs and ignores 10b; A-5 stage 08 has no timeout; A-6 non-atomic writes; A-7 absent inputs not fingerprinted.
Reproductions: `docs/autonomous_runs/biomedical_ux_agent_audit/AGENT_CONTRACT_AUDIT.md`. All fail safe today; none was patched (pipeline code, outside the UI scope).

### E-055 · update 2026-10-20 — A-1 to A-7 RESOLVED (code + tests); see C-121.

### E-056 · HIGH · Stage 03 kept only the first 20 search results per compound — CODE FIXED 2026-10-20, COHORT REBUILD OPEN (owner)
`search_trials` used `pageSize: 20` without `nextPageToken`. 12 compounds were truncated (Dopamine 280 hits, Ioflupane I 123 27, ...). Full re-ascertainment (read-only): all 90 labels unchanged; Ioflupane gains one Phase-3 feature trial (no rank change); **Dopamine would join the cohort** (A-dopamine trials 2020 and 2025). Pagination fixed and tested; re-running 03 rewrites protected files → owner. Evidence: `docs/autonomous_runs/scientific_release_audit/FINDINGS.md` S-01.

### E-057 · MEDIUM · Undefined AUROC silently selected the first weight vector — RESOLVED 2026-10-20
`auroc_cols` returned NaN (RuntimeWarning) on single-class folds; summed NaN made `np.argmax` pick index 0. The only occurrence was a vacuous test (all positives in one fold). Now explicit NaN, `best_index` skips undefined folds and raises if none; test repaired. Persisted weighting outputs re-run byte-identical.

### B-004 · OWNER · Lithium label depends on the registry intervention-type field — OPEN
Three interventional PD trials of lithium aspartate (2023-2024) are typed DIETARY_SUPPLEMENT and dropped by `filter_by_studytype.py`, so Lithium = 0. Under a content-based reading it would be 1 (5D AUROC 0.7754 → 0.7573). Extends TD-023 to a label. Evidence: FINDINGS S-02.

### E-058 · MEDIUM · Live server served a new page with old API code — RESOLVED 2026-10-21
The UI reads `app.js` from disk per request while the server process keeps the Python it started with; after code changes the new page called endpoints the running server lacked (404, found by browser suite drive7 against :8765). The server now fingerprints its own code at start and reports `server_code_changed`; the page shows a restart banner. Test: `tests/test_server_code_change.py`.

### E-059 · LOW · Atomic-write edit made protected stages 05/08 look out of date — RESOLVED 2026-10-21 (deferred change)
The 2026-10-20 atomic-write change to `05_safety_signal.py` and `08_molecular_pathway.py` changed their code fingerprints, so the dashboard asked the owner to re-run two protected, network-dependent stages for a change that does not alter their output. Both files restored to their prior bytes; the change is kept as `docs/autonomous_runs/overnight_audit_20261021/records/deferred_atomic_write_05_08.patch`, to apply with the next owner-approved run of those stages.

### E-060 · LOW · A dependant ran silently on a failed dependency's restored output — RESOLVED 2026-10-21
A single-stage run of 10e or 10h after 10d's latest attempt FAILED used 10d's restored, last-validated output. This is legitimate, but nothing said so (a `--sequence` already BLOCKS dependants). `run_stage.status()` now warns "dependency's latest attempt failed; its last validated output is the one in use", and the Run Center shows stage warnings. Test: `tests/test_agent_failure_modes.py::test_a_failed_dependency_is_flagged_on_its_dependants`.

### E-061 · MEDIUM · Agent badge said four agents "feed the score" — RESOLVED 2026-10-21
`AGENT_KIND` "VPS input" was rendered as "Feeds the score" for 10b, 10c, 10f and 10g, although stage 06 reads no agent output (`tests/test_vps_correctness.py` `test_stage06_reads_only_registered_inputs`). The badge now reads "checks a score input; does not change the score". Test: `tests/test_ui_quality.py::test_no_agent_is_described_as_feeding_the_score`.

### E-062 · LOW · Review count hard-coded as "28" in the 10c role text — RESOLVED 2026-10-21
`AGENT_VPS_ROLE["10c"]` carried a literal "28 links await human review" that would go stale once a reviewer recorded decisions. It is now counted from `data/clinical_review_worklist.csv` per request (unreadable file → "count unavailable"). Test: `tests/test_review_count.py`.

### E-063 · LOW · 10h reported "x/4 checks assessable" for five 10g checks — RESOLVED 2026-10-21
`independence_state` hard-coded the denominator 4 after 10g gained D5, so all-assessable compounds read "4/4" and one-missing read "3/4". It now uses the number of checks present. 10h re-run; only that text changed (run_status and coverage identical, verified in an isolated copy first). Test: `tests/test_completeness_gap_agent.py::test_independence_denominator_counts_all_five_checks`.
