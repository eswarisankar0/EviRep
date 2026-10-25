"""Agent failure modes through the real runner (2026-10-20): a corrupted input never yields a fresh-looking result.

Each of the eight agent stages is run by scripts/run_stage.py in an isolated copy of data/ with one input corrupted.
The run must be recorded as FAILED, the previously published output must stay byte-identical, the last success must
not move, and the dashboard's live state must report the failure instead of "current". Also: an input that the last
success did not fingerprint is reported as unverifiable, never as current.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("evirep_ui_faults", os.path.join(ROOT, "ui", "server.py"))
ui = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ui)
HAVE = os.path.exists(os.path.join(ROOT, "data", "run_manifest.json")) and os.path.exists(os.path.join(ROOT, "data", "vps_scores_v2.csv"))
SKIP = {"opentargets_20.11", "dailymed", "hetionet_edges.csv", "_runs", "_candidates", "_backup_contaminated_20261005"}
#: one essential input per agent stage
CASES = [("10a", "data/conflict_claims_curated.json"), ("10a-all", "data/literature_provenance.csv"),
         ("10b", "data/molecular_pathway_evidence.jsonl"), ("10c", "data/clinical_maturity_precutoff_clean.csv"),
         ("10d", "data/conflict_claims_curated.json"), ("10e", "data/cache/pubmed_efetch_case_claims.xml"),
         ("10f", "data/safety_signal.csv"), ("10g", "data/literature_independence.csv"), ("10h", "data/conflict_context.json")]
STAGE = {s["id"]: s for s in ui.STAGES}


def _md5(p):
    with open(p, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


@unittest.skipUnless(HAVE, "needs the approved artefacts")
class TestCorruptedInputNeverLooksFresh(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="evirep_faults_")
        shutil.copytree(os.path.join(ROOT, "data"), os.path.join(cls.tmp, "data"),
                        ignore=lambda d, names: [n for n in names if n in SKIP])
        os.makedirs(os.path.join(cls.tmp, "data", "_runs"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _manifest(self):
        with open(os.path.join(self.tmp, "data", "run_manifest.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def test_each_agent_fails_closed_on_a_malformed_input(self):
        for sid, rel in CASES:
            with self.subTest(stage=sid, corrupted=rel):
                p = os.path.join(self.tmp, rel)
                shutil.copy(p, p + ".orig")
                outs = {o: _md5(os.path.join(self.tmp, o)) for o in STAGE[sid]["outputs"]}
                before = self._manifest()["stages"].get(sid, {}).get("last_success")
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write("x;y\n\x00,,,\n" if rel.endswith(".csv") else "{not valid,,\n\x00garbage")
                try:
                    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "run_stage.py"), sid, "--root", self.tmp],
                                       capture_output=True, text=True, timeout=600)
                    st = self._manifest()["stages"][sid]
                    self.assertNotEqual(r.returncode, 0)
                    self.assertEqual(st["last_attempt"]["status"], "FAILED")
                    self.assertEqual(st.get("last_success"), before, "a failed attempt must not become the last success")
                    self.assertEqual({o: _md5(os.path.join(self.tmp, o)) for o in STAGE[sid]["outputs"]}, outs,
                                     "the previously published output must be restored byte-identical")
                    live = ui.build_live(self.tmp)
                    brief = next(x for x in live["stages"] if x["id"] == sid)
                    self.assertTrue(brief["latest_attempt_failed"])
                    self.assertEqual(live["overall"]["state"], "FAILED")
                finally:
                    shutil.move(p + ".orig", p)
                    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "run_stage.py"), sid, "--root", self.tmp],
                                   capture_output=True, text=True, timeout=600)

    def test_a_failed_dependency_is_flagged_on_its_dependants(self):
        """A single-stage run on top of a dependency whose latest attempt failed uses the restored output: legitimate,
        but every dependant must say so (audit 2026-10-21)."""
        p = os.path.join(self.tmp, "data", "conflict_claims_curated.json")
        shutil.copy(p, p + ".orig")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("{broken")
        try:
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "run_stage.py"), "10d", "--root", self.tmp],
                           capture_output=True, text=True, timeout=600)
        finally:
            shutil.move(p + ".orig", p)
        try:
            st = ui._runs.status(self.tmp, ui.STAGES)
            self.assertTrue(st["10d"]["latest_attempt_failed"])
            for dep in ("10e", "10h"):
                self.assertTrue(any("latest attempt failed" in w and "10d" in w for w in st[dep]["warnings"]), (dep, st[dep]["warnings"]))
        finally:
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "run_stage.py"), "10d", "--root", self.tmp],
                           capture_output=True, text=True, timeout=600)
        self.assertFalse(ui._runs.status(self.tmp, ui.STAGES)["10d"]["latest_attempt_failed"])
        self.assertFalse(any("latest attempt failed" in w for w in ui._runs.status(self.tmp, ui.STAGES)["10h"]["warnings"]))

    def test_upstream_failure_blocks_dependants_in_a_sequence(self):
        p = os.path.join(self.tmp, "data", "conflict_claims_curated.json")
        shutil.copy(p, p + ".orig")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("{broken")
        try:
            r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "run_stage.py"), "--sequence", "10d", "10h",
                                "--root", self.tmp], capture_output=True, text=True, timeout=600)
            seq = next(json.loads(x[len("SEQUENCE "):]) for x in r.stdout.splitlines() if x.startswith("SEQUENCE "))
            by = {x["stage"]: x["status"] for x in seq}
            self.assertEqual(by["10d"], "FAILED")
            self.assertEqual(by["10h"], "BLOCKED", "a dependant must not report success on top of a failed upstream")
        finally:
            shutil.move(p + ".orig", p)


@unittest.skipUnless(HAVE, "needs the approved artefacts")
class TestUnfingerprintedInputIsNotCurrent(unittest.TestCase):
    def test_untracked_input_is_reported_and_blocks_the_current_state(self):
        tmp = tempfile.mkdtemp(prefix="evirep_untracked_")
        try:
            shutil.copytree(os.path.join(ROOT, "data"), os.path.join(tmp, "data"),
                            ignore=lambda d, names: [n for n in names if n in SKIP or n == "cache"])
            mp = os.path.join(tmp, "data", "run_manifest.json")
            with open(mp, encoding="utf-8") as fh:
                m = json.load(fh)
            ls = m["stages"]["10h"]["last_success"]
            dropped = next(i for i in STAGE["10h"]["inputs"] if i in ls["inputs"])
            del ls["inputs"][dropped]                       # as if the last success had not fingerprinted it
            with open(mp, "w", encoding="utf-8") as fh:
                json.dump(m, fh)
            live = ui.build_live(tmp)
            un = live["freshness"]["untracked_inputs"]
            self.assertTrue(any(u["stage"] == "10h" and dropped in u["detail"].split(", ") for u in un), un)
            self.assertNotEqual(live["overall"]["state"], "CURRENT")
            self.assertIn("10h", ui.build_status(tmp)["by_status"]["UNVERIFIABLE"])
            self.assertTrue(any("10h" == a.get("stage") and "not fingerprinted" in a["text"] for a in live["next_actions"]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_untracked_output_is_not_described_as_an_input(self):
        v = {"warnings": ["declared output(s) not fingerprinted at the last success, so edits to them are not detected "
                          "(re-run to track them): data/x.json"]}
        self.assertEqual(ui._unfingerprinted(v), [("output", "data/x.json")])


@unittest.skipUnless(HAVE, "needs the approved artefacts")
class TestAgentDefectsFixed(unittest.TestCase):
    """E-055 A-2/A-3/A-4 (audit 2026-10-20): degraded inputs are reported, never published as clean success."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="evirep_defects_")
        shutil.copytree(os.path.join(ROOT, "data"), os.path.join(cls.tmp, "data"),
                        ignore=lambda d, names: [n for n in names if n in SKIP])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _run(self, script, out_rel):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", script), "--root", self.tmp],
                           capture_output=True, text=True, timeout=600)
        with open(os.path.join(self.tmp, out_rel), encoding="utf-8") as fh:
            return r, json.load(fh)

    def _swap(self, rel, writer):
        p = os.path.join(self.tmp, rel)
        shutil.copy(p, p + ".orig")
        writer(p)
        return lambda: shutil.move(p + ".orig", p)

    def test_10g_header_only_literature_is_partial_not_success(self):
        def header_only(p):
            with open(p + ".orig", encoding="utf-8") as src, open(p, "w", encoding="utf-8") as dst:
                dst.write(src.readline())
        restore = self._swap("data/literature_independence.csv", header_only)
        try:
            _, out = self._run("evidence_independence_agent.py", "data/evidence_independence.json")
            self.assertEqual(out["run_status"], "PARTIAL")
            self.assertIn("INPUT_EMPTY", [d["code"] for d in out["diagnostics"]])
        finally:
            restore()

    def test_10d_reports_malformed_molecular_lines(self):
        def bad_line(p):
            with open(p, "a", encoding="utf-8") as fh:
                fh.write("{not json\n")
        restore = self._swap("data/molecular_pathway_evidence.jsonl", bad_line)
        try:
            _, out = self._run("conflict_context_agent.py", "data/conflict_context.json")
            self.assertEqual(out["run_status"], "PARTIAL")
            self.assertTrue(any(d["code"] == "MALFORMED_LINE" and "1 unparseable" in d["message"] for d in out["diagnostics"]))
        finally:
            restore()

    def test_10h_does_not_read_a_failed_upstream_output_as_data(self):
        def fail(p):
            with open(p + ".orig", encoding="utf-8") as fh:
                env = json.load(fh)
            env["run_status"] = "FAILED"
            env["diagnostics"] = env.get("diagnostics", []) + [{"level": "error", "code": "TEST", "message": "injected"}]
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(env, fh)
        restore = self._swap("data/clinical_evidence.json", fail)
        try:
            _, out = self._run("completeness_gap_agent.py", "data/completeness_gaps.json")
            self.assertIn("UPSTREAM_FAILED", [d["code"] for d in out["diagnostics"]])
            self.assertNotEqual(out["run_status"], "SUCCESS")
            for rec in out["records"]:
                for dom in ("trial_outcomes", "trial_roles"):
                    self.assertEqual(rec["domains"][dom]["state"], "NOT_COMPUTED", (rec["compound"], dom))
        finally:
            restore()


if __name__ == "__main__":
    unittest.main()
