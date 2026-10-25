"""Live application API (/api/live, /api/agent) and the Dashboard entry point (ui/server.py, ui/app.js)."""
import builtins
import importlib.util
import json
import os
import pathlib
import re
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("evirep_ui_app", os.path.join(ROOT, "ui", "server.py"))
ui = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ui)


@unittest.skipUnless(os.path.exists(os.path.join(ROOT, "data", "run_manifest.json")), "needs the run manifest")
class TestLiveSnapshot(unittest.TestCase):
    def test_states_come_from_the_runner(self):
        live = ui.build_live(ROOT)
        st = ui._runs.status(ROOT, ui.STAGES)
        self.assertEqual({s["id"]: s["status"] for s in live["stages"]}, {k: v["status"] for k, v in st.items()})
        self.assertEqual(sum(live["overall"]["counts"].values()), len(ui.STAGES))
        self.assertEqual(len(live["agents"]), 8)
        self.assertEqual({a["id"] for a in live["agents"]}, {f"10{c}" for c in "abcdefgh"})
        order = [s["id"] for s in live["stages"]]                     # dependency order
        for s in ui.STAGES:
            for d in s["depends_on"]:
                self.assertLess(order.index(d), order.index(s["id"]))
        kinds = {a["id"]: a["kind"] for a in live["agents"]}
        self.assertEqual(kinds["10h"], "annotation")                   # agents stay distinct, not all VPS dimensions
        self.assertEqual({k for k, v in kinds.items() if v == "diagnostic"}, {"10a", "10d", "10e"})

    def test_live_payload_never_reads_documentation(self):
        opened, real_open = [], builtins.open

        def spy(file, *a, **k):
            opened.append(str(file))
            return real_open(file, *a, **k)
        builtins.open = spy
        try:
            ui._ENV_CACHE.clear()
            ui.build_live(ROOT)
        finally:
            builtins.open = real_open
        self.assertFalse([f for f in opened if f.endswith(".md")], "the live state must not come from Markdown")

    def test_agent_detail_and_unknown_agent(self):
        d = ui.build_agent_detail(ROOT, "10g")
        self.assertEqual([x["id"] for x in d["stages"]], ui.AGENT_STAGES["10g"])
        self.assertTrue(d["envelope"]["present"])
        self.assertIn("matches_last_success", d["stages"][-1]["inputs"][0])
        self.assertIsNone(ui.build_agent_detail(ROOT, "10z"))


class TestLiveSnapshotEdgeStates(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="evirep_liveapp_")
        os.makedirs(os.path.join(self.root, "data"))

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_nothing_run_is_not_current(self):
        live = ui.build_live(self.root)
        self.assertEqual(live["overall"]["state"], "INCOMPLETE")
        self.assertTrue(all(a["coverage_line"] == "output unavailable" for a in live["agents"]))

    def test_corrupt_manifest_is_unknown(self):
        with open(os.path.join(self.root, "data", "run_manifest.json"), "w") as fh:
            fh.write("{bad")
        live = ui.build_live(self.root)
        self.assertEqual(live["overall"]["state"], "UNKNOWN")
        self.assertTrue(live["manifest_error"])


class TestNextActions(unittest.TestCase):
    """Next-step guidance is derived only from tracked state; owner-only work is labelled as such."""

    def st(self, **over):
        base = {"id": "x", "status": "SUCCESS", "reasons": [], "warnings": [], "latest_attempt_failed": False}
        return {k: {**base, "id": k, **v} for k, v in over.items()}

    def test_cases(self):
        pol = {"10h": "ALLOWED", "06": "REFUSED", "05h": "CONFIRM"}
        na = ui._next_actions
        self.assertEqual(na(self.st(a={}), pol, None)[0]["level"], "ok")
        self.assertIn("check-manifest", na({}, pol, "unreadable")[0]["text"])
        r = na(self.st(**{"10h": {"status": "RUNNING"}}), pol, None)
        self.assertTrue(r[0]["text"].startswith("Wait: 10h"))
        r = na(self.st(**{"10h": {"status": "STALE", "latest_attempt_failed": True}}), pol, None)
        self.assertEqual((r[0]["who"], r[0]["stage"]), ("anyone", "10h"))
        r = na(self.st(**{"06": {"status": "STALE"}}), pol, None)
        self.assertEqual(r[0]["who"], "owner")
        r = na(self.st(**{"10h": {"status": "STALE"}}), pol, None)
        self.assertIn("Run all permitted stages", r[0]["text"])
        r = na(self.st(**{"10h": {"status": "FAILED", "latest_attempt_failed": True,
                                  "reasons": ["its stage process (pid 9) is still running orphaned: stop it"]}}), pol, None)
        self.assertTrue(any("--restore 10h" in a["text"] for a in r))
        r = na(self.st(**{"10h": {"status": "STALE"}, "05h": {"status": "RUNNING"}}), pol, None)
        self.assertFalse(any("Run all" in a["text"] for a in r))               # never suggest a launch while busy


class TestDashboardIsTheEntryPoint(unittest.TestCase):
    def test_default_route_and_nav(self):
        js = pathlib.Path(os.path.join(ROOT, "ui", "app.js")).read_text()
        html = pathlib.Path(os.path.join(ROOT, "ui", "index.html")).read_text()
        # 2026-10-20 (biomedical UX pass): the researcher Overview is the entry point; the live operational
        # dashboard is the Run Center, still re-rendered on every poll; five primary sections in a fixed order.
        self.assertIn('return {view: VIEWS[view] ? view : "overview", arg};', js)
        nav = html[html.index('<nav id="nav"'):html.index("</nav>")]
        self.assertEqual(re.findall(r'data-view="(\w+)"', nav), ["overview", "drugs", "evidence", "validation", "run"])
        self.assertIn('LIVE_VIEWS = new Set(["dashboard", "run", "agent", "live"])', js)
        self.assertIn("run: viewDashboard, dashboard: viewDashboard", js)          # old #dashboard links still work
        dash = js[js.index("async function viewDashboard"):js.index("async function viewAgent")]
        self.assertNotIn("/api/risks", dash)                             # no Markdown-derived content on the dashboard
        self.assertNotRegex(dash, r"%\s*(complete|done)|<progress")      # no fabricated progress


if __name__ == "__main__":
    unittest.main()
