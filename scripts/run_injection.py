"""One bounded binary-only cohort read and one fixed simulation pair."""
import argparse
import csv
from datetime import date, timedelta
from fractions import Fraction
import hashlib
import io
import json
import math
from pathlib import Path
import re
import shutil
from statistics import NormalDist
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import duckdb
import numpy as np
import scipy
from abtest.inject import simulate, synthetic_mc, EXPERIMENT_ID, PREFIX, SEED

COHORT = 'rees46-pre-oct01-14-post-oct15-28-v1'
SCOPE = 'rees46_2019_oct_user5_fedd938409b5f836_20260916_v1'
VALUES_SHA = 'd361a8660b7e8f4bd40bc4bc5b7a54e2bf4c74343990fcf338c7d22d9a266e97'
FROZEN_FILES = ['config/injection.json','docs/injection_contract.md','abtest/inject.py',
                'scripts/run_injection.py','tests/test_inject.py','abtest/assign.py',
                'abtest/srm.py','abtest/stats.py','docs/statistical_contract.md','requirements.lock.txt']


def require(ok, message):
    if not ok:raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def load_binary_cohort():
    folder = ROOT/'.local/t51/cohort-oct-01/complete'
    receipt = folder/'validation.json'; proof = json.loads(receipt.read_text())
    require(not (folder.parent/'staging').exists(), 'cohort incomplete')
    require(proof['status']=='passed' and proof['run_id']=='cohort-oct-01' and proof['cohort_version']==COHORT, 'cohort receipt identity mismatch')
    require(proof['checks'] and all(x['passed'] is True for x in proof['checks'].values()), 'failed cohort checks')
    b = proof['baseline']
    require((b['scope_id'],b['analysis_scope'],b['metric_run'],b['fact_run']) ==
            (SCOPE,'rees46_oct_user5_analysis_v1','metrics-month-01','month-v101-01'), 'cohort lineage mismatch')
    require((b['pre_start'],b['pre_end_exclusive'],b['post_start'],b['post_end_exclusive']) ==
            ('2019-10-01','2019-10-15','2019-10-15','2019-10-29'), 'cohort windows mismatch')
    require(b['enrolled_users']==84165 and b['post_buyers']==4812, 'cohort baseline mismatch')
    expected_dates = {(date(2019,10,1)+timedelta(days=i)).isoformat() for i in range(28)}
    gates = proof['gates']
    require(len(gates)==28 and {g['utc_date'] for g in gates}==expected_dates and
            all(g['count_allowed'] is True and g['scope_id']==SCOPE and g['source_run']=='month-v101-01'
                for g in gates), 'cohort count/date quality not allowed')
    path = folder/'cohort/values.parquet'; meta = proof['outputs']['cohort/values.parquet']
    require(path.is_file() and not path.is_symlink() and path.stat().st_size==meta['bytes'] and
            sha(path)==meta['sha256']==VALUES_SHA, 'cohort values fingerprint mismatch')
    protected = {str(path):VALUES_SHA, str(receipt):sha(receipt)}
    identity = folder/'cohort/identity.parquet'; identity_meta = proof['outputs']['cohort/identity.parquet']
    require(identity.is_file() and not identity.is_symlink() and identity.stat().st_size==identity_meta['bytes'] and
            sha(identity)==identity_meta['sha256'], 'identity fingerprint mismatch')
    protected[str(identity)] = identity_meta['sha256']  # No identity columns are queried.
    con = duckdb.connect(config={'threads':'1','memory_limit':'128MB','autoload_known_extensions':'false','autoinstall_known_extensions':'false'})
    try:
        rows = con.execute('SELECT cohort_key, post_converted, scope_id FROM read_parquet(?) ORDER BY cohort_key LIMIT 84166', [str(path)]).fetchall()
    finally:con.close()
    require(len(rows)==84165 and all(r[1] in (0,1) and r[2]==SCOPE for r in rows), 'row/scope/binary domain mismatch')
    keys = [r[0] for r in rows]; y0 = np.array([r[1] for r in rows], dtype=np.int8)
    require(int(y0.sum())==4812, 'original binary sum mismatch')
    y0.flags.writeable = False
    return keys, y0, protected


def independent_summary_checks(rows):
    """Counts -> Fraction and standard-library NormalDist/erfc, not the estimator."""
    checks = {}
    for r in rows:
        a = Fraction(r['buyers_A'],r['n_A']); b = Fraction(r['buyers_B'],r['n_B'])
        difference = b-a; tau = Fraction(r['K'],r['N'])
        se = math.sqrt(float(a*(1-a)/r['n_A']+b*(1-b)/r['n_B']))
        half = NormalDist().inv_cdf(.975)*se
        expected = dict(mean_A=float(a),mean_B=float(b),difference=float(difference),se=se,
                        ci_low=float(difference)-half,ci_high=float(difference)+half,
                        p_value=math.erfc(abs(float(difference))/se/math.sqrt(2)),
                        tau=float(tau),estimation_error=float(difference-tau))
        checks[r['scenario']] = {k:dict(expected=v,actual=r[k],passed=math.isclose(v,r[k],rel_tol=1e-12,abs_tol=1e-15)) for k,v in expected.items()}
    return checks


