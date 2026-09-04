# Urban Air Quality Intelligence & Early Warning System

An end-to-end data engineering and analytics project for collecting, cleaning, storing, and analyzing urban air-quality data across major Indian cities.

## Project Status

🚧 **In development**

The core ingestion, processing, database, and historical-data components are being developed and validated. The analytics, anomaly-detection, forecasting, and dashboard layers are still under development.

## Objective

The project aims to build a reliable air-quality intelligence pipeline that can:

- Collect near-real-time air-quality observations from public data sources.
- Build a structured historical dataset through scheduled ingestion.
- Clean and standardize observations from different sources.
- Store processed data in a relational MySQL database.
- Identify unusual air-quality conditions and potential pollution events.
- Support short-term air-quality trend analysis and forecasting.
- Provide an analytical dashboard for monitoring cities and stations.

## Data Sources

### Primary — data.gov.in / CPCB

The primary source is the CPCB real-time air-quality API available through data.gov.in. It provides current observations from monitoring stations across India.

Because the primary API does not provide a convenient historical query interface for this project, scheduled collection is used to build a local historical record over time.

### OpenAQ

OpenAQ v3 is used as a secondary source for air-quality observations and cross-validation. Its historical coverage for Indian locations is not assumed to be complete, so it is treated as a supporting source rather than a replacement for the primary dataset.

### Open-Meteo

Open-Meteo provides supporting meteorological information that can later be used to investigate relationships between weather conditions and air quality.

### Kaggle Historical Dataset

A historical Kaggle dataset covering earlier years is used to bootstrap historical analysis while the live ingestion pipeline continues collecting new observations.

## Cities in Scope

The initial monitoring scope includes major Indian cities such as Delhi, Mumbai, Bengaluru, Hyderabad, Chennai, Kolkata, Pune, Ahmedabad, Lucknow, Jaipur, and Patna.

The city list may evolve as source coverage and project requirements are validated.

## Architecture

```text
Public APIs / Historical Dataset
            │
            ▼
       Data Ingestion
            │
            ▼
        Raw Storage
            │
            ▼
     Data Cleaning &
       Standardization
            │
            ▼
       MySQL Database
            │
       ┌────┴────┐
       ▼         ▼
   Analytics   Monitoring
       │         │
       └────┬────┘
            ▼
     Dashboard / Insights
```

## Technology Stack

- **Language:** Python
- **Database:** MySQL
- **Analytics:** Pandas, NumPy
- **Visualization:** Matplotlib, Seaborn
- **BI:** Power BI
- **APIs:** data.gov.in/CPCB, OpenAQ, Open-Meteo
- **Automation:** Windows Task Scheduler
- **Version Control:** Git & GitHub

## Repository Structure

```text
india-air-quality-intel/
├── config/              # Project configuration
├── data/                # Local raw, processed, and external data
├── docs/                # Project documentation
├── files/               # Supporting project files
├── logs/                # Local pipeline logs
├── notebooks/           # Exploratory analysis and experiments
├── scripts/             # Pipeline launcher scripts
├── sql/                 # Database schema and SQL scripts
├── src/
│   ├── ingestion/       # API and historical-data ingestion
│   ├── loading/         # Database loading modules
│   ├── monitoring/      # Pipeline health checks
│   ├── processing/      # Data cleaning and transformation
│   └── utils/            # Shared utilities
├── .gitignore
├── requirements.txt
└── README.md
```

## Key Design Decisions

- **Scheduled ingestion:** used to build historical data from live sources that do not expose the required historical records directly.
- **Source separation:** observations from different providers retain their source-specific meaning instead of being treated as interchangeable measurements.
- **Relational storage:** MySQL is used to provide structured dimensions, facts, keys, and constraints for downstream analysis.
- **Raw-to-processed workflow:** raw API responses are kept separate from cleaned analytical data during local development.
- **Validation before analysis:** data-quality checks are performed before relying on derived statistics or dashboard metrics.

## Current Development Roadmap

- [x] Validate available data sources
- [x] Set up local Python environment and configuration
- [x] Implement live-source ingestion
- [x] Add supporting API ingestion
- [x] Build data-cleaning pipelines
- [x] Design MySQL relational schema
- [x] Load initial historical data
- [ ] Expand and validate the historical dataset
- [ ] Build anomaly-detection logic
- [ ] Develop short-term forecasting
- [ ] Complete analytical SQL layer
- [ ] Finalize Power BI dashboard
- [ ] Add production-oriented monitoring and documentation
- [ ] Perform end-to-end validation

## Important Note on Data

Raw and processed datasets are intentionally excluded from version control. API credentials and other secrets are also kept outside the repository.

## Future Direction

The final system is intended to move beyond descriptive reporting toward an early-warning workflow: continuously ingest new observations, detect abnormal pollution conditions, combine air-quality and weather signals, and surface actionable alerts through the analytical layer.

---

**Status:** Work in progress · Built as an end-to-end data engineering and analytics portfolio project
