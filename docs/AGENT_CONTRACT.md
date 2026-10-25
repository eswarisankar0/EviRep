# Specialised agents 10a–10h: shared contract and acceptance status

Contract module: `scripts/agent_contract.py`, standard library only. Every agent output carries
the same **envelope**. The dashboard (`ui/server.py::_agent_run`) and agent 10h read status,
time, staleness and diagnostics only from this envelope. It never invents a status for an output
that lacks one.

| Field | Meaning |
|---|---|
| `agent_id`, `agent`, `agent_version`, `schema_version` | identity |
| `run_status` | `SUCCESS` · `PARTIAL` (must carry a warn/error diagnostic) · `NO_EVIDENCE` · `FAILED` (must carry an error) |
| `generated_utc` | when the output was written |
| `inputs` | `{relative path: md5}` of every persisted input. **STALE** is derived at read time when one changes; it is never written by an agent |
| `coverage` | agent-specific counts |
| `limitations` | text |
| `diagnostics` | `[{level, code, message}]`; secrets and home paths are redacted, and an envelope carrying a secret-looking message is rejected |

Per-item states always keep these four apart: **retrieved / measured**, **source answered with
no record**, **retrieval failed (recorded)**, and **never retrieved**. A measured zero is a
finding, not a gap. No agent outside VPS produces a score, and the VPS neutral-rank policy (D-004)
is unchanged.

## Agents (2026-10-15)

| Id | Module → output | Sources | Tests | VPS role | Acceptance status |
|---|---|---|---|---|---|
| 10a | `literature_credibility_agent.py` → `data/literature_credibility_<compound>.json` | cached PubMed efetch XML | `test_literature_credibility_agent.py` (23) | diagnostic | **Met within scope**. Study design from PublicationType/MeSH, provenance and missing PMIDs recorded, efficacy never assessed. Coverage: the Droxidopa paper sample plus curated PMIDs for 4 compounds (`--curated`, offline). Other compounds have no persisted PMIDs (TD-021). |
| 10b | `molecular_agent.py` / stage 08 → `molecular_pathway.csv` + evidence JSONL; run record `molecular_run_record.py` → `molecular_agent_run.json` | Open Targets (ChEMBL, Reactome) | `test_molecular_agent.py` and others | dimension 5 | **Met**. Drug → target → gene → pathway → PD chain with Ensembl/ChEMBL/Reactome IDs; all 90 evidence records re-validated offline; the CSV matches the JSONL. |
| 10c | `clinical_evidence_agent.py` → `data/clinical_evidence.json` (stage 03 does discovery and matching) | ClinicalTrials.gov v2 (177 trials, batched, cached) | `test_clinical_evidence_agent.py` (8) | stage-03 max phase in VPS; 10c layer diagnostic | **Met**. Phase, status and why-stopped; results posted (67/177) with primary analyses copied verbatim and post-2021 results flagged; the drug's role in every link (automated, hand adjudication takes precedence); matching-audit outcomes. States: results posted / none posted / not in registry / retrieval failed / not retrieved. |
| 10d | `conflict_context_agent.py` → `data/conflict_context.json` | persisted claims | `test_conflict_context_agent.py` | diagnostic | **Met within scope**. INSUFFICIENT when there are fewer than 2 directional sources; conflicts are never invented. |
| 10e | `reproducibility_agent.py` → `data/reproducibility.json` | cached PubMed XML, curated claims | `test_reproducibility_agent.py` | diagnostic | **Met within scope**. Coverage: case-study findings plus the Droxidopa sample. |
| 10f | `safety_evidence_agent.py` → `data/safety_evidence.json` (stage 05 = label score) | openFDA label (stage-05 cache) and FAERS drug/event (cached, 4 count queries × 90) | `test_safety_evidence_agent.py` (12) | stage-05 label score in VPS; 10f layer diagnostic | **Met**. Label provenance (DailyMed set id, boxed-warning text) and FAERS totals (all-time and received by 2020, serious, deaths, top reactions). States: retrieved / no record / failed / not retrieved. Not incidence, not causality. |
| 10g | `evidence_independence_agent.py` → `data/evidence_independence.json` (stage 04 = within-literature dependence) | persisted outputs, 10c, cached XML | `test_evidence_independence_agent.py` (3) | stage-04 count in VPS; 10g layer diagnostic | **Met within scope**. Checks D1 shared trial across candidates (17 trials shared by 31 candidates), D2 the same study as both trial and paper, D3 duplicated or pooled claims (Melatonin: 6 claims, 1 source cluster), and D4 molecular datatype reuse (none). D2/D3 are NOT_ASSESSABLE without PMIDs. |
| 10h | `completeness_gap_agent.py` → `data/completeness_gaps.json` | all of the above | `test_completeness_gap_agent.py` (16) | diagnostic | **Met**. 12 domains; reads the 10c/10f/10g outputs and the stage-04/05 failure files; reports each agent output's staleness; asserts agreement with stage-06 missing flags. |

