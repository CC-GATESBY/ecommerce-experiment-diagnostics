-- Coverage counts are not sequential conversion rates.
SELECT CASE WHEN GROUPING(event_date_utc)=1 THEN 'month' ELSE 'day' END AS level,
       CAST(event_date_utc AS STRING) AS utc_date, event_type,
       COUNT(*) AS event_records, COUNT(DISTINCT user_id) AS behavior_users
FROM f_coverage_input
GROUP BY GROUPING SETS ((event_type),(event_date_utc,event_type))
