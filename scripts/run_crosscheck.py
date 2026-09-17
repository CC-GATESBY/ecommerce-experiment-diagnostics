"""Run bounded T1.4 synthetic Spark work, stop Spark, then check with DuckDB."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from crosscheck_duckdb import Budget,ready,save,code_hashes
from scripts.metric_snapshot import require
from scripts.project_config import load_config


def worker(run):
    from pyspark.sql import SparkSession
    from test_idempotency import spark_stage,finish_after_spark
    spark=None;result={'status':'failed'};started=time.monotonic()
    try:
        spark=SparkSession.builder.appName('T1.4-synthetic-snapshot-tests').getOrCreate();spark.sparkContext.setLogLevel('WARN')
        require(spark.sparkContext.master=='local[4]' and spark.sparkContext.getConf().get('spark.driver.memory')=='4g'
                and spark.conf.get('spark.sql.session.timeZone')=='UTC','unexpected Spark settings')
        result=spark_stage(spark,run)
        spark.catalog.clearCache();spark.stop();spark=None;result['spark_stopped']=True
        print(json.dumps({'phase':'spark_stopped_before_duckdb'}),flush=True)
        result=finish_after_spark(run,result)
    except BaseException as exc:
        result.update(status='failed',error=type(exc).__name__+': '+str(exc));raise
    finally:
        if spark:spark.stop();result['spark_stopped']=True
        result.update(elapsed_seconds=round(time.monotonic()-started,3),code_sha256=code_hashes())
        save(run/'staging/validation.json',result)


def main():
    p=argparse.ArgumentParser();p.add_argument('--run-dir',required=True);p.add_argument('--runtime-config',required=True);p.add_argument('--budget',required=True);p.add_argument('--worker',action='store_true');a=p.parse_args()
    run=Path(a.run_dir).resolve();require(run.is_relative_to(ROOT/'.local/t14'),'run outside T1.4')
    if a.worker:return worker(run)
    runtime=load_config(a.runtime_config,ROOT);require(Path(sys.prefix)==ROOT/'.venv','project environment required')
    import pyspark
    spark_home=Path(pyspark.__file__).resolve().parent;require(pyspark.__version__=='3.5.8' and spark_home.is_relative_to(ROOT/'.venv'),'wrong Spark')
    budget=Budget(a.budget);budget.check();run.mkdir(parents=True,exist_ok=False);(run/'staging').mkdir();temp=run/'temp';temp.mkdir();conf=temp/'spark-conf';conf.mkdir()
    props=conf/'spark-defaults.conf';props.write_text('# isolated existing project runtime\n')
    env=os.environ.copy()
    for k in ('PYTHONPATH','PYTHONHOME','SPARK_SUBMIT_OPTS','JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED'):env.pop(k,None)
    env.update(JAVA_HOME=str(runtime.java_home),SPARK_HOME=str(spark_home),SPARK_CONF_DIR=str(conf),TMPDIR=str(temp),SQLITE_TMPDIR=str(temp),SPARK_LOCAL_DIRS=str(temp),
        SPARK_LOCAL_IP='127.0.0.1',PYTHONNOUSERSITE='1',TZ='UTC',PYSPARK_PYTHON=str(runtime.python_executable),PYSPARK_DRIVER_PYTHON=str(runtime.python_executable))
    env['PATH']=os.pathsep.join([str(runtime.python_executable.parent),str(runtime.java_home/'bin'),env.get('PATH','')])
    command=[str(ROOT/'.venv/bin/spark-submit'),'--master','local[4]','--driver-memory','4g','--properties-file',str(props),'--driver-java-options','-Djava.io.tmpdir="'+str(temp)+'"']
    for k,v in {'spark.sql.shuffle.partitions':'32','spark.sql.session.timeZone':'UTC','spark.local.dir':str(temp),'spark.sql.warehouse.dir':(temp/'warehouse').as_uri(),
                'spark.pyspark.python':str(runtime.python_executable),'spark.pyspark.driver.python':str(runtime.python_executable),'spark.driver.host':'127.0.0.1','spark.driver.bindAddress':'127.0.0.1',
                'spark.ui.enabled':'false','spark.sql.catalogImplementation':'in-memory','spark.sql.legacy.timeParserPolicy':'CORRECTED','spark.sql.ansi.enabled':'true'}.items():command+=['--conf',k+'='+v]
    command+=[str(Path(__file__).resolve()),*sys.argv[1:],'--worker']
    result={'status':'failed'};proc=None;started=time.monotonic()
    try:
        with (run/'spark.log').open('x') as log:
            proc=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            while True:
                budget.check()
                try:code=proc.wait(timeout=1);break
                except subprocess.TimeoutExpired:pass
        require(code==0,'synthetic checks failed; local log retained')
        proof=json.loads((run/'staging/validation.json').read_text());require(proof['status']=='passed' and proof['spark_stopped'],'synthetic completion missing')
        budget.check();(run/'staging').rename(run/'complete');result['status']='passed'
    except BaseException as exc:
        if proc and proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        result['error']=str(exc);raise
    finally:
        result.update(elapsed_seconds=round(time.monotonic()-started,3),resources=budget.summary());save(run/'launch.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':main()
