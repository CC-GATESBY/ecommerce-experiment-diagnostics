"""One bounded E1 run: cache, interface pilot, four serial classifiers, valid comparison."""
import argparse
import csv
import gc
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time

# Set before importing numeric runtimes; each worker is serial at the process level.
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[name]='4'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import duckdb
import joblib
import numpy as np
import sklearn
from threadpoolctl import threadpool_limits, threadpool_info
from uplift import models
from uplift.ingest_criteo import bind_source, CSV_SHA, RECORDS
from uplift.split import row_id, assign, MEMBERSHIP_HEADER
from ingest.ingest_criteo_source import HEADER
from uplift.targeting import require, sha, dump, csv_out
from uplift.targeting_holdout import load_frozen

CONFIG=ROOT/'config/uplift_baselines.json'
SHARED=['uplift_development_metrics.csv','uplift_valid_policy_comparison.csv','uplift_valid_overlaps.csv']


def config():
    c=json.loads(CONFIG.read_text())
    models.check_features(c['features'])
    require(c['parameters']==models.PARAMETERS and c['training_order']==models.ROLES and c['policies']==models.POLICIES,
            'frozen model settings differ')
    require(c['source_sha256']==CSV_SHA and c['outcome']=='conversion' and c['capacity_percent']==30 and
            c['bootstrap_seed']==20260923 and c['bootstrap_repetitions']==1000 and c['sklearn_version']==sklearn.__version__,
            'frozen evaluation/environment differs')
    require(c['early_stop_prefix']==models.EARLY_PREFIX and c['pilot_prefix']==models.PILOT_PREFIX,
            'frozen hash namespace differs')
    return c


def array(path,mode='r'):
    return np.load(path,mmap_mode=mode,allow_pickle=False)


def allocate(path,dtype,shape):
    require(not path.exists(),'refuse array overwrite')
    return np.lib.format.open_memmap(path,mode='w+',dtype=dtype,shape=shape)


def extract_cache(raw,member,source_sha,out,manifest,progress=None):
    sizes={s:next(g['n'] for g in manifest['qc']['groups'] if g['split']==s and g['treatment']=='all') for s in ('train','valid')}
    arrays={};used=dict(train=0,valid=0)
    for split,n in sizes.items():
        folder=out/split;folder.mkdir()
        schema={'X':('float64',(n,12)),'y':('uint8',(n,)),'t':('uint8',(n,)),
                'row_id':('S64',(n,)),'ordinal':('int64',(n,))}
        if split=='train':schema.update(early_stop=('uint8',(n,)),pilot_hash=('uint64',(n,)))
        arrays[split]={k:allocate(folder/(k+'.npy'),dt,shape) for k,(dt,shape) in schema.items()}
    counts={s:[0,0] for s in ('train','valid','test')}
    conversions={s:[0,0] for s in ('train','valid')}
    sequences={s:hashlib.sha256() for s in ('train','valid','test')}
    logical=hashlib.sha256(MEMBERSHIP_HEADER)
    start=time.monotonic();count=0
    with raw.open(newline='',encoding='utf-8') as f,gzip.open(member,'rb') as m:
        reader=csv.reader(f,strict=True)
        require(next(reader,None)==HEADER and m.readline()==MEMBERSHIP_HEADER,'source/membership header mismatch')
        for ordinal,record in enumerate(reader):
            require(len(record)==16 and record[12] in ('0','1'),'structure/treatment mismatch')
            line=m.readline(256);fields=line.decode('ascii').rstrip('\n').split('\t')
            identity=row_id(source_sha,ordinal);split=assign(identity,record[12])
            require(fields==[str(ordinal),identity,record[12],split],'ordinal/identity/membership mismatch')
            logical.update(line);sequences[split].update((identity+'\n').encode())
            arm=int(record[12]);counts[split][arm]+=1
            if split!='test':
                require(record[13] in ('0','1'),'train/valid conversion invalid')
                a=arrays[split];i=used[split]
                require(i<sizes[split],'excess train/valid records')
                a['X'][i]=record[:12]
                require(np.isfinite(a['X'][i]).all(),'nonfinite train/valid feature')
                a['y'][i]=int(record[13]);a['t'][i]=arm;a['row_id'][i]=identity;a['ordinal'][i]=ordinal
                if split=='train':
                    a['early_stop'][i]=models.early_member(identity,split)
                    a['pilot_hash'][i]=models.hash64(models.PILOT_PREFIX,identity)
                conversions[split][arm]+=int(record[13]);used[split]+=1
            count+=1
            if progress and count%500000==0:progress(count,time.monotonic()-start)
        require(not m.read(1),'extra membership rows')
    require(used==sizes,'incomplete train/valid cache')
    support=[]
    for part in ('fit','early_stop'):
        for arm in (0,1):
            a=arrays['train'];mask=(a['early_stop']==(part=='early_stop'))&(a['t']==arm)
            n=int(mask.sum());y=int(a['y'][mask].sum())
            require(0<y<n,'train internal arm/label support missing')
            support.append(dict(part=part,treatment=arm,n=n,conversion=y))
    for a in arrays.values():
        for v in a.values():v.flush()
    del arrays;gc.collect()
    return dict(records=count,counts=counts,conversions=conversions,support=support,
                logical_sha256=logical.hexdigest(),sequence_sha256={s:h.hexdigest() for s,h in sequences.items()},
                physical_test_bytes_traversed=True,test_features_or_conversion_converted_or_retained=False,
                elapsed_seconds=time.monotonic()-start)


