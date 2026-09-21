"""Fixed pre-period cohort from one verified user-day snapshot; no assignment."""
import argparse
import csv
from datetime import date, timedelta
from decimal import Decimal
import io
import json
from pathlib import Path
import re
import shutil
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import duckdb
import yaml
from etl.fact_registry import registered_batch_matches
from scripts.metric_snapshot import select_snapshot, digest, require
from scripts.validate_analysis_scope import validate_scope, verify_evidence

VERSION = 'rees46-pre-oct01-14-post-oct15-28-v1'
PRE, POST, END = '2019-10-01', '2019-10-15', '2019-10-29'
DAYS = [(date.fromisoformat(PRE)+timedelta(days=n)).isoformat() for n in range(28)]


def scalar(c, sql, args=None):
    return c.execute(sql, args or []).fetchone()[0]


def date_permissions(gates, scope):
    require(len(gates) == 28 and {g['utc_date'] for g in gates} == set(DAYS), 'missing/duplicate window date')
    require(all(g['scope_id'] == scope and type(g['count_allowed']) is bool
                and g['count_allowed'] and type(g['amount_allowed']) is bool for g in gates), 'scope/count gate blocked')
    return (all(g['amount_allowed'] for g in gates if g['utc_date'] < POST),
            all(g['amount_allowed'] for g in gates if g['utc_date'] >= POST))


def build(c, scope, gates):
    permissions = date_permissions(gates, scope)
    require(scalar(c, "SELECT count(*) FROM user_daily WHERE scope_id IS DISTINCT FROM ? OR user_id IS NULL OR trim(user_id)='' OR utc_date IS NULL", [scope]) == 0, 'invalid input identity')
    require(scalar(c, 'SELECT count(*)-count(DISTINCT (scope_id,utc_date,user_id)) FROM user_daily') == 0, 'duplicate user-day key')
    require(scalar(c, """SELECT count(*) FROM user_daily WHERE utc_date>=?::DATE AND utc_date<?::DATE AND
       (count_allowed IS DISTINCT FROM TRUE OR event_records IS NULL OR event_records<=0
        OR purchase_events IS NULL OR purchase_events<0 OR purchase_events>event_records
        OR purchase_amount_bad IS NULL OR purchase_amount_valid IS NULL
        OR purchase_amount_bad<0 OR purchase_amount_valid<0
        OR purchase_amount_bad+purchase_amount_valid<>purchase_events
        OR (amount_allowed AND (purchase_amount IS NULL OR purchase_amount_bad<>0)))""", [PRE, END]) == 0, 'invalid user-day quantities/quality')
    c.execute('CREATE TEMP TABLE cohort_gates(utc_date DATE,count_allowed BOOLEAN,amount_allowed BOOLEAN)')
    c.executemany('INSERT INTO cohort_gates VALUES (?,?,?)', [(g['utc_date'],g['count_allowed'],g['amount_allowed']) for g in gates])
    require(scalar(c, """SELECT count(*) FROM user_daily u JOIN cohort_gates g USING(utc_date)
       WHERE u.count_allowed IS DISTINCT FROM g.count_allowed OR u.amount_allowed IS DISTINCT FROM g.amount_allowed""") == 0, 'user-day/date permission mismatch')
    c.execute('CREATE TEMP TABLE cohort_parameters(scope_id VARCHAR,pre_start DATE,post_start DATE,post_end DATE,pre_amount_allowed BOOLEAN,post_amount_allowed BOOLEAN)')
    c.execute('INSERT INTO cohort_parameters VALUES (?,?,?,?,?,?)', [scope,PRE,POST,END,*permissions])
    c.execute((ROOT/'sql/exp/user_window.sql').read_text())


