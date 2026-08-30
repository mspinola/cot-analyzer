import os
import queue
import threading

import cotmetrics.models as models
import cotmetrics.utils as utils
import dash
import dash_bootstrap_components as dbc
import requests
from cotmetrics.database import cotDatabase
from cotmetrics.indexer import get_indexer
from dash import Dash, Input, Output, State, dcc, html, no_update
from flask import request
from flask_compress import Compress

import routing
import visitors
import viz_constants as vc

utils.launch_logger.warning("Launch app_cot")

app = Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[
        dbc.themes.DARKLY,
        # The `bi bi-*` classes used across the pages are Bootstrap Icons, which DARKLY
        # does not carry. Without this every one of them rendered as a zero-width empty
        # element: the Home hero and screener headers, the download buttons on the
        # options and positioning pages. They had never displayed.
        dbc.icons.BOOTSTRAP,
        "https://cdn.jsdelivr.net/npm/ag-grid-community/styles/ag-theme-quartz.css"
    ],
    external_scripts=[
        "https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"
    ],
    suppress_callback_exceptions=True,
)
server = app.server
Compress(server)


def goatcounter_index_string(origin):
    """Dash's default index template with a self-hosted GoatCounter tracker appended.

    Two scripts, and the first exists because Dash is a single-page app: count.js on
    its own counts the document load and then never again, since navigation is
    pushState. The hook disables the onload count, counts once when the page settles,
    and re-counts on every pushState and popstate, which is exactly the set of
    transitions the client-side router makes. Everything else is Dash's stock
    template, spelled out because `index_string` replaces the whole thing.
    """
    return '''<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
        <script>
            window.goatcounter = {no_onload: true};
            (function () {
                var count = function () {
                    if (window.goatcounter.count) {
                        window.goatcounter.count({path: location.pathname});
                    }
                };
                window.addEventListener('load', function () { setTimeout(count, 1); });
                var push = history.pushState;
                history.pushState = function () {
                    push.apply(history, arguments);
                    count();
                };
                window.addEventListener('popstate', count);
            })();
        </script>
        <script data-goatcounter="__GC_ORIGIN__/count" async src="__GC_ORIGIN__/count.js"></script>
    </body>
</html>'''.replace('__GC_ORIGIN__', origin)


# Client-side analytics are opt-in per deployment: set GOATCOUNTER_URL to the origin
# of a GoatCounter instance (e.g. https://stats.example.com, no trailing path) in .env
# and every served page reports to it. Unset, the page is byte-identical to stock and
# nothing loads. run-local.sh does not set it, so local work stays untracked.
_goatcounter_origin = os.getenv('GOATCOUNTER_URL')
if _goatcounter_origin:
    app.index_string = goatcounter_index_string(_goatcounter_origin.rstrip('/'))


@app.server.before_request
def reject_unknown_paths():
    """Answer 404 for paths that match no page, instead of 200 with the app shell.

    The membership test and the body live in `routing`; see that module for why the
    catch-all makes every url a 200 by default. What belongs here is the ordering:
    registered BEFORE `record_visit` deliberately. Flask runs before_request handlers in
    registration order and stops at the first that returns a response, so this position
    is what keeps a probe out of the visitor DB and, more to the point, out of the
    third-party geolocation lookup `record_visit` performs on every logged request.

    The registry and route list are read per request rather than captured at import, so
    a page added later is served without touching this function.
    """
    page_paths = [page.get('path') for page in dash.page_registry.values()]
    if routing.is_known_path(request.path, page_paths, app.routes):
        return None
    body = routing.not_found_page(
        vc.BACKGROUND_COLOR, vc.TEXT_COLOR, vc.BRIGHTER_TEXT_COLOR)
    return body, 404, {'Content-Type': 'text/html; charset=utf-8'}


@app.server.before_request
def decline_vendor_sourcemaps():
    """Answer 404 for source-map requests Dash would 500 on; see `is_vendor_sourcemap`.

    Registered after `reject_unknown_paths` (the prefix admits these paths) and before
    `record_visit`, though the ignore list below also covers them: a devtools asset
    fetch should never reach the geolocation lookup.
    """
    if routing.is_vendor_sourcemap(request.path):
        return '', 404
    return None


# ── visit capture ─────────────────────────────────────────────────────────────
#
# Two kinds of row, written through one queue:
#
# - 'landing': a document GET, captured by the before_request hook below. The only
#   moment the EXTERNAL referrer exists, and for a single-page app also the only
#   HTTP-visible page event: after this, navigation is client-side.
# - 'pageview': every page the client-side router shows, captured by the callback on
#   the `url` Location further down. It fires on the initial load too, so the pageview
#   stream alone is the complete view count and a landing row is never added to it.
#
# Nothing slow runs in the request: the hook and the callback only derive the visitor
# hash and enqueue, and a single daemon thread does the geolocation (cached per IP in
# the database, so ip-api.com is asked about an address once, not per request), the
# sqlite insert AND the journal line. The old inline version cost every logged request
# a blocking lookup against ip-api's 45/min limit.
#
# The journal line is on that list because the lookup is what decides whether the visit
# was automated at all: two of the three signals (a datacenter address, and geography)
# only exist once it has returned. Only the user-agent test is free.

