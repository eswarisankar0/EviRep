"""
Regression tests for gaps found while auditing the molecular agent and its use
as VPS dimension 5. Each test covers a path no existing test exercised:

  * scripts/08_molecular_pathway.py `flatten` (the CSV that step 06 consumes)
    and the score identity score = 0.6*direct + 0.4*pathway on its output;
  * run_agent's target-retrieval API-failure path (resolution succeeded,
    mechanism/target fetch failed);
  * OpenTargetsClient re-fetching over a corrupt cache entry;
  * read-only contracts on the persisted artifacts (identity, leakage, cohort);
  * a latent defect in step 08's `--fresh` handling (expected failure).

Run:  ./venv/bin/python -m unittest discover -s tests -v

No network. Nothing is written to the project's data/ directory: the step-08
test runs inside a TemporaryDirectory with the API layer stubbed out, and the
persisted-artifact tests only read, and skip when the files are absent.
"""

import importlib.util
import json
import math
import os
import sys
import tempfile
import unittest
from unittest import mock

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import molecular_agent as ma  # noqa: E402

MOL_CSV = os.path.join(ROOT, "data", "molecular_pathway.csv")
MOL_JSONL = os.path.join(ROOT, "data", "molecular_pathway_evidence.jsonl")
VPS_CSV = os.path.join(ROOT, "data", "vps_scores_v2.csv")


