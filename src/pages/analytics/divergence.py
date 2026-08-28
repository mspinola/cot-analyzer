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

import urllib.parse
from datetime import datetime

import cotmetrics.constants as const
import cotmetrics.models as models
import dash
import dash_bootstrap_components as dbc
from cotmetrics.indexer import get_indexer
from cotmetrics.reports import get_matrix_data
from dash import Input, Output, State, callback, dcc, html

import app_utils
import viz_config
import viz_constants as vc
from components import class_filter, divergence_rows
from components.signal_cards import tier_of

dash.register_page(__name__, path='/divergence')

# Layout runs per request; the wiring must not.
class_filter.register('divergence_class_selector')

SHOW_DIFFERENCES = "differences"
SHOW_ALL = "all"
SHOW_LABELS = {SHOW_DIFFERENCES: "Differences only", SHOW_ALL: "All markets"}

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


def _triplet(read, is_equity, bright):
    """C / L / S on the model's own basis, with a dash for a leg its gate does not
    read. Equities print the Commercial leg alone, because that is all any gate
    consults for them."""
    def fmt(v):
        return "–" if v is None else f"{v:.0f}"
    colour = _BRIGHT if bright else _DIM
    if is_equity:
        return html.Span(fmt(read.comm), style={"color": colour})
    return html.Span(f"{fmt(read.comm)} / {fmt(read.lrg)} / {fmt(read.sml)}",
                     style={"color": colour})


def _market_tr(row, palette):
    bright = not row.dim
    name = html.A(row.label,
                  href=f"/oi_alignment?asset={urllib.parse.quote(row.label)}",
                  target="_blank",
                  style={"color": _BRIGHT if bright else _DIM,
                         "textDecoration": "none",
                         "fontWeight": "600" if row.split else "normal"})
    cells = [html.Td(name, style={**_CELL})]
    for read in row.reads:
        cells.append(html.Td([_triplet(read, row.is_equity, bright),
                              _chip(read.state, palette)],
                             style={**_CELL}))
    # The gap brightens with the disagreement it measures, so the column can be
    # scanned like the connectors on the Strip's other-basis view.
    gap_bright = bright and row.gap is not None and \
        row.gap >= divergence_rows.GAP_TOLERANCE
    cells.append(html.Td("–" if row.gap is None else f"{row.gap:.0f}",
                         style={**_CELL, "textAlign": "right",
                                "color": _BRIGHT if gap_bright else _DIM}))
    return html.Tr(cells, style={"borderTop": _ROW_BORDER,
                                 "opacity": 0.55 if row.dim else 1.0})


def _class_tr(row):
    return html.Tr(
        html.Td(row.label.upper(), colSpan=5,
                style={"padding": "10px 10px 3px", "fontSize": "0.68rem",
                       "letterSpacing": "0.05em", "color": _DIM}),
    )


def build_table(rows, palette):
    """The board, as one plain table. No grid library: five columns, no sorting UI
    (the rows arrive sorted by disagreement), and every cell is text plus a badge the
    app already knows how to draw."""
    header = html.Tr(
        [html.Th("Market", style={**_CELL, "textAlign": "left"})]
        + [html.Th(vc.MODEL_LABELS[m.key], style={**_CELL, "textAlign": "left"})
           for m in divergence_rows.MODEL_ORDER]
        + [html.Th("Basis gap", style={**_CELL, "textAlign": "right"})],
        style={"fontSize": "0.68rem", "color": _DIM,
               "borderBottom": "1px solid rgba(255,255,255,0.15)"})
    body = [(_class_tr(r) if r.kind == "class" else _market_tr(r, palette))
            for r in rows]
    return html.Table([html.Thead(header), html.Tbody(body)],
                      style={"width": "100%", "maxWidth": "1100px",
                             "margin": "0 auto", "borderCollapse": "collapse",
                             "fontSize": "0.8rem"})


