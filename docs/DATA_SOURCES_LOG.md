# Data Sources Log

Tracks when each data source was acquired/first tested, for reproducibility.

## Live API Sources

| Source | First successful pull | Notes |
|---|---|---|
| data.gov.in CPCB Real-Time AQI | 2026-08-17 | Required custom User-Agent header to avoid silent timeout (see src/ingestion/fetch_data_gov_in.py). Cleaned via src/processing/clean_data_gov_in.py. |
| OpenAQ v3 | 2026-08-25 | Two-step endpoint (/locations + /locations/{id}/latest). Cleaned via src/processing/clean_openaq.py. |
| Open-Meteo | 2026-08-25 | Batched 11 cities single call. Cleaned current + forecast via src/processing/clean_open_meteo.py. |

## Static/Historical Sources

| Source | Downloaded on | Version/notes |
|---|---|---|
| Kaggle "Air Quality Data in India" (2015-2020) | 2026-08-25 | Verified 5 CSV files, 26 cities (Pune missing). Verified via src/ingestion/verify_kaggle_data.py. |

## Known Source-Specific Quirks

- data.gov.in silently times out (no error, just hangs) if the request doesn't include a browser-like `User-Agent` header. Fixed permanently in `fetch_data_gov_in.py`.

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
- **Refined during Phase 6:** Pune's absence is more precise than "not
  included" — Pune actually IS listed once in `stations.csv` (station
  metadata exists), but that single station has zero rows in
  `station_day.csv`. Same practical gap, more precisely understood root
  cause.
- **Refined during Phase 6:** used `station_day.csv` + `stations.csv`
  only, not all 5 files — station-level (not city-aggregated) to match
  the rest of the project's schema, daily (not hourly) since this
  dataset's role is a historical trend baseline, not a second live feed.
- **Discovered during Phase 6:** 3 real pollutants — Benzene, Toluene,
  Xylene (VOCs) — appear in this dataset's columns but were never
  reported by data.gov.in or OpenAQ, so had never been tracked before.
  Added to `dim_pollutant` rather than dropped, since they're genuinely
  real pollution data.
- **Discovered during Phase 6:** this dataset appears to have already
  been cleaned by its original curator, unlike the live government/OpenAQ
  feeds. Verified rather than assumed — 0% of 1.14M cleaned rows flagged
  suspicious was investigated (checked real min/max values and how often
  the suspicious round number 1000 appeared — exactly once, consistent
  with a genuine pollution spike, not an artificial data cap) before
  being trusted.
- **Discovered during Phase 7 (dashboard build), re-confirmed independently
  in Phase 8:** one station — Maninagar, Ahmedabad - GPCB (source key
  `GJ001`) — has internally inconsistent precomputed AQI values (avg
  683.79, max 2049 on a defined 0-500 scale) that don't reconcile against
  its own underlying pollutant concentrations. Treated as a likely
  data-quality artifact in the original Kaggle source, not confirmed
  extreme pollution. Excluded entirely from Phase 9's anomaly baseline
  and Phase 10's forecasting panel, since Ahmedabad has only this one
  Kaggle station.
- **Discovered during Phase 8:** Mumbai's sole "stable panel" station
  reports a row on schedule every day for 2015-2017, but 100% of those
  rows are blank — a different failure mode from Ahmedabad's (real-but-
  invalid values vs. no usable data at all). Real, usable Mumbai history
  only begins in 2018.
- **Discovered during Phase 8:** station coverage grew substantially
  over 2015-2020 (most sharply 2018-2019), most visibly in Delhi (10
  stations in 2015 -> 38 from 2018 onward). A naive city-level yearly
  average partly reflects which parts of a city were being monitored
  that year, not purely how pollution changed.
- **Refined during Phase 10:** Lucknow's documented "March-May 2018"
  data-quality gap is actually 2018-02-15 to 2018-06-12 (118 days) — the
  real gap starts 6.5 weeks earlier and ends ~2 weeks later than
  originally labeled. Confirmed as one clean contiguous block, verified
  directly against the database rather than trusting the earlier label.

## Scheduling — data.gov.in hourly poll
- Task Scheduler task created 2026-08-25, confirmed running hourly and unattended
- Known limitation (superseded on 2026-10-25, see the Sept-Oct 2026 incident below):
  task only runs while logged on; if the machine is asleep/off
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

## Standalone SQL Analysis Layer (Phase 5, alongside the loaders)

**Why this was built:** loading data into MySQL isn't the same as being
able to answer real questions with it. Once the three live-source
loaders were working and verified, a committed set of analytical
queries was written directly against the schema — not just the one-off
`SELECT COUNT(*)` checks used to verify the loaders.

