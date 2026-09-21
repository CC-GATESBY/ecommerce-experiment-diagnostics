"""PRICE-01: fixed-price-pair association and explicitly conditional margins.

Only canonical October path Parquet is queried. No facts, CSV events, or Spark.
"""
import argparse
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

import duckdb
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
D = Decimal
SCOPE = 'rees46_2019_oct_user5_fedd938409b5f836_20260916_v1'
COLUMNS = ('scope_id,user_id,user_session,product_id,first_view_time,start_date_utc,'
           'first_view_price,first_view_price_status,has_purchase_after_view,release_status')
FLAGS = ['paths_ok', 'users_ok', 'days_ok', 'coverage_ok', 'gap_ok']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, indent=2, default=str, allow_nan=False)
        f.write('\n')


def write_csv(path, rows, empty_fields=None):
    fields = list(dict.fromkeys(k for r in rows for k in r)) or empty_fields
    with Path(path).open('x', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        w.writerows(rows)


def rows(con, sql, params=None, cap=100):
    cur = con.execute(sql, params or [])
    names = [x[0] for x in cur.description]
    out = cur.fetchmany(cap + 1)
    require(len(out) <= cap, 'bounded aggregate cap exceeded')
    return [dict(zip(names, r)) for r in out]


def select_pairs(con, cfg):
    params = dict(min_paths=cfg['min_paths_per_price'], min_users=cfg['min_users_per_price'],
                  min_days=cfg['min_dates_per_price'], min_coverage=cfg['min_pair_coverage'],
                  min_gap=cfg['min_price_gap'], max_gap=cfg['max_price_gap'])
    for statement in (ROOT/'sql/price/select_pairs.sql').read_text().split(';'):
        if statement.strip():
            con.execute(statement, params if '$min_paths' in statement else [])
    return rows(con, 'SELECT * FROM candidates ORDER BY min_users DESC,pair_paths DESC,product_id ASC LIMIT ?',
                [cfg['max_products']], cap=cfg['max_products'])



def price_support(con, product_id, low, high):
    return rows(con, "SELECT first_view_price AS price,COUNT(*) AS paths,COUNT(DISTINCT user_id) AS users,"
                "SUM(has_purchase_after_view::INT) AS successes,MIN(start_date_utc) AS first_date,"
                "MAX(start_date_utc) AS last_date,COUNT(DISTINCT start_date_utc) AS days "
                "FROM usable WHERE product_id=? AND first_view_price IN (?,?) GROUP BY 1 ORDER BY 1",
                [product_id, low, high], cap=2)


def margin(m, d, p_high=None, p_low=None):
    m, d = D(str(m)), D(str(d))
    require(D(0) < m <= 1 and D(0) <= d < 1, 'invalid margin/gap')
    r = dict(m=m, d=d, required_rate_ratio=None, required_relative_lift=None,
             required_low_rate=None, contribution_difference=None, status='defined')
    if m <= d:
        r['status'] = 'unit_contribution_nonpositive'
    else:
        r['required_rate_ratio'] = m/(m-d)
        r['required_relative_lift'] = d/(m-d)
    if p_high is not None:
        h, l = D(str(p_high)), D(str(p_low))
        require(0 <= h <= 1 and 0 <= l <= 1, 'invalid probability')
        r['contribution_difference'] = l*(m-d)-h*m
        if m > d:
            if h == 0:
                r.update(status='zero_high_rate_no_relative_threshold', required_rate_ratio=None,
                         required_relative_lift=None)
            else:
                r['required_low_rate'] = h*m/(m-d)
                if r['required_low_rate'] > 1:
                    r['status'] = 'required_probability_unattainable'
    return r


def compact_arrays(records):
    """Each row: stable user string, UTC day, side L=0/H=1, paths, successes."""
    users = sorted({r[0] for r in records})
    dates = sorted({str(r[1]) for r in records})
    ui, di = {u: i for i, u in enumerate(users)}, {d: i for i, d in enumerate(dates)}
    user = np.array([ui[r[0]] for r in records], dtype=np.int64)
    cell = np.array([2*di[str(r[1])]+int(r[2]) for r in records], dtype=np.int64)
    n = np.array([r[3] for r in records], dtype=np.int64)
    y = np.array([r[4] for r in records], dtype=np.int64)
    require(len(records) > 0 and np.all(n > 0) and np.all((y >= 0) & (y <= n)), 'invalid sufficient statistics')
    require(len(set(zip(user.tolist(), cell.tolist()))) == len(records), 'duplicate compact key')
    return users, dates, user, cell, n, y


def weighted_cells(weights, user, cell, n, y, date_count):
    """One user weight applies to every date and both price states."""
    wn = np.bincount(cell, weights=weights[user]*n, minlength=2*date_count).reshape(-1, 2)
    wy = np.bincount(cell, weights=weights[user]*y, minlength=2*date_count).reshape(-1, 2)
    return wn, wy


def rates(n, y, common, date_weights):
    den = n.sum(axis=0)
    raw = y.sum(axis=0)/den if np.all(den > 0) else None
    std = None
    if len(common) and np.all(n[common] > 0):
        std = ((y[common]/n[common])*date_weights[:, None]).sum(axis=0)
    return raw, std


def intervals(samples):
    if not len(samples):
        return dict(difference_ci_low_pp=None, difference_ci_high_pp=None,
                    relative_ci_low=None, relative_ci_high=None, relative_valid=0)
    diff = samples[:, 0]-samples[:, 1]
    ci = np.quantile(diff*100, [.025, .975], method='linear')
    ok = samples[:, 1] > 0
    rel = np.quantile(diff[ok]/samples[ok, 1], [.025, .975], method='linear') if ok.any() else [None, None]
    return dict(difference_ci_low_pp=ci[0], difference_ci_high_pp=ci[1],
                relative_ci_low=rel[0], relative_ci_high=rel[1], relative_valid=int(ok.sum()))


def compare(records, cfg, rank):
    users, dates, user, cell, n, y = compact_arrays(records)
    require(len(users) <= cfg['max_compact_users_per_product'] and len(records) <= cfg['max_compact_rows_per_product'], 'compact memory cap exceeded')
    totals, successes = weighted_cells(np.ones(len(users)), user, cell, n, y, len(dates))
    common = np.where(np.all(totals >= cfg['common_date_min_paths_per_price'], axis=1))[0]
    supported = len(common) >= cfg['min_common_dates']
    weights = totals[common].sum(axis=1)/totals[common].sum() if supported else np.array([])
    used = common if supported else np.array([], dtype=np.int64)
    raw, std = rates(totals, successes, used, weights)
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([cfg['bootstrap_seed'], rank])))
    draws = {'raw': [], 'date_standardized': []}
    for _ in range(cfg['bootstrap_repetitions']):
        w = np.bincount(rng.integers(0, len(users), size=len(users)), minlength=len(users))
        nn, yy = weighted_cells(w, user, cell, n, y, len(dates))
        rr, ss = rates(nn, yy, used, weights)
        if rr is not None:
            draws['raw'].append(rr)
        if ss is not None:
            draws['date_standardized'].append(ss)
    output = []
    arrays = {}
    for branch, point, subset in [('raw', raw, np.arange(len(dates))), ('date_standardized', std, used)]:
        arr = np.asarray(draws[branch], dtype=float).reshape(-1, 2)
        arrays[branch] = arr
        low_y, high_y = successes[subset].sum(axis=0)
        sparse = min(low_y, high_y) < cfg['sparse_success_warning_below']
        r = dict(branch=branch, status='defined' if point is not None else 'date_comparison_not_supported',
                 p_low=None if point is None else point[0], p_high=None if point is None else point[1],
                 absolute_difference=None if point is None else point[0]-point[1],
                 difference_pp=None if point is None else 100*(point[0]-point[1]),
                 relative_difference=None if point is None or point[1] == 0 else (point[0]-point[1])/point[1],
                 relative_status='not_available' if point is None else ('zero_high_rate' if point[1] == 0 else 'defined'),
                 bootstrap_planned=cfg['bootstrap_repetitions'], bootstrap_valid=len(arr),
                 bootstrap_invalid=cfg['bootstrap_repetitions']-len(arr) if point is not None else 0,
                 invalid_reason='zero_price_denominator' if branch == 'raw' else ('zero_common_date_price_denominator' if supported else 'not_run_date_comparison_not_supported'),
                 interval_status='not_available' if point is None else ('sparse_successes_not_suitable_for_inference' if sparse else 'descriptive_cluster_interval'),
                 common_dates=len(common), common_date_list=';'.join(dates[i] for i in common),
                 common_date_path_coverage=float(totals[common].sum()/totals.sum()) if len(common) else 0,
                 evaluated_paths=int(totals[subset].sum()) if point is not None else 0,
                 bootstrap_relative_invalid=int(len(arr)-(arr[:, 1] > 0).sum()),
                 **intervals(arr))
        output.append(r)
    days = [dict(utc_date=date, low_paths=int(totals[i, 0]), high_paths=int(totals[i, 1]),
                 low_successes=int(successes[i, 0]), high_successes=int(successes[i, 1]),
                 standardized_weight=float(weights[list(used).index(i)]) if i in used else None)
            for i, date in enumerate(dates)]
    shared_users = len(set(user[cell % 2 == 0]) & set(user[cell % 2 == 1]))
    return output, arrays, days, dict(distinct_pair_users=len(users), users_at_both_prices=shared_users,
                                    compact_rows=len(records), numeric_array_bytes=user.nbytes+cell.nbytes+n.nbytes+y.nbytes)


