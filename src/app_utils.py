"""
app_utils.py

App-layer (Dash/Flask) helpers. Kept out of the data layer so cotmetrics.utils
carries no web-framework dependency.
"""
from flask import request


def is_mobile():
    """Detects if the user agent belongs to a mobile device."""
    user_agent = request.headers.get("User-Agent", "").lower()
    mobile_keywords = ["android", "webos", "iphone", "ipad",
                       "ipod", "blackberry", "iemobile", "opera mini"]
    return any(keyword in user_agent for keyword in mobile_keywords)
