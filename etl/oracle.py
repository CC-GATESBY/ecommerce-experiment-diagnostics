"""Independent stdlib expected values, computed before starting Spark.

Only field names/contract constants are shared with the Spark implementation.
No Spark parsing functions or aggregate results are used as expected values.
"""

from collections import Counter
import csv
from datetime import datetime, timezone
from decimal import Decimal
import json
import re
import sqlite3
import time

from etl.event_config import ALLOWED, FLAGS, HEADER


def oracle_row(row):
    result = dict(zip(HEADER, row))
    flags = {name: False for name in FLAGS}
    missing = lambda value: value.strip(' \t\r\n\v\f') == ''
    flags['time_missing'] = missing(row[0])
    stamp = None
    if not flags['time_missing']:
        try:
            if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} UTC', row[0]):
                raise ValueError('format')
            stamp = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S UTC').replace(tzinfo=timezone.utc)
        except ValueError:
            flags['time_invalid'] = True
    result['event_timestamp_utc'] = stamp.isoformat(timespec='seconds') if stamp else None
    result['event_date_utc'] = stamp.date().isoformat() if stamp else None
    for name in ('user_id', 'product_id', 'category_id'):
        raw = result[name]
        flags[name + '_missing'] = missing(raw)
        flags[name + '_invalid'] = not missing(raw) and re.fullmatch('[0-9]+', raw) is None
    for raw_name, flag_name in [('category_code', 'category_code_missing'),
                                ('brand', 'brand_missing'), ('user_session', 'session_missing')]:
        flags[flag_name] = missing(result[raw_name])
    flags['event_type_unknown'] = row[1] not in ALLOWED
    value = row[6]
    flags['price_missing'] = missing(value)
    flags['price_nonfinite'] = re.fullmatch(r'[+-]?(?:s?nan|inf|infinity)', value.lower()) is not None
    match = re.fullmatch(r'[+-]?([0-9]+)(?:\.([0-9]+))?', value)
    flags['price_invalid'] = not flags['price_missing'] and not match and not flags['price_nonfinite']
    amount = None
    if match:
        number = Decimal(value)
        flags['price_negative'] = number < 0
        flags['price_zero'] = number == 0
        flags['price_precision_exceeded'] = len(match[1].lstrip('0') or '0') > 16
        flags['price_scale_exceeded'] = len(match[2] or '') > 2
        if not flags['price_precision_exceeded'] and not flags['price_scale_exceeded']:
            amount = number.quantize(Decimal('0.01'))
    result['price_decimal'] = format(amount, '.2f') if amount is not None else None
    # Canonical SQL Decimal has no negative signed zero.
    if amount == 0:
        result['price_decimal'] = '0.00'
    flags['event_eligible'] = stamp is not None and not flags['user_id_missing'] and not flags['user_id_invalid'] and not flags['event_type_unknown']
    flags['amount_eligible'] = flags['event_eligible'] and row[1] == 'purchase' and amount is not None and amount >= 0
    result.update({name: bool(value) for name, value in flags.items()})
    return result


