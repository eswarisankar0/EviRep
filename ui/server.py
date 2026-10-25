"""
EviRep read-only dashboard.

A minimal local UI over the artefacts the pipeline has already persisted in
`data/` and the canonical docs. It exists so the pipeline, its agents/APIs and
the per-drug evidence can be inspected without reading terminal output.

Guarantees (each one is asserted by tests/test_ui.py):
  * READ-ONLY. Nothing here writes to data/, runs a pipeline stage, or calls an
    external API. Page load issues requests only to this local server.
  * Nothing is invented. A missing artefact is reported as missing; a field
    that is absent from an artefact is absent from the UI. Status is derived
    only from files on disk ("outputs present", never "ran successfully").
  * No secrets. .env is never read; environment variables are listed by NAME
    only, and any key-like value appearing in rendered docs is redacted.
  * No internals. Error responses carry an exception CLASS only, never a
    message or an absolute path; absolute paths and home-directory usernames
    in any served string are rewritten ("<repo>", "/Users/<user>").
  * Loopback only. --host must be a loopback address; requests whose Host
    header is not a loopback name are refused (DNS-rebinding defence).
  * Standard library only (no new dependency).

Run from the repository root:
    ./venv/bin/python ui/server.py            # http://127.0.0.1:8765
    ./venv/bin/python ui/server.py --port 9000
"""

import argparse
import csv
import hashlib
import json
import math
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

UI_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.dirname(UI_DIR)

csv.field_size_limit(sys.maxsize)

CUTOFF_DATE = "2021-01-01"   # mirrors scripts/03_clinicaltrials_groundtruth.py
ROW_COUNT_SIZE_LIMIT = 20 * 1024 * 1024   # don't line-count the 89 MB Hetionet dump


# ============================================================
# 1. REGISTRY — what each stage reads, writes and calls
# ============================================================
# Every path, endpoint and env-var name below was taken from the scripts'
# source; tests/test_ui.py asserts that each one literally appears in the
# referenced script, so this table cannot silently drift from the code.

STAGES = [
    {
        "id": "01", "name": "Candidate extraction", "script": "scripts/01_get_pd_candidates.py",
        "purpose": "Download Hetionet v1.0.0 and list compounds linked to Parkinson's disease.",
        "depends_on": [],
        "inputs": [],
        "outputs": ["data/hetionet_nodes.csv", "data/hetionet_edges.csv",
                    "data/pd_candidates_full.csv", "data/pd_candidates.csv"],
        "checkpoint": None,
        "apis": [{"name": "Zenodo (Hetionet v1.0.0 archive)",
                  "endpoint": "https://zenodo.org/records/268568/files/dhimmel/hetionet-v1.0.0.zip",
                  "auth": "none", "query": "single 155 MB download"}],
        "env": [], "cost": "155 MB download, held in memory",
        "issues": ["TD-013"],
        "limitations": ["Hetionet is a 2017 snapshot."],
    },
    {
        "id": "00", "name": "Exclusion filter", "script": "scripts/00_exclusion_filter.py",
        "purpose": "Remove vitamins, amino acids, electrolytes and basic metabolites (runs AFTER 01).",
        "depends_on": ["01"],
        "inputs": ["data/pd_candidates.csv"],
        "outputs": ["data/pd_candidates_filtered.csv"],
        "checkpoint": None, "apis": [], "env": [], "cost": "local",
        "issues": ["TD-010"], "limitations": [],
    },
    {
        "id": "02", "name": "Network proximity (dimension 1)", "script": "scripts/02_network_proximity.py",
        "purpose": "Degree-matched z-score of drug-target distance to the PD gene module in the Hetionet PPI.",
        "depends_on": ["00"],
        "inputs": ["data/hetionet_edges.csv", "data/pd_candidates_filtered.csv"],
        "outputs": ["data/network_proximity.csv"],
        "checkpoint": None, "apis": [], "env": [], "cost": "CPU-bound",
        "issues": ["TD-011"],
        "limitations": ["N_RANDOM = 100 (the script's own quick-test value, TD-011)."],
    },
    {
        "id": "03", "name": "ClinicalTrials.gov ground truth (dimension 2 + labels)",
        "script": "scripts/03_clinicaltrials_groundtruth.py",
        "purpose": "Pre-cutoff PD trials become the clinical-maturity FEATURE; post-cutoff trials are the LABEL only. "
                   "Gate 1 checks the condition, Gate 2 the intervention identity.",
        "depends_on": ["00"],
        "inputs": ["data/pd_candidates_filtered.csv"],
        "outputs": ["data/clinical_maturity_precutoff.csv", "data/ground_truth_postcutoff.csv",
                    "data/clinicaltrials_match_audit.csv"],
        "checkpoint": None,
        "apis": [{"name": "ClinicalTrials.gov API v2", "endpoint": "https://clinicaltrials.gov/api/v2/studies",
                  "auth": "none", "query": "query.intr=<compound>, query.cond=<PD phrase>"},
                 {"name": "Open Targets GraphQL (ChEMBL synonyms for Gate 2)", "endpoint": "OpenTargetsClient",
                  "auth": "none", "query": "drug synonyms / trade names (cached in data/cache/molecular)"}],
        "env": [], "cost": "~1,500 requests (10-20 min)",
        "issues": ["TD-018", "TD-019", "TD-023", "E-010", "E-011", "E-012", "E-014"],
        "limitations": ["No checkpoint: an outage yields a complete-looking run (TD-019); recover with scripts/03b_resume_failed_searches.py."],
    },
    {
        "id": "03c", "name": "Study-type filter (mandatory)",
        "script": "scripts/check_studytype.py",
        "related_scripts": ["scripts/filter_by_studytype.py"],
        "purpose": "Fetch study type per NCT ID; filter_by_studytype.py then keeps INTERVENTIONAL drug/biological trials "
                   "and is the ONLY producer of the *_clean.csv files.",
        "depends_on": ["03"],
        "inputs": ["data/clinical_maturity_precutoff.csv", "data/ground_truth_postcutoff.csv"],
        "outputs": ["data/nct_studytype_check.csv", "data/clinical_maturity_precutoff_clean.csv",
                    "data/ground_truth_postcutoff_clean.csv"],
        "checkpoint": None,
        "apis": [{"name": "ClinicalTrials.gov API v2", "endpoint": "https://clinicaltrials.gov/api/v2/studies/",
                  "auth": "none", "query": "one GET per unique NCT ID"}],
        "env": [], "cost": "one request per unique NCT ID",
        "issues": ["TD-012", "TD-015"], "limitations": [],
    },
    {
        "id": "04", "name": "Literature independence (dimension 3)",
        "script": "scripts/04_literature_independence.py",
        "purpose": "Up to 30 PubMed papers per compound; papers joined by shared author or citation; "
                   "independent evidence = connected components.",
        "depends_on": ["03c"],
        "inputs": ["data/clinical_maturity_precutoff_clean.csv"],
        "outputs": ["data/literature_independence.csv"],
        "checkpoint": "data/_literature_checkpoint.jsonl",
        "apis": [{"name": "NCBI E-utilities (PubMed)", "endpoint": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils",
                  "auth": "optional API key (rate limit only)",
                  "query": '"<compound>"[Title/Abstract] AND "Parkinson Disease"[Title/Abstract], retmax 30 — no date bound'},
                 {"name": "Semantic Scholar Graph API", "endpoint": "https://api.semanticscholar.org/graph/v1/paper",
                  "auth": "none", "query": "PMID:<id>/citations"}],
        "env": ["NCBI_API_KEY", "S2_SLEEP"], "cost": "heaviest stage — hours",
        "issues": ["TD-009", "TD-016", "TD-021", "E-008", "E-009"],
        "limitations": ["PubMed query has no publication-date bound, so post-cutoff papers count (TD-021)."],
    },
    {
        "id": "05", "name": "Safety signal (dimension 4)", "script": "scripts/05_safety_signal.py",
        "purpose": "openFDA label: boxed warning flag and serious-term count.",
        "depends_on": ["03c"],
        "inputs": ["data/clinical_maturity_precutoff_clean.csv"],
        "outputs": ["data/safety_signal.csv"],
        "checkpoint": "data/_safety_checkpoint_v2.jsonl",
        "apis": [{"name": "openFDA drug label", "endpoint": "https://api.fda.gov/drug/label.json",
                  "auth": "none", "query": 'search=openfda.generic_name:"<compound>", limit=1'}],
        "env": [], "cost": "~90 requests",
        "issues": ["TD-014", "TD-022", "TD-031", "D-003"],
        "limitations": ["Current label, not cutoff-bounded (TD-022). Boxed-warning detection by key presence (TD-014).",
                        "v2 (D-003) counts terms in warnings AND warnings_and_cautions (PLR labels); raw labels "
                        "cached in data/cache/openfda_labels/. No label = missing, not zero risk (TD-031)."],
    },
    {
        "id": "08", "name": "Molecular / pathway agent (dimension 5)",
        "script": "scripts/08_molecular_pathway.py",
        "purpose": "drug -> ChEMBL target -> gene -> Reactome pathway -> PD module; "
                   "score = 0.6 x direct + 0.4 x pathway overlap (logic in scripts/molecular_agent.py).",
        "depends_on": ["03c"],
        "inputs": ["data/clinical_maturity_precutoff_clean.csv"],
        "outputs": ["data/molecular_pathway.csv", "data/molecular_pathway_evidence.jsonl"],
        "checkpoint": "data/_molecular_checkpoint.jsonl",
        # A hung Open Targets retrieval previously blocked the runner forever (E-055 A-5). Generous: a cold full
        # run is batched (25 IDs/request, 0.25 s throttle, <= 4 retries with backoff); the checkpoint resumes work.
        "timeout_s": 14400,
        "apis": [{"name": "Open Targets Platform GraphQL", "endpoint": "OpenTargetsClient",
                  "auth": "none", "query": "mapIds, drug mechanisms, target pathways, PD associations (batched, cached)"}],
        "env": [], "cost": "batched + cached; same-cohort rerun issues no network calls",
        "issues": ["TD-006", "TD-007", "TD-017", "TD-024", "TD-028", "B-001", "A-001", "A-002", "E-013"],
        "limitations": ["Open Targets snapshot is not cutoff-bounded (B-001/TD-006); clinical + literature datatypes excluded."],
    },
    {
        "id": "06", "name": "VPS fusion + evaluation", "script": "scripts/06_vps_fusion.py",
        "purpose": "Percentile-rank each dimension, fuse (equal and grid-searched weights), "
                   "evaluate against post-cutoff labels; baselines and ablations.",
        "depends_on": ["02", "03c", "04", "05", "08"],
        "inputs": ["data/pd_candidates_filtered.csv", "data/network_proximity.csv",
                   "data/clinical_maturity_precutoff_clean.csv", "data/literature_independence.csv",
                   "data/safety_signal.csv", "data/ground_truth_postcutoff_clean.csv",
                   "data/label_role_exclusions.csv", "data/molecular_pathway.csv", "data/feature_role_exclusions.csv"],
        "outputs": ["data/vps_scores_v2.csv", "data/vps_variant_results.csv",
                    "data/baseline_results_v2.csv", "data/ablation_results_v2.csv",
                    "data/ablation_results_5d.csv", "data/grid_search_4d_log.csv",
                    "data/grid_search_3d_log.csv", "data/grid_search_5d_log.csv"],
        "checkpoint": None, "apis": [], "env": [], "cost": "local, seconds",
        "issues": ["TD-003", "TD-004", "TD-020", "TD-024", "TD-025", "TD-027"],
        "limitations": ["14 positives / 90 compounds: AUROC CIs about +/-0.11 to 0.13 (TD-020)."],
    },
    {
        "id": "04b", "name": "Literature graph export (Figure 3 data)",
        "script": "scripts/04b_export_literature_graph.py",
        "purpose": "Re-derive one compound's paper graph with stage-04 functions; refuses to write unless "
                   "counts match the stage-04 checkpoint.",
        "depends_on": ["04"],
        "inputs": ["data/_literature_checkpoint.jsonl"],
        "outputs": ["data/literature_graph_droxidopa.json"],
        "run_args": ["--compound", "Droxidopa"],      # required argument; the declared output is Droxidopa's graph
        "checkpoint": None,
        "apis": [{"name": "NCBI E-utilities + Semantic Scholar", "endpoint": "stage-04 functions",
                  "auth": "as stage 04", "query": "one compound"}],
        "env": [], "cost": "one compound's stage-04 queries",
        "issues": ["TD-002", "TD-026"], "limitations": [],
    },
    {
        "id": "05h", "name": "Safety label at the cutoff (DailyMed version history)",
        "script": "scripts/05h_safety_label_history.py",
        "purpose": "For each label stage 05 scored, take the DailyMed version published on or before the cutoff and "
                   "apply stage 05's scoring; checks the parser against stage 05 on the current version. New files "
                   "only; VPS unchanged (TD-022/TD-033).",
        "depends_on": ["05"],
        "inputs": ["data/safety_signal.csv"],
        "outputs": ["data/safety_label_history.csv", "data/safety_label_history_run.json"],
        "timeout_s": 3600, "checkpoint": "data/cache/dailymed/",
        "apis": [{"name": "DailyMed web services", "endpoint": "/services/v2/spls/{setid}/history.json + getFile.cfm",
                  "auth": "none", "query": "one history and up to two SPL versions per labelled compound"}],
        "env": [], "cost": "about 3 requests per labelled compound; cached",
        "issues": ["TD-022", "TD-033"],
        "limitations": ["Follows only the current label's set ID; earlier labels under other set IDs are not found."],
    },
    {
        "id": "04p", "name": "Literature provenance (PMIDs, dates, cutoff status)",
        "script": "scripts/04p_literature_provenance.py",
        "purpose": "Re-run the stage-04 PubMed query for every compound and persist PMIDs, DOIs, publication "
                   "dates, cutoff status, duplicates and truncation (TD-021). New files only; VPS unchanged.",
        "depends_on": ["03c", "04"],
        "inputs": ["data/clinical_maturity_precutoff_clean.csv", "data/_literature_checkpoint.jsonl"],
        "outputs": ["data/literature_papers.jsonl", "data/literature_provenance.csv",
                    "data/literature_provenance_run.json"],
        "timeout_s": 7200, "checkpoint": "data/cache/pubmed_lit/",
        "apis": [{"name": "NCBI E-utilities", "endpoint": "esearch.fcgi + efetch.fcgi",
                  "auth": "optional NCBI_API_KEY", "query": "stage-04 query, unbounded (retmax 30) and pdat <= cutoff"}],
        "env": ["NCBI_API_KEY"], "cost": "about 3 requests per compound; cached",
        "issues": ["TD-021"],
        "limitations": ["PubMed is queried today; the sample can differ from the one stage 04 used."],
    },
    {
        "id": "07", "name": "Figures", "script": "scripts/07_generate_figures.py",
        "purpose": "Figures 1-3 drawn only from persisted metrics / the exported literature graph.",
        "depends_on": ["06", "04b"],
        "inputs": ["data/baseline_results_v2.csv", "data/vps_variant_results.csv",
                   "data/ablation_results_v2.csv", "data/ablation_results_5d.csv",
                   "data/literature_graph_droxidopa.json", "data/vps_scores_v2.csv"],
        "outputs": ["data/figure1_auroc_comparison.png", "data/figure2_ablation.png",
                    "data/figure2_ablation_5d.png", "data/figure3_droxidopa_literature_graph.png"],
        "timeout_s": 900, "checkpoint": None, "apis": [], "env": [], "cost": "local",
        "issues": ["TD-001", "TD-002", "TD-025"], "limitations": [],
    },
    {
        "id": "diag", "name": "Intervention-match diagnostic", "script": "scripts/check_intervention_match.py",
        "purpose": "Independent audit: does each accepted trial actually name the compound?",
        "depends_on": ["03c"],
        "inputs": ["data/clinical_maturity_precutoff_clean.csv", "data/ground_truth_postcutoff_clean.csv"],
        "outputs": ["data/intervention_match_check.csv"],
        "timeout_s": 3600, "checkpoint": None,
        "apis": [{"name": "ClinicalTrials.gov API v2", "endpoint": "https://clinicaltrials.gov/api/v2/studies/",
                  "auth": "none", "query": "one GET per NCT ID"}],
        "env": [], "cost": "one request per NCT ID", "issues": ["TD-018"], "limitations": [],
    },
    {
        "id": "10d", "name": "Conflict & Context Agent (diagnostic)", "script": "scripts/conflict_context_agent.py",
        "purpose": "Pairwise comparison of persisted, source-linked claims: contradiction vs context difference "
                   "vs benefit-risk tension. Never scored; not read by stage 06.",
        "depends_on": ["05", "08", "06"],
        "inputs": ["data/conflict_claims_curated.json", "data/molecular_pathway_evidence.jsonl",
                   "data/clinical_maturity_precutoff_clean.csv", "data/vps_scores_v2.csv"],
        "outputs": ["data/conflict_context.json"],
        "timeout_s": 900, "checkpoint": None, "apis": [],
        "env": [], "cost": "offline, seconds", "issues": ["D-015"],
        "limitations": ["Curated claims cover the case-study compounds only; label claims need a cached openFDA "
                        "label (83/90). Literature PMIDs for the pool are not persisted (TD-021)."],
    },
    {
        "id": "10e", "name": "Reproducibility Agent (diagnostic)", "script": "scripts/reproducibility_agent.py",
        "purpose": "Finding-level replication: independent primary-study clusters (shared authors, trial IDs, "
                   "documented shared data); syntheses never count as replicates. Not read by stage 06.",
        "depends_on": ["10d"],
        "inputs": ["data/cache/pubmed_efetch_case_claims.xml", "data/cache/pubmed_efetch_droxidopa.xml",
                   "data/conflict_claims_curated.json", "data/clinical_maturity_precutoff_clean.csv",
                   "data/ground_truth_postcutoff_clean.csv"],
        "outputs": ["data/reproducibility.json"],
        "timeout_s": 900, "checkpoint": None, "apis": [], "env": [], "cost": "offline, seconds", "issues": ["D-017"],
        "limitations": ["Findings only for case-study compounds with curated claims; independence is at best "
                        "'plausible' because populations/datasets are not persisted."],
    },
    {
        "id": "eval", "name": "VPS evaluation report", "script": "scripts/vps_evaluation_report.py",
        "purpose": "Reproduces every persisted AUROC, bootstrap CIs, AUPRC, repeated nested CV, correlations, "
                   "missing data. Reads stage-06 outputs only.",
        "depends_on": ["06", "10e"],
        "inputs": ["data/vps_scores_v2.csv", "data/ground_truth_postcutoff_clean.csv", "data/label_role_exclusions.csv",
                   "data/vps_variant_results.csv", "data/baseline_results_v2.csv", "data/ablation_results_5d.csv",
                   "data/bootstrap_ci_equal5d_vs_4d.csv", "data/reproducibility.json"],
        "outputs": ["data/vps_evaluation_report.json"],
        "checkpoint": None, "apis": [], "env": [], "cost": "offline, ~35 s", "issues": ["D-018"], "limitations": [],
    },
    {
        "id": "10b", "name": "Molecular agent run record (offline re-validation)", "script": "scripts/molecular_run_record.py",
        "purpose": "Re-validates every persisted stage-08 evidence record and the CSV/JSONL agreement; writes the "
                   "shared agent envelope. Does not re-run retrieval.",
        "depends_on": ["08", "06"],
        "inputs": ["data/molecular_pathway.csv", "data/molecular_pathway_evidence.jsonl", "data/vps_scores_v2.csv"],
        "outputs": ["data/molecular_agent_run.json"],
        "timeout_s": 900, "checkpoint": None, "apis": [], "env": [], "cost": "offline, seconds", "issues": ["D-023"], "limitations": [],
    },
    {
        "id": "10c", "name": "Clinical Evidence Agent (diagnostic layer)", "script": "scripts/clinical_evidence_agent.py",
        "purpose": "Registry status, posted results (verbatim), drug role in every pre-cutoff trial link, matching-audit "
                   "outcomes. Registry records come from a cache (--fetch refreshes it).",
        "depends_on": ["03c", "08", "06"],
        "inputs": ["data/clinical_maturity_precutoff_clean.csv", "data/clinicaltrials_match_audit.csv",
                   "data/feature_trial_roles_td038.csv", "data/vps_scores_v2.csv", "data/cache/ctgov_precutoff_trials.json",
                   "data/molecular_pathway_evidence.jsonl"],
        "outputs": ["data/clinical_evidence.json"],
        "timeout_s": 900, "checkpoint": None,
        "apis": [{"name": "ClinicalTrials.gov API v2", "endpoint": "https://clinicaltrials.gov/api/v2/studies",
                  "auth": "none", "query": "filter.ids batches of 20 (only with --fetch)"}],
        "env": [], "cost": "offline from cache; --fetch ~9 requests", "issues": ["D-023"], "limitations": [],
    },
    {
        "id": "10f", "name": "Safety Evidence Agent (diagnostic layer)", "script": "scripts/safety_evidence_agent.py",
        "purpose": "FDA label provenance + FAERS report counts with retrieved / no-record / failed / not-retrieved "
                   "states. FAERS cache refreshed only with --fetch.",
        "depends_on": ["05", "05h", "06"],
        "inputs": ["data/vps_scores_v2.csv", "data/safety_signal.csv", "data/safety_label_history.csv", "data/_safety_failures.jsonl"],
        "outputs": ["data/safety_evidence.json"],
        "timeout_s": 900, "checkpoint": None,
        "apis": [{"name": "openFDA drug/event (FAERS)", "endpoint": "https://api.fda.gov/drug/event.json",
                  "auth": "none", "query": "4 count queries per uncached compound (only with --fetch)"}],
        "env": [], "cost": "offline from cache; --fetch ~4 requests per compound", "issues": ["D-023"], "limitations": [],
    },
    {
        "id": "10g", "name": "Evidence Independence Agent (diagnostic layer)", "script": "scripts/evidence_independence_agent.py",
        "purpose": "Cross-source dependence: shared trials across candidates, one study in two dimensions, "
                   "duplicated/pooled claims, molecular datatype reuse, duplicate publications in the sample.",
        "depends_on": ["10c", "04", "08", "04p", "06"],
        "inputs": ["data/vps_scores_v2.csv", "data/clinical_maturity_precutoff_clean.csv", "data/literature_independence.csv",
                   "data/conflict_claims_curated.json", "data/clinical_evidence.json", "data/molecular_pathway_evidence.jsonl",
                   "data/literature_papers.jsonl", "data/cache/pubmed_efetch_droxidopa.xml", "data/cache/pubmed_efetch_case_claims.xml"],
        "outputs": ["data/evidence_independence.json"],
        "timeout_s": 900, "checkpoint": None, "apis": [], "env": [], "cost": "offline, seconds", "issues": ["D-023"], "limitations": [],
    },
    {
        "id": "10a", "name": "Literature Credibility Agent (curated PMIDs)", "script": "scripts/literature_credibility_agent.py",
        "purpose": "Study-design tiers for the curated case-study PMIDs (cached efetch XML), --curated mode.",
        "depends_on": [],
        "inputs": ["data/cache/pubmed_efetch_case_claims.xml", "data/conflict_claims_curated.json"],
        "outputs": ["data/literature_credibility_donepezil.json", "data/literature_credibility_domperidone.json",
                    "data/literature_credibility_melatonin.json", "data/literature_credibility_propranolol.json"],
        "timeout_s": 900, "checkpoint": None, "apis": [], "env": [], "cost": "offline, seconds", "issues": ["D-023"], "limitations": [],
        "run_args": ["--curated"],
    },
    {
        "id": "10a-all", "name": "Literature Credibility Agent (all compounds)",
        "script": "scripts/literature_credibility_agent.py",
        "purpose": "Study-design tiers for every compound's stage-04 sample and cutoff-bounded literature, "
                   "from the stage-04p records and cached XML (--all mode). Duplicates rated once.",
        "depends_on": ["04p"],
        "inputs": ["data/literature_provenance.csv", "data/literature_papers.jsonl"],
        "outputs": ["data/literature_credibility_all.json"],
        "timeout_s": 900, "checkpoint": None, "apis": [], "env": [], "cost": "offline, seconds", "issues": ["TD-021"],
        "limitations": ["Design tiers only; no direction or efficacy."],
        "run_args": ["--all"],
    },
    {
        "id": "review", "name": "Clinical trial-role review worklist (human adjudication queue)",
        "script": "scripts/clinical_role_review.py",
        "purpose": "Every pre-cutoff trial link with intervention/arm text, automated and structural role, any D-020 "
                   "adjudication and review flags; the flagged links form the prioritised worklist. Writes no "
                   "decision and changes no scoring input.",
        "depends_on": ["10c"],
        "inputs": ["data/clinical_maturity_precutoff_clean.csv", "data/cache/ctgov_precutoff_trials.json",
                   "data/feature_trial_roles_td038.csv", "data/molecular_pathway_evidence.jsonl"],
        "outputs": ["data/clinical_role_review.csv", "data/clinical_review_worklist.csv"],
        "timeout_s": 900, "checkpoint": None, "apis": [], "env": [], "cost": "offline, seconds", "issues": ["TD-038", "TD-043", "D-020"],
        "limitations": ["Unresolved links stay UNRESOLVED until a human records a D-020 decision."],
        "run_args": ["--out", "data/clinical_role_review.csv", "--worklist", "data/clinical_review_worklist.csv"],
    },
    {
        "id": "10h", "name": "Completeness & Gap Agent", "script": "scripts/completeness_gap_agent.py",
        "purpose": "Per candidate and evidence domain: measured / zero / absent / not computed / not retrieved / "
                   "failed / insufficient, gaps and staleness of every agent output. Run last.",
        "depends_on": ["06", "10b", "10c", "10d", "10e", "10f", "10g", "10a-all", "10a"],
        "inputs": ["data/vps_scores_v2.csv", "data/network_proximity.csv", "data/literature_independence.csv",
                   "data/safety_signal.csv", "data/molecular_pathway.csv", "data/conflict_context.json",
                   "data/reproducibility.json", "data/clinical_evidence.json", "data/safety_evidence.json",
                   "data/evidence_independence.json", "data/literature_credibility_all.json", "data/clinical_maturity_precutoff_clean.csv", "data/feature_trial_roles_td038.csv", "data/_safety_failures.jsonl", "data/_literature_failures.jsonl", "data/literature_credibility_donepezil.json", "data/literature_credibility_domperidone.json",
                   "data/literature_credibility_melatonin.json", "data/literature_credibility_propranolol.json",
                   "data/literature_credibility_droxidopa.json", "data/molecular_agent_run.json"],
        "outputs": ["data/completeness_gaps.json"],
        "timeout_s": 900, "checkpoint": None, "apis": [], "env": [], "cost": "offline, seconds", "issues": ["D-021"], "limitations": [],
    },
]

