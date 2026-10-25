"""
TD-042: with `pathway_excludes_drug_targets`, a pathway counts as a PD pathway only through a PD module
gene that is not one of the drug's own targets. Edge cases: a single target that is itself a module
gene, several targets, mixed pathways, duplicate pathway entries, no targets, the flag off (approved
baseline rule), provenance, and the stage-08 options used for the offline like-for-like re-score.
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import molecular_agent as ma  # noqa: E402

_spec = importlib.util.spec_from_file_location("step08_td042", os.path.join(ROOT, "scripts", "08_molecular_pathway.py"))
step08 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(step08)


def module(genes, pathways):
    m = ma.DiseaseModule(disease_id="MONDO_0005180", disease_name="Parkinson's disease")
    for g in genes:
        m.genes[g] = {"ensembl_id": g, "gene_symbol": g.replace("ENSG_", "")}
    for pid, members in pathways.items():
        m.pathway_to_genes[pid] = set(members)
    return m


def target(g):
    return {"ensembl_id": g, "gene_symbol": g.replace("ENSG_", ""), "action_type": "INHIBITOR",
            "mechanism_of_action": "x", "source": "ChEMBL", "references": []}


def details(spec):
    return {g: {"pathways": [{"pathwayId": p, "pathway": p, "topLevelTerm": None} for p in ps]} for g, ps in spec.items()}


def run(targets, spec, mod, on=True):
    cfg = ma.MolecularAgentConfig(pathway_excludes_drug_targets=on)
    tg = [target(g) for g in targets]
    det = details(spec)
    chain, pathways, evidence = ma.build_mechanistic_chain("Drug", "CHEMBL1", tg, det, mod, cfg)
    score = ma.score_molecular_plausibility(tg, det, pathways, mod, cfg)
    return pathways, evidence, score["components"]["pathway_overlap"]


class TestRule(unittest.TestCase):
    def test_target_that_is_the_only_module_gene_gets_no_pathway_credit(self):
        mod = module(["ENSG_A"], {"R1": ["ENSG_A"], "R2": ["ENSG_A"]})
        pw, ev, pc = run(["ENSG_A"], {"ENSG_A": ["R1", "R2"]}, mod)
        self.assertEqual(pc, 0.0)
        self.assertFalse(any(p["in_disease_module"] for p in pw))
        self.assertEqual({tuple(p["drug_targets_excluded_from_shared"]) for p in pw}, {("A",)})
        self.assertFalse([e for e in ev if e["tier"] == ma.EvidenceTier.INDIRECT])

    def test_flag_off_reproduces_the_baseline_rule(self):
        mod = module(["ENSG_A"], {"R1": ["ENSG_A"], "R2": ["ENSG_A"]})
        pw, _, pc = run(["ENSG_A"], {"ENSG_A": ["R1", "R2"]}, mod, on=False)
        self.assertEqual(pc, 1.0)
        self.assertNotIn("drug_targets_excluded_from_shared", pw[0])

    def test_other_module_genes_still_count_and_only_they_are_named(self):
        mod = module(["ENSG_A", "ENSG_B"], {"R1": ["ENSG_A", "ENSG_B"], "R2": ["ENSG_A"]})
        pw, ev, pc = run(["ENSG_A"], {"ENSG_A": ["R1", "R2"]}, mod)
        self.assertEqual(pc, 0.5)
        r1 = [p for p in pw if p["pathway_id"] == "R1"][0]
        self.assertEqual(r1["disease_module_genes_in_pathway"], ["B"])
        self.assertTrue(all(e["claim"].endswith("gene(s): B") for e in ev if e["tier"] == ma.EvidenceTier.INDIRECT))

    def test_all_of_the_drugs_targets_are_excluded_not_only_the_strongest(self):
        mod = module(["ENSG_A", "ENSG_B"], {"R1": ["ENSG_A", "ENSG_B"]})
        _, _, pc = run(["ENSG_A", "ENSG_B"], {"ENSG_A": ["R1"], "ENSG_B": ["R1"]}, mod)
        self.assertEqual(pc, 0.0)

    def test_a_pathway_listed_by_two_targets_counts_once(self):
        mod = module(["ENSG_C"], {"R1": ["ENSG_C"], "R2": []})
        _, _, pc = run(["ENSG_A", "ENSG_B"], {"ENSG_A": ["R1", "R2"], "ENSG_B": ["R1"]}, mod)
        self.assertEqual(pc, 0.5)                     # distinct pathways R1 (shared via C) and R2

    def test_no_targets_and_no_pathways(self):
        mod = module(["ENSG_A"], {"R1": ["ENSG_A"]})
        self.assertEqual(run([], {}, mod)[2], 0.0)
        self.assertEqual(run(["ENSG_A"], {"ENSG_A": []}, mod)[2], 0.0)


class TestStage08Options(unittest.TestCase):
    def test_offline_session_never_calls_the_network(self):
        cfg = ma.MolecularAgentConfig(max_retries=0, use_cache=False)
        client = ma.OpenTargetsClient(cfg, session=step08._OfflineSession())
        with self.assertRaises(ma.OpenTargetsUnavailable):
            client.query("{ x }", {})

    def test_resolutions_are_restored_in_run_agent_form(self):
        rec = {"drug": "Rifampicin", "chembl_id": "CHEMBL374478", "drug_normalized": "RIFAMPIN",
               "normalization": {"match_type": "exact_synonym", "candidates_considered": [{"id": "CHEMBL374478"}]}}
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
            fh.write(json.dumps(rec) + "\n")
        try:
            r = step08.load_resolutions(fh.name)["Rifampicin"]
        finally:
            os.remove(fh.name)
        self.assertEqual(r, {"chembl_id": "CHEMBL374478", "resolved_name": "RIFAMPIN", "match_type": "exact_synonym",
                             "candidates": [{"id": "CHEMBL374478"}]})


if __name__ == "__main__":
    unittest.main()
