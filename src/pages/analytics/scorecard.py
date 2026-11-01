"""The Scorecard: one card per asset class, positioning and tape on one screen.

The Heatmap and the Strip answer "which markets are extreme" across the whole
universe. This answers a narrower question the others make you assemble by eye: for
ONE complex, what does every market in it look like at once, on readings that can
actually be compared. Nine currencies against five rows is a shape a reader holds in
their head; forty-two markets against five rows is a different page, and the Heatmap
already is it.

Two composition rules follow from that, and both are visible in the output:

**One card per asset class, never one card for the selection.** The column axis is a
complex. Stacking classes into one table would put corn beside the yen under a header
row that means nothing, so each selected class gets its own card with its own columns.
Selecting all nine renders nine cards rather than one 42-column table. The cards
come widest first (by market count, then name), so the one class too wide for a
half column leads as a full-width band and the two-column grid below it pairs cards
of like width; alphabetical order put the two-market Crypto card beside a four-market
one at the top, inflated to the column, with the nine-market Currencies card under
them. Order by size also lets the grid flow in source order, where the dense packing
it used to need had Energies jumping above Currencies.

**Two windows, split by what each row is for.** `cotmetrics-config` tunes
`CustomLookbackWeeks` per market (the pound at 30 weeks, the euro at 90), which is
right for a gate and wrong for a comparison row: nine differently-defined numbers side
by side invite exactly the comparison they do not support. So the descriptive rows
(the Commercial move, price, open interest) read a uniform 52-week lookback. The gate
row does not, because its verdict has to be the same verdict every other surface in
the app shows, and that one is computed on the model's own window. Neither do the leg
marks, because their job is to EXPLAIN that verdict: drawn on 52 weeks they showed
6A's Non-Reportables at 27, comfortably on the bull side, under a blank chip whose
real blocker was the same leg at 55 on the 80-week window the gate read. A mark that
contradicts the verdict above it is worse than no mark. The how-to-read fold names
both windows, and the split is a real cost of the format rather than a detail to
reconcile.

Where the arithmetic lives, since this repo computes no metrics of its own: the level
rows are `get_symbols_data`'s own alias columns for the model's basis, the Commercial
move is `cotmetrics.indicators.calculate_range_index` over the index momentum column,
and the paths are the weekly closes and open interest the same frame carries, plus
the three legs' net positions on the model's basis for the net-positions row. The
drawing, the colour rule and the row set live in `components.scorecard_rows`, which is
pure over a read plus a colour set; this module is the data join, the controls and the
caption.

The trap this page inherits from every other index surface and must keep saying: a
TRAILING window renormalises every week, so a market that has been heavily short all
year reads near the top on its least-short week. It leads the how-to-read fold, one
click away, because a card built for a fast sweep is exactly where that misread is
cheapest to make. It used to sit in the caption with the two-windows note and the
colour rule, three lines of italic above the cards on every visit; the caption now
carries only this render's facts (the week, the basis, the model, what was not
readable), which is what the exported PNG needs and what changes week to week.
"""

import functools
from datetime import datetime

import cotmetrics.constants as const
import cotmetrics.models as models
import cotmetrics.utils as utils
import dash
import dash_bootstrap_components as dbc
import pandas as pd
from cotmetrics.indexer import get_indexer
from cotmetrics.indicators import calculate_range_index
from cotmetrics.reports import get_matrix_data
from dash import Input, Output, State, callback, clientside_callback, dcc, html

import components.scorecard_rows as scorecard_rows
import viz_config
import viz_constants as vc
from components import class_filter, config_fold, controls, help_fold
from components.plot_colors import grid_colors
from components.strip_traces import LEG_COLUMNS, LEG_PALETTE_SLOT, SETUP_COLUMN

