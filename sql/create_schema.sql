CREATE DATABASE IF NOT EXISTS india_air_quality
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE india_air_quality;

CREATE TABLE dim_city (
    city_id INT AUTO_INCREMENT PRIMARY KEY,
    city_name VARCHAR(50) NOT NULL UNIQUE,
    latitude DECIMAL(9,6) NOT NULL,
    longitude DECIMAL(9,6) NOT NULL,
    has_kaggle_historical_data BOOLEAN NOT NULL DEFAULT TRUE
) ENGINE=InnoDB;

CREATE TABLE dim_pollutant (
    pollutant_id INT AUTO_INCREMENT PRIMARY KEY,
    pollutant_code VARCHAR(10) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE dim_station (
    station_id INT AUTO_INCREMENT PRIMARY KEY,
    source_system ENUM('data_gov_in','openaq') NOT NULL,
    source_station_key VARCHAR(150) NOT NULL,
    station_name VARCHAR(150) NOT NULL,
    city_id INT NOT NULL,
    latitude DECIMAL(9,6),
    longitude DECIMAL(9,6),
    UNIQUE KEY uq_station_source (source_system, source_station_key),
    FOREIGN KEY (city_id) REFERENCES dim_city(city_id)
) ENGINE=InnoDB;

CREATE TABLE fact_cpcb_subindex (
    reading_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    station_id INT NOT NULL,
    pollutant_id INT NOT NULL,
    timestamp_local DATETIME NOT NULL,
    sub_index_min DECIMAL(6,2),
    sub_index_max DECIMAL(6,2),
    sub_index_avg DECIMAL(6,2),
    flag_negative BOOLEAN NOT NULL DEFAULT FALSE,
    flag_sentinel BOOLEAN NOT NULL DEFAULT FALSE,
    flag_missing BOOLEAN NOT NULL DEFAULT FALSE,
    is_suspicious BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE KEY uq_cpcb_reading (station_id, pollutant_id, timestamp_local),
    FOREIGN KEY (station_id) REFERENCES dim_station(station_id),
    FOREIGN KEY (pollutant_id) REFERENCES dim_pollutant(pollutant_id)
) ENGINE=InnoDB;

CREATE TABLE fact_openaq_concentration (
    reading_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    station_id INT NOT NULL,
    pollutant_id INT NOT NULL,
    timestamp_local DATETIME NOT NULL,
    timestamp_utc DATETIME NOT NULL,
    concentration_value DECIMAL(10,3),
    unit VARCHAR(10) NOT NULL,
    flag_negative BOOLEAN NOT NULL DEFAULT FALSE,
    flag_sentinel BOOLEAN NOT NULL DEFAULT FALSE,
    flag_missing BOOLEAN NOT NULL DEFAULT FALSE,
    flag_zero BOOLEAN NOT NULL DEFAULT FALSE,
    is_suspicious BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE KEY uq_openaq_reading (station_id, pollutant_id, timestamp_local),
    FOREIGN KEY (station_id) REFERENCES dim_station(station_id),
    FOREIGN KEY (pollutant_id) REFERENCES dim_pollutant(pollutant_id)
) ENGINE=InnoDB;

CREATE TABLE fact_weather_observations (
    observation_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    city_id INT NOT NULL,
    timestamp_local DATETIME NOT NULL,
    temperature_c DECIMAL(5,2),
    relative_humidity_pct DECIMAL(5,2),
    wind_speed_kmh DECIMAL(6,2),
    wind_direction_deg DECIMAL(5,2),
    precipitation_mm DECIMAL(6,2),
    surface_pressure_hpa DECIMAL(7,2),
    elevation_m DECIMAL(7,2),
    flag_humidity_invalid BOOLEAN NOT NULL DEFAULT FALSE,
    flag_temperature_extreme BOOLEAN NOT NULL DEFAULT FALSE,
    flag_wind_negative BOOLEAN NOT NULL DEFAULT FALSE,
    flag_pressure_invalid BOOLEAN NOT NULL DEFAULT FALSE,
    flag_missing BOOLEAN NOT NULL DEFAULT FALSE,
    is_suspicious BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE KEY uq_weather_obs (city_id, timestamp_local),
    FOREIGN KEY (city_id) REFERENCES dim_city(city_id)
) ENGINE=InnoDB;

CREATE TABLE fact_weather_forecast (
    forecast_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    city_id INT NOT NULL,
    forecast_timestamp_local DATETIME NOT NULL,
    forecast_step_hour INT NOT NULL,
    temperature_c DECIMAL(5,2),
    relative_humidity_pct DECIMAL(5,2),
    wind_speed_kmh DECIMAL(6,2),
    precipitation_mm DECIMAL(6,2),
    flag_humidity_invalid BOOLEAN NOT NULL DEFAULT FALSE,
    flag_temperature_extreme BOOLEAN NOT NULL DEFAULT FALSE,
    flag_wind_negative BOOLEAN NOT NULL DEFAULT FALSE,
    flag_missing BOOLEAN NOT NULL DEFAULT FALSE,
    is_suspicious BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE KEY uq_weather_forecast (city_id, forecast_timestamp_local),
    FOREIGN KEY (city_id) REFERENCES dim_city(city_id)
) ENGINE=InnoDB;

USE india_air_quality;
SHOW TABLES;

SHOW CREATE TABLE fact_cpcb_subindex;
DESCRIBE dim_station;

USE india_air_quality;

INSERT INTO dim_city (city_name, latitude, longitude, has_kaggle_historical_data) VALUES
('Delhi',      28.6139, 77.2090, TRUE),
('Mumbai',     19.0760, 72.8777, TRUE),
('Bengaluru',  12.9716, 77.5946, TRUE),
('Hyderabad',  17.3850, 78.4867, TRUE),
('Chennai',    13.0827, 80.2707, TRUE),
('Kolkata',    22.5726, 88.3639, TRUE),
('Pune',       18.5204, 73.8567, FALSE),   -- known gap: not in Kaggle dataset
('Ahmedabad',  23.0225, 72.5714, TRUE),
('Lucknow',    26.8467, 80.9462, TRUE),
('Jaipur',     26.9124, 75.7873, TRUE),
('Patna',      25.5941, 85.1376, TRUE);

INSERT INTO dim_pollutant (pollutant_code) VALUES
('PM2.5'), ('PM10'), ('SO2'), ('NO2'), ('CO'), ('O3'), ('NH3'), ('Pb'), ('BC');

SELECT * FROM dim_city;
SELECT * FROM dim_pollutant;

ALTER TABLE fact_openaq_concentration
ADD COLUMN sensor_id INT NULL AFTER station_id;

DESCRIBE fact_openaq_concentration;

-- 1. Widen the allowed source_system values to include Kaggle
ALTER TABLE dim_station 
MODIFY COLUMN source_system ENUM('data_gov_in', 'openaq', 'kaggle') NOT NULL;

-- 2. Per-pollutant historical readings (long format, matches your existing pattern)
CREATE TABLE fact_kaggle_historical (
    reading_id INT AUTO_INCREMENT PRIMARY KEY,
    station_id INT NOT NULL,
    pollutant_id INT NOT NULL,
    reading_date DATE NOT NULL,
    pollutant_value DECIMAL(10,3) NULL,
    flag_missing BOOLEAN NOT NULL DEFAULT FALSE,
    is_suspicious BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (station_id) REFERENCES dim_station(station_id),
    FOREIGN KEY (pollutant_id) REFERENCES dim_pollutant(pollutant_id),
    UNIQUE KEY uq_kaggle_reading (station_id, pollutant_id, reading_date)
);

-- 3. One overall AQI value per station per day (separate, so it's never duplicated)
CREATE TABLE fact_kaggle_daily_aqi (
    daily_aqi_id INT AUTO_INCREMENT PRIMARY KEY,
    station_id INT NOT NULL,
    reading_date DATE NOT NULL,
    aqi_value DECIMAL(6,1) NULL,
    aqi_bucket VARCHAR(20) NULL,
    flag_missing BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (station_id) REFERENCES dim_station(station_id),
    UNIQUE KEY uq_kaggle_daily_aqi (station_id, reading_date)
);

DESCRIBE dim_station;
DESCRIBE fact_kaggle_historical;
DESCRIBE fact_kaggle_daily_aqi;

INSERT INTO dim_pollutant (pollutant_code) VALUES ('Benzene'), ('Toluene'), ('Xylene');

SELECT * FROM dim_pollutant;

SELECT COUNT(*) FROM fact_kaggle_daily_aqi;

SELECT COUNT(*) FROM dim_station WHERE source_system = 'kaggle';

SELECT * FROM dim_station WHERE source_system = 'kaggle' LIMIT 5;

SELECT ds.station_name, dc.city_name
FROM dim_station ds
JOIN dim_city dc ON ds.city_id = dc.city_id
WHERE ds.source_system = 'kaggle'
LIMIT 10;

SELECT COUNT(*) FROM fact_kaggle_historical;

-- Confirm no new stations were created this time (all 90 already existed)
SELECT COUNT(*) FROM dim_station WHERE source_system = 'kaggle';

-- Spot-check real values for one station across a few pollutants
SELECT ds.station_name, dp.pollutant_code, f.reading_date, f.pollutant_value, f.flag_missing
FROM fact_kaggle_historical f
JOIN dim_station ds ON f.station_id = ds.station_id
JOIN dim_pollutant dp ON f.pollutant_id = dp.pollutant_id
WHERE ds.station_name = 'Alipur, Delhi - DPCC'
ORDER BY f.reading_date
LIMIT 15;

-- Confirm flag_missing rate roughly matches the 29.7% we saw during cleaning
SELECT 
    ROUND(AVG(flag_missing) * 100, 1) AS pct_missing,
    ROUND(AVG(is_suspicious) * 100, 1) AS pct_suspicious
FROM fact_kaggle_historical;

SELECT MIN(min_date) AS earliest_date, MAX(max_date) AS latest_date
FROM (
  SELECT MIN(timestamp_local) AS min_date, MAX(timestamp_local) AS max_date FROM fact_cpcb_subindex
  UNION ALL
  SELECT MIN(timestamp_local), MAX(timestamp_local) FROM fact_openaq_concentration
  UNION ALL
  SELECT MIN(timestamp_local), MAX(timestamp_local) FROM fact_weather_observations
  UNION ALL
  SELECT MIN(forecast_timestamp_local), MAX(forecast_timestamp_local) FROM fact_weather_forecast
  UNION ALL
  SELECT MIN(reading_date), MAX(reading_date) FROM fact_kaggle_historical
  UNION ALL
  SELECT MIN(reading_date), MAX(reading_date) FROM fact_kaggle_daily_aqi
) AS combined;

SELECT DATE(timestamp_local) AS day, COUNT(*) AS reading_count
FROM fact_cpcb_subindex
GROUP BY DATE(timestamp_local)
ORDER BY day;

SELECT AVG(fkda.aqi_value) AS avg_aqi
FROM fact_kaggle_daily_aqi fkda
JOIN dim_station ds ON fkda.station_id = ds.station_id
JOIN dim_city dc ON ds.city_id = dc.city_id
WHERE dc.city_name = 'Delhi'
AND YEAR(fkda.reading_date) = 2018;

SELECT COUNT(*) FROM fact_cpcb_subindex;                          -- should be 545
SELECT COUNT(DISTINCT city_id) FROM dim_station;                   -- compare to "Cities Monitored" card
SELECT AVG(sub_index_avg) FROM fact_cpcb_subindex 
WHERE DATE(timestamp_local) = (SELECT MAX(DATE(timestamp_local)) FROM fact_cpcb_subindex);  -- compare to "Avg Sub-Index Latest Day"

SELECT dc.city_name, YEAR(fkda.reading_date) AS yr, 
       COUNT(*) AS n_days, 
       MIN(fkda.aqi_value) AS min_aqi, 
       MAX(fkda.aqi_value) AS max_aqi, 
       AVG(fkda.aqi_value) AS avg_aqi
FROM fact_kaggle_daily_aqi fkda
JOIN dim_station ds ON fkda.station_id = ds.station_id
JOIN dim_city dc ON ds.city_id = dc.city_id
WHERE dc.city_name IN ('Ahmedabad', 'Delhi')
GROUP BY dc.city_name, YEAR(fkda.reading_date)
ORDER BY dc.city_name, yr;

SELECT ds.station_id, ds.station_name, dc.city_name
FROM dim_station ds
JOIN dim_city dc ON ds.city_id = dc.city_id
WHERE dc.city_name = 'Ahmedabad';
