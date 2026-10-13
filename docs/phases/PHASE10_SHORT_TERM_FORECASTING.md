# Short-Term AQI Forecasting

**Notebook:** `notebooks/phase10_forecasting.ipynb`
**Source tables:** `fact_kaggle_daily_aqi`, `fact_kaggle_anomaly_flags`, `dim_station`, `dim_city` (MySQL, `india_air_quality`)
**Scope:** 1-day and 3-day AQI forecasts for 7 cities, with translation of forecasts into AQI categories and a three-tier priority level

---

## Summary

This phase builds and evaluates short-horizon AQI forecasts on the historical Kaggle CPCB dataset (2015 to 2020-07-01). Forecasts are produced per city and compared against two baselines, a persistence forecast and a seasonal-median forecast, using a chronological train/test split. The model is a per-city Ridge regression on Fourier seasonality, lag, and rolling-mean features. Forecasts are then mapped onto India's AQI categories and a Low / Watch / Alert priority scale.

Key results:

- Persistence ("tomorrow equals today") is a strong baseline. It has lower RMSE than the seasonal median in all seven cities, by a factor of 1.3 (Bengaluru) to 3.0 (Delhi).
- At the 1-day horizon, tuned Ridge has lower RMSE than persistence in Bengaluru, Lucknow, and Patna, ties in Chennai, and has higher RMSE in Delhi, Hyderabad, and Mumbai.
- The lower-error model for each city is the same at both horizons, which gives a simple per-city routing rule: Ridge for Bengaluru, Chennai, Lucknow, and Patna; persistence for Delhi, Hyderabad, and Mumbai.
- No 1-day Ridge forecast was more than two AQI categories away from the observed category (1,074 test predictions).
- Detection of severe days (the Alert tier) differs sharply by city and is not predictable from RMSE. Patna is reliable at both horizons; Delhi and Lucknow miss most severe days at the 3-day horizon; four cities had no severe days in the test window and could not be evaluated.

---

## 1. Scope

| City | Stable-panel stations used |
|---|---|
| Delhi | 10 |
| Bengaluru | 4 |
| Chennai | 3 |
| Hyderabad | 2 |
| Lucknow | 2 |
| Mumbai | 1 |
| Patna | 1 |
| **Total** | **23** |

Four of the eleven target cities are out of scope, each for a documented reason: Ahmedabad (its only stable-panel station, GJ001, has AQI values outside the valid 0 to 500 scale), Jaipur and Kolkata (no stations with data in all six years), and Pune (no Kaggle readings).

The forecast target is the **city-day mean AQI** across the stable-panel stations that have a valid reading on that day.

---

## 2. Data preparation

### 2.1 Stable panel

Stations with readings in all six calendar years (2015 to 2020) were identified directly from MySQL: 24 stations, or 23 after removing GJ001. "Stable" means present in each calendar year, not complete within each year. Ten of the 23 stations begin after 2015-01-01 (between 2015-01-03 and 2015-11-10), so the number of stations contributing to a city's daily value changes over time.

### 2.2 City-day aggregation

44,804 station-day rows were aggregated to 13,909 city-day rows. Every station has a row for each day it is active, with gaps represented as rows with a missing AQI value rather than absent rows. 2,896 city-days have no valid reading from any station.

### 2.3 Known data gaps

| Window | City | Days | Handling |
|---|---|---|---|
| 2017-06-01 to 2017-09-26 | Delhi, Patna | 118 | Excluded from training |
| 2018-02-15 to 2018-06-12 | Lucknow | 118 | Excluded from training |
| 2015-01-01 to 2017-12-31 | Mumbai | 1,096 | Excluded from training (no usable readings) |

The Lucknow window refines the earlier "March to May 2018" description from the exploratory analysis. It was confirmed against the database as one contiguous block with no valid days inside it. Patna's decline in completeness in February to June 2020 (82 of 151 days missing in that window) is gradual rather than a clean block, so it is not excluded; it reduces the number of usable Patna test days.

### 2.4 Anomaly integration

Anomaly flags from the anomaly-detection phase are at station-day grain. They were rolled up to city-day grain, and a city-day is excluded from **training** when a strict majority (more than half) of the stations scored that day were flagged. Alternatives were compared before choosing this rule:

- "Any station flagged" scaled with station count rather than city-wide severity (any-station rate: Mumbai 0.0%, Patna 0.5%, Delhi 16.1%, Chennai 16.3%). In Chennai, 142 of 327 flagged days were flagged only because of its single industrial-zone station (Manali).
- "At least half flagged" is equivalent to "any station flagged" for two-station cities, because one of two stations is exactly 50%.

