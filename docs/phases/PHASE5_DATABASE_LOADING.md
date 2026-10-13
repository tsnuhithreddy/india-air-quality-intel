# Phase 5 — Relational Storage & Database Loading (MySQL)

**Project:** India Urban Air Quality Intelligence & Early-Warning System
**Status:** Complete
**Date:** 2026-08-29

---

## 1. Summary

By the end of Phase 4, the three live sources (data.gov.in, OpenAQ, Open-Meteo) were being ingested hourly and cleaned into standardized CSV files under `data/processed/<source>/<date>/`. Nothing was stored in a database yet, so every question about the data meant opening files by hand.

This phase moved that cleaned data into a MySQL database (`india_air_quality`). The work covered:

- designing and creating a relational schema (3 dimension tables, 4 fact tables)
- creating a restricted database user for the loader scripts
- writing one Python loader per source, plus a small runner that chains them
- loading real processed files and checking the result against the database itself
- writing a first set of analytical SQL queries against the loaded tables

Kaggle historical data is not part of this phase. It has no cleaning script yet, so there was nothing for a loader to read.

---

## 2. Tooling

| Task | Tool |
|---|---|
| Writing `.py` and `.sql` files | VS Code |
| Running SQL, browsing tables, checking data | MySQL Workbench |
| OS-level checks (service status, PATH), `pip` | PowerShell |

MySQL Server 8.0.44 was already installed. Before building anything, the `MySQL80` Windows service was confirmed running and a real login was tested. The `mysql` client was not on PATH, so its folder (`C:\Program Files\MySQL\MySQL Server 8.0\bin`) was added to the system PATH.

Python dependency added: `mysql-connector-python` (recorded in `requirements.txt`).

---

## 3. Schema

The schema follows a star layout: small dimension tables for descriptive reference data, and fact tables for the readings, which grow with every load. The full DDL is in `sql/create_schema.sql`.

One design rule shaped most of the schema: **data.gov.in values and OpenAQ values are different kinds of numbers** (Phase 3 finding). data.gov.in reports AQI sub-index scores on a 0–500 scale; OpenAQ reports real concentrations in µg/m³. They live in separate fact tables with differently named value columns, so they cannot end up in the same column or be averaged together by accident.

### 3.1 Dimension tables

**`dim_city`** — the 11 target metros.

| Column | Type | Notes |
|---|---|---|
| `city_id` | INT, PK, auto-increment | |
| `city_name` | VARCHAR(50), UNIQUE | Delhi, Mumbai, Bengaluru, Hyderabad, Chennai, Kolkata, Pune, Ahmedabad, Lucknow, Jaipur, Patna |
| `latitude`, `longitude` | DECIMAL(9,6) | Approximate city-centre points |
| `has_kaggle_historical_data` | BOOLEAN | `FALSE` for Pune only (not covered by the Kaggle dataset) |

Seeded by hand, since the list is fixed and known in advance.

**`dim_pollutant`** — one row per pollutant code. 11 rows: PM2.5, PM10, SO2, NO2, CO, O3, NH3, Pb, BC, NO, NOX. The first eight came from Phase 1, `BC` from Phase 4, and `NO`/`NOX` were added during this phase (section 6.3).

**`dim_station`** — one row per monitoring station, from either source.

| Column | Type | Notes |
|---|---|---|
| `station_id` | INT, PK, auto-increment | |
| `source_system` | ENUM('data_gov_in','openaq') | The database rejects any other value |
| `source_station_key` | VARCHAR(150) | The station's identifier in its own source system |
| `station_name` | VARCHAR(150) | |
| `city_id` | INT, **nullable**, FK → `dim_city` | NULL for OpenAQ stations (section 6.2) |
| `latitude`, `longitude` | DECIMAL(9,6), nullable | |

`(source_system, source_station_key)` is unique. This table is filled by the loaders, not by hand, because the station list only exists inside the real data files.

### 3.2 Fact tables

All four carry the same "flag, don't drop" approach as the cleaning scripts: questionable or missing values keep their row and get a boolean flag. Value columns are nullable so a missing reading is stored as missing rather than as zero.

**`fact_cpcb_subindex`** — data.gov.in readings.

