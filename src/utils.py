import constants
import pytz

from datetime import datetime, timedelta, timezone
from flask import request


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
                                                      minute=0, second=0, microsecond=0)
    delta = next_midnight - now
    return int(delta.total_seconds() * 1000)


def parse_setup_thresholds(setup):
    if setup == '95 5':
        max_threshold = 95
        min_threshold = 5
    elif setup == '90 10':
        max_threshold = 9
        min_threshold = 10
    elif setup == '75 25':
        max_threshold = 75
        min_threshold = 25
    else:
        max_threshold = 101
        min_threshold = -1

    return min_threshold, max_threshold
