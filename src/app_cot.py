import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
import pytz

from dateutil.relativedelta import relativedelta
from dash import Dash, html, dcc, Input, Output, callback
from datetime import datetime, timedelta, timezone
from plotly.subplots import make_subplots

from CotCmrIndexer import CotCmrIndexer
from CotDatabase import CotDatabase

app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

server = app.server
cotIndexer = CotCmrIndexer()
cotDatabase = CotDatabase()

app_timezone = "US/Eastern"
asset_class_list = cotIndexer.get_asset_classes()
asset_list = cotIndexer.get_instrument_names()

# Update the date display in the title daily at midnight
def milliseconds_until_midnight():
    local_tz = pytz.timezone(app_timezone)
    now = datetime.now(tz=local_tz)
    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    delta = next_midnight - now
    return int(delta.total_seconds() * 1000)

###############################################################################
#
# Graphs
#
###############################################################################
# Dash callback to update the date in the title daily
@app.callback(
    Output("date-display", "children"),
    Input("daily-interval", "n_intervals")
)
def update_date(n):
    tz = pytz.timezone(app_timezone)
    current_date = datetime.now(tz).strftime('%Y-%m-%d')
    return f"COT Analysis {current_date}"


@app.callback(
    Output('cot_graphs', 'figure'),
    [Input('cot_graphs_input', 'value')]
)
def get_cot_graphs(value):
    color_palette = ['#e70307', '#0000ff', '#ffff00']  # '#0202ed'
    assets = cotIndexer.get_assets_for_asset_class(value)
    num_cols = 2
    row = 1

    titles = []
    for asset in enumerate(assets):
        titles.append(asset[1] + " Index")
        titles.append(asset[1] + " Net Positions")

    fig = make_subplots(rows=len(assets) * 2, shared_xaxes=False, cols=num_cols, subplot_titles=(titles))
    for idx, asset in enumerate(assets):
        col = 1
        df = cotIndexer.get_symbols_custom_index(asset)

        xaxis_weeks = 52 * 2
        x_axis_start_range = 0
        if len(df.index) >= xaxis_weeks:  # one year
            x_axis_start_range = len(df.index) - xaxis_weeks

        legend = row == 1 and col == 1
        # Indexing Plot
        fig.add_trace(go.Scatter(x=df.index, y=df["comms"], line_shape='hv', legendgroup='commercials', showlegend=legend,
                    name='commercials', line=dict(color=color_palette[0])), row=row, col=col)
        fig.add_trace(go.Scatter(x=df.index, y=df["lrg"], line_shape='hv', legendgroup='large specs', showlegend=legend,
                    name='large specs', line=dict(color=color_palette[1])), row=row, col=col)
        fig.add_trace(go.Scatter(x=df.index, y=df["sml"], line_shape='hv', legendgroup='small specs', showlegend=legend,
                    name='small specs', line=dict(color=color_palette[2])), row=row, col=col)
        fig.update_xaxes(row=row, col=col, showgrid=False, matches='x', range=[df.index[x_axis_start_range], df.index[-1]])
        fig.update_yaxes(row=row, col=col, title="index", showgrid=True, gridcolor="rgba(0, 0, 0, 0.3)", gridwidth=1, range=[0,100])

        # Positioning Plot
        col = 2
        fig.add_trace(go.Bar(x=df.index, y=df["comms_net"], legendgroup='commercials', showlegend=False, zorder=0, marker=dict(opacity=1, line=dict(color=color_palette[0])),
                    name='commercials', marker_color=color_palette[0]), row=row, col=col)


        fig.add_trace(go.Bar(x=df.index, y=df["lrg_net"], legendgroup='large specs', showlegend=False, zorder=1, marker=dict(opacity=1, line=dict(color=color_palette[1])),
                    name='large specs', marker_color=color_palette[1]), row=row, col=col)
        fig.add_trace(go.Bar(x=df.index, y=df["sml_net"], legendgroup='small specs', showlegend=False, zorder=2, marker=dict(opacity=1, line=dict(color=color_palette[2])),
                    name='small specs', marker_color=color_palette[2]), row=row, col=col)
        fig.update_xaxes(row=row, col=col, showgrid=False, matches='x', range=[df.index[x_axis_start_range], df.index[-1]])
        fig.update_yaxes(row=row, col=col, title="index", showgrid=True, gridcolor="rgba(0, 0, 0, 0.3)", gridwidth=1)
        row = row + 1

    fig.update_layout(
        template="simple_white",
        showlegend=True,
        legend=dict(orientation="h", entrywidth=100, bgcolor="rgba(0, 0, 0, 0.15)", font=dict(size=14, color='white'), yanchor="top", y=1.1, xanchor="left"),
        height=600*row,
        width=1600,
        hovermode="x unified",
        hoverlabel=dict(bgcolor="rgba(0, 0, 0, 0)", bordercolor="rgba(0, 0, 0, 0)", font=dict(color="cyan")),
        bargap=0.2,
        yaxis=dict(fixedrange=True),
    )
    return fig


