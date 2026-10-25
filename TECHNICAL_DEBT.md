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

## TD-008 · MEDIUM · `debug_step2.py` has the disease–gene edge direction inverted — **FIXED 2026-10-19 (C-89)**
Now filters `source == PD` and reads genes from `target` (637 PD genes, was 0), as stage 02 does; `tests/test_debug_step2.py`.

Line 34 filters `edges["target"] == PD_DISEASE_ID` for DaG/DuG/DdG and reads genes from
`source`. `scripts/02_network_proximity.py:114` correctly uses `source == PD_DISEASE_ID`
with genes in `target` (Hetionet DaG is Disease→Gene). The diagnostic will report 0 PD
genes and mislead anyone debugging stage 2. The production path is correct; only the
debug helper is wrong.

## TD-009 · MEDIUM · Script 04 fails silently into wrong numbers — **OPEN**
**Update 2026-10-21 (final release audit): fixed in code; the text below is historical.** `fetch_citing_pmids()`
now retries (`S2_MAX_RETRIES = 5`, i.e. up to 6 attempts; Retry-After honoured), treats only 404 as "no citations", raises `SemanticScholarUnavailable`
otherwise, counts failures per compound and exits 1 on any failure (`scripts/04_literature_independence.py:123-178`,
:319-321). The saved `data/literature_independence.csv` records `citation_lookup_failures` 0 and
`citation_coverage_complete` True for all 90 pool compounds, so the upward bias described below is not present in the
current data. Status left OPEN for the owner to close.

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

---

## 2026-10-12 additions

Likelihood/impact are not part of this register's existing convention; severity follows the
HIGH / MEDIUM / LOW scale above. "Owner" is not defined in this repository and is left unset.
Every item below was found by inspection or computation in this session; none has been fixed
unless it says **FIXED**.

### TD-020 addendum (2026-10-12) — CI provenance not reproducible
Recomputed on the persisted `data/vps_scores_v2.csv` (90 rows, 17 positives): AUROC
VPS_equal_5d **0.7474**, VPS_equal **0.6886**, paired difference **+0.0588**, AUPRC
VPS_equal_5d **0.4790** — all match the historical values. The paired bootstrap (2000
resamples, seed 42, percentile CI) gives **[-0.0241, +0.1456], P(diff>0)=0.913** with
`np.random.default_rng(42)` and **[-0.0252, +0.1507], P=0.9085** with `RandomState(42)`.
Neither reproduces TD-020's `[-0.024, +0.150], P=0.918` or CASE_STUDIES' `[-0.025, +0.148]`
exactly, and no bootstrap script exists in the repository, so the original procedure cannot
be established. **Every variant's interval includes zero — the conclusion (not significant)
is unchanged.** Remedy: commit the bootstrap as a script and quote its output only.

### TD-021 · HIGH · Literature dimension is not cutoff-bounded and is a truncated, recency-ordered sample — **OPEN**
**Update 2026-10-21 (final release audit; nothing published):** the *composition* of the stage-04 sample is itself
associated with the label. The share of post-cutoff papers in each compound's sample (stage 04p) alone gives AUROC
**0.722** against the label (positives median 0.71 vs negatives 0.40; Mann-Whitney p = 0.009, n = 90, 14 positives).
No stored record in the sample carries a label-trial NCT ID, so this is indirect leakage (post-2020 research activity
tracks later trials), not a copy of the label. Evidence: `docs/final_release_20261022/SCIENTIFIC_AUDIT.md`.


**Update 2026-10-19 (C-79, C-83): provenance persisted; scoring unchanged.** Stage 04p now persists, for all 90
compounds, the PMIDs, DOIs, dates (with precision), cutoff status, duplicates and truncation behind the stage-04 query
(`data/literature_papers.jsonl`, `data/literature_provenance.csv`). Measured: 40 of 90 samples are truncated; median
43% of each sample is post-cutoff; 15 compounds' re-queried sample size differs from the stage-04 count (book chapters
not parsed by stage 04, plus new papers). Replacing the literature dimension with cutoff-bounded measures changes 5D
AUROC by −0.019 [−0.067, 0.030] (count) and −0.027 [−0.073, 0.016] (shared-author components):
the leakage is real but does not drive the result. The VPS literature dimension itself is unchanged (owner decision).
`scripts/04_literature_independence.py:59` searches
`"<compound>"[Title/Abstract] AND "Parkinson Disease"[Title/Abstract]` with `retmax=30`
and **no publication-date bound**. Measured for Droxidopa (2026-10-12 PubMed re-query, 7 NCBI
requests): the query now matches **90** records; the persisted graph holds **26** (the 30
first-returned hits minus 4 book chapters that `fetch_paper_details` does not parse —
inferred, since the run-time esearch response was not stored). **18 of the 26 are
post-cutoff (2021+)** although 67 of the 90 matching records are pre-cutoff, and **none of
the pivotal droxidopa RCTs** (e.g. PMIDs 24944260, 25350981, 24326693, 25487613) is in the
sample. The literature feature therefore (a) uses post-cutoff publications — temporal
leakage into a feature the design treats as pre-cutoff, and (b) describes the most recent
~30 papers, not the compound's PD literature. Affects every compound with >30 hits.
Remedy needs a methodological decision (add `maxdate` = cutoff, sort, raise the cap) and a
stage-04 rerun (hours). Not changed.


**Addendum 2026-10-15: dry-run plan for cutoff-bounded re-retrieval (not launched).**
- **Bound:** `search_pmids(max_date="2020/12/31")` bounds PubMed `pdat`. It still keeps only the 30
  first-returned hits, so the result is "the 30 most recent pre-cutoff papers", which is still
  a truncated sample. Raising the cap or changing the sort is a separate decision.
