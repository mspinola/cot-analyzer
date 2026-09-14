"""Tape context for the crowd board: four ETF ratios scored on the board's own windows.

The board answers "how crowded is Commercial positioning against its trailing range".
These rows put the tape beside it, in the same language: each ratio is scored as a
range index over the same 13, 26 and 52-week windows and full history, so "large
specs at 92 on NQ" and "staples over Nasdaq at 12" read off one scale.

**Orientation is chosen so the board's colour axis keeps its meaning.** On the board a
HIGH cell (the bull hue) is Commercials accumulated, which is the crowd washed out,
and a LOW cell (the bear hue) is the crowd long and crowded. Every ratio here is
written with the defensive or fearful leg on top, so its high end is the fearful,
broad or stressed side and its low end is the crowded, complacent side: staples over
Nasdaq, equal weight over cap weight, Treasuries over junk, front vol over 3-month
vol. Flip a ratio and its colours lie on this board.

**Weekly, at the Tuesday close.** COT is as of Tuesday, so each daily ratio is
collapsed to the last close on or before each Tuesday before it is scored. A daily
window would count sessions where the board counts reports, and the two would not be
the same window.

**Context, not signal, and not a composite.** Nothing here has been through the
evaluation ladder or crucible; the rows say where the tape sits, not what it
predicts. They stay four separate series on purpose: a single "fear" or "FOMO" number
is what crowdmon was, and it closed with no positive result after four pre-registered
tests. The exact breadth reads (net new 52-week highs, share above a moving average)
need a vendor this deployment does not have; equal weight over cap weight is the
proxy, and it is labelled as such. See marketdata's
docs/design/breadth-domain-scoping.md.

**Data arrives on its own schedule.** The legs are yfinance symbols on marketdata's
equities task, delivered by the nightly mirror. A leg the store does not hold yet
yields no row and is named in the caption as awaiting data, never a blank row and
never an error: the board must not depend on the price store to draw positioning.
"""

import functools
from dataclasses import dataclass

import cotmetrics.constants as const
import cotmetrics.utils as utils
import pandas as pd
from cotmetrics import indicators

import components.board_traces as board_traces

# Mirrors exposure.windowed_pct_rank's min_periods for the full-history window: a
# rolling window over the whole series IS the expanding window, and a percentile
# over fewer than two years of weekly reports is not one worth printing.
FULL_HISTORY_MIN_WEEKS = 104

# The board's weekday. COT positioning is as of Tuesday, so that is the close each
# ratio is read at; the bin runs Wednesday to Tuesday and takes the last close in it,
# which is Monday's on a Tuesday holiday.
WEEK_ANCHOR = "W-TUE"


@dataclass(frozen=True)
class ContextRatio:
    key: str
    numer: str
    denom: str
    # marketdata tier. `total` wherever the legs' distributions differ (XLP pays
    # ~2.5%/yr against QQQ's <1%; both bond ETFs distribute monthly), otherwise a
    # split-tier ratio drifts a couple of points a year in the low payer's favour.
    # The vol indices have no distributions, so their tiers are a passthrough.
    tier: str
    label: str
    reads: str
    high: str
    low: str

    @property
    def symbol(self):
        return f"{self.numer}/{self.denom}"


RATIOS = (
    ContextRatio("xlp_qqq", "XLP", "QQQ", "total",
                 "Staples over Nasdaq", "defensive against growth leadership",
                 "staples leading, the defensive side",
                 "Nasdaq leading, growth crowded"),
    ContextRatio("rsp_spy", "RSP", "SPY", "total",
                 "Equal over cap weight", "breadth: how broadly the index is carried",
                 "broad participation",
                 "a few names carrying the index, crowded leadership"),
    ContextRatio("ief_hyg", "IEF", "HYG", "total",
                 "Treasuries over junk", "credit appetite, defensive leg on top",
                 "credit stress, Treasuries bid",
                 "junk bid, credit crowded"),
    ContextRatio("vix_vix3m", "VIX", "VIX3M", "split",
                 "Front over 3-month vol", "vol term structure",
                 "front above 3-month: inversion, fear",
                 "steep contango: calm, complacent"),
)


# Indirection so tests can stand in for the store without a marketdata fixture, and
# so importing this module needs no MARKETDATA_STORE: the page imports it at load.
def _get_bars(symbol, tier):
    import marketdata
    return marketdata.get_bars(symbol, tier)


def _last_date(symbol):
    import marketdata
    return marketdata.provenance(symbol).last_date


def weekly_close(series):
    """A daily series at the board's cadence: the last value on or before each
    Tuesday, indexed by that Tuesday."""
    return series.resample(WEEK_ANCHOR).last().dropna()


def ratio_series(ratio, get_bars=None):
    """The weekly ratio, numerator over denominator, aligned on shared dates."""
    get_bars = get_bars or _get_bars
    numer = get_bars(ratio.numer, ratio.tier)["Close"]
    denom = get_bars(ratio.denom, ratio.tier)["Close"]
    daily = (numer / denom).dropna()
    weekly = weekly_close(daily.astype(float))
    weekly.name = ratio.key
    return weekly


