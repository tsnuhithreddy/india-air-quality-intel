# Phase 7 — Power BI Analytics Dashboard

**Project:** India Urban Air Quality Intelligence & Early-Warning System
**Status:** Complete (4-page dashboard)

---

## 1. Objective

Phases 1–6 produced a populated MySQL database (`india_air_quality`) containing four data sources, but the data could only be inspected through SQL. Phase 7 builds an interactive analytics layer on top of that database: a four-page Power BI dashboard covering headline metrics and historical trends, data quality and coverage, a live geographic snapshot, and an alert view for readings above a severity threshold.

Automating the cleaning and loading scripts was considered as the alternative direction for this phase and deferred. The dashboard was prioritised because it exercises new skills (analytical modelling, DAX, report design) and produces a result that can be viewed directly.

## 2. Deliverables

| Artifact | Description |
|---|---|
| `powerbi/india_air_quality_dashboard.pbix` | 4-page Power BI report |
| `powerbi/AQI_Dashboard_Theme.json` | Custom report theme (palette, typography, visual styling) |
| `files/PHASE7_POWERBI_DASHBOARD.md` | This document |

## 3. Data Model

### 3.1 Source tables

All nine tables were imported from MySQL in Import mode through MySQL Connector/NET, using the least-privilege `aqi_loader` account. Row counts were checked against the figures recorded in Phases 5 and 6 immediately after import.

| Table | Rows |
|---|---|
| `dim_city` | 11 |
| `dim_pollutant` | 14 |
| `dim_station` | 244 |
| `fact_cpcb_subindex` | 545 |
| `fact_openaq_concentration` | 127 |
| `fact_weather_observations` | 11 |
| `fact_weather_forecast` | 264 |
| `fact_kaggle_historical` | 1,140,696 |
| `fact_kaggle_daily_aqi` | 95,058 |

`dim_station` had no previously documented total; 244 is consistent with 90 Kaggle, 20 OpenAQ and approximately 134 data.gov.in stations.

### 3.2 Relationships

Foreign-key metadata does not carry over from MySQL on import, so all relationships were recreated in the Power BI model. All are many-to-one with single-direction filtering.

| Dimension | Fact tables |
|---|---|
| `dim_city` | `dim_station` (`city_id`), `fact_weather_observations` (`city_id`), `fact_weather_forecast` (`city_id`) |
| `dim_station` | `fact_cpcb_subindex`, `fact_openaq_concentration`, `fact_kaggle_historical`, `fact_kaggle_daily_aqi` (`station_id`) |
| `dim_pollutant` | `fact_cpcb_subindex`, `fact_openaq_concentration`, `fact_kaggle_historical` (`pollutant_id`) |
| `DateTable` | All six fact tables (see 3.3) |

`fact_kaggle_daily_aqi` has no relationship to `dim_pollutant`, because it stores one overall AQI value per station per day rather than per-pollutant values.

### 3.3 Date table

`DateTable` is a DAX calculated table (`CALENDAR` + `ADDCOLUMNS`) spanning 2015-01-01 to 2027-12-31 (4,748 days), with Year, Month Number, Month Name, Quarter and Day columns, marked as the model's date table.

The live fact tables store date and time together, which cannot be matched to a date-only key. A `DateOnly` calculated column (`DATEVALUE` of the timestamp) was added to `fact_cpcb_subindex`, `fact_openaq_concentration`, `fact_weather_observations` and `fact_weather_forecast`. The two Kaggle fact tables store `reading_date` as a plain date and relate directly.

## 4. Design System

A single theme file was imported before any visuals were built so that all visuals inherit consistent styling.

- **Canvas:** 1920 × 1080 (Full HD), 16:9.
- **Style:** light and clean; white visual containers, light grey borders, 8 px corner radius, Segoe UI.
- **Categorical palette:** 11 distinct colours used when comparing cities.
- **Severity palette:** the six-band Indian AQI scale, applied through conditional formatting wherever an AQI value is shown. It is kept separate from the categorical palette so that a severity colour always means severity.

