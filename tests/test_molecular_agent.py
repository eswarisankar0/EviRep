"""
Offline tests for the Molecular / Pathway Evidence Agent.

Run:  ./venv/bin/python -m unittest discover -s tests -v

These tests make NO network calls. The fake transport below returns payloads
shaped exactly like the live Open Targets responses that were probed and
recorded in scripts/molecular_agent.py's docstring.

The fixture *values* are synthetic test data, deliberately chosen so expected
scores are checkable by hand. They are test fixtures only and are never written
to data/ or presented as research results.
"""

import json
import os
import sys
import unittest
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import requests  # noqa: E402

import molecular_agent as ma  # noqa: E402


# ============================================================================
# FAKE TRANSPORT
# ============================================================================


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200,
                 headers: Optional[Dict[str, str]] = None, raw: Optional[str] = None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self._raw = raw

    def json(self):
        if self._raw is not None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    """
    Routes a GraphQL request to a canned response by matching the operation.
    Records every call so tests can assert on request counts (batching/caching).
    """

    def __init__(self, module_genes: Optional[List[Dict]] = None):
        self.calls: List[Dict[str, Any]] = []
        self.fail_with: Optional[Exception] = None
        self.status_queue: List[int] = []
        self.module_genes = module_genes if module_genes is not None else _PD_MODULE_ROWS

    def post(self, url, json=None, timeout=None):  # noqa: A002
        body = json or {}
        query = body.get("query", "")
        variables = body.get("variables", {})
        self.calls.append({"query": query, "variables": variables})

        if self.fail_with is not None:
            raise self.fail_with
        if self.status_queue:
            status = self.status_queue.pop(0)
            if status != 200:
                return FakeResponse({"errors": [{"message": "transient"}]},
                                    status_code=status, headers={"Retry-After": "0"})

        if "mapIds" in query:
            return FakeResponse({"data": _map_ids(variables["terms"])})
        if "drugs(chemblIds" in query:
            return FakeResponse({"data": _drugs(variables["ids"])})
        if "targets(ensemblIds" in query:
            return FakeResponse({"data": _targets(variables["ids"])})
        if "disease(efoId" in query:
            return FakeResponse({"data": _disease(self.module_genes)})
        raise AssertionError(f"unrouted query: {query[:120]}")


# ============================================================================
# SYNTHETIC FIXTURES (shaped like verified live responses)
# ============================================================================

# TESTDRUG targets gene TG1 (PD-associated via genetics) and TG2 (not associated).
# TG1 pathways: P1 (contains PD module gene MG1), P2 (contains nothing)
# TG2 pathways: P3 (contains nothing, but shares top-level term with module)

_MAP_HITS = {
    "Testdrug": [{"id": "CHEMBL_T", "name": "TESTDRUG", "entity": "drug"}],
    # Fuzzy case: no hit is name-identical -> must be rejected (see E-003).
    "Statinex": [
        {"id": "CHEMBL_A", "name": "OTHERSTATIN", "entity": "drug"},
        {"id": "CHEMBL_B", "name": "DIFFERENTSTATIN", "entity": "drug"},
    ],
    # Synonym case: primary name differs, but a synonym matches exactly.
    "Brandname": [{"id": "CHEMBL_S", "name": "GENERICNAME", "entity": "drug"}],
    "Notadrug": [],
    "Targetlessdrug": [{"id": "CHEMBL_NOTGT", "name": "TARGETLESSDRUG", "entity": "drug"}],
}

