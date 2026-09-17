"""At most 100 synthetic events; literal expectations and independent enumeration."""
from collections import Counter,defaultdict
from datetime import datetime,timedelta,timezone
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from scripts.run_funnel import (ROOT,KEY,VERSION,Checks,build_funnel,validate_config,write_json,publish,sha256)

SCHEMA='scope_id string,user_id string,user_session string,product_id string,event_type string,event_timestamp_utc timestamp,event_date_utc date,price_decimal decimal(18,2),event_eligible boolean,user_id_missing boolean,user_id_invalid boolean,product_id_missing boolean,product_id_invalid boolean,session_missing boolean'


def fixture():
    rows=[];base=datetime(2019,10,1,12,tzinfo=timezone.utc);users={}
    def add(case,behavior,minute=0,price='10',start=base,user=None,session=None,product='1',bad_product=False):
        users.setdefault(case,str(len(users)+1));t=start+timedelta(minutes=minute)
        rows.append(dict(scope_id='synthetic_t21',user_id=user or users[case],user_session=case if session is None else session,product_id=product,
            event_type=behavior,event_timestamp_utc=t,event_date_utc=t.date(),price_decimal=None if price is None else Decimal(price),event_eligible=True,
            user_id_missing=False,user_id_invalid=False,product_id_missing=False,product_id_invalid=bad_product,session_missing=session is not None and not session.strip()))
    for name,events in {
        'normal':[('view',0),('cart',1),('purchase',2)],'direct':[('view',0),('purchase',2)],
        'cart_only':[('view',0),('cart',1)],'view_only':[('view',0)],
        'pre_cart':[('cart',-1),('view',0),('purchase',2)],
        'pre_and_post_cart':[('cart',-1),('view',0),('cart',1),('purchase',2)],
        'p_c_p':[('view',0),('purchase',1),('cart',2),('purchase',3)],
        'p_c':[('view',0),('purchase',1),('cart',2)],
        'duplicates':[('view',0),('view',0),('view',1),('cart',2),('purchase',3),('purchase',3)],
        'tie_change':[('view',0),('cart',0),('purchase',1)],
        'tie_harmless':[('view',0),('cart',0),('cart',1),('purchase',2)],
        'tie_cp':[('view',0),('cart',1),('purchase',1)],
        'no_view':[('purchase',0)],'pre_purchase':[('purchase',-1),('view',0)],
        'purchase_at_view':[('view',0),('purchase',0)],
    }.items():
        for behavior,minute in events:add(name,behavior,minute)
    for user in ('80','81'):
        add('shared_session','view',user=user);add('shared_session','purchase',1,user=user)
    for product in ('1','2'):
        add('products','view',user='82',product=product)
    add('products','cart',1,user='82',product='1');add('products','purchase',2,user='82',product='2')
    add('missing_session','view',session=' ');add('missing_session','purchase',1,session=' ')
    add('bad_product','view',product='bad',bad_product=True);add('bad_product','purchase',1,product='bad',bad_product=True)
    for name,minutes in [('cross_day',120),('exact24',1440),('over24',1441)]:
        start=datetime(2019,10,1,23,tzinfo=timezone.utc);add(name,'view',start=start);add(name,'purchase',minutes,start=start)
    for name,day in [('oct30',30),('oct31',31)]:
        start=datetime(2019,10,day,0,tzinfo=timezone.utc);add(name,'view',start=start);add(name,'purchase',1440 if day==30 else 60,start=start)
    add('different_price','view',price='19.00');add('different_price','purchase',1,price='500.00')
    add('price_conflict','view',price='19');add('price_conflict','view',price='21')
    add('price_mixed','view',price='10');add('price_mixed','view',price=None)
    add('price_equal','view',price='20.0');add('price_equal','view',price='20.00')
    add('price_negative','view',price='-1');add('price_zero','view',price='0')
    add('price_50','view',price='50');add('price_200','view',price='200')
    for b,m in [('view',0),('view',1500),('cart',1560),('purchase',1620)]:add('no_daily_reset',b,m)
    for b,m in [('view',0),('cart',1380),('purchase',1500)]:add('shared_deadline',b,m)
    add('empty_session','view',session='')
    add('remove','remove_from_cart')
    assert len(rows)<=100
    return rows


