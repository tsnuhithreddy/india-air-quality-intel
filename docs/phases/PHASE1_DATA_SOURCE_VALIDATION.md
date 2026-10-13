# Phase 1 — Data Source Validation
**Project:** India Urban Air Quality Intelligence & Early-Warning System
**Status:** Approved — Phase 1 Complete

---

## Primary Data Source
**data.gov.in — "Real Time Air Quality Index from various locations" (CPCB)**
- Resource ID: `3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69`
- Official Government of India source (Central Pollution Control Board)
- Free API key via self-serve signup
- Live/current data only — **no historical query capability**

## Secondary / Backup Data Source
**OpenAQ v3 API**
- Requires free API key (Bearer/X-API-Key)
- Aggregates CPCB data globally; used for cross-validation and fallback if a station goes dark
- ⚠️ India's historical coverage has a known gap — CPCB's feed to OpenAQ was disrupted and only fully recovered in 2025. Do not treat OpenAQ as a reliable standalone historical source for India.

## Supporting Data Sources
- **Open-Meteo API** — weather/meteorological context (no key required, free, historical back to 1940, 16-day forecast)
- **Kaggle "Air Quality Data in India" (CPCB-sourced, 2015–2024)** — one-time historical bootstrap dataset, not live
- **CPCB CCR Portal (app.cpcbccr.com)** — manual-only historical backfill for specific stations, no stable API, not automated
- **Population/city reference table** — static, manually curated from Census of India 2011; optional, only if exposure scoring is retained

---

## Available Pollutants
PM2.5, PM10, SO2, NO2, CO, O3, NH3, Pb (availability varies by station instrumentation)

## Geographic Coverage
All CPCB-linked stations across India; uneven density (Delhi-NCR dense, smaller cities sparse).
**Recommended initial scope:** 10–12 major metros — Delhi-NCR, Mumbai, Bengaluru, Hyderabad, Chennai, Kolkata, Pune, Ahmedabad, Lucknow, Jaipur, Patna.

## Historical Data Availability
- Primary live API: **none** (current snapshot only)
- Kaggle dataset: **yes**, 2015–2024, hourly/daily, 26+ cities
- CPCB CCR portal: yes, deep archive, but manual extraction only

## Current/Live Data Availability
Yes — primary source (data.gov.in) is genuinely live, hourly-refreshed.

## Update Frequency
Hourly (matches CPCB's own station reporting cadence)

## API / Access Requirements
| Source | Auth | Cost |
|---|---|---|
| data.gov.in | Free API key | Free |
| OpenAQ v3 | Free API key | Free tier |
| Open-Meteo | None | Free (≤10,000 calls/day) |
| Kaggle | Account login for download | Free |
| CPCB CCR | Manual portal, no API | Free |

---

## Important Limitations
- Primary source has **no historical endpoint** — own historical dataset must be built via scheduled polling
- Units are inconsistent across pollutants (µg/m³ for most; mg/m³ for CO) — must standardize during cleaning
- CPCB CCR historical downloads are capped (~1 week of 15-min data per station per pollutant per request)
- OpenAQ India historical data has a multi-year gap (pre-2025 recovery) — not safe as sole ground truth

## Data-Quality Risks
1. Entire states/stations can go dark for months (e.g., confirmed real case: Haryana's CAAQMS network offline due to lapsed monitoring contract)
2. Sentinel/error values in raw readings (0s, negative numbers, 999s)
3. Uneven station density across cities — raw comparisons are not fair without normalization
4. Live-source outages require fallback logic (OpenAQ/WAQI cross-check)

## Feasibility Assessment
- **Anomaly detection:** ✅ Feasible — hourly time-series with sufficient historical (Kaggle) + growing live data supports statistical and ML-based anomaly detection
- **Short-term forecasting:** ✅ Feasible — historical bootstrap + weather covariates support short-horizon (24–72 hr) forecasting models

---

## Final Recommended Data Architecture
```
[data.gov.in API]  ──hourly poll──┐
[Open-Meteo API]   ──hourly poll──┼──> Raw landing zone ──> Validation/QA layer ──> MySQL (curated) ──> Analysis/ML layer
[OpenAQ API]        ──periodic────┘                                                       │
[Kaggle historical] ──one-time load────────────────────────────────────────────────────┘
```

## Changes to Original Project Scope
1. **Automated/scheduled ingestion is more central than originally planned** — since the primary live source has no historical query capability, the scheduler is the only path to a genuinely proprietary, growing dataset (not just a nice-to-have).
2. **Geospatial analysis remains secondary, not core** — station density is too uneven across cities for strong spatial-interpolation claims; kept as a supporting feature with explicit caveats.
3. All other planned capabilities (anomaly detection, forecasting, exposure/prioritization scoring, explainable alerts) remain fully supported — no reduction in scope.

---

## Official Source References
- CPCB Real-Time AQI (data.gov.in): https://www.data.gov.in/resource/real-time-air-quality-index-various-locations
- CPCB official site: https://cpcb.nic.in/
- CPCB CCR historical portal: https://app.cpcbccr.com/ccr/
- OpenAQ docs: https://docs.openaq.org/
- Open-Meteo docs: https://open-meteo.com/
- Kaggle — Air Quality Data in India: https://www.kaggle.com/datasets/rohanrao/air-quality-data-in-india
