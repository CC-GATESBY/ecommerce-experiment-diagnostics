"""Literal expectations independent of either production parser."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from etl.event_config import HEADER
from etl.oracle import oracle_row


def literal_cases():
    cases = []
    for value, nonfinite, invalid in [('NaN', True, False), ('+NaN', True, False),
            ('-Inf', True, False), ('++NaN', False, True), ('+-Inf', False, True),
            ('--Infinity', False, True)]:
        cases.append(('price', value, {'price_nonfinite': nonfinite, 'price_invalid': invalid,
                                      'price_missing': False, 'price_decimal': None}))
    for ending in ['\n', '\r', '\r\n']:
        cases += [('user_id', '123' + ending, {'user_id_invalid': True, 'user_id_missing': False}),
                  ('price', '1.20' + ending, {'price_invalid': True, 'price_nonfinite': False, 'price_decimal': None}),
                  ('event_time', '2019-10-01 00:00:00 UTC' + ending, {'time_invalid': True, 'time_missing': False, 'event_timestamp_utc': None}),
                  ('price', '+NaN' + ending, {'price_nonfinite': False, 'price_invalid': True})]
    for value in ['', ' ', '\n', '\r', '\r\n', ' \t\r\n\v\f']:
        cases += [('user_id', value, {'user_id_missing': True, 'user_id_invalid': False}),
                  ('price', value, {'price_missing': True, 'price_invalid': False, 'price_nonfinite': False}),
                  ('event_time', value, {'time_missing': True, 'time_invalid': False})]
    return cases


def raw_row(field, value):
    item = dict(zip(HEADER, ['2019-10-01 00:00:00 UTC', 'purchase', '1', '2', 'a', 'b', '1.20', '123', 's']))
    item[field] = value
    return [item[name] for name in HEADER]


class LiteralBoundaryTests(unittest.TestCase):
    def test_oracle_matches_literals(self):
        for field, value, expected in literal_cases():
            with self.subTest(field=field, value=repr(value)):
                actual = oracle_row(raw_row(field, value))
                self.assertEqual(actual[field], value)
                for key, expected_value in expected.items():
                    self.assertEqual(actual[key], expected_value, key)

    def test_spark_matches_literals(self):
        from scripts.project_config import load_config
        import pyspark
        cfg = load_config(ROOT / 'config/local.yaml', ROOT)
        parent = ROOT / '.local/t11/synthetic'; parent.mkdir(exist_ok=True, parents=True)
        folder = Path(tempfile.mkdtemp(prefix='boundary-', dir=parent))
        props = folder / 'spark-defaults.conf'; props.write_text('# isolated\n')
        env = os.environ.copy()
        for name in ('PYTHONPATH', 'PYTHONHOME', 'JAVA_TOOL_OPTIONS', '_JAVA_OPTIONS', 'JDK_JAVA_OPTIONS', 'SPARK_SUBMIT_OPTS'):
            env.pop(name, None)
        env.update(JAVA_HOME=str(cfg.java_home), SPARK_HOME=str(Path(pyspark.__file__).parent),
                   SPARK_CONF_DIR=str(folder), SPARK_LOCAL_DIRS=str(folder), SPARK_LOCAL_IP='127.0.0.1',
                   PYSPARK_PYTHON=str(cfg.python_executable), PYSPARK_DRIVER_PYTHON=str(cfg.python_executable), TZ='UTC')
        command = [str(ROOT / '.venv/bin/spark-submit'), '--master', 'local[4]', '--driver-memory', '4g',
                   '--properties-file', str(props), '--conf', 'spark.sql.session.timeZone=UTC',
                   '--conf', 'spark.sql.legacy.timeParserPolicy=CORRECTED', '--conf', 'spark.ui.enabled=false',
                   '--conf', 'spark.driver.bindAddress=127.0.0.1', '--conf', 'spark.driver.host=127.0.0.1',
                   str(Path(__file__).resolve()), '--spark-probe', str(folder / 'result.json')]
        with (folder / 'spark.log').open('w') as log:
            process = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        self.assertEqual(process.returncode, 0, str(folder.relative_to(ROOT)))
        result = json.loads((folder / 'result.json').read_text())
        self.assertEqual(result['mismatches'], [], str(folder.relative_to(ROOT)))


def spark_probe(destination):
    from pyspark.sql import SparkSession, functions as F, types as T
    spec = importlib.util.spec_from_file_location('events', ROOT / 'etl/01_events.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    spark = SparkSession.builder.getOrCreate(); spark.sparkContext.setLogLevel('WARN')
    result = {'mismatches': [], 'java': spark.sparkContext._jvm.java.lang.System.getProperty('java.version'), 'spark': spark.version}
    try:
        cases = literal_cases()
        # Unique synthetic session labels let each literal case be checked without collecting facts.
        rows = []
        for index, (field, value, _) in enumerate(cases):
            item = raw_row(field, value); item[8] = str(index); rows.append(item)
        raw = spark.createDataFrame(rows, T.StructType([T.StructField(name, T.StringType()) for name in HEADER]))
        fact = module.transform(raw, dict(source_id='synthetic', scope_id='synthetic_boundary', input_sha256='0'*64), 'boundary')
        for index, (field, value, expected) in enumerate(cases):
            condition = F.col(field).eqNullSafe(F.lit(value))
            for name, wanted in expected.items():
                condition = condition & F.col(name).eqNullSafe(F.lit(wanted))
            count = fact.filter((F.col('user_session') == str(index)) & ~condition).count()
            if count:
                result['mismatches'].append({'field': field, 'value_repr': repr(value), 'expected': expected, 'mismatch_count': count})
    finally:
        spark.stop()
        Path(destination).write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--spark-probe':
        spark_probe(sys.argv[2])
    else:
        unittest.main()
