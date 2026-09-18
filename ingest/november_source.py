"""Authorized November source extension; reuse immutable ingestion and user sampling."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ingest.ingest import (HEADER, IngestError, extract_gzip, publish_raw, sha256,
                           stream_download, verify_headers, write_new_json)
from ingest.profile_and_sample import (Profile, OutputBudget, scan, validate_candidate,
                                       ALGORITHM, SEED, PREFIX, THRESHOLD, SERIALIZATION)

BASE = ROOT / '.local/t4_cross_period'
URL = 'https://data.rees46.com/datasets/marketplace/2019-Nov.csv.gz'
ARCHIVE_BYTES = 2890421023
CSV_BYTES = 9006762395
ETAG = '"646b57e5-ac48531f"'
WINDOW = ('2019-11-01T00:00:00+00:00', '2019-12-01T00:00:00+00:00')


def check_budget():
    used = sum(p.stat().st_size for p in BASE.rglob('*') if p.is_file())
    free = shutil.disk_usage(BASE).free
    if used > 40*1024**3 or free < 150*1024**3:
        raise IngestError('Cross-period disk budget exceeded')
    return {'new_bytes': used, 'free_bytes': free}


class ExactURL(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise IngestError('Redirect requires source review')


def acquire():
    run = BASE / 'nov-source-01'
    if (run/'complete.json').exists():
        record = json.loads((run/'complete.json').read_text())
        for item in (record['archive'], record['csv']):
            path = ROOT/item['local_relative_path']
            if path.stat().st_size != item['bytes'] or sha256(path) != item['sha256']:
                raise IngestError('Existing raw content changed')
        return record
    stage = run/'staging'; stage.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    try:
        if ARCHIVE_BYTES > 4*1024**3 or shutil.disk_usage(BASE).free - 20*1024**3 < 150*1024**3:
            raise IngestError('Projected download/disk budget exceeded')
        view=json.loads((BASE/'view.json').read_text())
        listed=json.loads((BASE/'files.json').read_text())['datasetFiles']
        if URL not in view['description'] or view['currentVersionNumber'] != 8:
            raise IngestError('Official publisher link/version evidence changed')
        if [r['totalBytes'] for r in listed if r['name']=='2019-Nov.csv'] != [CSV_BYTES]:
            raise IngestError('Official file metadata changed')
        archive=stage/'2019-Nov.csv.gz'
        req=urllib.request.Request(URL,headers={'Accept-Encoding':'identity'})
        with urllib.request.build_opener(ExactURL).open(req,timeout=60) as response:
            verify_headers(response, {'archive_bytes':ARCHIVE_BYTES,'archive_etag':ETAG})
            compressed=stream_download(response, archive, ARCHIVE_BYTES)
        check_budget()
        extracted=extract_gzip(archive,stage/'2019-Nov.csv',CSV_BYTES,stage,expected_name='2019-Nov.csv')
        raw=BASE/'raw';raw.mkdir(exist_ok=True)
        for receipt in (compressed,extracted):
            published=publish_raw(stage/receipt['filename'],raw,receipt['sha256'])
            receipt['local_relative_path']=str(published.relative_to(ROOT))
        record={'status':'complete','source_id':'rees46_multicategory_2019_nov',
                'source_url':URL,'publisher':'https://rees46.com/en/datasets',
                'catalog':'https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store',
                'version':'publisher_unversioned_object; catalog_v8_context_only',
                'http_etag':ETAG,'archive':compressed,'csv':dict(extracted,parent_sha256=compressed['sha256']),
                'elapsed_seconds':round(time.monotonic()-start,3),'resources':check_budget()}
        write_new_json(run/'complete.json',record)
        print(json.dumps({'phase':'raw_complete','archive':compressed['bytes'],'csv':extracted['bytes']}),flush=True)
        return record
    except BaseException as exc:
        write_new_json(run/'failure.json',{'status':'failed','error':type(exc).__name__,
                                         'elapsed_seconds':round(time.monotonic()-start,3),'resources':check_budget()})
        raise


def sample():
    raw=json.loads((BASE/'nov-source-01/complete.json').read_text())
    if raw['status']!='complete': raise IngestError('Raw completion required')
    source=ROOT/raw['csv']['local_relative_path']
    stage=BASE/'nov-sample-01/staging'; stage.mkdir(parents=True,exist_ok=False)
    start=time.monotonic()
    source_profile,candidate_profile=Profile(*WINDOW),Profile(*WINDOW)
    try:
        budget=OutputBudget(stage,4*1024**3,150*1024**3)
        output=stage/'user_sample_candidate.csv'
        extraction=scan(source,output,source_profile,candidate_profile,budget,2000000,start)
        if extraction['source_sha256']!=raw['csv']['sha256'] or extraction['source_bytes']!=CSV_BYTES:
            raise IngestError('Raw hash/size mismatch during complete scan')
        validation=validate_candidate(output,extraction,candidate_profile.summary(),stage/'selected_users.sqlite3',budget,500000,start,window=WINDOW)
        if source_profile.outside_month or source_profile.time_invalid or source_profile.time_missing:
            raise IngestError('Source window/time anomalies require review')
        record={'status':'validated','kind':'user_sample_candidate','source_id':raw['source_id'],
                'scope_id':'rees46_2019_nov_user5_'+raw['csv']['sha256'][:16]+'_20260916_v1',
                'run_id':'nov-sample-01','parent_sha256':raw['csv']['sha256'],
                'algorithm_version':ALGORITHM,'seed':SEED,'target_user_probability':'0.05',
                'payload_prefix':PREFIX,'threshold_uint64':THRESHOLD,'serialization':SERIALIZATION,
                'source_scan':source_profile.summary(),
                'sample':dict(validation,bytes=extraction['sample_bytes'],sha256=extraction['sample_sha256'],field_sequence_sha256=extraction['field_sequence_sha256']),
                'expected_window':WINDOW,'elapsed_seconds':round(time.monotonic()-start,3),'resources':check_budget()}
        output.chmod(0o444)
        write_new_json(stage/'receipt.json',record)
        stage.rename(stage.parent/'complete')
        print(json.dumps({'phase':'candidate_complete','source_records':source_profile.records,'sample_records':candidate_profile.records,'users':validation['distinct_user_count']}),flush=True)
    except BaseException as exc:
        write_new_json(stage/'failure.json',{'status':'failed','error':type(exc).__name__,
                                          'partial_source':source_profile.summary(),'selected_records':candidate_profile.records})
        raise

if __name__=='__main__':
    args=argparse.ArgumentParser();args.add_argument('phase',choices=['acquire','sample']);a=args.parse_args()
    (acquire if a.phase=='acquire' else sample)()