| Column | Meaning |
|---|---|
| `reading_id` | PK, `BIGINT` auto-increment |
| `station_id`, `pollutant_id` | FKs to `dim_station`, `dim_pollutant` |
| `timestamp_local` | Reading time (IST), `DATETIME` |
| `sub_index_min`, `sub_index_max`, `sub_index_avg` | AQI sub-index scores (0–500), nullable |
| `flag_negative`, `flag_sentinel`, `flag_missing`, `is_suspicious` | Quality flags from the cleaning step |

Unique on `(station_id, pollutant_id, timestamp_local)`.

**`fact_openaq_concentration`** — OpenAQ readings.

| Column | Meaning |
|---|---|
| `reading_id` | PK |
| `station_id`, `pollutant_id` | FKs |
| `sensor_id` | OpenAQ sensor that produced the reading, nullable |
| `timestamp_local`, `timestamp_utc` | Reading time in IST and UTC |
| `concentration_value`, `unit` | Real concentration (µg/m³), value nullable |
| `flag_negative`, `flag_sentinel`, `flag_missing`, `flag_zero`, `is_suspicious` | Quality flags. `flag_zero` marks exact 0.0 readings, which usually indicate an inactive or uncalibrated sensor |

Unique on `(station_id, pollutant_id, timestamp_local)`.

**`fact_weather_observations`** — Open-Meteo current conditions, one row per city per hour.

Columns: `observation_id` (PK), `city_id` (FK), `timestamp_local`, `temperature_c`, `relative_humidity_pct`, `wind_speed_kmh`, `wind_direction_deg`, `precipitation_mm`, `surface_pressure_hpa`, `elevation_m`, plus `flag_humidity_invalid`, `flag_temperature_extreme`, `flag_wind_negative`, `flag_pressure_invalid`, `flag_missing`, `is_suspicious`. Unique on `(city_id, timestamp_local)`.

**`fact_weather_forecast`** — Open-Meteo 24-hour forecast, one row per city per predicted hour.

Columns: `forecast_id` (PK), `city_id` (FK), `forecast_timestamp_local`, `forecast_step_hour`, `temperature_c`, `relative_humidity_pct`, `wind_speed_kmh`, `precipitation_mm`, plus `flag_humidity_invalid`, `flag_temperature_extreme`, `flag_wind_negative`, `flag_missing`, `is_suspicious`. Unique on `(city_id, forecast_timestamp_local)`.

### 3.3 Duplicate handling

The rule differs by table, on purpose:

| Table | If the same row arrives again | Why |
|---|---|---|
| `fact_cpcb_subindex`, `fact_openaq_concentration`, `fact_weather_observations` | Rejected; the first version is kept | These are historical observations. Re-running a loader must not double-count them |
| `fact_weather_forecast` | Overwritten with the newer values (`ON DUPLICATE KEY UPDATE`) | Every hourly run re-predicts the same future hours, and only the latest prediction is useful |

For `fact_weather_observations`, "first reading per hour wins" was a deliberate choice. Two pulls in the same hour describe the same moment and are nearly identical, so keeping the first is simpler and consistent with the other observation tables.

---

## 4. Database user and credentials

The loaders do not connect as `root`. A separate user, `aqi_loader`, was created with only the privileges the loaders need:

```sql
CREATE USER 'aqi_loader'@'localhost' IDENTIFIED BY '<password>';
GRANT SELECT, INSERT, UPDATE ON india_air_quality.* TO 'aqi_loader'@'localhost';
```

The restriction was tested rather than assumed: connected as `aqi_loader`, `SELECT` worked and `DROP TABLE dim_city` was refused with `Error 1142: DROP command denied`.

Credentials live in `.env` (`MYSQL_USER`, `MYSQL_PASSWORD`), which is git-ignored, alongside the existing API keys. The user-creation script contains a plaintext password, so `sql/create_loader_user.sql` is git-ignored as well and is not committed.

`src/utils/db_connector.py` exposes `get_connection()`, which reads those variables and raises a clear error if they are missing or the connection fails. It follows the same pattern as `secrets_loader.py`.

---

## 5. Loaders

All loaders live in `src/loading/` and share the same shape: read a processed CSV, resolve IDs against the dimension tables, insert, and log a summary of what happened. They commit once at the end of a file, so a crash partway through leaves nothing half-loaded.

Because the cleaning scripts write flags to CSV as the text `"True"`/`"False"`, and any non-empty string is truthy in Python, each loader converts them with an explicit `str_to_bool()` rather than `bool()`.

