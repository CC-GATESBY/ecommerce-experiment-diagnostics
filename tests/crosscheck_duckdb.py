"""Independent CSV-to-metrics DuckDB verification; never executes Spark SQL."""
import argparse
import csv
from datetime import date,datetime
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.metric_snapshot import select_snapshot,digest,require

HEADER=['event_time','event_type','product_id','category_id','category_code','brand','price','user_id','user_session']
SCOPE='rees46_2019_oct_user5_fedd938409b5f836_20260916_v1'
SERIES='rees46_fixed_users_20260916_v1'
SHA='5bfc34f9c683a81ecb5eef6853a62ed454a76eca3244c9b7d80a426b8100055b'
VERSION='rees46-duckdb-crosscheck-v1'
KEYS={'dim_user_first_seen':['scope_id','user_id'],'agg_user_daily':['scope_id','utc_date','user_id'],
      'agg_daily_metrics':['scope_id','utc_date'],'agg_daily_dim':['scope_id','utc_date','dim_name','dim_value_key'],
      'brand_mapping':['brand']}
EVENTS=['event_records','view_events','cart_events','remove_from_cart_events','purchase_events','sessions','purchase_sessions']
AMOUNTS=['purchase_amount','purchase_amount_bad','purchase_amount_valid','purchase_zero_events']
STATE=['count_allowed','amount_allowed','amount_status','date_reason_codes']
RATIOS=['buyer_rate','amount_per_buyer','first_seen_ratio']
FIELDS={'dim_user_first_seen':['first_seen_at_utc','first_seen_date_utc'],
        'agg_user_daily':EVENTS+AMOUNTS+['is_buyer','is_first_seen_day']+STATE,
        'agg_daily_metrics':['active_users','buyers']+EVENTS+AMOUNTS+['first_seen_users']+STATE+RATIOS+[r+'_status' for r in RATIOS],
        'agg_daily_dim':['dim_value_label','users','buyers','event_records','purchase_events','purchase_amount','purchase_amount_bad','purchase_amount_valid']+STATE,
        'brand_mapping':['reference_events','brand_rank','dim_value_key','dim_value_label']}
PARSE_FIELDS=['time_missing','time_invalid','user_id_missing','user_id_invalid','event_type_unknown','session_missing','brand_missing','category_code_missing',
              'price_missing','price_invalid','price_nonfinite','price_negative','price_zero','price_precision_exceeded','price_scale_exceeded','event_eligible','amount_eligible']
ABS_TOL=1e-6;REL_TOL=1e-10


