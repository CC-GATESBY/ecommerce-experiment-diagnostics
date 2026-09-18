"""Local serial immutable-batch registration and fail-closed Spark reads."""

from functools import reduce
import importlib
import json
import os
from pathlib import Path
import re
import uuid

from etl.date_quality import POLICY, dates_checked, evaluate
from etl.event_config import CONTRACT, sha256

IDENTITY = ('source_id', 'scope_id', 'input_sha256', 'contract_version')
DESCRIPTOR = {*IDENTITY, 'kind', 'run_id', 'run_path', 'expected_records', 'dates',
              'series_id', 'sampling_rule'}


class FactAccessError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise FactAccessError(reason)


def local_path(root, value):
    require(isinstance(value, str) and value and not any(c in value for c in ('*', '?', '[')), 'explicit local path required')
    path = Path(value)
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    require(path.is_relative_to(root / '.local/t11'), 'path outside local T1.1 area')
    return path


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise FactAccessError('missing or malformed local evidence: ' + path.name) from exc


def check_proof(proof, name, value):
    c = proof['checks'].get(name, {})
    require(c.get('pass') is True and c.get('expected') == value and c.get('actual') == value,
            'missing or inconsistent verification: ' + name)


def inspect_batch(root, descriptor):
    """Only metadata and binary fingerprints; never opens a source CSV."""
    root = Path(root).resolve(); d = descriptor
    require(set(d) == DESCRIPTOR, 'descriptor fields mismatch')
    require(d['contract_version'] == CONTRACT, 'contract mismatch')
    require(re.fullmatch(r'[0-9a-f]{64}', d['input_sha256']) is not None, 'invalid input SHA')
    require(type(d['expected_records']) is int and d['expected_records'] > 0, 'invalid record count')
    require(all(isinstance(d[k], str) and d[k] for k in (*IDENTITY, 'series_id', 'sampling_rule', 'run_id')), 'empty identity')
    dates = dates_checked(d['dates']); run = local_path(root, d['run_path'])
    require(run.name == d['run_id'], 'run ID/path mismatch')
    require(d['kind'] in ('synthetic', 'user_sample_candidate'), 'unsupported input kind')
    extra_evidence = []
    if d['kind'] == 'synthetic':
        require('synthetic' in run.relative_to(root / '.local/t11').parts and d['source_id'].startswith('synthetic_')
                and d['series_id'].startswith('synthetic_') and d['scope_id'].startswith('synthetic_'), 'synthetic isolation required')
    else:
        manifest_path = root / 'data/manifest.json'
        manifest = read_json(manifest_path)
        matches = [x for x in manifest['user_sample_candidates'] if x['scope_id'] == d['scope_id']
                   and x['sample']['sha256'] == d['input_sha256'] and x['status'] == 'validated'
                   and x['kind'] == d['kind'] and x['sample']['profile']['record_count'] == d['expected_records']]
        require(len(matches) == 1, 'input not uniquely registered in source manifest')
        m = matches[0]
        require(d['source_id'] == 'rees46_multicategory_2019_oct' and d['run_id'] in ('month-v101-01', 'month-v101-02'),
                'real batch outside closeout authorization')
        require(d['sampling_rule'] == m['algorithm_version'] + '|' + m['seed'], 'sampling rule mismatch')
        extra_evidence.append(manifest_path)
    launch_path = run / 'launch.json'; proof_path = run / 'complete/validation.json'
    launch = read_json(launch_path); proof = read_json(proof_path)
    completed = (proof.get('completion_mode') == 'synthetic_no_active_writer_shared_test_session'
                 if d['kind'] == 'synthetic' else proof.get('spark_stopped') is True)
    require(launch.get('status') == proof.get('status') == 'passed' and completed,
            'batch not successfully completed')
    require(all(launch.get(k) == d[k] for k in ('scope_id', 'input_sha256', 'contract_version', 'run_id'))
            and proof.get('contract_version') == CONTRACT, 'receipt identity mismatch')
    checks = proof.get('checks', {})
    require(checks and all(x.get('pass') is True and x.get('expected') == x.get('actual') for x in checks.values()),
            'independent verification failed')
    check_proof(proof, 'rows', d['expected_records'])
    check_proof(proof, 'input_sha256_after', d['input_sha256'])
    for name in ('expected_minus_actual_multiset', 'actual_minus_expected_multiset'):
        check_proof(proof, name, 0)
    events = importlib.import_module('etl.01_events')
    require(proof.get('schema') == events.schema().jsonValue(), 'receipt schema mismatch')
    check_proof(proof, 'schema', events.schema().simpleString())
    summary = proof['summary']; daily = proof['daily_summary']
    require(summary['record_count'] == d['expected_records'] == sum(v['record_count'] for v in daily.values()), 'row conservation failed')
    for key, value in summary.items():
        check_proof(proof, 'summary_' + key, value)
    check_proof(proof, 'daily_bucket_keys', sorted(daily))
    for day, value in daily.items():
        check_proof(proof, 'daily_' + day, value)
    if d['kind'] != 'synthetic':
        import csv
        coverage_path = root / 'reports/sample_daily_coverage.csv'
        with coverage_path.open() as stream:
            coverage = {r['utc_date']: int(r['event_records']) for r in csv.DictReader(stream)}
        require(dates == sorted(coverage), 'declared real date coverage mismatch')
        require({k: v['record_count'] for k, v in daily.items()} == coverage, 'registered daily coverage mismatch')
        extra_evidence.append(coverage_path)
    folder = run / 'complete/fact_events'; success = folder / '_SUCCESS'
    files = sorted(folder.glob('*.parquet'))
    require(success.is_file() and files and not any(p.is_symlink() for p in files), 'incomplete or redirected fact directory')
    inventory = [dict(path=str(p.relative_to(root)), bytes=p.stat().st_size, sha256=sha256(p)) for p in files]
    evidence = {str(p.relative_to(root)): sha256(p) for p in [launch_path, proof_path, success, *extra_evidence]}
    identity = {k: d[k] for k in IDENTITY}; identity['source_run'] = d['run_id']
    return dict(descriptor=d, inventory=inventory, evidence=evidence,
                summary=summary, daily=daily, gates=evaluate(identity, daily, dates), policy_version=POLICY)