| Band | Range | Colour |
|---|---|---|
| Good | 0–50 | `#4CAF50` |
| Satisfactory | 51–100 | `#A3C853` |
| Moderate | 101–200 | `#FFC107` |
| Poor | 201–300 | `#FF9800` |
| Very Poor | 301–400 | `#F44336` |
| Severe | 401–500 | `#8E24AA` |

## 5. DAX Objects

### Measures

| Measure | Definition summary |
|---|---|
| Total data.gov.in Readings | `COUNTROWS(fact_cpcb_subindex)` |
| Avg Sub-Index (data.gov.in) | `AVERAGE` of `sub_index_avg` |
| Avg Concentration ug/m3 (OpenAQ) | `AVERAGE` of `concentration_value` |
| Avg Historical Daily AQI (Kaggle) | `AVERAGE` of `fact_kaggle_daily_aqi[aqi_value]` |
| Cities Monitored | `DISTINCTCOUNT(dim_station[city_id])` |
| Avg Sub-Index Latest Day | `AVERAGE` of `sub_index_avg` filtered to the latest `DateOnly` |
| Station Sub-Index Today | Same logic, evaluated per station for the map |
| Avg Wind Speed | `AVERAGE` of `wind_speed_kmh` |
| Kaggle Stations With Data | `DISTINCTCOUNT` of `station_id` in `fact_kaggle_daily_aqi` |
| Pct Missing (Kaggle) | `DIVIDE` of rows with `flag_missing = TRUE` by all rows in `fact_kaggle_historical` |
| Pct Missing by Pollutant | Same ratio, evaluated in a pollutant context |
| Valid Readings (Kaggle) | Rows with `flag_missing = FALSE` |
| Latest Data Timestamp | `MAX` of `fact_cpcb_subindex[timestamp_local]` |
| Hours Since Last Update | `DATEDIFF` in hours between Latest Data Timestamp and `NOW()` |
| Total Historical Records | `COUNTROWS(fact_kaggle_historical)` |
| Reading Count | `COUNTROWS(fact_cpcb_subindex)` |
| OpenAQ Reading Count | `COUNTROWS(fact_openaq_concentration)` |
| Active Alerts Count | Rows in `fact_cpcb_subindex` with `sub_index_avg > 100` |
| Avg Alert Severity | Average `sub_index_avg` over rows above 100 |

### Calculated columns

| Column | Table | Purpose |
|---|---|---|
| `DateOnly` | four live fact tables | Date-only key for `DateTable` relationships |
| `Severity Band` | `fact_cpcb_subindex` | Six-band classification via `SWITCH(TRUE(), ...)`, with `ISBLANK` evaluated first so missing readings are labelled "Missing" |
| `Alert Magnitude Bucket` | `fact_cpcb_subindex` | 10-point buckets above the alert threshold |
| `Reliability` | `fact_openaq_concentration` | "Valid" or "Suspicious" from `is_suspicious` |

## 6. Report Pages

### Page 1 — Overview

Headline metrics and long-run trends.

| Visual | Type | Purpose |
|---|---|---|
| Total data.gov.in Readings | Card | Size of the live reading set |
| Cities Monitored | Card | Geographic scope |
| Avg Sub-Index Latest Day | Gauge (0–500) | Position of the latest day's average on the full severity scale, coloured by AQI band |
| Avg Historical Daily AQI (Kaggle) | Card | Historical baseline for comparison with the live gauge |
| Hours Since Last Update | Card | Data freshness; green ≤ 2 h, amber ≤ 24 h, red above |
| Total Historical Records | Card | Scale of the historical dataset (1.14 M rows) |
| Average AQI by City, 2015–2020 | Line chart | City-level historical trend, with a dashed average reference line |
| Which Pollutant Reads Worst, On Average? | Column chart | Pollutant-level comparison of live sub-index values; the only visual on the page that compares pollutants rather than cities |

### Page 2 — Data Quality & Coverage

How far each source and each city's numbers can be relied on.

