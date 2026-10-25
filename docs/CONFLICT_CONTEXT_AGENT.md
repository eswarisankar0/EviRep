# Conflict & Context Agent (10d)

`scripts/conflict_context_agent.py` · tests `tests/test_conflict_context_agent.py` (21, offline)
· output `data/conflict_context.json` · status: **implemented, tested, shown in the dashboard;
diagnostic only — not read by `06_vps_fusion.py`** (decision D-015).

## Question
Where does the persisted evidence for a compound disagree, and is the disagreement a genuine
contradiction or a difference in context? Disagreements are classified and cited, **never
converted into a score or penalty**.

## Inputs (all persisted; no network)
| Input | Claims produced | Provenance kept |
|---|---|---|
| `data/conflict_claims_curated.json` | 20 claims for Donepezil, Melatonin, Domperidone, Propranolol, transcribed from `docs/CASE_STUDIES.md` | PMID, year, section; values only as written there (a test checks every PMID appears in the doc) |
| `data/cache/openfda_labels/*.json` (stage 05 v2) | fixed regex rules over named label sections: PD aggravation warning, contraindication, drug-induced parkinsonism/EPS, PD indication, diagnostic indication, PD-drug interaction | set_id, effective date, section, verbatim excerpt centred on the match, warning vs. listing strength |
| `data/molecular_pathway_evidence.jsonl` (10b) | one mechanism claim per compound with targets | ChEMBL id, top target, action types; caveat that associations are undirected |
| `data/clinical_maturity_precutoff_clean.csv` | context only: registered trials are NEUTRAL; stopped trials UNCLEAR (reason not retrieved) | NCT id, status, phase |

Directions are about each claim's own endpoint: `SUPPORTS`, `NULL_RESULT`, `OPPOSES`,
`NEUTRAL`, `UNCLEAR`. Domains: efficacy, safety, mechanism, disease_risk, clinical_activity,
diagnostic.

## Classification of a pair with different directions (different sources only)
| Class | Rule |
|---|---|
| `DIRECT_CONTRADICTION` | same domain and outcome, and endpoint measure, population, design, dose and intervention scope all recorded and equal |
| `STATISTICAL_DISAGREEMENT` | same effect measure, estimates of the same sign; only significance differs |
| `CONTEXT_DIFFERENCE` | same outcome domain; at least one context axis differs (listed) |
| `UNCERTAIN_COMPARABILITY` | same outcome domain; context not recorded well enough to judge |
| `CROSS_DOMAIN_TENSION` | SUPPORTS in one domain vs OPPOSES in another (benefit–risk or mechanism–safety) |
| `NON_COMPARABLE` | different outcomes in the same domain — listed, not a conflict |

Flags: `non_independent_sources` (shared data, e.g. overlapping meta-analyses),
`quality_asymmetry` (evidence-level gap ≥ 2), `uses_post_cutoff_evidence` (the pair must not
feed a retrospective score). Compound status = the highest-priority class found;
`INSUFFICIENT` = fewer than two directional sources (**not** agreement);
`NO_DISAGREEMENT_DETECTED` = ≥ 2 directional sources that agree.
`NO_COMPARABLE_PAIR` (added 2026-10-19) = ≥ 2 directional sources, but no pair addresses comparable
ground (e.g. a label safety warning and a null mechanism association); neither agreement nor conflict.
Before 2026-10-19 these compounds were reported as NO_DISAGREEMENT_DETECTED (8 of the 9 below).

## Real run (2026-10-15, 91 compounds = 90 pool + Propranolol)
Statuses: 1 STATISTICAL_DISAGREEMENT, 1 CONTEXT_DIFFERENCE, 8 CROSS_DOMAIN_TENSION,
9 NO_DISAGREEMENT_DETECTED, 72 INSUFFICIENT, 0 DIRECT_CONTRADICTION. Examples:
- **Melatonin:** Yousef 2026 (PMID 40588412) ESS MD −1.07, p=0.009 vs Badran 2025
  (PMID 40387966) ESS MD −1.04, p=0.25 → significance-only disagreement between
  non-independent meta-analyses — not a contradiction.
- **Donepezil:** Pagano 2015 (class-level MA, MMSE) vs Dubois 2012 (RCT, PDD, ADAS-cog) →
  context difference on endpoint measure, population, design and intervention scope.
- **Domperidone / Propranolol:** symptomatic benefit vs cardiac risk (PMID 27062307) /
  incident-PD association (PMIDs 35718329, 40200766; authors cite protopathic bias) →
  cross-domain tension.
- **Oxybutynin:** label warns of aggravation in PD patients vs molecular support → tension.

## Limitations
- Coverage is thin: curated claims exist for 4 compounds; 9 labels mention Parkinson's or
  EPS terms; literature PMIDs for the pool are not persisted (TD-021). 72/91 compounds are
  INSUFFICIENT — that is missing evidence, not agreement.
- Label claims are current labels (not cutoff-bounded) and `limit=1` picks one product label.
- Adverse-reaction listings of EPS terms are weak evidence (frequency/causality often not
  established); they are marked as such.
- No incremental predictive value is claimed; integration into scoring would need a
  pre-specified evaluation (as for 10a).
