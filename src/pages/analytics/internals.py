"""Market internals: six daily reads of the tape and an ETF table on one page.

The view recreated is the Caruso Insights market overview of 2026-09-17 (FOMO,
net new highs, advancing against declining, credit against its 20-day, defensive
rotation against its 50-day, up/down volume, and an index-and-asset table), read
from the two marketdata domains and drawn in this app's own chrome. Every number,
label and cutoff comes from `components.market_internals`; this file only draws.

Rendered per request in `layout()` rather than through a callback: there is no
control to react to, and the snapshot is cached on the store's own dates, so a
page load after the nightly delivery is the only one that pays for the reads.
The scoping doc (docs/design/tradingview-breadth-scoping.md, step 7) placed the
FOMO and net-highs component on the crowd page; it lives here instead because
the view it recreates is a page of daily reads, and the crowd board is weekly.
"""

import dash
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from cotmetrics import indicators
from dash import dcc, html

import components.market_internals as mi
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

AVERAGE_COLOR = "#5B8DD6"
CARD_STYLE = {
    "backgroundColor": "rgba(28,28,28,0.55)",
    "border": "1px solid rgba(255,255,255,0.10)",
}
TITLE_STYLE = {"color": vc.TEXT_COLOR, "fontSize": "0.85rem", "marginBottom": "0.4rem"}
BIG_STYLE = {"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "1.9rem", "fontWeight": 600,
             "lineHeight": 1.1}
DETAIL_STYLE = {"color": vc.TEXT_COLOR, "fontSize": "0.8rem"}
GRAPH_CONFIG = {"displayModeBar": False, "responsive": True, "staticPlot": True}
FOOTER = ("Breadth counts and shares are TradingView's published daily series, "
          "delivered by the producer box's routine; prices are the equities store. "
          "The credit read and the XLP/QQQ ratio are dividend-adjusted, because an "
          "ex-dividend notch in a raw price reads as a break of a moving average; "
          "the table and the up/down volume sessions are prices as traded. Up/down "
          "volume covers the last 20 completed sessions. Context, not signal: "
          "nothing on this page has been through the evaluation ladder. Information "
          "only, not investment advice.")


def _colors():
    return plot_colors.grid_colors(viz_config.get_palette())


def _verdict_color(verdict, colors):
    return {mi.POSITIVE: colors.bull, mi.NEGATIVE: colors.bear}.get(verdict, vc.TEXT_COLOR)


def _badge(text, verdict, colors):
    color = _verdict_color(verdict, colors)
    return html.Span(text, style={
        "color": color, "backgroundColor": plot_colors.hex_to_rgba(color, 0.14),
        "border": f"1px solid {plot_colors.hex_to_rgba(color, 0.35)}",
        "borderRadius": "4px", "padding": "2px 8px", "fontSize": "0.8rem",
        "fontWeight": 600, "whiteSpace": "nowrap",
    })


def _signed(value, fmt):
    return ("+" if value >= 0 else "") + format(value, fmt)


def _pct(fraction):
    return _signed(fraction * 100, ".2f") + "%"


def _base_layout(height):
    return dict(
        height=height, margin=dict(l=44, r=8, t=8, b=28),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False, font=dict(color=vc.TEXT_COLOR, size=10),
        xaxis=dict(showgrid=False, zeroline=False, fixedrange=True,
                   tickfont=dict(size=9, color=vc.TEXT_COLOR)),
        yaxis=dict(gridcolor=vc.GRID_COLOR, zeroline=False, fixedrange=True,
                   tickfont=dict(size=9, color=vc.TEXT_COLOR)),
    )


def _card(title, *body):
    return dbc.Card(dbc.CardBody([html.Div(title, style=TITLE_STYLE), *body],
                                 className="p-3"),
                    style=CARD_STYLE, className="mb-3")


def _awaiting_card(title, symbols):
    return _card(title, html.Div(f"Awaiting data for {', '.join(symbols)}.",
                                 style=DETAIL_STYLE))


# ── FOMO ──────────────────────────────────────────────────────────────────────

def _fomo_figure(read, colors):
    dates, values = read.path
    fig = go.Figure()
    for level, color in ((indicators.FOMO_EXHAUSTION_MIN, colors.bear),
                         (indicators.FOMO_FEAR_MAX, colors.bull)):
        fig.add_hline(y=level, line=dict(color=color, width=1, dash="dot"), opacity=0.6)
    # Thinner than the other charts on purpose: a year of a series this whippy is a
    # dense band in a third-width card, and the zone crossings are what has to stay
    # legible through it.
    fig.add_trace(go.Scatter(x=list(dates), y=list(values), mode="lines",
                             line=dict(color=vc.BRIGHTER_TEXT_COLOR, width=1),
                             hoverinfo="skip"))
    layout = _base_layout(200)
    layout["yaxis"]["range"] = [0, 100]
    # A year of sessions at agi's zoom, so the ticks are months. Fixed rather than
    # automatic: plotly's own format put the year on one tick and not the others.
    layout["xaxis"]["nticks"] = 5
    layout["xaxis"]["tickformat"] = "%b"
    fig.update_layout(**layout)
    return fig


