"""Alternative (unapproved) result sets (audit 2026-10-21): compared on the identical cohort, never shown as approved,
withheld when stale. Expectations come from explicit pair counting, not from production output."""
import csv
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import compare_result_sets as crs  # noqa: E402

_spec = importlib.util.spec_from_file_location("evirep_ui_alt", os.path.join(ROOT, "ui", "server.py"))
ui = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ui)

COLS = ["compound_name", "label", "VPS_equal_5d", "VPS_equal", "molecular_plausibility_score",
        "r_proximity", "r_clinical", "r_literature", "r_safety", "r_molecular"]


def _write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS); w.writeheader(); w.writerows(rows)


def _rows(scores5, labels, mol=None):
    return [{"compound_name": f"C{i:02d}", "label": labels[i], "VPS_equal_5d": s, "VPS_equal": s * 0.9,
             "molecular_plausibility_score": (mol or scores5)[i], "r_proximity": 0.5, "r_clinical": 0.5,
             "r_literature": 0.5, "r_safety": 0.5, "r_molecular": (mol or scores5)[i]} for i, s in enumerate(scores5)]


def pair_count(y, s):
    pos = [v for v, t in zip(s, y) if t]; neg = [v for v, t in zip(s, y) if not t]
    return sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))


class TestCompareResultSets(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.labels = [1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1, 0]
        self.a = [0.9, 0.4, 0.5, 0.8, 0.3, 0.6, 0.7, 0.2, 0.55, 0.35, 0.65, 0.45]
        self.b = [0.6, 0.4, 0.5, 0.8, 0.3, 0.6, 0.45, 0.2, 0.55, 0.35, 0.65, 0.45]
        _write(os.path.join(self.d, "a.csv"), _rows(self.a, self.labels))
        _write(os.path.join(self.d, "b.csv"), _rows(self.b, self.labels, mol=self.b))

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_metrics_equal_pair_counting_and_paired_diff_is_drawwise(self):
        r = crs.compare(os.path.join(self.d, "a.csv"), os.path.join(self.d, "b.csv"))
        self.assertAlmostEqual(r["metrics"]["approved_5d"]["auroc"], pair_count(self.labels, self.a), places=12)
        self.assertAlmostEqual(r["metrics"]["candidate_5d"]["auroc"], pair_count(self.labels, self.b), places=12)
        self.assertAlmostEqual(r["paired"]["approved_minus_candidate"]["diff"], pair_count(self.labels, self.a) - pair_count(self.labels, self.b), places=12)
        lo, hi = r["paired"]["approved_minus_candidate"]["ci95"]
        self.assertLessEqual(lo, hi)
        self.assertEqual(r["cohort"]["positives"], 4)
        self.assertEqual(r["dimensions_changed"]["r_proximity"], 0)

    def test_refuses_different_labels(self):
        bad = list(self.labels); bad[1] = 1
        _write(os.path.join(self.d, "c.csv"), _rows(self.b, bad))
        with self.assertRaises(SystemExit):
            crs.compare(os.path.join(self.d, "a.csv"), os.path.join(self.d, "c.csv"))

    def test_refuses_different_compounds(self):
        rows = _rows(self.b, self.labels); rows[0]["compound_name"] = "Other"
        _write(os.path.join(self.d, "c.csv"), rows)
        with self.assertRaises(SystemExit):
            crs.compare(os.path.join(self.d, "a.csv"), os.path.join(self.d, "c.csv"))


class TestServedAlternatives(unittest.TestCase):
    def _root(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "data", "_candidates", "alt1"))
        labels = [1, 0, 0, 1, 0, 0]
        _write(os.path.join(d, "data", "base.csv"), _rows([.9, .1, .2, .8, .3, .4], labels))
        _write(os.path.join(d, "data", "_candidates", "alt1", "cand.csv"), _rows([.5, .1, .2, .8, .3, .4], labels))
        cwd = os.getcwd(); os.chdir(d)
        try:
            crs.main(["--baseline", "data/base.csv", "--candidate", "data/_candidates/alt1/cand.csv",
                      "--out", "data/_candidates/alt1/comparison.json", "--name", "alt1", "--rule", "test rule", "--decision", "TD-X"])
        finally:
            os.chdir(cwd)
        return d

    def test_shown_as_not_approved_with_metrics(self):
        d = self._root()
        try:
            a = ui.build_alternatives(d)["alternatives"][0]
            self.assertEqual((a["status"], a["approved"]), ("NOT APPROVED", False))
            self.assertNotIn("withheld", a)
            self.assertIn("candidate_5d", a["metrics"])
        finally:
            shutil.rmtree(d)

    def test_withheld_when_an_input_changed(self):
        d = self._root()
        try:
            with open(os.path.join(d, "data", "base.csv"), "a", encoding="utf-8") as fh:
                fh.write("\n")
            a = ui.build_alternatives(d)["alternatives"][0]
            self.assertIn("withheld", a)
            self.assertNotIn("metrics", a)
            self.assertEqual(a["stale_inputs"], ["data/base.csv"])
        finally:
            shutil.rmtree(d)

    def test_repository_alternative_is_current_and_never_approved(self):
        a = [x for x in ui.build_alternatives(ROOT)["alternatives"] if x["name"] == "td042_v1"]
        if not a:
            self.skipTest("no td042_v1 comparison in this checkout")
        a = a[0]
        self.assertFalse(a["approved"]); self.assertEqual(a["stale_inputs"], [])
        with open(os.path.join(ROOT, "data", "vps_evaluation_report.json"), encoding="utf-8") as fh:
            rep = json.load(fh)
        prim = next(p for p in rep["primary"] if p["column"] == "VPS_equal_5d")
        self.assertAlmostEqual(a["metrics"]["approved_5d"]["auroc"], prim["auroc"], places=12)
        self.assertEqual([round(x, 12) for x in a["metrics"]["approved_5d"]["auroc_ci95"]], [round(x, 12) for x in prim["auroc_ci95"]])


if __name__ == "__main__":
    unittest.main()
