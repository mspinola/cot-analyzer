import constants as const
import pages.helpers as helpers
import utils

import dash
import dash_bootstrap_components as dbc
import math
import plotly.graph_objects as go

from dash import State, html, dcc, callback, Input, Output
from indexer import cotIndexer
from plotly.subplots import make_subplots


# Register this file as a page
dash.register_page(
    __name__,
    path='/graphs'
)

AVAILABLE_PLOTS = {
    "oi_pct": "Net Position % of OI",
    "willco": "WillCo",
    "spearman": "Spearman Correlation",
    "net_pos": "Net Positions",
    "index": "Positioning Index",
    "zscore": "Positioning Z-Score",
    "momentum": "Momentum Index",
    "tension": "Tension Oscillator"
}

layout = html.Div([
    dbc.Container([
        dbc.Accordion([
            dbc.AccordionItem([
                dbc.Row([
                    dbc.Col([
                        html.Label("Lookback:", style=const.label_style),
                        dbc.Select(
                            id='graphs_lookback_selector',
                            options=[
                                {"label": "26 Weeks", "value": "26"},
                                {"label": "52 Weeks", "value": "52"},
                                {"label": "Custom", "value": "Custom"},
                            ],
                            value="Custom",
                            size="sm",
                            className="mb-3 bg-dark text-white border-secondary",
                        )
                    ], xs=12, md="auto"),

                    dbc.Col([
                        html.Label("Asset Class Selector", style=const.label_style),
                        dbc.Select(
                            persistence=True,
                            id='graphs_single_asset_class_input',
                            options=[{'label': x, 'value': x}
                                    for x in cotIndexer.get_asset_classes()],
                            value=f"{cotIndexer.get_default_asset_class()}",
                            className="mb-3 bg-dark text-white border-secondary",
                        ),
                    ], xs=12, md="auto"),

                    dbc.Col([
                        html.Label("Asset Selector", style=const.label_style),
                        dcc.Dropdown(
                            persistence=True,
                            id='graphs_multi_equity_selector_input',
                            multi=True,
                            className="mb-3 dash-dropdown bg-dark text-white",
                            searchable=False,
                            clearable=True,
                        ),
                    ], xs=12, md="auto"),

                    dbc.Col([
                        html.Label("Columns:", style=const.label_style),
                        dbc.Select(
                            id='graphs_columns_selector',
                            persistence=True,
                            options=[
                                {"label": "1 Column", "value": "1"},
                                {"label": "2 Columns", "value": "2"},
                                {"label": "3 Columns", "value": "3"},
                            ],
                            value="1", # We'll handle responsive defaults in the callback
                            size="sm",
                            className="mb-3 bg-dark text-white border-secondary",
                        )
                    ], xs=6, md="auto"),

                    dbc.Col([
                        html.Label("Plot Selector", style=const.label_style),
                        dbc.Select(
                            persistence=True,
                            id='graphs_plot_selector_input',
                            options=[{'label': v, 'value': k} for k, v in AVAILABLE_PLOTS.items()],
                            value="net_pos",
                            className="mb-3 bg-dark text-white border-secondary",
                        ),
                    ], xs=6, md="auto"),
                ], align="center"),
            ],
            title="CHART CONFIGURATION",
            item_id="chart_config"),
        ],
        start_collapsed=True, # Keeps it clean on initial mobile load
        flush=True,
        className="mb-3",
        style={'backgroundColor': const.BACKGROUND_COLOR}),

        html.Hr(style=const.hr_style),

        dbc.Row([
            dcc.Loading(
                id="loading-cot-graphs",
                type="default", # Options: "graph", "cube", "circle", "dot", or "default"
                children=html.Div(id='cot_graphs'),
                color=const.BRIGHTER_TEXT_COLOR
            )
        ], justify='center')
    ], fluid=True),
])


@callback(
    Output('global_lookback_store', 'data'),
    Input('graphs_lookback_selector', 'value')
)
def update_global_lookback(value):
    if value == "26" or value == "52" or value == "Custom":
        return value
    else:
        return "Custom"


@callback(
    Output('graphs_lookback_selector', 'value'),
    Input('global_lookback_store', 'data')
)
def update_local_lookback(value):
    if value == "26" or value == "52" or value == "Custom":
        return value
    else:
        return "Custom"


@callback(
    Output('graphs_columns_selector', 'value'),
    Input('url', 'pathname'), # Triggers on page load
    State('graphs_columns_selector', 'value')
)
def set_default_columns(pathname, current_val):
    # Only set default if it hasn't been changed by the user (initial load)
    if utils.is_mobile():
        return "1"
    else:
        return "2" # Default for larger screens


