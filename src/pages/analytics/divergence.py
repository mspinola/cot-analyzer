"""The Divergence page: where the three models disagree, and by how much.

`components.divergence_rows` owns the definitions (what counts as a split, what
counts as "the same value", why the two normalized models can only split on verdict);
this module is the controls, the table rendering and the caption. It computes
nothing: every number and every verdict on the page is already on the Signal Matrix
frame, resolved once in `get_matrix_data`, which is what guarantees this page can
never disagree with the Heatmap, the Strip or the Home board about what a model said.

The default view shows only the rows where something differs, because that is the
page's whole question; the caption counts what was hidden so a short list cannot be
read as a short book.
"""

import functools
import urllib.parse
from datetime import datetime

import cotmetrics.constants as const
import cotmetrics.models as models
import cotmetrics.utils as utils
import dash
import dash_bootstrap_components as dbc
from cotmetrics.indexer import get_indexer
from cotmetrics.reports import get_matrix_data
from dash import Input, Output, State, callback, clientside_callback, dcc, html

import viz_config
import viz_constants as vc
from components import class_filter, config_fold, controls, divergence_rows, help_fold
from components.signal_cards import tier_of

dash.register_page(
    __name__, path='/divergence',
    title='COT Model Divergence | COT Analyzer',
    description='Where raw and OI-normalized COT models disagree, market by '
                'market: verdict splits, value gaps and a year of basis '
                'divergence per futures market.',
)

# Layout runs per request; the wiring must not.
class_filter.register('divergence_class_selector')
controls.register_target_date('divergence_date_selector')

# The PNG export, clientside for the Strip's reason: everything in the picture is
# already in the browser. The date rides along only to name the file; the caption
# inside the image carries it in prose.
clientside_callback(
    "window.dash_clientside.clientside.export_divergence_image",
    Output('divergence_download_img_btn', 'n_clicks'),
    Input('divergence_download_img_btn', 'n_clicks'),
    State('divergence_date_selector', 'value'),
    prevent_initial_call=True,
)

SHOW_DIFFERENCES = "differences"
SHOW_ALL = "all"
SHOW_LABELS = {SHOW_DIFFERENCES: "Differences only", SHOW_ALL: "All markets"}

# The column selectors. Each of the three columns picks any model or nothing, so the
# page can be the full three-way comparison (the default), any pair, or one model
# alone (where no split is possible and only the basis gap differentiates). "None" is
# a real option rather than an absent model key so a stored selection and a stale one
# stay distinguishable: an unknown key falls back to that column's default, "none" is
# a choice and is honoured.
COLUMN_NONE = "none"
COLUMN_IDS = ('divergence_col1_selector', 'divergence_col2_selector',
              'divergence_col3_selector')
# The default view is the two CLS 95/5 models: the SAME gate and band on the two
# bases, so every default-view disagreement is the normalization and nothing
# else, and the C emphasis below coincides exactly with the Basis gap column.
# The three-way comparison (adding NPF CS 80/20, where a split can also come
# from the band or the dropped Large Spec leg) is one selection away, not gone.
COLUMN_DEFAULTS = (models.RAW_PF.key, models.NPF_CLS_95_5.key, COLUMN_NONE)
_MODELS_BY_KEY = {m.key: m for m in divergence_rows.MODEL_ORDER}


def compared_models(*keys):
    """The models the three selectors resolve to, in column order.

    A stale key (a model renamed or removed while a browser session held it) falls
    back to that column's default rather than vanishing, because a silently missing
    column looks exactly like a deliberate None. Duplicates are allowed: two columns
    showing one model draw the same thing twice, which is harmless and self-evident.
    A column whose own default is None resolves a stale key to None too, for the
    same reason the fallback exists at all: it restores the column's shipped state.
    """
    out = []
    for key, default in zip(keys, COLUMN_DEFAULTS):
        if key == COLUMN_NONE:
            continue
        if key not in _MODELS_BY_KEY:
            key = default
            if key == COLUMN_NONE:
                continue
        out.append(_MODELS_BY_KEY[key])
    return out

