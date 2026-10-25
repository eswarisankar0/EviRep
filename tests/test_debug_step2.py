"""TD-008 regression: scripts/debug_step2.py reads PD disease-gene edges in Hetionet's Disease -> Gene direction,
the same genes stage 02 uses (it previously reported 0 PD genes)."""

import importlib.util
import os
import runpy
import shutil
import tempfile
import unittest

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestDebugStep2(unittest.TestCase):
    def test_disease_genes_match_stage02(self):
        pdid = "Disease::DOID:14330"
        edges = pd.DataFrame({"source": [pdid, pdid, pdid, "Gene::9", "Compound::C1"],
                              "target": ["Gene::1", "Gene::2", "Gene::3", pdid, "Gene::1"],
                              "metaedge": ["DaG", "DuG", "DrD", "GaD", "CbG"]})
        tmp = tempfile.mkdtemp()
        cwd = os.getcwd()
        try:
            os.makedirs(os.path.join(tmp, "data"))
            edges.to_csv(os.path.join(tmp, "data/hetionet_edges.csv"), index=False)
            pd.DataFrame({"compound_id": ["Compound::C1"], "compound_name": ["C1"]}).to_csv(
                os.path.join(tmp, "data/pd_candidates.csv"), index=False)
            os.chdir(tmp)
            g = runpy.run_path(os.path.join(ROOT, "scripts", "debug_step2.py"))
        finally:
            os.chdir(cwd)
            shutil.rmtree(tmp)
        spec = importlib.util.spec_from_file_location("s02", os.path.join(ROOT, "scripts", "02_network_proximity.py"))
        s02 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(s02)
        self.assertEqual(g["disease_genes"], {"Gene::1", "Gene::2"})
        self.assertEqual(set(s02.get_disease_genes(edges)), g["disease_genes"])


if __name__ == "__main__":
    unittest.main()
