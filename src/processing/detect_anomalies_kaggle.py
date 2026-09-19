"""
Phase 9 — Anomaly Detection on Kaggle historical daily AQI data.

Reproduces the notebook logic from phase9_anomaly_detection.ipynb as a
reusable script: builds a per-city, per-calendar-month median/MAD
baseline, computes a modified z-score per reading, and flags anomalies
where |modified_z| > 3.5.

Excludes:
  - Rows where flag_missing = 1 (no real value to score)
  - Ahmedabad's GJ001 station entirely (known invalid AQI values, Phase 7/8)

Output: writes results to data/processed/kaggle_anomalies/<date>/kaggle_anomaly_flags.csv
"""

import os
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

from src.utils.logger import get_logger

logger = get_logger("detect_anomalies_kaggle")

Z_THRESHOLD = 3.5
EXCLUDED_STATION_KEY = "GJ001"
CHENNAI_NOTE = "mixed-use city, industrial station present"


def get_engine():
    load_dotenv(r"C:\Dev\india-air-quality-intel\.env", override=True)
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD")
    host = os.getenv("MYSQL_HOST")
    port = os.getenv("MYSQL_PORT")
    database = os.getenv("MYSQL_DATABASE")
    return create_engine(
        f"mysql+mysqlconnector://{user}:{password}@{host}:{port}/{database}"
    )


def mad(series):
    med = series.median()
    return (series - med).abs().median()


def main():
    engine = get_engine()

    query = """
    SELECT f.daily_aqi_id, f.station_id, s.station_name, s.source_station_key,
           c.city_name, f.reading_date, f.aqi_value, f.aqi_bucket, f.flag_missing
    FROM fact_kaggle_daily_aqi f
    JOIN dim_station s ON f.station_id = s.station_id
    JOIN dim_city c ON s.city_id = c.city_id
    WHERE s.source_system = 'kaggle'
    """
    df_raw = pd.read_sql(query, engine)
    logger.info(f"Pulled {len(df_raw)} raw rows (expected 95058)")

    df_valid = df_raw[df_raw["flag_missing"] == 0].copy()
    logger.info(f"After flag_missing filter: {len(df_valid)}")

    df_model = df_valid[df_valid["source_station_key"] != EXCLUDED_STATION_KEY].copy()
    logger.info(f"After excluding {EXCLUDED_STATION_KEY} (Ahmedabad): {len(df_model)}")

    df_model["month"] = pd.to_datetime(df_model["reading_date"]).dt.month

    baseline = df_model.groupby(["city_name", "month"])["aqi_value"].agg(
        median_aqi="median", n_readings="count"
    ).reset_index()
    mad_vals = df_model.groupby(["city_name", "month"])["aqi_value"].apply(mad).reset_index(name="mad_aqi")
    baseline = baseline.merge(mad_vals, on=["city_name", "month"])

    zero_mad = baseline[baseline["mad_aqi"] == 0]
    if len(zero_mad) > 0:
        logger.warning(f"Found {len(zero_mad)} zero-MAD groups — these will produce inf/NaN z-scores!")

    df_scored = df_model.merge(baseline, on=["city_name", "month"], how="left")
    df_scored["modified_z"] = 0.6745 * (df_scored["aqi_value"] - df_scored["median_aqi"]) / df_scored["mad_aqi"]
    df_scored["is_anomaly"] = df_scored["modified_z"].abs() > Z_THRESHOLD

    nan_count = df_scored["modified_z"].isna().sum()
    logger.info(f"NaN modified_z count: {nan_count} (expected 0)")

    df_scored["baseline_note"] = None
    df_scored.loc[df_scored["city_name"] == "Chennai", "baseline_note"] = CHENNAI_NOTE

    total_flagged = df_scored["is_anomaly"].sum()
    logger.info(f"Total scored: {len(df_scored)}, flagged anomalies: {total_flagged} "
                f"({100 * df_scored['is_anomaly'].mean():.2f}%)")

    output_cols = [
        "daily_aqi_id", "station_id", "city_name", "month",
        "median_aqi", "mad_aqi", "modified_z", "is_anomaly", "baseline_note"
    ]
    df_out = df_scored[output_cols]

    date_str = datetime.now().strftime("%Y-%m-%d")
    out_dir = os.path.join("data", "processed", "kaggle_anomalies", date_str)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "kaggle_anomaly_flags.csv")
    df_out.to_csv(out_path, index=False)
    logger.info(f"Wrote {len(df_out)} rows to {out_path}")


if __name__ == "__main__":
    main()