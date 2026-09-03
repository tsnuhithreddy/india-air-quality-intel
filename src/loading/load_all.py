"""
Runs all three source loaders against a given date's processed files, in
one command. This does NOT automate scheduling (that's a later phase) —
it just chains today's three manual loader commands into one, reducing
the chance of forgetting a source or mistyping a path.

Usage:
    python -m src.loading.load_all 2026-08-28
"""

import sys
import glob
from src.loading.load_data_gov_in import load_file as load_data_gov_in
from src.loading.load_openaq import load_file as load_openaq
from src.loading.load_open_meteo import load_file as load_open_meteo
from src.utils.logger import get_logger

logger = get_logger("load_all")


def run(date_str):
    sources = [
        ("data_gov_in", load_data_gov_in),
        ("openaq", load_openaq),
        ("open_meteo", load_open_meteo),
    ]

    for source_name, loader_fn in sources:
        pattern = f"data/processed/{source_name}/{date_str}/*.csv"
        files = sorted(glob.glob(pattern))

        if not files:
            logger.warning(f"No processed files found for {source_name} on {date_str} — skipping")
            continue

        for f in files:
            logger.info(f"--- Loading {source_name}: {f} ---")
            loader_fn(f)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m src.loading.load_all <YYYY-MM-DD>")
        sys.exit(1)
    run(sys.argv[1])