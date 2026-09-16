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
    flags['price_nonfinite'] = value.lower().lstrip('+-') in ('nan', 'snan', 'inf', 'infinity')
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


def build_expected(source, destination, expected_records):
    counts = Counter({name: 0 for name in FLAGS})
    behaviors = Counter()
    users, buyers = set(), set()  # Hard capped at 100000 input records by configuration.
    total = Decimal('0.00')
    qualified_purchases = bad_purchases = bad_all_purchases = n = 0
    earliest = latest = None
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
            for flag in FLAGS:
                counts[flag] += item[flag]
            behaviors[row[1] if row[1] in ALLOWED else '__unknown__'] += 1
            stamp = item['event_timestamp_utc']
            if stamp:
                earliest = min(earliest, stamp) if earliest else stamp
                latest = max(latest, stamp) if latest else stamp
            price_ok = item['price_decimal'] is not None and not item['price_negative']
            if row[1] == 'purchase' and not price_ok:
                bad_all_purchases += 1
            if item['event_eligible']:
                users.add(row[7])
                if row[1] == 'purchase':
                    buyers.add(row[7]); qualified_purchases += 1
                    if not price_ok:
                        bad_purchases += 1
            if item['amount_eligible']:
                total += Decimal(item['price_decimal'])
        if n != expected_records:
            raise ValueError(f'input count mismatch: {n} != {expected_records}')
    state = 'no_purchases' if not qualified_purchases else ('complete_observed' if not bad_purchases else 'partial_observed' if counts['amount_eligible'] else 'unknown')
    summary = dict(record_count=n, flags=dict(counts), behaviors=dict(behaviors),
                   users=len(users), buyers=len(buyers), purchase_events=qualified_purchases,
                   purchase_price_bad_all=bad_all_purchases,
                   purchase_price_bad_eligible=bad_purchases,
                   purchase_amount=format(total, '.2f') if counts['amount_eligible'] or not qualified_purchases else None,
                   amount_status=state, time_min=earliest, time_max=latest)
    return summary
