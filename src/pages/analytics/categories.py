"""Disaggregated / TFF category view.

The rest of the app draws the Legacy report's three legs. Legacy pools actors that
behave differently: its Commercial leg is Producer/Merchant plus Swap Dealers, and its
Non-Commercial leg is Managed Money plus Other Reportable. This page draws the split.

Deliberately no Model selector. The model in this app is not only a setup gate, it also
carries the basis (see the note at the top of viz_constants), and the gate itself is a
three-leg model with bands calibrated on the legacy series, so it does not transfer to
five categories without recalibration. Rather than introduce a standalone basis control
here and be the first place that doctrine breaks, the two bases are two panels: Net
Positions in contracts, and Net % of OI.
"""

import math

import dash
import dash_bootstrap_components as dbc
from cotmetrics import categories as cot_categories
from cotmetrics.indexer import get_indexer
from dash import Input, Output, State, callback, clientside_callback, dcc, html, no_update

import app_utils
import components.category_traces as ct
import components.plot_layout as layout_helpers
import viz_config
import viz_constants as vc

dash.register_page(
    __name__,
    path='/categories'
)

AVAILABLE_PLOTS = ct.labels_for()

REPORT_ORDER = list(cot_categories.REPORT_CHOICES)


def _report_options(available):
    """Radio options with the unavailable report disabled rather than hidden.

    The two universes are disjoint by construction (Disaggregated covers physical
    commodities, TFF covers financials), so exactly one option is live for any market
    that has either. Showing the dead one greyed out, with the reason beside it, says
    something true about the data; hiding it would just look like a control that moves
    on its own.
    """
    return [{"label": cot_categories.REPORT_LABELS[r],
             "value": r,
             "disabled": r not in available}
            for r in REPORT_ORDER]


def _report_note(asset, available):
    if not asset:
        return ""
    if not available:
        return f"{asset} has neither report"
    missing = [cot_categories.REPORT_LABELS[r]
               for r in REPORT_ORDER if r not in available]
    if not missing:
        return ""
    if cot_categories.REPORT_DISAGG in available:
        return f"physical commodity, so no {missing[0]} report"
    return f"financial future, so no {missing[0]} report"