The strict-majority rule removes between 0.0% and 3.2% of each city's days. For single-station cities it reduces to that station's own flag.

| City | City-days excluded (strict majority) | Share |
|---|---|---|
| Bengaluru | 22 | 1.1% |
| Chennai | 65 | 3.2% |
| Delhi | 37 | 1.8% |
| Hyderabad | 55 | 2.7% |
| Lucknow | 16 | 0.8% |
| Mumbai | 0 | 0.0% |
| Patna | 10 | 0.5% |

### 2.5 Train/test split

The split is chronological: training through 2019-12-31, testing on 2020-01-01 to 2020-07-01 (183 days, the full remaining Kaggle window). Known-gap exclusions and majority-anomalous-day exclusions are applied to the **training set only**. The test set is left unfiltered so that reported error reflects realistic conditions, including difficult days.

Starting from 13,909 city-days, 3,336 are removed for a missing target or missing lag/rolling features, 8 for falling inside a known gap window, and 187 as majority-anomalous days (counts shown for the combined periods; in the final split the latter two exclusions apply to training only).

| City | Train rows | Test rows (1-day) | Test rows (3-day) |
|---|---|---|---|
| Bengaluru | 1,654 | 183 | 180 |
| Chennai | 1,602 | 183 | 180 |
| Delhi | 1,645 | 183 | 180 |
| Hyderabad | 1,222 | 169 | 163 |
| Lucknow | 1,519 | 183 | 180 |
| Mumbai | 519 | 95 | 86 |
| Patna | 1,144 | 78 | 72 |
| **Total** | **9,305** | **1,074** | **1,041** |

---

## 3. Forecast definition

Each row corresponds to a calendar day *t*. All lag and rolling features are computed from observations up to and including day *t*−1.

| Horizon | Target | Persistence baseline |
|---|---|---|
| 1-day | AQI on day *t* | AQI on day *t*−1 |
| 3-day | AQI on day *t*+3 | AQI on day *t* |

See Limitations (section 11) for the effect of this definition on the 3-day comparison.

---

## 4. Baselines

- **Persistence:** the most recent observed value is used as the forecast.
- **Seasonal median:** the median AQI for each city and calendar month, computed on the training period only. For the 3-day horizon it is keyed to the calendar month of the target date.

Baselines were first evaluated on all rows with a valid prediction, then re-evaluated on the common row set used for the model comparison, because persistence is undefined on the first day after a gap. Results were materially unchanged.

---

## 5. Features

- **Seasonality:** three harmonics of Fourier terms (sine and cosine pairs) on day of year, with a period of 365.25 days. This was chosen over a SARIMA-style seasonal term, which is numerically unstable at a period of 365, and over month indicators, which cannot represent a smooth annual cycle.
- **Momentum:** `lag_1`, `lag_7`, and 7-day and 30-day rolling means. The series is shifted by one day before each rolling window is computed so a day's own value never enters its own features.
- All lag and rolling operations are grouped by city. They were checked by hand against the raw series for one Delhi row (2018-03-15: `lag_1` = 286.78, 7-day rolling mean = 252.99).

---

## 6. Model

A separate Ridge regression is fitted per city on standardized features (the scaler is fitted on training data only). The regularization strength `alpha` is selected per city and per horizon using an inner chronological validation split, the last 20% of that city's training period, so the test set is never used for tuning.

- 1-day grid: 0.001, 0.01, 0.05, 0.1, 0.5, 1, 10, 50, 100 (the lower end was extended from 0.1 after several cities selected the original floor).
- 3-day grid: 0.001, 0.01, 0.1, 1, 10, 50, 100.

---

## 7. Results: 1-day horizon

RMSE on the test set, evaluated on the same rows for every model.

| City | Persistence | Seasonal median | Ridge (tuned) | Tuned alpha | Lowest RMSE |
|---|---|---|---|---|---|
| Bengaluru | 16.6 | 21.4 | **14.6** | 50 | Ridge |
| Chennai | 19.1 | 46.5 | 19.1 | 0.001 | Tie |
| Delhi | **41.4** | 126.1 | 43.8 | 0.001 | Persistence |
| Hyderabad | **14.7** | 39.4 | 18.7 | 0.001 | Persistence |
| Lucknow | 50.8 | 88.9 | **47.6** | 0.001 | Ridge |
| Mumbai | **19.0** | 37.1 | 19.8 | 100 | Persistence |
| Patna | 52.6 | 78.9 | **48.3** | 1 | Ridge |

