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
from components import controls

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
    path='/',
    title='COT Analyzer | Free Commitments of Traders Charts & Signals',
    description='Free weekly Commitments of Traders analysis: positioning '
                'indexes, signal heatmap, crowding boards and charts for 40+ '
                'futures markets, updated with every CFTC release.',
)

# Layout runs per request; the wiring must not.
controls.register_lookback('home_lookback_selector')
controls.register_model('home_model_selector')



# The two board panels are deliberately NOT the same weight any more. They used to
# share one style, and the result was that Biggest Commercial Moves won the page: it
# sits second, but its cards carry big saturated deltas and multiple badges, so on an
# identical panel it out-shouted the strip above it. A setup is what a reader came for
# and a mover is the context for it, so the chrome now says which is which instead of
# leaving the card contents to fight it out.
_SETUPS_PANEL_STYLE = {
    "backgroundColor": "rgba(28,28,28,0.55)",
    "border": "1px solid rgba(255,255,255,0.10)",
    "boxShadow": "0 1px 12px rgba(0,0,0,0.35)",
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
                    # On by default now. It was off while the approaching tier was
                    # interleaved among the full setups at the same size, where it
                    # doubled the length of the strip and diluted it. The tier is
                    # its own smaller block below the featured cards now, so showing
                    # it costs a fraction of the room and the switch goes back to
                    # being a way to get rid of it rather than a way to find it.
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
    style=_SETUPS_PANEL_STYLE,
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
            # One header row, not three. The navbar above already carries the app
            # name and the release date, and this page used to restate both in a
            # "Market Tape Overview" hero card: a title naming the page you are
            # already on, over a sentence repeating the navbar's badge in longer
            # words. Between the navbar, that card and the control row below, a
            # reader spent the whole first screen on chrome before reaching a
            # setup. The one thing the card said that the navbar does not -- that
            # the snapshot is Tuesday's close, not today's -- now rides in the
            # control row as a caption, where it sits beside the controls that
            # scope it rather than in a band of its own.
            dbc.Row([
                dbc.Col([
                    html.Div(
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col([
                                    controls.label("Lookback"),
                                    # Capped rather than left to fill the column: the widest
                                    # option is "26 Weeks", so a full-width select is mostly
                                    # empty chrome on a desktop viewport.
                                    controls.lookback_select(
                                        'home_lookback_selector',
                                        style={'borderRadius': '8px',
                                               'maxWidth': '200px'})
                                ], xs=12, md=3, lg=2, className="mb-3 mb-md-0 border-end border-secondary hide-border-below-md"),

                                dbc.Col([
                                    controls.label("Model"),
                                    # MODEL_CHOICES, no "Both": it is a chart comparison
                                    # view and this page renders verdicts, which can only
                                    # be reached by one model at a time. localStorage,
                                    # unlike the session default: which model you read
                                    # the board under is a standing preference.
                                    controls.model_select(
                                        'home_model_selector',
                                        persistence=True,
                                        persistence_type='local',
                                        style={'borderRadius': '8px',
                                               'maxWidth': '200px'})
                                ], xs=12, md=3, lg=2, className="mb-3 mb-md-0 border-end border-secondary hide-border-below-md"),

                                dbc.Col([
                                    # The label row carries the snapshot caption on its
                                    # right, in the whitespace this column already had.
                                    # It is what the deleted hero card was actually for:
                                    # the reader has to know these readings are Tuesday's
                                    # close and not today's, and the navbar's release
                                    # badge does not say that. Costing it zero height is
                                    # the point -- as its own band it was a third header
                                    # row for one clause.
                                    html.Div([
                                        html.Label("Signal Filters", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase", "marginBottom": 0}),
                                        html.Span(
                                            f"COT snapshot \u00b7 Tuesday close, "
                                            f"{datetime.strptime(get_indexer().get_available_dates()[0], '%Y-%m-%d').strftime('%B %d, %Y') if get_indexer().get_available_dates() else 'date unknown'}",
                                            style={"color": vc.TEXT_COLOR, "fontSize": "0.72rem"},
                                        ),
                                    ], className="d-flex flex-wrap align-items-baseline justify-content-between gap-2 mb-1"),
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
                        className="mt-3 mb-3 shadow",
                        style={
                            "backgroundColor": "rgba(20, 20, 20, 0.6)",
                            "border": "1px solid rgba(255, 255, 255, 0.05)",
                            "borderRadius": "16px",
                            "backdropFilter": "blur(16px)"
                        }
                    )
                ], width=12)
            ]),

            # No rule between the control row and the board. The control card is
            # already a bounded panel and each board panel below is another, so the
            # <hr> was a divider between two things nothing was running together.

            # The board is the setups panel and nothing else now. "Biggest Commercial
            # Moves This Week" used to sit under it, and it is gone rather than
            # demoted: a large move on a market that is not at or near a gate is not
            # a thing anyone can act on, so the strip spent eight cards and a
            # panel-width heading answering a question with no follow-up. The
            # movement that DOES matter -- a setup that arrived this week versus one
            # that has been sitting there -- was already on the setup cards as the
            # delta beside the index, and it stays there.
            dcc.Loading(
                id="loading-home-board",
                type="dot",
                children=[active_setups_panel],
                color=vc.BRIGHTER_TEXT_COLOR,
            ),

            dbc.Row([
                signals_view
            ], justify='center')
        ], fluid=True),
    ])


# 128 rather than 32: the key is (db_time, class, lookback, palette, filters, model), and
# 9 classes x 3 lookbacks x 3 models is already 81 combinations before palettes or filter
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


# The setups strip and every accordion title off ONE sweep. They must not be split:
# a second pass would walk all 42 instruments again per input change and, worse, would
# compute each row's setup state twice, which is how a class tally came to disagree
# with the strip above it. This mattered more when there were two strips here; it still
# matters, because the accordion titles carry the same tallies.
@callback(
    Output('home_setups_header', 'children'),
    Output('home_active_setups', 'children'),
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
    # Accordion headers off the same sweep, so a class tally can never disagree with the
    # setups strip above it. Built in the order Dash handed back the ids rather than in
    # get_asset_classes() order, which is what keeps each title on its own item.
    titles = [signal_cards.build_accordion_title(i["index"], rows) for i in item_ids]

    return setups.header, setups.body, titles