def main(run_id):
    require(re.fullmatch(r'[A-Za-z0-9_-]+',run_id) is not None, 'invalid run ID')
    base = ROOT/'.local/t55'; base.mkdir(exist_ok=True)
    run = base/run_id; run.mkdir(exist_ok=False); stage = run/'staging'; stage.mkdir()
    start = time.monotonic(); proof = dict(status='failed',run_id=run_id)
    def budget():
        local = sum(p.stat().st_size for p in base.rglob('*') if p.is_file())
        # Reserve 16 MiB for submitted code/docs and final receipt, far above their bounded size.
        free = shutil.disk_usage(ROOT).free
        require(local+16*2**20 < 512*2**20 and free >= 150*2**30, 'simulation resource budget exceeded')
        return dict(local_bytes=local,reserved_shared_bytes=16*2**20,free_bytes=free,peak_memory='not_measured')
    try:
        before = budget()
        expected = dict(version='rees46-injection-v1',cohort_run='cohort-oct-01',cohort_version=COHORT,
            experiment_id=EXPERIMENT_ID,assignment_prefix=PREFIX.decode(),rng='PCG64',seed=SEED,
            scenario_relative_lifts={'S0':'0','S1':'0.10'},sort='cohort_key_ASC',probability_B=.5,
            srm_alpha=.001,alpha=.05,binary_method='unpooled_wald_z_min_cell_10',expected_users=84165,
            expected_Y0_sum=4812,synthetic_mc_seed=20260922,synthetic_mc_repeats=500,synthetic_mc_max_abs_z=6)
        config = json.loads((ROOT/'config/injection.json').read_text())
        require(config==expected, 'unapproved simulation configuration')
        frozen = {f:sha(ROOT/f) for f in FROZEN_FILES}
        (run/'frozen_config.json').write_text(json.dumps(config,indent=2))
        log = io.StringIO()
        suite = unittest.defaultTestLoader.loadTestsFromNames(['tests.test_inject','tests.test_aa.AssignmentTests',
                                                            'tests.test_aa.StatisticsTests.test_binary_literal_formula_and_units'])
        tests = unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
        (run/'tests.log').write_text(log.getvalue()); require(tests.wasSuccessful(), 'synthetic gate failed')
        mc = synthetic_mc(); require(mc['passed'], 'synthetic binomial check failed')
        print('Synthetic and impacted regressions passed; reading one bounded binary cohort projection.',flush=True)
        keys,y0,protected = load_binary_cohort()
        before_y = hashlib.sha256(y0.tobytes()).hexdigest()
        simulation_start = time.monotonic()
        potentials,rows,mask,identity = simulate(keys,y0)
        simulation_seconds = time.monotonic()-simulation_start
        require(identity['status']=='passed', 'scenario increment identity failed')
        require(before_y==hashlib.sha256(y0.tobytes()).hexdigest() and not y0.flags.writeable, 'original Y0 modified')
        require(np.array_equal(potentials['outcomes'][0][0],potentials['y0']) and
                (potentials['outcomes'][1][0]>=potentials['y0']).all(), 'potential outcome monotonicity failed')
        require(all(r['status']=='ok' for r in rows), 'statistics not estimable; retain failure evidence')
        checks = independent_summary_checks(rows)
        require(all(c['passed'] for cs in checks.values() for c in cs.values()), 'independent formula mismatch')
        with (stage/'effect_injection_results.csv').open('x',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n'); writer.writeheader(); writer.writerows(rows)
        # One local synthetic-outcome artifact, explicitly outside business tables.
        np.savez_compressed(stage/'simulated_potential_outcomes_NOT_BUSINESS.npz',
            cohort_key=np.asarray(potentials['keys'],dtype='S64'),Y0=potentials['y0'],
            U=potentials['u'],Y1_S1=potentials['outcomes'][1][0],assigned_B=mask)
        require(all(sha(p)==h for p,h in protected.items()), 'original cohort evidence changed')
        require(all(sha(ROOT/p)==h for p,h in frozen.items()), 'frozen method changed')
        proof.update(status='passed',config=config,cohort_version=COHORT,read_columns=['cohort_key','post_converted','scope_id'],
            input_check={'N':len(y0),'Y0_sum':int(y0.sum()),'Y0_unchanged':True,'query_count':1},
            identity=identity,independent_checks=checks,synthetic_mc=mc,tests_passed=tests.testsRun,
            protected_hashes=protected,code_sha256=frozen,
            assignment_sha256=hashlib.sha256(mask.tobytes()).hexdigest(),
            U_sha256=hashlib.sha256(potentials['u'].tobytes()).hexdigest(),
            Y0_sorted_sha256=hashlib.sha256(potentials['y0'].tobytes()).hexdigest(),
            Y1_S1_sha256=hashlib.sha256(potentials['outcomes'][1][0].tobytes()).hexdigest(),
            outputs={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in stage.iterdir()},
            resources_before=before,resources_after=budget(),simulation_seconds=simulation_seconds,
            total_seconds=time.monotonic()-start,versions=dict(python=sys.version.split()[0],numpy=np.__version__,scipy=scipy.__version__,duckdb=duckdb.__version__))
        (stage/'validation.json').write_text(json.dumps(proof,indent=2,allow_nan=False))
        budget(); stage.rename(run/'complete')
        print(json.dumps(dict(status=proof['status'],run_id=run_id,scenarios=rows,identity=identity,synthetic_mc=mc),indent=2))
    except Exception as exc:
        proof.update(status='failed',error=type(exc).__name__+': '+str(exc),elapsed_seconds=time.monotonic()-start)
        (run/'failure.json').write_text(json.dumps(proof,indent=2,allow_nan=False))
        raise


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',required=True)
    main(parser.parse_args().run_id)
