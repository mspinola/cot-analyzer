"""What the market internals page says and draws, apart from how it is laid out.

`components.market_internals_static` lays these out as one HTML file, the page at
internals.bluemagicai.com: the card titles and texts, the number formats, the readings
tiles, and the charts as plain series for TradingView's Lightweight Charts. Nothing in
this module computes a read; every number comes off `components.market_internals`'
snapshot.

**Charts are data, not figures** (since 2026-11-15). Until then these were Plotly
figures drawn as static images; a chart is now a small dict (`line_chart`) the page's
script hands to Lightweight Charts, which gives a crosshair with the value and date
under it for about a hundredth of Plotly's download. No Dash and no Plotly import.
"""
from cotmetrics import indicators

import components.market_internals as mi
from components.sentiment_static import INK, INK_2

AVERAGE_COLOR = "#5B8DD6"

HEADWINDS_TITLE = "Market headwinds"
HEADWINDS_SUBTITLE = ("Five trend measures, each a headwind or not. The count is how many "
                      "are on.")
HEADWINDS_HOW = (
    "Net new highs: Nasdaq plus NYSE 52-week highs minus lows, as a 5-day average; below "
    "zero is a headwind. Up/down volume: over the last 20 sessions, volume on up-close "
    "days over volume on down-close days, for QQQ and for SPY; below 1 is net selling. "
    "JNK: the 20-day EMA of dividend-adjusted high-yield credit; falling is a headwind. "
    "XLP/QQQ: staples over Nasdaq above the ratio's 50-day average is defensives "
    "leading. The definitions are the Caruso Insights member dashboard's. Each card "
    "says what would flip it, how long it has been in its state, and whether it is "
    "better or worse than five sessions ago.")
UNCOUNTED_TITLE = "Not in the count"
UNCOUNTED_SUBTITLE = ("A short-term extreme check and a credit gauge. Neither is a trend "
                      "measure.")
DETAIL_TITLE = "Detail"
DETAIL_SUBTITLE = "The day's breadth by exchange, and the index and asset table."
FOMO_TITLE = "Nasdaq stocks above their 5-day average · FOMO"
FOMO_SUBTITLE = ("The share of Nasdaq Composite stocks above their own 5-day average, past "
                 "year. Not a trend signal.")
FOMO_HOW = (f"Above {indicators.FOMO_EXHAUSTION_MIN:.0f} is stretched: buying exhaustion, "
            f"the end to sell into. Below {indicators.FOMO_FEAR_MAX:.0f} is washed out: "
            "broad pessimism, the buyable end, and a reading climbing back out of it is "
            "recovering. Between the named zones the reading offers no edge either way.")
APPETITE_TITLE = (f"Credit appetite · {mi.APPETITE_JUNK} against {mi.APPETITE_TREASURY}")
APPETITE_SUBTITLE = ("Junk bonds against Treasuries, ranked on their own past year. "
                     "Context: not one of the headwinds.")
APPETITE_HOW = (
    f"The {mi.APPETITE_JUNK}/{mi.APPETITE_TREASURY} ratio's distance from its "
    f"{indicators.CREDIT_AVERAGE_DAYS}-day average, ranked against the previous "
    f"{indicators.CREDIT_RANK_DAYS} sessions, 0 to 100. Under "
    f"{indicators.CREDIT_STRESS_MAX:.0f}, money has rarely preferred Treasuries this "
    f"hard all year (stress); over {indicators.CREDIT_COMFORT_MIN:.0f} is comfort. Dots "
    "are divergence days: Treasuries up and junk down by an unusual margin (risk-off), "
    "or the reverse (risk-on). Both funds price off rates, so on such a day rates did "
    "not move junk: the market's view of credit risk did. It describes credit now, not "
    "next month: tested, a stress reading was not followed by a worse month, which is "
    "why it is drawn here and not counted.")
NET_HIGHS_TITLE = "Net new highs minus new lows"
NET_HIGHS_SUBTITLE = "New 52-week highs less new lows, with the last three sessions."
NET_HIGHS_HOW = (f"Each exchange on its own: {indicators.NET_HIGHS_CONFIRM_DAYS} sessions in "
                 "a row on one side is marked by the bar at the row's left, anything else "
                 "is mixed. The headwind above is a different cut of the same counts: both "
                 "exchanges summed, as a 5-day average.")
ADVANCE_DECLINE_TITLE = "Nasdaq issues advancing vs declining"
ASSETS_TITLE = "Index and asset overview"
ASSET_COLUMNS = ("Symbol", "Last", "Day", "3 mo")
FOMO_ZONES = (f"{indicators.FOMO_EXHAUSTION_MIN:.0f} stretched · "
              f"{indicators.FOMO_FEAR_MAX:.0f} washed out")

FOOTER = ("Breadth counts and shares are TradingView's published daily series, "
          "delivered by the producer box's routine; prices are the equities store. "
          "The credit reads and the XLP/QQQ ratio are dividend-adjusted, because an "
          "ex-dividend notch in a raw price reads as a break of a moving average; "
          "the table and the up/down volume sessions are prices as traded. Up/down "
          "volume covers the last 20 completed sessions. Context, not signal: "
          "nothing on this page has been through the evaluation ladder. Information "
          "only, not investment advice.")

