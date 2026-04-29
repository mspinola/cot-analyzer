import dash_bootstrap_components as dbc
import io
import logging
import pandas as pd
import plotly.graph_objects as go
import pytz
import time
import zipfile

from dateutil.relativedelta import relativedelta
from dash import Dash, State, html, dcc, Input, Output, callback, callback_context
from datetime import datetime, timedelta, timezone
from flask import request
from plotly.subplots import make_subplots

from CotCmrIndexer import CotCmrIndexer
from CotDatabase import CotDatabase

TEXT_COLOR = "#ABB8C9"
BRIGHTER_TEXT_COLOR = "#E2E8F0"
HOVER_TEXT_COLOR = "#FFFFFF"  # "#00FFFF"
BACKGROUND_COLOR = "#1a1a1a"  # "#0F172A"
GRID_COLOR = "rgba(255, 255, 255, 0.1)"  # Subtle white grid

# Plotting Dimensions
PIXELS_PER_ROW = 350
FIXED_OVERHEAD = 180

app = Dash(__name__, external_stylesheets=[dbc.themes.DARKLY])
server = app.server

# Note, this is a slow operation, so we only want to do it once and pass the indexer around as needed.
print("Loading COT Data... (this might take a moment)")
start_time = time.time()
cotIndexer = CotCmrIndexer()
logging.info(f"Loading COT data took: {time.time() - start_time:.2f}s")
start_time = time.time()
cotDatabase = CotDatabase()
logging.info(f"CotDatabase took: {time.time() - start_time:.2f}s")

palette_options = cotIndexer.get_palette_names()
app_timezone = "US/Eastern"
asset_class_list = cotIndexer.get_asset_classes()
asset_class_list.sort()
asset_list = cotIndexer.get_instrument_names()


def is_mobile():
    """Detects if the user agent belongs to a mobile device."""
    user_agent = request.headers.get("User-Agent", "").lower()
    mobile_keywords = ["android", "webos", "iphone", "ipad", "ipod", "blackberry", "iemobile", "opera mini"]
    return any(keyword in user_agent for keyword in mobile_keywords)


def milliseconds_until_midnight():
    """Calculate the number of milliseconds until the next midnight in the app's timezone."""
    local_tz = pytz.timezone(app_timezone)
    now = datetime.now(tz=local_tz)
    next_midnight = (now + timedelta(days=1)).replace(hour=0,
                                                      minute=0, second=0, microsecond=0)
    delta = next_midnight - now
    return int(delta.total_seconds() * 1000)


def parse_setup_thresholds(setup):
    if setup == '95 5':
        max_threshold = 95
        min_threshold = 5
    elif setup == '90 10':
        max_threshold = 9
        min_threshold = 10
    elif setup == '75 25':
        max_threshold = 75
        min_threshold = 25
    else:
        max_threshold = 101
        min_threshold = -1

    return min_threshold, max_threshold


###############################################################################
#
# Graphs
#
###############################################################################
@app.callback(
    Output("date-display", "children"),
    Input("daily-interval", "n_intervals")
)
def update_graphs_date(n):
    """Callback to update the date in the title of the graphs page."""
    tz = pytz.timezone(app_timezone)
    current_date = datetime.now(tz).strftime('%Y-%m-%d')
    return f"COT Analysis {current_date}"

