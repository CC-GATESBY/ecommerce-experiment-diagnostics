"""Small synthetic records and independent literal planning expectations."""
from datetime import datetime, timezone
from decimal import Decimal
import unittest

from abtest.sample_size import two_proportions, independent_n, break_even, incremental_contribution, planning_tables
from scripts.run_cart_recovery import eligibility, summarize
from etl.fact_registry import registered_batch_matches

SPARK = None


def fixture():
    rows = []
    def add(user, event, time, price='0', valid=True, category='electronics', product='a', session='s'):
        rows.append(('synthetic', user, event, datetime.fromisoformat('2019-10-'+time).replace(tzinfo=timezone.utc),
                     Decimal(price) if price is not None else None, True, valid, product, session, category))
    for user in 'ABCDEFGKMN': add(user, 'cart', '01T10:00:00')
    add('A','purchase','02T09:00:00','1'); add('A','cart','04T10:00:00')
    add('B','purchase','02T10:00:01','10')
    add('C','purchase','01T10:00:00','1')
    add('D','purchase','02T10:00:00','1')
    add('E','purchase','03T10:00:00','20')
    add('F','purchase','03T10:00:01','1')
    add('G','cart','01T10:00:00',product='b'); add('G','cart','04T10:00:00')
    add('G','purchase','02T11:00:00','5'); add('G','purchase','02T11:00:00','5')
    add('H','cart','30T00:00:00')
    add('I','cart','31T00:00:00'); add('I','purchase','31T01:00:00','1')
    add('J','cart','01T12:00:00',category=None)
    add('K','purchase','01T09:00:00','1')
    add('K','purchase','02T11:00:00','7',product='different',session='different')
    add('L','cart','29T23:59:59'); add('L','purchase','31T23:59:59','3')
    add('M','purchase','02T11:00:00',None,False)
    add('O','view','01T12:00:00')
    return rows


class EligibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if SPARK is None: raise RuntimeError('run through project Spark launcher')
        rows = fixture()
        assert len(rows) <= 100
        schema = ('scope_id string,user_id string,event_type string,event_timestamp_utc timestamp,'
                  'price_decimal decimal(18,2),event_eligible boolean,amount_eligible boolean,'
                  'product_id string,user_session string,category_code string')
        cls.fact = SPARK.createDataFrame(rows, schema)
        cls.users = eligibility(SPARK, cls.fact).cache()
        # This bounded synthetic fixture is the only user-level collection.
        cls.by_user = {r['user_id']: r.asDict() for r in cls.users.limit(101).collect()}
        cls.summary = summarize(SPARK, cls.users)

    @classmethod
    def tearDownClass(cls):
        cls.users.unpersist(blocking=True)

    def test_flow_literal_counts(self):
        expected = dict(cart_users=14, complete_first_cart_users=12, right_censored_users=2,
                        waiting_purchase_excluded_users=3, eligible_users=9, outcome_buyers=6,
                        outcome_nonbuyers=3, outcome_purchase_events=7,
                        outcome_bad_amount_events=1, outcome_bad_amount_users=1)
        self.assertEqual({k:self.summary[k] for k in expected}, expected)
        self.assertEqual(self.summary['known_outcome_amount'], Decimal('50.00'))
        self.assertEqual(self.summary['p_hist'], Decimal(6)/9)

    def test_waiting_includes_both_same_second_endpoints(self):
        for user in 'ACD':
            self.assertEqual(self.by_user[user]['eligibility_status'], 'waiting_purchase_excluded')
            self.assertIsNone(self.by_user[user]['purchased_24h'])

    def test_outcome_open_left_closed_right(self):
        self.assertEqual(self.by_user['B']['purchased_24h'], 1)
        self.assertEqual(self.by_user['E']['purchased_24h'], 1)
        self.assertEqual(self.by_user['F']['purchased_24h'], 0)
        self.assertEqual(self.by_user['L']['purchased_24h'], 1)

    def test_first_anchor_once_and_purchase_duplicates_preserved(self):
        self.assertEqual(len(self.by_user), 14)
        self.assertNotIn('O', self.by_user)
        self.assertEqual(self.by_user['G']['t_cart'].isoformat(), '2019-10-01T10:00:00')
        self.assertEqual(self.by_user['G']['outcome_purchase_events'], 2)
        self.assertEqual(self.by_user['G']['purchase_amount_24h'], Decimal('10.00'))
        self.assertEqual(self.by_user['A']['eligibility_status'], 'waiting_purchase_excluded')

    def test_right_censor_priority_and_complete_last_day(self):
        for user in 'HI': self.assertEqual(self.by_user[user]['eligibility_status'], 'right_censored')
        self.assertEqual(self.by_user['L']['eligibility_status'], 'eligible')
        self.assertIsNone(self.by_user['I']['purchased_24h'])

    def test_nonreturn_unknown_and_cross_product_remain(self):
        self.assertEqual(self.by_user['J']['purchased_24h'], 0)
        self.assertEqual(self.by_user['J']['purchase_amount_24h'], Decimal('0.00'))
        self.assertEqual(self.by_user['J']['amount_status'], 'no_purchases')
        self.assertEqual(self.by_user['N']['purchased_24h'], 0)
        self.assertEqual(self.by_user['K']['outcome_purchase_events'], 1)
        self.assertEqual(self.by_user['K']['purchase_amount_24h'], Decimal('7.00'))

    def test_bad_amount_is_not_zero_or_removed_buyer(self):
        self.assertEqual(self.by_user['M']['purchased_24h'], 1)
        self.assertIsNone(self.by_user['M']['purchase_amount_24h'])
        self.assertEqual(self.by_user['M']['amount_status'], 'unknown')
        self.assertIsNone(self.summary['observed_amount_per_eligible_user'])
        self.assertEqual(self.summary['amount_status'], 'partial_or_unknown')