@functools.lru_cache(maxsize=256)
def _gap_history(asset, newest_date):
    """One market's weekly basis gap (|raw - normalized| Commercial index), full
    history, oldest first.

    `newest_date` is a cache-buster and nothing else, the heatmap joins' rule: a
    Friday release must invalidate this and nothing else does. Both series come
    from get_symbols_data on the Custom lookback, the exact quantity the Basis
    gap column snapshots, so the sparkline and the number can never disagree
    about what the gap is. Returns ((date_str, gap), ...) or None when either
    basis is missing; the catch is broad on purpose, this is a display join.
    """
    try:
        raw = get_indexer().get_symbols_data(asset, "Custom", const.BASIS_RAW)
        norm = get_indexer().get_symbols_data(asset, "Custom",
                                              const.BASIS_OI_NORM)
        gaps = (raw[const.COMMS_IDX] - norm[const.COMMS_IDX]).abs().dropna()
    except Exception:
        return None
    if gaps.empty:
        return None
    return tuple((ts.strftime('%Y-%m-%d'), float(v)) for ts, v in gaps.items())


def spark_values(asset, target_date, newest_date, weeks=52):
    """The trailing year of gaps ending at the selected week, for one row."""
    history = _gap_history(asset, newest_date)
    if not history:
        return None
    values = [v for d, v in history if not target_date or d <= target_date]
    return values[-weeks:] or None


# The sparkline geometry. Height matches the row's text; the ceiling scales per
# row to the larger of twice the threshold and the row's own maximum, so the
# threshold rule is never squeezed above half-height and a quiet market's noise
# is not inflated to look like history.
SPARK_W, SPARK_H, SPARK_PAD = 110, 20, 2


def gap_spark(values, tolerance=divergence_rows.GAP_TOLERANCE):
    """A row's basis gap over the trailing year, as a data-URI SVG for the table.

    Server-built rather than a dcc.Graph per row: forty Plotly instances is a
    page of iframes' worth of runtime for forty 1KB pictures. The faint dashed
    rule is the SAME tolerance the dimming and the leg emphasis use, so "above
    the line" means exactly "wide enough to keep the row"; the endpoint dot
    brightens when this week's gap clears it.
    """
    if not values:
        return None
    ceiling = max(2 * tolerance, max(values)) or 1
    span = SPARK_H - 2 * SPARK_PAD

    def y(v):
        return SPARK_H - SPARK_PAD - min(v, ceiling) / ceiling * span

    step = (SPARK_W - 2 * SPARK_PAD) / max(len(values) - 1, 1)
    points = " ".join(f"{SPARK_PAD + i * step:.1f},{y(v):.1f}"
                      for i, v in enumerate(values))
    threshold_y = y(tolerance)
    end_x = SPARK_PAD + (len(values) - 1) * step
    hot = values[-1] >= tolerance
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' "
        f"width='{SPARK_W}' height='{SPARK_H}'>"
        f"<line x1='{SPARK_PAD}' y1='{threshold_y:.1f}' "
        f"x2='{SPARK_W - SPARK_PAD}' y2='{threshold_y:.1f}' "
        f"stroke='{_DIM}' stroke-opacity='0.35' stroke-dasharray='2,3'/>"
        f"<polyline points='{points}' fill='none' stroke='{_DIM}' "
        f"stroke-opacity='0.8' stroke-width='1'/>"
        f"<circle cx='{end_x:.1f}' cy='{y(values[-1]):.1f}' r='2' "
        f"fill='{_BRIGHT if hot else _DIM}'/>"
        f"</svg>")
    return "data:image/svg+xml;utf8," + urllib.parse.quote(svg)


def warm_caches():
    """Fill the sparkline's per-market history cache; the page warmers' rule.

    Two get_symbols_data frames per market, which nothing else on this page
    reads until a row draws its path. Keyed on the newest date exactly as the
    render path is, invalidated by a release by construction, failures logged
    and swallowed.
    """
    try:
        indexer = get_indexer()
        available = indexer.get_available_dates()
        if not available:
            return
        newest = available[0]
        df = get_matrix_data(indexer.get_asset_classes(), "Custom", None)
        for record in df.to_dict("records"):
            _gap_history(record.get("Asset"), newest)
        utils.cot_logger.info(
            f"divergence: warmed gap histories for {len(df)} markets ({newest}).")
    except Exception as e:
        utils.cot_logger.warning(
            f"divergence: cache warm failed, first render pays: {e}")


# Cell text tiers. The page dims whole rows, so these are deliberately the same two
# colours every other surface uses for "speaks" and "background".
_BRIGHT = vc.BRIGHTER_TEXT_COLOR
_DIM = vc.TEXT_COLOR

