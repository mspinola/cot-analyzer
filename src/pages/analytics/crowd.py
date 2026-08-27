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
from cotmetrics import indicators
from cotmetrics.indexer import get_indexer
from cotmetrics.reports import get_matrix_data
from dash import Input, Output, State, callback, dcc, html, no_update

import app_utils
import components.board_traces as board_traces
import viz_config
import viz_constants as vc
from components import class_filter
from components.plot_colors import grid_colors
from components.strip_traces import SETUP_COLUMN

dash.register_page(__name__, path='/crowd')

# Layout runs per request; the wiring must not.
class_filter.register('crowd_class_selector')

ORDER_LABELS = {
    board_traces.ORDER_CLASS: "By class",
    board_traces.ORDER_FLAT: "Most crowded",
    board_traces.ORDER_ALPHA: "A-Z",
}

# See the module docstring: mirrors exposure.windowed_pct_rank's min_periods.
FULL_HISTORY_MIN_WEEKS = 104


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

    out = pd.DataFrame(index=net.index)
    for weeks, label in zip(board_traces.WINDOW_WEEKS, board_traces.WINDOW_LABELS):
        if weeks is None:
            window = len(net)
            min_periods = min(FULL_HISTORY_MIN_WEEKS, int(net.notna().sum()))
        else:
            window = weeks + 1
            min_periods = window
        out[label] = indicators.calculate_range_index(
            net, window=window, min_periods=min_periods)
    year_label = board_traces.WINDOW_LABELS[2]
    out["move"] = out[year_label] - out[year_label].shift(const.MOMENTUM_PERIOD)
    out.attrs["history_weeks"] = int(net.notna().sum())
    first = net.first_valid_index()
    out.attrs["start"] = first.strftime('%Y-%m-%d') if first is not None else None
    return out


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


def caption(report_date, model, skipped):
    """The paragraph under the board. Every sentence is a fact the picture cannot
    carry: what the series is, what a cell means, how the windows line up with the
    rest of the app, and the trailing-window trap."""
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
        f"Commercial positioning as of Tuesday {pretty}, measured as {basis} "
        f"({model.title}'s basis). Each cell is the range index of that one series "
        f"within its own window (0 at the window's low, 100 at its high) over 13, "
        f"26 and 52 weekly reports, then the market's full history (each market's "
        f"history starts where its data does; hover the Full cell for the span). "
        f"Colour is the cell's own value, not the model's verdict; the SETUP chip "
        f"at the left edge (and its fainter NEAR tier) is {model.title}'s verdict "
        f"on its own window, and a crowded row with no chip is a market whose other "
        f"legs block the gate. A trailing window renormalises every week, so a short "
        f"column says where this week sits in the RECENT range, not whether the "
        f"market is net long: the 3M column especially moves in coarse steps and "
        f"pins at 0 or 100 often. The {vc.MOMENTUM_LABEL} column is the "
        f"{vc.MOMENTUM_UNIT_PHRASE}, on the 12M window; the path is the same "
        f"12M index over the trailing year.{dropped}"
    )


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
                                    html.Label("Target Date",
                                               style={**vc.label_style,
                                                      "fontSize": "0.8rem",
                                                      "textTransform": "uppercase"}),
                                    dcc.Dropdown(
                                        id='crowd_date_selector',
                                        options=[{'label': d, 'value': d}
                                                 for d in get_indexer().get_available_dates()],
                                        value=(get_indexer().get_available_dates()[0]
                                               if get_indexer().get_available_dates()
                                               else None),
                                        className="dash-dropdown bg-dark text-white",
                                        searchable=True,
                                        clearable=False,
                                        style={'borderRadius': '8px'},
                                    ),
                                ], xs=12, md=3, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Model",
                                               style={**vc.label_style,
                                                      "fontSize": "0.8rem",
                                                      "textTransform": "uppercase"}),
                                    dbc.Select(
                                        id='crowd_model_selector',
                                        options=[{"label": vc.MODEL_LABELS[k],
                                                  "value": k,
                                                  "title": vc.MODEL_TOOLTIPS[k]}
                                                 for k in vc.MODEL_CHOICES],
                                        value=models.DEFAULT_MODEL.key,
                                        size="sm",
                                        className="bg-dark text-white border-secondary",
                                    ),
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
                            ], align="center"),
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
                    html.P(id='crowd_caption',
                           style={'color': vc.TEXT_COLOR, 'fontSize': '0.85rem',
                                  'fontStyle': 'italic', 'marginBottom': '4px'}),
                ], width=12),
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
        ], fluid=True),
    ])


@callback(
    Output('crowd_date_selector', 'options'),
    Output('crowd_date_selector', 'value'),
    Input('cot_release_store', 'data'),
    State('crowd_date_selector', 'options'),
    State('crowd_date_selector', 'value'),
)
def follow_the_store(_release, current_options, current_value):
    """Re-offer the available weeks when the server takes a new one, the Heatmap's
    arithmetic: a tab on the newest week follows the release, one parked on an older
    week stays where it is."""
    return app_utils.next_date_selection(get_indexer().get_available_dates(),
                                         current_options, current_value)


@callback(
    Output('global_model_store', 'data', allow_duplicate=True),
    Input('crowd_model_selector', 'value'),
    State('global_model_store', 'data'),
    prevent_initial_call=True,
)
def update_global_model(value, current_store_val):
    new_val = value if value in vc.MODEL_CHOICES else models.DEFAULT_MODEL.key
    if new_val == current_store_val:
        return no_update
    return new_val


@callback(
    Output('crowd_model_selector', 'value'),
    Input('global_model_store', 'data'),
    State('crowd_model_selector', 'value'),
)
def follow_global_model(value, current_local_val):
    new_val = value if value in vc.MODEL_CHOICES else models.DEFAULT_MODEL.key
    if new_val == current_local_val:
        return no_update
    return new_val


@callback(
    Output('crowd_display_container', 'children'),
    Output('crowd_caption', 'children'),
    [Input('crowd_class_selector', 'value'),
     Input('global_model_store', 'data'),
     Input('crowd_order_selector', 'value'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('crowd_date_selector', 'value')],
)
def render_board(asset_classes, model_key, order, palette_name, target_date):
    empty = html.P("Select an asset class to draw the board.",
                   style={'textAlign': 'center', 'color': vc.TEXT_COLOR})
    if not asset_classes:
        return empty, ""

    model = models.resolve(model_key)
    order = order if order in ORDER_LABELS else board_traces.ORDER_CLASS

    # The matrix drives the universe and carries the verdict; the Custom lookback is
    # the models' own window, the same one every other verdict surface gates on.
    df = get_matrix_data(asset_classes, "Custom", target_date)
    if df.empty:
        return (html.P("No data available.",
                       style={'textAlign': 'center', 'color': vc.TEXT_COLOR}),
                "")

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
    palette = viz_config.get_palette(palette_name)
    colors = grid_colors(palette)
    fig = board_traces.build_figure(rows, model, colors)

    report_date = target_date or (reads[0].date if reads else None)
    return (
        dcc.Graph(figure=fig,
                  config={"displayModeBar": False, "responsive": True},
                  style={"width": "100%", "maxWidth": "1100px",
                         "margin": "0 auto"}),
        caption(report_date, model, sorted(set(unreadable) | set(skipped))),
    )
