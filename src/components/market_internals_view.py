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
from datetime import datetime

from cotmetrics import indicators

import components.market_internals as mi
from components import sentiment
from components.sentiment_static import INK, INK_2, SURFACE_COLOR

AVERAGE_COLOR = "#5B8DD6"

HEADWINDS_TITLE = "Market headwinds"
HEADWINDS_SUBTITLE = ("Six trend measures, each a headwind or not. The count is how many "
                      "are on.")
#: A "How to read this" is a string (one paragraph) or a tuple (one point each).
#: Points marked as Caruso's restate the Insights member dashboard's own notes in this
#: page's words; they are that dashboard's reading, not something tested here.
HEADWINDS_HOW = (
    "Each card is one trend measure, a headwind or not, and opens its own How to read "
    "this. The definitions are the Caruso Insights member dashboard's.",
    "Caruso's use of the count: the more headwinds are on, the more defensive to be, "
    "stepping exposure up or down as they change rather than all in or all out.",
    "Every card says what would flip it, how long it has been in its state, and whether "
    "it is better or worse than five sessions ago.",
)
#: Each headwind card's own explanation, by headwind key.
HEADWIND_HOWS = {
    "nasdaq_net_highs": (
        "Nasdaq stocks at a new 52-week high minus those at a new 52-week low, on the "
        "day. Below zero is a headwind.",
        "Caruso's reading: more highs than lows is a healthy market, more lows than "
        "highs a weak one, and the net tends to stay positive while money is flowing in.",
        "The fold under the chart is new lows as a share of Nasdaq issues traded "
        "(advancing plus declining), against the 4% line from the NYSE study cited on "
        "the NYSE card. Here it is a reference: the study was not of the Nasdaq.",
        "A few sessions of net lows can be a false signal. Caruso checks it against "
        "FOMO: net lows with a washed-out FOMO reading is usually a pause, net lows "
        "without one a real breakdown. Three or more sessions of net highs in a row is, "
        "in that reading, a positive trend.",
        "The chart is the last quarter, a column a session, red where it was below zero.",
    ),
    "nyse_net_highs": (
        "The same count for NYSE stocks: new 52-week highs minus new lows on the day. "
        "Below zero is a headwind.",
        "Caruso cites a study by Larry Williams and Ralph Vince on the NYSE: new lows "
        "reaching 4% or more of issues marked a market in serious trouble. The fold "
        "under the chart is that share: new lows over issues advancing plus declining, "
        "with the 4% line dashed. "
        "Unchanged issues are not counted, so it reads slightly high. Context only, "
        "not part of the headwind.",
        "The chart is the last quarter, a column a session, red where it was below zero.",
    ),
    "qqq_updown": (
        "Over the last 20 sessions, QQQ's volume on up-close days divided by its volume "
        "on down-close days.",
        "Below 1.0 is more selling than buying in the Nasdaq 100: the headwind side.",
        "Caruso reads it with net new highs: both on marks a weak market to be careful in.",
    ),
    "spy_updown": (
        "Over the last 20 sessions, SPY's volume on up-close days divided by its volume "
        "on down-close days.",
        "Below 1.0 is more selling than buying in the S&P 500: the headwind side.",
    ),
    "credit": (
        "JNK is a high-yield (junk) bond fund. Junk bonds behave partly like stocks, so "
        "they react quickly when risk rises.",
        "Caruso uses it as a daily stand-in for the Chicago Fed's National Financial "
        "Conditions Index, which comes out weekly and is revised.",
        "Its 20-day EMA falling is conditions tightening, a headwind; rising is easing. "
        "The price is dividend-adjusted, since each monthly payout would otherwise notch "
        "it under its average.",
        "Caruso notes it gives a few more false signals than the other measures.",
    ),
    "rotation": (
        "XLP (consumer staples, the defensive side) divided by QQQ (the Nasdaq 100, "
        "growth), against the ratio's 50-day average.",
        "Above the average is money rotating to defense, a headwind, and it can weigh on "
        "growth stocks while the index still looks fine. Below is risk on.",
        "Caruso notes it can be late, so read it with the others.",
    ),
}
HISTORY_TITLE = "When the headwinds lined up"
HISTORY_HOW = (
    "One row per headwind, marked on every session it was on, under the price. The "
    "bottom row marks the sessions all six were on at once, and the shading behind the "
    "price is the same count: light for five, darker for all six.",
    "Select a row's name to switch it off or on: the bottom row and the shading then "
    "count only the rows that are on, so you can ask when any set of them lined up. "
    "\"Only all on at once\" drops the lighter band.",
    "The bottom row is FOMO, the share of Nasdaq stocks above their 5-day average, on 0 "
    f"to 100. Under {indicators.FOMO_FEAR_MAX:.0f} (the cool band) is washed out, "
    f"{indicators.FOMO_EXHAUSTION_MIN:.0f} and over (the warm band) stretched. On a "
    "window of a year or so it is a daily bar: the high-to-low line, the open a tick "
    "left, the close a tick right. Every window marks the sessions that closed in "
    "either band, and on longer windows, where a daily bar is too thin to read, the "
    "marks are all it draws. It is never in the "
    "count, and starts in late 2018 where its series does.",
    "The window buttons zoom every row together. Point at a session (or tap it) for its "
    "date and the rows that were on. Your window, shading and rows are remembered on "
    "this device.",
    "Caruso's reading: strong uptrends show few headwinds and serious corrections show "
    "them stacked. Expect a few short false signals; the aim is to stay with the major "
    "trend, not to be perfect.",
    "The history starts where the youngest series does (JNK, late 2007). It shows when "
    "the headwinds lined up and nothing more: no claim is made here about what "
    "followed, and none has been tested.",
)
UNCOUNTED_TITLE = "Not in the count"
UNCOUNTED_SUBTITLE = ("A short-term extreme check, a credit gauge, and equity and rates "
                      "volatility. None is a trend measure.")
