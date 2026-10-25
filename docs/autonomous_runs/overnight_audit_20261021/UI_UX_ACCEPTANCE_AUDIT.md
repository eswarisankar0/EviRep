# UI/UX acceptance audit (2026-10-21)

- **The app:** the existing vanilla JS + Python standard-library application (`ui/`), five sections: Overview, Candidates, Evidence, Validation, Run Center.
- **Page-by-page history:** the earlier redesign, with before/after screenshots and the copy audit, is in `../biomedical_ux_agent_audit/`.
- **This session:** a full interaction audit, the defects found by it and by screenshots, the alternative-scoring and data-contract displays, and final acceptance on the final code.
- **Test environment:** real headless Chrome 155 via CDP, against an isolated data copy on :8799 (drive7 also reads the live server on :8765, read-only).

## Interaction audit (drive17, new)
For every route, every visible link, button, select, input, expandable section and clickable chart element was enumerated (collapsed sections opened). A control passes when:
- it is a link to a route that renders, or to an external record built from a valid identifier;
- it is a native expandable section;
- or Chrome's debugger reports an event listener on it or a delegating ancestor (`DOMDebugger.getEventListeners`).

| Route | Controls | Dead | Bad external links |
|---|---|---|---|
| overview | 28 | 0 | 0 |
| drugs | 1,377 | 0 | 0 |
| drugs/Donepezil | 52 | 0 | 0 |
| compare | 15 | 0 | 0 |
| evidence | 218 | 0 | 0 |
| mechanism | 26 | 0 | 0 |
| conflicts | 88 | 0 | 0 |
| review | 90 | 0 | 0 |
| validation | 34 | 0 | 0 |
| run | 27 | 0 | 0 |
| live | 50 | 0 | 0 |
| technical | 20 | 0 | 0 |
| pipeline | 25 | 0 | 0 |
| agents | 21 | 0 | 0 |
| cases | 35 | 0 | 0 |
| agent/10b | 12 | 0 | 0 |
| **Total** | **2,118** | **0** | **0** |

- **Internal links:** all 1,378 distinct internal links were navigated; every one renders (0 failures).
- **JavaScript exceptions:** 0.
- **External links:** 15 sampled identifiers (3 trials, 3 PubMed, 3 DailyMed, 3 Ensembl, 3 ChEMBL) resolve on their public APIs, and each response contains the identifier (`records/external_link_check.json`).

The drive17 run was on the code before the last three edits (data-contract panel, restart banner, UTC header). Those are covered by the final acceptance suites below and by unit tests.

## Defects found and fixed this session

| Defect | Evidence | Fix |
|---|---|---|
| Dependency graph: state labels ("Recorded baseline (before run tracking)") overflowed their boxes; the state bar-chart label was cut off | `screenshots/before_desktop_run.png` | short state names in wider boxes (full name in the tooltip and data table); wider label margin. drive16: "no state label overflows its box" |
| The dashboard told the owner to re-run protected stages 05/08 for a cosmetic code change | same screenshot, Next step | scripts restored (see `CHANGELOG.md`) |
| The header refresh time was local time while everything else is UTC | inspection | UTC everywhere |
| The live server served the new page with the old API (404s) | drive7 | restarted; automatic restart banner added |
| The unapproved TD-042 result was invisible, so the user could not see how much the headline depends on it | brief §4.2 | Validation §7, clearly marked **Not approved**, with the backend's numbers; the approved result is unchanged |
| Provenance was scattered | brief §10 | one data-contract panel (Validation §5, Overview › Technical details) |

## Final acceptance (all on the final code)

| Suite | Scope | Result |
|---|---|---|
| drive16 | navigation, Overview truthfulness, candidates, evidence, review, validation (incl. §7 alternative), Run Center refusals and confirmations, single launch on repeated clicks, disconnect/reconnect, jargon check, keyboard, 390 px, polling cost, graph label overflow | 47/47 |
| drive15 | routes, labels, charts against data, controls | 24/24 |
| drive11 | Run Center live runs, restart mid-run, real failure and restore | 16/16 |
| drive12 | malformed run records | 10/10 |
| drive14 | frozen server, next steps | 9/9 |
| drive7 | navigation, focus, review queue, no failed requests (live server) | 21/21 |
| drive8 | corrupt manifest | 8/8 |
| drive9 | Live Pipeline end to end | 15/15 |
| drive13 | timeout lifecycle (20 s limit in an isolated code copy only) | 9/9 |
| **Total** | | **159/159** |

## Accessibility and responsiveness
**Tested:**
- keyboard order (skip link → sections) and Enter activation;
- `aria-current` and `aria-sort`;
- live counts;
- every chart has a data-table alternative;
- status uses symbols and text, not colour alone;
- no horizontal page scroll at 390 px on the five sections and a candidate page.

**Not tested:** screen readers, and browsers other than Chrome.

## Remaining UI limitations
- The dependency graph is dense (25 stages, crossing edges). It is readable but would benefit from an owner-chosen grouping.
- The Review page is read-only by design (see `REMAINING_BLOCKERS.md`).
- The wide candidate table scrolls inside its box on phones.

## Screenshots
`screenshots/before_*`: Run Center, Validation and Stages before this session's UI fixes. `screenshots/after_*`: the final UI for the major workflows.
