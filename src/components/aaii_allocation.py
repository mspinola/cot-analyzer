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

**Against a trailing average** (the chart's third panel, added 2026-11-10): each share
minus the mean of its prior 36 months, in points, the current month excluded, as the
sentiment page's columns view sets NAAIM against its trailing average. Asked for as
"indexed like NAAIM"; drawn in points instead because the range index does not carry
over to these series. Measured on the store's 468 months, 2026-11-10
(`scripts/measure_allocation_index.py`), 2008 on:

| range index window | months at 0 or 100 | months in a zone (20/80) |
|---|---|---|
| 1 year (13 months) | 24-31% | 52-58% |
| 3 years (37 months) | 10-12% | 41-43% |
| 5 years (61 months) | 6-8% | 38-49% |

against 2% and 21-36% for NAAIM's 3-year index on the weekly page. Monthly readings
give the window few observations, and some shares barely move: bonds ran 13.8 to 16.6
over the last 37 months, so October's 1.4-point rise put the bond index at 100 and the
cash index at 0, two "extremes" from moves about the size of an ordinary month. In
points the same month reads stocks +1.4, bonds +1.4, cash -2.9, against a typical gap
(standard deviation over the whole history) of 5.4, 2.7 and 4.4. The three are also
not three readings: they sum to 100, and the stocks and cash indexes correlate -0.83
at three years. Like the other surveys the stocks share follows price (its 3-year
index correlates 0.67 with SPY's trailing 12-month return; NAAIM's level, 0.62 with
the 13-week return). Context to read, not a tested signal.

**Dating.** marketdata indexes a survey on its month's last day, and the card labels
it by that month (2026-10). AAII publishes each month's results in the first days of
the next, so the newest row is about a month old by design, not a lag in the store.

**Arithmetic.** Shares are the stored fractions times 100; the average is a plain
mean of every stored month; the high is the largest share in the 365 days ending on
the newest month (12 surveys); the chart's gap is a share minus the plain mean of its
prior 36 months. Nothing is smoothed or indexed. The store is
marketdata's AAII_ALLOC_* series, built by hand from AAII's member spreadsheet.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import viz_constants as vc
from components import aaii_votes, exposure_traces, sentiment
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
            "(grey), percent of portfolio, monthly.")
#: The rest, behind the card's "How to read this" toggle (sentiment.HOW_TO_READ_LABEL).
HOW_TO_READ = ("Three blocks: the last four surveys, newest first; the average since "
               "1987 with each share's highest month in the last year; and each recent "
               "month's stocks share against its average since 1987. AAII publishes "
               "each month in the first days of the next.")

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


def summary(alloc):
    """One sentence on the newest month, for the page's lead beside the sentiment
    surveys' line: the three shares, and how far stocks sit from their average."""
    row = alloc.recent.iloc[0]      # newest first
    gap = row["stocks"] - alloc.average["stocks"]
    side = "above" if gap >= 0 else "below"
    return (f"AAII asset allocation, {alloc.last:%Y-%m}: stocks {row['stocks']:.1f}%, "
            f"bonds {row['bonds']:.1f}%, cash {row['cash']:.1f}%. Stocks are "
            f"{abs(gap):.1f} points {side} their average since {alloc.since.year} "
            f"({alloc.average['stocks']:.1f}%).")


#: The page's note on what the allocation survey follows. The 0.67 is the stocks
#: share's three-year range index against SPY's trailing 12-month return, and the
#: reason for points is in "Against a trailing average" in the module docstring; both
#: measured by scripts/measure_allocation_index.py (2026-11-10, 468 months).
FOLLOWS_NOTE = (
    "Like the sentiment surveys, the stocks share mostly follows price: placed in its "
    "own three-year range it tracks SPY's trailing 12-month return at 0.67, so a high "
    "share usually follows a rally. The chart's bottom panel sets each share against "
    "its own prior three years in points, not as a 0-100 index: on these slow monthly "
    "series an index reads moves of a point or two as extremes. Context, not signal.")


