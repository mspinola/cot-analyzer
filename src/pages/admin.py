from db import cotDatabase
import constants as const

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
from dash import html, dcc, callback, Input, Output

dash.register_page(__name__, path='/admin')

layout = dbc.Container([
    html.H2("System Telemetry", className="mt-4 mb-4", style={'color': const.BRIGHTER_TEXT_COLOR}),

    # Graphs Section
    dbc.Row([
        dbc.Col(dcc.Graph(id='visit-time-chart'), width=6),
        dbc.Col(dcc.Graph(id='visitor-geo-chart'), width=6),
    ], className="mb-4"),

    # Logs Table Section
    html.Hr(style=const.hr_style),
    html.H4("Recent Access Logs", style={'color': const.TEXT_COLOR}),
    html.Div(id='admin-log-table'),

    dcc.Interval(id='admin-refresh', interval=60*1000) # Refresh every minute
], fluid=True)

@callback(
    [Output('visit-time-chart', 'figure'),
     Output('visitor-geo-chart', 'figure'),
     Output('admin-log-table', 'children')],
    Input('admin-refresh', 'n_intervals')
)
def update_admin_stats(n):
    df = cotDatabase.get_visitor_stats()
    if df.empty:
        return px.scatter(title="No Data"), px.scatter(title="No Data"), html.P("No logs found.")

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

    return time_fig, geo_fig, table
