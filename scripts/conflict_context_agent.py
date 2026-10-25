"""
Conflict & Context Agent (architecture 10d) — DIAGNOSTIC, not part of VPS.

Question it answers: where does the persisted evidence for a compound DISAGREE,
and is the disagreement a genuine contradiction or a difference in context
(endpoint, population, design, dose, intervention scope, evidence domain)?

Inputs (all persisted; no network access):
  * data/conflict_claims_curated.json   claims transcribed from docs/CASE_STUDIES.md,
                                        each with its PMID / NCT and the doc section
  * data/cache/openfda_labels/*.json    raw openFDA labels cached by stage 05 v2 (D-003)
  * data/molecular_pathway_evidence.jsonl  stage 08 evidence chains (10b)
  * data/clinical_maturity_precutoff_clean.csv  accepted pre-cutoff PD trials
  * data/vps_scores_v2.csv              only to mark pool membership (no score is read)

Output: data/conflict_context.json — one record per compound with its claims,
pairwise comparisons, insufficient evidence and coverage, plus a compact
`synthesis_inputs` list for Stage 11 (Evidence Synthesis).

Design rules
  * No claim is generated from free text by judgement. Label claims come from
    fixed regular-expression rules over named label sections; every claim keeps
    its source identifier, date, section and a verbatim excerpt.
  * Directions are about the claim's own endpoint: SUPPORTS (favourable,
    significant), NULL_RESULT (no significant effect), OPPOSES (harm/worsening/
    risk), NEUTRAL (context only, e.g. a registered trial), UNCLEAR.
  * A disagreement is a DIRECT_CONTRADICTION only when nothing distinguishes the
    two claims. Otherwise it is classified by what does differ. Disagreements are
    never converted into a score or a penalty.
  * Missing evidence is reported as missing (coverage), never as agreement.
"""

import argparse
import glob
import json
import os
import sys
import re
from itertools import combinations

import pandas as pd

AGENT_VERSION = "10d-0.1"
CUTOFF = "2021-01-01"

CURATED = "data/conflict_claims_curated.json"
LABEL_DIR = "data/cache/openfda_labels"
MOLECULAR = "data/molecular_pathway_evidence.jsonl"
TRIALS = "data/clinical_maturity_precutoff_clean.csv"
POOL = "data/vps_scores_v2.csv"
OUT = "data/conflict_context.json"

DIRECTIONS = ("SUPPORTS", "NULL_RESULT", "OPPOSES", "NEUTRAL", "UNCLEAR")
DIRECTIONAL = {"SUPPORTS", "NULL_RESULT", "OPPOSES"}
DOMAINS = ("efficacy", "safety", "mechanism", "disease_risk", "clinical_activity", "diagnostic")
CONTEXT_AXES = ("endpoint_measure", "population", "design", "dose", "intervention_scope")
#: evidence levels, ordinal; a gap >= 2 is flagged as quality asymmetry
LEVEL = {"meta_analysis": 4, "systematic_review": 4, "rct": 3, "regulatory_label": 3,
         "observational": 2, "open_label": 1, "case_report": 1, "mechanistic": 0}
CLASS_PRIORITY = ("DIRECT_CONTRADICTION", "STATISTICAL_DISAGREEMENT", "CONTEXT_DIFFERENCE",
                  "CROSS_DOMAIN_TENSION", "UNCERTAIN_COMPARABILITY", "NON_COMPARABLE")
STOPPED = {"TERMINATED", "WITHDRAWN", "SUSPENDED"}


# ---------------------------------------------------------------- claims ----

def _temporal(date):
    if not date or not re.match(r"^\d{4}", str(date)):
        return "UNKNOWN"
    d = str(date)
    if len(d) == 4:                       # year only: decidable unless it is the cutoff year
        return "PRE_CUTOFF" if d < CUTOFF[:4] else ("POST_CUTOFF" if d > CUTOFF[:4] else
                                                    ("POST_CUTOFF" if CUTOFF.endswith("01-01") else "UNKNOWN"))
    return "PRE_CUTOFF" if d < CUTOFF else "POST_CUTOFF"