def ready(v):
    if isinstance(v,(datetime,date)):return v.isoformat()
    if isinstance(v,Decimal):return format(v,'f')
    if isinstance(v,Path):return str(v)
    if isinstance(v,dict):return {k:ready(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [ready(x) for x in v]
    return v


def save(path,data):
    with Path(path).open('x') as f:json.dump(ready(data),f,indent=2,allow_nan=False);f.write('\n')


def rows(conn,sql,parameters=None,limit=128):
    cur=conn.execute(sql,parameters or []);names=[x[0] for x in cur.description];data=cur.fetchmany(limit+1)
    require(len(data)<=limit,'summary exceeds explicit bound')
    return [dict(zip(names,r)) for r in data]


def scalar(conn,sql,parameters=None):return rows(conn,sql,parameters,1)[0].popitem()[1]


def csv_structure(path):
    count=0;started=time.monotonic()
    with Path(path).open(newline='',encoding='utf-8') as f:
        reader=csv.reader(f,strict=True);require(next(reader,None)==HEADER,'CSV header mismatch')
        for row in reader:
            require(len(row)==9,'CSV field count invalid at record '+str(count+1));count+=1
            if count%500000==0:print(json.dumps(dict(phase='csv_structure',records=count,seconds=round(time.monotonic()-started,1))),flush=True)
    return count


def connection(folder):
    import duckdb
    require(duckdb.__version__=='1.5.5','DuckDB lock mismatch')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False);temp=folder/'temp';temp.mkdir()
    c=duckdb.connect(str(folder/'verification.duckdb'),config={'threads':'4','memory_limit':'2GB','temp_directory':str(temp),
        'max_temp_directory_size':'8GiB','allow_unsigned_extensions':'false','autoinstall_known_extensions':'false','autoload_known_extensions':'false'})
    c.execute("SET TimeZone='UTC'");return c


def import_csv(c,path,scope):
    count=csv_structure(path)
    columns='{'+','.join("'"+k+"':'VARCHAR'" for k in HEADER)+'}'
    force='['+','.join("'"+k+"'" for k in HEADER)+']'
    c.execute(f"""CREATE TABLE raw_csv AS SELECT * FROM read_csv(?,columns={columns},auto_detect=false,header=true,
        delim=',',quote='"',escape='"',new_line='\\n',encoding='utf-8',strict_mode=true,
        null_padding=false,ignore_errors=false,force_not_null={force})""",[str(path)])
    require(scalar(c,'SELECT COUNT(*) FROM raw_csv')==count,'CSV record count mismatch')
    c.execute('CREATE TABLE context(scope_id VARCHAR)');c.execute('INSERT INTO context VALUES (?)',[scope])
    c.execute((ROOT/'sql/validation/parse.sql').read_text());c.execute((ROOT/'sql/validation/quality.sql').read_text())
    return count


def compute(c,top_k,synthetic=False):
    require(top_k==(2 if synthetic else 200),'fixed TopK required')
    require(scalar(c,'SELECT COUNT(*) FROM quality WHERE NOT count_allowed')==0,'independent count gate blocks batch')
    c.execute((ROOT/'sql/validation/metrics.sql').read_text().replace('__TOP_K__',str(top_k)))


def compare(c,snapshot,folder,output_dates=None):
    results=[];table_results={};folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    for table,keys in KEYS.items():
        wanted='d_'+table;actual='s_'+table
        c.read_parquet(snapshot['files'][table],hive_partitioning=False).create_view(actual)
        if output_dates is not None and 'utc_date' in keys:
            c.execute('CREATE OR REPLACE VIEW cmp_expected AS SELECT * FROM '+wanted+' WHERE utc_date IN ('+','.join("DATE '"+d+"'" for d in output_dates)+')');wanted='cmp_expected'
        fields=FIELDS[table];both=keys+fields
        descriptions={name:{r[0]:r[1] for r in c.execute('DESCRIBE '+name).fetchall()} for name in (wanted,actual)}
        require(set(both)==set(descriptions[wanted]),'unmapped independent field '+table)
        meta=snapshot['lineage'] if table!='brand_mapping' else {}
        require(set(descriptions[actual])==set(both)|set(meta),'unmapped Spark field '+table)
        # Validate physical type categories, allowing wider exact integer SUMs.
        type_fail=0
        for col in both:
            a,b=descriptions[wanted][col],descriptions[actual][col]
            if a!=b and not (a in ('INTEGER','BIGINT','HUGEINT') and b in ('INTEGER','BIGINT','HUGEINT')):type_fail+=1
        stat=dict(expected_rows=scalar(c,'SELECT COUNT(*) FROM '+wanted),actual_rows=scalar(c,'SELECT COUNT(*) FROM '+actual),type_differences=type_fail)
        for name,relation in [('expected',wanted),('actual',actual)]:
            stat[name+'_null_keys']=scalar(c,'SELECT COUNT(*) FROM '+relation+' WHERE '+' OR '.join(k+' IS NULL' for k in keys))
            stat[name+'_duplicate_keys']=scalar(c,'SELECT COUNT(*) FROM (SELECT '+','.join(keys)+' FROM '+relation+' GROUP BY '+','.join(keys)+' HAVING COUNT(*)>1)')
        require(not any(stat[k] for k in stat if k.endswith(('_null_keys','_duplicate_keys'))),'invalid keys; stop join to avoid amplification')
        for key,value in meta.items():
            bad=scalar(c,'SELECT COUNT(*) FROM '+actual+' WHERE '+key+' IS DISTINCT FROM ?',[value])
            results.append(dict(table=table,field=key,comparison='lineage_exact',differences=bad,max_absolute_error=None,max_relative_error=None))
        join=' AND '.join('d.'+k+' IS NOT DISTINCT FROM s.'+k for k in keys)
        c.execute('CREATE OR REPLACE VIEW joined AS SELECT d AS d,s AS s,d._present AS dp,s._present AS sp FROM (SELECT *,true _present FROM '+wanted+') d FULL JOIN (SELECT *,true _present FROM '+actual+') s ON '+join)
        stat['missing_in_spark']=scalar(c,'SELECT COUNT(*) FROM joined WHERE sp IS NULL')
        stat['extra_in_spark']=scalar(c,'SELECT COUNT(*) FROM joined WHERE dp IS NULL')
        predicates=[]
        for field in fields:
            left='d.'+field;right='s.'+field;mode='exact';abs_err=rel_err=None
            mismatch=f'({left} IS DISTINCT FROM {right})'
            if field in RATIOS:
                mode='float_frozen_tolerance'
                mismatch=f"""CASE WHEN {left} IS NULL OR {right} IS NULL THEN {left} IS DISTINCT FROM {right}
                   WHEN NOT isfinite({left}) OR NOT isfinite({right}) THEN true
                   ELSE abs({left}-{right})>greatest({ABS_TOL},{REL_TOL}*greatest(abs({left}),abs({right}))) END"""
                errors=rows(c,f'''SELECT max(abs({left}-{right})) a,
                 max(CASE WHEN greatest(abs({left}),abs({right}))=0 THEN 0 ELSE abs({left}-{right})/greatest(abs({left}),abs({right})) END) r
                 FROM joined WHERE dp AND sp''',limit=1)[0];abs_err=errors['a'];rel_err=errors['r']
            elif field=='purchase_amount':
                abs_err=scalar(c,f'SELECT max(abs({left}-{right})) FROM joined WHERE dp AND sp')
            count=scalar(c,'SELECT COUNT(*) FROM joined WHERE dp AND sp AND ('+mismatch+')')
            predicates.append('('+mismatch+')')
            results.append(dict(table=table,field=field,comparison=mode,differences=count,max_absolute_error=abs_err,max_relative_error=rel_err))
        where='dp IS NULL OR sp IS NULL OR '+' OR '.join(predicates)
        stat['rows_with_business_difference']=scalar(c,'SELECT COUNT(*) FROM joined WHERE '+where)
        stat['field_differences']=sum(r['differences'] for r in results if r['table']==table)
        stat['pass']=stat['expected_rows']==stat['actual_rows'] and not any(stat[k] for k in ('type_differences','missing_in_spark','extra_in_spark','rows_with_business_difference','field_differences'))
        if not stat['pass']:
            target=str(folder/(table+'_differences.parquet')).replace("'","''")
            c.execute("COPY (SELECT * FROM joined WHERE "+where+") TO '"+target+"' (FORMAT PARQUET)")
        table_results[table]=stat
        print(json.dumps(dict(phase='compared',table=table,**stat)),flush=True)
    return dict(tables=table_results,fields=results,passed=all(t['pass'] for t in table_results.values()))


def code_hashes():
    names=['tests/crosscheck_duckdb.py','tests/test_idempotency.py','scripts/metric_snapshot.py','scripts/run_crosscheck.py','docs/t14_comparison_contract.md']
    names += [str(p.relative_to(ROOT)) for p in sorted((ROOT/'sql/validation').glob('*.sql'))]
    return {p:digest(ROOT/p) for p in names}


def table_csv(path,values):
    values=[ready(v) for v in values]
    with Path(path).open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(values[0]),lineterminator='\n');w.writeheader();w.writerows(values)


