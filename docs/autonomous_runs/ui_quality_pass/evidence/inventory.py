import os, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
URL = os.environ.get("INV_URL", "http://127.0.0.1:8765/")
cmd("Runtime.enable"); cmd("Page.enable")
routes = ["dashboard", "live", "drugs", "drugs/Acetylcysteine", "evidence", "mechanism", "conflicts", "review", "compare", "validation", "overview", "technical", "pipeline", "agents", "cases", "agent/10b"]
inv = {}
for r in routes:
    cmd("Page.navigate", url=URL + "#" + r); pump(4)
    inv[r] = js("""(() => { const m = document.getElementById('main'); const t = s => (s.textContent||'').replace(/\\s+/g,' ').trim();
      return {headings: [...m.querySelectorAll('h1,h2,h3')].map(t), badges: [...new Set([...m.querySelectorAll('.badge')].map(t))],
              buttons: [...m.querySelectorAll('button')].map(t), links: [...m.querySelectorAll('a')].map(a => [t(a).slice(0,60), a.getAttribute('href')]).slice(0,80),
              th: [...new Set([...m.querySelectorAll('th')].map(t))], selects: [...m.querySelectorAll('select,input')].map(e => e.id || e.name || e.type),
              chars: t(m).length, codes: (t(m).match(/\\b(td\\d{3}_v\\d|TD-\\d+|D-\\d+|E-\\d+|B-\\d+|10[a-h]\\b|[A-Z]{3,}_[A-Z_]{3,})/g)||[]).length,
              paths: (t(m).match(/(data|scripts|docs)\\/[\\w\\/.\\-]+/g)||[]).length, text: t(m).slice(0, 600)} })()""")
json.dump(inv, open(os.path.join(HERE, "inventory.json"), "w"), indent=1)
import urllib.request as _u; _u.urlopen(f"http://127.0.0.1:9333/json/close/{tab['id']}")
for r, v in inv.items():
    print(f"{r:22} chars {v['chars']:6} headings {len(v['headings']):3} buttons {len(v['buttons']):3} links {len(v['links']):3} codes {v['codes']:4} paths {v['paths']:4} badges {v['badges'][:8]}")
