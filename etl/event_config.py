"""Strict input authorization and shared schema names; no value parsing here."""

import hashlib
import json
from pathlib import Path
import re

from scripts.project_config import ConfigError, UniqueKeyLoader, _mapping
import yaml

HEADER = ['event_time', 'event_type', 'product_id', 'category_id', 'category_code',
          'brand', 'price', 'user_id', 'user_session']
SHA = 'fe2cd808172c853217201660a98a8c8600fb0230f5c89efda45a9a1a2fdae754'
MONTH_SHA = '5bfc34f9c683a81ecb5eef6853a62ed454a76eca3244c9b7d80a426b8100055b'
MONTH_SCOPE = 'rees46_2019_oct_user5_fedd938409b5f836_20260916_v1'
MONTH_RECORDS = 2114081
MONTH_BYTES = 282405091
CONTRACT = 'rees46-events-v1.0.1'
ALLOWED = ('view', 'cart', 'remove_from_cart', 'purchase')
FLAGS = ['time_missing', 'time_invalid', 'user_id_missing', 'user_id_invalid',
         'product_id_missing', 'product_id_invalid', 'category_id_missing',
         'category_id_invalid', 'category_code_missing', 'brand_missing',
         'session_missing', 'event_type_unknown', 'price_missing', 'price_invalid',
         'price_nonfinite', 'price_negative', 'price_zero', 'price_precision_exceeded',
         'price_scale_exceeded', 'event_eligible', 'amount_eligible']
DERIVED = ['event_timestamp_utc', 'event_date_utc', 'price_decimal']
PROVENANCE = ['source_id', 'scope_id', 'input_sha256', 'contract_version', 'run_id',
              'parsed_at_utc']


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def csv_line_separator(path):
    # The strictly validated fixed header cannot contain a field-internal newline.
    with Path(path).open('rb') as stream:
        prefix = stream.read(4096)
    match = re.search(b'\r\n|\n|\r', prefix)
    if not match:
        raise ConfigError('CSV header record separator not found in bounded prefix')
    return match[0].decode('ascii')


def load_events_config(path, root):
    root = Path(root).resolve()
    try:
        data = yaml.load(Path(path).read_text(), Loader=UniqueKeyLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError('events configuration must exist and be valid YAML') from exc
    _mapping(data, ['kind', 'input_path', 'input_sha256', 'scope_id', 'source_id',
                    'expected_records', 'output_root'], 'events')
    if data['kind'] not in ('engineering_sample', 'synthetic', 'user_sample_candidate'):
        raise ConfigError('unregistered input kind')
    for name in ('input_path', 'output_root'):
        value = data[name]
        if not isinstance(value, str) or not value or '<' in value or '>' in value:
            raise ConfigError(f'{name}: fill a project-relative path')
        p = Path(value)
        if p.is_absolute() or '..' in p.parts:
            raise ConfigError(f'{name}: project-relative path without traversal required')
        data[name] = (root / p).resolve()
        if not data[name].is_relative_to(root / '.local'):
            raise ConfigError(f'{name}: must remain inside ignored .local')
    if not data['input_path'].is_file():
        raise ConfigError('exact input file does not exist; directories/globs are rejected')
    if not data['output_root'].is_dir() or not data['output_root'].is_relative_to(root / '.local/t11'):
        raise ConfigError('existing output_root under .local/t11 required')
    if data['input_path'].is_relative_to(data['output_root']):
        raise ConfigError('input and output must be separate')
    for key in ('scope_id', 'source_id'):
        if not isinstance(data[key], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', data[key]):
            raise ConfigError(f'invalid {key}')
    if type(data['expected_records']) is not int or data['expected_records'] < 1:
        raise ConfigError('positive exact expected_records required')
    if not isinstance(data['input_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', data['input_sha256']):
        raise ConfigError('input SHA256 required')
    if data['kind'] == 'engineering_sample':
        manifest = json.loads((root / 'data/manifest.json').read_text())
        accepted = manifest['engineering_samples'][0]
        if not (data['input_path'] == (root / accepted['local_relative_path']).resolve()
                and data['input_sha256'] == SHA == accepted['sha256']
                and data['scope_id'] == accepted['scope_id']
                and data['expected_records'] == accepted['record_count'] == 100000
                and data['source_id'] == 'rees46_multicategory_2019_oct'):
            raise ConfigError('this entry point only accepts the first registered 100000-row sample')
    elif data['kind'] == 'user_sample_candidate':
        validate_candidate(data, root)
    elif not (data['expected_records'] <= 1000 and data['source_id'] == 'synthetic'
              and data['scope_id'].startswith('synthetic_')
              and data['input_path'].is_relative_to(root / '.local/t11/synthetic')):
        raise ConfigError('synthetic input must be explicitly labeled, isolated, and <=1000 rows')
    if sha256(data['input_path']) != data['input_sha256']:
        raise ConfigError('input content SHA256 mismatch')
    return data


def validate_candidate(data, root):
    manifest = json.loads((root / 'data/manifest.json').read_text())
    candidates = [entry for entry in manifest.get('user_sample_candidates', []) if entry.get('scope_id') == MONTH_SCOPE]
    if len(candidates) != 1:
        raise ConfigError('exactly one approved registered candidate is required')
    accepted = candidates[0]; sample = accepted['sample']
    approved_path = (root / sample['local_relative_path']).resolve()
    if not (data['input_path'] == approved_path and data['scope_id'] == MONTH_SCOPE
            and data['expected_records'] == sample['profile']['record_count'] == MONTH_RECORDS
            and data['input_sha256'] == sample['sha256'] == MONTH_SHA
            and sample['bytes'] == approved_path.stat().st_size == MONTH_BYTES
            and data['source_id'] == 'rees46_multicategory_2019_oct'
            and accepted.get('kind') == 'user_sample_candidate' and accepted.get('status') == 'validated'
            and accepted.get('registration_status') == 'validated_input_candidate_not_business_accepted'):
        raise ConfigError('candidate identity, size, scope, status or type mismatch')
    receipt_path = approved_path.parent / 'receipt.json'
    if not receipt_path.is_file():
        raise ConfigError('candidate completed receipt is missing')
    receipt = json.loads(receipt_path.read_text())
    if not (receipt.get('status') == 'validated' and receipt.get('kind') == accepted['kind']
            and receipt.get('scope_id') == MONTH_SCOPE and receipt.get('run_id') == accepted['run_id']
            and receipt['sample']['sha256'] == MONTH_SHA and receipt['sample']['bytes'] == MONTH_BYTES
            and receipt['sample']['profile']['record_count'] == MONTH_RECORDS
            and receipt['sample']['profile_matches_extraction'] == 'pass'
            and receipt['sample']['serialization_and_sha256'] == 'pass'):
        raise ConfigError('candidate receipt does not prove a completed matching candidate')
