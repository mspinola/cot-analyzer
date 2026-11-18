"""CMR Scan: the daily CMR news-failure scan, one day at a time. LOCAL ONLY.

Registered only when `local_pages.enabled()`: the scan is built on the CMR COT Index,
a paid membership licensed to the operator, and reads `cmrdata_store`, which only the
operator's machine has. Unregistered, the path 404s and the navbar omits it
(`local_pages`).

Added 2026-11-18 at the user's request ("can we put these results on a cot-analyzer
page, with formatting for easier reading"). The alert files are long markdown: a
fixed-width board, then one section and one FOR/AGAINST table per set-up, 25 of them on
a normal day. This page leads with the verdict and the counts, puts any row the routine
flagged in a card of its own with its whole argument open, and folds every other row's
evidence under it. Every number and word comes from the day's files through
`components.cmr_scan`; this file only lays them out.

The market picker turns the page ninety degrees (2026-11-18, "show me all of natural
gas recent info"): one market, every scan day in a window, newest first. While a market
is picked the date picker is disabled, because the day is no longer the thing chosen.
"""
import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html

import components.cmr_scan as cmr
import local_pages
import viz_constants as vc

DATE = "cmr_scan_date"
MARKET = "cmr_scan_market"
WINDOW = "cmr_scan_window"
WINDOW_WRAP = "cmr_scan_window_wrap"
BODY = "cmr_scan_body"

#: Scan days, not calendar days: the window counts alert files. 0 is all of them.
WINDOWS = ((10, "Last 10 scan days"), (20, "Last 20"), (40, "Last 40"), (0, "All"))
DEFAULT_WINDOW = 10

if local_pages.enabled():
    dash.register_page(
        __name__,
        path='/cmr',
        title='CMR Scan (local) | COT Analyzer',
        description='The daily CMR news-failure scan: every set-up, its gates, the news '
                    'read and the verdict. Local runs only.',
    )

NOTE_STYLE = {"color": vc.TEXT_COLOR, "fontSize": "0.8rem"}


def date_picker(dates, value):
    # No persistence, as on the sentiment page: layout() draws the newest day and the
    # callback does not fire on load, so a restored value would disagree with the body.
    return dcc.Dropdown(id=DATE, options=[{"label": d, "value": d} for d in dates],
                        value=value, clearable=False, searchable=False,
                        style={"width": "170px"})


def _labelled(label, control, **div):
    return html.Div([html.Div(label, style={**NOTE_STYLE, "fontSize": "0.7rem",
                                            "textTransform": "uppercase",
                                            "letterSpacing": "0.06em"}), control], **div)


def pickers(dates):
    market = dcc.Dropdown(
        id=MARKET, value=None, clearable=True, placeholder="All markets",
        options=[{"label": f"{name} ({sym})", "value": sym} for sym, name in cmr.markets()],
        style={"width": "230px"})
    window = dcc.Dropdown(id=WINDOW, value=DEFAULT_WINDOW, clearable=False,
                          searchable=False, style={"width": "170px"},
                          options=[{"label": lab, "value": n} for n, lab in WINDOWS])
    return html.Div([
        _labelled("Day", date_picker(dates, dates[0])),
        _labelled("One market over time", market),
        _labelled("Window", window, id=WINDOW_WRAP, style={"display": "none"}),
    ], className="d-flex align-items-end flex-wrap gap-2")


def body_for(date, market, window):
    """The page body: one market's history when a market is picked, else one day."""
    if market:
        name = dict(cmr.markets()).get(market, "")
        return cmr.render_history(market, cmr.market_history(market, window or None), name)
    return cmr.render_day(cmr.read_day(date)) if date else html.Div()


def layout(**_):
    dates = cmr.available_dates()
    head = html.Div([
        html.Div([
            html.H4("CMR news-failure scan", style={"color": vc.BRIGHTER_TEXT_COLOR,
                                                    "marginBottom": "2px"}),
            dbc.Badge("local only", color="warning", className="me-2"),
            html.Span("A crowded market handed news it should obey, visibly refusing it. "
                      "\"No failure\" is the normal day.", style=NOTE_STYLE),
        ]),
        pickers(dates) if dates else html.Span(),
    ], className="d-flex justify-content-between align-items-start flex-wrap gap-2 mb-3")
    if not dates:
        body = html.Div(f"No alerts found under {cmr.alerts_dir()}. Set "
                        f"{cmr.ENV} to the cmrdata_store checkout.", style=NOTE_STYLE)
    else:
        body = body_for(dates[0], None, DEFAULT_WINDOW)
    return dbc.Container([head, html.Div(body, id=BODY),
                          html.P(cmr.DISCLAIMER, style={**NOTE_STYLE, "marginTop": "16px"})],
                         fluid=True, className="py-3", style={"maxWidth": "1400px"})


if local_pages.enabled():
    @callback(Output(BODY, "children"), Output(DATE, "disabled"),
              Output(WINDOW_WRAP, "style"),
              Input(DATE, "value"), Input(MARKET, "value"), Input(WINDOW, "value"),
              prevent_initial_call=True)
    def _pick(date, market, window):
        return (body_for(date, market, window), bool(market),
                {} if market else {"display": "none"})
