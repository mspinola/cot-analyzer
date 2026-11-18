"""Market internals: six daily reads of the tape on one page, beside an ETF table.

The page recreates a market-overview view (the Caruso Insights layout of 2026-09-17)
from the two marketdata domains: the breadth series the Windows box pulls through
the TradingView connector (`series` domain, `docs/design/tradingview-breadth-scoping.md`)
and the ETF bars the equities task fetches nightly. Six reads, each one card:

1. FOMO: the share of Nasdaq Composite stocks above their own 5-day average, against
   the SWG zones `cotmetrics.indicators.fomo_zone` encodes.
2. Net new 52-week highs minus lows, Nasdaq and NYSE, with the three-day regime of
   `cotmetrics.indicators.net_highs_regime`.
3. Advancing against declining issues on the Nasdaq, the session's share advancing.
4. Credit: JNK against its 20-day average. Below the average is risk off.
5. Defensive rotation: XLP over QQQ against the ratio's 50-day average. The ratio
   below its average is growth leading, risk on.
6. Up/down volume: over the last 20 sessions, an ETF's volume on up-close days over
   its volume on down-close days, QQQ and SPY.

**The count is of HEADWINDS, five of them, and the definitions are Caruso's own**
(since 2026-11-18). Until then this page counted six "reads", restated from agi; the
Caruso Insights member dashboard ("Market Conditions", data through 2026-11-17) is a
more direct statement of the same measures, and three of ours differed from it. The
five, each either a headwind or not (`headwinds`):

- net new highs: Nasdaq plus NYSE, highs minus lows, 5-day average below zero (this
  page had the Nasdaq alone on a three-in-a-row rule);
- QQQ up/down volume below 1.00, and SPY's, as TWO headwinds (they were one read that
  needed both to agree);
- JNK's 20-day EMA falling, dividend-adjusted (this page had price under its 20-day
  simple average, which is the credit x-ray's status line and still feeds it);
- XLP/QQQ above its 50-day average (unchanged).

FOMO left the count: the dashboard files it as a tactical check on short-term extremes,
"not a trend signal", and counting a washed-out reading as a positive let a selloff
ADD to this page's tally. The advancing share was never on the dashboard and is
context now. The older reads below (1 to 6) still exist as the cards' detail.

A further card is context, not a read: CREDIT APPETITE, the junk-against-Treasuries
gauge of npf's `credit_xray.pine` (`cotmetrics.indicators.credit_appetite`, checked
against the TradingView pane on 2026-11-15). It is drawn and described but stays OUT
of the count of reads, on the evidence in that module's header: a stress reading was
not followed by a worse month in any era tested, so counting it as a negative would
claim something the measurement refused. Its JNK-against-20-day half is read 4.

**Daily, not the board's Tuesday.** Every one of these moves session to session
(`docs/analysis/2026-09-16-fomo-weekly-sampling.md` measured why FOMO cannot be a
weekly row), so this module reads the daily frames and never goes through
`tape_context.weekly_close`.

**agi owns the design of the Caruso reads; this page owns how they are drawn.**
Four of the reads here are the exposure inputs M-106 names, and agi's `/market`
screen is the authority on what each one IS: which series, which adjustment, which
threshold. Where the two differ, agi wins and this module follows. What stays this
page's own is presentation, which is why the credit card draws a price and its
average where agi draws the gap, and why the reads sit in cards rather than a gauge
row. cot-analyzer cannot import agi (it is private, and this repo is public), so the
definitions are restated here with agi's module named beside each one; a restatement
that drifts is a defect in this file, not a difference of opinion.

**Published cutoffs where one exists, labeled inputs where none does.** The FOMO
zones and the three-day net-highs regime are cotmetrics' transcriptions of the SWG.
The advancing-share, up/down-volume and moving-average cutoffs have no source in the
rulebook (`agi/rules/agi_rules.yaml` has no rule for any of the three, checked
2026-09-17); they are module constants named as this page's own, and a label built
from them is a restated cutoff, not a verdict. Context, not signal: nothing here has
been through the evaluation ladder or crucible, and there is no composite number,
only a count of reads on each side.

**Data arrives on its own schedule.** A symbol the store does not hold yet (the
series domain before the box's routine has delivered, DIA / USO / JNK / IBIT before
the equities task has fetched them) yields no card and is named as awaiting data,
never a blank card and never an error. The tape_context rule.
"""

from dataclasses import dataclass
from typing import Optional

import cotmetrics.constants as const
import cotmetrics.utils as utils
import numpy as np
import pandas as pd
from cotmetrics import indicators

from components import sentiment

# ── what is read ──────────────────────────────────────────────────────────────

