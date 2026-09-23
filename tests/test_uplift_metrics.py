"""Small synthetic checks; never train, read real data, or run the actual bootstrap."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from uplift import models
from uplift.evaluate import (no_training,rank_scores,capacity_evaluation,qini_curves,qini_point,trapezoid_area)
from uplift.split import row_id,MEMBERSHIP_HEADER
from ingest.ingest_criteo_source import HEADER
from scripts.run_model_evaluation import extract_test


class ConditionalModel:
    def predict_proba(self,x):
        p=.6-.2*x[:,-1] if x.shape[1]==13 else .2+.1*x[:,0]
        return np.column_stack([1-p,p])


class ModelEvaluationTests(unittest.TestCase):
    def config(self):
        return dict(capacities_percent=[10,20,30,50,100],max_joint_types=12500,
                    bootstrap_seed=20260924,bootstrap_repetitions=100,sparse_min_success_or_failure_per_arm=10)

    def test_training_is_blocked_and_model_identity_checked(self):
        with no_training():
            for call in (lambda:HistGradientBoostingClassifier().fit([[0]],[0]),
                         lambda:HistGradientBoostingClassifier().partial_fit([[0]],[0]),
                         lambda:models.fit_classifier(None,None,None,None,None,None)):
                with self.assertRaisesRegex(RuntimeError,'training forbidden'):call()
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'fake.joblib';f.write_bytes(b'not a model')
            with patch.object(models.joblib,'load',side_effect=AssertionError('must not deserialize')):
                with self.assertRaisesRegex(ValueError,'fingerprint'):models.load_own_model(f,'wrong',Path(tmp))

    def test_condition_scoring_and_label_isolation(self):
        x=np.zeros((10,12),dtype=np.float64);x[:,0]=np.arange(10)/10
        response=models.predict_conditions(ConditionalModel(),'RESPONSE_MODEL',x)[:,0]
        s=models.predict_conditions(ConditionalModel(),'S_LEARNER',x)
        np.testing.assert_allclose(s[:,0],.6);np.testing.assert_allclose(s[:,1],.4)
        tc=models.predict_conditions(ConditionalModel(),'T_CONTROL',x)[:,0]
        tt=tc-.05
        scores=dict(RANDOM=np.zeros(10),FROZEN_SIMPLE=np.zeros(10),RESPONSE_MODEL=response,
                    S_LEARNER=s[:,1]-s[:,0],T_LEARNER=tt-tc)
        self.assertTrue((scores['S_LEARNER']<0).all());self.assertTrue((scores['T_LEARNER']<0).all())
        ids=np.array([str(i).encode() for i in range(10)],dtype='S64');ranks=rank_scores(scores,ids)
        # Evaluation labels/arms change while the selected scores/ranks stay fixed.
        t=np.arange(10,dtype=np.uint8)%2;y=t.copy()
        capacity_evaluation(ranks,t,y,self.config());capacity_evaluation(ranks,1-t,1-y,self.config())
        again=rank_scores(scores,ids)
        for name in models.POLICIES:np.testing.assert_array_equal(ranks[name],again[name])
        order=np.arange(9,-1,-1)
        reordered=rank_scores({k:v[order] for k,v in scores.items()},ids[order])
        for name in models.POLICIES:np.testing.assert_array_equal(ranks[name][order],reordered[name])
        ties=np.array([hashlib.sha256(b'target-v1|20260921|'+bytes(i)).hexdigest().encode() for i in ids])
        for name in models.POLICIES:
            for cap in [10,20,30,50,100]:
                expected=models.select_by_score(scores[name],ids,ties,cap*len(ids)//100)
                np.testing.assert_array_equal(ranks[name]<=cap*len(ids)//100,expected)

    def test_joint_overlap_capacity_negative_and_empty_arm(self):
        ranks={p:np.arange(1,21,dtype=np.int32) for p in models.POLICIES}
        t=np.arange(20,dtype=np.uint8)%2;y=1-t
        rows,differences,joint=capacity_evaluation(ranks,t,y,self.config())
        self.assertEqual(sum(j['n'] for j in joint),20)
        self.assertEqual(len(rows),25);self.assertEqual(len(differences),20)
        for r in rows:
            self.assertEqual(r['selected_n'],20*r['capacity_percent']//100)
            self.assertEqual(r['G'],-100*r['capacity_percent'])
            self.assertIn('sparse',r['status'])
        for d in differences:
            self.assertEqual([d['G_difference'],d['ci95_low'],d['ci95_high']],[0,0,0])
        missing,_,_=capacity_evaluation(ranks,np.ones(20,dtype=np.uint8),y,self.config())
        self.assertTrue(all(r['G'] is None and r['bootstrap_invalid']==100 and r['status']=='zero_denominator' for r in missing))
        again=capacity_evaluation(ranks,t,y,self.config())
        self.assertEqual(rows,again[0]);self.assertEqual(differences,again[1])

    def test_qini_hand_calculated_grid_and_area(self):
        ranks={p:np.arange(1,5,dtype=np.int32) for p in models.POLICIES}
        t=np.array([0,1,0,1]);y=np.array([0,1,1,0])
        grid,areas=qini_curves(ranks,t,y)
        r=[q for q in grid if q['policy']=='RANDOM' and q['nominal_capacity_percent'] in [0,25,50,75,100]]
        self.assertEqual([q['Q'] for q in r],[0,0,1,.5,0])
        self.assertEqual([q['reference_L'] for q in r],[0,0,0,0,0])
        self.assertEqual(r[2]['Q_minus_L'],1)  # Actual RANDOM is not the conventional line.
        self.assertTrue(all(a['unnormalized_qini_area_approx']==.375 for a in areas))
        self.assertEqual(qini_point(1,2,1,0),(-2.,'point_estimate_only'))
        self.assertEqual(qini_point(0,1,0,1),(None,'no_control_prefix'))
        missing,area=qini_curves(ranks,t[::-1],y)
        self.assertTrue(any(q['status']=='no_control_prefix' for q in missing))
        self.assertTrue(all(a['unnormalized_qini_area_approx'] is None for a in area))
        zero,area=qini_curves(ranks,t,np.zeros(4,dtype=int))
        self.assertTrue(all(q['Q']==0 for q in zero));self.assertTrue(all(a['unnormalized_qini_area_approx']==0 for a in area))
        self.assertIsNone(trapezoid_area([0,.5,1],[0,None,2]))

    def test_stream_extract_alignment_and_no_other_split_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=root/'synthetic.csv';member=root/'membership.gz';sha=hashlib.sha256(b'synthetic-source').hexdigest()
            # Duplicate original test values retain separate ordinal identities.
            test=[str(i) for i in range(12)]+['0','1','unused','unused']
            other=['do_not_parse']*12+['1','do_not_parse','unused','unused']
            records=[test,other,test,other];splits=['test','train','test','valid']
            with raw.open('w',newline='') as f:
                w=csv.writer(f);w.writerow(HEADER);w.writerows(records)
            with gzip.open(member,'wb') as f:
                f.write(MEMBERSHIP_HEADER)
                for i,(record,split) in enumerate(zip(records,splits)):
                    f.write(f'{i}\t{row_id(sha,i)}\t{record[12]}\t{split}\n'.encode())
            with patch('scripts.run_model_evaluation.assign',side_effect=splits):
                receipt=extract_test(raw,member,sha,root/'cache',2)
            self.assertEqual(receipt['scanned_records'],4);self.assertEqual(receipt['test_n'],2)
            self.assertEqual(receipt['counts'],dict(train=[0,1],valid=[0,1],test=[2,0]))
            self.assertEqual(receipt['conversions'],[2,0])
            x=np.load(root/'cache/X.npy');np.testing.assert_array_equal(x,np.array([range(12),range(12)]))
            ids=np.load(root/'cache/row_id.npy');self.assertNotEqual(ids[0],ids[1])
            with self.assertRaises(FileExistsError):extract_test(raw,member,sha,root/'cache',2)
            with patch('scripts.run_model_evaluation.assign',return_value='train'):
                with self.assertRaisesRegex(ValueError,'alignment|membership'):extract_test(raw,member,sha,root/'bad',2)
            self.assertFalse((root/'bad/complete.json').exists())


if __name__=='__main__':unittest.main()
