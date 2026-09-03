# Phase 3 — Ingestion Expansion & Scheduling
**Project:** India Urban Air Quality Intelligence & Early-Warning System
**Status:** Complete

---

## The 30-Second Version (say this first, if asked "walk me through this phase")

> "Phase 2 got one data source working — a single script that could pull a live snapshot. Phase 3 turned that into a real pipeline: I added a second live source for cross-validation, a weather source since weather drives pollution dispersion, and a historical dataset to bootstrap training data, since the primary government API has no history endpoint at all. Then I made all three sources run automatically, every hour, unattended, using Windows Task Scheduler — which sounds simple but actually surfaced a genuinely tricky silent bug that took real debugging to find. Along the way I also caught and fixed a security issue, and made a real technical discovery about what the primary data source's numbers actually mean, which corrected an assumption from earlier in the project. I finished by building a monitoring script so I can check the health of the whole pipeline in one command instead of eyeballing folders."

Everything below unpacks that paragraph.

---

## What Phase 3 Set Out to Do

1. Add a backup/cross-validation live source (OpenAQ)
2. Add weather context (Open-Meteo) — a real modeling input, not decoration
3. Get a historical dataset (Kaggle) — the live API can only ever say "right now," never "last month"
4. Make the primary source's polling genuinely automatic, not something run by hand
5. Start turning raw JSON into clean, structured data
6. *(added once the above was working)* Extend automation to all three sources, and build a way to actually verify the whole pipeline is healthy — not just assume it is

---

## 1. OpenAQ — the backup / cross-validation source

**What it is:** an independent global aggregator of air quality data, pulling from many countries' official networks, India's included. Used as a second opinion on the primary government feed, and as a fallback if it goes down — which, notably, it genuinely did, twice, during this phase.

**Why it's structurally harder than the primary source:** the primary API returns station metadata *and* live readings in one call. OpenAQ v3 splits this into two calls — `/v3/locations` (which stations exist, no readings) and `/v3/locations/{id}/latest` (the actual reading, one station at a time). Getting real numbers means: pull the list once, then loop through stations individually.

**The engineering problem this creates, and the fix:** looping through stations with rapid-fire requests risks a rate limit. The script paces requests with a deliberate delay between calls, and treats one station's failure as **skip-and-log-a-warning**, not **crash-the-whole-run** — one bad station shouldn't take the entire pipeline down.

**A real data-quality finding:** in a 20-station sample, only 14 returned live readings — 6 were registered in OpenAQ's system but not actively reporting anything. Not a bug — a real characteristic of live third-party sensor networks, and it matched a risk the project's own earlier research had already flagged before it was ever observed in practice.

---

## 2. Open-Meteo — weather context

**What it is:** a free, no-authentication weather API. Weather is a real forecasting input (wind, precipitation, and pressure affect whether pollution disperses or accumulates), not just background color.

**The one trick worth explaining clearly in an interview:** instead of 11 separate calls for 11 cities (like OpenAQ needs per-station calls), Open-Meteo accepts **batched requests** — one comma-separated list of latitudes, one of longitudes, and it returns a JSON array, one entry per city, in the same order sent. One API call covers the entire city list. Worth explicitly contrasting this with OpenAQ's per-station design to show you understand that different APIs need different handling strategies, not just "call the endpoint."

**Design choices:** `timezone=auto` (local time per city, not raw UTC, since this needs to line up with India-local timestamps from the other sources later); pulled both current conditions and a 24-hour hourly forecast, since the project's forecasting goal needs a forward-looking weather window, not just a single snapshot.

---

## 3. Kaggle — the historical bootstrap dataset

**The core problem it solves:** the primary live API has no historical endpoint at all — without a historical dataset, there'd be zero training data for anomaly detection or forecasting until months of live polling had piled up naturally.

**A genuinely good "don't trust the label, verify the data" story, in two rounds:**

