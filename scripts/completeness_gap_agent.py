"""
Completeness & Gap Agent (architecture 10h) — DIAGNOSTIC, not part of VPS.

Question: for each candidate, which evidence exists, which does not, and WHY
not? It keeps four things apart that a single NaN (or a neutral 0.5 rank)
hides:
  * a real measurement of zero / no signal          (MEASURED_ZERO)
  * the source was queried and holds no record      (ABSENT_AT_SOURCE)
  * the evidence was never retrieved for this drug  (NOT_RETRIEVED)
  * a retrieval was attempted and failed            (RETRIEVAL_FAILED)
and adds what would be needed to close each gap and which research questions
remain unanswered. It never fills a gap, never scores evidence quality, and
produces no number that could enter VPS.

How it differs from neighbouring components
  * Stage 06 records dimensions_missing / n_dimensions_measured (D-004) for the
    five VPS dimensions only, and does not say why a value is missing. 10h
    re-derives those states from the stage outputs and asserts agreement.
  * 10a/10d/10e assess evidence that exists; 10h reports where they could not
    run and why.

Inputs (persisted only; no network): stage outputs of 02/03/04/05/08, stage-06
scores, 10a/10d/10e outputs, the TD-038 trial-role adjudication. Output:
data/completeness_gaps.json (schema COMPLETENESS_SCHEMA_VERSION), with a flat
`synthesis_inputs` list for Stage 11 (evidence synthesis).

Every state is derived from what a stage persists. Where a stage does not
persist failures (stage 05 does not checkpoint a failed request; stage 02 does
not record why a compound was skipped), the state says so instead of guessing.
"""

import argparse
import glob
import hashlib
import json
import os
import sys
from collections import Counter

import pandas as pd

AGENT_VERSION = "10h-1.0"
COMPLETENESS_SCHEMA_VERSION = "1.0"
OUT = "data/completeness_gaps.json"
LIT_SAMPLE_CAP = 30            # MAX_PAPERS_PER_COMPOUND in scripts/04_literature_independence.py

F = {"vps": "data/vps_scores_v2.csv", "proximity": "data/network_proximity.csv",
     "clinical": "data/clinical_maturity_precutoff_clean.csv", "literature": "data/literature_independence.csv",
     "safety": "data/safety_signal.csv", "molecular": "data/molecular_pathway.csv",
     "conflict": "data/conflict_context.json", "repro": "data/reproducibility.json",
     "roles": "data/feature_trial_roles_td038.csv", "clinical_evidence": "data/clinical_evidence.json",
     "safety_evidence": "data/safety_evidence.json", "independence": "data/evidence_independence.json",
     "safety_failures": "data/_safety_failures.jsonl", "literature_failures": "data/_literature_failures.jsonl",
     "credibility_all": "data/literature_credibility_all.json"}
#: Agent outputs whose own recorded inputs are checked for staleness (shared envelope, agent_contract.py).
AGENT_OUTPUTS = {"10a": "data/literature_credibility_all.json", "10c": "data/clinical_evidence.json", "10d": "data/conflict_context.json",
                 "10e": "data/reproducibility.json", "10f": "data/safety_evidence.json",
                 "10g": "data/evidence_independence.json",
                 # 10b re-validates stage 08's records; listed for staleness/failure reporting only (E-055 A-4) - the
                 # molecular domain itself is read from data/molecular_pathway.csv
                 "10b": "data/molecular_agent_run.json"}
CRED_GLOB = "data/literature_credibility_*.json"

STATES = {
    "MEASURED": "a value was computed from retrieved evidence",
    "MEASURED_ZERO": "a value was computed and is zero / no signal — a measurement, not missing evidence",
    "PARTIAL": "measured, but from incomplete or truncated input (see detail)",
    "ABSENT_AT_SOURCE": "the source was queried successfully and holds no record for this compound",
    "NOT_COMPUTED": "a local stage produced no value for this compound (reason in detail)",
    "NOT_RETRIEVED": "this evidence type was never retrieved for this compound (out of scope or not persisted)",
    "RETRIEVAL_FAILED": "a retrieval for this compound was attempted and a failure was recorded",
    "INSUFFICIENT": "assessed, but too little evidence for any conclusion (not agreement, not absence)",
    "ASSESSED": "a diagnostic agent produced a finding for this compound",
}
MISSING = {"ABSENT_AT_SOURCE", "NOT_COMPUTED", "NOT_RETRIEVED", "RETRIEVAL_FAILED"}
VPS_DIMS = ("proximity", "clinical", "literature", "safety", "molecular")

