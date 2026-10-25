"""
Molecular / Pathway Evidence Agent  (EviRep evidence dimension 5)

Builds a traceable molecular evidence chain:

    DRUG -> TARGET -> GENE -> PATHWAY -> PARKINSON'S DISEASE MECHANISM

and converts it into an explainable `molecular_plausibility_score`.

-------------------------------------------------------------------------------
DESIGN RULES (enforced, not aspirational)
-------------------------------------------------------------------------------
1. No biological relationship is ever invented. Every target, gene, pathway and
   disease link in the output carries `source`, an identifier where one exists,
   and provenance. Nothing is produced by an LLM or by this module's own
   reasoning -- it is all read from the Open Targets Platform API.

2. Drug identity is resolved at runtime, never hardcoded. Open Targets name
   search returns *fuzzy* neighbours (querying "Simvastatin" also returns
   PRAVASTATIN and FLUVASTATIN), so a hit is accepted only on normalised
   equality against the returned name / synonyms / trade names. A drug that
   cannot be matched exactly is reported unresolved -- it is not guessed.

3. Label-leakage control. The Open Targets target-disease association score is
   a composite over `datatypeScores`. Two of those datatypes must not be used
   by this project:
       - `clinical`   (datasource `clinical_precedence`) encodes that a drug
                      hitting this target is already in clinical trials for the
                      disease. That is effectively the EviRep ground-truth
                      label (post-cutoff PD trials) and also duplicates the
                      existing clinical-maturity dimension.
       - `literature` (datasource `europepmc`) is drug/gene-disease co-mention
                      counting, which duplicates the existing
                      literature-independence dimension and is not
                      cutoff-bounded.
   Both are therefore excluded by default via
   `MolecularAgentConfig.allowed_datatypes`. The overall Open Targets `score`
   field is deliberately NOT used, because it bakes those datatypes in.

4. Evidence strength is labelled, never flattened. Each evidence item is tiered
   DIRECT / INDIRECT / INFERRED / MISSING (see `EvidenceTier`). Absent evidence
   produces an explicit MISSING record plus a `limitations` entry -- it is never
   silently imputed to zero and never dropped.

5. `molecular_plausibility_score` and `confidence` are separate axes.
   A score of 0.0 with high confidence means "the evidence was retrieved and it
   does not support a molecular link". A score of 0.0 with confidence 0.0 means
   "no evidence could be retrieved". Collapsing these would be scientifically
   misleading.

-------------------------------------------------------------------------------
VERIFIED API FACTS (probed live against api.platform.opentargets.org,
Open Targets GraphQL API v26.9, data version 26.09, on 2026-10-05)
-------------------------------------------------------------------------------
* Parkinson's disease resolves to `MONDO_0005180` (via `search`). The commonly
  cited `EFO_0002508` was NOT used because it was not what the API returned.
* `drug(chemblId).mechanismsOfAction.rows[]` -> `{mechanismOfAction, actionType,
  targetName, references{source, ids, urls}, targets{id, approvedSymbol}}`.
  `targets[].id` is an Ensembl gene ID, giving the TARGET -> GENE step directly.
* `targets(ensemblIds: [...])` batches many targets into one request, each with
  `pathways{pathwayId, pathway, topLevelTerm}` (Reactome) and
  `associatedDiseases(Bs: [diseaseId]){rows{score, datatypeScores{id, score}}}`.
* `mapIds(queryTerms: [...], entityNames: ["drug"])` batches name resolution.
* `associationDatasources()` returned an empty list, so the datatype allowlist
  is built from datatype IDs observed in live responses and is configurable.
  See development_log/ERRORS_AND_BLOCKERS.md E-004.

No authentication is required by this API, so this module reads no credentials
and logs none.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import requests


# ============================================================================
# CONSTANTS
# ============================================================================

OPENTARGETS_GRAPHQL_URL = "https://api.platform.opentargets.org/api/v4/graphql"

#: Verified by live `search` query (see module docstring). Do not edit from memory.
PD_DISEASE_EFO_ID = "MONDO_0005180"
PD_DISEASE_NAME = "Parkinson's disease"

#: Hetionet's PD identifier, used by scripts 01/02. Kept here only so the two
#: identifier systems are traceable to each other in the output provenance.
HETIONET_PD_DISEASE_ID = "Disease::DOID:14330"

DEFAULT_CACHE_DIR = os.path.join("data", "cache", "molecular")


class EvidenceTier:
    """Evidence strength labels. Ordered strongest -> weakest."""

    DIRECT = "direct"       # drug target is itself PD-associated (allowed datatypes)
    INDIRECT = "indirect"   # drug target shares a Reactome pathway with a PD gene
    INFERRED = "inferred"   # only a shared Reactome top-level term (weak)
    MISSING = "missing"     # no evidence retrievable

    ALL = (DIRECT, INDIRECT, INFERRED, MISSING)


class MolecularAgentError(RuntimeError):
    """Base error for this module."""


class OpenTargetsUnavailable(MolecularAgentError):
    """API could not be reached / returned an unusable response after retries."""


class MalformedEvidenceChain(MolecularAgentError):
    """Output failed schema validation. Raised loudly -- never swallowed."""


# ============================================================================
# CONFIGURATION
# ============================================================================


@dataclass(frozen=True)
class MolecularAgentConfig:
    """
    All tunables in one place. Every weight is documented and configurable.

    WEIGHT RATIONALE (chosen a priori; NOT fitted or tuned against the EviRep
    ground-truth labels -- doing so would be label leakage):

      `weight_direct` (0.6) > `weight_pathway` (0.4)

    because a target that is itself associated with Parkinson's disease by
    genetic / animal-model / somatic / expression evidence is stronger
    mechanistic support than a target that merely shares a Reactome pathway
    with a PD-associated gene. The 60/40 split encodes only that ordering
    (direct dominates but does not erase pathway signal). It is not claimed to
    be optimal, and no label-based search was run to select it. Override via
    this config to test sensitivity.
    """

    disease_id: str = PD_DISEASE_EFO_ID
    disease_name: str = PD_DISEASE_NAME

    #: Datatypes permitted to contribute to the direct target-disease component.
    #: `clinical` and `literature` are excluded -- see module docstring rule 3.
    allowed_datatypes: Tuple[str, ...] = (
        "genetic_association",
        "genetic_literature",
        "animal_model",
        "affected_pathway",
        "somatic_mutation",
        "rna_expression",
    )

    #: Datatypes explicitly refused, kept as an auditable record in the output.
    excluded_datatypes: Tuple[str, ...] = ("clinical", "literature")

    #: Datatypes permitted to put a gene INTO the PD module (the disease end of
    #: the chain). Deliberately narrower than `allowed_datatypes`: it omits
    #: `affected_pathway`.
    #:
    #: RATIONALE (anti-circularity). Open Targets' `affected_pathway` evidence
    #: is itself derived from pathway / systems-biology sources. If a gene
    #: entered the PD module on `affected_pathway` evidence, and the pathway
    #: component then measured Reactome overlap against that same gene, the
    #: pathway annotation would be counted twice -- once to make the gene a "PD
    #: gene" and again to make the drug look PD-adjacent. That inflates the
    #: pathway component without adding independent information. Observed
    #: concretely in the first sample run: ADORA2B entered the module on
    #: `affected_pathway`=0.437 alone and then matched caffeine's targets
    #: through generic pathways including "Surfactant metabolism".
    #:
    #: Module membership therefore requires disease-gene evidence that is
    #: independent of pathway annotation. `affected_pathway` remains available
    #: to the DIRECT component, where no such double-count arises.
    module_datatypes: Tuple[str, ...] = (
        "genetic_association",
        "genetic_literature",
        "animal_model",
        "somatic_mutation",
        "rna_expression",
    )

    # --- scoring weights (must sum to 1.0; validated in __post_init__) ---
    weight_direct: float = 0.6
    weight_pathway: float = 0.4

    #: Size of the PD "molecular module": top-N PD-associated genes retrieved
    #: from Open Targets, re-ranked using allowed datatypes only. Bounded to keep
    #: the request count and the pathway-overlap denominator stable/reproducible.
    pd_module_size: int = 300

    #: Minimum allowed-datatype score for a gene to enter the PD module at all.
    #: Filters out genes whose association is near-zero noise.
    pd_module_min_score: float = 0.10

    #: TD-042. When True, a pathway counts as a PD pathway only through a module gene that is NOT one of
    #: the drug's own targets. A target that is itself a module gene otherwise makes every one of its
    #: pathways "shared" by construction, re-using the target-PD association already scored by the
    #: direct component. Default False reproduces the approved baseline; changing it is an owner decision.
    pathway_excludes_drug_targets: bool = False

    # --- transport ---
    min_request_interval_s: float = 0.25   # self-throttle; see note below
    max_retries: int = 4
    backoff_base_s: float = 1.0
    timeout_s: int = 60
    cache_dir: str = DEFAULT_CACHE_DIR
    use_cache: bool = True

    def __post_init__(self) -> None:
        total = self.weight_direct + self.weight_pathway
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"weights must sum to 1.0, got {total} "
                f"(direct={self.weight_direct}, pathway={self.weight_pathway})"
            )
        overlap = set(self.allowed_datatypes) & set(self.excluded_datatypes)
        if overlap:
            raise ValueError(f"datatype in both allowed and excluded: {sorted(overlap)}")
        leaky_module = set(self.module_datatypes) & set(self.excluded_datatypes)
        if leaky_module:
            raise ValueError(
                f"module_datatypes must not contain excluded datatypes: "
                f"{sorted(leaky_module)}"
            )


# NOTE on throttling: Open Targets does not publish a specific numeric rate
# limit for the GraphQL endpoint, so no limit value is asserted here. The
# default 0.25 s floor (<=4 req/s) is a deliberately conservative self-imposed
# ceiling, combined with aggressive on-disk caching and request batching so a
# re-run of the same cohort issues no network calls at all.


# ============================================================================
# TRANSPORT: cached, throttled, retrying GraphQL client
# ============================================================================


class OpenTargetsClient:
    """
    Minimal GraphQL client with on-disk caching, throttling and backoff.

    Caching is keyed on sha256(query + canonical-json(variables)), so it is
    exact and order-independent. Cached reads make the agent deterministic and
    cheap to re-run, which is what makes the pipeline resumable.
    """

    def __init__(
        self,
        config: Optional[MolecularAgentConfig] = None,
        session: Optional[requests.Session] = None,
        url: str = OPENTARGETS_GRAPHQL_URL,
    ) -> None:
        self.config = config or MolecularAgentConfig()
        self.url = url
        self.session = session or requests.Session()
        self._last_request_at = 0.0
        self.stats = {"network": 0, "cache_hits": 0, "retries": 0, "failures": 0}
        if self.config.use_cache:
            os.makedirs(self.config.cache_dir, exist_ok=True)

    # -- cache ---------------------------------------------------------------

    def _cache_path(self, query: str, variables: Dict[str, Any]) -> str:
        blob = json.dumps(
            {"q": " ".join(query.split()), "v": variables},
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
        return os.path.join(self.config.cache_dir, f"{digest}.json")

    def _read_cache(self, path: str) -> Optional[Dict[str, Any]]:
        if not (self.config.use_cache and os.path.exists(path)):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None  # corrupt cache entry -> re-fetch

    def _write_cache(self, path: str, payload: Dict[str, Any]) -> None:
        if not self.config.use_cache:
            return
        tmp = f"{path}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            os.replace(tmp, path)  # atomic; a killed run cannot leave a half file
        except OSError:
            pass  # cache is an optimisation, never a correctness requirement

    # -- throttle ------------------------------------------------------------

    def _throttle(self) -> None:
        gap = time.monotonic() - self._last_request_at
        wait = self.config.min_request_interval_s - gap
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    # -- query ---------------------------------------------------------------

    def query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query. Returns the `data` object.

        Raises OpenTargetsUnavailable if the API cannot be used after retries.
        Callers are expected to catch that and degrade to an empty-evidence
        state rather than fabricating data.
        """
        variables = variables or {}
        path = self._cache_path(query, variables)

        cached = self._read_cache(path)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return cached

        last_error = "unknown"
        for attempt in range(self.config.max_retries + 1):
            if attempt:
                # exponential backoff with jitter, to avoid synchronised retries
                delay = self.config.backoff_base_s * (2 ** (attempt - 1))
                time.sleep(delay + random.uniform(0, 0.3 * delay))
                self.stats["retries"] += 1

            self._throttle()
            try:
                self.stats["network"] += 1
                resp = self.session.post(
                    self.url,
                    json={"query": query, "variables": variables},
                    timeout=self.config.timeout_s,
                )
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                continue

            # Retry on throttling / transient server errors, honouring Retry-After.
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        time.sleep(min(float(retry_after), 60.0))
                    except ValueError:
                        pass
                continue

            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
                break  # 4xx other than 429 is a client bug; retrying won't help

            try:
                body = resp.json()
            except ValueError as exc:
                last_error = f"invalid JSON: {exc}"
                continue

            if body.get("errors"):
                # A GraphQL error is a query defect: surface it, do not retry.
                last_error = f"GraphQL errors: {json.dumps(body['errors'])[:400]}"
                break

            data = body.get("data")
            if data is None:
                last_error = "response contained no 'data'"
                continue

            self._write_cache(path, data)
            return data

        self.stats["failures"] += 1
        raise OpenTargetsUnavailable(last_error)


