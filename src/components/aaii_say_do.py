"""What AAII members say against what they hold: the weekly bullish vote, averaged per
month, beside the monthly stocks share of the Asset Allocation Survey, each ranked
against its own prior three years. A card on the sentiment page (local `/sentiment`)
and its published copy (surveys.bluemagicai.com), closing the page under the
allocation history.

**Why it exists.** The votes card shows opinion and the allocation card shows money, and
nothing put them side by side. Measured on the store before building (2026-11-26,
1987-11 to 2026-10, 468 months): the monthly bullish mean and the stocks share
correlate 0.34 in level and 0.37 in 3-month change, and in 19.4% of the 432 ranked
months their trailing three-year percentiles (this module's arithmetic) sit 50 points
or more apart. They move together loosely, and come apart often enough to be worth
drawing. The split is lopsided: 15.3% of months hold more stock than they sound, 4.2%
sound more bullish than they hold, which fits the price confound below.
Reproducer: `scripts/measure_say_do.py`. Asked for as the
"say against do" card after that measurement. Context to read, not a tested signal:
nothing here was chosen by what SPY did next.

**Arithmetic.**

- *Bullish per month*: the plain mean of the month's weekly bullish shares, official and
  provisional weeks alike (the votes card shows both), dated on the month's last day as
  marketdata dates the allocation survey. A month with fewer than MIN_WEEKS readings is
  dropped (only 1987-07, the survey's first, has fewer: 2 weeks).
- *Percentile*: each month's value as a percentile of the PRIOR `WINDOW_MONTHS`
  months, the current month excluded (as `aaii_allocation.trailing_gap` excludes it),
  by `sentiment.percentile_of`: the share at or below, 1 to 100. NaN until the window
  fills. A trailing window and not the whole history, because both series drift
  (stocks 47% of portfolio in 1987-89 and 67% in the 2020s, decade means), and a
  percentile of every month since 1987 partly measures the drift.
- *Gap*: bullish percentile minus stocks percentile, in percentile points, -99 to +99.
  Above zero, members talk more bullish than they are invested, by their own recent
  standards; below zero, they hold more stock than their vote suggests.
- Only months where both series exist: the allocation survey publishes about a month
  after its month ends, so the newest weekly votes wait for it.

**One known confound, said on the card.** The stocks share partly follows price
mechanically: with no rebalancing a rally raises it. So a rally can push the "do" line
up, and a selloff down, while nobody changed their mind. The bullish vote follows price
too (AAII's level tracks SPY's trailing 13-week return at 0.44, `sentiment`), so the gap
is not a clean opinion-minus-action measure.

**Colours.** The bullish line is the votes card's green (`sentiment.card_green`). The
stocks line cannot be the allocation card's stocks green, which is the same colour, so
it takes the light grey the allocation chart's cash line was validated with against
that green (`aaii_allocation.CASH_LINE_COLOR`, 18.3 to 1 and better for normal and
colour-blind vision). The gap's bars take each line's colour by sign, so the bar says
which line is ahead.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import viz_constants as vc
from components import aaii_allocation, aaii_votes, sentiment
from components.plot_colors import hex_to_rgba

#: The trailing window each series is ranked against, months: three years, the page's
#: default lookback and the allocation chart's gap window.
WINDOW_MONTHS = aaii_allocation.GAP_MONTHS
WINDOW_YEARS = WINDOW_MONTHS // 12
#: A month's bullish mean needs this many weekly readings.
MIN_WEEKS = 3
#: The gap's "far apart" lines, percentile points either side of zero. Descriptive:
#: 19% of months sat this far apart or more (module docstring), not a tuned level.
FAR_APART = 50
GAP_RANGE = [-100, 100]
PCT_RANGE = [0, 101]

TITLE = "AAII: what members say against what they hold"
SUBTITLE = ("AAII's bullish vote (green) against members' stocks share (grey), each "
            "ranked against its own prior three years, and the gap between them.")
HOW_TO_READ = (
    "The middle panel ranks each month's average bullish vote and its stocks share of "
    "portfolio against the same series' prior 36 months, as a percentile (50 is a "
    "typical month for that series). The bottom panel is the bullish percentile minus "
    "the stocks percentile: above zero, members sound more bullish than they are "
    "invested, by their own recent standards; below zero, they hold more stock than "
    "they sound. The dashed lines at plus and minus 50 mark the two far apart, which "
    "happened in about a fifth of months since 1987. The stocks share rises with a "
    "rally even when nobody buys, so part of a gap can be price alone. Monthly, so it "
    "ends on the newest allocation survey, about a month old.")

SAY_COLOR_FN = sentiment.card_green
DO_COLOR = aaii_allocation.CASH_LINE_COLOR

HEIGHT = 640
#: The chart opens on the last OPEN_YEARS, Max one click away. Over the whole history
#: the two percentile lines (each swinging 0 to 100 within a year or two) ran into one
#: band at desktop width and worse on a phone (2026-11-26 render); at five to ten
#: years they read apart. The gap bars read at any span.
OPEN_YEARS = 10
ROWS = (0.30, 0.35, 0.35)
UIREVISION = "aaii-say-do"


@dataclass(frozen=True)
class SayDo:
    """`months`: one row per month both surveys cover, oldest first, with `bullish`
    (monthly mean, percent), `stocks` (percent), `bullish_pct` and `stocks_pct`
    (trailing percentiles, NaN until the window fills) and `gap` (their difference).
    `last`: the newest month."""
    months: pd.DataFrame
    last: date


def monthly_bullish(weekly, min_weeks=MIN_WEEKS):
    """The weekly bullish shares (percent, indexed by survey date) as a mean per
    calendar month, dated on the month's last day; months short of `min_weeks`
    readings dropped."""
    s = weekly.dropna()
    grouped = s.resample("ME")
    mean, count = grouped.mean(), grouped.count()
    return mean[count >= min_weeks]


def trailing_percentile(series, n=WINDOW_MONTHS):
    """Each value as a percentile (1 to 100) of the `n` values before it, itself
    excluded; NaN until `n` precede it."""
    vals = series.to_numpy(dtype=float)
    out = np.full(len(vals), np.nan)
    for i in range(n, len(vals)):
        out[i] = sentiment.percentile_of(vals[i - n:i], vals[i])
    return pd.Series(out, index=series.index)


def build(weekly_bullish, stocks, n=WINDOW_MONTHS):
    """The card's frame from the weekly bullish shares and the monthly stocks share
    (both percent), or None when they share no month."""
    if weekly_bullish is None or stocks is None:
        return None
    frame = pd.concat({"bullish": monthly_bullish(weekly_bullish),
                       "stocks": stocks.dropna()}, axis=1).dropna().sort_index()
    if frame.empty:
        return None
    frame["bullish_pct"] = trailing_percentile(frame["bullish"], n)
    frame["stocks_pct"] = trailing_percentile(frame["stocks"], n)
    frame["gap"] = frame["bullish_pct"] - frame["stocks_pct"]
    return SayDo(months=frame, last=frame.index[-1].date())


def read(get_bars=None):
    """The card's numbers from the store, or None when either survey is missing."""
    official = aaii_votes.legs(get_bars)
    if official is None:
        return None
    late = aaii_votes.provisional_legs(official, get_bars)
    weekly = official["bullish"] if late is None else pd.concat(
        [official["bullish"], late["bullish"]])
    alloc = aaii_allocation.legs(get_bars)
    return build(weekly, None if alloc is None else alloc["stocks"])


