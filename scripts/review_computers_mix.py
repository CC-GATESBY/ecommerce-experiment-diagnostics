"""Six-date product-proxy investigation; all raw IDs and full results stay local."""
import argparse
import csv
from decimal import Decimal
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import shutil
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from anomaly.diagnose import serialized
from etl.fact_registry import load_registry,inspect_batch,registered_batch_matches
from scripts.metric_snapshot import require,digest
from scripts.review_cross_period import bounded

HISTORY={'2019-10-25':['2019-10-04','2019-10-11','2019-10-18'],
         '2019-11-01':['2019-10-04','2019-10-11','2019-10-18','2019-10-25'],
         '2019-11-08':['2019-10-11','2019-10-18','2019-10-25','2019-11-01']}
DAYS=sorted(set(HISTORY)|{d for dates in HISTORY.values() for d in dates})
BASE=ROOT/'.local/computers_mix'
PARTS=('stable_common','stable_history_only','stable_current_only','classification_unstable')


def dump(path,value):
    with path.open('x') as f:json.dump(serialized(value),f,indent=2,ensure_ascii=False);f.write('\n')


def csv_write(path,rows):
    with path.open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader()
        for row in serialized(rows):w.writerow({k:';'.join(v) if isinstance(v,list) else v for k,v in row.items()})


def attach_read_only(c,path):
    # DuckDB ATTACH does not accept bound path parameters; escape a SQL literal.
    literal="'"+str(path).replace("'","''")+"'"
    c.execute('ATTACH '+literal+' AS november (READ_ONLY)')


def classify(category_rows):
    known={}
    for r in category_rows:known.setdefault(r['product_id'],set()).add(r['category_key'])
    return {p:dict(stable=keys=={'category:computers'},observed_categories=sorted(keys),
                   other_known=any(k not in ('category:computers','bucket:unknown') for k in keys),
                   unknown='bucket:unknown' in keys) for p,keys in known.items()}


def compare(products,classes,target,history):
    require(target not in history and len(set(history))==len(history) and all(d<target for d in history),'invalid historical dates')
    lookup={(r['utc_date'],r['product_id']):r for r in products}
    require(len(lookup)==len(products),'duplicate product-date aggregate')
    ids=sorted({r['product_id'] for r in products if r['utc_date'] in [target,*history]})
    out=[]
    for p in ids:
        present=lookup.get((target,p));past=[lookup[(d,p)] for d in history if (d,p) in lookup]
        n1=F(present['purchase_events']) if present else F(0);v1=F(present['purchase_amount']) if present else F(0)
        nt=sum((F(r['purchase_events']) for r in past),F(0));vt=sum((F(r['purchase_amount']) for r in past),F(0))
        n0=nt/len(history);v0=vt/len(history);p0=v0/n0 if n0 else None;p1=v1/n1 if n1 else None
        part='classification_unstable' if not classes[p]['stable'] else 'stable_common' if n0 and n1 else 'stable_history_only' if n0 else 'stable_current_only'
        q=m=None
        if part=='stable_common':
            q=(n1-n0)*(p1+p0)/2;m=(p1-p0)*(n1+n0)/2
            require(q+m==v1-v0,'product identity failed')
        out.append(dict(target_date=target,product_id=p,part=part,history_dates=history,
                        history_purchase_events=nt,history_mean_events=n0,current_purchase_events=n1,
                        history_mean_amount=v0,current_amount=v1,amount_difference=v1-v0,
                        history_record_mean=p0,current_record_mean=p1,
                        current_record_min=present['min_record_amount'] if present else None,
                        current_record_max=present['max_record_amount'] if present else None,
                        history_record_min=min(r['min_record_amount'] for r in past) if past else None,
                        history_record_max=max(r['max_record_amount'] for r in past) if past else None,
                        quantity_component=q,within_product_amount_component=m))
    return out


