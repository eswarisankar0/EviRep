"""
Trial-role annotator (TD-023 / TD-032) — DIAGNOSTIC ONLY.

Gate 2 (intervention_matcher) answers "does this trial name the compound?".
It does not answer "is the compound the thing being tested, for Parkinson's?".
This module answers the second question from a ClinicalTrials.gov v2 study
record, deterministically, with the evidence for every verdict.

It is NOT wired into stage 03 and changes no label or feature. Using it to
filter trials would redefine the ground truth -> owner decision (TD-032).

Verdicts (first matching rule wins, evaluated in this order):
  UNDETERMINED          arm groups or interventions absent -> cannot judge
  NOT_NAMED             compound not found in any intervention name/otherName
  BACKGROUND_OTHERNAME  compound appears only in otherNames of an intervention
                        whose own name is a different agent (E-014 pattern)
  PROCEDURAL_CONTEXT    anaesthesia/sedation/surgical wording in the titles,
                        primary outcomes or arm descriptions (e.g. DBS
                        implantation, sedation, EC50, microelectrode recording)
  PROCEDURE_DELIVERED   the compound is the agent of a therapeutic procedure
                        (nerve/ganglion block): the procedure, not the drug's
                        systemic pharmacology, carries the therapeutic intent
  COMPARATOR_ONLY       every arm with the compound is comparator-typed AND a
                        different non-control agent sits in an EXPERIMENTAL arm
                        (registrants often type the only active arm
                        ACTIVE_COMPARATOR against placebo; that is not this)
  CO_ADMINISTERED       compound only ever appears together with another active
                        agent (drug, biological or GENETIC, e.g. a chemogenetic
                        actuator), never as the sole active agent of an arm
  THERAPEUTIC_TEST      compound is the sole active agent of an EXPERIMENTAL or
                        comparator-typed arm and no rule above fired

primary_purpose is reported alongside (BASIC_SCIENCE studies are mechanistic,
not efficacy trials) but does not change the verdict.

A THERAPEUTIC_TEST verdict is about trial DESIGN, never about efficacy.
"""

import re
from typing import Dict, Iterable, List, Optional

try:
    from intervention_matcher import normalise, tokens, is_control_intervention
except ImportError:  # imported as scripts.trial_role
    from scripts.intervention_matcher import normalise, tokens, is_control_intervention

PROCEDURAL_RE = re.compile(
    r"\b(an(a)?esthe\w*|sedat\w*|intubat\w*|ec50|ed50|microelectrode|\bmer\b|"
    r"(deep brain stimulation|dbs)\s+(surgery|implant\w*|procedure|operation)|"
    r"(surgery|implant\w*|operation)\s+(of|for)\s+(deep brain stimulation|dbs)|"
    r"perioperative|postoperative|intraoperative)\b", re.I)
BLOCK_RE = re.compile(r"\b(nerve|ganglion|plexus|epidural|spinal)\s+block\w*\b", re.I)
ACTIVE_TYPES = ("DRUG", "BIOLOGICAL", "COMBINATION_PRODUCT", "GENETIC")

COMPARATOR_ARMS = {"ACTIVE_COMPARATOR", "PLACEBO_COMPARATOR", "SHAM_COMPARATOR"}
VERDICTS = ("UNDETERMINED", "NOT_NAMED", "BACKGROUND_OTHERNAME", "PROCEDURAL_CONTEXT",
            "PROCEDURE_DELIVERED", "COMPARATOR_ONLY", "CO_ADMINISTERED", "THERAPEUTIC_TEST")


def _names_compound(text: Optional[str], aliases: Iterable[str]) -> bool:
    toks = tokens(text)
    for alias in aliases:
        a = tokens(alias)
        if a and any(toks[i:i + len(a)] == a for i in range(len(toks) - len(a) + 1)):
            return True
    return False


