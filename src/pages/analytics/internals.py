"""Market internals: six daily reads of the tape and an ETF table on one page.

The view recreated is the Caruso Insights market overview of 2026-09-17 (FOMO,
net new highs, advancing against declining, credit against its 20-day, defensive
rotation against its 50-day, up/down volume, and an index-and-asset table), read
from the two marketdata domains and drawn in this app's own chrome. Every number,
label and cutoff comes from `components.market_internals`; this file only draws.
The titles, formats and figures are `components.market_internals_view`'s, shared with
the published static copy (`components.market_internals_static`,
docs/internals-publishing.md), so the two pages cannot say different things.

Rendered per request in `layout()` rather than through a callback: there is no
control to react to, and the snapshot is cached on the store's own dates, so a
page load after the nightly delivery is the only one that pays for the reads.
The scoping doc (docs/design/tradingview-breadth-scoping.md, step 7) placed the
FOMO and net-highs component on the crowd page; it lives here instead because
the view it recreates is a page of daily reads, and the crowd board is weekly.
"""

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

import components.market_internals as mi
import components.market_internals_view as view
import viz_config
import viz_constants as vc
from components import plot_colors

dash.register_page(
    __name__,
    path='/internals',
    title='Market Internals | COT Analyzer',
    description='Six daily reads of the tape on one page: Nasdaq FOMO, net new '
                '52-week highs, advancing against declining issues, high-yield '
                'credit against its 20-day average, staples over Nasdaq against '
                'its 50-day, and 20-session up/down volume, beside an ETF table.',
)

CARD_STYLE = {
    "backgroundColor": "rgba(28,28,28,0.55)",
    "border": "1px solid rgba(255,255,255,0.10)",
}
TITLE_STYLE = {"color": vc.TEXT_COLOR, "fontSize": "0.85rem", "marginBottom": "0.4rem"}
BIG_STYLE = {"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "1.9rem", "fontWeight": 600,
             "lineHeight": 1.1}
DETAIL_STYLE = {"color": vc.TEXT_COLOR, "fontSize": "0.8rem"}
GRAPH_CONFIG = {"displayModeBar": False, "responsive": True, "staticPlot": True}
def _colors():
    return plot_colors.grid_colors(viz_config.get_palette())


def _badge(text, verdict, colors):
    color = view.verdict_color(verdict, colors)
    return html.Span(text, style={
        "color": color, "backgroundColor": plot_colors.hex_to_rgba(color, 0.14),
        "border": f"1px solid {plot_colors.hex_to_rgba(color, 0.35)}",
        "borderRadius": "4px", "padding": "2px 8px", "fontSize": "0.8rem",
        "fontWeight": 600, "whiteSpace": "nowrap",
    })


def _card(title, *body):
    return dbc.Card(dbc.CardBody([html.Div(title, style=TITLE_STYLE), *body],
                                 className="p-3"),
                    style=CARD_STYLE, className="mb-3")


def _awaiting_card(title, symbols):
    return _card(title, html.Div(view.awaiting_text(symbols), style=DETAIL_STYLE))


# ── FOMO ──────────────────────────────────────────────────────────────────────

def fomo_card(read, colors):
    if read is None:
        return _awaiting_card(view.FOMO_TITLE, [mi.FOMO_SYMBOL])
    return _card(
        view.FOMO_TITLE,
        html.Div([
            html.Span(f"{read.value:.1f}", style=BIG_STYLE),
            html.Span(_badge(read.label, read.verdict, colors), className="ms-2"),
            html.Span(f"{view.signed(read.change, '.1f')} on the day",
                      style={**DETAIL_STYLE, "float": "right",
                             "color": view.verdict_color(
                                 mi.POSITIVE if read.change >= 0 else mi.NEGATIVE, colors)}),
        ], className="d-flex align-items-center"),
        dcc.Graph(figure=view.fomo_figure(read, colors), config=GRAPH_CONFIG),
        html.Div([
            html.Span(view.FOMO_SPAN),
            html.Span(view.FOMO_ZONES, style={"float": "right"}),
        ], style=DETAIL_STYLE),
    )


# ── net new highs ─────────────────────────────────────────────────────────────

def _arrows(signs, colors):
    glyphs = {1: ("▲", colors.bull), -1: ("▼", colors.bear), 0: ("•", vc.TEXT_COLOR)}
    return html.Span([html.Span(glyphs[s][0], style={"color": glyphs[s][1],
                                                     "marginRight": "3px"})
                      for s in signs])


