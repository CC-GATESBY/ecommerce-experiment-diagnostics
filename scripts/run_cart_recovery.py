"""One authorized fact context for the first-cart planning baseline."""
import argparse
import csv
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from abtest.sample_size import planning_tables
from etl.fact_registry import FactReader, load_registry, require
from scripts.project_config import load_config
from scripts.run_metrics import ready, bounded, write_json, publish, DATES, SCOPE, SERIES, validate_config
from scripts.metric_snapshot import digest

VERSION = 'cart-recovery-first-cart-v1'
SQL = 'sql/experiments/cart_recovery_eligibility.sql'
CODE = ['scripts/run_cart_recovery.py', SQL, 'abtest/sample_size.py', 'tests/test_cart_recovery.py', 'etl/fact_registry.py']


def code_hashes():
    return {name: digest(ROOT/name) for name in CODE}


def write_csv(path, rows):
    require(bool(rows), 'refuse an empty summary without a status')
    with Path(path).open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader(); writer.writerows([ready(r) for r in rows])


def eligibility(spark, fact):
    fact.createOrReplaceTempView('cart_fact')
    return spark.sql((ROOT/SQL).read_text())


def summarize(spark, users):
    users.createOrReplaceTempView('cart_users')
    r = bounded(spark.sql("""
      SELECT COUNT(*) AS cart_users,
        COUNT_IF(window_complete) AS complete_first_cart_users,
        COUNT_IF(eligibility_status='right_censored') AS right_censored_users,
        COUNT_IF(eligibility_status='waiting_purchase_excluded') AS waiting_purchase_excluded_users,
        COUNT_IF(eligibility_status='eligible') AS eligible_users,
        COUNT_IF(purchased_24h=1) AS outcome_buyers,
        COUNT_IF(purchased_24h=0) AS outcome_nonbuyers,
        COALESCE(SUM(CASE WHEN eligibility_status='eligible' THEN outcome_purchase_events ELSE 0 END),0) AS outcome_purchase_events,
        COALESCE(SUM(CASE WHEN eligibility_status='eligible' THEN outcome_bad_amount_events ELSE 0 END),0) AS outcome_bad_amount_events,
        COUNT_IF(eligibility_status='eligible' AND outcome_bad_amount_events>0) AS outcome_bad_amount_users,
        COALESCE(SUM(CASE WHEN eligibility_status='eligible' THEN known_outcome_amount ELSE CAST(0 AS DECIMAL(38,2)) END),CAST(0 AS DECIMAL(38,2))) AS known_outcome_amount
      FROM cart_users
    """), 1)[0]
    require(r['cart_users'] == r['complete_first_cart_users'] + r['right_censored_users'], 'window conservation')
    require(r['complete_first_cart_users'] == r['waiting_purchase_excluded_users'] + r['eligible_users'], 'eligibility conservation')
    require(r['eligible_users'] == r['outcome_buyers'] + r['outcome_nonbuyers'], 'outcome conservation')
    n = r['eligible_users']
    r['p_hist'] = Decimal(r['outcome_buyers'])/n if n else None
    r['amount_status'] = ('no_eligible_users' if not n else 'partial_or_unknown'
                          if r['outcome_bad_amount_users'] else 'complete_observed'
                          if r['outcome_buyers'] else 'no_purchases')
    r['observed_amount_per_eligible_user'] = r['known_outcome_amount']/n if n and not r['outcome_bad_amount_users'] else None
    return r