def get_cot_graphs_only(value):
    color_palette = ['#e70307', '#0202ed', '#ffff00']
    assets = cotIndexer.get_assets_for_asset_class(value)
    num_cols = 2
    row = 1
    col = 1
    fig = make_subplots(rows=len(assets), shared_xaxes=False, cols=num_cols, subplot_titles=(assets))
    for idx, asset in enumerate(assets):
        df = cotIndexer.get_symbols_custom_index(asset)

        x_axis_start_range = 0
        if len(df.index) >= 52:  # one year
            x_axis_start_range = len(df.index) - 52

        legend = row == 1 and col == 1
        fig.add_trace(go.Scatter(x=df.index, y=df["comms"], line_shape='hv', legendgroup='commercials', showlegend=legend,
                    name='commercials', line=dict(color=color_palette[0])), row=row, col=col)
        fig.add_trace(go.Scatter(x=df.index, y=df["lrg"], line_shape='hv', legendgroup='large specs', showlegend=legend,
                    name='large specs', line=dict(color=color_palette[1])), row=row, col=col)
        fig.add_trace(go.Scatter(x=df.index, y=df["sml"], line_shape='hv', legendgroup='small specs', showlegend=legend,
                    name='small specs', line=dict(color=color_palette[2])), row=row, col=col)
        fig.update_xaxes(row=row, col=col, showgrid=False, matches='x', range=[df.index[x_axis_start_range], df.index[-1]])
        fig.update_yaxes(row=row, col=col, title="index", showgrid=True, gridcolor="rgba(0, 0, 0, 0.2)", gridwidth=1, range=[0,100], tick0=0, dtick=20)

        col = col + 1
        if col > num_cols:
            col = 1
            row = row + 1

    fig.update_layout(
        template="simple_white",
        showlegend=True,
        legend=dict(orientation="h", entrywidth=100, bgcolor="rgba(0, 0, 0, 0.15)", font=dict(size=14, color='white'), yanchor="top", y=1.1, xanchor="left"),
        height=1200,
        width=1450,
        hovermode="x",
    )
    return fig


graphs_layout = html.Div([
    dbc.Container([
        # Date Display and Latest Update
        html.H2(id='date-display', style={'textAlign': 'center', "text-decoration": "underline"}),
        html.P(f"Latest update: {cotDatabase.latest_update_timestamp()}", style={'textAlign': 'center', 'fontSize': 'small'}),
        dcc.Interval(id="daily-interval", interval=milliseconds_until_midnight(), n_intervals=0),
    ]),
    html.Br(),
    dbc.Row([
        dbc.Col([
            dbc.Row([
                dcc.Loading(
                    type="circle",
                    children=[
                        dcc.Dropdown(
                            id='cot_graphs_input',
                            options=[{'label': x, 'value': x} for x in asset_class_list],
                            value=f"{cotIndexer.get_default_asset_class()}",
                            placeholder='Select Asset Class',
                            multi=False,
                            style={'textAlign': 'center'}
                        )
                    ]
                )
            ])
        ], width={'size': 8, 'offset': 2})
    ], align='center'),

    html.Br(),

    # Row for the COT graphs
    dbc.Row(
        dbc.Col(
            dcc.Loading(
                type="circle",
                children=[dcc.Graph(id='cot_graphs')]
            ),
            width=12,  # Full width column
            style={"display": "flex", "justifyContent": "center"}  # Centering the graph
        ),
        align='center',
    )
])