@callback(
    Output('cot_graphs', 'children'),
    [Input('graphs_single_asset_class_input', 'value'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('graphs_multi_equity_selector_input', 'value'),
     Input('session_setup_highlight_asset_store', 'data'),
     Input('graphs_plot_selector_input', 'value'),
     Input('global_lookback_store', 'data'),
     Input('graphs_columns_selector', 'value')]
)
def get_cot_graphs(asset_class, palette_name, selected_assets, setup, selected_plot, lookback, num_cols):
    utils.cot_logger.info(f"Generating graphs for Asset Class: {asset_class}, Selected Assets: {selected_assets}, Plot: {selected_plot}, Lookback: {lookback}, Columns: {num_cols}")
    selected_plots = [selected_plot]
    if selected_assets is None or len(selected_assets) == 0 or selected_plots is None:
        return html.P("Select an asset class and plot to view data.", style={'textAlign': 'center', 'color': const.BRIGHTER_TEXT_COLOR})

    if selected_assets is None:
        assets = cotIndexer.get_assets_for_asset_class(asset_class)
    elif selected_assets:
        assets = selected_assets  # Use specific user selections if provided
    else:
        assets = cotIndexer.get_assets_for_asset_class(asset_class)

    num_cols = int(num_cols)
    num_selected = len(selected_plots) * len(assets)
    num_rows = math.ceil(num_selected / num_cols)

    min_threshold, max_threshold = utils.parse_setup_thresholds(setup)
    color_palette = cotIndexer.get_palette(palette_name)

    titles = []
    for idx, asset in enumerate(assets):
        if idx == 0:
            titles.append(AVAILABLE_PLOTS[selected_plot] + ":  " + asset)
        else:
            titles.append(asset)

    # Define specs based on selection
    specs = []
    plot_idx = 0
    for r in range(num_rows):
        row_specs = []
        for c in range(num_cols):
            if plot_idx < num_selected:
                p = selected_plots[0]
                # Most plots use secondary_y for Price or OI overlays
                has_secondary = p in ["oi_pct", "willco", "spearman", "net_pos", "index", "zscore", "momentum", "tension"]
                # for idx in range(len(assets)):
                row_specs.append({"secondary_y": has_secondary})
                plot_idx += 1
            else:
                row_specs.append(None) # Empty cell in grid
        specs.append(row_specs)

    fig = helpers.get_make_subplots_for_plots(num_rows, num_cols, titles, specs)

    plot_idx = 0
    for r in range(1, num_rows + 1):
        for c in range(1, num_cols + 1):
            if plot_idx < num_selected:
                df = cotIndexer.get_symbols_data(assets[plot_idx], lookback)
                if df is None:
                    return helpers.get_no_data_html_p()

                p = selected_plots[0]
                setup_highlight_row = None # r if p == "index" else None

                if p == "oi_pct":
                    fig = helpers.get_open_interest_percent_plot(fig, df, r, c, color_palette)
                elif p == "willco":
                    fig = helpers.get_willco_plot(fig, df, r, c, color_palette)
                elif p == "spearman":
                    fig = helpers.get_spearman_plot(fig, df, r, c, color_palette)
                elif p == "net_pos":
                    fig = helpers.get_net_pos_plot(fig, df, r, c, color_palette)
                elif p == "index":
                    fig = helpers.get_index_plot(fig, df, r, c, color_palette, min_threshold, max_threshold)
                elif p == "zscore":
                    fig = helpers.get_zscore_plot(fig, df, r, c, color_palette)
                elif p == "momentum":
                    fig = helpers.get_momentum_plot(fig, df, r, c, color_palette)
                elif p == "tension":
                    fig = helpers.get_tension_plot(fig, df, r, c, color_palette)

                if setup_highlight_row:
                    helpers.get_setup_highlighting(fig, df, min_threshold, max_threshold, r, c)

                plot_idx += 1

    fig = helpers.get_update_xaxes_for_plots(fig, df)
    fig = helpers.get_update_layout_for_plots(fig, num_rows, num_cols)

    return dcc.Graph(figure=fig,
                     config={
                        'scrollZoom': False,
                        'doubleClick': 'reset',
                        'displayModeBar': True,
                        'modeBarButtonsToRemove': ['pan2d', 'select2d', 'lasso2d'],
                        'displayLogo': False,
                        'responsive': True},
                        style={'width': '100%'
                    })


@callback(
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


@callback(
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


@callback(
    [Output('graphs_multi_equity_selector_input', 'options'),
     Output('graphs_multi_equity_selector_input', 'value')],
    Input('graphs_single_asset_class_input', 'value')
)
def update_multi_asset_dropdown_options(selected_class):
    if not selected_class:
        return [], None
    assets = cotIndexer.get_assets_for_asset_class(selected_class)
    options = [{'label': x, 'value': x} for x in assets]
    return options, assets