def cache_stage(out):
    raw,_,binding=bind_source(ROOT)
    manifest=json.loads((ROOT/'data/criteo_split_manifest.json').read_text())
    member=ROOT/manifest['membership']['local_relative_path']
    acceptance=json.loads((member.parent/'validation.json').read_text())
    split_run=json.loads((member.parent/'run.json').read_text())
    require(acceptance['status']=='pass' and all(r['pass'] for r in acceptance['checks']) and
            split_run['status']=='complete' and split_run['source_csv_sha256']==CSV_SHA,'split not accepted')
    require(member.resolve().is_relative_to(ROOT/'.local/t31/criteo-split-v1-01/complete') and
            not member.is_symlink() and member.stat().st_size==manifest['membership']['compressed_bytes'] and
            sha(member)==manifest['membership']['compressed_sha256'],'membership identity changed')
    protected={str(p):(p.stat().st_size,p.stat().st_mtime_ns) for p in (raw,member)}
    cache=out/'cache';cache.mkdir()
    receipt=extract_cache(raw,member,CSV_SHA,cache,manifest,
        lambda n,s:print(json.dumps(dict(stage='align',records=n,elapsed_seconds=round(s,1))),flush=True))
    require(receipt['records']==RECORDS and receipt['logical_sha256']==manifest['membership']['logical_sha256'],
            'source count or logical membership fingerprint mismatch')
    for split in ('train','valid','test'):
        require(receipt['sequence_sha256'][split]==manifest['membership']['sequence_sha256'][split],'split identity sequence mismatch')
        for arm in (0,1):
            g=next(g for g in manifest['qc']['groups'] if g['split']==split and g['treatment']==str(arm))
            require(receipt['counts'][split][arm]==g['n'],'split/arm count mismatch')
            if split!='test':require(receipt['conversions'][split][arm]==g['conversion'],'train/valid conversion QC mismatch')
    require(all((Path(p).stat().st_size,Path(p).stat().st_mtime_ns)==v for p,v in protected.items()),'input metadata changed')
    require(sha(raw)==CSV_SHA and sha(member)==manifest['membership']['compressed_sha256'],'input bytes changed')
    receipt.update(status='passed',source_binding=binding,protected_metadata=protected,
                   files={str(p.relative_to(cache)):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in cache.rglob('*.npy')})
    dump(out/'cache_complete.json',receipt)


