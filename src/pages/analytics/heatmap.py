import functools
import urllib.parse
from datetime import datetime

import cotmetrics.constants as const
import cotmetrics.models as models
import cotmetrics.utils as utils
import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pandas as pd
from cotmetrics import exposure, offside
from cotmetrics.indexer import get_indexer
from cotmetrics.reports import get_matrix_data
from dash import (
    ClientsideFunction,
    Input,
    Output,
    callback,
    clientside_callback,
    dcc,
    html,
)

import app_utils
import viz_config
import viz_constants as vc
from components import class_filter, config_fold, controls
from components.plot_colors import GridColors, grid_colors  # noqa: F401

dash.register_page(__name__, path="/heatmap")

# Layout runs per request; the wiring must not.
class_filter.register('page_heatmap_selector')
controls.register_lookback('heatmap_lookback_selector')
controls.register_target_date('heatmap_date_selector')

# The Setups filter. Values are stored in a session-persisted control, so they are a
# wire format: renaming one silently resets a returning reader's filter to the default.
SETUP_FILTER_ALL = "all"
SETUP_FILTER_GATE = "gate"
SETUP_FILTER_NEAR = "near"

# UNION ACROSS THE TWO MODELS THIS GRID SHOWS, deliberately. It reports Raw CLS 95/5
# and NPF CS 80/20 side by side and has no model selector, so a filter that picked one
# would hide rows the other half of the same row is lit up about. The two bands are
# independent rather than nested -- Coffee has been an NPF setup while its CLS legs
# were only close -- so "either" is the only rule that cannot contradict the grid it
# filters. NPF CLS 95/5 is deliberately absent on both counts, from the columns and
# from this union: the grid has no block for it (its legs are the normalized columns
# already shown, under a tighter band), and a verdict the grid does not display must
# not decide which rows survive the filter. Full CLS setups are CS setups anyway (95/5
# sits inside 80/20 and the extra Large-leg clause only narrows), so what the union
# forgoes is only the CLS near tier, which can fire off the Large leg alone.
_FILTER_STATES = {
    SETUP_FILTER_GATE: frozenset(const.SETUP_FULL_STATES),
    SETUP_FILTER_NEAR: frozenset(const.SETUP_FULL_STATES + const.SETUP_NEAR_STATES),
}


def filter_by_setup(df, mode):
    """Matrix rows narrowed to those at (or approaching) a gate under either model.

    Applied before the risk and offside passes rather than after, because those walk
    per-asset history and there is no reason to compute it for a row about to be
    dropped.
    """
    wanted = _FILTER_STATES.get(mode)
    if wanted is None or df.empty:
        return df
    return df[df[const.SETUP_CLS_COL].isin(wanted)
              | df[const.SETUP_NPF_COL].isin(wanted)]


def snapshot_caption(report_date):
    """The line under the title, for whichever week the grid is actually showing.

    Built from the SELECTED date rather than the newest one. It used to read
    get_available_dates()[0] unconditionally, which made it a claim about the store
    instead of about the table beneath it, and the two come apart both ways: pick an
    older week from the Target Date control and the caption still announced the newest,
    while a tab open across a Friday release kept announcing the week the page had
    loaded with. Same sentence, wrong in opposite directions.
    """
    if not report_date:
        return ("All data on this page reflects the official Commitments of Traders "
                "reporting snapshot as of Tuesday market close (Unknown Date).")
    pretty = datetime.strptime(report_date, '%Y-%m-%d').strftime('%B %d, %Y')
    return (f"All data on this page reflects the official Commitments of Traders "
            f"reporting snapshot as of Tuesday market close ({pretty}).")


