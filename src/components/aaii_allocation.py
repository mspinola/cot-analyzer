"""AAII's Asset Allocation Survey: members' average split between stocks, bonds and cash,
monthly from November 1987. A card on the sentiment page (local `/sentiment`) and its
published copy (surveys.bluemagicai.com), beside the AAII votes card.

The votes card says what members expect; this one says what they hold. Same layout,
one figure per block in the same wrapping grid (`aaii_votes`, breakpoints
VOTES_SIDE_BY_SIDE_MIN_PX and VOTES_THREE_ACROSS_MIN_PX):

1. **Recent months.** The last four surveys, newest on top, each split into stocks,
   bonds and cash (as AAII headlines them, rounded to a tenth of a point, so a row can
   sum to 99.9 or 100.1).
2. **History.** The average split since the series began, and each share's highest
   month in the last year with its month.
3. **Stocks against their average.** Each recent month's stocks share minus its
   average since 1987, on a fixed +-25 point scale: the stocks share has run 40.8
   (2009-03) to 77.0 (2000-01) around an average of 62.3, so every month on record fits
   (-21.5 to +14.7; measured on the store's 468 months, 2026-11-09). Green above the
   average, red below.

Added 2026-11-09 at the user's request, "just like the AAII sentiment numbers".

**The history chart** (`price_figure`, its own card under this one, added 2026-11-10):
every month since 1987 as a stacked area under SPY, laid out like the sentiment
chart (`sentiment.spy_panel`, its range buttons and refit) so the two cards behave
alike. Stocks stack on the floor so their band's top edge reads as the share itself.
Its own card rather than a fourth block, which has no room for a time axis, and
rather than a line on the sentiment chart, whose panel holds weekly opinion on a
range index, not a monthly holding in percent.

**Dating.** marketdata indexes a survey on its month's last day, and the card labels
it by that month (2026-10). AAII publishes each month's results in the first days of
the next, so the newest row is about a month old by design, not a lag in the store.

**Arithmetic.** Shares are the stored fractions times 100; the average is a plain
mean of every stored month; the high is the largest share in the 365 days ending on
the newest month (12 surveys). Nothing is smoothed or indexed. The store is
marketdata's AAII_ALLOC_* series, built by hand from AAII's member spreadsheet.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import viz_constants as vc
from components import aaii_votes, sentiment
from components.plot_colors import hex_to_rgba

#: (key, store symbol, label), in the order the bar stacks them, left to right.
LEGS = (("stocks", "AAII_ALLOC_STOCKS", "Stocks"),
        ("bonds", "AAII_ALLOC_BONDS", "Bonds"),
        ("cash", "AAII_ALLOC_CASH", "Cash"))
RECENT_MONTHS = 4
HIGH_DAYS = 365
#: The stocks-against-average block's fixed scale, points either side of the average.
STOCK_GAP_LIMIT = 25.0

TITLE = "AAII asset allocation"
SUBTITLE = ("AAII members' average split between stocks (green), bonds (blue) and cash "
            "(grey), percent of portfolio, monthly: the last four surveys, newest first, beside the average "
            "since 1987 and each share's highest month in the last year, and each recent "
            "month's stocks share against its average since 1987. AAII publishes each "
            "month in the first days of the next.")

BONDS_COLOR = "#60A5FA"     # the app palette's blue
#: Text inside each segment: dark on the bright green and blue, white on the grey.
INSIDE_TEXT = {"stocks": "#0e1116", "bonds": "#0e1116", "cash": "#FFFFFF"}


@dataclass(frozen=True)
class Allocation:
    """`recent`: the last RECENT_MONTHS surveys, newest first, a percent column per
    share, indexed by month end. `average`: each share's mean over every stored month,
    percent. `since`: the first stored month. `highs`: share -> (percent, month end)
    over the last HIGH_DAYS. `last`: the newest month."""
    recent: pd.DataFrame
    average: pd.Series
    since: date
    highs: dict
    last: date
    #: Every stored month, oldest first, a percent column per share: the history chart's.
    months: pd.DataFrame | None = None


def legs(get_bars=None):
    """The three shares as percent, one row per stored month, or None when the store
    cannot serve all three (a month missing any share is dropped, never filled)."""
    get_bars = get_bars or sentiment._get_bars
    cols = {}
    for key, symbol, _ in LEGS:
        s = sentiment._close(get_bars, symbol)
        if s is None:
            return None
        cols[key] = s * 100.0
    frame = pd.DataFrame(cols).dropna().sort_index()
    return frame if not frame.empty else None


def summarize(frame, recent=RECENT_MONTHS, high_days=HIGH_DAYS):
    """The cards' numbers from `legs()`, or None for an empty frame."""
    if frame is None or frame.empty:
        return None
    end = frame.index[-1]
    year = frame[frame.index > end - pd.Timedelta(days=high_days)]
    highs = {key: (float(year[key].max()), year[key].idxmax().date()) for key, *_ in LEGS}
    return Allocation(recent=frame.iloc[::-1].head(recent), average=frame.mean(),
                      since=frame.index[0].date(), highs=highs, last=end.date(),
                      months=frame)


