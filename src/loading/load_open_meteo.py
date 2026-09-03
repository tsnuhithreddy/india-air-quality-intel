"""
Loads cleaned Open-Meteo CSVs (weather observations + forecasts) into MySQL.

Open-Meteo is simpler than the other two sources: no idle-station problem
(it's a coordinate-based weather API, not a physical sensor network), and
city_name in the CSV matches dim_city directly, so there's no station
discovery step. This script handles both the "current" and "forecast"
file types, auto-detected from the filename.
"""

import sys
import pandas as pd
from mysql.connector import Error
from src.utils.db_connector import get_connection
from src.utils.logger import get_logger

logger = get_logger("load_open_meteo")


def str_to_bool(value):
    return str(value).strip().lower() == "true"


def load_current(df, cursor, city_lookup):
    inserted, skipped_duplicate, skipped_unknown_city = 0, 0, 0

    for _, row in df.iterrows():
        city_name = row["city_name"]
        if city_name not in city_lookup:
            logger.warning(f"Unknown city '{city_name}' — skipping row")
            skipped_unknown_city += 1
            continue
        city_id = city_lookup[city_name]

        try:
            cursor.execute(
                """INSERT INTO fact_weather_observations
                   (city_id, timestamp_local, temperature_c, relative_humidity_pct,
                    wind_speed_kmh, wind_direction_deg, precipitation_mm,
                    surface_pressure_hpa, elevation_m,
                    flag_humidity_invalid, flag_temperature_extreme,
                    flag_wind_negative, flag_pressure_invalid, flag_missing, is_suspicious)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    city_id,
                    row["timestamp_local"],
                    row["temperature_c"] if pd.notna(row["temperature_c"]) else None,
                    row["relative_humidity_pct"] if pd.notna(row["relative_humidity_pct"]) else None,
                    row["wind_speed_kmh"] if pd.notna(row["wind_speed_kmh"]) else None,
                    row["wind_direction_deg"] if pd.notna(row["wind_direction_deg"]) else None,
                    row["precipitation_mm"] if pd.notna(row["precipitation_mm"]) else None,
                    row["surface_pressure_hpa"] if pd.notna(row["surface_pressure_hpa"]) else None,
                    row["elevation_m"] if pd.notna(row["elevation_m"]) else None,
                    str_to_bool(row["flag_humidity_invalid"]),
                    str_to_bool(row["flag_temperature_extreme"]),
                    str_to_bool(row["flag_wind_negative"]),
                    str_to_bool(row["flag_pressure_invalid"]),
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

    return inserted, skipped_duplicate, skipped_unknown_city


def load_forecast(df, cursor, city_lookup):
    inserted, skipped_duplicate, skipped_unknown_city = 0, 0, 0

    for _, row in df.iterrows():
        city_name = row["city_name"]
        if city_name not in city_lookup:
            logger.warning(f"Unknown city '{city_name}' — skipping row")
            skipped_unknown_city += 1
            continue
        city_id = city_lookup[city_name]

        try:
            cursor.execute(
                """INSERT INTO fact_weather_forecast
                   (city_id, forecast_timestamp_local, forecast_step_hour,
                    temperature_c, relative_humidity_pct, wind_speed_kmh, precipitation_mm,
                    flag_humidity_invalid, flag_temperature_extreme,
                    flag_wind_negative, flag_missing, is_suspicious)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                    temperature_c = VALUES(temperature_c),
                    relative_humidity_pct = VALUES(relative_humidity_pct),
                    wind_speed_kmh = VALUES(wind_speed_kmh),
                    precipitation_mm = VALUES(precipitation_mm),
                    flag_humidity_invalid = VALUES(flag_humidity_invalid),
                    flag_temperature_extreme = VALUES(flag_temperature_extreme),
                    flag_wind_negative = VALUES(flag_wind_negative),
                    flag_missing = VALUES(flag_missing),
                    is_suspicious = VALUES(is_suspicious)""",
                (
                    city_id,
                    row["forecast_timestamp_local"],
                    row["forecast_step_hour"],
                    row["temperature_c"] if pd.notna(row["temperature_c"]) else None,
                    row["relative_humidity_pct"] if pd.notna(row["relative_humidity_pct"]) else None,
                    row["wind_speed_kmh"] if pd.notna(row["wind_speed_kmh"]) else None,
                    row["precipitation_mm"] if pd.notna(row["precipitation_mm"]) else None,
                    str_to_bool(row["flag_humidity_invalid"]),
                    str_to_bool(row["flag_temperature_extreme"]),
                    str_to_bool(row["flag_wind_negative"]),
                    str_to_bool(row["flag_missing"]),
                    str_to_bool(row["is_suspicious"]),
                ),
            )
            # ON DUPLICATE KEY UPDATE means this always "succeeds" — MySQL doesn't
            # distinguish a fresh insert from an update via rowcount in a simple way,
            # so we just count every processed row as "inserted" here.
            inserted += 1
        except Error as e:
            raise

    return inserted, skipped_duplicate, skipped_unknown_city


def load_file(csv_path):
    df = pd.read_csv(csv_path)
    logger.info(f"Read {len(df)} rows from {csv_path}")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT city_id, city_name FROM dim_city")
    city_lookup = {name: cid for cid, name in cursor.fetchall()}

    if "forecast_step_hour" in df.columns:
        logger.info("Detected forecast file")
        inserted, skipped_duplicate, skipped_unknown_city = load_forecast(df, cursor, city_lookup)
    else:
        logger.info("Detected current-weather file")
        inserted, skipped_duplicate, skipped_unknown_city = load_current(df, cursor, city_lookup)

    conn.commit()
    cursor.close()
    conn.close()

    logger.info(
        f"Done. inserted={inserted}, skipped_duplicate={skipped_duplicate}, "
        f"skipped_unknown_city={skipped_unknown_city}"
    )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.loading.load_open_meteo <path_to_csv>")
        sys.exit(1)
    load_file(sys.argv[1])