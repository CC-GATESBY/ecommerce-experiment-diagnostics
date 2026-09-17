-- One bounded UTC-hour result. Distinct users are local to each hour.
SELECT HOUR(event_timestamp_utc) AS utc_hour,
       COUNT(*) AS purchase_events,
       COUNT(DISTINCT user_id) AS purchase_users,
       SUM(CASE WHEN amount_eligible THEN CAST(price_decimal AS DECIMAL(38,2))
                ELSE CAST(0 AS DECIMAL(38,2)) END) AS purchase_amount
FROM behavior_fact
WHERE event_type='purchase'
GROUP BY HOUR(event_timestamp_utc)
ORDER BY utc_hour
