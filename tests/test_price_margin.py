"""Synthetic only: literal expectations for PRICE-01 boundaries."""
import copy
from decimal import Decimal as D
import json
import unittest

import duckdb
import numpy as np

from scripts.price_margin import ROOT, compare, compact_arrays, weighted_cells, margin, select_pairs, price_support

CFG = json.loads((ROOT/'config/price_analysis.json').read_text())


class PriceMarginTests(unittest.TestCase):
    def support(self, converted=False):
        con = duckdb.connect()
        con.execute('CREATE TABLE usable(product_id VARCHAR,first_view_price DECIMAL(18,2),user_id VARCHAR,start_date_utc DATE,has_purchase_after_view BOOLEAN)')
        # A/B have tied path counts: Decimal numeric order picks 9.01 then 10.01, never 11.01.
        for pid in ['B', 'A']:
            for price, count in [('9.01', 210), ('10.01', 210), ('11.01', 180)]:
                con.execute("INSERT INTO usable SELECT ?,?::DECIMAL(18,2),'u'||CAST(i%105 AS VARCHAR),DATE '2019-10-01'+CAST(i%3 AS INT),? FROM range(?) t(i)", [pid, price, converted, count])
        # The third price must not rescue this product's out-of-range top pair.
        for price, count in [('1.00', 210), ('10.00', 209), ('9.00', 208)]:
            con.execute("INSERT INTO usable SELECT 'unsupported',?::DECIMAL(18,2),'u'||CAST(i%105 AS VARCHAR),DATE '2019-10-01'+CAST(i%3 AS INT),FALSE FROM range(?) t(i)", [price, count])
        con.execute("INSERT INTO usable VALUES ('same',12.34,'u1',DATE '2019-10-01',FALSE)")
        return con

    def test_selection_ignores_outcomes_decimal_ties_and_third_price(self):
        results = []
        for converted in [False, True]:
            con = self.support(converted)
            selected = select_pairs(con, CFG)
            self.assertEqual([p['product_id'] for p in selected], ['A', 'B'])
            self.assertEqual([(p['low_price'], p['high_price']) for p in selected], [(D('9.01'), D('10.01'))]*2)
            self.assertEqual([p['pair_paths'] for p in selected], [420, 420])
            self.assertEqual([p['total_paths'] for p in selected], [600, 600])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM pairs WHERE product_id='same'").fetchone()[0], 0)
            self.assertFalse(con.execute("SELECT gap_ok FROM pairs WHERE product_id='unsupported'").fetchone()[0])
            got = price_support(con, 'A', D('9.01'), D('10.01'))
            self.assertEqual([(r['paths'], r['users'], r['days'], r['successes']) for r in got], [(210, 105, 3, 210 if converted else 0)]*2)
            results.append(selected)
            con.close()
        self.assertEqual(results[0], results[1])

    def test_price_exclusions_do_not_delete_nonbuyers(self):
        c = duckdb.connect()
        c.execute('CREATE TABLE p(price DECIMAL(18,2),status VARCHAR,y INT)')
        c.execute("INSERT INTO p VALUES (0,'unique_valid',0),(NULL,'invalid_or_missing',0),(NULL,'conflicting',1),(2.01,'unique_valid',0),(2.01,'unique_valid',1)")
        self.assertEqual(c.execute("SELECT COUNT(*),SUM(y) FROM p WHERE status='unique_valid' AND price>0").fetchone(), (2, 1))
        self.assertEqual(c.execute('SELECT COUNT(*) FROM p WHERE price=0').fetchone()[0], 1)
        c.close()

    def test_cluster_weight_is_shared_across_dates_prices(self):
        records = [('a','d1',0,2,1),('a','d2',1,3,2),('b','d1',1,1,0)]
        users, days, u, cell, n, y = compact_arrays(records)
        nn, yy = weighted_cells(np.array([2, 0]), u, cell, n, y, len(days))
        self.assertEqual(users, ['a', 'b'])
        np.testing.assert_array_equal(nn, [[4, 0], [0, 6]])
        np.testing.assert_array_equal(yy, [[2, 0], [0, 4]])

    def test_date_composition_reversal_literal(self):
        cfg = dict(CFG, min_common_dates=2, bootstrap_repetitions=30)
        # Both dates favor L within date, but L is concentrated on the low-rate date.
        data = [('a','d1',0,10,9),('b','d1',1,90,72),('c','d2',0,90,18),('d','d2',1,10,1)]
        out, _, days, _ = compare(data, cfg, 1)
        self.assertAlmostEqual(out[0]['p_low'], .27)
        self.assertAlmostEqual(out[0]['p_high'], .73)
        self.assertAlmostEqual(out[1]['p_low'], .55)
        self.assertAlmostEqual(out[1]['p_high'], .45)
        self.assertEqual([r['standardized_weight'] for r in days], [.5, .5])
        self.assertGreater(out[1]['bootstrap_invalid'], 0)

    def test_sparse_zero_and_missing_common_dates(self):
        out, _, _, _ = compare([('a','d1',0,10,0),('a','d2',1,10,0)], dict(CFG, bootstrap_repetitions=20), 1)
        self.assertEqual(out[0]['absolute_difference'], 0)
        self.assertEqual(out[0]['relative_status'], 'zero_high_rate')
        self.assertEqual(out[0]['interval_status'], 'sparse_successes_not_suitable_for_inference')
        self.assertEqual(out[0]['bootstrap_relative_invalid'], 20)
        self.assertEqual(out[1]['status'], 'date_comparison_not_supported')
        self.assertIsNone(out[1]['p_high'])

    def test_reproducibility_input_unchanged(self):
        data = [('a','d1',0,20,2),('a','d1',1,20,1),('b','d2',0,20,1),('c','d2',1,20,2)]
        before = copy.deepcopy(data)
        cfg = dict(CFG, min_common_dates=2, bootstrap_repetitions=40)
        a, aa, _, _ = compare(data, cfg, 1)
        b, bb, _, _ = compare(list(reversed(data)), cfg, 1)
        self.assertEqual(a, b)
        for branch in aa:
            np.testing.assert_array_equal(aa[branch], bb[branch])
        self.assertEqual(data, before)

    def test_margin_literal_loss_despite_relative_gain(self):
        r = margin('.30', '.10', '.02', '.026')
        self.assertEqual(r['required_relative_lift'], D('.50'))
        self.assertEqual(r['required_low_rate'], D('.03'))
        self.assertEqual(r['contribution_difference'], D('-.0008'))

    def test_margin_boundaries(self):
        self.assertEqual(margin('.2', '.2')['status'], 'unit_contribution_nonpositive')
        r = margin('.2', '.1', '.9', '1')
        self.assertEqual(r['status'], 'required_probability_unattainable')
        self.assertEqual(r['required_low_rate'], D('1.8'))
        self.assertEqual(margin('.3', '.1', '0', '.1')['status'], 'zero_high_rate_no_relative_threshold')
        with self.assertRaises(ValueError):
            margin('.3', '-.1')


if __name__ == '__main__':
    unittest.main()
