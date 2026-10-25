# ClinicalTrials.gov intervention matching policy

Implemented in `scripts/intervention_matcher.py`, applied by
`scripts/03_clinicaltrials_groundtruth.py`. Established 2026-10-05 in response to
ERRORS_AND_BLOCKERS **E-010** / TECHNICAL_DEBT **TD-018**.

---

## 1. The problem

Stage 03 searches ClinicalTrials.gov with `query.intr=<compound>`. That search expands
along relationships that are **not** evidence the trial administers the compound. All five
routes below were observed in real data from the 2026-10-05 run:

| Route | Example | What the trial actually tests |
|---|---|---|
| Chemical class | `Phenol` | levodopa/carbidopa (levodopa *is* a phenol) |
| Prodrug / metabolite | `Norepinephrine` | droxidopa (an NE prodrug) |
| Pharmacological class | `Dopamine` | sarizotan, safinamide, pramipexole |
| **Excipient in the placebo arm** | `Mannitol` | droxidopa — mannitol is the placebo filler |
| Registry catch-all | many compounds | one study listing dozens of drugs in free text |

Stage 03 already verified the trial's **condition** client-side (`is_actually_pd`). It did
not verify the **intervention**. This policy supplies that missing half.

---

## 2. What counts as evidence

A trial counts as evidence for compound *X* only when a **structured intervention field**
names *X*. Hierarchy, strongest first:

| `match_type` | Rule |
|---|---|
| `exact_name` | normalised intervention `name` **equals** the compound |
| `exact_othername` | normalised `otherNames[]` entry equals the compound |
| `token_name` | the compound's tokens appear as a contiguous whole-token run in `name` |
| `token_othername` | same, within an `otherNames[]` entry |
| `synonym_exact_name` / `synonym_exact_othername` | **exact** equality against a ChEMBL-verified synonym or trade name |

Token matching exists for combination products: `Levodopa` legitimately matches
`"ND0612 (Levodopa/Carbidopa solution)"`.

### Explicitly NOT evidence

- **Chemical, pharmacological or prodrug/metabolite class relationships.** The project's
  documentation does not define these as equivalent evidence, so accepting them would
  silently change the research definition. (Phase-2 rule 4: prodrug equivalence may only be
  used if the methodology explicitly defines it. It does not.)
- **The free-text `description` field.** It is prose; matching it reintroduces exactly the
  broad-text contamination being fixed.
- **Raw substring matching.** Comparison is on whole tokens, so `Phenol` cannot match
  `Phenolphthalein` and `Dopa` cannot match `Levodopa`.
- **Control/placebo arms.** See §3.

---

## 3. Control-arm exclusion

Trials list the inert filler of their placebo arm in `otherNames`. Observed live:

```
NCT01927055  interventions:
  { name: "Droxidopa", otherNames: ["L-threo-3,4-dihydroxyphenylserine, ..."] }
  { name: "Placebo",   otherNames: ["Mannitol"] }          <-- filler, not the studied drug
```

An intervention is treated as a control arm when **every token of its own name is a control
word** (`placebo`, `sham`, `vehicle`, `sugar`, `pill`, `tablet`, …). Its fields are excluded
from matching.

This is a **structural rule about the arm's role**, not a list of known-bad compounds:

- `"Placebo"`, `"Placebo Oral Tablet"`, `"Sugar Pill"` → control arm
- `"HRG2010; Sustained-release Carbidopa/Levodopa administered placebo"` → **not** a control
  arm (it names real agents), so it is still matched normally
- `"Oral D-Mannitol of Placebo"` → **not** a control arm, so the genuine mannitol trial
  (NCT03823638) is still accepted

---

## 4. Synonyms: authoritative, and exact-match only

Synonyms and trade names come from **ChEMBL**, retrieved through the Open Targets API
already used by the molecular agent (`scripts/molecular_agent.py`), batched and cached.
**No synonym is ever invented.** If a compound cannot be resolved, it keeps only its own
name, which makes matching *stricter*, never looser.

Synonyms match on **exact equality only** — token-run matching is reserved for the
compound's own name. Rationale: ChEMBL synonym lists carry noise. Observed live, the
synonym list for `Dopamine` includes `"Medopa"` (a levodopa brand) and `"Dobutamine a"`
(a different drug). Token-run matching on those could credit another drug's trial; exact
matching keeps the benefit (trade names like `NORTHERA` are listed exactly) without the risk.

Aliases shorter than 4 characters are dropped, so degenerate entries such as `"DA"` cannot
match.

Every accepted link records `match_source` (`compound_name` / `chembl_synonym` /
`chembl_trade_name`), so synonym-driven matches are auditable.

---

## 5. Four outcomes, and why the distinction is mandatory

| Outcome | Meaning | Qualifies as evidence? |
|---|---|---|
| `MATCHED` | a structured field names the compound | **yes** |
| `NO_MATCH` | interventions were readable; none names the compound | no — a *verified negative* |
| `UNVERIFIABLE` | structured fields cannot answer the question (e.g. a registry study whose `name` says "too many characters to list in this field") | no — but **not** a verified negative |
| `API_FAILURE` | the record could not be retrieved after retries | no — and **never** treated as absence of evidence |

Collapsing `API_FAILURE` or `UNVERIFIABLE` into `NO_MATCH` would convert an outage or a
documentation gap into a scientific finding. Stage 03 therefore retries 429/5xx with
exponential backoff and records failures separately; a compound whose *search* failed is
logged as `API_FAILURE` rather than as having no trials.

---

## 6. Audit trail

Stage 03 writes `data/clinicaltrials_match_audit.csv` containing **every** decision —
accepted and rejected — with:

`compound_name, compound_id, nct_id, brief_title, conditions, interventions, outcome,
match_type, matched_intervention, matched_alias, match_source, qualifies, cohort, reason`

Any accepted or rejected link can therefore be reproduced and challenged without re-querying
the API.

---

## 7. What this does NOT change

The temporal methodology is untouched. `CUTOFF_DATE = 2021-01-01`; pre-cutoff trials remain
a feature, post-cutoff trials remain ground truth and are never used as a feature. This
policy changes **which trials belong to a compound**, not what "positive" means.

Positives still encode *"a qualifying trial of this compound was first posted after the
cutoff"* — not clinical efficacy. That ambiguity is pre-existing and is recorded in
TECHNICAL_DEBT TD-004; it was not resolved here because doing so would be a
research-methodology decision.

---

## 8. Known residual limitations

1. **Synonym coverage is only as good as ChEMBL.** A trial naming a drug by an alias absent
   from ChEMBL will be a false negative. Counted and reported per run.
2. **`UNVERIFIABLE` records are genuinely unresolved**, not safe. They are excluded from
   evidence but should be reviewed if they are numerous.
3. **Token matching on combination products is permissive by design.** A trial of
   `"Levodopa/Carbidopa"` counts as evidence for *both* components. That is correct for
   "was this compound administered", but it is not evidence that the component was the
   active hypothesis under test.
