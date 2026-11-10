"""Stated sentiment against price: NAAIM and AAII, weekly. LOCAL ONLY in the app;
published as a static copy at surveys.bluemagicai.com (`sentiment_static`).

Two views of one weekly frame, and a caption:

1. **Sentiment against price.** SPY (total return) above one panel carrying NAAIM and
   AAII bulls minus bears, each drawn as a range index: its 2-week average placed
   between its own lowest (0) and highest (100) reading of the trailing lookback (three
   years by default, one on the toggle). The 20 and 80 zones stay fixed on the chart and
   the lines move between them. Behind both panels, SPY's drawdown bands: weeks with SPY
   5-10%, 10-20% or 20% or more below its highest close so far, amber, orange and red,
   each stronger than the last, with a legend key per depth. They tie the
   sentiment lines to price without a third line, and they are point-in-time (each
   week's depth is measured from the high up to that week). The zones are dotted lines
   rather than fills so the bands own the background. Chosen 2026-11-05 over shading by
   the trailing 13-week return (flickers week to week) and a SPY-return index line (a
   third line, and its gap from NAAIM is an untested quantity). Bands describe what price
   had done; nothing here is shaded by what followed. The depths took separate hues on
   2026-11-06: one hue at three opacities left the faint and the dark bands easy to read
   the wrong way round on a dark page, and nothing on the chart said which was which.
   Behind each line, faint dots: the week's raw reading placed on the line's own scale
   (`on_index_scale`), so the newest survey shows unlagged; the latest one is the large marker,
   and the panel title reads it out as the survey published it (see "The real-time
   reading", below).

2. **Weekly columns.** Columns, drawn the way the COT net-positioning chart draws its
   groups (own palette colour, 0.8 opacity, a hairline outline in the same colour, a 0.2
   bar gap): SPY's trailing 13-week return on top, then NAAIM minus its trailing
   average, AAII bulls minus bears as read, and S&P 500 commercials' net position as a
   percent of open interest (the COT chart's column, colour and units) at the bottom. SPY's panel (added 2026-11-06) is the
   price the surveys follow, at the horizon measured to track NAAIM's level best (0.62,
   PRICE_NOTE), grey above zero (SPY's own ink on the price chart, and not the board's
   bull green, which is AAII's colour two panels down) and bear red below; it ends on
   its own week, so it is point-in-time like everything else here. A 1-week change was the other choice and
   is noise at this scale (260 columns on the opening five years). NAAIM needs the
   reference because its readings are almost always positive and its normal level has
   drifted (yearly means about 30 in 2008, 84 in 2024), so against zero it draws as a
   solid block and against one full-history average (67.5) it reads with hindsight and
   leaves recent years one-sided. The trailing average is over the prior 52 x lookback
   weeks, the current week excluded, so each column compares a week only with what came
   before it, on the same window as the indexes. AAII already sits around zero and is
   drawn as read.

Both open on the last five years and carry the app's year buttons (1Y to 15Y and Max),
led by 3M and 6M for the recent weeks.
They re-fit their axes to each window through the shared clientside handler: the SPY
price panel, and all three column panels with zero kept in view (`refit.zero`); the
index panel stays pinned to 0-100. The column axes open fitted to the opening window,
since a full-history axis (2008 and 2020 put SPY's at -40%) squashed the recent years.

**No COT pairing, on purpose.** An earlier version drew each sentiment series beside an
S&P 500 COT group (NAAIM with large specs, AAII with non-reportables) with the
words-minus-money gap under each, and a quadrant of NAAIM's index against the
speculators'. Both were removed 2026-11-05 after measuring that the pairs do not move
together (`scripts/measure_sentiment_comovement.py`, 1,047 joint weeks, 2006-07 to
2026-08, live stores, real params; the index figures are on the 4-week average the page
used then):

| | level | 1w change | 4w change, non-overlapping (n=261) | 13w change | 3Y index |
|---|---|---|---|---|---|
| NAAIM, large specs | 0.17 | -0.07 | -0.04 | 0.02 | 0.44 |
| NAAIM, commercials | -0.12 | 0.03 | -0.01 | -0.08 | -0.47 |
| AAII, non-reportables | 0.17 | -0.05 | 0.04 | 0.14 | 0.35 |

The index-level correlation is the slow-drift artifact cotmetrics names for positioning
levels (large-spec net has a lag-1 autocorrelation of 0.96): two slow series rescaled
into one trailing window share long swings by chance. On changes nothing is there, so
the gap between two such indexes is close to the difference of two unrelated numbers:
on the 3-year index, SPY's trailing 13-week return explains 10% of NAAIM's gap, the
large-spec index alone 32%, and the two lines together are the rest of what the
eye reads (the gap correlates 0.49 with NAAIM's index and 0.57 with the inverted
speculators'). The quadrant placed the same two independent readings against each
other. Commercials are no alternative: in ES they nearly mirror large specs (-0.90 in
levels, -0.93 in 4-week changes). And the npf study found NAAIM added nothing once
speculator positioning was known, so the pairing had no tested meaning either.

What the sentiment series do follow is price, which is why view 1 sets them under SPY:
their 4-week changes correlate with SPY's 4-week return at 0.56 (NAAIM) and 0.47 (AAII),
against -0.11 for large specs, and NAAIM's level correlates 0.62 with SPY's trailing
13-week return, highest for returns ending 0 to 2 weeks before the survey. COT
positioning has its own pages.

**Provisional NAAIM weeks.** NAAIM's official series (the free table, three months
behind, plus the paid history file) ends a quarter back. Since 2026-11-06 the weeks
after its end come from marketdata's NAAIM_EXPOSURE_PROVISIONAL, a hand-kept series:
the first backfill read off a StockCharts chart by bar height (median 0.19 points from
NAAIM's values over 249 shared weeks; StockCharts itself differs on a few weeks), then
one exact label a week. They extend the official series, never stand in for it, and are
drawn apart everywhere they appear: a dotted index segment, a hollow latest marker,
faint columns, and "provisional" beside every date they set. marketdata drops each week
as NAAIM publishes it, so the dotted stretch shortens on its own.

**Provisional AAII weeks.** AAII's official legs are only as current as the member
spreadsheet last downloaded by hand, while AAII's public results page shows each week
the day it is published. Since 2026-11-09 the weeks after the spreadsheet's end come
from marketdata's AAII_BULLISH_PROVISIONAL and AAII_BEARISH_PROVISIONAL, typed from
that page one row a week (its rounded percentages, so bulls minus bears is within 0.1
point of the spreadsheet's). The page dates a survey by its Wednesday; marketdata
stores it on the Thursday after, where the spreadsheet reports it (21 of 21 shared
weeks). Spliced on and drawn exactly as NAAIM's provisional weeks are, and dropped by
marketdata once a newer spreadsheet is built.

**The commercials row is a contrast, not a pairing.** Added 2026-11-06 at the user's
request, as the bottom row of view 2: S&P 500 commercials (the group npf reads for
equities) under the three rows that move with price. It is there to show what the money
side does NOT do: commercials' 4-week change correlates +0.07 with SPY's 4-week return,
against +0.56 and +0.47 for the surveys (same script, same 1,047 weeks). Nothing on the
page relates the row to the surveys: no gap, no shared index, no shared axis. Each
report sits on the Friday of its week, the day the CFTC publishes it, so it is dated
like the surveys and uses nothing later.

**The lookback is a toggle, 3Y by default, 1Y beside it.** Measured 2026-11-05 on the
store, for NAAIM and AAII on their 2-week averages:

| | 1 year | 3 years |
|---|---|---|
| weeks in a zone (at or past 20/80) | 34-43% | 21-36% |
| weeks pinned at 0 or 100 | 7-8% | 2% |
| weeks an old high or low leaves the window, moving the scale | 7-8% | 2% |

Three years is the default because the zones stay rare, the scale stays put (the point
of moving off percentiles), and it is the window the pre-registered study ranked on.
One year is there because it turns sooner after a regime change and matches the 52-week
COT index the rest of the app shows. Nobody picked either by what followed: choosing a
lookback on forward returns would make this monitor an untested search.

**Why a range index and not a percentile.** A percentile view needs a moving band to
show "extreme", so the band and the line move together and the eye has to track both.
The range index is the COT index's own form, so the extremes are the fixed 0 and 100
and the zones are fixed lines. What it gives up: the scale is still a trailing window,
so when an old high or low rolls out of the window the scale shifts under the
line. That is the trap the crowd board's docstring names for every trailing window, and
the caption says it too.

**Why local only.** NAAIM's history is a paid file and AAII's a member download; see
`local_pages`. Nothing here is drawn on the deployed site.

**Arithmetic.** This repo computes no metrics of its own. The index is
`cotmetrics.indicators.calculate_range_index` over 52 x years + 1 weekly observations
(157 at three years, 53 at one: the `weeks + 1` convention every board column uses).
AAII is bulls minus bears in percentage points, a difference of two stored series. The
2-week average on the two sentiment series is display smoothing: both swing hard week
to week, and twenty years of raw weekly readings draw as a solid block.

**Why two weeks.** Chosen by eye on 2026-11-05 between raw, 2 and 4 weeks, trading lag
against a readable line; nothing was ranked on what followed. Measured on the 3-year
index (`scripts/measure_sentiment_comovement.py`, smoothing table):

| | raw | 2-week | 4-week |
|---|---|---|---|
| NAAIM median weekly move, index points | 7.7 | 5.4 | 4.3 |
| NAAIM direction changes a year | 30.0 | 18.9 | 14.7 |
| AAII median weekly move | 10.9 | 7.2 | 4.9 |
| AAII direction changes a year | 30.5 | 20.9 | 17.1 |
| mean lag behind the week's reading | 0 | 0.5 weeks | 1.5 weeks |

Two weeks takes out about a third of the raw series' direction changes for a
half-week of lag; four took out about half for a week and a half. NAAIM's correlation
with SPY's trailing 13-week return is 0.62-0.63 under all three, so the choice changes
how the line reads, not what it carries. AAII stays the busier line.

**The real-time reading: a short zoom and the raw week, not a short window.** Added
2026-11-09. A recent view could have been a third, shorter index window, gently
smoothed. Measured instead (`scripts/measure_short_lookback.py`, live stores, 2008 on,
the index of the 2-week average as drawn; "pinned" is at or below 5 or at or above 95):

| window | NAAIM pinned | NAAIM mean weekly move | AAII pinned | AAII mean weekly move |
|---|---|---|---|---|
| 13 weeks | 35% | 14.3 | 29% | 17.1 |
| 26 weeks | 23% | 11.4 | 18% | 13.7 |
| 1 year | 14% | 9.1 | 12% | 11.1 |
| 3 years | 6% | 7.0 | 4% | 8.5 |

A short window loses its anchor: on the day this was measured NAAIM read 78.6, which
the 13- and 26-week indexes both called 0 (managers had sat above 80 all quarter) and
the 3-year index called 64. And it is twice as jumpy, so smoothing it calm enough to
read would add back the lag a recent view exists to remove. So the window stays 1 or 3
years and recency comes from two other places: 3M and 6M zoom buttons (a zoom changes
what is shown, not what 0 and 100 mean), and the raw dots with the latest one read
out in the title, which show a new survey the week it lands rather than half a week
later through the average.

**Dating.** Every observation is keyed to the Friday of the week it falls in, because
each is public by that Friday's close: NAAIM surveys on Wednesday and publishes that
week, AAII reports on Thursday, SPY closes on Friday.

**The forward-return study is a caption, not a chart.** It was measured once under a
pre-registration in npf (2026-11-05), on weekly percentile ranks rather than this index:
a marginal lean on NAAIM's level and a genuine null once positioning is known. Colouring
these charts by what followed would turn a monitor into a backtest, and the app's rule
is context, not signal.

**The store lags NAAIM by about a quarter.** Its free table runs three months behind and
current readings are subscriber-only, so the NAAIM line ends months before the other
two. The caption names each series' last date.
"""
import functools
from dataclasses import dataclass, field

