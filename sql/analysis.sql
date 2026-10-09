-- analysis.sql
-- Ad-hoc queries against the live tables. Uses only the live-source tables,
-- not the Kaggle ones.

USE india_air_quality;

-- Which pollutant drives each city's AQI on average
SELECT
    c.city_name,
    p.pollutant_code,
    ROUND(AVG(f.sub_index_avg), 1) AS avg_sub_index,
    COUNT(*) AS reading_count
FROM fact_cpcb_subindex f
JOIN dim_station s ON f.station_id = s.station_id
JOIN dim_city c ON s.city_id = c.city_id
JOIN dim_pollutant p ON f.pollutant_id = p.pollutant_id
WHERE f.flag_missing = FALSE
GROUP BY c.city_name, p.pollutant_code
ORDER BY c.city_name, avg_sub_index DESC;


-- Worst OpenAQ station for each pollutant (ranked per pollutant, since OpenAQ stations have no city)
SELECT pollutant_code, station_name, avg_concentration, pollutant_rank
FROM (
    SELECT
        p.pollutant_code,
        s.station_name,
        ROUND(AVG(f.concentration_value), 2) AS avg_concentration,
        RANK() OVER (
            PARTITION BY p.pollutant_code
            ORDER BY AVG(f.concentration_value) DESC
        ) AS pollutant_rank
    FROM fact_openaq_concentration f
    JOIN dim_station s ON f.station_id = s.station_id
    JOIN dim_pollutant p ON f.pollutant_id = p.pollutant_id
    WHERE f.flag_missing = FALSE
    GROUP BY p.pollutant_code, s.station_name
) ranked
WHERE pollutant_rank = 1
ORDER BY avg_concentration DESC;


-- Stations above the national average sub-index
SELECT
    s.station_name,
    ROUND(AVG(f.sub_index_avg), 1) AS station_avg_sub_index
FROM fact_cpcb_subindex f
JOIN dim_station s ON f.station_id = s.station_id
WHERE f.flag_missing = FALSE
GROUP BY s.station_name
HAVING AVG(f.sub_index_avg) > (
    SELECT AVG(sub_index_avg)
    FROM fact_cpcb_subindex
    WHERE flag_missing = FALSE
)
ORDER BY station_avg_sub_index DESC;


-- Stations above their own city's average (correlated subquery). Shows when one station is pulling a city up
SELECT
    c.city_name,
    s.station_name,
    ROUND(AVG(f.sub_index_avg), 1) AS station_avg_sub_index
FROM fact_cpcb_subindex f
JOIN dim_station s ON f.station_id = s.station_id
JOIN dim_city c ON s.city_id = c.city_id
WHERE f.flag_missing = FALSE
GROUP BY c.city_name, s.station_name, s.city_id
HAVING AVG(f.sub_index_avg) > (
    SELECT AVG(f2.sub_index_avg)
    FROM fact_cpcb_subindex f2
    JOIN dim_station s2 ON f2.station_id = s2.station_id
    WHERE s2.city_id = s.city_id
      AND f2.flag_missing = FALSE
)
ORDER BY station_avg_sub_index DESC;


-- Pollution against wind and rain, matched on the same hour. Joining on city alone would cross-join as weather rows pile up.
SELECT
    c.city_name,
    DATE_FORMAT(f.timestamp_local, '%Y-%m-%d %H:00:00') AS hour_bucket,
    ROUND(AVG(f.sub_index_avg), 1) AS avg_sub_index,
    ROUND(AVG(w.wind_speed_kmh), 1) AS avg_wind_speed_kmh,
    ROUND(AVG(w.precipitation_mm), 1) AS avg_precipitation_mm
FROM fact_cpcb_subindex f
JOIN dim_station s ON f.station_id = s.station_id
JOIN dim_city c ON s.city_id = c.city_id
JOIN fact_weather_observations w
    ON w.city_id = c.city_id
    AND DATE_FORMAT(w.timestamp_local, '%Y-%m-%d %H:00:00') = DATE_FORMAT(f.timestamp_local, '%Y-%m-%d %H:00:00')
WHERE f.flag_missing = FALSE
GROUP BY c.city_name, hour_bucket
ORDER BY hour_bucket, avg_sub_index DESC;


-- 3-hour moving average of the temperature forecast per city
SELECT
    c.city_name,
    wf.forecast_step_hour,
    wf.temperature_c,
    ROUND(AVG(wf.temperature_c) OVER (
        PARTITION BY c.city_name
        ORDER BY wf.forecast_step_hour
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ), 1) AS rolling_3hr_avg_temp
FROM fact_weather_forecast wf
JOIN dim_city c ON wf.city_id = c.city_id
ORDER BY c.city_name, wf.forecast_step_hour;


-- Share of suspicious readings per pollutant, both live sources combined
SELECT
    pollutant_code,
    SUM(is_suspicious_flag) AS suspicious_count,
    COUNT(*) AS total_readings,
    ROUND(100.0 * SUM(is_suspicious_flag) / COUNT(*), 1) AS pct_suspicious
FROM (
    SELECT p.pollutant_code, f.is_suspicious AS is_suspicious_flag
    FROM fact_cpcb_subindex f
    JOIN dim_pollutant p ON f.pollutant_id = p.pollutant_id

    UNION ALL

    SELECT p.pollutant_code, f.is_suspicious AS is_suspicious_flag
    FROM fact_openaq_concentration f
    JOIN dim_pollutant p ON f.pollutant_id = p.pollutant_id
) combined
GROUP BY pollutant_code
ORDER BY pct_suspicious DESC;

-- Rows loaded per day from data.gov.in since polling started (gaps show outages)
SELECT DATE(timestamp_local) AS day,
       COUNT(DISTINCT HOUR(timestamp_local)) AS hours_covered,
       COUNT(*) AS rows_loaded
FROM fact_cpcb_subindex
WHERE timestamp_local >= '2026-08-17'
GROUP BY DATE(timestamp_local)
ORDER BY day;


-- Freshness check: newest timestamp and row count for each live table
SELECT 'fact_cpcb_subindex' AS table_name, MAX(timestamp_local) AS latest_ts, COUNT(*) AS row_count
FROM fact_cpcb_subindex
UNION ALL
SELECT 'fact_openaq_concentration', MAX(timestamp_local), COUNT(*)
FROM fact_openaq_concentration
UNION ALL
SELECT 'fact_weather_observations', MAX(timestamp_local), COUNT(*)
FROM fact_weather_observations
UNION ALL
SELECT 'fact_weather_forecast', MAX(forecast_timestamp_local), COUNT(*)
FROM fact_weather_forecast;