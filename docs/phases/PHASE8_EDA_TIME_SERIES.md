# Phase 8: Exploratory Data Analysis and Time-Series Analysis

**Project:** India Urban Air Quality Intelligence & Early-Warning System
**Status:** Complete
**Notebook:** `notebooks/phase8_eda_time_series.ipynb`
**Primary data:** `fact_kaggle_daily_aqi` (2015-01-01 to 2020-07-01), plus one external weather pull for Delhi

---

## 1. Objective

Phases 1 to 7 produced a loaded MySQL database and a Power BI dashboard, but none of the historical data had been analysed as a time series. Before building anomaly detection (Phase 9) or forecasting (Phase 10), this phase set out to answer a few basic questions about the data:

- How complete is the historical record, per city and per year?
- Is a city's yearly trend real, or does it reflect changes in which stations were reporting?
- What does normal seasonal variation look like, and does it differ by region?
- Are there stations or periods that should not be trusted?
- Does weather explain a meaningful share of day-to-day AQI variation?

---

## 2. Environment and Setup

- Added `sqlalchemy`, `jupyterlab`, `matplotlib`, `seaborn` and `statsmodels` to the project virtual environment and refreshed `requirements.txt`.
- Analysis was done in a local Jupyter Lab notebook that queries MySQL directly through SQLAlchemy and `mysql-connector-python`.
- The notebook connects as the existing read-limited `aqi_loader` user, not `root`. This phase only reads data, so no broader privileges were needed.
- Google Colab was considered and not used. Colab runs on Google's servers and cannot reach a MySQL instance on `localhost` without exposing the database to the internet or bridging through a local runtime.

### Configuration problems found and fixed

The first connection attempt failed with `Access denied for user 'None'@'localhost'`. Three separate issues were behind it:

1. The notebook read `DB_USER`, `DB_PASSWORD` etc., but the project's `.env` uses the `MYSQL_*` naming (`MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`).
2. `.env` contained two `MYSQL_USER` / `MYSQL_PASSWORD` pairs. `python-dotenv` keeps the last duplicate, so the file works only because the `aqi_loader` pair comes after the `root` pair. The duplicate was noted and the notebook loads `.env` by explicit path with `override=True`.
3. `MYSQL_DATABASE` was set to `india_air_quality_db`, but the live database is `india_air_quality`. Querying both showed that only `india_air_quality` contains the project tables (`fact_kaggle_historical` returned the expected 1,140,696 rows; the `_db` database has no tables). `.env` was corrected.

### Connection check

`SELECT COUNT(*) FROM fact_kaggle_historical` from Python returned 1,140,696, matching the figure confirmed in MySQL Workbench (Phase 6) and in the Power BI import (Phase 7).

---

## 3. Working Dataset

The daily dataset was built by joining `fact_kaggle_daily_aqi` to `dim_station` and `dim_city`, filtered to `source_system = 'kaggle'`.

| Check | Expected | Result |
|---|---|---|
| Total rows | 95,058 | 95,058 |
| Pune present | No | Absent |
| Rows with `flag_missing = 1` vs. rows with a null `aqi_value` | Equal | 18,898 and 18,898 |

The last check matters because `flag_missing` is stored as an integer (0/1). An early version of the check compared it to the string `"true"` and returned 0, which looked like a data problem but was a bug in the notebook code. After correcting the comparison, the flag and the nulls line up exactly, so pandas' default null-skipping averages are safe to use.

Rows per city: Delhi 45,360; Bengaluru 11,996; Hyderabad 8,752; Chennai 6,406; Lucknow 6,099; Mumbai 5,504; Kolkata 3,165; Jaipur 3,089; Patna 2,678; Ahmedabad 2,009.

---

## 4. Findings

### 4.1 Date coverage is uneven across cities

| City | First date | Last date | Days with data |
|---|---|---|---|
| Ahmedabad, Bengaluru, Chennai, Delhi, Lucknow, Mumbai | 2015-01-01 | 2020-07-01 | 2,009 each |
| Hyderabad | 2015-01-04 | 2020-07-01 | 2,006 |
| Patna | 2015-06-01 | 2020-07-01 | 1,858 |
| Jaipur | 2017-06-14 | 2020-07-01 | 1,114 |
| Kolkata | 2018-04-10 | 2020-07-01 | 814 |

Kolkata and Jaipur do not have the full 2015 to 2020 window that earlier phase documents implied. Any year-by-year comparison involving these two cities needs to account for that.

### 4.2 The number of reporting stations grew a lot over the period