import cotmetrics.constants as const
import cotmetrics.indicators as indicators
import cotmetrics.utils as utils
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import viz_constants as vc
from components import exposure_traces
from components.plot_colors import hex_to_rgba

NAAIM = "NAAIM_EXPOSURE"
#: The weeks after the official series' end, hand-kept and NOT official (marketdata's
#: NAAIM_EXPOSURE_PROVISIONAL). Spliced on after the official end and drawn apart:
#: dashed index line, faint columns, "provisional" beside every date it sets.
NAAIM_PROVISIONAL = "NAAIM_EXPOSURE_PROVISIONAL"
#: How much fainter a provisional NAAIM column draws than an official one.
PROVISIONAL_OPACITY = 0.4
AAII_BULL = "AAII_BULLISH"
AAII_BEAR = "AAII_BEARISH"
#: AAII's weeks after the member spreadsheet's end, typed from the public results page
#: and NOT official (marketdata's AAII_*_PROVISIONAL). Spliced and drawn as NAAIM's are.
AAII_BULL_PROVISIONAL = "AAII_BULLISH_PROVISIONAL"
AAII_BEAR_PROVISIONAL = "AAII_BEARISH_PROVISIONAL"
PRICE = "SPY"
PRICE_TIER = "total"
#: The contrast row: S&P 500 commercials' net as a percent of open interest, the column,
#: colour slot and units the COT net-positioning chart draws (plot_traces, COMM_LABEL).
POSITIONING_MARKET = "S&P 500"
COMM_COLUMN = const.COMM_PCT_OI
COMM_SLOT = 0
COMM_AWAITING = f"{POSITIONING_MARKET} commercials"