#: The net-positions row's legs, Commercials first because that is the one the row
#: draws, and the frame keys they are read into. All three are read, whatever the
#: model gates on, because the hover names them all.
_NET_LEGS = (vc.LEG_COMM, models.LEG_LARGE, models.LEG_SMALL)
_NET_KEYS = ("net_comm", "net_lrg", "net_sml")
_NET_COLUMNS = {
    const.BASIS_RAW: (const.COMM_NET, const.LARGE_NET, const.SMALL_NET),
    const.BASIS_OI_NORM: (const.COMM_NET_NORM, const.LARGE_NET_NORM,
                          const.SMALL_NET_NORM),
}

dash.register_page(
    __name__, path='/scorecard',
    title='COT Scorecard | COT Analyzer',
    description='Every market in an asset class on one card: Commercial and '
                'Non-Reportable positioning, the six-week move, and price and '
                'open interest as sparklines, from the weekly COT report.',
)

# Layout runs per request; the wiring must not.
class_filter.register('scorecard_class_selector')
controls.register_model('scorecard_model_selector')
controls.register_target_date('scorecard_date_selector')

# The PNG export, the Divergence page's machinery rather than the Strip's: this page
# has no Plotly on it, so the DOM clone IS the picture. Model and date ride along only
# to name the file. See export_scorecard_image in clientside.js for why it waits on
# the images instead of on a timer.
clientside_callback(
    "window.dash_clientside.clientside.export_scorecard_image",
    Output('scorecard_download_img_btn', 'n_clicks'),
    Input('scorecard_download_img_btn', 'n_clicks'),
    State('scorecard_model_selector', 'value'),
    State('scorecard_date_selector', 'value'),
    prevent_initial_call=True,
)

#: How many cards sit side by side above the 992px breakpoint. A MAXIMUM rather than
#: a fixed count: below the breakpoint the stylesheet collapses to one whatever is
#: chosen, because two cards on a phone is nine markets in 180px. The control is
#: hidden below the same breakpoint (Bootstrap's lg), since a choice that silently
#: does nothing is worse than no choice; the stored value survives for the next
#: wide screen.
COLUMN_CHOICES = (1, 2)
DEFAULT_COLUMNS = 2

#: The uniform lookback every row below the gate reads. A string, because that is what
#: `get_symbols_data` takes; `cotmetrics.constants.LB_52` is the same window spelled
#: for column names.
UNIFORM_LOOKBACK = "52"


@functools.lru_cache(maxsize=256)
def _market_frame(asset, basis, newest_date):
    """One market's uniform-window readings, or None.

    `newest_date` is a cache-buster and nothing else, the `/crowd` convention: a Friday
    release must invalidate this and nothing else does. The catch is broad for the same
    reason the boards' are: one unreadable market must not take its whole class down.
    """
    try:
        df = get_indexer().get_symbols_data(asset, UNIFORM_LOOKBACK, basis=basis)
    except Exception as e:  # noqa: BLE001 -- one market must not break the card
        utils.cot_logger.warning(f"scorecard: no frame for {asset}: {e}")
        return None
    if df.empty:
        return None

    out = pd.DataFrame(index=df.index)
    # The leg levels are NOT read here: they come from the matrix row, on the
    # model's own window, so they explain the chip (see `_legs_for`).
    # Index momentum is a POINT change of a bounded index, so it is not already on the
    # 0-100 scale the card's cells need; range-index it over the shared window.
    if "comm_momentum" in df:
        out["comm_move"] = calculate_range_index(df["comm_momentum"],
                                                 window=scorecard_rows.WINDOW)
    out["price"] = df.get(const.CLOSING_PRICE)
    out["oi"] = df.get(const.OPEN_INTEREST)
    # The frame carries BOTH bases' net columns whichever basis was asked for, so
    # the row's basis is chosen by name here rather than trusted to an alias.
    for key, column in zip(_NET_KEYS, _NET_COLUMNS.get(basis, ())):
        if column in df:
            out[key] = df[column]
    return out