###############################################################################
#
# Positioning Table
#
###############################################################################
# Dash callback to update the date in the title daily
@app.callback(
    Output("date-display-positioning", "children"),
    Input("daily-interval-positioning", "n_intervals")
)
def update_date(n):
    tz = pytz.timezone(app_timezone)
    current_date = datetime.now(tz).strftime('%Y-%m-%d')
    return f"Positioning {current_date}"

# Dash callback to update the positioning table
@app.callback(
    Output('cot_positioning', 'children'),
    [Input('cot_positioning_df_input', 'value')]
)
def get_CFTC_df_selection(value):
    return dbc.Table.from_dataframe(
        cotIndexer.get_positioning_table_by_asset_class(value),
        # cotIndexer.get_positioning_table(value),
        bordered=True)


positioning_layout = html.Div([
    dbc.Container([
        html.H2(id='date-display-positioning', style={'textAlign': 'center', "text-decoration": "underline"}),
        html.P(f"Latest update: {cotDatabase.latest_update_timestamp()}", style={'textAlign': 'center', 'fontSize': 'small'}),
        dcc.Interval(id="daily-interval-positioning", interval=milliseconds_until_midnight(), n_intervals=0),
    ]),
    html.Br(),
    dbc.Row([
        dbc.Col([
            dbc.Row([
                dcc.Loading(
                    type="circle",
                    children=[
                        dcc.Dropdown(
                            id='cot_positioning_df_input',
                            options=[{'label': x, 'value': x} for x in asset_class_list],
                            value=f"{asset_class_list}",
                            placeholder='Select asset class',
                            multi=True,
                            style={'textAlign': 'center'}
                        )
                    ])
                ])
        ], width={'size': 8, 'offset': 2})  # Centering the column
    ], align='center'),

    html.Br(),

    dbc.Row([
        dbc.Col([
            dcc.Loading(
                type="circle",
                children=[
                    html.Div(id='cot_positioning')
                ],
                style={"textAlign": "center"}
            )], width={'size': 8, 'offset': 2})  # Centering the column
    ], align='center')
])

###############################################################################
#
# Sidebar
#
###############################################################################
sidebar = html.Div(
    [
        html.H2("COT Report", className="display-4"),
        html.Hr(),
        dbc.Nav(
            [
                dbc.NavLink("Graphs", href="/graphs", id="graphs-link", active="exact"),
                dbc.NavLink("Positioning", href="/positioning", id="positioning-link", active="exact")
            ],
            vertical=True,
            pills=True,
        ),
    ],
    style={
        "position": "fixed",
        "top": 0,
        "left": 0,
        "bottom": 0,
        "width": "16rem",
        "padding": "2rem 1rem",
        "background-color": "#f8f9fa",
    },
)

###############################################################################
#
# Main Layout
#
###############################################################################
content = html.Div(id="page-content", style={"margin-left": "18rem", "padding": "2rem 1rem"})
app.layout = html.Div(children=[dcc.Location(id='url', refresh=False), sidebar, content])

# Callback to control page navigation
@app.callback(
    Output('page-content', 'children'),
    [Input('url', 'pathname')]
)
def display_page(pathname):
    if pathname == '/positioning':
        return positioning_layout
    elif pathname == '/graphs' or pathname is None or pathname == '/':
        return graphs_layout
    else:
        return graphs_layout

# Callback to update active state of navigation links
@app.callback(
    [Output('graphs-link', 'active'), Output('positioning-link', 'active')],
    Input('url', 'pathname')
)
def update_active_links(pathname):
    return pathname == '/graphs' or pathname == '/' or pathname is None, pathname == '/positioning'

