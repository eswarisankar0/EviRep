"""
Offline tests for scripts/conflict_context_agent.py (architecture 10d).

Synthetic claims exercise every classification; a temp-root run checks the
end-to-end contract with a socket guard; persisted-output checks pin the real
findings and the traceability of every curated identifier to CASE_STUDIES.md.
"""

import importlib.util
import json
import pathlib
import os
import re
import shutil
import socket
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("cca", os.path.join(ROOT, "scripts", "conflict_context_agent.py"))
cca = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cca)


def claim(cid, direction, src=None, **kw):
    base = {"claim_id": cid, "compound": "DrugX", "source_id": src or cid, "direction": direction,
            "domain": "efficacy", "endpoint_domain": "tremor", "endpoint_measure": "tremor amplitude",
            "population": "PD", "design": "rct", "dose": "40 mg", "intervention_scope": "drugx",
            "source_date": "2015"}
    base.update(kw)
    c, why = cca.normalise_claim(base)
    assert c, why
    return c


class TestNormalise(unittest.TestCase):
    def test_rejects_invalid_claims(self):
        self.assertEqual(cca.normalise_claim({"claim_id": "a"})[1], "missing compound")
        bad = {"claim_id": "a", "compound": "X", "source_id": "s", "direction": "LIKELY", "domain": "efficacy"}
        self.assertIn("invalid direction", cca.normalise_claim(bad)[1])
        bad.update(direction="SUPPORTS", domain="vibes")
        self.assertIn("invalid domain", cca.normalise_claim(bad)[1])
        self.assertIsNotNone(cca.normalise_claim("junk")[1])

    def test_temporal_from_date(self):
        self.assertEqual(claim("a", "SUPPORTS", source_date="2020-12-31")["temporal"], "PRE_CUTOFF")
        self.assertEqual(claim("a", "SUPPORTS", source_date="2021")["temporal"], "POST_CUTOFF")
        self.assertEqual(claim("a", "SUPPORTS", source_date=None)["temporal"], "UNKNOWN")


class TestCompare(unittest.TestCase):
    def test_direct_contradiction_only_when_nothing_differs(self):
        r = cca.compare(claim("a", "SUPPORTS"), claim("b", "NULL_RESULT"))
        self.assertEqual(r["classification"], "DIRECT_CONTRADICTION")
        self.assertEqual(r["side_a"]["source_id"], "a")
        self.assertEqual(r["side_b"]["source_id"], "b")

    def test_context_difference_lists_axes(self):
        r = cca.compare(claim("a", "SUPPORTS"), claim("b", "NULL_RESULT", population="PDD", dose="10 mg"))
        self.assertEqual(r["classification"], "CONTEXT_DIFFERENCE")
        self.assertEqual(r["differing_axes"], ["population", "dose"])

    def test_same_sign_effects_are_a_significance_disagreement(self):
        a = claim("a", "SUPPORTS", effect={"measure": "MD", "estimate": -1.07})
        b = claim("b", "NULL_RESULT", effect={"measure": "MD", "estimate": -1.04})
        self.assertEqual(cca.compare(a, b)["classification"], "STATISTICAL_DISAGREEMENT")
        b["effect"]["estimate"] = 0.5                     # opposite sign: no longer only significance
        self.assertNotEqual(cca.compare(a, b)["classification"], "STATISTICAL_DISAGREEMENT")

    def test_cross_domain_is_tension_not_contradiction(self):
        r = cca.compare(claim("a", "SUPPORTS"), claim("b", "OPPOSES", domain="safety"))
        self.assertEqual(r["classification"], "CROSS_DOMAIN_TENSION")
        self.assertIsNone(cca.compare(claim("a", "NULL_RESULT"), claim("b", "OPPOSES", domain="safety")))

    def test_different_outcomes_are_non_comparable(self):
        r = cca.compare(claim("a", "SUPPORTS"), claim("b", "NULL_RESULT", endpoint_domain="falls"))
        self.assertEqual(r["classification"], "NON_COMPARABLE")

    def test_missing_context_is_uncertain_not_contradiction(self):
        r = cca.compare(claim("a", "SUPPORTS"), claim("b", "NULL_RESULT", population=None, dose=None))
        self.assertEqual(r["classification"], "UNCERTAIN_COMPARABILITY")
        self.assertEqual(r["differing_axes"], ["population", "dose"])

    def test_non_directional_and_same_source_pairs_are_not_compared(self):
        self.assertIsNone(cca.compare(claim("a", "SUPPORTS"), claim("b", "NEUTRAL")))
        self.assertIsNone(cca.compare(claim("a", "SUPPORTS"), claim("b", "UNCLEAR")))
        self.assertIsNone(cca.compare(claim("a", "SUPPORTS", src="S"), claim("b", "NULL_RESULT", src="S")))
        self.assertIsNone(cca.compare(claim("a", "SUPPORTS"), claim("b", "SUPPORTS")))

    def test_flags(self):
        a = claim("a", "SUPPORTS", overlap_group="g", evidence_level="meta_analysis", source_date="2024")
        b = claim("b", "NULL_RESULT", overlap_group="g", evidence_level="open_label")
        self.assertEqual(cca.compare(a, b)["flags"],
                         ["non_independent_sources", "quality_asymmetry", "uses_post_cutoff_evidence"])


