# EviRep evidence agents 10a–10h: contract trace

Audit date 2026-10-20. Repository `/Users/thrisha/Drup_Rep_PF/EviRep`. The audit was read-only. No pipeline stage or network call was run. The only commands run were offline `unittest` modules and read-only reads.
All `file:line` references are relative to the repository root.

---

## 0. Shared machinery (applies to every agent)

### 0.1 Registries (`ui/server.py`)
| Registry | Location | Meaning |
|---|---|---|
| `STAGES` | `ui/server.py:57-394` | The single stage graph: script, inputs, outputs, depends_on, timeout_s, run_args. `scripts/run_stage.py:81-86` loads it via `load_stages()`, so the runner does not keep a second copy. |
| `AGENTS` | `ui/server.py:781-834` | Dashboard metadata for each agent: module, tests, outputs, scope, sources. |
| `AGENT_STAGES` | `ui/server.py:888-889` | Tracked stages behind each agent: `10a:[10a,10a-all]`, `10b:[08,10b]`, `10c:[03,03c,10c,review]`, `10d:[10d]`, `10e:[10e]`, `10f:[05,05h,10f]`, `10g:[04,04p,10g]`, `10h:[10h]`. |
| `AGENT_VPS_ROLE` | `ui/server.py:891-900` | Relationship to VPS. 10b/10c/10f/10g are "score-contributing via upstream stage" (08/03/05/04); the agent layers themselves are diagnostic. |
| `AGENT_OUTPUT` | `ui/server.py:1794-1797` | The envelope file the dashboard reads for each agent. 10a maps to `literature_credibility_all.json` only. |
| `AGENT_KIND` | `ui/server.py:1798-1799` | 10b/10c/10f/10g are labelled "VPS input", 10a/10d/10e "diagnostic", 10h "annotation". |

### 0.2 Launch policy (`ui/live_runs.py`)
- `ALLOWED = ("10a","10a-all","10b","10c","10d","10e","10f","10g","10h","review","07")` (`ui/live_runs.py:39`).
- `CONFIRM`: 04p ("may query PubMed for compounds without a valid cache entry"), 05h ("may query DailyMed…") and diag (`:40-42`). These stages need `confirm=true`; without it the server returns HTTP 428 (`:100-101`).
- `REFUSED`: any stage whose outputs intersect `PROTECTED_ARTEFACTS` (`:31-38`, `:52-55`), plus 04b (`:43`). In practice this refuses 01, 00, 02, 03, 03c, 04, 05, 06, 08 and eval.
- There is no cancellation. The rationale is stated at `ui/live_runs.py:12-13`: killing the runner would skip restore-on-failure. `build_session` also says "cancellation: not offered" (`ui/server.py:2163-2166`).
- Concurrency: the server refuses to launch while any tracked stage is RUNNING (409, `:105-111`). The runner's own lock refuses if a related stage is running (`scripts/run_stage.py:541-548`).

### 0.3 Runner (`scripts/run_stage.py::run`, `:509-645`)
1. Before the run it backs up each existing output (≤512 MB) to `data/_runs/<run_id>/previous/` (`:551-563`). If an output is larger, it fails closed and does not start (`:532-539`).
2. It runs `python <script> <run_args>` with `cwd=root` and waits with `timeout=s["timeout_s"]` (`:565-581`). On `TimeoutExpired` it kills the child and records `code=-9` plus a `TIMEOUT` diagnostic (`:577-585`).
3. Each output is validated (`_validate_file`, `:446-473`). The file must exist and be non-empty. CSVs are parsed and must have ≥1 row. Every JSONL line must parse. JSON files that carry `run_status` must pass `agent_contract.validate_envelope`, and `run_status == "FAILED"` counts as a validation problem.
4. Status rules:
   - exit 0 with no problems gives SUCCESS. It becomes PARTIAL if an output was not rewritten (`NOT_REWRITTEN`, `:597-603`) or if any JSON output says `run_status: PARTIAL` (`:604-609`).
   - exit 1 gives PARTIAL **only for stages 04 and 05** (`PARTIAL_ON_EXIT1`, `:66`, `:610-612`).
   - anything else gives FAILED.
5. On FAILED (non-staged stages, which includes every agent) the new outputs move to `…/failed/` and the backed-up previous outputs are restored atomically (`.restore` then `os.replace`, `:619-630`). An output that did not exist before the run is **not** removed on failure. The manifest records last_attempt, last_success and history (`:637-645`). `--restore STAGE` is available after the runner itself was killed (`:648-692`).
6. `--sequence` (the UI "run all") runs stages in topological order, skips fresh stages (`skip_fresh=True`) and marks downstream stages BLOCKED after an upstream failure (`:731-761`).

### 0.4 Envelope (`scripts/agent_contract.py`)
- Keys: `agent_id, agent, agent_version, schema_version, run_status, generated_utc, inputs{relpath: md5}, coverage, limitations, diagnostics[]` (`:40-41`).
- `RUN_STATUSES = SUCCESS | PARTIAL | NO_EVIDENCE | FAILED` (`:38`). STALE is never written; it is derived at read time from input md5s (`stale_inputs`, `:125-135`).
- `run_status(n_units, n_failed, n_with_evidence)`: zero units gives FAILED, all units failed gives FAILED, some failed gives PARTIAL, no evidence gives NO_EVIDENCE, otherwise SUCCESS (`:73-83`).
- `validate_envelope` (`:103-122`) requires all keys, a valid status, `agent_id` matching `10[a-h]`, relative input paths only, valid diagnostic levels, and no secret-like diagnostic text. PARTIAL must carry a warn or error diagnostic and FAILED must carry an error diagnostic. `diag()` redacts secret-like text and `/Users/<name>` (`:65-70`).
- `input_hashes` **omits absent inputs** (`:56-58`). If an input appears after a run, the envelope's staleness check cannot detect it.

### 0.5 Current state of outputs (read-only check)
Every agent output exists, validates against the envelope, reports `run_status=SUCCESS` and has 0 stale inputs. Every manifest last_attempt is SUCCESS with exit 0: 10a/10b/10c/10d/10e/10g/10h/review on 2026-10-20, 10a-all/04p/10f on 2026-10-19 and 05h on 2026-10-20. Stage 08 is `ADOPTED`, meaning it predates run tracking and has never been re-run under the runner. The 10b output reports `agent_version = "unrecorded"`, because the stage-08 JSONL records carry no `provenance.agent_version` (`scripts/molecular_run_record.py:66-67`).

---

## 1. Agent 10a: Literature Credibility

**Module:** `scripts/literature_credibility_agent.py` (583 lines). `AGENT_VERSION="10a-0.1 (2026-10-13)"` (`:44`).

1. **Purpose.** Rates study *design* credibility only. Each paper gets a tier A–D or X, derived from PubMed PublicationType (`DESIGN_PRIORITY`, `:51-73`; `TIER`, `:75-81`). Preclinical work (Animals without Humans in MeSH) is capped at C. Sample size is taken only from explicit "n = N" spans. Direction is copied only from curated claims, never inferred from text. Efficacy is never assessed, and `validate_output` raises if it appears (`:303`). There are three modes:
   - `--all`: every compound, from stage-04p records (`all_compounds_report`, `:468-496`).
   - `--curated`: the curated case-study PMIDs (`curated_reports`, `:345-381`).
   - `--graph`: one compound from a 04b graph, with an optional live efetch (`:533-580`).
