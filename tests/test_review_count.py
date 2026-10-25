"""The 10c role text counts the human-review worklist instead of hard-coding "28" (final release audit 2026-10-21)."""
import importlib.util
import os
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("evirep_ui_review_count", os.path.join(ROOT, "ui", "server.py"))
ui = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ui)
HEADER = "priority,flag,nct_id,compound,status,reviewer,decision\n"


class TestReviewCountIsComputed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="evirep_review_count_")
        os.makedirs(os.path.join(self.tmp, "data"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, rows):
        with open(os.path.join(self.tmp, "data", "clinical_review_worklist.csv"), "w", encoding="utf-8") as fh:
            fh.write(HEADER + "".join(rows))

    def test_counts_only_unresolved_rows(self):
        self._write(["1,F,NCT1,A,UNRESOLVED - awaiting human adjudication,,\n",
                     "1,F,NCT2,B,UNRESOLVED - awaiting human adjudication,,\n",
                     "2,F,NCT3,C,ADJUDICATED (D-020) - retained,,\n"])
        self.assertIn("2 links awaiting human review", ui.agent_vps_role(self.tmp, "10c"))

    def test_singular_and_missing_file(self):
        self._write(["1,F,NCT1,A,UNRESOLVED - awaiting human adjudication,,\n"])
        self.assertIn("1 link awaiting", ui.agent_vps_role(self.tmp, "10c"))
        os.remove(os.path.join(self.tmp, "data", "clinical_review_worklist.csv"))
        self.assertIn("count unavailable", ui.agent_vps_role(self.tmp, "10c"))

    def test_repository_value_matches_the_worklist(self):
        import csv
        with open(os.path.join(ROOT, "data", "clinical_review_worklist.csv"), encoding="utf-8") as fh:
            n = sum(1 for r in csv.DictReader(fh) if r["status"].startswith("UNRESOLVED"))
        self.assertIn(f"{n} link", ui.agent_vps_role(ROOT, "10c"))
        self.assertNotIn("{review_open}", ui.agent_vps_role(ROOT, "10c"))
        self.assertEqual(ui.agent_vps_role(ROOT, "10h"), ui.AGENT_VPS_ROLE["10h"])


if __name__ == "__main__":
    unittest.main()
