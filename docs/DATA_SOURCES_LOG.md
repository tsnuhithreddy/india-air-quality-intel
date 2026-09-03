\# Data Sources Log



Tracks when each data source was acquired/first tested, for reproducibility.



\## Live API Sources



| Source | First successful pull | Notes |
|---|---|---|
| data.gov.in CPCB Real-Time AQI | 2026-08-17 | Required custom User-Agent header to avoid silent timeout (see src/ingestion/fetch_data_gov_in.py). Cleaned via src/processing/clean_data_gov_in.py. |
| OpenAQ v3 | 2026-08-25 | Two-step endpoint (/locations + /locations/{id}/latest). Cleaned via src/processing/clean_openaq.py. |
| Open-Meteo | 2026-08-25 | Batched 11 cities single call. Cleaned current + forecast via src/processing/clean_open_meteo.py. |

## Static/Historical Sources

| Source | Downloaded on | Version/notes |
|---|---|---|
| Kaggle "Air Quality Data in India" (2015-2020) | 2026-08-25 | Verified 5 CSV files, 26 cities (Pune missing). Verified via src/ingestion/verify_kaggle_data.py. |



\## Known Source-Specific Quirks

\- data.gov.in silently times out (no error, just hangs) if the request doesn't include a browser-like `User-Agent` header. Fixed permanently in `fetch\_data\_gov\_in.py`.

## OpenAQ v3 API
- **First tested successfully:** 2026-08-25
- **Auth:** `X-API-Key` header (not a URL param) — no browser User-Agent needed, unlike data.gov.in
- **Endpoint pattern:** two calls required, not one:
  - `/v3/locations?iso=IN` — station metadata only, no pollutant values
  - `/v3/locations/{id}/latest` — actual readings, one station per call
- **Rate limiting:** generous but real; script paces requests 1 second apart and
  logs+skips on HTTP 429 rather than crashing
