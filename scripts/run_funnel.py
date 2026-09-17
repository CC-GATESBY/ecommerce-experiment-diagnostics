"""T2.1 controlled SQL coverage and first-view funnel; no CSV access."""
import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from etl.event_config import sha256
from etl.fact_registry import FactReader, load_registry, require
from etl.resource_budget import directory_bytes
from scripts.project_config import load_config
from scripts.run_metrics import Checks, bounded, ready, write_json, publish, DATES, SCOPE, SERIES
from scripts.validate_analysis_scope import validate_scope, canonical_snapshot, VERSION as ANALYSIS_VERSION

VERSION='rees46-funnel-v1'
KEY=['scope_id','user_id','user_session','product_id']
CODE=['scripts/run_funnel.py','tests/test_funnel.py','reports/funnel_definition.md','config/funnel.example.json',
      'sql/metrics/behavior_coverage.sql','sql/metrics/funnel_paths.sql','sql/metrics/funnel_summary.sql',
      'etl/fact_registry.py','etl/date_quality.py','scripts/metric_snapshot.py','scripts/validate_analysis_scope.py','scripts/run_metrics.py','scripts/project_config.py']
COUNTS=['n_view','n_cart','n_purchase','n_three_step','view_cart_purchase',
        'view_purchase_no_confirmed_intermediate_cart','view_cart_no_observed_purchase','view_only']


def code_hashes():return {p:sha256(ROOT/p) for p in CODE}


def sql_text(name):return (ROOT/'sql/metrics'/f'{name}.sql').read_text()


def local_path(value):
    require(isinstance(value,str) and value and 'REPLACE' not in value and not any(c in value for c in '*?['),'explicit populated path required')
    path=(ROOT/value).resolve();require(path.is_relative_to(ROOT) and path.is_file() or path.is_relative_to(ROOT/'.local') and path.is_dir(),'invalid project path')
    return path


def validate_config(cfg):
    require(set(cfg)=={'analysis_scope','scope_receipt','metrics_config','metrics_run','funnel_version','source_run','analysis_scope_version'},'funnel config fields mismatch')
    require(cfg['analysis_scope']=='config/analysis_scope.yaml' and cfg['funnel_version']==VERSION
            and cfg['analysis_scope_version']==ANALYSIS_VERSION and cfg['source_run']=='month-v101-01','unapproved funnel binding')
    for key in ('analysis_scope','scope_receipt','metrics_config','metrics_run'):local_path(cfg[key])
    require(Path(cfg['metrics_run']).name=='metrics-month-01','canonical metric run required')
    return cfg


def write_csv(path,rows):
    require(bool(rows),'empty report needs explicit schema')
    with Path(path).open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(ready(rows))


