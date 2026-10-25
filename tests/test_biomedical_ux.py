"""Biomedical UX pass (2026-10-20): five-section navigation, evidence stance/basis, honest freshness wording."""
import csv
import importlib.util
import os
import pathlib
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("evirep_ui_ux", os.path.join(ROOT, "ui", "server.py"))
ui = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ui)
JS = pathlib.Path(os.path.join(ROOT, "ui", "app.js")).read_text()
HAVE = os.path.exists(os.path.join(ROOT, "data", "vps_scores_v2.csv"))


class TestNavigation(unittest.TestCase):
    def test_every_route_belongs_to_one_of_five_sections(self):
        views = re.findall(r"(\w+): view\w+", JS[JS.index("const VIEWS = {"):JS.index("};", JS.index("const VIEWS = {"))])
        section_of = dict(re.findall(r"(\w+): \"(\w+)\"", JS[JS.index("const SECTION_OF = {"):JS.index("};", JS.index("const SECTION_OF = {"))]))
        self.assertEqual(sorted(set(views) - set(section_of)), [], "a page without a section is unreachable from the navigation")
        self.assertEqual(set(section_of.values()), {"overview", "drugs", "evidence", "validation", "run"})

    def test_old_addresses_still_resolve(self):
        for old in ("dashboard", "live", "mechanism", "conflicts", "review", "compare", "technical", "pipeline", "agents", "cases", "agent"):
            self.assertRegex(JS, rf"\b{old}: view\w+", old)


@unittest.skipUnless(HAVE, "needs the approved artefacts")
class TestEvidenceNature(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.E = ui.build_evidence(ROOT)["items"]
        cls.R = ui.build_review(ROOT)

    def test_review_state_comes_from_the_review_queue(self):
        basis = [i["basis"] for i in self.E if i["type"] == "clinical"]
        self.assertEqual(basis.count("awaiting_review"), self.R["n_unresolved"])
        self.assertEqual(basis.count("human_reviewed"), self.R["n_adjudicated"])

    def test_missing_safety_equals_compounds_without_a_label(self):
        with open(os.path.join(ROOT, "data", "safety_signal.csv"), newline="") as fh:
            no_label = sum(r["has_label"] != "True" for r in csv.DictReader(fh))
        self.assertEqual(sum(i["stance"] == "missing" for i in self.E), no_label)

    def test_curated_stance_follows_the_recorded_direction(self):
        for i in self.E:
            if i["basis"] == "curated":
                d = i["role"].split(" · ")[0]
                want = "supporting" if d == "SUPPORTS" else "null_or_opposing" if d in ("NULL_RESULT", "OPPOSES") else "context"
                self.assertEqual(i["stance"], want, i)

    def test_targets_are_hypotheses_and_trials_are_never_supporting_findings(self):
        self.assertTrue(all(i["basis"] == "hypothesis" for i in self.E if i["type"] == "molecular"))
        self.assertFalse(any(i["stance"] == "supporting" for i in self.E if i["type"] == "clinical"))


class TestWording(unittest.TestCase):
    def test_headline_states_cover_every_overall_state(self):
        src = pathlib.Path(os.path.join(ROOT, "ui", "server.py")).read_text()
        expr = src[src.index('    state = ("UNKNOWN" if'):src.index("\n    agents = []", src.index('    state = ("UNKNOWN" if'))]
        states = set(re.findall(r'"([A-Z_]+)"', expr))
        self.assertIn("VERIFIED_WITH_GAPS", states)
        block = JS[JS.index("const STATE_HEADLINE = {"):JS.index("};", JS.index("const STATE_HEADLINE = {"))]
        for s in states:
            self.assertIn(s + ":", block)

    def test_refusals_are_distinguished(self):
        pt = JS[JS.index("function policyText(p)"):JS.index("async function viewLive")]
        for phrase in ("Needs owner approval", "Command line only", "Not available from this screen"):
            self.assertIn(phrase, pt)

    def test_pending_result_set_id_is_kept_out_of_researcher_copy(self):
        ov = JS[JS.index("async function viewOverview()"):JS.index("async function viewEvidence(")]
        visible = ov[:ov.index("<summary><strong>Technical details</strong>")]
        self.assertNotIn("c.id", visible)


if __name__ == "__main__":
    unittest.main()
