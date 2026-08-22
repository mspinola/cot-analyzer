"""Cross-asset crowding strip.

The whole board on one screen. Same frame the Heatmap reads (`get_matrix_data`), same
model selector, same week: this draws no number the grid does not already carry, and it
computes nothing of its own. What it changes is the scan cost. A grid is read column by
column; a strip is read at a glance, which is the only thing it is for.

The figure work lives in `components.strip_traces`, which is pure over the frame, so
the layout can be tested without a store. This module is the controls, the caption, the
legend and the wiring. The legend renders here as HTML rather than inside a figure:
drawn in the first figure it cost that column ~40px of top margin the other column did
not pay (Plotly grows the margin to fit a legend it cannot lay out in the space
predicted for it), so the two boards started at different heights.

The caption is load-bearing rather than decorative. It carries the report date, which
the printed reports this was modelled on leave off entirely, and it says which window
each row was measured over, which matters here in a way it does not on a per-market
page: `CustomLookbackWeeks` is tuned per market, so a cross-asset ranking taken on the
Custom lookback compares markets measured over different windows. That is fine for a
per-market signal and is a hazard for a ranking, so the caption says so rather than
letting the page imply a uniform basis it does not have.
"""

from datetime import datetime

import cotmetrics.models as models
import dash
import dash_bootstrap_components as dbc
from cotmetrics.indexer import get_indexer
from cotmetrics.reports import get_matrix_data
from dash import Input, Output, State, callback, dcc, html, no_update

import app_utils
import components.strip_traces as strip_traces
import viz_config
import viz_constants as vc
from components.plot_colors import grid_colors

dash.register_page(__name__, path='/strip')

SORT_BY_INDEX = "index"
SORT_ALPHA = "alpha"


def caption(report_date, lookback, model, skipped, hidden=0,
            mark=strip_traces.MARK_DOT):
    """The two lines under the controls.

    Everything here is a fact the picture cannot carry on its own, and the list grew by
    one sentence after the first read of the page produced three questions in a row:
    what are the numbers, what are the ticks, and is this Commercials only. A legend
    that names the marks answers the last two once a reader looks at it; saying it in
    words is what stops them having to.
    """
    try:
        pretty = datetime.strptime(report_date, '%Y-%m-%d').strftime('%B %d, %Y')
    except (TypeError, ValueError):
        pretty = "an unknown date"
    if lookback in ("26", "52"):
        window = f"a uniform {lookback}-week window"
    else:
        window = ("each market's own tuned lookback, so the windows differ between "
                  "rows")
    mark_word = "bar" if mark == strip_traces.MARK_BAR else "diamond"
    legs = [strip_traces.LEG_LABELS[leg] for leg in model.spec_legs
            if leg in strip_traces.LEG_LABELS]
    if legs:
        tick_note = (f"Ticks are the other legs this gate reads ({', '.join(legs)}), "
                     f"and one brightens where it is through its own extreme opposite "
                     f"Commercials. ")
    else:
        tick_note = ""
    dropped = ""
    if hidden:
        dropped += f" {hidden} market(s) hidden by the Show/Side filters."
    if skipped:
        dropped = (f" {len(skipped)} market(s) have no index this week and are not "
                   f"shown: {', '.join(sorted(skipped))}.")
    return (
        f"Positioning as of Tuesday {pretty}, gated on {model.title}, measured over "
        f"{window}. The {mark_word} is the COMMERCIAL positioning index, 0-100; hover "
        f"any row for the exact figures. "
        f"{tick_note}"
        f"Its colour is the model's verdict on the whole row, not on its own value, so "
        f"a dim {mark_word} deep in a band is a market at an extreme with another leg "
        f"blocking it.{dropped}")


