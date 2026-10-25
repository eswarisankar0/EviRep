# Executive summary: biomedical UX redesign, eight-agent audit, release acceptance (2026-10-20)

## What changed

- **Navigation: 11 top-level tabs became 5 sections.**
  - **Overview** is the new default page.
  - **Candidates**, **Evidence** and **Validation** hold the research pages.
  - **Run Center** holds everything operational.
  - Every old address still works.
- **Overview** answers four questions in order: what you are looking at; how current and reliable it is (run state, source dates, scientific validity, each shown separately); what needs attention; what you can do next.
- **Candidates.**
  - One table with plain-language columns: what drives the score, evidence coverage, safety, mechanism, clinical, conflicting evidence, outcome and key limitation.
  - Search, filters, clear and sort.
  - Each candidate has its own page: why it ranked, evidence for and against, the drug → target → Parkinson's chain, safety, trials with human or automatic adjudication state, gaps, and provenance one click away.
- **Evidence.**
  - Evidence, mechanism, conflicting evidence and the trial-role review queue in one section.
  - Every evidence item is classified by **stance**: supports, null/opposing, context, missing, safety consideration.
  - Every item is also classified by **basis**: automatic, curated, human-reviewed, awaiting human review, mechanistic hypothesis.
- **Validation.**
  - A summary, then six sections: Performance, Evaluation design, Baselines and ablations, Missing and imputed data, Reproducibility, Methods and limitations.
  - Each result is tagged unfitted, in-sample, held-out or exploratory.
- **Truthful freshness.**
  - An unfingerprinted input now yields "Current against recorded inputs, with unverifiable inputs", never a green "current".
  - Refusals distinguish "Needs owner approval" from "Command line only" and "Not available".
- **Copy.** Researcher pages now show no raw status codes, agent or stage ids, file paths or the pending result-set id (they were 87, 100 and 21 on single pages before). Exact identifiers stay under "Source and provenance" and in Advanced diagnostics. See `UI_COPY_AUDIT.csv` (77 rows).

## Agents and online sources

- **Agent statuses.** 3 PASS (10c, 10e, 10f) and 5 PARTIAL (10a, 10b, 10d, 10g, 10h). None FAIL.
- **Fail-safe behaviour.** Every agent fails closed on a corrupt input when run through the real runner: FAILED, previous output byte-identical, dashboard shows the failure.
- **Seven pipeline defects (A-1 to A-7)** are documented with reproduction steps. They are not fixed, because they are pipeline code outside the UI scope.
- **Online sources (8 checked):**
  - PubMed, ClinicalTrials.gov, openFDA label, FAERS, DailyMed and Open Targets returned data **identical to what the project saved**.
  - Zenodo is reachable.
  - Semantic Scholar is blocked: HTTP 429, no key.

## Tests

- Python: 684 → **697 tests, all pass**.
- Browser: **156 / 156** checks in real Chrome, including the new 44-check acceptance suite.
- The protected artefacts are unchanged (19/19), and so is the Git index.

## Important remaining risks

- Open owner decisions: TD-042, TD-033, B-003, the 28 trial-role links, and the evaluation report's unfingerprinted input.
- Agent defects that can silently degrade diagnostic quality:
  - 10g accepts an empty literature table;
  - 10d skips malformed lines silently;
  - 10h consumes FAILED upstream outputs;
  - partial 04p, 05h and 10a-all results are discarded.
- Not tested: full online stages, production-length timeouts, screen readers, browsers other than Chrome.

## Release gate: **PARTIALLY PASSED**

| Criterion | Result |
|---|---|
| Navigation and primary journey materially simpler | PASS (11 → 5; candidate page halved; Overview answers the four questions) |
| Every visible primary control has verified behaviour | PASS (drive16 + 8 suites) |
| No unexplained internal jargon on researcher pages | PASS (0 codes, ids or paths on 10 researcher pages) |
| Every agent has a documented contract and evidence-backed status | PASS (statuses are 3 PASS / 5 PARTIAL) |
| Online behaviour distinguished from mocked tests | PASS |
| Freshness and failure states truthful | PASS |
| Charts use authoritative data | PASS |
| Protected outputs unchanged; adjudication and owner decisions untouched | PASS |
| Test failures and untested cases disclosed | PASS |
| All agents fully functional | **NOT MET**: 5 agents PARTIAL because of pipeline defects A-1 to A-4; Semantic Scholar not verified |

The UI work meets its gate. The application as a whole is not "fully ready": the agent defects and the owner's scientific decisions remain open.
