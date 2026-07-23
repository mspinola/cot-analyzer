import math

import cotmetrics.constants as const
import cotmetrics.utils as utils
import dash
import dash_bootstrap_components as dbc
import pandas as pd
from cotmetrics.indexer import get_indexer
from dash import Input, Output, State, callback, clientside_callback, dcc, html, no_update

import app_utils
import components.plot_helpers as helpers
import components.plot_registry as registry
import viz_config
import viz_constants as vc

dash.register_page(
    __name__,
    path='/aggregation',
    name='Aggregation'
)

PLOT_IDS = ["oi_pct", "net_pos", "index", "zscore"]

# This page draws one frame aggregated across several assets, so a panel means something
# slightly different here and says so. The registry's default labels describe a single
# instrument.
AVAILABLE_PLOTS = registry.labels_for(PLOT_IDS, overrides={
    "oi_pct": "Net Positions % of OI",
    "net_pos": "Net Positions (Sum)",
    "index": "Positioning Index (Average)",
    "zscore": "Positioning Z-Score (Average)",
})


def layout(**kwargs):
    # Built per request, not at import. Resolving these at module scope
    # made importing this page require a populated COTDATA_STORE.
    asset_classes = sorted(get_indexer().get_asset_classes())

    return html.Div([
        dbc.Container([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            html.H6("Class", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dbc.RadioItems(
                                id='agg_asset_class_selector',
                                persistence='session',
                                options=[{'label': c, 'value': c} for c in asset_classes],
                                value=get_indexer().get_default_asset_class(),
                                inline=True,
                                className="mb-3 p-1 rounded text-white",
                                style={'backgroundColor': 'black', 'border': '1px solid #6c757d'},
                                labelStyle={'color': 'white', 'marginRight': '0px', 'marginLeft': '0px', 'fontSize': '0.85rem'},
                                inputStyle={'opacity': '0.6'}
                            )
                        ], xs=12, md="auto"),

                        dbc.Col([
                            html.H6("Assets to Aggregate", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dcc.Dropdown(
                                persistence='session',
                                id='agg_assets_input',
                                options=[{'label': m, 'value': m} for m in sorted(get_indexer().get_assets_for_asset_class(get_indexer().get_default_asset_class()))],
                                multi=True,
                                className="mb-3 dash-dropdown bg-dark text-white",
                                searchable=True,
                                clearable=True,
                                style={'width': '200px'}
                            ),
                        ], xs=12, md="auto"),

                    ]),

                    dbc.Row([
                        dbc.Col([
                            html.H6("Visible Aggregations", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dcc.Dropdown(
                                persistence=True,
                                id='agg_plot_selector',
                                options=[{'label': v, 'value': k} for k, v in AVAILABLE_PLOTS.items()],
                                value=list(AVAILABLE_PLOTS.keys()),
                                multi=True,
                                className="mb-3 dash-dropdown bg-dark text-white",
                                searchable=False,
                                clearable=True,
                                style={'width': '200px'}
                            ),
                        ], xs=12, md="auto"),
                        dbc.Col([
                            html.H6("Lookback", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dbc.Select(
                                id='agg_lookback_selector',
                                persistence='session',
                                options=[
                                    {"label": "26 Weeks", "value": "26"},
                                    {"label": "52 Weeks", "value": "52"},
                                    {"label": "Custom", "value": "Custom"},
                                ],
                                value="Custom",
                                className="mb-3 bg-dark text-white border-secondary",
                                style={'width': '120px'}
                            )
                        ], xs=12, md="auto"),

                        dbc.Col([
                            html.H6("Cols", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dbc.Select(
                                id='agg_columns_selector',
                                persistence='session',
                                options=[
                                    {"label": "1", "value": "1"},
                                    {"label": "2", "value": "2"},
                                    {"label": "3", "value": "3"},
                                ],
                                value="1",
                                className="mb-3 bg-dark text-white border-secondary",
                                style={'width': '70px'}
                            )
                        ], xs=12, md="auto"),
                    ]),
                ])
            ], style={'backgroundColor': 'var(--card-color)', 'borderColor': vc.GRID_COLOR}, className="mb-4 mt-2"),

            # The browser writes the fitted zoom window here. Nothing on this page reads it,
            # but the shared autoscale needs an Output to hang the callback on.
            dcc.Store(id='agg_zoom_sink'),

            dbc.Row([
                dcc.Loading(
                    id="loading-agg-graph",
                    type="default",
                    children=html.Div(id='agg_stack'),
                    color=vc.BRIGHTER_TEXT_COLOR
                )
            ], justify='center')
        ], fluid=True),
    ])


# Rescale the y-axes to whatever the x-window is showing. Pure arithmetic over data the
# browser already holds, so it runs there. Shared with the other stacked-plot pages, which
# is why the graph id travels as State. See autoscale_y_axes in assets/clientside.js.
#
# This page hides the mode bar, so there is no Reset Axes button. Plotly's default
# double-click still resets, and the autoscale handles that path the same way.
clientside_callback(
    "window.dash_clientside.clientside.autoscale_y_axes",
    Output('agg_zoom_sink', 'data'),
    Input('aggregation_main_graph', 'relayoutData'),
    State('aggregation_main_graph', 'id'),
    prevent_initial_call=True
)


