# Phase 6 — Kaggle Historical Data: Cleaning & Database Loading
**Project:** India Urban Air Quality Intelligence & Early-Warning System
**Status:** Complete

---

## The 30-Second Version (say this first, if asked "walk me through this phase")

> "By the end of Phase 5, three of my four planned data sources were fully loaded into MySQL — but the historical Kaggle dataset, downloaded and verified all the way back in Phase 3, still wasn't in the database. Phase 6 closed that gap. I inspected the real raw files rather than trusting the dataset's description, filtered down to just my 11 target cities, and discovered the practical Pune gap was even more precise than I'd documented — its one listed station has zero actual readings. I designed two new database tables instead of one, specifically to avoid repeating the same daily AQI value across every pollutant row — the same 'don't blur different kinds of numbers' principle from Phase 5. While cleaning the data, I found three real pollutants — Benzene, Toluene, Xylene — that weren't in my pollutant catalogue at all, and added them properly rather than dropping real data. I also caught myself almost trusting a suspiciously clean '0% suspicious values' result, investigated it properly, and confirmed the dataset really was pre-cleaned by its original curator, unlike my live sources. Then I wrote a loader that reuses the exact same pattern as my other three loaders — same connection helper, same duplicate protection, same logging — and loaded over 1.2 million real rows into MySQL, verifying every step against actual database queries, not just clean console output."

Everything below unpacks that paragraph, explained simply, one piece at a time.

---

## 0. Why This Phase, and Why This Direction

At the start of Phase 6, three realistic directions were considered:
1. **Build the Kaggle historical loader** (chosen) — the one genuinely incomplete piece of the database; without it, there's no historical baseline behind any of the live data.
2. **Automate the existing loaders via Task Scheduler** — a real option, but it repeats a scheduling problem already solved in Phase 3, with low new learning value.
3. **Move into analysis / Power BI** — the eventual goal, but premature with only a few hours of live data loaded and no historical baseline to compare against.

Option 1 was chosen because it's the piece the other two options actually depend on: a dashboard or analysis layer is far more interesting with 5+ years of real historical trend data behind it than with a few dozen hours of live polling.

---

## 1. Inspecting the Real Files Before Writing Any Code

**Why this step matters:** Phase 1 and Phase 3 already proved this project's dataset descriptions can be wrong (the "2015–2024" date range that turned out to actually be "2015–2020"). Rather than assume the Kaggle download still matched its original description, the raw files were inspected directly with a small throwaway Python script before any real code was written.

**What the Kaggle download actually contains — 5 files:**
- `city_day.csv` / `city_hour.csv` — pollution data pre-aggregated to the whole-city level (not used — see below)
- `station_day.csv` / `station_hour.csv` — pollution data per individual monitoring station, daily or hourly
- `stations.csv` — a lookup table of station metadata (ID, name, city, state, status)

**Decision: use `station_day.csv` + `stations.csv` only.**
- **Station-level, not city-level:** the whole rest of this project (`dim_station`) is built around individual physical stations, matching your live sources — using pre-aggregated city-level data would break that consistency.
- **Daily, not hourly:** this dataset exists to provide historical *context and trend baseline*, not another live hourly feed — daily granularity is the right level of detail for that purpose, and it's a fraction of the size of the hourly file for the same underlying information.

This scope decision — using 2 of the 5 available files — is a deliberate, documented choice, the same way Pune's absence or OpenAQ's weather-in-pollutant-field discovery were documented rather than silently ignored.

---

## 2. Verifying Real City Coverage — and a More Precise Pune Finding

**Why this step:** `stations.csv` lists 230 stations across 127 cities nationwide — but the project only cares about 11 target metros, and not every *listed* station necessarily has *actual reading data* behind it.

**What was found, city by city (Delhi, Mumbai, Bengaluru, Hyderabad, Chennai, Kolkata, Pune, Ahmedabad, Lucknow, Jaipur, Patna):**

