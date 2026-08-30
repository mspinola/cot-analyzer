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
from components import class_filter, config_fold, controls

# One page, two views. The panel stack (one market, many panels) and the market
# grid (one metric, many markets) shared a registry, a figure assembler, a control
# card's worth of duplicated selectors and two nav entries; the grid used to be its
# own page at /graphs. Old bookmarks survive via a 301 in app_cot to
# /analysis?view=grid, an explicit route rather than Dash's `redirect_from`
# because that mechanism cannot carry the query naming which view the old
# address meant.
dash.register_page(
    __name__,
    path='/analysis',
)

# Layout runs per request; the wiring must not.
controls.register_lookback('analysis_lookback_selector')
controls.register_asset_link('analysis_single_asset_filter_input')
class_filter.register('graphs_asset_class_selector',
                      classes=lambda: sorted(get_indexer().get_asset_classes()))
controls.register_model('graphs_model_selector', choices=vc.MODEL_VIEW_CHOICES)

# The two views. Wire-format values (session-persisted control), so renaming one
# silently resets a returning reader to the default.
VIEW_STACK = "stack"
VIEW_GRID = "grid"
VIEW_LABELS = {VIEW_STACK: "Panel stack · one market",
               VIEW_GRID: "Market grid · one metric"}

# Which panels the GRID view offers, in picker order: the metrics worth comparing
# across markets. The stack's own picker (below) is richer because per-panel basis
# variants only make sense stacked on one market.
GRID_PLOT_IDS = ["oi_pct", "willco", "spearman", "net_pos", "index", "zscore",
                 "momentum", "max_pain", "max_pain_historical"]
GRID_PLOTS = registry.labels_for(GRID_PLOT_IDS)

