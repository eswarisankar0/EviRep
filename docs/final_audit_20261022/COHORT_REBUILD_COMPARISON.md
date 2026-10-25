# E-056: stage-03 cohort rebuild (final audit 2026-10-22)

**Status: RECOMMENDED — CANDIDATE VERIFIED, ADOPTION PENDING.**
- The rebuild ran on the **live** ClinicalTrials.gov API (v2) on 2026-10-22, in an isolated root (`~/EviRep_rebuild_e056_20261022T1504Z`).
- Approved files are unchanged.
- Evidence: `records/cohort_rebuild_diff.txt` (pass 1), `records/cohort_rebuild_diff_pass2.txt` (pass 2), and each run's `data/_runs/*/log.txt` in the rebuild root.

## What was rebuilt
- **Stages:** 03 (search, gates and matching, with pagination of 100/page and at most 50 pages) and 03c (study type), both through `scripts/run_stage.py`.
- **For new pool members:** 04, 05, 08, 04p and 05h through their checkpoints, so only new compounds were queried.
- **Coverage:** 1,483 compounds searched.
- **Aliases:** resolved from the cache (1,461 resolved).
- **Failures:** 0 API failures in either pass.

## Pass 1: pagination fix only
The approved cohort was reproduced exactly, with these additions:
- **Dopamine** entered the pool with 7 pre-cutoff and 4 post-cutoff links.
- **Ioflupane** gained NCT04193527 (Phase 3, 2019).

Inspection showed that **9 of Dopamine's 11 links were false matches**, from whole-token matching inside class or entity phrases:
- "Continuous Release Dopamine Agonists"
- "Dopamine Agent"
- "Bromocriptine and other dopamine agonists"
- "Cerebral Dopamine Neurotrophic Factor" (×2)
- "dopamine progenitor cell" (×2)
- "midbrain dopamine neurons"

This is a confirmed defect (S-03 / E-014 class). `docs/INTERVENTION_MATCHING.md` §2 already excludes class relationships.

**Fix:** `scripts/intervention_matcher.py` `CLASS_FOLLOWERS`. A whole-token hit followed by agonist(s), antagonist(s), agent(s), neurotrophic, neuron(s), progenitor(s), cell(s), receptor(s), transporter(s), precursor(s), derived or producing does not name the compound. One genuine occurrence still matches. Tests: `tests/test_intervention_matcher.py::TestClassPhrasesAreNotTheCompound` (3 tests, using the registry's own strings).

**Check on the approved cohort:** all 47 pre-cutoff and 27 post-cutoff token matches name the compound itself (`records/token_match_scan.txt`), so the fix does not touch it.

## Pass 2: pagination + class-phrase fix (the candidate cohort)

| | Approved | Rebuilt |
|---|---|---|
| Pre-cutoff links | 195 | 197 |
| Post-cutoff links | 57 | 58 |
| Pool | 90 | **91** (+Dopamine) |
| Positives (frozen D-010 window, posted ≤ 2026-10-05) | 14 | **15** |
| Positives (unfrozen) | 14 | 15 |
| Compounds whose label or max phase changed (other than Dopamine) | – | **0** |

**Added links:**

| Link | Registry evidence (2026-10-22) | Role |
|---|---|---|
| NCT04332276 Dopamine (pre, 2020-04-02) | intracerebroventricular A-dopamine, EXPERIMENTAL, vs optimised oral treatment; purpose TREATMENT; PD; phases PHASE1/PHASE2 | therapeutic, qualifies |
| NCT07214285 Dopamine (post, 2025-10-09) | A-dopamine long-term safety, EXPERIMENTAL; TREATMENT; PD | positive label, qualifies |
| NCT04193527 Ioflupane I 123 (pre, 2019-12-10) | DaTSCAN diagnostic efficacy, EXPERIMENTAL; PHASE3 | qualifies (diagnostic agent under test); max phase unchanged |

**Reproducibility finding:** apart from the pagination additions, every approved pool member, label and maximum phase reproduces from the live registry 17 days after the approved query. Field by field:
- **All 195 shared pre-cutoff links** are identical in every stored field.
- **Of the 57 shared post-cutoff links**, 2 changed `status` and 1 changed `enrollment`. NCT07288450 (Terazosin) is now WITHDRAWN with 0 enrolled; NCT05824728 (Levetiracetam) went from RECRUITING to ACTIVE_NOT_RECRUITING.
- **No positive depends only on a withdrawn trial:** Terazosin has three other qualifying post-cutoff trials. D-010 counts registered trials regardless of status. Whether a withdrawn, never-enrolled trial should count as "continued investigation" is recorded as an open policy question (MASTER_ISSUE_REGISTER **N-07**); today it changes no label.

## Downstream effect
Same equal-weight rules; `experiments/model_comparison_rebuilt_cohort.json`.

| Model | Approved cohort (90/14) | Rebuilt cohort (91/15) |
|---|---|---|
| Approved rules, 5D | 0.775 [0.656, 0.881] | 0.787 [0.672, 0.884] |
| Approved rules, 4D | 0.700 | 0.719 |
| TD-042 | 0.699 [0.557, 0.830] | 0.716 [0.575, 0.832] |
| Fully dated | 0.689 [0.548, 0.819] | 0.709 [0.557, 0.833] |
| All corrections | 0.646 [0.476, 0.808] (76/13) | 0.667 [0.506, 0.815] (77/14) |

- **Dopamine** ranks 1 of 77 in the all-corrections candidate (positive). Proximity z = −6.37: its targets are dopamine receptors.
- **On the 90 shared compounds** the rebuild changes no rank-relevant input under approved rules (paired difference 0.0 [−0.009, 0.009]).

## Remaining limitations
- **Dopamine's literature row** (30 papers, 25 components, 6 author edges, 0 citation edges) is numerically identical to Donepezil's. It was checked: the PubMed hit counts differ (22,884 vs 203) and the citation lookups completed. This is a coincidence of counts and is recorded, not hidden.
- **Dopamine is absent from the Open Targets 20.11 historical molecular data,** so in "dated" candidates it keeps its current molecular score (1 of 77 compounds not dated on that dimension).
- **The label window end** is the query date (D-010). Today's query adds no new positive inside the frozen window except Dopamine.

## Adoption (owner)
1. Run stages 03 and 03c from the corrected code on the primary root: `./venv/bin/python scripts/run_stage.py 03` then `03c`. This rewrites protected files.
2. Then run 04/05/08/04p/05h, 06 and eval, or adopt the verified candidate files.
3. Compare: `scripts/compare_result_sets.py --candidate <new vps_scores_v2.csv> ...`.
4. **Rollback:** restore from `~/EviRep_recovery_finalmission_20261022T1504Z/data_snapshot.tgz`.
