# VPS feature contract (2026-10-20)

The contract for each numeric VPS dimension. I checked it against the code (`scripts/06_vps_fusion.py`, `build_standardized_scores`) and against two independent re-implementations:
- `scripts/vps_verify.py`, which reproduces `data/vps_scores_v2.csv` exactly (the stage-06 publication gate);
- `scripts/vps_validation_experiments.py`, whose `main()` (default mode; not the `--matrix` path) asserts the same reproduction.

The approved baseline is unchanged: equal weights and five dimensions (D-002, D-004, D-024). For the weighting decision, see [VPS_WEIGHTING_DECISION_2026-10-19.md](VPS_WEIGHTING_DECISION_2026-10-19.md).

## Fusion
`VPS = mean(r_proximity, r_clinical, r_literature, r_safety, r_molecular)`, over the 90-compound evaluable pool.

**Rank function `r(x)` (legacy convention):**
- `rank(x, method="average") / n`; ties get the average rank.
- A lower-is-better dimension uses `1 − rank/n`. Its worst compound therefore scores exactly 0, while a higher-is-better dimension's worst scores `1/n` (D-024; `midrank` is a recorded alternative, not adopted).

**Missing values:**
- Unmeasured safety (no label) and molecular (no ChEMBL target) are not ranked; they get the neutral rank 0.5 (D-004).
- Missing proximity is median-imputed before ranking and flagged in `dimensions_imputed`.
- Clinical and literature are measured for all 90 compounds.

**Role:** the label is attached only after every feature has been computed. It is 1 if the compound has an accepted ClinicalTrials.gov PD trial first posted after 2020-12-31, after the D-020/TD-032 exclusions. The VPS is a **predictive** ranking of continued clinical investigation, not of efficacy.

## Dimensions
| | Proximity | Clinical | Literature | Safety | Molecular |
|---|---|---|---|---|---|
| Input artifact · field | `network_proximity.csv` · `proximity_z` | `clinical_maturity_precutoff_clean.csv` · `phase` → `max_phase_rank` | `literature_independence.csv` · `effective_independent_count` | `safety_signal.csv` · `serious_term_count`, `boxed_warning`, `has_label` | `molecular_pathway.csv` · `molecular_plausibility_score`, `n_targets` |
| Formula | z of mean shortest distance from drug targets to the PD module, vs 100 degree-matched random target sets (stage 02) | max over pre-cutoff accepted trials of the phase rank (NA 0, early 1 … phase 4 = 5) | connected components of the stage-04 paper graph (shared authors and citations) among PubMed's 30 most recent hits | serious-term count + 5 × boxed warning (current openFDA label) | 0.6 × direct (max allowed-datatype Open Targets score, target → PD) + 0.4 × pathway component (stage 08, `MolecularAgentConfig`) |
| Desirable direction | lower | higher | higher | lower | higher |
| Missing | median-imputed (2), flagged | none | none | neutral 0.5 (7 with no label) | neutral 0.5 (16 with no target) |
| Source · snapshot | Hetionet v1.0 PPI (2017) | CT.gov API v2, queried 2026-10-05 | PubMed + Semantic Scholar, current | openFDA label, current | Open Targets 26.09, ChEMBL mechanisms (current) |
| Cutoff-bounded? | **yes** (network predates the cutoff) | **yes** (trials first posted ≤ cutoff; phase from the current record) | **no** (unbounded search; 04p provides a bounded alternative) | **no** (78/83 labels effective after 2020; 05h gives the label at the cutoff for 31) | **no** (a fully dated rebuild exists for evaluation (OT 20.11 + ChEMBL 2020-06): 5D 0.775 → 0.704, the same as 4D; TD-033) |
| Overlap with other dimensions | Spearman 0.44 with literature, 0.25 with clinical | the same trials are reported by literature papers for 20 compounds (below) | see clinical; −0.36 with safety | 0.35 with molecular | shares targets with proximity (−0.20) |
| Kind | predictive | predictive | predictive | predictive (label risk; not incidence) | predictive (TD-042 double counting pending) |

Spearman correlations between the ranked dimensions (90 compounds) come from `data/_runs/evidence_overlap_20261020/evidence_overlap.json`. None exceeds |0.44|. No two dimensions are redundant.

## Evidence double counting (mission Step B)
`scripts/vps_evidence_overlap.py` links the PubMed records behind the literature dimension to trials. A link is either the ClinicalTrials.gov DataBank entry deposited with the record or an NCT ID in the title or abstract. Both sources give a lower bound, because many trial reports cite no registry number.

- **Clinical ↔ literature:** for 20 compounds, the stage-04 sample contains a paper reporting one of the same compound's pre-cutoff trials that the clinical dimension counts (21 in the cutoff-bounded set). Removing those papers from the bounded literature count changes 5D AUROC by +0.002 [−0.004, 0.009]. The double counting is real but immaterial to the ranking.
- **Label leakage through trial reports:** no paper in either set reports a post-cutoff label trial of the same compound (0 of 90 compounds). This does not make the unbounded literature dimension leakage-free: post-cutoff papers enter it without reporting the label trial itself (TD-021/TD-033).
- **Molecular direct ↔ pathway:** TD-042 (verified candidate `data/_candidates/td042_v1/`, **not approved**) removes the drug's own targets from the pathway credit.
- **Evidence-quality agents** (10a, 10d, 10e, 10g, 10h) are not VPS dimensions. They annotate evidence and are never added to the score (weighting decision §7).

## Weights
Equal weights are retained, and they are supported by the data, not just a default:
- **Approved feature sets:** nested CV (decision §3).
- **Experimental cutoff-bounded feature sets** (`scripts/vps_weighting_experimental.py`, 20 repeats, stratified and trial-grouped folds):
  - learned simplex, shrinkage and L2-logistic weights beat equal weights in at most 10% of repeats;
  - mean out-of-fold AUROC is lower than equal weights in every set (−0.013 to −0.156);
  - the per-fold weight SD reaches 0.26.