VOLATILITY_TITLE = (f"Volatility · {mi.VOLATILITY_SYMBOL} against "
                    f"{mi.VOLATILITY_TERM_SYMBOL}")
VOLATILITY_SUBTITLE = ("Equity implied volatility one month out against three months out, "
                       "past year. Context: not one of the headwinds.")
VOLATILITY_HOW = (
    "The VIX prices S&P 500 options about a month out, VIX3M about three. Normally the "
    "longer one is higher. When the VIX rises above it (inverted), the market is paying "
    "more for protection now than later, the shape it takes under stress. The percentile "
    "places today's VIX in its own history since 1990: how unusual the level is, not "
    "whether it is good or bad. Nothing here has been tested as a signal, so it "
    "is drawn and not counted.")
CALENDAR_TITLE = "Macro calendar"
CALENDAR_SUBTITLE = ("This week's and next week's scheduled US releases, Eastern time, "
                     "with the consensus estimate and, once out, the actual.")
CALENDAR_HOW = (
    "Context, not part of the count. Times, estimates and actuals are TradingView's "
    "economic calendar as captured the evening the page was built; an estimate can move "
    "before the release. Marked releases are the ones the calendar itself rates high "
    "impact. Only the releases in the key below are listed: the calendar also carries "
    "Treasury auctions, mortgage rates and weekly energy stocks, left out here. Hover a "
    "name for the previous reading and what it measures. The largest US companies' "
    "earnings sit in the same days, Pre (before the open) or Post (after the close), "
    "from each company's own announcement; a company that has not announced its date "
    "is not shown.")
CALENDAR_HIGH_LABEL = "High impact"

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
                        "report: the commercial index on four lookbacks, and each "
                        "trader group's net position through time.")
