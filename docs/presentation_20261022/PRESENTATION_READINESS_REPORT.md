# EviRep: presentation readiness report (2026-10-22, 02:17–02:36 UTC)

## 1. Verdict
**GO for today's local presentation.**
- All available checks passed on the current code.
- The full demo was rehearsed end to end in a real browser (22/22).
- No new defect was found. **No code, test, data or document in the project was changed today**; the only addition is this report folder. Verified by comparing the tree with this morning's snapshot (`logs/gates_final.log`).

Production deployment remains **NO-GO** (section 12).

## 2. Issues fixed
**None today.** No new defect was found; see section 13 for what was checked. The defects fixed in the previous release (E-061 agent badge, E-062 review count, E-063 10h denominator, atomic review writes) were re-verified as **VERIFIED, NO CHANGE REQUIRED**:
- their regression tests pass in the 756-test suite;
- the badge and count were confirmed again in the browser (rehearsal step 10).

## 3. Files changed
**None in the project.** New files: `docs/presentation_20261022/`, holding this report, `DEMO_RUNBOOK.md`, logs, browser records and screenshots.

## 4. Tests run (actual)

| Check | Result | Evidence |
|---|---|---|
| Full Python suite | **756 run, 756 passed, 0 failed, 0 skipped, 0 warnings, exit 0** | `logs/tests_baseline.log` |
| Browser suites (real Chrome, isolated copies) | **159/159** (drive7, 8, 9, 11, 12, 13, 14, 15, 16) | `records/browser/suites_pres.out` |
| Accessibility tree, 16 routes | 0 unnamed controls; 23/23 charts with label + data table | same |
| Demo rehearsal | **22/22** | `records/browser/drive22.out` |
| GET endpoint fuzz | 27 endpoints × 14 malformed inputs: **0 server errors, 0 tracebacks** | session log |
| Launch-policy probes with a valid nonce | 14/14 refused correctly: protected 403, unconfirmed network stage 428, malformed 400, oversized 413, wrong content type 415; no run started | `logs/launch_policy_probes.txt` |
| Log endpoint traversal (`run_id=../../.env` etc.) | 404 ×4; a valid run returns its log | session log |

The code changes from the previous release were already exercised by these runs: the suite ran on them, and the browser checks covered the badge and the review count.

## 5. Browser workflows tested
**FIXED AND VERIFIED (previous release) / VERIFIED (today):**
- overview;
- candidate list (90);
- search; sort (aria-sort changes); filter (14 positives); clear (90);
- Donepezil detail (0.773 + five ranks);
- evidence, mechanism, conflicts, trial-role review (28);
- validation (0.775 [0.656–0.881], 0.424, TD-042 "not approved");
- Run Center agent cards;
- protected stage 06 has no Run button;
- a real 10h run (SUCCESS, row updated without reload, log served);
- 0 console errors or failed requests;
- 1280 px with no horizontal scroll.

The suites also cover:
- failure → FAILED with the output restored;
- timeout;
- server restart mid-run;
- double click and two tabs → one run;
- corrupt manifest;
- frozen server;
- 390 px mobile layout.

## 6. Approved score verification
`scripts/vps_verify.py`: **MATCH**, 90 compounds, max |diff| 2.22e-16. Manifest check ok (12 ADOPTED + 13 SUCCESS).

## 7. Protected files
sha256 **19/19 identical** to the baseline (before and after). The git index is unchanged; nothing is staged, committed or pushed; 0 ahead / 0 behind.

## 8. Server
```
cd /Users/thrisha/Drup_Rep_PF/EviRep
pgrep -fl "ui/server.py" || ./venv/bin/python ui/server.py      # → http://127.0.0.1:8765/
```
- **Currently running:** PID 34750, `127.0.0.1:8765` only, on the current code (`server_code_changed: false`).
- **Do not start a second copy.**

## 9. Demo steps
See `DEMO_RUNBOOK.md`: a tested 3-minute script with clicks, expected values, talking points and a fallback for each step.

## 10. Recovery
- **Snapshot:** `~/EviRep_recovery_presentation_20261022T0217Z/`. It holds the worktree and data tarballs, git index, diffs and untracked list; `SHA256SUMS` was verified 5/5.
- **Previous snapshot:** `~/EviRep_recovery_final_20261021T1713Z/` (verified 5/5).

## 11. Scientific status
| Item | Label |
|---|---|
| Approved result 0.775 / 0.424 / prevalence 0.156; 90 = 14 + 76 | VERIFIED, NO CHANGE REQUIRED |
| Fully dated estimate 0.689 [0.548, 0.819] (not shown in the UI; quoted from the release report) | DOCUMENTED LIMITATION |
| Temporal leakage (literature, safety, molecular); label = trial activity, not efficacy; no external validation | DOCUMENTED LIMITATION (stated on the Overview and Validation pages) |
| TD-042: re-verified today. Candidate `all_pass`, 21 compounds change, candidate 0.6992 vs approved 0.7754; independent recompute of the candidate MATCH; kept separate | REQUIRES OWNER DECISION |
| E-056: pagination fixed in code (100/page, ≤ 50 pages, test in `test_scientific_audit.py`); read-only re-ascertainment shows Dopamine would join and Ioflupane gains a trial with no rank change | REQUIRES OWNER DECISION. A full isolated rebuild needs about 1,483 live registry queries and was **NOT VERIFIED** today (no live APIs on presentation day). |
| Lithium (B-004), Galantamine (D-011), 28 trial-role links, D-020 feature exclusions | REQUIRES OWNER DECISION |
| `phases[0]` parsing, undocumented constants (×5 boxed weight, N_RANDOM 100), `eval` fingerprint gap, missing `dimensions_imputed` column | DOCUMENTED LIMITATION |
| Equal weights retained (learned weights worse on held-out data in 20/20 repeats) | VERIFIED, NO CHANGE REQUIRED |

## 12. Remaining engineering and security risks
- **Production (NO-GO):** no authentication, TLS or multi-user support; only the run manifest serves as an audit log.
- **Verified for the local demo:**
  - loopback-only binding;
  - Host, Origin and nonce checks;
  - no `shell=True`;
  - realpath containment for logs and figures; documents served from a key allow-list;
  - no credentials in logs or reports.
- **Runner and agent limits:** stages 06 and eval have no timeout (CLI only; refused in the UI). Agents 10d, 10e and 10a-curated exit 0 on PARTIAL when run by hand; the runner still records PARTIAL.

## 13. Not verified
- A real screen reader; browsers other than Chrome; projector colour contrast.
- An isolated stage-03 rebuild (live APIs).
- Online stages 01, 03, 03c, 04, 05, 08, 04p, 05h against live services.
- Load testing.

A passing suite is evidence for the behaviour it covers, not proof that the system is free of defects.
