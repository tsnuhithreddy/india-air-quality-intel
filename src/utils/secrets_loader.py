"""
Loads API credentials from the .env file.
Never hardcode keys directly in scripts — always import from here.
"""
import os
from dotenv import load_dotenv

load_dotenv()

DATA_GOV_IN_API_KEY = os.getenv("DATA_GOV_IN_API_KEY")
OPENAQ_API_KEY = os.getenv("OPENAQ_API_KEY")

# MySQL Configuration
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "india_air_quality_db")

if not DATA_GOV_IN_API_KEY:
    raise ValueError("DATA_GOV_IN_API_KEY not found. Check your .env file.")
if not OPENAQ_API_KEY:
    raise ValueError("OPENAQ_API_KEY not found. Check your .env file.")

def redact_secrets(text: str) -> str:
    """
    Replace any known API key or DB password with a placeholder
    before logging exception messages, URLs, or connection strings.
    """
    if not text:
        return text

    for key in (DATA_GOV_IN_API_KEY, OPENAQ_API_KEY, MYSQL_PASSWORD):
        if key:
            text = text.replace(key, "***REDACTED***")

    return text