| City | Stations listed | Stations with real data |
|---|---|---|
| Delhi | 38 | 38 |
| Mumbai | 10 | 10 |
| Bengaluru | 10 | 10 |
| Hyderabad | 6 | 6 |
| Chennai | 4 | 4 |
| Kolkata | 7 | 7 |
| **Pune** | **1** | **0** |
| Ahmedabad | 1 | 1 |
| Lucknow | 5 | 5 |
| Jaipur | 3 | 3 |
| Patna | 6 | 6 |
| **Total** | **91** | **90** |

**The refined Pune finding:** Phase 1's original documentation said Pune "isn't included" in the Kaggle dataset. That's now been checked at a more precise level — Pune actually *is* listed once in `stations.csv` (station metadata exists), but that single station has **zero** rows in `station_day.csv` (no actual readings were ever recorded for it in this dataset). The practical effect is identical (no historical bootstrap for Pune), but the root cause is more precisely understood and documented — exactly the same "verify, don't trust the label" discipline used throughout this project.

**Result:** 90 real stations, across 10 of the 11 target cities, form the actual scope of what gets loaded.

---

## 3. Designing the New Database Tables

**The problem with a single combined table:** `station_day.csv` contains two fundamentally different *shapes* of data per station/day:
- Twelve separate pollutant readings (PM2.5, PM10, NO, NO2, NOx, NH3, CO, SO2, O3, Benzene, Toluene, Xylene) — **one row needed per pollutant**
- One single overall AQI score and category label (e.g. "Moderate") — **one row needed per station/day, period**

Putting both in the same table would mean copying the exact same AQI value onto 12 separate rows for every station/day — duplicated data, and a structural risk of someone downstream accidentally treating that repeated AQI as if it varied by pollutant, which it doesn't. This is the same category of mistake the Phase 5 schema was explicitly designed to make *impossible* (keeping sub-index and concentration values in separate tables) — so the same principle was applied here.

**Solution: two new tables instead of one.**

**`fact_kaggle_historical`** — one row per station, per pollutant, per day
| Column | Plain-English meaning |
|---|---|
| `reading_id` | Auto-generated unique row number |
| `station_id` | Links to `dim_station` — which physical station this reading is from |
| `pollutant_id` | Links to `dim_pollutant` — which pollutant this specific value measures |
| `reading_date` | The calendar date of the reading (no time — this is daily data) |
| `pollutant_value` | The actual measured/reported number for that pollutant that day |
| `flag_missing` | `TRUE` if the value was blank in the original file |
| `is_suspicious` | `TRUE` if the value looked invalid (negative, or a known error code) |

**`fact_kaggle_daily_aqi`** — one row per station, per day
| Column | Plain-English meaning |
|---|---|
| `daily_aqi_id` | Auto-generated unique row number |
| `station_id` | Links to `dim_station` |
| `reading_date` | The calendar date |
| `aqi_value` | The single overall Air Quality Index number for that station that day (0–500 scale) |
| `aqi_bucket` | The plain-language category Kaggle assigned (e.g. "Good," "Moderate," "Severe") |
| `flag_missing` | `TRUE` if AQI wasn't computable that day |

**Two supporting schema changes made at the same time:**
1. `dim_station.source_system` — previously only allowed `'data_gov_in'` or `'openaq'` as values (an `ENUM`, a column type that only accepts values from a fixed list, physically blocking typos). Widened to also allow `'kaggle'`.
2. **Decision: Kaggle stations become brand-new, unmatched rows in `dim_station`** — not linked to any existing data.gov.in or OpenAQ station, even if they're physically near each other in the same city. Matching stations across sources by comparing GPS coordinates is a real, separate engineering problem, and this project already deliberately deferred it twice before (Phase 1 planning, Phase 5 build). Staying consistent with that earlier decision was chosen over reopening it mid-task.

---

## 4. Reconciling the Pollutant List

**The check performed:** before writing any cleaning code, Kaggle's 12 pollutant column names were compared directly against the project's existing `dim_pollutant` table (11 codes, built up through Phases 1 and 5).

