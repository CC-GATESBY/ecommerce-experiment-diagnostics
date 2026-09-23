"""Synthetic input isolation, explicit stopping, ranking and paired-policy checks."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import joblib
import numpy as np
from threadpoolctl import threadpool_limits
from uplift import models
from uplift.split import row_id, assign, MEMBERSHIP_HEADER
from ingest.ingest_criteo_source import HEADER
from scripts.run_uplift_baselines import extract_cache


class ModelTests(unittest.TestCase):
    def test_whitelist_train_only_and_T_arms(self):
        models.check_features([f'f{i}' for i in range(12)])
        for names in (models.FEATURES+['exposure'],models.FEATURES[:-1]+['row_id'],models.FEATURES[::-1]):
            with self.assertRaises(ValueError):models.check_features(names)
        with self.assertRaises(ValueError):models.early_member('a'*64,'valid')
        with self.assertRaises(ValueError):models.early_member('a'*64,'test')
        identity='b'*64
        expected=int(hashlib.sha256(('e1-early-stop-v1|20260923|'+identity).encode()).hexdigest()[:16],16)<2**64//10
        self.assertEqual(models.early_member(identity,'train'),expected)
        e=np.array([0,0,1,1],dtype=np.uint8);t=np.array([0,1,0,1],dtype=np.uint8)
        self.assertEqual(models.training_indices(e,t,'fit','T_CONTROL').tolist(),[0])
        self.assertEqual(models.training_indices(e,t,'early_stop','T_TREATMENT').tolist(),[3])
        self.assertEqual(models.training_indices(e,t,'fit','RESPONSE_MODEL').tolist(),[0,1])
        self.assertEqual(models.training_indices(e,t,'fit','S_LEARNER').tolist(),[0,1])

    def test_explicit_validation_no_internal_split_and_local_reload(self):
        x=np.arange(80*12,dtype=np.float64).reshape(80,12)/100
        y=np.arange(80)%2;xe=x[:24].copy();ye=y[:24].copy()
        with threadpool_limits(limits=4),patch('sklearn.ensemble._hist_gradient_boosting.gradient_boosting.train_test_split',
                                              side_effect=AssertionError('unexpected internal early split')):
            model=models.fit_classifier('RESPONSE_MODEL',x,y,xe,ye,pilot=True)
        self.assertEqual(len(model.validation_score_),model.n_iter_+1)
        self.assertLessEqual(model.n_iter_,10)
        expected=models.predict_conditions(model,'RESPONSE_MODEL',xe)
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'synthetic.joblib';joblib.dump(model,path)
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            loaded=models.load_own_model(path,digest,Path(temp))
            np.testing.assert_array_equal(expected,models.predict_conditions(loaded,'RESPONSE_MODEL',xe))
            with self.assertRaises(ValueError):models.load_own_model(path,'0'*64,Path(temp))
        with self.assertRaises(ValueError):models.fit_classifier('RESPONSE_MODEL',x,y,xe,np.zeros(24))

    def test_S_potential_conditions_only_treatment_changes(self):
        calls=[]
        class Fake:
            def predict_proba(self,x):
                calls.append(x.copy());p=.6-.2*x[:,-1]
                return np.column_stack((1-p,p))
        x=np.arange(60,dtype=float).reshape(5,12)
        p=models.predict_conditions(Fake(),'S_LEARNER',x)
        np.testing.assert_array_equal(calls[0][:,:12],x)
        np.testing.assert_array_equal(calls[1][:,:12],x)
        self.assertTrue((calls[0][:,-1]==0).all() and (calls[1][:,-1]==1).all())
        np.testing.assert_allclose(p[:,1]-p[:,0],[-.2]*5)
        # Neither observed validation treatment nor labels is an input to scoring.
        for observed_t,labels in ((np.zeros(5),np.ones(5)),(np.ones(5),np.zeros(5))):
            np.testing.assert_array_equal(models.predict_conditions(Fake(),'S_LEARNER',x),p)

    def test_fixed_simple_DOUBLE_boundaries_ties_and_capacity(self):
        frozen=dict(boundaries={'f0':[1.00000000001],'f1':[]},groups=[
            dict(group_id=0,response_rank=1,incremental_rank=1),dict(group_id=1,response_rank=2,incremental_rank=2)])
        x=np.zeros((3,12));x[:,0]=[1.,1.00000000001,1.00000000002]
        self.assertEqual(models.simple_scores(x,frozen).tolist(),[-1,-1,-2])
        ids=np.array([b'c',b'a',b'b']);ties=np.array([b'x',b'x',b'x'])
        selected=models.select_by_score(np.array([-1.,-1.,-2.]),ids,ties,1)
        self.assertEqual(selected.tolist(),[False,True,False])
        constant=models.select_by_score(np.zeros(3),ids,ties,2)
        self.assertEqual(constant.tolist(),[False,True,True])
        with self.assertRaises(ValueError):models.select_by_score(np.array([np.nan,0.,1.]),ids,ties,1)

    def test_joint_paired_differences_and_failed_sparse_states(self):
        n=40;t=np.array([0]*20+[1]*20);y=np.array([1]*6+[0]*14+[0]*14+[1]*6)
        ids=np.array([f'{i:064x}'.encode() for i in range(n)]);ties=ids.copy()
        scores={'RANDOM':np.zeros(n),'FROZEN_SIMPLE':np.zeros(n),
                'RESPONSE_MODEL':np.array([1]*6+[0]*28+[1]*6),'S_LEARNER':np.zeros(n),'T_LEARNER':np.zeros(n)}
        selected={k:models.select_by_score(v,ids,ties,12) for k,v in scores.items()}
        cfg=dict(capacity_percent=30,bootstrap_seed=20260923,bootstrap_repetitions=1000)
        rows,overlaps,joint,draws=models.policy_evaluation(selected,t,y,cfg)
        self.assertEqual(rows[0]['status'],'zero_denominator')
        self.assertEqual(rows[0]['bootstrap_valid'],0)
        self.assertEqual(rows[2]['status'],'sparse_not_for_strong_inference')
        self.assertEqual(rows[2]['G'],0.)  # Six successes of six in both selected arms.
        self.assertEqual(sum(r['n'] for r in joint),40)
        again=models.policy_evaluation(selected,t,y,cfg)
        np.testing.assert_array_equal(draws,again[3])
        self.assertTrue(next(r for r in overlaps if r['policy_a']=='RANDOM' and r['policy_b']=='S_LEARNER')['identical'])
        # Balanced identical lists yield exact zero paired differences; negative effects survive.
        take=np.array([True]*6+[False]*14+[True]*6+[False]*14)
        all_same={k:take.copy() for k in models.POLICIES}
        rows,_,_,draws=models.policy_evaluation(all_same,t,y,cfg)
        self.assertEqual(rows[0]['G'],-3000.)
        self.assertEqual(rows[2]['G_minus_FROZEN_SIMPLE'],0.)
        self.assertEqual(rows[2]['ci95_low_minus_FROZEN_SIMPLE'],0.)
        self.assertEqual(rows[2]['ci95_high_minus_FROZEN_SIMPLE'],0.)
        with self.assertRaises(ValueError):
            broken=dict(all_same);broken['S_LEARNER']=np.ones(n,dtype=bool)
            models.policy_evaluation(broken,t,y,cfg)

    def test_small_stream_cache_never_converts_test_features_or_labels(self):
        source='a'*64;records=[];members=[];sizes=dict(train=0,valid=0,test=0)
        for i in range(600):
            arm=str(i%2);rid=row_id(source,i);split=assign(rid,arm);sizes[split]+=1
            features=['do-not-convert']*12 if split=='test' else [str(j+i/1000) for j in range(12)]
            outcome='unread-test-label' if split=='test' else str((i//2)%2)
            records.append(features+[arm,outcome,'unused-visit','unused-exposure'])
            members.append(f'{i}\t{rid}\t{arm}\t{split}\n'.encode())
        manifest={'qc':{'groups':[dict(split=s,treatment='all',n=n) for s,n in sizes.items()]}}
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);raw=root/'synthetic.csv';member=root/'synthetic.tsv.gz';out=root/'cache';out.mkdir()
            with raw.open('w',newline='') as f:
                w=csv.writer(f);w.writerow(HEADER);w.writerows(records)
            with gzip.open(member,'wb') as f:f.write(MEMBERSHIP_HEADER+b''.join(members))
            proof=extract_cache(raw,member,source,out,manifest)
            self.assertEqual(proof['records'],600)
            self.assertFalse((out/'test').exists())
            self.assertFalse(proof['test_features_or_conversion_converted_or_retained'])
            self.assertEqual(np.load(out/'train/X.npy').dtype,np.dtype('float64'))
            self.assertEqual(len(np.load(out/'valid/y.npy')),sizes['valid'])
            with self.assertRaises(FileExistsError):extract_cache(raw,member,source,out,manifest)


if __name__=='__main__':unittest.main()
