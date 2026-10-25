"""
Intervention matching for ClinicalTrials.gov evidence (EviRep).

PROBLEM THIS SOLVES
-------------------
`scripts/03_clinicaltrials_groundtruth.py` searches ClinicalTrials.gov with
`query.intr=<compound>`. That search expands along relationships that are NOT
evidence that the trial administers the compound:

    chemical class     "Phenol"         -> levodopa/carbidopa trials
    prodrug/metabolite "Norepinephrine" -> droxidopa trials
    pharmacological    "Dopamine"       -> sarizotan / safinamide / pramipexole
    excipient          "Mannitol"       -> droxidopa formulation trials
    registry expansion many compounds   -> one catch-all registry study

Script 03 already verified the trial's CONDITION client-side
(`is_actually_pd`). This module supplies the missing half: verifying the trial's
INTERVENTION.

MATCHING POLICY (conservative, deterministic, no fuzzy matching)
----------------------------------------------------------------
A trial counts as evidence for compound X only when a *structured* intervention
field names X. Evidence hierarchy, strongest first:

  1. `exact_name`     - a normalised intervention `name` equals the compound.
  2. `exact_othername`- a normalised `otherNames[]` entry equals the compound.
  3. `token_name`     - the compound's token sequence appears as a contiguous
                        token run inside an intervention `name`
                        (e.g. "Levodopa" in "ND0612 (Levodopa/Carbidopa solution)").
  4. `token_othername`- same, inside an `otherNames[]` entry.
  5. `synonym_*`      - as above, but matching a VERIFIED synonym or trade name
                        retrieved from ChEMBL via the Open Targets API
                        (see scripts/molecular_agent.py). Synonyms are never
                        invented here; if none could be retrieved, none are used.

Deliberately NOT accepted as evidence:
  * chemical-class, pharmacological-class or prodrug/metabolite relationships.
    The project's documentation does not define these as equivalent evidence, so
    treating them as such would silently change the research definition.
  * the free-text `description` field. It is prose and matching it reintroduces
    exactly the broad-text contamination being fixed.
  * substring matching that ignores token boundaries. "Phenol" must NOT match
    "Phenolphthalein", so comparison is on whole tokens, never raw substrings.

OUTCOMES (mutually exclusive, and the distinction is mandatory)
---------------------------------------------------------------
  MATCHED       - a structured field names the compound. Qualifies as evidence.
  NO_MATCH      - interventions were readable and none names the compound.
                  A verified negative.
  UNVERIFIABLE  - the structured intervention fields cannot answer the question,
                  e.g. a registry study whose name field says the drugs are
                  "too many characters to list in this field". Not evidence, but
                  NOT a verified negative either.
  API_FAILURE   - the trial record could not be retrieved. Never treated as
                  "no evidence".

This module performs no network I/O; it is pure and deterministic so it can be
unit-tested offline.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------

MATCHED = "MATCHED"
NO_MATCH = "NO_MATCH"
UNVERIFIABLE = "UNVERIFIABLE"
API_FAILURE = "API_FAILURE"

OUTCOMES = (MATCHED, NO_MATCH, UNVERIFIABLE, API_FAILURE)

#: Minimum length of an alias we are willing to match on. Guards against short
#: or degenerate synonyms (e.g. "DA", "L") matching unrelated interventions.
MIN_ALIAS_CHARS = 4

#: An intervention `name` longer than this is prose, not a drug name. Such a
#: field cannot be used to confirm OR deny the compound, so a trial whose
#: interventions are all prose is UNVERIFIABLE rather than a verified negative.
#: This is a general structural rule, not a list of known-bad trials.
PROSE_NAME_CHARS = 120


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_PUNCT = re.compile(r"[^a-z0-9]+")

#: Tokens that, on their own, describe a CONTROL arm rather than a studied agent.
#: An intervention whose entire name is built from these is a placebo/sham arm.
#: Its `otherNames` routinely list the inert filler (e.g. a droxidopa trial whose
#: placebo otherNames are ["Mannitol"]), which must not count as evidence that
#: the trial studies that filler. This is a structural rule about the arm's role,
#: not a list of known-bad compounds.
CONTROL_TOKENS = frozenset({
    "placebo", "placebos", "sham", "vehicle", "control", "comparator",
    "dummy", "sugar", "pill", "pills", "tablet", "tablets", "capsule",
    "capsules", "oral", "solution", "matching", "matched", "identical",
    "saline", "normal", "inactive", "no", "treatment", "standard", "care",
})


def normalise(text: Optional[str]) -> str:
    """
    Case/whitespace/punctuation/Unicode normalisation, reduced to space-separated
    alphanumeric tokens. NFKD strips accents and compatibility forms (e.g. the
    '®' in "Melatonin(Circadin®)" and the micro sign in dosages).
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text))
    ascii_only = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = ascii_only.lower()
    return _PUNCT.sub(" ", lowered).strip()


