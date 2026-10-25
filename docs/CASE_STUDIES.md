# Case studies — verification of top-ranked candidates

Candidates were taken from the **actual pipeline run of 2026-10-05**, ranked by
`VPS_grid_3d` (the best-performing variant on this cohort, AUROC 0.750). Evidence below was
retrieved from ClinicalTrials.gov and PubMed during verification; every PMID, DOI and
numeric result is copied from an API response, **none written from memory**.

**Rule applied throughout: mechanism is not efficacy.** A plausible molecular story is
recorded as mechanism, never as evidence that the drug works. Negative and null results are
recorded with the same prominence as positive ones.

> ✅ **UPDATE 2026-10-05 (afternoon): the artefacts described in §3 have been FIXED.**
> Gate 2 (intervention identity) now rejects them. Phenol, Norepinephrine and Dopamine have
> **zero** accepted trial links and no longer appear anywhere in the ranking. The sections
> below are retained as the verification record that found the defect; §6 gives the
> corrected ranking. Unsupported trial links fell from 39% to 2.8%, with no unexplained
> collision remaining. See `docs/INTERVENTION_MATCHING.md` and TECHNICAL_DEBT TD-018.

---

## 1. Donepezil — rank 1 (VPS_grid_3d 0.883, label = 1)

**Identifier check: GENUINE.** 3 of 4 inspected trials name Donepezil directly as the
intervention (e.g. NCT02206620, NCT00912808). One match (NCT02670161) is a registry study.

**Why the pipeline ranked it highly:** max phase rank 5, 15 PD trials, independence ratio
0.833, molecular plausibility 0.748 (AChE, via the cholinergic route).

### Verified clinical evidence — primary endpoints were NOT met

