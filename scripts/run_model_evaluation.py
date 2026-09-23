"""MODEL-EVAL-01: load accepted models, score original test, compare frozen policies."""
import argparse
import csv
from fractions import Fraction
import gc
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[name]='4'
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import duckdb
import numpy as np
import sklearn
from threadpoolctl import threadpool_limits, threadpool_info
from scripts.run_uplift_baselines import array, allocate, process_tree_rss, swapouts
from uplift import models
from uplift.evaluate import no_training, rank_scores, capacity_evaluation, qini_curves
from uplift.ingest_criteo import bind_source, CSV_SHA, RECORDS
from uplift.split import row_id, assign, MEMBERSHIP_HEADER
from ingest.ingest_criteo_source import HEADER
from uplift.targeting import require, sha, dump, csv_out
from uplift.targeting_holdout import load_frozen

CONFIG=ROOT/'config/model_evaluation.json'
SHARED=['coverage_comparison.csv','policy_differences.csv','qini_grid.csv','qini_area.csv']


def config():
    c=json.loads(CONFIG.read_text())
    require(c['run_id']=='model-eval-test-01' and c['model_run']=='uplift-valid-01' and
            c['candidate']=='RESPONSE_MODEL' and c['features']==models.FEATURES and c['split']=='test' and
            c['source_id']=='criteo_uplift_v2_1_corrected' and c['outcome']=='conversion', 'frozen identity mismatch')
    require(c['capacities_percent']==[10,20,30,50,100] and c['primary_capacity_percent']==30 and
            c['primary_contrast']=='RESPONSE_MODEL_minus_FROZEN_SIMPLE' and c['bootstrap_seed']==20260924 and
            c['bootstrap_repetitions']==1000 and c['qini_grid_percent']==[0,100,1] and c['threads']==4,
            'frozen comparison mismatch')
    return c


def accepted_models(c):
    folder=ROOT/'.local/e1'/c['model_run']
    proof=json.loads((folder/'complete.json').read_text())
    require(proof['status']=='passed' and proof['run_id']==c['model_run'], 'E1 not accepted')
    require(proof['versions']==dict(python=sys.version.split()[0],numpy=np.__version__,
            sklearn=sklearn.__version__,duckdb=duckdb.__version__), 'accepted model environment changed')
    for name,digest in proof['fingerprints'].items():
        require(sha(ROOT/name)==digest, 'E1 bound evidence changed: '+name)
    for name,meta in proof['outputs'].items():
        require(sha(ROOT/'reports'/name)==meta['sha256']==sha(folder/name), 'E1 published evidence changed')
    receipts={}
    for role in models.ROLES:
        r=json.loads((folder/(role+'_receipt.json')).read_text())
        require(r['status']=='passed' and r['full_valid_reload_equal'] and
                r['model_sha256']==c['model_sha256'][role]==sha(folder/'models'/(role+'.joblib')),
                'accepted model identity mismatch: '+role)
        receipts[role]=r
    return folder,receipts


def extract_test(raw,member,source_sha,output,n,progress=None):
    """Align every logical row; retain test only, never materialize other split features."""
    output.mkdir(exist_ok=False)
    arrays={k:allocate(output/(k+'.npy'),dt,shape) for k,dt,shape in
            [('X','float64',(n,12)),('row_id','S64',(n,)),('t','uint8',(n,)),('y','uint8',(n,))]}
    counts={s:[0,0] for s in ('train','valid','test')};conversions=[0,0]
    logical=hashlib.sha256(MEMBERSHIP_HEADER)
    sequences={s:hashlib.sha256() for s in ('test','0/test','1/test')}
    used=0;scanned=0;began=time.monotonic()
    with raw.open(newline='',encoding='utf-8') as f,gzip.open(member,'rb') as m:
        reader=csv.reader(f,strict=True)
        require(next(reader,None)==HEADER and m.readline()==MEMBERSHIP_HEADER,'header mismatch')
        for ordinal,record in enumerate(reader):
            require(len(record)==16 and record[12] in ('0','1'),'CSV width/treatment mismatch')
            line=m.readline(256);identity=row_id(source_sha,ordinal);split=assign(identity,record[12])
            require(line.decode('ascii').rstrip('\n').split('\t')==[str(ordinal),identity,record[12],split],
                    'logical ordinal/identity/membership mismatch')
            logical.update(line);arm=int(record[12]);counts[split][arm]+=1
            if split=='test':
                require(used<n and record[13] in ('0','1'),'test size/label mismatch')
                arrays['X'][used]=record[:12]
                require(np.isfinite(arrays['X'][used]).all(),'nonfinite test feature')
                arrays['row_id'][used]=identity;arrays['t'][used]=arm;arrays['y'][used]=int(record[13])
                conversions[arm]+=int(record[13]);used+=1
                for key in ('test',record[12]+'/test'):sequences[key].update((identity+'\n').encode())
            scanned+=1
            if progress and scanned%500000==0:progress(scanned,time.monotonic()-began)
        require(not m.read(1) and used==n,'extra membership or incomplete test cache')
    for a in arrays.values():a.flush()
    return dict(scanned_records=scanned,test_n=used,counts=counts,conversions=conversions,
        logical_sha256=logical.hexdigest(),sequence_sha256={s:h.hexdigest() for s,h in sequences.items()},
        elapsed_seconds=time.monotonic()-began,retained_columns=['row_id',*models.FEATURES,'treatment','conversion'],
        physical_other_split_bytes_traversed=True,non_test_features_or_outcomes_converted_or_retained=False)


