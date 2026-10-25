"""
Clinical trial-role review table (TD-038 / D-020 / TD-043). Read-only and offline.

For every pre-cutoff trial-compound link in data/clinical_maturity_precutoff_clean.csv, lists the
observed intervention and arm text from the cached registry record, the current automated verdict
(scripts/trial_role.py), any human adjudication (data/feature_trial_roles_td038.csv, D-020), and
review flags. A "structural" verdict (the same classifier with the title/outcome keyword rule
disabled) shows where a keyword alone decided the role. Proposed interpretations are suggestions
for human review, never labels: no file used by scoring is changed.

    ./venv/bin/python scripts/clinical_role_review.py [--out data/clinical_role_review.csv]
        [--worklist data/clinical_review_worklist.csv]

ChEMBL preferred names (aliases shared with agent 10c) come from data/molecular_pathway_evidence.jsonl.
The tracked stage 'review' writes both files above; the dashboard's review queue reads the worklist.
"""

import argparse
import json
import os
import re
import sys
from unittest import mock

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trial_role  # noqa: E402
from clinical_evidence_agent import chembl_names, compound_aliases  # noqa: E402  (same aliases as agent 10c)

LINKS = "data/clinical_maturity_precutoff_clean.csv"
CACHE = "data/cache/ctgov_precutoff_trials.json"
ROLES = "data/feature_trial_roles_td038.csv"
NEVER = re.compile(r"(?!x)x")             # matches nothing: disables the keyword rules


def structural_verdict(study, aliases):
    with mock.patch.object(trial_role, "PROCEDURAL_RE", NEVER), mock.patch.object(trial_role, "BLOCK_RE", NEVER):
        return trial_role.classify_trial_role(study, aliases)["verdict"]


def _interventions(study):
    ivs = ((study.get("protocolSection") or {}).get("armsInterventionsModule") or {}).get("interventions") or []
    return "; ".join(f"{iv.get('name')} [{iv.get('type')}]" + (f" (other names: {', '.join(iv['otherNames'])})"
                     if iv.get("otherNames") else "") for iv in ivs)


def _spelling_variant(compound, names):
    c = re.sub(r"[^a-z]", "", compound.lower())
    return [n for n in names if len(c) >= 6 and re.sub(r"[^a-z]", "", n.lower())[:6] == c[:6]]


