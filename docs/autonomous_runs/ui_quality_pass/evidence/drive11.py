"""Live application acceptance: real browser -> ui/server.py -> scripts/run_stage.py -> manifest -> Dashboard (isolated copy)."""
import os, json, time, hashlib, shutil, subprocess, sys, signal, re
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
C = os.path.join(S, "livecopy"); URL = "http://127.0.0.1:8799/"; PY = os.path.join(R, "venv/bin/python")
res = []
def rec(n, ok, d=None):
    res.append({"scenario": n, "ok": bool(ok), "detail": d or {}}); print(("PASS " if ok else "FAIL ") + n + " :: " + json.dumps(d or {})[:260], flush=True)
md5 = lambda rel: hashlib.md5(open(os.path.join(C, rel), "rb").read()).hexdigest()
manifest = lambda: json.load(open(os.path.join(C, "data/run_manifest.json")))
ld = os.path.join(C, "data/_runs/_ui_launches")
nlaunch = lambda: len([f for f in os.listdir(ld) if f.endswith(".json")]) if os.path.isdir(ld) else 0
T = lambda: js("(() => { const m = document.getElementById('main'); return m.textContent + [...m.querySelectorAll('.badge')].map(b => ' ' + (b.getAttribute('title') || '')).join(''); })()")
runner_status = lambda: {k: v["status"] for k, v in json.loads(subprocess.run([PY, os.path.join(R, "scripts/run_stage.py"), "--status", "--json", "--root", C], capture_output=True, text=True).stdout).items()}
card = lambda aid: js(f"(() => {{ const a = document.querySelector('a.agent[href=\"#agent/{aid}\"]'); return a ? a.textContent + [...a.querySelectorAll('.badge')].map(b => ' ' + b.title).join('') : ''; }})()").replace("\n", " ")
hero = lambda: js("(document.querySelector('.hero-state')||{}).textContent||''")
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
cmd("Page.navigate", url=URL); pump(6)
rec("1. the root URL opens the live Dashboard (hero state, counters, agents, flow)",
    js("location.hash") in ("", "#dashboard") and bool(hero()) and js("document.querySelectorAll('.tile').length") == 5
    and js("document.querySelectorAll('.dag .node').length") >= 25, {"hero": hero()})
api_live = json.loads(js("(async () => JSON.stringify(await (await fetch('/api/live')).json()))()"))
rs_ = runner_status()
cards = {a["id"]: card(a["id"]) for a in api_live["agents"]}
agree = all(a["status"] in cards[a["id"]] for a in api_live["agents"])
stage_agree = all(rs_[s["id"]] == s["status"] for s in api_live["stages"])
rec("2. all eight agent cards shown with states equal to the backend (/api/live = run_stage.py --status)",
    len(cards) == 8 and all(cards.values()) and agree and stage_agree, {k: v[:50] for k, v in cards.items()})
for v in ["dashboard", "agent/10h", "live", "drugs", "dashboard"]:
    cmd("Page.navigate", url=URL + "#" + v); pump(3)
pump(4)
rec("9. opening and navigating pages starts no work", len(manifest()["history"]) == h0 and nlaunch() == n0)
# make agents stale (whitespace-only change: same content, new fingerprint) -> visible without refresh
p = os.path.join(C, "data/conflict_claims_curated.json"); open(p, "a").write("\n")
st_ok = wait_until(lambda: "Inputs changed" in hero() and "STALE" in card("10d"), 20)
rec("5a. dependency staleness appears without a refresh (hero + agent card)", bool(st_ok), {"hero": hero(), "10d": card("10d")[:60]})
# 3/4/5: Run all from the Dashboard -> runner executes -> transition shown
js("document.querySelector('button[data-pipeline]').click()")
acc = wait_until(lambda: "accepted" in T(), 15, 0.3)
done = wait_until(lambda: "Current against tracked inputs" in hero(), 120, 0.5)
st = runner_status()
rec("3/4/5b. Run all launched from the Dashboard; the runner re-ran the stale agents; Dashboard returns to current without refresh",
    bool(acc) and bool(done) and all(st[x] == "SUCCESS" for x in ("10a", "10d", "10e", "10g", "10h")) and len(manifest()["history"]) > h0,
    {"hero": hero(), "status": {x: st[x] for x in ("10a", "10d", "10e", "10g", "10h")}})