def summarize(products,classes,daily):
    comparisons={t:compare(products,classes,t,h) for t,h in HISTORY.items()};base=comparisons['2019-10-25']
    negatives=sorted([r for r in base if r['amount_difference']<0],key=lambda r:(r['amount_difference'],r['product_id']))
    positives=sorted([r for r in base if r['amount_difference']>0],key=lambda r:(-r['amount_difference'],r['product_id']))
    chosen=negatives[:5]+positives[:2]
    aliases={r['product_id']:'product_'+chr(65+i) for i,r in enumerate(chosen)}
    roles={r['product_id']:'decline_top5' if r['amount_difference']<0 else 'offset_top2' for r in chosen}
    parts=[];focus=[];days=[]
    for d in daily:
        row=dict(utc_date=d['utc_date'],purchase_events=d['purchase_events'],purchase_product_ids=d['purchase_product_ids'],
                 purchase_users=d['purchase_users'],purchase_amount=d['purchase_amount'],mean_record_amount=F(d['purchase_amount'])/d['purchase_events'],
                 history_dates=[],history_event_total=None,history_days=None,history_mean_events=None,history_mean_amount=None,
                 history_weighted_record_amount=None,amount_difference=None,event_relative_change=None,mean_record_relative_change=None,
                 negative_amount_sum=None,positive_amount_sum=None,top1_negative_coverage=None,top5_negative_coverage=None)
        if d['utc_date'] in comparisons:
            rr=comparisons[d['utc_date']];hist=HISTORY[d['utc_date']]
            n0=sum(r['history_mean_events'] for r in rr);v0=sum(r['history_mean_amount'] for r in rr)
            neg=-sum((r['amount_difference'] for r in rr if r['amount_difference']<0),F(0));pos=sum((r['amount_difference'] for r in rr if r['amount_difference']>0),F(0))
            delta=F(d['purchase_amount'])-v0
            require(pos-neg==delta,'signed product conservation failed')
            row.update(history_dates=hist,history_event_total=n0*len(hist),history_days=len(hist),history_mean_events=n0,history_mean_amount=v0,
                       history_weighted_record_amount=v0/n0,amount_difference=delta,event_relative_change=F(d['purchase_events'])/n0-1,
                       mean_record_relative_change=row['mean_record_amount']/(v0/n0)-1,negative_amount_sum=neg,positive_amount_sum=pos)
            require(F(d['purchase_events'])*row['mean_record_amount']==F(d['purchase_amount']),'category identity failed')
            if d['utc_date']=='2019-10-25':
                row.update(top1_negative_coverage=-negatives[0]['amount_difference']/neg if negatives else None,
                           top5_negative_coverage=-sum((r['amount_difference'] for r in negatives[:5]),F(0))/neg if neg else None)
            for part in PARTS:
                group=[r for r in rr if r['part']==part]
                parts.append(dict(target_date=d['utc_date'],part=part,products=len(group),current_events=sum(r['current_purchase_events'] for r in group),
                                  history_mean_events=sum(r['history_mean_events'] for r in group),current_amount=sum(r['current_amount'] for r in group),
                                  history_mean_amount=sum(r['history_mean_amount'] for r in group),amount_difference=sum(r['amount_difference'] for r in group),
                                  quantity_component=sum((r['quantity_component'] for r in group),F(0)) if part=='stable_common' else None,
                                  within_product_amount_component=sum((r['within_product_amount_component'] for r in group),F(0)) if part=='stable_common' else None))
            require(sum(r['amount_difference'] for r in parts if r['target_date']==d['utc_date'])==delta,'four-part conservation failed')
            lookup={r['product_id']:r for r in rr}
            for p,alias in aliases.items():
                r=lookup.get(p)
                if r is None:
                    # A frozen focus product can have no purchases on either side of a later comparison.
                    r=dict(target_date=d['utc_date'],product_id=p,part='neither_side_observed',history_dates=hist,
                           history_purchase_events=F(0),history_mean_events=F(0),current_purchase_events=F(0),history_mean_amount=F(0),current_amount=F(0),
                           amount_difference=F(0),history_record_mean=None,current_record_mean=None,current_record_min=None,current_record_max=None,
                           history_record_min=None,history_record_max=None,quantity_component=None,within_product_amount_component=None)
                focus.append(dict(product_alias=alias,role=roles[p],**{k:v for k,v in r.items() if k!='product_id'},
                                  classification_stable=classes[p]['stable'],other_known=classes[p]['other_known'],unknown_observed=classes[p]['unknown']))
        days.append(row)
    return days,parts,focus,comparisons,aliases