def review(root="."):
    j = lambda p: os.path.join(root, p)
    links = pd.read_csv(j(LINKS))
    cache = {"studies": [], "batches": []}
    if os.path.exists(j(CACHE)):
        with open(j(CACHE), encoding="utf-8") as fh:
            cache = json.load(fh)
    studies = {s["protocolSection"]["identificationModule"]["nctId"]: s for s in cache.get("studies", [])}
    failed = {i for b in cache.get("batches", []) if not b.get("ok") for i in b["ids"]}
    manual = {}
    if os.path.exists(j(ROLES)):
        for r in pd.read_csv(j(ROLES), keep_default_na=False).itertuples():
            manual[(r.nct_id, r.compound_name)] = r
    rows = []
    chembl = chembl_names(root)
    for r in links.itertuples():
        st = studies.get(r.nct_id)
        aliases = compound_aliases(r.compound_name, r.matched_alias, chembl)
        row = {"nct_id": r.nct_id, "compound": r.compound_name, "phase_in_feature": r.phase,
               "matched_intervention": r.matched_intervention, "matched_alias": r.matched_alias}
        if st is None:
            row.update(retrieval_state="RETRIEVAL_FAILED" if r.nct_id in failed else "NOT_RETRIEVED",
                       auto_verdict="UNDETERMINED", proposed_interpretation="needs registry record",
                       confidence="none", uncertainty="no cached registry record")
            rows.append(row)
            continue
        res = trial_role.classify_trial_role(st, aliases)
        struct = structural_verdict(st, aliases)
        ident = st["protocolSection"].get("identificationModule") or {}
        arms = ((st["protocolSection"].get("armsInterventionsModule") or {}).get("armGroups") or [])
        ivs = ((st["protocolSection"].get("armsInterventionsModule") or {}).get("interventions") or [])
        m = manual.get((r.nct_id, r.compound_name))
        flags = []
        if res["verdict"] in ("PROCEDURAL_CONTEXT", "PROCEDURE_DELIVERED") and struct != res["verdict"]:
            flags.append(f"KEYWORD_DECIDED: {'; '.join(res['procedural_hits'][:3])}; structural reading {struct}")
        other = [iv.get("name") for iv in ivs if any(trial_role._names_compound(o, aliases) for o in iv.get("otherNames") or [])
                 and not trial_role._names_compound(iv.get("name"), aliases)]
        variants = _spelling_variant(r.compound_name, [iv.get("name") or "" for iv in ivs])
        if res["verdict"] in ("BACKGROUND_OTHERNAME", "NOT_NAMED") and (other or variants):
            flags.append(f"ALIAS_GAP: compound appears via {sorted(set(other + variants))}")
        if res["verdict"] == "UNDETERMINED":
            flags.append("STRUCTURE_INSUFFICIENT: " + "; ".join(res["evidence"][-1:]))
        if chembl.get(r.compound_name):
            plain = trial_role.classify_trial_role(st, [a for a in aliases if a != chembl[r.compound_name]])["verdict"]
            if plain != res["verdict"]:
                flags.append(f"CHEMBL_ALIAS: verdict {res['verdict']} with the ChEMBL name {chembl[r.compound_name]!r}, "
                             f"{plain} without it; the identity is source-backed, the trial role is not adjudicated")
        if m is not None and m.annotator_verdict and m.annotator_verdict != res["verdict"]:
            flags.append(f"AUTO_VS_ADJUDICATION: auto {res['verdict']} vs adjudicated category {m.category}")
        # proposal: human adjudication wins; otherwise structure, never a keyword alone
        if m is not None:
            prop, conf, why = (f"{m.category} (p1_qualifies {m.p1_qualifies})", "adjudicated (D-020)",
                               m.rationale)
        elif any(f.startswith("KEYWORD_DECIDED") for f in flags):
            prop, conf, why = (f"human review: keyword verdict {res['verdict']} vs structural {struct}", "low",
                               "a keyword cannot tell a procedure (e.g. anaesthesia for DBS surgery) from a symptom "
                               "or outcome (e.g. daytime sedation); neither reading is preferred")
        elif any(f.startswith("ALIAS_GAP") for f in flags):
            if variants:
                prop, conf, why = ("same agent under a spelling/salt variant - review", "medium",
                                   f"intervention name {variants} matches the compound's stem")
            else:
                prop, conf, why = ("brand name or drug class - review", "low",
                                   f"compound listed only as an other-name of {other}")
        elif any(f.startswith("CHEMBL_ALIAS") for f in flags):
            prop, conf, why = (f"{res['verdict']} (structure, via ChEMBL name) - review intent", "medium",
                               "the compound is recognised under its ChEMBL name; whether the trial tests it for PD "
                               "is a separate question")
        elif res["verdict"] == "UNDETERMINED":
            prop, conf, why = ("needs human review", "none", "arm structure does not name the compound's role")
        else:
            prop, conf, why = (res["verdict"], "heuristic (not adjudicated)", "arm types and interventions")
        row.update(retrieval_state="RETRIEVED", brief_title=ident.get("briefTitle"),
                   primary_purpose=res.get("primary_purpose"), observed_interventions=_interventions(st),
                   arm_types="; ".join(f"{a.get('label')}: {a.get('type')}" for a in arms),
                   auto_verdict=res["verdict"], structural_verdict=struct,
                   auto_evidence=" | ".join(res["evidence"])[:400],
                   adjudicated_category=m.category if m is not None else "",
                   adjudicated_p1=m.p1_qualifies if m is not None else "",
                   review_flags=" || ".join(flags), proposed_interpretation=prop, confidence=conf, uncertainty=why)
        rows.append(row)
    return pd.DataFrame(rows)


