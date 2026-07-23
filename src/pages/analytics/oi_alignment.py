import math
import urllib.parse

import cotmetrics.constants as const
import cotmetrics.models as models
import cotmetrics.utils as utils
import dash
import dash_bootstrap_components as dbc
import pandas as pd
from cotmetrics.indexer import get_indexer
from dash import Input, Output, Patch, State, callback, clientside_callback, dcc, html, no_update

import app_utils
import components.plot_helpers as helpers
import components.plot_registry as registry
import components.tv_layout as tv_layout
import viz_config
import viz_constants as vc

# Register this file as a page
dash.register_page(
    __name__,
    path='/oi_alignment'
)

# Which panels this page offers, in stack order. Labels and everything else about them
# comes from the registry, so a plot is described in one place rather than five.
PLOT_IDS = ["oi_alignment", "macd", "willco", "index", "momentum", "zscore",
            "net_pos", "oi_pct", "lrg_sentiment", "max_pain", "max_pain_historical"]

AVAILABLE_PLOTS = registry.labels_for(PLOT_IDS)



def get_collapsible_signals_accordion(signal_row, asset):
    return dbc.Accordion(
        [
            dbc.AccordionItem(
                html.Div(signal_row, style={'marginTop': '10px'}),
                title=html.Div(
                    html.Span(f"Algorithmic Tape-Reading Signals — {asset}", style={"fontWeight": "bold"}),
                    style={'fontSize': '1.08rem', 'color': vc.BRIGHTER_TEXT_COLOR, "textAlign": "left", "width": "100%"}
                ),
                item_id="signals",
                style={"backgroundColor": "transparent", "border": "none"}
            )
        ],
        active_item=["signals"],
        always_open=True,
        persistence=True,
        persistence_type="session",
        id="algorithmic_signals_accordion",
        flush=True,
        className="mb-4 mt-2",
        style={"backgroundColor": "transparent"}
    )

