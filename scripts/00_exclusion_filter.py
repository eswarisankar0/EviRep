"""
Exclusion filter: removes basic nutrients, vitamins, amino acids, and
electrolytes from the candidate pool before scoring. These are
mechanistically non-specific (broad enzymatic/cofactor roles) and
inflate network-proximity and literature scores without representing
targeted drug repurposing candidates. Documented explicitly for
methodological transparency in the paper.
"""
import pandas as pd

EXCLUSION_LIST = [
    # Vitamins
    "Vitamin C", "Vitamin D", "Vitamin E", "Vitamin A", "Vitamin K",
    "Riboflavin", "Thiamine", "Niacin", "Pyridoxine", "Pyridoxal",
    "Biotin", "Folic Acid", "Cyanocobalamin", "Hydroxocobalamin",
    "Cholecalciferol", "Calcidiol", "Tetrahydrofolic acid",
    # Amino acids
    "L-Valine", "L-Alanine", "L-Isoleucine", "L-Leucine", "L-Phenylalanine",
    "L-Histidine", "L-Arginine", "L-Lysine", "L-Serine", "L-Glutamine",
    "L-Aspartic Acid", "L-Methionine", "L-Tyrosine", "L-Cysteine",
    "L-Tryptophan", "Glycine", "S-Adenosylmethionine",
    # Common cofactors/electrolytes/basic metabolites
    "Choline", "Creatine", "Adenine", "Adenosine", "Glutathione",
    "Iron", "Calcium", "Magnesium", "Zinc", "Potassium", "Sodium",
    "Caffeine", "Nicotine",  # borderline -- see note below
]

def main():
    candidates = pd.read_csv("data/pd_candidates.csv")
    before = len(candidates)
    filtered = candidates[~candidates["compound_name"].isin(EXCLUSION_LIST)]
    after = len(filtered)
    filtered.to_csv("data/pd_candidates_filtered.csv", index=False)
    print(f"Candidates: {before} -> {after} (removed {before - after})")
    print(f"Saved to data/pd_candidates_filtered.csv")

if __name__ == "__main__":
    main()