"""Fixed-policy additional evaluation; no model fitting or candidate selection."""
from contextlib import contextmanager
import hashlib
from unittest.mock import patch

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

from uplift import models
from uplift.targeting import require, resample_joint, interval

CAPS = [10, 20, 30, 50, 100]
CONTRASTS = [('RESPONSE_MODEL', 'FROZEN_SIMPLE'), ('S_LEARNER', 'FROZEN_SIMPLE'),
             ('T_LEARNER', 'FROZEN_SIMPLE'), ('RESPONSE_MODEL', 'RANDOM')]


@contextmanager
def no_training():
    """Fail immediately if an accidental training call reaches this workflow."""
    with patch.object(HistGradientBoostingClassifier, 'fit', side_effect=RuntimeError('training forbidden')), \
         patch.object(HistGradientBoostingClassifier, 'partial_fit', create=True,
                      side_effect=RuntimeError('training forbidden')), \
         patch.object(models, 'fit_classifier', side_effect=RuntimeError('training forbidden')):
        yield


def rank_scores(scores, row_ids):
    """No outcome or observed treatment input; full original hash and ID tie break."""
    require(list(scores) == models.POLICIES, 'fixed five-policy order required')
    n = len(row_ids)
    require(n > 0 and len(np.unique(row_ids)) == n, 'nonempty unique record identities required')
    tie = np.fromiter((hashlib.sha256(b'target-v1|20260921|'+bytes(i)).hexdigest().encode()
                       for i in row_ids), dtype='S64', count=n)
    ranks = {}
    for policy, score in scores.items():
        require(score.shape == (n,) and np.isfinite(score).all(), 'invalid score')
        order = np.lexsort((row_ids, tie, -score))
        rank = np.empty(n, dtype=np.int32)
        rank[order] = np.arange(1, n+1, dtype=np.int32)
        ranks[policy] = rank
    return ranks


def validate_ranks(ranks, n):
    require(list(ranks) == models.POLICIES and n > 0, 'five fixed rankings required')
    for rank in ranks.values():
        require(rank.shape == (n,) and np.issubdtype(rank.dtype, np.integer) and
                np.array_equal(np.sort(rank), np.arange(1, n+1)), 'ranking must be a permutation')


def capacity_evaluation(ranks, treatment, conversion, cfg):
    n = len(conversion)
    validate_ranks(ranks, n)
    require(treatment.shape == conversion.shape and np.isin(treatment, [0, 1]).all() and
            np.isin(conversion, [0, 1]).all(), 'binary evaluation fields required')
    require(cfg['capacities_percent'] == CAPS, 'frozen capacity grid required')
    specs = []
    mask = np.zeros(n, dtype=np.uint32)
    for policy, rank in ranks.items():
        previous = np.zeros(n, dtype=bool)
        for cap in CAPS:
            k = cap*n//100
            selected = rank <= k
            require(int(selected.sum()) == k and not (previous & ~selected).any(), 'capacity/nesting mismatch')
            bit = len(specs)
            mask |= selected.astype(np.uint32) << bit
            specs.append(dict(policy=policy, capacity_percent=cap, selected_n=k, c_actual=k/n, bit=bit))
            previous = selected
    # Avoid a dense 2^27 bincount array: nested membership has at most 4*5^5 types.
    encoded = mask.astype(np.uint64) | ((2*treatment.astype(np.uint64)+conversion) << 25)
    keys, counts = np.unique(encoded, return_counts=True)
    require(len(keys) <= cfg['max_joint_types'] == 4*5**5, 'nested joint-type bound exceeded')
    joint = [dict(treatment=int(key >> np.uint64(26)), conversion=int((key >> np.uint64(25)) & np.uint64(1)),
                  mask=int(key & np.uint64(2**25-1)), n=int(count)) for key, count in zip(keys, counts)]
    (ns, ys, rates, deltas, gs), draws, _ = resample_joint(joint, specs, cfg)
    rows = []
    for i, spec in enumerate(specs):
        finite = bool(np.isfinite(gs[i]))
        sparse = min(ys[0,i], ns[0,i]-ys[0,i], ys[1,i], ns[1,i]-ys[1,i]) < cfg['sparse_min_success_or_failure_per_arm']
        rows.append(dict(policy=spec['policy'], split='test_additional', N_test=n,
                         capacity_percent=spec['capacity_percent'], selected_n=spec['selected_n'], c_actual=spec['c_actual'],
                         control_n=int(ns[0,i]), treatment_n=int(ns[1,i]),
                         conversion_control=int(ys[0,i]), conversion_treatment=int(ys[1,i]),
                         p0_S=float(rates[0,i]) if ns[0,i] else None,
                         p1_S=float(rates[1,i]) if ns[1,i] else None,
                         delta_S=float(deltas[i]) if finite else None, G=float(gs[i]) if finite else None,
                         status='zero_denominator' if not finite else ('sparse_not_for_strong_inference' if sparse else
                         'additional_benchmark_conditional_not_confirmatory'), **interval(draws[:,i])))
    differences = []
    for cap in CAPS:
        for first, second in CONTRASTS:
            a, b = [next(i for i, s in enumerate(specs) if s['policy'] == name and s['capacity_percent'] == cap)
                    for name in (first, second)]
            finite = bool(np.isfinite(gs[a]-gs[b]))
            sparse = any(rows[i]['status'] == 'sparse_not_for_strong_inference' for i in (a,b))
            differences.append(dict(capacity_percent=cap, contrast=first+'_minus_'+second,
                role='primary' if cap == 30 and (first,second) == CONTRASTS[0] else 'auxiliary',
                selected_n=cap*n//100, G_difference=float(gs[a]-gs[b]) if finite else None,
                status='zero_denominator' if not finite else ('sparse_not_for_strong_inference' if sparse else
                'additional_benchmark_conditional_not_confirmatory'), **interval(draws[:,a]-draws[:,b])))
    full = [i for i,s in enumerate(specs) if s['capacity_percent'] == 100]
    require(all(np.array_equal(draws[:,i], draws[:,full[0]], equal_nan=True) for i in full), '100% policies differ')
    return rows, differences, joint


