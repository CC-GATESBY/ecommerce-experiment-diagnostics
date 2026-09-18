"""Bounded Nov14-18 source/sample reconciliation and post-hoc sensitivity."""
import argparse
from collections import Counter
import csv
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from anomaly.diagnose import screen, serialized
from etl.oracle import oracle_row
from ingest.profile_and_sample import HEADER, HashingReader, add_fields, parse_time, selected

START, END = '2019-11-14', '2019-11-19'
DAYS = [(date.fromisoformat(START) + timedelta(days=i)).isoformat() for i in range(5)]
SUSPECT = {'2019-11-15', '2019-11-16', '2019-11-17'}
SOURCE_SHA = 'addd9a27ed99abdece368019ebfba19568972c7fcbe949db3484aab8a3bcffec'
SAMPLE_SHA = '46d918b3049ba540429519bd0f44852408910a00ce4ab48d569b429352d10e05'
CFG = dict(history_offsets_days=[7, 14, 21, 28], min_history_points=3,
           mad_scale='1.4826', score_abs_gt='3', relative_change_abs_gte='0.10')
BASE = ROOT / '.local/purchase_timing'
GIB = 1024**3


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, obj):
    with path.open('x') as f:
        json.dump(serialized(obj), f, ensure_ascii=False, indent=2); f.write('\n')


