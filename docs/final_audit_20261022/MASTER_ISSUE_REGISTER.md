# Master issue register (final audit 2026-10-22)

**Sources:**
- every OPEN, PROPOSED or partially fixed entry in `TECHNICAL_DEBT.md`, `development_log/ERRORS_AND_BLOCKERS.md` and `development_log/DECISIONS.md`;
- the 2026-10-21 / 2026-10-22 audit reports;
- **new issues found in this audit** (N-xx).

**Status vocabulary:** as in the mission brief. Evidence paths are relative to this folder unless stated otherwise.

**Labels used in the tables:**

| Label | Meaning |
|---|---|
| IMPLEMENTED | RESOLVED — IMPLEMENTED AND VERIFIED |
| NO CHANGE | RESOLVED — NO CHANGE JUSTIFIED |
| CANDIDATE | RECOMMENDED — CANDIDATE VERIFIED, ADOPTION PENDING |
| UNRESOLVED | UNRESOLVED — INSUFFICIENT EVIDENCE |
| BLOCKED | BLOCKED — EXTERNAL DEPENDENCY |
| ACCEPTED | ACCEPTED LIMITATION — DOCUMENTED |

## A. Scientific correctness, labels, matching and temporal validity

| ID | Area | Issue | Root cause / evidence | Selected solution | Verification | Status |
|---|---|---|---|---|---|---|
| TD-042 | Molecular | Own-target pathway double counting | `molecular_agent.py:875`; MOLECULAR_CORRECTION_REPORT | Exclude own targets | 6 synthetic tests; independent re-derivation exact; 18 candidates verify | CANDIDATE |
| E-056 | Matching / cohort | Search truncated at 20 results | old `pageSize: 20` | Live isolated rebuild | COHORT_REBUILD_COMPARISON; 0 API failures | CANDIDATE |
| **N-01** | Matching | Token match accepted class / entity phrases ("dopamine agonists", "…Neurotrophic Factor") | Pass 2 had no class guard; 9/11 Dopamine links false | `CLASS_FOLLOWERS` rule (implements INTERVENTION_MATCHING §2) | 3 tests; approved 74 token matches unaffected | IMPLEMENTED |
| TD-038 / D-020 / TD-032 (feature side) / TD-023 / E-014 | Feature links | Links where the compound was not tested for PD count as clinical maturity | `TRIAL_ROLE_ADJUDICATION.csv` (197 links) | P1 applied symmetrically (32 excluded) | candidates verify; SD-4 | CANDIDATE |
| Review-28 | Feature links | 28 unresolved trial-role links | registry records | Adjudicated individually: 20 qualify, 8 do not | `records/review28_evidence.txt` | IMPLEMENTED (adjudication) / CANDIDATE (applying it) |
| TD-043 | Agent 10c | Automated role heuristics misfire | 8 of 30 unflagged non-therapeutic links were real therapeutic tests | Human adjudication supersedes them; automated roles never feed scoring | SD-4 | ACCEPTED |
| B-004 | Label | Lithium (DIETARY_SUPPLEMENT) | pre-specified study-type rule | Keep label 0; report the content-based sensitivity (0.757) | SD-5 | NO CHANGE |
| D-011 | Label | Galantamine | NCT07284290 fetched 2026-10-22 | Qualifies under P1 (moderate confidence) | SD-6 | NO CHANGE |
| **N-07** | Label policy | A WITHDRAWN 0-enrolment trial counts as "continued investigation" | NCT07288450 (Terazosin) withdrawn since the approved query | Policy question; no label changes today (Terazosin has 3 other trials) | `records/cohort_rebuild_diff_pass2.txt` | UNRESOLVED |
| TD-021 / B-002 / D-006 | Temporal | Literature not cutoff-bounded; sample composition predicts the label (0.722) | 04p dates | Cutoff-bounded primary-record count | dated candidates verify | CANDIDATE |
| TD-022 | Temporal | Current safety labels | 05h | Label at the cutoff (31/83), current otherwise | dated candidates | CANDIDATE (52 compounds: ACCEPTED) |
| TD-006 / B-001 / TD-033 | Temporal | Molecular not dated | OT 26.09 | OT 20.11 + ChEMBL 2020-06 | dated candidates | CANDIDATE (method drift: ACCEPTED) |
| **UR-1** | Temporal | 65/177 pre-cutoff trials updated after the cutoff; phase at the cutoff unproven | cache `lastUpdatePostDate` | Needs registry version history | – | UNRESOLVED |
| TD-035 / TD-027 / TD-004 | Design | Pool = previously-tried drugs; first-time repurposing out of scope | D-013 | Documented; Lidocaine leaves the P1 pool on this basis | – | ACCEPTED |
| TD-017 / TD-007 | Molecular | Same-target drugs tie; pathways unweighted | inherent | Documented | – | ACCEPTED |
| E-003 | Molecular | Fuzzy Open Targets name hits | stage 08 never accepts fuzzy hits (`normalize_drug_batch`) | – | code | NO CHANGE |

