import constants

import dash
from db import cotDatabase

import dash_bootstrap_components as dbc
from dash import Dash, html, dcc, callback, Input, Output


app = Dash(__name__, use_pages=True, external_stylesheets=[dbc.themes.DARKLY])
server = app.server

navbar = dbc.NavbarSimple(
    children=[
        dbc.NavItem(dbc.NavLink("Graphs", href="/graphs", active="partial")),
        dbc.NavItem(dbc.NavLink("Table", href="/positioning", active="partial")),
        dbc.NavItem(dbc.NavLink("Heatmap", href="/heatmap", active="partial")),
        dbc.NavItem(dbc.NavLink("Analysis", href="/analysis", active="partial")),
        dbc.NavItem(dbc.NavLink("Options", href="/options", active="partial", className="me-1")),
    ],
        brand=[
            html.P("COT Analyzer",
                style={
                    'color': constants.BRIGHTER_TEXT_COLOR,
                    'margin': 0,
                    'fontSize': '1.5rem'
                }
            ),
            html.P(id='navbar_timestamp_text',
                style={
                    'fontSize': '0.95rem',
                    'margin': 0,
                    'color': constants.TEXT_COLOR
                }
            ),
            dcc.Interval(
                id='navbar_update_interval',
                interval=5 * 60 * 1000,  # 5 minutes in msec
                n_intervals=0
            ),
        ],
        color=constants.BLUE_BACKGROUND,
        brand_href="/graphs",
        dark=True
)

app.layout = dbc.Container(
    [
        dcc.Store(id='session_palette_theme_asset_store', storage_type='session'),
        dcc.Store(id='session_setup_highlight_asset_store', storage_type='session'),
        dcc.Store(id='global_lookback_store', storage_type='session', data='custom'),
        navbar,
        dash.page_container
    ],
    fluid=True
)

@app.callback(
    Output("navbar_timestamp_text", "children"),
    Input("navbar_update_interval", "n_intervals")
)
def update_graphs_date(n):
    """Callback to update the db last update string in the NavBar."""
    return f"CFTC Data Release: {cotDatabase.latest_update_timestamp()}"
