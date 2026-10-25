"""Cross-file data-integrity audit (offline, read-only). Writes row-level findings (data_integrity_findings.csv) and a
summary (data_integrity_summary.json) to OUT. Each check states its expectation; every deviation is a row."""
import csv, hashlib, json, math, os, sys
R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
os.chdir(R)
OUT = sys.argv[1]
F = []          # row-level findings
def add(check, file, key, detail, severity="INFO"):
    F.append({"check": check, "severity": severity, "file": file, "key": key, "detail": detail})
def rd(p): return list(csv.DictReader(open(p, newline="", encoding="utf-8")))
def num(v):
    try: return float(v)
    except (TypeError, ValueError): return math.nan
md5 = lambda p: hashlib.md5(open(p, "rb").read()).hexdigest()

S = rd("data/vps_scores_v2.csv"); pool = [r["compound_name"] for r in S]; P = set(pool)
summary = {"pool": len(pool), "pool_unique": len(P)}
# 1 primary keys
for path, key in [("data/vps_scores_v2.csv", ("compound_name",)), ("data/molecular_pathway.csv", ("compound_name",)),
                  ("data/safety_signal.csv", ("compound_name",)), ("data/literature_independence.csv", ("compound_name",)),
                  ("data/network_proximity.csv", ("compound_name",)), ("data/clinical_maturity_precutoff_clean.csv", ("compound_name", "nct_id")),
                  ("data/ground_truth_postcutoff_clean.csv", ("compound_name", "nct_id")), ("data/pd_candidates_filtered.csv", ("compound_name",)),
                  ("data/label_role_exclusions.csv", ("compound_name", "nct_id")), ("data/feature_trial_roles_td038.csv", ("compound_name", "nct_id"))]:
    rows = rd(path); keys = [tuple(r[k] for k in key) for r in rows]
    dup = sorted({k for k in keys if keys.count(k) > 1})
    summary[f"rows:{path}"] = len(rows); summary[f"dup_keys:{path}"] = len(dup)
    for k in dup: add("primary_key_unique", path, "|".join(k), f"{keys.count(k)} rows share this key", "HIGH")
    blank = [i for i, k in enumerate(keys) if any(not x.strip() for x in k)]
    for i in blank: add("primary_key_nonblank", path, str(i), "blank key", "HIGH")
# 2 pool coverage in each dimension source (and stale extra rows)
for path, nm in [("data/molecular_pathway.csv", "molecular"), ("data/safety_signal.csv", "safety"),
                 ("data/literature_independence.csv", "literature"), ("data/network_proximity.csv", "proximity")]:
    names = {r["compound_name"] for r in rd(path)}
    miss = sorted(P - names); extra = names - P
    summary[f"pool_missing:{nm}"] = len(miss); summary[f"rows_outside_pool:{nm}"] = len(extra)
    for c in miss: add("pool_coverage", path, c, f"pool compound absent from the {nm} source", "MEDIUM")
filtered = {r["compound_name"] for r in rd("data/pd_candidates_filtered.csv")}
for c in sorted(P - filtered): add("pool_in_filtered_candidates", "data/vps_scores_v2.csv", c, "pool compound not in pd_candidates_filtered.csv", "HIGH")
pre = rd("data/clinical_maturity_precutoff_clean.csv"); pre_c = {r["compound_name"] for r in pre}
summary["pool_equals_filtered_and_precutoff"] = P == (pre_c & filtered)
for c in sorted((pre_c & filtered) ^ P): add("pool_definition", "data/vps_scores_v2.csv", c, "pool != filtered ∩ pre-cutoff-trial compounds", "HIGH")
# 3 non-finite / range checks in the score file
for r in S:
    for col in ("r_proximity", "r_clinical", "r_literature", "r_safety", "r_molecular", "VPS_equal", "VPS_equal_5d"):
        v = num(r[col])
        if not (0 <= v <= 1): add("rank_range_0_1", "data/vps_scores_v2.csv", r["compound_name"], f"{col}={r[col]}", "HIGH")
    if r["label"] not in ("0", "1", "0.0", "1.0"): add("label_binary", "data/vps_scores_v2.csv", r["compound_name"], f"label={r['label']}", "HIGH")
