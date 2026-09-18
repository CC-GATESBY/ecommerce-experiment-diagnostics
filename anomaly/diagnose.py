"""Frozen screening, accounting decomposition and independent dimension comparisons."""
from datetime import date, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction as F
import math
from statistics import median

DIMENSIONS = ('category_l1','brand_group','price_band','is_first_seen_day')
EPS = F('1e-10')


def rational(value):
    return value if isinstance(value,F) else F(str(value))


def serialized(value):
    if isinstance(value,F):
        with localcontext() as c:
            c.prec=36
            return str(Decimal(value.numerator)/Decimal(value.denominator))
    if isinstance(value,Decimal): return str(value)
    if isinstance(value,(date,)): return value.isoformat()
    if isinstance(value,dict): return {k:serialized(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)): return [serialized(v) for v in value]
    return value


def usable(row):
    return bool(row and row['count_allowed'] and row['amount_allowed'] and row['purchase_amount'] is not None)


def screen(daily, dates, cfg):
    known={r['utc_date']:r for r in daily}
    if len(known)!=len(daily) or len(set(dates))!=len(dates):raise ValueError('duplicate dates')
    output=[]
    for day in dates:
        wanted=[(date.fromisoformat(day)-timedelta(days=n)).isoformat() for n in cfg['history_offsets_days']]
        available=[d for d in wanted if usable(known.get(d))]
        reasons=[('outside_observation:' if d not in dates else 'missing_date:' if d not in known else 'quality_blocked:')+d
                 for d in wanted if d not in available]
        gaps=[d for d in wanted if d in dates and d not in available]
        current=known.get(day)
        row=dict(utc_date=day,history_dates=available,history_count=len(available),reason=';'.join(reasons),
                 current_amount=current['purchase_amount'] if current else None,median_amount=None,mad=None,scale=None,
                 score=None,amount_difference=None,relative_change=None,candidate=False,comparable=False,status='')
        if not usable(current): row['status']='current_date_missing' if current is None else 'current_quality_blocked'
        elif len(available)<cfg['min_history_points']:row['status']='insufficient_history_with_gaps' if gaps else 'insufficient_history'
        else:
            values=[rational(known[d]['purchase_amount']) for d in available]
            center=median(values);v=rational(current['purchase_amount']);mad=median([abs(x-center) for x in values])
            row.update(median_amount=center,mad=mad,scale=mad*rational(cfg['mad_scale']),amount_difference=v-center)
            if v<0 or any(x<0 for x in values):row['status']='negative_amount_invalid'
            elif center<=0:row['status']='zero_baseline'
            else:
                row.update(relative_change=(v-center)/center,comparable=True)
                if mad==0:row['status']='zero_scale'
                else:
                    score=(v-center)/row['scale']
                    row.update(score=score,candidate=abs(score)>rational(cfg['score_abs_gt']) and
                               abs(row['relative_change'])>=rational(cfg['relative_change_abs_gte']),
                               status='evaluated_with_history_gaps' if gaps else 'evaluated')
        output.append(row)
    return output


def select_case(flags):
    down=[r for r in flags if r['candidate'] and r['amount_difference']<0]
    candidates=[r for r in flags if r['candidate']]
    comparable=[r for r in flags if r['comparable']]
    pool=down or candidates or comparable
    if not pool:return None,'no_comparable_date'
    chosen=sorted(pool,key=lambda r:(-abs(r['amount_difference']),r['utc_date']))[0]
    return chosen,('downward_candidate' if down else 'other_candidate' if candidates else 'descriptive_not_candidate')


def decompose(current, history):
    if not history or not usable(current) or not all(usable(r) for r in history):
        return dict(status='quality_or_history_unavailable',rows=[])
    now={k:rational(current[v]) for k,v in [('U','active_users'),('B','buyers'),('V','purchase_amount')]}
    base={k:sum((rational(r[v]) for r in history),F(0))/len(history)
          for k,v in [('U','active_users'),('B','buyers'),('V','purchase_amount')]}
    if any(x<=0 for x in [*now.values(),*base.values()]):return dict(status='nonpositive_factor_or_amount',rows=[])
    for values in (now,base):values.update(R=values['B']/values['U'],M=values['V']/values['B'])
    total_log=math.log(float(now['V']/base['V']));small=abs(total_log)<=float(EPS)
    rows=[]
    for key in ('U','B','R','M','V'):
        log=math.log(float(now[key]/base[key]))
        rows.append(dict(factor=key,current=now[key],history_mean_derived=base[key],relative_change=now[key]/base[key]-1,
                         log_change=log,log_contribution_share=log/total_log if key in ('U','R','M') and not small else None))
    residual=sum(r['log_change'] for r in rows if r['factor'] in ('U','R','M'))-total_log
    if abs(residual)>1e-12:raise ValueError('log identity failed')
    return dict(status='near_zero_total_log' if small else 'applicable',rows=rows,
                total_amount_difference=now['V']-base['V'],log_identity_residual=residual)


