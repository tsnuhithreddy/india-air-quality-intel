# Phase 6: Kaggle Historical Data, Cleaning and Loading

**Project:** India Urban Air Quality Intelligence & Early-Warning System
**Status:** Complete
**Completed:** 2026-08-30

---

## Summary

Before this phase, three of the four planned data sources were loaded into MySQL. The Kaggle historical dataset had been downloaded and checked in Phase 3, but it had no cleaning script and no database tables. This phase fills that gap.

What was done:

- Inspected the raw Kaggle files and decided which ones to use
- Checked which of the 11 target cities actually have readings
- Added two new fact tables and made two small changes to existing tables
- Wrote `clean_kaggle.py` (raw CSV to two cleaned CSVs)
- Wrote `load_kaggle.py` (cleaned CSVs to MySQL)
- Loaded 1,140,696 pollutant readings and 95,058 daily AQI rows, and checked the results against the database

Nothing in this phase is automated. Both scripts are run by hand.

---

## Why this was the next step

Three options were considered at the start of the phase:

1. Build the Kaggle loader.
2. Schedule the existing loaders with Task Scheduler.
3. Start analysis and dashboards on what was already in MySQL.

Option 1 was chosen because the other two depend on it. The live sources only had a few days of history, so any trend analysis or anomaly baseline would have had very little to work with. Scheduling the loaders would also have meant automating a database that was still missing one of its four sources.

---

## 1. Choosing the input files

The Kaggle download ("Air Quality Data in India") contains five files:

| File | Grain | Used? |
|---|---|---|
| `stations.csv` | One row per station (ID, name, city, state, status) | Yes |
| `station_day.csv` | One row per station per day | Yes |
| `station_hour.csv` | One row per station per hour | No |
| `city_day.csv` | One row per city per day | No |
| `city_hour.csv` | One row per city per hour | No |

Reasons:

- **Station level, not city level.** `dim_station` is built around individual stations, and city averages can always be computed later from station data. The reverse is not possible.
- **Daily, not hourly.** The goal is a historical baseline, not a second hourly feed. The hourly file is much larger and the extra resolution is not needed yet.

Leaving out three of the five files is a scope decision. If hourly historical data turns out to be needed later, `station_hour.csv` is already on disk.

Verified directly from `station_day.csv`: 108,035 rows, 110 distinct stations with readings, dates from 2015-01-01 to 2020-07-01. `stations.csv` lists 230 stations in 127 cities. So roughly half of the listed stations have no readings at all.

---

## 2. City coverage check

`stations.csv` was compared against the 11 target cities, and each station was checked for rows in `station_day.csv`.

| City | Stations listed | Stations with readings |
|---|---|---|
| Delhi | 38 | 38 |
| Mumbai | 10 | 10 |
| Bengaluru | 10 | 10 |
| Hyderabad | 6 | 6 |
| Chennai | 4 | 4 |
| Kolkata | 7 | 7 |
| Pune | 1 | 0 |
| Ahmedabad | 1 | 1 |
| Lucknow | 5 | 5 |
| Jaipur | 3 | 3 |
| Patna | 6 | 6 |
| Total | 91 | 90 |

**Pune.** Earlier documentation said Pune was "not included" in this dataset. The more accurate statement is that Pune has one station listed in `stations.csv`, but that station has no rows in `station_day.csv`. The practical result is the same (no historical data for Pune), and the documentation has been updated to say it this way.

The load scope is therefore 90 stations in 10 cities.

---

## 3. Database changes

All changes were made in MySQL Workbench against `india_air_quality`.

### 3.1 Widen `dim_station.source_system`

The column is an `ENUM`, which only accepts values from a fixed list. It previously allowed `data_gov_in` and `openaq`. Kaggle stations needed a third value.

```sql
ALTER TABLE dim_station
MODIFY COLUMN source_system ENUM('data_gov_in', 'openaq', 'kaggle') NOT NULL;
```

Existing rows are not affected.

### 3.2 Add three pollutants to `dim_pollutant`