def normalise_claim(raw):
    """Validate one claim dict; return (claim, None) or (None, reason)."""
    if not isinstance(raw, dict):
        return None, "not an object"
    for key in ("claim_id", "compound", "source_id", "direction", "domain"):
        if not raw.get(key):
            return None, f"missing {key}"
    if raw["direction"] not in DIRECTIONS:
        return None, f"invalid direction {raw['direction']!r}"
    if raw["domain"] not in DOMAINS:
        return None, f"invalid domain {raw['domain']!r}"
    c = dict(raw)
    c.setdefault("endpoint_domain", None)
    for axis in CONTEXT_AXES:
        c.setdefault(axis, None)
    c.setdefault("effect", None)
    c.setdefault("overlap_group", None)
    c.setdefault("evidence_level", None)
    if not c.get("excerpt") and c.get("summary"):
        c["excerpt"], c["excerpt_type"] = c["summary"], f"paraphrase of {c.get('provenance')}"
    c["temporal"] = _temporal(c.get("source_date"))
    return c, None


def load_curated(path=CURATED, root="."):
    if not os.path.exists(path):
        return [], [{"source": os.path.relpath(path, root), "reason": "file missing"}]   # never an absolute path
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    claims, rejected, seen = [], [], set()
    for raw in payload.get("claims", []):
        if raw.get("claim_id") in seen:
            rejected.append({"claim": raw.get("claim_id"), "reason": "duplicate claim_id"})
            continue
        seen.add(raw.get("claim_id"))
        c, why = normalise_claim(dict(raw, source_type=raw.get("source_type", "curated_doc")))
        (claims.append(c) if c else rejected.append({"claim": raw.get("claim_id"), "reason": why}))
    return claims, rejected


# Label rules: (name, section regex, sentence regex, direction, domain, endpoint_domain, population)
_PD = r"parkinson'?s?(?:’s)? disease|parkinson’s disease|parkinson's disease"
LABEL_RULES = [
    ("diagnostic_indication", r"indications_and_usage", r"diagnostic", "NEUTRAL", "diagnostic", None, None),
    ("pd_population_indication", r"indications_and_usage", r"parkinson", "SUPPORTS", "efficacy",
     "approved_indication", "PD among other conditions (see excerpt)"),
    ("pd_aggravation_warning", r"warnings|precautions",
     r"parkinson[^.]{0,120}(aggravat|worsen|exacerbat)|(aggravat|worsen|exacerbat)[^.]{0,120}parkinson",
     "OPPOSES", "safety", "motor_worsening", "patients with PD"),
    ("contraindicated_in_pd", r"contraindications", r"parkinson", "OPPOSES", "safety",
     "contraindication", "patients with PD"),
    ("drug_induced_parkinsonism", r"adverse_reactions|warnings", r"\bparkinsonism\b|parkinsonian|extrapyramidal",
     "OPPOSES", "safety", "motor_worsening", "label study populations (not PD-specific)"),
    ("pd_drug_interaction", r"drug_interactions|do_not_use", r"parkinson", "NEUTRAL", "safety",
     "interaction", None),
]


def _window(sentence, pattern, width=170):
    """Verbatim excerpt centred on the first match, so the evidence term is always visible."""
    m = re.search(pattern, sentence, re.I) or re.search(r"parkinson|extrapyramidal", sentence, re.I)
    i, j = max(0, m.start() - width), min(len(sentence), m.end() + width)
    return ("…" if i else "") + sentence[i:j] + ("…" if j < len(sentence) else "")


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.;])\s+", text) if s.strip()]