def validate_candidate_receipt(original,registered):
    # The committed manifest deliberately replaces local daily/hourly detail with references.
    for key in ('status','kind','run_id','scope_id','parent_sha256','algorithm_version','seed'):
        require(original[key]==registered[key],'candidate receipt identity mismatch: '+key)
    a=original['sample'];b=registered['sample']
    require({k:v for k,v in a.items() if k!='profile'}=={k:v for k,v in b.items() if k not in ('profile','local_relative_path')},'candidate receipt sample metadata mismatch')
    x=a['profile'];y=b['profile']
    require({k:v for k,v in x.items() if k not in ('daily_records','hourly_records')}==
            {k:v for k,v in y.items() if k not in ('daily_records_report','observed_utc_hour_count')},'candidate receipt profile mismatch')
    require(len(x['hourly_records'])==y['observed_utc_hour_count'] and sum(x['daily_records'].values())==sum(x['hourly_records'].values())==x['record_count'],
            'candidate receipt detail conservation mismatch')


def real_run(config,run,budget):
    cfg=json.loads(Path(config).read_text());run=Path(run).resolve();require(run.is_relative_to(ROOT/'.local/t14'),'run outside T1.4')
    require(set(cfg)=={'scope_id','series_id','source_run','metrics_run','candidate_path','registry_path','synthetic_gate'},'crosscheck config fields mismatch')
    require(cfg['scope_id']==SCOPE and cfg['series_id']==SERIES and cfg['source_run']=='month-v101-01','unauthorized identity')
    source=(ROOT/cfg['candidate_path']).resolve();require(source.is_relative_to(ROOT/'.local/t04/user-samples'),'candidate outside registered local area')
    manifest=json.loads((ROOT/'data/manifest.json').read_text());matches=[m for m in manifest['user_sample_candidates'] if m['scope_id']==SCOPE and m['kind']=='user_sample_candidate' and m['status']=='validated' and m['sample']['sha256']==SHA]
    require(len(matches)==1,'candidate manifest mismatch');m=matches[0]
    require(source==(ROOT/m['sample']['local_relative_path']).resolve() and source.stat().st_size==m['sample']['bytes']==282405091,'candidate path/size mismatch')
    original=json.loads((source.parent/'receipt.json').read_text());validate_candidate_receipt(original,m)
    require(m['sample']['profile']['record_count']==2114081 and digest(source)==SHA,'candidate hash/count identity mismatch')
    gate=json.loads((ROOT/cfg['synthetic_gate']).read_text());require(gate['status']=='passed' and gate['spark_stopped'] and gate['code_sha256']==code_hashes(),'synthetic gate stale or failed')
    snapshot=select_snapshot(ROOT,cfg['metrics_run'],scope_id=SCOPE,source_run='month-v101-01')
    require(snapshot['run']==ROOT/'.local/t13/metrics-month-01' and snapshot['lineage']['input_sha256']==SHA and snapshot['lineage']['source_id']=='rees46_multicategory_2019_oct','wrong metric run or lineage')
    registry=json.loads((ROOT/cfg['registry_path']).read_text());require(len(registry['batches'])==1,'unique registered batch required');entry=registry['batches'][0]
    require(entry['descriptor']['run_id']=='month-v101-01' and entry['descriptor']['scope_id']==SCOPE and entry['descriptor']['input_sha256']==SHA,'registry mismatch')
    protected=[ROOT/'data/manifest.json',source.parent/'receipt.json',ROOT/cfg['registry_path'],ROOT/'reports/data_quality_daily.csv',ROOT/'docs/t13_validation.md',snapshot['run']/'launch.json',snapshot['run']/'complete/validation.json']
    protected += [ROOT/x for x in entry['evidence']]
    before={str(p):digest(p) for p in protected};before.update({k:v['sha256'] for k,v in snapshot['inventory'].items()})
    run.mkdir(parents=True,exist_ok=False);stage=run/'staging';stage.mkdir();result={'status':'failed'};started=time.monotonic();c=None
    try:
        c=connection(stage/'duckdb');budget.start(c)
        n=import_csv(c,source,SCOPE);require(n==2114081,'independent CSV row count mismatch');compute(c,200)
        result.update(compare(c,snapshot,stage/'differences'))
        daily=[]
        for r in rows(c,'SELECT * FROM d_agg_daily_metrics ORDER BY utc_date',limit=31):
            day=str(r['utc_date']);old=entry['daily'][day];g=entry['gates'][day]
            q=rows(c,'SELECT * FROM quality WHERE utc_date=?',[day],1)[0]
            good=(r['event_records']==old['record_count'] and r['active_users']==old['users'] and r['buyers']==old['buyers']
                and r['purchase_events']==old['purchase_events'] and r['purchase_amount']==Decimal(old['purchase_amount'])
                and r['amount_status']==old['amount_status'] and r['count_allowed']==g['count_allowed'] and r['amount_allowed']==g['amount_allowed'])
            for key in ['brand_missing','category_code_missing','session_missing','time_missing','time_invalid','user_id_missing','user_id_invalid','event_type_unknown']:
                good=good and q[key]==old['flags'][key]
            daily.append(dict(r,quality_and_history_pass=good,check_version=VERSION))
        require(len(daily)==31 and all(r['quality_and_history_pass'] for r in daily),'independent date policy/history mismatch')
        month=rows(c,"""SELECT count(*) event_records,count(DISTINCT user_id) users,
            count(DISTINCT user_id) FILTER(WHERE event_type='purchase') buyers,count(*) FILTER(WHERE event_type='purchase') purchase_events,
            sum(price_decimal) FILTER(WHERE amount_eligible) purchase_amount,
            count(DISTINCT (user_id,user_session)) FILTER(WHERE NOT session_missing) sessions FROM eligible""",limit=1)[0]
        result.update(month=month,daily=daily,oct05=next(r for r in daily if str(r['utc_date'])=='2019-10-05'),
            input_records=n,input_sha256=SHA,source_run='month-v101-01',metric_run='metrics-month-01',scope_id=SCOPE,
            first_seen_rows=scalar(c,'SELECT COUNT(*) FROM d_dim_user_first_seen'),brand_rows=scalar(c,'SELECT COUNT(*) FROM d_brand_mapping'),
            resources_settings=rows(c,"SELECT current_setting('threads') threads,current_setting('memory_limit') memory_limit,current_setting('max_temp_directory_size') max_temp_directory_size",limit=1)[0])
        require(result['passed'],'independent metric differences; see retained local details')
        require(before=={p:digest(p) for p in before},'protected evidence or metric files changed')
        require(digest(source)==SHA,'candidate changed during validation')
        result.update(status='passed',protected_hashes=before)
        table_csv(stage/'crosscheck.csv',result['fields']);table_csv(stage/'crosscheck_daily.csv',daily)
    except BaseException as exc:
        result.update(status='failed',error=type(exc).__name__+': '+str(exc));raise
    finally:
        resource_error=None
        try:budget.stop()
        except BaseException as exc:resource_error=exc;result.update(status='failed',error=str(exc))
        if c:c.close()
        result.update(elapsed_seconds=round(time.monotonic()-started,3),code_sha256=code_hashes(),resources=budget.summary())
        save(stage/'validation.json',result)
        if result['status']=='passed':stage.rename(run/'complete')
        print(json.dumps(dict(status=result['status'],seconds=result['elapsed_seconds'],resources=result['resources'])),flush=True)
        if resource_error:raise resource_error


