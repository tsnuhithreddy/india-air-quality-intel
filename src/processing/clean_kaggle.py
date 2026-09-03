import pandas as pd
from pathlib import Path

RAW_DIR = Path("data/external/kaggle_air_quality_india")
OUT_DIR = Path("data/processed/kaggle")
OUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_CITIES = ["Delhi", "Mumbai", "Bengaluru", "Hyderabad", "Chennai",
                  "Kolkata", "Pune", "Ahmedabad", "Lucknow", "Jaipur", "Patna"]

# Maps Kaggle's raw column names to this project's standardized pollutant codes
# (matches the pollutant_code values already sitting in dim_pollutant)
POLLUTANT_COLUMN_MAP = {
    "PM2.5": "PM2.5",
    "PM10": "PM10",
    "NO": "NO",
    "NO2": "NO2",
    "NOx": "NOX",      # Kaggle spells it "NOx", your dim_pollutant has "NOX"
    "NH3": "NH3",
    "CO": "CO",
    "SO2": "SO2",
    "O3": "O3",
    "Benzene": "Benzene",
    "Toluene": "Toluene",
    "Xylene": "Xylene",
}

SENTINEL_VALUES = {999, 9999, -999}


def load_and_filter():
    """Load raw files and keep only rows belonging to our 11 target cities."""
    stations = pd.read_csv(RAW_DIR / "stations.csv")
    readings = pd.read_csv(RAW_DIR / "station_day.csv")

    target_stations = stations[stations["City"].isin(TARGET_CITIES)].copy()
    filtered = readings[readings["StationId"].isin(target_stations["StationId"])].copy()

    # Attach station name + city onto every reading row
    filtered = filtered.merge(
        target_stations[["StationId", "StationName", "City"]],
        on="StationId", how="left"
    )
    return filtered


def build_pollutant_table(filtered):
    """Reshape wide pollutant columns into one row per station/date/pollutant."""
    pollutant_cols = list(POLLUTANT_COLUMN_MAP.keys())
    id_cols = ["StationId", "StationName", "City", "Date"]

    long_df = filtered.melt(
        id_vars=id_cols,
        value_vars=pollutant_cols,
        var_name="raw_pollutant_column",
        value_name="pollutant_value"
    )

    long_df["pollutant_code"] = long_df["raw_pollutant_column"].map(POLLUTANT_COLUMN_MAP)

    long_df["flag_missing"] = long_df["pollutant_value"].isna()
    long_df["flag_negative"] = long_df["pollutant_value"] < 0
    long_df["flag_sentinel"] = long_df["pollutant_value"].isin(SENTINEL_VALUES)
    long_df["is_suspicious"] = long_df["flag_negative"] | long_df["flag_sentinel"]

    long_df = long_df.rename(columns={
        "StationId": "station_source_key",
        "StationName": "station_name",
        "City": "city",
        "Date": "reading_date",
    })

    return long_df[[
        "station_source_key", "station_name", "city", "reading_date",
        "pollutant_code", "pollutant_value",
        "flag_missing", "flag_negative", "flag_sentinel", "is_suspicious"
    ]]


def build_daily_aqi_table(filtered):
    """One row per station/date with the precomputed overall AQI."""
    df = filtered[["StationId", "StationName", "City", "Date", "AQI", "AQI_Bucket"]].copy()
    df["flag_missing"] = df["AQI"].isna()

    df = df.rename(columns={
        "StationId": "station_source_key",
        "StationName": "station_name",
        "City": "city",
        "Date": "reading_date",
        "AQI": "aqi_value",
        "AQI_Bucket": "aqi_bucket",
    })
    return df


def main():
    filtered = load_and_filter()
    print(f"Filtered to {filtered['StationId'].nunique()} stations, {len(filtered)} station-day rows")

    pollutant_table = build_pollutant_table(filtered)
    pollutant_table.to_csv(OUT_DIR / "kaggle_historical_readings.csv", index=False)
    print(f"\nWrote {len(pollutant_table)} rows to kaggle_historical_readings.csv")
    print(f"  flagged missing:    {pollutant_table['flag_missing'].mean() * 100:.1f}%")
    print(f"  flagged suspicious: {pollutant_table['is_suspicious'].mean() * 100:.1f}%")

    aqi_table = build_daily_aqi_table(filtered)
    aqi_table.to_csv(OUT_DIR / "kaggle_daily_aqi.csv", index=False)
    print(f"\nWrote {len(aqi_table)} rows to kaggle_daily_aqi.csv")
    print(f"  flagged missing: {aqi_table['flag_missing'].mean() * 100:.1f}%")

if __name__ == "__main__":
    main()