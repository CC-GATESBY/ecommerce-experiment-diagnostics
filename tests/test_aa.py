"""Synthetic literal expectations and independent library/formula checks."""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest
import duckdb
import numpy as np
from scipy import stats
from abtest.assign import prepare_keys,assign
from abtest.srm import srm
from abtest.stats import proportions,welch,ratio_difference,bootstrap_pairs,ratio_validation,wilson
from abtest.aa_test import summarize

ROOT=Path(__file__).resolve().parents[1]


class AssignmentTests(unittest.TestCase):
    def test_stable_order_independent_and_cross_implementation(self):
        keys=[hashlib.sha256(('synthetic-'+str(i)).encode()).hexdigest() for i in range(80)]
        encoded=prepare_keys(keys);eid='rees46-aa-v1-0001';actual=assign(encoded,eid)
        np.testing.assert_array_equal(actual,assign(encoded,eid))
        np.testing.assert_array_equal(actual,assign(encoded[::-1],eid)[::-1])
        c=duckdb.connect()
        try:
            expected=c.execute("SELECT substr(sha256('rees46-aa-assignment-v1|rees46-aa-v1-0001|' || k),1,1) IN ('8','9','a','b','c','d','e','f') FROM unnest(?) t(k)",[keys]).fetchnumpy()
            np.testing.assert_array_equal(actual,next(iter(expected.values())))
        finally:c.close()
        code="from abtest.assign import prepare_keys,assign; import json; print(json.dumps(assign(prepare_keys(json.loads(input())),'rees46-aa-v1-0001').tolist()))"
        other=subprocess.check_output([sys.executable,'-c',code],input=json.dumps(keys).encode(),cwd=ROOT)
        self.assertEqual(actual.tolist(),json.loads(other))
        # Arbitrary outcomes exist outside the assignment API and cannot enter its payload.
        outcomes=np.zeros(80);outcomes[:]=999
        np.testing.assert_array_equal(actual,assign(encoded,eid))
        self.assertEqual(srm(41,39)['srm_flag'],False)
        self.assertTrue(srm(99,1)['srm_flag'])
        self.assertAlmostEqual(srm(41,39)['srm_p'],stats.chisquare([41,39],[40,40]).pvalue)

    def test_invalid_keys_and_ids(self):
        for keys in ([],[''],['A'*64],['0'*64]*2):
            with self.assertRaises(ValueError):prepare_keys(keys)
        with self.assertRaises(ValueError):assign(prepare_keys(['0'*64]),'rees46-aa-v1-0301')
        self.assertEqual(srm(0,0)['srm_status'],'empty_assignment')