_DRUG_RECORDS = {
    "CHEMBL_T": {
        "id": "CHEMBL_T", "name": "TESTDRUG", "drugType": "Small molecule",
        "synonyms": [], "tradeNames": [],
        "mechanismsOfAction": {"rows": [
            {
                "mechanismOfAction": "TG1 inhibitor", "actionType": "INHIBITOR",
                "targetName": "Test target 1",
                "references": [{"source": "DailyMed", "ids": ["setid=abc"],
                                "urls": ["http://example.org/abc"]}],
                "targets": [{"id": "ENSG_TG1", "approvedSymbol": "TG1",
                             "approvedName": "test gene 1"},
                            {"id": "ENSG_TG2", "approvedSymbol": "TG2",
                             "approvedName": "test gene 2"}],
            },
            # Duplicate (same gene+mechanism+action) -> must be de-duplicated.
            {
                "mechanismOfAction": "TG1 inhibitor", "actionType": "INHIBITOR",
                "targetName": "Test target 1",
                "references": [{"source": "DailyMed", "ids": ["setid=abc"],
                                "urls": ["http://example.org/abc"]}],
                "targets": [{"id": "ENSG_TG1", "approvedSymbol": "TG1",
                             "approvedName": "test gene 1"}],
            },
        ]},
    },
    "CHEMBL_NOTGT": {
        "id": "CHEMBL_NOTGT", "name": "TARGETLESSDRUG", "drugType": "Small molecule",
        "synonyms": [], "tradeNames": [],
        "mechanismsOfAction": {"rows": []},
    },
    "CHEMBL_A": {"id": "CHEMBL_A", "name": "OTHERSTATIN",
                 "synonyms": [{"label": "foo", "source": "chembl"}],
                 "tradeNames": [], "mechanismsOfAction": {"rows": []}},
    "CHEMBL_B": {"id": "CHEMBL_B", "name": "DIFFERENTSTATIN", "synonyms": [],
                 "tradeNames": [], "mechanismsOfAction": {"rows": []}},
    "CHEMBL_S": {"id": "CHEMBL_S", "name": "GENERICNAME",
                 "synonyms": [{"label": "Brand Name", "source": "chembl"}],
                 "tradeNames": [], "mechanismsOfAction": {"rows": []}},
}

_TARGET_RECORDS = {
    "ENSG_TG1": {
        "id": "ENSG_TG1", "approvedSymbol": "TG1", "approvedName": "test gene 1",
        "pathways": [
            {"pathwayId": "R-P1", "pathway": "Pathway One",
             "topLevelTerm": "Metabolism"},
            {"pathwayId": "R-P2", "pathway": "Pathway Two",
             "topLevelTerm": "Unrelated Area"},
        ],
        "associatedDiseases": {"rows": [{
            "score": 0.9,
            "disease": {"id": "MONDO_0005180", "name": "Parkinson disease"},
            "datatypeScores": [
                {"id": "genetic_association", "score": 0.5},
                {"id": "animal_model", "score": 0.3},
                {"id": "clinical", "score": 0.99},      # excluded (leakage)
                {"id": "literature", "score": 0.95},    # excluded (leakage)
            ],
        }]},
    },
    "ENSG_TG2": {
        "id": "ENSG_TG2", "approvedSymbol": "TG2", "approvedName": "test gene 2",
        "pathways": [
            {"pathwayId": "R-P3", "pathway": "Pathway Three",
             "topLevelTerm": "Metabolism"},  # shares top-level term only
        ],
        # Association rests ONLY on excluded datatypes -> must contribute 0.
        "associatedDiseases": {"rows": [{
            "score": 0.8,
            "disease": {"id": "MONDO_0005180", "name": "Parkinson disease"},
            "datatypeScores": [
                {"id": "clinical", "score": 0.97},
                {"id": "literature", "score": 0.88},
            ],
        }]},
    },
    "ENSG_MG1": {
        "id": "ENSG_MG1", "approvedSymbol": "MG1", "approvedName": "module gene 1",
        "pathways": [
            {"pathwayId": "R-P1", "pathway": "Pathway One",
             "topLevelTerm": "Metabolism"},
        ],
        "associatedDiseases": {"rows": []},
    },
    "ENSG_MG2": {
        "id": "ENSG_MG2", "approvedSymbol": "MG2", "approvedName": "module gene 2",
        "pathways": [
            {"pathwayId": "R-P9", "pathway": "Pathway Nine",
             "topLevelTerm": "Metabolism"},
        ],
        "associatedDiseases": {"rows": []},
    },
}

_PD_MODULE_ROWS = [
    # Qualifies: genetic_association above threshold.
    {"score": 0.9, "target": {"id": "ENSG_MG1", "approvedSymbol": "MG1"},
     "datatypeScores": [{"id": "genetic_association", "score": 0.8}]},
    # Qualifies.
    {"score": 0.7, "target": {"id": "ENSG_MG2", "approvedSymbol": "MG2"},
     "datatypeScores": [{"id": "animal_model", "score": 0.4}]},
    # MUST be excluded: only leaky datatypes.
    {"score": 0.95, "target": {"id": "ENSG_LEAK", "approvedSymbol": "LEAKGENE"},
     "datatypeScores": [{"id": "clinical", "score": 0.99},
                        {"id": "literature", "score": 0.97}]},
    # MUST be excluded: below pd_module_min_score.
    {"score": 0.2, "target": {"id": "ENSG_WEAK", "approvedSymbol": "WEAKGENE"},
     "datatypeScores": [{"id": "genetic_association", "score": 0.01}]},
]


