"""Presentation rehearsal (2026-10-22): walks the demo runbook in real Chrome against an ISOLATED copy server (:8799),
including one real permitted diagnostic run (10h). Every step asserts the value the presenter will point at."""
import os, json, time, base64
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
URL = "http://127.0.0.1:8799/"
COPY = os.environ["EVIREP_COPY"]
SHOTS = os.environ.get("EVIREP_SHOTS")
res = []
def rec(n, ok, d=None):
    res.append({"step": n, "ok": bool(ok), "detail": d or {}}); print(("PASS " if ok else "FAIL ") + n + " :: " + json.dumps(d or {})[:240], flush=True)
def ready(t=15):
    end = time.time() + t
    while time.time() < end:
        pump(0.2)
        if js("document.getElementById('main').getAttribute('aria-busy') === 'false'"): return
def go(h): js(f"location.hash = {json.dumps(h)}"); ready(); pump(0.6)
def text(): return js("document.getElementById('main').innerText")
def shot(name):
    if SHOTS:
        open(os.path.join(SHOTS, name + ".png"), "wb").write(base64.b64decode(cmd("Page.captureScreenshot", format="png")["data"]))
cmd("Runtime.enable"); cmd("Page.enable"); cmd("Network.enable")
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
cmd("Page.navigate", url=URL); pump(5); ready()

go("overview"); t = text(); shot("01_overview")
rec("1 overview: cohort 90 / 14 and AUROC shown", all(k in t for k in ("90", "14", "0.775")), {"len": len(t)})
rec("1 overview: leakage caveat present", "not leakage-free" in t)

go("drugs"); shot("02_candidates")
rec("2 candidates: 90 rows, '90 of 90 shown'", js("document.querySelectorAll('#rankbody tr').length") == 90 and "90 of 90 shown" in text())
js("{ const q = document.getElementById('q'); q.value = 'donep'; q.dispatchEvent(new Event('input', {bubbles: true})); }"); pump(0.6)
rows = js("[...document.querySelectorAll('#rankbody tr')].map(r => r.innerText.split('\\t').join(' ').slice(0, 60))")
rec("3 search 'donep' -> Donepezil only", len(rows) == 1 and "Donepezil" in rows[0], {"rows": rows})
js("document.getElementById('freset').click()"); pump(0.5)
b = js("(() => { const b = document.querySelector('#rankhead button[data-sort]'); const th = b.closest('th'); const before = th.getAttribute('aria-sort'); b.click(); return [b.textContent.trim(), before]; })()"); pump(0.6)
after = js("(() => { const b = document.querySelector('#rankhead button[data-sort]'); return b.closest('th').getAttribute('aria-sort'); })()")
rec("4 sort: header click changes aria-sort", after != b[1] and after in ("ascending", "descending"), {"column": b[0], "before": b[1], "after": after})
js("{ const e = document.getElementById('flabel'); e.value = '1'; e.dispatchEvent(new Event('change', {bubbles: true})); }"); pump(0.6)
n_pos = js("document.querySelectorAll('#rankbody tr').length")
rec("5 filter 'new trial after 2020 = yes' -> 14 rows (the positives)", n_pos == 14, {"rows": n_pos})
js("document.getElementById('freset').click()"); pump(0.6)
rec("6 clear filters -> 90 rows", js("document.querySelectorAll('#rankbody tr').length") == 90)

go("drugs/Donepezil"); t = text(); shot("03_donepezil")
want = ("0.773", "0.41", "0.88", "1.00", "0.64", "0.93")
rec("7 Donepezil page: score 0.773 and the five ranks", all(w in t for w in want), {"missing": [w for w in want if w not in t]})
rec("7 Donepezil page: rank 1 of 90 and not-efficacy statement", "1 of 90" in t and ("not evidence of efficacy" in t or "not a probability" in t))

for h, k in (("evidence", "evidence"), ("mechanism", "Mechanism"), ("conflicts", "onflict"), ("review", "Awaiting human review (28)")):
    go(h); t = text()
    rec(f"8 {h} loads", len(t) > 300 and k in t and "internal error" not in t, {"len": len(t)})