2. **Trigger.**
   - Stage `10a` runs `--curated` (`ui/server.py:345-353`) with depends_on `[]`.
   - Stage `10a-all` runs `--all` (`ui/server.py:355-365`) with depends_on `[04p]`.
   - Both are UI **ALLOWED** ("offline; outputs are not protected artefacts").
   - `--graph` mode is CLI-only and has no stage.
3. **Inputs and validation.**
   - `--all` reads `data/literature_provenance.csv`, `data/literature_papers.jsonl` and `data/cache/pubmed_lit/<slug>.json`.
     - A missing CSV or JSONL raises an uncaught `FileNotFoundError` (`:404-412`).
     - A malformed JSONL line raises an uncaught `JSONDecodeError`.
     - An unreadable per-compound cache is caught. The compound becomes `RETRIEVAL_FAILED` with a `CACHE_UNREADABLE` warning (`:427-435`).
     - An empty CSV produces an `INPUT_EMPTY` error and FAILED (`:475-476`, `run_status(0,…)`).
     - Duplicates (non-primary records) are listed under `duplicates_removed` and rated once (`:438-441`).
   - `--curated` reads `data/cache/pubmed_efetch_case_claims.xml` and `data/conflict_claims_curated.json`. A missing file raises an exception. Requested PMIDs absent from the XML give `PMID_NOT_RETURNED` and PARTIAL. If none were returned the result is FAILED with `NO_RECORD_RETURNED` (`:319-341`).
   - Malformed XML raises `ET.ParseError`.
4. **External sources.**
   - `--all` and `--curated` make **no network calls**. They read data written by stage **04p**: NCBI E-utilities `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi` + `efetch.fcgi`, with optional `NCBI_API_KEY` (see §9).
   - `--graph` without `--xml` makes one live `requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", timeout=60)` (`:548-551`). It has no API key, no retry, no rate limiting, and calls `raise_for_status()`. It is capped at 200 PMIDs, refusing more (`:541-542`). It caches only when `--save-xml` is given.
5. **Outputs and envelope.**
   - `--all` writes `data/literature_credibility_all.json` with schema_version "1.1". Coverage: `compounds, assessed, retrieval_failed, no_results, papers_rated, duplicates_removed`.
   - `--curated` writes `data/literature_credibility_{donepezil,domperidone,melatonin,propranolol}.json` with schema "1.0".
   - `literature_credibility_droxidopa.json` comes from `--graph` mode and no stage produces it. 10h and the UI still read it.
   - Run statuses emitted: SUCCESS, PARTIAL, NO_EVIDENCE, FAILED. Provenance: `generated_utc`, md5 `inputs` (the 04p cache files are included per compound), `agent_version`.
6. **Persistence.**
   - `--all` writes atomically (`.tmp` + `os.replace`, `:512-516`).
   - `--curated` writes **non-atomically** (`open(path,"w")`, `:528-529`). It skips a file that holds a graph assessment (`:525-527`).
   - **Exit code:** `--all` returns 1 when the status is PARTIAL or FAILED (`:520`). Stage 10a-all is not in `PARTIAL_ON_EXIT1`, so the runner records a PARTIAL run as **FAILED** and **restores the previous output**. A legitimately PARTIAL 10a-all result can therefore never be published through the runner.
   - `--curated` returns None, which exits 0 (`:531`, `:582-583`). A FAILED envelope is still caught by `_validate_file`.
7. **Downstream consumers.**
   - Stage 06 reads nothing from 10a.
   - 10h reads `literature_credibility_all.json` and the `literature_credibility_*.json` glob (`scripts/completeness_gap_agent.py:55`, `:59`, `:384`, `:449-455`).
   - UI endpoints: `/api/agents` (`_agent_run` uses `output_glob`), `/api/agent?id=10a`, `/api/live`, and `/api/compound` (`ui/server.py:1636-1645`).
8. **Timeout.** `timeout_s=900` for both 10a and 10a-all (`ui/server.py:351`, `:362`). There is no in-agent cancellation.
9. **Tests.** `tests/test_literature_credibility_agent.py`: **28 tests, 28 pass**.
   - Covered: empty input, malformed XML, malformed and duplicate records, missing fields, unknown design (not scored as zero), `--all` determinism, unreadable 04p cache leading to RETRIEVAL_FAILED, PMIDs not returned leading to PARTIAL, all PMIDs missing leading to FAILED, graph-mode restriction, and the offline CLI.
   - Mocked: `socket.socket.connect` is patched to prove no network (`:219`). One test drives 04p `main` with a fake session (`:292-305`).
   - Indirect: `tests/test_eight_agents_integration.py` (reproduces the persisted output).
10. **Gaps (untested).** Missing `literature_provenance.csv` or `literature_papers.jsonl` (raises). Malformed JSONL line. Empty provenance CSV (the `INPUT_EMPTY` path). How the runner handles `--all` exiting 1 on PARTIAL. Non-atomic `--curated` writes. Live `--graph` HTTP failure, timeout or 429 (no retry, no test). Behaviour with more than 200 PMIDs.
11. **Known limitations (envelope).** Tiers rate design only. The stage-04 sample is PubMed's 30 most recent hits (TD-021). 04p queried PubMed after stage 04 ran. Direction is not assessed in `--all` mode (`:490-494`).

---

## 2. Agent 10b: Molecular Plausibility

**Modules:**
- `scripts/molecular_agent.py`: logic plus the Open Targets client.
- `scripts/08_molecular_pathway.py`: stage 08 runner.
- `scripts/molecular_run_record.py`: the 10b envelope.

1. **Purpose.**
   - Stage 08 traces drug → ChEMBL target → gene → Reactome pathway → PD module. The score is `0.6×direct + 0.4×pathway`, with leaky clinical and literature datatypes excluded. It produces the **VPS molecular dimension**.
   - Stage 10b does **not** re-run retrieval. It re-validates every JSONL record (`molecular_agent.validate_output`), checks CSV/JSONL score agreement, flags records written while the API was unavailable, and writes the envelope (`scripts/molecular_run_record.py:1-9`, `:29-75`).
2. **Trigger.**
   - Stage `08` (`ui/server.py:160-173`) depends on 03c. It is UI **REFUSED** because it rewrites protected `molecular_pathway.csv` and `…evidence.jsonl`.
   - Stage `10b` (`ui/server.py:299-306`) depends on [08, 06] and is UI **ALLOWED**.
3. **Inputs and validation.**
   - Stage 10b reads `data/molecular_pathway.csv`, `data/molecular_pathway_evidence.jsonl` and `data/vps_scores_v2.csv` (POOL; it falls back to the CSV if POOL is absent, `:44`).
     - Each invalid JSONL line gives an `INVALID_RECORD` warning and is counted as failed (`:33-41`).
     - A missing JSONL or CSV raises an uncaught exception.
     - Pool compounds without a row or evidence record produce warnings (`:47-50`).
     - A CSV/JSONL score mismatch produces an error and FAILED (`:51-65`).
     - API-failure records give `RETRIEVAL_FAILED_RECORD` and count as failed (`:55-58`).
   - Stage 08: a missing input or a missing `compound_name` column raises `SystemExit` (`08_molecular_pathway.py:136-149`). If any record remains an API failure, it exits 1 with an INCOMPLETE message (`:388-394`).
