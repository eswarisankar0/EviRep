"""
Generates the paper figures. Every figure is drawn from measured data; none
contains synthetic or hardcoded values.

1. AUROC comparison across baselines and VPS variants  (data/baseline_results_v2.csv,
   data/vps_variant_results.csv)
2. Ablation study, 4-dim and 5-dim                     (data/ablation_results_*.csv)
3. Paper co-dependency graph for a case-study compound (data/literature_graph_*.json,
   provenance-verified against data/_literature_checkpoint.jsonl)
"""
import json
import os

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import networkx as nx

plt.rcParams['font.size'] = 10


# ============================================================
# HELPERS: read measured metrics rather than hardcoding them
# ============================================================

def _read_metrics(path):
    """Load a metrics CSV written by script 06, or fail with a clear message."""
    if not os.path.exists(path):
        raise SystemExit(
            f"Required metrics file not found: {path}\n"
            f"Run scripts/06_vps_fusion.py first. Figures are generated from "
            f"measured results, never from hardcoded values."
        )
    frame = pd.read_csv(path, index_col=0)
    if "AUROC" not in frame.columns:
        raise SystemExit(f"{path} has no 'AUROC' column (found {list(frame.columns)})")
    return frame


def _wrap(label, width=14):
    """Wrap long metric names onto multiple lines for readable x-tick labels."""
    words, lines, current = str(label).split(), [], ""
    for word in words:
        if current and len(current) + len(word) + 1 > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return "\n".join(lines)

def _uncertainty_note(path="data/vps_scores_v2.csv", a="VPS_equal_5d", b="VPS_equal"):
    """
    One-line caption: label count and the paired-bootstrap CI of the
    equal-weight 5-dim minus 4-dim AUROC, computed from the persisted scores
    (never hardcoded). Returns None if the inputs are absent.
    """
    if not os.path.exists(path):
        return None
    frame = pd.read_csv(path)
    if not {a, b, "label"} <= set(frame.columns):
        return None
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from bootstrap_auroc_ci import paired_bootstrap
    r = paired_bootstrap(frame["label"], frame[a], frame[b])
    lo, hi = r["ci_diff"]
    verdict = "CI includes 0: not significant" if lo <= 0 <= hi else "CI excludes 0"
    return (f"Labels: {int(frame['label'].sum())} positive / {len(frame)} (effective labels incl. "
            f"data/label_role_exclusions.csv). Equal-weight 5-dim minus 4-dim AUROC "
            f"{r['diff']:+.3f}, 95% CI [{lo:+.3f}, {hi:+.3f}] (paired bootstrap, "
            f"n={r['n_boot']}, seed {r['seed']}; {verdict}).")


# ============================================================
# FIGURE 1: AUROC comparison
# ============================================================

def figure1_auroc_comparison():
    """
    Reads the measured metrics written by script 06.

    Previously the AUROC values here were hardcoded literals, so the figure
    could not reflect a rerun and silently diverged from the data. They are now
    read from data/baseline_results_v2.csv and data/vps_variant_results.csv.
    The molecular dimension appears automatically once step 08 has been run.
    """
    baselines = _read_metrics("data/baseline_results_v2.csv")
    variants = _read_metrics("data/vps_variant_results.csv")

    # Models whose weights were fitted on all labelled data are IN-SAMPLE and
    # are not comparable to the unfitted rows. Mark them explicitly (hatched,
    # label suffixed) so the figure cannot be read as a like-for-like
    # comparison. See TECHNICAL_DEBT TD-003.
    fitted = (variants["weights_fitted"].astype(str).str.lower() == "true"
              if "weights_fitted" in variants.columns
              else pd.Series(False, index=variants.index))

    labels = list(baselines.index) + [
        f"{n} (in-sample)" if fitted.get(n, False) else n for n in variants.index]
    methods = [_wrap(n) for n in labels]
    aurocs = list(baselines["AUROC"]) + list(variants["AUROC"])

    fig, ax = plt.subplots(figsize=(max(9, 1.5 * len(methods)), 5))
    colors = ['#999999'] * len(baselines) + ['#4C72B0'] * len(variants)
    hatches = [''] * len(baselines) + ['//' if fitted.get(n, False) else ''
                                       for n in variants.index]
    bars = ax.bar(methods, aurocs, color=colors, hatch=hatches, edgecolor='white')

    # Overlay the honest held-out value for every fitted model.
    if "heldout_nested_cv_auroc" in variants.columns:
        for i, name in enumerate(variants.index):
            nested = variants.loc[name, "heldout_nested_cv_auroc"]
            if pd.notna(nested):
                x = len(baselines) + i
                ax.plot([x - 0.4, x + 0.4], [nested, nested], color='#C44E52',
                        lw=2.2, zorder=5)
                ax.text(x, float(nested) + 0.004, f"{float(nested):.3f}",
                        ha='center', va='bottom', fontsize=8, color='#C44E52',
                        zorder=6, bbox=dict(facecolor='white', edgecolor='none',
                                            alpha=0.85, pad=1.0))
    ax.axhline(0.5, color='red', linestyle='--', linewidth=1, label='Random baseline (AUROC=0.5)')
    ax.set_ylabel("AUROC")
    ax.set_title("Predictive Performance: Baselines vs. VPS Variants")
    lo, hi = min(aurocs), max(aurocs)
    ax.set_ylim(max(0.0, lo - 0.1), min(1.02, hi + 0.08))
    handles, labels_ = ax.get_legend_handles_labels()
    handles.append(Line2D([0], [0], color='#C44E52', lw=2.2,
                          label='held-out nested-CV AUROC (fitted models)'))
    ax.legend(handles=handles, fontsize=8, loc='upper left')
    for bar, val in zip(bars, aurocs):
        ax.text(bar.get_x() + bar.get_width()/2, val + 0.012, f"{val:.3f}",
                ha='center', fontsize=9)
    fig.text(0.01, 0.015, "Hatched bars: weights fitted on all labelled data -> AUROC is "
             "IN-SAMPLE and not comparable to the unhatched bars. "
             "Red line = held-out nested-CV estimate (single 5-fold split, seed 42).",
             fontsize=7.5, color='#555555')
    note = _uncertainty_note()
    if note:
        fig.text(0.01, 0.045, note, fontsize=7.5, color='#555555')
    plt.tight_layout(rect=(0, 0.075 if note else 0.045, 1, 1))
    plt.savefig("data/figure1_auroc_comparison.png", dpi=200)
    print("Saved data/figure1_auroc_comparison.png")


