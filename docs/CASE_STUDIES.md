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
*(2026-10-12: NCT04287543 is WITHDRAWN with enrollment 0 per the registry record.)*

**Why the pipeline ranked it highly:** max phase rank 5, 6 PD trials, independence ratio
0.690 (one of the more literature-dependent in the top 15), molecular plausibility 0.200.

### Verified clinical evidence — subjective benefit, objective null

Yousef O, et al. *J Sleep Res* 2026, "The Effectiveness of Melatonin for Sleep Disturbances
in Parkinson's Disease: Systematic Review and Meta-Analysis" · PMID
[40588412](https://pubmed.ncbi.nlm.nih.gov/40588412/) · doi:10.1111/jsr.70097 —
8 RCTs, **409 PD patients** (7 entered the meta-analysis):

| Outcome | Result |
|---|---|
| Sleep quality (PSQI) | MD −1.75 (95% CI −2.94 to −0.55), **p = 0.004** — improved |
| Daytime sleepiness (ESS) | MD −1.07 (95% CI −1.87 to −0.27), **p = 0.009** — improved |
| Sleep onset latency | MD −9.74 (−17.47 to −2.02), p = 0.001 — improved (after heterogeneity adjustment) |
| **Objective sleep parameters** | **no significant impact overall**; sleep onset latency and total sleep time improved only after heterogeneity adjustment *(wording corrected 2026-10-12 against the abstract)* |
| Clinical importance | authors: subjective improvements "did not meet minimal clinically important difference" |
| REM Sleep Behaviour Disorder (RBDSQ) | MD 0.71 (−0.44 to 1.86), **not significant** |

Overlapping meta-analyses retrieved (largely the same RCT pool, so **not** independent
confirmation): Badran AS, et al. *Neurol Sci* 2025 · PMID
[40387966](https://pubmed.ncbi.nlm.nih.gov/40387966/) · doi:10.1007/s10072-025-08221-8 —
PSQI improved (MD −1.88, P = 0.002) but **ESS not significant (MD −1.04, P = 0.25)** and no
UPDRS-III effect, i.e. it *disagrees* with Yousef on daytime sleepiness; Zrineh A, et al.
*Sleep Med* 2025 · PMID [40288252](https://pubmed.ncbi.nlm.nih.gov/40288252/) ·
doi:10.1016/j.sleep.2025.106540. *(2026-10-12: previously described as "corroborating".)*

### Verdict
**Genuine, with a real but narrow and partly subjective effect.** Benefit is on
patient-reported sleep scales, below the minimal clinically important difference;
objective sleep measures were not improved overall, and the meta-analyses disagree on ESS. This is a symptomatic
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
because no PD trial for it was **first posted after 2021-01-01** — its two lisuride trials
(NCT00408915 n=60, NCT00089622 n=40) are pre-cutoff.

> **Correction 2026-10-12.** This section previously listed NCT00605683 (n=679) as a third
> lisuride trial. The registry record shows it is **MOTION, a safinamide add-on trial**;
> lisuride appears only among permitted background dopamine agonists. Gate 2 still accepts
> it (`token_othername`), so it remains Lisuride's phase-3 entry in the clean pre-cutoff
> file — a residual false match recorded as ERRORS_AND_BLOCKERS E-014 / TECHNICAL_DEBT TD-023.

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
| Melatonin | 4 | ✅ genuine | SR/MA, 8 RCTs (7 pooled), n=409 | ⚠️ subjective sleep only, below MCID; objective not improved overall |
| Dopamine | 5 | ❌ artefact (dopaminergics) | — | n/a |
| Lisuride | 6 | ✅ genuine (2 trials; NCT00605683 is a false match, E-014) | 2 pre-cutoff trials | not assessed; label=0 is a cutoff artefact |

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
5-dimension model is **+0.059** — not significant. *(2026-10-12: this section previously gave
the CI as [-0.025, +0.148] while TD-020 gives [-0.024, +0.150]. Neither is reproducible; a
recomputation gives [-0.024, +0.146] (`default_rng(42)`) or [-0.025, +0.151]
(`RandomState(42)`), 2000 paired resamples. All intervals include zero. See the TD-020
addendum and E-015.)*

---

## 7. Droxidopa — literature-independence verification (2026-10-12)

**Pipeline facts** (`data/vps_scores_v2.csv`): rank 8/90 under VPS_equal_5d (0.694), 14/90 under
VPS_equal, label 0, 13 accepted pre-cutoff trials, molecular 0.578 (adrenergic targets; e.g.
ADRB1 permitted score 0.0, its clinical 0.92 / literature 0.20 excluded for leakage).

### Reconciled counts — VERIFIED
Recomputed with networkx from `data/literature_graph_droxidopa.json` and compared with
`data/_literature_checkpoint.jsonl` and `data/literature_independence.csv`:

| Quantity | JSON | Checkpoint | CSV |
|---|---|---|---|
| Papers | 26 | 26 | 26 |
| Shared-author edges | 4 | 4 | 4 |
| Citation edges | 10 | 10 | 10 |
| Connected components | 16 (sizes 10, 2, 1×14) | 16 | 16 |
| independence_ratio | 16/26 = 0.615 | 0.615 | 0.615 |

No self-loops, duplicate pairs or pair counted under both edge types. The historical
"26 papers → 5 clusters" came from the old synthetic Figure 3 and was wrong (TD-002).
**Edge identity** can be checked only at count level: stage 04 never stored edge lists
(TD-026). All 26 PMIDs, titles and years match PubMed (one batched esummary).

### What the 16 components do and do not mean — JUDGMENT, from abstracts
- **They are publication clusters, not 16 independent pieces of evidence.** 13 of the 26 are
  reviews; about 12 do not test droxidopa in PD at all (enzymatic synthesis 40379165,
  docking 41520443, text-mining 41745708, a rasagiline BP study 34977548, an AL-amyloidosis
  case 32560740, prescribing-pattern databases 37426443 / 39441810, among others).
- **No randomized droxidopa efficacy trial is among the 26.** The pivotal trials (e.g. PMIDs
  24944260, 25350981, 24326693, 25487613) fall outside the stage-04 sample, which is the
  30 first-returned of **90** matching records (TD-021). The reviews spread across
  components most likely summarise the same NOH301/302/303/306 programme, but the graph cannot
  join them because those trial papers are not in it.
- **Temporal:** 8 of the 26 papers are pre-cutoff, 18 post-cutoff. Stage 04 has no date filter.
- Figure 3 is drawn only from the persisted JSON. Its caption now says "connected components
  (publication clusters, not independent trials)" and singletons are grey (CHANGES.md,
  2026-10-12).

**Status: PARTIAL.** Counts and provenance are VERIFIED. The independent-evidence reading is a
documented judgment, and the sample is not representative of droxidopa's PD literature
(TD-021). Next action: a date-bounded, uncapped re-query is a methodology change for the owner.

---

## 8. Seven shortlisted candidates — verification records (2026-10-12)

Method: identifiers and trial roles from `data/clinicaltrials_match_audit.csv`, registry
records re-fetched from ClinicalTrials.gov API v2, literature from PubMed E-utilities
(abstracts read). Every PMID/NCT/DOI/statistic was copied from an API response received in
this session (≈62 requests in total across the case-study work, all HTTP 200). Ranks are
from `data/vps_scores_v2.csv` (n = 90). **No record below is evidence of efficacy from a score.**

| Candidate | IDs | In pool? rank (5d / 4d equal) · label | Claim checked | Verdict | Status |
|---|---|---|---|---|---|
| Donepezil | DB00843 / CHEMBL502 | yes · 1 / 4 · 1 | label trials genuine; PD efficacy | label genuine; efficacy not established | **VERIFIED** |
| Melatonin | DB01065 / CHEMBL45 | yes · 6 / 2 · 1 | label trial genuine; §2 summary holds | label genuine; symptomatic sleep only | **VERIFIED** |
| Domperidone | DB01184 / CHEMBL219916 | yes · 5 / 3 · 0 | trial links genuine; PD role | established adjunct, not a repurposing hit; safety signal missed | **VERIFIED** |
| Propofol | DB00818 / CHEMBL526 | yes · 14 / 19 · 0 | why it has PD trials | procedural-context artefact (anaesthesia) | **VERIFIED** |
| Norepinephrine | DB00368 / CHEMBL1437 | no | former rank 2, label 1 | artefact (droxidopa / methylphenidate trials) | **VERIFIED** |
| Dopamine | DB00988 / CHEMBL59 | no | former rank 5, label 1 | artefact (sarizotan / safinamide / pramipexole / cell & gene therapy) | **VERIFIED** |
| Propranolol | DB00571 / CHEMBL27 | no | why shortlisted; PD evidence | symptomatic tremor adjunct only | **PARTIAL** |

### 8.1 Donepezil
- **Label trials (post-cutoff, MATCHED):** NCT05709301 (donepezil vs placebo, MCI in PD, posted
  2023-02-02, phase 2, n=120 planned); NCT06903910 (single arm, n=6, posted 2025-04-01;
  primary outcome is mechanistic — Ch4 grey-matter density vs gait speed). Both name donepezil.
- **Additional evidence:** Dubois B, et al. *Mov Disord* 2012 · PMID 22915447 ·
  doi:10.1002/mds.25098 — RCT, n=550 PDD; "ADAS-cog … were not significant for donepezil in
  the intent-to-treat population by the predefined statistical model (… P = .050, for 5 mg;
  … P = .076, for 10 mg)". Pagano G, et al. *JNNP* 2015 · PMID 25224676 ·
  doi:10.1136/jnnp-2014-308764 — class-level MA of cholinesterase inhibitors: slower MMSE
  decline, no effect on falls, tremor and adverse events favoured placebo.
- **Independence:** Pagano pools ChEIs and probably includes Dubois (not verified).
- **Temporal:** Dubois 2012, Pagano 2015, Mancini 2019 pre-cutoff; DASH-PD 2022 post-cutoff.
- **Policy note:** NCT00165815 (intervention "ARICEPT") is NO_MATCH — trade-name alias gap
  (pre-cutoff; label unaffected; TD-023).
- **Verdict:** SUPPORTS that the label is genuine; REJECTS any efficacy reading — the
  largest PDD RCT and both RCTs in §1 missed their primary endpoints.

### 8.2 Melatonin
- **Label rests on one trial:** NCT07375693 (posted 2026-01-29), melatonin 10 mg vs placebo;
  primary outcome an oxidative-stress biomarker, not clinical efficacy. NCT05307770 (ER
  melatonin in RBD, posted 2022-04-01) is MATCHED but dropped by the study-type filter
  because its interventions are typed DIETARY_SUPPLEMENT (TD-023).
- **Evidence:** see §2 (corrected 2026-10-12). Three overlapping meta-analyses; Badran 2025
  finds ESS not significant where Yousef 2026 finds it significant.
- **Verdict:** SUPPORTS label identity; symptomatic subjective-sleep benefit only.

### 8.3 Domperidone
- **Trial roles (registry arm data):** NCT00103597 (orthostatic hypotension, PD+MSA) and
  NCT00305331 (agonist-induced oedema) test domperidone; NCT03022201 uses it as the
  **active comparator** to DA-9701; NCT00006077 uses it as **co-medication** (study drug
  NS2330). No post-cutoff trial → label 0 is consistent.
- **Evidence:** Bacchi S, et al. *J Parkinsons Dis* 2017 · PMID 29103053 ·
  doi:10.3233/JPD-171209 — SR: in the sole independent RCT, only a "non-statistically
  significant trend" for OH; most evidence supports use with apomorphine. Schoffer KL, et al.
  *Mov Disord* 2007 · PMID 17557339 — crossover n=17, trend only. Soykan I, et al.
  *Mov Disord* 1997 · PMID 9399220 — open n=11, improved upper-GI symptoms.
- **Safety (negative):** Renoux C, et al. *Br J Clin Pharmacol* 2016 · PMID 27062307 ·
  doi:10.1111/bcp.12964 — VT/SCD RR 1.22 (0.99–1.50) overall, **1.38 (1.07–1.78)** with
  cardiovascular history. NCT02500108 (n = 214,962) is very likely the same study;
  Nakhlé 2021 (PMID 34508851) re-analyses the same data → **one** safety source, not three.
  The safety dimension scored domperidone 0 serious terms (TD-022).
- **Verdict:** the rank reflects an **established PD adjunct** (GI/OH), not a repurposing
  opportunity; the molecular score credits a D2 *antagonist* via pathway overlap without
  encoding direction of action.

### 8.4 Propofol
- **All linked trials are procedural:** NCT00615472 (IV vs inhalational anaesthesia,
  postoperative delirium), NCT02256319 (dexmedetomidine vs propofol sedation during DBS;
  phase 4, n=12 — the source of max_phase_rank 5), NCT00355927, NCT04502550; the only
  post-cutoff trial NCT05895019 (2023) is observational (anaesthetic dosing) → label 0.
- **Literature:** Martinez-Simon A, et al. *Anesthesiology* 2017 · PMID 28492384 (beta-power
  change in DBS LFPs under propofol); Wang P, et al. *Clin Interv Aging* 2023 · PMID 36879829
  (higher propofol EC50 in PD) — anaesthesia context, not treatment.
- **Verdict:** REJECTS propofol as a candidate; its clinical-maturity signal is a
  procedural-context artefact (TD-023). **Follow-up:** Dexmedetomidine (rank 4, **label 1**)
  shares NCT02256319 and has not yet been checked.
- **Follow-up resolved 2026-10-13 (§9):** Dexmedetomidine's five pre-cutoff trials are all
  DBS-surgery sedation / recording studies, and its only label trial NCT05376761 (posted
  2022-05-17, registry re-fetched) is an anaesthetic dose-finding study ("Median Effective
  Concentration (EC50) of Dexmedetomidine in Deep Brain Stimulation Implantation…", primary
  purpose OTHER). Its **label 1 is a procedural artefact**, not a repurposing signal (TD-032).

### 8.5 Norepinephrine
- All 20 audit rows rejected (17 NO_MATCH, 1 UNVERIFIABLE, 2 CONDITION_REJECTED). Re-fetched
  NCT03567447, NCT02897063, NCT03173781 — all droxidopa. The former label came from
  NCT05669170 (methylphenidate, posted 2022-12-30). Absent from the 90 pool because it has no
  accepted pre-cutoff trial.
- The claim that norepinephrine does not cross the blood–brain barrier is **UNVERIFIED** here
  (no retrieved source states it).
- **Verdict:** REJECTS — artefact; the noradrenergic hypothesis is represented by Droxidopa (§7).

### 8.6 Dopamine
- All 20 audit rows rejected; re-fetched NCT00105508 (sarizotan), NCT01264861 (safinamide),
  NCT00666653 (pramipexole). The six former post-cutoff label trials test other agents or cell
  / gene therapies. ChEMBL lists one mechanism target (ADRB1); its 0.400 molecular score is
  pathway overlap only.
- BBB: two low-tier sources state it in passing (PMID 4059691, 1985; PMID 20213574, 2010).
- **Verdict:** REJECTS — artefact.

### 8.7 Propranolol
- **Why shortlisted (previously undocumented):** in the contaminated 141 pool it had label 1
  and max_phase_rank 5, the latter from registry study NCT02670161, whose free text lists
  propranolol only under **migraine**. Gate 2 correctly marks it UNVERIFIABLE.
- **Genuine trial:** NCT07113015, propranolol vs amantadine for PD tremor, posted 2025-08-08,
  MATCHED. No posted results; the registry summary's outcome statement is unreviewed.
- **Evidence (symptomatic tremor):** Koller WC, Herbster G. *Arch Neurol* 1987 · PMID 3619710 ·
  doi:10.1001/archneur.1987.00520210023013 — double-blind crossover, n=10; resting-tremor
  amplitude −70%. van der Heide A, et al. *Ann Neurol* 2025 · PMID 39707791 ·
  doi:10.1002/ana.27159 — placebo-controlled crossover, single 40 mg dose, tremor power
  reduced (p = 0.02). Pirker W, et al. *J Parkinsons Dis* 2023 · PMID 36847017 — narrative
  review: may be considered as an adjunct.
- **Contradictory:** observational MAs associate propranolol use with higher PD risk
  (PMID 35718329, aRR 1.91; PMID 40200766, RR 2.36), the latter attributing it to protopathic
  bias (prescribed for tremor) and confounding.
- **Verdict:** SUPPORTS a symptomatic anti-tremor adjunct role only. Not evaluable by the
  pipeline: no accepted pre-cutoff trial (TD-027).
- **Status PARTIAL** because efficacy rests on n=10 and n=27 crossover studies, a 1966 Lancet
  paper (PMID 4159007) has no abstract, and no publication of NCT07113015 was searched.
- **2026-10-13 update:** PubMed searched for `NCT07113015` → **0 records** (esearch, HTTP 200).
  The small crossover samples are a property of the evidence (reflected in the verdict), not
  a verification gap. Status stays **PARTIAL** for one reason only: the content of PMID
  4159007 (1966, no abstract in PubMed) has not been read.

### 8.8 Cross-cutting findings
1. Gate 2 verifies identity, not role or therapeutic intent (active comparator, co-medication,
   background therapy, anaesthesia) — TD-023, E-014.
2. The pool cannot evaluate compounds first trialled after the cutoff — TD-027.
3. The literature dimension is truncated, recency-ordered and not cutoff-bounded — TD-021.
4. The safety dimension missed a documented cardiac signal — TD-022.
5. No candidate verified here supports a disease-modification claim for Parkinson's disease.

### 8.9 Droxidopa — literature credibility addendum to §7 (2026-10-13)
The new diagnostic agent 10a (`scripts/literature_credibility_agent.py`, not in VPS) was run
on the same 26 PMIDs (one batched PubMed efetch, 26/26 returned; XML saved to
`data/cache/pubmed_efetch_droxidopa.xml`; report `data/literature_credibility_droxidopa.json`).
Design comes only from PubMed PublicationType and population only from MeSH check tags.
- **Tiers:** A 0 · B 1 · C 16 · D 1 · unknown design 8. The single human tier-B paper is an
  observational prescription-trend study (PMID 39441810, 2024, post-cutoff).
- **Pre-cutoff (8 papers):** all tier C (5 narrative reviews, 3 case-report-tagged papers).
  PMID 31517701 is tagged "Case Reports" but its abstract reports 101 patients; the agent
  flags the conflict and keeps PubMed's tag.
- Confirms §7 independently: the stage-04 sample contains **no** randomised or controlled
  droxidopa trial. Status of §7 unchanged: **PARTIAL** (TD-021 owner decision).

## 9. Label-trial role audit (2026-10-13)

Question: is each **post-cutoff trial that makes a compound positive** actually a test of
that compound for Parkinson's? All 24 label-defining trials of the 17 positives were
re-fetched from ClinicalTrials.gov v2 (24 requests, all HTTP 200) and classified by the
diagnostic annotator `scripts/trial_role.py` (deterministic rules, evidence recorded per
verdict; **not** wired into stage 03; no label was changed).

| Verdict | Trials | Compounds |
|---|---|---|
| THERAPEUTIC_TEST | 17 | Acetylcysteine, Atomoxetine, Donepezil ×2, Galantamine†, Levetiracetam (AGB101), Melatonin, Methylphenidate, Mirabegron, Quetiapine, Rifaximin, Terazosin ×5†, Varenicline |
| PROCEDURAL_CONTEXT | 2 | **Dexmedetomidine** (NCT05376761, EC50 during DBS implantation), **Remifentanil** (NCT06658132, general-anaesthesia regimen for DBS surgery; registry purpose says TREATMENT) |
| CO_ADMINISTERED | 1 | **Clozapine** (NCT07085195: actuator drug of a chemogenetic gene therapy) |
| PROCEDURE_DELIVERED | 3 | **Lidocaine** (NCT06319625, NCT06370195, NCT06301724: stellate-ganglion block) |
| UNDETERMINED | 1 | **Pyridostigmine** (NCT05603715: single arm typed OTHER; title reads as a genuine treatment trial) |

† Galantamine NCT07284290 and two Terazosin trials have primary purpose BASIC_SCIENCE
(mechanistic studies), reported but not used to change the verdict.

**Five of 17 positives have no trial classified THERAPEUTIC_TEST.** Confirmed non-repurposing:
Dexmedetomidine, Remifentanil (procedural) and Clozapine (gene-therapy actuator). Ambiguous:
Lidocaine (the block procedure carries the intent). Undetermined: Pyridostigmine.

Sensitivity only (labels NOT changed; `data/vps_scores_v2.csv`; AUROC / AUPRC):

| Scenario | Positives | VPS_equal (4d) | VPS_equal_5d |
|---|---|---|---|
| As persisted | 17 | 0.689 / 0.412 | 0.747 / 0.479 |
| Dexmedetomidine, Remifentanil → 0 | 15 | 0.711 / 0.354 | 0.773 / 0.435 |
| + Clozapine → 0 | 14 | 0.724 / 0.358 | 0.781 / 0.439 |
| + Lidocaine → 0 | 13 | 0.731 / 0.360 | 0.770 / 0.423 |

AUROC rises and AUPRC falls, so the contamination does not bias the result in one direction;
it is a ground-truth validity problem. Redefining labels by trial role is an owner decision
(TD-032).

### 9.1 Per-label adjudication against the proposed TD-032 rule (2026-10-14)

Proposed rule: *a positive requires ≥1 post-cutoff trial that therapeutically tests the
compound in Parkinson's disease.* Evidence: the 24 registry records of §9 (no new requests),
annotator verdicts plus manual reading of arms, purpose and primary outcomes. A label is
CONFIRMED if any one of its trials qualifies. **No label was changed.**

| Compound | Decisive trial(s) | Status | Basis |
|---|---|---|---|
| Acetylcysteine | NCT07093944 | CONFIRMED | placebo-controlled RCT in PD |
| Atomoxetine | NCT07316296 | CONFIRMED | freezing of gait in PD |
| Donepezil | NCT05709301 (+NCT06903910) | CONFIRMED | RCT for PD-MCI |
| Levetiracetam | NCT05824728 | CONFIRMED | AGB101 (low-dose levetiracetam) for PD psychosis |
| Melatonin | NCT07375693 | CONFIRMED | double-blind placebo RCT in PD; purpose SUPPORTIVE_CARE, biomarker (MDA/GSH) endpoint |
| Methylphenidate | NCT05669170 | CONFIRMED | apathy in PD vs placebo |
| Mirabegron | NCT07187466 | CONFIRMED | urinary symptoms in PD |
| Quetiapine | NCT05590637 | CONFIRMED | head-to-head antipsychotics, PD psychosis / DLB |
| Rifaximin | NCT04730245 | CONFIRMED | motor complications of PD |
| Terazosin | NCT05109364, NCT05855577, NCT07207057 (+2 BASIC_SCIENCE) | CONFIRMED | treatment trials in PD |
| Varenicline | NCT06679374 | CONFIRMED | falls in PD |
| Pyridostigmine | NCT05603715 | CONFIRMED (manual) | annotator UNDETERMINED only because the single arm is typed OTHER; open-label, sole intervention, purpose TREATMENT, outcome = bowel movements in PD constipation |
| Dexmedetomidine | NCT05376761 | REJECTED | EC50 study during DBS implantation (anaesthesia) |
| Remifentanil | NCT06658132 | REJECTED | general-anaesthesia regimen for DBS surgery |
| Clozapine | NCT07085195 | REJECTED | actuator of a chemogenetic gene therapy; the therapy under test is the gene construct |
| Lidocaine | NCT06301724, NCT06319625, NCT06370195 | UNRESOLVED | all stellate-ganglion blocks: the drug is the agent but the procedure carries the intent; rule wording does not decide |
| Galantamine | NCT07284290 | UNRESOLVED | **new finding** (§9 counted it THERAPEUTIC_TEST): BASIC_SCIENCE, non-randomised, DLB/PDD population; galantamine given only in an 8-week open pre-post sub-cohort (n≈20) of a cross-sectional mechanism study |

Totals: 12 confirmed, 3 rejected, 2 unresolved. "Therapeutically tests" is read as treating
PD or a PD symptom; trials of non-motor symptoms (constipation, urinary, apathy) count.

**Impact (in memory; equal-weight scores do not depend on labels; 2000-resample paired
bootstrap, seed 42, `bootstrap_auroc_ci.paired_bootstrap`):**

| Policy | n / pos | 4d AUROC / AUPRC | 5d AUROC / AUPRC | 5d − 4d AUROC [95% CI], P(>0) |
|---|---|---|---|---|
| P0 as persisted | 90 / 17 | 0.689 / 0.412 | 0.747 / 0.479 | +0.059 [−0.024, +0.146], 0.91 |
| P1 rejected → 0 | 90 / 14 | 0.724 / 0.358 | 0.781 / 0.439 | +0.058 [−0.038, +0.159], 0.87 |
| P1x rejected excluded | 87 / 14 | 0.729 / 0.389 | 0.787 / 0.460 | +0.058 [−0.042, +0.163], 0.87 |
| P2 P1 + Lidocaine → 0 | 90 / 13 | 0.731 / 0.360 | 0.770 / 0.423 | +0.038 [−0.067, +0.143], 0.76 |
| P3 P2 + Galantamine → 0 | 90 / 12 | 0.749 / 0.369 | 0.765 / 0.420 | +0.016 [−0.086, +0.117], 0.61 |
| P3x rejected → 0; unresolved excluded | 88 / 12 | 0.751 / 0.371 | 0.772 / 0.429 | +0.021 [−0.078, +0.119], 0.64 |

5d AUROC 95% CIs span ≈0.60–0.89 in every row. No policy makes 5d significantly better than 4d.
The 5d advantage shrinks as the ambiguous labels are removed, so it partly depends on
contested labels. AUPRC falls partly because prevalence falls (AUPRC/prevalence: P0 2.53, P1 2.81).
The grid-searched variants depend on labels and are not re-estimated here; they need a stage-06 rerun.

**Applied 2026-10-14 (owner decision P1):** the three REJECTED labels are now 0 through `data/label_role_exclusions.csv`. The two UNRESOLVED labels stay positive by owner decision. Persisted rerun: 14/90 positives, AUROC 4d 0.724 / 5d 0.781. Equal-weight scores and ranks are unchanged, so the §6 ranking order still holds, but its label column now reads 0 for those three compounds.

### 9.2 Label-policy audit of disputed labels (2026-10-15, no decision changed)

Re-verified from code and data: the effective positives are the compounds in
`ground_truth_postcutoff_clean.csv` (md5 unchanged since 2026-10-13, now pinned by a test) that
are in the 90-compound pool, after removing the 3 trial rows in `data/label_role_exclusions.csv`.
That gives 14/90, and recomputing from the files matches the persisted `label` column.
- Exclusions are keyed by `nct_id`, and a mismatched (nct_id, compound) raises an error.
- None of the 3 excluded compounds has another ground-truth trial, so none can come back as positive.
- Re-entry through a *new* qualifying trial is allowed by design (per-trial policy). It could
  only happen if stage 03 were rerun.

| Compound | Trial(s) | Therapeutic intent | Cutoff eligibility (first posted) | Evidence source | Effective label | Unresolved question |
|---|---|---|---|---|---|---|
| Dexmedetomidine | NCT05376761 | anaesthetic EC50 during DBS implantation | post | registry record 2026-10-13 | 0 (P1) | — |
| Remifentanil | NCT06658132 | anaesthesia regimen for DBS surgery | post | same | 0 (P1) | — |
| Clozapine | NCT07085195 | actuator of chemogenetic gene therapy | post | same | 0 (P1) | — |
| Lidocaine | NCT06301724, NCT06319625, NCT06370195 | stellate-ganglion block for PD symptoms; randomised, quadruple-blind vs the same procedure with saline | post | same | **1, CONFIRMED 2026-10-15 (D-011)** | — (caveat: co-injected vitamin B12; local action) |
| Galantamine | NCT07284290 | 8-wk open pre-post sub-cohort in a BASIC_SCIENCE study (DLB/PDD) | post | same | **1, unresolved** | Does a mechanistic sub-study count, and does a mixed DLB/PDD population count as PD? |
| Pyridostigmine | NCT05603715 | open-label treatment of PD constipation | post | same; annotator UNDETERMINED, manual CONFIRMED | 1 | Accepted by manual review only |
| Melatonin | NCT07375693 | placebo RCT, oxidative-stress biomarker endpoint | post | same | 1 | Do biomarker-only endpoints qualify? |

A negative under this definition means only that no qualifying trial was identified up to the
retrieval date. It is **not** evidence of inefficacy. The two unresolved labels stay positive by
the 2026-10-14 owner decision, which is not confirmed ground truth.

**Draft pre-specified label policy (for owner review; not applied):**
1. **Endpoint:** a PD-indication interventional trial first posted 2021-01-01 to **a fixed end
   date**, rather than the retrieval date.
2. **The compound must be an active agent tested for PD or a PD symptom.** Excluded roles:
   anaesthesia or procedural, comparator-only, background or co-administered actuator.
3. **Procedure-delivered drugs and BASIC_SCIENCE studies:** decide explicitly; recommended
   default is *unresolved → excluded from evaluation*, not positive.
4. **Pool:** state whether a pre-cutoff trial is required (TD-027 / TD-035).
5. **Record keeping:** every adjudication is recorded by trial ID with its evidence, and the
   rules are fixed before any metric is computed.

## 10. Current state of the Parkinson's case study (2026-10-15)

**Claim (D-001, endpoint frozen by D-010).** Among 90 compounds with a pre-2021 Parkinson's trial, an
equal-weight evidence score ranks the 14 compounds that received a further qualifying PD trial
(first posted on/after 2021-01-01 in the ClinicalTrials.gov snapshot queried 2026-10-05; latest
observed 2026-09-08) above chance. The study does **not** measure efficacy, does not
evaluate first-time repurposing (TD-035), and is not leakage-free (TD-033).

**Inputs as of this run.**
- Ground truth: unchanged (md5 `c83e30bb…`), with 3 role exclusions (TD-032 P1).
- Safety: stage 05 v2 (D-003).
- Unmeasured dimensions get the neutral rank 0.5 (D-004): 7 compounds for safety, 16 for molecular.
- Coverage: 69 compounds have all 5 dimensions measured, 19 have 4 and 2 have 3.

| Model (D-002) | Kind | AUROC [95% CI] | AUPRC |
|---|---|---|---|
| Equal-weight 4d | primary, unfitted | 0.700 [0.567, 0.834] | 0.358 |
| Equal-weight 5d (+ molecular) | primary, unfitted | 0.775 [0.656, 0.881] | 0.424 |
| 5d − 4d (paired bootstrap, n=2000, seed 42) | — | +0.075 [−0.025, +0.176]; **not significant** | — |
| Grid-searched 4d / 3d / 5d | in-sample (not performance) | 0.725 / 0.720 / 0.774 | — |
| Grid-searched 4d / 3d / 5d | held-out, mean of 20 repeated nested-CV splits [2.5–97.5%] | 0.574 [0.46, 0.68] / 0.571 [0.45, 0.65] / 0.648 [0.56, 0.73] | — |

The fitted models do not generalise better than the unfitted ones. Prevalence is 0.156.

**Top 10, equal-weight 5d** (label; dimensions measured):

| Rank | Compound | Label | Dimensions measured |
|---|---|---|---|
| 1 | Donepezil | 1 | 5 |
| 2 | Zonisamide | 0 | 5 |
| 3 | Quetiapine | 1 | 5 |
| 4 | Dexmedetomidine | 0 (TD-032 exclusion) | 5 |
| 5 | Lisuride | 0 | 3 |
| 6 | Melatonin | 1 | 5 |
| 7 | Droxidopa | 0 | 5 |
| 8 | Methylphenidate | 1 | 5 |
| 9 | Lidocaine | 1 (unresolved) | 5 |
| 10 | Domperidone | 0 | 4 |

The case-study verdicts in §7–§9 concern evidence and trial records, not scores. They remain valid.
§6's ranking table is historical (17-positive labels, v1 safety).

**What would change the conclusion.**
- A fixed label window.
- Cutoff-bounded literature, which needs re-retrieval (D-006).
- Historical safety labels and Open Targets snapshots, which are not available (B-001).
- A decision on Lidocaine and Galantamine.

With 14 positives, no comparison between models is statistically supported.

### 10.1 Endpoint, label decisions and robustness (2026-10-15)

- **Endpoint (D-010, frozen):** continued clinical investigation. Positive = at least one
  Gate-2-matched, study-type-filtered, PD-condition interventional trial first posted on or after
  2021-01-01 in the ClinicalTrials.gov v2 snapshot queried 2026-10-05, excluding
  `data/label_role_exclusions.csv`. This is **not therapeutic efficacy**. First-time
  repurposing is a separate question (RQ-2, D-013) and is not evaluated here.
- **Lidocaine: confirmed (D-011).** Its three trials are placebo-controlled against the same
  procedure, so the drug is the tested agent for a PD symptom.
- **Galantamine: unresolved (D-011).** It comes from a basic-science sub-study in a pooled
  DLB/PDD population. Its label stays 1 by owner decision. Setting it to 0 gives
  4d 0.728 / 5d 0.781, and 5d−4d +0.053 [−0.052, +0.152]; no conclusion changes.
- **Dependence on dimensions that are not cutoff-bounded (D-012)**, unfitted equal-weight AUROC [95% CI]:

  | Dimensions | AUROC [95% CI] |
  |---|---|
  | All 5 | 0.775 [0.656, 0.881] |
  | Without literature | 0.740 [0.623, 0.855] |
  | Proximity + clinical only | 0.653 [0.474, 0.816] |

  The above-chance result does not need the literature dimension, but it does need safety and
  molecular, which use current data. The result is therefore a retrospective association with
  possible temporal leakage, not a validated forecast.
- **Molecular dimension:** integrated (5d is the primary model alongside 4d). Its added value
  is **not established**: +0.075 [−0.025, +0.176].

**Status: complete as a qualified retrospective case study.** Open items do not block this
claim, but they bound it:
- Galantamine is unresolved.
- Literature, safety and molecular are not cutoff-bounded (TD-033, B-001, B-002).
- With n = 14 positives, model comparisons are underpowered.

## 11. Verification-status ledger and replication check (2026-10-15)

`data/case_study_status.json` records, for the seven shortlisted candidates and Droxidopa:
the documented status (from §7–§9), trial roles, supporting vs null/opposing sources, the
trial-existence-vs-benefit distinction, and a fixed seven-item verification checklist. A test
checks that every identifier in it appears in this document. Shown on the dashboard's Case
Studies page.

**New verification (one PubMed efetch, 14/14 PMIDs of the curated claims, HTTP 200):** every
PMID resolved, and titles are consistent with the claims above. Two previously undated sources
now have verified years: PMID 35718329 (2022) and PMID 40200766 (2025). No record lists a
trial-registry ID.

**Replication (agent 10e, `docs/REPRODUCIBILITY_AGENT.md`):**
- The Propranolol tremor benefit is replicated by two small primary studies with no shared
  author (PMIDs 3619710, 39707791); independence is plausible, not proven.
- Melatonin's evidence is secondary only (overlapping meta-analyses).
- Donepezil's cognition finding rests on one primary RCT.
- The Droxidopa sample holds 4 primary records (3 case-report-tagged, 1 observational) and no
  randomised trial.

**Checklist result:**

| Case | Documented status | Checklist |
|---|---|---|
| Domperidone, Propofol, Norepinephrine, Dopamine | VERIFIED | all criteria met or not applicable |
| Donepezil | VERIFIED | overlap only partially checked (whether PMID 25224676 pools 22915447) |
| Melatonin | VERIFIED | safety not addressed |
| Propranolol | PARTIAL | PMID 4159007 unread |
| Droxidopa | PARTIAL | unrepresentative sample (TD-021) |

These gaps do not change the recorded verdicts.
