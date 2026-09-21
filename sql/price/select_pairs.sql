-- Outcomes are deliberately absent from price ranking and candidate selection.
CREATE TEMP TABLE price_support AS
WITH counts AS (
 SELECT product_id, first_view_price AS price, COUNT(*) AS paths,
        COUNT(DISTINCT user_id) AS users, COUNT(DISTINCT start_date_utc) AS days
 FROM usable GROUP BY product_id, first_view_price
)
SELECT *, ROW_NUMBER() OVER(PARTITION BY product_id ORDER BY paths DESC,price ASC) AS price_rank,
       SUM(paths) OVER(PARTITION BY product_id) AS total_paths
FROM counts;
CREATE TEMP TABLE pairs AS
WITH top_two AS (
 SELECT product_id, MIN(price) AS low_price, MAX(price) AS high_price,
        MIN(paths) AS min_paths, MIN(users) AS min_users, MIN(days) AS min_days,
        SUM(paths) AS pair_paths, MAX(total_paths) AS total_paths
 FROM price_support WHERE price_rank<=2 GROUP BY product_id HAVING COUNT(*)=2
)
SELECT *, min_paths >= $min_paths AS paths_ok, min_users >= $min_users AS users_ok,
       min_days >= $min_days AS days_ok,
       pair_paths >= total_paths * CAST($min_coverage AS DECIMAL(3,2)) AS coverage_ok,
       high_price-low_price >= high_price*CAST($min_gap AS DECIMAL(3,2))
       AND high_price-low_price <= high_price*CAST($max_gap AS DECIMAL(3,2)) AS gap_ok
FROM top_two;
CREATE TEMP VIEW candidates AS
SELECT * FROM pairs WHERE paths_ok AND users_ok AND days_ok AND coverage_ok AND gap_ok;
