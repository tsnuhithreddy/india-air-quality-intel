"""
Central configuration for the India Urban Air Quality Intelligence system.
Non-secret settings only. API keys/secrets belong in .env, NOT here.
"""

# --- API Base URLs (from Phase 1 validation) ---
PRIMARY_API_BASE_URL = "https://api.data.gov.in/resource/3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"
OPENAQ_API_BASE_URL = "https://api.openaq.org/v3"
OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"

# --- Target Cities (initial scope per Phase 1: 10-12 major metros) ---
TARGET_CITIES = [
    "Delhi",
    "Mumbai",
    "Bengaluru",
    "Hyderabad",
    "Chennai",
    "Kolkata",
    "Pune",
    "Ahmedabad",
    "Lucknow",
    "Jaipur",
    "Patna",
]

# --- Pollutants tracked (availability varies by station) ---
POLLUTANTS = ["PM2.5", "PM10", "SO2", "NO2", "CO", "O3", "NH3", "Pb"]

# --- Storage Paths (relative to project root) ---
RAW_DATA_DIR = "data/raw"
PROCESSED_DATA_DIR = "data/processed"
EXTERNAL_DATA_DIR = "data/external"
LOG_DIR = "logs"

# --- Request Settings ---
REQUEST_TIMEOUT_SECONDS = 30
