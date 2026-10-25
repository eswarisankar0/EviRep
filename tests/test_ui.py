"""
Tests for the read-only dashboard (ui/server.py).

Offline: every test builds a throwaway repository root in a temp directory, so
nothing here reads or writes the project's real data/. A socket guard asserts
that building any view makes no network connection.

Run:  ./venv/bin/python -m unittest discover -s tests -v
"""

import csv
import http.client
import importlib.util
import json
import pathlib
import os
import re
import shutil
import socket
import tempfile
import threading
import unittest
import urllib.request
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("evirep_ui", os.path.join(ROOT, "ui", "server.py"))
ui = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ui)

# Paths built with f-strings in the scripts, so they never appear literally.
DERIVED_PATHS = {
    "data/literature_graph_droxidopa.json": "literature_graph_",
    "data/figure2_ablation.png": "figure2_ablation",
    "data/figure2_ablation_5d.png": "figure2_ablation",
    "data/figure3_droxidopa_literature_graph.png": "_literature_graph.png",
    "data/clinical_maturity_precutoff_clean.csv": "_clean",
    "data/ground_truth_postcutoff_clean.csv": "_clean",
    # 10a writes one file per curated compound from this template; 10h reads them through this glob (R-06)
    **{f"data/literature_credibility_{c}.json": ("data/literature_credibility_{slug}.json", "data/literature_credibility_*.json")
       for c in ("donepezil", "domperidone", "melatonin", "propranolol")},
    # written by the manual --graph mode (D-023, documented in the 10a docstring); read by 10h through the glob
    "data/literature_credibility_droxidopa.json": ("data/literature_credibility_droxidopa.json",
                                                   "data/literature_credibility_*.json"),
}


def _needle_in(path, src):
    """Every needle is an exact string; a path may be produced or read through one of several (DERIVED_PATHS)."""
    needles = DERIVED_PATHS.get(path, path)
    return any(n in src for n in (needles if isinstance(needles, tuple) else (needles,)))


def write_csv(path, header, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


VPS_HEADER = ["compound_name", "proximity_z", "max_phase_rank", "n_trials", "effective_independent_count",
              "serious_term_count", "molecular_plausibility_score", "r_proximity", "r_clinical",
              "r_literature", "r_safety", "r_molecular", "label", "VPS_equal", "VPS_equal_5d"]


def build_fixture(root):
    """Minimal synthetic repo. Values are fixture data, never results."""
    d = os.path.join(root, "data")
    write_csv(os.path.join(d, "vps_scores_v2.csv"), VPS_HEADER, [
        ["Alpha", "-1.0", "5", "3", "4", "1", "0.5", "0.9", "0.8", "0.7", "0.6", "0.5", "1", "0.75", "0.70"],
        ["Beta", "0.5", "2", "1", "2", "0", "0.0", "0.1", "0.2", "0.3", "0.9", "0.1", "0", "0.40", "0.30"],
    ])
    write_csv(os.path.join(d, "network_proximity.csv"),
              ["compound_id", "compound_name", "n_targets", "proximity_z"],
              [["Compound::X1", "Alpha", "3", "-1.0"], ["Compound::X2", "Beta", "1", "0.5"]])
    write_csv(os.path.join(d, "clinical_maturity_precutoff_clean.csv"),
              ["compound_id", "compound_name", "nct_id", "phase", "status", "enrollment", "first_posted"],
              [["Compound::X1", "Alpha", "NCT00000001", "PHASE2", "COMPLETED", "40", "2015-01-01"]])
    write_csv(os.path.join(d, "ground_truth_postcutoff_clean.csv"),
              ["compound_id", "compound_name", "nct_id", "phase", "status", "enrollment", "first_posted"],
              [["Compound::X1", "Alpha", "NCT00000002", "PHASE3", "RECRUITING", "100", "2022-06-01"]])
    write_csv(os.path.join(d, "clinicaltrials_match_audit.csv"),
              ["compound_name", "nct_id", "brief_title", "cohort", "outcome", "qualifies", "reason"],
              [["Alpha", "NCT00000001", "t1", "pre", "MATCHED", "True", ""],
               ["Gamma", "NCT00000003", "t3", "pre", "NO_MATCH", "False", "other drug"]])
    write_csv(os.path.join(d, "molecular_pathway.csv"),
              ["compound_name", "chembl_id", "resolved", "molecular_plausibility_score", "confidence",
               "direct_component", "pathway_component", "n_targets"],
              [["Alpha", "CHEMBL0", "True", "0.5", "1.0", "0.5", "0.5", "3"]])
    with open(os.path.join(d, "molecular_pathway_evidence.jsonl"), "w") as fh:
        fh.write("{not json\n")
        fh.write(json.dumps({"drug": "Alpha", "scoring": {"explanation": "score = fixture"},
                             "targets": [{"gene_symbol": "G1"}], "disease_links": [], "limitations": ["L"]}) + "\n")


class _NoNetwork:
    """Fail the test if anything opens a non-local socket."""

    def __enter__(self):
        real = socket.socket.connect

        def guarded(sock, address):
            host = address[0] if isinstance(address, tuple) else address
            if host not in ("127.0.0.1", "localhost", "::1"):
                raise AssertionError(f"unexpected network connection to {address}")
            return real(sock, address)

        self._p = mock.patch.object(socket.socket, "connect", guarded)
        self._p.start()
        return self

    def __exit__(self, *exc):
        self._p.stop()


class UITestBase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="evirep_ui_")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)


class TestEffectiveLabelsAndMissingDimensions(UITestBase):
    """D-004 / TD-032: the UI must show label exclusions and unmeasured dimensions."""

    def setUp(self):
        super().setUp()
        build_fixture(self.root)
        d = os.path.join(self.root, "data")
        write_csv(os.path.join(d, "label_role_exclusions.csv"),
                  ["nct_id", "compound_name", "role_verdict", "policy", "approved", "evidence"],
                  [["NCT00000002", "Alpha", "PROCEDURAL_CONTEXT", "P1", "fixture", "fixture evidence"]])
        write_csv(os.path.join(d, "vps_scores_v2.csv"), VPS_HEADER + ["dimensions_missing", "n_dimensions_measured"], [
            ["Alpha", "-1.0", "5", "3", "4", "1", "0.5", "0.9", "0.8", "0.7", "0.6", "0.5", "0", "0.75", "0.70", "", "5"],
            ["Beta", "0.5", "2", "1", "2", "", "0.0", "0.1", "0.2", "0.3", "0.5", "0.1", "0", "0.40", "0.30",
             "safety", "4"],
        ])

    def test_excluded_label_trial_is_marked(self):
        trials = ui.build_compound(self.root, "Alpha")["dimensions"]["clinical"]["postcutoff_trials_label_only"]
        self.assertEqual(trials["exclusions_source"], "data/label_role_exclusions.csv")
        self.assertIn("PROCEDURAL_CONTEXT", trials["trials"][0]["excluded_from_label"])

    def test_unmeasured_dimension_is_reported(self):
        c = ui.build_compound(self.root, "Beta")
        self.assertEqual(c["pool"]["dimensions_missing"], ["safety"])
        self.assertEqual(c["pool"]["n_dimensions_measured"], 4)
        self.assertIn("neutral 0.5", c["dimensions"]["safety"]["not_measured"])
        self.assertNotIn("not_measured", c["dimensions"]["proximity"])
        self.assertIn("NOT efficacy", c["pool"]["label_meaning"])


