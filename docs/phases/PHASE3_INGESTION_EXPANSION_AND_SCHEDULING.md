# Phase 3: Ingestion Expansion and Scheduling

**Project:** India Urban Air Quality Intelligence & Early-Warning System
**Status:** Complete
**Period:** 2026-08-25 to 2026-08-28

## Overview

Phase 2 produced a single working ingestion script for the primary source (data.gov.in). Phase 3 extends that into a multi-source pipeline that runs without manual intervention.

Scope:

1. Add OpenAQ as a backup and cross-validation source.
2. Add Open-Meteo as a weather source.
3. Download and verify the Kaggle historical dataset.
4. Schedule all three live sources to run hourly.
5. Write the first raw-to-processed cleaning script (data.gov.in).
6. Add a health-check script for the scheduled pipeline.

## Why the work is structured this way

The primary source, data.gov.in, only returns the current state of each station. It has no history endpoint. Any historical record for it has to come from this project's own scheduled polling, so reliable unattended scheduling is a requirement rather than a convenience. For history that predates the project, a public dataset (Kaggle) is used as a one-time bootstrap.

## 1. OpenAQ ingestion

Script: `src/ingestion/fetch_openaq.py`

OpenAQ v3 splits station metadata and readings across two endpoints:

| Endpoint | Returns |
|---|---|
| `/v3/locations?iso=IN` | Station metadata only (name, coordinates, sensors). No readings. |
| `/v3/locations/{id}/latest` | Latest readings for one station. |

Getting readings therefore means fetching the station list once, then calling `/latest` per station.

Implementation notes:

- Authentication is an `X-API-Key` header.
- The station list is requested with `limit=300`. OpenAQ reports more than 300 stations for India, so the list is a partial view.
- Readings are fetched for the first 20 stations (`SAMPLE_STATION_COUNT = 20`), with a one-second pause between requests.
- An HTTP 429 or a request failure for one station is logged as a warning and skipped. It does not stop the run.
- Two files are written per run: `openaq_locations_<timestamp>.json` and `openaq_latest_<timestamp>.json`, under `data/raw/openaq/<date>/`.

Observation from testing: of the 20 sampled stations, 14 returned readings and 6 returned none. Those 6 are registered in OpenAQ but were not reporting. This matches the station-outage risk recorded in Phase 1.

## 2. Open-Meteo ingestion

Script: `src/ingestion/fetch_open_meteo.py`

Open-Meteo accepts comma-separated latitude and longitude lists and returns one result per location, in request order. All 11 target cities are fetched in one request, and no API key is needed.

- City coordinates were added to `config/config.py` as `CITY_COORDINATES` (approximate city centres, not tied to monitoring stations).
- Requested variables: current temperature, relative humidity, wind speed and direction, precipitation, surface pressure; hourly temperature, humidity, wind speed and precipitation for the next 24 hours (`forecast_days=1`).
- `timezone=auto` returns each city's local time instead of UTC, which is needed to align with the IST timestamps from CPCB.
- Each result is tagged with its city name by pairing the response list with the request order, so the raw file is self-describing.

Output: `data/raw/open_meteo/<date>/open_meteo_<timestamp>.json`. A returned Delhi temperature series (about 26 to 32 C) was checked against expected August conditions to confirm cities were not mismatched.

## 3. Kaggle historical dataset

Dataset: "Air Quality Data in India" (`rohanrao/air-quality-data-in-india`), downloaded manually and extracted to `data/external/kaggle_air_quality_india/`. Verification script: `src/ingestion/verify_kaggle_data.py`.

Files: `city_day.csv`, `city_hour.csv`, `station_day.csv`, `station_hour.csv`, `stations.csv`.

Findings from verification:

- The first download contained a `train.csv` file, which does not belong to this dataset. It was a wrong download and was replaced from the correct URL.
- Coverage is 2015-01-01 to 2020-07-01. Phase 1 had recorded 2015 to 2024, which was incorrect. `PHASE1_DATA_SOURCE_VALIDATION.md` was corrected.
- `city_day.csv` has 29,531 rows and 16 columns, covering 26 cities.
- Pune is not in the dataset. 10 of the 11 target cities are covered. Pune will only have history from this project's own live polling.
- City spellings match the project's target list, so no renaming is needed for joins.

