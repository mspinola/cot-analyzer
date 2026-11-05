"""Stated sentiment against price and positioning: NAAIM and AAII, weekly. LOCAL ONLY.

Three views of one weekly frame, and a caption:

1. **Sentiment against price.** SPY (total return) above one panel carrying NAAIM and
   AAII bulls minus bears, each drawn as a range index: its 4-week average placed
   between its own lowest (0) and highest (100) reading of the trailing lookback (three
   years by default, one on the toggle). The 20 and 80 zones stay fixed on the chart and
   the lines move between them.
2. **Words against money.** Two pairs, each a sentiment index beside the COT group whose
   money it is closest to, on the same 0-100 scale, with the words-minus-money gap
   under it: NAAIM (active managers) against S&P 500 large-speculator net, AAII
   (individual investors) against S&P 500 non-reportable net. This is the view only
   this app can draw: it joins stated exposure to COT positioning.
3. **Quadrants.** NAAIM's index against the speculators', every joint week dim, the
   last 13 weeks as a path and the latest week marked. It says where the market is, not
   what followed.

The two time views open on the last five years and carry the app's year buttons (1Y to
15Y and Max). The SPY panel re-fits its axis to each window through the shared clientside
handler; the index panels stay pinned to 0-100.

**The lookback is a toggle, 3Y by default, 1Y beside it.** Measured 2026-11-05 on the
store (each series on its own weeks, the sentiment pair on their 4-week averages):

| | 1 year | 3 years |
|---|---|---|
| weeks in a zone (at or past 20/80), across the four series | 36-44% | 25-36% |
| weeks pinned at 0 or 100 | 9-11% | 3-5% |
| weeks the scale moves under the line | 9-11% | 3-5% |
| NAAIM against large specs, rank correlation | 0.07 | 0.38 |
| AAII against non-reportables | 0.29 | 0.34 |

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

**Why these pairs.** Measured 2026-11-05 on the 888 weeks all four indexes share
(2009-07 to 2026-08, Spearman on the index levels): AAII against large specs 0.06,
against non-reportables 0.34; NAAIM against large specs 0.38, against non-reportables
0.27. AAII drawn against large specs set two unrelated lines side by side. The second
pair is descriptive only: the study pre-registered NAAIM against large specs and never
tested it. Non-reportables are what is left of open interest once the reportable traders
are counted, so they are small accounts, not retail by definition, and the noisiest
bucket (about 3% of OI here); the S&P 500 market is ES with the full-size contract and
the micros (at a tenth) folded in. The caption says so.

**Arithmetic.** This repo computes no metrics of its own. The index is
`cotmetrics.indicators.calculate_range_index` over 52 x years + 1 weekly observations
(157 at three years, 53 at one: the `weeks + 1` convention every board column uses). The
positioning series are the indexer's `Lrg Spec Pct OI` and `Sml Spec Pct OI` for the
S&P 500, indexed on their weekly values; they are the columns the other pages read, on
the page's lookback rather than the market's tuned COT lookback, so every series here
shares one window. AAII
is bulls minus bears in percentage points, a difference of two stored series. The
4-week average on the two sentiment series is display smoothing: both swing hard week
to week, and twenty years of raw weekly readings draw as a solid block.

**Dating.** Every observation is keyed to the Friday of the week it falls in, because
all three are public by that Friday's close: NAAIM surveys on Wednesday and publishes
that week, AAII reports on Thursday, COT positions are Tuesday's and are released on
Friday afternoon. The exceptions are COT holiday weeks (released the following Monday)
and the appropriations lapses of 2013, 2018-19 and 2025, when releases trailed by weeks;
a chart dated by the Friday reads those weeks as known early. The caption says so.

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
from dataclasses import dataclass

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
AAII_BULL = "AAII_BULLISH"
AAII_BEAR = "AAII_BEARISH"
PRICE = "SPY"
PRICE_TIER = "total"
POSITIONING_MARKET = "S&P 500"
POSITIONING_COLUMN = const.LARGE_PCT_OI
POSITIONING_LABEL = "S&P 500 large-spec net"
SMALL_COLUMN = const.SMALL_PCT_OI
SMALL_LABEL = "S&P 500 non-reportable net"

LOOKBACK_YEARS = (1, 3)           # the index toggle
DEFAULT_LOOKBACK = 3
INDEX_WEEKS = 52 * DEFAULT_LOOKBACK
INDEX_WINDOW = INDEX_WEEKS + 1    # observations, the board's weeks + 1 convention
_YEARS_WORD = {1: "year", 3: "three years"}
AVERAGE_WEEKS = 4
LO, HI = 20.0, 80.0               # fixed zones on the 0-100 index
OPEN_YEARS = 5                    # the time views open on this many trailing years
TRAIL_WEEKS = 13
#: Line colours, all from the selected palette so a palette switch repaints the page.
#: Large specs take slot 1, as on every positioning chart (`plot_traces`). The two
#: sentiment series are not COT categories, so they stay off slots 0-2: NAAIM takes slot
#: 5 (Volatility elsewhere) and AAII slot 3 (Price elsewhere). Slot 4 (Open Interest) is
#: a near-white neutral in every palette and would read as the SPY line. Neither borrowed
#: meaning is drawn on this page, and in all five palettes the two stay distinct from
#: each other and from slot 1.
SENTIMENT_SLOTS = {"naaim": 5, "aaii": 3}


def sentiment_colors(palette):
    """NAAIM's and AAII's line colours from the palette, keyed like the frame."""
    return {key: palette[slot] for key, slot in SENTIMENT_SLOTS.items()}


def large_spec_color(palette):
    """The large-speculator colour: palette slot 1, the plot_traces convention."""
    return palette[1]


def small_trader_color(palette):
    """The non-reportable colour: palette slot 2, the plot_traces convention."""
    return palette[2]

#: The four indexed series, in drawing order.
SERIES = (("naaim", "NAAIM exposure"), ("aaii", "AAII bulls minus bears"),
          ("spec", POSITIONING_LABEL), ("small", SMALL_LABEL))
LABELS = dict(SERIES)

#: Words against money: each sentiment series beside the COT group nearest it, as
#: (words key, money key, short words name, short money name). Order is drawing order.
PAIRS = (("naaim", "spec", "NAAIM", "large specs"),
         ("aaii", "small", "AAII", "non-reportables"))

QUADRANT_LABELS = {
    ("low", "low"): "Both washed out",
    ("high", "high"): "Both crowded long",
    ("high", "low"): "Words cautious, money long",
    ("low", "high"): "Words long, money short",
}

STUDY_NOTE = (
    "Studied once under a pre-registration (npf, 2026-11-05, SPY 13-week forward "
    "return, on weekly percentile ranks rather than this index): weeks with NAAIM in its "
    "bottom fifth were followed by about 2.5 points more than top-fifth weeks, a "
    "marginal lean that did not clear its line, and NAAIM added nothing measurable once "
    "S&P speculator positioning was known. Context, not signal.")


@dataclass(frozen=True)
class SentimentRead:
    """The weekly frame and what is known about it.

    `frame` is indexed by week (Friday) and holds, where the store has them: `spy`,
    `naaim`, `aaii`, `spec` (large specs), `small` (non-reportables) as read;
    `naaim_avg` and `aaii_avg`, their 4-week averages; and `naaim_idx`, `aaii_idx`,
    `spec_idx`, `small_idx`, the 0-100 range indexes (of the averages for the two
    sentiment series, of the weekly value for positioning). `last` maps each
    series key to the date of its newest stored observation. `awaiting` names what the
    store lacks.
    """
    frame: pd.DataFrame
    last: dict
    awaiting: tuple
    lookback_years: int = DEFAULT_LOOKBACK


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


def _get_bars(symbol, tier=None):
    import marketdata
    return marketdata.get_bars(symbol, tier) if tier else marketdata.get_bars(symbol)


def _positioning():
    """Both S&P 500 positioning series, keyed like the frame (`spec`, `small`)."""
    from cotmetrics.indexer import get_indexer
    df = get_indexer().get_symbols_data(POSITIONING_MARKET, "52")
    return pd.DataFrame({"spec": df[POSITIONING_COLUMN], "small": df[SMALL_COLUMN]})


def _positioning_series(frame, key):
    """One positioning column as a sorted float series, or None when it is absent."""
    if frame is None or key not in frame:
        return None
    s = pd.to_numeric(frame[key], errors="coerce").dropna()
    if s.empty:
        return None
    s.index = pd.DatetimeIndex(s.index)
    return s.sort_index()


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


def build_read(get_bars=None, get_positioning=None, lookback_years=DEFAULT_LOOKBACK):
    """Assemble the weekly frame, indexed over `lookback_years`. Store-free when both
    readers are injected."""
    get_bars = get_bars or _get_bars
    get_positioning = get_positioning or _positioning
    awaiting = []

    naaim = _close(get_bars, NAAIM)
    if naaim is None:
        awaiting.append(NAAIM)
    bull, bear = _close(get_bars, AAII_BULL), _close(get_bars, AAII_BEAR)
    aaii = None
    if bull is None or bear is None:
        awaiting += [s for s, v in ((AAII_BULL, bull), (AAII_BEAR, bear)) if v is None]
    else:
        aaii = ((bull - bear) * 100.0).dropna()   # fractions to percentage points
    spy = _close(get_bars, PRICE, PRICE_TIER)
    if spy is None:
        awaiting.append(PRICE)
    try:
        positioning = get_positioning()
    except Exception:  # noqa: BLE001
        positioning = None
    spec = _positioning_series(positioning, "spec")
    small = _positioning_series(positioning, "small")
    if spec is None:
        awaiting.append(f"{POSITIONING_MARKET} positioning")
    if small is None:
        awaiting.append(f"{POSITIONING_MARKET} non-reportables")

    cols, last = {}, {}
    for key, s in (("spy", spy), ("naaim", naaim), ("aaii", aaii), ("spec", spec),
                   ("small", small)):
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
    for key in ("spec", "small"):
        if key in cols:
            frame[f"{key}_idx"] = range_index(cols[key], lookback_years).reindex(frame.index)
    return SentimentRead(frame=frame, last=last, awaiting=tuple(dict.fromkeys(awaiting)),
                         lookback_years=lookback_years)


def joint(read, words="naaim", money="spec"):
    """Weeks with both indexes of a pair; NAAIM and large specs unless named."""
    cols = [f"{words}_idx", f"{money}_idx"]
    if not all(c in read.frame for c in cols):
        return read.frame.iloc[0:0].reindex(columns=cols)
    return read.frame[cols].dropna()


def quadrant(naaim_idx, spec_idx):
    """The quadrant label for one week, or None when either sits between the zones."""
    def side(v):
        return "low" if v <= LO else "high" if v >= HI else None
    return QUADRANT_LABELS.get((side(spec_idx), side(naaim_idx)))


# ── figures ───────────────────────────────────────────────────────────────────

def _base(fig, height):
    fig.update_layout(
        height=height, margin=dict(l=56, r=16, t=28, b=32),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=vc.TEXT_COLOR, size=11), hovermode="x unified",
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
        ann.x, ann.xanchor = 0, "left"


#: Plotly keeps a user's zoom across redraws that carry the same uirevision, so flipping
#: the lookback swaps the lines without throwing away the window on screen.
UIREVISION = "sentiment"


def range_buttons(fig):
    """The year buttons every chart in the app offers, on the top panel's axis where they
    render above the figure. The ladder is Exposure's, so it cannot drift from it."""
    fig.update_xaxes(rangeselector=dict(
        buttons=[dict(count=n, label=f"{n}Y", step="year", stepmode="backward")
                 for n in exposure_traces.RANGE_YEARS] + [dict(step="all", label="Max")],
        bgcolor=vc.BLUE_BACKGROUND, activecolor=vc.BLUE_BACKGROUND,
        font=dict(color=vc.BRIGHTER_TEXT_COLOR, size=10),
        y=1.0, yanchor="bottom", x=1.0, xanchor="right"), row=1, col=1)