# ============================================================================
# STEP 1: DRUG NORMALISATION  (drug name -> ChEMBL molecule)
# ============================================================================

_MAPIDS_QUERY = """
query($terms:[String!]!){
  mapIds(queryTerms:$terms, entityNames:["drug"]){
    mappings{ term hits{ id name entity } }
  }
}
"""

_DRUG_DETAIL_QUERY = """
query($ids:[String!]!){
  drugs(chemblIds:$ids){
    id name drugType
    synonyms{ label source }
    tradeNames{ label source }
    mechanismsOfAction{
      rows{
        mechanismOfAction actionType targetName
        references{ source ids urls }
        targets{ id approvedSymbol approvedName }
      }
    }
  }
}
"""


def _norm_name(value: str) -> str:
    """Casefold and strip punctuation/whitespace for identity comparison only."""
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _alias_labels(drug: Dict[str, Any]) -> List[str]:
    """
    Collect synonym / trade-name strings from a drug record.

    `Drug.synonyms` and `Drug.tradeNames` are `[DrugLabelAndSource!]!`, i.e.
    `{label, source}` objects -- NOT plain strings. Querying them without a
    sub-selection is an HTTP 400; treating them as strings silently yields zero
    alias matches. Both mistakes were made and fixed (see E-005).
    """
    labels: List[str] = []
    for key in ("synonyms", "tradeNames"):
        for entry in drug.get(key) or []:
            if isinstance(entry, dict):
                if entry.get("label"):
                    labels.append(entry["label"])
            elif isinstance(entry, str):  # tolerate a plain-string shape
                labels.append(entry)
    return labels