def worker(args, stage):
    from pyspark.sql import SparkSession
    from pyspark import StorageLevel
    spark = None; reader = None; users = None
    result = {'status': 'failed'}; started = time.monotonic()
    try:
        spark = SparkSession.builder.appName('T3.4 cart recovery planning').getOrCreate()
        spark.sparkContext.setLogLevel('WARN')
        require(spark.sparkContext.master == 'local[4]' and spark.conf.get('spark.driver.memory') == '4g'
                and spark.conf.get('spark.sql.session.timeZone') == 'UTC', 'runtime mismatch')
        if args.test:
            import unittest
            import tests.test_cart_recovery as suite_module
            suite_module.SPARK = spark
            suite = unittest.defaultTestLoader.loadTestsFromModule(suite_module)
            outcome = unittest.TextTestRunner(verbosity=2).run(suite)
            require(outcome.wasSuccessful(), 'synthetic/planning tests failed')
            result = dict(status='passed', kind='synthetic', tests=outcome.testsRun, code_sha256=code_hashes())
        else:
            import yaml
            scope = yaml.safe_load((ROOT/'config/analysis_scope.yaml').read_text())
            require(scope['analysis_scope_version'] == 'rees46_oct_user5_analysis_v1'
                    and scope['binding']['fact_run'] == 'month-v101-01'
                    and scope['binding']['scope_id'] == SCOPE
                    and scope['binding']['duplicate_policy'] == 'baseline_keep_all', 'analysis scope mismatch')
            cfg = json.loads((ROOT/'config/metrics.local.json').read_text()); validate_config(cfg)
            entries = [e for e in load_registry(ROOT, cfg['registry_path'])['batches']
                       if e['descriptor']['series_id'] == SERIES]
            require(len(entries) == 1 and entries[0]['descriptor']['run_id'] == 'month-v101-01'
                    and entries[0]['descriptor']['scope_id'] == SCOPE, 'canonical fact required')
            files = [ROOT/i['path'] for i in entries[0]['inventory']]
            before = {str(p.relative_to(ROOT)): [p.stat().st_size, p.stat().st_mtime_ns] for p in files}
            reader = FactReader(spark, ROOT, cfg['registry_path'], SERIES, allow_criteo_manifest_extension=True)
            reader.read(DATES, 'count', expected_scopes=[SCOPE])
            fact = reader.read(DATES, 'amount', expected_scopes=[SCOPE])
            users = eligibility(spark, fact).persist(StorageLevel.MEMORY_ONLY)
            summary = summarize(spark, users)
            with (ROOT/'reports/behavior_coverage.csv').open() as f:
                previous = [r for r in csv.DictReader(f) if r['level']=='month' and r['event_type']=='cart']
            require(len(previous) == 1 and summary['cart_users'] == int(previous[0]['behavior_users']), 'whole-month cart users mismatch')
            require(summary['eligible_users'] > 0, 'no eligible historical population; planning cannot proceed')
            require(reader.parquet_loads == 1, 'more than one physical fact load')
            users.write.mode('errorifexists').parquet(str(stage/'historical_user_windows'))
            # Only a bounded one-row structural verification; no record collection.
            saved = spark.read.parquet(str(stage/'historical_user_windows'))
            require(saved.schema.simpleString() == users.schema.simpleString() and saved.count() == summary['cart_users'], 'user-window write/read mismatch')
            sizes, economics = planning_tables(summary['p_hist'], summary['eligible_users'])
            baseline = dict(analysis_scope=scope['analysis_scope_version'], scope_id=SCOPE,
                            source_run='month-v101-01', rule_version=VERSION,
                            t_cart_start_inclusive='2019-10-01T00:00:00Z',
                            t_cart_end_exclusive='2019-10-30T00:00:00Z', waiting_hours=24, outcome_hours=24,
                            **summary, interpretation='historical_planning_reference_not_reminder_control_rate')
            write_csv(stage/'cart_recovery_baseline.csv', [baseline])
            write_csv(stage/'sample_size_scenarios.csv', sizes)
            write_csv(stage/'coupon_economics_scenarios.csv', economics)
            after = {str(p.relative_to(ROOT)): [p.stat().st_size, p.stat().st_mtime_ns] for p in files}
            require(before == after, 'source fact changed')
            result = dict(status='passed', run_id=args.run_id, baseline=baseline, fact_loads=reader.parquet_loads,
                          fact_reader_checks=reader.read_checks, fact_stat_unchanged=True,
                          manifest_compatibility='exact_audited_criteo_extension_only_registry_unchanged',
                          code_sha256=code_hashes(), design_before_run_sha256=digest(ROOT/'reports/next_experiment_design.md'),
                          source_inventory=entries[0]['inventory'],
                          config_sha256=digest(ROOT/'config/analysis_scope.yaml'),
                          versions=dict(python=sys.version.split()[0], spark=spark.version,
                                        java=spark._jvm.java.lang.System.getProperty('java.version')))
    except BaseException as exc:
        result.update(status='failed', error=type(exc).__name__+': '+str(exc)); raise
    finally:
        if users is not None: users.unpersist(blocking=True)
        if reader: reader.close()
        if spark: spark.stop(); result['spark_stopped'] = True
        result['elapsed_seconds'] = round(time.monotonic()-started, 3)
        write_json(stage/'validation.json', result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--synthetic-gate')
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    import re
    require(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run_id), 'invalid run id')
    run = ROOT/'.local/t34'/args.run_id; stage = run/'staging'
    if args.worker: return worker(args, stage)
    require(Path(sys.prefix) == ROOT/'.venv' and sys.version_info[:2] == (3,11), 'project venv required')
    runtime = load_config(ROOT/'config/local.yaml', ROOT)
    import pyspark
    spark_home = Path(pyspark.__file__).resolve().parent
    require(pyspark.__version__ == '3.5.8' and spark_home.is_relative_to(ROOT/'.venv'), 'project Spark required')
    if not args.test:
        require(bool(args.synthetic_gate), 'synthetic gate required')
        gate = json.loads(Path(args.synthetic_gate).read_text())
        require(gate['status'] == 'passed' and gate['kind'] == 'synthetic'
                and gate['code_sha256'] == code_hashes(), 'synthetic/code gate mismatch')
    run.mkdir(parents=True, exist_ok=False); stage.mkdir(); temp = run/'temp'; temp.mkdir()
    conf = temp/'spark-conf'; conf.mkdir(); props = conf/'spark-defaults.conf'
    props.write_text('# isolated project settings\n')
    env = os.environ.copy()
    for key in ('PYTHONPATH','PYTHONHOME','SPARK_SUBMIT_OPTS','JAVA_TOOL_OPTIONS','_JAVA_OPTIONS',
                'JDK_JAVA_OPTIONS','SPARK_REMOTE','SPARK_CONNECT_MODE_ENABLED'): env.pop(key,None)
    env.update(JAVA_HOME=str(runtime.java_home), SPARK_HOME=str(spark_home), SPARK_CONF_DIR=str(conf),
               TMPDIR=str(temp), SPARK_LOCAL_DIRS=str(temp), SPARK_LOCAL_IP='127.0.0.1', PYTHONNOUSERSITE='1', TZ='UTC',
               PYSPARK_PYTHON=str(runtime.python_executable), PYSPARK_DRIVER_PYTHON=str(runtime.python_executable))
    env['PATH'] = os.pathsep.join([str(runtime.python_executable.parent),str(runtime.java_home/'bin'),env.get('PATH','')])
    command = [str(ROOT/'.venv/bin/spark-submit'),'--master','local[4]','--driver-memory','4g',
               '--properties-file',str(props),'--driver-java-options','-Djava.io.tmpdir="'+str(temp)+'"']
    for key,value in {'spark.sql.shuffle.partitions':'32','spark.sql.session.timeZone':'UTC',
                      'spark.driver.host':'127.0.0.1','spark.driver.bindAddress':'127.0.0.1',
                      'spark.sql.warehouse.dir':(temp/'warehouse').as_uri(),'spark.ui.enabled':'false',
                      'spark.sql.catalogImplementation':'in-memory','spark.sql.ansi.enabled':'true'}.items():
        command += ['--conf',key+'='+value]
    command += [str(Path(__file__).resolve()),*sys.argv[1:],'--worker']
    started=time.monotonic(); process=None; minimum=shutil.disk_usage(ROOT).free; peak=0
    def budget():
        nonlocal minimum,peak
        used=sum(p.stat().st_size for p in (ROOT/'.local/t34').rglob('*') if p.is_file()) + 1024**2
        minimum=min(minimum,shutil.disk_usage(ROOT).free); peak=max(peak,used)
        require(used<=2*1024**3 and minimum>=150*1024**3, 'T3.4 budget exceeded')
    receipt=dict(status='running',run_id=args.run_id,started_utc=datetime.now(timezone.utc).isoformat())
    try:
        budget()
        with (run/'spark.log').open('x') as log:
            process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            while process.poll() is None:
                budget()
                try: process.wait(timeout=2)
                except subprocess.TimeoutExpired: pass
        require(process.returncode == 0, 'Spark job failed; local evidence retained')
        budget(); publish(stage,run); receipt['status']='passed'
    except BaseException as exc:
        if process and process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: os.killpg(process.pid,signal.SIGKILL); process.wait()
        receipt.update(status='failed',error=str(exc)); raise
    finally:
        receipt.update(elapsed_seconds=round(time.monotonic()-started,3), sampled_peak_new_bytes_with_1MiB_reserve=peak,
                       minimum_free_sampled_bytes=minimum,peak_memory='not_measured')
        write_json(run/'launch.json',receipt); print(json.dumps(receipt),flush=True)


if __name__ == '__main__':
    main()