def write_csv(path, rows):
    with path.open('x', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n"); writer.writeheader()
        writer.writerows([{k: ';'.join(v) if isinstance(v, list) else v for k, v in serialized(r).items()} for r in rows])


class Window:
    def __init__(self):
        self.hours = {f'{d}T{h:02}:00:00Z': Counter() for d in DAYS for h in range(24)}
        self.money = {k: Decimal('0.00') for k in self.hours}
        self.bad = Counter(); self.first = {}; self.last = {}
        self.sequence = hashlib.sha256()

    def observe(self, row, stamp, purchase):
        hour = stamp[:13] + ':00:00Z'; day = stamp[:10]
        self.hours[hour][row[1]] += 1
        if purchase is not None:
            if purchase['amount_eligible']:
                self.money[hour] += Decimal(purchase['price_decimal'])
            else:
                self.bad[hour] += 1
            self.first[day] = min(self.first.get(day, stamp), stamp)
            self.last[day] = max(self.last.get(day, stamp), stamp)

    def daily(self, day):
        keys = [k for k in self.hours if k[:10] == day]
        counts = sum((self.hours[k] for k in keys), Counter())
        bad = sum(self.bad[k] for k in keys)
        purchases = counts['purchase']
        return dict(event_records=sum(counts.values()), view=counts['view'], cart=counts['cart'],
                    purchase=purchases, purchase_amount=sum((self.money[k] for k in keys), Decimal('0.00')),
                    purchase_amount_bad=bad, amount_status='partial_observed' if bad else 'complete_observed' if purchases else 'no_observed_purchases',
                    first_purchase_utc=self.first.get(day), last_purchase_utc=self.last.get(day))

    def hourly(self, identity):
        return [dict(identity=identity, utc_hour=k, scan_status='complete',
                     event_records=sum(v.values()), view=v['view'], cart=v['cart'], purchase=v['purchase'],
                     purchase_amount=self.money[k], purchase_amount_bad=self.bad[k]) for k, v in self.hours.items()]


def scan(path, expected, *, source, db=None, budget=lambda: None):
    """Read each file once. No partial counters can be returned as complete."""
    start = time.monotonic(); all_rows = Window(); picked = Window(); n = inside = 0
    before = (path.stat().st_size, path.stat().st_mtime_ns)
    with path.open('rb') as raw:
        hashing = HashingReader(raw)
        with io.TextIOWrapper(io.BufferedReader(hashing), encoding='utf-8', newline='') as text:
            rows = csv.reader(text, strict=True)
            if next(rows, None) != HEADER: raise ValueError('header mismatch')
            for row in rows:
                n += 1
                if len(row) != 9: raise ValueError(f'CSV width error at record {n}')
                status, stamp = parse_time(row[0])
                if status != 'valid': raise ValueError(f'unassignable time at record {n}; zero counts cannot be certified')
                if START <= stamp[:10] < END:
                    inside += 1
                    if row[1] not in ('view', 'cart', 'purchase') or re.fullmatch('[0-9]+', row[7]) is None:
                        raise ValueError(f'core eligibility anomaly at record {n}')
                    purchase = oracle_row(row) if row[1] == 'purchase' else None
                    all_rows.observe(row, stamp, purchase)
                    is_selected = selected(row[7])
                    if not source and not is_selected: raise ValueError('candidate contains unselected user')
                    if is_selected:
                        picked.observe(row, stamp, purchase); add_fields(picked.sequence, row)
                    if db is not None and purchase is not None:
                        # Only the authorized candidate-window purchases, stored on disk.
                        key = json.dumps(row, ensure_ascii=False, separators=(',', ':'))
                        cents = int(Decimal(purchase['price_decimal']) * 100) if purchase['amount_eligible'] else 0
                        db.execute('INSERT INTO purchases VALUES (?,?,?,1) ON CONFLICT(raw_fields) DO UPDATE SET n=n+1', (key, stamp[:10], cents))
                if n % 5000000 == 0:
                    budget(); print(json.dumps(dict(phase='source' if source else 'candidate', processed_records=n,
                                                   elapsed_seconds=round(time.monotonic()-start, 2))), flush=True)
    after = (path.stat().st_size, path.stat().st_mtime_ns)
    actual = dict(bytes=hashing.bytes, sha256=hashing.digest.hexdigest(), records=n)
    if actual != expected or before != after: raise ValueError('input identity/record count/change mismatch')
    budget()
    return all_rows, picked, dict(status='complete', **actual, window_records=inside,
                                 selected_field_sequence_sha256=picked.sequence.hexdigest(),
                                 elapsed_seconds=round(time.monotonic()-start, 3))


def sensitivities(daily):
    """Do not mutate primary rows or replace removed history with other dates."""
    months = {'october_reference': [r for r in daily if r['utc_date'].startswith('2019-10')],
              'november_full_primary': [r for r in daily if r['utc_date'].startswith('2019-11')],
              'november_exclude_15_17_posthoc': [r for r in daily if r['utc_date'].startswith('2019-11') and r['utc_date'] not in SUSPECT]}
    monthly = []
    reference = sum((Decimal(r['purchase_amount']) for r in months['october_reference']), Decimal(0)) / len(months['october_reference'])
    for name, rows in months.items():
        if not rows or any(not r['count_allowed'] or not r['amount_allowed'] for r in rows):
            raise ValueError('monthly date/quality coverage invalid')
        total = sum((Decimal(r['purchase_amount']) for r in rows), Decimal(0)); mean = total / len(rows)
        monthly.append(dict(scenario=name, days=len(rows), purchase_amount=total, daily_mean=mean,
                            versus_october_daily_mean=mean/reference-1 if reference else None,
                            limitation='posthoc_unequal_calendar_not_adjusted_growth' if 'posthoc' in name else 'observational_log_not_platform_revenue'))
    days = [r['utc_date'] for r in daily]; lookup = {r['utc_date']: r for r in daily}
    affected = [d for d in days if any((date.fromisoformat(d)-timedelta(days=o)).isoformat() in SUSPECT for o in CFG['history_offsets_days'])]
    primary = {r['utc_date']: r for r in screen(daily, days, CFG)}
    alternative = [dict(r, amount_allowed=False) if r['utc_date'] in SUSPECT else dict(r) for r in daily]
    alt = {r['utc_date']: r for r in screen(alternative, days, CFG)}
    output = []
    for d in affected:
        for name, flags in [('original', primary), ('exclude_15_17_history_posthoc', alt)]:
            r = flags[d]; hist = r['history_dates']
            sufficient = len(hist) >= CFG['min_history_points']
            mean = sum((Decimal(lookup[h]['purchase_amount']) for h in hist), Decimal(0))/len(hist) if sufficient else None
            output.append(dict(utc_date=d, branch=name, history_dates=hist, history_count=len(hist),
                               current_amount=r['current_amount'], median_amount=r['median_amount'], mean_amount=mean,
                               relative_to_median=r['relative_change'], relative_to_mean=Decimal(r['current_amount'])/mean-1 if mean else None,
                               score=r['score'], candidate=r['candidate'], status=r['status'], reason=r['reason']))
    return monthly, output, primary


def run(run_id):
    if not re.fullmatch('[a-z0-9-]+', run_id): raise ValueError('unsafe run id')
    BASE.mkdir(exist_ok=True); target = BASE/run_id; target.mkdir(exist_ok=False)
    stage = target/'staging'; stage.mkdir(); started = time.monotonic()
    free_before = shutil.disk_usage(ROOT).free
    def budget():
        used = sum(p.stat().st_size for p in BASE.rglob('*') if p.is_file())
        free = shutil.disk_usage(ROOT).free
        if used > 2*GIB or free < 150*GIB: raise RuntimeError('resource budget exceeded')
        return dict(new_local_bytes=used, free_bytes=free)
    if free_before-2*GIB < 150*GIB: raise RuntimeError('projected free disk below minimum')
    try:
        prior = ROOT/'reports/cross_period'; local = ROOT/'.local/t4_cross_period'
        scope = json.loads((prior/'analysis_scope.json').read_text())
        manifest = json.loads((prior/'source_manifest.json').read_text())
        source_receipt = json.loads((local/'nov-source-01/complete.json').read_text())
        sample_dir = local/manifest['sample']['run_id']/'complete'
        sample_receipt = json.loads((sample_dir/'receipt.json').read_text())
        metrics_receipt = local/scope['november']['metrics_run']/'complete/validation.json'
        evidence_files = [prior/'analysis_scope.json', prior/'source_manifest.json', metrics_receipt,
                          local/'nov-source-01/complete.json', sample_dir/'receipt.json', ROOT/'config/cross_period.yaml',
                          ROOT/'etl/oracle.py', ROOT/'ingest/profile_and_sample.py', ROOT/'anomaly/diagnose.py']
        for name, sha in scope['result_files'].items():
            if digest(prior/name) != sha: raise ValueError('prior summary fingerprint mismatch')
            evidence_files.append(prior/name)
        if digest(metrics_receipt) != scope['november']['metrics_receipt_sha256']: raise ValueError('metrics receipt changed')
        if digest(ROOT/'config/cross_period.yaml') != scope['frozen_rule_sha256']: raise ValueError('frozen rule changed')
        if scope['analysis_scope_version'] != 'rees46_oct_nov_user5_analysis_v1' or scope['duplicate_policy'] != 'baseline_keep_all': raise ValueError('scope mismatch')
        if source_receipt['status'] != 'complete' or sample_receipt['status'] != 'validated': raise ValueError('completion required')
        if source_receipt['csv']['sha256'] != SOURCE_SHA or manifest['csv']['sha256'] != SOURCE_SHA or sample_receipt['parent_sha256'] != SOURCE_SHA: raise ValueError('source mismatch')
        if sample_receipt['sample']['sha256'] != SAMPLE_SHA or scope['november']['candidate_sha256'] != SAMPLE_SHA: raise ValueError('candidate mismatch')
        if sample_receipt['algorithm_version'] != 'rees46-user-sample-v1' or sample_receipt['seed'] != '20260916' or sample_receipt['target_user_probability'] != '0.05': raise ValueError('hash rule mismatch')
        source = (ROOT/source_receipt['csv']['local_relative_path']).resolve()
        candidate = sample_dir/'user_sample_candidate.csv'
        if not source.is_relative_to(local.resolve()) or not candidate.resolve().is_relative_to(local.resolve()): raise ValueError('input outside registered local space')
        evidence = {str(p.relative_to(ROOT)): digest(p) for p in evidence_files}
        input_stats = {str(p.relative_to(ROOT)): [p.stat().st_size, p.stat().st_mtime_ns] for p in (source, candidate)}
        expected_source = dict(bytes=manifest['csv']['bytes'], sha256=SOURCE_SHA, records=manifest['source_profile']['record_count'])
        expected_sample = dict(bytes=sample_receipt['sample']['bytes'], sha256=SAMPLE_SHA, records=sample_receipt['sample']['profile']['record_count'])
        write_json(target/'started.json', dict(status='running', window=[START, END], source=expected_source, candidate=expected_sample,
                                             script_sha256=digest(Path(__file__)), evidence=evidence, input_stats=input_stats,
                                             free_before=free_before))
        full, selected_source, source_scan = scan(source, expected_source, source=True, budget=budget)
        write_json(stage/'source_scan.json', dict(scan=source_scan, daily={d:full.daily(d) for d in DAYS},
                                               selected_daily={d:selected_source.daily(d) for d in DAYS},
                                               full_hourly=full.hourly('full_source'), selected_hourly=selected_source.hourly('fixed_user_sample')))
        with sqlite3.connect(stage/'purchase_duplicates.sqlite3') as db:
            db.execute('CREATE TABLE purchases(raw_fields TEXT PRIMARY KEY, day TEXT, cents INTEGER, n INTEGER) WITHOUT ROWID')
            sample, picked, sample_scan = scan(candidate, expected_sample, source=False, db=db, budget=budget)
            db.commit()
            duplicate = {r[0]:dict(groups=r[1], involved=r[2], excess=r[3], involved_amount=Decimal(r[4])/100, excess_amount=Decimal(r[5])/100) for r in db.execute('SELECT day,COUNT(*),SUM(n),SUM(n-1),SUM(n*cents),SUM((n-1)*cents) FROM purchases WHERE n>1 GROUP BY day')}
        if selected_source.sequence.hexdigest() != picked.sequence.hexdigest(): raise ValueError('selected raw field/order/multiplicity mismatch')
        if selected_source.hourly('fixed_hash') != sample.hourly('fixed_hash'): raise ValueError('sample hourly mismatch')
        daily = list(csv.DictReader((prior/'daily_metrics.csv').open()))
        for r in daily:
            for key in ('count_allowed', 'amount_allowed'): r[key] = r[key] == 'True'
        if len(daily) != 61 or len({r['utc_date'] for r in daily}) != 61: raise ValueError('daily calendar mismatch')
        # Reuse existing small independent parsing evidence for behavior-level reconciliation.
        oracle_file = local/'nov-metrics-01/complete/expected_daily.json'
        oracle_days = json.loads(oracle_file.read_text()); evidence[str(oracle_file.relative_to(ROOT))] = digest(oracle_file)
        reconciled = []
        for day in DAYS:
            a, b, c = full.daily(day), selected_source.daily(day), sample.daily(day)
            metric = next(r for r in daily if r['utc_date'] == day); old = oracle_days[day]
            if b != c: raise ValueError('source-hash and candidate day mismatch')
            if a['event_records'] != manifest['source_profile']['daily_records'][day]: raise ValueError('old source daily count mismatch')
            if c['event_records'] != int(metric['event_records']) or c['purchase'] != int(metric['purchase_events']) or c['purchase_amount'] != Decimal(metric['purchase_amount']): raise ValueError('published metric mismatch')
            if not metric['count_allowed'] or not metric['amount_allowed'] or c['purchase_amount_bad']: raise ValueError('candidate quality mismatch')
            if any(c[k] != old['behaviors'].get(k, 0) for k in ('view', 'cart', 'purchase')): raise ValueError('prior independent behavior evidence mismatch')
            dupe = duplicate.get(day, dict(groups=0, involved=0, excess=0, involved_amount=Decimal(0), excess_amount=Decimal(0)))
            row = dict(utc_date=day)
            for prefix, values in [('source',a), ('source_hash_selected',b), ('candidate',c)]:
                row.update({prefix+'_'+k:v for k,v in values.items()})
            row.update(metric_event_records=metric['event_records'], metric_purchase_events=metric['purchase_events'], metric_purchase_amount=metric['purchase_amount'],
                       prior_parsing_behavior_check='pass', exact_alignment='pass',
                       **{'candidate_duplicate_'+k:v for k,v in dupe.items()})
            reconciled.append(row)
        monthly, histories, flags = sensitivities(daily)
        old_flags = {r['utc_date']:r for r in csv.DictReader((prior/'anomaly_flags.csv').open())}
        for d, new in flags.items():
            if new['candidate'] != (old_flags[d]['candidate']=='True') or new['status'] != old_flags[d]['status']: raise ValueError('primary screening changed')
            for key in ('median_amount','score','relative_change'):
                value = serialized(new[key]); expected = old_flags[d][key]
                if (value is None and expected != '') or (value is not None and Decimal(value) != Decimal(expected)): raise ValueError('primary screening numerical mismatch')
        write_csv(stage/'daily_reconciliation.csv', reconciled)
        write_csv(stage/'hourly.csv', full.hourly('full_source')+selected_source.hourly('fixed_user_sample'))
        write_csv(stage/'monthly_sensitivity.csv', monthly)
        write_csv(stage/'history_sensitivity.csv', histories)
        if any(digest(ROOT/name) != sha for name,sha in evidence.items()): raise ValueError('prior evidence modified')
        if any([ (ROOT/name).stat().st_size,(ROOT/name).stat().st_mtime_ns] != meta for name,meta in input_stats.items()): raise ValueError('input modified')
        receipt = dict(status='passed', run_id=run_id, window_start_inclusive=START, window_end_exclusive=END,
                       source_scan=source_scan, candidate_scan=sample_scan, checks=dict(selected_fields_order_multiplicity='pass',
                       hourly_counts_amounts='pass', daily_metric_counts_amounts='pass', prior_behavior_counts='pass',
                       primary_screening_unchanged='pass', prior_evidence_unchanged='pass'), evidence=evidence,
                       outputs={p.name:digest(p) for p in stage.glob('*.csv')}, elapsed_seconds=round(time.monotonic()-started,3),
                       resources=dict(**budget(), free_before=free_before, peak_memory='not_measured'),
                       script_sha256=digest(Path(__file__)))
        write_json(stage/'validation.json', receipt); stage.rename(target/'complete')
        print(json.dumps(serialized(receipt), ensure_ascii=False), flush=True)
    except BaseException as exc:
        write_json(target/'failure.json', dict(status='failed', error=type(exc).__name__, message=str(exc), elapsed_seconds=round(time.monotonic()-started,3)))
        raise


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--run-id', required=True)
    run(parser.parse_args().run_id)