def build_funnel(spark,fact,stage,lineage):
    from pyspark import StorageLevel
    from pyspark.sql import functions as F
    stage=Path(stage);stage.mkdir(parents=True,exist_ok=False);checks=Checks();caches=[]
    def cache(frame,name):
        frame=frame.persist(StorageLevel.MEMORY_AND_DISK);caches.append(frame);frame.createOrReplaceTempView(name);return frame
    def coverage(frame):
        frame.createOrReplaceTempView('f_coverage_input')
        return sorted(bounded(spark.sql(sql_text('behavior_coverage')),128),key=lambda r:(r['level'],r['utc_date'] or '',r['event_type']))
    def signature(frame):
        frame.createOrReplaceTempView('f_signature')
        return sorted(bounded(spark.sql("""SELECT CAST(event_date_utc AS STRING) utc_date,COUNT(*) event_records,
            COUNT(DISTINCT user_id) active_users,COUNT_IF(event_type='purchase') purchase_events,
            COUNT(DISTINCT CASE WHEN event_type='purchase' THEN user_id END) buyers
            FROM f_signature GROUP BY GROUPING SETS ((),(event_date_utc))"""),32),key=lambda r:r['utc_date'] or '')
    try:
        checks.equal('input_is_eligible',0,fact.where('NOT event_eligible OR event_eligible IS NULL').count())
        checks.equal('input_in_observation',0,fact.where("event_timestamp_utc IS NULL OR event_timestamp_utc<TIMESTAMP '2019-10-01' OR event_timestamp_utc>=TIMESTAMP '2019-11-01'").count())
        base_cov=coverage(fact);base_sig=signature(fact);input_rows=sum(r['event_records'] for r in base_cov if r['level']=='month')
        events=fact.withColumn('path_key_valid',F.expr('NOT (user_id_missing OR user_id_invalid OR product_id_missing OR product_id_invalid OR session_missing)'))
        events.createOrReplaceTempView('f_events')
        pieces=sql_text('funnel_paths').split(';')
        for statement in pieces[:-1]:spark.sql(statement)
        starts=spark.table('f_starts')
        checks.equal('start_pk_unique',0,starts.groupBy(*KEY).count().where('count>1').count())
        linked=cache(spark.table('f_linked'),'f_linked')
        checks.equal('left_join_rows',input_rows,linked.count())
        checks.equal('left_join_coverage',base_cov,coverage(linked))
        checks.equal('left_join_daily_users',base_sig,signature(linked))
        paths=spark.sql(pieces[-1])
        for name,value in lineage.items():paths=paths.withColumn(name,F.lit(value))
        paths=cache(paths,'f_paths');path_rows=paths.count()
        checks.equal('start_keys_equal_paths',starts.count(),path_rows)
        checks.equal('path_pk_unique',0,paths.groupBy(*KEY).count().where('count>1').count())
        checks.equal('path_pk_not_null',0,paths.where(' OR '.join(x+' IS NULL' for x in KEY)).count())
        checks.equal('strict_cart_witness',0,paths.where('has_cart_after_view AND NOT (first_view_time<strict_cart_time AND strict_cart_time<=deadline)').count())
        checks.equal('strict_purchase_witness',0,paths.where('has_purchase_after_view AND NOT (first_view_time<strict_purchase_time AND strict_purchase_time<=deadline)').count())
        checks.equal('strict_three_witness',0,paths.where('has_three_step AND NOT (first_view_time<strict_cart_time AND strict_cart_time<strict_purchase_time AND strict_purchase_time<=deadline)').count())
        checks.equal('formal_time_and_order',0,paths.where("release_status='formal' AND (order_uncertain OR right_censored OR first_view_time>=TIMESTAMP '2019-10-31' OR deadline>=TIMESTAMP '2019-11-01')").count())
        summary=sorted(bounded(spark.sql(sql_text('funnel_summary')),37),key=lambda r:(r['level'],r['segment']))
        overall=next(r for r in summary if r['level']=='overall')
        for row in summary:
            label=row['level']+'_'+row['segment']
            checks.equal('count_bounds_'+label,True,0<=row['n_three_step']<=row['n_cart']<=row['n_view'] and 0<=row['n_three_step']<=row['n_purchase']<=row['n_view'])
            checks.equal('class_sum_'+label,row['n_view'],sum(row[k] for k in COUNTS[4:]))
            for rate,num,den in [('view_to_cart','n_cart','n_view'),('cart_to_purchase_three_step','n_three_step','n_cart'),('view_to_purchase','n_purchase','n_view'),('three_step_ratio','n_three_step','n_view')]:
                checks.equal('ratio_'+label+'_'+rate,None if row[den]==0 else row[num]/row[den],row[rate])
        for level in ('start_day','price_band'):
            for col in COUNTS:checks.equal('sum_'+level+'_'+col,overall[col],sum(r[col] for r in summary if r['level']==level))
        releases={r['release_status']:r['n'] for r in bounded(paths.groupBy('release_status').agg(F.count('*').alias('n')),3)}
        checks.equal('release_conservation',path_rows,sum(releases.values()))
        checks.equal('formal_denominator',releases.get('formal',0),overall['n_view'])
        exclusions=[]
        def ex(unit,reason,n,den):exclusions.append(dict(unit=unit,reason=reason,count=n,denominator=den,ratio=n/den if den else None,ratio_status='defined' if den else 'zero_denominator'))
        for status in ('formal','right_censored','order_uncertain'):ex('path_release',status,releases.get(status,0),path_rows)
        flags=bounded(paths.agg(F.count_if('order_uncertain').alias('order_uncertain'),F.count_if('right_censored').alias('right_censored')),1)[0]
        for flag,n in flags.items():ex('path_flag_overlapping',flag,n,path_rows)
        key_counts=bounded(spark.sql("""SELECT CASE WHEN user_id_missing OR user_id_invalid THEN 'invalid_user_id'
            WHEN product_id_missing OR product_id_invalid THEN 'invalid_product_id'
            WHEN session_missing THEN 'missing_session' ELSE 'valid_path_key' END reason,COUNT(*) n FROM f_events GROUP BY 1"""),4)
        by_reason={r['reason']:r['n'] for r in key_counts}
        for reason in ('invalid_user_id','invalid_product_id','missing_session','valid_path_key'):ex('event_key_mutually_exclusive',reason,by_reason.get(reason,0),input_rows)
        raw_flags=bounded(spark.sql('SELECT COUNT_IF(user_id_missing OR user_id_invalid) u,COUNT_IF(product_id_missing OR product_id_invalid) p,COUNT_IF(session_missing) s FROM f_events'),1)[0]
        for key,name in [('u','invalid_user_id'),('p','invalid_product_id'),('s','missing_session')]:ex('event_key_flag_overlapping',name,raw_flags[key],input_rows)
        for r in bounded(paths.groupBy('first_view_price_status').agg(F.count('*').alias('n')),3):ex('path_price',r['first_view_price_status'],r['n'],path_rows)
        no_view=linked.where('path_key_valid AND first_view_time IS NULL').count();ex('event_view_availability','valid_key_without_view',no_view,input_rows)
        audit=sorted(bounded(spark.sql("""WITH tagged AS (SELECT event_date_utc,
            CASE WHEN NOT path_key_valid THEN 'invalid_path_key' WHEN first_view_time IS NULL THEN 'no_view_same_key'
              WHEN event_timestamp_utc<=first_view_time THEN 'purchase_at_or_before_first_view'
              WHEN first_view_time>=TIMESTAMP '2019-10-31' THEN 'start_outside_formal_range'
              WHEN event_timestamp_utc>deadline THEN 'beyond_24_hours' ELSE 'within_path_window' END reason
            FROM f_linked WHERE event_type='purchase')
            SELECT CASE WHEN GROUPING(event_date_utc)=1 THEN 'month' ELSE 'day' END level,
            CAST(event_date_utc AS STRING) utc_date,reason,COUNT(*) purchase_events
            FROM tagged GROUP BY GROUPING SETS ((reason),(event_date_utc,reason))"""),192),key=lambda r:(r['level'],r['utc_date'] or '',r['reason']))
        for row in base_sig:
            lev='month' if row['utc_date'] is None else 'day'
            checks.equal('purchase_audit_'+str(row['utc_date']),row['purchase_events'],sum(r['purchase_events'] for r in audit if r['level']==lev and r['utc_date']==row['utc_date']))
        paths.write.mode('errorifexists').parquet(str(stage/'funnel_paths'))
        restored=spark.read.parquet(str(stage/'funnel_paths'))
        checks.equal('readback_schema',paths.schema.simpleString(),restored.schema.simpleString())
        checks.equal('readback_rows',path_rows,restored.count())
        checks.equal('readback_pk_unique',0,restored.groupBy(*KEY).count().where('count>1').count())
        checks.equal('written_minus_readback',0,paths.exceptAll(restored).count())
        checks.equal('readback_minus_written',0,restored.exceptAll(paths).count())
        if base_cov:write_csv(stage/'behavior_coverage.csv',base_cov)
        exclusions.sort(key=lambda r:(r['unit'],r['reason']))
        write_csv(stage/'funnel_summary.csv',summary);write_csv(stage/'funnel_exclusions.csv',exclusions)
        if audit:write_csv(stage/'purchase_path_coverage.csv',audit)
        return dict(checks=checks.rows,input_records=input_rows,path_records=path_rows,coverage=base_cov,signature=base_sig,summary=summary,
                    exclusions=exclusions,purchase_audit=audit,schema=paths.schema.jsonValue(),lineage=lineage)
    finally:
        for frame in reversed(caches):frame.unpersist()


