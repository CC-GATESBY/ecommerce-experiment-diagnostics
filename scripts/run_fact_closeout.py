"""Run isolated synthetic gates, then one authorized read of existing facts."""

import argparse
from datetime import datetime, timezone
import csv
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from etl.event_config import sha256
from etl.fact_registry import FactReader, inspect_batch, local_path, read_json, register_batch, require
from etl.resource_budget import Budget
from scripts.project_config import load_config

CODE = ['etl/date_quality.py', 'etl/fact_registry.py', 'tests/test_fact_access.py',
        'scripts/run_fact_closeout.py', 'etl/01_events.py', 'etl/event_config.py', 'etl/oracle.py']


def fingerprints():
    return {name: sha256(ROOT / name) for name in CODE}


def real_read(spark, config, stage):
    from pyspark.sql import functions as F
    cfg = read_json(Path(config)); require(set(cfg) == {'selected', 'replicate_run_path'}, 'configuration keys mismatch')
    selected = cfg['selected']; first = inspect_batch(ROOT, selected)
    replicate_path = local_path(ROOT, cfg['replicate_run_path'])
    second = inspect_batch(ROOT, {**selected, 'run_id': replicate_path.name, 'run_path': str(replicate_path.relative_to(ROOT))})
    require(selected['run_id'] == 'month-v101-01' and second['descriptor']['run_id'] == 'month-v101-02', 'fixed first-run selection required')
    require(first['summary'] == second['summary'] and first['daily'] == second['daily'], 'replicate evidence differs')
    second_proof = read_json(replicate_path / 'complete/validation.json')
    for key in ('rerun_previous_minus_current', 'rerun_current_minus_previous'):
        require(second_proof['checks'][key] == {'expected': 0, 'actual': 0, 'pass': True}, 'replicate full comparison missing')
    before = {**first['evidence'], **second['evidence']}
    for item in first['inventory'] + second['inventory']:
        before[item['path']] = item['sha256']
    # Historical daily CSV remains immutable and is cross-checked without reading source data.
    history_path = ROOT / 'reports/data_quality_daily.csv'; before[str(history_path.relative_to(ROOT))] = sha256(history_path)
    with history_path.open() as stream:
        history = list(csv.DictReader(stream))
    require(len(history) == len(first['daily']) and all(r['formal_analysis_release'] == 'not_granted'
            and r['reference_run_id'] == selected['run_id'] and r['scope_id'] == selected['scope_id']
            and int(r['record_count']) == first['daily'][r['utc_date']]['record_count']
            and r['amount_status'] == first['daily'][r['utc_date']]['amount_status'] for r in history), 'historical daily evidence mismatch')
    registry = stage / 'registry.json'
    registered = register_batch(ROOT, registry, selected)
    duplicate = register_batch(ROOT, registry, second['descriptor'])
    require(duplicate == {'status': 'already_registered', 'selected_run': 'month-v101-01'}, 'replicate must not append')
    (stage / 'selected_fact_inventory.json').write_text(json.dumps(dict(selected=first, replicate=second,
        reason='first successful run, already referenced by historical daily quality report'), indent=2))
    dates = selected['dates']; scopes = [selected['scope_id']]
    checks = {}
    def check(name, expected, actual):
        checks[name] = {'expected': expected, 'actual': actual, 'pass': expected == actual}
        require(expected == actual, name)
    with FactReader(spark, ROOT, registry, selected['series_id']) as reader:
        count_frame = reader.read(dates, 'count', expected_scopes=scopes)
        amount_frame = reader.read(dates, 'amount', expected_scopes=scopes)
        check('count_use_rows', 2114081, count_frame.count())
        # One bounded date aggregate from the already-materialized cache, not a second Parquet scan.
        rows = amount_frame.groupBy('event_date_utc').agg(F.count('*').alias('records'),
            F.sum(F.col('amount_eligible').cast('long')).alias('amount_eligible')).limit(32).collect()
        actual = {r['event_date_utc'].isoformat(): [r['records'], r['amount_eligible']] for r in rows}
        expected = {d: [s['record_count'], s['flags']['amount_eligible']] for d, s in first['daily'].items()}
        check('amount_use_all_behavior_denominator_per_date', expected, actual)
        check('single_selected_parquet_load', 1, reader.parquet_loads)
        check('physical_read_provenance_and_daily_counts', True, all(v['pass'] for v in reader.read_checks.values()))
        checks['read_checks'] = {'expected': reader.read_checks, 'actual': reader.read_checks, 'pass': True}
    check('both_runs_receipts_facts_and_historical_report_unchanged', before,
          {path: sha256(ROOT / path) for path in before})
    report = stage / 'date_quality_gate.csv'
    gates = list(first['gates'].values())
    with report.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(gates[0])); writer.writeheader()
        for gate in gates:
            writer.writerow({k: json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v for k, v in gate.items()})
    return dict(status='passed', checks=checks, selected_run=selected['run_id'], registration=registered,
                replicate_registration=duplicate, dates=len(dates), rows=selected['expected_records'],
                count_allowed_dates=sum(g['count_allowed'] for g in gates),
                amount_allowed_dates=sum(g['amount_allowed'] for g in gates),
                warning_dates=sum(bool(g['warnings']) for g in gates),
                new_real_fact_files=0, source_csv_reads=0, real_fact_loads=1,
                time_min=first['summary']['time_min'], time_max=first['summary']['time_max'])


