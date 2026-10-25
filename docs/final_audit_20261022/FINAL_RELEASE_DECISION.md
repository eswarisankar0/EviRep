# Final release decision (final audit 2026-10-22)

## Verdicts

| Area | Verdict | Basis |
|---|---|---|
| **Scientific integrity** | **CONDITIONAL** | The approved 0.775 reproduces, but it is an **upper estimate**. With every justified correction it is 0.667 [0.506, 0.815]. The corrections are verified but not yet adopted, and two items stay unresolved (UR-1, N-07). Reporting 0.775 *without* this context would fail. |
| **Local demo** | **GO** | The primary tree and its live server are untouched today (the demo was rehearsed 22/22 this morning). The proposed code passes 771 tests and 138/138 browser scenarios. |
| **Git commit readiness** | **READY** | Verified patch plus an explicit-path commit plan (`COMMIT_READINESS_REPORT.md`); 0 secrets; generated artefacts excluded. Needs owner authorisation, after the presentation. |
| **Production deployment** | **NO-GO** | No authentication, TLS, multi-user isolation or audit log; no deployment infrastructure is available to verify any of them (`SECURITY_AUDIT.md`). |

## Primary scientific result: recommendation
- **Recommended primary:** "all corrections" on the rebuilt cohort.
  - **5D AUROC 0.667 [0.506, 0.815]; AUPRC 0.409** (prevalence 0.182); n = 77, 14 positives.
  - Equal weights.
  - Molecular adds nothing (5D − 4D = −0.026 [−0.081, 0.027]).
- **Historical / sensitivity result:** the approved 0.775 [0.656, 0.881] (undated inputs, published molecular rule, original cohort).
- **Selection basis:** validity criteria fixed in advance (`TEMPORAL_LEAKAGE_AUDIT.md` §4), not the metric.

**Statements that remain true either way:**
- Validation is internal and retrospective; there is no external validation set.
- The label means a later registered PD trial, not efficacy.
- AUROC is a ranking statistic, not a probability that a drug works.

## Adoption package (owner authorisation required, because each step rewrites protected artefacts)
1. **Apply the code patch** (commit plan steps 1–3).
2. **Cohort (E-056 + class-phrase fix):** `run_stage.py 03` then `03c` on the primary root (live API, about 25 min); then 04 / 05 / 08 / 04p / 05h (checkpointed; only Dopamine is new).
3. **Feature links (P1):** copy `candidate_feature_role_exclusions.csv` to `data/feature_role_exclusions.csv` (32 links).
4. **TD-042:** run stage 08 with `--exclude-drug-targets-from-pathways`.
5. **Dating:** a design decision. The dated literature, safety and molecular inputs exist only as audit substitutions (`experiments/build_candidates.py`). Promoting them to registered stages is engineering work **not done here**. Alternatively, adopt the undated corrections and report the dated value as the leakage-bounded estimate.
6. **Re-run 06 and eval** (both are now staged, verified and time-limited); compare with `scripts/compare_result_sets.py`; record the decision in DECISIONS.md.
7. **Provenance after the presentation:**
   - `./venv/bin/python scripts/run_stage.py eval` (byte-identical; closes the fingerprint gap);
   - `--attest-from ~/EviRep_attest_20261022T1504Z 00`.
8. **Dependencies:** `pip install 'certifi>=2026.10.19'`; test `pillow>=13`; re-run the tests and stage 07.

**Rollback:** `~/EviRep_recovery_finalmission_20261022T1504Z/` (sha256-verified), plus `data/_candidates/` and the runner's `previous/` backups.

## Still unresolved or blocked
- **UR-1:** pre-cutoff trial phase as of 2021 (registry history not retrieved).
- **N-07:** withdrawn-trial label policy (no current effect).
- **Production controls:** blocked on infrastructure.
- **Undocumented constants:** ×5 boxed weight, 0.6/0.4 molecular weights. Documented and shown insensitive; no external justification exists in the repository, and none is claimed.
- **Direct-only molecular** (0.759): requires a pre-specified, independent evaluation before it can be considered.
