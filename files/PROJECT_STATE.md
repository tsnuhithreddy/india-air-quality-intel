# Project State

**Project Name:** India Urban Air Quality Intelligence & Early-Warning System

**Current Phase:** Phase 6 Complete → Ready for Phase 7

---

## Completed Work

* Phase 1: Validated all candidate data sources, finalized architecture
* Phase 2: Built local dev environment, config, secrets handling, logging,
  and first working ingestion script (data.gov.in)
* Phase 3: Added OpenAQ + Open-Meteo ingestion scripts, downloaded and
  verified Kaggle historical dataset, automated hourly polling for ALL
  THREE live sources via Windows Task Scheduler, fixed an API-key logging
  leak, built the first raw-to-processed cleaning script (data.gov.in),
  and built a pipeline health-check monitoring script
* Phase 4: Extended raw-to-processed cleaning to OpenAQ (`clean_openaq.py`)
  and Open-Meteo (`clean_open_meteo.py`), established shared schema
  conventions (aligned timestamps, coordinates, flag-don't-drop quality
  checks), and strictly maintained the distinction between 0-500 AQI
  sub-indices (data.gov.in) and raw physical concentrations in µg/m³
  (OpenAQ)
* Phase 5: Designed and built the MySQL relational schema (3 dimension
  tables + 4 fact tables) with real primary/foreign keys and unique
  constraints; created a dedicated least-privilege `aqi_loader` database
  user; wrote and verified a Python loader per live source
  (`load_data_gov_in.py`, `load_openaq.py`, `load_open_meteo.py`) plus a
  combined runner (`load_all.py`); confirmed all loaders are duplicate-safe
  and all inserted data was spot-checked against real Workbench queries,
  not just trusted from script logs
* **Phase 6: Closed the last data-source gap — built `clean_kaggle.py`
  (reshapes the Kaggle historical dataset from wide to long format,
  filters to the 90 real stations across 10 of 11 target cities) and
  `load_kaggle.py` (reuses the exact connection/duplicate-handling
  pattern from `load_openaq.py`); designed and created two new fact
  tables (`fact_kaggle_historical`, `fact_kaggle_daily_aqi`) to keep
  per-pollutant readings and single daily AQI scores from ever being
  blurred together; widened `dim_station.source_system` to include
  `'kaggle'`; expanded `dim_pollutant` from 11 to 14 codes (added
  Benzene, Toluene, Xylene, found missing during Kaggle column
  reconciliation); loaded and fully verified 1,140,696 historical
  pollutant readings and 95,058 daily AQI rows against real database
  queries — not just clean script output. Refined the known Pune gap:
  confirmed at the row level that Pune's one listed station has zero
  actual readings, not just "city absent."**

## Current Decisions

* Live ingestion pipeline polls data.gov.in, OpenAQ, and Open-Meteo hourly
  via Windows Task Scheduler, staggered a few minutes apart — all three
  confirmed working via real unattended file drops, not just configuration
* OpenAQ v3 used as backup/cross-validation source — **cannot be directly
  numerically compared to data.gov.in's values** (sub-index vs concentration)
* Open-Meteo weather pulled for all 11 target cities in a single batched
  API call (comma-separated lat/lon), producing current snapshot and 24h forecast
* Historical model development bootstraps from Kaggle CPCB dataset —
  **coverage corrected to 2015-2020** (originally misdocumented as 2015-2024)
* **Kaggle dataset does not include Pune** — 10 of 11 target metros covered;
  Pune's one listed station in `stations.csv` exists in the metadata file
  but has zero actual reading rows in `station_day.csv` — confirmed at the
  row level in Phase 6, same practical gap, more precise root cause than
  originally documented; Pune has no historical bootstrap, only live data
  from Aug 2026 onward