@app.callback(
    Output('cot_graphs', 'figure'),
    [Input('global_single_asset_class_input', 'value'),
     Input('global_palette_input', 'value'),
     Input('global_multi_equity_selector_input', 'value'),
     Input('global_setup_threshold_input', 'value')]
)
def get_cot_graphs(asset_class, palette_name, selected_assets, setup):
    enabled_plots = 'Positioning'
    overlay_selection = 'Price'
    min_threshold, max_threshold = parse_setup_thresholds(setup)

    grid_color = GRID_COLOR
    color_palette = cotIndexer.get_palette(palette_name)

    if selected_assets is None:
        assets = cotIndexer.get_assets_for_asset_class(asset_class)
    elif selected_assets:
        assets = selected_assets  # Use specific user selections if provided
    else:
        assets = cotIndexer.get_assets_for_asset_class(asset_class)
    assets.sort()

    row_count = len(assets)

    total_height = (PIXELS_PER_ROW * row_count) + FIXED_OVERHEAD
    v_spacing = 80 / total_height  # Consistent ~80px gap

    if enabled_plots == 'All':
        num_cols = 2
    elif enabled_plots in ['Indexing', 'Positioning']:
        num_cols = 1
    else:
        num_cols = 0

    titles = []
    for asset in assets:
        if enabled_plots in ['All', 'Indexing']:
            titles.append(asset + " Index")
        if enabled_plots in ['All', 'Positioning']:
            titles.append(asset + " Positions")

    specs = []
    if enabled_plots in ['Indexing']:
        specs = [[{"secondary_y": False}] for _ in range(row_count)]
    if enabled_plots in ['Positioning']:
        specs = [[{"secondary_y": True}] for _ in range(row_count)]
    if enabled_plots in ['All']:
        specs = [[{"secondary_y": False}, {"secondary_y": True}]
                 for _ in range(row_count)]

    fig = make_subplots(rows=row_count, shared_xaxes=False, cols=num_cols, subplot_titles=(
        titles), specs=specs, horizontal_spacing=0.08, vertical_spacing=v_spacing)
    fig.update_annotations(yshift=10, font=dict(size=15))

    for idx, asset in enumerate(assets):
        cur_row = idx + 1
        cur_col = 1
        df = cotIndexer.get_symbols_custom_index(asset)

        xaxis_weeks = 78
        x_axis_start_range = max(0, len(df.index) - xaxis_weeks)

        # Indexing Plot
        if enabled_plots in ['All', 'Indexing']:
            # Only show legend for the first plot
            legend = cur_row == 1 and cur_col == num_cols
            fig.add_trace(go.Scatter(x=df.index, y=df["comms"], legendgroup='commercials', line_shape='hv', showlegend=legend, zorder=0, line=dict(color=color_palette[0], width=1),
                                     name='commercials'), row=cur_row, col=cur_col, secondary_y=False)
            fig.add_trace(go.Scatter(x=df.index, y=df["lrg"], legendgroup='large specs', line_shape='hv', showlegend=legend, zorder=1, line=dict(color=color_palette[1], width=1),
                                     name='large specs'), row=cur_row, col=cur_col)
            fig.add_trace(go.Scatter(x=df.index, y=df["sml"], legendgroup='small specs', line_shape='hv', showlegend=legend, zorder=2, line=dict(color=color_palette[2], width=1),
                                     name='small specs'), row=cur_row, col=cur_col)
            fig.update_xaxes(row=cur_row, col=cur_col, showgrid=False, matches='x', range=[
                             df.index[x_axis_start_range], df.index[-1]])
            fig.update_yaxes(row=cur_row, col=cur_col, title="index",
                             showgrid=True, gridcolor=grid_color, gridwidth=1, range=[0, 100])

            # Loop through the data to find 'Extreme' clusters
            for i in range(1, len(df)):
                if df['comms'].iloc[i] is None or df['lrg'].iloc[i] or df['sml'].iloc[i] is None:
                    continue
                elif df['comms'].iloc[i] >= max_threshold and df['lrg'].iloc[i] <= min_threshold and df['sml'].iloc[i] <= min_threshold:
                    color = "rgba(255, 0, 0, 0.3)"  # Red Heat
                elif df['comms'].iloc[i] <= min_threshold and df['lrg'].iloc[i] >= max_threshold and df['sml'].iloc[i] >= max_threshold:
                    color = "rgba(0, 255, 0, 0.3)"  # Green Heat
                else:
                    continue

                # Highlight the specific week on the chart
                fig.add_vrect(
                    row=cur_row,
                    col=cur_col,
                    x0=df.index[i-1],
                    x1=df.index[i],
                    fillcolor=color,
                    layer="below",
                    line_width=0,
                )
            cur_col = cur_col + 1

        # Positioning Plot
        if enabled_plots in ['All', 'Positioning']:
            legend = cur_row == 1 and cur_col == num_cols  # Only show legend for the first plot
            fig.add_trace(go.Bar(x=df.index, y=df["comms_net"], legendgroup='commercials', showlegend=legend, zorder=0, marker=dict(opacity=1, line=dict(color=color_palette[0])),
                                name='commercials', marker_color=color_palette[0]), row=cur_row, col=cur_col, secondary_y=False)
            fig.add_trace(go.Bar(x=df.index, y=df["lrg_net"], legendgroup='large specs', showlegend=legend, zorder=1, marker=dict(opacity=1, line=dict(color=color_palette[1])),
                                name='large specs', marker_color=color_palette[1]), row=cur_row, col=cur_col, secondary_y=False)
            fig.add_trace(go.Bar(x=df.index, y=df["sml_net"], legendgroup='small specs', showlegend=legend, zorder=2, marker=dict(opacity=1, line=dict(color=color_palette[2])),
                                name='small specs', marker_color=color_palette[2]), row=cur_row, col=cur_col, secondary_y=False)

            if overlay_selection == 'Price' and 'price' in df.columns:
                fig.add_trace(go.Scatter(x=df.index, y=df["price"], legendgroup='price', showlegend=legend, zorder=3, line=dict(color=color_palette[3], width=1),
                                    name='price'), row=cur_row, col=cur_col, secondary_y=True)
            elif overlay_selection == 'Open Interest':
                fig.add_trace(go.Scatter(x=df.index, y=df["oi"], legendgroup='open interest', showlegend=legend, zorder=3, line=dict(color=color_palette[4], width=1),
                                    name='open interest'), row=cur_row, col=cur_col, secondary_y=True)
            else:
                pass

            if enabled_plots == 'All':
                fig.update_xaxes(row=cur_row, col=cur_col, showgrid=False, matches='x', range=[
                                df.index[x_axis_start_range], df.index[-1]])
            else:
                fig.update_xaxes(row=cur_row, col=cur_col, showgrid=False, matches='x', autorange=True)
            fig.update_yaxes(row=cur_row, col=cur_col, title="net positions", showgrid=True,
                            gridcolor=grid_color, gridwidth=1, secondary_y=False)
            if overlay_selection == 'Open Interest':
                fig.update_yaxes(row=cur_row, col=cur_col, title="open interest", showgrid=False, secondary_y=True)
            elif overlay_selection == 'Price':
                fig.update_yaxes(row=cur_row, col=cur_col, title="price", showgrid=False, secondary_y=True)

            # Loop through the data to find 'Extreme' clusters
            for i in range(1, len(df)):
                if df['comms'].iloc[i] is None or df['lrg'].iloc[i] is None or df['sml'].iloc[i] is None:
                    continue
                elif df['comms'].iloc[i] >= max_threshold and df['lrg'].iloc[i] <= min_threshold and df['sml'].iloc[i] <= min_threshold:
                    color = "rgba(255, 0, 0, 0.3)"  # Red Heat
                elif df['comms'].iloc[i] <= min_threshold and df['lrg'].iloc[i] >= max_threshold and df['sml'].iloc[i] >= max_threshold:
                    color = "rgba(0, 255, 0, 0.3)"  # Green Heat
                else:
                    continue

                # Highlight the specific week on the chart
                fig.add_vrect(
                    row=cur_row,
                    col=cur_col,
                    x0=df.index[i-1],
                    x1=df.index[i],
                    fillcolor=color,
                    layer="below",
                    line_width=0,
                )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BACKGROUND_COLOR,
        plot_bgcolor=BACKGROUND_COLOR,
        font=dict(color=BRIGHTER_TEXT_COLOR),  # Sets color for all graph text
        showlegend=True,
        legend=dict(
            orientation="h",
            entrywidth=120,
            entrywidthmode='pixels',
            bgcolor=BACKGROUND_COLOR,
            font=dict(size=14, color=BRIGHTER_TEXT_COLOR),
            yanchor="bottom",
            y=1.05,
            x=0.5,
            xanchor="center"
        ),
        autosize=True,
        height=total_height,
        margin=dict(t=10, b=10, l=10, r=10),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="rgba(20, 20, 20, 0.8)",
                        font=dict(color=HOVER_TEXT_COLOR)),
        bargap=0.2,
    )
    return fig

@app.callback(
    Output('cot_graphs_plot_input', 'value'),
    Input('cot_graphs_plot_input', 'value')
)
def update_plot_dropdown_value(selection):
    enabled_plots = 'Positioning'
    if not selection or selection == 'Positioning':
        enabled_plots = 'Positioning'
    elif selection == 'Indexing':
        enabled_plots = 'Indexing'
    elif selection == 'All':
        enabled_plots = 'All'
    else:
        enabled_plots = 'None'
    return enabled_plots

@app.callback(
    Output('cot_graphs_plot_overlay_input', 'value'),
    Input('cot_graphs_plot_overlay_input', 'value')
)
def update_overlay_dropdown_value(selection):
    if selection == 'Open Interest':
        return 'Open Interest'
    elif selection == 'Price':
        return 'Price'
    else:
        return 'None'

