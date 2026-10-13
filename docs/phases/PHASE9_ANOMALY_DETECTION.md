# Phase 9: Anomaly Detection

**Project:** India Urban Air Quality Intelligence & Early-Warning System
**Status:** Complete

## Summary

This phase adds a seasonal anomaly detector on top of the historical Kaggle AQI data already loaded into MySQL. Each daily AQI reading is compared against what is normal for that city in that calendar month, and readings that fall far outside that range are flagged. Results are stored in a new table, `fact_kaggle_anomaly_flags`, so later phases (forecasting, early warning) can query them directly.

| Item | Value |
|---|---|
| Source table | `fact_kaggle_daily_aqi` |
| Method | Per-city, per-month median/MAD baseline, modified z-score |
| Flag rule | `abs(modified_z) > 3.5` |
| Readings scored | 74,826 |
| Readings flagged | 2,002 (2.68%) |
| Cities covered | 9 of 11 target cities |
| New table | `fact_kaggle_anomaly_flags` (74,826 rows) |
| New scripts | `detect_anomalies_kaggle.py`, `load_kaggle_anomalies.py` |
| Notebook | `notebooks/phase9_anomaly_detection.ipynb` |

## Why this method

The Phase 8 analysis showed two things that rule out a simple threshold or a plain z-score:

1. AQI in North Indian cities has a strong seasonal swing (roughly 3x between winter and monsoon in Delhi). A single global threshold would flag most winter days.
2. At least one station (Ahmedabad GJ001) contains values far outside the valid 0-500 scale. A mean and standard deviation would be pulled around by values like that.

Four approaches were considered:

| Approach | Decision | Reason |
|---|---|---|
| `seasonal_decompose` per city, threshold the residuals | Not used | Needs a continuous series. The known gaps (Delhi/Patna 2017, Lucknow 2018, Patna 2020) would distort the decomposition itself. |
| Per-city, per-month median/MAD baseline with modified z-score | **Used** | A missing day simply drops out of its group. Robust to extreme values. Easy to check by hand. |
| Isolation Forest or similar | Deferred | Better for joint pollutant + weather anomalies, but harder to explain why a point was flagged. |
| Rolling z-score with no seasonal adjustment | Rejected | Would flag ordinary winters. |

The scoring formula is:

```
modified_z = 0.6745 * (aqi - median) / MAD
```

where the median and MAD (median absolute deviation) are computed per city and calendar month, pooling all years. A reading is flagged when `abs(modified_z) > 3.5`.

## Scope decisions

- **Data source:** `fact_kaggle_daily_aqi` only. It is the only source with several years of history. The live feeds (data.gov.in, OpenAQ) have only weeks of data so far, which is not enough to define a seasonal baseline. Scoring live data is left for Phase 11.
- **Granularity:** city level. Station-level detection is a possible later extension.
- **Station set:** all valid Kaggle stations (`flag_missing = 0`), not the 24-station "stable panel" from Phase 8. That panel was built only to isolate a station-growth effect and would discard valid data here.
- **Excluded station:** Ahmedabad GJ001 is dropped entirely. Its AQI values are known to be invalid (max 2049 on a 0-500 scale) and do not reconcile with its own pollutant readings.

### Effect of excluding GJ001: 9 cities, not 10

Ahmedabad has only one Kaggle station, and it is GJ001. Excluding it removes Ahmedabad from this phase altogether. Combined with Pune (which has no Kaggle readings at all), anomaly detection covers **9 of the 11 target cities**: Bengaluru, Chennai, Delhi, Hyderabad, Jaipur, Kolkata, Lucknow, Mumbai, Patna. These are two separate gaps with different causes.

## Data preparation

Row counts were checked at each step against figures confirmed in earlier phases.

| Step | Rows | Check |
|---|---|---|
| Pull from `fact_kaggle_daily_aqi` joined to `dim_station` and `dim_city` | 95,058 | Same as Phases 6-8 |
| Drop `flag_missing = 1` | 76,160 | 19.9% missing, matches Phase 6 |
| Drop station GJ001 | 74,826 | 1,334 rows removed |