# Deliberately enumerate small event combinations instead of SQL extrema.
def independent_paths(rows):
    grouped=defaultdict(list);result=[]
    for r in rows:
        if r['event_eligible'] and not any(r[x] for x in ('user_id_missing','user_id_invalid','product_id_missing','product_id_invalid','session_missing')):
            grouped[tuple(r[k] for k in KEY)].append(r)
    for key,events in grouped.items():
        views=[r for r in events if r['event_type']=='view']
        if not views:continue
        v=sorted(r['event_timestamp_utc'] for r in views)[0];end=v+timedelta(days=1)
        def classify(allow_ties):
            carts=[r for r in events if r['event_type']=='cart' and r['event_timestamp_utc']<=end and (r['event_timestamp_utc']>=v if allow_ties else r['event_timestamp_utc']>v)]
            purchases=[r for r in events if r['event_type']=='purchase' and r['event_timestamp_utc']<=end and (r['event_timestamp_utc']>=v if allow_ties else r['event_timestamp_utc']>v)]
            triple=any((c['event_timestamp_utc']<=p['event_timestamp_utc'] if allow_ties else c['event_timestamp_utc']<p['event_timestamp_utc']) for c in carts for p in purchases)
            category='view_cart_purchase' if triple else 'view_purchase_no_confirmed_intermediate_cart' if purchases else 'view_cart_no_observed_purchase' if carts else 'view_only'
            return bool(carts),bool(purchases),triple,category
        c,p,t,category=classify(False);possible=classify(True)[3];uncertain=category!=possible;censored=v.date()>=datetime(2019,10,31).date()
        prices=[r['price_decimal'] for r in views if r['event_timestamp_utc']==v];good={p for p in prices if p is not None and p>=0};bad=sum(p is None or p<0 for p in prices)
        status='conflicting' if len(good)>1 else 'invalid_or_missing' if bad or len(good)!=1 else 'unique_valid'
        price=next(iter(good)) if status=='unique_valid' else None
        band='unknown' if price is None else '[0,20)' if price<20 else '[20,50)' if price<50 else '[50,200)' if price<200 else '[200,+inf)'
        result.append(dict(zip(KEY,key),first_view_time=v,start_date_utc=v.date(),deadline=end,has_cart_after_view=c,has_purchase_after_view=p,
            has_three_step=t,strict_class=category,possible_class=possible,order_uncertain=uncertain,right_censored=censored,
            release_status='right_censored' if censored else 'order_uncertain' if uncertain else 'formal',first_view_price=price,first_view_price_status=status,
            first_view_bad_price_records=bad,first_view_valid_price_count=len(good),price_band=band))
    return result


def independent_coverage(rows):
    groups=defaultdict(list)
    for r in rows:
        for level,d in [('month',None),('day',r['event_date_utc'].isoformat())]:groups[(level,d,r['event_type'])].append(r)
    return sorted([dict(level=k[0],utc_date=k[1],event_type=k[2],event_records=len(rs),behavior_users=len({r['user_id'] for r in rs})) for k,rs in groups.items()],key=lambda r:(r['level'],r['utc_date'] or '',r['event_type']))


def independent_audit(rows,paths):
    origins={tuple(p[k] for k in KEY):p['first_view_time'] for p in paths};groups=Counter()
    for r in rows:
        if r['event_type']!='purchase':continue
        key=tuple(r[k] for k in KEY);v=origins.get(key);t=r['event_timestamp_utc']
        if any(r[x] for x in ('user_id_missing','user_id_invalid','product_id_missing','product_id_invalid','session_missing')):reason='invalid_path_key'
        elif v is None:reason='no_view_same_key'
        elif t<=v:reason='purchase_at_or_before_first_view'
        elif v.day==31:reason='start_outside_formal_range'
        elif t-v>timedelta(hours=24):reason='beyond_24_hours'
        else:reason='within_path_window'
        groups[('month',None,reason)]+=1;groups[('day',t.date().isoformat(),reason)]+=1
    return sorted([dict(level=k[0],utc_date=k[1],reason=k[2],purchase_events=v) for k,v in groups.items()],key=lambda r:(r['level'],r['utc_date'] or '',r['reason']))


def literal_checks(expected):
    checks=Checks();by_session=defaultdict(list)
    for row in expected:by_session[row['user_session']].append(row)
    literal={
      'normal':('view_cart_purchase',True,True,True,False),
      'direct':('view_purchase_no_confirmed_intermediate_cart',False,True,False,False),
      'cart_only':('view_cart_no_observed_purchase',True,False,False,False),
      'view_only':('view_only',False,False,False,False),
      'pre_cart':('view_purchase_no_confirmed_intermediate_cart',False,True,False,False),
      'pre_and_post_cart':('view_cart_purchase',True,True,True,False),
      'p_c_p':('view_cart_purchase',True,True,True,False),
      'p_c':('view_purchase_no_confirmed_intermediate_cart',True,True,False,False),
      'duplicates':('view_cart_purchase',True,True,True,False),
      'tie_change':('view_purchase_no_confirmed_intermediate_cart',False,True,False,True),
      'tie_harmless':('view_cart_purchase',True,True,True,False),
      'tie_cp':('view_purchase_no_confirmed_intermediate_cart',True,True,False,True),
      'exact24':('view_purchase_no_confirmed_intermediate_cart',False,True,False,False),
      'over24':('view_only',False,False,False,False),
      'no_daily_reset':('view_only',False,False,False,False),
      'shared_deadline':('view_cart_no_observed_purchase',True,False,False,False),
      'purchase_at_view':('view_only',False,False,False,True),
    }
    for case,want in literal.items():
        r=by_session[case][0];checks.equal('literal_'+case,want,tuple(r[k] for k in ('strict_class','has_cart_after_view','has_purchase_after_view','has_three_step','order_uncertain')))
    checks.equal('same_session_different_users',2,len(by_session['shared_session']))
    checks.equal('same_user_session_two_products',2,len(by_session['products']))
    checks.equal('products_do_not_form_three_step',0,sum(r['has_three_step'] for r in by_session['products']))
    checks.equal('duplicates_one_path',1,len(by_session['duplicates']))
    checks.equal('missing_keys_no_paths',False,any(r['user_session'] in (' ','bad_product') for r in expected))
    checks.equal('purchase_without_view_no_path',0,len(by_session['no_view']))
    checks.equal('oct30_complete',('formal',True),(by_session['oct30'][0]['release_status'],by_session['oct30'][0]['has_purchase_after_view']))
    checks.equal('oct31_censored','right_censored',by_session['oct31'][0]['release_status'])
    checks.equal('cross_day_start_date','2019-10-01',str(by_session['cross_day'][0]['start_date_utc']))
    for name,state,band in [('different_price','unique_valid','[0,20)'),('price_conflict','conflicting','unknown'),('price_mixed','invalid_or_missing','unknown'),('price_equal','unique_valid','[20,50)'),('price_negative','invalid_or_missing','unknown'),('price_zero','unique_valid','[0,20)'),('price_50','unique_valid','[50,200)'),('price_200','unique_valid','[200,+inf)')]:
        checks.equal('literal_price_'+name,(state,band),(by_session[name][0]['first_view_price_status'],by_session[name][0]['price_band']))
    return checks


