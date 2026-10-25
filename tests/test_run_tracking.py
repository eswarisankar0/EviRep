"""
Run tracking, dependency-aware freshness and safe publication (scripts/run_stage.py).
Every test uses a temporary root and tiny stand-in stage scripts; the real data/ is never touched.
"""

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import textwrap
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("rs", os.path.join(ROOT, "scripts", "run_stage.py"))
rs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rs)


def script(root, name, body):
    p = os.path.join(root, name)
    with open(p, "w") as fh:
        fh.write(textwrap.dedent(body))
    return p


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="evirep_runs_")
        os.makedirs(os.path.join(self.root, "data"))
        self.w("data/src.csv", "x\n1\n")
        a = script(self.root, "a.py", """
            import pandas as pd
            pd.DataFrame({"y": pd.read_csv("data/src.csv")["x"] * 2}).to_csv("data/a.csv", index=False)
        """)
        b = script(self.root, "b.py", """
            import os, sys, pandas as pd
            if os.path.exists("FAIL_B"):
                open("data/b.csv", "w").write("")       # broken output, then a failure exit
                sys.exit(3)
            pd.DataFrame({"z": pd.read_csv("data/a.csv")["y"] + 1}).to_csv("data/b.csv", index=False)
        """)
        self.stages = [
            {"id": "A", "name": "A", "script": a, "depends_on": [], "inputs": ["data/src.csv"], "outputs": ["data/a.csv"]},
            {"id": "B", "name": "B", "script": b, "depends_on": ["A"], "inputs": ["data/a.csv"], "outputs": ["data/b.csv"]},
        ]

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def w(self, rel, text):
        with open(os.path.join(self.root, rel), "w") as fh:
            fh.write(text)

    def r(self, rel):
        with open(os.path.join(self.root, rel)) as fh:
            return fh.read()

    def run_(self, sid):
        return rs.run(sid, self.root, stages=self.stages)

    def st(self):
        return rs.status(self.root, self.stages)


