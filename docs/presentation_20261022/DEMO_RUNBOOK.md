# EviRep demo runbook (tested 2026-10-22)

Every step below was rehearsed in real Chrome by `records/browser/drive22.py`: **22/22 checks passed** (`records/browser/drive22.out`). Screenshots are in `screenshots/`. Timings are for a 3-minute talk; the 10h run takes about 1 second.

## 0. Before the talk (5 minutes earlier)
1. **Start the server:**
   ```
   cd /Users/thrisha/Drup_Rep_PF/EviRep
   pgrep -fl "ui/server.py" || ./venv/bin/python ui/server.py      # reuse it if already running
   ```
   Open **http://127.0.0.1:8765/**. Browser zoom 100%, window ≥ 1280 px wide (tested: no horizontal scroll).
2. **Health check:** run `./venv/bin/python scripts/vps_verify.py`. It must print `MATCH; 90 compounds`.
3. **Stale-code check:** if a yellow "restart the server" banner appears, stop the server (Ctrl+C) and start it again.
4. **No internet needed.** The demo uses only saved files.

## 1. Script

| Time | Click | You should see | Say | If it's missing |
|---|---|---|---|---|
| 0:00 | **Overview** | 90 compounds, 14 positives, AUROC 0.775 | "We rank 90 drugs already tried in Parkinson's using only evidence from before 2021, then check which got a *new* trial from 2021 on. That's 14 positives and 76 negatives. The label means continued investigation, not that the drug works." | Reload the page; if still empty, run the health check (step 0.2) |
| 0:25 | **Candidates** | "90 of 90 shown"; Donepezil #1, 0.773 | "Each drug gets five percentile ranks, averaged with equal weights." Type `donep` in Search; set *New trial after 2020* = yes (**14 rows**: the positives); **Clear filters** (90). | – |
| 0:45 | **Donepezil** | rank 1 of 90; 0.773; ranks 0.41 / 0.88 / 1.00 / 0.64 / 0.93 | "Five dimensions: network proximity 0.41, clinical maturity 0.88, literature independence 1.00, safety 0.64, molecular 0.93. Mean = 0.773. The page says a rank is not a probability and not efficacy." | – |
| 1:05 | **Evidence** → *Mechanism*, *Conflicting evidence*, *Trial-role review* | review shows **Awaiting human review (28)** | "Every number links to its source. Conflicting evidence is shown, e.g. a 550-patient Donepezil trial with a null cognition result. 28 trial links wait for a human; the software never decides them." | – |
| 1:25 | **Validation** | AUROC 0.775 (0.656–0.881), AUPRC 0.424 vs chance 0.156; "not leakage-free"; corrected rule 0.699 "not approved" | "AUROC 0.775: a random positive outranks a random negative 77.5% of the time. It is not a success probability. Literature, safety and molecular data are current snapshots, so this is an **upper estimate**: using only pre-2021 data it is **0.689 [0.548–0.819]** (release report). A proposed molecular correction gives 0.699; it is not approved." | Note: 0.689 is not displayed in the UI. Quote it from `docs/final_release_20261022/FINAL_RELEASE_REPORT.md` §4. |
| 2:00 | **Run Center → Pipeline health** | yellow badge "some inputs not verifiable"; agent cards "checks a score input; does not change the score" | "Eight agents check the evidence. None of them changes the score; the five dimensions come from the pipeline stages. The yellow badge means one evaluation input was never fingerprinted, so we say 'not verifiable' rather than 'current'." | – |
| 2:20 | **Stages and runs** → row **10h Completeness & Gap Agent** → **Run** | the row turns to **Run completed · 1 s · log &lt;run id&gt;** without reloading | "This is a real run: recorded, logged, with its outputs validated. Stage 06, which writes the approved score, has no Run button; protected stages say 'Needs owner approval'." | If the button is disabled, a run is already in progress; wait for it to finish. Never click **Run…** on 05h or 04p (network). |
| 2:40 | – | – | **Summary:** "90 drugs, 5 dimensions, 8 checking agents. AUROC 0.775, an upper estimate (0.689 with dated inputs). Retrospective, internal validation of a trial-activity proxy, not efficacy. Open decisions: the molecular correction, a cohort rebuild that would add Dopamine, and 28 human reviews." | – |

## 2. Do not, during the talk
- Click **Run all**, **Run…** on 05h/04p, or anything marked "Needs owner approval".
- Edit code, or run tests or `run_stage.py` against the real project.

## 3. Fallback plan
- **Server crashes:** `./venv/bin/python ui/server.py` restarts it in about 2 s. The data is in files, so nothing is lost.
- **The 10h run fails:** the page shows FAILED with the log, and the previous output is restored automatically (browser-tested). Say exactly that; it demonstrates failure handling.
- **Browser problem:** show `screenshots/01_overview.png` … `07_after_10h_run.png`.
- **Something looks wrong:** run `./venv/bin/python scripts/vps_verify.py`. MATCH means the approved scores are intact.
- **Recovery:** the snapshot is at `~/EviRep_recovery_presentation_20261022T0217Z/` (checksums verified 5/5).
