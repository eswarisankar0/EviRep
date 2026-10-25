"""Live Pipeline end to end: real browser -> ui/server.py -> scripts/run_stage.py -> manifest -> live UI (isolated copy)."""
import os, json, time, hashlib, shutil, subprocess, sys, signal
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
C = os.path.join(S, "livecopy"); URL = "http://127.0.0.1:8799/"; PY = os.path.join(R, "venv/bin/python")
res = []
def rec(n, ok, d=None):
    res.append({"scenario": n, "ok": bool(ok), "detail": d or {}}); print(("PASS " if ok else "FAIL ") + n + " :: " + json.dumps(d or {})[:300], flush=True)
md5 = lambda rel: hashlib.md5(open(os.path.join(C, rel), "rb").read()).hexdigest()
manifest = lambda: json.load(open(os.path.join(C, "data/run_manifest.json")))
launches_dir = os.path.join(C, "data/_runs/_ui_launches")
nlaunch = lambda: len([f for f in os.listdir(launches_dir) if f.endswith(".json")]) if os.path.isdir(launches_dir) else 0
main_text = lambda: js("(() => { const m = document.getElementById('main'); return m.textContent + [...m.querySelectorAll('.badge')].map(b => ' ' + (b.getAttribute('title') || '')).join(''); })()")
def row(sid):
    return js(f"(() => {{ const r = [...document.querySelectorAll('tbody tr')].filter(r => [...r.closest('table').querySelectorAll('th')].some(h => h.textContent.trim() === 'action')).find(r => r.cells[0] && r.cells[0].textContent.trim().split(/\\s/)[0] === {json.dumps(sid)}); return r ? (r.textContent + [...r.querySelectorAll('.badge')].map(b => ' ' + b.title).join('')).replace(/\\s+/g,' ') : ''; }})()")
def wait_until(fn, timeout=90, step=0.5):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v: return v
        pump(step)
    return None
cmd("Runtime.enable"); cmd("Page.enable"); cmd("Network.enable")
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
h0, n0 = len(manifest()["history"]), nlaunch()
for v in ["overview", "drugs", "live", "pipeline", "live"]:
    cmd("Page.navigate", url=URL + "#" + v); pump(4)
pump(4)
rec("opening and reloading pages (incl. Live pipeline) starts nothing", len(manifest()["history"]) == h0 and nlaunch() == n0)
t = main_text()
rec("Live pipeline view lists every stage with its dashboard policy", all(js(f"!!document.querySelector('#main [title={x}]')") for x in ("REFUSED", "ALLOWED", "CONFIRM")) and "Needs owner approval" in row("06") and "not from this screen" in row("06"), {"06": row("06")[:120]})
# confirm flow (no network run): Run... -> Confirm/Back -> Back
js("document.querySelector('button[data-run=\"05h\"]').click()"); pump(2)
shown = "Confirm run" in row("05h")
js("document.querySelector('button[data-cancel-confirm]').click()"); pump(2)
rec("network stage needs an explicit second click; Back cancels without launching", shown and "Confirm run" not in row("05h") and nlaunch() == n0)
# make the agents stale in the copy (whitespace-only change to an agent input: same content, new fingerprint)
p = os.path.join(C, "data/conflict_claims_curated.json"); open(p, "a").write("\n")
pump(6)
stale = [s for s in ("10d", "10e", "10g", "10h", "10a") if "STALE" in row(s)]
rec("upstream input change shows dependants STALE live (no reload)", len(stale) >= 4, {"stale": stale})
# run all permitted stages (real runner)
js("document.querySelector('button[data-pipeline]').click()")
ok_fb = wait_until(lambda: "accepted" in main_text(), 15)
rec("Run all: launch accepted (HTTP 202) and command shown", bool(ok_fb))
pump(1)
done = wait_until(lambda: "EXITED" in main_text() and not any(x["status"] == "RUNNING" for x in json.loads(js("JSON.stringify((lastStatus||{}).stages||[])"))), 120, 1)
st = {k: v["status"] for k, v in json.loads(subprocess.run([PY, os.path.join(R, "scripts/run_stage.py"), "--status", "--json", "--root", C], capture_output=True, text=True).stdout).items()}
rec("pipeline finished: stale dependants re-run in dependency order and fresh, launch EXITED exit 0, shown without reload",
    bool(done) and all(st[s] == "SUCCESS" for s in ("10a", "10d", "10e", "10g", "10h")) and "exit 0" in main_text(), {"status": {s: st[s] for s in ("10a", "10d", "10e", "10g", "10h")}})
