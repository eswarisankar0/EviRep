# References

**Status of the pre-existing list: there was none.** The repository contained no
bibliography, no citations in code comments, and no documentation of any kind before
2026-10-05. Nothing could be "reviewed" — this list was therefore built from the data
sources and methods the code *demonstrably* uses, and every entry was verified against
PubMed before being written here.

**Verification method.** Each entry below was retrieved live from the NCBI E-utilities API
on 2026-10-05 and the returned `ArticleTitle` was string-matched against the intended
title. PMIDs, DOIs, journals, volumes and page ranges are copied from the API response, not
written from memory. Entries that could not be verified this way are listed separately in
§3 as resources, with URLs only — **no bibliographic details have been invented**.

---

## 1. Methodological references (verified)

These support methods the code actually implements.

### [M1] Hetionet — the knowledge graph behind stages 01 and 02
> Himmelstein DS, Lizee A, et al. **Systematic integration of biomedical knowledge
> prioritizes drugs for repurposing.** *eLife* 2017;6.
> PMID [28936969](https://pubmed.ncbi.nlm.nih.gov/28936969/) · doi:[10.7554/eLife.26726](https://doi.org/10.7554/eLife.26726)

**Supports:** `scripts/01_get_pd_candidates.py` downloads Hetionet v1.0.0 and uses its
metaedges (`CtD`, `CpD`, `CbG`, `GiG`, `DaG`/`DuG`/`DdG`).
**Claim check:** the abstract states Hetionet v1.0 has "47,031 nodes of 11 types and
2,250,197 relationships of 24 types" integrated from 29 public resources — matching the
artefact the script downloads. ✔ Supports the claim it is cited for.

### [M2] Network proximity — the method stage 02 implements
> Guney E, Menche J, et al. **Network-based in silico drug efficacy screening.**
> *Nat Commun* 2016;7:10331.
> PMID [26831545](https://pubmed.ncbi.nlm.nih.gov/26831545/) · doi:[10.1038/ncomms10331](https://doi.org/10.1038/ncomms10331)

**Supports:** the drug–disease proximity measure and the degree-matched randomisation in
`scripts/02_network_proximity.py`.
**Claim check:** the abstract introduces "a drug-disease proximity measure that quantifies
the interplay between drugs targets and diseases" and states it works "by correcting for
the known biases of the interactome" — i.e. the degree-matched null model the script
builds via `build_degree_bins()` / `generate_random_target_set()`. It also explicitly
"highlights efficacy issues for drugs used in Parkinson". ✔ Supports the claim.

> ⚠️ **Attribution is inferred, not stated by the authors.** `scripts/02_network_proximity.py`
> contains no citation. This reference is the canonical published description of the
> method the code implements; it is *not* evidence that the original author consulted it.
> The repo's implementation also differs in detail — it uses mean nearest-PD-gene distance
> (a "closest"-style measure) rather than reproducing any specific variant from the paper.

### [M3] Open Targets Platform — the molecular/pathway agent's data source
> Ochoa D, Hercules A, et al. **The next-generation Open Targets Platform: reimagined,
> redesigned, rebuilt.** *Nucleic Acids Res* 2023;51:D1353–D1359.
> PMID [36399499](https://pubmed.ncbi.nlm.nih.gov/36399499/) · doi:[10.1093/nar/gkac1046](https://doi.org/10.1093/nar/gkac1046)

**Supports:** all five legs of the chain in `scripts/molecular_agent.py`, and the
`datatypeScores` structure on which the leakage-exclusion design depends.
**Version note:** the agent queried **API v26.9, data version 26.09** (recorded in the
module docstring). That is a *later* release than this paper describes — the paper is cited
for the platform, not for the snapshot.

### [M4] Reactome — pathway annotations
> Milacic M, Beavers D, et al. **The Reactome Pathway Knowledgebase 2024.**
> *Nucleic Acids Res* 2024;52:D672–D678.
> PMID [37941124](https://pubmed.ncbi.nlm.nih.gov/37941124/) · doi:[10.1093/nar/gkad1025](https://doi.org/10.1093/nar/gkad1025)

**Supports:** `Target.pathways` (`pathwayId`, `pathway`, `topLevelTerm`) used for the
pathway-overlap component and the INDIRECT/INFERRED evidence tiers.

### [M5] ChEMBL — drug mechanisms of action
> Zdrazil B, Felix E, et al. **The ChEMBL Database in 2023: a drug discovery platform
> spanning multiple bioactivity data types and time periods.**
> *Nucleic Acids Res* 2024;52:D1180–D1192.
> PMID [37933841](https://pubmed.ncbi.nlm.nih.gov/37933841/) · doi:[10.1093/nar/gkad1004](https://doi.org/10.1093/nar/gkad1004)

**Supports:** the DRUG→TARGET leg (`drug.mechanismsOfAction`), surfaced through Open
Targets, and ChEMBL molecule identifiers used for drug normalization.

### [M6] Disease Ontology — the Hetionet disease identifier
> Schriml LM, Mitraka E, et al. **Human Disease Ontology 2018 update: classification,
> content and workflow expansion.** *Nucleic Acids Res* 2019;47:D955–D962.
> PMID [30407550](https://pubmed.ncbi.nlm.nih.gov/30407550/) · doi:[10.1093/nar/gky1032](https://doi.org/10.1093/nar/gky1032)

**Supports:** `DOID:14330` (Parkinson's disease), the identifier used throughout stages
01/02 as `Disease::DOID:14330`.

### [M7] NCBI E-utilities — PubMed access in stage 04
> Sayers EW, Beck J, et al. **Database resources of the National Center for Biotechnology
> Information.** *Nucleic Acids Res* 2024;52:D33–D43.
> PMID [37994677](https://pubmed.ncbi.nlm.nih.gov/37994677/) · doi:[10.1093/nar/gkad1044](https://doi.org/10.1093/nar/gkad1044)

**Supports:** `esearch`/`efetch` usage in `scripts/04_literature_independence.py`.

---

## 2. Identifier cross-reference

Parkinson's disease is referred to by **two different identifiers** in this project, which
is intentional and is recorded in every molecular-agent record:

| System | Identifier | Used by | How it was established |
|---|---|---|---|
| Disease Ontology (via Hetionet) | `DOID:14330` | stages 01, 02 | present in Hetionet v1.0 nodes |
| MONDO (via Open Targets) | `MONDO_0005180` | stage 08 | resolved **by live API query**, not from memory |

> `EFO_0002508` is *not* used. It is frequently cited for Parkinson's disease, but the Open
> Targets search API returned `MONDO_0005180`, so the queried value is what the code uses.

---

## 3. Data resources and APIs (cited by URL — not verified publications)

No bibliographic details are asserted for these. They are cited as the services the code
calls, with the access date.

| Resource | Used by | URL | Accessed |
|---|---|---|---|
| Hetionet v1.0.0 archive (Zenodo record 268568) | `01` | https://zenodo.org/records/268568 | 2026-10-05 |
| Open Targets Platform GraphQL API v26.9 (data 26.09) | `08` | https://api.platform.opentargets.org/api/v4/graphql | 2026-10-05 |
| ClinicalTrials.gov API v2 | `03`, `check_studytype` | https://clinicaltrials.gov/api/v2/studies | 2026-10-05 |
| openFDA drug label endpoint | `05` | https://api.fda.gov/drug/label.json | 2026-10-05 |
| NCBI E-utilities | `04` | https://eutils.ncbi.nlm.nih.gov/entrez/eutils | 2026-10-05 |
| Semantic Scholar Academic Graph API | `04` | https://api.semanticscholar.org/graph/v1 | 2026-10-05 |

> **Semantic Scholar:** its platform paper is not indexed in PubMed, so it could not be
> verified by the method used for §1. Rather than copy bibliographic details from memory,
> it is cited here as an API only. If a formal citation is needed, verify it independently
> before adding.

---

## 4. Case-study evidence

Clinical and preclinical evidence for individual ranked candidates is **not** listed here.
It belongs in `docs/CASE_STUDIES.md`, kept separate because it serves a different purpose:
§1 justifies the *method*, case studies interrogate a *result*. Mixing them would let a
methods citation look like evidence for a candidate.

---

## 5. Removed / flagged

| Item | Action | Reason |
|---|---|---|
| — | — | No pre-existing references existed to remove or correct. |

Nothing has been removed, because nothing was there. Every entry in §1 was added in this
session and verified at the time of writing.

---

## 6. Re-verification audit — 2026-10-12

All 13 PMIDs cited in this file (M1–M7) and in `docs/CASE_STUDIES.md` §1–§2 (35860451,
31675664, 35665915, 40588412, 40387966, 40288252) were re-checked with one batched NCBI
esummary request: title, journal, year, first author and DOI all match. Abstract quotes used
for the M1/M2 claim checks were re-confirmed verbatim. No placeholder, duplicate or
unverifiable citation was found in this file.

Issues found in the *case-study* citations (corrected in `docs/CASE_STUDIES.md`, not here):
NCT00605683 was mis-cited as a lisuride trial (E-014); Badran 2025 was described as
"corroborating" although it disagrees on ESS; Badran and Zrineh DOIs were added from PubMed.
Cosmetic: PubMed's own title for 40588412 reads "Parkinson' Disease".

Sources added for the 2026-10-12 candidate records are listed inline in
`docs/CASE_STUDIES.md` §7–§8, following §4 above (case-study evidence is kept out of this
methods list).
