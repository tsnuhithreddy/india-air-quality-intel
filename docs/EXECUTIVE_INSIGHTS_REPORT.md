# Executive Insights Report

**India Urban Air Quality Intelligence & Early-Warning System**

Last updated 10 October 2026. The live-pipeline status below is as of 9 October.

This is the short version of twelve phases of work. If you only read one document in this repo, read this one. The phase write-ups (PHASE1 to PHASE12) and `docs/DATA_SOURCES_LOG.md` have the detail behind every claim here.

---

## The five things that matter

1. **Winter pollution is a northern problem.** Delhi, Lucknow and Patna swing by roughly three times between the monsoon and November. Chennai, Bengaluru and Hyderabad barely move all year.
2. **One of my own early findings was wrong.** Delhi's sharp AQI spike in 2017 looked real. It was mostly a hole in the data that happened to fall in the cleanest months of the year.
3. **Tomorrow's AQI is fairly easy to predict, but the worst days are not.** A model that predicts "tomorrow will look like today" is hard to beat. Where a model did beat it, the gain was modest. The more important finding is that average error hides how often the forecast misses a severe day.
4. **For four of seven cities I can't say whether the early warnings work.** Their test window had no severe days at all, so there was nothing to catch.
5. **The live pipeline works, but it depends on things I don't control.** The government API has been down since 25 September, and the pipeline only runs while my laptop is on.

---

## What the project is

I pulled air quality data from four places and put it in one MySQL database:

- **data.gov.in (CPCB):** live, hourly, but only a snapshot. There is no history.
- **OpenAQ:** live, used as a backup and cross-check.
- **Open-Meteo:** weather, live and forecast.
- **Kaggle (CPCB-sourced):** daily history, 2015 to July 2020, for the 10 of my 11 target cities that it covers. Pune isn't in it.

The database has 3 dimension tables and 8 fact tables, about 1.3 million rows, most of them Kaggle history.

One thing shaped the design more than anything else. data.gov.in's numbers are AQI sub-indices on a 0 to 500 scale. OpenAQ's numbers are real concentrations in µg/m³. They look similar and mean different things, so they live in separate tables and I never compare them directly.

---

## What the data says

### Seasonality

Delhi's average AQI peaks in November (about 388) and December (about 374) and bottoms out in August (about 135). That is a roughly 3x swing, which fits what's known about crop burning, winter inversions and monsoon washout.

Lucknow and Patna follow the same shape. Chennai, Bengaluru and Hyderabad stay between roughly 80 and 150 all twelve months. Mumbai has a real but much weaker winter rise.

### The 2017 spike that wasn't

A chart of Delhi's yearly average showed 2017 far above its neighbours (371, against 294 in 2016 and 256 in 2018). I nearly reported it.

Checking gap lengths showed Delhi was missing 83 days (9 June to 31 August 2017) and another 24 days in September. Those are monsoon months, when Delhi's air is cleanest. About 88% of Delhi's June to September days that year were missing, so the 2017 average was built almost entirely from the dirty months.

When I left June to September out of every year, 2017 and 2016 came out essentially tied (353.6 and 357.2). The honest picture is a moderately high 2016 and 2017, then a steady decline into 2020. Patna, Hyderabad and Mumbai had the same hole, so any claim about 2017 in those cities needs the same caution. 2020 is a partial year, since the data stops in July.

### Weather (Delhi only)

Wind speed lowers AQI, and the effect holds even inside a single season (correlation of about -0.21 over the full year, -0.28 in winter alone). That makes it a real, direct effect.

Temperature looked important over the full year (about -0.27 for daily maximum), but inside winter alone the sign flipped to +0.36. Most of the full-year correlation was just the calendar: cold months are dirty and warm months are clean. Rain helps but is partly confounded by season too. Heavy rain doesn't guarantee clean air, but past about 20 mm the day's AQI never went above roughly 350.

I only did this for Delhi, because that's the only city where I pulled historical weather.

### Anomalies

