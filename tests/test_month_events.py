"""Synthetic monthly authorization, bounded SQLite and daily-quality tests."""

import csv
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml
from etl import event_config as ec
from etl.oracle import build_expected
from etl.resource_budget import Budget
from scripts.project_config import ConfigError


class MonthlyOracleTests(unittest.TestCase):
    def test_daily_completeness_raw_users_duplicates_and_zeros(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'synthetic.csv'
            base = ['2019-10-01 00:00:00 UTC', 'view', '1', '2', '', '', '0', '01', '']
            rows = [base, base[:1] + ['purchase'] + base[2:6] + [''] + base[7:]]
            purchase = ['2019-10-02 00:00:00 UTC', 'purchase', '1', '2', '', '', '0', '01', '']
            paid = purchase.copy(); paid[6] = '1.20'; paid[7] = '2'
            invalid = paid.copy(); invalid[0] = ''; invalid[7] = 'X'
            rows += [purchase, paid, paid, invalid]
            with source.open('w', newline='') as stream:
                writer = csv.writer(stream); writer.writerow(ec.HEADER); writer.writerows(rows)
            result = build_expected(source, root / 'expected.jsonl', 6)
            days = json.loads((root / 'expected_daily.json').read_text())
            self.assertEqual((result['record_count'], result['raw_users'], result['users'], result['buyers']), (6,3,2,2))
            self.assertEqual(result['purchase_amount'], '2.40'); self.assertEqual(result['amount_status'], 'partial_observed')
            self.assertEqual(days['2019-10-01']['amount_status'], 'unknown')
            self.assertIsNone(days['2019-10-01']['purchase_amount'])
            self.assertEqual(days['2019-10-02']['amount_status'], 'complete_observed')
            self.assertEqual(days['__invalid_time__']['record_count'], 1)
            self.assertEqual(result['zero_by_behavior']['view'], 1)
            self.assertEqual(result['zero_by_behavior']['purchase'], 1)

    def test_sqlite_batch_boundary_and_binary_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'synthetic.csv'
            with source.open('w',newline='') as stream:
                writer=csv.writer(stream); writer.writerow(ec.HEADER)
                for index in range(4098):
                    writer.writerow(['2019-10-01 00:00:00 UTC','view','1','2','','','0','01' if index%2 else '1',''])
            result=build_expected(source,root/'expected.jsonl',4098)
            self.assertEqual(result['users'],2); self.assertEqual(result['record_count'],4098)
            with sqlite3.connect(root/'expected.sqlite3') as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM ids').fetchone()[0],4)

    def test_budget_failure_keeps_partial_and_no_daily_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); source=root/'synthetic.csv'
            with source.open('w',newline='') as stream:
                writer=csv.writer(stream); writer.writerow(ec.HEADER)
                for _ in range(10001): writer.writerow(['2019-10-01 00:00:00 UTC','view','1','2','','','0','1',''])
            def fail(): raise RuntimeError('budget exceeded')
            with self.assertRaises(RuntimeError): build_expected(source,root/'expected.jsonl',10001,budget_check=fail)
            self.assertFalse((root/'expected_daily.json').exists())
            self.assertTrue((root/'expected.jsonl').exists())

    def test_budget_tracks_cumulative_outputs_and_low_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'.local/t11').mkdir(parents=True)
            p=root/'budget.json'; p.write_text(json.dumps(dict(initial_bytes=10,max_new_bytes=20,minimum_free_bytes=150*1024**3)))
            budget=Budget(root,p)
            with patch('etl.resource_budget.directory_bytes',return_value=31):
                with self.assertRaises(RuntimeError): budget.check()
            with patch('etl.resource_budget.directory_bytes',return_value=10), patch('etl.resource_budget.shutil.disk_usage',return_value=SimpleNamespace(free=1)):
                with self.assertRaises(RuntimeError): budget.check()


class CandidateConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name); (self.root/'data').mkdir(); (self.root/'.local/t04').mkdir(parents=True); (self.root/'.local/t11/runs').mkdir(parents=True)
        self.source=self.root/'.local/t04/synthetic.csv'; self.source.write_text('synthetic fixture only\n')
        digest=ec.sha256(self.source); size=self.source.stat().st_size
        for name,value in [('MONTH_SHA',digest),('MONTH_BYTES',size),('MONTH_RECORDS',1)]:
            context=patch.object(ec,name,value); context.start(); self.addCleanup(context.stop)
        self.entry=dict(scope_id=ec.MONTH_SCOPE,kind='user_sample_candidate',status='validated',run_id='synthetic',registration_status='validated_input_candidate_not_business_accepted',sample=dict(local_relative_path='.local/t04/synthetic.csv',sha256=digest,bytes=size,profile=dict(record_count=1),profile_matches_extraction='pass',serialization_and_sha256='pass'))
        (self.source.parent/'receipt.json').write_text(json.dumps(self.entry))
        self.manifest=self.root/'data/manifest.json'; self.manifest.write_text(json.dumps({'user_sample_candidates':[self.entry]}))
        self.data=dict(kind='user_sample_candidate',input_path='.local/t04/synthetic.csv',input_sha256=digest,scope_id=ec.MONTH_SCOPE,source_id='rees46_multicategory_2019_oct',expected_records=1,output_root='.local/t11/runs')

    def load(self, **change):
        p=self.root/'synthetic.local.yaml'; p.write_text(yaml.safe_dump(self.data | change)); return ec.load_events_config(p,self.root)

    def test_matching_registration_receipt_and_bytes(self):
        self.assertEqual(self.load()['input_path'],self.source.resolve())

    def test_wrong_identity_and_unregistered_paths_rejected(self):
        for changes in [dict(input_sha256='0'*64),dict(scope_id='other'),dict(expected_records=2),dict(kind='synthetic'),dict(input_path='.local/t04/*.csv'),dict(source_id='criteo')]:
            with self.subTest(changes=changes), self.assertRaises((ConfigError,ValueError)): self.load(**changes)

    def test_missing_failed_or_mismatched_receipt_rejected(self):
        p=self.source.parent/'receipt.json'
        for changes in [dict(status='running'),dict(scope_id='other'),dict(kind='engineering_sample')]:
            p.write_text(json.dumps(self.entry | changes))
            with self.assertRaises(ConfigError): self.load()
        p.unlink()
        with self.assertRaises(ConfigError): self.load()

    def test_unregistered_candidate_and_wrong_size_rejected(self):
        self.manifest.write_text(json.dumps({'user_sample_candidates':[]}))
        with self.assertRaises(ConfigError): self.load()
        self.manifest.write_text(json.dumps({'user_sample_candidates':[self.entry]}))
        self.source.write_text('changed bytes')
        with self.assertRaises(ConfigError): self.load()


if __name__ == '__main__':
    unittest.main()