def read(get_bars=None):
    """The card's numbers from the store, or None when the survey is not in it."""
    return summarize(legs(get_bars))


def leg_colors(colors):
    """Stocks in the page's bull green, bonds blue, cash the votes card's grey."""
    return {"stocks": colors.bull, "bonds": BONDS_COLOR, "cash": aaii_votes.NEUTRAL_COLOR}


def _bar(key, label, colors):
    fill = leg_colors(colors)[key]
    return dict(orientation="h", name=label, legendgroup=key, showlegend=False,
                marker=dict(color=hex_to_rgba(fill, aaii_votes.BAR_OPACITY)),
                textposition="inside", insidetextanchor="middle",
                insidetextfont=dict(color=INSIDE_TEXT[key], size=11), cliponaxis=False)


def _pct(v):
    """A share's label inside its bar, without the "%": with it, cash's 13.3 lost its
    label to Plotly at phone width (a 33px segment, a 35px label with padding); without,
    a label fits down to a share of about 11. The subtitle says these are percents."""
    return f"{v:.1f}"


def _months(index):
    return [f"{d:%Y-%m}" for d in index]


def recent_figure(alloc, colors):
    """The last RECENT_MONTHS surveys, newest on top."""
    recent = alloc.recent
    rows = _months(recent.index)
    fig = go.Figure()
    for key, _, label in LEGS:
        vals = recent[key].round(1).to_numpy()
        fig.add_trace(go.Bar(x=vals, y=rows, text=[_pct(v) for v in vals],
                             hovertemplate=f"{label} " + "%{x:.1f}%<extra>%{y}</extra>",
                             **_bar(key, label, colors)))
    return aaii_votes._finish(fig, "Recent months", len(rows))


def history_figure(alloc, colors):
    """The average split since the series began, and each share's high of the last
    year with its month beside the bar."""
    high_rows = [f"{label} high" for _, _, label in LEGS]
    rows = ["Average"] + high_rows
    fig = go.Figure()
    for i, (key, _, label) in enumerate(LEGS):
        high, when = alloc.highs[key]
        x = [round(float(alloc.average[key]), 1)] + [None] * len(high_rows)
        x[1 + i] = round(high, 1)
        fig.add_trace(go.Bar(
            x=x, y=rows, text=[_pct(v) if v is not None else "" for v in x],
            hovertemplate=f"{label} " + "%{x:.1f}%<extra>%{y}</extra>",
            **_bar(key, label, colors)))
        fig.add_annotation(x=high, y=high_rows[i], xanchor="left", showarrow=False,
                           text=f"  {when:%Y-%m}", font=dict(size=10, color=vc.TEXT_COLOR))
    return aaii_votes._finish(fig, f"Since {alloc.since:%Y}; highs of the last year",
                              len(rows))


def stock_gap_figure(alloc, colors):
    """Each recent month's stocks share minus its average since the series began, on a
    fixed +-STOCK_GAP_LIMIT scale, green above the average and red below."""
    recent = alloc.recent
    avg = float(alloc.average["stocks"])
    gap = (recent["stocks"] - avg).round(1)
    rows = _months(recent.index)
    color = [hex_to_rgba(colors.bull if v >= 0 else colors.bear, aaii_votes.BAR_OPACITY)
             for v in gap]
    fig = go.Figure(go.Bar(
        x=gap.clip(-STOCK_GAP_LIMIT, STOCK_GAP_LIMIT).to_numpy(), y=rows, orientation="h",
        showlegend=False, marker=dict(color=color),
        text=[f"{v:+.1f}" for v in gap], textposition="outside", cliponaxis=False,
        textfont=dict(size=11, color=vc.BRIGHTER_TEXT_COLOR),
        customdata=recent["stocks"].round(1).to_numpy(),
        hovertemplate=("Stocks %{customdata:.1f}%, %{text} against the average"
                       "<extra>%{y}</extra>")))
    fig.add_vline(x=0, line=dict(color=vc.TEXT_COLOR, width=1))
    # Short: the votes card's spread title is the measured limit at phone width.
    aaii_votes._finish(fig, f"Stocks vs average ({avg:.1f}%)", len(rows))
    fig.update_xaxes(range=[-STOCK_GAP_LIMIT, STOCK_GAP_LIMIT])
    return fig


