# Project State

**Project Name:** India Urban Air Quality Intelligence & Early-Warning System

**Current Phase:** Phase 11 Complete → Ready for Phase 12

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
  user; wrote and verified a Python loader per live source, plus a
  combined runner (`load_all.py`)
* Phase 6: Closed the last data-source gap — built `clean_kaggle.py` and
  `load_kaggle.py`, designed two new fact tables
  (`fact_kaggle_historical`, `fact_kaggle_daily_aqi`), widened
  `dim_station.source_system`, expanded `dim_pollutant` from 11 to 14
  codes, loaded and verified 1,140,696 historical pollutant readings and
  95,058 daily AQI rows, refined the known Pune gap to the row level
* Phase 7: Built a 4-page Power BI analytics dashboard on top of the
  completed MySQL database — Overview, Data Quality & Coverage, Live
  Snapshot, and Alerts pages, each backed by real relationships mirroring
  the MySQL star schema, a shared DateTable, and a custom theme applying
  a consistent AQI severity color language throughout. Real findings:
  a single-station data-quality anomaly in Ahmedabad's historical AQI
  values; a NULL-handling bug that silently mislabeled missing readings
  as "Severe"; a tenant-level policy blocking classic Map visuals, worked
  around via ArcGIS Maps for Power BI. Pushed the full codebase to a
  public GitHub repository.
* Phase 8: Exploratory Data Analysis & Time-Series Analysis — the
  first formal statistical/time-series pass over the completed database,
  done in a local Jupyter Lab notebook (`notebooks/phase8_eda_time_series.ipynb`)
  connected directly to MySQL via the existing least-privilege
  `aqi_loader` account. Central finding: an apparent sharp 2017 AQI
  "spike" in Delhi (and Patna) was substantially a data-gap artifact — an
  83+24-day mid-2017 missing-data gap coincided almost entirely with
  monsoon season (the cleanest time of year), inflating that year's
  average. Corrected via a fair year-over-year comparison and confirmed
  via monthly `seasonal_decompose`. Confirmed real, geographically-coherent
  seasonality; found two new station-level data-quality issues beyond
  Ahmedabad (Mumbai zero-data 2015-2017; bounded Lucknow/Patna gaps);
  pulled genuinely new historical weather data and confirmed wind speed's
  direct effect on AQI while showing temperature's correlation was
  substantially a seasonal confound.
* Phase 9: Anomaly Detection — built a seasonal-baseline anomaly
  detector on top of `fact_kaggle_daily_aqi` (median/MAD per city per
  calendar month, modified z-score, `|z| > 3.5`), excluding Ahmedabad's
  GJ001 station entirely (dropping modeling scope to 9 of 11 target
  cities). 2,002 of 74,826 readings flagged (2.68%). Investigated
  Chennai's elevated flag rate (industrial-zone station, a real
  granularity limitation, documented via `baseline_note`) and Bengaluru's
  most extreme outlier station (confirmed as real recurring spikes, kept
  in the model). Built `detect_anomalies_kaggle.py` and
  `load_kaggle_anomalies.py`, loaded and verified `fact_kaggle_anomaly_flags`
  (74,826 rows, duplicate-safe).
