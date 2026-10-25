"""Biomedical UX acceptance (real Chrome via CDP -> isolated copy server :8799 -> real runner)."""
import os, json, time, re, subprocess, urllib.request, sys
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
C = os.path.join(S, "uxcopy"); URL = "http://127.0.0.1:8799/"; PY = os.path.join(R, "venv/bin/python")
res = []
def rec(n, ok, d=None):
    res.append({"check": n, "result": "PASS" if ok else "FAIL", "detail": d or {}}); print(("PASS " if ok else "FAIL ") + n + " :: " + json.dumps(d or {})[:260], flush=True)
def api(p): return json.load(urllib.request.urlopen(URL + p.lstrip("/"), timeout=20))
def ready(t=12):
    end = time.time() + t
    while time.time() < end:
        pump(0.2)
        try:
            if js("document.getElementById('main').getAttribute('aria-busy') === 'false'"): return True
        except Exception: pass
    return False
def go(h): js(f"location.hash = {json.dumps(h)}"); ready(); pump(0.4)
jsb = lambda e: js("{" + e + "}")
T = lambda: js("document.getElementById('main').innerText")
manifest = lambda: json.load(open(os.path.join(C, "data/run_manifest.json")))
ldir = os.path.join(C, "data/_runs/_ui_launches")
nlaunch = lambda: len([f for f in os.listdir(ldir) if f.endswith(".json")]) if os.path.isdir(ldir) else 0
cmd("Runtime.enable"); cmd("Page.enable"); cmd("Network.enable"); cmd("Log.enable")
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
h0, n0 = len(manifest()["history"]), nlaunch()
ver = cmd("Browser.getVersion")
t0 = time.time(); cmd("Page.navigate", url=URL); ready(); load_s = round(time.time() - t0, 2)

# --- navigation ---------------------------------------------------------------------------------
nav = js("[...document.querySelectorAll('#nav button')].map(b => [b.dataset.view, b.textContent])")
rec("primary navigation has exactly five sections in order", [v for v, _ in nav] == ["overview", "drugs", "evidence", "validation", "run"], {"nav": nav})
rec("root URL opens the researcher Overview", js("document.title") == "EviRep · Overview" and "What you are looking at" in T(), {"title": js("document.title"), "load_s": load_s})
for view, label in nav:
    js(f"document.querySelector('#nav button[data-view=\"{view}\"]').click()"); ready(); pump(0.3)
    ok = js(f"document.querySelector('#nav button[data-view=\"{view}\"]').getAttribute('aria-current') === 'page'") and js("location.hash") == "#" + view and label in js("document.title")
    rec(f"nav '{label}' opens its section and marks it current", ok, {"hash": js("location.hash"), "title": js("document.title")})
go("evidence")
tabs = js("[...document.querySelectorAll('.subnav a')].map(a => a.getAttribute('href'))")
okt = True
for h in tabs:
    js(f"document.querySelector('.subnav a[href=\"{h}\"]').click()"); ready(); pump(0.3)
    okt &= js(f"document.querySelector('.subnav a[href=\"{h}\"]').getAttribute('aria-current') === 'page'") and js("document.querySelector('#nav button[data-view=evidence]').getAttribute('aria-current')") == "page"
rec("Evidence sub-pages (evidence, mechanism, conflicts, review) open inside the Evidence section", okt and tabs == ["#evidence", "#mechanism", "#conflicts", "#review"], {"tabs": tabs})
old = {}
for h, sec in (("dashboard", "run"), ("live", "run"), ("technical", "run"), ("pipeline", "run"), ("agents", "run"), ("cases", "run"), ("agent/10b", "run"), ("compare", "drugs"), ("mechanism", "evidence"), ("overview", "overview")):
    go(h); old[h] = js("(document.querySelector('#nav button[aria-current=page]')||{}).dataset.view")
    old[h] = old[h] == sec
rec("every older address still opens, inside its new section", all(old.values()), old)
cmd("Page.navigate", url=URL + "#drugs/Donepezil"); ready(); pump(0.5)
deep = "Why Donepezil ranks 1 of 90" in T()
go("validation"); cmd("Page.navigateToHistoryEntry", entryId=cmd("Page.getNavigationHistory")["entries"][-2]["id"]); ready(); pump(0.5)
back = js("location.hash") == "#drugs/Donepezil" and "Why Donepezil" in T()
cmd("Page.reload"); ready(); pump(0.5)
rec("deep link, back and refresh keep the candidate page", deep and back and "Why Donepezil" in T(), {"deep": deep, "back": back})

