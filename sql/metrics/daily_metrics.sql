WITH a AS (
 SELECT scope_id, utc_date, COUNT(*) AS active_users, COUNT_IF(is_buyer) AS buyers,
 SUM(event_records) AS event_records, SUM(view_events) AS view_events, SUM(cart_events) AS cart_events,
 SUM(remove_from_cart_events) AS remove_from_cart_events, SUM(purchase_events) AS purchase_events,
 SUM(sessions) AS sessions, SUM(purchase_sessions) AS purchase_sessions,
 SUM(purchase_amount) AS purchase_amount, SUM(purchase_amount_bad) AS purchase_amount_bad,
 SUM(purchase_amount_valid) AS purchase_amount_valid, SUM(purchase_zero_events) AS purchase_zero_events,
 COUNT_IF(is_first_seen_day) AS first_seen_users
 FROM m_user_daily GROUP BY scope_id, utc_date
)
SELECT a.*, g.count_allowed, g.amount_allowed, g.amount_status, g.reason_codes AS date_reason_codes
FROM a JOIN m_gates g ON a.utc_date=g.utc_date