Delhi and Hyderabad selected the smallest alpha in the grid and still did not beat persistence, so over-regularization does not explain the result. These two cities have the highest persistence R² (0.80 and 0.82), which leaves little unexplained variance for additional features to capture. Mumbai's result is sensitive to tuning: with a fixed alpha of 1 Ridge had a slightly lower RMSE than persistence (18.4 vs 19.0), but the validation-selected alpha of 100 reversed that on the test set. Mumbai has the shortest training history (519 rows).

---

## 8. Forecast reliability analysis

### 8.1 Normal days and anomaly days

A test day is labelled an anomaly day when at least one stable-panel station was flagged by the anomaly detector on that day. Only four cities have any such days in the test window (16 days in total); Delhi, Mumbai, and Patna have none.

| City | Anomaly days | Normal days | Persistence RMSE (anomaly / normal) | Ridge RMSE (anomaly / normal) |
|---|---|---|---|---|
| Bengaluru | 7 | 176 | 32.3 / 15.7 | 31.4 / 13.6 |
| Chennai | 3 | 180 | 60.0 / 17.6 | 62.9 / 17.5 |
| Hyderabad | 3 | 166 | 30.2 / 14.3 | 49.8 / 17.7 |
| Lucknow | 3 | 180 | 118.5 / 48.8 | 112.4 / 45.7 |

Error roughly doubles or more on anomaly days for both models. Hyderabad is the most pronounced case for Ridge, whose error nearly triples on anomaly days while persistence's roughly doubles. The sample is small (three to seven days per city).

### 8.2 AQI-category accuracy

Exact category match on the 1-day forecasts:

| City | Ridge | Persistence |
|---|---|---|
| Bengaluru | 72.1% | 70.5% |
| Chennai | 73.2% | 78.1% |
| Delhi | 63.4% | 69.9% |
| Hyderabad | 74.0% | 85.8% |
| Lucknow | 57.4% | 64.5% |
| Mumbai | 84.2% | 80.0% |
| Patna | 67.9% | 65.4% |

Across all 1,074 Ridge forecasts, 745 matched the observed category exactly, 323 were one category away, and 6 were two categories away. None was further away.

The six two-category misses occurred in Lucknow (4) and Patna (2). Five were over-predictions. The single under-prediction was Patna on 2020-02-28 (observed 302, Very Poor; predicted 198.8, Moderate). Only one of the six (Lucknow, 2020-01-17) fell on a day flagged by the anomaly detector, so anomaly flags and large forecast errors are largely independent signals.

---

## 9. Results: 3-day horizon

| City | Persistence | Seasonal median | Ridge (tuned) | Tuned alpha | Lowest RMSE |
|---|---|---|---|---|---|
| Bengaluru | 19.0 | 21.5 | **17.0** | 100 | Ridge |
| Chennai | 30.4 | 46.1 | **27.3** | 0.001 | Ridge |
| Delhi | **70.4** | 126.4 | 72.1 | 100 | Persistence |
| Hyderabad | **29.0** | 38.8 | 29.9 | 1 | Persistence |
| Lucknow | 72.4 | 89.3 | **62.2** | 100 | Ridge |
| Mumbai | **24.8** | 35.5 | 25.6 | 100 | Persistence |
| Patna | 80.0 | 84.8 | **64.3** | 100 | Ridge |

- Persistence error grows with horizon in every city (for example Delhi 41.4 to 70.4, Chennai 19.1 to 30.4).
- Ridge's relative improvement over persistence is larger at 3 days in Chennai (tie to 10% lower), Lucknow (6% to 14% lower), and Patna (8% to 20% lower), and roughly unchanged in Bengaluru (12% to 11% lower).
- The lower-error model for each city is the same at both horizons.
- The preferred regularization depends on horizon. Delhi moves from the lowest alpha at 1 day to the highest tested at 3 days, consistent with `lag_1` carrying less information as the horizon lengthens.

---

## 10. Forecast-to-risk translation

Each forecast from the routed model (Ridge or persistence per city) is mapped to India's six AQI categories (Good ≤50, Satisfactory ≤100, Moderate ≤200, Poor ≤300, Very Poor ≤400, Severe >400) and then to three priority tiers:

| Tier | Categories |
|---|---|
| Low | Good, Satisfactory |
| Watch | Moderate, Poor |
| Alert | Very Poor, Severe |

