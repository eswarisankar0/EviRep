"""
STEP 4b: export the real paper-level co-dependency graph for ONE compound.

Stage 04 builds a paper co-dependency graph per compound (shared-authorship and
citation edges) but persists only the aggregate counts, so the graph itself
cannot be drawn afterwards. Figure 3 previously worked around this by generating
a RANDOM graph -- which also carried the wrong cluster count (it drew 5 clusters
where the real Droxidopa value is 16).

This script re-derives the graph for a single compound using stage 04's own
functions, so the result is the same computation, not a reimplementation, and
persists the real nodes and edges.

PROVENANCE GUARD: the re-derived aggregate counts are compared against the
stage-04 checkpoint for that compound. If they disagree the script FAILS and
writes nothing, rather than emitting a graph that does not correspond to the
reported numbers.

Run from the repository root (needs network; ~1 call per paper):
    env -u NCBI_API_KEY S2_SLEEP=2.5 ./venv/bin/python \
        scripts/04b_export_literature_graph.py --compound Droxidopa

Output:
    data/literature_graph_<compound>.json
"""

import argparse
import importlib.util
import json
import os
import sys

import networkx as nx

HERE = os.path.dirname(os.path.abspath(__file__))
CHECKPOINT = "data/_literature_checkpoint.jsonl"


def load_stage04():
    path = os.path.join(HERE, "04_literature_independence.py")
    spec = importlib.util.spec_from_file_location("stage04", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["stage04"] = mod
    spec.loader.exec_module(mod)
    return mod


def checkpoint_record(compound):
    if not os.path.exists(CHECKPOINT):
        return None
    with open(CHECKPOINT, encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("compound_name") == compound:
                return rec
    return None


def build_graph_with_edges(stage04, paper_details):
    """
    Mirror of stage04.build_dependency_graph, but retaining the graph object so
    nodes/edges can be exported. Edge precedence (shared_author before citation)
    is identical, so component counts match.
    """
    G = nx.Graph()
    pmids = list(paper_details.keys())
    G.add_nodes_from(pmids)
    reasons = {"shared_author": 0, "citation": 0}

    citation_cache = {}
    failures = 0
    import time
    for pmid in pmids:
        try:
            citation_cache[pmid] = stage04.fetch_citing_pmids(pmid)
        except stage04.SemanticScholarUnavailable:
            citation_cache[pmid] = set()
            failures += 1
        time.sleep(stage04.S2_SLEEP)

    for i in range(len(pmids)):
        for j in range(i + 1, len(pmids)):
            p1, p2 = pmids[i], pmids[j]
            a1 = set(paper_details[p1]["authors"])
            a2 = set(paper_details[p2]["authors"])
            if a1 & a2:
                G.add_edge(p1, p2, reason="shared_author")
                reasons["shared_author"] += 1
                continue
            if p2 in citation_cache.get(p1, set()) or p1 in citation_cache.get(p2, set()):
                G.add_edge(p1, p2, reason="citation")
                reasons["citation"] += 1
    return G, reasons, failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compound", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    expected = checkpoint_record(args.compound)
    if expected is None:
        raise SystemExit(
            f"No stage-04 checkpoint record for {args.compound!r}. Cannot verify "
            f"provenance, so nothing will be written."
        )
    print(f"Checkpoint for {args.compound}: papers={expected['raw_paper_count']}, "
          f"components={expected['effective_independent_count']}, "
          f"author_edges={expected['edges_shared_author']}, "
          f"citation_edges={expected['edges_citation']}")

    stage04 = load_stage04()
    print(f"\nRe-deriving the graph (S2_SLEEP={stage04.S2_SLEEP}s)...")
    pmids = stage04.search_pmids(args.compound)
    details = stage04.fetch_paper_details(pmids)
    G, reasons, failures = build_graph_with_edges(stage04, details)
    components = list(nx.connected_components(G))

    derived = {
        "raw_paper_count": len(details),
        "effective_independent_count": len(components),
        "edges_shared_author": reasons["shared_author"],
        "edges_citation": reasons["citation"],
    }
    print(f"Derived: {derived}")
    print(f"Citation lookup failures this run: {failures}")

    # --- PROVENANCE GUARD -------------------------------------------------
    mismatch = {k: (expected[k], derived[k]) for k in derived if expected[k] != derived[k]}
    if mismatch:
        raise SystemExit(
            "\nFAILED PROVENANCE CHECK -- re-derived graph does not match the "
            "stage-04 checkpoint. Nothing written.\n"
            f"  differences (checkpoint, derived): {mismatch}\n"
            "This usually means PubMed/Semantic Scholar content changed since the "
            "stage-04 run. Do NOT draw a figure from this graph; either re-run "
            "stage 04 for the whole cohort or drop the figure."
        )
    print("\nPROVENANCE CHECK PASSED - derived graph matches the checkpoint exactly.")

    comp_index = {}
    for idx, comp in enumerate(sorted(components, key=lambda c: (-len(c), sorted(c)[0]))):
        for pmid in comp:
            comp_index[pmid] = idx

    payload = {
        "compound": args.compound,
        "source": "scripts/04b_export_literature_graph.py (re-derived via stage 04 functions)",
        "verified_against": CHECKPOINT,
        "counts": derived,
        "nodes": [
            {
                "pmid": p,
                "component": comp_index[p],
                "year": details[p].get("year", ""),
                "n_authors": len(details[p].get("authors", [])),
                "title": (details[p].get("title") or "")[:200],
            }
            for p in sorted(G.nodes())
        ],
        "edges": [
            {"source": u, "target": v, "reason": d.get("reason")}
            for u, v, d in sorted(G.edges(data=True))
        ],
        "component_sizes": sorted((len(c) for c in components), reverse=True),
    }

    out = args.out or f"data/literature_graph_{args.compound.lower().replace(' ', '_')}.json"
    os.makedirs("data", exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1)
    print(f"Wrote {out}")
    print(f"  nodes={len(payload['nodes'])} edges={len(payload['edges'])} "
          f"component_sizes={payload['component_sizes']}")


if __name__ == "__main__":
    main()