def label_claims(compound, label, path):
    """Rule-based claims from one cached openFDA label (first matching rule per sentence)."""
    claims, used = [], set()
    meta = {"source_type": "openfda_label", "source_id": f"openFDA set_id {label.get('set_id')}",
            "source_date": _fmt_date(label.get("effective_time")), "design": "regulatory_label",
            "evidence_level": "regulatory_label", "provenance": path}
    for section, value in sorted(label.items()):
        if not isinstance(value, list) or not value or not isinstance(value[0], str) or section.endswith("_table"):
            continue
        for sentence in _sentences(" ".join(value)):
            if not re.search(r"parkinson|extrapyramidal", sentence, re.I):
                continue
            for name, sec_re, sent_re, direction, domain, endpoint, population in LABEL_RULES:
                if re.search(sec_re, section) and re.search(sent_re, sentence, re.I):
                    if name in used:                   # one claim per rule; other hits counted
                        for c in claims:
                            if c["rule"] == name:
                                c["n_matching_sentences"] += 1
                                if section not in c["sections"]:
                                    c["sections"].append(section)
                                if re.search(r"warning|precaution|contraindication|boxed", section):
                                    c["label_strength"] = "warning or contraindication"
                        break
                    used.add(name)
                    c, _ = normalise_claim(dict(
                        meta, claim_id=f"{compound}:label:{name}", compound=compound,
                        direction=direction, domain=domain, endpoint_domain=endpoint,
                        population=population, rule=name, sections=[section], n_matching_sentences=1,
                        label_strength=("warning or contraindication" if re.search(r"warning|precaution|contraindication|boxed", section)
                                        else "listed in label section (frequency/causality often not established)"),
                        excerpt=_window(sentence, sent_re), excerpt_type=f"verbatim, label section {section}"))
                    claims.append(c)
                    break
    return claims


def _fmt_date(v):
    v = str(v or "")
    return f"{v[:4]}-{v[4:6]}-{v[6:8]}" if re.fullmatch(r"\d{8}", v) else (v or None)


def molecular_claim(record, path):
    """One mechanism claim from a stage-08 evidence chain, or None when there is no target."""
    comps = ((record.get("scoring") or {}).get("components") or {})
    direct = comps.get("direct_target_disease")
    targets = record.get("targets") or []
    if not targets or direct is None:
        return None
    per = ((record.get("scoring") or {}).get("detail") or {}).get("direct_score_per_target") or {}
    top = max(per.items(), key=lambda kv: kv[1])[0] if per else None
    actions = sorted({(t.get("gene_symbol"), t.get("action_type")) for t in targets if t.get("gene_symbol")},
                     key=lambda x: (x[0] or "", x[1] or ""))
    direction = "SUPPORTS" if direct and direct > 0 else "NULL_RESULT"
    c, _ = normalise_claim({
        "claim_id": f"{record.get('drug')}:molecular", "compound": record.get("drug"),
        "source_type": "opentargets", "source_id": f"ChEMBL {record.get('chembl_id')} / Open Targets",
        "source_date": "2026-09", "direction": direction, "domain": "mechanism",
        "date_note": "Open Targets data version 26.09 (current snapshot, not cutoff-bounded; B-001)",
        "endpoint_domain": "target_disease_association", "design": "mechanistic",
        "evidence_level": "mechanistic", "provenance": path,
        "excerpt": (f"direct target-PD component {direct:.3f}; strongest target {top}; "
                    f"targets/action types: " + ", ".join(f"{g} ({a})" for g, a in actions[:8])),
        "excerpt_type": "derived summary of persisted scoring fields",
        "caveat": "association is undirected: an antagonist and an agonist of the same target score alike"})
    return c


def trial_context(compound, rows):
    """Pre-cutoff trials as context (registration is not a result)."""
    out = []
    for r in rows:
        stopped = str(r.get("status")) in STOPPED
        c, _ = normalise_claim({
            "claim_id": f"{compound}:trial:{r['nct_id']}", "compound": compound,
            "source_type": "clinicaltrials", "source_id": r["nct_id"], "source_date": r.get("first_posted"),
            "direction": "UNCLEAR" if stopped else "NEUTRAL", "domain": "clinical_activity",
            "design": "registered_trial", "provenance": TRIALS,
            "excerpt": f"phase {r.get('phase')}, status {r.get('status')}",
            "excerpt_type": "registry fields",
            "note": ("stopped trial; reason not retrieved, so it is not evidence against the drug"
                     if stopped else "registration only; no results were retrieved")})
        out.append(c)
    return out


# ----------------------------------------------------------- comparison ----

def _differs(a, b, axis):
    va, vb = a.get(axis), b.get(axis)
    if va is None or vb is None:
        return "unknown"
    return "differs" if str(va).strip().lower() != str(vb).strip().lower() else "same"