def tokens(text: Optional[str]) -> List[str]:
    norm = normalise(text)
    return norm.split() if norm else []


def _contains_token_run(haystack: Sequence[str], needle: Sequence[str]) -> bool:
    """True when `needle` appears as a contiguous run of whole tokens."""
    n, m = len(haystack), len(needle)
    if m == 0 or m > n:
        return False
    for i in range(n - m + 1):
        if haystack[i : i + m] == list(needle):
            return True
    return False


# ---------------------------------------------------------------------------
# Alias handling
# ---------------------------------------------------------------------------


def build_alias_set(
    compound: str,
    synonyms: Optional[Iterable[str]] = None,
    trade_names: Optional[Iterable[str]] = None,
    ambiguous_names: Optional[set] = None,
) -> List[Dict[str, str]]:
    """
    Build the ordered alias list used for matching.

    Returns dicts of {alias, normalised, source} where source is one of
    'compound_name', 'chembl_synonym', 'chembl_trade_name'. Nothing is invented:
    synonyms/trade names must be supplied by the caller from an authoritative
    source.

    Two filters protect against class collisions re-entering through the synonym
    list:

    * aliases shorter than MIN_ALIAS_CHARS are dropped;
    * `ambiguous_names` (normalised) are dropped. Pass the normalised names of
      every OTHER compound in the study. ChEMBL synonym lists sometimes contain
      the name of a related but DISTINCT drug -- observed live, ChEMBL lists
      "citalopram" under Escitalopram (a different drug: the racemate vs the
      S-enantiomer) and "doxycycline" under Tetracycline (a different drug of
      the same class). Matching on those would credit one compound with another
      compound's trials, reintroducing exactly the class-collision problem the
      matcher exists to prevent. An alias that is itself another study
      compound's name is ambiguous by construction and is therefore refused.
      The compound's own name is never filtered this way.
    """
    out: List[Dict[str, str]] = []
    seen = set()
    blocked = ambiguous_names or set()

    def add(alias: str, source: str, allow_ambiguous: bool = False) -> None:
        norm = normalise(alias)
        if not norm or len(norm.replace(" ", "")) < MIN_ALIAS_CHARS:
            return
        if norm in seen:
            return
        if not allow_ambiguous and norm in blocked:
            return
        seen.add(norm)
        out.append({"alias": alias, "normalised": norm, "source": source})

    add(compound, "compound_name", allow_ambiguous=True)
    for s in synonyms or []:
        add(s, "chembl_synonym")
    for t in trade_names or []:
        add(t, "chembl_trade_name")
    return out


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def is_control_intervention(intervention: Dict) -> bool:
    """
    True when this intervention is a control/placebo arm.

    Detected structurally: every token of its own name is a control word. So
    "Placebo", "Placebo Oral Tablet" and "Sugar Pill" are controls, while
    "HRG2010; Sustained-release Carbidopa/Levodopa administered placebo" is not
    (it names actual agents alongside the word "placebo").
    """
    name_tokens = tokens(intervention.get("name"))
    if not name_tokens:
        return False
    return all(tok in CONTROL_TOKENS for tok in name_tokens)


def _iter_fields(
    interventions: Sequence[Dict], include_controls: bool = False
) -> Iterable[Tuple[str, str, str]]:
    """Yield (field_kind, intervention_name, text) for every structured field.

    Control arms are skipped by default: their `otherNames` list inert fillers,
    not the studied agent.
    """
    for iv in interventions or []:
        if not include_controls and is_control_intervention(iv):
            continue
        name = iv.get("name") or ""
        if name:
            yield ("name", name, name)
        for other in iv.get("otherNames") or []:
            if other:
                yield ("othername", name, other)


def _all_names_are_prose(interventions: Sequence[Dict]) -> bool:
    """
    True when every intervention name is prose rather than a drug name.

    Registry / quality-improvement studies put their drug list in the free-text
    description and leave a sentence in `name`. Such a record cannot confirm or
    deny the compound from structured fields.
    """
    names = [iv.get("name") or "" for iv in interventions or []]
    names = [n for n in names if n.strip()]
    if not names:
        return False
    return all(len(n) > PROSE_NAME_CHARS for n in names)