* **Phase 10: Short-Term AQI Forecasting & Decision Support — built and
  evaluated a 1-day and 3-day AQI forecasting pipeline, entirely in
  `notebooks/phase10_forecasting.ipynb`, on top of the same 23-station
  "stable panel" used in Phases 8/9 (24 stable stations minus Ahmedabad's
  GJ001) — 7 usable cities: Delhi, Mumbai, Bengaluru, Hyderabad, Chennai,
  Lucknow, Patna. Rebuilt and independently re-verified the stable panel,
  city-day aggregation, and all four known data-quality gaps directly
  from MySQL rather than trusting prior documentation — refined Lucknow's
  gap from the documented "Mar-May 2018" (~92 days) to its real boundary,
  2018-02-15 to 2018-06-12 (118 days, one clean contiguous block).
  Rolled Phase 9's station-level anomaly flags up to city-day granularity
  using a strict-majority rule (more than half of scored stations agree),
  chosen after testing showed a looser "any station" rule degenerated
  into a single-station rule for 2-station cities and over-excluded
  Chennai based solely on its known industrial-zone station's normal
  behavior. Built a persistence baseline and a train-only seasonal-median
  baseline; persistence beat seasonal-median by 2-3x in every city,
  setting the real bar for modeling. Built per-city Ridge regression
  (Fourier seasonality + lag + rolling features, leakage-checked by hand
  against a real row) with alpha tuned via inner chronological
  validation; Ridge beat persistence in 3 of 7 cities (Bengaluru, Lucknow,
  Patna), tied in 1 (Chennai), and lost in 3 (Delhi, Hyderabad, Mumbai) —
  losses concentrated exactly where 1-day persistence was already
  strongest. Extended to a 3-day horizon using the identical pipeline;
  the per-city winner was stable across both horizons (a simple,
  deployable routing rule), and Ridge's relative advantage over
  persistence widened with horizon in every city where it already won.
  Built an AQI-category and 3-tier priority (Low/Watch/Alert) translation
  layer; band-distance analysis showed no test-set prediction was ever
  off by more than 2 categories. The most important finding came from
  Alert-tier precision/recall: 4 of 7 cities had zero genuinely severe
  test-window days (untestable, not a defect); of the 3 testable cities,
  Patna's forecast is reliable (84-97% recall at both horizons), while
  Delhi and Lucknow's Alert-tier recall is weak and *worsens* at 3-day
  (Delhi 68%→41%, Lucknow 38.5%→18.2%) — a failure mode invisible in
  every earlier RMSE-based comparison. Caught and fixed a silent
  default-case bug in the tier-evaluation code (raw AQI values passed
  where category labels were expected, causing every day to fall through
  to "Alert" and produce an impossible 100% recall) — the same bug class
  as Phase 7's NULL→"Severe" mislabeling. Closed with a written
  operational recommendation: deploy the per-city router, trust Patna's
  Alerts, do not yet trust Delhi's or Lucknow's, and do not claim
  Alert-tier reliability for the four cities with no testable severe
  days.**