BASIS_AWARE_PLOTS = registry.BASIS_AWARE_PLOTS
BASIS_INVARIANT_NOTE = registry.BASIS_INVARIANT_NOTE
NO_OVERLAY_NOTE = vc.NO_OVERLAY_NOTE
BASIS_OVERLAY_SPEC = registry.BASIS_OVERLAY_SPEC

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
    default_class = get_indexer().get_default_asset_class()
    default_assets = sorted(get_indexer().get_assets_for_asset_class(default_class))

    return html.Div([
        dbc.Container([
            dbc.Card([
                dbc.CardBody([
                    config_fold.wrap('analysis', [
                    # The controls every view shares. Lookback and Cols used to
                    # exist twice, once per page; a reader flipping views keeps
                    # their window and their grid width because there is only one
                    # of each control to keep.
                    dbc.Row([
                        dbc.Col([
                            controls.label("View", marginBottom="0.5rem"),
                            dbc.RadioItems(
                                id='analysis_view_selector',
                                persistence='session',
                                options=[{'label': text, 'value': value}
                                         for value, text in VIEW_LABELS.items()],
                                value=VIEW_STACK,
                                inline=True,
                                style={'color': vc.BRIGHTER_TEXT_COLOR,
                                       'fontSize': '0.85rem'},
                            ),
                        ], xs=12, md="auto"),
                        dbc.Col([
                            controls.label("Lookback", marginBottom="0.5rem"),
                            controls.lookback_select(
                                'analysis_lookback_selector',
                                className="bg-dark text-white border-secondary control-mobile-full",
                                style={'width': '120px'})
                        ], xs=12, md="auto"),

                        dbc.Col([
                            controls.label("Cols", marginBottom="0.5rem"),
                            dbc.Select(
                                id='analysis_columns_selector',
                                persistence='session',
                                options=[
                                    {"label": "1", "value": "1"},
                                    {"label": "2", "value": "2"},
                                    {"label": "3", "value": "3"},
                                ],
                                value="1",
                                className="bg-dark text-white border-secondary control-mobile-full",
                                style={'width': '70px'}
                            )
                        ], xs=12, md="auto"),
                    ], className="g-2 align-items-start"),

                    # The stack's own controls: one market, chosen precisely, and
                    # a multi-select of panels (with per-panel basis variants).
                    html.Div(id='analysis_stack_controls', children=dbc.Row([
                        dbc.Col([
                            controls.label("Asset Class", marginBottom="0.5rem"),
                            dbc.RadioItems(
                                id='analysis_asset_class_selector',
                                persistence='session',
                                options=[{'label': c, 'value': c} for c in asset_classes],
                                value=default_class,
                                inline=True,
                                className="p-1 rounded text-white",
                                style={'backgroundColor': 'black', 'border': '1px solid #6c757d'},
                                labelStyle={'color': 'white', 'marginRight': '10px', 'marginLeft': '0px', 'fontSize': '0.85rem'},
                                inputStyle={'opacity': '0.6'}
                            )
                        ], xs=12, md="auto"),

                        dbc.Col([
                            controls.label("Asset Selector", marginBottom="0.5rem"),
                            dbc.Select(
                                persistence='session',
                                id='analysis_single_asset_filter_input',
                                options=[{'label': m, 'value': m} for m in default_assets],
                                className="bg-dark text-white border-secondary control-mobile-full",
                                style={'width': '200px'}
                            ),
                        ], xs=12, md="auto"),

                        dbc.Col([
                            controls.label("Visible Plots", marginBottom="0.5rem"),
                            dcc.Dropdown(
                                persistence=True,
                                id='analysis_plot_selector',
                                options=[{'label': v, 'value': k} for k, v in AVAILABLE_PLOTS.items()],
                                # The options-fed panels stay in the picker but out
                                # of the default stack; see DEFAULT_OFF_PLOTS.
                                value=[p for p in BASE_PLOTS
                                       if p not in registry.DEFAULT_OFF_PLOTS],
                                multi=True,
                                className="dash-dropdown bg-dark text-white control-mobile-full",
                                style={'width': '200px'}
                            ),
                        ], xs=12, md="auto"),
                    ], className="g-2 align-items-start mt-1")),

                    # The grid's controls: many markets, one metric, and the model
                    # view (Raw / NPF / Both) that decides the metric's basis.
                    html.Div(id='analysis_grid_controls', hidden=True,
                             children=dbc.Row([
                        dbc.Col([
                            controls.label("Asset Classes", marginBottom="0.5rem"),
                            class_filter.control(
                                'graphs_asset_class_selector', asset_classes,
                                value=[default_class])
                        ], xs=12, md="auto"),

                        dbc.Col([
                            controls.label("Asset Selector", marginBottom="0.5rem"),
                            dcc.Dropdown(
                                persistence='session',
                                id='graphs_multi_equity_selector_input',
                                options=[{'label': m, 'value': m} for m in default_assets],
                                multi=True,
                                className="dash-dropdown bg-dark text-white control-mobile-full",
                                searchable=True,
                                clearable=True,
                                style={'width': '200px'}
                            ),
                        ], xs=12, md="auto"),

                        dbc.Col([
                            controls.label("Plot Selector", marginBottom="0.5rem"),
                            dbc.Select(
                                persistence=True,
                                id='graphs_plot_selector_input',
                                options=[{'label': v, 'value': k} for k, v in GRID_PLOTS.items()],
                                value="net_pos",
                                className="bg-dark text-white border-secondary control-mobile-full",
                                style={'width': '200px'}
                            ),
                        ], xs=12, md="auto"),

                        dbc.Col([
                            controls.label("Model", marginBottom="0.5rem"),
                            controls.model_select(
                                'graphs_model_selector',
                                choices=vc.MODEL_VIEW_CHOICES,
                                className="bg-dark text-white border-secondary control-mobile-full",
                                style={'width': '110px'}),
                            # In flow rather than absolute, so the card reserves
                            # height for it; only present for some plots.
                            html.Div(id='graphs_model_note',
                                     className="text-muted",
                                     style={'fontSize': '0.7rem', 'marginTop': '2px'}),
                        ], xs=12, md="auto"),
                    ], className="g-2 align-items-start mt-1")),
                    ]),
                ])
            ], style={'backgroundColor': 'var(--card-color)', 'borderColor': vc.GRID_COLOR}, className="mb-4 mt-2"),

            html.Hr(style=vc.hr_style),

            # The browser writes the fitted zoom window here. Nothing on this page reads it,
            # but the shared autoscale needs an Output to hang the callback on. One sink
            # per view's graph, since either graph can exist.
            dcc.Store(id='analysis_zoom_sink'),
            dcc.Store(id='graphs_zoom_sink'),

            html.Div([
                dbc.Row([
                    dcc.Loading(
                        id="loading-analysis-graph",
                        type="default",  # Options: "graph", "cube", "circle", "dot", or "default"
                        children=html.Div(id='analysis_stack'),
                        color=vc.BRIGHTER_TEXT_COLOR
                    )
                ], justify='center'),
                dbc.Row([
                    dcc.Loading(
                        id="loading-cot-graphs",
                        type="default",
                        children=html.Div(id='cot_graphs'),
                        color=vc.BRIGHTER_TEXT_COLOR
                    )
                ], justify='center'),
            ], style={"position": "relative", "width": "100%"})
        ], fluid=True),
    ])


