# TECHNICAL DEBT

Known issues in the EviRep repository that are **recorded, not fixed**.

Most of these predate the Molecular / Pathway Agent work (2026-10-05). They were
identified during a read-only audit and were deliberately left alone, because that session
was scoped to adding dimension 5 — not to reworking existing methodology. Items marked
**FIXED** were touched only because they directly blocked that work.

Severity: **HIGH** (affects published conclusions) · **MEDIUM** (affects correctness or
reproducibility) · **LOW** (hygiene).

---

## TD-001 · HIGH · Figure metrics were hardcoded — **FIXED**
`scripts/07_generate_figures.py` contained AUROC values as literals
(`[0.620, 0.728, 0.734, 0.721, 0.742, 0.742]` and `[0.742, 0.730, 0.730, 0.678, 0.707]`)
while script 06 wrote the same metrics to CSV. Figures could not reflect a rerun and would
silently diverge from the data.

**Fixed for figures 1 and 2 only**, because the molecular dimension could not otherwise be
plotted without hardcoding a new number — i.e. without fabricating a result. They now read
`data/baseline_results_v2.csv`, `data/vps_variant_results.csv`,
`data/ablation_results_v2.csv` and (when present) `data/ablation_results_5d.csv`, and exit
with a clear message if those are missing. Script 06 now also persists the VPS variant
metrics it previously only printed.

**Closed 2026-10-05:** all figures regenerated from the real corrected pipeline outputs.

## TD-002 · HIGH · Figure 3 was synthetic data presented as a case study — **FIXED 2026-10-05**
`figure3_droxidopa_graph()` generates a *random* graph (`np.random.rand() < 0.4`) with
hand-set `cluster_sizes = [8, 6, 5, 4, 3]` to mimic "26 papers → 5 clusters". The
docstring and stdout admit it is a reconstruction, but the rendered figure is titled as
the Droxidopa result.

It also showed **5** clusters where the real Droxidopa value is **16**, so it misstated the
result, not merely its appearance.

**RESOLVED.** `scripts/04b_export_literature_graph.py` re-derives the graph with stage 04's
own functions and refuses to write unless the derived counts match the stage-04 checkpoint
exactly (they did: 26 papers / 16 components / 4 author / 10 citation edges).
`figure3_literature_graph()` draws only from that persisted JSON and skips the figure
entirely if it is missing. No synthetic figure remains.

## TD-003 · HIGH · Weight selection in script 06 is not cross-validation — **FIXED 2026-10-05**
`cv_grid_search_weights()` splits with `StratifiedKFold` but **never uses `train_idx`** —
nothing is fitted. It scores fixed weights on each test fold, averages, then selects the
maximum over the whole labeled set. The comment claims "mean out-of-fold AUROC", but
because weight selection sees every fold, the reported figure is selected on the same data
it is evaluated on and is optimistically biased.

**RESOLVED.** `cv_grid_search_weights` now selects weights on the TRAINING fold and
evaluates on the held-out fold (genuine nested CV). The honest estimates are materially
lower than the previously reported leaky figures: 4-dim 0.706 → **0.631**, 3-dim
0.716 → **0.648**, 5-dim 0.743 → **0.660**. The final model's in-sample AUROC is retained
in the log as `selected_model_in_sample_auroc` and must not be reported as performance.
Equal-weight variants were never affected (no selection) and were not modified.
Regression tests: `TestGridSearchNoLeakage`.

## TD-004 · MEDIUM · Candidate-pool selection bias — **OPEN**
Scripts 04, 05 and `merge_dimensions` in 06 all key off
`clinical_maturity_precutoff_clean.csv`, so the evaluable pool is restricted to compounds
that **already had a pre-2021 PD trial**. Positives are therefore drawn almost entirely
from drugs already under PD investigation, inflating the clinical dimension's apparent
value and limiting any claim about discovering novel candidates.

Script 08 follows the same convention for consistency (and exposes `--input` to override
it). It does not add to the bias, but it inherits it.

## TD-005 · MEDIUM · No pipeline outputs exist in this working copy — **OPEN**
`data/` was empty at session start and `.gitignore` excludes `data/` wholesale, so no
output was ever committed. Stages 02–07 cannot run until stage 01 (155 MB Hetionet
download) and stage 03 (~1,500 API calls) are re-run. Consequently the molecular dimension
has **not** been evaluated against the real cohort — only against a 5-compound live sample
and synthetic integration fixtures.