# Documented definition of each evidence dimension. Wording follows README.md
# and the r_* transforms in scripts/06_vps_fusion.py::build_standardized_scores.
DIMENSIONS = [
    {"key": "proximity", "label": "Network proximity", "stage": "02", "raw": "proximity_z", "rank": "r_proximity",
     "definition": "Degree-matched z-score of mean nearest-PD-gene distance in the Hetionet PPI. "
                   "More negative = closer; percentile-ranked INVERTED so closer scores higher.",
     "temporal": "Hetionet 2017 snapshot (pre-cutoff)."},
    {"key": "clinical", "label": "Clinical maturity", "stage": "03", "raw": "max_phase_rank", "rank": "r_clinical",
     "definition": "Maximum phase rank over accepted PRE-cutoff PD trials; percentile-ranked (higher = more mature).",
     "temporal": "Pre-cutoff trials only (first_posted < 2021-01-01)."},
    {"key": "literature", "label": "Literature independence", "stage": "04", "raw": "effective_independent_count",
     "rank": "r_literature",
     "definition": "Connected components of the paper co-dependency graph (shared author or citation) among up to 30 "
                   "PubMed papers; percentile-ranked (higher = more independent evidence).",
     "temporal": "NOT cutoff-bounded: the PubMed query has no date restriction (TD-021)."},
    {"key": "safety", "label": "Safety signal", "stage": "05", "raw": "serious_term_count", "rank": "r_safety",
     "definition": "Risk = serious_term_count + 5 x boxed_warning; percentile-ranked INVERTED (lower risk scores higher). "
                   "No openFDA label = not measured -> neutral rank 0.5 (D-004), never 'safest'.",
     "temporal": "Current openFDA label, not cutoff-bounded (TD-022)."},
    {"key": "molecular", "label": "Molecular / pathway plausibility", "stage": "08",
     "raw": "molecular_plausibility_score", "rank": "r_molecular",
     "definition": "0.6 x direct target-PD evidence (max over permitted Open Targets datatypes) + 0.4 x Reactome "
                   "pathway overlap with the PD module. Confidence is an evidence-AVAILABILITY axis, "
                   "not a probability of efficacy. No ChEMBL mechanism target = not measured -> neutral "
                   "rank 0.5 (D-004), not a measured 0.",
     "temporal": "Open Targets current snapshot, not cutoff-bounded (B-001 / TD-006); clinical and literature "
                 "datatypes excluded."},
]

DOCS = {
    "README": "README.md",
    "TECHNICAL_DEBT": "TECHNICAL_DEBT.md",
    "CHANGES": "development_log/CHANGES.md",
    "ERRORS_AND_BLOCKERS": "development_log/ERRORS_AND_BLOCKERS.md",
    "CASE_STUDIES": "docs/CASE_STUDIES.md",
    "INTERVENTION_MATCHING": "docs/INTERVENTION_MATCHING.md",
    "MOLECULAR_AGENT": "docs/MOLECULAR_AGENT.md",
    "REFERENCES": "docs/REFERENCES.md",
}

FIGURE_RE = re.compile(r"^figure[\w\-]*\.png$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,100}$")
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/index.html": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")   # accepted in the Host header
BIND_HOSTS = ("127.0.0.1", "localhost")               # IPv4 server; ::1 is not bindable here


# ============================================================
# 2. SAFE READERS
# ============================================================

_SECRET_PATTERNS = [
    # NAME=value / NAME: value for key-like names
    re.compile(r"(?i)\b([A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|PASSWD)[A-Z0-9_]*)(\s*[=:]\s*)(['\"]?)([^\s'\"`,)}]+)(\3)"),
    # JSON "api-key":"value", "api_key": "value"
    re.compile(r"(?i)(\"(?:api[-_]?key|token|secret|password)\"\s*:\s*\")([^\"]+)(\")"),
    # api_key=value in URLs
    re.compile(r"(?i)([?&]api_key=)([^&\s`'\"]+)"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
]
# Home directories reveal the local username: /Users/<name>/..., /home/<name>/...
_HOME_RE = re.compile(r"(?<![\w.])/(Users|home)/[^/\s'\"`]+")


def redact(text):
    """Replace credential VALUES with [REDACTED]; names are kept."""
    if not isinstance(text, str):
        return text
    text = _SECRET_PATTERNS[0].sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}[REDACTED]{m.group(5)}", text)
    text = _SECRET_PATTERNS[1].sub(lambda m: f"{m.group(1)}[REDACTED]{m.group(3)}", text)
    text = _SECRET_PATTERNS[2].sub(lambda m: f"{m.group(1)}[REDACTED]", text)
    text = _SECRET_PATTERNS[3].sub("[REDACTED PRIVATE KEY]", text)
    text = _HOME_RE.sub(lambda m: f"/{m.group(1)}/<user>", text)
    return text


def _err(exc):
    """Error text safe to show in the browser: the class name, never the
    message (OSError messages embed the absolute path)."""
    return f"unreadable ({type(exc).__name__})"


def sanitize(value, root=None):
    """Make a payload safe to serialise: credential values and absolute
    paths redacted in every string, non-finite floats -> None (strict JSON)."""
    if isinstance(value, str):
        if root:
            value = value.replace(os.path.abspath(root), "<repo>")
        return redact(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {sanitize(k, root) if isinstance(k, str) else k: sanitize(v, root) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v, root) for v in value]
    return value


def _abs(root, rel):
    return os.path.join(root, rel)


