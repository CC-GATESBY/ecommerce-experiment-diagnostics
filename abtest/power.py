"""Fixed-Y0 raw power simulation; no real-data loading or legacy API changes."""
from collections import Counter
from fractions import Fraction
import hashlib
import math

import numpy as np
from scipy.optimize import brentq
from scipy.stats import norm

from abtest.assign import prepare_keys
from abtest.inject import binary_array, potential_outcome
from abtest.srm import srm
from abtest.stats import proportions, wilson

VERSION = 'rees46-power-raw-v1'
PREFIX = VERSION.encode('ascii') + b'|'
SEED = 20260923
ROUNDS = 300
GRID_PP = ('0', '0.10', '0.20', '0.30', '0.40', '0.46', '0.50', 'S1_REFERENCE', '0.80')
RUN_FIELDS = (
    'round', 'effect', 'N', 'p0', 'delta', 'delta_fraction', 'delta_pp', 'q', 'q_fraction',
    'n_A', 'n_B', 'K', 'tau', 'flips_B', 'buyers_A', 'buyers_B',
    'mean_A', 'mean_B', 'difference', 'difference_pp', 'difference_per_10000',
    'relative_change', 'se', 'ci_low', 'ci_high', 'p_value', 'df', 'method', 'unit',
    'status', 'reason', 'estimation_error', 'two_sided_rejection', 'positive_rejection',
    'negative_rejection', 'srm_status', 'srm_statistic', 'srm_p', 'srm_flag')


def effect_grid(p0):
    p0 = p0 if isinstance(p0, Fraction) else Fraction(str(p0))
    return tuple((label, p0 / 10 if label == 'S1_REFERENCE' else Fraction(label) / 100)
                 for label in GRID_PP)


def prepare_cohort(keys, y0):
    encoded = prepare_keys(keys)
    y0 = binary_array(y0)
    if len(encoded) != len(y0):
        raise ValueError('key/outcome length mismatch')
    order = sorted(range(len(keys)), key=keys.__getitem__)
    y0 = y0[order]
    y0.flags.writeable = False
    return dict(keys=tuple(encoded[i] for i in order), y0=y0,
                p0=Fraction(int(y0.sum()), len(y0)))


def validate_round(round_index):
    if type(round_index) is not int or not 1 <= round_index <= ROUNDS:
        raise ValueError('round index must be an integer in 1..300')


def round_uniforms(n, round_index):
    validate_round(round_index)
    result = np.random.Generator(np.random.PCG64(
        np.random.SeedSequence([SEED, round_index]))).random(n)
    result.flags.writeable = False
    return result


def assign_power(encoded_keys, round_index):
    """Keys must come from prepare_cohort; only identity and round enter the hash."""
    validate_round(round_index)
    prefix = PREFIX + str(round_index).encode('ascii') + b'|'
    result = np.fromiter((int.from_bytes(hashlib.sha256(prefix + key).digest()[:8], 'big')
                          >= 2**63 for key in encoded_keys), dtype=np.bool_, count=len(encoded_keys))
    result.flags.writeable = False
    return result


def simulate_round(prepared, round_index):
    y0 = prepared['y0']
    n = len(y0)
    grid = effect_grid(prepared['p0'])
    u = round_uniforms(n, round_index)
    # All full potential outcomes exist before the one assignment is computed.
    potentials = tuple(potential_outcome(y0, delta, u) for _, delta in grid)
    mask = assign_power(prepared['keys'], round_index)
    nb = int(mask.sum())
    na = n - nb
    ka = int(y0[~mask].sum())
    qa = srm(na, nb)
    rows = []
    for (label, delta), (y1, q) in zip(grid, potentials):
        flips = y1 - y0
        k = int(flips.sum())
        kb = int(y1[mask].sum())
        row = dict.fromkeys(RUN_FIELDS)
        row.update(round=round_index, effect=label, N=n, p0=float(prepared['p0']),
                   delta=float(delta), delta_fraction=str(delta), delta_pp=float(delta*100),
                   q=float(q), q_fraction=str(q), n_A=na, n_B=nb, K=k, tau=k/n,
                   flips_B=int(flips[mask].sum()), buyers_A=ka, buyers_B=kb, **qa)
        try:
            row.update(proportions(na, ka, nb, kb))
        except (ValueError, ArithmeticError) as exc:
            row.update(status='calculation_failed', reason=type(exc).__name__ + ': ' + str(exc))
        if row['difference'] is not None:
            row['estimation_error'] = float(Fraction(kb, nb)-Fraction(ka, na)-Fraction(k, n))
        if row['status'] == 'ok' and row['p_value'] is not None:
            rejected = row['p_value'] < .05
            row.update(two_sided_rejection=rejected,
                       positive_rejection=rejected and row['difference'] > 0,
                       negative_rejection=rejected and row['difference'] < 0)
        rows.append(row)
    audit = dict(round=round_index, U_sha256=hashlib.sha256(u.tobytes()).hexdigest(),
                 assignment_sha256=hashlib.sha256(mask.tobytes()).hexdigest())
    return rows, audit