POSITIONING_HOW = (
    "Each cell is the commercial index: where commercials' net position sits between "
    "its low (0) and high (100) of that lookback, three months, six, twelve and the "
    "full history (the year beside each name is where it starts). High is commercials "
    "at the long end of their range, low at the short end; reading across a row shows "
    "whether the position is extreme only lately or on every horizon. The change is "
    "the twelve-month index against six weeks ago, and the path is that index over the "
    "last year around its midline. These are the COT Analyzer's own numbers, the "
    "equities rows of its landing page. The charts under the table are the position "
    "itself: each trader group's net in contracts, a column a week for three years, "
    "above zero while the group is net long and below it while net short, in the COT "
    "Analyzer's colours (commercials red, large speculators blue, small speculators "
    "yellow). Within a week the tallest column is at the back and the shortest in "
    "front, so none hides another. "
    "Weekly, as of the Tuesday the report covers. Context, not counted.")
POSITIONING_COLUMNS = ("3M", "6M", "12M", "Full")
POSITIONING_CHANGE = "6W change"
POSITIONING_PATH = "52w path"
ANOMALIES_TITLE = "Market anomalies"
ANOMALIES_SUBTITLE = ("Days a usual relationship between two markets did not hold. To be "
                      "aware of: not counted as a headwind.")
ANOMALIES_HOW = (
    "Each card compares two markets' closes, session by session, over the last "
    f"{mi.ANOMALY_SESSIONS} sessions. A triangle is that market's close, up or down "
    "on the day; a shaded column is an anomaly day.",
    "Red is the pressure side, green the relief side. Point at a column (or tap it) "
    "for its date and both changes.",
    "The three pairs and their colours are the Caruso Insights dashboard's. They are "
    "context only: nothing here has been tested as a signal.",
)
#: Each anomaly card's own explanation, by key. Caruso's notes restated in this page's
#: words and credited, as on the headwind cards.
ANOMALY_HOWS = {
    "vix_spy": (
        "The VIX and the S&P 500 usually move as mirror images: the VIX rises when the "
        "market sells off and falls when it rallies.",
        "An anomaly is a day they close the same way. Both up is red: the VIX climbing "
        "with the market, the pressure Caruso associates with tops. Both down is green: "
        "the VIX easing even as the market falls.",
        "Caruso notes the VIX was climbing alongside the S&P 500 before the 2019, 2020 "
        "and 2024 tops, and treats it as a yellow flag, not a reason to go to cash.",
    ),
    "jnk_tlt": (
        "JNK (high-yield bonds) usually moves with Treasuries like TLT. Both are "
        "dividend-adjusted here, since a payout would otherwise read as a down day.",
        "An anomaly is a day they close opposite ways. TLT up with JNK down is red: "
        "money leaving credit for safety. TLT down with JNK up is green.",
        "Caruso's example: in the April 2025 selloff TLT fell when it would normally "
        "have risen.",
    ),
    "xlp_qqq": (
        "XLP is consumer staples, the defensive side; QQQ is the Nasdaq 100.",
        "Red: both close up but XLP is up more, money favouring defense even on an up "
        "day. Green: both close down but QQQ is down less, growth holding up better "
        "than defense.",
        "The XLP/QQQ headwind above is the trend of this rotation; this card flags it a "
        "day at a time.",
    ),
}
ANOMALY_WORDS = {mi.RED: "Anomaly", mi.GREEN: "Anomaly", None: "Normal"}


def anomaly_badge(read):
    """The card's badge: today's state."""
    return ANOMALY_WORDS[read.flag]


def anomaly_tally(read):
    return f"Last {len(read.sessions)} sessions: {read.red} red · {read.green} green"


def anomaly_tip(read, session):
    """A column's tooltip: its date and both legs' changes."""
    day, first, second, _ = session
    (a, b) = read.labels
    return f"{day_text(day)}: {a} {first * 100:+.2f}%, {b} {second * 100:+.2f}%"


DETAIL_TITLE = "Detail"
DETAIL_SUBTITLE = ("A year of new highs and lows, the day's advancing share, and the "
                   "index and asset table.")
FOMO_TITLE = "Nasdaq stocks above their 5-day average · FOMO"
FOMO_SUBTITLE = ("The share of Nasdaq Composite stocks above their own 5-day average, past "
                 "year. Not a trend signal.")
