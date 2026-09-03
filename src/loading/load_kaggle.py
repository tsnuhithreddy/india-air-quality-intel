"""
Loads cleaned Kaggle historical CSVs into MySQL.

Handles two related but different files, auto-detected by column presence
(same trick as load_open_meteo.py):
  - kaggle_historical_readings.csv -> fact_kaggle_historical (station/date/pollutant)
  - kaggle_daily_aqi.csv           -> fact_kaggle_daily_aqi   (station/date)

Station discovery: Kaggle stations are new rows, not matched to existing
data.gov.in/OpenAQ stations (cross-source matching remains deferred, per
Phase 1/5). Unlike OpenAQ, Kaggle's stations.csv gives a real city name,
so city_id is looked up against dim_city instead of left NULL.
"""

import sys
import pandas as pd
from mysql.connector import Error
from src.utils.db_connector import get_connection
from src.utils.logger import get_logger

logger = get_logger("load_kaggle")


def str_to_bool(value):
    return str(value).strip().lower() == "true"


def get_or_create_station(cursor, station_lookup, station_key, station_name, city_lookup, city_name):
    if station_key in station_lookup:
        return station_lookup[station_key]

    cursor.execute(
        "SELECT station_id FROM dim_station WHERE source_system = 'kaggle' AND source_station_key = %s",
        (station_key,),
    )
    result = cursor.fetchone()
    if result:
        station_lookup[station_key] = result[0]
        return result[0]

    city_id = city_lookup.get(city_name)  # None if not found -- honest NULL, not a guess

    # stations.csv has no lat/long columns -- stays NULL, same honesty pattern as elsewhere
    cursor.execute(
        """INSERT INTO dim_station
           (source_system, source_station_key, station_name, city_id, latitude, longitude)
           VALUES ('kaggle', %s, %s, %s, NULL, NULL)""",
        (station_key, station_name, city_id),
    )
    station_lookup[station_key] = cursor.lastrowid
    return cursor.lastrowid


def load_pollutant_readings(cursor, df, station_lookup, city_lookup, pollutant_lookup):
    inserted = skipped_duplicate = skipped_unknown_pollutant = 0

    for _, row in df.iterrows():
        station_id = get_or_create_station(
            cursor, station_lookup,
            str(row["station_source_key"]), row["station_name"],
            city_lookup, row["city"],
        )

        pollutant_code = row["pollutant_code"]
        if pollutant_code not in pollutant_lookup:
            logger.warning(f"Unknown pollutant '{pollutant_code}' -- skipping row")
            skipped_unknown_pollutant += 1
            continue
        pollutant_id = pollutant_lookup[pollutant_code]

        try:
            cursor.execute(
                """INSERT INTO fact_kaggle_historical
                   (station_id, pollutant_id, reading_date, pollutant_value,
                    flag_missing, is_suspicious)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    station_id, pollutant_id, row["reading_date"],
                    row["pollutant_value"] if pd.notna(row["pollutant_value"]) else None,
                    str_to_bool(row["flag_missing"]),
                    str_to_bool(row["is_suspicious"]),
                ),
            )
            inserted += 1
        except Error as e:
            if e.errno == 1062:
                skipped_duplicate += 1
            else:
                raise

    return inserted, skipped_duplicate, skipped_unknown_pollutant


def load_daily_aqi(cursor, df, station_lookup, city_lookup):
    inserted = skipped_duplicate = 0

    for _, row in df.iterrows():
        station_id = get_or_create_station(
            cursor, station_lookup,
            str(row["station_source_key"]), row["station_name"],
            city_lookup, row["city"],
        )

        try:
            cursor.execute(
                """INSERT INTO fact_kaggle_daily_aqi
                   (station_id, reading_date, aqi_value, aqi_bucket, flag_missing)
                   VALUES (%s, %s, %s, %s, %s)""",
                (
                    station_id, row["reading_date"],
                    row["aqi_value"] if pd.notna(row["aqi_value"]) else None,
                    row["aqi_bucket"] if pd.notna(row["aqi_bucket"]) else None,
                    str_to_bool(row["flag_missing"]),
                ),
            )
            inserted += 1
        except Error as e:
            if e.errno == 1062:
                skipped_duplicate += 1
            else:
                raise

    return inserted, skipped_duplicate


def load_file(csv_path):
    df = pd.read_csv(csv_path)
    logger.info(f"Read {len(df)} rows from {csv_path}")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT pollutant_id, pollutant_code FROM dim_pollutant")
    pollutant_lookup = {code: pid for pid, code in cursor.fetchall()}

    cursor.execute("SELECT city_id, city_name FROM dim_city")
    city_lookup = {name: cid for cid, name in cursor.fetchall()}

    station_lookup = {}  # keyed by Kaggle's own StationId (e.g. "AP001")

    if "pollutant_code" in df.columns:
        inserted, skipped_duplicate, skipped_unknown = load_pollutant_readings(
            cursor, df, station_lookup, city_lookup, pollutant_lookup
        )
        conn.commit()
        logger.info(
            f"Done (historical readings). inserted={inserted}, "
            f"skipped_duplicate={skipped_duplicate}, skipped_unknown_pollutant={skipped_unknown}"
        )
    elif "aqi_value" in df.columns:
        inserted, skipped_duplicate = load_daily_aqi(cursor, df, station_lookup, city_lookup)
        conn.commit()
        logger.info(f"Done (daily AQI). inserted={inserted}, skipped_duplicate={skipped_duplicate}")
    else:
        cursor.close()
        conn.close()
        raise ValueError(f"Unrecognized Kaggle CSV format: {csv_path}")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.loading.load_kaggle <path_to_csv>")
        sys.exit(1)
    load_file(sys.argv[1])