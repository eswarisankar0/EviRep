"""Trial-paper linkage used by scripts/vps_evidence_overlap.py (registry DataBank and NCT IDs in the text)."""
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("veo", os.path.join(ROOT, "scripts", "vps_evidence_overlap.py"))
veo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(veo)

XML = """<?xml version="1.0" ?><PubmedArticleSet>
<PubmedArticle><MedlineCitation><PMID>1</PMID><Article><ArticleTitle>Trial of X</ArticleTitle>
<Abstract><AbstractText>Registered as nct 01234567 and <i>NCT07654321</i>.</AbstractText></Abstract>
<DataBankList><DataBank><DataBankName>ClinicalTrials.gov</DataBankName>
<AccessionNumberList><AccessionNumber>NCT01234567</AccessionNumber></AccessionNumberList></DataBank>
<DataBank><DataBankName>GENBANK</DataBankName><AccessionNumberList><AccessionNumber>NCT99999999</AccessionNumber>
</AccessionNumberList></DataBank></DataBankList></Article></MedlineCitation></PubmedArticle>
<PubmedArticle><MedlineCitation><PMID>2</PMID><Article><ArticleTitle>No registry</ArticleTitle></Article>
</MedlineCitation></PubmedArticle></PubmedArticleSet>"""


class TestTrialLinks(unittest.TestCase):
    def test_databank_and_text_ids(self):
        links = veo.trial_links(XML)
        self.assertEqual(links["1"]["databank"], {"NCT01234567"})       # other databanks ignored
        self.assertEqual(links["1"]["text"], {"NCT07654321"})           # text IDs not already in the databank
        self.assertEqual(links["2"], {"databank": set(), "text": set()})

    def test_partial_numbers_are_not_ids(self):
        x = XML.replace("NCT07654321", "NCT0765432")
        self.assertEqual(veo.trial_links(x)["1"]["text"], set())


if __name__ == "__main__":
    unittest.main()
