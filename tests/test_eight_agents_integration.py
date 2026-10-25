"""
End-to-end integration check across all eight agents (10a-10h) on the persisted repository artefacts.

For every agent the in-memory run on the current inputs must reproduce its persisted output exactly (apart from
the generation timestamp): a persisted output that no longer matches its inputs is stale, and a downstream agent
would be reading it. Also checked: every envelope validates, every agent covers the 90-compound evaluable pool,
10h sees all agent outputs present and none stale, 10g consumes the stage-04p PMIDs, and nothing is written.
Read-only; skipped when the persisted outputs are absent (fresh clone).
"""

import importlib.util
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _load(name):
    spec = importlib.util.spec_from_file_location(f"int_{name}", os.path.join(ROOT, "scripts", f"{name}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


AGENTS = {   # id: (module, callable name, persisted output)
    "10a": ("literature_credibility_agent", "all_compounds_report", "data/literature_credibility_all.json"),
    "10b": ("molecular_run_record", "build", "data/molecular_agent_run.json"),
    "10c": ("clinical_evidence_agent", "run", "data/clinical_evidence.json"),
    "10d": ("conflict_context_agent", "run", "data/conflict_context.json"),
    "10e": ("reproducibility_agent", "run", "data/reproducibility.json"),
    "10f": ("safety_evidence_agent", "run", "data/safety_evidence.json"),
    "10g": ("evidence_independence_agent", "run", "data/evidence_independence.json"),
    "10h": ("completeness_gap_agent", "run", "data/completeness_gaps.json"),
}
VOLATILE = {"generated_utc"}


def _strip(o):
    if isinstance(o, dict):
        return {k: _strip(v) for k, v in o.items() if k not in VOLATILE}
    if isinstance(o, list):
        return [_strip(v) for v in o]
    return o


def _first_difference(a, b, path=""):
    if type(a) is not type(b):
        return f"{path}: type {type(a).__name__} != {type(b).__name__}"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f"{path}/{k}: present on one side only"
            d = _first_difference(a[k], b[k], f"{path}/{k}")
            if d:
                return d
    elif isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: length {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = _first_difference(x, y, f"{path}[{i}]")
            if d:
                return d
    elif a != b:
        return f"{path}: {str(a)[:80]!r} != {str(b)[:80]!r}"
    return None


@unittest.skipUnless(all(os.path.exists(os.path.join(ROOT, o)) for _, _, o in AGENTS.values()),
                     "persisted agent outputs absent")
class TestEightAgents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = {o: os.stat(os.path.join(ROOT, o)).st_mtime_ns for _, _, o in AGENTS.values()}
        cls.fresh, cls.saved = {}, {}
        for aid, (mod, fn, out) in AGENTS.items():
            cls.fresh[aid] = json.loads(json.dumps(getattr(_load(mod), fn)(ROOT)))   # normalise tuples, keys
            with open(os.path.join(ROOT, out), encoding="utf-8") as fh:
                cls.saved[aid] = json.load(fh)

    def test_every_persisted_output_is_reproduced_by_its_agent(self):
        stale = {aid: _first_difference(_strip(self.saved[aid]), _strip(self.fresh[aid])) for aid in AGENTS}
        self.assertEqual({k: v for k, v in stale.items() if v}, {})

    def test_envelopes_validate_and_ids_match(self):
        from agent_contract import validate_envelope
        for aid, out in self.saved.items():
            self.assertTrue(validate_envelope(out), aid)
            self.assertEqual(out["agent_id"], aid)
            self.assertIn(out["run_status"], ("SUCCESS", "PARTIAL", "NO_EVIDENCE"), aid)

    def test_every_agent_covers_the_evaluable_pool(self):
        import pandas as pd
        pool = set(pd.read_csv(os.path.join(ROOT, "data/vps_scores_v2.csv"))["compound_name"])
        covered = {
            "10a": set(self.saved["10a"]["compounds"]),
            "10c": {c["compound"] for c in self.saved["10c"]["compounds"]},
            "10d": {r["compound"] for r in self.saved["10d"]["records"]},
            "10f": {r["compound"] for r in self.saved["10f"]["records"]},
            "10g": {r["compound"] for r in self.saved["10g"]["records"]},
            "10h": {r["compound"] for r in self.saved["10h"]["records"]},
        }
        for aid, names in covered.items():
            self.assertEqual(pool - names, set(), f"{aid} misses pool compounds")
        self.assertEqual(self.saved["10b"]["coverage"]["evidence_records_valid"], len(pool))

    def test_10h_sees_all_agent_outputs_present_and_fresh(self):
        ao = self.saved["10h"]["agent_outputs"]
        for aid in ("10a", "10c", "10d", "10e", "10f", "10g"):
            self.assertTrue(ao[aid]["present"], aid)
            self.assertEqual(ao[aid]["stale_inputs"], [], aid)

    def test_missing_failed_and_negative_stay_distinct_in_10h(self):
        states = {d["state"] for r in self.saved["10h"]["records"] for d in r["domains"].values()}
        self.assertTrue(states <= set(_load("completeness_gap_agent").STATES))
        lit = [r["domains"]["literature_credibility"]["state"] for r in self.saved["10h"]["records"]]
        self.assertNotIn("NOT_RETRIEVED", lit)                       # 04p + 10a-all supply every compound

    def test_10g_consumes_stage04p(self):
        d2 = self.saved["10g"]["coverage"]["checks"]["D2_same_study_in_two_dimensions"]
        self.assertLessEqual(d2["NOT_ASSESSABLE"], 1)
        self.assertIn("data/literature_papers.jsonl", self.saved["10g"]["inputs"])

    def test_nothing_was_written(self):
        after = {o: os.stat(os.path.join(ROOT, o)).st_mtime_ns for _, _, o in AGENTS.values()}
        self.assertEqual(after, self.before)


if __name__ == "__main__":
    unittest.main()