def inventory(paths):
    return {str(p): dict(bytes=p.stat().st_size, sha256=digest(p)) for p in paths}


def locate(locator, cfg):
    """Use canonical completion directory and launch, preserving the T2.2 legacy resolution."""
    source = json.loads(Path(locator).read_text())
    rel = Path(source['funnel_run'])
    run = (ROOT/rel).resolve()
    require(not rel.is_absolute() and run.is_relative_to(ROOT/'.local/t21') and run.name == cfg['funnel_run'], 'wrong canonical funnel path')
    proof_path, launch_path = run/'complete/validation.json', run/'launch.json'
    proof, launch = json.loads(proof_path.read_text()), json.loads(launch_path.read_text())
    require(not (run/'staging').exists() and proof['status'] == launch['status'] == 'passed'
            and proof['spark_stopped'] and proof['checks'] and all(c['pass'] for c in proof['checks'].values()), 'incomplete funnel evidence')
    scope = yaml.safe_load((ROOT/'config/analysis_scope.yaml').read_text())
    lineage = proof['lineage']
    require(lineage['analysis_scope_version'] == cfg['analysis_scope'] == scope['analysis_scope_version']
            and lineage['source_run'] == cfg['fact_run'] == scope['binding']['fact_run']
            and lineage['funnel_version'] == cfg['funnel_version']
            and lineage['input_sha256'] == scope['binding']['candidate_sha256'], 'lineage mismatch')
    require(lineage['funnel_run'] == 'staging', 'unexpected historical run encoding')
    # This historical value was already reviewed in scripts/behavior_analysis.py.
    folder = run/'complete/analysis/funnel_paths'
    require((folder/'_SUCCESS').exists(), 'missing Parquet success marker')
    files = sorted(folder.glob('*.parquet'))
    require(bool(files) and all(not p.is_symlink() for p in files), 'missing or redirected path files')
    local_csv = run/'complete/analysis/funnel_summary.csv'
    with local_csv.open(newline='') as f, (ROOT/'reports/funnel_summary.csv').open(newline='') as g:
        require(list(csv.DictReader(f)) == list(csv.DictReader(g)), 'published funnel summary content changed')
    expected = next(r for r in proof['summary'] if r['level'] == 'overall')
    with local_csv.open() as f:
        published = next(r for r in csv.DictReader(f) if r['level'] == 'overall')
    require(all(int(published[k]) == expected[k] for k in ['n_view', 'n_purchase']), 'receipt/summary mismatch')
    protected = inventory(files+[proof_path, launch_path, local_csv, ROOT/'reports/funnel_summary.csv', ROOT/'config/analysis_scope.yaml'])
    return files, proof, expected, protected


