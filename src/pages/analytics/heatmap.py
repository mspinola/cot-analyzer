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
from cotmetrics import exposure
from cotmetrics.indexer import get_indexer
from cotmetrics.reports import get_matrix_data
from dash import (
    ClientsideFunction,
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    dcc,
    html,
    no_update,
)

import viz_config
import viz_constants as vc
from app_utils import next_date_selection
from components.plot_colors import GridColors, grid_colors  # noqa: F401

dash.register_page(__name__, path="/heatmap")


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
                            dbc.Row([
                                dbc.Col([
                                    html.Label("Lookback Window", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dbc.Select(
                                        id='heatmap_lookback_selector',
                                        persistence='session',
                                        options=[
                                            {"label": "26 Weeks", "value": "26"},
                                            {"label": "52 Weeks", "value": "52"},
                                            {"label": "Custom", "value": "Custom"},
                                        ],
                                        value="Custom",
                                        className="bg-dark text-white border-secondary",
                                        style={'borderRadius': '8px'}
                                    )
                                ], xs=12, md=2, className="mb-3 mb-md-0 border-end border-secondary hide-border-below-md"),

                                dbc.Col([
                                    html.Label("Target Date", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dcc.Dropdown(
                                        id='heatmap_date_selector',
                                        options=[{'label': d, 'value': d} for d in get_indexer().get_available_dates()],
                                        value=get_indexer().get_available_dates()[0] if get_indexer().get_available_dates() else None,
                                        className="dash-dropdown bg-dark text-white",
                                        searchable=True,
                                        clearable=False,
                                        style={'borderRadius': '8px'}
                                    )
                                ], xs=12, md=3, className="mb-3 mb-md-0 border-end border-secondary px-md-3 hide-border-below-md"),

                                dbc.Col([
                                    html.Label("Asset Classes", style={**vc.label_style, "fontSize": "0.8rem", "textTransform": "uppercase"}),
                                    dbc.Checklist(
                                        persistence='session',
                                        id='page_heatmap_selector',
                                        options=[{"label": x, "value": x} for x in get_indexer().get_asset_classes()],
                                        value=get_indexer().get_asset_classes(),
                                        inline=True,
                                        switch=True,
                                        style={"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "0.95rem"}
                                    ),
                                ], xs=12, md=5, className="mb-3 mb-md-0 px-md-4"),

                                dbc.Col([
                                    dbc.Button(
                                        "Download CSV",
                                        id="btn-csv-export",
                                        size="sm",
                                        className="border-secondary text-white w-100 h-100",
                                        style={'backgroundColor': 'transparent', 'borderColor': 'rgba(147, 161, 161, 0.2)'}
                                    )
                                ], xs=12, md=2, className="d-flex align-items-center justify-content-end")
                            ], align="center")
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
    Output('heatmap_date_selector', 'options'),
    Output('heatmap_date_selector', 'value'),
    Input('cot_release_store', 'data'),
    State('heatmap_date_selector', 'options'),
    State('heatmap_date_selector', 'value'),
)
def follow_the_store(_release, current_options, current_value):
    """Re-offer the available weeks when the server takes a new one."""
    return next_date_selection(get_indexer().get_available_dates(),
                               current_options, current_value)


@callback(
    Output('heatmap_snapshot_caption', 'children'),
    Input('heatmap_date_selector', 'value'),
)
def update_snapshot_caption(target_date):
    return snapshot_caption(target_date)


@callback(
    Output('global_lookback_store', 'data', allow_duplicate=True),
    Input('heatmap_lookback_selector', 'value'),
    State('global_lookback_store', 'data'),
    prevent_initial_call=True
)
def update_global_lookback(value, current_store_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_store_val:
        return no_update
    return new_val


@callback(
    Output('heatmap_lookback_selector', 'value'),
    Input('global_lookback_store', 'data'),
    State('heatmap_lookback_selector', 'value')
)
def update_local_lookback(value, current_local_val):
    new_val = value if value in ["26", "52", "Custom"] else "Custom"
    if new_val == current_local_val:
        return no_update
    return new_val



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


@callback(
    Output('heatmap_display_container', 'children'),
    [Input('page_heatmap_selector', 'value'),
     Input('global_lookback_store', 'data'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('heatmap_date_selector', 'value')]
)
def render_heatmap_layout(assest_classes, lookback, palette_name, target_date):
    utils.cot_logger.info(f"Rendering matrix with Asset Classes: {assest_classes}, Lookback: {lookback}, Palette: {palette_name}, Date: {target_date}")

    if not assest_classes:
        return html.P("Select an asset class to view the signal matrix.", style={'textAlign': 'center', 'color': vc.TEXT_COLOR})
    if not lookback:
        lookback = "Custom"

    df = get_matrix_data(assest_classes, lookback, target_date)
    if df.empty:
        return html.P("No data available.", style={'textAlign': 'center', 'color': vc.TEXT_COLOR})

    available = get_indexer().get_available_dates()
    df = attach_spec_risk(df, available[0] if available else None)

    matrix_date = ""
    if not df.empty:
        matrix_date = df.iloc[0]["Date"]
    header_name = f"Asset Info — {matrix_date}" if matrix_date else "Asset Info"

    color_palette = viz_config.get_palette(palette_name)
    colors = grid_colors(color_palette)
    BULL_COLOR, BEAR_COLOR, DIM_TEXT = colors.bull, colors.bear, colors.dim

    oi_styles = oi_styles_for(colors, highlight=color_palette[2])
    risk_rank_styles = risk_rank_styles_for(colors, highlight=color_palette[2])

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
            "headerName": "Open Interest",
            "children": [
                {
                    "field": "OI Z",
                    "headerTooltip": "Open Interest Z-score relative to history",
                    "valueFormatter": {"function": "d3.format('+.2f')(params.value)"},
                    "cellStyle": {"styleConditions": oi_styles}
                },
                {
                    "field": "Max Pain Pull",
                    "headerTooltip": "Max Pain Pull (%)",
                    "cellStyle": {"styleConditions": pull_styles},
                    "valueFormatter": {"function": "params.value ? d3.format('+.1f')(params.value) + '%' : '–'"}
                },
                {
                    "field": "Delta IV",
                    "headerTooltip": "Delta Intrinsic Value",
                    "cellStyle": {"fontSize": "0.68rem", "color": DIM_TEXT},
                    "valueFormatter": {"function": "params.value ? (Math.abs(params.value) < 0.1 ? d3.format(',.3f')(params.value) : Math.abs(params.value) < 1.0 ? d3.format(',.2f')(params.value) : d3.format(',.1f')(params.value)) : '–'"}
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