class TestOverviewRankingAgents(UITestBase):
    """2026-10-15 endpoints: overview, ranking, agent inventory, 10d conflicts (D-014, D-015)."""

    def setUp(self):
        super().setUp()
        build_fixture(self.root)
        d = os.path.join(self.root, "data")
        write_csv(os.path.join(d, "bootstrap_ci_equal5d_vs_4d.csv"),
                  ["a", "b", "auroc_a", "ci_a_low", "ci_a_high", "auroc_b", "ci_b_low", "ci_b_high", "diff",
                   "ci_diff_low", "ci_diff_high", "p_diff_gt_0", "n_boot", "seed"],
                  [["VPS_equal_5d", "VPS_equal", "0.7", "0.6", "0.8", "0.65", "0.5", "0.75", "0.05", "-0.02",
                    "0.12", "0.9", "2000", "42"]])
        with open(os.path.join(d, "conflict_context.json"), "w") as fh:
            json.dump({"agent_version": "10d-test", "integration": "diagnostic", "status_counts": {"INSUFFICIENT": 1},
                       "records": [{"compound": "Alpha", "status": "CROSS_DOMAIN_TENSION", "claims": [],
                                    "comparisons": [], "coverage": {"curated_claims": 1}},
                                   {"compound": "Beta", "status": "INSUFFICIENT", "claims": [], "comparisons": [],
                                    "coverage": {}}]}, fh)

    def test_overview_reads_saved_ci_and_counts(self):
        o = ui.build_overview(self.root)
        self.assertEqual(o["cohort"], {"compounds": 2, "positives": 1, "negatives": 1})
        self.assertEqual(o["primary_ci"]["ci_diff_low"], -0.02)
        self.assertIn("not therapeutic efficacy", o["endpoint"])
        self.assertEqual(o["conflicts"]["status_counts"], {"INSUFFICIENT": 1})

    def test_overview_reports_missing_ci_artefact(self):
        os.remove(os.path.join(self.root, "data", "bootstrap_ci_equal5d_vs_4d.csv"))
        self.assertEqual(ui.build_overview(self.root)["primary_ci"]["status"], "artefact missing")

    def test_ranking_orders_by_primary_score_and_carries_10d_status(self):
        r = ui.build_ranking(self.root)
        self.assertEqual([x["compound"] for x in r["rows"]], ["Alpha", "Beta"])
        self.assertEqual(r["rows"][0]["conflict_status"], "CROSS_DOMAIN_TENSION")
        self.assertEqual(r["rows"][0]["rank"], 1)

    def test_agent_status_is_derived_not_asserted(self):
        a = {x["id"]: x for x in ui.build_agents(self.root)["agents"]}
        # the fixture repo has no scripts: nothing may be reported as implemented
        self.assertTrue(all(x["status"] == "not implemented" for x in a.values()))
        real = {x["id"]: x for x in ui.build_agents(ROOT)["agents"]}
        self.assertTrue(real["10e"]["status"].startswith("implemented + tested; diagnostic"))   # built 2026-10-15
        self.assertFalse(real["10e"]["integrated_in_vps"])
        self.assertTrue(real["10h"]["status"].startswith("implemented + tested; diagnostic"))   # built 2026-10-15
        self.assertFalse(real["10h"]["integrated_in_vps"])
        self.assertEqual(real["10b"]["status"], "integrated in VPS")
        self.assertTrue(real["10d"]["status"].startswith("implemented + tested; diagnostic"))
        self.assertFalse(real["10d"]["integrated_in_vps"])

    def test_conflicts_endpoint_hides_insufficient_and_compound_gets_10d_block(self):
        c = ui.build_conflicts(self.root)
        self.assertEqual([r["compound"] for r in c["records"]], ["Alpha"])
        self.assertEqual(ui.build_compound(self.root, "Alpha")["conflict_context"]["status"], "CROSS_DOMAIN_TENSION")
        os.remove(os.path.join(self.root, "data", "conflict_context.json"))
        self.assertEqual(ui.build_compound(self.root, "Alpha")["conflict_context"]["status"], "artefact missing")


class TestCaseStatusEvaluationRisks(UITestBase):
    """Case-study ledger, evaluation report, risk panel and run metadata (2026-10-15)."""

    def test_missing_artefacts_are_reported_not_invented(self):
        build_fixture(self.root)
        for fn, key in ((ui.build_case_status, "cases"), (ui.build_evaluation, None), (ui.build_runmeta, None)):
            out = fn(self.root)
            self.assertEqual(out["status"], "artefact missing", fn.__name__)
            if key:
                self.assertEqual(out[key], [])

    def test_evaluation_flags_stale_inputs(self):
        build_fixture(self.root)
        with open(os.path.join(self.root, "data", "vps_evaluation_report.json"), "w") as fh:
            json.dump({"inputs": {"data/vps_scores_v2.csv": "0" * 32}}, fh)
        self.assertEqual(ui.build_evaluation(self.root)["stale_inputs"], ["data/vps_scores_v2.csv"])

    def test_resolved_error_entries_leave_the_risk_panel(self):
        os.makedirs(os.path.join(self.root, "development_log"))
        with open(os.path.join(self.root, "development_log", "ERRORS_AND_BLOCKERS.md"), "w") as fh:
            fh.write("### B-009 · BLOCKER · open thing\nbody\n### E-099 · BLOCKER · old thing\n- Update: RESOLVED\n")
        ids = [i["id"] for i in ui.build_risks(self.root)["open_high"]]
        self.assertEqual(ids, ["B-009"])

    def test_cases_view_appends_panels_instead_of_overwriting(self):
        # regression 2026-10-15: the 10d ledger assignment replaced the case-status table
        js = pathlib.Path(os.path.join(ROOT, "ui", "app.js")).read_text()
        body = js[js.index("async function viewCases"):js.index("async function viewValidation")]
        self.assertEqual(len(re.findall(r"\bledger\s*=(?!=)", body)), 1)      # only the initialisation

    def test_real_case_ledger_identifiers_trace_to_case_studies(self):
        with open(os.path.join(ROOT, "data", "case_study_status.json")) as fh:
            ledger = fh.read()
        with open(os.path.join(ROOT, "docs", "CASE_STUDIES.md"), encoding="utf-8") as fh:
            doc = fh.read()
        ids = set(re.findall(r"(?:PMID |)(NCT\d{8}|\b\d{7,8}\b)", ledger))
        self.assertTrue(ids)
        for i in ids:
            self.assertIn(i, doc, i)
        cases = {c["compound"] for c in ui.build_case_status(ROOT)["cases"]}
        self.assertEqual(cases, {"Donepezil", "Melatonin", "Domperidone", "Propofol", "Norepinephrine",
                                 "Dopamine", "Propranolol", "Droxidopa"})