def figures(alloc, colors):
    """The card's three blocks, (recent, history, gap), laid out by each page like the
    votes card's."""
    return (recent_figure(alloc, colors), history_figure(alloc, colors),
            stock_gap_figure(alloc, colors))



# ── the history chart, its own card ────────────────────────────────────────────

PRICE_TITLE = "AAII allocation against price"
PRICE_SUBTITLE = ("SPY above, and below it AAII members' split between stocks (green), "
                  "bonds (blue) and cash (grey) each month since 1987, stacked to 100% "
                  "of portfolio. Stocks sit on the floor, so their band's top edge is the "
                  "stocks share; the dashed line is its average since 1987. Opens on the "
                  "whole history (SPY's starts in 1993); the buttons zoom in. Each month "
                  "is drawn on its last day, about a month before AAII publishes it.")
#: The sentiment chart's height, so the two price cards read as a pair.
PRICE_HEIGHT = sentiment.PRICE_HEIGHT
#: The stacked panel's scale. A month's rounded shares can sum to 100.1, so a hair of
#: room above 100 keeps the top edge from clipping.
STACK_RANGE = [0, 100.5]
UIREVISION = "aaii-allocation"


def _stack_title(alloc):
    """The stacked panel's title: the newest month, then its three shares, one line
    each so it fits a phone-width panel (the sentiment chart's measured limit)."""
    row = alloc.months.iloc[-1]
    shares = ", ".join(f"{label if i == 0 else label.lower()} {row[key]:.1f}"
                       for i, (key, _, label) in enumerate(LEGS))
    return f"AAII allocation, {alloc.last:%Y-%m}<br>{shares}"


def open_range(alloc, spy):
    """The whole history, from the first month to a little past the newest point
    drawn (SPY's last week, or the newest month when SPY is not in)."""
    months = alloc.months.index
    end = months[-1]
    if spy is not None and not spy.dropna().empty:
        end = max(end, spy.dropna().index[-1])
    return [months[0], end + pd.Timedelta(days=sentiment.OPEN_PAD_DAYS)]


def price_figure(alloc, spy, colors):
    """SPY above the monthly split, stacked, sharing one time axis.

    `spy` is the sentiment read's weekly SPY (`read.frame["spy"]`), or None, which
    leaves the top panel empty. The same layout, buttons, refit and autorange clip as
    `sentiment.price_sentiment_figure`, so the two cards behave alike."""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        row_heights=[0.5, 0.5],
                        subplot_titles=("SPY, total return", _stack_title(alloc)))
    window = open_range(alloc, spy)
    if spy is not None and not spy.dropna().empty:
        sentiment.spy_panel(fig, spy, window[0])
    months = alloc.months
    fills = leg_colors(colors)
    for key, _, label in LEGS:
        fig.add_trace(go.Scatter(
            x=months.index, y=months[key].round(1), mode="lines", name=label,
            stackgroup="allocation", showlegend=False,
            line=dict(color=fills[key], width=1),
            fillcolor=hex_to_rgba(fills[key], aaii_votes.BAR_OPACITY),
            hovertemplate=f"{label} " + "%{y:.1f}%<extra></extra>"), row=2, col=1)
    avg = float(alloc.average["stocks"])
    fig.add_hline(y=avg, line=dict(color=vc.BRIGHTER_TEXT_COLOR, width=1, dash="dash"),
                  opacity=0.8, row=2, col=1)
    fig.update_yaxes(range=STACK_RANGE, tickvals=[0, 25, 50, 75, 100], row=2, col=1)
    fig.update_xaxes(type="date", range=window,
                     autorangeoptions=dict(clipmin=f"{window[0]:%Y-%m-%d}",
                                           clipmax=f"{window[1]:%Y-%m-%d}"))
    sentiment.range_buttons(fig)
    sentiment._left_titles(fig)
    sentiment._base(fig, PRICE_HEIGHT)
    fig.update_layout(uirevision=UIREVISION, margin=dict(t=44), meta=sentiment.PRICE_REFIT)
    return fig