def summary(c):
    row = c.execute("""SELECT count(*) AS enrolled_users,
       coalesce(sum(post_active),0)::BIGINT AS returned_users,
       count(*)-coalesce(sum(post_active),0)::BIGINT AS not_returned_users,
       coalesce(sum(post_converted),0)::BIGINT AS post_buyers,
       coalesce(sum(post_purchase_events),0)::BIGINT AS post_purchase_events,
       count_if(post_purchase_amount IS NULL)::BIGINT AS amount_unknown_users,
       CASE WHEN count(*)>0 AND bool_and(post_purchase_amount IS NOT NULL)
            THEN sum(post_purchase_amount) ELSE NULL END AS post_purchase_amount
       FROM cohort""")
    result = dict(zip([x[0] for x in row.description], row.fetchone()))
    n, r, b = (result[k] for k in ('enrolled_users','returned_users','post_buyers'))
    result.update(cohort_buyer_rate=Decimal(b)/n if n else None,
                  returned_buyer_rate=Decimal(b)/r if r else None,
                  difference_percentage_points=(Decimal(b)/r-Decimal(b)/n)*100 if r and n else None,
                  post_amount_per_enrolled_user=result['post_purchase_amount']/n if n and result['post_purchase_amount'] is not None else None,
                  amount_status='empty_cohort' if not n else 'blocked_unknown' if result['amount_unknown_users'] else 'no_purchases' if not b else 'complete_observed')
    result['post_only_users'] = scalar(c, """SELECT count(DISTINCT user_id) FROM user_daily u
       WHERE utc_date>=?::DATE AND utc_date<?::DATE AND NOT EXISTS
       (SELECT 1 FROM user_daily p WHERE p.user_id=u.user_id AND p.scope_id=u.scope_id
        AND p.utc_date>=?::DATE AND p.utc_date<?::DATE)""", [POST,END,PRE,POST])
    return result


def validate(c):
    checks = {}
    def eq(name, expected, actual):
        checks[name] = dict(expected=expected,actual=actual,passed=expected == actual)
        require(expected == actual, 'cohort validation failed: '+name)
    n = scalar(c, 'SELECT count(*) FROM cohort')
    eq('primary_key_and_link_key', 0, scalar(c, 'SELECT count(*)-count(DISTINCT (scope_id,user_id))+count(*)-count(DISTINCT cohort_key) FROM cohort'))
    eq('membership_exact', 0, scalar(c, """WITH p AS (SELECT DISTINCT scope_id,user_id FROM user_daily WHERE utc_date>=?::DATE AND utc_date<?::DATE)
      SELECT (SELECT count(*) FROM (SELECT * FROM p EXCEPT SELECT scope_id,user_id FROM cohort))+
             (SELECT count(*) FROM (SELECT scope_id,user_id FROM cohort EXCEPT SELECT * FROM p))""", [PRE,POST]))
    s = summary(c)
    eq('return_conservation', n, s['returned_users']+s['not_returned_users'])
    eq('buyer_return_enrolment_order', True, s['post_buyers']<=s['returned_users']<=n)
    eq('inactive_zero_counts', 0, scalar(c, 'SELECT count(*) FROM cohort WHERE post_active=0 AND (post_converted<>0 OR post_purchase_events<>0 OR post_event_records<>0)'))
    # Independent semi-join reference: do not sum the production cohort for expected values.
    c.execute("""CREATE TEMP VIEW independent_post AS SELECT u.* FROM user_daily u
       WHERE utc_date>=DATE '2019-10-15' AND utc_date<DATE '2019-10-29' AND user_id IN
       (SELECT DISTINCT user_id FROM user_daily WHERE utc_date>=DATE '2019-10-01' AND utc_date<DATE '2019-10-15')""")
    for field, query in [('returned_users','count(DISTINCT user_id)'),
                         ('post_buyers',"count(DISTINCT CASE WHEN purchase_events>0 THEN user_id END)"),
                         ('post_purchase_events','coalesce(sum(purchase_events),0)')]:
        eq('independent_'+field, scalar(c, 'SELECT '+query+' FROM independent_post'), s[field])
    for prefix, table in [('pre',"(SELECT * FROM user_daily WHERE utc_date>=DATE '2019-10-01' AND utc_date<DATE '2019-10-15')"),('post','independent_post')]:
        eq(prefix+'_event_conservation', scalar(c,'SELECT coalesce(sum(event_records),0) FROM '+table), scalar(c,'SELECT coalesce(sum('+prefix+'_event_records),0) FROM cohort'))
        if scalar(c, 'SELECT count(*) FROM cohort WHERE '+prefix+'_purchase_amount IS NULL') == 0:
            eq(prefix+'_amount_exact', scalar(c,'SELECT coalesce(sum(purchase_amount),0)::DECIMAL(38,2) FROM '+table),
               scalar(c,'SELECT coalesce(sum('+prefix+'_purchase_amount),0)::DECIMAL(38,2) FROM cohort'))
    return checks