_visit_queue = queue.Queue()
_visit_worker_lock = threading.Lock()
_visit_worker_started = False


def _fetch_geo(ip_addr):
    """One ip-api.com lookup: (city, country, hosting).

    ('Lookup', 'Error', False) means failed, and is NOT cached, so a later event for
    the same address retries.

    `hosting` is ip-api's datacenter/proxy flag, free-tier and returned beside city and
    country for no extra request. `fields` is explicit because the flag is not in the
    default response; naming the fields also keeps the reply small.

    It is coerced to a real bool rather than passed through, because None would mean
    "unknown" to the cache and be refetched forever. An absent field means ip-api
    answered and did not call this address hosting, which is a False, not a mystery.
    """
    try:
        response = requests.get(
            f"http://ip-api.com/json/{ip_addr}"
            "?fields=status,message,city,country,hosting",
            timeout=2).json()
        if response.get('status') == 'success':
            return (response.get('city'), response.get('country'),
                    bool(response.get('hosting')))
    except Exception:
        pass
    return "Lookup", "Error", False


def _process_visit(row, db=None, fetch=None):
    """Resolve geography, decide whether the visit was automated, write the row, log it.

    `db` and `fetch` are injectable for tests; production passes neither.

    THE LOG LINE IS EMITTED HERE, not at enqueue time, and that is the whole point of
    this function's shape. A scanner sending a browser-shaped user agent is invisible to
    `visitors.is_bot`, and the only thing that separates it from a visitor is the
    address it came from, which costs a network lookup to learn. Logging at enqueue time
    would mean logging before the answer exists.

    The cost is that the line arrives a few hundred milliseconds late on a cache miss
    and out of order with werkzeug's access line for the same request. That is a journal,
    so ordering buys nothing; being right about which lines are worth reading does.

    Suppression stays a display decision. Every visit still gets its row, and `is_bot`
    still records the verdict, so the admin page's filter sees these exactly as it sees
    a self-described crawler.
    """
    db = db if db is not None else cotDatabase
    fetch = fetch if fetch is not None else _fetch_geo
    ip_addr = row['ip']
    if ip_addr in ('', '127.0.0.1', 'localhost', '::1'):
        city, country, hosting = "Internal", "Local", False
    else:
        cached = db.get_cached_geo(ip_addr)
        hosting = db.get_cached_hosting(ip_addr)
        # Both, not either: a row cached before `hosting` existed has the geography and
        # not the flag, and refetching once is what fills it in. `cache_geo` never
        # writes NULL for an answered lookup, so that refetch happens once per address
        # rather than on every visit it makes.
        if cached is not None and hosting is not None:
            city, country = cached
        else:
            city, country, hosting = fetch(ip_addr)
            if (city, country) != ("Lookup", "Error"):
                db.cache_geo(ip_addr, city, country, hosting)

    # A datacenter address is automated traffic whatever its user agent claims. OR-ing
    # into the one flag rather than adding a second column loses nothing recoverable:
    # the row keeps both `user_agent` and `ip_address`, so which signal caught a given
    # visit is still derivable after the fact.
    bot = bool(row['is_bot'] or hosting)
    db.log_visit(ip_addr, row['path'], row['ua'], city, country,
                 kind=row['kind'], visitor_id=row['visitor_id'],
                 is_bot=bot, referrer=row['referrer'])

    line = f"IP: {ip_addr} | Path: {row['path']}"
    if bot:
        utils.cot_logger.debug(line + (" | datacenter" if hosting else " | bot"))
    else:
        utils.cot_logger.info(line)


def _visit_worker():
    while True:
        row = _visit_queue.get()
        try:
            _process_visit(row)
        except Exception as e:
            utils.cot_logger.error(f"visit worker failed on {row.get('path')}: {e}")


