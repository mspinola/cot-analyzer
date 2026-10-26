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
Selecting all nine renders nine cards rather than one 42-column table.

**One window across every column, and it is NOT the model's.** `cotmetrics-config`
tunes `CustomLookbackWeeks` per market (the pound at 30 weeks, the euro at 90), which
is right for a gate and wrong for a row: nine differently-defined numbers side by side
invite exactly the comparison they do not support. Every row below the gate therefore
reads the uniform 52-week lookback. The gate row does not, because its verdict has to
be the same verdict every other surface in the app shows, and that one is computed on
the model's own window. The two windows differ, the caption says so, and that is a
real cost of the format rather than a detail to reconcile.

Where the arithmetic lives, since this repo computes no metrics of its own: the level
rows are `get_symbols_data`'s own alias columns for the model's basis, the Commercial
move is `cotmetrics.indicators.calculate_range_index` over the index momentum column,
and the paths are the weekly closes and open interest the same frame carries. The
drawing, the colour rule and the row set live in `components.scorecard_rows`, which is
pure over a read plus a colour set; this module is the data join, the controls and the
caption.

The trap this page inherits from every other index surface and must keep saying: a
TRAILING window renormalises every week, so a market that has been heavily short all
year reads near the top on its least-short week. The caption carries it, because a
card built for a fast sweep is exactly where that misread is cheapest to make.
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
from dash import Input, Output, callback, dcc, html

import components.scorecard_rows as scorecard_rows
import viz_config
import viz_constants as vc
from components import class_filter, config_fold, controls, help_fold
from components.plot_colors import grid_colors
from components.strip_traces import SETUP_COLUMN

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
    # The alias columns already follow `basis`, so these are the model's own series.
    # Re-deriving them from "Comm Net Pos" would quietly draw the RAW basis under a
    # normalized header, because the basis argument moves the aliases and not the
    # underlying net-position columns.
    out["comm"] = df.get("comms_idx")
    out["nonrept"] = df.get("sml_idx")
    # Index momentum is a POINT change of a bounded index, so it is not already on the
    # 0-100 scale the card's cells need; range-index it over the shared window.
    if "comm_momentum" in df:
        out["comm_move"] = calculate_range_index(df["comm_momentum"],
                                                 window=scorecard_rows.WINDOW)
    out["price"] = df.get(const.CLOSING_PRICE)
    out["oi"] = df.get(const.OPEN_INTEREST)
    return out


def _clean(value):
    return None if value is None or value != value else float(value)


def _read_for(asset, record, basis, model, newest_date, target_date):
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

    instrument = get_indexer().get_instrument_from_name(asset)
    return scorecard_rows.MarketRead(
        symbol=getattr(instrument, "symbol", "") or "",
        asset=asset,
        state=record.get(SETUP_COLUMN[model.key]) or const.SETUP_NONE,
        scores=scores,
        paths=paths,
        date=frame.index[-1].strftime('%Y-%m-%d'),
    )


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
                count += 1
        utils.cot_logger.info(
            f"scorecard: warmed {count} markets ({newest}).")
    except Exception as e:  # noqa: BLE001 -- a warmer must never fail a boot
        utils.cot_logger.warning(
            f"scorecard: cache warm failed, first render pays: {e}")


