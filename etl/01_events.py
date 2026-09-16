"""Parse and independently verify one authorized engineering CSV with Spark."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from etl.event_config import (ALLOWED, CONTRACT, DERIVED, FLAGS, HEADER,
                              PROVENANCE, csv_line_separator, load_events_config, sha256)
from scripts.project_config import load_config
from pyspark.sql import SparkSession, functions as F, types as T
import pyspark


def transform(raw, config, run_id):
    df = raw.select(*[F.coalesce(F.col(name), F.lit('')).alias(name) for name in HEADER])
    blank = lambda name: F.col(name).rlike(r'\A[ \t\r\n\x0b\x0c]*\z')
    pattern = "yyyy-MM-dd HH:mm:ss 'UTC'"
    exact = F.col('event_time').rlike(r'\A[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} UTC\z') & ~F.col('event_time').startswith('0000-')
    df = df.withColumn('event_timestamp_utc', F.when(exact, F.try_to_timestamp('event_time', F.lit(pattern))))
    df = df.withColumn('event_date_utc', F.to_date('event_timestamp_utc'))
    df = df.withColumn('time_missing', blank('event_time')).withColumn('time_invalid', ~blank('event_time') & F.col('event_timestamp_utc').isNull())
    for name in ('user_id', 'product_id', 'category_id'):
        df = df.withColumn(name + '_missing', blank(name)).withColumn(name + '_invalid', ~blank(name) & ~F.col(name).rlike(r'\A[0-9]+\z'))
    for name, flag in [('category_code', 'category_code_missing'), ('brand', 'brand_missing'), ('user_session', 'session_missing')]:
        df = df.withColumn(flag, blank(name))
    df = df.withColumn('event_type_unknown', ~F.col('event_type').isin(*ALLOWED))
    lexical = F.col('price').rlike(r'\A[+-]?[0-9]+(?:\.[0-9]+)?\z')
    nonfinite = F.lower(F.col('price')).rlike(r'\A[+-]?(?:s?nan|inf|infinity)\z')
    integral = F.regexp_replace(F.regexp_extract('price', r'^[+-]?([0-9]+)', 1), '^0+', '')
    fractional = F.regexp_extract('price', r'\.([0-9]+)\z', 1)
    zero = lexical & ~F.col('price').rlike('[1-9]')
    df = (df.withColumn('price_missing', blank('price'))
          .withColumn('price_nonfinite', nonfinite)
          .withColumn('price_invalid', ~blank('price') & ~lexical & ~nonfinite)
          .withColumn('price_negative', lexical & F.col('price').startswith('-') & ~zero)
          .withColumn('price_zero', zero)
          .withColumn('price_precision_exceeded', lexical & (F.length(integral) > 16))
          .withColumn('price_scale_exceeded', lexical & (F.length(fractional) > 2)))
    fits = lexical & ~F.col('price_precision_exceeded') & ~F.col('price_scale_exceeded')
    df = df.withColumn('price_decimal', F.when(fits, F.col('price').cast(T.DecimalType(18, 2))))
    df = df.withColumn('event_eligible', F.col('event_timestamp_utc').isNotNull() & ~F.col('user_id_missing') & ~F.col('user_id_invalid') & ~F.col('event_type_unknown'))
    df = df.withColumn('amount_eligible', F.col('event_eligible') & (F.col('event_type') == 'purchase') & F.col('price_decimal').isNotNull() & ~F.col('price_negative'))
    for name, value in {'source_id': config['source_id'], 'scope_id': config['scope_id'],
                        'input_sha256': config['input_sha256'], 'contract_version': CONTRACT,
                        'run_id': run_id}.items():
        df = df.withColumn(name, F.lit(value))
    df = df.withColumn('parsed_at_utc', F.lit(datetime.now(timezone.utc).replace(tzinfo=None)).cast('timestamp'))
    return df.select(*(HEADER + DERIVED + FLAGS + PROVENANCE))


def canonical(df):
    return df.select(*HEADER,
                     F.date_format('event_timestamp_utc', "yyyy-MM-dd'T'HH:mm:ssXXX").alias('event_timestamp_utc'),
                     F.col('event_date_utc').cast('string'), F.col('price_decimal').cast('string'), *FLAGS)


def summary_expressions():
    purchase = F.col('event_eligible') & (F.col('event_type') == 'purchase')
    bad = F.col('price_decimal').isNull() | F.col('price_negative')
    count_if = lambda condition, name: F.sum(F.when(condition, 1).otherwise(0)).cast('long').alias(name)
    aggregates = [F.count('*').alias('record_count'),
                  F.countDistinct('user_id').alias('raw_users'),
                  F.countDistinct(F.when(F.col('event_eligible'), F.col('user_id'))).alias('users'),
                  F.countDistinct(F.when(purchase, F.col('user_id'))).alias('buyers'),
                  count_if(purchase, 'purchase_events'),
                  count_if(purchase & bad, 'purchase_price_bad_eligible'),
                  count_if((F.col('event_type') == 'purchase') & bad, 'purchase_price_bad_all'),
                  F.sum(F.when(F.col('amount_eligible'), F.col('price_decimal'))).alias('purchase_amount'),
                  F.min('event_timestamp_utc').alias('time_min'), F.max('event_timestamp_utc').alias('time_max')]
    aggregates += [count_if(F.col(name), name) for name in FLAGS]
    aggregates += [count_if(F.col('event_type') == name, 'behavior_' + name) for name in ALLOWED]
    aggregates += [count_if(F.col('event_type_unknown'), 'behavior___unknown__')]
    aggregates += [count_if(F.col('price_zero') & (F.col('event_type') == name), 'zero_' + name) for name in ALLOWED]
    aggregates += [count_if(F.col('price_zero') & F.col('event_type_unknown'), 'zero___unknown__')]
    return aggregates


def finish_summary(result):
    result['zero_by_behavior'] = {name: result.pop('zero_' + name) for name in (*ALLOWED, '__unknown__')}
    result['flags'] = {name: result.pop(name) for name in FLAGS}
    result['behaviors'] = {name: result.pop('behavior_' + name) for name in (*ALLOWED, '__unknown__')}
    result['behaviors'] = {name: count for name, count in result['behaviors'].items() if count}
    for name in ('time_min', 'time_max'):
        if result[name] is not None:
            result[name] = result[name].replace(tzinfo=timezone.utc).isoformat(timespec='seconds')
    purchases = result['purchase_events']; bad_count = result['purchase_price_bad_eligible']
    result['amount_status'] = 'no_purchases' if not purchases else 'complete_observed' if not bad_count else 'partial_observed' if result['flags']['amount_eligible'] else 'unknown'
    result['purchase_amount'] = format(result['purchase_amount'], '.2f') if result['purchase_amount'] is not None else '0.00' if not purchases else None
    return result


def summary(df):
    # Exactly one aggregate row, never a fact-table collection.
    return finish_summary(df.agg(*summary_expressions()).first().asDict())


def daily_summary(df):
    rows = df.groupBy('event_date_utc').agg(*summary_expressions()).limit(65).collect()
    if len(rows) > 64:
        raise ValueError('more than 64 date aggregates; stop rather than truncate')
    result = {}
    for row in rows:
        item = row.asDict()
        date = item.pop('event_date_utc')
        result[date.isoformat() if date else '__invalid_time__'] = finish_summary(item)
    return result


def schema():
    return T.StructType([T.StructField(name, T.StringType()) for name in HEADER]
                        + [T.StructField('event_timestamp_utc', T.TimestampType()),
                           T.StructField('event_date_utc', T.DateType()),
                           T.StructField('price_decimal', T.DecimalType(18, 2))]
                        + [T.StructField(name, T.BooleanType()) for name in FLAGS]
                        + [T.StructField(name, T.TimestampType() if name == 'parsed_at_utc' else T.StringType()) for name in PROVENANCE])


def worker_info(_):
    import os, sys
    return (sys.executable, sys.prefix, os.environ.get('PYSPARK_PYTHON'))


def main():
    args_parser = argparse.ArgumentParser()
    args_parser.add_argument('--config', required=True)
    args_parser.add_argument('--runtime-config', required=True)
    args_parser.add_argument('--run-dir', required=True)
    args_parser.add_argument('--compare-run')
    args_parser.add_argument('--regression-against')
    args = args_parser.parse_args()
    cfg = load_events_config(args.config, ROOT)
    runtime = load_config(args.runtime_config, ROOT)
    run = Path(args.run_dir); stage = run / 'staging'
    expected_summary = json.loads((stage / 'expected_summary.json').read_text())
    receipt = {'status': 'running', 'checks': {}, 'spark_stopped': False}
    spark = None; started = time.monotonic()
    def check(name, expected, actual):
        receipt['checks'][name] = {'expected': expected, 'actual': actual, 'pass': expected == actual}
        if expected != actual:
            raise AssertionError(name)
    try:
        spark = SparkSession.builder.appName('T1.1-authorized-candidate-parsing').getOrCreate()
        spark.sparkContext.setLogLevel('WARN')
        sc = spark.sparkContext
        check('python_version', [3, 11], list(sys.version_info[:2]))
        check('driver_venv', str(ROOT / '.venv'), sys.prefix)
        check('pyspark', '3.5.8', pyspark.__version__)
        check('spark_jvm', '3.5.8', spark.version)
        java_version = sc._jvm.java.lang.System.getProperty('java.version')
        check('java_major', '17', java_version.split('.')[0])
        check('master', 'local[4]', sc.master)
        check('driver_memory', '4g', sc.getConf().get('spark.driver.memory'))
        check('jvm_max_heap_bytes', 4 * 1024**3, sc._jvm.java.lang.Runtime.getRuntime().maxMemory())
        check('utc', 'UTC', spark.conf.get('spark.sql.session.timeZone'))
        check('shuffle', '32', spark.conf.get('spark.sql.shuffle.partitions'))
        check('catalog', 'in-memory', spark.conf.get('spark.sql.catalogImplementation'))
        workers = sc.parallelize([0, 1], 2).map(worker_info).collect()  # Bounded synthetic worker probes, not facts.
        check('worker_python', True, all(Path(a).parent.resolve() == runtime.python_executable.parent.resolve() and b == str(ROOT / '.venv') and c == str(runtime.python_executable) for a, b, c in workers))
        receipt['versions'] = dict(python=sys.version.split()[0], java=java_version, pyspark=pyspark.__version__, spark_jvm=spark.version)
        raw_schema = T.StructType([T.StructField(name, T.StringType()) for name in HEADER])
        raw = (spark.read.schema(raw_schema).option('header', True).option('enforceSchema', False)
               .option('lineSep', csv_line_separator(cfg['input_path']))
               .option('multiLine', True).option('mode', 'FAILFAST').option('quote', '"')
               .option('escape', '"').option('unescapedQuoteHandling', 'RAISE_ERROR')
               .option('ignoreLeadingWhiteSpace', False).option('ignoreTrailingWhiteSpace', False)
               .option('nullValue', '').option('emptyValue', '').csv(str(cfg['input_path'])))
        fact = transform(raw, cfg, run.name)
        fact.write.mode('errorifexists').parquet(str(stage / 'fact_events'))
        readback = spark.read.parquet(str(stage / 'fact_events'))
        check('schema', schema().simpleString(), readback.schema.simpleString())
        check('rows', cfg['expected_records'], readback.count())
        expected_schema = T.StructType([T.StructField(name, T.StringType()) for name in HEADER + DERIVED]
                                       + [T.StructField(name, T.BooleanType()) for name in FLAGS])
        expected = spark.read.schema(expected_schema).json(str(stage / 'expected_rows.jsonl'))
        # Canonical UTC strings use the same written offset, not a numeric tolerance.
        actual = canonical(readback).withColumn('event_timestamp_utc', F.regexp_replace('event_timestamp_utc', 'Z$', '+00:00'))
        check('expected_minus_actual_multiset', 0, expected.exceptAll(actual).count())
        check('actual_minus_expected_multiset', 0, actual.exceptAll(expected).count())
        print(json.dumps({'phase': 'all_record_multisets_verified', 'records': cfg['expected_records']}), flush=True)
        actual_summary = summary(readback)
        for key, value in expected_summary.items():
            check('summary_' + key, value, actual_summary[key])
        actual_daily = daily_summary(readback)
        expected_daily = json.loads((stage / 'expected_daily.json').read_text())
        check('daily_bucket_keys', sorted(expected_daily), sorted(actual_daily))
        for date, expected_day in expected_daily.items():
            check('daily_' + date, expected_day, actual_daily[date])
        if cfg['kind'] == 'user_sample_candidate':
            import csv
            with (ROOT / 'reports/sample_daily_coverage.csv').open() as stream:
                coverage = {row['utc_date']: int(row['event_records']) for row in csv.DictReader(stream)}
            check('registered_daily_coverage', coverage, {k: v['record_count'] for k, v in actual_daily.items()})
            check('registered_raw_users', 151121, actual_summary['raw_users'])
            check('registered_behaviors', {'view': 2030590, 'cart': 46472, 'purchase': 37019}, actual_summary['behaviors'])
        if args.regression_against:
            old = Path(args.regression_against) / 'complete'
            old_receipt = json.loads((old / 'validation.json').read_text())
            for key, expected_value in old_receipt['summary'].items():
                check('historical_' + key, expected_value, actual_summary[key])
            columns = [name for name in readback.columns if name not in ('run_id', 'parsed_at_utc', 'contract_version')]
            old_fact = spark.read.parquet(str(old / 'fact_events')).select(*columns)
            check('historical_old_minus_new', 0, old_fact.exceptAll(readback.select(*columns)).count())
            check('historical_new_minus_old', 0, readback.select(*columns).exceptAll(old_fact).count())
        check('input_sha256_after', cfg['input_sha256'], sha256(cfg['input_path']))
        if args.compare_run:
            previous = Path(args.compare_run) / 'complete'
            previous_receipt = json.loads((previous / 'validation.json').read_text())
            check('previous_run_status', 'passed', previous_receipt['status'])
            columns = [name for name in readback.columns if name not in ('run_id', 'parsed_at_utc')]
            before = spark.read.parquet(str(previous / 'fact_events')).select(*columns)
            after = readback.select(*columns)
            check('rerun_previous_minus_current', 0, before.exceptAll(after).count())
            check('rerun_current_minus_previous', 0, after.exceptAll(before).count())
            check('rerun_summary', previous_receipt['summary'], actual_summary)
            check('rerun_daily_summary', previous_receipt['daily_summary'], actual_daily)
        receipt.update(status='passed', summary=actual_summary, daily_summary=actual_daily, schema=schema().jsonValue(), contract_version=CONTRACT)
    except BaseException as exc:
        receipt.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
        raise
    finally:
        try:
            if spark:
                spark.stop(); receipt['spark_stopped'] = True
        finally:
            receipt['spark_seconds'] = round(time.monotonic() - started, 3)
            (stage / 'validation.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
