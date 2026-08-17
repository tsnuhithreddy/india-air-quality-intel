# Project State

**Project Name:** India Urban Air Quality Intelligence & Early-Warning System

**Current Phase:** Phase 1 Complete → Ready for Phase 2

---

## Completed Work
- Investigated and validated all candidate data sources (CPCB/data.gov.in, OpenAQ, CPCB CCR, Kaggle historical, Open-Meteo, WAQI)
- Verified live API schema, auth requirements, and field structure for the primary source
- Identified key data-quality risks (station outages, sentinel error values, unit inconsistency)
- Confirmed feasibility of anomaly detection and short-term forecasting given available data
- Finalized data architecture and documented in `PHASE1_DATA_SOURCE_VALIDATION.md`

## Current Decisions
- Live ingestion pipeline will poll the primary source hourly, starting from Phase 2 onward
- Historical model development will bootstrap from the Kaggle CPCB dataset rather than waiting for self-collected data to accumulate
- Geospatial analysis will remain a secondary feature, not a core deliverable
- Population/exposure data will use a static, manually curated reference table (low priority, revisit later)

## Selected Data Sources
- **Primary:** data.gov.in CPCB Real-Time AQI API
- **Secondary/backup:** OpenAQ v3 API
- **Supporting:** Open-Meteo (weather), Kaggle CPCB historical dataset (2015–2024)
- **Optional/manual:** CPCB CCR portal (fine-grained historical backfill only)

## Planned Technologies
- Python, Pandas, NumPy (data collection, cleaning, transformation)
- Google Colab (development environment)
- MySQL (curated data storage)
- Advanced SQL (analysis layer)
- Power BI + DAX (reporting/dashboarding)
- Git/GitHub (version control)
- New for this project: API-based ingestion, scheduling/automation, time-series analysis, anomaly detection, short-term forecasting, exposure/prioritization scoring, explainable alerting, geospatial analysis (secondary)

## Current Architecture
```
[data.gov.in API]  ──hourly poll──┐
[Open-Meteo API]   ──hourly poll──┼──> Raw landing zone ──> Validation/QA layer ──> MySQL (curated) ──> Analysis/ML layer
[OpenAQ API]        ──periodic────┘                                                       │
[Kaggle historical] ──one-time load────────────────────────────────────────────────────┘
```

## Important Assumptions
- Initial geographic scope limited to 10–12 major metro areas (not all-India)
- Primary API's hourly refresh cadence is sufficient — no need for sub-hourly polling
- Kaggle historical dataset is representative enough for initial model training/validation
- Free-tier API limits (data.gov.in, OpenAQ, Open-Meteo) are sufficient for project scale

## Known Limitations / Issues
- Primary source has no historical endpoint — historical depth depends entirely on Kaggle bootstrap + self-collected data going forward
- OpenAQ India historical data has a coverage gap (pre-2025) — not usable as sole ground truth
- Station-level outages (e.g., contractor lapses) can silently break data continuity for entire states
- Units are inconsistent across pollutants and must be standardized during cleaning
- Station density is uneven across cities — cross-city comparisons need normalization, not raw values

## Files Created So Far
- `PHASE1_DATA_SOURCE_VALIDATION.md`
- `PROJECT_STATE.md`

## Next Phase
**Phase 2 — Environment & Ingestion Setup** (not started)

## Exact Next Step
Design and build the automated data ingestion pipeline: obtain API keys (data.gov.in, OpenAQ), set up the Colab/Python environment, and write the first working script to pull and store one hourly snapshot from the primary source before adding scheduling.
