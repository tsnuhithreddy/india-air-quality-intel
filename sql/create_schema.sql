-- ============================================================
-- India Urban Air Quality Intelligence & Early-Warning System
-- Full schema, rebuildable from scratch.
-- Corrected during post-Phase-11 housekeeping: stripped ad-hoc
-- verification queries (SHOW/DESCRIBE/SELECT) that had been
-- interspersed with the real DDL, and restored the NO/NOX
-- pollutant seed data (Phase 5 finding) that was missing from
-- this file despite being live in the database since Phase 5.
-- ============================================================

CREATE DATABASE IF NOT EXISTS india_air_quality
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE india_air_quality;

-- ============================================================
-- Dimension tables (Phase 5)
-- ============================================================

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

-- source_system widened to include 'kaggle' below (Phase 6) once fact_kaggle_* exists
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

-- ============================================================
-- Fact tables (Phase 5)
-- ============================================================

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

-- ============================================================
-- Seed data (Phase 5)
-- ============================================================

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

-- Original 9 pollutant codes (Phase 1 list + BC added Phase 4)
INSERT INTO dim_pollutant (pollutant_code) VALUES
('PM2.5'), ('PM10'), ('SO2'), ('NO2'), ('CO'), ('O3'), ('NH3'), ('Pb'), ('BC');

-- Phase 5 finding: NO and NOX surfaced during the first real OpenAQ load,
-- not present in Phase 1's original pollutant catalogue. Restored here —
-- these were live in the database since Phase 5 but had never been added
-- to this schema file until this housekeeping pass.
INSERT INTO dim_pollutant (pollutant_code) VALUES ('NO'), ('NOX');

ALTER TABLE fact_openaq_concentration
ADD COLUMN sensor_id INT NULL AFTER station_id;

-- ============================================================
-- Kaggle historical data (Phase 6)
-- ============================================================

-- 1. Widen the allowed source_system values to include Kaggle
ALTER TABLE dim_station
MODIFY COLUMN source_system ENUM('data_gov_in', 'openaq', 'kaggle') NOT NULL;

-- 2. Per-pollutant historical readings (long format, matches existing pattern)
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

-- Benzene/Toluene/Xylene: real VOC pollutants found in Kaggle's raw columns,
-- never reported by data.gov.in or OpenAQ, so never previously tracked.
INSERT INTO dim_pollutant (pollutant_code) VALUES ('Benzene'), ('Toluene'), ('Xylene');

-- ============================================================
-- Anomaly detection (Phase 9)
-- Pulled directly via `SHOW CREATE TABLE` against the live database
-- (this housekeeping pass) rather than reconstructed from memory.
-- Note: city_name is stored directly (not just derivable via
-- daily_aqi_id -> station_id -> city_id), matching this project's
-- established preference for direct queryability over strict
-- normalization -- documented in PHASE9_ANOMALY_DETECTION.md.
-- ============================================================

CREATE TABLE fact_kaggle_anomaly_flags (
  anomaly_id INT NOT NULL AUTO_INCREMENT,
  daily_aqi_id INT NOT NULL,
  station_id INT NOT NULL,
  city_name VARCHAR(50) COLLATE utf8mb4_unicode_ci NOT NULL,
  month TINYINT NOT NULL,
  median_aqi DECIMAL(6,2) NOT NULL,
  mad_aqi DECIMAL(6,2) NOT NULL,
  modified_z DECIMAL(8,4) NOT NULL,
  is_anomaly TINYINT(1) NOT NULL,
  baseline_note VARCHAR(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  PRIMARY KEY (anomaly_id),
  UNIQUE KEY uq_anomaly_reading (daily_aqi_id),
  KEY fk_anomaly_station (station_id),
  CONSTRAINT fk_anomaly_daily_aqi FOREIGN KEY (daily_aqi_id) REFERENCES fact_kaggle_daily_aqi (daily_aqi_id),
  CONSTRAINT fk_anomaly_station FOREIGN KEY (station_id) REFERENCES dim_station (station_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- Early warning system (Phase 11)
-- Pulled directly via `SHOW CREATE TABLE` against the live database
-- (this housekeeping pass) rather than reconstructed from memory.
-- horizon left as a plain TINYINT (not an ENUM restricted to 1/3) so a
-- future 7-day horizon only needs new rows, not a schema change --
-- same "widen, don't rebuild" principle as dim_station.source_system.
-- ============================================================

CREATE TABLE fact_early_warnings (
  warning_id INT NOT NULL AUTO_INCREMENT,
  city_id INT NOT NULL,
  reading_date DATE NOT NULL,
  target_date DATE NOT NULL,
  horizon TINYINT NOT NULL,
  model_used ENUM('ridge','persistence') COLLATE utf8mb4_unicode_ci NOT NULL,
  actual_aqi DECIMAL(6,2) DEFAULT NULL,
  predicted_aqi DECIMAL(6,2) DEFAULT NULL,
  actual_category VARCHAR(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  predicted_category VARCHAR(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  triggered TINYINT(1) NOT NULL,
  reliability_tier ENUM('reliable','known_unreliable','unvalidated') COLLATE utf8mb4_unicode_ci NOT NULL,
  warning_label VARCHAR(60) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  is_new_episode TINYINT(1) NOT NULL,
  PRIMARY KEY (warning_id),
  UNIQUE KEY uq_warning (city_id,target_date,horizon),
  CONSTRAINT fact_early_warnings_ibfk_1 FOREIGN KEY (city_id) REFERENCES dim_city (city_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
