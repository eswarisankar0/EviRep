"""
Independent re-computation of the equal-weight VPS from the RAW stage outputs.

Deliberately does NOT import scripts/06_vps_fusion.py. The rules below are
re-implemented from the written specification (DECISIONS D-002, D-004; the
stage docstrings) with a hand-written rank function, so an error in stage 06
cannot be reproduced by its own verifier.

Specification verified here
  pool        compounds with >= 1 row in clinical_maturity_precutoff_clean.csv
              that are also in pd_candidates_filtered.csv
  raw values  proximity_z (network_proximity.csv; lower = closer = better)
              max phase rank over pool trials (NA 0, EARLY_PHASE1 1, PHASE1 2,
                PHASE2 3, PHASE3 4, PHASE4 5; higher = better)
              effective_independent_count (literature_independence.csv; higher = better)
              safety risk = serious_term_count + 5 * boxed_warning, only when an
                openFDA label exists (lower = better)
              molecular_plausibility_score, only when n_targets > 0 (higher = better)
  missing     proximity / clinical / literature: pool median of the raw value
                (imputed, then ranked; current stage 06 flags these in dimensions_imputed,
                 but the approved file predates that column, D-024/B-003)
              safety without label, molecular without target: neutral rank 0.5,
                flagged in dimensions_missing (D-004)
  rank        percentile rank = average 1-based rank / n_measured (ties averaged);
              "lower is better" dimensions use 1 - that value
  fusion      VPS_equal    = mean(r_proximity, r_clinical, r_literature, r_safety)
              VPS_equal_5d = mean of those four and r_molecular
  label       1 iff a ground-truth row remains after removing the trials listed
              in label_role_exclusions.csv

    ./venv/bin/python scripts/vps_verify.py [--scores data/vps_scores_v2.csv]
Exit 0 when every compound, rank and score matches within TOL; 1 otherwise.
"""

import argparse
import csv
import json
import math
import os
import sys

TOL = 1e-9
PHASE = {"": 0, "NA": 0, "EARLY_PHASE1": 1, "PHASE1": 2, "PHASE2": 3, "PHASE3": 4, "PHASE4": 5}
NEUTRAL = 0.5


