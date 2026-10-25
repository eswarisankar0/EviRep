# Change log (2026-10-21 session)

**Nothing was staged, committed, pushed or deployed. No approved data, label, score or report changed.**

| File | Change | Why | Test |
|---|---|---|---|
| `scripts/compare_result_sets.py` (new) | compares a candidate result set with the approved one on the identical cohort and labels: AUROC, AUPRC, CIs (the report's ordinary bootstrap, seed 42, 2,000), paired differences and rank changes. Refuses different compounds or labels; atomic, fingerprinted output | the brief requires the original and corrected TD-042 results as separate, comparable result sets | `tests/test_alternative_result_sets.py` (6) |
| `data/_candidates/td042_v1/comparison.json` (new; git-ignored `data/`) | output of the above for `td042_v1` | consumed read-only by the UI | same |
| `ui/server.py` | `GET /api/alternatives` (unapproved result sets; stale comparisons withheld); `GET /api/result_set` (data contract of the approved set: run, cohort, cutoff, scoring version, 24 file fingerprints, unfingerprinted inputs); `pending_candidates[].compared`; `server_code_changed` in `/api/status` | alternative display, centralised provenance, restart detection | `test_alternative_result_sets`, `test_server_code_change` (3) |
| `ui/app.js` | Validation §7 "Alternative scoring variant (not approved)": banner, AUROC intervals, paired differences, rank changes; summary line about TD-042. Data-contract panel (Validation §5 and Overview › Technical details). Dependency graph uses short state names in wider boxes; state bar-chart label margin widened. Header refresh time in UTC. Restart banner when the server's code changed | brief §4.2, §10, §8.6; overflowing labels seen in screenshots; timezone consistency; stale-server incident | drive16 (+3 checks), drive17 |
| `tests/test_ui.py` | `pending_candidates` expectation includes `compared` | new field | — |
| `tests/test_vps_independent_agreement.py` (new) | the production `build_standardized_scores` vs an independent implementation, tolerance 1e-12; edge cases (ties, neutral 0.5, single compound, infinity, determinism, uniqueness) | brief §4.5: agreement with the production scoring function, not only the saved file | 9 |
| `tests/test_server_code_change.py` (new) | code-change detection | stale-server incident | 3 |
| `scripts/05_safety_signal.py`, `scripts/08_molecular_pathway.py` | **restored** to their pre-audit bytes (atomic-write edit from 2026-10-20 removed; saved in `records/deferred_atomic_write_05_08.patch`) | the edit changed the code fingerprints of two protected, network-dependent stages, so the dashboard asked the owner to re-run them for a change that does not alter their output | dashboard next actions now list only the genuine `eval` item |
| live server on 127.0.0.1:8765 | restarted twice (this session's own process) | it was serving the new page with old API code (404 on the new endpoints; found by drive7) | drive7 21/21 after restart |