**`sql/analysis.sql`** — 7 committed, commented queries (two operational
queries were added later, in Phase 12) covering
aggregation, multi-table joins, window functions (`RANK()`, a rolling
3-hour temperature average), correlated and non-correlated subqueries,
and a `UNION ALL` combining both live pollution sources into one
cross-source data-quality view. Each query's comment states the real
question it answers.

**A real bug hit and fixed while writing this file:** a station-level
"reads worse than its own city's average" query (correlated subquery)
initially failed with `Error 1054: Unknown column
'india_air_quality.s.city_id'`, due to MySQL's `ONLY_FULL_GROUP_BY`
mode — the correlated subquery referenced `s.city_id`, which wasn't
listed in the outer query's `GROUP BY`. Fixed by adding it to the
`GROUP BY` list.

**A second, later bug found and fixed (post-Phase-11 housekeeping):**
the query comparing live pollution against live weather originally
joined only on `city_id`, with no time alignment at all. This worked
by accident while `fact_weather_observations` still had just one row
per city, but would have silently become a cross join (every pollution
reading paired with every weather row ever recorded for that city) as
soon as more hourly weather data accumulated. Fixed to match on the
same real hour on both sides, not just the same city.

**Scope note:** at this point in the project, only the four live-source
fact tables exist (`fact_cpcb_subindex`, `fact_openaq_concentration`,
`fact_weather_observations`, `fact_weather_forecast`) — Kaggle's
historical data has not been loaded into MySQL yet (that's Phase 6), so
none of these queries reference it.

---

# Post-Phase-11 Operational Finding — Pipeline Staleness Incident

**Found:** during a Phase 12 planning review, ~2026-09-20
**Symptom:** the Power BI dashboard's "Hours Since Last Update" KPI
(Overview page) read 595 hours (~25 days) stale.
**Diagnosis, checked rather than assumed:** confirmed via Task
Scheduler status and real raw-file timestamps that all 3 ingestion
tasks (data.gov.in, OpenAQ, Open-Meteo) had continued running
automatically and correctly the entire time — the same automation
proven working since Phase 3 had not broken. The actual break was in
the cleaning + MySQL-loading step, which has been manual since Phase 5
and simply hadn't been run by hand in several weeks.
**Fix:** re-ran the three cleaning scripts and reloaded into MySQL by
hand. Verified via `SELECT MAX(timestamp_local)` returning current
timestamps across `fact_cpcb_subindex`, `fact_openaq_concentration`,
and `fact_weather_observations`, and a refreshed dashboard KPI —
not just assumed fixed because the scripts ran without error.
**Why this matters going forward:** this is the concrete, lived proof
that the ingestion/loading automation gap — open since Phase 5,
repeatedly deferred through Phases 7-11 as a "nice to have" — is a
real, recurring operational risk, not a theoretical one. It directly
motivated making loader automation an actual Phase 12 deliverable
rather than deferring it again.

#Phase 12.1- loader automation

## OpenAQ 20-station sample - staleness, corrected assessment (2026-09-22)
Initial check (2026-09-21) showed fact_openaq_concentration stuck at
2026-09-17 - looked like a permanently dead sample. Re-checked 2026-09-22:
table had advanced to 2026-09-21 21:00 (+40 rows), showing the sample was
still receiving occasional new readings, not permanently stalled. The
subsequent staleness observed today is fully explained by a ~6h ingestion
gap (machine asleep/logged off) affecting data.gov.in identically in the
same window - not a distinct OpenAQ-specific issue. Revising earlier
conclusion: no separate action needed on SAMPLE_STATION_COUNT for now;
continue monitoring via run_clean_and_load.py's freshness checks.

# Incident: live pipeline stale, Sept 25 to Oct 26, 2026

Written 2026-10-09 and updated 2026-10-26. Several separate problems
overlapped and looked like one. Phase 12 (docs/phases/PHASE12_LOADER_AUTOMATION.md)
has the summary.

## How it was noticed
The "Hours Since Last Update" KPI on the dashboard's Overview page kept
climbing (24 -> 29 -> 154 -> 279 over about two weeks). It only tracks
data.gov.in. `Latest Data Timestamp` is `MAX(fact_cpcb_subindex[timestamp_local])`,
so it says nothing about OpenAQ or Open-Meteo. I'm leaving it that way on
purpose, but anyone reading the dashboard should know it's data.gov.in-only.

## Problem 1: Task Scheduler wouldn't run unattended (fixed)
- All three ingestion tasks were set to "Run only when user is logged on".
  Last Run Result showed 0x800710E0 (request refused). The clean-and-load
  task showed 0xC000013A (killed mid-run), same as in Phase 3.
- Switching to "Run whether user is logged on or not" failed with "One or more
  of the specified arguments are not valid."
- Things that did NOT fix it: setting "Configure for" to Windows 10; checking
  for a blank Windows password (I have one).
- First workaround: I made a local Windows account called `aqi_loader` and
  pointed the tasks at it. Windows then said the account needed "Log on as a
  batch job" rights. `secpol.msc` doesn't exist on this Windows Home edition,
  and the "Backup Operators" group doesn't exist either (net localgroup
  error 1376). Making `aqi_loader` an Administrator account worked. After
  that the tasks saved without error and Last Run Result went back to 0x0.