FOMO_HOW = (
    "The share of Nasdaq stocks above their own 5-day average: short-term impulse "
    "buying and selling. A tactical check at the extremes, not a trend measure, and "
    "never in the count.",
    f"Above {indicators.FOMO_EXHAUSTION_MIN:.0f} is stretched: almost everyone has been "
    "buying, which Caruso treats as a likely short-term trap.",
    f"Below {indicators.FOMO_FEAR_MAX:.0f} is washed out: almost everyone has been "
    "selling, short-term fear. A reading climbing back out of it is recovering.",
    "Caruso uses it as context for net new lows: with fear, usually a pause; without "
    "fear, a real breakdown. Between the named zones it offers no edge either way.",
)
HIGHS_LOWS_TITLE = "New highs vs. new lows"
HIGHS_LOWS_SUBTITLE = ("Nasdaq plus NYSE 52-week highs above the line, lows below it. "
                       "Daily counts, past year.")
ADVANCE_DECLINE_TITLE = "Nasdaq issues advancing vs declining"
ASSETS_TITLE = "Index and asset overview"
ASSET_COLUMNS = ("Symbol", "Last", "Day", "3 mo", "")
FOMO_ZONES = (f"{indicators.FOMO_EXHAUSTION_MIN:.0f} stretched · "
              f"{indicators.FOMO_FEAR_MAX:.0f} washed out")

#: The line that stays on the page; the method sits in a closed fold under it.
DISCLAIMER = ("Context, not signal: nothing on this page has been through the "
              "evaluation ladder. Information only, not investment advice.")
METHOD = ("Breadth counts and shares are TradingView's published daily series, "
          "delivered by the producer box's routine; prices are the equities store. "
          "The credit reads and the XLP/QQQ ratio are dividend-adjusted, because an "
          "ex-dividend notch in a raw price reads as a break of a moving average; "
          "the table and the up/down volume sessions are prices as traded. Up/down "
          "volume covers the last 20 completed sessions.")
METHOD_LABEL = "Sources and method"

#: Sparkline box, px.
SPARK_WIDTH, SPARK_HEIGHT = 110, 30
# ── words and numbers ─────────────────────────────────────────────────────────

def day_text(stamp):
    """Nov 6, 2026 from 2026-11-06: the one date spelling on the page."""
    day = datetime.strptime(stamp[:10], "%Y-%m-%d")
    return f"{day:%b} {day.day}, {day:%Y}"


def month_text(stamp):
    """Jan 2022 from 2022-01-14."""
    return f"{datetime.strptime(stamp[:10], '%Y-%m-%d'):%b %Y}"


def headline_since(snap):
    """"5 of 5 since Nov 12, 2026 (4 before).": how long the count has stood and what it was.
    Read off the history's own count, and only when its newest count is the
    snapshot's: a headwind awaiting data says nothing, and neither does a history that
    ends before the snapshot with a different count (the history can trail the cards
    by a session, and then the day the count moved is not in it). None then, and when
    the count has never been anything else."""
    history = snap.history
    if history is None or not history.count or history.dates[-1] > snap.date:
        return None
    on = sum(h.on for h in snap.headwinds)
    if len(snap.headwinds) != history.total or history.count[-1] != on:
        return None
    start = len(history.count) - 1
    while start and history.count[start - 1] == on:
        start -= 1
    if not start:
        return None
    return (f"{on} of {history.total} since {day_text(history.dates[start])} "
            f"({history.count[start - 1]} before).")


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


def fomo_day(read):
    """The session's range: "Day: open 41.6 · high 41.6 · low 14.4 · close 14.4"."""
    if read.bar is None:
        return ""
    o, h, lo, c = read.bar
    return f"Day: open {o:.1f} · high {h:.1f} · low {lo:.1f} · close {c:.1f}"


def fomo_recent(read, sessions=5):
    """"Last 5 sessions: 70 → 45 → 33 → 24 → 10", the dashboard's line under the gauge."""
    values = read.path[1][-sessions:]
    return (f"Last {len(values)} sessions: " + " → ".join(f"{v:.0f}" for v in values) + ".")


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
    """The paragraph under the cards: the disclaimer, then what is provisional, missing
    or trailing."""
    parts = [DISCLAIMER]
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


