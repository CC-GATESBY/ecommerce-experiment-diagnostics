"""One category-only monthly distinct query to close the T2.2 reporting gap."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
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
from etl.fact_registry import FactReader,load_registry,require
from etl.resource_budget import directory_bytes
from scripts.project_config import load_config
from scripts.run_metrics import Checks,ready,publish,DATES,SCOPE,SERIES,validate_config
from scripts.metric_snapshot import digest
from scripts.validate_analysis_scope import canonical_snapshot,validate_scope
from scripts.behavior_analysis import read_csv,write_csv,write_json,CATEGORY_FIELDS

STATUS='measured_from_fact_monthly_distinct'
CHANGED_COLUMNS={'users','buyers','monthly_distinct_status'}
CODE=['scripts/close_behavior_categories.py','tests/test_category_closeout.py','sql/metrics/category_month_distinct.sql',
      'sql/metrics/event_dimensions.sql','etl/fact_registry.py','etl/date_quality.py','scripts/project_config.py']
def code_hashes():return {p:digest(ROOT/p) for p in CODE}


def category_projection():
    """Reuse T1.3 expressions verbatim; no brand, price-band, or first-seen query."""
    frozen=(ROOT/'sql/metrics/event_dimensions.sql').read_text()
    start=frozen.index(' CASE WHEN NOT f.category_code_missing')
    end=frozen.index(' END AS category_label,',start)+len(' END AS category_label')
    return frozen[start:end]


def merge_monthly(old,monthly):
    require(len({r['category_key'] for r in monthly})==len(monthly),'duplicate monthly bucket')
    by_key={r['category_key']:r for r in monthly}
    require(len({r['category_key'] for r in old})==len(old) and set(by_key)=={r['category_key'] for r in old},'monthly buckets differ')
    out=[]
    for row in old:
        actual=by_key[row['category_key']]
        require(row['category_label']==actual['category_label'],'category label drift')
        require(int(row['purchase_events'])==actual['purchase_events'] and Decimal(row['purchase_amount'])==Decimal(str(actual['purchase_amount'])),'amount or purchase drift')
        require(type(actual['users']) is int and type(actual['buyers']) is int and 0<=actual['buyers']<=actual['users'],'invalid distinct counts')
        require(actual['users']<=int(row['user_days']) and actual['buyers']<=int(row['buyer_user_days']),'monthly distinct exceeds user-days')
        out.append(dict(row,users=actual['users'],buyers=actual['buyers'],monthly_distinct_status=STATUS))
    return out


def reconcile(monthly,expected,scope):
    checks=Checks()
    checks.equal('bucket_keys',sorted(expected),sorted(r['category_key'] for r in monthly))
    for row in monthly:
        checks.equal('scope_'+row['category_key'],scope,row['scope_id'])
        for field in ('event_records','purchase_events','purchase_amount'):
            checks.equal(row['category_key']+'_'+field,expected[row['category_key']][field],row[field])
    return checks.rows


def prepare(config,stage):
    cfg=json.loads(Path(config).read_text())
    require(cfg['version']=='rees46-behavior-report-v1' and cfg['analysis_scope']=='config/analysis_scope.yaml','analysis config mismatch')
    for key in ('scope_receipt','metrics_config','metrics_run','funnel_run'):
        require((ROOT/cfg[key]).resolve().is_relative_to(ROOT) and not any(c in cfg[key] for c in '*?['),'explicit project-local path required')
    require(Path(cfg['metrics_run']).name=='metrics-month-01' and Path(cfg['funnel_run']).name=='funnel-month-01','canonical snapshot required')
    scope=yaml.safe_load((ROOT/cfg['analysis_scope']).read_text());validate_scope(scope)
    oldprep=json.loads((ROOT/'.local/t22/behavior-month-01/prepare.json').read_text())
    require(oldprep['status']=='passed' and cfg==oldprep['config'],'prior report binding mismatch')
    for path,sha in oldprep['protected_hashes'].items():require(digest(path)==sha,'historical input changed')
    snapshot=canonical_snapshot(ROOT,scope,cfg['metrics_run'])
    require(snapshot['proof']['code_sha256']['sql/metrics/event_dimensions.sql']==digest(ROOT/'sql/metrics/event_dimensions.sql'),'frozen T1.3 expression changed')
    import duckdb
    connection=duckdb.connect(':memory:')
    cursor=connection.execute("SELECT * FROM read_parquet(?) WHERE dim_name='category_l1' LIMIT 3969",[snapshot['files']['agg_daily_dim']])
    columns=[c[0] for c in cursor.description];daily=[dict(zip(columns,r)) for r in cursor.fetchall()];connection.close()
    require(0<len(daily)<=3968,'daily category bound exceeded')
    expected={};seen=set()
    for row in daily:
        require(row['scope_id']==SCOPE and row['source_run']=='month-v101-01' and str(row['utc_date']) in DATES and row['count_allowed'] and row['amount_allowed'],'category daily identity or quality mismatch')
        key=row['dim_value_key'];pk=(str(row['utc_date']),key);require(pk not in seen,'duplicate category day');seen.add(pk)
        group=expected.setdefault(key,dict(event_records=0,purchase_events=0,purchase_amount=Decimal('0.00'),user_days=0,buyer_user_days=0,dates=[]))
        for field in ('event_records','purchase_events','purchase_amount'):group[field]+=row[field]
        group['user_days']+=row['users'];group['buyer_user_days']+=row['buyers'];group['dates'].append(str(row['utc_date']))
    old=read_csv(ROOT/'reports/category_concentration.csv')
    require(len(old)==14 and len(expected)==14 and set(expected)=={r['category_key'] for r in old},'expected 14 existing buckets')
    for row in old:
        group=expected[row['category_key']]
        require(int(row['user_days'])==group['user_days'] and int(row['buyer_user_days'])==group['buyer_user_days'],'daily user totals changed')
        require(int(row['purchase_events'])==group['purchase_events'] and Decimal(row['purchase_amount'])==group['purchase_amount'],'historical category amounts differ')
    protected={p:digest(ROOT/p) for p in subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines() if (ROOT/p).is_file()}
    metadata={}
    for folder in ('t11','t13','t14','t15','t21','t22'):
        for file in (ROOT/'.local'/folder).rglob('*'):
            if file.is_file():metadata[str(file.relative_to(ROOT))]=[file.stat().st_size,file.stat().st_mtime_ns]
    result=dict(config=cfg,expected=expected,old_categories=old,category_csv_sha256=digest(ROOT/'reports/category_concentration.csv'),
        month=snapshot['proof']['month'],protected_sha256=protected,protected_stat=metadata,
        scope=scope['analysis_scope_version'],fact_run='month-v101-01',daily_rows=len(daily),initial_free_bytes=shutil.disk_usage(ROOT).free)
    write_json(stage/'preflight.json',result)
    return result


def unchanged(prepared):
    return all(digest(ROOT/p)==sha for p,sha in prepared['protected_sha256'].items()) and all(
        (ROOT/p).is_file() and [(ROOT/p).stat().st_size,(ROOT/p).stat().st_mtime_ns]==stat for p,stat in prepared['protected_stat'].items())


class Budget:
    def __init__(self,path):
        self.config=json.loads(Path(path).read_text());self.peak=0;self.minimum=shutil.disk_usage(ROOT).free;self.samples=0
        require(set(self.config)=={'max_new_bytes','minimum_free_bytes'} and 0<self.config['max_new_bytes']<=512*1024**2 and self.config['minimum_free_bytes']>=150*1024**3,'invalid closeout budget')
    def check(self):
        used=directory_bytes(ROOT/'.local/t22_closeout')+4*1024**2
        free=shutil.disk_usage(ROOT).free;self.peak=max(self.peak,used);self.minimum=min(self.minimum,free);self.samples+=1
        require(used<=self.config['max_new_bytes'] and free>=self.config['minimum_free_bytes'],'closeout budget exceeded')
    def summary(self):return dict(self.config,sampled_peak_new_bytes_with_4MiB_shared_reserve=self.peak,minimum_free_observed_bytes=self.minimum,samples=self.samples,peak_memory='not_measured')


def worker(args):
    from pyspark.sql import SparkSession,types as T
    stage=Path(args.run_dir).resolve()/'staging';spark=None;reader=None;checks=Checks();started=time.monotonic();result={'status':'failed'}
    try:
        gate=json.loads(Path(args.synthetic_gate).read_text());require(gate['status']=='passed' and gate['code_sha256']==code_hashes(),'unit gate stale or failed')
        prepared=prepare(args.config,stage)
        spark=SparkSession.builder.appName('T2.2-category-month-distinct-closeout').getOrCreate();spark.sparkContext.setLogLevel('WARN')
        require(spark.sparkContext.master=='local[4]' and spark.sparkContext.getConf().get('spark.driver.memory')=='4g' and spark.conf.get('spark.sql.session.timeZone')=='UTC' and spark.conf.get('spark.sql.catalogImplementation')=='in-memory','runtime mismatch')
        query=(ROOT/'sql/metrics/category_month_distinct.sql').read_text().replace('__CATEGORY_PROJECTION__',category_projection())
        from tests.test_category_closeout import run_synthetic
        synthetic=run_synthetic(spark,query,checks)
        write_json(stage/'synthetic.json',dict(status='passed',checks=checks.rows,fixture=synthetic,code_sha256=code_hashes()))
        cfg=json.loads((ROOT/prepared['config']['metrics_config']).read_text());validate_config(cfg)
        entries=[e for e in load_registry(ROOT,cfg['registry_path'])['batches'] if e['descriptor']['series_id']==SERIES]
        require(len(entries)==1 and entries[0]['descriptor']['run_id']=='month-v101-01' and entries[0]['descriptor']['scope_id']==SCOPE,'canonical fact required')
        reader=FactReader(spark,ROOT,cfg['registry_path'],SERIES)
        reader.read(DATES,'count',expected_scopes=[SCOPE]);fact=reader.read(DATES,'amount',expected_scopes=[SCOPE]);fact.createOrReplaceTempView('category_fact')
        aggregate=spark.sql(query)
        checks.equal('decimal_type','decimal(38,2)',aggregate.schema['purchase_amount'].dataType.simpleString())
        # Stream only bounded category aggregates, never user IDs or fact rows.
        monthly=[]
        for row in aggregate.toLocalIterator():
            require(len(monthly)<14,'more than the 14 authorized categories; stop without truncation')
            monthly.append(row.asDict())
        result['monthly']=monthly
        checks.equal('14_buckets',14,len(monthly));checks.equal('physical_fact_loads',1,reader.parquet_loads)
        checks.rows.update(reconcile(monthly,prepared['expected'],SCOPE))
        updated=merge_monthly(prepared['old_categories'],monthly)
        for field in ('event_records','purchase_events','purchase_amount'):
            expected=prepared['month'][field];actual=sum((r[field] for r in monthly),Decimal('0.00') if field=='purchase_amount' else 0)
            checks.equal('month_'+field,Decimal(expected) if field=='purchase_amount' else expected,actual)
        checks.equal('unknown_retained',True,any(r['category_key']=='bucket:unknown' for r in monthly))
        comparison=[dict(category_key=r['category_key'],users=r['users'],user_days=prepared['expected'][r['category_key']]['user_days'],buyers=r['buyers'],buyer_user_days=prepared['expected'][r['category_key']]['buyer_user_days'],observed_dates=len(prepared['expected'][r['category_key']]['dates'])) for r in monthly]
        checks.equal('real_cross_day_nonadditivity_observed',True,any(r['observed_dates']>1 and r['users']<r['user_days'] and r['buyers']<r['buyer_user_days'] for r in comparison))
        for old,new in zip(prepared['old_categories'],updated):
            checks.equal('only_distinct_columns_changed_'+old['category_key'],{k:v for k,v in old.items() if k not in CHANGED_COLUMNS},{k:v for k,v in new.items() if k not in CHANGED_COLUMNS})
        checks.equal('all_old_inputs_unchanged',True,unchanged(prepared))
        write_csv(stage/'category_concentration.csv',updated,CATEGORY_FIELDS)
        result.update(status='passed',comparison=comparison,category_csv_before_sha256=prepared['category_csv_sha256'],category_csv_after_sha256=digest(stage/'category_concentration.csv'),
            source_run='month-v101-01',analysis_scope=prepared['scope'],scope_id=SCOPE,fact_loads=reader.parquet_loads,record_read_checks=reader.read_checks,
            versions=dict(python=sys.version.split()[0],spark=spark.version,java=spark.sparkContext._jvm.java.lang.System.getProperty('java.version')))
    except BaseException as exc:
        result.update(error=type(exc).__name__+': '+str(exc));raise
    finally:
        if reader:reader.close()
        if spark:spark.catalog.clearCache();spark.stop();result['spark_stopped']=True
        result.update(checks=checks.rows,elapsed_seconds=round(time.monotonic()-started,3),code_sha256=code_hashes())
        write_json(stage/'validation.json',result)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-config',required=True)
    parser.add_argument('--config'); parser.add_argument('--synthetic-gate'); parser.add_argument('--run-dir',required=True)
    parser.add_argument('--budget',required=True); parser.add_argument('--worker',action='store_true'); args=parser.parse_args()
    if args.worker:return worker(args)
    require(Path(sys.prefix)==ROOT/'.venv' and sys.version_info[:2]==(3,11),'project Python required')
    runtime=load_config(args.runtime_config,ROOT)
    import pyspark
    spark_home=Path(pyspark.__file__).resolve().parent
    require(pyspark.__version__=='3.5.8' and spark_home.is_relative_to(ROOT/'.venv'),'project PySpark required')
    require(args.config and args.synthetic_gate,'behavior config and unit gate required')
    run=Path(args.run_dir).resolve(); require(run.is_relative_to(ROOT/'.local/t22_closeout'),'output must be in .local/t22_closeout')
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
        require(code==0,'Spark category closeout checks failed; retained local logs')
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