LOOKBACK_YEARS = (1, 3)           # the index toggle
DEFAULT_LOOKBACK = 3
INDEX_WEEKS = 52 * DEFAULT_LOOKBACK
INDEX_WINDOW = INDEX_WEEKS + 1    # observations, the board's weeks + 1 convention
_YEARS_WORD = {1: "year", 3: "three years"}
AVERAGE_WEEKS = 2
LO, HI = 20.0, 80.0               # fixed zones on the 0-100 index
OPEN_YEARS = 5                    # the time views open on this many trailing years
#: Zoom buttons ahead of the app's year ladder, for the recent weeks. A zoom, not a
#: window: the index keeps its 1- or 3-year scale ("The real-time reading").
RANGE_MONTHS = (3, 6)
#: Room after the last week. Small, because the zoom buttons count back from the axis's
#: right edge, not from the data: 30 days left a third of the 3M view empty. The latest
#: marker draws past the plot edge (cliponaxis=False), so it needs no more than this.
OPEN_PAD_DAYS = 7
#: The raw weekly dots behind each index line: present, but under the line.
RAW_DOT_SIZE = 4
RAW_DOT_OPACITY = 0.45
#: SPY drawdown bands, as (depth below the prior high, colour, opacity, legend label),
#: shallowest first. Each week takes the deepest level it reaches; the bands run behind
#: both panels. Hue says the depth (amber pullback, orange correction, red bear market)
#: and opacity rises with it too, so the order survives a reader who cannot tell the
#: hues apart.
DRAWDOWN_LEVELS = (
    (0.05, vc.SOLARIZED_DARK_YELLOW, 0.14, "SPY 5-10% off its high"),
    (0.10, vc.SOLARIZED_DARK_ORANGE, 0.20, "10-20% off"),
    (0.20, vc.SOLARIZED_DARK_RED, 0.28, "20% or more off"),
)
#: The COT net-positioning columns' look (plot_traces.add_trace_to_all, is_bar).
COLUMN_OPACITY = 0.8
COLUMN_BARGAP = 0.2
#: Figure heights in px. Compacted 2026-11-06 (from 620 and 940) so each card fits a
#: laptop screen: about 190 px a panel on the price card, 120 px a column row.
PRICE_HEIGHT = 470
COLUMNS_HEIGHT = 680
#: The columns view's SPY panel: its total return over the trailing weeks to each Friday,
#: up weeks in the page's grey ink rather than the board's bull green, which is AAII's.
SPY_RETURN_WEEKS = 13
SPY_UP = vc.TEXT_COLOR
#: The column panels' axes, which the browser re-fits to each window with zero in view.
COLUMN_AXES = ("yaxis", "yaxis2", "yaxis3", "yaxis4")
#: Line colours, all from the selected palette so a palette switch repaints the page.
#: The two sentiment series are not COT categories, so they stay off the category slots
#: 0-2 the rest of the app gives commercials, large specs and non-reportables: NAAIM
#: takes slot 5 (Volatility elsewhere) and AAII slot 3 (Price elsewhere). Slot 4 (Open
#: Interest) is a near-white neutral in every palette and would read as the SPY line.
#: Neither borrowed meaning is drawn on this page, and in all five palettes the two stay
#: distinct.
SENTIMENT_SLOTS = {"naaim": 5, "aaii": 3}


def sentiment_colors(palette):
    """NAAIM's and AAII's line colours from the palette, keyed like the frame."""
    return {key: palette[slot] for key, slot in SENTIMENT_SLOTS.items()}


#: The two series, in drawing order.
SERIES = (("naaim", "NAAIM exposure"), ("aaii", "AAII bulls minus bears"))
LABELS = dict(SERIES)

PRICE_NOTE = (
    "Both surveys mostly follow price: NAAIM's level tracks SPY's trailing 13-week "
    "return at 0.62, AAII's at 0.44, so a high reading usually follows a rally. Neither "
    "moves with the S&P 500 COT groups (correlations of weekly to quarterly changes near "
    "zero, 2006-2026), which is why the commercials row is drawn as a contrast, not a "
    "pairing.")

STUDY_NOTE = (
    "Studied once under a pre-registration (npf, 2026-11-05, SPY 13-week forward "
    "return, on weekly percentile ranks rather than this index): weeks with NAAIM in its "
    "bottom fifth were followed by about 2.5 points more than top-fifth weeks, a "
    "marginal lean that did not clear its line, and NAAIM added nothing measurable once "
    "S&P speculator positioning was known. Context, not signal.")


#: The two cards' headings, shared by the page and its published copy (sentiment_static).
PRICE_TITLE = "Sentiment against price"
PRICE_SUBTITLE = (
    f"NAAIM and AAII on one panel as range indexes: each {AVERAGE_WEEKS}-week average "
    "placed between its own lowest (0) and highest (100) reading of the lookback. Above "
    "80 the crowd leans long, below 20 it is washed out. Faint dots: each week as read, "
    "on the same scale; the large one is the latest week, read out above the panel. "
    "Shaded weeks: SPY below its high so far, amber 5-10%, orange 10-20%, red 20% or "
    "more. "
    f"Opens on {OPEN_YEARS} years; the buttons zoom down to {RANGE_MONTHS[0]} months "
    "without changing the index.")
COLUMNS_TITLE = "Weekly columns"


@dataclass(frozen=True)
class SentimentRead:
    """The weekly frame and what is known about it.

    `frame` is indexed by week (Friday) and holds, where the store has them: `spy`,
    `naaim`, `aaii` as read; `naaim_avg` and `aaii_avg`, their 2-week averages;
    `naaim_trail`, NAAIM's average over the prior 52 x lookback weeks (this week
    excluded), and `naaim_dev`, the week's reading minus it; and `naaim_idx` and
    `aaii_idx`, the 0-100 range indexes of the averages; `naaim_raw_idx` and
    `aaii_raw_idx`, each week as read placed on that index (`on_index_scale`); and `comm`, S&P 500
    commercials' net as a percent of open interest, on its report's Friday. `last` maps each
    series key to the date of its newest stored observation. `awaiting` names what the
    store lacks.
    """
    frame: pd.DataFrame
    last: dict
    awaiting: tuple
    lookback_years: int = DEFAULT_LOOKBACK
    #: Series key ("naaim", "aaii") -> the weeks (Fridays) whose reading is
    #: provisional, oldest first. A key with no provisional weeks is absent.
    provisional_by: dict = field(default_factory=dict)

    @property
    def provisional(self):
        """NAAIM's provisional weeks, the field's name before AAII had any."""
        return provisional_weeks(self, "naaim")


