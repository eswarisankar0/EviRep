# TD-042: molecular pathway double counting (final audit 2026-10-22)

**Status: RECOMMENDED — CANDIDATE VERIFIED, ADOPTION PENDING.** The approved artefacts are unchanged.

## Question
Does the molecular dimension give a drug credit twice for the same evidence?

## The chain, as implemented (`scripts/molecular_agent.py`)
1. **Drug → targets:** ChEMBL mechanism-of-action targets (`extract_targets`, `:543`).
2. **Direct component:** for each target, the maximum Open Targets PD association over *allowed* datatypes (genetic, animal model, affected pathway, somatic, expression). `clinical` and `literature` are excluded (`:165`).
3. **Pathway component:** the share of the targets' Reactome pathways that contain at least one gene of a 300-gene PD module (`build_mechanistic_chain`, `:786`).
4. **Score:** 0.6 × direct + 0.4 × pathway (`:1000-1003`).

## The defect
The PD module is built from the genes most strongly associated with PD. A drug whose own target is in that module therefore earns:
- **direct credit** for the target–PD association, and
- **pathway credit** for every pathway of that target, because the target itself is the module gene "shared" with PD.

The second credit restates the first, so it is not indirect evidence.

**Example, Donepezil:** its target ACHE is a PD-module gene. Pathway credit 3/3 comes entirely from ACHE, giving a molecular score of 0.748. Excluding the drug's own targets gives 0.348.

## Alternatives evaluated (same cohort, labels and bootstrap; nothing tuned)

| Rule | Biological meaning | 5D AUROC (approved cohort) | Molecular alone |
|---|---|---|---|
| Published (approved) | pathway credit includes the drug's own target | 0.775 [0.656, 0.881] | 0.627 |
| **TD-042 corrected** | pathway credit only via *other* PD-module genes | **0.699 [0.557, 0.830]** | 0.460 |
| Direct only (computed today) | molecular = direct component only; no target → 0.5 | 0.759 | 0.622 |
| 4D (no molecular) | – | 0.700 | – |

The "molecular alone" values come from the TD-042 candidate's verification (`data/_candidates/td042_v1/verification.json`).

## Verification
- **Synthetic graphs:** `tests/test_td042_pathway_rule.py` (6 tests) covers:
  - a target that is the only module gene gets no pathway credit;
  - other module genes still count;
  - all of a drug's targets are excluded, not only the strongest;
  - a pathway shared by two targets counts once;
  - no targets / no pathways;
  - flag off reproduces the baseline.
- **Independent re-derivation today:** stage 08 was re-run with `--exclude-drug-targets-from-pathways --fresh` in an isolated copy, from the response cache (2 live requests, both for Dopamine). It reproduces the `td042_v1` candidate **exactly** for all 90 shared compounds (max |diff| 0.0).
- **Verification of every candidate:** `vps_verify` gives MATCH for each TD-042 candidate (`experiments/candidates/*/td042*`).

## Effect
- **Scores:** 21 compounds change molecular score, including 6 positives (Donepezil, Galantamine, Lidocaine, Pyridostigmine, Quetiapine, Terazosin).
- **Paired difference:** approved − corrected = +0.076 [0.014, 0.158].
- **5D vs 4D:** with TD-042 the gap is −0.001 [−0.075, 0.080]. **The molecular dimension then adds nothing measurable.**
- **Where the signal sits:** the direct target–PD evidence carries most of the molecular signal (direct-only 0.759). The corrected pathway component mostly adds noise (0.699 < 0.759).
- **Possible follow-up:** a direct-only molecular dimension is a defensible alternative. It is **not** adopted here, because choosing it after seeing 0.759 vs 0.699 would be outcome-informed selection. It is listed as a pre-specification candidate for a future, independent evaluation.

**Case studies:**

| Compound | Approved | TD-042 |
|---|---|---|
| Donepezil | 1/90 | 7/90 |
| Droxidopa | 7/90 | 1/90 |
| Galantamine | 34/90 | 67/90 |
| Lidocaine | 9/90 | 18/90 |
| Melatonin | 6/90 | 5/90 |

## Decision and justification
**The corrected rule is the scientifically defensible definition.** The pathway component is documented as *indirect* evidence ("gene → pathway → disease", `build_mechanistic_chain`). Credit that exists only because the drug's own target is a PD-module gene is the same target–PD association the direct component already scores. Counting it twice inflates exactly the drugs whose target is a known PD gene. That systematically favours already-studied mechanisms, which correlate with the trial-activity label.

The higher AUROC of the published rule is **not** a reason to keep it.

**Adoption requires owner action, because it rewrites protected artefacts:**
```
data/_candidates/td042_v1/publish_td042.sh    # rehearsed; or apply via the corrected_all candidate (see FINAL_RELEASE_DECISION.md)
./venv/bin/python scripts/run_stage.py eval
```
**Rollback:** the approved files are preserved in `~/EviRep_recovery_finalmission_20261022T1504Z/data_snapshot.tgz`.
