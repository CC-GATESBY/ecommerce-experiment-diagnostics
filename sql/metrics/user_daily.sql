WITH a AS (
 SELECT scope_id, event_date_utc AS utc_date, user_id, is_first_seen_day,
  COUNT(*) AS event_records,
  COUNT_IF(event_type='view') AS view_events,
  COUNT_IF(event_type='cart') AS cart_events,
  COUNT_IF(event_type='remove_from_cart') AS remove_from_cart_events,
  COUNT_IF(event_type='purchase') AS purchase_events,
  COUNT(DISTINCT CASE WHEN NOT session_missing THEN user_session END) AS sessions,
  COUNT(DISTINCT CASE WHEN NOT session_missing AND event_type='purchase' THEN user_session END) AS purchase_sessions,
  COUNT_IF(event_type='purchase' AND NOT amount_eligible) AS purchase_amount_bad,
  COUNT_IF(amount_eligible) AS purchase_amount_valid,
  COUNT_IF(amount_eligible AND price_zero) AS purchase_zero_events,
  SUM(CASE WHEN amount_eligible THEN CAST(price_decimal AS DECIMAL(38,2)) ELSE CAST(0 AS DECIMAL(38,2)) END) AS observed_amount
 FROM m_events GROUP BY scope_id, event_date_utc, user_id, is_first_seen_day
)
SELECT a.scope_id, a.utc_date, a.user_id, a.event_records, a.view_events, a.cart_events,
 a.remove_from_cart_events, a.purchase_events, a.sessions, a.purchase_sessions,
 a.purchase_events>0 AS is_buyer, a.is_first_seen_day,
 CASE WHEN g.amount_allowed THEN a.observed_amount ELSE CAST(NULL AS DECIMAL(38,2)) END AS purchase_amount,
 a.purchase_amount_bad, a.purchase_amount_valid, a.purchase_zero_events,
 CASE WHEN a.purchase_events=0 THEN 'no_purchases' WHEN a.purchase_amount_bad=0 THEN 'complete_observed'
      WHEN a.purchase_amount_valid>0 THEN 'partial_observed' ELSE 'unknown' END AS amount_status,
 g.count_allowed, g.amount_allowed, g.reason_codes AS date_reason_codes
FROM a JOIN m_gates g ON a.utc_date=g.utc_date