def run(args):
    cfg_path = ROOT/'config/price_analysis.json'
    cfg = json.loads(cfg_path.read_text())
    require(cfg['version'] == 'rees46-price-margin-v1' and cfg['max_products'] <= 3, 'unexpected policy')
    require(args.run_id and all(c.isalnum() or c in '-_' for c in args.run_id), 'invalid run id')
    out = ROOT/'.local/price01'/args.run_id
    out.mkdir(parents=True, exist_ok=False)
    start, free_start = time.monotonic(), shutil.disk_usage(ROOT).free
    base = ROOT/'.local/price01'
    checks = []
    def check(name, expected, actual):
        checks.append(dict(check=name, expected=expected, actual=actual, passed=expected == actual))
        require(expected == actual, name)
    def budget():
        used = sum(p.stat().st_size for p in base.rglob('*') if p.is_file())
        require(used < 2*1024**3 and shutil.disk_usage(ROOT).free >= 150*1024**3, 'resource budget exceeded')
        return used
    con = None
    try:
        budget()
        write_json(out/'frozen_policy.json', cfg)
        code_paths = [cfg_path, Path(__file__), ROOT/'sql/price/select_pairs.sql', ROOT/'tests/test_price_margin.py']
        code_inventory = inventory(code_paths)
        files, proof, expected, protected = locate(ROOT/args.funnel_locator, cfg)
        write_json(out/'input_inventory.json', protected)
        con = duckdb.connect(str(out/'work.duckdb'))
        con.execute("SET memory_limit='768MB'; SET threads=2; SET TimeZone='UTC'; SET max_temp_directory_size='512MB'")
        con.execute('SET temp_directory=?', [str(out/'temp')])
        schema = {r[0]: r[1] for r in con.execute('DESCRIBE SELECT * FROM read_parquet(?)', [[str(p) for p in files]]).fetchall()}
        require(set(COLUMNS.split(',')) <= set(schema) and schema['first_view_price'] == 'DECIMAL(18,2)', 'path schema mismatch')
        # Explicit file list and only the ten authorized columns; no directory wildcard in a query.
        con.from_parquet([str(p) for p in files]).project(COLUMNS).create_view('paths')
        counts = rows(con, "SELECT release_status,COUNT(*) n,SUM(has_purchase_after_view::INT) successes FROM paths GROUP BY 1", cap=3)
        check('all_paths', proof['path_records'], sum(r['n'] for r in counts))
        formal = next(r for r in counts if r['release_status'] == 'formal')
        check('formal_paths', expected['n_view'], formal['n'])
        check('formal_success_paths', expected['n_purchase'], formal['successes'])
        invalid = con.execute("SELECT COUNT(*) FROM paths WHERE scope_id IS DISTINCT FROM ? OR user_id IS NULL OR product_id IS NULL OR has_purchase_after_view IS NULL OR (release_status='formal' AND (start_date_utc<DATE '2019-10-01' OR start_date_utc>=DATE '2019-10-31' OR start_date_utc IS DISTINCT FROM first_view_time::DATE))", [SCOPE]).fetchone()[0]
        check('scope_dates_and_required_fields', 0, invalid)
        con.execute("CREATE TEMP VIEW formal AS SELECT * FROM paths WHERE release_status='formal'")
        con.execute("CREATE TEMP VIEW usable AS SELECT * FROM formal WHERE first_view_price_status='unique_valid' AND first_view_price>0")
        feasibility = []
        def measure(name, value, unit='products', definition=''):
            feasibility.append(dict(measure=name, value=value, unit=unit, definition=definition))
        for r in rows(con, "SELECT CASE WHEN first_view_price_status='conflicting' THEN 'conflicting' WHEN first_view_price_status<>'unique_valid' OR first_view_price IS NULL THEN 'invalid_or_missing' WHEN first_view_price=0 THEN 'zero_price' WHEN first_view_price<0 THEN 'negative_price' ELSE 'positive_usable' END reason,COUNT(*) n FROM formal GROUP BY 1", cap=5):
            measure('formal_'+r['reason'], r['n'], 'paths', 'mutually_exclusive_price_status')
        # Always disclose zero-count exclusions as measured zeros.
        for reason in ['conflicting', 'invalid_or_missing', 'zero_price', 'negative_price']:
            if not any(r['measure'] == 'formal_'+reason for r in feasibility):
                measure('formal_'+reason, 0, 'paths', 'mutually_exclusive_price_status')
        check('price_exclusion_conservation', formal['n'], sum(r['value'] for r in feasibility))
        measure('formal_products', con.execute('SELECT COUNT(DISTINCT product_id) FROM formal').fetchone()[0])
        measure('positive_usable_products', con.execute('SELECT COUNT(DISTINCT product_id) FROM usable').fetchone()[0])
        selected = select_pairs(con, cfg)
        measure('at_least_two_prices', con.execute('SELECT COUNT(*) FROM pairs').fetchone()[0])
        for i, flag in enumerate(FLAGS):
            measure(flag+'_standalone', con.execute('SELECT COUNT(*) FROM pairs WHERE '+flag).fetchone()[0], definition='among_products_with_two_prices')
            measure(flag+'_cumulative', con.execute('SELECT COUNT(*) FROM pairs WHERE '+' AND '.join(FLAGS[:i+1])).fetchone()[0], definition='conditions_in_paths_users_days_coverage_gap_order')
        measure('final_candidates', con.execute('SELECT COUNT(*) FROM candidates').fetchone()[0])
        con.execute('COPY (SELECT * FROM candidates ORDER BY min_users DESC,pair_paths DESC,product_id ASC) TO ? (HEADER, DELIMITER \',\')', [str(out/'candidates_private.csv')])
        # The list is persisted before querying any selected-product outcomes.
        write_json(out/'selected_private.json', [dict(alias='price_product_'+chr(65+i), **p) for i, p in enumerate(selected)])
        for label, price_filter in [('candidate_all_usable', ''), ('candidate_price_pairs', 'AND u.first_view_price IN (c.low_price,c.high_price)')]:
            n, u, y = con.execute('SELECT COUNT(*),COUNT(DISTINCT u.user_id),COALESCE(SUM(u.has_purchase_after_view::INT),0) FROM usable u JOIN candidates c USING(product_id) WHERE TRUE '+price_filter).fetchone()
            for metric, value in [('paths', n), ('distinct_users', u), ('success_paths', y)]:
                measure(label+'_'+metric, value, metric, 'independently_deduplicated_across_products_for_users')
        comparisons, scenarios, daily = [], [], []
        for m in cfg['hypothetical_margins']:
            for d in cfg['hypothetical_gaps']:
                scenarios.append(dict(scenario_type='generic_hypothesis_grid', alias='', branch='hypothesis_only', **margin(m, d)))
        for rank, pair in enumerate(selected, 1):
            alias = 'price_product_'+chr(64+rank)
            pid, low, high = pair['product_id'], pair['low_price'], pair['high_price']
            params = [pid, low, high]
            query = 'FROM usable WHERE product_id=? AND first_view_price IN (?,?)'
            support = price_support(con, pid, low, high)
            compact_query = 'SELECT user_id,start_date_utc,CASE WHEN first_view_price=? THEN 0 ELSE 1 END side,COUNT(*) n,SUM(has_purchase_after_view::INT) y '+query+' GROUP BY 1,2,3 ORDER BY 1,2,3'
            compact_params = [low]+params
            nrows, nusers = con.execute('SELECT COUNT(*),COUNT(DISTINCT user_id) FROM ('+compact_query+')', compact_params).fetchone()
            require(nrows <= cfg['max_compact_rows_per_product'] and nusers <= cfg['max_compact_users_per_product'], 'selected compact cap exceeded; stop, do not replace product')
            records = con.execute(compact_query, compact_params).fetchall()
            output, draws, day, memory = compare(records, cfg, rank)
            write_json(out/(alias+'_compact_private.json'), records)
            check(alias+'_paths_from_compact', pair['pair_paths'], sum(r[3] for r in records))
            for side in range(2):
                check(alias+'_successes_'+str(side), support[side]['successes'], sum(r[4] for r in records if r[2] == side))
                check(alias+'_users_'+str(side), support[side]['users'], len({r[0] for r in records if r[2] == side}))
            d = (high-low)/high
            common_any = sum(r['low_paths'] > 0 and r['high_paths'] > 0 for r in day)
            meta = dict(alias=alias, P_low=low, P_high=high, gap=d, positive_product_paths=pair['total_paths'],
                        pair_paths=pair['pair_paths'], pair_path_share=D(pair['pair_paths'])/D(pair['total_paths']),
                        both_price_dates=common_any, **memory)
            for label, s in zip(['low', 'high'], support):
                meta.update({label+'_'+k: v for k, v in s.items() if k != 'price'})
                meta[label+'_path_share'] = D(s['paths'])/D(pair['total_paths'])
            for r in output:
                comparisons.append(dict(meta, **r))
                if r['p_high'] is not None:
                    for m in cfg['hypothetical_margins']:
                        mr = margin(m, d, r['p_high'], r['p_low'])
                        arr = draws[r['branch']]
                        ci = np.quantile(arr[:, 0]*(float(m)-float(d))-arr[:, 1]*float(m), [.025, .975], method='linear') if len(arr) else [None, None]
                        scenarios.append(dict(scenario_type='observed_price_pair_conditional_comparison', alias=alias,
                            branch=r['branch'], P_high=high, P_low=low, p_high=r['p_high'], p_low=r['p_low'],
                            observed_relative_difference=r['relative_difference'], **mr,
                            observed_minus_required_low_rate=None if mr['required_low_rate'] is None else D(str(r['p_low']))-mr['required_low_rate'],
                            contribution_ci_low=ci[0], contribution_ci_high=ci[1], bootstrap_valid=len(arr), interval_status=r['interval_status']))
            daily.extend(dict(alias=alias, **r) for r in day)
            budget()
            print(json.dumps(dict(stage='selected_product_complete', alias=alias, compact_rows=nrows, elapsed_seconds=round(time.monotonic()-start, 2))), flush=True)
        check('input_fingerprints_unchanged', protected, inventory([Path(p) for p in protected]))
        check('code_policy_unchanged', code_inventory, inventory(code_paths))
        con.close()
        con = None
        write_csv(out/'feasibility.csv', feasibility)
        write_csv(out/'product_comparisons.csv', comparisons, ['alias', 'branch', 'status'])
        write_csv(out/'margin_scenarios.csv', scenarios)
        write_csv(out/'date_comparison.csv', daily, ['alias', 'utc_date', 'low_paths', 'high_paths'])
        check('selected_count', min(3, int(next(r['value'] for r in feasibility if r['measure'] == 'final_candidates'))), len(selected))
        result = dict(status='passed', run_id=args.run_id, version=cfg['version'], source_run=cfg['funnel_run'],
                      selected_count=len(selected), analysis_status='completed' if selected else 'feasibility_only_no_supported_products',
                      policy=cfg, checks=checks, input_files=len(files), input_bytes=sum(p.stat().st_size for p in files),
                      elapsed_seconds=round(time.monotonic()-start, 3), new_bytes=budget(), free_start=free_start,
                      free_end=shutil.disk_usage(ROOT).free, peak_memory='not_measured',
                      versions=dict(python=sys.version.split()[0], duckdb=duckdb.__version__, numpy=np.__version__),
                      code_inventory=code_inventory)
        write_json(out/'complete.json', result)
        print(json.dumps({k: result[k] for k in ['status', 'selected_count', 'elapsed_seconds', 'new_bytes']}), flush=True)
    except BaseException as exc:
        write_json(out/'failed.json', dict(status='failed', error=type(exc).__name__+': '+str(exc), checks=checks))
        raise
    finally:
        if con is not None:
            con.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--funnel-locator', required=True)
    parser.add_argument('--run-id', required=True)
    run(parser.parse_args())
