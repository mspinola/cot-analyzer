"""AAII's vote split, as the survey reports it: the share of members bullish, neutral
and bearish on stocks over the next six months, week by week. A card on the sentiment
page (local `/sentiment`) and its published copy (surveys.bluemagicai.com).

The index chart above it turns AAII into one number (bulls minus bears, placed on a
trailing range). This card keeps the three shares apart, because a bearish week with
few neutrals and one with many read differently, and the spread alone cannot say
which. Three blocks, each its own figure in a wrapping grid (one figure with several
columns cannot reflow, and stacked on a desktop the bars ran the page's full width,
all colour): all three across on a wide page, two on a medium one, stacked on a phone.

1. **Recent weeks.** The last four surveys, newest on top, each a bar split into the
   three shares (they sum to 100, within 0.2 for rounding in AAII's file).
2. **History.** The average split since the series begins (1987), and each share's
   highest week over the last year with that week's date.
3. **Bulls minus bears.** The recent weeks' spread, the number the chart above indexes,
   as bars on a fixed +-50 scale (red below zero, green above), against a dashed line
   at its official average since 1987. Added 2026-11-09 at the user's request; the
   weekly columns lower on the page chart the same spread week by week.

Added 2026-11-09 at the user's request, after AAII's own results page, which shows the
same two blocks. The store reproduces that page: the four recent weeks match row for
row, the three one-year highs match to the decimal (49.5, 31.4, 53.3 on the day), and
the averages since 1987 come out 37.6 / 30.9 / 31.5 against AAII's 37.5 / 31.0 / 31.5.
AAII's own averages are presumably taken over a slightly different set of weeks; these
are the store's, every stored week weighted equally.

**Dates are the store's**, which is a day after AAII's "week ending" label (the member
file dates a survey on Thursday, the page names the Wednesday it closed): the store's
2026-10-29 is AAII's "week ending 10/28". The rest of the sentiment page dates AAII the
same way, so the card agrees with the chart beside it.

**Provisional weeks.** The store's AAII legs end where the member spreadsheet last
downloaded ends; marketdata's AAII_*_PROVISIONAL carry the weeks since, typed from AAII's
public results page (rounded to a tenth of a point). They reach the recent rows only,
after the official end and only when all three legs are present, drawn faint with
"prov" beside the date, as the chart above draws them hollow and faint. The average
and the one-year highs stay on official weeks, so a rounded hand-typed week never sets
a long-run number; the highs' year ends on the newest official week.

**Arithmetic.** Shares are the stored fractions times 100. The average is a plain mean
of every stored week; the high is the largest share in the 365 days ending on the
newest week (53 surveys). Nothing is smoothed or indexed. This repo computes no metrics
of its own, and none of this is one: it is the survey's own numbers, rearranged.
"""
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go

import viz_constants as vc
from components import sentiment
from components.plot_colors import hex_to_rgba

AAII_NEUTRAL = "AAII_NEUTRAL"
#: Each leg's provisional series (NOT official; see the module docstring).
PROVISIONAL = {"bullish": sentiment.AAII_BULL_PROVISIONAL,
               "neutral": "AAII_NEUTRAL_PROVISIONAL",
               "bearish": sentiment.AAII_BEAR_PROVISIONAL}
#: Beside a provisional week's date, in the row label (short: labels set the bars' width).
PROVISIONAL_TAG = "prov"
#: (key, store symbol, label), in the order the bar stacks them, left to right.
LEGS = (("bullish", sentiment.AAII_BULL, "Bullish"),
        ("neutral", AAII_NEUTRAL, "Neutral"),
        ("bearish", sentiment.AAII_BEAR, "Bearish"))
RECENT_WEEKS = 4
HIGH_DAYS = 365

TITLE = "AAII votes"
SUBTITLE = ("The share of AAII members bullish (green), neutral (grey) and bearish (red) "
            "on stocks over the next six months.")
#: The rest, behind the card's "How to read this" toggle (sentiment.HOW_TO_READ_LABEL).
HOW_TO_READ = ("Three blocks: the last four surveys, newest first; the average since "
               "1987 with each vote's highest week in the last year; and each recent "
               "week's bulls minus bears against its average since 1987 (dashed), with "
               "its percentile since 1987 in brackets.")

