"""Historical molecular reconstruction (scripts/vps_molecular_historical.py): stage-08 rules on 20.11 inputs."""
import gzip
import importlib.util
import os
import tempfile
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("vmh", os.path.join(ROOT, "scripts", "vps_molecular_historical.py"))
vmh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vmh)

UNIPROT = """<?xml version="1.0"?><uniprot xmlns="http://uniprot.org/uniprot">
<entry><accession>P1</accession>
 <dbReference type="Ensembl" id="ENST1"><property type="gene ID" value="ENSG_A.4"/></dbReference>
 <dbReference type="Reactome" id="R-HSA-1"/><dbReference type="Reactome" id="R-HSA-2"/></entry>
<entry><accession>P2</accession>
 <dbReference type="Ensembl" id="ENST2"><property type="gene ID" value="ENSG_M"/></dbReference>
 <dbReference type="Reactome" id="R-HSA-2"/></entry>
<entry><accession>P3</accession>
 <dbReference type="Ensembl" id="ENST3"><property type="gene ID" value="ENSG_OTHER"/></dbReference>
 <dbReference type="Reactome" id="R-HSA-9"/></entry>
</uniprot>"""


class TestHistoricalMolecular(unittest.TestCase):
    def test_uniprot_reactome_versionless_and_filtered(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "u.xml.gz")
            with gzip.open(p, "wt") as fh:
                fh.write(UNIPROT)
            got = vmh.uniprot_reactome(p, {"ENSG_A", "ENSG_M"})
        self.assertEqual(got, {"ENSG_A": {"R-HSA-1", "R-HSA-2"}, "ENSG_M": {"R-HSA-2"}})

    def test_module_uses_module_datatypes_and_threshold(self):
        rows = {"G1": (0.9, {"genetic_association": 0.5}),
                "G2": (0.8, {"affected_pathway": 0.9}),           # pathway-only evidence never enters the module
                "G3": (0.7, {"animal_model": 0.05}),              # below 0.10
                "G4": (0.6, {"literature": 0.9, "rna_expression": 0.2})}
        self.assertEqual(vmh.module_2011(rows), {"G1", "G4"})

    def test_components_and_td042(self):
        rows = {"ENSG_A": (0.5, {"affected_pathway": 0.4, "literature": 0.99}), "ENSG_M": (0.9, {"genetic_association": 0.7})}
        path_of = {"ENSG_A": {"R-HSA-1", "R-HSA-2"}, "ENSG_M": {"R-HSA-2"}}
        d, pw, n = vmh.components(["ENSG_A"], path_of, {"ENSG_M"}, rows, False)
        self.assertEqual((d, pw, n), (0.4, 0.5, 2))                     # literature excluded from direct
        # drug whose own target is the module gene: pathway credit only through OTHER module genes (TD-042)
        _, pw_own, _ = vmh.components(["ENSG_M"], path_of, {"ENSG_M"}, rows, False)
        _, pw_td, _ = vmh.components(["ENSG_M"], path_of, {"ENSG_M"}, rows, True)
        self.assertEqual((pw_own, pw_td), (1.0, 0.0))
        self.assertTrue(np.isnan(vmh.components([], path_of, {"ENSG_M"}, rows, False)[0]))   # no target: unmeasured

    def test_dated_chembl_targets_human_proteins_only(self):
        import json
        with tempfile.TemporaryDirectory() as root:
            d = os.path.join(root, vmh.D)
            os.makedirs(d)
            mech = [{"molecule_chembl_id": "SALT1", "parent_molecule_chembl_id": "DRUG1", "target_chembl_id": "T1"},
                    {"molecule_chembl_id": "DRUG1", "parent_molecule_chembl_id": "DRUG1", "target_chembl_id": "T2"},
                    {"molecule_chembl_id": "DRUG2", "parent_molecule_chembl_id": "DRUG2", "target_chembl_id": "TB"}]
            xref = lambda e: [{"xref_src_db": "EnsemblGene", "xref_id": e}, {"xref_src_db": "GoComponent", "xref_id": "GO:1"}]
            tg = [{"target_chembl_id": "T1", "tax_id": 9606, "target_components": [{"component_type": "PROTEIN", "target_component_xrefs": xref("ENSG1")}]},
                  {"target_chembl_id": "T2", "tax_id": 9606, "target_components": [{"component_type": "PROTEIN", "target_component_xrefs": xref("ENSG2")},
                                                                                     {"component_type": "PROTEIN", "target_component_xrefs": xref("ENSG3")}]},
                  {"target_chembl_id": "TB", "tax_id": 562, "target_components": [{"component_type": "PROTEIN", "target_component_xrefs": xref("ENSGX")}]}]
            for rel, rows in ((vmh.MECH_2006, mech), (vmh.TARGET_2006, tg)):
                with gzip.open(os.path.join(root, rel), "wt") as fh:
                    fh.write("\n".join(json.dumps(r) for r in rows) + "\n")
            got = vmh.chembl_targets_2006(root, {"DRUG1", "DRUG2", "DRUG3"})
        self.assertEqual(got["DRUG1"], ["ENSG1", "ENSG2", "ENSG3"])        # salt form mapped through its parent
        self.assertEqual(got["DRUG2"], [])                                  # bacterial target: no human target
        self.assertNotIn("DRUG3", got)                                      # no 2020 mechanism at all


if __name__ == "__main__":
    unittest.main()
