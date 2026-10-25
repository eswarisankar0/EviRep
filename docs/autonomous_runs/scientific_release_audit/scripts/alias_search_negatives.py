"""Read-only: for every negative candidate, search ClinicalTrials.gov by each verified alias (ChEMBL synonym / trade name
from stage 03's own alias map) and apply stage 03's own gates; report post-cutoff qualifying trials not already linked."""
import csv, importlib.util, json, os, sys, time, requests
R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, os.path.join(R, "scripts")); os.chdir(R)
spec = importlib.util.spec_from_file_location("s03", "scripts/03_clinicaltrials_groundtruth.py"); s03 = importlib.util.module_from_spec(spec); spec.loader.exec_module(s03)
import shutil, tempfile, molecular_agent as _ma          # never write the project's Open Targets cache: use a temporary copy
_tmp_cache = tempfile.mkdtemp(prefix="audit_ot_cache_"); shutil.copytree(os.path.join(R, "data/cache/molecular"), _tmp_cache, dirs_exist_ok=True)
s03.MolecularAgentConfig = lambda: _ma.MolecularAgentConfig(cache_dir=_tmp_cache)
OUT = sys.argv[1]
neg = [r["compound_name"] for r in csv.DictReader(open("data/vps_scores_v2.csv")) if float(r["label"]) == 0]
before = len(os.listdir("data/cache/molecular"))
pool_all = [r["compound_name"] for r in csv.DictReader(open("data/vps_scores_v2.csv"))]
amap, rep = s03.build_alias_map(pool_all)          # same batch as the cohort map -> served from the existing cache
assert len(os.listdir("data/cache/molecular")) == before, "alias map wrote to the project cache"  # guard kept
known = {(r["compound_name"], r["nct_id"]) for f in ("data/clinicaltrials_match_audit.csv",) for r in csv.DictReader(open(f))}
found, n_req = [], 0
for c in neg:
    aliases = amap.get(c) or s03.im.build_alias_set(c)
    names = sorted({d["alias"] for d in aliases if d["source"] != "compound_name"})[:12]
    for a in names:
        r = requests.get(s03.API_BASE, params={"query.intr": a, "query.cond": '"Parkinson Disease"', "pageSize": 100, "filter.advanced": "AREA[StudyFirstPostDate]RANGE[2021-01-01,2026-10-05]"}, timeout=30); n_req += 1
        time.sleep(0.4)
        if r.status_code != 200: found.append({"compound": c, "alias": a, "error": r.status_code}); continue
        for s in r.json().get("studies", []):
            nct = s["protocolSection"]["identificationModule"]["nctId"]
            if (c, nct) in known or not s03.is_actually_pd(s): continue
            ivs = (s["protocolSection"].get("armsInterventionsModule") or {}).get("interventions")
            v = s03.im.match_trial(c, ivs, aliases)
            found.append({"compound": c, "alias": a, "nct_id": nct, "outcome": v["outcome"], "qualifies": v["qualifies"],
                          "study_type": s["protocolSection"]["designModule"].get("studyType"),
                          "types": ";".join(i.get("type", "") for i in (ivs or [])),
                          "first_posted": s["protocolSection"]["statusModule"]["studyFirstPostDateStruct"]["date"],
                          "title": s["protocolSection"]["identificationModule"].get("briefTitle", "")[:120]})
json.dump({"requests": n_req, "negatives": len(neg), "alias_report": {k: v for k, v in rep.items() if not isinstance(v, (list, dict))}, "new_links": found}, open(os.path.join(OUT, "alias_search_negatives.json"), "w"), indent=1)
print(n_req, "requests;", sum(1 for f in found if f.get("qualifies")), "new qualifying links;", len(found), "new PD links total")
for f in found:
    if f.get("qualifies") or f.get("error"): print(f)
