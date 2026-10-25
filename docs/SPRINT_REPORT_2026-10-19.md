# Sprint report, 2026-10-19 (second session): agent verification, VPS validation, live UI

Everything below was run in this session unless it is marked *prior*. Experiment outputs are in
`data/_runs/validation_20261019/`. No published artefact, label, input or policy was changed.

## A. Execution summary
**Done**
- Re-established the baseline. Protected hashes are unchanged and the git index is unchanged (hash of `git diff --cached` recorded before and after). 498 → 509 tests pass, and VPS reproduces exactly.
- Re-verified all eight agents:
  - determinism (two runs on identical inputs);
  - reproduction of the persisted outputs;
  - the coverage actually achieved.
- TD-042 lineage analysis and variant, TD-040/TD-041 variants, a leakage review, bootstrap CIs, paired differences, and repeated nested CV for weights on the simplex: `scripts/vps_validation_experiments.py`.
- Review table for all 195 clinical trial–compound links: `scripts/clinical_role_review.py`.
- Run tracker:
  - a `MISSING` state;
  - `--skip-fresh`.
- UI:
  - content-based stage badges replace the timestamp heuristic;
  - a MISSING banner;
  - explicit live-monitoring wording.
- 20 browser acceptance scenarios in headless Chrome on fixture copies: 12 + 8, all passing.

**Not done, and why**
- Policy decisions were not applied (TD-042, TD-040, TD-041, D-020/TD-038/TD-043), and the VPS was not republished. They need owner approval.
- No live API call was made. Literature, safety and molecular data cannot be cutoff-bounded offline (see C4).
- The eight-agent weighted composite was **not built**. It is not defensible yet (C5).

## B. Eight-agent verification matrix
"Reproduces persisted" means a fresh offline run in a disposable copy equals the persisted output, ignoring timestamps. For 10g and 10h it differs only in the input hashes of upstream JSONs regenerated in the copy. "Deterministic" means two runs gave identical output. Failure-path tests are those added in the earlier sprint (E-027 to E-030) plus the existing suites.

| Agent | Coverage actually assessed | Sources (provenance) | Repro. / determ. | Failure paths tested | Status | Limitations |
|---|---|---|---|---|---|---|
| 10a Literature credibility | 5 of 90 compounds; 40 papers (Droxidopa 26; 4 curated compounds 2–4 each) | cached PubMed efetch XML (PMIDs, PublicationType) | ✓ / ✓ | no PMID returned → FAILED; papers outside the graph ignored; malformed XML; HTTP 429 | **verified, partial coverage** | TD-021: stage 04 persists no PMIDs |
| 10b Molecular | 90/90 records; 74 with targets, 16 without (neutral) | Open Targets snapshot 26.09 (ChEMBL, Ensembl, Reactome IDs) | ✓ / ✓ | API down → recorded failure, retried, stage exits 1; blank CSV score; malformed JSONL | **verified; scientific defect TD-042** | not cutoff-bounded |
| 10c Clinical evidence | 90 compounds, 195 links, 177 trials, 67 with posted results | ClinicalTrials.gov v2 cache (2026-10-15) | ✓ / ✓ | failed fetch keeps the cache; stale cache; failed batches; missing dates | **verified**; roles diagnostic | TD-043 heuristics (D) |
| 10d Conflict & context | 91 compounds; 19 assessed, 72 insufficient | curated claims, labels, Open Targets, trials | ✓ / ✓ | missing label dir, duplicate ids, missing files | **verified, sparse by design** | curated claims for case studies only |
| 10e Reproducibility | 14 findings for 4 compounds; 1 paper structure (Droxidopa) | PubMed XML, curated claims | ✓ / ✓ | missing records, non-PMID ids, missing trial files | **verified, partial coverage** | TD-021 |
| 10f Safety evidence | labels 83 retrieved / 7 none; FAERS 90/90 | openFDA label + FAERS caches | ✓ / ✓ | 404 vs 5xx/429/timeout; unparseable 200; retries | **verified** | FAERS counts are reports, **not incidence**; labels current |
| 10g Evidence independence | D1 and D4: 90; D2: 4 assessable; D3: 3 assessable | persisted outputs, 10c | ✓ / ✓ | empty links → FAILED; missing inputs warn | **verified, partial (D2/D3)** | detects dependence; de-duplicates nothing |
| 10h Completeness & gap | 90 compounds × 12 domains; 446 gaps; stage-06 agreement true | all of the above | ✓ / ✓ | empty CSV, absent agent output, stale inputs | **verified** | describes availability, not evidence |

