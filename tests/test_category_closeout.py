"""Literal synthetic expectations, independent of production category aggregation."""
from copy import deepcopy
from datetime import date
from decimal import Decimal as D
import unittest

from scripts.close_behavior_categories import category_projection, merge_monthly, reconcile


class CloseoutTests(unittest.TestCase):
    def old(self):
        return [dict(amount_rank='1',category_key='category:electronics',category_label='electronics',
            purchase_amount='10.00',purchase_events='1',user_days='3',buyer_user_days='1',
            users='',buyers='',monthly_distinct_status='not_measured_daily_counts_not_additive',
            amount_share='1.0',cumulative_amount_share='1.0',is_unknown='False',amount_status='complete_observed')]

    def monthly(self):
        return [dict(scope_id='synthetic',category_key='category:electronics',category_label='electronics',
            users=2,buyers=1,event_records=3,purchase_events=1,purchase_amount=D('10.00'))]

    def test_only_three_columns_change(self):
        old=self.old();snapshot=deepcopy(old);out=merge_monthly(old,self.monthly())
        self.assertEqual(old,snapshot)
        self.assertEqual((out[0]['users'],out[0]['buyers']),(2,1))
        for k in old[0]:
            if k not in ('users','buyers','monthly_distinct_status'):self.assertEqual(out[0][k],old[0][k])

    def test_duplicate_or_missing_bucket_rejected(self):
        with self.assertRaises(ValueError):merge_monthly(self.old(),self.monthly()*2)
        with self.assertRaises(ValueError):merge_monthly(self.old(),[])

    def test_amount_drift_rejected(self):
        row=self.monthly();row[0]['purchase_amount']=D('11')
        with self.assertRaises(ValueError):merge_monthly(self.old(),row)

    def test_label_drift_rejected(self):
        row=self.monthly();row[0]['category_label']='Electronics'
        with self.assertRaises(ValueError):merge_monthly(self.old(),row)

    def test_monthly_users_cannot_exceed_user_days(self):
        row=self.monthly();row[0]['users']=4
        with self.assertRaises(ValueError):merge_monthly(self.old(),row)

    def test_same_user_across_days_is_not_required_equal(self):
        expected={'category:electronics':dict(event_records=3,purchase_events=1,purchase_amount=D('10.00'))}
        self.assertTrue(all(v['pass'] for v in reconcile(self.monthly(),expected,'synthetic').values()))

    def test_event_drift_rejected(self):
        expected={'category:electronics':dict(event_records=4,purchase_events=1,purchase_amount=D('10.00'))}
        with self.assertRaises(ValueError):reconcile(self.monthly(),expected,'synthetic')

    def test_exact_frozen_projection(self):
        p=category_projection()
        self.assertIn("RLIKE r'\\A[A-Za-z0-9_]+(\\.[A-Za-z0-9_]+)*\\z'",p)
        self.assertEqual(p.count('NOT f.category_code_missing'),2)
        self.assertNotIn('brand',p);self.assertNotIn('TRIM',p)


def run_synthetic(spark, query, checks):
    """Run before any real FactReader access; all expected counts are literals."""
    from pyspark.sql import types as T
    schema='scope_id string,user_id string,event_type string,event_date_utc date,category_code string,category_code_missing boolean,price_decimal decimal(18,2),amount_eligible boolean'
    def event(user,day,code,kind='view',amount='0',eligible=False):
        return ('synthetic',user,kind,date(2019,10,day),code,code in (None,''),D(amount),eligible)
    def aggregate(rows):
        spark.createDataFrame(rows,schema).createOrReplaceTempView('category_fact')
        frame=spark.sql(query)
        checks.equal('synthetic_decimal_type',T.DecimalType(38,2).simpleString(),frame.schema['purchase_amount'].dataType.simpleString())
        return [r.asDict() for r in frame.collect()]
    simple=[event('A',1,'electronics.phone'),event('A',2,'electronics.phone','purchase','10',True),event('B',1,'electronics.phone')]
    got=aggregate(simple)
    checks.equal('synthetic_electronics_literal',[(2,1,3,1,D('10.00'))],[(r['users'],r['buyers'],r['event_records'],r['purchase_events'],r['purchase_amount']) for r in got])
    checks.equal('synthetic_daily_users_literal',3,len({(r[3],r[1]) for r in simple}))
    extended=simple+[event('A',3,'electronics.phone','purchase','5',True),event('A',2,'computers.pc','purchase','20',True),
        event('A',1,None),event('A',2,'bad..code','purchase','3',True),event('A',3,'','purchase','4',True)]
    got=aggregate(extended)
    checks.equal('synthetic_cross_category_unknown_literal',
        [('bucket:unknown',1,1,3,2,D('7.00')),('category:computers',1,1,1,1,D('20.00')),('category:electronics',2,1,4,2,D('15.00'))],
        [(r['category_key'],r['users'],r['buyers'],r['event_records'],r['purchase_events'],r['purchase_amount']) for r in got])
    checks.equal('synthetic_overlap_category_user_sum',4,sum(r['users'] for r in got))
    checks.equal('synthetic_unique_users_literal',2,len({r[1] for r in extended}))
    checks.equal('synthetic_electronics_daily_buyers_literal',2,len({(r[3],r[1]) for r in extended if r[4]=='electronics.phone' and r[2]=='purchase'}))
    boundaries=[event(str(i),1,c) for i,c in enumerate(['electronics.phone','Electronics.phone','unknown',' electronics.phone','electronics.','x..y','x\n','x\r\n','',None,'_a.9'])]
    got=aggregate(boundaries)
    checks.equal('synthetic_category_boundaries_literal',
        [('bucket:unknown',7),('category:Electronics',1),('category:_a',1),('category:electronics',1),('category:unknown',1)],
        [(r['category_key'],r['users']) for r in got])
    return dict(simple_events=3,extended_events=8,boundary_events=11,all_synthetic=True)
