# Urban Air Quality Intelligence & Early Warning System

An end-to-end data engineering and analytics project for collecting, cleaning, storing, analyzing, and forecasting urban air-quality data across major Indian cities.

## Project Status

✅ **Core pipeline, analytics, and early-warning layers complete** 

Ingestion, cleaning, and MySQL storage are built and automated for all four data sources. Exploratory analysis, anomaly detection, short-term forecasting, and a rule-based early-warning system have all been built, verified against real data, and are documented below. Automated loading, live-source scoring, and web-published dashboarding remain open extensions (see Roadmap).

## Objective

The project builds a reliable air-quality intelligence pipeline that:

- Collects near-real-time air-quality observations from public data sources.
- Builds a structured historical dataset through scheduled ingestion.
- Cleans and standardizes observations from different sources.
- Stores processed data in a relational MySQL database.
- Identifies unusual air-quality conditions and potential pollution events.
- Forecasts short-term air-quality trends (1-day and 3-day ahead).
- Translates forecasts into an early-warning system with city-specific reliability labeling.
- Provides an analytical Power BI dashboard for monitoring cities and stations.

## Data Sources

### Primary — data.gov.in / CPCB

The primary source is the CPCB real-time air-quality API available through data.gov.in. It provides current observations from monitoring stations across India, polled hourly via an automated scheduled task. Its values are AQI sub-index scores (0–500 health-severity scale), not raw pollutant concentrations — kept in a physically separate database table from OpenAQ's real concentration readings so the two are never confused.

### OpenAQ

OpenAQ v3 is used as a secondary source for air-quality observations and cross-validation, also polled hourly. Its historical coverage for Indian locations has a known multi-year gap, so it's treated as a supporting/backup source rather than a historical ground truth.

### Open-Meteo

Open-Meteo provides supporting meteorological information, pulled hourly for live/forecast data and separately via its Archive API for historical analysis. Confirmed to have a real, direct relationship with AQI (wind speed) alongside a partly confounded one (temperature — its strong full-year correlation is substantially seasonal).

### Kaggle Historical Dataset

A historical Kaggle dataset (2015–2020, verified — not the originally assumed 2015–2024) bootstraps historical analysis, anomaly detection, and forecasting, while the live ingestion pipeline continues collecting new observations. Covers 10 of 11 target cities (Pune has no historical bootstrap).

## Cities in Scope

The initial monitoring scope includes major Indian cities: Delhi, Mumbai, Bengaluru, Hyderabad, Chennai, Kolkata, Pune, Ahmedabad, Lucknow, Jaipur, and Patna.

Downstream analysis layers each work from a validated subset of these 11, for documented, source-specific reasons — e.g. forecasting and the early-warning system operate on 7 cities (a "stable panel" of stations with 6 full years of Kaggle history), excluding Ahmedabad (one known-inconsistent station), Jaipur/Kolkata (no stable-panel stations), and Pune (no Kaggle data at all).

## Architecture

```text
[data.gov.in API]  ──hourly poll (automated)──┐
[Open-Meteo API]   ──hourly poll (automated)──┼──> Raw JSON ──> Cleaning (CSV) ──> Python Loaders ──┐
[OpenAQ API]        ──hourly poll (automated)─┘                                                      │
[Kaggle historical] ──clean_kaggle.py──> 2 CSVs ──> load_kaggle.py ─────────────────────────────────┤
                                                                                                       ▼
                                                                                          MySQL: india_air_quality
                                                                                    (3 dimension + 8 fact tables)
                                                                                                       │
                                                        ┌──────────────────┬──────────────────────────┼──────────────────────────┐
                                                        ▼                  ▼                          ▼                          ▼
                                                  Power BI Dashboard   Jupyter EDA          Anomaly Detection          Forecasting + Early Warning
                                                  (4 pages)            (seasonality,        (median/MAD per city/     (Ridge/persistence router,
                                                                        weather effects)     month, 2.68% flagged)     fact_early_warnings)
```

## Technology Stack

