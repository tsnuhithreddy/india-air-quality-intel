# Phase 2: Environment & Ingestion Setup

**Project:** India Urban Air Quality Intelligence & Early-Warning System
**Status:** Complete
**Worked on:** 2026-08-14 to 2026-08-17

---

## Goal

Phase 1 settled which data sources to use. Phase 2 was about getting a working
foundation in place before building anything bigger: a reproducible Python
environment, a clean folder layout, safe handling of API keys, logging, and one
ingestion script that pulls a real live snapshot from the primary source
(data.gov.in, CPCB Real-Time AQI) and saves it to disk.

Nothing in this phase touches analysis, databases, or dashboards. Scheduling is
also left for Phase 3, so the ingestion script is run by hand for now.

---

## What was built

### 1. Project location and folder structure

The project lives at `C:\Dev\india-air-quality-intel`. It started inside a
OneDrive-synced Desktop folder whose name had spaces and an `&` in it, and that
caused trouble with the virtual environment (see "Problems hit" below). Moving it
to a short path outside OneDrive avoids that and also avoids sync-related file
locking later.

```
india-air-quality-intel/
├── config/                 non-secret settings
├── data/
│   ├── raw/                untouched API responses
│   │   ├── data_gov_in/
│   │   ├── open_meteo/
│   │   └── openaq/
│   ├── processed/          cleaned data (same per-source subfolders, empty for now)
│   └── external/           for one-time datasets such as the Kaggle download
├── docs/                   DATA_SOURCES_LOG.md
├── files/                  Phase documents (PHASE1..., PROJECT_STATE...)
├── logs/                   daily log files
├── notebooks/              empty for now
├── src/
│   ├── ingestion/          scripts that call the APIs
│   └── utils/              logger and secrets loader
├── requirements.txt
├── .gitignore
└── .env                    API keys (git-ignored)
```

The phase documents sit in `files/` while the sources log sits in `docs/`. That
is a small inconsistency I haven't cleaned up yet.

### 2. Python virtual environment

Created with Python 3.13.7. The normal `python -m venv venv` command failed on
this machine (see below), so the environment was created with
`python -m venv --without-pip venv` and pip was added afterwards using the
official `get-pip.py` script. pip ended up at version 26.2.1, installed inside
the venv.

The venv has to be activated in every new terminal session. From PowerShell:

