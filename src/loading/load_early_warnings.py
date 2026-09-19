import pandas as pd
from src.utils.db_connector import get_connection
from src.utils.logger import get_logger

logger = get_logger("load_early_warnings")

def str_to_bool(val):
    if isinstance(val, bool):
        return val
    if pd.isna(val):
        return None
    return str(val).strip().lower() == 'true'

def load_early_warnings(csv_path):
    df = pd.read_csv(csv_path)
    conn = get_connection()
    cursor = conn.cursor()

    inserted, skipped_duplicate, errors = 0, 0, 0

    # Pre-load city_id lookups once, same pattern as load_kaggle.py
    cursor.execute("SELECT city_id, city_name FROM dim_city")
    city_lookup = {name: cid for cid, name in cursor.fetchall()}

    for _, row in df.iterrows():
        city_id = city_lookup.get(row['city_name'])
        if city_id is None:
            logger.warning(f"Unknown city '{row['city_name']}', skipping row.")
            errors += 1
            continue

        actual_aqi = None if pd.isna(row['actual_aqi']) else float(row['actual_aqi'])
        predicted_aqi = None if pd.isna(row['predicted_aqi']) else float(row['predicted_aqi'])
        actual_category = None if pd.isna(row['actual_category']) else row['actual_category']
        predicted_category = None if pd.isna(row['predicted_category']) else row['predicted_category']
        warning_label = None if pd.isna(row['warning_label']) else row['warning_label']

        try:
            cursor.execute("""
                INSERT INTO fact_early_warnings
                (city_id, reading_date, target_date, horizon, model_used,
                 actual_aqi, predicted_aqi, actual_category, predicted_category,
                 triggered, reliability_tier, warning_label, is_new_episode)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                city_id, row['reading_date'], row['target_date'], int(row['horizon']), row['model_used'],
                actual_aqi, predicted_aqi, actual_category, predicted_category,
                str_to_bool(row['triggered']), row['reliability_tier'], warning_label,
                str_to_bool(row['is_new_episode'])
            ))
            inserted += 1
        except Exception as e:
            if "1062" in str(e):  # duplicate key
                skipped_duplicate += 1
            else:
                logger.error(f"Row failed: {e}")
                errors += 1

    conn.commit()
    cursor.close()
    conn.close()

    logger.info(f"Inserted: {inserted} | Duplicates skipped: {skipped_duplicate} | Errors: {errors}")
    print(f"Inserted: {inserted} | Duplicates skipped: {skipped_duplicate} | Errors: {errors}")

if __name__ == "__main__":
    load_early_warnings("data/processed/phase11_early_warnings/fact_early_warnings.csv")