Tests: `tests/test_*_agent.py`, `test_molecular_*`, `test_run_tracking.py`, `test_ui.py`.

## C. VPS scientific validation
Protocol:
- n = 90, 14 positives, prevalence 0.156.
- Stratified bootstrap with 2000 resamples (seed 20261019); differences are paired on the same resamples.
- P@10 averages over ties at the boundary.
- Source: `vps_validation.json`.

**C1. Reproduction.** A second path (pandas/scipy, not stage 06 or `vps_verify.py`) reproduces every rank, score and label (max |Δ| < 1e-12). `scripts/vps_verify.py` also returns MATCH. Labels are attached only after every feature is computed. Stage 06 re-run from the current code (*prior*, earlier session) gives identical scores. Two metadata differences: `n_dimensions_measured` is 3, not 4, for Deferiprone and Trimethobenzamide, and the published file lacks `dimensions_imputed`.

| Score | AUROC [95% CI] | AUPRC [CI] | P@10 [CI] |
|---|---|---|---|
| Equal 5D (published) | **0.775** [0.651, 0.881] | 0.424 [0.240, 0.657] | 0.50 [0.2, 0.7] |
| Equal 4D | 0.700 [0.560, 0.830] | 0.358 [0.197, 0.593] | 0.40 [0.1, 0.7] |
| 5D, TD-042 variant | 0.699 [0.557, 0.830] | 0.307 [0.188, 0.544] | 0.40 [0.1, 0.6] |
| 5D, TD-041 neutral proximity | 0.771 | 0.421 | 0.50 |
| 5D, TD-040 midrank | 0.774 | 0.423 | 0.50 |
| Molecular only (published) | 0.627 [0.442, 0.812] | 0.397 | 0.60 |
| Molecular only (TD-042 variant) | 0.460 [0.297, 0.620] | 0.236 | 0.20 |
| Cutoff-bounded only (proximity + clinical) | 0.653 [0.480, 0.808] | 0.314 | 0.40 |

Paired AUROC differences:

| Comparison | Δ | 95% CI |
|---|---|---|
| 5D − 4D | +0.075 | [−0.024, +0.176] (inconclusive) |
| 5D − 5D TD-042 | +0.076 | [+0.015, +0.155] |
| 5D TD-042 − 4D | −0.001 | [−0.078, +0.078] |

**C2. TD-042, molecular double counting (`td042_lineage.csv`).**
- **Lineage.** The PD module is every Open Targets PD-associated gene whose best allowed-datatype score is ≥ 0.10. The direct component is the drug target's own allowed-datatype PD score. When a target is itself a module gene, every Reactome pathway containing that target "contains a PD module gene" by construction. So the pathway component is a deterministic consequence of the same target–disease association row that the direct component already scores. It is duplicated information, not independent pathway evidence. The documented intent of the indirect tier is "shares a pathway with a PD module gene" (another gene). The variant removes the drug's own targets and genes from the shared set.
- **Impact.**
  - 21 compounds change (6 positives).
  - 16 of them had pathway component 1.0, and 6 drop to 0.
  - Examples: Lidocaine, Quinidine and Zonisamide 0.854 → 0.454; Donepezil, Galantamine and Pyridostigmine 0.748 → 0.348.
  - Only the molecular dimension changes (tested).
- **Conclusion.** Exclusion is scientifically justified on lineage grounds, independently of the metric. Under it, the molecular dimension alone falls to chance level (0.460), and 5D no longer improves on 4D. The reported 5D gain is therefore attributable to the double count. This finding is decided on lineage, not on AUROC. Applying it is an owner decision (G1).

**C3. Normalisation and missingness.**
- **TD-040 (midrank):** AUROC −0.001; maximum rank move 2; top 20 unchanged; Spearman 0.9999. Immaterial.
- **TD-041 (median-imputed vs neutral proximity):** affects 2 compounds (Deferiprone, Trimethobenzamide), rank 0.4944 vs 0.5, AUROC −0.005. Immaterial.
- Both conventions are documented and flagged (`dimensions_imputed` in current code).
- Every score traces to a measured value or a named imputation:
  - neutral 0.5 for 7 compounds with no label and 16 with no target;
  - the median for 2 compounds missing proximity.
