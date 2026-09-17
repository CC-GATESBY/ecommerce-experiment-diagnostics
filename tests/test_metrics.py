"""Literal synthetic facts and expectations; no CSV or source reparse."""
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import importlib
import json
from pathlib import Path
import unittest

from etl.event_config import FLAGS,ALLOWED,CONTRACT,sha256
from etl.fact_registry import FactReader,register_batch,FactAccessError
from scripts.run_metrics import (TOP_K,VERSION,BRAND_VERSION,DATE_POLICY,DATES,SCOPE,SERIES,TABLES,
    Checks,ready,write_json,build_metrics,controlled_input,validate_config,bounded,sql,publish)


class MetricUnitTests(unittest.TestCase):
    def config(self):
        return dict(registry_path='.local/t11/registry.json',source_run='month-v101-01',scope_id=SCOPE,series_id=SERIES,
                    observation_dates=DATES,output_dates=DATES,metric_version=VERSION,brand_version=BRAND_VERSION,
                    brand_top_k=TOP_K,date_policy_version=DATE_POLICY,contract_version=CONTRACT)
    def test_real_config_frozen(self):
        self.assertEqual(validate_config(self.config())['brand_top_k'],200)
        for key,bad in [('brand_top_k',2),('source_run','month-v101-02'),('scope_id','other'),('observation_dates',['2019-10-01']),
                        ('output_dates',['2019-11-01']),('registry_path',''),('contract_version','v2')]:
            with self.subTest(key=key),self.assertRaises(ValueError):validate_config(dict(self.config(),**{key:bad}))
    def test_short_output_keeps_observation_scope(self):
        cfg=validate_config(dict(self.config(),output_dates=['2019-10-31']))
        self.assertEqual(cfg['observation_dates'],DATES)
    def test_partial_publish_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);stage=run/'staging';stage.mkdir()
            write_json(stage/'validation.json',dict(status='failed',spark_stopped=True))
            with self.assertRaises(ValueError):publish(stage,run)
            self.assertTrue(stage.exists());self.assertFalse((run/'complete').exists())

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ValueError):json.dumps(ready({'bad':float('nan')}),allow_nan=False)


def fixture_rows():
    def row(day,user,session,behavior='view',price='0',brand='unknown',category='a.b'):
        value=None if price=='bad' else Decimal(price)
        data={k:False for k in FLAGS}
        data.update(event_time=f'2019-10-{day:02d} 12:00:00 UTC',event_type=behavior,product_id='1',category_id='2',
                    category_code=category,brand=brand,price=price,user_id=str(user),user_session=session,
                    event_timestamp_utc=datetime(2019,10,day,12,tzinfo=timezone.utc),event_date_utc=datetime(2019,10,day).date(),price_decimal=value,
                    event_eligible=True,amount_eligible=behavior=='purchase' and value is not None and value>=0,
                    session_missing=not session.strip(),brand_missing=not brand.strip(),category_code_missing=not category.strip(),
                    price_invalid=price=='bad',price_negative=value is not None and value<0,price_zero=value==0)
        return data
    duplicate=row(1,2,'S','purchase','50','other')
    return [row(1,1,'S'),row(1,1,'S','cart','20',category='b'),duplicate,duplicate.copy(),
            row(1,3,'',price='200',brand='',category=''),row(1,6,'X',price='-1',brand='Z',category='.bad'),
            row(2,1,'S','purchase','20',category='b'),row(2,1,'T',price='50',brand='other'),
            row(2,4,'','purchase','0','other',''),row(2,2,'S',price='200',brand='other'),
            row(3,5,'V'),row(4,7,'Q','purchase','bad','',''),row(4,8,'R','purchase','50','other'),
            row(8,1,'N',price='200',brand='new'),row(8,1,'N',price='200',brand='new',category='b'),
            row(8,1,'N','purchase','200','new'),row(8,2,'O',price='20',brand='Z'),
            row(8,9,'P','remove_from_cart','50','unknown','bad..x')]