def _map_ids(terms):
    return {"mapIds": {"mappings": [
        {"term": t, "hits": _MAP_HITS.get(t, [])} for t in terms
    ]}}


def _drugs(ids):
    return {"drugs": [_DRUG_RECORDS[i] for i in ids if i in _DRUG_RECORDS]}


def _targets(ids):
    return {"targets": [_TARGET_RECORDS[i] for i in ids if i in _TARGET_RECORDS]}


def _disease(rows):
    return {"disease": {
        "id": "MONDO_0005180", "name": "Parkinson disease",
        "associatedTargets": {"count": 8994, "rows": rows},
    }}


def make_client(session=None, **cfg_overrides):
    cfg = ma.MolecularAgentConfig(use_cache=False, min_request_interval_s=0.0,
                                  backoff_base_s=0.0, **cfg_overrides)
    return ma.OpenTargetsClient(cfg, session=session or FakeSession()), cfg


# ============================================================================
# 1. IMPORTS / SYNTAX
# ============================================================================


class TestImportsAndSyntax(unittest.TestCase):
    def test_module_imports_and_exposes_api(self):
        for name in ("run_agent", "run_agent_batch", "build_disease_module",
                     "normalize_drug_batch", "validate_output",
                     "OpenTargetsClient", "MolecularAgentConfig"):
            self.assertTrue(hasattr(ma, name), f"missing {name}")

    def test_all_project_scripts_parse(self):
        import ast
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for fname in sorted(os.listdir(os.path.join(root, "scripts"))):
            if fname.endswith(".py"):
                path = os.path.join(root, "scripts", fname)
                with open(path, encoding="utf-8") as fh:
                    ast.parse(fh.read(), filename=fname)

    def test_pd_identifier_is_the_verified_one(self):
        # Guard against someone "correcting" this to a remembered EFO id.
        self.assertEqual(ma.PD_DISEASE_EFO_ID, "MONDO_0005180")


# ============================================================================
# 2. CONFIG
# ============================================================================


class TestConfig(unittest.TestCase):
    def test_weights_must_sum_to_one(self):
        with self.assertRaises(ValueError):
            ma.MolecularAgentConfig(weight_direct=0.9, weight_pathway=0.9)

    def test_leaky_datatypes_excluded_by_default(self):
        cfg = ma.MolecularAgentConfig()
        self.assertIn("clinical", cfg.excluded_datatypes)
        self.assertIn("literature", cfg.excluded_datatypes)
        self.assertNotIn("clinical", cfg.allowed_datatypes)
        self.assertNotIn("literature", cfg.allowed_datatypes)

    def test_datatype_cannot_be_both_allowed_and_excluded(self):
        with self.assertRaises(ValueError):
            ma.MolecularAgentConfig(allowed_datatypes=("clinical",),
                                    excluded_datatypes=("clinical",))


# ============================================================================
# 3-4. DRUG NORMALIZATION
# ============================================================================


