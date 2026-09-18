"""Minimal November metrics and October/November review; immutable October evidence."""
import argparse
import csv
from datetime import date,timedelta
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import yaml
from anomaly.diagnose import screen,serialized,rational,usable
from etl.event_config import HEADER,FLAGS,DERIVED,CONTRACT,sha256
from etl.oracle import build_expected
from etl.date_quality import evaluate
from ingest.november_source import BASE,check_budget
from scripts.metric_snapshot import select_snapshot,require,digest
from scripts.run_diagnosis import csv_write,json_write
from scripts.validate_analysis_scope import validate_scope,verify_evidence
from etl.fact_registry import registered_batch_matches

NOV_DATES=[f'2019-11-{d:02d}' for d in range(1,31)]
ALL_DATES=[(date(2019,10,1)+timedelta(days=i)).isoformat() for i in range(61)]
CODE=['scripts/review_cross_period.py','sql/metrics/cross_period_minimal.sql','sql/validation/parse.sql',
      'etl/oracle.py','etl/date_quality.py','anomaly/diagnose.py','config/cross_period.yaml']


def bounded(c,sql,parameters=None,limit=1000):
    cur=c.execute(sql,parameters or []);names=[r[0] for r in cur.description];data=cur.fetchmany(limit+1)
    require(len(data)<=limit,'aggregate bound exceeded')
    return [dict(zip(names,r)) for r in data]


def connection(stage):
    import duckdb
    require(duckdb.__version__=='1.5.5','verified DuckDB required')
    temp=stage/'temp';temp.mkdir(exist_ok=False)
    c=duckdb.connect(str(stage/'metrics.duckdb'),config={'threads':'4','memory_limit':'2GB',
        'temp_directory':str(temp),'max_temp_directory_size':'12GiB',
        'autoinstall_known_extensions':'false','autoload_known_extensions':'false'})
    c.execute("SET TimeZone='UTC'");return c


def parse(c,path):
    columns={k:'VARCHAR' for k in HEADER}
    c.execute('CREATE TABLE raw_csv AS SELECT * FROM read_csv(?,columns=?,auto_detect=false,header=true,delim=\',\',quote=\'"\',escape=\'"\',new_line=\'\\n\',encoding=\'utf-8\',strict_mode=true,null_padding=false,ignore_errors=false,force_not_null=?)', [str(path),columns,HEADER])
    c.execute((ROOT/'sql/validation/parse.sql').read_text())
    # Same strict ID flags as the frozen parsing contract; the original SQL is unchanged.
    for field in ('product_id','category_id'):
        c.execute(f'ALTER TABLE parsed ADD COLUMN {field}_missing BOOLEAN')
        c.execute(f'ALTER TABLE parsed ADD COLUMN {field}_invalid BOOLEAN')
        c.execute(f"UPDATE parsed SET {field}_missing=blank({field}),{field}_invalid=NOT blank({field}) AND NOT regexp_full_match({field},'[0-9]+')")


def canonical_check(c,expected_path):
    columns={k:'VARCHAR' for k in HEADER+DERIVED};columns.update({k:'BOOLEAN' for k in FLAGS})
    c.execute('CREATE TABLE expected AS SELECT * FROM read_json(?,columns=?,format=\'newline_delimited\',ignore_errors=false)',[str(expected_path),columns])
    fields=','.join(HEADER)+",strftime(ts,'%Y-%m-%dT%H:%M:%S+00:00') AS event_timestamp_utc,CAST(utc_date AS VARCHAR) AS event_date_utc,CAST(price_decimal AS VARCHAR) AS price_decimal,"+','.join(FLAGS)
    c.execute('CREATE VIEW actual_canonical AS SELECT '+fields+' FROM parsed')
    differences={}
    for side,a,b in [('expected_minus_actual','expected','actual_canonical'),('actual_minus_expected','actual_canonical','expected')]:
        n=c.execute(f'SELECT count(*) FROM (SELECT * FROM {a} EXCEPT ALL SELECT * FROM {b})').fetchone()[0]
        differences[side]=n;require(n==0,'full row multiset mismatch: '+side)
    return differences


def build(c,gates):
    c.execute('CREATE TABLE gates(utc_date DATE,count_allowed BOOLEAN,amount_allowed BOOLEAN,amount_status VARCHAR)')
    c.executemany('INSERT INTO gates VALUES (?,?,?,?)',[(d,g['count_allowed'],g['amount_allowed'],g['amount_status']) for d,g in sorted(gates.items())])
    c.execute((ROOT/'sql/metrics/cross_period_minimal.sql').read_text())
    daily=bounded(c,'SELECT * FROM daily ORDER BY utc_date',limit=31)
    categories=bounded(c,'SELECT * FROM category_daily ORDER BY utc_date,category_key',limit=1000)
    return serialized(daily),serialized(categories)


