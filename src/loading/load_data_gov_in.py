"""
Loads cleaned data.gov.in CSVs (AQI sub-index readings) into MySQL.

For each row:
1. Looks up the city (must already exist in dim_city — seeded earlier).
2. Finds or creates the station in dim_station.
3. Looks up the pollutant in dim_pollutant.
4. Inserts into fact_cpcb_subindex, skipping (not crashing on) rows that
   already exist, so the script is safe to re-run.

Usage:
    python src/loading/load_data_gov_in.py data/processed/data_gov_in/2026-08-26/data_gov_in_clean_20260826_1750.csv
"""

import sys
import pandas as pd
from mysql.connector import Error
from src.utils.db_connector import get_connection
from src.utils.logger import get_logger

logger = get_logger("load_data_gov_in")


def str_to_bool(value):
    """CSV stores flags as the text 'True'/'False'. The Python string
    'False' is truthy, so we must compare explicitly instead of using
    bool(value) directly, or every flag would silently become True."""
    return str(value).strip().lower() == "true"


def load_file(csv_path):
    df = pd.read_csv(csv_path)
    logger.info(f"Read {len(df)} rows from {csv_path}")

    conn = get_connection()
    cursor = conn.cursor()

    # Load small reference tables into memory once, instead of
    # querying the database on every single row.
    cursor.execute("SELECT city_id, city_name FROM dim_city")
    city_lookup = {name: cid for cid, name in cursor.fetchall()}

    cursor.execute("SELECT pollutant_id, pollutant_code FROM dim_pollutant")
    pollutant_lookup = {code: pid for pid, code in cursor.fetchall()}

    station_lookup = {}  # filled in as we discover stations

    inserted = 0
    skipped_duplicate = 0
    skipped_unknown_city = 0
    skipped_unknown_pollutant = 0

    for _, row in df.iterrows():
        city_name = row["city"]
        if city_name not in city_lookup:
            logger.warning(f"Unknown city '{city_name}' — skipping row")
            skipped_unknown_city += 1
            continue
        city_id = city_lookup[city_name]

        pollutant_code = row["pollutant_id"]  # column is named pollutant_id but holds a code like 'CO'
        if pollutant_code not in pollutant_lookup:
            logger.warning(f"Unknown pollutant '{pollutant_code}' — skipping row")
            skipped_unknown_pollutant += 1
            continue
        pollutant_id = pollutant_lookup[pollutant_code]

        station_key = row["station"]  # data.gov.in has no separate numeric station ID
        if station_key not in station_lookup:
            cursor.execute(
                "SELECT station_id FROM dim_station WHERE source_system = 'data_gov_in' AND source_station_key = %s",
                (station_key,),
            )
            result = cursor.fetchone()
            if result:
                station_lookup[station_key] = result[0]
            else:
                cursor.execute(
                    """INSERT INTO dim_station
                       (source_system, source_station_key, station_name, city_id, latitude, longitude)
                       VALUES ('data_gov_in', %s, %s, %s, %s, %s)""",
                    (station_key, station_key, city_id, row["latitude"], row["longitude"]),
                )
                station_lookup[station_key] = cursor.lastrowid
        station_id = station_lookup[station_key]

        try:
            cursor.execute(
                """INSERT INTO fact_cpcb_subindex
                   (station_id, pollutant_id, timestamp_local,
                    sub_index_min, sub_index_max, sub_index_avg,
                    flag_negative, flag_sentinel, flag_missing, is_suspicious)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    station_id,
                    pollutant_id,
                    row["last_update"],
                    row["sub_index_min"] if pd.notna(row["sub_index_min"]) else None,
                    row["sub_index_max"] if pd.notna(row["sub_index_max"]) else None,
                    row["sub_index_avg"] if pd.notna(row["sub_index_avg"]) else None,
                    str_to_bool(row["flag_negative"]),
                    str_to_bool(row["flag_sentinel"]),
                    str_to_bool(row["flag_missing"]),
                    str_to_bool(row["is_suspicious"]),
                ),
            )
            inserted += 1
        except Error as e:
            if e.errno == 1062:  # MySQL's "duplicate entry" error code
                skipped_duplicate += 1
            else:
                raise

    conn.commit()
    cursor.close()
    conn.close()

    logger.info(
        f"Done. inserted={inserted}, skipped_duplicate={skipped_duplicate}, "
        f"skipped_unknown_city={skipped_unknown_city}, skipped_unknown_pollutant={skipped_unknown_pollutant}"
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python src/loading/load_data_gov_in.py <path_to_csv>")
        sys.exit(1)
    load_file(sys.argv[1])