"""Bind the verified venv/JDK before JVM startup; publish only verified runs."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import resource
import signal
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.project_config import ConfigError, load_config
from etl.event_config import CONTRACT, SHA, load_events_config, sha256
from etl.resource_budget import Budget
from etl.oracle import build_expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--runtime-config', required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--compare-run-id')
    parser.add_argument('--regression-against')
    parser.add_argument('--engineering-gate')
    parser.add_argument('--budget')
    args = parser.parse_args()
    run = None; receipt = {'status': 'running'}; started = time.monotonic(); budget = None
    try:
        runtime = load_config(args.runtime_config, ROOT)
        config = load_events_config(args.config, ROOT)
        code_files = ['etl/01_events.py', 'etl/oracle.py', 'etl/event_config.py', 'etl/resource_budget.py', 'scripts/run_events.py']
        if args.budget:
            budget_path = Path(args.budget).resolve()
            if not budget_path.is_relative_to(ROOT / '.local/t11'):
                raise ConfigError('budget receipt must be inside .local/t11')
            budget = Budget(ROOT, budget_path); budget.check()
        if config['kind'] == 'user_sample_candidate':
            if not args.engineering_gate or not budget:
                raise ConfigError('monthly parsing requires a verified engineering regression and cumulative budget')
            gate = Path(args.engineering_gate).resolve()
            if not gate.is_relative_to(ROOT / '.local/t11'):
                raise ConfigError('engineering gate must be local to this project')
            proof = json.loads((gate / 'complete/validation.json').read_text())
            launch = json.loads((gate / 'launch.json').read_text())
            frozen = {'record_count': 100000, 'users': 20384, 'buyers': 1336, 'purchase_events': 1655, 'purchase_amount': '501176.21'}
            if not (proof['status'] == launch['status'] == 'passed' and proof['spark_stopped']
                    and proof['contract_version'] == CONTRACT and launch['input_sha256'] == SHA
                    and all(proof['summary'][k] == v for k,v in frozen.items())
                    and proof['checks']['historical_old_minus_new']['pass']
                    and proof['checks']['historical_new_minus_old']['pass']
                    and all(v['pass'] for v in proof['checks'].values())
                    and all(launch['code_sha256'].get(name) == sha256(ROOT/name) for name in code_files)):
                raise ConfigError('engineering regression gate is stale or failed')
        if sys.version_info[:2] != (3, 11) or Path(sys.prefix) != ROOT / '.venv':
            raise ConfigError('use project .venv/bin/python 3.11')
        import pyspark
        spark_home = Path(pyspark.__file__).resolve().parent
        if pyspark.__version__ != '3.5.8' or not spark_home.is_relative_to(ROOT / '.venv'):
            raise ConfigError('project PySpark 3.5.8 required')
        java = subprocess.run([str(runtime.java_home / 'bin/java'), '-version'], capture_output=True, text=True, check=True)
        if not re.search(r'version "17\.', java.stderr + java.stdout):
            raise ConfigError('JDK 17 required')
        for value in (args.run_id, args.compare_run_id):
            if value is not None and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value):
                raise ConfigError('run IDs must be simple directory names')
        base = config['output_root'] / config['scope_id']
        target = base / args.run_id
        if target.exists():
            raise ConfigError('run ID exists; no overwrite is allowed')
        previous = base / args.compare_run_id if args.compare_run_id else None
        previous_files = {}
        if previous:
            if not (previous / 'complete/validation.json').is_file():
                raise ConfigError('compare run must have a completed validation')
            previous_files = {str(p.relative_to(previous)): sha256(p) for p in previous.rglob('*') if p.is_file()}
        if shutil.disk_usage(ROOT).free < 150 * 1024**3:
            raise ConfigError('at least 150 GiB free required')
        target.mkdir(parents=True, exist_ok=False); run = target
        stage = run / 'staging'; stage.mkdir()
        temp = run / 'temp'; temp.mkdir()
        receipt.update(run_id=args.run_id, scope_id=config['scope_id'], input_sha256=config['input_sha256'],
                       started_at=datetime.now(timezone.utc).isoformat(), free_before_bytes=shutil.disk_usage(ROOT).free,
                       code_sha256={name: sha256(ROOT / name) for name in code_files}, contract_version=CONTRACT, input_bytes=config['input_path'].stat().st_size)
        (run / 'launch.json').write_text(json.dumps(receipt, indent=2) + '\n')
        expected = build_expected(config['input_path'], stage / 'expected_rows.jsonl', config['expected_records'],
                                  budget_check=budget.check if budget else None)
        (stage / 'expected_summary.json').write_text(json.dumps(expected, indent=2) + '\n')
        print(json.dumps({'phase': 'stdlib_expected_complete', 'records': expected['record_count']}), flush=True)
        conf = temp / 'spark-conf'; conf.mkdir(); props = conf / 'spark-defaults.conf'
        props.write_text('# No inherited Spark defaults.\n')
        env = os.environ.copy()
        for key in ('PYTHONPATH', 'PYTHONHOME', 'SPARK_SUBMIT_OPTS', 'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS',
                    'JDK_JAVA_OPTIONS', 'SPARK_REMOTE', 'SPARK_CONNECT_MODE_ENABLED'):
            env.pop(key, None)
        env.update(JAVA_HOME=str(runtime.java_home), SPARK_HOME=str(spark_home), SPARK_CONF_DIR=str(conf), TMPDIR=str(temp), SQLITE_TMPDIR=str(temp),
                   SPARK_LOCAL_DIRS=str(temp), SPARK_LOCAL_IP='127.0.0.1', PYTHONNOUSERSITE='1', TZ='UTC',
                   PYSPARK_PYTHON=str(runtime.python_executable), PYSPARK_DRIVER_PYTHON=str(runtime.python_executable))
        env['PATH'] = os.pathsep.join([str(runtime.python_executable.parent), str(runtime.java_home / 'bin'), env.get('PATH', '')])
        command = [str(ROOT / '.venv/bin/spark-submit'), '--master', runtime.master,
                   '--driver-memory', runtime.driver_memory, '--properties-file', str(props),
                   '--driver-java-options', '-Djava.io.tmpdir="' + str(temp) + '"']
        settings = {'spark.sql.shuffle.partitions': '32', 'spark.sql.session.timeZone': 'UTC',
                    'spark.local.dir': str(temp), 'spark.sql.warehouse.dir': (temp / 'warehouse').as_uri(),
                    'spark.pyspark.python': str(runtime.python_executable), 'spark.pyspark.driver.python': str(runtime.python_executable),
                    'spark.driver.host': '127.0.0.1', 'spark.driver.bindAddress': '127.0.0.1', 'spark.ui.enabled': 'false',
                    'spark.sql.catalogImplementation': 'in-memory', 'spark.sql.legacy.timeParserPolicy': 'CORRECTED',
                    'spark.sql.ansi.enabled': 'true'}
        for key, value in settings.items():
            command += ['--conf', key + '=' + value]
        command += [str(ROOT / 'etl/01_events.py'), '--config', str(Path(args.config).resolve()),
                    '--runtime-config', str(Path(args.runtime_config).resolve()), '--run-dir', str(run)]
        if previous:
            command += ['--compare-run', str(previous)]
        if args.regression_against:
            old = Path(args.regression_against).resolve()
            if config['kind'] != 'engineering_sample' or not old.is_relative_to(ROOT / '.local/t11'):
                raise ConfigError('historical regression only for the authorized engineering input')
            command += ['--regression-against', str(old)]
        with (run / 'spark.log').open('x') as log:
            process = subprocess.Popen(command, env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                while True:
                    if budget:
                        budget.check()
                    try:
                        returncode = process.wait(timeout=2)
                        break
                    except subprocess.TimeoutExpired:
                        continue
                if returncode:
                    raise RuntimeError(f'Spark process failed with exit code {returncode}; see local spark.log')
            except BaseException:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL); process.wait()
                raise
        validation = json.loads((stage / 'validation.json').read_text())
        if validation['status'] != 'passed' or not validation['spark_stopped']:
            raise RuntimeError('validation/normal Spark stop required before publication')
        if previous:
            after_files = {str(p.relative_to(previous)): sha256(p) for p in previous.rglob('*') if p.is_file()}
            if previous_files != after_files:
                raise RuntimeError('previous output changed')
            receipt['previous_output_unchanged'] = True
        if sha256(config['input_path']) != config['input_sha256']:
            raise RuntimeError('input changed')
        if shutil.disk_usage(ROOT).free < 150 * 1024**3:
            raise RuntimeError('free disk fell below 150 GiB')
        if budget:
            budget.check()
        stage.rename(run / 'complete')
        receipt['status'] = 'passed'
        return 0
    except BaseException as exc:
        receipt.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
        print('T1.1 failed: ' + str(exc), file=sys.stderr)
        return 1
    finally:
        if budget:
            receipt['resources'] = budget.summary()
        if run:
            receipt['memory'] = dict(launcher_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                                     children_rusage_maxrss_bytes=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                                     combined_process_tree_peak='not_measured', interpretation='macOS rusage high-water values, not simultaneous aggregate RSS')
            receipt.update(elapsed_seconds=round(time.monotonic() - started, 3),
                           free_after_bytes=shutil.disk_usage(ROOT).free,
                           output_bytes=sum(p.stat().st_size for p in run.rglob('*') if p.is_file()))
            (run / 'launch.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps({'run_id': args.run_id, 'status': receipt['status']}), flush=True)


if __name__ == '__main__':
    raise SystemExit(main())
