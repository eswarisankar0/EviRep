# Overnight execution report (2026-10-21)

**Overall status: research-grade improvements verified; production readiness still pending.**
Open scientific owner decisions (TD-042, cohort rebuild, temporal validity) and a loopback-only, unauthenticated design both prevent a production-ready claim. See `REMAINING_BLOCKERS.md`.

## What was inspected
- **Repository state:** `main` at HEAD `576bc7f`, remote `github.com/eswarisankar0/EviRep`. The 25 staged and 21 unstaged changes plus about 425 untracked files from earlier work were preserved; there were no stashes.
- **Recovery snapshot:** `~/EviRep_recovery_7h_20261020T1929Z`.
- **Documents:** the canonical documents (README, decision, issue and change logs, `TECHNICAL_DEBT.md`, `INTERVENTION_MATCHING.md`, VPS contract, evaluation and weighting documents, `CASE_STUDIES.md`) and both previous audits. Not present: `SECUREDOC_CURRENT_STATE_REPORT.md` and `TOP_20_ACTIONS_TO_REACH_ENTERPRISE_GRADE.md`.
- **Scoring code, the TD-042 candidate, saved weighting results, and all eight agents' live state.**
- **UI:** every route and control, the server's security surface, and the protected artefacts.

## What changed
See `CHANGELOG.md`. In short:
- a candidate-comparison tool and a read-only "alternative result set" view (TD-042, clearly **not approved**);
- a centralised data contract for the approved result set;
- a production-vs-independent scoring test (1e-12);
- server code-change detection;
- dependency-graph readability and UTC times;
- reverting a previous change that falsely made protected stages look out of date.

**No approved data, label, cohort member, score or report changed.**

## Commands actually executed (main ones)

| Command | Result |
|---|---|
| `./venv/bin/python -W default -m unittest discover -s tests` (baseline) | 723 OK, exit 0, 0 warnings |
| same (final) | **741 OK, 0 failed, 0 skipped, 0 warnings, exit 0** (`logs/tests_after.log`) |
| `./venv/bin/python scripts/run_stage.py --check-manifest` | exit 0 |
| `./venv/bin/python scripts/vps_verify.py` | MATCH, 90 compounds, max abs diff 2.22e-16 |
| `shasum -a 256 -c logs/hashes_before.txt` | 19/19 protected artefacts unchanged |
| `git diff --check`; `node --check ui/app.js` | clean / OK |
| `scripts/compare_result_sets.py --candidate data/_candidates/td042_v1/root/data/vps_scores_v2.csv ...` | approved 0.7754, candidate 0.6992, 4D 0.7002 |
| `scripts/td042_comparison.py` (independent) | identical numbers |
| `../scientific_release_audit/scripts/independent_math.py`, `data_integrity.py` (re-run) | ranks diff 0; 0 HIGH findings |
| browser suites drive7–drive16 + drive13 (final code) | **159/159** |
| drive17 interaction audit | 2,118 controls, 0 dead; 1,378 internal links, 0 failing |
| external-link check (15 read-only requests) | 15/15 resolve |
| active security probes (curl) | every traversal, foreign-Host, cross-origin, no-nonce, PUT and DELETE request refused |

## Runtime and environment limitations
- **Not run:** protected online stages (01, 03, 03c, 04, 05, 08), full online runs of 04p/05h, production-length timeouts, screen readers, browsers other than Chrome.
- **Online calls this session:** only 15 read-only identifier lookups. The registry re-ascertainment is from the previous pass.
- **Wall-clock:** the work ran to completion within the session; the seven-hour budget was not the limiting factor.

## Remaining work
See `REMAINING_BLOCKERS.md`: TD-042 decision, cohort rebuild, temporal validity, Lithium, Galantamine/Rifaximin, the 28 review links, the eval re-run, molecular module selection, the deferred 05/08 atomic writes and core-stage timeouts.

## Resume
1. `./venv/bin/python ui/server.py`, then open http://127.0.0.1:8765/ (already running on the final code). Validation §7 shows the TD-042 comparison.
2. Owner: decide TD-042. If it is adopted, run `data/_candidates/td042_v1/publish_td042.sh` (rehearsed), then `scripts/run_stage.py eval`.
3. Owner: approve a stage-03 rebuild in an isolated copy (pagination fix), compare with `scripts/compare_result_sets.py`, then decide.
4. Owner: approve `./venv/bin/python scripts/run_stage.py eval` to fingerprint `data/reproducibility.json` (byte-identical output).
