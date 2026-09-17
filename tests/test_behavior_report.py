"""Whole Markdown generation for small synthetic aggregates, without Spark."""
from pathlib import Path
import json
import tempfile
import unittest
from scripts.behavior_analysis import daily_stats,write_csv,read_csv,CATEGORY_FIELDS
from scripts.write_behavior_report import build
from tests.test_behavior import make_plot_fixture,daily


class NarrativeTests(unittest.TestCase):
    def fixture(self,folder,empty):
        make_plot_fixture(folder,empty=empty)
        stats=daily_stats([] if empty else daily());write_csv(folder/'behavior_daily_stats.csv',stats,list(stats[0]))
        write_csv(folder/'behavior_coverage.csv',[dict(level='month',event_type='view',event_records=10,behavior_users=5)],['level','event_type','event_records','behavior_users'])
        rows=read_csv(folder/'funnel_summary.csv')
        for r in rows:
            v,c,p,t=(int(r[k]) for k in ('n_view','n_cart','n_purchase','n_three_step'))
            r.update(view_cart_purchase=t,view_purchase_no_confirmed_intermediate_cart=p-t,view_cart_no_observed_purchase=c-t,view_only=v-p-c+t)
        (folder/'funnel_summary.csv').unlink();write_csv(folder/'funnel_summary.csv',rows,list(rows[0]))
        prep=folder/'prepare.json';prep.write_text(json.dumps(dict(month=dict(active_users=5,buyers=3,purchase_events=4))))
        return prep
    def test_empty_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'input';prep=self.fixture(source,True);out=root/'output'
            result=build(prep,source,out);self.assertEqual(result['status'],'no_data')
            self.assertIn('NA',(out/'behavior.md').read_text());self.assertTrue((out/'period_summary.md').exists())
    def test_one_category_without_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'input';prep=self.fixture(source,False);out=root/'output'
            row=next(r for r in read_csv(source/'category_concentration.csv') if r['is_unknown']=='False');row.update(amount_rank=1,amount_share=1,cumulative_amount_share=1)
            (source/'category_concentration.csv').unlink();write_csv(source/'category_concentration.csv',[row],CATEGORY_FIELDS)
            result=build(prep,source,out);self.assertEqual(result['reports'],2)
            self.assertIn('100.00%',(out/'behavior.md').read_text());self.assertNotIn('nan',(out/'period_summary.md').read_text().lower())

    def test_measured_monthly_counts_render_without_rewriting_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'input';prep=self.fixture(source,False)
            build(prep,source,root/'before')
            rows=read_csv(source/'category_concentration.csv')
            for row in rows:row.update(users=1,buyers=1,monthly_distinct_status='measured_from_fact_monthly_distinct')
            (source/'category_concentration.csv').unlink();write_csv(source/'category_concentration.csv',rows,CATEGORY_FIELDS)
            build(prep,source,root/'after')
            self.assertIn('月去重users',(root/'after/behavior.md').read_text())
            self.assertIn('unknown月去重用户1',(root/'after/behavior.md').read_text())
            before=(root/'before/period_summary.md').read_text();after=(root/'after/period_summary.md').read_text()
            self.assertEqual(before.split('本轮仅完成描述性总结。')[0],after.split('本轮仅完成描述性总结。')[0])


class AmendmentTests(unittest.TestCase):
    def fixture(self,root):
        import hashlib
        from scripts.check_behavior import category_amendment
        complete=root/'run/complete';complete.mkdir(parents=True);report=root/'reports';report.mkdir()
        old=[dict(category_key='synthetic:'+str(i),purchase_amount='1.00',users='',buyers='',monthly_distinct_status='not_measured_daily_counts_not_additive') for i in range(14)]
        current=[dict(r,users=1,buyers=1,monthly_distinct_status='measured_from_fact_monthly_distinct') for r in old]
        write_csv(report/'category_concentration.csv',current,list(current[0]))
        proof=dict(status='passed',spark_stopped=True,fact_loads=1,source_run='month-v101-01',analysis_scope='rees46_oct_user5_analysis_v1',checks={'synthetic':{'pass':True}},category_csv_before_sha256='a'*64,category_csv_after_sha256=hashlib.sha256((report/'category_concentration.csv').read_bytes()).hexdigest())
        (complete/'preflight.json').write_text(json.dumps(dict(old_categories=old,category_csv_sha256='a'*64)))
        (complete.parent/'launch.json').write_text(json.dumps(dict(status='passed')))
        path=complete/'validation.json';path.write_text(json.dumps(proof))
        return path,report,proof,category_amendment

    def test_approved_unplotted_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,report,proof,check=self.fixture(Path(tmp));self.assertEqual(check(path,report),proof)

    def test_failed_or_wrong_fingerprint_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,report,proof,check=self.fixture(Path(tmp))
            proof['status']='failed';path.write_text(json.dumps(proof))
            with self.assertRaises(ValueError):check(path,report)
            proof['status']='passed';proof['category_csv_after_sha256']='wrong';path.write_text(json.dumps(proof))
            with self.assertRaises(ValueError):check(path,report)

    def test_amount_change_cannot_reuse_old_plot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path,report,proof,check=self.fixture(Path(tmp))
            before=json.loads((path.parent/'preflight.json').read_text());before['old_categories'][0]['purchase_amount']='2.00'
            (path.parent/'preflight.json').write_text(json.dumps(before))
            with self.assertRaises(ValueError):check(path,report)
