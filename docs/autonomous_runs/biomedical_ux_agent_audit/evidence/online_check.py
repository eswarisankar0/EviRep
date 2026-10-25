"""One small, read-only request per configured external source, through the project's own client code.
Nothing is written into the repository: caches/outputs go to an isolated scratch directory. No credential is read or printed."""
import importlib.util, json, os, sys, time, csv, hashlib, platform
from datetime import datetime, timezone
R = "/Users/thrisha/Drup_Rep_PF/EviRep"; OUT = sys.argv[1]; os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, R + "/scripts")
import requests
def load(name, rel):
    sp = importlib.util.spec_from_file_location(name, os.path.join(R, rel)); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
now = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
res = []
def rec(source, check, ok, **d):
    d = {"source": source, "check": check, "result": "PASS" if ok is True else "FAIL" if ok is False else ok, "utc": now(), **d}
    res.append(d); print(json.dumps(d)[:400], flush=True)
saf = {r["compound_name"]: r for r in csv.DictReader(open(R + "/data/safety_signal.csv"))}

# 1 PubMed E-utilities via 04p.retrieve (the stage's own code: 2 esearch + efetch), compared with the saved cache
try:
    p4 = load("p04p", "scripts/04p_literature_provenance.py")
    rec("PubMed E-utilities", "API key configured", "INFO", detail="NCBI_API_KEY " + ("set" if os.environ.get("NCBI_API_KEY") else "not set (anonymous rate limit, 3 req/s)"))
    s = requests.Session(); t0 = time.time()
    c = p4.retrieve(s, "Donepezil", sleep=lambda t: time.sleep(max(t, 0.4)))
    cached = p4.load_cache(R, "Donepezil")
    papers = {}
    for ch in c["efetch_xml"]: papers.update(p4.parse_articles(ch))
    rec("PubMed E-utilities", "retrieve('Donepezil') via scripts/04p_literature_provenance.py", bool(c["sample"]["idlist"]) and len(papers) > 0,
        endpoint=p4.NCBI_BASE, seconds=round(time.time() - t0, 1), sample_pmids=len(c["sample"]["idlist"]), bounded_count=c["bounded"].get("count"),
        bounded_pmids=len(c["bounded"]["idlist"]), parsed_records=len(papers), efetch_missing=len(c["efetch_missing"]),
        relevance=sum("donepezil" in (json.dumps(v).lower()) for v in papers.values()),
        cached_bounded_pmids=len(cached["bounded"]["idlist"]) if cached else None,
        bounded_identical_to_cache=(cached is not None and cached["bounded"]["idlist"] == c["bounded"]["idlist"]),
        note="cutoff-bounded (<=2020-12-31) PMIDs are expected to match the cache; the 30-paper recency sample may drift")
    json.dump({k: v for k, v in c.items() if k != "efetch_xml"}, open(os.path.join(OUT, "pubmed_donepezil.json"), "w"), indent=1)
    time.sleep(0.5)
    z = p4.esearch(s, '"zzqxnotacompound"[Title/Abstract] AND "Parkinson Disease"[MeSH Terms]', 30, sleep=lambda t: time.sleep(max(t, 0.4)))
    rec("PubMed E-utilities", "empty result is reported as zero records, not as evidence", z.get("count") in (0, "0") and not z["idlist"], count=z.get("count"))
except Exception as e:
    rec("PubMed E-utilities", "retrieve", False, error=f"{type(e).__name__}: {e}"[:300])

if os.environ.get('ONLY_RETRY'):
    pass
if not os.environ.get('ONLY_RETRY'):
  pass