def build_executive_synthesis_card(df, color_palette, target_date=None, asset=None):
    import components.signal_cards as signal_cards
    if target_date is not None and target_date in df.index:
        row = df.loc[target_date]
    else:
        row = df.iloc[-1]

    symbol_str = get_indexer().get_instrument_symbol_from_name(asset)
    synthesis = signal_cards.generate_exhaustive_tape_synthesis(row, symbol_str=symbol_str, df=df)

    tape_bias = synthesis.get("tape_bias", "neutral")

    # Dynamic styling based on tape_bias (since this is the Tape Reading matrix)
    if tape_bias == "bullish":
        accent_color = color_palette[3]  # Green
        border_style = f"1px solid {accent_color}50"
    elif tape_bias == "bearish":
        accent_color = color_palette[0]  # Red
        border_style = f"1px solid {accent_color}50"
    else:
        accent_color = vc.BRIGHTER_TEXT_COLOR  # Neutral (grey/white)
        border_style = "1px solid var(--border-color-dim)"  # Dim border for neutral

    # Map biases to color from color_palette (3: Green, 0: Red, neutral: vc.TEXT_COLOR)
    tape_color = color_palette[3] if tape_bias == "bullish" else (color_palette[0] if tape_bias == "bearish" else vc.TEXT_COLOR)

    # Tape Reading header (larger, no bullet)
    tape_header = html.Div([
        html.Span("Tape Reading [", style={"fontWeight": "bold"}),
        html.Span(tape_bias.upper(), style={"color": tape_color, "fontWeight": "bold"}),
        html.Span(f"]: {synthesis.get('tape_summary')}")
    ], style={"fontSize": "1.08rem", "color": vc.BRIGHTER_TEXT_COLOR, "lineHeight": "1.4", "width": "100%", "textAlign": "left"})

    # Rebuild the matrix as a rich colored Table
    table_header = [
        html.Thead(
            html.Tr([
                html.Th("Component", style={"color": vc.BRIGHTER_TEXT_COLOR, "borderBottom": f"2px solid {accent_color}", "fontWeight": "bold"}),
                html.Th("Status", style={"color": vc.BRIGHTER_TEXT_COLOR, "borderBottom": f"2px solid {accent_color}", "fontWeight": "bold"}),
                html.Th("Description", style={"color": vc.BRIGHTER_TEXT_COLOR, "borderBottom": f"2px solid {accent_color}", "fontWeight": "bold"}),
            ])
        )
    ]

    table_rows = []
    for k, v in synthesis["matrix"].items():
        status = v["status"]
        desc = v["desc"]

        # Color status based on value
        if status == "BULLISH":
            status_color = color_palette[3]  # Green
        elif status == "BEARISH":
            status_color = color_palette[0]  # Red
        else:
            status_color = vc.TEXT_COLOR  # Neutral (plain text color)

        status_text = status if status else "NEUTRAL"

        table_rows.append(
            html.Tr([
                html.Td(k, style={"fontWeight": "bold", "color": vc.TEXT_COLOR, "verticalAlign": "middle"}),
                html.Td(status_text, style={"color": status_color, "fontWeight": "bold", "verticalAlign": "middle"}),
                html.Td(desc, style={"color": vc.TEXT_COLOR, "verticalAlign": "middle"})
            ])
        )

    table_body = [html.Tbody(table_rows)]

    matrix_layout = dbc.Table(
        table_header + table_body,
        bordered=False,
        hover=True,
        responsive=True,
        striped=True,
        style={"fontSize": "0.9rem", "backgroundColor": vc.BACKGROUND_COLOR}
    )

    collapsible_matrix = dbc.Accordion(
        [
            dbc.AccordionItem(
                html.Div([
                    html.Hr(style={"borderColor": accent_color, "opacity": 0.2, "marginTop": "8px", "marginBottom": "12px"}),
                    matrix_layout
                ]),
                title=tape_header,
                item_id="matrix",
                style={"backgroundColor": "transparent", "border": "none"}
            )
        ],
        active_item=["matrix"],
        always_open=True,
        persistence=True,
        persistence_type="session",
        id="executive_synthesis_accordion",
        flush=True,
        style={"backgroundColor": "transparent"}
    )

    card = dbc.Card(
        dbc.CardBody([
            collapsible_matrix
        ]),
        className="mb-4",
        style={"backgroundColor": vc.BACKGROUND_COLOR, "border": border_style, "boxShadow": "0 4px 15px rgba(0,0,0,0.3)"}
    )
    is_neutral = (synthesis.get("overall_bias", "neutral") == "neutral")
    return card, is_neutral