PRIORITY = ["KEYWORD_DECIDED", "ALIAS_GAP", "CHEMBL_ALIAS", "STRUCTURE_INSUFFICIENT", "AUTO_VS_ADJUDICATION"]
EVIDENCE_NEEDED = {
    "KEYWORD_DECIDED": "Read the arm descriptions, interventions and primary outcome in the full registry record or "
                       "protocol: is the drug given as procedural anaesthesia/sedation (e.g. during DBS surgery) or "
                       "tested for a PD indication? A title keyword alone does not decide it.",
    "ALIAS_GAP": "Confirm whether the listed intervention name is the same active ingredient (brand, salt or "
                 "spelling variant) or a different agent or drug class; if the same, identify its arm role.",
    "CHEMBL_ALIAS": "The compound is now recognised under its ChEMBL preferred name. Confirm from the protocol "
                    "whether the trial tests it for a PD indication or uses it for another purpose (e.g. a "
                    "drug-interaction study).",
    "STRUCTURE_INSUFFICIENT": "The registry record has no usable arm/intervention structure: consult the protocol, the "
                              "results publication or the registry history. Do not infer arm assignment.",
    "AUTO_VS_ADJUDICATION": "None unless the owner reopens D-020: the human adjudication is retained unchanged.",
}


def worklist(df):
    """Flagged links only, one row per link, ordered by review priority. Nothing is resolved here."""
    rows = []
    for r in df[df["review_flags"].fillna("") != ""].itertuples():
        flags = [f.split(":")[0] for f in r.review_flags.split(" || ")]
        primary = min(flags, key=PRIORITY.index)
        adjudicated = bool(getattr(r, "adjudicated_category", "") or "")
        rows.append({
            "priority": PRIORITY.index(primary) + 1, "flag": primary, "all_flags": "; ".join(flags),
            "nct_id": r.nct_id, "compound": r.compound, "brief_title": r.brief_title,
            "intervention_text": r.observed_interventions, "arm_types": r.arm_types,
            "current_role_automated": r.auto_verdict, "structural_reading": r.structural_verdict,
            "current_role_adjudicated": (f"{r.adjudicated_category} (p1_qualifies {r.adjudicated_p1}; D-020, "
                                         f"data/feature_trial_roles_td038.csv)") if adjudicated else "",
            "reason_for_flag": r.review_flags, "evidence_needed": EVIDENCE_NEEDED[primary],
            "status": ("ADJUDICATED (D-020) - retained, not re-opened" if adjudicated
                       else "UNRESOLVED - awaiting human adjudication"),
            "reviewer": "", "decision": "", "decision_date": "", "decision_source": ""})
    return pd.DataFrame(rows).sort_values(["priority", "nct_id", "compound"])


def _write_csv_atomic(df, path):
    """Write next to the target and rename, so an interrupted run never leaves a half-written worklist (audit 2026-10-21;
    the agents already write this way)."""
    tmp = path + ".tmp"
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="data/clinical_role_review.csv")
    ap.add_argument("--worklist", default=None, help="also write the prioritised review worklist (flagged links) here")
    a = ap.parse_args(argv)
    df = review(a.root)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    _write_csv_atomic(df, a.out)
    if a.worklist:
        os.makedirs(os.path.dirname(a.worklist), exist_ok=True)
        wl = worklist(df)
        _write_csv_atomic(wl, a.worklist)
        print(f"worklist: {len(wl)} links -> {a.worklist}; by flag {wl['flag'].value_counts().to_dict()}; "
              f"status {wl['status'].value_counts().to_dict()}")
    flagged = df["review_flags"].fillna("").str.len() > 0
    print(f"{len(df)} links; retrieval {df['retrieval_state'].value_counts().to_dict()}")
    print("auto verdicts:", df["auto_verdict"].value_counts().to_dict())
    print("adjudicated (D-020):", int((df["adjudicated_category"].fillna("") != "").sum()))
    print("flagged for review:", int(flagged.sum()),
          {k: int(df["review_flags"].fillna("").str.contains(k).sum())
           for k in ("KEYWORD_DECIDED", "ALIAS_GAP", "STRUCTURE_INSUFFICIENT", "AUTO_VS_ADJUDICATION")})
    print("confidence:", df["confidence"].value_counts().to_dict())
    return 0


if __name__ == "__main__":
    sys.exit(main())