def caption(alloc):
    """The page's notes on the allocation survey: what it is and how it is dated, then
    what it follows. Paragraphs, like `sentiment.caption`."""
    return [
        f"AAII's Asset Allocation Survey is monthly, from {alloc.since:%Y-%m}: members' "
        "average split between stocks, bonds and cash. Each month is dated on its last "
        "day and AAII publishes it in the first days of the next, so the newest month "
        f"here ({alloc.last:%Y-%m}) is about a month old by design.",
        FOLLOWS_NOTE,
    ]


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
PRICE_SUBTITLE = ("SPY above AAII members' monthly split between stocks (green), bonds "
                  "(blue) and cash (grey) since 1987, and each share against its own "
                  "prior three years.")
PRICE_HOW_TO_READ = (
    "The middle panel stacks the shares to 100% of portfolio: stocks sit on the floor, "
    "so their band's top edge is the stocks share, and the dashed line is its average "
    "since 1987. The bottom panel is each share minus its own average over the prior "
    "three years, in points. Opens on the whole history (SPY's starts in 1993); the "
    "buttons zoom in. Each month is drawn on its last day, about a month before AAII "
    "publishes it.")
#: Taller than the sentiment chart's 470 by about the gap panel, so the two panels it
#: shared keep roughly the room they had, and the gap panel gets the most: its three
#: lines cross within a few points of zero and need the height to read apart. At 600
#: with a quarter of it, they ran together (2026-11-10). Rows top to bottom: SPY, the
#: stack, the gaps, about 175, 175 and 200 px.
PRICE_HEIGHT = 720
PRICE_ROWS = (0.32, 0.32, 0.36)
#: The stacked panel's scale. A month's rounded shares can sum to 100.1, so a hair of
#: room above 100 keeps the top edge from clipping.
STACK_RANGE = [0, 100.5]
UIREVISION = "aaii-allocation"
#: The gap panel's trailing window, months: three years, the sentiment page's default
#: lookback. See "Against a trailing average" in the module docstring for why points
#: and not the range index NAAIM is drawn on.
GAP_MONTHS = 36
GAP_YEARS = GAP_MONTHS // 12
#: Row 1 SPY, row 2 the stack, row 3 the gaps. Only SPY and the gaps refit on zoom: the
#: stack is a share of 100 and stays on its fixed scale. The gap panel keeps zero in
#: view, as the sentiment page's column panels do.
GAP_AXIS = "yaxis3"
#: Cash in the gap panel, as a line. The stack's grey (#6b7280, picked to carry white
#: text on a filled bar) is 3.6 to 1 on the page as a 1.5px line and was the hardest of
#: the three to follow. A light grey, and not the mid step between them: #9ca3af sits
#: at the bonds blue's own lightness and the two lines ran together (colour difference
#: 12.4 where 15 is the floor); this one clears every pair against the stocks green and
#: bonds blue for normal and colour-blind vision (18.3 and 9.1 at worst; the dataviz
#: skill's validate_palette.js, dark mode on #1a1a1a, all pairs, 2026-11-10).
CASH_LINE_COLOR = "#d1d5db"
#: The gap panel's zero line: visible, and quieter than the lines that cross it.
ZERO_ALPHA = 0.45
PRICE_REFIT = {exposure_traces.REFIT_META: {
    **sentiment.PRICE_REFIT[exposure_traces.REFIT_META],
    "axes": ["yaxis", GAP_AXIS], "zero": [GAP_AXIS]}}


def trailing_gap(months, n=GAP_MONTHS):
    """Each share minus the mean of its prior `n` months, the current month excluded
    (as `sentiment.trailing_average` does for NAAIM), in points. NaN until `n` months
    precede it. Display arithmetic: a difference of two stored shares, nothing fitted."""
    return months - months.shift(1).rolling(n, min_periods=n).mean()