class TestCompletenessEvidenceViews(UITestBase):
    """Agent 10h in the UI, the evidence index, the candidate summary (2026-10-15)."""

    def test_missing_10h_output_is_reported_not_invented(self):
        build_fixture(self.root)
        self.assertEqual(ui.build_gaps(self.root)["status"], "artefact missing")
        self.assertEqual(ui.build_compound(self.root, "Alpha")["completeness"]["status"], "artefact missing")

    def test_10h_staleness_is_flagged(self):
        build_fixture(self.root)
        with open(os.path.join(self.root, "data", "completeness_gaps.json"), "w") as fh:
            json.dump({"inputs": {"data/vps_scores_v2.csv": "0" * 32}, "records": [
                {"compound": "Alpha", "domains": {"safety": {"state": "ABSENT_AT_SOURCE", "detail": "x"}}, "gaps": []}]}, fh)
        g = ui.build_gaps(self.root)
        self.assertEqual(g["stale_inputs"], ["data/vps_scores_v2.csv"])
        self.assertEqual(g["rows"][0]["states"], {"safety": "ABSENT_AT_SOURCE"})
        self.assertEqual(ui.build_compound(self.root, "Alpha")["completeness"]["stale_inputs"], ["data/vps_scores_v2.csv"])

    def test_summary_says_rank_is_not_efficacy_and_lists_unmeasured(self):
        build_fixture(self.root)
        s = ui.build_compound(self.root, "Alpha")["summary"]
        self.assertIn("not a probability and not evidence of efficacy", s["text"])
        self.assertTrue(s["text"].startswith("Ranked 1 of 2"))

    def test_evidence_index_uses_only_persisted_identifiers(self):
        build_fixture(self.root)
        e = ui.build_evidence(self.root)
        ids = {i["id"] for i in e["items"] if i["type"] == "clinical"}
        self.assertEqual(ids, {"NCT00000001", "NCT00000002"})
        self.assertNotIn("safety", e["counts"])              # no safety artefact in the fixture -> nothing invented

    def test_real_10h_record_reaches_the_candidate_view(self):
        d = ui.build_compound(ROOT, "Domperidone")
        if d["completeness"].get("status"):
            self.skipTest("10h output not generated")
        self.assertEqual(d["completeness"]["domains"]["safety"]["state"], "ABSENT_AT_SOURCE")
        self.assertIn("safety", d["summary"]["not_measured"])
        self.assertEqual(d["completeness"]["stale_inputs"], [])

    def test_external_links_only_through_validated_patterns(self):
        js = pathlib.Path(os.path.join(ROOT, "ui", "app.js")).read_text()
        hrefs = re.findall(r'href="https?://', js)
        self.assertEqual(hrefs, [])                          # absolute URLs only come from LINKS via extLink()
        self.assertIn('rel="noopener noreferrer"', js)
        for pat in ("^NCT\\d{8}$", "^\\d{6,9}$", "^ENSG\\d{11}$"):
            self.assertIn(pat, js)


class TestAgentContractInUI(UITestBase):
    """2026-10-15: run status / staleness from the shared envelope; 10c/10f/10g candidate blocks."""

    def test_no_envelope_no_invented_status(self):
        build_fixture(self.root)
        a = {x["id"]: x for x in ui.build_agents(self.root)["agents"]}
        for aid in ("10c", "10d", "10e", "10f", "10g", "10h"):
            self.assertIsNone(a[aid]["run"]["run_status"], aid)
        d = ui.build_compound(self.root, "Alpha")
        for k in ("clinical_evidence", "safety_evidence", "evidence_independence"):
            self.assertEqual(d[k]["status"], "artefact missing")

    def test_envelope_status_and_staleness(self):
        build_fixture(self.root)
        env = {"agent_id": "10f", "agent": "S", "agent_version": "1", "schema_version": "1", "run_status": "PARTIAL",
               "generated_utc": "2026-10-15T00:00:00+00:00", "inputs": {"data/vps_scores_v2.csv": "0" * 32},
               "coverage": {}, "limitations": [], "diagnostics": [{"level": "warn", "code": "X", "message": "m"}],
               "records": [{"compound": "Alpha", "label": {"state": "NO_RECORD"}, "faers": {"state": "FAILED"}}]}
        with open(os.path.join(self.root, "data", "safety_evidence.json"), "w") as fh:
            json.dump(env, fh)
        a = {x["id"]: x for x in ui.build_agents(self.root)["agents"]}
        self.assertEqual(a["10f"]["run"]["run_status"], "STALE")              # recorded input changed
        self.assertEqual(a["10f"]["run"]["outputs"][0]["diagnostics"][0]["code"], "X")
        d = ui.build_compound(self.root, "Alpha")["safety_evidence"]
        self.assertEqual((d["faers"]["state"], d["stale_inputs"]), ("FAILED", ["data/vps_scores_v2.csv"]))
        self.assertEqual(ui.build_compound(self.root, "Beta")["safety_evidence"]["status"], "compound not covered by this agent")

    def test_real_agents_report_layer_status(self):
        a = {x["id"]: x for x in ui.build_agents(ROOT)["agents"]}
        for aid, via in (("10c", "stage 03"), ("10f", "stage 05"), ("10g", "stage 04")):
            self.assertEqual(a[aid]["status"], f"implemented + tested; {via} output in VPS, agent layer diagnostic")
        for aid in ("10a", "10b", "10c", "10d", "10e", "10f", "10g", "10h"):
            if a[aid]["run"]["run_status"] is not None:
                self.assertIn(a[aid]["run"]["run_status"], ("SUCCESS", "PARTIAL", "NO_EVIDENCE", "FAILED", "STALE"))


class TestLiveStatus(UITestBase):
    """2026-10-15: /api/status drives live updates; it must be cheap, read-only and honest."""

    def test_candidates_are_listed_as_pending_and_never_displayed(self):
        build_fixture(self.root)
        cdir = os.path.join(self.root, "data", "_candidates", "cand_x")
        os.makedirs(cdir)
        with open(os.path.join(cdir, "verification.json"), "w") as fh:
            json.dump({"all_pass": True}, fh)
        with open(os.path.join(cdir, "vps_scores_v2.csv"), "w") as fh:
            fh.write("compound_name,VPS_equal_5d\nZeta,0.99\n")             # must never reach the views
        st = ui.build_status(self.root)
        self.assertEqual(st["pending_candidates"], [{"name": "cand_x", "path": "data/_candidates/cand_x",
                                                     "independently_verified": True, "approved": False, "displayed": False,
                                                     "compared": False}])            # no comparison.json in this fixture
        self.assertEqual(st["approved_baseline"]["path"], "data/vps_scores_v2.csv")
        self.assertNotIn("Zeta", json.dumps(ui.list_compounds(self.root)))

    def test_status_without_manifest_is_untracked_not_success(self):
        build_fixture(self.root)
        st = ui.build_status(self.root)
        self.assertIn(st["vps"]["status"], ("UNTRACKED", "NOT_RUN"))
        self.assertFalse(st["vps"]["fresh"])
        self.assertIsNone(st["vps"]["displayed_run_id"])
        self.assertFalse(os.path.exists(os.path.join(self.root, "data", "run_manifest.json")))   # reading never writes

    def test_data_version_changes_with_outputs_only(self):
        build_fixture(self.root)
        v1 = ui.build_status(self.root)["data_version"]
        self.assertEqual(ui.build_status(self.root)["data_version"], v1)
        p = os.path.join(self.root, "data", "vps_scores_v2.csv")
        with open(p, "a") as fh:
            fh.write("\n")
        self.assertNotEqual(ui.build_status(self.root)["data_version"], v1)

    def test_vps_states_from_manifest(self):
        build_fixture(self.root)
        import run_stage as rs
        s06 = next(s_ for s_ in ui.STAGES if s_["id"] == "06")
        for rel in s06["outputs"]:                                        # adoption needs every declared output
            p = os.path.join(self.root, rel)
            if not os.path.exists(p):
                with open(p, "w") as fh:
                    fh.write("x\n1\n")
        rs.adopt(self.root, ui.STAGES)
        st = ui.build_status(self.root)
        self.assertEqual(st["vps"]["status"], "ADOPTED")
        with open(os.path.join(self.root, "data", "safety_signal.csv"), "w") as fh:
            fh.write("compound_name,has_label\nAlpha,True\n")              # a VPS input changes
        st = ui.build_status(self.root)
        self.assertEqual(st["vps"]["status"], "STALE")
        self.assertTrue(any("data/safety_signal.csv" in r for r in st["vps"]["reasons"]))

    def test_client_polls_only_the_status_endpoint(self):
        js = pathlib.Path(os.path.join(ROOT, "ui", "app.js")).read_text()
        self.assertIn('api("/api/status")', js)
        self.assertIn("visibilitychange", js)                              # slows down when hidden
        self.assertNotRegex(js, r"setInterval|WebSocket|EventSource")        # one timer chain, no push channel
        self.assertRegex(js, r"POLL_MS = \d{4}")
        self.assertIn('href="#run" role="status"', pathlib.Path(os.path.join(ROOT, "ui", "index.html")).read_text())

    def test_requests_time_out_and_polling_always_reschedules(self):
        # A suspended server accepts the connection and never answers: without a timeout the poll
        # awaits forever and live updates stop silently.
        with open(os.path.join(ROOT, "ui", "app.js")) as fh:
            js = fh.read()
        api = js[js.index("async function api("):js.index("const errBox")]
        self.assertIn("signal: ctl.signal", api)
        self.assertRegex(api, r"setTimeout\(\(\) => ctl\.abort\(\), API_TIMEOUT_MS\)")
        poll = js[js.index("async function poll()"):js.index("async function pollOnce()")]
        self.assertRegex(poll, r"finally \{[\s\S]*pollTimer = setTimeout\(poll, wait\)")


