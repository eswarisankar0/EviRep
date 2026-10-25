# Scientific decision log (final audit 2026-10-22)

Each decision follows the same template:
- **Q:** the question;
- **Evidence:** primary sources (identifiers and retrieval dates);
- **Options:** the alternatives considered;
- **Bias check:** the risk of choosing by outcome;
- **Decision** and status;
- **Impact.**

All registry evidence comes from ClinicalTrials.gov API v2, either cached (`data/cache/ctgov_precutoff_trials.json`, retrieved 2026-10-15) or fetched today (2026-10-22; `records/*registry*.txt`).

---

## SD-1 · TD-042 molecular double counting
- **Q:** Should pathway credit count a drug's own target as the shared PD gene?
- **Evidence:**
  - code (`molecular_agent.py:786, 875-876, 959-1003`);
  - synthetic tests (`tests/test_td042_pathway_rule.py`);
  - an independent stage-08 re-run today reproducing `td042_v1` exactly.
- **Options:** published rule; own-target exclusion (TD-042); direct only.
- **Bias check:** the published rule scores higher (0.775 vs 0.699). That is not a criterion. Direct-only scores 0.759 but was evaluated only after seeing the results, so it is **not** selected (outcome-informed).
- **Decision:** own-target exclusion is the defensible definition of *indirect* pathway evidence. **RECOMMENDED — CANDIDATE VERIFIED, ADOPTION PENDING.**
- **Impact:** −0.076 [−0.158, −0.014]; molecular adds nothing over 4D.

## SD-2 · E-056 cohort completeness (pagination)
- **Q:** Does complete retrieval change the cohort?
- **Evidence:** live rebuild of stages 03/03c (2026-10-22), 1,483 compounds, 0 API failures.
- **Decision:** adopt complete retrieval. **RECOMMENDED — CANDIDATE VERIFIED, ADOPTION PENDING.**
- **Impact:** the pool gains Dopamine (positive); Ioflupane gains a Phase-3 trial (no maximum-phase change). Everything else reproduces.

## SD-3 · Class-phrase false matches (new; S-03/E-014 class)
- **Q:** Should "dopamine agonists", "Cerebral Dopamine Neurotrophic Factor" or "dopamine neurons" count as Dopamine?
- **Evidence:** 9 of 11 Dopamine links in rebuild pass 1 (strings in `COHORT_REBUILD_COMPARISON.md`). `docs/INTERVENTION_MATCHING.md` §2 already says class relationships are not evidence.
- **Decision:** reject a token match followed by a class/entity word. This implements an existing rule, not a new one. **RESOLVED — IMPLEMENTED AND VERIFIED** (code + 3 tests). It has no effect on the approved cohort (all 74 token matches checked).

## SD-4 · P1 symmetry for feature links (D-020) and the 28 + 30 links
- **Q:** Should a pre-cutoff link count as clinical evidence when the compound was not tested for PD?
- **Evidence:**
  - D-020 (35 links, owner-proposed);
  - this audit's per-link registry adjudication of 50 more links (28 flagged + 30 unflagged non-therapeutic automated roles, minus 8 already in D-020);
  - 2 new rebuild links.
  - Table: `TRIAL_ROLE_ADJUDICATION.csv` (197 rows).
- **Rule:** the approved P1 criterion for labels (D-011), applied symmetrically. Procedural, comparator-only, auxiliary (interaction probe, premedication, QT positive control, immunosuppression) and background roles do not qualify. Fixed combinations and the withdrawn trial are retained (D-020 recs 3–4). Ambiguous links are retained.
- **Bias check:**
  - The rule is the *label* rule, fixed 2026-10-14 before these analyses.
  - Applying it **lowers** AUROC (0.775 → 0.746 approved cohort), so it is not performance-seeking.
  - The rule was not tuned: it is one prespecified criterion.
- **Results:**
  - 32 links do not qualify, 1 is ambiguous (Tadalafil, retained).
  - 14 compounds leave the pool: 13 negatives that were only tools in PD trials, plus Lidocaine.
  - Lidocaine's only pre-cutoff link is local anaesthesia in DBS surgery, so it is a first-time repurposing candidate (TD-035 scope). Its positive label is valid but it has no qualifying prior trial.
  - Of the 30 unflagged links with a non-therapeutic automated role, 8 are genuine therapeutic tests the heuristic misclassified (topiramate ×2, duloxetine, oxycodone, melatonin, NAC, droxidopa ×2; TD-043 confirmed).
  - 2 are the withdrawn-trial links retained under D-020, 1 is ambiguous (Tadalafil), and 19 do not qualify (6 of these were already "no" in D-020).
  - Exclusions reconcile: 11 (D-020) + 13 (new, unflagged) + 8 (from the 28 flagged) = **32**.
