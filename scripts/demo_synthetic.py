"""Small synthetic-only denominator and sparse-inference demonstration."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.test_cohort import connection, gates
from scripts.build_cohort import build, summary
from abtest.stats import proportions


def main():
    # Reuse the T5.1 artificial boundary/duplicate example, never local real data.
    events = [
        ('2019-10-01T00:00:00Z','A','view','0'),
        ('2019-10-01T00:00:01Z','A','view','0'),
        ('2019-10-14T23:59:59Z','B','view','0'),
        ('2019-10-02T10:00:00Z','C','purchase','5.00'),
        ('2019-10-15T00:00:00Z','A','purchase','10.00'),
        ('2019-10-15T00:00:00Z','A','purchase','10.00'),
        ('2019-10-28T23:59:59Z','B','view','0'),
        ('2019-10-15T00:00:00Z','D','purchase','999'),
        ('2019-09-30T23:59:59Z','E','view','0'),
        ('2019-10-15T00:00:00Z','E','view','0'),
        ('2019-10-29T00:00:00Z','C','purchase','300'),
        ('2019-10-29T00:00:00Z','F','purchase','400'),
    ]
    c = connection(events)
    try:
        build(c, 'synthetic', gates())
        result = summary(c)
        actual = {k:result[k] for k in ('enrolled_users','returned_users','not_returned_users',
                                       'post_buyers','post_purchase_events','post_only_users')}
        expected = dict(enrolled_users=3,returned_users=2,not_returned_users=1,
                        post_buyers=1,post_purchase_events=2,post_only_users=2)
        if actual != expected:
            raise AssertionError((expected, actual))
        if c.execute('SELECT user_id FROM cohort ORDER BY user_id').fetchall() != [('A',),('B',),('C',)]:
            raise AssertionError('synthetic membership changed')
        from decimal import Decimal
        if result['cohort_buyer_rate'] != Decimal(1)/3 or result['returned_buyer_rate'] != Decimal('0.5'):
            raise AssertionError('denominator mismatch')
        # A separate six-user literal statistics example, not a cohort effect.
        sparse = proportions(3,1,3,2)
        if sparse['status'] != 'sparse_cells' or sparse['p_value'] is not None or sparse['ci_low'] is not None:
            raise AssertionError('sparse inference should be withheld')
        print(json.dumps(dict(kind='synthetic',status='passed',event_rows=len(events),
            expected=expected,actual=actual,cohort_buyer_rate=str(result['cohort_buyer_rate']),
            returned_buyer_rate=str(result['returned_buyer_rate']),
            statistical_boundary=dict(n_A=3,k_A=1,n_B=3,k_B=2,status=sparse['status'],
                                      p_value=sparse['p_value'],ci_low=sparse['ci_low']),
            meaning='artificial_logic_demo_not_real_project_results'),indent=2))
    finally:
        c.close()


if __name__ == '__main__':main()
