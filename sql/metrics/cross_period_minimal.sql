-- rees46-metrics-v1 subset: no brand, first_seen, session or funnel extension.
-- Eligibility/Decimal values come from unchanged sql/validation/parse.sql.
CREATE TABLE eligible AS SELECT * FROM parsed WHERE event_eligible;
CREATE VIEW category_events AS
SELECT *,
 CASE WHEN regexp_full_match(category_code,'[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*')
      THEN 'category:'||split_part(category_code,'.',1) ELSE 'bucket:unknown' END AS category_key,
 CASE WHEN regexp_full_match(category_code,'[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*')
      THEN split_part(category_code,'.',1) ELSE 'unknown' END AS category_label
FROM eligible;
CREATE TABLE user_daily AS
SELECT utc_date,user_id,count(*) AS event_records,
 count(*) FILTER(WHERE event_type='purchase') AS purchase_events,
 sum(price_decimal) FILTER(WHERE amount_eligible) AS observed_amount
FROM eligible GROUP BY utc_date,user_id;
CREATE TABLE daily AS
WITH a AS (
 SELECT utc_date,count(*) AS active_users,count(*) FILTER(WHERE purchase_events>0) AS buyers,
 CAST(sum(event_records) AS BIGINT) AS event_records,CAST(sum(purchase_events) AS BIGINT) AS purchase_events,
 coalesce(sum(observed_amount),CAST(0 AS DECIMAL(38,2))) AS observed_amount
 FROM user_daily GROUP BY utc_date
)
SELECT a.* EXCLUDE(observed_amount),
 CASE WHEN g.amount_allowed THEN CAST(a.observed_amount AS DECIMAL(38,2)) END AS purchase_amount,
 g.count_allowed,g.amount_allowed,g.amount_status,
 CASE WHEN a.active_users>0 THEN a.buyers::DOUBLE/a.active_users END AS buyer_rate,
 CASE WHEN g.amount_allowed AND a.buyers>0 THEN a.observed_amount::DOUBLE/a.buyers END AS amount_per_buyer
FROM a JOIN gates g USING(utc_date);
CREATE TABLE category_daily AS
WITH a AS (
 SELECT utc_date,category_key,category_label,count(*) AS event_records,
 count(*) FILTER(WHERE event_type='purchase') AS purchase_events,
 coalesce(sum(price_decimal) FILTER(WHERE amount_eligible),CAST(0 AS DECIMAL(38,2))) AS observed_amount
 FROM category_events GROUP BY utc_date,category_key,category_label
)
SELECT a.* EXCLUDE(observed_amount),
 CASE WHEN g.amount_allowed THEN CAST(a.observed_amount AS DECIMAL(38,2)) END AS purchase_amount,
 g.count_allowed,g.amount_allowed
FROM a JOIN gates g USING(utc_date);
