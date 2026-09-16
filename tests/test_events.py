"""Synthetic fixtures only; no source/monthly candidate is opened by these tests."""

import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

import yaml
from etl.event_config import HEADER, load_events_config, sha256
from etl.oracle import build_expected, oracle_row
from scripts.project_config import ConfigError

ROOT = Path(__file__).resolve().parents[1]
BASE = ['2019-10-01 23:59:59 UTC', 'purchase', '0002', '0003', 'a.b', 'brand', '3.25', '001', 'session']


def row(**changes):
    values = dict(zip(HEADER, BASE)); values.update(changes)
    return [values[name] for name in HEADER]


def synthetic_rows():
    rows = [row(), row(), row(event_type='view'), row(event_time='2019-10-02 00:00:00 UTC', price='0')]
    rows += [row(event_time=value) for value in ['', 'bad', '2019-02-30 00:00:00 UTC', '0000-01-01 00:00:00 UTC', '2019-10-01 00:00:00 UTC ']]
    rows += [row(user_id=value) for value in ['', ' \t', ' 01', '1e3', '１２３']]
    rows += [row(event_type='mystery'), row(brand='', category_code='', user_session='', product_id='', category_id='bad')]
    rows += [row(price=value) for value in ['', 'bad', 'NaN', '-Infinity', '-1.20', '0.00', '10000000000000000.00', '1.001', '1.000', '-0.00', '+01.20', '1e3', ' 1.20', '9999999999999999.99', '00000000000000000000001.20']]
    rows += [row(brand='a,"b"\nc', category_code='', user_session='s,1'), row(event_type='remove_from_cart'),
             row(brand='null', category_code='NULL', user_session='__T11_RESERVED_NULL_7f0b79e9__'),
             row(brand='a\x00b', category_code=''), row(brand=' "a" ', category_code=' ') ]
    from test_event_boundaries import literal_cases, raw_row
    rows += [raw_row(field, value) for field, value, _ in literal_cases()]
    return rows


class OracleTests(unittest.TestCase):
    def expected(self, rows, raw=None):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'synthetic.csv'; destination = Path(tmp) / 'expected.jsonl'
            if raw is None:
                with source.open('w', newline='') as f:
                    writer = csv.writer(f); writer.writerow(HEADER); writer.writerows(rows)
            else:
                source.write_text(raw)
            return build_expected(source, destination, len(rows))

    def test_normal_strings_decimal_utc(self):
        actual = oracle_row(row())
        self.assertEqual(actual['user_id'], '001')
        self.assertEqual(actual['price_decimal'], '3.25')
        self.assertEqual(actual['event_timestamp_utc'], '2019-10-01T23:59:59+00:00')
        self.assertTrue(actual['amount_eligible'])

    def test_time_missing_and_invalid(self):
        self.assertTrue(oracle_row(row(event_time=''))['time_missing'])
        for value in ['bad', '2019-02-30 00:00:00 UTC', '0000-01-01 00:00:00 UTC']:
            self.assertTrue(oracle_row(row(event_time=value))['time_invalid'])

    def test_missing_and_invalid_identifiers(self):
        for value in ['', ' \t']:
            self.assertTrue(oracle_row(row(user_id=value))['user_id_missing'])
        for value in [' 01', '1e3', '１２３']:
            self.assertTrue(oracle_row(row(user_id=value))['user_id_invalid'])

    def test_unknown_behavior(self):
        actual = oracle_row(row(event_type='unknown'))
        self.assertTrue(actual['event_type_unknown']); self.assertFalse(actual['event_eligible'])

    def test_missing_dimensions_do_not_remove_eligible_event(self):
        actual = oracle_row(row(brand='', category_code='', user_session=''))
        self.assertTrue(actual['event_eligible'])
        for key in ('brand_missing', 'category_code_missing', 'session_missing'):
            self.assertTrue(actual[key])

    def test_price_missing_invalid_nonfinite_separate(self):
        for value, flag in [('', 'price_missing'), ('NaN', 'price_nonfinite'), ('-Inf', 'price_nonfinite'), ('1e3', 'price_invalid')]:
            actual = oracle_row(row(price=value))
            self.assertTrue(actual[flag]); self.assertIsNone(actual['price_decimal'])

    def test_price_negative_zero_and_leading_zeros(self):
        negative = oracle_row(row(price='-1.20'))
        self.assertTrue(negative['price_negative']); self.assertFalse(negative['amount_eligible'])
        zero = oracle_row(row(price='-0.00'))
        self.assertTrue(zero['price_zero']); self.assertTrue(zero['amount_eligible'])
        self.assertEqual(zero['price_decimal'], '0.00')
        self.assertEqual(oracle_row(row(price='000001.20'))['price_decimal'], '1.20')

    def test_precision_and_scale_never_round(self):
        for value, flag in [('10000000000000000.00', 'price_precision_exceeded'), ('1.001', 'price_scale_exceeded'), ('1.000', 'price_scale_exceeded')]:
            actual = oracle_row(row(price=value))
            self.assertTrue(actual[flag]); self.assertIsNone(actual['price_decimal'])

    def test_empty_amount_is_not_zero(self):
        unknown = self.expected([row(price='')])
        self.assertEqual(unknown['users'], 1); self.assertEqual(unknown['buyers'], 1)
        self.assertIsNone(unknown['purchase_amount']); self.assertEqual(unknown['amount_status'], 'unknown')

    def test_partial_complete_and_no_purchases(self):
        partial = self.expected([row(), row(price='')])
        self.assertEqual(partial['purchase_amount'], '3.25'); self.assertEqual(partial['amount_status'], 'partial_observed')
        self.assertEqual(self.expected([row()])['amount_status'], 'complete_observed')
        no = self.expected([row(event_type='view')])
        self.assertEqual(no['amount_status'], 'no_purchases'); self.assertEqual(no['purchase_amount'], '0.00')

    def test_duplicates_header_and_cross_utc_date(self):
        actual = self.expected([row(), row(), row(event_time='2019-10-02 00:00:00 UTC')])
        self.assertEqual(actual['record_count'], 3); self.assertEqual(actual['purchase_amount'], '9.75')
        self.assertEqual(actual['time_max'], '2019-10-02T00:00:00+00:00')

    def test_quotes_commas_empty_multiline(self):
        actual = self.expected([row(brand='"a",b\nc', category_code='')])
        self.assertEqual(actual['record_count'], 1); self.assertEqual(actual['flags']['category_code_missing'], 1)

    def test_field_width_under_and_over_fail(self):
        for values in [BASE[:-1], BASE + ['extra']]:
            with self.assertRaises(ValueError): self.expected([values])

    def test_unterminated_quote_fails(self):
        with self.assertRaises(csv.Error):
            self.expected([row()], raw=','.join(HEADER) + '\n"unterminated\n')

    def test_header_and_count_mismatch_fail(self):
        with self.assertRaises(ValueError): self.expected([row()], raw='wrong\n')
        with self.assertRaises(ValueError): self.expected([row()], raw=','.join(HEADER) + '\n')

    def test_literal_null_and_control_fields_preserved(self):
        actual = oracle_row(row(brand='null', category_code='a\x00b'))
        self.assertEqual(actual['brand'], 'null'); self.assertEqual(actual['category_code'], 'a\x00b')

    def test_unfilled_template_rejected(self):
        with self.assertRaises(ConfigError): load_events_config(ROOT / 'config/events.example.yaml', ROOT)