def normalize_drug_batch(
    names: Sequence[str],
    client: OpenTargetsClient,
) -> Dict[str, Dict[str, Any]]:
    """
    Resolve many drug names to ChEMBL IDs in one request.

    A hit is accepted ONLY if its name (or, after the detail fetch, one of its
    synonyms / trade names) is an exact normalised match for the query term.
    Open Targets returns ranked fuzzy neighbours -- accepting those would
    silently attribute one drug's targets to another. See E-003.

    Returns {input_name: {"chembl_id", "resolved_name", "match_type", "candidates"}}
    with `chembl_id=None` when unresolved.
    """
    out: Dict[str, Dict[str, Any]] = {
        n: {"chembl_id": None, "resolved_name": None, "match_type": "unresolved",
            "candidates": []}
        for n in names
    }
    if not names:
        return out

    data = client.query(_MAPIDS_QUERY, {"terms": list(names)})
    mappings = (data.get("mapIds") or {}).get("mappings") or []

    # Pass 1: exact match on the primary name returned by the search index.
    needs_synonym_check: Dict[str, List[Dict[str, Any]]] = {}
    for mapping in mappings:
        term = mapping.get("term")
        if term not in out:
            continue
        hits = [h for h in (mapping.get("hits") or []) if h.get("entity") == "drug"]
        out[term]["candidates"] = [{"id": h.get("id"), "name": h.get("name")} for h in hits]
        target = _norm_name(term)
        exact = [h for h in hits if _norm_name(h.get("name", "")) == target]
        if exact:
            out[term].update(
                chembl_id=exact[0]["id"],
                resolved_name=exact[0]["name"],
                match_type="exact_name",
            )
        elif hits:
            needs_synonym_check[term] = hits

    # Pass 2: for the remainder, check synonyms/trade names of the candidates.
    # Only one extra batched request, and only when pass 1 was inconclusive.
    if needs_synonym_check:
        candidate_ids = sorted({h["id"] for hits in needs_synonym_check.values()
                                for h in hits if h.get("id")})
        detail_by_id: Dict[str, Dict[str, Any]] = {}
        if candidate_ids:
            try:
                detail = client.query(_DRUG_DETAIL_QUERY, {"ids": candidate_ids})
                for drug in detail.get("drugs") or []:
                    if drug and drug.get("id"):
                        detail_by_id[drug["id"]] = drug
            except OpenTargetsUnavailable:
                detail_by_id = {}  # leave unresolved rather than guess

        for term, hits in needs_synonym_check.items():
            target = _norm_name(term)
            for hit in hits:
                drug = detail_by_id.get(hit.get("id") or "")
                if not drug:
                    continue
                aliases = _alias_labels(drug)
                if any(_norm_name(a) == target for a in aliases):
                    out[term].update(
                        chembl_id=drug["id"],
                        resolved_name=drug.get("name"),
                        match_type="exact_synonym",
                    )
                    break

    return out


# ============================================================================
# STEP 2: DRUG -> TARGET -> GENE  (mechanisms of action)
# ============================================================================


def get_drug_mechanisms(
    chembl_ids: Sequence[str],
    client: OpenTargetsClient,
) -> Dict[str, Dict[str, Any]]:
    """
    Batch-fetch mechanisms of action. Returns {chembl_id: drug_record}.

    Each mechanism row carries its own `references` (e.g. DailyMed, ChEMBL),
    which become the provenance of the DRUG -> TARGET edge.
    """
    if not chembl_ids:
        return {}
    data = client.query(_DRUG_DETAIL_QUERY, {"ids": list(chembl_ids)})
    return {d["id"]: d for d in (data.get("drugs") or []) if d and d.get("id")}