def _enqueue_visit(kind, path):
    """Build a visit row from the CURRENT flask request and hand it to the worker.

    Must run inside a request context (a before_request hook or a callback, both
    qualify). The worker is started lazily rather than at import so importing this
    module (tests, tooling) starts no thread and writes nothing.
    """
    global _visit_worker_started
    ip_addr = visitors.client_ip(request.headers.get('X-Forwarded-For'),
                                 request.remote_addr)
    ua = request.headers.get('User-Agent')
    bot = visitors.is_bot(ua)
    _visit_queue.put({
        'kind': kind,
        'path': path,
        'ip': ip_addr,
        'ua': ua,
        'visitor_id': visitors.visitor_id(ip_addr, ua),
        'is_bot': bot,
        # The referrer on a callback POST is just our own page url; only the
        # document load carries where the visitor actually came from.
        'referrer': request.referrer if kind == 'landing' else None,
    })
    with _visit_worker_lock:
        if not _visit_worker_started:
            threading.Thread(target=_visit_worker, daemon=True,
                             name='visit-worker').start()
            _visit_worker_started = True
    # No logging here. The line moved to `_process_visit`, which is the first place
    # that knows whether the address is a datacenter one; see the note there.


@app.server.before_request
def record_visit():
    # Ignore internal Dash endpoints and per-page-load asset fetches. The component
    # suites matter beyond log noise: a single page load requests over a dozen of them,
    # and logging each one costs a visit-DB row and an ip-api.com lookup against that
    # service's 45/min limit, starving the lookups for the page views the log is for.
    ignored_paths = [
        '/_dash-layout',
        '/_dash-dependencies',
        '/_dash-update-component',
        '/_dash-component-suites/',
        '/assets/',
        '/favicon.ico',
        '/_favicon.ico'
    ]

    if not any(request.path.startswith(path) for path in ignored_paths):
        _enqueue_visit('landing', request.path)


navbar = dbc.Navbar(
    (
        dbc.NavbarBrand(
            html.Div([
                html.P("COT Analyzer",
                    style={
                        'color': vc.BRIGHTER_TEXT_COLOR,
                        'margin': 0,
                        'fontSize': '1.5rem'
                    }
                ),
                html.P(id='navbar_timestamp_text',
                    style={
                        'fontSize': '0.75rem',
                        'margin': 0,
                        'color': vc.TEXT_COLOR
                    }
                ),
                dcc.Interval(
                    id='navbar_update_interval',
                    interval=5 * 60 * 1000,  # 5 minutes in msec
                    n_intervals=0
                ),
            ]),
            href="/",
            className="ms-3 text-decoration-none"
        ),

        dbc.NavbarToggler(id="navbar-toggler", n_clicks=0),

        dbc.Collapse(
            dbc.Nav(
                [
                    dbc.NavItem(dbc.NavLink("Home", href="/", active="exact")),
                    dbc.NavItem(dbc.NavLink("Heatmap", href="/heatmap", active="exact")),
                    dbc.NavItem(dbc.NavLink("Strip", href="/strip", active="exact")),
                    dbc.NavItem(dbc.NavLink("Crowd", href="/crowd", active="exact")),
                    dbc.NavItem(dbc.NavLink("Exposure", href="/exposure", active="exact")),
                    dbc.DropdownMenu(
                        children=[
                            dbc.DropdownMenuItem("Asset Graphs", href="/graphs"),
                            dbc.DropdownMenuItem("Asset Analysis", href="/analysis"),
                            dbc.DropdownMenuItem("OI Alignment", href="/oi_alignment"),
                            dbc.DropdownMenuItem("Divergence", href="/divergence"),
                            dbc.DropdownMenuItem("Aggregation", href="/aggregation"),
                            dbc.DropdownMenuItem("Disagg / TFF", href="/categories"),
                            dbc.DropdownMenuItem("Table", href="/positioning"),
                        ],
                        nav=True,
                        in_navbar=True,
                        label="Analytics"
                    ),

                    dbc.DropdownMenu(
                        children=[
                            dbc.DropdownMenuItem("Options", href="/options"),
                            dbc.DropdownMenuItem("Admin", href="/admin"),
                            dbc.DropdownMenuItem("Raw Data Viewer", href="/raw_data"),
                            dbc.DropdownMenuItem("About", href="/about"),
                        ],
                        nav=True,
                        in_navbar=True,
                        label="System",
                        className="me-2"
                    ),
                ],
                className="ms-auto",
                navbar=True,
            ),
            id="navbar-collapse",
            is_open=False,
            navbar=True,
        ),
    ),
    dark=True,
    className="w-100 navbar-custom", # Ensures the navbar spans the full width of the screen
    expand="md",
)

