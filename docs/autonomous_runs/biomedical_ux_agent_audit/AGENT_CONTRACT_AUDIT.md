# Eight-agent functional audit (2026-10-20)

## How this was established

- **Code trace.** Every row comes from the current code, cited `file:line` in `evidence/agent_trace.md`. A read-only sub-audit produced the trace, and I re-checked its main claims myself:
  - the runner's partial-on-exit-1 set (`scripts/run_stage.py:66`);
  - 04p/05h/10a-all exit 1 on any failure;
  - stage 08 has no `timeout_s`;
  - 10d silently skips malformed molecular lines (`scripts/conflict_context_agent.py:376-381`);
  - 10h never acts on upstream `run_status` and does not depend on 10b (`ui/server.py:384`).
- **Offline runs (real runner, not mocks).**
  - Each agent stage was run by `scripts/run_stage.py` in an isolated copy of `data/`.
  - Inputs were made malformed, empty, missing or header-only (34 runs; `evidence/agent_fault_matrix.json`).
  - The deterministic subset is now a repository test: `tests/test_agent_failure_modes.py`, 4 tests.
- **Existing unit tests.** All agent test modules ran and passed. 10a, 10b, 10c and 10f mock their HTTP layer with injected fake sessions; 10d, 10e, 10g and 10h use no mocks. Mocked tests are **not** counted as online evidence.
- **Online checks.** One small read-only request per external source, through the project's own client code (`ONLINE_INTEGRATION_RESULTS.md`).

## Important framing

None of the eight agent stages makes a network request in the mode the runner and the UI use. Each reads data retrieved earlier by an upstream stage:
- 03/03c: ClinicalTrials.gov
- 04: PubMed and Semantic Scholar
- 04p: PubMed
- 05: openFDA label
- 05h: DailyMed
- 08: Open Targets

Network code inside the agents themselves exists only in command-line flags the UI never passes: `10a --graph`, `10c --fetch` and `10f --fetch`. "Online verification" below therefore means verifying the **upstream source the agent depends on**, plus the agent's own fetch function where one exists.

Stage 06, the approved score, reads **no** agent output. It reads only stage files from 03c, 04, 05 and 08. The four agents labelled "feeds the score" (10b, 10c, 10f, 10g) feed it only through their upstream stage.

## Contract table

The `Offline test` column has two parts: (a) existing unit tests; (b) real-runner fault injection, where *fail-closed* means a malformed or empty input gave FAILED, the previous output was restored byte-identical, last success was unchanged, and the dashboard showed "Run failed".