def cache_stage(out,c):
    raw,_,binding=bind_source(ROOT)
    manifest=json.loads((ROOT/'data/criteo_split_manifest.json').read_text())
    member=ROOT/manifest['membership']['local_relative_path']
    prior=json.loads((member.parent/'validation.json').read_text())
    run=json.loads((member.parent/'run.json').read_text())
    require(prior['status']=='pass' and all(r['pass'] for r in prior['checks']) and
            run['status']=='complete' and run['source_csv_sha256']==CSV_SHA,'split acceptance missing')
    require(not member.is_symlink() and member.resolve().is_relative_to(ROOT/'.local/t31/criteo-split-v1-01/complete') and
            member.stat().st_size==manifest['membership']['compressed_bytes'] and
            sha(member)==manifest['membership']['compressed_sha256'],'membership bytes mismatch')
    protected={str(p):[p.stat().st_size,p.stat().st_mtime_ns] for p in (raw,member)}
    n=next(g['n'] for g in manifest['qc']['groups'] if g['split']=='test' and g['treatment']=='all')
    meta=extract_test(raw,member,CSV_SHA,out/'cache',n,
         lambda rows,s:print(json.dumps(dict(scanned_records=rows,seconds=round(s,1))),flush=True))
    require(meta['scanned_records']==RECORDS and meta['logical_sha256']==manifest['membership']['logical_sha256'],
            'source count/logical membership mismatch')
    for split in ('train','valid','test'):
        for arm in (0,1):
            qc=next(g for g in manifest['qc']['groups'] if g['split']==split and g['treatment']==str(arm))
            require(meta['counts'][split][arm]==qc['n'],'split arm count mismatch')
            if split=='test':require(meta['conversions'][arm]==qc['conversion'],'test label QC mismatch')
    for key,digest in meta['sequence_sha256'].items():
        require(digest==manifest['membership']['sequence_sha256'][key],'test identity sequence mismatch')
    require(all([Path(p).stat().st_size,Path(p).stat().st_mtime_ns]==v for p,v in protected.items()) and
            sha(raw)==CSV_SHA and sha(member)==manifest['membership']['compressed_sha256'],'source bytes changed')
    meta.update(status='passed',source_binding=binding,protected_metadata=protected,source_bytes=raw.stat().st_size,
                membership_compressed_bytes=member.stat().st_size,
                cache_files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in (out/'cache').iterdir()})
    dump(out/'cache_complete.json',meta)


def ordered_digest(records):
    h=hashlib.sha256()
    for identity in records:h.update(bytes(identity)+b'\n')
    return h.hexdigest()


