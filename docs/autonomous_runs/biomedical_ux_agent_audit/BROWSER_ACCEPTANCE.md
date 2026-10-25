# Browser acceptance

**Setup.** Headless Google Chrome **155.0.8059.84**, driven through CDP on port 9333. The app under test is `ui/server.py` serving an **isolated copy** of `data/` on port 8799, with the real `scripts/run_stage.py` and real stage processes.

**Result: 156 / 156 checks pass across 9 suites.** Raw results are in `evidence/browser_drive*.json`, console logs in `evidence/drive*.out` and driver scripts in `evidence/drive*.py`.

| Suite | Scope | Result |
|---|---|---|
| **drive16 (new)** | Biomedical UX acceptance: 5-section navigation, sub-pages, old addresses, deep link/back/refresh, Overview content and truthfulness, top-10 chart = approved ranking, bar → candidate, candidate table columns/search/filter/clear/sort/aria-sort, imputed marks, candidate page sections, compare add/remove, unknown compound, evidence stance/basis filters = API counts, legend, compound-scoped evidence, review queue (no decision control), validation sections + focus jump + evaluation-type tags + curves, distinct refusals, confirm/back, **no run on page load or polling**, **rapid repeated clicks start exactly one run**, completed run shown live, server loss and recovery, **no raw codes/agent ids/paths/td042 on 10 researcher pages**, keyboard order (skip link → sections) and Enter activation, 390 px without page overflow, idle polling = 5 `/api/status` requests in 20 s and nothing else, render times, no JS errors | **44 / 44** |
| drive15 | UI quality: routes, labels, charts against source data, controls | **24 / 24** |
| drive11 | Run Center live: Run all, a real running stage, concurrency 409, server restart mid-run, real failure + restore, views, traceability, layouts | **16 / 16** |
| drive14 | Frozen server (SIGSTOP), single-flight polling, next steps | **9 / 9** |
| drive9 | Stages and runs end to end, including confirm, stale propagation, pause/resume, restart, failure, corrupt manifest | **15 / 15** |
| drive12 | Malformed manifest | **10 / 10** |
| drive7 | Navigation, keyboard focus, review queue | **21 / 21** |
| drive8 | Corrupt manifest in the run table | **8 / 8** |
| drive13 | Timeout lifecycle on an isolated code+data copy (10h limit 20 s **in the copy only**) | **9 / 9** |

**Measured on this machine (drive16).**
- First load: 0.6 s.
- Section render: Overview 0.76 s, Candidates 0.78 s, Evidence 0.95 s, Validation 0.80 s, Run Center 0.79 s, candidate page 1.03 s.
- Server times: `/api/status` about 7 ms; `/api/live` about 10 ms warm (290 ms on the first, cold call).

## Expectation updates in older suites

These are test-text changes only; no check was weakened:
- **drive11 / drive14:** start at `#run`, because the Overview is now the default. Headline strings updated: "A run is in progress"; "Current against recorded inputs…"; "Recorded baseline".
- **drive15:** headline map now includes the `VERIFIED_WITH_GAPS` state. The candidate detail is now its own page, so the check returns to the table before the keyboard test. Search now filters the table. The Evidence table has 9 columns with the source shown.
- **drive9:** refusal text is now "Needs owner approval" / "not from this screen".
- **drive16:** four harness bugs were fixed during development:
  - a `const` redeclaration;
  - a variable name collision;
  - a keyboard check that did not start from a fresh page;
  - Enter sent without the text field that activates a button.

  The keyboard check was then **tightened**: focus order must be exactly skip link → Overview → Candidates → Evidence, and Enter must open Evidence.

**Timing note.** drive7, 8, 12 and 13 ran before the last three cosmetic edits (mobile CSS, one sentence, chip labels). drive16 was re-run after the CSS edit; the final chip-label edit was covered by the Python UI tests only.

## Accessibility limitations

- **Not tested:** screen readers and browsers other than Chrome.
- **Tested:**
  - keyboard order and activation;
  - `aria-current` on sections and sub-pages;
  - `aria-sort`;
  - live counts (`aria-live`);
  - every chart has a data-table alternative;
  - status is never shown by colour alone (✓ / ! / ✕ symbols, ● and † chart markers, text labels).
- **Colour contrast:** the new styles use only the existing colour tokens checked by `tests/test_ui.py::TestAccessibleContrast`.