class TestAuditRegressions(unittest.TestCase):
    """Sprint 2026-10-19 audit of 10d."""

    def test_sources_that_are_never_comparable_are_not_reported_as_agreement(self):
        r = cca.assess_compound("X", [claim("a", "OPPOSES", domain="safety", endpoint_domain="falls"),
                                      claim("b", "NULL_RESULT", domain="mechanism", endpoint_domain="target")], True, {})
        self.assertEqual(r["status"], "NO_COMPARABLE_PAIR")
        r = cca.assess_compound("X", [claim("a", "SUPPORTS", endpoint_domain="cognition"),
                                      claim("b", "NULL_RESULT", endpoint_domain="falls")], True, {})
        self.assertEqual(r["status"], "NO_COMPARABLE_PAIR")
        r = cca.assess_compound("X", [claim("a", "SUPPORTS", domain="efficacy", endpoint_domain="approved_indication"),
                                      claim("b", "SUPPORTS", domain="mechanism", endpoint_domain="target")], True, {})
        self.assertEqual(r["status"], "NO_DISAGREEMENT_DETECTED")       # both point the same way across domains

    def test_ratio_measures_are_compared_against_one(self):
        a = claim("a", "SUPPORTS", effect={"measure": "RR", "estimate": 0.7})
        b = claim("b", "NULL_RESULT", effect={"measure": "RR", "estimate": 1.3})
        self.assertNotEqual(cca.compare(a, b)["classification"], "STATISTICAL_DISAGREEMENT")
        c = claim("c", "NULL_RESULT", effect={"measure": "RR", "estimate": 0.9})
        self.assertEqual(cca.compare(a, c)["classification"], "STATISTICAL_DISAGREEMENT")

    def test_missing_curated_file_reports_a_relative_path(self):
        tmp = tempfile.mkdtemp()
        try:
            claims, rejected = cca.load_curated(os.path.join(tmp, cca.CURATED), root=tmp)
            self.assertEqual(rejected[0]["source"], cca.CURATED)
        finally:
            shutil.rmtree(tmp)

    def test_duplicate_claim_ids_are_rejected(self):
        tmp = tempfile.mkdtemp()
        try:
            raw = {"claim_id": "d1", "compound": "X", "source_id": "s", "direction": "SUPPORTS", "domain": "efficacy"}
            os.makedirs(os.path.join(tmp, "data"))
            with open(os.path.join(tmp, cca.CURATED), "w") as fh:
                json.dump({"claims": [raw, dict(raw, source_id="t")]}, fh)
            claims, rejected = cca.load_curated(os.path.join(tmp, cca.CURATED), root=tmp)
            self.assertEqual(len(claims), 1)
            self.assertEqual(rejected, [{"claim": "d1", "reason": "duplicate claim_id"}])
        finally:
            shutil.rmtree(tmp)


