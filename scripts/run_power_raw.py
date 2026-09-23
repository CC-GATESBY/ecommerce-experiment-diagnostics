"""One binary cohort projection, then 300 rounds of nine frozen power scenarios."""
import argparse
import csv
from datetime import date, timedelta
from fractions import Fraction
import hashlib
import io
import json
import math
from pathlib import Path
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
from abtest import power
from scripts.run_injection import COHORT, SCOPE, VALUES_SHA, require, sha

CONFIG_PATH = ROOT/'config/power_raw.json'
METHOD_FILES = ['config/power_raw.json', 'docs/power_raw_contract.md', 'abtest/power.py',
                'scripts/run_power_raw.py', 'tests/test_power_raw.py', 'abtest/inject.py',
                'abtest/assign.py', 'abtest/stats.py', 'abtest/srm.py', 'requirements.lock.txt']
HISTORY_FILES = ['config/aa.json', 'config/injection.json', 'docs/injection_contract.md',
                 'reports/aa_runs.csv', 'reports/aa_summary.csv', 'reports/aa_validation.md',
                 'reports/effect_injection_results.csv', 'reports/effect_injection.md',
                 'reports/cross_border_cost_review.md', 'config/cost_scenarios.json']


def expected_config():
    return dict(version=power.VERSION, run_id='power-raw-oct-01', cohort_run='cohort-oct-01',
        cohort_version=COHORT, expected_users=84165, expected_Y0_sum=4812,
        effect_grid_pp=list(power.GRID_PP), S1_REFERENCE_relative_lift='0.10', rounds=300,
        round_start=1, rng='PCG64', seed_sequence=[20260923, 'round_index'], sort='cohort_key_ASC',
        assignment_prefix=power.PREFIX.decode(), probability_B=.5, shared_within_round=['U', 'assignment'],
        alpha=.05, srm_alpha=.001, binary_method='unpooled_wald_z_min_cell_10',
        main_denominator='all_computable_including_SRM', interval_method='Wilson_95',
        mechanism_max_abs_mc_z=6, theory_mde_target=.8, theory_mde_bracket_pp=['0', '0.80'],
        new_output_limit_bytes=512*2**20, minimum_free_bytes=150*2**30)


def create_run(base, run_id):
    require(run_id == 'power-raw-oct-01', 'only the frozen run ID is allowed')
    base.mkdir(parents=True, exist_ok=True)
    run = base/run_id
    run.mkdir(exist_ok=False)
    (run/'staging').mkdir()
    return run


def load_cohort():
    """Validate metadata and fingerprints; query only the two authorized columns."""
    folder = ROOT/'.local/t51/cohort-oct-01/complete'
    receipt = folder/'validation.json'
    proof = json.loads(receipt.read_text())
    require(not (folder.parent/'staging').exists(), 'cohort incomplete')
    require((proof['status'], proof['run_id'], proof['cohort_version']) ==
            ('passed', 'cohort-oct-01', COHORT), 'cohort identity mismatch')
    require(proof['checks'] and all(v['passed'] is True for v in proof['checks'].values()), 'cohort checks failed')
    b = proof['baseline']
    require((b['scope_id'], b['analysis_scope'], b['fact_run'], b['metric_run']) ==
            (SCOPE, 'rees46_oct_user5_analysis_v1', 'month-v101-01', 'metrics-month-01'), 'lineage mismatch')
    require((b['pre_start'], b['pre_end_exclusive'], b['post_start'], b['post_end_exclusive']) ==
            ('2019-10-01', '2019-10-15', '2019-10-15', '2019-10-29'), 'window mismatch')
    require((b['enrolled_users'], b['post_buyers']) == (84165, 4812), 'baseline mismatch')
    expected_dates = {(date(2019,10,1)+timedelta(days=i)).isoformat() for i in range(28)}
    gates = proof['gates']
    require(len(gates) == 28 and {g['utc_date'] for g in gates} == expected_dates and
            all(g['count_allowed'] is True and g['scope_id'] == SCOPE and
                g['source_run'] == 'month-v101-01' for g in gates), 'count/date quality not allowed')
    path = folder/'cohort/values.parquet'
    meta = proof['outputs']['cohort/values.parquet']
    require(path.is_file() and not path.is_symlink() and path.stat().st_size == meta['bytes'] and
            sha(path) == meta['sha256'] == VALUES_SHA, 'values fingerprint mismatch')
    con = duckdb.connect(config={'threads':'1', 'memory_limit':'128MB',
        'autoload_known_extensions':'false', 'autoinstall_known_extensions':'false'})
    try:
        rows = con.execute('SELECT cohort_key, post_converted FROM read_parquet(?) '
                           'ORDER BY cohort_key LIMIT 84166', [str(path)]).fetchall()
    finally:
        con.close()
    require(len(rows) == 84165 and all(r[1] in (0,1) for r in rows), 'binary count/domain mismatch')
    prepared = power.prepare_cohort([r[0] for r in rows], [r[1] for r in rows])
    require(int(prepared['y0'].sum()) == 4812, 'Y0 sum mismatch')
    return prepared, {str(path):VALUES_SHA, str(receipt):sha(receipt)}


