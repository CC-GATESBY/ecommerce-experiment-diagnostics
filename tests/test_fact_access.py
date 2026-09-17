"""Literal policy expectations and <= 100 isolated synthetic integration rows."""

from copy import deepcopy
import csv
import importlib
import json
from pathlib import Path
from unittest.mock import patch
import unittest

from etl.date_quality import evaluate
from etl.event_config import CONTRACT, DERIVED, FLAGS, HEADER, sha256
from etl.fact_registry import FactAccessError, FactReader, inspect_batch, load_registry, register_batch
from etl.oracle import build_expected

IDENTITY = dict(source_id='synthetic_source', scope_id='synthetic_scope', input_sha256='a' * 64,
                contract_version=CONTRACT, source_run='synthetic_run')


def good_day():
    return dict(record_count=2, flags={**dict.fromkeys(FLAGS, 0), 'event_eligible': 2, 'amount_eligible': 1},
                behaviors={'view': 1, 'purchase': 1}, zero_by_behavior={}, purchase_events=1,
                purchase_price_bad_all=0, purchase_price_bad_eligible=0,
                purchase_amount='2.50', amount_status='complete_observed')


class DatePolicyTests(unittest.TestCase):
    def gate(self, day, valid=True):
        return evaluate(IDENTITY, {'2019-10-01': day}, ['2019-10-01'], valid)['2019-10-01']

    def test_good_both_purposes(self):
        gate = self.gate(good_day()); self.assertTrue(gate['count_allowed']); self.assertTrue(gate['amount_allowed'])

    def test_missing_date_is_not_zero(self):
        g = evaluate(IDENTITY, {}, ['2019-10-01'])['2019-10-01']
        self.assertFalse(g['count_allowed']); self.assertFalse(g['amount_allowed']); self.assertIn('date_not_observed', g['reason_codes'])

    def test_partial_and_unknown_amount_block_only_amount(self):
        for status in ('partial_observed', 'unknown'):
            day = good_day(); day.update(amount_status=status, purchase_price_bad_all=1, purchase_price_bad_eligible=1)
            g = self.gate(day); self.assertTrue(g['count_allowed']); self.assertFalse(g['amount_allowed'])

    def test_each_core_error_blocks(self):
        for key in ('time_missing', 'time_invalid', 'user_id_missing', 'user_id_invalid', 'event_type_unknown'):
            day = good_day(); day['flags'][key] = 1
            g = self.gate(day); self.assertFalse(g['count_allowed']); self.assertFalse(g['amount_allowed'])

    def test_dimension_warning_only(self):
        day = good_day(); day['flags'].update(brand_missing=1, category_code_missing=1, session_missing=1)
        g = self.gate(day); self.assertTrue(g['amount_allowed']); self.assertEqual(len(g['warnings']), 3)

    def test_no_purchase_requires_count_and_behavior_consistency(self):
        day = good_day(); day.update(purchase_events=0, behaviors={'view': 2}, purchase_amount='0.00', amount_status='no_purchases')
        day['flags']['amount_eligible'] = 0
        self.assertTrue(self.gate(day)['amount_allowed'])
        day['behaviors']['purchase'] = 1
        self.assertFalse(self.gate(day)['amount_allowed'])

    def test_nonpurchase_zero_and_purchase_zero_do_not_block(self):
        day = good_day(); day['zero_by_behavior'] = {'view': 1, 'purchase': 1}
        self.assertTrue(self.gate(day)['amount_allowed'])

    def test_unassigned_time_blocks_all_dates(self):
        day = good_day(); bad = good_day(); bad['flags']['time_invalid'] = 1
        gates = evaluate(IDENTITY, {'2019-10-01': day, '__invalid_time__': bad}, ['2019-10-01'])
        self.assertFalse(gates['2019-10-01']['count_allowed'])

    def test_failed_evidence_blocks(self):
        self.assertFalse(self.gate(good_day(), False)['count_allowed'])