# --- overview -------------------------------------------------------------------------------------
go("overview")
L = api("/api/live")
heads = js("[...document.querySelectorAll('#main h2')].map(h => h.textContent)")
need = ["What you are looking at", "How current and reliable is it?", "Strongest research signals", "Evidence coverage", "What needs attention", "What you can do next"]
rec("Overview answers what / how reliable / what needs attention / what next", all(n in heads for n in need), {"headings": heads})
hl = {"CURRENT": "Current against recorded inputs", "VERIFIED_WITH_GAPS": "Current against recorded inputs, with unverifiable inputs", "STALE": "Inputs changed — rerun needed", "FAILED": "Last run failed; previous results retained", "UNKNOWN": "Freshness could not be verified", "INCOMPLETE": "Some stages have never run", "RUNNING": "A run is in progress"}[L["overall"]["state"]]
first = js("document.querySelector('ul.checks li').innerText")
rec("Overview results line equals the tracker state and is not shown as a tick unless fully current", hl in first and (("✓" in first) == (L["overall"]["state"] == "CURRENT")), {"state": L["overall"]["state"], "line": first[:150]})
nd = [x["source"] for x in L["sources"] if not x["retrieved_utc"]]
rec("source line names the sources without a recorded retrieval date", all(n in T() for n in nd), {"not_recorded": nd})
rec("28 trial links awaiting human review shown with the review link", f"{L['science']['reviews_awaiting']} trial–drug links need a human decision" in T() and js("!!document.querySelector('#main a[href=\"#review\"]')"), {"n": L["science"]["reviews_awaiting"]})
RK = api("/api/ranking")["rows"]
bars = js("[...document.querySelectorAll('#main .chart .bar[data-key]')].slice(0,10).map(g => g.dataset.key)")
rec("Overview signal chart = approved top 10 in rank order", bars == [r["compound"] for r in RK[:10]], {"bars": bars[:3]})
js("document.querySelector('#main .chart .bar[data-key]').dispatchEvent(new MouseEvent('click', {bubbles: true}))"); ready(); pump(0.4)
rec("selecting a signal bar opens that candidate", js("location.hash") == "#drugs/" + RK[0]["compound"], {"hash": js("location.hash")})

# --- candidates -----------------------------------------------------------------------------------
go("drugs")
cols = js("[...document.querySelectorAll('#rankhead th')].map(t => t.textContent)")
rec("candidate table has score, plain profile, coverage, safety, mechanism, clinical, conflicts, outcome and limitation columns",
    all(c in cols for c in ["Score", "What drives the score", "Evidence coverage", "Safety (rank)", "Mechanism (rank)", "Clinical (rank)", "Conflicting evidence", "Key limitation"]), {"cols": cols})