def _clean(value):
    return None if value is None or value != value else float(value)


@functools.lru_cache(maxsize=512)
def _setup_age(asset, model_key, newest_date, target_date):
    """How many consecutive weeks the chip's story has held, or 0.

    The SAME call the Setups badge makes, on the same frame (the model's basis, its
    own Custom window), so the two surfaces cannot disagree about a market's age.
    `newest_date` is the cache-buster, as on `_market_frame`; the target date is a
    key because the walk starts at the week the card shows.
    """
    model = models.resolve(model_key)
    try:
        df = get_indexer().get_symbols_data(asset, "Custom", basis=model.basis)
    except Exception as e:  # noqa: BLE001 -- one market must not break the card
        utils.cot_logger.warning(f"scorecard: no age for {asset}: {e}")
        return 0
    if df is None or df.empty:
        return 0
    if target_date:
        df = df.loc[df.index <= pd.Timestamp(target_date)]
    return int(model.setup_age_from(df, "Custom", get_indexer().is_equity(asset)))


def _read_for(asset, record, basis, model, newest_date, target_date, palette):
    """A MarketRead at the week the card is showing, or None.

    Each market on its own dates rather than one global row position, the Heatmap's
    and the board's convention: with no target selected each column shows its own
    latest week, and those can differ.
    """
    frame = _market_frame(asset, basis, newest_date)
    if frame is None or frame.empty:
        return None
    if target_date:
        frame = frame.loc[frame.index <= pd.Timestamp(target_date)]
        if frame.empty:
            return None

    latest = frame.iloc[-1]
    scores = {row.key: _clean(latest.get(row.key))
              for row in scorecard_rows.SCORE_ROWS}
    paths = {row.key: tuple(_clean(v)
                            for v in frame[row.key].tail(scorecard_rows.WINDOW))
             for row in scorecard_rows.SPARK_ROWS if row.key in frame}

    net = tuple(
        scorecard_rows.NetSeries(
            vc.LEG_SHORT[leg],
            tuple(_clean(v) for v in frame[key].tail(scorecard_rows.WINDOW)))
        for leg, key in zip(_NET_LEGS, _NET_KEYS) if key in frame)

    instrument = get_indexer().get_instrument_from_name(asset)
    state = record.get(SETUP_COLUMN[model.key]) or const.SETUP_NONE
    return scorecard_rows.MarketRead(
        legs=_legs_for(record, model, palette),
        net=net,
        symbol=getattr(instrument, "symbol", "") or "",
        asset=asset,
        state=state,
        # Only read for a chip that will draw: the walk is the one per-market cost
        # here that the matrix does not already carry.
        setup_weeks=(_setup_age(asset, model.key, newest_date, target_date)
                     if state != const.SETUP_NONE else 0),
        scores=scores,
        paths=paths,
        date=frame.index[-1].strftime('%Y-%m-%d'),
    )


#: The speculator legs in lane order. Both read LOW as the bull side under positioning
#: fade, the mirror of Commercials.
_SPEC_LEGS = (models.LEG_LARGE, models.LEG_SMALL)


