# Completeness & Gap Agent (10h)

`scripts/completeness_gap_agent.py` · tests `tests/test_completeness_gap_agent.py` (12, offline,
socket-guarded) · output `data/completeness_gaps.json` (schema `1.0`, agent `10h-0.1`) · status:
**implemented, tested, shown in the dashboard; diagnostic only — not read by
`06_vps_fusion.py`** (decision D-021).

## Question
For each candidate and each kind of evidence: is it there, and if not, **why not**? A single NaN
or a neutral 0.5 rank hides the difference between a real measurement of zero, a source that
holds no record, evidence that was never retrieved, and a retrieval that failed. Absence of
evidence must not be read as evidence of absence.

## How it differs from existing components
- Stage 06 stores `dimensions_missing` / `n_dimensions_measured` (D-004) for the five VPS
  dimensions only and does not say why. 10h re-derives those states from the stage outputs and
  **fails if it disagrees** with stage 06.
- 10a/10d/10e assess evidence that exists; 10h records where they could not run and why.
- 10h produces no score and never fills a gap.

## States
| State | Meaning |
|---|---|
| `MEASURED` | value computed from retrieved evidence |
| `MEASURED_ZERO` | a value of zero / no signal — a measurement, not a gap |
| `PARTIAL` | measured from incomplete or truncated input |
| `ABSENT_AT_SOURCE` | source queried successfully, no record (e.g. no US FDA label, no ChEMBL target) |
| `NOT_COMPUTED` | a local stage produced no value; the reason is given, and where the stage does not persist failures this is said explicitly |
| `NOT_RETRIEVED` | this evidence type was never retrieved for the compound |
| `RETRIEVAL_FAILED` | a recorded failure (e.g. stage-04 citation lookups) |
| `INSUFFICIENT` | assessed, too little evidence to conclude (10d: < 2 directional sources) |
| `ASSESSED` | a diagnostic agent produced a finding |

## Domains (11)
The five VPS dimensions (proximity, clinical, literature, safety, molecular), and also trial
outcomes, trial roles (D-020 adjudication), post-marketing adverse events (FAERS),
study-design credibility (10a), conflicts (10d) and replication (10e). Each record lists the
gaps, what would close each one, and the research questions it leaves open. A flat
`synthesis_inputs` list is provided for Stage 11.

## Real run (2026-10-15, 90 compounds)
- **Proximity:** 88 measured; 2 not computed (Deferiprone, Trimethobenzamide). These are
  median-imputed in stage 06 **without** a `dimensions_missing` flag, and 10h reports that.
- **Clinical:** 81 measured; 9 measured zero (no phase recorded on any trial).
- **Literature:** 58 measured; 31 partial (sample capped at the first 30 PubMed records,
  TD-021); 1 measured zero (Glycerol Phenylbutyrate).
- **Safety:** 68 measured; 15 measured zero (label found, no boxed warning or serious term);
  7 absent at source (no US label). All 7 are negatives, so this missingness is
  label-associated.
- **Molecular:** 64 measured; 10 measured zero (targets with no permitted PD link); 16 absent
  at source (no ChEMBL target; 2 positives).
- **Trial outcomes:** not retrieved for 87 compounds; curated outcome claims exist for 3.
  FAERS is not retrieved for any compound.
- **Stage-06 agreement:** true for all 90.

Each count was cross-checked against the raw CSVs on 2026-10-15: 31/31, 7/7, 15/15, 16/16 and
10/10.

## What it cannot establish
- Stages 02, 04 and 05 do not persist failed requests. A missing row is `NOT_COMPUTED`, with
  that caveat, and is never a negative.
- It covers only the 90-compound evaluable pool.
- States describe availability, not quality or truth. Remedies are suggestions; none has
  been run.
