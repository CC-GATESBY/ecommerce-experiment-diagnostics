-- Event-time category; exact synonym of frozen rees46-metrics-v1 expression.
CREATE TEMP VIEW categorized AS
SELECT *, CASE WHEN regexp_full_match(category_code,'[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*')
 THEN 'category:'||split_part(category_code,'.',1) ELSE 'bucket:unknown' END AS category_key
FROM scoped_events;
CREATE TEMP TABLE computer_purchases AS
SELECT * FROM categorized WHERE event_eligible AND event_type='purchase' AND category_key='category:computers';
CREATE TEMP TABLE purchase_products AS SELECT DISTINCT product_id FROM computer_purchases;
-- Six-day retrospective classification check, including non-purchase events.
CREATE TEMP TABLE product_categories AS
SELECT c.product_id,c.category_key,count(*) AS related_event_records
FROM categorized c SEMI JOIN purchase_products p USING(product_id)
GROUP BY c.product_id,c.category_key;
CREATE TEMP TABLE product_daily AS
SELECT utc_date,product_id,count(*) AS purchase_events,
 CAST(sum(price_decimal) FILTER(WHERE amount_eligible) AS DECIMAL(38,2)) AS purchase_amount,
 min(price_decimal) FILTER(WHERE amount_eligible) AS min_record_amount,
 max(price_decimal) FILTER(WHERE amount_eligible) AS max_record_amount
FROM computer_purchases GROUP BY utc_date,product_id;
CREATE TEMP TABLE category_check AS
SELECT utc_date,count(*) AS event_records,
 count(*) FILTER(WHERE event_type='purchase') AS purchase_events,
 count(DISTINCT product_id) FILTER(WHERE event_type='purchase') AS purchase_product_ids,
 count(DISTINCT user_id) FILTER(WHERE event_type='purchase') AS purchase_users,
 CAST(sum(price_decimal) FILTER(WHERE amount_eligible) AS DECIMAL(38,2)) AS purchase_amount,
 count(*) FILTER(WHERE event_type='purchase' AND NOT amount_eligible) AS bad_purchase_amount,
 count(*) FILTER(WHERE event_type='purchase' AND (product_id IS NULL OR NOT regexp_full_match(product_id,'[0-9]+'))) AS bad_purchase_product_id
FROM categorized WHERE event_eligible AND category_key='category:computers' GROUP BY utc_date;