class TestRuns(Base):
    def test_success_records_metadata(self):
        rec = self.run_("A")
        self.assertEqual((rec["status"], rec["exit_code"], rec["validation_ok"]), ("SUCCESS", 0, True))
        m = json.loads(self.r("data/run_manifest.json"))
        e = m["stages"]["A"]
        self.assertEqual(e["last_success"]["run_id"], rec["run_id"])
        self.assertEqual(e["last_success"]["inputs"]["data/src.csv"]["md5"], rs.fingerprint(self.root, "data/src.csv")["md5"])
        self.assertTrue(e["last_success"]["finished_utc"] >= e["last_success"]["started_utc"])
        self.assertTrue(self.st()["A"]["fresh"])
        self.assertEqual(self.st()["B"]["status"], "NOT_RUN")

    def test_upstream_change_invalidates_only_dependants(self):
        self.run_("A"), self.run_("B")
        self.assertEqual({k: v["status"] for k, v in self.st().items()}, {"A": "SUCCESS", "B": "SUCCESS"})
        self.w("data/src.csv", "x\n5\n")
        s = self.st()
        self.assertEqual((s["A"]["status"], s["B"]["status"]), ("STALE", "STALE"))
        self.assertIn("upstream stage stale: A", s["B"]["reasons"])
        self.run_("A")
        s = self.st()
        self.assertEqual(s["A"]["status"], "SUCCESS")
        self.assertEqual(s["B"]["status"], "STALE")                  # its input data/a.csv changed
        self.assertIn("input changed since last success: data/a.csv", s["B"]["reasons"])

    def test_unchanged_rewrite_does_not_invalidate(self):
        self.run_("A"), self.run_("B")
        self.run_("A")                                               # same content, new mtime
        self.assertEqual(self.st()["B"]["status"], "SUCCESS")

    def test_failure_keeps_last_good_output_and_is_not_fresh(self):
        self.run_("A"), self.run_("B")
        good = self.r("data/b.csv")
        first = json.loads(self.r("data/run_manifest.json"))["stages"]["B"]["last_success"]["run_id"]
        self.w("FAIL_B", "")
        rec = self.run_("B")
        self.assertEqual((rec["status"], rec["exit_code"]), ("FAILED", 3))
        self.assertEqual(self.r("data/b.csv"), good)                 # restored, not deleted
        self.assertTrue(os.path.exists(os.path.join(self.root, rec["run_dir"], "failed", "b.csv")))
        s = self.st()["B"]
        self.assertEqual((s["status"], s["fresh"], s["retained_run_id"]), ("FAILED", False, first))
        self.assertTrue(any("showing retained result" in x for x in s["reasons"]))

    def test_stale_and_failed_are_distinct(self):
        self.run_("A"), self.run_("B")
        self.w("data/src.csv", "x\n9\n")
        self.w("FAIL_B", "")
        self.run_("B")
        s = self.st()["B"]
        self.assertEqual(s["status"], "STALE")                       # stale takes precedence, failure still reported
        self.assertTrue(any("failed" in x for x in s["reasons"]))

    def test_output_edited_outside_a_run_is_modified(self):
        self.run_("A")
        self.w("data/a.csv", "y\n999\n")
        self.assertEqual(self.st()["A"]["status"], "MODIFIED")

    def test_partial_exit_for_resumable_stages(self):
        p = script(self.root, "p.py", """
            import sys
            open("data/p.csv", "w").write("c\\n1\\n")
            sys.exit(1)
        """)
        stages = [{"id": "05", "name": "p", "script": p, "depends_on": [], "inputs": [], "outputs": ["data/p.csv"]}]
        rec = rs.run("05", self.root, stages=stages)
        self.assertEqual(rec["status"], "PARTIAL")
        self.assertEqual(rs.status(self.root, stages)["05"]["status"], "PARTIAL")

    def test_crash_of_resumable_stage_is_failed_not_partial(self):
        # A traceback also exits 1. Without new outputs the previous files would validate and the
        # crash would be recorded as a fresh PARTIAL success built on the new inputs.
        self.w("data/p.csv", "c\n1\n")
        p = script(self.root, "p.py", """
            raise RuntimeError("connector down")
        """)
        stages = [{"id": "05", "name": "p", "script": p, "depends_on": [], "inputs": ["data/src.csv"], "outputs": ["data/p.csv"]}]
        rs.adopt(self.root, stages)
        self.w("data/src.csv", "x\n7\n")
        rec = rs.run("05", self.root, stages=stages)
        self.assertEqual(rec["status"], "FAILED")
        s = rs.status(self.root, stages)["05"]
        self.assertFalse(s["fresh"])
        self.assertTrue(s["latest_attempt_failed"])

    def test_resumable_stage_other_nonzero_exit_is_failed(self):
        p = script(self.root, "p.py", """
            import sys
            open("data/p.csv", "w").write("c\\n1\\n")
            sys.exit(2)
        """)
        stages = [{"id": "04", "name": "p", "script": p, "depends_on": [], "inputs": [], "outputs": ["data/p.csv"]}]
        self.assertEqual(rs.run("04", self.root, stages=stages)["status"], "FAILED")

    def test_exit_zero_without_rewriting_outputs_is_not_full_success(self):
        self.w("data/q.csv", "c\n1\n")
        q = script(self.root, "q.py", "pass\n")
        stages = [{"id": "Q", "name": "q", "script": q, "depends_on": [], "inputs": [], "outputs": ["data/q.csv"]}]
        rec = rs.run("Q", self.root, stages=stages)
        self.assertEqual(rec["status"], "PARTIAL")
        self.assertIn("NOT_REWRITTEN", [d["code"] for d in rec["diagnostics"]])

    def test_deleted_output_is_missing_not_modified(self):
        self.run_("A")
        os.remove(os.path.join(self.root, "data/a.csv"))
        s = self.st()["A"]
        self.assertEqual((s["status"], s["fresh"]), ("MISSING", False))
        self.assertIn("data/a.csv", " ".join(s["reasons"]))

    def test_skip_fresh_does_no_work_on_identical_inputs(self):
        first = self.run_("A")
        again = rs.run("A", self.root, stages=self.stages, skip_fresh=True)
        self.assertEqual((again["status"], again["run_id"]), ("SKIPPED_FRESH", first["run_id"]))
        m = json.loads(self.r("data/run_manifest.json"))
        self.assertEqual(m["stages"]["A"]["last_attempt"]["run_id"], first["run_id"])   # nothing recorded
        self.w("data/src.csv", "x\n4\n")
        self.assertNotEqual(rs.run("A", self.root, stages=self.stages, skip_fresh=True)["run_id"], first["run_id"])

    def test_code_change_after_success_is_a_warning_not_stale(self):
        self.run_("A")
        self.assertEqual(self.st()["A"]["warnings"], [])
        with open(self.stages[0]["script"], "a") as fh:
            fh.write("# edited\n")
        s = self.st()["A"]
        self.assertEqual(s["status"], "SUCCESS")                      # outputs still match their inputs
        self.assertTrue(any("stage code changed" in w for w in s["warnings"]))
        self.run_("A")
        self.assertEqual(self.st()["A"]["warnings"], [])

    def test_interrupted_attempt_is_failed(self):
        self.run_("A")
        m = json.loads(self.r("data/run_manifest.json"))
        m["stages"]["A"]["last_attempt"] = {"run_id": "x", "status": "RUNNING", "pid": 999999}
        self.w("data/run_manifest.json", json.dumps(m))
        s = self.st()["A"]
        self.assertEqual(s["status"], "FAILED")
        self.assertIn("interrupted", " ".join(s["reasons"]))

    def test_status_reports_duration_log_upstream_and_elapsed(self):
        self.run_("A")
        self.run_("B")
        st = self.st()
        b = st["B"]
        self.assertIsInstance(b["last_success"]["duration_s"], int)
        self.assertTrue(b["last_success"]["log"].endswith("/log.txt"))
        self.assertTrue(os.path.exists(os.path.join(self.root, b["last_success"]["log"])))
        self.assertEqual(b["upstream"], [{"id": "A", "status": "SUCCESS"}])
        self.assertIsNone(b["elapsed_s"])
        m = json.loads(self.r("data/run_manifest.json"))
        m["stages"]["A"]["last_attempt"] = {"run_id": "x", "status": "RUNNING", "pid": os.getpid(),
                                            "started_utc": "2000-01-01T00:00:00+00:00"}
        self.w("data/run_manifest.json", json.dumps(m))
        a = self.st()["A"]
        self.assertEqual(a["status"], "RUNNING")
        self.assertGreater(a["elapsed_s"], 0)
        self.assertIsNone(a["last_attempt"]["duration_s"])       # not finished: no duration is claimed

    def test_input_declared_after_last_success_is_flagged_not_silently_fresh(self):
        """R-02 (2026-10-20): inputs added to the registry after a stage's last success were never compared, so a
        change to them left the stage fresh. Existing ones are now reported as untracked (warning); an optional
        declared input that does not exist stays silent."""
        self.run_("A")
        self.w("data/extra.csv", "e\n1\n")
        self.stages[0]["inputs"] = ["data/src.csv", "data/extra.csv", "data/optional_absent.csv"]
        a = self.st()["A"]
        self.assertTrue(any("data/extra.csv" in w and "not fingerprinted" in w for w in a["warnings"]), a["warnings"])
        self.assertFalse(any("optional_absent" in w for w in a["warnings"]))
        self.run_("A")                                   # a re-run records it; the warning clears
        self.assertEqual(self.st()["A"]["warnings"], [])
        self.w("data/extra.csv", "e\n2\n")              # and from now on a change makes it STALE
        self.assertEqual(self.st()["A"]["status"], "STALE")

    def test_running_stage_reports_last_log_activity(self):
        self.run_("A")
        rd = os.path.join(self.root, "data", "_runs", "live-A")
        os.makedirs(rd)
        with open(os.path.join(rd, "log.txt"), "w") as fh:
            fh.write("fetching batch 3/10\n\n")
        m = json.loads(self.r("data/run_manifest.json"))
        m["stages"]["A"]["last_attempt"] = {"run_id": "live-A", "status": "RUNNING", "pid": os.getpid(),
                                            "run_dir": "data/_runs/live-A", "started_utc": rs.now()}
        self.w("data/run_manifest.json", json.dumps(m))
        a = self.st()["A"]
        self.assertEqual(a["last_activity"]["line"], "fetching batch 3/10")
        self.assertGreaterEqual(a["last_activity"]["log_age_s"], 0)
        self.assertIsNone(self.st()["B"]["last_activity"])

    def test_truncated_and_invalid_utf8_log_is_shown_not_crashed(self):
        self.run_("A")
        rd = os.path.join(self.root, "data", "_runs", "live-T")
        os.makedirs(rd)
        with open(os.path.join(rd, "log.txt"), "wb") as fh:
            fh.write(b"step one\nhalf a multibyte char: \xe2\x82")          # truncated mid-character, no newline
        m = json.loads(self.r("data/run_manifest.json"))
        m["stages"]["A"]["last_attempt"] = {"run_id": "live-T", "status": "RUNNING", "pid": os.getpid(),
                                            "run_dir": "data/_runs/live-T", "started_utc": rs.now()}
        self.w("data/run_manifest.json", json.dumps(m))
        line = self.st()["A"]["last_activity"]["line"]
        self.assertTrue(line.startswith("half a multibyte char:"))
        self.assertIn("\ufffd", line)                                     # replaced, not an exception

    def test_code_fingerprint_recorded_flag(self):
        self.run_("A")
        self.assertTrue(self.st()["A"]["code_fingerprint_recorded"])
        m = json.loads(self.r("data/run_manifest.json"))
        m["stages"]["A"]["last_success"].pop("script_md5")              # as for runs before C-78 / ADOPTED
        self.w("data/run_manifest.json", json.dumps(m))
        self.assertFalse(self.st()["A"]["code_fingerprint_recorded"])
        self.assertFalse(self.st()["B"]["code_fingerprint_recorded"])   # never run

    def test_output_declared_after_last_success_is_flagged(self):
        self.run_("A")
        self.w("data/a_extra.csv", "x\n")
        self.stages[0]["outputs"] = ["data/a.csv", "data/a_extra.csv"]
        self.assertTrue(any("data/a_extra.csv" in w and "output" in w for w in self.st()["A"]["warnings"]))

    def test_adopt_records_existing_outputs(self):
        self.w("data/a.csv", "y\n2\n")
        self.assertEqual(self.st()["A"]["status"], "UNTRACKED")
        self.assertEqual(rs.adopt(self.root, self.stages), ["A"])
        self.assertEqual(self.st()["A"]["status"], "ADOPTED")