class Budget:
    def __init__(self,path):
        self.cfg=json.loads(Path(path).read_text());self.peak=0;self.minimum=shutil.disk_usage(ROOT).free;self.error=None;self.event=threading.Event();self.thread=None
        require(0<self.cfg['max_new_bytes']<=10*1024**3 and self.cfg['minimum_free_bytes']>=150*1024**3,'budget mismatch')
    def check(self):
        from etl.resource_budget import directory_bytes
        used=max(0,directory_bytes(ROOT/'.local')-self.cfg['initial_bytes'])+self.cfg.get('dependency_bytes',0);free=shutil.disk_usage(ROOT).free
        self.peak=max(self.peak,used);self.minimum=min(self.minimum,free)
        require(used<=self.cfg['max_new_bytes'] and free>=self.cfg['minimum_free_bytes'],'resource budget exceeded')
    def start(self,c):
        self.check()
        def monitor():
            while not self.event.wait(1):
                try:self.check()
                except BaseException as exc:self.error=str(exc);c.interrupt();break
        self.thread=threading.Thread(target=monitor,daemon=True);self.thread.start()
    def stop(self):
        self.event.set()
        if self.thread:self.thread.join()
        self.check();require(self.error is None,self.error)
    def summary(self):return dict(self.cfg,sampled_peak_new_bytes=self.peak,minimum_free_observed_bytes=self.minimum,peak_memory='not_measured',sampling_seconds=1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--run-dir',required=True);p.add_argument('--budget',required=True);a=p.parse_args()
    real_run(a.config,a.run_dir,Budget(a.budget))
