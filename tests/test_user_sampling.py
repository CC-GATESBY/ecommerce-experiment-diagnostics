"""Independent synthetic fixtures; never scan real source data in tests."""

import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ingest.ingest import HEADER, ROOT, IngestError, sha256
from ingest.profile_and_sample import (DB_RESERVE, METADATA_RESERVE, Profile,
                                      execute, load_config, parse_time, selected)


def reference_select(user):
    if not user or user.isspace():
        return False
    n = int(hashlib.sha256(('rees46-user-sample-v1|20260916|' + user).encode('utf-8')).hexdigest()[:16], 16)
    return n < (5 * 2**64) // 100


class SyntheticUserSamplingTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / '.local/t04/synthetic-user-sampling-tests'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-', dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'synthetic.csv'
        self.yes = next(str(i) for i in range(1, 1000) if reference_select(str(i)))
        self.no = next(str(i) for i in range(1, 1000) if not reference_select(str(i)))
        self.odd = next(' synthetic,"\n' + str(i) for i in range(1000) if reference_select(' synthetic,"\n' + str(i)))
        self.zero = next('00' + str(i) for i in range(1000) if reference_select('00' + str(i)))
        def row(user, when='2019-10-01 00:00:00 UTC', event='view', price='0001.20'):
            return [when, event, 'synthetic', '1', 'synthetic,"quoted"\nmultiline', '', price, user, '']
        first = row(self.yes)
        self.rows = [first, row(self.no), row(self.yes, '2019-10-31 23:59:59 UTC', 'purchase', '-bad'),
                     list(first), row(''), row(' \t '), row(self.yes, 'bad time', 'other', ''),
                     row(self.yes, '2019-11-01 00:00:00 UTC'), row(self.odd, ''), row(self.zero)]
        self.expected = [self.rows[i] for i in [0, 2, 3, 6, 7, 8, 9]]
        self.write(self.rows)

    def write(self, rows, header=HEADER):
        with self.source.open('w', encoding='utf-8', newline='') as f:
            w = csv.writer(f, lineterminator='\r\n')
            w.writerow(header)
            w.writerows(rows)

    def run_fixture(self, name='one', **kwargs):
        return execute(self.source, sha256(self.source), self.root / ('stage-' + name),
                       self.root / ('final-' + name), progress_every=1000, **kwargs)

    def test_hash_uses_exact_original_string(self):
        ids = ['', ' ', '\t', '0', '007', '7', ' 7', '7 ', '１２３', 'synthetic', self.odd]
        ids += [str(i) for i in range(1000)]
        for user in ids:
            self.assertEqual(selected(user), reference_select(user), repr(user))
        self.assertNotEqual(hashlib.sha256(('rees46-user-sample-v1|20260916|007').encode()).hexdigest(),
                            hashlib.sha256(('rees46-user-sample-v1|20260916|7').encode()).hexdigest())

    def test_complete_source_profile_header_excluded_and_anomalies_counted(self):
        p = self.run_fixture()['source_scan']
        self.assertEqual(p['record_count'], 10)
        self.assertEqual(p['header'], HEADER)
        self.assertEqual(p['field_count_anomaly_records'], 0)
        self.assertEqual(p['time_missing_records'], 1)
        self.assertEqual(p['time_parse_failure_records'], 1)
        self.assertEqual(p['outside_expected_month_records'], 1)
        self.assertEqual(p['user_id_empty_records'], 1)
        self.assertEqual(p['user_id_whitespace_only_records'], 1)
        self.assertEqual(p['user_id_non_ascii_digit_string_records'], 1)
        self.assertEqual(p['user_id_leading_zero_records'], 1)
        self.assertEqual(p['distinct_user_count'], 'not_measured')
        self.assertEqual(p['daily_records'], {'2019-10-01': 6, '2019-10-31': 1, '2019-11-01': 1})
        self.assertEqual(len(p['expected_dates_without_records']), 29)

    def test_selected_users_keep_all_dates_duplicates_and_abnormal_fields(self):
        result = self.run_fixture()
        with (self.root / 'final-one/user_sample_candidate.csv').open(newline='') as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows, [HEADER] + self.expected)
        self.assertEqual(result['sample']['profile']['record_count'], 7)
        self.assertEqual(result['sample']['distinct_user_count'], 3)
        self.assertEqual(result['sample']['profile']['time_parse_failure_records'], 1)
        self.assertEqual(result['sample']['profile']['time_missing_records'], 1)
        self.assertEqual(result['sample']['actual_event_extraction_ratio'], 0.7)
        self.assertEqual(result['target_user_sampling_percent'], 5)
        self.assertEqual(result['kind'], 'user_sample_candidate')

    def test_missing_ids_excluded_nonselected_excluded(self):
        self.write([self.rows[1], self.rows[4], self.rows[5]])
        result = self.run_fixture()
        self.assertEqual(result['sample']['profile']['record_count'], 0)
        self.assertEqual(result['sample']['distinct_user_count'], 0)
        self.assertEqual(result['source_scan']['user_id_missing_or_unusable_records'], 2)
        self.assertEqual(result['source_dates_without_sample_records'], ['2019-10-01'])

    def test_cross_process_reproducibility_independent_python_hash_seed(self):
        script = "from ingest.profile_and_sample import execute; from ingest.ingest import sha256; import sys; execute(sys.argv[1],sha256(sys.argv[1]),sys.argv[2],sys.argv[3])"
        for name, seed in [('a', '11'), ('b', '987654')]:
            env = dict(os.environ, PYTHONHASHSEED=seed)
            result = subprocess.run([sys.executable, '-c', script, str(self.source),
                                     str(self.root / ('stage-' + name)), str(self.root / ('final-' + name))],
                                    cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        first = self.root / 'final-a/user_sample_candidate.csv'
        second = self.root / 'final-b/user_sample_candidate.csv'
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(sha256(first), sha256(second))
        with first.open(newline='') as f:
            self.assertEqual(list(csv.reader(f)), [HEADER] + self.expected)

    def test_existing_outputs_never_overwritten(self):
        self.run_fixture()
        output = self.root / 'final-one/user_sample_candidate.csv'
        before = sha256(output)
        with self.assertRaises(IngestError):
            self.run_fixture()
        self.assertEqual(sha256(output), before)
        (self.root / 'stage-other').mkdir()
        with self.assertRaises(FileExistsError):
            self.run_fixture('other')

    def test_wrong_source_hash_is_failed_not_complete(self):
        with self.assertRaises(IngestError):
            execute(self.source, '0' * 64, self.root / 'stage', self.root / 'final')
        failure = json.loads((self.root / 'stage/failure.json').read_text())
        self.assertFalse(failure['complete'])
        self.assertFalse((self.root / 'final').exists())

    def test_interrupt_retains_failure_and_partial_not_validated(self):
        with patch('ingest.profile_and_sample.Profile.observe', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_fixture()
        stage = self.root / 'stage-one'
        self.assertEqual(json.loads((stage / 'failure.json').read_text())['status'], 'failed')
        self.assertTrue((stage / 'user_sample_candidate.csv.part').exists())
        self.assertFalse((self.root / 'final-one/receipt.json').exists())

    def test_width_error_cannot_register_partial_statistics(self):
        self.write([self.rows[0], ['synthetic', 'wrong-width']])
        with self.assertRaises(IngestError):
            self.run_fixture()
        failure = json.loads((self.root / 'stage-one/failure.json').read_text())
        self.assertFalse(failure['complete'])
        self.assertEqual(failure['partial_source_profile']['record_count'], 1)
        self.assertEqual(failure['partial_source_profile']['field_count_anomaly_records'], 1)
        self.assertFalse((self.root / 'final-one').exists())

    def test_csv_parse_error_cannot_register_complete(self):
        with self.source.open('a') as f:
            f.write('"unclosed synthetic quote\n')
        with self.assertRaises(csv.Error):
            self.run_fixture()
        self.assertEqual(json.loads((self.root / 'stage-one/failure.json').read_text())['status'], 'failed')
        self.assertFalse((self.root / 'final-one').exists())

    def test_header_error_stops_before_data_records(self):
        self.write(self.rows, list(reversed(HEADER)))
        with self.assertRaises(IngestError):
            self.run_fixture()
        failure = json.loads((self.root / 'stage-one/failure.json').read_text())
        self.assertEqual(failure['partial_source_profile']['record_count'], 0)

    def test_budget_exhaustion_is_failure_not_truncation(self):
        with self.assertRaises(IngestError):
            self.run_fixture(max_new_bytes=DB_RESERVE + METADATA_RESERVE + 130)
        self.assertFalse((self.root / 'final-one').exists())
        self.assertFalse(json.loads((self.root / 'stage-one/failure.json').read_text())['complete'])

    def test_low_disk_stops_without_reading_source(self):
        from collections import namedtuple
        usage = namedtuple('usage', 'total used free')(200, 100, 100)
        with patch('ingest.profile_and_sample.shutil.disk_usage', return_value=usage):
            with self.assertRaises(IngestError):
                self.run_fixture()
        self.assertEqual(json.loads((self.root / 'stage-one/failure.json').read_text())['phase'], 'preflight')

    def test_invalid_time_not_silently_normalized(self):
        for text in ['2019-02-30 00:00:00 UTC', '2019-10-01 24:00:00 UTC',
                     ' 2019-10-01 00:00:00 UTC', '2019-10-01T00:00:00Z']:
            self.assertEqual(parse_time(text), ('invalid', None))
        self.assertEqual(parse_time(' \t '), ('missing', None))
        self.assertEqual(parse_time('2019-10-01 00:00:00 UTC'), ('valid', '2019-10-01T00:00:00+00:00'))

    def test_template_and_frozen_rule_changes_rejected(self):
        with self.assertRaises(IngestError):
            load_config(ROOT / 'config/user_sampling.example.json')
        with self.assertRaises(IngestError):
            load_config(self.root / 'missing.json')
        cfg = json.loads((ROOT / 'config/user_sampling.example.json').read_text())
        for key, value in [('seed', '42'), ('target_percent', 10), ('minimum_free_bytes', 0),
                           ('parent_sha256', '0' * 64), ('extra', 'synthetic')]:
            local = self.root / 'synthetic.local.json'
            local.write_text(json.dumps(dict(cfg, **{key: value})))
            with self.assertRaises(IngestError):
                load_config(local)


if __name__ == '__main__':
    unittest.main()