- **Workload for 90 compounds:**
  - NCBI: 90 esearch + 90 efetch = 180 requests, about 1–2 min at 0.34 s each without a key.
  - Semantic Scholar: citation lookups of up to 30 papers per compound, so ≤2,700 requests at
    `S2_SLEEP` 1.1 s. That is ≥50 min, and realistically 1–2 h because the API throttled before
    (`literature_independence_THROTTLED_EVIDENCE.csv`).
- **Caching:** the run must write a **separate** checkpoint and output, never
  `data/_literature_checkpoint.jsonl`, which holds 141 lines of the unbounded run. It should
  store each raw esearch/efetch response plus the query and date, so the run can be replayed.
- **Missing data:** compounds with 0 pre-cutoff hits become missing rather than 0, as in TD-031.
  Semantic Scholar failures are already counted as missing, not as zero edges.
- **Reproducibility:** PubMed indexing and citation data change over time, so a re-query in a
  later year is not an exact historical snapshot. Citation edges come from today's
  citation graph, although both papers in an edge would be pre-cutoff.
- **Approval needed:** whether to launch, the cap and sort policy, and whether stage 06 should
  read the bounded output.

### TD-022 · MEDIUM · Safety dimension uses current openFDA labels and missed a documented signal — **OPEN**

**Update 2026-10-19 (C-85, C-88): label at the cutoff measured; scoring unchanged.** Stage 05h follows each current
label's set ID through DailyMed's version history and scores the version published on or before 2020-12-31 with
stage 05's rule (parser agrees with stage 05 on 83/83 current labels). 31 labels scored at the cutoff (10 changed since);
52 set IDs start after 2020 (UNKNOWN at the cutoff, not "no label"); 7 have no current label. Replacing the safety
dimension with the label at the cutoff changes 5D AUROC by −0.003 [−0.012, 0.006] (current label kept where unknown)
or −0.007 [−0.079, 0.071] (unknown as neutral). Alternate set IDs (other products of the same drug) were not used:
DailyMed name search mixes formulations and OTC products.
`scripts/05_safety_signal.py` reads the current label (no as-of date), so it is not
cutoff-bounded. Separately, Domperidone scores `boxed_warning=False`,
`serious_term_count=0`, while a 214,962-patient PD cohort (PMID 27062307) reports increased
ventricular tachyarrhythmia / sudden cardiac death risk in patients with cardiovascular
history (RR 1.38, 95% CI 1.07–1.78). Domperidone is not FDA-approved in the US, so an
openFDA-based signal is structurally blind to it. Not changed.


**Addendum 2026-10-15 (D-003):** the v1 stage read only `warnings`, so PLR-format labels
(4/5 probed; 55 of 83 labelled pool compounds have `warnings_and_cautions`) scored 0. Fixed and re-queried:
90 requests, checkpoint `data/_safety_checkpoint_v2.jsonl`, raw labels in `data/cache/openfda_labels/`.
Labelled compounds with zero terms: 52 → 16. **Still OPEN:** labels are current (effective
2018–2026), `limit=1` picks an arbitrary product label, and term counting is crude.

### TD-023 · MEDIUM · Gate 2 checks intervention identity, not role or therapeutic intent — **OPEN**
Found during the 2026-10-12 case-study verification (registry records fetched live):
- **Background-therapy match:** NCT00605683 (MOTION, n=679) is a *safinamide* trial; lisuride
  appears only in the list of permitted background dopamine agonists, yet it is accepted
  (`token_othername`) and is Lisuride's phase-3 entry in
  `clinical_maturity_precutoff_clean.csv`. Recorded as E-014.
- **Active comparator / co-medication:** Domperidone's NCT03022201 (active comparator to
  DA-9701) and NCT00006077 (co-administered with levodopa; study drug NS2330) count toward
  `n_trials`.
- **Procedural context:** every Propofol trial uses it for anaesthesia/sedation (mostly DBS
  surgery), giving it `max_phase_rank` 5 from a phase-4 sedation comparator (NCT02256319).
  Dexmedetomidine (label 1) shares NCT02256319 and has **not** been checked.
- **Trade-name alias gap:** NCT00165815 (intervention "ARICEPT") is NO_MATCH for Donepezil
  (pre-cutoff; label unaffected).
- **Study-type filter:** `filter_by_studytype.py` drops DIETARY_SUPPLEMENT-typed trials, e.g.
  melatonin NCT05307770 (post-cutoff) — the regulatory type, not the trial content, decides.
None changes a label among the seven candidates verified, but they distort clinical
maturity. Fixing any of them changes inclusion criteria → owner decision. Not changed.

