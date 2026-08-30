"""
app_utils.py

App-layer (Dash/Flask) helpers. Kept out of the data layer so cotmetrics.utils
carries no web-framework dependency.
"""
import urllib.parse

import flask

# The union of the two keyword lists that used to live here and (inline) in
# plot_layout.visible_weeks / plot_traces. Two sniffs that disagree mean one
# surface narrows its x-window while another still renders desktop chrome for
# the same visitor, so there is exactly one list and one function now.
MOBILE_UA_KEYWORDS = ["mobile", "android", "webos", "iphone", "ipad", "ipod",
                      "phone", "blackberry", "iemobile", "opera mini"]


def is_mobile():
    """Whether the CURRENT request's user agent is a mobile device.

    Guarded rather than assuming a request context: layout() and figure code
    run inside callbacks in production, but tests call them directly, and
    "desktop" is the answer that changes nothing there.
    """
    if not flask.has_request_context():
        return False
    user_agent = flask.request.headers.get("User-Agent", "").lower()
    return any(keyword in user_agent for keyword in MOBILE_UA_KEYWORDS)


def clicked_market_href(click_data):
    """The Market Detail href for a board-figure click, or None to stay put.

    Reads the point's customdata, which the Strip's and the Crowd board's
    hoverable traces set to the market's name. A click on a mark without one (a
    decorative trace) navigates nowhere, which is also what makes clicking safe
    to wire at all: only the marks that already carry a hover are targets.
    """
    try:
        asset = click_data['points'][0]['customdata']
    except (TypeError, KeyError, IndexError):
        return None
    if not asset or not isinstance(asset, str):
        return None
    return f"/oi_alignment?asset={urllib.parse.quote(asset)}"