def _net_highs_row(read, colors):
    color = view.verdict_color(read.verdict, colors)
    return html.Div([
        html.Div([
            html.Div(read.exchange, style={"color": vc.BRIGHTER_TEXT_COLOR}),
            html.Div(f"{read.highs} highs, {read.lows} lows", style=DETAIL_STYLE),
            _arrows(read.last_three, colors),
        ]),
        html.Div([
            html.Div(view.signed(read.net, "d"), style={**BIG_STYLE, "color": color,
                                                    "textAlign": "right"}),
            html.Div(_badge(read.label, read.verdict, colors),
                     style={"textAlign": "right", "marginTop": "4px"}),
        ]),
    ], className="d-flex justify-content-between mb-3",
       style={"borderLeft": f"3px solid {color}" if read.regime else "3px solid transparent",
              "paddingLeft": "8px"})


def net_highs_card(reads, awaiting, colors):
    rows = [_net_highs_row(r, colors) for r in reads]
    missing = view.net_highs_awaiting(awaiting)
    if missing:
        rows.append(html.Div(view.awaiting_text(missing), style=DETAIL_STYLE))
    return _card(view.NET_HIGHS_TITLE, *rows)


# ── advancing against declining ───────────────────────────────────────────────

def advance_decline_card(read, colors):
    if read is None:
        return _awaiting_card(view.ADVANCE_DECLINE_TITLE,
                              [mi.ADVANCING_SYMBOL, mi.DECLINING_SYMBOL])
    pct = read.share * 100
    return _card(
        view.ADVANCE_DECLINE_TITLE,
        html.Div([
            html.Div(style={"width": f"{pct:.1f}%", "backgroundColor": colors.bull,
                            "height": "8px", "borderRadius": "4px 0 0 4px"}),
            html.Div(style={"width": f"{100 - pct:.1f}%", "backgroundColor": colors.bear,
                            "height": "8px", "borderRadius": "0 4px 4px 0"}),
        ], className="d-flex mb-2"),
        html.Div([
            html.Span(f"{pct:.0f}% advancing", style={"color": colors.bull}),
            html.Span(_badge(read.label, read.verdict, colors)),
            html.Span(f"{100 - pct:.0f}% declining", style={"color": colors.bear}),
        ], className="d-flex justify-content-between"),
        html.Div(f"{read.advancing:,} up, {read.declining:,} down", style=DETAIL_STYLE),
    )


# ── a series against its average ──────────────────────────────────────────────

def trend_card(read, title, value_fmt, detail, awaiting_symbols, colors):
    if read is None:
        return _awaiting_card(title, awaiting_symbols)
    return _card(
        title,
        html.Div([
            html.Span(format(read.value, value_fmt), style=BIG_STYLE),
            html.Span(_badge(read.label, read.verdict, colors),
                      style={"marginLeft": "auto"}),
        ], className="d-flex align-items-center"),
        html.Div(detail(read), style=DETAIL_STYLE),
        dcc.Graph(figure=view.trend_figure(read), config=GRAPH_CONFIG),
        html.Div([
            html.Span(view.trend_key(read)[0], style={"marginRight": "12px"}),
            html.Span(view.trend_key(read)[1], style={"color": view.AVERAGE_COLOR}),
        ], style=DETAIL_STYLE),
    )


# ── up/down volume ────────────────────────────────────────────────────────────

def _updown_row(read, colors):
    color = view.verdict_color(read.verdict, colors)
    total = read.up_days + read.down_days
    up_share = read.up_days / total * 100 if total else 50
    return html.Div([
        html.Div([
            html.Span(read.symbol, style={"color": vc.BRIGHTER_TEXT_COLOR}),
            html.Span(f"{read.ratio:.2f}", style={**BIG_STYLE, "fontSize": "1.4rem",
                                                  "color": color}),
        ], className="d-flex justify-content-between align-items-center"),
        html.Div([
            html.Div(style={"width": f"{up_share:.1f}%", "backgroundColor": colors.bull,
                            "height": "6px"}),
            html.Div(style={"width": f"{100 - up_share:.1f}%",
                            "backgroundColor": colors.bear, "height": "6px"}),
        ], className="d-flex my-1"),
        html.Div([
            html.Span(f"{read.up_days} up days vs {read.down_days} down"),
            _badge(read.label, read.verdict, colors),
        ], className="d-flex justify-content-between", style=DETAIL_STYLE),
    ], className="mb-3")


