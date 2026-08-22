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
from dash import Input, Output, State, callback, clientside_callback, dcc, html, no_update

import app_utils
import components.strip_traces as strip_traces
import viz_config
import viz_constants as vc
from components.plot_colors import grid_colors

dash.register_page(__name__, path='/strip')

SORT_BY_INDEX = "index"
SORT_ALPHA = "alpha"

# Where this page starts: the navbar's bottom edge plus the app container's top
# padding, measured in the browser at the page's own top offset.
#
# The ONE number left in the page's vertical layout, where the `calc(100vh - 290px)` it
# replaces needed four (chrome, card, legend, caption). The difference that matters is
# not the count: nothing ON this page can change this one, so adding a row or folding
# the controls cannot silently invalidate it, which is exactly what the old constant
# could not survive. It moves only if the app's navbar changes, and it is measured
# rather than guessed: `document.getElementById('strip_export_container')`, walk up to
# the div carrying this calc, read `getBoundingClientRect().top`.
NAVBAR_PX = 96

# The word for each filter value, in one place because two things need it now: the
# radio that sets it and the summary line that reports it while the controls are
# folded away. Written twice they would drift, and the summary is exactly the thing
# nobody would check.
ORDER_LABELS = {SORT_BY_INDEX: "Crowding", SORT_ALPHA: "A-Z"}
SHOW_LABELS = {strip_traces.SHOW_ALL: "All",
               strip_traces.SHOW_SETUPS: "Setups",
               strip_traces.SHOW_SETUPS_NEAR: "+ Near"}
SIDE_LABELS = {strip_traces.SIDE_BOTH: "Both",
               strip_traces.SIDE_BULL: "Bullish",
               strip_traces.SIDE_BEAR: "Bearish"}


def _options(labels):
    return [{"label": text, "value": value} for value, text in labels.items()]


def controls_summary(target_date, model, lookback, sort_by, show, side, columns,
                     n_classes, n_all):
    """One line saying what the folded controls are set to.

    Folding the card hides seven controls, and a board drawn on a filter you cannot see
    is the same failure the caption already guards against: a partial view that looks
    like a full one. This is the caption's job for the controls rather than for the
    data, so it names every filter that can hide a row, and says how many classes are
    on out of how many rather than listing them, because nine names do not fit and the
    fraction is what tells you something is off.
    """
    bits = [target_date or "latest", vc.MODEL_LABELS.get(model.key, model.key)]
    bits.append(f"{lookback}-week" if lookback in ("26", "52") else "Custom lookback")
    bits.append(ORDER_LABELS.get(sort_by, sort_by))
    bits.append(SHOW_LABELS.get(show, show))
    bits.append(SIDE_LABELS.get(side, side))
    bits.append(f"{n_classes}/{n_all} classes")
    bits.append(f"{columns} column" + ("s" if int(columns or 1) != 1 else ""))
    return " · ".join(str(b) for b in bits)


def caption(report_date, lookback, model, skipped, hidden=0):
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
    legs = [strip_traces.LEG_LABELS[leg] for leg in model.spec_legs
            if leg in strip_traces.LEG_LABELS]
    if legs:
        tick_note = (f"Ticks are the other legs this gate reads ({', '.join(legs)}); "
                     f"they light with their row, and the hover says whether one is "
                     f"through its own gate. ")
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
        f"{window}. The lollipop is the COMMERCIAL positioning index, 0-100 — the stem "
        f"hangs from neutral (50), so length is distance from neutral; hover any head "
        f"for the exact figures. "
        f"{tick_note}"
        f"Its colour is the model's verdict on the whole row, not on its own value, so "
        f"a small faded lollipop deep in a band is a market at an extreme with another "
        f"leg blocking it.{dropped}")