def layout(**kwargs):
    # Built per request, not at import. Resolving these at module scope
    # made importing this page require a populated COTDATA_STORE.
    asset_classes = sorted(get_indexer().get_asset_classes())

    return html.Div([
        dbc.Container([

            # Primary Data Filters
            dbc.Row([
                dbc.Col([
                    html.Label("Asset Class", style=vc.label_style),
                    dbc.RadioItems(
                        id='oi_alignment_asset_class_selector',
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
                    html.Label("Asset Selector", style=vc.label_style),
                    dcc.Dropdown(
                        id='oi_alignment_single_asset_filter_input',
                        options=[{'label': m, 'value': m} for m in sorted(get_indexer().get_assets_for_asset_class(get_indexer().get_default_asset_class()))],
                        clearable=False,
                        searchable=True,
                        className="mb-3 dash-dropdown bg-dark text-white",
                        style={'width': '200px'}
                    ),
                ], xs=12, md="auto"),

            ], align="center", className="mb-2"),

            dbc.Row([
                dbc.Col([
                    html.Label("Visible Plots", style=vc.label_style),
                    dcc.Dropdown(
                        persistence=True,
                        id='oi_alignment_plot_selector',
                        options=[{'label': v, 'value': k} for k, v in AVAILABLE_PLOTS.items()],
                        value=list(AVAILABLE_PLOTS.keys()),  # Default to all selected
                        multi=True,
                        className="mb-3 dash-dropdown bg-dark text-white",
                        style={'width': '200px'}
                    ),
                ], xs=12, md="auto"),
                dbc.Col([
                    html.Label("Lookback:", style=vc.label_style),
                    dbc.Select(
                        id='oi_alignment_lookback_selector',
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
                    html.Label("Model:", style=vc.label_style),
                    dbc.Select(
                        id='oi_alignment_model_selector',
                        persistence='session',
                        options=[
                            {"label": vc.MODEL_LABELS[v], "value": v}
                            for v in vc.MODEL_VIEW_CHOICES
                        ],
                        value=models.DEFAULT_MODEL.key,
                        className="mb-3 bg-dark text-white border-secondary",
                        style={'width': '110px'}
                    ),
                    html.Div(id='oi_alignment_model_note',
                             className="text-muted",
                             style={'fontSize': '0.7rem', 'marginTop': '-10px'}),
                ], xs=12, md="auto"),

                dbc.Col([
                    html.Label("Cols", style=vc.label_style),
                    dbc.Select(
                        id='oi_alignment_columns_selector',
                        persistence='session',
                        options=[
                            {"label": "1", "value": "1"},
                            {"label": "2", "value": "2"},
                            {"label": "3", "value": "3"},
                        ],
                        value="1", # We'll handle responsive defaults in the callback
                        className="mb-3 bg-dark text-white border-secondary",
                        style={'width': '70px'}
                    )
                ], xs=12, md="auto"),

                dbc.Col([
                    html.Div([
                        html.Label("Delta $ Overlay", style=vc.label_style),
                        dbc.RadioItems(
                            id='oi_alignment_price_overlay_selector',
                            persistence=True,
                            options=[
                                {"label": "On", "value": "On"},
                                {"label": "Off", "value": "Off"},
                            ],
                            value=False,
                            inline=True,
                            className="mb-3",
                            labelStyle={'color': 'white', 'marginRight': '0px', 'marginLeft': '0px', 'fontSize': '0.85rem'},
                            inputStyle={'opacity': '0.6'}
                        )
                    ], id="price_overlay_container"),
                    dbc.Tooltip(
                        "Overlays the +/- change in front month price on the graph. Can be slow!",
                        target="price_overlay_container",
                        placement="bottom"
                    )
                ], xs=12, md="auto"),
                dbc.Col([
                    dbc.Button("📸 Export PNG", id="oi_alignment_download_img_btn", style={"color": vc.TEXT_COLOR}, size="sm", className="ms-2")
                ], xs=12, md="auto"),
            ], align="center", className="mb-2"),

            html.Hr(style=vc.hr_style),

            # The browser writes the zoom window here: {"xEnd": <date or None>, "stamp": n}.
            # The signal panel reads it to follow the right edge of the chart.
            dcc.Store(id='oi_alignment_zoom_sink'),

            html.Div(id="oi_alignment_export_container", children=[
                html.Div(id='oi_alignment_signal_panel'),

                html.Div([
                    html.Div(
                        tv_layout.get_tv_overlay_component(prefix=""),
                        style={
                            "position": "absolute",
                            "top": "60px",    # Adjust this to move it up/down to match your legend perfectly
                            "left": "40px",   # Pushes it slightly off the left wall
                            "zIndex": "1000"  # Ensures the button is clickable and sits ON TOP of the chart
                        }
                    ),

                    dbc.Row([
                        dcc.Loading(
                            id="loading_oi_alignment_graph",
                            type="default",  # Options: "graph", "cube", "circle", "dot", or "default"
                            children=html.Div(
                                [
                                    dcc.Graph(
                                        id='oi_alignment_main_graph',
                                        style={'display': 'none'}
                                    )
                                ],
                                id='oi_alignment_stack'
                            ),
                            color=vc.BRIGHTER_TEXT_COLOR
                        )
                    ], justify='center')
                ], style={"position": "relative", "width": "100%"})
            ], style={"backgroundColor": "transparent"})
        ], fluid=True),
    ])


@callback(
    Output('global_lookback_store', 'data', allow_duplicate=True),
    Input('oi_alignment_lookback_selector', 'value'),
    State('global_lookback_store', 'data'),
    prevent_initial_call=True
)
def update_global_lookback(value, current_store_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_store_val:
        return no_update
    return new_val


@callback(
    Output('oi_alignment_lookback_selector', 'value'),
    Input('global_lookback_store', 'data'),
    State('oi_alignment_lookback_selector', 'value')
)
def update_local_lookback(value, current_local_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_local_val:
        return no_update
    return new_val


# ── positioning basis ─────────────────────────────────────────────────────────
# Shares global_model_store with the Graphs page rather than keeping a local copy, so
# picking "% of OI" on one page and navigating to the other does not silently switch
# back. Same store, same two-way sync, same demotion rules.

@callback(
    Output('global_model_store', 'data', allow_duplicate=True),
    Input('oi_alignment_model_selector', 'value'),
    State('global_model_store', 'data'),
    prevent_initial_call=True
)
def update_global_model(value, current_store_val):
    new_val = value if value in vc.MODEL_VIEW_CHOICES else models.DEFAULT_MODEL.key
    if new_val == current_store_val:
        return no_update
    return new_val


@callback(
    Output('oi_alignment_model_selector', 'value'),
    Input('global_model_store', 'data'),
    State('oi_alignment_model_selector', 'value')
)
def update_local_model(value, current_local_val):
    new_val = value if value in vc.MODEL_VIEW_CHOICES else models.DEFAULT_MODEL.key
    if new_val == current_local_val:
        return no_update
    return new_val


@callback(
    Output('global_model_store', 'data', allow_duplicate=True),
    Input('oi_alignment_plot_selector', 'value'),
    State('global_model_store', 'data'),
    prevent_initial_call=True
)
def demote_both_when_unsupported(selected_plots, model_view):
    """Fall back to Raw when nothing on the stack can overlay, so the control never
    displays a view the figure isn't drawing."""
    if model_view == vc.MODEL_BOTH and not _overlayable(selected_plots):
        return models.DEFAULT_MODEL.key
    return no_update


def _basis_aware(selected_plots):
    return [p for p in (selected_plots or []) if p in registry.BASIS_AWARE_PLOTS]


def _overlayable(selected_plots):
    return [p for p in (selected_plots or []) if p in registry.BASIS_OVERLAY_SPEC]


def _panel_model(model_view):
    """Model for a signal panel rebuilt outside the stack callback.

    The overlay charts both bases, but a panel of scalar readings can only speak one,
    so it falls back to the model whose basis the overlay draws as its solid series.
    """
    return vc.resolve_model_view(model_view)[0]


@callback(
    Output('oi_alignment_model_selector', 'options'),
    Output('oi_alignment_model_selector', 'disabled'),
    Output('oi_alignment_model_note', 'children'),
    Input('oi_alignment_plot_selector', 'value')
)
def update_model_availability(selected_plots):
    """Offer only the views this stack can actually draw, and say why when one is missing.

    Unlike Graphs this page renders many panels at once, so the question is whether
    *any* selected panel responds rather than whether the single one does. A control
    that silently does nothing teaches the user it is broken.
    """
    def opts(views):
        return [{"label": vc.MODEL_LABELS[v], "value": v} for v in views]

    aware = _basis_aware(selected_plots)
    if not aware:
        # One selected plot means we can say *why* it does not respond; several means
        # the specific reasons stop being worth the line of text.
        note = (registry.BASIS_INVARIANT_NOTE.get(selected_plots[0], vc.NO_BASIS_PLOTS_NOTE)
                if selected_plots and len(selected_plots) == 1 else vc.NO_BASIS_PLOTS_NOTE)
        return opts(vc.MODEL_CHOICES), True, note
    if _overlayable(selected_plots):
        return opts(vc.MODEL_VIEW_CHOICES), False, ""
    return opts(vc.MODEL_CHOICES), False, vc.NO_OVERLAY_NOTE


@callback(
    Output('oi_alignment_columns_selector', 'value'),
    Input('url', 'pathname'),
    State('oi_alignment_columns_selector', 'value')
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
    Output("tv-modal", "is_open"),
    Output("tv-iframe", "src"),
    Output("tv-modal-title", "children"),
    Input("open-tv-modal-btn", "n_clicks"),
    State("tv-modal", "is_open"),
    State("oi_alignment_single_asset_filter_input", "value"),
    prevent_initial_call=True
)
def toggle_tv_modal(n_clicks, is_open, asset_name):
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


# Rescaling the y-axes to the visible window is pure arithmetic over data the browser
# already holds, so it runs there. See autoscale_y_axes in assets/clientside.js.
#
# It writes to the figure through Plotly rather than returning one. Returning a figure
# would hand back the stored x-range and undo the zoom that triggered it.
#
# It also reports the rightmost visible date on oi_alignment_zoom_sink, which is how the
# signal panel follows the zoom.
#
# That indirection is load-bearing. A server callback listening to relayoutData does
# fire with the right x-range, but the Plotly.relayout this performs emits a *second*
# relayoutData milliseconds later carrying the y-axis keys, and Dash drops the first
# answer as superseded before it reaches the DOM. The panel appeared frozen while the
# server was returning correct content the whole time. Only a real x-zoom writes the
# store, so nothing supersedes it.
clientside_callback(
    "window.dash_clientside.clientside.autoscale_y_axes",
    Output('oi_alignment_zoom_sink', 'data'),
    Input('oi_alignment_main_graph', 'relayoutData'),
    State('oi_alignment_main_graph', 'id'),
    prevent_initial_call=True
)


def _zoom_target_date(zoom, df):
    """The report the panel should show for the browser's reported zoom window.

    `zoom` is what the clientside autoscale wrote: {"xEnd": <date or None>, "stamp": n}.
    A null xEnd means the window was reset, so the panel goes back to the latest report.
    Otherwise it is the last report at or before the rightmost visible date, so the
    panel reads as of what the right edge of the chart is showing.
    """
    x_end_raw = (zoom or {}).get("xEnd")
    if not x_end_raw:
        return None

    x_end = pd.to_datetime(x_end_raw)
    if x_end.tz is not None:
        x_end = x_end.tz_localize(None)
    # Compare in the frame's own tz before slicing.
    x_end_cmp = x_end.tz_localize(df.index.tz) if df.index.tz is not None else x_end
    visible = df.index[df.index <= x_end_cmp]
    return visible[-1] if not visible.empty else None


@callback(
    [Output("oi_alignment_signal_panel", "children", allow_duplicate=True),
     Output("oi_alignment_main_graph", "figure", allow_duplicate=True)],
    [Input("oi_alignment_main_graph", "clickData"),
     Input('oi_alignment_zoom_sink', 'data'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('global_lookback_store', 'data'),
     Input('oi_alignment_single_asset_filter_input', 'value')],
    [State("oi_alignment_main_graph", "figure"),
     State('global_model_store', 'data')],
    prevent_initial_call=True
)
def sync_signal_board_to_crosshair(click_data, zoom, palette_name, lookback,
                                   asset, current_fig, model_view):
    """Move the signal panel to whichever date the user is pointing at.

    There are two ways to point: click a point, which also drops a crosshair, or pan and
    zoom, which reads the rightmost visible date. Both live here rather than in separate
    callbacks so the panel has one writer and the two cannot race each other.

    The zoom arrives on a store the browser writes, not from relayoutData directly. See
    the note above the clientside autoscale for why reading relayoutData here loses.
    """
    if not asset:
        return no_update, no_update

    triggered = dash.callback_context.triggered
    by_zoom = bool(triggered) and triggered[0]["prop_id"].endswith("zoom_sink.data")

    model = _panel_model(model_view)
    if not by_zoom and (not click_data or 'points' not in click_data):
        return no_update, no_update

    df = get_indexer().get_symbols_data(asset, lookback, model.basis)
    if df is None or df.empty:
        return no_update, no_update
    # An empty palette store means the default, not "no palette".
    color_palette = viz_config.get_palette(palette_name)

    if by_zoom:
        target_date = _zoom_target_date(zoom, df)
        signal_row = helpers.build_signal_panel(
            df=df, asset=asset, color_palette=color_palette,
            target_date=target_date, model=model,
        )
        exec_card, _ = build_executive_synthesis_card(
            df, color_palette, target_date=target_date, asset=asset)
        # The figure is left alone on purpose: returning one here would hand back the
        # stored x-range and undo the zoom that triggered this.
        return (html.Div([exec_card, get_collapsible_signals_accordion(signal_row, asset)]),
                no_update)

    try:
        #  Extract the date from the first trace the mouse is touching
        clicked_date_str = click_data['points'][0]['x']
        hovered_date = pd.to_datetime(clicked_date_str)

        # Rebuild the signal panel for that specific point in time
        # (Assuming df, asset, and color_palette are accessible in this scope)
        updated_signal_ui = helpers.build_signal_panel(
            df=df,
            asset=asset,
            color_palette=color_palette,
            target_date=hovered_date,
            model=model,
        )

        exec_card, is_neutral = build_executive_synthesis_card(df, color_palette, target_date=hovered_date, asset=asset)

        # Get existing shapes from current figure layout to avoid overwriting them
        existing_shapes = []
        if current_fig and 'layout' in current_fig and 'shapes' in current_fig['layout']:
            existing_shapes = current_fig['layout']['shapes']

        # Filter out any old crosshair lines (which are lines with yref='paper')
        updated_shapes = [
            s for s in existing_shapes
            if not (s.get('type') == 'line' and s.get('yref') == 'paper')
        ]

        # Append the new crosshair line
        updated_shapes.append({
            'type': 'line',
            'x0': clicked_date_str,
            'x1': clicked_date_str,
            'y0': 0,
            'y1': 1,
            'yref': 'paper',  # Spans the entire height of the chart
            'line': {'color': 'rgba(255,255,255,0.5)', 'width': 1, 'dash': 'dot'}
        })

        patched_fig = Patch()
        patched_fig['layout']['shapes'] = updated_shapes

        # Use Patch to update layout shapes dynamically
        collapsible_signals = get_collapsible_signals_accordion(updated_signal_ui, asset)

        return html.Div([exec_card, collapsible_signals]), patched_fig

    except Exception as e:
        print(f"Hover Sync Error: {e}")
        return no_update, no_update


@callback(
    [Output('oi_alignment_stack', 'children'),
     Output('oi_alignment_signal_panel', 'children')],
    [Input('session_palette_theme_asset_store', 'data'),
     Input('oi_alignment_single_asset_filter_input', 'value'),
     Input('global_lookback_store', 'data'),
     Input('oi_alignment_plot_selector', 'value'),
     Input('oi_alignment_columns_selector', 'value'),
     Input('oi_alignment_price_overlay_selector', 'value'),
     Input('global_model_store', 'data')]
)
def update_oi_alignment_stack(palette_name, asset, lookback, selected_plots, num_cols,
                              price_overlay, model_view):
    print(f"Updating oi_alignment stack with asset={asset}, lookback={lookback}, price_overlay={price_overlay}")
    utils.cot_logger.info(f"Updating oi_alignment stack with asset={asset}, lookback={lookback}, selected_plots={selected_plots}, num_cols={num_cols}")

    selected_plots = registry.sanitize_selection(selected_plots, AVAILABLE_PLOTS)

    if not asset or not selected_plots or selected_plots == 0:
        empty_message = html.P('SELECT ASSET AND PLOTS', style={'textAlign': 'center', 'color': vc.BRIGHTER_TEXT_COLOR})
        return empty_message, html.Div()

    if model_view not in vc.MODEL_VIEW_CHOICES:
        model_view = models.DEFAULT_MODEL.key
    # Nothing on the stack responds, or nothing can overlay: fall back to the default
    # model rather than letting a stale session value pick a view the figure isn't
    # drawing.
    if not _basis_aware(selected_plots):
        model_view = models.DEFAULT_MODEL.key
    elif model_view == vc.MODEL_BOTH and not _overlayable(selected_plots):
        model_view = models.DEFAULT_MODEL.key

    # One resolution point: the model carries the gate, and the basis it plots follows.
    # A single-basis view loads one frame; the overlay needs both to compare.
    model, is_overlay = vc.resolve_model_view(model_view)
    basis = model.basis

    df = get_indexer().get_symbols_data(asset, lookback, basis)
    if df is None:
        return html.P("No Data", style={'textAlign': 'center', 'color': vc.BRIGHTER_TEXT_COLOR}), html.Div()

    df_norm = None
    if is_overlay:
        df_norm = get_indexer().get_symbols_data(asset, lookback, const.BASIS_OI_NORM)
        if df_norm is None:
            return html.P("No Data", style={'textAlign': 'center', 'color': vc.BRIGHTER_TEXT_COLOR}), html.Div()

    # The signal panel and the executive synthesis below read the same df as the charts,
    # so the whole page speaks one model rather than charting one basis and judging it
    # by another's rule. The band itself travels on the model into PlotCtx.

    # Net Positions plots the underlying series by name rather than via the generic
    # aliases, so it has to pick the basis pair itself.
    if basis == const.BASIS_OI_NORM:
        comm_net, lrg_net, sml_net = const.COMM_NET_NORM, const.LARGE_NET_NORM, const.SMALL_NET_NORM
        net_y_title = "net / OI"
    else:
        comm_net, lrg_net, sml_net = const.COMM_NET, const.LARGE_NET, const.SMALL_NET
        net_y_title = "net position"
    color_palette = viz_config.get_palette(palette_name)
    instrument = get_indexer().get_instrument_from_name(asset)
    titles = [registry.plot_title(p, asset=asset, instrument=instrument,
                                  basis_view=basis, is_overlay=is_overlay)
              for p in selected_plots]

    num_cols = int(num_cols)
    num_selected = len(selected_plots)
    num_rows = math.ceil(num_selected / num_cols)

    specs = registry.subplot_specs(selected_plots, show_price=True, num_cols=num_cols)

    is_shared_x = False if any(p in ["max_pain", "max_pain_historical"] for p in selected_plots) else True
    fig = helpers.get_make_subplots_for_plots(num_rows, num_cols, titles, specs, shared_xaxes=is_shared_x)

    plot_idx = 0
    oi_legend_added = False
    decorator_targets = []
    price_delta_targets = []
    setup_comms_only = get_indexer().is_equity(asset)
    for r in range(1, num_rows + 1):
        for c in range(1, num_cols + 1):
            if plot_idx < num_selected:
                p = selected_plots[plot_idx]

                # Overlay draws both bases on one axis, so it replaces the panel rather
                # than varying it. Panels that cannot overlay fall through and render
                # raw, same as the basis-invariant ones.
                if is_overlay and p in registry.BASIS_OVERLAY_SPEC:
                    value_col, y_title, y_range, zero_line = registry.BASIS_OVERLAY_SPEC[p]
                    fig = helpers.get_basis_overlay_plot(
                        fig, df, df_norm, value_col, r, c, color_palette,
                        y_title=y_title, y_range=y_range, show_oi=True,
                        zero_line=zero_line)
                    plot_idx += 1
                    continue

                spec = registry.REGISTRY[p]
                ctx = registry.PlotCtx(
                    fig=fig, df=df, df_norm=df_norm, row=r, col=c,
                    palette=color_palette, show_price=True, asset=asset, model=model,
                    net_cols=(comm_net, lrg_net, sml_net), y_title=net_y_title,
                    setup_comms_only=setup_comms_only)
                fig = spec.build(ctx) or fig
                if spec.decorate:
                    ctx.fig = fig
                    fig = spec.decorate(ctx) or fig

                # Panel-specific follow-ups the registry has no business knowing about:
                # this page decorates its price panel with the tape-reading markers, and
                # Open Interest earns a legend entry only once however many panels use it.
                if p == "oi_alignment":
                    decorator_targets.append((r, c))
                    if price_overlay == "On":
                        price_delta_targets.append([r, c, False])
                elif p == "net_pos" and not oi_legend_added:
                    fig = helpers.add_open_interest_legend(fig, color_palette)
                    oi_legend_added = True

                plot_idx += 1

    if decorator_targets:
        fig = helpers.get_oi_alignment_decorators(
            fig, df, decorator_targets, color_palette,
            offset_pct=0.06,
            show_legend=True,
            show_oi_legend=(not oi_legend_added)
        )

    if price_delta_targets:
        # User requested 1-week price delta highlighting for maximum accuracy
        # A moving average of 1 would just be the current price, so we use shift(1)
        ma = df[const.CLOSING_PRICE].shift(1)
        uptrend_mask = (df[const.CLOSING_PRICE] >= ma)
        downtrend_mask = (df[const.CLOSING_PRICE] < ma)
        fig = helpers.add_trend_regime_highlighting(fig, df, ma, uptrend_mask, downtrend_mask, price_delta_targets)

    exclude_xaxes = [i for i, p in enumerate(selected_plots) if p in ["max_pain", "max_pain_historical"]]
    fig = helpers.get_update_xaxes_for_plots(fig, df, exclude_plot_indices=exclude_xaxes)
    fig = helpers.get_update_layout_for_plots(fig, num_rows, num_cols, asset, show_scale_toggle=False)

    # Generate the signal panel based on the latest data and thresholds
    is_equity = get_indexer().is_equity(asset)
    signal_row = helpers.build_signal_panel(df, asset, color_palette, is_equity=is_equity, model=model)

    exec_card, is_neutral = build_executive_synthesis_card(df, color_palette, asset=asset)

    collapsible_signals = get_collapsible_signals_accordion(signal_row, asset)

    # Return the graph and the panel
    return dcc.Graph(
                     id='oi_alignment_main_graph',
                     figure=fig,
                     clear_on_unhover=False,
                     config={
                         'scrollZoom': False,
                         'doubleClick': 'reset',
                         'displayModeBar': True,
                         'modeBarButtonsToRemove': ['pan2d', 'select2d', 'lasso2d'],
                         'displaylogo': False,
                         'responsive': True},
                         style={'width': '100%'}
                    ), html.Div([exec_card, collapsible_signals])

@callback(
    Output('oi_alignment_asset_class_selector', 'value'),
    Output('oi_alignment_single_asset_filter_input', 'options'),
    Output('oi_alignment_single_asset_filter_input', 'value'),
    Input('url', 'search'),
    Input('oi_alignment_asset_class_selector', 'value'),
    State('oi_alignment_single_asset_filter_input', 'value')
)
def update_oi_alignment_asset_options(search, selected_class, current_asset):
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
    is_initial_load = (triggered_id == '.' or triggered_id is None)

    # 1. URL Routing overrides everything on load
    if (is_initial_load or triggered_id == 'url') and search:
        parsed = urllib.parse.parse_qs(search.lstrip('?'))
        if 'asset' in parsed:
            asset_name = parsed['asset'][0]
            instrument = get_indexer().get_instrument_from_name(asset_name)
            if instrument:
                forced_class = instrument.asset_class
                assets = sorted(get_indexer().get_assets_for_asset_class(forced_class))
                options = [{'label': m, 'value': m} for m in assets]
                return forced_class, options, asset_name

    # 2. Normal class selector logic
    if not selected_class:
        selected_class = get_indexer().get_default_asset_class()

    assets = sorted(get_indexer().get_assets_for_asset_class(selected_class))
    options = [{'label': m, 'value': m} for m in assets]

    if current_asset in assets:
        return no_update, options, current_asset
    else:
        return no_update, options, assets[0] if assets else None

clientside_callback(
    "window.dash_clientside.clientside.export_oi_alignment_image",
    Output('oi_alignment_download_img_btn', 'n_clicks'),
    Input('oi_alignment_download_img_btn', 'n_clicks'),
    State('oi_alignment_single_asset_filter_input', 'value'),
    prevent_initial_call=True
)