def updown_card(reads, awaiting, colors, date):
    rows = [_updown_row(r, colors) for r in reads]
    missing = [s for s in mi.UPDOWN_SYMBOLS if s in awaiting]
    if missing:
        rows.append(html.Div(view.awaiting_text(missing), style=DETAIL_STYLE))
    if reads:
        rows.append(html.Div(view.updown_foot(reads),
                             style={**DETAIL_STYLE, "fontSize": "0.72rem"}))
    return _card(view.UPDOWN_TITLE, *rows)


# ── the asset table ───────────────────────────────────────────────────────────

def _spark(row, colors):
    return dcc.Graph(figure=view.spark_figure(row, colors), config=GRAPH_CONFIG,
                     style={"height": f"{view.SPARK_HEIGHT}px",
                            "width": f"{view.SPARK_WIDTH}px"})


def asset_table(rows, awaiting, colors):
    head = html.Thead(html.Tr([html.Th(h, style={**DETAIL_STYLE, "fontWeight": 400,
                                                 "borderBottom": "1px solid var(--border-color)"})
                               for h in view.ASSET_COLUMNS]))
    body = []
    # The text sits in a span inside each cell: custom.css sets every `tbody td` to
    # the muted color with !important, which beats a style on the cell itself.
    for row in rows:
        day_color = colors.bull if row.day_change >= 0 else colors.bear
        body.append(html.Tr([
            html.Td(html.Span(row.symbol, style={"color": vc.BRIGHTER_TEXT_COLOR,
                                                 "fontWeight": 600})),
            html.Td(html.Span(f"{row.last:,.2f}", style={"color": vc.BRIGHTER_TEXT_COLOR}),
                    style={"textAlign": "right"}),
            html.Td(html.Span(view.pct(row.day_change), style={"color": day_color}),
                    style={"textAlign": "right"}),
            html.Td(_spark(row, colors), style={"textAlign": "right"}),
        ], style={"borderBottom": "1px solid var(--border-color-dim)"}))
    missing = [s for s in mi.ASSET_SYMBOLS if s in awaiting]
    for symbol in missing:
        body.append(html.Tr([
            html.Td(symbol, style={"color": vc.TEXT_COLOR}),
            html.Td("awaiting data", colSpan=3, style=DETAIL_STYLE),
        ]))
    return _card(view.ASSETS_TITLE,
                 html.Table([head, html.Tbody(body)], className="w-100",
                            style={"borderCollapse": "collapse"}))


# ── the page ──────────────────────────────────────────────────────────────────

def _header(snap, colors):
    lean, count = mi.headline(snap)
    count_color = view.headline_color(lean, colors)
    return html.Div([
        html.Div([
            html.Span(lean, style={"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "1.5rem",
                                   "fontWeight": 500, "marginRight": "10px"}),
            html.Span(count, style={"color": count_color, "fontSize": "1.5rem",
                                    "fontWeight": 500}),
        ]),
        html.Div("; ".join(mi.summary_sentences(snap)), style=DETAIL_STYLE),
    ], className="mb-3")


def layout(**kwargs):
    # Built per request, not at import, so importing this page needs no store.
    snap = mi.snapshot()
    colors = _colors()
    date_text = f"As of {snap.date}" if snap.date else "No data yet"
    return dbc.Container([
        html.Div([
            html.H2("Market internals", className="mb-0",
                    style={"color": vc.BRIGHTER_TEXT_COLOR, "border": "none"}),
            html.Div(date_text, style=DETAIL_STYLE),
        ], className="d-flex justify-content-between align-items-end mb-3"),
        _header(snap, colors),
        dbc.Row([
            dbc.Col([
                fomo_card(snap.fomo, colors),
                net_highs_card(snap.net_highs, snap.awaiting, colors),
                advance_decline_card(snap.advance_decline, colors),
            ], xs=12, lg=3),
            dbc.Col([
                trend_card(snap.credit, view.CREDIT_TITLE, ".2f", view.credit_detail,
                           [mi.CREDIT_SYMBOL], colors),
                trend_card(snap.rotation, view.ROTATION_TITLE, ".4f", view.rotation_detail,
                           [mi.ROTATION_NUMER, mi.ROTATION_DENOM], colors),
            ], xs=12, lg=6),
            dbc.Col([
                asset_table(snap.assets, snap.awaiting, colors),
                updown_card(snap.updown, snap.awaiting, colors, snap.date),
            ], xs=12, lg=3),
        ], className="g-3"),
        html.Div(view.caption(snap), style={**DETAIL_STYLE, "fontSize": "0.75rem",
                                            "marginTop": "0.5rem"}),
    ], fluid=True, className="py-3")
