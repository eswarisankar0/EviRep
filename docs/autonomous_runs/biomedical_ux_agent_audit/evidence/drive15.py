"""UI quality acceptance: every route, controls, charts vs source data, labels, live updates (real browser; isolated copy)."""
import os, json, time, re, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
C = os.path.join(S, "livecopy"); URL = "http://127.0.0.1:8799/"
res = []
def rec(n, ok, d=None, action=""):
    res.append({"check": n, "result": "PASS" if ok else "FAIL", "browser_action": action, "detail": d or {}}); print(("PASS " if ok else "FAIL ") + n + " :: " + json.dumps(d or {})[:230], flush=True)
T = lambda: js("document.getElementById('main').textContent")
api = lambda p: json.loads(js(f"(async () => JSON.stringify(await (await fetch('{p}')).json()))()"))
def go(h, wait=3.5):
    js(f"location.hash='#{h}'"); pump(wait)
def wait_until(fn, timeout=60, step=0.4):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v: return v
        pump(step)
    return None
cmd("Runtime.enable"); cmd("Page.enable"); cmd("Network.enable")
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
cmd("Page.navigate", url=URL); pump(6)
# ---- every route renders; no raw machine codes in badges on primary screens ----
routes = ["dashboard", "live", "drugs", "drugs/Donepezil", "evidence", "mechanism/Donepezil", "conflicts", "review", "compare", "validation", "overview", "technical", "agent/10g"]
bad, raw = {}, {}
for r in routes:
    go(r)
    t = T()
    if len(t) < 300 or "failed to render" in t or "internal error" in t: bad[r] = len(t)
    codes = js("[...document.querySelectorAll('#main .badge')].map(b => b.textContent.trim()).filter(x => /^[A-Z][A-Z0-9_]{3,}$/.test(x) && x.includes('_') )")
    if codes: raw[r] = sorted(set(codes))[:6]
