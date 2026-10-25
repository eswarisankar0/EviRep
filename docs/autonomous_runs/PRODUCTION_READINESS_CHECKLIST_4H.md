# Production-readiness checklist, 4-hour sprint (2026-10-20)
This file supersedes the status column of [PRODUCTION_READINESS_CHECKLIST.md](PRODUCTION_READINESS_CHECKLIST.md) (kept unchanged). Only rows whose status changed or were re-verified are listed; every other row stands as recorded there.

| Area | Control | Before | Now | Evidence |
|---|---|---|---|---|
| Runner | Freshness covers every file a stage reads | PARTIAL (undeclared reads) | **PASS** | E-037. Static scan test over every stage script; write containment 10/10 agents (`evidence/agent_write_containment_4h.json`) |
| Runner | Corrupt manifest | PARTIAL (500 / traceback) | **PASS** | E-038. UNKNOWN never fresh; run refused, file kept; `--check-manifest`; fsync |
| Runner | Failed run can restore previous outputs | PARTIAL (> 50 MB skipped) | **PASS** | E-039. 512 MB limit; unrestorable runs refused (exit 4) |
| Runner | Code-drift detection | PARTIAL | PARTIAL | `code_fingerprint_recorded` shown; 12 ADOPTED stages + `eval` lack fingerprints (protected outputs; TD-046) |
| Runner | Concurrency (E-035) | PASS | PASS | tests re-run; write containment shows no cross-agent writes |
| UI | Status never claims "current" without known states | FAIL (latent) | **PASS** | E-040. Browser: corrupt manifest → "Run records unreadable" |
| UI | Single-flight polling | PARTIAL | **PASS** | E-041. Browser Fetch-hold: 1 request, 1 coalesced follow-up |
| Observability | Health / readiness | PARTIAL | **PASS** | `/api/health` 200 ready / 503 not ready; tests |
| Observability | Structured logs / monitoring | MISSING | MISSING | needs an owner decision on tooling (no SaaS added) |
| Recovery | Backups | PARTIAL | **PARTIAL+** | `scripts/backup_data.py`: atomic archive, sha256 manifest, member-level verify; one verified backup made. **Scheduling is not set up** (owner chooses cron/launchd) |
| Retention | Caches / run history | PARTIAL | PARTIAL | `--retention-report` (read-only) with a proposal; nothing deleted |
| Hygiene | Resource leaks | PARTIAL (126 warnings) | **PASS** | 0 ResourceWarnings in the full suite; 04p/05h Session accepted (TD-047) |
| Network | Timeouts / retries / failure recording | PASS | PASS (re-audited) | every outbound call has a timeout; per-request failures recorded |
| Supply chain | Dependency consistency | — | **PASS** | `pip check` clean; installed versions = pins (26 packages) |
| Supply chain | Vulnerability scan | NOT RUN | **BLOCKED** | `pip-audit` not installed. Needs approval: `./venv/bin/pip install pip-audit && ./venv/bin/pip-audit -r requirements.txt` |
| Security | Unsafe deserialization / shell | — | **PASS** | no pickle, yaml, eval, exec or `shell=True`; subprocess uses argument lists; expat 2.7.3 |
| Exposure | Authentication / HTTPS | MISSING | MISSING | deployment blocker; loopback-only bind kept |

**Verdict: DEVELOPMENT READY.**

The remaining mandatory controls for any shared deployment:
- authentication and HTTPS;
- monitoring and structured logging;
- scheduled backups;
- a vulnerability scan.

The scientific owner decisions are also still open.