# The whole view state, in one clientside callback: the ?view= deep link, the
# radio, which controls show, and the URL write-back. One writer on purpose, and
# clientside on purpose: with the link-reader as a server callback, the page-load
# wave ran the visibility half early with the default value and never re-ran it
# when the reader's answer landed (server-side dependents wait for pending
# outputs in the initial wave; clientside ones do not), so a ?view=grid load
# drew the grid under the stack's controls. Everything in one function cannot
# disagree with itself.
#
# The rules, each the same one the other deep links follow: a link's ?view=
# wins ONCE per distinct value (so navigation noise and the global write-back
# re-firing this cannot re-force a view the reader has since flipped away
# from); afterwards the radio owns the URL, writing ?view=grid and erasing it
# at the default, so the address bar always deep-links what is on screen.
# Hidden rather than unmounted, so a hidden control keeps its value: flipping
# to the grid and back lands on the exact stack the reader left.
clientside_callback(
    f"""
    function(view, _search) {{
        const nu = window.dash_clientside.no_update;
        const params = new URLSearchParams(window.location.search);
        const forced = params.get('view');
        const valid = forced === '{VIEW_STACK}' || forced === '{VIEW_GRID}';
        if (valid && forced !== view && window.__analysisViewApplied !== forced) {{
            window.__analysisViewApplied = forced;
            const grid = forced === '{VIEW_GRID}';
            return [forced, grid, !grid];
        }}
        if (view === '{VIEW_GRID}') {{ params.set('view', '{VIEW_GRID}'); }}
        else {{ params.delete('view'); }}
        // Record what WE just wrote as already applied. The write-back goes via
        // replaceState, invisible to the router, so nothing else updates the
        // guard; without this, a radio restored to grid by persistence writes
        // ?view=grid, and the reader then treated our own parameter as a fresh
        // link and forced the next manual flip straight back (observed live: a
        // stack click that would not stick).
        window.__analysisViewApplied = params.get('view');
        const q = params.toString();
        const next = window.location.pathname + (q ? '?' + q : '');
        if (next !== window.location.pathname + window.location.search) {{
            history.replaceState(null, '', next);
        }}
        const grid = view === '{VIEW_GRID}';
        return [nu, grid, !grid];
    }}
    """,
    Output('analysis_view_selector', 'value'),
    Output('analysis_stack_controls', 'hidden'),
    Output('analysis_grid_controls', 'hidden'),
    Input('analysis_view_selector', 'value'),
    Input('url', 'search'),
)


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
     Input('global_model_store', 'data'),
     Input('analysis_view_selector', 'value')]
)
def update_analysis_stack(palette_name, asset, lookback, selected_plots, num_cols,
                          model_view, view=VIEW_STACK):
    # The other view's render must cost nothing: an empty container, not a stale
    # figure, so nothing below the fold pretends to be current.
    if view == VIEW_GRID:
        return []
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

    # After the loop, because it is a question about the whole stack: the panel that
    # owns the legend is not necessarily the one drawing price or open interest.
    fig = helpers.reconcile_legend_entries(fig, color_palette)
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

        # Wrap the index values in an HTML span to inject the color. The leg
        # letters ride at reduced size inside it: a plotly title can carry no
        # tooltip, so "(14, 85, 64)" had nothing anywhere naming what the three
        # numbers were.
        letter = "<span style='font-size:0.65em;'>{}</span>"
        chart_title = (
            f"<span style='color:{title_color};'>{asset} "
            f"({letter.format('C')} {latest_comm:.0f} · "
            f"{letter.format('L')} {latest_lrg:.0f} · "
            f"{letter.format('S')} {latest_sml:.0f})</span>")

    except (IndexError, KeyError):
        chart_title = asset  # Fallback if data is missing

    fig = helpers.get_update_layout_for_plots(fig, num_rows, num_cols, chart_title)

    return dcc.Graph(
                     id='analysis_main_graph',
                     figure=fig,
                     config={
                         'scrollZoom': False,
                         'doubleClick': 'reset',
                         'displayModeBar': not app_utils.is_mobile(),
                         'modeBarButtonsToRemove': ['pan2d', 'select2d', 'lasso2d'],
                         'responsive': True,
                         'displaylogo': False,
                     },
                     style={'width': '100%'}
                     )

