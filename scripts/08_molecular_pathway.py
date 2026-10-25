"""
STEP 8: Molecular / Pathway evidence (EviRep evidence dimension 5).

Builds, per candidate compound, a traceable molecular evidence chain

    DRUG -> TARGET -> GENE -> PATHWAY -> PARKINSON'S DISEASE MECHANISM

using the Open Targets Platform GraphQL API, and emits an explainable
`molecular_plausibility_score`. All logic lives in `scripts/molecular_agent.py`;
this file is the thin, resumable pipeline wrapper around it.

Input (default, matching the convention already used by scripts 04 and 05):
    data/clinical_maturity_precutoff_clean.csv

Output:
    data/molecular_pathway.csv            <- tabular, consumed by script 06
    data/molecular_pathway_evidence.jsonl <- full evidence chain per compound
    data/_molecular_checkpoint.jsonl      <- resume checkpoint (as 04/05 do)
    data/cache/molecular/*.json           <- API response cache

Run from the REPOSITORY ROOT (all paths are relative, as in every other script):

    # offline sanity check, no network, no writes
    ./venv/bin/python scripts/08_molecular_pathway.py --dry-run

    # small controlled sample (recommended first real run)
    ./venv/bin/python scripts/08_molecular_pathway.py \
        --compounds "Ropinirole,Pramipexole,Caffeine" \
        --out data/sample_molecular_pathway.csv

    # full cohort, resumable
    ./venv/bin/python scripts/08_molecular_pathway.py

NOTE on candidate pool: this stage reads the same input file as scripts 04 and
05, so it inherits the existing pool convention (compounds having a pre-cutoff
PD trial). That restriction is a PRE-EXISTING property of the pipeline, not
something introduced here; it is recorded in TECHNICAL_DEBT.md (TD-004). Use
`--input` to score a different pool without touching other stages.
"""

import argparse
import json
import os
import sys

import pandas as pd
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from molecular_agent import (  # noqa: E402
    MolecularAgentConfig,
    OpenTargetsClient,
    OpenTargetsUnavailable,
    build_disease_module,
    is_retrieval_failure,
    normalize_drug_batch,
    run_agent,
    validate_output,
)

DEFAULT_INPUT = "data/clinical_maturity_precutoff_clean.csv"
DEFAULT_OUT_CSV = "data/molecular_pathway.csv"
DEFAULT_OUT_JSONL = "data/molecular_pathway_evidence.jsonl"
CHECKPOINT_FILE = "data/_molecular_checkpoint.jsonl"

#: Columns consumed downstream by script 06. `molecular_plausibility_score` is
#: the dimension value; the component/count columns exist so the score can be
#: audited without opening the JSONL.
CSV_COLUMNS = [
    "compound_name",
    "chembl_id",
    "resolved",
    "molecular_plausibility_score",
    "confidence",
    "direct_component",
    "pathway_component",
    "n_targets",
    "n_genes",
    "n_pathways",
    "n_pathways_in_disease_module",
    "n_direct_disease_links",
    "n_disease_link_rows",
    "n_evidence_direct",
    "n_evidence_indirect",
    "n_evidence_inferred",
    "n_evidence_missing",
    "n_limitations",
]


