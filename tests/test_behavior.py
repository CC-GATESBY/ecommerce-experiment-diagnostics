"""Literal small aggregate tests for the descriptive report only."""
from decimal import Decimal as D
from pathlib import Path
import tempfile
import unittest
from scripts.behavior_analysis import (daily_stats,category_summary,complete_hours,ratio,write_csv,read_csv,
    DAILY_FIELDS,CATEGORY_FIELDS,HOUR_FIELDS,RATIOS)


def category(day,key,amount,events=1,users=1,buyers=1):
    return dict(utc_date=day,dim_value_key=key,dim_value_label='unknown' if key=='bucket:unknown' else key.split(':')[1],purchase_amount=D(amount),
        purchase_events=events,users=users,buyers=buyers,count_allowed=True,amount_allowed=True,amount_status='complete_observed')


def daily():
    return [dict(utc_date=f'2019-10-{i+1:02d}',active_users=u,buyers=b,purchase_events=b+1,purchase_amount=D(v),buyer_rate=ratio(b,u),amount_per_buyer=ratio(v,b),first_seen_ratio=f,amount_status='complete_observed')
            for i,(u,b,v,f) in enumerate([(10,2,'20',1),(20,4,'80',.5),(15,3,'60',.25)])]


class BehaviorTests(unittest.TestCase):
    def test_min_max_median(self):
        stats={r['metric']:r for r in daily_stats(daily())}
        self.assertEqual((stats['purchase_amount']['min'],stats['purchase_amount']['max'],stats['purchase_amount']['median']),(D(20),D(80),D(60)))
        self.assertEqual(stats['purchase_amount']['max_dates'],'2019-10-02')
        self.assertEqual(stats['buyer_rate']['min_dates'],'2019-10-01;2019-10-02;2019-10-03')
    def test_even_and_empty_median(self):
        self.assertEqual(daily_stats(daily()[:2])[0]['median'],D(15))
        self.assertTrue(all(r['median'] is None and r['observations']==0 for r in daily_stats([])))
    def test_top10_and_tie_break(self):
        rows=[category('2019-10-01','category:'+chr(97+i),str(i+1)) for i in range(12)]
        out,s=category_summary(rows)
        self.assertEqual(sum(r['purchase_amount'] for r in out[:10]),D(75));self.assertEqual(s['total_amount'],D(78))
        self.assertEqual(s['top1_amount_share'],12/78);self.assertEqual(s['top5_amount_share'],50/78);self.assertEqual(s['top10_amount_share'],75/78)
        tied,_=category_summary([category('d','category:b','5'),category('d','category:a','5')]);self.assertEqual(tied[0]['category_key'],'category:a')
    def test_unknown_not_dropped(self):
        out,s=category_summary([category('d','category:a','60'),category('d','bucket:unknown','40')])
        self.assertEqual(s['unknown_amount'],D(40));self.assertEqual(s['unknown_share'],.4);self.assertEqual(s['top1_amount_share'],.6)
        self.assertTrue(any(r['is_unknown'] for r in out))
    def test_typed_unknown_collision(self):
        out,_=category_summary([category('d','category:unknown','30'),category('d','bucket:unknown','20')]);self.assertEqual(len(out),2)
        self.assertEqual(sum(r['is_unknown'] for r in out),1)
    def test_user_days_not_monthly_users(self):
        out,_=category_summary([category('2019-10-01','category:a','10',users=2),category('2019-10-02','category:a','20',users=2)])
        self.assertEqual(out[0]['user_days'],4);self.assertIsNone(out[0]['users']);self.assertIsNone(out[0]['buyers'])
        self.assertIn('not_measured',out[0]['monthly_distinct_status'])
    def test_blocked_and_duplicate_category(self):
        row=category('d','category:a','1')
        with self.assertRaises(ValueError):category_summary([row,row])
        with self.assertRaises(ValueError):category_summary([dict(row,amount_allowed=False)])
    def test_empty_few_zero_categories(self):
        out,s=category_summary([]);self.assertEqual(out,[]);self.assertIsNone(s['top10_amount_share'])
        out,s=category_summary([category('d','category:a','0')]);self.assertIsNone(out[0]['amount_share'])
        _,s=category_summary([category('d','category:a','3')]);self.assertEqual(s['top10_amount_share'],1)
    def test_ratio_zero_denominator(self):
        self.assertIsNone(ratio(0,0));self.assertIsNone(ratio(2,0));self.assertEqual(ratio(0,2),0)
    def test_hours_24_and_totals(self):
        out=complete_hours([dict(utc_hour=1,purchase_events=3,purchase_users=2,purchase_amount=D('6.25')),dict(utc_hour=23,purchase_events=1,purchase_users=1,purchase_amount=D('0'))])
        self.assertEqual([r['utc_hour'] for r in out],list(range(24)));self.assertEqual(sum(r['purchase_events'] for r in out),4)
        self.assertEqual(sum(r['purchase_amount'] for r in out),D('6.25'));self.assertEqual(out[1]['purchase_events_share'],.75)
        self.assertEqual(out[2]['purchase_events'],0)
    def test_bad_hour_and_empty(self):
        row=dict(utc_hour=24,purchase_events=1,purchase_users=1,purchase_amount=D(1))
        with self.assertRaises(ValueError):complete_hours([row])
        row['utc_hour']=1
        with self.assertRaises(ValueError):complete_hours([row,row])
        self.assertTrue(all(r['purchase_events_share'] is None for r in complete_hours([])))
    def test_csv_decimal_and_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'daily.csv';write_csv(p,daily(),DAILY_FIELDS);got=read_csv(p)
            self.assertEqual([r['utc_date'] for r in got],['2019-10-01','2019-10-02','2019-10-03'])
            self.assertEqual(D(got[1]['purchase_amount']),D(80))
            with self.assertRaises(FileExistsError):write_csv(p,daily(),DAILY_FIELDS)


def make_plot_fixture(folder,empty=False):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    write_csv(folder/'behavior_daily.csv',[] if empty else daily(),DAILY_FIELDS)
    categories=[] if empty else [category('d','category:'+chr(97+i),str(i+1)) for i in range(11)]+[category('d','bucket:unknown','15')]
    c,_=category_summary(categories);write_csv(folder/'category_concentration.csv',c,CATEGORY_FIELDS)
    hours=complete_hours([] if empty else [dict(utc_hour=1,purchase_events=3,purchase_users=2,purchase_amount=D('6.25')),dict(utc_hour=23,purchase_events=1,purchase_users=1,purchase_amount=D('0'))])
    write_csv(folder/'hourly_purchase.csv',hours,HOUR_FIELDS)
    counts=[('overall','all',10,5,6,3),('price_band','[0,20)',2,1,1,0),('price_band','[20,50)',3,2,2,1),('price_band','[50,200)',3,1,2,1),('price_band','[200,+inf)',2,1,1,1),('price_band','unknown',0,0,0,0)]
    rows=[]
    for level,segment,v,c,p,t in counts:
        if empty:v=c=p=t=0
        r=dict(level=level,segment=segment,n_view=v,n_cart=c,n_purchase=p,n_three_step=t)
        for name,num,den in RATIOS:r[name]=ratio(r[num],r[den])
        rows.append(r)
    write_csv(folder/'funnel_summary.csv',rows,list(rows[0]))
