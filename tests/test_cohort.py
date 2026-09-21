"""Small synthetic user-day fixtures with independent literal expectations."""
from datetime import datetime
from decimal import Decimal
import hashlib
from pathlib import Path
import tempfile
import unittest
import duckdb
from scripts.build_cohort import DAYS, build, summary, validate, export, scalar


def gates(blocked=None):
    return [dict(utc_date=d,scope_id='synthetic',count_allowed=True,amount_allowed=d!=blocked) for d in DAYS]


def connection(events, blocked=None):
    c=duckdb.connect(config={'threads':'1','memory_limit':'128MB'})
    c.execute('CREATE TABLE events(utc_date DATE,user_id VARCHAR,event_type VARCHAR,amount DECIMAL(38,2))')
    # Datetimes are explicitly UTC. No production cohort or price parser is used.
    c.executemany('INSERT INTO events VALUES (?,?,?,?)',[(datetime.fromisoformat(t.replace('Z','+00:00')).date(),u,k,a) for t,u,k,a in events])
    c.execute("""CREATE TABLE user_daily AS SELECT 'synthetic' AS scope_id,utc_date,user_id,
       count(*)::BIGINT AS event_records,count_if(event_type='purchase')::BIGINT AS purchase_events,
       count_if(event_type='purchase' AND amount IS NULL)::BIGINT AS purchase_amount_bad,
       count_if(event_type='purchase' AND amount IS NOT NULL)::BIGINT AS purchase_amount_valid,
       CASE WHEN utc_date IS NOT DISTINCT FROM ?::DATE THEN NULL ELSE
       sum(CASE WHEN event_type='purchase' THEN amount ELSE 0.00 END) END::DECIMAL(38,2) AS purchase_amount,
       TRUE AS count_allowed,utc_date IS DISTINCT FROM ?::DATE AS amount_allowed
       FROM events GROUP BY utc_date,user_id""",[blocked,blocked])
    return c


class CohortTests(unittest.TestCase):
    def test_fixed_membership_denominators_boundaries_and_roundtrip(self):
        events=[('2019-10-01T00:00:00Z','A','view','0'),
                ('2019-10-01T00:00:01Z','A','view','0'),
                ('2019-10-14T23:59:59Z','B','view','0'),
                ('2019-10-02T10:00:00Z','C','purchase','5.00'),
                ('2019-10-15T00:00:00Z','A','purchase','10.00'),
                ('2019-10-15T00:00:00Z','A','purchase','10.00'),
                ('2019-10-28T23:59:59Z','B','view','0'),
                ('2019-10-15T00:00:00Z','D','purchase','999'),
                ('2019-09-30T23:59:59Z','E','view','0'),
                ('2019-10-15T00:00:00Z','E','view','0'),
                ('2019-10-29T00:00:00Z','C','purchase','300'),
                ('2019-10-29T00:00:00Z','F','purchase','400')]
        c=connection(events)
        try:
            build(c,'synthetic',gates());validate(c);s=summary(c)
            self.assertEqual(c.execute('SELECT user_id FROM cohort ORDER BY user_id').fetchall(),[('A',),('B',),('C',)])
            self.assertEqual([s[k] for k in ('enrolled_users','returned_users','not_returned_users','post_buyers','post_purchase_events','post_only_users')],[3,2,1,1,2,2])
            self.assertEqual(s['cohort_buyer_rate'],Decimal(1)/3)
            self.assertEqual(s['returned_buyer_rate'],Decimal('0.5'))
            self.assertEqual(s['post_purchase_amount'],Decimal('20.00'))
            self.assertEqual(c.execute("SELECT pre_event_records,pre_converted,post_active,post_converted,post_purchase_events,post_purchase_amount,post_amount_status FROM cohort WHERE user_id='C'").fetchone(),(1,1,0,0,0,Decimal('0.00'),'no_purchases'))
            expected=hashlib.sha256(b'rees46-cohort-key-v1|9:synthetic1:A').hexdigest()
            self.assertEqual(scalar(c,"SELECT cohort_key FROM cohort WHERE user_id='A'"),expected)
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'first';export(c,path)
                before=(path/'values.parquet').read_bytes()
                with self.assertRaises(FileExistsError):export(c,path)
                self.assertEqual(before,(path/'values.parquet').read_bytes())
                self.assertNotIn('user_id',[x[0] for x in c.execute('DESCRIBE read_values').fetchall()])
                # Outcome modifications leave membership and stable keys unchanged.
                other=connection(events+[('2019-10-20T00:00:00Z','C','purchase','800')])
                try:
                    build(other,'synthetic',gates())
                    self.assertEqual(c.execute('SELECT cohort_key,user_id FROM cohort ORDER BY user_id').fetchall(),other.execute('SELECT cohort_key,user_id FROM cohort ORDER BY user_id').fetchall())
                finally:other.close()
        finally:c.close()

    def test_unknown_amount_preserves_buyers_and_blocks_window(self):
        c=connection([('2019-10-01T00:00:00Z','A','view','0'),
                      ('2019-10-01T00:00:00Z','B','view','0'),
                      ('2019-10-16T00:00:00Z','A','purchase',None)],'2019-10-16')
        try:
            build(c,'synthetic',gates('2019-10-16'));validate(c);s=summary(c)
            self.assertEqual((s['enrolled_users'],s['post_buyers'],s['returned_users']),(2,1,1))
            self.assertIsNone(s['post_purchase_amount']);self.assertEqual(s['amount_unknown_users'],2)
            self.assertEqual(c.execute('SELECT user_id,post_amount_status,post_purchase_amount FROM cohort ORDER BY user_id').fetchall(),[('A','unknown',None),('B','window_amount_blocked',None)])
        finally:c.close()

    def test_missing_or_blocked_date_rejected_and_zero_return(self):
        events=[('2019-10-01T00:00:00Z','A','view','0')]
        for bad in (gates()[:-1],gates()+[gates()[0]],
                    [dict(g,count_allowed=False) if g['utc_date']=='2019-10-16' else g for g in gates()]):
            c=connection(events)
            try:
                with self.assertRaises(ValueError):build(c,'synthetic',bad)
            finally:c.close()
        c=connection(events)
        try:
            build(c,'synthetic',gates());validate(c);s=summary(c)
            self.assertEqual(s['cohort_buyer_rate'],Decimal(0))
            self.assertIsNone(s['returned_buyer_rate']);self.assertIsNone(s['difference_percentage_points'])
            self.assertEqual(s['post_purchase_amount'],Decimal('0.00'))
        finally:c.close()

    def test_partial_amount_and_duplicate_user_day(self):
        events=[('2019-10-01T00:00:00Z','A','purchase','3.00'),
                ('2019-10-01T00:00:00Z','A','purchase',None),
                ('2019-10-16T00:00:00Z','A','view','0')]
        c=connection(events,'2019-10-01')
        try:
            build(c,'synthetic',gates('2019-10-01'));validate(c)
            self.assertEqual(c.execute('SELECT pre_converted,pre_purchase_events,pre_purchase_amount,pre_amount_status,post_purchase_amount FROM cohort').fetchone(),
                             (1,2,None,'partial_observed',Decimal('0.00')))
        finally:c.close()
        c=connection(events,'2019-10-01')
        try:
            c.execute('INSERT INTO user_daily SELECT * FROM user_daily LIMIT 1')
            with self.assertRaisesRegex(ValueError,'duplicate user-day'):build(c,'synthetic',gates('2019-10-01'))
        finally:c.close()


if __name__=='__main__':unittest.main()