def caption(report_date, model, skipped):
    """The line under the cards: the FACTS of this render and nothing more.

    The two windows get named explicitly rather than left to the fold, because a
    reader comparing a Setup chip here against the Heatmap's needs to know the rows
    below it are measured on a different lookback than the chip.
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
    return (
        f"Positioning as of Tuesday {pretty}, measured as {basis} "
        f"({model.title}'s basis). The Setup row is {model.title}'s verdict on its "
        f"own tuned window; every row below it is a uniform 52 weeks, so that the "
        f"columns can be compared. Colour is the model's verdict, not the cell's "
        f"own value.{dropped}"
    )


def help_text(model):
    """The teaching: the scale, the colour rule, and the trailing-window trap.

    Model-aware, so it is rendered per callback rather than baked into the layout.
    The colour sentence is the one that earns its length: this page and `/crowd`
    use opposite conventions, and a reader moving between them in one session will
    otherwise read one of the two backwards.
    """
    return (
        f"Each numbered cell is that row's reading as a range index over the same "
        f"52 weekly reports (0 at the window's low, 100 at its high), rewritten as "
        f"-{scorecard_rows.SCALE} to +{scorecard_rows.SCALE} so rows of different "
        f"origin share one scale. Nothing is sign-flipped: a number is always its "
        f"own native level, and the COLOUR carries what that level means under "
        f"{model.title}. So a Non-Reportable index of -9 is small specs washed out, "
        f"which is the bullish side, and the cell reads -9 while drawing the bull "
        f"hue. A number and its colour disagreeing is the informative case, not a "
        f"defect, and it is the same rule the Crowding Strip follows and the "
        f"OPPOSITE of the Crowdedness Board, where colour is the cell's own value. "
        f"A cell with a FILL is a row the model gives a direction; the gates read "
        f"three positioning indices and no price term, so price and open interest "
        f"have no verdict to carry and are drawn as paths instead, each over the "
        f"same 52 weeks with a faint rule at the midpoint of its own range and a "
        f"dot on the latest week. Hover any row label for how much that row adds "
        f"over the Commercial Index, and any path for its figure. A trailing window "
        f"renormalises every week, so a market short all year still reads near the "
        f"top on its least-short week. Only the Setup row has been through the "
        f"gauntlet; everything under it is description, which is why there is no "
        f"summary score."
    )


def layout(**kwargs):
    # Built per request, not at import, so importing this page needs no store.
    return html.Div([
        dbc.Container([
            dbc.Row([
                dbc.Col([
                    dbc.Card(
                        dbc.CardBody([
                            config_fold.wrap('scorecard', dbc.Row([
                                dbc.Col([
                                    controls.label("Target Date"),
                                    controls.target_date_dropdown(
                                        'scorecard_date_selector'),
                                ], xs=12, md=4, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    controls.label("Model"),
                                    # persistence=None: the value rides the global
                                    # store, the Crowd page's convention.
                                    controls.model_select(
                                        'scorecard_model_selector', size="sm",
                                        persistence=None),
                                ], xs=6, md=3, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Asset Classes",
                                               style={**vc.label_style,
                                                      "fontSize": "0.8rem",
                                                      "textTransform": "uppercase"}),
                                    class_filter.control(
                                        'scorecard_class_selector',
                                        get_indexer().get_asset_classes()),
                                ], xs=12, md=5, className="px-md-2"),
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

            dbc.Row([
                dbc.Col([
                    html.P(id='scorecard_caption',
                           style={'color': vc.TEXT_COLOR, 'fontSize': '0.85rem',
                                  'fontStyle': 'italic', 'marginBottom': '4px'}),
                    help_fold.wrap('scorecard', html.P(
                        id='scorecard_help',
                        style={'color': vc.TEXT_COLOR, 'fontSize': '0.85rem',
                               'fontStyle': 'italic', 'marginBottom': '4px'})),
                ], xs=12),
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
        ], fluid=True),
    ])


@callback(
    Output('scorecard_container', 'children'),
    Output('scorecard_caption', 'children'),
    Output('scorecard_help', 'children'),
    [Input('scorecard_class_selector', 'value'),
     Input('global_model_store', 'data'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('scorecard_date_selector', 'value')],
)
def render_scorecard(asset_classes, model_key, palette_name, target_date):
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
    colors = grid_colors(viz_config.get_palette(palette_name))

    cards, unreadable, report_date = [], [], None
    for asset_class, group in df.groupby("Asset Class", sort=True):
        reads = []
        for record in group.to_dict("records"):
            asset = record.get("Asset")
            read = _read_for(asset, record, model.basis, model, newest, target_date)
            if read is None:
                unreadable.append(asset)
            else:
                reads.append(read)
        if not reads:
            continue
        report_date = report_date or reads[0].date
        cards.append(html.Div([
            html.H2(asset_class,
                    style={"fontSize": "1rem", "fontWeight": "600",
                           "color": vc.BRIGHTER_TEXT_COLOR, "margin": "0 0 6px"}),
            scorecard_rows.build_table(reads, model, colors),
        ], className="mb-4"))

    if not cards:
        return (html.P("No data available.",
                       style={'textAlign': 'center', 'color': vc.TEXT_COLOR}),
                "", help_text(model))

    return (
        html.Div(cards, style={"maxWidth": "980px", "margin": "0 auto"}),
        caption(target_date or report_date, model, sorted(set(unreadable))),
        help_text(model),
    )