## TD-006 · MEDIUM · Molecular dimension is not cutoff-bounded — **OPEN (blocker B-001)**
Open Targets serves a single current snapshot (data version 26.09) with no as-of-date
parameter, so evidence published after the 2021-01-01 cutoff is included. The two
label-encoding datatypes (`clinical`, `literature`) are excluded, which removes direct
label leakage, but residual temporal optimism remains.

Remedy requires a methodological decision: pin to an archived pre-2021 Open Targets
release and rebuild the module from it. Not taken autonomously.

## TD-007 · LOW · Pathway overlap is unweighted by specificity — **OPEN**
`pathway_component` counts a match in a broad Reactome pathway the same as a match in a
narrow one, so it can be driven by generic signalling/metabolic pathways. Mitigated in
part by excluding top-level-term-only matches from the score, but not fully. Weighting by
inverse pathway size (or an information-content measure) would be more principled and
needs one extra query per pathway.

## TD-008 · MEDIUM · `debug_step2.py` has the disease–gene edge direction inverted — **OPEN**
Line 34 filters `edges["target"] == PD_DISEASE_ID` for DaG/DuG/DdG and reads genes from
`source`. `scripts/02_network_proximity.py:114` correctly uses `source == PD_DISEASE_ID`
with genes in `target` (Hetionet DaG is Disease→Gene). The diagnostic will report 0 PD
genes and mislead anyone debugging stage 2. The production path is correct; only the
debug helper is wrong.

## TD-009 · MEDIUM · Script 04 fails silently into wrong numbers — **OPEN**
`fetch_citing_pmids()` returns an empty `set()` on any non-200 — including HTTP 429
rate-limiting — and a bare `except Exception` discards the cause. A throttled run loses
citation edges, which *raises* `effective_independent_count` and `independence_ratio`. The
failure mode biases the headline literature metric upward with no warning.

## TD-010 · MEDIUM · Exclusion filter was bypassed upstream — **FIXED 2026-10-05**
`00_exclusion_filter.py` writes `pd_candidates_filtered.csv`, but scripts 02 and 03 both
read the *unfiltered* `pd_candidates.csv`. The filter was applied only downstream, inside
`06_vps_fusion.py:merge_dimensions`.

### Quantified impact (measured against the real Stage 01/00 outputs)

| Measure | Value |
|---|---|
| `pd_candidates.csv` | 1,524 candidates |
| `pd_candidates_filtered.csv` | 1,483 candidates |
| Removed by the exclusion filter | **41** |
| Removed compounds that have Hetionet CbG targets (so stage 02 actually scored them) | **39** |
| Stage 02 compounds scored, unfiltered input | 1,361 |
| Stage 02 compounds scored, filtered input | 1,322 |
| Stage 03 unnecessary ClinicalTrials.gov query sets | up to **41** |

Excluded compounds: Adenine, Adenosine, Biotin, Caffeine, Calcidiol, Cholecalciferol,
Choline, Creatine, Cyanocobalamin, Folic Acid, Glutathione, Glycine, Hydroxocobalamin,
Iron, 16 L-amino acids, Niacin, Nicotine, Pyridoxal, Pyridoxine, Riboflavin,
S-Adenosylmethionine, Tetrahydrofolic acid, Thiamine, Vitamins A/C/E, Zinc.

**Downstream propagation.** Stages 04, 05 and 08 all read
`clinical_maturity_precutoff_clean.csv`, which descends from stage 03's output. Any
excluded compound with a pre-cutoff PD trial therefore consumed budget in stage 04 — the
most expensive stage in the pipeline.

### Was it producing wrong results?

**No.** `merge_dimensions` applies the filter *before* `impute_missing` and
`build_standardized_scores`, so medians and percentile ranks were always computed over the
already-filtered pool, and per-compound values in stages 02/03 are computed independently.
Excluded compounds never influenced a retained compound's score. The defect was wasted
compute and API budget, plus misleading stage-02 summary counts — **not** corrupted output.

### RNG note (important, and the reason timing mattered)

Stage 02 seeds `random.seed(42)` once in `main()` and consumes `random.choice` *inside* the
candidate loop. Changing the candidate list shifts the global RNG stream for every
subsequent compound. The first excluded compound with CbG targets sits at position 6 in
scored-iteration order (Cyanocobalamin), so **1,354 of 1,361 compounds would receive a
different random draw sequence** under the filtered input.