def score_stage(out,c):
    folder,receipts=accepted_models(c);frozen,_=load_frozen()
    require(json.loads((out/'cache_complete.json').read_text())['status']=='passed','test cache incomplete')
    x=array(out/'cache/X.npy');ids=array(out/'cache/row_id.npy');n=len(x)
    pred_dir=out/'predictions';pred_dir.mkdir()
    for role in models.ROLES:
        estimator=models.load_own_model(folder/'models'/(role+'.joblib'),c['model_sha256'][role],folder/'models')
        require(all(estimator.get_params()[k]==v for k,v in models.PARAMETERS.items()) and
                estimator.n_iter_==receipts[role]['n_iter'] and
                estimator.n_features_in_==(13 if role=='S_LEARNER' else 12),'frozen fitted settings changed')
        predicted=allocate(pred_dir/(role+'.npy'),'float64',(n,2 if role=='S_LEARNER' else 1))
        for start in range(0,n,c['batch_size']):
            end=min(n,start+c['batch_size'])
            predicted[start:end]=models.predict_conditions(estimator,role,x[start:end])
        predicted.flush();del predicted,estimator;gc.collect()
        print(json.dumps(dict(scored=role,rows=n)),flush=True)
    response=array(pred_dir/'RESPONSE_MODEL.npy');s=array(pred_dir/'S_LEARNER.npy')
    tc=array(pred_dir/'T_CONTROL.npy');tt=array(pred_dir/'T_TREATMENT.npy')
    scores=dict(RANDOM=np.zeros(n),FROZEN_SIMPLE=models.simple_scores(x,frozen),RESPONSE_MODEL=response[:,0],
                S_LEARNER=s[:,1]-s[:,0],T_LEARNER=tt[:,0]-tc[:,0])
    ranks=rank_scores(scores,ids)
    rank_dir=out/'ranks';rank_dir.mkdir()
    for policy,rank in ranks.items():
        target=allocate(rank_dir/(policy+'.npy'),'int32',(n,));target[:]=rank;target.flush()
    # Compare complete order, not just total counts, with the accepted old test rules.
    old=ROOT/'.local/target02/targeting-test-01'
    proof=json.loads((old/'complete.json').read_text())
    require(proof['status']=='passed' and proof['test_n']==n and
            proof['frozen_rules_sha256']==sha(ROOT/'reports/targeting/frozen_rules.json'),'TARGET-02 proof invalid')
    con=duckdb.connect(str(old/'analysis.duckdb'),read_only=True)
    con.execute("SET threads=4; SET memory_limit='512MB'")
    con.execute('SET temp_directory=?',[str(out/'duckdb_temp')])
    matched={}
    try:
        for policy,col in [('RANDOM','rank_random'),('FROZEN_SIMPLE','rank_response')]:
            query=con.execute('SELECT row_id FROM selected_ranks ORDER BY '+col)
            h=hashlib.sha256();count=0
            while batch:=query.fetchmany(4096):
                for (identity,) in batch:h.update(identity.encode()+b'\n');count+=1
            actual=ordered_digest(ids[np.argsort(ranks[policy])])
            require(count==n and actual==h.hexdigest(),'old complete ranking changed: '+policy)
            matched[policy]=actual
    finally:con.close()
    dump(out/'selection_before_evaluation.json',dict(status='passed',N_test=n,
        actual_treatment_and_conversion_used_in_ranking=False,old_full_rank_identity=matched,
        negative_scores={p:int((scores[p]<0).sum()) for p in models.POLICIES[2:]},
        predictions={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in pred_dir.iterdir()},
        ranks={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in rank_dir.iterdir()},
        created_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),threadpools=threadpool_info()))


