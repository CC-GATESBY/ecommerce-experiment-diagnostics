"""Synthetic literal expectations; no real data or Spark required."""
import copy
import csv
from datetime import date, timedelta
from decimal import Decimal
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from scripts.review_purchase_timing import HEADER, scan, sensitivities, CFG, screen


def row(stamp, user='33', event='purchase', amount='1.20'):
    return [stamp, event, '1', '2', 'electronics.test', 'brand,"quoted"\nline', amount, user, '']


class TimingTests(unittest.TestCase):
    def make(self, directory, rows, name='synthetic.csv'):
        path=Path(directory)/name
        with path.open('w', newline='') as f:
            writer=csv.writer(f); writer.writerow(HEADER); writer.writerows(rows)
        return path, dict(bytes=path.stat().st_size, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), records=len(rows))

    def test_window_hash_alignment_and_duplicate_multiplicity(self):
        with tempfile.TemporaryDirectory() as directory:
            repeated=row('2019-11-14 00:00:00 UTC')
            rows=[row('2019-11-13 23:59:59 UTC'), repeated, repeated,
                  row('2019-11-15 01:00:00 UTC', event='view', amount='0.00'),
                  row('2019-11-18 23:59:59 UTC', user='1'), row('2019-11-19 00:00:00 UTC')]
            path, expected=self.make(directory, rows)
            full, chosen, receipt=scan(path, expected, source=True)
            self.assertEqual(receipt['window_records'],4)
            self.assertEqual(full.daily('2019-11-14')['purchase'],2)
            self.assertEqual(full.daily('2019-11-14')['purchase_amount'],Decimal('2.40'))
            self.assertEqual(chosen.daily('2019-11-18')['event_records'],0)
            candidate, exp=self.make(directory, [rows[i] for i in (0,1,2,3,5)], 'candidate.csv')
            with sqlite3.connect(':memory:') as db:
                db.execute('CREATE TABLE purchases(raw_fields TEXT PRIMARY KEY, day TEXT, cents INTEGER, n INTEGER) WITHOUT ROWID')
                sample, picked, _=scan(candidate, exp, source=False, db=db)
                self.assertEqual(db.execute('SELECT count(*),sum(n),sum(n-1),sum((n-1)*cents) FROM purchases WHERE n>1').fetchone(),(1,2,1,120))
            self.assertEqual(chosen.hourly('sample'),sample.hourly('sample'))
            self.assertEqual(chosen.sequence.hexdigest(),picked.sequence.hexdigest())
            self.assertEqual(sample.daily('2019-11-15')['purchase'],0)
            self.assertEqual(sample.daily('2019-11-15')['first_purchase_utc'],None)

    def test_read_failure_is_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            for rows in ([row('2019-11-15 00:00:00 UTC')[:-1]], [row('bad time')]):
                path, expected=self.make(directory, rows)
                with self.assertRaises(ValueError): scan(path, expected, source=True)
            path,expected=self.make(directory,[])
            self.assertEqual(scan(path, expected, source=True)[0].daily('2019-11-15')['purchase'],0)
            with self.assertRaises(FileNotFoundError): scan(Path(directory)/'missing',expected,source=True)
            expected['sha256']='wrong'
            with self.assertRaises(ValueError):scan(path,expected,source=True)

    def test_sensitivity_literal_means_and_no_primary_mutation(self):
        rows=[dict(utc_date=(date(2019,10,1)+timedelta(days=i)).isoformat(), purchase_amount='100.00', count_allowed=True,amount_allowed=True) for i in range(61)]
        by={r['utc_date']:r for r in rows}
        for day,value in [('2019-11-15','0.00'),('2019-11-16','300.00'),('2019-11-17','400.00'),('2019-11-22','90.00')]:by[day]['purchase_amount']=value
        before=copy.deepcopy(rows); month,hist,_=sensitivities(rows)
        self.assertEqual(rows,before)
        self.assertEqual(month[1]['purchase_amount'],Decimal('3390.00'))
        self.assertEqual(month[2]['purchase_amount'],Decimal('2690.00'))
        self.assertEqual(month[2]['days'],27)
        pair=[r for r in hist if r['utc_date']=='2019-11-22']
        self.assertEqual(pair[0]['mean_amount'],Decimal('75'))
        self.assertEqual(pair[0]['relative_to_mean'],Decimal('0.2'))
        self.assertEqual(pair[1]['mean_amount'],Decimal('100'))
        self.assertEqual(pair[1]['relative_to_mean'],Decimal('-0.1'))
        self.assertEqual({r['utc_date'] for r in hist},{'2019-11-22','2019-11-23','2019-11-24','2019-11-29','2019-11-30'})
        for r in hist:self.assertTrue(all(h<r['utc_date'] for h in r['history_dates']))
        by['2019-11-01']['amount_allowed']=False;by['2019-11-08']['amount_allowed']=False
        _,hist,_=sensitivities(rows[:31]+[r for r in rows[31:] if r['utc_date'] not in ('2019-11-01','2019-11-08')])
        blocked=next(r for r in hist if r['utc_date']=='2019-11-22' and 'posthoc' in r['branch'])
        self.assertEqual(blocked['history_count'],1);self.assertIsNone(blocked['mean_amount']);self.assertIsNone(blocked['median_amount'])

    def test_price_domain_and_unselected_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path,exp=self.make(directory,[row('2019-11-16 12:00:00 UTC',amount='NaN'),row('2019-11-16 13:00:00 UTC',amount='0')])
            observed=scan(path,exp,source=True)[0].daily('2019-11-16')
            self.assertEqual(observed['purchase'],2);self.assertEqual(observed['purchase_amount_bad'],1)
            self.assertEqual(observed['purchase_amount'],Decimal(0));self.assertEqual(observed['amount_status'],'partial_observed')
            path,exp=self.make(directory,[row('2019-11-15 00:00:00 UTC',user='1')])
            with self.assertRaises(ValueError):scan(path,exp,source=False)


if __name__=='__main__': unittest.main()
