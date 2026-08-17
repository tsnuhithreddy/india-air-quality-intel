"""
Pulls one live snapshot from the data.gov.in CPCB Real-Time AQI API
and saves it as raw JSON. No cleaning/transformation happens here.
"""
import sys
import os
import json
import requests
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}

# Allow imports from src/utils and config, regardless of where this script is run from
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(PROJECT_ROOT, "src", "utils"))
sys.path.append(os.path.join(PROJECT_ROOT, "config"))

from secrets_loader import DATA_GOV_IN_API_KEY
from logger import get_logger
import config

log = get_logger("fetch_data_gov_in")


def fetch_snapshot():
    params = {
        "api-key": DATA_GOV_IN_API_KEY,
        "format": "json",
        "limit": 2000,
    }

    log.info("Requesting live snapshot from data.gov.in...")

    try:
        response = requests.get(
            config.PRIMARY_API_BASE_URL,
            params=params,
            headers=HEADERS,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        log.error(f"API request failed: {e}")
        return None

    data = response.json()
    record_count = len(data.get("records", []))
    log.info(f"Received {record_count} station records.")

    return data


def save_raw_snapshot(data):
    now = datetime.now()
    date_folder = now.strftime("%Y-%m-%d")
    timestamp = now.strftime("%Y%m%d_%H%M")

    out_dir = os.path.join(PROJECT_ROOT, config.RAW_DATA_DIR, "data_gov_in", date_folder)
    os.makedirs(out_dir, exist_ok=True)

    out_path = os.path.join(out_dir, f"data_gov_in_{timestamp}.json")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    log.info(f"Saved raw snapshot to {out_path}")
    return out_path


if __name__ == "__main__":
    snapshot = fetch_snapshot()
    if snapshot is not None:
        save_raw_snapshot(snapshot)
    else:
        log.error("No data saved due to failed API request.")