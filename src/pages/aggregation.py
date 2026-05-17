import constants as const
import pages.helpers as helpers
import utils
from indexer import cotIndexer

import dash
import dash_bootstrap_components as dbc
import math
import plotly.graph_objects as go
import pandas as pd

from dash import State, html, dcc, Input, Output, callback
from plotly.subplots import make_subplots

dash.register_page(
    __name__,
    path='/aggregation',
    name='Aggregation'
)

AVAILABLE_PLOTS = {
    "oi_pct": "Net Positions % of OI",
    "net_pos": "Net Positions (Sum)",
    "index": "Positioning Index (Average)",
    "zscore": "Positioning Z-Score (Average)",
}

layout = html.Div([
    dbc.Container([
        dbc.Accordion([
            dbc.AccordionItem([
                dbc.Row([
                    dbc.Col([
                        html.Label("Lookback:", style=const.label_style),
                        dbc.Select(
                            id='agg_lookback_selector',
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
                            id='agg_asset_class_input',
                            options=[{'label': x, 'value': x}
                                     for x in cotIndexer.get_asset_classes()],
                            value=f"{cotIndexer.get_default_asset_class()}",
                            className="mb-3 bg-dark text-white border-secondary",
                        ),
                    ], xs=12, md="auto"),

                    dbc.Col([
                        html.Label("Assets to Aggregate", style=const.label_style),
                        dcc.Dropdown(
                            persistence=True,
                            id='agg_assets_input',
                            multi=True,
                            className="mb-3 dash-dropdown bg-dark text-white",
                            searchable=False,
                            clearable=True,
                            style={'minWidth': '300px'}
                        ),
                    ], xs=12, md=4),

                    dbc.Col([
                        html.Label("Columns:", style=const.label_style),
                        dbc.Select(
                            id='agg_columns_selector',
                            persistence=True,
                            options=[
                                {"label": "1 Column", "value": "1"},
                                {"label": "2 Columns", "value": "2"},
                                {"label": "3 Columns", "value": "3"},
                            ],
                            value="1",
                            size="sm",
                            className="mb-3 bg-dark text-white border-secondary",
                        )
                    ], xs=6, md="auto"),

                    dbc.Col([
                        html.Label("Visible Aggregations", style=const.label_style),
                        dcc.Dropdown(
                            persistence=True,
                            id='agg_plot_selector',
                            options=[{'label': v, 'value': k} for k, v in AVAILABLE_PLOTS.items()],
                            value=list(AVAILABLE_PLOTS.keys()),  # Default to all selected
                            multi=True,
                            className="mb-3 dash-dropdown bg-dark text-white",
                            style={'minWidth': '250px'}
                        ),
                    ], xs=12, md=4),
                ], align="center"),
            ],
            title="AGGREGATION CONFIGURATION",
            item_id="agg_config"),
        ],
        start_collapsed=True,
        flush=True,
        className="mb-3",
        style={'backgroundColor': const.BACKGROUND_COLOR}),

        html.Hr(style=const.hr_style),

        dbc.Row([
            dcc.Loading(
                id="loading-agg-graph",
                type="default",  # Options: "graph", "cube", "circle", "dot", or "default"
                children=html.Div(id='agg_stack'),
                color=const.BRIGHTER_TEXT_COLOR
            )
        ], justify='center')
    ], fluid=True),
])


@callback(
    Output('global_lookback_store', 'data'),
    Input('agg_lookback_selector', 'value')
)
def update_global_lookback(value):
    if value == "26" or value == "52" or value == "Custom":
        return value
    else:
        return "Custom"


@callback(
    Output('agg_lookback_selector', 'value'),
    Input('global_lookback_store', 'data')
)
def update_local_lookback(value):
    if value == "26" or value == "52" or value == "Custom":
        return value
    else:
        return "Custom"


@callback(
    [Output('agg_assets_input', 'options'),
     Output('agg_assets_input', 'value')],
    Input('agg_asset_class_input', 'value')
)
def update_agg_asset_dropdown_options(selected_class):
    """Callback to populate assets based on selected class and reset selected assets"""
    if not selected_class:
        return [], None
    assets = cotIndexer.get_assets_for_asset_class(selected_class)
    options = [{'label': x, 'value': x} for x in assets]
    return options, assets


@callback(
    Output('agg_columns_selector', 'value'),
    Input('url', 'pathname'),  # Triggers on page load
    State('agg_columns_selector', 'value')
)
def set_default_columns(pathname, current_val):
    # Only set default if it hasn't been changed by the user (initial load)
    if utils.is_mobile():
        return "1"
    else:
        return "2"  # Default for larger screens


