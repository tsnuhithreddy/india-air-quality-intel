"""
Post-ingestion stage for all three live sources, in one process:

    newest raw JSON  ->  clean  ->  processed CSV  ->  load into MySQL

Replaces the manual "run three cleaners, then load_all" routine that caused
the Phase 12 staleness incident (ingestion kept running; nothing carried its
output into MySQL).

Design:
- Reuses the existing, already-verified cleaner and loader functions
  unchanged. No cleaning or loading logic lives in this file.
- Loads exactly the file(s) each cleaner just wrote (the path it returns),
  so there is no date argument and no midnight edge case.
- Each source is isolated: one source failing does not stop the others.
- Fails loudly: any failure logs an ERROR and the process exits non-zero.
  A stale newest raw file (i.e. ingestion itself has stalled) is also an
  ERROR, because a run that "succeeds" on hours-old input is not healthy.

Known limitation (deliberate, for now): only the NEWEST raw file per source
is processed on each run, exactly like the cleaners' own __main__ blocks.
Raw snapshots that were never cleaned (a missed hour, or the weeks before
this automation existed) are NOT backfilled by this script.

Usage (from the project root, venv active):
    python -m src.loading.run_clean_and_load
"""
import os
import sys
import glob
import time
import traceback

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Put config/ FIRST so `import config` resolves to config/config.py and never
# to the config/ folder itself (which Python can treat as a namespace package
# when the project root is on sys.path, as it is under `python -m`).
sys.path.insert(0, os.path.join(PROJECT_ROOT, "config"))

import config
from src.utils.logger import get_logger
from src.processing import clean_data_gov_in, clean_openaq, clean_open_meteo
from src.loading.load_data_gov_in import load_file as load_data_gov_in
from src.loading.load_openaq import load_file as load_openaq
from src.loading.load_open_meteo import load_file as load_open_meteo

log = get_logger("run_clean_and_load")

# If the newest raw file is older than this, ingestion has stalled. Ingestion
# is hourly, so 3h tolerates a missed run or two without crying wolf.
STALE_RAW_HOURS = 3


def newest_raw(source_dir, pattern):
    """Newest raw file for a source - same selection the cleaners use (last in sorted order)."""
    files = sorted(glob.glob(os.path.join(
        PROJECT_ROOT, config.RAW_DATA_DIR, source_dir, "*", pattern
    )))
    return files[-1] if files else None


def check_raw_age(label, path):
    """Returns True if the raw file is fresh enough. Logs an ERROR if it is stale."""
    age_h = (time.time() - os.path.getmtime(path)) / 3600
    if age_h > STALE_RAW_HOURS:
        log.error(
            f"[{label}] newest raw file is {age_h:.1f}h old (> {STALE_RAW_HOURS}h) - "
            f"ingestion may have stalled: {path}"
        )
        return False
    log.info(f"[{label}] newest raw file is {age_h:.1f}h old: {os.path.basename(path)}")
    return True


def require_newest_raw(label, source_dir, pattern):
    raw = newest_raw(source_dir, pattern)
    if raw is None:
        raise RuntimeError(f"no raw {label} files found")
    return raw, check_raw_age(label, raw)


def run_data_gov_in():
    raw, fresh = require_newest_raw("data_gov_in", "data_gov_in", "*.json")
    df = clean_data_gov_in.process_file(raw)
    out_path = clean_data_gov_in.save_processed(df)
    load_data_gov_in(out_path)
    return fresh


def run_openaq():
    raw, fresh = require_newest_raw("openaq", "openaq", "openaq_latest_*.json")
    df = clean_openaq.process_latest_pair(latest_file=raw)
    if df is None or df.empty:
        raise RuntimeError("OpenAQ cleaning produced no data")
    out_path = clean_openaq.save_processed(df)
    load_openaq(out_path)
    return fresh


def run_open_meteo():
    raw, fresh = require_newest_raw("open_meteo", "open_meteo", "open_meteo_*.json")
    df_curr, df_fcst = clean_open_meteo.process_latest_file(raw)
    if df_curr is None or df_fcst is None or df_curr.empty:
        raise RuntimeError("Open-Meteo cleaning produced no data")
    curr_path, fcst_path = clean_open_meteo.save_processed(df_curr, df_fcst)
    load_open_meteo(curr_path)   # current conditions first...
    load_open_meteo(fcst_path)   # ...then forecast (latest forecast wins)
    return fresh


SOURCES = [
    ("data_gov_in", run_data_gov_in),
    ("openaq", run_openaq),
    ("open_meteo", run_open_meteo),
]


def main():
    log.info("=== clean + load run starting ===")
    failures = []

    for name, run_source in SOURCES:
        started = time.time()
        try:
            raw_is_fresh = run_source()
            if not raw_is_fresh:
                failures.append(f"{name} (stale raw input)")
            log.info(f"[{name}] finished in {time.time() - started:.1f}s")
        except (Exception, SystemExit) as e:
            # SystemExit is caught too: a loader that calls sys.exit() must not
            # silently skip the remaining sources.
            failures.append(f"{name} ({type(e).__name__})")
            log.error(f"[{name}] FAILED after {time.time() - started:.1f}s: {type(e).__name__}: {e}")
            log.error(traceback.format_exc())

    if failures:
        log.error(f"=== run finished WITH FAILURES: {'; '.join(failures)} ===")
        return 1

    log.info("=== run finished OK ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
