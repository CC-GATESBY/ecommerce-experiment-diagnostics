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