def evaluation_stage(out,c):
    require(json.loads((out/'selection_before_evaluation.json').read_text())['status']=='passed','ranking not accepted')
    ranks={p:array(out/'ranks'/(p+'.npy')) for p in models.POLICIES}
    t=array(out/'cache/t.npy');y=array(out/'cache/y.npy');n=len(y)
    rows,diffs,joint=capacity_evaluation(ranks,t,y,c)
    grid,areas=qini_curves(ranks,t,y)
    checks=[]
    def check(name,ok):
        checks.append(dict(check=name,passed=bool(ok)));require(ok,name)
    old=list(csv.DictReader((ROOT/'reports/targeting_test/coverage_comparison.csv').open()))
    exact={}
    for r in rows:
        chosen=ranks[r['policy']]<=r['selected_n']
        counts=[int((chosen&(t==a)).sum()) for a in (0,1)]+[int(y[chosen&(t==a)].sum()) for a in (0,1)]
        fields=['control_n','treatment_n','conversion_control','conversion_treatment']
        key=(r['policy'],r['capacity_percent'])
        check('direct_counts_'+str(key),counts==[r[f] for f in fields])
        require(counts[0]>0 and counts[1]>0,'real selected arm empty')
        value=Fraction(10000*r['selected_n'],n)*(Fraction(counts[3],counts[1])-Fraction(counts[2],counts[0]))
        exact[key]=value;check('Fraction_G_'+str(key),abs(float(value)-r['G'])<1e-12)
        q=next(q for q in grid if q['policy']==key[0] and q['nominal_capacity_percent']==key[1])
        check('capacity_Qini_count_'+str(key),[q[f] for f in fields]==counts)
        if r['policy'] in ('RANDOM','FROZEN_SIMPLE'):
            rule='RANDOM' if r['policy']=='RANDOM' else 'RESPONSE'
            previous=next(o for o in old if o['rule']==rule and int(o['capacity_percent'])==key[1])
            check('old_point_'+str(key),counts==[int(previous[f]) for f in fields] and
                  r['selected_n']==int(previous['selected_n']) and r['G']==float(previous['G']))
    for r in diffs:
        a,b=r['contrast'].split('_minus_');cap=r['capacity_percent']
        check('Fraction_difference_'+r['contrast']+str(cap),abs(float(exact[a,cap]-exact[b,cap])-r['G_difference'])<1e-12)
        if cap==100:check('full_identical_'+r['contrast'],r['G_difference']==r['ci95_low']==r['ci95_high']==0)
    for row in grid:
        if row['control_n']:
            q=Fraction(row['conversion_treatment'])-Fraction(row['conversion_control']*row['treatment_n'],row['control_n'])
            require(abs(float(q)-row['Q'])<1e-9,'independent Qini arithmetic mismatch')
    for area in areas:
        curve=[r for r in grid if r['policy']==area['policy']]
        if all(r['Q_minus_L'] is not None for r in curve):
            # Independent rational accumulation of the published floating-point points.
            value=sum((Fraction(b['selected_n']-a['selected_n'],n))*
                      (Fraction(str(a['Q_minus_L']))+Fraction(str(b['Q_minus_L'])))/2
                      for a,b in zip(curve,curve[1:]))
            check('independent_area_'+area['policy'],abs(float(value)-area['unnormalized_qini_area_approx'])<1e-9)
    for name,data in zip(SHARED,[rows,diffs,grid,areas]):csv_out(out/name,data)
    dump(out/'evaluation_receipt.json',dict(status='passed',checks=checks,N_test=n,joint_types=len(joint),
        bootstrap_repetitions=c['bootstrap_repetitions'],coverage_rows=len(rows),difference_rows=len(diffs),
        grid_rows=len(grid),area_rows=len(areas),test_control_n=int((t==0).sum()),test_treatment_n=int((t==1).sum()),
        test_conversion=int(y.sum()),bootstrap_invalid_total=sum(r['bootstrap_invalid'] for r in rows)))