- **Data quality quirk confirmed in testing:** many registered stations return
  0 readings (sensor exists in OpenAQ's system but isn't actively reporting).
  In a 20-station sample, 14/20 had live data, 6/20 had none. This matches the
  station-outage risk already flagged in Phase 1 — must be handled in cleaning
  (drop/flag zero-reading stations, don't treat as valid zero AQI).
- **`locality` field is often blank** for India stations — cannot reliably
  filter by city name; city-matching will need to use lat/lon coordinates
  instead, deferred to the cleaning phase.

## Open-Meteo API
- **First tested successfully:** 2026-08-25
- **Auth:** none required
- **Key trick:** all 11 target cities pulled in ONE request by passing
  comma-separated latitude/longitude lists — response comes back as a JSON
  array in the same order the coordinates were sent, no need to loop or
  pace requests like OpenAQ
- **Params used:** `current` (snapshot), `hourly` (next 24h, via
  `forecast_days=1`), `timezone=auto` (returns local time per city, not
  raw UTC — matters when aligning against CPCB's IST timestamps later)
- **City coordinates are approximate city-center points**, not tied to any
  specific CPCB monitoring station — acceptable for regional weather
  context, noted as a simplification for later reference

## Kaggle — Air Quality Data in India (rohanrao)
- **Downloaded:** 2026-08-25
- **Actual coverage:** 2015-01-01 to 2020-07-01 (corrects Phase 1's stated
  "2015-2024" — see PHASE1_DATA_SOURCE_VALIDATION.md correction)
- **Files:** city_day.csv, city_hour.csv, station_day.csv, station_hour.csv,
  stations.csv
- **city_day.csv:** 29,531 rows x 16 columns (City, Date, 8 pollutants,
  Benzene/Toluene/Xylene, AQI, AQI_Bucket)
- **⚠️ Coverage gap: Pune is NOT included** in this dataset's 26 cities.
  10 of 11 target metros are covered; Pune has no Kaggle historical
  bootstrap and will only accumulate history from live sources starting
  Phase 3 (Aug 2026 onward).
- City name spellings match target list exactly where present
  (e.g. "Bengaluru" not "Bangalore") — no renaming needed for future joins.

## Scheduling — data.gov.in hourly poll
- Task Scheduler task created 2026-08-25, confirmed running hourly and unattended
- Known limitation: task only runs while logged on; if the machine is asleep/off
  at the scheduled hour, that hour's snapshot is skipped (or killed mid-run, as
  observed once on 2026-08-26). Attempted to add "wake computer to run" and
  "restart on failure" as mitigations - both hit Windows/PowerShell Task
  Scheduler bugs and were abandoned as not worth the effort for an hourly-
  redundant dataset.

## Data Type Discovery — data.gov.in sub-index vs. raw concentration
- **Discovered:** 2026-08-26, while building the first cleaning script
- data.gov.in's `min_value`/`max_value`/`avg_value` fields have **no unit
  field at all** in the raw response — unusual for an environmental data feed
- **Reasoning that resolved it:** documented usage of this API computes a
  station's overall AQI as `max(avg_value)` across all its pollutants. That
  operation is only mathematically valid if every pollutant's number is
  already on the same normalized scale — raw CO concentration (often
  thousands, µg/m³) and raw PM2.5 concentration (double/triple digits)
  aren't comparable by simple magnitude otherwise
- **Conclusion:** these values are AQI sub-index scores (0-500
  health-severity scale), NOT raw pollutant concentrations. Corroborated by
  two independent sources describing the same max-across-pollutants
  workflow, not an official CPCB spec document
- **Practical effect:** cleaned output columns renamed `sub_index_min/max/avg`
  (not a generic `value`) so the distinction can't be missed. This source's
  numbers cannot be directly compared, number-for-number, against OpenAQ's
  real µg/m³ readings
- Corrected in PHASE1_DATA_SOURCE_VALIDATION.md and
  PHASE3_INGESTION_EXPANSION_AND_SCHEDULING.md on 2026-08-26

## Security Fix — API key leaking into logs
- **Found:** 2026-08-26
- data.gov.in's API key is sent as a URL parameter, not a header. Python's
  `requests` library includes the full request URL in certain exception
  messages (e.g. timeouts). Logging the raw exception text could write the
  real key into a plaintext log file
- **Fix:** `redact_secrets()` helper added to `secrets_loader.py`, scans any
  string for known key values before logging and replaces them with a
  placeholder. Applied everywhere an exception gets logged, across both
  live-source scripts. Verified with a deliberate test, not just assumed
  to work

## Scheduling — extending automation to OpenAQ and Open-Meteo (AC-power bug)
- **Date:** 2026-08-26
- Same `.bat`-launcher pattern as data.gov.in extended to OpenAQ and
  Open-Meteo, with separate log files per source and staggered trigger times
- **Symptom:** both new tasks showed `Status: Ready`, `Enabled: Yes`, and a
  correctly-advancing `NextRunTime` — every visible signal said healthy —
  but zero new files landed for hours, even while the machine was confirmed
  awake and the original data.gov.in task fired normally in parallel
- **Root cause:** Windows Task Scheduler checks "Start the task only if the
  computer is on AC power" ON by default for every newly created task. The
  original data.gov.in task had this explicitly unchecked early on; the two
  new tasks skipped the Conditions tab and inherited the default
- **Why it was hard to find:** a trigger blocked by an unmet condition
  produces no error and no log entry — Task Scheduler just silently declines
  to launch. Found by comparing `schtasks /query /v` output (which surfaces
  the Power Management field) against the working data.gov.in task's
  equivalent output
- **Fix:** deleted and recreated both tasks with the AC-power condition
  explicitly unchecked. Confirmed resolved by the result code changing from
  "has not run" to a genuine success code, and by real new files landing
  with nobody at the keyboard

## Monitoring — pipeline health-check script
- **Built:** 2026-08-26, `src/monitoring/check_pipeline_health.py`
- Checks, per source: (1) files exist for today, (2) files are non-empty and
  genuinely parse as valid JSON, (3) no gap between snapshots larger than 90
  minutes (a bit more than the 60-min schedule, to tolerate normal jitter
  without false-alarming), (4) no ERROR-level lines in today's log
- Built specifically because the AC-power bug proved that Task Scheduler's
  own "Ready/Enabled" status can be misleading — a real health check needed
  to look at actual file evidence, not just task configuration status

## Cleaning Verification — data.gov.in (clean_data_gov_in.py)
- **First run verified:** 2026-08-26
- Raw JSON standardized to one row per station/pollutant/timestamp: type
  casting (raw values arrive as text), pollutant name standardization
  (`"OZONE"` -> `"O3"`), suspicious-value flagging (negatives, sentinel
  codes like 999)
- **Principle:** flag, don't drop — bad/missing values get boolean flag
  columns instead of deletion
- **Real result:** first run flagged 8.6% of readings. Every flagged row was
  entirely blank (not garbled) — consistent with a station reporting it
  monitors a pollutant but having no valid reading that hour. Confirmed by
  actually checking the flagged rows, not assumed

---

# Phase 4 — Cleaning Expansion (2026-08-27)

## Cleaning Verification — OpenAQ (clean_openaq.py)
- Joins sensor/station metadata from the locations payload onto readings
  from the latest-readings payload; maps `sensor_id` -> standardized
  pollutant name, unit, and coordinates
- Idle/non-reporting stations retained (station name + coordinates kept)
  with `flag_missing=True`, not dropped
- Flags: `flag_negative`, `flag_sentinel`, `flag_missing`, `flag_zero`
  (exactly 0.0 readings — usually an inactive/uncalibrated sensor, not
  genuinely zero pollution), `is_suspicious` (composite)
- **Real verification result:** processed a real unattended snapshot — 150
  records across 20 stations, 4.0% flagged suspicious due to expected idle
  sensors

## Cleaning Verification — Open-Meteo (clean_open_meteo.py)
- Parses two views per run: current weather (1 row/city) and 24-hour hourly
  forecast (24 rows/city, 11 x 24 = 264 rows total)
- Flags: `flag_humidity_invalid` (outside 0-100%), `flag_temperature_extreme`
  (outside -20C to 60C), `flag_wind_negative`, `flag_pressure_invalid`
  (outside 800-1100 hPa), `flag_missing`, `is_suspicious`
- **Real verification result:** successfully parsed 11 city current-weather
  observations and 264 forecast hours with zero physical range violations

## Cross-Source Schema Standardization
- Shared conventions established across all three cleaners: `timestamp_local`
  (IST, +05:30) and `timestamp_utc` where applicable, consistent
  `latitude`/`longitude` naming, and the same flag-don't-drop QA philosophy
  applied identically across sources
- Explicit distinction preserved and documented: data.gov.in's sub-indices
  (0-500 scale) vs. OpenAQ's real physical concentrations (µg/m³) — never
  merged, never treated as directly comparable numbers
- All processed output partitioned by date under
  `data/processed/<source>/<YYYY-MM-DD>/`

---

# Phase 5 — MySQL Database & Loaders (2026-08-29)

**Database created:** `india_air_quality` (MySQL 8.0.44, local instance).
Schema: 3 dimension tables (`dim_city`, `dim_pollutant`, `dim_station`) +
4 fact tables (`fact_cpcb_subindex`, `fact_openaq_concentration`,
`fact_weather_observations`, `fact_weather_forecast`).
Sub-indices (data.gov.in) and concentrations (OpenAQ) kept in physically
separate tables — never merged — per the Phase 3 discovery that they are
not the same kind of number.

**Security:** loader scripts connect as a dedicated `aqi_loader` MySQL
user (SELECT/INSERT/UPDATE only on `india_air_quality`), not root.
Verified by deliberately attempting `DROP TABLE` as this user — correctly
denied (Error 1142). Credentials stored in `.env` alongside existing API
keys; user-creation SQL kept in `sql/create_loader_user.sql`, git-ignored
since it contains a plaintext password.

**Schema fix — `dim_station.city_id` made nullable:** originally
`NOT NULL`. OpenAQ's data does not indicate which target city a station
belongs to (cross-source station matching was already deferred in Phase
1). Rather than guess, `city_id` is left `NULL` for OpenAQ stations —
an honest "unknown" instead of a fabricated relationship.

**Schema fix — `sensor_id` added to `fact_openaq_concentration`:**
present in the real cleaned CSV but missing from the original table
design; added via `ALTER TABLE` before any data was loaded.

**Reference data fix — `NO` and `NOX` added to `dim_pollutant`:**
discovered missing during the first real OpenAQ load; Phase 1's original
pollutant list did not include them.

**Real discovery — OpenAQ mixes weather-sensor readings into the
pollutant field:** some OpenAQ stations report `TEMPERATURE`,
`RELATIVEHUMIDITY`, `WIND_SPEED`, `WIND_DIRECTION` through the same
`pollutant_id` field used for real pollutants. These are deliberately
excluded from `dim_pollutant` / `fact_openaq_concentration` — a wind
reading is not a pollutant concentration, and mixing them in would
defeat the sub-index/concentration separation this schema is built to
protect. No home currently exists for these incidental OpenAQ weather
readings; they are simply dropped (documented, not silent).

**Duplicate-handling rules, decided deliberately per table:**
- `fact_cpcb_subindex`, `fact_openaq_concentration`,
  `fact_weather_observations`: exact duplicate readings are **rejected**
  (kept: whichever was inserted first) — these represent real historical
  snapshots.
- `fact_weather_forecast`: exact duplicate forecasts for the same
  city+hour are **overwritten** with the newest prediction
  (`ON DUPLICATE KEY UPDATE`) — "latest forecast wins," per Phase 4's
  own design note. Verified by loading the same forecast file twice and
  confirming the row count stayed at 264, not 528.

**Note on processed-folder coverage:** as of this phase, only ingestion
scripts are Task-Scheduler-automated — cleaning scripts are still run by
hand. This is why `data/processed/` folders only contain the most recent
manual cleaning run's output per source, while `data/raw/` has every
date. Not a bug; scheduling the cleaning step is future work.

**Verified real load counts (as of 2026-08-29):**
- `fact_cpcb_subindex`: 545 rows (from 2026-08-26 snapshot; 1,455 of
  2,000 nationwide records correctly excluded as out-of-scope cities)
- `fact_openaq_concentration`: 127 rows across 20 distinct stations
  (3 stations idle/non-reporting, correctly produced 0 fact rows each)
- `fact_weather_observations`: 11 rows (one per target city)
- `fact_weather_forecast`: 264 rows (11 cities × 24 hours)

All counts cross-verified against the loader scripts' own logged
summaries and independently via `SELECT COUNT(*)` in MySQL Workbench —
not trusted from script output alone.