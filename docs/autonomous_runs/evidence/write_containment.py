"""Run each offline agent stage via the runner in an isolated copy; assert it changed only its declared outputs."""
import hashlib, importlib.util, json, os, subprocess, sys
REPO = "/Users/thrisha/Drup_Rep_PF/EviRep"; COPY = sys.argv[1]; OUT = sys.argv[2]
spec = importlib.util.spec_from_file_location("rs", os.path.join(REPO, "scripts/run_stage.py")); rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
stages = {s["id"]: s for s in rs.load_stages()}
def snap():
    out = {}
    for d, dirs, files in os.walk(os.path.join(COPY, "data")):
        if "/data/_runs" in d: continue
        for f in files:
            p = os.path.join(d, f)
            with open(p, "rb") as fh: out[os.path.relpath(p, COPY)] = hashlib.md5(fh.read()).hexdigest()
    return out
res = []
for sid in ["10a", "10a-all", "10b", "10c", "review", "10d", "10e", "10f", "10g", "10h"]:
    before = snap()
    p = subprocess.run([os.path.join(REPO, "venv/bin/python"), os.path.join(REPO, "scripts/run_stage.py"), sid, "--root", COPY],
                       capture_output=True, text=True)
    after = snap()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    allowed = set(stages[sid]["outputs"]) | {"data/run_manifest.json", "data/.run_manifest.lock"}
    stray = [c for c in changed if c not in allowed]
    res.append({"stage": sid, "exit": p.returncode, "last_line": p.stdout.strip().splitlines()[-1][:90] if p.stdout.strip() else p.stderr[-200:],
                "changed": changed, "outside_declared_outputs": stray, "ok": p.returncode == 0 and not stray})
    print(("PASS " if res[-1]["ok"] else "FAIL ") + sid, "exit", p.returncode, "changed", len(changed), "stray", stray)
json.dump(res, open(OUT, "w"), indent=1)
print("SUMMARY", sum(r["ok"] for r in res), "/", len(res))