I flagged unusual days using a baseline of the median and median absolute deviation for each city and calendar month, and a modified z-score cutoff of 3.5. A plain rolling average would have called every northern winter abnormal. Median-based statistics also don't get dragged around by one bad station.

Out of 74,826 usable readings, 2,002 were flagged (2.68%). Two cities stood out and I checked both:

- **Chennai (7.8% flagged)** is high because one of its stations (Manali) sits in an industrial zone and is normally dirtier than the rest of the city. A city-wide baseline over-flags its ordinary days. That's a limit of working at city level, not bad data.
- **Bengaluru's Kadabesanahalli station** produced many of the most extreme scores. Its flags were spread across five of six years and tapered off, so I kept it. It looks like a genuinely spike-prone location.

I left one station out entirely: Maninagar in Ahmedabad (GJ001). Its AQI values go as high as 2,049 on a scale that stops at 500, and they don't match its own pollutant readings. It was Ahmedabad's only Kaggle station, so Ahmedabad drops out of the anomaly work, which covers 9 of 11 cities.

---

## Forecasting and early warning

### How the forecasts did

I built 1-day and 3-day forecasts for 7 cities and tested them on January to July 2020 (183 days) that the models never saw in training. The bar to beat was persistence, meaning "tomorrow equals today". It beat a seasonal-average baseline by 2 to 3 times in every city, so it's a hard bar.

A per-city Ridge regression (seasonal terms plus recent values) beat persistence in Bengaluru, Lucknow and Patna, tied in Chennai, and lost in Delhi, Hyderabad and Mumbai. The gains were small. In Patna the 1-day error went from 52.6 to 48.3. In Delhi, Ridge was slightly worse (43.8 against 41.4), and tuning didn't change that.

The practical result is a simple rule: use Ridge for Bengaluru, Chennai, Lucknow and Patna, and persistence for Delhi, Hyderabad and Mumbai. The same split held at both horizons.

### Where it matters: catching the worst days

I turned forecasts into a three-tier priority (Low, Watch, Alert), with Alert meaning Very Poor or Severe. Then I checked how many genuinely severe days the system caught.

| City | Real severe days (1-day / 3-day) | Caught at 1-day | Caught at 3-day |
|---|---|---|---|
| Patna | 38 / 31 | 84% | 97% |
| Delhi | 25 / 22 | 68% | 41% |
| Lucknow | 13 / 11 | 38% | 18% |
| Bengaluru, Chennai, Hyderabad, Mumbai | 0 / 0 | untestable | untestable |

Delhi and Lucknow looked only a little worse than average on error alone. This table is what shows the problem. A Delhi forecast three days out would miss most severe days.

### What I built from that

Rather than present every city's alert with equal confidence, each warning carries a reliability label:

- **Reliable:** Patna.
- **Known unreliable:** Delhi and Lucknow. Shown as "Alert, low confidence, recommend review".
- **Unvalidated:** the four cities with no severe days in the test window. That is a different kind of uncertainty from Delhi's. It means untested, not proven weak.

The warnings table has 2,115 rows. 144 forecast days triggered an alert (75 at 1-day, 69 at 3-day), made up of 34 new episodes and 110 continuing days. Severe pollution comes in long runs. At 1-day, Patna had 38 alert days but only 6 separate onsets. For a warning system, the job is mostly to catch the onset.

I also tested whether the earlier anomaly flags could back up a weak Delhi or Lucknow alert. The answer is "can't tell". Delhi had no anomaly-flagged severe days in the test window, and Lucknow had one.

---

## What I'd trust and what I wouldn't

**I'd trust:**
- The seasonal pattern and the north/south split.
- The 2017 correction.
- Wind's effect on Delhi's AQI.
- Patna's alerts.
- The per-city choice of model.

**I wouldn't trust yet:**
- Delhi's and Lucknow's alerts, especially at 3 days.
- Any claim that the alerts work in Bengaluru, Chennai, Hyderabad or Mumbai.
- Any 2015 to 2017 trend claim for Mumbai, Kolkata or Jaipur (see below).