class FunnelUnitTests(unittest.TestCase):
    def test_literal_enumeration(self):self.assertTrue(all(c['pass'] for c in literal_checks(independent_paths(fixture())).rows.values()))
    def test_template_not_runnable(self):
        with self.assertRaises(ValueError):validate_config(json.loads((ROOT/'config/funnel.example.json').read_text()))
    def test_wrong_scope_or_run_rejected(self):
        cfg=json.loads((ROOT/'config/funnel.example.json').read_text())
        for k,v in [('source_run','month-v101-02'),('analysis_scope_version','other'),('funnel_version','v2')]:
            with self.subTest(k=k),self.assertRaises(ValueError):validate_config(dict(cfg,**{k:v}))
    def test_partial_publish_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp);stage=run/'staging';stage.mkdir();write_json(stage/'validation.json',dict(status='failed',spark_stopped=True))
            with self.assertRaises(ValueError):publish(stage,run)
            self.assertFalse((run/'complete').exists())


def run_tests(spark,stage):
    from pyspark.sql.types import StructType
    rows=fixture();expected=independent_paths(rows);checks=literal_checks(expected)
    fact=spark.createDataFrame(rows,SCHEMA);identity=dict(funnel_version=VERSION,source_run='synthetic',funnel_run='synthetic_reproducible')
    first=build_funnel(spark,fact,stage/'first',identity)
    paths=spark.read.parquet(str(stage/'first/funnel_paths'))
    fields=list(expected[0]);schema=StructType([paths.schema[k] for k in fields]);oracle=spark.createDataFrame(expected,schema)
    checks.equal('all_synthetic_paths_minus_oracle',0,paths.select(*fields).exceptAll(oracle).count())
    checks.equal('oracle_minus_all_synthetic_paths',0,oracle.exceptAll(paths.select(*fields)).count())
    checks.equal('all_coverage_vs_independent',independent_coverage(rows),first['coverage'])
    checks.equal('all_purchase_audit_vs_independent',independent_audit(rows,expected),first['purchase_audit'])
    before={str(p):sha256(p) for p in (stage/'first').rglob('*') if p.is_file()}
    second=build_funnel(spark,fact,stage/'second',identity)
    repeated=spark.read.parquet(str(stage/'second/funnel_paths'))
    checks.equal('rerun_logical_minus',0,paths.exceptAll(repeated).count());checks.equal('rerun_logical_plus',0,repeated.exceptAll(paths).count())
    for field in ('coverage','summary','exclusions','purchase_audit'):checks.equal('rerun_'+field,first[field],second[field])
    rejected=False
    try:build_funnel(spark,fact,stage/'first',identity)
    except FileExistsError:rejected=True
    checks.equal('existing_output_rejected',True,rejected)
    checks.equal('old_output_unchanged',before,{str(p):sha256(p) for p in (stage/'first').rglob('*') if p.is_file()})
    empty=build_funnel(spark,spark.createDataFrame([],SCHEMA),stage/'empty',identity)
    overall=next(r for r in empty['summary'] if r['level']=='overall')
    checks.equal('empty_denominator',0,overall['n_view'])
    for field in ('view_to_cart','cart_to_purchase_three_step','view_to_purchase','three_step_ratio'):checks.equal('empty_'+field,None,overall[field])
    checks.equal('empty_reason','zero_denominator',overall['cart_denominator_status'])
    checks.equal('synthetic_under_100',True,len(rows)<=100)
    return dict(checks=checks.rows,synthetic_events=len(rows),synthetic_paths=len(expected),first=first,repeat=second,empty=empty)
