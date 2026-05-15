import constants as const
import pages.helpers as helpers
import utils
from indexer import cotIndexer

import dash
import dash_bootstrap_components as dbc
import math
import plotly.graph_objects as go

from dash import State, html, dcc, Input, Output, callback
from plotly.subplots import make_subplots


# Register this file as a page
dash.register_page(
    __name__,
    path='/analysis'
)

AVAILABLE_PLOTS = {
    "oi_pct": "Net Position % of OI",
    "willco": "WillCo",
    "spearman": "Spearman Correlation",
    "net_pos": "Net Positions",
    "net_pos_normalized": "Net Positions Normalized",
    "index": "Positioning Index",
    "index_normalized": "Positioning Index Normalized",
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
                            id='analysis_lookback_selector',
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
                            id='analysis_single_asset_class_input',
                            options=[{'label': x, 'value': x}
                                    for x in cotIndexer.get_asset_classes()],
                            value=f"{cotIndexer.get_default_asset_class()}",
                            className="mb-3 bg-dark text-white border-secondary",
                        ),
                    ], xs=12, md="auto"),

                    dbc.Col([
                        html.Label("Asset Selector", style=const.label_style),
                        dbc.Select(
                            persistence=True,
                            id='analysis_single_asset_filter_input',
                            className="mb-3 bg-dark text-white border-secondary",
                        ),
                    ], xs=12, md="auto"),

                    dbc.Col([
                        html.Label("Columns:", style=const.label_style),
                        dbc.Select(
                            id='analysis_columns_selector',
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
                        html.Label("Visible Plots", style=const.label_style),
                        dcc.Dropdown(
                            persistence=True,
                            id='analysis_plot_selector',
                            options=[{'label': v, 'value': k} for k, v in AVAILABLE_PLOTS.items()],
                            value=list(AVAILABLE_PLOTS.keys()),  # Default to all selected
                            multi=True,
                            className="mb-3 dash-dropdown bg-dark text-white",
                            style={'minWidth': '250px'}
                        ),
                    ], xs=12, md=4),

                    dbc.Col([
                        html.Label("Price Overlay", style=const.label_style),
                        dbc.RadioItems(
                            id='analysis_price_overlay_radio',
                            options=[
                                {"label": "On", "value": True},
                                {"label": "Off", "value": False},
                            ],
                            value=True, # Default to showing the price
                            inline=True,
                            className="mb-3",
                            style={'color': const.TEXT_COLOR}
                        )
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
                id="loading-analysis-graph",
                type="default", # Options: "graph", "cube", "circle", "dot", or "default"
                children=html.Div(id='analysis_stack'),
                color=const.BRIGHTER_TEXT_COLOR
            )
        ], justify='center')
    ], fluid=True),
])


@callback(
    Output('global_lookback_store', 'data'),
    Input('analysis_lookback_selector', 'value')
)
def update_global_lookback(value):
    if value == "26" or value == "52" or value == "Custom":
        return value
    else:
        return "Custom"

@callback(
    Output('analysis_lookback_selector', 'value'),
    Input('global_lookback_store', 'data')
)
def update_local_lookback(value):
    if value == "26" or value == "52" or value == "Custom":
        return value
    else:
        return "Custom"


@callback(
    [Output('analysis_single_asset_filter_input', 'options'),
     Output('analysis_single_asset_filter_input', 'value')],
    Input('analysis_single_asset_class_input', 'value')
)
def update_asset_dropdown_options(selected_class):
    if not selected_class:
        return [], None
    assets = cotIndexer.get_assets_for_asset_class(selected_class)
    assets.sort()
    options = [{'label': x, 'value': x} for x in assets]
    default_value = options[0].get('value') if options else None
    return options, default_value


@callback(
    Output('analysis_page_header', 'children'),
    [Input('analysis_single_asset_class_input', 'value'),
     Input('analysis_single_asset_filter_input', 'value'),
     Input('global_lookback_store', 'data')]
)
def update_analysis_header(asset_class, asset_name, lookback):
    if not asset_name:
        return html.H6("SELECT ASSET", style={'color': const.TEXT_COLOR})

    # Fetch latest data point
    df = cotIndexer.get_symbols_data(asset_name, lookback)
    if df is None or df.empty:
        return html.H6(f"{asset_class} | {asset_name}", style={'color': const.BRIGHTER_TEXT_COLOR})

    # Get the latest Z-score (using the column name from your DataFrame)
    latest_z = df['comms_zscore'].iloc[-1]

    # Determine color logic based on your 95/5 (Z=2.0) setup
    z_color = "#4ade80" if latest_z >= 2.0 else "#f87171" if latest_z <= -2.0 else const.TEXT_COLOR

    return [
        html.Div([
            html.Span("CURRENT COMMERCIAL Z-SCORE: ", style={'color': const.BRIGHTER_TEXT_COLOR, 'fontSize': '0.9rem'}),
            html.Span(f"{latest_z:.2f}", style={'color': z_color, 'fontSize': '1.1rem', 'fontWeight': 'bold'})
        ])
    ]