def _stack_title(alloc):
    """The stacked panel's title: the newest month, then its three shares, one line
    each so it fits a phone-width panel (the sentiment chart's measured limit)."""
    row = alloc.months.iloc[-1]
    shares = ", ".join(f"{label if i == 0 else label.lower()} {row[key]:.1f}"
                       for i, (key, _, label) in enumerate(LEGS))
    return f"AAII allocation, {alloc.last:%Y-%m}<br>{shares}"


def _gap_title(gap):
    """The gap panel's title: what it is, then the newest month's three gaps."""
    row = gap.dropna().iloc[-1] if not gap.dropna().empty else None
    head = f"Each share vs its prior {GAP_YEARS}Y average, points"
    if row is None:
        return head
    shares = ", ".join(f"{label if i == 0 else label.lower()} {row[key]:+.1f}"
                       for i, (key, _, label) in enumerate(LEGS))
    return f"{head}<br>{shares}"


def open_range(alloc, spy):
    """The whole history, from the first month to a little past the newest point
    drawn (SPY's last week, or the newest month when SPY is not in)."""
    months = alloc.months.index
    end = months[-1]
    if spy is not None and not spy.dropna().empty:
        end = max(end, spy.dropna().index[-1])
    return [months[0], end + pd.Timedelta(days=sentiment.OPEN_PAD_DAYS)]


def _fit_gap(fig, gap, window):
    """The gap axis fitted to the months in `window`, zero included, padded 5% as the
    browser's refit pads it, so the chart opens as a button press would leave it."""
    t0, t1 = window
    vals = gap[(gap.index >= t0) & (gap.index <= t1)].to_numpy().ravel()
    vals = vals[~np.isnan(vals)]
    if not len(vals):
        return
    lo, hi = min(vals.min(), 0.0), max(vals.max(), 0.0)
    pad = (hi - lo) * 0.05 or 1.0
    fig.layout[GAP_AXIS].range = [lo - pad, hi + pad]


def price_figure(alloc, spy, colors):
    """SPY, the monthly split stacked, and each share against its trailing average,
    sharing one time axis.

    `spy` is the sentiment read's weekly SPY (`read.frame["spy"]`), or None, which
    leaves the top panel empty. The same layout, buttons, refit and autorange clip as
    `sentiment.price_sentiment_figure`, so the two cards behave alike."""
    gap = trailing_gap(alloc.months).round(1)
    trail = (alloc.months - gap).round(1)     # the prior-36-month mean, for the hover
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                        row_heights=list(PRICE_ROWS),
                        subplot_titles=("SPY, total return", _stack_title(alloc),
                                        _gap_title(gap)))
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
    for key, _, label in LEGS:
        g = gap[key].dropna()
        if g.empty:
            continue
        fig.add_trace(go.Scatter(
            x=g.index, y=g, mode="lines", name=f"{label} vs {GAP_YEARS}Y avg",
            showlegend=False,
            line=dict(color=CASH_LINE_COLOR if key == "cash" else fills[key], width=1.5),
            customdata=trail[key].reindex(g.index),
            hovertemplate=f"{label} vs {GAP_YEARS}Y avg " + "%{y:+.1f} pts "
                          "(avg %{customdata:.1f})<extra></extra>"), row=3, col=1)
    fig.update_yaxes(range=STACK_RANGE, tickvals=[0, 25, 50, 75, 100], row=2, col=1)
    fig.update_xaxes(type="date", range=window,
                     autorangeoptions=dict(clipmin=f"{window[0]:%Y-%m-%d}",
                                           clipmax=f"{window[1]:%Y-%m-%d}"))
    sentiment.range_buttons(fig)
    sentiment._left_titles(fig)
    sentiment._base(fig, PRICE_HEIGHT)
    # After _base, which turns every zero line off. The grid colour is the page's own
    # background in the dark theme, so the line takes the text colour, faded.
    fig.update_yaxes(zeroline=True, zerolinecolor=hex_to_rgba(vc.TEXT_COLOR, ZERO_ALPHA),
                     zerolinewidth=1, row=3, col=1)
    fig.update_layout(uirevision=UIREVISION, margin=dict(t=44), meta=PRICE_REFIT)
    _fit_gap(fig, gap, window)
    return fig
