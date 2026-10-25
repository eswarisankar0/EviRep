# Known failures, blockers and untested areas (2026-10-20)

## Open software failures
None reproducible after the fixes in this mission (D1–D7). This is not a claim that none exist: see "Not tested" below.

## Residual risks (documented, not defects)
| Risk | Behaviour today | Mitigation |
|---|---|---|
| A stage runs legitimately for longer than its timeout | killed and FAILED (TIMEOUT); previous outputs restored | raise `timeout_s` for that stage in the registry (900 s offline, 3600 s confirm stages) |
| The runner is SIGKILLed or the machine loses power mid-stage | shown as an interrupted attempt, never RUNNING forever; a live orphan is reported | stop the orphan, then `run_stage.py --restore <stage>` (md5-verified) |
| Launches started by an earlier server process | launch panel state "UNKNOWN (started before this server)" | the run table (manifest) is authoritative and shows the outcome |
| No cancellation control | by design: stopping mid-stage would skip the restore step | the timeout bounds runtime |
| Elapsed time and latest log line, no percentage | no stage reports reliable progress | — |

## BLOCKED (cannot verify without owner, credentials or tooling)
- Live network stages (01, 03, 03c, 04, 05, 04b, diag) under the new timeout path: refused from the dashboard by policy; full live runs not performed.
- Dependency vulnerability scan: `pip-audit` not installed; installation needs owner approval.
- Authentication, HTTPS, multi-user isolation: not implemented. The application is loopback-only by design.

## NOT TESTED
- A hung process observed in the browser at the moment its 900 s timeout fires. The same code path is covered by a real-process unit test with a 1 s timeout.
- Disk-full conditions during stage execution.
- Screen-reader and contrast-ratio tooling.
- Browsers other than Chrome (CDP).
- Clock skew between the browser and the server. "x min ago" uses the browser clock against server timestamps.

## Owner-only decisions (unchanged; not touched by this mission)
- Molecular dimension policy (TD-042 / TD-033).
- Adopting the bounded literature/safety dimensions.
- Label re-freeze, and re-publishing 02/06/eval (B-003).
- `docs/CASE_STUDIES.md` superseded metrics (TD-048).
- The 28 clinical-link adjudications (human reviewer).
