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

import functools
from datetime import datetime

import cotmetrics.constants as const
import cotmetrics.models as models
import cotmetrics.utils as utils
import dash
import dash_bootstrap_components as dbc
from cotmetrics import exposure, indicators
from cotmetrics.indexer import get_indexer
from cotmetrics.reports import get_matrix_data
from dash import Input, Output, State, callback, clientside_callback, dcc, html, no_update

import app_utils
import components.strip_traces as strip_traces
import viz_config
import viz_constants as vc
from components import class_filter, controls
from components.plot_colors import grid_colors

dash.register_page(
    __name__, path='/strip',
    title='Futures Crowding Strip | COT Analyzer',
    description='A one-screen crowding read of Commercial positioning across '
                '40+ futures markets, with prior-week, dollar and basis '
                'comparisons from the weekly COT report.',
)

# Layout runs per request; the wiring must not.
class_filter.register('strip_class_selector')
controls.register_lookback('strip_lookback_selector')
controls.register_model('strip_model_selector')
controls.register_target_date('strip_date_selector')

SORT_BY_INDEX = "index"
SORT_ALPHA = "alpha"

# The word for each filter value, in one place because two things need it now: the
# radio that sets it and the summary line that reports it while the controls are
# folded away. Written twice they would drift, and the summary is exactly the thing
# nobody would check.
ORDER_LABELS = {SORT_BY_INDEX: "Crowding", SORT_ALPHA: "A-Z"}
COMPARE_LABELS = {strip_traces.COMPARE_PRIOR: f"{const.MOMENTUM_PERIOD}w ago",
                  strip_traces.COMPARE_DOLLARS: "Dollars",
                  strip_traces.COMPARE_BASIS: "Other basis",
                  strip_traces.COMPARE_NONE: "None"}
SHOW_LABELS = {strip_traces.SHOW_ALL: "All",
               strip_traces.SHOW_SETUPS: "Setups",
               strip_traces.SHOW_SETUPS_NEAR: "+ Near"}
SIDE_LABELS = {strip_traces.SIDE_BOTH: "Both",
               strip_traces.SIDE_BULL: "Bullish",
               strip_traces.SIDE_BEAR: "Bearish"}


def _options(labels):
    return [{"label": text, "value": value} for value, text in labels.items()]


# ── the dollar lens ───────────────────────────────────────────────────────────
# The one thing on this page that reads a second store. Everything else comes off the
# Signal Matrix; this joins `cotmetrics.exposure` (prices, contract specs, volatility)
# onto the same rows, so the strip can draw the same leg over the same window measured
# in money instead of in contracts.
#
# Where the arithmetic lives, since this repo computes no metrics of its own: both
# halves are cotmetrics functions and this only composes them, the same shape as the
# Heatmap's `_spec_risk`, which pairs `market_exposure` with `expanding_pct_rank`. The
# composition is a range index of a dollar series, which nothing else in the app wants
# yet. The moment a second surface does, it moves to `cotmetrics.exposure` beside
# `windowed_pct_rank` rather than being copied.
#
# LEG_COMM, because the lollipop it is drawn against is Commercials. The mirror is
# exact rather than approximate (the Legacy legs sum to zero, so spec risk is minus
# commercial risk to the last decimal), so this is a presentation choice and not a
# different measurement.


def _window_weeks(asset, lookback):
    """How many weeks the row's index was measured over.

    The dollar reading has to use the SAME window, or the wedge between the two marks
    stops being a comparison of two units and becomes one of two stretches of time.
    Under Custom that is the market's own tuned lookback, which is why this asks the
    instrument rather than the control.
    """
    if lookback in ("26", "52"):
        return int(lookback)
    instrument = get_indexer().get_instrument_from_name(asset)
    custom = getattr(instrument, "custom_lookback", None)
    try:
        return int(custom)
    except (TypeError, ValueError):
        return 52