def real_analysis(spark,config,stage):
    cfg=validate_config(json.loads(Path(config).read_text()));scope=yaml.safe_load(local_path(cfg['analysis_scope']).read_text());days=validate_scope(scope)
    proof=json.loads(local_path(cfg['scope_receipt']).read_text())
    require(proof['status']=='passed' and proof['binding']==scope['binding'] and proof['analysis_scope_version']==ANALYSIS_VERSION
            and proof['scope_sha256']==sha256(local_path(cfg['analysis_scope'])),'T1.5 completion or scope mismatch')
    protected=dict(proof['evidence_hashes']);protected[cfg['analysis_scope']]=proof['scope_sha256']
    for path,digest in protected.items():require(sha256(ROOT/path)==digest,'bound evidence changed: '+Path(path).name)
    metrics_cfg=json.loads(local_path(cfg['metrics_config']).read_text())
    from scripts.run_metrics import validate_config as validate_metrics
    validate_metrics(metrics_cfg)
    snapshot=canonical_snapshot(ROOT,scope,cfg['metrics_run'])
    registry=load_registry(ROOT,metrics_cfg['registry_path'])
    batches=[r for r in registry['batches'] if r['descriptor']['series_id']==SERIES]
    require(len(batches)==1,'exactly one canonical fact batch required')
    entry=batches[0];d=entry['descriptor']
    require(d['run_id']==cfg['source_run'] and d['scope_id']==SCOPE and d['input_sha256']==scope['binding']['candidate_sha256'] and d['dates']==days,'fact identity mismatch')
    for p in entry['inventory']:protected[p['path']]=p['sha256']
    for path,item in snapshot['inventory'].items():protected[path]=item['sha256']
    reader=FactReader(spark,ROOT,metrics_cfg['registry_path'],SERIES)
    try:
        fact=reader.read(days,'count',expected_scopes=[SCOPE])
        result=build_funnel(spark,fact,stage,dict(analysis_scope_version=ANALYSIS_VERSION,funnel_version=VERSION,source_run=d['run_id'],input_sha256=d['input_sha256'],funnel_run=Path(stage).parent.name))
        checks=Checks();checks.rows=result['checks'];checks.equal('single_parquet_context',1,reader.parquet_loads)
        for sig in result['signature']:
            want=snapshot['proof']['month'] if sig['utc_date'] is None else next(r for r in snapshot['proof']['daily'] if r['utc_date']==sig['utc_date'])
            for field in ('event_records','active_users','purchase_events','buyers'):checks.equal('T13_'+str(sig['utc_date'])+'_'+field,want[field],sig[field])
        for cov in result['coverage']:
            if cov['level']=='day':
                want=next(r for r in snapshot['proof']['daily'] if r['utc_date']==cov['utc_date'])
                checks.equal('T13_behavior_'+cov['utc_date']+'_'+cov['event_type'],want[cov['event_type']+'_events'],cov['event_records'])
                if cov['event_type']=='purchase':checks.equal('T13_buyers_'+cov['utc_date'],want['buyers'],cov['behavior_users'])
            else:
                checks.equal('T11_behavior_'+cov['event_type'],entry['summary']['behaviors'].get(cov['event_type'],0),cov['event_records'])
        for path,digest in protected.items():checks.equal('immutable_'+str(Path(path).relative_to(ROOT) if Path(path).is_absolute() else path),digest,sha256(ROOT/path))
        preflight=json.loads((ROOT/'.local/t21/preflight.json').read_text())
        checks.equal('prior_output_metadata_unchanged',True,all((ROOT/p).exists() and [(ROOT/p).stat().st_size,(ROOT/p).stat().st_mtime_ns]==st for p,st in preflight['protected_stat'].items()))
        result.update(config=cfg,protected_hashes=protected,selected_fact_inventory=entry['inventory'],observed_event_range=scope['observed_event_range'])
        return result
    finally:reader.close()