class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = ROOT / '.local/t11/synthetic' / ('tests-' + uuid.uuid4().hex[:12])
        cls.folder.mkdir(parents=True)
        cls.source = cls.folder / 'synthetic.csv'
        with cls.source.open('w', newline='') as stream:
            writer = csv.writer(stream); writer.writerow(HEADER)
            for index, values in enumerate(synthetic_rows()):
                # Exercise quoted empty fields as well as the default unquoted empties.
                if index == 15:
                    csv.writer(stream, quoting=csv.QUOTE_ALL).writerow(values)
                else:
                    writer.writerow(values)
        (cls.folder / 'outputs').mkdir()
        cls.data = dict(kind='synthetic', input_path=str(cls.source.relative_to(ROOT)), input_sha256=sha256(cls.source),
                        scope_id='synthetic_events', source_id='synthetic', expected_records=len(synthetic_rows()),
                        output_root=str((cls.folder / 'outputs').relative_to(ROOT)))
        cls.config = cls.folder / 'synthetic.local.yaml'; cls.config.write_text(yaml.safe_dump(cls.data))

    def launch(self, run_id, **kwargs):
        from scripts import run_events
        argv = ['run_events.py', '--config', str(self.config), '--runtime-config', str(ROOT / 'config/local.yaml'), '--run-id', run_id]
        with patch.object(sys, 'argv', argv):
            return run_events.main()

    def test_existing_run_is_not_overwritten(self):
        folder = self.folder / 'outputs/synthetic_events/existing'
        folder.mkdir(parents=True); marker = folder / 'marker'; marker.write_text('unchanged')
        self.assertEqual(self.launch('existing'), 1); self.assertEqual(marker.read_text(), 'unchanged')
        self.assertFalse((folder / 'launch.json').exists())

    def test_interrupt_and_parse_failure_never_publish(self):
        for name, error in [('interrupt', KeyboardInterrupt()), ('parsefail', ValueError('synthetic parse failure'))]:
            with patch('scripts.run_events.build_expected', side_effect=error):
                self.assertEqual(self.launch(name), 1)
            run = self.folder / 'outputs/synthetic_events' / name
            self.assertEqual(json.loads((run / 'launch.json').read_text())['status'], 'failed')
            self.assertFalse((run / 'complete').exists())

    def test_sha_and_scope_and_month_guard(self):
        for changes in [{'input_sha256': '0' * 64}, {'kind': 'user_sample_candidate'}, {'expected_records': 1001}]:
            candidate = self.folder / 'bad.local.yaml'; candidate.write_text(yaml.safe_dump(self.data | changes))
            with self.assertRaises(ConfigError): load_events_config(candidate, ROOT)

    def test_spark_synthetic_integration(self):
        # This test starts one bounded synthetic Spark run with the same launcher as real runs.
        self.assertEqual(self.launch('spark-synthetic'), 0)
        result = json.loads((self.folder / 'outputs/synthetic_events/spark-synthetic/complete/validation.json').read_text())
        self.assertTrue(result['spark_stopped']); self.assertEqual(result['status'], 'passed')
        self.assertTrue(all(item['pass'] for item in result['checks'].values()))
        self.assertEqual(result['summary']['record_count'], len(synthetic_rows()))
        print('Synthetic validation: ' + str(self.folder.relative_to(ROOT)), flush=True)


if __name__ == '__main__':
    unittest.main()
