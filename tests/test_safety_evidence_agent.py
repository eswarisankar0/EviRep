"""
Tests for the Safety Evidence Agent (10f), the shared agent contract, and the
stage 04/05 failure recording (E-021). Offline: fake HTTP responses only.
"""

import importlib.util
import json
import pathlib
import os
import shutil
import socket
import tempfile
import unittest

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


saf = _load("saf10f", "scripts/safety_evidence_agent.py")
contract = _load("contract", "scripts/agent_contract.py")
_real_connect = socket.socket.connect


def setUpModule():
    def refuse(*a, **k):
        raise AssertionError("tests must not open network connections")
    socket.socket.connect = refuse          # patch connect, not the class: importing requests/ssl subclasses socket


def tearDownModule():
    socket.socket.connect = _real_connect


class FakeResp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body
        self.headers = {"Content-Type": "application/json"}

    def json(self):
        return self._body


def fake_get(table):
    def get(url, params=None, timeout=None):
        for key, q in saf.faers_queries("X").items():
            if q == params:
                item = table[key]
                if isinstance(item, Exception):
                    raise item
                return FakeResp(*item)
        raise AssertionError("unexpected query")
    return get


NOT_FOUND = (404, {"error": {"code": "NOT_FOUND", "message": "No matches found!"}})
OK = {"serious": (200, {"results": [{"term": 1, "count": 30}, {"term": 2, "count": 10}]}),
      "deaths": (200, {"meta": {"results": {"total": 4}}, "results": []}),
      "pre_cutoff": (200, {"meta": {"results": {"total": 25}}, "results": []}),
      "top_reactions": (200, {"results": [{"term": "NAUSEA", "count": 5}]})}


class TestFaers(unittest.TestCase):
    def test_counts_are_normalised_with_cutoff_bounded_total(self):
        n = saf.normalise_faers(saf.fetch_faers("X", get=fake_get(OK), pause=0))
        self.assertEqual(n["state"], "RETRIEVED")
        self.assertEqual((n["total_reports"], n["serious_reports"], n["death_reports"], n["reports_received_by_2020"]),
                         (40, 30, 4, 25))
        self.assertEqual(n["top_reactions"][0]["term"], "NAUSEA")

    def test_not_found_is_no_record_not_failure_and_not_safety(self):
        n = saf.normalise_faers(saf.fetch_faers("X", get=fake_get({k: NOT_FOUND for k in OK}), pause=0))
        self.assertEqual(n["state"], "NO_RECORD")
        self.assertEqual(n["total_reports"], 0)
        self.assertIn("not evidence of safety", n["detail"])

    def test_zero_deaths_is_a_measured_zero(self):
        table = dict(OK, deaths=NOT_FOUND)
        n = saf.normalise_faers(saf.fetch_faers("X", get=fake_get(table), pause=0))
        self.assertEqual(n["death_reports"], 0)
        self.assertEqual(n["failed_queries"], [])

    def test_http_errors_and_exceptions_are_failures_not_zero(self):
        table = {k: (500, {"error": {"code": "SERVER_ERROR"}}) for k in OK}
        table["deaths"] = ConnectionError("down")
        n = saf.normalise_faers(saf.fetch_faers("X", get=fake_get(table), pause=0))
        self.assertEqual(n["state"], "FAILED")
        self.assertIn("deaths: ConnectionError", n["detail"])
        self.assertNotIn("total_reports", n)

    def test_partial_failure_keeps_retrieved_values_and_lists_failures(self):
        table = dict(OK, top_reactions=(429, {"error": {"code": "RATE_LIMIT"}}))
        n = saf.normalise_faers(saf.fetch_faers("X", get=fake_get(table), pause=0))
        self.assertEqual(n["state"], "RETRIEVED")
        self.assertEqual(n["failed_queries"], ["top_reactions: HTTP 429"])
        self.assertEqual(n["top_reactions"], [])

    def test_no_cache_is_not_retrieved(self):
        self.assertEqual(saf.normalise_faers(None)["state"], "NOT_RETRIEVED")