RATIO_MEASURES = {"HR", "RR", "OR", "ARR", "IRR", "RATIO", "HAZARD RATIO", "RISK RATIO", "ODDS RATIO"}


def _comparable_agreement(directional):
    """True when two claims from different sources agree in direction on comparable ground: the same
    domain and endpoint (or an unrecorded endpoint), or - mirroring CROSS_DOMAIN_TENSION in compare() -
    different domains that both SUPPORT or both OPPOSE. This is what NO_DISAGREEMENT_DETECTED asserts."""
    for a, b in combinations(directional, 2):
        if a["source_id"] == b["source_id"] or a["direction"] != b["direction"]:
            continue
        if a["domain"] != b["domain"]:
            if a["direction"] in ("SUPPORTS", "OPPOSES"):
                return True
        elif not (a.get("endpoint_domain") and b.get("endpoint_domain") and a["endpoint_domain"] != b["endpoint_domain"]):
            return True
    return False


def compare(a, b):
    """Classify one pair of claims about the same compound, or None if not a disagreement."""
    if a["source_id"] == b["source_id"]:
        return None                                          # one source's mixed endpoints
    if a["direction"] not in DIRECTIONAL or b["direction"] not in DIRECTIONAL:
        return None
    if a["direction"] == b["direction"]:
        return None                                          # consistent
    flags = []
    if a.get("overlap_group") and a.get("overlap_group") == b.get("overlap_group"):
        flags.append("non_independent_sources")
    la, lb = LEVEL.get(a.get("evidence_level")), LEVEL.get(b.get("evidence_level"))
    if la is not None and lb is not None and abs(la - lb) >= 2:
        flags.append("quality_asymmetry")
    if "POST_CUTOFF" in (a["temporal"], b["temporal"]):
        flags.append("uses_post_cutoff_evidence")

    if a["domain"] != b["domain"]:
        if {"SUPPORTS", "OPPOSES"} == {a["direction"], b["direction"]}:
            cls, axes = "CROSS_DOMAIN_TENSION", ["domain"]
        else:
            return None
    elif a.get("endpoint_domain") and b.get("endpoint_domain") and a["endpoint_domain"] != b["endpoint_domain"]:
        cls, axes = "NON_COMPARABLE", ["endpoint_domain"]
    else:
        ea, eb = a.get("effect") or {}, b.get("effect") or {}
        same_measure = ea.get("measure") and ea.get("measure") == eb.get("measure")
        null = 1.0 if str(ea.get("measure") or "").upper() in RATIO_MEASURES else 0.0   # no-effect value
        if (same_measure and isinstance(ea.get("estimate"), (int, float)) and isinstance(eb.get("estimate"), (int, float))
                and (ea["estimate"] > null) == (eb["estimate"] > null)
                and "OPPOSES" not in (a["direction"], b["direction"])):
            cls, axes = "STATISTICAL_DISAGREEMENT", ["significance"]
        else:
            status = {ax: _differs(a, b, ax) for ax in CONTEXT_AXES}
            axes = [ax for ax, s in status.items() if s == "differs"]
            if axes:
                cls = "CONTEXT_DIFFERENCE"
            elif any(s == "unknown" for s in status.values()) or not a.get("endpoint_domain"):
                cls, axes = "UNCERTAIN_COMPARABILITY", [ax for ax, s in status.items() if s == "unknown"]
            else:
                cls = "DIRECT_CONTRADICTION"
    return {"classification": cls, "differing_axes": axes, "flags": flags,
            "side_a": _side(a), "side_b": _side(b), "rationale": _rationale(cls, a, b, axes, flags)}


def _side(c):
    return {k: c.get(k) for k in ("claim_id", "source_id", "source_date", "direction", "domain",
                                  "endpoint_domain", "endpoint_measure", "population", "design",
                                  "excerpt") if c.get(k) is not None}