def num(value):
    """Parse a numeric field. Blank, malformed and non-finite values -> None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def read_csv(root, rel):
    """Return (rows, error). Missing file -> ([], 'missing'); malformed -> ([], message)."""
    path = _abs(root, rel)
    if not os.path.exists(path):
        return [], "missing"
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            rows = []
            for row in reader:
                # rows longer than the header land under key None; drop them
                rows.append({k: v for k, v in row.items() if k is not None})
            return rows, None
    except (csv.Error, OSError, UnicodeError) as exc:
        return [], _err(exc)


def read_jsonl_where(root, rel, predicate):
    """Stream a JSONL file; return (first matching record, error, n_bad_lines)."""
    path = _abs(root, rel)
    if not os.path.exists(path):
        return None, "missing", 0
    bad = 0
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    bad += 1
                    continue
                if isinstance(rec, dict) and predicate(rec):
                    return rec, None, bad
    except OSError as exc:
        return None, _err(exc), bad
    return None, None, bad


def read_json(root, rel):
    path = _abs(root, rel)
    if not os.path.exists(path):
        return None, "missing"
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), None
    except (OSError, ValueError) as exc:
        return None, _err(exc)


def file_info(root, rel):
    path = _abs(root, rel)
    if not os.path.exists(path):
        return {"path": rel, "exists": False}
    st = os.stat(path)
    info = {"path": rel, "exists": True, "size_bytes": st.st_size,
            "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds"),
            "_mtime": st.st_mtime}
    if st.st_size <= ROW_COUNT_SIZE_LIMIT and rel.endswith((".csv", ".jsonl")):
        try:
            with open(path, "rb") as fh:
                lines = sum(1 for line in fh if line.strip())
            info["records"] = lines - 1 if rel.endswith(".csv") else lines
        except OSError:
            pass
    if rel.endswith(".csv") and st.st_size <= ROW_COUNT_SIZE_LIMIT:
        try:
            with open(path, newline="", encoding="utf-8", errors="replace") as fh:
                info["columns"] = next(csv.reader(fh), [])
        except (OSError, csv.Error):
            pass
    return info


def _norm(name):
    return re.sub(r"[^a-z0-9]+", " ", str(name if name is not None else "").lower()).strip()


# ============================================================
# 3. ISSUE INDEX (from the canonical logs)
# ============================================================

_TD_HEAD = re.compile(r"^#{2,3} (TD-\d+) · (\w+) · (.+?)(?: — \*\*(.+?)\*\*)?\s*$")
_EB_HEAD = re.compile(r"^### ([A-Z]-\d+(?:-FIX)?) · ([A-Z ]+?)(?: \([^)]*\))? · (.+)$")


def build_issue_index(root):
    issues = {}
    path = _abs(root, "TECHNICAL_DEBT.md")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                m = _TD_HEAD.match(line.rstrip())
                if m:
                    issues[m.group(1)] = {"id": m.group(1), "severity": m.group(2), "title": m.group(3),
                                          "status": m.group(4) or "", "source": "TECHNICAL_DEBT.md"}
    path = _abs(root, "development_log/ERRORS_AND_BLOCKERS.md")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                m = _EB_HEAD.match(line.rstrip())
                if m:
                    rest = m.group(3)
                    issues.setdefault(m.group(1), {"id": m.group(1), "severity": m.group(2).strip(),
                                                   "title": redact(rest), "status": "",
                                                   "source": "development_log/ERRORS_AND_BLOCKERS.md"})
    return issues


# ============================================================
# 4. PIPELINE / AGENT VIEW
# ============================================================

def _health(root, stage_id):
    """Stage-specific signals computed from the artefacts themselves."""
    notes = []
    if stage_id == "03":
        rows, err = read_csv(root, "data/clinicaltrials_match_audit.csv")
        if not err:
            counts = {}
            for r in rows:
                counts[r.get("outcome", "")] = counts.get(r.get("outcome", ""), 0) + 1
            notes.append({"level": "warn" if counts.get("API_FAILURE") else "info",
                          "text": "audit outcomes: " + ", ".join(f"{k or '(blank)'}={v}" for k, v in sorted(counts.items()))})
    elif stage_id == "04":
        rows, err = read_csv(root, "data/literature_independence.csv")
        if not err:
            incomplete = [r["compound_name"] for r in rows
                          if str(r.get("citation_coverage_complete", "")).strip().lower() not in ("true", "1")]
            fails = sum(int(num(r.get("citation_lookup_failures")) or 0) for r in rows)
            notes.append({"level": "warn" if incomplete else "info",
                          "text": f"{len(rows)} compounds; citation coverage incomplete for {len(incomplete)}; "
                                  f"citation lookup failures {fails}"})
    elif stage_id == "08":
        rows, err = read_csv(root, "data/molecular_pathway.csv")
        if not err:
            unresolved = [r["compound_name"] for r in rows if str(r.get("resolved", "")).lower() != "true"]
            no_targets = sum(1 for r in rows if (num(r.get("n_targets")) or 0) == 0)
            notes.append({"level": "info",
                          "text": f"{len(rows)} compounds; unresolved {len(unresolved)}"
                                  f"{' (' + ', '.join(unresolved) + ')' if unresolved else ''}; "
                                  f"no ChEMBL target {no_targets}"})
    elif stage_id == "06":
        rows, err = read_csv(root, "data/vps_scores_v2.csv")
        if not err:
            pos = sum(1 for r in rows if r.get("label") == "1")
            notes.append({"level": "info", "text": f"evaluable pool {len(rows)} compounds, {pos} positive labels"})
    return notes


def stage_status(outputs, inputs):
    """Derive status from files only. Never claims a run succeeded."""
    if not outputs:
        return "unknown"
    present = [o for o in outputs if o["exists"]]
    if not present:
        return "missing"
    if len(present) < len(outputs):
        return "partial"
    newest_input = max((i["_mtime"] for i in inputs if i.get("exists")), default=None)
    oldest_output = min(o["_mtime"] for o in outputs)
    if newest_input is not None and newest_input > oldest_output + 1:
        return "input_newer"            # a timestamp hint only; freshness comes from scripts/run_stage.py
    return "available"


def _strip_private(info):
    return {k: v for k, v in info.items() if not k.startswith("_")}


def build_pipeline(root):
    issues = build_issue_index(root)
    stages = []
    for s in STAGES:
        inputs = [file_info(root, p) for p in s["inputs"]]
        outputs = [file_info(root, p) for p in s["outputs"]]
        ckpt = file_info(root, s["checkpoint"]) if s["checkpoint"] else None
        stages.append({
            **{k: s[k] for k in ("id", "name", "script", "purpose", "depends_on", "apis", "env",
                                 "cost", "limitations")},
            "script_exists": os.path.exists(_abs(root, s["script"])),
            "status": stage_status(outputs, inputs),
            "inputs": [_strip_private(i) for i in inputs],
            "outputs": [_strip_private(o) for o in outputs],
            "checkpoint": _strip_private(ckpt) if ckpt else None,
            "persistence": ("checkpointed (resumable)" if s["checkpoint"]
                            else "persisted outputs only — a rerun recomputes everything"),
            "issues": [issues.get(i, {"id": i, "title": "(not found in logs)", "status": "", "severity": ""})
                       for i in s["issues"]],
            "health": _health(root, s["id"]),
        })
    return {
        "root": os.path.basename(os.path.abspath(root)),
        "cutoff_date": CUTOFF_DATE,
        "status_legend": {
            "available": "all listed outputs exist and none is older than an input",
            "input_newer": "outputs exist but an input file has a newer timestamp (a hint only: freshness is "
                           "decided from content fingerprints and dependencies by the run tracker)",
            "partial": "some listed outputs are missing",
            "missing": "no listed output exists",
            "unknown": "no persisted output to inspect",
        },
        "note": "File status is inferred from files on disk only. 'available' means outputs are present, "
                "not that the run was correct. The run status beside it (from data/run_manifest.json) is "
                "the authoritative freshness; see the health notes and linked issues.",
        "stages": stages,
    }


# ============================================================
# 5. DRUG EXPLORER
# ============================================================

def _find(rows, name, key="compound_name"):
    n = _norm(name)
    return [r for r in rows if _norm(r.get(key)) == n]


def _clean_row(row):
    return {k: (v if v != "" else None) for k, v in row.items()}


def _ranks(rows, col):
    vals = [(num(r.get(col)), r.get("compound_name")) for r in rows]
    vals = [v for v in vals if v[0] is not None]
    vals.sort(key=lambda v: -v[0])
    return {name: i + 1 for i, (_, name) in enumerate(vals)}, len(vals)


def list_compounds(root):
    sources = {
        "vps": "data/vps_scores_v2.csv",
        "proximity": "data/network_proximity.csv",
        "literature": "data/literature_independence.csv",
        "safety": "data/safety_signal.csv",
        "molecular": "data/molecular_pathway.csv",
        "audit": "data/clinicaltrials_match_audit.csv",
    }
    names = {}
    pool = set()
    for key, rel in sources.items():
        rows, err = read_csv(root, rel)
        if err:
            continue
        for r in rows:
            nm = r.get("compound_name")
            if not nm:
                continue
            names.setdefault(_norm(nm), nm)
            if key == "vps":
                pool.add(_norm(nm))
    out = [{"name": names[k], "in_pool": k in pool} for k in names]
    out.sort(key=lambda x: (not x["in_pool"], x["name"].lower()))
    return {"n_pool": len(pool), "compounds": out}


# ============================================================
# AGENT INVENTORY (architecture 10a-10h)
# ============================================================
# Status is computed from the repository, never asserted: a module counts as
# implemented only if the file exists, tested only if its test file exists
# (count of test functions shown; the UI does not run them), and integrated only
# if scripts/06_vps_fusion.py reads the agent's output file.
CONFLICT_JSON = "data/conflict_context.json"
CI_CSV = "data/bootstrap_ci_equal5d_vs_4d.csv"
AGENTS = [
    {"id": "10a", "name": "Literature Credibility", "module": "scripts/literature_credibility_agent.py",
     "tests": "tests/test_literature_credibility_agent.py", "vps_input": None,
     "outputs": ["data/literature_credibility_all.json", "data/literature_credibility_droxidopa.json"],
     "output_glob": "literature_credibility_",
     "scope": "Study-design tiers from PubMed PublicationType/MeSH for every compound (stage-04 sample and "
              "cutoff-bounded literature, from stage 04p) plus curated case-study PMIDs with curated directions.",
     "sources": "PubMed esearch/efetch via stage 04p (cached XML)"},
    {"id": "10b", "name": "Molecular Plausibility", "module": "scripts/molecular_agent.py",
     "tests": "tests/test_molecular_agent.py", "vps_input": "data/molecular_pathway.csv",
     "outputs": ["data/molecular_agent_run.json", "data/molecular_pathway.csv", "data/molecular_pathway_evidence.jsonl"],
     "scope": "Stage 08: ChEMBL targets -> Open Targets PD associations + Reactome overlap = VPS dimension 5.",
     "sources": "Open Targets GraphQL (ChEMBL, Reactome); STRING not used"},
    {"id": "10c", "name": "Clinical Evidence", "module": "scripts/clinical_evidence_agent.py",
     "tests": "tests/test_clinical_evidence_agent.py", "vps_input": "data/clinical_maturity_precutoff_clean.csv",
     "vps_via": "stage 03",
     "outputs": ["data/clinical_evidence.json", "data/clinical_maturity_precutoff_clean.csv",
                 "data/clinicaltrials_match_audit.csv"],
     "scope": "Stage 03 discovers and matches trials (feature = max phase, in VPS). The 10c layer adds registry "
              "status, posted results (primary analyses copied verbatim, never judged), the drug's role in every "
              "linked trial, and matching-audit outcomes. The 10c layer is diagnostic.",
     "sources": "ClinicalTrials.gov v2 (batched, cached)"},
    {"id": "10d", "name": "Conflict & Context", "module": "scripts/conflict_context_agent.py",
     "tests": "tests/test_conflict_context_agent.py", "vps_input": None, "outputs": [CONFLICT_JSON],
     "scope": "Pairwise classification of curated (case-study PMIDs), openFDA-label and molecular claims. Diagnostic.",
     "sources": "persisted only: docs/CASE_STUDIES.md claims, cached openFDA labels, stage-08 evidence, trial registry rows"},
    {"id": "10e", "name": "Reproducibility", "module": "scripts/reproducibility_agent.py",
     "tests": "tests/test_reproducibility_agent.py", "vps_input": None, "outputs": ["data/reproducibility.json"],
     "scope": "Finding-level replication by independent primary studies (shared authors / trial IDs / documented "
              "shared data); case-study compounds + Droxidopa paper sample. Diagnostic.",
     "sources": "cached PubMed efetch XML, 10d curated claims, trial registry rows"},
    {"id": "10f", "name": "Safety Evidence", "module": "scripts/safety_evidence_agent.py",
     "tests": "tests/test_safety_evidence_agent.py", "vps_input": "data/safety_signal.csv", "vps_via": "stage 05",
     "outputs": ["data/safety_evidence.json", "data/safety_signal.csv"],
     "scope": "Stage 05 label score is the VPS safety dimension. The 10f layer adds label provenance (DailyMed set id, "
              "boxed-warning text) and FAERS report counts (all-time and received by 2020, serious, deaths, top "
              "reactions) with explicit no-record / failed states. FAERS is not in VPS.",
     "sources": "openFDA drug label (stage 05 cache) + openFDA drug/event (FAERS, cached)"},
    {"id": "10g", "name": "Evidence Independence", "module": "scripts/evidence_independence_agent.py",
     "tests": "tests/test_evidence_independence_agent.py", "vps_input": "data/literature_independence.csv",
     "vps_via": "stage 04",
     "outputs": ["data/evidence_independence.json", "data/literature_independence.csv"],
     "scope": "Stage 04 measures dependence within the literature sample (VPS 'literature'). The 10g layer checks "
              "cross-source dependence: trials shared across candidates, one study counted in two dimensions, "
              "duplicated / pooled claims, molecular datatype reuse. Diagnostic; nothing de-duplicated in VPS.",
     "sources": "persisted stage 03/04/08 outputs, 10c output, cached PubMed XML, curated claims"},
    {"id": "10h", "name": "Completeness & Gap", "module": "scripts/completeness_gap_agent.py",
     "tests": "tests/test_completeness_gap_agent.py", "vps_input": None, "outputs": ["data/completeness_gaps.json"],
     "scope": "Per compound and evidence domain: measured / measured zero / absent at source / not computed / "
              "not retrieved / retrieval failed / insufficient, with VPS treatment, what would close each gap and "
              "open research questions. Checked against stage-06 dimensions_missing. Diagnostic.",
     "sources": "persisted stage 02-08 outputs, 10a/10d/10e outputs, TD-038 role adjudication"},
]


RUN_META = "data/test_run_metadata.json"


sys.path.insert(0, os.path.join(DEFAULT_ROOT, "scripts"))
from agent_contract import ENVELOPE_KEYS, stale_inputs as _contract_stale  # noqa: E402  (standard library only)
from agent_contract import input_changed as _contract_changed  # noqa: E402
from agent_contract import validate_envelope as _contract_validate  # noqa: E402
import run_stage as _runs  # noqa: E402  (status() reads the manifest and file fingerprints; it never runs anything)
import importlib.util as _ilu  # noqa: E402
_lr_spec = _ilu.spec_from_file_location("evirep_live_runs", os.path.join(UI_DIR, "live_runs.py"))
live_runs = _ilu.module_from_spec(_lr_spec)
_lr_spec.loader.exec_module(live_runs)   # Live Pipeline launches: only POST /api/run uses it, always via run_stage.py
MAX_RUN_BODY = 1024
SERVER_INSTANCE = secrets.token_hex(6)   # changes on every server start; lets an open page renew its session early
# The page's script and styles are read from disk on every request, but this process keeps the Python code it started
# with. After a code change the two can disagree (new page, old API) - found 2026-10-21. The server therefore reports
# when its own code on disk differs from what it is running.
_UI_DIR = os.path.dirname(os.path.abspath(__file__))
_SERVER_CODE = [os.path.join(_UI_DIR, "server.py"), os.path.join(_UI_DIR, "live_runs.py"),
                os.path.join(os.path.dirname(_UI_DIR), "scripts", "run_stage.py"), os.path.join(os.path.dirname(_UI_DIR), "scripts", "agent_contract.py")]


def _code_signature():
    sig = []
    for p in _SERVER_CODE:
        try:
            st_ = os.stat(p)
            sig.append((p, st_.st_size, st_.st_mtime_ns))
        except OSError:
            sig.append((p, None, None))
    return sig


_CODE_AT_START = _code_signature()


def _agent_run(root, a):
    """Run status / time / staleness / diagnostics from the agent's shared envelope (scripts/agent_contract.py).
    Agents without an envelope are reported as such, never given an invented status."""
    rels = list(a["outputs"][:1])
    if a.get("output_glob") and os.path.isdir(_abs(root, "data")):
        rels = sorted(f"data/{f}" for f in os.listdir(_abs(root, "data"))
                      if f.startswith(a["output_glob"]) and f.endswith(".json"))
    runs = []
    for rel in rels:
        if not rel.endswith(".json"):
            info = file_info(root, rel)
            runs.append({"output": rel, "contract": "none (tabular stage output; no input hashes recorded)",
                         "run_status": None, "generated_utc": info.get("modified") if info.get("exists") else None,
                         "stale_inputs": None, "present": bool(info.get("exists"))})
            continue
        data, err = read_json(root, rel)
        if err or not isinstance(data, dict):
            runs.append({"output": rel, "present": False, "error": err})
            continue
        has = all(k in data for k in ENVELOPE_KEYS)
        runs.append({"output": rel, "present": True, "contract": "agent_contract envelope" if has else "legacy (no envelope)",
                     "run_status": data.get("run_status") if has else None,
                     "generated_utc": data.get("generated_utc") if has else file_info(root, rel).get("modified"),
                     "stale_inputs": _contract_stale(root, data.get("inputs")) if has else None,
                     "coverage": data.get("coverage") if has else None,
                     "diagnostics": (data.get("diagnostics") or [])[:10] if has else []})
    worst = None
    order = ["FAILED", "PARTIAL", "NO_EVIDENCE", "SUCCESS"]
    sts = [r["run_status"] for r in runs if r.get("run_status")]
    if sts:
        worst = min(sts, key=order.index)
    stale = sorted({s_ for r in runs for s_ in (r.get("stale_inputs") or [])})
    return {"outputs": runs, "run_status": ("STALE" if stale else worst), "stale_inputs": stale,
            "generated_utc": max((r.get("generated_utc") or "" for r in runs), default=None) or None}


#: Tracked stages (scripts/run_stage.py) behind each agent, for dependency-aware freshness on the agent panel.
AGENT_STAGES = {"10a": ["10a", "10a-all"], "10b": ["08", "10b"], "10c": ["03", "03c", "10c", "review"], "10d": ["10d"],
                "10e": ["10e"], "10f": ["05", "05h", "10f"], "10g": ["04", "04p", "10g"], "10h": ["10h"]}
#: How each agent relates to the approved VPS (docs/autonomous_runs/EIGHT_AGENT_VPS_CONTRIBUTION_AUDIT.md).
AGENT_VPS_ROLE = {
    "10a": "diagnostic (evidence-quality annotation; not in VPS)",
    "10b": "score-contributing (stage 08 = VPS molecular dimension)",
    "10c": "score-contributing via stage 03 (clinical dimension); agent layer diagnostic; {review_open} awaiting human review",
    "10d": "diagnostic (categorical, curated claims; not in VPS)",
    "10e": "diagnostic (categorical, 4 compounds; not in VPS)",
    "10f": "score-contributing via stage 05 (safety dimension); agent layer diagnostic",
    "10g": "score-contributing via stage 04 (literature dimension); agent layer diagnostic (overlap checks)",
    "10h": "completeness annotation (never added to VPS)",
}


def _review_open(root):
    """Unresolved rows of the human trial-role worklist, counted from the file (was hard-coded "28"; audit 2026-10-21)."""
    try:
        with open(os.path.join(root, "data", "clinical_review_worklist.csv"), encoding="utf-8", newline="") as fh:
            n = sum(1 for r in csv.DictReader(fh) if (r.get("status") or "").startswith("UNRESOLVED"))
    except (OSError, csv.Error):
        return "links (count unavailable: worklist unreadable)"
    return f"{n} link{'s' if n != 1 else ''}"


def agent_vps_role(root, aid):
    role = AGENT_VPS_ROLE.get(aid)
    return role.replace("{review_open}", _review_open(root)) if role and "{review_open}" in role else role


_TRACK_ORDER = ["FAILED", "MISSING", "MODIFIED", "STALE", "RUNNING", "UNTRACKED", "NOT_RUN", "PARTIAL", "ADOPTED", "SUCCESS"]


def _tracked(st, sid):
    if not st:
        return {"stage": sid, "status": "UNKNOWN"}
    ls, la = st.get("last_success") or {}, st.get("last_attempt") or {}
    return {"stage": sid, "status": st["status"], "fresh": st["fresh"], "reasons": st["reasons"][:3],
            "warnings": st["warnings"][:3], "upstream": st.get("upstream"), "elapsed_s": st.get("elapsed_s"),
            "last_success_run_id": ls.get("run_id"), "last_success_utc": ls.get("finished_utc"),
            "duration_s": ls.get("duration_s"), "last_attempt_status": la.get("status"),
            "last_attempt_run_id": la.get("run_id"), "log": la.get("log")}


def _worst_tracked(tracked):
    sts = [t["status"] for t in tracked if t.get("status") in _TRACK_ORDER]
    return min(sts, key=_TRACK_ORDER.index) if sts else "UNKNOWN"


def build_agents(root):
    runmeta, _ = read_json(root, RUN_META)
    try:
        st_all = _runs.status(root, STAGES)
    except Exception as exc:       # the manifest is unreadable: say so rather than guess a status
        print(f"[evirep-ui] run status unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
        st_all = {}
    try:
        with open(_abs(root, "scripts/06_vps_fusion.py"), encoding="utf-8") as fh:
            fusion = fh.read()
    except OSError:
        fusion = ""
    out = []
    for a in AGENTS:
        mod = a["module"] and os.path.exists(_abs(root, a["module"]))
        n_tests = None
        if a["tests"] and os.path.exists(_abs(root, a["tests"])):
            with open(_abs(root, a["tests"]), encoding="utf-8") as fh:
                n_tests = len(re.findall(r"^\s+def test_", fh.read(), re.M))
        integrated = bool(a["vps_input"] and a["vps_input"] in fusion)
        outputs = [_strip_private(file_info(root, o)) for o in a["outputs"]]
        if not mod:
            status = "not implemented"
        elif integrated and a.get("vps_via") and n_tests:
            status = f"implemented + tested; {a['vps_via']} output in VPS, agent layer diagnostic"
        elif integrated:
            status = "integrated in VPS" + (" (partial agent)" if a["scope"].startswith("PARTIAL") else "")
        elif n_tests:
            status = "implemented + tested; diagnostic (not in VPS)"
        else:
            status = "implemented; no tests"
        schema = []
        for o in a["outputs"][:1]:
            if o.endswith(".json"):
                data, _ = read_json(root, o)
                schema = sorted(data.keys())[:25] if isinstance(data, dict) else []
            else:
                schema = (file_info(root, o).get("columns") or [])[:25]
        tested = (runmeta or {}).get("modules", {}).get(os.path.basename(a["tests"] or "")[:-3]) if a["tests"] else None
        run = _agent_run(root, a)
        tracked = [_tracked(st_all.get(sid), sid) for sid in AGENT_STAGES.get(a["id"], [])]
        out.append({**{k: a[k] for k in ("id", "name", "module", "tests", "scope", "sources")},
                    "vps_role": agent_vps_role(root, a["id"]), "tracked_runs": tracked,
                    "tracked_status": _worst_tracked(tracked),
                    "output_schema": schema, "latest_test_run": tested,
                    "module_exists": bool(mod), "n_test_functions": n_tests,
                    "integrated_in_vps": integrated, "vps_via": a.get("vps_via"), "outputs": outputs,
                    "status": status, "run": run})
    return {"agents": out, "test_run": {k: (runmeta or {}).get(k) for k in ("finished_utc", "total", "failures", "errors", "skipped")},
            "note": "Statuses are derived from files on disk. Test counts are the number of test functions in the "
                    "file; 'latest run' comes from data/test_run_metadata.json (scripts/record_test_run.py). "
                    "The UI never executes tests."}


def _conflicts(root):
    data, err = read_json(root, CONFLICT_JSON)
    return (data or {}), err


def build_overview(root):
    rows, err = read_csv(root, "data/vps_scores_v2.csv")
    out = {"saved_results_note": "Everything on this page is read from saved artefacts; nothing is recomputed "
                                 "or fetched when the page loads.",
           "endpoint": "Continued clinical investigation in PD (not therapeutic efficacy): a qualifying PD "
                       "interventional trial first posted on/after 2021-01-01 in the ClinicalTrials.gov snapshot "
                       "queried 2026-10-05, excluding data/label_role_exclusions.csv (D-010)."}
    if err:
        out["status"] = "data/vps_scores_v2.csv " + err
        return out
    out["cohort"] = {"compounds": len(rows), "positives": sum(r.get("label") == "1" for r in rows),
                     "negatives": sum(r.get("label") == "0" for r in rows)}
    ci, ci_err = read_csv(root, CI_CSV)
    out["primary_ci"] = ({"source": CI_CSV, "status": "artefact " + ci_err} if ci_err else
                         {"source": CI_CSV, "modified": file_info(root, CI_CSV).get("modified"),
                          **{k: num(ci[0].get(k)) if k not in ("a", "b") else ci[0].get(k)
                             for k in ("a", "b", "auroc_a", "ci_a_low", "ci_a_high", "auroc_b", "ci_b_low",
                                       "ci_b_high", "diff", "ci_diff_low", "ci_diff_high", "p_diff_gt_0",
                                       "n_boot", "seed")}})
    dims = []
    for d in DIMENSIONS:
        missing = sum(d["key"] in (r.get("dimensions_missing") or "").split("|") for r in rows)
        dims.append({"key": d["key"], "label": d["label"], "stage": d["stage"], "temporal": d["temporal"],
                     "measured": len(rows) - missing, "not_measured": missing})
    out["dimensions"] = dims
    measured = [num(r.get("n_dimensions_measured")) for r in rows]
    out["coverage"] = ({"dimensions_measured_counts": {k: sum(m == k for m in measured) for k in (5, 4, 3, 2, 1)}}
                       if any(m is not None for m in measured) else {"status": "n_dimensions_measured not in artefact"})
    key = ["data/vps_scores_v2.csv", "data/ground_truth_postcutoff_clean.csv", "data/label_role_exclusions.csv",
           "data/safety_signal.csv", "data/molecular_pathway.csv", "data/literature_independence.csv",
           "data/network_proximity.csv", CI_CSV, CONFLICT_JSON]
    out["artefacts"] = [_strip_private(file_info(root, k)) for k in key]
    c, cerr = _conflicts(root)
    out["conflicts"] = {"source": CONFLICT_JSON, "status": "artefact " + cerr} if cerr else \
        {"source": CONFLICT_JSON, "status_counts": c.get("status_counts")}
    return out


def build_ranking(root):
    rows, err = read_csv(root, "data/vps_scores_v2.csv")
    if err:
        return {"status": "data/vps_scores_v2.csv " + err, "rows": []}
    c, _ = _conflicts(root)
    cstat = {r["compound"]: r["status"] for r in c.get("records", [])}
    table, n = _ranks(rows, "VPS_equal_5d")
    imputed = set(_imputed_proximity(root, {r["compound_name"] for r in rows}).get("proximity_compounds") or [])
    out = []
    for r in rows:
        out.append({"compound": r["compound_name"], "rank": table.get(r["compound_name"]),
                    "label": num(r.get("label")), "VPS_equal_5d": num(r.get("VPS_equal_5d")),
                    "VPS_equal": num(r.get("VPS_equal")),
                    **{d["key"]: num(r.get(d["rank"])) for d in DIMENSIONS},
                    "n_dimensions_measured": num(r.get("n_dimensions_measured")),
                    "dimensions_missing": r.get("dimensions_missing") or "",
                    "dimensions_imputed": "proximity" if r["compound_name"] in imputed else "",
                    "conflict_status": cstat.get(r["compound_name"], "not assessed")})
    out.sort(key=lambda x: (x["rank"] is None, x["rank"] or 0))
    return {"source": "data/vps_scores_v2.csv", "rank_by": "VPS_equal_5d (primary, unfitted)", "of": n, "rows": out}


REPRO_JSON = "data/reproducibility.json"
EVAL_JSON = "data/vps_evaluation_report.json"
CASE_JSON = "data/case_study_status.json"


def build_case_status(root):
    data, err = read_json(root, CASE_JSON)
    if err:
        return {"source": CASE_JSON, "status": "artefact " + err, "cases": []}
    ranking = {r["compound"]: r for r in build_ranking(root).get("rows", [])}
    rp, _ = read_json(root, REPRO_JSON)
    cases = []
    for c in data.get("cases", []):
        r = ranking.get(c["compound"])
        reps = [{"finding": f["finding"], "status": f["status"], "independence": f.get("cluster_independence")}
                for f in (rp or {}).get("findings", []) if f["compound"] == c["compound"]]
        crit = c.get("criteria", {})
        cases.append({**c, "rank": r and r["rank"], "label": r and r["label"], "in_pool": bool(r),
                      "criteria_all_met": all(v is True or v == "not_applicable" for v in crit.values()),
                      "replication": reps})
    return {"source": CASE_JSON, "criteria_definitions": data.get("criteria_definitions"), "cases": cases}


def build_evaluation(root):
    data, err = read_json(root, EVAL_JSON)
    if err:
        return {"source": EVAL_JSON, "status": "artefact " + err}
    info = file_info(root, EVAL_JSON)
    stale = _stale_inputs(root, data.get("inputs"))
    return {"source": EVAL_JSON, "modified": info.get("modified"), "stale_inputs": stale, **data}


def _resolved_error_ids(root):
    """Error-log entries whose heading or body carries an explicit RESOLVED marker."""
    path = _abs(root, "development_log/ERRORS_AND_BLOCKERS.md")
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    done = set()
    for sec in re.split(r"(?m)^### ", text)[1:]:
        m = re.match(r"([A-Z]-\d+(?:-FIX)?) ", sec)
        if m and re.search(r"\bRESOLVED\b", sec):
            done.add(m.group(1))
    return done


def build_risks(root):
    done = _resolved_error_ids(root)
    items = [i for i in build_issue_index(root).values()
             if i["severity"].startswith(("HIGH", "BLOCKER")) and i["id"] not in done
             and ("OPEN" in (i["status"] or "") or not re.search(r"FIXED|RESOLVED|APPLIED", i["status"] or ""))]
    return {"source": "TECHNICAL_DEBT.md, development_log/ERRORS_AND_BLOCKERS.md", "open_high": items}


CANDIDATES_DIR = "data/_candidates"


def _pending_candidates(root):
    """Candidate result sets awaiting approval. Only their verification summaries are read, never their
    scores: the dashboard displays the approved data/vps_scores_v2.csv alone."""
    out = []
    base = _abs(root, CANDIDATES_DIR)
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        ver = os.path.join(base, name, "verification.json")
        if os.path.isfile(ver):
            try:
                with open(ver, encoding="utf-8") as fh:
                    ok = bool(json.load(fh).get("all_pass"))
            except (OSError, ValueError):
                ok = False
            out.append({"name": name, "path": f"{CANDIDATES_DIR}/{name}", "independently_verified": ok,
                        "approved": False, "displayed": False,          # never displayed AS the result
                        "compared": os.path.isfile(os.path.join(base, name, "comparison.json"))})
    return out


def build_result_set(root):
    """Data contract of the approved result set shown everywhere in the UI: which files, which run, which cohort, cutoff,
    scoring version and missing-data policy, and whether each file still matches the fingerprint recorded for that run.
    Everything is read from the run manifest, the evaluation report and the files; nothing is recomputed."""
    try:
        m = _runs.read_manifest(root)
    except _runs.ManifestError as exc:
        return {"status": f"run records unreadable ({exc})"}
    st = m.get("stages") or {}
    ls06, lsev = (st.get("06") or {}).get("last_success") or {}, (st.get("eval") or {}).get("last_success") or {}
    rep, err = read_json(root, EVAL_JSON)
    files = []
    for kind, rec in (("score output", ls06.get("outputs")), ("score input", ls06.get("inputs")), ("evaluation input", lsev.get("inputs")),
                      ("evaluation output", lsev.get("outputs"))):
        for rel, fp in sorted((rec or {}).items()):
            now = _runs.fingerprint(root, rel)
            recorded = (fp or {}).get("md5") if isinstance(fp, dict) else fp
            files.append({"role": kind, "path": rel, "md5_recorded": recorded, "md5_now": (now or {}).get("md5"),
                          "matches": bool(now) and (now or {}).get("md5") == recorded})
    st_now = _runs.status(root, STAGES)
    unv = [{"stage": k, "files": f} for k, v in st_now.items() for kind, f in _unfingerprinted(v) if k in ("06", "eval")]
    cohort = (rep or {}).get("cohort") or {} if not err else {}
    sc = ls06.get("scoring") or {}
    return {"result_set": "approved", "score_file": "data/vps_scores_v2.csv",
            "run_id": ls06.get("run_id"), "run_status": ls06.get("status"), "run_recorded_utc": ls06.get("finished_utc"),
            "baseline_lineage": sc.get("baseline_lineage"), "scoring_model": sc.get("model"), "rank_convention": sc.get("rank_convention"),
            "primary_score": "VPS_equal_5d = mean of five percentile ranks (equal weights 0.2)",
            "missing_policy": "safety without an FDA label and molecular without a target: neutral rank 0.5 (D-004); "
                              "missing proximity: pool median, flagged",
            "independent_recomputation": ls06.get("validation_ok"),
            "code_fingerprint_recorded": bool(ls06.get("code")),
            "cohort": {k: cohort.get(k) for k in ("n", "positives", "negatives", "prevalence", "label_definition")},
            "cutoff": "evidence: trials first posted before 2021-01-01; outcome: qualifying trials first posted 2021-01-01 to the 2026-10-05 registry snapshot",
            "evaluation": {"run_id": lsev.get("run_id"), "run_status": lsev.get("status"), "run_recorded_utc": lsev.get("finished_utc"),
                           "report_version": (rep or {}).get("report_version"), "seed": (rep or {}).get("seed"), "n_boot": (rep or {}).get("n_boot")},
            "files": files, "all_files_match": all(f["matches"] for f in files), "unfingerprinted": unv}


def build_alternatives(root):
    """Unapproved alternative result sets, shown as clearly labelled alternatives next to (never instead of) the
    approved result. Only a candidate's persisted comparison (scripts/compare_result_sets.py: same cohort, same labels,
    the report's own bootstrap procedure) is read; nothing is recomputed here. A comparison whose recorded inputs no
    longer match the files on disk is withheld as stale."""
    out = []
    base = _abs(root, CANDIDATES_DIR)
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        rel = f"{CANDIDATES_DIR}/{name}/comparison.json"
        data, err = read_json(root, rel)
        if err:
            continue
        ver, verr = read_json(root, f"{CANDIDATES_DIR}/{name}/verification.json")
        stale = _stale_inputs(root, data.get("inputs"))
        rec = {"name": name, "source": rel, "status": "NOT APPROVED", "approved": False,
               "independently_verified": bool((ver or {}).get("all_pass")) if not verr else False,
               "decision": data.get("decision"), "rule": data.get("rule"), "generated_utc": data.get("generated_utc"),
               "stale_inputs": stale}
        if stale:
            rec["withheld"] = "the comparison's inputs changed since it was computed; re-run scripts/compare_result_sets.py"
        elif not (data.get("cohort") or {}).get("labels_identical"):
            rec["withheld"] = "not computed on the approved cohort and labels"
        else:
            rec.update({k: data.get(k) for k in ("cohort", "metrics", "paired", "dimensions_changed", "top10_overlap", "procedure", "ranks")})
        out.append(rec)
    return {"alternatives": out,
            "note": "Alternatives are shown for comparison only. The approved result set is data/vps_scores_v2.csv."}


def build_status(root):
    """Lightweight, poll-friendly run status (dependency-aware; see scripts/run_stage.py).
    data_version changes whenever any registered output or the run manifest changes, so an open
    page knows when to reload its data; it never triggers computation or external requests."""
    st = _runs.status(root, STAGES)
    sig = []
    for rel in sorted({o for s_ in STAGES for o in s_["outputs"]} | {_runs.MANIFEST, RUN_META}):
        try:
            info = os.stat(_abs(root, rel))
            sig.append((rel, info.st_size, info.st_mtime_ns))
        except OSError:
            sig.append((rel, None, None))
    version = hashlib.sha1(json.dumps(sig).encode()).hexdigest()[:16]
    vps = st.get("06", {})
    manifest_error = None
    try:
        m = _runs.read_manifest(root)
    except _runs.ManifestError as exc:       # shown, never hidden: every stage is UNKNOWN until it is restored
        m, manifest_error = {}, str(exc)
    ls = ((m.get("stages") or {}).get("06") or {}).get("last_success") or {}
    groups = {}
    for v in st.values():
        groups.setdefault(v["status"], []).append(v["id"])
    groups["ATTEMPT_FAILED"] = [v["id"] for v in st.values() if v.get("latest_attempt_failed")]
    unverifiable = [v["id"] for v in st.values() if _unfingerprinted(v)]
    if unverifiable:
        groups["UNVERIFIABLE"] = unverifiable
    return {"data_version": version, "server_time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "manifest_updated_utc": m.get("updated_utc"), "manifest_error": manifest_error,
            "server_instance": SERVER_INSTANCE,
            "server_code_changed": _code_signature() != _CODE_AT_START,
            "vps": {"status": vps.get("status"), "fresh": vps.get("fresh"), "reasons": vps.get("reasons"),
                    "warnings": vps.get("warnings"), "latest_attempt_failed": vps.get("latest_attempt_failed"),
                    "retained_run_id": vps.get("retained_run_id"), "last_success": vps.get("last_success"),
                    "last_attempt": vps.get("last_attempt"),
                    "scoring": ls.get("scoring"), "validation_ok": ls.get("validation_ok"),
                    "displayed_run_id": ls.get("run_id")},
            "approved_baseline": {"path": "data/vps_scores_v2.csv", "run_id": ls.get("run_id")},
            "pending_candidates": _pending_candidates(root),
            "by_status": groups,
            "stages": list(st.values()),
            "history": (m.get("history") or [])[-15:],
            "commands": {"status": "./venv/bin/python scripts/run_stage.py --status",
                         "run_stage": "./venv/bin/python scripts/run_stage.py <stage id>",
                         "vps": "./venv/bin/python scripts/run_stage.py 06"}}


RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z-[A-Za-z0-9-]{1,20}-[0-9a-f]{4}$")
LOG_TAIL_LINES = 80


def build_log(root, run_id):
    """Last lines of one tracked run's log (data/_runs/<run_id>/log.txt), redacted. The run id is validated
    and the path confined to data/_runs, so no other file can be read."""
    if not RUN_ID_RE.match(run_id or ""):
        return None
    runs = os.path.realpath(_abs(root, _runs.RUNS_DIR))
    path = os.path.realpath(os.path.join(runs, run_id, "log.txt"))
    if os.path.dirname(os.path.dirname(path)) != runs or not os.path.isfile(path):
        return None
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        size = fh.tell()
        fh.seek(max(0, size - 64 * 1024))
        lines = fh.read().decode("utf-8", "replace").splitlines()[-LOG_TAIL_LINES:]
    return {"run_id": run_id, "log": f"{_runs.RUNS_DIR}/{run_id}/log.txt", "bytes": size,
            "tail_lines": len(lines), "tail": "\n".join(lines)}


def build_health(root):
    """Liveness + readiness for a supervisor: cheap, read-only, starts nothing, reveals no paths or secrets.
    ready = the run manifest is readable and the approved score file exists."""
    try:
        _runs.read_manifest(root)
        manifest = "readable"
    except _runs.ManifestError:
        manifest = "unreadable"
    vps = os.path.exists(_abs(root, "data/vps_scores_v2.csv"))
    return {"live": True, "ready": manifest == "readable" and vps, "manifest": manifest,
            "approved_scores_present": vps, "server_time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def build_runmeta(root):
    data, err = read_json(root, RUN_META)
    return ({"source": RUN_META, "status": "artefact " + err} if err else {"source": RUN_META, **data})


GAPS_JSON = "data/completeness_gaps.json"
CLINICAL_JSON = "data/clinical_evidence.json"
SAFETY_JSON = "data/safety_evidence.json"
CRED_ALL = "data/literature_credibility_all.json"
INDEP_JSON = "data/evidence_independence.json"


def _stale_inputs(root, inputs):
    """Inputs (path -> md5, or None when absent at run time) that no longer match the file on disk; one rule shared
    with agent_contract.input_changed (a None entry is stale once the file exists)."""
    return [rel for rel, md5 in (inputs or {}).items() if _contract_changed(root, rel, md5)]


def _gaps(root):
    data, err = read_json(root, GAPS_JSON)
    return (data if isinstance(data, dict) else {}), err


def build_gaps(root):
    """Cohort-level view of agent 10h: state counts, label-associated missingness, compact per-compound rows."""
    g, err = _gaps(root)
    if err:
        return {"source": GAPS_JSON, "status": "artefact " + err, "rows": []}
    rows = [{"compound": r["compound"], "rank": r.get("rank_vps_equal_5d"), "label": r.get("label"),
             "vps_dimensions_missing": r.get("vps_dimensions_missing", []),
             "imputed_not_flagged": r.get("vps_dimensions_imputed_not_flagged", []),
             "n_gaps": len(r.get("gaps", [])),
             "states": {k: v.get("state") for k, v in (r.get("domains") or {}).items()}}
            for r in g.get("records", [])]
    return {"source": GAPS_JSON, "modified": file_info(root, GAPS_JSON).get("modified"),
            "agent_version": g.get("agent_version"), "schema_version": g.get("schema_version"),
            "integration": g.get("integration"), "stale_inputs": _stale_inputs(root, g.get("inputs")),
            "stage06_agreement": g.get("stage06_agreement"), "state_meaning": g.get("state_meaning"),
            "domains": g.get("domains"), "state_counts_by_domain": g.get("state_counts_by_domain"),
            "missingness_vs_label": g.get("missingness_vs_label"), "limitations": g.get("limitations"),
            "cohort": g.get("cohort"), "rows": rows}


REVIEW_CSV = "data/clinical_review_worklist.csv"
REVIEW_COLS = ("priority", "flag", "all_flags", "nct_id", "compound", "brief_title", "intervention_text", "arm_types",
               "current_role_automated", "structural_reading", "current_role_adjudicated", "reason_for_flag",
               "evidence_needed", "status")


def build_review(root):
    """The human-review queue for clinical trial roles, read-only. Decisions are never recorded here: they belong in
    the D-020 adjudication file by a named reviewer."""
    path = _abs(root, REVIEW_CSV)
    if not os.path.exists(path):
        return {"source": REVIEW_CSV, "status": "artefact missing (run stage 'review')", "rows": []}
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REVIEW_COLS if c not in (reader.fieldnames or [])]
        if missing:
            return {"source": REVIEW_CSV, "status": f"artefact malformed (missing columns {missing})", "rows": []}
        rows = [{c: r.get(c) or "" for c in REVIEW_COLS} for r in reader]
    unresolved = [r for r in rows if r["status"].startswith("UNRESOLVED")]
    by_flag = {}
    for r in rows:
        by_flag[r["flag"]] = by_flag.get(r["flag"], 0) + 1
    return {"source": REVIEW_CSV, "modified": file_info(root, REVIEW_CSV).get("modified"),
            "n_links": len(rows), "n_unresolved": len(unresolved), "n_adjudicated": len(rows) - len(unresolved),
            "by_flag": dict(sorted(by_flag.items())),
            "decision_file": "data/feature_trial_roles_td038.csv",
            "policy": "Read-only. Unresolved links keep their automated role in scoring and stay flagged until a human "
                      "records a decision (D-020). Nothing on this page approves a match.",
            "rows": rows}


DIM_LABEL = {"proximity": "network proximity", "clinical": "clinical maturity", "literature": "literature independence",
             "safety": "safety (FDA label)", "molecular": "molecular plausibility"}


def _summary(row, rank, of, claims, safety_row):
    """Researcher-facing summary built only from persisted values (no new inference)."""
    missing = [d for d in (row.get("dimensions_missing") or "").split("|") if d]
    ranks = {d: num(row.get("r_" + d)) for d in DIM_LABEL}
    high = [f"{DIM_LABEL[d]} ({v:.2f})" for d, v in ranks.items() if v is not None and d not in missing and v >= 2 / 3]
    low = [f"{DIM_LABEL[d]} ({v:.2f})" for d, v in ranks.items() if v is not None and d not in missing and v <= 1 / 3]
    score = num(row.get("VPS_equal_5d"))
    parts = [f"Ranked {rank} of {of} by the equal-weight 5-dimension score (VPS {score:.3f})." if score is not None
             and rank else "No equal-weight 5-dimension score in data/vps_scores_v2.csv for this compound."]
    if high:
        parts.append("Upper third of the pool on: " + ", ".join(high) + ".")
    if low:
        parts.append("Lower third on: " + ", ".join(low) + ".")
    if missing:
        parts.append("Not measured (placed at the neutral 0.5 rank, not counted for or against): "
                     + ", ".join(DIM_LABEL.get(d, d) for d in missing) + ".")
    parts.append("A rank orders the pool by available evidence; it is not a probability and not evidence of efficacy.")
    pick = lambda dirs, types=None: [{k: c.get(k) for k in ("source_id", "source_type", "source_date", "domain",
                                                             "direction", "endpoint_measure", "excerpt", "provenance",
                                                             "temporal", "caveat")}
                                     for c in claims if c.get("direction") in dirs
                                     and (types is None or c.get("source_type") in types)]
    concerns = []
    if safety_row:
        sr = _clean_row(safety_row)
        if sr.get("has_label") == "True":
            if sr.get("boxed_warning") == "True":
                concerns.append({"text": "FDA label carries a boxed warning", "source": "data/safety_signal.csv",
                                 "label_set_id": sr.get("label_set_id"), "label_date": sr.get("label_effective_time")})
            if num(sr.get("serious_term_count")):
                concerns.append({"text": f"{int(num(sr.get('serious_term_count')))} serious term(s) in label warnings "
                                         f"({sr.get('warning_fields')})", "source": "data/safety_signal.csv",
                                 "label_set_id": sr.get("label_set_id"), "label_date": sr.get("label_effective_time")})
        else:
            concerns.append({"text": "No US FDA label found: safety is unmeasured, not 'safe'",
                             "source": "data/safety_signal.csv"})
    concerns += [{"text": c["excerpt"], "source": c["source_id"], "label_date": c.get("source_date"),
                  "provenance": c.get("provenance")} for c in pick({"OPPOSES"}) if c.get("domain") in ("safety", "disease_risk")]
    return {"text": " ".join(parts), "strengths": high, "weaknesses": low, "not_measured": missing,
            "supporting": pick({"SUPPORTS"}),
            "null_or_opposing": [c for c in pick({"NULL_RESULT", "OPPOSES"}) if c.get("domain") not in ("safety", "disease_risk")],
            "safety_concerns": concerns,
            "note": "Supporting, null and opposing items are the directional claims extracted from saved sources "
                    "(curated case-study publications, FDA labels, Open Targets) by the Conflict & Context agent. Clinical-trial registrations are not "
                    "listed here: a trial's existence is not evidence of benefit."}


_NCT = re.compile(r"^NCT\d{8}$")


def _results_note(t):
    r = (t or {}).get("results") or {}
    if r.get("state") == "RESULTS_POSTED":
        return f"results posted {r.get('results_first_posted')} ({r.get('n_primary_analyses', 0)} primary analyses)"
    return {"NO_RESULTS_POSTED": "no results posted", "NOT_IN_REGISTRY": "not returned by the registry",
            "RETRIEVAL_FAILED": "registry retrieval failed"}.get(r.get("state"), "results not checked")


def build_evidence(root):
    """One flat, source-linked index of persisted evidence items across compounds (no external request)."""
    items = []
    ce, _ = read_json(root, CLINICAL_JSON)
    trial_meta = (ce or {}).get("trials", {}) if isinstance(ce, dict) else {}
    pre, perr = read_csv(root, "data/clinical_maturity_precutoff_clean.csv")
    post, qerr = read_csv(root, "data/ground_truth_postcutoff_clean.csv")
    for rows, err, role, rel in ((pre, perr, "pre-cutoff trial (clinical feature)", "data/clinical_maturity_precutoff_clean.csv"),
                                 (post, qerr, "post-cutoff trial (label only)", "data/ground_truth_postcutoff_clean.csv")):
        for r in ([] if err else rows):
            if _NCT.match(r.get("nct_id") or ""):
                items.append({"type": "clinical", "compound": r.get("compound_name"), "id": r["nct_id"], "id_kind": "nct",
                              "date": r.get("first_posted"), "role": role,
                              "detail": f"phase {r.get('phase') or 'n/a'} · {r.get('status') or ''} · matched "
                                        f"'{r.get('matched_intervention') or ''}'"
                                        + ("" if rel != "data/clinical_maturity_precutoff_clean.csv" else
                                           " · " + _results_note(trial_meta.get(r["nct_id"]))), "source": rel})
    c, _ = _conflicts(root)
    for rec in c.get("records", []):
        for cl in rec.get("claims", []):
            if cl.get("source_type") == "curated_doc":
                m = re.search(r"PMID\s*(\d{6,9})", cl.get("source_id") or "")
                items.append({"type": "literature", "compound": rec["compound"], "id": m.group(1) if m else cl.get("source_id"),
                              "id_kind": "pmid" if m else "text", "date": cl.get("source_date"),
                              "role": f"{cl.get('direction')} · {cl.get('domain')}",
                              "detail": cl.get("excerpt"), "source": cl.get("provenance")})
    for name in os.listdir(_abs(root, "data")) if os.path.isdir(_abs(root, "data")) else []:
        if name.startswith("literature_graph_") and name.endswith(".json"):
            g, gerr = read_json(root, "data/" + name)
            for n in (g or {}).get("nodes", []) if not gerr and isinstance(g, dict) else []:
                if isinstance(n, dict) and str(n.get("pmid", "")).isdigit():
                    items.append({"type": "literature", "compound": name[len("literature_graph_"):-5].replace("_", " ").title(),
                                  "id": str(n["pmid"]), "id_kind": "pmid", "date": n.get("year"),
                                  "role": "stage-04 paper sample", "detail": n.get("title"), "source": "data/" + name})
    saf, serr = read_csv(root, "data/safety_signal.csv")
    for r in ([] if serr else saf):
        if r.get("has_label") == "True":
            items.append({"type": "safety", "compound": r.get("compound_name"), "id": r.get("label_set_id"),
                          "id_kind": "setid", "date": r.get("label_effective_time"), "role": "FDA label (current)",
                          "detail": f"boxed warning {r.get('boxed_warning')} · serious terms {r.get('serious_term_count')} "
                                    f"· fields {r.get('warning_fields')}", "source": "data/safety_signal.csv"})
        else:
            items.append({"type": "safety", "compound": r.get("compound_name"), "id": None, "id_kind": "none",
                          "date": None, "role": "no US FDA label found (absent at source)",
                          "detail": "safety not measured", "source": "data/safety_signal.csv"})
    path = _abs(root, "data/molecular_pathway_evidence.jsonl")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                for t in rec.get("targets") or []:
                    if isinstance(t, dict):
                        items.append({"type": "molecular", "compound": rec.get("drug"), "id": t.get("ensembl_id"),
                                      "id_kind": "ensembl", "date": None, "role": f"target · {t.get('action_type') or ''}",
                                      "detail": f"{t.get('gene_symbol')}: {t.get('mechanism_of_action') or ''}",
                                      "chembl_id": rec.get("chembl_id"), "source": "data/molecular_pathway_evidence.jsonl"})
    review = {}
    for r in build_review(root).get("rows", []):
        review[(r.get("compound"), r.get("nct_id"))] = "awaiting" if str(r.get("status")).startswith("UNRESOLVED") else "adjudicated"
    for it in items:
        it["stance"], it["basis"] = _evidence_nature(it, review)
    counts = {}
    for it in items:
        counts[it["type"]] = counts.get(it["type"], 0) + 1
    return {"counts": counts, "items": items,
            "note": "Every row is read from a persisted artefact. Identifier links open the public record in a new tab "
                    "only when you click them; this page itself makes no external request."}


def _evidence_nature(it, review):
    """(stance, basis) of one evidence item, from how it was produced - never from its content's apparent strength.
    stance: supporting | null_or_opposing | context | outcome_label | safety_concern | no_listed_concern | missing | not_assessed
    basis: automatic | curated | human_reviewed | awaiting_review | hypothesis"""
    t, role = it["type"], str(it.get("role") or "")
    if t == "clinical":
        rv = review.get((it.get("compound"), it.get("id")))
        basis = "human_reviewed" if rv == "adjudicated" else "awaiting_review" if rv == "awaiting" else "automatic"
        return ("outcome_label" if "label only" in role else "context"), basis
    if t == "literature":
        if role.startswith("stage-04"):
            return "not_assessed", "automatic"
        d = role.split(" · ")[0]
        return ("supporting" if d == "SUPPORTS" else "null_or_opposing" if d in ("NULL_RESULT", "OPPOSES") else "context"), "curated"
    if t == "safety":
        if it.get("id_kind") == "none":
            return "missing", "automatic"
        det = str(it.get("detail") or "")
        concern = "boxed warning True" in det or not re.search(r"serious terms (0(\.0)?|nan|None)\b", det)
        return ("safety_concern" if concern else "no_listed_concern"), "automatic"
    if t == "molecular":
        return "context", "hypothesis"
    return "not_assessed", "automatic"


def build_conflicts(root):
    c, err = _conflicts(root)
    if err:
        return {"source": CONFLICT_JSON, "status": "artefact " + err, "records": []}
    keep = [r for r in c.get("records", []) if r.get("status") not in ("INSUFFICIENT", "NO_EVIDENCE")]
    return {"source": CONFLICT_JSON, "agent_version": c.get("agent_version"), "integration": c.get("integration"),
            "status_counts": c.get("status_counts"), "records": keep}


def build_compound(root, name):
    result = {"query": name, "found_in": [], "missing_sources": [], "dimensions": {}}

    vps_rows, vps_err = read_csv(root, "data/vps_scores_v2.csv")
    vps = _find(vps_rows, name)
    if vps:
        row = vps[0]
        result["found_in"].append("data/vps_scores_v2.csv")
        ranks = {}
        for col in ("VPS_equal", "VPS_equal_5d", "VPS_grid_4d", "VPS_grid_3d", "VPS_grid_5d"):
            if col in row:
                table, n = _ranks(vps_rows, col)
                ranks[col] = {"score": num(row.get(col)), "rank": table.get(row["compound_name"]), "of": n}
        label = row.get("label")
        missing_dims = [d for d in (row.get("dimensions_missing") or "").split("|") if d]
        result["pool"] = {
            "in_evaluable_pool": True, "label": num(label),
            "label_meaning": "1 = a qualifying PD interventional trial naming this compound was first posted on/after "
                             f"{CUTOFF_DATE}, excluding trials listed in data/label_role_exclusions.csv "
                             "(TD-032). It measures later trial activity, NOT efficacy; 0 means no qualifying "
                             "trial was found, not that the drug is ineffective.",
            "dimensions_missing": missing_dims,
            "n_dimensions_measured": num(row.get("n_dimensions_measured")),
            "fused_scores": ranks,
            "fitted_variants_note": "VPS_grid_* use weights selected on all labelled data; their ranks are in-sample.",
            "source": "data/vps_scores_v2.csv",
            "duplicates": len(vps) - 1,
        }
    else:
        result["pool"] = {"in_evaluable_pool": False,
                          "reason": "not in data/vps_scores_v2.csv" if not vps_err else f"data/vps_scores_v2.csv {vps_err}",
                          "label_meaning": "Compounds enter the evaluable pool only with an accepted pre-cutoff PD "
                                           "trial (stage 03 + study-type filter)."}

    def dim_block(dim, source, rows_err, matched, fields):
        block = {"definition": dim["definition"], "temporal": dim["temporal"], "stage": dim["stage"],
                 "source": source}
        rows, err = rows_err
        if err:
            block["status"] = "artefact " + err
            result["missing_sources"].append(source)
        elif not matched:
            block["status"] = "no record for this compound"
        else:
            block["status"] = "present"
            result["found_in"].append(source)
            rec = _clean_row(matched[0])
            block["record"] = {k: rec.get(k) for k in fields if k in rec}
            if len(matched) > 1:
                block["warning"] = f"{len(matched)} rows for this compound in {source}; showing the first"
        if vps:
            r = vps[0]
            block["in_vps"] = {k: num(r.get(k)) for k in (dim["raw"], dim["rank"]) if k in r}
            if dim["key"] in (r.get("dimensions_missing") or "").split("|"):
                block["not_measured"] = ("No measurement for this compound: ranked at the neutral 0.5 in the "
                                         "fusion (D-004), not as best or worst.")
        return block

    dims = {d["key"]: d for d in DIMENSIONS}

    prox = read_csv(root, "data/network_proximity.csv")
    result["dimensions"]["proximity"] = dim_block(
        dims["proximity"], "data/network_proximity.csv", prox, _find(prox[0], name),
        ["compound_id", "n_targets", "n_targets_in_network", "d_real", "d_rand_mean", "d_rand_std",
         "proximity_z", "n_random"])

    # Clinical: pre-cutoff = feature, post-cutoff = label only, plus the audit trail.
    pre = read_csv(root, "data/clinical_maturity_precutoff_clean.csv")
    post = read_csv(root, "data/ground_truth_postcutoff_clean.csv")
    audit = read_csv(root, "data/clinicaltrials_match_audit.csv")
    trial_fields = ["nct_id", "phase", "status", "enrollment", "first_posted", "match_type",
                    "matched_intervention", "matched_alias", "match_source"]
    clin = {"definition": dims["clinical"]["definition"], "temporal": dims["clinical"]["temporal"],
            "stage": "03", "source": "data/clinical_maturity_precutoff_clean.csv"}
    excl_rows, excl_err = read_csv(root, "data/label_role_exclusions.csv")
    excluded = {} if excl_err else {(e.get("nct_id"), (e.get("compound_name") or "").lower()): e for e in excl_rows}
    for key, (rows, err), rel in (("precutoff_trials_feature", pre, "data/clinical_maturity_precutoff_clean.csv"),
                                  ("postcutoff_trials_label_only", post, "data/ground_truth_postcutoff_clean.csv")):
        if err:
            clin[key] = {"status": "artefact " + err, "source": rel}
            result["missing_sources"].append(rel)
        else:
            m = _find(rows, name)
            clin[key] = {"source": rel, "trials": [{k: _clean_row(t).get(k) for k in trial_fields} for t in m]}
            if key == "postcutoff_trials_label_only":
                for t in clin[key]["trials"]:
                    e = excluded.get((t.get("nct_id"), name.lower()))
                    t["excluded_from_label"] = (f"{e.get('role_verdict')}: {e.get('evidence')}" if e else None)
                clin[key]["exclusions_source"] = ("data/label_role_exclusions.csv" if not excl_err
                                                  else f"data/label_role_exclusions.csv {excl_err}")
            if m:
                result["found_in"].append(rel)
    rows, err = audit
    if err:
        clin["match_audit"] = {"status": "artefact " + err, "source": "data/clinicaltrials_match_audit.csv"}
        result["missing_sources"].append("data/clinicaltrials_match_audit.csv")
    else:
        m = _find(rows, name)
        clin["match_audit"] = {
            "source": "data/clinicaltrials_match_audit.csv",
            "policy": "docs/INTERVENTION_MATCHING.md — only MATCHED qualifies; UNVERIFIABLE is not API_FAILURE.",
            "decisions": [{k: redact(_clean_row(a).get(k)) for k in
                           ("nct_id", "brief_title", "cohort", "outcome", "qualifies", "match_type",
                            "matched_intervention", "matched_alias", "interventions", "reason")} for a in m],
        }
    if vps:
        clin["in_vps"] = {k: num(vps[0].get(k)) for k in ("max_phase_rank", "n_trials", "r_clinical")}
    result["dimensions"]["clinical"] = clin

    lit = read_csv(root, "data/literature_independence.csv")
    lit_block = dim_block(dims["literature"], "data/literature_independence.csv", lit, _find(lit[0], name),
                          ["raw_paper_count", "effective_independent_count", "independence_ratio",
                           "edges_shared_author", "edges_citation", "citation_lookup_failures",
                           "citation_coverage_complete"])
    # Same filename convention as 04b/07, but derived from the artefact's own
    # compound name (never the raw query) and restricted to a safe slug, so a
    # request cannot steer the read outside data/literature_graph_*.json.
    canonical = next((m[0].get("compound_name") for m in (vps, _find(lit[0], name)) if m), None)
    slug = str(canonical).lower().replace(" ", "_") if canonical else ""
    if _SLUG_RE.match(slug):
        graph_rel = f"data/literature_graph_{slug}.json"
        graph, gerr = read_json(root, graph_rel)
    else:
        graph_rel, graph, gerr = "data/literature_graph_<compound>.json", None, "missing"
    if graph is not None and isinstance(graph, dict):
        nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
        edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
        lit_block["paper_graph"] = {
            "source": graph_rel, "verified_against": graph.get("verified_against"),
            "counts": graph.get("counts"), "component_sizes": graph.get("component_sizes"),
            "papers": [{k: n.get(k) for k in ("pmid", "year", "title", "component", "n_authors")}
                       for n in nodes if isinstance(n, dict)],
            "edges": [{k: e.get(k) for k in ("source", "target", "reason")} for e in edges if isinstance(e, dict)],
        }
    else:
        lit_block["paper_graph"] = {"source": graph_rel,
                                    "status": "no persisted paper graph for this compound"
                                    if gerr == "missing" else f"graph {gerr}"}
    result["dimensions"]["literature"] = lit_block

    saf = read_csv(root, "data/safety_signal.csv")
    result["dimensions"]["safety"] = dim_block(dims["safety"], "data/safety_signal.csv", saf, _find(saf[0], name),
                                               ["has_label", "boxed_warning", "serious_term_count"])
    if vps:
        result["dimensions"]["safety"]["in_vps"] = {k: num(vps[0].get(k)) for k in
                                                    ("serious_term_count", "r_safety")}

    mol = read_csv(root, "data/molecular_pathway.csv")
    mol_block = dim_block(dims["molecular"], "data/molecular_pathway.csv", mol, _find(mol[0], name),
                          ["chembl_id", "resolved", "molecular_plausibility_score", "confidence",
                           "direct_component", "pathway_component", "n_targets", "n_genes", "n_pathways",
                           "n_pathways_in_disease_module", "n_direct_disease_links", "n_disease_link_rows",
                           "n_evidence_direct", "n_evidence_indirect", "n_evidence_inferred",
                           "n_evidence_missing"])
    mol_block["confidence_note"] = ("confidence measures whether evidence could be looked up "
                                    "(availability), not the probability that the drug works.")
    n = _norm(name)
    rec, err, bad = read_jsonl_where(root, "data/molecular_pathway_evidence.jsonl",
                                     lambda r: _norm(r.get("drug")) == n)
    if rec is not None:
        scoring = rec.get("scoring") if isinstance(rec.get("scoring"), dict) else {}
        mol_block["evidence_chain"] = {
            "source": "data/molecular_pathway_evidence.jsonl",
            "explanation": scoring.get("explanation"),
            "weights": scoring.get("weights"),
            "targets": [{k: t.get(k) for k in ("gene_symbol", "ensembl_id", "mechanism_of_action", "action_type")}
                        for t in rec.get("targets") or [] if isinstance(t, dict)],
            "disease_links": [{
                "gene_symbol": d.get("gene_symbol"),
                "score_allowed_datatypes": d.get("score_allowed_datatypes"),
                "datatype_scores_used": d.get("datatype_scores_used"),
                "datatype_scores_excluded_for_leakage": d.get("datatype_scores_excluded_for_leakage"),
            } for d in rec.get("disease_links") or [] if isinstance(d, dict)],
            "mechanistic_chain": [{k: st.get(k) for k in ("step", "from", "from_id", "to", "to_id", "via", "via_id",
                                                          "relation", "detail", "tier", "source", "strength")}
                                  for st in (rec.get("mechanistic_chain") or [])[:120] if isinstance(st, dict)],
            "n_mechanistic_steps": len(rec.get("mechanistic_chain") or []),
            "pathways": [{k: pw.get(k) for k in ("pathway_id", "pathway_name", "top_level_term", "gene_symbol",
                                                 "in_disease_module", "tier")}
                         for pw in (rec.get("pathways") or [])[:200] if isinstance(pw, dict)],
            "n_pathways": len(rec.get("pathways") or []),
            "chembl_id": rec.get("chembl_id"),
            "limitations": rec.get("limitations") if isinstance(rec.get("limitations"), list) else [],
            "provenance": rec.get("provenance") if isinstance(rec.get("provenance"), dict) else None,
        }
    else:
        mol_block["evidence_chain"] = {"source": "data/molecular_pathway_evidence.jsonl",
                                       "status": ("no evidence record for this compound" if err is None
                                                  else f"evidence file {err}")}
    if bad:
        mol_block["evidence_chain"]["malformed_lines_skipped"] = bad
    result["dimensions"]["molecular"] = mol_block

    c, cerr = _conflicts(root)
    if cerr:
        result["conflict_context"] = {"source": CONFLICT_JSON, "status": "artefact " + cerr}
    else:
        rec = _find(c.get("records", []), name, key="compound")
        result["conflict_context"] = ({"source": CONFLICT_JSON, **rec[0]} if rec else
                                      {"source": CONFLICT_JSON, "status": "compound not assessed by 10d"})
    rp, rerr = read_json(root, REPRO_JSON)
    result["reproducibility"] = ({"source": REPRO_JSON, "status": "artefact " + rerr} if rerr else {
        "source": REPRO_JSON,
        "findings": [f for f in rp.get("findings", []) if _norm(f["compound"]) == _norm(name)],
        "publication_structure": next((s_ for s_ in rp.get("publication_structures", [])
                                       if _norm(s_["compound"]) == _norm(name)), None),
        "shared_trials": [t for t in rp.get("shared_trials_across_compounds", {}).get("trials", [])
                          if any(_norm(c) == _norm(name) for c in t["compounds"])],
        "finding_status_meaning": rp.get("finding_status_meaning")})
    slug = re.sub(r"[^a-z0-9]+", "_", (vps[0]["compound_name"] if vps else name).lower()).strip("_")
    cred_rel = f"data/literature_credibility_{slug}.json"
    if _SLUG_RE.match(slug) and os.path.exists(_abs(root, cred_rel)):
        cred, _ = read_json(root, cred_rel)
        result["literature_credibility"] = {"source": cred_rel, "summary_pre_cutoff": (cred or {}).get("summary_pre_cutoff"),
                                            "summary_all": (cred or {}).get("summary_all"),
                                            "efficacy": (cred or {}).get("efficacy")}
    else:
        allc, aerr = read_json(root, CRED_ALL)
        rec = ((allc or {}).get("compounds") or {}).get(vps[0]["compound_name"] if vps else name) if not aerr else None
        if rec is not None:
            result["literature_credibility"] = {
                "source": CRED_ALL, "status_10a": rec.get("status"), "efficacy": (allc or {}).get("efficacy"),
                "summary_pre_cutoff": rec.get("summary_cutoff_bounded"), "summary_all": rec.get("summary_stage04_sample"),
                "note": rec.get("note") or "pre-cutoff = every primary paper published on or before 2020-12-31 (stage 04p); "
                                           "all = the stage-04 sample (30 most recent hits)",
                "duplicates_removed": len(rec.get("duplicates_removed") or [])}
    if vps:
        table, of = _ranks(vps_rows, "VPS_equal_5d")
        crec = _find(c.get("records", []), name, key="compound") if not cerr else []
        result["summary"] = _summary(vps[0], table.get(vps[0]["compound_name"]), of,
                                     (crec[0].get("claims") or []) if crec else [], (_find(saf[0], name) or [None])[0])
    for key, rel, list_key in (("clinical_evidence", CLINICAL_JSON, "compounds"), ("safety_evidence", SAFETY_JSON, "records"),
                               ("evidence_independence", INDEP_JSON, "records")):
        data, err = read_json(root, rel)
        if err or not isinstance(data, dict):
            result[key] = {"source": rel, "status": "artefact " + (err or "unreadable")}
            continue
        hit = _find(data.get(list_key, []), name, key="compound")
        block = {"source": rel, "agent_id": data.get("agent_id"), "agent_version": data.get("agent_version"),
                 "run_status": data.get("run_status"), "generated_utc": data.get("generated_utc"),
                 "stale_inputs": _contract_stale(root, data.get("inputs")) if isinstance(data.get("inputs"), dict) else None,
                 "limitations": data.get("limitations"),
                 "state_meaning": data.get("results_state_meaning") or data.get("state_meaning") or data.get("check_state_meaning")}
        if not hit:
            block["status"] = "compound not covered by this agent"
        else:
            block.update(hit[0])
            if key == "clinical_evidence":
                block["trial_records"] = [data.get("trials", {}).get(l["nct_id"]) for l in hit[0].get("links", [])]
        result[key] = block
    g, gerr = _gaps(root)
    grec = _find(g.get("records", []), name, key="compound") if not gerr else []
    result["completeness"] = ({"source": GAPS_JSON, "status": "artefact " + gerr} if gerr else
                              {"source": GAPS_JSON, "agent_version": g.get("agent_version"),
                               "stale_inputs": _stale_inputs(root, g.get("inputs")),
                               "state_meaning": g.get("state_meaning"), "domains_meta": g.get("domains"),
                               **grec[0]} if grec else
                              {"source": GAPS_JSON, "status": "compound not assessed by 10h (outside the evaluable pool)"})
    result["found_in"] = sorted(set(result["found_in"]))
    result["missing_sources"] = sorted(set(result["missing_sources"]))
    result["known"] = bool(result["found_in"] or (audit[1] is None and clin["match_audit"].get("decisions")))
    return result


# ============================================================
# 6. VALIDATION VIEW
# ============================================================

HISTORICAL = {
    "label": "Historical corrected-cohort results (development_log/CHANGES.md, TECHNICAL_DEBT.md TD-020)",
    "items": [
        "90 compounds, 17 positives, 73 negatives",
        "5-dim equal-weight VPS: AUROC 0.747, AUPRC 0.479",
        "4-dim equal-weight VPS: AUROC 0.689",
        "Paired AUROC difference +0.059, 95% CI [-0.024, +0.150] — NOT statistically significant",
        "Grid-searched variants: report nested-CV (held-out) AUROC, never the in-sample value",
    ],
    "caveat": "Historical claims. The tables below are read from the persisted CSVs; compare them, do not assume.",
}


def _metrics_table(root, rel):
    rows, err = read_csv(root, rel)
    if err:
        return {"source": rel, "status": "artefact " + err}
    info = file_info(root, rel)
    return {"source": rel, "modified": info.get("modified"), "columns": info.get("columns"),
            "rows": [_clean_row(r) for r in rows]}


def build_validation(root):
    vps_rows, err = read_csv(root, "data/vps_scores_v2.csv")
    integrity = {"source": "data/vps_scores_v2.csv"}
    if err:
        integrity["status"] = "artefact " + err
    else:
        names = [_norm(r.get("compound_name")) for r in vps_rows]
        score_cols = [c for c in ("r_proximity", "r_clinical", "r_literature", "r_safety", "r_molecular",
                                  "VPS_equal", "VPS_equal_5d", "label") if vps_rows and c in vps_rows[0]]
        nonfinite = {c: sum(1 for r in vps_rows if num(r.get(c)) is None) for c in score_cols}
        integrity.update({
            "rows": len(vps_rows),
            "positives": sum(1 for r in vps_rows if r.get("label") == "1"),
            "negatives": sum(1 for r in vps_rows if r.get("label") == "0"),
            "duplicate_compounds": len(names) - len(set(names)),
            "missing_or_nonfinite_by_column": nonfinite,
        })
    figures = []
    data_dir = _abs(root, "data")
    if os.path.isdir(data_dir):
        for fn in sorted(os.listdir(data_dir)):
            if FIGURE_RE.match(fn):
                figures.append(_strip_private(file_info(root, f"data/{fn}")))
    return {
        "historical": HISTORICAL,
        "integrity": integrity,
        "variants": _metrics_table(root, "data/vps_variant_results.csv"),
        "baselines": _metrics_table(root, "data/baseline_results_v2.csv"),
        "ablation_4d": _metrics_table(root, "data/ablation_results_v2.csv"),
        "ablation_5d": _metrics_table(root, "data/ablation_results_5d.csv"),
        "figures": figures,
        "tests": {"command": "./venv/bin/python -m unittest discover -s tests",
                  "note": "Not executed by the UI. Run it from the repository root."},
    }


def read_doc(root, key):
    rel = DOCS.get(key)
    if rel is None:
        return None
    path = _abs(root, rel)
    if not os.path.exists(path):
        return {"key": key, "path": rel, "status": "missing", "text": ""}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as exc:
        return {"key": key, "path": rel, "status": _err(exc), "text": ""}
    return {"key": key, "path": rel, "text": redact(text), "modified": file_info(root, rel).get("modified")}


# ============================================================
# 7. HTTP SERVER (local, GET only)
# ============================================================

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    # Same-origin only; no inline script, no framing, no form posts, no base-tag tricks.
    "Content-Security-Policy": ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
                                "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def _host_is_loopback(host_header):
    """True when a Host header names this machine's loopback interface."""
    if not host_header:
        return False
    host = host_header.strip().lower()
    if host.startswith("["):                      # [::1]:8765
        host = host[1:host.find("]")] if "]" in host else ""
    elif host.count(":") == 1:                    # name:port
        host = host.split(":")[0]
    return host in LOOPBACK_HOSTS


