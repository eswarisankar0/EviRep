# Security audit (final audit 2026-10-22)

**Scope:** `ui/server.py`, `ui/live_runs.py`, `scripts/run_stage.py`, the stage scripts' network clients, dependencies and secrets.

**Evidence:** today's executed checks (`docs/presentation_20261022/logs/launch_policy_probes.txt`, `logs/dependency_osv_scan.txt`) and the 2026-10-21/22 probe logs.

## Threat model (as designed)
- **Single-user research dashboard,** bound to **127.0.0.1**.
- **Threats in scope:**
  - a malicious web page in the same browser (CSRF / DNS rebinding);
  - another local process sending crafted requests;
  - accidental rewriting of approved artefacts;
  - secret leakage into logs or reports;
  - command injection through run requests.
- **Out of scope by design:** multi-user access, remote access, authentication.

## Controls verified by execution

| Control | Test | Result |
|---|---|---|
| Loopback-only bind; `--host` refuses non-loopback | `lsof` on the live server; server argument check | 127.0.0.1:8765 only |
| Host-header check (DNS rebinding) | `Host: evil.example`, `Host: 127.0.0.1.nip.io` | 403 |
| CSRF: same-origin + per-process nonce on POST | no nonce / cross-origin / bad nonce | 403 ×3 |
| Launch policy with a **valid** nonce | protected 06 / 03 / eval, live-only 04b → 403; unconfirmed network 05h → 428; unknown, injected (`10a; rm -rf /`) or path stage → 400; extra field → 400; malformed JSON → 400; oversized → 413; wrong content type → 415 | 14/14 correct; **no run started** (manifest history and launch records unchanged) |
| Command construction | registry-only argv lists, no `shell=True` in the server, runner or launcher | verified (grep + `tests/test_stage_registry_integrity.py`) |
| Path traversal | `/../`, `%2e%2e`, `/.env`, `/.git/config`, `/api/doc?path=..`, `/api/log?run_id=../../.env`; realpath containment for logs and figures; doc key allow-list | all 404 |
| Malformed input robustness | 27 GET endpoints × 14 malformed parameter sets | 0 server errors, 0 tracebacks leaked |
| Response headers | CSP `default-src 'none'`, `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, `no-store` | present |
| Secrets | pattern scan of staged / worktree / history / reports; run logs scanned for `api_key=`; server never reads `os.environ` | 0 matches |
| Unsafe writes | atomic writes (agents, review stage, 03c filter); runner backup / restore; protected-artefact refusal | tested (`test_agent_failure_modes`, `test_final_audit_fixes`) |
| Concurrency | one dashboard run at a time (409); manifest under an `fcntl` lock | browser-tested (drive11/12) |
| Timeouts | every registered stage now has `timeout_s` (fixed today) | `test_final_audit_fixes.TestEveryStageHasATimeout` |
| SSRF | the server makes no outbound requests; stages call fixed hosts only (ClinicalTrials.gov, NCBI, Semantic Scholar, openFDA, DailyMed, Open Targets) | code review |

## Findings

| ID | Severity | Finding | Status |
|---|---|---|---|
| SEC-1 | HIGH (pipeline network clients only) | `certifi 2026.7.22` has critical advisories (GHSA-6q48-6c7w-9gw2, PYSEC-2026-4320); fixed in 2026.10.19 | **RECOMMENDED — ADOPTION PENDING**: `./venv/bin/pip install 'certifi>=2026.10.19'`, then re-run tests. Not applied, because the venv is shared with the live presentation server. |
| SEC-2 | MEDIUM in this use | `pillow 12.3.0` (via matplotlib) has 28 advisories; fixed in 13.0.0 (major version). EviRep only *writes* its own PNGs and never parses untrusted images. | **RECOMMENDED — ADOPTION PENDING**: upgrade, then re-run stage 07 and the tests (compatibility unverified) |
| SEC-3 | LOW | `ThreadingHTTPServer` spawns unbounded threads; a local process could exhaust them | **ACCEPTED LIMITATION** (loopback, single user) |
| SEC-4 | INFO | `scripts/test_openfda.py` made a network call on import | **RESOLVED — IMPLEMENTED AND VERIFIED** (guarded; TD-012) |

## Production: NO-GO
**Missing controls:**
- authentication and authorisation;
- TLS;
- multi-user isolation (one manifest and one launch slot are shared);
- an audit log of who launched what (the run manifest records what, not who);
- rate limiting;
- service management and backups;
- a dependency update process.

**Status: BLOCKED — EXTERNAL DEPENDENCY.**
- Deployment infrastructure (reverse proxy, identity provider, TLS certificates) does not exist in this environment.
- No proxy (Caddy/nginx) is installed, so a configuration cannot be tested here.
- Per the mission, no custom authentication or cryptography was written, and nothing was exposed beyond loopback.

**Recommended pattern (not implemented, not tested):** keep the app on loopback behind an established reverse proxy that terminates TLS and enforces SSO / OIDC authentication, add an authenticated-user field to launch records, and run one instance per user, or add per-user launch isolation before any multi-user use.
