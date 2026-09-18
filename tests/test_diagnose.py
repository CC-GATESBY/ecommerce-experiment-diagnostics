"""Literal aggregate fixtures; no real facts, user tables or historical jobs."""
from copy import deepcopy
from datetime import date,timedelta
from decimal import Decimal as D
from fractions import Fraction as F
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

from anomaly.diagnose import screen,select_case,decompose,attribute,coverage,validate_dimensions,js_components,DIMENSIONS
from scripts.metric_snapshot import select_snapshot

ROOT=Path(__file__).resolve().parents[1]
CFG=yaml.safe_load((ROOT/'config/anomaly.yaml').read_text())
DATES=[f'2019-10-{n:02}' for n in range(1,32)]


def daily(day,value=100,u=100,b=20):
    return dict(utc_date=day,active_users=u,buyers=b,purchase_amount=D(str(value)),
                event_records=100,purchase_events=20,count_allowed=True,amount_allowed=True)


class ScreeningTests(unittest.TestCase):
    def fixture(self):
        rows=[daily(d) for d in DATES]
        for day,value in [(1,80),(8,100),(15,120),(22,10),(2,90),(9,100),(16,110),(23,500)]:
            rows[day-1]['purchase_amount']=D(value)
        return rows

    def test_past_only_and_downward_priority(self):
        rows=self.fixture();flags=screen(rows,DATES,CFG);f=flags[21]
        self.assertEqual(f['history_dates'],['2019-10-15','2019-10-08','2019-10-01'])
        self.assertEqual((f['median_amount'],f['mad'],f['amount_difference']),(100,20,-90))
        self.assertTrue(f['candidate']);self.assertEqual(f['score'],F(-7500,2471))  # -90 / 29.652
        rows[28]['purchase_amount']=D(999999999)
        self.assertEqual(screen(rows,DATES,CFG)[21],f)
        self.assertEqual(select_case(flags)[0]['utc_date'],'2019-10-22')
        self.assertEqual(select_case(flags)[1],'downward_candidate')

    def test_upward_and_tie(self):
        f=[dict(utc_date=d,candidate=True,amount_difference=F(20),comparable=True) for d in ('2019-10-24','2019-10-23')]
        self.assertEqual(select_case(f)[0]['utc_date'],'2019-10-23')
        self.assertEqual(select_case(f)[1],'other_candidate')

    def test_insufficient_missing_and_blocked_dates(self):
        rows=self.fixture();self.assertEqual(screen(rows,DATES,CFG)[15]['status'],'insufficient_history')
        rows=[r for r in rows if r['utc_date']!='2019-10-08']
        flags=screen(rows,DATES,CFG)
        self.assertEqual(flags[7]['status'],'current_date_missing')
        self.assertEqual(flags[21]['status'],'insufficient_history_with_gaps')
        self.assertIn('missing_date:2019-10-08',flags[21]['reason'])
        rows=self.fixture();rows[21]['amount_allowed']=False
        self.assertEqual(screen(rows,DATES,CFG)[21]['status'],'current_quality_blocked')
        rows=self.fixture();rows[0]['amount_allowed']=False
        f=screen(rows,DATES,CFG)[28]
        self.assertEqual(f['history_count'],3);self.assertEqual(f['status'],'evaluated_with_history_gaps')
        self.assertNotIn('2019-10-01',f['history_dates'])

    def test_zero_mad_descriptive_and_zero_baseline(self):
        rows=[daily(d) for d in DATES];rows[-1]['purchase_amount']=D(105)
        flags=screen(rows,DATES,CFG)
        self.assertEqual(flags[-1]['status'],'zero_scale');self.assertIsNone(flags[-1]['score'])
        selected,branch=select_case(flags)
        self.assertEqual((selected['utc_date'],branch),('2019-10-31','descriptive_not_candidate'))
        zeros=screen([daily(d,0) for d in DATES],DATES,CFG)
        self.assertEqual(zeros[-1]['status'],'zero_baseline');self.assertEqual(select_case(zeros),(None,'no_comparable_date'))


class DecompositionTests(unittest.TestCase):
    def test_literal_offsets_and_identity(self):
        r=decompose(daily(DATES[21],400,50,20),[daily(DATES[0],200,100,20),daily(DATES[7],200,100,20)])
        by={x['factor']:x for x in r['rows']}
        self.assertEqual([by[k]['relative_change'] for k in ('U','R','M')],[F('-0.5'),1,1])
        self.assertEqual([round(by[k]['log_contribution_share'],10) for k in ('U','R','M')],[-1,1,1])
        self.assertLess(abs(r['log_identity_residual']),1e-12)

    def test_ratio_from_mean_counts_not_mean_ratios(self):
        r=decompose(daily(DATES[21],250,150,30),[daily(DATES[0],100,100,10),daily(DATES[7],300,200,50)])
        by={x['factor']:x for x in r['rows']}
        self.assertEqual(by['R']['history_mean_derived'],F(1,5))
        self.assertEqual(by['M']['history_mean_derived'],F(20,3))

    def test_zero_quality_and_near_zero_total(self):
        self.assertEqual(decompose(daily(DATES[21],0,100,0),[daily(DATES[0])])['status'],'nonpositive_factor_or_amount')
        bad=daily(DATES[21]);bad['count_allowed']=False
        self.assertEqual(decompose(bad,[daily(DATES[0])])['status'],'quality_or_history_unavailable')
        r=decompose(daily(DATES[21],100,50,20),[daily(DATES[0])])
        self.assertEqual(r['status'],'near_zero_total_log')
        self.assertTrue(all(x['log_contribution_share'] is None for x in r['rows']))