- Compounds with fewer measured dimensions sit nearer 0.5 by construction. This is visible in the UI and in 10h, but it is not corrected.

**C4. Leakage review.** The label is continued PD investigation, not efficacy. Registry snapshot 2026-10-05; label trials first posted 2021-01-13 to 2026-09-08.

| Dimension | Temporal status | Evidence checked here |
|---|---|---|
| Proximity | bounded by documentation (Hetionet 2017); no file checksum recorded | — |
| Clinical | bounded by `first_posted` (max 2020-11-25); no NCT overlap with labels; phase from the current record | recomputed |
| Literature | **not bounded** | the checkpoint stores counts only, with no PMIDs or dates, so it cannot be bounded offline |
| Safety | **not bounded** | 78 of 83 label versions took effect after 2020 |
| Molecular | **not bounded** | Open Targets 26.09; no historical snapshot available |

The evaluation is **not leakage-free**. Using only the two bounded dimensions gives AUROC 0.653 [0.480, 0.808]. Historical snapshots were not simulated.

**Nested CV.**
- Setup: 20 repeats × 5 outer folds; 4 inner folds; nonnegative weights summing to 1 on a 0.1 grid; selection on training folds only (tested). Files: `nested_cv_*.csv`.
- 5D: fitted weights reach mean outer AUROC 0.688, against 0.763 for equal weights on the same folds. Fitted weights win in 20% of folds. Weight SD is 0.08–0.10.
- 4D: 0.575 against 0.702.
- Conclusion: weight tuning is not supported with 14 positives. Equal weights remain the best validated scheme.

**C5. Eight-agent composite readiness.**

| Agent | Class | Ready as a numeric dimension? | What is missing |
|---|---|---|---|
| 10b Molecular | numeric (dimension 5) | conditional | TD-042 fix; temporal snapshot |
| 10c Clinical | numeric via stage 03 (dimension 2) | already used | role policy (D-020/TD-038) |
| 10f Safety | numeric via stage 05 label (dimension 4) | already used | FAERS is not incidence; label versions not cutoff-bounded |
| 10g Independence | overlapping-evidence diagnostic | no | it describes dependence; adding it would double-count dimensions 2 and 3 |
| 10a Credibility | categorical | no | 5/90 coverage (TD-021) |
| 10e Reproducibility | categorical | no | 4/90 coverage |
| 10d Conflict | categorical | no | 19/91 assessed; classes, not a scale |
| 10h Completeness | confidence modifier | no (as a score) | could gate or annotate rankings, not add evidence |

**Verdict:** an eight-agent weighted VPS is **not defensible now**. Three agents already feed it through their stages, and the remaining five fail on coverage, scale or independence. Nested CV also shows that weights cannot be fitted reliably at this sample size.

## D. Clinical role review (`clinical_role_review.csv`)
All 195 links were retrieved from the cache; there were no retrieval failures. 35 are human-adjudicated (D-020) and take precedence. 132 carry only a heuristic verdict and are not ground truth. 37 are flagged:

| Flag | n | Meaning |
|---|---|---|
| KEYWORD_DECIDED | 10 | the verdict came from a title, outcome or arm keyword. Most are real procedural context (anaesthesia or MER during DBS surgery: NCT00615472, NCT01721460, NCT02236260). NCT04164758 (Quetiapine, "Daytime Sedation") reads structurally as COMPARATOR_ONLY. Neither reading is preferred. |
| ALIAS_GAP | 5 | the compound appears only as an other-name: Strattera (NCT01340885), AVP-923 (NCT01767129 ×2, adjudicated FIXED_COMBINATION), Rifampin (NCT02174250, spelling variant), and a background class (NCT00605683, E-014) |
| STRUCTURE_INSUFFICIENT | 22 | the registry record has no arm or intervention module (mostly pre-2008), or only OTHER-typed arms: missing data, not a retrieval failure |
| AUTO_VS_ADJUDICATION | 2 | automated BACKGROUND_OTHERNAME vs adjudicated FIXED_COMBINATION; the adjudication stands |

Nothing was relabelled, and no file used in scoring was changed. The flagged links are the human-review list.

## E. Live UI acceptance
All runs were on disposable fixture copies with a separate server (port 8799) and headless Chrome over CDP. Drivers and results are in `ui_acceptance/`.

