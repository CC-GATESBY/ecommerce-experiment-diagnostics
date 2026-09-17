SELECT scope_id, user_id, MIN(event_timestamp_utc) AS first_seen_at_utc,
       TO_DATE(MIN(event_timestamp_utc)) AS first_seen_date_utc
FROM m_fact
GROUP BY scope_id, user_id
