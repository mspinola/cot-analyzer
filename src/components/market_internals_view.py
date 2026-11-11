"""What the market internals page says and draws, apart from how it is laid out.

Two renderers draw `components.market_internals`' snapshot: the app's `/internals`
page (Dash components, `pages/analytics/internals.py`) and the published static copy
(`components.market_internals_static`, one HTML file). Everything the two must agree
on lives here, so neither can drift from the other: the card titles, the number
formats, the detail lines, the footer, and the three figures. Nothing in this module
computes a read; every number comes off the snapshot.

No Dash import, on purpose: the static export runs without an app, and
`dash.register_page` in the page module cannot be imported outside one.
"""
import plotly.graph_objects as go
from cotmetrics import indicators

import components.market_internals as mi
import viz_constants as vc

AVERAGE_COLOR = "#5B8DD6"

FOMO_TITLE = "Nasdaq stocks above their 5-day average · FOMO"
NET_HIGHS_TITLE = "Net new highs minus new lows"
ADVANCE_DECLINE_TITLE = "Nasdaq issues advancing vs declining"
CREDIT_TITLE = (f"High-yield credit · {mi.CREDIT_SYMBOL} against its "
                f"{mi.CREDIT_AVERAGE}-day average")
ROTATION_TITLE = f"Defensive rotation · {mi.ROTATION_NUMER} against {mi.ROTATION_DENOM}"
UPDOWN_TITLE = f"Up / down volume ratio · {mi.UPDOWN_SESSIONS} sessions"
ASSETS_TITLE = "Index and asset overview"
ASSET_COLUMNS = ("Symbol", "Last", "Day", "3 mo")
FOMO_SPAN = "Past year"
FOMO_ZONES = (f"{indicators.FOMO_EXHAUSTION_MIN:.0f} stretched · "
              f"{indicators.FOMO_FEAR_MAX:.0f} washed out")

FOOTER = ("Breadth counts and shares are TradingView's published daily series, "
          "delivered by the producer box's routine; prices are the equities store. "
          "The credit read and the XLP/QQQ ratio are dividend-adjusted, because an "
          "ex-dividend notch in a raw price reads as a break of a moving average; "
          "the table and the up/down volume sessions are prices as traded. Up/down "
          "volume covers the last 20 completed sessions. Context, not signal: "
          "nothing on this page has been through the evaluation ladder. Information "
          "only, not investment advice.")

#: Sparkline box, px. The table cell is sized to it by both renderers.
SPARK_WIDTH, SPARK_HEIGHT = 110, 30


# ── words and numbers ─────────────────────────────────────────────────────────

def signed(value, fmt):
    return ("+" if value >= 0 else "") + format(value, fmt)


def pct(fraction):
    return signed(fraction * 100, ".2f") + "%"


def verdict_color(verdict, colors):
    return {mi.POSITIVE: colors.bull, mi.NEGATIVE: colors.bear}.get(verdict, vc.TEXT_COLOR)


def headline_color(lean, colors):
    """The colour of the count beside the headline, from which way it leans."""
    if lean.endswith("constructive."):
        return colors.bull
    if lean.endswith("defensive."):
        return colors.bear
    return vc.TEXT_COLOR


def credit_detail(read):
    return (f"{read.average_sessions}-day avg {read.average:.2f} "
            f"{'rising' if read.rising else 'falling'} · price {pct(read.change)} "
            f"· price only")


def rotation_detail(read):
    side = "above" if read.above else "below"
    return (f"{read.average_sessions}-day avg {read.average:.4f} · ratio {side} by "
            f"{pct(read.gap)}")


def trend_key(read):
    """The two legend words under a trend chart: the line, then its average."""
    return ("— Price" if read.key == "credit" else "— Ratio",
            f"— {read.average_sessions}-day average")


def net_highs_awaiting(awaiting):
    return [s for _, hi, lo in mi.NET_HIGHS_SYMBOLS for s in (hi, lo) if s in awaiting]


def updown_foot(reads):
    return f"Final · {mi.UPDOWN_SESSIONS} sessions to {reads[-1].date}"


def awaiting_text(symbols):
    return f"Awaiting data for {', '.join(symbols)}."


def caption(snap):
    """The paragraph under the cards: the footer, then what is missing or trailing."""
    parts = [FOOTER]
    if snap.awaiting:
        parts.append(f"Awaiting data for: {', '.join(snap.awaiting)}.")
    stale = mi.stale_notes(snap)
    if stale:
        parts.append(f"Trailing the newest read: {'; '.join(stale)}.")
    return " ".join(parts)


# ── figures ───────────────────────────────────────────────────────────────────

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


def fomo_figure(read, colors):
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


def trend_figure(read):
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


def spark_figure(row, colors):
    color = colors.bull if row.quarter_change >= 0 else colors.bear
    fig = go.Figure(go.Scatter(y=list(row.path), mode="lines",
                               line=dict(color=color, width=1.2), hoverinfo="skip"))
    fig.update_layout(height=SPARK_HEIGHT, width=SPARK_WIDTH, margin=dict(l=0, r=0, t=2, b=2),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      xaxis=dict(visible=False, fixedrange=True),
                      yaxis=dict(visible=False, fixedrange=True), showlegend=False)
    return fig
