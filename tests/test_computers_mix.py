"""Literal synthetic product comparisons; no real input reads."""
from decimal import Decimal as D
from fractions import Fraction as F
from pathlib import Path
import tempfile
import unittest
import duckdb
from scripts.review_computers_mix import analysis,compare,summarize,DAYS,attach_read_only


class ProductMixTests(unittest.TestCase):
    def connection(self,rows):
        c=duckdb.connect(':memory:')
        c.execute('CREATE TABLE scoped_events(utc_date VARCHAR,event_type VARCHAR,product_id VARCHAR,category_code VARCHAR,user_id VARCHAR,price_decimal DECIMAL(18,2),event_eligible BOOLEAN,amount_eligible BOOLEAN)')
        c.executemany('INSERT INTO scoped_events VALUES (?,?,?,?,?,?,?,?)',rows)
        self.addCleanup(c.close);return c

    def test_four_parts_and_symmetric_identity_with_literal_expectations(self):
        def r(day,p,v,event='purchase',cat='computers.test'):
            return (day,event,p,cat,'synthetic_user',D(v),True,event=='purchase')
        a,b='2019-10-04','2019-10-25'
        rows=[r(a,'1','10')]*2+[r(b,'1','10')]*4
        rows += [r(a,'2','10')]*2+[r(b,'2','15')]*2
        rows += [r(a,'3','100'),r(b,'4','30'),r(a,'5','50'),r(b,'5','60'),r(a,'5','1','view',''),r(b,'5','1','cart','electronics.test')]
        daily,products,categories,classes=analysis(self.connection(rows))
        actual={r['product_id']:r for r in compare(products,classes,b,[a])}
        self.assertEqual(daily[0]['purchase_events'],6);self.assertEqual(daily[1]['purchase_events'],8)
        self.assertEqual(daily[0]['purchase_amount'],D('190'));self.assertEqual(daily[1]['purchase_amount'],D('160'))
        self.assertEqual((actual['1']['quantity_component'],actual['1']['within_product_amount_component']),(F(20),F(0)))
        self.assertEqual((actual['2']['quantity_component'],actual['2']['within_product_amount_component']),(F(0),F(10)))
        self.assertEqual((actual['3']['part'],actual['3']['amount_difference'],actual['3']['current_record_mean']),('stable_history_only',F(-100),None))
        self.assertEqual((actual['4']['part'],actual['4']['amount_difference'],actual['4']['history_record_mean']),('stable_current_only',F(30),None))
        self.assertEqual((actual['5']['part'],actual['5']['amount_difference']),('classification_unstable',F(10)))
        self.assertTrue(classes['5']['unknown'] and classes['5']['other_known'])
        self.assertEqual(sum(r['amount_difference'] for r in actual.values()),F(-30))
        self.assertEqual(actual['1']['current_purchase_events'],4)  # Identical purchases are not deduplicated.
        self.assertEqual(sum(-r['amount_difference'] for r in actual.values() if r['amount_difference']<0),100)

    def test_frozen_main_focus_does_not_switch_to_followup_extremes(self):
        rows=[]
        for day in DAYS[:3]: rows.append((day,'purchase','1','computers','u',D(200),True,True))
        for day in DAYS[3:]: rows.append((day,'purchase','2','computers','u',D(30),True,True))
        rows.append(('2019-11-01','purchase','3','computers','u',D(9999),True,True))
        daily,products,_,classes=analysis(self.connection(rows))
        _,parts,focus,_,aliases=summarize(products,classes,daily)
        self.assertEqual(aliases,{'1':'product_A','2':'product_B'})
        self.assertEqual(len(focus),6)
        for day in DAYS[3:]:self.assertEqual({r['product_alias'] for r in focus if r['target_date']==day},{'product_A','product_B'})
        main={r['part']:r['amount_difference'] for r in parts if r['target_date']=='2019-10-25'}
        self.assertEqual(main,dict(stable_common=0,stable_history_only=-200,stable_current_only=30,classification_unstable=0))
        with self.assertRaises(ValueError):compare(products,classes,'2019-10-25',['2019-11-01'])

    def test_exact_category_and_readonly_database(self):
        rows=[('2019-10-04','purchase','1','computers.valid','u',D('1.20'),True,True),
              ('2019-10-04','view','1','computers.','u',D('1.20'),True,False),
              ('2019-10-04','purchase','2',' computers.valid','u',D('9'),True,True)]
        daily,products,_,classes=analysis(self.connection(rows))
        self.assertEqual(daily[0]['purchase_events'],1);self.assertEqual(daily[0]['purchase_amount'],D('1.20'))
        self.assertTrue(classes['1']['unknown']);self.assertNotIn('2',classes)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'synthetic.duckdb';w=duckdb.connect(str(path));w.execute('CREATE TABLE parsed(x INTEGER)');w.close()
            c=duckdb.connect(':memory:');self.addCleanup(c.close)
            attach_read_only(c,path)
            with self.assertRaises(duckdb.InvalidInputException):c.execute('INSERT INTO november.parsed VALUES (1)')


if __name__=='__main__':unittest.main()
