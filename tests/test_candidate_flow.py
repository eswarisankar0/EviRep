"""
Regression tests for the candidate data flow.

Guards TECHNICAL_DEBT TD-010: stages 02 and 03 previously read the UNFILTERED
`data/pd_candidates.csv`, so the 41 compounds removed by
`scripts/00_exclusion_filter.py` (vitamins, amino acids, electrolytes, basic
metabolites) were scored in stage 02 and queried in stage 03, then discarded
downstream in stage 06.

These tests are static: they read the scripts' source, so they pass without any
data/ files, without network access, and without running the pipeline. They
exist so the bypass cannot silently reappear.

Run:  ./venv/bin/python -m unittest discover -s tests -v
"""

import ast
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")

CANDIDATE_PATH_RE = re.compile(r"data/pd_candidates[\w]*\.csv")

FILTERED = "data/pd_candidates_filtered.csv"
UNFILTERED = "data/pd_candidates.csv"


def source(name):
    with open(os.path.join(SCRIPTS, name), encoding="utf-8") as fh:
        return fh.read()


def csv_string_literals(name):
    """
    Every string literal in the file that looks like a candidate CSV path.

    Parsed from the AST rather than grepped, so a path inside a comment (such
    as the explanatory TD-010 notes added with the fix) is not mistaken for an
    actual read.
    """
    tree = ast.parse(source(name))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            # Must be a bare path literal, not prose. Module/function
            # docstrings are also ast.Constant strings and mention these
            # filenames, so match the whole literal, not a substring.
            if CANDIDATE_PATH_RE.fullmatch(node.value.strip()):
                found.append(node.value.strip())
    return found


class TestStage02UsesFilteredCandidates(unittest.TestCase):
    SCRIPT = "02_network_proximity.py"

    def test_reads_filtered_candidate_file(self):
        self.assertIn(FILTERED, csv_string_literals(self.SCRIPT))

    def test_does_not_read_unfiltered_candidate_file(self):
        self.assertNotIn(
            UNFILTERED, csv_string_literals(self.SCRIPT),
            "stage 02 must not read the unfiltered candidate list (TD-010)")

    def test_no_other_candidate_csv_referenced(self):
        for literal in csv_string_literals(self.SCRIPT):
            self.assertEqual(literal, FILTERED, f"unexpected candidate path: {literal}")


class TestStage03UsesFilteredCandidates(unittest.TestCase):
    SCRIPT = "03_clinicaltrials_groundtruth.py"

    def test_reads_filtered_candidate_file(self):
        self.assertIn(FILTERED, csv_string_literals(self.SCRIPT))

    def test_does_not_read_unfiltered_candidate_file(self):
        self.assertNotIn(
            UNFILTERED, csv_string_literals(self.SCRIPT),
            "stage 03 must not read the unfiltered candidate list (TD-010)")

    def test_no_other_candidate_csv_referenced(self):
        for literal in csv_string_literals(self.SCRIPT):
            self.assertEqual(literal, FILTERED, f"unexpected candidate path: {literal}")


class TestProducersAndConsumersStillAgree(unittest.TestCase):
    """The filter's producer/consumer contract must stay intact."""

    def test_stage_01_still_produces_the_unfiltered_list(self):
        # 01 is the producer of pd_candidates.csv; the exclusion filter reads it.
        self.assertIn(UNFILTERED, csv_string_literals("01_get_pd_candidates.py"))

    def test_exclusion_filter_reads_unfiltered_and_writes_filtered(self):
        literals = csv_string_literals("00_exclusion_filter.py")
        self.assertIn(UNFILTERED, literals, "00 must read the unfiltered list")
        self.assertIn(FILTERED, literals, "00 must write the filtered list")

    def test_stage_06_still_consumes_the_filtered_list(self):
        self.assertIn(FILTERED, csv_string_literals("06_vps_fusion.py"))

    def test_exclusion_list_is_non_empty(self):
        """A silently emptied EXCLUSION_LIST would make the filter a no-op."""
        tree = ast.parse(source("00_exclusion_filter.py"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "EXCLUSION_LIST":
                        self.assertGreater(len(node.value.elts), 0)
                        return
        self.fail("EXCLUSION_LIST not found in 00_exclusion_filter.py")


class TestStage02DocstringMatchesBehaviour(unittest.TestCase):
    def test_docstring_names_the_filtered_input(self):
        doc = ast.get_docstring(ast.parse(source("02_network_proximity.py"))) or ""
        self.assertIn("pd_candidates_filtered.csv", doc)
        # The unfiltered name must not appear as a standalone input path.
        self.assertNotIn("data/pd_candidates.csv", doc,
                         "docstring must not advertise the unfiltered input")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestApiKeyPlaceholderGuard(unittest.TestCase):
    """E-008/TD-016: a placeholder NCBI_API_KEY made every PubMed request return
    HTTP 400, and the per-compound except swallowed it, so the stage reported
    success while writing an empty literature dimension."""

    def _stage04(self):
        import importlib.util
        path = os.path.join(SCRIPTS, "04_literature_independence.py")
        spec = importlib.util.spec_from_file_location("s04_key", path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_placeholders_rejected(self):
        m = self._stage04()
        for bad in ("your_key", "YOUR_KEY", "changeme", "placeholder", "", "   ", "abc"):
            self.assertEqual(m._valid_api_key(bad), "", f"should reject {bad!r}")

    def test_realistic_key_accepted(self):
        m = self._stage04()
        key = "a" * 36
        self.assertEqual(m._valid_api_key(key), key)

    def test_rejected_key_falls_back_to_unauthenticated(self):
        """A rejected key must not be attached to the request params."""
        m = self._stage04()
        m.NCBI_API_KEY = m._valid_api_key("your_key")
        self.assertNotIn("api_key", m._ncbi_params({"db": "pubmed"}))
