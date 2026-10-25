import os, json, time, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
COPY = os.path.join(S, "uicopy8")
res = []
def rec(n, ok, d=None):
    res.append({"scenario": n, "ok": bool(ok), "detail": d or {}}); print(("PASS " if ok else "FAIL ") + n + " :: " + json.dumps(d or {})[:260], flush=True)
cmd("Runtime.enable"); cmd("Page.enable"); cmd("Network.enable")
# --- U-02: single-flight polling, real browser, /api/status held by the Fetch domain ---
cmd("Page.navigate", url="http://127.0.0.1:8765/#overview"); pump(6)
cmd("Fetch.enable", patterns=[{"urlPattern": "*/api/status*", "requestStage": "Request"}])
paused = []
def drain(sec):
    end = time.time() + sec
    while time.time() < end:
        try:
            m = json.loads(ws.recv(timeout=0.2))
        except TimeoutError:
            continue
        if m.get("method") == "Fetch.requestPaused":
            paused.append(m["params"]["requestId"])
        else:
            events.append(m)
drain(6)                                  # wait for the next scheduled poll to be held
held = len(paused)
for _ in range(3):
    js("document.dispatchEvent(new Event('visibilitychange'))")
drain(2)
rec("one poll in flight: 3 visibility events start no second request", held == 1 and len(paused) == 1, {"held_before": held, "held_after": len(paused)})
t0 = time.time()
for rid in paused:
    cmd("Fetch.continueRequest", requestId=rid)
paused.clear()
drain(2)
rec("coalesced follow-up poll issued promptly after the held one completes", len(paused) == 1, {"followups": len(paused), "within_s": round(time.time() - t0, 1)})
for rid in paused:
    cmd("Fetch.continueRequest", requestId=rid)
cmd("Fetch.disable"); pump(2)
# --- R-04/U-01: corrupt manifest in the isolated copy ---
mp = os.path.join(COPY, "data", "run_manifest.json")
shutil.copy(mp, mp + ".bak")
cmd("Page.navigate", url="http://127.0.0.1:8799/#pipeline"); pump(6)
pill0 = js("document.getElementById('runstate').textContent")
open(mp, "w").write("{corrupt")
pump(7)
pill = js("document.getElementById('runstate').textContent")
banner = js("document.getElementById('banner').hidden ? '' : document.getElementById('banner').textContent")
main = js("document.getElementById('main').textContent")
rec("corrupt manifest: pill says run records unreadable (never 'current')", pill == "Run records unreadable" and "current" not in pill, {"before": pill0, "after": pill})
rec("corrupt manifest: VPS banner says UNKNOWN", "UNKNOWN" in banner, {"banner": banner[:120]})
rec("corrupt manifest: run table shows UNKNOWN with the reason", "UNKNOWN" in main and "unreadable" in main)
shutil.move(mp + ".bak", mp)
pump(8)
pill2 = js("document.getElementById('runstate').textContent")
rec("restored manifest: page recovers without reload", pill2 != "Run records unreadable", {"after_restore": pill2})
# --- eval warning visible (live) ---
cmd("Page.navigate", url="http://127.0.0.1:8765/#pipeline"); pump(6)
main = js("document.getElementById('main').textContent")
rec("live: eval's untracked-input warning is visible on the pipeline page", "not fingerprinted at the last success" in main)
errs = [e for e in events if e.get("method") == "Runtime.exceptionThrown"]
rec("no JS exceptions", not errs, {"n": len(errs)})
json.dump(res, open(os.path.join(HERE, "results8.json"), "w"), indent=1)
print("SUMMARY", sum(r["ok"] for r in res), "/", len(res))