def training_data(out,role,pilot=False):
    folder=out/'cache/train'
    x=array(folder/'X.npy');y=array(folder/'y.npy');t=array(folder/'t.npy');early=array(folder/'early_stop.npy')
    h=array(folder/'pilot_hash.npy') if pilot else None
    result={};counts=[]
    for part in ('fit','early_stop'):
        ix=models.training_indices(early,t,part,role)
        if pilot:
            limit=100000 if part=='fit' else 10000
            ix=ix[np.lexsort((ix,h[ix]))[:limit]]
        width=13 if role=='S_LEARNER' else 12
        matrix=np.empty((len(ix),width),dtype=np.float64)
        for start in range(0,len(ix),65536):
            take=ix[start:start+65536];matrix[start:start+len(take),:12]=x[take]
            if role=='S_LEARNER':matrix[start:start+len(take),12]=t[take]
        labels=np.array(y[ix],copy=True)
        counts.append(dict(part=part,n=len(ix),control_n=int((t[ix]==0).sum()),treatment_n=int((t[ix]==1).sum()),
                           conversion=int(labels.sum())))
        result[part]=(matrix,labels)
    return result,counts


def train_stage(out,role,pilot=False):
    started=time.monotonic();data,counts=training_data(out,role,pilot)
    fit_start=time.monotonic()
    estimator=models.fit_classifier(role,*data['fit'],*data['early_stop'],pilot=pilot)
    training_seconds=time.monotonic()-fit_start
    name='pilot' if pilot else role
    folder=out/'models';folder.mkdir(exist_ok=True)
    path=folder/(name+'.joblib');require(not path.exists(),'model already exists')
    joblib.dump(estimator,path,compress=3);digest=sha(path)
    iterations=int(estimator.n_iter_);validation_steps=len(estimator.validation_score_)
    if pilot:
        x=data['early_stop'][0][:1024,:12].copy()
        expected=models.predict_conditions(estimator,role,x)
        del estimator;gc.collect();loaded=models.load_own_model(path,digest,folder)
        require(np.array_equal(expected,models.predict_conditions(loaded,role,x)),'pilot reload predictions differ')
        require(counts[0]['n']<=100000 and iterations<=10,'pilot scope exceeded')
        proof=dict(status='passed',kind='resource_interface_pilot_not_model_result',counts=counts,
                   n_iter=iterations,training_seconds=training_seconds,total_seconds=time.monotonic()-started,
                   model_sha256=digest,reload_equal=True)
    else:
        del data;gc.collect()
        x=array(out/'cache/valid/X.npy');width=2 if role=='S_LEARNER' else 1
        predicted=allocate(out/(role+'_predictions.npy'),'float64',(len(x),width))
        for start in range(0,len(x),65536):
            predicted[start:start+65536]=models.predict_conditions(estimator,role,x[start:start+65536])
        predicted.flush();del estimator;gc.collect()
        loaded=models.load_own_model(path,digest,folder)
        for start in range(0,len(x),65536):
            require(np.array_equal(predicted[start:start+65536],models.predict_conditions(loaded,role,x[start:start+65536])),
                    'full valid reload predictions differ')
        proof=dict(status='passed',role=role,counts=counts,n_iter=iterations,validation_steps=validation_steps,
                   training_seconds=training_seconds,total_seconds=time.monotonic()-started,
                   explicit_early_stop=True,valid_used_for_fit=False,full_valid_reload_equal=True,
                   model_sha256=digest,prediction_sha256=sha(out/(role+'_predictions.npy')))
    proof.update(maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                 threadpools=[{k:p.get(k) for k in ('user_api','internal_api','num_threads')} for p in threadpool_info()])
    require(all(p['num_threads']<=4 for p in proof['threadpools']),'thread limit exceeded')
    dump(out/(name+'_receipt.json'),proof)


def selected_digest(ids):
    h=hashlib.sha256()
    for identity in np.sort(ids):h.update(bytes(identity)+b'\n')
    return h.hexdigest()


