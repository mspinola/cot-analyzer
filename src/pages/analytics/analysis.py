import math

import cotmetrics.constants as const
import cotmetrics.models as models
import cotmetrics.utils as utils
import dash
import dash_bootstrap_components as dbc
from cotmetrics.indexer import get_indexer
from dash import Input, Output, State, callback, clientside_callback, dcc, html, no_update

import app_utils
import components.plot_helpers as helpers
import components.plot_registry as registry
import viz_config
import viz_constants as vc

# Register this file as a page
dash.register_page(
    __name__,
    path='/analysis'
)

# Which panels this page offers, in stack order. Everything about them beyond the
# order comes from the registry.
PLOT_IDS = ["price_candles", "macd", "willco", "index", "momentum", "zscore",
            "net_pos", "oi_pct", "spearman", "lrg_sentiment", "max_pain",
            "max_pain_historical"]

# Basis variants offered as extra selectable panels rather than a page-wide control, so
# a raw and a normalized read of the same metric can be stacked and compared directly.
# BASIS_VARIANTS maps the variant's plot id -> (base plot id, basis view).
#
# Which metrics get siblings is not a fact about this page: it is exactly the set the
# basis moves, so it comes from the registry rather than a second list here that could
# disagree with it. Base ids keep their original keys so session-persisted selections
# survive; a base gains "(Raw)" in its label only once it has siblings to be told apart
# from.
#
# BASE_PLOTS is what the selector defaults to. The variants are deliberately left out:
# sweeping them in would triple a fresh session's stack height for no one who asked.
BASE_PLOTS = {}
BASIS_VARIANTS = {}
AVAILABLE_PLOTS = {}
for _id in PLOT_IDS:
    _spec = registry.REGISTRY[_id]
    BASE_PLOTS[_id] = f"{_spec.label} (Raw)" if _spec.basis_aware else _spec.label
    AVAILABLE_PLOTS[_id] = BASE_PLOTS[_id]
    if not _spec.basis_aware:
        continue
    # Keep each metric's variants next to it in the picker rather than in a clump at the
    # bottom -- they're chosen together.
    BASIS_VARIANTS[f"{_id}_oinorm"] = (_id, const.BASIS_OI_NORM)
    AVAILABLE_PLOTS[f"{_id}_oinorm"] = f"{_spec.label} (% of OI)"
    # Net Positions gets no overlay: contracts and a fraction of OI share no scale.
    if _spec.overlay is not None:
        BASIS_VARIANTS[f"{_id}_both"] = (_id, vc.BASIS_BOTH)
        AVAILABLE_PLOTS[f"{_id}_both"] = f"{_spec.label} (Raw vs %OI)"


