import os, json
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
LIVE = "http://127.0.0.1:8765/"
res = []
def rec(n, ok, d=None):
    res.append({"scenario": n, "ok": bool(ok), "detail": d or {}}); print(("PASS " if ok else "FAIL ") + n + " :: " + json.dumps(d or {})[:260], flush=True)
cmd("Runtime.enable"); cmd("Page.enable"); cmd("Network.enable")
hist0 = len(json.load(open(os.path.join(R, "data/run_manifest.json")))["history"])
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
cmd("Page.navigate", url=LIVE + "#agents"); pump(7)
t = js("document.getElementById('main').textContent")
rec("agents panel shows tracked freshness column", "tracked freshness" in t)
rows = js("[...document.querySelectorAll('tbody tr')].filter(r => /^10[a-h]/.test(r.cells[0]?.textContent||'')).map(r => r.cells[0].textContent.trim()+'|'+r.cells[3].textContent.replace(/\\s+/g,' ').slice(0,60))")
rows = rows[:8]
rec("all eight agents listed with a tracked status", len(rows) == 8 and all(("SUCCESS" in r or "ADOPTED" in r) for r in rows), {"rows": rows})
rec("agents show their VPS role", all(x in t for x in ("score-contributing (stage 08", "diagnostic (categorical", "completeness annotation")))
views = {"live": 1000, "agents": 1000, "overview": 200, "drugs": 1000, "drugs/Droxidopa": 1000, "pipeline": 1000, "review": 1000, "validation": 300, "technical": 100}
misaligned = {}
for v, mn in views.items():
    js(f"location.hash='#{v}'"); pump(3)
    bad = js("""[...document.querySelectorAll('table')].filter(t => t.tHead && t.tBodies[0]).map(t => {
      const h = [...t.tHead.rows[0].cells].reduce((n, c) => n + (c.colSpan || 1), 0);
      const w = [...t.tBodies[0].rows].map(r => [...r.cells].reduce((n, c) => n + (c.colSpan || 1), 0));
      return w.filter(x => x !== h).length ? (t.closest('section')?.querySelector('h2')?.textContent || '?') + ' ' + h + 'v' + [...new Set(w)] : null }).filter(Boolean)""")
    if bad: misaligned[v] = bad
    t = js("document.getElementById('main').textContent")
    rec(f"desktop #{v} renders", len(t) > mn and "internal error" not in t and "Request failed" not in t, {"len": len(t)})
rec("every table: header cells match row cells (all views)", not misaligned, misaligned)
js("location.hash='#drugs/Droxidopa'"); pump(3)
t = js("document.getElementById('main').textContent")
rec("compound page states ranking is not an efficacy claim", any(k in t.lower() for k in ("not a measure of efficacy", "not efficacy", "does not estimate efficacy", "not a claim")), {})
js("location.hash='#review'"); pump(3)
t = js("document.getElementById('main').textContent")
rec("review queue: 28 awaiting adjudication, none auto-decided", "Awaiting adjudication (28)" in t)
# keyboard: Tab from the top reaches the skip link then nav items with a visible focus style
js("document.activeElement.blur(); window.scrollTo(0,0)")
foc = []
for _ in range(4):
    cmd("Input.dispatchKeyEvent", type="keyDown", key="Tab", code="Tab", windowsVirtualKeyCode=9)
    cmd("Input.dispatchKeyEvent", type="keyUp", key="Tab", code="Tab", windowsVirtualKeyCode=9)
    foc.append(js("(() => { const e = document.activeElement; const cs = getComputedStyle(e); return [e.tagName, (e.textContent||'').trim().slice(0,20), cs.outlineStyle !== 'none' || cs.boxShadow !== 'none'] })()"))
rec("keyboard Tab moves focus through links with a visible focus indicator", all(f[0] in ("A", "BUTTON", "SELECT", "INPUT", "SUMMARY") and f[2] for f in foc), {"focus": foc})
a11y = js("""({imgs_no_alt: [...document.images].filter(i => !i.hasAttribute('alt')).length,
  unlabeled_inputs: [...document.querySelectorAll('input,select,textarea')].filter(e => !e.labels?.length && !e.getAttribute('aria-label')).length,
  th_no_scope: document.querySelectorAll('thead th:not([scope])').length, lang: document.documentElement.lang,
  main: !!document.querySelector('main'), nav: !!document.querySelector('nav')})""")
rec("basic semantics: lang, main, nav, labelled inputs, img alt", a11y["lang"] and a11y["main"] and a11y["nav"] and a11y["unlabeled_inputs"] == 0 and a11y["imgs_no_alt"] == 0, a11y)
cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
over = {}
for v in ["live", "agents", "pipeline", "overview", "drugs/Droxidopa", "review", "validation"]:
    js(f"location.hash='#{v}'"); pump(3); s = state(); over[v] = s["sw"] - s["iw"]
rec("390px: no horizontal page scroll", all(x <= 0 for x in over.values()), over)
failed = [e["params"].get("response", {}).get("url") for e in events if e.get("method") == "Network.responseReceived" and e["params"].get("response", {}).get("status", 200) >= 400]
rec("no failed HTTP requests during ordinary use", not failed, {"failed": failed[:5]})
errs = [e for e in events if e.get("method") == "Runtime.exceptionThrown"]
cons = [e for e in events if e.get("method") == "Runtime.consoleAPICalled" and e["params"].get("type") in ("error", "warning")]
rec("no JS exceptions or console errors", not errs and not cons, {"exceptions": len(errs), "console": [c["params"]["args"][0].get("value") for c in cons][:3]})
rec("viewing pages started no stage", len(json.load(open(os.path.join(R, "data/run_manifest.json")))["history"]) == hist0)
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
js("location.hash='#agents'"); pump(4)
shot = cmd("Page.captureScreenshot", format="png")
import base64; open(os.path.join(HERE, "agents_panel_desktop.png"), "wb").write(base64.b64decode(shot["data"]))
json.dump(res, open(os.path.join(HERE, "results7.json"), "w"), indent=1)
print("SUMMARY", sum(r["ok"] for r in res), "/", len(res))
