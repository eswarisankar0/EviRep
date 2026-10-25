# Eight-agent integration (audit 2026-10-21)

**Source:** `/api/live` from the restarted live server on :8765, read at about 02:57Z on 2026-10-21.
The server runs the final code (`server_code_changed: false`). The overall state is `VERIFIED_WITH_GAPS`: 12 stages ADOPTED and 13 SUCCESS; 0 running, 0 failed, 0 stale, 0 unknown.

| Agent | Name | Role | Tracked status | Output envelope | Valid | Stale inputs | Coverage (from the output) | Launchable from the UI |
|---|---|---|---|---|---|---|---|---|
| 10a | Literature Credibility | diagnostic (not in the VPS) | SUCCESS | SUCCESS | yes | 0 | 89/90 compounds assessed · 4,191 papers rated | 10a, 10a-all |
| 10b | Molecular Plausibility | VPS input (stage 08) | ADOPTED | SUCCESS | yes | 0 | 74/90 compounds with targets · 16 unmeasured | 10b (offline re-validation only) |
| 10c | Clinical Evidence | VPS input (stage 03) | ADOPTED | SUCCESS | yes | 0 | 90 compounds · 177 trials · 0 retrieval failures | 10c, review |
| 10d | Conflict & Context | diagnostic | SUCCESS | SUCCESS | yes | 0 | 19/91 assessed · 72 insufficient evidence | 10d |
| 10e | Reproducibility | diagnostic | SUCCESS | SUCCESS | yes | 0 | 14 findings · 40 publication records | 10e |
| 10f | Safety Evidence | VPS input (stage 05) | ADOPTED | SUCCESS | yes | 0 | labels 83/90 · at cutoff 31 scored, 52 unknown | 10f |
| 10g | Evidence Independence | VPS input (stage 04) | ADOPTED | SUCCESS | yes | 0 | same study in two dimensions: 20 found, 1 not assessable | 10g |
| 10h | Completeness & Gap | annotation | SUCCESS | SUCCESS | yes | 0 | 90 compounds × 12 domains · 361 gaps | 10h |

## Integration guarantees, each checked by an executed test

| Guarantee | Test | Result |
|---|---|---|
| The score (stage 06) reads no agent output | `tests/test_stage_registry_integrity.py::test_the_score_reads_no_agent_output` | PASS |
| Each agent fails closed on a malformed input: FAILED recorded, output restored byte-identical, last success unchanged, dashboard shows FAILED | `tests/test_agent_failure_modes.py::test_each_agent_fails_closed_on_a_malformed_input` (9 cases) | PASS |
| A dependency's failed latest attempt is flagged on its dependants (**new in this audit**) | `test_a_failed_dependency_is_flagged_on_its_dependants` | PASS |
| An upstream failure in a sequence BLOCKS its dependants | `test_upstream_failure_blocks_dependants_in_a_sequence` | PASS |
| An unfingerprinted input is never reported as current | `TestUnfingerprintedInputIsNotCurrent` | PASS |
| Degraded inputs give PARTIAL or UPSTREAM_FAILED, never clean SUCCESS (10g, 10d, 10h) | `TestAgentDefectsFixed` | PASS |
| A stage reads only outputs of its ancestors, so freshness propagates | `test_a_stage_only_reads_outputs_of_its_ancestors` | PASS |
| Each output has exactly one producer | `test_each_output_has_one_producer` | PASS |

All of these tests are in the final suite: 751 OK (`logs/tests_final.log`).

## Defect found and fixed in this audit
**A-5 (P2).**
- **Problem:** a single-stage re-run of 10e or 10h after 10d had failed proceeded silently on 10d's restored, last-validated output. Using that output is legitimate, but nothing said so.
- **Fix:** `scripts/run_stage.py` `status()` now adds the warning "dependency's latest attempt failed; its last validated output is the one in use: 10d". The Run Center stage table shows each stage's warnings under its state (`ui/app.js`).
- **Verification:** the regression test above confirms the warning appears, and that it disappears after a successful re-run.

## Not executed
Agents whose source stages are online (03, 04, 05, 08) were not re-run against live APIs. Their recorded outputs were validated through envelopes and fingerprints instead (mission rule: no expensive external requests).