FOMO_SYMBOL = "NASDAQ_FOMO_5D"
# Exchange -> (new highs, new lows), both legs kept: the legs are read apart.
NET_HIGHS_SYMBOLS = (
    ("Nasdaq", "NASDAQ_NH52W", "NASDAQ_NL52W"),
    ("NYSE", "NYSE_NH52W", "NYSE_NL52W"),
)
ADVANCING_SYMBOL, DECLINING_SYMBOL = "NASDAQ_ADV", "NASDAQ_DEC"
# The credit leg on the TOTAL tier, and this is not a preference. JNK distributes
# about 6.7% a year in monthly instalments of roughly 0.56% of its price, so every
# ex-dividend date puts a notch in the raw price that has nothing to do with credit
# conditions, and a 20-day average test reads that notch as a breakdown. Measured on
# this store: over the last year the raw and adjusted series disagree on the
# above/below verdict on 24.6% of sessions, and over two years the disagreement is
# 98 sessions of raw-says-risk-off against 0 the other way, because a recurring
# downward notch can only push the price under its average. Caruso states the
# adjustment as a condition of the read ("if you don't adjust for dividends it looks
# very different"), and agi's `jnk_leg` preserves the worked example where the raw
# series inverted the July 2026 conclusion. JNK has never made a capital-gains
# distribution, so the total tier IS the dividend-adjusted series.
#
# This file previously read the split tier, on the reasoning that a total-return
# series "would put the monthly distribution into both" the price and the average.
# That is wrong: the notch is a discontinuity in the price which the trailing
# average smooths over 20 sessions, so it opens a gap rather than cancelling.
CREDIT_SYMBOL, CREDIT_TIER, CREDIT_AVERAGE = "JNK", "total", 20
# The ratio on the total tier, the tape_context rule: XLP distributes ~2.5%/yr
# against QQQ's <1%, so a split-tier ratio drifts in QQQ's favor.
ROTATION_NUMER, ROTATION_DENOM, ROTATION_TIER, ROTATION_AVERAGE = "XLP", "QQQ", "total", 50
# Credit appetite: JNK over TLT, both dividend-adjusted (the pane requests both that
# way, and the credit leg above says why it matters for JNK).
APPETITE_JUNK, APPETITE_TREASURY, APPETITE_TIER = "JNK", "TLT", "total"
# Up/down volume and the asset table stay on the split tier: an up session is a
# close above the prior close, and the classification is what a reader would see on
# a chart. Checked rather than assumed, since the credit leg above turned on exactly
# this question: over the last two years an ex-dividend notch flips the up/down
# classification on 0 of QQQ's sessions and 1 of SPY's, against 98 verdict flips on
# JNK. The difference is the distribution rate, under 1% a year here against 6.7%.
UPDOWN_SYMBOLS, UPDOWN_SESSIONS = ("QQQ", "SPY"), 20
ASSET_SYMBOLS = ("QQQ", "SPY", "DIA", "IWM", "USO", "GLD", "TLT", "JNK", "IBIT")
ASSET_TIER = "split"
# Sessions drawn: a quarter for the price paths. The FOMO chart is a YEAR, agi's
# zoom on the same gauge: a month shows the last wiggle, and the zone visits this
# read exists to locate are only legible against a year of them.
PATH_SESSIONS = 63
FOMO_PATH_SESSIONS = 252
APPETITE_PATH_SESSIONS = 252

# ── this page's own cutoffs (no rulebook source; see the module docstring) ─────

#: Share of issues advancing that reads as a broad advance, and its mirror.
ADVANCE_BROAD, ADVANCE_WEAK = 0.60, 0.40
#: Where up/down volume turns from net buying to net selling. ONE, and it is not
#: this page's to tune: agi's `updown_volume` calls it "the ratio's own definition"
#: rather than a threshold, since the ratio is up volume over down volume and one
#: is the level where they balance. This module previously carried an invented dead
#: zone from 0.95 to 1.05, which made a ratio of 1.02 read "Balanced" here and "net
#: buying" there for the same session.
UPDOWN_CENTRE = 1.0
#: Emphasis only, and this page's own: how far past the centre reads as heavy. The
#: pair is symmetric in log terms (1.5 and 1/1.5) and moves no verdict.
UPDOWN_HEAVY_ACCUMULATION, UPDOWN_HEAVY_DISTRIBUTION = 1.5, 1 / 1.5

# ── the five headwinds (the Caruso dashboard's definitions; see the docstring) ──

#: Sessions the net-highs average runs over, and the level under which it is a headwind.
NET_HIGHS_AVERAGE, NET_HIGHS_LEVEL = 5, 0.0
#: JNK's average for the headwind: an EMA whose DIRECTION is the read.
CREDIT_EMA_SPAN = 20
#: "Better / worse vs 5d": the comparison every headwind card carries.
COMPARE_SESSIONS = 5
HEADWIND_KEYS = ("net_highs", "qqq_updown", "spy_updown", "credit", "rotation")
#: The price line over the history strips. QQQ, not the Nasdaq Composite the dashboard
#: draws: the store holds no index series, and QQQ is the Nasdaq this page already reads.
HISTORY_PRICE_SYMBOL = "QQQ"

# ── context beside the count: volatility and positioning ──────────────────────

#: Volatility: the VIX, its three-month counterpart, and the Nasdaq's own index. The
#: read is the TERM STRUCTURE, not a level cutoff: the front month above the
#: three-month is the market paying more for protection now than later, which is the
#: stress shape. No level is called high or low here; the VIX's percentile on its own
#: history says how unusual it is and stops there.
VOLATILITY_SYMBOL, VOLATILITY_TERM_SYMBOL, VOLATILITY_NASDAQ_SYMBOL = "VIX", "VIX3M", "VXN"
VOLATILITY_PATH_SESSIONS = 252
#: Equity index futures positioning, weekly, from the COT index the app is built on:
#: (label, the indexer's market name). Commercials' net as a percent of open interest
#: is the number, the measure the surveys page draws for the S&P 500 and the one the
#: app's COT index is built on; large speculators' is the context.
POSITIONING_MARKETS = (("S&P 500 futures", "S&P 500"), ("Nasdaq 100 futures", "Nasdaq"))
POSITIONING_COLUMN, POSITIONING_SPEC_COLUMN = const.COMM_PCT_OI, const.LARGE_PCT_OI

POSITIVE, NEGATIVE, NEUTRAL = "positive", "negative", "neutral"

FOMO_LABELS = {
    "exhaustion": "Stretched",
    "neutral": "Middle ground",
    "fear": "Washed out",
    "recovery": "Recovering",
    None: "Between zones",
}
# Washed out and recovering count as positive: the SWG reads fear as the buyable
# end and exhaustion as the end to sell into, the contrarian orientation of the
# crowd board. Neutral and the unnamed gaps offer no edge either way.
FOMO_VERDICTS = {
    "exhaustion": NEGATIVE,
    "neutral": NEUTRAL,
    "fear": POSITIVE,
    "recovery": POSITIVE,
    None: NEUTRAL,
}


