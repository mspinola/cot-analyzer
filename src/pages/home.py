import threading
from datetime import datetime
from functools import lru_cache

import cotmetrics.constants as const
import cotmetrics.models as models
import cotmetrics.utils as utils
import dash
import dash_bootstrap_components as dbc
from cotmetrics.indexer import get_indexer
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

import components.plot_helpers as helpers
import components.signal_cards as signal_cards
import viz_config
import viz_constants as vc

skeleton_loader = html.Div([
    dbc.Row([
        dbc.Col(
            dbc.Card(
                dbc.CardBody([
                    html.Div(className="skeleton-text", style={"width": "50%", "height": "18px", "marginBottom": "15px"}),
                    html.Div(className="skeleton-text", style={"width": "100%", "height": "10px", "marginBottom": "8px"}),
                    html.Div(className="skeleton-text", style={"width": "90%", "height": "10px", "marginBottom": "8px"}),
                    html.Div(className="skeleton-text", style={"width": "75%", "height": "10px"}),
                ]),
                style={"backgroundColor": "rgba(30, 30, 30, 0.4)", "border": "1px solid rgba(255,255,255,0.05)", "height": "140px"}
            ), xs=12, sm=6, md=4, lg=3
        ) for _ in range(8)
    ], className="g-1 p-1")
], className="w-100 skeleton-pulse", style={"marginTop": "20px"})

# Register this file as a page
dash.register_page(
    __name__,
    path='/'
)



# Shared by both board panels so they cannot drift apart visually.
_PANEL_STYLE = {
    "backgroundColor": "rgba(20,20,20,0.4)",
    "border": "1px solid rgba(255,255,255,0.05)",
}

# The Active Setups box, with its chrome and its switch static rather than rebuilt by
# the callback. The switch has to live outside the div the callback writes: a control
# rendered into a callback's own output would be recreated on every change, and reading
# it as an Input to that same callback is a circular dependency. So the layout owns the
# box and the callback fills only the header text and the card row.
active_setups_panel = html.Div(
    [
        html.Div(
            [
                html.Div(id="home_setups_header", className="d-flex align-items-center"),
                dbc.Switch(
                    id="home_setups_show_near",
                    label="Approaching",
                    value=True,
                    # Session-persisted like every other control on this page, so the
                    # choice survives a navigation away and back.
                    persistence=True,
                    persistence_type="session",
                    className="mb-0",
                    style={"fontSize": "0.75rem", "color": vc.TEXT_COLOR},
                ),
            ],
            # flex-wrap so the switch drops to its own line on a phone instead of
            # squeezing the title and tally into two wrapped lines each.
            className=("d-flex flex-wrap align-items-center justify-content-between "
                       "mb-2 gap-2"),
        ),
        html.Div(id="home_active_setups"),
    ],
    className="w-100 px-3 pt-3 pb-2 mb-3 rounded",
    style=_PANEL_STYLE,
)

# Weekly Movers, collapsible. Deliberately NOT an accordion like the screener below:
# that one is start_collapsed, and hiding a strip by default is the discovery cost the
# Active Setups panel exists to remove. This opens by default and only closes if the
# reader asks, which is why Active Setups has no equivalent toggle -- it answers the
# page's main question and should never need a click to appear.
#
# Open state rides a session Store because dbc.Collapse has no persistence prop of its
# own, so is_open would otherwise reset on every navigation back to this page.
weekly_movers_panel = html.Div(
    [
        dcc.Store(id="home_movers_open", storage_type="session", data=True),
        html.Div(
            [
                html.Div(id="home_movers_header",
                         className="d-flex align-items-center flex-wrap"),
                # A word, not a chevron. This app never loads the Bootstrap Icons
                # stylesheet, so every `bi bi-*` in it renders as nothing -- a bare
                # chevron button measured 18x6px and was invisible. "Hide"/"Show" also
                # says which way the control goes, and cannot be confused with the
                # up/down delta arrows the cards below already use for direction.
                dbc.Button(
                    "Hide",
                    id="home_movers_toggle",
                    size="sm",
                    color="secondary",
                    outline=True,
                    title="Show or hide the weekly movers",
                    style={"fontSize": "0.7rem", "padding": "2px 10px",
                           "flex": "0 0 auto"},
                ),
            ],
            className=("d-flex flex-wrap align-items-center justify-content-between "
                       "mb-2 gap-2"),
        ),
        dbc.Collapse(html.Div(id="home_weekly_movers"), id="home_movers_collapse",
                     is_open=True),
    ],
    className="w-100 px-3 pt-3 pb-2 mb-3 rounded",
    style=_PANEL_STYLE,
)

