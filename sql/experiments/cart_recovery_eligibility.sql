-- Frozen first-cart user anchor; no category/session/product exclusion.
WITH anchors AS (
  SELECT scope_id, user_id, MIN(event_timestamp_utc) AS t_cart
  FROM cart_fact
  WHERE event_eligible AND event_type = 'cart'
  GROUP BY scope_id, user_id
), windows AS (
  SELECT *, t_cart + INTERVAL 24 HOURS AS t0,
    t_cart + INTERVAL 48 HOURS AS outcome_end,
    t_cart >= TIMESTAMP '2019-10-01 00:00:00'
      AND t_cart < TIMESTAMP '2019-10-30 00:00:00' AS window_complete
  FROM anchors
), joined AS (
  SELECT a.scope_id, a.user_id, a.t_cart, a.t0, a.outcome_end, a.window_complete,
    COUNT_IF(p.event_timestamp_utc <= a.t0) AS waiting_purchase_events,
    COUNT_IF(p.event_timestamp_utc > a.t0) AS outcome_purchase_events,
    COUNT_IF(p.event_timestamp_utc > a.t0 AND NOT COALESCE(p.amount_eligible, false)) AS outcome_bad_amount_events,
    SUM(CASE WHEN p.event_timestamp_utc > a.t0 AND p.amount_eligible
        THEN CAST(p.price_decimal AS DECIMAL(38,2)) ELSE CAST(0 AS DECIMAL(38,2)) END) AS known_outcome_amount
  FROM windows a LEFT JOIN cart_fact p
    ON a.scope_id = p.scope_id AND a.user_id = p.user_id
    AND p.event_eligible AND p.event_type = 'purchase'
    AND p.event_timestamp_utc >= a.t_cart AND p.event_timestamp_utc <= a.outcome_end
  GROUP BY a.scope_id, a.user_id, a.t_cart, a.t0, a.outcome_end, a.window_complete
), classified AS (
  SELECT *, CASE WHEN NOT window_complete THEN 'right_censored'
    WHEN waiting_purchase_events > 0 THEN 'waiting_purchase_excluded'
    ELSE 'eligible' END AS eligibility_status
  FROM joined
)
SELECT *,
  CASE WHEN eligibility_status = 'eligible' THEN CAST(outcome_purchase_events > 0 AS INT) END AS purchased_24h,
  CASE WHEN eligibility_status = 'eligible' AND outcome_bad_amount_events = 0
       THEN known_outcome_amount END AS purchase_amount_24h,
  CASE WHEN eligibility_status <> 'eligible' THEN 'not_applicable'
       WHEN outcome_purchase_events = 0 THEN 'no_purchases'
       WHEN outcome_bad_amount_events = outcome_purchase_events THEN 'unknown'
       WHEN outcome_bad_amount_events > 0 THEN 'partial_observed'
       ELSE 'complete_observed' END AS amount_status
FROM classified
