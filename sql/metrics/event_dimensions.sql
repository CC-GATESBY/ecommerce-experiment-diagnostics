SELECT f.*, s.first_seen_date_utc, f.event_date_utc = s.first_seen_date_utc AS is_first_seen_day,
 CASE WHEN NOT f.category_code_missing AND f.category_code RLIKE r'\A[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*\z'
      THEN CONCAT('category:', SPLIT(f.category_code, r'\.')[0]) ELSE 'bucket:unknown' END AS category_key,
 CASE WHEN NOT f.category_code_missing AND f.category_code RLIKE r'\A[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*\z'
      THEN SPLIT(f.category_code, r'\.')[0] ELSE 'unknown' END AS category_label,
 CASE WHEN f.brand_missing THEN 'bucket:unknown' WHEN b.brand IS NULL THEN 'bucket:other' ELSE b.dim_value_key END AS brand_key,
 CASE WHEN f.brand_missing THEN 'unknown' WHEN b.brand IS NULL THEN 'other' ELSE b.dim_value_label END AS brand_label,
 CASE WHEN f.price_decimal IS NULL OR f.price_decimal < 0 THEN 'bucket:unknown'
      WHEN f.price_decimal < 20 THEN 'band:0_20' WHEN f.price_decimal < 50 THEN 'band:20_50'
      WHEN f.price_decimal < 200 THEN 'band:50_200' ELSE 'band:200_plus' END AS price_key,
 CASE WHEN f.price_decimal IS NULL OR f.price_decimal < 0 THEN 'unknown'
      WHEN f.price_decimal < 20 THEN '[0,20)' WHEN f.price_decimal < 50 THEN '[20,50)'
      WHEN f.price_decimal < 200 THEN '[50,200)' ELSE '[200,+inf)' END AS price_label
FROM m_fact f
LEFT JOIN m_first_seen s ON f.scope_id=s.scope_id AND f.user_id=s.user_id
LEFT JOIN m_brand_map b ON NOT f.brand_missing AND f.brand=b.brand