### TD-024 · MEDIUM · No-target compounds enter VPS as a measured molecular 0.0 — **FIXED 2026-10-15 (D-004)**
16 of 90 compounds have no ChEMBL mechanism target (confidence 0.5, agent text "evidence
ABSENT"). `impute_molecular` (06) only imputes compounds missing from the CSV, so these 16
(2 positives) are fused as a real 0.0. Sensitivity (audit, in memory, no file written):
median-imputing them moves VPS_equal_5d AUROC 0.747 → 0.753 and molecular-only
0.630 → 0.612. A methodological choice, previously undocumented. Not changed.


**Addendum 2026-10-15 (14-positive labels, in memory):** median-imputing the 16 no-target compounds
moves VPS_equal_5d AUROC 0.781 → 0.794. The paired difference is +0.012, 95% CI
[−0.026, +0.063], so the choice is not significant. Molecular-only moves 0.637 → 0.630. Not changed.


**Fixed 2026-10-15 (D-004):** `n_targets == 0` → `molecular_evidence_missing`, neutral rank 0.5.
The raw 0.0 is kept. Test: `TestNoTargetMolecularIsMissing`.

### TD-025 · LOW · Ablation compares an in-sample fitted reference with equal-weight leave-one-out bars — **FIGURE LABELLED 2026-10-12; method OPEN**
`run_ablation` (06) scores the reference with grid-searched weights fitted on all labelled
data (in-sample) and each "Without X" with **equal** weights over the remaining dimensions,
so bar differences mix re-weighting with removal; in the 5-dim figure the in-sample
reference (0.730) is below the unfitted VPS_equal_5d (0.747). `07_generate_figures.py` now
hatches the reference, suffixes "(in-sample)" and states the weighting on the figure.
Figures 2 / 2-5d regenerated (previous PNGs kept in the session scratchpad). The persisted
ablation metrics were not changed.

### TD-026 · LOW · Literature-graph provenance guard checks counts, not edges — **OPEN**
Stage 04 persists only aggregate counts; `04b_export_literature_graph.py` compares
re-derived counts to them, so a different edge set with identical counts would pass.
`fetch_paper_details` also truncates titles at inline markup (PMID 41520443) and skips
collective authors (PMID 39441810: 10 vs 11). Neither affects current edges. Not changed.

### TD-027 · MEDIUM · The evaluable pool silently excludes compounds whose first PD trial is post-cutoff — **OPEN (extends TD-004)**
`merge_dimensions` keys the pool on accepted **pre-cutoff** trials, so a compound with only a
post-cutoff accepted trial is never labelled. Example: Propranolol — NCT07113015
(propranolol vs amantadine for PD tremor, first posted 2025-08-08) is MATCHED and in
`ground_truth_postcutoff_clean.csv`, but Propranolol has no accepted pre-cutoff trial (its
only pre-cutoff link, registry NCT02670161, lists it for migraine) and is absent from the
pool. "Newly trialled" candidates — the target of a repurposing study — are therefore
structurally unevaluable. Design decision for the owner. Not changed.

### TD-028 · LOW · Stage 08 `--fresh` emitted stale checkpoint records — **FIXED 2026-10-12**
`--fresh` skips reading the checkpoint but appends to it, and the collect step kept the
FIRST record per drug, so a fresh rescore wrote the old result. Collect now keeps the LAST
record. Current outputs are unaffected (the checkpoint holds no duplicate drug). See E-013;
regression test `TestStep08FreshRun`.

## 2026-10-13 additions

### TD-029 · MEDIUM · Dashboard leaked local paths, accepted any Host header and any bind address — **FIXED 2026-10-13**
Security/accessibility audit of `ui/` (each item reproduced before the fix, regression test
in `tests/test_ui.py::TestSecurityHardening` / `TestAccessibleContrast`):
- **Path disclosure (MEDIUM):** unreadable artefacts/docs returned the OSError message
  (absolute path incl. username) and the 500 handler returned `str(exc)`. Now only the
  exception class is sent; details go to the server console. Every JSON string is also passed
  through `sanitize()` (repo root → `<repo>`, `/Users|home/<name>` → `/Users/<user>`).
- **Non-loopback bind (MEDIUM):** `--host 0.0.0.0` silently listened on all interfaces
  (unauthenticated). `main()` now refuses any host other than `127.0.0.1` / `localhost`.
- **DNS rebinding (MEDIUM):** any `Host` header was served, so a hostile web page rebound to
  127.0.0.1 could read every endpoint. Non-loopback Host headers now get 403.
- **Query-steered file read (LOW):** the literature-graph path was built from the raw
  `?name=`; with any `data/literature_graph_*` directory present, `x/../../f` read `f.json`
  outside `data/`. The path now comes from the artefact's own compound name and a slug
  whitelist. `/figure/` additionally rejects symlinks resolving outside `data/`.
- **Headers / methods (LOW):** CSP allowed `'unsafe-inline'` script; no `nosniff`,
  frame-ancestors or referrer policy; `Server` advertised the Python version; HEAD/OPTIONS
  returned the stdlib HTML 501 page without security headers. JS/CSS moved to
  `ui/app.js` / `ui/style.css`; CSP is now `default-src 'none'` with `'self'` only; all
  non-GET methods → JSON 405; stdlib error pages replaced by JSON.
- **Strict JSON (LOW):** NaN/Infinity from a persisted JSON file were emitted as invalid JSON;
  now `null` (`allow_nan=False`).
- **Frontend (functional/a11y):** the Drug Explorer attached its list/search listeners in a
  `setTimeout` that fired before the awaited HTML was inserted, so the compound list and
  search never rendered; malformed `%`-escapes in the hash left the page stuck on "Loading…";
  list items were click-only `<div>`s; dark-mode status badges had 2.0–2.7:1 contrast and
  light-mode warning text 4.1–4.4:1 (WCAG AA needs 4.5). All fixed; list items are links,
  nav has `aria-current`, skip link, visible focus ring, stale-render guard.
No scientific label, score, cohort or pipeline file was touched.

### TD-030 · LOW · Residual dashboard risks (not fixable without changing the design) — **OPEN**
- **No authentication.** Any process or user on this machine can read every endpoint while
  the server runs (data are research artefacts and public-registry records, no credentials).
- **Redaction is pattern-based.** It catches `NAME=value` key/token/secret/password forms,
  `api_key=` URLs, PEM private keys and home-directory paths; a credential in another shape
  inside a doc or artefact would be shown.
- **Not visually verified in a browser** (L-003). Layout at desktop/mobile width,
  screen-reader behaviour and real keyboard flow are unverified; behaviour was checked by
  running `ui/app.js` in Node against the live server.
- `::1` is accepted in the Host header but the server binds IPv4 only.

### TD-020 addendum 2 (2026-10-13) · bootstrap procedure now versioned
`scripts/bootstrap_auroc_ci.py` (paired percentile bootstrap over compounds,
`numpy.random.default_rng(42)`, 2000 resamples, single-class resamples counted) gives
VPS_equal_5d − VPS_equal = **+0.0588, 95% CI [−0.0241, +0.1456]**, P(diff>0) 0.913, identical
on repeat runs; with 10,000 resamples [−0.0257, +0.1502]. The documented [−0.024, +0.150]
lies within this Monte-Carlo variation. Conclusion unchanged: not significant. Tests:
`tests/test_bootstrap_ci.py` (7).

## 2026-10-13 research sprint additions

### TD-031 · HIGH · "No openFDA label" was scored as zero safety risk — **FIXED 2026-10-15 (D-004)**
**Note 2026-10-21:** the "median" convention described in the Fix bullet was superseded by D-004: unlabelled safety
now receives the neutral rank 0.5 (`06_vps_fusion.py:254, 302`), as the closing bullets of this entry state.

- **Finding (persisted data):** `05.score_safety(None)` wrote `serious_term_count=0`,
  `boxed_warning=False`; 06 inverted the rank, so 7/90 pool compounds with no label
  (Agomelatine, Domperidone, Lisuride, Nabilone, Ursodeoxycholic acid, Yohimbine, Zopiclone;
  all label 0) received the pool-maximum `r_safety` 0.717.
- **Fix:** 05 now records no label as null; 06 `mask_unlabelled_safety()` blanks no-label
  rows (legacy zeros and new nulls alike) and adds `safety_label_missing`. Missing values
  then follow 06's existing convention (`impute_missing`, median). Tests:
  `tests/test_safety_missingness.py` (15; 8 fail on the pre-fix code).
- **Effect on current results: none.** The pool's median `serious_term_count` is 0, so
  median imputation lands on the same (best) rank. Old and new 06 run in scratch copies:
  every persisted metric file byte-identical; `vps_scores_v2.csv` gains only the flag column.
  So the fix makes missingness explicit but does **not** stop "missing" ranking level with
  "safest" on this data.
- **Open owner decision:** keep median, or leave safety out for unlabelled compounds and
  average the remaining dimensions (computed in memory: VPS_equal 0.697, VPS_equal_5d 0.753
  AUROC vs 0.689 / 0.747), or another rule. Persisted outputs were not regenerated.


**Re-verification 2026-10-15 (persisted 14-positive data): defect CONFIRMED, policy still OPEN.**
- 50/90 compounds have risk 0: 43 labelled with no matched serious term, plus the 7 unlabelled.
  The median risk is therefore 0.
- All 50 share r_safety **0.717**, which is the pool maximum (ties are averaged). An unlabelled
  compound is thus scored exactly as safe as the safest measured ones.
- Unlabelled ranks under VPS_equal_5d: Domperidone 5, Lisuride 9, Agomelatine 29, Yohimbine 34,
  Nabilone 42, Ursodeoxycholic acid 72, Zopiclone 78.
- Options, computed in memory (AUROC 4d / 5d):

  | Option | 4d | 5d |
  |---|---|---|
  | A — current median rule | 0.724 | 0.781 |
  | B — leave safety out for unlabelled compounds | 0.731 | 0.785 |
  | C1 — neutral rank 0.5 | 0.736 | 0.787 |
  | C2 — rank among labelled only, missing = their median | 0.724 | 0.781 |
  | C3 — worst observed rank | 0.753 | 0.804 |

- **Caution:** all 7 unlabelled compounds are negatives, so every rule that downgrades
  "missing" raises AUROC by construction. The rule must be chosen on principle (B or C1
  are the defensible ones), not by its AUROC.
- **Unverified measurement concern:** `score_safety` reads only the label's `warnings` and
  `boxed_warning` fields. Newer-format labels put warnings in `warnings_and_cautions`, which
  would make `serious_term_count=0` an artefact. Raw labels are not cached, so this cannot be
  checked offline. Checking it needs one openFDA request per labelled compound.


**Fixed 2026-10-15 (DECISIONS D-004).** Unmeasured safety now gets the neutral rank 0.5;
measured compounds are ranked among themselves; `dimensions_missing` and
`n_dimensions_measured` are persisted. The available-case alternative was implemented and
rejected because Lisuride rose to rank 1 on 3/5 dimensions. Regression tests are in
`TestFusionSafetyMissingness`. The rule is a convention (moderate confidence), not a measurement.

### TD-032 · HIGH · Post-cutoff labels include procedural and non-repurposing trials — **policy P1 APPLIED 2026-10-14; feature-side re-audit OPEN**
Role audit of all 24 label-defining trials (CASE_STUDIES.md §9; annotator
`scripts/trial_role.py`, diagnostic only): Dexmedetomidine and Remifentanil are positive only
through DBS-surgery anaesthesia trials; Clozapine only as the actuator of a chemogenetic gene
therapy; Lidocaine only as the agent of stellate-ganglion blocks (ambiguous); Pyridostigmine's
trial is undetermined by rule. Extends TD-023 from features to **labels** (the 2026-10-12 note
"none changes a label among the seven verified" remains true for those seven). Sensitivity
(labels unchanged): AUROC rises (5d 0.747 → 0.773–0.781) and AUPRC falls (0.479 → 0.435–0.439),
so this is a validity problem, not a one-directional bias. Redefining labels by role, and
re-auditing the pre-cutoff feature links the same way, need owner approval.

**Addendum 2026-10-14 (per-label adjudication, CASE_STUDIES §9.1):** 12 CONFIRMED (incl. Pyridostigmine by manual review), 3 REJECTED (Dexmedetomidine, Remifentanil, Clozapine), 2 UNRESOLVED (Lidocaine: ganglion block; Galantamine: BASIC_SCIENCE pre-post sub-cohort, newly flagged). Policy options P0–P3x with bootstrap CIs are in §9.1; under every option the 5d−4d AUROC CI includes 0. Two decisions remain: (a) whether rejected labels become 0 or are excluded; (b) whether the two unresolved labels stay. **Still OPEN: no label changed.**

**Decision and application 2026-10-14:** owner approved **P1**: the 3 rejected labels → 0; Lidocaine and Galantamine stay positive. Implemented as a per-trial exclusion list `data/label_role_exclusions.csv`, read by `apply_label_exclusions()` in `06_vps_fusion.py`. `ground_truth_postcutoff_clean.csv` is unchanged. Prior outputs are in `data/_archive_pre_td032_2026-10-14/` (MD5SUMS match the sprint baseline). Stage 06 was rerun: 14/90 positives; AUROC 4d 0.724, 5d 0.781. Nested-CV of the grid variants: 4d 0.631→0.560, 3d 0.648→0.686, 5d 0.660→0.717. 5d−4d +0.058 [−0.038, +0.159] (2000 resamples), or [−0.041, +0.164] with 10k resamples, so it is not significant. Still open: (i) the two kept labels are contested; (ii) pre-cutoff **feature** trial links have not been role-audited (TD-023); (iii) stage-07 figures are stale. This entry is not resolved.

### TD-033 · HIGH · Temporal validity by dimension (audit 2026-10-13) — **OPEN**
**Update 2026-10-21 (final release audit; nothing published): all dated inputs combined.** Equal-weight 5D with
every input dated before the cutoff where a dated source exists (proximity and clinical as approved; literature =
04p cutoff-bounded primary count; safety = 05h label at the cutoff; molecular = Open Targets 20.11 + ChEMBL 2020-06):
AUROC **0.689 [0.548, 0.819]** (safety: current label where no pre-cutoff version) / 0.685 [0.528, 0.832] (strict),
AUPRC 0.334, versus approved 0.775; paired difference -0.087 [-0.206, 0.030]. Reproduce:
`docs/final_release_20261022/experiments/release_experiments.py` (outputs in `experiments/out/`).


**Update 2026-10-20 (C-95): the full molecular dimension rebuilt from Open Targets 20.11 inputs (nothing published).**
`scripts/vps_molecular_historical.py` applies stage 08's rules unchanged (top-300 module, module datatypes >= 0.10,
allowed-datatype direct max, Reactome pathway fraction, 0.6/0.4) to the PD association rows and the UniProt
2020-11-10 Reactome cross-references that 20.11 itself was built from. The method check rebuilds the 26.09
pathway component exactly. Reactome membership barely changed (262/307 drug-target pairs identical; the rest
differ by about one pathway), so the drift is in Open Targets' PD evidence: module genes and association scores
(Spearman 2020 vs published molecular 0.26).
| Model | AUROC [95% CI] | d vs same model with 26.09 |
|---|---|---|
| 5D approved, molecular at 20.11 | 0.690 [0.550, 0.824] | -0.086 [-0.186, 0.020] |
| 5D TD-042, molecular at 20.11 | 0.690 [0.552, 0.825] | -0.009 [-0.087, 0.071] |
| molecular alone at 20.11 | 0.516 [0.340, 0.682] | -0.111 [-0.353, 0.143] |
| 5D approved, molecular at 20.11 + ChEMBL 2020-06 targets (every input dated) | 0.704 [0.573, 0.831] | -0.071 [-0.173, 0.030] |
| 5D TD-042, molecular at 20.11 + ChEMBL 2020-06 targets (every input dated) | 0.703 [0.571, 0.831] | +0.004 [-0.065, 0.082] |
Dated targets: 70 drugs have a human 2020-06 mechanism target (74 today); 62 have the identical target set.
The approved 5D advantage over 4D (0.775 vs 0.700) does not survive a pre-cutoff molecular dimension: with every
molecular input dated before the cutoff, 5D equals 4D under either rule. Open Targets scoring methods changed
between releases, so temporal and method effects are not separable.

