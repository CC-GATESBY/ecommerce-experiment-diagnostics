"""One bounded cohort read, 300 immutable-outcome A/A allocations, small outputs."""
import argparse
import csv
from decimal import Decimal
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import re
import resource
import shutil
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import duckdb
import numpy as np
import scipy
from abtest.assign import prepare_keys,assign,PREFIX
from abtest.srm import srm
from abtest.stats import proportions,welch,wilson,ratio_validation

COHORT='rees46-pre-oct01-14-post-oct15-28-v1'
SCOPE='rees46_2019_oct_user5_fedd938409b5f836_20260916_v1'
FINGERPRINTS={'cohort/identity.parquet':'3f2041b1fc9bf879d0f29737be75085830a189ce8ffea871bcad3049bcc36cdd',
              'cohort/values.parquet':'d361a8660b7e8f4bd40bc4bc5b7a54e2bf4c74343990fcf338c7d22d9a266e97'}


def require(ok,message):
    if not ok:raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def write_csv(path,rows):
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with Path(path).open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)


def read_cohort():
    run=ROOT/'.local/t51/cohort-oct-01';complete=run/'complete'
    require(not (run/'staging').exists(),'incomplete cohort')
    receipt=complete/'validation.json';proof=json.loads(receipt.read_text())
    require(proof['status']=='passed' and proof['run_id']=='cohort-oct-01' and proof['cohort_version']==COHORT,'wrong cohort receipt')
    require(all(x['passed'] for x in proof['checks'].values()),'cohort checks failed')
    b=proof['baseline']
    require((b['scope_id'],b['metric_run'],b['fact_run'])==(SCOPE,'metrics-month-01','month-v101-01'),'cohort lineage mismatch')
    require(b['enrolled_users']==84165 and b['post_buyers']==4812 and Decimal(b['post_purchase_amount'])==Decimal('3499563.53')
            and b['amount_status']=='complete_observed' and b['amount_unknown_users']==0,'cohort baseline mismatch')
    protected={str(receipt):sha(receipt)}
    for rel,expected in FINGERPRINTS.items():
        path=complete/rel;meta=proof['outputs'][rel]
        require(path.is_file() and not path.is_symlink() and path.stat().st_size==meta['bytes'] and sha(path)==meta['sha256']==expected,'cohort file fingerprint mismatch')
        protected[str(path)]=expected
    # Identity content is not queried; its fingerprint is checked without exposing user_id.
    c=duckdb.connect(config={'threads':'1','memory_limit':'128MB','autoload_known_extensions':'false','autoinstall_known_extensions':'false'})
    try:
        rows=c.execute("""SELECT cohort_key,post_converted,post_purchase_amount,scope_id,
            post_amount_status,post_amount_bad,post_null_amount_days,post_amount_allowed
            FROM read_parquet(?) ORDER BY cohort_key LIMIT 84166""",[str(complete/'cohort/values.parquet')]).fetchall()
    finally:c.close()
    require(len(rows)==84165,'cohort row bound mismatch')
    require(all(r[3]==SCOPE and r[1] in (0,1) and r[2] is not None and r[2]>=0 and r[4] in ('complete_observed','no_purchases')
                and r[5]==r[6]==0 and r[7] is True for r in rows),'cohort amount/binary quality mismatch')
    keys=prepare_keys([r[0] for r in rows]);converted=np.array([r[1] for r in rows],dtype=np.int8)
    decimals=[r[2] for r in rows]
    require(all(x*100==int(x*100) for x in decimals),'non-cent amount')
    cents=np.array([int(x*100) for x in decimals],dtype=np.int64)
    require(sum(decimals,Decimal(0))==Decimal('3499563.53') and int(cents.sum())==349956353 and int(converted.sum())==4812,'cohort exact totals mismatch')
    require(int(cents.max())*len(cents)<np.iinfo(np.int64).max,'integer sum overflow risk')
    amount=cents.astype(np.float64)/100
    require(np.array_equal(np.rint(amount*100).astype(np.int64),cents),'float cent roundtrip failed')
    error=abs(Decimal(str(amount.sum()))-sum(decimals,Decimal(0)))
    require(error<=Decimal('0.0000001'),'float sum precision exceeded')
    for array in (cents,converted,amount):array.flags.writeable=False
    return keys,converted,cents,amount,protected,dict(rows=len(keys),converted=int(converted.sum()),amount_cents=int(cents.sum()),
           amount_float_sum_error=str(error),cent_roundtrip_exact=True,numpy_bytes=converted.nbytes+cents.nbytes+amount.nbytes)