def provisional_weeks(read, key):
    """The weeks (Fridays) whose `key` reading is provisional, oldest first."""
    return read.provisional_by.get(key, ())


def _splice(official, prov):
    """`official` extended by the provisional weeks after its end, and those weeks as
    Fridays. Provisional weeks only extend an official series, never stand in for one,
    and only past its end: marketdata already trims them, this guards a stale copy."""
    if official is None or prov is None:
        return official, ()
    prov = prov[prov.index > official.index[-1]]
    if prov.empty:
        return official, ()
    return pd.concat([official, prov]), tuple(weekly(prov).index)


def week_key(index):
    """The Friday ending the Monday-to-Friday week each date falls in."""
    idx = pd.DatetimeIndex(index)
    return (idx + pd.to_timedelta(4 - idx.weekday, unit="D")).normalize()


def weekly(series):
    """A series keyed by week, keeping the later observation when a week has two."""
    s = series.dropna().copy()
    s.index = week_key(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index()


def index_window(years=DEFAULT_LOOKBACK):
    """Observations in a `years` lookback: 52 a year plus the current week."""
    return 52 * years + 1


def range_index(series, years=DEFAULT_LOOKBACK):
    """cotmetrics' range index over the trailing `years` of THIS series' weeks."""
    return indicators.calculate_range_index(series, window=index_window(years))


def on_index_scale(raw, avg, years=DEFAULT_LOOKBACK):
    """Each week as read, placed on its average's index: the same trailing lowest (0) and
    highest (100) of the AVERAGE that `range_index(avg, years)` uses, so a dot under the
    line means the week read below its 2-week average and the line is the dots' average.
    A week beyond everything the average reached in the window is pinned to the edge
    (3% of weeks at three years, 10% at one, 2008 on). Display arithmetic, like the
    average itself: the index is cotmetrics', this only places the raw reading on it.

    Not `range_index(raw)`: the raw series' own extremes are wider than the average's, so
    on its own window a week sits nearer the middle than the line, and dots drifted below
    the line through weeks that read above it (autumn 2026)."""
    window = index_window(years)
    lo = avg.rolling(window, min_periods=window).min()
    hi = avg.rolling(window, min_periods=window).max()
    span = (hi - lo).where(hi > lo)
    return (100.0 * (raw.reindex(avg.index) - lo) / span).clip(0.0, 100.0)


def trailing_average(series, years=DEFAULT_LOOKBACK):
    """The mean of the prior 52 x `years` observations of THIS series, the current one
    excluded, so a week is compared only with what came before it. NaN until a full
    window exists. Display arithmetic, like the 2-week average."""
    weeks = 52 * years
    return series.shift(1).rolling(weeks, min_periods=weeks).mean()


def _get_bars(symbol, tier=None):
    import marketdata
    return marketdata.get_bars(symbol, tier) if tier else marketdata.get_bars(symbol)


def _close(get_bars, symbol, tier=None):
    """The Close series, or None when the store cannot serve it (absent symbol, a
    marketdata checkout that predates the registry entry, an unset store)."""
    try:
        df = get_bars(symbol, tier) if tier else get_bars(symbol)
        s = pd.to_numeric(df["Close"], errors="coerce").dropna()
    except Exception:  # noqa: BLE001 -- named as awaiting, never raised into a page
        return None
    if s.empty:
        return None
    s.index = pd.DatetimeIndex(s.index)
    return s.sort_index()


def _positioning():
    """S&P 500 commercials' net, % of open interest, by report date, from the indexer."""
    from cotmetrics.indexer import get_indexer
    return get_indexer().get_symbols_data(POSITIONING_MARKET, "52")[COMM_COLUMN]


def _commercials(get_positioning):
    """The commercials series as sorted floats, or None when the store cannot serve it."""
    try:
        s = pd.to_numeric(get_positioning(), errors="coerce").dropna()
    except Exception:  # noqa: BLE001 -- named as awaiting, never raised into a page
        return None
    if s.empty:
        return None
    s.index = pd.DatetimeIndex(s.index)
    return s.sort_index()


def build_read(get_bars=None, lookback_years=DEFAULT_LOOKBACK, get_positioning=None):
    """Assemble the weekly frame, indexed over `lookback_years`. Store-free when
    `get_bars` and `get_positioning` are injected."""
    get_bars = get_bars or _get_bars
    awaiting = []

    provisional = {}
    naaim = _close(get_bars, NAAIM)
    if naaim is None:
        awaiting.append(NAAIM)
    else:
        naaim, weeks = _splice(naaim, _close(get_bars, NAAIM_PROVISIONAL))
        if weeks:
            provisional["naaim"] = weeks
    bull, bear = _close(get_bars, AAII_BULL), _close(get_bars, AAII_BEAR)
    aaii = None
    if bull is None or bear is None:
        awaiting += [s for s, v in ((AAII_BULL, bull), (AAII_BEAR, bear)) if v is None]
    else:
        aaii = ((bull - bear) * 100.0).dropna()   # fractions to percentage points
        # Both provisional legs or neither: a week with one leg is not a reading.
        pb, pr = (_close(get_bars, AAII_BULL_PROVISIONAL),
                  _close(get_bars, AAII_BEAR_PROVISIONAL))
        prov = None if pb is None or pr is None else ((pb - pr) * 100.0).dropna()
        aaii, weeks = _splice(aaii, prov if prov is not None and not prov.empty else None)
        if weeks:
            provisional["aaii"] = weeks
    spy = _close(get_bars, PRICE, PRICE_TIER)
    if spy is None:
        awaiting.append(PRICE)
    # Looked up at call time, so a test can stand in for the store.
    comm = _commercials(get_positioning or _positioning)
    if comm is None:
        awaiting.append(COMM_AWAITING)

    cols, last = {}, {}
    for key, s in (("spy", spy), ("naaim", naaim), ("aaii", aaii), ("comm", comm)):
        if s is None:
            continue
        last[key] = s.index[-1].date()
        cols[key] = weekly(s)
    frame = pd.DataFrame(cols).sort_index()
    frame.index.name = "week"

    # Averages and indexes on each series' own weeks, then aligned: the window is 157 of
    # THAT series' observations, and no value is carried into a week it was not read.
    for key in ("naaim", "aaii"):
        if key in cols:
            avg = cols[key].rolling(AVERAGE_WEEKS, min_periods=AVERAGE_WEEKS).mean()
            frame[f"{key}_avg"] = avg.reindex(frame.index)
            frame[f"{key}_idx"] = range_index(avg, lookback_years).reindex(frame.index)
            frame[f"{key}_raw_idx"] = on_index_scale(cols[key], avg, lookback_years
                                                     ).reindex(frame.index)
    if "naaim" in cols:
        trail = trailing_average(cols["naaim"], lookback_years)
        frame["naaim_trail"] = trail.reindex(frame.index)
        frame["naaim_dev"] = (cols["naaim"] - trail).reindex(frame.index)
    return SentimentRead(frame=frame, last=last, awaiting=tuple(dict.fromkeys(awaiting)),
                         lookback_years=lookback_years, provisional_by=provisional)


def _dated(read, key):
    """A series' newest date for the page's words, flagged when it is provisional."""
    tail = ", provisional" if provisional_weeks(read, key) else ""
    return f"{read.last[key]:%Y-%m-%d}{tail}"


# ── figures ───────────────────────────────────────────────────────────────────

def _base(fig, height):
    fig.update_layout(
        height=height, margin=dict(l=56, r=16, t=28, b=32),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=vc.TEXT_COLOR, size=11), hovermode="x unified",
        # The page background is transparent, so without its own colour the hover box
        # draws white under pale text. The board's dark label, as on Breadth and Crowd.
        hoverlabel=dict(bgcolor="#0e1116", bordercolor=vc.GRID_COLOR,
                        font=dict(color=vc.HOVER_TEXT_COLOR)),
        legend=dict(orientation="h", y=-0.06, yanchor="top", x=0, font=dict(size=10)),
    )
    fig.update_xaxes(showgrid=False, zeroline=False,
                     tickfont=dict(size=10, color=vc.TEXT_COLOR))
    fig.update_yaxes(gridcolor=vc.GRID_COLOR, zeroline=False,
                     tickfont=dict(size=10, color=vc.TEXT_COLOR))
    return fig


