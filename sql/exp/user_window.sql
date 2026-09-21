-- One row per pre-period user. Outcome presence never defines membership.
CREATE TEMP TABLE cohort AS
WITH periods AS (
 SELECT u.*, CASE WHEN utc_date < p.post_start THEN 'pre' ELSE 'post' END AS period
 FROM user_daily u CROSS JOIN cohort_parameters p
 WHERE u.scope_id=p.scope_id AND utc_date>=p.pre_start AND utc_date<p.post_end
), a AS (
 SELECT scope_id,user_id,period,SUM(event_records)::BIGINT AS event_records,
  SUM(purchase_events)::BIGINT AS purchase_events,
  SUM(purchase_amount_bad)::BIGINT AS amount_bad,
  SUM(purchase_amount_valid)::BIGINT AS amount_valid,
  COUNT_IF(purchase_amount IS NULL)::BIGINT AS null_amount_days,
  SUM(purchase_amount)::DECIMAL(38,2) AS observed_amount
 FROM periods GROUP BY scope_id,user_id,period
), joined AS (
 SELECT a.scope_id,a.user_id,a.event_records AS pre_event_records,
  (a.purchase_events>0)::INTEGER AS pre_converted,
  a.purchase_events AS pre_purchase_events,a.amount_bad AS pre_amount_bad,
  a.amount_valid AS pre_amount_valid,a.null_amount_days AS pre_null_amount_days,
  a.observed_amount AS pre_observed_amount,
  (b.user_id IS NOT NULL)::INTEGER AS post_active,
  (COALESCE(b.purchase_events,0)>0)::INTEGER AS post_converted,
  COALESCE(b.event_records,0)::BIGINT AS post_event_records,
  COALESCE(b.purchase_events,0)::BIGINT AS post_purchase_events,
  COALESCE(b.amount_bad,0)::BIGINT AS post_amount_bad,
  COALESCE(b.amount_valid,0)::BIGINT AS post_amount_valid,
  COALESCE(b.null_amount_days,0)::BIGINT AS post_null_amount_days,
  CASE WHEN b.user_id IS NULL THEN 0.00::DECIMAL(38,2)
       ELSE b.observed_amount END AS post_observed_amount,
  p.pre_amount_allowed,p.post_amount_allowed
 FROM a LEFT JOIN a b ON a.scope_id=b.scope_id AND a.user_id=b.user_id AND b.period='post'
 CROSS JOIN cohort_parameters p WHERE a.period='pre'
)
SELECT sha256('rees46-cohort-key-v1|' || length(scope_id)::VARCHAR || ':' || scope_id
              || length(user_id)::VARCHAR || ':' || user_id) AS cohort_key,
 scope_id,user_id,pre_event_records,pre_converted,pre_purchase_events,
 CASE WHEN pre_amount_allowed AND pre_amount_bad=0 AND pre_null_amount_days=0
      THEN pre_observed_amount ELSE NULL END::DECIMAL(38,2) AS pre_purchase_amount,
 CASE WHEN pre_amount_bad>0 THEN CASE WHEN pre_amount_valid>0 THEN 'partial_observed' ELSE 'unknown' END
      WHEN NOT pre_amount_allowed OR pre_null_amount_days>0 THEN 'window_amount_blocked'
      WHEN pre_purchase_events=0 THEN 'no_purchases' ELSE 'complete_observed' END AS pre_amount_status,
 pre_amount_bad,pre_amount_valid,pre_null_amount_days,pre_amount_allowed,
 post_active,post_converted,post_event_records,post_purchase_events,
 CASE WHEN post_amount_allowed AND post_amount_bad=0 AND post_null_amount_days=0
      THEN post_observed_amount ELSE NULL END::DECIMAL(38,2) AS post_purchase_amount,
 CASE WHEN post_amount_bad>0 THEN CASE WHEN post_amount_valid>0 THEN 'partial_observed' ELSE 'unknown' END
      WHEN NOT post_amount_allowed OR post_null_amount_days>0 THEN 'window_amount_blocked'
      WHEN post_purchase_events=0 THEN 'no_purchases' ELSE 'complete_observed' END AS post_amount_status,
 post_amount_bad,post_amount_valid,post_null_amount_days,post_amount_allowed
FROM joined;