def worker(args):
    from pyspark.sql import SparkSession
    stage = Path(args.run_dir) / 'staging'; spark = None; result = {'status': 'failed'}
    started = time.monotonic()
    try:
        spark = SparkSession.builder.appName('T1.1-date-gates-closeout').getOrCreate()
        spark.sparkContext.setLogLevel('WARN')
        require(spark.sparkContext.master == 'local[4]' and spark.conf.get('spark.sql.session.timeZone') == 'UTC'
                and spark.sparkContext.getConf().get('spark.driver.memory') == '4g'
                and spark.conf.get('spark.sql.catalogImplementation') == 'in-memory', 'runtime mismatch')
        if args.stage == 'synthetic':
            sys.path.insert(0, str(ROOT / 'tests'))
            from test_fact_access import run_synthetic
            result = run_synthetic(spark, ROOT, Path(args.run_dir) / 'synthetic')
        else:
            gate = read_json(local_path(ROOT, args.synthetic_gate))
            require(gate.get('status') == 'passed' and gate.get('spark_stopped') is True
                    and gate.get('stage') == 'synthetic' and gate.get('code_sha256') == fingerprints(), 'synthetic gate failed or stale')
            result = real_read(spark, args.config, stage)
        result['versions'] = dict(python=sys.version.split()[0], spark=spark.version,
                                 java=spark.sparkContext._jvm.java.lang.System.getProperty('java.version'))
    except BaseException as exc:
        result.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
        raise
    finally:
        if spark:
            spark.stop(); result['spark_stopped'] = True
        result.update(stage=args.stage, elapsed_seconds=round(time.monotonic() - started, 3), code_sha256=fingerprints())
        (stage / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', choices=['synthetic', 'real'], required=True)
    parser.add_argument('--runtime-config', required=True)
    parser.add_argument('--config')
    parser.add_argument('--synthetic-gate')
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--budget', required=True)
    parser.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    require(sys.version_info[:2] == (3, 11) and Path(sys.prefix) == ROOT / '.venv', 'project Python 3.11 required')
    runtime = load_config(args.runtime_config, ROOT)
    import pyspark
    spark_home = Path(pyspark.__file__).resolve().parent
    require(pyspark.__version__ == '3.5.8' and spark_home.is_relative_to(ROOT / '.venv'), 'project PySpark required')
    require(args.stage != 'real' or (args.config and args.synthetic_gate), 'real stage requires config and synthetic gate')
    run = local_path(ROOT, args.run_dir); budget = Budget(ROOT, local_path(ROOT, args.budget))
    require(budget.config['max_new_bytes'] <= 2 * 1024**3, 'closeout budget exceeds 2 GiB')
    budget.check(); run.mkdir(parents=True, exist_ok=False)
    stage = run / 'staging'; stage.mkdir(); temp = run / 'temp'; temp.mkdir()
    conf = temp / 'spark-conf'; conf.mkdir(); props = conf / 'spark-defaults.conf'; props.write_text('# isolated defaults\n')
    env = os.environ.copy()
    for key in ('PYTHONPATH', 'PYTHONHOME', 'SPARK_SUBMIT_OPTS', 'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS', 'SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED'):
        env.pop(key, None)
    env.update(JAVA_HOME=str(runtime.java_home), SPARK_HOME=str(spark_home), SPARK_CONF_DIR=str(conf), TMPDIR=str(temp),
               SQLITE_TMPDIR=str(temp), SPARK_LOCAL_DIRS=str(temp), SPARK_LOCAL_IP='127.0.0.1', PYTHONNOUSERSITE='1', TZ='UTC',
               PYSPARK_PYTHON=str(runtime.python_executable), PYSPARK_DRIVER_PYTHON=str(runtime.python_executable))
    env['PATH'] = os.pathsep.join([str(runtime.python_executable.parent), str(runtime.java_home / 'bin'), env.get('PATH', '')])
    command = [str(ROOT / '.venv/bin/spark-submit'), '--master', 'local[4]', '--driver-memory', '4g', '--properties-file', str(props),
               '--driver-java-options', '-Djava.io.tmpdir="' + str(temp) + '"']
    for key, value in {'spark.sql.shuffle.partitions': '32', 'spark.sql.session.timeZone': 'UTC', 'spark.local.dir': str(temp),
                       'spark.sql.warehouse.dir': (temp / 'warehouse').as_uri(), 'spark.pyspark.python': str(runtime.python_executable),
                       'spark.pyspark.driver.python': str(runtime.python_executable), 'spark.driver.host': '127.0.0.1',
                       'spark.driver.bindAddress': '127.0.0.1', 'spark.ui.enabled': 'false', 'spark.sql.catalogImplementation': 'in-memory',
                       'spark.sql.legacy.timeParserPolicy': 'CORRECTED', 'spark.sql.ansi.enabled': 'true'}.items():
        command += ['--conf', key + '=' + value]
    command += [str(Path(__file__).resolve()), *sys.argv[1:], '--worker']
    started = time.monotonic(); receipt = {'status': 'running', 'started_at': datetime.now(timezone.utc).isoformat()}
    process = None
    try:
        with (run / 'spark.log').open('x') as stream:
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            while True:
                budget.check()
                try:
                    code = process.wait(timeout=2); break
                except subprocess.TimeoutExpired:
                    pass
        require(code == 0, 'worker failed; see local spark.log')
        result = read_json(stage / 'validation.json')
        require(result['status'] == 'passed' and result.get('spark_stopped') is True, 'validation/normal Spark stop required')
        budget.check(); stage.rename(run / 'complete'); receipt['status'] = 'passed'
    except BaseException as exc:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait()
        receipt.update(status='failed', error=str(exc))
        raise
    finally:
        receipt.update(elapsed_seconds=round(time.monotonic() - started, 3), resources=budget.summary(), peak_memory='not_measured')
        (run / 'launch.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps({'stage': args.stage, 'status': receipt['status'], 'elapsed_seconds': receipt['elapsed_seconds']}), flush=True)


if __name__ == '__main__':
    main()
