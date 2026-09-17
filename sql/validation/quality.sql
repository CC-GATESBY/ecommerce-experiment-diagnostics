-- Date permissions derived from raw-input parsing, not copied from Spark gates.
CREATE OR REPLACE TABLE quality AS
WITH a AS (
 SELECT utc_date,COUNT(*) AS record_count,
  COUNT(*) FILTER (WHERE event_eligible) AS eligible_records,
  COUNT(*) FILTER (WHERE time_missing) AS time_missing,
  COUNT(*) FILTER (WHERE time_invalid) AS time_invalid,
  COUNT(*) FILTER (WHERE user_id_missing) AS user_id_missing,
  COUNT(*) FILTER (WHERE user_id_invalid) AS user_id_invalid,
  COUNT(*) FILTER (WHERE event_type_unknown) AS event_type_unknown,
  COUNT(*) FILTER (WHERE brand_missing) AS brand_missing,
  COUNT(*) FILTER (WHERE category_code_missing) AS category_code_missing,
  COUNT(*) FILTER (WHERE session_missing) AS session_missing,
  COUNT(*) FILTER (WHERE event_eligible AND event_type='purchase') AS purchases,
  COUNT(*) FILTER (WHERE event_type='purchase' AND NOT amount_eligible) AS purchase_amount_bad,
  COUNT(*) FILTER (WHERE amount_eligible) AS purchase_amount_valid,
  COUNT(*) FILTER (WHERE amount_eligible AND price_zero) AS purchase_zero_events,
  SUM(price_decimal) FILTER (WHERE amount_eligible) AS observed_amount
 FROM parsed GROUP BY utc_date
), b AS (
 SELECT *,record_count=eligible_records AND NOT EXISTS(
    SELECT 1 FROM parsed WHERE ts IS NULL OR utc_date<DATE '2019-10-01' OR utc_date>=DATE '2019-11-01') AS count_allowed,
  CASE WHEN purchases=0 THEN 'no_purchases' WHEN purchase_amount_bad=0 THEN 'complete_observed'
       WHEN purchase_amount_valid>0 THEN 'partial_observed' ELSE 'unknown' END AS amount_status
 FROM a
)
SELECT *,count_allowed AND purchase_amount_bad=0 AS amount_allowed,
 CASE WHEN purchase_amount_bad>0 THEN '["purchase_amount_incomplete"]' ELSE '[]' END AS date_reason_codes
FROM b;
CREATE OR REPLACE VIEW eligible AS SELECT p.*,c.scope_id FROM parsed p CROSS JOIN context c WHERE event_eligible;
