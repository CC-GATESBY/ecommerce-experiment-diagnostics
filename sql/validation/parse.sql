-- Independent lexical and range checks over VARCHAR input; no Spark helpers.
CREATE OR REPLACE MACRO blank(s) AS regexp_full_match(s, '[ \t\r\n\x0b\x0c]*');
CREATE OR REPLACE TABLE parsed AS
WITH lexical AS (
 SELECT *,
  blank(event_time) AS time_missing,
  CASE WHEN regexp_full_match(event_time,'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} UTC')
         AND substr(event_time,1,4)<>'0000'
       THEN try_strptime(event_time,'%Y-%m-%d %H:%M:%S UTC') END AS ts,
  blank(user_id) AS user_id_missing,
  NOT blank(user_id) AND NOT regexp_full_match(user_id,'[0-9]+') AS user_id_invalid,
  event_type NOT IN ('view','cart','remove_from_cart','purchase') AS event_type_unknown,
  blank(user_session) AS session_missing,blank(brand) AS brand_missing,blank(category_code) AS category_code_missing,
  regexp_full_match(price,'[+-]?[0-9]+(\.[0-9]+)?') AS price_lexical,
  regexp_full_match(lower(price),'[+-]?(snan|nan|inf|infinity)') AS price_nonfinite,
  blank(price) AS price_missing
 FROM raw_csv
), limits AS (
 SELECT *, NOT time_missing AND ts IS NULL AS time_invalid,
  price_lexical AND length(regexp_replace(regexp_extract(price,'[+-]?([0-9]+)',1),'^0+',''))>16 AS price_precision_exceeded,
  price_lexical AND length(regexp_extract(price,'\.([0-9]+)',1))>2 AS price_scale_exceeded,
  price_lexical AND NOT regexp_matches(price,'[1-9]') AS price_zero,
  price_lexical AND starts_with(price,'-') AND regexp_matches(price,'[1-9]') AS price_negative,
  NOT price_missing AND NOT price_lexical AND NOT price_nonfinite AS price_invalid,
  ts IS NOT NULL AND NOT user_id_missing AND NOT user_id_invalid AND NOT event_type_unknown AS event_eligible
 FROM lexical
), values_checked AS (
 SELECT *, CASE WHEN price_lexical AND NOT price_precision_exceeded AND NOT price_scale_exceeded
           THEN CAST(price AS DECIMAL(18,2)) END AS price_decimal
 FROM limits
)
SELECT *, CAST(ts AS DATE) AS utc_date,
 event_eligible AND event_type='purchase' AND price_decimal IS NOT NULL AND NOT price_negative AS amount_eligible
FROM values_checked;