def old_selection_checks(row_ids,selected,k):
    db=ROOT/'.local/target01/targeting-valid-01/analysis.duckdb'
    c=duckdb.connect(str(db),read_only=True,config={'threads':'1','memory_limit':'512MB'})
    digests={}
    try:
        for name,column in [('RANDOM','rank_random'),('FROZEN_SIMPLE','rank_response')]:
            cursor=c.execute(f'SELECT row_id FROM ranked WHERE {column}<=? ORDER BY row_id',[k])
            h=hashlib.sha256();n=0
            while batch:=cursor.fetchmany(4096):
                for (identity,) in batch:h.update((identity+'\n').encode());n+=1
            actual=selected_digest(row_ids[selected[name]])
            require(n==k and h.hexdigest()==actual,'old valid selection differs')
            digests[name]=actual
    finally:c.close()
    return digests


def evaluation_stage(out):
    cfg=config();frozen,_=load_frozen()
    x=array(out/'cache/valid/X.npy');ids=array(out/'cache/valid/row_id.npy');n=len(ids);k=30*n//100
    response=array(out/'RESPONSE_MODEL_predictions.npy')
    s=array(out/'S_LEARNER_predictions.npy')
    t=np.column_stack((array(out/'T_CONTROL_predictions.npy')[:,0],array(out/'T_TREATMENT_predictions.npy')[:,0]))
    scores=dict(RANDOM=np.zeros(n),FROZEN_SIMPLE=models.simple_scores(x,frozen),
                RESPONSE_MODEL=response[:,0],S_LEARNER=s[:,1]-s[:,0],T_LEARNER=t[:,1]-t[:,0])
    tie=np.fromiter((hashlib.sha256(b'target-v1|20260921|'+bytes(i)).hexdigest().encode() for i in ids),dtype='S64',count=n)
    selected={name:models.select_by_score(score,ids,tie,k) for name,score in scores.items()}
    # All five lists are fixed before any valid outcome or observed-arm evaluation.
    selected_hashes={name:selected_digest(ids[mask]) for name,mask in selected.items()}
    dump(out/'selected_before_outcomes.json',dict(N_valid=n,K=k,selected_sha256=selected_hashes))
    np.savez_compressed(out/'selected_private.npz',**selected)
    old_lists=old_selection_checks(ids,selected,k)
    y=array(out/'cache/valid/y.npy');treatment=array(out/'cache/valid/t.npy')
    rates={};support=json.loads((out/'cache_complete.json').read_text())['support']
    fit=[r for r in support if r['part']=='fit']
    rates['all']=sum(r['conversion'] for r in fit)/sum(r['n'] for r in fit)
    rates.update({str(r['treatment']):r['conversion']/r['n'] for r in fit})
    metrics=models.factual_metrics(y,treatment,dict(RESPONSE_MODEL=response,S_LEARNER=s,T_LEARNER=t),rates)
    policies,overlaps,joint,draws=models.policy_evaluation(selected,treatment,y,cfg)
    old=list(csv.DictReader((ROOT/'reports/targeting/coverage_comparison.csv').open()))
    for name,oldname in [('RANDOM','RANDOM'),('FROZEN_SIMPLE','RESPONSE')]:
        a=next(r for r in policies if r['policy']==name)
        b=next(r for r in old if r['rule']==oldname and r['capacity_percent']=='30')
        for key in ('selected_n','control_n','treatment_n','conversion_control','conversion_treatment'):
            require(a[key]==int(b[key]),'frozen baseline count differs')
        require(abs(a['G']-float(b['G']))<1e-12,'frozen baseline G differs')
    # Direct counts and a separate log formula independently check small aggregates.
    from fractions import Fraction
    for row in policies:
        mask=selected[row['policy']]
        for arm,ns,ys in [(0,'control_n','conversion_control'),(1,'treatment_n','conversion_treatment')]:
            take=mask&(treatment==arm)
            require(int(take.sum())==row[ns] and int(y[take].sum())==row[ys],'joint/direct count mismatch')
        expected=10000*Fraction(k,n)*(Fraction(row['conversion_treatment'],row['treatment_n'])-
                                    Fraction(row['conversion_control'],row['control_n']))
        require(abs(float(expected)-row['G'])<1e-12,'G/Fraction mismatch')
    probs=dict(RESPONSE_MODEL=response[:,0],S_LEARNER=np.where(treatment==1,s[:,1],s[:,0]),
               T_LEARNER=np.where(treatment==1,t[:,1],t[:,0]))
    for row in metrics:
        p=probs[row['model']];mask=np.ones(n,dtype=bool) if row['valid_arm']=='all' else treatment==int(row['valid_arm'])
        p=np.clip(p[mask],np.finfo(float).eps,1-np.finfo(float).eps);yy=y[mask]
        manual=float(-np.mean(yy*np.log(p)+(1-yy)*np.log1p(-p)))
        require(abs(manual-row['factual_logloss'])<1e-12,'logloss formula mismatch')
    diagnostics={name:dict(negative_scores=int((scores[name]<0).sum()),zero_scores=int((scores[name]==0).sum()),
                          unique_scores=len(np.unique(scores[name])),constant_score=bool(np.ptp(scores[name])==0))
                 for name in ('RESPONSE_MODEL','S_LEARNER','T_LEARNER')}
    for name,data in zip(SHARED,[metrics,policies,overlaps]):csv_out(out/name,data)
    dump(out/'evaluation_receipt.json',dict(status='passed',N_valid=n,K=k,fit_constant_rates=rates,
        old_valid_selection_sha256=old_lists,selected_sha256=selected_hashes,diagnostics=diagnostics,
        joint_types=len(joint),joint_counts=joint,bootstrap_shape=list(draws.shape),
        direct_count_G_logloss_checks='passed',test_evaluation=False))