def legend(model, colors, palette):
    """The figure key, rendered as one line of page chrome above both columns.

    `strip_traces.legend_items` says what the entries are; this only turns them into
    coloured text. Glyphs stand in for the plot symbols: the disc is the lollipop head,
    the vertical bar is the line-ns tick, the ring is the hollow prior-position circle.
    """
    glyphs = {
        strip_traces.GLYPH_MARK: "●",
        strip_traces.GLYPH_TICK: "│",
        strip_traces.GLYPH_CIRCLE: "○",
    }
    groups = []
    for title, entries in strip_traces.legend_items(model, colors, palette):
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
    #
    # One flex column at viewport height, with the board as the only part that
    # scrolls. This replaces a `calc(100vh - 290px)` on the board, a number that had to
    # be re-measured every time anything above it changed height, and which the
    # collapsing control card would have broken outright: the card is ~150px open and
    # ~40px shut, so one constant cannot be right in both states. `flex: 1` asks for
    # "whatever is left" instead, which is the same answer without the arithmetic.
    return html.Div(
        style={"display": "flex", "flexDirection": "column",
               "height": f"calc(100vh - {NAVBAR_PX}px)"},
        children=[
        # `local`, not `session`: folding is a standing preference about how this page
        # should look, not a fact about this visit. The filters below use session
        # persistence because the opposite is true of them, a filter restored weeks
        # later is a board that lies about what it is showing.
        #
        # Both start shut. The page is a board, and everything else on it is either an
        # input to the board or an explanation of it: worth one click when wanted,
        # not worth a permanent third of the screen. What survives the fold is the one
        # line that says what you are looking at, and the board itself.
        dcc.Store(id='strip_controls_open', storage_type='local', data=False),
        dcc.Store(id='strip_key_open', storage_type='local', data=False),
        dbc.Container(style={"display": "flex", "flexDirection": "column",
                             "flex": "1 1 auto", "minHeight": 0},
                      children=[
            dbc.Row([
                dbc.Col([
                    dbc.Card(
                        dbc.CardBody([
                            # The always-visible line: the two fold toggles, a summary
                            # of what the controls currently say, and the export.
                            # Nothing here is a filter or an explanation, so nothing
                            # here is worth hiding.
                            dbc.Row([
                                dbc.Col(
                                    dbc.Button(id='strip_controls_toggle', size="sm",
                                               color="secondary", outline=True,
                                               className="py-0"),
                                    xs="auto"),
                                dbc.Col(
                                    dbc.Button(id='strip_key_toggle', size="sm",
                                               color="secondary", outline=True,
                                               className="py-0"),
                                    xs="auto"),
                                dbc.Col(
                                    html.Div(id='strip_controls_summary',
                                             style={"color": vc.TEXT_COLOR,
                                                    "fontSize": "0.8rem"}),
                                    xs=True, className="text-truncate"),
                                dbc.Col([
                                    dbc.Button("📸 Export PNG",
                                               id="strip_download_img_btn",
                                               style={"color": vc.TEXT_COLOR},
                                               size="sm"),
                                    dbc.Tooltip(
                                        "The whole board as one image, including rows "
                                        "below the fold, with the caption and legend.",
                                        target="strip_download_img_btn",
                                        placement="bottom"),
                                ], xs="auto"),
                            ], align="center", className="g-2"),

                            dbc.Collapse(id='strip_controls_collapse', is_open=False,
                                         className="mt-2", children=[
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
                                        options=_options(ORDER_LABELS),
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
                                        options=_options(SHOW_LABELS),
                                        value=strip_traces.SHOW_ALL,
                                        inline=True,
                                        style={"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "0.85rem"},
                                    )
                                ], xs=12, md=2, className="mb-3 mb-md-0 px-md-2"),

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
                                        options=_options(SIDE_LABELS),
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
                                ], xs=12, md=True, className="px-md-2 mt-2"),

                            ], align="center")
                            ]),
                        ]),
                        className="mb-2 shadow-sm",
                        style={
                            "backgroundColor": "rgba(30, 30, 30, 0.6)",
                            "border": "1px solid rgba(255, 255, 255, 0.1)",
                            "borderRadius": "12px",
                            "backdropFilter": "blur(12px)"
                        }
                    )
                ], width=12)
            # No `position: sticky` any more. It was there because the page scrolled
            # under a card that had to stay put; in a flex column at viewport height the
            # page does not scroll at all, so the card is fixed by construction.
            ]),

            # Everything the PNG export captures lives inside this div: the legend,
            # the caption and the board. The export button does NOT, since a button in
            # the picture is the one thing on it that cannot be acted on.
            html.Div(id='strip_export_container',
                     style={"display": "flex", "flexDirection": "column",
                            "flex": "1 1 auto", "minHeight": 0},
                     children=[
                # The key: what the marks mean and what the board was measured over.
                # Folded by default like the controls, and INSIDE the export container
                # rather than beside it, because the PNG must carry both whatever the
                # fold says. The export re-opens every collapse in its clone, so a
                # reader who has never expanded this still gets a dated, explained
                # image. See export_strip_image in clientside.js.
                dbc.Collapse(id='strip_key_collapse', is_open=False, children=[
                    dbc.Row([
                        dbc.Col([
                            html.Div(id='strip_legend',
                                     style={'display': 'flex', 'flexWrap': 'wrap',
                                            'alignItems': 'baseline',
                                            'fontSize': '0.8rem',
                                            'marginBottom': '2px'})
                        ], xs=12, md=True),
                    ], align="center"),

                    dbc.Row([
                        dbc.Col([
                            html.P(id='strip_caption',
                                   style={'color': vc.TEXT_COLOR,
                                          'fontSize': '0.85rem',
                                          'fontStyle': 'italic',
                                          'marginBottom': '4px'})
                        ], width=12)
                    ]),
                ]),

                dcc.Loading(
                        id="loading-strip",
                        type="dot",
                        # The spinner's own wrapper is a link in the flex chain, so it
                        # gets the same treatment. Miss it and the box below reverts to
                        # its content height and the page scrolls.
                        parent_style={"display": "flex", "flexDirection": "column",
                                      "flex": "1 1 auto", "minHeight": 0},
                        # The strip scrolls inside its own box rather than scrolling the
                        # page, so the controls, the legend and the caption stay put
                        # while the board moves under them. `minHeight: 0` is what makes
                        # that work: a flex item defaults to min-height:auto, which means
                        # "at least my content", so without it the box grows to the full
                        # board and the whole page scrolls instead.
                        children=html.Div(id='strip_display_container',
                                          style={"flex": "1 1 auto", "minHeight": 0,
                                                 "overflowY": "auto", "width": "100%"}),
                        color=vc.BRIGHTER_TEXT_COLOR
                )
            ])
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
    Output('strip_controls_summary', 'children'),
    [Input('strip_class_selector', 'value'),
     Input('global_lookback_store', 'data'),
     Input('global_model_store', 'data'),
     Input('strip_sort_selector', 'value'),
     Input('strip_show_selector', 'value'),
     Input('strip_side_selector', 'value'),
     Input('strip_columns_selector', 'value'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('strip_date_selector', 'value')]
)
def render_strip(asset_classes, lookback, model_key, sort_by, show, side, columns,
                 palette_name, target_date):
    empty = html.P("Select an asset class to draw the strip.",
                   style={'textAlign': 'center', 'color': vc.TEXT_COLOR})
    all_classes = get_indexer().get_asset_classes()
    if not asset_classes:
        return empty, "", [], f"No asset class selected · 0/{len(all_classes)} classes"
    if not lookback:
        lookback = "Custom"

    model = models.resolve(model_key)
    summary = controls_summary(target_date, model, lookback, sort_by,
                               show or strip_traces.SHOW_ALL,
                               side or strip_traces.SIDE_BOTH,
                               columns, len(asset_classes), len(all_classes))
    df = get_matrix_data(asset_classes, lookback, target_date)
    if df.empty:
        return (html.P("No data available.",
                       style={'textAlign': 'center', 'color': vc.TEXT_COLOR}),
                "", [], summary)

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
    figures = [strip_traces.build_figure(chunk, model, colors, palette)
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
        caption(report_date, lookback, model, skipped, hidden),
        legend(model, colors, palette),
        summary,
    )


