SELECT *,
 CASE WHEN active_users>0 THEN CAST(buyers AS DOUBLE)/active_users END AS buyer_rate,
 CASE WHEN amount_allowed AND buyers>0 THEN CAST(purchase_amount AS DOUBLE)/buyers END AS amount_per_buyer,
 CASE WHEN active_users>0 THEN CAST(first_seen_users AS DOUBLE)/active_users END AS first_seen_ratio,
 CASE WHEN active_users>0 THEN 'defined' ELSE 'no_active_users' END AS buyer_rate_status,
 CASE WHEN NOT amount_allowed THEN 'amount_blocked' WHEN buyers=0 THEN 'no_buyers' ELSE 'defined' END AS amount_per_buyer_status,
 CASE WHEN active_users>0 THEN 'defined' ELSE 'no_active_users' END AS first_seen_ratio_status
FROM m_daily_base