def flatten(record):
    """Project one agent record onto the tabular schema consumed by step 6."""
    tiers = {}
    for item in record.get("evidence", []):
        tiers[item["tier"]] = tiers.get(item["tier"], 0) + 1
    components = (record.get("scoring") or {}).get("components") or {}
    detail = (record.get("scoring") or {}).get("detail") or {}
    return {
        "compound_name": record["drug"],
        "chembl_id": record.get("chembl_id"),
        "resolved": bool(record.get("chembl_id")),
        "molecular_plausibility_score": record["molecular_plausibility_score"],
        "confidence": record["confidence"],
        "direct_component": components.get("direct_target_disease"),
        "pathway_component": components.get("pathway_overlap"),
        "n_targets": len(record.get("targets", [])),
        "n_genes": len({g["ensembl_id"] for g in record.get("genes", [])}),
        "n_pathways": detail.get("n_target_pathways", 0),
        "n_pathways_in_disease_module":
            detail.get("n_target_pathways_in_disease_module", 0),
        # Only links with PERMITTED (non-leaky) evidence count as "direct".
        # `disease_links` also contains rows whose evidence was entirely
        # clinical/literature and therefore scored 0 -- counting those here
        # overstated the direct evidence (e.g. Riluzole: 10 rows, but only 4
        # carry permitted evidence). `n_disease_link_rows` keeps the raw count
        # for transparency.
        "n_direct_disease_links": sum(
            1 for dl in record.get("disease_links", [])
            if (dl.get("score_allowed_datatypes") or 0) > 0
        ),
        "n_disease_link_rows": len(record.get("disease_links", [])),
        "n_evidence_direct": tiers.get("direct", 0),
        "n_evidence_indirect": tiers.get("indirect", 0),
        "n_evidence_inferred": tiers.get("inferred", 0),
        "n_evidence_missing": tiers.get("missing", 0),
        "n_limitations": len(record.get("limitations", [])),
    }


def load_compounds(args):
    """Resolve the compound list from --compounds or the input CSV."""
    if args.compounds:
        names = [c.strip() for c in args.compounds.split(",") if c.strip()]
    else:
        if not os.path.exists(args.input):
            raise SystemExit(
                f"Input not found: {args.input}\n"
                f"This stage reads the same file as scripts 04/05. Produce it by "
                f"running steps 03 -> check_studytype.py -> filter_by_studytype.py, "
                f"or pass --compounds / --input to score a different pool."
            )
        frame = pd.read_csv(args.input)
        if "compound_name" not in frame.columns:
            raise SystemExit(
                f"{args.input} has no 'compound_name' column "
                f"(found: {list(frame.columns)})"
            )
        names = frame["compound_name"].dropna().unique().tolist()
    # Deterministic ordering, so checkpoints and cache keys are stable.
    names = sorted(set(names))
    if args.limit:
        names = names[: args.limit]
    return names


class _OfflineSession:
    """Stands in for requests.Session under --offline: any request is a failure, never a call."""

    def post(self, *args, **kwargs):
        import requests
        raise requests.ConnectionError("offline mode: query not in the cache")


def load_resolutions(path):
    """{drug: resolution} from an evidence JSONL, in the form run_agent expects."""
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            norm = r.get("normalization") or {}
            out[r["drug"]] = {"chembl_id": r.get("chembl_id"), "resolved_name": r.get("drug_normalized"),
                              "match_type": norm.get("match_type", "unresolved"),
                              "candidates": norm.get("candidates_considered", [])}
    return out