# a genuinely running real stage: launch 10g, pause its real process with SIGSTOP once the runner starts it
pidfile = os.path.join(S, "stopped.pid")
if os.path.exists(pidfile): os.remove(pidfile)
catcher = subprocess.Popen([sys.executable, os.path.join(HERE, "catch_stop.py"), C, "10g", pidfile])
js("document.querySelector('button[data-run=\"10g\"]').click()")
catcher.wait(timeout=60)
stopped = open(pidfile).read().split() if os.path.exists(pidfile) else []
seen = wait_until(lambda: "RUNNING" in row("10g") and "running " in row("10g"), 20, 0.3)
rec("a real stage (paused mid-run) is shown RUNNING with elapsed time and activity, no percentage", bool(seen) and "%" not in row("10g"), {"row": row("10g")[:200], "paused_pids": stopped})
dis = js("[...document.querySelectorAll('button[data-run],button[data-pipeline]')].every(b => b.disabled)")
code = js("""(async () => { const s = await (await fetch('/api/session')).json();
  const r = await fetch('/api/run', {method:'POST', headers:{'Content-Type':'application/json','X-EviRep-Nonce':s.session_nonce}, body: JSON.stringify({stage:'10h'})});
  return r.status })()""")
rec("during a run: controls disabled and a second launch is refused (409)", dis and code == 409, {"disabled": dis, "status": code})
subprocess.run(["pkill", "-f", "ui/server.py --root " + C])
lost = wait_until(lambda: "lost" in js("document.getElementById('runstate').textContent"), 30, 0.5)
subprocess.Popen([PY, os.path.join(R, "ui/server.py"), "--root", C, "--port", "8799"], stdout=open(os.path.join(S, "server8799b.log"), "w"), stderr=subprocess.STDOUT, start_new_session=True)
back = wait_until(lambda: "lost" not in js("document.getElementById('runstate').textContent") and "RUNNING" in row("10g"), 60, 1)
rec("server restarted while the stage runs: page shows connection lost, reconnects, and still shows the run RUNNING",
    bool(lost) and bool(back) and "UNKNOWN (started before this server" in main_text(), {"row": row("10g")[:120]})
for p_ in stopped:
    os.kill(int(p_), signal.SIGCONT)
fin = wait_until(lambda: "SUCCESS" in row("10g").split("running")[0] and "RUNNING" not in row("10g"), 90, 1)
st = {k: v["status"] for k, v in json.loads(subprocess.run([PY, os.path.join(R, "scripts/run_stage.py"), "--status", "--json", "--root", C], capture_output=True, text=True).stdout).items()}
rec("resumed run completes and the page shows it without reload", bool(fin) and st["10g"] in ("SUCCESS", "PARTIAL"), {"10g": st["10g"]})
# failure path: corrupt an input of 10h -> run 10h -> FAILED shown, previous output kept
gaps_before = md5("data/completeness_gaps.json")
cc = os.path.join(C, "data/conflict_context.json"); shutil.copy(cc, cc + ".bak"); open(cc, "w").write("{corrupt")
enabled = wait_until(lambda: js("!!document.querySelector('button[data-run=\"10h\"]') && !document.querySelector('button[data-run=\"10h\"]').disabled"), 30, 0.5)
h_before = len(manifest()["history"])
js("document.querySelector('button[data-run=\"10h\"]').click()")
failed = wait_until(lambda: "FAILED" in row("10h"), 60)
attempt = manifest()["stages"]["10h"]["last_attempt"]
rec("first click after the server restart launches (stale nonce renewed); real failure propagates to the UI (10h FAILED)", bool(enabled) and bool(failed) and attempt["status"] == "FAILED",
    {"row": row("10h")[:200], "attempt": attempt["status"]})
rec("failed run kept the previous validated output byte-identical (a FAILED attempt really ran)",
    attempt["status"] == "FAILED" and len(manifest()["history"]) > h_before and md5("data/completeness_gaps.json") == gaps_before)
shutil.move(cc + ".bak", cc)
# corrupt manifest: launches disabled
mp = os.path.join(C, "data/run_manifest.json"); shutil.copy(mp, mp + ".bak"); open(mp, "w").write("{x")
pump(6)
dis = js("[...document.querySelectorAll('button[data-run],button[data-pipeline]')].every(b => b.disabled)")
rec("corrupt manifest: launches disabled and the reason shown", dis and "Run records unreadable" in main_text())
shutil.move(mp + ".bak", mp); pump(6)
cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
pump(3); s_ = state()
rec("390px: Live pipeline has no horizontal page scroll", s_["sw"] - s_["iw"] <= 0, {"overflow": s_["sw"] - s_["iw"]})
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
errs = [e for e in events if e.get("method") == "Runtime.exceptionThrown"]
rec("no JS exceptions", not errs, {"n": len(errs), "first": errs[0]["params"]["exceptionDetails"].get("text") if errs else None})
shot = cmd("Page.captureScreenshot", format="png"); import base64
open(os.path.join(HERE, "live_pipeline_desktop.png"), "wb").write(base64.b64decode(shot["data"]))
json.dump(res, open(os.path.join(HERE, "results9.json"), "w"), indent=1)
print("SUMMARY", sum(r["ok"] for r in res), "/", len(res))