class TestLabelAndRun(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "data", "cache", "openfda_faers"))
        pd.DataFrame({"compound_name": ["A", "B", "C"], "label": [1, 0, 0]}).to_csv(
            os.path.join(self.root, saf.POOL), index=False)
        pd.DataFrame({"compound_name": ["A", "B"], "has_label": [True, False], "boxed_warning": [True, None],
                      "serious_term_count": [2, None], "warning_fields": ["boxed_warning", None],
                      "label_set_id": ["0c729939-d2d2-4e61-acbc-4f1646dc38c1", None],
                      "label_effective_time": [20231106, None]}).to_csv(os.path.join(self.root, saf.LABEL_CSV), index=False)
        with open(os.path.join(self.root, saf.LABEL_FAILURES), "w") as fh:
            fh.write(json.dumps({"compound_name": "C", "error_class": "HTTPError"}) + "\n")
        with open(os.path.join(self.root, saf.FAERS_CACHE, "A.json"), "w") as fh:
            json.dump(saf.fetch_faers("X", get=fake_get(OK), pause=0), fh)

    def tearDown(self):
        shutil.rmtree(self.root)

    def test_label_states_and_partial_run(self):
        out = saf.run(self.root)
        self.assertTrue(saf.validate_output(out))
        by = {r["compound"]: r for r in out["records"]}
        self.assertEqual(by["A"]["label"]["state"], "RETRIEVED")
        self.assertTrue(by["A"]["label"]["url"].startswith("https://dailymed.nlm.nih.gov/"))
        self.assertEqual(by["B"]["label"]["state"], "NO_RECORD")
        self.assertEqual(by["C"]["label"]["state"], "FAILED")        # recorded stage-05 failure, not 'never queried'
        self.assertEqual(by["B"]["faers"]["state"], "NOT_RETRIEVED")
        self.assertEqual(out["run_status"], "PARTIAL")
        self.assertTrue(any(d["code"] == "LABEL_FAILED" for d in out["diagnostics"]))
        self.assertIn("data/safety_signal.csv", out["inputs"])


class TestLabelAtCutoff(TestLabelAndRun):
    """Stage-05h states reach 10f unchanged: scored, unknown (no pre-cutoff version), no record."""

    def test_at_cutoff_states(self):
        pd.DataFrame({"compound_name": ["A", "B"], "state": ["PRE_CUTOFF_VERSION_SCORED", "NO_CURRENT_LABEL"],
                      "stage05_boxed_warning": [True, None], "stage05_serious_term_count": [2, None],
                      "cutoff_version": [3, None], "cutoff_version_date": ["2019-12-30", None],
                      "cutoff_boxed_warning": [False, None], "cutoff_serious_term_count": [2, None]}).to_csv(
            os.path.join(self.root, saf.LABEL_HISTORY), index=False)
        out = saf.run(self.root)
        saf.validate_output(out)
        by = {r["compound"]: r["label"] for r in out["records"]}
        a = by["A"]["at_cutoff"]
        self.assertEqual((a["state"], a["boxed_warning"], a["changed_since_cutoff"]), ("SCORED", False, True))
        self.assertEqual(by["A"]["temporal"], "POST_CUTOFF")
        self.assertEqual(by["B"]["at_cutoff"]["state"], "NO_RECORD")
        self.assertIn(saf.LABEL_HISTORY, out["inputs"])

    def test_unknown_is_not_no_record(self):
        self.assertEqual(saf.at_cutoff({"state": "NO_PRE_CUTOFF_VERSION", "detail": "x"})["state"], "UNKNOWN")
        self.assertEqual(saf.at_cutoff({"state": "RETRIEVAL_FAILED"})["state"], "FAILED")


