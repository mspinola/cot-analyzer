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
    path='/graphs'
)

# Which panels this page offers, in picker order. Everything else about them comes
# from the registry.
PLOT_IDS = ["oi_pct", "willco", "spearman", "net_pos", "index", "zscore", "momentum",
            "max_pain", "max_pain_historical"]

AVAILABLE_PLOTS = registry.labels_for(PLOT_IDS)

# Re-exported under the old names so the rest of this module reads unchanged.
BASIS_AWARE_PLOTS = registry.BASIS_AWARE_PLOTS
BASIS_INVARIANT_NOTE = registry.BASIS_INVARIANT_NOTE
NO_OVERLAY_NOTE = vc.NO_OVERLAY_NOTE
BASIS_OVERLAY_SPEC = registry.BASIS_OVERLAY_SPEC


default_asset = None


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
                            html.H6("Asset Classes", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dbc.Checklist(
                                id='graphs_asset_class_selector',
                                persistence='session',
                                options=[{'label': c, 'value': c} for c in asset_classes],
                                value=[get_indexer().get_default_asset_class()],
                                inline=True,
                                switch=True,
                                className="mb-3 p-1 rounded text-white",
                                style={'backgroundColor': 'black', 'border': '1px solid #6c757d'},
                                labelStyle={'color': 'white', 'marginRight': '0px', 'marginLeft': '0px', 'fontSize': '0.85rem'},
                                inputStyle={'opacity': '0.6'}
                            )
                        ], xs=12, md="auto"),

                        dbc.Col([
                            html.H6("Asset Selector", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dcc.Dropdown(
                                persistence='session',
                                id='graphs_multi_equity_selector_input',
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
                            html.H6("Plot Selector", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dbc.Select(
                                persistence=True,
                                id='graphs_plot_selector_input',
                                options=[{'label': v, 'value': k} for k, v in AVAILABLE_PLOTS.items()],
                                value="net_pos",
                                className="mb-3 bg-dark text-white border-secondary",
                                style={'width': '200px'}
                            ),
                        ], xs=12, md="auto"),
                        dbc.Col([
                            html.H6("Lookback", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dbc.Select(
                                id='graphs_lookback_selector',
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
                            html.H6("Model", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dbc.Select(
                                id='graphs_model_selector',
                                persistence='session',
                                options=[
                                    {"label": vc.MODEL_LABELS[v], "value": v}
                                    for v in vc.MODEL_VIEW_CHOICES
                                ],
                                value=models.DEFAULT_MODEL.key,
                                className="mb-3 bg-dark text-white border-secondary",
                                style={'width': '110px'}
                            ),
                            html.Div(id='graphs_model_note',
                                     className="text-muted",
                                     style={'fontSize': '0.7rem', 'marginTop': '-10px'}),
                        ], xs=12, md="auto"),

                        dbc.Col([
                            html.H6("Cols", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dbc.Select(
                                id='graphs_columns_selector',
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
            dcc.Store(id='graphs_zoom_sink'),

            dbc.Row([
                dcc.Loading(
                    id="loading-cot-graphs",
                    type="default",
                    children=html.Div(id='cot_graphs'),
                    color=vc.BRIGHTER_TEXT_COLOR
                )
            ], justify='center')
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
    Output('graphs_zoom_sink', 'data'),
    Input('graphs_main_graph', 'relayoutData'),
    State('graphs_main_graph', 'id'),
    prevent_initial_call=True
)


@callback(
    Output('global_lookback_store', 'data', allow_duplicate=True),
    Input('graphs_lookback_selector', 'value'),
    State('global_lookback_store', 'data'),
    prevent_initial_call=True
)
def update_global_lookback(value, current_store_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_store_val:
        return no_update
    return new_val


@callback(
    Output('graphs_lookback_selector', 'value'),
    Input('global_lookback_store', 'data'),
    State('graphs_lookback_selector', 'value')
)
def update_local_lookback(value, current_local_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_local_val:
        return no_update
    return new_val


@callback(
    Output('global_model_store', 'data', allow_duplicate=True),
    Input('graphs_model_selector', 'value'),
    State('global_model_store', 'data'),
    prevent_initial_call=True
)
def update_global_model(value, current_store_val):
    new_val = value if value in vc.MODEL_VIEW_CHOICES else models.DEFAULT_MODEL.key
    if new_val == current_store_val:
        return no_update
    return new_val


@callback(
    Output('graphs_model_selector', 'value'),
    Input('global_model_store', 'data'),
    State('graphs_model_selector', 'value')
)
def update_local_model(value, current_local_val):
    new_val = value if value in vc.MODEL_VIEW_CHOICES else models.DEFAULT_MODEL.key
    if new_val == current_local_val:
        return no_update
    return new_val


@callback(
    Output('global_model_store', 'data', allow_duplicate=True),
    Input('graphs_plot_selector_input', 'value'),
    State('global_model_store', 'data'),
    prevent_initial_call=True
)
def demote_both_when_unsupported(selected_plot, model_view):
    """Fall back to Raw when switching to a plot that cannot overlay, so the control
    never displays a view the figure isn't drawing."""
    if model_view == vc.MODEL_BOTH and selected_plot not in BASIS_OVERLAY_SPEC:
        return models.DEFAULT_MODEL.key
    return no_update


@callback(
    Output('graphs_model_selector', 'options'),
    Output('graphs_model_selector', 'disabled'),
    Output('graphs_model_note', 'children'),
    Input('graphs_plot_selector_input', 'value')
)
def update_model_availability(selected_plot):
    """Offer only the views this plot can actually draw, and say why when one is missing.

    A control that silently does nothing teaches the user it is broken.
    """
    def opts(views):
        return [{"label": vc.MODEL_LABELS[v], "value": v} for v in views]

    if selected_plot not in BASIS_AWARE_PLOTS:
        return (opts(vc.MODEL_CHOICES), True,
                BASIS_INVARIANT_NOTE.get(selected_plot, "not basis-dependent"))
    if selected_plot in BASIS_OVERLAY_SPEC:
        return opts(vc.MODEL_VIEW_CHOICES), False, ""
    return opts(vc.MODEL_CHOICES), False, NO_OVERLAY_NOTE


@callback(
    Output('graphs_columns_selector', 'value'),
    Input('url', 'pathname'),
    State('graphs_columns_selector', 'value')
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
    Output('cot_graphs', 'children'),
    Input('session_palette_theme_asset_store', 'data'),
    Input('graphs_multi_equity_selector_input', 'value'),
    Input('graphs_plot_selector_input', 'value'),
    Input('global_lookback_store', 'data'),
    Input('global_model_store', 'data'),
    Input('graphs_columns_selector', 'value')
)
def get_cot_graphs(palette_name, selected_assets, selected_plot, lookback, model_view, num_cols):
    print(f"Generating graphs for Selected Assets: {selected_assets}, Plot: {selected_plot}, Lookback: {lookback}, Model: {model_view}, Columns: {num_cols}")
    utils.cot_logger.info(f"Generating graphs for Selected Assets: {selected_assets}, Plot: {selected_plot}, Lookback: {lookback}, Model: {model_view}, Columns: {num_cols}")
    if not lookback:
        lookback = "Custom"
    # The selector persists per session, so a saved value can name a plot that no
    # longer exists (e.g. the retired synthesis plot). Fall back to the first option.
    if selected_plot not in AVAILABLE_PLOTS:
        selected_plot = next(iter(AVAILABLE_PLOTS))
    if model_view not in vc.MODEL_VIEW_CHOICES:
        model_view = models.DEFAULT_MODEL.key
    # Basis-invariant plots always render the default model so their cache entry is
    # shared and their output can never depend on a control that does not apply to them.
    # Same for Both on a plot that cannot overlay — the store callback demotes it, but a
    # stale session value can still arrive here.
    if selected_plot not in BASIS_AWARE_PLOTS:
        model_view = models.DEFAULT_MODEL.key
    elif model_view == vc.MODEL_BOTH and selected_plot not in BASIS_OVERLAY_SPEC:
        model_view = models.DEFAULT_MODEL.key

    # One resolution point: the model carries the gate, and the basis it plots is a
    # consequence rather than a second choice made somewhere else.
    model, is_overlay = vc.resolve_model_view(model_view)
    basis = model.basis

    price_overlay = True
    selected_plots = [selected_plot]
    if selected_assets is None or len(selected_assets) == 0 or selected_plots is None:
        return html.P("Select an asset class and plot to view data.", style={'textAlign': 'center', 'color': vc.BRIGHTER_TEXT_COLOR})

    assets = selected_assets

    num_cols = int(num_cols)
    num_selected = len(selected_plots) * len(assets)
    num_rows = math.ceil(num_selected / num_cols)

    color_palette = viz_config.get_palette(palette_name)

    # This page stacks one metric across many assets, so a panel is titled by its asset
    # rather than by the plot. The options curves still name the ticker they are quoted
    # on, which is often a proxy ETF rather than the futures symbol.
    titles = []
    for asset in assets:
        title = asset
        if registry.REGISTRY[selected_plots[0]].needs_asset:
            etf = registry.etf_symbol_for(get_indexer().get_instrument_from_name(asset))
            if etf:
                title = f"{asset} via {etf}"
        titles.append(title)

    # Every cell draws the same metric, so they all take the same spec.
    specs = registry.subplot_specs([selected_plots[0]] * num_selected,
                                   show_price=price_overlay, num_cols=num_cols)

    # Max Pain plots use price scales for X-axis (which are vastly different per asset)
    # So we must disable shared X-axes to prevent Plotly from squishing everything.
    is_shared_x = False if selected_plots[0] in ["max_pain", "max_pain_historical"] else True
    fig = helpers.get_make_subplots_for_plots(num_rows, num_cols, titles, specs, shared_xaxes=is_shared_x)

    plot_idx = 0
    for r in range(1, num_rows + 1):
        for c in range(1, num_cols + 1):
            if plot_idx < num_selected:
                df = get_indexer().get_symbols_data(assets[plot_idx], lookback, basis)
                if df is None:
                    return helpers.get_no_data_html_p()

                p = selected_plots[0]

                if is_overlay:
                    df_norm = get_indexer().get_symbols_data(assets[plot_idx], lookback, const.BASIS_OI_NORM)
                    if df_norm is None:
                        return helpers.get_no_data_html_p()
                    value_col, y_title, y_range, zero_line = BASIS_OVERLAY_SPEC[p]
                    fig = helpers.get_basis_overlay_plot(
                        fig, df, df_norm, value_col, r, c, color_palette,
                        y_title=y_title, y_range=y_range, show_oi=price_overlay,
                        zero_line=zero_line)
                    plot_idx += 1
                    continue

                # Net Positions plots the underlying series by name rather than via the
                # generic aliases, so it has to pick the basis pair itself.
                if basis == const.BASIS_OI_NORM:
                    comm_net, lrg_net, sml_net = const.COMM_NET_NORM, const.LARGE_NET_NORM, const.SMALL_NET_NORM
                else:
                    comm_net, lrg_net, sml_net = const.COMM_NET, const.LARGE_NET, const.SMALL_NET

                spec = registry.REGISTRY[p]
                ctx = registry.PlotCtx(
                    fig=fig, df=df, row=r, col=c, palette=color_palette,
                    show_price=price_overlay, asset=assets[plot_idx], model=model,
                    net_cols=(comm_net, lrg_net, sml_net),
                    y_title="net / OI" if basis == const.BASIS_OI_NORM else "net position",
                    setup_comms_only=get_indexer().is_equity(assets[plot_idx]),
                    # One legend for the whole stack: every panel here draws the same
                    # metric, so repeating it per asset would be noise.
                    showlegend=(plot_idx == 0))
                fig = spec.build(ctx) or fig
                if spec.decorate:
                    ctx.fig = fig
                    fig = spec.decorate(ctx) or fig

                plot_idx += 1

    if selected_plots[0] not in ["max_pain", "max_pain_historical"]:
        fig = helpers.get_update_xaxes_for_plots(fig, df)

    main_title = AVAILABLE_PLOTS[selected_plot]
    if selected_plot in BASIS_AWARE_PLOTS:
        suffix = "Raw vs % of OI" if is_overlay else vc.BASIS_LABELS[basis]
        main_title = f"{main_title} ({suffix})"
    fig = helpers.get_update_layout_for_plots(fig, num_rows, num_cols, main_title)

    return dcc.Graph(figure=fig,
                     id='graphs_main_graph',
                     config={
                        'scrollZoom': False,
                        'doubleClick': 'reset',
                        'displayModeBar': True,
                        'modeBarButtonsToRemove': ['pan2d', 'select2d', 'lasso2d'],
                        'displaylogo': False,
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
    Output('graphs_multi_equity_selector_input', 'options'),
    Output('graphs_multi_equity_selector_input', 'value'),
    Input('graphs_asset_class_selector', 'value'),
    State('graphs_multi_equity_selector_input', 'value')
)
def update_graphs_asset_options(selected_classes, current_assets):
    if not selected_classes:
        selected_classes = []

    all_assets = []
    for cls in selected_classes:
        all_assets.extend(sorted(get_indexer().get_assets_for_asset_class(cls)))

    all_assets = sorted(list(set(all_assets)))
    options = [{'label': m, 'value': m} for m in all_assets]

    # Preserve current selections if they are in the active classes
    valid_assets = [a for a in (current_assets or []) if a in all_assets]

    if not valid_assets and all_assets:
        valid_assets = [all_assets[0]]

    return options, valid_assets
