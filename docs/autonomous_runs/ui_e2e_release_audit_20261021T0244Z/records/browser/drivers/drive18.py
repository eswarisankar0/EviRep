"""Behavioural control audit: every button / select / search input / keyboard chart element is actually operated and
its effect recorded (real Chrome via CDP, isolated copy :8799). Launch buttons (data-run / data-pipeline) are excluded
here: they are executed for real in drive9/drive11/drive16 against the isolated runner.

Effect = any of: location.hash changed, #main DOM changed (innerHTML hash), the control's own state changed
(aria-sort, aria-expanded, value, open), a new network request, or a header/banner change. A control with no effect is
recorded as NO_EFFECT with its context, never silently passed.
"""
import os, json, time, hashlib
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
URL = "http://127.0.0.1:8799/"
ROUTES = ["overview", "drugs", "drugs/Donepezil", "compare", "evidence", "mechanism", "conflicts", "review", "validation",
          "run", "live", "technical", "pipeline", "agents", "cases", "agent/10b"]
cmd("Runtime.enable"); cmd("Page.enable"); cmd("Network.enable")
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
def ready(t=12):
    end = time.time() + t
    while time.time() < end:
        pump(0.15)
        if js("document.getElementById('main').getAttribute('aria-busy') === 'false'"): return
def go(h):
    js(f"location.hash = {json.dumps(h)}"); ready(); pump(0.3)
SNAP = """(() => { const m = document.getElementById('main'); let h = 0; const s = m.innerHTML + '|' + location.hash + '|' + document.getElementById('banner').textContent;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return h; })()"""
SEL = "#main button:not([data-run]):not([data-pipeline]):not([data-confirm]), #nav button, #main select, #main input[type=search], #main input[type=checkbox], #main .chart .bar[data-key], .subnav a"
cmd("Page.navigate", url=URL); pump(5)
rows = []
def nreq(): return sum(1 for e in events if e.get("method") == "Network.requestWillBeSent")
for route in ROUTES:
    go(route)
    n = js(f"document.querySelectorAll({json.dumps(SEL)}).length")
    for i in range(n):
        go(route); cmd("Page.reload", ignoreCache=False); ready(); pump(0.3)    # clean page state for every control
        if js(f"document.querySelectorAll({json.dumps(SEL)}).length") <= i:
            rows.append({"route": route, "index": i, "result": "SKIPPED", "detail": "control list changed"}); continue
        info = js(f"""(() => {{ const e = document.querySelectorAll({json.dumps(SEL)})[{i}]; e.scrollIntoView({{block:'center'}});
           return {{tag: e.tagName, id: e.id, type: e.type || '', label: (e.getAttribute('aria-label') || e.textContent || e.value || '').trim().replace(/\\s+/g,' ').slice(0,50),
             disabled: !!e.disabled, visible: !!e.getClientRects().length, options: e.tagName === 'SELECT' ? [...e.options].map(o => o.value) : null,
             data: Object.assign({{}}, e.dataset), active: e.getAttribute('aria-current') === 'page'}}; }})()""")
        if info.get("active"):
            rows.append({"route": route, "index": i, **{k: info[k] for k in ("tag", "id", "type", "label", "data")}, "result": "ALREADY_ACTIVE"}); continue
        if not info["visible"]:
            rows.append({"route": route, "index": i, **info, "result": "HIDDEN"}); continue
        if info["disabled"]:
            rows.append({"route": route, "index": i, **info, "result": "DISABLED"}); continue
        before, r0, h0 = js(SNAP), nreq(), js("location.hash")
        el = f"document.querySelectorAll({json.dumps(SEL)})[{i}]"
        if info["tag"] == "SELECT":
            opts = [o for o in info["options"] if o != js(f"{el}.value")][:3]
            effects = []
            for o in opts:
                js(f"{{ const e = {el}; e.value = {json.dumps(o)}; e.dispatchEvent(new Event('change', {{bubbles: true}})); e.dispatchEvent(new Event('input', {{bubbles: true}})); }}"); ready(4); pump(0.4)
                effects.append(js(SNAP) != before or js("location.hash") != h0)
                if js("location.hash") != h0: break
            ok = any(effects) if opts else None
        elif info["tag"] == "INPUT" and info["type"] == "search":
            js(f"{{ const e = {el}; e.value = 'zz-no-such-value'; e.dispatchEvent(new Event('input', {{bubbles: true}})); }}"); pump(0.5)
            empty_msg = js("document.getElementById('main').innerText").lower()
            ok = js(SNAP) != before
            info["empty_state"] = any(w in empty_msg for w in ("no candidate matches", "no item matches", "no waiting link matches", "no match"))
        elif info["tag"] == "INPUT":
            js(f"{el}.click()"); pump(0.4); ok = js(SNAP) != before
        elif info["tag"] == "g":
            js(f"{el}.focus()")
            cmd("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, text="\r")
            cmd("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13); ready(); pump(0.3)
            ok = js("location.hash") != h0
        else:
            js(f"{el}.click()"); ready(4); pump(0.4)
            ok = js(SNAP) != before or js("location.hash") != h0 or nreq() > r0
        errs = [e for e in events if e.get("method") == "Runtime.exceptionThrown"]
        rows.append({"route": route, "index": i, **{k: info[k] for k in ("tag", "id", "type", "label", "data")}, "empty_state": info.get("empty_state"),
                     "result": "EFFECT" if ok else ("NO_OPTIONS" if ok is None else "NO_EFFECT"), "hash_after": js("location.hash"), "js_exceptions_so_far": len(errs)})
    done = [r for r in rows if r["route"] == route]
    print(route, len(done), {k: sum(1 for r in done if r["result"] == k) for k in ("EFFECT", "NO_EFFECT", "ALREADY_ACTIVE", "HIDDEN", "DISABLED", "NO_OPTIONS", "SKIPPED")}, flush=True)
errs = [e for e in events if e.get("method") == "Runtime.exceptionThrown"]
json.dump({"rows": rows, "js_exceptions": len(errs)}, open(os.path.join(HERE, "results18.json"), "w"), indent=1)
summ = {k: sum(1 for r in rows if r["result"] == k) for k in ("EFFECT", "NO_EFFECT", "ALREADY_ACTIVE", "HIDDEN", "DISABLED", "NO_OPTIONS", "SKIPPED")}
print("SUMMARY", len(rows), summ, "js_exceptions", len(errs))
for r in rows:
    if r["result"] == "NO_EFFECT": print("NO_EFFECT", r["route"], r["tag"], r["label"], r["data"])
import urllib.request as _u; _u.urlopen(f"http://127.0.0.1:9333/json/close/{tab['id']}")