def _left_titles(fig):
    for ann in fig.layout.annotations:
        ann.font = dict(size=11, color=vc.TEXT_COLOR)
        # align too: a two-line header (_row_title) otherwise centres each line.
        ann.x, ann.xanchor, ann.align = 0, "left", "left"


#: Plotly keeps a user's zoom across redraws that carry the same uirevision, so flipping
#: the lookback swaps the lines without throwing away the window on screen.
UIREVISION = "sentiment"


def range_buttons(fig):
    """The year buttons every chart in the app offers, led by 3M and 6M, on the top
    panel's axis where they render above the figure. The year ladder is Exposure's, so it
    cannot drift from it."""
    months = [dict(count=n, label=f"{n}M", step="month", stepmode="backward")
              for n in RANGE_MONTHS]
    years = [dict(count=n, label=f"{n}Y", step="year", stepmode="backward")
             for n in exposure_traces.RANGE_YEARS]
    fig.update_xaxes(rangeselector=dict(
        buttons=months + years + [dict(step="all", label="Max")],
        bgcolor=vc.BLUE_BACKGROUND, activecolor=vc.BLUE_BACKGROUND,
        font=dict(color=vc.BRIGHTER_TEXT_COLOR, size=10),
        y=1.0, yanchor="bottom", x=1.0, xanchor="right"), row=1, col=1)


def open_range(read):
    """The x range the time views open on: the last OPEN_YEARS, plus a little room."""
    end = read.frame.index[-1]
    return [end - pd.DateOffset(years=OPEN_YEARS), end + pd.Timedelta(days=OPEN_PAD_DAYS)]


def autorange_clip(read):
    """Keep an autorange (the Max button, a double-click) to the data's own span.

    Plotly pads an autorange by about 5% of the span on each side for any trace drawn
    with markers, which the raw weekly dots and the latest markers are: at Max that
    put the right edge in January 2029, over two years past the data. The year and
    month buttons count back from the axis's right edge, not the data's, so 1Y after
    Max showed 2028 to 2029, an empty window the price axis could not refit to
    (reported 2026-11-10). Clipping the autorange to the first week anything is drawn
    (SPY, or an index once its window fills; the frame itself starts earlier, with
    AAII's raw weeks) and to `open_range`'s right edge keeps Max on the data and every
    button after it too.

    `clipmin` / `clipmax`, not `minallowed` / `maxallowed`: with date strings the
    latter left Plotly 3.7's autorange at its empty placeholder (2000 to 2001)."""
    f = read.frame
    drawn = [c for c in ("spy", "naaim_idx", "aaii_idx", "naaim_raw_idx", "aaii_raw_idx")
             if c in f and f[c].notna().any()]
    first = min(f[c].first_valid_index() for c in drawn) if drawn else f.index[0]
    return dict(clipmin=f"{first:%Y-%m-%d}", clipmax=f"{open_range(read)[1]:%Y-%m-%d}")


def _zones(fig, row):
    """The fixed extreme zones as dotted lines at 20 and 80. Lines rather than fills: the
    drawdown bands own the background, and a red top zone over a red band reads as
    one shape."""
    # exclude_empty_subplots=False: the zones go in before the line, and plotly's default
    # silently skips a subplot that has no trace yet.
    for v in (LO, HI):
        fig.add_hline(y=v, line=dict(color=vc.TEXT_COLOR, width=1, dash="dot"),
                      opacity=0.6, row=row, col=1, exclude_empty_subplots=False)
    fig.update_yaxes(range=[-2, 102], tickvals=[0, LO, 50, HI, 100], row=row, col=1)


def drawdown_level(spy):
    """Per week, how many DRAWDOWN_LEVELS SPY is past (0 to 3), measured from its highest
    close up to and including that week, so a band never knows a later high."""
    s = spy.dropna()
    depth = 1 - s / s.cummax()
    level = pd.Series(0, index=s.index)
    for i, (cut, *_) in enumerate(DRAWDOWN_LEVELS, start=1):
        level[depth >= cut] = i
    return level


def drawdown_runs(spy):
    """Consecutive weeks at one non-zero level, as (first week, last week, level). One
    shape per run rather than per week, so twenty years draw as dozens of shapes."""
    level = drawdown_level(spy)
    if level.empty:
        return []
    run_id = (level != level.shift()).cumsum()
    return [(g.index[0], g.index[-1], int(g.iloc[0]))
            for _, g in level.groupby(run_id) if g.iloc[0] > 0]


def _drawdown_bands(fig, read):
    """SPY's drawdown bands behind both panels, one hue per depth (DRAWDOWN_LEVELS).
    Each band spans its weeks from mid-week before the first to mid-week after the last.
    Every band of a depth shares one legend group with that depth's key (see
    `_drawdown_keys`), so clicking a key hides or shows that depth on both panels."""
    if "spy" not in read.frame:
        return
    # Built as one list and set once: add_vrect re-validates every shape already on the
    # figure, so 125 runs took 4.7 s per draw (measured 2026-11-05) against 0.01 s here.
    half = pd.Timedelta(days=3.5)
    bands = []
    for first, last, level in drawdown_runs(read.frame["spy"]):
        _, color, alpha, _ = DRAWDOWN_LEVELS[level - 1]
        for xref, yref in (("x", "y domain"), ("x2", "y2 domain")):
            bands.append(dict(type="rect", xref=xref, yref=yref, x0=first - half,
                              x1=last + half, y0=0, y1=1,
                              fillcolor=hex_to_rgba(color, alpha),
                              line=dict(width=0), layer="below",
                              legendgroup=f"drawdown{level}", showlegend=False))
    fig.update_layout(shapes=[*fig.layout.shapes, *bands])


