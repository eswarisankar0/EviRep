"""Full-page screenshots + simple page metrics for a list of routes. usage: shots.py BASEURL OUTDIR PREFIX route1 route2 ..."""
import os, sys, base64, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
base, out, prefix, routes = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
cmd("Runtime.enable"); cmd("Page.enable")
metrics = {}
for w, h, mob, tag in ((1440, 900, False, "desktop"), (390, 844, True, "mobile")):
    cmd("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=mob)
    cmd("Page.navigate", url=base); pump(5)
    for r in routes:
        if tag == "mobile" and r not in routes[:6]: continue
        t0 = time.time()
        js(f"location.hash = {json.dumps(r)}")
        for _ in range(60):
            pump(0.25)
            if js("document.getElementById('main').getAttribute('aria-busy') === 'false'"): break
        dt = round(time.time() - t0, 2)
        pump(0.8)
        ph = min(js("document.documentElement.scrollHeight"), 6000)
        cmd("Emulation.setDeviceMetricsOverride", width=w, height=ph, deviceScaleFactor=1, mobile=mob)
        pump(0.5)
        shot = cmd("Page.captureScreenshot", format="png")
        fn = f"{prefix}_{tag}_{r.replace('/', '_') or 'root'}.png"
        open(os.path.join(out, fn), "wb").write(base64.b64decode(shot["data"]))
        cmd("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=mob)
        if tag == "desktop":
            metrics[r] = js("""(() => { const m = document.getElementById('main'); const t = m.innerText;
              return {chars: t.length, raw_codes: (t.match(/\\b[A-Z]{3,}(?:_[A-Z]+)+\\b/g) || []).length,
                stage_ids: (t.match(/\\b(?:10[a-h]|04p|05h)\\b/g) || []).length, file_paths: (t.match(/\\b(?:data|scripts|docs)\\/[\\w.\\/-]+/g) || []).length,
                nav_buttons: document.querySelectorAll('#nav button').length, headings: m.querySelectorAll('h2,h3').length,
                charts: m.querySelectorAll('figure.chart').length, overflow: document.documentElement.scrollWidth - window.innerWidth,
                title: document.title}; })()""") | {"render_s": dt, "screenshot": fn}
json.dump(metrics, open(os.path.join(out, prefix + "_metrics.json"), "w"), indent=1)
print(json.dumps(metrics, indent=0)[:3000])
import urllib.request as _u; _u.urlopen(f"http://127.0.0.1:9333/json/close/{tab['id']}")
