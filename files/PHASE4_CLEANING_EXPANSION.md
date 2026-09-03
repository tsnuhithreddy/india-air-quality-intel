# Phase 4 — Cleaning Expansion & Schema Standardization
**Project:** India Urban Air Quality Intelligence & Early-Warning System  
**Status:** Complete

---

## 1. Executive Summary

Phase 4 expands the standardized data cleaning pipeline established in Phase 3 (`clean_data_gov_in.py`) across all live data sources:
1. **OpenAQ v3 API (`clean_openaq.py`):** Standardizes station and sensor metadata joined with live physical concentration readings ($\mu g/m^3$).
2. **Open-Meteo API (`clean_open_meteo.py`):** Standardizes city-level current weather observations and 24-hour hourly forward-looking forecasts.
3. **Cross-Source Schema Alignment:** Establishes shared timestamp conventions (`timestamp_local` in IST `+05:30` and `timestamp_utc`), geospatial coordinates (`latitude`, `longitude`), and a unified **"flag, don't drop"** QA layer.
4. **Preserved Semantic Distinction:** Strict separation between **AQI sub-indices (0–500 scale)** from `data.gov.in` and **physical concentrations ($\mu g/m^3$)** from `OpenAQ`.

---

## 2. Source-by-Source Cleaning Design

### A. OpenAQ v3 (`src/processing/clean_openaq.py`)
- **Input:** `openaq_locations_<timestamp>.json` and `openaq_latest_<timestamp>.json`.
- **Transformation Logic:**
  - Extracts and indexes sensor definitions from the locations payload mapping `sensor_id` $\rightarrow$ standardized pollutant name (`PM2.5`, `PM10`, `NO2`, `SO2`, `CO`, `O3`, `BC`, `NH3`), units (`µg/m³`, `ppm`, `ppb`), and station coordinates.
  - Joins sensor metadata onto each reading in `latest_readings`.
  - Handles idle/unreporting stations gracefully (retaining station name and coordinates with `flag_missing=True`).
  - Standardizes local and UTC timestamps (`YYYY-MM-DD HH:MM:SS+05:30` and `YYYY-MM-DD HH:MM:SS+00:00`).
- **Quality Flags:**
  - `flag_negative`: Concentration $< 0$.
  - `flag_sentinel`: Sentinel/placeholder error codes (`999`, `9999`, `-999`).
  - `flag_missing`: Null/empty concentration readings.
  - `flag_zero`: Exactly $0.0$ readings (identifying inactive or uncalibrated sensors).
  - `is_suspicious`: Composite flag indicating any anomaly.
- **Output Schema:**
  `station_id, station_name, locality, sensor_id, pollutant_id, concentration_value, unit, timestamp_local, timestamp_utc, latitude, longitude, flag_negative, flag_sentinel, flag_missing, flag_zero, is_suspicious`

---

### B. Open-Meteo Weather (`src/processing/clean_open_meteo.py`)
- **Input:** `open_meteo_<timestamp>.json` (batched response for all 11 target cities).
- **Transformation Logic:**
  - Parses two distinct analytical views:
    1. **Current Weather Snapshot:** 1 row per city containing observed temperature, humidity, wind speed & direction, precipitation, surface pressure, and elevation.
    2. **24-Hour Hourly Forecast:** 24 rows per city ($11 \times 24 = 264$ rows total) containing step-by-step forward weather predictions.
  - Standardizes metric names and units (`temperature_c`, `relative_humidity_pct`, `wind_speed_kmh`, `wind_direction_deg`, `precipitation_mm`, `surface_pressure_hpa`).
- **Quality Flags:**
  - `flag_humidity_invalid`: Relative humidity outside $[0, 100]\%$.
  - `flag_temperature_extreme`: Temperature outside $[-20^\circ\text{C}, 60^\circ\text{C}]$.
  - `flag_wind_negative`: Wind speed $< 0\text{ km/h}$.
  - `flag_pressure_invalid`: Surface pressure outside $[800, 1100]\text{ hPa}$.
  - `flag_missing`: Null values in required meteorological parameters.
  - `is_suspicious`: Composite flag.
- **Output Schemas:**
  - Current: `city_name, timestamp_local, temperature_c, relative_humidity_pct, wind_speed_kmh, wind_direction_deg, precipitation_mm, surface_pressure_hpa, latitude, longitude, elevation_m, flag_humidity_invalid, flag_temperature_extreme, flag_wind_negative, flag_pressure_invalid, flag_missing, is_suspicious`
  - Forecast: `city_name, forecast_timestamp_local, forecast_step_hour, temperature_c, relative_humidity_pct, wind_speed_kmh, precipitation_mm, latitude, longitude, flag_humidity_invalid, flag_temperature_extreme, flag_wind_negative, flag_missing, is_suspicious`

---

### C. data.gov.in (`src/processing/clean_data_gov_in.py`)
- Standardized long-format table mapping CPCB sub-index scores (`sub_index_min`, `sub_index_max`, `sub_index_avg`).
- Flags sentinel, negative, and missing sub-indices without row dropping.
- **Output Schema:**
  `country, state, city, station, last_update, latitude, longitude, pollutant_id, sub_index_min, sub_index_max, sub_index_avg, flag_negative, flag_sentinel, flag_missing, is_suspicious`

---

## 3. Cross-Source Standardization Summary

| Feature | `data.gov.in` | `OpenAQ v3` | `Open-Meteo` |
|---|---|---|---|
| **Measurement Type** | AQI Sub-Index (0–500) | Physical Concentration | Weather Covariates |
| **Value Column(s)** | `sub_index_min/max/avg` | `concentration_value`, `unit` | `temperature_c`, `relative_humidity_pct`, etc. |
| **Time Reference** | `last_update` (IST) | `timestamp_local`, `timestamp_utc` | `timestamp_local` / `forecast_timestamp_local` |
| **Geographic Keys** | `city`, `station`, `latitude`, `longitude` | `station_name`, `locality`, `latitude`, `longitude` | `city_name`, `latitude`, `longitude` |
| **QA Strategy** | Flag-don't-drop | Flag-don't-drop | Flag-don't-drop |

---

## 4. Verification Results
- **OpenAQ Cleaning:** Processed real unattended snapshot ($150$ records across $20$ stations; $4.0\%$ flagged as suspicious due to expected idle sensors).
- **Open-Meteo Cleaning:** Successfully parsed 11 city current weather observations and $264$ forecast hours ($11 \times 24$) with zero physical range violations.
- **Storage Organization:** All processed files partitioned by date under `data/processed/<source>/<YYYY-MM-DD>/`.

---

## 5. Next Phase (Phase 5)
**Phase 5 — Relational Storage & Database Loading (MySQL):**
- Design relational database schema (Dimension tables: `dim_city`, `dim_station`, `dim_pollutant`; Fact tables: `fact_cpcb_subindex`, `fact_openaq_concentration`, `fact_weather_observations`, `fact_weather_forecast`).
- Implement automated ETL loaders from `data/processed/` into MySQL.