ROW_HEIGHT = 30             # pixels per bar row
NEUTRAL_COLOR = "#6b7280"   # grey that keeps white text readable
BAR_OPACITY = 0.85
#: Text inside each segment: dark on the bright green and red, white on the grey.
INSIDE_TEXT = {"bullish": "#0e1116", "neutral": "#FFFFFF", "bearish": "#0e1116"}
#: Text inside a provisional (faint) segment, whatever its leg.
PROVISIONAL_TEXT = vc.BRIGHTER_TEXT_COLOR
#: Pixels each half adds to its rows: the title above, the margins.
FIGURE_CHROME = 44
#: The card's blocks: two side by side from VOTES_SIDE_BY_SIDE_MIN_PX, all three from
#: VOTES_THREE_ACROSS_MIN_PX, one column below. Each block needs about 310px to keep its
#: date labels and every segment's text (all 18 showed at 309 on a phone, and at 332 a
#: block at 768); three across at 768 would give each about 220. Both are Bootstrap's
#: md and xl breakpoints, so the app page's columns break at the same widths.
VOTES_SIDE_BY_SIDE_MIN_PX = 768
VOTES_THREE_ACROSS_MIN_PX = 1200
#: The spread block's fixed scale, points either side of zero: the same length means the
#: same spread every week. AAII's spread has run -54.0 (1990-10-19) to +62.9 (2003-06-26);
#: 0.68% of weeks fall outside +-50 and draw pinned to the edge with their true value
#: beside them (`scripts/measure_aaii_spread_range.py`, 2,047 official weeks, 2026-11-09).
SPREAD_LIMIT = 50.0
#: Past 100 by a little: rounded shares sum to as much as 100.2 in AAII's file, and a
#: segment that overruns the axis loses its label (2026-10-08 did, at 100.1).
X_RANGE = [0, 100.5]


@dataclass(frozen=True)
class Votes:
    """`recent`: the last RECENT_WEEKS surveys, newest first, a percent column per leg,
    indexed by stored date. `average`: each leg's mean over every stored week, percent.
    `since`: the first stored week. `highs`: leg -> (percent, date) over the last
    HIGH_DAYS. `last`: the newest week shown. `provisional`: the dates in `recent` that
    are provisional, oldest first. `spread_pct`: each `recent` row's bulls minus bears
    as a percentile (1-100) of every official week's, in `recent`'s order."""
    recent: pd.DataFrame
    average: pd.Series
    since: date
    highs: dict
    last: date
    provisional: tuple = ()
    spread_pct: tuple = ()


def legs(get_bars=None):
    """The three shares as percent, one row per stored week, or None when the store
    cannot serve all three (a week missing any leg is dropped, never filled)."""
    get_bars = get_bars or sentiment._get_bars
    cols = {}
    for key, symbol, _ in LEGS:
        s = sentiment._close(get_bars, symbol)
        if s is None:
            return None
        cols[key] = s * 100.0
    frame = pd.DataFrame(cols).dropna().sort_index()
    return frame if not frame.empty else None


def provisional_legs(official, get_bars=None):
    """The provisional weeks after `official`'s last week, percent, one row per week, or
    None. Never stands in for missing official legs, and a week missing any of its three
    provisional legs is dropped, as an official one is."""
    if official is None or official.empty:
        return None
    get_bars = get_bars or sentiment._get_bars
    cols = {}
    for key, symbol in PROVISIONAL.items():
        s = sentiment._close(get_bars, symbol)
        if s is None:
            return None
        cols[key] = s * 100.0
    frame = pd.DataFrame(cols).dropna().sort_index()
    frame = frame[frame.index > official.index[-1]]
    return frame if not frame.empty else None


def summarize(frame, recent=RECENT_WEEKS, high_days=HIGH_DAYS, provisional=None):
    """The card's numbers from `legs()`, or None for an empty frame. `provisional`
    (`provisional_legs()`) joins the recent rows only."""
    if frame is None or frame.empty:
        return None
    end = frame.index[-1]
    year = frame[frame.index > end - pd.Timedelta(days=high_days)]
    highs = {key: (float(year[key].max()), year[key].idxmax().date()) for key, *_ in LEGS}
    shown, late = frame, ()
    if provisional is not None and not provisional.empty:
        late = provisional[provisional.index > end]
        shown = pd.concat([frame, late])
        late = tuple(late.index)
    rows = shown.iloc[::-1].head(recent)
    return Votes(recent=rows, average=frame.mean(),
                 since=frame.index[0].date(), highs=highs, last=shown.index[-1].date(),
                 provisional=late, spread_pct=spread_percentiles(frame, rows))


def spread_percentiles(official, rows):
    """Each row's bulls minus bears as a percentile of every OFFICIAL week's: the share
    of official weeks at or below it, 1 to 100. A provisional row is ranked against the
    official weeks but never joins them, as for the average and the highs."""
    history = (official["bullish"] - official["bearish"]).to_numpy()
    values = (rows["bullish"] - rows["bearish"]).to_numpy()
    return tuple(max(1, int(round(float((history <= v).mean()) * 100))) for v in values)


