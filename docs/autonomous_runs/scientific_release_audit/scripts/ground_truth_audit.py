"""Row-level ground-truth audit of the 90 evaluated candidates (offline; reads saved files + the re-ascertainment CSV).

Independent label rule (as documented, D-010 + TD-032/P1): label = 1 iff the compound has >= 1 trial that is
(a) first posted on/after 2021-01-01 (and on/before the 2026-10-05 snapshot), (b) PD condition (stage-03 gate),
(c) intervention identity matched (stage-03 gate), (d) INTERVENTIONAL with a DRUG/BIOLOGICAL intervention
(filter_by_studytype), (e) not in data/label_role_exclusions.csv. Prior human decisions are taken from the
documented decision log (cited), never inferred.
"""
import csv, json, os, sys
R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
os.chdir(R)
REASC = sys.argv[1]; OUT = sys.argv[2]
T = list(csv.DictReader(open(os.path.join(REASC, "reascertain_trials.csv"))))
summ = {s["compound"]: s for s in json.load(open(os.path.join(REASC, "reascertain_summary.json")))["summary"]}
pool = {r["compound_name"]: r for r in csv.DictReader(open("data/vps_scores_v2.csv"))}
excl = {(r["compound_name"], r["nct_id"]): r for r in csv.DictReader(open("data/label_role_exclusions.csv"))}
post_saved = {}
for r in csv.DictReader(open("data/ground_truth_postcutoff_clean.csv")):
    post_saved.setdefault(r["compound_name"], []).append(r)
pre_saved = {}
for r in csv.DictReader(open("data/clinical_maturity_precutoff_clean.csv")):
    pre_saved.setdefault(r["compound_name"], []).append(r)
audit = list(csv.DictReader(open("data/clinicaltrials_match_audit.csv")))
s03_returned = {}
for r in audit:
    if r["nct_id"]: s03_returned[r["compound_name"]] = s03_returned.get(r["compound_name"], 0) + 1
review = list(csv.DictReader(open("data/clinical_review_worklist.csv")))
keep = lambda r: r["study_type"] == "INTERVENTIONAL" and any(t in ("DRUG", "BIOLOGICAL") for t in r["intervention_types"].split(";"))
# documented prior decisions on label trials (source: development_log/DECISIONS.md D-011; docs/CASE_STUDIES.md tables §9)
PRIOR = {"Lidocaine": ("CONFIRMED by owner (D-011, 2026-10-15)", "stellate-ganglion block: drug is the agent of the procedure; owner kept label 1"),
         "Galantamine": ("UNRESOLVED (D-011)", "only label trial NCT07284290 is a BASIC_SCIENCE open sub-cohort in DLB/PDD; drug in ACTIVE_COMPARATOR arm"),
         "Methylphenidate": ("CONFIRMED (CASE_STUDIES §9 table)", "arm typed ACTIVE_COMPARATOR but trial is methylphenidate vs placebo for apathy"),
         "Mirabegron": ("CONFIRMED (CASE_STUDIES §9 table)", "comparative trial; mirabegron is a treatment arm"),
         "Quetiapine": ("CONFIRMED (CASE_STUDIES §9 table)", "head-to-head antipsychotics; quetiapine is a treatment arm"),
         "Rifaximin": ("CONFIRMED (CASE_STUDIES §9 table)", "rifaximin is one component of a microbiota-modification regimen (enema + rifaximin + PEG); combination role not separately adjudicated"),
         "Clozapine": ("EXCLUDED by owner P1 (TD-032, 2026-10-14)", "clozapine actuates a chemogenetic gene therapy"),
         "Dexmedetomidine": ("EXCLUDED by owner P1 (TD-032, 2026-10-14)", "anaesthetic EC50 study during DBS implantation"),
         "Remifentanil": ("EXCLUDED by owner P1 (TD-032, 2026-10-14)", "general-anaesthesia regimen for DBS surgery")}
