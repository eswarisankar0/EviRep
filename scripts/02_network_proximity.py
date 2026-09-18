"""
STEP 2: Optimized Network Proximity Analysis

Input:
    data/hetionet_edges.csv
    data/pd_candidates.csv

Output:
    data/network_proximity.csv

Method:
    1. Build PPI network from Hetionet GiG edges.
    2. Extract Parkinson's disease-associated genes using
       DaG, DuG and DdG relationships.
    3. Precompute shortest-path distance from every PPI node
       to the nearest Parkinson's disease gene.
    4. For every candidate compound:
         - Find its CbG drug targets.
         - Calculate observed network proximity (d_real).
         - Generate degree-matched random target sets.
         - Calculate random proximities.
         - Calculate proximity z-score.

Interpretation:
    More negative proximity_z = closer to the PD module
    than expected under the degree-matched random baseline.
"""

import pandas as pd
import numpy as np
import networkx as nx
import random
from tqdm import tqdm


# ============================================================
# CONFIGURATION
# ============================================================

PD_DISEASE_ID = "Disease::DOID:14330"

# Number of randomizations.
# 100 = quick test
# 1000+ = recommended for final experiments
N_RANDOM = 100

# Make results reproducible
RANDOM_SEED = 42


# ============================================================
# 1. LOAD DATA
# ============================================================

def load_data():

    edges = pd.read_csv(
        "data/hetionet_edges.csv"
    )

    candidates = pd.read_csv(
        "data/pd_candidates.csv"
    )

    return edges, candidates


# ============================================================
# 2. BUILD PPI NETWORK
# ============================================================

def build_ppi(edges):

    print("\nBuilding PPI network...")

    # GiG = Gene interacts with Gene
    gig = edges[
        edges["metaedge"] == "GiG"
    ]

    G = nx.from_pandas_edgelist(
        gig,
        source="source",
        target="target"
    )

    print(
        f"PPI nodes: {G.number_of_nodes()}"
    )

    print(
        f"PPI edges: {G.number_of_edges()}"
    )

    return G


# ============================================================
# 3. GET PARKINSON'S DISEASE GENES
# ============================================================

def get_disease_genes(edges):

    # Hetionet represents these disease-gene
    # relationships as:
    #
    # Disease -> Gene
    #
    # DaG = Disease associates with Gene
    # DuG = Disease upregulates Gene
    # DdG = Disease downregulates Gene

    dg = edges[
        (edges["source"] == PD_DISEASE_ID)
        &
        (
            edges["metaedge"].isin(
                ["DaG", "DuG", "DdG"]
            )
        )
    ]

    disease_genes = set(
        dg["target"]
    )

    return disease_genes


# ============================================================
# 4. BUILD DRUG-TARGET MAP
# ============================================================

def build_drug_target_map(edges):

    print("\nBuilding drug-target map...")

    # CbG = Compound binds Gene
    cbg = edges[
        edges["metaedge"] == "CbG"
    ]

    drug_target_map = (
        cbg
        .groupby("source")["target"]
        .apply(set)
        .to_dict()
    )

    print(
        f"Drugs with known CbG targets: "
        f"{len(drug_target_map)}"
    )

    return drug_target_map


# ============================================================
# 5. PRECOMPUTE DISTANCE TO PD MODULE
# ============================================================