# 2 ClinicalTrials.gov v2 via check_studytype.get_study_info (stage 03c code) + direct schema check
try:
    cs = load("cst", "scripts/check_studytype.py")
    st, it = cs.get_study_info("NCT02005029")
    rec("ClinicalTrials.gov API v2", "get_study_info('NCT02005029') via scripts/check_studytype.py", st == "INTERVENTIONAL" and bool(it), study_type=st, intervention_types=it,
        endpoint="https://clinicaltrials.gov/api/v2/studies/{nct}")
    r = requests.get("https://clinicaltrials.gov/api/v2/studies/NCT02005029", params={"fields": "protocolSection.identificationModule,protocolSection.statusModule"}, timeout=20)
    j = r.json(); idm = j["protocolSection"]["identificationModule"]
    saved = next((row for row in csv.DictReader(open(R + "/data/clinical_maturity_precutoff_clean.csv")) if row["nct_id"] == "NCT02005029"), {})
    rec("ClinicalTrials.gov API v2", "record matches the saved trial (id, first-posted date)", r.status_code == 200 and idm["nctId"] == "NCT02005029"
        and j["protocolSection"]["statusModule"]["studyFirstPostDateStruct"]["date"] == saved.get("first_posted"),
        http_status=r.status_code, title=idm.get("briefTitle", "")[:90], first_posted_live=j["protocolSection"]["statusModule"]["studyFirstPostDateStruct"]["date"],
        first_posted_saved=saved.get("first_posted"), compound_saved=saved.get("compound_name"))
    time.sleep(0.3)
    st2, it2 = cs.get_study_info("NCT00000000")
    rec("ClinicalTrials.gov API v2", "unknown NCT id is reported as an error, not a study", st2 == "ERROR", returned=st2, detail=str(it2)[:120])
except Exception as e:
    rec("ClinicalTrials.gov API v2", "study lookup", False, error=f"{type(e).__name__}: {e}"[:300])

# 3 openFDA drug label via 05_safety_signal.query_label
try:
    s5 = load("s05", "scripts/05_safety_signal.py")
    lab = s5.query_label("Donepezil")
    rec("openFDA drug label", "query_label('Donepezil') via scripts/05_safety_signal.py", lab is not None and "donepezil" in json.dumps(lab.get("openfda", {})).lower(),
        endpoint=s5.BASE, set_id_live=lab.get("set_id") if lab else None, effective_time_live=lab.get("effective_time") if lab else None,
        set_id_saved=saf["Donepezil"]["label_set_id"], effective_time_saved=saf["Donepezil"]["label_effective_time"],
        same_label_as_saved=bool(lab) and lab.get("set_id") == saf["Donepezil"]["label_set_id"])
    time.sleep(0.4)
    none = s5.query_label("Zzzqxnotadrug")
    rec("openFDA drug label", "no match (HTTP 404) is returned as 'no label', which stage 05 records as absent at source", none is None, returned=none)
except Exception as e:
    rec("openFDA drug label", "label query", False, error=f"{type(e).__name__}: {e}"[:300])

# 4 openFDA FAERS via safety_evidence_agent.fetch_faers (10f --fetch code), compared with the saved cache
try:
    sea = load("sea", "scripts/safety_evidence_agent.py")
    f = sea.fetch_faers("Donepezil", pause=0.4)
    codes = {k: v["http_status"] for k, v in f["responses"].items()}
    cpath = os.path.join(R, "data/cache/openfda_faers", sea.safe_name("Donepezil") + ".json")
    cached = json.load(open(cpath)) if os.path.exists(cpath) else None
    tot = lambda rr: ((rr.get("responses", {}).get("pre_cutoff", {}).get("body") or {}).get("meta", {}).get("results", {}).get("total"))
    rec("openFDA adverse events (FAERS)", "fetch_faers('Donepezil') via scripts/safety_evidence_agent.py", all(c == 200 for c in codes.values()),
        endpoint=sea.FAERS_URL, http_status=codes, pre_cutoff_reports_live=tot(f), pre_cutoff_reports_saved=tot(cached) if cached else None,
        saved_retrieved_utc=(cached or {}).get("retrieved_utc"), note="report counts by 2020 should be stable; totals since then grow")
    json.dump(f, open(os.path.join(OUT, "faers_donepezil.json"), "w"))
except Exception as e:
    rec("openFDA adverse events (FAERS)", "fetch", False, error=f"{type(e).__name__}: {e}"[:300])