| Study | Design | Primary outcome result |
|---|---|---|
| Baba T, et al. *EClinicalMedicine* 2022 (DASH-PD) · PMID [35860451](https://pubmed.ncbi.nlm.nih.gov/35860451/) · doi:10.1016/j.eclinm.2022.101571 | RCT, double-blind, placebo-controlled, **n=201**, 4-year follow-up, donepezil in non-demented PD with severe hyposmia | PDD developed in 7/103 (6.8%) donepezil vs 12/98 (12.2%) placebo — **HR 0.609, 95% CI 0.240–1.547, not statistically significant**. Authors' interpretation: "did not change the incidence of dementia but had a beneficial effect on neuropsychological function, with good tolerability." |
| Mancini M, et al. *Parkinsonism Relat Disord* 2019 · PMID [31675664](https://pubmed.ncbi.nlm.nih.gov/31675664/) · doi:10.1016/j.parkreldis.2019.10.022 | RCT, double-blind, crossover, **n=49** (45 completed), donepezil 5→10 mg vs placebo, 6-week periods | **No significant treatment effect** on medio-lateral sway (p=0.28) or gait variability (p=0.31). |

**Supporting context (not efficacy evidence):** Allen NE, et al. *Cochrane Database Syst Rev*
2022, "Interventions for preventing falls in Parkinson's disease" · PMID
[35665915](https://pubmed.ncbi.nlm.nih.gov/35665915/) · doi:10.1002/14651858.CD011574.pub2 —
confirms falls prevention in PD is an active, systematically reviewed question.

### Verdict
**Genuine PD research target; efficacy NOT demonstrated in the trials verified here.** Both
RCTs examined missed their primary endpoints. The pipeline correctly identified a compound
under serious PD investigation — which is what `label = 1` actually encodes (a post-cutoff
trial exists: NCT05709301, NCT06903910) — but that label does not mean the drug works, and
nothing here should be read as efficacy.

---

## 2. Melatonin — rank 4 (VPS_grid_3d 0.828, label = 1)

**Identifier check: GENUINE.** 4 of 4 inspected trials name Melatonin as the intervention
(NCT03258294 "Melatonin(Circadin®)", NCT04287543, NCT02359448, NCT02789592).

**Why the pipeline ranked it highly:** max phase rank 5, 6 PD trials, independence ratio
0.690 (one of the more literature-dependent in the top 15), molecular plausibility 0.200.

### Verified clinical evidence — subjective benefit, objective null

Yousef O, et al. *J Sleep Res* 2026, "The Effectiveness of Melatonin for Sleep Disturbances
in Parkinson's Disease: Systematic Review and Meta-Analysis" · PMID
[40588412](https://pubmed.ncbi.nlm.nih.gov/40588412/) · doi:10.1111/jsr.70097 —
8 RCTs, **409 PD patients**:

| Outcome | Result |
|---|---|
| Sleep quality (PSQI) | MD −1.75 (95% CI −2.94 to −0.55), **p = 0.004** — improved |
| Daytime sleepiness (ESS) | MD −1.07 (95% CI −1.87 to −0.27), **p = 0.009** — improved |
| Sleep onset latency | MD −9.74 (−17.47 to −2.02), p = 0.001 — improved (after heterogeneity adjustment) |
| **Objective sleep parameters** | **no significant impact** |
| REM Sleep Behaviour Disorder (RBDSQ) | MD 0.71 (−0.44 to 1.86), **not significant** |

Corroborating meta-analyses retrieved: Badran AS, et al. *Neurol Sci* 2025 · PMID
[40387966](https://pubmed.ncbi.nlm.nih.gov/40387966/); Zrineh A, et al. *Sleep Med* 2025 ·
PMID [40288252](https://pubmed.ncbi.nlm.nih.gov/40288252/).

### Verdict
**Genuine, with a real but narrow and partly subjective effect.** Benefit is on
patient-reported sleep scales; objective sleep measures were null. This is a symptomatic
sleep intervention — there is **no evidence here of disease modification**, and the
molecular dimension's low score (0.200) is arguably the more honest signal about mechanism.

---

## 3. Phenol / Norepinephrine / Dopamine — ranks 3, 2, 5: **IDENTIFIER ARTEFACTS**

This is the most important finding of the verification, and it is a pipeline defect, not a
biology result.

### What the trials actually test

| Ranked compound | NCT inspected | What the trial actually tests |
|---|---|---|
| **Phenol** (rank 3, label 1) | NCT06596876 *(the trial that creates its positive label)* | HRG2010 vs sustained-release **carbidopa/levodopa** |
| | NCT04380142 | **ABBV-951** vs oral levodopa/carbidopa |
| | NCT00399477 | **rasagiline** (Azilect) |
| | NCT02577523 | **ND0612** (levodopa/carbidopa solution) |
| **Norepinephrine** (rank 2, label 1) | NCT03567447, NCT02897063, NCT03173781 | **Droxidopa** (L-DOPS) — all three |
| **Dopamine** (rank 5, label 1) | NCT00105508 / NCT01264861 / NCT00666653 | **Sarizotan** / **Safinamide** / **pramipexole** |
| **Mannitol** (rank 11) | NCT01927055, NCT01176240 | **Droxidopa** |
| **Acetylsalicylic acid** (rank 7), **Pregabalin** (rank 15) | NCT02670161 | A registry/quality-improvement study whose intervention field reads *"Listed for each disorder below, up to three drugs per disorder"* |

**No inspected trial administers phenol, norepinephrine, dopamine or mannitol as the study
drug.**

### Mechanism of the defect

`scripts/03_clinicaltrials_groundtruth.py` queries `query.intr=<compound>` and then
verifies client-side that the trial's **condition** really is Parkinson's
(`is_actually_pd`). It performs **no equivalent check on the intervention.**
ClinicalTrials.gov expands intervention queries along at least four routes, all observed
here:

1. **Chemical class** — levodopa is a phenol → `Phenol` inherits every levodopa trial.
2. **Prodrug / metabolite** — droxidopa is a norepinephrine prodrug → `Norepinephrine`
   inherits droxidopa trials.
3. **Pharmacological class** — dopaminergic agents → `Dopamine`.
4. **Excipient** — mannitol in a formulation → `Mannitol`.
5. **Catch-all registry studies** that enumerate many drugs match almost any query.

### Quantified scope (full cohort, not extrapolated)

Measured by `scripts/check_intervention_match.py` over all 451 (compound, trial) pairs:

| | |
|---|---|
| Trial links where an intervention names the compound | 255 MATCHED + 3 MATCHED_PARTIAL |
| Trial links where **no** intervention names the compound | **177 (39%)** |
| Catch-all registry studies | 16 |
| Compounds with **no** naming trial at all | **60 of 178** |
| **Of the 141-compound evaluable pool** | **48 flagged (34%)** |
| **Of the 30 positive labels** | **7 rest on no naming trial (23%)** |

### Verdict
**The clinical-maturity dimension and the ground-truth labels are both contaminated.**
Because positives are affected, this does not merely reorder the output — it biases the
AUROC measurements themselves. Recorded as **TD-018**.

Note the molecular dimension scored Phenol **0.000** and Mannitol **0.000**: it found no
mechanistic basis for either, which is correct. It did not rescue Norepinephrine (0.578) or
Dopamine (0.400), whose *molecules* genuinely do act on PD-relevant targets even though the
*trials* were misattributed.

---

## 4. Lisuride — rank 6, label = 0 (a instructive "false positive")

**Identifier check: GENUINE** (2 of 3 trials name lisuride).

Lisuride is a dopamine-agonist ergoline. It ranks 6th but carries `label = 0` purely
because no PD trial for it was **first posted after 2021-01-01** — its three PD trials
(NCT00605683 n=679, NCT00408915 n=60, NCT00089622 n=40) are all pre-cutoff.

**This is not a model error.** It illustrates what the ground truth actually measures:
*"a new trial was registered after the cutoff"*, not *"this drug is useful in PD"*. An
established drug that was already investigated and is no longer being newly trialled is
indistinguishable, under this label definition, from a drug that never worked. Relevant to
TD-004 (candidate-pool selection bias).

No efficacy claim is made here; lisuride's PD pharmacology was not independently verified
beyond confirming the trials exist and name it.

---

## 5. Summary

| Candidate | Rank | Identifier | Clinical evidence verified | Efficacy demonstrated? |
|---|---|---|---|---|
| Donepezil | 1 | ✅ genuine | 2 RCTs (n=201, n=49) | ❌ both missed primary endpoints |
| Norepinephrine | 2 | ❌ artefact (droxidopa) | — | n/a |
| Phenol | 3 | ❌ artefact (levodopa) | — | n/a |
| Melatonin | 4 | ✅ genuine | SR/MA, 8 RCTs, n=409 | ⚠️ subjective sleep only; objective null |
| Dopamine | 5 | ❌ artefact (dopaminergics) | — | n/a |
| Lisuride | 6 | ✅ genuine | 3 pre-cutoff trials | not assessed; label=0 is a cutoff artefact |

**Bottom line:** of the top five ranked candidates, **three are identifier artefacts**, and
the two genuine ones have verified clinical evidence that is null or narrow. No candidate
examined here supports a disease-modification claim for Parkinson's disease.


---

## 6. Corrected ranking (2026-10-05, after the Gate-2 fix)

Dataset: **90 evaluable compounds, 17 positives**. Best variant by AUROC: `VPS_equal_5d`
(0.747). Top 12:

| # | Compound | VPS_equal_5d | label | molecular score |
|---|---|---|---|---|
| 1 | Donepezil | 0.790 | 1 | 0.748 |
| 2 | Quetiapine | 0.753 | 1 | 0.690 |
| 3 | Zonisamide | 0.732 | 0 | 0.854 |
| 4 | Dexmedetomidine | 0.731 | 1 | 0.450 |
| 5 | Domperidone | 0.723 | 0 | 0.400 |
| 6 | Melatonin | 0.704 | 1 | 0.200 |
| 7 | Aripiprazole | 0.699 | 0 | 0.414 |
| 8 | Droxidopa | 0.694 | 0 | 0.578 |
| 9 | Lisuride | 0.691 | 0 | 0.000 |
| 10 | Sildenafil | 0.674 | 0 | 0.219 |
| 11 | Topiramate | 0.664 | 0 | 0.645 |
| 12 | Methylphenidate | 0.662 | 1 | 0.285 |

**Every artefact is gone.** Phenol, Norepinephrine, Dopamine, Mannitol (as a droxidopa
match), Acetylsalicylic acid and Pregabalin no longer hold any accepted trial link.
Droxidopa now appears under its **own** name rather than being misattributed to
Norepinephrine — the corrected behaviour.

### Case studies that remain valid

**Donepezil (still rank 1)** and **Melatonin (now rank 6)** were verified above and their
evidence is unchanged: Donepezil's two RCTs both missed their primary endpoints
(DASH-PD HR 0.609, 95% CI 0.240–1.547, ns; Mancini p=0.28/0.31), and Melatonin's benefit is
confined to subjective sleep scales with objective measures null. **Neither supports a
disease-modification claim.** No new efficacy claim is made for any compound in this table;
`label = 1` still means only *"a qualifying trial was first posted after 2021-01-01"*.

### Statistical caveat
With 17 positives, bootstrap 95% CIs on AUROC span ≈ ±0.15. The apparent advantage of the
5-dimension model is **+0.059, 95% CI [-0.025, +0.148]** — not significant. See TD-020.