def bucket(day,key,amount,events=10,purchases=2):
    return dict(utc_date=day,dim_name='category_l1',dim_value_key=key,dim_value_label=key,
                purchase_amount=D(str(amount)),event_records=events,purchase_events=purchases,
                count_allowed=True,amount_allowed=True)


class DimensionTests(unittest.TestCase):
    def groups(self,current=80):
        return {(DATES[0],'category_l1'):[bucket(DATES[0],'old',80),bucket(DATES[0],'bucket:unknown',20)],
                (DATES[7],'category_l1'):[bucket(DATES[7],'old',80),bucket(DATES[7],'bucket:unknown',20)],
                (DATES[21],'category_l1'):[bucket(DATES[21],'new',current),bucket(DATES[21],'bucket:unknown',40)]}

    def test_new_disappeared_unknown_and_exact_conservation(self):
        rows,summary=attribute(self.groups(),DATES[21],[DATES[0],DATES[7]],'category_l1',CFG)
        by={r['dim_value_key']:r for r in rows}
        self.assertEqual({k:r['amount_difference'] for k,r in by.items()},{'old':-80,'new':80,'bucket:unknown':20})
        self.assertEqual(sum(r['amount_difference'] for r in rows),20)
        self.assertEqual([by[k]['signed_contribution'] for k in ('old','new','bucket:unknown')],[-4,4,1])
        self.assertEqual(by['old']['direction'],'offsetting')
        self.assertGreater(summary['js_divergence'],0)

    def test_zero_difference_zero_distribution_and_missing_date(self):
        rows,s=attribute(self.groups(60),DATES[21],[DATES[0],DATES[7]],'category_l1',CFG)
        self.assertTrue(all(r['signed_contribution'] is None for r in rows))
        self.assertEqual(js_components([F(0),F(0)],[F(0),F(0)]),(None,[None,None]))
        self.assertEqual(js_components([F(1),F(0)],[F(0),F(1)])[0],1)
        self.assertEqual(js_components([F(1),F(2)],[F(1),F(2)])[0],0)
        with self.assertRaises(ValueError):attribute(self.groups(),DATES[21],[DATES[2]],'category_l1',CFG)

    def test_weighted_coverage_not_mean_daily_rate(self):
        d=[daily(DATES[i]) for i in (0,7,21)];d[0]['event_records']=10;d[1]['event_records']=90
        g=self.groups();g[(DATES[0],'category_l1')][1]['event_records']=8
        g[(DATES[7],'category_l1')][1]['event_records']=0
        out=coverage(g,d,DATES[21],[DATES[0],DATES[7]])
        self.assertEqual(out[0]['history_known_coverage'],F(92,100))

    def test_missing_whole_dimension_or_bad_sum_is_not_zero_bucket(self):
        day=daily(DATES[0]);rows=[]
        for dim in DIMENSIONS:
            r=bucket(DATES[0],'only',100,100,20);r['dim_name']=dim;rows.append(r)
        self.assertEqual(len(validate_dimensions([day],rows)),4)
        with self.assertRaises(ValueError):validate_dimensions([day],rows[:-1])
        rows[0]['purchase_amount']=D(99)
        with self.assertRaises(ValueError):validate_dimensions([day],rows)


class SelectorTests(unittest.TestCase):
    def test_subset_never_opens_other_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=root/'.local/metrics-month-01';complete=run/'complete';complete.mkdir(parents=True)
            proof=dict(status='passed',spark_stopped=True,checks={'ok':{'pass':True}},
                       lineage=dict(source_run='fact',metric_version='rees46-metrics-v1',contract_version='rees46-events-v1.0.1',date_policy_version='rees46-date-quality-v1'),daily=[{'scope_id':'scope'}])
            (complete/'validation.json').write_text(json.dumps(proof));(run/'launch.json').write_text('{"status":"passed"}')
            table=complete/'metrics/agg_daily_metrics';table.mkdir(parents=True);(table/'_SUCCESS').touch();(table/'one.parquet').write_bytes(b'synthetic')
            snap=select_snapshot(root,run,scope_id='scope',source_run='fact',tables=('agg_daily_metrics',))
            self.assertEqual(list(snap['files']),['agg_daily_metrics'])
            with self.assertRaises(ValueError):select_snapshot(root,run,scope_id='scope',source_run='fact',tables=('arbitrary',))
            with self.assertRaises(ValueError):select_snapshot(root,run,scope_id='scope',source_run='fact',tables=())
            with self.assertRaises(ValueError):select_snapshot(root,run,scope_id='scope',source_run='fact')


if __name__=='__main__':unittest.main()