Tier distribution of routed test forecasts: at 1 day, Low 554, Watch 445, Alert 75. At 3 days, Low 475, Watch 491, Alert 69, with 6 forecasts unclassified because the predicted value is missing (Mumbai).

### Alert-tier detection

The Alert tier is evaluated as a binary classification of severe days. Recall is the more important measure, since a missed severe day is a costlier error than a false alarm.

| City | Observed Alert days (1d / 3d) | Precision 1d | Recall 1d | Precision 3d | Recall 3d |
|---|---|---|---|---|---|
| Delhi | 25 / 22 | 65.4% | 68.0% | 36.0% | 40.9% |
| Lucknow | 13 / 11 | 45.5% | 38.5% | 28.6% | 18.2% |
| Patna | 38 / 31 | 84.2% | 84.2% | 81.1% | 96.8% |
| Bengaluru, Chennai, Hyderabad, Mumbai | 0 / 0 | n/a | n/a | n/a | n/a |

Patna's Alert-tier forecasts are reliable at both horizons. Delhi and Lucknow miss most severe days at the 3-day horizon, even though their overall RMSE looked only moderately worse than other cities, so average error is not a reliable indicator of early-warning usefulness. The four cities with no observed Alert-tier days cannot be assessed with this test window; this is an absence of evidence, not evidence of reliability.

---

## 11. Validation and issues resolved

- **Reconciliation:** station counts, row counts, and per-city date ranges were reconciled against figures from earlier phases (90 Kaggle stations, 44,804 station-day rows, 13,909 city-day rows). The notebook was rebuilt from a clean kernel and reproduced every count in this document.
- **Leakage check:** lag and rolling features were verified by hand against the raw series.
- **Anomaly rollup rule:** the strict-majority rule replaced an initial "at least half" rule after it was found to reduce to "any station" for two-station cities (Hyderabad and Lucknow had identical exclusion rates under both rules).
- **Tier-mapping default case:** an early version of the Alert-tier evaluation passed raw AQI values into a function expecting category labels. Every value fell through to the function's default branch and was labelled Alert, producing an implausible 100% recall in every city. The result was identified as implausible because severe days are rare (about 7% of the test set), and the evaluation was corrected to map values to categories before tiering.
- **Missing predictions in tier counts:** the notebook's 3-day tier count shows 75 Alert days. Six of these are Mumbai forecasts with no predicted value that the same default branch labelled Alert; the correct count is 69. The early-warning table built from these forecasts uses a version of the mapping that returns a missing value for missing input and raises an error for unrecognised categories.

---

## 12. Limitations

- **Short test window.** The 183-day test window (January to July 2020) covers a single partial year. Hyderabad, Mumbai, and Patna have 169, 95, and 78 usable test days.
- **Severe-day coverage.** Four of seven cities had no observed Alert-tier days, and only four cities had any anomaly-flagged days, so Alert-tier and anomaly-day conclusions rest on a small number of events.
- **3-day horizon alignment.** Lag and rolling features end on day *t*−1, so the Ridge forecast of day *t*+3 is made from information four days before the target. The persistence baseline for the same target uses day *t*, three days before it. The two models therefore do not share an information cutoff at the 3-day horizon, which disadvantages Ridge, and the 3-day comparison and the routing conclusion should be read with that in mind. Aligning both models to the same last observed day is the natural refinement.
- **Regularization grid.** For Mumbai at 1 day and for five cities at 3 days (Bengaluru, Delhi, Lucknow, Mumbai, Patna), the selected alpha is the largest value tested, so the optimum may lie above the grid.
- **Variable station composition.** City-day values are means over a station set that changes over time even within the stable panel.
- **Small training history for Mumbai.** 519 training rows, with all of 2015 to 2017 unusable.
- **Historical backtest only.** The Kaggle data ends on 2020-07-01. Forecasts are evaluated retrospectively and are not generated from live sources.

---

## 13. Out of scope

- A 7-day horizon, which would further shorten the already short test window.
- Forecasting from the live data.gov.in and OpenAQ feeds, for which only about a month of hourly history is available.
- Weather covariates. A direct wind-speed effect on Delhi's AQI was confirmed in the exploratory analysis but is not included in this feature set.
- Scheduling or deployment of the forecasting pipeline.

---

## 14. Outputs

The final notebook cell exports routed test-set predictions for both horizons (observed AQI, predicted AQI, observed and predicted category, and priority tier, per city) to `data/processed/phase10_test_predictions/`. These predictions are the input to the early-warning table built in the following phase.