def zone(color, shade, dates, values, base=0.0, top=None, width=2):
    """A line for `chart` whose side BELOW `base` is shaded: the headwind's zone. `top`
    shades the side above it too."""
    return {"type": "baseline", "color": color, "shade": shade, "top": top, "base": base,
            "width": width,
            "data": [{"time": d, "value": v} for d, v in zip(dates, values)
                     if v is not None and v == v]}


def area(color, dates, values, fills, width=1):
    """A line for `chart` shaded down to the axis, each session in its own `fills[i]`."""
    return {"type": "area", "color": color, "width": width,
            "data": [{"time": d, "value": v, "topColor": f, "bottomColor": f}
                     for d, v, f in zip(dates, values, fills) if v is not None and v == v]}


def band(dates, values, average, fills):
    """Two series that shade between `values` and `average`: an area down to the
    upper of the two in the session's fill, then one down to the lower in the card's
    own surface, which masks everything under the band. Lightweight Charts has no
    fill between two lines, so the band is drawn by subtraction. No fill where the
    average has not filled yet."""
    pairs = [(d, v, a, f) for d, v, a, f in zip(dates, values, average, fills)
             if a is not None and v is not None and v == v]
    upper = {"type": "area", "color": "transparent", "width": 1,
             "data": [{"time": d, "value": max(v, a), "topColor": f, "bottomColor": f}
                      for d, v, a, f in pairs]}
    lower = {"type": "area", "color": "transparent", "width": 1,
             "data": [{"time": d, "value": min(v, a), "topColor": SURFACE_COLOR,
                       "bottomColor": SURFACE_COLOR} for d, v, a, f in pairs]}
    return upper, lower


def chart(height, series, levels=(), decimals=0):
    """A chart of mixed series (`bars`, `zone`, or a line_chart series dict)."""
    return {"height": height, "range": None, "decimals": decimals, "series": list(series),
            "levels": [{"value": v, "color": c} for v, c in levels], "markers": []}


def highs_lows_chart(breadth, colors):
    """New highs above the line, new lows below it, a bar a session."""
    return chart(240, [bars(colors.bull, breadth.dates, breadth.highs),
                       bars(colors.bear, breadth.dates, [-v for v in breadth.lows])],
                 levels=((0.0, INK_2),))


def fomo_chart(read, colors):
    dates, values = read.path
    # Thinner than the trend charts on purpose: a year of a series this whippy is a
    # dense band, and the zone crossings are what has to stay legible through it.
    return line_chart(220, [(INK, 1, dates, values)],
                      levels=((indicators.FOMO_EXHAUSTION_MIN, colors.bear),
                              (indicators.FOMO_FEAR_MAX, colors.bull)),
                      value_range=(0, 100), decimals=0)


def volatility_chart(read, colors):
    dates, vix, term = read.path
    return line_chart(220, [(INK, 1.5, dates, vix), (AVERAGE_COLOR, 1.5, dates, term)],
                      decimals=1)


BOND_VOLATILITY_TITLE = f"Bond volatility · {mi.VOLATILITY_BOND_SYMBOL}"
BOND_VOLATILITY_SUBTITLE = ("Implied volatility of Treasuries, past year. Context: not "
                            "one of the headwinds.")
BOND_VOLATILITY_HOW = (
    "The MOVE index is the VIX's idea for Treasuries: what the options market is "
    "charging for moves in rates, from options on the 2, 5, 10 and 30-year, with its "
    "own percentile since 2002. It runs on its own scale, about four times the VIX's. "
    "Equity and rates volatility do not always move together, which is the reason to "
    "show both. Not tested as a signal, so it is drawn and not counted.")
BOND_VOLATILITY_NOTE = ("Implied volatility of Treasuries, from options on the 2, 5, 10 and "
                        "30-year. On its own scale, about four times the VIX's.")


def bond_volatility_chart(read):
    """The VIX chart's height: the two sit side by side as cards."""
    dates, values = read.path
    return line_chart(220, [(INK, 1.5, dates, values)], decimals=0)


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


