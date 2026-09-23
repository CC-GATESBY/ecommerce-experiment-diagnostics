"""Bounded synthetic cases; no real cohort or historical simulation is loaded."""
from fractions import Fraction
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
from abtest import power
from abtest.assign import assign, prepare_keys
from abtest.inject import potential_outcome, assign_injected
from scripts.run_power_raw import create_run, expected_config


def keys(n=80):
    return [hashlib.sha256(f'synthetic-power-{i}'.encode()).hexdigest() for i in range(n)]


class PowerTests(unittest.TestCase):
    def test_units_exact_reference_and_domains(self):
        grid = dict(power.effect_grid(Fraction(1,20)))
        self.assertEqual(grid['0.46'], Fraction(23,5000))
        self.assertEqual(grid['0.10'], Fraction(1,1000))
        self.assertEqual(grid['S1_REFERENCE'], Fraction(1,200))
        for delta in (-.001, .7501, float('inf')):
            with self.assertRaises(ValueError):potential_outcome([0,0,0,1], delta, [.1]*4)
        with self.assertRaises(ValueError):potential_outcome([1,1], .001, [.1,.2])
        self.assertEqual(potential_outcome([1,1], 0, [.1,.2])[0].tolist(), [1,1])
        for r in (0, 301, 1.0, True):
            with self.assertRaises(ValueError):power.round_uniforms(10,r)

    def test_fixed_U_literal_and_one_never_reverts(self):
        y0 = np.array([0,1,0,0], dtype=np.int8)
        y0.flags.writeable = False
        unchanged, q0 = potential_outcome(y0, 0, [.1,.9,.25,.2])
        y1, q = potential_outcome(y0, Fraction(3,16), [.1,.9,.25,.2])
        self.assertEqual(q0, 0)
        self.assertEqual(unchanged.tolist(), [0,1,0,0])
        self.assertEqual(q, Fraction(1,4))
        self.assertEqual(y1.tolist(), [1,1,0,1])
        self.assertEqual(y0.tolist(), [0,1,0,0])

    def test_potentials_precede_assignment_and_share_U(self):
        p = power.prepare_cohort(keys(), [i%2 for i in range(80)])
        calls, uniforms = [], []
        real_p, real_a = power.potential_outcome, power.assign_power
        def potential(y0, delta, u):
            calls.append('potential'); uniforms.append(u)
            return real_p(y0, delta, u)
        def assignment(*args):
            calls.append('assignment')
            return real_a(*args)
        with patch.object(power,'potential_outcome',side_effect=potential), patch.object(power,'assign_power',side_effect=assignment):
            rows, _ = power.simulate_round(p,1)
        self.assertEqual(calls, ['potential']*9+['assignment'])
        self.assertTrue(all(u is uniforms[0] for u in uniforms))
        self.assertEqual(len({(r['n_A'],r['n_B'],r['buyers_A']) for r in rows}),1)
        self.assertEqual(rows[0]['K'],0)
        for r in rows:
            self.assertEqual(r['buyers_B']-rows[0]['buyers_B'],r['flips_B'])

    def test_key_order_and_fresh_round_rng_reproducible(self):
        k = keys(); y = [i%2 for i in range(80)]
        p = power.prepare_cohort(k,y)
        a = power.simulate_round(p,1)
        b = power.simulate_round(power.prepare_cohort(k[::-1],y[::-1]),1)
        self.assertEqual(a,b)
        independent_u = np.random.Generator(np.random.PCG64(np.random.SeedSequence([20260923,1]))).random(80)
        np.testing.assert_array_equal(power.round_uniforms(80,1), independent_u)
        self.assertFalse(np.array_equal(power.round_uniforms(80,1),power.round_uniforms(80,2)))
        power.round_uniforms(80,2)
        np.testing.assert_array_equal(power.round_uniforms(80,1), independent_u)
        c = power.simulate_round(p,2)
        self.assertNotEqual(a[1]['assignment_sha256'],c[1]['assignment_sha256'])
        code = ('import json; from abtest.power import prepare_cohort,simulate_round; '
                'k,y=json.loads(input()); print(json.dumps(simulate_round(prepare_cohort(k,y),1)[1],sort_keys=True))')
        actual = subprocess.check_output([sys.executable,'-c',code], input=json.dumps([k,y]).encode())
        self.assertEqual(json.loads(actual),a[1])

    def test_assignment_payload_and_legacy_limits(self):
        p = power.prepare_cohort(keys(), [i%2 for i in range(80)])
        expected = [hashlib.sha256(b'rees46-power-raw-v1|1|'+k).hexdigest()[0] in '89abcdef'
                    for k in p['keys']]
        self.assertEqual(power.assign_power(p['keys'],1).tolist(),expected)
        altered = power.prepare_cohort(keys(), [0]*80)
        np.testing.assert_array_equal(power.assign_power(p['keys'],1),power.assign_power(altered['keys'],1))
        with self.assertRaises(ValueError):assign(prepare_keys(keys()),'rees46-power-raw-v1-0001')
        with self.assertRaises(ValueError):assign_injected(keys(),'rees46-power-raw-v1-0001')

    def test_theory_both_tails_and_mde_bracket(self):
        r = power.theoretical_power(80,.5,0)
        self.assertAlmostEqual(r['two_sided'], .05, places=14)
        self.assertAlmostEqual(r['positive'], .025, places=14)
        self.assertEqual(power.theoretical_mde(80,.5)['status'],'not_bracketed')
        self.assertEqual(power.theoretical_power(80,1,0)['status'],'zero_variance')
        with self.assertRaises(ValueError):power.theoretical_power(80,1,.001)
        mde = power.theoretical_mde(100000,.05)
        self.assertEqual(mde['status'],'bracketed')
        self.assertAlmostEqual(mde['theoretical_two_sided'], .8, places=10)

    def test_denominator_failure_SRM_and_extreme_wilson(self):
        p = power.prepare_cohort(keys(), [i%2 for i in range(80)])
        base = power.simulate_round(p,1)[0][0]
        rows = []
        # Three computable rounds, including a flagged SRM; one failed round.
        for i,(diff,pvalue,srm_flag,status) in enumerate(((.1,.01,True,'ok'),(-.1,.01,False,'ok'),
                                                        (.01,.9,False,'ok'),(None,None,False,'sparse_cells')),1):
            row = dict(base, round=i, difference=diff, p_value=pvalue, status=status, reason='',
                       srm_flag=srm_flag, estimation_error=diff,
                       two_sided_rejection=pvalue<.05 if pvalue is not None else None,
                       positive_rejection=pvalue<.05 and diff>0 if pvalue is not None else None,
                       negative_rejection=pvalue<.05 and diff<0 if pvalue is not None else None)
            rows.append(row)
        s = power.summarize(rows,80,Fraction(1,2),planned=4)[0]
        self.assertEqual((s['completed'],s['valid'],s['failed'],s['srm_flagged_valid']),(4,3,1,1))
        self.assertEqual((s['two_sided_rate'],s['positive_rate'],s['negative_rate']),(2/3,1/3,1/3))
        self.assertIn('sparse_cells',s['failure_reasons'])
        for r in rows[:3]:r.update(two_sided_rejection=False,positive_rejection=False)
        s = power.summarize(rows,80,Fraction(1,2),planned=4)[0]
        self.assertEqual(s['two_sided_mcse'],0)
        self.assertGreater(s['two_sided_ci_high'],0)
        for r in rows[:3]:r.update(two_sided_rejection=True,positive_rejection=True)
        s = power.summarize(rows,80,Fraction(1,2),planned=4)[0]
        self.assertEqual(s['two_sided_mcse'],0)
        self.assertLess(s['two_sided_ci_low'],1)
        with self.assertRaises(ValueError):power.summarize(rows+[rows[0]],80,Fraction(1,2),planned=5)

    def test_empty_arm_retained_and_no_false_nondetection(self):
        p = power.prepare_cohort(keys(), [i%2 for i in range(80)])
        with patch.object(power,'assign_power',return_value=np.zeros(80,dtype=bool)):
            rows,_ = power.simulate_round(p,1)
        self.assertTrue(all(r['status']=='empty_group' and r['two_sided_rejection'] is None for r in rows))
        self.assertTrue(all(r['srm_flag'] for r in rows))

    def test_crossings_do_not_force_monotonicity(self):
        sample = [dict(effect=str(i),delta=i/1000,delta_pp=i/10,two_sided_rate=v,
                       two_sided_ci_low=max(0,v-.1),two_sided_ci_high=min(1,v+.1))
                  for i,v in enumerate([.7,.9,.75,.85])]
        self.assertEqual([x['direction'] for x in power.empirical_crossings(sample)],['up','down','up'])

    def test_frozen_config_and_no_run_overwrite(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(json.loads((root/'config/power_raw.json').read_text()),expected_config())
        with tempfile.TemporaryDirectory() as temp:
            run = create_run(Path(temp),'power-raw-oct-01')
            (run/'keep').write_text('synthetic previous output')
            with self.assertRaises(FileExistsError):create_run(Path(temp),'power-raw-oct-01')
            self.assertEqual((run/'keep').read_text(),'synthetic previous output')
            with self.assertRaises(ValueError):create_run(Path(temp),'another-unapproved-run')


if __name__ == '__main__':unittest.main()
