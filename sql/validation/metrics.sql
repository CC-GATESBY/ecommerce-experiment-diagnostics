-- Independent implementation: direct fact aggregation at each grain, FILTER aggregates,
-- row tuples for session identity, and a long-form dimension relation.
CREATE OR REPLACE TABLE d_dim_user_first_seen AS
SELECT scope_id,user_id,min(ts) AS first_seen_at_utc,CAST(min(ts) AS DATE) AS first_seen_date_utc
FROM eligible GROUP BY scope_id,user_id;

CREATE OR REPLACE TABLE d_brand_mapping AS
WITH frequency AS (
 SELECT brand,count(*) AS reference_events FROM eligible
 WHERE utc_date>=DATE '2019-10-01' AND utc_date<DATE '2019-10-08' AND NOT brand_missing GROUP BY brand
)
SELECT brand,reference_events,row_number() OVER(ORDER BY reference_events DESC,encode(brand)) AS brand_rank,
 'brand:'||brand AS dim_value_key,brand AS dim_value_label
FROM frequency QUALIFY brand_rank<=__TOP_K__;

CREATE OR REPLACE VIEW decorated AS
SELECT e.*,e.utc_date=f.first_seen_date_utc AS is_first_seen_day,
 CASE WHEN regexp_full_match(e.category_code,'[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*')
      THEN 'category:'||split_part(e.category_code,'.',1) ELSE 'bucket:unknown' END AS category_key,
 CASE WHEN regexp_full_match(e.category_code,'[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*')
      THEN split_part(e.category_code,'.',1) ELSE 'unknown' END AS category_label,
 CASE WHEN e.brand_missing THEN 'bucket:unknown' WHEN m.brand IS NOT NULL THEN m.dim_value_key ELSE 'bucket:other' END AS brand_key,
 CASE WHEN e.brand_missing THEN 'unknown' WHEN m.brand IS NOT NULL THEN m.dim_value_label ELSE 'other' END AS brand_label,
 CASE WHEN price_decimal IS NULL OR price_decimal<0 THEN 'bucket:unknown'
      WHEN price_decimal>=200 THEN 'band:200_plus' WHEN price_decimal>=50 THEN 'band:50_200'
      WHEN price_decimal>=20 THEN 'band:20_50' ELSE 'band:0_20' END AS price_key,
 CASE WHEN price_decimal IS NULL OR price_decimal<0 THEN 'unknown'
      WHEN price_decimal>=200 THEN '[200,+inf)' WHEN price_decimal>=50 THEN '[50,200)'
      WHEN price_decimal>=20 THEN '[20,50)' ELSE '[0,20)' END AS price_label
FROM eligible e JOIN d_dim_user_first_seen f USING(scope_id,user_id)
LEFT JOIN d_brand_mapping m ON e.brand=m.brand AND NOT e.brand_missing;

CREATE OR REPLACE MACRO observed_status(p,b,v) AS
 CASE WHEN p=0 THEN 'no_purchases' WHEN b=0 THEN 'complete_observed' WHEN v>0 THEN 'partial_observed' ELSE 'unknown' END;
CREATE OR REPLACE MACRO formal_amount(a,p,allowed) AS
 CASE WHEN NOT allowed THEN NULL WHEN p=0 THEN CAST(0 AS DECIMAL(38,2)) ELSE CAST(a AS DECIMAL(38,2)) END;

CREATE OR REPLACE TABLE d_agg_user_daily AS
WITH counts AS (
 SELECT scope_id,utc_date,user_id,
 count(*) AS event_records,
 count(*) FILTER(WHERE event_type='view') AS view_events,
 count(*) FILTER(WHERE event_type='cart') AS cart_events,
 count(*) FILTER(WHERE event_type='remove_from_cart') AS remove_from_cart_events,
 count(*) FILTER(WHERE event_type='purchase') AS purchase_events,
 count(DISTINCT user_session) FILTER(WHERE NOT session_missing) AS sessions,
 count(DISTINCT user_session) FILTER(WHERE NOT session_missing AND event_type='purchase') AS purchase_sessions,
 bool_or(is_first_seen_day) AS is_first_seen_day,
 sum(price_decimal) FILTER(WHERE amount_eligible) AS amount_sum,
 count(*) FILTER(WHERE event_type='purchase' AND NOT amount_eligible) AS purchase_amount_bad,
 count(*) FILTER(WHERE amount_eligible) AS purchase_amount_valid,
 count(*) FILTER(WHERE amount_eligible AND price_zero) AS purchase_zero_events
 FROM decorated GROUP BY scope_id,utc_date,user_id
)
SELECT a.* EXCLUDE(amount_sum),a.purchase_events>0 AS is_buyer,
 formal_amount(amount_sum,a.purchase_events,q.amount_allowed) AS purchase_amount,
 observed_status(a.purchase_events,a.purchase_amount_bad,a.purchase_amount_valid) AS amount_status,
 q.count_allowed,q.amount_allowed,q.date_reason_codes