@callback(
    Output('strip_controls_open', 'data'),
    Input('strip_controls_toggle', 'n_clicks'),
    State('strip_controls_open', 'data'),
    prevent_initial_call=True,
)
def toggle_controls(_n, is_open):
    return not is_open


@callback(
    Output('strip_controls_collapse', 'is_open'),
    Output('strip_controls_toggle', 'children'),
    Output('strip_controls_summary', 'style'),
    Input('strip_controls_open', 'data'),
)
def apply_controls_fold(is_open):
    """Open or shut, and the two bits of chrome that have to agree with it.

    The summary is hidden while the controls are open rather than always drawn: with
    the radios on screen it says what they already say, and a line that repeats the
    thing above it is the kind of clutter this fold exists to remove.
    """
    label = "▾ Filters" if is_open else "▸ Filters"
    style = {"color": vc.TEXT_COLOR, "fontSize": "0.8rem",
             "display": "none" if is_open else "block"}
    return bool(is_open), label, style


@callback(
    Output('strip_key_open', 'data'),
    Input('strip_key_toggle', 'n_clicks'),
    State('strip_key_open', 'data'),
    prevent_initial_call=True,
)
def toggle_key(_n, is_open):
    return not is_open


@callback(
    Output('strip_key_collapse', 'is_open'),
    Output('strip_key_toggle', 'children'),
    Input('strip_key_open', 'data'),
)
def apply_key_fold(is_open):
    return bool(is_open), ("▾ Key" if is_open else "▸ Key")


# The PNG export. Clientside for the reason OI Alignment's is: the figure, the caption
# and the legend are all already in the browser, so shipping them to the server to be
# re-rendered would be a round trip to redraw what is on screen.
#
# The model and the date ride along as State only to name the file. A strip PNG loses
# every control that produced it the moment it leaves the page, and the caption inside
# the image carries the date and window in prose, so the filename is the version a
# reader sees in a folder listing.
clientside_callback(
    "window.dash_clientside.clientside.export_strip_image",
    Output('strip_download_img_btn', 'n_clicks'),
    Input('strip_download_img_btn', 'n_clicks'),
    State('strip_model_selector', 'value'),
    State('strip_date_selector', 'value'),
    prevent_initial_call=True
)