def compute_distance_to_pd(
    G,
    disease_genes
):

    print(
        "\nComputing distance from every "
        "PPI node to nearest PD gene..."
    )

    # Keep only PD genes that actually
    # exist in the PPI network.

    pd_genes_in_network = [
        gene
        for gene in disease_genes
        if gene in G
    ]

    print(
        f"PD genes in PPI: "
        f"{len(pd_genes_in_network)}"
    )

    if not pd_genes_in_network:

        raise ValueError(
            "No Parkinson's disease genes "
            "were found in the PPI network."
        )

    # --------------------------------------------------------
    # Create temporary super-source
    # --------------------------------------------------------

    SUPER_SOURCE = "__PD_SUPER_SOURCE__"

    # Avoid accidental collision
    while SUPER_SOURCE in G:
        SUPER_SOURCE += "_X"

    # Copy graph so original PPI remains unchanged
    H = G.copy()

    # Connect the temporary source to
    # every Parkinson's gene.

    for gene in pd_genes_in_network:

        H.add_edge(
            SUPER_SOURCE,
            gene
        )

    # --------------------------------------------------------
    # One BFS from the super-source
    # --------------------------------------------------------

    distances = (
        nx.single_source_shortest_path_length(
            H,
            SUPER_SOURCE
        )
    )

    # Remove artificial source
    distances.pop(
        SUPER_SOURCE,
        None
    )

    # The artificial source adds one edge:
    #
    # SUPER_SOURCE -> PD_GENE
    #
    # Therefore subtract 1 to obtain the
    # real distance to the nearest PD gene.

    distance_to_pd = {
        node: distance - 1
        for node, distance in distances.items()
    }

    print(
        f"Nodes with a path to PD module: "
        f"{len(distance_to_pd)}"
    )

    return distance_to_pd


# ============================================================
# 6. CALCULATE REAL DRUG-PD DISTANCE
# ============================================================

def calculate_real_distance(
    targets,
    distance_to_pd
):

    distances = []

    for target in targets:

        # If target exists in the precomputed
        # distance dictionary, retrieve its
        # distance to the nearest PD gene.

        if target in distance_to_pd:

            distances.append(
                distance_to_pd[target]
            )

    if not distances:

        return None

    # Average nearest-PD distance across
    # all drug targets that are reachable.

    return float(
        np.mean(distances)
    )


# ============================================================
# 7. BUILD DEGREE BINS
# ============================================================

def build_degree_bins(G):

    print(
        "\nBuilding degree bins..."
    )

    degree_bins = {}

    for node in G.nodes():

        degree = G.degree(node)

        if degree not in degree_bins:

            degree_bins[degree] = []

        degree_bins[degree].append(
            node
        )

    return degree_bins


# ============================================================
# 8. GENERATE DEGREE-MATCHED RANDOM TARGET SET
# ============================================================

def generate_random_target_set(
    real_targets,
    G,
    degree_bins
):

    random_targets = []

    for target in real_targets:

        # Ignore targets outside PPI
        if target not in G:
            continue

        degree = G.degree(
            target
        )

        possible_nodes = (
            degree_bins.get(
                degree,
                []
            )
        )

        if not possible_nodes:
            continue

        # Don't select the original target itself
        choices = [
            node
            for node in possible_nodes
            if node != target
        ]

        if not choices:
            continue

        random_target = random.choice(
            choices
        )

        random_targets.append(
            random_target
        )

    return set(
        random_targets
    )