def _drawdown_keys(fig):
    """One legend key per depth, as an empty marker trace in the band's colour.

    Traces rather than the shapes' own legend entries: a shape with showlegend on, in a
    figure whose top x axis `matches` the bottom one, makes Plotly 3.7 (dash's bundle)
    throw away every range change on that axis, so the year buttons and a drag-zoom
    did nothing (found 2026-11-06, the same day the keys went in). Shapes in the key's
    legend group with showlegend off still follow its click, and the zoom works.

    All three keys always show, so the scheme reads even on a window with no 20% band.
    legendrank puts them after the two lines (default 1000), shallowest first. Added
    after the lines: Plotly types an axis from its first trace, and an empty first trace
    typed the index panel's axis as numbers (the axes are also pinned to dates)."""
    for level, (_, color, alpha, label) in enumerate(DRAWDOWN_LEVELS, start=1):
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode="markers", name=label,
            marker=dict(symbol="square", size=12, color=hex_to_rgba(color, alpha)),
            legendgroup=f"drawdown{level}", legendrank=1000 + level,
            hoverinfo="skip"), row=2, col=1)


def _index_line(fig, read, key, label, color, row):
    """One sentiment index line, its raw weekly dots behind it, and the latest week's
    marker on the newest dot, in its own colour."""
    f = read.frame
    col = f"{key}_idx"
    if col not in f or f[col].dropna().empty:
        return
    idx = f[col].dropna()
    raw = f[[f"{key}_avg", key, f"{key}_raw_idx"]].reindex(idx.index).to_numpy()
    hover = ("%{y:.0f}  (" + f"{AVERAGE_WEEKS}-wk avg " + "%{customdata[0]:.1f}; "
             "week %{customdata[1]:.1f}, index %{customdata[2]:.0f})")
    late_weeks = provisional_weeks(read, key)
    prov = idx.index.isin(late_weeks)
    solid = ~prov
    dots = f[f"{key}_raw_idx"].dropna()
    if not dots.empty:
        # Under the line, faint, hollow where provisional. The line's hover already
        # carries the week's reading, so the dots add none.
        dprov = dots.index.isin(late_weeks)
        fig.add_trace(go.Scatter(
            x=dots.index, y=dots, mode="markers", name=f"{label}, week as read",
            legendgroup=key, showlegend=False, hoverinfo="skip", opacity=RAW_DOT_OPACITY,
            marker=dict(size=RAW_DOT_SIZE, color=np.where(dprov, vc.BACKGROUND_COLOR, color),
                        line=dict(color=color, width=np.where(dprov, 1, 0)))),
            row=row, col=1)
    fig.add_trace(go.Scatter(
        x=idx.index[solid], y=idx[solid], mode="lines", line=dict(color=color, width=1.8),
        name=label, legendgroup=key, customdata=raw[solid],
        hovertemplate=hover + "<extra>" + label + "</extra>"), row=row, col=1)
    if prov.any():
        # Dashed from the last official week, so the two segments join.
        first = int(np.argmax(prov))
        seg = slice(max(first - 1, 0), len(idx))
        fig.add_trace(go.Scatter(
            x=idx.index[seg], y=idx.iloc[seg], mode="lines",
            line=dict(color=color, width=1.8, dash="dot"), name=f"{label} (provisional)",
            legendgroup=key, showlegend=False, customdata=raw[seg],
            hovertemplate=hover + "<extra>" + label + ", provisional</extra>"),
            row=row, col=1)
    # The latest week's marker, on the newest raw dot (the reading the title names, not
    # the half-week-late average), hollow when that reading is provisional.
    at, y = (dots.index[-1], dots.iloc[-1]) if not dots.empty else (idx.index[-1], idx.iloc[-1])
    late = at in late_weeks
    fill = vc.BACKGROUND_COLOR if late else color
    edge = color if late else vc.BACKGROUND_COLOR
    fig.add_trace(go.Scatter(x=[at], y=[y], mode="markers", name=f"{label}, latest",
                             marker=dict(size=8, color=fill, line=dict(color=edge, width=1.5)),
                             cliponaxis=False, hoverinfo="skip", showlegend=False),
                  row=row, col=1)


def latest_reading(read, key):
    """The newest week as the survey published it: NAAIM's exposure, AAII's bulls minus
    bears in points. None when the series is not in."""
    if key not in read.frame or key not in read.last or read.frame[key].dropna().empty:
        return None
    return float(read.frame[key].dropna().iloc[-1])


def _index_title(read):
    """The combined panel's title: each survey's newest reading, as published, and the
    date it was read, one survey a line. The real-time readout; the index values are in
    the summary line and the hover."""
    parts = []
    for key, label in (("naaim", "NAAIM"), ("aaii", "AAII")):
        value = latest_reading(read, key)
        if value is not None and f"{key}_idx" in read.frame:
            parts.append(f"{label} {value:.1f} ({_dated(read, key)})")
    # One survey a line, no "Latest:" lead: on one line the pair ran past a phone-width
    # panel (395 pixels where 253 fit; the index-valued title before it took 373),
    # cutting AAII off, and with the lead the NAAIM line alone still ran 5 over. The
    # dates say these are the newest readings; the card subtitle says it in words.
    return "<br>".join(parts) if parts else "Sentiment range index"


#: The refit rules for a figure whose top panel is `spy_panel`: only the price axis is
#: re-fitted on a zoom, deciding log against linear for the window on screen; the panel
#: under it keeps its fixed scale.
PRICE_REFIT = {exposure_traces.REFIT_META: {
    "axes": ["yaxis"], "price_axis": "yaxis",
    "log_ratio_min": exposure_traces.LOG_RATIO_MIN, "pad": exposure_traces.REFIT_PAD}}