@callback(
    Output('global_lookback_store', 'data', allow_duplicate=True),
    Input('agg_lookback_selector', 'value'),
    State('global_lookback_store', 'data'),
    prevent_initial_call=True
)
def update_global_lookback(value, current_store_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_store_val:
        return no_update
    return new_val


@callback(
    Output('agg_lookback_selector', 'value'),
    Input('global_lookback_store', 'data'),
    State('agg_lookback_selector', 'value')
)
def update_local_lookback(value, current_local_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_local_val:
        return no_update
    return new_val


@callback(
    Output('agg_columns_selector', 'value'),
    Input('url', 'pathname'),
    State('agg_columns_selector', 'value')
)
def set_default_columns(pathname, current_val):
    # Only set default if it hasn't been changed by the user (initial load)
    if app_utils.is_mobile():
        new_val = "1"
    elif current_val in ["1", "2", "3"]:
        new_val = current_val  # User has already made a selection, keep it
    else:
        new_val = "2"  # Default for larger screens

    # CRITICAL: Don't cascade the change if the value didn't actually change
    # Prevents calculating all of the plots twice
    if new_val == current_val:
        return no_update

    return new_val


@callback(
    Output('agg_stack', 'children'),
    Input('session_palette_theme_asset_store', 'data'),
    Input('agg_assets_input', 'value'),
    Input('global_lookback_store', 'data'),
    Input('agg_plot_selector', 'value'),
    Input('agg_columns_selector', 'value')
)
def update_agg_stack(palette_name, selected_assets, lookback, selected_plots, num_cols):
    print(f"Updating aggregation stack with assets={selected_assets}, lookback={lookback}, selected_plots={selected_plots}, num_cols={num_cols}")
    utils.cot_logger.info(f"Updating aggregation stack with assets={selected_assets}, lookback={lookback}, selected_plots={selected_plots}, num_cols={num_cols}")
    if not lookback:
        lookback = "Custom"

    if not selected_assets or len(selected_assets) == 0:
        return html.P("SELECT ASSETS TO AGGREGATE", style={'textAlign': 'center', 'color': vc.BRIGHTER_TEXT_COLOR})
    if not selected_plots or len(selected_plots) == 0:
        return html.P("SELECT PLOTS TO RENDER", style={'textAlign': 'center', 'color': vc.BRIGHTER_TEXT_COLOR})

    # Fetch dynamic colors from user's current session state
    color_palette = viz_config.get_palette(palette_name)

    # Fetch data for all selected assets
    dataframes = []
    for asset in selected_assets:
        df = get_indexer().get_symbols_data(asset, lookback)
        if df is not None and not df.empty:
            df = df.copy()
            df.attrs = {}  # Clear attributes to avoid truth value ambiguity in pd.concat
            df['Asset'] = asset
            dataframes.append(df)

    if not dataframes:
        return html.P("No Data Found", style={'textAlign': 'center', 'color': vc.BRIGHTER_TEXT_COLOR})

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
    agg_df[const.COMMS_ZSCORE] = round(grouped[const.COMMS_ZSCORE].mean(), 4)
    agg_df[const.LRG_ZSCORE] = round(grouped[const.LRG_ZSCORE].mean(), 4)
    agg_df[const.SML_ZSCORE] = round(grouped[const.SML_ZSCORE].mean(), 4)
    agg_df[const.OI_ZSCORE] = round(grouped[const.OI_ZSCORE].mean(), 4)

    agg_df[const.COMMS_IDX] = round(grouped[const.COMMS_IDX].mean(), 0)
    agg_df[const.LRG_IDX] = round(grouped[const.LRG_IDX].mean(), 0)
    agg_df[const.SML_IDX] = round(grouped[const.SML_IDX].mean(), 0)

    # Dynamic Subplot Layout Configuration
    num_cols = int(num_cols)
    num_selected = len(selected_plots)
    num_rows = math.ceil(num_selected / num_cols)
    titles = [AVAILABLE_PLOTS[p] for p in selected_plots]

    # No price overlay on this page. Net Positions still takes a secondary axis, because
    # what rides there is Open Interest rather than price.
    specs = registry.subplot_specs(selected_plots, show_price=False, num_cols=num_cols)

    fig = helpers.get_make_subplots_for_plots(num_rows, num_cols, titles, specs)

    plot_idx = 0
    for r in range(1, num_rows + 1):
        for c in range(1, num_cols + 1):
            if plot_idx < num_selected:
                p = selected_plots[plot_idx]
                # No model: a positioning gate reads a single instrument against its own
                # history, and this frame is an average across several. So the index
                # panel draws its lines without a band, as it did before.
                ctx = registry.PlotCtx(
                    fig=fig, df=agg_df, row=r, col=c, palette=color_palette,
                    show_price=False, model=None,
                    net_cols=(const.COMM_NET, const.LARGE_NET, const.SMALL_NET))
                fig = registry.REGISTRY[p].build(ctx) or fig

                plot_idx += 1

    helpers.get_update_xaxes_for_plots(fig, agg_df)
    helpers.get_update_layout_for_plots(fig, num_rows, num_cols, "Custom Aggregation")

    return dcc.Graph(
        id='aggregation_main_graph',
        figure=fig,
        config={'displayModeBar': False},
        style={'width': '100%'}
    )

@callback(
    Output('agg_assets_input', 'options'),
    Output('agg_assets_input', 'value'),
    Input('agg_asset_class_selector', 'value'),
    State('agg_assets_input', 'value')
)
def update_agg_asset_options(selected_class, current_assets):
    if not selected_class:
        selected_class = get_indexer().get_default_asset_class()

    assets = sorted(get_indexer().get_assets_for_asset_class(selected_class))
    options = [{'label': m, 'value': m} for m in assets]

    # We strictly enforce single class aggregation
    valid_assets = [a for a in (current_assets or []) if a in assets]

    if not valid_assets and assets:
        valid_assets = [assets[0]]

    return options, valid_assets
