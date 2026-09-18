"""The breadth panel under the crowd board: FOMO and net new highs, daily, against
their published zones.

Two series the crowd board's weekly frame cannot carry, and the measurement that
says so is docs/analysis/2026-09-16-fomo-weekly-sampling.md: the FOMO read (the
share of Nasdaq Composite stocks above their own 5-day average) visits its zones for
a session at a time, and a Tuesday sample sees one exhaustion visit in five. So this
panel is DAILY, and it is drawn against the zones the June 2026 Swing Trading Guide
publishes rather than as a range index: the zone edges are absolute, calibrated by
the source on the vendor's scale, and re-normalising them against a trailing window
would replace the published cutoffs with ones the window happened to produce. The
classifiers are `cotmetrics.indicators.fomo_zones` and `net_highs_regime`, cited
there to the AGI rulebook (M-07, M-01); this module draws what they return.

**Orientation keeps the board's colour axis.** On the board a high cell in the bull
hue is the crowd washed out and a low cell in the bear hue is the crowd crowded. FOMO
exhaustion (above 80) is the crowd chasing, so it wears the bear hue; fear (below 25)
is the washed-out side and wears the bull hue; recovery, which is a direction rather
than a level, wears the bull hue's near tier; neutral and the two unnamed gaps are
dim. Net new highs are a different axis (trend confirmation, the source's own words),
and they keep the source's own rendering: columns in plain ink, with a background
band in the bull hue where the last three sessions were all net positive and the bear
hue where all three were net negative. That band is the regime; the columns are the
counts.

**Context, not signal, and not a composite.** Nothing here has been through the
evaluation ladder or crucible. A zone label is a published cutoff restated. The two
series stay two panels, and neither is folded into the other or into the board.

**Data arrives on its own schedule.** The series come from marketdata's `series`
domain, produced nightly on the Windows box and delivered by the mirror. A series
the store does not hold yields no panel and a caption saying so, never an error: the
board above must not depend on the price store to draw positioning.
"""

import functools
from dataclasses import dataclass

import cotmetrics.indicators as ind
import cotmetrics.utils as utils
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import viz_constants as vc
from components.plot_colors import hex_to_rgba

# Trailing sessions drawn: three months of trading days, enough to see the last few
# zone visits and the regime flips around them without the line turning to noise.
SESSIONS = 60

# Nasdaq for both series, and only Nasdaq. Rulebook M-07 defines FOMO on Nasdaq
# stocks and its zones were read off that series; the S&P 500 variant (S5FD, in the
# store as SPX_FOMO_5D) exists only as a dropdown in the Pine script, and nothing in
# the corpus, the call notes or the agi importer uses it. Drawing it against
# Nasdaq-calibrated bands would be an untested extension wearing the guide's labels,
# so the panel does not offer it (it did, for a day). M-01's net new highs are Nasdaq
# by the author's explicit choice: the liquidity-sensitive names under the surface.
FOMO = ("NASDAQ_FOMO_5D", "Nasdaq Composite")
NET_HIGHS = ("NASDAQ_NH52W", "NASDAQ_NL52W")
SYMBOLS = (FOMO[0],) + NET_HIGHS

# How far the last session may trail the board's week before the caption says so.
# A weekend plus a holiday is four days; five means the routine missed a night.
STALE_AFTER_DAYS = 5

FIGURE_PX = 360
ZONE_WASH_ALPHA = 0.10
REGIME_WASH_ALPHA = 0.14
MARKER_SIZE = 6
GAP_MARKER_SIZE = 3


@dataclass(frozen=True)
class BreadthRead:
    """What the panel draws: the trailing window of both series and their labels."""
    fomo: pd.Series
    zones: pd.Series
    net: pd.Series
    regime: pd.Series
    highs: pd.Series
    lows: pd.Series

    @property
    def date(self):
        return max(self.fomo.index.max(), self.net.index.max()).strftime("%Y-%m-%d")

    @property
    def zone(self):
        return self.zones.iloc[-1]

    @property
    def latest(self):
        return float(self.fomo.iloc[-1])