def main(run_id):
    c=config();require(run_id==c['run_id'],'run mismatch');accepted_models(c);load_frozen()
    base=ROOT/'.local/model_eval';base.mkdir(exist_ok=True);out=base/run_id;out.mkdir(exist_ok=False)
    published=ROOT/'reports/model_evaluation';require(not published.exists(),'refuse published result overwrite')
    method=['config/model_evaluation.json','docs/model_evaluation_protocol.md','uplift/evaluate.py',
            'scripts/run_model_evaluation.py','tests/test_uplift_metrics.py','requirements.lock.txt']
    history=['reports/uplift_model_card.md','reports/uplift_development_metrics.csv','reports/uplift_valid_policy_comparison.csv',
             'reports/uplift_valid_overlaps.csv','reports/targeting/frozen_rules.json','reports/targeting/coverage_comparison.csv',
             'reports/targeting/policy_differences.csv','reports/targeting_test/coverage_comparison.csv',
             'reports/targeting_test/policy_differences.csv','reports/targeting_holdout_review.md',
             'data/criteo_split_manifest.json','data/manifest.json','uplift/models.py','uplift/targeting.py',
             'uplift/targeting_holdout.py','scripts/run_uplift_baselines.py']
    frozen={p:sha(ROOT/p) for p in method+history}
    dump(out/'protocol_before_data.json',dict(config=c,sha256=frozen,
        created_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
    start=time.monotonic();samples=[];stages=[];proc=None
    def sample(stage):
        used=sum(p.stat().st_size for p in base.rglob('*') if p.is_file())
        state=dict(stage=stage,elapsed_seconds=time.monotonic()-start,local_bytes=used,
                   free_bytes=shutil.disk_usage(ROOT).free,rss_bytes=process_tree_rss(os.getpid()),swapouts=swapouts())
        samples.append(state)
        require(used+256*2**20<=c['max_new_bytes'] and state['free_bytes']>=c['minimum_free_bytes'],'disk budget exceeded')
        require(state['rss_bytes']<c['stop_process_tree_rss_bytes'],'process-tree memory budget exceeded')
        if len(samples)>=4:
            last=samples[-4:]
            require(not (state['rss_bytes']>6*2**30 and all(a['swapouts']<b['swapouts'] for a,b in zip(last,last[1:]))),
                    'sustained swapping')
        return state
    try:
        sample('before_tests')
        with (out/'tests.log').open('x') as log:
            r=subprocess.run([sys.executable,'-m','unittest','tests.test_uplift_metrics','-v'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        require(r.returncode==0,'synthetic gate failed')
        for stage in ['cache','score','evaluate']:
            began=time.monotonic()
            with (out/(stage+'.log')).open('x') as log:
                proc=subprocess.Popen([sys.executable,__file__,'--worker',stage,'--run-id',run_id],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
                ticks=0
                while proc.poll() is None:
                    state=sample(stage);ticks+=1
                    if ticks%10==1:print(json.dumps(dict(stage=stage,seconds=round(time.monotonic()-began,1),rss_GiB=round(state['rss_bytes']/2**30,3))),flush=True)
                    time.sleep(c['monitor_interval_seconds'])
                require(proc.returncode==0,'worker failed: '+stage)
            stages.append(dict(stage=stage,elapsed_seconds=time.monotonic()-began));sample(stage+'_done')
        accepted_models(c)
        require(all(sha(ROOT/p)==h for p,h in frozen.items()),'historical evidence or frozen method changed')
        for meta_name,folder in [('cache_complete.json','cache'),('selection_before_evaluation.json','predictions')]:
            meta=json.loads((out/meta_name).read_text())
            files=meta['cache_files'] if folder=='cache' else meta['predictions']
            require(all(sha(out/folder/p)==v['sha256'] for p,v in files.items()),'new artifact changed after acceptance')
        proof=dict(status='passed',task='MODEL-EVAL-01',run_id=run_id,config=c,fingerprints=frozen,
            stage_times=stages,total_seconds=time.monotonic()-start,resources=samples,
            peak_sampled_process_tree_rss_bytes=max(s['rss_bytes'] for s in samples),
            min_sampled_free_bytes=min(s['free_bytes'] for s in samples),new_local_bytes=max(s['local_bytes'] for s in samples),
            outputs={name:dict(bytes=(out/name).stat().st_size,sha256=sha(out/name)) for name in SHARED},
            versions=dict(python=sys.version.split()[0],numpy=np.__version__,sklearn=sklearn.__version__,duckdb=duckdb.__version__),
            training_calls=0,new_independent_test=False)
        dump(out/'complete.json',proof)
        published.mkdir()
        for name in SHARED:
            with (out/name).open('rb') as src,(published/name).open('xb') as dst:shutil.copyfileobj(src,dst)
        print(json.dumps(dict(status='passed',run_id=run_id,seconds=proof['total_seconds'])),flush=True)
    except BaseException as exc:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        dump(out/'failure.json',dict(status='failed',error=repr(exc),stage_times=stages,resources=samples))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',required=True)
    parser.add_argument('--worker',choices=['cache','score','evaluate']);args=parser.parse_args()
    with no_training(),threadpool_limits(limits=4):
        if args.worker:
            c=config();require(args.run_id==c['run_id'],'worker run mismatch')
            out=ROOT/'.local/model_eval'/args.run_id
            proof=json.loads((out/'protocol_before_data.json').read_text())
            require(proof['config']==c and all(sha(ROOT/p)==h for p,h in proof['sha256'].items()),'worker frozen evidence changed')
            {'cache':cache_stage,'score':score_stage,'evaluate':evaluation_stage}[args.worker](out,c)
        else:main(args.run_id)