rows = []
for c in sorted(pool):
    mine = [r for r in T if r["compound"] == c]
    post_q = [r for r in mine if r["qualifies"] == "True" and r["cohort"] == "post" and keep(r)]
    post_lab = [r for r in post_q if (c, r["nct_id"]) not in excl]
    post_drop_type = [r for r in mine if r["qualifies"] == "True" and r["cohort"] == "post" and not keep(r)]
    post_unver = [r for r in mine if r["cohort"] == "post" and r["outcome"] == "UNVERIFIABLE"]
    pre_q = [r for r in mine if r["qualifies"] == "True" and r["cohort"] == "pre" and keep(r)]
    lab_saved = int(float(pool[c]["label"])); lab_ind = int(bool(post_lab))
    saved_post_ids = sorted(r["nct_id"] for r in post_saved.get(c, []))
    reasc_post_ids = sorted(r["nct_id"] for r in post_q)
    flags = []
    if post_drop_type:
        interventional_supp = [r for r in post_drop_type if r["study_type"] == "INTERVENTIONAL" and "DIETARY_SUPPLEMENT" in r["intervention_types"]]
        if interventional_supp and lab_ind == 0:
            flags.append("LABEL_DEPENDS_ON_INTERVENTION_TYPE_FIELD")
    if any(r["cohort"] == "post" and r["outcome"] == "UNVERIFIABLE" and r["study_type"] == "INTERVENTIONAL" for r in mine) and lab_ind == 0:
        flags.append("UNVERIFIABLE_INTERVENTIONAL_POST_TRIAL")
    if s03_returned.get(c, 0) >= 20: flags.append("STAGE03_SEARCH_TRUNCATED_AT_20")
    prior = PRIOR.get(c, ("", ""))
    if c == "Lithium": status = "DISPUTED (candidate correction 0->1; owner decision)"
    elif "UNRESOLVED" in prior[0]: status = "UNRESOLVED (owner)"
    elif lab_saved == lab_ind and lab_ind == 1: status = "CONFIRMED positive"
    elif lab_saved == lab_ind: status = "CONFIRMED negative (no qualifying trial identified under the ascertainment rules)"
    else: status = "MISMATCH"
    rows.append({"compound": c, "label_saved": lab_saved, "label_independent": lab_ind, "status": status,
                 "prior_decision": prior[0], "prior_note": prior[1],
                 "post_label_trials": ";".join(f"{r['nct_id']}({r['first_posted']})" for r in post_lab),
                 "post_role_excluded": ";".join(r["nct_id"] for r in post_q if (c, r["nct_id"]) in excl),
                 "post_dropped_by_type_filter": ";".join(f"{r['nct_id']}[{r['study_type']}/{r['intervention_types']}]" for r in post_drop_type),
                 "post_unverifiable": ";".join(f"{r['nct_id']}[{r['study_type']}]" for r in post_unver),
                 "post_saved_equals_reascertained": saved_post_ids == reasc_post_ids,
                 "pre_trials_saved": len(pre_saved.get(c, [])), "pre_trials_reascertained": len(pre_q),
                 "pre_extra_found": ";".join(sorted({r["nct_id"] for r in pre_q} - {r["nct_id"] for r in pre_saved.get(c, [])})),
                 "registry_hits_live": (summ.get(c) or {}).get("total_hits"), "stage03_rows": s03_returned.get(c, 0),
                 "retrieval_ok": (summ.get(c) or {}).get("ok"),
                 "open_feature_review_links": sum(1 for r in review if r["compound"] == c and r["status"].startswith("UNRESOLVED")),
                 "flags": ";".join(flags)})
with open(os.path.join(OUT, "ground_truth_row_audit.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
import collections
print(collections.Counter(r["status"] for r in rows)); print("saved positives", sum(r["label_saved"] for r in rows), "independent", sum(r["label_independent"] for r in rows))
print("flags", collections.Counter(f for r in rows for f in r["flags"].split(";") if f))
print("post sets equal for all:", all(r["post_saved_equals_reascertained"] for r in rows))
