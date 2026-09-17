-- name: keys
SELECT f.*,
  named_struct(
    'time', named_struct('value', event_timestamp_utc,
      'raw_unparsed', IF(event_timestamp_utc IS NULL, event_time, NULL),
      'missing', time_missing, 'invalid', time_invalid),
    'behavior', event_type, 'product', product_id, 'category_id', category_id,
    'category_code', category_code, 'brand', brand,
    'price', named_struct('value', price_decimal,
      'raw_unparsed', IF(price_decimal IS NULL, price, NULL),
      'missing', price_missing, 'invalid', price_invalid, 'nonfinite', price_nonfinite,
      'precision', price_precision_exceeded, 'scale', price_scale_exceeded,
      'negative', price_negative, 'zero', price_zero),
    'user', user_id, 'session', user_session) AS candidate_key,
  named_struct('time', event_time, 'behavior', event_type, 'product', product_id,
    'category_id', category_id, 'category_code', category_code, 'brand', brand,
    'price', price, 'user', user_id, 'session', user_session) AS raw_key
FROM q_input f
;
-- name: normalized_groups
SELECT candidate_key, event_type, user_id, COUNT(*) AS group_size,
  SUM(CASE WHEN amount_eligible THEN price_decimal ELSE CAST(0 AS DECIMAL(18,2)) END) AS group_amount,
  MAX(CASE WHEN amount_eligible THEN price_decimal ELSE CAST(0 AS DECIMAL(18,2)) END) AS retained_amount
FROM q_keys
GROUP BY candidate_key, event_type, user_id
;
-- name: raw_groups
SELECT raw_key, event_type, user_id, COUNT(*) AS group_size,
  SUM(CASE WHEN amount_eligible THEN price_decimal ELSE CAST(0 AS DECIMAL(18,2)) END) AS group_amount,
  MAX(CASE WHEN amount_eligible THEN price_decimal ELSE CAST(0 AS DECIMAL(18,2)) END) AS retained_amount
FROM q_keys
GROUP BY raw_key, event_type, user_id
;
-- name: joined
SELECT k.*, d.group_size AS duplicate_group_size
FROM q_keys k
LEFT JOIN q_duplicates d ON k.candidate_key <=> d.candidate_key
;
-- name: summary
SELECT IF(GROUPING(event_type)=1, '__all__', event_type) AS behavior,
  COUNT(*) AS duplicate_groups,
  COALESCE(SUM(group_size),0) AS involved_events,
  COALESCE(SUM(group_size-1),0) AS excess_events,
  COUNT(DISTINCT user_id) AS involved_users,
  COALESCE(SUM(IF(event_type='purchase',group_size,0)),0) AS purchase_involved_events,
  COALESCE(SUM(IF(event_type='purchase',group_size-1,0)),0) AS purchase_excess_events,
  COALESCE(SUM(group_amount-retained_amount),CAST(0 AS DECIMAL(38,2))) AS hypothetical_purchase_amount_reduction
FROM q_groups_for_summary
WHERE group_size > 1
GROUP BY GROUPING SETS ((),(event_type))
;
-- name: one_per_group
SELECT * FROM (
  SELECT l.*, ROW_NUMBER() OVER (PARTITION BY candidate_key ORDER BY raw_key) AS hypothetical_rank
  FROM q_labeled l
) ranked
WHERE hypothetical_rank=1