**What was found:** 9 of Kaggle's pollutant columns already matched existing codes (with `NOx` simply needing to map onto the existing `NOX` spelling). But **three did not exist anywhere in the project yet: Benzene, Toluene, and Xylene** — real air pollutants (a category called VOCs, volatile organic compounds) that neither data.gov.in nor OpenAQ had ever reported, so the project had never needed to track them before.

**The decision — add them, don't drop them.** This is a different situation from the OpenAQ weather-fields discovery in Phase 5, where excluding the data was the *correct* choice (because mixing temperature readings into a pollutant table would have been actively wrong). Here, Benzene/Toluene/Xylene genuinely are pollutants — excluding real, correctly-typed pollution data for no reason would just be throwing away information the dataset actually has. Three rows were added to `dim_pollutant`, bringing the total from 11 to 14 codes.

---

## 5. Writing `clean_kaggle.py`

**What "cleaning" means here, concretely:**
1. Load `stations.csv` and `station_day.csv`
2. Filter down to only the 90 real stations belonging to the 11 target cities
3. **Reshape the data from wide to long format** — the one genuinely new technique in this phase. The raw file has one row per station/day with 12 separate pollutant columns side by side. The database wants one row per station/day/**pollutant**. Pandas has a built-in function for this exact transformation, called `melt()` — it takes columns that should really be separate rows and stacks them vertically instead of side by side.
4. Standardize pollutant column names to match the 14 codes now in `dim_pollutant`
5. Apply the same "flag, don't drop" quality checks used in every prior cleaning script: `flag_missing` (blank value), `flag_negative` (value below zero), `flag_sentinel` (known placeholder error codes like 999/9999/−999), and a combined `is_suspicious` flag
6. Write out two separate CSVs — one matching each of the two new database tables

**Verified results, checked against real numbers, not just "it ran":**
- 90 stations, 95,058 station-day rows found after filtering
- Melted into **1,140,696 rows** (95,058 × 12 pollutants) — verified the arithmetic matched exactly before trusting the output
- 29.7% of pollutant readings flagged missing, 19.9% of daily AQI values flagged missing — both plausible for a real multi-year sensor dataset, and not something to just accept without a second look
- **0.0% flagged suspicious — investigated rather than accepted at face value.** A perfectly clean result across 1.14 million real-world sensor rows is unusual enough to be worth double-checking. The real minimum and maximum values were checked directly (`0.0` to `1000.0`), and the exact value `1000.0` — a suspiciously round number that sometimes indicates an artificial data cap — was checked for how often it occurred. It appeared exactly **once**, in a single PM2.5 reading, which is far more consistent with a genuine extreme pollution spike (Delhi's winter PM2.5 levels are well known to spike into four-digit territory) than a systematic clipping artifact. **Conclusion, now confirmed rather than assumed:** this particular Kaggle dataset appears to have already been cleaned by its original curator before publishing — a real, useful difference from the live government/OpenAQ feeds, which do genuinely contain negative values and sentinel codes.

---

## 6. Writing `load_kaggle.py`

**Design principle: reuse the existing pattern, don't reinvent it.** Rather than designing a new loader from scratch, the actual working code from `load_openaq.py` and `db_connector.py` was read directly and used as the template — same `get_connection()` helper, same `str_to_bool()` text-to-boolean conversion, same duplicate-handling approach (catching MySQL's error code `1062`, which means "this exact row already exists," and counting it as a skip rather than crashing).

**What it does, step by step, for every row:**
1. Look up whether this station already exists in `dim_station` (keyed by Kaggle's own station ID, e.g. `"AP001"`). If not, create it.
2. Look up the pollutant's internal ID from `dim_pollutant`.
3. Try to insert the reading. If it's a genuine duplicate (same station + pollutant + date already loaded), let the database reject it and count it as skipped — don't crash, don't insert twice.

**Two real differences from `load_openaq.py`, both deliberate:**
1. **One script, two destination tables.** The script auto-detects which of the two cleaned CSVs it's been given by checking for a `pollutant_code` column (same trick already used in `load_open_meteo.py` to tell its two file types apart), and routes to either `fact_kaggle_historical` or `fact_kaggle_daily_aqi` accordingly.
2. **Real city lookup, not a NULL.** OpenAQ's loader leaves `city_id` as `NULL` because OpenAQ's data never says which of the 11 target cities a station belongs to. Kaggle's `stations.csv` *does* give a real city name for each station, so `load_kaggle.py` looks that name up against `dim_city` and stores the real match — an honest, verified relationship instead of a guess or a placeholder.

---

## 7. Loading the Real Data — and Verifying Every Step

**Order of operations, and why it matters:** the smaller file (`kaggle_daily_aqi.csv`, 95,058 rows) was loaded first, deliberately. Loading it first meant all 90 Kaggle stations got created during that run. Loading the much larger file second (`kaggle_historical_readings.csv`, 1,140,696 rows) then tested the *other* branch of the "look up or create" logic — confirming stations were correctly found and reused, not accidentally re-created — which is a real thing worth proving, not just assuming.

**Results, and the specific checks that confirmed them:**

| Check | Expected | Actual | Verified how |
|---|---|---|---|
| `fact_kaggle_daily_aqi` row count | 95,058 | 95,058 | `SELECT COUNT(*)` in MySQL Workbench |
| Kaggle stations created | 90 | 90 | `SELECT COUNT(*) FROM dim_station WHERE source_system = 'kaggle'` |
| City lookup correctness | Real city names, correctly matched | Confirmed — e.g. Patna stations → `Patna`, Delhi stations → `Delhi` | Manual join + spot-check of 10 real rows |
| `fact_kaggle_historical` row count | 1,140,696 | 1,140,696 | `SELECT COUNT(*)` in MySQL Workbench |
| No new stations on second load | Still 90 (all reused, none re-created) | Confirmed still 90 | Re-ran the station count query |
| Real pollutant values | Sensible numbers matching raw file preview | Confirmed — e.g. a real Delhi PM2.5 reading of 232.36 during November (plausible peak pollution season) | Spot-checked 15 real rows via a 3-table join |
| Aggregate flag rates match the cleaning script | ~29.7% missing, 0.0% suspicious | Confirmed exactly: 29.7% / 0.0% | `AVG(flag_missing)`, `AVG(is_suspicious)` query against the loaded table |

**A real mistake caught during verification, worth including honestly:** an early spot-check query used station ID `AP001` (seen in the very first raw-file preview back in Step 1) and returned zero rows — briefly looking like a loading failure. Investigating properly (rather than assuming the loader was broken) showed the real cause: `AP001` belongs to Amaravati, a city that was never in the 11-city target list, and was correctly filtered out by `clean_kaggle.py` long before loading. The query was corrected to use a station that had actually survived the filter (`Alipur, Delhi - DPCC`), which then returned real, correct data. This is a small but genuine example of the same discipline used throughout the project: when something looks wrong, verify which side of the pipeline the problem is actually on before assuming a bug.

---

## 8. Themes Worth Emphasizing in an Interview

1. **A documentation gap gets more precise, not just corrected.** The Pune finding didn't just get re-confirmed — it moved from "not included" to "listed in metadata with zero real readings," a specific, more useful fact.
2. **The same design principle got reapplied in a new situation.** The "don't blur different kinds of numbers" reasoning that separated sub-index and concentration tables in Phase 5 was recognized as applying here too (AQI vs. per-pollutant readings), even though the presenting problem looked different on the surface.
3. **A too-clean result was investigated, not just accepted.** 0% suspicious values could easily have been taken as "the flags aren't finding anything to flag" — instead, it was checked against real min/max values and a specific round-number pattern, and only accepted once a concrete explanation was confirmed.
4. **Consistency was chosen over convenience** — reusing `load_openaq.py`'s exact pattern for the new loader, and declining to reopen the cross-source station-matching question that had already been deliberately deferred twice.
5. **Real mistakes during verification were investigated and explained, not hidden** — the `AP001` spot-check is a small, honest example of debugging your own query before assuming the pipeline is at fault.

---

## 9. Architecture, End of Phase 6

```
[data.gov.in API]  ──hourly poll (AUTOMATED)──┐
[Open-Meteo API]   ──hourly poll (AUTOMATED)──┼──> Raw JSON ──> Cleaning (CSV) ──> Python Loaders ──┐
[OpenAQ API]        ──hourly poll (AUTOMATED)─┘                                                      │
[Kaggle historical] ──clean_kaggle.py──> 2 CSVs ──> load_kaggle.py ─────────────────────────────────┤
                                                                                                       ▼
                                                                                          MySQL: india_air_quality
                                                                                    ┌─────────────┴─────────────────────┐
                                                                              dim_city, dim_pollutant (14),      fact_cpcb_subindex,
                                                                              dim_station (incl. 90 kaggle)      fact_openaq_concentration,
                                                                                                                 fact_weather_observations,
                                                                                                                 fact_weather_forecast,
                                                                                                                 fact_kaggle_historical (1,140,696 rows),
                                                                                                                 fact_kaggle_daily_aqi (95,058 rows)
                                                                                                                          │
                                                                                                                          ▼
                                                                                                          Analysis / ML layer (future — Phase 7 candidate)
```

---

## Interview Q&A — Phase 6

**"Why did the historical data need its own new tables instead of reusing the existing fact tables?"**
Because it's a third, genuinely different kind of number. `fact_cpcb_subindex` holds AQI sub-index health scores, `fact_openaq_concentration` holds real µg/m³ concentrations, and this Kaggle data has both a per-pollutant raw-style reading *and* a single precomputed overall AQI per station/day — two different shapes of fact that would either collide with the existing tables' meaning or, if combined into one new table, force the same AQI value to repeat across 12 pollutant rows. Splitting it into two purpose-built tables keeps every table representing exactly one kind of fact.

**"Walk me through the wide-to-long reshape — why was that necessary?"**
The raw file has one row per station/day with each pollutant as its own column — convenient for a spreadsheet, but not for a relational database that wants one row per individual measurement. I used pandas' `melt()` function to stack those 12 pollutant columns into 12 separate rows per station/day, each tagged with which pollutant it is — matching the same long-format pattern my other three fact tables already use.

**"You mentioned 0% of values were flagged suspicious — how do you know that's actually correct, and not just a bug in your flagging logic?"**
I didn't just accept it. I checked the real minimum and maximum values directly (0 to 1000), then specifically checked how often the suspiciously round number 1000 appeared, since that pattern sometimes indicates an artificial data cap rather than a real reading. It showed up exactly once, in a single PM2.5 reading — consistent with a genuine pollution spike, not a systemic clipping issue. That let me confidently conclude this particular dataset had likely already been cleaned before I received it, rather than assuming my flags were broken or blindly trusting a suspiciously perfect result.

**"How did you decide whether to add the new pollutants you found (Benzene, Toluene, Xylene), versus excluding them the way you excluded OpenAQ's weather readings in Phase 5?"**
Those are different situations. OpenAQ's weather readings were excluded because including them would have been *wrong* — mixing temperature and wind speed into a pollutant concentration table breaks the schema's core promise. Benzene, Toluene, and Xylene are genuinely pollutants; my source data just hadn't included them before. Excluding real, correctly typed pollution data would have thrown away information for no reason, so I added them to my pollutant lookup table instead.

**"Why did you load the smaller file (daily AQI) before the much larger file (1.1 million rows)?"**
Loading the smaller file first meant all 90 stations got created during that run. Loading the larger file second then specifically tested my loader's "station already exists, just look it up" logic path — not just the "create it" path I'd already proven — and I confirmed that by re-checking the station count stayed at exactly 90 after the second load, proving nothing got duplicated or re-created.

**"What was the hardest part of this phase?"**
Recognizing that the too-clean "0% suspicious" result needed investigating rather than trusting, and correctly diagnosing my own mistake during verification — using a station ID from an early raw-file preview that had actually been filtered out by my own cleaning script for being outside my target cities. Both were small moments, but they're the same class of discipline as harder bugs earlier in the project: check the real evidence before accepting a result, and check your own assumptions before blaming the pipeline.

**"What's next?"**
With all four planned data sources now fully loaded into MySQL — data.gov.in, OpenAQ, Open-Meteo, and now Kaggle's historical bootstrap — the database is functionally complete. From here, the realistic next steps are: automating the loaders via Task Scheduler (the option deferred at the start of this phase), or moving into real analysis and dashboarding (Power BI or Python) now that there's a genuine multi-year historical baseline to build trend charts and anomaly detection against.

---

## The Full "Guide Me Through This Phase" Answer

*(Use this as a spoken, flowing narrative — same content as the 30-second version above, expanded to walk through the real sequence of work.)*

"Going into Phase 6, my database had three of four planned sources loaded — the live sources were in, but the Kaggle historical dataset, downloaded and verified back in Phase 3, still wasn't in MySQL. Before picking a direction at all, I weighed three real options: finishing the Kaggle loader, automating my existing loaders the way I'd automated ingestion in Phase 3, or moving straight into analysis. I chose the Kaggle loader, because it's the piece the other two options actually depend on — a dashboard is much more interesting with real historical trend data behind it, and automating a loader I hadn't finished testing on all four sources felt premature.

I started the same way every phase in this project has started — by looking at the real files instead of trusting the dataset's description. That's exactly what caught the earlier '2015 to 2024' date range being wrong back in Phase 3, so I wasn't going to skip that step here. I found five files, but decided I only needed two of them — station-level daily data plus the station metadata file — since city-aggregated and hourly-level data weren't the right fit for a historical trend baseline matching my existing station-level schema.

Checking real city coverage turned up a more precise version of something I already knew: Pune isn't just absent from this dataset — it's technically listed once in the metadata file, but that one station has zero actual readings. Same practical gap, more precise root cause, and I made sure to note that distinction rather than leave the vaguer original wording standing.

Designing the database side, I caught a mistake in my own first draft before writing any code: a single new table would have repeated the same daily AQI value across all twelve pollutant rows for every station-day, which is exactly the kind of 'different numbers getting blurred together' problem I'd already solved once in Phase 5 by keeping sub-index and concentration data in separate tables. So I split this into two tables instead — one for individual pollutant readings, one for the single daily AQI score — keeping every table honest about representing exactly one kind of fact.

While reconciling pollutant names between the raw file and my existing lookup table, I found three real pollutants — Benzene, Toluene, and Xylene — that had never shown up in my other sources. I added them properly rather than dropping real data, since unlike the OpenAQ weather-in-pollutant-field issue from Phase 5, these genuinely are pollutants, just ones my other sources never reported.

I wrote the cleaning script to reshape the wide station-day format into the long format my database expects, using pandas' melt function, then applied the same flag-don't-drop quality checks I'd used for every other source. When the result came back showing 0% suspicious values across 1.1 million rows, I didn't just accept that — a perfectly clean result on real-world data is worth a second look. I checked the actual minimum and maximum values and specifically checked how often the suspiciously round number 1000 appeared. It showed up exactly once, consistent with a real pollution spike rather than an artificial cap, and let me confidently conclude this dataset had likely already been cleaned by its original publisher — a genuine, useful difference from my live sources.

For the loader, rather than writing something new from scratch, I pulled up my actual existing OpenAQ loader and database connector code and matched that same pattern exactly — same connection handling, same duplicate protection, same logging style — so all four of my loaders now work the same way. The one real difference is that Kaggle's station file actually gives me real city names, so unlike OpenAQ, I could look up and store a genuine city match instead of leaving it blank.

I loaded the smaller daily-AQI file first, which created all 90 real stations, then loaded the much larger 1.14-million-row pollutant readings file second — which specifically proved my loader's 'station already exists, reuse it' logic worked correctly, since the station count stayed at exactly 90 rather than growing. Every step was verified against real database queries — row counts, a spot-checked join across three tables, and comparing my loader's own missing/suspicious percentages against the numbers my cleaning script had already reported, not just trusting that the script finished without an error.

By the end of the phase, all four of my planned data sources are genuinely loaded, tested, and verified in MySQL — over 1.2 million real historical rows sitting alongside my live data, ready for the next phase, whether that's automating the loaders or finally moving into real analysis."