class TestCorruptManifest(Base):
    """R-04 (2026-10-20): a corrupt manifest raised a raw JSONDecodeError (dashboard HTTP 500, CLI traceback). It
    must yield UNKNOWN (never fresh), refuse runs without overwriting the file, and be diagnosable read-only."""

    def setUp(self):
        super().setUp()
        self.run_("A")
        self.w("data/run_manifest.json", "{not json")

    def test_status_is_unknown_never_fresh(self):
        st = self.st()
        self.assertEqual({v["status"] for v in st.values()}, {"UNKNOWN"})
        self.assertFalse(any(v["fresh"] for v in st.values()))
        self.assertIn("unreadable", st["A"]["reasons"][0])

    def test_run_refused_and_manifest_preserved(self):
        runs = set(os.listdir(os.path.join(self.root, "data", "_runs")))
        before = self.r("data/a.csv")
        with self.assertRaises(rs.ManifestError):
            self.run_("A")
        self.assertEqual(self.r("data/run_manifest.json"), "{not json")              # evidence kept
        self.assertEqual(set(os.listdir(os.path.join(self.root, "data", "_runs"))), runs)
        self.assertEqual(self.r("data/a.csv"), before)

    def test_cli_exit_codes_and_check(self):
        orig = rs.load_stages
        rs.load_stages = lambda: self.stages
        try:
            self.assertEqual(rs.main(["A", "--root", self.root]), 2)
            self.assertEqual(rs.main(["--check-manifest", "--root", self.root]), 2)
            self.w("data/run_manifest.json", "[]")                                       # valid JSON, wrong shape
            self.assertEqual(rs.check_manifest(self.root, self.stages)[0], False)
        finally:
            rs.load_stages = orig

    def test_check_reports_missing_run_directory(self):
        os.remove(os.path.join(self.root, "data", "run_manifest.json"))
        rec = self.run_("A")
        shutil.rmtree(os.path.join(self.root, rec["run_dir"]))
        ok, problems, _ = rs.check_manifest(self.root, self.stages)
        self.assertFalse(ok)
        self.assertTrue(any("run directory missing" in p for p in problems), problems)