def run_synthetic(spark, root, workspace):
    """Every read test calls the production API; fixture results have literal expectations."""
    from pyspark.sql import functions as F, types as T
    events = importlib.import_module('etl.01_events')
    root = Path(root).resolve(); workspace = Path(workspace).resolve(); workspace.mkdir(parents=True, exist_ok=False)
    checks = {}; created_rows = 0

    def check(name, expected, actual):
        checks[name] = dict(expected=expected, actual=actual, pass_=expected == actual)
        checks[name]['pass'] = checks[name].pop('pass_')
        if expected != actual:
            raise AssertionError(name + ': ' + str(actual))

    def rejects(name, action):
        try:
            action()
        except (FactAccessError, FileNotFoundError):
            check(name, 'rejected', 'rejected')
        else:
            check(name, 'rejected', 'accepted')

    def row(day, behavior='view', user='1', price='1.00', **changes):
        value = dict(zip(HEADER, [day + ' 12:00:00 UTC', behavior, '1', '2', 'a.b', 'brand', price, user, 'session']))
        value.update(changes); return [value[k] for k in HEADER]

    def batch(run_id, scope, rows, dates, series='synthetic_fixed_users', duplicate_input=None):
        nonlocal created_rows
        created_rows += len(rows)
        check('synthetic_record_budget', True, created_rows <= 100)
        run = workspace / run_id; run.mkdir(); stage = run / 'staging'; stage.mkdir()
        source = run / 'synthetic.csv'
        with source.open('x', newline='') as stream:
            writer = csv.writer(stream, lineterminator='\n'); writer.writerow(HEADER); writer.writerows(rows)
        digest = sha256(source)
        if duplicate_input:
            check('rerun_input_identical', duplicate_input, digest)
        d = dict(source_id='synthetic_rees46_fixture', scope_id=scope, input_sha256=digest,
                 contract_version=CONTRACT, kind='synthetic', run_id=run_id,
                 run_path=str(run.relative_to(root)), expected_records=len(rows), dates=dates,
                 series_id=series, sampling_rule='synthetic_fixed-user-fixture-v1|literal-users')
        expected = build_expected(source, stage / 'expected_rows.jsonl', len(rows))
        expected_daily = json.loads((stage / 'expected_daily.json').read_text())
        raw = spark.createDataFrame(rows, T.StructType([T.StructField(k, T.StringType()) for k in HEADER]))
        fact = events.transform(raw, d, run_id)
        fact.write.mode('errorifexists').parquet(str(stage / 'fact_events'))
        actual = spark.read.parquet(str(stage / 'fact_events'))
        proof_checks = {}
        def proof(name, want, got):
            proof_checks[name] = dict(expected=want, actual=got, pass_=want == got)
            proof_checks[name]['pass'] = proof_checks[name].pop('pass_')
            if want != got:
                raise AssertionError(run_id + ':' + name)
        proof('schema', events.schema().simpleString(), actual.schema.simpleString())
        proof('rows', len(rows), actual.count())
        schema = T.StructType([T.StructField(k, T.StringType()) for k in HEADER + DERIVED]
                              + [T.StructField(k, T.BooleanType()) for k in FLAGS])
        oracle = spark.read.schema(schema).json(str(stage / 'expected_rows.jsonl'))
        canonical = events.canonical(actual).withColumn('event_timestamp_utc', F.regexp_replace('event_timestamp_utc', 'Z$', '+00:00'))
        proof('expected_minus_actual_multiset', 0, oracle.exceptAll(canonical).count())
        proof('actual_minus_expected_multiset', 0, canonical.exceptAll(oracle).count())
        actual_summary = events.summary(actual); actual_daily = events.daily_summary(actual)
        for key, value in expected.items():
            proof('summary_' + key, value, actual_summary[key])
        proof('daily_bucket_keys', sorted(expected_daily), sorted(actual_daily))
        for day, values in expected_daily.items():
            proof('daily_' + day, values, actual_daily[day])
        proof('input_sha256_after', digest, sha256(source))
        # Synthetic batches share this session; mark them complete only after successful materialized verification.
        validation = dict(status='passed', spark_stopped=False, contract_version=CONTRACT, checks=proof_checks,
                          schema=actual.schema.jsonValue(), summary=actual_summary, daily_summary=actual_daily,
                          synthetic_shared_session=True)
        # The outer integration receipt records the eventual real JVM stop.
        validation['completion_mode'] = 'synthetic_no_active_writer_shared_test_session'
        (stage / 'validation.json').write_text(json.dumps(validation, indent=2))
        stage.rename(run / 'complete')
        (run / 'launch.json').write_text(json.dumps({**d, 'status': 'passed'}, indent=2))
        check(run_id + '_independent_full_multiset_and_summary', True, all(v['pass'] for v in proof_checks.values()))
        print(json.dumps({'phase': 'synthetic_batch_verified', 'run_id': run_id, 'created_records': created_rows}), flush=True)
        return d

    october = [row('2019-10-01', price='0', brand='', category_code=''), row('2019-10-01', 'purchase', price='2.50'), row('2019-10-01', user='2'),
               row('2019-10-02', user='3', price='0'), row('2019-10-02', 'cart', user='3', price='0'),
               row('2019-10-03', user='4'), row('2019-10-03', 'purchase', '4', ''),
               row('2019-10-04', 'purchase', '5', '2'), row('2019-10-04', 'purchase', '6', 'bad'), row('2019-10-04', user='6', price='0'),
               row('2019-10-05', user=''), row('2019-10-06', 'mystery', '7'), row('2019-10-07', 'purchase', '8', '0'),
               row('2019-10-08', user='9', price='bad', user_session='')]
    oct_dates = [f'2019-10-{day:02d}' for day in range(1, 10)]
    oct_batch = batch('oct-01', 'synthetic_oct', october, oct_dates)
    registry = workspace / 'registry.json'
    check('A_register_october', 'registered', register_batch(root, registry, oct_batch)['status'])
    october_hashes = {str(p): sha256(p) for p in (workspace / 'oct-01').rglob('*') if p.is_file()}
    def read_count(reader, dates, purpose='count', scopes=None):
        return reader.read(dates, purpose, expected_scopes=scopes or ['synthetic_oct']).count()
    with FactReader(spark, root, registry, 'synthetic_fixed_users') as reader:
        check('A_october_count', 3, read_count(reader, ['2019-10-01']))
        amount = reader.read(['2019-10-01'], 'amount', expected_scopes=['synthetic_oct'])
        check('amount_preserves_denominator', [3, 1], [amount.count(), amount.where('amount_eligible').count()])
        check('dimension_missing_allowed', 3, read_count(reader, ['2019-10-01'], 'amount'))
        for day, count in [('2019-10-03', 2), ('2019-10-04', 3)]:
            check('bad_amount_keeps_count_' + day, count, read_count(reader, [day]))
            rejects('F_bad_amount_refused_' + day, lambda day=day: read_count(reader, [day], 'amount'))
        for day in ('2019-10-05', '2019-10-06', '2019-10-09', '2019-10-10'):
            for purpose in ('count', 'amount'):
                rejects('core_or_missing_refused_' + day + '_' + purpose, lambda day=day, purpose=purpose: read_count(reader, [day], purpose))
        rejects('mixed_request_not_silently_skipped', lambda: read_count(reader, ['2019-10-01', '2019-10-05']))
        check('no_purchases_structural_zero', 2, read_count(reader, ['2019-10-02'], 'amount'))
        check('zero_purchase_is_valid', 1, read_count(reader, ['2019-10-07'], 'amount'))
        check('nonpurchase_bad_price_session_warning_only', 1, read_count(reader, ['2019-10-08'], 'amount'))
        rejects('scope_mismatch_read', lambda: read_count(reader, ['2019-10-01'], scopes=['synthetic_wrong']))
        rejects('unsupported_purpose_read', lambda: read_count(reader, ['2019-10-01'], 'metrics'))
        nov = batch('nov-01', 'synthetic_nov', [row('2019-11-01'), row('2019-11-01', 'purchase', price='3'), row('2019-11-01', user='2', price='0')], ['2019-11-01'])
        check('B_append_november', 'registered', register_batch(root, registry, nov)['status'])
        check('B_october_query_unchanged', 3, read_count(reader, ['2019-10-01']))
        check('B_combined_same_series_only_adds_november', 6, read_count(reader, ['2019-10-01', '2019-11-01'], 'amount', ['synthetic_oct', 'synthetic_nov']))
        check('B_october_files_unchanged', october_hashes, {str(p): sha256(p) for p in (workspace / 'oct-01').rglob('*') if p.is_file()})
        check('C_repeat_registration', 'already_registered', register_batch(root, registry, oct_batch)['status'])
        replay = batch('nov-02', 'synthetic_nov', [row('2019-11-01'), row('2019-11-01', 'purchase', price='3'), row('2019-11-01', user='2', price='0')], ['2019-11-01'], duplicate_input=nov['input_sha256'])
        check('C_changed_run_id', {'status': 'already_registered', 'selected_run': 'nov-01'}, register_batch(root, registry, replay))
        check('C_still_two_batches', 2, len(load_registry(root, registry)['batches']))
        check('C_no_double_count', 6, read_count(reader, ['2019-10-01', '2019-11-01'], scopes=['synthetic_oct', 'synthetic_nov']))
        overlap = batch('overlap', 'synthetic_overlap', [row('2019-10-01', price='4')], ['2019-10-01'])
        rejects('D_date_overlap', lambda: register_batch(root, registry, overlap))
        shifted = {**nov, 'scope_id': 'synthetic_wrong'}
        rejects('receipt_scope_mismatch', lambda: register_batch(root, registry, shifted))
        rejects('receipt_row_count_mismatch', lambda: register_batch(root, registry, {**nov, 'expected_records': 4}))
        partial = {**nov, 'run_id': 'partial', 'run_path': str((workspace / 'partial').relative_to(root))}
        (workspace / 'partial/staging').mkdir(parents=True)
        (workspace / 'partial/staging/FAILED.json').write_text('{"status":"simulated_failure_before_publication"}')
        before = sha256(registry)
        rejects('E_incomplete_not_registered', lambda: register_batch(root, registry, partial))
        check('E_registry_unchanged', before, sha256(registry))
        rejects('E_partial_scope_not_readable', lambda: read_count(reader, ['2019-11-01'], scopes=['synthetic_partial']))
        check('E_old_batch_readable', 3, read_count(reader, ['2019-10-01']))
        fresh = batch('nov-pending', 'synthetic_nov_pending', [row('2019-11-02')], ['2019-11-02'])
        try:
            with patch('etl.fact_registry.os.replace', side_effect=OSError('simulated pre-commit failure')):
                register_batch(root, registry, fresh)
        except OSError:
            check('E_atomic_registration_failure', 'retained_old_registry', 'retained_old_registry')
        else:
            raise AssertionError('expected simulated registration failure')
        check('E_atomic_registry_unchanged', before, sha256(registry))
        check('E_after_atomic_failure_old_readable', 3, read_count(reader, ['2019-10-01']))
        # Tamper only the registry pointer metadata; the immutable fixture facts/receipts remain unchanged.
        original = registry.read_text(); altered = json.loads(original)
        altered['batches'][0]['evidence'][str((workspace / 'oct-01/complete/validation.json').relative_to(root))] = '0' * 64
        registry.write_text(json.dumps(altered))
        rejects('changed_evidence_read_rejected', lambda: read_count(reader, ['2019-10-01']))
        registry.write_text(original)
        altered = json.loads(original); altered['batches'].append(deepcopy(altered['batches'][0]))
        registry.write_text(json.dumps(altered))
        rejects('duplicate_registry_corruption_rejected', lambda: read_count(reader, ['2019-10-01']))
        registry.write_text(original)
        altered = json.loads(original); altered['batches'][0]['inventory'][0]['sha256'] = '0' * 64
        registry.write_text(json.dumps(altered))
        rejects('file_fingerprint_mismatch_rejected', lambda: read_count(reader, ['2019-10-01']))
        registry.write_text(original)
    bad_time = batch('bad-time', 'synthetic_bad_time', [row('2019-10-01'), row('2019-10-01', event_time='bad')], ['2019-10-01'], 'synthetic_time_series')
    register_batch(root, registry, bad_time)
    with FactReader(spark, root, registry, 'synthetic_time_series') as reader:
        rejects('unassigned_bad_time_blocks_valid_date', lambda: read_count(reader, ['2019-10-01'], scopes=['synthetic_bad_time']))
    with FactReader(spark, root, registry, 'synthetic_unregistered') as reader:
        rejects('unregistered_series_rejected', lambda: read_count(reader, ['2019-10-01']))
    return dict(status='passed', checks=checks, synthetic_records_created=created_rows,
                synthetic_only=True, series='synthetic_fixed_users', no_concurrent_transaction_claim=True)


if __name__ == '__main__':
    unittest.main()