This is a stochastic re-draw, not a methodological change — the expectation is identical.
Because **no `data/network_proximity.csv` existed when the fix was applied**, there was no
prior run to diverge from, so this is **not a reproducibility regression**. The
filtered-input configuration is the correct baseline for the real run.

### Fix applied
- `scripts/02_network_proximity.py` — `load_data()` now reads
  `data/pd_candidates_filtered.csv`; module docstring corrected.
- `scripts/03_clinicaltrials_groundtruth.py` — `main()` now reads
  `data/pd_candidates_filtered.csv`.
- Regression test `tests/test_candidate_flow.py` (11 static tests, no data/network needed)
  asserts both stages read the filtered list, that neither references the unfiltered one,
  that 01/00/06 still honour the producer-consumer contract, and that `EXCLUSION_LIST` is
  non-empty.

Not recorded in `ERRORS_AND_BLOCKERS.md`: it was corrected before it produced any research
output, so it never caused an actual error.

## TD-011 · LOW · `N_RANDOM = 100` is the script's own "quick test" value — **OPEN**
`scripts/02_network_proximity.py:45`. Its comment recommends "1000+ for final
experiments". Any `proximity_z` behind existing figures is the low-precision setting.

## TD-012 · LOW · Missing `__main__` guards — **OPEN**
`check_groundtruth.py`, `debug_step2.py`, `filter_by_studytype.py` and `test_openfda.py`
execute on import. `filter_by_studytype.py` is the concerning one: it is a mandatory
pipeline stage that writes files as a side effect of being imported.

## TD-013 · LOW · Missing `os.makedirs("data")` in several scripts — **OPEN**
Scripts 00, 01 and 02 write to `data/` without creating it (03/04/05/08 do). They work
only because `data/` happens to exist; on a fresh clone it does not, since `data/` is
gitignored, and script 01 crashes at its first write.

## TD-014 · LOW · `safety_signal` boxed-warning detection is unreliable — **OPEN**
`scripts/05_safety_signal.py:31` uses `"boxed_warning" in label`, which is true whenever
the key exists even for an empty list, so the flag may fire on labels with no actual boxed
warning. It feeds `safety_risk` with a weight of `× 5` in script 06.

## TD-015 · LOW · Unnumbered scripts are mandatory pipeline stages — **OPEN**
`check_studytype.py` and `filter_by_studytype.py` must run between stage 03 and stages
04/05/06/08 — they are the only producers of `*_clean.csv`. Their position is implied by
nothing in their filenames. Now documented in `README.md`, but renaming them (e.g.
`03b_`, `03c_`) would make the ordering self-evident.

## TD-016 · MEDIUM · `NCBI_API_KEY` env var holds the placeholder `your_key` — **CODE HARDENED 2026-10-05; environment still unfixed**
The shell environment exports `NCBI_API_KEY='your_key'`. Because
`scripts/04_literature_independence.py` attaches the key whenever the string is truthy, a
placeholder value makes **every** PubMed request return HTTP 400, and the stage's bare
`except Exception` swallows it per compound — producing a silently empty literature
dimension rather than a visible failure.

