"""
Loads API credentials from the .env file.
Never hardcode keys directly in scripts — always import from here.
"""
import os
from dotenv import load_dotenv

load_dotenv()

DATA_GOV_IN_API_KEY = os.getenv("DATA_GOV_IN_API_KEY")
OPENAQ_API_KEY = os.getenv("OPENAQ_API_KEY")

if not DATA_GOV_IN_API_KEY:
    raise ValueError("DATA_GOV_IN_API_KEY not found. Check your .env file.")
if not OPENAQ_API_KEY:
    raise ValueError("OPENAQ_API_KEY not found. Check your .env file.")