## Baseline

The baseline has 108 groups (9 cities x 12 months). Before using it, two checks were run:

- **Group size:** the smallest group is Patna in September with 87 readings. Jaipur and Kolkata, which start reporting later, still have 150+ readings in every month. No group was too small to use.
- **Zero MAD:** no group has a MAD of zero, so no score divides by zero. The scored data contains no NaN values.

## Results

74,826 readings were scored and 2,002 flagged (2.68%), which is in the normal range for a 3.5 threshold on real data. Flag rates by city:

| City | Total readings | Flagged | Rate |
|---|---|---|---|
| Chennai | 4,810 | 377 | 7.84% |
| Bengaluru | 9,639 | 316 | 3.28% |
| Jaipur | 3,011 | 93 | 3.09% |
| Lucknow | 5,245 | 133 | 2.54% |
| Hyderabad | 7,025 | 167 | 2.38% |
| Delhi | 36,107 | 835 | 2.31% |
| Kolkata | 2,996 | 44 | 1.47% |
| Patna | 2,121 | 17 | 0.80% |
| Mumbai | 3,872 | 20 | 0.52% |

Chennai's rate is more than double any other city's, and one Bengaluru station produced half of the 50 most extreme scores. Both were investigated before the output was accepted.

### Chennai: Manali station

Looking at each Chennai station's typical value (median AQI), not just its flagged days:

| Station | Median AQI |
|---|---|
| Manali, Chennai - CPCB | 104 |
| Manali Village, Chennai - TNPCB | 98 |
| Alandur Bus Depot, Chennai - CPCB | 94 |
| Velachery Res. Area, Chennai - CPCB | 78 |

Manali is an industrial and refinery area and is consistently the dirtiest of Chennai's stations. It accounts for 180 of Chennai's 377 flags. The readings are valid. The issue is that a city-wide baseline, pulled down by the cleaner residential stations, is too strict for it.

Decision: keep the station, and mark every Chennai row with `baseline_note = 'mixed-use city, industrial station present'`. Station-level baselines would remove the issue and are a candidate for later work.

### Bengaluru: BWSSB Kadabesanahalli station

This station produced 25 of the 50 highest scores, similar to how GJ001 first showed up in Phase 7. Its flags by year:

| Year | Flags |
|---|---|
| 2015 | 49 |
| 2016 | 23 |
| 2017 | 22 |
| 2018 | 2 |
| 2019 | 17 |
| 2020 | 6 |

The flags span five of six years and taper off, and the station's value range (8 to 727) is plausible. That fits a spike-prone location rather than a faulty sensor, so the station stays in the model.

### Values above 500

Several flagged readings exceed 500 (for example 917 in Hyderabad, 814 in Lucknow). Across the 425 flagged readings above 500, 45 distinct stations are involved. Delhi's Anand Vihar is the largest single contributor (155), consistent with it being one of Delhi's most polluted monitoring points. Unlike GJ001, this is not concentrated in one or two stations, so no further exclusions were made.

## Implementation

### Detection script

`src/processing/detect_anomalies_kaggle.py` reproduces the notebook logic end to end: pull, filter, exclude GJ001, build the baseline, score, flag, attach the Chennai note. It writes `data/processed/kaggle_anomalies/<date>/kaggle_anomaly_flags.csv`. Its log output matched the notebook exactly (95,058 -> 76,160 -> 74,826, 0 NaN, 2,002 flagged).

```powershell
python -m src.processing.detect_anomalies_kaggle
```

### Database table

```sql
CREATE TABLE fact_kaggle_anomaly_flags (
    anomaly_id      INT AUTO_INCREMENT PRIMARY KEY,
    daily_aqi_id    INT NOT NULL,
    station_id      INT NOT NULL,
    city_name       VARCHAR(50) NOT NULL,
    month           TINYINT NOT NULL,
    median_aqi      DECIMAL(6,2) NOT NULL,
    mad_aqi         DECIMAL(6,2) NOT NULL,
    modified_z      DECIMAL(8,4) NOT NULL,
    is_anomaly      BOOLEAN NOT NULL,
    baseline_note   VARCHAR(255) NULL,

    CONSTRAINT fk_anomaly_daily_aqi FOREIGN KEY (daily_aqi_id)
        REFERENCES fact_kaggle_daily_aqi(daily_aqi_id),
    CONSTRAINT fk_anomaly_station FOREIGN KEY (station_id)
        REFERENCES dim_station(station_id),
    CONSTRAINT uq_anomaly_reading UNIQUE (daily_aqi_id)
);
```