def independent_summary(rows):
    purchases=[r for r in rows if r['event_type']=='purchase'];valid=[r for r in purchases if r['amount_eligible']]
    flags={k:sum(r[k] for r in rows) for k in FLAGS};bad=len(purchases)-len(valid)
    return dict(record_count=len(rows),raw_users=len({r['user_id'] for r in rows}),users=len({r['user_id'] for r in rows}),
        buyers=len({r['user_id'] for r in purchases}),purchase_events=len(purchases),purchase_price_bad_eligible=bad,purchase_price_bad_all=bad,
        purchase_amount=format(sum((r['price_decimal'] for r in valid),Decimal('0')),'.2f') if valid or not purchases else None,
        time_min=min(r['event_timestamp_utc'] for r in rows).isoformat(),time_max=max(r['event_timestamp_utc'] for r in rows).isoformat(),
        flags=flags,behaviors=dict(Counter(r['event_type'] for r in rows)),
        zero_by_behavior={b:sum(r['price_zero'] and r['event_type']==b for r in rows) for b in (*ALLOWED,'__unknown__')},
        amount_status='no_purchases' if not purchases else 'complete_observed' if not bad else 'partial_observed' if valid else 'unknown')


def create_fixture(spark,root,run,rows):
    events=importlib.import_module('etl.01_events')
    fixture=root/'.local/t11'/('t13-'+run.name)/'synthetic'/'fixture-01';fixture.mkdir(parents=True,exist_ok=False)
    stage=fixture/'staging';stage.mkdir()
    write_json(fixture/'synthetic.json',rows);digest=sha256(fixture/'synthetic.json')
    dates=sorted({str(r['event_date_utc']) for r in rows})
    d=dict(source_id='synthetic_t13',scope_id='synthetic_t13_scope',input_sha256=digest,contract_version=CONTRACT,
           run_id='fixture-01',kind='synthetic',run_path=str(fixture.relative_to(root)),expected_records=len(rows),dates=dates,
           series_id='synthetic_t13_series',sampling_rule='synthetic_literal_v1')
    full=[dict(r,**{k:d[k] for k in ('source_id','scope_id','input_sha256','contract_version','run_id')},
               parsed_at_utc=datetime(2026,9,17,tzinfo=timezone.utc)) for r in rows]
    facts=spark.createDataFrame(full,events.schema());facts.write.mode('errorifexists').parquet(str(stage/'fact_events'))
    restored=spark.read.parquet(str(stage/'fact_events'));checks=Checks()
    checks.equal('schema',events.schema().simpleString(),restored.schema.simpleString())
    checks.equal('rows',len(rows),restored.count())
    checks.equal('expected_minus_actual_multiset',0,facts.exceptAll(restored).count())
    checks.equal('actual_minus_expected_multiset',0,restored.exceptAll(facts).count())
    expected=independent_summary(rows);actual=events.summary(restored)
    for k,v in expected.items():checks.equal('summary_'+k,v,actual[k])
    daily={day:independent_summary([r for r in rows if str(r['event_date_utc'])==day]) for day in dates}
    got=events.daily_summary(restored);checks.equal('daily_bucket_keys',dates,sorted(got))
    for day in dates:checks.equal('daily_'+day,daily[day],got[day])
    checks.equal('input_sha256_after',digest,sha256(fixture/'synthetic.json'))
    write_json(stage/'validation.json',dict(status='passed',completion_mode='synthetic_no_active_writer_shared_test_session',
        contract_version=CONTRACT,checks=checks.rows,schema=restored.schema.jsonValue(),summary=actual,daily_summary=got))
    stage.rename(fixture/'complete');write_json(fixture/'launch.json',dict(d,status='passed'))
    registry=fixture.parent/'registry.json';register_batch(root,registry,d)
    entry=json.loads(registry.read_text())['batches'][0]
    return d,registry,entry


