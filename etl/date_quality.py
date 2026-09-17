"""Frozen conservative date/use policy; never infer absent dates as zeros."""

from datetime import date
from etl.event_config import CONTRACT

POLICY = 'rees46-date-quality-v1'
CORE = ('time_missing', 'time_invalid', 'user_id_missing', 'user_id_invalid', 'event_type_unknown')
WARNINGS = ('brand_missing', 'category_code_missing', 'session_missing',
            'product_id_missing', 'product_id_invalid', 'category_id_missing', 'category_id_invalid')
PRICE_BAD = ('price_missing', 'price_invalid', 'price_nonfinite', 'price_negative',
             'price_precision_exceeded', 'price_scale_exceeded')


def dates_checked(values):
    if not isinstance(values, list) or not values or len(values) > 366 or len(set(values)) != len(values):
        raise ValueError('explicit, unique dates required (1..366)')
    for value in values:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError('ISO UTC dates required')
    return sorted(values)


def evaluate(identity, daily, expected_dates, evidence_valid=True):
    """Input evidence is validated by the registry, not supplied by downstream users."""
    dates = dates_checked(expected_dates)
    batch_reasons = []
    if not evidence_valid or identity['contract_version'] != CONTRACT:
        batch_reasons.append('invalid_batch_evidence')
    if any(k not in dates for k in daily):
        batch_reasons.append('unassigned_or_outside_date')
    if any(day['flags']['time_missing'] or day['flags']['time_invalid'] for day in daily.values()):
        batch_reasons.append('batch_time_unassignable')
    result = {}
    for day in dates:
        reasons = list(batch_reasons); warnings = {}; counts = daily.get(day)
        if not counts or counts['record_count'] <= 0:
            reasons.append('date_not_observed')
            eligible = records = 0
        else:
            records = counts['record_count']; flags = counts['flags']; eligible = flags['event_eligible']
            reasons += ['core_' + key for key in CORE if flags[key]]
            if eligible != records:
                reasons.append('ineligible_events')
            warnings = {key: flags[key] for key in WARNINGS if flags[key]}
            for behavior, count in counts['zero_by_behavior'].items():
                if count:
                    warnings['zero_price_' + behavior] = count
            if any(flags[key] for key in PRICE_BAD) and not counts['purchase_price_bad_all']:
                warnings['nonpurchase_price_quality'] = 'present'
        count_allowed = not reasons
        amount_reasons = []
        if counts:
            purchases = counts['behaviors'].get('purchase', 0)
            valid_amount = (counts['amount_status'] == 'complete_observed' and purchases > 0
                            and counts['purchase_events'] == purchases
                            and counts['flags']['amount_eligible'] == purchases
                            and counts['purchase_amount'] is not None)
            structural_zero = (counts['amount_status'] == 'no_purchases' and purchases == 0
                               and counts['purchase_events'] == 0 and counts['flags']['amount_eligible'] == 0
                               and counts['purchase_amount'] == '0.00')
            if (not (valid_amount or structural_zero) or counts['purchase_price_bad_all']
                    or counts['purchase_price_bad_eligible']):
                amount_reasons.append('purchase_amount_incomplete')
        amount_allowed = count_allowed and not amount_reasons
        result[day] = dict(identity, utc_date=day, policy_version=POLICY,
                          count_allowed=count_allowed, amount_allowed=amount_allowed,
                          status='blocked' if not count_allowed else 'count_only' if not amount_allowed
                          else 'allowed_with_warnings' if warnings else 'allowed',
                          reason_codes=sorted(set(reasons + amount_reasons)), warnings=warnings,
                          record_count=records, event_eligible_records=eligible,
                          core_ineligible_records=records - eligible,
                          amount_status=counts['amount_status'] if counts else 'not_observed',
                          evidence='completed_receipts+independent_multisets+daily_counts+immutable_file_hashes',
                          release_scope='T1.1_data_use_conditions_only')
    return result