**Update 2026-10-19 (C-79, C-83, C-85, C-87): each dimension's temporal sensitivity measured (nothing published).**
| Dimension | Cutoff-bounded source | Effect on 5D AUROC (paired bootstrap, 2000) |
|---|---|---|
| literature | stage 04p, papers published <= cutoff | −0.019 [−0.067, 0.030] |
| safety | stage 05h, DailyMed label version <= cutoff (31/83) | −0.003 [−0.012, 0.006] |
| molecular (direct component only) | Open Targets 20.11 (Nov 2020) vs 26.09, same formula | −0.086 [−0.169, −0.011] |
The molecular effect is the only one whose interval excludes 0. It mixes newer evidence with Open Targets method
changes between releases (new datatypes such as genetic_literature, MONDO vs EFO disease IDs), so it is an upper
bound on leakage, not a clean estimate; the pathway component could not be rebuilt for 2020 (gene sets not persisted).
| Dimension | Cutoff enforced? | Evidence | Can it be enforced from persisted data? |
|---|---|---|---|
| Proximity | yes (by construction) | Hetionet 2017 | — |
| Clinical (feature + label) | **yes** | pre max `first_posted` 2020-11-25; post min 2021-01-13; 0 violations | — |
| Literature | **no** (TD-021) | no per-paper dates persisted; Droxidopa 18/26 post-cutoff | no — needs re-retrieval; opt-in `search_pmids(max_date=…)` prepared, not wired into `main()` |
| Safety | **no** (TD-022) | current openFDA labels; no label date persisted | no — needs re-query against label versions |
| Molecular | **no** (B-001/TD-006) | all 90 records Open Targets snapshot 26.09 | no historical snapshot available |
Confirmed leakage: literature (Droxidopa). Residual/unknown: literature for 89 compounds,
safety and molecular for all. The retrospective evaluation is **not** leakage-free.