def extract_targets(drug_record: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Flatten mechanismsOfAction into one record per (gene target, mechanism).

    The Ensembl gene ID in `targets[].id` is what makes TARGET -> GENE explicit
    rather than inferred: Open Targets keys drug targets on genes directly.
    """
    if not drug_record:
        return []
    moa = drug_record.get("mechanismsOfAction") or {}
    rows = moa.get("rows") or []

    seen: set = set()
    targets: List[Dict[str, Any]] = []
    for row in rows:
        refs = [
            {
                "source": r.get("source"),
                "ids": r.get("ids") or [],
                "urls": r.get("urls") or [],
            }
            for r in (row.get("references") or [])
        ]
        for tgt in row.get("targets") or []:
            ensembl_id = tgt.get("id")
            if not ensembl_id:
                continue
            key = (ensembl_id, row.get("mechanismOfAction"), row.get("actionType"))
            if key in seen:
                continue
            seen.add(key)
            targets.append(
                {
                    "ensembl_id": ensembl_id,
                    "gene_symbol": tgt.get("approvedSymbol"),
                    "gene_name": tgt.get("approvedName"),
                    "mechanism_of_action": row.get("mechanismOfAction"),
                    "action_type": row.get("actionType"),
                    "target_name": row.get("targetName"),
                    "source": "ChEMBL via OpenTargets",
                    "references": refs,
                }
            )
    # Deterministic ordering so repeated runs produce byte-identical output.
    targets.sort(key=lambda t: (t["ensembl_id"], t["mechanism_of_action"] or "",
                                t["action_type"] or ""))
    return targets


# ============================================================================
# STEP 3: GENE -> PATHWAY  and  GENE -> DISEASE
# ============================================================================

_TARGET_QUERY = """
query($ids:[String!]!,$disease:String!){
  targets(ensemblIds:$ids){
    id approvedSymbol approvedName
    pathways{ pathwayId pathway topLevelTerm }
    associatedDiseases(Bs:[$disease]){
      rows{ score disease{ id name } datatypeScores{ id score } }
    }
  }
}
"""


def get_target_details(
    ensembl_ids: Sequence[str],
    client: OpenTargetsClient,
    config: MolecularAgentConfig,
    batch_size: int = 25,
) -> Dict[str, Dict[str, Any]]:
    """
    Batch-fetch Reactome pathways + disease association for targets.

    Batched (default 25/request) to keep request count low; IDs are sorted so
    batch boundaries -- and therefore cache keys -- are deterministic.
    """
    unique_ids = sorted({i for i in ensembl_ids if i})
    details: Dict[str, Dict[str, Any]] = {}
    for start in range(0, len(unique_ids), batch_size):
        chunk = unique_ids[start : start + batch_size]
        data = client.query(_TARGET_QUERY, {"ids": chunk, "disease": config.disease_id})
        for tgt in data.get("targets") or []:
            if tgt and tgt.get("id"):
                details[tgt["id"]] = tgt
    return details


def filtered_disease_link(
    target_detail: Optional[Dict[str, Any]],
    config: MolecularAgentConfig,
) -> Optional[Dict[str, Any]]:
    """
    Extract this target's disease association using ALLOWED datatypes only.

    The Open Targets composite `score` is intentionally not used -- it includes
    `clinical` and `literature`. Instead the allowed datatype scores are
    re-aggregated with `max`.

    HONEST CAVEAT, surfaced in the output: `max` over allowed datatypes is a
    simplified re-aggregation, NOT Open Targets' official harmonic-sum
    weighting. It is used because the per-datatype weights that produce the
    official score are not exposed by the API response, and inventing weights
    would be fabrication. `max` is the conservative, interpretable choice
    ("strongest permitted evidence type"), and the full per-datatype breakdown
    is retained in the output so any other aggregation can be recomputed later.
    """
    if not target_detail:
        return None
    rows = ((target_detail.get("associatedDiseases") or {}).get("rows")) or []
    if not rows:
        return None

    row = rows[0]  # Bs filter restricts to the one requested disease
    allowed = set(config.allowed_datatypes)
    excluded = set(config.excluded_datatypes)

    all_scores = {
        d["id"]: d["score"] for d in (row.get("datatypeScores") or []) if d.get("id")
    }
    kept = {k: v for k, v in all_scores.items() if k in allowed}
    dropped = {k: v for k, v in all_scores.items() if k in excluded}

    return {
        "disease_id": (row.get("disease") or {}).get("id"),
        "disease_name": (row.get("disease") or {}).get("name"),
        "score_allowed_datatypes": max(kept.values()) if kept else 0.0,
        "aggregation": "max over allowed datatypes (not OpenTargets harmonic sum)",
        "datatype_scores_used": dict(sorted(kept.items())),
        "datatype_scores_excluded_for_leakage": dict(sorted(dropped.items())),
        "opentargets_overall_score_not_used": row.get("score"),
        "source": "OpenTargets target-disease association",
    }


# ============================================================================
# STEP 4: THE PD MOLECULAR MODULE  (disease -> genes -> pathways)
# ============================================================================

_DISEASE_TARGETS_QUERY = """
query($disease:String!,$size:Int!){
  disease(efoId:$disease){
    id name
    associatedTargets(page:{index:0,size:$size}){
      count
      rows{ score target{ id approvedSymbol } datatypeScores{ id score } }
    }
  }
}
"""


@dataclass
class DiseaseModule:
    """PD genes and their Reactome pathways, built from allowed datatypes only."""

    disease_id: str
    disease_name: str
    genes: Dict[str, Dict[str, Any]] = field(default_factory=dict)      # ensembl -> info
    pathway_to_genes: Dict[str, set] = field(default_factory=dict)      # R-HSA -> {ensembl}
    pathway_names: Dict[str, str] = field(default_factory=dict)
    top_level_terms: Dict[str, set] = field(default_factory=dict)       # term -> {R-HSA}
    total_associated_targets: int = 0
    source: str = "OpenTargets disease-target associations + Reactome pathways"
    #: Datatypes that were permitted to put a gene in this module (provenance).
    module_datatypes: Tuple[str, ...] = ()

    @property
    def pathway_ids(self) -> set:
        return set(self.pathway_to_genes)


def build_disease_module(
    client: OpenTargetsClient,
    config: MolecularAgentConfig,
) -> DiseaseModule:
    """
    Retrieve PD-associated genes, keep only those supported by allowed
    datatypes, and collect their Reactome pathways.

    This is the "PARKINSON'S DISEASE MECHANISM" end of the chain. It is
    computed once per run and cached, so it costs a bounded number of requests
    regardless of how many drugs are scored.
    """
    data = client.query(
        _DISEASE_TARGETS_QUERY,
        {"disease": config.disease_id, "size": config.pd_module_size},
    )
    disease = data.get("disease") or {}
    assoc = disease.get("associatedTargets") or {}

    module = DiseaseModule(
        disease_id=disease.get("id") or config.disease_id,
        disease_name=disease.get("name") or config.disease_name,
        total_associated_targets=assoc.get("count") or 0,
        module_datatypes=tuple(config.module_datatypes),
    )

    allowed = set(config.module_datatypes)
    for row in assoc.get("rows") or []:
        tgt = row.get("target") or {}
        ensembl_id = tgt.get("id")
        if not ensembl_id:
            continue
        kept = {
            d["id"]: d["score"]
            for d in (row.get("datatypeScores") or [])
            if d.get("id") in allowed
        }
        if not kept:
            continue  # association rested entirely on excluded datatypes
        best = max(kept.values())
        if best < config.pd_module_min_score:
            continue
        module.genes[ensembl_id] = {
            "ensembl_id": ensembl_id,
            "gene_symbol": tgt.get("approvedSymbol"),
            "score_allowed_datatypes": best,
            "datatype_scores_used": dict(sorted(kept.items())),
        }

    # Pathways for the module genes (batched, cached).
    details = get_target_details(sorted(module.genes), client, config)
    for ensembl_id, detail in details.items():
        for pathway in detail.get("pathways") or []:
            pid = pathway.get("pathwayId")
            if not pid:
                continue
            module.pathway_to_genes.setdefault(pid, set()).add(ensembl_id)
            module.pathway_names[pid] = pathway.get("pathway") or ""
            term = pathway.get("topLevelTerm")
            if term:
                module.top_level_terms.setdefault(term, set()).add(pid)

    return module


# ============================================================================
# STEP 5: BUILD THE MECHANISTIC CHAIN + SCORE
# ============================================================================


def build_mechanistic_chain(
    drug_name: str,
    chembl_id: Optional[str],
    targets: List[Dict[str, Any]],
    target_details: Dict[str, Dict[str, Any]],
    module: DiseaseModule,
    config: MolecularAgentConfig,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Assemble DRUG -> TARGET -> GENE -> PATHWAY -> DISEASE links.

    Returns (mechanistic_chain, pathways, evidence). Every chain step names its
    source and tier; nothing is asserted without a retrieved record behind it.
    """
    chain: List[Dict[str, Any]] = []
    pathways: List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []
    # every target of the drug (Ensembl IDs), not only the one whose direct score is the maximum
    own_targets = {t["ensembl_id"] for t in targets if t.get("ensembl_id")}

    for tgt in targets:
        ensembl_id = tgt["ensembl_id"]
        detail = target_details.get(ensembl_id)

        # --- DRUG -> TARGET -> GENE (pharmacological fact, with references) ---
        chain.append(
            {
                "step": "drug_to_target",
                "from": drug_name,
                "from_id": chembl_id,
                "to": tgt["gene_symbol"],
                "to_id": ensembl_id,
                "relation": tgt["action_type"],
                "detail": tgt["mechanism_of_action"],
                "tier": EvidenceTier.DIRECT,
                "source": tgt["source"],
                "references": tgt["references"],
            }
        )
        evidence.append(
            {
                "tier": EvidenceTier.DIRECT,
                "claim": f"{drug_name} acts on {tgt['gene_symbol']} "
                         f"({tgt['action_type']})",
                "source": tgt["source"],
                "identifiers": {"chembl": chembl_id, "ensembl": ensembl_id},
                "references": tgt["references"],
                "strength": None,  # ChEMBL MoA is categorical, not scored
            }
        )

        # --- GENE -> DISEASE (direct, allowed datatypes only) ---
        link = filtered_disease_link(detail, config)
        if link and link["score_allowed_datatypes"] > 0:
            chain.append(
                {
                    "step": "gene_to_disease",
                    "from": tgt["gene_symbol"],
                    "from_id": ensembl_id,
                    "to": link["disease_name"],
                    "to_id": link["disease_id"],
                    "relation": "associated_with",
                    "detail": link["aggregation"],
                    "tier": EvidenceTier.DIRECT,
                    "source": link["source"],
                    "strength": link["score_allowed_datatypes"],
                }
            )
            evidence.append(
                {
                    "tier": EvidenceTier.DIRECT,
                    "claim": f"{tgt['gene_symbol']} is associated with "
                             f"{link['disease_name']}",
                    "source": link["source"],
                    "identifiers": {"ensembl": ensembl_id,
                                    "disease": link["disease_id"]},
                    "strength": link["score_allowed_datatypes"],
                    "datatype_scores_used": link["datatype_scores_used"],
                    "datatype_scores_excluded_for_leakage":
                        link["datatype_scores_excluded_for_leakage"],
                }
            )

        # --- GENE -> PATHWAY -> DISEASE (indirect / inferred) ---
        for pathway in (detail or {}).get("pathways") or []:
            pid = pathway.get("pathwayId")
            if not pid:
                continue
            module_genes = module.pathway_to_genes.get(pid, set())
            removed = sorted(module_genes & own_targets) if config.pathway_excludes_drug_targets else []
            shared_genes = sorted(module_genes - set(removed))
            term = pathway.get("topLevelTerm")
            term_shared = bool(term and term in module.top_level_terms)

            if shared_genes:
                tier = EvidenceTier.INDIRECT
            elif term_shared:
                tier = EvidenceTier.INFERRED
            else:
                tier = None  # pathway recorded, but it links nothing to PD

            pathways.append(
                {
                    "pathway_id": pid,
                    "pathway_name": pathway.get("pathway"),
                    "top_level_term": term,
                    "gene_symbol": tgt["gene_symbol"],
                    "ensembl_id": ensembl_id,
                    "source": "Reactome via OpenTargets",
                    "in_disease_module": bool(shared_genes),
                    "disease_module_genes_in_pathway": [
                        module.genes[g]["gene_symbol"] for g in shared_genes
                        if g in module.genes
                    ],
                    "tier": tier or EvidenceTier.MISSING,
                    **({"drug_targets_excluded_from_shared": [
                        module.genes[g]["gene_symbol"] for g in removed if g in module.genes]}
                       if config.pathway_excludes_drug_targets else {}),
                }
            )

            if tier == EvidenceTier.INDIRECT:
                shared_symbols = [
                    module.genes[g]["gene_symbol"] for g in shared_genes
                    if g in module.genes
                ]
                chain.append(
                    {
                        "step": "pathway_to_disease",
                        "from": tgt["gene_symbol"],
                        "from_id": ensembl_id,
                        "via": pathway.get("pathway"),
                        "via_id": pid,
                        "to": module.disease_name,
                        "to_id": module.disease_id,
                        "relation": "shares_pathway_with_disease_gene",
                        "tier": EvidenceTier.INDIRECT,
                        "source": "Reactome via OpenTargets",
                        "disease_genes_in_pathway": shared_symbols,
                    }
                )
                evidence.append(
                    {
                        "tier": EvidenceTier.INDIRECT,
                        "claim": f"{tgt['gene_symbol']} shares Reactome pathway "
                                 f"'{pathway.get('pathway')}' with "
                                 f"{module.disease_name} gene(s): "
                                 f"{', '.join(shared_symbols)}",
                        "source": "Reactome via OpenTargets",
                        "identifiers": {"reactome": pid, "ensembl": ensembl_id},
                        "strength": None,  # pathway co-membership is unweighted
                    }
                )
            elif tier == EvidenceTier.INFERRED:
                evidence.append(
                    {
                        "tier": EvidenceTier.INFERRED,
                        "claim": f"{tgt['gene_symbol']} pathway "
                                 f"'{pathway.get('pathway')}' shares only the "
                                 f"broad Reactome area '{term}' with "
                                 f"{module.disease_name} genes. This is a weak, "
                                 f"non-mechanistic co-location.",
                        "source": "Reactome via OpenTargets",
                        "identifiers": {"reactome": pid, "ensembl": ensembl_id},
                        "strength": None,
                    }
                )

    chain.sort(key=lambda c: (c["step"], str(c.get("to_id")), str(c.get("from_id"))))
    pathways.sort(key=lambda p: (p["pathway_id"], p["ensembl_id"]))
    return chain, pathways, evidence


def score_molecular_plausibility(
    targets: List[Dict[str, Any]],
    target_details: Dict[str, Dict[str, Any]],
    pathways: List[Dict[str, Any]],
    module: DiseaseModule,
    config: MolecularAgentConfig,
) -> Dict[str, Any]:
    """
    Compute an explainable molecular plausibility score in [0, 1].

        score = w_direct * direct_component + w_pathway * pathway_component

    direct_component  = max over the drug's targets of that target's
                        allowed-datatype PD association score.
                        -> "strongest permitted gene-disease evidence"
    pathway_component = (# of the drug's target pathways that contain >=1 PD
                        module gene) / (# of the drug's target pathways)
                        -> "what fraction of this drug's biology is PD biology"

    Both components are in [0, 1], so the score is too. The returned dict
    includes every intermediate value so the score is auditable, and
    `explanation` renders it in words.

    INFERRED (shared top-level term only) evidence deliberately contributes
    0 to the score. Reactome top-level terms such as "Signal Transduction"
    cover thousands of genes; counting them would manufacture signal.
    """
    direct_per_target: Dict[str, float] = {}
    for tgt in targets:
        link = filtered_disease_link(target_details.get(tgt["ensembl_id"]), config)
        if link:
            direct_per_target[tgt["gene_symbol"] or tgt["ensembl_id"]] = \
                link["score_allowed_datatypes"]

    direct_component = max(direct_per_target.values()) if direct_per_target else 0.0

    distinct_pathways = {p["pathway_id"]: p for p in pathways}
    n_pathways = len(distinct_pathways)
    n_in_module = sum(1 for p in distinct_pathways.values() if p["in_disease_module"])
    pathway_component = (n_in_module / n_pathways) if n_pathways else 0.0

    score = (
        config.weight_direct * direct_component
        + config.weight_pathway * pathway_component
    )

    explanation = (
        f"score = {config.weight_direct} x direct({direct_component:.4f}) "
        f"+ {config.weight_pathway} x pathway({n_in_module}/{n_pathways} "
        f"= {pathway_component:.4f}) = {score:.4f}"
    )

    return {
        "molecular_plausibility_score": round(score, 6),
        "components": {
            "direct_target_disease": round(direct_component, 6),
            "pathway_overlap": round(pathway_component, 6),
        },
        "weights": {
            "direct": config.weight_direct,
            "pathway": config.weight_pathway,
        },
        "detail": {
            "direct_score_per_target": {
                k: round(v, 6) for k, v in sorted(direct_per_target.items())
            },
            "n_target_pathways": n_pathways,
            "n_target_pathways_in_disease_module": n_in_module,
            "allowed_datatypes": list(config.allowed_datatypes),
            "excluded_datatypes_for_leakage": list(config.excluded_datatypes),
        },
        "explanation": explanation,
    }


def compute_confidence(
    resolved: bool,
    targets: List[Dict[str, Any]],
    target_details: Dict[str, Dict[str, Any]],
    pathways: List[Dict[str, Any]],
    module: DiseaseModule,
) -> Dict[str, Any]:
    """
    Confidence = how complete the retrieved evidence was, NOT how strong it was.

    Four independent availability checks, averaged. This separation is what lets
    a consumer tell "evidence retrieved, and it says no" (score 0, confidence
    high) from "we could not look" (score 0, confidence 0).
    """
    checks = {
        "drug_resolved": bool(resolved),
        "has_targets": bool(targets),
        "targets_have_pathways": bool(pathways),
        "disease_module_available": bool(module.genes),
    }
    value = sum(1 for v in checks.values() if v) / len(checks)
    return {"confidence": round(value, 6), "checks": checks}


# ============================================================================
# OUTPUT CONTRACT + VALIDATION
# ============================================================================

REQUIRED_OUTPUT_KEYS = (
    "drug",
    "disease",
    "targets",
    "genes",
    "pathways",
    "disease_links",
    "mechanistic_chain",
    "molecular_plausibility_score",
    "confidence",
    "evidence",
    "limitations",
)


def is_retrieval_failure(record: Dict[str, Any]) -> bool:
    """True for a record written because Open Targets could not be reached. Its 0.0 score is a
    recorded failure, not a measured absence of evidence, and must not be scored or treated as done."""
    return (any("(API unavailable)" in str(l) for l in record.get("limitations") or [])
            or any(str(e.get("source", "")).endswith("(unavailable)") for e in record.get("evidence") or []))


def validate_output(record: Dict[str, Any]) -> None:
    """
    Fail loudly on a malformed evidence chain.

    Called on every record produced by `run_agent`, so a schema regression
    surfaces as a test/pipeline failure rather than silently corrupting results.
    """
    if not isinstance(record, dict):
        raise MalformedEvidenceChain(f"record must be a dict, got {type(record).__name__}")

    missing = [k for k in REQUIRED_OUTPUT_KEYS if k not in record]
    if missing:
        raise MalformedEvidenceChain(f"missing required keys: {missing}")

    for key in ("targets", "genes", "pathways", "disease_links",
                "mechanistic_chain", "evidence", "limitations"):
        if not isinstance(record[key], list):
            raise MalformedEvidenceChain(
                f"'{key}' must be a list, got {type(record[key]).__name__}"
            )

    for key in ("molecular_plausibility_score", "confidence"):
        value = record[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MalformedEvidenceChain(f"'{key}' must be numeric, got {value!r}")
        if not 0.0 <= float(value) <= 1.0:
            raise MalformedEvidenceChain(f"'{key}' must be in [0,1], got {value!r}")

    # Every evidence item must be attributable and tiered.
    for i, item in enumerate(record["evidence"]):
        if not isinstance(item, dict):
            raise MalformedEvidenceChain(f"evidence[{i}] must be a dict")
        if not item.get("source"):
            raise MalformedEvidenceChain(f"evidence[{i}] has no 'source': {item}")
        tier = item.get("tier")
        if tier not in EvidenceTier.ALL:
            raise MalformedEvidenceChain(
                f"evidence[{i}] tier {tier!r} not in {EvidenceTier.ALL}"
            )

    # Every chain step must be tiered and sourced.
    for i, step in enumerate(record["mechanistic_chain"]):
        if not isinstance(step, dict):
            raise MalformedEvidenceChain(f"mechanistic_chain[{i}] must be a dict")
        for required in ("step", "tier", "source"):
            if not step.get(required):
                raise MalformedEvidenceChain(
                    f"mechanistic_chain[{i}] missing '{required}': {step}"
                )
        if step["tier"] not in EvidenceTier.ALL:
            raise MalformedEvidenceChain(
                f"mechanistic_chain[{i}] tier {step['tier']!r} invalid"
            )

    # A non-zero score must be backed by non-missing evidence.
    if float(record["molecular_plausibility_score"]) > 0:
        tiers = {e.get("tier") for e in record["evidence"]}
        if not tiers & {EvidenceTier.DIRECT, EvidenceTier.INDIRECT}:
            raise MalformedEvidenceChain(
                "non-zero molecular_plausibility_score with no direct/indirect "
                "evidence -- score is not supported by the evidence chain"
            )


# ============================================================================
# AGENT ENTRY POINTS
# ============================================================================

#: Applies to every record. Documented here once rather than restated per drug.
BASELINE_LIMITATIONS = [
    "Open Targets data version is a CURRENT snapshot (26.09). It therefore "
    "includes evidence published after the EviRep 2021-01-01 cutoff. Unlike the "
    "clinical dimension (script 03), this dimension is NOT cutoff-bounded. "
    "Residual temporal optimism is possible even though the two label-encoding "
    "datatypes are excluded. See development_log/ERRORS_AND_BLOCKERS.md B-001.",
    "The direct component re-aggregates allowed datatype scores with max(), "
    "which is NOT Open Targets' official harmonic-sum weighting; the official "
    "per-datatype weights are not exposed by the API.",
    "Pathway membership is Reactome-only (as exposed by Open Targets "
    "Target.pathways). KEGG/WikiPathways are not consulted, so pathway coverage "
    "is incomplete for genes poorly annotated in Reactome.",
    "Shared pathway membership is co-membership, not a directional mechanistic "
    "claim: it does not establish that the drug modulates the disease process.",
    "Pathway overlap is unweighted by pathway size or specificity. A match in a "
    "broad Reactome pathway counts the same as a match in a narrow one, so the "
    "pathway component can be driven by generic signalling/metabolic pathways. "
    "Specificity weighting is recorded as future work in TECHNICAL_DEBT.md TD-007.",
]


def run_agent(
    drug_name: str,
    client: OpenTargetsClient,
    module: DiseaseModule,
    config: Optional[MolecularAgentConfig] = None,
    resolution: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run the molecular agent for ONE drug and return a contract-compliant record.

    `module` is built once by `build_disease_module` and reused across drugs.
    `resolution` may be supplied from a batched `normalize_drug_batch` call to
    avoid a per-drug resolution request.

    Degrades gracefully: on API failure or missing data it returns a valid
    record with empty evidence, confidence reflecting what was unavailable, and
    an explicit limitation. It never fabricates targets, pathways or scores.
    """
    config = config or MolecularAgentConfig()
    limitations: List[str] = list(BASELINE_LIMITATIONS)

    record: Dict[str, Any] = {
        "drug": drug_name,
        "drug_normalized": None,
        "chembl_id": None,
        "disease": config.disease_name,
        "disease_id": config.disease_id,
        "hetionet_disease_id": HETIONET_PD_DISEASE_ID,
        "targets": [],
        "genes": [],
        "pathways": [],
        "disease_links": [],
        "mechanistic_chain": [],
        "molecular_plausibility_score": 0.0,
        "confidence": 0.0,
        "scoring": {},
        "evidence": [],
        "limitations": limitations,
        "provenance": {
            "api": "OpenTargets Platform GraphQL",
            "url": client.url,
            "disease_module_source": module.source,
            "disease_module_genes": len(module.genes),
            "disease_module_pathways": len(module.pathway_ids),
            "disease_module_datatypes": list(module.module_datatypes),
            "direct_component_datatypes": list(config.allowed_datatypes),
            "datatypes_excluded_for_leakage": list(config.excluded_datatypes),
            # recorded only when set, so default runs stay byte-identical to the approved baseline
            **({"pathway_excludes_drug_targets": True} if config.pathway_excludes_drug_targets else {}),
        },
    }

    # --- resolve the drug ---------------------------------------------------
    try:
        if resolution is None:
            resolution = normalize_drug_batch([drug_name], client).get(drug_name)
    except OpenTargetsUnavailable as exc:
        record["limitations"].append(f"Drug resolution failed (API unavailable): {exc}")
        record["evidence"].append(
            {
                "tier": EvidenceTier.MISSING,
                "claim": f"No molecular evidence retrieved for {drug_name}.",
                "source": "OpenTargets Platform GraphQL (unavailable)",
                "identifiers": {},
                "strength": None,
            }
        )
        validate_output(record)
        return record

    resolution = resolution or {}
    chembl_id = resolution.get("chembl_id")
    record["drug_normalized"] = resolution.get("resolved_name")
    record["chembl_id"] = chembl_id
    record["normalization"] = {
        "match_type": resolution.get("match_type", "unresolved"),
        "candidates_considered": resolution.get("candidates", []),
        "note": "A candidate is accepted only on exact normalised name/synonym "
                "equality; Open Targets returns fuzzy neighbours.",
    }

    if not chembl_id:
        record["limitations"].append(
            f"'{drug_name}' could not be matched to a ChEMBL molecule by exact "
            f"name or synonym; no molecular evidence was retrieved. Candidates "
            f"rejected as non-identical: "
            f"{[c.get('name') for c in resolution.get('candidates', [])]}"
        )
        record["evidence"].append(
            {
                "tier": EvidenceTier.MISSING,
                "claim": f"{drug_name} is not resolvable to a ChEMBL molecule; "
                         f"molecular plausibility is unknown, not zero.",
                "source": "OpenTargets mapIds (no exact match)",
                "identifiers": {},
                "strength": None,
            }
        )
        record["confidence"] = 0.0
        validate_output(record)
        return record

    # --- drug -> targets ----------------------------------------------------
    try:
        drug_records = get_drug_mechanisms([chembl_id], client)
        targets = extract_targets(drug_records.get(chembl_id))
        target_details = get_target_details(
            [t["ensembl_id"] for t in targets], client, config
        )
    except OpenTargetsUnavailable as exc:
        record["limitations"].append(f"Target retrieval failed (API unavailable): {exc}")
        record["evidence"].append(
            {
                "tier": EvidenceTier.MISSING,
                "claim": f"No molecular evidence retrieved for {drug_name}.",
                "source": "OpenTargets Platform GraphQL (unavailable)",
                "identifiers": {"chembl": chembl_id},
                "strength": None,
            }
        )
        validate_output(record)
        return record

    record["targets"] = targets
    record["genes"] = [
        {
            "ensembl_id": t["ensembl_id"],
            "gene_symbol": t["gene_symbol"],
            "gene_name": t["gene_name"],
            "source": t["source"],
        }
        for t in targets
    ]

    if not targets:
        record["limitations"].append(
            f"{drug_name} ({chembl_id}) has no mechanism-of-action target "
            f"annotated in Open Targets/ChEMBL. The molecular chain cannot be "
            f"built; the score is 0.0 because evidence is ABSENT, which is not "
            f"the same as evidence of no molecular link."
        )
        record["evidence"].append(
            {
                "tier": EvidenceTier.MISSING,
                "claim": f"{drug_name} has no annotated molecular target.",
                "source": "OpenTargets mechanismsOfAction (empty)",
                "identifiers": {"chembl": chembl_id},
                "strength": None,
            }
        )
        record["confidence"] = compute_confidence(
            True, targets, target_details, [], module
        )["confidence"]
        validate_output(record)
        return record

    # --- build chain, pathways, evidence ------------------------------------
    chain, pathways, evidence = build_mechanistic_chain(
        drug_name, chembl_id, targets, target_details, module, config
    )
    record["mechanistic_chain"] = chain
    record["pathways"] = pathways
    record["evidence"] = evidence

    record["disease_links"] = [
        {
            "gene_symbol": t["gene_symbol"],
            "ensembl_id": t["ensembl_id"],
            **(filtered_disease_link(target_details.get(t["ensembl_id"]), config) or {}),
        }
        for t in targets
        if filtered_disease_link(target_details.get(t["ensembl_id"]), config)
    ]

    # --- score + confidence -------------------------------------------------
    scoring = score_molecular_plausibility(
        targets, target_details, pathways, module, config
    )
    record["scoring"] = scoring
    record["molecular_plausibility_score"] = scoring["molecular_plausibility_score"]

    conf = compute_confidence(True, targets, target_details, pathways, module)
    record["confidence"] = conf["confidence"]
    record["confidence_checks"] = conf["checks"]

    if not record["disease_links"]:
        record["limitations"].append(
            "No target of this drug has a Parkinson's association from the "
            "allowed (non-clinical, non-literature) datatypes. Any score here "
            "rests on pathway co-membership only."
        )
    if not evidence:
        record["evidence"].append(
            {
                "tier": EvidenceTier.MISSING,
                "claim": f"Targets were found for {drug_name} but none produced "
                         f"a disease or pathway link to {config.disease_name}.",
                "source": "OpenTargets (no qualifying link)",
                "identifiers": {"chembl": chembl_id},
                "strength": None,
            }
        )

    validate_output(record)
    return record


def run_agent_batch(
    drug_names: Sequence[str],
    client: Optional[OpenTargetsClient] = None,
    config: Optional[MolecularAgentConfig] = None,
) -> List[Dict[str, Any]]:
    """
    Convenience wrapper: resolve names in one batch, build the module once,
    then score each drug. Order of output matches order of input.
    """
    config = config or MolecularAgentConfig()
    client = client or OpenTargetsClient(config)
    module = build_disease_module(client, config)
    resolutions = normalize_drug_batch(list(drug_names), client)
    return [
        run_agent(name, client, module, config, resolutions.get(name))
        for name in drug_names
    ]