- The Windows account `aqi_loader` and the MySQL user `aqi_loader` are two
  unrelated things that happen to share a name. I mixed them up while
  debugging.
- Final setup (2026-10-25): I wanted the tasks on my own account. `SNUHITH`
  turned out to be a local account (Get-LocalUser shows PrincipalSource
  Local), not a Microsoft account, so my Microsoft account password didn't
  apply. `runas /user:SNUHITH cmd` gave error 1326 with the
  wrong password, and a later attempt to save a task said Task Scheduler
  could not apply the change (user unknown, password incorrect, or no
  permission). Both fit a wrong password, but I didn't prove why the very
  first "arguments not valid" error happened. With the right Windows sign-in
  password, Open-Meteo switched first and produced a scheduled file, then I
  switched the other three one at a time. All four now run as `SNUHITH` with
  "Run whether user is logged on or not". I deleted the Windows `aqi_loader`
  account on 2026-10-25. The MySQL user `aqi_loader` and `.env` were not
  touched, and clean-and-load runs after the deletion connected to MySQL fine.
- The tasks store the SNUHITH password. If I change that password, each task
  has to be re-saved.
- StopIfGoingOnBatteries was True on all four tasks even though the
  Conditions tab showed the box unticked (it is greyed out while the
  AC-power condition is off). After the switch, Get-ScheduledTask showed
  Stop=False Disallow=False on all four.

## Problem 2: data.gov.in API unreachable (resolved 2026-10-12, cause unknown)
- Last successful raw file before the outage: `data_gov_in_20260925_0952.json`.
- `Test-NetConnection api.data.gov.in -Port 443` failed (TCP and ping) while
  `www.data.gov.in` and `cpcb.nic.in` connected fine. So my network, DNS,
  proxy and firewall were not the problem. Only the API host
  (164.100.61.198) was dead.
- The failure type kept changing: connection refused (WinError 10061), one
  DNS failure (Oct 6 00:09), a 502 Bad Gateway (Oct 6 01:47), a 30s read
  timeout (Oct 6 06:27), then refused again (Oct 7 and Oct 9). That looks
  like an unstable server, not a credentials problem. The DNS failure hit
  data.gov.in and Open-Meteo in the same second and OpenAQ worked 14 minutes
  later, so I treated it as a network blip.
- Still failing on 2026-10-09 11:57. The first successful fetch was at 20:56
  on 2026-10-12 (734,526 bytes, a full response). The outage lasted about
  17.5 days.
- From 2026-10-13 the hourly task wrote full files again. For example
  `data_gov_in_20261013_2252.json` was written at 22:52:22, five seconds
  after the 22:52:17 trigger. A fetch also worked from my home network, so
  the failures were not specific to the other network I tested on.
- What changed on the server side is not known, and I never checked whether
  data.gov.in changed the endpoint or key policy.
- `fact_cpcb_subindex` has no rows dated 2026-09-26 to 2026-10-11. The gap is
  not back-filled: the pipeline only processes the newest raw file and the
  API has no history endpoint.

## Problem 3: gaps across all three sources (the laptop, not the pipeline)
Three independent APIs stalling together points at the machine, which is what
the stale-raw check is for.
- 8 Oct 23:20 to 9 Oct 11:45 (12.6 hours): my first guess was sleep, which
  was wrong. The sleep events that day were all 2-3 seconds long
  (Kernel-Power events 42/107). Windows event 1074 at 23:20:23 shows
  Explorer.EXE initiated a power-off for my user. I shut the laptop down.
- 13 Oct 17:21 to about 20:05: event 1074 at 17:21:11, another shutdown. The
  runs due at 17:06 and 17:10 also left no files and I didn't check why.
- 13 to 14 Oct overnight: all three stale at 09:38, newest raw files 23:26
  to 23:27. Laptop not running, cause not checked.
- 26 Oct 03:35 to about 12:59: event 1074 at 03:34:58, another shutdown.
- 17 Oct about 17:00 to 20:00: all four tasks missed several hourly runs
  (Open-Meteo 18:06 and 20:06, OpenAQ 18:11, data.gov.in 17:52 to 19:52,
  clean-and-load 17:38 and 18:38). The Kernel-Power query found no sleep
  events in that window. Cause not established. It also hit the three tasks
  that were still running as aqi_loader, so the account switch can't explain it.
- Task history was disabled during all of these, so the Task Scheduler log
  had nothing. Enable it (Actions pane -> Enable All Tasks History).