### `load_data_gov_in.py`

For each row: look up the city in `dim_city`, find or create the station in `dim_station`, look up the pollutant, insert into `fact_cpcb_subindex`. Rows for cities outside the 11 targets are skipped and counted.

### `load_openaq.py`

Same flow, with two differences:

- Stations are inserted with `city_id = NULL`, since OpenAQ's data does not say which target city a station belongs to.
- Idle stations (registered but reporting nothing, so no sensor, pollutant or timestamp) are still recorded in `dim_station`, but produce no fact row. A fact row represents a measurement at a point in time, and these have none. They are counted separately as `skipped_idle_station`.

### `load_open_meteo.py`

No station discovery is needed, because `city_name` in the CSV matches `dim_city` directly. The script detects which file it was given (a `forecast_step_hour` column means forecast) and routes it to the observations table or the forecast table accordingly.

### `load_all.py`

Runs the three loaders for one date: `python -m src.loading.load_all 2026-08-28`. It finds every CSV under `data/processed/<source>/<date>/` and passes each to the matching loader. It adds no loading logic of its own. It is run by hand; scheduling is not part of this phase.

---

## 6. Issues found and how they were resolved

These all surfaced from checking real files and real results, not from the original design.

1. **`sensor_id` missing from `fact_openaq_concentration`.** The cleaned OpenAQ CSV contains it; the first schema did not. Found by comparing the CSV header against the table before any data was loaded, and added with `ALTER TABLE`.

2. **`dim_station.city_id` was `NOT NULL`.** That suited data.gov.in stations but would have failed for every OpenAQ station. Rather than guess a city, the column was changed to allow `NULL`. Cross-source station matching was already deferred in Phase 1, and this keeps the gap visible instead of hiding it behind an invented value.

3. **`NO` and `NOX` missing from `dim_pollutant`.** The first real OpenAQ load rejected rows with these codes. Both are genuine pollutants, so they were added to the table.

4. **OpenAQ reports weather through the pollutant field.** Some stations carry weather sensors, and their readings (`TEMPERATURE`, `RELATIVEHUMIDITY`, `WIND_SPEED`, `WIND_DIRECTION`) arrive with the same field used for pollutants. These are deliberately not loaded: a wind speed is not a pollutant concentration, and putting it in `fact_openaq_concentration` would undo the separation the schema is built around. The loader logs and counts them as `skipped_unknown_pollutant`. Weather data comes from Open-Meteo.

5. **Python import error when running a loader as a script.** `python src/loading/load_data_gov_in.py` failed with `ModuleNotFoundError: No module named 'src'`, because Python only adds the script's own folder to its path. Loaders are run as modules from the project root instead (`python -m src.loading.load_data_gov_in <csv>`).

6. **A summary line that did not add up.** One OpenAQ run's pasted summary showed `skipped_unknown_pollutant=2`, but the four counts only reached 132 of the 150 rows read. The full terminal output showed the real value was `20`; the summary had been truncated when copied. The rows were fully accounted for once the correct figure was used. Since then, loader counts are reconciled against rows read.

7. **Processed folders hold only recent runs.** Raw folders contain every date because ingestion is scheduled, but cleaning is still run by hand, so `data/processed/` only holds the latest manual run per source. This is a consequence of scope, not a fault, and it limits how much history can be loaded for now.

---

## 7. Verification

Each loader was checked against the database, not only against its own log.

| Check | Result |
|---|---|
| `fact_cpcb_subindex` row count vs. loader summary | 545 / 545 |
| data.gov.in stations in `dim_station` | 134 |
| `fact_openaq_concentration` row count | 127 (117 on first run + 10 after `NO`/`NOX` were added) |
| OpenAQ stations in `dim_station` | 20 |
| `fact_weather_observations` row count | 11 |
| `fact_weather_forecast` row count | 264 (11 cities × 24 hours) |
| Re-running the same data.gov.in file | `inserted=0, skipped_duplicate=545`; table count unchanged |
| Re-running the same forecast file | Count stayed at 264, not 528 |
| `load_all` over a date that was already loaded | No new rows; counts unchanged after the run |
| `DROP TABLE` as `aqi_loader` | Refused (Error 1142) |

