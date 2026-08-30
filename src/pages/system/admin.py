import os
import subprocess
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

import cotmetrics
import cotmetrics.utils as utils
import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
from cotmetrics.database import cotDatabase
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

        # Traffic filter + headline. Humans is the default because bots are most of
        # raw traffic and the question this page answers is "who is using the app";
        # the Bots view exists so a scraper burst is diagnosable rather than merely
        # excluded. Rows logged before the is_bot column existed count as human.
        dbc.Row([
            dbc.Col(dbc.RadioItems(
                id='admin-traffic-filter',
                options=[
                    {'label': 'Humans', 'value': 'humans'},
                    {'label': 'Bots', 'value': 'bots'},
                    {'label': 'All', 'value': 'all'},
                ],
                value='humans',
                inline=True,
            ), width="auto"),
            dbc.Col(html.Div(
                id='admin-visit-summary',
                style={'color': vc.TEXT_COLOR, 'fontSize': '0.9rem'}
            ), width="auto"),
        ], justify="between", align="center", className="mb-2"),

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
    SECRET = os.getenv('COT_ADMIN_PASSWORD')
    if not SECRET:
        # Name the variable and its home. The old text was just "Admin login is not
        # configured", which is true and useless: it does not distinguish a missing
        # setting from a wrong password, and it does not say where the setting goes.
        # The trap it hides is that COT_ADMIN_PASSWORD has lived only in ~/.zshrc and
        # ~/.bash_profile, so the app inherits it when launched from an interactive
        # shell and silently does not otherwise (launchd, an editor, a preview
        # harness). run-local.sh sources .env with `set -a` and the deployed unit
        # loads the same file via EnvironmentFile, so .env is the one home that works
        # in every launch context. server-side/README.md already documents it there.
        return dash.no_update, dbc.Alert(
            "Admin login is not configured: COT_ADMIN_PASSWORD is not set in this "
            "process. Add it to cot-analyzer/.env (gitignored) and restart the app.",
            color="danger")
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

    try:
        # Run cotdata-update to refresh the store
        subprocess.run(
            ['cotdata-update', '--cot-all'],
            capture_output=True, text=True, check=True
        )
    except Exception as e:
        utils.cot_logger.error(f"Manual data poll failed: {e}")
        return f"Manual poll failed: {e}"

    # Run predictions in case they were missing or not generated
    try:
        from pardo.deploy.predict import predict_all
        predict_all(force=False)
    except Exception as e:
        utils.cot_logger.error(f"Failed to run predictions after manual poll: {e}")

    current_time = datetime.now().strftime("%H:%M:%S")
    return f"Manual poll executed at {current_time}. Check server logs for results."


def _weekly_email_script():
    """Locate cotmetrics' generate-weekly-report-email.py, or None if it is not there.

    The report generator lives in cotmetrics, not here: it imports
    cotmetrics.reports.get_matrix_data/generate_matrix_html, and it moved there with
    the rest of the metrics layer when that repo was split out. What did not move was
    this page, which went on invoking `bash scripts/generate-weekly-report-email.sh`
    relative to cot-analyzer's own working directory. That path has pointed at nothing
    ever since, and the button has been failing with a bare "No such file or directory"
    on a path no one would think to look for in a sibling repo.

    Resolved from the installed package rather than a relative path so it follows the
    editable install instead of the caller's cwd. scripts/ sits beside src/, so the
    repo root is two levels up from the package directory. A wheel install has no
    scripts/ at all, hence the existence check and the None.

    The .sh wrapper is deliberately skipped. Despite the comment that used to sit here
    claiming it "contains the email credentials", it holds none: it is one line,
    `.venv/bin/python scripts/generate-weekly-report-email.py "$@"`, whose only effect
    is to require a cotmetrics-local venv that does not exist on this machine and to
    re-break the cwd assumption. Credentials come from the environment, which a
    subprocess inherits. Running the .py directly with our own interpreter drops both
    problems, and our interpreter is the right one: cotmetrics is installed here.
    """
    root = Path(cotmetrics.__file__).resolve().parents[2]
    script = root / "scripts" / "generate-weekly-report-email.py"
    return script if script.is_file() else None


@callback(
    Output("admin-send-email-output", "children"),
    Input("admin-send-email-btn", "n_clicks"),
    prevent_initial_call=True
)
def trigger_send_email(n_clicks):
    if not n_clicks:
        return ""

    current_time = datetime.now().strftime("%H:%M:%S")
    script = _weekly_email_script()
    if script is None:
        msg = ("Cannot find generate-weekly-report-email.py in the cotmetrics checkout. "
               "It ships in that repo's scripts/, which only exists in a source checkout, "
               "so this needs cotmetrics installed editable from a sibling clone.")
        utils.cot_logger.error(msg)
        return f"{msg} ({current_time})"

    try:
        utils.cot_logger.info(f"Admin initiated manual email send -> {script}")
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        utils.cot_logger.error("Email script timed out after 120s (SMTP connect hanging?).")
        return f"Email script timed out at {current_time}. Check logs."
    except Exception as e:
        utils.cot_logger.error(f"Email script failed to execute: {e}")
        return f"Script execution failed: {e}"

    if result.returncode == 0:
        return f"Email sent successfully at {current_time}."

    utils.cot_logger.error(f"Email script failed (exit {result.returncode}): "
                           f"{result.stderr or result.stdout}")
    return f"Error sending email at {current_time}: {_failure_line(result)}"