#: The three trader groups, in the palette's slot order (`viz_config.PALETTE_SLOTS`).
POSITIONING_GROUPS = ("Commercials", "Large specs", "Small specs")
#: The app's own bar opacity (`plot_traces.add_trace_to_all`): the columns of the three
#: groups share a week, so each has to let the one behind it show.
POSITIONING_ALPHA = 0.8


def positioning_chart(read, groups):
    """One market's net position by trader group: contracts, a column a week from
    zero, in the COT Analyzer's own colours (`groups` is the palette's first three
    slots).

    The groups share a week, so each week's columns are drawn tallest at the back and
    shortest in front: a series here is a RANK (the week's tallest, its middle, its
    shortest) and each point carries its group's colour. Drawn a group a series, the
    one on top hid the others wherever it was the biggest (small specs over
    commercials on ES)."""
    from components import plot_colors
    dates, values = read.series
    tones = [plot_colors.hex_to_rgba(color, POSITIONING_ALPHA) for color in groups]
    columns = list(zip(tones, (values, *read.others)))
    ranks = [{"type": "histogram", "color": tone, "data": []} for tone, _ in columns]
    for i, day in enumerate(dates):
        week = [(series[i], tone) for tone, series in columns
                if series[i] is not None and series[i] == series[i]]
        # Stable, so groups level on a week keep the palette's order.
        week.sort(key=lambda point: -abs(point[0]))
        for rank, (value, tone) in zip(ranks, week):
            rank["data"].append({"time": day, "value": value, "color": tone})
    return chart(150, ranks, levels=((0.0, INK_2),))


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


#: Opacity of the faint state fill under a headwind card's line.
STATE_FILL = 0.16


LOWS_SHARE_TITLE = "New lows, % of issues traded"


def lows_share_chart(share, colors):
    """A column a session, red at or over the line Caruso cites, grey under it."""
    dates, values = share.path
    cols = bars(INK_2, dates, values)
    for point in cols["data"]:
        if point["value"] >= mi.LOWS_SHARE_LINE:
            point["color"] = colors.bear
    return chart(80, [cols], levels=((mi.LOWS_SHARE_LINE, colors.bear),), decimals=1)


def headwind_chart(headwind, colors):
    """A headwind's quarter: its series against the level it turns on, or, where the
    read is a series against its own average, the two lines. Net new highs, a daily
    count, is columns."""
    dates, values, second = headwind.path
    tone = colors.bear if headwind.on else colors.bull
    if headwind.key.endswith("net_highs"):
        # A daily count reads as columns: one a session from zero, red on the
        # sessions it was a headwind (below the level), green on the others.
        cols = bars(colors.bull, dates, values)
        for point in cols["data"]:
            if point["value"] < headwind.level:
                point["color"] = colors.bear
        return chart(120, [cols], levels=((headwind.level, INK_2),))
    from components import plot_colors
    good = plot_colors.hex_to_rgba(colors.bull, STATE_FILL)
    bad = plot_colors.hex_to_rgba(colors.bear, STATE_FILL)
    if headwind.key.endswith("_updown"):
        # Shaded from the 1.0 line to the ratio: green on the buying side, red below.
        return chart(120, [zone(INK, bad, dates, values, base=headwind.level, top=good,
                                width=1.5)],
                     levels=((headwind.level, tone),), decimals=2)
    if headwind.key in ("credit", "rotation"):
        # Shaded between the line and its average, red on the sessions the headwind was
        # on: JNK's EMA falling, or the ratio above its average.
        if headwind.key == "credit":
            on = [i > 0 and None not in (second[i], second[i - 1])
                  and second[i] < second[i - 1] for i in range(len(second))]
        else:
            on = [a is not None and v > a for v, a in zip(values, second)]
        return chart(120, [*band(dates, values, second, [bad if x else good for x in on]),
                           {"color": INK_2, "width": 1,
                            "data": [{"time": d, "value": v} for d, v in zip(dates, values)]},
                           {"color": tone, "width": 2,
                            "data": [{"time": d, "value": v} for d, v in zip(dates, second)
                                     if v is not None]}],
                     decimals=2 if headwind.key == "credit" else 4)
    decimals = 2
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
HISTORY_WINDOWS = (("3M", 63), ("1Y", 252), ("3Y", 756), ("5Y", 1260), ("10Y", 2520), ("Max", 0))
HISTORY_DEFAULT_WINDOW = "1Y"


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