_CELL = {"padding": "5px 10px", "fontVariantNumeric": "tabular-nums",
         "whiteSpace": "nowrap"}
_ROW_BORDER = "1px solid rgba(255,255,255,0.07)"


def _chip(state, palette):
    """A model's verdict as the app's badge vocabulary: SETUP, a fainter NEAR, or a
    dash. The dash is drawn rather than omitted so a cell with no verdict still says
    it was asked, which on this page is half the point."""
    text, colour = tier_of(state, palette)
    if not text:
        return html.Span("—", style={"opacity": 0.35, "marginLeft": "6px"})
    near = state in const.SETUP_NEAR_STATES
    style = {
        "color": colour, "border": f"1px solid {colour}66",
        "borderRadius": "3px", "padding": "0 4px", "fontSize": "0.6rem",
        "fontWeight": "bold", "marginLeft": "6px",
        "opacity": 0.7 if near else 1.0,
    }
    if not near:
        style["backgroundColor"] = f"{colour}1a"
    return html.Span(text, style=style)


def _triplet(read, is_equity, bright, hot):
    """C / L / S on the model's own basis, with a dash for a leg its gate does not
    read. Equities print the Commercial leg alone, because that is all any gate
    consults for them.

    Every leg carries its own two-state emphasis, decided per ROW per LEG
    (`leg_spread` against GAP_TOLERANCE) and applied to every column's value so
    the disagreeing PAIR lights up, not one arbitrary side of it: heavy and
    bright where the shown columns actually read that leg differently, dim where
    they print the same number twice. Under the default view (the two CLS
    models) every leg is the same gate on two bases, which is what made this
    worth extending beyond the Commercial leg it started on; a leg fewer than
    two shown columns carry never lights, `leg_spread`'s doing, so the mixed
    three-column view cannot light a value against a dash. Achromatic on
    purpose: colour on this page belongs to the verdict chips, and a coloured
    pair would read as a directional claim the numbers do not make.
    """
    def piece(value, leg):
        text = "–" if value is None else f"{value:.0f}"
        if hot.get(leg) and bright and value is not None:
            return html.Span(text, style={"color": _BRIGHT, "fontWeight": "600"})
        # Opacity, not just the dim colour: _BRIGHT and _DIM are two nearly
        # identical creams under the shipped palettes, so a "dim" leg rendered
        # in _DIM read as bright and the emphasis looked like nothing had
        # happened (reported from the live board). Receding is the point, so
        # recede visibly.
        return html.Span(text, style={"color": _DIM, "opacity": 0.45})
    sep = html.Span(" / ", style={"color": _DIM, "opacity": 0.45})
    if is_equity:
        return piece(read.comm, "comm")
    return html.Span([piece(read.comm, "comm"), sep,
                      piece(read.lrg, "lrg"), sep,
                      piece(read.sml, "sml")])


def _market_tr(row, palette, spark=None):
    bright = not row.dim
    hot = {}
    for leg in ("comm", "lrg", "sml"):
        spread = divergence_rows.leg_spread(row.reads, leg)
        hot[leg] = spread is not None and spread >= divergence_rows.GAP_TOLERANCE
    name = html.A(row.label,
                  href=f"/oi_alignment?asset={urllib.parse.quote(row.label)}",
                  target="_blank",
                  style={"color": _BRIGHT if bright else _DIM,
                         "textDecoration": "none",
                         "fontWeight": "600" if row.split else "normal"})
    cells = [html.Td(name, style={**_CELL})]
    for read in row.reads:
        cells.append(html.Td([_triplet(read, row.is_equity, bright, hot),
                              _chip(read.state, palette)],
                             style={**_CELL}))
    # The path first, then the number it ends at. The image dims with the row.
    cells.append(html.Td(
        html.Img(src=spark, style={"display": "block", "marginLeft": "auto"})
        if spark else html.Span("–", style={"color": _DIM, "opacity": 0.45}),
        style={**_CELL, "textAlign": "right"}))
    # The gap brightens with the disagreement it measures, so the column can be
    # scanned like the connectors on the Strip's other-basis view.
    gap_bright = bright and row.gap is not None and \
        row.gap >= divergence_rows.GAP_TOLERANCE
    cells.append(html.Td("–" if row.gap is None else f"{row.gap:.0f}",
                         style={**_CELL, "textAlign": "right",
                                "color": _BRIGHT if gap_bright else _DIM}))
    return html.Tr(cells, style={"borderTop": _ROW_BORDER,
                                 "opacity": 0.55 if row.dim else 1.0})