* Geospatial analysis remains secondary
* Population/exposure data uses static reference table (low priority)
* Raw data stored as JSON, processed data stored as CSV
  (data/raw/<source>/<date>/*.json, data/processed/<source>/<date>/*.csv)
* data.gov.in requires a browser-like User-Agent header — API silently
  times out otherwise
* **data.gov.in's min/max/avg fields are AQI sub-index scores (0-500
  health-severity scale), NOT raw pollutant concentrations in µg/m³ or
  mg/m³** — discovered/corrected in Phase 3. Cleaned columns named
  sub_index_min/max/avg to make this explicit.
* API keys are redacted from error logs via a `redact_secrets()` helper
  in `secrets_loader.py`, applied to both data.gov.in and OpenAQ scripts
* **Windows Task Scheduler's "Start the task only if on AC power" is
  checked by DEFAULT for every newly created task** and must be explicitly
  unchecked (Conditions tab) or the task silently never fires.
* Tasks only run while logged on; a run in progress when the machine
  sleeps/logs off gets killed mid-execution with no exception logged.
* MySQL database `india_air_quality` holds all processed data; sub-index
  (data.gov.in), concentration (OpenAQ), and historical (Kaggle) readings
  are kept in separate fact tables and can never be merged into one column
* Loader scripts authenticate as a dedicated `aqi_loader` user
  (SELECT/INSERT/UPDATE only) — verified this user cannot DROP tables
* `dim_station.city_id` is nullable — OpenAQ stations aren't matched to
  a target city (cross-source station matching remains deferred, per
  Phase 1); Kaggle stations DO get a real `city_id`, looked up from
  `stations.csv`'s real city names via `dim_city`
* OpenAQ occasionally reports weather-sensor readings (temperature,
  humidity, wind) through its pollutant field — deliberately excluded from
  pollutant tables, not loaded anywhere yet
* Weather observations reject duplicates (first reading per hour kept);
  weather forecasts overwrite duplicates (latest prediction per hour kept)
* **Kaggle historical data IS now in MySQL** (Phase 6) — split across two
  tables: `fact_kaggle_historical` (per-pollutant daily readings,
  1,140,696 rows) and `fact_kaggle_daily_aqi` (single daily AQI score per
  station, 95,058 rows). Verified the raw Kaggle values contain zero
  negative/sentinel values (unlike the live sources) — investigated
  directly rather than assumed, and concluded this dataset was likely
  pre-cleaned by its original publisher.
* `dim_station.source_system` ENUM widened in Phase 6 to
  `('data_gov_in', 'openaq', 'kaggle')`
* `dim_pollutant` expanded in Phase 6 from 11 to 14 codes — added
  `Benzene`, `Toluene`, `Xylene` (found in Kaggle data, not present in
  any live source)
* Kaggle stations are new, unmatched rows in `dim_station` — not linked
  to existing data.gov.in/OpenAQ stations even when physically nearby,
  consistent with the cross-source station-matching deferral from
  Phase 1/5

## Selected Data Sources

* **Primary:** data.gov.in CPCB Real-Time AQI API — tested, working,
  scheduled hourly, cleaned via `clean_data_gov_in.py`, loaded via
  `load_data_gov_in.py`
* **Secondary/backup:** OpenAQ v3 API — tested, working, scheduled hourly,
  cleaned via `clean_openaq.py`, loaded via `load_openaq.py`
* **Supporting:** Open-Meteo (weather) — tested, working, scheduled hourly,
  single batched call for all cities, cleaned via `clean_open_meteo.py`,
  loaded via `load_open_meteo.py`
* **Supporting:** Kaggle CPCB historical dataset — downloaded and
  verified (2015-01-01 to 2020-07-01, 26 cities nationwide, Pune not
  included), filtered to 90 real stations across 10 target cities,
  cleaned via `clean_kaggle.py`, **now loaded via `load_kaggle.py`**
  (Phase 6)
* **Optional/manual:** CPCB CCR portal — deferred

## Planned Technologies

* Python, Pandas, NumPy — in active use across ingestion, cleaning,
  loading, and monitoring
* Windows Task Scheduler — hourly automated polling of all three live
  sources
* MySQL — relational storage for all four data sources (built Phase 5,
  extended Phase 6)
* Power BI + DAX — post-database modeling (candidate for Phase 7)
* Git/GitHub — local repo tracking all phase changes

## Current Architecture

```
[data.gov.in API]  ──hourly poll (AUTOMATED)──┐
[Open-Meteo API]   ──hourly poll (AUTOMATED)──┼──> Raw JSON ──> Cleaning (CSV) ──> Python Loaders ──┐
[OpenAQ API]        ──hourly poll (AUTOMATED)─┘                                                      │
[Kaggle historical] ──clean_kaggle.py──> 2 CSVs ──> load_kaggle.py ─────────────────────────────────┤
                                                                                                       ▼
                                                                                          MySQL: india_air_quality
                                                                                    ┌─────────────┴─────────────────────┐
                                                                              dim_city, dim_pollutant (14),      fact_cpcb_subindex,
                                                                              dim_station (incl. 90 kaggle)      fact_openaq_concentration,
                                                                                                                 fact_weather_observations,
                                                                                                                 fact_weather_forecast,
                                                                                                                 fact_kaggle_historical (1,140,696 rows),
                                                                                                                 fact_kaggle_daily_aqi (95,058 rows)
                                                                                                                          │
                                                                                                                          ▼
                                                                                                          Analysis / ML layer (future — Phase 7)
```

## Project Structure (as built)

```
india-air-quality-intel/
├── venv/                                    (not committed)
├── data/raw/data_gov_in/                    (hourly automated snapshots)
├── data/raw/openaq/                         (hourly automated snapshots)
├── data/raw/open_meteo/                     (hourly automated snapshots)
├── data/processed/data_gov_in/              (cleaned CSVs - AQI sub-indices)
├── data/processed/openaq/                   (cleaned CSVs - concentrations)
├── data/processed/open_meteo/               (cleaned CSVs - current & forecast)
├── data/processed/kaggle/                   (cleaned CSVs - historical readings + daily AQI)
├── data/external/kaggle_air_quality_india/  (5 CSVs, 2015-2020)
├── config/config.py                         (URLs, cities, paths, timeout, CITY_COORDINATES)
├── src/utils/secrets_loader.py              (loads .env keys + redact_secrets())
├── src/utils/logger.py                      (console + daily file logging)
├── src/utils/db_connector.py                (WORKING - shared MySQL connection helper)
├── src/ingestion/fetch_data_gov_in.py       (WORKING - scheduled hourly)
├── src/ingestion/fetch_openaq.py            (WORKING - scheduled hourly)
├── src/ingestion/fetch_open_meteo.py        (WORKING - scheduled hourly)
├── src/ingestion/verify_kaggle_data.py      (WORKING - one-time verification)
├── src/processing/clean_data_gov_in.py      (WORKING - data.gov.in cleaner)
├── src/processing/clean_openaq.py           (WORKING - OpenAQ cleaner)
├── src/processing/clean_open_meteo.py       (WORKING - Open-Meteo cleaner)
├── src/processing/clean_kaggle.py           (WORKING - Kaggle cleaner, wide-to-long reshape)
├── src/monitoring/check_pipeline_health.py  (WORKING - pipeline health check)
├── src/loading/load_data_gov_in.py          (WORKING - loads sub-index readings, tested duplicate-safe)
├── src/loading/load_openaq.py               (WORKING - loads concentration readings, handles idle stations)
├── src/loading/load_open_meteo.py           (WORKING - loads weather obs + forecast)
├── src/loading/load_kaggle.py               (WORKING - loads historical readings + daily AQI, tested duplicate-safe)
├── src/loading/load_all.py                  (WORKING - runs all three LIVE loaders for a given date; Kaggle run separately, one-time)
├── scripts/run_data_gov_in.bat               (Task Scheduler launcher)
├── scripts/run_openaq.bat                    (Task Scheduler launcher)
├── scripts/run_open_meteo.bat                (Task Scheduler launcher)
├── sql/create_schema.sql                     (MySQL schema DDL — committed; extended Phase 6)
├── sql/create_loader_user.sql                (creates aqi_loader user — git-ignored, has password)
├── docs/DATA_SOURCES_LOG.md                  (tracks source testing dates/quirks)
├── files/PHASE1_DATA_SOURCE_VALIDATION.md    (Phase 1 documentation)
├── files/PHASE2_ENVIRONMENT_SETUP.md         (Phase 2 documentation)
├── files/PHASE3_INGESTION_EXPANSION_AND_SCHEDULING.md (Phase 3 documentation)
├── files/PHASE4_CLEANING_EXPANSION.md        (Phase 4 documentation)
├── files/PHASE5_DATABASE_LOADING.md          (Phase 5 documentation)
├── files/PHASE6_KAGGLE_HISTORICAL_LOADING.md (Phase 6 documentation — this phase)
├── requirements.txt
├── .env                                      (not committed - has real API keys + DB credentials)
└── .gitignore                                (verified excludes .env, venv/, data/)
```

## Next Phase

**Phase 7 — candidates, to be decided:**
- Automate the loader scripts themselves via Task Scheduler (same proven
  pattern as Phase 3's ingestion automation — proven manually first, then
  scheduled), now that all four sources have working, tested loaders; OR
- Begin real analysis / Power BI on the data already in MySQL, now that a
  genuine multi-year historical baseline exists behind the live data,
  supporting real trend charts and anomaly-detection baselines that
  weren't meaningful with only a few hours of live data.

## Exact Next Step

Decide which Phase 7 direction to take before starting new work.