Records per year rose sharply between 2017 and 2019 for most cities. Counting distinct stations per year shows why:

| City | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 |
|---|---|---|---|---|---|---|
| Ahmedabad | 1 | 1 | 1 | 1 | 1 | 1 |
| Bengaluru | 4 | 4 | 4 | 10 | 10 | 10 |
| Chennai | 3 | 3 | 3 | 3 | 4 | 4 |
| Delhi | 10 | 12 | 18 | 38 | 38 | 38 |
| Hyderabad | 2 | 3 | 6 | 6 | 6 | 6 |
| Jaipur | 0 | 0 | 3 | 3 | 3 | 3 |
| Kolkata | 0 | 0 | 0 | 2 | 7 | 7 |
| Lucknow | 2 | 2 | 4 | 4 | 5 | 5 |
| Mumbai | 1 | 1 | 1 | 1 | 10 | 10 |
| Patna | 1 | 1 | 1 | 1 | 4 | 6 |

The 2020 column sums to 90, which matches the 90 stations with data identified in Phase 6.

A city-level yearly average therefore partly reflects which parts of the city were being monitored that year, not only how pollution changed. To check how much this matters, a "stable panel" was defined: stations that appear in all six calendar years. This gave 24 stations (Delhi 10, Bengaluru 4, Chennai 3, Hyderabad 2, Lucknow 2, and one each in Ahmedabad, Mumbai and Patna). Jaipur and Kolkata have none.

The stable panel was used as a diagnostic tool in this phase. It is not intended as the working dataset for later phases, because it discards most stations.

### 4.3 Delhi's trend, and a data gap that distorted it

Delhi's yearly average AQI, using all stations versus the stable panel only:

| Year | All stations | Stable panel (10 stations) |
|---|---|---|
| 2015 | 302.3 | 302.3 |
| 2016 | 299.0 | 294.2 |
| 2017 | 326.1 | 371.0 |
| 2018 | 246.3 | 256.5 |
| 2019 | 232.0 | 236.3 |
| 2020 (Jan to Jun) | 183.5 | 181.6 |

Both versions have the same overall shape, so the decline after 2017 is not simply an effect of new stations joining. But both show 2017 as a peak, and the stable-panel figure (371) is a sharp outlier. That needed checking.

A gap analysis of Delhi's daily series (2,009 calendar days, 114 with no data) found two long gaps in 2017:

- 83 days starting 2017-06-09 (data resumes 2017-08-31)
- 24 days starting 2017-09-02 (data resumes 2017-09-26)

Both fall almost entirely in the June to September monsoon, which is Delhi's cleanest season (see 4.5). If most of a year's cleanest months are missing, that year's average is pulled upward.

The share of June to September days missing in Delhi, by year, was 0% in 2015, 0.8% in 2016, **88.5% in 2017**, and 0% in 2018 to 2020. Recomputing yearly averages with June to September excluded from every year gives a like-for-like comparison:

| Year | Avg AQI, Jun to Sep excluded |
|---|---|
| 2015 | 335.7 |
| 2016 | 357.2 |
| 2017 | 353.6 |
| 2018 | 305.7 |
| 2019 | 283.0 |
| 2020 (partial year) | 191.5 |

On this basis 2017 is roughly level with 2016 and no longer a spike. The corrected reading is a moderate elevation in 2016 to 2017 followed by a steady decline to 2020.

A decomposition of the daily series gave a misleading result: `seasonal_decompose` needs an unbroken series, and removing the rows left by the two long gaps shifted every later date out of position, which produced a visible straight-line dip. Interpolating 83 days of missing monsoon data was rejected, because that would invent three months of values. The decomposition was instead run on the **monthly** average series (one month with no data; short gaps interpolated up to 2 months; period = 12). The monthly trend component shows a gentle rise through 2016 to early 2017 and a steady decline afterwards, consistent with the like-for-like table above.

### 4.4 The same gap in other cities

The share of June to September 2017 days missing, per city (stable panel):

| City | Missing |
|---|---|
| Bengaluru | 0.8% |
| Chennai | 3.3% |
| Lucknow | 2.5% |
| Delhi | 88.5% |
| Hyderabad | 100% |
| Mumbai | 100% |
| Patna | 100% |

This is not a single national outage. Four cities lost most or all of the monsoon months in 2017 and three did not. Of the four, the effect on the yearly average depends on the city:

- **Patna:** the naive 2017 average (326) sits well above 2016 (252). With June to September removed from all years, 2016 rises to 307 and 2017 stays at 326. Most of the apparent jump is the gap; a smaller elevation remains.
- **Hyderabad:** 2017 (131) does not stand out against neighbouring years, so the gap has little visible effect on its yearly averages.
- **Mumbai:** yearly averages for 2015 to 2017 cannot be computed at all (see 4.6).

