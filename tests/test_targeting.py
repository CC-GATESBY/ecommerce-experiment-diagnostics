"""Synthetic fixtures only; no raw source or private cache read."""
import copy
import csv
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import duckdb
import numpy as np

from uplift.targeting import ROOT,aligned_cache,cuts,train_rules,rank_valid,joint_table,evaluate,resample_joint
from uplift.split import row_id,assign,MEMBERSHIP_HEADER
from ingest.ingest_criteo_source import HEADER

CFG=json.loads((ROOT/'config/targeting.json').read_text())


def fixture(change_y=False,change_t=False):
    c=duckdb.connect();c.execute('CREATE TABLE cache(row_id VARCHAR,split VARCHAR,f0 DOUBLE,f1 DOUBLE,treatment TINYINT,conversion TINYINT)')
    records=[]
    for g in [0,1]:
        for t in [0,1]:
            successes=[[2,10],[10,11]][g][t]
            for i in range(20):records.append((f't-{g}-{t}-{i}','train',g,g,t,int(i<successes)))
    for i in range(40):
        g=i%4
        records.append((f'v-{i:03d}','valid',g//2,g%2,(i//4%2) ^ int(change_t and i==0),int(i%7==0) ^ int(change_y)))
    c.executemany('INSERT INTO cache VALUES (?,?,?,?,?,?)',records)
    return c


class TargetingTests(unittest.TestCase):
    def test_train_only_support_fallback_and_ranking(self):
        c=fixture();f=train_rules(c,dict(CFG,min_train_arm_n=10));c.close()
        self.assertEqual(f['boundaries'],{'f0':[.5],'f1':[.5]})
        self.assertEqual(f['groups'][0]['p0_train'],.1)
        self.assertEqual(f['groups'][3]['p0_train'],.5)
        self.assertEqual(f['groups'][0]['delta_train'],.4)
        self.assertEqual(f['groups'][3]['delta_train'],.05)
        self.assertLess(f['groups'][0]['incremental_rank'],f['groups'][3]['incremental_rank'])
        self.assertGreater(f['groups'][0]['response_rank'],f['groups'][3]['response_rank'])
        self.assertTrue(f['groups'][1]['fallback']);self.assertEqual(f['groups'][1]['response_score'],.3)
        self.assertEqual(cuts([0,0,0],0,0),[])
        self.assertEqual(cuts([0,1,1],0,2),[1])
        c=fixture();c.execute('UPDATE cache SET f0=1,f1=1');constant=train_rules(c,CFG);c.close()
        self.assertEqual(len(constant['groups']),1);self.assertTrue(constant['groups'][0]['fallback'])

    def test_valid_labels_treatment_do_not_change_membership(self):
        outputs=[]
        for y,t in [(False,False),(True,False),(False,True)]:
            c=fixture(y,t);f=train_rules(c,dict(CFG,min_train_arm_n=10));n=rank_valid(c,f)
            outputs.append((f,c.execute('SELECT row_id,rank_random,rank_response,rank_incremental FROM ranked ORDER BY row_id').fetchall()))
            joint,spec=joint_table(c,n,CFG);a,d,b=evaluate(joint,spec,dict(CFG,bootstrap_repetitions=100))
            self.assertEqual([r['selected_n'] for r in a],[4,8,12,20,40]*3)
            for r in d:
                if r['capacity_percent']==100:self.assertEqual((r['G_difference'],r['ci95_low'],r['ci95_high']),(0,0,0))
            for rule in ['random','response','incremental']:
                sets=[set(x[0] for x in c.execute('SELECT row_id FROM ranked WHERE rank_'+rule+'<=?',[k]).fetchall()) for k in [4,8,12,20,40]]
                self.assertTrue(all(x<=z for x,z in zip(sets,sets[1:])))
            expected=sorted([f'v-{i:03d}' for i in range(40)],key=lambda rid:(hashlib.sha256(('target-v1|20260921|'+rid).encode()).hexdigest(),rid))
            self.assertEqual([r[0] for r in c.execute('SELECT row_id FROM ranked ORDER BY rank_random').fetchall()],expected)
            c.close()
        self.assertEqual(outputs[0],outputs[1]);self.assertEqual(outputs[0],outputs[2])

    def test_joint_bootstrap_record_equivalence_moments(self):
        # Independent algorithms, shared joint flags; equivalence assessed within Monte Carlo error.
        flags=np.array([[int(i<8),int(i>=4)] for i in range(12)])
        ys=np.array([0,1,0,1,0,0,1,0,1,0,1,0])
        joint=[]
        for arm in [0,1]:
            for i in range(12):joint.append(dict(treatment=arm,conversion=int(ys[i]),mask=int(flags[i,0]+2*flags[i,1]),n=1))
        spec=[dict(bit=0,c_actual=2/3),dict(bit=1,c_actual=2/3)]
        _,compressed,_=resample_joint(joint,spec,dict(CFG,bootstrap_repetitions=6000))
        rng=np.random.default_rng(918);direct=[]
        for _ in range(6000):
            rates=[]
            for arm in [0,1]:
                ix=rng.integers(0,12,size=12);den=flags[ix].sum(axis=0);num=(flags[ix]*ys[ix,None]).sum(axis=0)
                rates.append(np.divide(num,den,out=np.full(2,np.nan),where=den>0))
            direct.append((rates[1]-rates[0])*10000*2/3)
        direct=np.asarray(direct)
        x=compressed[np.isfinite(compressed).all(axis=1)];z=direct[np.isfinite(direct).all(axis=1)]
        mcse=np.sqrt(x.var(axis=0,ddof=1)/len(x)+z.var(axis=0,ddof=1)/len(z))
        self.assertTrue(np.all(abs(x.mean(axis=0)-z.mean(axis=0))<6*mcse))
        for i in range(2):
            for j in range(2):
                a=(x[:,i]-x[:,i].mean())*(x[:,j]-x[:,j].mean());b=(z[:,i]-z[:,i].mean())*(z[:,j]-z[:,j].mean())
                error=np.sqrt(a.var(ddof=1)/len(a)+b.var(ddof=1)/len(b))
                self.assertLess(abs(a.mean()-b.mean()),6*error)
        self.assertGreater(np.cov(x.T)[0,1],0)

    def test_sparse_negative_zero_and_shared_full_coverage(self):
        # The whole sample is selected at every synthetic capacity to isolate edge behavior.
        joint=[dict(treatment=0,conversion=1,mask=32767,n=2),dict(treatment=1,conversion=0,mask=32767,n=2)]
        spec=[dict(rule=r,capacity_percent=k,selected_n=4,c_actual=1,bit=5*i+j) for i,r in enumerate(['RANDOM','RESPONSE','INCREMENTAL']) for j,k in enumerate([10,20,30,50,100])]
        a,d,draw=evaluate(joint,spec,dict(CFG,bootstrap_repetitions=20))
        self.assertEqual(a[0]['delta_S'],-1);self.assertEqual(a[0]['interval_status'],'sparse_not_for_strong_inference')
        self.assertTrue(all(x['G_difference']==0 for x in d))
        empty=copy.deepcopy(joint);empty[0]['n']=0
        for s in spec:s['selected_n']=2
        a,d,_=evaluate(empty,spec,dict(CFG,bootstrap_repetitions=20))
        self.assertIsNone(a[0]['G']);self.assertEqual(a[0]['interval_status'],'zero_denominator')
        self.assertEqual(a[0]['bootstrap_valid'],0)

    def test_strict_alignment_and_test_not_retained(self):
        source='0'*64
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);raw=p/'source.csv';member=p/'member.gz';test_seen=0
            with raw.open('w',newline='') as f,gzip.open(member,'wb') as m:
                w=csv.writer(f);w.writerow(HEADER);m.write(MEMBERSHIP_HEADER)
                for i in range(40):
                    rid=row_id(source,i);t=str(i%2);s=assign(rid,t)
                    values=['1','2']+['synthetic,quoted\nvalue']*10+[t,'1','unused','unused']
                    if s=='test':values[0]='DO_NOT_PARSE';values[13]='DO_NOT_ANALYZE';test_seen+=1
                    w.writerow(values);m.write(f'{i}\t{rid}\t{t}\t{s}\n'.encode())
            r=aligned_cache(raw,member,source,p/'cache.tsv')
            self.assertEqual(r['records'],40);self.assertGreater(test_seen,0)
            with (p/'cache.tsv').open() as stream:cached=list(csv.DictReader(stream,delimiter='\t'))
            self.assertEqual(len(cached),40-test_seen);self.assertNotIn('test',{x['split'] for x in cached})
            self.assertNotIn('DO_NOT',(p/'cache.tsv').read_text())
            with self.assertRaises(FileExistsError):aligned_cache(raw,member,source,p/'cache.tsv')
            with gzip.open(member,'ab') as m:m.write(b'extra\n')
            with self.assertRaises(ValueError):aligned_cache(raw,member,source,p/'bad.tsv')


if __name__=='__main__':unittest.main()