**Status per dimension (2026-10-15; cutoff = trials first posted ≤ 2020-12-31, i.e. `< "2021-01-01"`):**

| Dimension | Status | Evidence |
|---|---|---|
| Network proximity | **Cannot verify from artifacts** (bounded by documentation) | `data/hetionet_edges.csv` is a local file; the docs describe it as Hetionet v1.0 (2017), but no version or checksum is recorded with the file |
| Clinical maturity | **Partially bounded** | inclusion is by `first_posted` (max 2020-11-25; 0 pre/post NCT overlap), but phase and other fields come from today's registry record |
| Literature | **Not cutoff-bounded** | TD-021 |
| Safety | **Not cutoff-bounded** | current openFDA label, no version date (TD-022) |
| Molecular | **Not cutoff-bounded** | Open Targets 26.09 snapshot |
| Labels | Bounded at the start only | first_posted 2021-01-13 … **2026-09-08**; the window's end is the retrieval date, not a fixed date, so a rerun would add positives |

### TD-034 · LOW · Stages 05 and 06 ignore command-line arguments — **FIXED 2026-10-15**
`05_safety_signal.py --help` and `06_vps_fusion.py --help` run the full stage (no argparse).
This caused incident E-017. Adding a parser is safe but was left for review.
**Fix 2026-10-15:** an option-free `argparse` guard now runs in the `__main__` block of the 10
pipeline scripts that lacked one (00–07, `check_studytype`, `check_intervention_match`).
`--help` exits 0 and an unknown flag exits 2, both before any work. Run behaviour is
unchanged. Regression test: `tests/test_pipeline_safety_contracts.py::TestHelpDoesNotRunStages`
runs each script with `--help` in an empty temp dir behind an unroutable proxy and asserts
that no file is written. Note: 03, 04 and 05 still create an empty `data/` directory at import.