# Indirection so tests stand in for the store, and so importing this module needs
# no MARKETDATA_STORE: the crowd page imports it at load.
def _get_bars(symbol):
    import marketdata
    return marketdata.get_bars(symbol)


def _last_date(symbol):
    import marketdata
    p = marketdata.provenance(symbol)
    return p.last_date if p else None


def _stamp(symbols):
    """The cache key: each series' last bar date, or None when any is unreadable.
    Keyed on the data, the tape-context convention: a nightly delivery invalidates
    the entry and nothing else does."""
    try:
        return tuple(_last_date(s) for s in symbols)
    except Exception:  # noqa: BLE001 -- absent series, unset store, stale checkout
        return None


def _close(symbol, get_bars):
    df = get_bars(symbol)
    if df is None or df.empty or "Close" not in df:
        return None
    s = df["Close"].astype(float).dropna()
    s.index = pd.to_datetime(s.index).normalize()
    return s.sort_index()


def build_read(get_bars=None, target_date=None, sessions=SESSIONS):
    """The read, or None when any of the three series is absent.

    The zone and regime classifiers run over the FULL series before the window is
    cut, because the recovery test and the three-day rule look back past the first
    drawn session. `target_date` ends the window on or before that date, so the
    panel agrees with the week the board shows.
    """
    get_bars = get_bars or _get_bars
    fomo = _close(FOMO[0], get_bars)
    highs = _close(NET_HIGHS[0], get_bars)
    lows = _close(NET_HIGHS[1], get_bars)
    if fomo is None or highs is None or lows is None:
        return None
    net = (highs - lows).dropna()
    if target_date:
        cut = pd.Timestamp(target_date)
        fomo = fomo.loc[fomo.index <= cut]
        net = net.loc[net.index <= cut]
    if fomo.empty or net.empty:
        return None
    zones = ind.fomo_zones(fomo)
    regime = ind.net_highs_regime(net)
    tail = slice(-sessions, None)
    return BreadthRead(
        fomo=fomo.iloc[tail], zones=zones.iloc[tail],
        net=net.iloc[tail], regime=regime.iloc[tail],
        highs=highs.reindex(net.index).iloc[tail],
        lows=lows.reindex(net.index).iloc[tail],
    )


@functools.lru_cache(maxsize=16)
def _cached_read(target_date, stamp):
    if stamp is None or None in stamp:
        return None
    try:
        return build_read(target_date=target_date)
    except Exception as e:  # noqa: BLE001 -- one missing series must not take the page
        utils.cot_logger.warning(f"breadth panel: no read: {e}")
        return None


def read(target_date=None):
    """`(read, awaiting)`: the BreadthRead, or None with the symbols the store
    cannot serve."""
    r = _cached_read(target_date, _stamp(SYMBOLS))
    if r is None:
        return None, list(SYMBOLS)
    return r, []


def cut_date(target_date, newest_report_date):
    """Where the panel ends. None (run to the last session) unless the reader has
    chosen a week OLDER than the newest report; the newest report is the board's
    default and means "now", not "cut at Tuesday"."""
    if not target_date or not newest_report_date:
        return None
    return target_date if pd.Timestamp(target_date) < pd.Timestamp(newest_report_date) else None


def warm():
    """Fill the cache for the boot warmer. Swallowing is the warmer's own rule."""
    _cached_read(None, _stamp(SYMBOLS))


# ── drawing ───────────────────────────────────────────────────────────────────
ZONE_LABELS = {
    "exhaustion": "exhaustion, above 80",
    "neutral": "neutral, 35 to 60",
    "fear": "fear, below 25",
    "recovery": "recovery, turning up from fear",
    None: "unnamed gap (25 to 35 or 60 to 80)",
}


def zone_color(zone, colors):
    """The zone's ink, on the board's axis: crowded wears the bear hue, washed out
    the bull hue, a turn out of fear the bull near tier, anything unnamed dim."""
    return {"exhaustion": colors.bear, "fear": colors.bull,
            "recovery": colors.bull_near}.get(zone, colors.dim)