app.layout = html.Div(
    id="theme-container",
    className="theme-solarized-dark",
    children=[
        dbc.Container(
            [
                dcc.Store(id='session_admin_auth', storage_type='session'),
                dcc.Store(id='session_palette_theme_asset_store', storage_type='session'),
                dcc.Store(id='global_lookback_store', storage_type='session', data='Custom'),
                dcc.Store(id='global_model_store', storage_type='session', data=models.DEFAULT_MODEL.key),
                # The as-of week, shared by every page with a Target Date the way
                # model and lookback already are: park the Heatmap on an old week
                # and the Strip, Crowd, Divergence and Positioning show the same
                # week when you arrive. None means "tracking the newest week",
                # and only an explicitly chosen OLDER week is ever stored -- the
                # distinction is what lets a Friday release move every tracking
                # page forward while a parked one stays parked (the same split
                # next_date_selection used to make per control, now made once).
                # Session, not local, for Exposure's reason: which week you are
                # reading is a fact about this visit, and a page reopened weeks
                # later still describing a stale week would be lying by default.
                dcc.Store(id='global_week_store', storage_type='session'),
                dcc.Store(id='theme_store', storage_type='local', data='solarized_dark'),
                # The COT week the server currently serves, republished by the navbar
                # poller below whenever it changes. Pages whose contents are pinned to
                # a report date subscribe to this so an ALREADY-OPEN tab converges
                # instead of sitting on the previous week under a badge that has moved
                # on. Deliberately NOT persisted: it describes the server's state right
                # now, and a value restored from sessionStorage would be a claim about
                # a previous one.
                dcc.Store(id='cot_release_store'),
                # Sink for the pageview logger below; never read.
                dcc.Store(id='pageview_logged'),
                dcc.Location(id='url', refresh=False),
                navbar,
                dash.page_container
            ],
            fluid=True
        )
    ]
)

@app.callback(
    Output('pageview_logged', 'data'),
    Input('url', 'pathname'),
)
def record_pageview(pathname):
    """Log every page the client-side router shows, the initial one included.

    This is the half of tracking the HTTP layer cannot see: Dash is a single-page
    app, so after the first document load, moving Home -> Heatmap -> Crowd is a
    pushState plus a callback POST, and `record_visit` above never fires again. Until
    this callback existed the visit log recorded which page people ARRIVED on and
    nothing after, and any per-page popularity read off it was wrong.

    It deliberately fires on the initial load too (no prevent_initial_call), so the
    'pageview' rows are the complete view count on their own; 'landing' rows carry
    the referrer and are never summed with them. Runs in a request context, which is
    what lets `_enqueue_visit` read the caller's IP and user agent off the POST.
    """
    if pathname:
        _enqueue_visit('pageview', pathname)
    return no_update


# Callback to toggle the collapse on small screens
@app.callback(
    Output("navbar-collapse", "is_open"),
    [Input("navbar-toggler", "n_clicks")],
    [State("navbar-collapse", "is_open")],
)
def toggle_navbar_collapse(n, is_open):
    if n:
        return not is_open
    return is_open

@app.callback(
    Output("theme-container", "className"),
    Input("theme_store", "data")
)
def update_theme(theme_value):
    if theme_value == "modern_web":
        return "theme-modern-web"
    return "theme-solarized-dark"

@app.callback(
    Output("navbar_timestamp_text", "children"),
    Output("cot_release_store", "data"),
    Input("navbar_update_interval", "n_intervals"),
    State("navbar_timestamp_text", "children"),
    State("cot_release_store", "data"),
)
def update_graphs_date(n, current_text, current_release):
    """Refresh the index if the store advanced, then show the CFTC release date.

    This is the app's data poller as well as its badge. The two jobs belong on one
    callback because they read the same signal: cotdata rewrites status.json once,
    atomically, at the end of a producer run, and both the badge below and
    refresh_if_stale key on its cot_legacy newest_data.

    They used to disagree, and visibly. The badge has always read status.json
    uncached, so it moved the moment a new week landed, while the only staleness
    check in the indexer sat inside get_symbols_data's lru_cache and therefore never
    ran on a warm board. On 2026-08-07 that gap was 4h40m of a navbar reading
    2026-08-04 above pages reading 2026-07-28.

    dcc.Interval is client-side, so this fires on every page load and then every 5
    minutes for as long as a tab stays open. With no tab open nothing polls, and the
    first load after a release pays the ~2 minute rebuild.

    It also republishes the week into cot_release_store, which is what lets a page
    already on screen notice. The badge alone was the narrower half of the same bug it
    was built to fix: it moved the moment a week landed while the page under it kept
    rendering the previous one, and on a tab nobody reloaded, that disagreement was
    permanent rather than a two minute window.

    The store is written only when the week CHANGES, so the five-minute tick does not
    wake every subscriber for nothing. A read that fails leaves both outputs alone:
    latest_update_timestamp returns None mid-sync (replication is not atomic), and
    replacing a real date with "unavailable" on a tab that was showing one would make
    the badge flicker on exactly the day it matters most.
    """
    get_indexer().refresh_if_stale()

    release = cotDatabase.latest_update_timestamp()
    if release is None:
        return (no_update if current_text else "CFTC Data Release: unavailable",
                no_update)

    return (f"CFTC Data Release: {release}",
            no_update if release == current_release else release)



