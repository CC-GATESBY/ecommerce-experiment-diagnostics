"""Equal-allocation normal-approximation planning and coupon cost conditions."""
from decimal import Decimal, localcontext
import math
from statistics import NormalDist


def two_proportions(p0, relative_mde, alpha=0.05, power=0.80):
    p0, relative_mde = float(p0), float(relative_mde)
    p1 = p0*(1+relative_mde)
    result = dict(p0=p0, p1=p1, relative_mde=relative_mde,
                  absolute_difference_pp=(p1-p0)*100, alpha=alpha, power=power,
                  n_per_arm=None, n_total=None)
    if not all(math.isfinite(x) for x in (p0, p1, relative_mde, alpha, power)):
        return {**result, 'status': 'invalid_nonfinite'}
    if not (0 < p0 < 1 and 0 < p1 < 1):
        return {**result, 'status': 'invalid_probability'}
    if relative_mde <= 0 or not (0 < alpha < 1 and 0.5 < power < 1):
        return {**result, 'status': 'invalid_design'}
    pooled = (p0+p1)/2
    z_alpha = NormalDist().inv_cdf(1-alpha/2)
    z_power = NormalDist().inv_cdf(power)
    raw = ((z_alpha*math.sqrt(2*pooled*(1-pooled)) +
            z_power*math.sqrt(p0*(1-p0)+p1*(1-p1)))/(p1-p0))**2
    n = math.ceil(raw)
    return {**result, 'n_per_arm': n, 'n_total': 2*n, 'status': 'planning_approximation'}


def independent_n(p0, relative_mde):
    """Separate Decimal arithmetic and fixed quantiles for the frozen 0.05/0.8 design."""
    with localcontext() as context:
        context.prec = 45
        a, lift = Decimal(str(p0)), Decimal(str(relative_mde))
        b = a*(1+lift)
        if not (0 < a < 1 and 0 < b < 1 and lift > 0):
            return None
        mean = (a+b)/2
        # Standard-normal quantiles, not derived from the production calculation.
        x = Decimal('1.95996398454005423552')*(2*mean*(1-mean)).sqrt()
        y = Decimal('0.84162123357291420518')*(a*(1-a)+b*(1-b)).sqrt()
        return int(((x+y)**2/(b-a)**2).to_integral_value(rounding='ROUND_CEILING'))


def break_even(k):
    k = Decimal(str(k))
    if not k.is_finite() or not 0 <= k < 1:
        raise ValueError('expected coupon burden must satisfy 0 <= k < 1')
    return k/(1-k)


def incremental_contribution(p0, p1, v, q, d, c=0):
    p0, p1, v, q, d, c = (Decimal(str(x)) for x in (p0, p1, v, q, d, c))
    if (not all(x.is_finite() for x in (p0,p1,v,q,d,c)) or not
            (0 <= p0 <= 1 and 0 <= p1 <= 1 and v > 0 and 0 <= q <= 1 and d >= 0)):
        raise ValueError('invalid economics parameters')
    return (p1-p0)*v-p1*q*d-c


def planning_tables(p_hist, historical_n):
    if type(historical_n) is not int or historical_n <= 0:
        raise ValueError('positive measured historical cohort required')
    p = Decimal(str(p_hist)); sizes = []; economics = []
    for multiplier in ('0.5', '1', '1.5'):
        for mde in ('0.05', '0.10', '0.20'):
            p0 = p*Decimal(multiplier)
            row = two_proportions(p0, mde)
            if row['status'] == 'planning_approximation':
                if row['n_per_arm'] != independent_n(p0, mde):
                    raise ValueError('independent sample-size formula mismatch')
            sizes.append(dict(baseline_multiplier=multiplier, p_hist=str(p), historical_eligible_users=historical_n,
                              **row, within_historical_count=(row['n_total'] <= historical_n if row['n_total'] else None),
                              interpretation='planning_assumption_not_future_reachable_traffic'))
    for k in ('0.05', '0.10', '0.20'):
        for lift in ('0.05', '0.10', '0.20'):
            r, burden = Decimal(lift), Decimal(k)
            p1 = p*(1+r)
            valid = 0 < p < 1 and 0 < p1 < 1
            value = p*(r-(1+r)*burden) if valid else None
            economics.append(dict(p0=str(p), p1=str(p1), relative_lift=lift, k=k, normalized_v='1', c='0',
                                  break_even_relative_lift=str(break_even(k)),
                                  normalized_increment_per_enrolled=str(value) if value is not None else None,
                                  status=('positive' if value > 0 else 'break_even' if value == 0 else 'negative') if valid else 'invalid_probability',
                                  interpretation='conditional_model_not_measured_profit'))
    return sizes, economics
