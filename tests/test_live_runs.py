"""
Live Pipeline run controls (ui/live_runs.py + POST /api/run in ui/server.py).

REAL integration (no mocks): a request launches scripts/run_stage.py as a subprocess against a temporary root; the
runner executes the real stage script, records the attempt in the run manifest, and /api/launches reports the exit.
STAND-IN (clearly marked): one test swaps the runner path for a slow script to hold a launch open and prove that a
second launch is refused while the first is running.
"""
import http.client
import importlib.util
import json
import os
import shutil
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("evirep_ui_live", os.path.join(ROOT, "ui", "server.py"))
ui = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ui)
lr = ui.live_runs


class Live:
    def __init__(self, root):
        self.srv = ui.ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(root))
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse()
        data = r.read()
        c.close()
        try:
            return r.status, json.loads(data)
        except ValueError:
            return r.status, data

    def nonce(self):
        return self.req("GET", "/api/session")[1]["session_nonce"]

    def post(self, body, origin=True, nonce=True, ctype="application/json", raw=None):
        h = {"Content-Type": ctype}
        if origin:
            h["Origin"] = f"http://127.0.0.1:{self.port}"
        if nonce:
            h["X-EviRep-Nonce"] = self.nonce() if nonce is True else nonce
        return self.req("POST", "/api/run", raw if raw is not None else json.dumps(body).encode(), h)

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="evirep_live_")
        os.makedirs(os.path.join(self.root, "data"))
        self.live = Live(self.root)
        lr._PROCS.clear()

    def tearDown(self):
        for p in lr._PROCS.values():
            try:
                p.wait(timeout=60)
            except Exception:
                p.kill()
        lr._PROCS.clear()
        self.live.close()
        shutil.rmtree(self.root, ignore_errors=True)

    def launch_records(self):
        d = os.path.join(self.root, lr.LAUNCH_DIR)
        return sorted(os.listdir(d)) if os.path.isdir(d) else []


class TestPolicy(unittest.TestCase):
    def test_no_launchable_stage_writes_a_protected_artefact(self):
        for s in ui.STAGES:
            cls, _ = lr.policy(s)
            if cls != "REFUSED":
                self.assertFalse(set(s["outputs"]) & lr.PROTECTED_ARTEFACTS, s["id"])

    def test_label_score_and_evaluation_stages_are_refused(self):
        pol = {s["id"]: lr.policy(s)[0] for s in ui.STAGES}
        for sid in ("01", "00", "02", "03", "03c", "04", "05", "08", "06", "eval", "04b"):
            self.assertEqual(pol[sid], "REFUSED", sid)
        for sid in ("10a", "10a-all", "10b", "10c", "10d", "10e", "10f", "10g", "10h", "review"):
            self.assertEqual(pol[sid], "ALLOWED", sid)
        self.assertEqual({k for k, v in pol.items() if v == "CONFIRM"}, {"04p", "05h", "diag"})


class TestRequestGuards(Base):
    def test_session_exposes_nonce_and_policy(self):
        status, s = self.live.req("GET", "/api/session")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(s["session_nonce"]), 32)
        self.assertEqual(s["policy"]["06"]["class"], "REFUSED")

    def test_guards(self):
        cases = [
            (dict(origin=False), 403), (dict(nonce=False), 403), (dict(nonce="wrong"), 403),
            (dict(ctype="text/plain"), 415), (dict(raw=b"x" * 2000), 413), (dict(raw=b"{not json"), 400),
        ]
        for kw, code in cases:
            status, body = self.live.post({"stage": "10h"}, **kw)
            self.assertEqual(status, code, (kw, body))
        h = {"Content-Type": "application/json", "Origin": "http://evil.example", "X-EviRep-Nonce": self.live.nonce()}
        self.assertEqual(self.live.req("POST", "/api/run", b'{"stage":"10h"}', h)[0], 403)
        self.assertEqual(self.launch_records(), [])                       # nothing was launched

    def test_policy_enforced_server_side(self):
        self.assertEqual(self.live.post({"stage": "06"})[0], 403)          # approved score
        self.assertEqual(self.live.post({"stage": "03"})[0], 403)          # labels
        self.assertEqual(self.live.post({"stage": "05h"})[0], 428)         # network: needs confirmation
        self.assertEqual(self.live.post({"stage": "nope"})[0], 400)
        self.assertEqual(self.live.post({"stage": "10h", "extra": 1})[0], 400)
        self.assertEqual(self.launch_records(), [])

    def test_other_post_paths_stay_405_and_get_never_launches(self):
        self.assertEqual(self.live.req("POST", "/api/status")[0], 405)
        for p in ("/api/run", "/api/session", "/api/launches", "/api/status"):
            self.live.req("GET", p)
        self.assertEqual(self.launch_records(), [])