def spy_panel(fig, spy, start):
    """SPY's line on the top panel, its axis fitted to the window opening at `start`.

    Scale, ticks and range by Exposure's rules: log only where the window spans 3x or
    more, ticks spelled out on a log axis. The browser re-decides all three on every
    zoom (PRICE_REFIT in the figure's meta). Shared by every chart drawn over SPY here."""
    s = spy.dropna()
    fig.add_trace(go.Scatter(x=s.index, y=s, mode="lines",
                             line=dict(color=vc.BRIGHTER_TEXT_COLOR, width=1),
                             name="SPY", showlegend=False,
                             hovertemplate="%{y:.2f}<extra>SPY</extra>"), row=1, col=1)
    shown = s[s.index >= start]
    shown = shown if not shown.empty else s
    axis_type = exposure_traces.price_axis_type(shown)
    pad = exposure_traces.REFIT_PAD
    if axis_type == "log":
        lo, hi = np.log10(shown.min()), np.log10(shown.max())
        ticks = exposure_traces.log_ticks(shown)
        fig.update_yaxes(type="log", range=[lo - (hi - lo) * pad, hi + (hi - lo) * pad],
                         tickvals=ticks, tickformat=",.0f", row=1, col=1)
    else:
        lo, hi = float(shown.min()), float(shown.max())
        fig.update_yaxes(type="linear", range=[lo - (hi - lo) * pad, hi + (hi - lo) * pad],
                         row=1, col=1)


def price_sentiment_figure(read, colors, palette):
    """View 1: SPY above NAAIM and AAII's range indexes on one panel, opening on five
    years. `palette` is the viz palette, for the two sentiment colours."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        row_heights=[0.5, 0.5],
                        subplot_titles=("SPY, total return", _index_title(read)))
    f = read.frame
    if "spy" in f:
        spy_panel(fig, f["spy"], open_range(read)[0])
    _drawdown_bands(fig, read)
    _zones(fig, 2)
    line_colors = sentiment_colors(palette)
    _index_line(fig, read, "naaim", "NAAIM exposure", line_colors["naaim"], 2)
    _index_line(fig, read, "aaii", "AAII bulls minus bears", line_colors["aaii"], 2)
    if "spy" in f:
        _drawdown_keys(fig)
    fig.update_xaxes(type="date")
    if not f.empty:
        fig.update_xaxes(range=open_range(read), autorangeoptions=autorange_clip(read))
    range_buttons(fig)
    _left_titles(fig)
    _base(fig, PRICE_HEIGHT)
    fig.update_layout(uirevision=UIREVISION)
    # Only the price axis is re-fitted on a zoom: the index panel is pinned to 0-100,
    # which is the point of an index, and fitting it to a window would undo it.
    fig.update_layout(margin=dict(t=44), meta=PRICE_REFIT)
    return fig


def _columns(fig, s, label, color, row, hovertemplate, customdata=None, faint=None):
    """One series as weekly columns, the way get_net_pos_plot draws a COT group.
    `faint` marks columns to draw at PROVISIONAL_OPACITY of the others."""
    marker = dict(color=color, line=dict(color=color, width=0.5))
    if faint is not None and np.any(faint):
        marker["opacity"] = np.where(faint, PROVISIONAL_OPACITY, 1.0)
    fig.add_trace(go.Bar(x=s.index, y=s, name=label, opacity=COLUMN_OPACITY,
                         marker=marker,
                         showlegend=False, customdata=customdata,
                         hovertemplate=hovertemplate),
                  row=row, col=1)


def spy_return(read):
    """SPY's total return over the SPY_RETURN_WEEKS to each Friday, in percent. Each
    value ends on its own week, so it uses nothing later."""
    if "spy" not in read.frame:
        return pd.Series(dtype=float)
    spy = read.frame["spy"].dropna()
    return (spy.pct_change(SPY_RETURN_WEEKS) * 100).dropna()


def _row_title(title, note):
    """A column row's header: its name, and under it the one sentence that reads it.
    Each row carries its own explanation rather than the card's subtitle carrying all
    four, so the sentence sits beside the columns it describes (2026-11-06)."""
    return f"{title}<br><span style='font-size:10px'>{note}</span>"


def columns_figure(read, colors, palette):
    """SPY's trailing return, NAAIM against its trailing average, AAII bulls minus
    bears and, as a contrast, ES commercials' net, weekly columns.

    Each on its own panel: on one axis NAAIM's swings (about 20 points either way)
    would hide AAII's. NAAIM follows the lookback; SPY and AAII do not. `colors` gives
    SPY's down weeks the board's bear; up weeks take SPY's grey."""
    f = read.frame
    sent = sentiment_colors(palette)
    n = read.lookback_years
    # Spacing leaves room for each row's two-line header (_row_title), about 40 px.
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.075,
                        subplot_titles=(
                            _row_title(f"SPY {SPY_RETURN_WEEKS}-week return, %",
                                       f"Total return over the {SPY_RETURN_WEEKS} weeks to "
                                       "each Friday, the move both surveys track most closely"),
                            _row_title(f"NAAIM vs {n}Y avg",
                                       f"Exposure minus its average over the prior {n} "
                                       f"{'year' if n == 1 else 'years'}: above zero, "
                                       "managers are more invested than their recent normal"),
                            _row_title("AAII bulls minus bears, points",
                                       "As read, so the lookback does not change it"),
                            _row_title("ES commercials net, % of OI (contrast)",
                                       "As on the COT chart. Unlike the rows above, it "
                                       "barely moves with SPY's return")))
    # Values rounded here rather than formatted in the template: Plotly drops a bar
    # template's number format in a unified hover.
    ret = spy_return(read).round(1)
    if not ret.empty:
        signed = [SPY_UP if v >= 0 else colors.bear for v in ret]
        fig.add_trace(go.Bar(x=ret.index, y=ret, name="SPY return", opacity=COLUMN_OPACITY,
                             marker=dict(color=signed, line=dict(color=signed, width=0.5)),
                             showlegend=False,
                             hovertemplate=f"%{{y}}%  ({SPY_RETURN_WEEKS} weeks)"
                                           "<extra>SPY</extra>"),
                      row=1, col=1)
    if "naaim_dev" in f:
        dev = f["naaim_dev"].dropna().round(1)
        raw = f[["naaim", "naaim_trail"]].reindex(dev.index).round(1).to_numpy()
        prov = dev.index.isin(read.provisional)
        raw = np.column_stack([raw, np.where(prov, ", provisional", "")])
        _columns(fig, dev, "NAAIM against its average", sent["naaim"], 2,
                 "%{y}  (exposure %{customdata[0]}%{customdata[2]}, "
                 f"{n}Y average " + "%{customdata[1]})<extra>NAAIM</extra>", raw,
                 faint=prov)
    if "aaii" in f:
        aaii = f["aaii"].dropna().round(1)
        prov = aaii.index.isin(provisional_weeks(read, "aaii"))
        _columns(fig, aaii, "AAII bulls minus bears", sent["aaii"], 3,
                 "%{y} pts%{customdata}<extra>AAII bulls minus bears</extra>",
                 np.where(prov, ", provisional", ""), faint=prov)
    if "comm" in f:
        _columns(fig, f["comm"].dropna().round(1), "ES commercials", palette[COMM_SLOT], 4,
                 "%{y}% of OI<extra>ES commercials</extra>")
    fig.update_yaxes(zeroline=True, zerolinecolor=vc.GRID_COLOR, zerolinewidth=1)
    if not f.empty:
        fig.update_xaxes(range=open_range(read))
    range_buttons(fig)
    _left_titles(fig)
    _base(fig, COLUMNS_HEIGHT)
    fig.update_layout(bargap=COLUMN_BARGAP, margin=dict(t=62), uirevision=UIREVISION,
                      showlegend=False,
                      meta={exposure_traces.REFIT_META: {"axes": list(COLUMN_AXES),
                                                         "zero": list(COLUMN_AXES)}})
    if not f.empty:
        _fit_columns(fig, open_range(read))
    return fig