class TestMissingArtefacts(UITestBase):
    def test_empty_repo_reports_missing_not_fabricated(self):
        p = ui.build_pipeline(self.root)
        statuses = {s["id"]: s["status"] for s in p["stages"]}
        self.assertTrue(all(v == "missing" for v in statuses.values()), statuses)
        for s in p["stages"]:
            for o in s["outputs"]:
                self.assertFalse(o["exists"])
                self.assertNotIn("records", o)
                self.assertNotIn("modified", o)

    def test_empty_repo_compound_has_no_scores(self):
        c = ui.build_compound(self.root, "Droxidopa")
        self.assertFalse(c["known"])
        self.assertFalse(c["pool"]["in_evaluable_pool"])
        self.assertNotIn("record", c["dimensions"]["proximity"])
        self.assertIn("missing", c["dimensions"]["proximity"]["status"])
        self.assertIn("data/vps_scores_v2.csv", c["pool"]["reason"])

    def test_empty_repo_validation_and_compounds(self):
        v = ui.build_validation(self.root)
        self.assertIn("missing", v["variants"]["status"])
        self.assertEqual(v["figures"], [])
        self.assertEqual(ui.list_compounds(self.root)["compounds"], [])

    def test_partial_outputs_are_partial(self):
        build_fixture(self.root)
        s = {s["id"]: s for s in ui.build_pipeline(self.root)["stages"]}
        self.assertEqual(s["06"]["status"], "partial")   # only vps_scores_v2.csv exists
        self.assertEqual(s["02"]["status"], "available")

    def test_stale_output_detected(self):
        build_fixture(self.root)
        out = os.path.join(self.root, "data", "network_proximity.csv")
        inp = os.path.join(self.root, "data", "pd_candidates_filtered.csv")
        write_csv(inp, ["compound_name"], [["Alpha"]])
        os.utime(out, (1_000_000, 1_000_000))
        s = {s["id"]: s for s in ui.build_pipeline(self.root)["stages"]}
        self.assertEqual(s["02"]["status"], "input_newer")             # a hint, not a freshness verdict


class TestEvidenceReading(UITestBase):
    def setUp(self):
        super().setUp()
        build_fixture(self.root)

    def test_reads_each_dimension_from_its_artefact(self):
        c = ui.build_compound(self.root, "alpha")   # case-insensitive lookup
        D = c["dimensions"]
        self.assertTrue(c["pool"]["in_evaluable_pool"])
        self.assertEqual(c["pool"]["label"], 1.0)
        self.assertEqual(D["proximity"]["record"]["proximity_z"], "-1.0")
        self.assertEqual(D["proximity"]["source"], "data/network_proximity.csv")
        self.assertEqual([t["nct_id"] for t in D["clinical"]["precutoff_trials_feature"]["trials"]], ["NCT00000001"])
        self.assertEqual([t["nct_id"] for t in D["clinical"]["postcutoff_trials_label_only"]["trials"]],
                         ["NCT00000002"])
        self.assertEqual(D["molecular"]["record"]["chembl_id"], "CHEMBL0")
        self.assertEqual(D["molecular"]["evidence_chain"]["explanation"], "score = fixture")
        self.assertEqual(D["molecular"]["evidence_chain"]["malformed_lines_skipped"], 1)
        self.assertEqual(c["pool"]["fused_scores"]["VPS_equal_5d"]["rank"], 1)

    def test_post_cutoff_trials_never_shown_as_feature(self):
        D = ui.build_compound(self.root, "Alpha")["dimensions"]["clinical"]
        pre = {t["nct_id"] for t in D["precutoff_trials_feature"]["trials"]}
        self.assertNotIn("NCT00000002", pre)

    def test_absent_fields_stay_absent(self):
        D = ui.build_compound(self.root, "Beta")["dimensions"]
        self.assertEqual(D["molecular"]["status"], "no record for this compound")
        self.assertNotIn("record", D["molecular"])
        self.assertEqual(D["literature"]["status"], "artefact missing")
        # fields not present in the CSV are not invented
        self.assertNotIn("n_random", D["proximity"]["record"])

    def test_compound_only_in_audit_is_known_but_not_in_pool(self):
        c = ui.build_compound(self.root, "Gamma")
        self.assertTrue(c["known"])
        self.assertFalse(c["pool"]["in_evaluable_pool"])
        self.assertEqual(c["dimensions"]["clinical"]["match_audit"]["decisions"][0]["outcome"], "NO_MATCH")
        names = {x["name"]: x["in_pool"] for x in ui.list_compounds(self.root)["compounds"]}
        self.assertEqual(names, {"Alpha": True, "Beta": True, "Gamma": False})

    def test_validation_integrity_counts(self):
        I = ui.build_validation(self.root)["integrity"]
        self.assertEqual((I["rows"], I["positives"], I["negatives"], I["duplicate_compounds"]), (2, 1, 1, 0))


class TestMalformedInput(UITestBase):
    def test_malformed_and_nonfinite_values_do_not_crash(self):
        d = os.path.join(self.root, "data")
        write_csv(os.path.join(d, "vps_scores_v2.csv"), VPS_HEADER + ["extra"], [
            ["Alpha", "nan", "x", "", "inf", "", "", "", "", "", "", "", "1", "not-a-number", "", "too", "many"],
            ["Alpha"],                       # short row, duplicate name
        ])
        with open(os.path.join(d, "literature_graph_alpha.json"), "w") as fh:
            fh.write("{broken")
        with open(os.path.join(d, "molecular_pathway_evidence.jsonl"), "w") as fh:
            fh.write("[]\n\n{\"drug\": 5}\n")
        c = ui.build_compound(self.root, "Alpha")
        self.assertEqual(c["pool"]["duplicates"], 1)
        self.assertIsNone(c["pool"]["fused_scores"]["VPS_equal"]["score"])
        self.assertIn("unreadable", c["dimensions"]["literature"]["paper_graph"]["status"])
        I = ui.build_validation(self.root)["integrity"]
        self.assertEqual(I["duplicate_compounds"], 1)
        self.assertEqual(I["missing_or_nonfinite_by_column"]["VPS_equal"], 2)
        json.dumps(c)   # serialisable

    def test_num_rejects_nonfinite(self):
        for bad in ("nan", "inf", "-inf", "", None, "abc"):
            self.assertIsNone(ui.num(bad))
        self.assertEqual(ui.num("0.5"), 0.5)


