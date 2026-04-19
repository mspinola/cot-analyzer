import dash_bootstrap_components as dbc
import io
import logging
import pandas as pd
import plotly.graph_objects as go
import pytz
import time
import zipfile

from dateutil.relativedelta import relativedelta
from dash import Dash, State, html, dcc, Input, Output, callback
from datetime import datetime, timedelta, timezone
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
# app = Dash(__name__, external_stylesheets=[dbc.themes.DARKLY, dbc.icons.BOOTSTRAP])

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


def milliseconds_until_midnight():
    """Calculate the number of milliseconds until the next midnight in the app's timezone."""
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
    [Input('cot_graphs_input', 'value'),
     Input('palette_input', 'value'),
     Input('asset_selection_input', 'value'),
     Input('cot_graphs_plot_input', 'value')]
)
def get_cot_graphs(value, palette_name, selected_assets, enabled_plots):
    grid_color = GRID_COLOR
    color_palette = cotIndexer.get_palette(palette_name)

    if selected_assets:
        assets = selected_assets  # Use specific user selections if provided
    else:
        assets = cotIndexer.get_assets_for_asset_class(value)
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
                #  for _ in range(row_count - 1)]
        # specs.append([{"secondary_y": True}])
    if enabled_plots in ['All']:
        specs = [[{"secondary_y": False}, {"secondary_y": True}]
                 for _ in range(row_count)]
    print(type(specs), specs)
    fig = make_subplots(rows=row_count, shared_xaxes=False, cols=num_cols, subplot_titles=(
        titles), specs=specs, horizontal_spacing=0.08, vertical_spacing=v_spacing)
    fig.update_annotations(yshift=10, font=dict(size=15))

    for idx, asset in enumerate(assets):
        cur_row = idx + 1
        cur_col = 1
        df = cotIndexer.get_symbols_custom_index(asset)

        xaxis_weeks = 52 * 2
        x_axis_start_range = max(0, len(df.index) - xaxis_weeks)

        # Indexing Plot
        if enabled_plots in ['All', 'Indexing']:
            legend = cur_row == 1 and cur_col == num_cols  # Only show legend for the first plot
            fig.add_trace(go.Scatter(x=df.index, y=df["comms"], line_shape='hv', legendgroup='commercials', showlegend=legend,
                                    name='commercials', line=dict(width=1, color=color_palette[0])), row=cur_row, col=cur_col)
            fig.add_trace(go.Scatter(x=df.index, y=df["lrg"], line_shape='hv', legendgroup='large specs', showlegend=legend,
                                    name='large specs', line=dict(width=1, color=color_palette[1])), row=cur_row, col=cur_col)
            fig.add_trace(go.Scatter(x=df.index, y=df["sml"], line_shape='hv', legendgroup='small specs', showlegend=legend,
                                    name='small specs', line=dict(width=1, color=color_palette[2])), row=cur_row, col=cur_col)
            if True:  # enabled_plots == 'All':
                fig.update_xaxes(row=cur_row, col=cur_col, showgrid=False, matches='x', range=[
                                 df.index[x_axis_start_range], df.index[-1]])
            else:
                fig.update_xaxes(row=cur_row, col=cur_col,
                                 showgrid=False, matches='x', autorange=True)
            fig.update_yaxes(row=cur_row, col=cur_col, title="index", showgrid=True,
                             gridcolor=grid_color, gridwidth=1, range=[0, 100])
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
            fig.add_trace(go.Scatter(x=df.index, y=df["oi"], legendgroup='open interest', showlegend=legend, zorder=0, marker=dict(opacity=1, line=dict(color=color_palette[3])),
                                    name='open interest', marker_color=color_palette[3]), row=cur_row, col=cur_col, secondary_y=True)
            if enabled_plots == 'All':
                fig.update_xaxes(row=cur_row, col=cur_col, showgrid=False, matches='x', range=[
                                df.index[x_axis_start_range], df.index[-1]])
            else:
                fig.update_xaxes(row=cur_row, col=cur_col, showgrid=False, matches='x', autorange=True)
            fig.update_yaxes(row=cur_row, col=cur_col, title="net positions", showgrid=True,
                            gridcolor=grid_color, gridwidth=1, secondary_y=False)
            fig.update_yaxes(row=cur_row, col=cur_col, title="open interest", showgrid=False, secondary_y=True)

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
    Output('asset_selection_input', 'options'),
    Output('asset_selection_input', 'value'),
    Input('cot_graphs_input', 'value')
)
def update_asset_dropdown_options(selected_class):
    if not selected_class:
        return [], []
    assets = cotIndexer.get_assets_for_asset_class(selected_class)
    assets.sort()
    options = [{'label': x, 'value': x} for x in assets]
    return options, assets