@functools.lru_cache(maxsize=512)
def _dollar_reads(asset, window, newest_date):
    """One market's weekly dollar readings, keyed by report date.

    `newest_date` is a cache-buster and nothing else: a Friday release must invalidate
    this and nothing else does. `market_exposure` is always asked for "Custom" because
    the lookback control does not touch what it reads (net contracts, price and
    volatility); the window belongs to the index computed here, and it IS a cache key.

    Returns `{date_str: DollarRead}`, or None when the market has no dollar reading at
    all: no contract multiplier in the specs table, or no bars to price it with. The
    catch is broad on purpose. This is a display join, and one unpriceable market must
    not take the other forty rows down with it.
    """
    try:
        ex = exposure.market_exposure(asset, leg=exposure.LEG_COMM, lookback="Custom")
        risk, notional = ex["risk_usd"], ex["notional_usd"]
        if not risk.notna().any():
            return None
        risk_index = indicators.calculate_range_index(risk, window)
        notional_index = indicators.calculate_range_index(notional, window)
    except Exception as e:
        utils.cot_logger.warning(f"strip: no dollar reading for {asset}: {e}")
        return None

    def clean(value):
        return float(value) if value == value else None

    return {ts.strftime('%Y-%m-%d'): strip_traces.DollarRead(
                index=clean(idx), risk_usd=clean(level),
                notional_index=clean(notional_idx), sigma_daily=clean(sigma),
                weeks=window)
            for ts, idx, level, notional_idx, sigma
            in zip(risk.index, risk_index.to_numpy(), risk.to_numpy(),
                   notional_index.to_numpy(), ex["sigma_daily"].to_numpy())}


def dollar_table(df, lookback, newest_date):
    """`{asset: DollarRead}` for the week each row is showing.

    Row by row on the row's OWN date rather than on the page's target date, matching
    what the Heatmap's joins do: with no target selected each market shows its latest
    week, and those can differ.
    """
    table = {}
    for asset, date in zip(df["Asset"], df["Date"]):
        reads = _dollar_reads(asset, _window_weeks(asset, lookback), newest_date)
        if reads and date in reads:
            table[asset] = reads[date]
    return table


def controls_summary(target_date, model, lookback, sort_by, show, side, columns,
                     n_classes, n_all, hidden=0, skipped=0,
                     compare=strip_traces.COMPARE_PRIOR):
    """One line saying what the folded controls are set to.

    Folding the card hides seven controls, and a board drawn on a filter you cannot see
    is the same failure the caption already guards against: a partial view that looks
    like a full one. This is the caption's job for the controls rather than for the
    data, so it names every filter that can hide a row, and says how many classes are
    on out of how many rather than listing them, because nine names do not fit and the
    fraction is what tells you something is off.

    It also carries what the filters REMOVED, not only what they are set to, and that
    is the half that had no home. The caption says the same two things in prose, and
    the caption now starts folded, so without this a fresh visitor reads a board with
    nothing on screen saying markets are missing from it. The counts sit ahead of the
    class fraction and the column count because this line truncates on a narrow
    viewport and they are the two segments least worth losing.
    """
    bits = [target_date or "latest", vc.MODEL_LABELS.get(model.key, model.key)]
    bits.append(f"{lookback}-week" if lookback in ("26", "52") else "Custom lookback")
    bits.append(ORDER_LABELS.get(sort_by, sort_by))
    bits.append(SHOW_LABELS.get(show, show))
    bits.append(SIDE_LABELS.get(side, side))
    bits.append(f"vs {COMPARE_LABELS.get(compare, compare)}")
    if hidden:
        bits.append(f"{hidden} hidden")
    if skipped:
        bits.append(f"{skipped} no index")
    bits.append(f"{n_classes}/{n_all} classes")
    bits.append(f"{columns} column" + ("s" if int(columns or 1) != 1 else ""))
    return " · ".join(str(b) for b in bits)


