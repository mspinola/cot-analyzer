import os

import cotmetrics.models as models
import cotmetrics.utils as utils
import dash
import dash_bootstrap_components as dbc
import requests
from cotmetrics.database import cotDatabase
from dash import Dash, Input, Output, State, dcc, html
from flask import request
from flask_compress import Compress

import viz_constants as vc

utils.launch_logger.warning("Launch app_cot")

if not os.path.exists('data/raw_cot_data.parquet'):
    utils.cot_logger.warning("raw_cot_data.parquet not found! Forcing ETL pipeline to generate it before launching server...")
    import importlib
    etl_module = importlib.import_module("cotmetrics.pipelines.01_etl_downloader")
    etl_module.run_etl_pipeline()

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



@app.server.before_request
def record_visit():
    # Define internal Dash and asset paths to ignore
    ignored_paths = [
        '/_dash-layout',
        '/_dash-dependencies',
        '/_dash-update-component',
        '/assets/',
        '/favicon.ico'
    ]

    # Ignore internal Dash updates and assets to keep logs clean
    if not any(request.path.startswith(path) for path in ignored_paths):
        ip_addr = request.headers.get('X-Forwarded-For', request.remote_addr)

        # Default values
        city, country = "Internal", "Local"

        # Skip lookup for localhost/internal IPs
        if ip_addr not in ['127.0.0.1', 'localhost']:
            try:
                # Use ip-api.com (Limit: 45 requests per minute)
                response = requests.get(f"http://ip-api.com/json/{ip_addr}", timeout=0.5).json()
                if response.get('status') == 'success':
                    city = response.get('city')
                    country = response.get('country')
            except Exception:
                city, country = "Lookup", "Error"

        cotDatabase.log_visit(
            ip_addr,
            request.path,
            request.headers.get('User-Agent'),
            city,
            country
        )

        msg = f"IP: {ip_addr} | Path: {request.path}"
        utils.cot_logger.info(msg)


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
                    dbc.DropdownMenu(
                        children=[
                            dbc.DropdownMenuItem("Asset Graphs", href="/graphs"),
                            dbc.DropdownMenuItem("Asset Analysis", href="/analysis"),
                            dbc.DropdownMenuItem("OI Alignment", href="/oi_alignment"),
                            dbc.DropdownMenuItem("Aggregation", href="/aggregation"),
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
                dcc.Store(id='theme_store', storage_type='local', data='solarized_dark'),
                dcc.Location(id='url', refresh=False),
                navbar,
                dash.page_container
            ],
            fluid=True
        )
    ]
)

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
    Input("navbar_update_interval", "n_intervals")
)
def update_graphs_date(n):
    """Callback to update the db last update string in the NavBar."""
    return f"CFTC Data Release: {cotDatabase.latest_update_timestamp()}"