FROM counts a JOIN quality q USING(utc_date);

CREATE OR REPLACE TABLE d_agg_daily_metrics AS
WITH counts AS (
 SELECT scope_id,utc_date,count(DISTINCT user_id) AS active_users,
 count(DISTINCT user_id) FILTER(WHERE event_type='purchase') AS buyers,
 count(*) AS event_records,
 count(*) FILTER(WHERE event_type='view') AS view_events,
 count(*) FILTER(WHERE event_type='cart') AS cart_events,
 count(*) FILTER(WHERE event_type='remove_from_cart') AS remove_from_cart_events,
 count(*) FILTER(WHERE event_type='purchase') AS purchase_events,
 count(DISTINCT (user_id,user_session)) FILTER(WHERE NOT session_missing) AS sessions,
 count(DISTINCT (user_id,user_session)) FILTER(WHERE NOT session_missing AND event_type='purchase') AS purchase_sessions,
 sum(price_decimal) FILTER(WHERE amount_eligible) AS amount_sum,
 count(*) FILTER(WHERE event_type='purchase' AND NOT amount_eligible) AS purchase_amount_bad,
 count(*) FILTER(WHERE amount_eligible) AS purchase_amount_valid,
 count(*) FILTER(WHERE amount_eligible AND price_zero) AS purchase_zero_events,
 count(DISTINCT user_id) FILTER(WHERE is_first_seen_day) AS first_seen_users
 FROM decorated GROUP BY scope_id,utc_date
), final AS (
 SELECT a.* EXCLUDE(amount_sum),formal_amount(amount_sum,a.purchase_events,q.amount_allowed) AS purchase_amount,
 q.count_allowed,q.amount_allowed,q.amount_status,q.date_reason_codes
 FROM counts a JOIN quality q USING(utc_date)
)
SELECT *,CASE WHEN active_users<>0 THEN buyers::DOUBLE/active_users END AS buyer_rate,
 CASE WHEN amount_allowed AND buyers<>0 THEN purchase_amount::DOUBLE/buyers END AS amount_per_buyer,
 CASE WHEN active_users<>0 THEN first_seen_users::DOUBLE/active_users END AS first_seen_ratio,
 CASE WHEN active_users=0 THEN 'no_active_users' ELSE 'defined' END AS buyer_rate_status,
 CASE WHEN NOT amount_allowed THEN 'amount_blocked' WHEN buyers=0 THEN 'no_buyers' ELSE 'defined' END AS amount_per_buyer_status,
 CASE WHEN active_users=0 THEN 'no_active_users' ELSE 'defined' END AS first_seen_ratio_status
FROM final;

CREATE OR REPLACE TABLE d_agg_daily_dim AS
WITH buckets AS (
 SELECT scope_id,utc_date,user_id,event_type,amount_eligible,price_decimal,'category_l1' dim_name,category_key dim_value_key,category_label dim_value_label FROM decorated
 UNION ALL SELECT scope_id,utc_date,user_id,event_type,amount_eligible,price_decimal,'brand_group',brand_key,brand_label FROM decorated
 UNION ALL SELECT scope_id,utc_date,user_id,event_type,amount_eligible,price_decimal,'price_band',price_key,price_label FROM decorated
 UNION ALL SELECT scope_id,utc_date,user_id,event_type,amount_eligible,price_decimal,'is_first_seen_day','first_seen:'||is_first_seen_day::VARCHAR,is_first_seen_day::VARCHAR FROM decorated
), counts AS (
 SELECT scope_id,utc_date,dim_name,dim_value_key,dim_value_label,count(DISTINCT user_id) AS users,
 count(DISTINCT user_id) FILTER(WHERE event_type='purchase') AS buyers,count(*) AS event_records,
 count(*) FILTER(WHERE event_type='purchase') AS purchase_events,
 sum(price_decimal) FILTER(WHERE amount_eligible) AS amount_sum,
 count(*) FILTER(WHERE event_type='purchase' AND NOT amount_eligible) AS purchase_amount_bad,
 count(*) FILTER(WHERE amount_eligible) AS purchase_amount_valid
 FROM buckets GROUP BY scope_id,utc_date,dim_name,dim_value_key,dim_value_label
)
SELECT a.* EXCLUDE(amount_sum),formal_amount(amount_sum,a.purchase_events,q.amount_allowed) AS purchase_amount,
 observed_status(a.purchase_events,a.purchase_amount_bad,a.purchase_amount_valid) AS amount_status,
 q.count_allowed,q.amount_allowed,q.date_reason_codes
FROM counts a JOIN quality q USING(utc_date);