class TestRealLaunch(Base):
    def wait_exit(self, lid, timeout=120):
        end = time.time() + timeout
        while time.time() < end:
            ls = {x["launch_id"]: x for x in self.live.req("GET", "/api/launches")[1]["launches"]}
            if ls.get(lid, {}).get("state") == "EXITED":
                return ls[lid]
            time.sleep(0.3)
        self.fail("launch did not exit")

    def test_launch_runs_the_real_runner_and_is_recorded(self):
        status, rec = self.live.post({"stage": "10h"})
        self.assertEqual(status, 202, rec)
        done = self.wait_exit(rec["launch_id"])
        self.assertIsInstance(done["exit_code"], int)
        with open(os.path.join(self.root, "data", "run_manifest.json")) as fh:
            m = json.load(fh)
        la = m["stages"]["10h"]["last_attempt"]                           # written by run_stage.py itself
        self.assertIn(la["status"], ("SUCCESS", "PARTIAL", "FAILED"))
        self.assertEqual(done["exit_code"] == 0, la["status"] in ("SUCCESS", "PARTIAL"))
        st = self.live.req("GET", "/api/status")[1]
        self.assertNotIn("RUNNING", st["by_status"])                       # never left as running


class TestPathConfinement(Base):
    """D2/D3 (2026-10-20 runtime audit): manifest run_dir and launch-record log paths were followed blindly, so the
    dashboard could display the tail of any log.txt / file on disk."""

    def setUp(self):
        super().setUp()
        self.outside = tempfile.mkdtemp(prefix="evirep_outside_")
        with open(os.path.join(self.outside, "log.txt"), "w") as fh:
            fh.write("SECRET-OUTSIDE-LINE\n")

    def tearDown(self):
        shutil.rmtree(self.outside, ignore_errors=True)
        super().tearDown()

    def test_manifest_run_dir_outside_runs_is_ignored(self):
        m = {"stages": {"10h": {"last_attempt": {"run_id": "x", "status": "RUNNING", "pid": os.getpid(),
                                                 "run_dir": os.path.relpath(self.outside, self.root),
                                                 "started_utc": "2026-10-20T00:00:00+00:00"}}}, "history": []}
        with open(os.path.join(self.root, "data", "run_manifest.json"), "w") as fh:
            json.dump(m, fh)
        blob = json.dumps([self.live.req("GET", p)[1] for p in ("/api/status", "/api/live")])
        self.assertNotIn("SECRET-OUTSIDE", blob)
        self.assertIn("RUNNING", blob)                                    # the run itself is still reported

    def test_launch_record_log_path_is_not_followed(self):
        d = os.path.join(self.root, lr.LAUNCH_DIR)
        os.makedirs(d)
        with open(os.path.join(d, "20261020T000000Z-ui-aaaaaa.json"), "w") as fh:
            json.dump({"launch_id": "20261020T000000Z-ui-aaaaaa", "command": "x",
                       "log": os.path.relpath(os.path.join(self.outside, "log.txt"), self.root)}, fh)
        with open(os.path.join(d, "20261020T000001Z-ui-bbbbbb.json"), "w") as fh:
            json.dump({"launch_id": "../../evil", "command": "y"}, fh)
        blob = json.dumps(self.live.req("GET", "/api/launches")[1])
        self.assertNotIn("SECRET-OUTSIDE", blob)


