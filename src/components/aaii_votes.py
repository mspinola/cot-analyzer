"""AAII's vote split, as the survey reports it: the share of members bullish, neutral
and bearish on stocks over the next six months, week by week. A card on the sentiment
page (local `/sentiment`) and its published copy (surveys.bluemagicai.com).

The index chart above it turns AAII into one number (bulls minus bears, placed on a
trailing range). This card keeps the three shares apart, because a bearish week with
few neutrals and one with many read differently, and the spread alone cannot say
which. Two parts, one figure:

1. **Recent weeks.** The last four surveys, newest on top, each a bar split into the
   three shares (they sum to 100, within 0.2 for rounding in AAII's file).
2. **History.** The average split since the series begins (1987), and each share's
   highest week over the last year with that week's date.

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

**Arithmetic.** Shares are the stored fractions times 100. The average is a plain mean
of every stored week; the high is the largest share in the 365 days ending on the
newest week (53 surveys). Nothing is smoothed or indexed. This repo computes no metrics
of its own, and none of this is one: it is the survey's own numbers, rearranged.
"""
from dataclasses import dataclass
from datetime import date

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import viz_constants as vc
from components import sentiment
from components.plot_colors import hex_to_rgba

AAII_NEUTRAL = "AAII_NEUTRAL"
#: (key, store symbol, label), in the order the bar stacks them, left to right.
LEGS = (("bullish", sentiment.AAII_BULL, "Bullish"),
        ("neutral", AAII_NEUTRAL, "Neutral"),
        ("bearish", sentiment.AAII_BEAR, "Bearish"))
RECENT_WEEKS = 4
HIGH_DAYS = 365

TITLE = "AAII votes"
SUBTITLE = ("The share of AAII members bullish (green), neutral (grey) and bearish (red) "
            "on stocks over the next six months. Top: the last four surveys, newest "
            "first. Bottom: the average since 1987, and each vote's highest week in the "
            "last year.")

ROW_HEIGHT = 30             # pixels per bar row
NEUTRAL_COLOR = "#6b7280"   # grey that keeps white text readable
BAR_OPACITY = 0.85
#: Text inside each segment: dark on the bright green and red, white on the grey.
INSIDE_TEXT = {"bullish": "#0e1116", "neutral": "#FFFFFF", "bearish": "#0e1116"}
#: Past 100 by a little: rounded shares sum to as much as 100.2 in AAII's file, and a
#: segment that overruns the axis loses its label (2026-10-08 did, at 100.1).
X_RANGE = [0, 100.5]


@dataclass(frozen=True)
class Votes:
    """`recent`: the last RECENT_WEEKS surveys, newest first, a percent column per leg,
    indexed by stored date. `average`: each leg's mean over every stored week, percent.
    `since`: the first stored week. `highs`: leg -> (percent, date) over the last
    HIGH_DAYS. `last`: the newest stored week."""
    recent: pd.DataFrame
    average: pd.Series
    since: date
    highs: dict
    last: date


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


def summarize(frame, recent=RECENT_WEEKS, high_days=HIGH_DAYS):
    """The card's numbers from `legs()`, or None for an empty frame."""
    if frame is None or frame.empty:
        return None
    last = frame.index[-1]
    year = frame[frame.index > last - pd.Timedelta(days=high_days)]
    highs = {key: (float(year[key].max()), year[key].idxmax().date()) for key, *_ in LEGS}
    return Votes(recent=frame.iloc[::-1].head(recent), average=frame.mean(),
                 since=frame.index[0].date(), highs=highs, last=last.date())


def read(get_bars=None):
    """The card's numbers from the store, or None when AAII is not in it."""
    return summarize(legs(get_bars))


def leg_colors(colors):
    """Bull and bear from the page's colour set (the columns use the same), grey between."""
    return {"bullish": colors.bull, "neutral": NEUTRAL_COLOR, "bearish": colors.bear}


def figure(votes, colors):
    """Both blocks as one figure: stacked horizontal bars, 0 to 100, no zoom."""
    fills = leg_colors(colors)
    recent = votes.recent
    spread = (recent["bullish"] - recent["bearish"]).to_numpy()
    recent_rows = [f"{d:%Y-%m-%d}" for d in recent.index]
    # Short labels: a long one widens the label column and squeezes the bars until
    # Plotly hides the narrow segments' text at phone width. The detail is in the title.
    high_rows = [f"{label} high" for _, _, label in LEGS]
    history_rows = ["Average"] + high_rows

    fig = make_subplots(rows=2, cols=1, vertical_spacing=0.16,
                        row_heights=[len(recent_rows), len(history_rows)],
                        subplot_titles=("Recent weeks",
                                        f"Since {votes.since:%Y}; highs of the last year"))
    for i, (key, _, label) in enumerate(LEGS):
        bar = dict(orientation="h", name=label, legendgroup=key,
                   marker=dict(color=hex_to_rgba(fills[key], BAR_OPACITY)
                               if fills[key].startswith("#") else fills[key]),
                   textposition="inside", insidetextanchor="middle",
                   insidetextfont=dict(color=INSIDE_TEXT[key], size=11),
                   cliponaxis=False)
        vals = recent[key].round(1).to_numpy()
        fig.add_trace(go.Bar(
            x=vals, y=recent_rows, text=[f"{v:.1f}%" for v in vals], customdata=spread,
            hovertemplate=(f"{label} " + "%{x:.1f}%  (bulls minus bears %{customdata:+.1f})"
                           "<extra>%{y}</extra>"),
            **bar), row=1, col=1)
        # History: the average row stacks all three; each high row carries one leg.
        high, _ = votes.highs[key]
        x = [round(float(votes.average[key]), 1)] + [None] * len(high_rows)
        x[1 + i] = round(high, 1)
        fig.add_trace(go.Bar(
            x=x, y=history_rows, text=[f"{v:.1f}%" if v is not None else "" for v in x],
            hovertemplate=f"{label} " + "%{x:.1f}%<extra>%{y}</extra>",
            showlegend=False, **bar), row=2, col=1)
        fig.add_annotation(x=high, y=high_rows[i], xref="x2", yref="y2", xanchor="left",
                           text=f"  {votes.highs[key][1]:%Y-%m-%d}", showarrow=False,
                           font=dict(size=10, color=vc.TEXT_COLOR))

    fig.update_layout(
        barmode="stack", bargap=0.25,
        height=ROW_HEIGHT * (len(recent_rows) + len(history_rows)) + 120,
        margin=dict(l=8, r=8, t=30, b=8),
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
    for ann in fig.layout.annotations[:2]:
        ann.font = dict(size=11, color=vc.TEXT_COLOR)
        ann.x, ann.xanchor, ann.align = 0, "left", "left"
    return fig
