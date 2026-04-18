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

TEXT_COLOR = "#ABB8C9"
BRIGHTER_TEXT_COLOR = "#E2E8F0"
HOVER_TEXT_COLOR = "#FFFFFF"  # "#00FFFF"
BACKGROUND_COLOR = "#1a1a1a" #"#0F172A"
GRID_COLOR = "rgba(255, 255, 255, 0.1)"  # Subtle white grid

# Plotting Dimensions
PIXELS_PER_ROW = 350
FIXED_OVERHEAD = 180

app = Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])

server = app.server
cotIndexer = CotCmrIndexer()
cotDatabase = CotDatabase()

palette_options = cotIndexer.get_palette_names()
app_timezone = "US/Eastern"
asset_class_list = cotIndexer.get_asset_classes()
asset_class_list.sort()
asset_list = cotIndexer.get_instrument_names()

# Update the date display in the title daily at midnight
def milliseconds_until_midnight():
    local_tz = pytz.timezone(app_timezone)
    now = datetime.now(tz=local_tz)
    next_midnight = (now + timedelta(days=1)).replace(hour=0,
                                                      minute=0, second=0, microsecond=0)
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
def update_graphs_date(n):
    tz = pytz.timezone(app_timezone)
    current_date = datetime.now(tz).strftime('%Y-%m-%d')
    return f"COT Analysis {current_date}"


@app.callback(
    Output('cot_graphs', 'figure'),
    [Input('cot_graphs_input', 'value'),
     Input('palette_input', 'value')]  # New Input
)
def get_cot_graphs(value, palette_name):
    grid_color = GRID_COLOR
    color_palette = cotIndexer.get_palette(palette_name)
    assets = cotIndexer.get_assets_for_asset_class(value)
    row_count = len(assets)

    total_height = (PIXELS_PER_ROW * row_count) + FIXED_OVERHEAD
    v_spacing = 80 / total_height  # Consistent ~80px gap

    titles = []
    for asset in enumerate(assets):
        titles.append(asset[1] + " Index")
        titles.append(asset[1] + " Positions")

    specs = [[{"secondary_y": False}, {"secondary_y": True}]
             for _ in range(row_count)]
    fig = make_subplots(rows=row_count, shared_xaxes=False, cols=2, subplot_titles=(
        titles), specs=specs, horizontal_spacing=0.04, vertical_spacing=v_spacing)

    for idx, asset in enumerate(assets):
        cur_row = idx + 1
        col = 1
        df = cotIndexer.get_symbols_custom_index(asset)

        xaxis_weeks = 52 * 2
        x_axis_start_range = 0
        if len(df.index) >= xaxis_weeks:  # one year
            x_axis_start_range = len(df.index) - xaxis_weeks

        # Indexing Plot
        fig.add_trace(go.Scatter(x=df.index, y=df["comms"], line_shape='hv', legendgroup='commercials', showlegend=False,
                                 name='commercials', line=dict(width=1, color=color_palette[0])), row=cur_row, col=col)
        fig.add_trace(go.Scatter(x=df.index, y=df["lrg"], line_shape='hv', legendgroup='large specs', showlegend=False,
                                 name='large specs', line=dict(width=1, color=color_palette[1])), row=cur_row, col=col)
        fig.add_trace(go.Scatter(x=df.index, y=df["sml"], line_shape='hv', legendgroup='small specs', showlegend=False,
                                 name='small specs', line=dict(width=1, color=color_palette[2])), row=cur_row, col=col)
        fig.update_xaxes(row=cur_row, col=col, showgrid=False, matches='x', range=[
                         df.index[x_axis_start_range], df.index[-1]])
        fig.update_yaxes(row=cur_row, col=col, title="index", showgrid=True,
                         gridcolor=grid_color, gridwidth=1, range=[0, 100])

        # Positioning Plot
        col = 2
        legend = cur_row == 1 and col == 2
        fig.add_trace(go.Bar(x=df.index, y=df["comms_net"], legendgroup='commercials', showlegend=legend, zorder=0, marker=dict(opacity=1, line=dict(color=color_palette[0])),
                             name='commercials', marker_color=color_palette[0]), row=cur_row, col=col, secondary_y=False)
        fig.add_trace(go.Bar(x=df.index, y=df["lrg_net"], legendgroup='large specs', showlegend=legend, zorder=1, marker=dict(opacity=1, line=dict(color=color_palette[1])),
                             name='large specs', marker_color=color_palette[1]), row=cur_row, col=col, secondary_y=False)
        fig.add_trace(go.Bar(x=df.index, y=df["sml_net"], legendgroup='small specs', showlegend=legend, zorder=2, marker=dict(opacity=1, line=dict(color=color_palette[2])),
                             name='small specs', marker_color=color_palette[2]), row=cur_row, col=col, secondary_y=False)
        fig.add_trace(go.Scatter(x=df.index, y=df["oi"], legendgroup='open interest', showlegend=legend, zorder=0, marker=dict(opacity=1, line=dict(color=color_palette[3])),
                                 name='open interest', marker_color=color_palette[3]), row=cur_row, col=col, secondary_y=True)
        fig.update_xaxes(row=cur_row, col=col, showgrid=False, matches='x', range=[
                         df.index[x_axis_start_range], df.index[-1]])
        fig.update_yaxes(row=cur_row, col=col, title="net", showgrid=True,
                         gridcolor=grid_color, gridwidth=1, secondary_y=False)
        fig.update_yaxes(row=cur_row, col=col, title="open",
                         showgrid=False, secondary_y=True)

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BACKGROUND_COLOR,
        plot_bgcolor=BACKGROUND_COLOR,
        font=dict(color=BRIGHTER_TEXT_COLOR),  # Sets color for all graph text
        showlegend=True,
        legend=dict(orientation="h", entrywidth=100, bgcolor=BACKGROUND_COLOR, font=dict(
            size=14, color=BRIGHTER_TEXT_COLOR), yanchor="bottom", y=1.02, xanchor="left"),
        autosize=True,
        height=total_height,
        margin=dict(t=100, b=50, l=50, r=50),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="rgba(20, 20, 20, 0.8)",
                        font=dict(color=HOVER_TEXT_COLOR)),
        bargap=0.2,
    )
    return fig