class TestNormalization(unittest.TestCase):
    def test_exact_name_match_resolves(self):
        client, _ = make_client()
        out = ma.normalize_drug_batch(["Testdrug"], client)
        self.assertEqual(out["Testdrug"]["chembl_id"], "CHEMBL_T")
        self.assertEqual(out["Testdrug"]["match_type"], "exact_name")

    def test_normalize_rejects_fuzzy_nonidentical_match(self):
        """E-003: querying one drug returns ranked neighbours; taking hits[0]
        would attribute another molecule's targets to this drug."""
        client, _ = make_client()
        out = ma.normalize_drug_batch(["Statinex"], client)
        self.assertIsNone(out["Statinex"]["chembl_id"])
        self.assertEqual(out["Statinex"]["match_type"], "unresolved")
        # The rejected candidates are still reported, for auditability.
        self.assertEqual(
            [c["name"] for c in out["Statinex"]["candidates"]],
            ["OTHERSTATIN", "DIFFERENTSTATIN"],
        )

    def test_exact_synonym_match_resolves(self):
        client, _ = make_client()
        out = ma.normalize_drug_batch(["Brandname"], client)
        self.assertEqual(out["Brandname"]["chembl_id"], "CHEMBL_S")
        self.assertEqual(out["Brandname"]["match_type"], "exact_synonym")

    def test_alias_labels_handles_real_object_shape(self):
        """E-005: Drug.synonyms/tradeNames are [{label, source}] objects, not
        strings. Treating them as strings silently matched nothing."""
        labels = ma._alias_labels({
            "synonyms": [{"label": "Ropinirol", "source": "chembl"}],
            "tradeNames": [{"label": "Ropitor", "source": "chembl"}],
        })
        self.assertEqual(sorted(labels), ["Ropinirol", "Ropitor"])

    def test_alias_labels_tolerates_plain_strings(self):
        self.assertEqual(ma._alias_labels({"synonyms": ["Foo"]}), ["Foo"])

    def test_alias_labels_empty_when_absent(self):
        self.assertEqual(ma._alias_labels({}), [])

    def test_drug_detail_query_subselects_label_objects(self):
        """A missing sub-selection on these fields is an HTTP 400 (E-005)."""
        self.assertIn("synonyms{ label source }", ma._DRUG_DETAIL_QUERY)
        self.assertIn("tradeNames{ label source }", ma._DRUG_DETAIL_QUERY)

    def test_no_hits_is_unresolved_not_guessed(self):
        client, _ = make_client()
        out = ma.normalize_drug_batch(["Notadrug"], client)
        self.assertIsNone(out["Notadrug"]["chembl_id"])

    def test_batch_resolution_uses_one_request(self):
        session = FakeSession()
        client, _ = make_client(session)
        ma.normalize_drug_batch(["Testdrug", "Notadrug"], client)
        self.assertEqual(len(session.calls), 1, "names must be resolved in one batch")


# ============================================================================
# 5. TARGET EXTRACTION
# ============================================================================


class TestTargetExtraction(unittest.TestCase):
    def test_extracts_genes_with_provenance(self):
        targets = ma.extract_targets(_DRUG_RECORDS["CHEMBL_T"])
        symbols = sorted(t["gene_symbol"] for t in targets)
        self.assertEqual(symbols, ["TG1", "TG2"])
        for t in targets:
            self.assertTrue(t["ensembl_id"])
            self.assertEqual(t["source"], "ChEMBL via OpenTargets")
            self.assertTrue(t["references"], "drug->target edge needs references")
            self.assertEqual(t["references"][0]["source"], "DailyMed")

    def test_duplicate_mechanism_rows_deduplicated(self):
        targets = ma.extract_targets(_DRUG_RECORDS["CHEMBL_T"])
        keys = [(t["ensembl_id"], t["mechanism_of_action"], t["action_type"])
                for t in targets]
        self.assertEqual(len(keys), len(set(keys)))

    def test_extraction_is_deterministic(self):
        a = ma.extract_targets(_DRUG_RECORDS["CHEMBL_T"])
        b = ma.extract_targets(_DRUG_RECORDS["CHEMBL_T"])
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_empty_and_none_drug_records(self):
        self.assertEqual(ma.extract_targets(None), [])
        self.assertEqual(ma.extract_targets(_DRUG_RECORDS["CHEMBL_NOTGT"]), [])


# ============================================================================
# 6. PATHWAY EXTRACTION / DISEASE MODULE
# ============================================================================


