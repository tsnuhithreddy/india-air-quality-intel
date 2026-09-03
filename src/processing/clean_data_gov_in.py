"""
Cleans raw data.gov.in CPCB snapshots into a standardized long-format CSV:
one row per (station, pollutant, timestamp) reading.

IMPORTANT: min/max/avg here are AQI SUB-INDEX scores (0-500 health-severity
scale), NOT raw pollutant concentrations - confirmed during Phase 3 (see
DATA_SOURCES_LOG.md). Columns are named accordingly to avoid future confusion.

Handles:
- Type casting (raw values arrive as strings)
- Sentinel/error value flagging (negative values, suspiciously high values
  like 999) per Phase 1's documented data-quality risks
- Pollutant name standardization (e.g. "OZONE" -> "O3")
- Parsing last_update into a proper datetime

Does NOT drop flagged rows - just marks them, so downstream analysis can
decide how to handle them.
"""
import sys
import os
import json
import glob
import pandas as pd
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(PROJECT_ROOT, "src", "utils"))
sys.path.append(os.path.join(PROJECT_ROOT, "config"))

from logger import get_logger
import config

log = get_logger("clean_data_gov_in")

POLLUTANT_NAME_MAP = {
    "OZONE": "O3",
    "PM2.5": "PM2.5",
    "PM10": "PM10",
    "NO2": "NO2",
    "SO2": "SO2",
    "CO": "CO",
    "NH3": "NH3",
}


def load_raw_file(filepath):
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("records", [])


def clean_records(records):
    df = pd.DataFrame(records)

    # Raw values arrive as strings - convert to numeric, non-numeric -> NaN
    # Renamed from min_value/max_value/avg_value to make clear these are
    # sub-index scores, not concentrations - see module docstring.
    df["sub_index_min"] = pd.to_numeric(df["min_value"], errors="coerce")
    df["sub_index_max"] = pd.to_numeric(df["max_value"], errors="coerce")
    df["sub_index_avg"] = pd.to_numeric(df["avg_value"], errors="coerce")
    df = df.drop(columns=["min_value", "max_value", "avg_value"])

    df["pollutant_id"] = df["pollutant_id"].map(lambda p: POLLUTANT_NAME_MAP.get(p, p))
    df["last_update"] = pd.to_datetime(df["last_update"], format="%d-%m-%Y %H:%M:%S", errors="coerce")

    # Flag (don't drop) suspicious values
    df["flag_negative"] = df["sub_index_avg"] < 0
    df["flag_sentinel"] = df["sub_index_avg"].isin([999, 9999, -999])
    df["flag_missing"] = df["sub_index_avg"].isna()
    df["is_suspicious"] = df["flag_negative"] | df["flag_sentinel"] | df["flag_missing"]

    return df


def process_file(filepath):
    log.info(f"Processing {filepath}...")
    df = clean_records(load_raw_file(filepath))

    total = len(df)
    suspicious = df["is_suspicious"].sum()
    log.info(f"{total} records processed, {suspicious} flagged as suspicious ({suspicious/total:.1%})")

    return df


def save_processed(df):
    now = datetime.now()
    date_folder = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y%m%d_%H%M")

    out_dir = os.path.join(PROJECT_ROOT, config.PROCESSED_DATA_DIR, "data_gov_in", date_folder)
    os.makedirs(out_dir, exist_ok=True)

    out_path = os.path.join(out_dir, f"data_gov_in_clean_{timestamp}.csv")
    df.to_csv(out_path, index=False)

    log.info(f"Saved cleaned data to {out_path}")
    return out_path


if __name__ == "__main__":
    # Process just the single most recent raw file for now - batch processing
    # of all historical raw files comes later, once this logic is verified.
    raw_files = sorted(glob.glob(os.path.join(
        PROJECT_ROOT, config.RAW_DATA_DIR, "data_gov_in", "*", "*.json"
    )))

    if not raw_files:
        log.error("No raw data.gov.in files found.")
    else:
        df = process_file(raw_files[-1])
        save_processed(df)