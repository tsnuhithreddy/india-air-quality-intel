# Phase 12: Loader Automation, Dashboard Page 5 and Pipeline Incident

**Project:** India Urban Air Quality Intelligence & Early-Warning System
**Status:** Complete, with open items listed at the end
**Period:** 2026-09-20 to 2026-10-10

## Contents

- [Part A: Loader automation](#part-a-loader-automation)
- [Part B: Dashboard completion, pipeline incident and housekeeping](#part-b-dashboard-completion-pipeline-incident-and-housekeeping)
- [Files added or changed](#files-added-or-changed)
- [Limitations](#limitations)
- [Open items](#open-items)

---

# Part A: Loader automation

## A1. Overview

Ingestion of the three live sources (data.gov.in, OpenAQ, Open-Meteo) has been scheduled since Phase 3. Cleaning and loading into MySQL had remained a manual step since Phase 5. This part adds a single script that carries the newest raw file of each source through cleaning and loading, and registers it as an hourly scheduled task.

## A2. Motivation

A check of the Power BI dashboard showed the "Hours Since Last Update" measure at 595 hours (about 25 days). Task Scheduler status and raw file timestamps showed that all three ingestion tasks had been running throughout. The cause was the manual cleaning and loading step, which had not been run for several weeks. Ingestion was working, but its output was not reaching MySQL.

## A3. Design: `src/loading/run_clean_and_load.py`

For each source the script runs: newest raw JSON, clean, write processed CSV, load into MySQL.

Run from the project root:

```
python -m src.loading.run_clean_and_load
```

Design decisions:

**Existing functions are reused unchanged.** The script imports the cleaning functions from `clean_data_gov_in`, `clean_openaq` and `clean_open_meteo`, and each source's `load_file` from the loader modules. It contains no cleaning or loading logic of its own, so the only new code is orchestration.

**Only the newest raw file is processed.** Each run takes the newest raw file per source, as the cleaners' own `__main__` blocks do, and loads exactly the CSV path the cleaner returns. There is no date argument, so a run that starts just before midnight cannot look in the wrong date folder. For OpenAQ the newest `openaq_latest_*.json` is used; for Open-Meteo the current-conditions CSV is loaded first, then the forecast CSV.

**Each source is isolated.** Each source runs in its own `try/except`. `SystemExit` is caught as well as `Exception`, because a loader that calls `sys.exit()` would otherwise end the whole process and skip the sources after it. A failure is recorded and the remaining sources still run.

**A stale raw file is a failure.** Before processing, the script checks the age of the newest raw file against `STALE_RAW_HOURS = 3`. If the file is older, an `ERROR` is logged and the source is added to the failure list, even if cleaning and loading succeed. A run that succeeds on old input does not show that the pipeline is healthy. The threshold is three hours because ingestion is hourly and occasional late or missed runs are expected.

**Exit codes are propagated.** `main()` returns 0 only if no source failed and no raw file was stale, otherwise 1. The launcher ends with `exit /b %ERRORLEVEL%`, so Task Scheduler's `LastTaskResult` reflects the script's result.

`config/` is inserted first on `sys.path` so that `import config` resolves to `config/config.py` and not to the `config` directory, which Python can treat as a namespace package when the project root is on the path.

### Launcher: `scripts/run_clean_and_load.bat`

```bat
@echo off
cd /d C:\Dev\india-air-quality-intel
set PYTHONUTF8=1
"C:\Dev\india-air-quality-intel\venv\Scripts\python.exe" -m src.loading.run_clean_and_load >> "C:\Dev\india-air-quality-intel\logs\task_scheduler_clean_and_load.log" 2>&1
exit /b %ERRORLEVEL%
```

## A4. Task Scheduler registration

Task name: `AQI - clean and load hourly`.

1. Task Scheduler, then **Create Task...** (not Create Basic Task).
2. General: set the name.
3. Triggers: New, Daily, repeat every 1 hour, duration Indefinitely. Start a few minutes after the ingestion tasks so the newest raw files have already landed.
4. Actions: Start a program, `C:\Dev\india-air-quality-intel\scripts\run_clean_and_load.bat`.
5. Conditions: uncheck **Start the task only if the computer is on AC power**. This is enabled by default on new tasks and prevents the task from starting on battery without reporting an error (see Phase 3).
6. Save.

## A5. Verification

### Log

`logs/task_scheduler_clean_and_load.log` records, for each source, the age of the newest raw file, the cleaning counts and the loader summary. Excerpt from a run:

```
=== clean + load run starting ===
[data_gov_in] newest raw file is 2.1h old: data_gov_in_20260921_1420.json
Done. inserted=0, skipped_duplicate=514, skipped_unknown_city=1486, skipped_unknown_pollutant=0
[openaq] newest raw file is 2.1h old: openaq_latest_20260921_1421.json
Done. inserted=0, skipped_duplicate=127, skipped_idle_station=3, skipped_unknown_pollutant=20
[open_meteo] newest raw file is 2.0h old: open_meteo_20260921_1431.json
=== run finished OK ===
```

`inserted=0` does not by itself indicate a fault. The counts are checked by adding them up: 514 + 1486 = 2000 rows for data.gov.in, and 127 + 3 + 20 = 150 rows for OpenAQ. Every row is accounted for as either a duplicate of an already-loaded reading or a documented exclusion (a city outside the target set, an idle station, or OpenAQ weather readings delivered through the pollutant field).

### Database freshness

Run against the `india_air_quality` database:

```sql
USE india_air_quality;
SELECT 'fact_cpcb_subindex' AS tbl, MAX(timestamp_local) AS max_ts, COUNT(*) AS n FROM fact_cpcb_subindex
UNION ALL SELECT 'fact_openaq_concentration', MAX(timestamp_local), COUNT(*) FROM fact_openaq_concentration
UNION ALL SELECT 'fact_weather_observations', MAX(timestamp_local), COUNT(*) FROM fact_weather_observations
UNION ALL SELECT 'fact_weather_forecast', MAX(forecast_timestamp_local), COUNT(*) FROM fact_weather_forecast;
```

Results at two points:

| Table | 2026-09-21 | | 2026-09-22 | |
|---|---|---|---|---|
| | Max timestamp | Rows | Max timestamp | Rows |
| `fact_cpcb_subindex` | 2026-09-21 13:00 | 2,110 | 2026-09-22 09:00 | 2,665 |
| `fact_openaq_concentration` | 2026-09-17 20:00 | 167 | 2026-09-21 21:00 | 207 |
| `fact_weather_observations` | 2026-09-21 14:30 | 44 | 2026-09-22 15:00 | 77 |
| `fact_weather_forecast` | 2026-09-21 23:00 | 792 | 2026-09-22 23:00 | 1,056 |

`fact_weather_forecast` holds future forecast hours, so its maximum timestamp is later than the load time.

### Unattended execution

Two `Get-ScheduledTaskInfo` checks both reported `NextRunTime` as 15:38:21 on 2026-09-22. The log then showed a complete run at 15:38:34, which was not started manually.

## A6. Issues found during verification

### Stale ingestion detected on 2026-09-22

The 15:38 run ended with:

```
=== run finished WITH FAILURES: data_gov_in (stale raw input); openaq (stale raw input) ===
```

The raw folders showed data.gov.in files at 09:52, 09:56 and 09:59 and none after, and OpenAQ files at 10:11 and 10:12 plus a locations-only file at 13:11. `LastTaskResult` for both ingestion tasks was `3221225786` (`0xC000013A`, process terminated externally). Open-Meteo was current and its data loaded (11 observation rows and 264 forecast rows inserted).

The pattern is consistent with the machine being asleep or logged off, which is the known limitation recorded in Phase 3. The sleep or logoff itself was not confirmed from system logs. The stale-input check reported the gap as designed.

### Log encoding

Warnings containing an em dash (for example `Unknown pollutant 'WIND_SPEED' - skipping row`) appeared as `'WIND_SPEED' ? skipping row` in the redirected log. When Python runs under Task Scheduler with no console, it uses the system's legacy code page for standard output. Adding `set PYTHONUTF8=1` to the launcher fixed this; later log output showed the dash correctly. No cleaning or loading code was changed.

### Query run against the wrong database

A freshness query returned zero rows for all four fact tables a few minutes after the log had reported 275 rows inserted. Because the two results contradicted each other, the connection was checked rather than the pipeline. `SELECT DATABASE()` showed the session was not using `india_air_quality`. After `USE india_air_quality;` the query returned the figures in the table above. This is the same kind of problem as the database-name mismatch in Phase 8.

### OpenAQ staleness: revised conclusion

On 2026-09-21 `fact_openaq_concentration` had a maximum timestamp of 2026-09-17 20:00, even though the newest raw OpenAQ file was only about two hours old and loading it produced 127 duplicates and no inserts. That was first read as the 20-station sample having stopped reporting.

A later check showed the maximum timestamp had advanced to 2026-09-21 21:00 (40 new rows), so the sample reports intermittently and had not stopped. The staleness seen on 2026-09-22 coincides with the ingestion gap described above. The earlier conclusion was too strong. No change to `SAMPLE_STATION_COUNT` is planned. Freshness will continue to be monitored through the existing checks.

---

# Part B: Dashboard completion, pipeline incident and housekeeping

Part B covers the remaining Phase 12 work: a fifth Power BI page for the early-warning results, fixes to the existing pages, a two-week interruption of the live pipeline, and cleanup of the SQL files and repository.

## B1. Power BI Page 5: Early Warning & Model Governance

### Data and relationships

Two tables were imported into the existing model: `fact_early_warnings` (2,115 rows, Phase 11) and `fact_kaggle_anomaly_flags` (74,826 rows, Phase 9).

| From | To | Cardinality | Filter direction |
|---|---|---|---|
| `fact_early_warnings[city_id]` | `dim_city[city_id]` | Many-to-one | Single |
| `fact_early_warnings[target_date]` | `DateTable[Date]` | Many-to-one | Single |
| `fact_kaggle_anomaly_flags[station_id]` | `dim_station[station_id]` | Many-to-one | Single |

- `target_date` is the active date relationship, since the page describes when a warning applies and not when it was issued. `reading_date` is not related to `DateTable`. A second, inactive relationship can be added later with `USERELATIONSHIP` if issue-date views are needed.
- `fact_kaggle_anomaly_flags[month]` is not related to `DateTable`. It is the pooled calendar-month key from the Phase 9 baseline (months 1 to 12 across all years), not a date.
- No Page 5 visual uses `fact_kaggle_anomaly_flags`.

### Page contents

| Element | Purpose |
|---|---|
| Banner | States that the page is a retrospective view of the Jan to Jul 2020 test window, not a live feed |
| KPI cards | Triggered warnings, new episodes (onsets), continuing days |
| Reliability donut | Triggered warnings by reliability tier |
| Episode chart | New episodes and continuing days by city |
| Warning grid | Triggered warnings only, coloured by reliability tier, newest first |
| Governance table | Model used per city and Phase 10 Alert-tier recall |
| Horizon slicer | 1-day / 3-day tiles, default 1-day |

The page reuses the existing synced `city_name` slicer. The horizon slicer is new.

### Measures

```dax
EW Triggered Days =
CALCULATE(COUNTROWS(fact_early_warnings), fact_early_warnings[triggered] = TRUE())

EW New Episodes =
CALCULATE(COUNTROWS(fact_early_warnings),
    fact_early_warnings[triggered] = TRUE(),
    fact_early_warnings[is_new_episode] = TRUE())

EW Continuing Days =
CALCULATE(COUNTROWS(fact_early_warnings),
    fact_early_warnings[triggered] = TRUE(),
    fact_early_warnings[is_new_episode] = FALSE())

Warning Reliability Color =
VAR t = SELECTEDVALUE(fact_early_warnings[reliability_tier])
RETURN SWITCH(TRUE(),
    t = "reliable",         "#2E7D32",
    t = "known_unreliable", "#F9A825",
    t = "unvalidated",      "#9E9E9E",
    "#FFFFFF")

Reliability Tier Display =
VAR t = SELECTEDVALUE(fact_early_warnings[reliability_tier])
RETURN SWITCH(TRUE(),
    t = "reliable",         "Reliable",
    t = "known_unreliable", "Known Unreliable — Review",
    t = "unvalidated",      "Unvalidated — No Severe History",
    BLANK())
```

Also added: `EW Reliable Triggered`, `EW Known Unreliable Triggered` and `EW Unvalidated Triggered`, which count triggered rows per tier for the donut, and a `Horizon Label` calculated column (`1-day` / `3-day`).

### Design decisions

- **Three reliability colours.** Green is reliable (Patna). Amber is known unreliable (Delhi, Lucknow), meaning recall was measured and found weak. Grey is unvalidated (Bengaluru, Chennai, Hyderabad, Mumbai), meaning no severe days occurred in the test window, so recall could not be measured. These are different kinds of uncertainty and are not merged into one colour.
- **NULL handling.** Six rows have a NULL `warning_label` (a known Mumbai 3-day gap). The grid shows the raw column, and the tier text falls through to `BLANK()`. No branch returns a default label, which avoids the NULL-to-default errors found in Phase 7 and Phase 11.
- **Governance table is static.** It is a manually entered table (`Model Governance Reference`) holding the Phase 10 results. Recomputing Alert-tier recall in DAX would duplicate logic that had already produced two default-case defects. A caption on the page states that the figures are Phase 10 results and not live calculations.
- **Visuals already present elsewhere were not repeated.** The existing Alerts page (live data.gov.in threshold alerts) is separate from this page (forecast-based warnings), and the two are titled differently.

### Verification against Phase 11

With the horizon slicer set to 1-day:

| Check | Phase 11 | Page 5 |
|---|---|---|
| Triggered | 26 + 11 + 38 = 75 | 75 |
| New episodes | 9 + 6 + 6 = 21 | 21 |
| Continuing days | 17 + 5 + 32 = 54 | 54 |
| Reliable / known unreliable | 38 / 37 | 38 / 37 |
| Patna onsets / continuing | 6 / 32 | 6 / 32 |
| Delhi onsets / continuing | 9 / 17 | 9 / 17 |
| Lucknow onsets / continuing | 6 / 5 | 6 / 5 |

With the slicer cleared, the page shows 144 triggered, 34 new episodes and 110 continuing days, matching Phase 11. Exact agreement also indicates the relationships are not producing duplicate matches. Before a default horizon was set, all visuals showed both horizons combined.

## B2. Changes to the existing pages

| Page | Change |
|---|---|
| Overview | `Cities Monitored` changed from `DISTINCTCOUNT` to `DISTINCTCOUNTNOBLANK` on `dim_station[city_id]`. It showed 12 because a NULL `city_id` (OpenAQ stations) was counted as a value, and now shows 11. |
| Overview | Added a data-quality note: Ahmedabad's average comes from one station (Maninagar, GPCB, `GJ001`) with values above the 0-500 scale. The note is a text box and does not link to the Data Quality page. |
| Live Snapshot | Removed the subtitle on the sub-index / wind chart. It said the two sources had no overlapping dates because of manual loading, which no longer held after Part A. |
| Live Snapshot | Limited the same chart to a recent date window, since it gained a bar per day without bound. |

`Hours Since Last Update` is unchanged. It is based on `Latest Data Timestamp = MAX(fact_cpcb_subindex[timestamp_local])`, so it measures data.gov.in only and does not reflect OpenAQ or Open-Meteo freshness. Per-source freshness measures have not been built.

The navigation button label `Early Warning&Model Governance` has no spaces around the ampersand and wraps onto two lines.

## B3. Pipeline incident, 2026-09-25 to 2026-10-09

The `Hours Since Last Update` card rose from 24 to 279 hours over about two weeks. Four separate problems contributed. The full record is in `docs/DATA_SOURCES_LOG.md`.

### B3.1 Task Scheduler configuration (resolved)

The three ingestion tasks were set to "Run only when user is logged on". `LastTaskResult` was `0x800710E0` (not logged on) for the ingestion tasks and `0xC000013A` for the clean-and-load task. Changing a task to "Run whether user is logged on or not" failed with "One or more of the specified arguments are not valid."

Not effective: setting "Configure for" to Windows 10. A blank account password was also ruled out.

Resolution:

1. A local Windows account named `aqi_loader` was created and the tasks were set to run as that account. Windows then reported that the account needed the "Log on as a batch job" right.
2. The environment is Windows Home. `secpol.msc` is not installed, and the "Backup Operators" group does not exist (`net localgroup` error 1376).
3. The account was changed to an Administrator, which holds the right by default. After that the tasks saved and `LastTaskResult` returned to `0x0`.

Notes:

- The Windows account `aqi_loader` and the MySQL user `aqi_loader` are unrelated and share a name only.
- The Windows account being an Administrator is broader than the task requires. It is a local account on a single-user machine running the project's own scripts.
- The clean-and-load task reports `0x1` while any source is stale. This follows from the exit-code design in A3 and is not a separate fault.

### B3.2 data.gov.in API unreachable (ongoing, external)

The last successful raw file is `data_gov_in_20260925_0952.json`.

Connectivity checks from the host:

| Target | Result |
|---|---|
| `api.data.gov.in:443` (164.100.61.198) | TCP connect and ping failed |
| `www.data.gov.in:443` | Connected |
| `cpcb.nic.in:443` | Connected |

The Windows proxy settings were off and no outbound firewall rule blocked the host. This limits the fault to the API host.

The error returned by `fetch_data_gov_in.py` changed over time:

| Date | Error |
|---|---|
| 2026-09-25 to 2026-10-05 | Connection refused (`WinError 10061`) |
| 2026-10-06 00:09 | DNS resolution failure (same second as an Open-Meteo failure; OpenAQ succeeded 14 minutes later) |
| 2026-10-06 01:47 | `502 Bad Gateway` |
| 2026-10-06 06:27 | Read timeout (30 s) |
| 2026-10-07 and 2026-10-09 | Connection refused |

A connection-level failure occurs before the API key is evaluated, so it is not caused by credentials. The pattern is consistent with an unstable server. The endpoint was still failing on 2026-10-09 at 11:57. Whether the API endpoint or key policy has changed has not been checked.

### B3.3 All-source gap on 2026-10-08 to 2026-10-09 (cause identified)

At 11:45 on 2026-10-09 the stale-input check flagged all three sources. The newest OpenAQ and Open-Meteo raw files dated from about 23:10 on 2026-10-08, a gap of 12.6 hours.

The Kernel-Power events for 2026-10-08 showed only sleep intervals of 2 to 3 seconds, which does not explain the gap. A System log query for shutdown events returned event 1074 at 23:20:23 on 2026-10-08, showing that Explorer.EXE initiated a power-off for the user account. The machine was shut down until the next day.

Task Scheduler history is disabled, so the scheduler log held no entries for the window.

### B3.4 OpenAQ sample inactive (source side, not confirmed)

`fact_openaq_concentration` held 359 rows with a maximum timestamp of 2026-10-02 14:00 on 2026-10-07, and 399 rows with a maximum of 2026-10-07 20:00 after the next load. Since then the loader has run against fresh raw files and inserted nothing (`inserted=0, skipped_duplicate=127`), because the 20 sampled stations have reported nothing newer. The processed file's newest rows were stamped 2026-10-07 20:00.

The loader and its duplicate check are working. The likely cause is that OpenAQ's India data is relayed from CPCB, which is consistent with the data.gov.in outage, but this has not been verified.

### B3.5 `.env` duplicate keys

| Variable | Finding | Action |
|---|---|---|
| `DATA_GOV_IN_API_KEY` | Defined twice with the same value | Removed the duplicate. No functional effect. |
| `MYSQL_USER`, `MYSQL_PASSWORD` | Defined twice, once for `root` and once for `aqi_loader` | Removed the `root` pair |

`python-dotenv` uses the last occurrence of a repeated key. The loaders were connecting as `aqi_loader` only because that block appeared second. Reordering the file would have switched every loader to `root` without an error and removed the least-privilege restriction from Phase 5. This is the same fault found in Phase 8 for the MySQL variables.

### B3.6 Verification after the changes

`python -m src.loading.run_clean_and_load` was run on 2026-10-09 at 12:18 after the `.env` edit. All three sources loaded without database errors. Open-Meteo inserted 11 current-weather rows and overwrote 264 forecast rows, and the OpenAQ and Open-Meteo raw files were under an hour old. The run summary listed only data.gov.in as failed (stale raw input).

Freshness at that point:

| Table | Max timestamp | Rows |
|---|---|---|
| `fact_cpcb_subindex` | 2026-09-25 09:00 | 7,512 |
| `fact_openaq_concentration` | 2026-10-07 20:00 | 399 |
| `fact_weather_observations` | current | 770 (759 before the run, +11) |
| `fact_weather_forecast` | current | 5,016 (overwritten, not appended) |

The row increase of 11 shows the duplicate constraints are intact. OpenAQ logs `skipped_unknown_pollutant=20` on every run. These are the weather readings OpenAQ delivers through the pollutant field, excluded since Phase 5.

Log output continued to show the data.gov.in API key as `***REDACTED***`.

## B4. SQL and repository housekeeping

### `sql/create_schema.sql`

The file already contained `fact_kaggle_anomaly_flags` and `fact_early_warnings`, taken from `SHOW CREATE TABLE` output. Changes made:

- `dim_station.city_id` changed from `NOT NULL` to `NULL`, matching the live schema. The old definition would have failed on the first OpenAQ station.
- The `ALTER TABLE` statements (OpenAQ `sensor_id`, `source_system` widening) folded into the `CREATE TABLE` statements, so the file reads top to bottom.
- Pollutant seed inserts merged into one statement in the live order (14 codes).
- Comments rewritten, and a header added stating the file is for an empty database and is not re-runnable.

The two derived tables were checked against `SHOW CREATE TABLE` output for the live database. The older tables were carried over from the previous file. A rebuild comparison against the live schema has not been run (see open items).

Live table counts confirmed through `INFORMATION_SCHEMA`: 3 `dim_` tables and 8 `fact_` tables.

### `sql/analysis.sql`

Comments shortened, leading tabs and a duplicate `USE` removed, a typo in a column alias corrected, and the trailing queries labelled (rows loaded per day, and a freshness check across the four live tables).

### Files removed and files checked

- Deleted untracked scratch files: `scratch_agg.py`, `scratch_verify.py`, `test.py` and `sql/sql file.sql`. A search of the three scripts found no hardcoded credentials. They read secrets from the environment, and none had been committed.
- `sql/create_loader_user.sql` contains a real password. `git check-ignore` confirmed it is covered by `.gitignore` (line 32), `git ls-files` does not list it, and `git log` shows it has never been committed.
- `git ls-files sql` lists only `analysis.sql` and `create_schema.sql`.

### Documentation

- `docs/DATA_SOURCES_LOG.md`: incident entry added (114 lines, no deletions). A search of the file for password, key and token terms returned descriptions only, with no values.
- `docs/EXECUTIVE_INSIGHTS_REPORT.md`: summary of findings across the project for readers who will not read the phase documents.

---

# Files added or changed

| File | Change |
|---|---|
| `src/loading/run_clean_and_load.py` | New (Part A) |
| `scripts/run_clean_and_load.bat` | New (Part A) |
| `dashboard/India Urban Air Quality Intelligence & Early-Warning System.pbix` | Page 5 added, fixes applied (Part B) |
| `sql/create_schema.sql` | Synced with live schema |
| `sql/analysis.sql` | Comments and queries tidied |
| `docs/DATA_SOURCES_LOG.md` | Staleness and OpenAQ findings (Part A), pipeline incident (Part B) |
| `docs/EXECUTIVE_INSIGHTS_REPORT.md` | New |
| `PROJECT_STATE.md` | To be updated at the end of the phase |

# Limitations

- Only the newest raw file per source is processed on each run. Raw snapshots from before the automation, and any hour missed by ingestion, are not backfilled.
- Polling and loading run only while the host is powered on and awake. Tasks now run whether or not a user is logged on (B3.1), but a shutdown or sleep still interrupts them, and interrupted runs are lost.
- Nothing is sent when a run fails. Failures are visible in the log, in the exit code and in Task Scheduler's last result.
- A rerun against an already-loaded raw file inserts nothing. This is safe because of the duplicate constraints, but the log distinguishes it from a source that has stopped updating only through the three-hour stale-input check.
- `Hours Since Last Update` measures data.gov.in only.
- Page 5 is a retrospective view of the 2020 test window. It is not connected to live data.
- Task Scheduler history is disabled, so gaps in scheduled runs are not recorded by the scheduler.
- The Windows account used by the scheduled tasks is an Administrator.

# Open items

| Item | Status |
|---|---|
| data.gov.in API | Unreachable as of 2026-10-09. The hourly task retries and will resume when the host responds. |
| OpenAQ sample | No readings newer than 2026-10-07 20:00. Cause not confirmed. |
| `.pbix` commit and PDF export | Waiting for data.gov.in to recover so the dashboard is refreshed first. |
| `create_schema.sql` rebuild check | Build the file into an empty database and compare columns with the live schema. Not yet run. |
| `create_loader_user.template.sql` | Optional public template with a placeholder password. Not yet created. |
| Task Scheduler history | Enable, so future gaps leave a record. |
| Windows Update active hours | Set, but not confirmed as saved. |
| Per-source freshness measures | Not built. |
| Navigation button label | Add spaces around the ampersand. |
| `PROJECT_STATE.md` | Update at the end of the phase, including the schema file now holding both derived tables and the incident summary. |