class TestMalformedManifestStructure(Base):
    """D1 (2026-10-20 runtime audit): valid JSON with the wrong structure raised AttributeError in status(), so the
    dashboard returned HTTP 500. Every malformed shape must become ManifestError -> UNKNOWN, never a crash."""

    SHAPES = {
        "stage record is a string": {"stages": {"A": "oops"}, "history": []},
        "last_success is a list": {"stages": {"A": {"last_success": [1, 2]}}, "history": []},
        "last_attempt is a number": {"stages": {"A": {"last_attempt": 3}}, "history": []},
        "recorded outputs not an object": {"stages": {"A": {"last_success": {"run_id": "r", "status": "SUCCESS",
                                                                            "outputs": ["x"]}}}, "history": []},
        "history entry is a string": {"stages": {}, "history": ["x"]},
        "stages is a list": {"stages": [], "history": []},
    }

    def test_every_shape_is_unknown_with_a_reason(self):
        for name, m in self.SHAPES.items():
            self.w("data/run_manifest.json", json.dumps(m))
            st = self.st()
            self.assertEqual({v["status"] for v in st.values()}, {"UNKNOWN"}, name)
            self.assertIn("unexpected structure", st["A"]["reasons"][0], name)
            ok, problems, _ = rs.check_manifest(self.root, self.stages)
            self.assertFalse(ok, name)
            with self.assertRaises(rs.ManifestError, msg=name):
                self.run_("A")


class TestStageTimeout(Base):
    """D4 (2026-10-20 runtime audit): a hung stage stayed RUNNING forever. With timeout_s the runner kills its own
    child, records FAILED with a TIMEOUT diagnostic and restores the previous outputs."""

    def test_hung_stage_is_killed_failed_and_restored(self):
        self.run_("A")
        good = self.r("data/a.csv")
        self.w("data/src.csv", "x\n7\n")
        hang = script(self.root, "hang.py", """
            open("data/a.csv", "w").write("half-written")
            import time
            time.sleep(60)
        """)
        self.stages[0].update(script=hang, timeout_s=1)
        t0 = time.time()
        rec = self.run_("A")
        self.assertLess(time.time() - t0, 20)
        self.assertEqual(rec["status"], "FAILED")
        self.assertIn("TIMEOUT", [d["code"] for d in rec["diagnostics"]])
        self.assertEqual(self.r("data/a.csv"), good)                       # previous output restored
        st = self.st()["A"]
        self.assertEqual(st["status"], "STALE")                           # input changed; never shown as running
        self.assertTrue(st["latest_attempt_failed"])
        with open(os.path.join(self.root, rec["run_dir"], "log.txt")) as fh:
            self.assertIn("TIMEOUT", fh.read())

    def test_launchable_stages_have_a_timeout(self):
        import importlib.util as ilu
        spec = ilu.spec_from_file_location("srv_t", os.path.join(ROOT, "ui", "server.py"))
        srv = ilu.module_from_spec(spec)
        spec.loader.exec_module(srv)
        for st in srv.STAGES:
            if srv.live_runs.policy(st)[0] != "REFUSED":
                self.assertTrue(st.get("timeout_s"), st["id"])