n_all = js("document.querySelectorAll('#rankbody tr').length")
jsb("const q = document.getElementById('q'); q.value = 'pine'; q.dispatchEvent(new Event('input'))"); pump(0.3)
srch = js("[...document.querySelectorAll('#rankbody tr td:nth-child(2)')].map(t => t.textContent)")
jsb("const f = document.getElementById('fmiss'); f.value = 'safety'; f.dispatchEvent(new Event('change'))"); pump(0.3)
both = js("document.querySelectorAll('#rankbody tr').length")
js("document.getElementById('freset').click()"); pump(0.3)
rec("search, filter and 'Clear filters' work together", n_all == 90 and srch and all("pine" in s.lower() for s in srch) and both <= len(srch) and js("document.querySelectorAll('#rankbody tr').length") == 90 and js("document.getElementById('q').value") == "", {"search": srch, "with_filter": both})
js("document.querySelector('#rankhead button[data-sort=VPS_equal_5d]').click()"); pump(0.2)
a1 = js("document.querySelector('#rankhead button[data-sort=VPS_equal_5d]').parentElement.getAttribute('aria-sort')"); top1 = js("document.querySelector('#rankbody tr td:nth-child(2)').textContent")
js("document.querySelector('#rankhead button[data-sort=VPS_equal_5d]').click()"); pump(0.2)
a2 = js("document.querySelector('#rankhead button[data-sort=VPS_equal_5d]').parentElement.getAttribute('aria-sort')"); top2 = js("document.querySelector('#rankbody tr td:nth-child(2)').textContent")
rec("sorting by score toggles direction and announces it (aria-sort)", a1 != a2 and {a1, a2} == {"ascending", "descending"} and top1 != top2, {"first": [a1, top1], "second": [a2, top2]})
lim = {r["compound"]: r for r in RK}
rowtxt = js("[...document.querySelectorAll('#rankbody tr')].find(r => r.cells[1].textContent === 'Deferiprone').innerText")
rec("imputed and not-measured values are marked in the table", "imputed" in rowtxt, {"row": rowtxt[:200]})
js("document.querySelector('#rankbody a[href=\"#drugs/Melatonin\"]').click()"); ready(); pump(0.4)
t = T()
rec("candidate page: why it ranked, evidence for and against, mechanism chain, safety, trials, gaps, provenance",
    all(x in t for x in ["Why Melatonin ranks", "Evidence for and against", "Mechanism: drug → target", "Safety: FDA label", "Clinical trials before 2021", "What is measured and what is missing"]) and js("!!document.querySelector('details.prov')"), {})
js("[...document.querySelectorAll('#main a.btn')].find(a => a.textContent.startsWith('Compare')).click()"); ready(); pump(0.4)
rec("'Compare with other candidates' opens Compare with this candidate", js("location.hash") == "#compare/Melatonin" and js("[...document.querySelectorAll('#main thead th a')].map(a => a.textContent)")[:1] == ["Melatonin"], {"hash": js("location.hash")})
jsb("const s = document.getElementById('cmpadd'); s.value = 'Donepezil'; s.dispatchEvent(new Event('change'))"); ready(); pump(0.4)
added = js("[...document.querySelectorAll('#main thead th a')].map(a => a.textContent)")
js("document.querySelector('button[data-rm=\"Melatonin\"]').click()"); ready(); pump(0.4)
rec("compare: add and remove a candidate", added == ["Melatonin", "Donepezil"] and js("[...document.querySelectorAll('#main thead th a')].map(a => a.textContent)") == ["Donepezil"], {"added": added})
go("drugs/Notadrugxyz")
rec("unknown compound gives one clear message", "No saved evidence mentions this compound" in T() and "Not in the evaluated set" not in T(), {})

# --- evidence ---------------------------------------------------------------------------------------
go("evidence"); E = api("/api/evidence")["items"]
def setsel(i, v): jsb(f"const s = document.getElementById('{i}'); s.value = {json.dumps(v)}; s.dispatchEvent(new Event('input'))"); pump(0.3)
setsel("ebasis", "awaiting_review"); c1 = js("document.getElementById('ecount').textContent")
setsel("ebasis", ""); setsel("estance", "null_or_opposing"); c2 = js("document.getElementById('ecount').textContent")
setsel("estance", "")
rec("evidence filters by basis and stance agree with the API (awaiting review, null or opposing)",
    c1.startswith(f"{sum(i['basis'] == 'awaiting_review' for i in E)} items") and c2.startswith(f"{sum(i['stance'] == 'null_or_opposing' for i in E)} items"), {"awaiting": c1, "null_or_opposing": c2})
js("document.querySelector('details.legend-box').open = true"); pump(0.2)
rec("the stance/basis legend explains missing ≠ negative and that the app never adjudicates", "Missing evidence is not negative evidence" in T() and "never decides it" in T(), {})
go("evidence/Donepezil")
rec("candidate-scoped evidence link pre-filters the compound", js("document.getElementById('ecomp').value") == "Donepezil" and js("[...document.querySelectorAll('#ebody tr td:nth-child(2)')].every(t => t.textContent === 'Donepezil')"), {})
go("review"); RV = api("/api/review")
jsb("const q = document.getElementById('rq'); q.value = 'Dexmedetomidine'; q.dispatchEvent(new Event('input'))"); pump(0.3)
rec("review queue: search narrows, counts equal the artefact, no decision control exists",
    f"of {RV['n_unresolved']} shown" in js("document.getElementById('rcount').textContent") and not js("[...document.querySelectorAll('#main button, #main input[type=checkbox], #main input[type=radio]')].some(b => /approve|adjudicat|accept|decide/i.test(b.textContent + (b.name||'') + (b.id||'')))"),
    {"count": js("document.getElementById('rcount').textContent")})

