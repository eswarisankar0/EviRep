"""
Tests for scripts/05h_safety_label_history.py: version selection at the cutoff, SPL section parsing (outermost
sections only, LOINC codes stage 05 uses), stage-05 scoring parity, failure and missing states kept distinct,
offline cache replay. No network.
"""

import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
import zipfile

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("h05", os.path.join(ROOT, "scripts", "05h_safety_label_history.py"))
h05 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h05)


def spl(boxed=None, warnings=None, wp=None, nested=False):
    sec = lambda code, text, inner="": (f'<component><section><code code="{code}" codeSystem="2.16.840.1.113883.6.1"/>'
                                        f"<text>{text}</text>{inner}</section></component>")
    parts = []
    if boxed:
        parts.append(sec("34066-1", boxed))
    if warnings:
        parts.append(sec("34071-1", warnings))
    if wp:
        inner = sec("34071-1", "nested warnings mention death") if nested else ""
        parts.append(sec("43685-7", wp, inner))
    return (f'<document xmlns="urn:hl7-org:v3"><component><structuredBody>{"".join(parts)}'
            f"</structuredBody></component></document>").encode()


def zipped(xml):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("label.xml", xml)
    return b.getvalue()


class Resp:
    def __init__(self, code=200, payload=None, content=b""):
        self.status_code, self._p, self.content = code, payload, content

    def json(self):
        if self._p is None:
            raise ValueError
        return self._p


class FakeDailyMed:
    def __init__(self, histories, spls, fail=()):
        self.h, self.s, self.fail, self.calls = histories, spls, set(fail), []

    def get(self, url, params=None, timeout=None):
        self.calls.append(url)
        if url.endswith("history.json"):
            setid = url.split("/")[-2]
            if setid in self.fail:
                return Resp(503)
            return Resp(200, {"data": {"history": [{"spl_version": v, "published_date": d} for v, d in self.h[setid]]}})
        return Resp(200, content=zipped(self.s[(params["setid"], params["version"])]))


class TestPure(unittest.TestCase):
    def test_version_at_cutoff(self):
        h = h05.parse_history({"data": {"history": [{"spl_version": 3, "published_date": "Jan 05, 2021"},
                                                    {"spl_version": 2, "published_date": "Dec 31, 2020"},
                                                    {"spl_version": 1, "published_date": "Jun 01, 2017"}]}})
        self.assertEqual(h05.version_at(h), (2, "2020-12-31"))           # published on the cutoff day counts
        self.assertIsNone(h05.version_at([(1, "2021-02-01")]))
        with self.assertRaises(h05.RetrievalError):
            h05.parse_history({"data": {"history": [{"spl_version": "x"}]}})

    def test_sections_outermost_only_and_scoring_matches_stage05_terms(self):
        terms = h05.serious_terms()
        self.assertIn("death", terms)
        s = h05.spl_sections(spl(boxed="Risk of death.", wp="Seizure and fatal outcomes.", nested=True))
        self.assertEqual(sorted(s), ["boxed_warning", "warnings_and_cautions"])     # nested 34071-1 not double-read
        sc = h05.score(s, terms)
        self.assertTrue(sc["boxed_warning"])
        self.assertEqual(sc["serious_term_count"], 4)          # death, seizure, fatal (+ nested 'death' once)

    def test_no_sections_is_zero_not_missing(self):
        sc = h05.score(h05.spl_sections(spl()), h05.serious_terms())
        self.assertEqual((sc["boxed_warning"], sc["serious_term_count"]), (False, 0))


class TestRun(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, h05.LABEL_CACHE))
        pd.DataFrame({"compound_name": ["Old Drug", "New", "Nolabel", "Broken"],
                      "has_label": [True, True, False, True], "boxed_warning": [True, False, "", False],
                      "serious_term_count": [1.0, 0.0, "", 0.0]}).to_csv(os.path.join(self.root, h05.SAFETY), index=False)
        for name, sid in (("Old_Drug", "s1"), ("New", "s2"), ("Broken", "s3")):
            with open(os.path.join(self.root, h05.LABEL_CACHE, f"{name}.json"), "w") as fh:
                json.dump({"set_id": sid}, fh)
        self.fake = FakeDailyMed({"s1": [(1, "Mar 01, 2015"), (2, "Feb 01, 2022")], "s2": [(1, "Jan 10, 2021")]},
                                 {("s1", 1): spl(warnings="no serious terms"), ("s1", 2): spl(boxed="death"),
                                  ("s2", 1): spl()}, fail={"s3"})

    def tearDown(self):
        shutil.rmtree(self.root)

    def run_main(self, argv=(), session=None):
        h05.time.sleep, sleep = (lambda s: None), h05.time.sleep
        try:
            return h05.main(list(argv), session=session, root=self.root)
        finally:
            h05.time.sleep = sleep

    def test_states(self):
        rc = self.run_main(session=self.fake)
        self.assertEqual(rc, 1)                                          # Broken failed
        d = pd.read_csv(os.path.join(self.root, h05.OUT)).set_index("compound_name")
        self.assertEqual(d.loc["Old Drug", "state"], "PRE_CUTOFF_VERSION_SCORED")
        self.assertEqual((d.loc["Old Drug", "cutoff_version"], bool(d.loc["Old Drug", "cutoff_boxed_warning"])), (1, False))
        self.assertTrue(bool(d.loc["Old Drug", "current_version_agrees_with_stage05"]))   # v2: boxed, 1 term
        self.assertEqual(d.loc["New", "state"], "NO_PRE_CUTOFF_VERSION")
        self.assertEqual(d.loc["Nolabel", "state"], "NO_CURRENT_LABEL")
        self.assertEqual(d.loc["Broken", "state"], "RETRIEVAL_FAILED")

    def test_offline_replay_identical_and_networkless(self):
        self.fake.fail = set()
        os.remove(os.path.join(self.root, h05.LABEL_CACHE, "Broken.json"))   # leave only retrievable compounds
        pd.read_csv(os.path.join(self.root, h05.SAFETY)).iloc[:3].to_csv(os.path.join(self.root, h05.SAFETY), index=False)
        self.assertEqual(self.run_main(session=self.fake), 0)
        with open(os.path.join(self.root, h05.OUT), "rb") as fh:
            a = fh.read()
        self.run_main(["--offline"])
        with open(os.path.join(self.root, h05.OUT), "rb") as fh:
            b = fh.read()
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
