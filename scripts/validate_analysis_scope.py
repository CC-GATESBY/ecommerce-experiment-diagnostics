"""Freeze the October scope using receipts, file metadata and bounded daily summaries."""
import argparse
import csv
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
import shutil
import sys
import time
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.metric_snapshot import TABLES, digest, require, select_snapshot

VERSION = 'rees46_oct_user5_analysis_v1'
BINDING = dict(source_id='rees46_multicategory_2019_oct',
    scope_id='rees46_2019_oct_user5_fedd938409b5f836_20260916_v1',
    series_id='rees46_fixed_users_20260916_v1',
    candidate_sha256='5bfc34f9c683a81ecb5eef6853a62ed454a76eca3244c9b7d80a426b8100055b',
    fact_run='month-v101-01', metric_run='metrics-month-01', crosscheck_run='crosscheck-month-01',
    parsing_contract='rees46-events-v1.0.1', metric_version='rees46-metrics-v1',
    date_policy='rees46-date-quality-v1', brand_mapping='rees46-brand-oct01-07-top200-v1',
    duplicate_policy='baseline_keep_all')


def utc(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value), 'explicit canonical UTC required')
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def window(values):
    start, end = utc(values['start_inclusive']), utc(values['end_exclusive'])
    require(start < end and start.time().isoformat() == end.time().isoformat() == '00:00:00', 'invalid complete-day half-open window')
    return start, end


def dates_between(start, end):
    return [(start.date() + timedelta(days=i)).isoformat() for i in range((end-start).days)]