DOMAINS = {
    "proximity": {"label": "Network proximity", "kind": "VPS dimension", "source": F["proximity"], "stage": "02",
                  "temporal": "Hetionet 2017 snapshot (pre-cutoff)"},
    "clinical": {"label": "Clinical maturity (pre-cutoff trials)", "kind": "VPS dimension", "source": F["clinical"],
                 "stage": "03", "temporal": "cutoff-bounded (first posted < 2021-01-01)"},
    "literature": {"label": "Literature independence", "kind": "VPS dimension", "source": F["literature"],
                   "stage": "04 (10g)", "temporal": "NOT cutoff-bounded (TD-021/TD-033)"},
    "safety": {"label": "Safety (FDA label)", "kind": "VPS dimension", "source": F["safety"], "stage": "05 (10f)",
               "temporal": "current label, NOT cutoff-bounded"},
    "molecular": {"label": "Molecular plausibility", "kind": "VPS dimension", "source": F["molecular"],
                  "stage": "08 (10b)", "temporal": "current Open Targets snapshot, NOT cutoff-bounded"},
    "trial_outcomes": {"label": "Trial results / outcome evidence", "kind": "evidence type",
                       "source": F["clinical_evidence"], "stage": "10c registry results / curated case studies",
                       "temporal": "mixed (results posted after 2021 are flagged by 10c)"},
    "trial_roles": {"label": "Role of the drug in its pre-cutoff trials", "kind": "evidence type",
                    "source": F["roles"], "stage": "TD-038 / D-020", "temporal": "pre-cutoff"},
    "adverse_events": {"label": "Post-marketing adverse events (FAERS)", "kind": "evidence type",
                       "source": F["safety_evidence"], "stage": "10f", "temporal": "all-time counts + count received by 2020"},
    "literature_credibility": {"label": "Study-design credibility (10a)", "kind": "diagnostic agent",
                               "source": CRED_GLOB, "stage": "10a", "temporal": "per paper"},
    "conflict_context": {"label": "Conflicting evidence (10d)", "kind": "diagnostic agent", "source": F["conflict"],
                         "stage": "10d", "temporal": "per claim"},
    "reproducibility": {"label": "Replication by independent studies (10e)", "kind": "diagnostic agent",
                        "source": F["repro"], "stage": "10e", "temporal": "per finding"},
    "evidence_independence": {"label": "Cross-source independence (10g)", "kind": "diagnostic agent",
                              "source": F["independence"], "stage": "10g", "temporal": "—"},
}


def _read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)

def credibility_state(c):
    """10a --all record -> domain state. NO_RESULTS is a successful empty query, never a failure or a zero."""
    if c.get("status") == "RETRIEVAL_FAILED":
        return _st("RETRIEVAL_FAILED", "stage 04p could not retrieve this compound's literature")
    if c.get("status") == "NO_RESULTS":
        return _st("ABSENT_AT_SOURCE", "PubMed returned no record for the stage-04 query")
    s, b = c["summary_stage04_sample"], c["summary_cutoff_bounded"]
    return _st("ASSESSED", f"10a --all: stage-04 sample {s['n_papers']} paper(s), {c['n_sample_post_cutoff']} after the "
               f"cutoff, human tier A/B {s['n_human_tier_A_or_B']}; cutoff-bounded {b['n_papers']} paper(s), "
               f"human tier A/B {b['n_human_tier_A_or_B']}",
               sample_papers=s["n_papers"], sample_post_cutoff=c["n_sample_post_cutoff"],
               cutoff_bounded_papers=b["n_papers"], cutoff_bounded_human_A_B=b["n_human_tier_A_or_B"])