APPETITE_LABELS = {"stress": "Stress", "neutral": "Neutral", "comfort": "Comfort"}
# The colour of the badge and nothing else: this card is not one of the six reads.
APPETITE_TONES = {"stress": NEGATIVE, "neutral": NEUTRAL, "comfort": POSITIVE}
DIVERGENCE_WORDS = {"risk_off": "risk-off divergence", "risk_on": "risk-on divergence"}


# ── the reads ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FomoRead:
    value: float
    change: float          # on the day
    zone: Optional[str]    # cotmetrics' zone key
    label: str
    verdict: str
    path: tuple            # (date strings, values), the last month
    date: str


@dataclass(frozen=True)
class NetHighsRead:
    exchange: str
    highs: int
    lows: int
    net: int
    last_three: tuple      # signs of the last three sessions, oldest first: -1, 0, 1
    streak: int            # consecutive sessions of the current sign, signed
    regime: Optional[str]  # "up", "down", None
    label: str
    verdict: str
    date: str


@dataclass(frozen=True)
class AdvanceDeclineRead:
    advancing: int
    declining: int
    share: float           # advancing / (advancing + declining)
    label: str
    verdict: str
    date: str


@dataclass(frozen=True)
class TrendRead:
    """A series against its own moving average: a price (credit) or a ratio."""
    key: str
    symbol: str
    value: float
    average: float
    average_sessions: int
    rising: bool           # the average, against its prior session
    above: bool            # the value against the average
    change: float          # the value's day change, as a fraction
    gap: float             # (value - average) / average
    label: str
    verdict: str
    path: tuple            # (date strings, values, averages), the last quarter
    date: str


@dataclass(frozen=True)
class Headwind:
    """One of the five trend measures: a headwind today or not, how far from flipping,
    for how long, and whether it is better or worse than five sessions ago."""
    key: str
    title: str             # "Net new highs"
    subtitle: str          # "Nasdaq + NYSE · 5-day average"
    display: str           # the value as the card prints it: "-131", "0.64", "Falling"
    on: bool               # a headwind today
    flip: str              # what turns it: "Flips at 0 · needs +131"
    streak: int            # sessions in today's state, today included
    versus: Optional[str]  # "better", "worse" or None against COMPARE_SESSIONS ago
    path: tuple            # (date strings, values, second line or None), a quarter
    level: Optional[float]  # the horizontal line a single-series chart turns on
    date: str


@dataclass(frozen=True)
class VolatilityRead:
    """Context: the VIX against its three-month counterpart. Never counted."""
    value: float            # VIX close
    change: float           # on the day, points
    term: float             # VIX3M close
    ratio: float            # VIX / VIX3M
    inverted: bool          # the front above the three-month
    streak: int             # sessions in today's shape
    rank: tuple             # (percentile 1-100, word, first year) of the VIX's history
    nasdaq: Optional[float]  # VXN close, when the store has it
    path: tuple             # (date strings, VIX, VIX3M), the last year
    date: str


@dataclass(frozen=True)
class PositioningRead:
    """Context: one index future's commercials, weekly, on their own history."""
    label: str              # "S&P 500 futures"
    value: float            # commercials' net, percent of open interest
    speculators: float      # large speculators' net, percent of open interest
    rank: tuple             # (percentile 1-100, word, first year) of `value`
    date: str               # the report's date


@dataclass(frozen=True)
class CreditAppetiteRead:
    """Context beside the reads: junk against Treasuries, ranked on its own year."""
    value: float            # 0 to 100
    change: float           # on the day, in points of the gauge
    zone: str               # cotmetrics' zone key
    label: str
    tone: str               # badge colour only; never counted
    deviation: float        # the JNK/TLT ratio against its 20-day average, percent
    divergence: Optional[str]        # today's: "risk_off", "risk_on" or None
    last_risk_off: Optional[str]     # date of the newest risk-off divergence day
    path: tuple             # (date strings, values), the last year
    markers: tuple          # ((date string, "risk_off" | "risk_on"), ...) on the path
    date: str


@dataclass(frozen=True)
class UpDownRead:
    symbol: str
    ratio: float
    up_days: int
    down_days: int
    label: str
    verdict: str
    date: str


@dataclass(frozen=True)
class AssetRow:
    symbol: str
    last: float
    day_change: float      # fraction
    quarter_change: float  # fraction, first to last of the path
    path: tuple            # closes, the last quarter
    date: str


@dataclass(frozen=True)
class Snapshot:
    fomo: Optional[FomoRead]
    net_highs: tuple
    advance_decline: Optional[AdvanceDeclineRead]
    credit: Optional[TrendRead]
    rotation: Optional[TrendRead]
    updown: tuple
    assets: tuple
    headwinds: tuple       # the Headwinds the store could serve, in HEADWIND_KEYS order
    history: Optional["HeadwindHistory"]   # the strips; None unless all five are served
    volatility: Optional[VolatilityRead]
    appetite: Optional[CreditAppetiteRead]
    awaiting: tuple        # symbols the store could not serve
    date: Optional[str]    # the newest session across the reads


# ── store access (stood in for by tests) ──────────────────────────────────────

def _get_bars(symbol, tier=None):
    import marketdata
    return marketdata.get_bars(symbol) if tier is None else marketdata.get_bars(symbol, tier)


def _dates(index):
    return tuple(d.strftime("%Y-%m-%d") for d in index)


def _stamp_of(index):
    return index[-1].strftime("%Y-%m-%d")


def _closes(get_bars, symbol, tier=None):
    """The daily Close series, float, in session order, or None if unreadable."""
    try:
        frame = get_bars(symbol, tier) if tier else get_bars(symbol)
    except Exception as e:  # noqa: BLE001 -- absent symbol, unset store, stale checkout
        utils.cot_logger.warning(f"market internals: no bars for {symbol}: {e}")
        return None
    if frame is None or frame.empty or "Close" not in frame:
        return None
    s = frame["Close"].astype(float).dropna().sort_index()
    return s if len(s) else None


# ── each read, pure over the series it is given ───────────────────────────────

def _sign(x):
    return 0 if x == 0 else (1 if x > 0 else -1)