class TestRunnerKilledMidStage(Base):
    """D6 (2026-10-20 runtime audit): a runner killed mid-stage left a half-written output reported as an outside
    edit, its stage process running untracked, and no way back to the validated output."""

    def test_orphan_reported_restore_refused_then_verified(self):
        import signal
        import subprocess
        self.run_("A")
        good = self.r("data/a.csv")
        self.w("data/src.csv", "x\n8\n")
        slow = script(self.root, "slow.py", """
            import time
            open("data/a.csv", "w").write("half-written")
            time.sleep(60)
        """)
        self.stages[0]["script"] = slow
        with open(os.path.join(self.root, "stages.json"), "w") as fh:
            json.dump(self.stages, fh)
        drv = script(self.root, "drv.py", f"""
            import importlib.util, json
            spec = importlib.util.spec_from_file_location("rs", {os.path.join(ROOT, "scripts", "run_stage.py")!r})
            rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
            rs.run("A", {self.root!r}, stages=json.load(open({os.path.join(self.root, "stages.json")!r})))
        """)
        runner = subprocess.Popen([sys.executable, drv])
        end = time.time() + 20
        while time.time() < end and not (json.loads(self.r("data/run_manifest.json"))["stages"]["A"]
                                         .get("last_attempt", {}).get("child_pid")):
            time.sleep(0.05)
        time.sleep(0.5)
        os.kill(runner.pid, signal.SIGKILL)
        runner.wait()
        la = json.loads(self.r("data/run_manifest.json"))["stages"]["A"]["last_attempt"]
        child = la["child_pid"]
        try:
            st = self.st()["A"]
            self.assertTrue(st["latest_attempt_failed"])
            why = " ".join(st["reasons"])
            self.assertIn("still running orphaned", why)
            self.assertIn("--restore A", why)
            self.assertIn("not an outside edit", why)
            ok, msg = rs.restore("A", self.root, self.stages)
            self.assertFalse(ok)
            self.assertIn("still alive", msg)
        finally:
            os.kill(child, signal.SIGKILL)
            time.sleep(0.3)
        self.assertEqual(self.r("data/a.csv"), "half-written")
        ok, msg = rs.restore("A", self.root, self.stages)
        self.assertTrue(ok, msg)
        self.assertEqual(self.r("data/a.csv"), good)                       # byte-identical validated output
        st = self.st()["A"]
        self.assertEqual(st["status"], "STALE")                           # src changed: honest, not "current"
        self.assertTrue(st["latest_attempt_failed"])
        ok, msg = rs.restore("A", self.root, self.stages)                   # idempotent: nothing left to restore
        self.assertIn("restored nothing", msg)

    def test_restore_refuses_a_copy_that_does_not_match(self):
        self.run_("A")
        self.w("data/src.csv", "x\n9\n")
        self.stages[0]["script"] = script(self.root, "bad.py", "open('data/a.csv','w').write('bad'); import sys; sys.exit(1)\n")
        rec = self.run_("A")                                               # FAILED: runner already restored
        self.assertEqual(rec["status"], "FAILED")
        with open(os.path.join(self.root, rec["run_dir"], "previous", "a.csv"), "w") as fh:
            fh.write("tampered")
        self.w("data/a.csv", "damaged")
        ok, msg = rs.restore("A", self.root, self.stages)
        self.assertFalse(ok)
        self.assertIn("does not match", msg)
        self.assertEqual(self.r("data/a.csv"), "damaged")                  # nothing written


class TestBackupLimit(Base):
    """R-05 (2026-10-20): outputs above the backup limit were overwritten in place with only a NO_BACKUP warning,
    so a failed run could not restore them (stage 01's 89 MB edge list exceeded the old 50 MB limit)."""

    def test_unrestorable_run_is_refused_before_anything_is_written(self):
        self.run_("A")
        before_manifest, before_out = self.r("data/run_manifest.json"), self.r("data/a.csv")
        runs = set(os.listdir(os.path.join(self.root, "data", "_runs")))
        orig = rs.BACKUP_LIMIT
        rs.BACKUP_LIMIT = 1                                   # every existing output is now "too large"
        try:
            with self.assertRaises(rs.UnsafeRun):
                self.run_("A")
        finally:
            rs.BACKUP_LIMIT = orig
        self.assertEqual(self.r("data/run_manifest.json"), before_manifest)
        self.assertEqual(self.r("data/a.csv"), before_out)
        self.assertEqual(set(os.listdir(os.path.join(self.root, "data", "_runs"))), runs)

    def test_limit_covers_the_largest_registered_output(self):
        self.assertGreaterEqual(rs.BACKUP_LIMIT, 89 * 1024 * 1024 * 2)    # stage 01 edge list with headroom

    def test_first_run_without_existing_outputs_is_allowed(self):
        orig = rs.BACKUP_LIMIT
        rs.BACKUP_LIMIT = 1
        try:
            self.assertEqual(self.run_("A")["status"], "SUCCESS")     # nothing to restore, nothing at risk
        finally:
            rs.BACKUP_LIMIT = orig


