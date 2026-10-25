"""Runtime reliability browser scenarios (real browser, real server, real runner, isolated copy)."""
import os, json, time, hashlib, shutil, subprocess, sys, signal, re, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
C = os.path.join(S, "livecopy"); URL = "http://127.0.0.1:8799/"; PY = os.path.join(R, "venv/bin/python")
res = []
def rec(n, ok, d=None):
    res.append({"scenario": n, "ok": bool(ok), "detail": d or {}, "real_process": True}); print(("PASS " if ok else "FAIL ") + n + " :: " + json.dumps(d or {})[:240], flush=True)
manifest = lambda: json.load(open(os.path.join(C, "data/run_manifest.json")))
ld = os.path.join(C, "data/_runs/_ui_launches")
launch_ids = lambda: sorted(f[:-5] for f in os.listdir(ld) if f.endswith(".json")) if os.path.isdir(ld) else []
T = lambda: js("(() => { const m = document.getElementById('main'); return m.textContent + [...m.querySelectorAll('.badge')].map(b => ' ' + (b.getAttribute('title') || '')).join(''); })()")
hero = lambda: js("(document.querySelector('.hero-state')||{}).textContent||''")
rstat = lambda: {k: v for k, v in json.loads(subprocess.run([PY, os.path.join(R, "scripts/run_stage.py"), "--status", "--json", "--root", C], capture_output=True, text=True).stdout).items()}
def wait_until(fn, timeout=90, step=0.4):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v: return v
        pump(step)
    return None
def run_reqs():
    return [e for e in events if e.get("method") == "Network.requestWillBeSent" and e["params"]["request"]["url"].endswith("/api/run")]
def idle():
    return wait_until(lambda: "Running" != hero() and js("(async()=>{const l=await (await fetch('/api/live')).json();return !l.launches.some(x=>x.state==='RUNNING') && !l.overall.running.length})()"), 120)
cmd("Runtime.enable"); cmd("Page.enable"); cmd("Network.enable")
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
cmd("Page.navigate", url=URL + "#agent/10e"); pump(5)
# --- double-click: one request, one launch ---
n0, before = len(run_reqs()), set(launch_ids())
js("(() => { const b = document.querySelector('button[data-run=\"10e\"]'); b.click(); b.click(); b.click(); })()")
pump(3); idle()
new = set(launch_ids()) - before
rec("double/triple click on Run sends one request and creates one launch", len(run_reqs()) - n0 == 1 and len(new) == 1, {"requests": len(run_reqs()) - n0, "launches": len(new)})
# --- two tabs clicking at the same time: one 202, one 409, one launch ---
tab2 = json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:9333/json/new?about:blank", method="PUT")))
from websockets.sync.client import connect as _c
ws2 = _c(tab2["webSocketDebuggerUrl"], max_size=50_000_000); mid2 = [0]
def cmd2(method, **params):
    mid2[0] += 1; ws2.send(json.dumps({"id": mid2[0], "method": method, "params": params}))
    while True:
        m = json.loads(ws2.recv())
        if m.get("id") == mid2[0]: return m.get("result")