shot("04_review")

go("validation"); t = text(); shot("05_validation")
rec("9 validation: 0.775, 0.424 and CI 0.656 shown", all(k in t for k in ("0.775", "0.424", "0.656")))
rec("9 validation: TD-042 candidate marked not approved (0.699)", "0.699" in t and "not approved" in t.lower())

go("run"); t = text(); shot("06_run_center")
rec("10 Run Center: agents described as not changing the score", "does not change the score" in t and "eeds the score" not in t)
go("live"); pump(1)
h0 = len(json.load(open(os.path.join(COPY, "data/run_manifest.json")))["history"])
has06 = js("[...document.querySelectorAll('button[data-run]')].some(b => b.dataset.run === '06')")
rec("11 protected stage 06 has no Run button", not has06)
js("[...document.querySelectorAll('button[data-run]')].find(b => b.dataset.run === '10h').click()")
seen_running, t0 = False, time.time()
while time.time() - t0 < 90:
    pump(0.5)
    row = js("(() => { const r = [...document.querySelectorAll('tbody tr')].find(r => r.cells[0] && r.cells[0].textContent.trim().startsWith('10h Completeness') && r.innerText.trim()); return r ? r.innerText : ''; })()") or ""
    if "Running" in row or "running" in row: seen_running = True
    m = json.load(open(os.path.join(COPY, "data/run_manifest.json")))
    if len(m["history"]) > h0 and m["history"][-1].get("status") not in (None, "RUNNING"): break
last = json.load(open(os.path.join(COPY, "data/run_manifest.json")))["history"][-1]
pump(6); shot("07_after_10h_run")
row = js("(() => { const r = [...document.querySelectorAll('tbody tr')].find(r => r.cells[0] && r.cells[0].textContent.trim().startsWith('10h Completeness') && r.innerText.trim()); return r ? r.innerText.replace(/\\s+/g,' ') : ''; })()")
rec("10 live run of 10h recorded SUCCESS in the manifest", last.get("stage") == "10h" and last.get("status") == "SUCCESS", {"run_id": last.get("run_id"), "status": last.get("status")})
rec("10 stage row shows Run completed + the new run id without reload", last.get("run_id", "x") in (row or "") and "completed" in (row or "").lower(), {"row": (row or "")[:160], "saw_running": seen_running})
import urllib.request as _ur
lg = json.loads(_ur.urlopen(f"{URL}api/log?run_id={last.get('run_id')}").read())
rec("10 run log served by the UI API with content", bool(lg.get("tail")) and lg.get("run_id") == last.get("run_id"),
    {"tail_lines": lg.get("tail_lines"), "last_line": (lg.get("tail") or "").splitlines()[-1:]})

errs = [e for e in events if e.get("method") == "Runtime.exceptionThrown"]
cons = [e for e in events if e.get("method") == "Runtime.consoleAPICalled" and e["params"].get("type") in ("error", "warning")]
bad = [e["params"]["response"]["url"] for e in events if e.get("method") == "Network.responseReceived" and e["params"]["response"]["status"] >= 400]
rec("12 no JS exceptions, console errors or failed requests", not errs and not cons and not bad, {"exceptions": len(errs), "console": len(cons), "failed": bad[:3]})
cmd("Emulation.setDeviceMetricsOverride", width=1280, height=720, deviceScaleFactor=1, mobile=False)
over = {}
for h in ("overview", "drugs", "drugs/Donepezil", "validation", "live"):
    go(h); over[h] = js("document.documentElement.scrollWidth - document.documentElement.clientWidth")
rec("13 projector width 1280: no horizontal page scroll", all(v <= 0 for v in over.values()), over)
print("SUMMARY", sum(r["ok"] for r in res), "/", len(res))
json.dump(res, open(os.path.join(HERE, "results22.json"), "w"), indent=1)
import urllib.request as _u; _u.urlopen(f"http://127.0.0.1:9333/json/close/{tab['id']}")