def validate_dimensions(daily, dims):
    """Only complete date/dimension totals authorize zero for absent buckets."""
    known={r['utc_date']:r for r in daily};seen=set();groups={}
    for r in dims:
        key=(r['utc_date'],r['dim_name'],r['dim_value_key'])
        if key in seen:raise ValueError('duplicate dimension key')
        seen.add(key)
        if r['utc_date'] not in known or r['dim_name'] not in DIMENSIONS:raise ValueError('unknown dimension/date')
        if not usable(r) or not usable(known[r['utc_date']]):raise ValueError('dimension/date quality blocked')
        groups.setdefault(key[:2],[]).append(r)
    for day,total in known.items():
        for dim in DIMENSIONS:
            rows=groups.get((day,dim))
            if not rows:raise ValueError('missing whole date/dimension')
            for field in ('event_records','purchase_events','purchase_amount'):
                if sum((rational(r[field]) for r in rows),F(0))!=rational(total[field]):
                    raise ValueError('dimension conservation failed: '+field)
    return groups


def js_components(a,b):
    if any(x<0 for x in a+b):raise ValueError('negative distribution')
    sa,sb=sum(a),sum(b)
    if sa<=0 or sb<=0:return None,[None]*len(a)
    p=[float(x/sa) for x in a];q=[float(x/sb) for x in b];terms=[]
    for x,y in zip(p,q):
        m=(x+y)/2
        terms.append(.5*((x*math.log2(x/m) if x else 0)+(y*math.log2(y/m) if y else 0)))
    return sum(terms),terms


def attribute(groups,day,hist,dim,cfg):
    required=[(d,dim) for d in [day,*hist]]
    if not hist or any(k not in groups for k in required):raise ValueError('missing dimension date')
    current={r['dim_value_key']:r for r in groups[(day,dim)]};base={};labels={}
    for d in [day,*hist]:
        for r in groups[(d,dim)]:
            if labels.setdefault(r['dim_value_key'],r['dim_value_label'])!=r['dim_value_label']:
                raise ValueError('dimension label changed')
            if d!=day:base[r['dim_value_key']]=base.get(r['dim_value_key'],F(0))+rational(r['purchase_amount'])
    keys=sorted(set(current)|set(base));a=[rational(current[k]['purchase_amount']) if k in current else F(0) for k in keys]
    b=[base.get(k,F(0))/len(hist) for k in keys];ta,tb=sum(a),sum(b);delta=ta-tb
    near=abs(delta)<=EPS*max(abs(ta),abs(tb),F(1));js,terms=js_components(a,b)
    rows=[]
    for k,x,y,term in zip(keys,a,b,terms):
        change=x-y
        direction=('same_direction' if change*delta>0 else 'offsetting' if change*delta<0 else 'unchanged' if change==0 else 'total_near_zero')
        rows.append(dict(utc_date=day,dim_name=dim,dim_value_key=k,dim_value_label=labels[k],current_amount=x,
                         history_amount_sum=base.get(k,F(0)),history_days=len(hist),history_mean_amount=y,amount_difference=change,
                         current_share=x/ta if ta>0 else None,history_share=y/tb if tb>0 else None,
                         signed_contribution=change/delta if not near else None,direction=direction,js_component=term))
    same=sorted([r for r in rows if r['direction']=='same_direction'],key=lambda r:(-abs(r['amount_difference']),r['dim_value_key']))
    offsets=sorted([r for r in rows if r['direction']=='offsetting'],key=lambda r:(-abs(r['amount_difference']),r['dim_value_key']))
    pool=sum((abs(r['amount_difference']) for r in same),F(0));cumulative=F(0)
    for rank,r in enumerate(same,1):
        cumulative+=abs(r['amount_difference']);r.update(direction_rank=rank,cumulative_same_direction_share=cumulative/pool)
    for rank,r in enumerate(offsets,1):r.update(direction_rank=rank,cumulative_same_direction_share=None)
    for r in rows:
        r.setdefault('direction_rank',None);r.setdefault('cumulative_same_direction_share',None)
        r['share_status']='near_zero_total_difference' if near else 'defined'
    # Exact rational conservation, including non-terminating means.
    assert sum((r['amount_difference'] for r in rows),F(0))==delta
    hit=next((r['direction_rank'] for r in same if r['cumulative_same_direction_share']>=rational(cfg['summary_same_direction_coverage'])),None)
    summary=dict(dim_name=dim,current_total=ta,history_mean_total=tb,total_difference=delta,js_divergence=js,
                 js_status='defined' if js is not None else 'zero_distribution',same_direction_abs_sum=pool,
                 offsetting_abs_sum=sum((abs(r['amount_difference']) for r in offsets),F(0)),
                 buckets_to_same_direction_67pct=hit,top_k=cfg['summary_top_k'])
    return rows,summary


def coverage(groups,daily,day,hist):
    known={r['utc_date']:r for r in daily};out=[]
    for field in ('event_records','purchase_events','purchase_amount'):
        vals={}
        for tag,days in [('current',[day]),('history',hist)]:
            total=sum((rational(known[d][field]) for d in days),F(0))
            unknown=sum((rational(r[field]) for d in days for r in groups[(d,'category_l1')]
                         if r['dim_value_key']=='bucket:unknown'),F(0))
            vals.update({tag+'_total':total,tag+'_unknown':unknown,
                         tag+'_known_coverage':(total-unknown)/total if total>0 else None})
        out.append(dict(metric=field,history_days=len(hist),**vals))
    return out
