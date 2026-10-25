# Test evidence (final audit 2026-10-22)

Every row was executed in this audit, and its log is in `logs/` or the path shown. "Work copy" means `~/EviRep_work_20261022T1504Z`, which carries every proposed change. The primary tree was not modified.

## Python
| Run | Tests | Result | Log |
|---|---|---|---|
| Baseline, work copy before any change | 756 | OK, 0 failures, 0 skipped, 0 warnings | `logs/tests_baseline_workcopy.log` |
| Mid-audit, after the first fixes | 771 | **1 failure**: `test_stage03_failure_handling.test_filter_refuses_a_check_file_with_errors`. It ran the 03c filter via `runpy` without `__main__`, which the TD-012 guard intentionally makes a no-op. Fixed by invoking the filter exactly as `check_studytype.py` does (`run_name="__main__"`); the assertions are unchanged. | `logs/tests_after_fixes.log` |
| **Final, work copy** | **771** | **OK, 0 failures, 0 skipped, 0 warnings, exit 0** | `logs/tests_final.log` |
| New and updated regression tests | 13 in `tests/test_final_audit_fixes.py` + 3 in `test_intervention_matcher.py` + 1 invocation fix | pass | same |

The absent-molecular regression test was also run against the **old** verifier. It returns 0.5 there, so the test detects the defect (`records/old_vs_new_verifier_absent_molecular.txt`).

## Browser (real Chrome via CDP, isolated copies, work-copy code)
`records/` holds the suite outputs. drive7 targets the live primary server (unchanged code) and was **not** re-run on the work copy; it passed 21/21 on 2026-10-22 morning.

| Suite | Result |
|---|---|
| drive16 (biomedical UX, refusals, runs) | 47/47 |
| drive15 (routes, charts vs data, labels, 390 px) | 24/24 |
| drive11 (run lifecycle, restart mid-run, failure restore) | 16/16 |
| drive12 (double click, two tabs, runner killed, malformed manifest, log injection) | 10/10 |
| drive14 (frozen/slow server, next-step guidance) | 9/9 |
| drive8 | 8/8 |
| drive9 (live pipeline end to end) | 15/15 |
| drive13 (timeout lifecycle) | 9/9 |
| **Total** | **138/138** |
| drive19 accessibility tree, 16 routes | 0 unnamed controls; 23/23 charts with label + data table |

## Security (executed)
| Check | Result | Log |
|---|---|---|
| Probes against the work-copy server | traversal / `.env` / log traversal → 404; foreign Host, no nonce, cross-origin → 403; protected 06/03 → 403; unconfirmed 05h → 428; injection, malformed → 400; wrong content type → 415; no run started | `logs/security_probes_workcopy.txt` |
| Launch-policy probes with a valid nonce (primary, morning) | 14/14 correct | `docs/presentation_20261022/logs/launch_policy_probes.txt` |
| GET fuzz (27 endpoints × 14 inputs, primary) | 0 server errors, 0 tracebacks | presentation audit |
| Dependency advisories (OSV) | certifi and pillow affected (SEC-1/2) | `logs/dependency_osv_scan.txt` |

## Data integrity and scientific verification
| Check | Result |
|---|---|
| `vps_verify` on the approved scores (work copy, fixed verifier) | MATCH, 90 compounds, max \|diff\| 2.2e-16 |
| `vps_verify` on all 18 candidates | **18/18 MATCH** (after fixing two verifier defects, E-065) |
| Approved artefacts (19 protected files), work copy and primary | sha256 identical to the baseline |
| From-source reproduction 00 → 02 → 06 → eval (current code, isolated) | 00 byte-identical; 02 differs only in the Monte Carlo null (Spearman 0.991); 5D AUROC 0.776 vs 0.775 |
| `eval` re-run on approved inputs | **byte-identical** report; all 8 inputs fingerprinted |
| TD-042 re-derivation (stage 08, isolated) | identical to the `td042_v1` candidate for 90/90 compounds |
| Live cohort rebuild (03 + 03c), twice | 0 API failures; pass 2 = approved + Dopamine + 1 Ioflupane trial |
| Filter refactor (TD-012) | output byte-identical to the original script and to the approved files |
| Patch | `git apply --check` OK; the patched primary copy equals the work copy (21 files) |

## Not verified
- A screen reader; browsers other than Chrome.
- Registry version history for the 65 trials updated after the cutoff (UR-1).
- A representative deployment environment: no proxy is available.
- Dependency upgrades: not applied, so untested.
- Peer-reviewed justification for the ×5 and 0.6/0.4 constants: none found; none claimed.