- **Decision:** **RECOMMENDED — CANDIDATE VERIFIED, ADOPTION PENDING.** The adjudications are evidence-backed; adopting them changes approved inputs.
- **Residual:** 110 links are accepted on automated + structural agreement only (not individually reviewed).

## SD-5 · B-004 Lithium
- **Q:** Do three lithium-aspartate trials typed DIETARY_SUPPLEMENT make Lithium positive?
- **Evidence:** NCT06099886, NCT06339034, NCT06592014 (`ground_truth_postcutoff.csv`); stage 03c rule `keep_trial` (INTERVENTIONAL + DRUG/BIOLOGICAL); D-010 frozen endpoint lists "passes the study-type filter".
- **Options:** keep the pre-specified registry-type rule (label 0); content-based reading (label 1, AUROC 0.757).
- **Bias check:** changing a label rule after seeing results is the larger risk. The same filter removed Mannitol on the feature side, so the rule is applied symmetrically.
- **Decision:** the confirmatory label stays 0 under the pre-specified endpoint. **RESOLVED — NO CHANGE JUSTIFIED.** The content-based reading is reported as a sensitivity analysis.

## SD-6 · D-011 Galantamine
- **Q:** Does NCT07284290 qualify under P1?
- **Evidence (fetched 2026-10-22):**
  - conditions DLB, **Parkinson Disease Dementia**, healthy controls;
  - EXPERIMENTAL 8-week pre-post cohort, with galantamine as the only drug;
  - primary outcomes are cognitive-fluctuation scales and MDS-UPDRS;
  - primary purpose BASIC_SCIENCE; non-randomised.
- **Decision:** the drug is the active agent tested for a PD-dementia symptom, and P1 excludes only procedural, comparator and actuator roles. **The label stays 1 (moderate confidence). RESOLVED — NO CHANGE JUSTIFIED.**
- **Sensitivity:** label → 0 gives AUROC 0.781 (D-011).

## SD-7 · Primary model
- **Q:** Which score is the primary scientific result?
- **Criteria** (fixed before comparison; `TEMPORAL_LEAKAGE_AUDIT.md` §4): dated inputs, no double counting, P1-symmetric links, complete retrieval, equal weights.
- **Decision:** "All corrections" on the rebuilt cohort, **0.667 [0.506, 0.815]**, is recommended as primary. The approved 0.775 becomes the historical / undated result. **RECOMMENDED — ADOPTION PENDING** (it changes approved artefacts).

## SD-8 · Constants
- **Boxed-warning ×5:** insensitive (k = 0…10: 0.767–0.779). **ACCEPTED LIMITATION — DOCUMENTED.** No literature basis was found in the repository; no external citation is invented.
- **`phases[0]`:** contradicts the "maximum phase" definition. Fixed in the code (`highest_phase`). **RESOLVED — IMPLEMENTED AND VERIFIED** (code + test). The approved data is unchanged until a rebuild (effect −0.007).
- **N_RANDOM 100:** Monte Carlo spread ±0.007 AUROC. Raised to 1,000 in the code. **RESOLVED — IMPLEMENTED AND VERIFIED** (stable 0.775–0.776).
- **σ = 0 → z = 0:** never triggered (minimum σ = 0.073 in the pool). **RESOLVED — NO CHANGE JUSTIFIED.**
- **Safety term negation:** 12 of 635 hits (1.9%) preceded by a negation word. **ACCEPTED LIMITATION.**
- **Missing-data policy:** D-004 neutral 0.5 for unmeasured safety and molecular; median for proximity and for compounds absent from the molecular file. **Verified consistent** between stage 06 and the verifier after today's fix.

## SD-9 · Weighting
Equal weights retained: learned weights are unstable and worse on held-out data (`docs/final_release_20261022/WEIGHTING_DECISION.md`). **RESOLVED — NO CHANGE JUSTIFIED.**

## Research access note
- **Live services used today:** ClinicalTrials.gov API v2 (about 1,500 searches ×2 passes, plus study-type checks and 4 single records); PubMed / Semantic Scholar / openFDA / Open Targets / DailyMed for the new compound only (checkpointed stages); OSV for dependency advisories.
- **Not consulted:** no peer-reviewed literature was used to justify the ×5 multiplier or the 0.6/0.4 molecular weights, and **none is claimed**.