**Rerun order (offline after the first fetch):**
```bash
./venv/bin/python scripts/clinical_evidence_agent.py      # --fetch to refresh the registry cache
./venv/bin/python scripts/safety_evidence_agent.py        # --fetch for uncached FAERS
./venv/bin/python scripts/literature_credibility_agent.py --curated
./venv/bin/python scripts/conflict_context_agent.py
./venv/bin/python scripts/reproducibility_agent.py
./venv/bin/python scripts/molecular_run_record.py
./venv/bin/python scripts/evidence_independence_agent.py  # reads 10c
./venv/bin/python scripts/completeness_gap_agent.py       # reads everything; run last
```

## Known limits (not hidden)
- **Literature-dependent checks have narrow coverage:** 10a, 10d, 10e, and D2/D3 in 10g, depend on
  PMIDs, which stage 04 does not persist (TD-021).
- **Automated roles are not adjudicated:** 10c's automated role verdicts for the 160 links outside
  D-020 are not hand-checked, and none is applied to scoring.
- **FAERS name matching is imperfect:** it uses the generic name or the reported product name;
  counts are all-time, plus a cutoff-bounded count.
- **Stage 02 skips are unrecorded:** it does not record why a compound was skipped.

## Evidence lineage and VPS contribution (verified against the code, 2026-10-15)
| Agent | Output used by VPS? | Field | Temporal | Coverage (of 90) | Overlap / double-counting | Score justified? |
|---|---|---|---|---|---|---|
| 10a | no | design tiers | per paper (pre/post flagged) | 5 compounds | duplicates 10e's paper set | no: coverage 5/90 |
| 10b | **yes** (dimension 5) | `molecular_plausibility_score` (ranked) | current Open Targets (not cutoff-bounded) | 74 measured, 16 no target (neutral) | literature and clinical datatypes excluded (10g D4: none reused) | yes, as now (equal weight) |
| 10c | **stage-03 feature only** (`max_phase_rank`) | posted results, roles, status (diagnostic) | results mostly posted after the cutoff | 90 | roles would change the clinical feature: D-020, owner | not without the D-020 decision; results are post-cutoff (leakage) |
| 10d | no | conflict classes | per claim | 18 assessed / 72 insufficient | — | no: categorical, sparse |
| 10e | no | replication status | per finding | 3 compounds | — | no: coverage |
| 10f | **stage-05 label score only** (`serious_term_count`, boxed warning) | FAERS counts (diagnostic) | all-time; a by-2020 count exists | 90 | FAERS correlates with market size and age, not risk | not yet: needs a pre-specified, leakage-aware design (counts are not incidence) |
| 10g | **stage-04 count only** (`effective_independent_count`) | cross-source dependence (diagnostic) | — | D1/D4: 90; D2/D3: 4 | D1 is the TD-038 shared-trial issue | not as a score; de-duplication would be a D-020 policy |
| 10h | no | availability states | — | 90 | reads everything | no: describes availability, not evidence |

**Decision (D-024):** VPS stays the equal-weight 5-dimension score of stages 02, 03, 04, 05 and 08.
No diagnostic agent output is added, because none meets all three conditions:
- coverage of the 90-compound cohort;
- pre-cutoff availability;
- non-duplication of an existing dimension.

Adding one and judging it on the same 14 positives would be test-set tuning. The test
`tests/test_vps_correctness.py::TestIsolation` fails if stage 06 reads any diagnostic agent output.