class TestFailureNotMistakenForEvidence(unittest.TestCase):
    """Sprint 2026-10-19 audit: failures that were reported as NO_RECORD or as a clean SUCCESS."""

    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "data", "cache", "openfda_faers"))
        os.makedirs(os.path.join(self.root, "data", "cache", "openfda_labels"))
        pd.DataFrame({"compound_name": ["A", "B"]}).to_csv(os.path.join(self.root, saf.POOL), index=False)
        pd.DataFrame({"compound_name": ["A", "B"], "has_label": [True, True], "boxed_warning": [True, False],
                      "serious_term_count": [2, 1], "warning_fields": [None, None], "label_set_id": ["s1", "s2"],
                      "label_effective_time": [20231106, 20231106]}).to_csv(os.path.join(self.root, saf.LABEL_CSV), index=False)

    def tearDown(self):
        shutil.rmtree(self.root)

    def cache(self, name, table):
        with open(os.path.join(self.root, saf.FAERS_CACHE, name + ".json"), "w") as fh:
            json.dump(saf.fetch_faers("X", get=fake_get(table), pause=0), fh)

    def test_http_200_without_a_json_result_is_failure_not_no_record(self):
        class Html(FakeResp):
            def __init__(self):
                super().__init__(200, None)
                self.headers = {"Content-Type": "text/html"}
        rec = saf.fetch_faers("X", get=lambda *a, **k: Html(), pause=0)
        self.assertEqual(saf.normalise_faers(rec)["state"], "FAILED")
        n = saf.normalise_faers(saf.fetch_faers("X", get=fake_get({k: (200, {}) for k in OK}), pause=0))
        self.assertEqual(n["state"], "FAILED")

    def test_failed_query_or_missing_label_input_makes_run_partial(self):
        self.cache("A", dict(OK, pre_cutoff=(503, {"error": {"code": "SERVER_ERROR"}})))
        self.cache("B", OK)
        out = saf.run(self.root)
        self.assertEqual(out["run_status"], "PARTIAL")
        self.assertIn("FAERS_QUERY_FAILED", [d["code"] for d in out["diagnostics"]])
        os.remove(os.path.join(self.root, saf.LABEL_CSV))
        self.cache("A", OK)
        out = saf.run(self.root)
        self.assertEqual(out["run_status"], "PARTIAL")
        self.assertIn("LABEL_NOT_RETRIEVED", [d["code"] for d in out["diagnostics"]])

    def test_all_failed_writes_a_failed_envelope_instead_of_crashing(self):
        os.remove(os.path.join(self.root, saf.LABEL_CSV))
        with open(os.path.join(self.root, saf.LABEL_FAILURES), "w") as fh:
            for n in ("A", "B"):
                fh.write(json.dumps({"compound_name": n, "error_class": "HTTPError"}) + "\n")
        for n in ("A", "B"):
            self.cache(n, {k: (500, {"error": {"code": "SERVER_ERROR"}}) for k in OK})
        out = saf.run(self.root)
        self.assertEqual(out["run_status"], "FAILED")
        self.assertTrue(saf.validate_output(out))

    def test_fetch_retries_failed_cache_entries_only(self):
        self.cache("A", {k: (429, {"error": {"code": "RATE_LIMIT"}}) for k in OK})
        self.cache("B", OK)
        self.assertEqual(saf.needs_fetch(self.root, ["A", "B"]), ["A"])

    def test_raw_label_cache_is_a_tracked_input(self):
        with open(os.path.join(self.root, saf.LABEL_CACHE, "A.json"), "w") as fh:
            json.dump({"boxed_warning": ["text"]}, fh)
        self.cache("A", OK), self.cache("B", OK)
        self.assertIn("data/cache/openfda_labels/A.json", saf.run(self.root)["inputs"])

    def test_duplicate_pool_rows_are_counted_once(self):
        pd.DataFrame({"compound_name": ["A", "A", "B"]}).to_csv(os.path.join(self.root, saf.POOL), index=False)
        self.cache("A", OK), self.cache("B", OK)
        self.assertEqual(saf.run(self.root)["coverage"]["compounds"], 2)