@callback(
    Output('agg_stack', 'children'),
    Input('session_palette_theme_asset_store', 'data'),
    Input('agg_assets_input', 'value'),
    Input('global_lookback_store', 'data'),
    Input('agg_plot_selector', 'value'),
    Input('agg_columns_selector', 'value'),
    Input('agg_asset_class_input', 'value')
)
def update_agg_stack(palette_name, selected_assets, lookback, selected_plots, num_cols, asset_class):
    utils.cot_logger.info(f"Updating aggregation stack with assets={selected_assets}, lookback={lookback}, selected_plots={selected_plots}, num_cols={num_cols}")

    if not selected_assets or len(selected_assets) == 0:
        return html.P("SELECT ASSETS TO AGGREGATE", style={'textAlign': 'center', 'color': const.BRIGHTER_TEXT_COLOR})
    if not selected_plots or len(selected_plots) == 0:
        return html.P("SELECT PLOTS TO RENDER", style={'textAlign': 'center', 'color': const.BRIGHTER_TEXT_COLOR})

    # Fetch dynamic colors from user's current session state
    color_palette = cotIndexer.get_palette(palette_name)

    # Fetch data for all selected assets
    dataframes = []
    for asset in selected_assets:
        df = cotIndexer.get_symbols_data(asset, lookback)
        if df is not None and not df.empty:
            df = df.copy()
            df['Asset'] = asset
            dataframes.append(df)

    if not dataframes:
        return html.P("No Data Found", style={'textAlign': 'center', 'color': const.BRIGHTER_TEXT_COLOR})

    # Combine and Aggregate
    combined_df = pd.concat(dataframes)
    grouped = combined_df.groupby(level=0)

    agg_df = pd.DataFrame()

    # Sum absolute positions
    agg_df[const.COMM_NET] = grouped[const.COMM_NET].sum()
    agg_df[const.LARGE_NET] = grouped[const.LARGE_NET].sum()
    agg_df[const.SMALL_NET] = grouped[const.SMALL_NET].sum()
    agg_df[const.OPEN_INTEREST] = grouped[const.OPEN_INTEREST].sum()
    agg_df[const.COMM_PCT_OI] = round(agg_df[const.COMM_NET] / (agg_df[const.OPEN_INTEREST] + 1e-9) * 100, 2)
    agg_df[const.LARGE_PCT_OI] = round(agg_df[const.LARGE_NET] / (agg_df[const.OPEN_INTEREST] + 1e-9) * 100, 2)
    agg_df[const.SMALL_PCT_OI] = round(agg_df[const.SMALL_NET] / (agg_df[const.OPEN_INTEREST] + 1e-9) * 100, 2)

    # Average Oscillators and Z-Scores
    agg_df['comms_zscore'] = round(grouped['comms_zscore'].mean(), 4)
    agg_df['lrg_zscore'] = round(grouped['lrg_zscore'].mean(), 4)
    agg_df['sml_zscore'] = round(grouped['sml_zscore'].mean(), 4)

    agg_df['comms_idx'] = round(grouped['comms_idx'].mean(), 0)
    agg_df['lrg_idx'] = round(grouped['lrg_idx'].mean(), 0)
    agg_df['sml_idx'] = round(grouped['sml_idx'].mean(), 0)

    # Dynamic Subplot Layout Configuration
    num_cols = int(num_cols)
    num_selected = len(selected_plots)
    num_rows = math.ceil(num_selected / num_cols)
    titles = [AVAILABLE_PLOTS[p] for p in selected_plots]

    specs = []
    plot_idx = 0
    for r in range(1, num_rows + 1):
        row_specs = []
        for c in range(1, num_cols + 1):
            if plot_idx < num_selected:
                p = selected_plots[plot_idx]
                has_secondary = p in ["net_pos", "net_pos_normalized"]
                row_specs.append({"secondary_y": has_secondary})
                plot_idx += 1
            else:
                row_specs.append(None)
        specs.append(row_specs)

    fig = helpers.get_make_subplots_for_plots(num_rows, num_cols, titles, specs)

    plot_idx = 0
    for r in range(1, num_rows + 1):
        for c in range(1, num_cols + 1):
            if plot_idx < num_selected:
                p = selected_plots[plot_idx]
                if p == "oi_pct":
                    fig = helpers.get_open_interest_percent_plot(fig, agg_df, r, c, color_palette, show_price=False)

                elif p == "net_pos":
                    fig = helpers.get_net_pos_plot(fig, agg_df, const.COMM_NET, const.LARGE_NET, const.SMALL_NET, r, c, color_palette, show_price=False)

                elif p == "zscore":
                    fig = helpers.get_zscore_plot(fig, agg_df, r, c, color_palette, show_price=False)

                elif p == "index":
                    fig = helpers.get_index_plot(fig, agg_df, 'comms_idx', 'lrg_idx', 'sml_idx', r, c, color_palette, show_price=False)

                plot_idx += 1

    helpers.get_update_xaxes_for_plots(fig, agg_df)
    helpers.get_update_layout_for_plots(fig, num_rows, num_cols, asset_class)

    return dcc.Graph(figure=fig, config={'displayModeBar': False}, style={'width': '100%'})
