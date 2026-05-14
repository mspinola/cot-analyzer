from db import cotDatabase
import constants as const
import utils

import dash
import dash_bootstrap_components as dbc
import os
import pandas as pd
import plotly.express as px
from collections import deque
from dash import html, dcc, callback, clientside_callback, ClientsideFunction, Input, Output, State


dash.register_page(__name__, path='/admin')

def login_layout():
    return dbc.Container([
        dbc.Row([
            dbc.Col([
                html.H3("Admin Access Required", style={'color': const.BRIGHTER_TEXT_COLOR}),
                dbc.Input(id='admin-pw-input', type='password', placeholder='Enter Password', className="mb-3"),
                dbc.Button("Unlock Dashboard", id='admin-login-btn', color="primary"),
                html.Div(id='admin-login-alert', className="mt-2")
            ], width=4)
        ], justify="center", style={'marginTop': '20%'})
    ])

def admin_content():
    return dbc.Container([
        html.H2("System Telemetry", className="mt-4 mb-4", style={'color': const.BRIGHTER_TEXT_COLOR}),

        # Graphs Section
        dbc.Row([
            dbc.Col(dcc.Graph(id='visit-time-chart'), width=6),
            dbc.Col(dcc.Graph(id='visitor-geo-chart'), width=6),
        ], className="mb-4"),

        html.Hr(style=const.hr_style),
        html.H4("Server Logs", style={'color': const.TEXT_COLOR}),

        # The Scrolling Log Viewer
        html.Div([
            html.Pre(
                id='server-log-viewer',
                style={
                    'height': '300px',
                    'overflowY': 'scroll',
                    'backgroundColor': '#000',
                    'color': '#00FF00', # Classic terminal green
                    'padding': '10px',
                    'fontSize': '0.75rem',
                    'borderRadius': '5px',
                    'border': '1px solid #333'
                }
            )
        ], className="mb-4"),

        # Logs Table Section
        html.Hr(style=const.hr_style),
        html.H4("Recent Access Logs", style={'color': const.TEXT_COLOR}),
        html.Div(id='admin-log-table'),
    ], fluid=True)

def layout():
    return html.Div([
        # The trigger must be static so Dash can always find it
        dcc.Interval(id='admin-refresh', interval=30*1000),

        # Div to hold the Login form
        html.Div(id='admin-login-view', children=login_layout()),

        # Div to hold the actual Dashboard (hidden by default)
        html.Div(
            id='admin-dashboard-view',
            children=admin_content(),
            style={'display': 'none'}
        )
    ])

@callback(
    [Output('admin-login-view', 'style'),
     Output('admin-dashboard-view', 'style')],
    Input('session_admin_auth', 'data')
)
def toggle_admin_visibility(auth_data):
    """Switches visibility between login and dashboard without removing IDs."""
    if auth_data == "AUTHORIZED":
        return {'display': 'none'}, {'display': 'block'}
    return {'display': 'block'}, {'display': 'none'}

@callback(
    [Output('session_admin_auth', 'data'),
     Output('admin-login-alert', 'children')],
    Input('admin-login-btn', 'n_clicks'),
    State('admin-pw-input', 'value'),
    prevent_initial_call=True
)
def validate_login(n_clicks, password):
    # DO NOT hardcode this in a production app.
    # Use an environment variable: os.getenv('ADMIN_PASSWORD')
    SECRET = os.getenv('COT_ADMIN_PASSWORD', 'default_dev_pw')
    if password == SECRET:
        return "AUTHORIZED", ""
    return dash.no_update, dbc.Alert("Incorrect Password", color="danger")

@callback(
    [Output('visit-time-chart', 'figure'),
     Output('visitor-geo-chart', 'figure'),
     Output('admin-log-table', 'children'),
     Output('server-log-viewer', 'children')],
    Input('admin-refresh', 'n_intervals'),
    State('session_admin_auth', 'data')
)
def update_admin_stats(n, auth_data):
    if auth_data != "AUTHORIZED":
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    df = cotDatabase.get_visitor_stats()
    if df.empty:
        return px.scatter(title="No Data"), px.scatter(title="No Data"), html.P("No logs found."), html.P("No logs found.")

    # Fetch raw log content
    log_content = get_log_tail("logs/" + utils.main_cot_logger_file, n=100)

    # Time Chart
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    time_fig = px.histogram(
        df, x="timestamp",
        title="Access Frequency",
        template="plotly_dark",
        color_discrete_sequence=[const.BLUE_BACKGROUND]
    )
    time_fig.update_layout(
        paper_bgcolor=const.BACKGROUND_COLOR,
        plot_bgcolor=const.BACKGROUND_COLOR
    )

    # Geo Chart
    geo_fig = px.bar(
        df['country'].value_counts().reset_index(),
        x='count', y='country', orientation='h',
        title="Visitor Geography",
        template="plotly_dark",
        color_discrete_sequence=[const.BLUE_BACKGROUND]
    )
    geo_fig.update_layout(
        paper_bgcolor=const.BACKGROUND_COLOR,
        plot_bgcolor=const.BACKGROUND_COLOR
    )

    # Table: Raw logs (using your established dense-table style)
    table = dbc.Table.from_dataframe(
        df[['timestamp', 'ip_address', 'city', 'country', 'path']].head(15),
        striped=True, bordered=True, hover=True,
        className="dense-table",
        style={'fontSize': '0.85rem'}
    )

    return time_fig, geo_fig, table, log_content

# Helper to efficiently read the end of a file
def get_log_tail(filename, n=100):
    try:
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                return "".join(deque(f, n))
        return f"Log file not found at: {filename}"
    except Exception as e:
        return f"Error reading log: {str(e)}"

clientside_callback(
    ClientsideFunction(namespace='clientside', function_name='scroll_to_bottom'),
    Output('server-log-viewer', 'id'), # Target ID (used as a dummy here)
    Input('server-log-viewer', 'children') # Trigger when text updates
)
