# Remaining risks and blockers (2026-10-20)

## Security (local-only application)
| Item | Status |
|---|---|
| Authentication, HTTPS, multi-user isolation | **not implemented**; loopback-only bind, Host check, same-origin + nonce on the single POST route |
| Dependency vulnerability scan | **BLOCKED**: `pip-audit` not installed; needs owner approval to add it to the venv |
| Credentials | NCBI and Semantic Scholar keys absent; stage 04 cannot run live (HTTP 429) |

## Runtime
| Item | Status / mitigation |
|---|---|
| diag timeout (3600 s) | estimate only; diag has never run under the tracker |
| Long live stages (01, 03, 03c, 04, 05, 08, 04b) | no timeout, by design (hours); refused from the dashboard; run from the CLI by the owner |
| Runner SIGKILL / power loss | interrupted run reported, orphan named; recovery via `run_stage.py --restore` (md5-verified, manual) |
| No cancel button | by design; the timeout bounds runtime |
| Launch records from a previous server process | "UNKNOWN (started before this server)"; the run manifest stays authoritative |
| NOT TESTED | disk-full conditions; browsers other than Chrome; screen-reader and contrast tools; browser/server clock skew in "x min ago" |

## Scientific (owner-only; untouched)
- **B-003:** a from-source rerun gives AUROC 0.7763 against the approved 0.7754 (stage-02 Monte Carlo redraw). The approved scores reproduce exactly from persisted inputs. Re-publishing 02/06/eval is an owner decision.
- **Temporal validity:** the molecular dimension is not cutoff-bounded (TD-042 / TD-033); 5D 0.775 against 0.704 with dated inputs.
- **eval:** has an untracked input fingerprint (`data/reproducibility.json`); clearing it means re-running eval, which rewrites a protected file, so it needs approval.
- **Documents:** `docs/CASE_STUDIES.md` contains superseded metrics (TD-048).
- **Human review:** 28 clinical links await adjudication by a reviewer.
