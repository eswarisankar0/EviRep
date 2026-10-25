# Continuation report, 2026-10-19: TD-042 corrected baseline and clinical-role worklist

Continues [`SPRINT_REPORT_2026-10-19.md`](SPRINT_REPORT_2026-10-19.md).

**Stopped at the authorization boundary.** The corrected baseline is built, verified and rehearsed. The live
approved baseline (`data/vps_scores_v2.csv`) is unchanged and still the one displayed.

Paths:
- candidate: `data/_candidates/td042_v1/` (see its README);
- clinical review: `data/_runs/clinical_review_20261019/`;
- earlier experiments: `data/_runs/validation_20261019/` (unchanged).

## 1. TD-042: rationale and implementation
**Rationale.**
- The PD module is the set of Open Targets PD-associated genes with an allowed-datatype score ≥ 0.10.
- The direct component is the drug target's own allowed-datatype PD score.
- When the target is itself a module gene, every Reactome pathway containing it "contains a PD gene" by construction.
- The pathway component then re-scores the same target–PD association as if it were independent pathway evidence.

The corrected rule asks the question the indirect tier documents: "does this target share a pathway with *another* PD gene?"

**Implementation (default off = approved rule).**
- `scripts/molecular_agent.py`, `MolecularAgentConfig.pathway_excludes_drug_targets`:
  - removes **all** of the drug's own target Ensembl IDs from each pathway's module-gene set, not only the strongest target, since every target's association is direct evidence for that drug;
  - records the removed genes per pathway entry (`drug_targets_excluded_from_shared`) and the setting in `provenance`.
- `scripts/08_molecular_pathway.py`:
  - `--exclude-drug-targets-from-pathways`;
  - `--offline`: cache only, so any miss is a recorded failure, stage exits 1;
  - `--resolutions-from`: freezes drug identity to an earlier run.
- **No-op proof:** with the rule off, an offline replay reproduces the published `molecular_pathway.csv` and the evidence JSONL **byte for byte** (0 network requests, 171 cache hits).
- **Edge cases**, tested in `tests/test_td042_pathway_rule.py` (8 tests):
  - a single target that is the only module gene;
  - other module genes still credited and named;
  - multiple targets, where all are excluded;
  - one pathway listed by two targets, counted once;
  - no targets or no pathways;
  - flag off equals the approved rule;
  - the offline session never calls the network;
  - the resolutions round-trip.
- **Checks on all 90 real records:**
  - no pathway entry credits a drug through its own target (0 violations);
  - 260 exclusions recorded;
  - 44 multi-target drugs handled;
  - direct components, targets, resolutions and `n_targets` are identical to the approved run.
- **Cross-implementation:** the agent rule (Ensembl IDs) and the earlier experiment (gene symbols) change the same 21 compounds. Their scores agree to 1e-6 (rounding), and the 5D VPS to 1.7e-16.

## 2. Original vs corrected
- Only the molecular dimension changes. VPS-4D and the four other ranks are identical (verified).
- 21 molecular scores fall; none rises.
- 78 of 90 5D ranks move, because the molecular percentile ranks of unchanged compounds shift too. The largest move is 33 places (Galantamine).

| Positive (label 1), molecular changed | Molecular score | 5D rank |
|---|---|---|
| Donepezil | 0.748 → 0.348 | 1 → 7 |
| Quetiapine | 0.690 → 0.557 | 3 → 2 |
| Lidocaine | 0.854 → 0.454 | 9 → 18 |
| Terazosin | 0.703 → 0.436 | 17 → 30 |
| Pyridostigmine | 0.748 → 0.348 | 29 → 61 |
| Galantamine | 0.748 → 0.348 | 34 → 67 |

Top 10:
- approved: Donepezil, Zonisamide, Quetiapine, Dexmedetomidine, Lisuride, Melatonin, Droxidopa, Methylphenidate, Lidocaine, Domperidone;
- corrected: Droxidopa, Quetiapine, Dexmedetomidine, Lisuride, Melatonin, Zonisamide, Donepezil, Domperidone, Methylphenidate, Aripiprazole.