def layout(**kwargs):
    # Built per request, not at import: resolving these at module scope would make
    # importing this page require a populated COTDATA_STORE.
    asset_classes = sorted(get_indexer().get_asset_classes())
    default_class = get_indexer().get_default_asset_class()
    assets = sorted(get_indexer().get_assets_for_asset_class(default_class))

    return html.Div([
        dbc.Container([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            html.H6("Asset Class", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dbc.Select(
                                id='categories_asset_class_selector',
                                persistence='session',
                                options=[{'label': c, 'value': c} for c in asset_classes],
                                value=default_class,
                                className="mb-3 bg-dark text-white border-secondary",
                                style={'width': '160px'}
                            ),
                        ], xs=12, md="auto"),

                        dbc.Col([
                            html.H6("Asset", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dcc.Dropdown(
                                id='categories_asset_selector',
                                persistence='session',
                                options=[{'label': m, 'value': m} for m in assets],
                                value=assets[0] if assets else None,
                                multi=False,
                                className="mb-3 dash-dropdown bg-dark text-white",
                                searchable=True,
                                clearable=False,
                                style={'width': '200px'}
                            ),
                        ], xs=12, md="auto"),

                        dbc.Col([
                            html.H6("Report", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dbc.RadioItems(
                                id='categories_report_selector',
                                persistence='session',
                                options=_report_options(REPORT_ORDER),
                                value=cot_categories.REPORT_DISAGG,
                                inline=True,
                                className="mb-1 text-white",
                                labelStyle={'marginRight': '10px', 'fontSize': '0.85rem'},
                            ),
                            html.Div(id='categories_report_note',
                                     className="text-muted mb-3",
                                     style={'fontSize': '0.7rem'}),
                        ], xs=12, md="auto"),
                    ]),

                    dbc.Row([
                        dbc.Col([
                            html.H6("Categories", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dbc.Checklist(
                                id='categories_category_selector',
                                # Deliberately NOT persisted. The keys are
                                # report-specific and the report is derived from the
                                # asset, so a value saved under one report can come
                                # back under the other. The two reports share the
                                # labels Other Reportable and Non-Reportable, so a
                                # persisted pair of those reads as a legitimate
                                # within-report selection and sticks: every commodity
                                # then loads with Managed Money switched off and no
                                # way to tell why. The value survives asset switches
                                # inside a session anyway, because the callback below
                                # only fires when the report changes.
                                options=[],
                                value=[],
                                inline=True,
                                switch=True,
                                className="mb-3 p-1 rounded text-white",
                                style={'backgroundColor': 'black', 'border': '1px solid #6c757d'},
                                labelStyle={'color': 'white', 'marginRight': '0px', 'marginLeft': '0px', 'fontSize': '0.85rem'},
                                inputStyle={'opacity': '0.6'}
                            ),
                        ], xs=12, md="auto"),
                    ]),

                    dbc.Row([
                        dbc.Col([
                            html.H6("Plot Selector", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dcc.Dropdown(
                                id='categories_plot_selector',
                                persistence='session',
                                options=[{'label': v, 'value': k} for k, v in AVAILABLE_PLOTS.items()],
                                value=list(ct.DEFAULT_PLOTS),
                                multi=True,
                                className="mb-3 dash-dropdown bg-dark text-white",
                                clearable=False,
                                style={'width': '340px'}
                            ),
                        ], xs=12, md="auto"),

                        dbc.Col([
                            html.H6("Lookback", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dbc.Select(
                                id='categories_lookback_selector',
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
                            html.H6("Layout", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dbc.Select(
                                id='categories_layout_selector',
                                persistence='session',
                                options=[{"label": vc.LAYOUT_LABELS[v], "value": v}
                                         for v in vc.LAYOUT_CHOICES],
                                value=vc.LAYOUT_FACET,
                                className="mb-3 bg-dark text-white border-secondary",
                                style={'width': '150px'}
                            ),
                        ], xs=12, md="auto"),

                        dbc.Col([
                            html.H6("Cols", className="text-muted text-uppercase mb-2", style={'fontSize': '0.75rem'}),
                            dbc.Select(
                                id='categories_columns_selector',
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

            # The browser writes the fitted zoom window here. Nothing on this page reads
            # it, but the shared autoscale needs an Output to hang the callback on.
            dcc.Store(id='categories_zoom_sink'),

            dbc.Row([
                dcc.Loading(
                    id="loading-categories",
                    type="default",
                    children=html.Div(id='categories_stack'),
                    color=vc.BRIGHTER_TEXT_COLOR
                )
            ], justify='center')
        ], fluid=True),
    ])


clientside_callback(
    "window.dash_clientside.clientside.autoscale_y_axes",
    Output('categories_zoom_sink', 'data'),
    Input('categories_main_graph', 'relayoutData'),
    State('categories_main_graph', 'id'),
    prevent_initial_call=True
)


@callback(
    Output('global_lookback_store', 'data', allow_duplicate=True),
    Input('categories_lookback_selector', 'value'),
    State('global_lookback_store', 'data'),
    prevent_initial_call=True
)
def update_global_lookback(value, current_store_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_store_val:
        return no_update
    return new_val


@callback(
    Output('categories_lookback_selector', 'value'),
    Input('global_lookback_store', 'data'),
    State('categories_lookback_selector', 'value')
)
def update_local_lookback(value, current_local_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_local_val:
        return no_update
    return new_val


@callback(
    Output('categories_asset_selector', 'options'),
    Output('categories_asset_selector', 'value'),
    Input('categories_asset_class_selector', 'value'),
    State('categories_asset_selector', 'value')
)
def update_categories_asset_options(asset_class, current_asset):
    # get_assets_for_asset_class, not .instruments: it honours instrument roles, so a
    # heldout market cannot become plottable through this new door.
    assets = sorted(get_indexer().get_assets_for_asset_class(asset_class or ""))
    options = [{'label': m, 'value': m} for m in assets]
    value = current_asset if current_asset in assets else (assets[0] if assets else None)
    return options, value


@callback(
    Output('categories_report_selector', 'options'),
    Output('categories_report_selector', 'value'),
    Output('categories_report_note', 'children'),
    Input('categories_asset_selector', 'value'),
    State('categories_report_selector', 'value')
)
def update_report_availability(asset, current_report):
    """Offer only the report this market actually has, and say why the other is off.

    A control that silently does nothing teaches the user it is broken.
    """
    available = get_indexer().available_reports_for(asset) if asset else ()
    options = _report_options(available)
    value = current_report if current_report in available else (
        available[0] if available else no_update)
    return options, value, _report_note(asset, available)


@callback(
    Output('categories_category_selector', 'options'),
    Output('categories_category_selector', 'value'),
    Input('categories_report_selector', 'value'),
    State('categories_category_selector', 'value')
)
def update_category_options(report, current):
    """Re-key the checklist when the report changes.

    A selection carries over only when it belongs to this report. The two reports
    share the labels other_reportable and nonreportable, but that is a naming
    coincidence rather than a shared population: Other Reportable under
    Disaggregated is a different set of traders from Other Reportable under TFF. So
    intersecting a carried-over selection is wrong on the merits, and it is bad in
    practice too, since the intersection can only ever be those two residual
    categories. Switching reports would silently drop Managed Money, the one most
    people came for, and leave a chart that looks broken.

    A selection that is entirely within this report's keys is a real within-report
    deselection, and that is kept.
    """
    if report not in cot_categories.REPORT_CHOICES:
        return [], []
    specs = cot_categories.categories_for(report)
    options = [{'label': s.label, 'value': s.key} for s in specs]
    keys = [s.key for s in specs]
    current = current or []
    from_this_report = current and not (set(current) - set(keys))
    return options, (list(current) if from_this_report else keys)


@callback(
    Output('categories_columns_selector', 'value'),
    Input('url', 'pathname'),
    State('categories_columns_selector', 'value')
)
def set_default_columns(pathname, current_val):
    if app_utils.is_mobile():
        new_val = "1"
    elif current_val in ["1", "2", "3"]:
        new_val = current_val
    else:
        new_val = "1"

    if new_val == current_val:
        return no_update
    return new_val


@callback(
    Output('categories_stack', 'children'),
    Input('session_palette_theme_asset_store', 'data'),
    Input('categories_asset_selector', 'value'),
    Input('categories_report_selector', 'value'),
    Input('categories_category_selector', 'value'),
    Input('categories_plot_selector', 'value'),
    Input('global_lookback_store', 'data'),
    Input('categories_columns_selector', 'value'),
    Input('categories_layout_selector', 'value'),
)
def render_category_stack(palette_name, asset, report, selected_categories,
                          selected_plots, lookback, num_cols, layout_mode):
    if not asset:
        return html.P("Select an asset to view its category breakdown.",
                      style={'textAlign': 'center', 'color': vc.BRIGHTER_TEXT_COLOR})
    if report not in cot_categories.REPORT_CHOICES:
        return layout_helpers.get_no_data_html_p()

    lookback = lookback or "Custom"
    df = get_indexer().get_category_data(asset, report, lookback)
    if df is None or df.empty:
        return layout_helpers.get_no_data_html_p()

    palette = viz_config.get_palette(palette_name)
    # Filtered against the frame, not just the checklist: a market missing a category
    # then renders the panels it has rather than raising on the column it does not.
    series = ct.category_series(report, selected_categories, palette, frame=df)
    if not series:
        return html.P("Select at least one trader category.",
                      style={'textAlign': 'center', 'color': vc.BRIGHTER_TEXT_COLOR})

    plots = ct.sanitize_selection(selected_plots)
    show_price = True
    lookback_header = df.attrs.get("lookback_header", " Custom")
    faceted = layout_mode == vc.LAYOUT_FACET

    if faceted:
        # Rows are categories and columns are panels, so the Cols control does not
        # apply: the column count is the number of panels selected.
        num_rows, num_cols = ct.facet_shape(plots, series, show_price)
        fig = layout_helpers.get_make_subplots_for_facets(
            num_rows, num_cols,
            ct.facet_titles(plots, series, show_price),
            ct.facet_specs(plots, series, show_price))
        fig = ct.build_facet_figure(fig, df, series, plots, lookback_header, palette,
                                    show_price=show_price)
        height = layout_helpers.get_facet_figure_height(num_rows, num_cols)
        # Every row is direct-labelled, so a legend would only repeat itself.
        show_legend = False
    else:
        num_cols = int(num_cols or 1)
        num_rows = math.ceil(len(plots) / num_cols)
        titles = [AVAILABLE_PLOTS[p] for p in plots]
        specs = ct.subplot_specs(plots, show_price=show_price, num_cols=num_cols)
        fig = layout_helpers.get_make_subplots_for_plots(num_rows, num_cols, titles, specs)
        i = 0
        for r in range(1, num_rows + 1):
            for c in range(1, num_cols + 1):
                if i >= len(plots):
                    break
                # One legend for the whole stack: every panel draws the same
                # categories, so repeating the entries per panel would be noise.
                fig = ct.build_panel(plots[i], fig, df, series, lookback_header, r, c,
                                     palette, show_price=show_price,
                                     showlegend=(i == 0))
                i += 1
        height = None
        show_legend = True

    fig = layout_helpers.get_update_xaxes_for_plots(fig, df)
    if faceted:
        fig = layout_helpers.hide_inner_facet_xlabels(fig, num_rows, num_cols)

    weeks = df.attrs.get("lookback_weeks")
    main_title = (f"{asset}: {cot_categories.REPORT_LABELS[report]}"
                  f"{f' ({weeks}w lookback)' if weeks else ''}")
    fig = layout_helpers.get_update_layout_for_plots(fig, num_rows, num_cols, main_title,
                                                     height=height)
    if not show_legend:
        fig.update_layout(showlegend=False)

    return dcc.Graph(figure=fig,
                     id='categories_main_graph',
                     config={
                         'scrollZoom': False,
                         'doubleClick': 'reset',
                         'displayModeBar': True,
                         'modeBarButtonsToRemove': ['pan2d', 'select2d', 'lasso2d'],
                         'displaylogo': False,
                         'responsive': True},
                     style={'width': '100%'})
