"""T1.2 SQL quality checks, using the unchanged registered fact reader."""

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import csv
import hashlib
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
from etl.fact_registry import FactReader, inspect_batch, load_registry, require
from etl.resource_budget import directory_bytes
from scripts.project_config import load_config

POLICY = 'rees46-quality-v1'
HEAVY = 5000
METRICS = ('events', 'users', 'buyers', 'purchase_events', 'purchase_amount')
SCENARIOS = ('baseline_keep_all', 'hypothetical_one_per_duplicate_group', 'hypothetical_exclude_heavy_sessions')
CODE = ['scripts/run_quality.py', 'tests/test_quality.py', 'sql/quality/duplicate_candidates.sql',
        'sql/quality/session_profile.sql', 'reports/quality_policy.md', 'etl/fact_registry.py', 'etl/date_quality.py']


def json_ready(value):
    if isinstance(value, Decimal):
        return format(value, 'f')
    if isinstance(value, dict):
        return {k: json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(v) for v in value]
    return value


def code_hashes():
    return {p: sha256(ROOT / p) for p in CODE}


def queries(filename, threshold):
    require(type(threshold) is int and threshold > 0, 'invalid threshold')
    source = (ROOT / filename).read_text()
    chunks = re.split(r'^-- name: ([a-z_]+)\n', source, flags=re.M)
    require(not chunks[0].strip(), 'SQL requires named sections')
    return {chunks[i]: chunks[i+1].strip().rstrip(';').replace('__HEAVY_THRESHOLD__', str(threshold))
            for i in range(1, len(chunks), 2)}


def bounded(frame, limit):
    rows = frame.limit(limit + 1).collect()
    require(len(rows) <= limit, 'aggregate result exceeded bound; no truncation')
    return [r.asDict(recursive=True) for r in rows]


def sensitivity_rows(scenarios, dates):
    rows = []
    for scenario, values in scenarios.items():
        for period in ['__all__', *dates]:
            base = scenarios[SCENARIOS[0]][period]
            current = values.get(period, {key: Decimal('0.00') if key == 'purchase_amount' else 0 for key in base if key != 'period'})
            for metric in METRICS:
                expected = base[metric]; actual = current[metric]; delta = actual - expected
                ratio = None if expected == 0 else (Decimal(delta) / Decimal(expected)).quantize(Decimal('0.000000000001'))
                rows.append(dict(scenario=scenario, period=period, metric=metric, baseline=expected,
                                 value=actual, absolute_change=delta, relative_change=ratio,
                                 relative_change_reason='baseline_zero' if expected == 0 else 'defined',
                                 period_state='observed' if period in values else 'all_rows_removed_by_hypothesis'))
    return rows


