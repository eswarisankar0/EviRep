"""
Tests for scripts/vps_molecular_snapshot_sensitivity.py: 20.11 rows for Parkinson's only, indirect preferred over
direct, excluded datatypes (literature, known_drug) never counted, direct component = max over targets, no target
stays unmeasured, and the 26.09 recompute equals the published stage-08 direct component.
"""

import importlib.util
import json
import os
import shutil
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("mss", os.path.join(ROOT, "scripts", "vps_molecular_snapshot_sensitivity.py"))
mss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mss)


def row(tid, disease, direct, **dt):
    return {"target": {"id": tid}, "disease": {"id": disease}, "is_direct": direct,
            "association_score": {"datatypes": dt}}


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, os.path.dirname(mss.OT2011)))
        rows = [row("T1", "EFO_0002508", True, genetic_association=0.9),
                row("T1", "EFO_0002508", False, genetic_association=0.5, literature=1.0),
                row("T2", "EFO_0002508", True, known_drug=1.0, literature=0.8, animal_model=0.2),
                row("T3", "Orphanet_1", False, genetic_association=1.0)]
        with open(os.path.join(self.root, mss.OT2011), "w") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        ev = [{"drug": "A", "targets": [{"ensembl_id": "T1"}, {"ensembl_id": "T2"}],
               "disease_links": [{"ensembl_id": "T1", "datatype_scores_used": {"genetic_association": 0.7}},
                                 {"ensembl_id": "T2", "datatype_scores_used": {"animal_model": 0.3}}],
               "scoring": {"components": {"direct_target_disease": 0.7}}},
              {"drug": "B", "targets": [], "disease_links": []},
              {"drug": "C", "targets": [{"ensembl_id": "T3"}], "disease_links": []}]
        with open(os.path.join(self.root, mss.EVIDENCE), "w") as fh:
            for r in ev:
                fh.write(json.dumps(r) + "\n")

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_load_and_components(self):
        ot = mss.load_2011(self.root)
        self.assertEqual(ot, {"T1": 0.5, "T2": 0.2})                 # indirect row kept; literature/known_drug ignored
        d = mss.direct_components(self.root, ot)
        self.assertEqual((d.loc["A", "direct_current"], d.loc["A", "direct_2011"]), (0.7, 0.5))
        self.assertTrue(np.isnan(d.loc["B", "direct_2011"]))         # no target: unmeasured, not zero
        self.assertEqual(d.loc["C", "direct_2011"], 0.0)              # target without a 2020 PD row: measured zero


@unittest.skipUnless(os.path.exists(os.path.join(ROOT, "data", "molecular_pathway_evidence.jsonl")), "stage 08 output absent")
class TestRecomputeMatchesPublished(unittest.TestCase):
    def test_current_direct_equals_published(self):
        d = mss.direct_components(ROOT, {})
        m = d["direct_current"].notna()
        self.assertLess((d.loc[m, "direct_current"] - d.loc[m, "direct_published"]).abs().max(), 1e-6)   # published rounds to 6 dp


if __name__ == "__main__":
    unittest.main()