# a genuinely running stage, observed on the Dashboard: launch 10g from its agent page, pause its real process
cmd("Page.navigate", url=URL + "#agent/10g"); pump(4)
wait_until(lambda: js("!!document.querySelector('button[data-run=\"10g\"]') && !document.querySelector('button[data-run=\"10g\"]').disabled"), 30)
pid_file = os.path.join(S, "stopped11.pid")
if os.path.exists(pid_file): os.remove(pid_file)
catcher = subprocess.Popen([sys.executable, os.path.join(HERE, "catch_stop.py"), C, "10g", pid_file])
js("document.querySelector('button[data-run=\"10g\"]').click()")
catcher.wait(timeout=60)
stopped = open(pid_file).read().split() if os.path.exists(pid_file) else []
cmd("Page.navigate", url=URL + "#dashboard"); pump(2)
running = wait_until(lambda: hero() == "Running" and "RUNNING" in card("10g") and "running" in card("10g").lower()
                     and js("!!document.querySelector('.activity')"), 20, 0.3)
act = js("(document.querySelector('.activity')||{}).textContent||''").replace("\n", " ")
rec("5c. launched from an agent page; the Dashboard shows the real run RUNNING (hero, card, activity with elapsed time) without refresh",
    bool(running) and "%" not in act, {"activity": act[:160], "paused": stopped})
dis = js("[...document.querySelectorAll('button[data-run],button[data-pipeline]')].every(b => b.disabled)")
code = js("""(async () => { const s = await (await fetch('/api/session')).json();
  const r = await fetch('/api/run', {method:'POST', headers:{'Content-Type':'application/json','X-EviRep-Nonce':s.session_nonce}, body: JSON.stringify({pipeline:true})});
  return r.status })()""")
rec("concurrency: while running, Run controls are disabled and a second launch is refused (409)", dis and code == 409, {"status": code})
# 8: server restart while the stage runs
subprocess.run(["pkill", "-f", "ui/server.py --root " + C])
lost = wait_until(lambda: "lost" in js("document.getElementById('runstate').textContent"), 30)
subprocess.Popen([PY, os.path.join(R, "ui/server.py"), "--root", C, "--port", "8799"], stdout=open(os.path.join(S, "server8799c.log"), "w"), stderr=subprocess.STDOUT, start_new_session=True)
back = wait_until(lambda: "lost" not in js("document.getElementById('runstate').textContent") and hero() == "Running", 60, 1)
rec("8. server restarted mid-run: connection loss shown, then reconnects and still shows the real run", bool(lost) and bool(back))
for p_ in stopped: os.kill(int(p_), signal.SIGCONT)
fin = wait_until(lambda: hero() not in ("Running", "") and "RUNNING" not in card("10g"), 90)
st = runner_status()
rec("5d. the resumed run finishes; the Dashboard shows it done and, truthfully, its dependant 10h now STALE (no refresh)",
    bool(fin) and st["10g"] == "SUCCESS" and st["10h"] == "STALE" and "Inputs changed" in hero() and "STALE" in card("10h"),
    {"hero": hero(), "10g": st["10g"], "10h": st["10h"]})
# 6/7: real failure from the agent page; previous output kept; error + log visible
gaps_before = md5("data/completeness_gaps.json")
cc = os.path.join(C, "data/conflict_context.json"); shutil.copy(cc, cc + ".bak"); open(cc, "w").write("{corrupt")
cmd("Page.navigate", url=URL + "#agent/10h"); pump(3)
wait_until(lambda: js("!!document.querySelector('button[data-run=\"10h\"]') && !document.querySelector('button[data-run=\"10h\"]').disabled"), 30)
js("document.querySelector('button[data-run=\"10h\"]').click()")
failed = wait_until(lambda: "FAILED" in T() and "Traceback" in T(), 60)
att = manifest()["stages"]["10h"]["last_attempt"]
rec("6. a real failure appears on the agent page with its error log (no refresh)", bool(failed) and att["status"] == "FAILED",
    {"attempt": att["status"], "log_excerpt": (re.findall(r"(\w+Error[^\n]{0,80})", T()) or [""])[0]})