def signed_streak(net):
    """How many sessions, ending at the last, share the last session's sign:
    +8 for eight positive nets, -3 for three negative. A zero ends the run and a
    last session at zero is a streak of zero."""
    values = [int(v) for v in net]
    if not values:
        return 0
    last = _sign(values[-1])
    if last == 0:
        return 0
    n = 0
    for v in reversed(values):
        if _sign(v) != last:
            break
        n += 1
    return n * last


def fomo_read(series):
    if series is None or len(series) < 2:
        return None
    zones = indicators.fomo_zones(series)
    zone = zones.iloc[-1]
    path = series.tail(FOMO_PATH_SESSIONS)
    return FomoRead(
        value=float(series.iloc[-1]),
        change=float(series.iloc[-1] - series.iloc[-2]),
        zone=zone,
        label=FOMO_LABELS[zone],
        verdict=FOMO_VERDICTS[zone],
        path=(_dates(path.index), tuple(float(v) for v in path)),
        date=_stamp_of(series.index),
    )


def net_highs_read(exchange, highs, lows):
    if highs is None or lows is None:
        return None
    net = (highs - lows).dropna()
    if len(net) < indicators.NET_HIGHS_CONFIRM_DAYS:
        return None
    regime = indicators.net_highs_regime(net).iloc[-1]
    streak = signed_streak(net)
    if regime == "up":
        label, verdict = f"Positive {streak} days", POSITIVE
    elif regime == "down":
        label, verdict = f"Negative {-streak} days", NEGATIVE
    else:
        label, verdict = "Mixed", NEUTRAL
    last = net.index[-1]
    return NetHighsRead(
        exchange=exchange,
        highs=int(highs.loc[last]),
        lows=int(lows.loc[last]),
        net=int(net.iloc[-1]),
        last_three=tuple(_sign(v) for v in net.tail(3)),
        streak=streak,
        regime=regime,
        label=label,
        verdict=verdict,
        date=_stamp_of(net.index),
    )


def advance_decline_read(advancing, declining):
    if advancing is None or declining is None:
        return None
    both = pd.concat([advancing, declining], axis=1, join="inner").dropna()
    if both.empty:
        return None
    adv, dec = (int(v) for v in both.iloc[-1])
    if adv + dec == 0:
        return None
    share = adv / (adv + dec)
    if share >= ADVANCE_BROAD:
        label, verdict = "Broad advance", POSITIVE
    elif share <= ADVANCE_WEAK:
        label, verdict = "Broad decline", NEGATIVE
    else:
        label, verdict = "Mixed", NEUTRAL
    return AdvanceDeclineRead(adv, dec, share, label, verdict, _stamp_of(both.index))


def trend_read(key, symbol, series, sessions, risk_on_above):
    """`series` against its `sessions`-day simple average. `risk_on_above` says
    which side is risk on: a credit price above its average is, a defensive
    ratio above its average is not."""
    if series is None or len(series) < sessions + 1:
        return None
    average = series.rolling(sessions).mean()
    value, avg = float(series.iloc[-1]), float(average.iloc[-1])
    above = value > avg
    risk_on = above if risk_on_above else not above
    tail = series.tail(PATH_SESSIONS)
    return TrendRead(
        key=key,
        symbol=symbol,
        value=value,
        average=avg,
        average_sessions=sessions,
        rising=bool(average.iloc[-1] > average.iloc[-2]),
        above=above,
        change=float(series.iloc[-1] / series.iloc[-2] - 1),
        gap=(value - avg) / avg,
        label="Risk on" if risk_on else "Risk off",
        verdict=POSITIVE if risk_on else NEGATIVE,
        path=(_dates(tail.index),
              tuple(float(v) for v in tail),
              tuple(None if v != v else float(v) for v in average.tail(PATH_SESSIONS))),
        date=_stamp_of(series.index),
    )


# ── the headwinds ─────────────────────────────────────────────────────────────

def _run_length(flags):
    """Sessions, ending at the last, that share the last session's state."""
    values = [bool(v) for v in flags]
    n = 0
    for v in reversed(values):
        if v != values[-1]:
            break
        n += 1
    return n


def _versus(series, higher_is_better):
    """The last value against COMPARE_SESSIONS ago: "better", "worse", or None when
    there is no such session or nothing moved."""
    if len(series) <= COMPARE_SESSIONS:
        return None
    now, then = float(series.iloc[-1]), float(series.iloc[-1 - COMPARE_SESSIONS])
    if now == then or now != now or then != then:
        return None
    return "better" if (now > then) == higher_is_better else "worse"


def _headwind(key, title, subtitle, display, flags, flip, versus, line, second=None,
              level=None):
    tail = line.tail(PATH_SESSIONS)
    other = None if second is None else tuple(
        None if v != v else float(v) for v in second.reindex(tail.index))
    return Headwind(key=key, title=title, subtitle=subtitle, display=display,
                    on=bool(flags.iloc[-1]), flip=flip, streak=_run_length(flags),
                    versus=versus,
                    path=(_dates(tail.index), tuple(float(v) for v in tail), other),
                    level=level, date=_stamp_of(line.index))


def _needs(value, fmt):
    return ("+" if value >= 0 else "") + format(value, fmt)


def _net_highs_average(pairs):
    if not pairs or any(h is None or lo is None for h, lo in pairs):
        return None
    net = sum((h - lo) for h, lo in pairs).dropna()
    return net.rolling(NET_HIGHS_AVERAGE).mean().dropna()


def _credit_ema(series):
    return series.ewm(span=CREDIT_EMA_SPAN, adjust=False).mean()


def _rotation_gap(ratio):
    return ((ratio / ratio.rolling(ROTATION_AVERAGE).mean() - 1) * 100).dropna()