def logical_id(descriptor):
    return tuple(descriptor[k] for k in IDENTITY)


def load_registry(root, path):
    path = local_path(Path(root).resolve(), str(path))
    if not path.exists():
        return {'version': 1, 'batches': []}
    data = read_json(path)
    require(set(data) == {'version', 'batches'} and data['version'] == 1 and isinstance(data['batches'], list), 'registry format mismatch')
    seen = set(); series = {}; coverage = set(); content = set()
    for entry in data['batches']:
        d = entry['descriptor']; key = (d['series_id'], logical_id(d))
        require(key not in seen, 'duplicate logical batch in registry'); seen.add(key)
        binding = (d['source_id'], d['sampling_rule'], d['kind'])
        require(series.setdefault(d['series_id'], binding) == binding, 'series definition conflict')
        same_content = (d['series_id'], d['input_sha256'])
        require(same_content not in content, 'same content registered twice'); content.add(same_content)
        for day in dates_checked(d['dates']):
            coverage_key = (d['series_id'], day)
            require(coverage_key not in coverage, 'date overlap in registry'); coverage.add(coverage_key)
    return data


def register_batch(root, registry_path, descriptor):
    root = Path(root).resolve(); path = local_path(root, str(registry_path))
    data = load_registry(root, path); candidate = inspect_batch(root, descriptor)
    d = candidate['descriptor']
    for existing in data['batches']:
        e = existing['descriptor']
        if e['series_id'] != d['series_id']:
            continue
        require((e['source_id'], e['sampling_rule'], e['kind']) == (d['source_id'], d['sampling_rule'], d['kind']), 'series definition conflict')
        if logical_id(e) == logical_id(d):
            require(inspect_batch(root, e) == existing, 'selected batch changed')
            require(all(existing[k] == candidate[k] for k in ('summary', 'daily'))
                    and e['dates'] == d['dates'] and e['expected_records'] == d['expected_records'], 'logical input conflict')
            return {'status': 'already_registered', 'selected_run': e['run_id']}
        require(e['input_sha256'] != d['input_sha256'], 'same content with changed identity')
        require(not set(e['dates']) & set(d['dates']), 'unauthorized date overlap')
    data['batches'].append(candidate)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.pending')
    try:
        with temporary.open('x') as stream:
            json.dump(data, stream, indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {'status': 'registered', 'selected_run': d['run_id']}


def registered_batch_matches(current, registered, *, allow_criteo_manifest_extension=False):
    """Opt-in compatibility for one audited Criteo-only manifest extension.

    The exact two file hashes bind the old REES46 evidence and the accepted
    T0.4 Criteo addition. All other evidence and batch values remain exact.
    This does not refresh the registry or allow arbitrary future extensions.
    """
    if current == registered:
        return True
    if not allow_criteo_manifest_extension:
        return False
    name = 'data/manifest.json'
    pair = (registered.get('evidence', {}).get(name), current.get('evidence', {}).get(name))
    if pair != ('f6fde65d4a8f2f8051456b5ed744233e08ea1881ee5ec50a539cd3d2772237ad',
                '39089916016724996b3b8c6f204aa35e4a5a9978b3729bdc1cf67276529667f3'):
        return False
    adjusted = {**current, 'evidence': {**current['evidence'], name: pair[0]}}
    return adjusted == registered


class FactReader:
    """One cached Parquet materialization per batch in this reader; explicit close."""

    def __init__(self, spark, root, registry_path, series_id, *, allow_criteo_manifest_extension=False):
        self.spark = spark; self.root = Path(root).resolve(); self.path = registry_path; self.series = series_id
        self.frames = {}; self.parquet_loads = 0; self.read_checks = {}
        self.allow_criteo_manifest_extension = allow_criteo_manifest_extension

    def read(self, dates, purpose, *, expected_scopes):
        from pyspark.sql import functions as F
        from pyspark import StorageLevel
        requested = dates_checked(dates)
        require(purpose in ('count', 'amount'), 'unsupported purpose')
        require(isinstance(expected_scopes, list) and expected_scopes and len(set(expected_scopes)) == len(expected_scopes), 'explicit unique scopes required')
        entries = [e for e in load_registry(self.root, self.path)['batches'] if e['descriptor']['series_id'] == self.series]
        chosen = [e for e in entries if set(e['descriptor']['dates']) & set(requested)]
        require(chosen and set(expected_scopes) == {e['descriptor']['scope_id'] for e in chosen}, 'unregistered range or scope mismatch')
        require(set(requested) <= {day for e in chosen for day in e['descriptor']['dates']}, 'requested date absent')
        for entry in chosen:
            require(registered_batch_matches(inspect_batch(self.root, entry['descriptor']), entry,
                    allow_criteo_manifest_extension=self.allow_criteo_manifest_extension),
                    'registered evidence or files changed')
            for day in set(requested) & set(entry['descriptor']['dates']):
                gate = entry['gates'][day]
                require(gate[purpose + '_allowed'], 'quality blocked ' + day + ': ' + ','.join(gate['reason_codes']))
        frames = []
        for entry in chosen:
            d = entry['descriptor']; key = logical_id(d)
            if key not in self.frames:
                paths = [str(self.root / item['path']) for item in entry['inventory']]
                frame = self.spark.read.parquet(*paths)
                events = importlib.import_module('etl.01_events')
                require(frame.schema == events.schema(), 'actual fact schema mismatch')
                frame = frame.persist(StorageLevel.MEMORY_AND_DISK)
                self.frames[key] = frame; self.parquet_loads += 1
                try:
                    correct = F.lit(True)
                    for name in (*IDENTITY, 'run_id'):
                        correct = correct & F.col(name).eqNullSafe(F.lit(d[name]))
                    aggregates = frame.groupBy('event_date_utc').agg(F.count('*').alias('records'),
                        F.sum(F.col('event_eligible').cast('long')).alias('events'),
                        F.sum(F.col('amount_eligible').cast('long')).alias('amounts'),
                        F.sum(F.when(correct, 0).otherwise(1)).alias('bad_provenance')).limit(65).collect()
                    require(len(aggregates) <= 64, 'too many date groups')
                    actual = {(r['event_date_utc'].isoformat() if r['event_date_utc'] else '__invalid_time__'):
                              [r['records'], r['events'], r['amounts'], r['bad_provenance']] for r in aggregates}
                    expected = {day: [s['record_count'], s['flags']['event_eligible'], s['flags']['amount_eligible'], 0]
                                for day, s in entry['daily'].items()}
                    require(actual == expected, 'actual Parquet counts/eligibility/provenance mismatch')
                    self.read_checks[d['run_id']] = {'expected': expected, 'actual': actual, 'pass': True}
                except BaseException:
                    self.frames.pop(key).unpersist()
                    raise
            frames.append(self.frames[key].where(F.col('event_date_utc').cast('string').isin(requested) & F.col('event_eligible')))
        # The amount purpose intentionally keeps views/carts and both flags.
        return reduce(lambda a, b: a.unionByName(b), frames)

    def close(self):
        for frame in self.frames.values():
            frame.unpersist()
        self.frames.clear()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
