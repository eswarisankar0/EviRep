"""UI quality pass (2026-10-20): chart data, freshness facts, source timestamps and readable labels are truthful."""
import csv
import importlib.util
import json
import os
import pathlib
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("evirep_ui_quality", os.path.join(ROOT, "ui", "server.py"))
ui = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ui)
HAVE = os.path.exists(os.path.join(ROOT, "data", "vps_scores_v2.csv"))


@unittest.skipUnless(HAVE, "needs the approved artefacts")
class TestValidationChartData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.V = ui.build_validation_charts(ROOT)
        with open(os.path.join(ROOT, "data", "vps_evaluation_report.json"), encoding="utf-8") as fh:
            cls.rep = json.load(fh)

    def test_curves_reproduce_the_approved_report(self):
        prim = next(p for p in self.rep["primary"] if p["column"] == "VPS_equal_5d")
        self.assertTrue(self.V["matches_report"])
        self.assertAlmostEqual(self.V["auroc_recomputed"], prim["auroc"], places=9)
        self.assertAlmostEqual(self.V["auprc_recomputed"], prim["auprc"], places=9)
        self.assertEqual(self.V["roc"][0], [0.0, 0.0])
        self.assertEqual(self.V["roc"][-1], [1.0, 1.0])
        self.assertEqual((self.V["n"], self.V["positives"], self.V["negatives"]), (90, 14, 76))

    def test_independent_recomputation_of_the_roc_area(self):
        with open(os.path.join(ROOT, "data", "vps_scores_v2.csv"), newline="") as fh:
            rows = list(csv.DictReader(fh))
        pos = [float(r["VPS_equal_5d"]) for r in rows if float(r["label"]) == 1]
        neg = [float(r["VPS_equal_5d"]) for r in rows if float(r["label"]) == 0]
        mw = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))
        self.assertAlmostEqual(self.V["auroc_recomputed"], mw, places=12)

    def test_model_comparison_and_missingness_are_copied_from_the_report(self):
        self.assertEqual([m["auroc"] for m in self.V["models"]], [p["auroc"] for p in self.rep["primary"]])
        self.assertEqual(self.V["paired_5d_vs_4d"], self.rep["paired_5d_vs_4d"])
        self.assertEqual(self.V["missing_by_dimension"], self.rep["missing_data"]["not_measured_by_dimension"])
        self.assertEqual(self.V["imputed_by_dimension"]["proximity"], 2)

    def test_mismatch_withholds_the_curves(self):
        orig = ui.read_json

        def fake(root, rel):
            d, e = orig(root, rel)
            if rel.endswith("vps_evaluation_report.json") and isinstance(d, dict):
                d = json.loads(json.dumps(d))
                next(p for p in d["primary"] if p["column"] == "VPS_equal_5d")["auroc"] = 0.5
            return d, e
        ui.read_json = fake
        try:
            V = ui.build_validation_charts(ROOT)
        finally:
            ui.read_json = orig
        self.assertFalse(V["matches_report"])
        self.assertIsNone(V["roc"])


@unittest.skipUnless(HAVE, "needs the approved artefacts")
class TestFreshnessSourcesScience(unittest.TestCase):
    def test_freshness_comes_from_the_tracker(self):
        L = ui.build_live(ROOT)
        st = ui._runs.status(ROOT, ui.STAGES)
        F = L["freshness"]
        self.assertEqual(sorted(F["inputs_changed"]), sorted(k for k, v in st.items() if v["status"] in ("STALE", "MODIFIED", "MISSING")))
        self.assertEqual(sorted(F["code_unverifiable"]),
                         sorted(k for k, v in st.items() if v.get("last_success") and not v["code_fingerprint_recorded"]))
        times = [v["last_success"]["finished_utc"] for v in st.values() if v.get("last_success") and v["last_success"].get("finished_utc")]
        self.assertEqual(F["last_success_utc"], max(times))

    def test_sources_never_invent_a_retrieval_time(self):
        S = {x["source"]: x for x in ui.build_live(ROOT)["sources"]}
        with open(os.path.join(ROOT, "data", "literature_provenance_run.json")) as fh:
            self.assertEqual(S["PubMed"]["retrieved_utc"], json.load(fh)["generated_utc"])
        for name in ("openFDA drug labels", "Open Targets Platform", "Hetionet v1.0"):
            self.assertIsNone(S[name]["retrieved_utc"], name)          # not recorded -> shown as "not recorded"

    def test_science_counts_match_the_artefacts(self):
        SC = ui.build_live(ROOT)["science"]
        R = ui.build_review(ROOT)
        self.assertEqual((SC["reviews_awaiting"], SC["reviews_adjudicated"]), (R["n_unresolved"], R["n_adjudicated"]))
        self.assertEqual(SC["cohort"]["positives"], 14)
        self.assertTrue(all(c["id"] for c in SC["pending_candidates"]))  # exact identifier kept beside the label

    def test_ranking_marks_imputed_values(self):
        rows = {r["compound"]: r for r in ui.build_ranking(ROOT)["rows"]}
        self.assertEqual(sorted(k for k, r in rows.items() if r["dimensions_imputed"]), ["Deferiprone", "Trimethobenzamide"])


class TestReadableLabels(unittest.TestCase):
    def setUp(self):
        self.js = pathlib.Path(os.path.join(ROOT, "ui", "app.js")).read_text()

    def test_every_agent_status_code_has_a_readable_label(self):
        codes = set()
        for rel in ("scripts/conflict_context_agent.py", "scripts/reproducibility_agent.py", "scripts/clinical_role_review.py",
                    "scripts/run_stage.py"):
            src = pathlib.Path(os.path.join(ROOT, rel)).read_text()
            codes |= set(re.findall(r'"((?:DIRECT|STATISTICAL|CONTEXT|CROSS|UNCERTAIN|NON|NO|REPLICATED|SINGLE|INCONSISTENT|SECONDARY|'
                                    r'KEYWORD|ALIAS|CHEMBL|STRUCTURE|SKIPPED)_[A-Z_]+)"', src))
        labels = self.js[self.js.index("const LABELS = {"):self.js.index("const human =")]
        missing = sorted(c for c in codes if not re.search(r"\b" + c + r":", labels))
        self.assertEqual(missing, [], "status codes shown to users without a readable label")

    def test_badges_show_label_and_keep_code_in_tooltip(self):
        self.assertIn('title="${esc(s)}">${esc(human(s))}</span>', self.js)

    def test_no_agent_is_described_as_feeding_the_score(self):
        # final release audit 2026-10-21: stage 06 reads no agent output (test_vps_correctness.TestIsolation);
        # agents paired with a scoring stage only check it, so "feeds the score" overstated their role
        self.assertNotIn("eeds the score", self.js)
        self.assertIn("does not change the score", self.js)

    def test_every_chart_keeps_its_data_table_alternative(self):
        # audit 2026-10-21: the Run Center state chart opted out (noTable: true), leaving screen-reader users nothing
        self.assertNotIn("noTable: true", self.js)

    def test_no_blanket_current_claim(self):
        self.assertNotIn('"All results current"', self.js)
        self.assertNotIn('"Pipeline results current"', self.js)
        self.assertIn("Current against recorded inputs", self.js)
        self.assertIn('VERIFIED_WITH_GAPS: "Current against recorded inputs, with unverifiable inputs"', self.js)


if __name__ == "__main__":
    unittest.main()
