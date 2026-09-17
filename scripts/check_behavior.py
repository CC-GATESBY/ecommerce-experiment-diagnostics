"""Independent standard-library arithmetic over the report CSVs and receipts."""
import argparse
import csv
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def rows(path):
    with Path(path).open(newline='') as f:return list(csv.DictReader(f))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def category_amendment(path,report):
    proof=json.loads(Path(path).read_text())
    before=json.loads((Path(path).parent/'preflight.json').read_text())
    launch=json.loads((Path(path).parent.parent/'launch.json').read_text())
    if not (proof['status']==launch['status']=='passed' and proof['spark_stopped'] and proof['fact_loads']==1
            and proof['source_run']=='month-v101-01' and proof['analysis_scope']=='rees46_oct_user5_analysis_v1'
            and proof['checks'] and all(r['pass'] for r in proof['checks'].values())):
        raise ValueError('unsuccessful category closeout')
    if sha(report/'category_concentration.csv')!=proof['category_csv_after_sha256'] or before['category_csv_sha256']!=proof['category_csv_before_sha256']:
        raise ValueError('category closeout fingerprint mismatch')
    actual=rows(report/'category_concentration.csv');old=before['old_categories']
    if len(actual)!=14 or len(old)!=14:raise ValueError('category closeout requires 14 buckets')
    for prior,current in zip(old,actual):
        if {k:v for k,v in prior.items() if k not in ('users','buyers','monthly_distinct_status')}!={k:v for k,v in current.items() if k not in ('users','buyers','monthly_distinct_status')}:
            raise ValueError('category closeout changed protected columns')
    return proof


