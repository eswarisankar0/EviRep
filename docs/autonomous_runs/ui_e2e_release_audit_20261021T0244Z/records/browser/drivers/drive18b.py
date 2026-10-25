"""Targeted check of the one control drive18 recorded as NO_EFFECT: 'Clear filters' on a clean page has nothing to clear.
Set every filter first, then clear, and assert that all values and the full row count are restored (real Chrome, :8799)."""
import os, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "drive.py")).read().split("results = []")[0])
cmd("Runtime.enable"); cmd("Page.enable")
cmd("Page.navigate", url="http://127.0.0.1:8799/#drugs"); pump(5)
def ready(t=12):
    end = time.time() + t
    while time.time() < end:
        pump(0.2)
        if js("document.getElementById('main').getAttribute('aria-busy') === 'false' && !!document.getElementById('freset')"): return
ready()
rows = lambda: js("document.querySelectorAll('#rankbody tr').length")
full = rows()
js("""{ const q = document.getElementById('q'); q.value = 'pine'; q.dispatchEvent(new Event('input', {bubbles: true}));
  for (const [id, v] of [['flabel','1'],['fmiss','complete']]) { const e = document.getElementById(id); e.value = v; e.dispatchEvent(new Event('change', {bubbles: true})); } }"""); pump(0.8)
filtered, count_f = rows(), js("document.getElementById('rankcount').textContent")
js("document.getElementById('freset').click()"); pump(0.8)
after = {"rows": rows(), "q": js("document.getElementById('q').value"), "flabel": js("document.getElementById('flabel').value"),
         "fmiss": js("document.getElementById('fmiss').value"), "fconf": js("document.getElementById('fconf').value"),
         "count": js("document.getElementById('rankcount').textContent")}
ok = filtered < full and after["rows"] == full and not any(after[k] for k in ("q", "flabel", "fmiss", "fconf"))
res = {"full_rows": full, "filtered_rows": filtered, "count_when_filtered": count_f, "after_clear": after, "result": "PASS" if ok else "FAIL"}
json.dump(res, open(os.path.join(HERE, "results18b.json"), "w"), indent=1); print(res)
import urllib.request as _u; _u.urlopen(f"http://127.0.0.1:9333/json/close/{tab['id']}")
