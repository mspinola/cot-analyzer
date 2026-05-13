import constants
from db import cotDatabase
import utils

import dash
import dash_bootstrap_components as dbc
from dash import Dash, State, html, dcc, callback, Input, Output
from flask import request
import logging
import requests

app = Dash(__name__, use_pages=True, external_stylesheets=[dbc.themes.DARKLY])
server = app.server

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
        utils.visitor_logger.info(msg)


navbar = dbc.Navbar(
    (
        dbc.NavbarBrand(
            html.Div([
                html.P("COT Analyzer",
                    style={
                        'color': constants.BRIGHTER_TEXT_COLOR,
                        'margin': 0,
                        'fontSize': '1.5rem'
                    }
                ),
                html.P(id='navbar_timestamp_text',
                    style={
                        'fontSize': '0.75rem',
                        'margin': 0,
                        'color': constants.TEXT_COLOR
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
                    dbc.NavItem(dbc.NavLink("Graphs", href="/graphs", active="partial", style={'fontSize': '0.9rem'})),
                    dbc.NavItem(dbc.NavLink("Table", href="/positioning", active="partial", style={'fontSize': '0.9rem'})),
                    dbc.NavItem(dbc.NavLink("Heatmap", href="/heatmap", active="partial", style={'fontSize': '0.9rem'})),
                    dbc.NavItem(dbc.NavLink("Analysis", href="/analysis", active="partial", style={'fontSize': '0.9rem'})),
                    dbc.NavItem(dbc.NavLink("Options", href="/options", active="partial", style={'fontSize': '0.9rem'})),
                    dbc.NavItem(dbc.NavLink("About", href="/about", active="partial", style={'fontSize': '0.9rem'}, className="me-2")),
                ],
                className="ms-auto",
                navbar=True,
            ),
            id="navbar-collapse",
            is_open=False,
            navbar=True,
        ),
    ),
    color=constants.BLUE_BACKGROUND,
    dark=True,
    className="w-100", # Ensures the navbar spans the full width of the screen
    expand="md",
)

app.layout = dbc.Container(
    [
        dcc.Store(id='session_admin_auth', storage_type='session'),
        dcc.Store(id='session_palette_theme_asset_store', storage_type='session'),
        dcc.Store(id='session_setup_highlight_asset_store', storage_type='session'),
        dcc.Store(id='global_lookback_store', storage_type='session', data='Custom'),
        dcc.Location(id='url', refresh=True),
        navbar,
        dash.page_container
    ],
    fluid=True
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

@app.callback(Output('url', 'pathname'),
              [Input('url', 'pathname')])
def redirect_root(pathname):
    if pathname == '/':
        return '/positioning'
    elif pathname == '/admin':
        return '/admin'
    return dash.no_update

@app.callback(
    Output("navbar_timestamp_text", "children"),
    Input("navbar_update_interval", "n_intervals")
)
def update_graphs_date(n):
    """Callback to update the db last update string in the NavBar."""
    return f"CFTC Data Release: {cotDatabase.latest_update_timestamp()}"
