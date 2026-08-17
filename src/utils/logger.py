"""
Centralized logging setup for the Urban Air Quality Intelligence system.
Import get_logger() in any script that needs to log activity.
"""
import logging
import os
from datetime import datetime

LOG_DIR = "logs"


def get_logger(name: str) -> logging.Logger:
    """
    Creates (or retrieves) a logger that writes to both:
    - the console (so you see it live while a script runs)
    - a daily log file in logs/ (so there's a permanent record)
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if this logger was already set up
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    log_filename = os.path.join(LOG_DIR, f"{datetime.now().strftime('%Y-%m-%d')}.log")

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger