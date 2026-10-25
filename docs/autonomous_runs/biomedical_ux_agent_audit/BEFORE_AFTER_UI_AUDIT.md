# Before / after UI audit

Screenshots are in `screenshots/` (`before_*` were taken from the live server before any edit; `after_*` from an isolated copy on the final code). Desktop is 1440 px wide and mobile 390 px. The metrics come from `before_metrics.json` and `after_metrics.json`, measured on the visible text of `#main` only, so collapsed technical details are excluded.

## Navigation

| Before (11 top-level entries) | After (5 sections) |
|---|---|
| Dashboard, Stages | **Run Center**: Pipeline health · Stages and runs · Advanced diagnostics (stages/files, agents/connectors, documents, agent pages) |
| Candidates, Compare | **Candidates**: Candidate table · Compare; a separate page per candidate |
| Evidence, Mechanism, Conflicts, Review queue | **Evidence**: All evidence · Mechanism · Conflicting evidence · Trial-role review |
| Validation & Methods, Results summary | **Validation** (summary + 6 sections); the Results-summary findings moved into its summary |
| Diagnostics | Run Center › Advanced diagnostics |
| (default page: operational Dashboard) | **Overview**: researcher landing page (new default) |

Every older address still works and opens inside its new section:
- `#dashboard` and `#live`;
- `#mechanism/…` and `#conflicts/…`;
- `#review`;
- `#compare/…`;
- `#technical`, `#pipeline`, `#agents`, `#cases` and `#agent/…`.

Browser title pattern: `EviRep · Section · Page`.

## Page by page

| Page | Before | After |
|---|---|---|
| overview | 3,598 chars, 5 agent ids, 3 paths, 0 charts | 3,553 chars, **0** ids/paths, 2 charts (top-10 signals, evidence coverage) |
| dashboard → run | 6,401 chars, 29 ids, 4 charts | 6,778 chars, 21 ids (stage identifiers are legitimate in the operational view), 4 charts |
| drugs | 33,010 chars, 17 raw codes, 25 ids, 7 paths | 19,897 chars, **0 / 0 / 0** |
| drugs/Donepezil | 31,198 chars, 25 codes, 20 ids, 6 paths | 14,837 chars, **0 / 0 / 0**; adds "Why it ranks", the mechanism chain and actions |
| evidence | 17,550 chars, 100 agent ids (in result notes) | 22,531 chars, **0 ids**; adds Stance and Basis columns, two filters and a legend |
| validation | 10,353 chars, 14 paths, 6 charts | 9,165 chars, **0 paths**, 7 charts, 6 numbered sections plus summary |
| compare | 3,118 chars, 3 ids | 2,942 chars, 0 ids |
| mechanism | 1 id, 1 path | 0 / 0 |
| conflicts | 21 ids, 21 paths | 0 / 0 (provenance in expandable boxes) |
| review | **87 raw codes** | **0**; codes shown in words; adjudication explicitly human |
| live (Stages and runs) | 59 ids | 57 ids (operational by design) |

## Removed, merged or relocated

- **Removed from primary copy** (still available under "Source and provenance" or Advanced diagnostics):
  - file paths, agent and stage ids, run ids, decision ids (TD-, D-, B-);
  - the pending result-set id `td042_v1`;
  - registry and role codes.
- **Moved off the Overview to Advanced diagnostics:**
  - the Markdown-derived "open high-severity risks" list;
  - saved-artefact file table;
  - test-run metadata.
- **Merged:**
  - Results summary into Validation;
  - Mechanism, Conflicts and Review into Evidence;
  - Stages and Diagnostics into Run Center.
- **Split:** the candidate table and the candidate detail were one 33,000-character page and are now two pages with their own addresses.
- **New:**
  - Overview;
  - Evidence stance and basis;
  - candidate "What drives the score" and "Key limitation";
  - evaluation-type tags;
  - the "verified with gaps" freshness state;
  - distinct refusal reasons;
  - "Clear filters";
  - a single clear message for an unknown compound.

## Defects found and fixed during the pass

| Defect | Fix | Verified by |
|---|---|---|
| Freshness showed "current" while a declared input was never fingerprinted | New `VERIFIED_WITH_GAPS` state; header pill no longer green | `test_agent_failure_modes` |
| Untracked **outputs** were described as inputs ("reads … would rewrite an approved file") | Inputs and outputs separated; consequence stated only when true | `test_untracked_output_is_not_described_as_an_input` |
| Unknown compound showed two contradictory messages | One message | drive16 |
| 28 + 9 trial links had no visible human/automatic distinction in the evidence list | Basis column joined to the review queue | `test_review_state_comes_from_the_review_queue` |
| Mobile: the 5th section hidden in a scrolling nav; candidate table squeezed until words broke | Nav wraps; table scrolls in its box | screenshots `after_mobile_*` |
