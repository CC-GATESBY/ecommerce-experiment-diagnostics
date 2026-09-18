"""Small literal fixtures for the November extension; no real rows."""
import csv
from datetime import date
from decimal import Decimal
from fractions import Fraction
import gzip
import json
from pathlib import Path
import tempfile
import unittest

import duckdb
from anomaly.diagnose import screen
from etl.oracle import build_expected
from etl.date_quality import evaluate
from etl.event_config import HEADER,CONTRACT
from ingest.ingest import extract_gzip,IngestError
from ingest.profile_and_sample import Profile,selected
from scripts.review_cross_period import parse,canonical_check,build,compare_categories,validate_categories

CFG={'history_offsets_days':[7,14,21,28],'min_history_points':3,'mad_scale':'1.4826','score_abs_gt':'3','relative_change_abs_gte':'0.10'}

class CrossPeriod(unittest.TestCase):
 def test_month_window_and_fixed_hash(self):
  # User-key selection never sees month, date, purchase or October membership.
  octp=Profile();novp=Profile('2019-11-01T00:00:00+00:00','2019-12-01T00:00:00+00:00')
  for p,t in [(octp,'2019-10-01'),(novp,'2019-11-30')]:
   p.observe([t+' 12:00:00 UTC','view','1','2','','','0','1000',''])
   self.assertEqual(p.summary()['outside_expected_month_records'],0)
  self.assertEqual(len(novp.summary()['expected_dates_without_records']),29)
  self.assertTrue(selected('1034'))
  self.assertFalse(selected('1000'))
  import hashlib
  for user in ['1000','1001','001001','new_november_id',' ','']:
   literal=bool(user and not user.isspace()) and int(hashlib.sha256(('rees46-user-sample-v1|20260916|'+user).encode()).hexdigest()[:16],16)<922337203685477580
   self.assertEqual(selected(user),literal)
  # A November-only ID is admitted without consulting an October user list.
  from ingest.profile_and_sample import scan,OutputBudget
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'source.csv';output=root/'sample.csv'
   with source.open('w',newline='') as f:
    w=csv.writer(f,lineterminator='\n');w.writerow(HEADER)
    for d,u in [('2019-11-01','1034'),('2019-11-30','1034'),('2019-11-30','1000')]:
     w.writerow([d+' 12:00:00 UTC','view','1','2','','','0',u,''])
   a,b=Profile('2019-11-01T00:00:00+00:00','2019-12-01T00:00:00+00:00'),Profile('2019-11-01T00:00:00+00:00','2019-12-01T00:00:00+00:00')
   import time
   scan(source,output,a,b,OutputBudget(root,512*1024**2,0),100,time.monotonic())
   with output.open(newline='') as f:data=list(csv.reader(f))
   self.assertEqual(len(data)-1,2);self.assertEqual([r[7] for r in data[1:]],['1034','1034'])

 def test_november_extraction_safe(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);b=b'header\nvalue\n';p=root/'a.gz';p.write_bytes(gzip.compress(b))
   r=extract_gzip(p,root/'2019-Nov.csv',len(b),root,expected_name='2019-Nov.csv')
   self.assertEqual(r['bytes'],13);self.assertEqual(r['gzip_crc'],'pass')
   with self.assertRaises(IngestError):extract_gzip(p,root/'2019-Nov.csv',13,root,expected_name='2019-Nov.csv')
   with self.assertRaises(IngestError):extract_gzip(p,root/'2019-Dec.csv',13,root,expected_name='2019-Dec.csv')

 def test_sql_oracle_raw_multiset_and_metric_grain(self):
  rows=[['2019-11-01 01:00:00 UTC','view','1','2','electronics.phone','a,quoted','10.00','1',''],
        ['2019-11-01 02:00:00 UTC','purchase','1','2','electronics.phone','a,quoted','12.20','1','s'],
        ['2019-11-01 02:00:00 UTC','purchase','1','2','electronics.phone','a,quoted','12.20','1','s'],
        ['2019-11-01 03:00:00 UTC','view','1','2','computers','','0','2',''],
        ['2019-11-02 01:00:00 UTC','purchase','1','2','','multi\nline','0.00','2',''],
        ['2019-11-02 03:00:00 UTC','view','1','2','electronics.phone','','NaN','1','']]
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'s.csv'
   with source.open('w',newline='') as f:w=csv.writer(f,lineterminator='\n');w.writerow(HEADER);w.writerows(rows)
   expected=build_expected(source,root/'expected_rows.jsonl',len(rows))
   days=json.loads((root/'expected_daily.json').read_text())
   gates=evaluate({'contract_version':CONTRACT},days,['2019-11-01','2019-11-02'])
   c=duckdb.connect(':memory:');parse(c,source);self.assertEqual(canonical_check(c,root/'expected_rows.jsonl'),{'expected_minus_actual':0,'actual_minus_expected':0})
   daily,categories=build(c,gates);validate_categories(daily,categories)
   c.execute('COPY daily TO ? (FORMAT PARQUET)',[str(root/'daily.parquet')])
   types={r[0]:r[1] for r in c.execute('DESCRIBE SELECT * FROM read_parquet(?)',[str(root/'daily.parquet')]).fetchall()}
   self.assertEqual(types['event_records'],'BIGINT');self.assertEqual(types['purchase_events'],'BIGINT')
   self.assertEqual([(r['active_users'],r['buyers'],r['event_records'],r['purchase_events'],r['purchase_amount']) for r in daily],[(2,1,4,2,'24.40'),(2,1,2,1,'0.00')])
   unknown=[r for r in categories if r['category_key']=='bucket:unknown'];self.assertEqual(len(unknown),1);self.assertEqual(unknown[0]['purchase_events'],1)
   self.assertTrue(all(r['amount_allowed'] for r in daily));c.close()

 def test_boundary_literals(self):
  prices=['+NaN','++NaN','1.20\n','1.234','-1.20','0','']
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'s.csv'
   with source.open('w',newline='') as f:
    w=csv.writer(f,lineterminator='\n');w.writerow(HEADER)
    for value in prices:w.writerow(['2019-11-01 01:00:00 UTC','purchase','1','2','','',value,'1',''])
   build_expected(source,root/'expected_rows.jsonl',7)
   c=duckdb.connect(':memory:');parse(c,source);canonical_check(c,root/'expected_rows.jsonl')
   result=c.execute('SELECT price_nonfinite,price_invalid,price_scale_exceeded,price_negative,price_zero,price_missing FROM parsed').fetchall()
   self.assertEqual(result,[(True,False,False,False,False,False),(False,True,False,False,False,False),(False,True,False,False,False,False),(False,False,True,False,False,False),(False,False,False,True,False,False),(False,False,False,False,True,False),(False,False,False,False,False,True)])
   gates=evaluate({'contract_version':CONTRACT},json.loads((root/'expected_daily.json').read_text()),['2019-11-01'])
   daily,_=build(c,gates);self.assertTrue(daily[0]['count_allowed']);self.assertFalse(daily[0]['amount_allowed']);self.assertIsNone(daily[0]['purchase_amount']);c.close()

 def test_observed_no_purchase_day_keeps_null_buyer_amount(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);source=root/'s.csv'
   with source.open('w',newline='') as f:
    w=csv.writer(f,lineterminator='\n');w.writerow(HEADER)
    w.writerow(['2019-11-15 01:00:00 UTC','view','1','2','','','10','1',''])
   build_expected(source,root/'expected_rows.jsonl',1)
   days=json.loads((root/'expected_daily.json').read_text())
   gates=evaluate({'contract_version':CONTRACT},days,['2019-11-15'])
   c=duckdb.connect(':memory:');parse(c,source);canonical_check(c,root/'expected_rows.jsonl');daily,cats=build(c,gates)
   self.assertEqual((daily[0]['buyers'],daily[0]['purchase_events'],daily[0]['purchase_amount'],daily[0]['amount_per_buyer'],daily[0]['amount_status']),(0,0,'0.00',None,'no_purchases'))
   self.assertTrue(gates['2019-11-15']['amount_allowed']);validate_categories(daily,cats);c.close()

 def test_past_only_comparison_and_abs_vs_relative(self):
  days=['2019-10-04','2019-10-11','2019-10-18','2019-10-25'];daily=[];cat=[]
  for d,total,elec,comp in zip(days,[100,100,100,80],[70,70,70,56],[20,20,20,10]):
   daily.append(dict(utc_date=d,purchase_amount=str(total),event_records=10,purchase_events=3,count_allowed=True,amount_allowed=True))
   for k,v,n in [('category:electronics',elec,4),('category:computers',comp,3),('bucket:unknown',total-elec-comp,3)]:
    cat.append(dict(utc_date=d,category_key=k,purchase_amount=str(v),event_records=n,purchase_events=1,count_allowed=True,amount_allowed=True))
  flags=screen(daily,days,CFG);self.assertEqual(flags[-1]['status'],'zero_scale');self.assertFalse(flags[-1]['candidate'])
  result=compare_categories(daily,cat,flags)[-3:]
  self.assertEqual(result[0]['relative_change'],Fraction(-1,5));self.assertEqual(result[0]['excess_change_pp'],0)
  self.assertEqual(result[1]['relative_change'],Fraction(-1,2));self.assertEqual(result[1]['excess_change_pp'],-30)
  future=dict(daily[-1],utc_date='2019-11-01',purchase_amount='99999')
  self.assertEqual(screen(daily+[future],days+['2019-11-01'],CFG)[:4],flags)
  with self.assertRaises(ValueError):validate_categories(daily,cat[:-1])

if __name__=='__main__':unittest.main()
