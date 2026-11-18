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
    "price is the same count: light for four, darker for all five. Click a row's name "
    "to switch it off or on: the bottom row and the shading then count only the rows "
    "that are on, so you can ask when any set of them lined up. FOMO is an extra row, "
    "off to begin with and never in the count: switched on, it marks the sessions the "
    "reading was washed out (cool) or stretched (warm), on its own row and over the "
    "price, from late 2018 where its series starts. The window buttons "
    "zoom every row together and refit the price to what is on screen. The history starts "
    "where the youngest series does (JNK, late 2007). It shows when the headwinds lined "
    "up and nothing more: no claim is made here about what followed, and none has been "
    "tested.")
UNCOUNTED_TITLE = "Not in the count"
UNCOUNTED_SUBTITLE = ("A short-term extreme check, a credit gauge and the volatility term "
                      "structure. None is a trend measure.")
VOLATILITY_TITLE = (f"Volatility · {mi.VOLATILITY_SYMBOL} against "
                    f"{mi.VOLATILITY_TERM_SYMBOL}")
VOLATILITY_SUBTITLE = ("Equity implied volatility one month out against three months out, "
                       "and rates volatility under it, past year. Context: not one of "
                       "the headwinds.")
VOLATILITY_HOW = (
    "The VIX prices S&P 500 options about a month out, VIX3M about three. Normally the "
    "longer one is higher. When the VIX rises above it (inverted), the market is paying "
    "more for protection now than later, the shape it takes under stress. The percentile "
    "places today's VIX in its own history since 1990: how unusual the level is, not "
    "whether it is good or bad. Under it, the MOVE index is the same idea for "
    "Treasuries: what the options market is charging for moves in rates, with its own "
    "percentile since 2002. Equity and rates volatility do not always move together, "
    "which is the reason to show both. Nothing here has been tested as a signal, so it "
    "is drawn and not counted.")
SENTIMENT_TITLE = "Sentiment"
SENTIMENT_SUBTITLE = ("Each survey's current reading, and its percentile on three "
                      "histories.")
SENTIMENT_HOW = (
    "NAAIM is active managers' average stock exposure; AAII is individual investors, "
    "bulls minus bears and their stocks allocation. Each has three bars: the newest "
    "reading as a percentile (the number in the dot) of its full history, of the last "
    "three years and of the last year, against a tick at the median. A reading that is "
    "extreme on all three is extreme now, not only against a different era. A dot turns "
    "warm toward a high and cool toward a low: how unusual the reading is, not whether "
    "it is good or bad. Weekly or monthly, so these move slower than the rest of the "
    "page. Context, not counted.")
POSITIONING_TITLE = "Positioning"
POSITIONING_SUBTITLE = ("Commercials in equity index futures, from the CFTC's weekly "
                        "report: the commercial index on four lookbacks, and their net "
                        "position through time.")
POSITIONING_HOW = (
    "Each cell is the commercial index: where commercials' net position sits between "
    "its low (0) and high (100) of that lookback, three months, six, twelve and the "
    "full history (the year beside each name is where it starts). High is commercials "
    "at the long end of their range, low at the short end; reading across a row shows "
    "whether the position is extreme only lately or on every horizon. The change is "
    "the twelve-month index against six weeks ago, and the path is that index over the "
    "last year around its midline. These are the COT Analyzer's own numbers, the "
    "equities rows of its landing page. The charts under the table are the position "
    "itself: commercials' net as a percent of open interest, weekly, three years. "
    "Weekly, as of the Tuesday the report covers. Context, not counted.")
POSITIONING_COLUMNS = ("3M", "6M", "12M", "Full")
POSITIONING_CHANGE = "6W change"
POSITIONING_PATH = "52w path"
DETAIL_TITLE = "Detail"
DETAIL_SUBTITLE = ("A year of new highs and lows, the day's breadth by exchange, and the "
                   "index and asset table.")
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
HIGHS_LOWS_TITLE = "New highs vs. new lows"
HIGHS_LOWS_SUBTITLE = ("Nasdaq plus NYSE 52-week highs above the line, lows below it. "
                       "Daily counts, past year.")
