"""
Tests for the ClinicalTrials.gov intervention matcher.

Offline and deterministic. The intervention payloads below are VERBATIM copies of
structured fields retrieved live from the ClinicalTrials.gov v2 API on 2026-10-05
(NCT IDs named in each fixture), so the collision classes under test are real
observed data, not invented examples.

The matcher must solve these generally. No test relies on a hardcoded blacklist
of compounds or NCT IDs, and the matcher contains none.

Run:  ./venv/bin/python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import intervention_matcher as im  # noqa: E402


# ---------------------------------------------------------------------------
# Real structured payloads (verbatim from the live API)
# ---------------------------------------------------------------------------

# NCT03567447 - matched by query.intr=Norepinephrine, actually tests Droxidopa.
DROXIDOPA_TRIAL = [
    {"type": "DRUG", "name": "Droxidopa", "armGroupLabels": ["Treatment group"],
     "otherNames": ["NORTHERA"]},
    {"type": "OTHER", "name": "Placebo",
     "armGroupLabels": ["Non treatment group", "Treatment group"]},
]

# NCT06596876 - matched by query.intr=Phenol, actually tests carbidopa/levodopa.
# This trial also supplies Phenol's only post-cutoff (positive) label.
HRG2010_TRIAL = [
    {"type": "DRUG",
     "name": "HRG2010; Sustained-release Carbidopa/Levodopa administered placebo",
     "armGroupLabels": ["HRG2010 and Sustained-release Carbidopa/Levodopa administered placebo"]},
    {"type": "DRUG",
     "name": "Sustained-release Carbidopa/Levodopa; HRG2010 placebo",
     "armGroupLabels": ["Sustained-release Carbidopa/Levodopa and HRG2010 placebo"]},
]

# NCT02577523 - matched by query.intr=Phenol, actually tests ND0612.
ND0612_TRIAL = [
    {"type": "DRUG", "name": "ND0612 (Levodopa/Carbidopa solution)"},
    {"type": "DRUG", "name": "ND0612 (Levodopa/Carbidopa solution) + morning oral dose"},
]

# NCT00666653 - matched by query.intr=Dopamine, actually tests pramipexole.
PRAMIPEXOLE_TRIAL = [{"type": "DRUG", "name": "pramipexole"}]

# NCT00105508 - matched by query.intr=Dopamine, actually tests Sarizotan.
SARIZOTAN_TRIAL = [
    {"type": "DRUG", "name": "Sarizotan"},
    {"type": "DRUG", "name": "Placebo"},
]

# NCT02670161 - catch-all registry study; drug list is in the description.
CATCH_ALL_TRIAL = [
    {"type": "DRUG",
     "name": "Listed for each disorder below, up to three drugs per disorder "
             "(too many characters to list in this field; see Intervention Description)",
     "otherNames": ["See Intervention Description"]},
]

# NCT03258294 - genuine Melatonin trial (note the ® character).
MELATONIN_TRIAL = [
    {"type": "DRUG", "name": "Melatonin(Circadin®)"},
    {"type": "DRUG", "name": "Placebo Oral Tablet"},
]

# NCT02206620 - genuine Donepezil trial.
DONEPEZIL_TRIAL = [{"type": "DRUG", "name": "Donepezil"}]


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


class TestNormalisation(unittest.TestCase):
    def test_case_punctuation_whitespace(self):
        self.assertEqual(im.normalise("  Levodopa/Carbidopa  "), "levodopa carbidopa")

    def test_unicode_registered_mark_stripped(self):
        self.assertEqual(im.normalise("Melatonin(Circadin®)"),
                         "melatonin circadin")

    def test_accents_folded(self):
        self.assertEqual(im.normalise("Levodopà"), "levodopa")

    def test_empty_inputs(self):
        for value in (None, "", "   ", "---"):
            self.assertEqual(im.normalise(value), "")

    def test_tokens(self):
        self.assertEqual(im.tokens("ND0612 (Levodopa/Carbidopa solution)"),
                         ["nd0612", "levodopa", "carbidopa", "solution"])


# ---------------------------------------------------------------------------
# The real collision classes -- all must be rejected
# ---------------------------------------------------------------------------


class TestKnownCollisionsRejected(unittest.TestCase):
    def test_prodrug_norepinephrine_vs_droxidopa(self):
        """Droxidopa is a norepinephrine PRODRUG. The project does not define
        prodrug relationships as equivalent evidence, so this must not match."""
        r = im.match_trial("Norepinephrine", DROXIDOPA_TRIAL)
        self.assertEqual(r["outcome"], im.NO_MATCH)
        self.assertFalse(r["qualifies"])

    def test_chemical_class_phenol_vs_levodopa(self):
        """Levodopa is chemically a phenol. Class membership is not evidence."""
        for payload in (HRG2010_TRIAL, ND0612_TRIAL):
            r = im.match_trial("Phenol", payload)
            self.assertEqual(r["outcome"], im.NO_MATCH, payload[0]["name"])
            self.assertFalse(r["qualifies"])

    def test_pharmacological_class_dopamine_vs_agonists(self):
        for payload in (PRAMIPEXOLE_TRIAL, SARIZOTAN_TRIAL):
            r = im.match_trial("Dopamine", payload)
            self.assertEqual(r["outcome"], im.NO_MATCH)
            self.assertFalse(r["qualifies"])

    def test_excipient_mannitol_vs_droxidopa(self):
        r = im.match_trial("Mannitol", DROXIDOPA_TRIAL)
        self.assertEqual(r["outcome"], im.NO_MATCH)
        self.assertFalse(r["qualifies"])

    def test_catch_all_registry_is_unverifiable_not_a_negative(self):
        """A registry study whose drug list lives in free text cannot confirm OR
        deny the compound. It must not qualify, and must not be recorded as a
        verified negative."""
        for compound in ("Pregabalin", "Acetylsalicylic acid", "Donepezil"):
            r = im.match_trial(compound, CATCH_ALL_TRIAL)
            self.assertEqual(r["outcome"], im.UNVERIFIABLE, compound)
            self.assertFalse(r["qualifies"])

    def test_substring_collision_rejected(self):
        """Token-boundary matching: 'Phenol' must not match 'Phenolphthalein'."""
        r = im.match_trial("Phenol", [{"type": "DRUG", "name": "Phenolphthalein"}])
        self.assertEqual(r["outcome"], im.NO_MATCH)

    def test_reverse_substring_collision_rejected(self):
        r = im.match_trial("Dopa", [{"type": "DRUG", "name": "Levodopa"}])
        self.assertEqual(r["outcome"], im.NO_MATCH)


# NCT01927055 - matched by query.intr=Mannitol. Mannitol is the PLACEBO filler.
DROXIDOPA_PLACEBO_MANNITOL = [
    {"type": "DRUG", "name": "Droxidopa",
     "otherNames": ["L-threo-3,4-dihydroxyphenylserine, L-threo-DOPS, or L-DOPS"]},
    {"type": "OTHER", "name": "Placebo", "otherNames": ["Mannitol"]},
]

# NCT01176240 - same pattern, filler listed alongside another term.
DROXIDOPA_PLACEBO_MANNITOL_2 = [
    {"type": "DRUG", "name": "Droxidopa",
     "otherNames": ["Northera", "L-DOPS", "L-threo-dihydroxyphenylserine", "SM-5688"]},
    {"type": "OTHER", "name": "Placebo", "otherNames": ["Mannitol, Sugar Pill"]},
]

# NCT03823638 - a GENUINE mannitol trial, for contrast.
REAL_MANNITOL_TRIAL = [{"type": "DRUG", "name": "Oral D-Mannitol of Placebo"}]


class TestControlArmExclusion(unittest.TestCase):
    """Excipients named in a placebo arm are not evidence of being studied."""

    def test_mannitol_as_placebo_filler_rejected(self):
        for payload in (DROXIDOPA_PLACEBO_MANNITOL, DROXIDOPA_PLACEBO_MANNITOL_2):
            r = im.match_trial("Mannitol", payload)
            self.assertEqual(r["outcome"], im.NO_MATCH)
            self.assertFalse(r["qualifies"])
            self.assertIn("control", r["reason"])

    def test_real_mannitol_trial_still_accepted(self):
        """The genuine trial must NOT be lost to the control-arm rule."""
        r = im.match_trial("Mannitol", REAL_MANNITOL_TRIAL)
        self.assertEqual(r["outcome"], im.MATCHED)
        self.assertTrue(r["qualifies"])

    def test_droxidopa_still_matches_its_own_trial(self):
        r = im.match_trial("Droxidopa", DROXIDOPA_PLACEBO_MANNITOL)
        self.assertEqual(r["outcome"], im.MATCHED)

    def test_control_detection_is_structural(self):
        self.assertTrue(im.is_control_intervention({"name": "Placebo"}))
        self.assertTrue(im.is_control_intervention({"name": "Placebo Oral Tablet"}))
        self.assertTrue(im.is_control_intervention({"name": "Sugar Pill"}))
        # Names that also carry real agents are NOT control arms.
        self.assertFalse(im.is_control_intervention(
            {"name": "HRG2010; Sustained-release Carbidopa/Levodopa administered placebo"}))
        self.assertFalse(im.is_control_intervention({"name": "Droxidopa"}))
        self.assertFalse(im.is_control_intervention({"name": ""}))


class TestSynonymMatchingIsExactOnly(unittest.TestCase):
    """ChEMBL synonym lists contain noisy entries (observed live: 'Medopa' and
    'Dobutamine a' under Dopamine). Token-run matching on those could credit a
    different drug's trial, so synonyms match only on exact equality."""

    def test_noisy_synonym_does_not_token_match(self):
        aliases = im.build_alias_set("Dopamine", synonyms=["Medopa"])
        trial = [{"type": "DRUG", "name": "Medopa 250mg modified release tablets"}]
        r = im.match_trial("Dopamine", trial, aliases)
        self.assertEqual(r["outcome"], im.NO_MATCH)

    def test_exact_synonym_still_matches(self):
        aliases = im.build_alias_set("Dopamine", synonyms=["Medopa"])
        r = im.match_trial("Dopamine", [{"type": "DRUG", "name": "Medopa"}], aliases)
        self.assertEqual(r["outcome"], im.MATCHED)
        self.assertEqual(r["match_source"], "chembl_synonym")

    def test_compound_name_still_token_matches(self):
        """The compound's own name keeps token matching for combination products."""
        r = im.match_trial("Levodopa", ND0612_TRIAL)
        self.assertEqual(r["outcome"], im.MATCHED)
        self.assertEqual(r["match_type"], "token_name")


