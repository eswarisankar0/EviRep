# Ground-truth audit (all 90 candidates)

**Row-level file:** `records/ground_truth_row_audit.csv` (90 rows). It is built by `scripts/ground_truth_audit.py` from the saved files and the live re-ascertainment in `records/reascertain/`.

## The rule, as implemented and documented
- **Label = 1** if the compound has at least one trial that meets all of:
  - first posted on or after 2021-01-01 (string comparison on `studyFirstPostDate`, `03:304`), up to the 2026-10-05 snapshot (D-010);
  - Parkinson's in its conditions (Gate 1);
  - an intervention identity match on structured name / otherName / ChEMBL synonym (Gate 2);
  - INTERVENTIONAL with at least one DRUG or BIOLOGICAL intervention (`filter_by_studytype.py`);
  - not listed in `data/label_role_exclusions.csv` (owner policy P1, 2026-10-14).
- **Cohort:** compounds in `pd_candidates_filtered.csv` with at least one trial meeting the same gates, first posted before 2021-01-01.
- **No indeterminate class exists in code** (S-21).
- **Outcome meaning:** continued clinical investigation (D-010 / D-013), **not efficacy**.
- **What a negative means:** no qualifying trial was identified in ClinicalTrials.gov under these rules. It does not mean that no trial exists anywhere (other registries are not searched).

## How it was verified
1. **Re-derivation from files.** Labels = post-cutoff clean file minus exclusions: 90 of 90 agree (`records/data_integrity_summary.json`).
2. **Live re-ascertainment** (2026-10-20, read-only, `scripts/reascertain_ctgov.py`):
   - every page of `query.intr=<name>` + `query.cond="Parkinson Disease"`;
   - stage 03's own `is_actually_pd`, `match_trial` and alias map;
   - trials first posted after 2026-10-05 ignored (none qualified).
   - **101/101 searches succeeded. The post-cutoff qualifying sets equal the saved sets for all 90 compounds.**
3. **Alias search for the 76 negatives** (`scripts/alias_search_negatives.py`):
   - every ChEMBL synonym and trade name (at most 12 per compound), restricted to first posted 2021-01-01 to 2026-10-05;
   - 691 requests; 151 additional Parkinson's trials found, **none matched the compound under stage 03's matcher**;
   - 4 alias queries were rejected by the registry (HTTP 400; special characters): Naltrexone "EN-1639A [AS HYDROCHLORIDE]", two Sirolimus chemical names and "[11c]yohimbine". Those aliases are unverified.
4. **Role review** of every label trial: arm types, interventions and titles from the live registry, plus the documented prior human decisions (D-011, TD-032/P1, CASE_STUDIES §9).

## Results

| Status | Count | Compounds |
|---|---|---|
| Confirmed positive | 13 | Acetylcysteine, Atomoxetine, Donepezil, Levetiracetam, Lidocaine (owner, D-011), Melatonin, Methylphenidate, Mirabegron, Pyridostigmine, Quetiapine, Rifaximin*, Terazosin, Varenicline |
| Unresolved (owner) | 1 | **Galantamine** (D-011): its only label trial is a BASIC_SCIENCE DLB/PDD study with an open sub-cohort |
| Disputed (candidate correction 0 → 1, owner) | 1 | **Lithium**: 3 interventional PD trials typed DIETARY_SUPPLEMENT (S-02) |
| Confirmed negative under the rules | 75 | includes Clozapine, Dexmedetomidine and Remifentanil, whose only label trials were excluded by owner policy P1 |

\*Rifaximin's role as one component of a microbiota regimen was not separately adjudicated (S-04).

**Approved counts:** 14 positives / 76 negatives. **Independently derived under the same rules:** 14 / 76. **Labels changed by this audit:** 0.

**Withdrawn or suspended label trials still count**, as the rules require; there is no exclusion by status. Terazosin has one withdrawn and one suspended trial, among four others.

**Trials with results posted after the cutoff but first posted before it:** classified by first-posted date (features). 10c flags their results as POST_CUTOFF, and they never enter labels.

## Trial-role links awaiting human review
- **28 unresolved and 9 adjudicated** feature-trial links (`data/clinical_review_worklist.csv`). All 28 are **pre-cutoff feature** links, none is a label trial (checked by key join), so they cannot change a label.
- They can change clinical maturity once a role policy is applied (D-020, proposed). **None was resolved by this audit.**

## Search completeness
- Stage 03 truncated 12 compounds at 20 results (S-01). For the 90 cohort compounds, full pagination changes no label and no max phase.
- Outside the cohort, **Dopamine** would enter with full pagination (S-01).

## Acceptance criteria

| Criterion | Result |
|---|---|
| All 90 have a decision or an explicit unresolved status | PASS: 88 decided, 1 unresolved, 1 disputed |
| Every positive has at least one verified qualifying trial | PASS (Galantamine's is contested on role, not identity) |
| Every negative has a recorded search and its limits | PASS (`registry_hits_live`, `stage03_rows`, alias search, the 4 unverified aliases) |
| Every role exclusion has a specific reason | PASS (3 P1 rows cite CASE_STUDIES §9.1) |
| No unresolved review case silently promoted | PASS (28 remain unresolved) |
| Counts reconcile with the row audit | PASS (14 / 76) |
| Changed labels have source-backed rationale and tests | N/A (no label changed) |