4. **External sources.**
   - Stage 10b makes none.
   - Stage 08 uses `OpenTargetsClient` (`molecular_agent.py:250-385`):
     - endpoint `https://api.platform.opentargets.org/api/v4/graphql` (`:90`), via `requests.Session().post`, with no auth and no env var;
     - throttle `min_request_interval_s=0.25`, `max_retries=4`, exponential backoff `1.0·2^(n-1)` plus jitter, `timeout_s=60` (`:211-216`);
     - retries on 429 and 5xx, honouring `Retry-After` capped at 60 s (`:352-360`); other 4xx and GraphQL errors are not retried (`:362-376`); invalid JSON is retried (`:366-370`);
     - batching of 25 IDs per request (`:613-624`); the PD module is limited to `pd_module_size=300` associated targets (`:200`, `:684-688`);
     - cache in `data/cache/molecular/<sha256(query+vars)>.json`, written atomically. It has **no TTL**. A corrupt entry is refetched (`:275-302`).
     - `--offline` (cache-only) and `--no-cache` options exist (`08_molecular_pathway.py:194-213`, `:157-162`).
5. **Outputs and envelope.**
   - Stage 10b writes `data/molecular_agent_run.json` with schema "1.0". `agent_version` is the joined record versions, currently "unrecorded". Coverage: `pool_compounds, evidence_records_valid, invalid_records, resolved, with_targets, without_targets, with_unretrievable_evidence_items`. Statuses: SUCCESS, PARTIAL, NO_EVIDENCE, FAILED.
   - Stage 08 writes `data/molecular_pathway.csv`, `…_evidence.jsonl` and the checkpoint `data/_molecular_checkpoint.jsonl`. These are not envelopes.
6. **Persistence.**
   - Stage 10b writes **non-atomically** (`open(...,"w")`, `molecular_run_record.py:84-85`). It exits 1 only on FAILED (`:87`).
   - Stage 08 writes the JSONL and CSV directly (`08_molecular_pathway.py:357-362`), non-atomically. Its checkpoint is append-only.
   - The runner restores the previous output on FAILED.
7. **Downstream consumers.**
   - **Stage 06 reads `data/molecular_pathway.csv`** (`scripts/06_vps_fusion.py:58`). This is VPS dimension 5. Stage 06 does not read `molecular_agent_run.json`.
   - 10h reads `molecular_pathway.csv` (`completeness_gap_agent.py:49`) but **not** `molecular_agent_run.json`, and 10b is absent from 10h's staleness map (`:52-54`).
   - 10c, 10d and 10g read the evidence JSONL.
   - UI: `/api/agents`, `/api/agent?id=10b`, `/api/live`.
8. **Timeout.** Stage 10b has `timeout_s=900`. Stage 08 has **no `timeout_s`**, so the runner waits indefinitely (`child.wait(timeout=None)`). It is REFUSED in the UI.
9. **Tests.**
   - `tests/test_molecular_agent.py`: **69 tests, 69 pass** (stage-08 logic). Mocked sessions cover connection error after retries, GraphQL errors not retried, invalid JSON retried then failing, 429 recovery, the cache preventing repeat calls, cache-key order independence, batching, determinism, empty or None inputs, unresolved drugs, an empty module, and validation of malformed records.
   - `tests/test_molecular_vps_audit.py`: **16 tests, 16 pass**. One test exercises `molecular_run_record.build` (retrieval-failure record and blank-score mismatch). Others cover corrupt cache refetch, resume after a checkpointed failure, stage exit ≠0 on remaining failures, and fresh rescoring.
   - Integration: 7 tests.
10. **Gaps (untested).** Invalid JSONL line in `molecular_run_record` (the `INVALID_RECORD` path). Missing JSONL or CSV (raises). Pool compound without a row. Non-atomic write of the 10b output. Stage 08 hang (no timeout). Stale-cache semantics: the cache never expires, which is documented but untested.
11. **Known limitations (envelope).** The Open Targets snapshot is not cutoff-bounded (B-001). Clinical and literature datatypes are excluded. The record re-validates and does not re-run (`molecular_run_record.py:73-75`).

---

## 3. Agent 10c: Clinical Evidence

**Module:** `scripts/clinical_evidence_agent.py` (304 lines). `AGENT_VERSION="10c-1.0"`, schema "1.0" (`:43-44`).

1. **Purpose.** A diagnostic layer over stage 03. Per pre-cutoff trial link it records registry status class, posted results (primary analyses copied verbatim and flagged POST_CUTOFF if posted after 2021-01-01) and the drug's role (`trial_role.classify_trial_role`, with the D-020 hand adjudication taking precedence). Per compound it adds matching-audit outcome counts. It never scores; `validate_output` rejects `efficacy` and `score` (`:269-271`).
2. **Trigger.**
   - Stage `10c` (`ui/server.py:308-319`) depends on [03c, 08, 06] and has no run_args, so it runs offline from cache. It is UI **ALLOWED**.
   - The related stage `review` (`scripts/clinical_role_review.py`, `:367-378`) depends on [10c] and is ALLOWED.
   - Upstream 03 and 03c are REFUSED.
3. **Inputs and validation.**
   - Required: `data/clinical_maturity_precutoff_clean.csv`; it raises if missing (`:159`).
   - Optional: `clinicaltrials_match_audit.csv`, `feature_trial_roles_td038.csv`, `vps_scores_v2.csv`, `data/cache/ctgov_precutoff_trials.json` and `molecular_pathway_evidence.jsonl`.
   - No cache gives a `NO_REGISTRY_CACHE` error and FAILED (`:177-178`, `:240-241`).
   - Failed batches give `BATCH_FAILED` warnings and the affected trials become `RETRIEVAL_FAILED` (`:179-181`, `:186-188`).
   - Links never requested by the cache give `CACHE_STALE` and `NOT_RETRIEVED` (`:192-196`).
   - Requested trials that were not returned give `NOT_IN_REGISTRY` and PARTIAL (`:197-199`, `:242-243`).
   - A malformed cache JSON or JSONL raises an uncaught exception.
4. **External sources.**
   - The default (stage) mode makes **none**. It reads a cache produced earlier with `--fetch`.
   - With `--fetch` (CLI only; neither the runner nor the UI passes it) it calls `GET https://clinicaltrials.gov/api/v2/studies` with `filter.ids` (batches of 20), `fields=protocolSection,hasResults,resultsSection.outcomeMeasuresModule`, `pageSize=20` and `timeout=60` (`:52-80`).
     - There is no auth, **no retry, no backoff and no inter-request pause**.
     - There is no pagination token handling; one page per batch is assumed.
     - Each batch outcome is recorded.
     - If every batch fails and a cache exists, the old cache is kept and the command exits 1 (`:284-287`). Otherwise the cache is replaced atomically (`:288-290`).
     - The cache file is a **protected artefact** (`ui/live_runs.py:38`).
   - Discovery data comes from upstream **stage 03** (`https://clinicaltrials.gov/api/v2/studies`, see §9).