def theoretical_power(n, p0, delta):
    p0, delta = float(p0), float(delta)
    if n <= 0 or not all(map(math.isfinite, (p0, delta))) or not 0 <= p0 <= 1 or not 0 <= delta <= 1-p0:
        raise ValueError('invalid theoretical reference parameters')
    p1 = p0 + delta
    variance = (p0*(1-p0) + p1*(1-p1)) / (n/2)
    if variance <= 0:
        return dict(status='zero_variance', se_ref=None, two_sided=None, positive=None)
    se = math.sqrt(variance)
    lam = delta/se
    zcrit = float(norm.ppf(.975))
    return dict(status='ok', se_ref=se,
                two_sided=float(norm.cdf(lam-zcrit) + norm.cdf(-lam-zcrit)),
                positive=float(norm.cdf(lam-zcrit)))


def theoretical_mde(n, p0):
    lo, hi = 0., .008
    if float(p0)+hi > 1:
        return dict(status='invalid_reference_bracket')
    def f(delta):
        result = theoretical_power(n, p0, delta)
        return None if result['two_sided'] is None else result['two_sided']-.8
    a, b = f(lo), f(hi)
    if a is None or b is None or a*b > 0:
        return dict(status='not_bracketed', bracket_pp=[0, .8])
    root = float(brentq(f, lo, hi, xtol=1e-14))
    return dict(status='bracketed', delta=root, delta_pp=root*100,
                relative_to_p0=root/float(p0) if p0 else None,
                theoretical_two_sided=theoretical_power(n, p0, root)['two_sided'])


def empirical_crossings(summary):
    crossings = []
    ordered = sorted(summary, key=lambda r: r['delta'])
    for a, b in zip(ordered, ordered[1:]):
        av, bv = a['two_sided_rate'], b['two_sided_rate']
        if av is None or bv is None:
            continue
        if (av < .8 <= bv) or (av >= .8 > bv):
            crossings.append(dict(direction='up' if bv > av else 'down',
                                  lower_effect=a['effect'], upper_effect=b['effect'],
                                  lower_pp=a['delta_pp'], upper_pp=b['delta_pp'],
                                  lower_rate=av, upper_rate=bv,
                                  lower_wilson=[a['two_sided_ci_low'], a['two_sided_ci_high']],
                                  upper_wilson=[b['two_sided_ci_low'], b['two_sided_ci_high']]))
    return crossings


def summarize(rows, n, p0, planned=ROUNDS):
    result = []
    for label, delta in effect_grid(p0):
        subset = [r for r in rows if r['effect'] == label]
        rounds = [r['round'] for r in subset]
        if len(rounds) != len(set(rounds)) or len(rounds) > planned:
            raise ValueError('duplicate or excess rounds')
        valid = [r for r in subset if r['status'] == 'ok' and r['p_value'] is not None]
        failures = Counter(r['status'] + ':' + r['reason'] for r in subset
                           if r['status'] != 'ok' or r['p_value'] is None)
        q = delta/(1-p0) if delta else Fraction(0)
        n0 = n-int(p0*n)
        variance_k = float(n0*q*(1-q))
        expected_k = float(n0*q)
        mcse_tau = math.sqrt(variance_k)/(n*math.sqrt(len(subset))) if subset else None
        mean_tau = float(np.mean([r['tau'] for r in subset])) if subset else None
        mc_z = ((mean_tau-float(delta))/mcse_tau if mcse_tau else None)
        mechanism_ok = (all(r['K'] == 0 for r in subset) if not delta else
                        mc_z is not None and abs(mc_z) <= 6)
        ref = theoretical_power(n, p0, delta)
        row = dict(effect=label, delta=float(delta), delta_fraction=str(delta), delta_pp=float(delta*100),
                   N=n, p0=float(p0), q=float(q), planned=planned, completed=len(subset), valid=len(valid),
                   failed=len(subset)-len(valid), not_completed=planned-len(subset),
                   failure_reasons=';'.join(f'{k}={v}' for k, v in sorted(failures.items())),
                   denominator='all_computable_including_SRM',
                   srm_flagged=sum(r['srm_flag'] is True for r in subset),
                   srm_flagged_valid=sum(r['srm_flag'] is True for r in valid))
        for name in ('two_sided', 'positive', 'negative'):
            count = sum(r[name+'_rejection'] is True for r in valid)
            rate = count/len(valid) if valid else None
            row.update({name+'_count':count, name+'_rate':rate})
            if name != 'negative':
                low, high = wilson(count, len(valid))
                row.update({name+'_ci_low':low, name+'_ci_high':high,
                            name+'_mcse':math.sqrt(rate*(1-rate)/len(valid)) if valid else None})
        errors = [r['estimation_error'] for r in valid]
        row.update(mean_tau=mean_tau, mean_K=float(np.mean([r['K'] for r in subset])) if subset else None,
                   expected_K=expected_k, variance_K=variance_k, mean_tau_mcse=mcse_tau,
                   mechanism_mc_z=mc_z, mechanism_status='passed' if mechanism_ok and subset else 'needs_review',
                   mean_estimate=float(np.mean([r['difference'] for r in valid])) if valid else None,
                   mean_estimation_error=float(np.mean(errors)) if errors else None,
                   error_p025=float(np.quantile(errors,.025,method='linear')) if errors else None,
                   error_p975=float(np.quantile(errors,.975,method='linear')) if errors else None,
                   theory_status=ref['status'], theory_se_ref=ref['se_ref'],
                   theory_two_sided=ref['two_sided'], theory_positive=ref['positive'])
        result.append(row)
    return result