def export(c, folder):
    folder.mkdir(exist_ok=False)
    selections = {'identity':'cohort_key,scope_id,user_id', 'values':'* EXCLUDE(user_id)'}
    checks = {}
    for name, cols in selections.items():
        path = folder/(name+'.parquet')
        c.execute(f'COPY (SELECT {cols} FROM cohort ORDER BY cohort_key) TO ? (FORMAT PARQUET,COMPRESSION ZSTD)', [str(path)])
        c.read_parquet(str(path)).create_view('read_'+name)
        expected_schema=[r[:2] for r in c.execute(f'DESCRIBE SELECT {cols} FROM cohort').fetchall()]
        actual_schema=[r[:2] for r in c.execute('DESCRIBE read_'+name).fetchall()]
        require(expected_schema==actual_schema,'Parquet schema mismatch')
        for direction, left, right in [('missing',f'SELECT {cols} FROM cohort','SELECT * FROM read_'+name),
                                      ('extra','SELECT * FROM read_'+name,f'SELECT {cols} FROM cohort')]:
            diff = scalar(c,f'SELECT count(*) FROM ({left} EXCEPT ALL {right})')
            require(diff == 0, 'Parquet roundtrip mismatch')
            checks[name+'_'+direction] = diff
    require(scalar(c,'SELECT count(*) FROM read_identity JOIN read_values USING(cohort_key,scope_id)') == scalar(c,'SELECT count(*) FROM cohort'), 'identity/value join mismatch')
    checks['values_schema'] = c.execute('DESCRIBE read_values').fetchall()
    return checks


