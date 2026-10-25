"""Timeout lifecycle in a real browser: launch -> RUNNING -> timeout -> FAILED -> output restored (isolated code+data copy,
10h timeout_s=20 in the copy only; production registry keeps 900 s)."""
import os, json, time, hashlib, subprocess, sys, signal
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
G = os.path.join(S, "gatecopy4"); URL = "http://127.0.0.1:8799/"; PY = os.path.join(R, "venv/bin/python")
res = []
def rec(n, ok, d=None, action=""):
    res.append({"check": n, "result": "PASS" if ok else "FAIL", "browser_action": action, "detail": d or {}, "real_process": True}); print(("PASS " if ok else "FAIL ") + n + " :: " + json.dumps(d or {})[:230], flush=True)
md5 = lambda rel: hashlib.md5(open(os.path.join(G, rel), "rb").read()).hexdigest()
man = lambda: json.load(open(os.path.join(G, "data/run_manifest.json")))
pstate = lambda pid: subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
alive = lambda pid: pstate(pid) != "" and not pstate(pid).startswith("Z")     # a zombie is not alive
T = lambda: js("(() => { const m = document.getElementById('main'); return m.textContent + [...m.querySelectorAll('.badge')].map(b => ' ' + (b.getAttribute('title') || '')).join(''); })()")
def wait_until(fn, timeout=90, step=0.4):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v: return v
        pump(step)
    return None
cmd("Runtime.enable"); cmd("Page.enable"); cmd("Network.enable")
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
good = md5("data/completeness_gaps.json")
sentinel = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)          # unrelated process
server_pid = int(subprocess.run(["pgrep", "-f", "ui/server.py --port 8799"], capture_output=True, text=True).stdout.split()[0])
open(os.path.join(G, "HANG_FOR_TIMEOUT_TEST"), "w").write("1")
cmd("Page.navigate", url=URL + "#agent/10h"); pump(5)
wait_until(lambda: js("!!document.querySelector('button[data-run=\"10h\"]') && !document.querySelector('button[data-run=\"10h\"]').disabled"), 30)
t0 = time.time()
js("document.querySelector('button[data-run=\"10h\"]').click()")
running = wait_until(lambda: "running" in T() and "test hang" in T(), 15, 0.3)
la = man()["stages"]["10h"]["last_attempt"]
runner, child = la.get("pid"), la.get("child_pid")
rec("launch from the agent page -> RUNNING shown with elapsed time and the real log line, no refresh",
    bool(running) and la["status"] == "RUNNING" and alive(runner) and alive(child), {"run_id": la["run_id"], "runner": runner, "child": child}, "click 'Run 10h' on #agent/10h")
partial_md5 = md5("data/completeness_gaps.json")
rec("while running, the stage has really overwritten its output (partial write)", partial_md5 != good, {"partial": partial_md5 != good})
failed = wait_until(lambda: "FAILED" in T() and "TIMEOUT" in T(), 60, 0.5)
elapsed = round(time.time() - t0, 1)
la2 = man()["stages"]["10h"]["last_attempt"]
rec("timeout fires (~20 s): agent page shows FAILED and the TIMEOUT line from the real log, without refresh",
    bool(failed) and la2["status"] == "FAILED" and any(d["code"] == "TIMEOUT" for d in la2.get("diagnostics") or []) and 18 <= elapsed <= 60,
    {"seconds_to_failed_in_ui": elapsed, "exit_code": la2.get("exit_code")}, "wait on #agent/10h")
rec("previous valid output restored byte-identical", md5("data/completeness_gaps.json") == good, {"md5": md5("data/completeness_gaps.json")})
time.sleep(1)
rec("only the stage's own child was killed: child and runner gone; unrelated sentinel and the server still alive",
    not alive(child) and not alive(runner) and sentinel.poll() is None and alive(server_pid),
    {"child_state": pstate(child) or "gone", "runner_state": pstate(runner) or "gone (reaped)", "sentinel_alive": sentinel.poll() is None})
orph = subprocess.run(["pgrep", "-f", "scripts/completeness_gap_agent.py --root"], capture_output=True, text=True).stdout.split()
st = json.loads(subprocess.run([PY, os.path.join(G, "scripts/run_stage.py"), "--status", "--json", "--root", G], capture_output=True, text=True).stdout)["10h"]
rec("no orphaned stage process and no RUNNING record remain", not orph and st["status"] != "RUNNING" and st["latest_attempt_failed"], {"status": st["status"], "orphans": orph})
cmd("Page.navigate", url=URL + "#dashboard"); pump(4)
hero = js("(document.querySelector('.hero-state')||{}).textContent")
rec("Dashboard reports the failure (hero, failed counter, 10h card) after timeout", "failed" in hero.lower() and "10h" in js("(document.querySelector('.tile.t-bad')||{}).title||''"), {"hero": hero})
os.remove(os.path.join(G, "HANG_FOR_TIMEOUT_TEST"))
cmd("Page.navigate", url=URL + "#agent/10h"); pump(4)
wait_until(lambda: js("!!document.querySelector('button[data-run=\"10h\"]') && !document.querySelector('button[data-run=\"10h\"]').disabled"), 30)
js("document.querySelector('button[data-run=\"10h\"]').click()")
ok = wait_until(lambda: (lambda a: a.get("status") == "SUCCESS")(man()["stages"]["10h"]["last_attempt"]), 60)
pump(4)
rec("recovery: next run (hang removed) succeeds and the page shows it", bool(ok) and "SUCCESS" in T(), {}, "click 'Run 10h' again")
sentinel.kill(); sentinel.wait()
errs = [e for e in events if e.get("method") == "Runtime.exceptionThrown"]
rec("no JS exceptions during the lifecycle", not errs, {"n": len(errs)})
json.dump(res, open(os.path.join(HERE, "results13.json"), "w"), indent=1)
print("SUMMARY", sum(r["result"] == "PASS" for r in res), "/", len(res))
import urllib.request as _u
_u.urlopen(f"http://127.0.0.1:9333/json/close/{tab['id']}")      # do not leave headless tabs behind