def _failure_line(result):
    """The one line of a failed run worth putting on screen.

    "Check logs" was the old answer and it is a bad one: the most likely failure here
    is a missing EMAIL_USER / RECEIVER_EMAIL_USER / EMAIL_PASSWORD, which the operator
    standing at the button can fix in seconds if only they are told. The script names
    the missing variables, so show that instead of hiding it in a file.

    Prefer the first line mentioning an error, then fall back to the last line. Both
    routes land on the diagnosis today: the script reports a bad configuration as a
    single "[!] Not configured: missing EMAIL_USER, ..." line, which the fallback
    returns intact. The first-line rule is what catches a traceback, whose final
    "SomeError: ..." line is the only one worth showing.
    """
    text = (result.stderr or result.stdout or "").strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return f"exit {result.returncode}"
    for line in lines:
        if "error" in line.lower():
            return line
    return lines[-1]


def split_visit_rows(df, traffic):
    """(page views, filtered events) for one setting of the traffic filter.

    Pure so the reading of the columns is testable without a Dash app. Two rules the
    charts rely on:

    - `is_bot` outside {1} counts as human, so rows logged before the column existed
      (NULL) land in the default view rather than vanishing from every one.
    - Page views are the 'pageview' rows PLUS the NULL-kind legacy rows: before the
      kind column, one row per document GET was the only record of a view, and those
      remain the whole history for old weeks. 'landing' rows are excluded because
      each one coexists with a pageview row for the same load, and summing the two
      kinds would double-count every entry page.
    """
    bots = pd.to_numeric(df['is_bot'], errors='coerce').fillna(0).astype(int)
    if traffic == 'humans':
        df = df[bots != 1]
    elif traffic == 'bots':
        df = df[bots == 1]
    views = df[df['kind'].isna() | (df['kind'] == 'pageview')]
    return views, df


@callback(
    [Output('visit-time-chart', 'figure'),
     Output('visitor-geo-chart', 'figure'),
     Output('admin-visit-summary', 'children'),
     Output('admin-log-table', 'children'),
     Output('server-log-viewer', 'children')],
    Input('admin-refresh', 'n_intervals'),
    Input('session_admin_auth', 'data'),
    Input('admin-traffic-filter', 'value'),
    prevent_initial_call=True
)
def update_admin_stats(n, auth_data, traffic):
    if auth_data != "AUTHORIZED":
        raise PreventUpdate

    df = cotDatabase.get_visitor_stats()
    if df.empty:
        return (px.scatter(title="No Data"), px.scatter(title="No Data"), "",
                html.P("No logs found."), html.P("No logs found."))

    # Fetch raw log content from the same dir the logger writes to (utils.LOG_DIR,
    # i.e. COTMETRICS_LOG_DIR). A hardcoded relative "logs/" only matched the
    # pre-split layout and read nothing once the log dir became configurable.
    log_content = get_log_tail(os.path.join(utils.LOG_DIR, utils.main_cot_logger_file), n=100)

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    views, events = split_visit_rows(df, traffic)

    # The window is the last 500 logged events, not all history, which is why the
    # summary says so instead of implying totals.
    uniques = views['visitor_id'].dropna().nunique()
    summary = (f"{len(views)} page views | {uniques} unique visitors "
               f"(daily-rotating ids) | window: last {len(df)} events")

    # Time Chart
    time_fig = px.histogram(
        views, x="timestamp",
        title="Page Views",
        template="plotly_dark",
        color_discrete_sequence=[vc.BLUE_BACKGROUND]
    )
    time_fig.update_layout(
        paper_bgcolor=vc.BACKGROUND_COLOR,
        plot_bgcolor=vc.BACKGROUND_COLOR
    )

    # Geo Chart
    geo_fig = px.bar(
        views['country'].value_counts().reset_index(),
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
    table_cols = ['timestamp', 'visitor_id', 'kind', 'ip_address', 'city', 'country', 'path']
    # responsive: seven nowrap columns (dense-table forces nowrap cells) run well
    # past a phone viewport, and the body-level overflow-x: hidden clipped the
    # right edge silently. The wrapper div this adds scrolls instead.
    table = dbc.Table.from_dataframe(
        events[table_cols].head(15).fillna(''),
        striped=True, bordered=True, hover=True, responsive=True,
        className="dense-table",
        style={'fontSize': '0.85rem'}
    )

    return time_fig, geo_fig, summary, table, log_content

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
