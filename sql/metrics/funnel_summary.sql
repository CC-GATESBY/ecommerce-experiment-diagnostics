WITH agg AS (
 SELECT CASE WHEN GROUPING(start_date_utc)=0 THEN 'start_day'
             WHEN GROUPING(price_band)=0 THEN 'price_band' ELSE 'overall' END AS level,
        CASE WHEN GROUPING(start_date_utc)=0 THEN CAST(start_date_utc AS STRING)
             WHEN GROUPING(price_band)=0 THEN price_band ELSE 'all' END AS segment,
 COUNT(*) AS n_view,COUNT_IF(has_cart_after_view) AS n_cart,
 COUNT_IF(has_purchase_after_view) AS n_purchase,COUNT_IF(has_three_step) AS n_three_step,
 COUNT_IF(strict_class='view_cart_purchase') AS view_cart_purchase,
 COUNT_IF(strict_class='view_purchase_no_confirmed_intermediate_cart') AS view_purchase_no_confirmed_intermediate_cart,
 COUNT_IF(strict_class='view_cart_no_observed_purchase') AS view_cart_no_observed_purchase,
 COUNT_IF(strict_class='view_only') AS view_only
 FROM f_paths WHERE release_status='formal'
 GROUP BY GROUPING SETS ((),(start_date_utc),(price_band))
), complete AS (
 SELECT * FROM agg
 UNION ALL
 SELECT 'overall','all',0,0,0,0,0,0,0,0
 WHERE NOT EXISTS (SELECT 1 FROM agg WHERE level='overall')
 UNION ALL
 SELECT 'price_band',p.band,0,0,0,0,0,0,0,0
 FROM VALUES ('[0,20)'),('[20,50)'),('[50,200)'),('[200,+inf)'),('unknown') p(band)
 WHERE NOT EXISTS (SELECT 1 FROM agg WHERE level='price_band' AND segment=p.band)
)
SELECT *,CASE WHEN n_view>0 THEN n_cart/CAST(n_view AS DOUBLE) END AS view_to_cart,
 CASE WHEN n_cart>0 THEN n_three_step/CAST(n_cart AS DOUBLE) END AS cart_to_purchase_three_step,
 CASE WHEN n_view>0 THEN n_purchase/CAST(n_view AS DOUBLE) END AS view_to_purchase,
 CASE WHEN n_view>0 THEN n_three_step/CAST(n_view AS DOUBLE) END AS three_step_ratio,
 CASE WHEN n_view=0 THEN 'zero_denominator' ELSE 'defined' END AS view_denominator_status,
 CASE WHEN n_cart=0 THEN 'zero_denominator' ELSE 'defined' END AS cart_denominator_status
FROM complete
