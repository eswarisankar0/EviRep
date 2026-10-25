"""
Ground-truth and evaluation contract, checked against the approved artefacts with an INDEPENDENT implementation:
standard-library csv/json only (no pandas, no project code), plus a frozen fixture of the approved labels.

Contract (docs/autonomous_runs/SCIENTIFIC_CONTRACT_TRACEABILITY.md):
  pool       = filtered candidates (stage 00) with >= 1 accepted pre-cutoff PD trial (stage 03 + 03c)
  feature    = trial first_posted <  2021-01-01   (stage 03 CUTOFF_DATE; i.e. on or before 2020-12-31)
  label      = 1 if the compound has >= 1 accepted trial with first_posted >= 2021-01-01 that is not excluded in
               data/label_role_exclusions.csv (TD-032 / D-020 policy P1); outcome = continued clinical
               investigation, not efficacy
  VPS        = VPS_equal_5d (equal-weight mean of five percentile ranks), the approved primary score
If any assertion here fails, an approved artefact changed: that is an owner decision (label re-freeze), never a
test to update silently.
"""
import csv
import hashlib
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUTOFF = "2021-01-01"
D = lambda rel: os.path.join(ROOT, rel)

#: Frozen fixture: the approved positives and the label-trial exclusions' effect (verified 2026-10-20 against the
#: protected artefacts; changing it requires an owner-approved label re-freeze).
APPROVED_POSITIVES = {"Acetylcysteine", "Atomoxetine", "Donepezil", "Galantamine", "Levetiracetam", "Lidocaine",
                      "Melatonin", "Methylphenidate", "Mirabegron", "Pyridostigmine", "Quetiapine", "Rifaximin",
                      "Terazosin", "Varenicline"}
LOST_BY_EXCLUSION = {"Clozapine", "Dexmedetomidine", "Remifentanil"}


def rows(rel):
    with open(D(rel), newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def mann_whitney_auroc(pos, neg):
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


@unittest.skipUnless(os.path.exists(D("data/vps_scores_v2.csv")), "needs the approved artefacts")
class TestGroundTruthContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vps = rows("data/vps_scores_v2.csv")
        cls.pool = {r["compound_name"] for r in cls.vps}
        cls.pre = rows("data/clinical_maturity_precutoff_clean.csv")
        cls.gt = rows("data/ground_truth_postcutoff_clean.csv")
        cls.excl = {r["nct_id"] for r in rows("data/label_role_exclusions.csv")}
        cls.labels = {r["compound_name"]: int(float(r["label"])) for r in cls.vps}

    def test_population_size_and_construction(self):
        filtered = {r["compound_name"] for r in rows("data/pd_candidates_filtered.csv")}
        with_pre_trial = {r["compound_name"] for r in self.pre}
        self.assertEqual(len(self.pool), 90)
        self.assertEqual(len(self.vps), 90)                                   # one row per compound
        self.assertEqual(self.pool, filtered & with_pre_trial)

    def test_cutoff_semantics_on_every_trial(self):
        self.assertTrue(all(r["first_posted"] and r["first_posted"] < CUTOFF for r in self.pre))
        self.assertTrue(all(r["first_posted"] and r["first_posted"] >= CUTOFF for r in self.gt))
        self.assertFalse({r["nct_id"] for r in self.pre} & {r["nct_id"] for r in self.gt})

    def test_every_label_follows_the_rule(self):
        positive = {r["compound_name"] for r in self.gt if r["nct_id"] not in self.excl} & self.pool
        for c in self.pool:
            self.assertEqual(self.labels[c], int(c in positive), c)

    def test_labels_equal_the_frozen_approved_set(self):
        self.assertEqual({c for c, y in self.labels.items() if y}, APPROVED_POSITIVES)
        with_any_label_trial = {r["compound_name"] for r in self.gt} & self.pool
        self.assertEqual(with_any_label_trial - APPROVED_POSITIVES, LOST_BY_EXCLUSION)

    def test_exclusions_refer_to_existing_label_trials(self):
        gt_pairs = {(r["nct_id"], r["compound_name"]) for r in self.gt}
        for r in rows("data/label_role_exclusions.csv"):
            self.assertIn((r["nct_id"], r["compound_name"]), gt_pairs)

    def test_evaluation_report_matches_the_data(self):
        with open(D("data/vps_evaluation_report.json"), encoding="utf-8") as fh:
            rep = json.load(fh)
        n_pos = sum(self.labels.values())
        self.assertEqual((rep["cohort"]["n"], rep["cohort"]["positives"], rep["cohort"]["negatives"]),
                         (90, n_pos, 90 - n_pos))
        self.assertAlmostEqual(rep["cohort"]["prevalence"], n_pos / 90, places=12)
        s = {r["compound_name"]: float(r["VPS_equal_5d"]) for r in self.vps}
        pos = [s[c] for c in self.pool if self.labels[c]]
        neg = [s[c] for c in self.pool if not self.labels[c]]
        primary = next(p for p in rep["primary"] if p["column"] == "VPS_equal_5d")
        self.assertAlmostEqual(primary["auroc"], mann_whitney_auroc(pos, neg), places=12)
        ranked = sorted(self.pool, key=lambda c: -s[c])
        self.assertEqual(len(set(s.values())), 90)          # no ties, so average precision is order-unambiguous
        tp, ap = 0, 0.0
        for i, c in enumerate(ranked, 1):
            if self.labels[c]:
                tp += 1
                ap += tp / i
        self.assertAlmostEqual(primary["auprc"], ap / n_pos, places=12)
        lo, hi = primary["auroc_ci95"]
        self.assertTrue(lo < primary["auroc"] < hi)
        self.assertFalse(rep["calibration"]["applicable"])  # a ranking score, never read as a probability
        for rel, md5 in rep["inputs"].items():               # the report was computed from these exact files
            with open(D(rel), "rb") as fh:
                self.assertEqual(hashlib.md5(fh.read()).hexdigest(), md5, rel)

    def test_auroc_reference_values(self):
        s = {r["compound_name"]: r for r in self.vps}
        def au(col):
            pos = [float(s[c][col]) for c in self.pool if self.labels[c]]
            neg = [float(s[c][col]) for c in self.pool if not self.labels[c]]
            return mann_whitney_auroc(pos, neg)
        self.assertAlmostEqual(au("VPS_equal_5d"), 0.7753759398, places=9)   # approved 5D
        self.assertAlmostEqual(au("VPS_equal"), 0.7001879699, places=9)      # 4D sensitivity

    def test_label_never_enters_the_score(self):
        # flipping a label cannot change any score: scores are a function of feature columns only
        feats = [c for c in self.vps[0] if c.startswith("r_")]
        self.assertEqual(set(feats), {"r_proximity", "r_clinical", "r_literature", "r_safety", "r_molecular"})
        for r in self.vps:
            mean5 = sum(float(r[c]) for c in feats) / 5
            self.assertAlmostEqual(float(r["VPS_equal_5d"]), mean5, places=12, msg=r["compound_name"])

    def test_missing_dimensions_are_neutral_not_negative(self):
        self.assertGreater(sum(1 for r in self.vps if r.get("dimensions_missing")), 0)   # never vacuous
        for r in self.vps:
            missing = [d for d in (r.get("dimensions_missing") or "").split("|") if d]
            for d in missing:
                self.assertEqual(float(r["r_" + d]), 0.5, f"{r['compound_name']}: missing {d} must be neutral 0.5")


if __name__ == "__main__":
    unittest.main()
