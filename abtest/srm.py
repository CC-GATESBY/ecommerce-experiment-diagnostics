"""SRM checks assigned users, never buyers."""
from scipy.stats import chi2


def srm(n_a,n_b):
    if any(type(n) is not int or n<0 for n in (n_a,n_b)):raise ValueError('invalid assigned counts')
    n=n_a+n_b
    if not n:return dict(srm_status='empty_assignment',srm_p=None,srm_flag=None,srm_statistic=None)
    statistic=(n_a-n_b)**2/n
    p=float(chi2.sf(statistic,1))
    return dict(srm_status='ok',srm_statistic=statistic,srm_p=p,srm_flag=p<0.001)