def main():
    parser = argparse.ArgumentParser(
        description="EviRep step 8: molecular / pathway evidence dimension."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT,
                        help=f"candidate CSV (default: {DEFAULT_INPUT})")
    parser.add_argument("--compounds", default=None,
                        help="comma-separated compound names, bypassing --input")
    parser.add_argument("--limit", type=int, default=None,
                        help="score only the first N compounds (small-sample runs)")
    parser.add_argument("--out", default=DEFAULT_OUT_CSV,
                        help=f"output CSV (default: {DEFAULT_OUT_CSV})")
    parser.add_argument("--out-jsonl", default=DEFAULT_OUT_JSONL,
                        help=f"evidence JSONL (default: {DEFAULT_OUT_JSONL})")
    parser.add_argument("--checkpoint", default=CHECKPOINT_FILE,
                        help="resume checkpoint path")
    parser.add_argument("--no-cache", action="store_true",
                        help="bypass the on-disk API cache")
    parser.add_argument("--fresh", action="store_true",
                        help="ignore an existing checkpoint and rescore everything")
    parser.add_argument("--dry-run", action="store_true",
                        help="resolve the compound list and exit; no API calls, no writes")
    parser.add_argument("--weight-direct", type=float, default=None,
                        help="override the direct target-disease weight")
    parser.add_argument("--weight-pathway", type=float, default=None,
                        help="override the pathway-overlap weight")
    parser.add_argument("--pd-module-size", type=int, default=None,
                        help="number of PD-associated genes to retrieve")
    parser.add_argument("--exclude-drug-targets-from-pathways", action="store_true",
                        help="TD-042: a pathway is a PD pathway only through a module gene that is not one of "
                             "the drug's own targets (owner decision; default is the approved baseline rule)")
    parser.add_argument("--resolutions-from", default=None,
                        help="evidence JSONL of an earlier run: re-use its drug -> ChEMBL resolutions instead of "
                             "resolving names again (freezes compound identity for a like-for-like re-score)")
    parser.add_argument("--offline", action="store_true",
                        help="never contact Open Targets: every query must be a cache hit, otherwise that "
                             "compound is recorded as a retrieval failure and the stage exits 1")
    args = parser.parse_args()

    compounds = load_compounds(args)

    print("=" * 62)
    print("STEP 8: MOLECULAR / PATHWAY EVIDENCE")
    print("=" * 62)
    print(f"Compounds to score: {len(compounds)}")
    if args.dry_run:
        print("\n--dry-run: no API calls, no files written.")
        for name in compounds[:20]:
            print(f"  {name}")
        if len(compounds) > 20:
            print(f"  ... and {len(compounds) - 20} more")
        return

    os.makedirs("data", exist_ok=True)

    overrides = {}
    if args.weight_direct is not None:
        overrides["weight_direct"] = args.weight_direct
    if args.weight_pathway is not None:
        overrides["weight_pathway"] = args.weight_pathway
    if args.pd_module_size is not None:
        overrides["pd_module_size"] = args.pd_module_size
    if args.no_cache:
        overrides["use_cache"] = False
    if args.exclude_drug_targets_from_pathways:
        overrides["pathway_excludes_drug_targets"] = True
    if args.offline:
        overrides["max_retries"] = 0

    config = MolecularAgentConfig(**overrides)
    client = OpenTargetsClient(config, session=_OfflineSession()) if args.offline else OpenTargetsClient(config)
    if args.exclude_drug_targets_from_pathways:
        print("TD-042 rule: drug's own targets are excluded from the shared PD-gene sets")

    print(f"Disease: {config.disease_name} ({config.disease_id})")
    print(f"Allowed datatypes:  {', '.join(config.allowed_datatypes)}")
    print(f"EXCLUDED for leakage: {', '.join(config.excluded_datatypes)}")
    print(f"Weights: direct={config.weight_direct}, pathway={config.weight_pathway}")

    # --- resume -----------------------------------------------------------
    done = set()
    if os.path.exists(args.checkpoint) and not args.fresh:
        with open(args.checkpoint, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                    drug = rec["drug"]
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
                if is_retrieval_failure(rec):
                    done.discard(drug)          # an API failure is retried, never treated as scored
                else:
                    done.add(drug)
        print(f"Resuming: {len(done)} compounds already scored.")

    todo = [c for c in compounds if c not in done]

    # --- PD module (once) -------------------------------------------------
    print("\nBuilding Parkinson's molecular module (allowed datatypes only)...")
    try:
        module = build_disease_module(client, config)
    except OpenTargetsUnavailable as exc:
        raise SystemExit(
            f"Could not build the disease module: {exc}\n"
            f"Refusing to continue: without the PD module every pathway score "
            f"would be 0.0 for reasons unrelated to biology, which would be "
            f"misleading rather than merely incomplete."
        )
    print(f"  PD genes kept:   {len(module.genes)} "
          f"(of {module.total_associated_targets} associated targets)")
    print(f"  Reactome pathways in module: {len(module.pathway_ids)}")

    if not module.genes:
        raise SystemExit(
            "Disease module is empty — aborting rather than emitting scores of "
            "0.0 that would look like evidence of absence."
        )

    # --- batched name resolution -----------------------------------------
    resolutions = {}
    if todo and args.resolutions_from:
        frozen = load_resolutions(args.resolutions_from)
        resolutions = {n: frozen[n] for n in todo if n in frozen}
        missing = [n for n in todo if n not in frozen]
        print(f"\nRe-using {len(resolutions)} resolutions from {args.resolutions_from}"
              + (f"; {len(missing)} not found there, resolved now" if missing else ""))
        todo_resolve = missing
    else:
        todo_resolve = todo
    if todo_resolve:
        print(f"\nResolving {len(todo_resolve)} drug names (batched)...")
        BATCH = 100
        for start in range(0, len(todo_resolve), BATCH):
            chunk = todo_resolve[start : start + BATCH]
            try:
                resolutions.update(normalize_drug_batch(chunk, client))
            except OpenTargetsUnavailable as exc:
                print(f"  name resolution batch failed ({exc}); "
                      f"those compounds will be scored as unresolved")
        resolved_n = sum(1 for r in resolutions.values() if r.get("chembl_id"))
        print(f"  resolved to ChEMBL: {resolved_n} / {len(todo)}")

    # --- score ------------------------------------------------------------
    failures = 0
    if todo:
        print()
        with open(args.checkpoint, "a", encoding="utf-8") as ckpt:
            for name in tqdm(todo, desc="molecular evidence"):
                try:
                    record = run_agent(
                        name, client, module, config, resolutions.get(name)
                    )
                    validate_output(record)
                    ckpt.write(json.dumps(record) + "\n")
                    ckpt.flush()
                except Exception as exc:  # noqa: BLE001 - keep the run resumable
                    failures += 1
                    print(f"  error for {name}: {type(exc).__name__}: {exc}")
    else:
        print("\nNothing to do (all compounds already in checkpoint).")

    # --- collect ----------------------------------------------------------
    # The checkpoint is append-only, so a later line for the same drug is the
    # newer result (e.g. after --fresh, which re-scores without truncating the
    # file). Keep the LAST record per drug; previously the first (stale) one won.
    latest = {}
    with open(args.checkpoint, encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            latest[rec.get("drug")] = rec
    records = list(latest.values())

    wanted = set(compounds)
    records = [r for r in records if r["drug"] in wanted]
    records.sort(key=lambda r: r["drug"])

    with open(args.out_jsonl, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")

    frame = pd.DataFrame([flatten(r) for r in records], columns=CSV_COLUMNS)
    frame.to_csv(args.out, index=False)

    # --- summary ----------------------------------------------------------
    print("\n" + "=" * 62)
    print("STEP 8 COMPLETE")
    print("=" * 62)
    print(f"Scored compounds: {len(frame)}")
    print(f"Errors during scoring: {failures}")
    print(f"API requests: {client.stats['network']}  "
          f"cache hits: {client.stats['cache_hits']}  "
          f"retries: {client.stats['retries']}")
    if len(frame):
        print(f"Resolved to ChEMBL: {int(frame['resolved'].sum())} / {len(frame)}")
        print(f"With >=1 target:    {int((frame['n_targets'] > 0).sum())}")
        print(f"With a direct PD gene link (allowed datatypes): "
              f"{int((frame['n_direct_disease_links'] > 0).sum())}")
        print(f"With pathway overlap: "
              f"{int((frame['n_pathways_in_disease_module'] > 0).sum())}")
        print(f"Score > 0:          {int((frame['molecular_plausibility_score'] > 0).sum())}")
        print("\nTop 15 by molecular_plausibility_score:")
        cols = ["compound_name", "molecular_plausibility_score", "confidence",
                "direct_component", "pathway_component", "n_targets"]
        print(frame.sort_values("molecular_plausibility_score", ascending=False)
                   .head(15)[cols].to_string(index=False))
    print(f"\nOutputs:\n  {args.out}\n  {args.out_jsonl}")
    print("\nReminder: a score of 0.0 with low confidence means evidence was "
          "ABSENT, not that a molecular link was ruled out.")
    api_failed = sorted(r["drug"] for r in records if is_retrieval_failure(r))
    if api_failed:
        # These rows carry 0.0 because Open Targets was unreachable; stage 06 would fuse them as measured.
        print(f"\nINCOMPLETE: Open Targets unavailable for {len(api_failed)} compound(s): {api_failed[:20]}. "
              "Re-run to retry; do not publish this output.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