def independent_checks(rows, summary):
    """Independent Fraction/stdlib count reconstruction; no call to proportions."""
    max_error = 0.
    def compare(expected, actual):
        nonlocal max_error
        require(actual is not None and math.isclose(expected, actual, rel_tol=1e-12, abs_tol=1e-15),
                'independent count/formula mismatch')
        max_error = max(max_error, abs(expected-actual))
    for row in rows:
        if row['n_A'] and row['n_B']:
            a = Fraction(row['buyers_A'], row['n_A'])
            b = Fraction(row['buyers_B'], row['n_B'])
            if row['difference'] is not None:
                compare(float(b-a), row['difference'])
            compare(row['K']/row['N'], row['tau'])
            if row['status'] == 'ok':
                se = math.sqrt(float(a*(1-a)/row['n_A']+b*(1-b)/row['n_B']))
                half = NormalDist().inv_cdf(.975)*se
                compare(se, row['se'])
                compare(float(b-a)-half, row['ci_low'])
                compare(float(b-a)+half, row['ci_high'])
                p = math.erfc(abs(float(b-a))/se/math.sqrt(2))
                compare(p, row['p_value'])
                require(row['two_sided_rejection'] == (p < .05), 'rejection mismatch')
                require(row['positive_rejection'] == (p < .05 and b > a), 'positive rejection mismatch')
                require(row['negative_rejection'] == (p < .05 and b < a), 'negative rejection mismatch')
        require(row['n_A']+row['n_B'] == row['N'], 'assignment conservation failed')
    for round_index in sorted({r['round'] for r in rows}):
        group = [r for r in rows if r['round'] == round_index]
        require(len(group) == 9 and len({(r['n_A'],r['n_B'],r['buyers_A']) for r in group}) == 1,
                'within-round identity mismatch')
        zero = next(r for r in group if r['effect'] == '0')
        require(zero['K'] == zero['flips_B'] == 0, 'zero effect changed outcomes')
        for r in group:
            require(r['buyers_B']-zero['buyers_B'] == r['flips_B'], 'B flip identity failed')
        ks = [r['K'] for r in sorted(group, key=lambda r:r['delta'])]
        require(ks == sorted(ks), 'shared-U monotone potentials failed')
    for s in summary:
        group = [r for r in rows if r['effect'] == s['effect']]
        valid = [r for r in group if r['status'] == 'ok' and r['p_value'] is not None]
        require(s['completed'] == len(group) and s['valid'] == len(valid) and
                s['failed'] == len(group)-len(valid), 'summary denominator mismatch')
        for name in ('two_sided', 'positive'):
            k = sum(r[name+'_rejection'] is True for r in valid)
            require(k == s[name+'_count'], 'summary numerator mismatch')
            if valid:
                n = len(valid); p = k/n; z = NormalDist().inv_cdf(.975)
                center = (p+z*z/(2*n))/(1+z*z/n)
                half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
                compare(center-half, s[name+'_ci_low'])
                compare(center+half, s[name+'_ci_high'])
    return dict(status='passed', evaluated_rows=len(rows), summary_rows=len(summary),
                max_absolute_float_difference=max_error,
                methods='Fraction, NormalDist/erfc, direct Wilson formula; all rows checked')