def js2(expr):
    return cmd2("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)["result"].get("value")
cmd2("Runtime.enable"); cmd2("Page.navigate", url=URL + "#agent/10e"); time.sleep(5)
cmd("Page.navigate", url=URL + "#agent/10e"); pump(5)
before = set(launch_ids())
grab = "(async () => { const s = await (await fetch('/api/session')).json(); window.__n = s.session_nonce; return true })()"
js(grab); js2(grab)
fire = "fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json','X-EviRep-Nonce':window.__n},body:JSON.stringify({stage:'10e'})}).then(r=>r.status)"
js(f"window.__p = {fire}"); js2(f"window.__p = {fire}")
codes = sorted([js("window.__p"), js2("window.__p")])
idle()
rec("two tabs launching at the same moment: one 202, one 409, one launch", codes == [202, 409] and len(set(launch_ids()) - before) == 1, {"codes": codes})
ws2.close(); urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:9333/json/close/{tab2['id']}"))
# --- back / forward ---
for v in ["dashboard", "agent/10d", "drugs"]:
    js(f"location.hash='#{v}'"); pump(2.5)
js("history.back()"); pump(3); b1 = js("location.hash"), "10d" in T() and "Stage 10d" in T()
js("history.back()"); pump(3); b2 = js("location.hash"), bool(hero())
js("history.forward()"); pump(3); f1 = js("location.hash"), "Stage 10d" in T()
rec("browser back/forward re-render the right views", b1 == ("#agent/10d", True) and b2 == ("#dashboard", True) and f1 == ("#agent/10d", True), {"back": b1, "back2": b2, "fwd": f1})
# --- run all with a failed prerequisite: downstream BLOCKED and shown ---
cc = os.path.join(C, "data/conflict_claims_curated.json"); shutil.copy(cc, cc + ".bak")
open(cc, "w").write('{"claims": "not-a-list"}')
js("location.hash='#dashboard'"); pump(5)
wait_until(lambda: js("!!document.querySelector('button[data-pipeline]') && !document.querySelector('button[data-pipeline]').disabled"), 30)
js("document.querySelector('button[data-pipeline]').click()")
shown = wait_until(lambda: "blocked by a failed prerequisite" in T(), 120)
seq = js("(document.querySelector('.seq')||{}).textContent||''")
st = rstat()
rec("run all with a failed prerequisite: 10d FAILED, dependants BLOCKED (not run), shown on the Dashboard",
    bool(shown) and "failed: 10d" in seq and "10e" in seq.split("blocked")[1] and st["10d"]["latest_attempt_failed"],
    {"summary": seq[:200], "hero": hero()})
shutil.move(cc + ".bak", cc)
idle()
# --- runner killed mid-stage: interrupted + orphan reported, restore picked up live ---
pidf = os.path.join(S, "stopped12.pid")
if os.path.exists(pidf): os.remove(pidf)
js("location.hash='#agent/10g'"); pump(4)
wait_until(lambda: js("!!document.querySelector('button[data-run=\"10g\"]') && !document.querySelector('button[data-run=\"10g\"]').disabled"), 60)
catcher = subprocess.Popen([sys.executable, os.path.join(HERE, "catch_stop.py"), C, "10g", pidf])
js("document.querySelector('button[data-run=\"10g\"]').click()")
catcher.wait(timeout=60)
child = int(open(pidf).read().split()[0])
la = manifest()["stages"]["10g"]["last_attempt"]
os.kill(int(la["pid"]), signal.SIGKILL)                         # the runner dies; its stage process lives on
orphan = wait_until(lambda: "still running orphaned" in T(), 30)
rec("runner killed mid-stage: the agent page shows the interrupted run and the orphaned stage process (never RUNNING forever)",
    bool(orphan) and "RUNNING" not in js("(document.querySelector('h2')||{}).textContent") and rstat()["10g"]["status"] != "RUNNING",
    {"status": rstat()["10g"]["status"], "reasons": rstat()["10g"]["reasons"][:3]})
os.kill(child, signal.SIGKILL); time.sleep(0.5)
r = subprocess.run([PY, os.path.join(R, "scripts/run_stage.py"), "--restore", "10g", "--root", C], capture_output=True, text=True)
after = wait_until(lambda: "still running orphaned" not in T() and "showing retained result" in T(), 30)
st = rstat()["10g"]
out_ok = hashlib.md5(open(os.path.join(C, "data/evidence_independence.json"), "rb").read()).hexdigest() == \
    manifest()["stages"]["10g"]["last_success"]["outputs"]["data/evidence_independence.json"]["md5"]
rec("--restore verifies the validated output (restored if damaged); the page updates without refresh: attempt FAILED, retained result shown",
    r.returncode == 0 and bool(after) and st["status"] == "FAILED" and out_ok, {"restore": r.stdout.strip()[:120], "status": st["status"]})
# --- malformed manifest (valid JSON, wrong structure): visible UNKNOWN, not an HTTP 500 ---
mp = os.path.join(C, "data/run_manifest.json"); shutil.copy(mp, mp + ".bak")
m = manifest(); m["stages"]["10h"] = "oops"; json.dump(m, open(mp, "w"))
js("location.hash='#dashboard'")
unk = wait_until(lambda: hero() == "Freshness could not be verified" and "unexpected structure" in T(), 30)
code = js("fetch('/api/live').then(r=>r.status)")
rec("structurally malformed manifest: Dashboard shows 'Run records unreadable' with the reason; /api/live 200", bool(unk) and code == 200, {"status": code})
shutil.move(mp + ".bak", mp); pump(5)
# --- unsafe rendering: HTML in a log is shown as text ---
rid = manifest()["stages"]["10e"]["last_attempt"]["run_id"]
with open(os.path.join(C, "data/_runs", rid, "log.txt"), "a") as fh:
    fh.write('<img src=x onerror="window.__xss=1"><script>window.__xss=2</script>\n')
js("location.hash='#agent/10e'"); pump(4)
js("document.querySelectorAll('details').forEach(d => d.open = true)"); pump(2)
xss = js("window.__xss || 0"); imgs = js("document.querySelectorAll('#main img').length")
rec("HTML injected into a log renders as text (no element, no script)", xss == 0 and imgs == 0 and "onerror" in T(), {"xss": xss, "imgs": imgs})
# --- mobile + console ---
cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
over = {}
for v in ["dashboard", "agent/10g", "live"]:
    js(f"location.hash='#{v}'"); pump(2.5); s_ = state(); over[v] = s_["sw"] - s_["iw"]
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
rec("390px: no horizontal overflow on dashboard, agent and stages views", all(x <= 0 for x in over.values()), over)
errs = [e for e in events if e.get("method") == "Runtime.exceptionThrown"]
cons = [e for e in events if e.get("method") == "Runtime.consoleAPICalled" and e["params"].get("type") == "error"]
bad = [(e["params"]["response"]["url"].split("8799")[-1], e["params"]["response"]["status"]) for e in events
       if e.get("method") == "Network.responseReceived" and e["params"]["response"]["status"] >= 400]
rec("no JS exceptions or console errors; the only non-2xx responses are the intentional 409", not errs and not cons and all(b == ("/api/run", 409) for b in bad), {"bad": bad[:4]})
json.dump(res, open(os.path.join(HERE, "results12.json"), "w"), indent=1)
print("SUMMARY", sum(r["ok"] for r in res), "/", len(res))