def fomo_card(read, colors):
    if read is None:
        return _awaiting_card("Nasdaq stocks above their 5-day average · FOMO",
                              [mi.FOMO_SYMBOL])
    return _card(
        "Nasdaq stocks above their 5-day average · FOMO",
        html.Div([
            html.Span(f"{read.value:.1f}", style=BIG_STYLE),
            html.Span(_badge(read.label, read.verdict, colors), className="ms-2"),
            html.Span(f"{_signed(read.change, '.1f')} on the day",
                      style={**DETAIL_STYLE, "float": "right",
                             "color": _verdict_color(
                                 mi.POSITIVE if read.change >= 0 else mi.NEGATIVE, colors)}),
        ], className="d-flex align-items-center"),
        dcc.Graph(figure=_fomo_figure(read, colors), config=GRAPH_CONFIG),
        html.Div([
            html.Span("Past year"),
            html.Span(f"{indicators.FOMO_EXHAUSTION_MIN:.0f} stretched · "
                      f"{indicators.FOMO_FEAR_MAX:.0f} washed out",
                      style={"float": "right"}),
        ], style=DETAIL_STYLE),
    )


# ── net new highs ─────────────────────────────────────────────────────────────

def _arrows(signs, colors):
    glyphs = {1: ("▲", colors.bull), -1: ("▼", colors.bear), 0: ("•", vc.TEXT_COLOR)}
    return html.Span([html.Span(glyphs[s][0], style={"color": glyphs[s][1],
                                                     "marginRight": "3px"})
                      for s in signs])


def _net_highs_row(read, colors):
    color = _verdict_color(read.verdict, colors)
    return html.Div([
        html.Div([
            html.Div(read.exchange, style={"color": vc.BRIGHTER_TEXT_COLOR}),
            html.Div(f"{read.highs} highs, {read.lows} lows", style=DETAIL_STYLE),
            _arrows(read.last_three, colors),
        ]),
        html.Div([
            html.Div(_signed(read.net, "d"), style={**BIG_STYLE, "color": color,
                                                    "textAlign": "right"}),
            html.Div(_badge(read.label, read.verdict, colors),
                     style={"textAlign": "right", "marginTop": "4px"}),
        ]),
    ], className="d-flex justify-content-between mb-3",
       style={"borderLeft": f"3px solid {color}" if read.regime else "3px solid transparent",
              "paddingLeft": "8px"})


def net_highs_card(reads, awaiting, colors):
    rows = [_net_highs_row(r, colors) for r in reads]
    missing = [s for _, hi, lo in mi.NET_HIGHS_SYMBOLS for s in (hi, lo) if s in awaiting]
    if missing:
        rows.append(html.Div(f"Awaiting data for {', '.join(missing)}.", style=DETAIL_STYLE))
    return _card("Net new highs minus new lows", *rows)


# ── advancing against declining ───────────────────────────────────────────────

def advance_decline_card(read, colors):
    if read is None:
        return _awaiting_card("Nasdaq issues advancing vs declining",
                              [mi.ADVANCING_SYMBOL, mi.DECLINING_SYMBOL])
    pct = read.share * 100
    return _card(
        "Nasdaq issues advancing vs declining",
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

def _trend_figure(read):
    dates, values, averages = read.path
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=list(dates), y=list(values), mode="lines", name=read.symbol,
                             line=dict(color=vc.BRIGHTER_TEXT_COLOR, width=1.5),
                             hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=list(dates), y=list(averages), mode="lines",
                             name=f"{read.average_sessions}-day average",
                             line=dict(color=AVERAGE_COLOR, width=2), hoverinfo="skip"))
    layout = _base_layout(260)
    layout["xaxis"]["nticks"] = 4
    fig.update_layout(**layout)
    return fig


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
        dcc.Graph(figure=_trend_figure(read), config=GRAPH_CONFIG),
        html.Div([
            html.Span("— Price" if read.key == "credit" else "— Ratio",
                      style={"marginRight": "12px"}),
            html.Span(f"— {read.average_sessions}-day average",
                      style={"color": AVERAGE_COLOR}),
        ], style=DETAIL_STYLE),
    )