def _rows(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _float(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def pct_rank(values, invert=False, convention="legacy"):
    """{key: rank in (0, 1]} over keys with a non-None value; ties get the average position."""
    items = sorted((v, k) for k, v in values.items() if v is not None)
    n, out, i = len(items), {}, 0
    while i < n:
        j = i
        while j + 1 < n and items[j + 1][0] == items[i][0]:
            j += 1
        avg = (i + 1 + j + 1) / 2.0
        q = avg / n if convention == "legacy" else (avg - 0.5) / n      # "midrank": D-024 candidate
        for _, k in items[i:j + 1]:
            out[k] = 1 - q if invert else q
        i = j + 1
    return out


def _median(xs):
    xs = sorted(xs)
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2.0


def recompute(root=".", convention="legacy"):
    j = lambda p: os.path.join(root, p)
    cand = {r["compound_name"] for r in _rows(j("data/pd_candidates_filtered.csv"))}
    clin = [r for r in _rows(j("data/clinical_maturity_precutoff_clean.csv"))]
    pool = sorted({r["compound_name"] for r in clin} & cand)
    phase = {}
    for r in clin:
        if r["compound_name"] in pool:
            phase[r["compound_name"]] = max(phase.get(r["compound_name"], 0), PHASE.get(r.get("phase") or "", 0))
    prox = {r["compound_name"]: _float(r["proximity_z"]) for r in _rows(j("data/network_proximity.csv"))}
    lit = {r["compound_name"]: _float(r["effective_independent_count"]) for r in _rows(j("data/literature_independence.csv"))}
    risk, labelled = {}, {}
    for r in _rows(j("data/safety_signal.csv")):
        has = r["has_label"] == "True"
        labelled[r["compound_name"]] = has
        if has:
            risk[r["compound_name"]] = _float(r["serious_term_count"]) + (5 if r["boxed_warning"] == "True" else 0)
    mol = {}
    for r in _rows(j("data/molecular_pathway.csv")):
        nt = _float(r.get("n_targets"))
        mol[r["compound_name"]] = None if nt == 0 else _float(r["molecular_plausibility_score"])

    def impute(d):
        vals = {c: d.get(c) for c in pool}
        med = _median([v for v in vals.values() if v is not None])
        return {c: (v if v is not None else med) for c, v in vals.items()}, [c for c, v in vals.items() if v is None]

    p_vals, p_imp = impute(prox)
    c_vals, c_imp = impute(phase)
    l_vals, l_imp = impute(lit)
    k = {"convention": convention}
    r = {"proximity": pct_rank(p_vals, invert=True, **k), "clinical": pct_rank(c_vals, **k),
         "literature": pct_rank(l_vals, **k),
         "safety": pct_rank({c: risk.get(c) for c in pool}, invert=True, **k),
         "molecular": pct_rank({c: mol.get(c) for c in pool}, **k)}
    gt = _rows(j("data/ground_truth_postcutoff_clean.csv"))
    excl = {e["nct_id"] for e in _rows(j("data/label_role_exclusions.csv"))} if os.path.exists(
        j("data/label_role_exclusions.csv")) else set()
    pos = {g["compound_name"] for g in gt if g["nct_id"] not in excl}
    out = {}
    for c in pool:
        ranks = {d: r[d].get(c, NEUTRAL) for d in r}
        missing = sorted(d for d in ("safety", "molecular") if c not in r[d])
        out[c] = {**{f"r_{d}": v for d, v in ranks.items()},
                  "VPS_equal": sum(ranks[d] for d in ("proximity", "clinical", "literature", "safety")) / 4,
                  "VPS_equal_5d": sum(ranks.values()) / 5,
                  "missing": missing, "label": int(c in pos)}
    return out, {"proximity": p_imp, "clinical": c_imp, "literature": l_imp}


def compare(expected, scores_path):
    saved = {r["compound_name"]: r for r in _rows(scores_path)}
    problems = []
    if set(saved) != set(expected):
        problems.append(f"pool differs: only saved {sorted(set(saved) - set(expected))}, "
                        f"only recomputed {sorted(set(expected) - set(saved))}")
    if len(saved) != len(_rows(scores_path)):
        problems.append("duplicate compounds in saved scores")
    max_diff = 0.0
    for c in sorted(set(saved) & set(expected)):
        e, s = expected[c], saved[c]
        for col in ("r_proximity", "r_clinical", "r_literature", "r_safety", "r_molecular", "VPS_equal", "VPS_equal_5d"):
            sv = _float(s.get(col))
            if sv is None:
                problems.append(f"{c}: {col} missing or non-finite in saved scores")
                continue
            d = abs(sv - e[col])
            max_diff = max(max_diff, d)
            if d > TOL:
                problems.append(f"{c}: {col} saved {sv} recomputed {e[col]}")
        flags = sorted(x for x in (s.get("dimensions_missing") or "").split("|") if x)
        if flags != e["missing"]:
            problems.append(f"{c}: dimensions_missing saved {flags} recomputed {e['missing']}")
        if int(float(s["label"])) != e["label"]:
            problems.append(f"{c}: label saved {s['label']} recomputed {e['label']}")
    rank = lambda d, col: {c: i + 1 for i, c in enumerate(sorted(d, key=lambda c: (-float(d[c][col]), c)))}
    rs, re_ = rank(saved, "VPS_equal_5d"), rank(expected, "VPS_equal_5d")
    rank_moves = {c: (rs[c], re_[c]) for c in rs if c in re_ and rs[c] != re_[c]}
    return {"ok": not problems and not rank_moves, "tolerance": TOL, "max_abs_diff": max_diff,
            "n_compounds": len(expected), "problems": problems[:50], "rank_differences": rank_moves}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Independently recompute the equal-weight VPS and compare")
    ap.add_argument("--root", default=".")
    ap.add_argument("--scores", default="data/vps_scores_v2.csv")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--rank-convention", choices=("legacy", "midrank"), default="legacy")
    args = ap.parse_args(argv)
    expected, imputed = recompute(args.root, args.rank_convention)
    res = compare(expected, os.path.join(args.root, args.scores))
    res["median_imputed_unflagged"] = imputed
    if args.json:
        print(json.dumps(res, indent=1))
    else:
        print(f"{args.scores}: {'MATCH' if res['ok'] else 'MISMATCH'}; {res['n_compounds']} compounds; "
              f"max |diff| {res['max_abs_diff']:.2e}; median-imputed (unflagged): {imputed}")
        for p in res["problems"][:20]:
            print("  " + p)
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