### TD-035 · HIGH · The evaluation endpoint is "another PD trial after the cutoff", and the pool requires a prior PD trial — **OPEN (owner decision)**
`merge_dimensions` builds the pool from compounds with an accepted **pre-cutoff** PD trial (90).
The label is the existence of an accepted **post-cutoff** PD trial (minus TD-032 exclusions).
So the endpoint is trial existence and **continuation** of clinical interest. It is not efficacy
and not first-time repurposing; 24 of the 41 ground-truth compounds are outside the pool
(TD-027). The clinical-maturity feature and the label both come from the same registry and
query, which favours the clinical dimension (largest ablation drop). A negative means only
that no qualifying trial was found up to the retrieval date. Recommended: a written,
pre-specified label policy (draft in CASE_STUDIES §9.2) before any further tuning.


**Decision 2026-10-15 (D-010, D-013):** the continued-investigation endpoint is retained
and frozen to the 2026-10-05 registry snapshot. First-time repurposing is recorded as a
separate question (RQ-2). It needs a new pool and its own label audit and is not part of this
cohort. This entry stays OPEN as a scope limitation, not a defect.

### TD-036 · MEDIUM · Nested-CV estimate comes from a single 5-fold split — **OPEN (reporting)**
`cv_grid_search_weights` reports the mean over one StratifiedKFold split (seed 42; about 3
positives per test fold). Selection happens on training folds only (verified;
`TestGridSearchSelectsOnTrainingFoldsOnly`). Percentile ranks and median imputation are computed
once on all 90 compounds; this uses no labels, but it is transductive. Repeating the split 20
times (seeds 0–19, in memory) gives held-out AUROC **4d 0.636 [0.539, 0.686]; 3d 0.669
[0.545, 0.754]; 5d 0.710 [0.569, 0.816]**, versus the persisted single-split 0.560 / 0.686 /
0.717. The persisted figure is one draw from a wide distribution. Suggest reporting
repeated nested CV. Not changed.

**Update 2026-10-15 (after D-003/D-004):** single split 4d 0.607, 3d 0.584, 5d 0.639; 20 repeats
4d **0.574 [0.459, 0.679]**, 3d **0.571 [0.450, 0.654]**, 5d **0.648 [0.561, 0.728]**. The grid-searched
models do not beat the unfitted equal-weight models (4d 0.700, 5d 0.775).

### TD-037 · LOW · Stage 06 writes outputs non-atomically — **OPEN**
`main()` writes `grid_search_5d_log.csv` before the remaining outputs. A crash after that
point leaves the files mutually inconsistent (seen in E-018). Fix: write to temporary files
and rename at the end. Not changed: the stage now completes, and old outputs are archived.

### TD-038 · MEDIUM · One trial credited as clinical evidence to several compounds — **OPEN**
Found by agent 10e (`data/reproducibility.json`, `shared_trials_across_compounds`) and
quantified in `docs/VPS_EVALUATION.md`: **17 pre-cutoff trials** in
`clinical_maturity_precutoff_clean.csv` are linked to more than one pool compound, affecting
**31/90** compounds. Examples include combination arms, comparators and multi-drug protocols
(e.g. NCT00615472: Isoflurane, Propofol, Remifentanil). Each linked compound's clinical maturity
counts the same study, so the clinical dimension is not compound-specific evidence for these
compounds; it overlaps the role problem in TD-023. 4 label trials are shared; only one involves
a pool compound (NCT07207057, a platform trial: Terazosin + Telmisartan), so labels are unaffected.
Remedy options (owner): per-trial role filtering (TD-023 annotator) or down-weighting shared
trials. Not changed.