def open_range(read):
    """The x range the time views open on: the last OPEN_YEARS, plus a little room."""
    end = read.frame.index[-1]
    return [end - pd.DateOffset(years=OPEN_YEARS), end + pd.Timedelta(days=30)]


def _zones(fig, colors, row=None):
    """The fixed extreme zones: 80-100 in the bear hue (crowd leaning long), 0-20 in the
    bull hue (washed out), the breadth panel's colour axis."""
    # exclude_empty_subplots=False: the zones go in before the line, and plotly's default
    # silently skips a subplot that has no trace yet.
    kw = dict(row=row, col=1, exclude_empty_subplots=False) if row else {}
    fig.add_hrect(y0=HI, y1=100, fillcolor=hex_to_rgba(colors.bear, 0.10), line_width=0, **kw)
    fig.add_hrect(y0=0, y1=LO, fillcolor=hex_to_rgba(colors.bull, 0.10), line_width=0, **kw)
    axis_kw = dict(row=row, col=1) if row else {}
    fig.update_yaxes(range=[-2, 102], tickvals=[0, LO, 50, HI, 100], **axis_kw)


def _index_line(fig, read, key, label, color, row):
    """One sentiment index line and its latest-week marker, in its own colour."""
    f = read.frame
    col = f"{key}_idx"
    if col not in f or f[col].dropna().empty:
        return
    idx = f[col].dropna()
    raw = f[[f"{key}_avg", key]].reindex(idx.index).to_numpy()
    fig.add_trace(go.Scatter(
        x=idx.index, y=idx, mode="lines", line=dict(color=color, width=1.8),
        name=label, customdata=raw,
        hovertemplate=("%{y:.0f}  (" + f"{AVERAGE_WEEKS}-wk avg " + "%{customdata[0]:.1f}, "
                       "week %{customdata[1]:.1f})<extra>" + label + "</extra>")),
        row=row, col=1)
    fig.add_trace(go.Scatter(x=[idx.index[-1]], y=[idx.iloc[-1]], mode="markers",
                             marker=dict(size=8, color=color,
                                         line=dict(color=vc.BACKGROUND_COLOR, width=1)),
                             hoverinfo="skip", showlegend=False), row=row, col=1)