# ============================================================
# FIGURE 2: Ablation study
# ============================================================

def figure2_ablation(path="data/ablation_results_v2.csv", suffix=""):
    """
    Reads the measured ablation metrics written by script 06 (previously
    hardcoded). When data/ablation_results_5d.csv exists it is plotted too, so
    the molecular dimension's ablation row appears without any manual edit.
    """
    frame = _read_metrics(path)
    names = list(frame.index)
    # The reference bar uses grid-searched weights selected on ALL labelled
    # data, so its AUROC is in-sample (TD-003). Mark it, as Figure 1 does.
    fitted_ref = "grid-searched" in str(names[0])
    if fitted_ref:
        names[0] = f"{names[0]} (in-sample)"
    labels = [_wrap(n) for n in names]
    aurocs = list(frame["AUROC"])

    fig, ax = plt.subplots(figsize=(max(8, 1.6 * len(labels)), 5))
    colors = ['#4C72B0'] + ['#DD8452' if v < aurocs[0] else '#55A868' for v in aurocs[1:]]
    bars = ax.bar(labels, aurocs, color=colors)
    if fitted_ref:
        bars[0].set_hatch('//')
        bars[0].set_edgecolor('white')
        # scripts/06_vps_fusion.py::run_ablation scores each "Without X" bar
        # with EQUAL weights over the remaining dimensions, not the fitted
        # weights minus one dimension. Say so on the figure.
        fig.text(0.01, 0.01,
                 "Hatched reference: grid-searched weights fitted on all labelled data (in-sample; "
                 "see held-out nested-CV in Figure 1). 'Without X' bars use EQUAL weights over the "
                 "remaining dimensions, so differences mix re-weighting with removal.",
                 fontsize=7, color='#555555', wrap=True)
    ax.axhline(aurocs[0], color='#4C72B0', linestyle='--', linewidth=1, alpha=0.5)
    ax.set_ylabel("AUROC")
    n_dims = len(labels) - 1
    ax.set_title(f"Ablation: Effect of Removing Each Evidence Dimension "
                 f"({n_dims} dimensions)")
    lo, hi = min(aurocs), max(aurocs)
    ax.set_ylim(max(0.0, lo - 0.05), min(1.02, hi + 0.05))
    for bar, val in zip(bars, aurocs):
        ax.text(bar.get_x() + bar.get_width()/2, val + 0.005, f"{val:.3f}", ha='center', fontsize=9)
    plt.tight_layout(rect=(0, 0.05 if fitted_ref else 0, 1, 1))
    out = f"data/figure2_ablation{suffix}.png"
    plt.savefig(out, dpi=200)
    print(f"Saved {out}")


# ============================================================
# FIGURE 3: Droxidopa co-dependency graph (case study)
# ============================================================

