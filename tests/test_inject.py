"""Small synthetic tests with literal outcomes, counts and exact identities."""
from fractions import Fraction
import hashlib
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

import numpy as np
from abtest.assign import assign, prepare_keys
from abtest import inject


def keys(n):
    return [hashlib.sha256(f'synthetic-injection-{i}'.encode()).hexdigest() for i in range(n)]


class InjectionTests(unittest.TestCase):
    def test_fixed_uniform_literal_and_no_mutation(self):
        y0 = np.array([0, 1, 0, 0], dtype=np.int8)
        y0.flags.writeable = False
        u = [.1, .9, .25, .2]
        unchanged, q0 = inject.potential_outcome(y0, 0, u)
        self.assertEqual(unchanged.tolist(), [0, 1, 0, 0])
        self.assertEqual(q0, 0)
        y1, q = inject.potential_outcome(y0, Fraction(3,16), u)
        self.assertEqual(q, Fraction(1,4))
        self.assertEqual(y1.tolist(), [1, 1, 0, 1])
        self.assertEqual(int((y1-y0).sum()), 2)
        self.assertEqual(y0.tolist(), [0, 1, 0, 0])
        self.assertFalse(np.shares_memory(y0, y1))
        self.assertFalse(y1.flags.writeable)
        self.assertEqual(inject.potential_outcome(y0, Fraction(3,4), u)[0].tolist(), [1,1,1,1])

    def test_invalid_domain_not_clipped(self):
        for delta in [-.01, .75001, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):inject.potential_outcome([0,1,0,0], delta, [.1]*4)
        with self.assertRaises(ValueError):inject.potential_outcome([1,1], .01, [.1,.2])
        self.assertEqual(inject.potential_outcome([1,1], 0, [.1,.2])[0].tolist(), [1,1])
        for y0 in ([], [0,2], [0,float('nan')], [[0,1]]):
            with self.assertRaises(ValueError):inject.potential_outcome(y0, 0, [.1,.2])
        for u in ([1,.1], [-.1,.1], [float('nan'),.1], [.1]):
            with self.assertRaises(ValueError):inject.potential_outcome([0,1], 0, u)
        with self.assertRaises(ValueError):inject.build_potentials(keys(2), [0])
        with self.assertRaises(ValueError):inject.build_potentials(keys(1)*2, [0,1])

    def test_reproducible_key_order_and_cross_process(self):
        k = keys(80); y = np.array([i%4 == 0 for i in range(80)], dtype=np.int8)
        first = inject.simulate(k, y)
        second = inject.simulate(k[::-1], y[::-1])
        self.assertEqual(first[0]['keys'], second[0]['keys'])
        for name in ('y0','u'):
            np.testing.assert_array_equal(first[0][name], second[0][name])
        for index in range(2):
            np.testing.assert_array_equal(first[0]['outcomes'][index][0], second[0]['outcomes'][index][0])
        np.testing.assert_array_equal(first[2], second[2])
        self.assertEqual(first[1], second[1])
        code = ('import json,hashlib; from abtest.inject import simulate; '
                'k,y=json.loads(input()); p,r,m,i=simulate(k,y); '
                'print(hashlib.sha256(p["y0"].tobytes()+p["u"].tobytes()+p["outcomes"][1][0].tobytes()+m.tobytes()).hexdigest())')
        other = subprocess.check_output([sys.executable,'-c',code], input=json.dumps([k,y.tolist()]).encode())
        p,_,m,_ = first
        self.assertEqual(other.decode().strip(), hashlib.sha256(p['y0'].tobytes()+p['u'].tobytes()+p['outcomes'][1][0].tobytes()+m.tobytes()).hexdigest())

    def test_builds_both_potentials_before_single_allocation(self):
        calls = []; real_p = inject.potential_outcome; real_a = inject.assign_injected
        def potential(*a):
            calls.append('potential');return real_p(*a)
        def assignment(*a):
            calls.append('assignment');return real_a(*a)
        with patch.object(inject,'potential_outcome',side_effect=potential), patch.object(inject,'assign_injected',side_effect=assignment):
            _, rows, _, _ = inject.simulate(keys(80), [i%3 == 0 for i in range(80)])
        self.assertEqual(calls, ['potential','potential','assignment'])
        self.assertEqual((rows[0]['n_A'],rows[0]['n_B']), (rows[1]['n_A'],rows[1]['n_B']))
        self.assertEqual(rows[0]['buyers_A'], rows[1]['buyers_A'])

    def test_assignment_independent_and_old_api_unchanged(self):
        k = keys(80)
        a = inject.simulate(k, [i%4 == 0 for i in range(80)])[2]
        b = inject.simulate(k, [0]*80)[2]
        np.testing.assert_array_equal(a,b)
        # Independent hex-leading-digit calculation of the same 64-bit threshold.
        expected = [hashlib.sha256(('rees46-injected-assignment-v1|rees46-injected-v1-0001|'+key).encode()).hexdigest()[0] in '89abcdef'
                    for key in sorted(k)]
        self.assertEqual(a.tolist(), expected)
        with self.assertRaises(ValueError):assign(prepare_keys(k), inject.EXPERIMENT_ID)
        with self.assertRaises(ValueError):inject.assign_injected(k, 'rees46-aa-v1-0001')
        with self.assertRaises(ValueError):inject.assign_injected(k, 'rees46-injected-v1-0002')

    def test_literal_group_flip_identity(self):
        # A: one of four buys; B: one of four buys, then two B and one A potentials flip.
        y0 = np.array([1,0,0,0,1,0,0,0],dtype=np.int8)
        y1 = np.array([1,1,0,0,1,1,1,0],dtype=np.int8)
        p = dict(keys=keys(8),y0=y0,p0=Fraction(1,4),deltas=(Fraction(0),Fraction(1,8)),
                 outcomes=((y0.copy(),Fraction(0)),(y1,Fraction(1,6))))
        with patch.object(inject,'assign_injected',return_value=np.array([False]*4+[True]*4)):
            rows,_,identity = inject.evaluate(p)
        self.assertEqual([r['difference'] for r in rows], [0,.5])
        self.assertEqual(rows[1]['K'], 3)
        self.assertEqual(rows[1]['tau'], 3/8)
        self.assertEqual(rows[1]['estimation_error'], 1/8)
        self.assertEqual(rows[1]['flips_B'], 2)
        self.assertEqual(identity['estimated_increment_exact'], '1/2')
        self.assertEqual(identity['expected_exact'], '1/2')
        self.assertEqual(identity['status'], 'passed')
        self.assertIsNone(rows[1]['ci_contains_tau'])  # Sparse cells retain estimates, not inference.

    def test_small_synthetic_binomial_mechanism(self):
        r = inject.synthetic_mc()
        self.assertEqual(r['expected_mean_K'], 8)
        self.assertAlmostEqual(r['mc_se_mean_K'], .12)
        self.assertTrue(r['passed'], r)


if __name__ == '__main__':unittest.main()
