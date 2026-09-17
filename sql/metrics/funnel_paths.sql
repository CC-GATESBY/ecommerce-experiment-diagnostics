-- Each valid key has exactly one origin across the entire observation window.
CREATE OR REPLACE TEMP VIEW f_starts AS
SELECT scope_id,user_id,user_session,product_id,MIN(event_timestamp_utc) AS first_view_time
FROM f_events WHERE path_key_valid AND event_type='view'
GROUP BY scope_id,user_id,user_session,product_id;

-- Unique-key left join preserves every eligible event, including invalid keys.
CREATE OR REPLACE TEMP VIEW f_linked AS
SELECT e.*,s.first_view_time,s.first_view_time + INTERVAL 24 HOURS AS deadline
FROM f_events e LEFT JOIN f_starts s
ON e.path_key_valid AND e.scope_id=s.scope_id AND e.user_id=s.user_id
AND e.user_session=s.user_session AND e.product_id=s.product_id;

WITH stages AS (
 SELECT scope_id,user_id,user_session,product_id,first_view_time,deadline,
   MIN(CASE WHEN event_type='cart' AND event_timestamp_utc>first_view_time AND event_timestamp_utc<=deadline THEN event_timestamp_utc END) AS strict_cart_time,
   MAX(CASE WHEN event_type='purchase' AND event_timestamp_utc>first_view_time AND event_timestamp_utc<=deadline THEN event_timestamp_utc END) AS strict_purchase_time,
   MIN(CASE WHEN event_type='cart' AND event_timestamp_utc>=first_view_time AND event_timestamp_utc<=deadline THEN event_timestamp_utc END) AS possible_cart_time,
   MAX(CASE WHEN event_type='purchase' AND event_timestamp_utc>=first_view_time AND event_timestamp_utc<=deadline THEN event_timestamp_utc END) AS possible_purchase_time,
   COUNT_IF(event_type='view' AND event_timestamp_utc=first_view_time AND (price_decimal IS NULL OR price_decimal<0)) AS first_view_bad_price_records,
   COUNT(DISTINCT CASE WHEN event_type='view' AND event_timestamp_utc=first_view_time AND price_decimal>=0 THEN price_decimal END) AS first_view_valid_price_count,
   MIN(CASE WHEN event_type='view' AND event_timestamp_utc=first_view_time AND price_decimal>=0 THEN price_decimal END) AS candidate_price
 FROM f_linked WHERE first_view_time IS NOT NULL
 GROUP BY scope_id,user_id,user_session,product_id,first_view_time,deadline
), flags AS (
 SELECT *,strict_cart_time IS NOT NULL AS has_cart_after_view,
   strict_purchase_time IS NOT NULL AS has_purchase_after_view,
   COALESCE(strict_cart_time<strict_purchase_time,FALSE) AS has_three_step,
   CASE WHEN first_view_valid_price_count>1 THEN 'conflicting'
        WHEN first_view_bad_price_records>0 OR first_view_valid_price_count<>1 THEN 'invalid_or_missing'
        ELSE 'unique_valid' END AS first_view_price_status
 FROM stages
), classes AS (
 SELECT *,CASE WHEN has_three_step THEN 'view_cart_purchase'
               WHEN has_purchase_after_view THEN 'view_purchase_no_confirmed_intermediate_cart'
               WHEN has_cart_after_view THEN 'view_cart_no_observed_purchase' ELSE 'view_only' END AS strict_class,
   CASE WHEN possible_cart_time<=possible_purchase_time THEN 'view_cart_purchase'
        WHEN possible_purchase_time IS NOT NULL THEN 'view_purchase_no_confirmed_intermediate_cart'
        WHEN possible_cart_time IS NOT NULL THEN 'view_cart_no_observed_purchase' ELSE 'view_only' END AS possible_class,
   CASE WHEN first_view_price_status='unique_valid' THEN candidate_price END AS first_view_price,
   first_view_time>=TIMESTAMP '2019-10-31 00:00:00' AS right_censored
 FROM flags
), release AS (
 SELECT *,strict_class<>possible_class AS order_uncertain,
   CASE WHEN right_censored THEN 'right_censored'
        WHEN strict_class<>possible_class THEN 'order_uncertain' ELSE 'formal' END AS release_status
 FROM classes
)
SELECT scope_id,user_id,user_session,product_id,first_view_time,CAST(first_view_time AS DATE) AS start_date_utc,deadline,
 strict_cart_time,strict_purchase_time,possible_cart_time,possible_purchase_time,
 has_cart_after_view,has_purchase_after_view,has_three_step,strict_class,possible_class,order_uncertain,right_censored,release_status,
 first_view_price,first_view_price_status,first_view_bad_price_records,first_view_valid_price_count,
 CASE WHEN first_view_price IS NULL THEN 'unknown' WHEN first_view_price<20 THEN '[0,20)'
      WHEN first_view_price<50 THEN '[20,50)' WHEN first_view_price<200 THEN '[50,200)' ELSE '[200,+inf)' END AS price_band
FROM release