class TestCompoundStatus(unittest.TestCase):
    def test_statuses(self):
        cov = {}
        self.assertEqual(cca.assess_compound("X", [], True, cov)["status"], "NO_EVIDENCE")
        self.assertEqual(cca.assess_compound("X", [claim("a", "NEUTRAL")], True, cov)["status"], "INSUFFICIENT")
        self.assertEqual(cca.assess_compound("X", [claim("a", "SUPPORTS")], True, cov)["status"], "INSUFFICIENT")
        two = [claim("a", "SUPPORTS"), claim("b", "SUPPORTS")]
        self.assertEqual(cca.assess_compound("X", two, True, cov)["status"], "NO_DISAGREEMENT_DETECTED")
        mixed = [claim("a", "SUPPORTS"), claim("b", "NULL_RESULT", population="PDD"),
                 claim("c", "OPPOSES", domain="safety")]
        r = cca.assess_compound("X", mixed, True, cov)
        self.assertEqual(r["status"], "CONTEXT_DIFFERENCE")           # priority over tension
        self.assertEqual(r["counts"]["CROSS_DOMAIN_TENSION"], 1)

    def test_unclear_claims_are_listed_as_insufficient(self):
        r = cca.assess_compound("X", [claim("a", "UNCLEAR", note="stopped")], True, {})
        self.assertEqual(r["insufficient"][0]["note"], "stopped")


class TestExtractors(unittest.TestCase):
    LABEL = {"set_id": "abc", "effective_time": "20240102",
             "warnings_and_cautions": ["Use with caution in patients with Parkinson's disease due to the risk of "
                                       "aggravation of symptoms. Other text."],
             "adverse_reactions": ["Nervous system: dizziness, extrapyramidal disorder, headache."],
             "drug_interactions": ["Antiparkinson drugs (for Parkinson's disease) may interact."],
             "indications_and_usage": ["X is a diagnostic agent for Parkinsonian syndromes."]}

    def test_label_rules(self):
        cl = {c["rule"]: c for c in cca.label_claims("DrugX", self.LABEL, "p.json")}
        self.assertEqual(cl["pd_aggravation_warning"]["direction"], "OPPOSES")
        self.assertEqual(cl["pd_aggravation_warning"]["label_strength"], "warning or contraindication")
        self.assertEqual(cl["drug_induced_parkinsonism"]["population"], "label study populations (not PD-specific)")
        self.assertTrue(cl["drug_induced_parkinsonism"]["label_strength"].startswith("listed"))
        self.assertIn("extrapyramidal", cl["drug_induced_parkinsonism"]["excerpt"])
        self.assertEqual(cl["pd_drug_interaction"]["direction"], "NEUTRAL")
        self.assertEqual(cl["diagnostic_indication"]["domain"], "diagnostic")
        self.assertEqual(cl["pd_aggravation_warning"]["source_date"], "2024-01-02")
        self.assertEqual(cl["pd_aggravation_warning"]["source_id"], "openFDA set_id abc")

    def test_label_without_pd_mentions_yields_no_claims(self):
        self.assertEqual(cca.label_claims("DrugX", {"warnings": ["Risk of falls."]}, "p"), [])

    def test_stopped_trial_is_unclear_not_negative(self):
        cl = cca.trial_context("DrugX", [{"nct_id": "NCT1", "status": "TERMINATED", "phase": "PHASE2",
                                          "first_posted": "2010-01-01"}])
        self.assertEqual(cl[0]["direction"], "UNCLEAR")
        self.assertIn("reason not retrieved", cl[0]["note"])

    def test_molecular_claim_absent_without_targets(self):
        self.assertIsNone(cca.molecular_claim({"drug": "X", "targets": [], "scoring": {}}, "p"))
        rec = {"drug": "X", "chembl_id": "C1", "targets": [{"gene_symbol": "DRD2", "action_type": "ANTAGONIST"}],
               "scoring": {"components": {"direct_target_disease": 0.4},
                           "detail": {"direct_score_per_target": {"DRD2": 0.4}}}}
        c = cca.molecular_claim(rec, "p")
        self.assertEqual((c["direction"], c["domain"]), ("SUPPORTS", "mechanism"))
        self.assertIn("DRD2 (ANTAGONIST)", c["excerpt"])
        self.assertIn("undirected", c["caveat"])