def metrics():
    started=time.monotonic();run=BASE/'nov-metrics-01';stage=run/'staging';stage.mkdir(parents=True,exist_ok=False)
    c=None;stop=threading.Event();budget_failure=[];proof={'status':'failed'}
    try:
        sample=BASE/'nov-sample-01/complete';receipt=json.loads((sample/'receipt.json').read_text());path=sample/'user_sample_candidate.csv'
        require(receipt['status']=='validated' and receipt['kind']=='user_sample_candidate' and receipt['source_id']=='rees46_multicategory_2019_nov','candidate registration mismatch')
        raw=json.loads((BASE/'nov-source-01/complete.json').read_text())
        require(raw['status']=='complete' and receipt['parent_sha256']==raw['csv']['sha256']
                and receipt['scope_id']=='rees46_2019_nov_user5_'+raw['csv']['sha256'][:16]+'_20260916_v1'
                and receipt['run_id']=='nov-sample-01'
                and receipt['sample']['profile_matches_extraction']=='pass'
                and receipt['sample']['serialization_and_sha256']=='pass'
                and receipt['sample']['all_user_hash_conditions']=='pass','candidate parent/scope/completion mismatch')
        require(receipt['seed']=='20260916' and receipt['payload_prefix']=='rees46-user-sample-v1|20260916|' and receipt['threshold_uint64']==(5*2**64)//100,'sampling rule mismatch')
        require(path.stat().st_size==receipt['sample']['bytes'] and sha256(path)==receipt['sample']['sha256'],'candidate content mismatch')
        require(receipt['sample']['profile']['expected_dates_without_records']==[],'candidate missing dates')
        proof.update(scope_id=receipt['scope_id'],candidate_sha256=receipt['sample']['sha256'],contract_version=CONTRACT,
                     run_id=run.name,code_sha256={x:sha256(ROOT/x) for x in CODE})
        expected=build_expected(path,stage/'expected_rows.jsonl',receipt['sample']['profile']['record_count'],budget_check=check_budget)
        json_write(stage/'expected_summary.json',expected)
        days=json.loads((stage/'expected_daily.json').read_text())
        identity={'source_id':receipt['source_id'],'scope_id':receipt['scope_id'],'input_sha256':receipt['sample']['sha256'],
                  'contract_version':CONTRACT,'run_id':run.name}
        gates=evaluate(identity,days,NOV_DATES,evidence_valid=True)
        json_write(stage/'date_gates.json',gates)
        # New lexical/ID failures require review before metric publication, not a wider contract.
        exceptional=['time_invalid','user_id_invalid','product_id_invalid','category_id_invalid','event_type_unknown',
                     'price_invalid','price_nonfinite','price_precision_exceeded','price_scale_exceeded']
        require(not any(expected['flags'][x] for x in exceptional),'new parsing format/identity issue; inspect expected_summary and stop')
        require(all(g['count_allowed'] for g in gates.values()),'date count quality blocks reliable comparison')
        print(json.dumps({'phase':'oracle_complete','records':expected['record_count']}),flush=True)
        c=connection(stage)
        def monitor():
            while not stop.wait(2):
                try:check_budget()
                except BaseException as exc:
                    budget_failure.append(str(exc));c.interrupt();return
        watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
        parse(c,path)
        proof['multiset_checks']=canonical_check(c,stage/'expected_rows.jsonl')
        print(json.dumps({'phase':'full_multiset_pass'}),flush=True)
        daily,categories=build(c,gates)
        require([r['utc_date'] for r in daily]==NOV_DATES,'November date coverage mismatch')
        for r in daily:
            e=days[r['utc_date']]
            for a,b in [('active_users','users'),('buyers','buyers'),('event_records','record_count'),('purchase_events','purchase_events')]:
                require(r[a]==e[b],'independent daily mismatch '+a)
            expected_amount=e['purchase_amount'] if gates[r['utc_date']]['amount_allowed'] else None
            require(r['purchase_amount']==expected_amount,'independent Decimal daily mismatch')
        validate_categories(daily,categories)
        # Independently derive category totals from the stdlib-parsed expected rows.
        check=c.execute("""WITH a AS (SELECT CAST(event_date_utc AS DATE) utc_date,
          CASE WHEN regexp_full_match(category_code,'[A-Za-z0-9_]+(\\.[A-Za-z0-9_]+)*') THEN 'category:'||split_part(category_code,'.',1) ELSE 'bucket:unknown' END k,
          count(*) n,count(*) FILTER(WHERE event_type='purchase') p,
          coalesce(sum(CAST(price_decimal AS DECIMAL(38,2))) FILTER(WHERE amount_eligible),0) v
          FROM expected WHERE event_eligible GROUP BY 1,2)
          SELECT count(*) FROM a FULL JOIN category_daily b ON a.utc_date=b.utc_date AND a.k=b.category_key
          WHERE a.n IS DISTINCT FROM b.event_records OR a.p IS DISTINCT FROM b.purchase_events
          OR (b.amount_allowed AND a.v IS DISTINCT FROM b.purchase_amount)""").fetchone()[0]
        require(check==0,'independent category mismatch')
        for table in ('daily','category_daily'):
            output=stage/(table+'.parquet');c.execute(f'COPY {table} TO ? (FORMAT PARQUET)',[str(output)])
            types={r[0]:r[1] for r in c.execute('DESCRIBE SELECT * FROM read_parquet(?)',[str(output)]).fetchall()}
            require(types['event_records']==types['purchase_events']=='BIGINT','count export physical type mismatch')
            require(c.execute(f'SELECT count(*) FROM ((SELECT * FROM {table} EXCEPT ALL SELECT * FROM read_parquet(?)) UNION ALL (SELECT * FROM read_parquet(?) EXCEPT ALL SELECT * FROM {table}))',[str(output),str(output)]).fetchone()[0]==0,'Parquet readback mismatch')
        csv_write(stage/'daily.csv',daily);csv_write(stage/'category_daily.csv',categories)
        require(not budget_failure,'resource monitor interrupted run')
        stop.set();watcher.join();c.close();c=None
        require(sha256(path)==receipt['sample']['sha256'],'candidate changed')
        proof.update(status='passed',daily_rows=len(daily),category_rows=len(categories),input_records=expected['record_count'],
                     summary=expected,gates=gates,independent_category_differences=check,
                     resources=check_budget(),elapsed_seconds=round(time.monotonic()-started,3))
        json_write(stage/'validation.json',proof);stage.rename(run/'complete')
    except BaseException as exc:
        stop.set()
        if c:c.close()
        proof.update(error=type(exc).__name__+': '+str(exc),elapsed_seconds=round(time.monotonic()-started,3))
        json_write(stage/'failure.json',proof);raise


def validate_categories(daily,categories):
    known={r['utc_date']:r for r in daily};seen=set()
    for r in categories:
        key=(r['utc_date'],r['category_key']);require(key not in seen,'duplicate category date');seen.add(key)
        require(r['utc_date'] in known,'category outside observation')
    for day,total in known.items():
        group=[r for r in categories if r['utc_date']==day];require(group,'missing entire category date')
        for key in ('event_records','purchase_events','purchase_amount'):
            if key=='purchase_amount' and not total['amount_allowed']:
                require(all(r[key] is None for r in group),'blocked amount leaked');continue
            require(sum(rational(r[key]) for r in group)==rational(total[key]),'category conservation '+day+' '+key)


def october():
    """Reuse canonical selector and the exact already-reviewed evidence compatibility."""
    cfg=yaml.safe_load((ROOT/'config/analysis_scope.yaml').read_text());validate_scope(cfg);binding=cfg['binding']
    lc=json.loads((ROOT/'config/analysis_scope.local.json').read_text());mc=json.loads((ROOT/lc['metrics_config']).read_text());cc=json.loads((ROOT/lc['crosscheck_config']).read_text())
    require(Path(cc['metrics_run']).name==binding['metric_run']=='metrics-month-01','canonical October metric required')
    require(mc['scope_id']==cc['scope_id']==binding['scope_id'] and mc['registry_path']==cc['registry_path'],'October binding mismatch')
    cross=json.loads((ROOT/lc['crosscheck_receipt']).read_text());registry=json.loads((ROOT/mc['registry_path']).read_text())
    require(len(registry['batches'])==1,'ambiguous October input')
    batch=registry['batches'][0];desc=batch['descriptor'];fr=ROOT/desc['run_path']
    snap=select_snapshot(ROOT,cc['metrics_run'],scope_id=binding['scope_id'],source_run=binding['fact_run'],tables=('agg_daily_metrics','agg_daily_dim'))
    verify_evidence(cfg,desc,json.loads((fr/'launch.json').read_text()),json.loads((fr/'complete/validation.json').read_text()),snap['proof'],cross)
    require(registered_batch_matches({'evidence':{p:digest(ROOT/p) for p in batch['evidence']}},{'evidence':batch['evidence']},allow_criteo_manifest_extension=True),'October evidence changed')
    for p,m in snap['inventory'].items():require(cross['protected_hashes'].get(p)==m['sha256'],'October selected file changed')
    import duckdb
    c=duckdb.connect(':memory:');c.execute("SET threads=2; SET memory_limit='512MB'; SET TimeZone='UTC'")
    try:
        d=bounded(c,'SELECT utc_date,active_users,buyers,event_records,purchase_events,purchase_amount,count_allowed,amount_allowed,amount_status,buyer_rate,amount_per_buyer FROM read_parquet(?) ORDER BY utc_date',[snap['files']['agg_daily_metrics']],31)
        cat=bounded(c,"SELECT utc_date,dim_value_key AS category_key,dim_value_label AS category_label,event_records,purchase_events,purchase_amount,count_allowed,amount_allowed FROM read_parquet(?) WHERE dim_name='category_l1' ORDER BY utc_date,category_key",[snap['files']['agg_daily_dim']],1000)
        require(len(d)==31,'October daily count changed');validate_categories(serialized(d),serialized(cat))
        return serialized(d),serialized(cat),snap['inventory']
    finally:c.close()


def compare_categories(daily,categories,flags):
    known={r['utc_date']:r for r in daily};groups={(r['utc_date'],r['category_key']):r for r in categories};out=[]
    validate_categories(daily,categories)
    for flag in flags:
        day=flag['utc_date'];hist=flag['history_dates'];total=known[day]
        for key in ('category:electronics','category:computers','bucket:unknown'):
            r=groups.get((day,key));value=rational(r['purchase_amount']) if r and total['amount_allowed'] else Fraction(0) if not r and total['amount_allowed'] else None
            row=dict(utc_date=day,category_key=key,current_amount=value,current_share=value/rational(total['purchase_amount']) if value is not None and total['purchase_amount'] and rational(total['purchase_amount'])>0 else None,
                     history_dates=hist,history_count=len(hist),history_mean_amount=None,history_share=None,relative_change=None,total_relative_change=None,excess_change_pp=None,amount_difference=None,status='history_or_quality_unavailable')
            if len(hist)>=3 and usable(total):
                base=sum((rational(groups[(d,key)]['purchase_amount']) if (d,key) in groups else Fraction(0) for d in hist),Fraction(0))/len(hist)
                vbase=sum(rational(known[d]['purchase_amount']) for d in hist)/len(hist)
                overall=rational(total['purchase_amount'])/vbase-1 if vbase>0 else None
                row.update(history_mean_amount=base,history_share=base/vbase if vbase>0 else None,amount_difference=value-base,total_relative_change=overall,status='zero_category_baseline' if base==0 else 'comparable')
                if base>0:row.update(relative_change=value/base-1,excess_change_pp=((value/base-1)-overall)*100 if overall is not None else None)
            out.append(row)
    return out


def review(run_id='review-01',november_run='nov-metrics-01'):
    import re
    require(re.fullmatch('[A-Za-z0-9_-]+',run_id) is not None,'unsafe review run id')
    require(november_run in ('nov-metrics-01','nov-metrics-02'),'unregistered November metric run')
    run=BASE/run_id;run.mkdir(exist_ok=False);stage=run/'staging';stage.mkdir();start=time.monotonic()
    cfg=yaml.safe_load((ROOT/'config/cross_period.yaml').read_text())
    require(sha256(ROOT/'config/cross_period.yaml')==sha256(BASE/'frozen_cross_period.yaml'),'pre-result rule changed')
    old_policy=yaml.safe_load((ROOT/'config/anomaly.yaml').read_text())
    for k in ('history_offsets_days','min_history_points','mad_scale','score_abs_gt','relative_change_abs_gte'):
        require(cfg[k]==old_policy[k],'screen rule changed')
    try:
        old,oldcat,inventory=october();nov=BASE/november_run/'complete'
        proof=json.loads((nov/'validation.json').read_text());require(proof['status']=='passed' and proof['run_id']==november_run,'November metrics not verified')
        import duckdb
        c=duckdb.connect(':memory:')
        new=serialized(bounded(c,'SELECT * FROM read_parquet(?) ORDER BY utc_date',[str(nov/'daily.parquet')],30))
        newcat=serialized(bounded(c,'SELECT * FROM read_parquet(?) ORDER BY utc_date,category_key',[str(nov/'category_daily.parquet')],1000));c.close()
        daily=old+new;cats=oldcat+newcat
        require([r['utc_date'] for r in daily]==ALL_DATES,'61-day range mismatch')
        flags=screen(daily,ALL_DATES,cfg);comp=compare_categories(daily,cats,flags)
        for r in flags:require(all(d<r['utc_date'] for d in r['history_dates']),'future leakage')
        # October output values must remain exactly as previously computed.
        before=list(csv.DictReader((ROOT/'reports/anomaly_flags.csv').open()))
        for a,b in zip(flags[:31],before):
            require(a['utc_date']==b['utc_date'] and a['status']==b['status'] and str(a['candidate'])==b['candidate'],'October screen state changed')
            for k in ('current_amount','median_amount','mad','score','amount_difference','relative_change'):
                actual=serialized(a[k]);expected=b[k] or None
                require((actual is None and expected is None) or (actual is not None and Decimal(str(actual))==Decimal(expected)),'October screen value changed '+k)
        for r in daily:r.update(analysis_scope=cfg['analysis_scope'],source_month=r['utc_date'][:7])
        for r in cats:r.update(analysis_scope=cfg['analysis_scope'])
        csv_write(stage/'daily_metrics.csv',daily);csv_write(stage/'category_daily.csv',cats)
        csv_write(stage/'anomaly_flags.csv',flags);csv_write(stage/'category_comparisons.csv',comp)
        fridays=[r for r in comp if date.fromisoformat(r['utc_date']).weekday()==4 and r['utc_date']>='2019-10-04']
        csv_write(stage/'friday_comparisons.csv',fridays)
        coverage=[]
        for r in daily:
            unknown=next((x for x in cats if x['utc_date']==r['utc_date'] and x['category_key']=='bucket:unknown'),None)
            row={'utc_date':r['utc_date']}
            for k in ('event_records','purchase_events','purchase_amount'):
                value=unknown[k] if unknown else 0;row['unknown_'+k]=value
                row['known_'+k+'_coverage']=1-rational(value)/rational(r[k]) if r[k] is not None and rational(r[k])>0 and value is not None else None
            coverage.append(row)
        csv_write(stage/'category_coverage.csv',coverage)
        totals=[]
        for month in ('2019-10','2019-11'):
            days=[r for r in daily if r['utc_date'].startswith(month)]
            for key in ('overall','category:electronics','category:computers','bucket:unknown'):
                data=days if key=='overall' else [r for r in cats if r['utc_date'].startswith(month) and r['category_key']==key]
                valid=all(r['amount_allowed'] for r in days)
                amount=sum(rational(r['purchase_amount']) for r in data) if valid else None
                total=sum(rational(r['purchase_amount']) for r in days) if valid else None
                totals.append(dict(month=month,category_key=key,calendar_days=len(days),amount_allowed=valid,
                    purchase_amount=amount,daily_mean_amount=amount/len(days) if amount is not None else None,
                    amount_share=amount/total if amount is not None and total>0 else None,
                    purchase_events=sum(r['purchase_events'] for r in data),daily_mean_purchase_events=Fraction(sum(r['purchase_events'] for r in data),len(days))))
        csv_write(stage/'monthly_daily_means.csv',totals)
        require(all(sha256(p)==m['sha256'] for p,m in inventory.items()),'October input changed')
        json_write(stage/'validation.json',dict(status='passed',october_inventory=inventory,november_metrics_sha256=sha256(nov/'validation.json'),
            code_sha256={p:sha256(ROOT/p) for p in CODE},daily_rows=len(daily),category_rows=len(cats),flags=len(flags),
            candidates=[r['utc_date'] for r in flags if r['candidate']],resources=check_budget(),elapsed_seconds=round(time.monotonic()-start,3)))
        stage.rename(run/'complete')
    except BaseException as exc:
        json_write(stage/'failure.json',{'status':'failed','error':str(exc)});raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['metrics','review'])
    parser.add_argument('--run-id',default='review-01');parser.add_argument('--november-run',default='nov-metrics-01');args=parser.parse_args()
    if args.phase=='metrics':metrics()
    else:review(args.run_id,args.november_run)
