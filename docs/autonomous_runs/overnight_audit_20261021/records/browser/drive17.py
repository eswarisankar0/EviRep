"""Interaction audit: every visible control on every route must do something (real Chrome via CDP, isolated copy).

A control passes when it is (a) an <a> with an internal route that renders or an external URL on an allowed host built
from a valid identifier, (b) a <summary> (native toggle), or (c) a button / select / input / [role=button] with at
least one event listener on itself or an ancestor up to <main>/<header>/<document> (delegation), found with
DOMDebugger.getEventListeners. Disabled controls are listed separately with their reason.
"""
import os, json, re, time
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
URL = "http://127.0.0.1:8799/"
ROUTES = ["overview", "drugs", "drugs/Donepezil", "compare", "evidence", "mechanism", "conflicts", "review", "validation",
          "run", "live", "technical", "pipeline", "agents", "cases", "agent/10b"]
EXT = {"clinicaltrials.gov": r"^https://clinicaltrials\.gov/study/NCT\d{8}$", "pubmed.ncbi.nlm.nih.gov": r"^https://pubmed\.ncbi\.nlm\.nih\.gov/\d{6,9}/$",
       "dailymed.nlm.nih.gov": r"^https://dailymed\.nlm\.nih\.gov/dailymed/lookup\.cfm\?setid=[0-9a-f-]{36}$",
       "www.ensembl.org": r"^https://www\.ensembl\.org/id/ENSG\d{11}$", "www.ebi.ac.uk": r"^https://www\.ebi\.ac\.uk/chembl/compound_report_card/CHEMBL\d+/$",
       "reactome.org": r"^https://reactome\.org/content/detail/R-HSA-\d+$"}
cmd("Runtime.enable"); cmd("Page.enable"); cmd("DOM.enable")
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
cmd("Page.navigate", url=URL); pump(5)
def ready(t=12):
    end = time.time() + t
    while time.time() < end:
        pump(0.2)
        if js("document.getElementById('main').getAttribute('aria-busy') === 'false'"): return
def listeners(expr):
    r = cmd("Runtime.evaluate", expression=expr)
    oid = r["result"].get("objectId")
    if not oid: return []
    return [l["type"] for l in cmd("DOMDebugger.getEventListeners", objectId=oid, depth=0)["listeners"]]
report, internal = {}, set()
doc_listeners = None
for route in ROUTES:
    js(f"location.hash = {json.dumps(route)}"); ready(); pump(0.6)
    js("document.querySelectorAll('#main details').forEach(d => d.open = true)"); pump(0.3)   # reveal controls in collapsed sections
    n = js("""(() => { window.__ctl = [...document.querySelectorAll('header a, header button, #main a, #main button, #main select, #main input, #main summary, #main [role=button]')]
        .filter(e => e.getClientRects().length); return window.__ctl.length; })()""")
    dead, ext_bad, disabled, kinds = [], [], [], {}
    for i in range(n):
        info = js(f"(() => {{ const e = window.__ctl[{i}]; return {{tag: e.tagName, type: e.type || '', href: e.getAttribute('href'), id: e.id, text: (e.textContent || e.value || e.getAttribute('aria-label') || '').trim().slice(0, 40), disabled: !!e.disabled, title: e.title || ''}}; }})()")
        kinds[info["tag"]] = kinds.get(info["tag"], 0) + 1
        if info["tag"] == "A":
            h = info["href"] or ""
            if h.startswith("#"):
                internal.add(h)
            elif h.startswith("http"):
                host = re.sub(r"^https?://([^/]+).*$", r"\1", h)
                if host not in EXT or not re.match(EXT[host], h): ext_bad.append(h)
            else:
                dead.append(info)
            continue
        if info["tag"] == "SUMMARY":
            continue
        if info["disabled"]:
            disabled.append(info); continue
        found = False
        for depth in range(0, 8):
            path = "window.__ctl[%d]%s" % (i, ".parentElement" * depth)
            if js(f"!{path} || {path}.id === 'main' || {path}.tagName === 'HEADER' || {path}.tagName === 'BODY'") and depth > 0:
                ls = listeners(path) if js(f"!!{path}") else []
                found = found or bool(ls)
                break
            if listeners(path):
                found = True; break
        if not found:
            # delegated listeners at document level (the toggle handler for log tails etc.)
            dead.append(info)
    report[route] = {"controls": n, "by_tag": kinds, "dead": dead, "external_bad": ext_bad[:5], "disabled": disabled}
    print(route, n, kinds, "dead:", [(d["tag"], d["text"]) for d in dead][:6], "ext_bad:", len(ext_bad), "disabled:", len(disabled), flush=True)
bad_routes = {}
for h in sorted(internal):
    js(f"location.hash = {json.dumps(h)}"); ready(); pump(0.3)
    t = js("document.getElementById('main').innerText")
    if "Could not load" in t or "failed to render" in t or len(t) < 80: bad_routes[h] = t[:120]
print("internal links checked:", len(internal), "failing:", bad_routes)
errs = [e for e in events if e.get("method") == "Runtime.exceptionThrown"]
json.dump({"routes": report, "internal_links": sorted(internal), "internal_link_failures": bad_routes, "js_exceptions": len(errs)},
          open(os.path.join(HERE, "results17.json"), "w"), indent=1)
total = sum(r["controls"] for r in report.values()); dead = sum(len(r["dead"]) for r in report.values())
print("SUMMARY controls", total, "dead", dead, "external_bad", sum(len(r["external_bad"]) for r in report.values()), "internal_failing", len(bad_routes), "js_exceptions", len(errs))
import urllib.request as _u; _u.urlopen(f"http://127.0.0.1:9333/json/close/{tab['id']}")