5. **Outputs and envelope.** `data/clinical_evidence.json`. Coverage: `trials, links, compounds, results{RESULTS_POSTED,…}, registry_retrieved_utc`. Inputs: md5 of 6 files. Statuses: SUCCESS, PARTIAL, NO_EVIDENCE, FAILED.
6. **Persistence.** Atomic `.tmp` + `os.replace` (`:295-298`). Exits 1 only on FAILED. The runner restores the previous output on FAILED. A `--fetch` run under the runner would rewrite the cache, which is not a declared output, so it is not backed up.
7. **Downstream consumers.**
   - Stage 06 reads `clinical_maturity_precutoff_clean.csv`, which is stage 03c's output and not 10c's. It does not read 10c.
   - **10g** reads `clinical_evidence.json` for trial roles (`evidence_independence_agent.py:117-122`) and does not check its run_status.
   - **10h** reads it for trial outcomes and roles (`completeness_gap_agent.py:399`, `:442-443`).
   - UI: `/api/evidence` (`ui/server.py:1343-1346`), `/api/compound`, `/api/agents`, `/api/agent`, `/api/live`.
8. **Timeout.** `timeout_s=900`.
9. **Tests.** `tests/test_clinical_evidence_agent.py`: **19 executed (16 unique; TestRun re-runs 3 inherited tests), 19 pass**.
   - Covered: no cache gives FAILED, all batches failed gives a FAILED output, a failed fetch keeps the previous cache, missing/failed/retrieved states stay distinct, stale cache (link never requested), results without a posting date, post-cutoff flagging, the alias rules, and the persisted output.
   - Mocked: `fetch_registry`/`main` take an injected `get` (`:87-95` simulates a `TimeoutError` and HTTP 503).
10. **Gaps (untested).** Partial-batch failure overwriting a good cache with a worse one (only the all-failed case is tested). HTTP 429 handling (none exists). Malformed cache JSON. Missing links CSV. Malformed molecular JSONL in `chembl_names` (raises). Pagination beyond `pageSize`.
11. **Known limitations (envelope).** Pre-cutoff trials only. Roles are automated except the 35 D-020 links. Analyses are verbatim. ClinicalTrials.gov only; there is no EU-CTR, ISRCTN or ICTRP (`:249-255`).

---

## 4. Agent 10d: Conflict & Context

**Module:** `scripts/conflict_context_agent.py` (473 lines). `AGENT_VERSION="10d-0.1"`, schema "1.0".

1. **Purpose.** Pairwise classification of persisted, source-linked claims into DIRECT_CONTRADICTION, STATISTICAL_DISAGREEMENT, CONTEXT_DIFFERENCE, CROSS_DOMAIN_TENSION, UNCERTAIN_COMPARABILITY or NON_COMPARABLE (`:57-58`). Claims come from four sources: curated case-study claims, fixed regex rules over cached openFDA label sections (`LABEL_RULES`, `:119+`), stage-08 molecular claims and trial context. It never scores (`:452-453`).
2. **Trigger.** Stage `10d` (`ui/server.py:262-273`), depends on [05, 08, 06], UI **ALLOWED**.
3. **Inputs and validation.**
   - Inputs: `data/conflict_claims_curated.json` (protected), `data/cache/openfda_labels/*.json`, `molecular_pathway_evidence.jsonl`, `clinical_maturity_precutoff_clean.csv` and `vps_scores_v2.csv`. Each is optional.
   - A missing input gives an `INPUT_MISSING` warning and PARTIAL (`:405-407`, `:414-416`).
   - A missing curated file is recorded as a rejection with a relative path (`:101-103`).
   - Duplicate `claim_id`s are rejected (`:108-110`). Invalid claims are rejected with a reason.
   - A malformed label JSON raises an uncaught exception (`:367-369`).
   - A malformed molecular JSONL line is **skipped silently**, with no diagnostic (`:378-381`).
4. **External sources.** None. Upstream data: stage **05** cached openFDA labels (`https://api.fda.gov/drug/label.json`) and stage **08** Open Targets.
5. **Outputs and envelope.** `data/conflict_context.json`. Coverage: `compounds, assessed, insufficient`. Also `status_counts`, `synthesis_inputs` and `records`. Statuses: SUCCESS, PARTIAL, NO_EVIDENCE, FAILED (via `run_status(len(records),0,n_ev)`; FAILED only when there are no records at all).
6. **Persistence.** Atomic (`:465-468`). `main` returns None, so the process always exits 0 unless it raises. A FAILED envelope is still caught by the runner's validation.
7. **Downstream consumers.** Not stage 06; `tests/test_conflict_context_agent.py` asserts there is no coupling. 10h reads it (`completeness_gap_agent.py:381`, `:430-433`). UI: `/api/conflicts`, `/api/overview` (`ui/server.py:974-1013`), `/api/compound`, `/api/agents`, `/api/agent`.
8. **Timeout.** `timeout_s=900`.
9. **Tests.** `tests/test_conflict_context_agent.py`: **25 tests, 25 pass**.
   - Covered: classification rules, duplicate claim IDs, a missing curated file (relative path), invalid claims rejected, temporal parsing, a label without PD mentions, a molecular record without targets, a stopped trial treated as UNCLEAR, a deterministic temp-root run that reports missing inputs, rejection of scores, and the persisted output against `docs/CASE_STUDIES.md`.
   - No network mocks are needed.
10. **Gaps (untested).** Malformed label cache JSON (crash). Silently skipped malformed molecular lines (no diagnostic at all). Empty pool combined with no curated claims (the FAILED path). Missing pool CSV. Exit code on FAILED (always 0).
11. **Known limitations (envelope).** Curated claims exist only for case-study compounds. INSUFFICIENT means fewer than 2 directional sources, not agreement. Stage-04 literature is not read (TD-021) (`:420-424`).

---

## 5. Agent 10e: Reproducibility

**Module:** `scripts/reproducibility_agent.py` (399 lines). `AGENT_VERSION="10e-0.1"`, schema "1.0".

1. **Purpose.** Finding-level replication. A finding is compound × outcome domain × direction. The agent counts independent primary-study clusters. Shared author, trial ID or documented shared data makes studies DEPENDENT; reviews and meta-analyses are never replicates. Independence is categorical: DEPENDENT, PLAUSIBLY_INDEPENDENT or UNDETERMINED (`:1-35`).
2. **Trigger.** Stage `10e` (`ui/server.py:275-286`), depends on [10d], UI **ALLOWED**. The dependency on 10d is an ordering dependency only: 10e reads 10d's *input* (curated claims), not 10d's output.
3. **Inputs and validation.**
   - Inputs: `data/cache/pubmed_efetch_case_claims.xml`, `pubmed_efetch_droxidopa.xml`, `conflict_claims_curated.json`, `data/literature_graph_*.json` (globbed; **not declared in the registry inputs**) and the two clean trial CSVs.
   - Each missing input gives an `INPUT_MISSING` warning (`:300-301`).
   - Findings without source records give `MISSING_SOURCE_RECORDS` and `INSUFFICIENT_METADATA`, leading to PARTIAL (`:305-312`).
   - With no findings and no graph the result is FAILED with `NOTHING_TO_ASSESS` (`:322-324`).
   - Malformed XML or graph JSON raises.
