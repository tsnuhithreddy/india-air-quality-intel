# Phase 11 — Early Warning System

**Project:** India Urban Air Quality Intelligence & Early-Warning System
**Status:** Complete

## Overview

Phase 10 produced a validated 1-day and 3-day AQI forecast, along with an honest account of where that forecast could and could not be trusted. Phase 11 turns that forecast into a decision-support system: it defines what counts as a warning, assigns each city a reliability tier based on Phase 10's own evaluation results, and records every scored prediction in a queryable database table.

No new modeling or new data was introduced in this phase. It is a decision layer built entirely on top of Phase 10's existing, already-validated predictions.

## Design Decisions

Four decisions were settled before any implementation:

1. **Trigger condition.** A warning fires when the forecast category crosses into `Alert` (India's "Very Poor"/"Severe" AQI bands), reusing Phase 10's already-validated category tiers rather than introducing a new, unvalidated magnitude-of-jump threshold.
2. **Trust level per city.** Taken directly from Phase 10's Alert-tier recall results, not re-derived: Patna (reliable, 84–97% recall at both horizons), Delhi and Lucknow (known unreliable, recall degrades with horizon), and four cities with zero real Alert-tier days in their 2020 test window (unvalidated — genuinely untested, not confirmed unreliable).
3. **Safeguard for the unreliable cities.** See below — this was the one open question this phase needed to resolve empirically.
4. **Deliverable scope.** Following the pattern used for Phase 9's anomaly flags (notebook → script → a real MySQL table with constraints and a verified duplicate-safety check), since a warning system needs to be queryable, not just analyzed.

## Testing Anomaly Flags as Corroboration

A candidate safeguard for Delhi and Lucknow's weak Alert-tier recall was to corroborate a low-confidence warning using Phase 9's anomaly flags. This was tested rather than assumed: for both cities, at both horizons, Alert-tier recall was compared on anomaly-flagged target days versus non-flagged days.

| City | Horizon | Anomaly-flagged Alert days | Recall | Non-flagged Alert days | Recall |
|---|---|---|---|---|---|
| Delhi | 1 | 0 | n/a | 25 | 68.0% |
| Delhi | 3 | 0 | n/a | 22 | 40.9% |
| Lucknow | 1 | 1 | 100%* | 12 | 33.3% |
| Lucknow | 3 | 0 | n/a | 11 | 18.2% |

*Based on a single data point; not a generalizable result.

Delhi has zero anomaly-flagged Alert days in its entire test window, so corroboration cannot be tested there at all. Lucknow has exactly one, which is not evidence either way. The result is "untestable with the available data," not "doesn't work." This ruled out a signal-based safeguard and pointed to a structural one: label the uncertainty explicitly rather than attempting to resolve it computationally with insufficient data.

## Reliability Labeling

Delhi/Lucknow's weak-but-proven recall and the four flat-seasonality cities' untested status are different kinds of uncertainty, so they are labeled separately rather than collapsed into one generic "low confidence" category:

- **`reliable`** — Patna. Shown as full-confidence `Alert`.
- **`known_unreliable`** — Delhi, Lucknow. Shown as `Alert — Low Confidence (Recommend Review)`.
- **`unvalidated`** — Bengaluru, Chennai, Hyderabad, Mumbai. Shown as `Alert — Unvalidated (No Historical Severe Events)`.

## Episode Detection

Each triggered day is tagged `is_new_episode`: true only if the immediately preceding available prediction for that city/horizon was not also triggered. This distinguishes the onset of a severe event from its continuation, since an early-warning system is primarily useful at onset.

Corrected episode counts:

| City | Horizon | Triggered | New episodes | Continuations |
|---|---|---|---|---|
| Delhi | 1 | 26 | 9 | 17 |
| Delhi | 3 | 25 | 9 | 16 |
| Lucknow | 1 | 11 | 6 | 5 |
| Lucknow | 3 | 7 | 2 | 5 |
| Patna | 1 | 38 | 6 | 32 |
| Patna | 3 | 37 | 2 | 35 |

Patna's severe pollution arrives in long sustained runs rather than isolated spikes: 38 triggered days at the 1-day horizon come from only 6 distinct onset events. An operational system for Patna mainly needs to catch 6 onset events correctly, not make 38 independent daily calls.

One disclosed limitation: with gaps in the underlying data, "new episode" means new relative to the nearest available prior prediction, not strictly relative to the previous calendar day.

## Known Issues Found and Fixed

**Episode-detection dtype bug.** The first implementation applied the `~` operator to a boolean column that `groupby().shift(1)` had silently upcast to `object` dtype (due to the `NaN` introduced at each group's first row). On an object-dtype column, `~` performs a bitwise complement rather than logical negation. The error happened to produce numerically identical output in most cases, which masked it: the result showed zero continuations across 144 triggered days, i.e. every Alert day registered as a new episode. This was caught because a perfectly clean result on a quantity expected to vary was itself suspicious. The fix was an explicit `.astype(bool)` after the shift, which revealed 110 real continuations, consistent with the day-to-day AQI autocorrelation already established in Phase 8.

**Unsafe default in the priority-tier function.** A discrepancy surfaced during verification: `Alert` plus `Alert — Low Confidence` summed to 150, six more than the independently verified trigger total of 144. The cause was an unguarded `else` branch in the priority-tier function, which silently returned `'Alert'` for 6 rows where `predicted_category` was genuinely missing (a known Mumbai 3-day data gap) — even though those same rows correctly evaluated `triggered = False`. The function was rewritten to return `NaN` explicitly for missing input and to raise `ValueError` on any unrecognized category, converting a silent-failure class of bug into a loud one. Corrected totals: `Alert: 75`, `Alert — Low Confidence: 69`, genuinely missing: 6 — summing to exactly 144, matching the independently verified trigger count.

## Database Table

`fact_early_warnings` follows the same design discipline as `fact_kaggle_anomaly_flags` from Phase 9: a real foreign key to `dim_city`, a unique constraint preventing duplicate warnings, flag-don't-drop throughout, and nullable value columns representing genuine data gaps rather than fabricated values.

```sql
CREATE TABLE fact_early_warnings (
    warning_id INT AUTO_INCREMENT PRIMARY KEY,
    city_id INT NOT NULL,
    reading_date DATE NOT NULL,
    target_date DATE NOT NULL,
    horizon TINYINT NOT NULL,
    model_used ENUM('ridge', 'persistence') NOT NULL,
    actual_aqi DECIMAL(6,2) NULL,
    predicted_aqi DECIMAL(6,2) NULL,
    actual_category VARCHAR(20) NULL,
    predicted_category VARCHAR(20) NULL,
    triggered BOOLEAN NOT NULL,
    reliability_tier ENUM('reliable', 'known_unreliable', 'unvalidated') NOT NULL,
    warning_label VARCHAR(60) NULL,
    is_new_episode BOOLEAN NOT NULL,
    FOREIGN KEY (city_id) REFERENCES dim_city(city_id),
    UNIQUE KEY uq_warning (city_id, target_date, horizon)
);
```

`horizon` is a plain `TINYINT` rather than an `ENUM`, so extending to a 7-day horizon in a future phase only requires new rows, not a schema change — consistent with how `dim_station.source_system` was widened rather than rebuilt in Phase 6.

**Loading.** `load_early_warnings.py` reuses the pattern established by `load_kaggle_anomalies.py`: a pre-loaded city-name lookup, explicit boolean conversion, and MySQL error-code-1062 duplicate handling.

**Verification.**
- First run: 2,115 inserted, 0 duplicates, 0 errors — matching the source CSV exactly.
- `SELECT COUNT(*)`: 2,115, cross-checked against the `warning_label` breakdown (1,029 Low / 936 Watch / 75 Alert / 69 Alert — Low Confidence / 6 genuinely NULL), which sums to exactly 2,115.
- `reliability_tier` totals (unvalidated: 0 triggered, known_unreliable: 69, reliable: 75) sum to 144, matching the notebook's own trigger count.
- Second run on the identical file: 0 inserted, 2,115 skipped as duplicates, 0 errors — confirming the `UNIQUE(city_id, target_date, horizon)` constraint works as intended, rather than assuming it from the schema definition alone.

## Scope

**Not included in this phase:**
- Live scoring against data.gov.in or OpenAQ — this operates on the same 2020 historical test window used in Phase 10, consistent with the deferral of live-source scoring in Phases 9 and 10 until sufficient hourly history accumulates.
- Automated scheduling of the warning pipeline — run by hand, as with every loader in the project to date.
- A notification or alerting mechanism. `fact_early_warnings` is a queryable record, not a system that pushes alerts.
- A structural safeguard beyond the confidence label for Delhi and Lucknow (e.g. a second model, wider confidence bands). Labeling the uncertainty honestly was judged sufficient for this phase's scope.