# --- validation -------------------------------------------------------------------------------------
go("validation")
sec = js("[...document.querySelectorAll('#main section[id^=v-] h2')].map(h => h.textContent)")
rec("Validation has a summary and the six sections in order", sec == ["1. Performance", "2. Evaluation design", "3. Baselines and ablations", "4. Missing and imputed data", "5. Reproducibility", "6. Methods and limitations"], {"sections": sec})
js("document.querySelector('a[data-jump=\"v-repro\"]').click()"); pump(0.4)
rec("section links move focus to the section heading", js("document.activeElement && document.activeElement.textContent") == "5. Reproducibility", {})
rec("evaluation types are labelled (unfitted, in-sample, held-out, exploratory)", all(js(f"!!document.querySelector('.etag.et-{k}')") for k in ("unfitted", "insample", "heldout", "exploratory")), {})
rec("ROC and PR curves drawn only from data that reproduces the report", js("document.querySelectorAll('#v-perf figure.curve').length") == 2 and api("/api/validation_charts")["matches_report"], {})

# --- run center ---------------------------------------------------------------------------------------
go("live")
r06 = js("[...document.querySelectorAll('tbody tr')].find(r => r.cells[0] && r.cells[0].textContent.trim().startsWith('06 ') && r.closest('table').querySelector('th') && [...r.closest('table').querySelectorAll('th')].some(h => h.textContent === 'action'))?.innerText || ''")
r04b = js("[...document.querySelectorAll('tbody tr')].find(r => r.cells[0] && r.cells[0].textContent.trim().startsWith('04b ') && [...r.closest('table').querySelectorAll('th')].some(h => h.textContent === 'action'))?.innerText || ''")
rec("refusals are distinguished: owner approval (protected data) vs command line only (live services)", "Needs owner approval" in r06 and "Command line only" in r04b, {"06": r06[:120], "04b": r04b[:120]})
js("document.querySelector('button[data-run=\"05h\"]').click()"); pump(1.5)
shown = js("!!document.querySelector('button[data-cancel-confirm]')")
js("document.querySelector('button[data-cancel-confirm]').click()"); pump(1.5)
rec("a network stage needs a second, explicit confirmation; Back launches nothing", shown and nlaunch() == n0, {})
rec("opening every page and polling started no run", len(manifest()["history"]) == h0 and nlaunch() == n0, {"history": [h0, len(manifest()["history"])]})
# double-click protection on a quick offline stage (isolated copy)
jsb("const b = document.querySelector('button[data-run=\"10e\"]'); b.click(); b.click(); b.click();"); pump(0.3)
jsb("const b = document.querySelector('button[data-run=\"10e\"]'); if (b) b.click();")
end = time.time() + 40
while time.time() < end and not (nlaunch() > n0 and json.load(open(os.path.join(ldir, sorted(f for f in os.listdir(ldir) if f.endswith('.json'))[-1]))).get("exit_code") is not None):
    pump(0.5)
pump(3)
rec("rapid repeated clicks start exactly one run", nlaunch() == n0 + 1 and len(manifest()["history"]) == h0 + 1, {"launches": nlaunch() - n0, "runs": len(manifest()["history"]) - h0})
go("run")
rec("Run Center shows the completed run without reload", "10e" in js("JSON.stringify((lastStatus||{}).stages||[])") and manifest()["stages"]["10e"]["last_attempt"]["status"] == "SUCCESS", {})
# disconnect / reconnect
subprocess.run(["pkill", "-f", "ui/server.py --root " + C])
lost = None; end = time.time() + 30
while time.time() < end and not lost:
    pump(0.5); lost = "Server not responding" in js("document.getElementById('refreshed').textContent")