def classify_trial_role(study: Dict, aliases: Iterable[str]) -> Dict:
    """Classify the compound's role in one ClinicalTrials.gov v2 study."""
    aliases = [a for a in aliases if normalise(a)]
    ps = (study or {}).get("protocolSection") or {}
    ident = ps.get("identificationModule") or {}
    nct = ident.get("nctId")
    arms_mod = ps.get("armsInterventionsModule") or {}
    interventions = arms_mod.get("interventions") or []
    arms = arms_mod.get("armGroups") or []
    purpose = ((ps.get("designModule") or {}).get("designInfo") or {}).get("primaryPurpose")
    out = {"nct_id": nct, "primary_purpose": purpose, "evidence": [], "procedural_hits": []}

    def verdict(v):
        out["verdict"] = v
        return out

    if not interventions or not arms:
        out["evidence"].append("armsInterventionsModule lacks interventions or armGroups")
        return verdict("UNDETERMINED")

    by_name, own_named, other_only = {}, set(), set()
    for iv in interventions:
        name = iv.get("name") or ""
        by_name[normalise(name)] = iv
        if _names_compound(name, aliases):
            own_named.add(normalise(name))
            out["evidence"].append(f"intervention name names compound: {name!r}")
        elif any(_names_compound(o, aliases) for o in iv.get("otherNames") or []):
            other_only.add(normalise(name))
            out["evidence"].append(f"compound only in otherNames of {name!r}")
    if not own_named and not other_only:
        return verdict("NOT_NAMED")
    if not own_named:
        return verdict("BACKGROUND_OTHERNAME")

    texts = [("briefTitle", ident.get("briefTitle")), ("officialTitle", ident.get("officialTitle"))]
    texts += [("primaryOutcome", o.get("measure")) for o in
              ((ps.get("outcomesModule") or {}).get("primaryOutcomes") or [])]
    texts += [(f"arm:{a.get('label')}", a.get("description")) for a in arms]
    for field, text in texts:
        for m in PROCEDURAL_RE.finditer(text or ""):
            out["procedural_hits"].append(f"{field}: {m.group(0)!r}")
    if out["procedural_hits"]:
        return verdict("PROCEDURAL_CONTEXT")
    for field, text in texts:
        for m in BLOCK_RE.finditer(text or ""):
            out["procedural_hits"].append(f"{field}: {m.group(0)!r}")
    if out["procedural_hits"]:
        return verdict("PROCEDURE_DELIVERED")

    def active(n):
        return (n in by_name and not is_control_intervention(by_name[n])
                and (by_name[n].get("type") or "").upper() in ACTIVE_TYPES)

    compound_arms = []
    for a in arms:
        names = [normalise(n.split(":", 1)[-1]) for n in a.get("interventionNames") or []]
        if any(n in own_named for n in names):
            others = [n for n in names if n not in own_named and active(n)]
            compound_arms.append((a.get("type") or "UNKNOWN", others, a.get("label")))
            out["evidence"].append(f"arm {a.get('label')!r} type {a.get('type')} with other drugs {others}")
    if not compound_arms:
        out["evidence"].append("no armGroup lists the compound's intervention")
        return verdict("UNDETERMINED")
    types = {t for t, _, _ in compound_arms}
    if types <= COMPARATOR_ARMS:
        rival = [a.get("label") for a in arms if (a.get("type") or "") == "EXPERIMENTAL" and any(
            active(normalise(n.split(":", 1)[-1])) and normalise(n.split(":", 1)[-1]) not in own_named
            for n in a.get("interventionNames") or [])]
        if rival:
            out["evidence"].append(f"different agent in EXPERIMENTAL arm(s) {rival}")
            return verdict("COMPARATOR_ONLY")
        out["evidence"].append("comparator-typed arm(s) but no different experimental agent")
    if all(others for _, others, _ in compound_arms):
        return verdict("CO_ADMINISTERED")
    if not ({"EXPERIMENTAL"} | COMPARATOR_ARMS) & types:
        return verdict("UNDETERMINED")
    return verdict("THERAPEUTIC_TEST")


def summarise(results: List[Dict]) -> Dict[str, int]:
    counts = {v: 0 for v in VERDICTS}
    for r in results:
        counts[r["verdict"]] += 1
    return counts
