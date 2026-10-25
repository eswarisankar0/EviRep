# Route and control matrix (audit 2026-10-21)

Every control below was **operated in real Chrome** (CDP; isolated copy server on :8799) by `drive18.py`. The page was reloaded before each control, so state could not leak between controls. Evidence: `records/browser/results18.json` (row = route + index), `records/browser/drive18.out`, and `records/browser/results18b.json` (targeted re-test).

**Excluded here, but executed elsewhere:**
- Run-launch controls (`data-run`, `data-pipeline`, `data-confirm`): executed against an isolated runner by drive9, drive11, drive13 and drive16 (`RUN_CENTER_AUDIT.md`).
- Every internal link: the previous overnight interaction audit drive17 checked 2,118 controls and 1,378 links with 0 dead (earlier code; not re-run in this audit).

## Summary by route

| Route | Controls | Effect | Already active | No effect | JS exceptions |
|---|---|---|---|---|---|
| `#overview` | 15 | 14 | 1 | 0 | 0 |
| `#drugs` | 46 | 43 | 2 | 1 | 0 |
| `#drugs/Donepezil` | 7 | 5 | 2 | 0 | 0 |
| `#compare` | 10 | 8 | 2 | 0 | 0 |
| `#evidence` | 16 | 14 | 2 | 0 | 0 |
| `#mechanism` | 10 | 8 | 2 | 0 | 0 |
| `#conflicts` | 9 | 7 | 2 | 0 | 0 |
| `#review` | 11 | 9 | 2 | 0 | 0 |
| `#validation` | 5 | 4 | 1 | 0 | 0 |
| `#run` | 8 | 6 | 2 | 0 | 0 |
| `#live` | 8 | 6 | 2 | 0 | 0 |
| `#technical` | 8 | 6 | 2 | 0 | 0 |
| `#pipeline` | 8 | 6 | 2 | 0 | 0 |
| `#agents` | 9 | 7 | 2 | 0 | 0 |
| `#cases` | 8 | 6 | 2 | 0 | 0 |
| `#agent/10b` | 8 | 6 | 2 | 0 | 0 |
| **Total** | **186** | **155** | **30** | **1** (re-tested: PASS) | **0** |

Severity is "–" for every row: no defect was found by operating a control. The defects found in this audit came from other checks (`ISSUES_AND_REMEDIATION.md`).

## Per-control matrix