def _newest(sd):
    """The newest month with both percentiles, or None while the window fills."""
    ranked = sd.months.dropna(subset=["gap"])
    return None if ranked.empty else ranked.iloc[-1]


def _pct_title(sd):
    """Short enough for a phone-width panel (about 40 characters a line clipped there,
    2026-11-26); the raw shares are in the hover."""
    head = f"Percentile of each one's prior {WINDOW_YEARS}Y"
    row = _newest(sd)
    if row is None:
        return head
    return (f"{head}<br>{row.name:%Y-%m}: bullish {row['bullish_pct']:.0f}, "
            f"stocks {row['stocks_pct']:.0f}")


def _gap_title(sd):
    head = "Say minus do, percentile points"
    row = _newest(sd)
    if row is None:
        return head
    g = row["gap"]
    side = (" (say more than they hold)" if g > 0
            else " (hold more than they say)" if g < 0 else "")
    return f"{head}<br>{row.name:%Y-%m}: {g:+.0f}{side}"


def summary(sd):
    """One sentence on the newest month, or None while the window fills."""
    row = _newest(sd)
    if row is None:
        return None
    return (f"AAII say against do, {row.name:%Y-%m}: the bullish vote is at the "
            f"{sentiment.ordinal(int(row['bullish_pct']))} percentile of its prior "
            f"{WINDOW_YEARS} years and the stocks share at the "
            f"{sentiment.ordinal(int(row['stocks_pct']))}, a gap of {row['gap']:+.0f}.")


