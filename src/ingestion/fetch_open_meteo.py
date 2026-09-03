"""
Pulls current + next-24h forecast weather data from Open-Meteo for all
target cities in a SINGLE API call. No API key required. This is
supporting/context data (Phase 1), not a primary AQI source.
"""
import sys
import os
import json
import requests
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(PROJECT_ROOT, "src", "utils"))
sys.path.append(os.path.join(PROJECT_ROOT, "config"))

from logger import get_logger
import config

log = get_logger("fetch_open_meteo")


def fetch_weather_snapshot():
    """
    Fetch current conditions + next-24h hourly forecast for every city in
    config.CITY_COORDINATES, in a single Open-Meteo API call.
    """
    cities = list(config.CITY_COORDINATES.keys())
    latitudes = ",".join(str(config.CITY_COORDINATES[city][0]) for city in cities)
    longitudes = ",".join(str(config.CITY_COORDINATES[city][1]) for city in cities)

    params = {
        "latitude": latitudes,
        "longitude": longitudes,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,precipitation,surface_pressure",
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation",
        "forecast_days": 1,
        "timezone": "auto",
    }

    log.info(f"Requesting weather for {len(cities)} cities from Open-Meteo...")

    try:
        response = requests.get(
            config.OPEN_METEO_BASE_URL,
            params=params,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        log.error(f"Open-Meteo API request failed: {e}")
        return None

    data = response.json()

    # When multiple coordinates are sent, Open-Meteo returns a plain LIST,
    # one entry per city, in the SAME ORDER the coordinates were sent in.
    # We tag each entry with its city name so the raw file is self-describing.
    if isinstance(data, list):
        for city, entry in zip(cities, data):
            entry["city_name"] = city
        log.info(f"Received weather for {len(data)} cities.")
    else:
        log.warning("Unexpected response shape (expected a list) — check raw file.")

    return data


def save_raw_snapshot(data):
    now = datetime.now()
    date_folder = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y%m%d_%H%M")

    out_dir = os.path.join(PROJECT_ROOT, config.RAW_DATA_DIR, "open_meteo", date_folder)
    os.makedirs(out_dir, exist_ok=True)

    out_path = os.path.join(out_dir, f"open_meteo_{timestamp}.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    log.info(f"Saved raw weather snapshot to {out_path}")
    return out_path


if __name__ == "__main__":
    snapshot = fetch_weather_snapshot()
    if snapshot is not None:
        save_raw_snapshot(snapshot)
    else:
        log.error("No data saved due to failed Open-Meteo API request.")
        