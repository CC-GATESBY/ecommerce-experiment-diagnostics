"""Literal synthetic counts and separate arithmetic for the overall ITT table."""
import copy
import csv
from decimal import Decimal
import math
from pathlib import Path
import tempfile
import unittest

from uplift.ate import ROOT, HEADER, aggregate_csv, effects, estimate, independent_formula_check, source_metadata

SPARK = None


class PrerequisiteMetadataTest(unittest.TestCase):
    def test_accepted_receipts_and_profile_shape(self):
        # Metadata only; no real CSV or membership scan.
        raw, member, profile = source_metadata()
        self.assertTrue(raw.is_file() and member.is_file())
        self.assertEqual(set(profile), {"treatment", "conversion", "visit", "exposure"})
        self.assertTrue(all(set(counts) == {"0", "1"} for counts in profile.values()))


def synthetic_rows():
    # Exactly 20 synthetic observations; never use a real record as a fixture.
    return [["synthetic"]*12 + [str(t), str(i < (2 if t == 0 else 5)),
                                str(i < (4 if t == 0 else 7)), str(i < (0 if t == 0 else 6))]
            for t in (0, 1) for i in range(10)]


EXPECTED = [dict(treatment=0, n=10, conversion_count=2, visit_count=4, exposure_count=0),
            dict(treatment=1, n=10, conversion_count=5, visit_count=7, exposure_count=6)]


class FormulaTests(unittest.TestCase):
    def test_hand_rates_difference(self):
        r = estimate(10, 10, 2, 5)
        self.assertEqual([Decimal(r[k]) for k in ("control_rate", "treatment_rate", "absolute_difference")],
                         [Decimal("0.2"), Decimal("0.5"), Decimal("0.3")])

    def test_hand_standard_error(self):
        self.assertAlmostEqual(float(estimate(10, 10, 2, 5)["standard_error"]), math.sqrt(0.041), places=15)

    def test_units_and_relative(self):
        r = estimate(10, 10, 2, 5)
        self.assertEqual([Decimal(r[k]) for k in ("absolute_difference_pp", "absolute_difference_bp", "relative_lift", "incremental_per_10k")],
                         [Decimal("30"), Decimal("3000"), Decimal("1.5"), Decimal("3000")])

    def test_ci_scalar_sufficient_statistics(self):
        # Scalar arithmetic case only; no extra data rows are generated.
        r = estimate(100, 100, 20, 40)
        self.assertAlmostEqual(float(r["ci95_low"]), 0.2-1.96*math.sqrt(0.004), places=15)
        self.assertAlmostEqual(float(r["ci95_high"]), 0.2+1.96*math.sqrt(0.004), places=15)
        self.assertAlmostEqual(float(r["incremental_per_10k_ci_low"]), (0.2-1.96*math.sqrt(0.004))*10000, places=11)

    def test_zero_control_relative_null(self):
        self.assertIsNone(estimate(10, 10, 0, 5)["relative_lift"])

    def test_empty_control(self):
        r = estimate(0, 10, 0, 5)
        self.assertEqual(r["status"], "empty_group")
        self.assertIsNone(r["absolute_difference"])

    def test_empty_treatment(self):
        self.assertEqual(estimate(10, 0, 5, 0)["status"], "empty_group")

    def test_sparse_ci_withheld(self):
        r = estimate(10, 10, 2, 5)
        self.assertEqual(r["status"], "sparse_cells_ci_not_reported")
        self.assertIsNone(r["ci95_low"])

    def test_invalid_sufficient_statistics(self):
        for args in [(-1, 10, 0, 0), (10, 10, 11, 1), (10.0, 10, 2, 2), (True, 10, 0, 1)]:
            with self.subTest(args=args), self.assertRaises(ValueError): estimate(*args)

    def test_negative_direction(self):
        self.assertEqual(Decimal(estimate(100, 100, 40, 20)["absolute_difference"]), Decimal("-0.2"))

    def test_exposure_is_only_descriptive(self):
        r = estimate(10, 10, 0, 6, "exposure")
        self.assertEqual(Decimal(r["absolute_difference"]), Decimal("0.6"))
        self.assertTrue(all(r[k] is None for k in ("relative_lift", "standard_error", "ci95_low", "incremental_per_10k")))

    def test_roles_and_repeat(self):
        self.assertEqual([r["role"] for r in effects(EXPECTED)], ["primary", "secondary", "descriptive"])
        self.assertEqual(effects(EXPECTED), effects(copy.deepcopy(EXPECTED)))

    def test_independent_formula_and_tamper(self):
        groups = [dict(treatment=0,n=100,conversion_count=20,visit_count=30,exposure_count=0),
                  dict(treatment=1,n=100,conversion_count=40,visit_count=50,exposure_count=50)]
        table = effects(groups)
        self.assertTrue(all(c["passed"] for c in independent_formula_check(groups, table)))
        table[0]["absolute_difference"] = "0.3"
        with self.assertRaises(ValueError): independent_formula_check(groups, table)


class SparkAggregateTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(SPARK, "Run through python -m uplift.ate --test")
        (ROOT/".local/t32").mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix="synthetic-", dir=ROOT/".local/t32")
        self.path = Path(self.directory.name)/"synthetic.csv"
        self.rows = synthetic_rows()
        for row in self.rows:
            row[13:] = ["1" if x == "True" else "0" for x in row[13:]]

    def tearDown(self):
        self.directory.cleanup()

    def write(self, rows, header=HEADER):
        with self.path.open("w", newline="") as f:
            w = csv.writer(f); w.writerow(header); w.writerows(rows)

    def test_all_assigned_literal_counts_and_repeat(self):
        self.write(self.rows)
        self.assertEqual(aggregate_csv(SPARK, self.path), EXPECTED)
        self.assertEqual(aggregate_csv(SPARK, self.path), EXPECTED)

    def test_quoted_empty_multiline_fields(self):
        self.rows[0][0] = 'quoted,"value"\nnext line'
        self.rows[1][1] = ""
        self.write(self.rows)
        self.assertEqual(aggregate_csv(SPARK, self.path), EXPECTED)

    def test_invalid_binary_labels(self):
        for bad in ("2", "", "01", " 1"):
            with self.subTest(bad=bad):
                self.rows[0][13] = bad; self.write(self.rows)
                with self.assertRaises(ValueError): aggregate_csv(SPARK, self.path)

    def test_wrong_header(self):
        self.write(self.rows, ["wrong", *HEADER[1:]])
        with self.assertRaises(Exception): aggregate_csv(SPARK, self.path)


if __name__ == "__main__":
    unittest.main()