# 5 DailyMed label history via 05h.history (writes only to the scratch root's cache)
try:
    h5 = load("h05", "scripts/05h_safety_label_history.py")
    os.makedirs(os.path.join(OUT, "data/cache/dailymed/history"), exist_ok=True)
    setid = saf["Donepezil"]["label_set_id"]
    h = h5.history(requests.Session(), OUT, setid, offline=False)
    hc = h5.history(None, R, setid, offline=True)
    rec("DailyMed SPL history", "history(setid of the saved Donepezil label) via scripts/05h_safety_label_history.py", bool(h),
        endpoint=h5.DM + "/services/v2/spls/{setid}/history.json", versions_live=len(h), versions_cached=len(hc),
        version_at_cutoff_live=str(h5.version_at(h))[:80], version_at_cutoff_cached=str(h5.version_at(hc))[:80],
        note="the project caches history forever; a newer live version count means the cache is older than the registry")
except Exception as e:
    rec("DailyMed SPL history", "history", False, error=f"{type(e).__name__}: {e}"[:300])

# 6 Open Targets Platform GraphQL via molecular_agent.OpenTargetsClient (cache disabled)
try:
    import molecular_agent as ma
    cl = ma.OpenTargetsClient(ma.MolecularAgentConfig(use_cache=False))
    d = cl.query("query($id:String!){ target(ensemblId:$id){ id approvedSymbol } meta { dataVersion { year month } } }", {"id": "ENSG00000087085"})
    rec("Open Targets Platform GraphQL", "target(ENSG00000087085) via scripts/molecular_agent.py OpenTargetsClient", (d.get("target") or {}).get("approvedSymbol") == "ACHE",
        endpoint=ma.OPENTARGETS_GRAPHQL_URL, symbol=(d.get("target") or {}).get("approvedSymbol"), data_version_live=d.get("meta", {}).get("dataVersion"),
        note="ACHE is Donepezil's target in the saved evidence; the dashboard records data version 26.09 for the saved run")
except Exception as e:
    rec("Open Targets Platform GraphQL", "query", False, error=f"{type(e).__name__}: {e}"[:300])

# 7 Semantic Scholar (stage 04; REFUSED in the UI): one anonymous lookup
try:
    r = requests.get("https://api.semanticscholar.org/graph/v1/paper/PMID:17557339", params={"fields": "title,year,externalIds"}, timeout=20)
    j = r.json() if r.headers.get("Content-Type", "").startswith("application/json") else {}
    rec("Semantic Scholar Graph API", "paper PMID:17557339 (anonymous)", True if r.status_code == 200 and j.get("externalIds", {}).get("PubMed") == "17557339" else ("BLOCKED" if r.status_code == 429 else False),
        http_status=r.status_code, title=str(j.get("title", ""))[:90], year=j.get("year"),
        note="no Semantic Scholar key is configured; anonymous requests are rate-limited (HTTP 429 is common)")
except Exception as e:
    rec("Semantic Scholar Graph API", "lookup", False, error=f"{type(e).__name__}: {e}"[:300])

# 8 Zenodo (Hetionet archive, stage 01): HEAD only - the 155 MB archive is not downloaded
try:
    g = load("g01", "scripts/01_get_pd_candidates.py") if False else None
    r = requests.head("https://zenodo.org/records/268568/files/dhimmel/hetionet-v1.0.0.zip", allow_redirects=True, timeout=30)
    rec("Zenodo (Hetionet v1.0 archive)", "HEAD of the configured archive URL (no download)", r.status_code == 200, http_status=r.status_code,
        content_length=r.headers.get("Content-Length"), note="reachability only; the local Hetionet snapshot is used by the pipeline")
except Exception as e:
    rec("Zenodo (Hetionet v1.0 archive)", "HEAD", False, error=f"{type(e).__name__}: {e}"[:300])

json.dump({"generated_utc": now(), "python": platform.python_version(), "requests": requests.__version__, "results": res}, open(os.path.join(OUT, "online_results.json"), "w"), indent=1)