def legend(model, colors, palette, mark):
    """The figure key, rendered as one line of page chrome above both columns.

    `strip_traces.legend_items` says what the entries are; this only turns them into
    coloured text. Glyphs stand in for the plot symbols: the diamond and square are the
    marks themselves, the vertical bar is the line-ns tick, the ring is the hollow
    prior-position circle.
    """
    glyphs = {
        strip_traces.GLYPH_MARK:
            "■" if mark == strip_traces.MARK_BAR else "◆",
        strip_traces.GLYPH_TICK: "│",
        strip_traces.GLYPH_CIRCLE: "○",
    }
    groups = []
    for title, entries in strip_traces.legend_items(model, colors, palette, mark):
        bits = [html.Span(f"{title}:",
                          style={"color": vc.TEXT_COLOR, "marginRight": "0.6rem"})]
        for label, colour, glyph in entries:
            bits.append(html.Span(
                [html.Span(glyphs[glyph],
                           style={"color": colour, "marginRight": "0.25rem"}), label],
                style={"color": vc.BRIGHTER_TEXT_COLOR, "marginRight": "0.9rem",
                       "whiteSpace": "nowrap"}))
        groups.append(html.Span(bits, style={"marginRight": "1.2rem"}))
    return groups


def layout(**kwargs):
    # Built per request, not at import, so importing this page needs no store.
    return html.Div([
        dbc.Container([
            dbc.Row([
                dbc.Col([
                    dbc.Card(
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col([
                                    html.Label("Target Date", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dcc.Dropdown(
                                        id='strip_date_selector',
                                        options=[{'label': d, 'value': d} for d in get_indexer().get_available_dates()],
                                        value=get_indexer().get_available_dates()[0] if get_indexer().get_available_dates() else None,
                                        className="dash-dropdown bg-dark text-white",
                                        searchable=True,
                                        clearable=False,
                                        style={'borderRadius': '8px'}
                                    )
                                ], xs=12, md=2, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Model", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dbc.Select(
                                        id='strip_model_selector',
                                        options=[{"label": vc.MODEL_LABELS[k], "value": k,
                                                  "title": vc.MODEL_TOOLTIPS[k]}
                                                 for k in vc.MODEL_CHOICES],
                                        value=models.DEFAULT_MODEL.key,
                                        size="sm",
                                        className="bg-dark text-white border-secondary",
                                    )
                                ], xs=6, md=2, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Lookback", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dbc.Select(
                                        id='strip_lookback_selector',
                                        options=[
                                            {"label": "26 Weeks", "value": "26"},
                                            {"label": "52 Weeks", "value": "52"},
                                            {"label": "Custom", "value": "Custom"},
                                        ],
                                        value="Custom",
                                        size="sm",
                                        className="bg-dark text-white border-secondary",
                                    )
                                ], xs=6, md=2, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Order", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dbc.RadioItems(
                                        persistence='session',
                                        id='strip_sort_selector',
                                        options=[{"label": "Crowding", "value": SORT_BY_INDEX},
                                                 {"label": "A-Z", "value": SORT_ALPHA}],
                                        value=SORT_BY_INDEX,
                                        inline=True,
                                        style={"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "0.85rem"},
                                    )
                                ], xs=12, md=2, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Show", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dbc.RadioItems(
                                        persistence='session',
                                        id='strip_show_selector',
                                        options=[
                                            {"label": "All", "value": strip_traces.SHOW_ALL},
                                            {"label": "Setups", "value": strip_traces.SHOW_SETUPS},
                                            {"label": "+ Near", "value": strip_traces.SHOW_SETUPS_NEAR},
                                        ],
                                        value=strip_traces.SHOW_ALL,
                                        inline=True,
                                        style={"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "0.85rem"},
                                    )
                                ], xs=12, md=2, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Mark", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dbc.RadioItems(
                                        persistence='session',
                                        id='strip_mark_selector',
                                        options=[{"label": "Dot", "value": strip_traces.MARK_DOT},
                                                 {"label": "Bar", "value": strip_traces.MARK_BAR}],
                                        value=strip_traces.MARK_DOT,
                                        inline=True,
                                        style={"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "0.85rem"},
                                    )
                                ], xs=6, md=1, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Columns", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dbc.RadioItems(
                                        persistence='session',
                                        id='strip_columns_selector',
                                        options=[{"label": "1", "value": 1},
                                                 {"label": "2", "value": 2}],
                                        value=2,
                                        inline=True,
                                        style={"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "0.85rem"},
                                    )
                                ], xs=6, md=1, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Side", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dbc.RadioItems(
                                        persistence='session',
                                        id='strip_side_selector',
                                        options=[
                                            {"label": "Both", "value": strip_traces.SIDE_BOTH},
                                            {"label": "Bullish", "value": strip_traces.SIDE_BULL},
                                            {"label": "Bearish", "value": strip_traces.SIDE_BEAR},
                                        ],
                                        value=strip_traces.SIDE_BOTH,
                                        inline=True,
                                        style={"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "0.85rem"},
                                    )
                                ], xs=12, md=2, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Asset Classes", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dbc.Checklist(
                                        persistence='session',
                                        id='strip_class_selector',
                                        options=[{"label": x, "value": x} for x in get_indexer().get_asset_classes()],
                                        value=get_indexer().get_asset_classes(),
                                        inline=True,
                                        switch=True,
                                        style={"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "0.85rem"}
                                    ),
                                ], xs=12, md=12, className="px-md-2 mt-2"),
                            ], align="center")
                        ]),
                        className="mb-3 shadow-sm",
                        style={
                            "backgroundColor": "rgba(30, 30, 30, 0.6)",
                            "border": "1px solid rgba(255, 255, 255, 0.1)",
                            "borderRadius": "12px",
                            "backdropFilter": "blur(12px)"
                        }
                    )
                ], width=12)
            ], style={'position': 'sticky', 'top': '10px', 'zIndex': 1000}),

            dbc.Row([
                dbc.Col([
                    html.Div(id='strip_legend',
                             style={'display': 'flex', 'flexWrap': 'wrap',
                                    'alignItems': 'baseline', 'fontSize': '0.8rem',
                                    'marginBottom': '2px'})
                ], width=12)
            ]),

            dbc.Row([
                dbc.Col([
                    html.P(id='strip_caption',
                           style={'color': vc.TEXT_COLOR, 'fontSize': '0.85rem',
                                  'fontStyle': 'italic', 'marginBottom': '4px'})
                ], width=12)
            ]),

            dbc.Row([
                dcc.Loading(
                    id="loading-strip",
                    type="dot",
                    # The strip scrolls inside its own box rather than scrolling the
                    # page. The control card above is sticky, so a page that scrolled
                    # would slide rows underneath it and hide them. The offset covers
                    # the controls, the legend line and the caption.
                    children=html.Div(id='strip_display_container',
                                      style={"height": "calc(100vh - 290px)",
                                             "overflowY": "auto", "width": "100%"}),
                    color=vc.BRIGHTER_TEXT_COLOR
                )
            ], justify='center')
        ], fluid=True),
    ])


