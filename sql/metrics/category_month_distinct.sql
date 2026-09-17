-- Inject the two frozen T1.3 category expressions verbatim, without other dimensions.
WITH categorized AS (
 SELECT f.*, __CATEGORY_PROJECTION__
 FROM category_fact f
)
SELECT scope_id, category_key, category_label,
       COUNT(DISTINCT user_id) AS users,
       COUNT(DISTINCT CASE WHEN event_type='purchase' THEN user_id END) AS buyers,
       COUNT(*) AS event_records,
       COUNT_IF(event_type='purchase') AS purchase_events,
       SUM(CASE WHEN amount_eligible THEN CAST(price_decimal AS DECIMAL(38,2))
                ELSE CAST(0 AS DECIMAL(38,2)) END) AS purchase_amount
FROM categorized
GROUP BY scope_id, category_key, category_label
ORDER BY scope_id, category_key, category_label
