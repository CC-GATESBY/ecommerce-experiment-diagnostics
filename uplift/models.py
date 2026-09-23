"""Four fixed classifiers, label-blind selection, and five-policy joint evaluation."""
import hashlib
import inspect
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss

from uplift.targeting import require, resample_joint, interval, sha

FEATURES = [f'f{i}' for i in range(12)]
ROLES = ['RESPONSE_MODEL', 'S_LEARNER', 'T_CONTROL', 'T_TREATMENT']
POLICIES = ['RANDOM', 'FROZEN_SIMPLE', 'RESPONSE_MODEL', 'S_LEARNER', 'T_LEARNER']
PARAMETERS = dict(loss='log_loss', learning_rate=.05, max_iter=150, max_leaf_nodes=15,
                  max_bins=63, min_samples_leaf=200, l2_regularization=1.,
                  early_stopping=True, scoring='loss', n_iter_no_change=10, tol=1e-7,
                  categorical_features=None, class_weight=None, random_state=20260923)
EARLY_PREFIX = 'e1-early-stop-v1|20260923|'
PILOT_PREFIX = 'e1-resource-pilot-v1|20260923|'


def hash64(prefix, row_id):
    return int.from_bytes(hashlib.sha256((prefix+row_id).encode('ascii')).digest()[:8], 'big')


def early_member(row_id, original_split):
    require(original_split == 'train', 'early-stop membership can only be formed within original train')
    return hash64(EARLY_PREFIX, row_id) < 2**64//10


def check_features(names):
    require(names == FEATURES, 'only ordered f0..f11 features are accepted')


def training_indices(early_flags, treatment, part, role):
    require(role in ROLES and part in ('fit','early_stop'), 'invalid training role/part')
    mask = early_flags == (part == 'early_stop')
    if role.startswith('T_'):
        mask = mask & (treatment == (role == 'T_TREATMENT'))
    return np.flatnonzero(mask)


def fit_classifier(role, xfit, yfit, xearly, yearly, *, pilot=False):
    require(role in ROLES, 'unknown classifier')
    width = 13 if role == 'S_LEARNER' else 12
    require(xfit.ndim == xearly.ndim == 2 and xfit.shape[1] == xearly.shape[1] == width,
            'training feature width mismatch')
    require(xfit.dtype == xearly.dtype == np.float64, 'DOUBLE features required')
    require(len(xfit) == len(yfit) and len(xearly) == len(yearly) and
            set(np.unique(yfit)) == set(np.unique(yearly)) == {0,1}, 'training label support missing')
    require({'X_val','y_val'} <= set(inspect.signature(HistGradientBoostingClassifier.fit).parameters),
            'explicit early-stop interface unavailable')
    parameters = dict(PARAMETERS)
    if pilot:
        parameters['max_iter'] = 10
    estimator = HistGradientBoostingClassifier(**parameters)
    estimator.fit(xfit, yfit, X_val=xearly, y_val=yearly)
    require(estimator.do_early_stopping_ and len(estimator.validation_score_) == estimator.n_iter_+1,
            'explicit validation loss history missing')
    return estimator


def predict_conditions(estimator, role, x):
    """No observed treatment or outcome is accepted for selecting valid records."""
    require(role in ROLES and x.ndim == 2 and x.shape[1] == 12 and x.dtype == np.float64,
            'prediction requires the twelve DOUBLE features')
    if role == 'S_LEARNER':
        design = np.empty((len(x),13), dtype=np.float64)
        design[:,:12] = x
        design[:,12] = 0
        p0 = estimator.predict_proba(design)[:,1]
        design[:,12] = 1
        p1 = estimator.predict_proba(design)[:,1]
        probabilities = np.column_stack((p0,p1))
    else:
        probabilities = estimator.predict_proba(x)[:,1,None]
    require(np.isfinite(probabilities).all() and ((probabilities>=0)&(probabilities<=1)).all(),
            'invalid predicted probabilities')
    return probabilities


def load_own_model(path, expected_sha, allowed_directory):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and path.resolve().parent == Path(allowed_directory).resolve(),
            'only this run local models may be loaded')
    require(sha(path) == expected_sha, 'model fingerprint mismatch')
    return joblib.load(path)


def simple_scores(x, frozen):
    # Right-closed bins match the frozen DuckDB CASE expressions, without rounding.
    b0 = np.searchsorted(frozen['boundaries']['f0'],x[:,0],side='left')
    b1 = np.searchsorted(frozen['boundaries']['f1'],x[:,1],side='left')
    group = b0*(len(frozen['boundaries']['f1'])+1)+b1
    ranks = {g['group_id']:g['response_rank'] for g in frozen['groups']}
    require(all(g['response_rank']==g['incremental_rank'] for g in frozen['groups']), 'simple ranks changed')
    lookup=np.array([ranks[i] for i in range(max(ranks)+1)],dtype=np.float64)
    return -lookup[group]


