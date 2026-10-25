"""Exploratory: corrupt / empty one input per agent stage in an isolated copy; run the real runner; record outcome."""
import hashlib, json, os, shutil, subprocess, sys, tempfile
R = "/Users/thrisha/Drup_Rep_PF/EviRep"; PY = R + "/venv/bin/python"
SKIP = {"opentargets_20.11", "dailymed", "hetionet_edges.csv", "_runs", "_candidates", "_backup_contaminated_20261005"}
def ign(d, names): return [n for n in names if n in SKIP]
CASES = [("10a-all", "data/literature_provenance.csv"), ("10a", "data/conflict_claims_curated.json"), ("10b", "data/molecular_pathway_evidence.jsonl"),
         ("10c", "data/clinical_maturity_precutoff_clean.csv"), ("10d", "data/conflict_claims_curated.json"), ("10e", "data/cache/pubmed_efetch_case_claims.xml"),
         ("10f", "data/safety_signal.csv"), ("10g", "data/literature_independence.csv"), ("10h", "data/conflict_context.json")]
MODES = {"malformed": lambda p: open(p, "w").write("{not valid,,\n\x00garbage" if not p.endswith(".csv") else "x;y\n\x00,,,\n"),
         "empty": lambda p: open(p, "w").close(),
         "missing": lambda p: os.remove(p),
         "header_only": lambda p: open(p, "w").write(open(p + ".orig").readline() if p.endswith(".csv") else "[]" if p.endswith(".json") else "")}
md5 = lambda p: hashlib.md5(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None
sys.path.insert(0, R + "/scripts"); import importlib.util
sp = importlib.util.spec_from_file_location("srv", R + "/ui/server.py"); srv = importlib.util.module_from_spec(sp); sp.loader.exec_module(srv)
ST = {s["id"]: s for s in srv.STAGES}
base = tempfile.mkdtemp(prefix="agentfault_")
shutil.copytree(R + "/data", base + "/data", ignore=ign); os.makedirs(base + "/data/_runs")
out = []
for sid, rel in CASES:
    for mode, fn in MODES.items():
        if mode == "header_only" and not rel.endswith((".csv", ".json")): continue
        p = os.path.join(base, rel); shutil.copy(p, p + ".orig")
        outs = {o: md5(os.path.join(base, o)) for o in ST[sid]["outputs"]}
        man0 = json.load(open(base + "/data/run_manifest.json"))["stages"].get(sid, {})
        fn(p)
        r = subprocess.run([PY, R + "/scripts/run_stage.py", sid, "--root", base], capture_output=True, text=True, timeout=600)
        man = json.load(open(base + "/data/run_manifest.json"))["stages"][sid]
        outs2 = {o: md5(os.path.join(base, o)) for o in ST[sid]["outputs"]}
        env = None
        for o in ST[sid]["outputs"]:
            if o.endswith(".json") and os.path.exists(os.path.join(base, o)):
                try: env = json.load(open(os.path.join(base, o))).get("run_status")
                except Exception: env = "unreadable"
        L = srv.build_live(base); stbrief = next(x for x in L["stages"] if x["id"] == sid)
        out.append({"stage": sid, "input": rel, "mode": mode, "exit": r.returncode, "attempt": man["last_attempt"]["status"],
                    "last_success_unchanged": man.get("last_success") == man0.get("last_success"),
                    "outputs_unchanged": outs == outs2, "envelope_status_after": env,
                    "ui_overall": L["overall"]["state"], "ui_stage_status": stbrief["status"], "ui_attempt_failed": stbrief.get("latest_attempt_failed"),
                    "diag": (man["last_attempt"].get("diagnostics") or [{}])[-1].get("code") if man["last_attempt"].get("diagnostics") else None,
                    "tail": r.stdout.strip().splitlines()[-1][:160] if r.stdout.strip() else r.stderr.strip()[-160:]})
        print(json.dumps(out[-1]), flush=True)
        shutil.move(p + ".orig", p)
        # re-run cleanly so the next case starts from SUCCESS
        subprocess.run([PY, R + "/scripts/run_stage.py", sid, "--root", base], capture_output=True, text=True, timeout=600)
json.dump(out, open(sys.argv[1], "w"), indent=1)
shutil.rmtree(base)
