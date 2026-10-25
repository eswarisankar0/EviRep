# Production-readiness checklist (2026-10-20)

Status per control:
- **PASS** = evidenced in this audit.
- **PARTIAL** = it exists but has a gap.
- **MISSING** = it does not exist.
- **N/A** = not needed for the current local, read-only design.

Evidence paths are relative to the repository.

| Area | Control | Status | Evidence / gap |
|---|---|---|---|
| Exposure | Loopback-only bind | PASS | `--host` refuses anything except 127.0.0.1/localhost (`ui/server.py` main) |
| Exposure | Host-header check (DNS rebinding) | PASS | foreign Host → 403 (probe log) |
| Exposure | Read-only HTTP surface | PASS | POST/PUT/DELETE/… → 405; no route starts a stage or test |
| Exposure | Authentication / authorization | **MISSING** | none. Acceptable only on loopback; **a deployment blocker** for any shared host |
| Exposure | HTTPS | **MISSING** | plain HTTP; a deployment blocker beyond loopback |
| Browser | CSP, X-Frame-Options, nosniff, Referrer-Policy, no-store | PASS | response headers (probe) |
| Browser | CORS | PASS | no CORS headers, so cross-origin reads are blocked by default |
| Browser | CSRF | N/A | no state-changing routes |
| Input | Validation / traversal | PASS | `/api/doc` key allow-list; `/api/log` run-id regex + realpath confinement; `/figure/` regex + dirname check; traversal probes → 404; tests `TestRunLog`, `TestSecurityHardening` |
| Secrets | Not read or shown by the UI | PASS | TD-029 test forbids `os.environ` in the server; redaction of values in every payload; secret scan of tracked and untracked files found none; `.env` git-ignored and absent |
| Secrets | Credentials for full live runs | PARTIAL | `NCBI_API_KEY` optional; **no Semantic Scholar key** (HTTP 429), so stage 04 cannot complete live |
| Errors | No information disclosure | PASS | the browser gets the exception class only; absolute paths replaced by `<repo>`, home dirs by `/Users/<user>` |
| Rate limiting | Inbound | N/A (loopback, single user) | needed if deployed |
| Rate limiting | Outbound API politeness | PASS | bounded retries/backoff in 03, 04p, 05h, 08; 10-consecutive-failure breaker (E-033/E-034) |
| Runner | No duplicate or conflicting runs | PASS | E-035 atomic claim under the manifest lock; 6 tests + live check |
| Runner | Atomic, validated publication | PASS (06) / PARTIAL (others) | 06 staged + `vps_verify` + `os.replace`. Other stages write in place, then the runner validates; on failure the previous outputs are restored from `previous/` |
| Runner | Freshness and dependency propagation | PASS | fingerprints + dependencies; F-01 fixed (06 → agents); registry tests |
| Runner | Interrupted runs | PASS | dead PID → FAILED with the retained result named (test) |
| Runner | Corrupt manifest | PARTIAL | the agent panel shows UNKNOWN (test). `/api/status` and the CLI raise (HTTP 500 with the class name only). The manifest is written atomically, so corruption is unlikely, but there is no repair tool |
| Observability | Health endpoint | PARTIAL | `/api/status` serves as liveness/readiness (manifest-based); no dedicated `/healthz` |
| Observability | Structured logs / correlation IDs | **MISSING** | per-run `log.txt` + manifest history (run IDs act as correlation IDs for runs); server logs are print-to-stderr |
| Observability | Monitoring / alerting | **MISSING** | none |
| Recovery | Backups | PARTIAL | `data/` is git-ignored. Previous outputs kept per run (< 50 MB); manual recovery snapshots (`~/EviRep_recovery_*`); no scheduled backup |
| Recovery | Restore procedure | PARTIAL | documented here and in the reports; not rehearsed as a drill |
| Retention | Caches / run history | PARTIAL | `data/cache` 297 MB, `data/_runs` 12 MB (37 runs) with no retention policy; nothing deleted (by policy) |
| Reproducibility | Pinned dependencies | PASS | `requirements.txt` pins all 8 direct dependencies (Python 3.13.9). scipy is now also imported directly (sensitivity scripts) and is pinned |
| Reproducibility | Offline end-to-end run | PASS | `data/_runs/e2e_audit_20261020/` exit 0; 20 SUCCESS, 5 live-only stages blocked by design; `vps_verify` MATCH |
| Reproducibility | Independent score reproduction | PASS | `vps_verify` (live + TD-042 candidate) MATCH, max abs diff ≤ 2.2e-16 |
| Supply chain | Vulnerability scan | **NOT RUN** | `pip-audit` is not installed in the venv; not installed during the audit (no environment changes). Next action: `./venv/bin/pip install pip-audit && ./venv/bin/pip-audit -r requirements.txt` with owner approval |
| Config | Environment-specific configuration | PARTIAL | CLI flags (`--root`, `--port`); no deployment profiles |
| Lifecycle | Startup / shutdown | PASS (local) | stdlib server, no state; restart shown safe (the UI recovers through polling) |
| Accessibility | Semantics, keyboard, focus, text status | PASS (automated subset) | `lang`, `main`, `nav`, scoped `th`, labelled inputs, `img alt`, visible focus, status words not colour alone. No screen-reader or contrast audit tool was run |
| UI correctness | Live state, no JS errors, mobile | PASS | browser 20/20 (`docs/autonomous_runs/evidence/ui_browser_checks_e2e_audit.json`) |

**Verdict: DEVELOPMENT READY.** EviRep is usable locally by its owner, on loopback, as a read-only research dashboard with a tracked pipeline.

It is **not** pilot, staging or production ready. The engineering blockers are:
- authentication and HTTPS;
- monitoring and structured logging;
- backup and retention policies;
- a dependency vulnerability scan.

The scientific blockers are:
- an owner decision on the molecular dimension;
- adjudication of the 28 clinical links;
- a Semantic Scholar key for the live literature stage.
