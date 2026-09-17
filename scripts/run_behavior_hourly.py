"""One Spark session, one controlled fact context, at most 24 report rows."""
import argparse
from datetime import datetime,timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from etl.fact_registry import FactReader,load_registry,require
from etl.resource_budget import directory_bytes
from scripts.project_config import load_config
from scripts.run_metrics import Checks,bounded,ready,publish,DATES,SCOPE,SERIES
from scripts.metric_snapshot import digest
from scripts.behavior_analysis import complete_hours,write_csv,write_json,HOUR_FIELDS

CODE=['scripts/run_behavior_hourly.py','sql/metrics/behavior_hourly.sql','scripts/behavior_analysis.py','tests/test_behavior.py','etl/fact_registry.py','etl/date_quality.py','scripts/project_config.py','reports/behavior_analysis_contract.md']
def code_hashes():return {p:digest(ROOT/p) for p in CODE}


class Budget:
    def __init__(self,path):
        self.config=json.loads(Path(path).read_text());self.peak=0;self.minimum=shutil.disk_usage(ROOT).free;self.samples=0
        require(set(self.config)=={'max_new_bytes','minimum_free_bytes'} and 0<self.config['max_new_bytes']<=2*1024**3 and self.config['minimum_free_bytes']>=150*1024**3,'invalid T2.2 budget')
    def check(self):
        used=directory_bytes(ROOT/'.local/t22');free=shutil.disk_usage(ROOT).free
        self.peak=max(self.peak,used);self.minimum=min(self.minimum,free);self.samples+=1
        require(used<=self.config['max_new_bytes'] and free>=self.config['minimum_free_bytes'],'T2.2 resource budget exceeded')
    def summary(self):return dict(self.config,sampled_peak_new_bytes=self.peak,minimum_free_observed_bytes=self.minimum,samples=self.samples,peak_memory='not_measured')


def worker(args):
    from pyspark.sql import SparkSession
    stage=Path(args.run_dir).resolve()/'staging';spark=None;result={'status':'failed'};started=time.monotonic();reader=None
    try:
        gate=json.loads(Path(args.synthetic_gate).read_text());require(gate['status']=='passed' and gate['code_sha256']==code_hashes(),'unit gate stale or failed')
        prepared=json.loads(Path(args.config).read_text());require(prepared['status']=='passed','small metrics preparation required')
        for path,sha in prepared['protected_hashes'].items():require(digest(path)==sha,'protected input changed before hourly read')
        spark=SparkSession.builder.appName('T2.2-UTC-hour-purchase-aggregate').getOrCreate();spark.sparkContext.setLogLevel('WARN')
        require(spark.sparkContext.master=='local[4]' and spark.sparkContext.getConf().get('spark.driver.memory')=='4g' and spark.conf.get('spark.sql.session.timeZone')=='UTC' and spark.conf.get('spark.sql.catalogImplementation')=='in-memory','runtime mismatch')
        query=(ROOT/'sql/metrics/behavior_hourly.sql').read_text();checks=Checks()
        synthetic=[('purchase','1',datetime(2019,10,1,1,tzinfo=timezone.utc),Decimal('1.25'),True),
                   ('purchase','1',datetime(2019,10,1,1,tzinfo=timezone.utc),Decimal('1.25'),True),
                   ('purchase','2',datetime(2019,10,2,1,tzinfo=timezone.utc),Decimal('3.75'),True),
                   ('purchase','1',datetime(2019,10,1,23,tzinfo=timezone.utc),Decimal('0'),True),
                   ('view','3',datetime(2019,10,1,5,tzinfo=timezone.utc),Decimal('99'),False)]
        spark.createDataFrame(synthetic,'event_type string,user_id string,event_timestamp_utc timestamp,price_decimal decimal(18,2),amount_eligible boolean').createOrReplaceTempView('behavior_fact')
        expected=[dict(utc_hour=1,purchase_events=3,purchase_users=2,purchase_amount=Decimal('6.25')),dict(utc_hour=23,purchase_events=1,purchase_users=1,purchase_amount=Decimal('0.00'))]
        checks.equal('synthetic_SQL_literal',expected,bounded(spark.sql(query),24))
        cfg=json.loads((ROOT/prepared['config']['metrics_config']).read_text())
        from scripts.run_metrics import validate_config
        validate_config(cfg);registry=load_registry(ROOT,cfg['registry_path']);entries=[r for r in registry['batches'] if r['descriptor']['series_id']==SERIES]
        require(len(entries)==1 and entries[0]['descriptor']['run_id']=='month-v101-01' and entries[0]['descriptor']['scope_id']==SCOPE,'canonical fact required')
        reader=FactReader(spark,ROOT,cfg['registry_path'],SERIES)
        reader.read(DATES,'count',expected_scopes=[SCOPE]);fact=reader.read(DATES,'amount',expected_scopes=[SCOPE])
        fact.createOrReplaceTempView('behavior_fact');raw=bounded(spark.sql(query),24);hours=complete_hours(raw)
        checks.equal('24_UTC_buckets',list(range(24)),[r['utc_hour'] for r in hours]);checks.equal('one_fact_load',1,reader.parquet_loads)
        checks.equal('monthly_purchase_events',prepared['month']['purchase_events'],sum(r['purchase_events'] for r in hours))
        checks.equal('monthly_purchase_amount',prepared['month']['purchase_amount'],format(sum((r['purchase_amount'] for r in hours),Decimal('0')),'.2f'))
        checks.equal('hour_share_sum',True,abs(sum(r['purchase_events_share'] for r in hours)-1)<1e-12)
        for path,sha in prepared['protected_hashes'].items():checks.equal('immutable_'+path,sha,digest(path))
        write_csv(stage/'hourly_purchase.csv',hours,HOUR_FIELDS)
        result=dict(status='passed',checks=checks.rows,hours=hours,source_run='month-v101-01',scope_id=SCOPE,record_read_checks=reader.read_checks,
                    versions=dict(python=sys.version.split()[0],spark=spark.version,java=spark.sparkContext._jvm.java.lang.System.getProperty('java.version')),
                    fact_loads=reader.parquet_loads,synthetic_events=len(synthetic),code_sha256=code_hashes())
    except BaseException as exc:result.update(status='failed',error=type(exc).__name__+': '+str(exc));raise
    finally:
        if reader:reader.close()
        if spark:spark.catalog.clearCache();spark.stop();result['spark_stopped']=True
        result.update(elapsed_seconds=round(time.monotonic()-started,3));write_json(stage/'validation.json',result)


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
    require(args.config and args.synthetic_gate,'prepare receipt and unit gate required')
    run=Path(args.run_dir).resolve(); require(run.is_relative_to(ROOT/'.local/t22'),'output must be in .local/t22')
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
        require(code==0,'Spark hourly checks failed; retained local logs')
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