| Route | # | Control | Expected behaviour | Actual behaviour | Evidence | Status | Severity |
|---|---|---|---|---|---|---|---|
| `#overview` | 0 | button “Overview” | navigates to the overview view | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#overview` | 1 | button “Candidates” | navigates to the drugs view | view changed; hash → #drugs | results18.json | PASS | – |
| `#overview` | 2 | button “Evidence” | navigates to the evidence view | view changed; hash → #evidence | results18.json | PASS | – |
| `#overview` | 3 | button “Validation” | navigates to the validation view | view changed; hash → #validation | results18.json | PASS | – |
| `#overview` | 4 | button “Run Center” | navigates to the run view | view changed; hash → #run | results18.json | PASS | – |
| `#overview` | 5 | g “1. Donepezil: 0.773” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Donepezil | results18.json | PASS | – |
| `#overview` | 6 | g “2. Zonisamide: 0.761” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Zonisamide | results18.json | PASS | – |
| `#overview` | 7 | g “3. Quetiapine: 0.724” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Quetiapine | results18.json | PASS | – |
| `#overview` | 8 | g “4. Dexmedetomidine: 0.723” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Dexmedetomidine | results18.json | PASS | – |
| `#overview` | 9 | g “5. Lisuride: 0.718” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Lisuride | results18.json | PASS | – |
| `#overview` | 10 | g “6. Melatonin: 0.717” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Melatonin | results18.json | PASS | – |
| `#overview` | 11 | g “7. Droxidopa: 0.703” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Droxidopa | results18.json | PASS | – |
| `#overview` | 12 | g “8. Methylphenidate: 0.669” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Methylphenidate | results18.json | PASS | – |
| `#overview` | 13 | g “9. Lidocaine: 0.667” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Lidocaine | results18.json | PASS | – |
| `#overview` | 14 | g “10. Domperidone: 0.663” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Domperidone | results18.json | PASS | – |
| `#drugs` | 0 | button “Overview” | navigates to the overview view | view changed; hash → #overview | results18.json | PASS | – |
| `#drugs` | 1 | button “Candidates” | navigates to the drugs view | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#drugs` | 2 | button “Evidence” | navigates to the evidence view | view changed; hash → #evidence | results18.json | PASS | – |
| `#drugs` | 3 | button “Validation” | navigates to the validation view | view changed; hash → #validation | results18.json | PASS | – |
| `#drugs` | 4 | button “Run Center” | navigates to the run view | view changed; hash → #run | results18.json | PASS | – |
| `#drugs` | 5 | a “Candidate table” | sub-navigation link opens its section | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#drugs` | 6 | a “Compare” | sub-navigation link opens its section | view changed; hash → #compare | results18.json | PASS | – |
| `#drugs` | 7 | g “1. Donepezil: 0.773” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Donepezil | results18.json | PASS | – |
| `#drugs` | 8 | g “2. Zonisamide: 0.761” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Zonisamide | results18.json | PASS | – |
| `#drugs` | 9 | g “3. Quetiapine: 0.724” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Quetiapine | results18.json | PASS | – |
| `#drugs` | 10 | g “4. Dexmedetomidine: 0.723” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Dexmedetomidine | results18.json | PASS | – |
| `#drugs` | 11 | g “5. Lisuride: 0.718” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Lisuride | results18.json | PASS | – |
| `#drugs` | 12 | g “6. Melatonin: 0.717” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Melatonin | results18.json | PASS | – |
| `#drugs` | 13 | g “7. Droxidopa: 0.703” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Droxidopa | results18.json | PASS | – |
| `#drugs` | 14 | g “8. Methylphenidate: 0.669” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Methylphenidate | results18.json | PASS | – |
| `#drugs` | 15 | g “9. Lidocaine: 0.667” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Lidocaine | results18.json | PASS | – |
| `#drugs` | 16 | g “10. Domperidone: 0.663” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Domperidone | results18.json | PASS | – |
| `#drugs` | 17 | g “11. Aripiprazole: 0.658” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Aripiprazole | results18.json | PASS | – |
| `#drugs` | 18 | g “12. Clonidine: 0.643” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Clonidine | results18.json | PASS | – |
| `#drugs` | 19 | g “13. Sildenafil: 0.637” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Sildenafil | results18.json | PASS | – |
| `#drugs` | 20 | g “14. Buspirone: 0.633” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Buspirone | results18.json | PASS | – |
| `#drugs` | 21 | g “15. Acetylcysteine: 0.628” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Acetylcysteine | results18.json | PASS | – |
| `#drugs` | 22 | g “16. Quinidine: 0.617” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Quinidine | results18.json | PASS | – |
| `#drugs` | 23 | g “17. Terazosin: 0.614” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Terazosin | results18.json | PASS | – |
| `#drugs` | 24 | g “18. Carvedilol: 0.614” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Carvedilol | results18.json | PASS | – |
| `#drugs` | 25 | g “19. Minocycline: 0.613” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Minocycline | results18.json | PASS | – |
| `#drugs` | 26 | g “20. Dextromethorphan: 0.612” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Dextromethorphan | results18.json | PASS | – |
| `#drugs` | 27 | g “21. Omeprazole: 0.609” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Omeprazole | results18.json | PASS | – |
| `#drugs` | 28 | g “22. Fesoterodine: 0.608” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Fesoterodine | results18.json | PASS | – |
| `#drugs` | 29 | g “23. Ioflupane I 123: 0.605” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Ioflupane%20I%20123 | results18.json | PASS | – |
| `#drugs` | 30 | g “24. Solifenacin: 0.603” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Solifenacin | results18.json | PASS | – |
| `#drugs` | 31 | g “25. Glycopyrrolate: 0.601” | keyboard Enter on the focused chart bar opens that candidate | view changed; hash → #drugs/Glycopyrrolate | results18.json | PASS | – |
| `#drugs` | 32 | input#q “q” | typing filters the list; a non-matching term shows an empty-state message | view changed; empty-state message shown | results18.json | PASS | – |
| `#drugs` | 33 | select#flabel | changing the option re-filters or re-renders the view | view changed | results18.json | PASS | – |
| `#drugs` | 34 | select#fmiss | changing the option re-filters or re-renders the view | view changed | results18.json | PASS | – |
| `#drugs` | 35 | select#fconf | changing the option re-filters or re-renders the view | view changed | results18.json | PASS | – |
| `#drugs` | 36 | button#freset “Clear filters” | changes the view or its state | no change on a clean page (nothing to clear). Targeted re-test: 90→1 rows filtered, Clear → 90 rows, all fields empty: PASS | results18.json | PASS (re-tested) | – |
| `#drugs` | 37 | button “Rank” | sorts the table (aria-sort changes) | view changed | results18.json | PASS | – |
| `#drugs` | 38 | button “Compound” | sorts the table (aria-sort changes) | view changed | results18.json | PASS | – |
| `#drugs` | 39 | button “Score” | sorts the table (aria-sort changes) | view changed | results18.json | PASS | – |
| `#drugs` | 40 | button “Evidence coverage” | sorts the table (aria-sort changes) | view changed | results18.json | PASS | – |
| `#drugs` | 41 | button “Clinical (rank)” | sorts the table (aria-sort changes) | view changed | results18.json | PASS | – |
| `#drugs` | 42 | button “Safety (rank)” | sorts the table (aria-sort changes) | view changed | results18.json | PASS | – |
| `#drugs` | 43 | button “Mechanism (rank)” | sorts the table (aria-sort changes) | view changed | results18.json | PASS | – |
| `#drugs` | 44 | button “Conflicting evidence” | sorts the table (aria-sort changes) | view changed | results18.json | PASS | – |
| `#drugs` | 45 | button “New trial after 2020” | sorts the table (aria-sort changes) | view changed | results18.json | PASS | – |
| `#drugs/Donepezil` | 0 | button “Overview” | navigates to the overview view | view changed; hash → #overview | results18.json | PASS | – |
| `#drugs/Donepezil` | 1 | button “Candidates” | navigates to the drugs view | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#drugs/Donepezil` | 2 | button “Evidence” | navigates to the evidence view | view changed; hash → #evidence | results18.json | PASS | – |
| `#drugs/Donepezil` | 3 | button “Validation” | navigates to the validation view | view changed; hash → #validation | results18.json | PASS | – |
| `#drugs/Donepezil` | 4 | button “Run Center” | navigates to the run view | view changed; hash → #run | results18.json | PASS | – |
| `#drugs/Donepezil` | 5 | a “Candidate table” | sub-navigation link opens its section | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#drugs/Donepezil` | 6 | a “Compare” | sub-navigation link opens its section | view changed; hash → #compare | results18.json | PASS | – |
| `#compare` | 0 | button “Overview” | navigates to the overview view | view changed; hash → #overview | results18.json | PASS | – |
| `#compare` | 1 | button “Candidates” | navigates to the drugs view | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#compare` | 2 | button “Evidence” | navigates to the evidence view | view changed; hash → #evidence | results18.json | PASS | – |
| `#compare` | 3 | button “Validation” | navigates to the validation view | view changed; hash → #validation | results18.json | PASS | – |
| `#compare` | 4 | button “Run Center” | navigates to the run view | view changed; hash → #run | results18.json | PASS | – |
| `#compare` | 5 | a “Candidate table” | sub-navigation link opens its section | view changed; hash → #drugs | results18.json | PASS | – |
| `#compare` | 6 | a “Compare” | sub-navigation link opens its section | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#compare` | 7 | select#cmpadd | changing the option re-filters or re-renders the view | view changed; hash → #compare/Donepezil,Zonisamide,Quetiapine | results18.json | PASS | – |
| `#compare` | 8 | button “Remove Donepezil” | changes the view or its state | view changed; hash → #compare/Zonisamide | results18.json | PASS | – |
| `#compare` | 9 | button “Remove Zonisamide” | changes the view or its state | view changed; hash → #compare/Donepezil | results18.json | PASS | – |
| `#evidence` | 0 | button “Overview” | navigates to the overview view | view changed; hash → #overview | results18.json | PASS | – |
| `#evidence` | 1 | button “Candidates” | navigates to the drugs view | view changed; hash → #drugs | results18.json | PASS | – |
| `#evidence` | 2 | button “Evidence” | navigates to the evidence view | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#evidence` | 3 | button “Validation” | navigates to the validation view | view changed; hash → #validation | results18.json | PASS | – |
| `#evidence` | 4 | button “Run Center” | navigates to the run view | view changed; hash → #run | results18.json | PASS | – |
| `#evidence` | 5 | a “All evidence” | sub-navigation link opens its section | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#evidence` | 6 | a “Mechanism” | sub-navigation link opens its section | view changed; hash → #mechanism | results18.json | PASS | – |
| `#evidence` | 7 | a “Conflicting evidence” | sub-navigation link opens its section | view changed; hash → #conflicts | results18.json | PASS | – |
| `#evidence` | 8 | a “Trial-role review” | sub-navigation link opens its section | view changed; hash → #review | results18.json | PASS | – |
| `#evidence` | 9 | select#etype | changing the option re-filters or re-renders the view | view changed | results18.json | PASS | – |
| `#evidence` | 10 | select#estance | changing the option re-filters or re-renders the view | view changed | results18.json | PASS | – |
| `#evidence` | 11 | select#ebasis | changing the option re-filters or re-renders the view | view changed | results18.json | PASS | – |
| `#evidence` | 12 | input#ecomp “ecomp” | typing filters the list; a non-matching term shows an empty-state message | view changed; empty-state message shown | results18.json | PASS | – |
| `#evidence` | 13 | input#etext “etext” | typing filters the list; a non-matching term shows an empty-state message | view changed; empty-state message shown | results18.json | PASS | – |
| `#evidence` | 14 | button#emore “Show 100 more” | changes the view or its state | view changed | results18.json | PASS | – |
| `#evidence` | 15 | input#esrc “on” | toggling changes the view | view changed | results18.json | PASS | – |
| `#mechanism` | 0 | button “Overview” | navigates to the overview view | view changed; hash → #overview | results18.json | PASS | – |
| `#mechanism` | 1 | button “Candidates” | navigates to the drugs view | view changed; hash → #drugs | results18.json | PASS | – |
| `#mechanism` | 2 | button “Evidence” | navigates to the evidence view | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#mechanism` | 3 | button “Validation” | navigates to the validation view | view changed; hash → #validation | results18.json | PASS | – |
| `#mechanism` | 4 | button “Run Center” | navigates to the run view | view changed; hash → #run | results18.json | PASS | – |
| `#mechanism` | 5 | a “All evidence” | sub-navigation link opens its section | view changed; hash → #evidence | results18.json | PASS | – |
| `#mechanism` | 6 | a “Mechanism” | sub-navigation link opens its section | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#mechanism` | 7 | a “Conflicting evidence” | sub-navigation link opens its section | view changed; hash → #conflicts | results18.json | PASS | – |
| `#mechanism` | 8 | a “Trial-role review” | sub-navigation link opens its section | view changed; hash → #review | results18.json | PASS | – |
| `#mechanism` | 9 | select#mechpick | changing the option re-filters or re-renders the view | view changed; hash → #mechanism/Zonisamide | results18.json | PASS | – |
| `#conflicts` | 0 | button “Overview” | navigates to the overview view | view changed; hash → #overview | results18.json | PASS | – |
| `#conflicts` | 1 | button “Candidates” | navigates to the drugs view | view changed; hash → #drugs | results18.json | PASS | – |
| `#conflicts` | 2 | button “Evidence” | navigates to the evidence view | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#conflicts` | 3 | button “Validation” | navigates to the validation view | view changed; hash → #validation | results18.json | PASS | – |
| `#conflicts` | 4 | button “Run Center” | navigates to the run view | view changed; hash → #run | results18.json | PASS | – |
| `#conflicts` | 5 | a “All evidence” | sub-navigation link opens its section | view changed; hash → #evidence | results18.json | PASS | – |
| `#conflicts` | 6 | a “Mechanism” | sub-navigation link opens its section | view changed; hash → #mechanism | results18.json | PASS | – |
| `#conflicts` | 7 | a “Conflicting evidence” | sub-navigation link opens its section | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#conflicts` | 8 | a “Trial-role review” | sub-navigation link opens its section | view changed; hash → #review | results18.json | PASS | – |
| `#review` | 0 | button “Overview” | navigates to the overview view | view changed; hash → #overview | results18.json | PASS | – |
| `#review` | 1 | button “Candidates” | navigates to the drugs view | view changed; hash → #drugs | results18.json | PASS | – |
| `#review` | 2 | button “Evidence” | navigates to the evidence view | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#review` | 3 | button “Validation” | navigates to the validation view | view changed; hash → #validation | results18.json | PASS | – |
| `#review` | 4 | button “Run Center” | navigates to the run view | view changed; hash → #run | results18.json | PASS | – |
| `#review` | 5 | a “All evidence” | sub-navigation link opens its section | view changed; hash → #evidence | results18.json | PASS | – |
| `#review` | 6 | a “Mechanism” | sub-navigation link opens its section | view changed; hash → #mechanism | results18.json | PASS | – |
| `#review` | 7 | a “Conflicting evidence” | sub-navigation link opens its section | view changed; hash → #conflicts | results18.json | PASS | – |
| `#review` | 8 | a “Trial-role review” | sub-navigation link opens its section | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#review` | 9 | input#rq “rq” | typing filters the list; a non-matching term shows an empty-state message | view changed; empty-state message shown | results18.json | PASS | – |
| `#review` | 10 | select#rflag | changing the option re-filters or re-renders the view | view changed | results18.json | PASS | – |
| `#validation` | 0 | button “Overview” | navigates to the overview view | view changed; hash → #overview | results18.json | PASS | – |
| `#validation` | 1 | button “Candidates” | navigates to the drugs view | view changed; hash → #drugs | results18.json | PASS | – |
| `#validation` | 2 | button “Evidence” | navigates to the evidence view | view changed; hash → #evidence | results18.json | PASS | – |
| `#validation` | 3 | button “Validation” | navigates to the validation view | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#validation` | 4 | button “Run Center” | navigates to the run view | view changed; hash → #run | results18.json | PASS | – |
| `#run` | 0 | button “Overview” | navigates to the overview view | view changed; hash → #overview | results18.json | PASS | – |
| `#run` | 1 | button “Candidates” | navigates to the drugs view | view changed; hash → #drugs | results18.json | PASS | – |
| `#run` | 2 | button “Evidence” | navigates to the evidence view | view changed; hash → #evidence | results18.json | PASS | – |
| `#run` | 3 | button “Validation” | navigates to the validation view | view changed; hash → #validation | results18.json | PASS | – |
| `#run` | 4 | button “Run Center” | navigates to the run view | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#run` | 5 | a “Pipeline health” | sub-navigation link opens its section | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#run` | 6 | a “Stages and runs” | sub-navigation link opens its section | view changed; hash → #live | results18.json | PASS | – |
| `#run` | 7 | a “Advanced diagnostics” | sub-navigation link opens its section | view changed; hash → #technical | results18.json | PASS | – |
| `#live` | 0 | button “Overview” | navigates to the overview view | view changed; hash → #overview | results18.json | PASS | – |
| `#live` | 1 | button “Candidates” | navigates to the drugs view | view changed; hash → #drugs | results18.json | PASS | – |
| `#live` | 2 | button “Evidence” | navigates to the evidence view | view changed; hash → #evidence | results18.json | PASS | – |
| `#live` | 3 | button “Validation” | navigates to the validation view | view changed; hash → #validation | results18.json | PASS | – |
| `#live` | 4 | button “Run Center” | navigates to the run view | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#live` | 5 | a “Pipeline health” | sub-navigation link opens its section | view changed; hash → #run | results18.json | PASS | – |
| `#live` | 6 | a “Stages and runs” | sub-navigation link opens its section | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#live` | 7 | a “Advanced diagnostics” | sub-navigation link opens its section | view changed; hash → #technical | results18.json | PASS | – |
| `#technical` | 0 | button “Overview” | navigates to the overview view | view changed; hash → #overview | results18.json | PASS | – |
| `#technical` | 1 | button “Candidates” | navigates to the drugs view | view changed; hash → #drugs | results18.json | PASS | – |
| `#technical` | 2 | button “Evidence” | navigates to the evidence view | view changed; hash → #evidence | results18.json | PASS | – |
| `#technical` | 3 | button “Validation” | navigates to the validation view | view changed; hash → #validation | results18.json | PASS | – |
| `#technical` | 4 | button “Run Center” | navigates to the run view | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#technical` | 5 | a “Pipeline health” | sub-navigation link opens its section | view changed; hash → #run | results18.json | PASS | – |
| `#technical` | 6 | a “Stages and runs” | sub-navigation link opens its section | view changed; hash → #live | results18.json | PASS | – |
| `#technical` | 7 | a “Advanced diagnostics” | sub-navigation link opens its section | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#pipeline` | 0 | button “Overview” | navigates to the overview view | view changed; hash → #overview | results18.json | PASS | – |
| `#pipeline` | 1 | button “Candidates” | navigates to the drugs view | view changed; hash → #drugs | results18.json | PASS | – |
| `#pipeline` | 2 | button “Evidence” | navigates to the evidence view | view changed; hash → #evidence | results18.json | PASS | – |
| `#pipeline` | 3 | button “Validation” | navigates to the validation view | view changed; hash → #validation | results18.json | PASS | – |
| `#pipeline` | 4 | button “Run Center” | navigates to the run view | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#pipeline` | 5 | a “Pipeline health” | sub-navigation link opens its section | view changed; hash → #run | results18.json | PASS | – |
| `#pipeline` | 6 | a “Stages and runs” | sub-navigation link opens its section | view changed; hash → #live | results18.json | PASS | – |
| `#pipeline` | 7 | a “Advanced diagnostics” | sub-navigation link opens its section | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#agents` | 0 | button “Overview” | navigates to the overview view | view changed; hash → #overview | results18.json | PASS | – |
| `#agents` | 1 | button “Candidates” | navigates to the drugs view | view changed; hash → #drugs | results18.json | PASS | – |
| `#agents` | 2 | button “Evidence” | navigates to the evidence view | view changed; hash → #evidence | results18.json | PASS | – |
| `#agents` | 3 | button “Validation” | navigates to the validation view | view changed; hash → #validation | results18.json | PASS | – |
| `#agents` | 4 | button “Run Center” | navigates to the run view | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#agents` | 5 | a “Pipeline health” | sub-navigation link opens its section | view changed; hash → #run | results18.json | PASS | – |
| `#agents` | 6 | a “Stages and runs” | sub-navigation link opens its section | view changed; hash → #live | results18.json | PASS | – |
| `#agents` | 7 | a “Advanced diagnostics” | sub-navigation link opens its section | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#agents` | 8 | select#agentpick | changing the option re-filters or re-renders the view | view changed; hash → #agents/Acamprosate | results18.json | PASS | – |
| `#cases` | 0 | button “Overview” | navigates to the overview view | view changed; hash → #overview | results18.json | PASS | – |
| `#cases` | 1 | button “Candidates” | navigates to the drugs view | view changed; hash → #drugs | results18.json | PASS | – |
| `#cases` | 2 | button “Evidence” | navigates to the evidence view | view changed; hash → #evidence | results18.json | PASS | – |
| `#cases` | 3 | button “Validation” | navigates to the validation view | view changed; hash → #validation | results18.json | PASS | – |
| `#cases` | 4 | button “Run Center” | navigates to the run view | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#cases` | 5 | a “Pipeline health” | sub-navigation link opens its section | view changed; hash → #run | results18.json | PASS | – |
| `#cases` | 6 | a “Stages and runs” | sub-navigation link opens its section | view changed; hash → #live | results18.json | PASS | – |
| `#cases` | 7 | a “Advanced diagnostics” | sub-navigation link opens its section | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#agent/10b` | 0 | button “Overview” | navigates to the overview view | view changed; hash → #overview | results18.json | PASS | – |
| `#agent/10b` | 1 | button “Candidates” | navigates to the drugs view | view changed; hash → #drugs | results18.json | PASS | – |
| `#agent/10b` | 2 | button “Evidence” | navigates to the evidence view | view changed; hash → #evidence | results18.json | PASS | – |
| `#agent/10b` | 3 | button “Validation” | navigates to the validation view | view changed; hash → #validation | results18.json | PASS | – |
| `#agent/10b` | 4 | button “Run Center” | navigates to the run view | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#agent/10b` | 5 | a “Pipeline health” | sub-navigation link opens its section | control is the current page (aria-current=page); clicking it is a no-op by design | results18.json | PASS (n/a) | – |
| `#agent/10b` | 6 | a “Stages and runs” | sub-navigation link opens its section | view changed; hash → #live | results18.json | PASS | – |
| `#agent/10b` | 7 | a “Advanced diagnostics” | sub-navigation link opens its section | view changed; hash → #technical | results18.json | PASS | – |
