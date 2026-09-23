"""Literal arithmetic expectations for synthetic COST-01; no business data."""
from decimal import Decimal as D
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.cost_scenarios import (
    Basket, build_tables, load_config, normalized, pairwise_boundary,
    run, strategies, threshold,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/cost_scenarios.json"


def main_rows(**kwargs):
    return {r["strategy"]: r for r in strategies(Basket("40", "0.30", 2), **kwargs)}


class CostScenarioTests(unittest.TestCase):
    def test_main_case_literal_contributions(self):
        actual = {k: r["unit_contribution"] for k, r in main_rows().items()}
        self.assertEqual(actual, dict(REFERENCE=D(8), ABSORB=D(2), PASS_HALF=D(5),
                                     PASS_FULL=D(8), ADD_SAME_CATEGORY=D(4), ADD_NEW_CATEGORY=D(1)))

    def test_zero_fee_is_not_a_tax_free_business_claim(self):
        rows = main_rows(fee="0")
        self.assertEqual([rows[k]["unit_contribution"] for k in
                          ("REFERENCE", "ABSORB", "PASS_HALF", "PASS_FULL")], [D(8)]*4)
        self.assertEqual(rows["ADD_SAME_CATEGORY"]["unit_contribution"], D(10))
        self.assertEqual(rows["ADD_NEW_CATEGORY"]["unit_contribution"], D(10))
        self.assertTrue(all(r["fixed_charge"] == 0 for r in rows.values()))

    def test_extra_category_at_same_sales_and_cost(self):
        a = strategies(Basket("40", "0.30", 1))[1]
        b = strategies(Basket("40", "0.30", 2))[1]
        self.assertEqual((a["S"], a["C"], a["L"]), (b["S"], b["C"], b["L"]))
        self.assertEqual(b["unit_contribution"]-a["unit_contribution"], D(-3))

    def test_pass_through_keeps_absolute_goods_cost(self):
        rows = main_rows()
        self.assertEqual([rows[k]["C"] for k in ("ABSORB", "PASS_HALF", "PASS_FULL")], [D(28)]*3)
        self.assertEqual((rows["PASS_HALF"]["S"], rows["PASS_FULL"]["S"]), (D(43), D(46)))
        self.assertNotEqual(rows["PASS_FULL"]["C"], D("0.7")*D(46))

    def test_added_goods_increase_both_goods_and_fulfillment_costs(self):
        for key, h in (("ADD_SAME_CATEGORY", 2), ("ADD_NEW_CATEGORY", 3)):
            r = main_rows()[key]
            self.assertEqual((r["S"], r["C"], r["L"], r["H_strategy"]), (D(50), D(35), D(5), h))

    def test_two_references_have_different_probability_thresholds(self):
        self.assertEqual(threshold(8, 8)["allowed_probability_decline"], D(0))
        self.assertEqual(threshold(2, 8)["allowed_probability_decline"], D("0.75"))
        self.assertEqual(threshold(8, 5)["r_required"], D("1.6"))
        self.assertEqual(threshold(8, 5)["required_probability_lift"], D("0.6"))
        self.assertEqual(threshold(8, 5)["max_p_ref_if_lift_required"], D("0.625"))
        self.assertIsNone(threshold(8, 5)["allowed_probability_decline"])

    def test_nonpositive_values_do_not_create_spurious_ratios(self):
        for ref in (0, -4):
            for strategy in (-2, 0, 8):
                r = threshold(ref, strategy)
                self.assertEqual(r["status"], "reference_nonpositive_ratio_not_applicable")
                self.assertIsNone(r["r_required"])
        for strategy in (0, -1):
            r = threshold(8, strategy)
            self.assertEqual(r["status"], "strategy_nonpositive_cannot_recover_positive_reference")
            self.assertIsNone(r["r_required"])

    def test_invalid_domains_rejected_without_clipping(self):
        for args in (("0", ".3", 1), ("-20", ".3", 1), ("40", "-0.1", 1),
                     ("40", "1.01", 1), ("40", ".3", 0), ("40", ".3", 1.5),
                     ("40", ".3", True), ("NaN", ".3", 1), (40.0, ".3", 1)):
            with self.assertRaises(ValueError):
                Basket(*args)
        for r in ("-0.1", "NaN", "Infinity", "bad", .9, True):
            with self.assertRaises(ValueError):
                normalized(8, r)
        with self.assertRaises(ValueError):
            main_rows(fee="-3")
        self.assertEqual(normalized(5, "1.6"), D(8))  # A ratio may exceed one.

    def test_requested_075_example_and_pairwise_boundary(self):
        value = normalized(8, "0.75")
        self.assertEqual(value, D(6))
        self.assertEqual((value-D(2), value-D(8)), (D(4), D(-2)))
        self.assertEqual(pairwise_boundary(8, 4), D("0.5"))
        self.assertEqual(pairwise_boundary(8, 5), D("0.625"))
        self.assertEqual(pairwise_boundary(4, 1), D("0.25"))
        self.assertIsNone(pairwise_boundary(8, 0))

    def test_grid_complete_and_reference_probabilities_fixed(self):
        tables = build_tables(load_config(CONFIG))
        self.assertEqual({k: len(v) for k, v in tables.items()}, {
            "synthetic_baskets.csv": 27, "strategy_comparison.csv": 162,
            "demand_thresholds.csv": 324, "demand_sensitivity.csv": 594})
        main = [r for r in tables["demand_sensitivity.csv"] if r["basket_id"] == "S40_m30_H2"]
        fixed = [r for r in main if r["probability_role"] == "fixed_reference"]
        self.assertEqual([(r["strategy"], r["r"], r["normalized_expected_contribution"])
                          for r in fixed], [("REFERENCE", D(1), D(8)), ("ABSORB", D(1), D(2))])
        full = [r["normalized_expected_contribution"] for r in main if r["strategy"] == "PASS_FULL"]
        self.assertEqual(full, list(map(D, ["8", "7.6", "7.2", "6.4", "5.6"])))
        self.assertTrue(all(r["evidence_type"] == "synthetic_scenario" and
                            r["currency"] == "EUR_scenario" for rows in tables.values() for r in rows))

    def test_frozen_config_rejects_unrequested_grid_or_main_case(self):
        for key, value in (("net_sales", ["0", "40", "80"]),
                           ("demand_retention", ["1", "0.9", "0.8"]),
                           ("main_case", {"S0": "80", "m0": ".3", "H": 2})):
            data = json.loads(CONFIG.read_text()); data[key] = value
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp)/"config.json"; p.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    load_config(p)

    def test_cross_process_reproducibility_and_no_overwrite(self):
        before = hashlib.sha256(CONFIG.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            first, second = Path(tmp)/"first", Path(tmp)/"second"
            receipt = run(CONFIG, first)
            completed = subprocess.run([sys.executable, str(ROOT/"scripts/cost_scenarios.py"),
                                        "--config", str(CONFIG), "--output-dir", str(second)],
                                       check=True, capture_output=True, text=True)
            self.assertEqual(receipt, json.loads(completed.stdout))
            for p in first.iterdir():
                self.assertEqual(p.read_bytes(), (second/p.name).read_bytes())
            with self.assertRaises(FileExistsError):
                run(CONFIG, first)
            self.assertEqual(before, hashlib.sha256(CONFIG.read_bytes()).hexdigest())
            self.assertLess(receipt["output_bytes"], 128*1024*1024)


if __name__ == "__main__":
    unittest.main()