def _legs_for(record, model, palette):
    """The legs this model gates on for this market, Commercials first.

    The rule is `signal_cards.strip_legs`', and it is not "the three legs": every
    gate reads Commercials, the speculator legs are exactly `model.spec_legs` (NPF's
    CS gate never reads Non-Commercials), and an equity index contract gates on
    Commercials ALONE whatever the model. Drawing a leg the gate does not read puts a
    condition on the card the verdict above it never checked; omitting one it does
    read leaves a verdict unexplained. The card had the second failure until this
    existed, showing two fixed legs under a three-leg gate.

    The values come from the matrix row, `strip_traces.LEG_COLUMNS`' columns for this
    model: the model's basis on the model's tuned window, the readings the gate in
    the same row evaluated. Any other window can put a dot on the wrong side of a
    threshold the gate saw it on, which is the one thing a mark under a verdict must
    never do.
    """
    columns = LEG_COLUMNS[model.key]
    # No hue: Commercials take the VERDICT colour. Palette slot 0 is the bear red,
    # so colouring that lane by identity draws a bullish reading in red, which is
    # the bug signal_cards records at COMM_LANE_TAKES_LEG_COLOUR.
    legs = [scorecard_rows.LegMark(vc.LEG_SHORT[vc.LEG_COMM],
                                   _clean(record.get(columns["comm"])),
                                   scorecard_rows.BULL_HIGH)]
    if record.get(const.IS_EQUITY_COL):
        return tuple(legs)
    for leg in _SPEC_LEGS:
        if leg in model.spec_legs:
            legs.append(scorecard_rows.LegMark(
                vc.LEG_SHORT[leg], _clean(record.get(columns.get(leg))),
                scorecard_rows.BULL_LOW,
                # The app's own colour for this leg, so the lanes read as the same
                # legs the Strip and the home card draw. Their verdict is carried by
                # the zone the dot lands in, so identity here costs nothing.
                hue=palette[LEG_PALETTE_SLOT[leg]]))
    return tuple(legs)


def warm_caches():
    """Fill the per-market caches so no visitor pays the cold render.

    Called from main.py alongside the board's warmer and for the same reason: every
    entry is keyed on `newest_date`, so a release invalidates the lot by construction
    and the first visitor afterwards would otherwise pay for the whole universe.
    Failures are logged and swallowed; a warmer that can take the server down is worse
    than a slow first visitor.
    """
    try:
        indexer = get_indexer()
        available = indexer.get_available_dates()
        if not available:
            return
        newest = available[0]
        count = 0
        # Distinct bases, not one per model: two models share the OI-normalized basis
        # and would warm the same entries.
        for asset_class in indexer.get_asset_classes():
            for asset in indexer.get_assets_for_asset_class(asset_class):
                for basis in dict.fromkeys(m.basis for m in models.MODELS):
                    _market_frame(asset, basis, newest)
                # The age is per model (its own gate), for the week with no target.
                for model in models.MODELS:
                    _setup_age(asset, model.key, newest, None)
                count += 1
        utils.cot_logger.info(
            f"scorecard: warmed {count} markets ({newest}).")
    except Exception as e:  # noqa: BLE001 -- a warmer must never fail a boot
        utils.cot_logger.warning(
            f"scorecard: cache warm failed, first render pays: {e}")


def card_order(by_class):
    """(class, reads) pairs, widest card first, ties by name.

    See the module docstring: the wide class leads as a band and the grid pairs
    like with like below it. Ties alphabetical so the order is stable week to week.
    """
    return sorted(by_class.items(), key=lambda item: (-len(item[1]), item[0]))


def _columns(value):
    """The chosen column count as a CSS value, defaulting rather than raising.

    A custom property is substituted before the declaration is parsed, so repeat()
    takes one as its count; a bad value would break the whole grid rather than one
    card, which is why it is clamped to the offered choices here.
    """
    return str(value if value in COLUMN_CHOICES else DEFAULT_COLUMNS)


def caption(report_date, model, skipped):
    """The line under the cards: the FACTS of this render and nothing more.

    The week, the basis, the model and what could not be read. The two windows,
    the colour rule and the trailing-window trap are teaching and live in the fold;
    they used to be here, which made the caption three lines of italic that every
    visit scrolled past before the first card.
    """
    try:
        pretty = datetime.strptime(report_date, '%Y-%m-%d').strftime('%B %d, %Y')
    except (TypeError, ValueError):
        pretty = "an unknown date"
    basis = ("net contracts" if model.basis == const.BASIS_RAW
             else "net position as a share of open interest")
    dropped = ""
    if skipped:
        dropped = (f" {len(skipped)} market(s) have no reading this week and are "
                   f"not shown: {', '.join(sorted(skipped))}.")
    return (f"Positioning as of Tuesday {pretty}, measured as {basis} "
            f"({model.title}'s basis).{dropped}")