class TestSequence(Base):
    """run_sequence: dependency order, skip fresh, BLOCKED dependants after a failure (Live Pipeline 'run all')."""

    def test_runs_in_dependency_order_then_skips_fresh(self):
        res = rs.run_sequence(["B", "A"], self.root, stages=self.stages)
        self.assertEqual([(r["stage"], r["status"]) for r in res], [("A", "SUCCESS"), ("B", "SUCCESS")])
        res = rs.run_sequence(["A", "B"], self.root, stages=self.stages)
        self.assertEqual([r["status"] for r in res], ["SKIPPED_FRESH", "SKIPPED_FRESH"])

    def test_failure_blocks_dependants_and_keeps_their_outputs(self):
        rs.run_sequence(["A", "B"], self.root, stages=self.stages)
        b_before = self.r("data/b.csv")
        self.w("data/src.csv", "x\n5\n")                                     # A must recompute
        self.stages[0]["script"] = script(self.root, "a_fail.py", "import sys; sys.exit(2)\n")
        res = rs.run_sequence(["A", "B"], self.root, stages=self.stages)
        self.assertEqual([r["status"] for r in res], ["FAILED", "BLOCKED"])
        self.assertIn("upstream", res[1]["detail"])
        self.assertEqual(self.r("data/b.csv"), b_before)                    # B never started

    def test_refused_stage_is_reported_not_raised(self):
        self.run_("A")
        m = json.loads(self.r("data/run_manifest.json"))
        m["stages"]["A"]["last_attempt"] = {"run_id": "live", "status": "RUNNING", "pid": os.getpid()}
        self.w("data/run_manifest.json", json.dumps(m))
        self.w("data/src.csv", "x\n9\n")
        res = rs.run_sequence(["A", "B"], self.root, stages=self.stages, skip_fresh=False)
        self.assertEqual([r["status"] for r in res], ["REFUSED", "BLOCKED"])


class TestAttest(Base):
    """Code-fingerprint attestation for runs without one (ADOPTED / pre-C-78): only by a byte-identical isolated
    reproduction with the current script; outputs untouched."""

    def setUp(self):
        super().setUp()
        self.w("data/a.csv", "y\n2\n")
        rs.adopt(self.root, self.stages)                          # live: adopted, no code fingerprint
        self.copy = tempfile.mkdtemp(prefix="evirep_attest_copy_")
        shutil.copytree(os.path.join(self.root, "data"), os.path.join(self.copy, "data"), dirs_exist_ok=True)
        os.remove(os.path.join(self.copy, "data", "run_manifest.json"))

    def tearDown(self):
        shutil.rmtree(self.copy, ignore_errors=True)
        super().tearDown()

    def test_identical_reproduction_attests_without_touching_outputs(self):
        rs.run("A", self.copy, stages=self.stages)               # current code reproduces y=2 from x=1
        before = self.r("data/a.csv")
        self.assertFalse(self.st()["A"]["code_fingerprint_recorded"])
        ok, why = rs.attest("A", self.root, self.copy, self.stages)
        self.assertTrue(ok, why)
        self.assertEqual(self.r("data/a.csv"), before)
        a = self.st()["A"]
        self.assertTrue(a["code_fingerprint_recorded"])
        self.assertEqual(a["status"], "ADOPTED")
        m = json.loads(self.r("data/run_manifest.json"))
        self.assertIn("copy_run_id", m["stages"]["A"]["last_success"]["code_fingerprint_attested"])
        self.assertFalse(rs.attest("A", self.root, self.copy, self.stages)[0])          # never twice

    def test_refused_when_outputs_differ_or_code_differs(self):
        rs.run("A", self.copy, stages=self.stages)
        self.w("data/a.csv", "y\n3\n")                           # live output is not what the code produces
        rs.adopt(self.root, self.stages)
        ok, why = rs.attest("A", self.root, self.copy, self.stages)
        self.assertFalse(ok)
        self.assertIn("differs", why)
        self.w("data/a.csv", "y\n2\n")
        self.stages[0]["script"] = script(self.root, "a2.py", "print('other code')\n")
        ok, why = rs.attest("A", self.root, self.copy, self.stages)
        self.assertFalse(ok)
        self.assertIn("different code", why)