#: Sparkline box, px.
SPARK_WIDTH, SPARK_HEIGHT = 110, 30
# ── words and numbers ─────────────────────────────────────────────────────────

def signed(value, fmt):
    return ("+" if value >= 0 else "") + format(value, fmt)


def pct(fraction):
    return signed(fraction * 100, ".2f") + "%"


def verdict_color(verdict, colors):
    return {mi.POSITIVE: colors.bull, mi.NEGATIVE: colors.bear}.get(verdict, INK_2)


def count_color(snap, colors):
    """The colour of the headline's number: the defensive red when most of the
    headwinds are on, the constructive green when none is, the page's grey between."""
    total = len(snap.headwinds)
    on = sum(h.on for h in snap.headwinds)
    if total and on * 2 > total:
        return colors.bear
    if total and on == 0:
        return colors.bull
    return INK_2


def headwind_badge(headwind):
    return "Headwind" if headwind.on else "Clear"


def headwind_versus(headwind):
    """"Better vs 5d" / "Worse vs 5d", or nothing when it has not moved."""
    if headwind.versus is None:
        return ""
    return f"{headwind.versus.capitalize()} vs {mi.COMPARE_SESSIONS}d"


def headwind_streak(headwind):
    n = headwind.streak
    return f"{headwind_badge(headwind)} for {n} session{'' if n == 1 else 's'}"


def fomo_recent(read, sessions=5):
    """"Last 5 sessions: 70 → 45 → 33 → 24 → 10", the dashboard's line under the gauge."""
    values = read.path[1][-sessions:]
    return (f"Last {len(values)} sessions: " + " → ".join(f"{v:.0f}" for v in values) + ".")


def appetite_status(read, credit=None):
    """The pane's status line: the zone and number, JNK against its average when the
    credit read is on the page, and the divergence days."""
    parts = [f"Credit: {read.label.upper()} {read.value:.0f}"]
    if credit is not None:
        parts.append(f"{credit.symbol} {'above' if credit.above else 'below'} its "
                     f"{credit.average_sessions}-day")
    if read.divergence:
        parts.append(f"{mi.DIVERGENCE_WORDS[read.divergence]} today")
    if read.last_risk_off:
        parts.append(f"last risk-off divergence {read.last_risk_off}")
    return " · ".join(parts)


def net_highs_awaiting(awaiting):
    return [s for _, hi, lo in mi.NET_HIGHS_SYMBOLS for s in (hi, lo) if s in awaiting]


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


# ── charts, as data for Lightweight Charts ────────────────────────────────────

def line_chart(height, series, levels=(), markers=(), value_range=None, decimals=2):
    """One chart: `series` is [(color, width, dates, values)], `levels` horizontal
    lines [(value, color)], `markers` dots on the first series [(date, color)]. A
    missing value (an average before its window fills) is dropped, not drawn at zero."""
    return {
        "height": height, "range": list(value_range) if value_range else None,
        "decimals": decimals,
        "series": [{"color": color, "width": width,
                    "data": [{"time": d, "value": v} for d, v in zip(dates, values)
                             if v is not None and v == v]}
                   for color, width, dates, values in series],
        "levels": [{"value": v, "color": c} for v, c in levels],
        "markers": [{"time": d, "color": c} for d, c in markers],
    }


def fomo_chart(read, colors):
    dates, values = read.path
    # Thinner than the trend charts on purpose: a year of a series this whippy is a
    # dense band, and the zone crossings are what has to stay legible through it.
    return line_chart(220, [(INK, 1, dates, values)],
                      levels=((indicators.FOMO_EXHAUSTION_MIN, colors.bear),
                              (indicators.FOMO_FEAR_MAX, colors.bull)),
                      value_range=(0, 100), decimals=0)


def appetite_chart(read, colors):
    dates, values = read.path
    dot = {"risk_off": colors.bear, "risk_on": colors.bull}
    return line_chart(220, [(INK, 1.5, dates, values)],
                      levels=((indicators.CREDIT_COMFORT_MIN, colors.bull),
                              (indicators.CREDIT_STRESS_MAX, colors.bear)),
                      markers=[(d, dot[kind]) for d, kind in read.markers],
                      value_range=(0, 100), decimals=0)


def headwind_chart(headwind, colors):
    """A headwind's quarter: its series against the level it turns on, or, where the
    read is a series against its own average, the two lines."""
    dates, values, second = headwind.path
    tone = colors.bear if headwind.on else colors.bull
    decimals = 4 if headwind.key == "rotation" else 2 if headwind.key != "net_highs" else 0
    if second is None:
        return line_chart(120, [(INK, 1.5, dates, values)],
                          levels=((headwind.level, tone),), decimals=decimals)
    return line_chart(120, [(INK_2, 1, dates, values), (tone, 2, dates, second)],
                      decimals=decimals)


def spark_points(row, width=SPARK_WIDTH, height=SPARK_HEIGHT, pad=2):
    """The table's sparkline as SVG polyline points: the path scaled into the box."""
    path = row.path
    low, high = min(path), max(path)
    span = (high - low) or 1.0
    step = (width - 2 * pad) / max(len(path) - 1, 1)
    return " ".join(f"{pad + i * step:.1f},{pad + (high - v) / span * (height - 2 * pad):.1f}"
                    for i, v in enumerate(path))