@callback(
    Output('analysis_asset_class_selector', 'value'),
    Output('analysis_single_asset_filter_input', 'options'),
    Output('analysis_single_asset_filter_input', 'value'),
    Input('url', 'search'),
    Input('analysis_asset_class_selector', 'value'),
    State('analysis_single_asset_filter_input', 'value')
)
def update_analysis_asset_options(search, selected_class, current_asset):
    # A ?asset= deep link wins on load, forcing the class along with the asset
    # so the link is self-sufficient; the OI Alignment page's pattern.
    triggered = dash.ctx.triggered_id
    if triggered in (None, 'url') and search:
        forced = controls.forced_asset(search)
        if forced:
            forced_class, asset = forced
            assets = sorted(get_indexer().get_assets_for_asset_class(forced_class))
            return (forced_class,
                    [{'label': m, 'value': m} for m in assets], asset)

    if not selected_class:
        selected_class = get_indexer().get_default_asset_class()

    assets = sorted(get_indexer().get_assets_for_asset_class(selected_class))
    options = [{'label': m, 'value': m} for m in assets]

    if current_asset in assets:
        return no_update, options, current_asset
    else:
        return no_update, options, assets[0] if assets else None


# ── the market grid (one metric, many markets; formerly the /graphs page) ─────

clientside_callback(
    "window.dash_clientside.clientside.autoscale_y_axes",
    Output('graphs_zoom_sink', 'data'),
    Input('graphs_main_graph', 'relayoutData'),
    State('graphs_main_graph', 'id'),
    prevent_initial_call=True
)


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
    if selected_plot not in BASIS_AWARE_PLOTS:
        return (controls.model_options(vc.MODEL_CHOICES), True,
                BASIS_INVARIANT_NOTE.get(selected_plot, "not basis-dependent"))
    if selected_plot in BASIS_OVERLAY_SPEC:
        return controls.model_options(vc.MODEL_VIEW_CHOICES), False, ""
    return controls.model_options(vc.MODEL_CHOICES), False, NO_OVERLAY_NOTE


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