def headwind_flags(pairs, frames, credit, ratio):
    """Each headwind's on/off at every session it can be read, keyed as HEADWIND_KEYS:
    the SAME expressions the cards read their last value from, so the history strip and
    today's card cannot disagree. A headwind the store cannot serve is absent."""
    out = {}
    average = _net_highs_average(pairs)
    if average is not None and len(average):
        out["net_highs"] = average < NET_HIGHS_LEVEL
    for symbol, frame in frames.items():
        if frame is not None and not frame.empty and "Volume" in frame:
            series = updown_ratio_series(frame)
            if len(series):
                out[f"{symbol.lower()}_updown"] = series < UPDOWN_CENTRE
    if credit is not None and len(credit) > CREDIT_EMA_SPAN + 1:
        # The seed sessions are the EMA settling, not a direction: read from the span on.
        out["credit"] = (_credit_ema(credit).diff() < 0).iloc[CREDIT_EMA_SPAN:]
    if ratio is not None and len(ratio) > ROTATION_AVERAGE:
        out["rotation"] = _rotation_gap(ratio) > 0
    return out


#: The history's row labels: each headwind as the condition that turns it on.
HEADWIND_CONDITIONS = {
    "net_highs": "Net new highs below 0",
    "qqq_updown": "QQQ up/down volume below 1",
    "spy_updown": "SPY up/down volume below 1",
    "credit": f"{CREDIT_SYMBOL} {CREDIT_EMA_SPAN} EMA falling",
    "rotation": f"{ROTATION_NUMER}/{ROTATION_DENOM} above its {ROTATION_AVERAGE}-day",
}
#: Sessions of quiet that end a stretch of all-on days: about a month. A stretch is a
#: run of all-on sessions with no gap longer than this, so one selloff that flickers
#: counts once rather than once per flicker.
STRETCH_GAP_SESSIONS = 21


@dataclass(frozen=True)
class HeadwindHistory:
    """Every session ALL the headwinds can be read on, from the first to the last."""
    dates: tuple           # date strings
    price: tuple           # the price line's closes on those sessions
    price_symbol: str
    rows: tuple            # ((key, condition label, tuple of bools), ...)
    count: tuple           # headwinds on, per session
    total: int             # how many headwinds a session can have on


def headwind_history(flags, price, price_symbol):
    """The strips under the price: None unless every headwind in HEADWIND_KEYS has a
    state series, because a count of four possible is not a shorter count of five."""
    if price is None or any(k not in flags for k in HEADWIND_KEYS):
        return None
    table = pd.concat([flags[k].rename(k) for k in HEADWIND_KEYS], axis=1, join="inner")
    table = table.join(price.rename("price"), how="inner").dropna()
    if table.empty:
        return None
    states = table[list(HEADWIND_KEYS)].astype(bool)
    return HeadwindHistory(
        dates=_dates(table.index),
        price=tuple(float(v) for v in table["price"]),
        price_symbol=price_symbol,
        rows=tuple((k, HEADWIND_CONDITIONS[k], tuple(bool(v) for v in states[k]))
                   for k in HEADWIND_KEYS),
        count=tuple(int(v) for v in states.sum(axis=1)),
        total=len(HEADWIND_KEYS),
    )


def all_on_stretches(history, gap=STRETCH_GAP_SESSIONS):
    """Stretches when every headwind was on: `(first date, last date, sessions on)`,
    oldest first. Runs closer together than `gap` sessions are one stretch."""
    out = []
    last_index = None
    for i, n in enumerate(history.count):
        if n < history.total:
            continue
        if last_index is not None and i - last_index <= gap:
            first, _, sessions = out[-1]
            out[-1] = (first, history.dates[i], sessions + 1)
        else:
            out.append((history.dates[i], history.dates[i], 1))
        last_index = i
    return out


def net_highs_headwind(pairs):
    """Both exchanges' highs minus lows, summed, as a 5-day average: below zero is the
    headwind. `pairs` is [(highs, lows), ...]; any missing leg and there is no read,
    because half the sum is a different number, not an approximation of it."""
    average = _net_highs_average(pairs)
    if average is None or len(average) < 2:
        return None
    value = float(average.iloc[-1])
    return _headwind(
        "net_highs", "Net new highs",
        f"Nasdaq + NYSE · {NET_HIGHS_AVERAGE}-day average", f"{value:+.0f}",
        average < NET_HIGHS_LEVEL,
        f"Flips at {NET_HIGHS_LEVEL:.0f} · needs {_needs(NET_HIGHS_LEVEL - value, '.0f')}",
        _versus(average, higher_is_better=True), average, level=NET_HIGHS_LEVEL)


def updown_ratio_series(frame, sessions=UPDOWN_SESSIONS):
    """`updown_read`'s ratio at every session: volume on up-close days over volume on
    down-close days across the trailing `sessions`. NaN where no day closed down."""
    f = frame.sort_index()
    close, volume = f["Close"].astype(float), f["Volume"].astype(float)
    direction = np.sign(close.diff())
    up = volume.where(direction > 0, 0.0).rolling(sessions).sum()
    down = volume.where(direction < 0, 0.0).rolling(sessions).sum()
    # The first row has no prior close to compare with, so the first full window is one
    # session later than the rolling sum's own.
    return (up / down.where(down > 0)).iloc[sessions:].dropna()


def updown_headwind(symbol, frame):
    """Up/down volume under UPDOWN_CENTRE: net selling over the last 20 sessions."""
    if frame is None or frame.empty or "Volume" not in frame:
        return None
    ratio = updown_ratio_series(frame)
    if len(ratio) < 2:
        return None
    value = float(ratio.iloc[-1])
    return _headwind(
        f"{symbol.lower()}_updown", f"{symbol} up/down volume",
        f"{UPDOWN_SESSIONS}-day ratio", f"{value:.2f}", ratio < UPDOWN_CENTRE,
        f"Flips at {UPDOWN_CENTRE:.2f} · needs {_needs(UPDOWN_CENTRE - value, '.2f')}",
        _versus(ratio, higher_is_better=True), ratio, level=UPDOWN_CENTRE)


