"""
Tests for the opt-in publication-date bound in stage 04 (TD-021).

The default query must stay byte-identical (no silent methodology change);
the bounded query must carry PubMed's pdat window; main() must not use it.
Offline: requests.get is mocked.
"""

import importlib.util
import pathlib
import os
import re
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "scripts", "04_literature_independence.py")
with mock.patch.dict(os.environ, {"NCBI_API_KEY": ""}):
    _spec = importlib.util.spec_from_file_location("lit04", PATH)
    lit04 = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(lit04)

XML = b"<eSearchResult><IdList><Id>111</Id><Id>222</Id></IdList></eSearchResult>"


def _call(**kw):
    resp = mock.Mock(content=XML)
    resp.raise_for_status.return_value = None
    with mock.patch.object(lit04.requests, "get", return_value=resp) as get:
        ids = lit04.search_pmids("Droxidopa", **kw)
    return ids, get.call_args.kwargs["params"]


class TestDateBound(unittest.TestCase):
    def test_default_query_is_unbounded_and_unchanged(self):
        ids, params = _call()
        self.assertEqual(ids, ["111", "222"])
        self.assertEqual(params["term"], '"Droxidopa"[Title/Abstract] AND "Parkinson Disease"[Title/Abstract]')
        self.assertEqual(params["retmax"], lit04.MAX_PAPERS_PER_COMPOUND)
        for k in ("datetype", "mindate", "maxdate"):
            self.assertNotIn(k, params)

    def test_bounded_query_uses_publication_date_window(self):
        _, params = _call(max_date="2020/12/31")
        self.assertEqual(params["datetype"], "pdat")
        self.assertEqual(params["maxdate"], "2020/12/31")
        self.assertEqual(params["mindate"], "1800/01/01")   # PubMed requires both ends

    def test_malformed_date_rejected_before_any_request(self):
        for bad in ("2021-01-01", "2020/1/1", "yesterday", "2020/12/31; DROP"):
            with mock.patch.object(lit04.requests, "get") as get:
                with self.assertRaises(ValueError):
                    lit04.search_pmids("X", max_date=bad)
                get.assert_not_called()

    def test_main_does_not_enable_the_bound(self):
        src = pathlib.Path(PATH).read_text(encoding="utf-8")
        main_src = src[src.index("def main():"):]
        self.assertIsNone(re.search(r"search_pmids\([^)]*max_date", main_src))


if __name__ == "__main__":
    unittest.main()