# ============================================================
# LIVE APPLICATION API (2026-10-20): the dashboard's single source, derived from scripts/run_stage.py state.
# Nothing here reads Markdown or documentation; it never starts work.
# ============================================================

AGENT_OUTPUT = {"10a": "data/literature_credibility_all.json", "10b": "data/molecular_agent_run.json",
                "10c": "data/clinical_evidence.json", "10d": "data/conflict_context.json",
                "10e": "data/reproducibility.json", "10f": "data/safety_evidence.json",
                "10g": "data/evidence_independence.json", "10h": "data/completeness_gaps.json"}
AGENT_KIND = {"10a": "diagnostic", "10b": "VPS input", "10c": "VPS input", "10d": "diagnostic", "10e": "diagnostic",
              "10f": "VPS input", "10g": "VPS input", "10h": "annotation"}
_ENV_CACHE = {}


def _envelope(root, rel):
    """Agent output envelope, re-read only when the file changes (the dashboard polls every few seconds)."""
    p = _abs(root, rel)
    try:
        st = os.stat(p)
    except OSError:
        return None
    key = (p, st.st_mtime_ns, st.st_size)
    if key not in _ENV_CACHE:
        data, err = read_json(root, rel)
        _ENV_CACHE.clear() if len(_ENV_CACHE) > 64 else None
        _ENV_CACHE[key] = data if not err and isinstance(data, dict) else None
    return _ENV_CACHE[key]