```powershell
cd C:\Dev\india-air-quality-intel
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks the script, run this once in that terminal first (it only
applies to the current window):

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

The prompt should then start with `(venv)`.

### 3. Packages and requirements.txt

Only three packages were installed directly:

| Package | Used for |
|---|---|
| `requests` | HTTP calls to the APIs |
| `python-dotenv` | loading API keys from `.env` |
| `pandas` | installed for later phases, not used yet |

`requirements.txt` was generated with `python -m pip freeze > requirements.txt`
and pins everything that came along with them:

```
certifi==2026.7.22
charset-normalizer==3.5.0
idna==3.18
numpy==2.5.2
pandas==3.0.5
python-dateutil==2.9.0.post0
python-dotenv==1.2.2
requests==2.34.2
six==1.17.0
tzdata==2026.3
urllib3==2.7.0
```

To rebuild the environment on another machine:
`python -m pip install -r requirements.txt`.

### 4. Configuration (`config/config.py`)

Holds settings that are safe to commit: the three API base URLs (data.gov.in,
OpenAQ v3, Open-Meteo), the list of 11 target cities (Delhi, Mumbai, Bengaluru,
Hyderabad, Chennai, Kolkata, Pune, Ahmedabad, Lucknow, Jaipur, Patna), the
pollutant list, the storage folder names, and `REQUEST_TIMEOUT_SECONDS`.

The timeout is 30 seconds. I raised it to 60 while debugging the timeout problem
below and put it back once the real cause was found.

### 5. Secrets (`.env` and `src/utils/secrets_loader.py`)

The two API keys (`DATA_GOV_IN_API_KEY`, `OPENAQ_API_KEY`) are in `.env` at the
project root. `secrets_loader.py` loads that file with `python-dotenv` and exposes
the keys as variables other scripts can import. If either key is missing it
raises an error straight away rather than failing later in the middle of a
request.

Both keys were verified to load. The OpenAQ key is stored but no OpenAQ request
has been made yet.

Settings and secrets are deliberately in separate files, so `config.py` can be
shared freely and `.env` never leaves the machine.

### 6. `.gitignore`

Excludes the venv, `.env` and `.env.*`, `__pycache__/` and compiled files,
Jupyter checkpoints, `logs/*.log`, the contents of `data/raw`, `data/processed`
and `data/external`, OS files, and IDE folders. I checked `git status` before
committing and none of the excluded items showed up as trackable.

### 7. Data storage convention

Agreed before writing any ingestion code:

```
data/raw/<source>/<YYYY-MM-DD>/<source>_<YYYYMMDD_HHMM>.json
data/processed/<source>/<YYYY-MM-DD>/<source>_<YYYYMMDD_HHMM>_clean.csv
```

Raw files are saved exactly as the API returned them (JSON) and are never edited
or overwritten. Every pull gets its own timestamped file. This matters here
because the primary API only shows the current moment, so these saved snapshots
are the only history that will exist for it. Cleaned CSVs are a separate layer
that can be regenerated from the raw files at any time. Only the raw side is
used so far; the processed folders are empty.

### 8. Logging (`src/utils/logger.py`)

`get_logger(name)` returns a logger that writes every message to both the
terminal and a daily file, `logs/YYYY-MM-DD.log`, in this format:

```
2026-08-17 16:51:13 | INFO     | fetch_data_gov_in | Requesting live snapshot from data.gov.in...
```

Levels used are INFO, WARNING and ERROR. It checks for existing handlers so that
calling it twice doesn't print every line twice. The reason for building it this
early is that the pipeline is meant to run unattended later, and a log file is
the only way to find out what happened while nobody was watching.

Tested by logging one message at each level and confirming the same three lines
appeared in the terminal and in `logs/2026-08-15.log`.

### 9. Ingestion script (`src/ingestion/fetch_data_gov_in.py`)

Pulls one live snapshot from the data.gov.in CPCB Real-Time AQI resource
(`3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69`) and saves the raw response.

How it works:

1. Works out the project root from its own file location, so it runs correctly
   from any folder.
2. Imports the API key, the logger and the config.
3. `fetch_snapshot()` sends a GET request with `api-key`, `format=json` and
   `limit=2000`, a browser-style `User-Agent` header, and the timeout from
   config. Any request error is caught and logged, and the function returns
   `None` instead of crashing.
4. It logs how many records came back.
5. `save_raw_snapshot()` writes the response to
   `data/raw/data_gov_in/<date>/data_gov_in_<timestamp>.json`.

Run it from the project root with the venv active:

```powershell
python src/ingestion/fetch_data_gov_in.py
```

Result from the first successful run (2026-08-17):

```
16:51:13 | INFO | fetch_data_gov_in | Requesting live snapshot from data.gov.in...
16:51:14 | INFO | fetch_data_gov_in | Received 2000 station records.
16:51:14 | INFO | fetch_data_gov_in | Saved raw snapshot to ...\data\raw\data_gov_in\2026-08-17\data_gov_in_20260817_1651.json
```

### 10. Sources log (`docs/DATA_SOURCES_LOG.md`)

A short running record of when each source was first tested and any quirks found
along the way. At the end of this phase only data.gov.in has an entry with a
real date (2026-08-17); OpenAQ, Open-Meteo and Kaggle are listed as not yet
tested or downloaded.

### 11. Git

The repository was initialised locally and one commit was made at the end of
the phase:

```
b8c6960  Phase 2: environment setup, config, logging, and first working ingestion script
```

It contains 9 files: `.gitignore`, `config/config.py`, `docs/DATA_SOURCES_LOG.md`,
the two Phase 1 documents in `files/`, `requirements.txt`, and the three Python
files under `src/`. I read the staged file list before committing to make sure
nothing from `.env`, `venv/` or `data/` was in it.

---

## Problems hit and how they were resolved

| Problem | Cause | Fix |
|---|---|---|
| `python -m venv venv` failed at the `ensurepip` step, in both the original and the new location | The Python install's bundled pip bootstrap is broken on this machine. I didn't track down why. | Created the venv with `--without-pip`, then installed pip with `get-pip.py` |
| First venv attempt failed inside the OneDrive folder | Project path was in a synced folder and contained spaces and an `&`. Possibly a contributor, though the failure continued after moving, so it was not the only cause. | Moved the project to `C:\Dev\india-air-quality-intel` |
| A scratch file with the raw API keys (`api key.txt`) was sitting in the project root, not covered by `.gitignore` | Keys had been copied there while signing up | Deleted it before the first commit. It was never staged. |
| `No module named 'dotenv'` when running from VS Code | VS Code was using the system Python, not the venv | Ran the scripts from a terminal with the venv active |
| `No such file or directory` and "venv not recognised" errors | Commands were run from `src/ingestion` instead of the project root, and the venv was not active in a new terminal | Always `cd` to the project root and activate the venv first |
| Ingestion request timed out every time | See below | Added a browser-style `User-Agent` header |

### The data.gov.in timeout

The first runs of the ingestion script hung until the timeout and failed with
`Read timed out`, while the same URL loaded in a browser in under three seconds.

What I tried, in order:

1. Changed `limit=all` to `limit=2000` and raised the timeout to 60 seconds.
   Still timed out.
2. Dropped the limit to 100 through the script. Still timed out, so response
   size was not the problem.
3. Called `api.github.com` from Python. That responded immediately, so Python's
   networking in general was fine.
4. Sent the same data.gov.in request with a browser-style `User-Agent` header.
   It returned status 200 in about two seconds.

Adding that header to the real script fixed it (2000 records back in about a
second). My conclusion is that the server ignores requests that identify
themselves as `python-requests`. I haven't confirmed that with the data.gov.in
team, so it is an inference from the tests above, not documented behaviour. It
does mean any future script that calls this API needs the same header, and it is
recorded in `docs/DATA_SOURCES_LOG.md`.

---

## Known limitations and open items

- **The 2000 may be a cap, not the full dataset.** The script asks for
  `limit=2000` and gets exactly 2000 back. I haven't checked whether the API
  holds more than that (its response should say how many records exist in
  total). This needs checking before relying on the snapshot being complete.
- **The saved JSON hasn't been inspected field by field.** Field names and
  units are for Phase 3, when the cleaning script is written. Phase 1 already
  noted that units may differ between pollutants.
- **The Kaggle date range is unverified.** The "2015 to 2024" coverage in the
  Phase 1 notes and in `DATA_SOURCES_LOG.md` comes from the dataset's
  description and has not been checked against the actual files yet.
- **One manual run only.** No scheduling exists, so no history is accumulating
  yet.
- **Only one of three live sources is done.** OpenAQ has a key but no script;
  Open-Meteo has no script; nothing has been downloaded from Kaggle.
- **VS Code still points at the wrong interpreter**, so Pylance shows
  "import could not be resolved" warnings on the scripts. They run fine from a
  terminal with the venv active. I left this alone.
- **`pandas` is installed but unused**, kept because the next phase needs it.
- **Nothing has been cleaned, validated, or loaded anywhere.** `data/processed/`
  is empty and there is no database yet.

---

## Next: Phase 3

1. OpenAQ ingestion script (check the `User-Agent` behaviour there as well)
2. Open-Meteo ingestion script
3. Download the Kaggle historical dataset and verify its real date range
4. Schedule the ingestion so it runs hourly without being started by hand
5. First raw-to-processed cleaning script