def get_cot_graphs_only(value):
    grid_color = GRID_COLOR
    color_palette = cotIndexer.get_palette()
    assets = cotIndexer.get_assets_for_asset_class(value)
    num_cols = 2
    row = 1
    col = 1
    fig = make_subplots(rows=len(assets), shared_xaxes=False, cols=num_cols, subplot_titles=(
        assets), horizontal_spacing=0.04, vertical_spacing=0.1)
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
        fig.update_xaxes(row=row, col=col, showgrid=False, matches='x', range=[
                         df.index[x_axis_start_range], df.index[-1]])
        fig.update_yaxes(row=row, col=col, title="index", showgrid=True,
                         gridcolor=grid_color, gridwidth=1, range=[0, 100], tick0=0, dtick=20)

        col = col + 1
        if col > num_cols:
            col = 1
            row = row + 1

    fig.update_layout(
        template="plotly_dark",
        font=dict(color=TEXT_COLOR),  # Sets color for all graph text
        showlegend=True,
        legend=dict(orientation="h", entrywidth=100, bgcolor=BACKGROUND_COLOR, font=dict(
            size=14, color=TEXT_COLOR), yanchor="top", y=1.01, xanchor="center"),
        autosize=True,
        height=(PIXELS_PER_ROW * row) + FIXED_OVERHEAD,
        width=None,
        hovermode="x",
    )
    return fig