class TestDiseaseModule(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        self.client, self.cfg = make_client(self.session)
        self.module = ma.build_disease_module(self.client, self.cfg)

    def test_module_keeps_only_allowed_datatype_genes(self):
        self.assertIn("ENSG_MG1", self.module.genes)
        self.assertIn("ENSG_MG2", self.module.genes)
        self.assertNotIn("ENSG_LEAK", self.module.genes,
                         "gene supported only by clinical/literature must be dropped")

    def test_module_applies_min_score_threshold(self):
        self.assertNotIn("ENSG_WEAK", self.module.genes)

    def test_module_collects_reactome_pathways(self):
        self.assertIn("R-P1", self.module.pathway_ids)
        self.assertEqual(self.module.pathway_to_genes["R-P1"], {"ENSG_MG1"})
        self.assertEqual(self.module.pathway_names["R-P1"], "Pathway One")

    def test_module_collects_top_level_terms(self):
        self.assertIn("Metabolism", self.module.top_level_terms)

    def test_affected_pathway_alone_cannot_create_module_gene(self):
        """Anti-circularity: a gene whose only PD evidence is `affected_pathway`
        (itself pathway-derived) must not enter the module, or Reactome overlap
        would count the same annotation twice."""
        rows = [{"score": 0.5,
                 "target": {"id": "ENSG_PWONLY", "approvedSymbol": "PWONLY"},
                 "datatypeScores": [{"id": "affected_pathway", "score": 0.9}]}]
        client, cfg = make_client(FakeSession(module_genes=rows))
        module = ma.build_disease_module(client, cfg)
        self.assertNotIn("ENSG_PWONLY", module.genes)

    def test_affected_pathway_still_allowed_for_direct_component(self):
        cfg = ma.MolecularAgentConfig()
        self.assertIn("affected_pathway", cfg.allowed_datatypes)
        self.assertNotIn("affected_pathway", cfg.module_datatypes)

    def test_module_datatypes_cannot_include_leaky_types(self):
        with self.assertRaises(ValueError):
            ma.MolecularAgentConfig(module_datatypes=("clinical",))

    def test_module_records_its_datatypes_as_provenance(self):
        self.assertEqual(tuple(self.module.module_datatypes),
                         self.cfg.module_datatypes)

    def test_module_records_total_count(self):
        self.assertEqual(self.module.total_associated_targets, 8994)


# ============================================================================
# 7. LEAKAGE CONTROL ON DISEASE LINKS
# ============================================================================


class TestLeakageControl(unittest.TestCase):
    def test_excluded_datatypes_do_not_contribute(self):
        _, cfg = make_client()
        link = ma.filtered_disease_link(_TARGET_RECORDS["ENSG_TG1"], cfg)
        # max over allowed {genetic_association 0.5, animal_model 0.3} = 0.5,
        # NOT the clinical 0.99 / literature 0.95 values.
        self.assertAlmostEqual(link["score_allowed_datatypes"], 0.5)
        self.assertEqual(sorted(link["datatype_scores_used"]),
                         ["animal_model", "genetic_association"])
        self.assertEqual(sorted(link["datatype_scores_excluded_for_leakage"]),
                         ["clinical", "literature"])

    def test_opentargets_composite_score_is_not_used(self):
        _, cfg = make_client()
        link = ma.filtered_disease_link(_TARGET_RECORDS["ENSG_TG1"], cfg)
        self.assertEqual(link["opentargets_overall_score_not_used"], 0.9)
        self.assertNotAlmostEqual(link["score_allowed_datatypes"], 0.9)

    def test_target_with_only_leaky_evidence_scores_zero(self):
        _, cfg = make_client()
        link = ma.filtered_disease_link(_TARGET_RECORDS["ENSG_TG2"], cfg)
        self.assertEqual(link["score_allowed_datatypes"], 0.0)

    def test_no_association_row_returns_none(self):
        _, cfg = make_client()
        self.assertIsNone(ma.filtered_disease_link(_TARGET_RECORDS["ENSG_MG1"], cfg))
        self.assertIsNone(ma.filtered_disease_link(None, cfg))


# ============================================================================
# 8. SCORING
# ============================================================================


class TestScoring(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        self.client, self.cfg = make_client(self.session)
        self.module = ma.build_disease_module(self.client, self.cfg)
        self.record = ma.run_agent("Testdrug", self.client, self.module, self.cfg)

    def test_score_matches_hand_computed_value(self):
        """
        direct  = max(TG1 allowed=0.5, TG2 allowed=0.0) = 0.5
        pathways of the drug's targets = {R-P1, R-P2, R-P3} -> 3 distinct
        in PD module: R-P1 only (contains MG1)             -> 1
        pathway = 1/3
        score   = 0.6*0.5 + 0.4*(1/3) = 0.30 + 0.133333 = 0.433333
        """
        expected = 0.6 * 0.5 + 0.4 * (1.0 / 3.0)
        self.assertAlmostEqual(self.record["molecular_plausibility_score"],
                               round(expected, 6), places=6)
        comp = self.record["scoring"]["components"]
        self.assertAlmostEqual(comp["direct_target_disease"], 0.5)
        self.assertAlmostEqual(comp["pathway_overlap"], 1.0 / 3.0, places=6)

    def test_score_is_explainable(self):
        self.assertIn("explanation", self.record["scoring"])
        self.assertIn("0.6", self.record["scoring"]["explanation"])
        self.assertIn("weights", self.record["scoring"])

    def test_inferred_shared_toplevel_term_contributes_zero(self):
        """R-P3 shares only the 'Metabolism' top-level term; it must not count
        toward pathway overlap, or broad Reactome areas would manufacture
        signal."""
        p3 = [p for p in self.record["pathways"] if p["pathway_id"] == "R-P3"][0]
        self.assertEqual(p3["tier"], ma.EvidenceTier.INFERRED)
        self.assertFalse(p3["in_disease_module"])
        self.assertEqual(
            self.record["scoring"]["detail"]["n_target_pathways_in_disease_module"], 1)

    def test_score_within_unit_interval(self):
        self.assertGreaterEqual(self.record["molecular_plausibility_score"], 0.0)
        self.assertLessEqual(self.record["molecular_plausibility_score"], 1.0)

    def test_weights_are_configurable_and_change_the_score(self):
        cfg = ma.MolecularAgentConfig(use_cache=False, min_request_interval_s=0.0,
                                      weight_direct=1.0, weight_pathway=0.0)
        client = ma.OpenTargetsClient(cfg, session=FakeSession())
        module = ma.build_disease_module(client, cfg)
        rec = ma.run_agent("Testdrug", client, module, cfg)
        self.assertAlmostEqual(rec["molecular_plausibility_score"], 0.5, places=6)


# ============================================================================
# 9. EVIDENCE / PROVENANCE STRUCTURE
# ============================================================================


class TestEvidenceStructure(unittest.TestCase):
    def setUp(self):
        self.client, self.cfg = make_client()
        self.module = ma.build_disease_module(self.client, self.cfg)
        self.record = ma.run_agent("Testdrug", self.client, self.module, self.cfg)

    def test_output_contract_keys_present(self):
        for key in ma.REQUIRED_OUTPUT_KEYS:
            self.assertIn(key, self.record)

    def test_every_evidence_item_has_source_and_tier(self):
        self.assertTrue(self.record["evidence"])
        for item in self.record["evidence"]:
            self.assertTrue(item["source"])
            self.assertIn(item["tier"], ma.EvidenceTier.ALL)

    def test_evidence_tiers_are_distinguished(self):
        tiers = {e["tier"] for e in self.record["evidence"]}
        self.assertIn(ma.EvidenceTier.DIRECT, tiers)
        self.assertIn(ma.EvidenceTier.INDIRECT, tiers)
        self.assertIn(ma.EvidenceTier.INFERRED, tiers)

    def test_mechanistic_chain_covers_full_path(self):
        steps = {c["step"] for c in self.record["mechanistic_chain"]}
        self.assertEqual(steps, {"drug_to_target", "gene_to_disease",
                                 "pathway_to_disease"})

    def test_chain_steps_carry_source_and_tier(self):
        for step in self.record["mechanistic_chain"]:
            self.assertTrue(step["source"])
            self.assertIn(step["tier"], ma.EvidenceTier.ALL)

    def test_drug_target_edge_carries_references(self):
        edges = [c for c in self.record["mechanistic_chain"]
                 if c["step"] == "drug_to_target"]
        self.assertTrue(edges)
        for e in edges:
            self.assertTrue(e["references"])

    def test_limitations_are_always_reported(self):
        self.assertTrue(self.record["limitations"])
        joined = " ".join(self.record["limitations"])
        self.assertIn("2021-01-01", joined, "temporal caveat must be stated")
        self.assertIn("Reactome", joined)

    def test_identifiers_present_on_evidence(self):
        for item in self.record["evidence"]:
            self.assertIn("identifiers", item)


# ============================================================================
# 10. MISSING-DATA BEHAVIOUR
# ============================================================================


class TestMissingData(unittest.TestCase):
    def setUp(self):
        self.client, self.cfg = make_client()
        self.module = ma.build_disease_module(self.client, self.cfg)

    def test_unresolved_drug_yields_zero_score_and_zero_confidence(self):
        rec = ma.run_agent("Statinex", self.client, self.module, self.cfg)
        self.assertEqual(rec["molecular_plausibility_score"], 0.0)
        self.assertEqual(rec["confidence"], 0.0)
        self.assertEqual(rec["chembl_id"], None)
        self.assertTrue(any(e["tier"] == ma.EvidenceTier.MISSING
                            for e in rec["evidence"]))
        ma.validate_output(rec)

    def test_unresolved_drug_records_rejected_candidates(self):
        rec = ma.run_agent("Statinex", self.client, self.module, self.cfg)
        joined = " ".join(rec["limitations"])
        self.assertIn("OTHERSTATIN", joined)

    def test_drug_with_no_targets_distinguishes_absent_from_zero(self):
        rec = ma.run_agent("Targetlessdrug", self.client, self.module, self.cfg)
        self.assertEqual(rec["molecular_plausibility_score"], 0.0)
        # Confidence is non-zero (drug resolved, module available) but < 1.
        self.assertGreater(rec["confidence"], 0.0)
        self.assertLess(rec["confidence"], 1.0)
        joined = " ".join(rec["limitations"])
        self.assertIn("not the same as evidence of no molecular link", joined)
        ma.validate_output(rec)

    def test_empty_disease_module_is_handled(self):
        session = FakeSession(module_genes=[])
        client, cfg = make_client(session)
        module = ma.build_disease_module(client, cfg)
        self.assertEqual(module.genes, {})
        rec = ma.run_agent("Testdrug", client, module, cfg)
        # No module -> no pathway overlap; direct evidence still stands.
        self.assertAlmostEqual(rec["scoring"]["components"]["pathway_overlap"], 0.0)
        self.assertLess(rec["confidence"], 1.0)
        ma.validate_output(rec)


# ============================================================================
# 11. API FAILURE BEHAVIOUR
# ============================================================================


class TestApiFailure(unittest.TestCase):
    def test_connection_error_raises_unavailable_after_retries(self):
        session = FakeSession()
        session.fail_with = requests.ConnectionError("boom")
        client, _ = make_client(session)
        with self.assertRaises(ma.OpenTargetsUnavailable):
            client.query("{ mapIds }", {})
        self.assertEqual(len(session.calls), client.config.max_retries + 1)

    def test_retries_then_succeeds_on_429(self):
        session = FakeSession()
        session.status_queue = [429, 500]  # two transient failures, then OK
        client, _ = make_client(session)
        out = client.query("query($terms:[String!]!){ mapIds }", {"terms": ["Testdrug"]})
        self.assertIn("mapIds", out)
        self.assertEqual(len(session.calls), 3)

    def test_graphql_error_is_not_retried(self):
        class ErrSession(FakeSession):
            def post(self, url, json=None, timeout=None):  # noqa: A002
                self.calls.append({})
                return FakeResponse({"errors": [{"message": "bad field"}]})
        session = ErrSession()
        client, _ = make_client(session)
        with self.assertRaises(ma.OpenTargetsUnavailable):
            client.query("{ bad }", {})
        self.assertEqual(len(session.calls), 1, "query defects must not be retried")

    def test_agent_degrades_gracefully_when_api_unavailable(self):
        """Agent must return a VALID empty-evidence record, not fabricate data."""
        good_session = FakeSession()
        client, cfg = make_client(good_session)
        module = ma.build_disease_module(client, cfg)

        dead = FakeSession()
        dead.fail_with = requests.ConnectionError("down")
        dead_client, _ = make_client(dead)

        rec = ma.run_agent("Testdrug", dead_client, module, cfg)
        self.assertEqual(rec["molecular_plausibility_score"], 0.0)
        self.assertEqual(rec["targets"], [])
        self.assertTrue(any("unavailable" in l.lower() for l in rec["limitations"]))
        ma.validate_output(rec)

    def test_invalid_json_is_retried_then_fails(self):
        class BadJson(FakeSession):
            def post(self, url, json=None, timeout=None):  # noqa: A002
                self.calls.append({})
                return FakeResponse(None, raw="<html>502</html>")
        session = BadJson()
        client, _ = make_client(session)
        with self.assertRaises(ma.OpenTargetsUnavailable):
            client.query("{ x }", {})
        self.assertEqual(len(session.calls), client.config.max_retries + 1)


# ============================================================================
# 12. SCHEMA VALIDATION FAILS LOUDLY
# ============================================================================


class TestValidation(unittest.TestCase):
    def _valid(self):
        return {
            "drug": "X", "disease": "Parkinson's disease", "targets": [],
            "genes": [], "pathways": [], "disease_links": [],
            "mechanistic_chain": [], "molecular_plausibility_score": 0.0,
            "confidence": 0.0, "evidence": [], "limitations": [],
        }

    def test_valid_record_passes(self):
        ma.validate_output(self._valid())

    def test_missing_key_rejected(self):
        rec = self._valid()
        del rec["pathways"]
        with self.assertRaises(ma.MalformedEvidenceChain):
            ma.validate_output(rec)

    def test_out_of_range_score_rejected(self):
        for bad in (1.5, -0.1):
            rec = self._valid()
            rec["molecular_plausibility_score"] = bad
            with self.assertRaises(ma.MalformedEvidenceChain):
                ma.validate_output(rec)

    def test_non_numeric_score_rejected(self):
        rec = self._valid()
        rec["confidence"] = "high"
        with self.assertRaises(ma.MalformedEvidenceChain):
            ma.validate_output(rec)

    def test_evidence_without_source_rejected(self):
        rec = self._valid()
        rec["evidence"] = [{"tier": ma.EvidenceTier.DIRECT, "claim": "c"}]
        with self.assertRaises(ma.MalformedEvidenceChain):
            ma.validate_output(rec)

    def test_evidence_with_bad_tier_rejected(self):
        rec = self._valid()
        rec["evidence"] = [{"tier": "very_strong", "claim": "c", "source": "s"}]
        with self.assertRaises(ma.MalformedEvidenceChain):
            ma.validate_output(rec)

    def test_chain_step_without_source_rejected(self):
        rec = self._valid()
        rec["mechanistic_chain"] = [{"step": "drug_to_target",
                                     "tier": ma.EvidenceTier.DIRECT}]
        with self.assertRaises(ma.MalformedEvidenceChain):
            ma.validate_output(rec)

    def test_unsupported_nonzero_score_rejected(self):
        """A score must be backed by direct/indirect evidence."""
        rec = self._valid()
        rec["molecular_plausibility_score"] = 0.7
        rec["evidence"] = [{"tier": ma.EvidenceTier.MISSING, "claim": "none",
                            "source": "s"}]
        with self.assertRaises(ma.MalformedEvidenceChain):
            ma.validate_output(rec)

    def test_list_field_must_be_list(self):
        rec = self._valid()
        rec["targets"] = {"not": "a list"}
        with self.assertRaises(ma.MalformedEvidenceChain):
            ma.validate_output(rec)


# ============================================================================
# 13. DETERMINISM / REPRODUCIBILITY
# ============================================================================


class TestDeterminism(unittest.TestCase):
    def test_same_input_produces_identical_output(self):
        def run():
            client, cfg = make_client()
            module = ma.build_disease_module(client, cfg)
            return ma.run_agent("Testdrug", client, module, cfg)
        a, b = run(), run()
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_batch_order_matches_input_order(self):
        cfg = ma.MolecularAgentConfig(use_cache=False, min_request_interval_s=0.0)
        client = ma.OpenTargetsClient(cfg, session=FakeSession())
        names = ["Testdrug", "Notadrug", "Targetlessdrug"]
        out = ma.run_agent_batch(names, client, cfg)
        self.assertEqual([r["drug"] for r in out], names)

    def test_pathways_and_chain_sorted_stably(self):
        client, cfg = make_client()
        module = ma.build_disease_module(client, cfg)
        rec = ma.run_agent("Testdrug", client, module, cfg)
        pids = [p["pathway_id"] for p in rec["pathways"]]
        self.assertEqual(pids, sorted(pids))


# ============================================================================
# 14. CACHING / REQUEST ECONOMY
# ============================================================================


class TestCaching(unittest.TestCase):
    def test_cache_prevents_repeat_network_calls(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cfg = ma.MolecularAgentConfig(use_cache=True, cache_dir=tmp,
                                          min_request_interval_s=0.0)
            session = FakeSession()
            client = ma.OpenTargetsClient(cfg, session=session)
            q = "query($terms:[String!]!){ mapIds }"
            client.query(q, {"terms": ["Testdrug"]})
            self.assertEqual(len(session.calls), 1)
            client.query(q, {"terms": ["Testdrug"]})
            self.assertEqual(len(session.calls), 1, "second call must hit cache")
            self.assertEqual(client.stats["cache_hits"], 1)

    def test_targets_are_batched_into_one_request(self):
        session = FakeSession()
        client, cfg = make_client(session)
        before = len(session.calls)
        ma.get_target_details(["ENSG_TG1", "ENSG_TG2", "ENSG_MG1"], client, cfg)
        self.assertEqual(len(session.calls) - before, 1)

    def test_cache_key_is_variable_order_independent(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cfg = ma.MolecularAgentConfig(use_cache=True, cache_dir=tmp,
                                          min_request_interval_s=0.0)
            client = ma.OpenTargetsClient(cfg, session=FakeSession())
            p1 = client._cache_path("q", {"a": 1, "b": 2})
            p2 = client._cache_path("q", {"b": 2, "a": 1})
            self.assertEqual(p1, p2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
