# Phase 2 — Environment & Ingestion Setup
**Project:** India Urban Air Quality Intelligence & Early-Warning System
**Status:** Complete

---

## What Was Built

### 1. Local Project Structure
Folders: `data/raw/`, `data/processed/`, `data/external/`, `src/ingestion/`,
`src/utils/`, `config/`, `logs/`, `docs/`, `notebooks/`. Raw data further
split into per-source, per-date subfolders (e.g. `data/raw/data_gov_in/2026-08-17/`).

### 2. Python Virtual Environment
Created with `python -m venv venv` (Python 3.13.7). `ensurepip` was broken
on this machine — pip was manually bootstrapped via `get-pip.py`
(https://bootstrap.pypa.io/get-pip.py). Activate each new terminal session
with `.\venv\Scripts\Activate.ps1` (PowerShell) before running anything.

### 3. Installed Packages
`requests`, `python-dotenv`, `pandas` — recorded in `requirements.txt`
via `pip freeze`.

### 4. Configuration Management
`config/config.py` holds non-secret settings: API base URLs, target city
list (10-12 metros), pollutant list, storage paths, request timeout
(30 seconds). Centralized so scripts never hardcode these values.

### 5. Secrets Handling
`.env` (project root, git-ignored) holds `DATA_GOV_IN_API_KEY` and
`OPENAQ_API_KEY`. `src/utils/secrets_loader.py` loads them via
`python-dotenv` and raises a clear error if either is missing.

### 6. .gitignore
Verified to exclude: `venv/`, `.env`, `__pycache__/`, `data/raw/*`,
`data/processed/*`, `data/external/*`, `logs/*.log`, IDE folders.
Confirmed via `git status` that none of these appear as trackable.

### 7. Logging
`src/utils/logger.py` provides `get_logger(name)` — writes timestamped
INFO/WARNING/ERROR messages to both the console and a daily file
(`logs/YYYY-MM-DD.log`). Used by the ingestion script.

### 8. First Working Ingestion Script
`src/ingestion/fetch_data_gov_in.py` — pulls a live snapshot from the
data.gov.in CPCB Real-Time AQI API and saves it as raw JSON to
`data/raw/data_gov_in/<date>/data_gov_in_<timestamp>.json`.

**Confirmed working:** successfully pulled 2000 station records.

**Key bug fixed:** requests using Python's default `requests` library
User-Agent silently timed out against data.gov.in's server (hung for the
full timeout with no error), while browser requests worked instantly.
Fixed permanently by adding a browser-like `User-Agent` header to the
request. This is now a required part of any request to this API.

Request parameters used: `api-key` (from secrets_loader), `format=json`,
`limit=2000` (do not use `limit=all` — very slow/unreliable).

### 9. Data Versioning Log
`docs/DATA_SOURCES_LOG.md` — tracks the date each source was first
successfully tested and any source-specific quirks (e.g. the User-Agent
issue above). To be updated as OpenAQ, Open-Meteo, and Kaggle are added.

### 10. Git
Local repository initialized. One commit made:
`"Phase 2: environment setup, config, logging, and first working
ingestion script"`. Nothing has been pushed to GitHub yet (deliberate).

---

## Not Yet Done (Phase 3 scope)
- OpenAQ ingestion script
- Open-Meteo ingestion script
- Kaggle historical dataset download
- Scheduling (hourly automated runs)
- Raw → processed cleaning/validation logic
- MySQL setup and loading

## Environment Notes for Future Sessions
- Always `cd C:\Dev\india-air-quality-intel` then
  `.\venv\Scripts\Activate.ps1` in any new terminal before running scripts.
- VS Code's integrated terminal and Pylance may default to the wrong
  (system) Python interpreter — select the `venv` interpreter explicitly
  if import errors appear in the editor; this does not affect terminal runs.
- Project lives outside OneDrive at `C:\Dev\india-air-quality-intel`
  specifically to avoid sync-related file-lock issues encountered earlier
  when the project was inside a OneDrive-synced folder.
