# Literature Credibility / Evidence Quality Agent (10a)

`scripts/literature_credibility_agent.py` · tests `tests/test_literature_credibility_agent.py`
(21 offline tests) · status: **implemented and tested as a diagnostic; NOT integrated into VPS**.

## What it answers — and what it does not

| Axis | Handled here? | Source |
|---|---|---|
| Credibility of study **design** | **Yes** | PubMed `PublicationType` (curated by NLM) |
| Population (human vs preclinical) | Yes | MeSH check tags `Humans` / `Animals` |
| Sample size | Only when unambiguous | one distinct explicit count in the abstract (`n = N`, `N patients…`), span recorded |
| Publication date vs cutoff | Yes (year granularity) | PubDate / ArticleDate / MedlineDate |
| Independence / replication | **Consumed**, not computed | stage 04/04b connected-component labels |
| Supporting vs opposing | **Only if curated** | caller-supplied `direction` + `direction_source`; otherwise `NOT_ASSESSED` |
| Clinical relevance to PD | No | — |
| Efficacy | **Never** | output field `efficacy` is fixed to `NOT_ASSESSED` and validated |

No LLM and no free-text judgement are used. Unknown inputs stay `UNKNOWN`/`None`, are counted
in `coverage`, and are excluded from averages — never scored as low quality.

## Criteria (fixed, in code as `DESIGN_PRIORITY`, `TIER`, `TIER_SCORE`)

| Tier | Designs (first matching PublicationType wins) | Score |
|---|---|---|
| A | Meta-Analysis, Systematic Review, Randomized Controlled Trial | 1.0 |
| B | Controlled Clinical Trial, Clinical Trial (any phase), Observational Study | 0.6 |
| C | Case Reports, Review (narrative) — and any A/B design on animals only | 0.3 |
| D | Editorial, Comment, Letter | 0.1 |
| X | Retracted Publication, Retraction of Publication | 0.0 |
| U | none of the above (incl. "Journal Article" only, "Comparative Study") | none |

"Comparative Study" is deliberately unmapped: PubMed applies it to laboratory and
computational work (found on PMID 41520443, a molecular-interaction study). A "Case Reports"
tag that conflicts with an abstract count > 10 is flagged in `limitations`, not reclassified.

## Input / output contract

Input: `assess_pair(drug, disease, papers, cutoff_date="2021-01-01", retrieval=None)`, where
each paper is `{pmid, title, year, publication_types[], mesh_terms[], abstract, component?,
direction?, direction_source?}` — typically from `parse_pubmed_xml()` on a PubMed efetch.
Malformed and duplicate records are listed in `rejected_records`, not scored.

Output (validated by `validate_output`): per-paper assessment with the source of every
derived field; `summary_all` and `summary_pre_cutoff` (counts by tier/design/population,
coverage, mean score over known designs, human tier-A/B count, replication indicator,
conflict flag); `uncertainty`; `criteria`; `provenance`.

## Integration boundary

Not read by `06_vps_fusion.py`. Before any integration, review: (1) whether design tiers
predict anything in this cohort; (2) leakage — use `summary_pre_cutoff`, and note the
stage-04 paper sample itself is not cutoff-bounded (TD-021); (3) coverage — recent papers
are often not yet MeSH-indexed (9/26 for Droxidopa); (4) the input sample's selection bias
(30 recency-ordered PubMed hits).

### Integration assessment (2026-10-14, after TD-032 P1): **NOT integrable yet**
1. **Leakage.** The input sample is stage 04's ~30 most recent PubMed hits, and that query has no date bound (TD-021).
   `summary_pre_cutoff` filters papers by year, but the choice of which papers enter the sample
   depends on post-cutoff publication volume. Results papers from the post-cutoff label trials
   could also enter the sample. Year-only dates leave cutoff-year papers UNKNOWN.
2. **Double counting.** The literature dimension already scores the same PMIDs
   (raw count, independence ratio). Tier-A/B papers usually report registered trials that
   the clinical dimension already counts (`max_phase_rank`, `n_trials`). A design-quality
   score would partly re-weight both.
3. **Coverage.** Only Droxidopa has PMIDs. The other 89 compounds need re-retrieval (B-002), and
   9/26 Droxidopa papers lack PublicationType/MeSH.
4. **Validation power.** With 14 positives, even the molecular dimension's +0.058 is not
   significant. A sixth dimension cannot be shown to add value on this cohort.

Prerequisites, all owner decisions:
- Cutoff-bounded re-retrieval for all 90 compounds (`search_pmids(max_date="2020/12/31")`).
- Removing PMIDs that only report trials already counted by the clinical dimension.
- Evaluating the agent first as a stand-alone diagnostic, with a pre-registered bootstrap test of its incremental value.

Until then it stays diagnostic only.

### Proposed evaluation design (2026-10-15; to pre-register, not run)
1. **Cohort:** the same 90 compounds and the same effective labels, frozen by md5 before any agent output is inspected.
2. **Input:** cutoff-bounded retrieval (TD-021 dry-run plan), stored as raw XML per compound.
   Papers that only report trials already counted by the clinical dimension (NCT ID in the
   abstract or `DataBank`) are excluded or flagged. Overlap with the stage-04 PMIDs is reported.
3. **Statistic, fixed in advance:** AUROC of `VPS_equal_5d` with versus without a 6th
   dimension, the percentile rank of `summary_pre_cutoff.mean_credibility_score_known`. Missing
   values use the same missing-data rule as the other dimensions, and coverage is reported per compound.
4. **Test:** paired bootstrap (`bootstrap_auroc_ci.paired_bootstrap`, n=2000, seed 42). Incremental
   value is claimed only if the 95% CI excludes 0.
5. **Power:** with 14 positives, the current 5d−4d CI is about ±0.10 wide. An effect smaller than
   about +0.10 is unlikely to be detected, and a null result is not evidence of no value.

## Real run (2026-10-13)

`env -u NCBI_API_KEY ./venv/bin/python scripts/literature_credibility_agent.py --graph
data/literature_graph_droxidopa.json --save-xml data/cache/pubmed_efetch_droxidopa.xml --out
data/literature_credibility_droxidopa.json` — one efetch, 26/26 PMIDs. Offline rerun:
`--xml data/cache/pubmed_efetch_droxidopa.xml` (identical paper assessments). Result: tier A 0,
B 1, C 16, D 1, U 8; all 8 pre-cutoff papers tier C. See CASE_STUDIES.md §8.9.

## Known limitations
- Year granularity: a paper in the cutoff year is `UNKNOWN` unless the cutoff is 1 January.
- PublicationType and MeSH lag publication; new papers are often unknown on both axes.
- Tiers rank design only; a tier-A trial may be small, negative or off-topic.
- Running it on other compounds needs their PMIDs, which stage 04 does not persist (only
  Droxidopa has a 04b graph). A pool-wide run therefore needs re-retrieval (owner decision).
