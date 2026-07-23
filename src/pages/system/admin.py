import os
import subprocess
from collections import deque
from datetime import datetime

import cotmetrics.utils as utils
import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
from cotmetrics.database import cotDatabase
from cotmetrics.pipelines.etl_scheduler import CotJobScheduler
from dash import ClientsideFunction, Input, Output, State, callback, clientside_callback, dcc, html
from dash.exceptions import PreventUpdate

import viz_constants as vc

dash.register_page(__name__, path='/admin')

def login_layout():
    return dbc.Container([
        dbc.Row([
            dbc.Col([
                html.H3("Admin Access Required", style={'color': vc.BRIGHTER_TEXT_COLOR}),
                dbc.Input(id='admin-pw-input', type='password', placeholder='Enter Password', className="mb-3"),
                dbc.Button("Unlock Dashboard", id='admin-login-btn', color="primary"),
                html.Div(id='admin-login-alert', className="mt-2")
            ], width=4)
        ], justify="center", style={'marginTop': '20%'})
    ])

def admin_content():
    return dbc.Container([
        dbc.Row([
            dbc.Col(html.H2("System Telemetry", className="mt-4 mb-4", style={'color': vc.BRIGHTER_TEXT_COLOR})),
            dbc.Col([
                html.Div([
                    dbc.Button("Restart Application", id='admin-restart-btn', color="danger", n_clicks=0),
                    html.Div(id='admin-restart-alert', className="mt-2")
                ], className="mt-4 mb-4 text-end"),

                html.Div([
                    dbc.Button(
                        "🔄 Force Manual Data Poll",
                        id="admin-manual-poll-btn",
                        color="warning",
                        outline=True,
                        className="mt-4 mb-2"
                    ),
                    dbc.Button(
                        "📧 Send Email Report",
                        id="admin-send-email-btn",
                        color="info",
                        outline=True,
                        className="mt-4 mb-2 ms-2"
                    ),

                    # This will display a timestamp when the button is clicked
                    html.Div(id="admin-manual-poll-output", style={'color': '#839496', 'fontSize': '0.9rem'}),
                    html.Div(id="admin-send-email-output", style={'color': '#839496', 'fontSize': '0.9rem'})
                ])
            ], width="auto")
        ], justify="between", align="start"),
        html.Hr(style=vc.hr_style),

        # Graphs Section
        dbc.Row([
            dbc.Col(dcc.Graph(id='visit-time-chart'), width=6),
            dbc.Col(dcc.Graph(id='visitor-geo-chart'), width=6),
        ], className="mb-4"),

        html.Hr(style=vc.hr_style),
        html.H4("Server Logs", style={'color': vc.TEXT_COLOR}),

        # The Scrolling Log Viewer
        html.Div([
            html.Pre(
                id='server-log-viewer',
                style={
                    'height': '300px',
                    'overflowY': 'scroll',
                    'backgroundColor': vc.SOLARIZED_DARK_BASE03,
                    'color': vc.SOLARIZED_DARK_BASE0,
                    'padding': '10px',
                    'fontSize': '0.75rem',
                    'borderRadius': '5px',
                    'border': '1px solid #333'
                }
            )
        ], className="mb-4"),

        # Logs Table Section
        html.Hr(style=vc.hr_style),
        html.H4("Recent Access Logs", style={'color': vc.TEXT_COLOR}),
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
    # Use an environment variable: os.getenv('COT_ADMIN_PASSWORD')
    SECRET = os.getenv('COT_ADMIN_PASSWORD')
    if not SECRET:
        return dash.no_update, dbc.Alert("Admin login is not configured", color="danger")
    if password and password == SECRET:
        return "AUTHORIZED", ""
    return dash.no_update, dbc.Alert("Incorrect Password", color="danger")


@callback(
    Output("admin-manual-poll-output", "children"),
    Input("admin-manual-poll-btn", "n_clicks"),
    prevent_initial_call=True
)
def trigger_manual_poll(n_clicks):
    if not n_clicks:
        return ""

    # Instantiate a temporary downloader just for this check
    # You can pass enable_email=False if you don't want to be spammed during manual tests
    downloader = CotJobScheduler(enable_email=False)

    # Run a single attempt
    downloader.run_polling_window(attempts=1, interval_minutes=1)

    # Run predictions in case they were missing or not generated
    try:
        from pardo.deploy.predict import predict_all
        predict_all(force=False)
    except Exception as e:
        utils.cot_logger.error(f"Failed to run predictions after manual poll: {e}")

    current_time = datetime.now().strftime("%H:%M:%S")
    return f"Manual poll executed at {current_time}. Check server logs for results."


@callback(
    Output("admin-send-email-output", "children"),
    Input("admin-send-email-btn", "n_clicks"),
    prevent_initial_call=True
)
def trigger_send_email(n_clicks):
    if not n_clicks:
        return ""

    try:
        utils.cot_logger.info("Admin initiated manual email send.")
        # Run the bash script that contains the email credentials and triggers the python script
        result = subprocess.run(
            ['bash', 'scripts/generate-weekly-report-email.sh'],
            capture_output=True, text=True
        )
        current_time = datetime.now().strftime("%H:%M:%S")
        if result.returncode == 0:
            return f"Email sent successfully at {current_time}."
        else:
            utils.cot_logger.error(f"Email script failed: {result.stderr}")
            return f"Error sending email at {current_time}. Check logs."
    except Exception as e:
        utils.cot_logger.error(f"Email script failed to execute: {e}")
        return f"Script execution failed: {e}"


@callback(
    [Output('visit-time-chart', 'figure'),
     Output('visitor-geo-chart', 'figure'),
     Output('admin-log-table', 'children'),
     Output('server-log-viewer', 'children')],
    Input('admin-refresh', 'n_intervals'),
    Input('session_admin_auth', 'data'),
    prevent_initial_call=True
)
def update_admin_stats(n, auth_data):
    if auth_data != "AUTHORIZED":
        raise PreventUpdate

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
        color_discrete_sequence=[vc.BLUE_BACKGROUND]
    )
    time_fig.update_layout(
        paper_bgcolor=vc.BACKGROUND_COLOR,
        plot_bgcolor=vc.BACKGROUND_COLOR
    )

    # Geo Chart
    geo_fig = px.bar(
        df['country'].value_counts().reset_index(),
        x='count', y='country', orientation='h',
        title="Visitor Geography",
        template="plotly_dark",
        color_discrete_sequence=[vc.BLUE_BACKGROUND]
    )
    geo_fig.update_layout(
        paper_bgcolor=vc.BACKGROUND_COLOR,
        plot_bgcolor=vc.BACKGROUND_COLOR
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


@callback(
    Output('admin-restart-alert', 'children'),
    Input('admin-restart-btn', 'n_clicks'),
    prevent_initial_call=True
)
def trigger_application_restart(n_clicks):
    if n_clicks > 0:
        utils.cot_logger.warning("Admin initiated manual application restart from dashboard.")

        try:
            # Because launch-cot-analyzer.sh runs from the repo root,
            # the relative path to the restart script is just server-side/
            subprocess.Popen(['bash', 'server-side/restart.sh'])

            return dbc.Alert(
                "Restart command sent. The application will reload momentarily.",
                color="warning",
                style={"fontSize": "0.85rem", "padding": "8px"}
            )
        except Exception as e:
            utils.cot_logger.error(f"Restart script failed: {e}")
            return dbc.Alert(
                f"Failed to execute restart: {e}",
                color="danger",
                style={"fontSize": "0.85rem", "padding": "8px"}
            )
