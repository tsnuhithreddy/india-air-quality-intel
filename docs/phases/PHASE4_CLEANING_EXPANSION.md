# Phase 4: Cleaning Expansion and Schema Conventions

**Project:** India Urban Air Quality Intelligence & Early-Warning System
**Status:** Complete

## Overview

By the end of Phase 3, only one of the three live sources (data.gov.in) had a cleaning script. OpenAQ and Open-Meteo were being collected every hour but sat in raw JSON with no processing. This phase wrote cleaning scripts for both, using the same approach as `clean_data_gov_in.py`, and settled the column and timestamp conventions the three cleaned outputs share so they can be loaded into a database later.

Scripts added:

| Script | Input | Output |
|---|---|---|
| `src/processing/clean_openaq.py` | `openaq_locations_*.json` + `openaq_latest_*.json` | `data/processed/openaq/<date>/openaq_clean_<timestamp>.csv` |
| `src/processing/clean_open_meteo.py` | `open_meteo_*.json` | `data/processed/open_meteo/<date>/open_meteo_current_clean_<timestamp>.csv` and `open_meteo_forecast_clean_<timestamp>.csv` |

## Design principles

**Flag, don't drop.** Bad or missing values are never deleted. Each row gets boolean flag columns, and a combined `is_suspicious` column marks any row where at least one flag is set. Later analysis can then decide what to exclude, and nothing is lost silently.

**Different kinds of numbers stay separate.** data.gov.in reports AQI sub-index scores on a 0-500 scale. OpenAQ reports physical concentrations (mostly µg/m³). These are not comparable number for number, so the cleaned columns are named differently on purpose: `sub_index_min/max/avg` for data.gov.in, `concentration_value` plus an explicit `unit` for OpenAQ.

**Check against real data.** Both scripts were run against real raw snapshots collected by the hourly scheduler, not sample or hand-made files.

## OpenAQ cleaning (`clean_openaq.py`)

OpenAQ v3 splits its information across two files: the locations file (which stations exist, which sensors they have, and what each sensor measures) and the latest file (the readings, which identify sensors only by ID). The script joins them.

**Steps**

1. Read the locations file and build two lookups: sensor ID to pollutant, unit and station details, and location ID to station name, locality and coordinates.
2. Read the latest-readings file and attach the sensor details to each reading by `sensorsId`.
3. Map OpenAQ parameter names to the project's standard pollutant codes (`pm25` to `PM2.5`, `ozone` to `O3`, and so on).
4. Convert values to numbers and parse both the local (+05:30) and UTC timestamps.
5. Add the quality flags.

**Idle stations.** Some registered stations return no readings at all. These are kept as a single row with the station name and coordinates filled in, no pollutant or value, and `flag_missing = True`. This keeps the information that the station exists but is not reporting.

**Flags**

| Flag | Meaning |
|---|---|
| `flag_negative` | value below 0 |
| `flag_sentinel` | value is 999, 9999 or -999 |
| `flag_missing` | no value |
| `flag_zero` | value is exactly 0.0 |
| `is_suspicious` | any of the above |

**Output columns:** `station_id, station_name, locality, sensor_id, pollutant_id, concentration_value, unit, timestamp_local, timestamp_utc, latitude, longitude, flag_negative, flag_sentinel, flag_missing, flag_zero, is_suspicious`

## Open-Meteo cleaning (`clean_open_meteo.py`)

Open-Meteo returns one batched response covering all 11 target cities. The script splits it into two tables because they describe different things.

- **Current conditions:** one row per city, with temperature, humidity, wind speed and direction, precipitation, surface pressure and elevation.
- **24-hour forecast:** one row per city per hour (11 x 24 = 264 rows), with temperature, humidity, wind speed and precipitation, plus `forecast_step_hour` (0 to 23) showing how far ahead each row is.

Columns are renamed so units are visible: `temperature_c`, `relative_humidity_pct`, `wind_speed_kmh`, `wind_direction_deg`, `precipitation_mm`, `surface_pressure_hpa`.