def _stale_cached(root, inputs):
    """Inputs (path -> md5) an agent recorded that no longer match the file, using the run tracker's fingerprint cache
    (re-hashed only when size or mtime changes), so polling stays cheap. Same result as agent_contract.stale_inputs."""
    out = []
    for rel, md5 in (inputs or {}).items():
        fp = _runs.fingerprint(root, rel)
        if (bool(fp) if md5 is None else (not fp or fp.get("md5") != md5)):
            out.append(rel)
    return out


def _envelope_valid(env):
    if not env:
        return None
    try:
        return bool(_contract_validate(env))
    except Exception:
        return False


def _coverage_line(aid, cov):
    """One honest headline from the agent's own coverage block (no derived or invented numbers)."""
    c = cov or {}
    g = lambda *ks: next((c[k] for k in ks if c.get(k) is not None), None)
    try:
        if aid == "10a":
            return f"{c['assessed']}/{c['compounds']} compounds assessed · {c['papers_rated']} papers rated"
        if aid == "10b":
            return f"{c['with_targets']}/{c['pool_compounds']} compounds with targets · {c['without_targets']} unmeasured"
        if aid == "10c":
            r = c.get("results") or {}
            return f"{c['compounds']} compounds · {c['trials']} trials · {r.get('RETRIEVAL_FAILED', 0)} retrieval failures"
        if aid == "10d":
            return f"{c['assessed']}/{c['compounds']} assessed · {c['insufficient']} insufficient evidence"
        if aid == "10e":
            return f"{c['findings']} findings · {c['publication_records']} publication records"
        if aid == "10f":
            lab, cut = c.get("label") or {}, c.get("label_at_cutoff") or {}
            return (f"labels {lab.get('RETRIEVED', 0)}/{c['compounds']} · at cutoff {cut.get('SCORED', 0)} scored, "
                    f"{cut.get('UNKNOWN', 0)} unknown")
        if aid == "10g":
            d2 = (c.get("checks") or {}).get("D2_same_study_in_two_dimensions") or {}
            return (f"same study in two dimensions: {d2.get('DEPENDENCE_FOUND', 0)} found, "
                    f"{d2.get('NOT_ASSESSABLE', 0)} not assessable")
        if aid == "10h":
            return f"{c['compounds']} compounds × {c['domains']} domains · {c['gaps']} gaps"
    except (KeyError, TypeError):
        pass
    n = g("compounds", "pool_compounds")
    return f"{n} compounds" if n is not None else "coverage not reported"