## 4. Scheduling

All three sources run hourly through Windows Task Scheduler. Task Scheduler was chosen over a Python scheduling library to avoid adding a dependency and to avoid requiring a long-running Python process.

Each source has a launcher in `scripts/`:

```bat
@echo off
cd /d C:\Dev\india-air-quality-intel
"C:\Dev\india-air-quality-intel\venv\Scripts\python.exe" "C:\Dev\india-air-quality-intel\src\ingestion\fetch_<source>.py" >> "C:\Dev\india-air-quality-intel\logs\task_scheduler_<source>.log" 2>&1
```

- The venv's `python.exe` is called directly rather than activating the environment.
- Output, including failures that occur before the script's own logger starts, is redirected to a per-source log file.
- Trigger times are staggered so the three tasks do not start in the same minute.

### Verification of unattended execution

A manual run only shows that the launcher works. Automation was confirmed by finding new, correctly timestamped files in `data/raw/` that appeared without any manual action, roughly an hour apart.

### Issue: tasks created without unchecking the AC-power condition never ran

The data.gov.in task fired normally. The OpenAQ and Open-Meteo tasks did not, although every status field looked correct: `Status: Ready`, trigger enabled, and `NextRunTime` advancing each hour. `LastRunTime` stayed at the placeholder value (`30-11-1999`) and `LastTaskResult` stayed at `267011` (`SCHED_S_TASK_HAS_NOT_RUN`).

Diagnosis:

1. The data.gov.in task fired during the same period, so the machine was awake and the scheduler was running.
2. `schtasks /query /tn "<name>" /v /fo list` showed `Power Management: Stop On Battery Mode, No Start On Batteries` on the failing tasks. The working task showed only `Stop On Battery Mode`.

Cause: Windows enables "Start the task only if the computer is on AC power" by default on new tasks. When the condition is not met, the scheduler does not start the action and records no error. The result is indistinguishable from a task that was never triggered.

Fix: the tasks were deleted and recreated through **Create Task...** with that condition unchecked on the Conditions tab. After that, `LastTaskResult` returned `0` and new files appeared in both raw folders. The condition must be unchecked explicitly on every new task on a laptop.

### Known limitation: runs only while logged on

Tasks are configured as "Run only when user is logged on". If the machine sleeps or the user logs off during a run, the process is terminated (`LastTaskResult 3221225786`, hex `0xC000013A`). This was observed on data.gov.in and, once, on OpenAQ, where a run saved the locations file but was cut off before writing the latest-readings file.

Attempts to add "restart on failure" and "wake the computer to run" failed. The Task Scheduler dialog returned "One or more of the specified arguments are not valid" on save, and `Set-ScheduledTask` returned "The parameter is incorrect". These were not pursued. Because polling is hourly, a missed run means one missing snapshot.

## 5. API key redaction in logs

`fetch_data_gov_in.py` sends the API key as a URL query parameter. When `requests` raises certain exceptions (for example a connection timeout), the exception text includes the full URL, so logging the exception wrote the key into the log file.

Fix: `redact_secrets()` was added to `src/utils/secrets_loader.py`. It replaces any known key value in a string with `***REDACTED***`. It is applied wherever an exception is logged in `fetch_data_gov_in.py` and `fetch_openaq.py`. A later failed request showed `api-key=***REDACTED***` in the log. Log files are excluded from version control via `.gitignore`.

## 6. data.gov.in values are AQI sub-indices

The raw records contain `min_value`, `max_value` and `avg_value` per pollutant, with no unit field.

Evidence that these are CPCB AQI sub-index scores (0 to 500 scale) and not concentrations:

- Documented usage of this API computes a station's AQI as the maximum of `avg_value` across its pollutants. Taking a maximum across pollutants is only meaningful if all values are on the same normalised scale. Raw concentrations of different pollutants are not comparable by magnitude.
- A second independent source describes the same workflow.
- No official CPCB specification page confirming this was found, so this is a reasoned conclusion and not a confirmed fact.

