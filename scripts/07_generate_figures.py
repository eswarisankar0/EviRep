"""
Generates the three key figures for the paper:
1. AUROC comparison across baselines and VPS variants
2. Ablation study (dimension dropout) bar chart
3. Droxidopa co-dependency graph visualization (case study)
"""
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import networkx as nx

plt.rcParams['font.size'] = 10

# ============================================================
# FIGURE 1: AUROC comparison
# ============================================================

def figure1_auroc_comparison():
    methods = [
        "Proximity\nonly", "Publication\ncount only", "Naive\nunweighted sum",
        "VPS\nequal weights", "VPS\ngrid-searched\n(4-dim)", "VPS\ngrid-searched\n(3-dim)"
    ]
    aurocs = [0.620, 0.728, 0.734, 0.721, 0.742, 0.742]

    fig, ax = plt.subplots(figsize=(9, 5))
    colors = ['#999999']*3 + ['#4C72B0']*3
    bars = ax.bar(methods, aurocs, color=colors)
    ax.axhline(0.5, color='red', linestyle='--', linewidth=1, label='Random baseline (AUROC=0.5)')
    ax.set_ylabel("AUROC")
    ax.set_title("Predictive Performance: Baselines vs. VPS Variants")
    ax.set_ylim(0.4, 0.85)
    ax.legend()
    for bar, val in zip(bars, aurocs):
        ax.text(bar.get_x() + bar.get_width()/2, val + 0.01, f"{val:.3f}", ha='center', fontsize=9)
    plt.tight_layout()
    plt.savefig("data/figure1_auroc_comparison.png", dpi=200)
    print("Saved data/figure1_auroc_comparison.png")


# ============================================================
# FIGURE 2: Ablation study
# ============================================================

def figure2_ablation():
    labels = ["Full VPS\n(4 dims)", "Without\nproximity", "Without\nclinical",
              "Without\nliterature", "Without\nsafety"]
    aurocs = [0.742, 0.730, 0.730, 0.678, 0.707]

    fig, ax = plt.subplots(figsize=(8, 5))
    colors = ['#4C72B0'] + ['#DD8452' if v < aurocs[0] else '#55A868' for v in aurocs[1:]]
    bars = ax.bar(labels, aurocs, color=colors)
    ax.axhline(aurocs[0], color='#4C72B0', linestyle='--', linewidth=1, alpha=0.5)
    ax.set_ylabel("AUROC")
    ax.set_title("Ablation: Effect of Removing Each Evidence Dimension")
    ax.set_ylim(0.6, 0.8)
    for bar, val in zip(bars, aurocs):
        ax.text(bar.get_x() + bar.get_width()/2, val + 0.005, f"{val:.3f}", ha='center', fontsize=9)
    plt.tight_layout()
    plt.savefig("data/figure2_ablation.png", dpi=200)
    print("Saved data/figure2_ablation.png")


# ============================================================
# FIGURE 3: Droxidopa co-dependency graph (case study)
# ============================================================

def figure3_droxidopa_graph():
    """
    Illustrative reconstruction: since the actual paper-level graph edges
    weren't saved to a file by script 04, this rebuilds a graph with the
    SAME structure (26 nodes, same cluster count) to visualize the concept.
    If you saved per-paper edge data, replace this with the real edges.
    """
    np.random.seed(42)
    G = nx.Graph()
    n_papers = 26
    n_clusters = 5
    G.add_nodes_from(range(n_papers))

    # Distribute 26 papers into 5 clusters of varying size (illustrative)
    cluster_sizes = [8, 6, 5, 4, 3]
    node_id = 0
    cluster_assignment = {}
    for cluster_idx, size in enumerate(cluster_sizes):
        for _ in range(size):
            cluster_assignment[node_id] = cluster_idx
            node_id += 1

    # Connect nodes within the same cluster (simulating shared author/citation edges)
    for i in range(n_papers):
        for j in range(i+1, n_papers):
            if cluster_assignment[i] == cluster_assignment[j] and np.random.rand() < 0.4:
                G.add_edge(i, j)

    pos = nx.spring_layout(G, seed=42, k=0.5)
    cluster_colors = ['#4C72B0', '#DD8452', '#55A868', '#C44E52', '#8172B2']
    node_colors = [cluster_colors[cluster_assignment[n]] for n in G.nodes()]

    fig, ax = plt.subplots(figsize=(8, 7))
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=300, ax=ax)
    nx.draw_networkx_edges(G, pos, alpha=0.4, ax=ax)
    ax.set_title("Droxidopa: 26 Papers -> 5 Independent Evidence Clusters\n(illustrative reconstruction, colors = distinct clusters)")
    ax.axis('off')
    plt.tight_layout()
    plt.savefig("data/figure3_droxidopa_graph.png", dpi=200)
    print("Saved data/figure3_droxidopa_graph.png")
    print("\nNOTE: This is a reconstructed illustration with matching cluster")
    print("counts, not the literal saved edges (those weren't persisted to disk).")
    print("If you want the REAL graph, we'd need to rerun script 04 for just")
    print("Droxidopa with edge data saved this time -- takes under a minute.")


if __name__ == "__main__":
    import os
    os.makedirs("data", exist_ok=True)
    figure1_auroc_comparison()
    figure2_ablation()
    figure3_droxidopa_graph()