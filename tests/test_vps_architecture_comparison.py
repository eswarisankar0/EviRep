"""scripts/vps_architecture_comparison.py: same population for every architecture; A is the published VPS."""
import importlib.util
import os
import unittest

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("vac", os.path.join(ROOT, "scripts", "vps_architecture_comparison.py"))
vac = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vac)


@unittest.skipUnless(os.path.exists(os.path.join(ROOT, "data", "safety_label_history.csv")), "needs live artifacts")
class TestArchitectures(unittest.TestCase):
    def test_a_is_the_published_score_and_population_is_shared(self):
        arch, y = vac.architectures(ROOT)
        self.assertEqual((len(y), int(y.sum())), (90, 14))
        pub = pd.read_csv(os.path.join(ROOT, "data", "vps_scores_v2.csv")).set_index("compound_name")
        a = arch["A approved 5D"]
        np.testing.assert_allclose(a.mean(axis=1).to_numpy(), pub.loc[a.index, "VPS_equal_5d"].to_numpy(), atol=1e-12)
        for k, F in arch.items():
            self.assertEqual(list(F.index), list(a.index), k)
            self.assertFalse(F.isna().any().any(), k)


if __name__ == "__main__":
    unittest.main()
