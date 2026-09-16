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
CONTRACT = 'rees46-events-engineering-v1'
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


def load_events_config(path, root):
    root = Path(root).resolve()
    try:
        data = yaml.load(Path(path).read_text(), Loader=UniqueKeyLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError('events configuration must exist and be valid YAML') from exc
    _mapping(data, ['kind', 'input_path', 'input_sha256', 'scope_id', 'source_id',
                    'expected_records', 'output_root'], 'events')
    if data['kind'] not in ('engineering_sample', 'synthetic'):
        raise ConfigError('only engineering_sample or synthetic is authorized')
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
    elif not (data['expected_records'] <= 1000 and data['source_id'] == 'synthetic'
              and data['scope_id'].startswith('synthetic_')
              and data['input_path'].is_relative_to(root / '.local/t11/synthetic')):
        raise ConfigError('synthetic input must be explicitly labeled, isolated, and <=1000 rows')
    if sha256(data['input_path']) != data['input_sha256']:
        raise ConfigError('input content SHA256 mismatch')
    return data