@app.callback(
    Output('global_setup_threshold_input', 'value'),
    Input('global_setup_threshold_input', 'value')
)
def plot_setup_threshold_input(selection):
    if selection == '95 5':
        return '95 5'
    elif selection == '90 10':
        return '90 10'
    elif selection == '75 25':
        return '75 25'
    else:
        return 'None'


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

    # Row for the COT graphs
    dbc.Row(
        dbc.Col(
            dcc.Loading(
                type="circle",
                children=[dcc.Graph(id='cot_graphs', config={'scrollZoom': True,
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
@app.callback(
    Output('cot_positioning', 'children'),
    [Input('global_multi_asset_class_selector_input', 'value'),
     Input('cot_positioning_column_select_input', 'value')]
)
def get_CFTC_df_selection(assets, selected_columns):
    """Dash callback to update the positioning table"""
    # Determine the list of asset classes to fetch
    if not assets:
        return html.P("Select an asset class to view positioning data.", style={'textAlign': 'center', 'color': TEXT_COLOR})

    asset_list = [assets] if isinstance(assets, str) else assets
    df = cotIndexer.get_positioning_table_by_asset_class(asset_list)

    if not df.empty:
        df = df.sort_values(by=['Asset Class', 'Name'], ascending=[True, True])

        # Logic to filter columns based on the 'selected_columns' dropdown
        if True: # selected_columns:
            # Always keep core columns, then add user-selected extras
            core_cols = ['Date', 'Asset Class', 'Symbol', 'Name', 'Commercials', 'Large Specs', 'Small Specs', 'Willco']
            # Map dropdown values to actual DataFrame column names if they differ
            col_map = {'Comm 26wk': 'Comms (26-Week)'}
            requested_cols = [col_map.get(c, c) for c in selected_columns]

            final_cols = [c for c in core_cols + requested_cols if c in df.columns]
            df = df[final_cols]

    return dbc.Table.from_dataframe(
        df,
        bordered=True,
        hover=True,
        responsive=True,
        striped=True,
    )


@app.callback(
    Output("download-positioning-csv", "data"),
    Input("btn_download_csv", "n_clicks"),
    State('global_multi_asset_class_selector_input', 'value'),  # Capture current filter state
    prevent_initial_call=True,
)
def download_positioning_table(n_clicks, selected_values):
    if not n_clicks or not selected_values:
        return None

    asset_list = [selected_values] if isinstance(
        selected_values, str) else selected_values

    # Fetch the dataframe
    df = cotIndexer.get_positioning_table_by_asset_class(asset_list)
    if not df.empty:
        df = df.sort_values(by=['Asset Class', 'Name'], ascending=[True, True])

    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M')
    return dcc.send_data_frame(df.to_csv, f"COT_Positioning_{timestamp}.csv", index=False)


@app.callback(
    Output('cot_positioning_options', 'children'),
    [Input('cot_positioning_column_select_input', 'value')]
)
def cot_positioning_column_select_input(value):
    if not value:
        return None
    return value


positioning_layout = html.Div([
    dbc.Container([
        html.H2(id='date-display', style={'textAlign': 'center'}),
        html.P(f"Latest update: {cotDatabase.latest_update_timestamp()}", style={
               'textAlign': 'center', 'fontSize': 'small'}),
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
        dbc.Col([
            dcc.Loading(
                type="circle",
                children=[
                    html.Div(id='cot_positioning')
                ],
                style={"textAlign": "center"}
            )], width="auto")
    ], justify='center', className="mt-3 mb-3"),  # Pulled to the center with margin top/bottom
])

@app.callback(
    Output("sidebar-full-download-logic", "data"),
    Input("sidebar-full-download-btn", "n_clicks"),
    prevent_initial_call=True,
)
def download_cftc_data_zip(n_clicks):
    if not n_clicks:
        return None

    all_classes = cotIndexer.get_asset_classes()
    all_classes.sort()

    # Create an in-memory buffer to hold the zip data
    buffer = io.BytesIO()

    # Initialize the ZipFile object
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for asset_class in all_classes:
            for asset in cotIndexer.get_assets_for_asset_class(asset_class):
                instrument_code = cotIndexer.get_instrument_code_from_name(
                    asset)
                df = cotIndexer.collect_symbol_summary_results(instrument_code)

                if not df.empty:
                    # Convert DataFrame to a CSV string
                    csv_string = df.to_csv(index=False)

                    # Write the CSV string into the zip as a file
                    # We sanitize the name by removing spaces
                    file_name = f"{cotIndexer.get_instrument_symbol_from_name(asset).replace(' ', '_')}_summary.csv"
                    zf.writestr(file_name, csv_string)

                df_detailed = cotIndexer.collect_symbol_detailed_results(
                    instrument_code)
                if not df_detailed.empty:
                    csv_string_detailed = df_detailed.to_csv(index=False)
                    file_name_detailed = f"{cotIndexer.get_instrument_symbol_from_name(asset).replace(' ', '_')}_detailed.csv"
                    zf.writestr(file_name_detailed, csv_string_detailed)

    # Seek to the start of the buffer so Dash can read it
    buffer.seek(0)

    zip_filename = f"COT_Full_Data_{datetime.now().strftime('%Y-%m-%d')}.zip"

    # Use send_bytes to transmit the binary zip data
    return dcc.send_bytes(buffer.getvalue(), zip_filename)


@app.callback(
    Output("sidebar-real-test-download-logic", "data"),
    Input("sidebar-real-test-download-btn", "n_clicks"),
    prevent_initial_call=True,
)
def download_real_test_data_zip(n_clicks):
    if not n_clicks:
        return None

    all_classes = cotIndexer.get_asset_classes()
    all_classes.sort()

    # Create an in-memory buffer to hold the zip data
    buffer = io.BytesIO()

    # Initialize the ZipFile object
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for asset_class in all_classes:
            for asset in cotIndexer.get_assets_for_asset_class(asset_class):
                instrument_code = cotIndexer.get_instrument_code_from_name(
                    asset)
                df = cotIndexer.create_real_test_event_asset_list(
                    instrument_code)

                if not df.empty:
                    # Convert DataFrame to a CSV string
                    csv_string = df.to_csv(index=False)

                    # Write the CSV string into the zip as a file
                    # We sanitize the name by removing spaces
                    file_name = f"{cotIndexer.get_instrument_symbol_from_name(asset).replace(' ', '_')}_real_test.csv"
                    zf.writestr(file_name, csv_string)

    # Seek to the start of the buffer so Dash can read it
    buffer.seek(0)

    zip_filename = f"COT_Real_Test_Data_{datetime.now().strftime('%Y-%m-%d')}.zip"

    # Use send_bytes to transmit the binary zip data
    return dcc.send_bytes(buffer.getvalue(), zip_filename)


###############################################################################
#
# Asset Analysis
#
###############################################################################
analysis_layout = html.Div([
    dbc.Container([
        html.Div(id='analysis-page-header', style={'textAlign': 'center', 'marginBottom': '20px'}),
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

    # Row for the COT graphs
    dbc.Row(
        dbc.Col(
            dcc.Loading(
                type="circle",
                children=[dcc.Graph(id='analysis_stack', config={'scrollZoom': True,
                                    'responsive': True}, style={'width': '100%'})],
            ),
            width=12,  # Full width column
            style={"padding": "0"}  # Centering the graph
        ),
    )
])


@app.callback(
    Output('analysis-page-header', 'children'),
    [Input('global_single_asset_class_input', 'value'),      # The Sidebar Input
     Input('global_single_equity_filter_input', 'value')]  # The Individual Filter
)
def update_analysis_header(asset_class, asset_name):
    if not asset_name:
        return html.H2("SELECT ASSET", style={'color': TEXT_COLOR})

    # Fetch latest data point
    df = cotIndexer.get_symbols_custom_index(asset_name)
    if df is None or df.empty:
        return html.H2(f"{asset_class} | {asset_name}", style={'color': BRIGHTER_TEXT_COLOR})

    # Get the latest Z-score (using the column name from your DataFrame)
    latest_z = df['comms-z'].iloc[-1]

    # Determine color logic based on your 95/5 (Z=2.0) setup
    z_color = "#4ade80" if latest_z >= 2.0 else "#f87171" if latest_z <= -2.0 else TEXT_COLOR

    return [
        html.H2(f"{asset_class.upper()} | {asset_name.upper()}",
                style={'color': BRIGHTER_TEXT_COLOR, 'fontWeight': 'bold', 'marginBottom': '5px'}),
        html.Div([
            html.Span("CURRENT COMMERCIAL Z-SCORE: ", style={'color': TEXT_COLOR, 'fontSize': '0.9rem'}),
            html.Span(f"{latest_z:.2f}", style={'color': z_color, 'fontSize': '1.1rem', 'fontWeight': 'bold'})
        ])
    ]


@app.callback(
    Output('analysis_stack', 'figure'),
    [Input('global_palette_input', 'value'),
     Input('global_single_equity_filter_input', 'value'),
     Input('global_setup_threshold_input', 'value')]
)
def update_analysis_stack(palette_name, asset, setup):
    if not asset:
        return go.Figure()

    min_threshold, max_threshold = parse_setup_thresholds(setup)
    color_palette = cotIndexer.get_palette(palette_name)
    df = cotIndexer.get_symbols_custom_index(asset)
    if df is None:
        return go.Figure()

    fig = make_subplots(
        rows=5,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=("Net Position % of Open Interest", "Spearman Correlation + Price",
                        "Net Positions + Open Interest", "Positioning Index (Trend Exhaustion)",
                        "Positioning Z-Score (Statistical Extremes)"),
        specs=[[{"secondary_y": False}], [{"secondary_y": True}], [{"secondary_y": True}], [{"secondary_y": False}], [{"secondary_y": False}]]
    )

    # Global Legend Toggle Logic: Show legend only once, but use legendgroups to link all 5 plots
    def add_trace_to_all(fig, df, col_name, row, name, color, zorder, visible=True, is_bar=False, secondary=False, showlegend=False):
        if is_bar:
            fig.add_trace(go.Bar(x=df.index, y=df[col_name], name=name, legendgroup=name.lower(), visible=visible,
                                 showlegend=showlegend, marker_color=color, zorder=zorder), row=row, col=1, secondary_y=secondary)
        else:
            fig.add_trace(go.Scatter(x=df.index, y=df[col_name], name=name, legendgroup=name.lower(), visible=visible,
                                     showlegend=showlegend, line=dict(color=color, width=1), zorder=zorder), row=row, col=1, secondary_y=secondary)

    # PLOT 1: % of OI
    # Primary Axis: % of OI
    cur_row = 1
    cur_col = 1
    add_trace_to_all(fig, df, "comm_oi_pct", cur_row, "Commercials", color_palette[0], 0, showlegend=True)
    add_trace_to_all(fig, df, "lrg_oi_pct", cur_row, "Large Specs", color_palette[1], 1, showlegend=True)
    add_trace_to_all(fig, df, "sml_oi_pct", cur_row, "Small Specs", color_palette[2], 2, showlegend=True)
    fig.update_yaxes(title="%", row=cur_row, col=cur_col, gridcolor=GRID_COLOR, secondary_y=False)

    # PLOT 2: Spearman Correlation (-1 to 1)
    # Plotting the relationship between position ranks and price ranks
    cur_row = cur_row + 1
    add_trace_to_all(fig, df, "comm_spearman", cur_row, "Commercials", color_palette[0], 0)
    add_trace_to_all(fig, df, "lrg_spearman", cur_row, "Large Specs", color_palette[1], 1)
    add_trace_to_all(fig, df, "sml_spearman", cur_row, "Small Specs", color_palette[2], 2)
    add_trace_to_all(fig, df, "price", cur_row, "Price", color_palette[3], 3, secondary=True, showlegend=True)
    fig.update_yaxes(title="correlation", row=cur_row, col=cur_col, gridcolor=GRID_COLOR, secondary_y=False)
    fig.update_yaxes(title="$", row=cur_row, col=cur_col, gridcolor=BACKGROUND_COLOR, secondary_y=True)

    # THIRD PLOT: Net Positions (Bars)
    cur_row = cur_row + 1
    add_trace_to_all(fig, df, "comms_net", cur_row, "Commercials", color_palette[0], 0, is_bar=True)
    add_trace_to_all(fig, df, "lrg_net", cur_row, "Large Specs", color_palette[1], 1, is_bar=True)
    add_trace_to_all(fig, df, "sml_net", cur_row, "Small Specs", color_palette[2], 2, is_bar=True)
    add_trace_to_all(fig, df, "oi", cur_row, "Open Interest", color_palette[4], 3, secondary=True, showlegend=True)
    fig.update_yaxes(title="net position", row=cur_row, col=cur_col, gridcolor=GRID_COLOR, secondary_y=False)
    fig.update_yaxes(title="OI", row=cur_row, col=cur_col, gridcolor=BACKGROUND_COLOR, secondary_y=True)

    # FOURTH PLOT: Sentiment Context
    cur_row = cur_row + 1
    add_trace_to_all(fig, df, "comms", cur_row, "Commercials", color_palette[0], 0)
    add_trace_to_all(fig, df, "lrg", cur_row, "Large Specs", color_palette[1], 1)
    add_trace_to_all(fig, df, "sml", cur_row, "Small Specs", color_palette[2], 2)
    # Threshold Lines for Plot 4
    fig.add_hline(y=max_threshold, line_dash="dot", line_color="red", opacity=0.5, row=cur_row, col=cur_col)
    fig.add_hline(y=min_threshold, line_dash="dot", line_color="green", opacity=0.5, row=cur_row, col=cur_col)
    fig.update_yaxes(title="Index", range=[0, 100], row=cur_row, col=cur_col, secondary_y=False, gridcolor=GRID_COLOR)

    # FIFTH PLOT: Sentiment z-score
    cur_row = cur_row + 1
    add_trace_to_all(fig, df, "comms-z", cur_row, "Commercials", color_palette[0], 0)
    add_trace_to_all(fig, df, "lrg-z", cur_row, "Large Specs", color_palette[1], 1)
    add_trace_to_all(fig, df, "sml-z", cur_row, "Small Specs", color_palette[2], 2)
    # Threshold Lines for Plot 5
    fig.add_hline(y=-3.0, line_dash="dot", line_color="red", opacity=0.5, row=cur_row, col=cur_col)
    fig.add_hline(y=3.0, line_dash="dot", line_color="green", opacity=0.5, row=cur_row, col=cur_col)
    fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)", row=5, col=1)
    fig.update_yaxes(title="Std Dev", range=[-4, 4], row=cur_row, col=cur_col, secondary_y=False, gridcolor=GRID_COLOR)

    # Loop through the data to find 'Extreme' clusters
    for i in range(1, len(df)):
        if df['comms'].iloc[i] is None or df['lrg'].iloc[i] is None or df['sml'].iloc[i] is None:
            continue
        elif df['comms'].iloc[i] >= max_threshold and df['lrg'].iloc[i] <= min_threshold and df['sml'].iloc[i] <= min_threshold:
            color = "rgba(255, 0, 0, 0.3)"  # Red Heat
        elif df['comms'].iloc[i] <= min_threshold and df['lrg'].iloc[i] >= max_threshold and df['sml'].iloc[i] >= max_threshold:
            color = "rgba(0, 255, 0, 0.3)"  # Green Heat
        else:
            continue

        # Highlight the specific week on the chart
        for j in range(1, cur_row):
            fig.add_vrect(
                row=j,
                col=cur_col,
                x0=df.index[i-1],
                x1=df.index[i],
                fillcolor=color,
                layer="below",
                line_width=0,
            )

    weeks_back = 156
    start_idx = max(0, len(df) - weeks_back)
    start_date = df.index[start_idx]
    end_date = df.index[-1]

    fig.update_xaxes(
        range=[start_date, end_date],
        minallowed=df.index[0],   # User cannot scroll left past the first data point
        maxallowed=df.index[-1],   # User cannot scroll right past the latest data point
        showspikes=True,
        spikemode="across",
        spikesnap="cursor",
        spikethickness=1,
        spikecolor=BRIGHTER_TEXT_COLOR,
        spikedash="solid",
        hoverformat="%Y-%m-%d",
        matches='x',
        layer="above traces",
        showticklabels=True,
        tickfont_color=TEXT_COLOR
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BACKGROUND_COLOR,
        plot_bgcolor=BACKGROUND_COLOR,
        height=1400,
        hovermode="x unified",
        spikedistance=1000,
        hoverdistance=100
    )

    return fig


@app.callback(
    Output('analysis_asset_selection_input', 'options'),
    Output('analysis_asset_selection_input', 'value'),
    Input('global_single_asset_class_input', 'value')
)
def update_analysis_asset_dropdown_options(selected_class):
    if not selected_class:
        return None, None
    assets = cotIndexer.get_assets_for_asset_class(selected_class)
    assets.sort()
    options = [{'label': x, 'value': x} for x in assets]
    default = options[0].get('value') if options else None
    return options, default


###############################################################################
#
# Heatmap
#
###############################################################################
heatmap_layout = html.Div([
    dbc.Container([
        html.Div("Market Sentiment Heatmap", style={
                 'textAlign': 'center', 'marginBottom': '20px'}),
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
            html.H5("Z-Score Heatmap", style={'color': BRIGHTER_TEXT_COLOR, 'textAlign': 'center'}),
            dcc.Loading(dcc.Graph(id='market_z_score_heat_map'))
        ], width=6),

        dbc.Col([
            html.H5("Index Heatmap", style={'color': BRIGHTER_TEXT_COLOR, 'textAlign': 'center'}),
            dcc.Loading(dcc.Graph(id='market_index_score_heat_map'))
        ], width=6)
    ], className="mb-4"),
    html.Br(),
])


@app.callback(
    Output('market_z_score_heat_map', 'figure'),
    Input('global_multi_asset_class_selector_input', 'value')
)
def update_z_score_heat_map(assest_classes):
    final_df_list = []
    for asset_class in assest_classes:
        class_df = cotIndexer.get_asset_class_z_score_heat(asset_class)
        if class_df.empty:
            continue

        # Sort alphabetically
        class_df = class_df.sort_values(by='Asset', ascending=True)

        # Add a Label column for the class heading (optional, for tooltips)
        class_df['Class'] = asset_class

        # Inject a "Header" row
        header_row = pd.DataFrame([{
            "Asset": f"--- {asset_class.upper()} ---",
            "Commercials": None,
            "Large Specs": None,
            "Small Specs": None,
            "Class": "Header"
        }])
        final_df_list.append(header_row)
        final_df_list.append(class_df)
    df = pd.concat(final_df_list).reset_index(drop=True)

    # Extract values for the matrix
    z_values = df[['Commercials', 'Large Specs', 'Small Specs']].values

    # Build a manual Text Matrix to prevent NaN being rendered as 0.00
    text_matrix = []
    y_display_labels = []
    for i, (name, z_row) in enumerate(zip(df['Asset'], z_values)):
        row_text = ["", "", ""]
        if "---" in str(name):
            new_name = name.replace("---", "")
            y_display_labels.append(" " * (i + 1))
            row_text[1] = f"<b>{new_name}</b>"
        else:
            y_display_labels.append(name)
            for j, val in enumerate(z_row):
                row_text[j] = f"{val:.1f}" if not pd.isna(val) else ""

        text_matrix.append(row_text)

    # Create the Heatmap
    # We use a Diverging scale: Red (Short Extreme) -> Gray (Neutral) -> Green (Long Extreme)
    fig = go.Figure(data=go.Heatmap(
        hoverinfo='none',
        z=z_values,
        x=['Commercials', 'Large Specs', 'Small Specs'],
        y=y_display_labels,
        text=text_matrix,
        texttemplate="%{text}",
        textfont={"size": 13, "family": "Consolas, monospace", "color": "#FFFFFF"},
        colorscale=[
            [0, '#ff4b2b'],
            [0.05, '#ff4b2b'],
            [0.10, '#f87171'],
            [0.25, '#252C36'],
            [0.75, '#252C36'],
            [0.90, '#4ade80'],
            [0.95, '#00c853'],
            [1, '#00c853']
        ],
        zmin=-3, zmax=3,  # Force scale to Z-score range
        xgap=2,
        ygap=2,
        showscale=True,
        colorbar=dict(
            orientation='h',      # Flip to horizontal
            y=-0.08,              # Position it just below the X-axis
            x=0.5,                # Center it under the chart
            xanchor='center',
            thickness=12,         # Make it thinner/sleeker
            len=0.7,              # Don't let it span the full width
            title=dict(text="Std Dev", side="top", font=dict(size=12)),
            tickvals=[-3, -2, -1, 0, 1, 2, 3]  # Explicit ticks for the Z-score
        )
    ))

    fig.update_traces(
        # Matches the cell color of NaNs to the background exactly
        zsmooth=False,
        connectgaps=False,
        zmid=0  # Helps center the color mapping
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BACKGROUND_COLOR,
        plot_bgcolor=BACKGROUND_COLOR,
        height=len(z_values) * 20 + 100,  # Dynamic height based on row count
        margin=dict(t=40, b=10, l=80, r=10),  # Left margin for asset names
        xaxis=dict(side="top", dtick=1, fixedrange=True),
        yaxis=dict(dtick=1, autorange="reversed", fixedrange=True)
    )
    return fig


@app.callback(
    Output('market_index_score_heat_map', 'figure'),
    Input('global_multi_asset_class_selector_input', 'value')
)
def update_index_heat_map(assest_classes):
    final_df_list = []
    for asset_class in assest_classes:
        class_df = cotIndexer.get_asset_class_index_heat(asset_class)
        if class_df.empty:
            continue

        # Sort alphabetically
        class_df = class_df.sort_values(by='Asset', ascending=True)

        # Add a Label column for the class heading (optional, for tooltips)
        class_df['Class'] = asset_class

        # Inject a "Header" row
        header_row = pd.DataFrame([{
            "Asset": f"--- {asset_class.upper()} ---",
            "Commercials": None,
            "Large Specs": None,
            "Small Specs": None,
            "Class": "Header"
        }])
        final_df_list.append(header_row)
        final_df_list.append(class_df)
    df = pd.concat(final_df_list).reset_index(drop=True)

    # Extract values for the matrix
    index_values = df[['Commercials', 'Large Specs', 'Small Specs']].values

    # Build a manual Text Matrix to prevent NaN being rendered as 0.00
    text_matrix = []
    y_display_labels = []
    for i, (name, z_row) in enumerate(zip(df['Asset'], index_values)):
        row_text = ["", "", ""]
        if "---" in str(name):
            new_name = name.replace("---", "")
            y_display_labels.append(" " * (i + 1))
            row_text[1] = f"<b>{new_name}</b>"
        else:
            y_display_labels.append(name)
            for j, val in enumerate(z_row):
                row_text[j] = f"{val:.0f}" if not pd.isna(val) else ""

        text_matrix.append(row_text)

    # Create the Heatmap
    # We use a Diverging scale: Red (Short Extreme) -> Gray (Neutral) -> Green (Long Extreme)
    fig = go.Figure(data=go.Heatmap(
        hoverinfo='none',
        z=index_values,
        x=['Commercials', 'Large Specs', 'Small Specs'],
        y=y_display_labels,
        text=text_matrix,
        texttemplate="%{text}",
        textfont={"size": 13, "family": "Consolas, monospace", "color": "#FFFFFF"},
        colorscale=[
            [0, '#ff4b2b'],
            [0.05, '#ff4b2b'],
            [0.10, '#f87171'],
            [0.25, "#252C36"],
            [0.75, '#252C36'],
            [0.90, '#4ade80'],
            [0.95, '#00c853'],
            [1, '#00c853']
        ],
        zmin=-0, zmax=100,
        xgap=2,
        ygap=2,
        showscale=True,
        colorbar=dict(
            orientation='h',      # Flip to horizontal
            y=-0.08,              # Position it just below the X-axis
            x=0.5,                # Center it under the chart
            xanchor='center',
            thickness=12,         # Make it thinner/sleeker
            len=0.7,              # Don't let it span the full width
            title=dict(text="Index", side="top", font=dict(size=12)),
            tickvals=[0, 25, 50, 75, 100]
        )
    ))

    fig.update_traces(
        # Matches the cell color of NaNs to the background exactly
        zsmooth=False,
        connectgaps=False,
        zmid=0  # Helps center the color mapping
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BACKGROUND_COLOR,
        plot_bgcolor=BACKGROUND_COLOR,
        height=len(index_values) * 20 + 100,  # Dynamic height based on row count
        margin=dict(t=40, b=10, l=80, r=60),  # Left margin for asset names
        xaxis=dict(side="top", dtick=1),
        yaxis=dict(dtick=1, autorange="reversed", fixedrange=True)
    )
    return fig


###############################################################################
#
# Sidebar
#
###############################################################################
SIDEBAR_STYLE = {
    "position": "fixed",
    "top": 0,
    "left": 0,
    "bottom": 0,
    "width": "18rem",
    "padding": "1rem 0.5rem",
    "background-color": BACKGROUND_COLOR,
    "transition": "all 0.5s",
    "overflow-y": "auto",
    "overflow-x": "hidden",
    "display": "flex",
    "flex-direction": "column",
    "borderRight": f"1px solid {TEXT_COLOR}26",
    "zIndex": 1000
}
# The sidebar state when "hidden"
SIDEBAR_HIDDEN_STYLE = {
    **SIDEBAR_STYLE,
    "left": f"-20rem", # Slides it off-screen to the left
}
CONTENT_STYLE = {
    "transition": "margin-left 0.5s",
    "margin-left": "18rem", # sidebar width + 2rem buffer
    "padding": "2rem 1rem",
}
CONTENT_STYLE_HIDDEN = {
    **CONTENT_STYLE,
    "margin-left": "2rem", # Expanded state
}

sidebar = html.Div(
    id="sidebar",
    children=[
        # Heading - Pushed down to avoid the button
        html.Hr(style={'backgroundColor': BACKGROUND_COLOR,
                'marginTop': '3.5rem'}),
        html.Br(),

        # GLOBAL CONTROLS SECTION
        html.Label("Global Controls", style={
                   'color': BRIGHTER_TEXT_COLOR, 'fontWeight': 'bold', 'fontSize': '1rem'}),
        html.Div([
            # Global Asset Class
            html.Label("Asset Class", id="label_global_single_asset_class_input", style={
                       'color': TEXT_COLOR, 'fontSize': '0.85rem'}),
            dbc.Select(
                persistence=True,
                id='global_single_asset_class_input',
                options=[{'label': x, 'value': x} for x in asset_class_list],
                value=f"{cotIndexer.get_default_asset_class()}",
                className="mb-3",
                style={'backgroundColor': BACKGROUND_COLOR,
                       'color': 'TEXT_COLOR', 'borderColor': f"{TEXT_COLOR}26"}
            ),

            html.Label("Multi Asset Class Selector", id='label_global_multi_asset_class_selector_input', style={
                'color': TEXT_COLOR, 'fontSize': '0.85rem'}),
            dcc.Dropdown(
                persistence=True,
                id='global_multi_asset_class_selector_input',
                options=[{'label': x, 'value': x}
                            for x in asset_class_list],
                value=asset_class_list,  # This selects every item in the list by default
                multi=True,
                className="mb-3",
                searchable=False,
                clearable=True,
                # Backup inline style to ensure dark background if the class doesn't apply for some reason
                style={'textAlign': 'center', 'color': BRIGHTER_TEXT_COLOR,
                       'backgroundColor': BACKGROUND_COLOR, 'borderColor': TEXT_COLOR, 'width': '150px'}
            ),

            # Global Single Equity Filter
            html.Label("Single Asset Selector", id='label_global_single_equity_filter_input', style={
                       'color': TEXT_COLOR, 'fontSize': '0.85rem'}),
            dbc.Select(
                persistence=True,
                id='global_single_equity_filter_input',
                className="mb-3",
                style={'backgroundColor': BACKGROUND_COLOR,
                       'color': 'TEXT_COLOR', 'borderColor': f"{TEXT_COLOR}26"}
            ),

            # Global Multi Equity Selector
            html.Label("Multi Equity Selector", id='label_global_multi_equity_selector_input', style={
                       'color': TEXT_COLOR, 'fontSize': '0.85rem'}),
            dcc.Dropdown(
                persistence=True,
                id='global_multi_equity_selector_input',
                multi=True,
                className="mb-3",
                searchable=False,
                clearable=True,
                # Backup inline style to ensure dark background if the class doesn't apply for some reason
                style={'textAlign': 'center', 'color': BRIGHTER_TEXT_COLOR,
                       'backgroundColor': BACKGROUND_COLOR, 'borderColor': TEXT_COLOR, 'width': '150px'}
            ),

            # Global Theme
            html.Label("Color Palette", id='label_global_palette_input', style={
                       'color': TEXT_COLOR, 'fontSize': '0.85rem'}),
            dbc.Select(
                persistence=True,
                id='global_palette_input',
                options=[{'label': x, 'value': x} for x in palette_options],
                value=palette_options[0] if palette_options else None,
                className="mb-3",
                style={'backgroundColor': BACKGROUND_COLOR,
                       'color': TEXT_COLOR, 'borderColor': f"{TEXT_COLOR}26"}
            ),

            # Setup Threshold Selector Group
            html.Label("Setup Highlight (slow)", id='label_global_setup_threshold_input', style={
                       'color': TEXT_COLOR, 'fontSize': '0.85rem'}),
            dbc.Select(
                persistence=True,
                id='global_setup_threshold_input',
                options=[{'label': 'None', 'value': 'None'}, {'label': '95 5', 'value': '95 5'}, {'label': '90 10', 'value': '90 10'}, {'label': '75 25', 'value': '75 25'}],
                value=f"{'None', 'None'}",
                className="mb-3",
                style={'backgroundColor': BACKGROUND_COLOR,
                       'color': TEXT_COLOR, 'borderColor': f"{TEXT_COLOR}26"}
            ),

            # Positioning Table Extended Data
            html.Label("Positioning Table Data", id='label_cot_positioning_column_select_input', style={
                        'color': TEXT_COLOR, 'fontSize': '0.85rem'}),
            dcc.Dropdown(
                id='cot_positioning_column_select_input',
                options=[{'label': 'Comm 26wk', 'value': 'Comm 26wk'}],
                value=[],
                multi=True,
                # Adding 'form-control' and 'bg-dark' forces the dark style
                className="form-control bg-dark text-white border-secondary",
                searchable=False,
                clearable=True,
                # Backup inline style to ensure dark background if the class doesn't apply for some reason
                style={'textAlign': 'center', 'color': BRIGHTER_TEXT_COLOR,
                       'backgroundColor': BACKGROUND_COLOR, 'borderColor': TEXT_COLOR, 'width': '150px'}
            )
        ], className="px-3 mb-4"),

        # Navigation Links
        html.Label("Views", style={
            'color': BRIGHTER_TEXT_COLOR, 'fontWeight': 'bold', 'fontSize': '1rem'}),
        dbc.Nav(
            [
                dbc.NavLink("Heatmap", href="/heatmap", id="heatmap-link",
                            active="exact", style={'color': TEXT_COLOR}),
                dbc.NavLink("Graphs", href="/graphs", id="graphs-link",
                            active="exact", style={'color': TEXT_COLOR}),
                dbc.NavLink("Positioning Table", href="/positioning", id="positioning-link",
                            active="exact", style={'color': TEXT_COLOR}),
                dbc.NavLink("Asset Analysis", href="/analysis", id="analysis-link",
                            active="exact", style={'color': TEXT_COLOR}),
            ],
            vertical=True,
            pills=True,
            className="mb-4"
        ),
        html.Br(),

        # Action Section
        html.Label("Data Download", style={
            'color': BRIGHTER_TEXT_COLOR, 'fontWeight': 'bold', 'fontSize': '1rem'}),
        html.Br(),
        html.Div([
            dbc.Button(
                [html.I(className="bi bi-cloud-download me-2"),
                 "CFTC Data"],
                id="sidebar-full-download-btn",
                color="secondary",
                outline=True,
                className="w-100",
                style={
                    'color': TEXT_COLOR,
                    'borderColor': f"{TEXT_COLOR}26",
                    'fontSize': '0.9rem'
                }
            ),
            dcc.Download(id="sidebar-full-download-logic")
        ], className="px-3 mb-4"),

        html.Div([
            dbc.Button(
                [html.I(className="bi bi-cloud-download me-2"),
                 "Position Table"],
                id="btn_download_csv",
                color="secondary",
                outline=True,
                className="w-100",
                style={
                    'color': TEXT_COLOR,
                    'borderColor': f"{TEXT_COLOR}26",
                    'whiteSpace': 'nowrap'
                }
            ),
            dcc.Download(id="download-positioning-csv"),
        ], className="px-3 mb-4"),

        html.Div([
            dbc.Button(
                [html.I(className="bi bi-cloud-download me-2"),
                 "Real Test Data"],
                id="sidebar-real-test-download-btn",
                color="secondary",
                outline=True,
                className="w-100",
                style={
                    'color': TEXT_COLOR,
                    'borderColor': f"{TEXT_COLOR}26",
                    'fontSize': '0.9rem'
                }
            ),
            dcc.Download(id="sidebar-real-test-download-logic")
        ], className="px-3 mb-4"),

        html.Hr(style={'opacity': '0.15'}),
        html.Div([
            "BlueMagicAi | ",
                 html.A(
                     "CFTC",
                     href="https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm",
                     target="_blank",
                     style={'color': BRIGHTER_TEXT_COLOR,
                            'textDecoration': 'underline'}
                 ),
                 ], style={'padding': '20px', 'text-align': 'center', 'fontSize': '0.8rem', 'color': TEXT_COLOR})
    ],
    style=SIDEBAR_STYLE,
)

@app.callback(
    [Output("sidebar", "style"),
     Output("page-content", "style")],
    [Input("url", "pathname"), # Auto-close sidebar on mobile when link is clicked
     Input("btn-sidebar-toggle", "n_clicks")],
    [State("sidebar", "style")]
)
def toggle_sidebar(pathname, n_clicks, current_style):
    # Logic to close sidebar if a link was clicked on mobile
    ctx = callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if is_mobile() and triggered_id == 'url':
        return SIDEBAR_HIDDEN_STYLE, CONTENT_STYLE_HIDDEN

    # Detect mobile on initial load (when n_clicks is None)
    if n_clicks and current_style.get("left") == 0:
        return SIDEBAR_HIDDEN_STYLE, CONTENT_STYLE_HIDDEN

    return SIDEBAR_STYLE, CONTENT_STYLE


@app.callback(
    [Output('global_single_asset_class_input', 'disabled'),
     Output('global_single_asset_class_input', 'style')],
    Input('url', 'pathname'),
    State('global_single_asset_class_input', 'style')
)
def update_sidebar_selector(pathname, current_style):
    is_disabled = pathname == '/positioning' or pathname == '/heatmap'

    # Ensure current_style is a dict
    new_style = (current_style or {}).copy()

    if is_disabled:
        new_style['opacity'] = '0.2'
        new_style['cursor'] = 'not-allowed'
    else:
        new_style['opacity'] = '1.0'
        new_style['cursor'] = 'default'

    return is_disabled, new_style


@app.callback(
    [Output('global_multi_equity_selector_input', 'disabled'),
     Output('global_multi_equity_selector_input', 'style')],
    Input('url', 'pathname'),
    State('global_multi_equity_selector_input', 'style')
)
def update_sidebar_selector_multi_equity_selector(pathname, current_style):
    is_disabled = pathname != '/graphs'

    # Ensure current_style is a dict
    new_style = (current_style or {}).copy()

    if is_disabled:
        new_style['opacity'] = '0.2'
        new_style['cursor'] = 'not-allowed'
    else:
        new_style['opacity'] = '1.0'
        new_style['cursor'] = 'default'

    return is_disabled, new_style


@app.callback(
    [Output('global_single_equity_filter_input', 'disabled'),
     Output('global_single_equity_filter_input', 'style')],
    Input('url', 'pathname'),
    State('global_single_equity_filter_input', 'style')
)
def update_sidebar_selector_gloabl_single_equity(pathname, current_style):
    is_disabled = pathname != '/analysis'

    # Ensure current_style is a dict
    new_style = (current_style or {}).copy()

    if is_disabled:
        new_style['opacity'] = '0.2'
        new_style['cursor'] = 'not-allowed'
    else:
        new_style['opacity'] = '1.0'
        new_style['cursor'] = 'default'

    return is_disabled, new_style


@app.callback(
    [Output('global_single_equity_filter_input', 'options'),
     Output('global_single_equity_filter_input', 'value')],
    Input('global_single_asset_class_input', 'value')
)
def update_asset_dropdown_options(selected_class):
    if not selected_class:
        return [], None
    assets = cotIndexer.get_assets_for_asset_class(selected_class)
    assets.sort()
    options = [{'label': x, 'value': x} for x in assets]
    default_value = options[0].get('value') if options else None
    return options, default_value


@app.callback(
    [Output('global_multi_equity_selector_input', 'options'),
     Output('global_multi_equity_selector_input', 'value')],
    Input('global_single_asset_class_input', 'value')
)
def update_multi_asset_dropdown_options(selected_class):
    if not selected_class:
        return [], []
    assets = cotIndexer.get_assets_for_asset_class(selected_class)
    assets.sort()
    options = [{'label': x, 'value': x} for x in assets]
    return options, assets


@app.callback(
    [Output('global_palette_input', 'disabled'),
     Output('global_palette_input', 'style')],
    Input('url', 'pathname'),
    State('global_palette_input', 'style')
)
def update_sidebar_selector_palette_input(pathname, current_style):
    is_disabled = pathname == '/positioning' or pathname == '/heatmap'

    # Ensure current_style is a dict
    new_style = (current_style or {}).copy()

    if is_disabled:
        new_style['opacity'] = '0.2'
        new_style['cursor'] = 'not-allowed'
    else:
        new_style['opacity'] = '1.0'
        new_style['cursor'] = 'default'

    return is_disabled, new_style

@app.callback(
    [Output('global_setup_threshold_input', 'disabled'),
     Output('global_setup_threshold_input', 'style')],
    Input('url', 'pathname'),
    State('global_setup_threshold_input', 'style')
)
def update_sidebar_selector_setup_threshold(pathname, current_style):
    is_disabled = pathname == '/positioning' or pathname == '/heatmap'

    # Ensure current_style is a dict
    new_style = (current_style or {}).copy()

    if is_disabled:
        new_style['opacity'] = '0.2'
        new_style['cursor'] = 'not-allowed'
    else:
        new_style['opacity'] = '1.0'
        new_style['cursor'] = 'default'

    return is_disabled, new_style


@app.callback(
    [Output('global_multi_asset_class_selector_input', 'disabled'),
     Output('global_multi_asset_class_selector_input', 'style')],
    Input('url', 'pathname'),
    State('global_multi_asset_class_selector_input', 'style')
)
def update_sidebar_selector(pathname, current_style):
    is_disabled = pathname == '/graphs' or pathname == '/analysis'

    # Ensure current_style is a dict
    new_style = (current_style or {}).copy()

    if is_disabled:
        new_style['opacity'] = '0.2'
        new_style['cursor'] = 'not-allowed'
    else:
        new_style['opacity'] = '1.0'
        new_style['cursor'] = 'default'

    return is_disabled, new_style


@app.callback(
    [Output('cot_positioning_column_select_input', 'disabled'),
     Output('cot_positioning_column_select_input', 'style')],
    Input('url', 'pathname'),
    State('cot_positioning_column_select_input', 'style')
)
def update_sidebar_selector_positioning_table_data(pathname, current_style):
    is_disabled = pathname != '/positioning'

    # Ensure current_style is a dict
    new_style = (current_style or {}).copy()

    if is_disabled:
        new_style['opacity'] = '0.2'
        new_style['cursor'] = 'not-allowed'
    else:
        new_style['opacity'] = '1.0'
        new_style['cursor'] = 'default'

    return is_disabled, new_style


@app.callback(
    Output('label_cot_positioning_column_select_input', 'style'),
    Input('url', 'pathname'),
    State('label_cot_positioning_column_select_input', 'style')
)
def dim_label_by_path_positioing_table_data(pathname, current_style):
    # Determine if the control is "Inactive" for the current view
    is_dimmed = pathname != '/positioning'

    # Clone the current style dictionary to avoid mutating state
    new_style = (current_style or {}).copy()

    # Apply the Opacity "Filter"
    new_style['opacity'] = '0.2' if is_dimmed else '1.0'
    new_style['transition'] = 'opacity 0.5s'

    return new_style


###############################################################################
#
# Main Layout
#
###############################################################################
content = html.Div(id="page-content", style={"margin-left": "16rem", "padding": "1rem 1rem",
                   "width": "calc(100% - 16rem)", "backgroundColor": BACKGROUND_COLOR})
app.layout = html.Div([
    dcc.Location(id='url'),
    dbc.Button(
        [html.I(className="bi bi-list"), "Toggle Sidebar"],
        id="btn-sidebar-toggle",
        color="secondary",
        outline=True,
        style={
            "position": "fixed",
            "top": "1rem",
            "left": "1rem",
            "zIndex": "1001",  # Higher than sidebar (1000)
            "color": TEXT_COLOR,
            "border": f"1px solid {TEXT_COLOR}26"
        }
    ),
    sidebar,
    content,
], style={"backgroundColor": BACKGROUND_COLOR, "minHeight": "100vh"})

@app.callback(
    Output('page-content', 'children'),
    [Input('url', 'pathname')]
)
def display_page(pathname):
    """Callback to control page navigation."""
    if pathname == '/analysis':
        return analysis_layout
    elif pathname == '/positioning':
        return positioning_layout
    elif pathname == '/heatmap':
        return heatmap_layout
    else:
        return graphs_layout

@app.callback(
    [Output('graphs-link', 'active'),
     Output('positioning-link', 'active'),
     Output('analysis-link', 'active'),
     Output('heatmap-link', 'active')],
    Input('url', 'pathname')
)
def update_active_links(pathname):
    """Callback to set the active state of navigation links based on current pathname."""
    is_graphs = pathname in ['/graphs', '/', None]
    is_positioning = pathname == '/positioning'
    is_analysis = pathname == '/analysis'
    is_heatmap = pathname == '/heatmap'

    return is_graphs, is_positioning, is_analysis, is_heatmap