1. The first download pulled the wrong dataset entirely (a `train.csv` file — a competition-style name that doesn't belong to the real dataset). Caught by actually inspecting the downloaded files, fixed by re-downloading from the exact, verified source.
2. A deeper catch: earlier project documentation described this dataset as covering "2015–2024." Actually running a script against the real files' date column showed it stops in **2020** — a four-year gap between what was documented and what was true. The fix wasn't just correcting the number — it was updating the project's own earlier documentation on the spot, rather than letting a wrong assumption quietly persist.

**A disclosed limitation, not hidden:** the same verification revealed **Pune** — one of the 11 target cities — isn't in this dataset's 26 cities at all. Documented as a known gap rather than ignored: Pune will have no historical training data, only live data accumulating from this project's own polling onward.

---

## 4. Scheduling — making the primary source genuinely automatic

**Why this matters more than it sounds like it should:** since the primary source has no history endpoint, this project's own accumulated hourly snapshots *are* the only historical record that will ever exist for it. If the polling isn't reliably automatic, the core dataset simply doesn't get built.

**Tool choice:** Windows Task Scheduler, not a Python scheduling library — deliberately, to avoid adding a dependency that runs only while a Python process happens to be open. A small `.bat` launcher calls the virtual environment's Python directly by full file path (not via "activation," which is a human-typing convenience, not something an unattended process needs), and redirects all output — including failures that happen before the script's own logger even starts — into a log file.

**How this was actually proven to work, not just configured:** clicking "Run" once isn't proof of real automation. The real test was finding a new, correctly-timestamped file that appeared with nobody touching the keyboard, an hour after the last one.

**A real troubleshooting story:** one run failed with a cryptic exit code (`0xC000013A`). Decoded properly (converting the raw decimal into its Windows status-code meaning) it means the process was forcibly killed externally — consistent with the machine sleeping mid-run, not a code bug. Attempts to harden this (auto-retry, wake-computer-to-run) hit real, reproducible Windows/PowerShell bugs; the decision was to accept the limitation (worst case: one missed hour out of a day, immaterial for hourly-redundant data) rather than keep fighting a platform quirk for marginal benefit.

---

## 5. A real security fix: API keys leaking into logs

**What happened:** the primary source's API key is sent as a URL parameter, not a header. Python's `requests` library includes the full request URL — key included — inside certain exception messages (like a timeout error). Since failures were logged by printing the exception text directly, a failed request could write the real key straight into a plaintext log file.

**The fix:** a small `redact_secrets()` helper scans any string for known key values and replaces them with a placeholder before logging, applied everywhere an exception gets logged across both live-source scripts — and verified with a deliberate test rather than just assumed to work.

**Why it's worth mentioning even though the specific key was low-stakes:** the habit generalizes. Treating any credential that could leak as something to fix immediately — not something to weigh case-by-case — is the right default, and it shows you can spot an issue outside the original task spec.

---

## 6. The deepest technical finding: sub-index vs. raw concentration

**The best "tell me about a hard problem you solved" story in this phase.**

While building the cleaning script, the primary API's pollutant readings had **no unit field at all** — unusual for an environmental data feed. Investigating turned up that these fields are very likely **AQI sub-index scores** — a normalized 0–500 health-severity scale per pollutant — not physical concentrations.

**The decisive reasoning, not just a source citation:** documented usage of this exact API describes computing a station's overall AQI by taking the **maximum reading across all its different pollutants.** That operation is only mathematically valid if every pollutant's number is already on the same normalized scale — you can't meaningfully compare raw CO concentration (often in the thousands, µg/m³) against raw PM2.5 concentration (typically double/triple digits) by just taking "the bigger number." The only way "max across pollutants" produces a sensible standard AQI is if the values were already normalized sub-indices going in. That logical argument, backed by two independent sources describing the identical workflow, was strong enough to act on.

**What this changed concretely:** cleaned output columns were explicitly renamed (`sub_index_min/max/avg`, not a generic `value`) so the distinction can't be missed later, and the project's documentation was corrected to note this source can't be naively compared, number-for-number, against OpenAQ's real µg/m³ readings — a disclosed limitation, not a silently ignored one.

**Why it matters in an interview:** it shows noticing something *missing* from documentation, forming a hypothesis, and verifying it through reasoning about how the data must behave — not just reading docs and coding against them.

---

## 7. The First Cleaning Script (data.gov.in)

**What "cleaning" means here:** raw JSON becomes a standardized CSV — one row per station/pollutant/timestamp — with three concrete fixes: type casting (raw values arrive as text strings), pollutant name standardization (the raw feed's `"OZONE"` mapped to the project's standard `"O3"`), and suspicious-value flagging (negative numbers, known sentinel codes like `999`).

**A deliberate principle worth naming: flag, don't silently drop.** Bad or missing values get boolean flag columns instead of deletion — preserving the ability to make an informed decision downstream instead of hiding data loss.

**Verified against real data, not just "ran without crashing":** the first run flagged 8.6% of readings. Broken down by type, every flagged row was entirely blank (not garbled) — consistent with a station reporting it monitors a pollutant but having no valid reading that hour. A normal live-network characteristic, confirmed by actually checking, not assumed.

---

## 8. Extending automation to all three sources — and a genuinely hard bug

Once data.gov.in's automation was proven solid, the same treatment was extended to OpenAQ and Open-Meteo — same `.bat`-launcher pattern, separate log files per source (so a problem in one source doesn't get lost in another's output), staggered trigger times so all three don't compete for resources in the same minute.

**Registering the two new tasks appeared to work — every visible signal said so:** Task Scheduler showed `Status: Ready`, the trigger showed `Enabled: Yes`, and `NextRunTime` kept correctly advancing hour after hour. By every surface-level indicator, everything was fine.

**But it wasn't.** A dedicated pipeline health-check (see next section) caught what a quick glance wouldn't have: **zero new files were landing from either task, hours after they should have fired multiple times** — even during a window where the machine was confirmed awake and the original data.gov.in task was firing normally in parallel. That ruled out sleep as the explanation this time, which was the working theory for every scheduling problem up to this point.

**The actual debugging process, worth describing step by step in an interview:**
1. Ruled out the obvious ("is the machine asleep?") by cross-checking against the third task, which *was* firing successfully in the same time window.
2. Queried the task two different ways — PowerShell's `Get-ScheduledTaskInfo` and the older `schtasks /query /v` command — because the two tools sometimes surface different detail, and `schtasks`'s verbose output turned out to show a field the other didn't foreground clearly: **Power Management: `Stop On Battery Mode, No Start On Batteries`.**
3. Compared that field directly against the working data.gov.in task's equivalent output, which showed only `Stop On Battery Mode` — **missing** the "No Start On Batteries" restriction.

**Root cause:** Windows checks "**Start the task only if the computer is on AC power**" as a **default-on condition for every newly created task.** The original data.gov.in task had this explicitly unchecked, early in Phase 3 — but recreating the two new tasks skipped the Conditions tab (in an attempt to keep the setup minimal and avoid an unrelated GUI bug hit earlier), leaving that default silently active.

**Why this bug was so hard to see, and worth explaining precisely:** a trigger firing while blocked by an unmet condition produces **no error, no log entry, nothing** — Task Scheduler just quietly declines to launch the action. From the outside, a task that's condition-blocked looks *identical* to a task that's never been triggered at all (`LastRunTime` stuck at a placeholder "never" value, a specific "has not run yet" result code) — even though the trigger itself is firing correctly, over and over, every hour. This is exactly the kind of failure that looks like "nothing's configured" right up until you check the one specific field that reveals it's actually "configured, but silently blocked."

**The fix:** delete and recreate both tasks, this time explicitly unchecking "Start the task only if the computer is on AC power" in the Conditions tab. Confirmed resolved two ways: the result code changed from the "has not run" placeholder to a genuine success code, and — the only evidence that actually counts — real new files landed in both sources' folders with nobody manually running anything.

**Why this is a strong interview story:** it's a textbook example of a class of bug every engineer eventually hits — a condition that silently prevents an action, leaving no error trail, where the "obviously working" status indicators (Ready, Enabled, NextRunTime advancing) are all technically true and still completely misleading. The fix required refusing to trust surface-level status and cross-referencing against a known-working control case instead.

---

## 9. Building a Pipeline Health-Check Script

**Why this exists:** manually running three separate `dir` commands and eyeballing timestamps doesn't scale, and — as the AC-power bug just proved — status commands can report "healthy" while something is actually silently broken. A real pipeline needs an actual health check, not a vibe check.

**What it actually verifies, for each source:**
1. **Files exist for today** at all (catches a source that's stopped running entirely).
2. **Files are a sane size and genuinely parse as valid JSON** — not just "a file with the right name exists," which would miss a run that got killed mid-write and left a truncated or empty file.
3. **No gap between consecutive snapshots larger than expected** (90 minutes — a bit more than the 60-minute schedule, to tolerate normal timing jitter without false-alarming on it), which catches a source that's silently stopped firing even if some files from earlier in the day still look fine.
4. **No ERROR-level lines in today's log**, a cheap final sweep for anything that failed outright.

**Design choice worth naming:** thresholds were deliberately chosen to avoid false alarms (90 minutes, not exactly 60) based on evidence already seen in this project — real successful runs have landed a few minutes late before, and a health check that cries wolf on normal jitter trains you to ignore it.

---

## 10. Closing Out the Phase

- All three sources' quirks and root causes were written into `docs/DATA_SOURCES_LOG.md` as they were discovered — not just fixed silently, but documented with enough detail that the *why*, not just the *what*, is recoverable later.
- `PROJECT_STATE.md` was updated to reflect the phase's real end-state, including every disclosed limitation, not a cleaned-up version of events.
- Everything was committed to git — checked first with `git status` to confirm only intended files were staged (explicitly not `.env` or `venv/`), since a clean commit history matters as much as clean code.

---

## Architecture, End of Phase 3

```
[data.gov.in API]  ──hourly poll (AUTOMATED)──┐
[Open-Meteo API]   ──hourly poll (AUTOMATED)──┼──> Raw landing zone (JSON) ──> Cleaning
[OpenAQ API]        ──hourly poll (AUTOMATED)─┘         (data.gov.in done,       │
[Kaggle historical] ──one-time load (done)               OpenAQ/Open-Meteo       ▼
                                                           next)             Processed (CSV)
                                                                                    │
        [check_pipeline_health.py] ── run on-demand to verify all of the above ──> (pass/fail report)
                                                                                    ▼
                                                                          MySQL (not yet built)
                                                                                    │
                                                                                    ▼
                                                                          Analysis / ML layer
```

---

## Themes Worth Emphasizing in an Interview

1. **Verification over assumption, repeatedly.** A downloaded file's actual date range, a raw record's actual empty value, an automated task's actual unattended file drop, a "Ready/Enabled" status that turned out to be misleading — the constant move was checking the real evidence, not trusting the label.
2. **Documentation — including your own project's — can be wrong, and fixing it when you find that out is part of the job.**
3. **Security is a default habit,** applied even to a low-stakes credential, because the habit is what generalizes.
4. **Knowing when to stop chasing a low-value fix** (the wake-computer/retry-on-failure Task Scheduler bugs) versus **when a surprising result deserves real investigation** (the AC-power silent failure) — both are judgment calls, and this phase required making both correctly at different points.
5. **Designing for "nobody's watching":** clear logging, graceful failure (skip-and-log instead of crash), flagging instead of silently discarding bad data, and — critically — building an actual way to check on the system later instead of just hoping it keeps working.
6. **A subtle bug is often invisible specifically because every individual status check looks fine** — real debugging meant cross-referencing against a known-good control (the working data.gov.in task) rather than staring harder at the broken one.

---

## Quick Q&A Cheat Sheet

**"Why not just use one data source?"**
The primary government source has no historical API — only a live snapshot — so a second source, plus our own scheduled polling, is the only way to build history or cross-check reliability.

**"What was the hardest technical problem?"**
Two candidates, both good to have ready: (1) realizing the primary source's numbers were pre-computed health-severity index scores, not raw concentrations — solved by reasoning through why the documented AQI calculation only makes sense under that interpretation; (2) a scheduling bug where two automated tasks looked completely healthy by every visible status indicator, yet were silently never firing — solved by cross-referencing against a known-working task and finding one specific missing configuration flag.

**"How do you know your automation actually works, not just that it's configured?"**
By checking for new files that appeared with nobody at the keyboard — and, after the AC-power bug, by explicitly not trusting "Ready/Enabled" status alone, since that specific bug proved those can be true while nothing is actually running.

**"What would you do differently, or next?"**
Extend the same cleaning pattern to OpenAQ and Open-Meteo, then move into anomaly detection and short-horizon forecasting using the cleaned data plus the Kaggle historical bootstrap.