def _fit_columns(fig, window):
    """Each column panel's axis fitted to the bars in `window`, zero included, padded 5%
    as the browser pads it, so the chart opens as a button press would leave it."""
    t0, t1 = window
    for trace in fig.data:
        x = pd.DatetimeIndex(trace.x)
        y = np.asarray(trace.y, dtype=float)[(x >= t0) & (x <= t1)]
        if not len(y):
            continue
        lo, hi = min(y.min(), 0.0), max(y.max(), 0.0)
        pad = (hi - lo) * 0.05 or 1.0
        fig.layout[trace.yaxis.replace("y", "yaxis", 1)].range = [lo - pad, hi + pad]


# ── words ─────────────────────────────────────────────────────────────────────

def summary(read):
    """One sentence on the latest index readings, or None when neither series is in.
    Dated by the stored observation, as the chart title is, not by the week's Friday."""
    parts = []
    for key, label in SERIES:
        col = f"{key}_idx"
        if col in read.frame and key in read.last and read.frame[col].notna().any():
            parts.append(f"{label.split()[0]} at {read.frame[col].dropna().iloc[-1]:.0f} "
                         f"({_dated(read, key)})")
    if not parts:
        return None
    if read.provisional:
        bound = (f" NAAIM's last {len(read.provisional)} weeks are provisional, hand-kept "
                 "until NAAIM publishes them.")
    elif "naaim" in read.last:
        bound = " NAAIM's store runs about a quarter behind the others."
    else:
        bound = ""
    aaii_late = provisional_weeks(read, "aaii")
    if aaii_late:
        bound += (f" AAII's last {_weeks_word(len(aaii_late))} provisional, from AAII's "
                  "public page until the member spreadsheet is rebuilt.")
    return (f"On the {read.lookback_years}-year range index: {', '.join(parts)}." + bound)


def _weeks_word(n):
    """'week is' or 'N weeks are', for a sentence about the newest provisional weeks."""
    return "week is" if n == 1 else f"{n} weeks are"


def caption(read, local=True):
    """Data dates, the lag, the index's one caveat, the price note and the study note.
    `local=False` is the published copy (sentiment_static), which drops the local-only
    line: that copy IS the publication."""
    names = {"spy": "SPY", "naaim": "NAAIM", "aaii": "AAII", "comm": "ES COT"}
    flag = {k: " (provisional)" for k in names if provisional_weeks(read, k)}
    dated = ", ".join(f"{names[k]} {read.last[k]:%Y-%m-%d}{flag.get(k, '')}"
                      for k in names if k in read.last)
    parts = []
    if dated:
        parts.append(f"Newest stored observation: {dated}.")
    parts.append(
        f"Each index places a series' {AVERAGE_WEEKS}-week average between its own lowest (0) and "
        "highest (100) reading of the trailing "
        f"{_YEARS_WORD.get(read.lookback_years, f'{read.lookback_years} years')}. "
        "When an old high or low leaves that window the scale shifts under the line, as "
        "it does for the COT index.")
    if read.provisional:
        parts.append(
            f"NAAIM's official series runs about a quarter behind: its free table is "
            f"delayed and current readings are subscriber-only. The {len(read.provisional)} "
            f"weeks from {read.provisional[0]:%Y-%m-%d} are provisional, read off a "
            "StockCharts chart or its label (about 0.2 points from NAAIM's own values "
            "where both exist, with a few weeks where StockCharts differs), drawn dotted "
            "and faint, and replaced by NAAIM's values as they are published. Every point "
            "sits on the Friday of the week it became public.")
    else:
        parts.append(
            "NAAIM in the store runs about a quarter behind: its free table is delayed and "
            "current readings are subscriber-only. Every point sits on the Friday of the "
            "week it became public.")
    aaii_late = provisional_weeks(read, "aaii")
    if aaii_late:
        n = len(aaii_late)
        # Dated by the stored observation, as the title is, not by the week's Friday.
        through = "" if n == 1 else "through "
        parts.append(
            f"AAII's last {_weeks_word(n)} provisional ({through}{read.last['aaii']:%Y-%m-%d}): "
            "typed from AAII's public results page, "
            "whose rounded percentages put bulls minus bears within 0.1 point of the member "
            "spreadsheet's, drawn hollow and faint, and replaced when the spreadsheet is "
            "next downloaded.")
    parts.append(PRICE_NOTE)
    parts.append(STUDY_NOTE)
    if read.lookback_years != DEFAULT_LOOKBACK:
        parts.append(
            f"The study ranked on three years; on this {read.lookback_years}-year index "
            "the lines are not the window it measured, and more weeks sit in a zone "
            "(34-43% of them, against 21-36% at three years).")
    if local:
        parts.append("Local only: NAAIM and AAII history is licensed data and is not "
                     "published on the site.")
    return parts


# ── caching ───────────────────────────────────────────────────────────────────

def _stamp():
    """Keyed on the stores' dates rather than the clock: a delivery invalidates the
    entry and nothing else does (the tape_context convention)."""
    stamp = []
    for symbol in (NAAIM, NAAIM_PROVISIONAL, AAII_BULL, AAII_BEAR, AAII_BULL_PROVISIONAL,
                   AAII_BEAR_PROVISIONAL, PRICE):
        try:
            import marketdata
            stamp.append(marketdata.provenance(symbol).last_date)
        except Exception:  # noqa: BLE001
            stamp.append(None)
    try:
        from cotmetrics.indexer import get_indexer
        dates = get_indexer().get_available_dates()
        stamp.append(str(max(dates)) if len(dates) else None)
    except Exception:  # noqa: BLE001
        stamp.append(None)
    return tuple(stamp)


@functools.lru_cache(maxsize=4)
def _cached(stamp, years):
    return build_read(lookback_years=years)


def read(lookback_years=DEFAULT_LOOKBACK):
    """The current read on a lookback, cached until a store's dates move."""
    try:
        return _cached(_stamp(), lookback_years)
    except Exception as e:  # noqa: BLE001
        utils.cot_logger.warning(f"sentiment: read failed: {e}")
        return SentimentRead(frame=pd.DataFrame(), last={},
                             awaiting=(NAAIM, AAII_BULL, AAII_BEAR, PRICE),
                             lookback_years=lookback_years)
