"""Raw synthetic CSV literals, real Spark build/publish calls, and snapshot selection."""
import csv
from datetime import datetime
from decimal import Decimal
import importlib
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from crosscheck_duckdb import HEADER,PARSE_FIELDS,KEYS,rows,scalar,ready,save,connection,import_csv,compute,compare,code_hashes,validate_candidate_receipt,csv_structure
from scripts.metric_snapshot import select_snapshot,digest,require


def row(day,user,session,behavior='view',price='0',brand='unknown',category='a.b',**changes):
    r=dict(zip(HEADER,[f'2019-10-{day:02d} 12:00:00 UTC',behavior,'1','2',category,brand,price,user,session]));r.update(changes);return r


def definitions():
    duplicate=row(1,'2','S','purchase','50','other')
    good=[row(1,'01','S'),row(1,'01','S','cart','20',category='b.c'),duplicate,duplicate.copy(),row(1,'3','',price='200',brand='',category=''),
          row(2,'01','S','purchase','20',category='b.c'),row(2,'4','T','purchase','0','other'),row(2,'5','V',price='bad'),
          row(5,'01','N',price='200',brand='prior_small'),row(5,'01','N','purchase','200','prior_small'),row(5,'2','S',price='50',brand='other',category='c.x'),
          row(5,'6','',price='20',brand='',category='.bad'),row(5,'7','Q','purchase','bad','other'),
          row(8,'01','N',price='200',brand='new'),row(8,'01','N',price='200',brand='new',category='b'),row(8,'8','R','purchase','50','new'),
          row(8,'1','R',price='0',category=''),row(3,'10','X',price='-1',brand='Z',category='bad..x')]
    cases=[('zero',{},'0',True),('twenty',{},'20',True),('fifty',{},'50',True),('two_hundred',{},'200',True),
      ('scale',{},'1.000',False),('precision',{},'10000000000000000',False),('nan',{},'NaN',False),('plus_nan',{},'+NaN',False),
      ('inf',{},'-Inf',False),('multi_nan',{},'++NaN',False),('multi_inf',{},'+-Inf',False),('negative',{},'-1',False),
      ('empty_price',{},'',False),('id_lf',{'user_id':'123\n'},'1.20',False),('id_cr',{'user_id':'123\r'},'1.20',False),
      ('id_empty',{'user_id':''},'1.20',False),('id_space',{'user_id':' \t'},'1.20',False),('price_lf',{},'1.20\n',False),
      ('price_cr',{},'1.20\r',False),('time_lf',{'event_time':'2019-10-01 12:00:00 UTC\n'},'1.20',False),
      ('invalid_date',{'event_time':'2019-02-31 12:00:00 UTC'},'1.20',False),('empty_time',{'event_time':''},'1.20',False),
      ('quoted',{'brand':'a,"b\r\nc','category_code':'','user_session':' \t'},'1.20',True),
      ('unknown_behavior',{'event_type':'other'},'1.20',False),('minus_infinity',{},'--Infinity',False)]
    boundary=[row(1,'001','s','purchase',price,product_id=name,**changes) for name,changes,price,_ in cases]
    return good,boundary,cases


def ensure_inputs():
    import io
    good,boundary,cases=definitions();folder=ROOT/'.local/t14/synthetic-inputs';folder.mkdir(exist_ok=True)
    for name,data in [('good',good),('boundary',boundary)]:
        stream=io.StringIO(newline='');w=csv.DictWriter(stream,fieldnames=HEADER,lineterminator='\n');w.writeheader();w.writerows(data)
        content=stream.getvalue().encode();path=folder/(name+'.csv')
        if path.exists():require(path.read_bytes()==content,'existing synthetic source changed')
        else:
            with path.open('xb') as f:f.write(content)
    require(len(good)+len(boundary)<=100,'synthetic row budget exceeded')
    return folder,good,boundary,cases


