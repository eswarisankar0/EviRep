"""Minimal CDP driver: live-UI scenarios against the fixture server (copy root, port 8799)."""
import re, json, subprocess, sys, time, urllib.request, os, signal
from websockets.sync.client import connect

S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = "/Users/thrisha/Drup_Rep_PF/EviRep"
ROOT = os.path.join(S, "uicopy")
URL = "http://127.0.0.1:8799/"
tab = json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:9333/json/new?about:blank", method="PUT")))
ws = connect(tab["webSocketDebuggerUrl"], max_size=50_000_000)
mid = 0
events = []

def cmd(method, **params):
    global mid
    mid += 1
    ws.send(json.dumps({"id": mid, "method": method, "params": params}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == mid:
            if "error" in m:
                raise RuntimeError(m["error"])
            return m.get("result")
        events.append(m)

def js(expr):
    r = cmd("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
    if r.get("exceptionDetails"):
        raise RuntimeError(r["exceptionDetails"])
    return r["result"].get("value")

def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        try:
            m = json.loads(ws.recv(timeout=0.25))
            events.append(m)
        except TimeoutError:
            pass

def state():
    return js("""({run: document.getElementById('runstate').textContent, banner: document.getElementById('banner').hidden ? null : document.getElementById('banner').textContent,
      version: document.getElementById('main').dataset.version, busy: document.getElementById('main').getAttribute('aria-busy'),
      hash: location.hash, sw: document.documentElement.scrollWidth, iw: window.innerWidth})""")

def wait_for(pred, timeout=40, label=""):
    t0 = time.time()
    while time.time() - t0 < timeout:
        pump(0.5)
        st = state()
        if pred(st):
            return st, round(time.time() - t0, 1)
    raise AssertionError(f"timeout waiting for {label}: {state()}")

def sh(*args):
    p = subprocess.run(list(args), capture_output=True, text=True, cwd=R)
    return p.returncode, (p.stdout + p.stderr).strip().splitlines()[-1:] 

results = []
def record(name, ok, detail):
    results.append({"scenario": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + " :: " + json.dumps(detail)[:400], flush=True)

cmd("Runtime.enable"); cmd("Log.enable"); cmd("Network.enable"); cmd("Page.enable")
cmd("Page.navigate", url=URL + "#pipeline")
pump(4)
st0 = state()
record("initial load", st0["run"] and st0["busy"] == "false", st0)

PY = R + "/venv/bin/python"
RS = [PY, R + "/scripts/run_stage.py"]
def man():
    return json.load(open(os.path.join(ROOT, "data/run_manifest.json")))
def status06():
    return man()["stages"]["06"]
def sha(rel):
    import hashlib
    return hashlib.sha256(open(os.path.join(ROOT, rel), "rb").read()).hexdigest()

# --- 12. viewing every page launches nothing ---------------------------------
hist0 = len(man().get("history", []))
for v in ["overview", "drugs", "evidence", "mechanism", "conflicts", "compare", "validation", "technical", "pipeline", "agents", "cases", "drugs/Droxidopa"]:
    js(f"location.hash = '#{v}'"); pump(1.5)
record("12 page views launch no stage", len(man().get("history", [])) == hist0, {"history_before": hist0, "after": len(man().get("history", []))})

# --- 1/2/3 terminal run of a diagnostic stage -> browser updates, VPS untouched -----
js("location.hash = '#pipeline'"); pump(2)
v0 = state()["version"]; vps_before = sha("data/vps_scores_v2.csv")
code, tail = sh(*RS, "10d", "--root", ROOT)
rid = man()["stages"]["10d"]["last_attempt"]["run_id"]
st, dt = wait_for(lambda s: s["version"] != v0 and s["busy"] == "false", label="version change after 10d")
shown = js(f"document.getElementById('main').textContent.includes('{rid}')")
record("1-3 terminal run -> manifest -> browser refresh", code == 0 and shown, {"exit": code, "run_id": rid, "seconds_to_refresh": dt, "run_id_visible": shown, "run": st["run"]})
s06 = json.loads(subprocess.run(RS + ["--status", "--json", "--root", ROOT], capture_output=True, text=True).stdout)["06"]
record("9 diagnostic run does not invalidate VPS", s06["status"] in ("ADOPTED", "SUCCESS") and sha("data/vps_scores_v2.csv") == vps_before,
       {"vps_status": s06["status"]})

# --- 5/6/7 failed VPS run: not fresh, last good retained & named -----------------
prox = os.path.join(ROOT, "data/network_proximity.csv")
good = open(prox).read()
open(prox, "w").write("garbage\n")
v0 = state()["version"]
code, tail = sh(*RS, "06", "--root", ROOT)
open(prox, "w").write(good)
st, dt = wait_for(lambda s: s["banner"] and "FAILED" in s["banner"], label="failed banner")
la = status06()["last_attempt"]; ls = status06()["last_success"]
record("5-7 failed run shown as failure, last good retained", code == 1 and la["status"] == "FAILED" and sha("data/vps_scores_v2.csv") == vps_before
       and ls["run_id"] in st["banner"], {"exit": code, "attempt": la["run_id"], "retained": ls["run_id"], "banner": st["banner"][:300], "seconds": dt})

# --- 4 upstream change makes VPS and dependants stale --------------------------
saf = os.path.join(ROOT, "data/safety_signal.csv")
with open(saf, "a") as fh:
    fh.write("\n")
st, dt = wait_for(lambda s: s["banner"] and "STALE" in s["banner"], label="stale banner")
allst = json.loads(subprocess.run(RS + ["--status", "--json", "--root", ROOT], capture_output=True, text=True).stdout)
record("4 changed upstream input -> STALE", allst["06"]["status"] == "STALE" and allst["10f"]["status"] == "STALE",
       {"06": allst["06"]["status"], "10f": allst["10f"]["status"], "eval": allst["eval"]["status"], "banner": st["banner"][:200]})

# --- 8 successful republish: every view uses the new published version ------------
js("location.hash = '#drugs'"); pump(2)
v0 = state()["version"]
code, tail = sh(*RS, "06", "--root", ROOT)
st, dt = wait_for(lambda s: s["version"] != v0 and s["busy"] == "false", label="refresh after 06")
new_id = status06()["last_success"]["run_id"]
seen = {}
for v in ["drugs", "overview", "compare", "validation", "drugs/Droxidopa"]:
    js(f"location.hash = '#{v}'"); pump(2)
    seen[v] = js(f"document.getElementById('main').dataset.version") == state()["version"]
api_run = json.load(urllib.request.urlopen(URL + "api/status"))["vps"]["displayed_run_id"]
record("8 new VPS published; views share one data version", code == 0 and all(seen.values()) and api_run == new_id
       and status06()["last_success"]["validation_ok"], {"exit": code, "run_id": new_id, "views": seen, "seconds": dt, "banner": st["banner"]})

# --- 10 missing artefact is not shown as zero findings -----------------------------
se = os.path.join(ROOT, "data/safety_evidence.json"); os.rename(se, se + ".hidden")
js("location.hash = '#drugs/Sertraline'"); pump(5)
panels = js("[...document.querySelectorAll('#main section')].map(s => s.textContent.replace(/\\s+/g, ' '))")
os.rename(se + ".hidden", se)
p10f = [t for t in panels if "(agent 10f)" in t]
p10h = [t for t in panels if "(agent 10h)" in t]
record("10 missing artefact shown as missing (not zero)", len(p10f) == 1 and "artefact missing" in p10f[0] and not re.search(r"\d+ reports", p10f[0])
       and len(p10h) == 1 and "STALE" in p10h[0], {"10f": p10f[0][:120] if p10f else None, "10h": p10h[0][:160] if p10h else None})

# --- 11 server suspended / stopped -> lost -> recovers -----------------------------
pid = int(subprocess.run(["lsof", "-tnP", "-iTCP:8799", "-sTCP:LISTEN"], capture_output=True, text=True).stdout.split()[0])
os.kill(pid, signal.SIGSTOP)
try:
    st, dt = wait_for(lambda s: "lost" in s["run"], timeout=40, label="lost while suspended")
    lost_t = dt
finally:
    os.kill(pid, signal.SIGCONT)
st, dt = wait_for(lambda s: "lost" not in s["run"], timeout=60, label="recovery after resume")
record("11a suspended server detected (fetch timeout) and recovered", True, {"seconds_to_detect": lost_t, "seconds_to_recover": dt, "run": st["run"]})
os.kill(pid, signal.SIGTERM); time.sleep(1)
st, dt = wait_for(lambda s: "lost" in s["run"], timeout=30, label="lost after kill")
fails = js("pollFailures")
pump(20)
fails2 = js("pollFailures")
srv = subprocess.Popen([PY, R + "/ui/server.py", "--root", ROOT, "--port", "8799"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
st, dt = wait_for(lambda s: "lost" not in s["run"], timeout=60, label="recovery after restart")
record("11b stopped server: backoff then recovery", fails2 - fails <= 3, {"poll_failures_in_20s": fails2 - fails, "seconds_to_recover": dt})

# --- 13 390px width ----------------------------------------------------------------
cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
over = {}
for v in ["overview", "drugs", "evidence", "mechanism", "conflicts", "compare", "validation", "technical", "pipeline", "agents", "cases", "drugs/Droxidopa"]:
    js(f"location.hash = '#{v}'"); pump(2)
    s = state(); over[v] = s["sw"] - s["iw"]
record("13 no horizontal page scroll at 390px", all(x <= 0 for x in over.values()), over)
cmd("Emulation.clearDeviceMetricsOverride")

# --- 14 console errors / secrets / external hosts ------------------------------------
errs = [e["params"] for e in events if e.get("method") == "Runtime.exceptionThrown"]
cons = [e["params"]["args"][0].get("value") for e in events if e.get("method") == "Runtime.consoleAPICalled" and e["params"]["type"] == "error"]
logs = [e["params"]["entry"] for e in events if e.get("method") == "Log.entryAdded" and e["params"]["entry"]["level"] == "error"]
hosts = sorted({urllib.parse.urlparse(e["params"]["request"]["url"]).netloc for e in events if e.get("method") == "Network.requestWillBeSent"})
methods = sorted({e["params"]["request"]["method"] for e in events if e.get("method") == "Network.requestWillBeSent"})
body = js("document.documentElement.outerHTML")
import re
secret = re.findall(r"(?i)(api[_-]?key|token|secret)\s*[=:]\s*['\"]?[A-Za-z0-9]{16,}", body)
net_err_logs = [l["text"][:120] for l in logs]
record("14 console/exception/secrets/external", not errs and not cons and not secret and hosts == ["127.0.0.1:8799"] and methods == ["GET"],
       {"exceptions": len(errs), "console_errors": cons[:3], "log_errors": net_err_logs[:6], "hosts": hosts, "methods": methods, "secret_hits": len(secret)})
srv.terminate()
json.dump(results, open(os.path.join(S, "cdp", "results.json"), "w"), indent=1)
print("SUMMARY", sum(r["ok"] for r in results), "/", len(results))