def help_text(model):
    """The teaching, one line per row, then the three rules that span rows.

    Model-aware, so it is rendered per callback rather than baked into the layout.
    A list rather than a paragraph because the reader's question is almost always
    "what is THIS row", and a 400-word paragraph made them read the other five to
    find it. The trap leads, since it is the misread a fast sweep makes cheapest.
    The colour sentence stays long: this page and `/crowd` use opposite
    conventions, and a reader moving between them in one session will otherwise
    read one of the two backwards.
    """
    # Prose, not a list: setup_leg_phrase names the SPECULATOR legs the gate
    # requires and returns None where it requires none (equities). Commercials are
    # named separately because every gate reads them.
    spec = vc.setup_leg_phrase(model)
    legs = f"Commercials and {spec}" if spec else "Commercials"

    def item(name, text):
        return html.Li([html.B(name), " ", text], style={"marginBottom": "3px"})

    return [
        html.P(
            f"Two windows. The Setup chip and the marks under it read "
            f"{model.title}'s own tuned window, which differs by market, because "
            f"those are the readings its gate checked; every row below the marks "
            f"reads the same 52 weekly reports across all markets, so those can be "
            f"compared side by side. A trailing window renormalises every week, "
            f"so a market short all year still reads near the top on its "
            f"least-short week.",
            style={"marginBottom": "6px"}),
        html.Ul([
            item("Setup.", f"{model.title}'s verdict, the only row that has been "
                 f"through the gate and the only cell that fills. The number "
                 f"beside it is the chip's age: consecutive weeks at or "
                 f"approaching this gate in this direction, so SETUP · 1w fired "
                 f"this week and near · 9w has told the same story for nine. "
                 f"The Setups page's badge shows the same count. Everything "
                 f"under it is description, which is why there is no summary "
                 f"score."),
            item("Leg marks.", f"One lane per leg {model.title} gates on, which is "
                 f"{legs}, Commercials always on top. Each dot sits at that leg's "
                 f"range index (0 at the window low, 100 at its high) with a faint "
                 f"rule at the midpoint; an equity index contract gates on "
                 f"Commercials alone, so its mark has one lane. A mark whose dots "
                 f"disagree is a market whose legs disagree, which is usually why "
                 f"a crowded row carries no chip. Hover for the figures."),
            item("Commercial 6wk move.", f"The change in the Commercial index over "
                 f"six weeks, range-indexed over the 52 weeks and printed on a "
                 f"-{scorecard_rows.SCALE} to +{scorecard_rows.SCALE} scale, "
                 f"nothing sign-flipped."),
            item("Commercial net.", "The Commercial leg's weekly net position as "
                 "bars from a zero line, with the Non-Commercial net as a faint "
                 "line over them, scaled to the window's largest reading of "
                 "either: the shape the Commercial mark is computed from, with "
                 "no open interest line and no range band. The line is mostly "
                 "the bars mirrored, since the three legs sum to zero. Hover for "
                 "all three legs' latest figures."),
            item("Price, Open interest.", "Paths over the same 52 weeks, each "
                 "with a faint rule at the midpoint of its own range and a dot on "
                 "the latest week. No verdict: the gates read positioning and no "
                 "price term. Hover for the figure."),
        ], style={"paddingLeft": "1.2rem", "marginBottom": "6px"}),
        html.P(
            "Color is the verdict, not the value. A Commercial dot high in its "
            "range and a speculator dot low in its range both draw bullish, "
            "because crowded speculators are the side this book fades; the 6wk "
            "move uses the same rule. That is what the Crowding Strip does and "
            "the OPPOSITE of the Crowdedness Board, where color is the cell's own "
            "value. The Commercial net row is the one exception: its ink names "
            "nothing, it is the paths' neutral. Hover any row label for how much "
            "that row adds over the Commercial Index.",
            style={"marginBottom": "0"}),
    ]