def ordinal(n):
    """1st, 2nd, 3rd, 4th ... 11th, 12th, 13th ... 21st, 22nd ... 100th."""
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def read(get_bars=None):
    """The card's numbers from the store, or None when AAII is not in it."""
    official = legs(get_bars)
    return summarize(official, provisional=provisional_legs(official, get_bars))


def leg_colors(colors):
    """Bull and bear from the page's colour set (the columns use the same), grey between."""
    return {"bullish": colors.bull, "neutral": NEUTRAL_COLOR, "bearish": colors.bear}


def _bar(key, label, colors):
    """The look every segment shares: its leg's colour, its share inside, no clipping."""
    fill = leg_colors(colors)[key]
    return dict(orientation="h", name=label, legendgroup=key, showlegend=False,
                marker=dict(color=hex_to_rgba(fill, BAR_OPACITY) if fill.startswith("#")
                            else fill),
                textposition="inside", insidetextanchor="middle",
                insidetextfont=dict(color=INSIDE_TEXT[key], size=11), cliponaxis=False)


def _finish(fig, title, rows):
    """Layout for one half: fixed 0 to 100, no zoom, rows read top down, a left title."""
    fig.update_layout(
        barmode="stack", bargap=0.25, height=ROW_HEIGHT * rows + FIGURE_CHROME,
        margin=dict(l=8, r=8, t=26, b=4),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=vc.TEXT_COLOR, size=11), hovermode="closest",
        hoverlabel=dict(bgcolor="#0e1116", bordercolor=vc.GRID_COLOR,
                        font=dict(color=vc.HOVER_TEXT_COLOR)),
        # No legend: Plotly caps one at the plot's width, which at phone width wraps
        # the three entries; the subtitle names the colours and the high rows show them.
        showlegend=False,
        uniformtext=dict(minsize=8, mode="hide"),
    )
    fig.update_xaxes(range=X_RANGE, showticklabels=False, showgrid=False, zeroline=False,
                     fixedrange=True)
    # Newest week on top, the average above the highs: categories read top down. Typed
    # as categories, or Plotly reads the ISO labels as dates and runs them oldest first.
    fig.update_yaxes(type="category", autorange="reversed", automargin=True,
                     showgrid=False, fixedrange=True,
                     tickfont=dict(size=10, color=vc.TEXT_COLOR), ticksuffix="  ")
    fig.add_annotation(text=title, x=0, y=1, xref="paper", yref="paper", xanchor="left",
                       yanchor="bottom", align="left", showarrow=False,
                       font=dict(size=11, color=vc.TEXT_COLOR))
    return fig


def recent_figure(votes, colors):
    """The last RECENT_WEEKS surveys, newest on top, provisional ones faint."""
    recent = votes.recent
    spread = (recent["bullish"] - recent["bearish"]).to_numpy()
    late = recent.index.isin(votes.provisional)
    rows = [f"{d:%Y-%m-%d} {PROVISIONAL_TAG}" if p else f"{d:%Y-%m-%d}"
            for d, p in zip(recent.index, late)]
    fig = go.Figure()
    for key, _, label in LEGS:
        bar = _bar(key, label, colors)
        if late.any():
            bar["marker"] = dict(bar["marker"], opacity=np.where(
                late, sentiment.PROVISIONAL_OPACITY, 1.0))
            # Light text on a faint segment: the dark text the bright bars carry sat on a
            # dimmed fill over the dark page and could not be read.
            bar["insidetextfont"] = dict(bar["insidetextfont"], color=np.where(
                late, PROVISIONAL_TEXT, INSIDE_TEXT[key]).tolist())
        vals = recent[key].round(1).to_numpy()
        fig.add_trace(go.Bar(
            x=vals, y=rows, text=[f"{v:.1f}%" for v in vals], customdata=spread,
            hovertemplate=(f"{label} " + "%{x:.1f}%  (bulls minus bears %{customdata:+.1f})"
                           "<extra>%{y}</extra>"), **bar))
    title = "Recent weeks (faint: provisional)" if late.any() else "Recent weeks"
    return _finish(fig, title, len(rows))