# ============================================================
# 9. MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # Reproducibility
    # --------------------------------------------------------

    random.seed(
        RANDOM_SEED
    )

    np.random.seed(
        RANDOM_SEED
    )

    print("=" * 60)
    print(
        "STEP 2: OPTIMIZED NETWORK PROXIMITY"
    )
    print("=" * 60)

    # --------------------------------------------------------
    # Load data
    # --------------------------------------------------------

    edges, candidates = load_data()

    print(
        f"\nTotal Hetionet edges: "
        f"{len(edges)}"
    )

    print(
        f"Total candidates: "
        f"{len(candidates)}"
    )

    # --------------------------------------------------------
    # Build PPI
    # --------------------------------------------------------

    G = build_ppi(
        edges
    )

    # --------------------------------------------------------
    # Parkinson's genes
    # --------------------------------------------------------

    disease_genes = (
        get_disease_genes(
            edges
        )
    )

    print(
        f"Total Parkinson's-associated genes: "
        f"{len(disease_genes)}"
    )

    # --------------------------------------------------------
    # Precompute distance to PD
    # --------------------------------------------------------

    distance_to_pd = (
        compute_distance_to_pd(
            G,
            disease_genes
        )
    )

    # --------------------------------------------------------
    # Build drug-target map
    # --------------------------------------------------------

    drug_target_map = (
        build_drug_target_map(
            edges
        )
    )

    # --------------------------------------------------------
    # Build degree bins
    # --------------------------------------------------------

    degree_bins = (
        build_degree_bins(
            G
        )
    )

    # --------------------------------------------------------
    # Score candidates
    # --------------------------------------------------------

    results = []

    skipped_no_targets = 0
    skipped_no_distance = 0
    skipped_random = 0

    print(
        "\nScoring candidates...\n"
    )

    for _, row in tqdm(
        candidates.iterrows(),
        total=len(candidates)
    ):

        compound_id = (
            row["compound_id"]
        )

        compound_name = (
            row["compound_name"]
        )

        # ----------------------------------------------------
        # Get drug targets
        # ----------------------------------------------------

        targets = (
            drug_target_map.get(
                compound_id,
                set()
            )
        )

        if not targets:

            skipped_no_targets += 1

            continue

        # ----------------------------------------------------
        # Calculate real distance
        # ----------------------------------------------------

        d_real = (
            calculate_real_distance(
                targets,
                distance_to_pd
            )
        )

        if d_real is None:

            skipped_no_distance += 1

            continue

        # ----------------------------------------------------
        # Randomization
        # ----------------------------------------------------

        random_distances = []

        for _ in range(
            N_RANDOM
        ):

            random_targets = (
                generate_random_target_set(
                    targets,
                    G,
                    degree_bins
                )
            )

            if not random_targets:

                continue

            d_random = (
                calculate_real_distance(
                    random_targets,
                    distance_to_pd
                )
            )

            if d_random is not None:

                random_distances.append(
                    d_random
                )

        # ----------------------------------------------------
        # Require minimum number of random samples
        # ----------------------------------------------------

        if len(random_distances) < 10:

            skipped_random += 1

            continue

        # ----------------------------------------------------
        # Random baseline
        # ----------------------------------------------------

        mu = float(
            np.mean(
                random_distances
            )
        )

        sigma = float(
            np.std(
                random_distances
            )
        )

        # ----------------------------------------------------
        # Z-score
        # ----------------------------------------------------

        if sigma > 0:

            proximity_z = (
                (d_real - mu)
                / sigma
            )

        else:

            proximity_z = 0.0

        # ----------------------------------------------------
        # Save result
        # ----------------------------------------------------

        results.append({

            "compound_id":
                compound_id,

            "compound_name":
                compound_name,

            "n_targets":
                len(targets),

            "n_targets_in_network":
                len([
                    target
                    for target in targets
                    if target in G
                ]),

            "d_real":
                d_real,

            "d_rand_mean":
                mu,

            "d_rand_std":
                sigma,

            "proximity_z":
                proximity_z,

            "n_random":
                len(random_distances)
        })

    # ========================================================
    # SAVE RESULTS
    # ========================================================

    out = pd.DataFrame(
        results
    )

    out.to_csv(
        "data/network_proximity.csv",
        index=False
    )

    # ========================================================
    # SUMMARY
    # ========================================================

    print(
        "\n" + "=" * 60
    )

    print(
        "STEP 2 COMPLETE"
    )

    print(
        "=" * 60
    )

    print(
        f"Candidates: "
        f"{len(candidates)}"
    )

    print(
        f"Scored: "
        f"{len(out)}"
    )

    print(
        f"Skipped - no targets: "
        f"{skipped_no_targets}"
    )

    print(
        f"Skipped - no network distance: "
        f"{skipped_no_distance}"
    )

    print(
        f"Skipped - insufficient random samples: "
        f"{skipped_random}"
    )

    print(
        "\nOutput:"
    )

    print(
        "data/network_proximity.csv"
    )

    print(
        "\nInterpretation:"
    )

    print(
        "More negative proximity_z = "
        "closer to PD module than random."
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()