## B. Statistics and model choice

| ID | Issue | Evidence | Status |
|---|---|---|---|
| SD-7 | Primary model | Validity criteria fixed first; "all corrections" on the rebuilt cohort, 0.667 [0.506, 0.815] | CANDIDATE |
| Weights | Equal vs learned | Logistic 0.596 (lost 20/20); grid held-out 0.639 | NO CHANGE |
| TD-020 | Statistical power (14 positives) | CI widths about 0.3 | ACCEPTED |
| TD-036 | Single-split nested CV | eval already reports 20-repeat nested CV (`grid_search.repeated_nested_cv`); register stale | NO CHANGE |
| TD-025 | Ablation reference in-sample | figure labelled | ACCEPTED |
| TD-040 | Legacy rank convention asymmetric | 0.7754 (legacy) vs 0.7744 (midrank) | ACCEPTED |
| TD-041 | Proximity median vs neutral | 2 compounds; D-004 | ACCEPTED |
| Direct-only molecular | 0.759 (seen after results) | Not adopted (outcome-informed); pre-specify for future evaluation | ACCEPTED (recommendation) |
| E-015 | Bootstrap CIs not reproducible | eval re-run on approved inputs is **byte-identical** today | NO CHANGE (verified) |
| Calibration | Not a probability target | eval `calibration.applicable=false` | NO CHANGE |
| External validation | None exists | stated in all reports | ACCEPTED |

## C. Constants and formula checks

| ID | Issue | Result | Status |
|---|---|---|---|
| TD-011 | N_RANDOM 100 | ±0.007 AUROC across seeds; 1,000 is stable | IMPLEMENTED (code = 1000) |
| N-04 | `phases[0]` takes the lowest phase | 18 links, 6 compounds; −0.007 | IMPLEMENTED (`highest_phase` + test) |
| σ = 0 → z = 0 | Zero-variance rule | never triggered in the pool (minimum σ 0.073) | NO CHANGE |
| ×5 boxed warning | Undocumented weight | insensitive (k = 0…10: 0.767–0.779); no source invented | ACCEPTED |
| TD-014 | Boxed-warning key-existence test | all 30 flagged labels have non-empty text | NO CHANGE (inert today) |
| Negation | Safety terms ignore negation | 1.9% of hits | ACCEPTED |

## D. Reproducibility and provenance