rec("7. the failed run preserved the last validated output byte-identical", att["status"] == "FAILED" and md5("data/completeness_gaps.json") == gaps_before)
cmd("Page.navigate", url=URL + "#dashboard"); pump(4)
rec("6b. the Dashboard reports the failure (hero + failed counter + card)", "failed" in hero().lower() and "FAILED" in card("10h"), {"hero": hero(), "10h": card("10h")[:60]})
shutil.move(cc + ".bak", cc)
# 10/11: research views work and candidate evidence is traceable
views = {"drugs": 2000, "drugs/Acetylcysteine": 2000, "evidence": 1000, "mechanism": 300, "conflicts": 1000, "review": 1000,
         "compare": 200, "validation": 1000, "overview": 1000, "technical": 300, "agents": 1000, "pipeline": 1000, "live": 1000}
bad = {}
for v, mn in views.items():
    cmd("Page.navigate", url=URL + "#" + v); pump(3)
    t = T()
    if len(t) < mn or "internal error" in t or "failed to render" in t: bad[v] = len(t)
rec("10. research and diagnostics views render", not bad, bad)
cmd("Page.navigate", url=URL + "#drugs/Acetylcysteine"); pump(5)
t = T()
trace = {"rank": bool(re.search(r"\d+\s*(of|/)\s*90", t)), "dims": all(d in t.lower() for d in ("proximity", "clinical", "literature", "safety", "molecular")),
         "PMID": "PMID" in t or "pubmed" in t.lower(), "NCT": bool(re.search(r"NCT\d{8}", t)), "cutoff": "cutoff" in t.lower(),
         "not efficacy": bool(re.search(r"not (a )?(measure of )?efficacy|not efficacy|continued clinical investigation", t, re.I)),
         "source links": js("document.querySelectorAll('#main a[href^=\"http\"]').length") > 0}
rec("11. candidate evidence is traceable (rank, dimensions, PMIDs, NCT IDs, cutoff, links, not-efficacy)", all(trace.values()), trace)
# 12: layouts
over = {}
for w, h, mob in ((1440, 900, False), (390, 844, True)):
    cmd("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=2 if mob else 1, mobile=mob)
    for v in ["dashboard", "agent/10g", "live", "drugs", "drugs/Acetylcysteine", "review", "validation"]:
        cmd("Page.navigate", url=URL + "#" + v); pump(2.5); s_ = state(); over[f"{w}:{v}"] = s_["sw"] - s_["iw"]
hdr = js("document.querySelector('header').getBoundingClientRect().height")
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
rec("12. desktop 1440 and mobile 390: no horizontal page overflow on 7 views; mobile header compact", all(x <= 0 for x in over.values()) and hdr < 200,
    {"max_overflow": max(over.values()), "mobile_header_px": hdr})
# 13: console / requests (409 above was an intentional probe; 503/404 none expected)
failed_req = [(e["params"]["response"]["url"].split("8799")[-1], e["params"]["response"]["status"]) for e in events
              if e.get("method") == "Network.responseReceived" and e["params"]["response"]["status"] >= 400]
unexpected = [f for f in failed_req if not (f[0].startswith("/api/run") and f[1] == 409)]   # 409 = the intentional probe
errs = [e for e in events if e.get("method") == "Runtime.exceptionThrown"]
cons = [e for e in events if e.get("method") == "Runtime.consoleAPICalled" and e["params"].get("type") == "error"]
rec("13. no JS exceptions, console errors or failed required requests (only the intentional 409 probe)", not errs and not cons and not unexpected,
    {"exceptions": len(errs), "console_errors": len(cons), "failed": unexpected[:5]})
cmd("Page.navigate", url=URL + "#dashboard"); pump(4)
import base64
open(os.path.join(HERE, "app_dashboard.png"), "wb").write(base64.b64decode(cmd("Page.captureScreenshot", format="png")["data"]))
json.dump(res, open(os.path.join(HERE, "results11.json"), "w"), indent=1)
print("SUMMARY", sum(r["ok"] for r in res), "/", len(res))