def figure(sd, spy, colors):
    """SPY, the two trailing percentiles, and their gap, on one time axis.

    `spy` is the sentiment read's weekly SPY, or None, which leaves the top panel
    empty. Range buttons and SPY's refit as the allocation chart has them; the two
    lower panels keep fixed scales (a percentile, a difference of two), so only SPY
    refits on zoom."""
    m = sd.months
    say, do = SAY_COLOR_FN(colors), DO_COLOR
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        row_heights=list(ROWS),
                        subplot_titles=("SPY, total return", _pct_title(sd),
                                        _gap_title(sd)))
    ranked = m.dropna(subset=["gap"])
    start = ranked.index[0] if not ranked.empty else m.index[0]
    start = max(start, m.index[-1] - pd.DateOffset(years=OPEN_YEARS))
    end = m.index[-1]
    if spy is not None and not spy.dropna().empty:
        sentiment.spy_panel(fig, spy, start)
        end = max(end, spy.dropna().index[-1])
    window = [start, end + pd.Timedelta(days=sentiment.OPEN_PAD_DAYS)]
    for key, label, color, raw in (("bullish_pct", "Bullish vote", say, "bullish"),
                                   ("stocks_pct", "Stocks held", do, "stocks")):
        fig.add_trace(go.Scatter(
            x=ranked.index, y=ranked[key], mode="lines", name=label, showlegend=False,
            line=dict(color=color, width=1.5), customdata=ranked[raw].round(1),
            hovertemplate=(f"{label} " + "%{y:.0f} (%{customdata:.1f}%)"
                           "<extra></extra>")), row=2, col=1)
    gap = ranked["gap"]
    fig.add_trace(go.Bar(
        x=gap.index, y=gap, name="Say minus do", showlegend=False,
        marker=dict(color=[hex_to_rgba(say if v >= 0 else do, aaii_votes.BAR_OPACITY)
                           for v in gap], line=dict(width=0)),
        hovertemplate="Say minus do %{y:+.0f}<extra></extra>"), row=3, col=1)
    for y in (FAR_APART, -FAR_APART):
        fig.add_hline(y=y, line=dict(color=vc.TEXT_COLOR, width=1, dash="dash"),
                      opacity=0.6, row=3, col=1)
    fig.add_hline(y=50, line=dict(color=vc.TEXT_COLOR, width=1, dash="dot"),
                  opacity=0.5, row=2, col=1)
    fig.update_yaxes(range=PCT_RANGE, tickvals=[0, 25, 50, 75, 100], row=2, col=1)
    fig.update_yaxes(range=GAP_RANGE, tickvals=[-100, -50, 0, 50, 100], row=3, col=1)
    fig.update_xaxes(type="date", range=window,
                     autorangeoptions=dict(clipmin=f"{window[0]:%Y-%m-%d}",
                                           clipmax=f"{window[1]:%Y-%m-%d}"))
    sentiment.range_buttons(fig)
    sentiment._left_titles(fig)
    sentiment._base(fig, HEIGHT)
    fig.update_yaxes(zeroline=True, zerolinewidth=1,
                     zerolinecolor=hex_to_rgba(vc.TEXT_COLOR, aaii_allocation.ZERO_ALPHA),
                     row=3, col=1)
    fig.update_layout(uirevision=UIREVISION, margin=dict(t=44), bargap=0,
                      meta=sentiment.PRICE_REFIT)
    return fig