def caption(report_date, show, hidden, unplaced):
    try:
        pretty = datetime.strptime(report_date, '%Y-%m-%d').strftime('%B %d, %Y')
    except (TypeError, ValueError):
        pretty = "an unknown date"
    if show == SHOW_ALL:
        visibility = (" Agreeing markets are dimmed rather than hidden; a dimmed row "
                      "is one where every verdict matches and the two bases read "
                      "within a few points of each other.")
    else:
        visibility = (f" {hidden} market(s) agree under all three models and are "
                      f"hidden; switch to All markets to see them dimmed in place."
                      if hidden else "")
    dropped = ""
    if unplaced:
        dropped = (f" {len(unplaced)} market(s) have no reading on one of the bases "
                   f"this week and cannot be compared: {', '.join(sorted(unplaced))}.")
    return (
        f"Each model's Commercials / Large Specs / Small Traders on its own basis, "
        f"with its verdict, as of Tuesday {pretty}. A dash is a leg that model's "
        f"gate does not read. {models.NPF.title} and {models.NPF_CLS_95_5.title} "
        f"share one OI-normalized series by construction, so they can only differ "
        f"in verdict, never in value; the Basis gap column is |raw − normalized| on "
        f"the Commercial index, which is the contract-size drift the normalization "
        f"removes and the same gap the Strip's Other basis view draws as a "
        f"connector. Rows sort by disagreement inside each class: verdict splits "
        f"first, then the widest gaps.{visibility}{dropped}")


def layout(**kwargs):
    dates = get_indexer().get_available_dates()
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
                                        id='divergence_date_selector',
                                        options=[{'label': d, 'value': d}
                                                 for d in dates],
                                        value=dates[0] if dates else None,
                                        className="dash-dropdown bg-dark text-white",
                                        searchable=True,
                                        clearable=False,
                                        style={'borderRadius': '8px'},
                                    ),
                                ], xs=12, md=3, className="mb-3 mb-md-0 px-md-2"),

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
                                ], xs=12, md=4, className="mb-3 mb-md-0 px-md-2"),

                                dbc.Col([
                                    html.Label("Asset Classes",
                                               style={**vc.label_style,
                                                      "fontSize": "0.8rem",
                                                      "textTransform": "uppercase"}),
                                    class_filter.control(
                                        'divergence_class_selector',
                                        get_indexer().get_asset_classes()),
                                ], xs=12, md=5, className="px-md-2"),
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
                    html.P(id='divergence_caption',
                           style={'color': vc.TEXT_COLOR, 'fontSize': '0.85rem',
                                  'fontStyle': 'italic', 'marginBottom': '4px'}),
                ], width=12),
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
        ], fluid=True),
    ])


@callback(
    Output('divergence_date_selector', 'options'),
    Output('divergence_date_selector', 'value'),
    Input('cot_release_store', 'data'),
    State('divergence_date_selector', 'options'),
    State('divergence_date_selector', 'value'),
)
def follow_the_store(_release, current_options, current_value):
    """The Heatmap's arithmetic: a tab on the newest week follows a release, one
    parked on an older week stays where it is."""
    return app_utils.next_date_selection(get_indexer().get_available_dates(),
                                         current_options, current_value)


@callback(
    Output('divergence_display_container', 'children'),
    Output('divergence_caption', 'children'),
    [Input('divergence_class_selector', 'value'),
     Input('divergence_show_selector', 'value'),
     Input('session_palette_theme_asset_store', 'data'),
     Input('divergence_date_selector', 'value')],
)
def render_board(asset_classes, show, palette_name, target_date):
    empty = html.P("Select an asset class to draw the board.",
                   style={'textAlign': 'center', 'color': vc.TEXT_COLOR})
    if not asset_classes:
        return empty, ""

    show = show if show in SHOW_LABELS else SHOW_DIFFERENCES
    # The models' own window, the same Custom lookback every verdict surface gates on.
    df = get_matrix_data(asset_classes, "Custom", target_date)
    if df.empty:
        return (html.P("No data available.",
                       style={'textAlign': 'center', 'color': vc.TEXT_COLOR}),
                "")

    rows, hidden, unplaced = divergence_rows.build_rows(
        df, show_all=(show == SHOW_ALL))
    palette = viz_config.get_palette(palette_name)
    report_date = target_date or (df.iloc[0]["Date"] if not df.empty else None)

    if not rows:
        board = html.P(
            "No disagreements this week: every drawn market reads the same under "
            "all three models.",
            style={'textAlign': 'center', 'color': vc.TEXT_COLOR,
                   'padding': '2rem 0'})
    else:
        board = build_table(rows, palette)
    return board, caption(report_date, show, hidden, unplaced)