def _credit_detail(read):
    return (f"{read.average_sessions}-day avg {read.average:.2f} "
            f"{'rising' if read.rising else 'falling'} · price {_pct(read.change)} "
            f"· price only")


def _rotation_detail(read):
    side = "above" if read.above else "below"
    return (f"{read.average_sessions}-day avg {read.average:.4f} · ratio {side} by "
            f"{_pct(read.gap)}")


# ── up/down volume ────────────────────────────────────────────────────────────

def _updown_row(read, colors):
    color = _verdict_color(read.verdict, colors)
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
        rows.append(html.Div(f"Awaiting data for {', '.join(missing)}.", style=DETAIL_STYLE))
    if reads:
        rows.append(html.Div(f"Final · {mi.UPDOWN_SESSIONS} sessions to {reads[-1].date}",
                             style={**DETAIL_STYLE, "fontSize": "0.72rem"}))
    return _card(f"Up / down volume ratio · {mi.UPDOWN_SESSIONS} sessions", *rows)


# ── the asset table ───────────────────────────────────────────────────────────

def _spark(row, colors):
    color = colors.bull if row.quarter_change >= 0 else colors.bear
    fig = go.Figure(go.Scatter(y=list(row.path), mode="lines",
                               line=dict(color=color, width=1.2), hoverinfo="skip"))
    fig.update_layout(height=30, width=110, margin=dict(l=0, r=0, t=2, b=2),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      xaxis=dict(visible=False, fixedrange=True),
                      yaxis=dict(visible=False, fixedrange=True), showlegend=False)
    return dcc.Graph(figure=fig, config=GRAPH_CONFIG,
                     style={"height": "30px", "width": "110px"})


def asset_table(rows, awaiting, colors):
    head = html.Thead(html.Tr([html.Th(h, style={**DETAIL_STYLE, "fontWeight": 400,
                                                 "borderBottom": "1px solid var(--border-color)"})
                               for h in ("Symbol", "Last", "Day", "3 mo")]))
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
            html.Td(html.Span(_pct(row.day_change), style={"color": day_color}),
                    style={"textAlign": "right"}),
            html.Td(_spark(row, colors), style={"textAlign": "right"}),
        ], style={"borderBottom": "1px solid var(--border-color-dim)"}))
    missing = [s for s in mi.ASSET_SYMBOLS if s in awaiting]
    for symbol in missing:
        body.append(html.Tr([
            html.Td(symbol, style={"color": vc.TEXT_COLOR}),
            html.Td("awaiting data", colSpan=3, style=DETAIL_STYLE),
        ]))
    return _card("Index and asset overview",
                 html.Table([head, html.Tbody(body)], className="w-100",
                            style={"borderCollapse": "collapse"}))


# ── the page ──────────────────────────────────────────────────────────────────

def _header(snap, colors):
    lean, count = mi.headline(snap)
    count_color = colors.bull if lean.endswith("constructive.") else (
        colors.bear if lean.endswith("defensive.") else vc.TEXT_COLOR)
    return html.Div([
        html.Div([
            html.Span(lean, style={"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "1.5rem",
                                   "fontWeight": 500, "marginRight": "10px"}),
            html.Span(count, style={"color": count_color, "fontSize": "1.5rem",
                                    "fontWeight": 500}),
        ]),
        html.Div("; ".join(mi.summary_sentences(snap)), style=DETAIL_STYLE),
    ], className="mb-3")


def _caption(snap):
    parts = [FOOTER]
    if snap.awaiting:
        parts.append(f"Awaiting data for: {', '.join(snap.awaiting)}.")
    stale = mi.stale_notes(snap)
    if stale:
        parts.append(f"Trailing the newest read: {'; '.join(stale)}.")
    return html.Div(" ".join(parts), style={**DETAIL_STYLE, "fontSize": "0.75rem",
                                             "marginTop": "0.5rem"})


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
                trend_card(snap.credit,
                           f"High-yield credit · {mi.CREDIT_SYMBOL} against its "
                           f"{mi.CREDIT_AVERAGE}-day average",
                           ".2f", _credit_detail, [mi.CREDIT_SYMBOL], colors),
                trend_card(snap.rotation,
                           f"Defensive rotation · {mi.ROTATION_NUMER} against "
                           f"{mi.ROTATION_DENOM}",
                           ".4f", _rotation_detail,
                           [mi.ROTATION_NUMER, mi.ROTATION_DENOM], colors),
            ], xs=12, lg=6),
            dbc.Col([
                asset_table(snap.assets, snap.awaiting, colors),
                updown_card(snap.updown, snap.awaiting, colors, snap.date),
            ], xs=12, lg=3),
        ], className="g-3"),
        _caption(snap),
    ], fluid=True, className="py-3")
