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
from components import sentiment
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
HISTORY_TITLE = "When the headwinds lined up"
HISTORY_HOW = (
    "One row per headwind, marked on every session it was on, under the price. The "
    "bottom row marks the sessions all five were on at once, and the shading behind the "
    "price is the same count: light for four, darker for all five. The window buttons "
    "zoom every row together and refit the price to what is on screen. The history starts "
    "where the youngest series does (JNK, late 2007). It shows when the headwinds lined "
    "up and nothing more: no claim is made here about what followed, and none has been "
    "tested.")
UNCOUNTED_TITLE = "Not in the count"
UNCOUNTED_SUBTITLE = ("A short-term extreme check, a credit gauge and the volatility term "
                      "structure. None is a trend measure.")
VOLATILITY_TITLE = (f"Volatility · {mi.VOLATILITY_SYMBOL} against "
                    f"{mi.VOLATILITY_TERM_SYMBOL}")
VOLATILITY_SUBTITLE = ("Implied volatility one month out against three months out, past "
                       "year. Context: not one of the headwinds.")
VOLATILITY_HOW = (
    "The VIX prices S&P 500 options about a month out, VIX3M about three. Normally the "
    "longer one is higher. When the VIX rises above it (inverted), the market is paying "
    "more for protection now than later, the shape it takes under stress. The percentile "
    "places today's VIX in its own history since 1990: how unusual the level is, not "
    "whether it is good or bad. Nothing here has been tested as a signal, so it is "
    "drawn and not counted.")
POSITIONING_TITLE = "Sentiment and positioning"
POSITIONING_SUBTITLE = ("Surveys and index futures positioning: each one's own number, and "
                        "its percentile on its full history.")
POSITIONING_HOW = (
    "NAAIM is active managers' average stock exposure; AAII is individual investors, "
    "bulls minus bears and their stocks allocation. The futures tiles are large "
    "speculators' net position in S&P 500 and Nasdaq 100 futures as a percent of open "
    "interest, from the CFTC's weekly report, with commercials' beside it. The badge is "
    "the reading's percentile against every week of its history, and the dot shows the "
    "same thing. Weekly or monthly, so these move slower than the rest of the page. "
    "Context, not counted.")
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


def volatility_chart(read, colors):
    dates, vix, term = read.path
    return line_chart(220, [(INK, 1.5, dates, vix), (AVERAGE_COLOR, 1.5, dates, term)],
                      decimals=1)


def volatility_label(read):
    return "Inverted" if read.inverted else "Normal"


def volatility_status(read):
    """The line under the chart: the two indexes, the shape and how long, the VIX's
    place in its history, and the Nasdaq's own index when the store has it."""
    n = read.streak
    parts = [f"{mi.VOLATILITY_SYMBOL} {read.value:.1f} · "
             f"{mi.VOLATILITY_TERM_SYMBOL} {read.term:.1f} · ratio {read.ratio:.2f}",
             f"{volatility_label(read).lower()} for {n} session{'' if n == 1 else 's'}",
             f"{mi.VOLATILITY_SYMBOL} at its "
             f"{sentiment.percentile_phrase(read.rank[1], read.rank[2])}"]
    if read.nasdaq is not None:
        parts.append(f"{mi.VOLATILITY_NASDAQ_SYMBOL} {read.nasdaq:.1f}")
    return " · ".join(parts)


def positioning_tiles(reads, date_text):
    """ES and NQ large speculators as readings tiles, in the surveys tiles' own shape
    (`sentiment_static._tiles`): the number, its percentile, commercials as context."""
    return [{"key": "cot_" + r.label.split()[0].lower().replace("&", ""),
             "label": f"{r.label}, large speculators",
             "value": f"{r.value:+.1f}%",
             "context": f"net, % of open interest · commercials {r.commercials:+.1f}%",
             "pct": sentiment.percentile_phrase(r.rank[1], r.rank[2]),
             "rank": r.rank, "foot": date_text(r.date)}
            for r in reads]


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


# ── the history strips, as SVG geometry ───────────────────────────────────────