def write_csv(path, rows, fields=None):
    with path.open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields or list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def main(run_id):
    config = json.loads(CONFIG_PATH.read_text())
    require(config == expected_config(), 'unapproved power configuration')
    for name in ('power_raw_runs.csv', 'power_raw_summary.csv'):
        require(not (ROOT/'reports'/name).exists(), 'shared output already exists; no overwrite')
    run = create_run(ROOT/'.local/power01', run_id)
    stage = run/'staging'
    start = time.monotonic()
    proof = dict(status='failed', run_id=run_id, config=config)
    def budget():
        new_bytes = sum(p.stat().st_size for p in run.rglob('*') if p.is_file())
        free = shutil.disk_usage(ROOT).free
        # Covers shared CSV copies, code, documents and the final receipt.
        require(new_bytes+16*2**20 <= config['new_output_limit_bytes'] and
                free >= config['minimum_free_bytes'], 'resource budget exceeded')
        return dict(local_bytes=new_bytes, reserved_other_bytes=16*2**20, free_bytes=free,
                    peak_memory='not_measured')
    try:
        before = budget()
        frozen = {p:sha(ROOT/p) for p in METHOD_FILES}
        history = {p:sha(ROOT/p) for p in HISTORY_FILES}
        old_metadata = {}
        for relative in ('.local/t51/cohort-oct-01', '.local/t54/aa-oct-01', '.local/t55/injected-oct-01'):
            for p in (ROOT/relative).rglob('*'):
                if p.is_file():
                    stat = p.stat()
                    old_metadata[str(p)] = (stat.st_size, stat.st_mtime_ns)
        (run/'frozen_config.json').write_text(json.dumps(config, indent=2))
        log = io.StringIO()
        suite = unittest.defaultTestLoader.loadTestsFromNames(['tests.test_power_raw', 'tests.test_inject'])
        tests = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        (run/'tests.log').write_text(log.getvalue())
        require(tests.wasSuccessful(), 'synthetic gate failed')
        print('Synthetic checks passed; loading one binary-only cohort projection.', flush=True)
        prepared, protected = load_cohort()
        y0_hash = hashlib.sha256(prepared['y0'].tobytes()).hexdigest()
        rows, audits = [], []
        simulation_start = time.monotonic()
        with (stage/'power_raw_runs.csv').open('x', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=power.RUN_FIELDS, lineterminator='\n')
            writer.writeheader()
            for round_index in range(1, 301):
                block, audit = power.simulate_round(prepared, round_index)
                writer.writerows(block); f.flush()
                rows.extend(block); audits.append(audit)
                if round_index % 25 == 0:
                    budget()
                    print(f'Completed {round_index}/300 rounds ({len(rows)}/2700 evaluations); '
                          f'{time.monotonic()-simulation_start:.1f}s.', flush=True)
        simulation_seconds = time.monotonic()-simulation_start
        summary = power.summarize(rows, len(prepared['y0']), prepared['p0'])
        checks = independent_checks(rows, summary)
        write_csv(stage/'power_raw_summary.csv', summary)
        require(all(s['mechanism_status'] == 'passed' for s in summary), 'mechanism needs review; results retained')
        require(not prepared['y0'].flags.writeable and
                hashlib.sha256(prepared['y0'].tobytes()).hexdigest() == y0_hash, 'Y0 changed')
        require(all(sha(p) == h for p,h in protected.items()), 'cohort changed')
        require(all(sha(ROOT/p) == h for p,h in (frozen | history).items()), 'method/history changed')
        require(all((Path(p).stat().st_size, Path(p).stat().st_mtime_ns) == v
                    for p,v in old_metadata.items()), 'old run files changed')
        n = len(prepared['y0'])
        proof.update(status='passed', tests_passed=tests.testsRun,
            input_check=dict(N=n, Y0_sum=int(prepared['y0'].sum()), query_count=1,
                             queried_columns=['cohort_key','post_converted'], Y0_unchanged=True),
            p0_fraction=str(prepared['p0']), planned=2700, completed=len(rows),
            valid=sum(s['valid'] for s in summary), failed=sum(s['failed'] for s in summary),
            independent_checks=checks, method_sha256=frozen, historical_sha256=history,
            protected_hashes=protected, old_run_metadata_unchanged=True, round_fingerprints=audits,
            mde=power.theoretical_mde(n, prepared['p0']), empirical_crossings=power.empirical_crossings(summary),
            simulation_seconds=simulation_seconds, total_seconds=time.monotonic()-start,
            resources_before=before, resources_after=budget(),
            versions=dict(python=sys.version.split()[0], numpy=np.__version__, scipy=scipy.__version__, duckdb=duckdb.__version__),
            outputs={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in stage.iterdir()})
        (stage/'validation.json').write_text(json.dumps(proof, indent=2, allow_nan=False))
        budget()
        stage.rename(run/'complete')
        for name in ('power_raw_runs.csv', 'power_raw_summary.csv'):
            with (run/'complete'/name).open('rb') as source, (ROOT/'reports'/name).open('xb') as target:
                shutil.copyfileobj(source, target)
        print(json.dumps(dict(status='passed', run_id=run_id, completed=len(rows),
                              mde=proof['mde'], empirical_crossings=proof['empirical_crossings']), indent=2))
    except BaseException as exc:
        proof.update(status='failed', error=type(exc).__name__+': '+str(exc),
                     elapsed_seconds=time.monotonic()-start)
        (run/'failure.json').write_text(json.dumps(proof, indent=2, allow_nan=False))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    main(parser.parse_args().run_id)
