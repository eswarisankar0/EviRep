"""Stage 02 draws degree-matched random target sets with a fixed seed. The draws must not depend on Python's
per-process string hashing (PYTHONHASHSEED): iterating a set of target IDs made proximity_z differ between
otherwise identical runs (found 2026-10-19; up to 2.0 in z)."""

import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROG = r"""
import importlib.util, random, sys, networkx as nx
spec = importlib.util.spec_from_file_location("st02", sys.argv[1]); m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
G = nx.Graph()
for i in range(60):
    G.add_edge(f"Gene::{i}", f"Gene::{(i * 7 + 3) % 60}"); G.add_edge(f"Gene::{i}", f"Gene::{(i + 1) % 60}")
bins = m.build_degree_bins(G)
random.seed(42)
targets = {f"Gene::{i}" for i in range(0, 60, 3)}
print([sorted(m.generate_random_target_set(targets, G, bins)) for _ in range(5)])
"""


class TestDeterminismAcrossHashSeeds(unittest.TestCase):
    def test_random_target_sets_do_not_depend_on_pythonhashseed(self):
        outs = []
        for h in ("0", "1", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=h)
            p = subprocess.run([sys.executable, "-c", PROG, os.path.join(ROOT, "scripts", "02_network_proximity.py")],
                               capture_output=True, text=True, env=env, cwd=ROOT, timeout=120)
            self.assertEqual(p.returncode, 0, p.stderr[-500:])
            outs.append(p.stdout.strip().splitlines()[-1])
        self.assertEqual(len(set(outs)), 1)


if __name__ == "__main__":
    unittest.main()
