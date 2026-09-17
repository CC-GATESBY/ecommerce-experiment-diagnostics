"""Synthetic facts with independent literal expectations; no real CSV access."""

import csv
from decimal import Decimal
import importlib
import json
from pathlib import Path
import unittest

from etl.event_config import CONTRACT, DERIVED, FLAGS, HEADER, sha256
from etl.fact_registry import FactReader, register_batch
from etl.oracle import build_expected
from scripts.run_quality import HEAVY, SCENARIOS, analyze, queries, sensitivity_rows


class QualityUnitTests(unittest.TestCase):
    def test_sql_sections_and_fixed_real_threshold(self):
        self.assertEqual(HEAVY,5000)
        self.assertIn('COUNT(*) > 5000',queries('sql/quality/session_profile.sql',HEAVY)['profiles'])
        self.assertIn('COUNT(*) > 3',queries('sql/quality/session_profile.sql',3)['profiles'])
        with self.assertRaises(ValueError):queries('sql/quality/session_profile.sql',-1)

    def test_relative_zero_and_removed_date(self):
        row=dict(period='2019-10-01',events=2,users=1,buyers=0,purchase_events=0,purchase_amount=Decimal('0.00'))
        scenarios={SCENARIOS[0]:{'__all__':row,'2019-10-01':row},SCENARIOS[1]:{'__all__':row,'2019-10-01':row},
                   SCENARIOS[2]:{'__all__':dict(row,events=0,users=0)}}
        rows=sensitivity_rows(scenarios,['2019-10-01'])
        zero=next(x for x in rows if x['scenario']==SCENARIOS[2] and x['period']=='2019-10-01' and x['metric']=='purchase_amount')
        self.assertIsNone(zero['relative_change']);self.assertEqual(zero['relative_change_reason'],'baseline_zero')
        removed=next(x for x in rows if x['scenario']==SCENARIOS[2] and x['period']=='2019-10-01' and x['metric']=='events')
        self.assertEqual(removed['absolute_change'],-2);self.assertEqual(removed['relative_change'],Decimal('-1'))
        self.assertEqual(removed['period_state'],'all_rows_removed_by_hypothesis')