def layout(**kwargs):
    # Built per request, not at import. Resolving these at module scope
    # made importing this page require a populated COTDATA_STORE.
    asset_list = tuple(get_indexer().get_asset_classes())
    accordion_items = helpers.build_accordion_skeleton(asset_list)
    signals_feed = html.Div([
        dcc.Store(id='loaded_accordions_store', data=[]),
        dcc.Store(id='dummy-home-session-saver', data=None),
        dbc.Accordion(
            accordion_items,
            id="home_signals_accordion",
            active_item=None,
            start_collapsed=True,
            always_open=True,
            flush=True,
            persistence=True,
            persistence_type="session",
            className="mt-2"
        )
    ])
    signals_view = html.Div(
        [
            html.Div(
                [
                    html.Div([
                        html.I(className="bi bi-view-list me-2", style={"fontSize": "1.2rem", "color": vc.BRIGHTER_TEXT_COLOR}),
                        html.H5("Live Screener Results", className="mb-0", style={"color": vc.BRIGHTER_TEXT_COLOR, "fontWeight": "700"}),
                    ], className="d-flex align-items-center"),
                    html.Div([
                        dbc.Button("Expand All", id="expand_all_btn", size="sm", color="secondary", outline=True, className="me-2", style={"fontSize": "0.75rem"}),
                        dbc.Button("Collapse All", id="collapse_all_btn", size="sm", color="secondary", outline=True, style={"fontSize": "0.75rem"})
                    ])
                ],
                className="d-flex align-items-center justify-content-between mb-3 p-3 rounded",
                style={
                    "backgroundColor": "rgba(40, 40, 40, 0.4)",
                    "border": "1px solid rgba(255,255,255,0.05)",
                    "boxShadow": "inset 0 1px 3px rgba(0,0,0,0.2)"
                }
            ),
            html.Div(
                signals_feed,
                style={
                    "animation": "fadeInUp 0.6s ease-out forwards"
                }
            )
        ],
        className="mb-4 w-100",
        style={'backgroundColor': 'transparent'}
    )

    return html.Div([
        dbc.Container([
            # 1. Hero Banner (Glassmorphism)
            dbc.Row([
                dbc.Col([
                    dbc.Card(
                        dbc.CardBody([
                            html.H4(
                                [html.I(className="bi bi-bar-chart-steps me-2"), "Market Tape Overview"],
                                className="card-title text-center mb-3",
                                style={"color": vc.BRIGHTER_TEXT_COLOR, "fontWeight": "600", "letterSpacing": "1px"}
                            ),
                            html.P(
                                f"All data on this page reflects the official Commitments of Traders reporting snapshot as of Tuesday market close "
                                f"({datetime.strptime(get_indexer().get_available_dates()[0], '%Y-%m-%d').strftime('%B %d, %Y') if get_indexer().get_available_dates() else 'Unknown Date'}).",
                                className="text-center mb-0",
                                style={'color': vc.TEXT_COLOR, 'fontSize': '0.95rem'}
                            )
                        ]),
                        className="mb-4 mt-4 shadow-sm",
                        style={
                            "backgroundColor": "rgba(30, 30, 30, 0.4)",
                            "border": "1px solid rgba(255, 255, 255, 0.1)",
                            "borderRadius": "12px",
                            "backdropFilter": "blur(12px)"
                        }
                    )
                ], width=12)
            ]),

            # 2. Command Center (Glassmorphism Control Panel)
            dbc.Row([
                dbc.Col([
                    html.Div(
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col([
                                    html.Label("Lookback Window", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dbc.Select(
                                        id='home_lookback_selector',
                                        persistence='session',
                                        options=[
                                            {"label": "26 Weeks", "value": "26"},
                                            {"label": "52 Weeks", "value": "52"},
                                            {"label": "Custom", "value": "Custom"},
                                        ],
                                        value="Custom",
                                        className="bg-dark text-white border-secondary",
                                        # Capped rather than left to fill the column: the widest
                                        # option is "26 Weeks", so a full-width select is mostly
                                        # empty chrome on a desktop viewport.
                                        style={'borderRadius': '8px', 'maxWidth': '200px'}
                                    )
                                ], xs=12, md=3, lg=2, className="mb-3 mb-md-0 border-end border-secondary hide-border-below-md"),

                                dbc.Col([
                                    html.Label("Model", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dbc.Select(
                                        id='home_model_selector',
                                        persistence='session',
                                        # No "Both" here: it is a chart comparison view and
                                        # this page renders verdicts, which can only be
                                        # reached by one model at a time.
                                        options=[
                                            {"label": vc.MODEL_LABELS[k], "value": k,
                                             "title": vc.MODEL_TOOLTIPS[k]}
                                            for k in vc.MODEL_CHOICES
                                        ],
                                        value=models.DEFAULT_MODEL.key,
                                        className="bg-dark text-white border-secondary",
                                        style={'borderRadius': '8px', 'maxWidth': '200px'}
                                    )
                                ], xs=12, md=3, lg=2, className="mb-3 mb-md-0 border-end border-secondary hide-border-below-md"),

                                dbc.Col([
                                    html.Label("Signal Filters", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dbc.Checklist(
                                        options=[
                                            {"label": "📈 Bullish Tape Bias", "value": "TAPE_BIAS_BULL"},
                                            {"label": "📉 Bearish Tape Bias", "value": "TAPE_BIAS_BEAR"},
                                        ],
                                        value=[],
                                        id="home_filter_chips",
                                        inline=True,
                                        switch=True,
                                        style={"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "0.95rem"}
                                    )
                                # 6/8 rather than 9/10, so the three columns sum to exactly 12
                                # and the filters sit *beside* the two selects. At 9 and 10
                                # the row overflowed (3+3+9, 2+2+10) and Bootstrap wrapped the
                                # filters onto a second line at every breakpoint, which is the
                                # vertical space this row was spending for nothing.
                                ], xs=12, md=6, lg=8, className="mb-3 mb-md-0 px-md-4"),
                            ], align="center", className="g-3")
                        ]),
                        className="mb-4 shadow",
                        style={
                            "backgroundColor": "rgba(20, 20, 20, 0.6)",
                            "border": "1px solid rgba(255, 255, 255, 0.05)",
                            "borderRadius": "16px",
                            "backdropFilter": "blur(16px)"
                        }
                    )
                ], width=12)
            ]),

            html.Hr(style=vc.hr_style),

            # Setups above movers: a setup is state you can act on, a mover is context for
            # it. It also makes the SETUP/NEAR badges further down the movers strip read as
            # a cross-reference rather than as the place you were meant to discover them.
            dcc.Loading(
                id="loading-home-board",
                type="dot",
                children=[
                    active_setups_panel,
                    weekly_movers_panel,
                ],
                color=vc.BRIGHTER_TEXT_COLOR,
            ),

            dbc.Row([
                signals_view
            ], justify='center')
        ], fluid=True),
    ])


