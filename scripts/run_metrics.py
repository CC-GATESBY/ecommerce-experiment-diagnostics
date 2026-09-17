"""T1.3 fixed-scope Spark SQL metrics and bounded verification."""
import argparse
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from etl.event_config import sha256
from etl.fact_registry import FactReader, inspect_batch, load_registry, require
from etl.resource_budget import directory_bytes
from scripts.project_config import load_config

VERSION='rees46-metrics-v1'
BRAND_VERSION='rees46-brand-oct01-07-top200-v1'
DATE_POLICY='rees46-date-quality-v1'
CONTRACT='rees46-events-v1.0.1'
SCOPE='rees46_2019_oct_user5_fedd938409b5f836_20260916_v1'
SERIES='rees46_fixed_users_20260916_v1'
DATES=[f'2019-10-{d:02d}' for d in range(1,32)]
TOP_K=200
ABS_TOL=1e-6
REL_TOL=1e-10
TABLES={'dim_user_first_seen':['scope_id','user_id'],
        'agg_user_daily':['scope_id','utc_date','user_id'],
        'agg_daily_metrics':['scope_id','utc_date'],
        'agg_daily_dim':['scope_id','utc_date','dim_name','dim_value_key']}
CODE=['scripts/run_metrics.py','tests/test_metrics.py','docs/metric_contract.md','etl/fact_registry.py','etl/date_quality.py',
      *['sql/metrics/'+n+'.sql' for n in ('first_seen','brand_mapping','event_dimensions','user_daily','daily_metrics','ratios','direct_daily','daily_dim')]]