def verify(prepared,hourly,render,output,category_closeout=None):
    prep=json.loads(Path(prepared).read_text());hour=json.loads(Path(hourly).read_text());fig=json.loads(Path(render).read_text())
    checks=[]
    def eq(name,want,got):
        ok=want==got;checks.append(dict(check=name,expected=str(want),actual=str(got),pass_check=ok))
        if not ok:raise AssertionError(name+': '+str(want)+' != '+str(got))
    report=ROOT/'reports';daily=rows(report/'behavior_daily.csv');stats=rows(report/'behavior_daily_stats.csv');categories=rows(report/'category_concentration.csv');hours=rows(report/'hourly_purchase.csv')
    closeout=category_amendment(category_closeout,report) if category_closeout else None
    original=json.loads((ROOT/prep['config']['metrics_run']/'complete/validation.json').read_text());month=original['month']
    eq('31_days',31,len(daily));eq('exact_dates',[f'2019-10-{d:02d}' for d in range(1,32)],[r['utc_date'] for r in daily])
    max_error=0.
    for r in daily:
        old=next(v for v in original['daily'] if v['utc_date']==r['utc_date'])
        for k,v in r.items():eq('historical_'+r['utc_date']+'_'+k,str(old[k]),v)
        u,b,v=int(r['active_users']),int(r['buyers']),Decimal(r['purchase_amount']);rr=Decimal(r['buyer_rate']);m=Decimal(r['amount_per_buyer'])
        eq('buyer_rate_'+r['utc_date'],True,math.isclose(float(rr),b/u,abs_tol=1e-6,rel_tol=1e-10))
        eq('amount_per_buyer_'+r['utc_date'],True,math.isclose(float(m),float(v/Decimal(b)),abs_tol=1e-6,rel_tol=1e-10))
        err=abs(float(v)-float(Decimal(u)*rr*m));max_error=max(max_error,err)
        eq('identity_'+r['utc_date'],True,math.isclose(float(v),float(Decimal(u)*rr*m),abs_tol=1e-6,rel_tol=1e-10))
    for s in stats:
        values=sorted(Decimal(r[s['metric']]) for r in daily if r[s['metric']]!='');n=len(values)
        median=values[n//2] if n%2 else (values[n//2-1]+values[n//2])/2
        for name,expected in [('min',values[0]),('max',values[-1]),('median',median)]:eq('stats_'+s['metric']+'_'+name,expected,Decimal(s[name]))
        eq('stats_dates_min_'+s['metric'],';'.join(r['utc_date'] for r in daily if Decimal(r[s['metric']])==values[0]),s['min_dates'])
        eq('stats_dates_max_'+s['metric'],';'.join(r['utc_date'] for r in daily if Decimal(r[s['metric']])==values[-1]),s['max_dates'])
    raw=json.loads((Path(prepared).parent/'category_daily_expected.json').read_text());expected={}
    for r in raw:
        k=r['dim_value_key'];g=expected.setdefault(k,[Decimal(0),0,0,0]);g[0]+=Decimal(r['purchase_amount']);g[1]+=r['purchase_events'];g[2]+=r['users'];g[3]+=r['buyers']
    eq('category_keys',sorted(expected),sorted(r['category_key'] for r in categories))
    total=Decimal(month['purchase_amount']);cumulative=Decimal(0)
    ordered=sorted(expected,key=lambda k:(-expected[k][0],k));eq('amount_sort',ordered,[r['category_key'] for r in categories])
    for r in categories:
        want=expected[r['category_key']];eq('category_values_'+r['category_key'],want,[Decimal(r['purchase_amount']),int(r['purchase_events']),int(r['user_days']),int(r['buyer_user_days'])])
        cumulative+=want[0]
        eq('category_share_'+r['category_key'],True,abs(Decimal(r['amount_share'])-want[0]/total)<Decimal('1e-15'))
        eq('cumulative_share_'+r['category_key'],True,abs(Decimal(r['cumulative_amount_share'])-cumulative/total)<Decimal('1e-15'))
        if closeout:
            measured=next(v for v in closeout['monthly'] if v['category_key']==r['category_key'])
            eq('measured_month_users_'+r['category_key'],(str(measured['users']),str(measured['buyers']),'measured_from_fact_monthly_distinct'),(r['users'],r['buyers'],r['monthly_distinct_status']))
        else:
            eq('not_fabricated_month_users_'+r['category_key'],('','','not_measured_daily_counts_not_additive'),(r['users'],r['buyers'],r['monthly_distinct_status']))
    eq('category_total_amount',total,sum((Decimal(r['purchase_amount']) for r in categories),Decimal(0)))
    eq('category_total_purchase_events',month['purchase_events'],sum(int(r['purchase_events']) for r in categories))
    old_unknown=next(r for r in original['unknown_dimensions'] if r['dim_name']=='category_l1')
    eq('unknown_amount',Decimal(old_unknown['purchase_amount']),sum((Decimal(r['purchase_amount']) for r in categories if r['is_unknown']=='True'),Decimal(0)))
    eq('hour_buckets',list(range(24)),[int(r['utc_hour']) for r in hours]);eq('hour_events_total',month['purchase_events'],sum(int(r['purchase_events']) for r in hours))
    eq('hour_amount_total',total,sum((Decimal(r['purchase_amount']) for r in hours),Decimal(0)))
    for r in hours:
        old=next(v for v in hour['hours'] if v['utc_hour']==int(r['utc_hour']))
        for field,value in old.items():eq('hour_receipt_'+r['utc_hour']+'_'+field,str(value),r[field])
        eq('hour_share_'+r['utc_hour'],True,abs(Decimal(r['purchase_events_share'])-Decimal(r['purchase_events'])/Decimal(month['purchase_events']))<Decimal('1e-15'))
    eq('monthly_active_users_source',month['active_users'],prep['month']['active_users']);eq('monthly_buyers_source',month['buyers'],prep['month']['buyers'])
    eq('figure_count',8,len(fig['figures']))
    for f in fig['figures']:
        source=report/f['source_csv']
        if closeout and f['source_csv']=='category_concentration.csv':
            eq('original_figure_source_'+f['figure'],f['source_sha256'],closeout['category_csv_before_sha256'])
            eq('amended_figure_source_'+f['figure'],closeout['category_csv_after_sha256'],sha(source))
        else: eq('figure_source_'+f['figure'],f['source_sha256'],sha(source))
        data=rows(source)
        if f['kind']=='daily_line':
            field={'daily_purchase_amount.png':'purchase_amount','daily_active_users.png':'active_users','daily_buyer_rate.png':'buyer_rate','daily_amount_per_buyer.png':'amount_per_buyer'}[f['figure']]
            vals=[float(r[field]) if r[field] else None for r in data];keys=[r['utc_date'] for r in data]
        elif f['kind']=='ratio_bar':
            r=next(v for v in data if v['level']=='overall');keys=['view_to_cart','cart_to_purchase_three_step','view_to_purchase','three_step_ratio'];vals=[float(r[k]) if r[k] else None for k in keys]
        elif f['kind']=='price_ratio_bar':
            keys=['[0,20)','[20,50)','[50,200)','[200,+inf)','unknown'];d={r['segment']:r for r in data if r['level']=='price_band'};vals=[float(d[k]['view_to_purchase']) if d[k]['view_to_purchase'] else None for k in keys]
            eq('unknown_is_na',None,vals[-1])
        elif f['kind']=='category_bar':
            data=sorted(data,key=lambda r:int(r['amount_rank']))[:10];keys=[r['category_key'] for r in data];vals=[float(r['purchase_amount']) for r in data]
        else:keys=[int(r['utc_hour']) for r in data];vals=[float(r['purchase_events']) for r in data]
        eq('figure_keys_'+f['figure'],keys,f['keys']);eq('figure_values_'+f['figure'],vals,f['artist_values'])
        eq('figure_image_'+f['figure'],f['image_sha256'],sha(Path(render).parent/f['figure']))
    preflight=json.loads((ROOT/'.local/t22/preflight.json').read_text())
    eq('old_local_metadata_unchanged',True,all((ROOT/p).is_file() and [(ROOT/p).stat().st_size,(ROOT/p).stat().st_mtime_ns]==v for p,v in preflight['protected_stat'].items()))
    for p,value in preflight['protected_sha256'].items():eq('old_tracked_'+p,value,sha(ROOT/p))
    with Path(output).open('x') as f:json.dump(dict(status='passed',checks=checks,max_identity_absolute_error=max_error),f,indent=2)
    print(json.dumps(dict(status='passed',checks=len(checks),max_identity_absolute_error=max_error)))
    return checks


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepared',required=True);p.add_argument('--hourly',required=True);p.add_argument('--render',required=True);p.add_argument('--output',required=True);p.add_argument('--category-closeout');a=p.parse_args();verify(a.prepared,a.hourly,a.render,a.output,a.category_closeout)