def _index_title(read):
    """The combined panel's title: each series' latest index and the date it was read."""
    f, parts = read.frame, []
    for key, label in (("naaim", "NAAIM"), ("aaii", "AAII")):
        col = f"{key}_idx"
        if col in f and key in read.last and f[col].notna().any():
            parts.append(f"{label} {f[col].dropna().iloc[-1]:.0f} "
                         f"({read.last[key]:%Y-%m-%d})")
    # Short on purpose: at phone width a longer title runs off the panel, and the card's
    # subtitle already says what the index is.
    return f"Index: {', '.join(parts)}" if parts else "Sentiment range index"


def price_sentiment_figure(read, colors, palette):
    """View 1: SPY above NAAIM and AAII's range indexes on one panel, opening on five
    years. `palette` is the viz palette, for the two sentiment colours."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        row_heights=[0.5, 0.5],
                        subplot_titles=("SPY, total return", _index_title(read)))
    f = read.frame
    if "spy" in f:
        s = f["spy"].dropna()
        fig.add_trace(go.Scatter(x=s.index, y=s, mode="lines",
                                 line=dict(color=vc.BRIGHTER_TEXT_COLOR, width=1),
                                 name="SPY", showlegend=False,
                                 hovertemplate="%{y:.2f}<extra>SPY</extra>"), row=1, col=1)
        # Scale, ticks and range for the window the chart opens on, by Exposure's rules:
        # log only where the window spans 3x or more, ticks spelled out on a log axis.
        # The browser re-decides all three on every zoom (layout.meta.refit, below).
        shown = s[s.index >= open_range(read)[0]]
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
    _zones(fig, colors, 2)
    line_colors = sentiment_colors(palette)
    _index_line(fig, read, "naaim", "NAAIM exposure", line_colors["naaim"], 2)
    _index_line(fig, read, "aaii", "AAII bulls minus bears", line_colors["aaii"], 2)
    if not f.empty:
        fig.update_xaxes(range=open_range(read))
    range_buttons(fig)
    _left_titles(fig)
    _base(fig, 620)
    fig.update_layout(uirevision=UIREVISION)
    # Only the price axis is re-fitted on a zoom: the index panel is pinned to 0-100,
    # which is the point of an index, and fitting it to a window would undo it.
    fig.update_layout(margin=dict(t=44), meta={
        exposure_traces.REFIT_META: {
            "axes": ["yaxis"], "price_axis": "yaxis",
            "log_ratio_min": exposure_traces.LOG_RATIO_MIN, "pad": exposure_traces.REFIT_PAD}})
    return fig


def words_money_figure(read, colors, palette):
    """View 2: two words-against-money pairs on one fixed scale, each with its gap.

    Rows: NAAIM with large specs, NAAIM minus large specs, AAII with non-reportables,
    AAII minus non-reportables. `palette` is the viz palette: the two COT groups wear
    their plot_traces slots (1 and 2), the sentiment lines their own."""
    titles = []
    for words, money, w_name, m_name in PAIRS:
        titles += [f"{w_name}, {m_name}", f"{w_name} minus {m_name}"]
    # Short first title on purpose: the year buttons share its row.
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                        row_heights=[0.31, 0.19, 0.31, 0.19], subplot_titles=titles)
    f = read.frame
    sent = sentiment_colors(palette)
    styles = {"naaim": dict(color=sent["naaim"], width=1.6),
              "aaii": dict(color=sent["aaii"], width=1.6),
              "spec": dict(color=large_spec_color(palette), width=1.6),
              "small": dict(color=small_trader_color(palette), width=1.6)}
    for n, (words, money, w_name, m_name) in enumerate(PAIRS):
        line_row, gap_row = 2 * n + 1, 2 * n + 2
        _zones(fig, colors, line_row)
        for key in (words, money):
            col = f"{key}_idx"
            if col not in f:
                continue
            s = f[col].dropna()
            fig.add_trace(go.Scatter(x=s.index, y=s, mode="lines", line=styles[key],
                                     name=LABELS[key],
                                     hovertemplate="%{y:.0f}<extra>" + LABELS[key] + "</extra>"),
                          row=line_row, col=1)
        j = joint(read, words, money)
        if j.empty:
            continue
        gap = j[f"{words}_idx"] - j[f"{money}_idx"]
        fig.add_trace(go.Bar(x=gap.index, y=gap,
                             marker_color=[colors.bull if v < 0 else colors.bear for v in gap],
                             name=f"{w_name} minus {m_name}", showlegend=False,
                             hovertemplate=("%{y:+.0f}<extra>" + f"{w_name} minus {m_name}"
                                            + "</extra>")),
                      row=gap_row, col=1)
        # No +-100 ticks: the top one sits under the panel title.
        fig.update_yaxes(range=[-100, 100], tickvals=[-50, 0, 50], row=gap_row, col=1)
    if not f.empty:
        fig.update_xaxes(range=open_range(read))
    range_buttons(fig)
    _left_titles(fig)
    fig.update_layout(bargap=0)
    _base(fig, 820)
    fig.update_layout(uirevision=UIREVISION)
    fig.update_layout(margin=dict(t=44), legend=dict(y=-0.04))   # every axis pinned
    return fig


#: The quadrant's window ladder: the app's year buttons, plus Max. The chart opens on
#: the same five years as the time views.
QUADRANT_YEARS = exposure_traces.RANGE_YEARS
QUADRANT_DEFAULT_YEARS = OPEN_YEARS


def quadrant_window(j, years):
    """The joint weeks within `years` of the LATEST joint week, or all of them for None.

    Counted back from the latest joint week rather than from today, because NAAIM's store
    ends a quarter early: a 1-year window from today would hold nine months of NAAIM."""
    if years is None or j.empty:
        return j
    return j[j.index > j.index[-1] - pd.DateOffset(years=years)]


def quadrant_figure(read, colors, years=QUADRANT_DEFAULT_YEARS):
    """View 3: where the latest joint week sits, and how it got there.

    `years` windows the scatter (None is the whole history). Each week is shaded by its
    age within the window, dim to bright, so the drift across quadrants reads over time;
    the last 13 weeks are joined as a path and the latest week is marked."""
    j = quadrant_window(joint(read), years)
    fig = go.Figure()
    for v in (LO, HI):
        fig.add_hline(y=v, line=dict(color=vc.GRID_COLOR, width=1, dash="dot"))
        fig.add_vline(x=v, line=dict(color=vc.GRID_COLOR, width=1, dash="dot"))
    for (x_side, y_side), text in QUADRANT_LABELS.items():
        fig.add_annotation(x=4 if x_side == "low" else 96, y=99 if y_side == "high" else 1,
                           xanchor="left" if x_side == "low" else "right",
                           yanchor="top" if y_side == "high" else "bottom",
                           text=text, showarrow=False,
                           font=dict(size=10, color=hex_to_rgba(vc.TEXT_COLOR, 0.8)))
    hover = "%{customdata}<br>spec %{x:.0f}, NAAIM %{y:.0f}<extra></extra>"
    if not j.empty:
        span = (j.index[-1] - j.index[0]).days or 1
        age = [(d - j.index[0]).days / span for d in j.index]   # 0 oldest, 1 newest
        label = ("every joint week" if years is None
                 else f"joint weeks, last {years} year{'s' if years != 1 else ''}")
        fig.add_trace(go.Scatter(
            x=j["spec_idx"], y=j["naaim_idx"], mode="markers",
            marker=dict(size=6, color=age, cmin=0, cmax=1, showscale=False,
                        colorscale=[[0, hex_to_rgba(vc.TEXT_COLOR, 0.10)],
                                    [1, hex_to_rgba(vc.BRIGHTER_TEXT_COLOR, 0.85)]]),
            customdata=[d.strftime("%Y-%m-%d") for d in j.index], hovertemplate=hover,
            name=f"{label} (older dimmer)"))
        t = j.iloc[-TRAIL_WEEKS:]
        fig.add_trace(go.Scatter(
            x=t["spec_idx"], y=t["naaim_idx"], mode="lines+markers",
            line=dict(color=vc.BRIGHTER_TEXT_COLOR, width=1),
            marker=dict(size=5, color=vc.BRIGHTER_TEXT_COLOR),
            customdata=[d.strftime("%Y-%m-%d") for d in t.index], hovertemplate=hover,
            name=f"last {TRAIL_WEEKS} joint weeks"))
        last = j.iloc[-1]
        fig.add_trace(go.Scatter(
            x=[last["spec_idx"]], y=[last["naaim_idx"]], mode="markers",
            marker=dict(size=13, color=colors.bear, line=dict(color="white", width=1)),
            name=f"latest joint week {j.index[-1]:%Y-%m-%d}",
            hovertemplate="latest<br>spec %{x:.0f}, NAAIM %{y:.0f}<extra></extra>"))
    fig.update_xaxes(range=[0, 100], title=dict(text=f"{POSITIONING_LABEL}, range index",
                                                font=dict(size=11)))
    fig.update_yaxes(range=[0, 100],
                     title=dict(text="NAAIM, range index", font=dict(size=11)))
    _base(fig, 520)
    fig.update_layout(hovermode="closest", legend=dict(y=-0.16))
    return fig


# ── words ─────────────────────────────────────────────────────────────────────

def summary(read):
    """One sentence on the latest joint week, or None when there is none. Says which
    store bounds it, because NAAIM's ends a quarter before the others."""
    j = joint(read)
    if j.empty:
        return None
    week, row = j.index[-1], j.iloc[-1]
    where = quadrant(row["naaim_idx"], row["spec_idx"]) or "Neither at an extreme"
    bound = (f" (NAAIM's store ends {read.last['naaim']:%Y-%m-%d})"
             if "naaim" in read.last else "")
    text = (f"Latest week with both stored, {week:%Y-%m-%d}{bound}: NAAIM at "
            f"{row['naaim_idx']:.0f} on its {read.lookback_years}-year range index, "
            "speculators at "
            f"{row['spec_idx']:.0f}. {where}.")
    small = joint(read, "aaii", "small")
    if not small.empty:
        s_week, s_row = small.index[-1], small.iloc[-1]
        text += (f" AAII at {s_row['aaii_idx']:.0f}, non-reportables at "
                 f"{s_row['small_idx']:.0f} ({s_week:%Y-%m-%d}).")
    return text