def summarize(rows):
    output=[]
    for metric in ('post_converted','post_purchase_amount'):
        original=[r for r in rows if r['metric']==metric]
        for selection in ('all_computable_including_srm','srm_pass_only'):
            eligible=[r for r in original if selection=='all_computable_including_srm' or r['srm_flag'] is False]
            valid=[r for r in eligible if r['status']=='ok']
            n=len(valid);significant=[r for r in valid if r['p_value']<.05]
            low,high=wilson(len(significant),n)
            diffs=np.array([r['difference'] for r in valid]);quantiles=np.quantile(diffs,[.025,.5,.975],method='linear') if n else [None]*3
            hist=np.histogram([r['p_value'] for r in valid],bins=[0,.01,.05,.1,.5,1])[0]
            output.append(dict(metric=metric,selection=selection,planned=300,attempted=len(original),
                completed=sum(r['status']!='execution_error' for r in original),selection_runs=len(eligible),valid=n,
                significant=len(significant),positive_significant=sum(r['difference']>0 for r in significant),
                negative_significant=sum(r['difference']<0 for r in significant),false_positive_rate=len(significant)/n if n else None,
                wilson_low=low,wilson_high=high,difference_q025=quantiles[0],difference_median=quantiles[1],difference_q975=quantiles[2],
                zero_covered=sum(r['ci_low']<=0<=r['ci_high'] for r in valid),zero_coverage=sum(r['ci_low']<=0<=r['ci_high'] for r in valid)/n if n else None,
                srm_flags=sum(r['srm_flag'] is True for r in original),failures=sum(r['status']!='ok' for r in original),
                failure_reasons=json.dumps(sorted(set(r['reason'] for r in original if r['status']!='ok'))),
                p_0_001=int(hist[0]),p_001_005=int(hist[1]),p_005_01=int(hist[2]),p_01_05=int(hist[3]),p_05_1=int(hist[4])))
    return output