def _class_tr(row, span):
    return html.Tr(
        html.Td(row.label.upper(), colSpan=span,
                style={"padding": "10px 10px 3px", "fontSize": "0.68rem",
                       "letterSpacing": "0.05em", "color": _DIM}),
    )


def build_table(rows, palette, compare, sparks):
    """The board, as one plain table. No grid library: a name column, one column per
    selected model, the gap's trailing-year path, and the gap, with no sorting UI
    (the rows arrive sorted by disagreement). Every cell is text plus a badge or
    picture the app already knows how to draw; `sparks` maps a market to its
    pre-built path image."""
    span = len(compare) + 3
    header = html.Tr(
        [html.Th("Market", style={**_CELL, "textAlign": "left"})]
        + [html.Th(vc.MODEL_LABELS[m.key], style={**_CELL, "textAlign": "left"})
           for m in compare]
        + [html.Th("52w gap", id='divergence_spark_header',
                   style={**_CELL, "textAlign": "right"}),
           html.Th("Basis gap", id='divergence_gap_header',
                   style={**_CELL, "textAlign": "right"})],
        style={"fontSize": "0.68rem", "color": _DIM,
               "borderBottom": "1px solid rgba(255,255,255,0.15)"})
    body = [(_class_tr(r, span) if r.kind == "class"
             else _market_tr(r, palette, sparks.get(r.label)))
            for r in rows]
    # A short hover answer per gap column; the full teaching stays behind the
    # fold. Rendered beside the table because the table is rebuilt per callback
    # and a tooltip must be born with its target.
    tol = divergence_rows.GAP_TOLERANCE
    tooltips = [
        dbc.Tooltip(
            f"The basis gap over the trailing year to the selected week. The "
            f"dashed rule is the {tol}-point threshold the page keys on; the "
            f"endpoint dot brightens when this week clears it.",
            target='divergence_spark_header', placement="top"),
        dbc.Tooltip(
            f"This week's |raw − OI-normalized| Commercial index: the "
            f"contract-size drift the normalization removes. Bright at "
            f"{tol}+ points on a row that is not dimmed.",
            target='divergence_gap_header', placement="top"),
    ]
    # The scroll box is what keeps the table honest on a phone: every cell is
    # nowrap, so at 375px the rightmost columns ran past the viewport and the
    # page-level overflow-x: hidden clipped them with no scrollbar, which read
    # as the Basis gap column not existing. Scrolling inside this div works
    # because the clip is on the body, not on ancestors of the table.
    return html.Div(
        [html.Table([html.Thead(header), html.Tbody(body)],
                    style={"width": "100%", "maxWidth": "1100px",
                           "margin": "0 auto", "borderCollapse": "collapse",
                           "fontSize": "0.8rem"})] + tooltips,
        style={"overflowX": "auto"})


def caption(report_date, show, hidden, unplaced, compare):
    """The FACTS of this render: which week, what was hidden and why, what could
    not be compared, and the one-column caveat that changes what a reader should
    expect to see. The teaching moved to `help_text` behind the fold (see
    components.help_fold for the split)."""
    try:
        pretty = datetime.strptime(report_date, '%Y-%m-%d').strftime('%B %d, %Y')
    except (TypeError, ValueError):
        pretty = "an unknown date"
    agree_under = ("all three models" if len(compare) == len(divergence_rows.MODEL_ORDER)
                   else "the selected models" if len(compare) > 1
                   else "the one selected model")
    if show == SHOW_ALL:
        visibility = (" Agreeing markets are dimmed rather than hidden; a dimmed row "
                      "is one where every shown verdict matches and every leg the "
                      "shown columns share reads within a few points.")
    else:
        visibility = (f" {hidden} market(s) agree under {agree_under} and are "
                      f"hidden; switch to All markets to see them dimmed in place."
                      if hidden else "")
    dropped = ""
    if unplaced:
        dropped = (f" {len(unplaced)} market(s) have no reading on one of the bases "
                   f"this week and cannot be compared: {', '.join(sorted(unplaced))}.")
    # Splits are a property of the columns on screen, so a one-column view says so
    # rather than leaving a reader to wonder why nothing ever splits.
    solo = (" With a single model column, no verdict split is possible and only the "
            "basis gap differentiates rows." if len(compare) == 1 else "")
    return (f"Each shown model's verdict as of Tuesday {pretty}."
            f"{solo}{visibility}{dropped}")