HISTORY_READ_HINT = "Point at a session, or tap it, for its date and what was on."


def history_day_steps(history):
    """`(first date, "1,1,3,1,...")`: every session's date as the days since the one
    before, which is what lets the page's script name the session under the pointer
    for about two characters a session where the dates themselves would be eleven."""
    days = [datetime.strptime(d, "%Y-%m-%d") for d in history.dates]
    return history.dates[0], ",".join(str((b - a).days) for a, b in zip(days, days[1:]))


def history_month_starts(history):
    """`[[session index, "2026-03"], ...]`: the first session of every month, which is
    all the page's script needs to label any window (months, quarters or years)."""
    out, seen = [], None
    for i, date in enumerate(history.dates):
        if date[:7] != seen:
            seen = date[:7]
            out.append([i, seen])
    return out


HISTORY_FOMO_LABEL = "FOMO, 0 to 100"
#: Height of the FOMO row in its own SVG units: the share itself, 0 to 100.
HISTORY_FOMO_UNITS = 100.0


#: Longest window, in sessions, that draws FOMO's daily bars. Past it a bar is under a
#: pixel wide and the row is a solid band; a coarser bar does not help either, because
#: the share crosses most of its range inside a week, so a weekly or monthly bar is
#: nearly full height every time (tried 2026-11-19). Every window draws the extremes:
#: a mark in the washed-out band for each session that closed under it, and in the
#: stretched band for each that closed in it; past this window they are all it draws.
HISTORY_FOMO_DAILY_UPTO = 400


def history_fomo_path(history):
    """One SVG path of FOMO's daily bars, a session a unit wide on a 0 to 100 scale
    flipped for SVG: the high-to-low line, the open a tick to the left, the close a
    tick to the right."""
    if history.fomo is None:
        return ""
    bars, _ = history.fomo
    top = HISTORY_FOMO_UNITS
    parts = []
    for i, bar in enumerate(bars):
        if bar is None:
            continue
        o, h, lo, c = (round(top - v, 1) for v in bar)
        x = i + 0.5
        parts.append(f"M{x} {h:g}V{lo:g}M{i + 0.15:g} {o:g}H{x}M{x} {c:g}H{i + 0.85:g}")
    return "".join(parts)


def history_fomo_extremes(history):
    """(washed-out flags, stretched flags) per session, from each session's close:
    the long windows' marks."""
    if history.fomo is None:
        return (), ()
    closes = [None if bar is None else bar[3] for bar in history.fomo[0]]
    return (tuple(c is not None and c < indicators.FOMO_FEAR_MAX for c in closes),
            tuple(c is not None and c >= indicators.FOMO_EXHAUSTION_MIN for c in closes))


def history_fomo_closes(history):
    """FOMO's close per session, for the pointer's readout; "" where it was not read."""
    if history.fomo is None:
        return ""
    return ",".join("" if bar is None else f"{bar[3]:.1f}" for bar in history.fomo[0])


def history_subtitle(history):
    return (f"{history.price_symbol} since {history.dates[0][:4]}, daily. Marks show the "
            "sessions each headwind was on. Select a row's name to switch it off or on.")


def history_summary(history, longest=3):
    """What the bottom row adds up to: how many sessions, in how many stretches, and
    the longest of them. A count of occurrences, not of outcomes."""
    stretches = mi.all_on_stretches(history)
    on = sum(n == history.total for n in history.count)
    total = len(history.count)
    if not on:
        return f"All {history.total} have never been on at once since {history.dates[0][:4]}."
    top = sorted(stretches, key=lambda s: -s[2])[:longest]
    listed = "; ".join(f"{month_text(first)} to {month_text(last)} ({sessions} sessions)"
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