Worked around for the 2026-10-05 run by clearing the variable so the script uses its
documented unauthenticated path. **Not fixed in the environment.** Either set a real key
(https://account.ncbi.nlm.nih.gov/settings/) or unset the variable.

**Code hardening applied 2026-10-05:** `_valid_api_key()` in script 04 rejects obvious
placeholders and keys shorter than 20 characters, printing a warning and falling back to
the documented unauthenticated path instead of sending an invalid key. The repository
default was already safe (empty string); the fragility was that *any* truthy string was
attached. Tests: `TestApiKeyPlaceholderGuard`.

**Still open:** the user's shell continues to export `NCBI_API_KEY='your_key'`. The guard
now prevents it from breaking stage 04, but a real key should be set or the variable unset.
See ERRORS_AND_BLOCKERS E-008.

## TD-017 · LOW · Molecular score cannot discriminate drugs sharing a target set — **OPEN (inherent)**
`molecular_plausibility_score` is a pure function of the drug's ChEMBL mechanism target
set, so any two drugs with identical annotated targets receive an identical score. Observed
on the real cohort: Zonisamide, Lidocaine, Quinidine, Riluzole and Lamotrigine all score
0.854442 (identical SCN1A-SCN11A target set); the ACHE inhibitors all score 0.748278; the
α1-adrenergics all score 0.702975.

This is correct behaviour for a target-based mechanistic score, not a defect — but it means
the dimension ranks *target sets*, not drugs, and cannot by itself separate members of a
pharmacological class. Potency, selectivity, CNS penetration and dose are not represented.
Any top-N reading of this dimension alone should be interpreted at class level.

## TD-018 · HIGH · ClinicalTrials.gov intervention-name collisions contaminate features AND labels — **FIXED 2026-10-05**
`scripts/03_clinicaltrials_groundtruth.py` verifies that a matched trial's *condition* is
Parkinson's but never that its *intervention* is the queried compound. ClinicalTrials.gov
expands `query.intr` by chemical class, prodrug/metabolite relation, pharmacological class
and excipient content.

Measured over all 451 (compound, trial) pairs of the 2026-10-05 run
(`scripts/check_intervention_match.py` → `data/intervention_match_check.csv`):

| | |
|---|---|
| Trial links with no intervention naming the compound | **177 / 451 (39%)** |
| Catch-all registry studies | 16 |
| Compounds with no naming trial at all | **60 / 178** |
| Evaluable pool affected | **48 / 141 (34%)** |
| Positive labels affected | **7 / 30 (23%)** |

Verified artefacts include `Phenol` → levodopa trials, `Norepinephrine` → droxidopa,
`Dopamine` → sarizotan/safinamide/pramipexole, `Mannitol` → droxidopa (excipient).
**Three of the top five ranked candidates are artefacts.**

Because positive labels are affected, this biased the AUROC measurements themselves.

### RESOLVED
Gate 2 (intervention identity) added to stage 03 via `scripts/intervention_matcher.py`;
policy documented in `docs/INTERVENTION_MATCHING.md`. After the fix and a clean rerun the
independent diagnostic reports unsupported links **7/252 (2.8%)**, down from 177/451 (39%),
and **every residual is an explained ChEMBL trade name/synonym — no unexplained collision
remains**. Evaluable pool 141 → 90; positives 30 → 17. See ERRORS_AND_BLOCKERS E-010,
E-011, E-012.

**Suggested fix (not applied):** add an intervention-name check mirroring the existing
`is_actually_pd()` pattern — accept a trial only when the compound name (or a known synonym,
e.g. via the molecular agent's ChEMBL synonym list) appears in the trial's `interventions`
or their `otherNames`. This changes the project's inclusion criteria and ground-truth label
set, so it is a methodological decision for the project owner. Re-running 03 → filters →
04/05/08 → 06 afterwards costs roughly 3 hours, dominated by stage 04.
See ERRORS_AND_BLOCKERS E-010.

## TD-019 · MEDIUM · Stage 03 has no checkpoint — **OPEN**
`scripts/03_clinicaltrials_groundtruth.py` holds all results in memory and writes once at
the end. A transient network outage therefore produces a *complete-looking* run whose audit
silently contains `API_FAILURE` rows (observed 2026-10-05: a local DNS failure left 84 of
1483 compounds unsearched, yet the stage printed "STEP 3 COMPLETE").

Mitigated by `scripts/03b_resume_failed_searches.py`, which re-queries only the failed
compounds and merges, so recovery costs ~2 minutes instead of a 25-minute rerun. The
underlying absence of incremental checkpointing (which stages 04/05/08 all have) is **not**
fixed. Adding an append-only JSONL checkpoint to stage 03 would remove the failure mode.

## TD-020 · LOW · Statistical power is insufficient to separate VPS variants — **OPEN**
The corrected dataset has **17 positives in 90 compounds** (prevalence 0.189). Bootstrap
95% CIs on AUROC span roughly ±0.15 for every variant, and the paired comparison of
equal-weight 5-dim against equal-weight 4-dim gives **+0.059, 95% CI [-0.024, +0.150],
P(diff>0)=0.918** — suggestive but **not statistically significant** (reproduced
2026-10-05 evening, 2000 bootstrap resamples, seed 42).

A wider pool is NOT available without changing the study design: 1,314 compounds have
network-proximity scores, but only 90 satisfy the design's requirement of a verified
pre-cutoff PD trial. Expanding the pool would redefine the cohort and was therefore not
done.

No claim of improvement from the molecular dimension is supportable at this sample size.
Enlarging the evaluable pool (see TD-004) is a prerequisite for any such claim.
