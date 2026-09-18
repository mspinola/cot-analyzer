"""The Crowdedness Board: every market against four windows.

The Strip already puts the whole board on one screen for ONE window. This page asks
the question the Strip's caption warns about from the other side: how does the same
reading change as the window changes. Four windows per row (13, 26 and 52 weekly
reports, then the market's full history), so the cross-window pattern is visible
instead of reconstructed from memory. `components.board_traces` owns the drawing and
the departure note about colour; this module is the data join, the controls and the
caption.

Where the arithmetic lives, since this repo computes no metrics of its own: the
series is `get_symbols_data`'s net-position column for the model's basis, and every
cell is `cotmetrics.indicators.calculate_range_index` over it. This page only
composes the two, the same shape as the Strip's dollar lens, and under the same rule:
the moment a second surface wants a multi-window index table, the sweep moves to
`cotmetrics.reports` beside `get_matrix_data` rather than being copied.

Two compositional choices that would otherwise look arbitrary:

- **Windows are `weeks + 1` observations.** `CotIndexer.process_lookback` slices
  `[idx - lb : idx + 1]`, so the app's existing "52-week" columns are computed over
  53 observations, and `categories.build_category_frame` already passes `window=lb+1`
  to match. This page does the same, so its 12M column and the Strip's 52-week
  reading are the same number rather than neighbours.
- **Full history is the same function with `window=len(series)`.** A rolling window
  covering the whole series IS the expanding window, position by position, so no new
  metric exists here. If cotmetrics ever grows an explicit expanding form (the
  natural spelling is `calculate_range_index(series, window=None)`, mirroring
  `exposure.windowed_pct_rank`), this is the line that switches to it. Its
  `min_periods` mirrors `windowed_pct_rank`'s 104 for the same reason that default
  exists: an "all history" reading over a dozen rows is noise wearing a long name.

The trap this page inherits and must keep saying: a TRAILING window renormalises
every week. `exposure.windowed_pct_rank`'s docstring measures it: on a 52-week
window, a market that has been heavily short all year reads near 100 on its
least-short week. The shorter the window the worse it bites, so the 3M column is a
statement about the recent range only, never about whether the market is long. The
caption carries this, because the board's whole selling point (a fast sweep) is
exactly what makes the misread cheap.
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
from cotmetrics.reports import get_matrix_data
from dash import (
    Input,
    Output,
    State,
    callback,
    clientside_callback,
    dcc,
    html,
    no_update,
)

import app_utils
import components.board_traces as board_traces
import components.breadth_panel as breadth_panel
import components.tape_context as tape_context
import viz_config
import viz_constants as vc
from components import class_filter, config_fold, controls, help_fold
from components.plot_colors import grid_colors
from components.strip_traces import SETUP_COLUMN

dash.register_page(
    __name__, path='/crowd',
    title='COT Crowdedness Board | COT Analyzer',
    description='How crowded is each futures market? Range index of Commercial '
                'net positioning over 13, 26 and 52 weeks and full history, '
                'from the weekly COT report.',
)

# Layout runs per request; the wiring must not.
class_filter.register('crowd_class_selector')
controls.register_model('crowd_model_selector')
controls.register_target_date('crowd_date_selector')

# The PNG export, the Strip's machinery exactly (see exportBoardImage in
# clientside.js): the board snapshotted at on-screen size, the caption and the
# how-to-read fold opened in the clone. Model and date ride along only to name
# the file.
clientside_callback(
    "window.dash_clientside.clientside.export_crowd_image",
    Output('crowd_download_img_btn', 'n_clicks'),
    Input('crowd_download_img_btn', 'n_clicks'),
    State('crowd_model_selector', 'value'),
    State('crowd_date_selector', 'value'),
    prevent_initial_call=True,
)

ORDER_LABELS = {
    board_traces.ORDER_CLASS: "By class",
    board_traces.ORDER_FLAT: "Most crowded",
    board_traces.ORDER_ALPHA: "A-Z",
}

# See the module docstring: mirrors exposure.windowed_pct_rank's min_periods. Lives
# with the window rule in tape_context, which scores the context rows the same way.
FULL_HISTORY_MIN_WEEKS = tape_context.FULL_HISTORY_MIN_WEEKS


@functools.lru_cache(maxsize=256)
def _market_indices(asset, basis, newest_date):
    """One market's four window-index series, plus the change and path columns.

    `newest_date` is a cache-buster and nothing else, the `_dollar_reads` convention:
    a Friday release must invalidate this and nothing else does. Returns a frame
    indexed by report date with one column per WINDOW_WEEKS entry (keyed by its
    label), plus "move" and nothing more, or None when the market has no usable
    series. The catch is broad for the Strip's reason: one broken market must not
    take the rest of the board down with it.
    """
    try:
        df = get_indexer().get_symbols_data(asset, "52")
        col = (const.COMM_NET_NORM if basis == const.BASIS_OI_NORM
               else const.COMM_NET)
        net = df[col].astype(float)
    except Exception as e:
        utils.cot_logger.warning(f"crowd: no series for {asset}: {e}")
        return None
    if net.notna().sum() < 2:
        return None

    # One window rule for the markets and the tape-context rows under them.
    return tape_context.window_index_frame(net)


def _clean(value):
    return None if value is None or value != value else float(value)


def _symbol_for(asset):
    """The ticker beside the name. Blank rather than raising for a market the
    registry cannot resolve: the symbol is a scanning aid, not a join key."""
    instrument = get_indexer().get_instrument_from_name(asset)
    return getattr(instrument, "symbol", "") or ""


def _read_for(asset, record, basis, model, newest_date, target_date):
    """A MarketRead at the week the board is showing, or None.

    Row by row on each market's own dates rather than one global row position, the
    same convention the Heatmap's joins follow: with no target selected each market
    shows its latest week, and those can differ.
    """
    frame = _market_indices(asset, basis, newest_date)
    if frame is None or frame.empty:
        return None
    if target_date:
        frame = frame.loc[frame.index <= pd.Timestamp(target_date)]
        if frame.empty:
            return None
    latest = frame.iloc[-1]
    year_label = board_traces.WINDOW_LABELS[2]
    path = tuple(_clean(v) for v in frame[year_label].tail(52))
    return board_traces.MarketRead(
        asset=asset,
        asset_class=record.get("Asset Class"),
        symbol=_symbol_for(asset),
        windows=tuple(_clean(latest[label]) for label in board_traces.WINDOW_LABELS),
        history_weeks=frame.attrs.get("history_weeks"),
        start=frame.attrs.get("start"),
        move=_clean(latest["move"]),
        path=path,
        state=record.get(SETUP_COLUMN[model.key]) or const.SETUP_NONE,
        is_equity=bool(record.get(const.IS_EQUITY_COL)),
        date=frame.index[-1].strftime('%Y-%m-%d'),
    )


def warm_caches():
    """Fill the board's per-market caches so no visitor pays the cold render.

    Called from main.py in a daemon thread at boot and again by the store poller
    when a new week lands, the same reasoning as the poller itself: `newest_date`
    keys every entry, so a release invalidates the lot by construction, and without
    this the first visitor afterwards pays it all. Measured 2026-08-27 on the
    42-market universe: ~2.3s for the Signal Matrix (also the Heatmap's and the
    Strip's first-render cost, so they ride along) plus ~2.2s per basis for the
    window indices, against ~0.2s for a warm render. Both bases, so the first model
    switch is warm too. Failures are logged and swallowed: a warmer that can take
    the server down is worse than a slow first visitor.
    """
    try:
        indexer = get_indexer()
        available = indexer.get_available_dates()
        if not available:
            return
        newest = available[0]
        df = get_matrix_data(indexer.get_asset_classes(), "Custom", None)
        # Distinct bases, not one per model: the cache is keyed on the basis, and two
        # models sharing one (NPF and NPF CLS 95/5) warm the same entries.
        for record in df.to_dict("records"):
            for basis in dict.fromkeys(m.basis for m in models.MODELS):
                _market_indices(record.get("Asset"), basis, newest)
        utils.cot_logger.info(
            f"crowd: warmed window indices for {len(df)} markets ({newest}).")
        tape_context.warm()
        breadth_panel.warm()
    except Exception as e:
        utils.cot_logger.warning(f"crowd: cache warm failed, first render pays: {e}")


def caption(report_date, model, skipped, awaiting=(), stale=()):
    """The line under the board: the FACTS of this render, and nothing a reader
    already taught can skip. What the series is measured as and which week, plus
    what could not be shown; the teaching moved to `help_text` behind the fold
    (see components.help_fold for the split). `awaiting` names the tape-context
    ratios the price store cannot serve yet, which is a delivery fact, not a
    data gap in the positioning. `stale` names the ratios whose last priced week
    trails the board's (a leg that stopped updating), so the reader knows the two
    dates differ before comparing the rows."""
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
    context = ""
    if awaiting:
        context = (f" Tape context awaiting price data for: "
                   f"{', '.join(awaiting)}.")
    if stale:
        context += f" Tape context trailing the board: {'; '.join(stale)}."
    return (
        f"Commercial positioning as of Tuesday {pretty}, measured as {basis} "
        f"({model.title}'s basis). Colour is the cell's own value, not the "
        f"model's verdict.{dropped}{context}"
    )


def help_text(model):
    """The teaching: what a cell means, how the windows line up with the rest of
    the app, and the trailing-window trap. Model-aware (the chip carries the
    current model's verdict), which is why this is rendered per callback rather
    than baked into the layout."""
    return (
        f"Each cell is the range index of that one series within its own window "
        f"(0 at the window's low, 100 at its high) over 13, 26 and 52 weekly "
        f"reports, then the market's full history (each market's history starts "
        f"where its data does; hover the Full cell for the span). The SETUP chip "
        f"at the left edge (and its fainter NEAR tier) is {model.title}'s verdict "
        f"on its own window, and a crowded row with no chip is a market whose "
        f"other legs block the gate. A trailing window renormalises every week, "
        f"so a short column says where this week sits in the RECENT range, not "
        f"whether the market is net long: the 3M column especially moves in "
        f"coarse steps and pins at 0 or 100 often. The {vc.MOMENTUM_LABEL} "
        f"column is the {vc.MOMENTUM_UNIT_PHRASE}, on the 12M window; the path "
        f"is the same 12M index over the trailing year. Click any of a row's "
        f"marks to open that market's detail page. The {board_traces.CONTEXT_CLASS} "
        f"block at the bottom is not positioning: four ETF ratios at the Tuesday "
        f"close, scored on the same windows, each written with the defensive leg "
        f"on top so a high cell is the fearful or broad side and a low cell the "
        f"crowded, complacent side, the same way round as the markets above. "
        f"Equal-over-cap-weight is a weekly breadth proxy on the board's own "
        f"frame; the exact daily breadth reads (FOMO, net new highs) are the "
        f"panel below the board, on their own zones, because a weekly sample "
        f"misses most of their visits. Context, not a signal, and not a composite."
    )


def layout(**kwargs):
    # Built per request, not at import, so importing this page needs no store.
    return html.Div([
        dbc.Container([
            dbc.Row([
                dbc.Col([
                    dbc.Card(
                        dbc.CardBody([
                            config_fold.wrap('crowd', dbc.Row([
                                dbc.Col([
                                    controls.label("Target Date"),
                                    controls.target_date_dropdown(
                                        'crowd_date_selector'),
                                ], xs=12, md=3, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    controls.label("Model"),
                                    # persistence=None: the value rides the global
                                    # store, as it did before the shared kit.
                                    controls.model_select(
                                        'crowd_model_selector', size="sm",
                                        persistence=None),
                                ], xs=6, md=2, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Order",
                                               style={**vc.label_style,
                                                      "fontSize": "0.8rem",
                                                      "textTransform": "uppercase"}),
                                    dbc.RadioItems(
                                        persistence='session',
                                        id='crowd_order_selector',
                                        options=[{"label": text, "value": value}
                                                 for value, text in ORDER_LABELS.items()],
                                        value=board_traces.ORDER_CLASS,
                                        inline=True,
                                        style={"color": vc.BRIGHTER_TEXT_COLOR,
                                               "fontSize": "0.85rem"},
                                    ),
                                ], xs=12, md=4, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Asset Classes",
                                               style={**vc.label_style,
                                                      "fontSize": "0.8rem",
                                                      "textTransform": "uppercase"}),
                                    class_filter.control(
                                        'crowd_class_selector',
                                        get_indexer().get_asset_classes()),
                                ], xs=12, md=3, className="px-md-2"),
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

            # Everything the PNG export captures lives inside this div, buttons
            # included: exportBoardImage strips them from its clone, the
            # Divergence container's rule.
            html.Div(id='crowd_export_container', children=[
                dbc.Row([
                    dbc.Col([
                        html.P(id='crowd_caption',
                               style={'color': vc.TEXT_COLOR, 'fontSize': '0.85rem',
                                      'fontStyle': 'italic', 'marginBottom': '4px'}),
                        help_fold.wrap('crowd', html.P(
                            id='crowd_help',
                            style={'color': vc.TEXT_COLOR, 'fontSize': '0.85rem',
                                   'fontStyle': 'italic', 'marginBottom': '4px'})),
                    ], xs=True),
                    dbc.Col([
                        dbc.Button("📸 Export PNG",
                                   id="crowd_download_img_btn",
                                   style={"color": vc.TEXT_COLOR},
                                   size="sm"),
                        dbc.Tooltip(
                            "The whole board as one image, with the caption and "
                            "the how-to-read text.",
                            target="crowd_download_img_btn",
                            placement="bottom"),
                    ], xs="auto"),
                ]),

                dbc.Row([
                    dbc.Col(
                        dcc.Loading(
                            id="loading-crowd",
                            type="dot",
                            children=html.Div(id='crowd_display_container'),
                            color=vc.BRIGHTER_TEXT_COLOR,
                        ),
                        width=12),
                ]),
            ]),

            # The breadth panel: FOMO and net new highs, DAILY, against their
            # published zones. Outside the export container on purpose: the PNG is
            # the board, and this is a different cadence with its own caption.
            # components.breadth_panel says why it is not a fifth context row.
            dbc.Row([
                dbc.Col([
                    html.P(id='crowd_breadth_caption',
                           style={'color': vc.TEXT_COLOR, 'fontSize': '0.85rem',
                                  'fontStyle': 'italic', 'marginBottom': '4px'}),
                    help_fold.wrap('crowd_breadth', html.P(
                        id='crowd_breadth_help',
                        style={'color': vc.TEXT_COLOR, 'fontSize': '0.85rem',
                               'fontStyle': 'italic', 'marginBottom': '4px'})),
                ], xs=12, md=True),
                # The universe toggle sits beside the caption on a desktop and
                # under it on a phone, where a side column squeezed the caption
                # into a strip of one word per line.
                dbc.Col([
                    dbc.RadioItems(
                        persistence='session',
                        id='crowd_fomo_universe',
                        options=[{"label": name, "value": key}
                                 for key, (_sym, name) in breadth_panel.UNIVERSES.items()],
                        value=breadth_panel.DEFAULT_UNIVERSE,
                        inline=True,
                        style={"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "0.8rem"},
                    ),
                ], xs=12, md="auto", className="mb-2 mb-md-0"),
            ], className="mt-4", align="center"),
            dbc.Row([
                dbc.Col(html.Div(id='crowd_breadth_container'), width=12),
            ]),
        ], fluid=True),
    ])


@callback(
    Output('crowd_breadth_container', 'children'),
    Output('crowd_breadth_caption', 'children'),
    Output('crowd_breadth_help', 'children'),
    [Input('crowd_fomo_universe', 'value'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('crowd_date_selector', 'value')],
)
def render_breadth(universe, palette_name, target_date):
    """The daily panel, on the board's palette. A series the store cannot serve
    draws nothing and says so in the caption, the tape-context rule.

    The board's date selector defaults to the newest COT Tuesday, which for a DAILY
    panel is up to a week stale on the default view. So the panel runs to the last
    session unless the reader has chosen an older week, in which case it ends there
    so the two agree about which week is on screen.
    """
    cut = breadth_panel.cut_date(target_date, _newest_report_date())
    r, awaiting = breadth_panel.read(universe, cut)
    if r is None:
        return (html.Div(), breadth_panel.caption(None, awaiting),
                breadth_panel.help_text())
    colors = grid_colors(viz_config.get_palette(palette_name))
    fig = breadth_panel.build_figure(r, colors)
    return (
        dcc.Graph(id='crowd_breadth_graph', figure=fig,
                  config={"displayModeBar": False, "responsive": True},
                  style={"width": "100%", "maxWidth": "1100px", "margin": "0 auto"}),
        breadth_panel.caption(r, report_date=cut),
        breadth_panel.help_text(),
    )


def _newest_report_date():
    try:
        available = get_indexer().get_available_dates()
    except Exception:  # noqa: BLE001 -- the panel must draw even if the indexer cannot
        return None
    return available[0] if available else None


@callback(
    Output('crowd_display_container', 'children'),
    Output('crowd_caption', 'children'),
    Output('crowd_help', 'children'),
    [Input('crowd_class_selector', 'value'),
     Input('global_model_store', 'data'),
     Input('crowd_order_selector', 'value'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('crowd_date_selector', 'value')],
)
def render_board(asset_classes, model_key, order, palette_name, target_date):
    empty = html.P("Select an asset class to draw the board.",
                   style={'textAlign': 'center', 'color': vc.TEXT_COLOR})
    # Resolved before the early exits so the fold teaches even over an empty
    # board; the teaching does not depend on the data being present.
    model = models.resolve(model_key)
    if not asset_classes:
        return empty, "", help_text(model)

    order = order if order in ORDER_LABELS else board_traces.ORDER_CLASS

    # The matrix drives the universe and carries the verdict; the Custom lookback is
    # the models' own window, the same one every other verdict surface gates on.
    df = get_matrix_data(asset_classes, "Custom", target_date)
    if df.empty:
        return (html.P("No data available.",
                       style={'textAlign': 'center', 'color': vc.TEXT_COLOR}),
                "", help_text(model))

    available = get_indexer().get_available_dates()
    newest = available[0] if available else None

    reads, unreadable = [], []
    for record in df.to_dict("records"):
        asset = record.get("Asset")
        read = _read_for(asset, record, model.basis, model, newest, target_date)
        if read is None:
            unreadable.append(asset)
        else:
            reads.append(read)

    rows, skipped = board_traces.build_rows(reads, order=order)
    # The tape beside the positioning, under the markets whatever the order. A
    # ratio the price store cannot serve yet is named in the caption, not drawn.
    context_reads, awaiting = tape_context.context_reads(target_date)
    context_rows, context_skipped = board_traces.build_context_rows(context_reads)
    rows += context_rows
    awaiting = sorted(set(awaiting) | set(context_skipped))
    palette = viz_config.get_palette(palette_name)
    colors = grid_colors(palette)
    fig = board_traces.build_figure(rows, model, colors)

    report_date = target_date or (reads[0].date if reads else None)
    stale = tape_context.stale_notes(context_reads, report_date)
    return (
        dcc.Graph(id='crowd_board_graph', figure=fig,
                  config={"displayModeBar": False, "responsive": True},
                  style={"width": "100%", "maxWidth": "1100px",
                         "margin": "0 auto"}),
        caption(report_date, model, sorted(set(unreadable) | set(skipped)),
                awaiting=awaiting, stale=stale),
        help_text(model),
    )


@callback(
    Output('url', 'href', allow_duplicate=True),
    Input('crowd_board_graph', 'clickData'),
    prevent_initial_call=True,
)
def open_market(click):
    """A click on any of a row's marks opens the market's detail page.

    The destination rides on the point (`customdata`, set by board_traces), so
    this never re-derives row order from a figure the server no longer holds.
    Location has refresh=False, so the write is a client-side pushState: the
    same navigation the navbar makes, back button included.
    """
    href = app_utils.clicked_market_href(click)
    return href or no_update