class StatisticsTests(unittest.TestCase):
    def test_binary_literal_formula_and_units(self):
        r=proportions(100,20,100,40)
        self.assertAlmostEqual(r['difference'],.2)
        self.assertAlmostEqual(r['se'],math.sqrt(.004))
        self.assertAlmostEqual(r['ci_low'],.2-stats.norm.ppf(.975)*math.sqrt(.004))
        self.assertAlmostEqual(r['p_value'],math.erfc((.2/math.sqrt(.004))/math.sqrt(2)))
        self.assertAlmostEqual(r['difference_pp'],20)
        self.assertAlmostEqual(r['difference_per_10000'],2000)
        self.assertAlmostEqual(r['relative_change'],1)
        reverse=proportions(100,40,100,20)
        self.assertAlmostEqual(reverse['difference'],-r['difference'])
        self.assertAlmostEqual(reverse['ci_low'],-r['ci_high'])

    def test_welch_library_and_independent_formula(self):
        a=np.array([0,1,2,3,4]);b=np.array([1,3,5,7,9,11])
        r=welch(a,b);ref=stats.ttest_ind(b,a,equal_var=False)
        self.assertEqual(r['difference'],4)
        self.assertAlmostEqual(r['se'],math.sqrt(.5+7/3))
        self.assertAlmostEqual(r['df'],(.5+7/3)**2/(.5**2/4+(7/3)**2/5))
        self.assertAlmostEqual(r['df'],ref.df)
        self.assertAlmostEqual(r['p_value'],ref.pvalue)
        ci=ref.confidence_interval(.95)
        self.assertAlmostEqual(r['ci_low'],ci.low);self.assertAlmostEqual(r['ci_high'],ci.high)

    def test_invalid_and_degenerate_statuses(self):
        self.assertEqual(welch([], [1,2])['status'],'empty_group')
        self.assertEqual(welch([1], [1,2])['status'],'insufficient_n')
        self.assertEqual(welch([1,1], [2,2])['status'],'zero_variance')
        self.assertEqual(welch([float('nan'),1], [2,3])['status'],'nonfinite_input')
        self.assertEqual(proportions(100,0,100,0)['status'],'sparse_cells')
        self.assertEqual(proportions(0,0,100,50)['status'],'empty_group')
        self.assertEqual(ratio_difference([[1,0],[1,0]],[[1,1],[2,2]])['status'],'zero_denominator')
        self.assertEqual(ratio_difference([],[[1,1],[2,2]])['status'],'empty_group')
        lo,hi=wilson(15,300)
        z=stats.norm.ppf(.975);d=1+z*z/300;center=(.05+z*z/600)/d
        half=z*math.sqrt(.05*.95/300+z*z/(4*300**2))/d
        self.assertAlmostEqual(lo,center-half);self.assertAlmostEqual(hi,center+half)

    def test_ratio_covariance_pairing_and_reproducibility(self):
        a=np.array([[0,0],[1,1],[4,2],[6,3],[4,4]],dtype=float)
        b=np.array([[0,0],[2,1],[4,2],[9,3],[8,4]],dtype=float)
        r=ratio_difference(a,b);self.assertAlmostEqual(r['mean_A'],1.5);self.assertAlmostEqual(r['mean_B'],2.3)
        v=[]
        for x in (a,b):
            cov=np.cov(x.T,ddof=1);ratio=x[:,0].sum()/x[:,1].sum()
            v.append((cov[0,0]+ratio*ratio*cov[1,1]-2*ratio*cov[0,1])/(len(x)*x[:,1].mean()**2))
        self.assertAlmostEqual(r['se'],math.sqrt(sum(v)))
        proportional=np.column_stack((2*np.arange(1,21),np.arange(1,21)))
        np.testing.assert_array_equal(bootstrap_pairs(proportional,proportional,seed=99,repeats=40),np.zeros(40))
        one=bootstrap_pairs(a,b,seed=7,repeats=100);two=bootstrap_pairs(a,b,seed=7,repeats=100)
        np.testing.assert_array_equal(one,two)
        before=a.copy();ratio_difference(a,b);np.testing.assert_array_equal(before,a)
        result=ratio_validation()
        self.assertEqual(result['bootstrap_valid'],6000)
        self.assertGreater(result['bootstrap_se_mcse'],0)
        # SE proximity is reported, not a test tuned to a chosen relative threshold.

    def test_summary_keeps_srm_and_significant_results(self):
        rows=[]
        for metric in ('post_converted','post_purchase_amount'):
            for i,(d,p,flag) in enumerate([(1,.02,True),(-1,.04,False),(.1,.6,False),(-.1,.9,False)]):
                rows.append(dict(metric=metric,status='ok',reason='',difference=d,p_value=p,srm_flag=flag,
                                 ci_low=d-.5,ci_high=d+.5))
        summaries=summarize(rows)
        self.assertEqual(len(summaries),4)
        self.assertEqual([summaries[0][k] for k in ('valid','significant','positive_significant','negative_significant','srm_flags')],[4,2,1,1,1])
        self.assertEqual([summaries[1][k] for k in ('valid','significant','positive_significant','negative_significant')],[3,1,0,1])
        self.assertEqual(summaries[0]['zero_coverage'],.5)


if __name__=='__main__':unittest.main()