@callback(
    Output('analysis_columns_selector', 'value'),
    Input('url', 'pathname'), # Triggers on page load
    State('analysis_columns_selector', 'value')
)
def set_default_columns(pathname, current_val):
    # Only set default if it hasn't been changed by the user (initial load)
    if utils.is_mobile():
        return "1"
    else:
        return "2" # Default for larger screens


@callback(
    Output('analysis_stack', 'children'),
    [Input('session_palette_theme_asset_store', 'data'),
     Input('analysis_single_asset_filter_input', 'value'),
     Input('session_setup_highlight_asset_store', 'data'),
     Input('global_lookback_store', 'data'),
     Input('analysis_plot_selector', 'value'),
     Input('analysis_columns_selector', 'value'),
     Input('analysis_price_overlay_radio', 'value')]
)
def update_analysis_stack(palette_name, asset, setup, lookback, selected_plots, num_cols, price_overlay):
    utils.cot_logger.info(f"Updating analysis stack with asset={asset}, setup={setup}, lookback={lookback}, selected_plots={selected_plots}, num_cols={num_cols}, price_overlay={price_overlay}")

    if not asset or not selected_plots or selected_plots == 0:
        return html.P("SELECT ASSET AND PLOTS", style={'textAlign': 'center', 'color': const.BRIGHTER_TEXT_COLOR})

    df = cotIndexer.get_symbols_data(asset, lookback)
    if df is None:
        return html.P("No Data", style={'textAlign': 'center', 'color': const.BRIGHTER_TEXT_COLOR})

    min_threshold, max_threshold = utils.parse_setup_thresholds(setup)
    color_palette = cotIndexer.get_palette(palette_name)
    titles = [AVAILABLE_PLOTS[p] for p in selected_plots]

    num_cols = int(num_cols)
    num_selected = len(selected_plots)
    if not price_overlay:
        num_selected += 1  # Account for the separate price plot when overlay is off
        titles.insert(1, "Price")  # Add price title if overlay is on
        selected_plots.insert(1, "price")  # We'll add the price as a separate plot if overlay is off
    num_rows = math.ceil(num_selected / num_cols)

    # Define specs based on selection
    specs = []
    plot_idx = 0
    for r in range(num_rows):
        row_specs = []
        for c in range(num_cols):
            if plot_idx < num_selected:
                p = selected_plots[plot_idx]
                # Most plots use secondary_y for Price or OI overlays
                has_secondary = p in ["oi_pct", "willco", "spearman", "index",
                                      'index_normalized', "zscore", "momentum",
                                      "tension"] and price_overlay
                has_secondary = has_secondary or p in ["net_pos",
                                                       "net_pos_normalized",
                                                       "price"]
                row_specs.append({"secondary_y": has_secondary})
                plot_idx += 1
            else:
                row_specs.append(None)  # Empty cell in grid
        specs.append(row_specs)

    fig = helpers.get_make_subplots_for_plots(num_rows, num_cols, titles, specs)

    plot_idx = 0
    for r in range(1, num_rows + 1):
        for c in range(1, num_cols + 1):
            if plot_idx < num_selected:
                p = selected_plots[plot_idx]
                setup_highlight_row = None  # r if p == "index" else None

                if p == "price":
                    fig = helpers.get_price_plot(fig, df, r, c, color_palette)
                elif p == "oi_pct":
                    fig = helpers.get_open_interest_percent_plot(fig, df, r, c, color_palette, price_overlay)
                elif p == "willco":
                    fig = helpers.get_willco_plot(fig, df, r, c, color_palette, price_overlay)
                elif p == "spearman":
                    fig = helpers.get_spearman_plot(fig, df, r, c, color_palette, price_overlay)
                elif p == "net_pos":
                    fig = helpers.get_net_pos_plot(fig, df, const.COMM_NET, const.LARGE_NET, const.SMALL_NET, r, c, color_palette, price_overlay)
                elif p == "net_pos_normalized":
                    fig = helpers.get_net_pos_plot(fig, df, const.COMM_NET_NORM, const.LARGE_NET_NORM, const.SMALL_NET_NORM, r, c, color_palette, show_price=price_overlay)
                elif p == "index":
                    fig = helpers.get_index_plot(fig, df, "comms_idx", "lrg_idx", "sml_idx", r, c, color_palette, min_threshold, max_threshold, price_overlay)
                elif p == "index_normalized":
                    fig = helpers.get_index_plot(fig, df, "comms_norm_idx", "lrg_norm_idx", "sml_norm_idx", r, c, color_palette, min_threshold, max_threshold, price_overlay)
                elif p == "zscore":
                    fig = helpers.get_zscore_plot(fig, df, r, c, color_palette, min_threshold, max_threshold, price_overlay)
                elif p == "momentum":
                    fig = helpers.get_momentum_plot(fig, df, r, c, color_palette, price_overlay)
                elif p == "tension":
                    fig = helpers.get_tension_plot(fig, df, r, c, color_palette, price_overlay)

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
                        'responsive': True},
                        style={'width': '100%'
                    })