NET_HISTORY_TITLE = "Net new highs"
NET_HISTORY_SUBTITLE = (f"Highs minus lows, daily and as the {mi.NET_HIGHS_AVERAGE}-day "
                        "average the headwind reads. Below zero is the headwind's zone.")
NET_HISTORY_HOW = ("The thin line is each session's highs minus lows; the heavy line is "
                   f"its {mi.NET_HIGHS_AVERAGE}-day average, the number on the Net new "
                   "highs card above. The headwind is on while the average is below "
                   "zero, the shaded side.")
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


PROVISIONAL_TAG = "provisional"
PROVISIONAL_NAMES = {"fomo": "FOMO", "net_highs": "net new highs",
                     "advance_decline": "advancing and declining issues"}


def provisional_tag(snap, key):
    """The word a card prints beside a number that rests on a provisional bar."""
    return PROVISIONAL_TAG if key in snap.provisional else ""


def provisional_note(snap):
    """One sentence naming what is provisional, or nothing."""
    named = [PROVISIONAL_NAMES[k] for k in PROVISIONAL_NAMES if k in snap.provisional]
    if not named:
        return ""
    return ("Provisional: the newest " + ", ".join(named) + " reading"
            + ("s are" if len(named) > 1 else " is")
            + " the evening's value before the vendor has confirmed it. About one in "
            "four is revised, and each is replaced by the settled value when it lands.")


def caption(snap):
    """The paragraph under the cards: the footer, then what is provisional, missing
    or trailing."""
    parts = [FOOTER]
    if provisional_note(snap):
        parts.append(provisional_note(snap))
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


def bars(color, dates, values):
    """A histogram series for `chart`: a bar a session, from zero."""
    return {"type": "histogram", "color": color,
            "data": [{"time": d, "value": v} for d, v in zip(dates, values)
                     if v is not None and v == v]}


def zone(color, shade, dates, values, base=0.0):
    """A line for `chart` whose side BELOW `base` is shaded: the headwind's zone."""
    return {"type": "baseline", "color": color, "shade": shade, "base": base, "width": 2,
            "data": [{"time": d, "value": v} for d, v in zip(dates, values)
                     if v is not None and v == v]}


def chart(height, series, levels=(), decimals=0):
    """A chart of mixed series (`bars`, `zone`, or a line_chart series dict)."""
    return {"height": height, "range": None, "decimals": decimals, "series": list(series),
            "levels": [{"value": v, "color": c} for v, c in levels], "markers": []}


def highs_lows_chart(breadth, colors):
    """New highs above the line, new lows below it, a bar a session."""
    return chart(240, [bars(colors.bull, breadth.dates, breadth.highs),
                       bars(colors.bear, breadth.dates, [-v for v in breadth.lows])],
                 levels=((0.0, INK_2),))


def net_highs_chart(breadth, colors):
    """The daily net, thin, under its 5-day average; under zero the average is in the
    headwind's zone, shaded."""
    from components import plot_colors
    daily = {"color": plot_colors.hex_to_rgba(INK_2, 0.55), "width": 1,
             "data": [{"time": d, "value": v} for d, v in zip(breadth.dates, breadth.net)]}
    return chart(240, [daily, zone(INK, plot_colors.hex_to_rgba(colors.bear, 0.22),
                                   breadth.dates, breadth.average)],
                 levels=((mi.NET_HIGHS_LEVEL, colors.bear),))


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


BOND_VOLATILITY_TITLE = f"Bond volatility · {mi.VOLATILITY_BOND_SYMBOL}"
BOND_VOLATILITY_NOTE = ("Implied volatility of Treasuries, from options on the 2, 5, 10 and "
                        "30-year. On its own scale, about four times the VIX's.")


