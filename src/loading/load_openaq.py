"""
Loads cleaned OpenAQ CSVs (real µg/m³ concentration readings) into MySQL.

Key difference from the data.gov.in loader: OpenAQ rows for idle/non-reporting
stations have no sensor_id, pollutant_id, concentration, or timestamps at all.
These rows still register the station (so we know it exists), but produce no
fact-table row, since a fact row represents a measurement at a point in time,
and there is no measurement to record.
"""

import sys
import pandas as pd
from mysql.connector import Error
from src.utils.db_connector import get_connection
from src.utils.logger import get_logger

logger = get_logger("load_openaq")


def str_to_bool(value):
    return str(value).strip().lower() == "true"


def load_file(csv_path):
    df = pd.read_csv(csv_path)
    logger.info(f"Read {len(df)} rows from {csv_path}")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT pollutant_id, pollutant_code FROM dim_pollutant")
    pollutant_lookup = {code: pid for pid, code in cursor.fetchall()}

    station_lookup = {}  # keyed by OpenAQ's own numeric station_id

    inserted = 0
    skipped_duplicate = 0
    skipped_idle_station = 0
    skipped_unknown_pollutant = 0

    for _, row in df.iterrows():
        station_key = str(row["station_id"])  # OpenAQ's own numeric ID, as text for consistency

        if station_key not in station_lookup:
            cursor.execute(
                "SELECT station_id FROM dim_station WHERE source_system = 'openaq' AND source_station_key = %s",
                (station_key,),
            )
            result = cursor.fetchone()
            if result:
                station_lookup[station_key] = result[0]
            else:
                # OpenAQ rows are not tied to one of our 11 dim_city rows directly —
                # city matching for OpenAQ is out of scope for this phase (per Phase 1's
                # note that cross-source station matching is deferred), so city_id is left NULL.
                cursor.execute(
                    """INSERT INTO dim_station
                       (source_system, source_station_key, station_name, city_id, latitude, longitude)
                       VALUES ('openaq', %s, %s, NULL, %s, %s)""",
                    (station_key, row["station_name"], row["latitude"], row["longitude"]),
                )
                station_lookup[station_key] = cursor.lastrowid
        station_id = station_lookup[station_key]

        # Idle station: no timestamp means no real measurement to insert.
        if pd.isna(row["timestamp_local"]) or pd.isna(row["pollutant_id"]):
            skipped_idle_station += 1
            continue

        pollutant_code = row["pollutant_id"]
        if pollutant_code not in pollutant_lookup:
            logger.warning(f"Unknown pollutant '{pollutant_code}' — skipping row")
            skipped_unknown_pollutant += 1
            continue
        pollutant_id = pollutant_lookup[pollutant_code]

        sensor_id = int(row["sensor_id"]) if pd.notna(row["sensor_id"]) else None

        try:
            cursor.execute(
                """INSERT INTO fact_openaq_concentration
                   (station_id, sensor_id, pollutant_id, timestamp_local, timestamp_utc,
                    concentration_value, unit,
                    flag_negative, flag_sentinel, flag_missing, flag_zero, is_suspicious)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    station_id,
                    sensor_id,
                    pollutant_id,
                    row["timestamp_local"],
                    row["timestamp_utc"],
                    row["concentration_value"] if pd.notna(row["concentration_value"]) else None,
                    row["unit"],
                    str_to_bool(row["flag_negative"]),
                    str_to_bool(row["flag_sentinel"]),
                    str_to_bool(row["flag_missing"]),
                    str_to_bool(row["flag_zero"]),
                    str_to_bool(row["is_suspicious"]),
                ),
            )
            inserted += 1
        except Error as e:
            if e.errno == 1062:
                skipped_duplicate += 1
            else:
                raise

    conn.commit()
    cursor.close()
    conn.close()

    logger.info(
        f"Done. inserted={inserted}, skipped_duplicate={skipped_duplicate}, "
        f"skipped_idle_station={skipped_idle_station}, skipped_unknown_pollutant={skipped_unknown_pollutant}"
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.loading.load_openaq <path_to_csv>")
        sys.exit(1)
    load_file(sys.argv[1])