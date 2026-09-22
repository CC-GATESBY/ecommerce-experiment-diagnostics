"""TARGET-01: fixed train-only bins, equal-capacity policies, joint validation bootstrap."""
import argparse
import csv
from fractions import Fraction
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import time

import duckdb
import numpy as np

from abtest.stats import proportions
from uplift.ingest_criteo import bind_source, CSV_SHA, RECORDS
from uplift.split import row_id, assign, MEMBERSHIP_HEADER
from ingest.ingest_criteo_source import HEADER

ROOT = Path(__file__).resolve().parents[1]
RULES = ['RANDOM', 'RESPONSE', 'INCREMENTAL']
CAPS = [10, 20, 30, 50, 100]


def require(ok, why):
    if not ok:
        raise ValueError(why)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def dump(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.write('\n')


def csv_out(path, data):
    fields = list(dict.fromkeys(k for r in data for k in r))
    with Path(path).open('x', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        w.writerows(data)


def small(c, sql, params=None, cap=100):
    cur = c.execute(sql, params or [])
    names = [r[0] for r in cur.description]
    vals = cur.fetchmany(cap+1)
    require(len(vals) <= cap, 'small-result cap exceeded')
    return [dict(zip(names, r)) for r in vals]


def aligned_cache(raw_path, member_path, source_sha, output, progress=None):
    """Test feature/outcome strings are traversed physically, never converted or retained."""
    counters = {s: [0, 0] for s in ['train', 'valid', 'test']}
    logical = hashlib.sha256(MEMBERSHIP_HEADER)
    start = time.monotonic()
    with Path(raw_path).open(newline='', encoding='utf-8') as f, gzip.open(member_path, 'rb') as m, Path(output).open('x', newline='') as target:
        reader = csv.reader(f, strict=True)
        require(next(reader, None) == HEADER and m.readline() == MEMBERSHIP_HEADER, 'header mismatch')
        w = csv.writer(target, delimiter='\t', lineterminator='\n')
        w.writerow(['row_id','split','f0','f1','treatment','conversion'])
        count = 0
        for ordinal, record in enumerate(reader):
            require(len(record) == 16 and record[12] in ('0','1'), 'CSV structure/treatment invalid')
            line = m.readline(256)
            fields = line.decode('ascii').rstrip('\n').split('\t')
            require(len(fields) == 4, 'membership width')
            identity = row_id(source_sha, ordinal)
            split = fields[3]
            require(fields == [str(ordinal), identity, record[12], assign(identity, record[12])], 'membership alignment mismatch')
            logical.update(line)
            counters[split][int(record[12])] += 1
            if split != 'test':
                require(all(math.isfinite(float(v)) for v in record[:2]) and record[13] in ('0','1'), 'train/valid feature or outcome invalid')
                w.writerow([identity, split, record[0], record[1], record[12], record[13]])
            count += 1
            if progress and count % 500000 == 0:
                target.flush()
                progress(count, time.monotonic()-start)
        require(count > 0 and not m.read(1), 'empty source or extra membership')
    return dict(records=count, counts=counters, logical_sha256=logical.hexdigest(), elapsed_seconds=time.monotonic()-start,
                physical_test_bytes_traversed=True, test_features_or_outcomes_retained=False)


def cuts(values, minimum, maximum):
    return sorted({float(v) for v in values if minimum < v < maximum})


def bin_sql(feature, boundaries):
    terms = ' '.join(f'WHEN {feature}<={v!r} THEN {i}' for i, v in enumerate(boundaries))
    return f'(CASE {terms} ELSE {len(boundaries)} END)' if boundaries else '0'


def group_sql(boundaries):
    return f'({bin_sql("f0", boundaries["f0"])}*{len(boundaries["f1"])+1}+{bin_sql("f1", boundaries["f1"])})'


def train_rules(c, cfg):
    boundaries = {}
    for feature in cfg['features']:
        q, lo, hi = c.execute(f"SELECT quantile_cont({feature},[.25,.5,.75]),MIN({feature}),MAX({feature}) FROM cache WHERE split='train'").fetchone()
        require(lo is not None and math.isfinite(lo) and math.isfinite(hi), 'empty or invalid train features')
        boundaries[feature] = cuts(q, lo, hi)
    expression = group_sql(boundaries)
    c.execute("CREATE TEMP VIEW train_grouped AS SELECT *,"+expression+" AS group_id FROM cache WHERE split='train'")
    total = c.execute('SELECT COUNT(*) FILTER(WHERE treatment=0),COUNT(*) FILTER(WHERE treatment=1),SUM(conversion) FILTER(WHERE treatment=0),SUM(conversion) FILTER(WHERE treatment=1) FROM train_grouped').fetchone()
    require(total[0] > 0 and total[1] > 0, 'train arm empty')
    global_p0 = Fraction(total[2], total[0])
    global_delta = Fraction(total[3], total[1])-global_p0
    measured = {r['group_id']: r for r in small(c, 'SELECT group_id,COUNT(*) FILTER(WHERE treatment=0) AS n_control,COUNT(*) FILTER(WHERE treatment=1) AS n_treatment,COALESCE(SUM(conversion) FILTER(WHERE treatment=0),0) AS conversion_control,COALESCE(SUM(conversion) FILTER(WHERE treatment=1),0) AS conversion_treatment FROM train_grouped GROUP BY 1 ORDER BY 1', cap=16)}
    groups, exact = [], []
    for g in range((len(boundaries['f0'])+1)*(len(boundaries['f1'])+1)):
        r = measured.get(g, dict(group_id=g,n_control=0,n_treatment=0,conversion_control=0,conversion_treatment=0))
        fallback = min(r['n_control'], r['n_treatment']) < cfg['min_train_arm_n']
        p0 = None if r['n_control'] == 0 else Fraction(r['conversion_control'], r['n_control'])
        p1 = None if r['n_treatment'] == 0 else Fraction(r['conversion_treatment'], r['n_treatment'])
        delta = p1-p0 if p0 is not None and p1 is not None else None
        score0, scored = (global_p0,global_delta) if fallback else (p0,delta)
        groups.append(dict(r,p0_train=None if p0 is None else float(p0),p1_train=None if p1 is None else float(p1),delta_train=None if delta is None else float(delta),
                           fallback=fallback, fallback_reason='unobserved_train_combination' if g not in measured else ('low_train_arm_support' if fallback else 'supported'),
                           response_score=float(score0),incremental_score=float(scored),response_score_fraction=str(score0),incremental_score_fraction=str(scored)))
        exact.append((score0,scored))
    for side, name in [(0,'response_rank'),(1,'incremental_rank')]:
        order = sorted({s[side] for s in exact}, reverse=True)
        for r, score in zip(groups, exact):
            r[name] = order.index(score[side])+1
    return dict(version=cfg['version'], boundaries=boundaries, groups=groups, train_totals=list(total),
                global_p0=float(global_p0),global_delta=float(global_delta), features=cfg['features'], outcome='conversion',
                capacities_percent=cfg['capacities_percent'],primary_contrast=cfg['primary_contrast'],tie_break=cfg['tie_break'],
                quantile_algorithm=cfg['quantile_algorithm'],bin_boundary=cfg['bin_boundary'])


def rank_valid(c, frozen):
    c.execute('CREATE TEMP TABLE scores(group_id INT,response_rank INT,incremental_rank INT,fallback BOOLEAN)')
    c.executemany('INSERT INTO scores VALUES (?,?,?,?)', [(g['group_id'],g['response_rank'],g['incremental_rank'],g['fallback']) for g in frozen['groups']])
    # None of treatment, conversion or validation-derived rates enters any ORDER BY.
    c.execute("""CREATE TABLE ranked AS WITH v AS (
        SELECT row_id,treatment,conversion,"""+group_sql(frozen['boundaries'])+""" AS group_id,
               sha256('target-v1|20260921|'||row_id) AS tie_hash
        FROM cache WHERE split='valid'
    ) SELECT row_id,treatment,conversion,group_id,fallback,
       ROW_NUMBER() OVER(ORDER BY tie_hash ASC,row_id ASC) AS rank_random,
       ROW_NUMBER() OVER(ORDER BY response_rank ASC,tie_hash ASC,row_id ASC) AS rank_response,
       ROW_NUMBER() OVER(ORDER BY incremental_rank ASC,tie_hash ASC,row_id ASC) AS rank_incremental
       FROM v JOIN scores USING(group_id)""")
    return c.execute('SELECT COUNT(*) FROM ranked').fetchone()[0]


def joint_table(c, n_valid, cfg):
    terms, specs = [], []
    for i, rule in enumerate(RULES):
        for j, cap in enumerate(CAPS):
            k = cap*n_valid//100
            bit = 5*i+j
            terms.append(f'CASE WHEN rank_{rule.lower()}<={k} THEN {1<<bit} ELSE 0 END')
            specs.append(dict(rule=rule,capacity_percent=cap,selected_n=k,c_actual=k/n_valid,bit=bit))
    c.execute('CREATE TEMP VIEW marked AS SELECT *,('+ '+'.join(terms)+') AS mask FROM ranked')
    joint = small(c,'SELECT treatment,conversion,mask,COUNT(*) AS n FROM marked GROUP BY 1,2,3 ORDER BY 1,2,3',cap=cfg['max_joint_types'])
    return joint, specs


def resample_joint(joint, specs, cfg):
    """A multinomial draw over full joint types is equivalent to record resampling."""
    arms = np.array([r['treatment'] for r in joint])
    ys = np.array([r['conversion'] for r in joint])
    counts = np.array([r['n'] for r in joint],dtype=np.int64)
    membership = np.array([[(r['mask'] >> s['bit']) & 1 for s in specs] for r in joint],dtype=np.int64)
    capacities = np.array([s['c_actual'] for s in specs])
    def estimate(weights):
        ns, events = [], []
        for arm in (0,1):
            w = weights*(arms == arm)
            ns.append(w @ membership)
            events.append((w*ys) @ membership)
        ns, events = np.asarray(ns),np.asarray(events)
        rates = np.divide(events,ns,out=np.full(ns.shape,np.nan),where=ns>0)
        delta = rates[1]-rates[0]
        return ns, events, rates, delta, 10000*capacities*delta
    point = estimate(counts)
    rng = np.random.Generator(np.random.PCG64(cfg['bootstrap_seed']))
    draws = np.empty((cfg['bootstrap_repetitions'],len(specs)),dtype=float)
    for b in range(len(draws)):
        w = np.zeros_like(counts)
        for arm in (0,1):
            ix = np.flatnonzero(arms == arm)
            n = int(counts[ix].sum())
            if n:
                w[ix] = rng.multinomial(n,counts[ix]/n)
        draws[b] = estimate(w)[-1]
    return point, draws, membership


def interval(values):
    v = values[np.isfinite(values)]
    lo,hi = np.quantile(v,[.025,.975],method='linear') if len(v) else [None,None]
    return dict(ci95_low=None if lo is None else float(lo),ci95_high=None if hi is None else float(hi),
                bootstrap_valid=len(v),bootstrap_invalid=len(values)-len(v),invalid_reason='zero_selected_arm_denominator' if len(v)<len(values) else '')


def evaluate(joint,specs,cfg):
    (ns,ys,rates,delta,gs), draws, membership = resample_joint(joint,specs,cfg)
    coverage=[]
    for j,s in enumerate(specs):
        sparse = min(ys[0,j],ns[0,j]-ys[0,j],ys[1,j],ns[1,j]-ys[1,j]) < cfg['sparse_min_success_or_failure_per_arm']
        finite = math.isfinite(gs[j])
        summary = interval(draws[:,j])
        require(int(ns[:,j].sum()) == s['selected_n'],'equal capacity count mismatch')
        coverage.append(dict(s,control_n=int(ns[0,j]),treatment_n=int(ns[1,j]),conversion_control=int(ys[0,j]),conversion_treatment=int(ys[1,j]),
            p0_S=float(rates[0,j]) if math.isfinite(rates[0,j]) else None,p1_S=float(rates[1,j]) if math.isfinite(rates[1,j]) else None,
            delta_S=float(delta[j]) if finite else None,delta_pp=float(100*delta[j]) if finite else None,
            difference_per_10k_selected=float(10000*delta[j]) if finite else None,G=float(gs[j]) if finite else None,
            treatment_share=float(ns[1,j]/s['selected_n']) if s['selected_n'] else None,
            interval_status='zero_denominator' if not finite else ('sparse_not_for_strong_inference' if sparse else 'descriptive_conditional_bootstrap'),
            **summary))
    differences=[]
    for cap in CAPS:
        for first,second in [('INCREMENTAL','RANDOM'),('RESPONSE','RANDOM'),('INCREMENTAL','RESPONSE')]:
            a,b=[next(i for i,s in enumerate(specs) if s['rule']==rule and s['capacity_percent']==cap) for rule in (first,second)]
            overlap=sum(r['n'] for i,r in enumerate(joint) if membership[i,a] and membership[i,b])
            valid=math.isfinite(gs[a]) and math.isfinite(gs[b])
            differences.append(dict(capacity_percent=cap,contrast=first+'_minus_'+second,role='primary' if cap==30 and first=='INCREMENTAL' and second=='RANDOM' else 'auxiliary',
                selected_n=specs[a]['selected_n'],overlap_n=overlap,union_n=2*specs[a]['selected_n']-overlap,
                G_difference=float(gs[a]-gs[b]) if valid else None,
                interval_status='zero_denominator' if not valid else ('sparse_not_for_strong_inference' if any(coverage[i]['interval_status']=='sparse_not_for_strong_inference' for i in [a,b]) else 'descriptive_paired_bootstrap'),
                **interval(draws[:,a]-draws[:,b])))
            if cap==100:
                require(np.array_equal(membership[:,a],membership[:,b]) and (not valid or np.all(draws[:,a]-draws[:,b]==0)),'100 percent mismatch')
    return coverage,differences,draws


def stratum_report(c,frozen):
    data=[]
    for split,table in [('train','train_grouped'),('valid','ranked')]:
        obs=small(c,'SELECT group_id,COUNT(*) FILTER(WHERE treatment=0) AS n_control,COUNT(*) FILTER(WHERE treatment=1) AS n_treatment,COALESCE(SUM(conversion) FILTER(WHERE treatment=0),0) AS conversion_control,COALESCE(SUM(conversion) FILTER(WHERE treatment=1),0) AS conversion_treatment FROM '+table+' GROUP BY 1 ORDER BY 1',cap=16)
        by={r['group_id']:r for r in obs}
        for g in frozen['groups']:
            r=by.get(g['group_id'],dict(group_id=g['group_id'],n_control=0,n_treatment=0,conversion_control=0,conversion_treatment=0))
            n0,n1,y0,y1=[int(r[k]) for k in ['n_control','n_treatment','conversion_control','conversion_treatment']]
            st=proportions(n0,y0,n1,y1)
            p0=y0/n0 if n0 else None;p1=y1/n1 if n1 else None
            data.append(dict(split=split,**r,p0=p0,p1=p1,delta=None if p0 is None or p1 is None else p1-p0,
                             treatment_share=n1/(n0+n1) if n0+n1 else None,ci95_low=st['ci_low'],ci95_high=st['ci_high'],
                             interval_status=st['status'],method='descriptive_unpooled_normal_min_cell_10_not_simultaneous',
                             fallback=g['fallback'],fallback_reason=g['fallback_reason'],response_rank=g['response_rank'],incremental_rank=g['incremental_rank']))
    return data


def execute(run_id, resume_cache=False):
    cfg=json.loads((ROOT/'config/targeting.json').read_text())
    require(cfg['features']==['f0','f1'] and cfg['outcome']=='conversion' and cfg['capacities_percent']==CAPS,'frozen scope mismatch')
    require(run_id and all(c.isalnum() or c in '-_' for c in run_id),'unsafe run ID')
    base=ROOT/'.local/target01';out=base/run_id
    if not resume_cache:
        out.mkdir(parents=True,exist_ok=False)
    else:
        require(out.is_dir() and (out/'cache_complete.json').exists() and not (out/'complete.json').exists(),'no resumable cache')
        require(not (out/'frozen_rules.json').exists(),'rules already frozen; do not rerun valid evaluation')
    start=time.monotonic();checks=[];peak_bytes=0;min_free=shutil.disk_usage(ROOT).free;c=None
    def budget():
        nonlocal peak_bytes,min_free
        used=sum(p.stat().st_size for p in base.rglob('*') if p.is_file());free=shutil.disk_usage(ROOT).free
        peak_bytes=max(peak_bytes,used);min_free=min(min_free,free)
        require(used<=cfg['max_new_bytes'] and free>=cfg['minimum_free_bytes'],'TARGET-01 resource budget exceeded')
    def check(name,want,actual):
        checks.append(dict(check=name,expected=want,actual=actual,passed=want==actual));require(want==actual,name)
    def progress(n,seconds):
        budget();print(json.dumps(dict(stage='align_source_membership',records=n,elapsed_seconds=round(seconds,1))),flush=True)
    try:
        budget()
        policy=ROOT/'config/targeting.json';policy_sha=sha(policy)
        code_sha={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'tests/test_targeting.py',policy]}
        if not resume_cache:dump(out/'policy_before_data.json',dict(config=cfg,sha256=policy_sha,code_sha256=code_sha))
        else:check('same_cache_policy',json.loads((out/'policy_before_data.json').read_text())['sha256'],policy_sha)
        raw,entry,binding=bind_source(ROOT)
        manifest=json.loads((ROOT/'data/criteo_split_manifest.json').read_text());member=ROOT/manifest['membership']['local_relative_path']
        receipt=json.loads((member.parent/'validation.json').read_text());proof=json.loads((member.parent/'run.json').read_text())
        require(member.resolve().is_relative_to(ROOT/'.local/t31/criteo-split-v1-01/complete') and not member.is_symlink(),'membership locator mismatch')
        require(receipt['status']=='pass' and all(x['pass'] for x in receipt['checks']) and proof['status']=='complete' and proof['source_csv_sha256']==CSV_SHA and manifest['split_rule']['seed']==20260917,'split acceptance mismatch')
        check('membership_bytes',manifest['membership']['compressed_bytes'],member.stat().st_size)
        check('membership_sha',manifest['membership']['compressed_sha256'],sha(member))
        protected={str(p):[p.stat().st_size,p.stat().st_mtime_ns] for p in [raw,member]}
        if not resume_cache:
            print(json.dumps(dict(stage='identities_passed',source_bytes=raw.stat().st_size,membership_bytes=member.stat().st_size)),flush=True)
            cache_meta=aligned_cache(raw,member,CSV_SHA,out/'train_valid.tsv',progress)
            check('source_records',RECORDS,cache_meta['records'])
            check('logical_membership_sha',manifest['membership']['logical_sha256'],cache_meta['logical_sha256'])
            for split in ['train','valid','test']:
                for arm in range(2):
                    n=next(r['n'] for r in manifest['qc']['groups'] if r['split']==split and r['treatment']==str(arm))
                    check('membership_n_'+split+'_'+str(arm),n,cache_meta['counts'][split][arm])
            cache_meta.update(cache_sha256=sha(out/'train_valid.tsv'),policy_sha256=policy_sha)
            dump(out/'cache_complete.json',cache_meta)
        else:
            cache_meta=json.loads((out/'cache_complete.json').read_text())
            check('cache_hash',cache_meta['cache_sha256'],sha(out/'train_valid.tsv'))
        budget()
        db=out/'analysis.duckdb'
        require(not db.exists(),'existing analysis DB; refuse overwrite')
        c=duckdb.connect(str(db));c.execute("SET threads=4; SET memory_limit='2GB'; SET TimeZone='UTC'; SET max_temp_directory_size='3GB'")
        c.execute('SET temp_directory=?',[str(out/'temp')])
        c.execute("CREATE TABLE cache AS SELECT * FROM read_csv(?,delim='\t',header=true,columns={'row_id':'VARCHAR','split':'VARCHAR','f0':'DOUBLE','f1':'DOUBLE','treatment':'TINYINT','conversion':'TINYINT'},strict_mode=true)",[str(out/'train_valid.tsv')])
        for r in small(c,'SELECT split,treatment,COUNT(*) AS n FROM cache GROUP BY 1,2',cap=4):check('cache_n_'+r['split']+'_'+str(r['treatment']),cache_meta['counts'][r['split']][r['treatment']],r['n'])
        frozen=train_rules(c,cfg)
        frozen.update(policy_sha256=policy_sha,code_sha256=code_sha,source_sha256=CSV_SHA,split_run=manifest['run_id'],frozen_before_valid_effects=True)
        dump(out/'frozen_rules.json',frozen)
        rules_sha=sha(out/'frozen_rules.json')
        print(json.dumps(dict(stage='train_rules_frozen',groups=len(frozen['groups']),rules_sha256=rules_sha)),flush=True)
        n_valid=rank_valid(c,frozen)
        check('valid_rows',sum(cache_meta['counts']['valid']),n_valid)
        check('valid_id_uniqueness',n_valid,c.execute('SELECT COUNT(DISTINCT row_id) FROM ranked').fetchone()[0])
        for arm in (0,1):
            want=next(r for r in manifest['qc']['groups'] if r['split']=='valid' and r['treatment']==str(arm))
            check('valid_conversion_'+str(arm),want['conversion'],c.execute('SELECT SUM(conversion) FROM ranked WHERE treatment=?',[arm]).fetchone()[0])
        budget()
        joint,specs=joint_table(c,n_valid,cfg)
        coverage,diffs,draws=evaluate(joint,specs,cfg)
        strata=stratum_report(c,frozen)
        for r in coverage:
            check('capacity_'+r['rule']+'_'+str(r['capacity_percent']),r['capacity_percent']*n_valid//100,r['control_n']+r['treatment_n'])
            fallback=c.execute('SELECT COUNT(*) FROM ranked WHERE fallback AND rank_'+r['rule'].lower()+'<=?',[r['selected_n']]).fetchone()[0]
            r['fallback_selected_n']=fallback
        for rule in RULES:
            col='rank_'+rule.lower()
            counts=c.execute('SELECT MIN('+col+'),MAX('+col+'),COUNT(DISTINCT '+col+') FROM ranked').fetchone()
            check('complete_rank_and_nested_'+rule,[1,n_valid,n_valid],list(counts))
        for r in diffs:
            if r['capacity_percent']==100:check('full_coverage_difference_'+r['contrast'],[0.0,0.0,0.0],[r['G_difference'],r['ci95_low'],r['ci95_high']])
        check('rules_unchanged_after_valid',rules_sha,sha(out/'frozen_rules.json'))
        check('inputs_stat_unchanged',protected,{str(p):[p.stat().st_size,p.stat().st_mtime_ns] for p in [raw,member]})
        check('raw_sha_after',CSV_SHA,sha(raw));check('membership_sha_after',manifest['membership']['compressed_sha256'],sha(member))
        check('policy_unchanged',policy_sha,sha(policy))
        csv_out(out/'stratum_summary.csv',strata);csv_out(out/'coverage_comparison.csv',coverage);csv_out(out/'policy_differences.csv',diffs)
        dump(out/'joint_types_private.json',joint)
        c.execute('CHECKPOINT');c.close();c=None;budget()
        dump(out/'complete.json',dict(status='passed',run_id=run_id,version=cfg['version'],checks=checks,code_sha256=code_sha,source_binding=binding,
             frozen_rules_sha256=rules_sha,cache=cache_meta,valid_n=n_valid,joint_types=len(joint),test_analysis=False,
             elapsed_seconds=round(time.monotonic()-start,3),sampled_peak_new_bytes=peak_bytes,minimum_free_bytes=min_free,
             peak_memory='not_measured',versions=dict(duckdb=duckdb.__version__,numpy=np.__version__)))
        print(json.dumps(dict(status='passed',joint_types=len(joint),elapsed_seconds=round(time.monotonic()-start,1))),flush=True)
    except BaseException as exc:
        dump(out/('failed-'+str(time.time_ns())+'.json'),dict(status='failed',error=type(exc).__name__+': '+str(exc),checks=checks));raise
    finally:
        if c is not None:c.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',required=True);parser.add_argument('--resume-cache',action='store_true');a=parser.parse_args()
    execute(a.run_id,a.resume_cache)
