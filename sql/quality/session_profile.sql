-- name: profiles
SELECT user_id, user_session, COUNT(*) AS session_events,
  SUM(IF(event_type='purchase',1,0)) AS session_purchases,
  SUM(CASE WHEN amount_eligible THEN price_decimal ELSE CAST(0 AS DECIMAL(18,2)) END) AS session_observed_amount,
  MIN(event_timestamp_utc) AS first_time_utc, MAX(event_timestamp_utc) AS last_time_utc,
  COUNT(DISTINCT event_date_utc) AS observed_dates,
  UNIX_TIMESTAMP(MAX(event_timestamp_utc))-UNIX_TIMESTAMP(MIN(event_timestamp_utc)) AS observed_span_seconds,
  COUNT(*) > __HEAVY_THRESHOLD__ AS heavy_session
FROM q_input
WHERE NOT user_id_missing AND NOT user_id_invalid AND NOT session_missing
  AND user_id IS NOT NULL AND user_session IS NOT NULL
GROUP BY user_id, user_session
;
-- name: joined
SELECT f.*, s.session_events, s.heavy_session, s.observed_span_seconds, s.observed_dates
FROM q_duplicate_labeled f
LEFT JOIN q_sessions s
  ON NOT f.session_missing AND NOT f.user_id_missing AND NOT f.user_id_invalid
  AND f.user_id <=> s.user_id AND f.user_session <=> s.user_session
;
-- name: session_only_joined
SELECT f.*, s.session_events, s.heavy_session
FROM q_input f
LEFT JOIN q_sessions s
  ON NOT f.session_missing AND NOT f.user_id_missing AND NOT f.user_id_invalid
  AND f.user_id <=> s.user_id AND f.user_session <=> s.user_session
;
-- name: summary
SELECT COUNT(*) AS valid_sessions,
  percentile_approx(session_events,array(0.5D,0.9D,0.99D),10000) AS event_count_quantiles,
  MAX(session_events) AS max_session_events,
  COALESCE(SUM(IF(heavy_session,1,0)),0) AS heavy_sessions,
  COALESCE(SUM(IF(heavy_session,session_events,0)),0) AS heavy_events,
  COUNT(DISTINCT IF(heavy_session,user_id,NULL)) AS heavy_users,
  COALESCE(SUM(IF(heavy_session,session_purchases,0)),0) AS heavy_purchase_events,
  COALESCE(SUM(IF(heavy_session,session_observed_amount,CAST(0 AS DECIMAL(38,2)))),CAST(0 AS DECIMAL(38,2))) AS heavy_purchase_amount,
  COALESCE(SUM(IF(observed_dates>1,1,0)),0) AS cross_day_sessions,
  percentile_approx(observed_span_seconds,array(0.5D,0.9D,0.99D),10000) AS span_seconds_quantiles,
  MAX(observed_span_seconds) AS max_observed_span_seconds,
  percentile_approx(IF(observed_dates>1,observed_span_seconds,NULL),array(0.5D,0.9D,0.99D),10000) AS cross_day_span_seconds_quantiles,
  MAX(IF(observed_dates>1,observed_span_seconds,NULL)) AS max_cross_day_span_seconds
FROM q_sessions
;
-- name: baseline_keep_all
SELECT * FROM q_labeled
;
-- name: exclude_heavy
SELECT * FROM q_labeled WHERE NOT COALESCE(heavy_session,FALSE)
;
-- name: measures
SELECT IF(GROUPING(event_date_utc)=1,'__all__',CAST(event_date_utc AS STRING)) AS period,
  COUNT(*) AS events, COUNT(DISTINCT user_id) AS users,
  COUNT(DISTINCT IF(event_type='purchase',user_id,NULL)) AS buyers,
  COALESCE(SUM(IF(event_type='purchase',1,0)),0) AS purchase_events,
  COALESCE(SUM(CASE WHEN amount_eligible THEN price_decimal ELSE CAST(0 AS DECIMAL(18,2)) END),CAST(0 AS DECIMAL(38,2))) AS purchase_amount,
  COALESCE(SUM(IF(event_type='view',1,0)),0) AS views,
  COALESCE(SUM(IF(event_type='cart',1,0)),0) AS carts,
  COALESCE(SUM(IF(event_type='remove_from_cart',1,0)),0) AS removes,
  COALESCE(SUM(IF(session_missing,1,0)),0) AS missing_session_events
FROM q_measure_input
GROUP BY GROUPING SETS ((),(event_date_utc))