def help_text(compare):
    """The teaching: what a column and its cells are, the C emphasis rule, the
    Basis gap, and the sort. Column-aware only for the shared-series note, which
    is why this renders per callback rather than being baked into the layout."""
    both_npf = ""
    if models.NPF in compare and models.NPF_CLS_95_5 in compare:
        both_npf = (f" {models.NPF.title} and {models.NPF_CLS_95_5.title} share one "
                    f"OI-normalized series by construction, so they can only differ "
                    f"in verdict, never in value.")
    return (
        f"Each column is one model's Commercials / Large Specs / Small Traders on "
        f"its own basis, with its verdict. A dash is a leg that model's gate does "
        f"not read. A leg's values print heavy only where the shown columns "
        f"disagree on that leg by {divergence_rows.GAP_TOLERANCE} index points "
        f"or more; a dim value is the same reading twice, and a leg only one "
        f"column carries never lights.{both_npf} The Basis gap column "
        f"is |raw − normalized| on the Commercial index, which is the "
        f"contract-size drift the normalization removes and the same gap the "
        f"Strip's Other basis view draws as a connector; it does not depend on "
        f"which columns are shown. The 52w gap column draws that same gap over "
        f"the trailing year to the selected week, the faint rule at the "
        f"{divergence_rows.GAP_TOLERANCE}-point threshold, so a row says whether "
        f"the bases have disagreed for months or just this week. Rows sort by disagreement inside each class: "
        f"verdict splits first, then the widest gaps.")


def _column_select(column_id, default):
    """One column's model picker. dbc.Select rather than a radio because three radio
    groups of four options each would dwarf the board they configure."""
    return dbc.Select(
        id=column_id,
        options=[{"label": vc.MODEL_LABELS[m.key], "value": m.key}
                 for m in divergence_rows.MODEL_ORDER]
                + [{"label": "None", "value": COLUMN_NONE}],
        value=default,
        persistence='session',
        size="sm",
        className="bg-dark text-white border-secondary",
        # Flex sizing, because the wrapping container below cannot do it alone:
        # .form-select is width: 100%, so once the row was allowed to wrap (the
        # phone fix) each select claimed a full line on DESKTOP too. A basis of
        # 110px with grow shares one row where three fit and wraps where they
        # do not, which is both layouts from one rule.
        style={"flex": "1 1 110px", "minWidth": "110px", "width": "auto"},
    )