def ready(value):
    if isinstance(value,Decimal):return format(value,'f')
    if isinstance(value,(date,datetime)):return value.isoformat()
    if isinstance(value,dict):return {k:ready(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [ready(v) for v in value]
    return value


def write_json(path,value):
    with Path(path).open('x') as stream:json.dump(ready(value),stream,indent=2,allow_nan=False);stream.write('\n')


def bounded(frame,limit):
    rows=frame.limit(limit+1).collect()
    require(len(rows)<=limit,'bounded aggregate exceeded; no truncation')
    return [r.asDict(recursive=True) for r in rows]


def sql(spark,name,top_k=TOP_K):
    return spark.sql((ROOT/'sql/metrics'/f'{name}.sql').read_text().replace('__TOP_K__',str(top_k)))


def code_hashes():return {p:sha256(ROOT/p) for p in CODE}


class Checks:
    def __init__(self):self.rows={}
    def equal(self,name,expected,actual):
        passed=expected==actual
        self.rows[name]=dict(expected=ready(expected),actual=ready(actual),**{'pass':passed})
        require(passed,name+': expected '+str(expected)+' actual '+str(actual))


def controlled_input(reader,dates,scope,gates):
    fact=reader.read(dates,'count',expected_scopes=[scope])
    allowed=[d for d in dates if gates[d]['amount_allowed']]
    if allowed:reader.read(allowed,'amount',expected_scopes=[scope])
    return fact


def validate_config(cfg):
    require(set(cfg)=={'registry_path','source_run','scope_id','series_id','observation_dates','output_dates',
                      'metric_version','brand_version','brand_top_k','date_policy_version','contract_version'},'metrics config fields mismatch')
    require(cfg['registry_path'] and cfg['source_run']=='month-v101-01' and cfg['scope_id']==SCOPE and cfg['series_id']==SERIES
            and cfg['observation_dates']==DATES and cfg['metric_version']==VERSION and cfg['brand_version']==BRAND_VERSION
            and type(cfg['brand_top_k']) is int and cfg['brand_top_k']==TOP_K and cfg['date_policy_version']==DATE_POLICY
            and cfg['contract_version']==CONTRACT,'unauthorized scope, versions or brand mapping')
    require(isinstance(cfg['output_dates'],list) and cfg['output_dates'] and sorted(set(cfg['output_dates']))==cfg['output_dates']
            and set(cfg['output_dates'])<=set(DATES),'invalid output dates')
    return cfg


def build_metrics(spark,fact,gates,stage,identity,*,top_k=TOP_K,synthetic=False,output_dates=None):
    """Aggregate one complete observation scope; output filtering happens last."""
    from pyspark import StorageLevel
    from pyspark.sql import functions as F, types as T
    require((synthetic and top_k==2) or (not synthetic and top_k==TOP_K),'test TopK cannot enter real execution')
    dates=sorted(gates); output_dates=dates if output_dates is None else output_dates
    require(set(output_dates)<=set(dates),'output outside observation range')
    require(all(g['count_allowed'] and g['policy_version']==DATE_POLICY for g in gates.values()),'count gate failed')
    checks=Checks();caches=[];stage=Path(stage);stage.mkdir(parents=True,exist_ok=False)
    def view(frame,name,cache=False):
        if cache:frame=frame.persist(StorageLevel.MEMORY_AND_DISK);caches.append(frame)
        frame.createOrReplaceTempView(name);return frame
    def signature(frame):
        frame.createOrReplaceTempView('m_check_input')
        return ready(sorted(bounded(spark.sql("""SELECT CAST(event_date_utc AS STRING) d,COUNT(*) n,
          COUNT(DISTINCT user_id) u,COUNT(DISTINCT CASE WHEN event_type='purchase' THEN user_id END) b,
          COUNT_IF(event_type='view') v,COUNT_IF(event_type='cart') c,COUNT_IF(event_type='remove_from_cart') r,
          COUNT_IF(event_type='purchase') p,
          SUM(CASE WHEN amount_eligible THEN CAST(price_decimal AS DECIMAL(38,2)) ELSE CAST(0 AS DECIMAL(38,2)) END) a
          FROM m_check_input GROUP BY event_date_utc"""),31),key=lambda r:r['d']))
    def key_check(frame,name,suffix=""):
        keys=TABLES[name]; name+=suffix
        checks.equal(name+'_pk_unique',0,frame.groupBy(*keys).count().where('count>1').count())
        checks.equal(name+'_pk_not_null',0,frame.where(' OR '.join(k+' IS NULL' for k in keys)).count())
    try:
        view(fact,'m_fact')
        baseline=signature(fact);checks.equal('observed_dates',dates,[r['d'] for r in baseline])
        gate_rows=[(date.fromisoformat(d),g['count_allowed'],g['amount_allowed'],g['amount_status'],json.dumps(g['reason_codes'],sort_keys=True)) for d,g in sorted(gates.items())]
        view(spark.createDataFrame(gate_rows,'utc_date date,count_allowed boolean,amount_allowed boolean,amount_status string,reason_codes string'),'m_gates')
        first=view(sql(spark,'first_seen'),'m_first_seen',True)
        checks.equal('first_seen_join_conservation',baseline,signature(spark.sql('SELECT f.* FROM m_fact f LEFT JOIN m_first_seen s ON f.scope_id=s.scope_id AND f.user_id=s.user_id')))
        brand=view(sql(spark,'brand_mapping',top_k),'m_brand_map',True)
        mapping=bounded(brand.orderBy('brand_rank'),top_k)
        fingerprint=hashlib.sha256(json.dumps(mapping,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        write_json(stage/'brand_mapping.json',dict(version=BRAND_VERSION if not synthetic else 'synthetic-top2-v1',reference_start='2019-10-01',reference_end='2019-10-07',content_sha256=fingerprint,rows=mapping))
        brand.write.mode('errorifexists').parquet(str(stage/'brand_mapping'))
        brand_read=spark.read.parquet(str(stage/'brand_mapping'))
        checks.equal('brand_mapping_readback',True,mapping==bounded(brand_read.orderBy('brand_rank'),top_k))
        checks.equal('brand_mapping_unique',0,brand.groupBy('brand').count().where('count>1').count())
        events=view(sql(spark,'event_dimensions'),'m_events')
        checks.equal('brand_and_first_seen_join_conservation',baseline,signature(events))
        checks.equal('first_seen_join_complete',0,events.where('first_seen_date_utc IS NULL').count())
        user=view(sql(spark,'user_daily'),'m_user_daily',True)
        daily_base=view(sql(spark,'daily_metrics'),'m_daily_base')
        daily=sql(spark,'ratios')
        direct=view(sql(spark,'direct_daily'),'m_daily_base')
        direct_ratios=sql(spark,'ratios')
        daily_rows=bounded(daily.orderBy('utc_date'),31)
        checks.equal('user_daily_vs_independent_fact_sql',daily_rows,bounded(direct_ratios.orderBy('utc_date'),31))
        max_error=0.0
        for row in daily_rows:
            for field in ('buyer_rate','amount_per_buyer','first_seen_ratio'):
                require(row[field] is None or math.isfinite(row[field]),'nonfinite ratio')
            if row['active_users']>0 and row['buyers']>0 and row['amount_allowed']:
                expected=float(row['purchase_amount']);actual=row['active_users']*row['buyer_rate']*row['amount_per_buyer']
                max_error=max(max_error,abs(expected-actual))
                checks.equal('identity_'+str(row['utc_date']),True,math.isclose(expected,actual,abs_tol=ABS_TOL,rel_tol=REL_TOL))
        month=bounded(spark.sql("""SELECT COUNT(*) event_records,COUNT(DISTINCT user_id) active_users,
          COUNT(DISTINCT CASE WHEN event_type='purchase' THEN user_id END) buyers,
          COUNT_IF(event_type='purchase') purchase_events,
          SUM(CASE WHEN amount_eligible THEN CAST(price_decimal AS DECIMAL(38,2)) ELSE CAST(0 AS DECIMAL(38,2)) END) observed_purchase_amount,
          COUNT(DISTINCT CASE WHEN NOT session_missing THEN NAMED_STRUCT('u',user_id,'s',user_session) END) sessions
          FROM m_fact"""),1)[0]
        month['purchase_amount']=month.pop('observed_purchase_amount') if all(g['amount_allowed'] for g in gates.values()) else None
        checks.equal('first_seen_population',month['active_users'],first.count())
        checks.equal('first_seen_daily_sum',month['active_users'],sum(r['first_seen_users'] for r in daily_rows))
        checks.equal('event_conservation_user_daily',month['event_records'],sum(r['event_records'] for r in daily_rows))
        dims=sql(spark,'daily_dim');view(dims,'m_dim')
        totals=bounded(spark.sql("""SELECT utc_date,dim_name,SUM(event_records) event_records,SUM(purchase_events) purchase_events,
          SUM(purchase_amount) purchase_amount,SUM(users) users,SUM(buyers) buyers FROM m_dim GROUP BY utc_date,dim_name"""),124)
        by_day={r['utc_date']:r for r in daily_rows}
        checks.equal('dimension_date_groups',4*len(dates),len(totals))
        for r in totals:
            wanted=by_day[r['utc_date']]; cols=['event_records','purchase_events','purchase_amount']
            if r['dim_name']=='is_first_seen_day':cols+=['users','buyers']
            checks.equal('dimension_'+str(r['utc_date'])+'_'+r['dim_name'],
                [wanted['active_users' if c=='users' else c] for c in cols],[r[c] for c in cols])
        unknown=bounded(spark.sql("""SELECT dim_name,SUM(event_records) event_records,SUM(purchase_events) purchase_events,
          CASE WHEN MIN(CAST(amount_allowed AS INT))=1 THEN SUM(purchase_amount) END purchase_amount
          FROM m_dim WHERE dim_value_key='bucket:unknown' GROUP BY dim_name ORDER BY dim_name"""),4)
        lineage=dict(metric_version=VERSION,contract_version=CONTRACT,date_policy_version=DATE_POLICY,
            brand_mapping_version=BRAND_VERSION if not synthetic else 'synthetic-top2-v1',brand_mapping_sha256=fingerprint,
            source_id=identity['source_id'],source_run=identity['run_id'],input_sha256=identity['input_sha256'],
            observation_start_utc='2019-10-01',observation_end_exclusive_utc='2019-11-01')
        frames=dict(dim_user_first_seen=first,agg_user_daily=user,agg_daily_metrics=daily,agg_daily_dim=dims)
        output={}
        for name,frame in frames.items():
            if name!='dim_user_first_seen':frame=frame.where(F.col('utc_date').cast('string').isin(output_dates))
            for k,v in lineage.items():frame=frame.withColumn(k,F.lit(v))
            key_check(frame,name);rows=frame.count()
            if 'purchase_amount' in frame.columns:
                checks.equal(name+'_decimal_type','decimal(38,2)',frame.schema['purchase_amount'].dataType.simpleString())
                checks.equal(name+'_allowed_amount_not_null',0,frame.where('amount_allowed AND purchase_amount IS NULL').count())
                checks.equal(name+'_blocked_amount_null',0,frame.where('NOT amount_allowed AND purchase_amount IS NOT NULL').count())
            frame.write.mode('errorifexists').parquet(str(stage/name))
            restored=spark.read.parquet(str(stage/name))
            checks.equal(name+'_schema',[(f.name,f.dataType.simpleString()) for f in frame.schema],[(f.name,f.dataType.simpleString()) for f in restored.schema])
            checks.equal(name+'_readback_rows',rows,restored.count());key_check(restored,name,'_readback')
            checks.equal(name+'_expected_minus_readback',0,frame.exceptAll(restored).count())
            checks.equal(name+'_readback_minus_expected',0,restored.exceptAll(frame).count())
            output[name]=dict(rows=rows,primary_key=TABLES[name],schema=restored.schema.jsonValue())
            print(json.dumps(dict(phase='metrics_table_verified',table=name,rows=rows)),flush=True)
        result=dict(checks=checks.rows,tables=output,month=month,daily=daily_rows,unknown_dimensions=unknown,
                    brand_mapping=dict(version=lineage['brand_mapping_version'],count=len(mapping),sha256=fingerprint),
                    ratio_check=dict(type='double',abs_tol=ABS_TOL,rel_tol=REL_TOL,max_absolute_error=max_error),lineage=lineage)
        write_json(stage/'checks.json',result)
        return result
    finally:
        for frame in reversed(caches):frame.unpersist(blocking=True)


def real_analysis(spark,config_path,stage):
    cfg=validate_config(json.loads(Path(config_path).read_text()))
    entries=load_registry(ROOT,cfg['registry_path'])['batches']
    require(len(entries)==1,'exactly one canonical batch required');entry=entries[0];d=entry['descriptor']
    require(d['run_id']==cfg['source_run'] and d['scope_id']==cfg['scope_id'] and d['series_id']==cfg['series_id'],'registered identity mismatch')
    require(inspect_batch(ROOT,d)==entry,'registered evidence changed')
    paths=[ROOT/p for p in entry['evidence']]+[ROOT/x['path'] for x in entry['inventory']]
    paths += [ROOT/cfg['registry_path'],ROOT/'reports/data_quality_daily.csv',ROOT/'docs/event_parsing_contract.md',ROOT/'docs/date_quality_policy.md']
    before={str(p):sha256(p) for p in paths}
    checks=Checks()
    with FactReader(spark,ROOT,cfg['registry_path'],cfg['series_id']) as reader:
        fact=controlled_input(reader,cfg['observation_dates'],cfg['scope_id'],entry['gates'])
        result=build_metrics(spark,fact,entry['gates'],stage/'metrics',d,output_dates=cfg['output_dates'])
        checks.equal('canonical_parquet_loads',1,reader.parquet_loads)
        for k,w in dict(event_records=2114081,active_users=151121,buyers=17121,purchase_events=37019,purchase_amount=Decimal('11598630.22'),sessions=460550).items():
            checks.equal('month_'+k,w,result['month'][k])
        for row in result['daily']:
            day=str(row['utc_date']);old=entry['daily'][day]
            for key,oldkey in dict(event_records='record_count',active_users='users',buyers='buyers',purchase_events='purchase_events',purchase_amount='purchase_amount',amount_status='amount_status').items():
                expected=Decimal(old[oldkey]) if key=='purchase_amount' else old[oldkey]
                checks.equal('historical_'+day+'_'+key,expected,row[key])
            checks.equal('historical_behaviors_'+day,[old['behaviors'].get(b,0) for b in ('view','cart','remove_from_cart')],
                         [row[k] for k in ('view_events','cart_events','remove_from_cart_events')])
        checks.equal('input_still_readable',2114081,reader.read(DATES,'count',expected_scopes=[SCOPE]).count())
    checks.equal('protected_input_sha256_unchanged',True,before=={str(p):sha256(p) for p in paths})
    result['checks'].update(checks.rows);result.update(config=cfg,protected_hashes=before)
    # Only date aggregates and verification summaries are eligible for publication.
    from scripts.run_quality import write_csv
    write_csv(stage/'daily_metrics_preview.csv',[ready(r) for r in result['daily']],result['lineage'])
    write_csv(stage/'metric_checks.csv',[dict(check=k,**v) for k,v in result['checks'].items()],dict(metric_version=VERSION))
    return result


class Budget:
    def __init__(self, path):
        self.config = json.loads(Path(path).read_text()); self.peak=0; self.minimum=shutil.disk_usage(ROOT).free; self.samples=0
        require(set(self.config)=={'initial_bytes','max_new_bytes','minimum_free_bytes'} and 0 < self.config['max_new_bytes'] <= 10*1024**3
                and self.config['minimum_free_bytes'] >= 150*1024**3, 'invalid T1.3 budget')
    def check(self):
        total = sum(directory_bytes(ROOT/'.local'/name) for name in ('t11','t13'))
        used = max(0,total-self.config['initial_bytes']); free=shutil.disk_usage(ROOT).free
        self.peak=max(self.peak,used); self.minimum=min(self.minimum,free); self.samples+=1
        require(used<=self.config['max_new_bytes'] and free>=self.config['minimum_free_bytes'], 'T1.3 resource budget exceeded')
    def summary(self):
        return dict(self.config,sampled_peak_new_bytes=self.peak,minimum_free_observed_bytes=self.minimum,samples=self.samples,sampling='at most 2 seconds while Spark runs',peak_memory='not_measured')


def worker(args):
    from pyspark.sql import SparkSession
    stage=Path(args.run_dir).resolve()/'staging'; spark=None; result={'status':'failed'}; started=time.monotonic()
    try:
        spark=SparkSession.builder.appName('T1.3-unified-metrics').getOrCreate(); spark.sparkContext.setLogLevel('WARN')
        require(spark.sparkContext.master=='local[4]' and spark.sparkContext.getConf().get('spark.driver.memory')=='4g'
                and spark.conf.get('spark.sql.session.timeZone')=='UTC' and spark.conf.get('spark.sql.catalogImplementation')=='in-memory', 'runtime mismatch')
        if args.stage=='synthetic':
            sys.path.insert(0,str(ROOT/'tests'))
            from test_metrics import run_tests
            result=run_tests(spark,ROOT,Path(args.run_dir).resolve())
        else:
            gate=json.loads(Path(args.synthetic_gate).read_text())
            require(gate['status']=='passed' and gate['spark_stopped'] and gate['stage']=='synthetic' and gate['code_sha256']==code_hashes(), 'synthetic gate stale or failed')
            result=real_analysis(spark,args.config,stage)
        result.update(status='passed',versions=dict(python=sys.version.split()[0],spark=spark.version,java=spark.sparkContext._jvm.java.lang.System.getProperty('java.version')))
    except BaseException as exc:
        result.update(status='failed',error=type(exc).__name__+': '+str(exc)); raise
    finally:
        if spark:
            spark.catalog.clearCache(); spark.stop(); result['spark_stopped']=True
        result.update(stage=args.stage,elapsed_seconds=round(time.monotonic()-started,3),code_sha256=code_hashes())
        (stage/'validation.json').write_text(json.dumps(ready(result),indent=2)+'\n')


def publish(stage,run):
    validation=json.loads((stage/'validation.json').read_text())
    require(validation.get('status')=='passed' and validation.get('spark_stopped') is True,'partial run cannot publish')
    require(not (run/'complete').exists(),'completed output cannot be replaced')
    stage.rename(run/'complete')


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
    run=Path(args.run_dir).resolve(); require(run.is_relative_to(ROOT/'.local/t13'),'output must be in .local/t13')
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
        require(code==0,'Spark metrics checks failed; retained local logs')
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