---

## Data problems to know about

| Problem | Effect |
|---|---|
| Ahmedabad GJ001 has AQI values far above 500 | Excluded from anomaly and forecast work |
| Mumbai's main station is blank for all of 2015 to 2017 | Real Mumbai history starts in 2018 |
| Kolkata's data starts 10 April 2018, Jaipur's 14 June 2017 | Their history is shorter than 2015 to 2020 |
| Lucknow is missing 15 February to 12 June 2018 | Excluded from training |
| Patna's completeness falls Feb to Jun 2020 | Possibly lockdown-related; I haven't confirmed it |
| Delhi went from 10 stations in 2015 to 38 from 2018 | A city average partly reflects which stations existed that year |
| Pune has no Kaggle history | No historical baseline; live data only |
| data.gov.in sub-indices aren't concentrations | Can't be compared directly with OpenAQ |

---

## Operations: what broke

The live pipeline polls three APIs every hour through Windows Task Scheduler and loads them into MySQL. It has failed in ways worth recording.

**Earlier incident.** The dashboard's freshness figure reached 595 hours. Ingestion had kept running, but cleaning and loading were manual and nobody had run them for weeks. That's why `run_clean_and_load.py` exists. It treats a stale input file as a failure even if nothing crashes.

**25 September to 9 October.** Four separate problems overlapped and looked like one:

1. **Task Scheduler settings.** The tasks were set to run only while I was logged on. Fixing it took a dedicated Windows account with administrator rights, since this Windows Home edition lacks the policy tool that would normally grant the right.
2. **data.gov.in's API is unreachable.** The last good file is from 25 September. My network, DNS, proxy and firewall are fine. The main data.gov.in site and CPCB's own site connect normally, and only the API host fails. The error kept changing (refused, DNS failure, 502, timeout), which looks like an unstable server and not a credentials problem. It was still failing on 9 October.
3. **A 12.6-hour gap across all three sources.** I first suspected sleep. The Windows event log showed I had shut the laptop down.
4. **OpenAQ went quiet.** Its 20 sampled stations haven't reported anything newer than 7 October at 20:00. The loader is working and gets fresh files, but they contain nothing new. I suspect the cause is upstream, but I haven't confirmed it.

Along the way I found two copies of the MySQL user and password in my `.env` file. That one mattered. The loaders only used the least-privilege account because it came second in the file. Reordering would have silently switched them to root. I deleted the root pair.

The staleness check caught all of this. But nothing sends a notification, so I found each problem by looking at a dashboard.

One reading note: the "Hours Since Last Update" figure on the Overview page tracks data.gov.in only. It doesn't say anything about OpenAQ or weather.

---

## Limits of this work

- **The forecasts and early warnings are retrospective.** They're scored on January to July 2020 history, not on live data. Page 5 of the dashboard says so.
- **The test window is short.** 183 days, with few severe days outside Delhi, Lucknow and Patna. It also overlaps the spring 2020 lockdown, which I haven't examined separately.
- **Everything historical stops in July 2020.** Nothing here tells us how the air behaves today.
- **Weather isn't in the forecasts.** I found wind matters but didn't use it as a feature.
- **Forecasting lives in a notebook.** It has no script, scheduler or database table.
- **The dashboard isn't published.** Publish to web returns an admin-permission error, so it only exists in Power BI Desktop.
- **Polling needs the laptop on.** Any time it's off or asleep, hourly polls are lost.

---

## What I'd do next

1. **Restart live scoring** once data.gov.in recovers and enough hourly history has built up.
2. **Add notifications** for failed runs and for Alert-tier warnings.
3. **Move polling to an always-on machine,** such as a spare PC or a small cloud VM.
4. **Add wind speed to the forecast,** then re-check Delhi and Lucknow's recall.
5. **Try station-level anomaly detection,** which would handle the Chennai industrial station without a workaround.
6. **Re-test the Alert tier** once the data includes severe days in the four untested cities.