# 4 raw values in the score file equal their sources
mol = {r["compound_name"]: r for r in rd("data/molecular_pathway.csv")}
saf = {r["compound_name"]: r for r in rd("data/safety_signal.csv")}
lit = {r["compound_name"]: r for r in rd("data/literature_independence.csv")}
prox = {r["compound_name"]: r for r in rd("data/network_proximity.csv")}
phase_rank = {"NA": 0, "EARLY_PHASE1": 1, "PHASE1": 2, "PHASE2": 3, "PHASE3": 4, "PHASE4": 5}
mismatch = 0
for r in S:
    c = r["compound_name"]
    checks = [("molecular_plausibility_score", num(mol[c]["molecular_plausibility_score"]), num(r["molecular_plausibility_score"])),
              ("effective_independent_count", num(lit[c]["effective_independent_count"]), num(r["effective_independent_count"])),
              ("serious_term_count", num(saf[c]["serious_term_count"]), num(r["serious_term_count"]))]
    pz = num(prox[c]["proximity_z"]) if c in prox else math.nan
    if not math.isnan(pz): checks.append(("proximity_z", pz, num(r["proximity_z"])))
    else: add("proximity_imputed", "data/network_proximity.csv", c, f"raw proximity_z missing (n_targets_in_network={prox.get(c, {}).get('n_targets_in_network')}); score file holds the imputed value {r['proximity_z']}", "INFO")
    mpr = max((phase_rank.get(x["phase"], 0) for x in pre if x["compound_name"] == c), default=math.nan)
    checks.append(("max_phase_rank", float(mpr), num(r["max_phase_rank"])))
    checks.append(("n_trials", float(sum(1 for x in pre if x["compound_name"] == c)), num(r["n_trials"])))
    for col, src, val in checks:
        if not (math.isnan(src) and math.isnan(val)) and abs(src - val) > 1e-9:
            mismatch += 1; add("raw_value_equals_source", "data/vps_scores_v2.csv", c, f"{col}: source {src} vs score file {val}", "HIGH")
    if (saf[c]["has_label"] != "True") != (r["safety_label_missing"] == "True"):
        add("safety_missing_flag", "data/vps_scores_v2.csv", c, "safety_label_missing disagrees with safety_signal.has_label", "HIGH")
summary["raw_value_mismatches"] = mismatch
# 5 labels re-derived from files
post = rd("data/ground_truth_postcutoff_clean.csv"); excl = {(r["compound_name"], r["nct_id"]) for r in rd("data/label_role_exclusions.csv")}
pos = {r["compound_name"] for r in post if (r["compound_name"], r["nct_id"]) not in excl}
for r in S:
    if int(num(r["label"])) != int(r["compound_name"] in pos):
        add("label_rederived", "data/vps_scores_v2.csv", r["compound_name"], "label differs from post-cutoff file minus exclusions", "HIGH")
for k in excl:
    if k not in {(r["compound_name"], r["nct_id"]) for r in post}: add("exclusion_refers_to_label_trial", "data/label_role_exclusions.csv", "|".join(k), "exclusion row has no matching label trial", "HIGH")
# 6 cutoff semantics on every trial row
for r in pre:
    if not (r["first_posted"] and r["first_posted"] < "2021-01-01"): add("pre_cutoff_date", "data/clinical_maturity_precutoff_clean.csv", f"{r['compound_name']}|{r['nct_id']}", f"first_posted={r['first_posted']}", "HIGH")
for r in post:
    if not (r["first_posted"] and "2021-01-01" <= r["first_posted"] <= "2026-10-05"): add("post_cutoff_date", "data/ground_truth_postcutoff_clean.csv", f"{r['compound_name']}|{r['nct_id']}", f"first_posted={r['first_posted']}", "HIGH")
both = {r["nct_id"] for r in pre} & {r["nct_id"] for r in post}
for n in both: add("trial_in_both_windows", "clean trial files", n, "same NCT in features and labels", "HIGH")
# shared feature trials (many-to-many)
by = {}
for r in pre: by.setdefault(r["nct_id"], set()).add(r["compound_name"])
shared = {n: c for n, c in by.items() if len(c) > 1}
summary["shared_pre_trials"] = len(shared); summary["compounds_with_shared_trial"] = len(set().union(*shared.values())) if shared else 0
for n, c in sorted(shared.items()): add("shared_feature_trial", "data/clinical_maturity_precutoff_clean.csv", n, "credited to " + ", ".join(sorted(c)), "INFO")
# 7 report input fingerprints
rep = json.load(open("data/vps_evaluation_report.json"))
for p, h in (rep.get("inputs") or {}).items():
    ok = os.path.exists(p) and md5(p) == h
    if not ok: add("report_input_md5", "data/vps_evaluation_report.json", p, "md5 differs from the file now on disk", "HIGH")
summary["report_inputs_checked"] = len(rep.get("inputs") or {})
# 8 manifest fingerprints of the approved run
man = json.load(open("data/run_manifest.json"))
ls = man["stages"]["06"]["last_success"]
for kind in ("inputs", "outputs"):
    for p, h in (ls.get(kind) or {}).items():
        hv = h.get("md5") if isinstance(h, dict) else h
        if os.path.exists(p) and hv and md5(p) != hv: add("approved_run_fingerprint", "data/run_manifest.json", p, f"{kind} md5 differs", "HIGH")
summary["approved_run_id"] = ls.get("run_id"); summary["approved_run_code_fingerprint"] = ls.get("code") or ls.get("code_fingerprint")
summary["findings_by_severity"] = {s: sum(1 for x in F if x["severity"] == s) for s in ("HIGH", "MEDIUM", "INFO")}
with open(os.path.join(OUT, "data_integrity_findings.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=["check", "severity", "file", "key", "detail"]); w.writeheader(); w.writerows(F)
json.dump(summary, open(os.path.join(OUT, "data_integrity_summary.json"), "w"), indent=1)
print(json.dumps(summary, indent=1))
for x in F:
    if x["severity"] != "INFO": print(x)