def qini_point(n0, n1, y0, y1):
    if n0+n1 == 0:
        return 0., 'origin'
    if n0 == 0:
        return None, 'no_control_prefix'
    return float(y1-y0*n1/n0), 'point_estimate_only'


def trapezoid_area(c, excess):
    require(len(c) == len(excess) and len(c) >= 2 and all(a <= b for a,b in zip(c,c[1:])), 'invalid grid')
    if any(v is None or not np.isfinite(v) for v in excess):
        return None
    return float(sum((b-a)*(x+y)/2 for a,b,x,y in zip(c,c[1:],excess,excess[1:])))


def qini_curves(ranks, treatment, conversion):
    n = len(conversion)
    validate_ranks(ranks, n)
    require(treatment.shape == conversion.shape and np.isin(treatment,[0,1]).all() and
            np.isin(conversion,[0,1]).all(), 'binary curve fields required')
    n0 = int((treatment == 0).sum()); n1 = n-n0
    y0 = int(conversion[treatment == 0].sum()); y1 = int(conversion[treatment == 1].sum())
    full_q, _ = qini_point(n0,n1,y0,y1)
    rows=[];areas=[]
    for policy, rank in ranks.items():
        order = np.argsort(rank)
        t = treatment[order]; y = conversion[order]
        cumulative = [np.r_[np.int64(0), np.cumsum(v,dtype=np.int64)] for v in
                      ((t==0), (t==1), (t==0)*y, (t==1)*y)]
        curve=[]
        for cap in range(101):
            k=cap*n//100; actual=k/n
            a,b,x,z=[int(v[k]) for v in cumulative]
            q,status=qini_point(a,b,x,z)
            line=actual*full_q if full_q is not None else None
            excess=q-line if q is not None and line is not None else None
            curve.append(dict(policy=policy,nominal_capacity_percent=cap,selected_n=k,c_actual=actual,
                control_n=a,treatment_n=b,conversion_control=x,conversion_treatment=z,Q=q,
                reference_L=line,Q_minus_L=excess,status=status,
                sparse_prefix=bool(k and min(x,a-x,z,b-z)<10)))
        area=trapezoid_area([r['c_actual'] for r in curve],[r['Q_minus_L'] for r in curve])
        areas.append(dict(policy=policy,N_test=n,grid='fixed_1_percent_actual_K_over_N',
                          unnormalized_qini_area_approx=area,
                          status='point_estimate_only' if area is not None else 'unavailable_curve_gap',
                          interval='not_computed',reference='L(c)=c*Q(1); not empirical RANDOM'))
        rows.extend(curve)
    return rows,areas
