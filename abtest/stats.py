"""Small B-minus-A interfaces; distributions supplied by SciPy."""
import math
import numpy as np
from scipy.stats import norm, t, binomtest


def base(n_a,n_b,method,unit):
    r=dict(n_A=n_a,n_B=n_b,method=method,unit=unit,status='ok',reason='')
    r.update({k:None for k in ('mean_A','mean_B','difference','se','df','ci_low','ci_high','p_value')})
    if not n_a or not n_b:r.update(status='empty_group',reason='both groups must contain users')
    elif min(n_a,n_b)<2:r.update(status='insufficient_n',reason='at least two users per group')
    return r


def finish(r,variance,df=None):
    r['se']=math.sqrt(variance);r['df']=df
    if variance<=0:
        r.update(status='zero_variance',reason='no sampling SE; inference withheld');return r
    dist=norm if df is None else t(df)
    critical=float(dist.ppf(.975));half=critical*r['se']
    r.update(ci_low=r['difference']-half,ci_high=r['difference']+half,
             p_value=float(2*dist.sf(abs(r['difference']/r['se']))))
    return r


def proportions(n_a,k_a,n_b,k_b):
    if any(type(x) is not int or x<0 for x in (n_a,n_b,k_a,k_b)) or k_a>n_a or k_b>n_b:
        raise ValueError('invalid binary counts')
    r=base(n_a,n_b,'unpooled_wald_z_min_cell_10','probability')
    if r['status']!='ok':return r
    a,b=k_a/n_a,k_b/n_b
    r.update(mean_A=a,mean_B=b,difference=b-a,difference_pp=(b-a)*100,
             difference_per_10000=(b-a)*10000,relative_change=(b-a)/a if a else None)
    if min(k_a,n_a-k_a,k_b,n_b-k_b)<10:
        r.update(status='sparse_cells',reason='minimum success/failure cell below 10');return r
    return finish(r,a*(1-a)/n_a+b*(1-b)/n_b)


def welch(a,b):
    a,b=np.asarray(a,dtype=np.float64),np.asarray(b,dtype=np.float64)
    if a.ndim!=1 or b.ndim!=1:raise ValueError('one outcome per user required')
    r=base(len(a),len(b),'welch_t','observed_amount_per_enrolled_user')
    if r['status']!='ok':return r
    if not (np.isfinite(a).all() and np.isfinite(b).all()):
        r.update(status='nonfinite_input',reason='all outcomes must be finite');return r
    r.update(mean_A=float(a.mean()),mean_B=float(b.mean()),difference=float(b.mean()-a.mean()))
    va,vb=float(a.var(ddof=1)/len(a)),float(b.var(ddof=1)/len(b))
    v=va+vb
    df=v*v/(va*va/(len(a)-1)+vb*vb/(len(b)-1)) if v>0 else None
    return finish(r,v,df)


def ratio_difference(a,b):
    a,b=np.asarray(a,dtype=float),np.asarray(b,dtype=float)
    if a.size==0:a=a.reshape(0,2)
    if b.size==0:b=b.reshape(0,2)
    if any(x.ndim!=2 or x.shape[1]!=2 for x in (a,b)):raise ValueError('paired X,Y columns required')
    r=base(len(a),len(b),'paired_ratio_delta_z','ratio_of_sums')
    if r['status']!='ok':return r
    if any(not np.isfinite(x).all() or (x[:,1]<0).any() for x in (a,b)):
        r.update(status='invalid_pairs',reason='finite X and nonnegative Y required');return r
    if any(x[:,1].sum()==0 for x in (a,b)):
        r.update(status='zero_denominator',reason='group denominator sum is zero');return r
    def moments(x):
        ratio=float(x[:,0].sum()/x[:,1].sum())
        residual=x[:,0]-ratio*x[:,1]
        variance=float(residual.var(ddof=1)/(len(x)*x[:,1].mean()**2))
        return ratio,variance
    ra,va=moments(a);rb,vb=moments(b)
    r.update(mean_A=ra,mean_B=rb,difference=rb-ra)
    return finish(r,va+vb)


def wilson(k,n):
    if not n:return (None,None)
    ci=binomtest(k,n).proportion_ci(confidence_level=.95,method='wilson')
    return float(ci.low),float(ci.high)


def bootstrap_pairs(a,b,*,seed,repeats):
    """Only synthetic data: the same sampled index selects both columns."""
    rng=np.random.Generator(np.random.PCG64(seed)); ratios=[]
    for data in (np.asarray(a,dtype=float),np.asarray(b,dtype=float)):
        indices=rng.integers(0,len(data),size=(repeats,len(data)))
        totals=data[indices].sum(axis=1)
        with np.errstate(divide='ignore',invalid='ignore'):
            ratios.append(totals[:,0]/totals[:,1])
    return ratios[1]-ratios[0]


def ratio_validation(seed=20260921,repeats=6000,batches=30):
    y=[0,1,2,1,2,2,3,2,3,4,3,4]
    a=np.tile(np.column_stack(([0,1,2,1,3,2,4,2,3,5,4,6],y)),(10,1))
    b=np.tile(np.column_stack(([0,2,2,2,3,3,4,3,4,5,5,6],y)),(8,1))
    delta=ratio_difference(a,b);samples=bootstrap_pairs(a,b,seed=seed,repeats=repeats)
    if not np.isfinite(samples).all():raise ValueError('synthetic bootstrap invalid denominator')
    se=float(samples.std(ddof=1));batch_se=samples.reshape(batches,-1).std(axis=1,ddof=1)
    return dict(kind='synthetic_only',n_A=len(a),n_B=len(b),delta=delta,bootstrap_repeats=repeats,
                bootstrap_valid=repeats,bootstrap_se=se,relative_se_difference=se/delta['se']-1,
                bootstrap_se_mcse=float(batch_se.std(ddof=1)/np.sqrt(batches)),batches=batches,
                seed=seed,bootstrap_mean=float(samples.mean()),bootstrap_bias=float(samples.mean()-delta['difference']))