subprocess.Popen([PY, os.path.join(R, "ui/server.py"), "--root", C, "--port", "8799"], stdout=open(os.path.join(S, "server8799.log"), "a"), stderr=subprocess.STDOUT, start_new_session=True)
back_ok = None; end = time.time() + 60
while time.time() < end and not back_ok:
    pump(1); back_ok = js("document.getElementById('refreshed').textContent").startswith("Updated")
rec("losing the server is shown, and the page recovers by itself", bool(lost) and bool(back_ok), {"lost": lost, "recovered": back_ok})

# --- copy: no internal jargon on researcher pages -------------------------------------------------------
leaks = {}
for h in ("overview", "drugs", "drugs/Donepezil", "drugs/Melatonin", "compare", "evidence", "mechanism", "conflicts", "review", "validation"):
    go(h); t = T()
    leaks[h] = {"codes": re.findall(r"\b[A-Z]{3,}(?:_[A-Z]+)+\b", t)[:5], "agent_ids": re.findall(r"\b(?:10[a-h]|04p|05h)\b", t)[:5],
                "paths": re.findall(r"\b(?:data|scripts)/[\w./-]+", t)[:5], "td042": "td042" in t}
rec("no raw status codes, agent ids, file paths or the pending result-set id in researcher-facing text",
    all(not v["codes"] and not v["agent_ids"] and not v["paths"] and not v["td042"] for v in leaks.values()), {k: v for k, v in leaks.items() if any(v.values())})
# keyboard
cmd("Page.navigate", url=URL + "#overview"); ready(); cmd("Page.reload", ignoreCache=True); ready(); pump(0.8)
foc = []
for _ in range(4):
    cmd("Input.dispatchKeyEvent", type="keyDown", key="Tab", code="Tab", windowsVirtualKeyCode=9); cmd("Input.dispatchKeyEvent", type="keyUp", key="Tab", code="Tab", windowsVirtualKeyCode=9); pump(0.1)
    foc.append(js("document.activeElement.textContent.trim().slice(0,20)"))
cmd("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, text="\r"); cmd("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13); ready(); pump(0.3)
rec("keyboard: Tab reaches the skip link and the sections in order; Enter opens the focused section",
    foc == ["Skip to content", "Overview", "Candidates", "Evidence"] and js("location.hash") == "#evidence", {"focus": foc, "hash": js("location.hash")})
# mobile
ov = {}
cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
for h in ("overview", "drugs", "drugs/Donepezil", "evidence", "validation", "run"):
    go(h); ov[h] = js("document.documentElement.scrollWidth - window.innerWidth")
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
rec("390 px: no horizontal page scroll on the five sections and a candidate page", all(v <= 0 for v in ov.values()), ov)
# polling cost
go("overview"); pump(1)
mark = len(events); pump(20)
reqs = [e["params"]["request"]["url"] for e in events[mark:] if e.get("method") == "Network.requestWillBeSent"]
rec("idle polling: one small status request every ~4 s, nothing else", 3 <= len(reqs) <= 7 and all(u.endswith("/api/status") for u in reqs), {"requests_in_20s": len(reqs), "urls": sorted(set(u.replace(URL, "/") for u in reqs))})
perf = {}
for h in ("overview", "drugs", "evidence", "validation", "run", "drugs/Donepezil"):
    t0 = time.time(); go(h); perf[h] = round(time.time() - t0, 2)
rec("each section renders within 2 s on this machine", all(v < 2 for v in perf.values()), perf)
errs = [e for e in events if e.get("method") == "Runtime.exceptionThrown" or (e.get("method") == "Log.entryAdded" and e["params"]["entry"]["level"] == "error" and "8799" in e["params"]["entry"].get("url", "8799") and "ERR_CONNECTION_REFUSED" not in e["params"]["entry"].get("text", ""))]
rec("no JavaScript exceptions or console errors (connection-refused during the deliberate restart excluded)", not errs, {"n": len(errs), "first": json.dumps(errs[:1])[:300]})
json.dump({"browser": ver.get("product"), "results": res}, open(os.path.join(HERE, "results16.json"), "w"), indent=1)
print("SUMMARY", sum(r["result"] == "PASS" for r in res), "/", len(res))
import urllib.request as _u; _u.urlopen(f"http://127.0.0.1:9333/json/close/{tab['id']}")
