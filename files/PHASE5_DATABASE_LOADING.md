# Phase 5 — Relational Storage & Database Loading (MySQL)
**Project:** India Urban Air Quality Intelligence & Early-Warning System
**Status:** Complete (loaders for all three live sources; Kaggle historical loader deferred)

---

## The 30-Second Version (say this first, if asked "walk me through this phase")

> "Up to this point, all my cleaned data was sitting in CSV files — one file per source, per day. Phase 5 gave that data a permanent, structured home in a real MySQL database. I designed a small relational schema: three lookup tables for things that don't change often — cities, pollutants, stations — and four tables for the actual hourly readings, kept deliberately separate so the two fundamentally different kinds of pollution numbers this project deals with — AQI health-severity scores from one source, and real physical concentrations from another — can never accidentally get mixed together. Then I wrote a Python loader for each source that reads the cleaned CSV, looks up or creates the right IDs, and inserts the readings — safely, meaning if I run it twice by accident, it won't create duplicate data. Along the way I found and fixed a handful of real issues that only showed up once I looked at actual files instead of trusting documentation — a missing database column, a constraint that was too strict for one source, two pollutant codes nobody had listed, and a discovery that one data source secretly mixes weather readings in with its pollution readings. Every single step was verified against real inserted rows in the database, not just 'the script ran without an error.'"

Everything below unpacks that paragraph, in plain language, one piece at a time.

---

## Part 1 — The Big Idea: Why a Database at All?

Before this phase, your data lived as CSV files — essentially spreadsheets. That works fine for a handful of files, but it breaks down fast:

- You can't easily ask "give me every Delhi reading from the last 30 days" across dozens of separate daily files.
- Nothing stops the same reading from being saved twice.
- Nothing stops a typo (e.g., "Delhi" vs "delhi" vs "New Delhi") from quietly splitting one city into three different "cities" in your data.

A **relational database** solves all three problems by storing data in linked **tables**, with rules the database itself enforces — not rules you have to remember to follow by hand.

