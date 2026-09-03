"""
Pulls OpenAQ India station metadata + a sample of latest pollutant readings.
Saved as raw JSON, no cleaning/transformation happens here.
"""
import sys
import os
import json
import time
import requests
from datetime import datetime

# Allow imports from src/utils and config, regardless of where this script is run from
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(PROJECT_ROOT, "src", "utils"))
sys.path.append(os.path.join(PROJECT_ROOT, "config"))

from secrets_loader import OPENAQ_API_KEY, redact_secrets
from logger import get_logger
import config

log = get_logger("fetch_openaq")

HEADERS = {
    "X-API-Key": OPENAQ_API_KEY,
}

# How many stations to pull live readings for in this sample.
# Kept small deliberately: 20 stations x ~1 sec delay each = ~20-30 seconds runtime,
# well within OpenAQ's rate limit, and enough to prove the pipeline works.
SAMPLE_STATION_COUNT = 20
SECONDS_BETWEEN_REQUESTS = 1


def fetch_india_locations():
    """Fetch metadata for OpenAQ monitoring stations located in India."""
    url = f"{config.OPENAQ_API_BASE_URL}/locations"
    params = {"iso": "IN", "limit": 300}

    log.info("Requesting India station list from OpenAQ...")

    try:
        response = requests.get(
            url, params=params, headers=HEADERS, timeout=config.REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        log.error(f"OpenAQ API request failed: {redact_secrets(str(e))}")
        return None

    data = response.json()
    found = data.get("meta", {}).get("found", "unknown")
    returned = len(data.get("results", []))
    log.info(f"OpenAQ reports {found} total India stations; returned {returned} in this call.")

    return data


def fetch_latest_for_sample(locations_data, sample_size=SAMPLE_STATION_COUNT):
    """
    For a sample of stations from locations_data, fetch their latest pollutant
    readings, one station at a time, with a pause between each call.
    """
    stations = locations_data.get("results", [])[:sample_size]
    log.info(f"Fetching latest readings for {len(stations)} sample stations...")

    all_readings = []

    for station in stations:
        station_id = station.get("id")
        station_name = station.get("name", "unknown")
        url = f"{config.OPENAQ_API_BASE_URL}/locations/{station_id}/latest"

        try:
            response = requests.get(url, headers=HEADERS, timeout=config.REQUEST_TIMEOUT_SECONDS)

            if response.status_code == 429:
                log.warning(f"Rate limited on station {station_id} ({station_name}) — skipping.")
                time.sleep(SECONDS_BETWEEN_REQUESTS)
                continue

            response.raise_for_status()
            readings = response.json().get("results", [])
            all_readings.append({
                "station_id": station_id,
                "station_name": station_name,
                "readings": readings,
            })
            log.info(f"  Got {len(readings)} reading(s) for station {station_id} ({station_name})")

        except requests.exceptions.RequestException as e:
            log.warning(
                f"Failed to fetch latest for station {station_id} "
                f"({station_name}): {redact_secrets(str(e))}"
            )

        time.sleep(SECONDS_BETWEEN_REQUESTS)

    return all_readings


def save_raw_json(data, filename_prefix):
    now = datetime.now()
    date_folder = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y%m%d_%H%M")

    out_dir = os.path.join(PROJECT_ROOT, config.RAW_DATA_DIR, "openaq", date_folder)
    os.makedirs(out_dir, exist_ok=True)

    out_path = os.path.join(out_dir, f"{filename_prefix}_{timestamp}.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    log.info(f"Saved {filename_prefix} to {out_path}")
    return out_path


if __name__ == "__main__":
    locations = fetch_india_locations()

    if locations is None:
        log.error("No location data — aborting before fetching readings.")
    else:
        save_raw_json(locations, "openaq_locations")

        latest_readings = fetch_latest_for_sample(locations)
        save_raw_json({"readings": latest_readings}, "openaq_latest")