# ---------------------------------------------------------------------------
# Genuine matches must still be accepted
# ---------------------------------------------------------------------------


class TestGenuineMatchesAccepted(unittest.TestCase):
    def test_exact_name(self):
        r = im.match_trial("Donepezil", DONEPEZIL_TRIAL)
        self.assertEqual(r["outcome"], im.MATCHED)
        self.assertEqual(r["match_type"], "exact_name")
        self.assertTrue(r["qualifies"])

    def test_case_insensitive_exact(self):
        r = im.match_trial("PRAMIPEXOLE", PRAMIPEXOLE_TRIAL)
        self.assertEqual(r["outcome"], im.MATCHED)

    def test_unicode_name_matches_by_token(self):
        r = im.match_trial("Melatonin", MELATONIN_TRIAL)
        self.assertEqual(r["outcome"], im.MATCHED)
        self.assertEqual(r["match_type"], "token_name")

    def test_combination_product_token_match(self):
        """'Levodopa' genuinely IS in "ND0612 (Levodopa/Carbidopa solution)"."""
        r = im.match_trial("Levodopa", ND0612_TRIAL)
        self.assertEqual(r["outcome"], im.MATCHED)
        self.assertTrue(r["qualifies"])
        self.assertIn("levodopa", im.normalise(r["matched_intervention"]))

    def test_carbidopa_also_matches_combination(self):
        r = im.match_trial("Carbidopa", HRG2010_TRIAL)
        self.assertEqual(r["outcome"], im.MATCHED)

    def test_trade_name_via_othernames(self):
        """Droxidopa's trade name NORTHERA appears in otherNames."""
        aliases = im.build_alias_set("Droxidopa")
        r = im.match_trial("Droxidopa", DROXIDOPA_TRIAL, aliases)
        self.assertEqual(r["outcome"], im.MATCHED)
        self.assertEqual(r["match_type"], "exact_name")

    def test_verified_synonym_rescues_a_real_trial(self):
        """A trial naming only the trade name must match when that trade name is
        supplied by an authoritative source."""
        aliases = im.build_alias_set("Droxidopa", trade_names=["NORTHERA"])
        trial = [{"type": "DRUG", "name": "NORTHERA"}]
        r = im.match_trial("Droxidopa", trial, aliases)
        self.assertEqual(r["outcome"], im.MATCHED)
        self.assertEqual(r["match_source"], "chembl_trade_name")
        self.assertEqual(r["matched_alias"], "NORTHERA")

    def test_synonym_does_not_rescue_a_collision(self):
        """Supplying real norepinephrine synonyms must NOT make the droxidopa
        trial match -- droxidopa is not a synonym of norepinephrine."""
        aliases = im.build_alias_set(
            "Norepinephrine",
            synonyms=["Noradrenaline", "Levarterenol"],
            trade_names=["Levophed"],
        )
        r = im.match_trial("Norepinephrine", DROXIDOPA_TRIAL, aliases)
        self.assertEqual(r["outcome"], im.NO_MATCH)