rec("all 13 routes render without error", not bad, bad, "visit each route")
rec("no raw MACHINE_CODE badges on any route (codes kept in tooltips)", not raw, raw)
# ---- dashboard: truthful freshness and charts match the API / artefacts ----
go("dashboard", 5)
L = api("/api/live"); V = api("/api/validation_charts")
hero = js("document.querySelector('.hero-state').textContent")
expected = {"CURRENT": "Current against recorded inputs", "VERIFIED_WITH_GAPS": "Current against recorded inputs, with unverifiable inputs", "STALE": "Inputs changed — rerun needed"}.get(L["overall"]["state"], None)
rec("hero headline is derived from the tracker state (no blanket claim)", hero == expected and "All results current" not in T(), {"hero": hero, "state": L["overall"]["state"]})
rec("last successful run time shown equals the tracker's", L["freshness"]["last_success_utc"][:16].replace("T", " ") in T(), {"last": L["freshness"]["last_success_utc"]})
nodes = js("document.querySelectorAll('.dag .node').length"); edges = js("document.querySelectorAll('.dag .edge').length")
n_edges = sum(len(s["upstream"]) for s in L["stages"])
rec("dependency graph: one node per stage and one arrow per dependency", nodes == len(L["stages"]) and edges == n_edges, {"nodes": nodes, "edges": edges, "expected": [len(L["stages"]), n_edges]})
au = js("[...document.querySelectorAll('.panel')].find(p => p.textContent.includes('Scientific validation')).querySelector('.chart .val').textContent")
rec("dashboard AUROC equals the approved report (0.775)", au == f"{L['science']['primary_metric']['value']:.3f}", {"shown": au})
src_rows = js("[...document.querySelectorAll('.panel')].find(p => p.querySelector('h3') && p.querySelector('h3').textContent === 'Source data').querySelectorAll('tbody tr').length")
rec("source data table lists every recorded source, unrecorded times shown as 'not recorded'", src_rows == len(L["sources"]) and "not recorded" in T(), {"rows": src_rows})
rec("header shows the last successful refresh time", js("document.getElementById('refreshed').textContent").startswith("Updated"))
# ---- validation charts equal the source data ----
go("validation", 5)
rec("ROC and PR curves drawn (areas reproduce the approved report)", V["matches_report"] and js("document.querySelectorAll('.chart.curve').length") == 2, {"auroc": V["auroc_recomputed"]})
roc_pts = js("document.querySelector('.chart.curve polyline').getAttribute('points').trim().split(' ').length")
rec("ROC polyline has one vertex per distinct threshold (+origin)", roc_pts == len(V["roc"]), {"vertices": roc_pts, "api": len(V["roc"])})
miss = js("[...document.querySelectorAll('.chart')].find(f => f.textContent.includes('Compounds without a measured value')).querySelectorAll('.val')").__class__
miss_txt = js("[...[...document.querySelectorAll('.chart')].find(f => f.textContent.includes('Compounds without a measured value')).querySelectorAll('text.val')].map(t => t.textContent)")
rec("missing-data chart equals the report (7 safety, 16 molecular, 2 proximity imputed)", "7 not measured" in miss_txt and "16 not measured" in miss_txt and "2 median-imputed" in miss_txt, {"values": miss_txt})
rec("paired 5D-4D interval chart shows the zero reference and says the interval includes zero", "includes zero" in T() and js("!!document.querySelector('.chart .ref')"))
# ---- candidates: chart, selection, search, sort, filters ----
go("drugs", 5)
R = api("/api/ranking")
first = js("document.querySelector('.chart .bar[data-key]').dataset.key")
rec("ranking chart's first bar is the rank-1 compound with its persisted score", first == R["rows"][0]["compound"] and f"{R['rows'][0]['VPS_equal_5d']:.3f}" in js("document.querySelector('.chart .bar[data-key] text.val').textContent"), {"first": first})
js("document.querySelectorAll('.chart .bar[data-key]')[2].dispatchEvent(new MouseEvent('click', {bubbles: true}))"); pump(4)
third = R["rows"][2]["compound"]
rec("clicking a bar opens that candidate", third in js("decodeURIComponent(location.hash)") and f"Why {third} ranks" in T(), {"hash": js("location.hash")})
go("drugs", 5)
js("document.querySelectorAll('.chart .bar[data-key]')[0].focus()")
cmd("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13); cmd("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13); pump(4)
rec("keyboard: Enter on a focused bar opens the candidate", first in js("decodeURIComponent(location.hash)"))
go("drugs", 5)
js("{const q=document.getElementById('q'); q.value='done'; q.dispatchEvent(new Event('input'))}"); pump(1)
items = js("[...document.querySelectorAll('#rankbody tr td:nth-child(2)')].map(l => l.textContent.trim())")
js("{const q=document.getElementById('q'); q.value=''; q.dispatchEvent(new Event('input'))}"); pump(1)
rec("candidate search filters the list", items and all("done" in i.lower() for i in items), {"items": items[:5]})
before = js("[...document.querySelectorAll('#rankbody tr td:nth-child(2)')].slice(0,3).map(t=>t.textContent)") if js("!!document.getElementById('rankbody')") else None
js("document.querySelector('button[data-sort=\"compound\"]') && document.querySelector('button[data-sort=\"compound\"]').click()"); pump(1)
after = js("[...document.querySelectorAll('#rankbody tr td:nth-child(2)')].slice(0,3).map(t=>t.textContent)") if js("!!document.getElementById('rankbody')") else None
rec("ranking table sorts when a header is clicked", before is not None and before != after and after == sorted(after), {"before": before, "after": after})
# ---- compare: add / remove ----
go("compare/Donepezil,Melatonin", 5)
n0 = js("document.querySelectorAll('.chart .legend .sw.s0, .legend .sw.s0, .legend .sw.s1').length")
js("{const s=document.getElementById('cmpadd'); s.value=[...s.options][1].value; s.dispatchEvent(new Event('change'))}"); pump(4)
three = js("decodeURIComponent(location.hash)").count(",") == 2
js("document.querySelector('button[data-rm]').click()"); pump(4)
rec("compare: add and remove candidates; grouped chart drawn for the selection", three and js("decodeURIComponent(location.hash)").count(",") == 1 and js("document.querySelectorAll('.legend .sw').length") >= 3, {"hash": js("decodeURIComponent(location.hash)")})
# ---- evidence: filter, more, source toggle ----
go("evidence", 5)
c0 = js("document.querySelectorAll('#ebody tr').length")
js("document.getElementById('emore').click()"); pump(1)
c1 = js("document.querySelectorAll('#ebody tr').length")
js("{const e=document.getElementById('esrc'); e.click()}"); pump(1)
src_on = js("document.querySelectorAll('#ebody tr:first-child td').length")
js("{const c=document.getElementById('ecomp'); c.value='Donepezil'; c.dispatchEvent(new Event('input'))}"); pump(1)
only = js("[...document.querySelectorAll('#ebody tr td:nth-child(2)')].every(t => t.textContent === 'Donepezil')")
rec("evidence: 100 rows, 'Show 100 more', source-file toggle and compound filter all work", c0 == 100 and c1 == 200 and src_on == 9 and only, {"rows": [c0, c1], "cols_with_source": src_on})
# ---- mechanism chain equals the record ----
go("mechanism/Donepezil", 5)
D = api("/api/compound?name=Donepezil"); E = D["dimensions"]["molecular"]["evidence_chain"]
tgt = js("document.querySelectorAll('.chart svg g.node').length") - 2
rec("mechanism chain draws one node per target (max 10) from the saved record", tgt == min(10, len(E["targets"])), {"targets": tgt, "record": len(E["targets"])})
# ---- review queue: counts, search, filter ----
go("review", 5)
RV = api("/api/review")
txt = T()
js("{const q=document.getElementById('rq'); q.value='NCT'; q.dispatchEvent(new Event('input'))}"); pump(1)
cnt = js("document.getElementById('rcount').textContent")
js("{const f=document.getElementById('rflag'); f.value='ALIAS_GAP'; f.dispatchEvent(new Event('change'))}"); pump(1)
cnt2 = js("document.getElementById('rcount').textContent")
rec("review queue: counts equal the artefact; search and reason filter narrow the list", f"{RV['n_unresolved']}" in txt and cnt.startswith(f"{RV['n_unresolved']} of") and int(cnt2.split()[0]) <= 4, {"all": cnt, "alias": cnt2})
# ---- back / forward, mobile, console ----
go("dashboard"); go("validation"); js("history.back()"); pump(3)
rec("back returns to the previous view", js("location.hash") == "#dashboard" and js("!!document.querySelector('.hero-state')"))
cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
over = {}
for r in ["dashboard", "live", "drugs", "validation", "mechanism/Donepezil", "review", "compare"]:
    go(r, 3); s_ = state(); over[r] = s_["sw"] - s_["iw"]
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
rec("390px: no horizontal page overflow on 7 views (wide charts scroll inside their box)", all(v <= 0 for v in over.values()), over)
errs = [e for e in events if e.get("method") == "Runtime.exceptionThrown"]
cons = [e for e in events if e.get("method") == "Runtime.consoleAPICalled" and e["params"].get("type") == "error"]
badr = [(e["params"]["response"]["url"].split("8799")[-1], e["params"]["response"]["status"]) for e in events if e.get("method") == "Network.responseReceived" and e["params"]["response"]["status"] >= 400]
rec("no JS exceptions, console errors or failed requests", not errs and not cons and not badr, {"exceptions": len(errs), "console": len(cons), "failed": badr[:4]})
json.dump(res, open(os.path.join(HERE, "results15.json"), "w"), indent=1)
urllib.request.urlopen(f"http://127.0.0.1:9333/json/close/{tab['id']}")
print("SUMMARY", sum(r["result"] == "PASS" for r in res), "/", len(res))
