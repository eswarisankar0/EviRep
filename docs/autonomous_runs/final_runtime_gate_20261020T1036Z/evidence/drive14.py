"""Slow / frozen server, next-step guidance, validity labels (real browser, isolated copy)."""
import os, json, time, subprocess, signal, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
C = os.path.join(S, "livecopy"); URL = "http://127.0.0.1:8799/"
res = []
def rec(n, ok, d=None, action=""):
    res.append({"check": n, "result": "PASS" if ok else "FAIL", "browser_action": action, "detail": d or {}, "real_process": True}); print(("PASS " if ok else "FAIL ") + n + " :: " + json.dumps(d or {})[:220], flush=True)
T = lambda: js("document.getElementById('main').textContent")
pill = lambda: js("document.getElementById('runstate').textContent")
def wait_until(fn, timeout=90, step=0.4):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v: return v
        pump(step)
    return None
cmd("Runtime.enable"); cmd("Page.enable"); cmd("Network.enable")
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
cmd("Page.navigate", url=URL); pump(6)
nxt = js("(document.querySelector('.next')||{}).textContent||''")
rec("Dashboard shows a 'Next step' derived from real state", "Next step" in nxt and len(nxt) > 20, {"next": nxt[:160]})
cards = js("[...document.querySelectorAll('a.agent')].map(a => a.textContent.replace(/\\s+/g,' '))")
rec("agent cards separate run status from output validity ('run' badge + 'output contract valid')",
    len(cards) == 8 and all(" run " in (" " + c + " ") and "contract valid" in c for c in cards), {"first": cards[0][:120]})
rec("results panel states that process success is not scientific validation", "Process success is not scientific validation" in T())
# stale input -> next step tells the user what to do
cc = os.path.join(C, "data/conflict_claims_curated.json"); open(cc, "a").write("\n")
adv = wait_until(lambda: "Run all permitted stages" in js("(document.querySelector('.next')||{}).textContent||''") and "Out of date" in js("(document.querySelector('.next')||{}).textContent||''"), 30)
rec("upstream change -> Next step says what is out of date and how to refresh it (no reload)", bool(adv), {"next": js("(document.querySelector('.next')||{}).textContent")[:200]})
# frozen server (SIGSTOP): requests hang -> single-flight, timeout, 'connection lost', then recovery
spid = int(subprocess.run(["pgrep", "-f", "ui/server.py --root " + C], capture_output=True, text=True).stdout.split()[0])
before = len([e for e in events if e.get("method") == "Network.requestWillBeSent" and "/api/status" in e["params"]["request"]["url"]])
os.kill(spid, signal.SIGSTOP)
t0 = time.time()
lost = wait_until(lambda: "lost" in pill(), 40, 0.5)
t_lost = round(time.time() - t0, 1)
pump(10)
during = [e for e in events if e.get("method") == "Network.requestWillBeSent" and "/api/status" in e["params"]["request"]["url"]][before:]
rec("frozen server: the page says 'connection lost — retrying' after the 15 s request timeout (stale data not presented as live)",
    bool(lost) and 12 <= t_lost <= 35, {"seconds": t_lost, "pill": pill()})
rec("frozen server: polling stays single-flight with backoff (no request pile-up)", len(during) <= 4, {"status_requests_in_25s": len(during)})
os.kill(spid, signal.SIGCONT)
back = wait_until(lambda: "lost" not in pill(), 60, 0.5)
rec("server unfrozen: the page recovers by itself and re-renders current state", bool(back) and "Next step" in T(), {"pill": pill()})
cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
js("location.hash='#dashboard'"); pump(3); s_ = state()
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
rec("390px: Dashboard with Next step has no horizontal overflow", s_["sw"] - s_["iw"] <= 0, {"overflow": s_["sw"] - s_["iw"]})
errs = [e for e in events if e.get("method") == "Runtime.exceptionThrown"]
cons = [e for e in events if e.get("method") == "Runtime.consoleAPICalled" and e["params"].get("type") == "error"]
rec("no JS exceptions or console errors (aborted requests during the freeze are handled)", not errs and not cons, {"exceptions": len(errs), "console": len(cons)})
json.dump(res, open(os.path.join(HERE, "results14.json"), "w"), indent=1)
import urllib.request as _u; _u.urlopen(f"http://127.0.0.1:9333/json/close/{tab['id']}")
print("SUMMARY", sum(r["result"] == "PASS" for r in res), "/", len(res))
