"""
Cleans raw OpenAQ v3 snapshots (locations metadata + latest readings) into a
standardized long-format CSV: one row per (station, pollutant, timestamp) reading.

IMPORTANT: Unlike data.gov.in (which reports 0-500 AQI sub-indices), OpenAQ
reports genuine physical concentrations (typically in µg/m³ or ppm).
Columns are named `concentration_value` and `unit` to make this distinction explicit.

Handles:
- Sensor lookup: maps sensor ID to pollutant parameter name, display name, and units
- Type casting: ensures numeric concentration values
- Timestamp parsing: standardizes local (+05:30) and UTC datetimes
- Pollutant standardization: maps parameter codes to unified standard names (e.g. "PM2.5", "O3")
- Flag-don't-drop quality checks:
    - flag_negative: value < 0
    - flag_sentinel: known sentinel error codes (e.g. 999, 9999, -999)
    - flag_missing: missing/null values
    - flag_zero: 0.0 reading (often uncalibrated/idle sensor)
    - is_suspicious: combination of any quality flag

Does NOT drop flagged rows - marks them with boolean columns so downstream
models and analysis can filter or impute cleanly.
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

log = get_logger("clean_openaq")

POLLUTANT_NAME_MAP = {
    "pm25": "PM2.5",
    "pm10": "PM10",
    "no2": "NO2",
    "so2": "SO2",
    "co": "CO",
    "o3": "O3",
    "ozone": "O3",
    "nh3": "NH3",
    "bc": "BC",
    "pm1": "PM1",
}


def build_sensor_lookup(locations_file):
    """
    Builds two dictionaries from openaq_locations_*.json:
    1. sensor_map: sensor_id -> sensor and pollutant metadata
    2. location_map: location_id -> station coordinates and metadata
    """
    log.info(f"Loading sensor metadata from {locations_file}...")
    with open(locations_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    sensor_map = {}
    location_map = {}
    for loc in data.get("results", []):
        loc_id = loc.get("id")
        loc_name = loc.get("name")
        locality = loc.get("locality")
        coords = loc.get("coordinates") or {}
        lat = coords.get("latitude")
        lon = coords.get("longitude")

        location_map[loc_id] = {
            "station_id": loc_id,
            "station_name": loc_name,
            "locality": locality,
            "latitude": lat,
            "longitude": lon,
        }

        for sensor in loc.get("sensors", []):
            sensor_id = sensor.get("id")
            param = sensor.get("parameter") or {}
            param_name = param.get("name", "").lower()
            param_display = param.get("displayName") or POLLUTANT_NAME_MAP.get(param_name, param_name.upper())
            units = param.get("units", "")

            sensor_map[sensor_id] = {
                "station_id": loc_id,
                "station_name": loc_name,
                "locality": locality,
                "latitude": lat,
                "longitude": lon,
                "pollutant_id": POLLUTANT_NAME_MAP.get(param_name, param_name.upper()),
                "pollutant_display": param_display,
                "unit": units,
            }

    log.info(f"Indexed metadata for {len(sensor_map)} sensors across {len(location_map)} locations.")
    return sensor_map, location_map


def clean_readings(latest_file, sensor_map, location_map):
    """
    Parses openaq_latest_*.json readings and joins with sensor metadata.
    Returns a cleaned pandas DataFrame with quality flags.
    """
    log.info(f"Loading latest readings from {latest_file}...")
    with open(latest_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    rows = []
    stations = data.get("readings", [])

    for st in stations:
        station_id = st.get("station_id")
        station_name = st.get("station_name")
        readings_list = st.get("readings", [])
        loc_meta = location_map.get(station_id, {})

        # Station has no live readings reported
        if not readings_list:
            rows.append({
                "station_id": station_id,
                "station_name": station_name or loc_meta.get("station_name"),
                "locality": loc_meta.get("locality"),
                "sensor_id": None,
                "pollutant_id": None,
                "concentration_value": None,
                "unit": None,
                "timestamp_local": None,
                "timestamp_utc": None,
                "latitude": loc_meta.get("latitude"),
                "longitude": loc_meta.get("longitude"),
                "flag_negative": False,
                "flag_sentinel": False,
                "flag_missing": True,
                "flag_zero": False,
                "is_suspicious": True,
            })
            continue

        for r in readings_list:
            sensor_id = r.get("sensorsId")
            meta = sensor_map.get(sensor_id, {})

            dt = r.get("datetime") or {}
            dt_local = dt.get("local")
            dt_utc = dt.get("utc")

            val = r.get("value")
            coords = r.get("coordinates") or {}
            lat = coords.get("latitude") or meta.get("latitude") or loc_meta.get("latitude")
            lon = coords.get("longitude") or meta.get("longitude") or loc_meta.get("longitude")

            pollutant_id = meta.get("pollutant_id")
            unit = meta.get("unit")
            locality = meta.get("locality") or loc_meta.get("locality")

            rows.append({
                "station_id": station_id,
                "station_name": station_name or loc_meta.get("station_name"),
                "locality": locality,
                "sensor_id": sensor_id,
                "pollutant_id": pollutant_id,
                "concentration_value": val,
                "unit": unit,
                "timestamp_local": dt_local,
                "timestamp_utc": dt_utc,
                "latitude": lat,
                "longitude": lon,
            })

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    # Numeric conversion
    df["concentration_value"] = pd.to_numeric(df["concentration_value"], errors="coerce")

    # Standardize timestamps
    if "timestamp_local" in df.columns:
        df["timestamp_local"] = pd.to_datetime(df["timestamp_local"], errors="coerce")
    if "timestamp_utc" in df.columns:
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], errors="coerce")

    # Quality Flags (Flag, Don't Drop)
    df["flag_negative"] = df["concentration_value"] < 0
    df["flag_sentinel"] = df["concentration_value"].isin([999, 9999, -999])
    df["flag_missing"] = df["concentration_value"].isna()
    df["flag_zero"] = df["concentration_value"] == 0.0
    df["is_suspicious"] = (
        df["flag_negative"] | df["flag_sentinel"] | df["flag_missing"] | df["flag_zero"]
    )

    return df


def process_latest_pair(latest_file=None, locations_file=None):
    """
    Finds and cleans the most recent OpenAQ raw files.
    """
    if not locations_file:
        loc_files = sorted(glob.glob(os.path.join(
            PROJECT_ROOT, config.RAW_DATA_DIR, "openaq", "*", "openaq_locations_*.json"
        )))
        if not loc_files:
            log.error("No openaq_locations JSON files found.")
            return None
        locations_file = loc_files[-1]

    if not latest_file:
        lat_files = sorted(glob.glob(os.path.join(
            PROJECT_ROOT, config.RAW_DATA_DIR, "openaq", "*", "openaq_latest_*.json"
        )))
        if not lat_files:
            log.error("No openaq_latest JSON files found.")
            return None
        latest_file = lat_files[-1]

    sensor_map, location_map = build_sensor_lookup(locations_file)
    df = clean_readings(latest_file, sensor_map, location_map)

    total_rows = len(df)
    suspicious = df["is_suspicious"].sum()
    missing = df["flag_missing"].sum()
    zeros = df["flag_zero"].sum()

    log.info(
        f"Processed {total_rows} readings: {suspicious} flagged as suspicious "
        f"({suspicious / total_rows:.1%}), {missing} missing, {zeros} zero-readings."
    )

    return df


def save_processed(df):
    """
    Saves cleaned OpenAQ DataFrame to data/processed/openaq/YYYY-MM-DD/openaq_clean_YYYYMMDD_HHMM.csv
    """
    now = datetime.now()
    date_folder = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y%m%d_%H%M")

    out_dir = os.path.join(PROJECT_ROOT, config.PROCESSED_DATA_DIR, "openaq", date_folder)
    os.makedirs(out_dir, exist_ok=True)

    out_path = os.path.join(out_dir, f"openaq_clean_{timestamp}.csv")
    df.to_csv(out_path, index=False)

    log.info(f"Saved cleaned OpenAQ data to {out_path}")
    return out_path


if __name__ == "__main__":
    df = process_latest_pair()
    if df is not None and not df.empty:
        save_processed(df)
    else:
        log.error("No data processed.")
