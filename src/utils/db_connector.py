"""
Reusable MySQL connection helper.
Mirrors the pattern used in secrets_loader.py: read credentials from .env,
fail loudly and clearly if something required is missing, and hand back
a ready-to-use connection object.
"""

import os
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """
    Opens and returns a new MySQL connection using credentials from .env.
    Raises a clear error immediately if required env vars are missing,
    or if the connection itself fails (wrong password, server down, etc.)
    rather than letting a caller hit a confusing error later.
    """
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_PASSWORD")

    if not user or not password:
        raise EnvironmentError(
            "MYSQL_USER and/or MYSQL_PASSWORD not found in .env. "
            "Add them before running any database scripts."
        )

    try:
        connection = mysql.connector.connect(
            host="127.0.0.1",
            port=3306,
            database="india_air_quality",
            user=user,
            password=password,
        )
        return connection
    except Error as e:
        raise ConnectionError(f"Failed to connect to MySQL: {e}")