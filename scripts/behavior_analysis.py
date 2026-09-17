"""T2.2 small aggregate preparation; no fact-level or CSV source access."""
import argparse
from collections import defaultdict
import csv
from decimal import Decimal
import json
import math
from pathlib import Path
import statistics
import sys
import time
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.metric_snapshot import digest, require
from scripts.validate_analysis_scope import canonical_snapshot, validate_scope, VERSION as ANALYSIS_VERSION
from scripts.run_metrics import ready, Checks, DATES, SCOPE

VERSION='rees46-behavior-report-v1'
DAILY_FIELDS=['utc_date','active_users','buyers','purchase_events','purchase_amount','buyer_rate','amount_per_buyer','first_seen_ratio','amount_status']
STATS_FIELDS=DAILY_FIELDS[1:-1]
CATEGORY_FIELDS=['amount_rank','category_key','category_label','purchase_amount','purchase_events','user_days','buyer_user_days','users','buyers','monthly_distinct_status','amount_share','cumulative_amount_share','is_unknown','amount_status']
HOUR_FIELDS=['utc_hour','purchase_events','purchase_users','purchase_amount','purchase_events_share','share_status']
RATIOS=[('view_to_cart','n_cart','n_view'),('cart_to_purchase_three_step','n_three_step','n_cart'),('view_to_purchase','n_purchase','n_view'),('three_step_ratio','n_three_step','n_view')]
FUNNEL_REPORTS=['behavior_coverage.csv','funnel_summary.csv','funnel_exclusions.csv','purchase_path_coverage.csv']


def ratio(num,den):return None if den==0 else float(Decimal(str(num))/Decimal(str(den)))


def daily_stats(rows):
    result=[]
    for key in STATS_FIELDS:
        values=[(str(r['utc_date']),Decimal(str(r[key]))) for r in rows if r[key] is not None]
        if not values:
            result.append(dict(metric=key,min=None,max=None,median=None,min_dates='',max_dates='',observations=0));continue
        lo=min(v for _,v in values);hi=max(v for _,v in values)
        result.append(dict(metric=key,min=lo,max=hi,median=statistics.median(v for _,v in values),
            min_dates=';'.join(d for d,v in values if v==lo),max_dates=';'.join(d for d,v in values if v==hi),observations=len(values)))
    return result


def category_summary(rows):
    grouped={}
    seen=set()
    for r in rows:
        pk=(str(r['utc_date']),r['dim_value_key']);require(pk not in seen,'duplicate category-day');seen.add(pk)
        require(r['count_allowed'] and r['amount_allowed'] and r['purchase_amount'] is not None and r['amount_status'] in ('complete_observed','no_purchases'),'category amount unavailable')
        key=r['dim_value_key']
        if key not in grouped:grouped[key]=dict(category_key=key,category_label=r['dim_value_label'],purchase_amount=Decimal('0.00'),purchase_events=0,user_days=0,buyer_user_days=0)
        g=grouped[key];require(g['category_label']==r['dim_value_label'],'category label drift')
        g['purchase_amount']+=Decimal(str(r['purchase_amount']));g['purchase_events']+=r['purchase_events'];g['user_days']+=r['users'];g['buyer_user_days']+=r['buyers']
    ordered=sorted(grouped.values(),key=lambda r:(-r['purchase_amount'],r['category_key']))
    total=sum((r['purchase_amount'] for r in ordered),Decimal('0'));cumulative=Decimal('0');out=[]
    for rank,r in enumerate(ordered,1):
        cumulative+=r['purchase_amount']
        out.append(dict(amount_rank=rank,**r,users=None,buyers=None,monthly_distinct_status='not_measured_daily_counts_not_additive',
            amount_share=ratio(r['purchase_amount'],total),cumulative_amount_share=ratio(cumulative,total),is_unknown=r['category_key']=='bucket:unknown',
            amount_status='complete_observed' if r['purchase_events'] else 'no_purchases'))
    concentration={f'top{k}_amount_share':ratio(sum((r['purchase_amount'] for r in ordered[:k]),Decimal('0')),total) for k in (1,5,10)}
    unknown=next((r for r in out if r['is_unknown']),None)
    return out,dict(total_amount=total,**concentration,unknown_amount=unknown['purchase_amount'] if unknown else Decimal('0.00'),unknown_share=ratio(unknown['purchase_amount'] if unknown else 0,total),categories=len(out))