class TestRunLog(UITestBase):
    """/api/log: one tracked run's log tail, redacted, confined to data/_runs/<valid run id>/log.txt."""

    RID = "20261020T010203Z-10h-ab12"

    def setUp(self):
        super().setUp()
        d = os.path.join(self.root, "data", "_runs", self.RID)
        os.makedirs(d)
        with open(os.path.join(d, "log.txt"), "w") as fh:
            fh.write("".join(f"line {i}\n" for i in range(200)) + "NCBI_API_KEY=leakme123\nTraceback: boom\n")
        with open(os.path.join(self.root, "data", "secret.txt"), "w") as fh:
            fh.write("not a log\n")
        self.live = _LiveServer(self.root)

    def tearDown(self):
        self.live.close()
        super().tearDown()

    def test_tail_is_bounded_and_redacted(self):
        status, _, body = self.live.request(f"/api/log?run_id={self.RID}")
        self.assertEqual(status, 200)
        r = _strict_json(body)
        self.assertEqual(r["tail_lines"], ui.LOG_TAIL_LINES)
        self.assertIn("Traceback: boom", r["tail"])
        self.assertNotIn("line 0\n", r["tail"])
        self.assertNotIn("leakme123", body.decode())
        self.assertEqual(r["log"], f"data/_runs/{self.RID}/log.txt")

    def test_only_valid_run_ids_are_served(self):
        for bad in ("../secret.txt", "..%2F..%2Fdata", "20261020T010203Z-10h-ab12/../../secret.txt",
                    "nope", "", "20261020T010203Z-10h-zzzz"):
            status, _, body = self.live.request("/api/log?run_id=" + bad)
            self.assertEqual(status, 404, bad)
            self.assertNotIn("not a log", body.decode())

    def test_missing_log_is_404(self):
        status, _, _ = self.live.request("/api/log?run_id=20261020T010203Z-06-cd34")
        self.assertEqual(status, 404)


class TestAgentPanelTrackedFreshness(UITestBase):
    """The agent panel uses the run tracker's dependency-aware status: an agent whose upstream stage is STALE is
    shown STALE even though its own output and input hashes are unchanged (2026-10-20 audit, F-02)."""

    def setUp(self):
        super().setUp()
        rs = ui._runs
        self.stages = ui.STAGES
        for s in self.stages:
            for rel in s["outputs"] + s["inputs"]:
                p = os.path.join(self.root, rel)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                if not os.path.exists(p):
                    open(p, "w").close()
        m = {"stages": {s["id"]: {"last_success": {"run_id": f"r-{s['id']}", "status": "SUCCESS",
                                                  "finished_utc": "2026-10-20T00:00:00+00:00",
                                                  "inputs": rs._fps(self.root, s["inputs"]),
                                                  "outputs": rs._fps(self.root, s["outputs"])}} for s in self.stages}}
        with open(os.path.join(self.root, rs.MANIFEST), "w") as fh:
            json.dump(m, fh)

    def agent(self, aid):
        return next(a for a in ui.build_agents(self.root)["agents"] if a["id"] == aid)

    def test_fresh_then_stale_when_vps_inputs_change(self):
        self.assertEqual(self.agent("10f")["tracked_status"], "SUCCESS")
        with open(os.path.join(self.root, "data", "label_role_exclusions.csv"), "w") as fh:
            fh.write("changed\n")
        a = self.agent("10f")
        self.assertEqual(a["tracked_status"], "STALE")
        t = {x["stage"]: x for x in a["tracked_runs"]}
        self.assertIn("upstream stage stale: 06", " ".join(t["10f"]["reasons"]))
        self.assertTrue(a["vps_role"].startswith("score-contributing via stage 05"))

    def test_every_agent_has_tracked_stages_and_a_role(self):
        ids = {s["id"] for s in self.stages}
        for a in ui.build_agents(self.root)["agents"]:
            self.assertTrue(a["tracked_runs"], a["id"])
            self.assertTrue(all(t["stage"] in ids for t in a["tracked_runs"]), a["id"])
            self.assertTrue(a["vps_role"], a["id"])

    def test_unreadable_manifest_is_unknown_not_success(self):
        with open(os.path.join(self.root, ui._runs.MANIFEST), "w") as fh:
            fh.write("{not json")
        self.assertIn(self.agent("10f")["tracked_status"], ("UNKNOWN", "UNTRACKED"))