4. **External sources.** None. Upstream data: PubMed efetch XML saved by earlier `--graph` / case-claim retrievals (`eutils efetch.fcgi`). These are static files with no stage owner.
5. **Outputs and envelope.** `data/reproducibility.json`. Coverage: `findings, paper_structures, publication_records`. `inputs` is `{path: md5}`; `input_files` also records the XML mtime as `retrieved_utc`. The top-level `limitations` key overrides the envelope's empty list (`:358-366`).
6. **Persistence.** Atomic (`:390-392`). `main` returns None, so it always exits 0. The runner catches FAILED.
7. **Downstream consumers.**
   - Not stage 06 (asserted by a test).
   - **`scripts/vps_evaluation_report.py:178`** reads it (stage `eval` depends on 10e).
   - 10h reads it (`completeness_gap_agent.py:382`).
   - UI: `/api/case_status` (`ui/server.py:1044-1049`), `/api/compound`, `/api/agents`, `/api/agent`.
8. **Timeout.** `timeout_s=900`.
9. **Tests.** `tests/test_reproducibility_agent.py`: **21 tests, 21 pass**.
   - Covered: malformed XML raises, missing metadata gives UNDETERMINED, missing records are flagged on the finding and the run, duplicate claims on one record, meta-analysis is not a replicate, same group, two papers of one trial, citation is not a dependency, an offline deterministic run, rejection of scores, and the persisted output (inputs checksummed).
   - No mocks are used.
10. **Gaps (untested).** All inputs absent (the FAILED `NOTHING_TO_ASSESS` path). Malformed curated JSON. Malformed graph JSON. Exit code on FAILED (always 0). Staleness of the undeclared `literature_graph_*.json`: the runner cannot see it, although the envelope can.
11. **Known limitations (output).** Coverage is limited to case-study compounds. Author matching uses last name plus initial (homonym risk). No affiliation or funding data. NCT IDs come only from DataBank or the abstract. Independence is not quality (`:358-366`).

---

## 6. Agent 10f: Safety Evidence

**Module:** `scripts/safety_evidence_agent.py` (311 lines). `AGENT_VERSION="10f-1.0"`, schema "1.0".

1. **Purpose.** Per compound it keeps two sources separate:
   - the FDA label: provenance, boxed warning and the label-at-cutoff view from 05h;
   - FAERS report counts: total, serious, deaths, received by 2020-12-31 and top reactions.

   Each source has a state of RETRIEVED, NO_RECORD, FAILED or NOT_RETRIEVED (`:50`). It produces no score (`:263-264`).
2. **Trigger.** Stage `10f` (`ui/server.py:322-332`), depends on [05, 05h, 06], UI **ALLOWED**. Upstream 05 is REFUSED; 05h is CONFIRM.
3. **Inputs and validation.**
   - **Required:** `data/vps_scores_v2.csv` (raises if missing, `:179`).
   - Optional: `safety_signal.csv` (missing gives `INPUT_MISSING` and PARTIAL), `_safety_failures.jsonl`, `safety_label_history.csv` (missing gives an info diagnostic and at_cutoff `NOT_RETRIEVED`), the `openfda_faers/` cache and the `openfda_labels/` cache.
   - A malformed FAERS cache JSON, label JSON or failures JSONL line raises an uncaught exception (`:198-200`, `:205-207`, `label_evidence`).
   - Duplicate pool rows are de-duplicated (`dict.fromkeys`, `:179`).
   - HTTP 200 without a JSON results body is a failure. A 404 `NOT_FOUND` is NO_RECORD (`:90-105`).
