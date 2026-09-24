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

import functools
from dataclasses import dataclass
from typing import Optional

import cotmetrics.utils as utils
import numpy as np
import pandas as pd
from cotmetrics import indicators

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
    awaiting: tuple        # symbols the store could not serve
    date: Optional[str]    # the newest session across the reads


# ── store access (stood in for by tests) ──────────────────────────────────────

def _get_bars(symbol, tier=None):
    import marketdata
    return marketdata.get_bars(symbol) if tier is None else marketdata.get_bars(symbol, tier)


def _last_date(symbol):
    import marketdata
    prov = marketdata.provenance(symbol)
    return None if prov is None else prov.last_date


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

WORDS = {0: "None", 1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six"}


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
    """The six reads' verdicts, in card order, None for a read awaiting data."""
    nasdaq = next((r for r in snapshot.net_highs if r.exchange == "Nasdaq"), None)
    return (
        snapshot.fomo.verdict if snapshot.fomo else None,
        nasdaq.verdict if nasdaq else None,
        snapshot.advance_decline.verdict if snapshot.advance_decline else None,
        snapshot.credit.verdict if snapshot.credit else None,
        snapshot.rotation.verdict if snapshot.rotation else None,
        volume_verdict(snapshot.updown) if snapshot.updown else None,
    )


def headline(snapshot):
    """`(lean, count)`: "Internals lean defensive." and "Two of six positive.".
    Four or more positive reads lean constructive, two or fewer lean defensive,
    three is mixed; a read awaiting data counts on neither side and the count
    says how many were read."""
    verdicts = read_verdicts(snapshot)
    read = [v for v in verdicts if v is not None]
    positives = sum(v == POSITIVE for v in read)
    if not read:
        return "Internals awaiting data.", "No reads available."
    if positives >= 4:
        lean = "Internals lean constructive."
    elif positives <= 2:
        lean = "Internals lean defensive."
    else:
        lean = "Internals are mixed."
    count = f"{WORDS[positives]} of {WORDS[len(read)].lower()} positive."
    return lean, count


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
    `get_bars(symbol, tier=None)`; the module default reads the store."""
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

    dates = [r.date for r in [fomo, advance_decline, credit, rotation,
                              *net_highs, *updown, *assets] if r is not None]
    return Snapshot(
        fomo=fomo,
        net_highs=tuple(net_highs),
        advance_decline=advance_decline,
        credit=credit,
        rotation=rotation,
        updown=tuple(updown),
        assets=tuple(assets),
        awaiting=tuple(dict.fromkeys(awaiting)),
        date=max(dates) if dates else None,
    )


def _all_symbols():
    out = [FOMO_SYMBOL, ADVANCING_SYMBOL, DECLINING_SYMBOL, CREDIT_SYMBOL,
           ROTATION_NUMER, ROTATION_DENOM, *UPDOWN_SYMBOLS, *ASSET_SYMBOLS]
    for _, hi, lo in NET_HIGHS_SYMBOLS:
        out += [hi, lo]
    return tuple(dict.fromkeys(out))


def _stamp():
    """The cache key: the store's last bar date per symbol, None where the store
    holds nothing. Keyed on the data rather than the clock, the tape_context
    convention: a nightly delivery invalidates the entry and nothing else does."""
    stamp = []
    for symbol in _all_symbols():
        try:
            stamp.append(_last_date(symbol))
        except Exception:  # noqa: BLE001 -- absent symbol, unset store, stale checkout
            stamp.append(None)
    return tuple(stamp)


@functools.lru_cache(maxsize=4)
def _snapshot(stamp):
    return build_snapshot()


def snapshot():
    """The current snapshot, cached until the store's dates move."""
    return _snapshot(_stamp())


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
                        ("credit", snap.credit), ("rotation", snap.rotation)):
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


def warm():
    """Fill the cache, for the boot warmer. Swallowing is the warmer's own rule."""
    try:
        snapshot()
    except Exception as e:  # noqa: BLE001
        utils.cot_logger.warning(f"market internals: cache warm failed: {e}")