@app.callback(
    Output('cot_graphs_plot_input', 'value'),
    Input('cot_graphs_plot_input', 'value')
)
def update_plot_dropdown_value(selection):
    enabled_plots = 'All'  # Default to all plots if no selection is made
    if not selection or selection == 'All':
        enabled_plots = 'All'
    elif selection == 'Indexing':
        enabled_plots = 'Indexing'
    elif selection == 'Positioning':
        enabled_plots = 'Positioning'
    else:
        enabled_plots = 'None'
    return enabled_plots

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
                        'color': BRIGHTER_TEXT_COLOR, 'textAlign': 'right', 'fontWeight': 'bold', 'whiteSpace': 'nowrap'}), width=4, className="text-end"),
                dbc.Col(dbc.Select(
                    id='palette_input',
                    options=[{'label': x, 'value': x}
                        for x in palette_options],
                    value=palette_options[0] if palette_options else None,
                    style={'textAlign': 'center', 'color': BRIGHTER_TEXT_COLOR,
                        'backgroundColor': BACKGROUND_COLOR, 'borderColor': TEXT_COLOR, 'width': '150px'}
                ), width='auto')
            ], align='center', className="g-2 flex-nowrap")  # g-2 adds a tiny gap between label and box, flex-nowrap keeps them on the same line
        ], width='auto', className="px-4"),

        # Asset Class Selector Group
        dbc.Col([
            dbc.Row([
                dbc.Col(html.Label("Asset Class:", style={
                        'color': BRIGHTER_TEXT_COLOR, 'textAlign': 'right', 'fontWeight': 'bold', 'whiteSpace': 'nowrap'}), width=4, className="text-end"),
                dbc.Col(dcc.Loading(dbc.Select(
                    id='cot_graphs_input',
                    options=[{'label': x, 'value': x}
                        for x in asset_class_list],
                    value=f"{cotIndexer.get_default_asset_class()}",
                    style={'textAlign': 'center', 'color': BRIGHTER_TEXT_COLOR,
                        'backgroundColor': BACKGROUND_COLOR, 'borderColor': TEXT_COLOR, 'width': '150px'}
                )), width='auto')
            ], align='center', className="g-2 flex-nowrap")  # g-2 adds a tiny gap between label and box, flex-nowrap keeps them on the same line
        ], width='auto', className="px-4"),

        # Individual Asset Selector
        dbc.Col([
            dbc.Row([
                dbc.Col(html.Label("Asset Filter:", style={
                        'color': BRIGHTER_TEXT_COLOR, 'textAlign': 'right', 'fontWeight': 'bold', 'whiteSpace': 'nowrap'}), width=4, className="text-end"),
                dbc.Col(dcc.Dropdown(
                    id='asset_selection_input',
                    # We'll populate 'options' via callback
                    multi=True,
                    placeholder="All Assets",
                    className="dash-dropdown",  # gets styling from css
                    searchable=False,
                    clearable=True,
                    # Backup inline style to ensure dark background if the class doesn't apply for some reason
                    style={'text_align': 'center', 'color': BRIGHTER_TEXT_COLOR,
                        'backgroundColor': BACKGROUND_COLOR, 'borderColor': TEXT_COLOR, 'width': '150px'}
                ), width='auto')
            ], align='center', className="g-2 flex-nowrap")  # g-2 adds a tiny gap between label and box, flex-nowrap keeps them on the same line
        ], width='auto', className="px-4"),

        # PlotSelector Group
        dbc.Col([
            dbc.Row([
                dbc.Col(html.Label("Plots:", style={
                        'color': BRIGHTER_TEXT_COLOR, 'textAlign': 'right', 'fontWeight': 'bold', 'whiteSpace': 'nowrap'}), width=4, className="text-end"),
                dbc.Col(dcc.Loading(dbc.Select(
                    id='cot_graphs_plot_input',
                    options=[{'label': 'Indexing', 'value': 'Indexing'}, {'label': 'Positioning', 'value': 'Positioning'}, {'label': 'All', 'value': 'All'}],
                    value=f"{'All'}",
                    style={'textAlign': 'center', 'color': BRIGHTER_TEXT_COLOR,
                        'backgroundColor': BACKGROUND_COLOR, 'borderColor': TEXT_COLOR, 'width': '150px'}
                )), width='auto')
            ], align='center', className="g-2 flex-nowrap")  # g-2 adds a tiny gap between label and box, flex-nowrap keeps them on the same line
        ], width='auto', className="px-4"),
    ], justify='center', className="mt-3 mb-3"),  # Pulled to the center with margin top/bottom
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
@app.callback(
    Output("date-display-positioning", "children"),
    Input("daily-interval-positioning", "n_intervals")
)
def update_positioning_date(n):
    """Callback to update the date in the title of the positioning page."""
    tz = pytz.timezone(app_timezone)
    current_date = datetime.now(tz).strftime('%Y-%m-%d')
    return f"Positioning {current_date}"

