"""
Cleans raw Open-Meteo weather snapshots into standardized CSVs:
1. Current weather snapshot (1 row per city)
2. 24-hour hourly weather forecast (24 rows per city)

Meteorological covariates (temperature, humidity, wind speed/direction,
precipitation, pressure) are key drivers of pollutant dispersion and accumulation.

Handles:
- Extracting city-level current conditions and hourly forecasts
- Standardizing metric column names and units:
    - temperature_c (°C)
    - relative_humidity_pct (%)
    - wind_speed_kmh (km/h)
    - wind_direction_deg (0-360°)
    - precipitation_mm (mm)
    - surface_pressure_hpa (hPa)
- Standardizing ISO timestamps to datetime objects (local IST)
- Physical range quality checks:
    - flag_humidity_invalid: humidity not in [0, 100]
    - flag_temperature_extreme: temperature < -20°C or > 60°C
    - flag_wind_negative: wind speed < 0
    - flag_pressure_invalid: surface pressure < 800 or > 1100 hPa
    - is_suspicious: combination of any quality flags

Does NOT drop flagged rows - marks them with boolean columns.
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

log = get_logger("clean_open_meteo")


def clean_current_weather(cities_data):
    """
    Extracts and standardizes current weather observations for all cities.
    Returns a pandas DataFrame.
    """
    rows = []
    for city_entry in cities_data:
        city_name = city_entry.get("city_name")
        lat = city_entry.get("latitude")
        lon = city_entry.get("longitude")
        elevation = city_entry.get("elevation")
        current = city_entry.get("current") or {}

        time_str = current.get("time")
        temp = current.get("temperature_2m")
        rh = current.get("relative_humidity_2m")
        ws = current.get("wind_speed_10m")
        wd = current.get("wind_direction_10m")
        precip = current.get("precipitation")
        sp = current.get("surface_pressure")

        rows.append({
            "city_name": city_name,
            "timestamp_local": time_str,
            "temperature_c": temp,
            "relative_humidity_pct": rh,
            "wind_speed_kmh": ws,
            "wind_direction_deg": wd,
            "precipitation_mm": precip,
            "surface_pressure_hpa": sp,
            "latitude": lat,
            "longitude": lon,
            "elevation_m": elevation,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Type conversions
    numeric_cols = [
        "temperature_c",
        "relative_humidity_pct",
        "wind_speed_kmh",
        "wind_direction_deg",
        "precipitation_mm",
        "surface_pressure_hpa",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["timestamp_local"] = pd.to_datetime(df["timestamp_local"], errors="coerce")

    # Quality Flags (Flag, Don't Drop)
    df["flag_humidity_invalid"] = (df["relative_humidity_pct"] < 0) | (df["relative_humidity_pct"] > 100)
    df["flag_temperature_extreme"] = (df["temperature_c"] < -20) | (df["temperature_c"] > 60)
    df["flag_wind_negative"] = df["wind_speed_kmh"] < 0
    df["flag_pressure_invalid"] = (df["surface_pressure_hpa"] < 800) | (df["surface_pressure_hpa"] > 1100)
    df["flag_missing"] = df[["temperature_c", "relative_humidity_pct", "wind_speed_kmh"]].isna().any(axis=1)

    df["is_suspicious"] = (
        df["flag_humidity_invalid"]
        | df["flag_temperature_extreme"]
        | df["flag_wind_negative"]
        | df["flag_pressure_invalid"]
        | df["flag_missing"]
    )

    return df


def clean_forecast_weather(cities_data):
    """
    Extracts and standardizes 24-hour hourly weather forecasts for all cities.
    Returns a pandas DataFrame.
    """
    rows = []
    for city_entry in cities_data:
        city_name = city_entry.get("city_name")
        lat = city_entry.get("latitude")
        lon = city_entry.get("longitude")
        hourly = city_entry.get("hourly") or {}

        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        rhs = hourly.get("relative_humidity_2m", [])
        wss = hourly.get("wind_speed_10m", [])
        precips = hourly.get("precipitation", [])

        num_hours = len(times)
        for i in range(num_hours):
            rows.append({
                "city_name": city_name,
                "forecast_timestamp_local": times[i] if i < len(times) else None,
                "forecast_step_hour": i,
                "temperature_c": temps[i] if i < len(temps) else None,
                "relative_humidity_pct": rhs[i] if i < len(rhs) else None,
                "wind_speed_kmh": wss[i] if i < len(wss) else None,
                "precipitation_mm": precips[i] if i < len(precips) else None,
                "latitude": lat,
                "longitude": lon,
            })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    numeric_cols = ["temperature_c", "relative_humidity_pct", "wind_speed_kmh", "precipitation_mm"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["forecast_timestamp_local"] = pd.to_datetime(df["forecast_timestamp_local"], errors="coerce")

    # Quality Flags
    df["flag_humidity_invalid"] = (df["relative_humidity_pct"] < 0) | (df["relative_humidity_pct"] > 100)
    df["flag_temperature_extreme"] = (df["temperature_c"] < -20) | (df["temperature_c"] > 60)
    df["flag_wind_negative"] = df["wind_speed_kmh"] < 0
    df["flag_missing"] = df[["temperature_c", "relative_humidity_pct", "wind_speed_kmh"]].isna().any(axis=1)

    df["is_suspicious"] = (
        df["flag_humidity_invalid"]
        | df["flag_temperature_extreme"]
        | df["flag_wind_negative"]
        | df["flag_missing"]
    )

    return df


def process_latest_file(raw_filepath=None):
    """
    Finds and cleans the most recent Open-Meteo raw JSON file.
    """
    if not raw_filepath:
        raw_files = sorted(glob.glob(os.path.join(
            PROJECT_ROOT, config.RAW_DATA_DIR, "open_meteo", "*", "open_meteo_*.json"
        )))
        if not raw_files:
            log.error("No raw Open-Meteo JSON files found.")
            return None, None
        raw_filepath = raw_files[-1]

    log.info(f"Loading weather snapshot from {raw_filepath}...")
    with open(raw_filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        log.error("Expected raw Open-Meteo data to be a list of city dicts.")
        return None, None

    df_current = clean_current_weather(data)
    df_forecast = clean_forecast_weather(data)

    log.info(f"Cleaned current weather for {len(df_current)} cities.")
    log.info(f"Cleaned 24h forecast ({len(df_forecast)} rows total) for {len(df_current)} cities.")

    return df_current, df_forecast


def save_processed(df_current, df_forecast):
    """
    Saves cleaned current and forecast DataFrames to CSV in data/processed/open_meteo/YYYY-MM-DD/
    """
    now = datetime.now()
    date_folder = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y%m%d_%H%M")

    out_dir = os.path.join(PROJECT_ROOT, config.PROCESSED_DATA_DIR, "open_meteo", date_folder)
    os.makedirs(out_dir, exist_ok=True)

    current_path = os.path.join(out_dir, f"open_meteo_current_clean_{timestamp}.csv")
    forecast_path = os.path.join(out_dir, f"open_meteo_forecast_clean_{timestamp}.csv")

    df_current.to_csv(current_path, index=False)
    df_forecast.to_csv(forecast_path, index=False)

    log.info(f"Saved cleaned current weather to {current_path}")
    log.info(f"Saved cleaned weather forecast to {forecast_path}")

    return current_path, forecast_path


if __name__ == "__main__":
    df_curr, df_fcst = process_latest_file()
    if df_curr is not None and df_fcst is not None:
        save_processed(df_curr, df_fcst)
    else:
        log.error("No weather data processed.")
