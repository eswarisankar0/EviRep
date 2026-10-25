# Data provenance and freshness (audit 2026-10-21)

## Guarantee checked: the UI never presents stale or unverifiable data as current

| Mechanism | Evidence (executed) | Result |
|---|---|---|
| Manifest integrity | `scripts/run_stage.py --check-manifest`: ok, 0 problems, 25 stages recorded, 49 history entries, 0 registry stages never recorded | PASS |
| Input/output fingerprints per success; freshness propagates along the DAG | `tests/test_stage_registry_integrity.py` (reads ⊆ ancestors' outputs; one producer per output); `tests/test_run_tracking.py` | PASS |
| An unfingerprinted input blocks the "current" state | `TestUnfingerprintedInputIsNotCurrent`; live: `eval` / `data/reproducibility.json` keeps the overall state at `VERIFIED_WITH_GAPS` | PASS (gap displayed, not hidden) |
| A failed latest attempt is visible even though the last success remains | `test_each_agent_fails_closed_on_a_malformed_input`; drive9 / drive16 live run views | PASS |
| A failed dependency is visible on its dependants | new warning and test (A-5) | PASS |
| A server running stale code is detected | live: before the restart, `server_code_changed: true` (the 2026-10-21 edits to `run_stage.py` / `app.js` came after the server started); after the restart, `false`. Test: `tests/test_server_code_change.py` | PASS (detected, then remediated) |
| Times are UTC and labelled | manifest and API fields use `*_utc` ISO-8601 with `+00:00` (observed in `/api/live`); the UI formats every displayed time with a "UTC" suffix (`ui/app.js:371, 1012, 1144, 1314`, static inspection; no browser assertion) | PASS (static) |
| No caching of live data | `Cache-Control: no-store` on every response (`logs/security_probes.txt`) | PASS |

## Live freshness snapshot (final code, :8765)
- **Last success** in the manifest: `2026-10-20T18:44:42+00:00` (stage 10h).
- **Inputs changed** since the last success: 0. **Untracked outputs:** 0.
- **Untracked inputs:** 1. The `eval` stage reads `data/reproducibility.json`, which was not fingerprinted at its last success. Re-running `eval` rewrites a protected report, so it needs the **owner**.
- **Code unverifiable (8 stages):** 01, 02, 03, 03c, 06, 04b, diag, eval. These are the adopted 2026-10-15 stages, whose code was not fingerprinted at adoption. They are shown as such, not as current or stale.
- **Agent stages:** the latest attempt of every agent stage succeeded, and every agent output envelope is valid with 0 stale inputs (`EIGHT_AGENT_INTEGRATION.md`).

## Approved artefacts
- **Hashes:** the 19 protected files match the baseline before and after (`logs/protected_sha256_baseline.txt`; `shasum -c` gives 19 OK).
- **Score:** `data/vps_scores_v2.csv` was independently reproduced (`VPS_AND_SCIENTIFIC_VALIDATION.md`).
- **Approved run:** `adopted-20261015T015501Z-06`. The TD-042 candidate lives only under `data/_candidates/td042_v1/` and is labelled "not approved" in the UI.

## External data
Not refreshed in this audit (mission rule 6). No ClinicalTrials.gov, PubMed, DailyMed or OpenTargets requests were made. Browser and integration tests ran against isolated copies built with rsync (`scratchpad/uxcopy`, `livecopy`, `gatecopy4`) on port 8799. `run_suites.sh` builds each copy fresh, so no test could write to the protected paths of the real repository.