# ---------------------------------------------------------------------------
# Failure modes must stay distinguishable
# ---------------------------------------------------------------------------


class TestOutcomeDistinctions(unittest.TestCase):
    def test_api_failure_is_not_no_match(self):
        r = im.match_trial("Donepezil", None, fetch_ok=False)
        self.assertEqual(r["outcome"], im.API_FAILURE)
        self.assertFalse(r["qualifies"])

    def test_missing_interventions_field_is_unverifiable_not_api_failure(self):
        """A retrieved record with no structured intervention list (observational
        studies) is UNVERIFIABLE. API_FAILURE is reserved for records that could
        not be retrieved at all."""
        r = im.match_trial("Donepezil", None)
        self.assertEqual(r["outcome"], im.UNVERIFIABLE)
        self.assertFalse(r["qualifies"])

    def test_api_failure_requires_fetch_failure(self):
        self.assertEqual(im.match_trial("X", None, fetch_ok=False)["outcome"],
                         im.API_FAILURE)
        self.assertEqual(im.match_trial("X", [], fetch_ok=True)["outcome"],
                         im.UNVERIFIABLE)

    def test_empty_intervention_list_is_unverifiable(self):
        r = im.match_trial("Donepezil", [])
        self.assertEqual(r["outcome"], im.UNVERIFIABLE)

    def test_all_four_outcomes_are_distinct(self):
        self.assertEqual(len(set(im.OUTCOMES)), 4)

    def test_only_matched_qualifies(self):
        cases = [
            im.match_trial("Donepezil", DONEPEZIL_TRIAL),
            im.match_trial("Phenol", HRG2010_TRIAL),
            im.match_trial("Donepezil", CATCH_ALL_TRIAL),
            im.match_trial("Donepezil", None, fetch_ok=False),
        ]
        for r in cases:
            self.assertEqual(r["qualifies"], r["outcome"] == im.MATCHED, r["outcome"])

    def test_every_result_carries_a_reason(self):
        for r in (im.match_trial("Phenol", HRG2010_TRIAL),
                  im.match_trial("Donepezil", DONEPEZIL_TRIAL),
                  im.match_trial("Donepezil", CATCH_ALL_TRIAL),
                  im.match_trial("X", None, fetch_ok=False)):
            self.assertTrue(r["reason"])