**Investigation 2026-10-14 (DECISIONS D-020; sensitivity only, primary outputs unchanged).**
All 17 registry records were fetched in one ClinicalTrials.gov v2 request
(`data/cache/ctgov_td038_shared_trials.json`). Each of the 35 (trial, compound) links was then
run through `scripts/trial_role.py` and adjudicated by hand in `data/feature_trial_roles_td038.csv`:

| Category | Links | Meets the approved P1 criterion? |
|---|---|---|
| Drug in its own arm (multi-arm or crossover) | 14 | yes |
| Alternatives within one arm (doxepin *or* zopiclone) | 2 | yes |
| Fixed-dose combination (H. pylori triple therapy, oxycodone/naloxone, dextromethorphan/quinidine) | 6 | undecided |
| Procedural (anaesthesia, sedation) | 5 | no |
| Auxiliary agent (interaction-study probe or perpetrator drug, concomitant immunosuppression) | 6 | no |
| Unverifiable (withdrawn, 0 enrolled, one sequential arm) | 2 | undecided; no score effect |

**Correction to the original entry:** sharing a trial does not inflate the score. The clinical
dimension is the percentile rank of each compound's **maximum phase**, and `n_trials` is not
scored. So a legitimate multi-arm trial credits each tested drug once and is not counted as
several independent studies. The real defect is **role**: under the current inputs, 7 negatives
are in the pool only through links that fail P1 (Isoflurane, Remifentanil, Propofol, Midazolam,
Rosuvastatin, Methylprednisolone, Sirolimus). With the same rule applied, no compound that stays
in the pool changes maximum phase. Applying P1 to feature links (pool 90 → 83, still 14
positives) moves the equal-weight 5d AUROC from 0.775 [0.656, 0.881] to 0.765 [0.628, 0.876].
Almost all of that shift comes from removing compounds (0.762 on the same 83 with the old
scores). On identical compounds the paired change in score ordering is +0.003 [−0.012, +0.019].
This is a corrected measurement, not a change in predictive performance. The 5d − 4d CI
includes 0 in every scenario. Report: `data/td038_feature_role_sensitivity.json`.

**Still OPEN.** P1 was approved for labels, and both this entry and TD-032 reserve its
application to features for the owner. It also changes the pool. The other 160 non-shared
feature links have not been role-audited (TD-023).

### TD-039 · LOW · `annotator_verdict` in the D-020 adjudication was computed with an over-broad alias list — **OPEN (cosmetic)**
`scripts/td038_feature_role_sensitivity.py::load_roles` checks the stored `annotator_verdict`
against `trial_role` using `[compound, matched_alias, matched_intervention]`. The last item is a
registry intervention name, not an alias (E-022). The hand adjudication, the P1 verdicts and the
sensitivity results do not use that column, so no result changes. If it is regenerated with
`[compound, matched_alias]`, a few stored verdicts (for example combination products) would read
BACKGROUND_OTHERNAME instead of THERAPEUTIC_TEST. Not changed: D-020 is awaiting an owner decision.

### TD-040 · LOW · Percentile-rank convention is direction-asymmetric — **OPEN (owner decision, D-024)**
"legacy" ranks span [1/n, 1] for higher-is-better and [0, 1−1/n] for lower-is-better dimensions,
so the neutral 0.5 for unmeasured safety sits slightly above the mean measured safety rank
(0.494 at n = 83). The "midrank" alternative is implemented and verified
(`--rank-convention midrank`). Its effect is AUROC 5d −0.001 and 5 adjacent rank swaps. Not applied.

### TD-041 · LOW · Missing proximity is median-imputed, unlike safety and molecular (neutral 0.5) — **OPEN (policy)**
D-004 applies the neutral rank to safety and molecular only. The two compounds without a
proximity value are median-imputed. They are now flagged (`dimensions_imputed`), and their rank
(≈ 0.5) is numerically close to neutral. Unifying the rule is a missing-data policy change; not done.

### TD-042 · HIGH · Molecular pathway credit counts a drug's own target as the shared PD gene — **OPEN (owner decision)**
`molecular_agent.py` marks a target pathway "in the disease module" when any module gene is in it,
including the drug's own target (e.g. Donepezil: ACHE shares Reactome pathways with "PD gene(s):
ACHE"). The direct component already credits that target–PD association. If the target is
excluded from the shared-gene set, 21 compounds change. Equal 5D AUROC falls 0.775 → 0.699
(≈ the 4D baseline 0.700), AUPRC 0.424 → 0.307, and P@10 0.50 → 0.40. Staged in
`data/_candidates/2026-10-19_sprint/10b_own_target_excluded_variant.csv`. This changes VPS
dimension 5, so it is not applied.

### TD-043 · LOW · 10c automated role heuristics misfire on real links — **OPEN (owner, D-020/TD-038 scope)**
- `trial_role.py`: `sedat\w*` makes NCT04164758 ("Daytime Sedation"; Quetiapine an active comparator) PROCEDURAL_CONTEXT instead of COMPARATOR_ONLY.
- Only the compound name and matched alias are passed as aliases, so Strattera (NCT01340885) and Rifampin (NCT02174250) come out BACKGROUND_OTHERNAME.
These are diagnostic only and not applied to scoring. The classifier also feeds the TD-038 sensitivity analysis, so it is left unchanged.