def main(run_id):
    require(re.fullmatch('[A-Za-z0-9_-]+',run_id) is not None, 'invalid run id')
    folder = ROOT/'.local/t51'; folder.mkdir(exist_ok=True)
    run = folder/run_id; run.mkdir(exist_ok=False); stage=run/'staging';stage.mkdir()
    started=time.monotonic(); c=None; protected={}; proof={'status':'failed','run_id':run_id}
    def budget():
        used=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file()); free=shutil.disk_usage(ROOT).free
        require(used+1024**2<=1024**3 and free>=150*1024**3,'T5.1 budget exceeded')
        return dict(new_local_bytes=used,free_bytes=free,peak_memory='not_measured')
    def local(path):
        p=(ROOT/path).resolve();require(p.is_relative_to(ROOT),'path outside project');return p
    def load(path):
        p=local(path);protected[str(p)]=digest(p);return json.loads(p.read_text())
    try:
        before=budget();log=io.StringIO()
        for path in ('config/analysis_scope.yaml','docs/metric_contract.md','docs/date_quality_policy.md',
                     'reports/next_experiment_design.md','reports/cohort_definition.md'):
            protected[str(ROOT/path)]=digest(ROOT/path)
        tests=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('tests.test_cohort'))
        (run/'tests.log').write_text(log.getvalue());require(tests.wasSuccessful(),'synthetic tests failed')
        cfg=yaml.safe_load((ROOT/'config/analysis_scope.yaml').read_text());validate_scope(cfg);b=cfg['binding']
        lc=load('config/analysis_scope.local.json');mc=load(lc['metrics_config']);cc=load(lc['crosscheck_config'])
        require(Path(cc['metrics_run']).name==b['metric_run']=='metrics-month-01','canonical metric required')
        require(mc['registry_path']==cc['registry_path'] and mc['scope_id']==cc['scope_id']==b['scope_id'] and
                mc['series_id']==cc['series_id']==b['series_id'] and mc['source_run']==cc['source_run']==b['fact_run'],'local binding mismatch')
        cross_path=local(lc['crosscheck_receipt']);require(cross_path.parts[-3:]==('crosscheck-month-01','complete','validation.json') and not (cross_path.parent.parent/'staging').exists(),'canonical crosscheck required')
        cross=load(cross_path);reg=load(mc['registry_path']);require(len(reg['batches'])==1,'ambiguous registry')
        batch=reg['batches'][0];d=batch['descriptor'];fr=local(d['run_path'])
        require(fr.name==b['fact_run'] and not (fr/'staging').exists(),'canonical fact receipt required')
        snap=select_snapshot(ROOT,cc['metrics_run'],scope_id=b['scope_id'],source_run=b['fact_run'],tables=('agg_user_daily',))
        metric=load(snap['run']/'complete/validation.json');load(snap['run']/'launch.json')
        verify_evidence(cfg,d,load(fr/'launch.json'),load(fr/'complete/validation.json'),metric,cross)
        current={p:digest(local(p)) for p in batch['evidence']}
        require(registered_batch_matches({'evidence':current},{'evidence':batch['evidence']},allow_criteo_manifest_extension=True),'bound evidence changed')
        protected.update({str(local(p)):sha for p,sha in current.items()})
        for p,meta in snap['inventory'].items():
            require(cross['protected_hashes'].get(p)==meta['sha256'],'metric changed after independent check');protected[p]=meta['sha256']
        fact_stats={str(local(x['path'])):[local(x['path']).stat().st_size,local(x['path']).stat().st_mtime_ns] for x in batch['inventory']}
        gates=[batch['gates'][day] for day in DAYS]
        for g in gates:
            require(g['scope_id']==b['scope_id'] and g['source_run']==b['fact_run'] and g['policy_version']==b['date_policy'],'gate identity mismatch')
            for rows in (metric['daily'],cross['daily']):
                matches=[r for r in rows if r['utc_date']==g['utc_date']];require(len(matches)==1,'missing/duplicate daily evidence')
                r=matches[0];require(all(r[k]==g[k] for k in ('scope_id','count_allowed','amount_allowed','amount_status')) and r['event_records']==g['record_count'],'gate/daily mismatch')
        c=duckdb.connect(config={'threads':'4','memory_limit':'512MB','autoload_known_extensions':'false','autoinstall_known_extensions':'false'})
        c.execute("SET TimeZone='UTC'; SET max_temp_directory_size='256MB'");c.execute('SET temp_directory=?',[str(stage/'temp')])
        c.read_parquet(snap['files']['agg_user_daily'],hive_partitioning=False).create_view('source_user_daily')
        require(scalar(c,'SELECT count(*) FROM source_user_daily')==metric['tables']['agg_user_daily']['rows'],'user-day row count changed')
        for k,v in dict(scope_id=b['scope_id'],**metric['lineage']).items():
            require(scalar(c,f'SELECT count(*) FROM source_user_daily WHERE "{k}" IS DISTINCT FROM ?',[v])==0,'user-day lineage mismatch '+k)
        c.execute('CREATE TEMP TABLE user_daily AS SELECT * FROM source_user_daily WHERE utc_date>=?::DATE AND utc_date<?::DATE',[PRE,END])
        # Date-level conservation validates that the selected window was not truncated.
        for day,n in c.execute('SELECT utc_date,sum(event_records) FROM user_daily GROUP BY utc_date ORDER BY utc_date LIMIT 29').fetchall():
            require(n==batch['gates'][str(day)]['record_count'],'user-day date count mismatch')
        require(scalar(c,'SELECT count(DISTINCT utc_date) FROM user_daily')==28,'user-day window date missing')
        build(c,b['scope_id'],gates);checks=validate(c);baseline=summary(c);budget()
        roundtrip=export(c,stage/'cohort');budget()
        baseline=dict(analysis_scope=cfg['analysis_scope_version'],scope_id=b['scope_id'],cohort_version=VERSION,
                      metric_run=b['metric_run'],fact_run=b['fact_run'],pre_start=PRE,pre_end_exclusive=POST,
                      post_start=POST,post_end_exclusive=END,**baseline)
        with (stage/'cohort_baseline.csv').open('x',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(baseline),lineterminator='\n');w.writeheader();w.writerow(baseline)
        c.close();c=None
        require(all(digest(Path(p))==sha for p,sha in protected.items()),'input/evidence changed')
        require(all([Path(p).stat().st_size,Path(p).stat().st_mtime_ns]==stat for p,stat in fact_stats.items()),'fact metadata changed')
        output_files={str(p.relative_to(stage)):dict(bytes=p.stat().st_size,sha256=digest(p)) for p in stage.rglob('*.parquet')}
        proof.update(status='passed',cohort_version=VERSION,baseline=baseline,checks=checks,roundtrip=roundtrip,
                     snapshot_inventory=snap['inventory'],protected_hashes=protected,fact_metadata=fact_stats,
                     gates=gates,outputs=output_files,resources_before=before,resources_after=budget(),
                     tests_passed=tests.testsRun,seconds=round(time.monotonic()-started,3),
                     versions=dict(python=sys.version.split()[0],duckdb=duckdb.__version__),
                     code_sha256={p:digest(ROOT/p) for p in ('scripts/build_cohort.py','sql/exp/user_window.sql','tests/test_cohort.py')})
        (stage/'validation.json').write_text(json.dumps(proof,indent=2,default=str))
        stage.rename(run/'complete')
        print(json.dumps({'status':'passed','baseline':baseline,'resources':proof['resources_after'],'seconds':proof['seconds']},default=str))
    except Exception as e:
        proof.update(error=type(e).__name__+': '+str(e))
        (run/'failure.json').write_text(json.dumps(proof,indent=2,default=str));raise
    finally:
        if c is not None:c.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',required=True)
    main(parser.parse_args().run_id)