class IdempotencyUnitTests(unittest.TestCase):
    def test_fixture_budget_and_scope(self):
        g,b,_=definitions();self.assertEqual([len(g),len(b)],[18,25]);self.assertLessEqual(len(g)+len(b),100)
    def test_selector_refuses_multiple_or_wildcard(self):
        for choice in [['a','b'],'.local/t13/*']:
            with self.assertRaises(ValueError):select_snapshot(ROOT,choice,scope_id='x',source_run='x')

    def test_sanitized_candidate_receipt_comparison(self):
        from copy import deepcopy
        a=dict(status='validated',kind='user_sample_candidate',run_id='r',scope_id='s',parent_sha256='parent',algorithm_version='v',seed='s',
               sample=dict(sha256='sha',bytes=10,profile=dict(record_count=2,daily_records={'d':2},hourly_records={'h':2})))
        b=deepcopy(a);b['sample']['local_relative_path']='local.csv'
        b['sample']['profile']=dict(record_count=2,daily_records_report='report.csv',observed_utc_hour_count=1)
        validate_candidate_receipt(a,b)
        for key in ('sha256','bytes'):
            bad=deepcopy(a);bad['sample'][key]='different'
            with self.assertRaises(ValueError):validate_candidate_receipt(bad,b)
        bad=deepcopy(a);bad['sample']['profile']['daily_records']['d']=1
        with self.assertRaises(ValueError):validate_candidate_receipt(bad,b)

    def test_structure_errors_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'synthetic.csv'
            for content in [','.join(HEADER)+'\na,b\n',','.join(HEADER)+'\n'+','.join(['x']*10)+'\n','wrong\n']:
                p.write_text(content)
                with self.assertRaises(ValueError):csv_structure(p)