| Visual | Type | Purpose |
|---|---|---|
| Real Reporting Stations per City | Bar chart | Number of stations with data per city; cities with one station are visually flagged |
| Do Fewer Stations Mean Less Complete Data? | Scatter | Tests whether station count relates to missing-data rate |
| Pollutant Data Availability | Treemap | Box size is valid readings; colour is missing-data rate |
| City × Pollutant Data Completeness | Matrix | Missing-data rate for each city and pollutant pair |
| OpenAQ Reading Reliability | Donut | Valid versus suspicious readings in the live backup source (125 / 2 of 127) |
| Data quality note | Text | Discloses the Ahmedabad station issue (section 8) |

### Page 3 — Live Snapshot

The most recent loaded readings.

| Visual | Type | Purpose |
|---|---|---|
| Live Air Quality Snapshot | ArcGIS map | Location of each station reading; bubble size and colour reflect sub-index value |
| Avg Sub-Index and Avg Wind Speed by Date | Combo chart | Compares the two independently collected live sources; a subtitle discloses the date mismatch (section 10) |
| Today's Readings by Severity Band | Donut | Composition of the 545 readings by band, including a separate "Missing" slice |

### Page 4 — Alerts

Readings above the "Satisfactory" threshold (sub-index > 100).

| Visual | Type | Purpose |
|---|---|---|
| Active Alerts table | Table | Station-level list of alerting readings, sorted by value and coloured by band; one row per station and pollutant |
| Which Cities Have Active Alerts? | Bar chart | Geographic distribution of alerts |
| Which Pollutants Are Triggering Alerts? | Bar chart | Pollutant distribution of alerts |
| City · Pollutant Alert Concentration | Matrix | Combines both dimensions to show where alerts concentrate |
| How Far Above Threshold Are Today's Alerts? | Column chart | Magnitude distribution, in 10-point buckets, sorted by bucket order |
| Avg Alert Severity | Card | Typical magnitude of an active alert (116.11) |

## 7. Cross-Page Features

- Shared header banner and footer band with data-source provenance on every page.
- A city slicer synchronised across all four pages through Sync Slicers.
- Page-navigation buttons in the header, replacing the default page tabs.
- Icon images on the KPI cards.

## 8. Data Quality Findings Surfaced

**Ahmedabad (single-station city).** Ahmedabad's historical trend comes from one station, Maninagar – GPCB (`GJ001`). Its precomputed AQI values average 683.79 with a maximum of 2049, above the defined 0–500 scale, and do not reconcile with the station's own pollutant readings (PM10 average 114.6, PM2.5 average 67.9). Daily row counts match calendar days exactly (365, 366, 365, 365, 365, 183), which rules out row duplication from the model. The values appear to be an artefact of the source dataset. They are disclosed on the Data Quality page and retained in the model.

**Pollutant availability.** NH3 and the three VOCs added in Phase 6 (Benzene, Toluene, Xylene) show the highest missing-data rates. The overall missing rate across the historical readings is 29.7%.

**Missing live readings.** In the loaded data.gov.in snapshot, 56 of 545 readings (10.3%) have no sub-index value.

## 9. Issues Encountered and Resolutions

