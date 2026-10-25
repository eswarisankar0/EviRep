"""The server reports when its own code on disk differs from the code it is running (audit 2026-10-21: a live server
started before a code change served the new page with the old API, and the new endpoints returned 404)."""
import importlib.util
import os
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("evirep_ui_codechange", os.path.join(ROOT, "ui", "server.py"))
ui = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ui)


class TestServerCodeChange(unittest.TestCase):
    def test_unchanged_code_is_not_flagged(self):
        self.assertFalse(ui.build_status(ROOT)["server_code_changed"])

    def test_a_changed_code_file_is_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "server.py")
            with open(p, "w") as fh:
                fh.write("a")
            saved_code, saved_start = ui._SERVER_CODE, ui._CODE_AT_START
            try:
                ui._SERVER_CODE = [p]
                ui._CODE_AT_START = ui._code_signature()
                self.assertFalse(ui.build_status(ROOT)["server_code_changed"])
                time.sleep(0.01)
                with open(p, "w") as fh:
                    fh.write("ab")
                self.assertTrue(ui.build_status(ROOT)["server_code_changed"])
            finally:
                ui._SERVER_CODE, ui._CODE_AT_START = saved_code, saved_start

    def test_the_page_shows_a_restart_banner(self):
        with open(os.path.join(ROOT, "ui", "app.js"), encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn("st.server_code_changed", js)
        self.assertIn("Restart it", js)


if __name__ == "__main__":
    unittest.main()