def match_trial(
    compound: str,
    interventions: Optional[Sequence[Dict]],
    aliases: Optional[Sequence[Dict[str, str]]] = None,
    fetch_ok: bool = True,
) -> Dict[str, object]:
    """
    Decide whether `interventions` constitute evidence for `compound`.

    `interventions` is the live `protocolSection.armsInterventionsModule.interventions`
    list. `aliases` comes from build_alias_set(); when omitted only the compound
    name itself is used (no synonyms invented).

    Returns an auditable record:
        outcome, match_type, matched_intervention, matched_alias,
        match_source, qualifies, reason
    """
    base = {
        "compound": compound,
        "outcome": None,
        "match_type": None,
        "matched_intervention": None,
        "matched_alias": None,
        "match_source": None,
        "qualifies": False,
        "reason": None,
    }

    if not fetch_ok:
        base.update(outcome=API_FAILURE, reason="trial record could not be retrieved")
        return base

    if interventions is None:
        # The record WAS retrieved; it simply carries no structured intervention
        # list (observed for OBSERVATIONAL studies in search responses). That is
        # unverifiable, NOT an API failure -- conflating the two would overstate
        # outage rates and understate genuine data gaps.
        base.update(outcome=UNVERIFIABLE,
                    reason="no structured intervention list in the record "
                           "(typical of observational studies)")
        return base

    if len(interventions) == 0:
        base.update(outcome=UNVERIFIABLE,
                    reason="trial lists no structured interventions")
        return base

    alias_list = list(aliases) if aliases else build_alias_set(compound)
    if not alias_list:
        base.update(outcome=UNVERIFIABLE,
                    reason=f"no usable alias for {compound!r} "
                           f"(shorter than {MIN_ALIAS_CHARS} characters)")
        return base

    fields = list(_iter_fields(interventions))

    # Pass 1 — exact normalised equality (strongest).
    for kind, iv_name, text in fields:
        text_norm = normalise(text)
        for alias in alias_list:
            if text_norm == alias["normalised"]:
                base.update(
                    outcome=MATCHED,
                    match_type=f"exact_{kind}" if alias["source"] == "compound_name"
                               else f"synonym_exact_{kind}",
                    matched_intervention=iv_name,
                    matched_alias=alias["alias"],
                    match_source=alias["source"],
                    qualifies=True,
                    reason=f"intervention {kind} exactly equals {alias['alias']!r}",
                )
                return base

    # Pass 2 — contiguous whole-token run, for the COMPOUND NAME ONLY.
    # Synonyms/trade names are restricted to exact equality (pass 1): ChEMBL
    # synonym lists contain noisy entries (e.g. "Medopa" and "Dobutamine a"
    # appear under Dopamine), and token-run matching on those could credit a
    # different drug's trial. The compound's own name still needs token
    # matching so combination products such as
    # "ND0612 (Levodopa/Carbidopa solution)" resolve correctly.
    for kind, iv_name, text in fields:
        text_tokens = tokens(text)
        for alias in alias_list:
            if alias["source"] != "compound_name":
                continue
            if _contains_token_run(text_tokens, alias["normalised"].split()):
                base.update(
                    outcome=MATCHED,
                    match_type=f"token_{kind}" if alias["source"] == "compound_name"
                               else f"synonym_token_{kind}",
                    matched_intervention=iv_name,
                    matched_alias=alias["alias"],
                    match_source=alias["source"],
                    qualifies=True,
                    reason=f"intervention {kind} contains {alias['alias']!r} "
                           f"as whole token(s)",
                )
                return base

    # No match. Decide whether that is a verified negative or simply unanswerable.
    if _all_names_are_prose(interventions):
        base.update(
            outcome=UNVERIFIABLE,
            reason="all intervention names are free text, not drug names "
                   "(structured fields cannot confirm or deny the compound)",
        )
        return base

    # Did the compound appear ONLY in a control arm? Report that explicitly --
    # it is a common and otherwise confusing rejection (inert filler).
    control_only = False
    for kind, iv_name, text in _iter_fields(interventions, include_controls=True):
        text_norm = normalise(text)
        text_tokens = tokens(text)
        for alias in alias_list:
            hit = (text_norm == alias["normalised"] or
                   (alias["source"] == "compound_name" and
                    _contains_token_run(text_tokens, alias["normalised"].split())))
            if hit:
                control_only = True
                break
        if control_only:
            break

    if control_only:
        base.update(
            outcome=NO_MATCH,
            reason=f"{compound!r} appears only in a control/placebo arm "
                   f"(inert filler), not as a studied intervention",
        )
        return base

    base.update(
        outcome=NO_MATCH,
        reason=f"no structured intervention name or otherName contains "
               f"{compound!r} or a verified synonym",
    )
    return base