| Agent | Purpose (from code) | Trigger | Inputs | External sources | Output | Persistence | Downstream consumer | Offline test | Online verification | Known limitations | Final status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **10a Literature Credibility** | Rates study *design* credibility (tiers A–D/X from PubMed PublicationType); never efficacy | stage `10a` (`--curated`) and `10a-all` (`--all`, after 04p); UI: can run here | 04p provenance CSV/JSONL + `data/cache/pubmed_lit/*`; curated PMIDs XML + curated claims | none in stage mode; upstream 04p = NCBI E-utilities; `--graph` = live efetch (CLI only) | `literature_credibility_all.json`, `literature_credibility_<case>.json` (envelope) | `--all` atomic; `--curated` non-atomic (runner restores on failure) | 10h; UI candidate pages | (a) 28/28 (04p path mocked); (b) fail-closed for malformed/empty/missing/header-only, 8/8 | upstream PubMed **PASS**: `04p.retrieve('Donepezil')` returned 140 cutoff-bounded PMIDs, identical to the saved cache | exit 1 on any PARTIAL makes the runner record FAILED and restore, so a partial result can never be published; `--graph` live path has no retry and was not tested online | **PARTIAL** |
| **10b Molecular Plausibility** | Re-validates the stage-08 drug→target→pathway→PD records (stage 08 = score dimension 5) | stage `10b` (after 08, 06); UI: can run here. Stage 08: needs owner approval | `molecular_pathway.csv`, `molecular_pathway_evidence.jsonl`, `vps_scores_v2.csv` | none in 10b; upstream 08 = Open Targets GraphQL (4 retries, backoff, cache without TTL) | `molecular_agent_run.json` | non-atomic write (runner restores on failure) | not read by 06 or 10h; UI | (a) 69/69 + 16/16 (HTTP mocked); (b) fail-closed for malformed/empty/missing, 3/3 | Open Targets **PASS**: target ENSG00000087085 = ACHE (Donepezil's target), live data version 26.09 = recorded version | `agent_version` "unrecorded"; stage 08 never re-run under the tracker (recorded baseline) and has **no timeout**; 10h does not check 10b | **PARTIAL** |
| **10c Clinical Evidence** | Per pre-2021 trial link: registry status, verbatim posted results, the drug's role (human adjudication takes precedence); never scores | stage `10c` (after 03c, 08, 06); UI: can run here | clean pre-cutoff trials, match audit, adjudicated roles, `ctgov_precutoff_trials.json` cache | none in stage mode; `--fetch` = ClinicalTrials.gov v2 (no retry, no pause; CLI only) | `clinical_evidence.json` | atomic | 10g, 10h, review queue; UI | (a) 19/19 (fetch mocked); (b) fail-closed for malformed/empty/missing/header-only, 4/4 | ClinicalTrials.gov **PASS**: NCT02005029 is interventional; first-posted date 2013-12-09 equals the saved record; an invalid id returns an error (HTTP 400), not a study | `--fetch` has no retry/backoff; pre-cutoff trials only; roles automated except human-adjudicated links | **PASS** |
| **10d Conflict & Context** | Classifies disagreements between source-linked claims (contradiction, significance-only, context, cross-domain); never averages | stage `10d` (after 05, 08, 06); UI: can run here | curated claims (protected), openFDA label cache, molecular JSONL, trials, pool | none; upstream 05 openFDA, 08 Open Targets | `conflict_context.json` | atomic; exit 0 even on FAILED (runner validation catches it) | 10h; UI conflicts pages | (a) 25/25 (no mocks); (b) malformed/empty/header-only fail-closed; **missing** curated file publishes PARTIAL with an `INPUT_MISSING` diagnostic | upstream openFDA label **PASS** | **malformed molecular JSONL lines are skipped silently** (no diagnostic); curated claims exist only for case-study compounds | **PARTIAL** |
| **10e Reproducibility** | Finding-level replication: counts independent primary-study clusters; reviews are never replicates | stage `10e` (after 10d); UI: can run here | case-claim and Droxidopa efetch XML, curated claims, `literature_graph_*.json` (not declared to the runner), trial CSVs | none (static PubMed XML saved earlier) | `reproducibility.json` | atomic; exit 0 even on FAILED (runner validation catches it) | `eval` report, 10h; UI | (a) 21/21 (no mocks); (b) malformed/empty fail-closed; missing XML publishes PARTIAL with a diagnostic | no live source of its own (offline by design); upstream PubMed **PASS** | coverage limited to case-study compounds; author matching by last name + initial; undeclared graph inputs are invisible to runner staleness (the envelope still sees them) | **PASS** |
| **10f Safety Evidence** | Keeps FDA label facts and FAERS report counts separate per compound; no score | stage `10f` (after 05, 05h, 06); UI: can run here | pool, `safety_signal.csv`, label history, failures, FAERS + label caches | none in stage mode; `--fetch` = openFDA FAERS (no key, no retry); upstream 05 openFDA label, 05h DailyMed | `safety_evidence.json` | output atomic; FAERS cache **non-atomic** | 10h; UI candidate pages | (a) 21/21 (HTTP mocked); (b) malformed/empty fail-closed; missing or header-only label CSV publishes PARTIAL with a diagnostic | **PASS**: `fetch_faers('Donepezil')` all 4 queries HTTP 200; reports received by 2020 = 28,152, identical to the saved cache. openFDA label: same set ID and effective date as saved; no-match = HTTP 404 → "no label". DailyMed history: 3 versions, same as cached; same version in force at the cutoff | FAERS: no denominator, no causality; non-atomic cache write can truncate on a kill; no 429 backoff | **PASS** |
| **10g Evidence Independence** | Five cross-source dependence checks (shared trial, same study in two dimensions, pooled claims, molecular datatype reuse, duplicate publication) | stage `10g` (after 10c, 04, 08, 04p, 06); UI: can run here | pool, trial links (required); literature CSV, curated claims, 10c output, molecular JSONL, XMLs, 04p cache (optional) | none; upstream 04p PubMed, 04 PubMed/Semantic Scholar | `evidence_independence.json` | atomic | 10h; UI | (a) 11/11 (no mocks); (b) malformed/empty fail-closed; missing literature CSV → PARTIAL | upstream PubMed **PASS**; Semantic Scholar **BLOCKED** (HTTP 429, no API key) | **a header-only `literature_independence.csv` is accepted as SUCCESS with no diagnostic** (per-compound literature fields become empty); does not check 10c's `run_status` before using it | **PARTIAL** |
| **10h Completeness & Gap** | Per candidate × 12 domains: measured / measured zero / partial / absent / not computed / not retrieved / failed / insufficient, with gaps and staleness | stage `10h` (after 06, 10a–10g except 10b); UI: can run here | pool (required) and every other stage and agent output | none | `completeness_gaps.json` | atomic; exit 0 except on exceptions | UI candidate pages and Overview coverage | (a) 20/20 (no mocks); (b) malformed/empty/header-only fail-closed; missing 10d output → PARTIAL with `AGENT_OUTPUT_ABSENT`; upstream failure → **BLOCKED** in a sequence (test) | no external source (offline by design) | records upstream `run_status` but uses a FAILED upstream output's data anyway; does not see 10b; validation raises on disagreement with stage 06 (fails closed) | **PARTIAL** |

**Status key.**
- **PASS:** the agent's real responsibility runs through the real runner, fails closed on bad input, and its live upstream source returned data identical to what the agent uses. Only documented limitations remain.
- **PARTIAL:** it works and fails closed on corrupt input, but at least one confirmed defect can silently degrade output or provenance, or an important path is unverified.

No agent is FAIL. None is BLOCKED overall; Semantic Scholar is blocked as a source.

## Behaviour common to all eight, verified

1. **A corrupt input never looks fresh.** In 27 of 34 fault runs the attempt was FAILED, the previous output was restored byte-identical, last success was unchanged, and the dashboard showed "Last run failed; previous results retained" (overall state FAILED).
2. **Six runs published a PARTIAL result.** Five had a *missing optional* input (10d, 10e, 10f, 10g, 10h); one had a header-only safety CSV (10f). Each carried a diagnostic, and the dashboard showed the inputs as changed, not current. That is the documented design: missing evidence is reported, not treated as negative.
3. **One run reported SUCCESS:** 10g with a header-only literature CSV (row 10g).
4. **An upstream failure blocks dependants.** With `--sequence 10d 10h` and a corrupt 10d input, 10h is reported "Blocked by a failed prerequisite" (`test_upstream_failure_blocks_dependants_in_a_sequence`).
5. **The UI separates execution from evidence quality.** Agent cards show "Run completed" and "Output checks: passed" separately, with the note that neither is a scientific validation. Candidate pages show evidence *states* (measured, missing, not retrieved), not run states.
6. **No agent adjudicates trial roles.** The review queue has no decision control (browser check).

## Defects found (not fixed: they are pipeline code, outside the UI redesign; each is reproducible)

| # | Defect | Reproduce | Suggested fix (owner) |
|---|---|---|---|
| A-1 | Partial results of 04p, 05h and 10a-all are discarded: exit 1 maps to FAILED and the previous output is restored | make one compound's 04p cache unreadable and run `10a-all` | add them to `PARTIAL_ON_EXIT1` or exit 0 with a PARTIAL envelope |
| A-2 | 10g accepts a header-only `literature_independence.csv` as SUCCESS | `head -1 data/literature_independence.csv > copy/data/literature_independence.csv`, then `run_stage.py 10g --root copy` | add an `INPUT_EMPTY` warning |
| A-3 | 10d skips malformed molecular JSONL lines without a diagnostic | append a bad line to the molecular JSONL in a copy, then run 10d | emit `MALFORMED_LINE` as 10g does |
| A-4 | 10h uses data from upstream outputs whose `run_status` is FAILED, and ignores 10b | — | mark those domains NOT_COMPUTED; add 10b to inputs and dependencies |
| A-5 | Stage 08 has no `timeout_s` | — | add a timeout (it can only be started from the command line) |
| A-6 | Non-atomic writes: 10b output, 10a `--curated`, 10f FAERS cache, 05 label cache, 08 CSV/JSONL | — | `.tmp` + `os.replace` |
| A-7 | Inputs absent at run time are not fingerprinted, so their later appearance is not detected | — | record absent inputs as `null` in `inputs` |