def _load_step08():
    path = os.path.join(ROOT, "scripts", "08_molecular_pathway.py")
    spec = importlib.util.spec_from_file_location("step08_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


step08 = _load_step08()


class _DeadClient:
    """Stands in for OpenTargetsClient: every query fails as the API would."""

    url = "stub://opentargets"

    def query(self, query, variables=None):
        raise ma.OpenTargetsUnavailable("HTTP 503 (stub)")


def _module_with_genes():
    module = ma.DiseaseModule(disease_id="MONDO_0005180",
                              disease_name="Parkinson's disease")
    module.genes["ENSG_PD"] = {"ensembl_id": "ENSG_PD", "gene_symbol": "PDG"}
    module.pathway_to_genes["R-HSA-1"] = {"ENSG_PD"}
    return module


def _scored_record(direct, pathway):
    cfg = ma.MolecularAgentConfig()
    score = cfg.weight_direct * direct + cfg.weight_pathway * pathway
    return {
        "drug": "Fixturedrug", "chembl_id": "CHEMBL0",
        "molecular_plausibility_score": round(score, 6), "confidence": 1.0,
        "scoring": {"components": {"direct_target_disease": round(direct, 6),
                                   "pathway_overlap": round(pathway, 6)},
                    "detail": {"n_target_pathways": 3,
                               "n_target_pathways_in_disease_module": 1}},
        "targets": [{"ensembl_id": "E1"}], "genes": [{"ensembl_id": "E1"}],
        "disease_links": [{"score_allowed_datatypes": direct},
                          {"score_allowed_datatypes": 0.0}],
        "evidence": [{"tier": "direct"}, {"tier": "indirect"}],
        "limitations": ["a"],
    }


# ============================================================================
# STEP 08 FLATTEN: the projection step 06 actually reads
# ============================================================================


class TestFlattenContract(unittest.TestCase):
    def test_flatten_emits_exactly_the_csv_columns(self):
        row = step08.flatten(_scored_record(0.4373, 1 / 3))
        self.assertEqual(list(row), step08.CSV_COLUMNS)

    def test_flatten_preserves_score_identity(self):
        for direct, pathway in [(0.0, 0.0), (0.4373, 1 / 3), (1.0, 1.0), (0.754171, 11 / 13)]:
            row = step08.flatten(_scored_record(direct, pathway))
            recomputed = 0.6 * row["direct_component"] + 0.4 * row["pathway_component"]
            self.assertAlmostEqual(recomputed, row["molecular_plausibility_score"], delta=1e-6)

    def test_flatten_counts_only_permitted_direct_links(self):
        row = step08.flatten(_scored_record(0.5, 0.5))
        self.assertEqual(row["n_direct_disease_links"], 1)
        self.assertEqual(row["n_disease_link_rows"], 2)

    def test_flatten_unscored_record_has_null_components_and_zero_score(self):
        """Unresolved and no-target drugs carry no `scoring` block: components are None (NaN in
        the CSV) while the score is 0.0. Consumers must not treat the NaN
        components as a score mismatch, nor the 0.0 as a measured component."""
        rec = ma.run_agent("Nodrug", _DeadClient(), _module_with_genes(),
                           resolution={"chembl_id": None, "candidates": []})
        row = step08.flatten(rec)
        self.assertIsNone(row["direct_component"])
        self.assertIsNone(row["pathway_component"])
        self.assertEqual(row["molecular_plausibility_score"], 0.0)
        self.assertFalse(row["resolved"])


# ============================================================================
# AGENT FAILURE / CACHE PATHS NOT PREVIOUSLY EXERCISED
# ============================================================================


class TestTargetRetrievalFailure(unittest.TestCase):
    def test_api_down_after_resolution_yields_valid_missing_record(self):
        resolution = {"chembl_id": "CHEMBL9", "resolved_name": "X",
                      "match_type": "exact_name", "candidates": []}
        rec = ma.run_agent("Xdrug", _DeadClient(), _module_with_genes(),
                           resolution=resolution)
        ma.validate_output(rec)
        self.assertEqual(rec["chembl_id"], "CHEMBL9")
        self.assertEqual(rec["molecular_plausibility_score"], 0.0)
        self.assertEqual(rec["confidence"], 0.0)
        self.assertEqual(rec["targets"], [])
        self.assertEqual({e["tier"] for e in rec["evidence"]}, {ma.EvidenceTier.MISSING})
        self.assertTrue(any("Target retrieval failed" in l for l in rec["limitations"]))


class _OkResponse:
    status_code = 200
    headers = {}

    def json(self):
        return {"data": {"ok": True}}


class _CountingSession:
    def __init__(self):
        self.calls = 0

    def post(self, url, json=None, timeout=None):  # noqa: A002
        self.calls += 1
        return _OkResponse()


class TestCorruptCache(unittest.TestCase):
    def test_corrupt_cache_entry_is_refetched_and_repaired(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = ma.MolecularAgentConfig(cache_dir=tmp, min_request_interval_s=0.0)
            session = _CountingSession()
            client = ma.OpenTargetsClient(cfg, session=session)
            path = client._cache_path("{ q }", {})
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("{not json")
            self.assertEqual(client.query("{ q }", {}), {"ok": True})
            self.assertEqual(session.calls, 1)
            self.assertEqual(client.query("{ q }", {}), {"ok": True})
            self.assertEqual(session.calls, 1, "repaired entry must be served from cache")


# ============================================================================
# STEP 08 --fresh: LATENT DEFECT
# ============================================================================


class TestStep08FreshRun(unittest.TestCase):
    """`--fresh` skips loading the checkpoint but still opens it in append
    mode (08_molecular_pathway.py:273), and the collect loop keeps the FIRST
    record per drug (08_molecular_pathway.py:296-298). A --fresh rescore
    therefore wrote the STALE record to the CSV/JSONL. Fixed 2026-10-12: the
    collect step now keeps the LAST record per drug. Regression test."""

    def test_fresh_rescore_replaces_stale_checkpoint_record(self):
        def fake_run_agent(name, client, module, config, resolution):
            return {"drug": name, "chembl_id": "CHEMBL1", "targets": [], "genes": [],
                    "pathways": [], "disease_links": [], "mechanistic_chain": [],
                    "molecular_plausibility_score": 0.9, "confidence": 1.0,
                    "evidence": [{"tier": "direct", "source": "stub"}],
                    "limitations": [], "disease": "PD",
                    "scoring": {"components": {"direct_target_disease": 1.0,
                                               "pathway_overlap": 0.75}}}

        stale = {"drug": "Alpha", "chembl_id": "CHEMBL1",
                 "molecular_plausibility_score": 0.1, "confidence": 1.0,
                 "evidence": [], "limitations": []}
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                ckpt = os.path.join(tmp, "ckpt.jsonl")
                with open(ckpt, "w", encoding="utf-8") as fh:
                    fh.write(json.dumps(stale) + "\n")
                module = _module_with_genes()
                argv = ["08", "--compounds", "Alpha", "--fresh",
                        "--checkpoint", ckpt,
                        "--out", os.path.join(tmp, "m.csv"),
                        "--out-jsonl", os.path.join(tmp, "m.jsonl")]
                with mock.patch.object(sys, "argv", argv), \
                     mock.patch.object(step08, "OpenTargetsClient",
                                       lambda cfg: mock.Mock(stats={"network": 0, "cache_hits": 0, "retries": 0})), \
                     mock.patch.object(step08, "build_disease_module", lambda c, cfg: module), \
                     mock.patch.object(step08, "normalize_drug_batch", lambda names, c: {}), \
                     mock.patch.object(step08, "run_agent", fake_run_agent), \
                     mock.patch.object(step08, "validate_output", lambda r: None), \
                     mock.patch.object(step08, "tqdm", lambda it, **kw: it), \
                     mock.patch("builtins.print"):
                    step08.main()
                out = pd.read_csv(os.path.join(tmp, "m.csv"))
            finally:
                os.chdir(cwd)
        self.assertAlmostEqual(float(out.loc[0, "molecular_plausibility_score"]), 0.9)


class TestRetrievalFailureIsNotAMeasuredZero(unittest.TestCase):
    """Sprint 2026-10-19 audit: an API-down record (score 0.0) was checkpointed as done, never retried,
    published by stage 08 with exit 0, and accepted by the 10b run record as SUCCESS."""

    def failed_record(self, name="Alpha"):
        return ma.run_agent(name, _DeadClient(), _module_with_genes(),
                            resolution={"chembl_id": "CHEMBL9", "resolved_name": name,
                                        "match_type": "exact_name", "candidates": []})

    def test_helper_recognises_api_failure_records(self):
        self.assertTrue(ma.is_retrieval_failure(self.failed_record()))
        self.assertFalse(ma.is_retrieval_failure(_scored_record(0.5, 0.5)))

    def run08(self, tmp, ckpt_records, fake):
        ckpt = os.path.join(tmp, "ckpt.jsonl")
        with open(ckpt, "w", encoding="utf-8") as fh:
            for r in ckpt_records:
                fh.write(json.dumps(r) + "\n")
        argv = ["08", "--compounds", "Alpha", "--checkpoint", ckpt,
                "--out", os.path.join(tmp, "m.csv"), "--out-jsonl", os.path.join(tmp, "m.jsonl")]
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(step08, "OpenTargetsClient",
                               lambda cfg: mock.Mock(stats={"network": 0, "cache_hits": 0, "retries": 0})), \
             mock.patch.object(step08, "build_disease_module", lambda c, cfg: _module_with_genes()), \
             mock.patch.object(step08, "normalize_drug_batch", lambda names, c: {}), \
             mock.patch.object(step08, "run_agent", fake), \
             mock.patch.object(step08, "validate_output", lambda r: None), \
             mock.patch.object(step08, "tqdm", lambda it, **kw: it), \
             mock.patch("builtins.print"):
            step08.main()

    def test_resume_retries_a_checkpointed_failure(self):
        calls = []

        def fake(name, *a):
            calls.append(name)
            return dict(_scored_record(0.5, 0.5), drug=name)
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                self.run08(tmp, [self.failed_record()], fake)
                out = pd.read_csv(os.path.join(tmp, "m.csv"))
            finally:
                os.chdir(cwd)
        self.assertEqual(calls, ["Alpha"])
        self.assertAlmostEqual(float(out.loc[0, "molecular_plausibility_score"]), 0.5)

    def test_stage_exits_nonzero_when_a_failure_remains(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                with self.assertRaises(SystemExit) as cm:
                    self.run08(tmp, [], lambda name, *a: self.failed_record(name))
            finally:
                os.chdir(cwd)
        self.assertEqual(cm.exception.code, 1)

    def run_record(self, rows, recs):
        import molecular_run_record as mrr
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "data"))
            pd.DataFrame(rows).to_csv(os.path.join(tmp, mrr.CSV), index=False)
            with open(os.path.join(tmp, mrr.JSONL), "w") as fh:
                for r in recs:
                    fh.write(json.dumps(r) + "\n")
            return mrr.build(tmp)

    @unittest.skipUnless(os.path.exists(MOL_JSONL), "molecular evidence not present")
    def test_run_record_flags_failures_and_blank_scores(self):
        with open(MOL_JSONL, encoding="utf-8") as fh:
            good = dict(json.loads(fh.readline()), drug="Beta")
        bad = self.failed_record("Alpha")
        row = lambda n, s: {"compound_name": n, "molecular_plausibility_score": s, "n_targets": 1, "resolved": True,
                            "n_evidence_missing": 0}
        out = self.run_record([row("Alpha", 0.0), row("Beta", good["molecular_plausibility_score"])], [bad, good])
        self.assertIn("RETRIEVAL_FAILED_RECORD", [d["code"] for d in out["diagnostics"]])
        self.assertNotEqual(out["run_status"], "SUCCESS")
        out = self.run_record([row("Beta", None)], [good])
        self.assertIn("CSV_JSONL_MISMATCH", [d["code"] for d in out["diagnostics"]])


# ============================================================================
# PERSISTED ARTIFACTS (read-only; skip on a fresh clone)
# ============================================================================


@unittest.skipUnless(os.path.exists(MOL_CSV), "molecular_pathway.csv not present")
class TestPersistedMolecularIdentity(unittest.TestCase):
    def test_score_equals_weighted_components_on_every_scored_row(self):
        m = pd.read_csv(MOL_CSV)
        scored = m.dropna(subset=["direct_component", "pathway_component"])
        self.assertGreater(len(scored), 0)
        err = (0.6 * scored.direct_component + 0.4 * scored.pathway_component
               - scored.molecular_plausibility_score).abs().max()
        self.assertLess(err, 1e-5)

    def test_rows_without_components_score_zero(self):
        m = pd.read_csv(MOL_CSV)
        unscored = m[m.direct_component.isna() | m.pathway_component.isna()]
        self.assertTrue((unscored.molecular_plausibility_score == 0.0).all())
        self.assertTrue((unscored.n_targets == 0).all())

    def test_nonzero_score_never_has_zero_confidence(self):
        m = pd.read_csv(MOL_CSV)
        self.assertEqual(int(((m.molecular_plausibility_score > 0) &
                              (m.confidence == 0)).sum()), 0)


@unittest.skipUnless(os.path.exists(MOL_JSONL), "molecular evidence JSONL not present")
class TestPersistedLeakageControl(unittest.TestCase):
    def test_no_scored_disease_link_used_an_excluded_datatype(self):
        allowed = set(ma.MolecularAgentConfig().allowed_datatypes)
        with open(MOL_JSONL, encoding="utf-8") as fh:
            for line in fh:
                rec = json.loads(line)
                for link in rec["disease_links"]:
                    used = set(link.get("datatype_scores_used") or {})
                    self.assertLessEqual(used, allowed, rec["drug"])
                    if used:
                        self.assertTrue(math.isclose(
                            max(link["datatype_scores_used"].values()),
                            link["score_allowed_datatypes"]), rec["drug"])


@unittest.skipUnless(os.path.exists(MOL_CSV) and os.path.exists(VPS_CSV),
                     "persisted molecular/VPS outputs not present")
class TestPersistedCohortAlignment(unittest.TestCase):
    def test_molecular_rows_match_vps_cohort_and_values(self):
        m = pd.read_csv(MOL_CSV)
        v = pd.read_csv(VPS_CSV)
        self.assertEqual(set(m.compound_name), set(v.compound_name))
        j = v.merge(m[["compound_name", "molecular_plausibility_score"]],
                    on="compound_name", suffixes=("", "_m"))
        self.assertEqual(
            float((j.molecular_plausibility_score - j.molecular_plausibility_score_m).abs().max()),
            0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