**Workflow 1: 12/12**
- page views start nothing;
- a terminal run → manifest → browser refresh in 2.3 s;
- a diagnostic run leaves VPS valid;
- a forced 06 failure → FAILED banner naming the retained run, with the last good file unchanged;
- an upstream edit → STALE;
- republication → every view on one data version;
- a missing artefact → "artefact missing", with 10h flagged STALE;
- a suspended server is detected in 17.7 s and recovers;
- a killed and restarted server recovers with backoff (one failed poll in 20 s);
- 390 px: no horizontal scroll on 12 views;
- no JS exceptions or secrets, and only GET requests to localhost.

**Workflow 2: 8/8**
- RUNNING is visible (badge and banner) within 0.5 s of starting a real tracked 06 run, and the result is published without a page reload;
- a manual artefact edit → MODIFIED;
- an edited VPS file → a red "not validated" banner that clears on restore;
- a deleted output → MISSING;
- manifest fingerprints equal the published files;
- 1366 px: no overflow;
- the server log is clean.

On real data, the live server on 8765 serves the new code, and every real stage is fresh. The failure, edit and deletion tests ran only on fixtures, never on real outputs.

## F. Change ledger
| File | Change | Tests |
|---|---|---|
| `scripts/run_stage.py` | `MISSING` status (deleted published output); `--skip-fresh` (no work on unchanged inputs) | `test_run_tracking.py` +2 |
| `ui/server.py`, `ui/app.js`, `ui/style.css` | stage badges from the run tracker (content and dependencies); file check renamed `input_newer` (a hint); MISSING banner and colour; live-monitoring wording | `test_ui.py` (updated 1), browser 20/20 |
| `scripts/vps_validation_experiments.py` (new) | second-path VPS, variants, bootstrap, nested CV | `test_vps_validation_experiments.py` (6) |
| `scripts/clinical_role_review.py` (new) | review table | `test_clinical_role_review.py` (3) |
| `docs/SPRINT_REPORT_2026-10-19.md` (new), `development_log/CHANGES.md`, `TECHNICAL_DEBT.md` | records (append-only) | — |

- Full suite: `./venv/bin/python -m unittest discover -s tests` → 509 tests, OK, exit 0.
- `git diff --check` is clean.
- Rollback: revert the listed files. The new scripts and outputs can simply be removed.
- Protected hashes (ground truth ×2, `vps_scores_v2.csv`, clinical inputs ×2, exclusions, candidates, stage outputs, molecular evidence, registry cache, curated claims, D-020 roles, match audit, evaluation report) are identical at the start and end of the session.

## G. Owner decisions
1. **TD-042 (high).** Alternatives:
   - (a) keep the current definition;
   - (b) exclude the drug's own targets from the pathway credit (staged);
   - (c) drop the pathway component for targets in the module.

   Evidence: lineage shows a duplicated association, not independent evidence. Impact under (b): molecular-only AUROC 0.627 → 0.460, and the 5D gain over 4D disappears (Δ −0.001). **Recommendation: (b)**, decided on lineage. Report 5D results as unvalidated until it is decided. Applying it needs a stage-08/06 rerun into staging, then publication.
2. **Clinical roles (D-020/TD-038/TD-043).** Have a human adjudicate the 37 flagged links. Until then, automated roles stay diagnostic.
3. **Republish VPS metadata (low).** The current-code stage-06 output differs only in `n_dimensions_measured` for 2 compounds and an added `dimensions_imputed` column. Recommend republishing together with any TD-042 decision, to avoid two baseline versions.
4. **TD-040/TD-041:** the effects are immaterial (≤ 0.005 AUROC). Recommend no change.

## H. Next steps
1. Owner decides TD-042. If (b), run stage 08 → 06 into staging, verify with `vps_verify.py` and `vps_validation_experiments.py`, then publish through `run_stage.py`.
2. Human adjudication of the 37 flagged trial links (start with the 10 KEYWORD_DECIDED).
3. TD-021: persist PMIDs and publication dates in stage 04 (opt-in `search_pmids(max_date=…)` exists). This is the only path to a cutoff-bounded literature dimension and to wider 10a/10e coverage.
4. Report evaluation metrics with the bootstrap CIs and the leakage table above. Do not report the 5D vs 4D gain as an improvement.