#: Height of the price panel in its own SVG units (the width is one unit a session).
HISTORY_PRICE_UNITS = 100.0
#: Every how many sessions the price line takes a point: a week. Daily points on a
#: plot a few hundred pixels wide are five to a pixel.
HISTORY_PRICE_STEP = 5
HISTORY_TICK_YEARS = 2
#: The most recent sessions the price line keeps every point for, so a zoom to a year
#: or three still draws a daily line and not fifty-two weekly segments.
HISTORY_DAILY_SESSIONS = 3 * 252
#: The card's windows, (label, sessions back from the newest; 0 is everything). Max is
#: what the page opens on and what a reader without JavaScript sees.
HISTORY_WINDOWS = (("1Y", 252), ("3Y", 756), ("5Y", 1260), ("10Y", 2520), ("Max", 0))
HISTORY_DEFAULT_WINDOW = "Max"


def runs(flags):
    """`[(start index, length)]` of each run of true values."""
    out, start = [], None
    for i, flag in enumerate(flags):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            out.append((start, i - start))
            start = None
    if start is not None:
        out.append((start, len(flags) - start))
    return out


def history_price_points(history):
    """The price as polyline points on a log scale: x a session index, y down from the
    top of HISTORY_PRICE_UNITS."""
    import math
    logs = [math.log(v) for v in history.price]
    low, high = min(logs), max(logs)
    span = (high - low) or 1.0
    recent = max(len(logs) - HISTORY_DAILY_SESSIONS, 0)
    picks = list(range(0, recent, HISTORY_PRICE_STEP)) + list(range(recent, len(logs)))
    return " ".join(f"{i},{(high - logs[i]) / span * HISTORY_PRICE_UNITS:.2f}" for i in picks)


def history_year_ticks(history, every=HISTORY_TICK_YEARS):
    """`[(fraction across, "2010")]` at the first session of every `every`th year."""
    out, seen = [], None
    n = len(history.dates)
    for i, date in enumerate(history.dates):
        year = int(date[:4])
        if year != seen:
            seen = year
            if i and year % every == 0:
                out.append((i / n, str(year)))
    return out


def history_month_starts(history):
    """`[[session index, "2026-03"], ...]`: the first session of every month, which is
    all the page's script needs to label any window (months, quarters or years)."""
    out, seen = [], None
    for i, date in enumerate(history.dates):
        if date[:7] != seen:
            seen = date[:7]
            out.append([i, seen])
    return out


def history_subtitle(history):
    return (f"{history.price_symbol} since {history.dates[0][:4]}, daily. Marks show the "
            "sessions each headwind was on.")


def history_summary(history, longest=3):
    """What the bottom row adds up to: how many sessions, in how many stretches, and
    the longest of them. A count of occurrences, not of outcomes."""
    stretches = mi.all_on_stretches(history)
    on = sum(n == history.total for n in history.count)
    total = len(history.count)
    if not on:
        return f"All {history.total} have never been on at once since {history.dates[0][:4]}."
    top = sorted(stretches, key=lambda s: -s[2])[:longest]
    listed = "; ".join(f"{first[:7]} to {last[:7]} ({sessions} sessions)"
                       for first, last, sessions in top)
    return (f"All {history.total} were on at once on {on:,} of {total:,} sessions since "
            f"{history.dates[0][:4]} ({on / total:.0%}), in {len(stretches)} stretches "
            f"(runs within {mi.STRETCH_GAP_SESSIONS} sessions of each other counted as one). "
            f"Longest: {listed}.")


def spark_points(row, width=SPARK_WIDTH, height=SPARK_HEIGHT, pad=2):
    """The table's sparkline as SVG polyline points: the path scaled into the box."""
    path = row.path
    low, high = min(path), max(path)
    span = (high - low) or 1.0
    step = (width - 2 * pad) / max(len(path) - 1, 1)
    return " ".join(f"{pad + i * step:.1f},{pad + (high - v) / span * (height - 2 * pad):.1f}"
                    for i, v in enumerate(path))
