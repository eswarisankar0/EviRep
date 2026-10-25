# Online integration results (2026-10-20, 15:53–15:54 UTC)

## What was done

- **Scope.** One small, read-only request (or one compound's worth) per external source that the pipeline is configured to use. No full network pipeline was run.
- **Client code.** Every request went through the **project's own client function** where one exists, so the check exercises the configured endpoint, parameters and parsing.
- **Isolation.** Responses were written only to a scratch directory. Nothing in the repository or its caches was written; `git status` of `data/` was unchanged afterwards.
- **Script and raw results:** `evidence/online_check.py` and `evidence/online_results*.json`.

**Credentials (names only, values never read or printed).**
- The project declares one optional credential, `NCBI_API_KEY` (`.env.example`). It is **not set** in this environment, and there is no `.env` file.
- No Semantic Scholar or openFDA key is configured.
- All checks therefore ran anonymously, within each service's anonymous rate limit.

## Results

| Source (used by) | Endpoint (from code) | Client function exercised | HTTP / schema | Data check against what the project saved | Result |
|---|---|---|---|---|---|
| **PubMed E-utilities** (04p → 10a, 10g) | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils` esearch + efetch | `04p_literature_provenance.retrieve("Donepezil")` (2 esearch + efetch, 5 s) | 200; XML parsed by the stage's own parser: 170 records, 0 missing | Cutoff-bounded result: **140 PMIDs, identical to the saved cache**. The 30-paper recency sample is expected to drift. Of the 170 parsed records, 83 mention donepezil in their parsed title or MeSH fields; the query is the stage-04 query. | **PASS** |
| PubMed: empty result | same | `esearch` with a nonsense term | 200, count 0 | Zero records come back as zero, not as evidence. | **PASS** |
| **ClinicalTrials.gov API v2** (03/03c → 10c) | `https://clinicaltrials.gov/api/v2/studies/{nct}` | `check_studytype.get_study_info("NCT02005029")`, plus one fields-restricted GET | 200; `protocolSection.identificationModule` / `statusModule` present | Interventional with 2 drug interventions; **first-posted 2013-12-09 = saved record** (Erythromycin). | **PASS** |
| ClinicalTrials.gov: invalid id | same | `get_study_info("NCT00000000")` | HTTP 400 | Returned as `ERROR`, not as a study. | **PASS** |
| **openFDA drug label** (05 → 10d, 10f, score dimension 4) | `https://api.fda.gov/drug/label.json` | `05_safety_signal.query_label("Donepezil")` | 200; `results[0].openfda` present | **Same set ID (03e26183-…) and effective date (20241129) as saved.** | **PASS** |
| openFDA label: no match | same | `query_label("Zzzqxnotadrug")` | HTTP 404 | Returned as `None`; stage 05 records it as "no FDA label (absent at source)", which is not negative evidence. | **PASS** |
| **openFDA adverse events (FAERS)** (10f `--fetch`) | `https://api.fda.gov/drug/event.json` | `safety_evidence_agent.fetch_faers("Donepezil")` (4 queries) | 200 ×4; `meta.results.total` present | **Reports received by 2020-12-31: 28,152 live = 28,152 saved.** All-time totals grow and are labelled as such. | **PASS** |
| **DailyMed SPL history** (05h → 10f) | `https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{setid}/history.json` | `05h_safety_label_history.history(...)` into a scratch cache | 200; parsed by the stage's own parser | **3 versions live = 3 cached**; the version in force at the cutoff (v6, 2019-01-16) is the same. | **PASS** |
| **Open Targets Platform GraphQL** (08 → 10b, score dimension 5) | `https://api.platform.opentargets.org/api/v4/graphql` | `molecular_agent.OpenTargetsClient.query(...)` with the cache disabled | 200; `data.target.approvedSymbol` | ENSG00000087085 = **ACHE** (Donepezil's target in the saved evidence); **live data version 26.09 = the version the dashboard records for the saved run**. | **PASS** |
| **Semantic Scholar Graph API** (04 only; stage refused in the UI) | `https://api.semanticscholar.org/graph/v1/paper/PMID:17557339` | direct anonymous GET | **HTTP 429** | Not verified: anonymous requests are rate-limited and no key is configured. | **BLOCKED** |
| **Zenodo, Hetionet v1.0 archive** (01; stage refused in the UI) | `https://zenodo.org/records/268568/files/dhimmel/hetionet-v1.0.0.zip` | HEAD only | 200, 154,927,387 bytes | Reachability only. The 155 MB archive was not downloaded; the pipeline uses the local snapshot. | **PASS (reachability)** |

**Harness errors (not service failures).** The first attempt for PubMed and Open Targets failed in my script: I passed a number where the stage expects a sleep function, and loaded a dataclass module the wrong way. Both were re-run correctly; see `online_results_run1.json` and `online_results_retry.json`. Neither failure was a service failure.

## Per-agent online summary

| Agent | Network in its stage mode? | Online evidence |
|---|---|---|
| 10a | no | upstream PubMed verified; own `--graph` live path not exercised |
| 10b | no | upstream Open Targets verified (same data version) |
| 10c | no | ClinicalTrials.gov verified; own `--fetch` (no retry) not exercised at scale |
| 10d | no | upstream openFDA label verified |
| 10e | no | offline by design (saved PubMed XML) |
| 10f | no | own FAERS fetch function verified; openFDA label and DailyMed verified |
| 10g | no | upstream PubMed verified; Semantic Scholar blocked (429) |
| 10h | no | offline by design |

## Not verified online

- **Full online stages.**
  - 04p would make about 270+ requests and 05h about 250.
  - 03/03c/04/05/08 rewrite protected files, so they must not run here.
  - Retrieval *functions* were verified instead, on one representative compound.
- **Rate-limit behaviour under load.** Only the anonymous 429 from Semantic Scholar was observed. Retry and backoff code is covered by mocked unit tests (`test_molecular_agent`, `test_literature_provenance`), which are **mocked**, not online evidence.
- **Pagination beyond one page.** ClinicalTrials.gov `--fetch` assumes `pageSize=20` per 20-id batch; esearch `retmax` 500 truncation was not exceeded for Donepezil (140 records).

## Reproduce

```
./venv/bin/python docs/autonomous_runs/biomedical_ux_agent_audit/evidence/online_check.py /tmp/evirep_online
```

The script writes only to the given directory. It makes about 16 anonymous requests.
