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

FOMO_TITLE = "Nasdaq stocks above their 5-day average · FOMO"
FOMO_SUBTITLE = "The share of Nasdaq Composite stocks above their own 5-day average, past year."
FOMO_HOW = (f"Above {indicators.FOMO_EXHAUSTION_MIN:.0f} is stretched: buying exhaustion, "
            f"the end to sell into. Below {indicators.FOMO_FEAR_MAX:.0f} is washed out: "
            "broad pessimism, the buyable end, and a reading climbing back out of it is "
            "recovering. Between the named zones the reading offers no edge either way.")
APPETITE_TITLE = (f"Credit appetite · {mi.APPETITE_JUNK} against {mi.APPETITE_TREASURY}")
APPETITE_SUBTITLE = ("Junk bonds against Treasuries, ranked on their own past year. "
                     "Context: not one of the six reads.")
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
NET_HIGHS_HOW = (f"{indicators.NET_HIGHS_CONFIRM_DAYS} sessions in a row on one side is a "
                 "confirmed trend, marked by the bar at the row's left; anything else is "
                 "mixed. The Nasdaq row is the one counted among the six reads.")
ADVANCE_DECLINE_TITLE = "Nasdaq issues advancing vs declining"
CREDIT_TITLE = (f"High-yield credit · {mi.CREDIT_SYMBOL} against its "
                f"{mi.CREDIT_AVERAGE}-day average")
CREDIT_SUBTITLE = "Junk bonds below their average is risk off. Past quarter."
CREDIT_HOW = ("Dividend-adjusted, because the fund's monthly payout notches the raw "
              "price on each ex-date and a notch reads as a break of the average.")
ROTATION_TITLE = f"Defensive rotation · {mi.ROTATION_NUMER} against {mi.ROTATION_DENOM}"
ROTATION_SUBTITLE = (f"Staples over Nasdaq against the ratio's {mi.ROTATION_AVERAGE}-day "
                     "average. Past quarter.")
ROTATION_HOW = ("The ratio above its average is defensives leading, risk off; below it, "
                "growth is leading. Dividend-adjusted on both legs.")
UPDOWN_TITLE = f"Up / down volume ratio · {mi.UPDOWN_SESSIONS} sessions"
UPDOWN_SUBTITLE = "Volume on up-close days over volume on down-close days."
UPDOWN_HOW = ("Above 1 is net buying (accumulation), below 1 net selling. Both funds on "
              "the same side is the read; a split counts on neither side.")
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
#: Tile tones, the classes the page's stylesheet colours: a read on the constructive
#: side, on the defensive side, or neither.
TONE_CLASS = {mi.POSITIVE: "pos", mi.NEGATIVE: "neg", mi.NEUTRAL: "mid"}


# ── words and numbers ─────────────────────────────────────────────────────────

def signed(value, fmt):
    return ("+" if value >= 0 else "") + format(value, fmt)


def pct(fraction):
    return signed(fraction * 100, ".2f") + "%"


def verdict_color(verdict, colors):
    return {mi.POSITIVE: colors.bull, mi.NEGATIVE: colors.bear}.get(verdict, INK_2)


def headline_color(lean, colors):
    """The colour of the count beside the headline, from which way it leans."""
    if lean.endswith("constructive."):
        return colors.bull
    if lean.endswith("defensive."):
        return colors.bear
    return INK_2


def credit_detail(read):
    return (f"{read.average_sessions}-day avg {read.average:.2f} "
            f"{'rising' if read.rising else 'falling'} · price {pct(read.change)} "
            f"· price only")


def rotation_detail(read):
    side = "above" if read.above else "below"
    return (f"{read.average_sessions}-day avg {read.average:.4f} · ratio {side} by "
            f"{pct(read.gap)}")


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


# ── the readings strip ────────────────────────────────────────────────────────

def _tile(key, label, value, state, verdict, context, date, gauge=None):
    return {"key": key, "label": label, "value": value, "state": state,
            "tone": TONE_CLASS[verdict], "context": context, "date": date, "gauge": gauge}


def tiles(snap):
    """One tile per read the snapshot holds, in card order, then credit appetite. Each:
    the read's own number, the word its cutoff gives it, and one line of context. A
    read awaiting data has no tile; the notes name it."""
    out = []
    if snap.fomo:
        r = snap.fomo
        out.append(_tile("fomo", "Nasdaq FOMO, 5-day", f"{r.value:.1f}", r.label, r.verdict,
                         f"{signed(r.change, '.1f')} on the day", r.date, gauge=r.value))
    nasdaq = next((r for r in snap.net_highs if r.exchange == "Nasdaq"), None)
    if nasdaq:
        out.append(_tile("net_highs", "Nasdaq net new highs", signed(nasdaq.net, "d"),
                         nasdaq.label, nasdaq.verdict,
                         f"{nasdaq.highs} highs, {nasdaq.lows} lows", nasdaq.date))
    if snap.advance_decline:
        r = snap.advance_decline
        out.append(_tile("advance", "Nasdaq issues advancing", f"{r.share:.0%}", r.label,
                         r.verdict, f"{r.advancing:,} up, {r.declining:,} down", r.date))
    if snap.credit:
        r = snap.credit
        out.append(_tile("credit", f"{r.symbol} vs its {r.average_sessions}-day",
                         f"{r.value:.2f}", r.label, r.verdict,
                         f"{abs(r.gap):.2%} {'above' if r.above else 'below'}, average "
                         f"{'rising' if r.rising else 'falling'}", r.date))
    if snap.rotation:
        r = snap.rotation
        out.append(_tile("rotation", f"{r.symbol} vs its {r.average_sessions}-day",
                         f"{r.value:.4f}", r.label, r.verdict,
                         f"{abs(r.gap):.2%} {'above' if r.above else 'below'}, "
                         f"{'defensives' if r.above else 'growth'} leading", r.date))
    if snap.updown:
        first, rest = snap.updown[0], snap.updown[1:]
        others = "".join(f"{r.symbol} {r.ratio:.2f}, " for r in rest)
        out.append(_tile("updown", f"{first.symbol} up/down volume", f"{first.ratio:.2f}",
                         first.label, first.verdict,
                         f"{others}{mi.UPDOWN_SESSIONS} sessions", first.date))
    if snap.appetite:
        r = snap.appetite
        out.append(_tile("appetite", "Credit appetite", f"{r.value:.0f}", r.label, r.tone,
                         "context, not counted", r.date, gauge=r.value))
    return out


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


def trend_chart(read):
    dates, values, averages = read.path
    return line_chart(240, [(INK, 1.5, dates, values),
                            (AVERAGE_COLOR, 2, dates, averages)],
                      decimals=2 if read.key == "credit" else 4)


def spark_points(row, width=SPARK_WIDTH, height=SPARK_HEIGHT, pad=2):
    """The table's sparkline as SVG polyline points: the path scaled into the box."""
    path = row.path
    low, high = min(path), max(path)
    span = (high - low) or 1.0
    step = (width - 2 * pad) / max(len(path) - 1, 1)
    return " ".join(f"{pad + i * step:.1f},{pad + (high - v) / span * (height - 2 * pad):.1f}"
                    for i, v in enumerate(path))