@callback(
    Output('strip_date_selector', 'options'),
    Output('strip_date_selector', 'value'),
    Input('cot_release_store', 'data'),
    State('strip_date_selector', 'options'),
    State('strip_date_selector', 'value'),
)
def follow_the_store(_release, current_options, current_value):
    """Re-offer the available weeks when the server takes a new one.

    Shares the Heatmap's arithmetic rather than restating it: a tab sitting on the
    newest week follows the release, one parked on an older week stays where it is.
    """
    return app_utils.next_date_selection(get_indexer().get_available_dates(),
                                         current_options, current_value)


@callback(
    Output('global_model_store', 'data', allow_duplicate=True),
    Input('strip_model_selector', 'value'),
    State('global_model_store', 'data'),
    prevent_initial_call=True
)
def update_global_model(value, current_store_val):
    new_val = value if value in vc.MODEL_CHOICES else models.DEFAULT_MODEL.key
    if new_val == current_store_val:
        return no_update
    return new_val


@callback(
    Output('strip_model_selector', 'value'),
    Input('global_model_store', 'data'),
    State('strip_model_selector', 'value'),
)
def follow_global_model(value, current_local_val):
    new_val = value if value in vc.MODEL_CHOICES else models.DEFAULT_MODEL.key
    if new_val == current_local_val:
        return no_update
    return new_val


