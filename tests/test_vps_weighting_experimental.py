"""Feature sets of scripts/vps_weighting_experimental.py: label-free ranks, complete, separate from the baseline."""
import importlib.util
import os
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("vwe", os.path.join(ROOT, "scripts", "vps_weighting_experimental.py"))
vwe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vwe)


@unittest.skipUnless(os.path.exists(os.path.join(ROOT, "data", "safety_label_history.csv")), "needs live artifacts")
class TestFeatureSets(unittest.TestCase):
    def test_sets_are_complete_ranks_and_label_free(self):
        sets, y, index = vwe.feature_sets(ROOT)
        self.assertEqual((len(index), int(y.sum())), (90, 14))
        self.assertEqual(set(sets), {"td042_bounded_lit_safety", "bounded_4d", "bounded_trio"})
        for F in sets.values():
            self.assertFalse(F.isna().any().any())
            self.assertTrue(((F >= 0) & (F <= 1)).all().all())   # legacy rank/n: inverted worst = 0 (D-024)
            self.assertNotIn("label", F.columns)
        # the bounded literature/safety columns really differ from the approved ones
        base = vwe.vve.build(ROOT)
        F = sets["td042_bounded_lit_safety"]
        self.assertFalse(np.allclose(F["r_literature"], base["r_literature"]))
        self.assertFalse(np.allclose(F["r_safety"], base["r_safety"]))


if __name__ == "__main__":
    unittest.main()
