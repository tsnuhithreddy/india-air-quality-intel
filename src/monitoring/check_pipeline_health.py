"""
Health check for the automated ingestion pipeline. Run this anytime to get
a real snapshot of whether data is actually flowing correctly - not just
whether Task Scheduler *says* success, but whether valid data is landing
on schedule with no silent gaps or corruption.

Checks per source:
1. Are today's files parseable JSON, and a sane size (not empty/truncated)?
2. For data.gov.in specifically (the only hourly-automated source): are
   there any gaps between snapshots bigger than expected?
Plus: any ERROR lines in today's log file.
"""
import sys
import os
import json
import glob
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(PROJECT_ROOT, "src", "utils"))
sys.path.append(os.path.join(PROJECT_ROOT, "config"))

import config

TODAY = datetime.now().strftime("%Y-%m-%d")
MIN_EXPECTED_SIZE_BYTES = 1000  # a real snapshot is hundreds of KB; anything tiny is suspicious


def check_source_files(source_name, max_gap_minutes=None):
    print(f"\n--- {source_name} ---")
    pattern = os.path.join(PROJECT_ROOT, config.RAW_DATA_DIR, source_name, TODAY, "*.json")
    files = sorted(glob.glob(pattern))

    if not files:
        print(f"  [MISSING] No files found for today ({TODAY}).")
        return

    print(f"  {len(files)} file(s) found today.")

    bad_files = []
    for f in files:
        size = os.path.getsize(f)
        if size < MIN_EXPECTED_SIZE_BYTES:
            bad_files.append((f, f"too small ({size} bytes)"))
            continue
        try:
            with open(f, encoding="utf-8") as fh:
                json.load(fh)
        except json.JSONDecodeError:
            bad_files.append((f, "invalid/corrupted JSON"))

    if bad_files:
        print(f"  [PROBLEM] {len(bad_files)} bad file(s):")
        for f, reason in bad_files:
            print(f"      {os.path.basename(f)} - {reason}")
    else:
        print(f"  [OK] All files parse correctly and are a reasonable size.")

    if max_gap_minutes:
        timestamps = []
        for f in files:
            name = os.path.basename(f)
            try:
                ts_str = name.split("_")[-2] + name.split("_")[-1].replace(".json", "")
                timestamps.append(datetime.strptime(ts_str, "%Y%m%d%H%M"))
            except (ValueError, IndexError):
                continue
        timestamps.sort()

        gaps = []
        for i in range(1, len(timestamps)):
            gap = (timestamps[i] - timestamps[i - 1]).total_seconds() / 60
            if gap > max_gap_minutes:
                gaps.append((timestamps[i - 1], timestamps[i], gap))

        if gaps:
            print(f"  [WARNING] {len(gaps)} gap(s) over {max_gap_minutes} min:")
            for start, end, gap in gaps:
                print(f"      {start.strftime('%H:%M')} -> {end.strftime('%H:%M')} ({gap:.0f} min gap)")
        else:
            print(f"  [OK] No gaps larger than {max_gap_minutes} minutes between snapshots.")


def check_todays_log_for_errors():
    print(f"\n--- Today's log ({TODAY}.log) ---")
    log_path = os.path.join(PROJECT_ROOT, config.LOG_DIR, f"{TODAY}.log")
    if not os.path.exists(log_path):
        print("  [MISSING] No log file found for today.")
        return

    with open(log_path, encoding="utf-8") as f:
        error_lines = [line.strip() for line in f if "| ERROR" in line]

    if error_lines:
        print(f"  [WARNING] {len(error_lines)} ERROR line(s) found (showing last 5):")
        for line in error_lines[-5:]:
            print(f"      {line}")
    else:
        print("  [OK] No ERROR lines today.")


if __name__ == "__main__":
    print(f"=== Pipeline Health Check — {TODAY} ===")
    check_source_files("data_gov_in", max_gap_minutes=90)  # hourly + buffer for delays
    check_source_files("openaq")       # manual/on-demand - no gap check
    check_source_files("open_meteo")   # manual/on-demand - no gap check
    check_todays_log_for_errors()
    print('\nAlso check separately: Get-ScheduledTaskInfo -TaskName "AQI - data.gov.in hourly poll"')