def layout(**kwargs):
    # Built per request, not at import. Resolving these at module scope
    # made importing this page require a populated COTDATA_STORE.
    return html.Div([
        dbc.Container([
            dbc.Row([
                dbc.Col([
                    html.P(
                        id='heatmap_snapshot_caption',
                        children=snapshot_caption(
                            get_indexer().get_available_dates()[0]
                            if get_indexer().get_available_dates() else None),
                        style={
                            'textAlign': 'center',
                            'color': vc.TEXT_COLOR,
                            'fontSize': '0.9rem',
                            'marginBottom': '20px',
                            'marginTop': '20px',
                            'fontStyle': 'italic'
                        }
                    )
                ], width=12)
            ]),

            # Command Center (Glassmorphism Control Panel)
            dbc.Row([
                dbc.Col([
                    dbc.Card(
                        dbc.CardBody([
                            # Folded on a phone: stacked, these five controls fill the
                            # viewport, and this row is sticky, so the grid scrolled
                            # under a full-screen overlay. Folded, the sticky row is
                            # one button tall.
                            config_fold.wrap('heatmap', dbc.Row([
                                dbc.Col([
                                    controls.label("Lookback"),
                                    controls.lookback_select(
                                        'heatmap_lookback_selector',
                                        style={'borderRadius': '8px'})
                                ], xs=12, md=2, className="mb-3 mb-md-0 border-end border-secondary hide-border-below-md"),

                                dbc.Col([
                                    controls.label("Target Date"),
                                    controls.target_date_dropdown(
                                        'heatmap_date_selector')
                                ], xs=12, md=2, className="mb-3 mb-md-0 border-end border-secondary px-md-3 hide-border-below-md"),

                                dbc.Col([
                                    html.Label("Asset Classes", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    # Collapsed behind one toggle that states the
                                    # current answer. The switches inside keep this
                                    # page's own element id, so every callback reading
                                    # `page_heatmap_selector` is untouched.
                                    class_filter.control(
                                        'page_heatmap_selector',
                                        get_indexer().get_asset_classes()),
                                ], xs=12, md=3, className="mb-3 mb-md-0 border-end border-secondary px-md-3 hide-border-below-md"),

                                dbc.Col([
                                    html.Label(
                                        "Setups",
                                        title="Either model. A row survives if it is at "
                                              "the gate under Raw CLS 95/5 OR NPF CS "
                                              "80/20, because this grid reports both "
                                              "and hiding a row one of them fired on "
                                              "would contradict the block beside it.",
                                        style={**vc.label_style, "fontSize": "0.8rem",
                                               "textTransform": "uppercase",
                                               "cursor": "help"}),
                                    dbc.Select(
                                        id='heatmap_setup_filter',
                                        persistence='session',
                                        options=[
                                            {"label": "All markets", "value": SETUP_FILTER_ALL},
                                            {"label": "At a gate", "value": SETUP_FILTER_GATE},
                                            {"label": "At or approaching", "value": SETUP_FILTER_NEAR},
                                        ],
                                        value=SETUP_FILTER_ALL,
                                        className="bg-dark text-white border-secondary",
                                        style={'borderRadius': '8px'},
                                    )
                                ], xs=12, md=3, className="mb-3 mb-md-0 px-md-3"),

                                dbc.Col([
                                    dbc.Button(
                                        "Download CSV",
                                        id="btn-csv-export",
                                        size="sm",
                                        className="border-secondary text-white w-100 h-100",
                                        style={'backgroundColor': 'transparent', 'borderColor': 'rgba(147, 161, 161, 0.2)'}
                                    )
                                ], xs=12, md=2, className="d-flex align-items-center justify-content-end")
                            ], align="center"))
                        ]),
                        className="mb-4 shadow-sm",
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
                dcc.Loading(
                    id="loading-heatmap",
                    type="dot",
                    children=html.Div(id='heatmap_display_container'),
                    color=vc.BRIGHTER_TEXT_COLOR
                )
            ], justify='center')
        ], fluid=True),
    ])


@callback(
    Output('heatmap_snapshot_caption', 'children'),
    Input('heatmap_date_selector', 'value'),
)
def update_snapshot_caption(target_date):
    return snapshot_caption(target_date)


# The verdict colour set moved to components.plot_colors when the Crowding Strip
# started drawing the same bull/bear/near states. Re-imported under the old names so
# this page, and the tests that reach it through this module, keep reading.


# The two index families get different extreme bands. Normalizing by open interest
# removes the secular growth in contract size, so the normalized series sits at the
# ends of its own range far less often -- 95/5 would leave it almost never lit.
#
# Each band gets a ramp rather than a binary lit/dim: the gate keeps full saturation
# and its background wash, and two fainter text-only steps mark the approach, so a
# market walking toward a setup is visible before the week it arrives. Stops come
# from cotmetrics so this page and the emailed HTML step at the same values.
#
# styleConditions is first-match-wins (hence the catch-all "true" last), so these run
# strongest first. The bull and bear conditions are mutually exclusive, so pairing
# them per step is safe.
def oi_styles_for(colors, highlight=None):
    """Cell styling for the OI Z column.

    Same gate as the emailed HTML's OI Z column, which reads the constant too. Read at
    call time rather than at import so the threshold stays overridable in tests.
    """
    return [
        {"condition": f"Math.abs(params.value) >= {const.OI_ZSCORE_HIGHLIGHT_THRESHOLD}",
         "style": {"color": highlight or colors.bull}},
        {"condition": "true", "style": {"color": colors.dim}},
    ]


def setup_styles_for(state_col, role, high_val, low_val, colors,
                     near=const.SETUP_NEAR_WIDTH):
    """Style a positioning-index cell from its *row's* setup state.

    The state is resolved once per row by utils.setup_state and carried on the
    matrix, so these conditions only read it. Re-deriving `comm >= 95 AND lrg <= 5
    AND sml <= 5` as AG Grid condition strings would fork the setup rules between
    the strategy and the grid.

    A full setup washes every leg in the band. A near setup tints only the legs
    actually at or near their own gate, leaving the blocking leg neutral so it reads
    as the reason the setup has not fired.
    """
    st = f"params.data['{state_col}']"
    v = "params.value"
    is_eq = f"params.data['{const.IS_EQUITY_COL}']"
    # Equities skip the speculator legs in is_setup, so their spec cells never tint
    # on a near state.
    eq_guard = "" if role == "comm" else f" && !{is_eq}"
    if role == "comm":
        near_bull, near_bear = f"{v} >= {high_val - near}", f"{v} <= {low_val + near}"
    else:
        near_bull, near_bear = f"{v} <= {low_val + near}", f"{v} >= {high_val - near}"

    # An equity setup is decided by Commercials alone, so its spec legs can sit
    # anywhere. Washing one that disagrees would colour a cell against its own
    # value: DOW is a bear setup whose Small Specs sit at 64, and a red mid-range
    # cell invites being read as a bearish extreme. Commodity rows are unaffected,
    # since a full state already required every leg through its gate.
    if role == "comm":
        agrees_bull = agrees_bear = ""
    else:
        agrees_bull = f" && (!{is_eq} || {near_bull})"
        agrees_bear = f" && (!{is_eq} || {near_bear})"

    return [
        {"condition": f"{st} === '{const.SETUP_BULL}'{agrees_bull}",
         "style": {"backgroundColor": f"{colors.bull}{vc.INDEX_WASH}", "color": colors.bull}},
        {"condition": f"{st} === '{const.SETUP_BEAR}'{agrees_bear}",
         "style": {"backgroundColor": f"{colors.bear}{vc.INDEX_WASH}", "color": colors.bear}},
        {"condition": f"{st} === '{const.SETUP_NEAR_BULL}' && {near_bull}{eq_guard}",
         "style": {"color": colors.bull_near}},
        {"condition": f"{st} === '{const.SETUP_NEAR_BEAR}' && {near_bear}{eq_guard}",
         "style": {"color": colors.bear_near}},
        {"condition": "true", "style": {"color": colors.dim}},
    ]


# ── Speculator dollar risk ────────────────────────────────────────────────────
# One column joined onto the matrix from cotmetrics.exposure, which is where the
# arithmetic lives (this app computes no metrics of its own): speculator dollar risk
# as an expanding percentile of the market's own history.
#
# The DOLLAR LEVEL is deliberately not a column, only the cell's hover tooltip. It
# shipped as one and was removed the same week: a reader meets "$262M" with no idea
# what Gasoline typically carries, so the level answers nothing at a glance, and it
# drifts upward with price whatever positioning does (cotmetrics.exposure's own
# docstring: the most recent swings will always look the largest). The percentile is
# the module's answer to exactly that, so the grid shows the answer and keeps the
# input on hover. Cross-market dollar comparison is the /exposure page's job, where
# the levels come with the composition and coverage a total needs.
#
# Display thresholds for the percentile column, not a strategy gate. Both tails light
# the same way because both mean "at an extreme of this market's own history": the
# percentile ranks the SIGNED position, so high is a long extreme and low a short
# one, and colouring either tail bull/bear would render a verdict no model on this
# page renders.
RISK_RANK_HIGH = 95
RISK_RANK_LOW = 5


@functools.lru_cache(maxsize=256)
def _spec_risk(asset, newest_date):
    """One market's weekly speculator dollar risk and its expanding percentile.

    Keyed by the store's newest date purely as a cache-buster: a Friday release must
    invalidate this, and nothing else does. Lookback is deliberately NOT a key and the
    computation always passes "Custom", because the risk series reads net contracts,
    price and volatility, none of which the index-window control touches (the weekly
    frame is full-history under every lookback, only its index columns differ).

    The percentile is expanding against the market's own history, so a historical
    Target Date reads what was knowable that week rather than today's distribution.

    Returns {date_str: (risk_usd, pct_rank)} with NaNs already turned into None, or
    None when the market has no dollar risk at all (no contract multiplier, no bars).
    Broad catch by design: this is a display join, and one market without prices must
    not take the other 41 rows down with it.
    """
    try:
        ex = exposure.market_exposure(asset, leg=exposure.LEG_SPEC, lookback="Custom")
        risk = ex["risk_usd"]
        rank = exposure.expanding_pct_rank(risk)
    except Exception as e:
        utils.cot_logger.warning(f"heatmap: no speculator dollar risk for {asset}: {e}")
        return None
    return {ts.strftime('%Y-%m-%d'): (float(v) if v == v else None,
                                      float(r) if r == r else None)
            for ts, v, r in zip(risk.index, risk.to_numpy(), rank.to_numpy())}


def attach_spec_risk(df, newest_date):
    """Join the two exposure columns onto the matrix frame, by asset and week.

    Row-by-row on the row's OWN date rather than the page's target date: with no
    target selected each market shows its latest week, and those can differ.

    Both columns ride the rowData but only the percentile is a grid column: "Spec
    Risk" exists for the percentile cell's tooltipValueGetter, which reads it off
    params.data. Dropping it here would blank the tooltip, not raise.
    """
    risks, ranks = [], []
    for asset, date in zip(df["Asset"], df["Date"]):
        table = _spec_risk(asset, newest_date) or {}
        risk, rank = table.get(date, (None, None))
        risks.append(risk)
        ranks.append(rank)
    # Object dtype on purpose: a float column would coerce every None to NaN, and the
    # grid's null guards ('params.value != null') key on null, not NaN.
    df["Spec Risk"] = pd.Series(risks, index=df.index, dtype=object)
    df["Risk %ile"] = pd.Series(ranks, index=df.index, dtype=object)
    return df


#: How far under water is worth lighting, in the market's own weekly sigma. A DISPLAY
#: threshold, deliberately rounder than any figure in the study behind the measure: the
#: pooled tenth percentile of Large Spec readings is about -1.7 and the per-market median
#: cutoff about -1.4, so -2 lights a genuinely unusual reading without implying the grid
#: reproduces a statistic. Only the losing tail is lit; a cohort deep in PROFIT is not
#: distress, and the measure is not symmetric in what it says.
OFFSIDE_DEEP = -2.0

#: The cohort this column reads. Large Specs alone, NOT the large+small `LEG_SPEC` the
#: dollar-risk column uses, and the difference is not cosmetic: a basis computed on the
#: summed net describes a trader who is both cohorts at once, and the two have different
#: average costs and behave differently when under water (measured in
#: `npf/docs/handoffs/2026-08-23-offside-capitulation-prereg.md`). Large Specs is also
#: the cohort every published figure for this measure is quoted on.
OFFSIDE_LEG = exposure.LEG_LARGE


@functools.lru_cache(maxsize=256)
def _leg_offside(asset, newest_date):
    """One market's weekly offside reading, and the cost basis behind it.

    Keyed by the store's newest date purely as a cache-buster, exactly as `_spec_risk`
    is: a Friday release must invalidate this and nothing else does. Lookback is not a
    key and the computation always passes "Custom", because a cost basis reads net
    contracts and prices, none of which the index-window control touches.

    No percentile here, unlike the dollar-risk column, and the asymmetry is the point.
    Dollar risk is incomparable across markets, so it needs ranking against a market's
    own history before it means anything. Offside is ALREADY comparable: dividing by the
    market's own weekly sigma is what the measure does, and 0 means "at the cohort's
    average cost" in every market. Ranking it would throw that away and replace a
    readable quantity with a percentile of one.

    Returns {date_str: (offside, basis, price)} with NaNs already turned into None, or
    None when the market cannot be marked at all. Broad catch by design: this is a
    display join, and one market without prices must not take the other rows down.
    """
    try:
        r = offside.market_offside(asset, leg=OFFSIDE_LEG, lookback="Custom")
    except Exception as e:
        utils.cot_logger.warning(f"heatmap: no offside reading for {asset}: {e}")
        return None
    return {ts.strftime('%Y-%m-%d'): (float(o) if o == o else None,
                                      float(b) if b == b else None,
                                      float(p) if p == p else None)
            for ts, o, b, p in zip(r.index, r["offside"].to_numpy(),
                                   r["basis"].to_numpy(), r["price"].to_numpy())}


def attach_offside(df, newest_date):
    """Join the offside reading onto the matrix frame, by asset and week.

    Row-by-row on the row's OWN date rather than the page's target date, matching
    `attach_spec_risk`: with no target selected each market shows its latest week, and
    those can differ.

    Three columns ride the rowData and only one is a grid column: the basis and the mark
    exist for the cell's tooltipValueGetter, which reads them off params.data. Dropping
    them here would blank the tooltip, not raise.
    """
    reads, bases, prices = [], [], []
    for asset, date in zip(df["Asset"], df["Date"]):
        table = _leg_offside(asset, newest_date) or {}
        o, b, p = table.get(date, (None, None, None))
        reads.append(o)
        bases.append(b)
        prices.append(p)
    # Object dtype on purpose: a float column would coerce every None to NaN, and the
    # grid's null guards ('params.value != null') key on null, not NaN.
    df["Offside"] = pd.Series(reads, index=df.index, dtype=object)
    df["Offside Basis"] = pd.Series(bases, index=df.index, dtype=object)
    df["Offside Mark"] = pd.Series(prices, index=df.index, dtype=object)
    return df


def offside_styles_for(colors, highlight=None):
    """Cell styling for the Offside column.

    Lights the LOSING tail only, and uses the bear colour for it. That is a P&L
    statement rather than a market-direction verdict: the number is the sign of the
    cohort's own mark-to-market, so red means "these holders are down", not "this market
    goes lower". The distinction matters more here than anywhere else on the page,
    because the intuitive next step (they are trapped, so they must fold) was
    pre-registered, tested, and did not hold.

    The null guard is load-bearing for the same reason it is on the risk column: JS
    coerces null to 0, so without it a market with no basis yet would read as deeply
    offside rather than as blank.
    """
    return [
        {"condition": f"params.value != null && params.value <= {OFFSIDE_DEEP}",
         "style": {"color": highlight or colors.bear}},
        {"condition": "true", "style": {"color": colors.dim}},
    ]


def risk_rank_styles_for(colors, highlight=None):
    """Cell styling for the Risk %ile column.

    The null guard is load-bearing: JS coerces null to 0, so a bare `value <= 5` would
    light every market that has no percentile yet, which is exactly the set with the
    least history behind the number.
    """
    return [
        {"condition": f"params.value != null && (params.value >= {RISK_RANK_HIGH} "
                      f"|| params.value <= {RISK_RANK_LOW})",
         "style": {"color": highlight or colors.bull}},
        {"condition": "true", "style": {"color": colors.dim}},
    ]


def warm_caches():
    """Fill the grid's two join caches so no visitor pays the cold render.

    Called from main.py in a daemon thread at boot and again by the store poller
    when a new week lands, beside `crowd.warm_caches` and for the same reason:
    `newest_date` keys both joins, so a release invalidates the lot by
    construction. The Signal Matrix itself arrives warm (the crowd warmer builds
    it and this page rides along), but `_spec_risk` and `_leg_offside` did not:
    both read the PRICE store per market, so the first Heatmap render still paid
    the whole universe of dollar-risk and offside reads that nothing else warms.
    Failures are logged and swallowed: a warmer that can take the server down is
    worse than a slow first visitor.
    """
    try:
        indexer = get_indexer()
        available = indexer.get_available_dates()
        if not available:
            return
        newest = available[0]
        df = get_matrix_data(indexer.get_asset_classes(), "Custom", None)
        for record in df.to_dict("records"):
            _spec_risk(record.get("Asset"), newest)
            _leg_offside(record.get("Asset"), newest)
        utils.cot_logger.info(
            f"heatmap: warmed spec-risk and offside joins for {len(df)} "
            f"markets ({newest}).")
    except Exception as e:
        utils.cot_logger.warning(
            f"heatmap: cache warm failed, first render pays: {e}")


@callback(
    Output('heatmap_display_container', 'children'),
    [Input('page_heatmap_selector', 'value'),
     Input('global_lookback_store', 'data'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('heatmap_date_selector', 'value'),
     Input('heatmap_setup_filter', 'value')]
)
def render_heatmap_layout(assest_classes, lookback, palette_name, target_date,
                          setup_filter=SETUP_FILTER_ALL):
    utils.cot_logger.info(f"Rendering matrix with Asset Classes: {assest_classes}, Lookback: {lookback}, Palette: {palette_name}, Date: {target_date}")

    if not assest_classes:
        return html.P("Select an asset class to view the signal matrix.", style={'textAlign': 'center', 'color': vc.TEXT_COLOR})
    if not lookback:
        lookback = "Custom"

    df = get_matrix_data(assest_classes, lookback, target_date)
    if df.empty:
        return html.P("No data available.", style={'textAlign': 'center', 'color': vc.TEXT_COLOR})

    matched = filter_by_setup(df, setup_filter)
    if matched.empty:
        wording = ("at a gate" if setup_filter == SETUP_FILTER_GATE
                   else "at or approaching a gate")
        return html.P(
            f"No market in the selected asset classes is {wording} under either model "
            f"on this date.",
            style={'textAlign': 'center', 'color': vc.TEXT_COLOR})
    df = matched

    available = get_indexer().get_available_dates()
    df = attach_spec_risk(df, available[0] if available else None)
    df = attach_offside(df, available[0] if available else None)

    matrix_date = ""
    if not df.empty:
        matrix_date = df.iloc[0]["Date"]
    header_name = f"Asset Info — {matrix_date}" if matrix_date else "Asset Info"

    color_palette = viz_config.get_palette(palette_name)
    colors = grid_colors(color_palette)
    BULL_COLOR, BEAR_COLOR, DIM_TEXT = colors.bull, colors.bear, colors.dim

    oi_styles = oi_styles_for(colors, highlight=color_palette[2])
    risk_rank_styles = risk_rank_styles_for(colors, highlight=color_palette[2])
    offside_styles = offside_styles_for(colors)

    _RAW = models.RAW_PF.band
    _NORM = models.NPF.band

    index_styles = setup_styles_for(const.SETUP_CLS_COL, "comm", *_RAW, colors=colors)
    spec_styles = setup_styles_for(const.SETUP_CLS_COL, "spec", *_RAW, colors=colors)
    index_norm_styles = setup_styles_for(const.SETUP_NPF_COL, "comm", *_NORM, colors=colors)
    spec_norm_styles = setup_styles_for(const.SETUP_NPF_COL, "spec", *_NORM, colors=colors)

    inst_sentiment_styles = [
        {"condition": f"params.value <= {const.LW_LRG_SENTIMENT_MIN_THRESHOLD}", "style": {"color": BULL_COLOR}},
        {"condition": f"params.value >= {const.LW_LRG_SENTIMENT_MAX_THRESHOLD}", "style": {"color": BEAR_COLOR}},
        {"condition": "true", "style": {"color": DIM_TEXT}}
    ]

    willco_styles = [
        {"condition": f"params.value >= {const.WILLCO_MAX_THRESHOLD}", "style": {"color": BULL_COLOR}},
        {"condition": f"params.value <= {const.WILLCO_MIN_THRESHOLD}", "style": {"color": BEAR_COLOR}},
        {"condition": "true", "style": {"color": DIM_TEXT}}
    ]

    pull_styles = [
        {"condition": "params.value > 0", "style": {"color": BULL_COLOR, "fontSize": "0.68rem"}},
        {"condition": "params.value < 0", "style": {"color": BEAR_COLOR, "fontSize": "0.68rem"}},
        {"condition": "true", "style": {"color": DIM_TEXT, "fontSize": "0.68rem"}}
    ]

    setup_styles = [
        {"condition": "params.value === 'Bullish'", "style": {"color": BULL_COLOR, "fontSize": "11px", "opacity": "0.9"}},
        {"condition": "params.value === 'Bearish'", "style": {"color": BEAR_COLOR, "fontSize": "11px", "opacity": "0.9"}},
        {"condition": "true", "style": {"color": vc.TEXT_COLOR, "fontSize": "11px"}}
    ]


    def with_bg(styles, bg="rgba(255, 255, 255, 0.04)"):
        return [{"condition": s["condition"], "style": {**s["style"], "backgroundColor": s["style"].get("backgroundColor", bg)}} for s in styles]

    columnDefs = [
        {
            "headerName": header_name,
            "children": [
                {"field": "Asset Class", "filter": True, "pinned": "left", "width": 120},
                {
                    "field": "Asset",
                    "filter": True,
                    "pinned": "left",
                    "width": 150,
                    "cellRenderer": "markdown",
                    "valueFormatter": {"function": "params.value ? params.value.replace(/^\\\\[(.+?)\\\\]\\\\(.+?\\\\)$/, '$1') : params.value"},
                },
                {"field": "Tape Bias", "pinned": "left", "width": 90, "cellStyle": {"styleConditions": setup_styles}},
                {"field": "Signals", "pinned": "left", "width": 160, "cellRenderer": "SignalBadgesRenderer", "headerClass": "group-border-right", "cellClass": "group-border-right"},
            ]
        },
        {
            # The two blocks mirror the two npf books. Raw/all-three-legs/95-5 is the
            # Raw PF baseline (Raw CLS 95/5); OI-normalized/Comm+Small/80-20 is
            # NPF CS 80/20, the deployable headline. Large Specs is absent from the
            # second block because the CS gate drops that leg -- showing it here would
            # invite reading a column the book does not gate on.
            "headerName": f"Positioning · {models.RAW_PF.title}",
            "children": [
                {"field": "Comm Index", "headerTooltip": f"Williams Commercial Index, on net contracts. The C leg of the {models.RAW_PF.title} gate", "valueFormatter": {"function": "d3.format('.0f')(params.value)"}, "cellStyle": {"styleConditions": index_styles}},
                {"field": "Lrg Index", "headerTooltip": f"Large Speculators positioning index, on net contracts. The L leg of the {models.RAW_PF.title} gate, coloured only when opposed to Commercials, since that is the only configuration counted as a setup leg", "valueFormatter": {"function": "d3.format('.0f')(params.value)"}, "cellStyle": {"styleConditions": spec_styles}},
                {"field": "Sml Index", "headerTooltip": f"Small Traders positioning index, on net contracts. The S leg of the {models.RAW_PF.title} gate, coloured only when opposed to Commercials, since that is the only configuration counted as a setup leg", "valueFormatter": {"function": "d3.format('.0f')(params.value)"}, "cellStyle": {"styleConditions": spec_styles}, "headerClass": "group-border-right", "cellClass": "group-border-right"},
            ]
        },
        {
            "headerName": f"Positioning · {models.NPF.title}",
            # Wider than the default 90: this group is only two columns, so it gets the
            # least room to flex into and the header is the longest of the two blocks.
            "children": [
                {"field": "Comm Index Norm", "headerName": "Comm Index", "minWidth": 115, "headerTooltip": "Williams Commercial Index built on net / open interest, so contract-size growth is out of the level. The C leg of the NPF CS gate", "valueFormatter": {"function": "d3.format('.0f')(params.value)"}, "cellStyle": {"styleConditions": index_norm_styles}},
                {"field": "Sml Index Norm", "headerName": "Sml Index", "minWidth": 115, "headerTooltip": "Small Traders positioning index built on net / open interest. The S leg of the NPF CS gate, coloured only when opposed to Commercials", "valueFormatter": {"function": "d3.format('.0f')(params.value)"}, "cellStyle": {"styleConditions": spec_norm_styles}, "headerClass": "group-border-right", "cellClass": "group-border-right"},
            ]
        },
        {
            "headerName": "Index Momentum",
            "children": [
                {
                    "field": "Comm Move",
                    "headerTooltip": f"Commercial {vc.MOMENTUM_UNIT_PHRASE}",
                    "valueFormatter": {"function": "d3.format(',.0f')(params.value)"},
                    "cellRenderer": "MomentumRenderer",
                    "cellRendererParams": {
                        "maxThreshold": const.MOMENTUM_MAX_THRESHOLD,
                        "minThreshold": const.MOMENTUM_MIN_THRESHOLD,
                        "neutralColor": DIM_TEXT
                    }
                },
                {
                    "field": "Lrg Move",
                    "headerTooltip": f"Large Speculator {vc.MOMENTUM_UNIT_PHRASE}",
                    "valueFormatter": {"function": "d3.format(',.0f')(params.value)"},
                    "cellRenderer": "MomentumRenderer",
                    "cellRendererParams": {
                        "maxThreshold": const.MOMENTUM_MAX_THRESHOLD,
                        "minThreshold": const.MOMENTUM_MIN_THRESHOLD,
                        "neutralColor": DIM_TEXT
                    }
                },
                {
                    "field": "Sml Move",
                    "headerTooltip": f"Small Trader {vc.MOMENTUM_UNIT_PHRASE}",
                    "valueFormatter": {"function": "d3.format(',.0f')(params.value)"},
                    "cellRenderer": "MomentumRenderer",
                    "cellRendererParams": {
                        "maxThreshold": const.MOMENTUM_MAX_THRESHOLD,
                        "minThreshold": const.MOMENTUM_MIN_THRESHOLD,
                        "neutralColor": DIM_TEXT
                    },
                    "headerClass": "group-border-right",
                    "cellClass": "group-border-right"
                },
            ]
        },
        {
            "headerName": "Friction & Flow",
            "children": [
                {"field": "WILLCO", "headerTooltip": "Williams Commercial Index (Thresholds: <= 20 Bearish / >= 80 Bullish)", "valueFormatter": {"function": "d3.format('.0f')(params.value)"}, "cellStyle": {"styleConditions": willco_styles}},
                # minWidth 110, not the default 90: at 90 the header wraps mid-word
                # ("Sentim / ent"), and wrapHeaderText cannot know where the word breaks.
                {"field": "Inst Sentiment", "minWidth": 110, "headerTooltip": "Institutional Speculator Sentiment (Thresholds: <= 20 Bullish / >= 80 Bearish)", "valueFormatter": {"function": "d3.format('.0f')(params.value)"}, "cellStyle": {"styleConditions": inst_sentiment_styles}, "headerClass": "group-border-right", "cellClass": "group-border-right"},
            ]
        },
        {
            "headerName": "Exposure · Speculators",
            "children": [
                {
                    "field": "Risk %ile",
                    "minWidth": 100,
                    "headerTooltip": (
                        f"Net {exposure.LEG_LABELS[exposure.LEG_SPEC]} position in USD "
                        f"daily risk (contracts x point value x price x "
                        f"{exposure.DEFAULT_VOL_WINDOW}-day vol), as an expanding "
                        f"percentile of this market's own history, so a past date "
                        f"reads what was knowable then: 100 is the most net-long "
                        f"speculators have ever been, 0 the most net-short. Lit at "
                        f">= {RISK_RANK_HIGH} or <= {RISK_RANK_LOW}. Hover a cell for "
                        f"the dollar figure. Blank until two years of priced history"),
                    "valueFormatter": {"function": "params.value != null ? d3.format('.0f')(params.value) : '–'"},
                    # The dollar level behind the percentile, on hover rather than in a
                    # column (see the module comment above). d3's SI suffix for 1e9 is
                    # G, which nobody reads as dollars, hence the replace; the sign is
                    # spelled out because a bare minus is easy to miss in a tooltip.
                    "tooltipValueGetter": {"function": (
                        "params.data['Spec Risk'] != null ? "
                        "d3.format('$.3s')(Math.abs(params.data['Spec Risk'])).replace('G','B')"
                        " + (params.data['Spec Risk'] < 0 ? ' net short' : ' net long')"
                        " + ' in daily risk' : null")},
                    "cellStyle": {"styleConditions": risk_rank_styles},
                    "headerClass": "group-border-right",
                    "cellClass": "group-border-right",
                },
            ]
        },
        {
            # Its own group rather than a third column under Exposure, because it reads a
            # different cohort (Large Specs, not Large+Small) and answers the opposite
            # question. Exposure is about SIZE; this is about P&L per contract, and the
            # two move independently: a cohort can be at a record position and in profit,
            # which is in fact the common case.
            "headerName": "Cost Basis · Large Specs",
            "children": [
                {
                    "field": "Offside",
                    "minWidth": 100,
                    "headerTooltip": (
                        f"How far {exposure.LEG_LABELS[OFFSIDE_LEG]} sit from their own "
                        f"average cost, in this market's weekly standard deviations. "
                        f"Negative is under water. Per CONTRACT, so position size does "
                        f"not enter: -3 means the cohort is three typical weekly moves "
                        f"below what it paid, whether it holds 400 lots or 400,000. "
                        f"Basis is average-cost on the weekly net, marked on "
                        f"ratio-adjusted prices. Lit at <= {OFFSIDE_DEEP:.0f}. This is a "
                        f"reading of who is LOSING, not a forecast: deep readings were "
                        f"tested for predicting capitulation and did not, so a lit cell "
                        f"is not a signal that the position is about to be cut. Hover a "
                        f"cell for the basis. Blank until the market has half a year of "
                        f"priced history"),
                    "valueFormatter": {"function": "params.value != null ? d3.format('+.1f')(params.value) : '–'"},
                    # The two prices behind the ratio, on hover rather than in columns,
                    # on the same argument as the dollar-risk level one group over: a
                    # reader who wants the level wants it once, not in every row.
                    "tooltipValueGetter": {"function": (
                        "params.data['Offside Basis'] != null ? "
                        "'cost ' + d3.format(',.2f')(params.data['Offside Basis'])"
                        " + ' vs mark ' + d3.format(',.2f')(params.data['Offside Mark'])"
                        " : null")},
                    "cellStyle": {"styleConditions": offside_styles},
                    "headerClass": "group-border-right",
                    "cellClass": "group-border-right",
                },
            ]
        },
        {
            "headerName": "Open Interest",
            "children": [
                {
                    "field": "OI Z",
                    "headerTooltip": "Open Interest Z-score relative to history",
                    "valueFormatter": {"function": "d3.format('+.2f')(params.value)"},
                    "cellStyle": {"styleConditions": oi_styles}
                },
                # Delta IV is deliberately absent, on the argument that retired the
                # dollar-risk level one column over, only stronger. It is the gap in
                # TOTAL CHAIN INTRINSIC VALUE between the current price and max pain,
                # in millions, so it scales with the size of the option chain it was
                # measured on: live, it ran 0.0001 (5-Year Note) to 8.5 (Gold), five
                # orders of magnitude, which is a chain-size ranking rather than a
                # reading about any market.
                #
                # And the chain is never the futures market's. Every symbol here is
                # priced through options_data.ETF_PROXIES, and the snapshot scales the
                # STRIKES to futures while leaving IntrinsicValue_M in the ETF chain's
                # own dollars, so the number cannot honestly be labelled in the units
                # of the row it sits on. That is why it is dropped outright rather than
                # moved to a hover the way $ Risk was: a tooltip has to say what the
                # number IS.
                #
                # Nothing is lost from the page. Max Pain Pull above is the same
                # phenomenon, the distance between price and max pain, as a percentage,
                # which IS comparable across markets and is the half a reader can act
                # on. get_matrix_data still carries the column for the emailed HTML.
                {
                    "field": "Max Pain Pull",
                    "headerTooltip": "Distance from the current price to max pain, as a percent of price. Positive means max pain sits above the market",
                    "cellStyle": {"styleConditions": pull_styles},
                    "valueFormatter": {"function": "params.value != null ? d3.format('+.1f')(params.value) + '%' : '–'"},
                    "headerClass": "group-border-right",
                    "cellClass": "group-border-right",
                },
            ]
        }
    ]

    # Every column past the pinned four is a number, and numbers compare by their
    # right edge: left-aligned, 9 sits under 100's hundreds digit and reads larger.
    # Done as a pass rather than per definition so a new column cannot forget it, and
    # driven by the text set because that is the list that is actually short. The
    # matching font-variant-numeric: tabular-nums lives in custom.css.
    _TEXT_FIELDS = {"Asset Class", "Asset", "Tape Bias", "Signals"}
    for group in columnDefs:
        for child in group["children"]:
            if child["field"] not in _TEXT_FIELDS:
                child["type"] = "rightAligned"

    # The four pinned columns are 520px together, and AG Grid gives pinned
    # columns priority, so on a phone they consumed the whole viewport and the
    # scrollable body had no room left: the grid rendered as a two-column sliver
    # of truncated text. Keep only the market name frozen there and let the rest
    # scroll under it. Same per-request sniff as plot_layout.visible_weeks; this
    # runs in a callback, so a rotation that changes nothing about the UA keeps
    # the same answer, which is the known cost of deciding server-side.
    if app_utils.is_mobile():
        for group in columnDefs:
            for child in group["children"]:
                if child.get("pinned") and child["field"] != "Asset":
                    del child["pinned"]

    # Convert asset column to markdown links
    df['Asset'] = df['Asset'].apply(lambda x: f"[{x}](/oi_alignment?asset={urllib.parse.quote(x)})")

    grid = dag.AgGrid(
        id="heatmap-matrix-grid",
        rowData=df.to_dict("records"),
        columnDefs=columnDefs,
        className="ag-theme-quartz-dark",
        style={"height": "80vh", "width": "100%", "fontSize": "13px"},
        defaultColDef={
            "sortable": True,
            "filter": True,
            "wrapHeaderText": True,
            "autoHeaderHeight": True,
            "minWidth": 90,
            "flex": 1,
        },
        dashGridOptions={
            "rowHeight": 32,
            "pagination": False,
            "tooltipShowDelay": 500,
        },
    )

    # The colour grammar, in words, once. The grid encodes verdicts (a washed cell is
    # a full setup, tinted text a leg near its gate) and nothing on the page said so;
    # the tooltips explain columns one at a time, which is no help to a reader asking
    # what the colours mean at all. One muted line, under the grid so it costs the
    # table nothing above the fold.
    key_line = html.P(
        "Reading the colours: a washed cell is a full setup on that model, every leg "
        "it gates on through its band; bright text is a leg at its gate; faint tinted "
        "text is a leg approaching it, with the blocking leg left grey. Risk %ile and "
        "OI Z light at extremes of the market's own history and render no verdict. "
        "Hover any header for its definition and thresholds.",
        style={'color': vc.TEXT_COLOR, 'fontSize': '0.8rem', 'fontStyle': 'italic',
               'marginTop': '8px', 'marginBottom': '4px'})

    return dbc.Row([
        dbc.Col(grid, width=12),
        dbc.Col(key_line, width=12),
    ])


clientside_callback(
    ClientsideFunction(
        namespace='clientside',
        function_name='export_heatmap_csv'
    ),
    Output("btn-csv-export", "n_clicks"),
    Input("btn-csv-export", "n_clicks"),
    prevent_initial_call=True
)