class Accumulator:
    """Bounded per-date counters, independent of Spark expressions."""
    def __init__(self):
        self.flags = Counter({name: 0 for name in FLAGS})
        self.behaviors = Counter()
        self.zeros = Counter({name: 0 for name in (*ALLOWED, '__unknown__')})
        self.amount = Decimal('0.00')
        self.records = self.purchases = self.bad = self.bad_all = 0
        self.earliest = self.latest = None

    def add(self, item):
        self.records += 1
        for key in FLAGS:
            self.flags[key] += item[key]
        behavior = item['event_type'] if item['event_type'] in ALLOWED else '__unknown__'
        self.behaviors[behavior] += 1
        self.zeros[behavior] += item['price_zero']
        stamp = item['event_timestamp_utc']
        if stamp:
            self.earliest = min(self.earliest, stamp) if self.earliest else stamp
            self.latest = max(self.latest, stamp) if self.latest else stamp
        bad = item['price_decimal'] is None or item['price_negative']
        if item['event_type'] == 'purchase':
            self.bad_all += bad
            if item['event_eligible']:
                self.purchases += 1
                self.bad += bad
        if item['amount_eligible']:
            self.amount += Decimal(item['price_decimal'])

    def finish(self, db, bucket):
        raw, users, buyers = db.execute('SELECT COUNT(*), COALESCE(SUM(eligible),0), COALESCE(SUM(buyer),0) FROM ids WHERE bucket=?', (bucket,)).fetchone()
        state = 'no_purchases' if not self.purchases else ('complete_observed' if not self.bad else 'partial_observed' if self.flags['amount_eligible'] else 'unknown')
        return dict(record_count=self.records, flags=dict(self.flags), behaviors=dict(self.behaviors),
                    zero_by_behavior=dict(self.zeros), raw_users=raw, users=users, buyers=buyers,
                    purchase_events=self.purchases, purchase_price_bad_all=self.bad_all,
                    purchase_price_bad_eligible=self.bad,
                    purchase_amount=format(self.amount, '.2f') if self.flags['amount_eligible'] or not self.purchases else None,
                    amount_status=state, time_min=self.earliest, time_max=self.latest)


def build_expected(source, destination, expected_records, budget_check=None):
    database = destination.with_suffix('.sqlite3')
    if database.exists():
        raise FileExistsError('oracle SQLite output already exists')
    db = sqlite3.connect(database)
    started = time.monotonic()
    total = Accumulator(); daily = {}; batch = []; n = 0
    def flush():
        db.executemany('INSERT INTO ids VALUES (?,?,?,?) ON CONFLICT(bucket,user_id) DO UPDATE SET eligible=MAX(eligible,excluded.eligible),buyer=MAX(buyer,excluded.buyer)', batch)
        db.commit(); batch.clear()
    try:
        db.execute('PRAGMA cache_size=-4096')
        db.execute('PRAGMA temp_store=FILE')
        db.execute('CREATE TABLE ids(bucket TEXT COLLATE BINARY, user_id TEXT COLLATE BINARY, eligible INTEGER, buyer INTEGER, PRIMARY KEY(bucket,user_id)) WITHOUT ROWID')
        with source.open(encoding='utf-8', newline='') as stream, destination.open('x', encoding='utf-8') as output:
            reader = csv.reader(stream, strict=True)
            if next(reader, None) != HEADER:
                raise ValueError('CSV header must match the nine raw fields exactly')
            for row in reader:
                n += 1
                if n > expected_records or len(row) != 9:
                    raise ValueError(f'CSV structure/count failure at data record {n}')
                item = oracle_row(row)
                output.write(json.dumps(item, ensure_ascii=False, separators=(',', ':')) + '\n')
                bucket = item['event_date_utc'] or '__invalid_time__'
                if bucket not in daily:
                    if len(daily) >= 64:
                        raise ValueError('more than 64 date buckets; authorization requires revalidation')
                    daily[bucket] = Accumulator()
                total.add(item); daily[bucket].add(item)
                eligible = int(item['event_eligible']); buyer = int(item['event_eligible'] and item['event_type'] == 'purchase')
                batch.extend([('*', row[7], eligible, buyer), (bucket, row[7], eligible, buyer)])
                if len(batch) >= 4096:
                    flush()
                if n % 10000 == 0 and budget_check:
                    output.flush(); budget_check()
                if n % 250000 == 0:
                    print(json.dumps(dict(phase='oracle', processed_records=n, elapsed_seconds=round(time.monotonic()-started, 2))), flush=True)
            if n != expected_records:
                raise ValueError(f'input count mismatch: {n} != {expected_records}')
        flush()
        result = total.finish(db, '*')
        dates = {key: value.finish(db, key) for key, value in sorted(daily.items())}
        with destination.with_name('expected_daily.json').open('x') as stream:
            json.dump(dates, stream, indent=2); stream.write('\n')
        if budget_check:
            budget_check()
        return result
    finally:
        db.close()
