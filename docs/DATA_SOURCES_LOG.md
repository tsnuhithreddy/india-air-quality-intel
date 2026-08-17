\# Data Sources Log



Tracks when each data source was acquired/first tested, for reproducibility.



\## Live API Sources



| Source | First successful pull | Notes |

|---|---|---|

| data.gov.in CPCB Real-Time AQI | 2026-08-17 | Required custom User-Agent header to avoid silent timeout (see src/ingestion/fetch\_data\_gov\_in.py) |

| OpenAQ v3 | Not yet tested | |

| Open-Meteo | Not yet tested | |



\## Static/Historical Sources



| Source | Downloaded on | Version/notes |

|---|---|---|

| Kaggle "Air Quality Data in India" (2015-2024) | Not yet downloaded | |



\## Known Source-Specific Quirks

\- data.gov.in silently times out (no error, just hangs) if the request doesn't include a browser-like `User-Agent` header. Fixed permanently in `fetch\_data\_gov\_in.py`.