def run_tests(spark,root,run):
    from pyspark.sql import functions as F, types as T
    events=importlib.import_module('etl.01_events'); checks={}
    def check(name,expected,actual):
        checks[name]=dict(expected=expected,actual=actual,**{'pass':expected==actual})
        if expected!=actual:raise AssertionError(name+': '+str(actual))
    def row(user,session,behavior='view',price='0',day=1,**change):
        data=dict(zip(HEADER,[f'2019-10-{day:02d} 12:00:00 UTC',behavior,'1','2','a.b','brand',price,user,session]))
        data.update(change);return [data[k] for k in HEADER]
    exact=row('1','S','purchase','2.00')
    rows=[exact[:],exact[:],exact[:],row('1','S','purchase','3.00'),
          row('2','S','purchase','1.0',product_id='2'),row('2','S','purchase','1.00',product_id='2'),
          row('3',''),row('4',' \t'),row('5','CROSS',event_time='2019-10-01 23:59:59 UTC'),
          row('5','CROSS','purchase','4',day=2,event_time='2019-10-02 00:00:01 UTC'),
          row('6','Z',price='1',day=2,brand='Brand'),row('6','Z',price='1',day=2,brand='brand'),
          row('6','Z',price='bad-a',day=2,product_id='9'),row('6','Z',price='bad-b',day=2,product_id='9'),
          row('7','ZERO',day=3),row('8','EXACT3',day=3),row('8','EXACT3',day=3),row('8','EXACT3',day=3)]
    check('synthetic_input_records',18,len(rows))
    fixture=root/'.local/t11'/('t12-'+run.name)/'synthetic'/'fixture-01';fixture.mkdir(parents=True,exist_ok=False)
    stage=fixture/'staging';stage.mkdir();source=fixture/'synthetic.csv'
    with source.open('x',newline='') as stream:
        w=csv.writer(stream,lineterminator='\n');w.writerow(HEADER);w.writerows(rows)
    dates=['2019-10-01','2019-10-02','2019-10-03'];digest=sha256(source)
    descriptor=dict(source_id='synthetic_t12',scope_id='synthetic_t12_scope',input_sha256=digest,contract_version=CONTRACT,
                    kind='synthetic',run_id='fixture-01',run_path=str(fixture.relative_to(root)),expected_records=len(rows),dates=dates,
                    series_id='synthetic_t12_series',sampling_rule='synthetic_literal_events_v1')
    expected=build_expected(source,stage/'expected_rows.jsonl',len(rows));daily=json.loads((stage/'expected_daily.json').read_text())
    fact=events.transform(spark.createDataFrame(rows,T.StructType([T.StructField(k,T.StringType()) for k in HEADER])),descriptor,'fixture-01')
    fact.write.mode('errorifexists').parquet(str(stage/'fact_events'));actual=spark.read.parquet(str(stage/'fact_events'))
    proof={}
    def verify(name,want,got):
        proof[name]=dict(expected=want,actual=got,**{'pass':want==got})
        if want!=got:raise AssertionError('fixture '+name)
    verify('schema',events.schema().simpleString(),actual.schema.simpleString());verify('rows',len(rows),actual.count())
    schema=T.StructType([T.StructField(k,T.StringType()) for k in HEADER+DERIVED]+[T.StructField(k,T.BooleanType()) for k in FLAGS])
    oracle=spark.read.schema(schema).json(str(stage/'expected_rows.jsonl'))
    canonical=events.canonical(actual).withColumn('event_timestamp_utc',F.regexp_replace('event_timestamp_utc','Z$','+00:00'))
    verify('expected_minus_actual_multiset',0,oracle.exceptAll(canonical).count());verify('actual_minus_expected_multiset',0,canonical.exceptAll(oracle).count())
    summary=events.summary(actual);daily_actual=events.daily_summary(actual)
    for key,value in expected.items():verify('summary_'+key,value,summary[key])
    verify('daily_bucket_keys',sorted(daily),sorted(daily_actual))
    for key,value in daily.items():verify('daily_'+key,value,daily_actual[key])
    verify('input_sha256_after',digest,sha256(source))
    (stage/'validation.json').write_text(json.dumps(dict(status='passed',spark_stopped=False,
        completion_mode='synthetic_no_active_writer_shared_test_session',contract_version=CONTRACT,
        checks=proof,schema=actual.schema.jsonValue(),summary=summary,daily_summary=daily_actual),indent=2))
    stage.rename(fixture/'complete');(fixture/'launch.json').write_text(json.dumps({**descriptor,'status':'passed'},indent=2))
    registry=fixture.parent/'registry.json';register_batch(root,registry,descriptor)
    before={str(p):sha256(p) for p in fixture.rglob('*') if p.is_file()}
    with FactReader(spark,root,registry,'synthetic_t12_series') as reader:
        reader.read(dates,'count',expected_scopes=['synthetic_t12_scope'])
        data=reader.read(dates,'amount',expected_scopes=['synthetic_t12_scope'])
        results=analyze(spark,data,dates,threshold=3,synthetic=True)
        normal=next(x for x in results['duplicates'] if x['key_type']=='normalized' and x['behavior']=='__all__')
        raw=next(x for x in results['duplicates'] if x['key_type']=='raw_exact' and x['behavior']=='__all__')
        names=['duplicate_groups','involved_events','excess_events','involved_users','purchase_involved_events','purchase_excess_events','hypothetical_purchase_amount_reduction']
        check('normalized_literal_counts',[3,8,5,3,5,3,Decimal('5.00')],[normal[k] for k in names])
        check('raw_literal_counts',[2,6,4,2,3,2,Decimal('4.00')],[raw[k] for k in names])
        sessions=results['sessions']
        check('session_literal_counts',[6,2,4,2,8,2,4,Decimal('9.00'),1,2],
              [sessions[k] for k in ['valid_sessions','missing_session_events','max_session_events','heavy_sessions','heavy_events','heavy_users','heavy_purchase_events','heavy_purchase_amount','cross_day_sessions','max_observed_span_seconds']])
        check('session_quantiles',[2,4,4],sessions['event_count_quantiles'])
        metric=['events','users','buyers','purchase_events','purchase_amount']
        for name,want in zip(SCENARIOS,[[18,8,3,7,Decimal('15.00')],[13,8,3,4,Decimal('10.00')],[10,6,2,3,Decimal('6.00')]]):
            check(name+'_literal_month',want,[results['scenarios'][name]['__all__'][k] for k in metric])
        day_expectations=[[[9,5,2,6,'11.00'],[5,2,1,1,'4.00'],[4,2,0,0,'0.00']],
                          [[6,5,2,3,'6.00'],[5,2,1,1,'4.00'],[2,2,0,0,'0.00']],
                          [[5,4,1,2,'2.00'],[1,1,1,1,'4.00'],[4,2,0,0,'0.00']]]
        for name,wants in zip(SCENARIOS,day_expectations):
            for day,want in zip(dates,wants):
                want[-1]=Decimal(want[-1]);check(name+'_literal_'+day,want,[results['scenarios'][name][day][k] for k in metric])
        # Bounded scalar probes exercise the exact-key boundaries without exporting identifiers.
        check('three_exact_records',[1,3,2],list(spark.sql('SELECT COUNT(*) g, SUM(group_size) n, SUM(group_size-1) e FROM q_duplicates WHERE user_id=\'1\' AND group_size=3').first()))
        check('different_prices_not_merged',2,spark.sql("SELECT COUNT(*) FROM q_duplicates WHERE user_id='1'").first()[0])
        check('decimal_normalized_not_raw',[1,2],[spark.sql("SELECT COUNT(*) FROM q_duplicates WHERE user_id='2'").first()[0],spark.sql("SELECT COUNT(*) FROM q_raw_duplicates WHERE user_id='2'").first()[0]])
        check('unparsed_price_and_brand_case_preserved',4,spark.sql("SELECT COUNT(*) FROM q_duplicates WHERE user_id='6'").first()[0])
        check('same_session_different_users',2,spark.sql("SELECT COUNT(*) FROM q_sessions WHERE user_session='S'").first()[0])
        check('exact_threshold_not_heavy',0,spark.sql("SELECT COUNT(*) FROM q_sessions WHERE user_id='8' AND heavy_session").first()[0])
        clean=analyze(spark,data.where("user_id='7'"),['2019-10-03'],threshold=3,synthetic=True)
        check('no_candidates_or_heavy',[0,0],[clean['duplicates'][0]['duplicate_groups'],clean['sessions']['heavy_sessions']])
        check('clean_branches_unchanged',True,all(v==clean['scenarios'][SCENARIOS[0]] for v in clean['scenarios'].values()))
        empty=analyze(spark,data.where("user_id='1'"),['2019-10-01'],threshold=3,synthetic=True)
        removed=next(x for x in empty['sensitivity'] if x['scenario']==SCENARIOS[2] and x['period']=='2019-10-01' and x['metric']=='events')
        check('fully_removed_day_explicit_zero',[0,Decimal('-1'),'all_rows_removed_by_hypothesis'],[removed['value'],removed['relative_change'],removed['period_state']])
        check('original_reader_retains_all',18,reader.read(dates,'amount',expected_scopes=['synthetic_t12_scope']).count())
        check('single_registered_fact_load',1,reader.parquet_loads)
    check('synthetic_fact_unchanged',before,{str(p):sha256(p) for p in fixture.rglob('*') if p.is_file()})
    return dict(status='passed',synthetic_input_records=18,checks=checks,analysis_checks=results['checks'],
                clean_checks=clean['checks'],empty_branch_checks=empty['checks'],fixture_checks=proof,
                results=results,real_threshold_constant=HEAVY,test_threshold=3)


if __name__=='__main__':unittest.main()