def window_index_frame(series):
    """One series' four window-index columns plus the change column.

    The board's data rule, in one place for both the markets and these rows.
    Windows are `weeks + 1` observations, the same slice `CotIndexer.process_lookback`
    scores the COT index on; full history is the same function over the whole series
    with a two-year floor. Columns keyed by WINDOW_LABELS, plus "move", the
    MOMENTUM_PERIOD-week change of the 52-week index.
    """
    out = pd.DataFrame(index=series.index)
    for weeks, label in zip(board_traces.WINDOW_WEEKS, board_traces.WINDOW_LABELS):
        if weeks is None:
            window = len(series)
            min_periods = min(FULL_HISTORY_MIN_WEEKS, int(series.notna().sum()))
        else:
            window = weeks + 1
            min_periods = window
        out[label] = indicators.calculate_range_index(
            series, window=window, min_periods=min_periods)
    year_label = board_traces.WINDOW_LABELS[2]
    out["move"] = out[year_label] - out[year_label].shift(const.MOMENTUM_PERIOD)
    out.attrs["history_weeks"] = int(series.notna().sum())
    first = series.first_valid_index()
    out.attrs["start"] = first.strftime('%Y-%m-%d') if first is not None else None
    return out


def _stamp(ratio):
    """The cache key: the store's last bar date for each leg, or None when either
    leg is unreadable. Keyed on the data rather than the clock, the `_market_indices`
    convention: a nightly delivery invalidates the entry and nothing else does."""
    try:
        return (_last_date(ratio.numer), _last_date(ratio.denom))
    except Exception:  # noqa: BLE001 -- absent leg, unset store, stale checkout
        return None


@functools.lru_cache(maxsize=32)
def _context_frame(key, stamp):
    """The window-index frame for one ratio, or None. `stamp` is the cache key."""
    if stamp is None or None in stamp:
        return None
    ratio = next(r for r in RATIOS if r.key == key)
    try:
        series = ratio_series(ratio)
    except Exception as e:  # noqa: BLE001 -- one missing leg must not take the board
        utils.cot_logger.warning(f"tape context: no series for {ratio.symbol}: {e}")
        return None
    if series.notna().sum() < 2:
        return None
    frame = window_index_frame(series)
    # The ratio itself, for the hover: the index says where it sits, not what it is.
    frame["value"] = series
    return frame


def _clean(value):
    return None if value is None or value != value else float(value)


def ratio_text(ratio, value):
    """"XLP/QQQ 0.1315": the ratio at the row's date, four significant figures,
    so a reader sees that index 2 is a small ratio near its floor rather than
    a strong one."""
    if value is None:
        return ""
    return f"{ratio.symbol} {value:.4g}"


def context_reads(target_date=None):
    """`(reads, awaiting)`: a MarketRead per ratio the store can serve at the week
    the board shows, and the symbols of the ratios it cannot."""
    reads, awaiting = [], []
    for ratio in RATIOS:
        frame = _context_frame(ratio.key, _stamp(ratio))
        if frame is not None and target_date:
            frame = frame.loc[frame.index <= pd.Timestamp(target_date)]
        if frame is None or frame.empty:
            awaiting.append(ratio.symbol)
            continue
        latest = frame.iloc[-1]
        year_label = board_traces.WINDOW_LABELS[2]
        # The ratio rides in the NAME column, and the symbol column stays empty:
        # "VIX/VIX3M" overruns the width cut for a futures ticker, and a blank
        # ticker slot is itself the mark that this row is not a market.
        reads.append(board_traces.MarketRead(
            asset=f"{ratio.symbol} · {ratio.label}",
            asset_class=board_traces.CONTEXT_CLASS,
            symbol="",
            windows=tuple(_clean(latest[label]) for label in board_traces.WINDOW_LABELS),
            history_weeks=frame.attrs.get("history_weeks"),
            start=frame.attrs.get("start"),
            move=_clean(latest["move"]),
            path=tuple(_clean(v) for v in frame[year_label].tail(52)),
            state=const.SETUP_NONE,
            date=frame.index[-1].strftime('%Y-%m-%d'),
            linked=False,
            measure=f"{ratio.label} index",
            note=f"high: {ratio.high} · low: {ratio.low}",
            value_text=ratio_text(ratio, _clean(latest["value"])),
        ))
    return reads, awaiting


# How far a ratio's last priced week may trail the board's week before the caption
# says so. Two weekly reports: one covers the equities task running after the COT
# release, two is a leg that has stopped updating (Yahoo's ^VIX3M did, 2026-07-17).
STALE_AFTER_DAYS = 14


def stale_notes(reads, report_date, max_days=STALE_AFTER_DAYS):
    """One note per context row priced more than `max_days` before the board's
    week: "VIX/VIX3M last priced 2026-07-14". A row that trails the board is drawn,
    because its windows are still the truth as of ITS date, but a reader comparing
    it with the positioning above has to be told the dates differ."""
    if not report_date:
        return []
    cutoff = pd.Timestamp(report_date) - pd.Timedelta(days=max_days)
    return [f"{read.asset} last priced {read.date}"
            for read in reads if read.date and pd.Timestamp(read.date) < cutoff]


def warm():
    """Fill the ratio cache, for the boot warmer. Cheap, and swallowing is the
    warmer's own rule."""
    for ratio in RATIOS:
        _context_frame(ratio.key, _stamp(ratio))