def layout(**kwargs):
    # Built per request, not at import, so importing this page needs no store.
    return html.Div([
        dbc.Container([
            dbc.Row([
                dbc.Col([
                    dbc.Card(
                        dbc.CardBody([
                            # Widths sum to 12 at md and 10 at lg, so the row
                            # never wraps and no control stretches far past its
                            # content.
                            config_fold.wrap('scorecard', dbc.Row([
                                dbc.Col([
                                    controls.label("Target Date"),
                                    controls.target_date_dropdown(
                                        'scorecard_date_selector'),
                                ], xs=12, md=3, lg=2, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    controls.label("Model"),
                                    # persistence=None: the value rides the global
                                    # store, the Crowd page's convention.
                                    controls.model_select(
                                        'scorecard_model_selector', size="sm",
                                        persistence=None),
                                ], xs=6, md=3, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Columns",
                                               style={**vc.label_style,
                                                      "fontSize": "0.8rem",
                                                      "textTransform": "uppercase"}),
                                    dbc.RadioItems(
                                        persistence='session',
                                        id='scorecard_cols_selector',
                                        options=[{"label": str(c), "value": c}
                                                 for c in COLUMN_CHOICES],
                                        value=DEFAULT_COLUMNS,
                                        inline=True,
                                        style={"color": vc.BRIGHTER_TEXT_COLOR,
                                               "fontSize": "0.85rem"},
                                    ),
                                ], xs=6, md=2,
                                    className="mb-3 mb-md-0 px-md-2 d-none d-lg-block"),

                                dbc.Col([
                                    html.Label("Asset Classes",
                                               style={**vc.label_style,
                                                      "fontSize": "0.8rem",
                                                      "textTransform": "uppercase"}),
                                    class_filter.control(
                                        'scorecard_class_selector',
                                        get_indexer().get_asset_classes()),
                                ], xs=12, md=4, lg=3, className="px-md-2"),
                            ], align="center")),
                        ]),
                        className="mb-2 shadow-sm",
                        style={
                            "backgroundColor": "rgba(30, 30, 30, 0.6)",
                            "border": "1px solid rgba(255, 255, 255, 0.1)",
                            "borderRadius": "12px",
                            "backdropFilter": "blur(12px)",
                        },
                    ),
                ], width=12),
            ], className="mt-3"),

            # Everything the PNG captures lives inside this div, the help fold's
            # toggle included: the export strips buttons from its clone, the
            # Divergence container's rule.
            html.Div(id='scorecard_export_container', children=[
                dbc.Row([
                    dbc.Col([
                        html.P(id='scorecard_caption',
                               style={'color': vc.TEXT_COLOR, 'fontSize': '0.85rem',
                                      'fontStyle': 'italic', 'marginBottom': '4px'}),
                        # Out of the PNG, open or shut, which is `/crowd`'s rule
                        # and now this page's: exportBoardImage re-opens every
                        # fold in its clone, and this one is several hundred
                        # words of teaching above the cards people share. The
                        # image is the cards. The caption stays, because it
                        # carries the week, the basis and the model, which the
                        # picture cannot say on its own.
                        html.Div(help_fold.wrap('scorecard', html.Div(
                            id='scorecard_help',
                            style={'color': vc.TEXT_COLOR, 'fontSize': '0.85rem',
                                   'marginBottom': '4px'})),
                            **{'data-export': 'omit'}),
                    ], xs=True),
                    dbc.Col([
                        dbc.Button("📸 Export PNG",
                                   id="scorecard_download_img_btn",
                                   style={"color": vc.TEXT_COLOR},
                                   size="sm"),
                        dbc.Tooltip(
                            "Every card as one image, with its caption. Cards "
                            "that pan sideways on screen are exported whole.",
                            target="scorecard_download_img_btn",
                            placement="bottom"),
                    ], xs="auto"),
                ]),

                dbc.Row([
                    dbc.Col(
                        dcc.Loading(
                            id="loading-scorecard",
                            type="dot",
                            children=html.Div(id='scorecard_container'),
                            color=vc.BRIGHTER_TEXT_COLOR,
                        ),
                        width=12),
                ]),
            ]),
        ], fluid=True),
    ])


