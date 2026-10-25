# Data-point and lineage audit

## Machine-readable outputs

| File | Rows | Content |
|---|---|---|
| `records/ground_truth_row_audit.csv` | 90 | per candidate: saved and independent label, status, prior decision, label trials with dates, role exclusions, trials dropped by the study-type filter, unverifiable trials, saved = re-ascertained, pre-cutoff counts, live registry hits, truncation flag, open review links |
| `records/independent_scores.csv` | 90 | per compound: each stored and recomputed rank, absolute differences, stored and recomputed 4D/5D score, neutral count |
| `records/data_integrity_findings.csv` | 21 | one row per deviation or notable record (0 HIGH, 2 MEDIUM, 19 INFO) |
| `records/reascertain/reascertain_trials.csv` | 1 row per (compound, trial) returned live | NCT, first posted, study type, intervention types, phases, status, gates, match, arm groups, interventions, conditions, title |
| `records/reascertain/alias_search_negatives.json` | — | 691 alias queries, the 151 additional PD trials and their matcher verdicts, 4 failed queries |
| `records/protected_inventory.json` | 19 | sha256, bytes, mtime, rows and schema of every protected artefact |

## Identity
- 90 compounds with 90 unique DrugBank IDs (`Compound::DB…`) and 90 unique resolved ChEMBL IDs.
- No salt or formulation near-duplicates; all `resolved = True`.
- Exclusion list: 41 names removed by exact name match (`00_exclusion_filter.py`). Its only source is that file, with no external reference. "Caffeine" and "Nicotine" are marked "borderline" in a comment that refers to a note which does not exist (C-documentation, TD-010).
- Every pool compound is in `pd_candidates_filtered.csv`. The pool equals filtered ∩ compounds with an accepted pre-cutoff trial.
- No compound outside the pool enters scoring: the 51 extra rows in `literature_independence.csv` and the 1,226 in `network_proximity.csv` are ignored by the left join.

## Joins and keys

| File | Rows | Key | Duplicates | Pool coverage |
|---|---|---|---|---|
| `vps_scores_v2.csv` | 90 | compound | 0 | — |
| `molecular_pathway.csv` | 90 | compound | 0 | 90/90 |
| `safety_signal.csv` | 90 | compound | 0 | 90/90 (7 without a label) |
| `literature_independence.csv` | 141 | compound | 0 | 90/90 (+51 outside the pool) |
| `network_proximity.csv` | 1314 | compound | 0 | 88/90 (Deferiprone and Trimethobenzamide have no row: no target in the network, median-imputed and flagged) |
| `clinical_maturity_precutoff_clean.csv` | 195 | (compound, NCT) | 0 | 90/90 |
| `ground_truth_postcutoff_clean.csv` | 57 | (compound, NCT) | 0 | — |
| `label_role_exclusions.csv` | 3 | (compound, NCT) | 0 | every row matches a label trial |

**Raw values equal their sources for every compound:** proximity_z, max_phase_rank (recomputed from trials), n_trials, effective_independent_count, serious_term_count, molecular score, and the safety-missing flag. 0 mismatches.

**Dates:**
- every feature trial is first posted before 2021-01-01 (latest 2020-11-25);
- every label trial is between 2021-01-01 and 2026-10-05 (earliest 2021-01-13);
- no NCT appears in both windows.

**Many-to-many:** 17 pre-cutoff trials are credited to 31 compounds (S-22, TD-038), so the clinical dimension double-counts shared evidence by design.

## Provenance and fingerprints
- The approved run `adopted-20261015T015501Z-06` has all 16 input/output md5s matching. It has no code fingerprint (S-14).
- The evaluation report has 7 recorded input md5s, all matching. `data/reproducibility.json` is not fingerprinted by the run record (S-13).
- **Retrieval dates:**
  - recorded: ClinicalTrials.gov cache (2026-10-05), the 04p PubMed run, the 05h DailyMed run, the per-compound FAERS cache;
  - **not recorded:** the openFDA label retrieval, the Open Targets retrieval (data version 26.09 is recorded), and Hetionet (v1.0, 2017).

## Stale or mixed generations
- Agent outputs were regenerated with the current code; their content is identical (S-17).
- The approved score file predates the `dimensions_imputed` column (B-003 / D-024); the UI derives the flag from raw data.
- Stage-07 figures are older than the latest label policy (TD-032 note). They are not used by the UI's charts, which are computed from the approved files.

## Evidence links
UI identifier links are built only from identifiers that match strict patterns:
- `NCT\d{8}` → clinicaltrials.gov/study;
- PMID → pubmed;
- DailyMed set ID;
- ENSG;
- CHEMBL;
- R-HSA.

During this audit, live lookups confirmed that NCT02005029 (record and first-posted date), the Donepezil DailyMed set ID (03e26183-…), ENSG00000087085 (ACHE) and the PubMed queries resolve to the expected records.
