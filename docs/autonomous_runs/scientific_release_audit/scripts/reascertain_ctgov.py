"""Independent, read-only re-ascertainment of PD trials on ClinicalTrials.gov (audit tool; writes only to OUT).

Reuses stage 03's own gates (is_actually_pd, intervention_matcher.match_trial, the same alias map) so that any
difference from the saved files comes from search completeness or registry changes, not from new rules. Unlike stage
03, it follows nextPageToken (stage 03 requests pageSize=20 and never paginates) and records the total hit count.
Trials first posted after the label snapshot date (2026-10-05) are reported but excluded from the comparison.
"""
import csv, importlib.util, json, os, sys, time
import requests
R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, os.path.join(R, "scripts"))
os.chdir(R)
spec = importlib.util.spec_from_file_location("s03", os.path.join(R, "scripts/03_clinicaltrials_groundtruth.py"))
s03 = importlib.util.module_from_spec(spec); spec.loader.exec_module(s03)
import shutil, tempfile, molecular_agent as _ma          # never write the project's Open Targets cache: use a temporary copy
_tmp_cache = tempfile.mkdtemp(prefix="audit_ot_cache_"); shutil.copytree(os.path.join(R, "data/cache/molecular"), _tmp_cache, dirs_exist_ok=True)
s03.MolecularAgentConfig = lambda: _ma.MolecularAgentConfig(cache_dir=_tmp_cache)
im = s03.im
OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
SNAPSHOT = "2026-10-05"; CUTOFF = s03.CUTOFF_DATE
pool = [r["compound_name"] for r in csv.DictReader(open("data/vps_scores_v2.csv"))]
truncated = ["Benzocaine", "Carboplatin", "Cisplatin", "Docetaxel", "Dopamine", "Fluorouracil", "Methyldopa",
             "Norepinephrine", "Paclitaxel", "Pemetrexed", "Phenol"]
targets = pool + [c for c in truncated if c not in pool]
alias_map, rep = s03.build_alias_map(targets)

def search_all(drug):
    studies, token, pages, total = [], None, 0, None
    while True:
        p = {"query.intr": drug, "query.cond": '"Parkinson Disease"', "pageSize": 100, "countTotal": "true"}
        if token: p["pageToken"] = token
        for attempt in range(4):
            r = requests.get(s03.API_BASE, params=p, timeout=30)
            if r.status_code == 200: break
            time.sleep(2 * 2 ** attempt)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}", pages
        j = r.json(); pages += 1
        total = j.get("totalCount", total)
        studies += j.get("studies", [])
        token = j.get("nextPageToken")
        time.sleep(0.4)
        if not token: return studies, total, pages

rows, summary = [], []
for drug in targets:
    studies, total, pages = search_all(drug)
    if studies is None:
        summary.append({"compound": drug, "ok": False, "error": total}); print("FAIL", drug, total, flush=True); continue
    aliases = alias_map.get(drug) or im.build_alias_set(drug)
    for s in studies:
        pr = s.get("protocolSection", {}); idm = pr.get("identificationModule", {}); st = pr.get("statusModule", {})
        de = pr.get("designModule", {}); arms = pr.get("armsInterventionsModule") or {}
        ivs = arms.get("interventions")
        fp = st.get("studyFirstPostDateStruct", {}).get("date", "")
        pd_ok = s03.is_actually_pd(s)
        v = im.match_trial(drug, ivs, aliases) if pd_ok else {"outcome": "CONDITION_REJECTED", "qualifies": False, "reason": "", "matched_intervention": ""}
        rows.append({"compound": drug, "nct_id": idm.get("nctId"), "first_posted": fp, "study_type": de.get("studyType"),
                     "intervention_types": ";".join(i.get("type", "") for i in (ivs or [])),
                     "phases": ";".join(de.get("phases", []) or []), "status": st.get("overallStatus"),
                     "pd_condition": pd_ok, "outcome": v["outcome"], "qualifies": v["qualifies"],
                     "matched_intervention": v.get("matched_intervention") or "", "reason": (v.get("reason") or "")[:160],
                     "cohort": "pre" if fp and fp < CUTOFF else "post" if fp and fp <= SNAPSHOT else "after_snapshot" if fp else "no_date",
                     "arm_groups": json.dumps([{"label": a.get("label"), "type": a.get("type"), "interventions": a.get("interventionNames")} for a in (arms.get("armGroups") or [])])[:900],
                     "interventions": json.dumps([{"type": i.get("type"), "name": i.get("name"), "other": i.get("otherNames")} for i in (ivs or [])])[:900],
                     "conditions": "; ".join(pr.get("conditionsModule", {}).get("conditions", []) or [])[:200],
                     "title": (idm.get("briefTitle") or "")[:200]})
    summary.append({"compound": drug, "ok": True, "total_hits": total, "pages": pages, "returned": len(studies)})
    print(drug, total, pages, flush=True)
json.dump({"retrieved_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "endpoint": s03.API_BASE, "snapshot": SNAPSHOT,
           "alias_report": {k: v for k, v in rep.items() if not isinstance(v, (list, dict))}, "summary": summary}, open(os.path.join(OUT, "reascertain_summary.json"), "w"), indent=1)
with open(os.path.join(OUT, "reascertain_trials.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