class Budget:
    def __init__(self,path):
        self.config=json.loads(Path(path).read_text());self.peak=0;self.minimum=shutil.disk_usage(ROOT).free;self.samples=0
        require(set(self.config)=={'max_new_bytes','minimum_free_bytes'} and 0<self.config['max_new_bytes']<=10*1024**3 and self.config['minimum_free_bytes']>=150*1024**3,'invalid T2.1 budget')
    def check(self):
        used=directory_bytes(ROOT/'.local/t21');free=shutil.disk_usage(ROOT).free
        self.peak=max(self.peak,used);self.minimum=min(self.minimum,free);self.samples+=1
        require(used<=self.config['max_new_bytes'] and free>=self.config['minimum_free_bytes'],'T2.1 resource budget exceeded')
    def summary(self):return dict(self.config,sampled_peak_new_bytes=self.peak,minimum_free_observed_bytes=self.minimum,samples=self.samples,sampling='at most 2 seconds while Spark runs',peak_memory='not_measured')


def worker(args):
    from pyspark.sql import SparkSession
    stage=Path(args.run_dir).resolve()/'staging';spark=None;result={'status':'failed'};started=time.monotonic()
    try:
        spark=SparkSession.builder.appName('T2.1-coverage-and-funnel').getOrCreate();spark.sparkContext.setLogLevel('WARN')
        require(spark.sparkContext.master=='local[4]' and spark.sparkContext.getConf().get('spark.driver.memory')=='4g'
                and spark.conf.get('spark.sql.session.timeZone')=='UTC' and spark.conf.get('spark.sql.catalogImplementation')=='in-memory','runtime mismatch')
        if args.stage=='synthetic':
            sys.path.insert(0,str(ROOT/'tests'))
            from test_funnel import run_tests
            result=run_tests(spark,stage)
        else:
            gate=json.loads(Path(args.synthetic_gate).read_text())
            require(gate['status']=='passed' and gate['spark_stopped'] and gate['stage']=='synthetic' and gate['code_sha256']==code_hashes(),'synthetic gate stale or failed')
            result=real_analysis(spark,args.config,stage/'analysis')
        result.update(status='passed',versions=dict(python=sys.version.split()[0],spark=spark.version,java=spark.sparkContext._jvm.java.lang.System.getProperty('java.version')))
    except BaseException as exc:
        result.update(status='failed',error=type(exc).__name__+': '+str(exc));raise
    finally:
        if spark:spark.catalog.clearCache();spark.stop();result['spark_stopped']=True
        result.update(stage=args.stage,elapsed_seconds=round(time.monotonic()-started,3),code_sha256=code_hashes())
        (stage/'validation.json').write_text(json.dumps(ready(result),indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['synthetic','real'],required=True); parser.add_argument('--runtime-config',required=True)
    parser.add_argument('--config'); parser.add_argument('--synthetic-gate'); parser.add_argument('--run-dir',required=True)
    parser.add_argument('--budget',required=True); parser.add_argument('--worker',action='store_true'); args=parser.parse_args()
    if args.worker:return worker(args)
    require(Path(sys.prefix)==ROOT/'.venv' and sys.version_info[:2]==(3,11),'project Python required')
    runtime=load_config(args.runtime_config,ROOT)
    import pyspark
    spark_home=Path(pyspark.__file__).resolve().parent
    require(pyspark.__version__=='3.5.8' and spark_home.is_relative_to(ROOT/'.venv'),'project PySpark required')
    require(args.stage!='real' or (args.config and args.synthetic_gate),'real config and synthetic gate required')
    run=Path(args.run_dir).resolve(); require(run.is_relative_to(ROOT/'.local/t21'),'output must be in .local/t21')
    budget=Budget(args.budget);budget.check(); run.mkdir(parents=True,exist_ok=False)
    stage=run/'staging';stage.mkdir();temp=run/'temp';temp.mkdir();conf=temp/'spark-conf';conf.mkdir()
    props=conf/'spark-defaults.conf';props.write_text('# isolated project settings\n')
    env=os.environ.copy()
    for key in ('PYTHONPATH','PYTHONHOME','SPARK_SUBMIT_OPTS','JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED'):env.pop(key,None)
    env.update(JAVA_HOME=str(runtime.java_home),SPARK_HOME=str(spark_home),SPARK_CONF_DIR=str(conf),TMPDIR=str(temp),SQLITE_TMPDIR=str(temp),
               SPARK_LOCAL_DIRS=str(temp),SPARK_LOCAL_IP='127.0.0.1',PYTHONNOUSERSITE='1',TZ='UTC',
               PYSPARK_PYTHON=str(runtime.python_executable),PYSPARK_DRIVER_PYTHON=str(runtime.python_executable))
    env['PATH']=os.pathsep.join([str(runtime.python_executable.parent),str(runtime.java_home/'bin'),env.get('PATH','')])
    command=[str(ROOT/'.venv/bin/spark-submit'),'--master','local[4]','--driver-memory','4g','--properties-file',str(props),
             '--driver-java-options','-Djava.io.tmpdir="'+str(temp)+'"']
    for key,value in {'spark.sql.shuffle.partitions':'32','spark.sql.session.timeZone':'UTC','spark.local.dir':str(temp),
                      'spark.sql.warehouse.dir':(temp/'warehouse').as_uri(),'spark.pyspark.python':str(runtime.python_executable),
                      'spark.pyspark.driver.python':str(runtime.python_executable),'spark.driver.host':'127.0.0.1','spark.driver.bindAddress':'127.0.0.1',
                      'spark.ui.enabled':'false','spark.sql.catalogImplementation':'in-memory','spark.sql.legacy.timeParserPolicy':'CORRECTED','spark.sql.ansi.enabled':'true'}.items():
        command+=['--conf',key+'='+value]
    command+=[str(Path(__file__).resolve()),*sys.argv[1:],'--worker']
    started=time.monotonic();receipt={'status':'running','started_at':datetime.now(timezone.utc).isoformat()};process=None
    try:
        with (run/'spark.log').open('x') as log:
            process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            while True:
                budget.check()
                try:code=process.wait(timeout=2);break
                except subprocess.TimeoutExpired:pass
        require(code==0,'Spark funnel checks failed; retained local logs')
        validation=json.loads((stage/'validation.json').read_text())
        require(validation['status']=='passed' and validation['spark_stopped'],'validation and normal stop required')
        budget.check();publish(stage,run);receipt['status']='passed'
    except BaseException as exc:
        if process and process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
        receipt.update(status='failed',error=str(exc));raise
    finally:
        receipt.update(elapsed_seconds=round(time.monotonic()-started,3),resources=budget.summary())
        (run/'launch.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)


if __name__=='__main__':main()