@callback(
    Output('scorecard_container', 'children'),
    Output('scorecard_caption', 'children'),
    Output('scorecard_help', 'children'),
    [Input('scorecard_class_selector', 'value'),
     Input('global_model_store', 'data'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('scorecard_date_selector', 'value'),
     Input('scorecard_cols_selector', 'value')],
)
def render_scorecard(asset_classes, model_key, palette_name, target_date, columns):
    # Resolved before the early exits so the fold teaches even over an empty page.
    model = models.resolve(model_key)
    if not asset_classes:
        return (html.P("Select an asset class to draw a card.",
                       style={'textAlign': 'center', 'color': vc.TEXT_COLOR}),
                "", help_text(model))

    # The matrix drives the universe and carries the verdict. The Custom lookback is
    # the models' own window, the same one every other verdict surface gates on; the
    # rows below the gate deliberately use a different one. See the module docstring.
    df = get_matrix_data(asset_classes, "Custom", target_date)
    if df.empty:
        return (html.P("No data available.",
                       style={'textAlign': 'center', 'color': vc.TEXT_COLOR}),
                "", help_text(model))

    available = get_indexer().get_available_dates()
    newest = available[0] if available else None
    palette = viz_config.get_palette(palette_name)
    colors = grid_colors(palette)

    by_class, unreadable = {}, []
    for asset_class, group in df.groupby("Asset Class", sort=True):
        reads = []
        for record in group.to_dict("records"):
            asset = record.get("Asset")
            read = _read_for(asset, record, model.basis, model, newest,
                             target_date, palette)
            if read is None:
                unreadable.append(asset)
            else:
                reads.append(read)
        if reads:
            by_class[asset_class] = reads

    cards, report_date = [], None
    for asset_class, reads in card_order(by_class):
        report_date = report_date or reads[0].date
        # A class too wide for a half column takes the whole row rather than
        # scrolling sideways inside one. How many markets a class holds is this
        # layer's fact; where the breakpoint sits is the stylesheet's.
        wide = scorecard_rows.card_min_px(len(reads)) > scorecard_rows.GRID_COLUMN_PX
        cards.append(html.Div([
            # Centred in the table's own box, so it sits over its table at any
            # width rather than at the page's left edge.
            html.H2(asset_class,
                    style={"fontSize": "1rem", "fontWeight": "600",
                           "color": vc.BRIGHTER_TEXT_COLOR, "textAlign": "center",
                           "maxWidth": f"{scorecard_rows.card_max_px(len(reads))}px",
                           "margin": "0 auto 6px"}),
            scorecard_rows.build_table(reads, model, colors),
        ], className="mb-2" + (" scorecard-wide" if wide else "")))

    if not cards:
        return (html.P("No data available.",
                       style={'textAlign': 'center', 'color': vc.TEXT_COLOR}),
                "", help_text(model))

    return (
        # Two across from 992px up, one below; see .scorecard-grid in custom.css.
        # The cap rises with the column count so a two-up layout is not squeezed
        # into the width that suited a single column.
        html.Div(cards, className="scorecard-grid",
                 # The count is Python's fact and the breakpoint is the
                 # stylesheet's, the split .setup-grid already draws.
                 style={"maxWidth": "1600px", "margin": "0 auto",
                        "--scorecard-cols": _columns(columns)}),
        caption(target_date or report_date, model, sorted(set(unreadable))),
        help_text(model),
    )