def validate_scope(cfg):
    require(cfg['analysis_scope_version'] == VERSION and cfg['binding'] == BINDING, 'unapproved scope/run/version')
    require(cfg['approval'] == 'october_first_edition_scope_only', 'scope-only approval required')
    obs = cfg['observation']; start, end = window(obs)
    require(obs['timezone'] == 'UTC' and obs['interval'] == '[)', 'UTC half-open interval required')
    require((start.isoformat(), end.isoformat()) == ('2019-10-01T00:00:00+00:00', '2019-11-01T00:00:00+00:00'), 'October observation required')
    observed = cfg['observed_event_range']
    require(start <= utc(observed['min']) <= utc(observed['max']) < end, 'observed events outside observation')
    use = cfg['uses']; require(set(use) == {'descriptive', 'funnel', 'history', 'experiment'}, 'unknown use')
    require(use['descriptive']['window'] == 'observation' and use['descriptive']['quality_purposes'] == ['count','amount'], 'descriptive scope mismatch')
    f = use['funnel']; fs, fe = window(f)
    require(type(f['max_window_hours']) is int and f['max_window_hours'] == 24 and f['result_window'] == 'observation', '24 hour rule required')
    require(fs == start and fe == end-timedelta(hours=24), 'funnel start boundary mismatch')
    h = use['history']
    require(h['lookback_offsets_days'] == [7,14,21,28] and type(h['min_history_points']) is int and h['min_history_points'] == 3, 'history policy frozen')
    require(h['quality_purposes'] == ['count','amount'] and h['success_status'] == 'history_available_not_evaluated', 'history is not a detector release')
    pre = window(use['experiment']['pre']); out = window(use['experiment']['outcome'])
    require(start <= pre[0] < pre[1] <= out[0] < out[1] <= end, 'experiment overlap or outside observation')
    require(pre == (start, utc('2019-10-15T00:00:00Z')) and out == (pre[1], utc('2019-10-29T00:00:00Z')), 'experiment windows frozen')
    s = cfg['sampling']
    require(s['algorithm_version'] == 'rees46-user-sample-v1' and s['seed'] == '20260916' and s['target_user_probability'] == 0.05
            and s['payload_prefix'] == 'rees46-user-sample-v1|20260916|' and s['threshold_uint64'] == (5*2**64)//100, 'sampling rule mismatch')
    return dates_between(start, end)


def validate_request(cfg, dates, purpose):
    allowed = validate_scope(cfg)
    require(isinstance(dates, list) and dates and len(dates) == len(set(dates)), 'nonempty unique dates required')
    require(purpose in ('count','amount','funnel_start'), 'unknown purpose')
    if purpose == 'funnel_start':allowed = dates_between(*window(cfg['uses']['funnel']))
    require(all(type(d) is str and d in allowed for d in dates), 'request outside approved window')
    return dates


def history_readiness(cfg, daily):
    dates = validate_scope(cfg); known = {}
    for r in daily:
        d = r['utc_date']; require(d in dates and d not in known, 'duplicate or out-of-range quality date')
        require(type(r['count_allowed']) is bool and type(r['amount_allowed']) is bool, 'quality flags must be boolean')
        known[d] = r
    def usable(d, purpose):
        r = known.get(d)
        return bool(r and r['count_allowed'] and (purpose == 'count' or r['amount_allowed']))
    result = []
    for purpose in cfg['uses']['history']['quality_purposes']:
        for d in dates:
            want = [(date.fromisoformat(d)-timedelta(days=n)).isoformat() for n in cfg['uses']['history']['lookback_offsets_days']]
            available = [x for x in want if usable(x,purpose)]
            reasons = [('outside_observation:' if x not in dates else 'missing_date:' if x not in known else 'quality_blocked:')+x for x in want if x not in available]
            current = usable(d, purpose); meets = len(available) >= cfg['uses']['history']['min_history_points']
            status = 'current_date_unavailable' if not current else 'history_available_not_evaluated' if meets else 'insufficient_history'
            if not current:reasons.append('current_date_missing_or_blocked')
            result.append(dict(utc_date=d, purpose=purpose, history_dates=available, history_count=len(available),
                meets_min3=meets, meets_full4=len(available)==4, status=status, reason=';'.join(reasons) or 'history_quantity_only'))
    return result


def verify_evidence(cfg, descriptor, fact_launch, fact, metrics, crosscheck):
    validate_scope(cfg); b = cfg['binding']
    for key, want in dict(source_id=b['source_id'], scope_id=b['scope_id'], series_id=b['series_id'],
        input_sha256=b['candidate_sha256'], contract_version=b['parsing_contract'], run_id=b['fact_run'], kind='user_sample_candidate').items():
        require(descriptor.get(key) == want, 'fact descriptor mismatch: '+key)
    require(fact_launch.get('status') == fact.get('status') == metrics.get('status') == crosscheck.get('status') == 'passed', 'incomplete evidence')
    require(fact.get('spark_stopped') is True and metrics.get('spark_stopped') is True and crosscheck.get('passed') is True, 'completion verification missing')
    for proof in (fact,metrics):require(proof.get('checks') and all(c.get('pass') is True for c in proof['checks'].values()), 'failed checks')
    for key in ('scope_id','input_sha256','run_id','contract_version'):
        require(fact_launch.get(key) == descriptor[key], 'fact launch identity mismatch')
    expected = dict(source_id=b['source_id'], source_run=b['fact_run'], input_sha256=b['candidate_sha256'],
        contract_version=b['parsing_contract'], metric_version=b['metric_version'], date_policy_version=b['date_policy'], brand_mapping_version=b['brand_mapping'],
        observation_start_utc='2019-10-01', observation_end_exclusive_utc='2019-11-01')
    for k,v in expected.items():require(metrics['lineage'].get(k) == v, 'metric lineage mismatch: '+k)
    for k,v in dict(scope_id=b['scope_id'], input_sha256=b['candidate_sha256'], source_run=b['fact_run'], metric_run=b['metric_run']).items():
        require(crosscheck.get(k) == v, 'crosscheck identity mismatch: '+k)
    require(set(crosscheck['tables']) == set(TABLES), 'missing independently compared table')
    require(crosscheck['fields'] and all(x['differences'] == 0 for x in crosscheck['fields']), 'crosscheck field mismatch')
    for name, t in crosscheck['tables'].items():
        require(t['pass'] is True and t['expected_rows'] == t['actual_rows'], 'crosscheck table failed')
        if name != 'brand_mapping':require(t['actual_rows'] == metrics['tables'][name]['rows'], 'row receipt mismatch')


def canonical_snapshot(root, cfg, path):
    validate_scope(cfg)
    require(isinstance(path,str) and Path(path).name == cfg['binding']['metric_run'], 'canonical single metric run required')
    return select_snapshot(root,path,scope_id=cfg['binding']['scope_id'],source_run=cfg['binding']['fact_run'])


def local_path(value):
    require(isinstance(value,str) and value and not any(x in value for x in '*?['), 'explicit local path required')
    p = (ROOT/value).resolve(); require(p.is_relative_to(ROOT) and p != ROOT, 'path outside project')
    return p


def read_json(path):return json.loads(Path(path).read_text())


def layout(folder):
    files = sorted(p for p in folder.rglob('*') if p.is_file())
    parquet = [p for p in files if p.suffix == '.parquet']
    return dict(parquet_files=len(parquet), parquet_bytes=sum(p.stat().st_size for p in parquet),
        all_files=len(files), directory_bytes=sum(p.stat().st_size for p in files),
        physical_date_partitioned=any('=' in p and ('date' in p or 'dt=' in p) for f in parquet for p in f.relative_to(folder).parts[:-1]),
        flat_parquet_layout=all(p.parent == folder for p in parquet))


def run(scope_path, local_config, run_dir):
    started = time.monotonic(); cfg = yaml.safe_load(Path(scope_path).read_text()); days = validate_scope(cfg)
    output = local_path(run_dir); require(output.is_relative_to(ROOT/'.local/t15'), 'output outside T1.5')
    require(shutil.disk_usage(ROOT).free >= 150*1024**3, 'disk reserve insufficient')
    output.mkdir(parents=True,exist_ok=False); stage = output/'staging'; stage.mkdir()
    result = dict(status='failed',analysis_scope_version=VERSION); evidence_hashes = {}; protected_stat = {}
    def load(path):
        path=Path(path); evidence_hashes[str(path)] = digest(path); return read_json(path)
    def check_budget():
        n=sum(p.stat().st_size for p in (ROOT/'.local/t15').rglob('*') if p.is_file())
        free=shutil.disk_usage(ROOT).free
        require(n <= 512*1024**2 and free >= 150*1024**3, 'T1.5 resource budget exceeded')
        return dict(new_local_bytes=n,free_bytes=free,peak_memory='not_measured')
    try:
        lc=load(local_config); require(set(lc)=={'metrics_config','crosscheck_config','crosscheck_receipt'},'local binding fields mismatch')
        mc=load(local_path(lc['metrics_config'])); cc=load(local_path(lc['crosscheck_config']))
        require(mc['registry_path']==cc['registry_path'] and mc['series_id']==cfg['binding']['series_id']==cc['series_id'], 'local series/registry mismatch')
        require(mc['source_run']==cc['source_run']==BINDING['fact_run'] and mc['scope_id']==cc['scope_id']==BINDING['scope_id'], 'local scope/run mismatch')
        require(mc['observation_dates']==mc['output_dates']==days,'metric output dates mismatch')
        cross_path=local_path(lc['crosscheck_receipt'])
        require(cross_path.parts[-3:]==(BINDING['crosscheck_run'],'complete','validation.json') and not (cross_path.parent.parent/'staging').exists(), 'canonical complete crosscheck required')
        cross=load(cross_path); reg=load(local_path(mc['registry_path']))
        require(len(reg['batches'])==1, 'ambiguous registered input'); batch=reg['batches'][0]; descriptor=batch['descriptor']
        fact_run=local_path(descriptor['run_path'])
        require(fact_run.name==BINDING['fact_run'] and not (fact_run/'staging').exists(), 'canonical complete fact required')
        fl=load(fact_run/'launch.json'); fv=load(fact_run/'complete/validation.json')
        snap=canonical_snapshot(ROOT,cfg,cc['metrics_run']); mv=snap['proof']
        load(snap['run']/'complete/validation.json'); ml=load(snap['run']/'launch.json')
        verify_evidence(cfg,descriptor,fl,fv,mv,cross)
        for p,meta in snap['inventory'].items():require(cross['protected_hashes'].get(p)==meta['sha256'], 'selected metric changed since crosscheck')
        for p,sha in batch['evidence'].items():
            file=local_path(p); require(file.stat().st_size<2*1024**2 and digest(file)==sha,'bound receipt changed'); evidence_hashes[str(file)]=sha
        for item in batch['inventory']:
            p=local_path(item['path']); require(p.stat().st_size==item['bytes'],'fact size changed')
        manifest=load(ROOT/'data/manifest.json')
        candidates=[x for x in manifest['user_sample_candidates'] if x['scope_id']==BINDING['scope_id'] and x['sample']['sha256']==BINDING['candidate_sha256']]
        require(len(candidates)==1 and candidates[0]['status']=='validated' and candidates[0]['kind']=='user_sample_candidate','candidate registration invalid')
        candidate=candidates[0]; source=local_path(cc['candidate_path'])
        require(source==local_path(candidate['sample']['local_relative_path']) and source.stat().st_size==candidate['sample']['bytes'],'candidate metadata mismatch')
        sampling=load(source.parent/'receipt.json'); sample=sampling['sample']
        require(sampling['status']=='validated' and sampling['scope_id']==BINDING['scope_id'] and sample['sha256']==BINDING['candidate_sha256'],'sampling receipt mismatch')
        for a,b in [('algorithm_version','algorithm_version'),('seed','seed'),('selection_payload_prefix','payload_prefix'),('selection_threshold_uint64','threshold_uint64')]:
            require(sampling[a]==cfg['sampling'][b],'sampling configuration mismatch')
        require(sampling['target_user_sampling_percent']/100==cfg['sampling']['target_user_probability'],'sampling probability mismatch')
        observed={k:v.replace('+00:00','Z') for k,v in sample['profile']['time_range_utc'].items()}
        require(all(cfg['observed_event_range'][k]==v for k,v in observed.items()),'observed range mismatch')
        require(sample['profile']['record_count']==descriptor['expected_records']==fv['summary']['record_count']==cross['input_records'], 'input scale mismatch')
        require(sample['distinct_user_count']==fv['summary']['raw_users']==cross['first_seen_rows'],'user scale mismatch')
        gates=list(batch['gates'].values()); require(sorted(batch['gates'])==days,'registered date coverage incomplete')
        require(all(g['scope_id']==BINDING['scope_id'] and g['source_run']==BINDING['fact_run'] and g['policy_version']==BINDING['date_policy'] for g in gates),'quality identity mismatch')
        for proof in (mv,cross):
            require(len(proof['daily'])==31 and sorted(r['utc_date'] for r in proof['daily'])==days,'daily evidence incomplete')
            for row in proof['daily']:
                g=batch['gates'][row['utc_date']]
                require(row['scope_id']==BINDING['scope_id'] and all(row[k]==g[k] for k in ('count_allowed','amount_allowed','amount_status')), 'daily gate mismatch')
                require(row['event_records']==g['record_count'],'daily count evidence mismatch')
        require(all(r['quality_and_history_pass'] is True for r in cross['daily']), 'independent daily check failed')
        history=history_readiness(cfg,gates)
        # Only the 31-row table is opened as tabular data. No fact/user table is queried.
        import duckdb
        conn=duckdb.connect(config={'threads':'1','memory_limit':'256MB','autoinstall_known_extensions':'false','autoload_known_extensions':'false'})
        try:
            data=conn.read_parquet(snap['files']['agg_daily_metrics'],hive_partitioning=False).project('scope_id,utc_date,count_allowed,amount_allowed,event_records').limit(32).fetchall()
            require(len(data)==31,'daily Parquet row count mismatch')
            actual={str(r[1]):r for r in data}; require(sorted(actual)==days,'daily Parquet dates mismatch')
            for d,r in actual.items():
                g=batch['gates'][d]; require((r[0],r[2],r[3],r[4])==(BINDING['scope_id'],g['count_allowed'],g['amount_allowed'],g['record_count']),'daily Parquet scope/gate mismatch')
        finally:conn.close()
        require(all(g['count_allowed'] and g['amount_allowed'] for g in gates),'declared 31-day descriptive use blocked')
        layouts={n:layout(snap['run']/'complete/metrics'/n) for n in TABLES}
        layouts['fact_events']=layout(fact_run/'complete/fact_events')
        require(layouts['fact_events']['parquet_files']==len(batch['inventory']) and layouts['fact_events']['parquet_bytes']==sum(x['bytes'] for x in batch['inventory']), 'fact inventory layout mismatch')
        for p in [source,*(local_path(x['path']) for x in batch['inventory']),*(Path(p) for p in snap['inventory'])]:
            s=p.stat(); protected_stat[str(p)]=[s.st_size,s.st_mtime_ns,s.st_ino]
        with (stage/'history_readiness.csv').open('x',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(history[0]),lineterminator='\n');w.writeheader()
            for row in history:w.writerow(dict(row,history_dates=json.dumps(row['history_dates'],separators=(',',':'))))
        result.update(status='passed',binding=cfg['binding'],observation=cfg['observation'],observed_event_range=observed,
            history_summary={p:dict(meets_min3=sum(r['meets_min3'] for r in history if r['purpose']==p),meets_full4=sum(r['meets_full4'] for r in history if r['purpose']==p)) for p in ('count','amount')},
            allowed_dates=days,layouts=layouts,metric_rows={n:t['rows'] for n,t in mv['tables'].items()},
            input=dict(records=sample['profile']['record_count'],bytes=sample['bytes'],users=sample['distinct_user_count'],kind='user_sample_candidate',actual_event_extraction_ratio=sample['actual_event_extraction_ratio']),
            stages=dict(sampling=dict(run_id=sampling['run_id'],source=sampling['source_scan'],output_bytes=sample['bytes'],timing=sampling['timing_seconds'],resources=sampling['resources']),
                fact=dict(run_id=BINDING['fact_run'],input_bytes=fl['input_bytes'],records=fv['summary']['record_count'],elapsed_seconds=fl['elapsed_seconds'],spark_seconds=fv['spark_seconds'],resources=fl['resources'],memory=fl['memory']),
                metrics=dict(run_id=BINDING['metric_run'],elapsed_seconds=ml['elapsed_seconds'],work_seconds=mv['elapsed_seconds'],resources=ml['resources']),
                crosscheck=dict(run_id=BINDING['crosscheck_run'],elapsed_seconds=cross['elapsed_seconds'],resources=cross['resources'])),
            selected_metric_files=snap['inventory'],fact_inventory=batch['inventory'],evidence_hashes=evidence_hashes,
            operations=dict(spark_started=False,csv_content_read=False,fact_or_user_table_queried=False,daily_parquet_rows_read=31,full_hash_chain_recomputed=False))
        require(all(digest(p)==sha for p,sha in evidence_hashes.items()),'evidence changed during freeze')
        result['resources']=check_budget()
    except BaseException as exc:
        result.update(status='failed',error=type(exc).__name__+': '+str(exc));raise
    finally:
        result['elapsed_seconds']=round(time.monotonic()-started,3)
        result['code_sha256']=digest(Path(__file__)); result['scope_sha256']=digest(scope_path)
        with (stage/'etl_baseline.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
        if result['status']=='passed':stage.rename(output/'complete')
    print(json.dumps({k:result[k] for k in ('status','analysis_scope_version','history_summary','layouts','resources','elapsed_seconds')}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--scope',default='config/analysis_scope.yaml');parser.add_argument('--local-config',default='config/analysis_scope.local.json');parser.add_argument('--run-dir',required=True)
    args=parser.parse_args();run(args.scope,args.local_config,args.run_dir)
