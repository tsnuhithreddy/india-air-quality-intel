"""
Phase 9 — Loads scored anomaly flags (from detect_anomalies_kaggle.py's
output CSV) into fact_kaggle_anomaly_flags.

Reuses the same connection helper and duplicate-handling pattern as
load_kaggle.py: tries each insert, catches MySQL error 1062 (duplicate
key on daily_aqi_id) and counts it as skipped rather than crashing.
"""

import sys
import pandas as pd
import mysql.connector

from src.utils.db_connector import get_connection
from src.utils.logger import get_logger

logger = get_logger("load_kaggle_anomalies")

INSERT_SQL = """
INSERT INTO fact_kaggle_anomaly_flags
    (daily_aqi_id, station_id, city_name, month,
     median_aqi, mad_aqi, modified_z, is_anomaly, baseline_note)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def load_file(csv_path):
    df = pd.read_csv(csv_path)
    logger.info(f"Read {len(df)} rows from {csv_path}")

    conn = get_connection()
    cursor = conn.cursor()

    inserted = 0
    skipped_duplicate = 0
    errors = 0

    for _, row in df.iterrows():
        baseline_note = None if pd.isna(row["baseline_note"]) else row["baseline_note"]
        try:
            cursor.execute(INSERT_SQL, (
                int(row["daily_aqi_id"]),
                int(row["station_id"]),
                row["city_name"],
                int(row["month"]),
                float(row["median_aqi"]),
                float(row["mad_aqi"]),
                float(row["modified_z"]),
                bool(row["is_anomaly"]),
                baseline_note,
            ))
            inserted += 1
        except mysql.connector.Error as e:
            if e.errno == 1062:
                skipped_duplicate += 1
            else:
                errors += 1
                logger.warning(f"Row error (daily_aqi_id={row['daily_aqi_id']}): {e}")

    conn.commit()
    cursor.close()
    conn.close()

    logger.info(f"Inserted: {inserted}, skipped_duplicate: {skipped_duplicate}, errors: {errors}")
    logger.info(f"Total processed: {inserted + skipped_duplicate + errors} (expected {len(df)})")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.loading.load_kaggle_anomalies <path_to_csv>")
        sys.exit(1)
    load_file(sys.argv[1])