class TestRunOffline(unittest.TestCase):
    def test_temp_root_run_is_deterministic_offline_and_reports_missing(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "data", "cache", "openfda_labels"))
            with open(os.path.join(tmp, "data", "vps_scores_v2.csv"), "w") as fh:
                fh.write("compound_name,label\nDrugX,1\nDrugY,0\n")
            with open(os.path.join(tmp, "data", "cache", "openfda_labels", "DrugX.json"), "w") as fh:
                json.dump(TestExtractors.LABEL, fh)
            with open(os.path.join(tmp, cca.CURATED), "w") as fh:
                json.dump({"claims": [{"claim_id": "c1", "compound": "DrugX", "source_id": "PMID 1",
                                       "direction": "SUPPORTS", "domain": "efficacy"},
                                      {"claim_id": "bad", "compound": "DrugX"}]}, fh)

            def no_net(*a, **k):
                raise AssertionError("network used")
            with mock.patch.object(socket.socket, "connect", no_net), mock.patch("builtins.print"):
                cca.main(["--root", tmp])
                first = pathlib.Path(os.path.join(tmp, cca.OUT)).read_text()
                cca.main(["--root", tmp])
            self.assertEqual(first, pathlib.Path(os.path.join(tmp, cca.OUT)).read_text())
            out = json.loads(first)
            cca.validate_output(out)
            recs = {r["compound"]: r for r in out["records"]}
            self.assertEqual(recs["DrugX"]["status"], "CROSS_DOMAIN_TENSION")
            self.assertIn("missing", recs["DrugY"]["coverage"]["openfda_label"])
            self.assertEqual(recs["DrugY"]["status"], "NO_EVIDENCE")
            self.assertEqual(out["rejected_curated_claims"][0]["claim"], "bad")
            self.assertFalse(os.path.exists(os.path.join(tmp, cca.OUT) + ".tmp"))
        finally:
            shutil.rmtree(tmp)

    def test_validate_rejects_scores(self):
        out = {"agent_version": cca.AGENT_VERSION, "records": [
            {"compound": "X", "comparisons": [], "claims": [dict(claim("a", "SUPPORTS"), score=1)]}]}
        with self.assertRaises(ValueError):
            cca.validate_output(out)


class TestPersistedOutput(unittest.TestCase):
    PATH = os.path.join(ROOT, "data", "conflict_context.json")

    def setUp(self):
        if not os.path.exists(self.PATH):
            self.skipTest("data/conflict_context.json not generated")
        with open(self.PATH) as fh:
            self.out = json.load(fh)
        self.recs = {r["compound"]: r for r in self.out["records"]}

    def test_contract_and_known_findings(self):
        cca.validate_output(self.out)
        mel = self.recs["Melatonin"]
        self.assertEqual(mel["status"], "STATISTICAL_DISAGREEMENT")
        sd = [c for c in mel["comparisons"] if c["classification"] == "STATISTICAL_DISAGREEMENT"][0]
        self.assertIn("non_independent_sources", sd["flags"])
        self.assertEqual({sd["side_a"]["source_id"], sd["side_b"]["source_id"]}, {"PMID 40387966", "PMID 40588412"})
        self.assertEqual(self.recs["Donepezil"]["status"], "CONTEXT_DIFFERENCE")
        self.assertEqual(self.out["status_counts"]["DIRECT_CONTRADICTION"], 0)

    def test_every_curated_identifier_is_in_the_case_studies(self):
        with open(os.path.join(ROOT, "docs", "CASE_STUDIES.md"), encoding="utf-8") as fh:
            doc = fh.read()
        with open(os.path.join(ROOT, cca.CURATED)) as fh:
            curated = json.load(fh)["claims"]
        for c in curated:
            ident = re.sub(r"^PMID ", "", c["source_id"])
            self.assertIn(ident, doc, c["claim_id"])

    def test_pool_is_covered_and_no_vps_coupling(self):
        import pandas as pd
        pool = set(pd.read_csv(os.path.join(ROOT, "data", "vps_scores_v2.csv"))["compound_name"])
        self.assertTrue(pool <= set(self.recs))
        with open(os.path.join(ROOT, "scripts", "06_vps_fusion.py")) as fh:
            self.assertNotIn("conflict_context", fh.read())


if __name__ == "__main__":
    unittest.main()