Full table: `data/_candidates/td042_v1/ranking_comparison.csv`.

Metrics, reported but not used to choose the rule:

| | AUROC | AUPRC | P@10 |
|---|---|---|---|
| Approved 5D | 0.775 | 0.424 | 0.50 |
| Corrected 5D | 0.699 | 0.307 | 0.40 |
| 4D | 0.700 | 0.358 | 0.40 |

The prior sprint's CIs and paired tests apply to this exact variant: the scores are identical to 1.7e-16.

## 3. Independent verification (all pass)
- The candidate was produced through the real mechanisms in an isolated root (`run_stage.py 08`, then `06`). Stage 06 staged its output, validated it with the independent recompute (`vps_verify.py`), and published atomically inside the candidate root only.
- `vps_verify.py --root data/_candidates/td042_v1/root`: exit 0, MATCH, max |diff| 1.1e-16.
- `verify_td042_candidate.py` (a second path through `vps_validation_experiments.build`): exit 0, `all_pass: true`. Results for 90 compounds, 0 duplicates:
  - ranks, VPS-5D and VPS-4D agree to ≤ 1.7e-16;
  - labels are identical to the independent rebuild and to the approved baseline;
  - `dimensions_missing`, `dimensions_imputed` and `n_dimensions_measured` match the expected values for every compound.

## 4. Missingness and imputation (candidate, unchanged by TD-042)
- `n_dimensions_measured`: 69 compounds have 5, 17 have 4, 4 have 3.
- Missing, neutral rank 0.5:
  - molecular only: 14;
  - safety only: 5;
  - both: 2.
- Imputed, median, flagged in `dimensions_imputed`: proximity, 2 compounds (Deferiprone, Trimethobenzamide).

The candidate is written by the current stage-06 code, so it also carries the metadata fix noted earlier: those 2 compounds count 3 measured dimensions, not 4.

## 5. Publication rehearsal (disposable fixture copies; real data untouched)
Script: `data/_candidates/td042_v1/publish_td042.sh`.

| Scenario | Result |
|---|---|
| A. Stage 08 fails (Open Targets cache removed, offline) | script exits 1; 08 FAILED; molecular and VPS files byte-unchanged; 06 still the approved result |
| B. 08 succeeds, then 06 fails (corrupted proximity input) | VPS file unchanged; 06 shows STALE plus "latest attempt failed", so it is never presented as current |
| B-rollback (a) copy `data/_runs/<08>/previous/*` back | files byte-identical to approved; `vps_verify` MATCH; 08 shows MODIFIED (honest, untracked edit) |
| B-rollback (b) tracked re-run of 08 with the approved rule (`--offline --resolutions-from`) | byte-identical to approved; 08 SUCCESS (preferred rollback) |
| C. Clean full publication | exit 0; 11 tracked runs SUCCESS; all 21 stages fresh (12 SUCCESS, 9 untouched ADOPTED); published VPS **byte-identical** to the verified candidate |

My first rehearsal of B went wrong because of a setup mistake (my restore nested the hidden cache directory inside a new empty one). It was redone; the product behaved correctly in both runs. The first full run also showed that the dependant list was incomplete (6 stages left STALE). The script now re-runs eval, 10b, 10c, 10f, 10d, 10e, 10g, 07 and 10h in that order.

**UI.**
- `/api/status` now reports `approved_baseline` (path and run id) and `pending_candidates`. Candidates are listed by name and verification state only, never their scores.
- The score provenance line reads "Approved baseline `data/vps_scores_v2.csv` · scores from run …".
- Checked on the real repository with a second server instance: Donepezil is displayed with the approved r_molecular 0.932 and VPS 0.773 (rank 1), not the candidate's 0.446 / 0.676.
- Test: `test_ui.py::TestLiveStatus::test_candidates_are_listed_as_pending_and_never_displayed`.
- The already-running server on 8765 picks up the server-side change only after a restart; its JS degrades gracefully until then.

