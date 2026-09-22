"""Synthetic holdout application tests; no private source or cache access."""
from bisect import bisect_left
import csv
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb

from uplift.targeting import ROOT, evaluate, joint_table
from uplift.targeting_holdout import load_frozen, extract_test, apply_test, FROZEN_PATH
from uplift.split import row_id, assign, MEMBERSHIP_HEADER
from ingest.ingest_criteo_source import HEADER


def synthetic_cache(change_outcomes=False, change_treatment=False):
    c = duckdb.connect()
    c.execute('CREATE TABLE test_cache(row_id VARCHAR,f0 DOUBLE,f1 DOUBLE,treatment TINYINT,conversion TINYINT)')
    # Eighty records; the first feature includes both exact boundaries and all three bins.
    features = [10.0, 21.923943332541803, 23.0, 24.436236184073156, 26.0]
    data = [(f'synthetic-{i:03d}', features[i % 5], 10.0,
             i % 2 ^ int(change_treatment and i == 7), int(i % 4 == 0) ^ int(change_outcomes)) for i in range(80)]
    c.executemany('INSERT INTO test_cache VALUES (?,?,?,?,?)', data)
    return c, data


class HoldoutTests(unittest.TestCase):
    def test_load_is_frozen_not_training_and_rejects_mutation(self):
        with patch('uplift.targeting.train_rules', side_effect=AssertionError('training forbidden')) as train:
            frozen, cfg = load_frozen()
            c, _ = synthetic_cache()
            self.assertEqual(apply_test(c, frozen), 80)
            c.close()
            train.assert_not_called()
        self.assertEqual(frozen['boundaries']['f1'], [])
        self.assertEqual([g['incremental_rank'] for g in frozen['groups']], [1, 2, 3])
        self.assertEqual(cfg['bootstrap_repetitions'], 1000)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/FROZEN_PATH
            p.parent.mkdir(parents=True)
            p.write_text((ROOT/FROZEN_PATH).read_text()+' ')
            with self.assertRaisesRegex(ValueError, 'fingerprint'):
                load_frozen(Path(tmp))

    def test_labels_do_not_change_ranks_and_capacities(self):
        frozen, cfg = load_frozen()
        observed = []
        for cy, ct in ((False, False), (True, False), (False, True)):
            c, data = synthetic_cache(cy, ct)
            self.assertEqual(apply_test(c, frozen), 80)
            ranks = c.execute('SELECT * FROM selected_ranks ORDER BY row_id').fetchall()
            observed.append(ranks)
            columns = [x[0] for x in c.execute('DESCRIBE selected_ranks').fetchall()]
            self.assertNotIn('conversion', columns)
            self.assertNotIn('treatment', columns)
            key = lambda rid: hashlib.sha256(('target-v1|20260921|'+rid).encode()).hexdigest()
            expected_random = sorted(data, key=lambda x: (key(x[0]), x[0]))
            expected_target = sorted(data, key=lambda x: (bisect_left(frozen['boundaries']['f0'], x[1]), key(x[0]), x[0]))
            for name, expected in [('random', expected_random), ('response', expected_target), ('incremental', expected_target)]:
                actual = c.execute('SELECT row_id FROM selected_ranks ORDER BY rank_'+name).fetchall()
                self.assertEqual([x[0] for x in actual], [x[0] for x in expected])
                sets = [set(x[0] for x in c.execute('SELECT row_id FROM selected_ranks WHERE rank_'+name+'<=?', [k]).fetchall()) for k in [8, 16, 24, 40, 80]]
                self.assertEqual([len(s) for s in sets], [8, 16, 24, 40, 80])
                self.assertTrue(all(a <= b for a, b in zip(sets, sets[1:])))
            c.close()
        self.assertEqual(observed[0], observed[1])
        self.assertEqual(observed[0], observed[2])

    def test_primary_joint_difference_negative_and_empty(self):
        frozen, cfg = load_frozen()
        c, _ = synthetic_cache()
        n = apply_test(c, frozen)
        joint, specs = joint_table(c, n, cfg)
        a, diffs, draws = evaluate(joint, specs, dict(cfg, bootstrap_repetitions=200))
        full = [r for r in a if r['capacity_percent'] == 100]
        # Literal population: forty per arm; twenty conversions in control, zero in treatment.
        self.assertTrue(all([r['control_n'], r['treatment_n'], r['conversion_control'], r['conversion_treatment']] == [40, 40, 20, 0] for r in full))
        self.assertTrue(all(r['G'] == -5000 and r['interval_status'] == 'sparse_not_for_strong_inference' for r in full))
        primary = [r for r in diffs if r['role'] == 'primary']
        self.assertEqual(len(primary), 1)
        self.assertEqual(primary[0]['capacity_percent'], 30)
        lookup = {r['rule']: r for r in a if r['capacity_percent'] == 30}
        self.assertEqual(primary[0]['G_difference'], lookup['INCREMENTAL']['G']-lookup['RANDOM']['G'])
        self.assertTrue(all(r['G_difference'] == 0 and r['ci95_low'] == 0 and r['ci95_high'] == 0 for r in diffs if r['capacity_percent'] == 100 or r['contrast'] == 'INCREMENTAL_minus_RESPONSE'))
        # Keep the zero arm, rather than inventing an epsilon denominator.
        for row in joint:
            if row['treatment'] == 0:
                row['n'] = 0
        for spec in specs:
            spec['selected_n'] = sum(r['n'] for r in joint if r['mask'] & (1 << spec['bit']))
        empty, _, _ = evaluate(joint, specs, dict(cfg, bootstrap_repetitions=20))
        self.assertTrue(all(r['G'] is None and r['bootstrap_valid'] == 0 for r in empty))
        c.close()

    def test_extract_only_original_test_with_logical_alignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            source_sha = 'a'*64
            expected_ids = []
            with (p/'synthetic.csv').open('w', newline='') as f, gzip.open(p/'membership.gz', 'wb') as m:
                writer = csv.writer(f)
                writer.writerow(HEADER)
                m.write(MEMBERSHIP_HEADER)
                for i in range(80):
                    identity = row_id(source_sha, i)
                    arm = str(i % 2)
                    split = assign(identity, arm)
                    values = ['10', '11']+['synthetic,quote\nvalue']*10+[arm, '0', 'not_used', 'not_used']
                    if split == 'test':
                        expected_ids.append(identity)
                    else:
                        values[0] = 'DO_NOT_PARSE_OTHER_SPLIT'
                        values[13] = 'DO_NOT_ANALYZE_OTHER_SPLIT'
                    writer.writerow(values)
                    m.write(f'{i}\t{identity}\t{arm}\t{split}\n'.encode())
            meta = extract_test(p/'synthetic.csv', p/'membership.gz', source_sha, p/'test.tsv')
            self.assertEqual(meta['scanned_records'], 80)
            self.assertGreater(len(expected_ids), 0)
            with (p/'test.tsv').open() as f:
                reader = csv.DictReader(f, delimiter='\t')
                rows = list(reader)
                self.assertEqual(reader.fieldnames, ['row_id', 'f0', 'f1', 'treatment', 'conversion'])
            self.assertEqual([r['row_id'] for r in rows], expected_ids)
            digest = hashlib.sha256(''.join(x+'\n' for x in expected_ids).encode()).hexdigest()
            self.assertEqual(meta['sequence_sha256']['test'], digest)
            self.assertNotIn('DO_NOT_', (p/'test.tsv').read_text())
            with self.assertRaises(FileExistsError):
                extract_test(p/'synthetic.csv', p/'membership.gz', source_sha, p/'test.tsv')
            with gzip.open(p/'membership.gz', 'ab') as m:
                m.write(b'extra\n')
            with self.assertRaisesRegex(ValueError, 'extra membership'):
                extract_test(p/'synthetic.csv', p/'membership.gz', source_sha, p/'invalid.tsv')


if __name__ == '__main__':
    unittest.main()