class TestLaunchEnvironmentErrors(Base):
    """D5 (2026-10-20 runtime audit): an unwritable launch directory gave only "launch failed (PermissionError)"."""

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores file permissions")
    def test_unwritable_launch_dir_is_actionable_and_starts_nothing(self):
        d = os.path.join(self.root, lr.LAUNCH_DIR)
        os.makedirs(d)
        os.chmod(d, 0o500)
        try:
            status, body = self.live.post({"stage": "10h"})
        finally:
            os.chmod(d, 0o755)
        self.assertEqual(status, 500)
        self.assertIn("not started", body["error"])
        self.assertIn("data/_runs is writable", body["error"])
        self.assertNotIn(self.root, json.dumps(body))
        self.assertEqual(lr._PROCS, {})

    def test_missing_runner_is_reported_as_a_failed_launch_not_success(self):
        orig = lr.RUN_STAGE
        lr.RUN_STAGE = os.path.join(self.root, "no_such_runner.py")
        try:
            status, rec = self.live.post({"stage": "10h"})
        finally:
            lr.RUN_STAGE = orig
        self.assertEqual(status, 202)                                      # accepted is not succeeded
        end = time.time() + 20
        while time.time() < end:
            ls = self.live.req("GET", "/api/launches")[1]["launches"]
            if ls and ls[0]["state"] == "EXITED":
                break
            time.sleep(0.2)
        self.assertEqual(ls[0]["state"], "EXITED")
        self.assertNotEqual(ls[0]["exit_code"], 0)
        self.assertTrue(any("can't open file" in x for x in ls[0]["log_tail"]))


class TestSequenceOutcome(unittest.TestCase):
    def test_sequence_line_is_parsed_per_stage(self):
        tail = ["10d: FAILED (r1) - exit code 1", "10e: BLOCKED - not started: upstream in this sequence did not succeed: 10d",
                'SEQUENCE [{"stage": "10d", "status": "FAILED", "run_id": "r1", "detail": "x"}, '
                '{"stage": "10e", "status": "BLOCKED", "run_id": null, "detail": "y"}]']
        seq = lr._sequence(tail)
        self.assertEqual([(r["stage"], r["status"]) for r in seq], [("10d", "FAILED"), ("10e", "BLOCKED")])
        self.assertIsNone(lr._sequence(["20261020T000000Z-10h-abcd: SUCCESS (exit 0)"]))
        self.assertIsNone(lr._sequence(["SEQUENCE {not json"]))


class TestRunnerReaped(Base):
    """D8 (2026-10-20 release gate): a finished runner stayed a zombie, and its exit code was recorded only when
    something polled /api/launches. Each launch is now reaped as soon as it exits."""

    def test_exited_runner_is_reaped_and_recorded_without_polling(self):
        import subprocess
        fast = os.path.join(self.root, "fast.py")
        with open(fast, "w") as fh:
            fh.write("import sys\nsys.exit(3)\n")
        orig = lr.RUN_STAGE
        lr.RUN_STAGE = fast
        try:
            status, rec = self.live.post({"stage": "10h"})
        finally:
            lr.RUN_STAGE = orig
        self.assertEqual(status, 202)
        path = os.path.join(self.root, lr.LAUNCH_DIR, rec["launch_id"] + ".json")
        end = time.time() + 10
        while time.time() < end:
            with open(path) as fh:
                if json.load(fh).get("exit_code") is not None:
                    break
            time.sleep(0.1)
        with open(path) as fh:
            saved = json.load(fh)
        self.assertEqual(saved["exit_code"], 3)                             # recorded with nobody polling
        self.assertTrue(saved["finished_utc"])
        state = subprocess.run(["ps", "-o", "stat=", "-p", str(rec["pid"])], capture_output=True, text=True).stdout.strip()
        self.assertFalse(state.startswith("Z"), f"runner left as a zombie ({state})")


class TestConflicts(Base):
    """STAND-IN runner (a 3 s sleeper) holds the first launch open; the server must refuse a second one."""

    def test_second_launch_refused_while_first_runs(self):
        slow = os.path.join(self.root, "slow_runner.py")
        with open(slow, "w") as fh:
            fh.write("import time\ntime.sleep(3)\n")
        orig = lr.RUN_STAGE
        lr.RUN_STAGE = slow
        try:
            self.assertEqual(self.live.post({"stage": "10h"})[0], 202)
            status, body = self.live.post({"stage": "10g"})
            self.assertEqual(status, 409, body)
            self.assertIn("still starting or running", body["error"])
        finally:
            lr.RUN_STAGE = orig


if __name__ == "__main__":
    unittest.main()