def analyze(spark, fact, dates, *, threshold, synthetic=False):
    from pyspark import StorageLevel
    require((synthetic and threshold == 3) or (not synthetic and threshold == HEAVY), 'real threshold must stay 5000')
    dup = queries('sql/quality/duplicate_candidates.sql', threshold)
    ses = queries('sql/quality/session_profile.sql', threshold)
    caches = []; checks = {}
    def check(name, expected, actual):
        checks[name] = dict(expected=json_ready(expected), actual=json_ready(actual), **{'pass': expected == actual})
        require(expected == actual, name)
    def view(name, query, cache=False):
        frame = spark.sql(query)
        if cache:
            frame = frame.persist(StorageLevel.MEMORY_AND_DISK); caches.append(frame)
        frame.createOrReplaceTempView(name)
        return frame
    def measures(frame):
        frame.createOrReplaceTempView('q_measure_input')
        result = {x['period']: x for x in bounded(spark.sql(ses['measures']), 32)}
        if not result:
            # Spark GROUPING SETS can return no grand-total row on empty input.
            require(frame.count() == 0, 'missing aggregates for nonempty input')
            result['__all__'] = dict(period='__all__', events=0, users=0, buyers=0,
                purchase_events=0, purchase_amount=Decimal('0.00'), views=0, carts=0, removes=0, missing_session_events=0)
        return result
    try:
        fact.createOrReplaceTempView('q_input')
        baseline = measures(fact)
        check('baseline_dates', sorted(dates), sorted(set(baseline) - {'__all__'}))
        print(json.dumps({'phase': 'baseline', 'events': baseline['__all__']['events']}), flush=True)
        view('q_keys', dup['keys'])
        groups = view('q_duplicates', dup['normalized_groups'], True)
        raw_groups = view('q_raw_duplicates', dup['raw_groups'], True)
        profiles = view('q_sessions', ses['profiles'], True)
        for name, frame, key in [('candidate', groups, ['candidate_key']), ('raw', raw_groups, ['raw_key']),
                                  ('session', profiles, ['user_id', 'user_session'])]:
            check(name + '_keys_unique', 0, frame.groupBy(*key).count().where('count > 1').count())
        first_join = view('q_duplicate_labeled', dup['joined'])
        check('duplicate_join_conservation', baseline, measures(first_join))
        session_join = view('q_session_labeled', ses['session_only_joined'])
        check('session_join_conservation', baseline, measures(session_join))
        labeled = view('q_labeled', ses['joined'], True)
        check('both_joins_conservation', baseline, measures(labeled))
        check('all_events_have_candidate_group', 0, labeled.where('duplicate_group_size IS NULL').count())
        check('missing_session_has_no_shared_label', 0, labeled.where('session_missing AND session_events IS NOT NULL').count())
        print(json.dumps({'phase': 'joins_verified', 'periods': len(baseline)}), flush=True)
        duplicate_rows = []
        behaviors = ['__all__', 'view', 'cart', 'remove_from_cart', 'purchase']
        for kind, frame in [('normalized', groups), ('raw_exact', raw_groups)]:
            frame.createOrReplaceTempView('q_groups_for_summary')
            aggregate = {row['behavior']: row for row in bounded(spark.sql(dup['summary']), 5)}
            columns = ('duplicate_groups', 'involved_events', 'excess_events', 'involved_users',
                       'purchase_involved_events', 'purchase_excess_events', 'hypothetical_purchase_amount_reduction')
            for behavior in behaviors:
                row = aggregate.get(behavior, dict(behavior=behavior, **{c: Decimal('0.00') if c.endswith('reduction') else 0 for c in columns}))
                denominator = baseline['__all__']['events']
                row.update(key_type=kind, involved_event_share=Decimal(row['involved_events'])/denominator if denominator else None,
                           share_denominator='all_baseline_events')
                duplicate_rows.append(row)
        session = bounded(spark.sql(ses['summary']), 1)[0]
        session.update(missing_session_events=baseline['__all__']['missing_session_events'], heavy_threshold=threshold,
                       quantile_algorithm='Spark percentile_approx', quantile_accuracy=10000,
                       quantile_probabilities=[0.5, 0.9, 0.99])
        branches = {SCENARIOS[0]: labeled, SCENARIOS[1]: spark.sql(dup['one_per_group']), SCENARIOS[2]: spark.sql(ses['exclude_heavy'])}
        scenarios = {name: (baseline if name == SCENARIOS[0] else measures(frame)) for name, frame in branches.items()}
        normal = next(r for r in duplicate_rows if r['key_type'] == 'normalized' and r['behavior'] == '__all__')
        b = scenarios[SCENARIOS[0]]['__all__']; one = scenarios[SCENARIOS[1]]['__all__']; heavy = scenarios[SCENARIOS[2]]['__all__']
        check('B_event_reduction_equals_excess', normal['excess_events'], b['events']-one['events'])
        check('B_amount_reduction_matches_groups', normal['hypothetical_purchase_amount_reduction'], b['purchase_amount']-one['purchase_amount'])
        check('C_event_reduction_matches_sessions', session['heavy_events'], b['events']-heavy['events'])
        check('C_purchase_reduction_matches_sessions', session['heavy_purchase_events'], b['purchase_events']-heavy['purchase_events'])
        check('C_amount_reduction_matches_sessions', session['heavy_purchase_amount'], b['purchase_amount']-heavy['purchase_amount'])
        check('C_missing_sessions_retained', b['missing_session_events'], heavy['missing_session_events'])
        check('baseline_unchanged_after_hypotheses', baseline, measures(fact))
        return dict(duplicates=duplicate_rows, sessions=session, scenarios=scenarios,
                    sensitivity=sensitivity_rows(scenarios, dates), checks=checks,
                    caches='FactReader facts plus normalized/raw groups, session groups, joined labels; MEMORY_AND_DISK; all released',
                    full_user_or_session_collection=False)
    finally:
        for frame in reversed(caches):
            frame.unpersist(blocking=True)


def write_csv(path, rows, metadata=None):
    safe = [{**(metadata or {}), **json_ready(row)} for row in rows]
    for row in safe:
        for key, value in row.items():
            if isinstance(value, (list, dict)):
                row[key] = json.dumps(value, sort_keys=True)
    with Path(path).open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(safe[0])); writer.writeheader(); writer.writerows(safe)