### 4.5 Seasonality

Seasonality was measured by averaging by calendar month across all years, using the stable panel and excluding Ahmedabad (see 4.6).

Delhi's monthly averages range from 135.3 (August) to 387.5 (November), roughly a 2.9x swing. November (387.5), December (373.8) and January (358.1) are the highest; July (150.9), August (135.3) and September (153.4) are the lowest. This matches the known pattern of winter inversions and post-monsoon crop-residue burning, followed by monsoon washout.

Across cities the pattern splits by region:

- **Delhi, Lucknow, Patna:** clear winter peak (roughly 320 to 400 between November and January) and a monsoon trough (roughly 95 to 150 in July and August). These three track each other closely.
- **Chennai, Bengaluru, Hyderabad:** stay between roughly 75 and 150 all year, with no strong winter peak.
- **Mumbai:** a smaller winter rise, with monthly values between roughly 83 and 154.

A formal decomposition of Delhi's monthly series gives a repeating annual seasonal component that matches the monthly averages and is separate from the trend.

### 4.6 Station-level data quality

The percentage of non-missing AQI values per city per year (stable panel):

| City | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 |
|---|---|---|---|---|---|---|
| Ahmedabad | 72.1 | 32.0 | 18.9 | 97.8 | 96.4 | 96.2 |
| Bengaluru | 73.6 | 62.8 | 68.9 | 75.9 | 82.7 | 82.9 |
| Chennai | 68.3 | 68.8 | 46.5 | 85.7 | 91.1 | 98.9 |
| Delhi | 51.4 | 40.4 | 27.0 | 95.3 | 98.5 | 96.5 |
| Hyderabad | 76.2 | 47.8 | 19.7 | 92.9 | 91.9 | 85.2 |
| Lucknow | 72.3 | 85.7 | 91.5 | 66.3 | 99.0 | 100.0 |
| Mumbai | 0.0 | 0.0 | 0.0 | 62.2 | 93.2 | 70.5 |
| Patna | 37.9 | 90.4 | 39.5 | 98.9 | 98.4 | 55.2 |

Completeness is generally lower in 2015 to 2017 and higher from 2018. Four specific issues stand out.

**Ahmedabad (station GJ001, Maninagar, GPCB).** This is Ahmedabad's only Kaggle station, and it was already flagged in Phase 7. Its AQI values reach 2049, well past the 0 to 500 scale, and they do not reconcile with the station's own pollutant readings. Phase 8 reproduces the maximum exactly (2049.0). The mean did not reproduce: this analysis gives 452.1 where Phase 7 documented 683.79. The two figures were not reconciled, and the cause is not known. Either value is far outside the valid scale, so the conclusion that this station is unreliable is unchanged. Ahmedabad was left out of the cross-city seasonality comparison. In the earlier version of that chart, GJ001 alone put Ahmedabad's curve at up to roughly 690, far above every other city.

**Mumbai, 2015 to 2017.** Mumbai's only stable-panel station reports a row every day in these years (365, 366 and 365 rows) but every value is blank. Usable data starts in 2018. This is a different problem from Ahmedabad: the values there are present but invalid; here they are absent.

**Lucknow, early 2018.** Monthly completeness in 2018: January 95.2%, February 48.2%, **March to May 0%**, June 55.0%, then 97% to 100% from July. This is a bounded outage. It does not affect the seasonal findings but it thins the sample for those months.

**Patna, early 2020.** Monthly completeness: January 100%, February 82.8%, March 83.9%, April 33.3%, May 0%, June 30.0%, with a single row in July (the dataset ends 2020-07-01). This is a decline rather than a clean gap. The timing overlaps the COVID-19 lockdown in India, and reduced maintenance of monitoring equipment is a plausible cause. This analysis does not confirm that.

### 4.7 Weather and AQI (Delhi)

Before this phase, the weather-versus-pollution relationship had not been tested with enough data. The only weather data in MySQL covers the live polling period (from August 2026), with no overlap with the 2015 to 2020 AQI history. The Phase 7 wind-speed chart had two data points.

Historical daily weather for Delhi was pulled from the Open-Meteo Archive API, using Delhi's coordinates from `dim_city` and the same date range as the AQI series. It was joined to Delhi's daily AQI (average of the 10 stable-panel stations), giving 2,009 matched days. Variables: daily maximum and minimum temperature, total precipitation, maximum wind speed.

