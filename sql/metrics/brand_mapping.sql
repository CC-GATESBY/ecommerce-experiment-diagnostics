WITH counts AS (
  SELECT brand, COUNT(*) AS reference_events
  FROM m_fact
  WHERE event_date_utc BETWEEN DATE '2019-10-01' AND DATE '2019-10-07'
    AND NOT brand_missing
  GROUP BY brand
), ranked AS (
  SELECT *, ROW_NUMBER() OVER (ORDER BY reference_events DESC, brand ASC) AS brand_rank
  FROM counts
)
SELECT brand, reference_events, brand_rank, CONCAT('brand:', brand) AS dim_value_key, brand AS dim_value_label
FROM ranked WHERE brand_rank <= __TOP_K__