| Column | Purpose |
|---|---|
| `daily_aqi_id` | Links each score to its source reading. Unique, so each reading is scored once. |
| `station_id` | Stored directly (also reachable via `daily_aqi_id`) so queries do not need an extra join. |
| `city_name`, `month` | The baseline group the reading was scored against. |
| `median_aqi`, `mad_aqi` | The baseline values used, stored so a flag can be traced without recomputing. |
| `modified_z`, `is_anomaly` | The score and the resulting flag. |
| `baseline_note` | Nullable. Set only for Chennai rows. |

Both foreign keys were confirmed through `INFORMATION_SCHEMA.KEY_COLUMN_USAGE` after creation.

### Loader

`src/loading/load_kaggle_anomalies.py` follows the same pattern as `load_kaggle.py`: it uses the shared `get_connection()` helper and treats MySQL error 1062 (duplicate key) as a skip rather than a failure.

```powershell
python -m src.loading.load_kaggle_anomalies data\processed\kaggle_anomalies\<date>\kaggle_anomaly_flags.csv
```

## Verification

| Check | Expected | Result |
|---|---|---|
| First load: inserted / skipped / errors | 74,826 / 0 / 0 | 74,826 / 0 / 0 |
| `SELECT COUNT(*)` on the table | 74,826 | 74,826 |
| Rows with `is_anomaly = 1` | 2,002 | 2,002 |
| Rows with `baseline_note IS NOT NULL` | 4,810 (all Chennai rows) | 4,810 |
| Second load of the same file | 0 inserted, 74,826 skipped | 0 inserted, 74,826 skipped |
| Row count after second load | 74,826 | 74,826 |

The second load confirms the unique constraint prevents duplicates.

## Limitations

- **Coverage:** 9 of 11 cities. Pune has no Kaggle readings; Ahmedabad was excluded with GJ001.
- **Historical only:** scores are based on 2015 to mid-2020 data. Live data has not been scored yet.
- **City-level baseline:** stations that differ structurally from their city (Chennai's Manali) are over-flagged. This is documented through `baseline_note` and not corrected.
- **Seasonality assumed stable:** pooling all years assumes a city's seasonal pattern did not change over the period. Station networks grew substantially from 2015 to 2020 (Phase 8), which this approach does not adjust for.
- **Known data gaps:** the 2017 gap (Delhi, Patna and others), Lucknow 2018 and Patna 2020 reduce the number of readings in affected months. They do not distort the baseline, but anomalies cannot be detected on missing days.
- **Manual execution:** the script and loader are run by hand and are not scheduled.
- **Loader warning:** `pandas` prints a `DtypeWarning` for the `baseline_note` column when reading the CSV. The load itself is unaffected, and the warning can be removed by passing `dtype` to `read_csv`.
- **Schema file:** `sql/create_schema.sql` has not yet been updated with the new table. It was created directly in MySQL Workbench.

## Files added or changed

| File | Change |
|---|---|
| `notebooks/phase9_anomaly_detection.ipynb` | New. Exploration and verification of the method. |
| `src/processing/detect_anomalies_kaggle.py` | New. Baseline, scoring, flagging, CSV output. |
| `src/loading/load_kaggle_anomalies.py` | New. Loads the CSV into MySQL. |
| MySQL: `fact_kaggle_anomaly_flags` | New table, 74,826 rows. |
| `files/PHASE9_ANOMALY_DETECTION.md` | This document. |
| `PROJECT_STATE.md` | Updated for Phase 9. |

## Next phase

Phase 10 covers short-term AQI forecasting. One open design question carried over from this phase is whether the flagged anomalies should be excluded from forecast training data or used as a feature.