def regime_color(regime, colors):
    return {"up": colors.bull, "down": colors.bear}.get(regime)


def _runs(labels):
    """Consecutive runs of an object Series as (label, start, end) with None skipped."""
    out, cur = [], None
    for date, label in labels.items():
        if cur is not None and cur[0] == label:
            cur[2] = date
            continue
        if cur is not None:
            out.append(tuple(cur))
        cur = [label, date, date]
    if cur is not None:
        out.append(tuple(cur))
    return [r for r in out if r[0] is not None]


def build_figure(r, colors, background=vc.BACKGROUND_COLOR):
    """The two panels, pure over a BreadthRead and a colour set."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.10,
                        row_heights=[0.58, 0.42])
    x0, x1 = r.fomo.index.min(), max(r.fomo.index.max(), r.net.index.max())

    # The published zones as washes, drawn first so the line sits on them.
    for lo, hi, hue in ((ind.FOMO_EXHAUSTION_MIN, 100, colors.bear),
                        (0, ind.FOMO_FEAR_MAX, colors.bull),
                        (ind.FOMO_NEUTRAL[0], ind.FOMO_NEUTRAL[1], None)):
        fill = (hex_to_rgba(hue, ZONE_WASH_ALPHA) if hue
                else "rgba(255,255,255,0.05)")
        fig.add_shape(type="rect", xref="x", yref="y", x0=x0, x1=x1, y0=lo, y1=hi,
                      fillcolor=fill, line=dict(width=0), layer="below", row=1, col=1)

    hover = [f"{d:%Y-%m-%d}<br>FOMO {v:.2f}<br>{ZONE_LABELS[z]}"
             for d, v, z in zip(r.fomo.index, r.fomo, r.zones)]
    fig.add_trace(go.Scatter(
        x=r.fomo.index, y=r.fomo.values, mode="lines",
        line=dict(color=vc.TEXT_COLOR, width=1.2),
        hoverinfo="skip", showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=r.fomo.index, y=r.fomo.values, mode="markers",
        marker=dict(
            size=[MARKER_SIZE if z else GAP_MARKER_SIZE for z in r.zones],
            color=[zone_color(z, colors) for z in r.zones]),
        hovertext=hover, hoverinfo="text", showlegend=False), row=1, col=1)
    # The reading of record: the last session, labelled with its zone.
    fig.add_annotation(
        x=r.fomo.index[-1], y=r.latest, xref="x", yref="y",
        text=f"<b>{r.latest:.0f}</b> {ZONE_LABELS[r.zone].split(',')[0]}",
        showarrow=True, arrowhead=0, ax=-56, ay=-22, arrowcolor=colors.dim,
        font=dict(size=11, color=zone_color(r.zone, colors)),
        bgcolor=hex_to_rgba(background, 0.7) if background.startswith("#") else background,
        row=1, col=1)

    # Net new highs: the source's rendering, columns in ink and a regime band behind.
    for label, start, end in _runs(r.regime):
        fig.add_shape(type="rect", xref="x2", yref="y2 domain",
                      x0=start - pd.Timedelta(hours=12), x1=end + pd.Timedelta(hours=12),
                      y0=0, y1=1, fillcolor=hex_to_rgba(regime_color(label, colors),
                                                        REGIME_WASH_ALPHA),
                      line=dict(width=0), layer="below", row=2, col=1)
    net_hover = [f"{d:%Y-%m-%d}<br>net {int(v):+d} (highs {int(h)}, lows {int(lo)})"
                 + (f"<br>regime {g}, three sessions" if g else "")
                 for d, v, h, lo, g in zip(r.net.index, r.net, r.highs, r.lows, r.regime)]
    fig.add_trace(go.Bar(
        x=r.net.index, y=r.net.values,
        marker=dict(color=[colors.bull if v > 0 else colors.bear if v < 0 else colors.dim
                           for v in r.net], line=dict(width=0)),
        opacity=0.85, hovertext=net_hover, hoverinfo="text", showlegend=False),
        row=2, col=1)
    fig.add_hline(y=0, row=2, col=1,
                  line=dict(color=hex_to_rgba(vc.BRIGHTER_TEXT_COLOR, 0.25), width=1))

    fig.update_layout(
        height=FIGURE_PX, paper_bgcolor=background, plot_bgcolor=background,
        margin=dict(l=40, r=12, t=30, b=30), showlegend=False, bargap=0.25,
        font=dict(color=vc.TEXT_COLOR, size=11),
        hoverlabel=dict(bgcolor="#0e1116", font=dict(color=vc.HOVER_TEXT_COLOR)),
        annotations=list(fig.layout.annotations) + [
            dict(text=f"FOMO, {FOMO[1]}: % above 5-day average", xref="paper",
                 yref="paper", x=0, y=1.07, xanchor="left", showarrow=False,
                 font=dict(size=10, color=colors.dim)),
            dict(text="Nasdaq net new 52-week highs", xref="paper", yref="paper",
                 x=0, y=0.40, xanchor="left", showarrow=False,
                 font=dict(size=10, color=colors.dim)),
        ],
    )
    fig.update_xaxes(showgrid=False, zeroline=False, fixedrange=True,
                     tickfont=dict(size=9), range=[x0 - pd.Timedelta(days=1),
                                                    x1 + pd.Timedelta(days=1)])
    fig.update_yaxes(showgrid=False, zeroline=False, fixedrange=True,
                     tickfont=dict(size=9))
    fig.update_yaxes(range=[0, 100], tickvals=[0, 25, 35, 60, 80, 100], row=1, col=1)
    return fig


# ── copy ──────────────────────────────────────────────────────────────────────
def caption(r, awaiting=(), report_date=None):
    """The facts: what is drawn and as of when, or what could not be."""
    if r is None:
        names = ", ".join(awaiting) if awaiting else "the breadth series"
        return f"Breadth panel awaiting series data for: {names}."
    zone = ZONE_LABELS[r.zone].split(",")[0]
    regime = r.regime.iloc[-1]
    trend = (f"net new highs regime {regime} (three sessions)" if regime
             else "net new highs regime unconfirmed")
    stale = ""
    if report_date:
        gap = (pd.Timestamp(report_date) - pd.Timestamp(r.date)).days
        if gap > STALE_AFTER_DAYS:
            stale = f" The panel trails the board: last session {r.date}."
    return (f"Breadth as of the {r.date} session: FOMO ({FOMO[1]}) "
            f"{r.latest:.0f}, {zone}; {trend}. Daily, against the published zones; "
            f"context, not a signal.{stale}")


def help_text():
    return (
        "FOMO is the share of Nasdaq Composite stocks closing above their own 5-day "
        "average, as TradingView publishes it; the rulebook defines it on Nasdaq and its "
        "zones were read off that series, so no other universe is offered. It is drawn "
        "daily because its zone "
        "visits last a session at a time and the board's weekly frame sees one in "
        f"five of them. The bands are the June 2026 Swing Trading Guide's zones: above "
        f"{ind.FOMO_EXHAUSTION_MIN:.0f} buying exhaustion (the crowd chasing, in the "
        f"board's crowded hue), {ind.FOMO_NEUTRAL[0]:.0f} to {ind.FOMO_NEUTRAL[1]:.0f} "
        f"neutral, below {ind.FOMO_FEAR_MAX:.0f} fear (the washed-out side, in the "
        "board's accumulated hue), and recovery, which is a direction rather than a "
        "level: a reading turning up from fear. The guide names no zone between 25 and "
        "35 or 60 and 80, and neither does this panel. Below it, Nasdaq stocks at new "
        "52-week highs minus stocks at new lows, one column per session, with the "
        "background shaded where the last three sessions were all positive or all "
        "negative, the source's own regime rule. That axis is trend confirmation, not "
        "crowding. Nothing here has been through the evaluation ladder; a zone label is "
        "a published cutoff restated, and the two series stay separate on purpose."
    )