@callback(
    Output('global_lookback_store', 'data', allow_duplicate=True),
    Input('strip_lookback_selector', 'value'),
    State('global_lookback_store', 'data'),
    prevent_initial_call=True
)
def update_global_lookback(value, current_store_val):
    new_val = value if value in ("26", "52", "Custom") else "Custom"
    if new_val == current_store_val:
        return no_update
    return new_val


@callback(
    Output('strip_lookback_selector', 'value'),
    Input('global_lookback_store', 'data'),
    State('strip_lookback_selector', 'value'),
)
def follow_global_lookback(value, current_local_val):
    new_val = value if value in ("26", "52", "Custom") else "Custom"
    if new_val == current_local_val:
        return no_update
    return new_val


@callback(
    Output('strip_display_container', 'children'),
    Output('strip_caption', 'children'),
    Output('strip_legend', 'children'),
    [Input('strip_class_selector', 'value'),
     Input('global_lookback_store', 'data'),
     Input('global_model_store', 'data'),
     Input('strip_sort_selector', 'value'),
     Input('strip_show_selector', 'value'),
     Input('strip_side_selector', 'value'),
     Input('strip_columns_selector', 'value'),
     Input('strip_mark_selector', 'value'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('strip_date_selector', 'value')]
)
def render_strip(asset_classes, lookback, model_key, sort_by, show, side, columns,
                 mark, palette_name, target_date):
    empty = html.P("Select an asset class to draw the strip.",
                   style={'textAlign': 'center', 'color': vc.TEXT_COLOR})
    if not asset_classes:
        return empty, "", []
    if not lookback:
        lookback = "Custom"

    model = models.resolve(model_key)
    df = get_matrix_data(asset_classes, lookback, target_date)
    if df.empty:
        return html.P("No data available.",
                      style={'textAlign': 'center', 'color': vc.TEXT_COLOR}), "", []

    rows, skipped = strip_traces.build_rows(
        df, model, sort_by_index=(sort_by != SORT_ALPHA),
        show=show or strip_traces.SHOW_ALL, side=side or strip_traces.SIDE_BOTH)
    # What the filters removed, said rather than left to be noticed. The board is the
    # page's whole claim, so a filtered view that looks like a full one is the one
    # failure mode worth spending a sentence on.
    drawn = sum(1 for r in rows if r.kind == "market")
    hidden = max(0, len(df) - drawn - len(skipped))
    palette = viz_config.get_palette(palette_name)
    colors = grid_colors(palette)
    chunks = strip_traces.split_columns(rows, int(columns or 1))
    figures = [strip_traces.build_figure(chunk, model, colors, palette,
                                         mark=mark or strip_traces.MARK_DOT)
               for chunk in chunks]

    report_date = target_date or df.iloc[0]["Date"]
    return (
        # Capped rather than stretched. The axis is a fixed number of units wide
        # whatever the window, so on a wide monitor every bar becomes a slab and the
        # verdict colour goes from a cue to a wall. Narrowing the browser was the first
        # thing that made the page read better, which is the same observation from the
        # other end. The cap is per column, so two columns use the width a laptop has
        # rather than leaving half of it empty and scrolling instead.
        dbc.Row([
            # `responsive` because the figure carries an explicit pixel height and
            # would otherwise keep the width it was first drawn at. Resizing the window
            # left the chart at its old width until a reload, which is a real thing to
            # hit: narrowing the browser is the first thing a reader does to this page.
            dbc.Col(dcc.Graph(figure=f,
                              config={"displayModeBar": False, "responsive": True},
                              style={"width": "100%", "maxWidth": "960px",
                                     "margin": "0 auto"}),
                    xs=12, md=(12 // len(figures)))
            for f in figures
        # align="start", because Bootstrap's default is to stretch every column to the
        # row's height. The columns hold different row counts, so the shorter figure
        # was stretched to the taller one's height and `responsive` re-drew it to fit:
        # its rows landed on a ~23px pitch beside the other column's 19px, two visibly
        # different densities on one board.
        ], className="g-0", align="start"),
        caption(report_date, lookback, model, skipped, hidden,
                mark=mark or strip_traces.MARK_DOT),
        legend(model, colors, palette, mark or strip_traces.MARK_DOT),
    )