## Problem 4: OpenAQ reporting irregularly (source side, cause not established)
- `fact_openaq_concentration`: 359 rows, max timestamp 2026-10-02 14:00 on
  Oct 7, then 399 rows, max 2026-10-07 20:00 after the next load, and 487
  rows by Oct 13.
- Rows by reading date: 7 Oct 40, 8 Oct 40, 10 Oct 8, 12 Oct 40 (none for
  9 and 11 Oct).
- On Oct 9 the loader was inserting nothing (`inserted=0, skipped_duplicate=127`)
  and I wrote that the sample had gone quiet. That was too strong: the 8 Oct
  readings loaded afterwards.
- The 20-station sample did not change (20 unique station IDs in the October
  logs). A search of the raw files found the 8 Oct readings only in the two
  files fetched on 13 Oct (20:11 and 20:23), about five days after their
  timestamps. The search pattern was a guess and only covered
  `openaq_latest_*` files, so treat this as indicative.
- I don't know whether OpenAQ publishes late or the stations report in
  bursts. Readings missed while the laptop is off are lost, because only the
  newest reading per sensor is kept.
- `skipped_unknown_pollutant=20` on every OpenAQ run is the weather sensors
  (temperature, humidity, wind) that OpenAQ reports through the pollutant
  field. They are excluded on purpose (Phase 5).

## Problem 5: some task attempts refused with 0x800710E0 (cause not established)
- clean-and-load: 13 Oct 20:06 and 14 Oct 10:13, both off its xx:38 schedule.
  On 14 Oct there is no log line at 10:13, so Windows refused the task before
  the script started.
- data.gov.in: 26 Oct 13:10:16 and 14:10:16, both off its xx:52:17 trigger.
- Scheduled runs worked around each one (clean-and-load finished OK at 13:51,
  14:38 and 14:39 on 14 Oct; the data.gov.in task wrote a full file at
  13:52:22 on 26 Oct), so no data was lost.
- Checked and not the cause: the battery settings were identical across
  tasks, each task has a single trigger, and the two ingestion tasks launch
  separate .bat files. Earlier refusals each followed a power-on, but the
  14 Oct one isn't tight, so I don't call that the cause.
- Ingestion tasks exit 0 even when a fetch fails (for example the
  getaddrinfo DNS failure at 20:11 on 17 Oct), so a 0 result there only means
  the script ran. The raw files and the log are the real evidence.

## .env findings
- `DATA_GOV_IN_API_KEY` was pasted twice with the identical value. Harmless,
  because python-dotenv takes the last value and they matched. It did not
  cause the outage.
- `MYSQL_USER` / `MYSQL_PASSWORD` were each defined twice, once as `root`
  and once as `aqi_loader`. This one was a real risk: python-dotenv takes the
  last entry, so the loaders were using `aqi_loader` only because that block
  came second. Reordering the file would have silently switched every loader
  to root and defeated the least-privilege setup from Phase 5. It is the
  same bug found in Phase 8. I deleted the root pair.

## Verification
- 2026-10-09 12:18: ran `python -m src.loading.run_clean_and_load` after the
  `.env` edit. It connected and loaded all three sources with no database
  errors. Open-Meteo inserted 11 new current-weather rows and overwrote 264
  forecast rows. The only failure in the summary was data.gov.in (stale raw
  input), which is correct. `fact_weather_observations` went from 759 to 770
  rows after a real run, so the duplicate constraints are intact.
- 2026-10-13 10:31: a manual run inserted 569 data.gov.in rows
  (`skipped_unknown_city=1431`), and the freshness card dropped to 1 hour.
- 2026-10-25 and 26: with all four tasks on SNUHITH, scheduled runs produced
  files at 22:06, 22:11 and 22:52 (25 Oct) and 13:06, 13:11, 13:38 and 13:52
  (26 Oct), and clean-and-load finished OK at 14:38 after the Windows
  `aqi_loader` account was deleted. I did not test the signed-out case.
- The API key still shows as `***REDACTED***` in the logs.

## Mistakes I made while debugging
- I misread the first set of unlabelled query results and thought the
  weather table was stuck. It was fine.
- I blamed sleep for the overnight gap before checking the power events.
- I looked at the duplicate API key as a possible cause. It was a dead end.
- I said OpenAQ had gone quiet on Oct 7. Later loads showed it hadn't, so the
  claim was too strong.
- I tried my recently changed Microsoft account password for SNUHITH before
  checking that SNUHITH is a local account.

## Still open
- Cause of the 0x800710E0 refusals, and of the 17 Oct missed runs.
- Why OpenAQ readings arrive irregularly and late.
- Overnight and evening gaps whenever the laptop is shut down. Options:
  accept and document, or move polling to an always-on machine.
- Turn on Task Scheduler history.
- Confirm the Windows Update active hours setting was actually saved.
- The signed-out case (tasks running while nobody is signed in) is untested.
