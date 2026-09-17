"""Small configuration/calendar tests; no Spark, CSV inputs or historical ETL."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import yaml

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.validate_analysis_scope import (BINDING, TABLES, validate_scope, validate_request,
    history_readiness, verify_evidence, canonical_snapshot, utc)


class AnalysisScopeTests(unittest.TestCase):
    def setUp(self):
        self.cfg=yaml.safe_load((ROOT/'config/analysis_scope.yaml').read_text())
        self.days=[f'2019-10-{d:02d}' for d in range(1,32)]
        self.daily=[dict(utc_date=d,count_allowed=True,amount_allowed=True) for d in self.days]

    def test_complete_utc_window(self):
        self.assertEqual(validate_scope(self.cfg),self.days)
        self.assertEqual(utc(self.cfg['observation']['end_exclusive']).day,1)

    def test_non_utc_and_noncanonical_values(self):
        for value in ('2019-10-01','2019-10-01T00:00:00','2019-10-01T00:00:00+10:00','2019-10-01T00:00:00Z\n'):
            with self.subTest(value=value),self.assertRaises(ValueError):utc(value)

    def test_invalid_window_order_and_grain(self):
        for key,value in [('end_exclusive','2019-10-01T00:00:00Z'),('start_inclusive','2019-10-01T00:00:01Z'),('interval','[]'),('timezone','Australia/Melbourne')]:
            bad=deepcopy(self.cfg);bad['observation'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_scope(bad)

    def test_no_expansion_to_november(self):
        bad=deepcopy(self.cfg);bad['observation']['end_exclusive']='2019-12-01T00:00:00Z'
        with self.assertRaises(ValueError):validate_scope(bad)

    def test_requests_outside_or_duplicate(self):
        for days in ([],['2019-09-30'],['2019-11-01'],['2019-10-01']*2):
            with self.subTest(days=days),self.assertRaises(ValueError):validate_request(self.cfg,days,'count')
        self.assertEqual(validate_request(self.cfg,['2019-10-31'],'amount'),['2019-10-31'])

    def test_wrong_scope_or_canonical_run(self):
        for key,value in [('scope_id','wrong'),('fact_run','month-v101-02'),('metric_run','metrics-month-02'),('crosscheck_run','crosscheck-month-02'),('duplicate_policy','hypothetical_one_per_duplicate_group')]:
            bad=deepcopy(self.cfg);bad['binding'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_scope(bad)

    def test_selector_rejects_replicate_multiple_and_wildcard(self):
        with patch('scripts.validate_analysis_scope.select_snapshot') as reader:
            for path in (['one','two'],'.local/t13/metrics-month-02','.local/t13/*'):
                with self.subTest(path=path),self.assertRaises(ValueError):canonical_snapshot(ROOT,self.cfg,path)
            reader.assert_not_called()
            reader.return_value={'selected':True}
            self.assertEqual(canonical_snapshot(ROOT,self.cfg,'.local/t13/metrics-month-01'),{'selected':True})
            self.assertEqual(reader.call_args.kwargs['source_run'],'month-v101-01')

    def test_calendar_literal_counts(self):
        actual=history_readiness(self.cfg,self.daily)
        expected=[0]*7+[1]*7+[2]*7+[3]*7+[4]*3
        for purpose in ('count','amount'):
            part=[r for r in actual if r['purpose']==purpose]
            self.assertEqual([r['history_count'] for r in part],expected)
            self.assertEqual(sum(r['meets_min3'] for r in part),10)
            self.assertEqual(sum(r['meets_full4'] for r in part),3)
            self.assertEqual(part[21]['history_dates'],['2019-10-15','2019-10-08','2019-10-01'])
            self.assertEqual(part[28]['history_dates'],['2019-10-22','2019-10-15','2019-10-08','2019-10-01'])
            self.assertEqual(part[21]['status'],'history_available_not_evaluated')
            self.assertEqual(part[20]['status'],'insufficient_history')

    def test_missing_day_excludes_corresponding_history(self):
        result=history_readiness(self.cfg,self.daily[1:])
        for purpose in ('count','amount'):
            byday={r['utc_date']:r for r in result if r['purpose']==purpose}
            self.assertEqual(byday['2019-10-08']['history_count'],0)
            self.assertEqual(byday['2019-10-22']['history_count'],2)
            self.assertFalse(byday['2019-10-22']['meets_min3'])
            self.assertEqual(byday['2019-10-29']['history_count'],3)
            self.assertFalse(byday['2019-10-29']['meets_full4'])
            self.assertEqual(byday['2019-10-01']['status'],'current_date_unavailable')

    def test_amount_block_does_not_block_count_history(self):
        self.daily[0]['amount_allowed']=False
        result={(r['purpose'],r['utc_date']):r for r in history_readiness(self.cfg,self.daily)}
        self.assertEqual(result['count','2019-10-22']['history_count'],3)
        self.assertEqual(result['amount','2019-10-22']['history_count'],2)
        self.assertIn('quality_blocked:2019-10-01',result['amount','2019-10-22']['reason'])

    def test_count_block_also_blocks_amount(self):
        self.daily[0]['count_allowed']=False
        for r in history_readiness(self.cfg,self.daily):
            if r['utc_date']=='2019-10-08':self.assertEqual(r['history_count'],0)

    def test_current_date_quality_prevents_detector_release(self):
        self.daily[28]['amount_allowed']=False
        r=next(r for r in history_readiness(self.cfg,self.daily) if r['utc_date']=='2019-10-29' and r['purpose']=='amount')
        self.assertEqual(r['history_count'],4)
        self.assertEqual(r['status'],'current_date_unavailable')

    def test_bad_daily_lists(self):
        for bad in (self.daily+[self.daily[0]],self.daily+[dict(utc_date='2019-11-01',count_allowed=True,amount_allowed=True)],
                    [dict(utc_date='2019-10-01',count_allowed='True',amount_allowed=True)]):
            with self.subTest(bad=bad[-1]),self.assertRaises(ValueError):history_readiness(self.cfg,bad)

    def test_funnel_24hour_day_boundary(self):
        self.assertEqual(len(validate_request(self.cfg,self.days[:-1],'funnel_start')),30)
        with self.assertRaises(ValueError):validate_request(self.cfg,['2019-10-31'],'funnel_start')
        bad=deepcopy(self.cfg);bad['uses']['funnel']['end_exclusive']='2019-11-01T00:00:00Z'
        with self.assertRaises(ValueError):validate_scope(bad)
        bad=deepcopy(self.cfg);bad['uses']['funnel']['max_window_hours']=12
        with self.assertRaises(ValueError):validate_scope(bad)

    def test_experiment_overlap_and_outside(self):
        for start,end in [('2019-10-14T00:00:00Z','2019-10-29T00:00:00Z'),('2019-10-15T00:00:00Z','2019-11-02T00:00:00Z')]:
            bad=deepcopy(self.cfg);bad['uses']['experiment']['outcome']={'start_inclusive':start,'end_exclusive':end}
            with self.subTest(start=start),self.assertRaises(ValueError):validate_scope(bad)

    def test_frozen_sampling_and_history_parameters(self):
        for section,key,value in [('sampling','seed','different'),('history','min_history_points',2),('history','lookback_offsets_days',[1,2,3])]:
            bad=deepcopy(self.cfg);target=bad['sampling'] if section=='sampling' else bad['uses']['history'];target[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_scope(bad)

    def proofs(self):
        b=BINDING
        d=dict(source_id=b['source_id'],scope_id=b['scope_id'],series_id=b['series_id'],input_sha256=b['candidate_sha256'],contract_version=b['parsing_contract'],run_id=b['fact_run'],kind='user_sample_candidate')
        launch=dict(d,status='passed');fact=dict(status='passed',spark_stopped=True,checks={'synthetic':{'pass':True}})
        m=dict(status='passed',spark_stopped=True,checks={'synthetic':{'pass':True}},lineage=dict(source_id=b['source_id'],source_run=b['fact_run'],input_sha256=b['candidate_sha256'],contract_version=b['parsing_contract'],metric_version=b['metric_version'],date_policy_version=b['date_policy'],brand_mapping_version=b['brand_mapping'],observation_start_utc='2019-10-01',observation_end_exclusive_utc='2019-11-01'),tables={n:{'rows':1} for n in TABLES if n!='brand_mapping'})
        c=dict(status='passed',passed=True,scope_id=b['scope_id'],input_sha256=b['candidate_sha256'],source_run=b['fact_run'],metric_run=b['metric_run'],tables={n:dict(expected_rows=1,actual_rows=1,**{'pass':True}) for n in TABLES},fields=[{'differences':0}])
        return [d,launch,fact,m,c]

    def test_complete_synthetic_receipts(self):
        verify_evidence(self.cfg,*self.proofs())

    def test_incomplete_failed_wrong_receipts(self):
        for index,key,value in [(0,'run_id','month-v101-02'),(0,'scope_id','wrong'),(1,'status','running'),(2,'spark_stopped',False),(3,'status','failed'),(4,'passed',False),(4,'metric_run','metrics-month-02')]:
            proofs=self.proofs();proofs[index][key]=value
            with self.subTest(index=index,key=key),self.assertRaises(ValueError):verify_evidence(self.cfg,*proofs)
        proofs=self.proofs();proofs[4]['fields'][0]['differences']=1
        with self.assertRaises(ValueError):verify_evidence(self.cfg,*proofs)


if __name__=='__main__':unittest.main()