| ID | Issue | Evidence | Status |
|---|---|---|---|
| B-003 | Approved scores not byte-reproducible | From-source 02 → 06 → eval with current code: 0.776 vs 0.775; differences come only from the proximity Monte Carlo draws (pre-fix RNG order) | ACCEPTED (quantified) |
| TD-046 (eval) | `eval` never fingerprinted `reproducibility.json` | Re-run on approved inputs is byte-identical and fingerprints all 8 inputs + script | CANDIDATE (owner command; touches the live manifest) |
| TD-046 (adopted code) | No code fingerprint for 12 adopted stages | Stage 00 reproduces byte-identically and can be attested; 02 / 06 cannot (Monte Carlo); 01 / 03 / 03c / 04 / 04b / 05 / 08 need live services | CANDIDATE (00) / ACCEPTED (02, 06) / BLOCKED (network stages) |
| `dimensions_imputed` | Approved CSV predates the column | Every candidate output carries it | CANDIDATE (comes with any adoption) |
| **N-02** | Verifier ignored `feature_role_exclusions.csv` | D-020 adoption would have failed verification | IMPLEMENTED (+3 tests) |
| **N-03** | Verifier gave 0.5 to compounds absent from the molecular CSV; 06 and D-004 use the median | rebuilt-cohort candidates failed verification | IMPLEMENTED (+1 test, shown to fail on the old code) |
| Bootstrap CSV | `bootstrap_ci_equal5d_vs_4d.csv` is produced outside the registry | eval checks it to 1e-12 | ACCEPTED (recommend a registry stage) |
| TD-019 | Stage 03 has no checkpoint | A full live re-run took about 25 min and succeeded twice | ACCEPTED |
| TD-026 | Graph guard checks counts, not edges | – | ACCEPTED |
| TD-005 | "No pipeline outputs" | obsolete | NO CHANGE (stale entry) |
| TD-048 | Superseded metrics in docs | README TD-020 historical note; corrected `VPS_EVALUATION.md` (2026-10-21) | ACCEPTED (owner wording) |

## E. Engineering, security, UI

| ID | Issue | Status |
|---|---|---|
| **N-05** | 8 stages (01, 00, 02, 03, 03c, 04, 05, 04b) and 06 / eval had no timeout | IMPLEMENTED (+ test) |
| **N-06** / E-055 residue | 10d / 10e / 10h / 10a-curated exited 0 on FAILED | IMPLEMENTED (+4 tests; convention: exit 1 only on FAILED) |
| E-055 (A-1 … A-7) | Agent contract defects | NO CHANGE (fixed 2026-10-20; heading stale) |
| TD-012 | Scripts ran on import (03c filter wrote data) | IMPLEMENTED (filter, test_openfda, check_groundtruth guarded; byte-identical output; `debug_step2` kept, read-only and tested) |
| TD-013 | Missing `os.makedirs("data")` | IMPLEMENTED (00, 01, check_studytype) |
| TD-037 | 06 non-atomic | NO CHANGE (atomic per file + runner staging) |
| TD-009 | Script 04 silent failures | NO CHANGE (fixed in code; data shows 0 failures) |
| TD-045 | Test file-handle leaks | NO CHANGE (`-W default` run: 0 warnings) |
| TD-047 / TD-016 / TD-030 / TD-039 / TD-015 | Minor / accepted design | ACCEPTED |
| SEC-1 / SEC-2 | certifi / pillow advisories | CANDIDATE (upgrade after the presentation) |
| SEC-3 | Unbounded server threads | ACCEPTED |
| TD-044 / Production | Authentication, TLS, multi-user, audit log | BLOCKED |
| UI | Full functional, accessibility and security browser verification on the changed code | see TEST_EVIDENCE.md |

## Counts (mechanical, one primary status per register line)
Computed by parsing the tables above: 57 lines.

| Primary status | Lines |
|---|---|
| RESOLVED — IMPLEMENTED AND VERIFIED | 10 |
| RESOLVED — NO CHANGE JUSTIFIED | 15 (incl. the UI line, set by the browser verification in TEST_EVIDENCE.md) |
| RECOMMENDED — CANDIDATE VERIFIED, ADOPTION PENDING | 11 |
| UNRESOLVED — INSUFFICIENT EVIDENCE | 2 |
| BLOCKED — EXTERNAL DEPENDENCY | 1 (production controls) |
| ACCEPTED LIMITATION — DOCUMENTED | 18 |
| **Total** | **57** |

**Lines with a split status** (primary first):
- **Review-28:** adjudication implemented; applying it is pending adoption.
- **TD-022:** candidate; 52 compounds accepted as a limitation.
- **TD-006 / TD-033:** candidate; method drift accepted.
- **TD-046 (adopted code):** candidate for stage 00; accepted for 02 / 06; blocked for the network stages.