def credit_headwind(series):
    """JNK's 20-day EMA falling. The EMA turns the session the close crosses it, so the
    level that flips the read is the EMA itself."""
    if series is None or len(series) < CREDIT_EMA_SPAN + 2:
        return None
    ema = _credit_ema(series)
    # The seed sessions are the EMA settling, not a direction: read from the span on.
    falling = (ema.diff() < 0).iloc[CREDIT_EMA_SPAN:]
    on = bool(falling.iloc[-1])
    side = "above" if on else "below"
    return _headwind(
        "credit", f"{CREDIT_SYMBOL} {CREDIT_EMA_SPAN} EMA", "Dividend-adjusted",
        "Falling" if on else "Rising", falling,
        f"Turns {'up' if on else 'down'} on a close {side} {ema.iloc[-1]:.2f} "
        f"(now {series.iloc[-1]:.2f})",
        _versus(ema, higher_is_better=True), series, second=ema)


def rotation_headwind(ratio):
    """Staples over Nasdaq above the ratio's 50-day average: defensives leading."""
    if ratio is None or len(ratio) < ROTATION_AVERAGE + 1:
        return None
    average = ratio.rolling(ROTATION_AVERAGE).mean()
    gap = _rotation_gap(ratio)
    on = bool(gap.iloc[-1] > 0)
    return _headwind(
        "rotation", f"{ROTATION_NUMER}/{ROTATION_DENOM} vs {ROTATION_AVERAGE}-day",
        f"Ratio vs its {ROTATION_AVERAGE}-day average", f"{gap.iloc[-1]:+.1f}%", gap > 0,
        f"Flips on a ratio {'below' if on else 'above'} {average.iloc[-1]:.4f}",
        _versus(gap, higher_is_better=False), ratio, second=average)


def _rank(history, value):
    """`(percentile, word, first year)`, the surveys tiles' tuple, by their own rule."""
    h = history.to_numpy()
    return (sentiment.percentile_of(h, value), sentiment.percentile_word(h, value),
            history.index[0].year)


def volatility_read(vix, term, nasdaq=None):
    """The VIX against VIX3M on their shared sessions, or None without both."""
    if vix is None or term is None:
        return None
    both = pd.concat([vix, term], axis=1, join="inner", keys=["vix", "term"]).dropna()
    if len(both) < 2:
        return None
    ratio = both["vix"] / both["term"]
    tail = both.tail(VOLATILITY_PATH_SESSIONS)
    return VolatilityRead(
        value=float(both["vix"].iloc[-1]),
        change=float(both["vix"].iloc[-1] - both["vix"].iloc[-2]),
        term=float(both["term"].iloc[-1]),
        ratio=float(ratio.iloc[-1]),
        inverted=bool(ratio.iloc[-1] > 1),
        streak=_run_length(ratio > 1),
        rank=_rank(vix, float(both["vix"].iloc[-1])),   # the VIX's own, longer history
        nasdaq=None if nasdaq is None else float(nasdaq.iloc[-1]),
        path=(_dates(tail.index), tuple(float(v) for v in tail["vix"]),
              tuple(float(v) for v in tail["term"])),
        date=_stamp_of(both.index),
    )


def _indexer_positioning(market):
    from cotmetrics.indexer import get_indexer
    return get_indexer().get_symbols_data(market, "52")


def positioning_reads(get_positioning=None):
    """ES and NQ commercials, each against its own history, or () when the COT
    store cannot serve them (a market that fails is left out and logged, never raised:
    this is context on a page whose count does not depend on it)."""
    get_positioning = get_positioning or _indexer_positioning
    out = []
    for label, market in POSITIONING_MARKETS:
        try:
            frame = get_positioning(market)
            comm = pd.to_numeric(frame[POSITIONING_COLUMN], errors="coerce").dropna()
            spec = pd.to_numeric(frame[POSITIONING_SPEC_COLUMN], errors="coerce").dropna()
        except Exception as e:  # noqa: BLE001 -- unset store, unknown market, old cache
            utils.cot_logger.warning(f"market internals: no positioning for {market}: {e}")
            continue
        if spec.empty or comm.empty:
            continue
        comm.index = pd.DatetimeIndex(comm.index)
        comm = comm.sort_index()
        out.append(PositioningRead(label=label, value=float(comm.iloc[-1]),
                                   speculators=float(spec.iloc[-1]),
                                   rank=_rank(comm, float(comm.iloc[-1])),
                                   date=_stamp_of(comm.index)))
    return tuple(out)


def credit_appetite_read(junk, treasuries):
    """The credit x-ray's Glance reading and its divergence days, or None before the
    history exists (the gauge needs its 20-day average and a year of ranks)."""
    if junk is None or treasuries is None:
        return None
    appetite = indicators.credit_appetite(junk, treasuries).dropna()
    if len(appetite) < 2:
        return None
    deviation = indicators.credit_ratio_deviation(junk, treasuries)
    flags = indicators.credit_divergence(junk, treasuries)
    zone = indicators.credit_zone(appetite.iloc[-1])
    path = appetite.tail(APPETITE_PATH_SESSIONS)
    on_path = flags.reindex(path.index).dropna()
    risk_off = flags[flags == "risk_off"]
    last = appetite.index[-1]
    return CreditAppetiteRead(
        value=float(appetite.iloc[-1]),
        change=float(appetite.iloc[-1] - appetite.iloc[-2]),
        zone=zone,
        label=APPETITE_LABELS[zone],
        tone=APPETITE_TONES[zone],
        deviation=float(deviation.loc[last]),
        divergence=flags.loc[last],
        last_risk_off=_stamp_of(risk_off.index) if len(risk_off) else None,
        path=(_dates(path.index), tuple(float(v) for v in path)),
        markers=tuple(zip(_dates(on_path.index), on_path.tolist())),
        date=_stamp_of(appetite.index),
    )