def select_by_score(score, row_ids, tie_hashes, k):
    require(score.ndim==1 and len(score)==len(row_ids)==len(tie_hashes) and np.isfinite(score).all(),
            'finite one-score-per-record required')
    require(0<=k<=len(score), 'invalid capacity')
    order = np.lexsort((row_ids, tie_hashes, -score))
    selected = np.zeros(len(score), dtype=bool)
    selected[order[:k]] = True
    return selected


def factual_metrics(y, treatment, probabilities, fit_rates):
    output=[]
    for name, p in probabilities.items():
        factual = p[:,0] if name=='RESPONSE_MODEL' else np.where(treatment==1,p[:,1],p[:,0])
        constant_global = np.full(len(y),fit_rates['all'],dtype=np.float64)
        constant_arm = np.where(treatment==1,fit_rates['1'],fit_rates['0'])
        for group in ('all','0','1'):
            ix = np.ones(len(y),dtype=bool) if group=='all' else treatment==int(group)
            n=int(ix.sum()); positives=int(y[ix].sum())
            row=dict(model=name,valid_arm=group,n=n,conversion=positives,
                     corresponding_constant='fit_global' if name=='RESPONSE_MODEL' else 'fit_arm',
                     status='ok' if n else 'empty_arm')
            for key, pred in [('factual_logloss',factual),('fit_global_constant_logloss',constant_global),
                              ('fit_arm_constant_logloss',constant_arm)]:
                row[key]=float(log_loss(y[ix],pred[ix],labels=[0,1])) if n else None
            row['improvement_vs_corresponding_constant'] = (
                row['fit_global_constant_logloss' if name=='RESPONSE_MODEL' else 'fit_arm_constant_logloss']
                -row['factual_logloss']) if n else None
            output.append(row)
    return output


def policy_evaluation(selected, treatment, y, cfg):
    """Retain all records in joint types, including records selected by no policy."""
    require(list(selected)==POLICIES, 'frozen policy order required')
    n=len(y);k=cfg['capacity_percent']*n//100
    require(n==len(treatment) and all(len(v)==n and int(v.sum())==k for v in selected.values()),
            'same-capacity selection required')
    require(np.isin(treatment,[0,1]).all() and np.isin(y,[0,1]).all(), 'binary evaluation fields required')
    mask=np.zeros(n,dtype=np.int64)
    for j,values in enumerate(selected.values()): mask += values.astype(np.int64)*(1<<j)
    encoded=treatment.astype(np.int64)*64+y.astype(np.int64)*32+mask
    counts=np.bincount(encoded,minlength=128)
    joint=[dict(treatment=i//64,conversion=(i%64)//32,mask=i%32,n=int(count))
           for i,count in enumerate(counts) if count]
    specs=[dict(rule=name,capacity_percent=30,selected_n=k,c_actual=k/n,bit=j)
           for j,name in enumerate(selected)]
    (ns,events,rates,deltas,gs),draws,_=resample_joint(joint,specs,cfg)
    rows=[]
    for j,spec in enumerate(specs):
        finite=bool(np.isfinite(gs[j]))
        sparse=min(events[0,j],ns[0,j]-events[0,j],events[1,j],ns[1,j]-events[1,j]) < 10
        row=dict(policy=spec['rule'],split='valid',capacity_percent=30,N_valid=n,selected_n=k,c_actual=k/n,
                 control_n=int(ns[0,j]),treatment_n=int(ns[1,j]),conversion_control=int(events[0,j]),
                 conversion_treatment=int(events[1,j]),
                 p0_S=float(rates[0,j]) if ns[0,j] else None,p1_S=float(rates[1,j]) if ns[1,j] else None,
                 delta_S=float(deltas[j]) if finite else None,G=float(gs[j]) if finite else None,
                 status='zero_denominator' if not finite else ('sparse_not_for_strong_inference' if sparse else 'development_marginal_paired_bootstrap'),
                 **interval(draws[:,j]))
        for ref,index in [('FROZEN_SIMPLE',1),('RANDOM',0)]:
            ci=interval(draws[:,j]-draws[:,index])
            row['G_minus_'+ref]=float(gs[j]-gs[index]) if np.isfinite(gs[j]-gs[index]) else None
            ref_sparse=min(events[0,index],ns[0,index]-events[0,index],events[1,index],ns[1,index]-events[1,index])<10
            row['status_minus_'+ref]=('zero_denominator' if not np.isfinite(gs[j]-gs[index]) else
                                    ('sparse_not_for_strong_inference' if sparse or ref_sparse else 'development_marginal_paired_bootstrap'))
            for key,value in ci.items():row[key+'_minus_'+ref]=value
        rows.append(row)
    overlaps=[]
    for i,a in enumerate(POLICIES):
        for b in POLICIES[i+1:]:
            intersection=int(np.count_nonzero(selected[a]&selected[b]))
            overlaps.append(dict(policy_a=a,policy_b=b,selected_n=k,intersection_n=intersection,
                                 overlap_rate=intersection/k if k else None,
                                 identical=bool(np.array_equal(selected[a],selected[b]))))
    return rows, overlaps, joint, draws
