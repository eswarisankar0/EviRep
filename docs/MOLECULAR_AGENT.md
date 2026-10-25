# Molecular / Pathway Evidence Agent

EviRep evidence dimension 5. Builds a traceable molecular evidence chain and converts it
into an explainable score.

```
DRUG ──▶ TARGET ──▶ GENE ──▶ PATHWAY ──▶ PARKINSON'S DISEASE MECHANISM
```

| | |
|---|---|
| Library | `scripts/molecular_agent.py` |
| Pipeline stage | `scripts/08_molecular_pathway.py` |
| Tests | `tests/test_molecular_agent.py` (69), `tests/test_vps_integration.py` (24) |
| Data source | Open Targets Platform GraphQL API — **no authentication required** |
| Outputs | `data/molecular_pathway.csv`, `data/molecular_pathway_evidence.jsonl` |

---

## 1. Data source and why

All five legs of the chain come from one API, the
[Open Targets Platform](https://platform.opentargets.org/) GraphQL endpoint
(`https://api.platform.opentargets.org/api/v4/graphql`). It aggregates ChEMBL (drug
mechanisms), Ensembl (genes), Reactome (pathways) and curated gene–disease evidence, so a
single batched query answers the whole chain without downloading a bulk dataset.

**Every field used was verified by live probe before any code was written against it**
(API v26.9, data version 26.09, probed 2026-10-05). Two assumptions taken from memory were
wrong and were caught by probing:

- Parkinson's disease resolves to **`MONDO_0005180`**, not the commonly cited
  `EFO_0002508`.
- A ChEMBL ID recalled from memory for ropinirole (`CHEMBL1200539`) is actually
  **calcium carbonate**. All drug identity is now resolved at runtime; none is hardcoded.

DrugBank is not used and is not a blocker — ChEMBL mechanisms of action via Open Targets
supply the drug→target leg with references.

---

## 2. The chain, leg by leg

| Leg | Source | Field | Provenance captured |
|---|---|---|---|
| Drug → ChEMBL molecule | Open Targets search index | `mapIds` | match type, rejected candidates |
| Drug → Target | ChEMBL | `drug.mechanismsOfAction.rows[]` | `references{source, ids, urls}` (e.g. FDA label, PubMed) |
| Target → Gene | Ensembl | `targets[].id` | Ensembl gene ID + approved symbol |
| Gene → Pathway | Reactome | `target.pathways[]` | `pathwayId`, `pathway`, `topLevelTerm` |
| Gene → Disease | Open Targets associations | `associatedDiseases(Bs: [MONDO_0005180])` | per-datatype scores |

### Drug normalization is exact-match only

Open Targets name search returns ranked **fuzzy** neighbours. Querying `"Simvastatin"`
returns `SIMVASTATIN` *and* `PRAVASTATIN` *and* `FLUVASTATIN`. Taking `hits[0]` would
attribute one molecule's targets to another — a fabricated biological relationship.

A hit is accepted only when its name, synonym, or trade name is an exact match after
case/punctuation normalization. Otherwise the drug is reported **unresolved**, with the
rejected candidates listed in `limitations`. Enforced by
`test_normalize_rejects_fuzzy_nonidentical_match`.

---

## 3. Label-leakage control (the most important design decision)

Open Targets' headline target–disease `score` is a composite over `datatypeScores`. Two
datatypes must not be used by this project:

| Datatype | Datasource | Why excluded |
|---|---|---|
| `clinical` | `clinical_precedence` | Encodes that a drug hitting this target is already in clinical trials for PD. That is **effectively the EviRep ground-truth label**, and duplicates the clinical-maturity dimension. |
| `literature` | `europepmc` | Gene–disease co-mention counting. Duplicates the literature-independence dimension and is not cutoff-bounded. |

**The composite `score` field is never used.** The allowed datatype scores are
re-aggregated independently.

This is not a theoretical concern. Measured on live data:

```
ADORA2A → Parkinson disease
  OpenTargets composite score : 0.610
  clinical   (clinical_precedence) : 0.957   ← EXCLUDED
  literature (europepmc)           : 0.922   ← EXCLUDED
  permitted score                  : 0.000
```

ADORA2A is the target of istradefylline, an approved PD drug — exactly the leakage path
the exclusion blocks. Similarly, ropinirole (a real PD drug) gets a **direct component of
0.0**, because its DRD2/3/4→PD association is entirely `clinical` + `literature`. Its
score comes only from pathway overlap. The agent is therefore not re-deriving the label.

### Anti-circularity: a second, narrower allowlist

`affected_pathway` evidence is itself pathway-derived. If a gene entered the PD module on
that evidence and the pathway component then measured Reactome overlap against it, the
same annotation would be counted twice.

So there are **two** allowlists:

- `allowed_datatypes` — may contribute to the **direct** component (includes
  `affected_pathway`).
- `module_datatypes` — may put a gene **into the PD module** (excludes
  `affected_pathway`).

Found by inspecting a real run: ADORA2B entered the module on `affected_pathway`=0.437
alone, then matched caffeine through the irrelevant pathway *"Surfactant metabolism"*.
After the fix caffeine's pathway component fell 0.833 → 0.333. See
`development_log/ERRORS_AND_BLOCKERS.md` E-006.

---

## 4. Scoring

```
score = w_direct × direct_component  +  w_pathway × pathway_component
      = 0.6      × direct            +  0.4       × pathway
```

| Component | Definition | Range |
|---|---|---|
| `direct_component` | max over the drug's targets of that target's **permitted-datatype** PD association score | [0, 1] |
| `pathway_component` | (drug's target pathways containing ≥1 PD module gene) / (drug's target pathways) | [0, 1] |

**Weight rationale.** `direct > pathway` because a target that is itself PD-associated by
genetic / animal-model / somatic / expression evidence is stronger mechanistic support
than one that merely shares a Reactome pathway with a PD gene. The 60/40 split encodes
**only that ordering**.

> These weights were chosen **a priori**. No label-based search was run to select them.
> Tuning them against the EviRep ground truth would be label leakage. They are
> configurable (`--weight-direct`, `--weight-pathway`) specifically so sensitivity can be
> tested as an explicit, reported experiment.

`INFERRED` evidence (shared Reactome *top-level term* only) contributes **0**. Terms like
"Signal Transduction" span thousands of genes; counting them would manufacture signal.

Every record carries a readable derivation:

```
score = 0.6 x direct(0.4373) + 0.4 x pathway(2/6 = 0.3333) = 0.3957
```

### Score and confidence are separate axes

| | score 0.0 | score > 0 |
|---|---|---|
| **confidence 0.0** | could not look (unresolved drug / API down) | impossible |
| **confidence > 0** | looked, found no link | link found |

Collapsing these would turn "we don't know" into "we know it's not plausible".
`confidence` is the fraction of four availability checks that passed: drug resolved, has
targets, targets have pathways, disease module available.

---

## 5. Evidence tiers

| Tier | Meaning |
|---|---|
| `direct` | drug acts on target (ChEMBL MoA), **or** target is itself PD-associated via permitted datatypes |
| `indirect` | drug target shares a specific Reactome pathway with a PD module gene |
| `inferred` | shares only a broad Reactome top-level term — weak, non-mechanistic, **scores 0** |
| `missing` | no evidence retrievable; emitted explicitly, never silently dropped |

---

## 6. Output contract

```jsonc
{
  "drug": "Caffeine",
  "drug_normalized": "CAFFEINE",
  "chembl_id": "CHEMBL113",
  "disease": "Parkinson's disease",
  "disease_id": "MONDO_0005180",
  "targets":   [{"ensembl_id", "gene_symbol", "mechanism_of_action",
                 "action_type", "source", "references"}],
  "genes":     [{"ensembl_id", "gene_symbol", "gene_name", "source"}],
  "pathways":  [{"pathway_id", "pathway_name", "top_level_term",
                 "in_disease_module", "disease_module_genes_in_pathway", "tier"}],
  "disease_links": [{"gene_symbol", "score_allowed_datatypes",
                     "datatype_scores_used",
                     "datatype_scores_excluded_for_leakage",
                     "opentargets_overall_score_not_used"}],
  "mechanistic_chain": [{"step", "from", "to", "relation", "tier", "source"}],
  "molecular_plausibility_score": 0.395686,
  "confidence": 1.0,
  "scoring":   { "components", "weights", "detail", "explanation" },
  "evidence":  [{"tier", "claim", "source", "identifiers", "strength"}],
  "limitations": ["..."],
  "provenance": { "api", "url", "disease_module_*", "datatypes_excluded_for_leakage" }
}
```

`validate_output()` runs on **every** record and raises `MalformedEvidenceChain` on: a
missing key, a score outside [0,1], an evidence item without a `source`, an invalid tier,
a chain step without `step`/`tier`/`source`, or — importantly — **a non-zero score with no
direct or indirect evidence behind it**.

---

## 7. Running it

Always run from the repository root.

```bash
# offline: resolve the compound list, no API calls, no writes
./venv/bin/python scripts/08_molecular_pathway.py --dry-run

# small controlled sample (do this first)
./venv/bin/python scripts/08_molecular_pathway.py \
    --compounds "Ropinirole,Rasagiline,Isradipine,Caffeine" \
    --out data/sample_molecular_pathway.csv

# full cohort (resumable; re-running is nearly free thanks to the cache)
./venv/bin/python scripts/08_molecular_pathway.py
```

Useful flags: `--limit N`, `--input FILE`, `--fresh`, `--no-cache`,
`--weight-direct`, `--weight-pathway`, `--pd-module-size`.

### Request economy

- **Caching** — every response cached on disk under `data/cache/molecular/`, keyed by
  SHA-256 of (query, variables). Re-runs issue no network calls.
- **Batching** — names resolved 100/request; targets fetched 25/request; the PD module is
  built once per run, not once per drug.
- **Throttling** — 0.25 s floor between requests (≤4 req/s). Open Targets publishes no
  specific numeric rate limit, so no limit is asserted; this is a deliberately
  conservative self-imposed ceiling.
- **Backoff** — exponential with jitter on 429/5xx/network errors, honouring `Retry-After`.
  GraphQL *query* errors are not retried (they are defects, not transient).
- **Checkpointing** — `data/_molecular_checkpoint.jsonl`, append-only, same convention as
  scripts 04/05.

Measured on the 5-compound sample: 17 requests cold, then 5 requests + 10 cache hits.

---

## 8. VPS integration

Dimension 5 enters `scripts/06_vps_fusion.py` through a dimension registry
(`BASE_DIMENSIONS` / `ALL_DIMENSIONS`), percentile-ranked as `r_molecular` exactly like
the other four.

**Existing results are unchanged.** `VPS_equal`, `VPS_grid_4d` and `VPS_grid_3d` are
computed exactly as before; the 5-dimension variants are *additional* columns
(`VPS_equal_5d`, `VPS_grid_5d`, `VPS_molecular_only`) and an additional ablation file
(`data/ablation_results_5d.csv`). Asserted by
`test_four_dim_scores_identical_with_and_without_molecular`.

If `data/molecular_pathway.csv` is absent, step 06 prints a notice and runs the original
4-dimension analysis — the pipeline stays backwards compatible.

**Imputation.** A 0.0 produced by the agent is a real measurement and is left alone. Only
compounds *absent* from `molecular_pathway.csv` are NaN, and those are median-imputed to
match the convention the other four dimensions already use. The imputed count is printed,
not hidden.

---

## 9. Limitations (reported in every record)

1. **Not cutoff-bounded.** Open Targets serves a single current snapshot (26.09) with no
   as-of-date parameter, so evidence published after the project's 2021-01-01 cutoff is
   included. The two label-encoding datatypes are excluded, but residual *temporal
   optimism* remains. This is an **open blocker** — see
   `development_log/ERRORS_AND_BLOCKERS.md` B-001 and `TECHNICAL_DEBT.md` TD-006.
2. **`max` is not Open Targets' harmonic sum.** The official per-datatype weights are not
   exposed by the API, and inventing them would be fabrication. `max` is the
   conservative, interpretable choice; the full per-datatype breakdown is retained so any
   other aggregation can be recomputed without re-querying.
3. **Reactome only.** Pathway coverage comes from `Target.pathways`; KEGG and
   WikiPathways are not consulted.
4. **Pathway overlap is unweighted by pathway size or specificity** (TD-007).
5. **Co-membership is not mechanism.** A shared pathway does not establish that the drug
   modulates the disease process in the relevant direction.
6. **Pool inherited from scripts 04/05** — compounds with a pre-cutoff PD trial. A
   pre-existing property of the pipeline (TD-004), not introduced here.