def main(run_id):
    require(re.fullmatch('[A-Za-z0-9_-]+',run_id) is not None,'invalid run ID')
    folder=ROOT/'.local/t54';folder.mkdir(exist_ok=True);run=folder/run_id;run.mkdir(exist_ok=False)
    stage=run/'staging';stage.mkdir();started=time.monotonic();rows=[];proof={'status':'failed'}
    deps=sum(Path(d.locate_file(f)).stat().st_size for n in ('numpy','scipy') for d in [importlib.metadata.distribution(n)] for f in d.files if Path(d.locate_file(f)).is_file())
    def budget():
        used=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())+deps;free=shutil.disk_usage(ROOT).free
        require(used+1024**2<1024**3 and free>=150*1024**3,'A/A budget exceeded')
        return dict(local_plus_new_dependencies_bytes=used,dependency_bytes=deps,free_bytes=free)
    try:
        before=budget();cfg=json.loads((ROOT/'config/aa.json').read_text())
        expected=dict(version='rees46-aa-method-v1',cohort_run='cohort-oct-01',cohort_version=COHORT,experiment_prefix='rees46-aa-v1-',
            first_experiment=1,last_experiment=300,assignment_prefix=PREFIX.decode(),probability_b=.5,srm_alpha=.001,alpha=.05,
            binary_method='unpooled_wald_z_min_cell_10',amount_method='welch_t',bootstrap_seed=20260921,bootstrap_repeats=6000,
            bootstrap_batches=30,max_users=84165,expected_converted=4812,expected_amount_cents=349956353)
        require(cfg==expected,'unapproved A/A configuration')
        code_files=['config/aa.json','docs/statistical_contract.md','abtest/assign.py','abtest/srm.py','abtest/stats.py','abtest/aa_test.py','tests/test_aa.py']
        frozen={f:sha(ROOT/f) for f in code_files}
        (run/'frozen_config.json').write_text(json.dumps(cfg,indent=2));(run/'frozen_contract.md').write_text((ROOT/'docs/statistical_contract.md').read_text())
        log=io.StringIO();tests=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('tests.test_aa'))
        (run/'tests.log').write_text(log.getvalue());require(tests.wasSuccessful(),'synthetic gate failed')
        ratio=ratio_validation();(stage/'ratio_synthetic.json').write_text(json.dumps(ratio,indent=2))
        keys,converted,cents,amount,protected,input_check=read_cohort();budget()
        outcome_sha=hashlib.sha256(converted.tobytes()+cents.tobytes()).hexdigest();first_mask=None;overlap=None;max_mean_error=0
        allocation_digests={};run_started=time.monotonic()
        for index in range(1,301):
            eid=f'rees46-aa-v1-{index:04d}'
            try:
                mask=assign(keys,eid);n_b=int(mask.sum());n_a=len(keys)-n_b
                qa=srm(n_a,n_b);ka=int(converted[~mask].sum());kb=int(converted[mask].sum())
                ca,cb=int(cents[~mask].sum()),int(cents[mask].sum())
                require(ka+kb==4812 and ca+cb==349956353,'assignment outcome conservation failed')
                binary=proportions(n_a,ka,n_b,kb);money=welch(amount[~mask],amount[mask])
                for n,total,mean in [(n_a,ca,money['mean_A']),(n_b,cb,money['mean_B'])]:
                    if mean is not None:
                        error=abs(Decimal(str(mean))-Decimal(total)/100/n);max_mean_error=max(max_mean_error,float(error))
                        require(error<=Decimal('0.0000000001'),'amount mean precision exceeded')
                for metric,result in [('post_converted',binary),('post_purchase_amount',money)]:
                    rows.append(dict(experiment_id=eid,metric=metric,**result,**qa,business_use='diagnostic_only_srm' if qa['srm_flag'] else 'offline_aa_only',
                                     converted_A=ka,converted_B=kb,amount_cents_A=ca,amount_cents_B=cb))
                allocation_digests[eid]=hashlib.sha256(mask.tobytes()).hexdigest()
                if index==1:first_mask=mask.copy()
                if index==2:
                    table=np.array([[np.sum(~first_mask & ~mask),np.sum(~first_mask & mask)],[np.sum(first_mask & ~mask),np.sum(first_mask & mask)]])
                    overlap=dict(cells=table.tolist(),phi=float(np.corrcoef(first_mask.astype(float),mask.astype(float))[0,1]),
                                 meaning='first_two_IDs_descriptive_only_not_orthogonality_guarantee')
            except Exception as e:
                for metric in ('post_converted','post_purchase_amount'):
                    if not any(r['experiment_id']==eid and r['metric']==metric for r in rows):
                        rows.append(dict(experiment_id=eid,metric=metric,status='execution_error',reason=type(e).__name__+': '+str(e),srm_flag=None))
            if index%25==0:
                budget();print(f'completed {index}/300 IDs; elapsed {time.monotonic()-run_started:.1f}s',flush=True)
        require(len(rows)==600 and len({(r['experiment_id'],r['metric']) for r in rows})==600,'planned results missing')
        # Recheck fixed 0001 only; never choose another example or rerun to improve calibration.
        repeat=assign(keys,'rees46-aa-v1-0001')
        require(np.array_equal(first_mask,repeat),'assignment not reproducible')
        require(outcome_sha==hashlib.sha256(converted.tobytes()+cents.tobytes()).hexdigest(),'outcomes changed')
        summaries=summarize(rows);write_csv(stage/'aa_runs.csv',rows);write_csv(stage/'aa_summary.csv',summaries)
        require(all(sha(p)==h for p,h in protected.items()),'cohort input changed')
        require(all(sha(ROOT/p)==h for p,h in frozen.items()),'method changed during run')
        proof.update(status='passed' if all(r['status']=='ok' for r in rows) else 'completed_with_failures',run_id=run_id,config=cfg,
                     input_check=input_check,protected_hashes=protected,code_sha256=frozen,assignment_digests=allocation_digests,
                     first_two_assignment_overlap=overlap,summary=summaries,ratio_validation=ratio,tests_passed=tests.testsRun,
                     amount_mean_max_error=max_mean_error,outcome_sha256=outcome_sha,read_once=True,run_seconds=round(time.monotonic()-run_started,3),
                     total_seconds=round(time.monotonic()-started,3),resources_before=before,resources_after=budget(),
                     process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                     versions=dict(python=sys.version.split()[0],numpy=np.__version__,scipy=scipy.__version__,duckdb=duckdb.__version__))
        (stage/'validation.json').write_text(json.dumps(proof,indent=2,allow_nan=False))
        stage.rename(run/'complete');print(json.dumps({'status':proof['status'],'summary':summaries,'ratio':ratio,'seconds':proof['total_seconds']},allow_nan=False))
    except Exception as e:
        if rows:write_csv(run/'partial_runs.csv',rows)
        (run/'failure.json').write_text(json.dumps(dict(status='failed',error=type(e).__name__+': '+str(e)),indent=2));raise


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);main(p.parse_args().run_id)
