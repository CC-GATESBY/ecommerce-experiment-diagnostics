WITH firsts AS (
 SELECT scope_id, user_id, MIN(event_date_utc) AS first_date FROM m_fact GROUP BY scope_id,user_id
), a AS (
 SELECT f.scope_id, f.event_date_utc AS utc_date,
 COUNT(DISTINCT f.user_id) AS active_users,
 COUNT(DISTINCT CASE WHEN f.event_type='purchase' THEN f.user_id END) AS buyers,
 COUNT(*) AS event_records, COUNT_IF(f.event_type='view') AS view_events, COUNT_IF(f.event_type='cart') AS cart_events,
 COUNT_IF(f.event_type='remove_from_cart') AS remove_from_cart_events, COUNT_IF(f.event_type='purchase') AS purchase_events,
 COUNT(DISTINCT CASE WHEN NOT f.session_missing THEN NAMED_STRUCT('u',f.user_id,'s',f.user_session) END) AS sessions,
 COUNT(DISTINCT CASE WHEN NOT f.session_missing AND f.event_type='purchase' THEN NAMED_STRUCT('u',f.user_id,'s',f.user_session) END) AS purchase_sessions,
 SUM(CASE WHEN f.amount_eligible THEN CAST(f.price_decimal AS DECIMAL(38,2)) ELSE CAST(0 AS DECIMAL(38,2)) END) AS observed_amount,
 COUNT_IF(f.event_type='purchase' AND NOT f.amount_eligible) AS purchase_amount_bad,
 COUNT_IF(f.amount_eligible) AS purchase_amount_valid, COUNT_IF(f.amount_eligible AND f.price_zero) AS purchase_zero_events,
 COUNT(DISTINCT CASE WHEN f.event_date_utc=s.first_date THEN f.user_id END) AS first_seen_users
 FROM m_fact f JOIN firsts s ON f.scope_id=s.scope_id AND f.user_id=s.user_id
 GROUP BY f.scope_id,f.event_date_utc
)
SELECT a.scope_id,a.utc_date,a.active_users,a.buyers,a.event_records,a.view_events,a.cart_events,
 a.remove_from_cart_events,a.purchase_events,a.sessions,a.purchase_sessions,
 CASE WHEN g.amount_allowed THEN a.observed_amount ELSE CAST(NULL AS DECIMAL(38,2)) END AS purchase_amount,
 a.purchase_amount_bad,a.purchase_amount_valid,a.purchase_zero_events,a.first_seen_users,
 g.count_allowed,g.amount_allowed,g.amount_status,g.reason_codes AS date_reason_codes
FROM a JOIN m_gates g ON a.utc_date=g.utc_date
