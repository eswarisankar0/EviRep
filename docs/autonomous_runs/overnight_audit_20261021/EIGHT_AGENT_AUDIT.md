# Eight-agent audit (2026-10-21)

**Sources**
- The full contract trace (file:line), the 34-run fault matrix and the online checks are in `../biomedical_ux_agent_audit/AGENT_CONTRACT_AUDIT.md` and `ONLINE_INTEGRATION_RESULTS.md`.
- The defect fixes A-1 to A-7 are in `../scientific_release_audit/FIX_LOG.md`.
- This file records the current, re-checked state.

**Live backend state, read with `ui/server.py` `build_live`** (the same function the dashboard uses):

| ID | Name (registered) | Implementation | Kind | Last attempt | Output envelope | Stale inputs | Affects VPS? |
|---|---|---|---|---|---|---|---|
| 10a | Literature Credibility | `scripts/literature_credibility_agent.py` (stages 10a, 10a-all) | diagnostic | SUCCESS 2026-10-20 17:45 | valid, SUCCESS | 0 | no |
| 10b | Molecular Plausibility | `scripts/molecular_agent.py` + stage 08; run record `scripts/molecular_run_record.py` | VPS input via stage 08 | SUCCESS 17:45 | valid, SUCCESS | 0 | **yes**, through `molecular_pathway.csv` (dimension 5); the 10b record itself is not read by stage 06 |
| 10c | Clinical Evidence | `scripts/clinical_evidence_agent.py` | VPS input via stage 03c | SUCCESS 08:01 | valid, SUCCESS | 0 | clinical maturity comes from stage 03/03c, not from the 10c output |
| 10d | Conflict & Context | `scripts/conflict_context_agent.py` | diagnostic | SUCCESS 18:44 (dashboard launch) | valid, SUCCESS | 0 | no |
| 10e | Reproducibility | `scripts/reproducibility_agent.py` | diagnostic | SUCCESS 08:01 | valid, SUCCESS | 0 | no (read by the eval report) |
| 10f | Safety Evidence | `scripts/safety_evidence_agent.py` | VPS input via stage 05 | SUCCESS 17:45 | valid, SUCCESS | 0 | safety comes from stage 05, not from the 10f output |
| 10g | Evidence Independence | `scripts/evidence_independence_agent.py` | VPS input via stage 04 | SUCCESS 17:45 | valid, SUCCESS | 0 | literature comes from stage 04, not from the 10g output |
| 10h | Completeness & Gap | `scripts/completeness_gap_agent.py` | annotation | SUCCESS 18:44 (dashboard launch) | valid, SUCCESS | 0 | no |

**Observed activity:** the 18:44 UTC runs of 10d and 10h came from two dashboard launches on the live server: "Run 10d" and "Run all 11 permitted stages", records `data/_runs/_ui_launches/20261020T1844*`, exit 0. They were made after the previous session ended. None of my automation targets that server, so they are recorded as **user-initiated**.

## Verified properties
- **All eight are real implementations with tests.** 10a 28, 10b 69 + 16, 10c 19, 10d 25, 10e 21, 10f 21, 10g 11, 10h 20, integration 7 (counts from the previous pass). Plus the fault-mode tests (`tests/test_agent_failure_modes.py`, 7), which use the real runner and agents and no mocks. All pass in this session's suite.
- **Diagnostic agents cannot reach VPS.** Stage 06 reads only stage files from 02, 03c, 04, 05 and 08 (traced). The sentinel tests check that feature producers read no label files.
- **No stale output passes as fresh.**
  - On a FAILED attempt the runner restores the previous output byte-identical and marks the stage failed; the dashboard shows "Last run failed; previous results retained".
  - An upstream failure BLOCKS dependants; a FAILED upstream envelope makes 10h mark those domains NOT_COMPUTED.
  - Inputs absent at run time are now recorded, so their later appearance is detected.
- **Molecular chain:** drug → ChEMBL target → Ensembl gene → Reactome pathway → PD module, read from the saved evidence JSONL. The Open Targets live data version (26.09) equals the recorded version, and ACHE is confirmed as Donepezil's target (previous pass). A successful API call does not prove biological correctness. The chain is shown as mechanistic plausibility, never as efficacy.
- **Double counting across dimensions:**
  - TD-042: the molecular pathway credit counts the drug's own target, which the direct component already credits (see `SCIENTIFIC_AND_VPS_AUDIT.md`);
  - 17 shared pre-cutoff trials are credited to 31 compounds (TD-038);
  - the same study can appear as both a trial and a paper (10g D2: 20 compounds).
  - All three are reported, none corrected in the score (owner decisions).

## Gaps between the proposed architecture and the implementation
- No agent queries live sources in the mode the runner uses. Retrieval sits in upstream stages, or behind command-line flags the UI never passes (`10a --graph`, `10c --fetch`, `10f --fetch`; no retry or backoff on the last two).
- "VPS input" agents (10b/10c/10f/10g) annotate and diagnose. The score uses the upstream stage files directly, and the dashboard labels say "feeds the score through its stage".
- Core stages 00–06 have no runner timeout (08 now has one); this is open.
- The atomic-write fix for stages 05 and 08 was **reverted this session** and deferred to their next owner-approved re-run (`records/deferred_atomic_write_05_08.patch`). Changing their code made the dashboard tell the owner to re-run two protected, network-dependent stages for a change that does not alter their output.
- Semantic Scholar (stage 04) cannot be verified anonymously: HTTP 429, no key.