def _depths(stages):
    by, depth = {s["id"]: s for s in stages}, {}

    def d(i):
        if i not in depth:
            depth[i] = 1 + max((d(x) for x in by[i]["depends_on"] if x in by), default=-1)
        return depth[i]
    for s in stages:
        d(s["id"])
    return depth


def _stage_brief(v, policy_cls, depth):
    ls, la = v.get("last_success") or {}, v.get("last_attempt") or {}
    return {"id": v["id"], "name": v["name"], "status": v["status"], "fresh": v["fresh"], "depth": depth,
            "reasons": v["reasons"][:3], "n_warnings": len(v["warnings"]), "warnings": v["warnings"][:2],
            "upstream": [u["id"] for u in v.get("upstream") or []], "elapsed_s": v.get("elapsed_s"),
            "last_activity": v.get("last_activity"), "policy": policy_cls,
            "last_success": {k: ls.get(k) for k in ("run_id", "finished_utc", "duration_s")} if ls else None,
            "last_attempt": {k: la.get(k) for k in ("run_id", "status", "started_utc", "finished_utc", "duration_s",
                                                     "exit_code", "log")} if la else None,
            "latest_attempt_failed": v.get("latest_attempt_failed")}


# ---- truthful freshness, sources and scientific state for the Dashboard (2026-10-20 UI quality pass) ----
#: Owner-only scientific decisions that the application must surface and never resolve by itself.
OPEN_DECISIONS = [
    {"id": "TD-042", "title": "Molecular-dimension rule", "detail": "A corrected molecular rule exists as an unapproved candidate result set; the approved score keeps the original rule.", "href": "#validation"},
    {"id": "TD-033", "title": "Temporal validity", "detail": "Literature, safety and molecular evidence use current snapshots, not data frozen at the cutoff.", "href": "#validation"},
    {"id": "B-003", "title": "Evaluation reproducibility", "detail": "A from-source rerun gives AUROC 0.7763 versus the approved 0.7754 (network-proximity resampling); the approved scores reproduce exactly from their saved inputs.", "href": "#validation"},
]


