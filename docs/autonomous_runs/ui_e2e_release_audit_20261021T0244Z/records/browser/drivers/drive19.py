"""Accessibility-tree audit (real Chrome via CDP, isolated copy :8799): every focusable control has an accessible name,
charts are labelled images with a data-table alternative, the document has a language and a main landmark."""
import os, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
URL = "http://127.0.0.1:8799/"
ROUTES = ["overview", "drugs", "drugs/Donepezil", "compare", "evidence", "mechanism", "conflicts", "review", "validation",
          "run", "live", "technical", "pipeline", "agents", "cases", "agent/10b"]
ROLES = {"button", "link", "combobox", "textbox", "searchbox", "checkbox", "listbox", "menuitem", "tab"}
cmd("Runtime.enable"); cmd("Page.enable"); cmd("Accessibility.enable")
cmd("Page.navigate", url=URL); pump(5)
def ready(t=12):
    end = time.time() + t
    while time.time() < end:
        pump(0.2)
        if js("document.getElementById('main').getAttribute('aria-busy') === 'false'"): return
out = {}
for r in ROUTES:
    js(f"location.hash = {json.dumps(r)}"); ready(); pump(0.5)
    js("document.querySelectorAll('#main details').forEach(d => d.open = true)"); pump(0.3)
    nodes = cmd("Accessibility.getFullAXTree")["nodes"]
    unnamed, counts = [], {}
    for n in nodes:
        role = (n.get("role") or {}).get("value")
        if role in ROLES and not n.get("ignored"):
            counts[role] = counts.get(role, 0) + 1
            name = ((n.get("name") or {}).get("value") or "").strip()
            if not name:
                unnamed.append(role)
    charts = js("[...document.querySelectorAll('#main figure.chart svg')].map(s => ({label: s.getAttribute('aria-label') || '', role: s.getAttribute('role'), table: !!s.closest('figure').querySelector('details.chartdata')}))")
    bad_charts = [c for c in charts if not c["label"] or c["role"] != "img" or not c["table"]]
    out[r] = {"controls_by_role": counts, "unnamed_controls": unnamed, "charts": len(charts), "charts_missing_label_or_table": bad_charts}
    print(r, counts, "unnamed:", unnamed, "charts:", len(charts), "bad charts:", len(bad_charts), flush=True)
doc = js("({lang: document.documentElement.lang, main: !!document.querySelector('main#main'), skip: !!document.getElementById('skip'), title: document.title})")
json.dump({"routes": out, "document": doc}, open(os.path.join(HERE, "results19.json"), "w"), indent=1)
print("SUMMARY unnamed", sum(len(v["unnamed_controls"]) for v in out.values()), "charts", sum(v["charts"] for v in out.values()),
      "bad_charts", sum(len(v["charts_missing_label_or_table"]) for v in out.values()), "doc", doc)
import urllib.request as _u; _u.urlopen(f"http://127.0.0.1:9333/json/close/{tab['id']}")