def real_analysis(spark, config_path, stage):
    cfg = json.loads(Path(config_path).read_text())
    require(set(cfg) == {'registry_path', 'source_run', 'scope_id', 'series_id', 'dates', 'policy_version', 'heavy_threshold'}, 'config fields mismatch')
    require(cfg['source_run'] == 'month-v101-01' and cfg['scope_id'] == 'rees46_2019_oct_user5_fedd938409b5f836_20260916_v1'
            and cfg['series_id'] == 'rees46_fixed_users_20260916_v1' and cfg['dates'] == [f'2019-10-{d:02d}' for d in range(1,32)]
            and cfg['policy_version'] == POLICY and type(cfg['heavy_threshold']) is int and cfg['heavy_threshold'] == HEAVY, 'unauthorized real scope or threshold')
    entries = load_registry(ROOT, cfg['registry_path'])['batches']
    require(len(entries) == 1 and entries[0]['descriptor']['run_id'] == cfg['source_run'], 'exactly one canonical batch required')
    entry = entries[0]; require(inspect_batch(ROOT, entry['descriptor']) == entry, 'input evidence changed')
    paths = [ROOT / k for k in entry['evidence']] + [ROOT / x['path'] for x in entry['inventory']]
    paths += [ROOT / cfg['registry_path'], ROOT/'docs/event_parsing_contract.md', ROOT/'docs/date_quality_policy.md', ROOT/'reports/data_quality_daily.csv']
    before = {str(p): sha256(p) for p in paths}
    with FactReader(spark, ROOT, cfg['registry_path'], cfg['series_id']) as reader:
        reader.read(cfg['dates'], 'count', expected_scopes=[cfg['scope_id']])
        fact = reader.read(cfg['dates'], 'amount', expected_scopes=[cfg['scope_id']])
        result = analyze(spark, fact, cfg['dates'], threshold=HEAVY)
        require(reader.parquet_loads == 1, 'unexpected fact reload')
        expected = entry['summary']; actual = result['scenarios'][SCENARIOS[0]]['__all__']
        mapping = dict(events='record_count',users='users',buyers='buyers',purchase_events='purchase_events',purchase_amount='purchase_amount')
        for metric, old in mapping.items():
            want = Decimal(expected[old]) if metric == 'purchase_amount' else expected[old]
            require(actual[metric] == want, 'historical baseline mismatch: ' + metric)
        for day, old in entry['daily'].items():
            current = result['scenarios'][SCENARIOS[0]][day]
            for metric, key in mapping.items():
                require(current[metric] == (Decimal(old[key]) if metric == 'purchase_amount' else old[key]), 'historical daily mismatch')
        result['checks']['historical_baseline_month_and_all_dates'] = dict(expected='all five measures exactly equal',actual='all five measures exactly equal',**{'pass': True})
        reread = reader.read(cfg['dates'], 'count', expected_scopes=[cfg['scope_id']])
        require(reread.count() == expected['record_count'], 'controlled input changed after hypotheses')
        result['checks']['controlled_input_after_hypotheses'] = dict(expected=expected['record_count'],actual=expected['record_count'],**{'pass':True})
        result['parquet_loads'] = reader.parquet_loads
    require(before == {str(p): sha256(p) for p in paths}, 'protected facts or evidence changed')
    result['checks']['protected_input_sha256_unchanged'] = dict(expected=True,actual=True,**{'pass':True})
    metadata = {k: cfg[k] for k in ('source_run','scope_id','series_id','policy_version')}
    metadata.update(start_utc='2019-10-01',end_utc_inclusive='2019-10-31')
    write_csv(stage/'duplicate_summary.csv', result['duplicates'], metadata)
    write_csv(stage/'session_summary.csv', [result['sessions']], metadata)
    write_csv(stage/'quality_sensitivity.csv', result['sensitivity'], metadata)
    result.update(protected_file_hashes=before, config=cfg)
    return result


class Budget:
    def __init__(self, path):
        self.config = json.loads(Path(path).read_text()); self.peak=0; self.minimum=shutil.disk_usage(ROOT).free; self.samples=0
        require(set(self.config)=={'initial_bytes','max_new_bytes','minimum_free_bytes'} and 0 < self.config['max_new_bytes'] <= 5*1024**3
                and self.config['minimum_free_bytes'] >= 150*1024**3, 'invalid T1.2 budget')
    def check(self):
        total = sum(directory_bytes(ROOT/'.local'/name) for name in ('t11','t12'))
        used = max(0,total-self.config['initial_bytes']); free=shutil.disk_usage(ROOT).free
        self.peak=max(self.peak,used); self.minimum=min(self.minimum,free); self.samples+=1
        require(used<=self.config['max_new_bytes'] and free>=self.config['minimum_free_bytes'], 'T1.2 resource budget exceeded')
    def summary(self):
        return dict(self.config,sampled_peak_new_bytes=self.peak,minimum_free_observed_bytes=self.minimum,samples=self.samples,sampling='at most 2 seconds while Spark runs',peak_memory='not_measured')


def worker(args):
    from pyspark.sql import SparkSession
    stage=Path(args.run_dir).resolve()/'staging'; spark=None; result={'status':'failed'}; started=time.monotonic()
    try:
        spark=SparkSession.builder.appName('T1.2-repeated-candidates-and-sessions').getOrCreate(); spark.sparkContext.setLogLevel('WARN')
        require(spark.sparkContext.master=='local[4]' and spark.sparkContext.getConf().get('spark.driver.memory')=='4g'
                and spark.conf.get('spark.sql.session.timeZone')=='UTC' and spark.conf.get('spark.sql.catalogImplementation')=='in-memory', 'runtime mismatch')
        if args.stage=='synthetic':
            sys.path.insert(0,str(ROOT/'tests'))
            from test_quality import run_tests
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
        (stage/'validation.json').write_text(json.dumps(json_ready(result),indent=2)+'\n')


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
    run=Path(args.run_dir).resolve(); require(run.is_relative_to(ROOT/'.local/t12'),'output must be in .local/t12')
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
        require(code==0,'Spark quality checks failed; retained local logs')
        validation=json.loads((stage/'validation.json').read_text())
        require(validation['status']=='passed' and validation['spark_stopped'],'validation and normal stop required')
        budget.check();stage.rename(run/'complete');receipt['status']='passed'
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