@callback(
    Output('cot_graphs', 'children'),
    Input('session_palette_theme_asset_store', 'data'),
    Input('graphs_multi_equity_selector_input', 'value'),
    Input('graphs_plot_selector_input', 'value'),
    Input('global_lookback_store', 'data'),
    Input('global_model_store', 'data'),
    Input('analysis_columns_selector', 'value'),
    Input('analysis_view_selector', 'value'),
)
def get_cot_graphs(palette_name, selected_assets, selected_plot, lookback,
                   model_view, num_cols, view=VIEW_STACK):
    # The stack view's render must not pay for this one; same rule in reverse in
    # update_analysis_stack.
    if view != VIEW_GRID:
        return []
    utils.cot_logger.info(f"Generating graphs for Selected Assets: {selected_assets}, Plot: {selected_plot}, Lookback: {lookback}, Model: {model_view}, Columns: {num_cols}")
    if not lookback:
        lookback = "Custom"
    # The selector persists per session, so a saved value can name a plot that no
    # longer exists (e.g. the retired synthesis plot). Fall back to the first option.
    if selected_plot not in GRID_PLOTS:
        selected_plot = next(iter(GRID_PLOTS))
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
    if not selected_assets:
        return html.P("Select an asset class and plot to view data.", style={'textAlign': 'center', 'color': vc.BRIGHTER_TEXT_COLOR})

    assets = selected_assets

    num_cols = int(num_cols)
    num_selected = len(assets)
    num_rows = math.ceil(num_selected / num_cols)

    color_palette = viz_config.get_palette(palette_name)

    # This view stacks one metric across many assets, so a panel is titled by its asset
    # rather than by the plot. The options curves still name the ticker they are quoted
    # on, which is often a proxy ETF rather than the futures symbol.
    titles = []
    for asset in assets:
        title = asset
        if registry.REGISTRY[selected_plot].needs_asset:
            etf = registry.etf_symbol_for(get_indexer().get_instrument_from_name(asset))
            if etf:
                title = f"{asset} via {etf}"
        titles.append(title)

    # Every cell draws the same metric, so they all take the same spec.
    specs = registry.subplot_specs([selected_plot] * num_selected,
                                   show_price=price_overlay, num_cols=num_cols)

    # Max Pain plots use price scales for X-axis (which are vastly different per asset)
    # So we must disable shared X-axes to prevent Plotly from squishing everything.
    is_shared_x = selected_plot not in ["max_pain", "max_pain_historical"]
    fig = helpers.get_make_subplots_for_plots(num_rows, num_cols, titles, specs, shared_xaxes=is_shared_x)

    df = None
    plot_idx = 0
    for r in range(1, num_rows + 1):
        for c in range(1, num_cols + 1):
            if plot_idx < num_selected:
                df = get_indexer().get_symbols_data(assets[plot_idx], lookback, basis)
                if df is None:
                    return helpers.get_no_data_html_p()

                if is_overlay:
                    df_norm = get_indexer().get_symbols_data(assets[plot_idx], lookback, const.BASIS_OI_NORM)
                    if df_norm is None:
                        return helpers.get_no_data_html_p()
                    value_col, y_title, y_range, zero_line = BASIS_OVERLAY_SPEC[selected_plot]
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

                spec = registry.REGISTRY[selected_plot]
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

    # After the loop, because it is a question about the whole stack: the panel that
    # owns the legend is not necessarily the one drawing price or open interest.
    fig = helpers.reconcile_legend_entries(fig, color_palette)

    if selected_plot not in ["max_pain", "max_pain_historical"] and df is not None:
        fig = helpers.get_update_xaxes_for_plots(fig, df)

    main_title = GRID_PLOTS[selected_plot]
    if selected_plot in BASIS_AWARE_PLOTS:
        suffix = "Raw vs % of OI" if is_overlay else vc.BASIS_LABELS[basis]
        main_title = f"{main_title} ({suffix})"
    fig = helpers.get_update_layout_for_plots(fig, num_rows, num_cols, main_title)

    return dcc.Graph(figure=fig,
                     id='graphs_main_graph',
                     config={
                        'scrollZoom': False,
                        'doubleClick': 'reset',
                        # Off on a phone: hover-revealed buttons have no hover,
                        # and the bar painted over the figure title at 375px.
                        'displayModeBar': not app_utils.is_mobile(),
                        'modeBarButtonsToRemove': ['pan2d', 'select2d', 'lasso2d'],
                        'displaylogo': False,
                        'responsive': True},
                        style={'width': '100%'
                    })