def _rationale(cls, a, b, axes, flags):
    text = {
        "DIRECT_CONTRADICTION": "Opposite findings with no recorded difference in endpoint, population, design, dose or scope.",
        "STATISTICAL_DISAGREEMENT": ("Effect estimates on the same measure point the same way; the sources differ only "
                                     "in statistical significance."),
        "CONTEXT_DIFFERENCE": "The findings differ, but so does the context: " + ", ".join(axes) + ".",
        "CROSS_DOMAIN_TENSION": (f"{a['domain']} evidence and {b['domain']} evidence point in different directions; "
                                 "this is a benefit-risk or mechanism-context tension, not a contradiction."),
        "UNCERTAIN_COMPARABILITY": "Findings differ, but too little context is recorded to judge comparability.",
        "NON_COMPARABLE": "Different outcomes; not a contradiction.",
    }[cls]
    if "non_independent_sources" in flags:
        text += " The two sources share underlying data (not independent)."
    return text


def assess_compound(compound, claims, in_pool, coverage):
    comparisons = []
    for a, b in combinations(sorted(claims, key=lambda c: c["claim_id"]), 2):
        r = compare(a, b)
        if r:
            comparisons.append(r)
    classes = {c["classification"] for c in comparisons}
    directional = [c for c in claims if c["direction"] in DIRECTIONAL]
    sources = {c["source_id"] for c in directional}
    found = next((k for k in CLASS_PRIORITY if k in classes and k != "NON_COMPARABLE"), None)
    if not claims:
        status = "NO_EVIDENCE"
    elif found:
        status = found
    elif len(sources) < 2:
        status = "INSUFFICIENT"        # fewer than two directional sources: nothing to compare
    elif _comparable_agreement(directional):
        status = "NO_DISAGREEMENT_DETECTED"
    else:
        status = "NO_COMPARABLE_PAIR"   # >= 2 directional sources, but on different domains or endpoints
    comparisons.sort(key=lambda r: (CLASS_PRIORITY.index(r["classification"]),
                                    r["side_a"]["claim_id"], r["side_b"]["claim_id"]))
    return {
        "compound": compound, "in_evaluable_pool": in_pool, "status": status,
        "n_claims": len(claims), "n_directional_claims": len(directional),
        "counts": {k: sum(1 for c in comparisons if c["classification"] == k) for k in CLASS_PRIORITY},
        "comparisons": comparisons,
        "insufficient": [_side(c) | {"note": c.get("note")} for c in claims if c["direction"] == "UNCLEAR"],
        "claims": sorted(claims, key=lambda c: c["claim_id"]),
        "coverage": coverage,
    }


# ------------------------------------------------------------------ run ----