def bond_volatility_chart(read):
    dates, values = read.path
    return line_chart(140, [(INK, 1.5, dates, values)], decimals=0)


def bond_volatility_status(read):
    return (f"{mi.VOLATILITY_BOND_SYMBOL} {read.value:.1f} · {signed(read.change, '.1f')} on "
            f"the day · at its {sentiment.percentile_phrase(read.rank[1], read.rank[2])}")


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


def _rail(label, position, word):
    """One percentile row: (label, 0-100 position, the number in the dot, tier key)."""
    tier, _ = sentiment.percentile_tier(position, word)
    records = {sentiment.HIGHEST: "hi", sentiment.LOWEST: "lo"}
    shown = records.get(word) or (word[:-2] if word[-2:] in ("st", "nd", "rd", "th") else word)
    return (label, position, shown, tier)


def percentile_blocks(naaim, votes, allocation, date_text):
    """The sentiment blocks: each a label, its current reading and date, and three
    rails, the surveys page's own percentile rows (full history, last three years,
    last year: `naaim_card`, `aaii_votes`, `aaii_allocation`), so the two pages show
    one set of numbers. A part that is None is left out."""
    from components import aaii_votes
    out = []
    if naaim is not None:
        out.append({"key": "naaim", "label": "NAAIM exposure",
                    "value": f"{naaim.recent.iloc[0]:.1f}", "foot": date_text(naaim.last),
                    "rows": [_rail(label, pct, word) for label, pct, word, _ in naaim.latest]})
    if votes is not None:
        newest = votes.recent.iloc[0]
        key = aaii_votes.SPREAD_KEY
        rows = [(f"Since {votes.since:%Y}", votes.spread_latest_pct)] + list(votes.spread_window_pct)
        out.append({"key": "aaii", "label": "AAII bulls minus bears",
                    "value": f"{newest['bullish'] - newest['bearish']:+.1f}",
                    "foot": date_text(votes.last),
                    "rows": [_rail(label, *pcts[key]) for label, pcts in rows if key in pcts]})
    if allocation is not None:
        rows = ([(f"Since {allocation.since:%Y}", allocation.latest_pct)]
                + list(allocation.window_pct))
        out.append({"key": "stocks", "label": "AAII stocks allocation",
                    "value": f"{allocation.recent.iloc[0]['stocks']:.1f}%",
                    "foot": f"{allocation.last:%b %Y}",
                    "rows": [_rail(label, *pcts["stocks"]) for label, pcts in rows
                             if "stocks" in pcts]})
    return out


def positioning_chart(read):
    """One market's commercials through time: net, percent of open interest, against
    zero."""
    dates, values = read.series
    return line_chart(150, [(INK, 1.5, dates, values)], levels=((0.0, INK_2),), decimals=1)


def positioning_spark(read, width=SPARK_WIDTH, height=SPARK_HEIGHT, pad=3):
    """The 52-week path as polyline points on a fixed 0-100 scale (the midline is the
    box's middle), and the end point for its dot."""
    values = [v for v in read.path if v is not None]
    if len(values) < 2:
        return "", None
    step = (width - 2 * pad) / (len(values) - 1)
    pts = [(pad + i * step, pad + (100 - min(100.0, max(0.0, v))) / 100 * (height - 2 * pad))
           for i, v in enumerate(values)]
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts), pts[-1]


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


HISTORY_FOMO_KEY = "fomo"
HISTORY_FOMO_LABEL = (f"FOMO extremes (under {indicators.FOMO_FEAR_MAX:.0f}, over "
                      f"{indicators.FOMO_EXHAUSTION_MIN:.0f})")


def history_subtitle(history):
    return (f"{history.price_symbol} since {history.dates[0][:4]}, daily. Marks show the "
            "sessions each headwind was on. Click a row's name to switch it off or on.")


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
