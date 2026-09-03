"""
One-time verification of the manually-downloaded Kaggle historical CPCB
dataset (2015-2020). Does not download anything — just confirms the files
are present, readable, and shaped as expected before we build cleaning
logic around them in a later step.
"""
import sys
import os
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.join(PROJECT_ROOT, "src", "utils"))
sys.path.append(os.path.join(PROJECT_ROOT, "config"))

from logger import get_logger
import config

log = get_logger("verify_kaggle_data")

KAGGLE_DIR = os.path.join(PROJECT_ROOT, config.EXTERNAL_DATA_DIR, "kaggle_air_quality_india")

EXPECTED_FILES = [
    "city_day.csv",
    "city_hour.csv",
    "station_day.csv",
    "station_hour.csv",
    "stations.csv",
]


def verify():
    log.info(f"Checking for Kaggle files in {KAGGLE_DIR}...")

    missing = [f for f in EXPECTED_FILES if not os.path.exists(os.path.join(KAGGLE_DIR, f))]
    if missing:
        log.error(f"Missing expected file(s): {missing}")
        return
    log.info("All 5 expected files found.")

    df = pd.read_csv(os.path.join(KAGGLE_DIR, "city_day.csv"))
    log.info(f"city_day.csv: {df.shape[0]} rows, {df.shape[1]} columns")
    log.info(f"Columns: {list(df.columns)}")
    log.info(f"Cities in dataset: {sorted(df['City'].unique())}")
    log.info(f"Date range: {df['Date'].min()} to {df['Date'].max()}")


if __name__ == "__main__":
    verify()