def history_figure(votes, colors):
    """The average split since the series began, and each vote's high of the last year
    with its date beside the bar. Official weeks only (`summarize`)."""
    # Short labels: a long one widens the label column and squeezes the bars until
    # Plotly hides the narrow segments' text at phone width. The detail is in the title.
    high_rows = [f"{label} high" for _, _, label in LEGS]
    rows = ["Average"] + high_rows
    fig = go.Figure()
    for i, (key, _, label) in enumerate(LEGS):
        # The average row stacks all three; each high row carries one leg.
        high, when = votes.highs[key]
        x = [round(float(votes.average[key]), 1)] + [None] * len(high_rows)
        x[1 + i] = round(high, 1)
        fig.add_trace(go.Bar(
            x=x, y=rows, text=[f"{v:.1f}%" if v is not None else "" for v in x],
            hovertemplate=f"{label} " + "%{x:.1f}%<extra>%{y}</extra>",
            **_bar(key, label, colors)))
        fig.add_annotation(x=high, y=high_rows[i], xanchor="left", showarrow=False,
                           text=f"  {when:%Y-%m-%d}", font=dict(size=10, color=vc.TEXT_COLOR))
    return _finish(fig, f"Since {votes.since:%Y}; highs of the last year", len(rows))


def spread_figure(votes, colors):
    """Bulls minus bears for the recent weeks, on a fixed +-SPREAD_LIMIT scale, red below
    zero and green above, provisional weeks faint; the official average since the series
    began is a dashed line across them (the rows stay four, so the blocks line up)."""
    recent = votes.recent
    spread = (recent["bullish"] - recent["bearish"]).round(1)
    late = recent.index.isin(votes.provisional)
    rows = [f"{d:%Y-%m-%d} {PROVISIONAL_TAG}" if p else f"{d:%Y-%m-%d}"
            for d, p in zip(recent.index, late)]
    fills = leg_colors(colors)
    color = [hex_to_rgba(fills["bullish" if v >= 0 else "bearish"], BAR_OPACITY)
             for v in spread]
    shown = spread.clip(-SPREAD_LIMIT, SPREAD_LIMIT)
    fig = go.Figure(go.Bar(
        x=shown.to_numpy(), y=rows, orientation="h", showlegend=False,
        marker=dict(color=color, opacity=np.where(late, sentiment.PROVISIONAL_OPACITY, 1.0)
                    if late.any() else None),
        customdata=[[b, r, f"{v:+.1f}", ordinal(p) if p else "?"] for b, r, v, p in zip(
            recent["bullish"].round(1), recent["bearish"].round(1), spread,
            votes.spread_pct or (None,) * len(spread))],
        hovertemplate=("Bulls minus bears %{customdata[2]}, %{customdata[3]} percentile "
                       "since 1987  (bullish %{customdata[0]:.1f}, bearish "
                       "%{customdata[1]:.1f})<extra>%{y}</extra>")))
    avg = round(float(votes.average["bullish"] - votes.average["bearish"]), 1)
    fig.add_vline(x=0, line=dict(color=vc.TEXT_COLOR, width=1))
    fig.add_vline(x=avg, line=dict(color=vc.TEXT_COLOR, width=1, dash="dash"))
    # The average named in the title, not by its line: a note at the line's top ran into
    # the title wherever the block is narrow. Short: a longer title ran 34px past a
    # phone-width block. The subtitle says the average runs since 1987.
    _finish(fig, f"Bulls minus bears (avg {avg:+.1f} dashed)", len(rows))
    fig.update_xaxes(range=[-SPREAD_LIMIT, SPREAD_LIMIT])
    # Each label on the EMPTY side of zero, beyond the dashed average: a bearish week's
    # right of it, a bullish week's left of zero. At the bar's own end, as first drawn,
    # "-14.3 (13th)" met the date labels at phone width (1px apart) and a -40 week
    # would have run into them; the empty half always has about half the plot.
    for row, v, label in zip(rows, spread, _spread_labels(spread, votes.spread_pct)):
        bearish = v < 0
        fig.add_annotation(x=max(0.0, avg) if bearish else min(0.0, avg), y=row,
                           xref="x", yref="y", xanchor="left" if bearish else "right",
                           text=f"  {label}" if bearish else f"{label}  ", showarrow=False,
                           font=dict(size=11, color=vc.BRIGHTER_TEXT_COLOR))
    return fig


def _spread_labels(spread, pct):
    """'-14.3 (13th)': the spread, and its percentile since 1987 in brackets (the
    subtitle says so; the block title has no room). Without percentiles, the spread."""
    if not pct:
        return [f"{v:+.1f}" for v in spread]
    return [f"{v:+.1f} ({ordinal(p)})" for v, p in zip(spread, pct)]


def figures(votes, colors):
    """The card's three blocks, (recent, history, spread), laid out by each page at
    VOTES_SIDE_BY_SIDE_MIN_PX and VOTES_THREE_ACROSS_MIN_PX."""
    return (recent_figure(votes, colors), history_figure(votes, colors),
            spread_figure(votes, colors))