def build_freshness(st):
    """Stage freshness from the run tracker only (never from file dates alone)."""
    ls_times = [v["last_success"]["finished_utc"] for v in st.values() if v.get("last_success") and v["last_success"].get("finished_utc")]
    untracked, untracked_out = [], []
    for v in st.values():
        for kind, files in _unfingerprinted(v):
            (untracked if kind == "input" else untracked_out).append({"stage": v["id"], "name": v.get("name"), "detail": files,
                                                                     "rewrites_protected": _rewrites_protected(v["id"])})
    return {"last_success_utc": max(ls_times) if ls_times else None,
            "inputs_changed": [v["id"] for v in st.values() if v["status"] in ("STALE", "MODIFIED", "MISSING")],
            "code_unverifiable": [v["id"] for v in st.values() if v.get("last_success") and not v.get("code_fingerprint_recorded")],
            "untracked_inputs": untracked, "untracked_outputs": untracked_out}


def _unfingerprinted(v):
    """(kind, files) for each runner warning about a declared input/output that its last success did not fingerprint."""
    out = []
    for w in v.get("warnings") or []:
        if "not fingerprinted" in w:
            out.append(("output" if w.startswith("declared output") else "input", w.split(": ", 1)[-1]))
    return out


def _rewrites_protected(sid):
    s = next((x for x in STAGES if x["id"] == sid), None)
    return bool(s and set(s["outputs"]) & live_runs.PROTECTED_ARTEFACTS)


def build_sources(root):
    """External sources with the retrieval or snapshot facts that the artefacts actually record."""
    out = []
    lp = _envelope(root, "data/literature_provenance_run.json")
    if isinstance(lp, dict):
        out.append({"source": "PubMed", "what": "paper records for the literature dimension and its provenance",
                    "retrieved_utc": lp.get("generated_utc"), "cutoff": lp.get("cutoff"),
                    "note": f"{lp.get('from_network', '?')} retrieved over the network and {lp.get('from_cache', '?')} from cache in that run; "
                            f"{lp.get('n_failed', '?')} failures"})
    ce = _envelope(root, CLINICAL_JSON)
    if isinstance(ce, dict):
        out.append({"source": "ClinicalTrials.gov", "what": "registry status and posted results of linked trials",
                    "retrieved_utc": (ce.get("coverage") or {}).get("registry_retrieved_utc"), "cutoff": "2020-12-31",
                    "note": "trials first posted before the cutoff are evidence; trials posted after it are outcome labels"})
    lh = _envelope(root, "data/safety_label_history_run.json")
    if isinstance(lh, dict):
        out.append({"source": "DailyMed (FDA label history)", "what": "label version in force at the cutoff",
                    "retrieved_utc": lh.get("generated_utc"), "cutoff": lh.get("cutoff"),
                    "note": "time of the last tracked run of this stage; version histories are cached"})
    out.append({"source": "openFDA drug labels", "what": "current label used by the safety dimension", "retrieved_utc": None,
                "cutoff": None, "note": "retrieval time not recorded in the saved labels; these are current labels, not labels at the cutoff"})
    out.append({"source": "Open Targets Platform", "what": "target-disease associations and pathways (molecular dimension)",
                "retrieved_utc": None, "snapshot": "data version 26.09", "cutoff": None,
                "note": "snapshot version recorded in the stage documentation; a current snapshot, not frozen at the cutoff"})
    out.append({"source": "Hetionet v1.0", "what": "protein interaction network (proximity dimension)", "retrieved_utc": None,
                "snapshot": "2017 release", "cutoff": None, "note": "predates the cutoff"})
    return out


def build_science(root, base):
    rev = build_review(root)
    pending = [c for c in base.get("pending_candidates") or []]
    rep = _envelope(root, "data/vps_evaluation_report.json")
    prim = next((p for p in (rep or {}).get("primary", []) if p.get("column") == "VPS_equal_5d"), {}) if isinstance(rep, dict) else {}
    return {"approved_run_id": (base.get("vps") or {}).get("displayed_run_id"),
            "independent_recomputation": (base.get("vps") or {}).get("validation_ok"),
            "cohort": (rep or {}).get("cohort") if isinstance(rep, dict) else None,
            "primary_metric": {"name": "AUROC", "model": prim.get("model"), "value": prim.get("auroc"), "ci95": prim.get("auroc_ci95"),
                               "auprc": prim.get("auprc"), "auprc_ci95": prim.get("auprc_ci95")} if prim else None,
            "paired_5d_vs_4d": (rep or {}).get("paired_5d_vs_4d") if isinstance(rep, dict) else None,
            "temporal_validity": (rep or {}).get("temporal_validity") if isinstance(rep, dict) else None,
            "reviews_awaiting": (rev or {}).get("n_unresolved") if isinstance(rev, dict) else None,
            "reviews_adjudicated": (rev or {}).get("n_adjudicated") if isinstance(rev, dict) else None,
            "pending_candidates": [{"id": c.get("name"), "label": "Corrected molecular rule (TD-042), version 1" if c.get("name") == "td042_v1" else c.get("name"),
                                    "independently_verified": c.get("independently_verified")} for c in pending],
            "open_decisions": OPEN_DECISIONS}


def _imputed_proximity(root, pool):
    """Pool compounds whose raw proximity is missing (median-imputed by stage 06; the saved score holds the median)."""
    raw, err = read_csv(root, "data/network_proximity.csv")
    if err:
        return {"proximity": None}
    have = {r.get("compound_name") for r in raw if num(r.get("proximity_z")) is not None}
    names = sorted(pool - have)
    return {"proximity": len(names), "proximity_compounds": names}


def build_validation_charts(root):
    """ROC/PR points straight from the approved scores and labels, checked against the approved evaluation report
    (a chart is only served if its area matches the report); model comparison and missingness from the report."""
    rows, err = read_csv(root, "data/vps_scores_v2.csv")
    rep, rerr = read_json(root, "data/vps_evaluation_report.json")
    if err or rerr or not isinstance(rep, dict):
        return {"error": "evaluation artefacts unavailable"}
    pts = sorted(((num(r.get("VPS_equal_5d")), int(num(r.get("label")) or 0)) for r in rows if num(r.get("VPS_equal_5d")) is not None),
                 key=lambda x: -x[0])
    P = sum(y for _, y in pts); N = len(pts) - P
    roc, pr, tp, fp, ap = [[0.0, 0.0]], [], 0, 0, 0.0
    i = 0
    while i < len(pts):                       # group ties so the curve is correct with tied scores
        j = i
        while j < len(pts) and pts[j][0] == pts[i][0]:
            j += 1
        dtp = sum(y for _, y in pts[i:j]); dfp = (j - i) - dtp
        tp += dtp; fp += dfp
        if dtp:
            ap += (dtp / P) * (tp / (tp + fp))
        roc.append([fp / N, tp / P]); pr.append([tp / P, tp / (tp + fp)])
        i = j
    auc = sum((roc[k][0] - roc[k - 1][0]) * (roc[k][1] + roc[k - 1][1]) / 2 for k in range(1, len(roc)))
    prim = next(p for p in rep["primary"] if p["column"] == "VPS_equal_5d")
    ok = abs(auc - prim["auroc"]) < 1e-9 and abs(ap - prim["auprc"]) < 1e-9
    md = rep.get("missing_data") or {}
    return {"source": "data/vps_scores_v2.csv + data/vps_evaluation_report.json", "n": len(pts), "positives": P, "negatives": N,
            "prevalence": P / len(pts) if pts else None,
            "roc": roc if ok else None, "pr": pr if ok else None, "auroc_recomputed": auc, "auprc_recomputed": ap,
            "matches_report": ok,
            "models": [{"model": p["model"], "auroc": p["auroc"], "ci95": p.get("auroc_ci95"), "auprc": p.get("auprc"),
                        "kind": "unfitted"} for p in rep["primary"]],
            "baselines": rep.get("baselines"), "ablation": rep.get("ablation_5d"),
            "paired_5d_vs_4d": rep.get("paired_5d_vs_4d"),
            "missing_by_dimension": md.get("not_measured_by_dimension"), "imputation_paths": md.get("imputation_paths"),
            "imputed_by_dimension": _imputed_proximity(root, {r.get("compound_name") for r in rows}),
            "grid_search_note": (rep.get("grid_search") or {}).get("note")}


