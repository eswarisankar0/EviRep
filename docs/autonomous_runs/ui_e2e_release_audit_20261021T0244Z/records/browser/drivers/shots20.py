"""Read-only screenshots of the live server (:8765) on the final code."""
import os, json, time, base64
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
OUT = "/Users/thrisha/Drup_Rep_PF/EviRep/docs/autonomous_runs/ui_e2e_release_audit_20261021T0244Z/screenshots"
cmd("Runtime.enable"); cmd("Page.enable")
hist0 = len(json.load(open(os.path.join(R, "data/run_manifest.json")))["history"])
cmd("Emulation.setDeviceMetricsOverride", width=1440, height=1000, deviceScaleFactor=1, mobile=False)
cmd("Page.navigate", url="http://127.0.0.1:8765/"); pump(5)
for v in ["overview", "drugs", "drugs/Donepezil", "validation", "run", "live", "agents", "review"]:
    js(f"location.hash = {json.dumps(v)}"); pump(3)
    d = cmd("Page.captureScreenshot", format="png", captureBeyondViewport=False)["data"]
    open(os.path.join(OUT, v.replace("/", "_") + "_1440.png"), "wb").write(base64.b64decode(d)); print("shot", v)
cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
js("location.hash = 'live'"); pump(3)
open(os.path.join(OUT, "live_390.png"), "wb").write(base64.b64decode(cmd("Page.captureScreenshot", format="png")["data"]))
print("history unchanged:", len(json.load(open(os.path.join(R, "data/run_manifest.json")))["history"]) == hist0)
import urllib.request as _u; _u.urlopen(f"http://127.0.0.1:9333/json/close/{tab['id']}")