**Flags**

| Flag | Rule | Current | Forecast |
|---|---|---|---|
| `flag_humidity_invalid` | outside 0-100% | yes | yes |
| `flag_temperature_extreme` | below -20 °C or above 60 °C | yes | yes |
| `flag_wind_negative` | wind speed below 0 | yes | yes |
| `flag_pressure_invalid` | outside 800-1100 hPa | yes | no |
| `flag_missing` | temperature, humidity or wind speed is null | yes | yes |
| `is_suspicious` | any of the above | yes | yes |

The forecast table has no pressure flag because it does not include a pressure column.

## Shared conventions across the three sources

| | data.gov.in | OpenAQ | Open-Meteo |
|---|---|---|---|
| Value type | AQI sub-index (0-500) | Concentration | Weather |
| Value columns | `sub_index_min/max/avg` | `concentration_value`, `unit` | `temperature_c`, `relative_humidity_pct`, etc. |
| Timestamp | `last_update` (IST) | `timestamp_local`, `timestamp_utc` | `timestamp_local` / `forecast_timestamp_local` |
| Location | `city`, `station`, `latitude`, `longitude` | `station_name`, `locality`, `latitude`, `longitude` | `city_name`, `latitude`, `longitude` |
| Quality handling | flag, don't drop | flag, don't drop | flag, don't drop |

Other shared rules:

- Coordinates are always called `latitude` and `longitude`.
- Quality flag columns are boolean, with an `is_suspicious` rollup.
- Processed files are saved under `data/processed/<source>/<YYYY-MM-DD>/` with a timestamp in the filename.
- Each script reads the newest matching raw file by default, or a specific file passed to its main function.

## Verification

Both scripts were run against real unattended snapshots from the scheduler.

- **OpenAQ:** 150 readings across 20 stations, 4.0% (6 rows) flagged as suspicious. Stations that returned nothing were kept as flagged rows rather than dropped.
- **Open-Meteo:** current weather for 11 cities and 264 forecast rows (11 x 24), with no physical range violations.

The first cleaning run of each script was checked by reading rows from the output CSV against the raw JSON, not just by confirming the script finished without an error.

## Known limitations

These were noticed at the end of the phase and deliberately left alone.

1. **`flag_zero` is a blunt rule.** Every exact 0.0 reading is marked suspicious. For some pollutants a true zero is plausible, so this may over-flag. Worth revisiting if a specific pollutant shows many zeros.
2. **Timestamps are not fully uniform.** OpenAQ timestamps carry a +05:30 offset. Open-Meteo timestamps are local IST strings without an offset, so they parse as timezone-naive. They line up by clock time but are not identical in format.
3. **OpenAQ weather sensors are not filtered here.** Some OpenAQ stations report temperature, humidity and wind through the same parameter field as pollutants. The cleaner passes these through under their uppercased names. They are excluded later, at database loading (Phase 5).
4. **Division by zero in the OpenAQ summary log.** `process_latest_pair` computes a flagged percentage by dividing by the row count. If the output were ever completely empty this would raise an error. A one-line guard would fix it. Unlikely in practice, but not handled.
5. **Locations and latest files are picked independently.** Each is chosen as the newest file of its own type. If a run were interrupted between the two files, they could come from different fetches.
6. **Cleaning is still run by hand.** Automating cleaning and loading is planned for a later phase.

## Documentation updated

- `PROJECT_STATE.md`: marked Phase 4 complete and set the next step to MySQL setup and schema design.
- `docs/DATA_SOURCES_LOG.md`: added the OpenAQ and Open-Meteo cleaning notes and the cross-source conventions above.

## Next: Phase 5

Move the cleaned data from CSV files into MySQL. Confirm MySQL is installed and running, design a schema with dimension tables (city, station, pollutant) and fact tables (one each for CPCB sub-indices, OpenAQ concentrations, weather observations and weather forecasts), then write loaders that read `data/processed/` and keep the quality flag columns intact.