def complete_hours(rows):
    known={}
    for r in rows:
        h=r['utc_hour'];require(type(h) is int and 0<=h<24 and h not in known,'invalid or duplicate UTC hour')
        require(0<=r['purchase_users']<=r['purchase_events'] and r['purchase_amount'] is not None,'invalid hourly aggregate')
        known[h]=r
    total=sum(r['purchase_events'] for r in rows);out=[]
    for h in range(24):
        r=known.get(h,dict(utc_hour=h,purchase_events=0,purchase_users=0,purchase_amount=Decimal('0.00')))
        out.append(dict(r,purchase_events_share=ratio(r['purchase_events'],total),share_status='defined' if total else 'zero_denominator'))
    return out


def write_csv(path,rows,fields):
    with Path(path).open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n');writer.writeheader();writer.writerows(ready(rows))


def read_csv(path):
    with Path(path).open(newline='') as f:return list(csv.DictReader(f))


def write_json(path,value):
    with Path(path).open('x') as f:json.dump(ready(value),f,indent=2,ensure_ascii=False,allow_nan=False);f.write('\n')


def prepare(config,run_dir):
    started=time.monotonic();cfg=json.loads(Path(config).read_text());checks=Checks()
    require(set(cfg)=={'analysis_scope','scope_receipt','metrics_config','metrics_run','funnel_run','version'},'report config fields')
    require(cfg['version']==VERSION and cfg['analysis_scope']=='config/analysis_scope.yaml' and Path(cfg['metrics_run']).name=='metrics-month-01' and Path(cfg['funnel_run']).name=='funnel-month-01','canonical runs required')
    for value in [cfg[k] for k in ('analysis_scope','scope_receipt','metrics_config','metrics_run','funnel_run')]:
        require(isinstance(value,str) and value and 'REPLACE' not in value and not any(c in value for c in '*?[') and (ROOT/value).resolve().is_relative_to(ROOT),'explicit project path required')
    run=(ROOT/run_dir).resolve();require(run.is_relative_to(ROOT/'.local/t22'),'T2.2 output only');run.mkdir(parents=True,exist_ok=False)
    try:
        scope=yaml.safe_load((ROOT/cfg['analysis_scope']).read_text());validate_scope(scope)
        scope_proof=json.loads((ROOT/cfg['scope_receipt']).read_text());require(scope_proof['status']=='passed' and scope_proof['binding']==scope['binding'] and scope_proof['scope_sha256']==digest(ROOT/cfg['analysis_scope']),'scope evidence mismatch')
        protected={str(ROOT/k):v for k,v in scope_proof['evidence_hashes'].items()}
        protected[str(ROOT/cfg['analysis_scope'])]=scope_proof['scope_sha256']
        for path,sha in protected.items():checks.equal('evidence_'+Path(path).name,sha,digest(path))
        snap=canonical_snapshot(ROOT,scope,cfg['metrics_run']);protected.update({p:r['sha256'] for p,r in snap['inventory'].items()})
        funnel=ROOT/cfg['funnel_run'];fp=json.loads((funnel/'complete/validation.json').read_text());fl=json.loads((funnel/'launch.json').read_text())
        require(not (funnel/'staging').exists() and fp['status']==fl['status']=='passed' and fp['spark_stopped'] and fp['checks'] and all(c['pass'] for c in fp['checks'].values()),'funnel not complete')
        require(fp['lineage']['source_run']=='month-v101-01' and fp['lineage']['analysis_scope_version']==ANALYSIS_VERSION and fp['lineage']['input_sha256']==scope['binding']['candidate_sha256'],'funnel binding mismatch')
        for f in [funnel/'complete/validation.json',funnel/'launch.json']:protected[str(f)]=digest(f)
        for name in FUNNEL_REPORTS:
            local=funnel/'complete/analysis'/name;shared=ROOT/'reports'/name
            checks.equal('funnel_csv_'+name,read_csv(local),read_csv(shared))
            key=dict(zip(FUNNEL_REPORTS,['coverage','summary','exclusions','purchase_audit']))[name]
            expected=[{k:'' if v is None else str(v) for k,v in r.items()} for r in ready(fp[key])]
            checks.equal('funnel_receipt_'+name,expected,read_csv(shared))
            protected[str(local)]=digest(local);protected[str(shared)]=digest(shared)
        import duckdb
        con=duckdb.connect(':memory:');con.execute("SET TimeZone='UTC'")
        def read(table,where='',cap=31):
            files=snap['files'][table];cur=con.execute('SELECT * FROM read_parquet(?) '+where+' LIMIT '+str(cap+1),[files]);keys=[c[0] for c in cur.description];rows=[dict(zip(keys,r)) for r in cur.fetchall()];require(len(rows)<=cap,'small aggregate cap exceeded');return rows
        daily=sorted(read('agg_daily_metrics'),key=lambda r:r['utc_date']);checks.equal('daily_dates',DATES,[str(r['utc_date']) for r in daily])
        for r in daily:
            require(r['scope_id']==SCOPE and r['source_run']=='month-v101-01' and r['count_allowed'] and r['amount_allowed'] and r['amount_status']=='complete_observed','unapproved daily scope/quality')
            old=next(x for x in snap['proof']['daily'] if x['utc_date']==str(r['utc_date']))
            for k,v in old.items():checks.equal('daily_'+str(r['utc_date'])+'_'+k,v,ready(r[k]))
            require(math.isclose(float(r['purchase_amount']),r['active_users']*r['buyer_rate']*r['amount_per_buyer'],abs_tol=1e-6,rel_tol=1e-10),'U R M identity failed')
        categories=read('agg_daily_dim',"WHERE dim_name='category_l1'",31*128);con.close()
        for r in categories:require(r['scope_id']==SCOPE and r['source_run']=='month-v101-01' and str(r['utc_date']) in DATES,'category scope mismatch')
        result,concentration=category_summary(categories)
        month=snap['proof']['month']
        checks.equal('category_month_amount',month['purchase_amount'],format(concentration['total_amount'],'.2f'))
        checks.equal('category_month_purchase_events',month['purchase_events'],sum(r['purchase_events'] for r in result))
        unknown=next(r for r in snap['proof']['unknown_dimensions'] if r['dim_name']=='category_l1')
        checks.equal('category_unknown_amount',unknown['purchase_amount'],format(concentration['unknown_amount'],'.2f'))
        checks.equal('category_unknown_purchase_events',unknown['purchase_events'],sum(r['purchase_events'] for r in result if r['is_unknown']))
        for day in daily:
            part=[r for r in categories if r['utc_date']==day['utc_date']]
            checks.equal('category_daily_amount_'+str(day['utc_date']),day['purchase_amount'],sum((r['purchase_amount'] for r in part),Decimal('0')))
            checks.equal('category_daily_purchase_'+str(day['utc_date']),day['purchase_events'],sum(r['purchase_events'] for r in part))
        small=[{k:r[k] for k in DAILY_FIELDS} for r in daily]
        write_csv(run/'behavior_daily.csv',small,DAILY_FIELDS)
        stats=daily_stats(small);write_csv(run/'behavior_daily_stats.csv',stats,list(stats[0]))
        write_csv(run/'category_concentration.csv',result,CATEGORY_FIELDS)
        write_json(run/'category_daily_expected.json',categories)
        checks.equal('monthly_users_from_receipt',snap['proof']['tables']['dim_user_first_seen']['rows'],month['active_users'])
        checks.equal('daily_user_sum_not_monthly_users',False,sum(r['active_users'] for r in daily)==month['active_users'])
        for path,sha in protected.items():require(digest(path)==sha,'protected input changed')
        output=dict(status='passed',checks=checks.rows,config=cfg,month=month,concentration=concentration,daily_summary=stats,
            category_daily_rows=len(categories),protected_hashes=protected,elapsed_seconds=round(time.monotonic()-started,3),
            funnel_identity=dict(selected_directory='funnel-month-01',historical_lineage_funnel_run=fp['lineage']['funnel_run'],resolution='canonical_complete_directory_and_launch_plus_result_content'),
            matplotlib_in_project=False,monthly_category_users='not_measured_daily_aggregate_not_additive')
        write_json(run/'prepare.json',output)
    except BaseException as exc:
        write_json(run/'failed.json',dict(status='failed',error=str(exc)));raise
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);parser.add_argument('--run-dir',required=True);args=parser.parse_args()
    r=prepare(args.config,args.run_dir);print(json.dumps(dict(status=r['status'],checks=len(r['checks']),category_rows=r['category_daily_rows'],elapsed_seconds=r['elapsed_seconds'])))