def _next_actions(st, pol, manifest_error):
    """What the user should do next, derived only from tracked state. Owner-only work is labelled as such."""
    if manifest_error:
        return [{"level": "bad", "who": "operator", "text": "Run records are unreadable: diagnose with ./venv/bin/python "
                 "scripts/run_stage.py --check-manifest and restore data/run_manifest.json from a recovery snapshot."}]
    out, vals = [], list(st.values())
    running = [v["id"] for v in vals if v["status"] == "RUNNING"]
    if running:
        out.append({"level": "info", "who": "anyone", "text": f"Wait: {', '.join(running)} running; this page updates by itself."})
    for v in vals:
        orphan = next((r for r in v["reasons"] if "still running orphaned" in r), None)
        if orphan:
            out.append({"level": "bad", "who": "operator", "stage": v["id"], "text": f"{v['id']}: {orphan}; then "
                        f"./venv/bin/python scripts/run_stage.py --restore {v['id']}"})
    failed = [v["id"] for v in vals if v.get("latest_attempt_failed") and v["status"] != "RUNNING"]
    for sid in failed:
        out.append({"level": "bad", "who": "anyone" if pol.get(sid) == "ALLOWED" else "owner", "stage": sid,
                    "text": f"{sid} failed: open its page, read the error log, fix the cause, then re-run "
                            + (f"{sid} from its page." if pol.get(sid) == "ALLOWED" else "it from the command line.")})
    stale = [v["id"] for v in vals if v["status"] in ("STALE", "MODIFIED", "MISSING") and v["id"] not in failed]
    mine = [x for x in stale if pol.get(x) == "ALLOWED"]
    theirs = [x for x in stale if pol.get(x) != "ALLOWED"]
    if mine and not running:
        out.append({"level": "warn", "who": "anyone", "text": f"Out of date: {', '.join(mine)}. Use 'Run all permitted stages'."})
    if theirs:
        out.append({"level": "warn", "who": "owner", "text": f"Out of date and protected or network-bound: {', '.join(theirs)}. "
                    "Owner decision: review, then run from the command line in an isolated copy first."})
    never = [v["id"] for v in vals if v["status"] in ("NOT_RUN", "UNTRACKED")]
    if never:
        out.append({"level": "warn", "who": "owner", "text": f"Never run under the tracker: {', '.join(never)}."})
    for v in vals:
        for kind, files in _unfingerprinted(v):
            consequence = ("Re-running it rewrites approved research data, so this is the owner's decision: approve a re-run or "
                           "leave it as is." if _rewrites_protected(v["id"]) else "Re-running the stage records the missing fingerprint.")
            out.append({"level": "info", "who": "owner" if _rewrites_protected(v["id"]) else "anyone", "stage": v["id"],
                        "text": f"{v.get('name') or v['id']} {'reads' if kind == 'input' else 'writes'} {files}, which was not "
                                f"fingerprinted at its last run, so changes to it cannot be detected. {consequence}"})
        for w in v["warnings"]:
            if "code changed" in w:
                out.append({"level": "info", "who": "owner", "stage": v["id"],
                            "text": f"Stage {v['id']}'s code changed after its last successful run; re-run it to apply the change."})
    if not out:
        out.append({"level": "ok", "who": "anyone", "text": "Nothing to do: every tracked stage is current."})
    return out


def build_live(root):
    st = _runs.status(root, STAGES)
    base = build_status(root)                                   # data_version, manifest_error, vps, history
    depth = _depths(STAGES)
    order = [s["id"] for s in _runs._topo(STAGES)]
    pol = {s["id"]: live_runs.policy(s)[0] for s in STAGES}
    stages = [_stage_brief(st[i], pol[i], depth[i]) for i in order]
    counts = {}
    for v in st.values():
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    running = [v["id"] for v in st.values() if v["status"] == "RUNNING"]
    failed = [v["id"] for v in st.values() if v["status"] == "FAILED" or v.get("latest_attempt_failed")]
    stale = [v["id"] for v in st.values() if v["status"] in ("STALE", "MODIFIED", "MISSING")]
    unknown = [v["id"] for v in st.values() if v["status"] in ("UNKNOWN", "UNTRACKED", "NOT_RUN")]
    # CURRENT only when every declared input and output was fingerprinted; otherwise currentness is limited, not proven.
    unverifiable = any(_unfingerprinted(v) for v in st.values())
    state = ("UNKNOWN" if base.get("manifest_error") else "RUNNING" if running else "FAILED" if failed
             else "STALE" if stale else "INCOMPLETE" if unknown else "VERIFIED_WITH_GAPS" if unverifiable else "CURRENT")
    agents = []
    for a in AGENTS:
        aid, sids = a["id"], AGENT_STAGES.get(a["id"], [])
        env = _envelope(root, AGENT_OUTPUT[aid])
        tracked = [st[x] for x in sids if x in st]
        own = [t for t in tracked if t["id"].startswith("10") or t["id"] == "review"]
        latest = max((t["last_attempt"] for t in own if t.get("last_attempt")), key=lambda x: x.get("started_utc") or "",
                     default=None)
        agents.append({"id": aid, "name": a["name"], "kind": AGENT_KIND[aid], "role": agent_vps_role(root, aid),
                       "stages": sids, "status": _worst_tracked([_tracked(st.get(x), x) for x in sids]),
                       "running": any(t["status"] == "RUNNING" for t in tracked),
                       "latest_attempt_failed": any(t.get("latest_attempt_failed") for t in own),
                       "running_activity": next(((t["id"], t.get("elapsed_s"), t.get("last_activity")) for t in tracked
                                                 if t["status"] == "RUNNING"), None),
                       "latest_attempt": {k: (latest or {}).get(k) for k in ("run_id", "status", "started_utc",
                                                                            "finished_utc", "duration_s")} if latest else None,
                       "output_run_status": (env or {}).get("run_status"), "output_generated_utc": (env or {}).get("generated_utc"),
                       "output_envelope_valid": _envelope_valid(env),
                       "output_stale_inputs": len(_stale_cached(root, env.get("inputs"))) if env else None,
                       "coverage_line": _coverage_line(aid, (env or {}).get("coverage")) if env else "output unavailable",
                       "launchable": [x for x in sids if pol.get(x) == "ALLOWED"]})
    hist = []
    for h in reversed(base.get("history") or []):
        hist.append({**{k: h.get(k) for k in ("run_id", "stage", "status", "started_utc", "finished_utc", "exit_code")},
                     "duration_s": _runs._seconds(h.get("started_utc"), h.get("finished_utc"))})
    launches = live_runs.launches(root)[:5]
    vps = base["vps"]
    return {"server_time_utc": base["server_time_utc"], "data_version": base["data_version"],
            "manifest_error": base.get("manifest_error"),
            "next_actions": _next_actions(st, pol, base.get("manifest_error")),
            "freshness": build_freshness(st), "sources": build_sources(root), "science": build_science(root, base),
            "overall": {"state": state, "counts": counts, "running": running, "failed": failed, "stale": stale,
                        "unknown": unknown, "n_stages": len(st)},
            "stages": stages, "agents": agents, "history": hist[:12],
            "launches": [{k: l.get(k) for k in ("launch_id", "state", "command", "exit_code", "requested_utc",
                                                 "finished_utc", "sequence")} for l in launches],
            "results": {"approved_path": "data/vps_scores_v2.csv", "vps_status": vps.get("status"),
                        "vps_run_id": vps.get("displayed_run_id"), "validation_ok": vps.get("validation_ok"),
                        "fresh": vps.get("fresh"), "pending_candidates": [c.get("name") for c in base.get("pending_candidates") or []]},
            "n_allowed": sum(1 for c in pol.values() if c == "ALLOWED")}


def _artefact(root, rel, recorded):
    fp = _runs.fingerprint(root, rel)
    rec = (recorded or {}).get(rel)
    return {"path": rel, "exists": fp is not None,
            "modified_utc": datetime.fromtimestamp(fp["mtime_ns"] / 1e9, timezone.utc).isoformat(timespec="seconds") if fp else None,
            "bytes": fp.get("size") if fp else None,
            "matches_last_success": None if rec is None or fp is None else rec.get("md5") == fp.get("md5")}


def build_agent_detail(root, aid):
    a = next((x for x in AGENTS if x["id"] == aid), None)
    if a is None:
        return None
    st = _runs.status(root, STAGES)
    m = _runs.read_manifest(root) if not any(v["status"] == "UNKNOWN" for v in st.values()) else {}
    reg = {s["id"]: s for s in STAGES}
    stages = []
    for sid in AGENT_STAGES.get(aid, []):
        s, v = reg[sid], st.get(sid) or {}
        ls = ((m.get("stages") or {}).get(sid) or {}).get("last_success") or {}
        la = v.get("last_attempt") or {}
        log = build_log(root, (la.get("run_id") or "")) if la.get("run_id") else None
        stages.append({"id": sid, "name": s["name"], "script": s["script"], "purpose": s.get("purpose"),
                       "depends_on": s["depends_on"], "status": v.get("status"), "reasons": v.get("reasons"),
                       "warnings": v.get("warnings"), "policy": dict(zip(("class", "reason"), live_runs.policy(s))),
                       "elapsed_s": v.get("elapsed_s"), "last_activity": v.get("last_activity"),
                       "last_success": v.get("last_success"), "last_attempt": v.get("last_attempt"),
                       "code_fingerprint_recorded": v.get("code_fingerprint_recorded"),
                       "inputs": [_artefact(root, x, ls.get("inputs")) for x in s["inputs"]],
                       "outputs": [_artefact(root, x, ls.get("outputs")) for x in s["outputs"]],
                       "log_tail": (log or {}).get("tail")})
    env = _envelope(root, AGENT_OUTPUT[aid]) or {}
    valid = None
    if env:
        try:
            valid = bool(_contract_validate(env))
        except Exception:
            valid = False
    return {"id": aid, "name": a["name"], "kind": AGENT_KIND[aid], "role": agent_vps_role(root, aid),
            "scope": a.get("scope"), "sources": a.get("sources"), "module": a.get("module"), "tests": a.get("tests"),
            "output": AGENT_OUTPUT[aid], "stages": stages,
            "envelope": {"present": bool(env), "valid": valid, "run_status": env.get("run_status"),
                         "agent_version": env.get("agent_version"), "generated_utc": env.get("generated_utc"),
                         "coverage": env.get("coverage"), "coverage_line": _coverage_line(aid, env.get("coverage")) if env else None,
                         "diagnostics": (env.get("diagnostics") or [])[:12],
                         "stale_inputs": _contract_stale(root, env.get("inputs")) if env else None,
                         "limitations": (env.get("limitations") or [])[:6]}}


def build_session(nonce):
    """What the Live Pipeline view needs before it may POST: the per-server nonce and the launch policy."""
    return {"session_nonce": nonce, "run_controls": "enabled for allow-listed stages",
            "cancellation": "not offered: stopping the runner mid-stage would skip its restore-on-failure step",
            "policy": {s["id"]: dict(zip(("class", "reason"), live_runs.policy(s))) for s in STAGES}}


def make_handler(root):
    root = os.path.abspath(root)
    data_dir = os.path.realpath(_abs(root, "data"))
    nonce = live_runs.new_nonce()        # a cross-site page cannot read it (no CORS), so it cannot POST /api/run

    class Handler(BaseHTTPRequestHandler):
        server_version = "EviRepUI"
        sys_version = ""                          # don't advertise the Python version

        def log_message(self, fmt, *args):  # quiet by default
            pass

        def _send(self, code, body, ctype):
            data = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            for k, v in SECURITY_HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def _json(self, payload, code=200):
            body = json.dumps(sanitize(payload, root), default=str, allow_nan=False)
            self._send(code, body, "application/json; charset=utf-8")

        def send_error(self, code, message=None, explain=None):
            # Replaces the stdlib HTML error page (which lacks these headers).
            # Only the standard reason phrase is returned, never request text.
            try:
                reason = self.responses.get(code, ("error",))[0]
                self.close_connection = True
                self._json({"error": reason}, code)
            except Exception:
                pass

        def do_GET(self):
            if not _host_is_loopback(self.headers.get("Host")):
                return self._json({"error": "host not allowed"}, 403)
            url = urlparse(self.path)
            q = parse_qs(url.query)
            try:
                if url.path in STATIC:
                    fn, ctype = STATIC[url.path]
                    with open(os.path.join(UI_DIR, fn), "rb") as fh:
                        return self._send(200, fh.read(), ctype)
                if url.path == "/favicon.ico":           # browsers request it; answer without a console 404
                    return self._send(204, b"", "image/x-icon")
                if url.path == "/api/pipeline":
                    return self._json(build_pipeline(root))
                if url.path == "/api/dimensions":
                    return self._json(DIMENSIONS)
                if url.path == "/api/compounds":
                    return self._json(list_compounds(root))
                if url.path == "/api/compound":
                    name = (q.get("name") or [""])[0][:200]
                    if not name.strip():
                        return self._json({"error": "name required"}, 400)
                    return self._json(build_compound(root, name))
                if url.path == "/api/validation":
                    return self._json(build_validation(root))
                if url.path == "/api/overview":
                    return self._json(build_overview(root))
                if url.path == "/api/ranking":
                    return self._json(build_ranking(root))
                if url.path == "/api/agents":
                    return self._json(build_agents(root))
                if url.path == "/api/conflicts":
                    return self._json(build_conflicts(root))
                if url.path == "/api/case_status":
                    return self._json(build_case_status(root))
                if url.path == "/api/evaluation":
                    return self._json(build_evaluation(root))
                if url.path == "/api/risks":
                    return self._json(build_risks(root))
                if url.path == "/api/gaps":
                    return self._json(build_gaps(root))
                if url.path == "/api/evidence":
                    return self._json(build_evidence(root))
                if url.path == "/api/review":
                    return self._json(build_review(root))
                if url.path == "/api/status":
                    return self._json(build_status(root))
                if url.path == "/api/live":
                    return self._json(build_live(root))
                if url.path == "/api/validation_charts":
                    return self._json(build_validation_charts(root))
                if url.path == "/api/alternatives":
                    return self._json(build_alternatives(root))
                if url.path == "/api/result_set":
                    return self._json(build_result_set(root))
                if url.path == "/api/agent":
                    d = build_agent_detail(root, (q.get("id") or [""])[0][:8])
                    return self._json(d if d else {"error": "unknown agent"}, 200 if d else 404)
                if url.path == "/api/session":
                    return self._json(build_session(nonce))
                if url.path == "/api/launches":
                    return self._json({"launches": live_runs.launches(root)})
                if url.path == "/api/health":
                    h = build_health(root)
                    return self._json(h, 200 if h["ready"] else 503)
                if url.path == "/api/log":
                    lg = build_log(root, (q.get("run_id") or [""])[0][:64])
                    return self._json(lg if lg else {"error": "unknown run"}, 200 if lg else 404)
                if url.path == "/api/runmeta":
                    return self._json(build_runmeta(root))
                if url.path == "/api/doc":
                    doc = read_doc(root, (q.get("key") or [""])[0])
                    return self._json(doc if doc else {"error": "unknown doc"}, 200 if doc else 404)
                if url.path.startswith("/figure/"):
                    fn = url.path[len("/figure/"):]
                    path = os.path.realpath(_abs(root, f"data/{fn}"))
                    if (FIGURE_RE.match(fn) and os.path.dirname(path) == data_dir and os.path.isfile(path)):
                        with open(path, "rb") as fh:
                            return self._send(200, fh.read(), "image/png")
                    return self._json({"error": "not found"}, 404)
                return self._json({"error": "not found"}, 404)
            except Exception as exc:  # never crash the server on a bad artefact
                # Details go to the local console only; the browser gets the class name.
                print(f"[evirep-ui] {self.path[:200]!r}: {type(exc).__name__}: {exc}", file=sys.stderr)
                return self._json({"error": f"internal error ({type(exc).__name__}); see the server console"}, 500)

        def do_HEAD(self):
            self._json({"error": "read-only: GET only"}, 405)

        do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_TRACE = do_CONNECT = do_HEAD

        def do_POST(self):
            """Only POST /api/run exists. Same-origin + per-server nonce + JSON body; the stage policy and the
            runner's lock decide the rest. Every other POST is 405, as before."""
            if urlparse(self.path).path != "/api/run":
                return self.do_HEAD()
            if not _host_is_loopback(self.headers.get("Host")):
                return self._json({"error": "host not allowed"}, 403)
            port = self.server.server_address[1]
            if self.headers.get("Origin") not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                return self._json({"error": "cross-origin or missing Origin: refused"}, 403)
            if not secrets.compare_digest(self.headers.get("X-EviRep-Nonce") or "", nonce):
                return self._json({"error": "missing or stale session nonce: reload the page"}, 403)
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                return self._json({"error": "Content-Type must be application/json"}, 415)
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                length = -1
            if not 0 < length <= MAX_RUN_BODY:
                return self._json({"error": f"body must be 1-{MAX_RUN_BODY} bytes"}, 413)
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                rec = live_runs.launch(root, STAGES, _runs.status(root, STAGES), body)
            except ValueError:
                return self._json({"error": "body is not valid JSON"}, 400)
            except live_runs.LaunchError as exc:
                return self._json({"error": str(exc)}, exc.code)
            except Exception as exc:  # never crash the server; details stay in the local console
                print(f"[evirep-ui] launch failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                return self._json({"error": f"launch failed ({type(exc).__name__}); see the server console"}, 500)
            print(f"[evirep-ui] launch {rec['launch_id']}: {rec['command']}", file=sys.stderr)
            return self._json(rec, 202)

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description="EviRep read-only dashboard")
    parser.add_argument("--host", default="127.0.0.1",
                        help="loopback address to bind (127.0.0.1 or localhost); anything else is refused")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--root", default=DEFAULT_ROOT, help="repository root (default: parent of ui/)")
    args = parser.parse_args(argv)
    if args.host not in BIND_HOSTS:
        parser.error(f"refusing to bind {args.host!r}: the dashboard has no authentication and is "
                     "loopback-only (use 127.0.0.1 or localhost)")
    server = ThreadingHTTPServer((args.host, args.port), make_handler(os.path.abspath(args.root)))
    print(f"EviRep UI (read-only views; run controls for allow-listed stages) serving {os.path.abspath(args.root)} at http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
