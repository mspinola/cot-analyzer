import constants
import pytz

from datetime import datetime, timedelta, timezone
from flask import request
import logging
from logging.handlers import RotatingFileHandler
import os

def get_visitor_logger():
    logger = logging.getLogger("visitor_logger")

    # Prevents adding multiple handlers if the function is called twice
    if not logger.handlers:
        log_dir = "log"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        handler = RotatingFileHandler(
            os.path.join(log_dir, "visitor_access.log"),
            maxBytes=10*1024*1024,
            backupCount=5
        )
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        # Ensure it doesn't send logs to the root logger as well (prevents duplicates)
        logger.propagate = False

    return logger
visitor_logger = get_visitor_logger()

def get_downloader_logger():
    logger = logging.getLogger("downloader_logger")

    # Prevents adding multiple handlers if the function is called twice
    if not logger.handlers:
        log_dir = "log"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        handler = RotatingFileHandler(
            os.path.join(log_dir, "downloader_access.log"),
            maxBytes=10*1024*1024,
            backupCount=5
        )
        formatter = logging.Formatter('%(asctime)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        # Ensure it doesn't send logs to the root logger as well (prevents duplicates)
        logger.propagate = False

    return logger
downloader_logger = get_downloader_logger()

def is_mobile():
    """Detects if the user agent belongs to a mobile device."""
    user_agent = request.headers.get("User-Agent", "").lower()
    mobile_keywords = ["android", "webos", "iphone", "ipad",
                       "ipod", "blackberry", "iemobile", "opera mini"]
    return any(keyword in user_agent for keyword in mobile_keywords)


def milliseconds_until_midnight():
    """Calculate the number of milliseconds until the next midnight in the app's timezone."""
    local_tz = pytz.timezone(constants.app_timezone)
    now = datetime.now(tz=local_tz)
    next_midnight = (now + timedelta(days=1)).replace(hour=0,
                                                      minute=0,
                                                      second=0,
                                                      microsecond=0)
    delta = next_midnight - now
    return int(delta.total_seconds() * 1000)


def parse_setup_thresholds(setup):
    if setup == '95 5':
        max_threshold = 95
        min_threshold = 5
    elif setup == '90 10':
        max_threshold = 90
        min_threshold = 10
    elif setup == '75 25':
        max_threshold = 75
        min_threshold = 25
    else:
        max_threshold = None
        min_threshold = None

    return min_threshold, max_threshold


def get_lookback_weeks(lookback, instrument):
    if lookback == "26":
        return 26
    elif lookback == "52":
        return 52
    else:
        return instrument.custom_lookback