**TD-042 update 2026-10-19 (second session):** lineage confirmed in code. Module genes and the
direct component come from the same Open Targets association, so a target that is itself a
module gene makes every one of its pathways "PD pathways" by construction. Independent
re-computation: 21 compounds change (6 positives); 5D AUROC 0.775 → 0.699; paired
Δ +0.076 [0.015, 0.155]. Molecular-only AUROC 0.627 → 0.460. The variant's 5D minus 4D
is −0.001 [−0.078, 0.078]. Recommendation: exclude the drug's own targets (owner decision).
See `docs/SPRINT_REPORT_2026-10-19.md` §C2.

**TD-043 update 2026-10-19:** all 195 links reviewed in `data/_runs/validation_20261019/clinical_role_review.csv`.
- 10 links are keyword-decided; most are genuine DBS-surgery anaesthesia.
- 5 links are alias gaps.
- 22 links lack arm data in the registry.
- 2 links have an automated verdict that disagrees with adjudication; the adjudication stands.
Nothing relabelled.

**TD-040 / TD-041 update 2026-10-19:** midrank changes 5D AUROC by −0.001 (max rank move 2; top 20
unchanged). Neutral proximity changes it by −0.005 (2 compounds). Both are immaterial;
recommendation: no change.

**TD-042 update 2026-10-19 (continuation):** the fix is implemented behind
`MolecularAgentConfig.pathway_excludes_drug_targets` / stage 08 `--exclude-drug-targets-from-pathways`
(default off). The corrected candidate `data/_candidates/td042_v1/` is independently verified and has
been rehearsed through publication on fixtures. Status: **READY, AWAITING OWNER APPROVAL**. The live
baseline is unchanged. See `docs/SPRINT_REPORT_2026-10-19_CONTINUATION.md` §9.

**TD-043 update 2026-10-19 (continuation):** of the 37 flagged links, 9 already have human D-020
adjudications (retained). 28 await adjudication: 5 keyword-decided, 3 alias gaps and 20 without arm
structure. Worklist: `data/_runs/clinical_review_20261019/review_worklist_flagged.csv`.

**Weighting (TD-036 follow-up, 2026-10-19):** repeated nested CV with grouped and ungrouped folds shows that simplex, shrinkage and L2-logistic weights never reliably beat equal weights. Equal weights are retained. See `docs/VPS_WEIGHTING_DECISION_2026-10-19.md`.

### TD-044 · MEDIUM · Deployment and operations controls absent (audit 2026-10-20) — **OPEN**
The dashboard is safe for loopback, single-user, read-only use (bind + Host check, GET-only, CSP, redaction,
validated paths). Missing before any shared deployment: authentication, HTTPS, structured server logging and
monitoring, scheduled backups of the git-ignored `data/`, a retention policy for `data/cache` (297 MB) and
`data/_runs`, a dependency vulnerability scan (pip-audit not installed), and a manifest repair path (a corrupt
`data/run_manifest.json` makes `/api/status` return 500 and the CLI exit 1; the agent panel shows UNKNOWN).
Checklist: `docs/autonomous_runs/PRODUCTION_READINESS_CHECKLIST.md`.

### TD-045 · LOW · Test-only file-handle leaks — **OPEN**
After C-99 the remaining ResourceWarnings come from test helpers (`tests/test_evidence_independence_agent.py`
lines 60-61 and 143, `tests/test_vps_correctness.py`, `tests/test_ui.py`, `tests/test_safety_evidence_agent.py`).
Harmless; fix with `with open(...)` when those files are next touched.

**TD-044 update 2026-10-20 (4-hour sprint):** resolved parts — backup + verification tool (`scripts/backup_data.py`,
one verified backup made), retention report (read-only proposal), `/api/health` readiness probe, manifest diagnostic
and corrupt-manifest handling. Still open: authentication, HTTPS, structured server logging/monitoring, scheduled
backups (needs an owner-chosen scheduler), and the dependency vulnerability scan (`pip-audit` not installed; needs
approval to add it to the venv).

**TD-045 RESOLVED 2026-10-20:** test and production ResourceWarnings 126 -> 0 (C-110).

### TD-046 · LOW · Code-drift detection unavailable for 12 ADOPTED stages and `eval` — **OPEN**
Their last success has no script fingerprint (adopted baselines / runs before C-78), so later code changes are not
detected (`code_fingerprint_recorded: false`, shown in the run table). All their outputs are protected; re-running
them is an owner decision. `eval` additionally reports `data/reproducibility.json` as not fingerprinted.

### TD-047 · LOW · `requests.Session` in stages 04p and 05h is never closed — **OPEN (accepted)**
Process-lifetime session, released at exit. Wrapping the long `main()` bodies was judged riskier than the leak.

**TD-046 update 2026-10-20:** 00, 04, 05 and 08 now carry attested code fingerprints (`run_stage.py --attest-from`,
byte-identical isolated reproduction by the current scripts). Still without: 01, 03, 03c, 04b, diag (live-only, no
offline run) and 02, 06, eval (outputs not byte-reproducible; B-003). Owner decision to re-publish.

### TD-048 · MEDIUM · Submission-facing documents carry superseded metrics — **OPEN (owner)**
`docs/CASE_STUDIES.md` line 4 ranks candidates by `VPS_grid_3d` ("best-performing variant, AUROC 0.750") — grid
weights are fitted on the evaluation labels (in-sample); line 509 reports the 2026-10-14 rerun "AUROC 4d 0.724 / 5d
0.781", superseded by the approved 0.700 / 0.775 (README and `vps_evaluation_report.json`). Not edited (human-authored
narrative): mark as superseded or update before any submission. No manuscript exists in the repository.
