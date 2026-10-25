"""Build TRIAL_ROLE_ADJUDICATION.csv for all 195 pre-cutoff feature links (final audit 2026-10-22).
Sources, in precedence order: (1) D-020 human adjudication (data/feature_trial_roles_td038.csv, 35 links);
(2) this audit's per-link adjudication of the 58 links that were flagged (28) or carried a non-therapeutic automated
role (30), from the registry fields cached in data/clinical_role_review.csv / data/cache/ctgov_precutoff_trials.json;
(3) remaining links: automated and structural readings both THERAPEUTIC_TEST, accepted (residual risk: TD-043).
P1 criterion (approved 2026-10-14 for labels, DECISIONS D-011): the compound must be an active agent tested for PD or a
PD symptom; procedural/anaesthesia, comparator-only, auxiliary (interaction probe, premedication, QT positive control,
immunosuppression) and background-othername roles do not qualify. D-020 rec. 3/4: fixed combinations and the withdrawn
trial are retained. AMBIGUOUS links are retained (no forced exclusion) and listed for sensitivity."""
import os, sys
import pandas as pd
ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
OUT = sys.argv[2]
Q, NQ, AMB = "YES", "NO", "AMBIGUOUS"
A = {  # (nct, compound): (final_role, p1, confidence, evidence)
 ("NCT00608231","Dexmedetomidine"):("PROCEDURAL_CONTEXT",NQ,"high","sedation during microelectrode recording in DBS surgery; PD/ET/dystonia surgical groups vs saline"),
 ("NCT01721460","Dexmedetomidine"):("PROCEDURAL_CONTEXT",NQ,"high","arm 'Dexmedetomidine during MER': effect on STN recordings during DBS surgery"),
 ("NCT01789385","Dexmedetomidine"):("PROCEDURAL_CONTEXT",NQ,"high","title 'Anesthesia for Deep Brain Stimulation'; primary outcome sedation"),
 ("NCT02236260","Lidocaine"):("PROCEDURAL_CONTEXT",NQ,"high","local anaesthesia in both arms of a DBS-surgery acupuncture trial; electroacupuncture is the tested intervention"),
 ("NCT04164758","Quetiapine"):("COMPARATOR_ONLY",NQ,"high","ACTIVE_COMPARATOR arm to pimavanserin (EXPERIMENTAL) for PD neuropsychiatric symptoms"),
 ("NCT00605683","Lisuride"):("BACKGROUND_OTHERNAME",NQ,"high","listed only among background dopamine-agonist otherNames of 'Safinamide (as add-on therapy)'"),
 ("NCT01340885","Atomoxetine"):("THERAPEUTIC_TEST",Q,"medium","Strattera = atomoxetine (brand); own arm vs placebo arm for cognitive decline in PD (registry types it ACTIVE_COMPARATOR, but a placebo arm exists)"),
 ("NCT02174250","Rifampicin"):("AUXILIARY_AGENT",NQ,"high","CYP3A inducer in an istradefylline interaction study in healthy volunteers"),
 ("NCT00001365","Dextromethorphan"):("THERAPEUTIC_TEST",Q,"high","sole intervention; title 'Dextromethorphan for the Treatment of Parkinson's Disease'"),
 ("NCT00004826","Clozapine"):("THERAPEUTIC_TEST",Q,"high","sole intervention; psychosis in idiopathic PD"),
 ("NCT00006077","Domperidone"):("AUXILIARY_AGENT",NQ,"medium","'Levodopa and Domperidone' co-medication in a trial of NS2330 (title names NS2330 as the investigated drug)"),
 ("NCT00030979","Donepezil"):("THERAPEUTIC_TEST",Q,"high","sole intervention; dementia in PD"),
 ("NCT00043849","Quetiapine"):("THERAPEUTIC_TEST",Q,"high","sole intervention; agitation/psychosis in dementia/parkinsonism"),
 ("NCT00063193","Minocycline"):("THERAPEUTIC_TEST",Q,"high","minocycline and creatine both listed as tested interventions in the NINDS PD neuroprotection trial"),
 ("NCT00089622","Lisuride"):("THERAPEUTIC_TEST",Q,"high","title 'Lisuride Patch to Treat Parkinson's Disease'; IV levodopa is a second intervention"),
 ("NCT00103597","Domperidone"):("THERAPEUTIC_TEST",Q,"medium","domperidone listed with fludrocortisone and conservative measures as therapeutic interventions for orthostatic hypotension in PD/MSA"),
 ("NCT00160576","Levetiracetam"):("THERAPEUTIC_TEST",Q,"high","sole intervention; dyskinesias in PD"),
 ("NCT00211588","Galantamine"):("THERAPEUTIC_TEST",Q,"high","sole intervention; executive function in PD"),
 ("NCT00286949","Atomoxetine"):("THERAPEUTIC_TEST",Q,"high","sole intervention; executive dysfunction in PD"),
 ("NCT00296946","Ipratropium bromide"):("THERAPEUTIC_TEST",Q,"high","sole intervention; drooling in PD"),
 ("NCT00296959","Topiramate"):("THERAPEUTIC_TEST",Q,"high","sole intervention; levodopa-induced dyskinesia"),
 ("NCT00305331","Domperidone"):("THERAPEUTIC_TEST",Q,"high","sole intervention; agonist-induced oedema in PD"),
 ("NCT00307450","Levetiracetam"):("THERAPEUTIC_TEST",Q,"high","levetiracetam vs placebo on levodopa-induced dyskinesia"),
 ("NCT00393562","Methylphenidate"):("THERAPEUTIC_TEST",Q,"high","modafinil vs methylphenidate comparison for daytime sleepiness in PD; both tested"),
 ("NCT00408915","Lisuride"):("THERAPEUTIC_TEST",Q,"high","sole intervention; subcutaneous lisuride infusion in PD"),
 ("NCT00640952","Acamprosate"):("THERAPEUTIC_TEST",Q,"high","sole intervention; compulsive behaviours in PD"),
 ("NCT02066571","Droxidopa"):("THERAPEUTIC_TEST",Q,"high","droxidopa vs placebo crossover in PD"),
 ("NCT03773796","Nabilone"):("THERAPEUTIC_TEST",Q,"high","sole intervention; non-motor symptoms in PD"),
 ("NCT03187301","Moxifloxacin"):("AUXILIARY_AGENT",NQ,"high","positive control in a cardiac-safety (QT) study of APL-130277"),
 ("NCT01532115","Moxifloxacin"):("AUXILIARY_AGENT",NQ,"high","positive control in a cardiac repolarisation study of BIA 9-1067"),
 ("NCT00292227","Moxifloxacin"):("AUXILIARY_AGENT",NQ,"high","moxifloxacin infusion as QT positive control in a rotigotine cardiac study"),
 ("NCT04342273","Moxifloxacin"):("AUXILIARY_AGENT",NQ,"high","positive control in a thorough QT study of KW-6356"),
 ("NCT01789047","Topiramate"):("THERAPEUTIC_TEST",Q,"high","topiramate vs placebo as adjunct to amantadine for dyskinesia (automated CO_ADMINISTERED misfire, TD-043)"),
 ("NCT00794313","Topiramate"):("THERAPEUTIC_TEST",Q,"high","amantadine+topiramate vs amantadine vs placebo: antidyskinetic effect of topiramate tested"),
 ("NCT02305017","Acetaminophen"):("AUXILIARY_AGENT",NQ,"high","paracetamol in an opicapone pharmacokinetic study in healthy volunteers"),
 ("NCT01504178","Duloxetine"):("THERAPEUTIC_TEST",Q,"medium","duloxetine EXPERIMENTAL arm on pain perception in PD (BASIC_SCIENCE; same reasoning as Galantamine label)"),
 ("NCT02601586","Oxycodone"):("THERAPEUTIC_TEST",Q,"high","PR oxycodone vs levodopa vs placebo for central neuropathic pain in PD"),
 ("NCT01770145","Trimethobenzamide"):("AUXILIARY_AGENT",NQ,"high","antiemetic premedication with apomorphine (APOKYN) in a morning-akinesia trial"),
 ("NCT02373072","Trimethobenzamide"):("AUXILIARY_AGENT",NQ,"high","antiemetic with PF-06649751 in a phase-1 safety/PK study"),
 ("NCT02305030","Warfarin"):("AUXILIARY_AGENT",NQ,"high","opicapone-warfarin pharmacokinetic interaction study"),
 ("NCT02169440","Warfarin"):("AUXILIARY_AGENT",NQ,"high","BIA 9-1067 effect on warfarin PK/PD"),
 ("NCT02225548","Tadalafil"):("AMBIGUOUS",AMB,"low","single arm selegiline + tadalafil in PD with erectile dysfunction; registry does not state whether tadalafil or the combination's safety is tested"),
 ("NCT01536366","Repaglinide"):("AUXILIARY_AGENT",NQ,"high","BIA 9-1067 effect on repaglinide PK"),
 ("NCT02789592","Melatonin"):("THERAPEUTIC_TEST",Q,"high","melatonin PR vs clonazepam vs placebo for REM sleep behaviour disorder in PD"),
 ("NCT00070941","Escitalopram"):("COMPARATOR_ONLY",NQ,"high","ACTIVE_COMPARATOR to SAM-e (EXPERIMENTAL) for depression in PD"),
 ("NCT03022201","Domperidone"):("COMPARATOR_ONLY",NQ,"high","ACTIVE_COMPARATOR to DA-9701 (EXPERIMENTAL) in PD"),
 ("NCT04459052","Acetylcysteine"):("THERAPEUTIC_TEST",Q,"medium","oral+IV NAC cohort vs waitlist control in PD, FDOPA PET outcome (primary purpose DIAGNOSTIC)"),
 ("NCT03115827","Droxidopa"):("THERAPEUTIC_TEST",Q,"high","droxidopa (+carbidopa) for action control in PD"),
 ("NCT00547911","Droxidopa"):("THERAPEUTIC_TEST",Q,"high","L-DOPS is the tested agent; carbidopa/entacapone augmentation"),
 ("NCT01950468","Ioflupane I 123"):("COMPARATOR_ONLY",NQ,"high","DaTscan ACTIVE_COMPARATOR to the investigational imaging agent NAV5001"),
}
r = pd.read_csv(os.path.join(ROOT, "data/clinical_role_review.csv"))
td = pd.read_csv(os.path.join(ROOT, "data/feature_trial_roles_td038.csv")).set_index(["nct_id", "compound_name"])
rows = []
for _, x in r.iterrows():
    k = (x.nct_id, x.compound)
    base = dict(nct_id=x.nct_id, compound_name=x.compound, phase=x.phase_in_feature, brief_title=x.brief_title,
                original_auto_role=x.auto_verdict, original_flags=x.review_flags if isinstance(x.review_flags, str) else "")
    if k in td.index:
        t = td.loc[k]
        p1 = {"YES": Q, "NO": NQ}.get(t.p1_qualifies, "RETAINED_" + str(t.p1_qualifies))
        rows.append({**base, "final_role": t.category, "p1_qualifies": p1, "confidence": "owner-proposed (D-020)",
                     "evidence": t.rationale, "source": "D-020 adjudication (2026-10-14)"})
    elif k in A:
        role, p1, conf, ev = A[k]
        rows.append({**base, "final_role": role, "p1_qualifies": p1, "confidence": conf, "evidence": "registry: " + ev,
                     "source": "final audit 2026-10-22 (registry record)"})
    else:
        assert x.auto_verdict == "THERAPEUTIC_TEST" and not isinstance(x.review_flags, str), k
        rows.append({**base, "final_role": "THERAPEUTIC_TEST", "p1_qualifies": Q, "confidence": "automated (auto+structural agree)",
                     "evidence": "automated: " + str(x.auto_evidence)[:160], "source": "automated, not individually reviewed"})
out = pd.DataFrame(rows)
missing = set(A) - set(zip(out.nct_id, out.compound_name))
assert not missing, missing
out.to_csv(os.path.join(OUT, "TRIAL_ROLE_ADJUDICATION.csv"), index=False)
excl = out[out.p1_qualifies == NQ][["nct_id", "compound_name"]]
excl.to_csv(os.path.join(OUT, "candidate_feature_role_exclusions.csv"), index=False)
print(len(out), "links;", out.p1_qualifies.value_counts().to_dict(), "| source", out.source.value_counts().to_dict())
print("exclusions:", len(excl))
