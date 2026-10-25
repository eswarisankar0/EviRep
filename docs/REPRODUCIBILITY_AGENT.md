# Reproducibility Agent (10e)

`scripts/reproducibility_agent.py` · tests `tests/test_reproducibility_agent.py` (18, offline,
socket-guarded) · output `data/reproducibility.json` (schema `1.0`, agent `10e-0.1`) · status:
**implemented, tested, shown in the dashboard; diagnostic only — not read by
`06_vps_fusion.py`** (decision D-017).

## Question
Is a finding supported by **independent studies**, or by several publications of one study,
one group, one dataset, or by syntheses of the same evidence? Independence is not quality
(10a) and not efficacy.

## How it differs from 10g and 10d
| Component | Unit | What makes two items dependent |
|---|---|---|
| 10g (stage 04, VPS "literature") | paper | shared author **or citation** → one component |
| 10d | claim pair | — (classifies disagreement) |
| **10e** | **finding** (compound × domain × outcome × direction) | same record, shared trial ID, documented shared data, shared author. A citation is recorded but does **not** make data dependent. Reviews/meta-analyses are never counted as replicates. |

## Inputs (persisted; no network at run time)
- `data/cache/pubmed_efetch_case_claims.xml` — one PubMed efetch (2026-10-15, 14/14 PMIDs of the
  curated case-study claims; HTTP 200): authors, years, PublicationTypes, DataBank trial IDs.
- `data/cache/pubmed_efetch_droxidopa.xml` — the 26-paper Droxidopa sample (10a, 2026-10-13).
- `data/conflict_claims_curated.json` — outcome-level claims (10d ledger) with direction and
  documented `overlap_group`.
- `data/literature_graph_droxidopa.json` — citation edges and 10g components (for comparison).
- trial registry rows (pre- and post-cutoff) — trials linked to more than one compound.

## Rules (deterministic, first match wins)
1. `SAME_RECORD` (same PMID) → DEPENDENT
2. `SHARED_TRIAL` (NCT ID in DataBank or abstract) → DEPENDENT
3. `DOCUMENTED_SHARED_DATA` (same `overlap_group` in the curated ledger) → DEPENDENT
4. `SHARED_AUTHORS` (≥1 author, last name + first initial) → DEPENDENT ("same group")
5. `METADATA_MISSING` (author list absent) → UNDETERMINED
6. `NO_SHARED_INDICATOR` → PLAUSIBLY_INDEPENDENT — *not proven*: populations and datasets
   are not persisted. Different PMIDs alone never imply independence.

Primary studies (RCT, controlled/clinical trial, observational, case report) are clustered by
union-find over DEPENDENT relations. Finding status:
`REPLICATED` (≥2 clusters agree, none disagrees; `cluster_independence` gives the weakest level),
`REPLICATED_WITH_DISAGREEMENT`, `SINGLE_STUDY`, `INCONSISTENT_SINGLE_STUDIES`,
`SECONDARY_ONLY`, `UNDETERMINED`, `INSUFFICIENT_METADATA`. **No numeric score.**

## Real run (2026-10-15)
14 findings: 1 REPLICATED, 6 SINGLE_STUDY, 7 SECONDARY_ONLY.
- **Propranolol / tremor:** REPLICATED by PMID 3619710 (1987, crossover n=10) and 39707791
  (2025, single-dose crossover) — no shared author; independence PLAUSIBLY_INDEPENDENT. Both
  are small; sample size is not assessed here.
- **Melatonin:** every finding is SECONDARY_ONLY (meta-analyses); the two MAs are DEPENDENT
  (documented shared RCT pool).
- **Donepezil / cognition:** SINGLE_STUDY (one primary RCT, PMID 22915447; the MA is secondary).
- **Droxidopa sample:** 26/26 records with metadata; 4 primary records (3 case-report-tagged,
  1 observational) in 4 clusters vs 16 stage-04 components; 5 shared-author pairs; 10 citation
  pairs (recorded, not dependencies). No finding-level replication can be assessed (no curated
  directions).
- **Trials credited to >1 compound:** 21 (17 pre-cutoff feature trials, 4 label trials). See
  `docs/VPS_EVALUATION.md` (duplicate evidence) and TD-038.

## What it cannot establish
- Patient-level overlap, shared datasets or funding (not persisted; affiliations are
  inconsistently present in PubMed).
- Homonymous authors can create false dependencies; name variants can hide true ones.
- Pre-2005 trials rarely have registry IDs, so shared-trial detection is incomplete.
- Coverage: only compounds with curated outcome claims (4) plus the Droxidopa paper sample.
  The 90-compound pool has no persisted PMIDs (TD-021); everything else is
  `INSUFFICIENT_METADATA` by construction.
- No incremental predictive value is claimed; integration would need a pre-specified,
  leakage-aware evaluation (see `docs/VPS_EVALUATION.md`).