Consequences:

- Cleaned columns are named `sub_index_min`, `sub_index_max` and `sub_index_avg`.
- data.gov.in values cannot be compared directly with OpenAQ concentrations (ug/m3). Doing so would require inverting CPCB's breakpoint formula, which is out of scope for now.
- `PHASE1_DATA_SOURCE_VALIDATION.md` was updated. Its earlier statement that units were inconsistent (ug/m3 versus mg/m3) understated the issue.

## 7. Cleaning script for data.gov.in

Script: `src/processing/clean_data_gov_in.py`. Reads the newest raw JSON and writes `data/processed/data_gov_in/<date>/data_gov_in_clean_<timestamp>.csv`, one row per station, pollutant and timestamp.

Transformations:

- Min, max and avg values are converted from strings to numbers. Unparseable values become `NaN`.
- Pollutant name `OZONE` is mapped to `O3`.
- `last_update` (`DD-MM-YYYY HH:MM:SS`) is parsed to a datetime.

Quality flags (rows are flagged, not dropped): `flag_negative`, `flag_sentinel` (values 999, 9999, -999), `flag_missing`, and the combined `is_suspicious`.

First run on a real snapshot: 2,000 records, 173 flagged (8.6%). Breakdown: 0 negative, 0 sentinel, 173 missing. The flagged rows had no value in any of the three fields, which matches a station listing a pollutant but having no reading for that hour. The raw JSON for a flagged record was not inspected directly at this point.

## 8. Pipeline health check

Script: `src/monitoring/check_pipeline_health.py`. Run on demand. For each source it checks:

1. At least one file exists for the current date.
2. Each file is at least 1,000 bytes and parses as valid JSON.
3. The gap between consecutive snapshots is no more than 90 minutes (the schedule is 60 minutes; the extra margin avoids alerts on normal timing variation).
4. Today's log contains no `ERROR` lines.

The check was added because the AC-power problem showed that task status fields can look correct while nothing runs. It examines files rather than scheduler state.

## Pipeline at the end of Phase 3

```
data.gov.in  --hourly (Task Scheduler)--+
Open-Meteo   --hourly (Task Scheduler)--+--> data/raw (JSON) --> cleaning --> data/processed (CSV) --> MySQL (later phase)
OpenAQ       --hourly (Task Scheduler)--+        (data.gov.in cleaner done)
Kaggle       --one-time download, verified

check_pipeline_health.py: on-demand verification of raw files and logs
```

## Files added or changed

| File | Change |
|---|---|
| `config/config.py` | Added `CITY_COORDINATES` |
| `src/utils/secrets_loader.py` | Added `redact_secrets()` |
| `src/ingestion/fetch_data_gov_in.py` | Redacted exception logging |
| `src/ingestion/fetch_openaq.py` | New |
| `src/ingestion/fetch_open_meteo.py` | New |
| `src/ingestion/verify_kaggle_data.py` | New |
| `src/processing/clean_data_gov_in.py` | New |
| `src/monitoring/check_pipeline_health.py` | New |
| `scripts/run_data_gov_in.bat`, `run_openaq.bat`, `run_open_meteo.bat` | New |
| `docs/DATA_SOURCES_LOG.md` | Entries for OpenAQ, Open-Meteo, Kaggle, scheduling, redaction |
| `PHASE1_DATA_SOURCE_VALIDATION.md` | Corrected Kaggle coverage and the sub-index finding |

## Known limitations at the end of this phase

- data.gov.in has no historical endpoint. History starts from the first scheduled run (August 2026).
- OpenAQ readings are collected for a fixed sample of 20 stations; some are registered but not reporting.
- Kaggle data ends 2020-07-01 and does not include Pune.
- Scheduled tasks only run while the user is logged on. Runs interrupted by sleep or logoff are lost.
- Only data.gov.in has a cleaning script. OpenAQ and Open-Meteo raw files are being collected but not yet processed.
- data.gov.in sub-index values and OpenAQ concentrations are different quantities and are not directly comparable.