| Issue | Cause | Resolution |
|---|---|---|
| `fact_weather_observations` related to `dim_city` as one-to-one, bidirectional | Auto-detection from both tables having 11 rows | Set to many-to-one, single direction, matching the intended many-readings-per-city design |
| Documentation referenced `last_update` in `fact_cpcb_subindex` | Real column is `timestamp_local` | Column names confirmed through `INFORMATION_SCHEMA.COLUMNS` |
| Date table could not relate to timestamp columns | Date+time versus date-only values | `DateOnly` calculated columns; display type set to Date |
| `Cities Monitored` shows 12 rather than 11 | `DISTINCTCOUNT` counts the blank `city_id` of unmatched OpenAQ stations | `DISTINCTCOUNTNOBLANK` identified as the fix; the original measure was deliberately retained |
| Classic Map and Filled Map visuals disabled | Tenant-level policy on the signed-in account | Icon Map Pro was tried and required a licence; ArcGIS Maps for Power BI (built in, no login) used instead |
| Map bubbles uniform in size and colour | Colour field and layer style not applied | `Station Sub-Index Today` bound to both Size and Color; style set through the layer menu |
| Combo chart axis showed day-of-month numbers, then hourly ticks | Date hierarchy at Day level, then Continuous axis on date-only data | Bound to the plain `Date` field and set to a Categorical axis |
| `AVERAGE` failed on `flag_missing` | Column imported as Boolean | Replaced with `DIVIDE(CALCULATE(COUNTROWS(...), flag = TRUE), COUNTROWS(...))` |
| Severity donut legend showed numeric ranges; a SQL check reported 56 "Severe" rows when the maximum reading was 138 | Bin grouping produces data-driven ranges; NULL fails every `CASE` comparison and falls to `ELSE` | Replaced with the `Severity Band` column (`ISBLANK` first); SQL check corrected with an explicit NULL branch |
| Treemap had no colour-saturation well | Not available in this visual version | Conditional formatting on Data colors, based on `Pct Missing by Pollutant` |
| Alert magnitude buckets out of order | Default sort by value | Sort axis set to bucket, ascending |
| Public web publishing unavailable | "Publish to web" disabled by the institutional tenant; personal accounts cannot sign in to Power BI Service | Report distributed as a `.pbix` file (section 11) |

## 10. Validation

Each measure and visual was compared with a direct MySQL query at the time it was built.

| Check | Power BI | MySQL |
|---|---|---|
| Table row counts (all nine) | match Phases 5–6 | match |
| `Total data.gov.in Readings` | 545 | 545 |
| Delhi 2018 average daily AQI | 246.32 | 246.32384 |
| Hours Since Last Update | 165 (at check time) | 165 |
| Active Alerts Count | 19 | 19 |
| Avg Alert Severity | 116.11 | 116.105 (sum 2,206 / 19) |
| Pct Missing (Kaggle), overall | 29.7% | 29.7% |
| Pct Missing per city | match | match |
| OpenAQ valid / suspicious | 125 / 2 | 125 / 2 (127 total) |
| Severity bands (Good / Satisfactory / Moderate / Missing) | 373 / 97 / 19 / 56 = 545 | 373 / 97 / 19 / 56 |
| Stations per city (Page 2) | Delhi 38 … Ahmedabad 1 | matches the Phase 6 table |

Performance was profiled with Performance Analyzer on all four pages. The slowest visual on each page took 196 ms (Overview), 153 ms (Data Quality & Coverage), 111 ms (Live Snapshot) and 159 ms (Alerts). Visuals reading `fact_kaggle_historical` (1.14 M rows) were not slower than other visuals on the same page, so no model or query changes were needed.

## 11. Distribution

- The report was published to a Power BI Service workspace for viewing by signed-in users.
- Public web embedding is not available: the institutional tenant disables "Publish to web", and personal Microsoft accounts cannot sign in to Power BI Service.
- The `.pbix` file is distributed in this repository and opens in the free Power BI Desktop application with all pages, slicers and navigation functional.
- Credentials were never loaded into the model; it contains only cleaned readings and station and city reference data.

## 12. Known Limitations

- **Live data coverage in the model.** The imported data.gov.in readings cover a single day (2026-08-26) and the weather observations two days. Live time-series visuals are therefore sparse, and the combo chart on Page 3 has no date on which both series have values; its subtitle states this.
- **Manual refresh.** Cleaning and loading were run manually when this phase was completed. The model reflects the last load, and the `Hours Since Last Update` card reports its age. The published copy is a snapshot and does not refresh automatically.
- **Historical coverage.** The Kaggle data ends on 2020-07-01, so 2020 is a partial year that omits the highest-pollution months and should not be read as a genuine improvement. Pune has no historical data.
- **Ahmedabad.** Its historical series depends on one station with the inconsistencies described in section 8.
- **Cities Monitored.** Reports 12 because of the unmatched-station blank described in section 9.
- **Source scales.** data.gov.in values are AQI sub-indices and OpenAQ values are concentrations in µg/m³; they are not directly comparable and are never combined in a visual.
- **Alert page.** With all 19 alerts between 101 and 138, several alert visuals are sparse by design. They will fill out as more live days are loaded.
