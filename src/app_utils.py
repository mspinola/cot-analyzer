"""
app_utils.py

App-layer (Dash/Flask) helpers. Kept out of the data layer so cotmetrics.utils
carries no web-framework dependency.
"""
import flask
from dash import no_update

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


def next_date_selection(dates, current_options, current_value):
    """`(options, value)` for the Target Date control when the store may have moved.

    A page resolves its date list once, at page load, so before this a tab left open
    across a Friday release could not reach the new week at all: it was absent from the
    dropdown, and the grid renders strictly from the selection. The navbar badge above
    it updated on its own five-minute interval, so the page contradicted its own header
    for as long as the tab stayed open. Observed 2026-08-14, when the 2026-08-11 week
    landed at 15:34.

    Following the new week is conditional, and that is the whole subtlety. Sitting on
    the newest week is the default nobody chose, so it tracks. Having picked an older
    one is a decision, and yanking a reader off the week they are reading because the
    CFTC published is worse than leaving them there with the new one now offered. The
    test is whether the current selection WAS the newest, which the old options list
    answers without anything having to be remembered server-side.

    Kept apart from the callback because the interesting half is this arithmetic, and a
    Dash callback cannot be called directly to check it. It lives here rather than on the
    Heatmap because the Crowding Strip has the same control and the same problem, and a
    page importing another page to borrow a helper is a dependency neither one wants.
    """
    if not dates:
        return no_update, no_update

    options = [{'label': d, 'value': d} for d in dates]
    if options == current_options:
        return no_update, no_update

    previous = [o['value'] for o in (current_options or [])]
    was_on_newest = not previous or current_value == previous[0]
    value = dates[0] if (was_on_newest or current_value not in dates) else current_value
    return options, value