graphs_layout = html.Div([
    dbc.Container([
        # Date Display and Latest Update
        html.H2(id='date-display',
                style={'textAlign': 'center', 'color': BRIGHTER_TEXT_COLOR}),
        html.P(f"Latest update: {cotDatabase.latest_update_timestamp()}", style={
               'textAlign': 'center', 'fontSize': 'small', 'color': BRIGHTER_TEXT_COLOR}),
        dcc.Interval(id="daily-interval",
                     interval=milliseconds_until_midnight(), n_intervals=0),
    ], fluid=True),

    html.Hr(style={
        'color': BRIGHTER_TEXT_COLOR,   # Sets the color for modern browsers
        'backgroundColor': TEXT_COLOR,  # Ensures color in older browsers
        'height': '1px',                # Thickness of the line
        'border': 'none',               # Removes default 3D shading
        'opacity': '1.0',               # Makes it subtle (optional)
        'marginTop': '10px',            # Space above the line
        'marginBottom': '10px',         # Space below the line
        'width': '95%',                 # Don't let it touch the screen edges
        'margin-left': 'auto',          # Centers the line
        'margin-right': 'auto'
    }),
    html.Br(),

    dbc.Row([
        # Theme Selector Group
        dbc.Col([
            dbc.Row([
                dbc.Col(html.Label("Theme: ", style={
                        'color': BRIGHTER_TEXT_COLOR, 'textAlign': 'right', 'fontWeight': 'bold'}), width=4, className="text-end"),
                dbc.Col(dbc.Select(
                    id='palette_input',
                    options=[{'label': x, 'value': x}
                        for x in palette_options],
                    value=palette_options[0] if palette_options else None,
                    style={'textAlign': 'center', 'color': BRIGHTER_TEXT_COLOR,
                        'backgroundColor': BACKGROUND_COLOR, 'borderColor': TEXT_COLOR}
                ), width=8)
            ], align='center')
        ], width=4),  # Centering the column

        # Asset Class Selector Group
        dbc.Col([
            dbc.Row([
                dbc.Col(html.Label("Asset Class:", style={
                        'color': BRIGHTER_TEXT_COLOR, 'textAlign': 'right', 'fontWeight': 'bold'}), width=4, className="text-end"),
                dbc.Col(dcc.Loading(dbc.Select(
                    id='cot_graphs_input',
                    options=[{'label': x, 'value': x}
                        for x in asset_class_list],
                    value=f"{cotIndexer.get_default_asset_class()}",
                    style={'textAlign': 'center', 'color': BRIGHTER_TEXT_COLOR,
                        'backgroundColor': BACKGROUND_COLOR, 'borderColor': TEXT_COLOR}
                )), width=8)
            ], align='center')
        ], width=4),
    ], justify='center'),
    html.Br(),

    html.Hr(style={
        'color': TEXT_COLOR,            # Sets the color for modern browsers
        'backgroundColor': TEXT_COLOR,  # Ensures color in older browsers
        'height': '1px',                # Thickness of the line
        'border': 'none',               # Removes default 3D shading
        'opacity': '0.25',              # Makes it subtle (optional)
        'marginTop': '1px',            # Space above the line
        'marginBottom': '10px',         # Space below the line
        'width': '95%',                 # Don't let it touch the screen edges
        'margin-left': 'auto',          # Centers the line
        'margin-right': 'auto'
    }),
    html.Br(),

    # Row for the COT graphs
    dbc.Row(
        dbc.Col(
            dcc.Loading(
                type="circle",
                children=[dcc.Graph(id='cot_graphs', config={
                                    'responsive': True}, style={'width': '100%'})],
            ),
            width=12,  # Full width column
            style={"padding": "0"}  # Centering the graph
        ),
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
def update_positioning_date(n):
    tz = pytz.timezone(app_timezone)
    current_date = datetime.now(tz).strftime('%Y-%m-%d')
    return f"Positioning {current_date}"

# Dash callback to update the positioning table
@app.callback(
    Output('cot_positioning', 'children'),
    [Input('cot_positioning_df_input', 'value')]
)
def get_CFTC_df_selection(value):
    if value == 'ALL':
        # Pass the full list of asset classes to your indexer
        return dbc.Table.from_dataframe(
            cotIndexer.get_positioning_table_by_asset_class(asset_class_list),
            bordered=True
        )
    # Otherwise, process the single selected asset class
    return dbc.Table.from_dataframe(
        cotIndexer.get_positioning_table_by_asset_class(
            [value] if isinstance(value, str) else value),
        bordered=True
    )


positioning_layout = html.Div([
    dbc.Container([
        html.H2(id='date-display-positioning', style={'textAlign': 'center'}),
        html.P(f"Latest update: {cotDatabase.latest_update_timestamp()}", style={
               'textAlign': 'center', 'fontSize': 'small'}),
        dcc.Interval(id="daily-interval-positioning",
                     interval=milliseconds_until_midnight(), n_intervals=0),
    ], fluid=True),

    html.Hr(style={
        'color': BRIGHTER_TEXT_COLOR,   # Sets the color for modern browsers
        'backgroundColor': TEXT_COLOR,  # Ensures color in older browsers
        'height': '1px',                # Thickness of the line
        'border': 'none',               # Removes default 3D shading
        'opacity': '1.0',               # Makes it subtle (optional)
        'marginTop': '10px',            # Space above the line
        'marginBottom': '10px',         # Space below the line
        'width': '95%',                 # Don't let it touch the screen edges
        'margin-left': 'auto',          # Centers the line
        'margin-right': 'auto'
    }),
    html.Br(),

    dbc.Row([
        dbc.Col([
            dbc.Row([
                dcc.Loading(
                    type="circle",
                    children=[
                        dcc.Dropdown(
                            id='cot_positioning_df_input',
                            options=[{'label': x, 'value': x}
                                     for x in asset_class_list],
                            value=asset_class_list,  # This selects every item in the list by default
                            multi=True,
                            # Adding 'form-control' and 'bg-dark' forces the dark style
                            className="form-control bg-dark text-white border-secondary",
                            searchable=False,
                            clearable=True,
                            style={'color': BRIGHTER_TEXT_COLOR, 'backgroundColor': BACKGROUND_COLOR}  # Backup inline style to ensure dark background if the class doesn't apply for some reason
                        )
                        # dbc.Select(
                        #     id='cot_positioning_df_input',
                        #     options=[{'label': 'All Assets', 'value': 'ALL'}] +
                        #     [{'label': x, 'value': x}
                        #         for x in asset_class_list],
                        #     value='ALL',  # Set "ALL" as the default
                        #     placeholder='Select asset class',
                        #     style={'textAlign': 'center', 'color': BRIGHTER_TEXT_COLOR,
                        #            'backgroundColor': BACKGROUND_COLOR, 'borderColor': TEXT_COLOR}
                        # )
                    ])
            ])
        ], width={'size': 8, 'offset': 2})  # Centering the column
    ], align='center'),
    html.Br(),

    html.Hr(style={
        'color': TEXT_COLOR,            # Sets the color for modern browsers
        'backgroundColor': TEXT_COLOR,  # Ensures color in older browsers
        'height': '1px',                # Thickness of the line
        'border': 'none',               # Removes default 3D shading
        'opacity': '0.25',               # Makes it subtle (optional)
        'marginTop': '10px',            # Space above the line
        'marginBottom': '10px',         # Space below the line
        'width': '95%',                 # Don't let it touch the screen edges
        'margin-left': 'auto',          # Centers the line
        'margin-right': 'auto'
    }),
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
        html.H2("Views", style={'color': BRIGHTER_TEXT_COLOR}),
        html.Hr(style={'backgroundColor': BACKGROUND_COLOR}),
        dbc.Nav(
            [
                dbc.NavLink("Graphs", href="/graphs", id="graphs-link",
                            active="exact", style={'color': TEXT_COLOR}),
                dbc.NavLink("Positioning", href="/positioning", id="positioning-link",
                            active="exact", style={'color': TEXT_COLOR})
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
        "background-color": BACKGROUND_COLOR,
        "color": TEXT_COLOR,
        # 0% opacity border for separation
        "borderRight": f"1px solid {TEXT_COLOR}26"  # 26 is hex for 15% opacity
    },
)

###############################################################################
#
# Main Layout
#
###############################################################################
content = html.Div(id="page-content", style={"margin-left": "16rem", "padding": "1rem 1rem",
                   "width": "calc(100% - 16rem)", "backgroundColor": BACKGROUND_COLOR})
app.layout = html.Div(children=[dcc.Location(
    id='url', refresh=False), sidebar, content],
    # This tells all Bootstrap components to use the DARKLY variables
    # extra_data_attributes={"data-bs-theme": "dark"}
)

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