class TestCorruptManifestInUI(UITestBase):
    def test_status_endpoint_reports_error_not_500_and_never_current(self):
        os.makedirs(os.path.join(self.root, "data"))
        with open(os.path.join(self.root, "data", "run_manifest.json"), "w") as fh:
            fh.write("{broken")
        live = _LiveServer(self.root)
        try:
            status, _, body = live.request("/api/status")
        finally:
            live.close()
        self.assertEqual(status, 200)
        st = _strict_json(body)
        self.assertIn("unreadable", st["manifest_error"])
        self.assertEqual(st["vps"]["status"], "UNKNOWN")
        self.assertEqual(set(st["by_status"]) - {"ATTEMPT_FAILED"}, {"UNKNOWN"})

    def test_pill_logic_never_says_current_for_unknown_states(self):
        with open(os.path.join(ROOT, "ui", "app.js"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('st.manifest_error ? "Run records unreadable"', src)
        self.assertRegex(src, r"unknown \? `\$\{unknown\} stage\(s\) without a known run state`")


class TestPollingSingleFlight(unittest.TestCase):
    """U-02 (2026-10-20): visibilitychange during an in-flight poll started a second concurrent poll. The browser
    check (docs/autonomous_runs/evidence) holds /api/status and asserts one request; this pins the guard."""

    def test_guard_present(self):
        src = pathlib.Path(os.path.join(ROOT, "ui", "app.js")).read_text()
        body = src[src.index("async function poll()"):src.index("async function pollOnce()")]
        self.assertIn("if (pollInFlight) { pollAgain = true; return; }", body)
        self.assertLess(body.index("pollInFlight = false"), body.index("pollTimer = setTimeout(poll, wait)"))


class TestHealth(UITestBase):
    def _get(self):
        live = _LiveServer(self.root)
        try:
            status, _, body = live.request("/api/health")
        finally:
            live.close()
        return status, _strict_json(body)

    def test_ready_when_manifest_readable_and_scores_present(self):
        os.makedirs(os.path.join(self.root, "data"))
        with open(os.path.join(self.root, "data", "vps_scores_v2.csv"), "w") as fh:
            fh.write("compound_name\n")
        status, h = self._get()
        self.assertEqual((status, h["live"], h["ready"], h["manifest"]), (200, True, True, "readable"))

    def test_not_ready_on_corrupt_manifest(self):
        os.makedirs(os.path.join(self.root, "data"))
        for rel, body in (("data/vps_scores_v2.csv", "compound_name\n"), ("data/run_manifest.json", "{x")):
            with open(os.path.join(self.root, rel), "w") as fh:
                fh.write(body)
        status, h = self._get()
        self.assertEqual((status, h["live"], h["ready"], h["manifest"]), (503, True, False, "unreadable"))
        self.assertNotIn(self.root, json.dumps(h))


class TestLivePipelineClientRules(unittest.TestCase):
    """Pins the Live pipeline client behaviour proven in the browser run (docs/autonomous_runs/evidence/
    ui_live_pipeline_e2e.json): stale-nonce renewal after a server restart, click-safe background refresh,
    no launch on load, and no fabricated percentage."""

    def setUp(self):
        self.src = pathlib.Path(os.path.join(ROOT, "ui", "app.js")).read_text()

    def test_stale_nonce_is_renewed_once_and_retried(self):
        body = self.src[self.src.index("async function livePost"):self.src.index("async function viewLive")]
        self.assertIn("for (let attempt = 0; attempt < 2; attempt++)", body)
        self.assertIn("await liveSessionGet(attempt > 0)", body)

    def test_identical_background_render_leaves_dom_alone(self):
        body = self.src[self.src.index("async function route"):]
        self.assertIn("if (opts.keepScroll && res.html === lastRenderedHtml)", body)

    def test_only_a_click_posts_and_no_percentage_is_rendered(self):
        live = self.src[self.src.index("async function viewLive"):self.src.index("// ---------- router ----------")]
        self.assertNotIn("livePost(", live.split("const after = () => {")[0])     # rendering never posts
        self.assertNotRegex(live, r"%\s*(complete|done)|progress\s*bar|<progress")


class TestSecrets(UITestBase):
    def test_redact_values_keeps_names(self):
        text = ("NCBI_API_KEY='abc123realkey' and \"api-key\":\"zzz999\" and "
                "https://x/esearch.fcgi?db=pubmed&api_key=SECRET42&term=x and MY_TOKEN=tok_77")
        out = ui.redact(text)
        for secret in ("abc123realkey", "zzz999", "SECRET42", "tok_77"):
            self.assertNotIn(secret, out)
        self.assertIn("NCBI_API_KEY", out)
        self.assertIn("[REDACTED]", out)

    def test_docs_are_redacted_and_env_never_read(self):
        os.makedirs(os.path.join(self.root, "docs"), exist_ok=True)
        with open(os.path.join(self.root, "docs", "CASE_STUDIES.md"), "w") as fh:
            fh.write("export NCBI_API_KEY=supersecretvalue123\n")
        with open(os.path.join(self.root, ".env"), "w") as fh:
            fh.write("NCBI_API_KEY=envfilesecret\n")
        doc = ui.read_doc(self.root, "CASE_STUDIES")
        self.assertNotIn("supersecretvalue123", doc["text"])
        self.assertIsNone(ui.read_doc(self.root, ".env"))
        self.assertIsNone(ui.read_doc(self.root, "../.env"))
        with mock.patch.dict(os.environ, {"NCBI_API_KEY": "fromenvironment999"}):
            blob = json.dumps([ui.build_pipeline(self.root), ui.build_validation(self.root)])
        self.assertNotIn("fromenvironment999", blob)
        self.assertNotIn("envfilesecret", blob)

    def test_server_source_never_reads_environment_values(self):
        src = pathlib.Path(os.path.join(ROOT, "ui", "server.py")).read_text()
        self.assertNotRegex(src, r"os\.environ|getenv|dotenv")


class TestNoExternalRequests(UITestBase):
    def test_building_views_opens_no_socket(self):
        build_fixture(self.root)
        with _NoNetwork():
            ui.build_pipeline(self.root)
            ui.build_compound(self.root, "Alpha")
            ui.list_compounds(self.root)
            ui.build_validation(self.root)
            ui.read_doc(self.root, "README")

    def test_ui_imports_no_http_client(self):
        src = pathlib.Path(os.path.join(ROOT, "ui", "server.py")).read_text()
        self.assertNotRegex(src, r"import requests|urllib\.request|http\.client|import socket")

    def test_page_loads_no_third_party_resource(self):
        for fn in ("index.html", "app.js", "style.css"):
            text = pathlib.Path(os.path.join(ROOT, "ui", fn)).read_text()
            self.assertNotRegex(text, r"<(script|link|img|iframe)[^>]+(src|href)=[\"']https?://", fn)
            self.assertNotRegex(text, r"fetch\([\"'`]https?://", fn)
            self.assertNotRegex(text, r"@import|url\(\s*[\"']?https?:", fn)
            self.assertNotRegex(text, r"setInterval|XMLHttpRequest|WebSocket|EventSource", fn)   # no auto-refresh

    def test_live_server_is_read_only_and_serves_local_json(self):
        build_fixture(self.root)
        srv = ui.ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(self.root))
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            with _NoNetwork():
                body = urllib.request.urlopen(base + "/api/compound?name=Alpha").read()
                self.assertEqual(json.loads(body)["pool"]["label"], 1.0)
                csp = urllib.request.urlopen(base + "/").headers["Content-Security-Policy"]
                self.assertIn("connect-src 'self'", csp)
                for path in ("/figure/../../etc/passwd", "/figure/vps_scores_v2.csv", "/api/doc?key=.env"):
                    with self.assertRaises(urllib.error.HTTPError) as cm:
                        urllib.request.urlopen(base + path)
                    self.assertEqual(cm.exception.code, 404)
                req = urllib.request.Request(base + "/api/pipeline", method="POST", data=b"x")
                with self.assertRaises(urllib.error.HTTPError) as cm:
                    urllib.request.urlopen(req)
                self.assertEqual(cm.exception.code, 405)
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, "data"))),
                         sorted(["vps_scores_v2.csv", "network_proximity.csv",
                                 "clinical_maturity_precutoff_clean.csv", "ground_truth_postcutoff_clean.csv",
                                 "clinicaltrials_match_audit.csv", "molecular_pathway.csv",
                                 "molecular_pathway_evidence.jsonl"]))


class TestRegistryMatchesCode(unittest.TestCase):
    """The Agents & Data Sources view must not drift from the scripts."""

    def _source(self, stage):
        text = ""
        for rel in [stage["script"]] + stage.get("related_scripts", []):
            with open(os.path.join(ROOT, rel)) as fh:
                text += fh.read()
        return text

    def test_scripts_exist(self):
        for s in ui.STAGES:
            for rel in [s["script"]] + s.get("related_scripts", []):
                self.assertTrue(os.path.exists(os.path.join(ROOT, rel)), rel)

    def test_paths_and_endpoints_appear_in_script_source(self):
        for s in ui.STAGES:
            src = self._source(s)
            for p in s["outputs"] + ([s["checkpoint"]] if s["checkpoint"] else []):
                self.assertTrue(_needle_in(p, src), f"{s['id']}: {p} not found in {s['script']}")
            for p in s["inputs"]:
                self.assertTrue(_needle_in(p, src), f"{s['id']}: input {p} not in {s['script']}")
            for a in s["apis"]:
                if a["endpoint"].startswith("http") or a["endpoint"] == "OpenTargetsClient":
                    self.assertIn(a["endpoint"], src, f"{s['id']}: {a['endpoint']}")
            for e in s["env"]:
                self.assertIn(e, src)

    def test_dimension_rank_columns_match_stage_06(self):
        src = pathlib.Path(os.path.join(ROOT, "scripts", "06_vps_fusion.py")).read_text()
        for d in ui.DIMENSIONS:
            self.assertIn(f'df["{d["rank"]}"]', src)
            self.assertIn(d["raw"], src)

    def test_confidence_never_described_as_probability_of_efficacy(self):
        blob = json.dumps(ui.DIMENSIONS).lower() + "".join(
            pathlib.Path(os.path.join(ROOT, "ui", fn)).read_text().lower() for fn in ("index.html", "app.js"))
        self.assertIn("not a probability of efficacy", blob)
        self.assertIsNone(re.search(r"probability (that|of) (the drug )?(works|efficacy)(?! )", blob.replace(
            "not a probability of efficacy", "").replace("not the probability that the drug works", "")))