@callback(
    Output('global_lookback_store', 'data', allow_duplicate=True),
    Input('home_lookback_selector', 'value'),
    State('global_lookback_store', 'data'),
    prevent_initial_call=True
)
def update_global_lookback_home(value, current_store_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_store_val:
        return no_update
    return new_val


@callback(
    Output('home_lookback_selector', 'value'),
    Input('global_lookback_store', 'data'),
    State('home_lookback_selector', 'value')
)
def update_local_lookback_home(value, current_local_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_local_val:
        return no_update
    return new_val


# ── positioning model ─────────────────────────────────────────────────────────
# Same two-way sync as Lookback. The chart pages can also hold MODEL_BOTH, which this
# page's selector does not offer, so arriving here with it set resolves to the model the
# overlay draws as its baseline rather than blanking the control.

@callback(
    Output('global_model_store', 'data', allow_duplicate=True),
    Input('home_model_selector', 'value'),
    State('global_model_store', 'data'),
    prevent_initial_call=True
)
def update_global_model_home(value, current_store_val):
    new_val = value if value in vc.MODEL_CHOICES else models.DEFAULT_MODEL.key
    if new_val == current_store_val:
        return no_update
    return new_val


@callback(
    Output('home_model_selector', 'value'),
    Input('global_model_store', 'data'),
    State('home_model_selector', 'value')
)
def update_local_model_home(value, current_local_val):
    new_val = vc.resolve_model_view(value)[0].key
    if new_val == current_local_val:
        return no_update
    return new_val


# 128 rather than 32: the key is (db_time, class, lookback, palette, filters, model), and
# 9 classes x 3 lookbacks x 2 models is already 54 combinations before palettes or filter
# selections multiply it. At 32 the cache could not even hold one full Expand All across
# two models, so switching model and back rebuilt everything. Unlike the indexer's frame
# cache this is cheap to raise: the entries are rendered card trees, not DataFrames.
@lru_cache(maxsize=128)
def _cached_build_asset_class_cards(db_time, ac, lookback, palette_name, filter_types_tuple,
                                    model_key=None):
    # model_key is part of the key, not just an argument: the cards carry setup badges,
    # so the same asset class renders differently under each model and a shared entry
    # would serve one model's verdicts under the other's name.
    filter_types = list(filter_types_tuple)
    color_palette = viz_config.get_palette(palette_name)
    return helpers.build_asset_class_cards(get_indexer(), ac, lookback, color_palette,
                                          model=models.resolve(model_key),
                                          filter_types=filter_types)

@callback(
    Output('dummy-home-session-saver', 'data'),
    [Input('global_lookback_store', 'data'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('home_filter_chips', 'value'),
     Input('global_model_store', 'data')]
)
def update_home_signals(lookback, palette_name, filter_types, model_key):
    if filter_types is None:
        filter_types = []

    if not lookback:
        lookback = "Custom"

    import json
    import os
    try:
        session_state = {
            "lookback": lookback,
            "palette_name": palette_name,
            "filter_types": list(filter_types),
            "model": model_key,
        }
        cache_path = os.path.join(const.CACHE_DIR, "last_home_session.json")
        with open(cache_path, "w") as f:
            json.dump(session_state, f)
    except Exception as e:
        utils.cot_logger.warning(f"Failed to save session state: {e}")

    return no_update



@callback(
    Output({"type": "accordion-body", "index": ALL}, "children"),
    Output('loaded_accordions_store', 'data'),
    Input("home_signals_accordion", "active_item"),
    Input('global_lookback_store', 'data'),
    Input('session_palette_theme_asset_store', 'data'),
    Input('home_filter_chips', 'value'),
    Input('global_model_store', 'data'),
    State({"type": "accordion-body", "index": ALL}, "id"),
    State('loaded_accordions_store', 'data'),
    prevent_initial_call=True
)
def lazy_load_accordion(active_items, lookback, palette_name, filter_types, model_key,
                        body_ids, loaded_store):
    trigger = ctx.triggered_id
    if not trigger:
        raise PreventUpdate

    loaded_store = loaded_store or []

    if not active_items:
        active_items = []
    elif isinstance(active_items, str):
        active_items = [active_items]

    if trigger != "home_signals_accordion":
        # Filters changed, so wipe the cache memory. This forces all
        # currently open accordions to re-render, and closed ones to re-render when opened.
        loaded_store = []

    if filter_types is None:
        filter_types = []

    if not lookback:
        lookback = "Custom"
    filter_types_tuple = tuple(filter_types)
    db_time = get_indexer().last_known_db_time

    outputs = []
    for body_id in body_ids:
        ac = body_id["index"]
        if ac in active_items and ac not in loaded_store:
            content = _cached_build_asset_class_cards(db_time, ac, lookback, palette_name,
                                                     filter_types_tuple, model_key)
            outputs.append(content)
            loaded_store.append(ac)
        else:
            outputs.append(no_update)

    return outputs, loaded_store


# Pre-warm the cache for the default home page load in the background


def _prewarm_cache():
    import json
    import os
    try:
        utils.cot_logger.info("Pre-generating home page signals feed based on last session...")
        db_time = get_indexer().last_known_db_time

        assets = tuple(get_indexer().get_asset_classes())
        lookback = 'Custom'
        palette_name = None
        filter_types = ()
        model_key = models.DEFAULT_MODEL.key

        cache_path = os.path.join(const.CACHE_DIR, "last_home_session.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r") as f:
                    state = json.load(f)
                lookback = state.get("lookback", "Custom")
                palette_name = state.get("palette_name")
                filter_types = tuple(state.get("filter_types", []))
                model_key = state.get("model", models.DEFAULT_MODEL.key)
                utils.cot_logger.info(f"Loaded session defaults from disk: {lookback}")
            except Exception as e:
                utils.cot_logger.warning(f"Could not load last session state: {e}")

        for ac in assets:
            _cached_build_asset_class_cards(db_time, ac, lookback, palette_name, filter_types,
                                           model_key)

        utils.cot_logger.info("Home page individual asset classes pre-generated.")
    except Exception as e:
        utils.cot_logger.error(f"Error prewarming cache: {e}")

threading.Thread(target=_prewarm_cache, daemon=True).start()

@callback(
    Output('home_signals_accordion', 'active_item'),
    Input('expand_all_btn', 'n_clicks'),
    Input('collapse_all_btn', 'n_clicks'),
    prevent_initial_call=True
)
def toggle_all_accordions(expand_clicks, collapse_clicks):
    trigger = ctx.triggered_id
    if trigger == 'expand_all_btn':
        return list(get_indexer().get_asset_classes())
    elif trigger == 'collapse_all_btn':
        return []
    return no_update


# Both strips in one callback, off one sweep. Splitting them would walk all 42
# instruments twice per input change -- and worse, would compute each row's setup state
# twice, which is the one thing the shared board exists to prevent.
@callback(
    Output('home_setups_header', 'children'),
    Output('home_active_setups', 'children'),
    Output('home_movers_header', 'children'),
    Output('home_weekly_movers', 'children'),
    Output({"type": "accordion-item", "index": ALL}, 'title'),
    Input('global_lookback_store', 'data'),
    Input('session_palette_theme_asset_store', 'data'),
    Input('home_filter_chips', 'value'),
    Input('global_model_store', 'data'),
    Input('home_setups_show_near', 'value'),
    State({"type": "accordion-item", "index": ALL}, 'id'),
)
def update_home_board(lookback, palette_name, filter_types, model_key, show_near,
                      item_ids):
    from cotmetrics.movers import get_board

    if not lookback:
        lookback = "Custom"
    palette = viz_config.get_palette(palette_name)
    model = vc.resolve_model_view(model_key)[0]

    rows = get_board(lookback=lookback, filter_types=filter_types, model=model)

    # The Approaching switch is a view of rows already swept, not a different sweep. It
    # is an Input here rather than its own callback so it cannot render against a board
    # built under a stale model or filter.
    setups = signal_cards.build_active_setups_strip(
        rows, palette, model=model, filter_types=filter_types, show_near=show_near,
    )
    # Built even while the movers panel is collapsed. The cards are the cheap half of
    # this callback -- the sweep above is the cost, and it is already paid for the setups
    # panel -- so making the build conditional would buy nothing and would leave stale
    # cards behind the toggle the moment a filter changed.
    movers = signal_cards.build_weekly_movers_strip(rows, palette,
                                                    filter_types=filter_types)

    # Accordion headers off the same sweep, so a class tally can never disagree with the
    # setups strip above it. Built in the order Dash handed back the ids rather than in
    # get_asset_classes() order, which is what keeps each title on its own item.
    titles = [signal_cards.build_accordion_title(i["index"], rows) for i in item_ids]

    return setups.header, setups.body, movers.header, movers.body, titles


# ── the movers collapse ───────────────────────────────────────────────────────
# Two callbacks rather than one: the click *writes* the session store and the store
# *drives* the panel. Toggling dbc.Collapse directly from n_clicks would leave the
# stored value and the rendered state as two sources of truth that disagree the moment
# the page is reloaded with the store already set.

@callback(
    Output('home_movers_open', 'data'),
    Input('home_movers_toggle', 'n_clicks'),
    State('home_movers_open', 'data'),
    prevent_initial_call=True,
)
def toggle_movers_open(n_clicks, is_open):
    return not (True if is_open is None else is_open)


@callback(
    Output('home_movers_collapse', 'is_open'),
    Output('home_movers_toggle', 'children'),
    Input('home_movers_open', 'data'),
)
def apply_movers_open(is_open):
    # None means the session store has nothing yet, which is a first visit, not a
    # collapsed panel. Same reasoning as the Approaching switch: default to showing.
    is_open = True if is_open is None else bool(is_open)
    return is_open, ("Hide" if is_open else "Show")