class TestConcurrentLaunch(Base):
    """A launch must be refused while a conflicting attempt is alive (same stage, upstream or downstream)."""

    def setUp(self):
        super().setUp()
        self.w("data/c_src.csv", "q\n1\n")
        c = script(self.root, "c.py", """
            open("data/c.csv", "w").write("q\\n1\\n")
        """)
        self.stages.append({"id": "C", "name": "C", "script": c, "depends_on": [], "inputs": ["data/c_src.csv"],
                            "outputs": ["data/c.csv"]})
        self.run_("A")

    def mark_running(self, sid, pid):
        m = json.loads(self.r("data/run_manifest.json"))
        m["stages"].setdefault(sid, {})["last_attempt"] = {"run_id": f"live-{sid}", "status": "RUNNING", "pid": pid}
        self.w("data/run_manifest.json", json.dumps(m))

    def assert_refused(self, sid):
        before = self.r("data/run_manifest.json")
        runs = set(os.listdir(os.path.join(self.root, "data", "_runs")))
        with self.assertRaises(rs.StageBusy):
            self.run_(sid)
        self.assertEqual(self.r("data/run_manifest.json"), before)            # nothing recorded
        self.assertEqual(set(os.listdir(os.path.join(self.root, "data", "_runs"))), runs)   # no run dir

    def test_same_stage_refused_while_alive(self):
        self.mark_running("A", os.getpid())
        self.assert_refused("A")
        self.assertEqual(self.st()["A"]["status"], "RUNNING")

    def test_downstream_refused_while_upstream_runs(self):
        self.mark_running("A", os.getpid())
        self.assert_refused("B")

    def test_upstream_refused_while_downstream_runs(self):
        self.mark_running("B", os.getpid())
        self.assert_refused("A")

    def test_unrelated_stage_may_run(self):
        self.mark_running("A", os.getpid())
        self.assertEqual(self.run_("C")["status"], "SUCCESS")

    def test_dead_attempt_does_not_block(self):
        self.mark_running("A", 999999)
        self.assertEqual(self.run_("A")["status"], "SUCCESS")

    def test_cli_exit_code(self):
        self.mark_running("A", os.getpid())
        orig = rs.load_stages
        rs.load_stages = lambda: self.stages
        try:
            self.assertEqual(rs.main(["A", "--root", self.root]), 3)
        finally:
            rs.load_stages = orig


class TestPropagationRules(Base):
    """Found by the live browser workflow 2026-10-15 (E-024)."""

    def test_modified_upstream_does_not_make_a_consumer_stale(self):
        self.run_("A")
        self.w("data/a.csv", "y\n7\n")                     # hand edit of A's output
        self.run_("B")                                     # B consumes the edited file
        s = self.st()
        self.assertEqual(s["A"]["status"], "MODIFIED")
        self.assertEqual(s["B"]["status"], "SUCCESS")       # consistent with what it read ...
        self.assertTrue(s["B"]["unvalidated_upstream"])     # ... but flagged as built on unvalidated input
        self.assertIn("unvalidated", s["B"]["warnings"][0])

    def test_failed_attempt_flag_survives_staleness(self):
        self.run_("A"), self.run_("B")
        self.w("data/src.csv", "x\n3\n")
        self.w("FAIL_B", "")
        self.run_("B")
        s = self.st()["B"]
        self.assertEqual(s["status"], "STALE")
        self.assertTrue(s["latest_attempt_failed"])
        self.assertFalse(s["fresh"])


class TestStagedPublication(Base):
    def setUp(self):
        super().setUp()
        s = script(self.root, "s.py", """
            import argparse, os, pandas as pd
            ap = argparse.ArgumentParser(); ap.add_argument("--output-dir"); ap.add_argument("--bad", action="store_true")
            a = ap.parse_args()
            df = pd.DataFrame({"v": [] if a.bad else [1, 2]})
            os.makedirs(a.output_dir, exist_ok=True)
            df.to_csv(os.path.join(a.output_dir, "s.csv"), index=False)
        """)
        self.stages.append({"id": "S", "name": "S", "script": s, "depends_on": [], "inputs": [], "outputs": ["data/s.csv"]})
        self._staged = rs.STAGED
        rs.STAGED = {"S"}

    def tearDown(self):
        rs.STAGED = self._staged
        super().tearDown()

    def test_valid_output_published_and_previous_kept(self):
        self.w("data/s.csv", "v\n0\n")
        rec = self.run_("S")
        self.assertEqual(rec["status"], "SUCCESS")
        self.assertEqual(self.r("data/s.csv"), "v\n1\n2\n")
        self.assertEqual(self.r(os.path.join(rec["run_dir"], "previous", "s.csv")), "v\n0\n")

    def test_invalid_output_never_published(self):
        self.w("data/s.csv", "v\n0\n")
        rec = rs.run("S", self.root, extra_args=["--bad"], stages=self.stages)
        self.assertEqual(rec["status"], "FAILED")
        self.assertEqual(self.r("data/s.csv"), "v\n0\n")            # data/ untouched