class _LiveServer:
    """Serve a fixture root on an ephemeral loopback port for one test."""

    def __init__(self, root):
        self.srv = ui.ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(root))
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def request(self, path, method="GET", host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Host": host} if host else {}
        conn.request(method, path, headers=headers)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, {k.lower(): v for k, v in resp.getheaders()}, body

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


def _strict_json(body):
    def reject(token):
        raise ValueError(f"non-standard JSON constant {token}")
    return json.loads(body, parse_constant=reject)


class TestSecurityHardening(UITestBase):
    """Regression tests for the 2026-10-13 UI security audit (TD-029)."""

    def setUp(self):
        super().setUp()
        build_fixture(self.root)
        self.live = _LiveServer(self.root)

    def tearDown(self):
        self.live.close()
        super().tearDown()

    # -- information disclosure -------------------------------------------
    def test_unreadable_doc_error_has_no_absolute_path(self):
        os.makedirs(os.path.join(self.root, "README.md"))          # open() -> IsADirectoryError
        status, _, body = self.live.request("/api/doc?key=README")
        text = body.decode()
        self.assertNotEqual(status, 500)
        self.assertNotIn(self.root, text)
        self.assertNotIn(os.path.realpath(self.root), text)
        self.assertIn("unreadable", _strict_json(body)["status"])

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root ignores file permissions")
    def test_unreadable_artefact_error_has_no_absolute_path(self):
        path = os.path.join(self.root, "data", "vps_scores_v2.csv")
        os.chmod(path, 0)
        try:
            status, _, body = self.live.request("/api/compound?name=Alpha")
        finally:
            os.chmod(path, 0o600)
        self.assertEqual(status, 200)
        self.assertNotIn(self.root, body.decode())
        self.assertNotIn(os.path.realpath(self.root), body.decode())
        self.assertIn("unreadable (PermissionError)", _strict_json(body)["pool"]["reason"])

    def test_unexpected_exception_hides_message_and_path(self):
        leak = os.path.join(self.root, "data", "secret_location.csv")
        with mock.patch.object(ui, "build_validation", side_effect=OSError(2, "No such file", leak)), \
                mock.patch("sys.stderr"):
            status, _, body = self.live.request("/api/validation")
        self.assertEqual(status, 500)
        self.assertNotIn(leak, body.decode())
        self.assertNotIn("secret_location", body.decode())
        self.assertIn("FileNotFoundError", _strict_json(body)["error"])

    def test_home_directory_and_repo_paths_redacted(self):
        os.makedirs(os.path.join(self.root, "docs"), exist_ok=True)
        with open(os.path.join(self.root, "docs", "CASE_STUDIES.md"), "w") as fh:
            fh.write(f"run from {self.root}/data and /Users/alice/x and /home/bob/y\n")
        status, _, body = self.live.request("/api/doc?key=CASE_STUDIES")
        text = _strict_json(body)["text"]
        for needle in (self.root, "alice", "bob"):
            self.assertNotIn(needle, text)
        self.assertIn("<repo>/data", text)
        self.assertIn("/Users/<user>/x", text)

    def test_server_header_does_not_advertise_python(self):
        _, headers, _ = self.live.request("/api/dimensions")
        self.assertNotIn("python", headers.get("server", "").lower())

    # -- network exposure ---------------------------------------------------
    def test_non_loopback_host_header_is_refused(self):
        port = self.live.port
        for host in ("evil.example", f"evil.example:{port}", f"192.168.1.10:{port}", ""):
            status, _, body = self.live.request("/api/pipeline", host=host or " ")
            self.assertEqual(status, 403, host)
            self.assertNotIn(b"stages", body)
        for host in (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}", "localhost"):
            status, _, _ = self.live.request("/api/dimensions", host=host)
            self.assertEqual(status, 200, host)

    def test_cli_refuses_non_loopback_bind(self):
        for host in ("0.0.0.0", "::", "192.168.1.10", "example.org"):
            with mock.patch.object(ui, "ThreadingHTTPServer") as srv, mock.patch("sys.stderr"):
                with self.assertRaises(SystemExit):
                    ui.main(["--host", host, "--port", "0", "--root", self.root])
                srv.assert_not_called()

    def test_default_bind_is_loopback(self):
        with mock.patch.object(ui, "ThreadingHTTPServer") as srv, mock.patch("builtins.print"):
            srv.return_value.serve_forever.side_effect = KeyboardInterrupt
            ui.main(["--root", self.root])
        self.assertEqual(srv.call_args[0][0], ("127.0.0.1", 8765))

    # -- file access ---------------------------------------------------------
    def test_compound_query_cannot_steer_graph_read_outside_data(self):
        # Original code built data/literature_graph_<raw query>.json, so with any
        # data/literature_graph_* directory present a query could read other .json.
        os.makedirs(os.path.join(self.root, "data", "literature_graph_x"))
        with open(os.path.join(self.root, "outside.json"), "w") as fh:
            json.dump({"nodes": [{"title": "OUTSIDE-DATA"}], "edges": []}, fh)
        for name in ("x/../../outside", "X/../../outside", "../outside", "x\\..\\..\\outside"):
            res = ui.build_compound(self.root, name)
            blob = json.dumps(res)
            self.assertNotIn("OUTSIDE-DATA", blob, name)
            self.assertNotIn("outside", res["dimensions"]["literature"]["paper_graph"]["source"], name)

    def test_graph_is_still_found_for_a_real_compound(self):
        with open(os.path.join(self.root, "data", "literature_graph_alpha.json"), "w") as fh:
            json.dump({"nodes": [{"pmid": "1", "title": "t"}], "edges": [], "counts": {"n": 1}}, fh)
        g = ui.build_compound(self.root, "alpha")["dimensions"]["literature"]["paper_graph"]
        self.assertEqual(g["source"], "data/literature_graph_alpha.json")
        self.assertEqual(len(g["papers"]), 1)

    def test_figure_route_rejects_traversal_symlink_and_non_figures(self):
        outside = os.path.join(self.root, "outside.png")
        with open(outside, "wb") as fh:
            fh.write(b"\x89PNG-outside")
        os.symlink(outside, os.path.join(self.root, "data", "figure9_link.png"))
        for path in ("/figure/figure9_link.png", "/figure/..%2Foutside.png", "/figure/../outside.png",
                     "/figure/vps_scores_v2.csv", "/figure/sub/figure1.png"):
            status, _, body = self.live.request(path)
            self.assertEqual(status, 404, path)
            self.assertNotIn(b"PNG-outside", body)

    # -- methods, headers, serialisation -------------------------------------
    def test_non_get_methods_are_405_json_with_security_headers(self):
        for method in ("HEAD", "OPTIONS", "PUT", "DELETE", "PATCH", "POST", "TRACE"):
            status, headers, body = self.live.request("/api/pipeline", method=method)
            self.assertEqual(status, 405, method)
            self.assertIn("content-security-policy", headers, method)
            if method != "HEAD":
                self.assertEqual(_strict_json(body)["error"], "read-only: GET only")

    def test_favicon_is_204_with_security_headers(self):
        status, headers, body = self.live.request("/favicon.ico")
        self.assertEqual((status, body), (204, b""))
        self.assertIn("content-security-policy", headers)

    def test_malformed_request_gets_json_error_not_html(self):
        status, headers, body = self.live.request("/" + "a" * 70000)
        self.assertGreaterEqual(status, 400)
        self.assertNotIn(b"<html", body.lower())

    def test_security_headers_and_strict_csp(self):
        for path in ("/", "/app.js", "/style.css", "/api/pipeline"):
            status, h, _ = self.live.request(path)
            self.assertEqual(status, 200, path)
            csp = h["content-security-policy"]
            self.assertNotIn("unsafe-inline", csp)
            self.assertNotIn("unsafe-eval", csp)
            for directive in ("default-src 'none'", "script-src 'self'", "connect-src 'self'",
                              "frame-ancestors 'none'", "base-uri 'none'", "form-action 'none'"):
                self.assertIn(directive, csp)
            self.assertEqual(h["x-content-type-options"], "nosniff")
            self.assertEqual(h["x-frame-options"], "DENY")
            self.assertEqual(h["referrer-policy"], "no-referrer")
            self.assertEqual(h["cache-control"], "no-store")
        self.assertTrue(self.live.request("/app.js")[1]["content-type"].startswith("text/javascript"))

    def test_page_has_no_inline_script_or_handlers(self):
        html = pathlib.Path(os.path.join(ROOT, "ui", "index.html")).read_text()
        self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html))
        self.assertIsNone(re.search(r"\son[a-z]+\s*=", html))
        self.assertNotIn("style=", html)
        js = pathlib.Path(os.path.join(ROOT, "ui", "app.js")).read_text()
        self.assertNotRegex(js, r"\beval\(|new Function|document\.write|outerHTML|insertAdjacentHTML\([^,]+,\s*[a-z]")
        self.assertNotRegex(js, r"style=")             # CSP forbids inline style attributes

    def test_nonfinite_numbers_serialise_as_strict_json(self):
        with open(os.path.join(self.root, "data", "literature_graph_alpha.json"), "w") as fh:
            fh.write('{"nodes": [], "edges": [], "counts": {"x": NaN, "y": Infinity}}')
        status, _, body = self.live.request("/api/compound?name=Alpha")
        self.assertEqual(status, 200)
        counts = _strict_json(body)["dimensions"]["literature"]["paper_graph"]["counts"]
        self.assertEqual(counts, {"x": None, "y": None})

    def test_blank_or_oversized_name_is_handled(self):
        self.assertEqual(self.live.request("/api/compound?name=%20%20")[0], 400)
        status, _, body = self.live.request("/api/compound?name=" + "A" * 5000)
        self.assertEqual(status, 200)
        self.assertEqual(len(_strict_json(body)["query"]), 200)

    def test_no_route_writes_or_spawns(self):
        before = {f: os.path.getmtime(os.path.join(self.root, "data", f))
                  for f in os.listdir(os.path.join(self.root, "data"))}
        with _NoNetwork(), mock.patch("subprocess.Popen") as popen, mock.patch("os.system") as system:
            for path in ("/", "/app.js", "/style.css", "/api/pipeline", "/api/dimensions", "/api/compounds",
                         "/api/compound?name=Alpha", "/api/validation", "/api/doc?key=README", "/api/status"):
                self.live.request(path)
        popen.assert_not_called()
        system.assert_not_called()
        after = {f: os.path.getmtime(os.path.join(self.root, "data", f))
                 for f in os.listdir(os.path.join(self.root, "data"))}
        self.assertEqual(before, after)


