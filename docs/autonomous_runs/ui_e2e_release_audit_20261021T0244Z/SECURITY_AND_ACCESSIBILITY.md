# Security and accessibility (audit 2026-10-21)

## Security: active probes (executed)
Source: `logs/security_probes.txt`.
Probes ran at 2026-10-21T03:00Z against the live server on :8765. Every POST used a non-existent stage ID, so no probe could launch anything.

| Probe | HTTP | Expected | Status |
|---|---|---|---|
| `GET /` and `GET /api/status` (baseline) | 200 | served | PASS |
| Path traversal: `/../server.py`, `/%2e%2e/ui/server.py`, `/static/..%2f..%2f.env` | 404 | refused | PASS |
| `/.env`, `/.git/config` | 404 | refused | PASS |
| `/api/doc?path=../../.env`, `/api/log?run=../../.env` | 404 | refused | PASS |
| Foreign `Host: evil.example` | 403 | refused | PASS |
| DNS-rebinding `Host: 127.0.0.1.nip.io:8765` | 403 | refused | PASS |
| `POST /api/run` without nonce or Origin; cross-origin; same-origin with a wrong nonce | 403 ×3 | refused at the origin/nonce layer (403, not the 400 an unknown stage would give) | PASS |
| `PUT` / `DELETE /api/run` | 405 | refused | PASS |

**Response headers:**
- `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'`
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: no-referrer`
- `Cache-Control: no-store`

**Binding:** the live server listens only on `127.0.0.1:8765` (lsof).

### Launch policy
These checks are executed in `tests/test_stage_registry_integrity.py`:
- the launch command always comes from the registry, never from the request;
- shell injection (`10a; rm -rf /`) or a path as the stage → 400;
- protected writer `06` → 403;
- network stage `05h` without confirmation → 428;
- an unknown request field → 400;
- every stage that writes a protected artefact is REFUSED, and every launchable stage has a timeout.

### Credentials (`logs/credential_scan.txt`; counts only, no values printed)
- 0 pattern matches in the staged diff, in tracked files, in the working tree outside `venv`/`data`, and across the full git history.
- `.env` is git-ignored and untracked; `.env.example` has 0 non-empty assignments.
- `ui/server.py` and `ui/live_runs.py` contain 0 `os.environ` reads (TD-029).
- The staged-tree test run printed only placeholder-key warnings (truncated prefixes such as `YOUR...`, which are test fixtures).

### Not production-grade (by design; release blockers)
- No authentication or authorisation: anyone with local access to the machine can use the UI.
- No TLS.
- Single-user, loopback-only.
- No rate limiting or audit log of who launched a run, beyond the run manifest.

## Accessibility: executed in real Chrome (drive19, accessibility tree)
Source: `records/browser/results19.json`. The 16 routes were checked after the fix.

| Check | Result |
|---|---|
| Focusable controls without an accessible name (button, link, combobox, textbox, searchbox, checkbox, …) | **0** |
| Charts: SVG `role="img"` with an `aria-label` and a data-table alternative | see `TEST_RESULTS.md` (before the fix: 23 charts, 1 without a table → fixed) |
| Document language | `en` |
| `main` landmark, skip link | present |

**Fixed in this audit (A11Y-1, P2):** the Run Center chart "Stages by tracked state" opted out of its data table (`noTable: true`), so screen-reader users had no text alternative for it. The opt-out was removed (`ui/app.js`), and a static regression test was added: `tests/test_ui_quality.py::test_every_chart_keeps_its_data_table_alternative`.

**Not executed:** a real screen reader (VoiceOver or NVDA), browsers other than Chrome, a WCAG colour-contrast measurement.
