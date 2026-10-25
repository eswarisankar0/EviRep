"""Stage registry integrity (audit 2026-10-21): the Run Center's stage graph is a well-formed DAG whose edges match the
files each stage reads, and every stage that rewrites a protected artefact is refused from the dashboard."""
import collections
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ui"))
_spec = importlib.util.spec_from_file_location("evirep_ui_registry", os.path.join(ROOT, "ui", "server.py"))
ui = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ui)
import live_runs  # noqa: E402

S = ui.STAGES
IDS = [s["id"] for s in S]
DEPS = {s["id"]: list(s.get("depends_on") or []) for s in S}
PRODUCER = collections.defaultdict(list)
for _s in S:
    for _o in _s["outputs"]:
        PRODUCER[_o].append(_s["id"])


def ancestors(n, seen=None):
    seen = set() if seen is None else seen
    for d in DEPS.get(n, []):
        if d not in seen:
            seen.add(d)
            ancestors(d, seen)
    return seen


class TestRegistryIsAWellFormedDag(unittest.TestCase):
    def test_unique_ids_and_existing_scripts(self):
        self.assertEqual([k for k, v in collections.Counter(IDS).items() if v > 1], [])
        self.assertEqual([s["script"] for s in S if not os.path.exists(os.path.join(ROOT, s["script"]))], [])

    def test_dependencies_exist_and_are_acyclic(self):
        self.assertEqual([(i, d) for i, ds in DEPS.items() for d in ds if d not in DEPS], [])
        for i in IDS:
            self.assertNotIn(i, ancestors(i), f"cycle through {i}")

    def test_each_output_has_one_producer(self):
        self.assertEqual({o: p for o, p in PRODUCER.items() if len(p) > 1}, {})

    def test_a_stage_only_reads_outputs_of_its_ancestors(self):
        bad = [(s["id"], i, p) for s in S for i in s["inputs"] for p in PRODUCER.get(i, [])
               if p != s["id"] and p not in ancestors(s["id"])]
        self.assertEqual(bad, [], "a stage reads a file whose producer it does not depend on: freshness could not propagate")

    def test_topological_order_used_by_the_runner_respects_dependencies(self):
        import run_stage
        order = [s["id"] for s in run_stage._topo(S)]
        pos = {k: n for n, k in enumerate(order)}
        self.assertEqual(sorted(order), sorted(IDS))
        for i, ds in DEPS.items():
            for d in ds:
                self.assertLess(pos[d], pos[i], f"{d} must run before {i}")


class TestLaunchPolicy(unittest.TestCase):
    def test_protected_writers_are_refused_and_permitted_stages_are_safe(self):
        for s in S:
            cls, _ = live_runs.policy(s)
            if set(s["outputs"]) & live_runs.PROTECTED_ARTEFACTS:
                self.assertEqual(cls, "REFUSED", s["id"])
            if cls in ("ALLOWED", "CONFIRM"):
                self.assertFalse(set(s["outputs"]) & live_runs.PROTECTED_ARTEFACTS, s["id"])
                self.assertGreater(s.get("timeout_s") or 0, 0, f"launchable stage {s['id']} needs a timeout")

    def test_the_score_reads_no_agent_output(self):
        s06 = next(s for s in S if s["id"] == "06")
        agent_outputs = {o for s in S if s["id"].startswith("10") or s["id"] == "review" for o in s["outputs"]}
        self.assertEqual(set(s06["inputs"]) & agent_outputs, set())

    def test_launch_commands_come_from_the_registry_not_the_request(self):
        with self.assertRaises(live_runs.LaunchError) as e:
            live_runs.launch(ROOT, S, {}, {"stage": "10a; rm -rf /"})
        self.assertEqual(e.exception.code, 400)
        with self.assertRaises(live_runs.LaunchError) as e:
            live_runs.launch(ROOT, S, {}, {"stage": "../../scripts/06_vps_fusion.py"})
        self.assertEqual(e.exception.code, 400)
        with self.assertRaises(live_runs.LaunchError) as e:
            live_runs.launch(ROOT, S, {}, {"stage": "06"})                    # protected writer
        self.assertEqual(e.exception.code, 403)
        with self.assertRaises(live_runs.LaunchError) as e:
            live_runs.launch(ROOT, S, {}, {"stage": "05h"})                   # network stage without confirmation
        self.assertEqual(e.exception.code, 428)
        with self.assertRaises(live_runs.LaunchError) as e:
            live_runs.launch(ROOT, S, {}, {"stage": "10a", "extra": "x"})    # unknown field
        self.assertEqual(e.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