def figure3_literature_graph(path=None, compound="Droxidopa"):
    """
    Paper co-dependency graph, drawn from REAL persisted data.

    Reads data/literature_graph_<compound>.json, produced by
    scripts/04b_export_literature_graph.py, which re-derives the graph using
    stage 04's own functions and refuses to write unless the derived aggregate
    counts match the stage-04 checkpoint exactly.

    This replaces an earlier version that generated a RANDOM graph with
    np.random and hardcoded cluster sizes [8, 6, 5, 4, 3]. That figure was not
    merely illustrative: it also showed 5 clusters where the real Droxidopa
    value is 16, so it misstated the result it was captioned as showing.
    """
    path = path or f"data/literature_graph_{compound.lower().replace(' ', '_')}.json"
    if not os.path.exists(path):
        print(f"{path} not found -- skipping Figure 3. Generate it with:\n"
              f"  env -u NCBI_API_KEY S2_SLEEP=2.5 ./venv/bin/python \\\n"
              f"      scripts/04b_export_literature_graph.py --compound {compound}\n"
              f"NO figure is drawn from synthetic data.")
        return

    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)

    counts = payload["counts"]
    G = nx.Graph()
    for node in payload["nodes"]:
        G.add_node(node["pmid"], component=node["component"])
    for edge in payload["edges"]:
        G.add_edge(edge["source"], edge["target"], reason=edge["reason"])

    # Sanity: the drawn graph must match the persisted counts.
    assert G.number_of_nodes() == counts["raw_paper_count"], "node count mismatch"
    assert nx.number_connected_components(G) == counts["effective_independent_count"], \
        "component count mismatch"

    # Colour only multi-paper components; singletons are grey. The previous
    # palette[component % 10] reused colours once there were >10 components,
    # so singletons looked like members of the main cluster.
    palette = ['#4C72B0', '#DD8452', '#55A868', '#C44E52', '#8172B2',
               '#937860', '#DA8BC3', '#CCB974', '#64B5CD']
    comp_size = {}
    for n in G.nodes():
        c = G.nodes[n]["component"]
        comp_size[c] = comp_size.get(c, 0) + 1
    multi = sorted(c for c, k in comp_size.items() if k > 1)
    colour_of = {c: palette[i % len(palette)] for i, c in enumerate(multi)}
    node_colors = [colour_of.get(G.nodes[n]["component"], '#BBBBBB') for n in G.nodes()]

    author_edges = [(u, v) for u, v, d in G.edges(data=True)
                    if d.get("reason") == "shared_author"]
    citation_edges = [(u, v) for u, v, d in G.edges(data=True)
                      if d.get("reason") == "citation"]

    pos = nx.spring_layout(G, seed=42, k=0.6)
    fig, ax = plt.subplots(figsize=(9, 7.5))
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=260,
                           linewidths=0.5, edgecolors='white', ax=ax)
    nx.draw_networkx_edges(G, pos, edgelist=author_edges, edge_color='#C44E52',
                           width=1.8, alpha=0.85, ax=ax, label='shared author')
    nx.draw_networkx_edges(G, pos, edgelist=citation_edges, edge_color='#4C72B0',
                           width=1.2, alpha=0.65, style='dashed', ax=ax,
                           label='citation')

    sizes = payload["component_sizes"]
    singletons = sum(1 for s_ in sizes if s_ == 1)
    ax.set_title(
        f"{payload['compound']}: {counts['raw_paper_count']} PubMed papers -> "
        f"{counts['effective_independent_count']} connected components "
        f"(publication clusters, not independent trials)\n"
        f"{counts['edges_shared_author']} shared-author edges (red, solid), "
        f"{counts['edges_citation']} citation edges (blue, dashed); "
        f"largest cluster {sizes[0]} papers, {singletons} singletons",
        fontsize=10)
    handles = [
        Line2D([0], [0], color='#C44E52', lw=1.8, label='shared author'),
        Line2D([0], [0], color='#4C72B0', lw=1.2, ls='dashed', label='citation'),
    ]
    ax.legend(handles=handles, loc='lower right', fontsize=9, frameon=True)
    ax.text(0.01, 0.01,
            "Real data: nodes are PubMed PMIDs; counts verified against "
            "data/_literature_checkpoint.jsonl. Singletons grey.\n"
            "Sample = stage-04 PubMed hits (capped at 30, no date bound; TD-021).",
            transform=ax.transAxes, fontsize=7, color='#555555')
    ax.axis('off')
    plt.tight_layout()
    out = f"data/figure3_{payload['compound'].lower()}_literature_graph.png"
    plt.savefig(out, dpi=200)
    print(f"Saved {out}")
    print(f"  drawn from {path} (provenance-verified against the stage-04 checkpoint)")


if __name__ == "__main__":
    import argparse
    # No options yet: parse anyway so --help or a stray argument exits before any
    # work is done (TD-034; incident E-017 ran stages 05/06 via --help).
    argparse.ArgumentParser(description=__doc__.strip().splitlines()[0] if __doc__ else None).parse_args()
    os.makedirs("data", exist_ok=True)
    figure1_auroc_comparison()
    figure2_ablation()
    # 5-dimension ablation, present once scripts/08_molecular_pathway.py has run.
    if os.path.exists("data/ablation_results_5d.csv"):
        figure2_ablation("data/ablation_results_5d.csv", suffix="_5d")
    else:
        print("data/ablation_results_5d.csv not found -- skipping the "
              "5-dimension ablation figure (run scripts/08_molecular_pathway.py "
              "then scripts/06_vps_fusion.py to produce it).")
    figure3_literature_graph()