def resolve_basis_plot(plot_id, default_basis=const.BASIS_RAW):
    """Plot id -> (base plot id, basis view).

    An explicit variant names its own basis and always wins. A plain id follows the
    app's positioning model, so switching the model moves the default panels without
    disturbing a variant someone selected on purpose to compare against.
    """
    return BASIS_VARIANTS.get(plot_id, (plot_id, default_basis))




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
                            html.H6("Asset Class", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dbc.RadioItems(
                                id='analysis_asset_class_selector',
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
                            html.H6("Asset Selector", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dbc.Select(
                                persistence='session',
                                id='analysis_single_asset_filter_input',
                                options=[{'label': m, 'value': m} for m in sorted(get_indexer().get_assets_for_asset_class(get_indexer().get_default_asset_class()))],
                                className="mb-3 bg-dark text-white border-secondary",
                                style={'width': '200px'}
                            ),
                        ], xs=12, md="auto"),

                    ]),

                    dbc.Row([
                        dbc.Col([
                            html.H6("Visible Plots", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dcc.Dropdown(
                                persistence=True,
                                id='analysis_plot_selector',
                                options=[{'label': v, 'value': k} for k, v in AVAILABLE_PLOTS.items()],
                                value=list(BASE_PLOTS.keys()),
                                multi=True,
                                className="mb-3 dash-dropdown bg-dark text-white",
                                style={'width': '200px'}
                            ),
                        ], xs=12, md="auto"),
                        dbc.Col([
                            html.H6("Lookback", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dbc.Select(
                                id='analysis_lookback_selector',
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
                                id='analysis_columns_selector',
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

            html.Hr(style=vc.hr_style),

            # The browser writes the fitted zoom window here. Nothing on this page reads it,
            # but the shared autoscale needs an Output to hang the callback on.
            dcc.Store(id='analysis_zoom_sink'),

            html.Div([
                dbc.Row([
                    dcc.Loading(
                        id="loading-analysis-graph",
                        type="default",  # Options: "graph", "cube", "circle", "dot", or "default"
                        children=html.Div(id='analysis_stack'),
                        color=vc.BRIGHTER_TEXT_COLOR
                    )
                ], justify='center')
            ], style={"position": "relative", "width": "100%"})
        ], fluid=True),
    ])


# Rescale the y-axes to whatever the x-window is showing. Pure arithmetic over data the
# browser already holds, so it runs there. Shared with the other stacked-plot pages, which
# is why the graph id travels as State. See autoscale_y_axes in assets/clientside.js.
#
# It writes through Plotly rather than returning a figure: returning one would hand back
# the stored x-range and undo the zoom that triggered it.
clientside_callback(
    "window.dash_clientside.clientside.autoscale_y_axes",
    Output('analysis_zoom_sink', 'data'),
    Input('analysis_main_graph', 'relayoutData'),
    State('analysis_main_graph', 'id'),
    prevent_initial_call=True
)


@callback(
    Output('global_lookback_store', 'data', allow_duplicate=True),
    Input('analysis_lookback_selector', 'value'),
    State('global_lookback_store', 'data'),
    prevent_initial_call=True
)
def update_global_lookback(value, current_store_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_store_val:
        return no_update
    return new_val


@callback(
    Output('analysis_lookback_selector', 'value'),
    Input('global_lookback_store', 'data'),
    State('analysis_lookback_selector', 'value')
)
def update_local_lookback(value, current_local_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_local_val:
        return no_update
    return new_val



@callback(
    Output("analysis-tv-modal", "is_open"),
    Output("analysis-tv-iframe", "src"),
    Output("analysis-tv-modal-title", "children"),
    Input("analysis-open-tv-modal-btn", "n_clicks"),
    State("analysis-tv-modal", "is_open"),
    State("analysis_single_asset_filter_input", "value"),
    prevent_initial_call=True
)
def toggle_tv_modal(n_clicks, is_open, asset_name):
    utils.cot_logger.info(f"DEBUG toggle_tv_modal: n_clicks={n_clicks}, is_open={is_open}, asset_name={asset_name}")
    if not n_clicks or not asset_name:
        return is_open, "", ""

    # Get the TradingView symbol for this asset
    # (You may need to map your asset_name to the TV ticker format here)
    # e.g., mapping "S&P 500 Consolidated" -> "CME:ES1!"
    tv_symbol = viz_config.tv_chart_for_name(asset_name)

    # Fallback/cleanup if your symbols don't perfectly match TV's format
    if not tv_symbol:
        tv_symbol = get_indexer().get_instrument_symbol_from_name(asset_name)

    # Build the TradingView embed URL
    tv_url = f"https://s.tradingview.com/widgetembed/?symbol={tv_symbol}&interval=D&theme=dark&style=1&hidesidetoolbar=0&symboledit=1"

    # Return the new state: Toggle Modal, set URL, set Title
    return not is_open, tv_url, f"TradingView - {asset_name}"


@callback(
    Output('analysis_columns_selector', 'value'),
    Input('url', 'pathname'),
    State('analysis_columns_selector', 'value')
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
    Output('analysis_stack', 'children'),
    [Input('session_palette_theme_asset_store', 'data'),
     Input('analysis_single_asset_filter_input', 'value'),
     Input('global_lookback_store', 'data'),
     Input('analysis_plot_selector', 'value'),
     Input('analysis_columns_selector', 'value'),
     Input('global_model_store', 'data')]
)
def update_analysis_stack(palette_name, asset, lookback, selected_plots, num_cols, model_view):
    print(f"Updating analysis stack with asset={asset}, lookback={lookback}, selected_plots={selected_plots}, num_cols={num_cols}")
    utils.cot_logger.info(f"Updating analysis stack with asset={asset}, lookback={lookback}, selected_plots={selected_plots}, num_cols={num_cols}")

    show_price = True
    if not lookback:
        lookback = "Custom"

    selected_plots = registry.sanitize_selection(selected_plots, AVAILABLE_PLOTS)

    if not asset or not selected_plots or selected_plots == 0:
        return html.P("SELECT ASSET AND PLOTS", style={'textAlign': 'center', 'color': vc.BRIGHTER_TEXT_COLOR})

    # This page has no model selector of its own: its per-panel variants are the finer
    # control. The app model just decides what a *plain* panel means.
    app_model, _ = vc.resolve_model_view(model_view)
    def resolve(pid):
        return resolve_basis_plot(pid, app_model.basis)

    df = get_indexer().get_symbols_data(asset, lookback)
    if df is None:
        return html.P("No Data", style={'textAlign': 'center', 'color': vc.BRIGHTER_TEXT_COLOR})

    # Only pay for the normalized frame if a selected panel actually asks for it, or
    # the app model needs it to judge the asset title below.
    needs_norm = (any(resolve(p)[1] != const.BASIS_RAW for p in selected_plots)
                  or app_model.basis != const.BASIS_RAW)
    df_norm = get_indexer().get_symbols_data(asset, lookback, const.BASIS_OI_NORM) if needs_norm else None
    if needs_norm and df_norm is None:
        return html.P("No Data", style={'textAlign': 'center', 'color': vc.BRIGHTER_TEXT_COLOR})

    # Resolved per panel below, from that panel's own basis. A single page-wide band
    # was the bug: an OI-normalized index panel was shaded with the raw 95/5 CLS gate.
    color_palette = viz_config.get_palette(palette_name)
    instrument = get_indexer().get_instrument_from_name(asset)
    # This page names the basis in the picker label rather than in the title, since a
    # variant is a panel you chose by name. So the label is passed through and only the
    # options curves rewrite it, to name the ETF actually quoted.
    titles = [registry.plot_title(resolve(p)[0], asset=asset, instrument=instrument,
                                 label=AVAILABLE_PLOTS[p])
              for p in selected_plots]

    num_cols = int(num_cols)
    num_selected = len(selected_plots)
    num_rows = math.ceil(num_selected / num_cols)

    # A basis variant needs the same subplot spec as the metric it varies, so the grid
    # is built from resolved base ids rather than the selected variant ids.
    specs = registry.subplot_specs([resolve(p)[0] for p in selected_plots],
                                   show_price=show_price, num_cols=num_cols)

    is_shared_x = False if any(p in ["max_pain", "max_pain_historical"] for p in selected_plots) else True
    fig = helpers.get_make_subplots_for_plots(num_rows, num_cols, titles, specs, shared_xaxes=is_shared_x)

    plot_idx = 0
    for r in range(1, num_rows + 1):
        for c in range(1, num_cols + 1):
            if plot_idx < num_selected:
                p, basis_view = resolve(selected_plots[plot_idx])

                setup_comms_only = get_indexer().is_equity(asset)

                if basis_view == vc.BASIS_BOTH:
                    value_col, y_title, y_range, zero_line = registry.BASIS_OVERLAY_SPEC[p]
                    fig = helpers.get_basis_overlay_plot(
                        fig, df, df_norm, value_col, r, c, color_palette,
                        y_title=y_title, y_range=y_range, show_oi=show_price,
                        zero_line=zero_line)
                    plot_idx += 1
                    continue

                # Single-basis panels read the generic aliases, which already carry the
                # chosen basis, so they only need pointing at the right frame. The gate
                # comes from the same place: a panel drawn on the normalized basis is
                # judged by the model that owns it, never by the raw band.
                model = models.for_basis(basis_view)
                if basis_view == const.BASIS_OI_NORM:
                    comm_net, lrg_net, sml_net = const.COMM_NET_NORM, const.LARGE_NET_NORM, const.SMALL_NET_NORM
                    net_y_title = "net / OI"
                else:
                    comm_net, lrg_net, sml_net = const.COMM_NET, const.LARGE_NET, const.SMALL_NET
                    net_y_title = "net position"

                # Only the panels the basis actually moves follow the variant's frame.
                # The invariant ones stay on raw however the variant was selected, which
                # is the same rule that decides whether they get a sibling at all.
                spec = registry.REGISTRY[p]
                ctx = registry.PlotCtx(
                    fig=fig,
                    df=(df_norm if (spec.basis_aware and basis_view == const.BASIS_OI_NORM)
                        else df),
                    df_norm=df_norm, row=r, col=c, palette=color_palette,
                    show_price=show_price, asset=asset, model=model,
                    net_cols=(comm_net, lrg_net, sml_net), y_title=net_y_title,
                    setup_comms_only=setup_comms_only)
                fig = spec.build(ctx) or fig
                if spec.decorate:
                    ctx.fig = fig
                    fig = spec.decorate(ctx) or fig

                plot_idx += 1

    fig = helpers.add_open_interest_legend(fig, color_palette)
    exclude_xaxes = [i for i, p in enumerate(selected_plots) if p in ["max_pain", "max_pain_historical"]]
    fig = helpers.get_update_xaxes_for_plots(fig, df, exclude_plot_indices=exclude_xaxes)

    try:
        # The title is a verdict, so it reads the app model's own frame rather than
        # whichever one the panels happened to need. It used to read
        # min_threshold/max_threshold, which the panel loop had left pointing at
        # whichever basis the last panel happened to use.
        tdf = df_norm if app_model.basis == const.BASIS_OI_NORM else df
        latest_comm = tdf[const.COMMS_IDX].dropna().iloc[-1]
        latest_lrg = tdf[const.LRG_IDX].dropna().iloc[-1]
        latest_sml = tdf[const.SML_IDX].dropna().iloc[-1]

        # Default to standard text color
        title_color = vc.BRIGHTER_TEXT_COLOR

        state = app_model.setup_state(
            latest_comm, latest_lrg, latest_sml, get_indexer().is_equity(asset)
        )
        if state == const.SETUP_BULL:
            title_color = color_palette[3]
        elif state == const.SETUP_BEAR:
            title_color = color_palette[0]

        # Wrap the index values in an HTML span to inject the color
        chart_title = f"<span style='color:{title_color};'>{asset} ({latest_comm:.0f}, {latest_lrg:.0f}, {latest_sml:.0f})</span>"

    except (IndexError, KeyError):
        chart_title = asset  # Fallback if data is missing

    fig = helpers.get_update_layout_for_plots(fig, num_rows, num_cols, chart_title)

    return dcc.Graph(
                     id='analysis_main_graph',
                     figure=fig,
                     config={
                         'scrollZoom': False,
                         'doubleClick': 'reset',
                         'displayModeBar': True,
                         'modeBarButtonsToRemove': ['pan2d', 'select2d', 'lasso2d'],
                         'responsive': True,
                         'displaylogo': False,
                     },
                     style={'width': '100%'}
                     )

@callback(
    Output('analysis_single_asset_filter_input', 'options'),
    Output('analysis_single_asset_filter_input', 'value'),
    Input('analysis_asset_class_selector', 'value'),
    State('analysis_single_asset_filter_input', 'value')
)
def update_analysis_asset_options(selected_class, current_asset):
    if not selected_class:
        selected_class = get_indexer().get_default_asset_class()

    assets = sorted(get_indexer().get_assets_for_asset_class(selected_class))
    options = [{'label': m, 'value': m} for m in assets]

    if current_asset in assets:
        return options, current_asset
    else:
        return options, assets[0] if assets else None