def _tokens(css, block_re):
    m = re.search(block_re, css, re.S | re.M)
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", m.group(1)))


def _contrast(a, b):
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class TestAccessibleContrast(unittest.TestCase):
    """WCAG AA (4.5:1) for the small text the dashboard uses (single dark palette)."""

    def test_text_and_badge_contrast(self):
        css = pathlib.Path(os.path.join(ROOT, "ui", "style.css")).read_text()
        # Single dark palette since 2026-10-15 (D-014); the tokens are the former dark scheme.
        dark = _tokens(css, r"^:root \{(.*?)\}")
        for scheme, t in (("dark", dark),):
            for fg in ("ink", "muted", "warn", "bad", "ok", "accent"):
                for bg in ("panel", "bg", "chip"):
                    self.assertGreaterEqual(_contrast(t[fg], t[bg]), 4.5, f"{scheme}: {fg} on {bg}")
            for bg in ("ok", "warn", "bad", "unk"):
                self.assertGreaterEqual(_contrast(t["badge-ink"], t[bg]), 4.5, f"{scheme}: badge on {bg}")
            self.assertGreaterEqual(_contrast(t["panel"], t["accent"]), 4.5, f"{scheme}: active nav")


if __name__ == "__main__":
    unittest.main()


class TestReviewQueue(unittest.TestCase):
    """/api/review: read-only queue; missing/malformed artefacts are reported, unresolved links stay unresolved."""

    def test_missing_and_malformed(self):
        import tempfile, shutil
        root = tempfile.mkdtemp()
        try:
            self.assertIn("missing", _review_module().build_review(root)["status"])
            os.makedirs(os.path.join(root, "data"))
            with open(os.path.join(root, "data/clinical_review_worklist.csv"), "w") as fh:
                fh.write("nct_id,compound\nNCT1,A\n")
            self.assertIn("malformed", _review_module().build_review(root)["status"])
        finally:
            shutil.rmtree(root)

    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, "data/clinical_review_worklist.csv")), "worklist absent")
    def test_counts_match_the_worklist_and_d020_file(self):
        import csv as _csv
        r = _review_module().build_review(ROOT)
        with open(os.path.join(ROOT, "data/clinical_review_worklist.csv"), newline="") as fh:
            rows = list(_csv.DictReader(fh))
        self.assertEqual(r["n_links"], len(rows))
        self.assertEqual(r["n_unresolved"], sum(x["status"].startswith("UNRESOLVED") for x in rows))
        self.assertEqual(r["n_unresolved"] + r["n_adjudicated"], r["n_links"])
        for x in r["rows"]:
            self.assertNotIn("decision", x)                     # the page never carries or invents a decision


def _review_module():
    import importlib.util as _u
    spec = _u.spec_from_file_location("srv_review", os.path.join(ROOT, "ui", "server.py"))
    m = _u.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@unittest.skipUnless(os.path.exists(os.path.join(ROOT, "data/literature_credibility_all.json")), "10a-all output absent")
class TestCredibilityAllOnCompoundPage(unittest.TestCase):
    def test_compound_without_curated_file_uses_10a_all(self):
        m = _review_module()
        r = m.build_compound(ROOT, "Ondansetron")["literature_credibility"]
        self.assertEqual(r["source"], "data/literature_credibility_all.json")
        self.assertEqual(r["status_10a"], "ASSESSED")
        self.assertIn("n_papers", r["summary_pre_cutoff"])