def process_tree_rss(root_pid):
    records=[list(map(int,line.split())) for line in subprocess.check_output(['/bin/ps','-axo','pid=,ppid=,rss='],text=True).splitlines()]
    pids={root_pid}
    while True:
        larger=pids|{pid for pid,parent,rss in records if parent in pids}
        if larger==pids:break
        pids=larger
    return sum(rss*1024 for pid,parent,rss in records if pid in pids)


def swapouts():
    result=subprocess.check_output(['/usr/bin/vm_stat'],text=True)
    match=re.search(r'Swapouts:\s+(\d+)',result)
    require(match is not None,'swap monitoring unavailable')
    return int(match.group(1))


def main(run_id):
    cfg=config();require(run_id==cfg['run_id']=='uplift-valid-01','only frozen E1 run allowed')
    base=ROOT/'.local/e1';base.mkdir(exist_ok=True);out=base/run_id;out.mkdir(exist_ok=False)
    for name in SHARED:require(not (ROOT/'reports'/name).exists(),'shared result already exists')
    method=['config/uplift_baselines.json','docs/uplift_baselines_protocol.md','uplift/models.py',
            'scripts/run_uplift_baselines.py','tests/test_uplift_models.py','requirements.lock.txt']
    history=['reports/targeting/frozen_rules.json','reports/targeting/coverage_comparison.csv',
             'reports/targeting/policy_differences.csv','reports/targeting_test/coverage_comparison.csv',
             'reports/targeting_test/policy_differences.csv','data/manifest.json','data/criteo_split_manifest.json',
             'reports/power_raw_summary.csv','reports/cross_border_cost_review.md']
    frozen={p:sha(ROOT/p) for p in method+history}
    dump(out/'protocol_before_data.json',dict(config=cfg,sha256=frozen))
    start=time.monotonic();samples=[];stages=[];proc=None
    def sample(stage):
        used=sum(p.stat().st_size for p in base.rglob('*') if p.is_file())
        free=shutil.disk_usage(ROOT).free;rss=process_tree_rss(os.getpid())
        result=dict(stage=stage,elapsed_seconds=time.monotonic()-start,local_bytes=used,free_bytes=free,rss_bytes=rss,swapouts=swapouts())
        samples.append(result)
        require(used+256*2**20<=cfg['max_new_bytes'] and free>=cfg['minimum_free_bytes'],'disk budget exceeded')
        require(rss<cfg['stop_process_tree_rss_bytes'],'process-tree RSS approaching 8 GiB')
        if len(samples)>=4:
            last=samples[-4:]
            require(not (rss>6*2**30 and all(a['swapouts']<b['swapouts'] for a,b in zip(last,last[1:]))),'sustained swapping')
        return result
    try:
        sample('before_tests')
        test=subprocess.run([sys.executable,'-m','unittest','tests.test_uplift_models','tests.test_targeting','-v'],
                            cwd=ROOT,stdout=(out/'tests.log').open('x'),stderr=subprocess.STDOUT)
        require(test.returncode==0,'synthetic/impacted regression gate failed')
        for stage in ['cache','pilot',*models.ROLES,'evaluate']:
            began=time.monotonic()
            with (out/(stage+'.log')).open('x') as log:
                proc=subprocess.Popen([sys.executable,__file__,'--worker',stage,'--run-id',run_id],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
                ticks=0
                while proc.poll() is None:
                    state=sample(stage);ticks+=1
                    if ticks%10==1:print(json.dumps(dict(stage=stage,seconds=round(time.monotonic()-began,1),rss_GiB=round(state['rss_bytes']/2**30,3))),flush=True)
                    time.sleep(cfg['monitor_interval_seconds'])
                require(proc.returncode==0,'worker failed: '+stage)
            stages.append(dict(stage=stage,elapsed_seconds=time.monotonic()-began));sample(stage+'_done')
        require(all(sha(ROOT/p)==h for p,h in frozen.items()),'frozen method or historical evidence changed')
        proof=dict(status='passed',run_id=run_id,config=cfg,stage_times=stages,total_seconds=time.monotonic()-start,
                   fingerprints=frozen,resources=samples,peak_sampled_process_tree_rss_bytes=max(s['rss_bytes'] for s in samples),
                   min_sampled_free_bytes=min(s['free_bytes'] for s in samples),new_local_bytes=max(s['local_bytes'] for s in samples),
                   outputs={name:dict(bytes=(out/name).stat().st_size,sha256=sha(out/name)) for name in SHARED},
                   versions=dict(python=sys.version.split()[0],numpy=np.__version__,sklearn=sklearn.__version__,duckdb=duckdb.__version__))
        dump(out/'complete.json',proof)
        for name in SHARED:
            with (out/name).open('rb') as source,(ROOT/'reports'/name).open('xb') as target:shutil.copyfileobj(source,target)
        print(json.dumps(dict(status='passed',run_id=run_id,seconds=proof['total_seconds'],peak_sampled_rss_GiB=proof['peak_sampled_process_tree_rss_bytes']/2**30)),flush=True)
    except BaseException as exc:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        dump(out/'failure.json',dict(status='failed',error=repr(exc),stages=stages,resources=samples,elapsed_seconds=time.monotonic()-start))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',required=True)
    parser.add_argument('--worker',choices=['cache','pilot',*models.ROLES,'evaluate'])
    args=parser.parse_args()
    if args.worker:
        c=config();require(args.run_id==c['run_id'],'worker run mismatch')
        out=ROOT/'.local/e1'/args.run_id
        proof=json.loads((out/'protocol_before_data.json').read_text())
        require(proof['config']==c,'worker frozen config mismatch')
        with threadpool_limits(limits=4):
            if args.worker=='cache':cache_stage(out)
            elif args.worker=='pilot':train_stage(out,'S_LEARNER',pilot=True)
            elif args.worker=='evaluate':evaluation_stage(out)
            else:train_stage(out,args.worker)
    else:main(args.run_id)