class TestRealRegistry(unittest.TestCase):
    def test_graph_is_acyclic_and_covers_vps_and_agents(self):
        stages = rs.load_stages()
        ids = [s["id"] for s in rs._topo(stages)]
        for need in ("06", "eval", "10c", "10f", "10g", "10h"):
            self.assertIn(need, ids)
        pos = {i: n for n, i in enumerate(ids)}
        for s in stages:
            for d in s["depends_on"]:
                self.assertLess(pos[d], pos[s["id"]], f"{d} -> {s['id']}")

    def test_every_consumed_stage_output_is_an_upstream_dependency(self):
        """F-01 (2026-10-20): 10b/10c/10d/10f/10g read data/vps_scores_v2.csv without depending on 06, so a
        STALE 06 left them reported fresh. Every input that another stage produces must be reachable upstream."""
        stages = rs.load_stages()
        by = {s["id"]: s for s in stages}
        producer = {o: s["id"] for s in stages for o in s["outputs"]}

        def upstream(i, seen):
            for d in by[i]["depends_on"]:
                if d not in seen:
                    seen.add(d)
                    upstream(d, seen)
            return seen
        for s in stages:
            up = upstream(s["id"], set())
            for rel in s["inputs"]:
                p = producer.get(rel)
                if p and p != s["id"]:
                    self.assertIn(p, up, f"stage {s['id']} reads {rel} from {p} but does not depend on it")

    def test_every_data_file_a_stage_script_names_is_declared(self):
        """R-03 (2026-10-20): 06, 07, eval, 10f, 10g and 10h read files the registry did not declare, so changes to
        them (human TD-038 roles, 10e output, cached XML) never made the stage STALE. Allowed exceptions are named."""
        import re
        allowed = {
            # side outputs (failure logs) the stage itself writes; consumers declare them as inputs
            "04": {"data/_literature_failures.jsonl"}, "05": {"data/_safety_failures.jsonl"},
            # one script, two registry stages: each mode's files are declared on its own stage
            "10a": {"data/literature_credibility_all.json", "data/literature_papers.jsonl", "data/literature_provenance.csv"},
            "10a-all": {"data/cache/pubmed_efetch_case_claims.xml", "data/conflict_claims_curated.json"},
        }
        for s in rs.load_stages():
            with open(os.path.join(ROOT, s["script"]), encoding="utf-8") as fh:
                src = fh.read()
            named = set(re.findall(r'["\'](data/[A-Za-z0-9_./\-]+\.(?:csv|json|jsonl|xml|png|txt))["\']', src))
            declared = set(s["inputs"]) | set(s["outputs"]) | ({s["checkpoint"]} if s.get("checkpoint") else set())
            missing = named - declared - allowed.get(s["id"], set())
            self.assertFalse(missing, f"stage {s['id']} ({s['script']}) names undeclared files: {sorted(missing)}")

    def test_10h_declares_every_credibility_file_it_globs(self):
        """R-06 (2026-10-20): 10a --curated wrote four case files but declared one; 10h read all of them through
        literature_credibility_*.json while depending only on 10a-all."""
        import glob
        by = {s["id"]: s for s in rs.load_stages()}
        files = {os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "data", "literature_credibility_*.json"))}
        if not files:
            self.skipTest("no persisted credibility files")
        self.assertLessEqual(files, set(by["10h"]["inputs"]))
        self.assertIn("10a", by["10h"]["depends_on"])
        self.assertLessEqual({f for f in files if f not in ("data/literature_credibility_all.json",
                                                            "data/literature_credibility_droxidopa.json")},
                             set(by["10a"]["outputs"]))

    def test_every_output_has_exactly_one_producing_stage(self):
        from collections import Counter
        c = Counter(o for s in rs.load_stages() for o in s["outputs"])
        self.assertEqual([o for o, n in c.items() if n > 1], [])

    def test_stale_vps_propagates_to_every_agent_that_reads_it(self):
        stages = rs.load_stages()
        readers = {s["id"] for s in stages if "data/vps_scores_v2.csv" in s["inputs"]}
        manifest = {"stages": {}}
        root = tempfile.mkdtemp(prefix="evirep_dep_")
        try:
            os.makedirs(os.path.join(root, "data"))
            for s in stages:                                   # every stage recorded as a success on empty files
                for rel in s["outputs"] + s["inputs"]:
                    p = os.path.join(root, rel)
                    os.makedirs(os.path.dirname(p), exist_ok=True)
                    if not os.path.exists(p):
                        open(p, "w").close()
            for s in stages:
                manifest["stages"][s["id"]] = {"last_success": {
                    "run_id": f"r-{s['id']}", "status": "SUCCESS",
                    "inputs": rs._fps(root, s["inputs"]), "outputs": rs._fps(root, s["outputs"])}}
            with open(os.path.join(root, "data", "label_role_exclusions.csv"), "w") as fh:
                fh.write("changed\n")                         # an input of 06 only
            st = rs.status(root, stages, manifest)
            self.assertEqual(st["06"]["status"], "STALE")
            for r in readers - {"06"}:
                self.assertEqual(st[r]["status"], "STALE", r)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


class TestRegistryRunArgs(unittest.TestCase):
    """2026-10-19: stage 04b exited 2 under the runner because its required --compound was not passed."""

    def test_required_arguments_are_supplied_by_the_registry(self):
        import re
        for s in rs.load_stages():
            with open(os.path.join(ROOT, s["script"])) as fh:
                src = fh.read()
            required = re.findall(r'add_argument\("(--[\w-]+)"[^)]*required=True', src)
            for flag in required:
                self.assertIn(flag, s.get("run_args", []), f"{s['id']}: {flag} is required by {s['script']}")