Row accounting for the OpenAQ file (150 rows read): 127 inserted + 3 idle stations + 20 weather-sensor rows = 150.

Reading the data.gov.in file (2,000 rows): 545 loaded + 1,455 belonging to cities outside the 11 targets = 2,000. Skipped rows are logged, not silently dropped.

Running `load_all` also showed that a single date folder can contain more than one processed file per source (several cleaning runs on the same day). The runner loads all of them; the extra files came back as duplicates, as expected.

---

## 8. SQL analysis queries

`sql/analysis_queries.sql` contains seven analytical queries against the tables above, so the database can be queried directly rather than only checked with one-off counts. Each query has a comment stating the question it answers.

| # | Question | Technique |
|---|---|---|
| Q1 | Which pollutant has the highest average sub-index in each city? | Aggregation, 4-table join |
| Q2 | Which OpenAQ station reports the highest average concentration for each pollutant? | `RANK() OVER (PARTITION BY …)` |
| Q3 | Which data.gov.in stations read above the all-station average? | Non-correlated subquery |
| Q4 | Which stations read above their own city's average? | Correlated subquery |
| Q5 | How do each city's pollution readings sit next to its current wind and rain? | Join across two independently collected sources |
| Q6 | What does a 3-hour rolling average of the forecast temperature look like per city? | Window function with a frame (`ROWS BETWEEN 2 PRECEDING AND CURRENT ROW`) |
| Q7 | Which pollutant is flagged suspicious most often across both live sources? | `UNION ALL` + aggregation |

Notes on the queries:

- OpenAQ stations have no city in `dim_station`, so Q2 groups by pollutant and station rather than by city.
- Q4 includes `s.city_id` in its `GROUP BY`. MySQL's default `ONLY_FULL_GROUP_BY` mode requires this for the correlated subquery to be able to reference it.
- At this point the live tables hold only a few days of data, so Q5 and Q6 are working with small samples. They are useful as query patterns now and become more meaningful as data accumulates.

---

## 9. Architecture at the end of this phase

```
[data.gov.in API]  ──hourly (scheduled)──┐
[OpenAQ API]       ──hourly (scheduled)──┼──> raw JSON ──> cleaning ──> processed CSV ──> loaders ──┐
[Open-Meteo API]   ──hourly (scheduled)──┘                                                          │
[Kaggle historical] ── downloaded and verified, not yet cleaned or loaded                            │
                                                                                                     ▼
                                                                                  MySQL: india_air_quality
                                                                  dim_city · dim_pollutant · dim_station
                                                                  fact_cpcb_subindex · fact_openaq_concentration
                                                                  fact_weather_observations · fact_weather_forecast
```

---

## 10. Files added or changed

```
sql/create_schema.sql                  schema (DDL)
sql/create_loader_user.template.sql    sanitized user-creation template (committed)
sql/create_loader_user.sql             real user-creation script (git-ignored, contains password)
sql/analysis_queries.sql               7 analytical queries
src/utils/db_connector.py              shared MySQL connection helper
src/loading/load_data_gov_in.py
src/loading/load_openaq.py
src/loading/load_open_meteo.py
src/loading/load_all.py
src/__init__.py, src/utils/__init__.py, src/loading/__init__.py
requirements.txt                       + mysql-connector-python
.gitignore                             + sql/create_loader_user.sql
```

---

## 11. Known limitations

- **Kaggle historical data is not in MySQL.** No cleaning script exists for it yet, so no table or loader was built.
- **Loading is manual.** Ingestion is scheduled; cleaning and loading are not, so the database only reflects the last time they were run.
- **OpenAQ stations are not matched to cities.** `dim_station.city_id` is `NULL` for all of them, so OpenAQ readings cannot be grouped by city. Matching by coordinates is deferred.
- **data.gov.in and OpenAQ values are not comparable.** One is a 0–500 sub-index, the other is µg/m³. Keeping them apart in the schema is intentional.
- **OpenAQ's incidental weather readings are discarded.** They are counted in the loader log but have no table.
- **Small live sample.** Counts above reflect a few snapshots, not a long history.

---

## 12. Next

Candidates for the next phase: clean and load the Kaggle historical dataset so the database has a multi-year baseline; schedule the clean-and-load step the same way ingestion was scheduled in Phase 3; or begin analysis and dashboarding on the data already loaded.