def updown_label(ratio):
    """The badge and the verdict. The verdict turns at UPDOWN_CENTRE, agi's
    definition; the heavy tiers are this page's emphasis and change nothing."""
    if ratio >= UPDOWN_HEAVY_ACCUMULATION:
        return "Heavy accumulation", POSITIVE
    if ratio >= UPDOWN_CENTRE:
        return "Accumulation", POSITIVE
    if ratio <= UPDOWN_HEAVY_DISTRIBUTION:
        return "Heavy distribution", NEGATIVE
    return "Distribution", NEGATIVE


def updown_read(symbol, frame, sessions=UPDOWN_SESSIONS):
    """Volume on up-close sessions over volume on down-close sessions, the last
    `sessions` completed sessions. An up session is a close above the prior close,
    so the window needs one extra bar for the first comparison; unchanged closes
    count on neither side."""
    if frame is None or frame.empty or "Volume" not in frame or len(frame) < sessions + 1:
        return None
    f = frame.sort_index().tail(sessions + 1)
    close, volume = f["Close"].astype(float), f["Volume"].astype(float)
    direction = np.sign(close.diff()).iloc[1:]
    vol = volume.iloc[1:]
    up, down = float(vol[direction > 0].sum()), float(vol[direction < 0].sum())
    if down == 0:
        return None
    ratio = up / down
    label, verdict = updown_label(ratio)
    return UpDownRead(symbol, ratio, int((direction > 0).sum()),
                      int((direction < 0).sum()), label, verdict, _stamp_of(f.index))


def asset_row(symbol, series):
    if series is None or len(series) < 2:
        return None
    path = series.tail(PATH_SESSIONS)
    return AssetRow(
        symbol=symbol,
        last=float(series.iloc[-1]),
        day_change=float(series.iloc[-1] / series.iloc[-2] - 1),
        quarter_change=float(path.iloc[-1] / path.iloc[0] - 1),
        path=tuple(float(v) for v in path),
        date=_stamp_of(series.index),
    )


# ── the headline ──────────────────────────────────────────────────────────────

def volume_verdict(updown):
    """QQQ and SPY as one read: positive when both accumulate, negative when both
    distribute, neutral when they disagree or either is missing."""
    verdicts = {r.verdict for r in updown if r is not None}
    if len(updown) == 2 and all(r is not None for r in updown):
        if verdicts == {POSITIVE}:
            return POSITIVE
        if verdicts == {NEGATIVE}:
            return NEGATIVE
    return NEUTRAL


def read_verdicts(snapshot):
    """The six OLD reads' verdicts, in card order, None for a read awaiting data. No
    longer the count (see `headline`); kept because the cards still colour by them."""
    nasdaq = next((r for r in snapshot.net_highs if r.exchange == "Nasdaq"), None)
    return (
        snapshot.fomo.verdict if snapshot.fomo else None,
        nasdaq.verdict if nasdaq else None,
        snapshot.advance_decline.verdict if snapshot.advance_decline else None,
        snapshot.credit.verdict if snapshot.credit else None,
        snapshot.rotation.verdict if snapshot.rotation else None,
        volume_verdict(snapshot.updown) if snapshot.updown else None,
    )


def has_reads(snapshot):
    """True when the store served anything at all: a headwind, or FOMO."""
    return bool(snapshot.headwinds) or snapshot.fomo is not None


def headline(snapshot):
    """`(count, lean)`: "4 of 5 headwinds on" and one sentence. The count is of the
    headwinds the store could serve; one awaiting data is named in the count's
    denominator shrinking, never guessed at."""
    total = len(snapshot.headwinds)
    if not total:
        return "Headwinds awaiting data", "No trend measure could be read."
    on = sum(h.on for h in snapshot.headwinds)
    count = f"{on} of {total} headwinds on"
    if on == total:
        lean = "Every headwind is on."
    elif on == 0:
        lean = "No headwind is on."
    elif on * 2 > total:
        lean = "Most headwinds are on."
    else:
        lean = "Most headwinds are off."
    return count, lean


def summary_sentences(snapshot):
    """One clause per read, the strip under the headline."""
    out = []
    if snapshot.fomo:
        r = snapshot.fomo
        out.append({
            "exhaustion": "the 5-day reading is stretched, buying exhaustion",
            "fear": "the 5-day reading is washed out, broad pessimism",
            "recovery": "the 5-day reading is climbing out of fear",
            "neutral": "the 5-day reading sits mid-range, offering no edge",
            None: "the 5-day reading sits between zones",
        }[r.zone])
    for r in snapshot.net_highs:
        if r.regime == "up":
            out.append(f"{r.exchange} net new highs have led lows for {r.streak} sessions")
        elif r.regime == "down":
            out.append(f"{r.exchange} net new lows have outnumbered highs for {-r.streak} sessions")
        else:
            out.append(f"{r.exchange} net new highs are mixed")
    if snapshot.advance_decline:
        r = snapshot.advance_decline
        out.append(f"{r.share:.0%} of Nasdaq issues advanced on the day")
    if snapshot.credit:
        r = snapshot.credit
        out.append(f"{r.symbol} is {'above' if r.above else 'below'} its "
                   f"{'rising' if r.rising else 'falling'} {r.average_sessions}-day average")
    if snapshot.rotation:
        r = snapshot.rotation
        out.append(f"{r.symbol} is {'above' if r.above else 'below'} its "
                   f"{r.average_sessions}-day average, "
                   f"{'defensives leading' if r.above else 'growth leading'}")
    for r in snapshot.updown:
        out.append(f"{r.symbol} is under {r.label.lower()} on {UPDOWN_SESSIONS}-day volume")
    return out


# ── assembly ──────────────────────────────────────────────────────────────────

