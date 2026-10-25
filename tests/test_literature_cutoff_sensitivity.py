"""
Tests for scripts/vps_literature_cutoff_sensitivity.py: only primary, pre-cutoff journal records from the bounded
search are counted; shared authors merge records into one component; a failed retrieval is missing (NaN), never 0;
the run reproduces the approved baseline and never writes outside --out.
"""

import importlib.util
import json
import os
import shutil
import tempfile
import unittest

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("lcs", os.path.join(ROOT, "scripts", "vps_literature_cutoff_sensitivity.py"))
lcs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lcs)


def rec(name, pmid, authors, **kw):
    r = {"compound_name": name, "pmid": pmid, "authors": authors, "in_cutoff_bounded_search": True,
         "cutoff_status": "PRE_CUTOFF", "is_primary_record": True, "not_primary_evidence_type": None,
         "record_type": "JOURNAL_ARTICLE"}
    r.update(kw)
    return r


class TestBoundedMeasures(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "data"))
        pd.DataFrame({"compound_name": ["A", "B", "C"], "status": ["SUCCESS", "NO_RESULTS", "RETRIEVAL_FAILED"]}) \
            .to_csv(os.path.join(self.root, lcs.SUMMARY), index=False)
        recs = [rec("A", "1", ["x"]), rec("A", "2", ["x", "y"]), rec("A", "3", ["z"]),
                rec("A", "4", ["w"], cutoff_status="POST_CUTOFF"),
                rec("A", "5", ["v"], is_primary_record=False),
                rec("A", "6", ["u"], not_primary_evidence_type=["Comment"]),
                rec("A", "7", ["t"], in_cutoff_bounded_search=False),
                rec("A", "8", ["s"], record_type="BOOK_CHAPTER")]
        with open(os.path.join(self.root, lcs.PAPERS), "w") as fh:
            for r in recs:
                fh.write(json.dumps(r) + "\n")

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_filters_components_and_missing(self):
        m = lcs.bounded_measures(self.root)
        self.assertEqual(m.loc["A", "lit_bounded_count"], 3)            # 1, 2, 3 only
        self.assertEqual(m.loc["A", "lit_bounded_author_comp"], 2)      # {1, 2} share author x; {3}
        self.assertEqual(m.loc["B", "lit_bounded_count"], 0)            # queried, nothing found: a true zero
        self.assertTrue(np.isnan(m.loc["C", "lit_bounded_count"]))      # failure: missing, not zero


class TestBoundedSafety(unittest.TestCase):
    def test_mixed_and_strict(self):
        root = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(root, "data"))
            pd.DataFrame({"compound_name": ["A", "B", "C"],
                          "state": ["PRE_CUTOFF_VERSION_SCORED", "NO_PRE_CUTOFF_VERSION", "NO_CURRENT_LABEL"],
                          "stage05_has_label": [True, True, False], "stage05_boxed_warning": [True, False, None],
                          "stage05_serious_term_count": [9, 4, None], "cutoff_boxed_warning": [False, None, None],
                          "cutoff_serious_term_count": [2, None, None]}).to_csv(os.path.join(root, lcs.SAFETY_HISTORY),
                                                                                index=False)
            mixed, strict, n = lcs.bounded_safety(root, pd.Index(["A", "B", "C"]))
            self.assertEqual(n, 1)
            self.assertEqual(mixed["A"], 2)                      # the label at the cutoff, not today's 9 + 5
            self.assertEqual(mixed["B"], 4)                      # no pre-cutoff version: current label kept
            self.assertTrue(np.isnan(strict["B"]))               # strict: unknown, ranked neutral later
            self.assertTrue(np.isnan(mixed["C"]) and np.isnan(strict["C"]))   # no label stays unmeasured
        finally:
            shutil.rmtree(root)


@unittest.skipUnless(os.path.exists(os.path.join(ROOT, "data", "literature_papers.jsonl")), "stage 04p output absent")
class TestOnPersistedArtefacts(unittest.TestCase):
    def test_reference_rows_match_the_approved_baseline(self):
        res = lcs.run(ROOT, n_boot=50)
        rows = {r["model"]: r for r in res["results"]}
        self.assertEqual((res["n"], res["positives"]), (90, 14))
        self.assertAlmostEqual(rows["5D published (approved)"]["auroc"], 0.7755, places=3)
        self.assertEqual(res["n_compounds_without_04p_record"], 0)