class PlanningTests(unittest.TestCase):
    def test_literal_sample_size(self):
        result = two_proportions('.1', '.2')
        self.assertEqual(result['n_per_arm'], 3841)
        self.assertEqual(result['n_total'], 7682)
        self.assertAlmostEqual(result['absolute_difference_pp'], 2)
        self.assertEqual(independent_n('.1', '.2'), 3841)

    def test_independent_grid_and_historical_size_comparison(self):
        sizes, costs = planning_tables(Decimal('.1'), 10000)
        self.assertEqual((len(sizes),len(costs)),(9,9))
        for row in sizes:
            self.assertEqual(row['n_per_arm'], independent_n(row['p0'],row['relative_mde']))
            self.assertEqual(row['n_total'], 2*row['n_per_arm'])
            self.assertEqual(row['within_historical_count'], row['n_total'] <= 10000)

    def test_invalid_probability_is_not_clamped(self):
        row = two_proportions('.9','.2')
        self.assertEqual(row['status'], 'invalid_probability')
        self.assertIsNone(row['n_total'])
        self.assertGreater(row['p1'], 1)
        self.assertEqual(two_proportions(0,.1)['status'], 'invalid_probability')
        self.assertEqual(two_proportions(.1,0)['status'], 'invalid_design')
        rows,_ = planning_tables(Decimal('.7'),10)
        self.assertTrue(any(r['status']=='invalid_probability' and r['n_total'] is None for r in rows))

    def test_nonfinite_rejected(self):
        self.assertEqual(two_proportions(float('nan'),.1)['status'], 'invalid_nonfinite')

    def test_break_even_literal_and_domain(self):
        self.assertEqual(break_even('.2'), Decimal('.25'))
        self.assertEqual(break_even('.1'), Decimal(1)/9)
        self.assertEqual(break_even('.05'), Decimal(1)/19)
        self.assertEqual(break_even(0), 0)
        for k in ('1','-0.1','NaN'):
            with self.assertRaises(ValueError): break_even(k)

    def test_conversion_up_but_cost_exceeds_increment(self):
        # All 0.11 buyers carry expected 0.10 cost, not only the incremental 0.01.
        self.assertEqual(incremental_contribution('.1','.11',1,'.5','.2'), Decimal('-.001'))
        self.assertEqual(incremental_contribution('.1','.125',1,1,'.2'), 0)
        self.assertEqual(incremental_contribution('.1','.12',1,1,'.1'), Decimal('.008'))

    def test_cost_grid_literal_signs(self):
        _, rows = planning_tables(Decimal('.1'),100)
        self.assertEqual([r['status'] for r in rows],
                         ['negative','positive','positive','negative','negative','positive','negative','negative','negative'])
        for r in rows:
            self.assertEqual(Decimal(r['normalized_increment_per_enrolled']),
                             incremental_contribution(r['p0'],r['p1'],1,1,r['k']))


class ManifestCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.old = {'evidence': {'data/manifest.json': 'f6fde65d4a8f2f8051456b5ed744233e08ea1881ee5ec50a539cd3d2772237ad',
                                 'receipt': 'unchanged'}, 'inventory': ['unchanged'], 'summary': {'rows': 10}}
        self.new = {**self.old, 'evidence': {**self.old['evidence'], 'data/manifest.json':
                    '39089916016724996b3b8c6f204aa35e4a5a9978b3729bdc1cf67276529667f3'}}

    def test_default_remains_exact_and_opt_in_is_nonmutating(self):
        import copy
        snapshot = copy.deepcopy([self.old, self.new])
        self.assertTrue(registered_batch_matches(self.old, self.old))
        self.assertFalse(registered_batch_matches(self.new, self.old))
        self.assertTrue(registered_batch_matches(self.new, self.old, allow_criteo_manifest_extension=True))
        self.assertEqual([self.old, self.new], snapshot)

    def test_any_other_batch_or_proof_change_rejected(self):
        for key, value in [('inventory',['changed']), ('summary',{'rows':11}),
                           ('evidence',{**self.new['evidence'],'receipt':'changed'})]:
            self.assertFalse(registered_batch_matches({**self.new,key:value},self.old,
                                                     allow_criteo_manifest_extension=True))

    def test_other_manifest_hash_or_reverse_transition_rejected(self):
        changed = {**self.new, 'evidence': {**self.new['evidence'],'data/manifest.json':'unapproved'}}
        self.assertFalse(registered_batch_matches(changed,self.old,allow_criteo_manifest_extension=True))
        self.assertFalse(registered_batch_matches(self.old,self.new,allow_criteo_manifest_extension=True))


if __name__ == '__main__': unittest.main()