# ---------------------------------------------------------------------------
# Alias hygiene
# ---------------------------------------------------------------------------


class TestAliasSet(unittest.TestCase):
    def test_compound_name_always_first(self):
        a = im.build_alias_set("Donepezil", synonyms=["Aricept"])
        self.assertEqual(a[0]["source"], "compound_name")

    def test_short_aliases_dropped(self):
        a = im.build_alias_set("Dopamine", synonyms=["DA", "L"])
        self.assertEqual([x["alias"] for x in a], ["Dopamine"])

    def test_duplicates_collapsed(self):
        a = im.build_alias_set("Melatonin", synonyms=["melatonin", "MELATONIN"])
        self.assertEqual(len(a), 1)

    def test_no_synonyms_invented(self):
        a = im.build_alias_set("Norepinephrine")
        self.assertEqual([x["alias"] for x in a], ["Norepinephrine"])

    def test_sources_labelled(self):
        a = im.build_alias_set("Donepezil", synonyms=["E2020"], trade_names=["Aricept"])
        self.assertEqual({x["source"] for x in a},
                         {"compound_name", "chembl_synonym", "chembl_trade_name"})

    def test_too_short_compound_is_unverifiable(self):
        r = im.match_trial("Fe", DONEPEZIL_TRIAL)
        self.assertEqual(r["outcome"], im.UNVERIFIABLE)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestAmbiguousAliasFilter(unittest.TestCase):
    """ChEMBL synonym lists contain related-but-DISTINCT drugs. Observed live:
    "citalopram" is listed under Escitalopram and "doxycycline" under
    Tetracycline. An alias that is itself another study compound's name must be
    refused, or one compound inherits another's trials."""

    def test_sibling_drug_alias_refused(self):
        others = {im.normalise("Citalopram")}
        a = im.build_alias_set("Escitalopram", synonyms=["citalopram"],
                               ambiguous_names=others)
        self.assertEqual([x["alias"] for x in a], ["Escitalopram"])

    def test_refused_alias_prevents_the_false_match(self):
        """NCT04590612 lists Citalopram; Escitalopram must NOT match it."""
        trial = [{"type": "DRUG", "name": "Citalopram"},
                 {"type": "DRUG", "name": "Carbidopa-Levodopa 25 Mg-100 Mg Oral Tablet"}]
        bad = im.build_alias_set("Escitalopram", synonyms=["citalopram"])
        self.assertEqual(im.match_trial("Escitalopram", trial, bad)["outcome"],
                         im.MATCHED)          # without the filter: false positive
        good = im.build_alias_set("Escitalopram", synonyms=["citalopram"],
                                  ambiguous_names={im.normalise("Citalopram")})
        self.assertEqual(im.match_trial("Escitalopram", trial, good)["outcome"],
                         im.NO_MATCH)         # with the filter: correctly rejected

    def test_class_sibling_doxycycline_refused(self):
        trial = [{"type": "DRUG", "name": "Doxycycline"}]
        good = im.build_alias_set("Tetracycline", synonyms=["doxycycline"],
                                  ambiguous_names={im.normalise("Doxycycline")})
        self.assertEqual(im.match_trial("Tetracycline", trial, good)["outcome"],
                         im.NO_MATCH)

    def test_legitimate_trade_names_survive_the_filter(self):
        """Trade names that are not other study compounds must be kept."""
        others = {im.normalise("Citalopram"), im.normalise("Doxycycline")}
        for compound, alias in [("Zonisamide", "Zonegran"), ("Droxidopa", "L-DOPS"),
                                ("Ioflupane I 123", "Datscan"),
                                ("Acetylcysteine", "n-acetyl cysteine")]:
            a = im.build_alias_set(compound, synonyms=[alias], ambiguous_names=others)
            self.assertIn(alias, [x["alias"] for x in a], compound)

    def test_compound_own_name_never_filtered(self):
        """Even if another compound shares the name, the compound keeps its own."""
        a = im.build_alias_set("Dopamine", ambiguous_names={im.normalise("Dopamine")})
        self.assertEqual([x["alias"] for x in a], ["Dopamine"])


class TestDeterminism(unittest.TestCase):
    def test_repeated_calls_identical(self):
        a = im.match_trial("Phenol", HRG2010_TRIAL)
        b = im.match_trial("Phenol", HRG2010_TRIAL)
        self.assertEqual(a, b)

    def test_alias_order_does_not_change_match_outcome(self):
        a1 = im.build_alias_set("Droxidopa", synonyms=["NORTHERA", "L-DOPS"])
        a2 = im.build_alias_set("Droxidopa", synonyms=["L-DOPS", "NORTHERA"])
        t = [{"type": "DRUG", "name": "L-DOPS"}]
        self.assertEqual(im.match_trial("Droxidopa", t, a1)["outcome"],
                         im.match_trial("Droxidopa", t, a2)["outcome"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