def caption(report_date, lookback, model, skipped, hidden=0,
            compare=strip_traces.COMPARE_PRIOR, disagree=0, unpriced=0):
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
    # Both sentences when both apply. The second branch used to assign rather than
    # append, so a board that was BOTH filtered and short of data reported only the
    # missing markets and said nothing about the filter. That is the wrong one to
    # lose: a market with no index is absent from every view of this week, where a
    # hidden one is a choice the reader made and can undo, and not knowing a filter
    # is on is how a partial board gets read as the whole book.
    dropped = ""
    if hidden:
        dropped += f" {hidden} market(s) hidden by the Show/Side filters."
    if skipped:
        dropped += (f" {len(skipped)} market(s) have no index this week and are not "
                    f"shown: {', '.join(sorted(skipped))}.")
    # The dollar sentence carries two counts for the same reason the line above counts
    # hidden markets: a row with no second mark and a row whose two marks agree look
    # identical, and only one of them is a measurement.
    if compare == strip_traces.COMPARE_DOLLARS:
        unpriced_note = (f" {unpriced} market(s) cannot be priced (no contract "
                         f"multiplier or no bars) and carry no diamond."
                         if unpriced else "")
        money = (
            f" The hollow diamond is this SAME 0-100 index, over the same window and "
            f"on the same leg, computed on dollars at risk (contracts x point value x "
            f"price x daily volatility) instead of on contracts: a range position like "
            f"the lollipop, not a percentile. The line runs back to the contract "
            f"reading, and where the two part, the crowd's money and its contract "
            f"count disagree about how extreme this market is. {disagree} of the drawn "
            f"markets disagree about which band they are in this week.{unpriced_note}")
    elif compare == strip_traces.COMPARE_BASIS:
        other_name = strip_traces._other_basis_name(model)
        own_name = ("net contracts" if other_name != "net contracts"
                    else "share of open interest")
        money = (
            f" The hollow square is this SAME index computed on {other_name} instead "
            f"of on {own_name}, with a line back to the reading the gate actually "
            f"uses. The gap on a row is the contract-size drift the OI normalization "
            f"removes, so the widest lines mark the markets where the two bases tell "
            f"different stories. The square carries no verdict: only the model's own "
            f"basis is gated, and the Divergence page compares all three models' "
            f"verdicts side by side.")
    elif compare == strip_traces.COMPARE_PRIOR:
        money = (f" The hollow ring is where the same index stood "
                 f"{const.MOMENTUM_PERIOD} weeks ago.")
    else:
        money = ""
    return (
        f"Positioning as of Tuesday {pretty}, gated on {model.title}, measured over "
        f"{window}. The lollipop is the COMMERCIAL positioning index, 0-100 — the stem "
        f"hangs from neutral (50), so length is distance from neutral; hover any head "
        f"for the exact figures, or click it to open the market's detail page. "
        f"{tick_note}"
        f"Its colour is the model's verdict on the whole row, not on its own value, so "
        f"a small faded lollipop deep in a band is a market at an extreme with another "
        f"leg blocking it.{money}{dropped}")