Full-year Pearson correlations with AQI:

| Variable | Correlation |
|---|---|
| Minimum temperature | -0.48 |
| Precipitation | -0.28 |
| Maximum temperature | -0.27 |
| Maximum wind speed | -0.21 |

All four are negative, which is the expected direction for rain and wind. The strong temperature correlation is more likely to reflect season than a direct effect: Delhi's winters are cold and polluted, and its monsoon is warm and clean.

To test this, the same correlations were recomputed using winter days only (November, December, January; 491 days):

| Variable | Winter-only correlation |
|---|---|
| Maximum wind speed | -0.28 |
| Precipitation | -0.14 |
| Minimum temperature | +0.16 |
| Maximum temperature | +0.36 |

Interpretation:

- Wind speed keeps its negative sign and magnitude when season is held roughly constant, so it looks like a real day-to-day effect.
- Precipitation weakens but keeps its sign.
- Temperature changes sign. The full-year relationship was mostly seasonal. Why warmer winter days are somewhat more polluted is not explained by this analysis.

The AQI-versus-precipitation scatter plot has a wedge shape: on dry days AQI ranges up past 700, but on days with more than about 20 mm of rain AQI rarely exceeds roughly 350, and above about 40 mm it stays under roughly 250 (read from the plot, not computed). Heavy rain does not guarantee clean air but it appears to limit how bad a day can get.

These are correlations from one city and one weather grid point. They do not establish causation.

---

## 5. Limitations

- **Station coverage changes over time.** Yearly city averages from the full station set are partly a function of which stations were active. The stable panel addresses this for diagnosis, at the cost of dropping most stations.
- **2017 monsoon data is missing for several cities** (Delhi, Hyderabad, Mumbai, Patna). Any 2017 yearly figure for these cities should be read with that in mind.
- **Mumbai has no usable data before 2018**, and Ahmedabad's only station has invalid values. Neither can support historical trend claims.
- **Kolkata and Jaipur** have no stable-panel stations and start in 2018 and 2017 respectively.
- **The Patna 2020 and Lucknow 2018 gap causes are not confirmed.** No external outage records were checked.
- **Weather analysis covers Delhi only**, and used one grid point to represent a city-wide average of 10 stations.
- **The weather data is not in MySQL** and is not part of the automated pipeline. It was fetched into the notebook for analysis.
- **Pollutant-level time series were not examined.** The analysis used the overall daily AQI only.
- **2020 contains only January to early July** and is not comparable to a full year.

---

## 6. Open Items From Earlier Phases

Phase 8 did not contradict any written conclusion from Phases 1 to 7, but it affects two things built earlier. Neither has been changed yet.

1. **Power BI Overview page, "Average AQI by City, 2015 to 2020".** The chart uses all stations and has no adjustment for the 2017 gap, so the Delhi and Patna lines are affected by it. The Ahmedabad line also appears to be driven by GJ001 and has no disclosure on this page (the disclosure note is on the Data Quality page only). This should be confirmed by inspecting the line and then either excluding Ahmedabad from the chart or adding a note.
2. **GJ001 mean value.** Phase 7 documents 683.79; Phase 8 computes 452.1. The maximum matches. The difference is unexplained.

---

## 7. What This Phase Did Not Do

- No anomaly detection (Phase 9) and no forecasting (Phase 10).
- No change to the database schema, loaders or dashboard.
- No weather analysis outside Delhi.

---

## 8. Handoff to Phase 9

Findings that Phase 9 should build on:

- Anomaly thresholds need a seasonal baseline (per city and calendar month). A single threshold would flag every North Indian winter.
- GJ001 (Ahmedabad) and Mumbai 2015 to 2017 should not be treated as valid input. Mumbai's blank rows are already excluded by `flag_missing = 0`. Because GJ001 is Ahmedabad's only Kaggle station, excluding it removes Ahmedabad from historical modelling altogether.
- The baseline should use the full set of valid stations rather than the 24-station stable panel. The station-growth problem affects year-over-year comparisons, not a per-city, per-month baseline pooled across years.
- The 2017 monsoon gap, Lucknow's early-2018 gap and Patna's early-2020 decline mean some city-months rest on fewer years of data than others.

---

## 9. Reproducing This Phase

```powershell
cd C:\Dev\india-air-quality-intel
.\venv\Scripts\Activate.ps1
jupyter lab
```

Open `notebooks/phase8_eda_time_series.ipynb` and run the cells in order. The notebook expects `.env` at the project root with the `MYSQL_*` variables, and network access to `archive-api.open-meteo.com` for the weather section.