* **Phase 11: Early Warning System — built real warning logic on top of
  Phase 10's already-validated forecasts, entirely in
  `notebooks/phase11_early_warning.ipynb`. No new modeling or data:
  Phase 10's routed test-set predictions were exported to
  `data/processed/phase10_test_predictions/phase10_test_predictions.csv`
  and used as the sole input. Four design questions were settled before
  any code: (1) trigger = category-crossing-into-Alert, reusing Phase
  10's validated tiers rather than a new, unvalidated magnitude
  threshold; (2) trust level per city taken directly from Phase 10's own
  recall table (Patna reliable; Delhi/Lucknow known-unreliable;
  Bengaluru/Chennai/Hyderabad/Mumbai unvalidated — zero real Alert days
  in their test windows, a distinct kind of uncertainty from Delhi/
  Lucknow's proven weakness, given a separate label rather than folded
  together); (3) empirically tested whether Phase 9's anomaly flags
  could corroborate a low-confidence Delhi/Lucknow warning — found
  untestable, not disproven (Delhi had zero anomaly-flagged Alert days
  to test against; Lucknow had exactly one, n=1, not generalizable) — so
  the safeguard became a structural confidence label instead of a
  signal-based check; (4) built notebook → script → real MySQL table
  (Phase 9's pattern), not notebook-only. Added episode detection
  (`is_new_episode`, new Alert onset vs. a continuing one) using a
  city+horizon grouped shift. Caught and fixed two real bugs: a boolean
  dtype coercion (object dtype after `groupby().shift()` on a boolean
  column) that silently made every one of 144 triggered days register as
  a brand-new episode with zero continuations ever — caught because a
  perfect-looking result was investigated rather than trusted, revealing
  110 real continuations once fixed; and a leftover unsafe default-case
  priority-tier function that silently mislabeled 6 genuinely-missing
  Mumbai 3-day predictions as full-confidence "Alert" — caught via
  arithmetic reconciliation (150 vs. an independently-verified 144).
  Built and loaded `fact_early_warnings` (2,115 rows, real FK to
  `dim_city`, unique constraint on city+target_date+horizon), verified
  duplicate-safe by running the loader twice.**

## Current Decisions

* Live ingestion pipeline polls data.gov.in, OpenAQ, and Open-Meteo hourly
  via Windows Task Scheduler, staggered a few minutes apart
* OpenAQ v3 used as backup/cross-validation source — **cannot be directly
  numerically compared to data.gov.in's values** (sub-index vs concentration)
* Open-Meteo weather pulled for all 11 target cities in a single batched
  API call, producing current snapshot and 24h forecast
* Historical model development bootstraps from Kaggle CPCB dataset —
  coverage corrected to 2015-2020
* Kaggle dataset does not include Pune (10 of 11 target metros covered)
* Geospatial analysis remains secondary
* MySQL database `india_air_quality` holds all processed data; sub-index,
  concentration, and historical readings are kept in separate fact tables
* Loader scripts authenticate as a dedicated `aqi_loader` user
  (SELECT/INSERT/UPDATE only)
* `dim_station.city_id` is nullable — OpenAQ stations aren't matched to
  a target city; Kaggle stations DO get a real `city_id`
* Kaggle historical data is in MySQL: `fact_kaggle_historical` (1,140,696
  rows) and `fact_kaggle_daily_aqi` (95,058 rows)
* `dim_station.source_system` ENUM: `('data_gov_in', 'openaq', 'kaggle')`
* `dim_pollutant` has 14 codes, including `Benzene`, `Toluene`, `Xylene`
* Loader scripts are still triggered by hand — not yet automated
* `dim_station` totals 244 rows: ~134 data.gov.in, 20 OpenAQ, 90 Kaggle
* A single Kaggle-sourced station (Maninagar, Ahmedabad — GPCB, source
  key GJ001) has internally inconsistent precomputed AQI values —
  excluded from Phase 8's seasonality comparison, Phase 9's anomaly
  baseline, AND Phase 10's forecasting panel entirely
* Anomaly detection (Phase 9) is built on `fact_kaggle_daily_aqi` only,
  covers 9 of 11 target cities, method: median/MAD per city/month,
  `|modified_z| > 3.5`, 2,002 of 74,826 (2.68%) flagged
* Confirmed real, geographically-coherent AQI seasonality: North Indian
  cities (Delhi, Lucknow, Patna) show a sharp winter peak and monsoon
  trough; South Indian cities (Chennai, Bengaluru, Hyderabad) stay flat
  and low all year; Mumbai shows a real but muted version of the pattern
* Wind speed has a real, direct negative correlation with Delhi's AQI,
  holding within-season; temperature's full-year correlation is
  substantially a seasonal confound (sign reverses within winter alone)
* **New in Phase 10: forecasting scope is 7 of 11 cities** (the 23-station
  stable panel minus GJ001) — Delhi, Mumbai, Bengaluru, Hyderabad,
  Chennai, Lucknow, Patna. Ahmedabad, Jaipur, Kolkata, and Pune are
  out of scope, each for its own already-documented reason.
* **New in Phase 10: Lucknow's data-quality gap is refined from the
  Phase 8 label "March-May 2018" to its verified real boundary,
  2018-02-15 to 2018-06-12 (118 days, one clean contiguous block)** —
  the practical conclusion is unchanged (a real, bounded, explainable
  gap), but the precise window now matters for exclusion logic and
  should be used in place of the coarser original label going forward.
* **New in Phase 10: city-day anomaly exclusion uses a strict-majority
  rule** (more than half of that day's scored stable-panel stations
  independently flagged anomalous by Phase 9) to decide which days to
  exclude from *forecasting training only* — not from the test set, and
  not from the underlying data. A looser "any station flagged" rule was
  tested and rejected: it scales with station count (unfairly penalizing
  Delhi's 10 stations vs. Mumbai's 1) and, at exactly 2 stations,
  mathematically degenerates into "any single station," re-introducing
  the same Chennai/Manali over-flagging problem Phase 9 had already
  solved with a `baseline_note`.
* **New in Phase 10: persistence ("tomorrow = today") is a very strong
  baseline for this data** — it beat a train-only seasonal-median
  baseline by 2-3x in every one of the 7 forecasting cities, confirming
  strong day-to-day AQI autocorrelation and setting the real bar for
  any model in this phase.
* **New in Phase 10: per-city Ridge regression (Fourier + lag + rolling
  features, alpha tuned via inner chronological validation) beats
  persistence in Bengaluru, Lucknow, and Patna; ties in Chennai; loses
  in Delhi, Hyderabad, and Mumbai** — losses concentrated exactly where
  1-day persistence was already strongest (highest autocorrelation,
  least residual variance for engineered features to explain). This is
  a genuine, alpha-tuning-confirmed negative result for those three
  cities, not an unoptimized model.
* **New in Phase 10: the per-city best-model routing decision is
  identical at both 1-day and 3-day horizons** — a stable, simple
  operational rule (Ridge for Bengaluru/Chennai/Lucknow/Patna,
  persistence for Delhi/Hyderabad/Mumbai) that doesn't need to change
  based on forecast distance. Ridge's relative advantage over persistence
  widens at 3-day in every city where it already won at 1-day.
* **New in Phase 10: optimal Ridge regularization depends on forecast
  horizon, not just city** — Delhi and Hyderabad wanted near-zero
  regularization at 1-day but the maximum tested value at 3-day, since
  `lag_1`'s predictive power weakens over a longer horizon, making
  lightly-regularized coefficients more prone to overfitting noise.
* **New in Phase 10: AQI forecasts were translated into a 3-tier
  priority system (Low/Watch/Alert) mapped from India's 6-band AQI
  scale.** Band-distance analysis across all 1,074 test-set predictions
  found no miss ever exceeded 2 categories, and only 6 exceeded 1 —
  the model is never wildly wrong when it errs.
* **New in Phase 10, the most important operational finding: Alert-tier
  (severe-day) precision/recall varies enormously by city and is NOT
  predictable from RMSE alone.** 4 of 7 cities (Bengaluru, Chennai,
  Hyderabad, Mumbai) had zero genuinely severe days in the entire 2020
  test window — Alert-tier reliability is simply untested there, not
  confirmed either way. Of the 3 testable cities: **Patna's forecast is
  reliable** (84.2% recall at 1-day, improving to 96.8% at 3-day).
  **Delhi and Lucknow are not** — Delhi's recall drops from 68.0% (1-day)
  to 40.9% (3-day); Lucknow's drops from 38.5% to 18.2%. Both looked
  only moderately worse than average on RMSE alone — this gap was only
  visible after building the category/tier translation layer.
* **New in Phase 10: a silent default-case bug was found and fixed in
  the Alert-tier evaluation code** — raw AQI values were passed where
  category labels were expected, causing every test day to fall through
  to the function's `else` branch and be mislabeled "Alert," producing
  an impossible 100% recall in every city. Caught because a perfect
  score on something known to be rare (~7% of days) was itself the red
  flag — same discipline as Phase 6's "0% suspicious" investigation, and
  the same bug class as Phase 7's NULL→"Severe" DAX/SQL mislabeling.
* **Forecasting is analysis/notebook-only, not productionized** — no
  script, no loader, no database table was built for Phase 10's
  forecasts (unlike Phase 9's anomaly flags), and no automated scheduling
  exists. This is a deliberate scope decision, consistent with treating
  Phase 10 as a data-analysis deliverable rather than an ML-engineering
  build-out.
* **New in Phase 11: warning trigger = category-crossing-into-Alert
  only** (Very Poor/Severe on India's 6-band scale), reusing Phase 10's
  already-validated tier logic. A second, magnitude-of-jump trigger was
  considered and rejected as unvalidated new machinery for no
  demonstrated benefit, given Phase 10 already proved no test-set
  prediction ever missed its true category by more than 2 bands.
* **New in Phase 11: three-tier reliability labeling, not a single
  confidence flag** — `reliable` (Patna, full-confidence "Alert"),
  `known_unreliable` (Delhi, Lucknow — proven weak recall, displayed as
  "Alert — Low Confidence (Recommend Review)"), and `unvalidated`
  (Bengaluru, Chennai, Hyderabad, Mumbai — zero real Alert days in their
  2020 test windows, displayed as "Alert — Unvalidated"). These are
  deliberately two different labels, not one generic low-confidence
  bucket, since "proven weak" and "never tested" are different kinds of
  uncertainty that shouldn't be blurred together.
* **New in Phase 11: Phase 9 anomaly-flag corroboration for Delhi/
  Lucknow was tested empirically and found untestable with available
  data, not proven or disproven** — Delhi had zero anomaly-flagged Alert
  days in its test window; Lucknow had exactly one (not a generalizable
  sample). The safeguard for these two cities is therefore a structural
  confidence label, not a signal-based corroboration check.
* **New in Phase 11: episode detection** (`is_new_episode`) distinguishes
  a new Alert onset from a continuing one, using a city+horizon grouped
  shift on the trigger column. 110 real continuations exist across the
  144 total triggered predictions (concentrated in Patna, which shows
  long sustained severe-pollution runs — only 6 distinct onsets produced
  38 triggered days at 1-day horizon).
* **New in Phase 11: `fact_early_warnings` is built and loaded** — 2,115
  rows, real FK to `dim_city`, unique constraint on
  (city_id, target_date, horizon), verified duplicate-safe by running
  the loader twice (2nd run: 0 inserted, 2,115 skipped as duplicates).
  `warning_label` is genuinely NULL for 6 rows (a known Mumbai 3-day
  prediction gap) rather than fabricated — consistent with this
  project's flag-don't-drop principle throughout.
* **New in Phase 11: this phase uses Phase 10's 2020 historical test
  window only — no live scoring, no automated scheduling, and no
  notification mechanism were built.** `fact_early_warnings` is a
  queryable backtest record, not a live-firing alert system. This is a
  deliberate scope decision consistent with Phase 9 and 10's identical
  deferral of live-source scoring until sufficient hourly history
  accumulates.

## Selected Data Sources

* **Primary:** data.gov.in CPCB Real-Time AQI API — tested, working,
  scheduled hourly, cleaned, loaded
* **Secondary/backup:** OpenAQ v3 API — tested, working, scheduled hourly,
  cleaned, loaded
* **Supporting:** Open-Meteo (weather) — tested, working, scheduled hourly,
  cleaned, loaded (live/forecast); historical Archive API used for
  Phase 8 analysis only, not yet part of the automated pipeline
* **Supporting:** Kaggle CPCB historical dataset — cleaned, loaded,
  the sole source for Phase 9's anomaly baseline AND Phase 10's
  forecasting panel (7 of 11 target cities after Phase 10's own
  exclusions)
* **Optional/manual:** CPCB CCR portal — deferred

## Visualization Layer

* **Power BI Desktop**, 4-page dashboard: Overview, Data Quality &
  Coverage, Live Snapshot, Alerts
* Publishing to Power BI Service / public web: status unchanged since
  Phase 7 — still open, not blocking Phase 10 or 11

## Analysis Layer

* **Jupyter Lab notebook (Phase 8):** `notebooks/phase8_eda_time_series.ipynb`
* **Jupyter Lab notebook (Phase 9):** `notebooks/phase9_anomaly_detection.ipynb`
* **Jupyter Lab notebook (Phase 10):** `notebooks/phase10_forecasting.ipynb`
  — rebuilds and independently re-verifies the stable panel and known
  gaps directly from MySQL; builds persistence/seasonal-median baselines;
  engineers Fourier/lag/rolling features with hand-verified no-leakage
  checks; fits and alpha-tunes per-city Ridge models at 1-day and 3-day
  horizons; builds the AQI-category/priority-tier translation layer;
  evaluates Alert-tier precision/recall by city and horizon
* All three connect directly to MySQL via SQLAlchemy + `mysql-connector-python`,
  using the existing `aqi_loader` least-privilege credentials

## Anomaly Detection Layer (Phase 9)

* Method: per-city, per-calendar-month median/MAD baseline, modified
  z-score, flagged at `|z| > 3.5`
* Scope: `fact_kaggle_daily_aqi` only, 9 of 11 target cities
* Result: 2,002 of 74,826 readings flagged (2.68%)
* Real table: `fact_kaggle_anomaly_flags` (74,826 rows, verified,
  duplicate-safe)

## Forecasting Layer (New — Phase 10)

* **Scope:** 7 of 11 target cities (23-station stable panel minus
  Ahmedabad's GJ001) — Delhi, Mumbai, Bengaluru, Hyderabad, Chennai,
  Lucknow, Patna
* **Horizons:** 1-day and 3-day ahead (7-day deliberately out of scope —
  would further shrink an already-short 183-day test window)
* **Baselines:** persistence ("tomorrow = today") and a train-only
  seasonal median per city/month; persistence beat seasonal-median 2-3x
  everywhere
* **Model:** per-city Ridge regression (3 Fourier harmonics + lag_1/lag_7
  + 7-day/30-day rolling means), alpha tuned via inner chronological
  validation (never touching the real test set)
* **Routing rule (stable across both horizons):** Ridge for Bengaluru,
  Chennai, Lucknow, Patna; persistence for Delhi, Hyderabad, Mumbai
* **Risk translation:** 6-band Indian AQI category → 3-tier priority
  (Low/Watch/Alert); no test-set prediction ever missed by more than 2
  categories
* **Alert-tier reliability (the headline result):** untestable in 4 of 7
  cities (zero real severe days in the 2020 test window); reliable in
  Patna (84-97% recall); unreliable and worsening with horizon in Delhi
  (68%→41% recall) and Lucknow (38.5%→18.2% recall)
* **Not built:** no forecasting script, no loader, no new database table,
  no scheduling — analysis/notebook-only by deliberate scope decision

## Planned Technologies

* Python, Pandas, NumPy, scikit-learn (new in Phase 10, for Ridge
  regression and evaluation metrics)
* statsmodels — `seasonal_decompose` (Phase 8)
* Windows Task Scheduler — hourly automated polling of all three live
  sources
* MySQL — relational storage for all four data sources plus derived
  anomaly flags
* Power BI + DAX — 4-page analytics dashboard
* Git/GitHub — local repo tracking all phase changes; pushed to a
  public remote repository

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
                                                                              dim_station (244)                  fact_openaq_concentration,
                                                                                                                 fact_weather_observations,
                                                                                                                 fact_weather_forecast,
                                                                                                                 fact_kaggle_historical (1,140,696 rows),
                                                                                                                 fact_kaggle_daily_aqi (95,058 rows)
                                                                                                                          │
                                                                          ┌───────────────────────────────┬─────────────┼───────────────────────────────┐
                                                                          ▼                               ▼             ▼                               ▼
                                                          Power BI Dashboard (verified)     Jupyter EDA (Phase 8)  fact_kaggle_anomaly_flags     Jupyter Forecasting (Phase 10)
                                                                          │                                        (74,826 rows, Phase 9)          (notebook-only, not in MySQL)
                                                                          ▼                                                                                │
                                                              Publish to web (in progress)                                                    Per-city router: Ridge (4 cities)
                                                              + GitHub repo (public)                                                           vs persistence (3 cities)
                                                                                                                                                            │
                                                                                                                                                            ▼
                                                                                                                                        AQI category + Low/Watch/Alert tiers
                                                                                                                                        (reliable: Patna; unreliable: Delhi,
                                                                                                                                         Lucknow; untested: 4 other cities)
                                                                                                                                                            │
                                                                                                                                                            ▼
                                                                                                                                        Phase 11: fact_early_warnings
                                                                                                                                        (2,115 rows — trigger + reliability
                                                                                                                                         tier + episode detection, MySQL)
```

## Project Structure (as built)

```
india-air-quality-intel/
├── venv/                                      (not committed)
├── data/                                      (not committed)
├── config/config.py
├── src/utils/{secrets_loader,logger,db_connector}.py
├── src/ingestion/                              (4 scripts, all WORKING)
├── src/processing/                             (5 cleaning/analysis scripts, all WORKING)
├── src/monitoring/check_pipeline_health.py
├── src/loading/                                (6 loader scripts, all WORKING)
├── scripts/                                    (3 Task Scheduler .bat launchers)
├── sql/create_schema.sql                       (rebuildable from scratch — verified against
│                                                 a fresh throwaway database this session;
│                                                 includes fact_kaggle_anomaly_flags and
│                                                 fact_early_warnings, and the NO/NOX seed
│                                                 rows that had been missing since Phase 5)
├── sql/analysis.sql                            (7 committed analytical queries, Phase 5 —
│                                                 Q5's city-only join corrected this session
│                                                 to match on the same hour, not just city)
├── sql/create_loader_user.sql                  (git-ignored, has password)
├── sql/create_loader_user.template.sql         (sanitized, committed)
├── notebooks/phase8_eda_time_series.ipynb
├── notebooks/phase9_anomaly_detection.ipynb
├── notebooks/phase10_forecasting.ipynb
├── notebooks/phase11_early_warning.ipynb
├── src/loading/load_early_warnings.py
├── src/loading/load_kaggle_anomalies.py
├── src/processing/detect_anomalies_kaggle.py
├── docs/DATA_SOURCES_LOG.md
├── dashboard/India Urban Air Quality Intelligence & Early-Warning System.pbix
│                                                (corrected this session — the real folder
│                                                 name has always been dashboard/, not
│                                                 powerbi/ as previously documented; the
│                                                 .pbix filename was also missing its
│                                                 leading "I", fixed this session)
├── requirements.txt
├── README.md
└── .gitignore
```

**Git-ignored, kept locally only (not in the public repo) — a deliberate
decision made during post-Phase-11 housekeeping, not an oversight:**
- `files/PHASE1_*.md` through `files/PHASE11_*.md` — written in an
  interview-prep style (30-second summaries, "Interview Q&A" sections)
  not intended for public/professional viewing. `files/PROJECT_STATE.md`
  is unaffected and remains committed — it reads as a real engineering
  log, not prep notes.
- `inspect_kaggle.py` — the one-time, throwaway inspection script
  described in `PHASE6_KAGGLE_HISTORICAL_LOADING.md`; superseded by the
  real `clean_kaggle.py` pipeline.
- `sql/anomalies.sql` — an earlier, slightly different draft of
  `fact_kaggle_anomaly_flags`'s `CREATE TABLE` statement plus two
  one-time build-verification queries. Redundant with (and a drift risk
  against) the authoritative version now in `sql/create_schema.sql`.

**Schema file housekeeping fully closed this session:** both
`fact_kaggle_anomaly_flags` (Phase 9) and `fact_early_warnings`
(Phase 11) are now in `sql/create_schema.sql`, pulled directly from the
live database via `mysqldump` rather than retyped from documentation.
The file was also found to be missing the `NO`/`NOX` pollutant seed
rows (live in the database since Phase 5, never previously added to
this file) and ~110 lines of interspersed ad-hoc verification queries
that didn't belong in a from-scratch schema file — both fixed. Verified
by rebuilding the entire schema into a throwaway test database and
confirming 11 tables and 14 correctly-ordered pollutant codes.

## Next Phase

**Phase 12 — candidate directions, not yet chosen.** The user's original
roadmap (EDA → Anomaly Detection → Forecasting → Early Warning System)
is now complete end-to-end. Realistic next directions, none yet decided:

- **Live scoring:** extend `fact_early_warnings`-style logic to the live
  hourly sources (data.gov.in/OpenAQ) now that automated polling has been
  running since Phase 3 — deferred repeatedly through Phases 9-11
  pending sufficient live history; worth re-assessing how much has now
  accumulated.
- **Notification layer:** `fact_early_warnings` is currently a queryable
  backtest record, not a live-firing system — adding an actual
  notification mechanism (email, dashboard push) is a natural, currently
  unbuilt extension.
- **A real structural safeguard for Delhi/Lucknow** beyond the confidence
  label — e.g. a second corroborating model, or wider uncertainty bands
  — since Phase 11 found anomaly-flag corroboration untestable rather
  than adopting a real fix.
- **Automating the still-manual loaders** via Task Scheduler — deferred
  since Phase 7, still open.
- **Publishing the Power BI dashboard to the web** — deferred since
  Phase 7, still open, and could now incorporate `fact_early_warnings`
  as a fifth page.
- Small housekeeping carried forward: `sql/create_schema.sql` still needs
  both `fact_kaggle_anomaly_flags` (Phase 9) and `fact_early_warnings`
  (Phase 11) appended — not a blocker to any of the above.

## Exact Next Step

Decide which Phase 12 direction to pursue — likely live scoring or the
notification layer, since both build most directly on Phase 11's
completed warning logic rather than opening a new, separate track of
work.
