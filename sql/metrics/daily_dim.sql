WITH expanded AS (
 SELECT scope_id,event_date_utc AS utc_date,user_id,event_type,amount_eligible,price_decimal,
  dim.dim_name,dim.dim_value_key,dim.dim_value_label
 FROM m_events
 LATERAL VIEW EXPLODE(ARRAY(
  NAMED_STRUCT('dim_name','category_l1','dim_value_key',category_key,'dim_value_label',category_label),
  NAMED_STRUCT('dim_name','brand_group','dim_value_key',brand_key,'dim_value_label',brand_label),
  NAMED_STRUCT('dim_name','price_band','dim_value_key',price_key,'dim_value_label',price_label),
  NAMED_STRUCT('dim_name','is_first_seen_day','dim_value_key',CONCAT('first_seen:',CAST(is_first_seen_day AS STRING)),'dim_value_label',CAST(is_first_seen_day AS STRING))
 )) t AS dim
), a AS (
 SELECT scope_id,utc_date,dim_name,dim_value_key,dim_value_label,
 COUNT(DISTINCT user_id) AS users, COUNT(DISTINCT CASE WHEN event_type='purchase' THEN user_id END) AS buyers,
 COUNT(*) AS event_records,COUNT_IF(event_type='purchase') AS purchase_events,
 COUNT_IF(event_type='purchase' AND NOT amount_eligible) AS purchase_amount_bad,
 COUNT_IF(amount_eligible) AS purchase_amount_valid,
 SUM(CASE WHEN amount_eligible THEN CAST(price_decimal AS DECIMAL(38,2)) ELSE CAST(0 AS DECIMAL(38,2)) END) AS observed_amount
 FROM expanded GROUP BY scope_id,utc_date,dim_name,dim_value_key,dim_value_label
)
SELECT a.scope_id,a.utc_date,a.dim_name,a.dim_value_key,a.dim_value_label,a.users,a.buyers,a.event_records,a.purchase_events,
 CASE WHEN g.amount_allowed THEN a.observed_amount ELSE CAST(NULL AS DECIMAL(38,2)) END AS purchase_amount,
 a.purchase_amount_bad,a.purchase_amount_valid,
 CASE WHEN a.purchase_events=0 THEN 'no_purchases' WHEN a.purchase_amount_bad=0 THEN 'complete_observed'
      WHEN a.purchase_amount_valid>0 THEN 'partial_observed' ELSE 'unknown' END AS amount_status,
 g.count_allowed,g.amount_allowed,g.reason_codes AS date_reason_codes
FROM a JOIN m_gates g ON a.utc_date=g.utc_date