def _md5(path):
    with open(path, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def _rows(df, name):
    return df[df["compound_name"] == name] if df is not None else None


def _st(state, detail, vps_treatment=None, value=None, **extra):
    out = {"state": state, "detail": detail}
    if vps_treatment:
        out["vps_treatment"] = vps_treatment
    if value is not None:
        out["value"] = value
    out.update(extra)
    return out


def assess_proximity(row):
    if row is None or row.empty:
        return _st("NOT_COMPUTED", "no row in network_proximity.csv: stage 02 skips a compound with no Hetionet "
                   "binding target, no target in the PPI network, or no finite distance; the skip reason is not "
                   "persisted", "median-imputed proximity_z (not flagged in dimensions_missing)")
    z = row.iloc[0]["proximity_z"]
    if pd.isna(z):
        return _st("NOT_COMPUTED", "proximity_z is empty", "median-imputed")
    return _st("MEASURED", f"z = {z:.3f} from {int(row.iloc[0]['n_targets_in_network'])} target(s) in network",
               "ranked", round(float(z), 4))


def assess_clinical(rows):
    if rows is None or rows.empty:
        # Every scored compound entered the pool through an accepted trial, so no row here means the
        # stage-03c output changed or is missing since stage 06 ran, not that the compound left the pool.
        return _st("NOT_COMPUTED", "no accepted pre-cutoff trial row for a compound in the VPS pool: "
                   "stage-03c output missing or changed since stage 06", "ranked by stage 06 from the earlier file")
    phases = rows["phase"].fillna("NA")
    if set(phases) == {"NA"}:
        return _st("MEASURED_ZERO", f"{len(rows)} accepted trial(s), none with a phase (max phase rank 0)",
                   "ranked (lowest)", 0, trials=sorted(rows["nct_id"]))
    return _st("MEASURED", f"{len(rows)} accepted pre-cutoff trial(s); highest phase {sorted(phases)[-1]}",
               "ranked by maximum phase", None, trials=sorted(rows["nct_id"]))


def assess_literature(row, failure=None):
    if (row is None or row.empty) and failure:
        return _st("RETRIEVAL_FAILED", f"stage 04 recorded a failure ({failure.get('error_class')}); re-run stage 04",
                   "median-imputed")
    if row is None or row.empty:
        return _st("NOT_COMPUTED", "no row in literature_independence.csv: stage 04 logs a failed compound but "
                   "does not persist the failure, so 'never queried' and 'failed' cannot be told apart",
                   "median-imputed")
    r = row.iloc[0]
    n, fails = int(r["raw_paper_count"]), int(r["citation_lookup_failures"])
    if fails > 0:
        return _st("PARTIAL", f"{fails} citation lookup(s) failed: the independence count is an upper bound",
                   "ranked", int(r["effective_independent_count"]), retrieval_failures=fails)
    if n == 0:
        return _st("MEASURED_ZERO", "PubMed search returned no PD paper for this compound", "ranked (lowest)", 0)
    if n >= LIT_SAMPLE_CAP:
        return _st("PARTIAL", f"sample capped at the first {LIT_SAMPLE_CAP} PubMed records returned (TD-021); "
                   "not representative of all literature", "ranked", int(r["effective_independent_count"]))
    return _st("MEASURED", f"{n} papers, {int(r['effective_independent_count'])} independent components",
               "ranked", int(r["effective_independent_count"]))


def assess_safety(row, failure=None):
    if (row is None or row.empty) and failure:
        return _st("RETRIEVAL_FAILED", f"stage 05 recorded a failure ({failure.get('error_class')}); re-run stage 05",
                   "neutral rank 0.5 (D-004)")
    if row is None or row.empty:
        return _st("NOT_COMPUTED", "no row in safety_signal.csv: stage 05 does not checkpoint a failed request, "
                   "so 'never queried' and 'failed' cannot be told apart", "neutral rank 0.5 (D-004)")
    r = row.iloc[0]
    if not bool(r["has_label"]):
        return _st("ABSENT_AT_SOURCE", "openFDA returned no US label (HTTP 404 or empty result); the drug may be "
                   "unapproved in the US or labelled under another name", "neutral rank 0.5 (D-004)")
    n = int(r["serious_term_count"])
    boxed = bool(r["boxed_warning"]) if not pd.isna(r["boxed_warning"]) else False
    if n == 0 and not boxed:
        return _st("MEASURED_ZERO", "label found; no boxed warning and no listed serious term in its warnings — "
                   "not evidence of safety in PD", "ranked (lowest risk)", 0, label_set_id=r.get("label_set_id"))
    return _st("MEASURED", f"label found; boxed warning: {'yes' if boxed else 'no'}; serious terms: {n}",
               "ranked", n, boxed_warning=boxed, label_set_id=r.get("label_set_id"))


def with_label_at_cutoff(state, se_rec):
    """Attach 10f's label-at-cutoff view (stage 05h) to the safety domain without changing its state: the VPS uses
    the current label; this says whether that label existed in this form at the cutoff."""
    a = ((se_rec or {}).get("label") or {}).get("at_cutoff")
    if a:
        state["label_at_cutoff"] = a.get("state")
        if a.get("state") == "SCORED":
            state["label_changed_since_cutoff"] = a.get("changed_since_cutoff")
    return state


def assess_molecular(row):
    if row is None or row.empty:
        return _st("NOT_COMPUTED", "no row in molecular_pathway.csv", "median-imputed")
    r = row.iloc[0]
    if not bool(r["resolved"]):
        return _st("ABSENT_AT_SOURCE", "drug name not resolved to a ChEMBL record", "neutral rank 0.5 (D-004)")
    if int(r["n_targets"]) == 0:
        return _st("ABSENT_AT_SOURCE", "resolved, but ChEMBL lists no mechanism-of-action target",
                   "neutral rank 0.5 (D-004)", chembl_id=r["chembl_id"])
    s = float(r["molecular_plausibility_score"])
    missing = int(r["n_evidence_missing"])
    if s == 0:
        return _st("MEASURED_ZERO", f"{int(r['n_targets'])} target(s), none with a permitted PD association or "
                   "disease-module pathway — a measured absence of mechanistic support", "ranked (lowest)", 0.0,
                   chembl_id=r["chembl_id"])
    if missing > 0:
        return _st("PARTIAL", f"score {s:.3f}; {missing} evidence item(s) could not be looked up", "ranked",
                   round(s, 4), chembl_id=r["chembl_id"])
    return _st("MEASURED", f"score {s:.3f} from {int(r['n_targets'])} target(s)", "ranked", round(s, 4),
               chembl_id=r["chembl_id"])


def assess_outcomes(claims, clinical=None, clinical_status=None):
    cur = [c for c in claims if c.get("source_type") == "curated_doc"]
    if not cur and clinical is not None:
        n, k = clinical["n_trials"], clinical["n_results_posted"]
        failed = sum(l["results_state"] in ("RETRIEVAL_FAILED", "NOT_RETRIEVED") for l in clinical["links"])
        if k:
            return _st("MEASURED", f"registry results posted for {k} of {n} pre-cutoff trial(s) "
                       f"({clinical['n_results_posted_pre_cutoff']} before 2021; {clinical['n_primary_analyses_posted']} "
                       "primary analyses copied verbatim by 10c, not interpreted as benefit)", results_posted=k, trials=n)
        if failed:
            return _st("RETRIEVAL_FAILED", f"registry retrieval failed for {failed} of {n} trial(s) (10c)")
        return _st("ABSENT_AT_SOURCE", f"none of {n} pre-cutoff trial(s) has results posted on ClinicalTrials.gov; "
                   "outcome publications are not retrieved (10c)", results_posted=0, trials=n)
    if not cur:
        return _st("NOT_RETRIEVED", "no trial results or outcome literature retrieved: stage 03 records trial "
                   "existence and phase only (10c partial); outcome claims exist only for curated case studies")
    dirs = Counter(c.get("direction") for c in cur)
    return _st("ASSESSED", f"{len(cur)} curated outcome claim(s) with PMIDs: "
               + ", ".join(f"{k} {v}" for k, v in sorted(dirs.items())), directions=dict(dirs))


def assess_roles_10c(clinical):
    links = clinical["links"]
    manual = sum(1 for l in links if l.get("role_manual"))
    roles = Counter(((l.get("role_manual") or {}).get("category") or l["role_auto"]) for l in links)
    not_test = {k: v for k, v in roles.items() if k not in ("THERAPEUTIC_TEST", "DRUG_SPECIFIC_ARM", "ALTERNATIVES_IN_ONE_ARM")}
    detail = (f"{len(links)} link(s): {manual} hand-adjudicated (D-020), {len(links) - manual} automated (10c); "
              + ", ".join(f"{k} {v}" for k, v in sorted(roles.items())))
    state = "PARTIAL" if roles.get("UNDETERMINED") else "ASSESSED"
    return _st(state, detail + ". Not applied to scoring (D-020 pending).", roles=dict(roles), not_tested_links=not_test)


def assess_roles(trials, roles):
    if not trials:
        return _st("NOT_RETRIEVED", "no pre-cutoff trials")
    audited = roles[roles["compound_name"].isin([trials["compound"]]) & roles["nct_id"].isin(trials["ids"])] \
        if roles is not None else pd.DataFrame()
    n, k = len(trials["ids"]), len(audited)
    if k == 0:
        return _st("NOT_RETRIEVED", f"none of {n} trial link(s) role-audited (only trials shared by several "
                   "compounds were audited, D-020; TD-023)")
    fail = audited[audited["p1_qualifies"] == "NO"]
    detail = f"{k}/{n} link(s) audited (D-020); {len(fail)} fail the P1 role criterion"
    if len(fail):
        detail += " (" + ", ".join(f"{a.nct_id}: {a.category}" for a in fail.itertuples()) + ")"
    return _st("PARTIAL" if k < n else "ASSESSED", detail, audited=k, links=n,
               failing_links=[a.nct_id for a in fail.itertuples()])


def faers_state(rec):
    """10f FAERS state -> 10h state. A zero-report answer is a source with no record, not 'safe'."""
    if rec is None:
        return _st("NOT_RETRIEVED", "no 10f output for this compound")
    f = rec["faers"]
    m = {"RETRIEVED": "MEASURED", "NO_RECORD": "ABSENT_AT_SOURCE", "FAILED": "RETRIEVAL_FAILED",
         "NOT_RETRIEVED": "NOT_RETRIEVED"}[f["state"]]
    return _st(m, "FAERS (10f): " + f.get("detail", ""), total_reports=f.get("total_reports"))


def independence_state(rec):
    if rec is None:
        return _st("NOT_RETRIEVED", "no 10g output for this compound")
    found = [k.split("_", 1)[1].replace("_", " ") for k, c in rec["checks"].items() if c["state"] == "DEPENDENCE_FOUND"]
    na = sum(c["state"] == "NOT_ASSESSABLE" for c in rec["checks"].values())
    detail = ("dependence found: " + "; ".join(found) if found else "no cross-source dependence found in the checks run")
    n = len(rec["checks"])                                 # 10g runs D1-D5 (was hard-coded 4; audit 2026-10-21)
    detail += f" ({n - na}/{n} checks assessable)"
    return _st("PARTIAL" if na else "ASSESSED", detail, dependence=found)


def gaps_for(rec):
    """Turn states into actionable gaps: consequence + what would close them."""
    d, out = rec["domains"], []
    need = {
        ("proximity", "NOT_COMPUTED"): "map the drug's targets to the interactome (no binding target in Hetionet)",
        ("literature", "PARTIAL"): "cutoff-bounded, complete PubMed retrieval with persisted PMIDs (D-006/TD-021)",
        ("safety", "ABSENT_AT_SOURCE"): "a non-US label (EMA SmPC) or FAERS reports",
        ("molecular", "ABSENT_AT_SOURCE"): "curated mechanism/target annotation outside ChEMBL",
        ("trial_outcomes", "NOT_RETRIEVED"): "posted trial results or outcome publications for the pre-cutoff trials",
        ("trial_roles", "NOT_RETRIEVED"): "role audit of the drug's pre-cutoff trial links (D-020 recommendation)",
        ("trial_roles", "PARTIAL"): "manual reading of the trial records whose role the annotator could not determine",
        ("trial_outcomes", "ABSENT_AT_SOURCE"): "outcome publications of the trials (PubMed) — registry has no results",
        ("trial_outcomes", "RETRIEVAL_FAILED"): "re-run scripts/clinical_evidence_agent.py --fetch",
        ("adverse_events", "ABSENT_AT_SOURCE"): "FAERS search under brand or alternative names",
        ("adverse_events", "RETRIEVAL_FAILED"): "re-run scripts/safety_evidence_agent.py --fetch",
        ("safety", "RETRIEVAL_FAILED"): "re-run stage 05 (scripts/05_safety_signal.py)",
        ("literature", "RETRIEVAL_FAILED"): "re-run stage 04 (scripts/04_literature_independence.py)",
        ("evidence_independence", "PARTIAL"): "persisted PMIDs for the literature sample (TD-021)",
        ("adverse_events", "NOT_RETRIEVED"): "re-run scripts/safety_evidence_agent.py (--fetch for uncached FAERS)",
        ("literature_credibility", "NOT_RETRIEVED"): "run stage 04p then 10a-all (literature provenance + design tiers)",
        ("literature_credibility", "RETRIEVAL_FAILED"): "re-run stage 04p (PubMed retrieval failed), then 10a-all",
        ("conflict_context", "INSUFFICIENT"): "at least two directional sources (outcome claims) for this drug",
        ("reproducibility", "NOT_RETRIEVED"): "outcome-level claims with PMIDs (curated or retrieved)",
    }
    for dom, s in d.items():
        state = s["state"]
        if state in ("MEASURED", "ASSESSED", "MEASURED_ZERO"):     # a measured zero is a finding, not a gap
            continue
        severity = "affects VPS" if dom in VPS_DIMS and state in MISSING else \
                   "limits VPS input" if dom in VPS_DIMS else "limits interpretation"
        out.append({"domain": dom, "state": state, "severity": severity, "detail": s["detail"],
                    "vps_treatment": s.get("vps_treatment"),
                    "needed_to_close": need.get((dom, state)) or "see detail"})
    return out


def open_questions(rec):
    d, q = rec["domains"], []
    if d["trial_outcomes"]["state"] == "MEASURED":
        q.append("Do the posted trial results show benefit? 10c lists them verbatim; they have not been appraised "
                 "(no curated outcome claims).")
    elif d["trial_outcomes"]["state"] != "ASSESSED":
        q.append("Does the drug improve any PD outcome? Not assessed: trial existence is not trial benefit.")
    else:
        q.append("Is the PD outcome evidence replicated? See reproducibility: "
                 + d["reproducibility"]["detail"])
    if d["safety"]["state"] == "ABSENT_AT_SOURCE":
        q.append("What is the drug's safety profile? No US label was found, so the safety dimension is unmeasured.")
    else:
        q.append("Is the drug safe in a PD population? Only general label warnings are measured, not PD-specific harms.")
    if d["molecular"]["state"] in MISSING:
        q.append("Is there a mechanistic rationale? No molecular target is recorded.")
    q.append("Would the evidence have been visible before 2021? Literature, safety and molecular inputs are "
             "current snapshots (TD-033).")
    return q


def run(root="."):
    j = lambda p: os.path.join(root, p)

    def csv(key):
        return pd.read_csv(j(F[key])) if os.path.exists(j(F[key])) else None

    vps = csv("vps")
    if vps is None:
        raise FileNotFoundError(F["vps"])
    prox, clin, lit, saf, mol = csv("proximity"), csv("clinical"), csv("literature"), csv("safety"), csv("molecular")
    roles = pd.read_csv(j(F["roles"]), keep_default_na=False) if os.path.exists(j(F["roles"])) else None
    conflict = _read_json(j(F["conflict"])) if os.path.exists(j(F["conflict"])) else {}
    repro = _read_json(j(F["repro"])) if os.path.exists(j(F["repro"])) else {}
    cred = {os.path.basename(p)[len("literature_credibility_"):-5] for p in glob.glob(j(CRED_GLOB))}
    c_by = {r["compound"]: r for r in conflict.get("records", [])}

    def jload(key):
        return _read_json(j(F[key])) if os.path.exists(j(F[key])) else None

    def failures(key):
        out = {}
        if os.path.exists(j(F[key])):
            with open(j(F[key])) as fh:
                for line in fh:
                    rec = json.loads(line)
                    out[rec["compound_name"]] = rec
        return out
    ce, se, ei = jload("clinical_evidence"), jload("safety_evidence"), jload("independence")
    cred_all = (jload("credibility_all") or {}).get("compounds", {})
    ce_by = {c["compound"]: c for c in (ce or {}).get("compounds", [])}
    se_by = {r["compound"]: r for r in (se or {}).get("records", [])}
    ei_by = {r["compound"]: r for r in (ei or {}).get("records", [])}
    saf_fail, lit_fail = failures("safety_failures"), failures("literature_failures")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from agent_contract import diag, envelope, input_hashes, run_status, stale_inputs
    agent_outputs = {}
    for aid, rel in AGENT_OUTPUTS.items():
        if not os.path.exists(j(rel)):
            agent_outputs[aid] = {"output": rel, "present": False}
            continue
        with open(j(rel), encoding="utf-8") as fh:
            meta = json.load(fh)
        st = stale_inputs(root, meta.get("inputs")) if isinstance(meta.get("inputs"), dict) else None
        agent_outputs[aid] = {"output": rel, "present": True, "run_status": meta.get("run_status"),
                              "generated_utc": meta.get("generated_utc"), "stale_inputs": st}
    stale_agents = {a for a, m in agent_outputs.items() if m.get("stale_inputs")}
    # An upstream agent whose own envelope says FAILED holds no valid result: its domains are NOT_COMPUTED here,
    # never read as data (E-055 A-4). PARTIAL outputs stay usable; their own diagnostics explain the gaps.
    failed_agents = {a for a, m in agent_outputs.items() if m.get("present") and m.get("run_status") == "FAILED"}
    domain_agent = {"trial_outcomes": "10c", "trial_roles": "10c", "adverse_events": "10f",
                    "conflict_context": "10d", "reproducibility": "10e", "evidence_independence": "10g",
                    "literature_credibility": "10a"}

    vps = vps.assign(rank_5d=vps["VPS_equal_5d"].rank(ascending=False, method="min").astype(int))
    records = []
    for v in vps.sort_values("rank_5d").itertuples():
        name = v.compound_name
        crow = _rows(clin, name)
        trials = {"compound": name, "ids": sorted(crow["nct_id"])} if crow is not None and len(crow) else None
        cc = c_by.get(name, {})
        finds = [f for f in repro.get("findings", []) if f["compound"] == name]
        slug = name.lower().replace(" ", "_")
        d = {
            "proximity": assess_proximity(_rows(prox, name)),
            "clinical": assess_clinical(crow),
            "literature": assess_literature(_rows(lit, name), lit_fail.get(name)),
            "safety": with_label_at_cutoff(assess_safety(_rows(saf, name), saf_fail.get(name)),
                                           se_by.get(name)),
            "molecular": assess_molecular(_rows(mol, name)),
            "trial_outcomes": assess_outcomes(cc.get("claims", []), ce_by.get(name)),
            "trial_roles": assess_roles_10c(ce_by[name]) if name in ce_by else assess_roles(trials, roles),
            "adverse_events": faers_state(se_by.get(name)),
            "evidence_independence": independence_state(ei_by.get(name)),
            "literature_credibility": (credibility_state(cred_all[name]) if name in cred_all else
                                       _st("ASSESSED", f"10a output data/literature_credibility_{slug}.json")
                                       if slug in cred else
                                       _st("NOT_RETRIEVED", "10a needs persisted PMIDs; stage 04 does not persist "
                                           "them (TD-021)")),
            "conflict_context": (_st("NOT_RETRIEVED", "compound not in the 10d output") if not cc else
                                 _st("INSUFFICIENT", "fewer than two directional sources") if cc["status"] == "INSUFFICIENT"
                                 else _st("ASSESSED", f"10d status {cc['status']}", status=cc["status"])),
            "reproducibility": (_st("ASSESSED", "; ".join(f"{f['finding'].split(':', 1)[-1]} {f['status']}"
                                                          for f in finds), statuses=[f["status"] for f in finds])
                                if finds else _st("NOT_RETRIEVED", "no outcome-level claims with PMIDs for 10e")),
        }
        for dom, aid in domain_agent.items():
            if aid in failed_agents and dom in d:
                d[dom] = _st("NOT_COMPUTED", f"agent {aid} output has run_status FAILED: not used")
            elif aid in stale_agents and dom in d:
                d[dom]["stale"] = f"agent {aid} output is stale: its inputs changed since it ran"
        missing_vps = sorted(k for k in VPS_DIMS if d[k]["state"] in MISSING)
        rec = {"compound": name, "in_evaluable_pool": True, "label": int(v.label), "rank_vps_equal_5d": int(v.rank_5d),
               "domains": d,
               "vps_dimensions_missing": missing_vps,
               "vps_dimensions_imputed_not_flagged": sorted(k for k in VPS_DIMS
                                                            if "median-imputed" in (d[k].get("vps_treatment") or "")),
               "n_vps_dimensions_with_value": 5 - len(missing_vps),
               "n_domains_assessed_or_measured": sum(s["state"] not in MISSING and s["state"] != "INSUFFICIENT"
                                                     for s in d.values())}
        rec["gaps"] = gaps_for(rec)
        rec["open_questions"] = open_questions(rec)
        # Self-check against stage 06 (D-004): neutral-rank dimensions must coincide.
        neutral = sorted(k for k in VPS_DIMS if "neutral rank" in (d[k].get("vps_treatment") or ""))
        flagged = sorted(x for x in str(v.dimensions_missing if not pd.isna(v.dimensions_missing) else "").split("|") if x)
        rec["agrees_with_stage06_dimensions_missing"] = neutral == flagged
        records.append(rec)

    summary = {dom: dict(Counter(r["domains"][dom]["state"] for r in records)) for dom in DOMAINS}
    by_label = {dom: {str(lab): dict(Counter(r["domains"][dom]["state"] for r in records if r["label"] == lab))
                      for lab in (0, 1)} for dom in VPS_DIMS}
    informative = []
    for dom in VPS_DIMS:
        miss = [r for r in records if r["domains"][dom]["state"] in MISSING]
        if miss:
            pos = sum(r["label"] for r in miss)
            informative.append({"dimension": dom, "missing": len(miss), "positives_among_missing": pos,
                                "note": ("too few missing compounds to judge" if len(miss) < 3 else
                                         "all missing compounds are negatives: missingness is associated with the "
                                         "label, so the neutral rank is not label-free in effect" if pos == 0 else
                                         "positives and negatives both among missing compounds")})
    inputs = {rel: _md5(j(rel)) for rel in F.values() if os.path.exists(j(rel))}
    for p in sorted(glob.glob(j(CRED_GLOB))):
        inputs[os.path.relpath(p, root)] = _md5(p)
    diags = [diag("warn", "STALE_AGENT_OUTPUT", f"{a}: {agent_outputs[a]['output']} inputs changed "
                  f"({', '.join(agent_outputs[a]['stale_inputs'][:5])}); re-run that agent") for a in sorted(stale_agents)]
    diags += [diag("warn", "UPSTREAM_FAILED", f"{a}: {agent_outputs[a]['output']} has run_status FAILED; its domains "
                   "are NOT_COMPUTED") for a in sorted(failed_agents)]
    diags += [diag("warn", "AGENT_OUTPUT_ABSENT", f"{a}: {m['output']} not present; its domains read as not retrieved")
              for a, m in sorted(agent_outputs.items()) if not m["present"]]
    for key in ("proximity", "clinical", "literature", "safety", "molecular"):
        df = {"proximity": prox, "clinical": clin, "literature": lit, "safety": saf, "molecular": mol}[key]
        if df is None:
            diags.append(diag("warn", "INPUT_MISSING", f"{F[key]} absent: the {key} domain cannot be assessed"))
        elif df.empty:
            diags.append(diag("warn", "INPUT_EMPTY", f"{F[key]} has no rows: the {key} domain cannot be assessed"))
    status = run_status(len(records), 0, len(records))
    if status == "SUCCESS" and any(x["level"] == "warn" for x in diags):
        status = "PARTIAL"
    env = envelope("10h", "Completeness & Gap", AGENT_VERSION, COMPLETENESS_SCHEMA_VERSION, status, inputs,
                   {"compounds": len(records), "domains": len(DOMAINS), "gaps": sum(len(r["gaps"]) for r in records)},
                   [], diags)
    return {
        **env,
        "agent_outputs": agent_outputs,
        "agent": "10h Completeness & Gap", "agent_version": AGENT_VERSION,
        "schema_version": COMPLETENESS_SCHEMA_VERSION, "disease": {"name": "Parkinson's disease", "id": "MONDO_0005180"},
        "integration": "diagnostic only; not read by scripts/06_vps_fusion.py",
        "inputs": inputs, "state_meaning": STATES, "domains": DOMAINS,
        "cohort": {"n": len(records), "positives": sum(r["label"] for r in records)},
        "state_counts_by_domain": summary, "state_counts_by_label": by_label,
        "missingness_vs_label": informative,
        "stage06_agreement": all(r["agrees_with_stage06_dimensions_missing"] for r in records),
        "records": records,
        "synthesis_inputs": [{"compound": r["compound"], "domain": g["domain"], "state": g["state"],
                              "severity": g["severity"], "needed_to_close": g["needed_to_close"]}
                             for r in records for g in r["gaps"]],
        "limitations": [
            "Covers the 90-compound evaluable pool only (compounds outside it have no stage-06 row).",
            "Stage 02 does not persist why a compound was skipped; stages 04 and 05 persist per-compound failures "
            "since 2026-10-15 (E-021). A missing row without a recorded failure is NOT_COMPUTED, never a negative.",
            "Staleness is checked for agent outputs that record input hashes (10a, 10c-10g; shared envelope).",
            "States describe availability, not quality or truth; 10h produces no score.",
            "Gap remedies are suggestions for retrieval; none has been run.",
        ],
    }


def validate_output(out):
    from agent_contract import validate_envelope
    validate_envelope(out)
    if out.get("schema_version") != COMPLETENESS_SCHEMA_VERSION:
        raise ValueError("schema version mismatch")
    for r in out["records"]:
        for dom, s in r["domains"].items():
            if dom not in out["domains"] or s["state"] not in out["state_meaning"]:
                raise ValueError(f"{r['compound']}/{dom}: bad domain or state")
        if any(k in r for k in ("score", "completeness_score", "penalty")):
            raise ValueError("10h produces no score")
    if not out["stage06_agreement"]:
        bad = [r["compound"] for r in out["records"] if not r["agrees_with_stage06_dimensions_missing"]]
        raise ValueError(f"10h disagrees with stage 06 dimensions_missing for {bad}")
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="Completeness & Gap Agent (10h) - diagnostic, offline, not in VPS")
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(argv)
    out = run(args.root)
    validate_output(out)
    path = os.path.join(args.root, args.out)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, default=str)
    os.replace(path + ".tmp", path)
    print(f"Saved {args.out}: {len(out['records'])} compounds, {len(out['synthesis_inputs'])} gaps; "
          f"stage-06 agreement {out['stage06_agreement']}")
    for dom in VPS_DIMS:
        print(f"  {dom}: {out['state_counts_by_domain'][dom]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
