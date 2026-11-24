"""News Failure Scan: the daily news-failure scan, one day at a time. LOCAL ONLY.

Registered on a local run (`local_pages.enabled()`), and on the server only with
`local_pages.private_enabled()`, where the layout and the callback both answer nothing
until the browser has logged in at /admin (`local_pages.allowed`). The scan is built on a third-party
positioning index licensed to the operator (a paid product), and reads `cmrdata_store`, which lives
on the operator's machine and is pushed to the server. Unregistered, the path 404s.
The navbar lists it only on a local run, so on the server it is unlinked as well as
gated.

Added 2026-11-18 at the user's request ("can we put these results on a cot-analyzer
page, with formatting for easier reading"). The alert files are long markdown: a
fixed-width board, then one section and one FOR/AGAINST table per set-up, 25 of them on
a normal day. This page leads with the verdict and the counts, puts any row the routine
flagged in a card of its own with its whole argument open, and folds every other row's
evidence under it. Every number and word comes from the day's files through
`components.news_failure`; this file only lays them out.

The market picker turns the page ninety degrees (2026-11-18, "show me all of natural
gas recent info"): one market, every scan day in a window, newest first. While a market
is picked the date picker is disabled, because the day is no longer the thing chosen.

The model picker (2026-11-19) keeps the markets one model holds, and opens on Raw CLS.
Cleared, it shows every market once whichever models hold it: a market's rows differ
between models only in positioning, so the board prints the facts once and names the
models (`components.news_failure.by_market`). The same day the page took its present
name and path, and the scanner's first book became Raw CLS on screen, the name the rest
of the app uses.

Since 2026-11-24 the page is drawn as one of the monitor pages (their page colour, fonts
and header row, `assets/custom.css` `.monitor-page`), as npf's watchlist and timeline
are, and stands alone as they do: the app's navbar is hidden while it is on screen
(the `:has()` rule beside those). The header row adds the three pages behind the login
(`components.news_failure.PRIVATE_SITES`).
"""
import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html
from dash.exceptions import PreventUpdate

import components.news_failure as nf
import local_pages

#: `verify-deploy.sh` pins this path as a 404 on the live site.
PATH = "/news-failure"

DATE = "news_failure_date"
MODEL = "news_failure_model"
MARKET = "news_failure_market"
WINDOW = "news_failure_window"
WINDOW_WRAP = "news_failure_window_wrap"
BODY = "news_failure_body"

#: Scan days, not calendar days: the window counts alert files. 0 is all of them.
WINDOWS = ((10, "Last 10 scan days"), (20, "Last 20"), (40, "Last 40"), (0, "All"))
DEFAULT_WINDOW = 10

REGISTERED = local_pages.enabled() or local_pages.private_enabled()

if REGISTERED:
    dash.register_page(
        __name__,
        path=PATH,
        title='News Failure Scan | COT Analyzer',
        description='The daily news-failure scan: every set-up, its gates, the news '
                    'read and the verdict. Local runs only.',
    )

NOTE_STYLE = {"color": nf.MUTED, "fontSize": "0.8rem"}


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
        options=[{"label": f"{name} ({sym})", "value": sym} for sym, name in nf.markets()],
        style={"width": "230px"})
    window = dcc.Dropdown(id=WINDOW, value=DEFAULT_WINDOW, clearable=False,
                          searchable=False, style={"width": "170px"},
                          options=[{"label": lab, "value": n} for n, lab in WINDOWS])
    model = dcc.Dropdown(id=MODEL, value=nf.DEFAULT_MODEL, clearable=True, searchable=False,
                         placeholder="All models", style={"width": "150px"},
                         options=[{"label": lab, "value": book} for book, lab in nf.MODELS])
    return html.Div([
        _labelled("Day", date_picker(dates, dates[0])),
        _labelled("Model", model),
        _labelled("One market over time", market),
        _labelled("Window", window, id=WINDOW_WRAP, style={"display": "none"}),
    ], className="d-flex align-items-end flex-wrap gap-2")


def body_for(date, market, window, model=None):
    """The page body: one market's history when a market is picked, else one day.
    `model` is a scanner book name, or None for every model."""
    if market:
        name = dict(nf.markets()).get(market, "")
        entries = nf.market_history(market, window or None, book=model)
        return nf.render_history(market, entries, name, book=model)
    return nf.render_day(nf.read_day(date, book=model)) if date else html.Div()


def login_prompt():
    return dbc.Container(html.Div([
        html.H4("News failure scan", style={"color": nf.BRIGHT}),
        html.P(["Log in on the ", html.A("admin page", href="/admin"),
                " first, then come back here."], style=NOTE_STYLE),
    ]), fluid=True, className="py-3")


def layout(**_):
    # Before anything reads the store: a logged-out request gets no dates, no market
    # names and no counts, not just no board.
    if not local_pages.allowed():
        return login_prompt()
    dates = nf.available_dates()
    # The monitors' header: the row of sites, then eyebrow and title on the left and the
    # as-of on the right (the watchlist and timeline pages carry the same one).
    # When the newest alert was written is read per page load, so a day pushed since
    # the last load shows on refresh.
    top = html.Header([
        html.Div([html.Div(["CMR \u00b7 daily scan ", dbc.Badge("private", color="warning")],
                           className="eyebrow"),
                  html.H1("News Failure Scan")]),
        html.Div([f"Last updated {nf.fmt_time(nf.updated_at())}"]
                 + ([html.Br(), f"newest scan day {dates[0]}"] if dates else []),
                 className="asof"),
    ], className="top")
    head = html.Div([
        html.Span("A crowded market handed news it should obey, visibly refusing it. "
                  "\"No failure\" is the normal day.", style=NOTE_STYLE),
        pickers(dates) if dates else html.Span(),
    ], className="d-flex justify-content-between align-items-end flex-wrap gap-2 mb-3")
    if not dates:
        body = html.Div(f"No alerts found under {nf.alerts_dir()}. Set "
                        f"{nf.ENV} to the cmrdata_store checkout.", style=NOTE_STYLE)
    else:
        body = body_for(dates[0], None, DEFAULT_WINDOW, nf.DEFAULT_MODEL)
    # `monitor-page` (assets/custom.css) carries the monitors' page colour, fonts and
    # header rules, scoped to this page so the rest of the app keeps its own theme.
    return html.Div(dbc.Container(
        [html.Link(rel="stylesheet", href=nf.FONTS_HREF), nf.site_nav(), top, head,
         html.Div(body, id=BODY),
         html.P(nf.DISCLAIMER, style={**NOTE_STYLE, "color": nf.FAINT, "marginTop": "16px"})],
        fluid=True, style={"maxWidth": "1400px"}), className="monitor-page")


if REGISTERED:
    @callback(Output(BODY, "children"), Output(DATE, "disabled"),
              Output(WINDOW_WRAP, "style"),
              Input(DATE, "value"), Input(MARKET, "value"), Input(WINDOW, "value"),
              Input(MODEL, "value"), prevent_initial_call=True)
    def _pick(date, market, window, model):
        if not local_pages.allowed():
            raise PreventUpdate      # a forged POST gets a 204, not a board
        return (body_for(date, market, window, model), bool(market),
                {} if market else {"display": "none"})
