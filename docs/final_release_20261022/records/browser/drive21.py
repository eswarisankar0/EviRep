"""Read-only check on the live server (:8765): agent role badges no longer claim agents feed the score; 10c review count."""
import os, json
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
cmd("Runtime.enable"); cmd("Page.enable")
hist0 = len(json.load(open(os.path.join(R, "data/run_manifest.json")))["history"])
out = {}
cmd("Page.navigate", url="http://127.0.0.1:8765/#run"); pump(6)
t = js("document.getElementById('main').innerText")
out["run: 'does not change the score' shown"] = "does not change the score" in t
out["run: 'feeds the score' absent"] = "eeds the score" not in t
for a in ("10c", "10b"):
    js(f"location.hash = 'agent/{a}'"); pump(4)
    t = js("document.getElementById('main').innerText")
    out[f"agent/{a}: badge says checks a score input"] = "checks a score input" in t
    out[f"agent/{a}: 'feeds the score' absent"] = "eeds the score" not in t
    if a == "10c":
        out["agent/10c: computed '28 links awaiting human review'"] = "28 links awaiting human review" in t
out["no stage started"] = len(json.load(open(os.path.join(R, "data/run_manifest.json")))["history"]) == hist0
out["js exceptions"] = sum(1 for e in events if e.get("method") == "Runtime.exceptionThrown")
print(json.dumps(out, indent=1))
import urllib.request as _u; _u.urlopen(f"http://127.0.0.1:9333/json/close/{tab['id']}")