def spark_stage(spark,run):
    from pyspark.sql import types as T
    from etl.date_quality import evaluate
    from scripts.run_metrics import build_metrics
    events=importlib.import_module('etl.01_events');folder,good,boundary,cases=ensure_inputs()
    checks={};pending=[];fixtures={}
    def check(name,want,got):
        checks[name]=dict(expected=ready(want),actual=ready(got),**{'pass':want==got});require(want==got,name)
    for name,source_rows in [('good',good),('boundary',boundary)]:
        source=folder/(name+'.csv');raw=(spark.read.schema(T.StructType([T.StructField(k,T.StringType()) for k in HEADER]))
            .option('header',True).option('lineSep','\n').option('multiLine',True).option('mode','FAILFAST')
            .option('quote','"').option('escape','"').option('ignoreLeadingWhiteSpace',False).option('ignoreTrailingWhiteSpace',False)
            .option('nullValue','').option('emptyValue','').csv(str(source)))
        desc=dict(source_id='synthetic_t14',scope_id='synthetic_t14_scope',input_sha256=digest(source))
        fact=events.transform(raw,desc,'synthetic-fixture')
        expected=spark.createDataFrame([[r[k] for k in HEADER] for r in source_rows],T.StructType([T.StructField(k,T.StringType()) for k in HEADER]))
        check(name+'_raw_multiset_preservation',0,expected.exceptAll(fact.select(*HEADER)).count()+fact.select(*HEADER).exceptAll(expected).count())
        target=run/'staging'/(name+'_parsed');fact.write.mode('errorifexists').parquet(str(target));fixtures[name]=target
        if name=='boundary':
            values={r['product_id']:r.asDict() for r in fact.select('product_id',*PARSE_FIELDS).limit(100).collect()}
            for label,_,_,eligible in cases:check('literal_spark_'+label,eligible,values[label]['amount_eligible'])
            for name2 in ['nan','plus_nan','inf']:check('nonfinite_spark_'+name2,True,values[name2]['price_nonfinite'])
            for name2 in ['multi_nan','multi_inf','minus_infinity']:check('invalid_spark_'+name2,True,values[name2]['price_invalid'])
        else:
            identity=dict(desc,contract_version='rees46-events-v1.0.1',run_id='synthetic-fixture',source_run='synthetic-fixture')
            summary=events.daily_summary(fact);gates=evaluate(identity,summary,sorted(summary))
            for tag,dates in [('one-day',['2019-10-05']),('repeat',['2019-10-05']),('two-days',['2019-10-05','2019-10-08'])]:
                subrun=run/'snapshots'/tag;subrun.mkdir(parents=True,exist_ok=False);stage=subrun/'staging';stage.mkdir()
                result=build_metrics(spark,fact,gates,stage/'metrics',identity,top_k=2,synthetic=True,output_dates=dates)
                result.update(status='passed',spark_stopped=False,synthetic=True,output_dates=dates)
                save(stage/'validation.json',result);pending.append(subrun)
            # The actual builder fails after it has created staging, not a fake write path.
            failed=run/'snapshots'/'failed-attempt';failed.mkdir();(failed/'staging').mkdir()
            from copy import deepcopy
            mismatch=deepcopy(gates);mismatch['2019-10-09']=dict(next(iter(gates.values())),utc_date='2019-10-09')
            try:build_metrics(spark,fact,mismatch,failed/'staging/metrics',identity,top_k=2,synthetic=True)
            except ValueError as exc:
                save(failed/'staging/validation.json',dict(status='failed',spark_stopped=False,error=str(exc)))
                save(failed/'launch.json',dict(status='failed'))
                check('actual_build_failure_retained',True,(failed/'staging/metrics').is_dir())
            else:raise AssertionError('injected date mismatch should fail')
            retry=run/'snapshots'/'retry';retry.mkdir();(retry/'staging').mkdir()
            result=build_metrics(spark,fact,gates,retry/'staging/metrics',identity,top_k=2,synthetic=True,output_dates=['2019-10-05','2019-10-08'])
            result.update(status='passed',spark_stopped=False,synthetic=True,output_dates=['2019-10-05','2019-10-08'])
            save(retry/'staging/validation.json',result);pending.append(retry)
            try:build_metrics(spark,fact,gates,pending[0]/'staging/metrics',identity,top_k=2,synthetic=True)
            except FileExistsError:check('same_run_no_overwrite',True,True)
            else:raise AssertionError('existing metrics overwritten')
            save(run/'staging/spark_daily_gates.json',gates)
            from scripts.run_metrics import sql as spark_sql
            fact.where("user_id IN ('4','10')").createOrReplaceTempView('m_fact')
            tied=spark_sql(spark,'brand_mapping',2).orderBy('brand_rank').select('brand').limit(2).collect()
            check('spark_brand_tie_binary_order',['Z','other'],[r['brand'] for r in tied])
    return dict(checks=checks,pending=pending,fixtures=fixtures,raw_records=len(good)+len(boundary))