def caption(read):
    """Data dates, the lags, the index's one caveat, and the study note."""
    names = {"spy": "SPY", "naaim": "NAAIM", "aaii": "AAII", "spec": "COT positioning"}
    # spec and small come from the same COT report, so one date names both.
    dated = ", ".join(f"{names[k]} {read.last[k]:%Y-%m-%d}" for k in names if k in read.last)
    parts = []
    if dated:
        parts.append(f"Newest stored observation: {dated}.")
    parts.append(
        "Each index places a series between its own lowest (0) and highest (100) reading "
        f"of the trailing {_YEARS_WORD.get(read.lookback_years, f'{read.lookback_years} years')}: "
        "the 4-week average for NAAIM and AAII, the weekly "
        "value for COT positioning. When an old high or low leaves that window the "
        "scale shifts under the line, as it does for the COT index.")
    parts.append(
        "Non-reportables are the open interest left once reportable traders are counted: "
        "small accounts, not retail by definition, and the noisiest group, about 3% of "
        "open interest here. The S&P 500 market folds the full-size contract and the "
        "micros (at a tenth) into ES. Pairing them with AAII is descriptive: the study "
        "tested NAAIM against large specs only.")
    parts.append(
        "NAAIM in the store runs about a quarter behind: its free table is delayed and "
        "current readings are subscriber-only. Every point sits on the Friday of the "
        "week it became public; COT holiday weeks and the 2013, 2018-19 and 2025 "
        "release lapses were public later than drawn.")
    parts.append(STUDY_NOTE)
    if read.lookback_years != DEFAULT_LOOKBACK:
        parts.append(
            f"The study ranked on three years; on this {read.lookback_years}-year index "
            "the lines are not the window it measured, and more weeks sit in a zone "
            "(36-44% of them, against 25-36% at three years).")
    parts.append("Local only: NAAIM and AAII history is licensed data and is not "
                 "published on the site.")
    return parts


# ── caching ───────────────────────────────────────────────────────────────────

def _stamp():
    """Keyed on the stores' dates rather than the clock: a delivery invalidates the
    entry and nothing else does (the tape_context convention)."""
    stamp = []
    for symbol in (NAAIM, AAII_BULL, AAII_BEAR, PRICE):
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