# Dash callback to update the positioning table
@app.callback(
    Output('cot_positioning', 'children'),
    [Input('cot_positioning_df_input', 'value')]
)
def get_CFTC_df_selection(value):
    # Determine the list of asset classes to fetch
    if not value:
        return html.P("Select an asset class to view positioning data.", style={'textAlign': 'center', 'color': TEXT_COLOR})

    asset_list = [value] if isinstance(value, str) else value

    # Fetch the data
    df = cotIndexer.get_positioning_table_by_asset_class(asset_list)

    # MULTI-LEVEL SORT
    # Assumes columns are named 'Asset Class' and 'Name' (adjust if named 'Instrument' etc.)
    if not df.empty:
        df = df.sort_values(by=['Asset Class', 'Name'], ascending=[True, True])

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
    State('cot_positioning_df_input', 'value'),  # Capture current filter state
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
                # dcc.Loading(
                #     type="circle",
                #     children=[
                dbc.Col(
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
                        # Backup inline style to ensure dark background if the class doesn't apply for some reason
                        style={'color': BRIGHTER_TEXT_COLOR,
                               'backgroundColor': BACKGROUND_COLOR}
                    ), width=True
                    # ])
                ),
                dbc.Col(
                    dbc.Button(
                        [html.I(className="bi bi-download me-2"),
                         "Download CSV"],
                        id="btn_download_csv",
                        color="secondary",
                        outline=True,
                        style={
                            'color': TEXT_COLOR,
                            'borderColor': 'rgba(171, 184, 201, 0.3)',
                            'whiteSpace': 'nowrap'
                        }
                    ), width="auto"
                ),
                # The actual download component (invisible)
                dcc.Download(id="download-positioning-csv"),
            ], align='center', className="g-2 flex-nowrap")  # g-2 adds a tiny gap between label and box, flex-nowrap keeps them on the same line
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
# Sidebar
#
###############################################################################
# The sidebar width when open
SIDEBAR_WIDTH = "16rem"
SIDEBAR_STYLE = {
    "position": "fixed",
    "top": 0,
    "left": 0,
    "bottom": 0,
    "width": SIDEBAR_WIDTH,
    "padding": "2rem 1rem",
    "background-color": BACKGROUND_COLOR,
    "transition": "all 0.5s",
    "overflow": "hidden",
    "display": "flex",
    "flex-direction": "column",
    "borderRight": f"1px solid {TEXT_COLOR}26",
    "zIndex": 1000
}
# The sidebar state when "hidden"
SIDEBAR_HIDDEN_STYLE = {
    **SIDEBAR_STYLE,
    "left": f"-{SIDEBAR_WIDTH}", # Slides it off-screen to the left
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
        html.Hr(style={
            'backgroundColor': BACKGROUND_COLOR,
            'marginTop': '3.5rem',  # The "Buffer Zone"
            }),
        html.H2("COT Analyzer",
                style={
                    'color': BRIGHTER_TEXT_COLOR,
                    'paddingLeft': '0.5rem'
                }),
        html.Hr(style={'backgroundColor': BACKGROUND_COLOR}),

        # Navigation Links
        dbc.Nav(
            [
                dbc.NavLink("Graphs", href="/graphs", id="graphs-link",
                            active="exact", style={'color': TEXT_COLOR}),
                dbc.NavLink("Positioning", href="/positioning", id="positioning-link",
                            active="exact", style={'color': TEXT_COLOR})
            ],
            vertical=True,
            pills=True,
            className="mb-4"
        ),

        # Action Section
        html.Div([
            # html.Hr(style={'opacity': '0.15'}),
            dbc.Button(
                [html.I(className="bi bi-cloud-download me-2"),
                 "Download CFTC Data"],
                id="sidebar-full-download-btn",
                color="secondary",
                outline=True,
                className="w-100",
                style={
                    'color': TEXT_COLOR,
                    'borderColor': 'rgba(171, 184, 201, 0.3)',
                    'fontSize': '0.9rem'
                }
            ),
            dcc.Download(id="sidebar-full-download-logic")
        ]),
        html.Br(),

        html.Div([
            dbc.Button(
                [html.I(className="bi bi-cloud-download me-2"),
                 "Download Real Test Data"],
                id="sidebar-real-test-download-btn",
                color="secondary",
                outline=True,
                className="w-100",
                style={
                    'color': TEXT_COLOR,
                    'borderColor': 'rgba(171, 184, 201, 0.3)',
                    'fontSize': '0.9rem'
                }
            ),
            dcc.Download(id="sidebar-real-test-download-logic")
        ]),
        html.Br(),

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
     Output("page-content", "style")], # Assuming page-content is main wrapper
    [Input("btn-sidebar-toggle", "n_clicks")],
    [State("sidebar", "style")]
)
def toggle_sidebar(n_clicks, current_style):
    if n_clicks is None:
        return SIDEBAR_STYLE, CONTENT_STYLE

    # If the current left position is 0, it's visible. Toggle it.
    if current_style.get("left") == 0:
        return SIDEBAR_HIDDEN_STYLE, CONTENT_STYLE_HIDDEN

    return SIDEBAR_STYLE, CONTENT_STYLE


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
    if pathname == '/positioning':
        return positioning_layout
    elif pathname == '/graphs' or pathname is None or pathname == '/':
        return graphs_layout
    else:
        return graphs_layout

@app.callback(
    [Output('graphs-link', 'active'), Output('positioning-link', 'active')],
    Input('url', 'pathname')
)
def update_active_links(pathname):
    """Callback to set the active state of navigation links based on current pathname."""
    return pathname == '/graphs' or pathname == '/' or pathname is None, pathname == '/positioning'