def build_snapshot(get_bars=None):
    """Every read the store can serve, and the symbols it cannot. Pure over
    `get_bars(symbol, tier=None)`; the module default reads the store.

    Uncached: the one caller is the nightly static export
    (scripts/export_internals_page.py). The per-request cache keyed on the store's
    dates went with the app's `/internals` page on 2026-11-11."""
    get_bars = get_bars or _get_bars
    awaiting = []

    def closes(symbol, tier=None):
        s = _closes(get_bars, symbol, tier)
        if s is None:
            awaiting.append(symbol)
        return s

    fomo = fomo_read(closes(FOMO_SYMBOL))

    net_highs = []
    for exchange, hi, lo in NET_HIGHS_SYMBOLS:
        read = net_highs_read(exchange, closes(hi), closes(lo))
        if read is not None:
            net_highs.append(read)

    advance_decline = advance_decline_read(closes(ADVANCING_SYMBOL), closes(DECLINING_SYMBOL))

    credit = trend_read("credit", CREDIT_SYMBOL, closes(CREDIT_SYMBOL, CREDIT_TIER),
                        CREDIT_AVERAGE, risk_on_above=True)

    numer = closes(ROTATION_NUMER, ROTATION_TIER)
    denom = closes(ROTATION_DENOM, ROTATION_TIER)
    ratio = None
    if numer is not None and denom is not None:
        ratio = (numer / denom).dropna()
    rotation = trend_read("rotation", f"{ROTATION_NUMER}/{ROTATION_DENOM}", ratio,
                          ROTATION_AVERAGE, risk_on_above=False)

    updown = []
    for symbol in UPDOWN_SYMBOLS:
        try:
            frame = get_bars(symbol, ASSET_TIER)
        except Exception as e:  # noqa: BLE001 -- same posture as _closes
            utils.cot_logger.warning(f"market internals: no bars for {symbol}: {e}")
            frame = None
        read = updown_read(symbol, frame)
        if read is None:
            awaiting.append(symbol)
        else:
            updown.append(read)

    assets = []
    for symbol in ASSET_SYMBOLS:
        row = asset_row(symbol, closes(symbol, ASSET_TIER))
        if row is not None:
            assets.append(row)

    frames = {}
    for symbol in UPDOWN_SYMBOLS:
        try:
            frames[symbol] = get_bars(symbol, ASSET_TIER)
        except Exception:  # noqa: BLE001 -- already named as awaiting by the loop above
            frames[symbol] = None
    pairs = [(_closes(get_bars, hi), _closes(get_bars, lo)) for _, hi, lo in NET_HIGHS_SYMBOLS]
    built = {"net_highs": net_highs_headwind(pairs),
             "credit": credit_headwind(_closes(get_bars, CREDIT_SYMBOL, CREDIT_TIER)),
             "rotation": rotation_headwind(ratio)}
    for symbol in UPDOWN_SYMBOLS:
        built[f"{symbol.lower()}_updown"] = updown_headwind(symbol, frames[symbol])
    headwinds = tuple(built[k] for k in HEADWIND_KEYS if built.get(k) is not None)
    history = headwind_history(
        headwind_flags(pairs, frames, _closes(get_bars, CREDIT_SYMBOL, CREDIT_TIER), ratio),
        _closes(get_bars, HISTORY_PRICE_SYMBOL, ASSET_TIER), HISTORY_PRICE_SYMBOL)

    # Read with _closes directly: both symbols are already asked for above (JNK as the
    # credit leg, TLT in the table), and a miss there has named them as awaiting.
    appetite = credit_appetite_read(_closes(get_bars, APPETITE_JUNK, APPETITE_TIER),
                                    _closes(get_bars, APPETITE_TREASURY, APPETITE_TIER))

    def quiet(symbol):
        # Context only: a miss here is no card, not a symbol the count is waiting for.
        try:
            return _closes(get_bars, symbol)
        except Exception:  # noqa: BLE001
            return None

    volatility = volatility_read(quiet(VOLATILITY_SYMBOL), quiet(VOLATILITY_TERM_SYMBOL),
                                 quiet(VOLATILITY_NASDAQ_SYMBOL))

    dates = [r.date for r in [fomo, advance_decline, credit, rotation, appetite,
                              *net_highs, *updown, *assets, *headwinds] if r is not None]
    return Snapshot(
        fomo=fomo,
        net_highs=tuple(net_highs),
        advance_decline=advance_decline,
        credit=credit,
        rotation=rotation,
        updown=tuple(updown),
        assets=tuple(assets),
        headwinds=headwinds,
        history=history,
        volatility=volatility,
        appetite=appetite,
        awaiting=tuple(dict.fromkeys(awaiting)),
        date=max(dates) if dates else None,
    )


def _all_symbols():
    out = [FOMO_SYMBOL, ADVANCING_SYMBOL, DECLINING_SYMBOL, CREDIT_SYMBOL,
           ROTATION_NUMER, ROTATION_DENOM, *UPDOWN_SYMBOLS, *ASSET_SYMBOLS]
    for _, hi, lo in NET_HIGHS_SYMBOLS:
        out += [hi, lo]
    return tuple(dict.fromkeys(out))


def stale_notes(snap, max_days=3):
    """Reads priced more than `max_days` before the newest read, named: a series
    whose delivery stopped is drawn (its reading was true as of its date) but a
    reader comparing cards has to be told the dates differ."""
    if snap.date is None:
        return []
    cutoff = pd.Timestamp(snap.date) - pd.Timedelta(days=max_days)
    named = []
    for label, read in (("FOMO", snap.fomo),
                        ("advancing / declining", snap.advance_decline),
                        ("credit", snap.credit), ("rotation", snap.rotation),
                        ("credit appetite", snap.appetite),
                        ("volatility", snap.volatility)):
        if read is not None and pd.Timestamp(read.date) < cutoff:
            named.append(f"{label} last read {read.date}")
    for read in snap.net_highs:
        if pd.Timestamp(read.date) < cutoff:
            named.append(f"{read.exchange} net new highs last read {read.date}")
    for read in snap.updown:
        if pd.Timestamp(read.date) < cutoff:
            named.append(f"{read.symbol} volume last read {read.date}")
    for row in snap.assets:
        if pd.Timestamp(row.date) < cutoff:
            named.append(f"{row.symbol} last priced {row.date}")
    return named