def finish_after_spark(run,result):
    from scripts.run_metrics import publish
    for subrun in result.pop('pending'):
        proof=subrun/'staging/validation.json';v=json.loads(proof.read_text());v['spark_stopped']=True;proof.write_text(json.dumps(ready(v),indent=2)+'\n')
        publish(subrun/'staging',subrun);save(subrun/'launch.json',dict(status='passed'))
    checks=result['checks']
    def check(name,want,got):
        checks[name]=dict(expected=ready(want),actual=ready(got),**{'pass':want==got});require(want==got,name)
    failed=run/'snapshots/failed-attempt'
    try:publish(failed/'staging',failed)
    except ValueError:check('failed_publish_refused',True,True)
    else:raise AssertionError('partial published')
    kwargs=dict(scope_id='synthetic_t14_scope',source_run='synthetic-fixture')
    try:select_snapshot(ROOT,failed,**kwargs)
    except (ValueError,FileNotFoundError):check('failed_read_refused',True,True)
    else:raise AssertionError('partial selected')
    folder,good,boundary,cases=ensure_inputs()
    c=connection(run/'staging/duckdb-synthetic')
    try:
        import_csv(c,folder/'good.csv','synthetic_t14_scope');compute(c,2,True)
        expected={'2019-10-01':[5,3,1,2,'100.00',2,1,3], '2019-10-02':[3,3,2,2,'20.00',3,2,2],
                  '2019-10-03':[1,1,0,0,'0.00',1,0,1], '2019-10-05':[5,4,2,2,None,3,2,2], '2019-10-08':[4,3,1,1,'50.00',3,1,2]}
        fields=['event_records','active_users','buyers','purchase_events','purchase_amount','sessions','purchase_sessions','first_seen_users']
        daily=rows(c,'SELECT * FROM d_agg_daily_metrics ORDER BY utc_date',limit=5)
        for r in daily:check('duck_literal_'+str(r['utc_date']),expected[str(r['utc_date'])],ready([r[k] for k in fields]))
        gates=json.loads((run/'staging/spark_daily_gates.json').read_text())
        for r in daily:
            g=gates[str(r['utc_date'])];check('independent_gates_'+str(r['utc_date']),[g['count_allowed'],g['amount_allowed'],g['amount_status']],[r['count_allowed'],r['amount_allowed'],r['amount_status']])
        selections={tag:select_snapshot(ROOT,run/'snapshots'/tag,**kwargs) for tag in ('one-day','repeat','two-days','retry')}
        fingerprints={tag:x['inventory'] for tag,x in selections.items()}
        for tag,snap in selections.items():
            check('csv_independent_vs_spark_'+tag,True,compare(c,snap,run/'staging'/('diff-'+tag),snap['proof']['output_dates'])['passed'])
            for r in snap['proof']['daily']:check('spark_literal_'+tag+'_'+str(r['utc_date']),expected[str(r['utc_date'])],ready([r[k] for k in fields]))
        for table in KEYS:
            def view(tag,name):c.read_parquet(selections[tag]['files'][table]).create_view(name)
            view('one-day','a');view('repeat','b')
            check('rerun_multiset_'+table,0,scalar(c,'SELECT COUNT(*) FROM ((SELECT * FROM a EXCEPT ALL SELECT * FROM b) UNION ALL (SELECT * FROM b EXCEPT ALL SELECT * FROM a))'))
            view('two-days','b');where=" WHERE utc_date=DATE '2019-10-05'" if 'utc_date' in KEYS[table] else ''
            check('append_old_date_unchanged_'+table,0,scalar(c,'SELECT COUNT(*) FROM ((SELECT * FROM a EXCEPT ALL SELECT * FROM b'+where+') UNION ALL (SELECT * FROM b'+where+' EXCEPT ALL SELECT * FROM a))'))
            view('retry','a')
            check('retry_equal_completed_'+table,0,scalar(c,'SELECT COUNT(*) FROM ((SELECT * FROM a EXCEPT ALL SELECT * FROM b) UNION ALL (SELECT * FROM b EXCEPT ALL SELECT * FROM a))'))
        selected=select_snapshot(ROOT,run/'snapshots/retry',**kwargs)
        c.read_parquet(selected['files']['agg_daily_metrics']).create_view('final_metrics')
        check('selected_snapshot_days',2,scalar(c,'SELECT COUNT(*) FROM final_metrics'))
        check('selected_snapshot_event_total',9,scalar(c,'SELECT SUM(event_records) FROM final_metrics'))
        check('append_new_date_once',1,scalar(c,"SELECT COUNT(*) FROM final_metrics WHERE utc_date=DATE '2019-10-08'"))
        check('first_seen_keeps_full_window',10,scalar(c,'SELECT COUNT(*) FROM d_dim_user_first_seen'))
        check('frozen_top2_literal',['other','unknown'],[r['brand'] for r in rows(c,'SELECT brand FROM d_brand_mapping ORDER BY brand_rank',limit=2)])
        check('post_reference_brand_not_selected',0,scalar(c,"SELECT COUNT(*) FROM d_brand_mapping WHERE brand='new'"))
        check('post_reference_brand_other',3,scalar(c,"SELECT COUNT(*) FROM decorated WHERE utc_date=DATE '2019-10-08' AND brand='new' AND brand_key='bucket:other'"))
        check('leading_zero_user_distinct',2,scalar(c,"SELECT COUNT(DISTINCT user_id) FROM eligible WHERE user_id IN ('01','1')"))
        check('zero_purchase_amount_literal','0.00',str(scalar(c,"SELECT purchase_amount FROM d_agg_user_daily WHERE user_id='4'")))
        check('no_purchase_state_literal','no_purchases',scalar(c,"SELECT amount_status FROM d_agg_daily_metrics WHERE utc_date=DATE '2019-10-03'"))
        check('unknown_brand_typed_collision',4,scalar(c,"SELECT COUNT(DISTINCT brand_key) FROM decorated"))
        for tag,x in selections.items():check('snapshot_immutable_'+tag,fingerprints[tag],select_snapshot(ROOT,run/'snapshots'/tag,**kwargs)['inventory'])
        c.execute("CREATE OR REPLACE VIEW eligible AS SELECT p.*,c.scope_id FROM parsed p CROSS JOIN context c WHERE event_eligible AND user_id IN ('4','10')")
        compute(c,2,True)
        check('duck_brand_tie_binary_order',['Z','other'],[r['brand'] for r in rows(c,'SELECT brand FROM d_brand_mapping ORDER BY brand_rank',limit=2)])
    finally:c.close()
    c=connection(run/'staging/duckdb-boundary')
    try:
        import_csv(c,folder/'boundary.csv','synthetic_boundary')
        raw=rows(c,'SELECT * FROM raw_csv ORDER BY product_id',limit=25)
        check('duck_raw_strings_preserved',sorted(boundary,key=lambda r:r['product_id']),raw)
        parsed={r['product_id']:r for r in rows(c,'SELECT product_id,'+','.join(PARSE_FIELDS)+' FROM parsed',limit=25)}
        for label,_,_,eligible in cases:check('literal_duck_'+label,eligible,parsed[label]['amount_eligible'])
        for label,flag in {'scale':'price_scale_exceeded','precision':'price_precision_exceeded','negative':'price_negative','empty_price':'price_missing',
                           'id_lf':'user_id_invalid','id_cr':'user_id_invalid','id_empty':'user_id_missing','id_space':'user_id_missing',
                           'price_lf':'price_invalid','price_cr':'price_invalid','time_lf':'time_invalid','invalid_date':'time_invalid','empty_time':'time_missing'}.items():
            check('literal_duck_flag_'+label,True,parsed[label][flag])
        for label in ('nan','plus_nan','inf'):check('duck_nonfinite_'+label,True,parsed[label]['price_nonfinite'])
        for label in ('multi_nan','multi_inf','minus_infinity'):check('duck_invalid_'+label,True,parsed[label]['price_invalid'])
        files=[str(p) for p in result['fixtures']['boundary'].iterdir() if p.suffix=='.parquet'];c.read_parquet(files).create_view('spark_boundary')
        cols=','.join(HEADER+PARSE_FIELDS)
        check('boundary_fields_both_implementations',0,scalar(c,'SELECT COUNT(*) FROM ((SELECT '+cols+' FROM parsed EXCEPT ALL SELECT '+cols+' FROM spark_boundary) UNION ALL (SELECT '+cols+' FROM spark_boundary EXCEPT ALL SELECT '+cols+' FROM parsed))'))
        check('bad_time_blocks_entire_batch',0,scalar(c,'SELECT COUNT(*) FROM quality WHERE count_allowed'))
    finally:c.close()
    result.update(status='passed',spark_stopped=True,code_sha256=code_hashes())
    return result


if __name__=='__main__':unittest.main()