4. **External sources.**
   - The default (stage) mode makes **none**.
   - With `--fetch [--limit N]` (CLI only) it calls `GET https://api.fda.gov/drug/event.json` (`:48`) four times per compound (`faers_queries`, `:57-67`) through `requests.get(timeout=30)` with `time.sleep(0.3)` between queries (`:70-84`).
     - There is **no API key** (openFDA's optional `api_key` is not used), **no retry and no backoff**. A 429 is recorded as FAILED, and `needs_fetch` retries failed or partial entries on the next `--fetch` (`:268-280`).
     - It fetches only compounds that are uncached or failed.
     - Cache: `data/cache/openfda_faers/<safe_name>.json`, written **non-atomically** (`:297-298`), with no TTL.
   - Label data comes from stage **05** (`https://api.fda.gov/drug/label.json`, cache `data/cache/openfda_labels/`). Label-at-cutoff data comes from stage **05h** (DailyMed).
5. **Outputs and envelope.** `data/safety_evidence.json`. Coverage: `compounds, label{states}, faers{states}, label_at_cutoff{SCORED,UNKNOWN,NO_RECORD,FAILED,NOT_RETRIEVED}`. Inputs: md5 of the pool, the label CSV, failures, history and each FAERS and raw-label cache file. Statuses: SUCCESS, PARTIAL, NO_EVIDENCE, FAILED. Any warning or NOT_RETRIEVED FAERS entry forces PARTIAL (`:229-235`).
6. **Persistence.** Output is written atomically (`:301-304`); the FAERS cache is not. Exits 1 only on FAILED. The runner restores the previous output on FAILED.
7. **Downstream consumers.** Stage 06 reads `safety_signal.csv` (stage 05), not 10f. 10h reads `safety_evidence.json` for `with_label_at_cutoff` and `faers_state` (`completeness_gap_agent.py:400`, `:422-425`). UI: `/api/compound` (`ui/server.py:1650-1667`), `/api/agents`, `/api/agent`, `/api/live`.
8. **Timeout.** `timeout_s=900`.
9. **Tests.** `tests/test_safety_evidence_agent.py`: **21 executed (20 unique), 21 pass**.
   - Covered: envelope rules (unexplained PARTIAL, secrets, absolute paths), staleness, FAERS normalisation, HTTP 500 and 429 and exceptions treated as failures (not zero), NOT_FOUND as NO_RECORD, a measured zero for deaths, partial query failure, all failed giving a FAILED envelope without a crash, duplicate pool rows, HTTP 200 without JSON, `--fetch` retrying only failed entries, label-at-cutoff states and the persisted output.
   - Mocked: an injected fake `get` and synthetic cache files.
10. **Gaps (untested).** Malformed FAERS or label cache JSON (crash). Missing pool CSV. Non-atomic FAERS cache write (a killed fetch leaves a truncated cache, which then crashes `run`). Real 429 storms (no backoff exists). Request timeout behaviour in `fetch_faers`.
11. **Known limitations (envelope).** FAERS has no denominator, carries reporting bias and implies no causality. Name matching misses brand-only reports. Labels are current versions. FAERS totals are all-time, while `reports_received_by_2020` is bounded (`:242-246`).

---

## 7. Agent 10g: Evidence Independence

**Module:** `scripts/evidence_independence_agent.py` (298 lines). `AGENT_VERSION="10g-1.1"`, schema "1.0".

1. **Purpose.** Five cross-source dependence checks per candidate:
   - D1: a shared trial across compounds.
   - D2: the same study in two dimensions (an NCT ID in a paper matches a clinical-feature trial).
   - D3: duplicated or pooled curated claims (union-find).
   - D4: molecular datatype reuse.
   - D5: a duplicate publication in the stage-04 sample, from 04p.

   Each check is DEPENDENCE_FOUND, NONE_FOUND or NOT_ASSESSABLE (`:1-33`). It produces no score.
2. **Trigger.** Stage `10g` (`ui/server.py:334-343`), depends on [10c, 04, 08, 04p, 06], UI **ALLOWED**.
3. **Inputs and validation.**
   - **Required:** `vps_scores_v2.csv` and `clinical_maturity_precutoff_clean.csv` (both raise if missing, `:110-111`).
   - Optional: `literature_independence.csv`, `conflict_claims_curated.json`, `clinical_evidence.json`, `molecular_pathway_evidence.jsonl`, the two efetch XMLs, `literature_papers.jsonl` and `data/cache/pubmed_lit/<slug>.json`.
   - Missing optional inputs give `INPUT_MISSING` or `XML_MISSING` warnings and PARTIAL.
   - An unreadable 04p cache gives `CACHE_UNREADABLE` (`:150-153`).
   - A malformed molecular line gives `MALFORMED_LINE` (`:164-166`).
   - A header-only links CSV gives an `INPUT_EMPTY` error and FAILED (`:177-178`, `:246-247`).
   - The run_status of `clinical_evidence.json` is **not checked** before its roles are consumed.
   - A malformed `literature_papers.jsonl` or `clinical_evidence.json` raises.
4. **External sources.** None. Upstream data: stage **04p** (PubMed E-utilities), stage **04** (PubMed + Semantic Scholar `https://api.semanticscholar.org/graph/v1/paper`), stage **08** (Open Targets) and **10c**.
5. **Outputs and envelope.** `data/evidence_independence.json`. Coverage: `compounds, checks{D1..D5: state counts}, trials_shared_across_compounds`. Statuses: SUCCESS, PARTIAL, FAILED (NO_EVIDENCE cannot occur, because `n_with_evidence = n_units`).
6. **Persistence.** Atomic (`:287-290`). Exits 1 on FAILED.
7. **Downstream consumers.** Stage 06 reads `literature_independence.csv` (stage 04), not 10g. 10h reads it (`completeness_gap_agent.py:400`, `:426`). UI: `/api/compound`, `/api/agents`, `/api/agent`, `/api/live`.
8. **Timeout.** `timeout_s=900`.
9. **Tests.** `tests/test_evidence_independence_agent.py`: **11 executed (7 unique; the TestMissingInputsAreNotFindings class re-runs the fixture tests), 11 pass**.
   - Covered: the D1–D5 checks on a fixture, rejection of scores, 04p making D2 and D5 assessable, an unreadable provenance cache, absent inputs, header-only links giving FAILED, and the persisted output.
   - No mocks are used.
   - Integration: `test_10g_consumes_stage04p`.
10. **Gaps (untested).** Missing pool or links CSV (raise). Malformed `literature_papers.jsonl` or `clinical_evidence.json`. A FAILED or stale 10c output being consumed. The `MALFORMED_LINE` path. Duplicate pool rows (not de-duplicated, unlike 10f).
11. **Known limitations (envelope).** D2 and D5 use the 04p re-query. NCT links give false negatives. Patient-level overlap cannot be detected. Nothing is de-duplicated in VPS (`:254-263`).

---

## 8. Agent 10h: Completeness & Gap

**Module:** `scripts/completeness_gap_agent.py` (564 lines). `AGENT_VERSION="10h-1.0"`, schema "1.0".

1. **Purpose.** For each candidate and each of the 12 domains (5 VPS dimensions plus 7 evidence or agent domains), the agent assigns a state:
   - MEASURED, MEASURED_ZERO or PARTIAL;
   - ABSENT_AT_SOURCE, NOT_COMPUTED, NOT_RETRIEVED or RETRIEVAL_FAILED;
   - INSUFFICIENT or ASSESSED.

   It also gives gaps with "needed to close", open questions, the staleness of every agent output and a self-check against stage 06 `dimensions_missing` (`:1-29`, `:62-72`, `:521-523`). It produces no score.
2. **Trigger.** Stage `10h` (`ui/server.py:381-393`), depends on [06, 10c, 10d, 10e, 10f, 10g, 10a-all, 10a] (**not 10b**), UI **ALLOWED**. It is described as "Run last".
3. **Inputs and validation.**
   - **Required:** `vps_scores_v2.csv` (`FileNotFoundError`, `:375-376`).
   - All others are optional: `F` (`:46-53`) plus the `literature_credibility_*.json` glob.
   - Absent agent outputs give `AGENT_OUTPUT_ABSENT` warnings. Stale agent outputs (md5 mismatch per `stale_inputs`) give `STALE_AGENT_OUTPUT` warnings and a `stale` note on each domain. Missing or empty stage CSVs give `INPUT_MISSING` or `INPUT_EMPTY`. Any of these makes the run PARTIAL (`:479-498`).
   - Malformed upstream JSON or JSONL raises.
   - **Upstream `run_status` (FAILED or PARTIAL) is recorded in `agent_outputs` but does not change domain states.**
   - `validate_output` **raises** if 10h disagrees with stage-06 `dimensions_missing` (`:539-541`). That is a hard failure, and the runner then restores the previous output.
4. **External sources.** None. Upstream: everything listed in §9.
5. **Outputs and envelope.** `data/completeness_gaps.json`. Coverage: `compounds, domains, gaps`. Also `agent_outputs`, `state_counts_by_domain`, `missingness_vs_label`, `stage06_agreement` and `synthesis_inputs`. `inputs` is the md5 of every existing input. Statuses: SUCCESS, PARTIAL, FAILED (only with zero compounds).
6. **Persistence.** Atomic (`:552-555`). `main` always returns 0 (`:562`), so a failure surfaces only as an exception or as validation.
7. **Downstream consumers.** No agent and not stage 06. It is meant to feed "Stage 11" via `synthesis_inputs`, but no Stage 11 script exists. UI: `/api/gaps` (`ui/server.py:1225-1253`), `/api/compound` (`:1671-1677`), `/api/agents`, `/api/agent`, `/api/live`.
8. **Timeout.** `timeout_s=900`.
9. **Tests.** `tests/test_completeness_gap_agent.py`: **20 tests, 20 pass**.
   - Covered: state mapping for each domain (zero versus absent versus failed versus imputed), an empty stage CSV plus missing agent output giving warnings, recorded failures giving RETRIEVAL_FAILED, credibility states, the label-at-cutoff annotation, staleness reporting, agreement with stage 06 on persisted artefacts, and rejection of scores and unknown states.
   - No mocks are used; temp-root copies and read-only persisted data are used.
   - Integration: `test_10h_sees_all_agent_outputs_present_and_fresh`, `test_missing_failed_and_negative_stay_distinct_in_10h`.
10. **Gaps (untested).** Malformed upstream JSON. An upstream agent output with `run_status=FAILED` being consumed as data. 10b staleness (never checked). The hard-fail on stage-06 disagreement under the runner (restore path). Missing `vps_scores_v2.csv`.
11. **Known limitations (output).** Evaluable pool only. Stage 02 does not persist skip reasons. Staleness checks cover only 10a and 10c–10g. States describe availability, not quality. Remedies have not been run (`:524-529`).

---

## 9. Network clients the agents depend on

None of the eight agent stages (10a, 10a-all, 10b–10h) makes a network request in the mode the runner invokes. Network access sits in upstream stages or in CLI-only flags.

| Stage / flag | Script | Endpoint(s) | HTTP client | Auth / env var names | Retry / backoff / rate limit | Timeout | Pagination / truncation | Cache (dir, semantics) | Cache present (files) |
|---|---|---|---|---|---|---|---|---|---|
| 03 (REFUSED) | `03_clinicaltrials_groundtruth.py` | `https://clinicaltrials.gov/api/v2/studies` (`:54`) + Open Targets synonyms | `requests.get` | none | `MAX_RETRIES=4`, exponential backoff, Retry-After on 429/5xx (`:60-95`); 0.34 s pause (`:204`) | 25 s | per query | none for searches (synonyms via `data/cache/molecular`) | — |
| 03c (REFUSED) | `check_studytype.py` | `https://clinicaltrials.gov/api/v2/studies/{nct}` (`:14`) | `requests.get` | none | no retry; aborts after 10 consecutive failures; 0.15 s pause | 15 s | one per NCT | none | — |
| 04 (REFUSED) | `04_literature_independence.py` | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils` esearch/efetch; `https://api.semanticscholar.org/graph/v1/paper` | `requests.get` | `NCBI_API_KEY` (optional), `S2_SLEEP` | S2: 5 retries, backoff, Retry-After; NCBI 0.34/0.11 s pause | 20/30 s | retmax 30 with no date bound (TD-021) | checkpoint `data/_literature_checkpoint.jsonl` | n/a |
| **04p** (CONFIRM) | `04p_literature_provenance.py` | `…/eutils/esearch.fcgi`, `efetch.fcgi` (`:41`) | `requests.Session` | `NCBI_API_KEY` (optional; used only if ≥20 chars and not a placeholder, `:62-64`) | 3 retries, `2·2^n` s on 429/500/502/503/504; other codes stop; 0.11 s (key) or 0.35 s pause (`:80-99`) | 30 s | sample retmax 30, cutoff-bounded retmax 500 (`:43`), efetch in chunks of 200 | `data/cache/pubmed_lit/<slug>.json`, atomic; valid only if `cache_version`, query, cutoff and efetch sha256 match; no TTL; `--refresh`, `--offline` (`:285-306`) | `pubmed_lit/`: **90** |
| 05 (REFUSED) | `05_safety_signal.py` | `https://api.fda.gov/drug/label.json` (`:12`) | `requests.get` | none | no retry; 0.3 s pause; failures to `_safety_failures.jsonl` | 20 s | `limit=1` | `data/cache/openfda_labels/` (non-atomic write `:71`); checkpoint `_safety_checkpoint_v2.jsonl` | `openfda_labels/`: **83** |
| **05h** (CONFIRM) | `05h_safety_label_history.py` | `https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{setid}/history.json`, `…/getFile.cfm?type=zip` (`:38`) | `requests.Session` | none | 3 retries, `2·2^n` s on 429/5xx; 0.25 s pause (`:62-79`) | 60 s | ≤3 requests per labelled compound; follows only the current set ID | `data/cache/dailymed/{history,spl}/`, atomic; **history cached forever** (new label versions are never seen without deleting the cache) | `dailymed/history`: **83**, `dailymed/spl`: **110** |
| 08 (REFUSED) | `08_molecular_pathway.py` / `molecular_agent.py` | `https://api.platform.opentargets.org/api/v4/graphql` | `requests.Session.post` | none | 4 retries, exponential backoff plus jitter, Retry-After ≤60 s, 0.25 s throttle; GraphQL errors and other 4xx not retried | 60 s | batches of 25; PD module top 300 | `data/cache/molecular/<sha256>.json`, atomic, no TTL, corrupt entries refetched | `molecular/`: **311** |
| 10c `--fetch` (CLI only) | `clinical_evidence_agent.py` | `https://clinicaltrials.gov/api/v2/studies` (filter.ids) | `requests.get` | none | **none** (no retry, no pause) | 60 s | 20 IDs per batch, `pageSize=20`, no page token | `data/cache/ctgov_precutoff_trials.json` (protected), atomic; kept only if every batch failed | single file present |
| 10f `--fetch` (CLI only) | `safety_evidence_agent.py` | `https://api.fda.gov/drug/event.json` | `requests.get` | none (no `api_key`) | none; 0.3 s pause; failed entries retried on the next `--fetch` | 30 s | `limit=1` / `limit=10` counts | `data/cache/openfda_faers/<name>.json`, **non-atomic**, no TTL | `openfda_faers/`: **90** |
| 10a `--graph` (CLI only) | `literature_credibility_agent.py` | `…/eutils/efetch.fcgi` | `requests.get` | none (docstring runs with `env -u NCBI_API_KEY`) | none; `raise_for_status` | 60 s | ≤200 PMIDs, refuses more | only with `--save-xml` | `pubmed_efetch_droxidopa.xml`, `pubmed_efetch_case_claims.xml` present |

Other caches under `data/cache/`: `opentargets_20.11/` (7 files; a public Open Targets FTP snapshot used by historical-sensitivity scripts, not by the agents) and `ctgov_td038_shared_trials.json`.

---

## 10. Cross-cutting findings

1. **Exit-1-on-PARTIAL versus the runner.** 10a-all (`literature_credibility_agent.py:520`), 04p (`:476`) and 05h (`:256`) exit 1 when any unit failed. Only stages 04 and 05 are treated as PARTIAL on exit 1 (`run_stage.py:66`). A partially successful run of these three stages is therefore recorded as **FAILED, and the previous outputs are restored**. Partial results can never be published through the runner or UI. 10b, 10c, 10f and 10g exit 0 on PARTIAL and do publish.
2. **Non-atomic writers:**
   - 10b output (`molecular_run_record.py:84`);
   - 10a `--curated` outputs (`:528`);
   - the 10f FAERS cache (`:297`);
   - stage 05's label cache (`05_safety_signal.py:71`);
   - stage 08's CSV and JSONL (`08_molecular_pathway.py:357-362`).

   The runner's restore covers declared outputs only. Caches are not declared outputs.
3. **Exit code ignores FAILED** for 10a `--curated`, 10d, 10e and 10h (main returns None or 0). This is mitigated by the runner's `_validate_file` FAILED check, but direct CLI runs report success.
4. **Silent data loss:** 10d skips malformed molecular JSONL lines without a diagnostic (`conflict_context_agent.py:378-381`).
5. **Consumers ignore upstream run_status.** 10g reads `clinical_evidence.json`, and 10h reads the agent outputs, regardless of their run_status. 10h only reports it.
6. **10b is outside 10h's view.** `molecular_agent_run.json` is not in `AGENT_OUTPUTS` and not in 10h's `depends_on`.
7. **Registry versus actual inputs drift.** Runner STALE detection uses only the registry `inputs`. These per-agent inputs are missing from the registry:
   - 10d: the label cache;
   - 10e: `literature_graph_*.json`;
   - 10f: the FAERS and label caches;
   - 10a-all: `pubmed_lit/*`.

   The envelope `inputs` do include them, so the dashboard's envelope staleness still catches changes.
8. **Envelope staleness ignores inputs that were absent at run time**, because `input_hashes` omits them (`agent_contract.py:56-58`).
9. **Stage 08 has no `timeout_s`**, so a hung Open Targets retrieval run from the CLI blocks indefinitely. It is REFUSED in the UI.
10. **No cancellation exists** anywhere. Timeout kills the child and restores outputs; that path is tested in `tests/test_run_tracking.py::TestStageTimeout` (`:360-394`), which also asserts that every launchable stage has a `timeout_s`.

---

## 11. Test execution record (offline, `./venv/bin/python -m unittest tests.<module>`)

| Module | Executed | Pass | Unique tests | Mocking |
|---|---|---|---|---|
| test_literature_credibility_agent | 28 | 28 | 28 | socket connect patched; saved XML; fake 04p session |
| test_molecular_agent | 69 | 69 | 69 | fake `requests.Session` objects / mock patches |
| test_molecular_vps_audit | 16 | 16 | 16 | mock patches; one test covers `molecular_run_record` |
| test_clinical_evidence_agent | 19 | 19 | 16 | injected fake `get` (503, TimeoutError) |
| test_conflict_context_agent | 25 | 25 | 25 | none (temp root + persisted) |
| test_reproducibility_agent | 21 | 21 | 21 | none |
| test_safety_evidence_agent | 21 | 21 | 20 | injected fake `get` (500/429/non-JSON) |
| test_evidence_independence_agent | 11 | 11 | 7 | none |
| test_completeness_gap_agent | 20 | 20 | 20 | none |
| test_eight_agents_integration | 7 | 7 | 7 | none; real persisted data, asserts nothing was written |
| test_literature_provenance (04p) | 13 | 13 | 13 | fake session, no-op sleep (429 recovery, 500 exhaustion, corrupt cache) |
| test_safety_label_history (05h) | 5 | 5 | 5 | fake session (503), offline replay |

All modules passed, with no skips and no failures.

---

## 12. Summary table

| Agent | Purpose | Trigger (stage, UI policy) | Inputs | External sources | Output | Persistence | Downstream consumer | Offline tests (count, pass) | Untested failure modes |
|---|---|---|---|---|---|---|---|---|---|
| 10a Literature Credibility | Study-design tier per paper (A–D/X); no efficacy; direction only from curated claims | `10a` (`--curated`, deps none) and `10a-all` (`--all`, deps 04p); both ALLOWED; 900 s | 04p `literature_provenance.csv`, `literature_papers.jsonl`, `cache/pubmed_lit/*`; curated XML + claims | None in stage modes; reads 04p (NCBI E-utilities, `NCBI_API_KEY` optional). `--graph` CLI: live efetch, no retry | `literature_credibility_all.json` (schema 1.1) + 4 curated JSONs (1.0) | `--all` atomic; `--curated` non-atomic; **`--all` exits 1 on PARTIAL, so the runner marks FAILED and restores** | 10h; UI `/api/compound`, `/api/agents`, `/api/agent`, `/api/live`; not stage 06 | 28 / 28 (+ integration) | missing or empty 04p CSV/JSONL, malformed JSONL, PARTIAL→FAILED runner interaction, live `--graph` HTTP errors |
| 10b Molecular Plausibility | Stage 08: Open Targets drug→target→pathway→PD score (VPS dim 5); 10b re-validates and writes envelope | `08` (REFUSED, no timeout); `10b` (deps 08, 06; ALLOWED; 900 s) | `molecular_pathway.csv`, `…_evidence.jsonl`, `vps_scores_v2.csv` | Stage 08: Open Targets GraphQL, 4 retries, backoff, Retry-After, 0.25 s throttle, `cache/molecular` (311 files, no TTL) | `molecular_agent_run.json` (agent_version "unrecorded") | non-atomic write; runner restore on FAILED | **Stage 06 reads `molecular_pathway.csv`**; 10c/10d/10g read the JSONL; 10h reads the CSV but not the 10b envelope | 69 / 69 (stage 08) + 1 run-record test in 16 / 16 audit | invalid JSONL lines in run record, missing JSONL/CSV, stage-08 hang, cache staleness |
| 10c Clinical Evidence | Per-trial registry status, verbatim posted results, drug role, matching-audit counts | `10c` (deps 03c, 08, 06; ALLOWED; 900 s); `review` downstream | `clinical_maturity_precutoff_clean.csv`, match audit, TD-038 roles, pool, `cache/ctgov_precutoff_trials.json`, molecular JSONL | None by default; `--fetch` CLI: CT.gov v2 `filter.ids` × 20, no retry or pause; upstream stage 03 CT.gov | `clinical_evidence.json` | atomic; old cache kept only if all batches fail | 10g, 10h; UI `/api/evidence`, `/api/compound`; not stage 06 (stage 06 uses 03c CSV) | 19 / 19 (16 unique) | partial-batch cache overwrite, 429, malformed cache JSON, missing links CSV |
| 10d Conflict & Context | Classify disagreements between curated, label, molecular and trial claims | `10d` (deps 05, 08, 06; ALLOWED; 900 s) | curated claims, `cache/openfda_labels/*`, molecular JSONL, trials CSV, pool | None; upstream 05 openFDA label, 08 Open Targets | `conflict_context.json` | atomic; always exits 0 | 10h; UI `/api/conflicts`, `/api/overview`, `/api/compound` | 25 / 25 | malformed label JSON (crash), silently skipped malformed molecular lines, FAILED path, exit code |
| 10e Reproducibility | Finding-level replication by independent primary-study clusters | `10e` (deps 10d, ordering only; ALLOWED; 900 s) | 2 cached efetch XMLs, curated claims, `literature_graph_*.json` (undeclared), trial CSVs | None; static saved PubMed XML | `reproducibility.json` | atomic; always exits 0 | `vps_evaluation_report.py` (eval), 10h; UI `/api/case_status`, `/api/compound` | 21 / 21 | all inputs absent (FAILED), malformed curated or graph JSON, undeclared input staleness in runner |
| 10f Safety Evidence | Label provenance + label-at-cutoff + FAERS counts with explicit states | `10f` (deps 05, 05h, 06; ALLOWED; 900 s) | pool, `safety_signal.csv`, `_safety_failures.jsonl`, `safety_label_history.csv`, FAERS + label caches | None by default; `--fetch` CLI: openFDA drug/event, no key, no retry, 0.3 s pause; upstream 05 (openFDA label), 05h (DailyMed) | `safety_evidence.json` | atomic output; **non-atomic FAERS cache** | 10h; UI `/api/compound`; not stage 06 (stage 06 uses 05 CSV) | 21 / 21 (20 unique) | malformed cache JSON (crash), truncated cache after a killed fetch, missing pool, 429 storms |
| 10g Evidence Independence | Cross-source dependence checks D1–D5 | `10g` (deps 10c, 04, 08, 04p, 06; ALLOWED; 900 s) | pool, links, lit CSV, curated claims, `clinical_evidence.json`, molecular JSONL, XMLs, 04p papers + cache | None; upstream 04p/04 (PubMed, Semantic Scholar), 08, 10c | `evidence_independence.json` | atomic; exits 1 on FAILED | 10h; UI `/api/compound`; not stage 06 (stage 06 uses 04 CSV) | 11 / 11 (7 unique) | missing pool or links, malformed 04p JSONL or 10c JSON, FAILED 10c consumed, duplicate pool rows |
| 10h Completeness & Gap | Per compound × 12 domains: availability state, gaps, open questions, agent staleness, stage-06 agreement | `10h` (deps 06, 10a-all, 10a, 10c–10g; **not 10b**; ALLOWED; 900 s) | stage 02–08 outputs, 10a/10c–10g outputs, failure files, TD-038 roles | None | `completeness_gaps.json` | atomic; always exits 0; raises on stage-06 disagreement | UI `/api/gaps`, `/api/compound` (intended Stage 11; not implemented) | 20 / 20 | malformed upstream JSON, FAILED upstream consumed as data, 10b staleness unchecked, missing vps CSV |