## 6. Clinical-role review
Worklist: `data/_runs/clinical_review_20261019/review_worklist_flagged.csv`. It covers 37 links, ordered by priority. Columns: trial ID, compound, intervention text, arm types, automated role, structural reading, adjudicated role, reason, evidence needed, status, and empty reviewer/decision fields. The full 195-link table was regenerated and is unchanged.

**Correction to the previous report:** 9 of the 37 flagged links already carry human D-020 adjudications. They are shown verbatim from `data/feature_trial_roles_td038.csv` and kept ("retained, not re-opened"). **28 links await adjudication:**

| Flag (priority) | Adjudicated (retained) | Unresolved |
|---|---|---|
| 1. KEYWORD_DECIDED | 5 (NCT00615472 ×3, NCT02256319 ×2) | **5**: NCT00608231, NCT01721460, NCT01789385 (Dexmedetomidine); NCT02236260 (Lidocaine); NCT04164758 (Quetiapine) |
| 2. ALIAS_GAP | 2 (NCT01767129, AVP-923) | 3: NCT01340885 (Strattera), NCT02174250 (Rifampin), NCT00605683 (Lisuride, background) |
| 3. STRUCTURE_INSUFFICIENT | 2 | 20: the registry record has no arm/intervention module, or only OTHER-typed arms |

No role was inferred, no unresolved case relabelled, and the review tooling writes only under `data/_runs/`. It is separate from ground-truth and feature generation.

## 7. Tests and integrity (executed in this session)
| Command | Result |
|---|---|
| `./venv/bin/python -m unittest tests.test_td042_pathway_rule` | 8 tests OK |
| `… tests.test_molecular_agent tests.test_molecular_vps_audit` | OK (after the agent change) |
| `… tests.test_ui` | 70 tests OK |
| `… tests.test_clinical_role_review` | 4 tests OK. The first draft failed on a wrong assumption about adjudicated links; the test was corrected to check against the D-020 file |
| `./venv/bin/python -m unittest discover -s tests` | **519 tests, OK, exit 0** |
| `./venv/bin/python scripts/vps_verify.py` (live) | exit 0, MATCH |
| `… --root data/_candidates/td042_v1/root` | exit 0, MATCH |
| `./venv/bin/python data/_candidates/td042_v1/verify_td042_candidate.py` | exit 0, all_pass |
| `git diff --check` | clean |
| Protected-file hashes (19 files: ground truth, VPS, clinical inputs, exclusions, candidates, stage outputs, molecular evidence, registry cache, curated claims, D-020 roles, match audit, evaluation report) | identical to the session start |
| `git diff --cached` hash | identical to the session start; nothing staged, committed or pushed |

## 8. Remaining limitations
- **Leakage (unchanged by TD-042):**
  - literature has no persisted PMIDs or dates (TD-021);
  - safety labels are current versions (78 of 83 took effect after 2020);
  - Open Targets is the 26.09 snapshot.
  - The corrected molecular dimension is still not cutoff-bounded. The evaluation is not leakage-free.
- **Coverage:** 10a covers 5 compounds, 10e 4, and the 10g D2/D3 checks 4 (TD-021).
- With the correction, molecular-only AUROC is 0.460, so the molecular dimension adds no measurable discrimination. Its place in VPS is a separate scientific question; nothing was changed.

## 9. Approval needed before the live baseline changes
One explicit owner instruction, for example: *"Approve TD-042 candidate td042_v1: run `sh data/_candidates/td042_v1/publish_td042.sh` on the live repository."* That step:
1. replaces `data/molecular_pathway.csv` and `data/molecular_pathway_evidence.jsonl` (tracked stage 08; previous files kept in `data/_runs/<run>/previous/`);
2. replaces `data/vps_scores_v2.csv` and the other stage-06 outputs, after independent verification;
3. re-runs eval, 10b, 10c, 10f, 10d, 10e, 10g, 07 and 10h.

Also update `TECHNICAL_DEBT.md` TD-042 to FIXED and record a DECISIONS entry. The approved baseline stays until then.
