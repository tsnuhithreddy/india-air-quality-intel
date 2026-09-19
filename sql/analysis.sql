-- sql/analysis_queries.sql
-- Ad-hoc analytical queries against the live schema, written once the
-- three live-source loaders were working (Phase 5). Only uses tables
-- that existed at that point — dim_city, dim_pollutant, dim_station,
-- fact_cpcb_subindex, fact_openaq_concentration, fact_weather_observations,
-- fact_weather_forecast. Kaggle historical tables came later in Phase 6.

USE india_air_quality;

-- Which pollutant is actually driving each city's AQI, on average?
-- A city-wide sub-index number hides this — useful if an alert should
-- name a specific pollutant rather than just say "air quality is bad".
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


-- For each pollutant, which OpenAQ station reports the highest average
-- real concentration? Ranked per pollutant rather than per city, since
-- dim_station.city_id is left NULL for OpenAQ stations — OpenAQ's data
-- never tells us which of our target cities a station actually belongs to.
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


-- Stations reading above the national average sub-index — a simple way
-- to flag which ones might be worth prioritizing, rather than eyeballing
-- a ranked list and guessing where the real cutoff is.
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


-- Same idea, but against each station's OWN city average instead of the
-- national one (correlated subquery). Catches the case where most
-- stations in a city are fine and just one is dragging the city average
-- up — a city-level number alone wouldn't show that.
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


-- Pollution vs. wind/rain, matched hour-for-hour rather than just by
-- city. An earlier version of this query joined only on city_id, which
-- worked by accident while fact_weather_observations still had just one
-- row per city — it would have started producing a cross join (every
-- pollution reading paired with every weather row ever recorded for that
-- city) as soon as more hourly weather data piled up. Matching on the
-- same hour fixes that properly.
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


-- Smoothed temperature forecast per city (3-hour moving average) from
-- the 24-hour Open-Meteo forecast. A single forecasted hour is noisy;
-- this shows the underlying trend across the day per city.
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


-- Which pollutant gets flagged suspicious most often, combining BOTH
-- live sources into one list. Data-quality flags were tracked
-- per-source since Phase 3/4, but never combined before into one view
-- of which pollutant is least reliably measured overall, regardless of
-- which source is reporting it.
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