def run(root="."):
    j = lambda p: os.path.join(root, p)
    pool = set(pd.read_csv(j(POOL))["compound_name"]) if os.path.exists(j(POOL)) else set()
    by_compound, coverage = {}, {}

    curated, rejected = load_curated(j(CURATED), root)
    for c in curated:
        by_compound.setdefault(c["compound"], []).append(c)

    labels = {}
    for f in sorted(glob.glob(j(os.path.join(LABEL_DIR, "*.json")))):
        with open(f, encoding="utf-8") as fh:
            labels[os.path.basename(f)[:-5]] = (json.load(fh), os.path.relpath(f, root))
    trials = pd.read_csv(j(TRIALS)).to_dict("records") if os.path.exists(j(TRIALS)) else []
    molecular, malformed_molecular = {}, 0
    if os.path.exists(j(MOLECULAR)):
        with open(j(MOLECULAR), encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:       # counted and reported, never silently dropped (E-055 A-3)
                    malformed_molecular += 1
                    continue
                molecular[rec.get("drug")] = rec

    names = sorted(pool | set(by_compound))
    for name in names:
        safe = "".join(ch if ch.isalnum() else "_" for ch in name)
        lab = labels.get(safe)
        if lab:
            by_compound.setdefault(name, []).extend(label_claims(name, lab[0], lab[1]))
        mol = molecular.get(name)
        mc = molecular_claim(mol, MOLECULAR) if mol else None
        if mc:
            by_compound.setdefault(name, []).append(mc)
        trs = [t for t in trials if t["compound_name"] == name]
        by_compound.setdefault(name, []).extend(trial_context(name, trs))
        coverage[name] = {
            "curated_claims": sum(1 for c in curated if c["compound"] == name),
            "openfda_label": "cached" if lab else "no cached label (missing, not evidence of safety)",
            "molecular": ("scored" if mc else ("no ChEMBL mechanism target (missing)" if mol else "no record")),
            "pre_cutoff_trials": len(trs),
            "literature": "not read by this agent (stage-04 PMIDs are not persisted; TD-021)",
        }

    records = [assess_compound(n, by_compound.get(n, []), n in pool, coverage[n]) for n in names]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from agent_contract import diag, envelope, input_hashes, run_status
    label_files = [os.path.relpath(f, root) for f in sorted(glob.glob(j(os.path.join(LABEL_DIR, "*.json"))))]
    diags = [diag("warn", "CURATED_CLAIM_REJECTED", f"{r.get('claim') or r.get('source')}: {r.get('reason', '')}")
             for r in rejected if isinstance(r, dict)]
    for rel in (CURATED, LABEL_DIR, MOLECULAR, TRIALS, POOL):
        if not os.path.exists(j(rel)):
            diags.append(diag("warn", "INPUT_MISSING", f"{rel} absent: its claims are not assessed"))
    if malformed_molecular:
        diags.append(diag("warn", "MALFORMED_LINE", f"{MOLECULAR}: {malformed_molecular} unparseable line(s) skipped; "
                                                    "those compounds' molecular claims are not assessed"))
    n_ev = sum(1 for r in records if r["status"] not in ("INSUFFICIENT", "NO_EVIDENCE"))
    status = run_status(len(records), 0, n_ev)
    if status == "SUCCESS" and diags:
        status = "PARTIAL"
    env = envelope("10d", "Conflict & Context", AGENT_VERSION, "1.0", status,
                   input_hashes(root, [CURATED, MOLECULAR, TRIALS, POOL] + label_files),
                   {"compounds": len(records), "assessed": n_ev, "insufficient": len(records) - n_ev},
                   ["Curated outcome claims exist only for case-study compounds; elsewhere only label, molecular and "
                    "trial-context claims are compared.",
                    "Disagreements are classified, never scored; INSUFFICIENT means < 2 directional sources, not agreement.",
                    "Stage-04 literature is not read (PMIDs not persisted, TD-021)."], diags)
    return {
        **env,
        "agent": "10d Conflict & Context", "cutoff": CUTOFF,
        "integration": "diagnostic only; not read by scripts/06_vps_fusion.py",
        "input_files": [CURATED, LABEL_DIR, MOLECULAR, TRIALS, POOL],
        "rejected_curated_claims": rejected,
        "status_counts": {s: sum(1 for r in records if r["status"] == s) for s in
                          CLASS_PRIORITY + ("NO_DISAGREEMENT_DETECTED", "NO_COMPARABLE_PAIR", "INSUFFICIENT",
                                            "NO_EVIDENCE")},
        "synthesis_inputs": [{"compound": r["compound"], "status": r["status"], "counts": r["counts"],
                              "flags": sorted({f for c in r["comparisons"] for f in c["flags"]})}
                             for r in records],
        "records": records,
    }


def validate_output(out):
    assert out["agent_version"] == AGENT_VERSION
    for r in out["records"]:
        for c in r["comparisons"]:
            if c["classification"] not in CLASS_PRIORITY:
                raise ValueError(f"bad classification {c['classification']}")
            for side in ("side_a", "side_b"):
                if not c[side].get("source_id"):
                    raise ValueError(f"{r['compound']}: comparison side without a source")
        for c in r["claims"]:
            if c["direction"] not in DIRECTIONS or c["domain"] not in DOMAINS:
                raise ValueError(f"{r['compound']}: invalid claim {c['claim_id']}")
            if "score" in c or "penalty" in c:
                raise ValueError("10d never scores")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="Conflict & Context Agent (10d) - diagnostic, offline, not in VPS")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(argv)
    out = run(args.root)
    validate_output(out)
    path = os.path.join(args.root, args.out)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, default=str)
    os.replace(tmp, path)                                    # atomic: no partial output (TD-037 lesson)
    print(f"Saved {args.out}: {len(out['records'])} compounds; status counts {out['status_counts']}")


if __name__ == "__main__":
    main()