def layout(**kwargs):
    return html.Div([
        dbc.Container([
            dbc.Row([
                dbc.Col([
                    dbc.Card(
                        dbc.CardBody([
                            config_fold.wrap('divergence', dbc.Row([
                                dbc.Col([
                                    controls.label("Target Date"),
                                    controls.target_date_dropdown(
                                        'divergence_date_selector'),
                                ], xs=12, md=3, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Columns",
                                               style={**vc.label_style,
                                                      "fontSize": "0.8rem",
                                                      "textTransform": "uppercase"}),
                                    html.Div(
                                        [_column_select(cid, default)
                                         for cid, default in zip(COLUMN_IDS,
                                                                 COLUMN_DEFAULTS)],
                                        # Wraps rather than crushes: three selects
                                        # side by side do not fit a phone, and the
                                        # page-level overflow-x: hidden would clip
                                        # the third one silently.
                                        style={"display": "flex", "gap": "6px",
                                               "flexWrap": "wrap"},
                                    ),
                                ], xs=12, md=4, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Show",
                                               style={**vc.label_style,
                                                      "fontSize": "0.8rem",
                                                      "textTransform": "uppercase"}),
                                    dbc.RadioItems(
                                        persistence='session',
                                        id='divergence_show_selector',
                                        options=[{"label": text, "value": value}
                                                 for value, text in SHOW_LABELS.items()],
                                        value=SHOW_DIFFERENCES,
                                        inline=True,
                                        style={"color": vc.BRIGHTER_TEXT_COLOR,
                                               "fontSize": "0.85rem"},
                                    ),
                                ], xs=12, md=2, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Asset Classes",
                                               style={**vc.label_style,
                                                      "fontSize": "0.8rem",
                                                      "textTransform": "uppercase"}),
                                    class_filter.control(
                                        'divergence_class_selector',
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

            # Everything the PNG export captures lives inside this div; unlike the
            # Strip's container it also holds the buttons (the export's own and the
            # help fold's toggle), because export_divergence_image strips buttons
            # from its clone rather than requiring them to live elsewhere.
            html.Div(id='divergence_export_container', children=[
                dbc.Row([
                    dbc.Col([
                        html.P(id='divergence_caption',
                               style={'color': vc.TEXT_COLOR, 'fontSize': '0.85rem',
                                      'fontStyle': 'italic', 'marginBottom': '4px'}),
                        help_fold.wrap('divergence', html.P(
                            id='divergence_help',
                            style={'color': vc.TEXT_COLOR, 'fontSize': '0.85rem',
                                   'fontStyle': 'italic', 'marginBottom': '4px'})),
                    ], xs=True),
                    dbc.Col([
                        dbc.Button("📸 Export PNG",
                                   id="divergence_download_img_btn",
                                   style={"color": vc.TEXT_COLOR},
                                   size="sm"),
                        dbc.Tooltip(
                            "The whole board as one image, every row and column, "
                            "with the caption and the how-to-read text.",
                            target="divergence_download_img_btn",
                            placement="bottom"),
                    ], xs="auto"),
                ]),

                dbc.Row([
                    dbc.Col(
                        dcc.Loading(
                            id="loading-divergence",
                            type="dot",
                            children=html.Div(id='divergence_display_container'),
                            color=vc.BRIGHTER_TEXT_COLOR,
                        ),
                        width=12),
                ]),
            ]),
        ], fluid=True),
    ])


@callback(
    Output('divergence_display_container', 'children'),
    Output('divergence_caption', 'children'),
    Output('divergence_help', 'children'),
    [Input('divergence_class_selector', 'value'),
     Input('divergence_show_selector', 'value'),
     Input(COLUMN_IDS[0], 'value'),
     Input(COLUMN_IDS[1], 'value'),
     Input(COLUMN_IDS[2], 'value'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('divergence_date_selector', 'value')],
)
def render_board(asset_classes, show, col1, col2, col3, palette_name, target_date):
    empty = html.P("Select an asset class to draw the board.",
                   style={'textAlign': 'center', 'color': vc.TEXT_COLOR})
    # Resolved before the early exits so the fold teaches even over an empty
    # board; the teaching does not depend on the data being present.
    compare = compared_models(col1, col2, col3)
    if not asset_classes:
        return empty, "", help_text(compare)

    if not compare:
        return (html.P("Every column is set to None. Pick at least one model.",
                       style={'textAlign': 'center', 'color': vc.TEXT_COLOR,
                              'padding': '2rem 0'}),
                "", help_text(compare))

    show = show if show in SHOW_LABELS else SHOW_DIFFERENCES
    # The models' own window, the same Custom lookback every verdict surface gates on.
    df = get_matrix_data(asset_classes, "Custom", target_date)
    if df.empty:
        return (html.P("No data available.",
                       style={'textAlign': 'center', 'color': vc.TEXT_COLOR}),
                "", help_text(compare))

    rows, hidden, unplaced = divergence_rows.build_rows(
        df, show_all=(show == SHOW_ALL), compare=compare)
    palette = viz_config.get_palette(palette_name)
    report_date = target_date or (df.iloc[0]["Date"] if not df.empty else None)

    if not rows:
        board = html.P(
            "No disagreements this week: every drawn market reads the same under "
            "the selected models.",
            style={'textAlign': 'center', 'color': vc.TEXT_COLOR,
                   'padding': '2rem 0'})
    else:
        # Sparks only for the rows actually drawn: the histories are cached per
        # market (and boot-warmed), so this loop is a dictionary walk after the
        # first render.
        available = get_indexer().get_available_dates()
        newest = available[0] if available else None
        sparks = {r.label: gap_spark(spark_values(r.label, target_date, newest))
                  for r in rows if r.kind == "market"}
        board = build_table(rows, palette, compare, sparks)
    return (board, caption(report_date, show, hidden, unplaced, compare),
            help_text(compare))