class TestContract(unittest.TestCase):
    def test_run_status_rules(self):
        self.assertEqual(contract.run_status(0, 0, 0), "FAILED")
        self.assertEqual(contract.run_status(3, 3, 0), "FAILED")
        self.assertEqual(contract.run_status(3, 1, 2), "PARTIAL")
        self.assertEqual(contract.run_status(3, 0, 0), "NO_EVIDENCE")
        self.assertEqual(contract.run_status(3, 0, 1), "SUCCESS")

    def test_envelope_rejects_unexplained_partial_secrets_and_absolute_paths(self):
        with self.assertRaises(ValueError):
            contract.envelope("10f", "x", "1", "1", "PARTIAL", {}, {}, [])
        with self.assertRaises(ValueError):
            contract.envelope("10f", "x", "1", "1", "SUCCESS", {"/abs/path": "0"}, {}, [])
        with self.assertRaises(ValueError):
            contract.envelope("10z", "x", "1", "1", "SUCCESS", {}, {}, [])
        d = contract.diag("warn", "X", "failed for /Users/someone/data api_key=abc123")
        self.assertNotIn("abc123", d["message"])
        self.assertNotIn("someone", d["message"])

    def test_stale_inputs(self):
        root = tempfile.mkdtemp()
        try:
            with open(os.path.join(root, "f.csv"), "w") as fh:
                fh.write("a")
            h = contract.input_hashes(root, ["f.csv", "missing.csv"])
            # absent inputs are recorded as None (no hash is invented) so a later appearance is detected (E-055 A-7)
            self.assertEqual(h["missing.csv"], None)
            self.assertEqual(contract.stale_inputs(root, h), [])
            with open(os.path.join(root, "f.csv"), "w") as fh:
                fh.write("b")
            self.assertEqual(contract.stale_inputs(root, h), ["f.csv"])
            with open(os.path.join(root, "missing.csv"), "w") as fh:
                fh.write("c")
            self.assertEqual(contract.stale_inputs(root, h), ["f.csv", "missing.csv"])
        finally:
            shutil.rmtree(root)


class TestStageFailureRecording(unittest.TestCase):
    """E-021: stages 04/05 used to print and drop a failed compound."""

    def test_stage05_and_04_persist_failures(self):
        tmp = tempfile.mkdtemp()
        try:
            for rel, mod_name in (("scripts/05_safety_signal.py", "s05"), ("scripts/04_literature_independence.py", "s04")):
                src = pathlib.Path(os.path.join(ROOT, rel)).read_text()
                self.assertIn("record_failure(compound, e)", src)
                self.assertIn("raise SystemExit(1)", src)
            s05 = _load("s05", "scripts/05_safety_signal.py")
            p = os.path.join(tmp, "f.jsonl")
            s05.record_failure("Drug", RuntimeError("boom"), path=p)
            rec = json.loads(pathlib.Path(p).read_text())
            self.assertEqual((rec["compound_name"], rec["error_class"]), ("Drug", "RuntimeError"))
        finally:
            shutil.rmtree(tmp)


class TestPersistedOutput(unittest.TestCase):
    def test_real_output_valid_and_current(self):
        path = os.path.join(ROOT, saf.OUT)
        if not os.path.exists(path):
            self.skipTest("10f not run")
        out = json.loads(pathlib.Path(path).read_text())
        self.assertTrue(saf.validate_output(out))
        self.assertEqual(contract.stale_inputs(ROOT, out["inputs"]), [])
        by = {r["compound"]: r for r in out["records"]}
        self.assertEqual(by["Domperidone"]["label"]["state"], "NO_RECORD")


if __name__ == "__main__":
    unittest.main()