Two words you'll hear constantly, explained simply:
- **Primary Key (PK):** a column that uniquely identifies each row — like a passport number, no two rows can share one.
- **Foreign Key (FK):** a column in one table that points to a Primary Key in another table — this is how tables "link" to each other, and it lets the database refuse bad data (e.g., a reading for a station that doesn't exist).

---

## Part 2 — The Schema Design: Star Schema, Explained Simply

We used a standard, well-known pattern called a **star schema** — worth naming exactly like that in an interview.

**Dimension tables** = small, slow-changing, descriptive lookup tables. A city's name doesn't change every hour.
**Fact tables** = the fast-growing, numeric "event" tables — one row per actual measurement, growing every single hour, forever.

### The three dimension tables

**`dim_city`** — one row per target metro city
| Column | What it holds | Why this type |
|---|---|---|
| `city_id` | An internal number (1, 2, 3...) MySQL assigns automatically | `AUTO_INCREMENT` — you never type this yourself |
| `city_name` | e.g. "Delhi" | `UNIQUE` — stops the same city being entered twice |
| `latitude`, `longitude` | Coordinates | `DECIMAL` instead of a plain float, so coordinates don't drift due to rounding errors |
| `has_kaggle_historical_data` | `TRUE`/`FALSE` | Encodes the known Pune gap directly into the schema — Pune is the one city set to `FALSE` |

Contains **11 rows** — the target metros from Phase 1 (Delhi, Mumbai, Bengaluru, Hyderabad, Chennai, Kolkata, Pune, Ahmedabad, Lucknow, Jaipur, Patna).

**`dim_pollutant`** — one row per pollutant code
| Column | What it holds |
|---|---|
| `pollutant_id` | Auto-assigned internal number |
| `pollutant_code` | e.g. "PM2.5", "CO", "NO2" |

Contains **11 rows** — the original 8 from Phase 1 (PM2.5, PM10, SO2, NO2, CO, O3, NH3, Pb), plus `BC` (from Phase 4), plus `NO` and `NOX` (discovered missing during this phase — see Part 5).

**`dim_station`** — one row per physical monitoring station
| Column | What it holds | Why |
|---|---|---|
| `station_id` | Auto-assigned internal number | |
| `source_system` | Either `'data_gov_in'` or `'openaq'` | An `ENUM` — MySQL physically rejects any other value, catching typos automatically |
| `source_station_key` | The station's own original ID/name from its source | data.gov.in and OpenAQ don't share a common ID system |
| `station_name` | Human-readable name | |
| `city_id` | Links to `dim_city` | **Nullable** — explained in Part 5 |
| `latitude`, `longitude` | Station's coordinates | |

Populated **automatically by the loader scripts**, not by hand — because the real list of stations only exists inside the actual data files, and typing in guessed stations would mean fabricating data.

### The four fact tables

Each one represents "a real measurement, at a real place, at a real time." All four share a "flag, don't drop" philosophy carried over from the Phase 3/4 cleaning scripts: **bad or missing values get a `TRUE` flag column, they are never silently deleted.**

**`fact_cpcb_subindex`** (data.gov.in) — 545 rows loaded
- Links to a station and a pollutant.
- Stores `sub_index_min/max/avg` — **AQI health-severity scores, 0–500 scale, NOT real pollutant concentrations.** This naming is deliberate, so nobody downstream can mistake these for real µg/m³ numbers.
- These value columns are `NULL`-able on purpose — this is exactly how the documented "8.6% blank readings" from Phase 3 get represented: a real row exists (a station really did report for that hour), the flag says the number was missing, and the number itself is genuinely absent rather than faked as zero.
- A `UNIQUE` rule on (station, pollutant, timestamp) means the same reading can never be inserted twice.

**`fact_openaq_concentration`** (OpenAQ) — 127 rows loaded, across 20 stations
- Same idea, but stores `concentration_value` — **real physical concentrations in µg/m³**, a completely different kind of number from the sub-index scores above. This is the single most important design decision in the whole schema: these two kinds of numbers physically cannot end up in the same column, because they don't share a table.
- Also stores `sensor_id` (added mid-phase — see Part 5) and a `flag_zero` column specifically for exactly-0.0 readings, which usually mean an inactive or uncalibrated sensor rather than genuinely zero pollution.

**`fact_weather_observations`** (Open-Meteo, current conditions) — 11 rows loaded
- One row per city per hour: temperature, humidity, wind, rain, pressure, elevation, plus validity flags for each.
- Duplicates are **rejected**, not overwritten — a weather observation represents a real historical snapshot worth keeping, so if the exact same hour gets submitted twice, the first version is kept and the second is discarded as a duplicate.

**`fact_weather_forecast`** (Open-Meteo, 24-hour forecast) — 264 rows loaded (11 cities × 24 hours)
- One row per city per predicted hour, plus how many hours ahead the prediction was made (`forecast_step_hour`).
- **Deliberately different rule:** since the same future hour gets re-predicted by every hourly run, duplicates here are **overwritten with the newest prediction**, not rejected — "latest forecast wins." This was tested directly: loading the same file twice kept the row count at exactly 264, not 528, proving the overwrite rule works as intended.

---

## Part 3 — Setting Up: Verifying Before Building

Before writing a single `CREATE TABLE` statement, we confirmed MySQL was actually installed, running, and accepting logins — not assumed from a past install. This turned out to be a two-part check: the Windows Service (`MySQL80`, confirmed `Running`) and an actual authenticated login through the `mysql` command-line client, which needed a one-time PATH fix (Windows didn't know where the `mysql.exe` program lived until we manually added its folder to the system PATH).

We also learned partway through that different tools suit different jobs:
- **VS Code** — for writing `.sql` and `.py` files (a text editor)
- **MySQL Workbench** — for running SQL, browsing tables visually, and checking real data (a purpose-built database GUI)
- **PowerShell** — only for OS-level checks (is a service running) and Python/pip commands, not routine SQL work

---

## Part 4 — Security: A Dedicated, Restricted Database User

**The problem:** if the Python loader script logs in as `root` (the database's all-powerful administrator account), any bug in the script — a typo in a query, a wrong condition — could accidentally destroy tables, not just insert bad data.

**The fix — the principle of "least privilege":** we created a separate MySQL user, `aqi_loader`, and gave it only the permissions it actually needs:
```sql
GRANT SELECT, INSERT, UPDATE ON india_air_quality.* TO 'aqi_loader'@'localhost';
```
No `DROP`, no `DELETE`, no permission to touch any other database.

**This was tested directly, not just assumed to work:** logging in as `aqi_loader` and running `DROP TABLE dim_city;` returned:
```
Error Code: 1142. DROP command denied to user 'aqi_loader'@'localhost' for table 'dim_city'
```
That failure is the actual proof — if a future bug in the loader ever tried to run a destructive command, MySQL itself would block it, the same way `redact_secrets()` in Phase 3 was verified with a deliberate test rather than assumed to work.

The credentials were stored in `.env` (already git-ignored), exactly like the existing API keys — same pattern, same discipline.

---

## Part 5 — The Loader Scripts: What They Do and How

### The shared pattern behind every loader

All three loader scripts (`load_data_gov_in.py`, `load_openaq.py`, `load_open_meteo.py`) follow the same four moves for every row in a CSV:

1. **Look up (or create) the city/station's internal ID.** Cities were already seeded by hand (Part 2); stations are discovered live from the real data, the first time each one appears.
2. **Look up the pollutant's internal ID.**
3. **Try to insert the actual reading.**
4. **If that exact reading already exists (same station/pollutant/timestamp), let the database reject it and just count it as "skipped" — don't crash, don't duplicate.**

A helper function `get_connection()` (in `src/utils/db_connector.py`) centralizes how every script connects to MySQL — mirroring the existing `secrets_loader.py` pattern from Phase 2, so credential-handling logic lives in exactly one place.

### A subtlety worth understanding: CSV flags are text, not real True/False

The cleaning scripts write flag columns as the literal text `"True"`/`"False"`. In Python, **any non-empty string is automatically treated as "true"** — so the string `"False"` would be mistakenly read as `True` if not handled carefully. Every loader includes a small `str_to_bool()` function that explicitly checks the text content, rather than trusting Python's default truthiness.

### What made each loader different

**data.gov.in loader** — the simplest and first one built. Straightforward: look up city (already seeded), find-or-create station, find pollutant, insert. Out of the 2000 nationwide station records in the raw pull, only 545 belonged to the 11 target cities — the other 1,455 were correctly recognized as out-of-scope and skipped, not silently dropped (each skip is logged with a reason).

**OpenAQ loader** — the trickiest one, because OpenAQ's data has a real structural quirk: some rows represent a station that's registered but currently reporting nothing at all (no sensor, no pollutant, no timestamp — nothing). A fact-table row is supposed to represent "a real measurement, at a real time" — a row with no timestamp isn't a measurement. So the loader still records that the *station* exists (useful information), but correctly produces **no fact-table row** for it, and counts it separately as `skipped_idle_station` so it's visible, not hidden. Out of 150 rows in the test file, 3 were idle stations like this.

**Open-Meteo loader** — the simplest by nature, since Open-Meteo is a coordinate-based weather API, not a network of physical sensors that can go offline. There's no "station discovery" step at all — city names in the file match `dim_city` directly. This script also had to handle **two related but differently-behaved tables** from two related files (current conditions vs. 24-hour forecast), auto-detecting which file it was given by checking for a `forecast_step_hour` column.

### The final piece — one script to run all three

`load_all.py` chains the three individual loaders together for a given date, so loading a full day's data is one command instead of three separately-typed ones. It reuses the exact same, already-tested loading functions underneath — it adds no new loading logic, just convenience and fewer chances to forget a source or mistype a path. This is explicitly **not** automation/scheduling (that's future work) — it's still run by hand, on purpose.

---

## Part 6 — Real Discoveries and Fixes Made During This Phase

This is the part most worth remembering for an interview — these weren't planned in advance, they were found by actually looking at real data and real results, the same discipline this whole project has followed since Phase 3.

1. **A missing database column, found by inspecting the real CSV.** The original schema didn't include `sensor_id` for OpenAQ readings. Comparing the actual CSV header against the table definition (before writing any loading code) caught this early, and it was added with a simple `ALTER TABLE` before any real data was loaded — cheap to fix early, expensive to fix after loading thousands of rows.

2. **A constraint that was too strict, caught before it caused a crash.** `dim_station.city_id` was originally `NOT NULL`, which worked fine for data.gov.in stations (always tied to a known city) but broke for OpenAQ stations, which the source data doesn't tie to any of our 11 target cities. Rather than guessing a city (fabricating a relationship the data doesn't actually support), the column was changed to allow `NULL` — an honest "we don't know" instead of an invented answer.

3. **Two real pollutant codes missing from the seed list.** The first real OpenAQ load surfaced `NO` and `NOX` — real pollutants nobody had listed in Phase 1's original pollutant catalogue. Added directly, verified with a second load.

4. **A genuine data discovery: OpenAQ secretly reports weather through the same field as pollutants.** Some OpenAQ-registered stations have built-in weather sensors, and their readings (`TEMPERATURE`, `RELATIVEHUMIDITY`, `WIND_SPEED`, `WIND_DIRECTION`) come through the exact same `pollutant_id` field as real pollutants like PM2.5. These were deliberately **excluded** from `dim_pollutant` and `fact_openaq_concentration` — a wind-speed reading is not a pollutant concentration, even if the API delivers it that way, and mixing them in would break the same "don't blur different kinds of numbers" principle the whole schema is built around.

5. **A math-verification catch — proving "verify, don't trust the label" still applies to our own logs.** A pasted summary line briefly showed `skipped_unknown_pollutant=2`, but adding up all four of the script's own reported numbers (inserted + duplicate + idle + unknown) only reached 132 out of 150 rows read — 18 short. Re-checking the full terminal output (not just the last line) revealed the real number was `20`, not `2` — a copy-paste truncation, not a real bug. The arithmetic check is what caught it; simply trusting the pasted summary would not have.

6. **The forecast table's overwrite behavior was tested on purpose, twice.** Loading the same forecast file a second time was a deliberate test, not an afterthought — proving the row count stayed at 264 (not 528) is the real evidence the "latest prediction wins" rule works, not just that the code looks like it should.

---

## Part 7 — How Everything Was Verified (Not Just "It Ran")

At every single step in this phase, "the script finished with no error" was treated as necessary but not sufficient. The actual verification always involved one or more of:
- Comparing the loader's own logged counts against a real `SELECT COUNT(*)` query in MySQL Workbench
- Spot-checking real row contents (`SELECT * ... LIMIT 5`) to confirm values look sensible, not just present
- Deliberately re-running a loader a second time to prove duplicate-handling actually works, rather than assuming a `UNIQUE` constraint written in the schema is automatically doing its job
- Deliberately trying a forbidden action (`DROP TABLE` as the restricted user) to prove a security rule is enforced, not just declared

---

## Part 8 — Architecture at the End of Phase 5

```
[data.gov.in API]  ──hourly poll (AUTOMATED)──┐
[Open-Meteo API]   ──hourly poll (AUTOMATED)──┼──> Raw JSON ──> Cleaning (CSV) ──> Python Loaders ──┐
[OpenAQ API]        ──hourly poll (AUTOMATED)─┘                                                      │
[Kaggle historical] ──one-time load (done, not yet in MySQL)                                         ▼
                                                                                          MySQL: india_air_quality
                                                                                    ┌─────────────┴─────────────┐
                                                                              dim_city, dim_pollutant,    fact_cpcb_subindex,
                                                                              dim_station                 fact_openaq_concentration,
                                                                                                           fact_weather_observations,
                                                                                                           fact_weather_forecast
                                                                                                                    │
                                                                                                                    ▼
                                                                                                    Analysis / ML layer (future)
```

---

## Part 9 — What's Deliberately NOT Done Yet (Out of Scope for This Phase)

- **No Kaggle historical data in MySQL yet** — there's no `clean_kaggle.py` producing a processed CSV for it, so there's nothing yet for a loader to read. Building a table with no data source feeding it would be premature.
- **No automated/scheduled loading** — everything above is triggered by hand, on purpose. Task Scheduler automation of the loader itself is future work, same pattern as how ingestion was automated in Phase 3 only after being proven correct manually first.
- **No cross-source station matching** — data.gov.in and OpenAQ stations are not linked to each other, even when they might physically be near the same location. This was scoped as secondary/deferred back in Phase 1, and nothing in Phase 5 changes that.

---

## Interview Q&A — Phase 5

**"Why did you use a relational database instead of just querying the CSV files directly?"**
CSVs don't enforce any rules — nothing stops duplicate rows, inconsistent city names, or a reading pointing to a station that doesn't exist. A relational database enforces those rules automatically through constraints (primary keys, foreign keys, unique constraints), and makes it possible to efficiently query across all your accumulated history in one place instead of opening dozens of separate files by hand.

**"Explain your schema design — why dimension tables and fact tables?"**
This is a standard pattern called a star schema. Dimension tables (city, pollutant, station) hold small, slow-changing descriptive data — I store "Delhi" once, not on every single row. Fact tables hold the actual hourly measurements and reference the dimension tables by ID instead of repeating text, which keeps the data both smaller and more consistent — there's no way to accidentally spell a city two different ways across different rows.

**"Why four separate fact tables instead of one shared 'readings' table?"**
Because this project has two fundamentally different kinds of pollution numbers: data.gov.in gives AQI sub-index health-severity scores on a 0–500 scale, while OpenAQ gives real physical concentrations in µg/m³. These are not directly comparable numbers. If I stored them in one shared table with a generic "value" column, it would become possible — even easy — to accidentally average or compare numbers that mean completely different things. Splitting them into separate, differently-named tables makes that mistake structurally impossible, not just something you have to remember to avoid.

**"What's the difference between a primary key and a foreign key?"**
A primary key uniquely identifies a row within its own table — no two rows can share one, similar to a passport number. A foreign key is a column in one table that points to a primary key in a different table, and it's how tables link together. It also acts as a safety check: the database will refuse to insert a reading for a station ID that doesn't actually exist in the stations table.

**"How do you prevent duplicate data if your ingestion or loader runs twice?"**
Every fact table has a `UNIQUE` constraint across the columns that together define "one real reading" — for example, station + pollutant + timestamp. If the loader tries to insert the same reading twice, MySQL itself rejects the second attempt with a duplicate-key error, which my script catches and counts separately rather than treating as a crash. I tested this directly by deliberately running a loader twice on the same file and confirming the row count in the database didn't change.

**"Why did some columns need to allow NULL, like the sub-index values or `dim_station.city_id`?"**
Because leaving a value out is sometimes the honest, correct answer — not an error to hide. About 8.6% of data.gov.in readings are genuinely blank because a station didn't report that hour; storing that as `NULL` with a flag preserves the fact that we know it's missing, rather than faking a zero. Similarly, OpenAQ's data doesn't tell us which of our target cities a station belongs to, so I made `city_id` nullable rather than guessing — an honest "unknown" instead of a fabricated relationship.

**"What was the hardest technical problem in this phase?"**
Handling OpenAQ correctly, for two separate reasons. First, some of its stations are registered but not currently reporting anything at all — no timestamp, no pollutant, nothing — and I had to decide that these should still register the station but produce zero fact-table rows, since a fact row is supposed to represent an actual measurement at an actual time. Second, I discovered mid-load that some OpenAQ stations report weather readings (temperature, humidity, wind) through the exact same field normally used for pollutants — and I had to deliberately decide to keep those out of the pollutant tables entirely, since mixing them in would undermine the exact "don't blur different kinds of data" principle the rest of the schema was built to protect.

**"How do you know your loader actually worked, rather than just not throwing an error?"**
At every step, I cross-checked the loader's own logged counts against a live `SELECT COUNT(*)` query in the actual database, and spot-checked real row contents to confirm the values looked sensible. I also deliberately tried to break things on purpose — running the same file twice to confirm no duplicates appeared, and trying a forbidden `DROP TABLE` command as the restricted database user to confirm it actually got denied, rather than assuming a permission I'd granted was working correctly.

**"Why create a separate database user instead of just using root in your script?"**
Least privilege — if there's ever a bug in my loading logic, I want the damage it could possibly cause to be limited to inserting or updating bad data, not the ability to delete tables or affect other databases entirely. I created a dedicated `aqi_loader` user with only SELECT, INSERT, and UPDATE permissions on this one database, and confirmed the restriction was real by deliberately trying (and being denied) a DROP TABLE command.

**"What would you do differently, or what's next?"**
Next is building a loader for the Kaggle historical dataset once its cleaning script exists, then eventually automating the loader itself via Task Scheduler the same way ingestion was automated in Phase 3 — but only after proving it correct manually first, same discipline as before. After that, the project moves into actual analysis and dashboarding.

---

## The Full "Guide Me Through This Phase" Answer

*(Use this as a spoken, flowing narrative — it's the same content as the 30-second version above, expanded to walk through the real sequence of work.)*

"By the end of Phase 4, I had three sources of cleaned data sitting in CSV files — data.gov.in's AQI sub-index readings, OpenAQ's real pollutant concentrations, and Open-Meteo's weather data — but nothing was actually in a database yet. Phase 5's goal was to design and build that database properly, then load the real data into it.

I started by actually verifying MySQL was installed and running on my machine, rather than assuming a past install worked — I checked the Windows service status and logged in directly. Then I designed the schema: three small lookup tables for city, pollutant, and station — things that don't change often — and four fact tables for the actual hourly readings, one for each measurement type. The most important decision there was keeping data.gov.in's AQI sub-index scores and OpenAQ's real µg/m³ concentrations in physically separate tables, since they're fundamentally different kinds of numbers and I wanted it to be structurally impossible to accidentally compare them.

I created the tables with real constraints — primary keys, foreign keys linking readings back to their station and pollutant, and unique constraints so the same reading could never be inserted twice — and verified the structure was actually correct by querying it back, not just trusting that the CREATE TABLE statements ran without error.

Before writing any loading code, I also set up a dedicated, restricted database user for the loader to use instead of the all-powerful root account, and proved the restriction was real by deliberately trying a command it shouldn't be allowed to run and confirming it got denied.

Then I wrote a loader script per source, one at a time, testing and verifying each fully before moving to the next. Each one follows the same core pattern — look up or create the city and station IDs, look up the pollutant, and insert the reading, letting the database itself reject true duplicates. Along the way I found several real issues just by looking closely at the actual data instead of trusting my own earlier assumptions — a database column I'd forgotten to include, a constraint that was too strict for one particular source, two pollutant codes that were missing from my reference list, and a genuine discovery that one source occasionally reports weather readings through the same field it uses for pollutants, which I deliberately chose to exclude rather than let contaminate the pollution data.

Every single step was checked against real evidence — comparing the loader's own counts against actual database queries, spot-checking real rows, and deliberately re-running loaders to prove duplicate protection actually works rather than just assuming it does. By the end of the phase, all three live sources have working, tested, duplicate-safe loaders, and the database contains real, verified data: 545 sub-index readings, 127 concentration readings across 20 stations, and 275 weather rows between current conditions and forecasts."