The Kaggle pollutant columns were compared against the 11 codes already in `dim_pollutant`. Nine matched (Kaggle's `NOx` maps to the existing `NOX`). Three did not exist yet: Benzene, Toluene and Xylene. These are volatile organic compounds that neither data.gov.in nor OpenAQ had reported.

They were added, not dropped, because they are real pollutant readings. (This is different from the OpenAQ weather-sensor readings in Phase 5, which were excluded because they are not pollutants.)

```sql
INSERT INTO dim_pollutant (pollutant_code) VALUES ('Benzene'), ('Toluene'), ('Xylene');
```

`dim_pollutant` now has 14 codes. Benzene, Toluene and Xylene have IDs 12, 13 and 14.

### 3.3 Two new fact tables

`station_day.csv` holds two different kinds of data for each station and day: up to twelve individual pollutant values, and one overall AQI value with a category label. Putting both in one table would repeat the same AQI value on twelve rows for every station-day, and make it easy to mistake that repeated value for something that varies by pollutant. So there are two tables.

```sql
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
```

| Table | One row represents | Notes |
|---|---|---|
| `fact_kaggle_historical` | One station, one pollutant, one day | `pollutant_value` is NULL when the source was blank |
| `fact_kaggle_daily_aqi` | One station, one day | AQI and category are Kaggle's own precomputed values |

The `UNIQUE` keys stop the same reading being inserted twice. The foreign keys stop a reading being stored for a station or pollutant that does not exist. Both were confirmed with `DESCRIBE` after creation.

### 3.4 Kaggle stations are separate rows

Kaggle stations are inserted into `dim_station` as new rows. They are not matched to existing data.gov.in or OpenAQ stations, even where two stations are in the same neighbourhood. Matching stations across sources would need coordinate comparison and distance thresholds, and that decision was already postponed in Phase 1 and Phase 5. It stays postponed.

---

## 4. `src/processing/clean_kaggle.py`

Input: `data/external/kaggle_air_quality_india/stations.csv` and `station_day.csv`
Output: `data/processed/kaggle/kaggle_historical_readings.csv` and `kaggle_daily_aqi.csv`

Steps:

1. Load both input files.
2. Keep only stations whose city is one of the 11 target cities, then keep only the readings for those stations. Station name and city are merged onto each reading.
3. Reshape the pollutant columns from wide to long using `pandas.melt()`. The raw file has one row per station-day with twelve pollutant columns. The database wants one row per station-day-pollutant, so each pollutant column becomes its own row.
4. Map Kaggle's column names to the project's pollutant codes (the only real change is `NOx` to `NOX`).
5. Add quality flags: `flag_missing` (blank value), `flag_negative` (below zero), `flag_sentinel` (equal to 999, 9999 or -999), and `is_suspicious` (negative or sentinel).
6. Build a second table with the AQI value, AQI category and a `flag_missing` for AQI.

As in the other cleaning scripts, flagged rows are kept, not deleted.

Output of the final run:

```
Filtered to 90 stations, 95058 station-day rows
Wrote 1140696 rows to kaggle_historical_readings.csv
  flagged missing:    29.7%
  flagged suspicious: 0.0%
Wrote 95058 rows to kaggle_daily_aqi.csv
  flagged missing: 19.9%
```

Check on the row count: 95,058 station-days times 12 pollutants is 1,140,696, which matches.

### Checking the "0.0% suspicious" result

Zero negative values and zero sentinel codes across 1.14 million sensor readings looked too clean to accept without checking. Two temporary checks were run and then removed from the script:

- Minimum and maximum value: 0.0 and 1000.0. Counts of 999, 9999 and -999: all zero.
- Because 1000.0 is a round number that can indicate a value capped by whoever prepared the data, its frequency was checked. It appears once in the whole dataset, in one PM2.5 reading.

A single 1000.0 is not what a systematic cap would look like (that would show up many times), and PM2.5 readings that high do occur in Delhi winters. The conclusion is that the dataset was probably cleaned by its publisher before release. That is an inference from the data, not something the dataset's documentation confirms.

One consequence worth knowing: the negative and sentinel flag logic never fired on real Kaggle data, so it has not been exercised here against real positives. It is the same logic used in the other cleaning scripts, where it did fire.

---

## 5. `src/loading/load_kaggle.py`

The loader was written after reading the real `load_openaq.py` and `db_connector.py`, and follows their pattern so the loaders behave the same way: same `get_connection()`, same `str_to_bool()` for converting the CSV's "True"/"False" text, same handling of MySQL error 1062 (duplicate key), which is counted as a skip, not treated as a failure.

For each row it:

1. Finds the station in `dim_station` by Kaggle's station ID (for example `AP001`), or creates it if it does not exist.
2. Looks up the pollutant ID (readings file only).
3. Inserts the row, counting duplicates as skipped.

Two differences from `load_openaq.py`:

- **One script, two target tables.** It checks which file it was given. A `pollutant_code` column means the readings file (`fact_kaggle_historical`); an `aqi_value` column means the daily AQI file (`fact_kaggle_daily_aqi`). Any other format raises an error.
- **City is looked up, not left empty.** OpenAQ stations have `city_id = NULL` because OpenAQ does not say which target city a station is in. Kaggle's `stations.csv` does give a city name, so the loader matches it against `dim_city`. If a name ever failed to match, `city_id` would be NULL, not guessed.

Kaggle station latitude and longitude are NULL, because `stations.csv` has no coordinates.

Usage:

```powershell
python -m src.loading.load_kaggle data/processed/kaggle/kaggle_daily_aqi.csv
python -m src.loading.load_kaggle data/processed/kaggle/kaggle_historical_readings.csv
```

---

## 6. Load results

The daily AQI file was loaded first, so that all 90 stations were created in the first run. The much larger readings file was then loaded, which exercised the "station already exists" path.

| File | Rows read | Inserted | Duplicates | Unknown pollutant | Run time |
|---|---|---|---|---|---|
| `kaggle_daily_aqi.csv` | 95,058 | 95,058 | 0 | n/a | about 1 min 43 s |
| `kaggle_historical_readings.csv` | 1,140,696 | 1,140,696 | 0 | 0 | about 20 min |

### Checks against the database

The script's own log was not treated as sufficient. These were checked with queries in MySQL Workbench:

| Check | Expected | Result |
|---|---|---|
| Rows in `fact_kaggle_daily_aqi` | 95,058 | 95,058 |
| Rows in `fact_kaggle_historical` | 1,140,696 | 1,140,696 |
| Kaggle stations in `dim_station` | 90 | 90, and still 90 after the second load |
| City matching | Station names agree with matched city | Patna stations matched Patna, Delhi stations matched Delhi |
| Spot check of real rows | Values look plausible | Alipur, Delhi - DPCC, Nov 2018: PM2.5 232.36, PM10 415.28, NO2 79.86 |
| Missing rate in loaded table | Matches cleaning output | 29.7% |
| Suspicious rate in loaded table | Matches cleaning output | 0.0% |

A mistake during checking, for the record: the first spot-check query used station `AP001` and returned no rows. That station is in Amaravati, which is not a target city, so the cleaning script had correctly removed it. The query was wrong, not the loader. It was rerun with a station that is in scope.

---

## 7. Known limitations

- **Pune has no historical data.** One listed station, zero readings.
- **Coverage is uneven across cities.** This phase only confirmed that stations have some readings. It did not check how many days each station covers. (Later analysis may show some cities start much later than 2015.)
- **Units are not documented.** The Kaggle pollutant columns have no unit field. The values are assumed to be daily figures in the usual units, but this was not confirmed. The same applies to the precomputed AQI, which was calculated by the dataset's publisher and was not recomputed here.
- **Not comparable with the live sources.** Kaggle readings, data.gov.in sub-indices and OpenAQ concentrations are kept in separate tables and should not be compared directly.
- **Kaggle stations have no coordinates** and are not linked to stations from other sources.
- **The Kaggle data ends on 2020-07-01.** It is a fixed historical snapshot and does not update.
- **Loading is slow.** The loader inserts row by row, and the large file took about 20 minutes. Nothing is committed until the end of the file, so an interrupted run leaves nothing partial. A rerun skips any rows already present because of the unique keys. Batch inserts would be faster but were not needed for a one-time load.
- **Cleaned output is not date-partitioned.** Unlike the live sources, Kaggle output goes to `data/processed/kaggle/`, since the dataset is loaded once and has no daily runs.
- **Flag columns are partly dropped at load time.** `flag_negative` and `flag_sentinel` exist in the cleaned CSV, but only `flag_missing` and `is_suspicious` are stored in MySQL.
- **`sql/create_schema.sql` needs updating** with the two new tables and the changes to `dim_station` and `dim_pollutant`, so the committed schema matches the real database.

---

## 8. Files added or changed

| Path | Change |
|---|---|
| `src/processing/clean_kaggle.py` | New |
| `src/loading/load_kaggle.py` | New |
| `data/processed/kaggle/kaggle_historical_readings.csv` | Generated, not committed |
| `data/processed/kaggle/kaggle_daily_aqi.csv` | Generated, not committed |
| `fact_kaggle_historical`, `fact_kaggle_daily_aqi` | New MySQL tables |
| `dim_station.source_system` | ENUM widened to include `kaggle` |
| `dim_pollutant` | 11 to 14 codes |
| `PROJECT_STATE.md` | Updated |
| `docs/DATA_SOURCES_LOG.md` | Pune note refined |
| `sql/create_schema.sql` | Still to be updated |

`inspect_kaggle.py`, the throwaway script used to look at the raw files, is not part of the project and should not be committed.

---

## 9. Database state at the end of the phase

| Table | Rows |
|---|---|
| `dim_city` | 11 |
| `dim_pollutant` | 14 |
| `dim_station` | 244 (about 134 data.gov.in, 20 OpenAQ, 90 Kaggle) |
| `fact_cpcb_subindex` | 545 at last check, growing |
| `fact_openaq_concentration` | 127 at last check, growing |
| `fact_weather_observations` | 11 at last check, growing |
| `fact_weather_forecast` | 264 at last check |
| `fact_kaggle_historical` | 1,140,696 |
| `fact_kaggle_daily_aqi` | 95,058 |

The live table counts are from the Phase 5 load and will be higher once the loaders are run again.

---

## 10. Next

The database now has all four planned sources. The two main options are scheduling the loaders (ingestion has been automated since Phase 3, loading has not) or starting analysis and dashboards with the historical data as a baseline.