- **Language:** Python
- **Database:** MySQL
- **Data & Analysis:** Pandas, NumPy, scikit-learn, statsmodels
- **Visualization:** Matplotlib, Seaborn
- **BI:** Power BI
- **APIs:** data.gov.in/CPCB, OpenAQ, Open-Meteo
- **Automation:** Windows Task Scheduler
- **Version Control:** Git & GitHub

## Repository Structure

```text
india-air-quality-intel/
├── config/              # Project configuration
├── data/                # Local raw, processed, and external data (not committed)
├── dashboard/           # Power BI (.pbix) dashboard file
├── docs/                # Data source log and other project documentation
├── files/               # Project state tracking (phase-by-phase working notes kept locally)
├── logs/                # Local pipeline logs
├── notebooks/           # EDA, anomaly detection, forecasting, and early-warning notebooks
├── scripts/             # Task Scheduler launcher scripts
├── sql/                 # Database schema and committed analytical queries
├── src/
│   ├── ingestion/       # API and historical-data ingestion
│   ├── loading/         # Database loading modules (one per source, plus anomaly/warning loaders)
│   ├── monitoring/      # Pipeline health checks
│   ├── processing/      # Data cleaning, anomaly detection, and transformation
│   └── utils/           # Shared utilities (secrets, logging, DB connection)
├── .gitignore
├── requirements.txt
└── README.md
```

## Key Design Decisions

- **Scheduled ingestion:** builds historical data from live sources that don't expose the required historical records directly.
- **Source separation:** observations from different providers retain their source-specific meaning — sub-index scores and physical concentrations are never merged into one column.
- **Relational storage:** MySQL provides structured dimensions, facts, keys, and constraints for downstream analysis, with a real least-privilege database user for all loaders.
- **Flag, don't drop:** bad or missing values get boolean flag columns rather than being deleted, preserving the ability to make an informed decision downstream.
- **Validation before analysis:** every real finding in this project — a date-range correction, a data-quality gap, a model result — was checked against real evidence before being trusted, not assumed from documentation or a clean-looking output.
- **Robust statistics over classical decomposition for anomaly detection:** median/MAD per city per calendar month, chosen specifically to avoid distortion from a single already-known bad station and to handle real data gaps without added complexity.
- **Baselines before models:** a naive "tomorrow = today" forecast was proven surprisingly strong before any regression model was built, setting a real, honest bar to beat rather than reporting model accuracy in isolation.
- **Explicit reliability labeling in the early-warning layer:** forecast trust level is reported per city, based on real backtested recall — not presented as uniformly confident across cities with very different amounts of supporting evidence.

## Development Roadmap

- [x] Validate available data sources
- [x] Set up local Python environment and configuration
- [x] Implement live-source ingestion (data.gov.in) with automated scheduling
- [x] Add supporting API ingestion (OpenAQ, Open-Meteo) with automated scheduling
- [x] Build data-cleaning pipelines for all four sources
- [x] Design and build the MySQL relational schema
- [x] Load and verify historical Kaggle data (1.14M+ rows)
- [x] Build the Power BI analytics dashboard
- [x] Exploratory data analysis & time-series analysis
- [x] Build and load a seasonal-baseline anomaly detector
- [x] Build and evaluate short-term (1-day/3-day) AQI forecasting
- [x] Build and load an early-warning system on top of validated forecasts
- [ ] Automate the still-manual database loaders via Task Scheduler
- [ ] Extend anomaly/warning scoring to live hourly sources
- [ ] Add a real notification mechanism (the warning table is currently a queryable backtest record, not a live-firing system)
- [ ] Publish the Power BI dashboard to the web

## Important Note on Data

Raw and processed datasets are intentionally excluded from version control. API credentials and other secrets are also kept outside the repository.

## Current Direction

With the original roadmap (EDA → Anomaly Detection → Forecasting → Early Warning System) complete end-to-end, the project's next phase is not yet fixed — realistic candidates include live-source scoring, a real notification layer on top of the existing warning table, loader automation, and dashboard publishing. See `files/PROJECT_STATE.md` for the full, current decision log.

---