def legend(model, colors, palette, compare=strip_traces.COMPARE_PRIOR):
    """The figure key, rendered as one line of page chrome above both columns.

    `strip_traces.legend_items` says what the entries are; this only turns them into
    coloured text. Glyphs stand in for the plot symbols: the disc is the lollipop head,
    the vertical bar is the line-ns tick, the ring is the hollow prior-position circle.
    """
    glyphs = {
        strip_traces.GLYPH_MARK: "●",
        strip_traces.GLYPH_TICK: "│",
        strip_traces.GLYPH_CIRCLE: "○",
        strip_traces.GLYPH_DIAMOND: "◇",
        strip_traces.GLYPH_SQUARE: "□",
    }
    groups = []
    for title, entries in strip_traces.legend_items(model, colors, palette, compare):
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
    # The page scrolls; the board does NOT scroll inside its own box. It used to
    # (a viewport-height flex column with the board as the only scrolling part),
    # which kept the controls and legend put, but it meant the page's scrollbar
    # never moved while two thirds of the board sat off screen: reported as "I
    # can't scroll the main page to see the remaining strips". A board is a page
    # of content, so it flows like one, and the control card goes sticky instead
    # (the heatmap's pattern), which keeps the controls reachable without taking
    # the page's scroll away.
    return html.Div(
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
        dbc.Container(children=[
            # Sticky, the heatmap's pattern: now that the page scrolls, the card
            # would otherwise scroll away with two thirds of the board below it.
            dbc.Row(style={'position': 'sticky', 'top': '10px', 'zIndex': 1000},
                    children=[
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
                                    controls.label("Target Date"),
                                    controls.target_date_dropdown(
                                        'strip_date_selector')
                                ], xs=12, md=2, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    controls.label("Model"),
                                    # persistence=None keeps this page's original
                                    # behaviour: the value rides the global store,
                                    # not its own browser copy.
                                    controls.model_select(
                                        'strip_model_selector', size="sm",
                                        persistence=None)
                                ], xs=6, md=2, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    controls.label("Lookback"),
                                    controls.lookback_select(
                                        'strip_lookback_selector', size="sm",
                                        persistence=None)
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
                                    html.Label("Compare", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dbc.RadioItems(
                                        persistence='session',
                                        id='strip_compare_selector',
                                        options=_options(COMPARE_LABELS),
                                        value=strip_traces.COMPARE_PRIOR,
                                        inline=True,
                                        style={"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "0.85rem"},
                                    )
                                ], xs=12, md=2, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Asset Classes", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    # Was nine inline switches at md=True, so it took
                                    # whatever the other six controls left and wrapped
                                    # to a second line. Same switches, collapsed.
                                    class_filter.control(
                                        'strip_class_selector',
                                        get_indexer().get_asset_classes()),
                                ], xs=12, md=2, className="px-md-2"),

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
            ]),

            # Everything the PNG export captures lives inside this div: the legend,
            # the caption and the board. The export button does NOT, since a button in
            # the picture is the one thing on it that cannot be acted on.
            html.Div(id='strip_export_container', children=[
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
                        # Natural height: the board flows and the PAGE scrolls. It
                        # used to scroll inside this box (flex chain + overflowY),
                        # which kept the chrome put but left the page's own
                        # scrollbar dead over a mostly off-screen board.
                        children=html.Div(id='strip_display_container',
                                          style={"width": "100%"}),
                        color=vc.BRIGHTER_TEXT_COLOR
                )
            ])
        ], fluid=True),
    ])


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
     Input('strip_compare_selector', 'value'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('strip_date_selector', 'value')]
)
def render_strip(asset_classes, lookback, model_key, sort_by, show, side, columns,
                 compare, palette_name, target_date):
    empty = html.P("Select an asset class to draw the strip.",
                   style={'textAlign': 'center', 'color': vc.TEXT_COLOR})
    all_classes = get_indexer().get_asset_classes()
    if not asset_classes:
        return empty, "", [], f"No asset class selected · 0/{len(all_classes)} classes"
    if not lookback:
        lookback = "Custom"

    model = models.resolve(model_key)
    show = show or strip_traces.SHOW_ALL
    side = side or strip_traces.SIDE_BOTH
    compare = compare or strip_traces.COMPARE_PRIOR

    def summarise(hidden=0, skipped=0):
        return controls_summary(target_date, model, lookback, sort_by, show, side,
                                columns, len(asset_classes), len(all_classes),
                                hidden=hidden, skipped=skipped, compare=compare)

    df = get_matrix_data(asset_classes, lookback, target_date)
    if df.empty:
        return (html.P("No data available.",
                       style={'textAlign': 'center', 'color': vc.TEXT_COLOR}),
                "", [], summarise())

    # Only when the mark is on. The dollar join reads the price store market by
    # market, and paying for it on every render of a board that is not drawing it
    # would put a second store in the path of a page that otherwise needs one.
    dollars = None
    if compare == strip_traces.COMPARE_DOLLARS:
        available = get_indexer().get_available_dates()
        dollars = dollar_table(df, lookback, available[0] if available else None)

    rows, skipped = strip_traces.build_rows(
        df, model, sort_by_index=(sort_by != SORT_ALPHA),
        show=show, side=side, dollars=dollars)
    disagree, unpriced = strip_traces.dollar_split(rows, model)
    # What the filters removed, said rather than left to be noticed. The board is the
    # page's whole claim, so a filtered view that looks like a full one is the one
    # failure mode worth spending a sentence on.
    drawn = sum(1 for r in rows if r.kind == "market")
    hidden = max(0, len(df) - drawn - len(skipped))
    palette = viz_config.get_palette(palette_name)
    colors = grid_colors(palette)
    chunks = strip_traces.split_columns(rows, int(columns or 1))
    figures = [strip_traces.build_figure(chunk, model, colors, palette,
                                         compare=compare)
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
            dbc.Col(dcc.Graph(id={'type': 'strip_board_graph', 'index': n},
                              figure=f,
                              config={"displayModeBar": False, "responsive": True},
                              style={"width": "100%", "maxWidth": "960px",
                                     "margin": "0 auto"}),
                    xs=12, md=(12 // len(figures)))
            for n, f in enumerate(figures)
        # align="start", because Bootstrap's default is to stretch every column to the
        # row's height. The columns hold different row counts, so the shorter figure
        # was stretched to the taller one's height and `responsive` re-drew it to fit:
        # its rows landed on a ~23px pitch beside the other column's 19px, two visibly
        # different densities on one board.
        ], className="g-0", align="start"),
        caption(report_date, lookback, model, skipped, hidden, compare=compare,
                disagree=disagree, unpriced=unpriced),
        legend(model, colors, palette, compare),
        summarise(hidden=hidden, skipped=len(skipped)),
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


@callback(
    Output('url', 'href', allow_duplicate=True),
    Input({'type': 'strip_board_graph', 'index': dash.ALL}, 'clickData'),
    prevent_initial_call=True,
)
def open_market(_clicks):
    """A click on a row's value mark opens the market's detail page.

    Pattern-matched over the columns because the board is one or two figures by
    the Columns control; the triggering figure's point carries the destination
    (`customdata`, set on the head mark, the row's one hoverable trace).
    Location has refresh=False, so the write is a client-side pushState: the
    same navigation the navbar makes, back button included.
    """
    triggered = dash.ctx.triggered
    href = app_utils.clicked_market_href(
        triggered[0]['value'] if triggered else None)
    return href or no_update