def analysis(c):
    c.execute((ROOT/'sql/quality/computers_product_mix.sql').read_text())
    daily=bounded(c,'SELECT * FROM category_check ORDER BY utc_date',limit=6)
    require(all(r['bad_purchase_amount']==r['bad_purchase_product_id']==0 for r in daily),'purchase amount or product identity invalid')
    products=bounded(c,'SELECT * FROM product_daily ORDER BY utc_date,product_id',limit=10000)
    categories=bounded(c,'SELECT * FROM product_categories ORDER BY product_id,category_key',limit=10000)
    classes=classify(categories)
    for d in daily:
        p=[r for r in products if r['utc_date']==d['utc_date']]
        require(sum(r['purchase_events'] for r in p)==d['purchase_events'] and sum(r['purchase_amount'] for r in p)==d['purchase_amount'],'product-category mismatch')
    return daily,products,categories,classes


def run(run_id):
    import duckdb
    require(run_id.replace('-','').isalnum(),'invalid run id')
    BASE.mkdir(exist_ok=True);run=BASE/run_id;run.mkdir(exist_ok=False);stage=run/'staging';stage.mkdir()
    start=time.monotonic();c=None;stop=threading.Event();failures=[];protected={}
    def budget():
        used=sum(p.stat().st_size for p in BASE.rglob('*') if p.is_file());free=shutil.disk_usage(ROOT).free
        require(used<2*1024**3 and free>150*1024**3,'budget exceeded')
        return dict(new_local_bytes=used,free_bytes=free)
    def guard(path,expected=None):
        path=Path(path);sha=digest(path)
        require(expected is None or sha==expected,'evidence/file fingerprint mismatch: '+path.name)
        protected[str(path.relative_to(ROOT))]=sha;return json.loads(path.read_text()) if path.suffix=='.json' else sha
    try:
        require(budget()['free_bytes']-2*1024**3>150*1024**3,'projected free space')
        scope=guard(ROOT/'reports/cross_period/analysis_scope.json')
        require(scope['analysis_scope_version']=='rees46_oct_nov_user5_analysis_v1' and scope['duplicate_policy']=='baseline_keep_all','scope mismatch')
        guard(ROOT/'reports/cross_period/category_daily.csv',scope['result_files']['category_daily.csv'])
        mc=guard(ROOT/'config/metrics.local.json');registry=load_registry(ROOT,mc['registry_path'])
        require(len(registry['batches'])==1,'ambiguous October batch');entry=registry['batches'][0];d=entry['descriptor']
        require(d['run_id']==scope['october']['fact_run']=='month-v101-01' and d['input_sha256']==scope['october']['candidate_sha256'],'October canonical mismatch')
        current=inspect_batch(ROOT,d)
        require(registered_batch_matches(current,entry,allow_criteo_manifest_extension=True),'October registered evidence mismatch')
        for day in DAYS[:4]:require(entry['gates'][day]['count_allowed'] and entry['gates'][day]['amount_allowed'],'October date blocked')
        for item in current['inventory']:protected[item['path']]=item['sha256']
        for name in entry['evidence']:guard(ROOT/name)
        guard(ROOT/mc['registry_path'])
        novroot=ROOT/'.local/t4_cross_period';np=scope['november']
        proof=guard(novroot/np['metrics_run']/'complete/validation.json',np['metrics_receipt_sha256'])
        parent=proof['parent_verified_metrics'];require(parent['run_id']=='nov-metrics-01','unrecognized November detail run')
        old=guard(novroot/parent['run_id']/'complete/validation.json',parent['receipt_sha256'])
        require(old['status']=='passed' and old['scope_id']==np['candidate_scope'] and old['candidate_sha256']==np['candidate_sha256']
                and old['contract_version']=='rees46-events-v1.0.1' and old['multiset_checks']=={'expected_minus_actual':0,'actual_minus_expected':0},'November proof mismatch')
        for day in DAYS[4:]:require(old['gates'][day]['count_allowed'] and old['gates'][day]['amount_allowed'],'November date blocked')
        db=novroot/parent['run_id']/'complete/metrics.duckdb';guard(db)
        for name in ('reports/cross_period_business_review.md','reports/purchase_timing_review.md','docs/metric_contract.md','requirements.lock.txt'):
            guard(ROOT/name)
        c=duckdb.connect(':memory:',config={'threads':'4','memory_limit':'1GB','temp_directory':str(stage/'temp'),
            'max_temp_directory_size':'512MB','autoinstall_known_extensions':'false','autoload_known_extensions':'false'})
        c.execute("SET TimeZone='UTC'")
        attach_read_only(c,db)
        def monitor():
            while not stop.wait(2):
                try:budget()
                except Exception as exc:failures.append(str(exc));c.interrupt();return
        watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
        octpaths=[str(ROOT/item['path']) for item in current['inventory']]
        # Date predicates and only required columns; no source/candidate CSV or full fact reconstruction.
        c.execute('''CREATE TEMP TABLE scoped_events AS
          SELECT CAST(event_date_utc AS VARCHAR) utc_date,event_type,product_id,category_code,user_id,
                 price_decimal,event_eligible,amount_eligible
          FROM read_parquet(?) WHERE CAST(event_date_utc AS VARCHAR) IN (SELECT unnest(?))
          UNION ALL
          SELECT CAST(utc_date AS VARCHAR),event_type,product_id,category_code,user_id,
                 price_decimal,event_eligible,amount_eligible
          FROM november.parsed WHERE CAST(utc_date AS VARCHAR) IN (SELECT unnest(?))''',[octpaths,DAYS[:4],DAYS[4:]])
        daily,products,categories,classes=analysis(c)
        expected={r['utc_date']:r for r in csv.DictReader((ROOT/'reports/cross_period/category_daily.csv').open()) if r['category_key']=='category:computers' and r['utc_date'] in DAYS}
        require([r['utc_date'] for r in daily]==DAYS,'missing day')
        for r in daily:
            e=expected[r['utc_date']]
            require(e['count_allowed']==e['amount_allowed']=='True','summary quality blocked')
            for key in ('event_records','purchase_events','purchase_amount'):require(F(r[key])==F(e[key]),'existing category reconciliation failed '+r['utc_date']+' '+key)
        days,parts,focus,comparisons,aliases=summarize(products,classes,daily)
        csv_write(stage/'product_daily_local.csv',[dict(r,mean_record_amount=F(r['purchase_amount'])/r['purchase_events']) for r in products])
        csv_write(stage/'product_categories_local.csv',categories)
        dump(stage/'all_comparisons_local.json',comparisons);dump(stage/'alias_map_local.json',aliases)
        csv_write(stage/'daily_comparison.csv',days);csv_write(stage/'decomposition.csv',parts);csv_write(stage/'focus_products.csv',focus)
        stop.set();watcher.join();c.close();c=None;require(not failures,'resource monitor failed')
        for name,sha in protected.items():require(digest(ROOT/name)==sha,'protected file changed')
        proof=dict(status='passed',run_id=run_id,analysis_scope=scope['analysis_scope_version'],dates=DAYS,histories=HISTORY,
                   source_runs=['month-v101-01','nov-metrics-01'],november_canonical_summary_run=np['metrics_run'],duplicate_policy='baseline_keep_all',
                   elapsed_seconds=round(time.monotonic()-start,3),versions=dict(python=sys.version.split()[0],duckdb=duckdb.__version__),
                   rows=dict(daily=len(days),product_daily=len(products),product_categories=len(categories),distinct_purchase_products=len(classes)),
                   classification=dict(stable=sum(x['stable'] for x in classes.values()),other_known=sum(x['other_known'] for x in classes.values()),unknown=sum(x['unknown'] for x in classes.values())),
                   checks=dict(six_day_category_reconciliation=True,product_sums=True,four_parts_exact=True,common_product_identity_exact=True,
                               fixed_focus_tracking=True,protected_files_unchanged=True),protected_hashes=protected,resources=budget(),peak_memory='not_measured',
                   code_hashes={n:digest(ROOT/n) for n in ('scripts/review_computers_mix.py','sql/quality/computers_product_mix.sql')},
                   safe_csv_sha256={n:digest(stage/n) for n in ('daily_comparison.csv','decomposition.csv','focus_products.csv')})
        dump(stage/'validation.json',proof);stage.rename(run/'complete');print(json.dumps(serialized({k:v for k,v in proof.items() if k!='protected_hashes'})),flush=True)
    except BaseException as exc:
        dump(run/'failure.json',dict(status='failed',error=type(exc).__name__,message=str(exc),elapsed_seconds=time.monotonic()-start));raise
    finally:
        stop.set()
        if c:c.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);run(p.parse_args().run_id)