def run_tests(spark,root,run):
    checks=Checks();rows=fixture_rows();checks.equal('synthetic_rows_literal',18,len(rows))
    d,registry,entry=create_fixture(spark,root,run,rows);dates=d['dates']
    before={str(p):sha256(p) for p in registry.parent.rglob('*') if p.is_file()}
    with FactReader(spark,root,registry,d['series_id']) as reader:
        data=controlled_input(reader,dates,d['scope_id'],entry['gates'])
        checks.equal('reader_count_retains_bad_amount',18,data.count())
        for day in ('2019-10-04','2019-10-05'):
            try:reader.read([day],'amount',expected_scopes=[d['scope_id']])
            except FactAccessError:checks.equal('reader_refuses_'+day,True,True)
            else:raise AssertionError('reader must reject amount or missing date')
        a=build_metrics(spark,data,entry['gates'],run/'staging'/'metrics-a',d,top_k=2,synthetic=True)
        wanted={'2019-10-01':[6,4,1,2,'100.00',3,1,4], '2019-10-02':[4,3,2,2,'20.00',3,1,1],
                '2019-10-03':[1,1,0,0,'0.00',1,0,1], '2019-10-04':[2,2,2,2,None,2,2,2],
                '2019-10-08':[5,3,1,1,'200.00',3,1,1]}
        keys=['event_records','active_users','buyers','purchase_events','purchase_amount','sessions','purchase_sessions','first_seen_users']
        for r in a['daily']:checks.equal('literal_daily_'+str(r['utc_date']),wanted[str(r['utc_date'])],ready([r[k] for k in keys]))
        checks.equal('literal_month',[18,9,5,7,None,10],[a['month'][k] for k in ['event_records','active_users','buyers','purchase_events','purchase_amount','sessions']])
        checks.equal('table_rows',[9,13,5], [a['tables'][k]['rows'] for k in ['dim_user_first_seen','agg_user_daily','agg_daily_metrics']])
        mapping=json.loads((run/'staging/metrics-a/brand_mapping.json').read_text())['rows']
        checks.equal('top2_frozen_literal',['other','unknown'],[r['brand'] for r in mapping])
        checks.equal('reference_counts_literal',[6,4],[r['reference_events'] for r in mapping])
        # Scalar checks inspect the actual SQL tables, never retrieve user-level lists.
        ud=spark.read.parquet(str(run/'staging/metrics-a/agg_user_daily'));ud.createOrReplaceTempView('test_ud')
        dim=spark.read.parquet(str(run/'staging/metrics-a/agg_daily_dim'));dim.createOrReplaceTempView('test_dim')
        def scalar(query):return spark.sql(query).first()[0]
        checks.equal('day1_view_does_not_inherit_purchase',0,scalar("SELECT purchase_sessions FROM test_ud WHERE utc_date=DATE '2019-10-01' AND user_id='1'"))
        checks.equal('duplicate_retained',2,scalar("SELECT purchase_events FROM test_ud WHERE utc_date=DATE '2019-10-01' AND user_id='2'"))
        checks.equal('missing_session_retained',2,scalar('SELECT COUNT(*) FROM test_ud WHERE sessions=0'))
        checks.equal('all_countable_bad_day_retained',2,scalar("SELECT COUNT(*) FROM test_ud WHERE utc_date=DATE '2019-10-04' AND purchase_amount IS NULL"))
        checks.equal('zero_purchase_valid','0.00',str(spark.sql("SELECT purchase_amount FROM test_ud WHERE user_id='4'").first()[0]))
        day3=next(r for r in a['daily'] if str(r['utc_date'])=='2019-10-03')
        checks.equal('no_purchase_ratios',[0.0,None,'no_buyers','no_purchases'],[day3[k] for k in ['buyer_rate','amount_per_buyer','amount_per_buyer_status','amount_status']])
        checks.equal('bad_amount_ratio',None,next(r['amount_per_buyer'] for r in a['daily'] if str(r['utc_date'])=='2019-10-04'))
        checks.equal('no_missing_day_zero',False,any(str(r['utc_date'])=='2019-10-05' for r in a['daily']))
        checks.equal('collision_safe_brand_keys',4,scalar("SELECT COUNT(DISTINCT dim_value_key) FROM test_dim WHERE dim_name='brand_group'"))
        checks.equal('post_reference_new_brand_other',4,scalar("SELECT event_records FROM test_dim WHERE dim_name='brand_group' AND dim_value_key='bucket:other' AND utc_date=DATE '2019-10-08'" ) )
        # Day 8 has three new events plus one Z event, both outside the reference Top2.
        day8_top=bounded(spark.sql("SELECT brand,COUNT(*) n FROM m_fact WHERE event_date_utc=DATE '2019-10-08' GROUP BY brand ORDER BY n DESC,brand ASC LIMIT 2"),2)
        checks.equal('daily_reranking_counterexample',['new','Z'],[r['brand'] for r in day8_top])
        bands=bounded(spark.sql("SELECT dim_value_key,event_records FROM test_dim WHERE dim_name='price_band' AND utc_date=DATE '2019-10-01' ORDER BY dim_value_key"),5)
        checks.equal('boundary_prices_and_negative',[('band:0_20',1),('band:200_plus',1),('band:20_50',1),('band:50_200',2),('bucket:unknown',1)],[(r['dim_value_key'],r['event_records']) for r in bands])
        checks.equal('malformed_category_unknown',2,scalar("SELECT SUM(event_records) FROM test_dim WHERE dim_name='category_l1' AND dim_value_key='bucket:unknown' AND utc_date=DATE '2019-10-01'"))
        # One independent synthetic rerun; every output field must be identical.
        b=build_metrics(spark,data,entry['gates'],run/'staging'/'metrics-b',d,top_k=2,synthetic=True)
        for name in TABLES:
            left=spark.read.parquet(str(run/'staging/metrics-a'/name));right=spark.read.parquet(str(run/'staging/metrics-b'/name))
            checks.equal('synthetic_rerun_'+name,0,left.exceptAll(right).count()+right.exceptAll(left).count())
        checks.equal('rerun_mapping_fingerprint',a['brand_mapping'],b['brand_mapping'])
        try:build_metrics(spark,data,entry['gates'],run/'staging'/'metrics-a',d,top_k=2,synthetic=True)
        except FileExistsError:checks.equal('existing_output_rejected',True,True)
        else:raise AssertionError('existing output overwritten')
        # A short-window projection must retain observed first-seen dates from the full scope.
        checks.equal('later_day_not_new',0,scalar("SELECT COUNT(*) FROM test_ud WHERE utc_date=DATE '2019-10-08' AND user_id IN ('1','2') AND is_first_seen_day"))
        data.where("user_id IN ('5','6')").createOrReplaceTempView('m_fact')
        tied=bounded(sql(spark,'brand_mapping',2).orderBy('brand_rank'),2)
        checks.equal('stable_binary_brand_tie',['Z','unknown'],[r['brand'] for r in tied])
        checks.equal('bad_purchase_price_unknown_bucket',1,scalar("SELECT event_records FROM test_dim WHERE utc_date=DATE '2019-10-04' AND dim_name='price_band' AND dim_value_key='bucket:unknown'"))
        empty=build_metrics(spark,data.where('false'),{},run/'staging'/'metrics-empty',d,top_k=2,synthetic=True)
        checks.equal('empty_tables',[0,0,0,0],[empty['tables'][name]['rows'] for name in TABLES])
        spark.sql("SELECT 0L active_users,0L buyers,0L first_seen_users,CAST(0 AS DECIMAL(38,2)) purchase_amount,true amount_allowed").createOrReplaceTempView('m_daily_base')
        zero=bounded(sql(spark,'ratios'),1)[0]
        checks.equal('zero_denominators',[None,None,None,'no_active_users','no_buyers'],[zero[k] for k in ['buyer_rate','amount_per_buyer','first_seen_ratio','buyer_rate_status','amount_per_buyer_status']])
        checks.equal('canonical_synthetic_unchanged',18,reader.read(dates,'count',expected_scopes=[d['scope_id']]).count())
        checks.equal('one_synthetic_fact_load',1,reader.parquet_loads)
    checks.equal('synthetic_evidence_unchanged',True,before=={str(p):sha256(p) for p in registry.parent.rglob('*') if p.is_file()})
    return dict(checks=checks.rows,analysis_checks=a['checks'],rerun_checks=b['checks'],empty_checks=empty['checks'],synthetic_input_records=18)


if __name__=='__main__':unittest.main()
