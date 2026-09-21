"""Monotone binary potential outcomes, built before one independent allocation."""
from fractions import Fraction
import hashlib
import math

import numpy as np
from abtest.assign import prepare_keys
from abtest.srm import srm
from abtest.stats import proportions

EXPERIMENT_ID = 'rees46-injected-v1-0001'
PREFIX = b'rees46-injected-assignment-v1|'
SEED = 20260921


def binary_array(values):
    values = np.asarray(values)
    if values.ndim != 1 or not len(values) or not np.isin(values, [0, 1]).all():
        raise ValueError('nonempty binary outcome vector required')
    result = values.astype(np.int8, copy=True)
    result.flags.writeable = False
    return result


def potential_outcome(y0, delta, u):
    """Never modify outcomes or clip invalid probabilities."""
    y0 = binary_array(y0)
    if not math.isfinite(float(delta)):
        raise ValueError('finite delta required')
    delta = delta if isinstance(delta, Fraction) else Fraction(str(delta))
    p0 = Fraction(int(y0.sum()), len(y0))
    if delta < 0 or delta > 1 - p0:
        raise ValueError('delta outside [0, 1-p0]; positive injection at p0=1 forbidden')
    u = np.asarray(u, dtype=np.float64)
    if u.shape != y0.shape or not np.isfinite(u).all() or ((u < 0) | (u >= 1)).any():
        raise ValueError('one finite U in [0,1) per user required')
    q = delta / (1 - p0) if delta else Fraction(0)
    y1 = y0.copy()
    if delta:
        y1[(y0 == 0) & (u < float(q))] = 1
    y1.flags.writeable = False
    return y1, q


def build_potentials(keys, y0):
    """No assignment information is available while constructing Y1."""
    encoded = prepare_keys(keys)
    y0 = binary_array(y0)
    if len(encoded) != len(y0):
        raise ValueError('key/outcome length mismatch')
    order = sorted(range(len(keys)), key=keys.__getitem__)
    keys = tuple(keys[i] for i in order)
    y0 = y0[order]
    y0.flags.writeable = False
    u = np.random.Generator(np.random.PCG64(SEED)).random(len(y0))
    u.flags.writeable = False
    p0 = Fraction(int(y0.sum()), len(y0))
    deltas = (Fraction(0), p0 / 10)
    outcomes = tuple(potential_outcome(y0, d, u) for d in deltas)
    return dict(keys=keys, y0=y0, u=u, p0=p0, deltas=deltas, outcomes=outcomes)


def assign_injected(keys, experiment_id=EXPERIMENT_ID):
    if experiment_id != EXPERIMENT_ID:
        raise ValueError('only the frozen simulation ID is allowed')
    encoded = prepare_keys(keys)
    prefix = PREFIX + experiment_id.encode('ascii') + b'|'
    result = np.fromiter((int.from_bytes(hashlib.sha256(prefix + k).digest()[:8], 'big') >= 2**63
                          for k in encoded), dtype=np.bool_, count=len(encoded))
    result.flags.writeable = False
    return result


def evaluate(potentials):
    y0 = potentials['y0']
    mask = assign_injected(potentials['keys'])
    n = len(y0); nb = int(mask.sum()); na = n - nb
    qa = srm(na, nb)
    rows = []; exact_estimates = []
    for index, (y1, q) in enumerate(potentials['outcomes']):
        delta = potentials['deltas'][index]
        flips = y1 - y0
        k = int(flips.sum()); kb_flip = int(flips[mask].sum())
        tau = Fraction(k, n)
        ka = int(y0[~mask].sum()); kb = int(y1[mask].sum())
        result = proportions(na, ka, nb, kb)
        exact = Fraction(kb, nb) - Fraction(ka, na) if na and nb else None
        exact_estimates.append(exact)
        ci_ok = result['ci_low'] is not None and result['ci_high'] is not None
        difference = result['difference']
        rows.append(dict(scenario=f'S{index}', experiment_id=EXPERIMENT_ID, N=n,
            p0=float(potentials['p0']), target_relative_lift=0 if index == 0 else .1,
            target_delta=float(delta), target_delta_fraction=str(delta), q=float(q),
            K=k, flips_B=kb_flip, tau=float(tau), tau_fraction=str(tau),
            buyers_A=ka, buyers_B=kb, **result, **qa,
            estimation_error=float(exact-tau) if exact is not None else None,
            ci_contains_tau=bool(result['ci_low'] <= float(tau) <= result['ci_high']) if ci_ok else None,
            significant=result['p_value'] < .05 if result['p_value'] is not None else None,
            target_delta_pp=float(delta*100), target_delta_per_10000=float(delta*10000),
            tau_pp=float(tau*100), tau_per_10000=float(tau*10000),
            estimation_error_pp=float((exact-tau)*100) if exact is not None else None,
            ci_low_pp=result['ci_low']*100 if ci_ok else None,
            ci_high_pp=result['ci_high']*100 if ci_ok else None,
            ci_low_per_10000=result['ci_low']*10000 if ci_ok else None,
            ci_high_per_10000=result['ci_high']*10000 if ci_ok else None,
            decision_status='not_decision_usable_srm' if qa['srm_flag'] else
                ('not_estimable' if difference is None else 'simulation_only_not_real_strategy_evidence')))
    if na and nb:
        increment = exact_estimates[1] - exact_estimates[0]
        expected = Fraction(rows[1]['flips_B'], nb)
        identity = dict(status='passed' if increment == expected else 'failed',
                        estimated_increment_exact=str(increment), expected_exact=str(expected),
                        increment_pp=float(increment*100))
    else:
        identity = dict(status='not_estimable_empty_group')
    return rows, mask, identity


def simulate(keys, y0):
    potentials = build_potentials(keys, y0)
    rows, mask, identity = evaluate(potentials)
    return potentials, rows, mask, identity


def synthetic_mc():
    """Small mechanism check; no hypothesis tests or power estimation."""
    rng = np.random.Generator(np.random.PCG64(20260922))
    y0 = np.array([1]*20 + [0]*80, dtype=np.int8)
    flips = [int((potential_outcome(y0, Fraction(2,25), rng.random(100))[0]-y0).sum())
             for _ in range(500)]
    mean = float(np.mean(flips)); mc_se = math.sqrt(7.2/500)
    z = (mean-8)/mc_se
    return dict(kind='synthetic_mechanism_only', users=100, repeats=500, seed=20260922,
                expected_mean_K=8, actual_mean_K=mean, expected_variance_K=7.2,
                mc_se_mean_K=mc_se, z=z, max_abs_z=6, passed=abs(z) <= 6,
                actual_mean_delta=mean/100, expected_delta=.08)
