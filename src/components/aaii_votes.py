"""AAII's vote split, as the survey reports it: the share of members bullish, neutral
and bearish on stocks over the next six months, week by week. A card on the sentiment
page (local `/sentiment`) and its published copy (surveys.bluemagicai.com).

The index chart above it turns AAII into one number (bulls minus bears, placed on a
trailing range). This card keeps the three shares apart, because a bearish week with
few neutrals and one with many read differently, and the spread alone cannot say
which. Four blocks, each its own figure in a wrapping grid (one figure with several
columns cannot reflow, and stacked on a desktop the bars ran the page's full width,
all colour): two across from a medium width, stacked on a phone, and all four across
only in the app at its widest (the published page's 1180px column never gives four
enough room).

1. **Recent weeks.** The last four surveys, newest on top, each a bar split into the
   three shares (they sum to 100, within 0.2 for rounding in AAII's file).
2. **History.** The average split since the series begins (1987), and each share's
   highest week over the last year with that week's date.
3. **Bulls minus bears.** The recent weeks' spread, the number the chart above indexes,
   as bars on a fixed +-50 scale (red below zero, green above), against a dashed line
   at its official average since 1987. Added 2026-11-09 at the user's request; the
   weekly columns lower on the page chart the same spread week by week.
4. **Percentile.** The newest week's three shares as percentiles (`sentiment.percentile_of`:
   the share of weeks at or below it) over three histories, one row each: every
   official week since 1987, the last three years and the last year. Each row carries
   three dots, green bullish, grey neutral, red bearish, each with its percentile
   printed inside. Added 2026-11-12 at the user's request with one row per vote against
   the full history; regrouped the same day into one row per history ("show since 1987,
   last 3 years, last year, with each bar having three colored circles"), as the NAAIM
   card's percentile block reads. The windows say where the week sits in the recent
   regime, which the full history cannot. Like the NAAIM card's, they rank the newest
   week against the window's EARLIER weeks, provisional ones included, since the
   member spreadsheet can end a few weeks before the newest; the since-1987 row stays
   official, as the average and the highs do. A dotted median and no 10/90 lines,
   which would read as zones nothing has tested.
   Neutral has drifted (decade means 40.7% in 1987-89, 28.0% in the 2020s; bearish
   27.3% and 36.7%), so its percentile partly measures the drift; HOW_TO_READ says so.

Added 2026-11-09 at the user's request, after AAII's own results page, which shows the
first two blocks. The store reproduces that page: the four recent weeks match row for
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
after the official end and only when all three legs are present, drawn and dated as
any other week (the page's footer names them, `sentiment.provisional_note`). The average
and the one-year highs stay on official weeks, so a rounded hand-typed week never sets
a long-run number; the highs' year ends on the newest official week.

**Arithmetic.** Shares are the stored fractions times 100. The average is a plain mean
of every stored week; the high is the largest share in the 365 days ending on the
newest week (53 surveys). Nothing is smoothed or indexed. This repo computes no metrics
of its own, and none of this is one: it is the survey's own numbers, rearranged.
"""
from dataclasses import dataclass, field
from datetime import date

import pandas as pd
import plotly.graph_objects as go

import viz_constants as vc
from components import sentiment
from components.plot_colors import INK_PIVOT, blend_over, hex_to_rgba, relative_luminance

AAII_NEUTRAL = "AAII_NEUTRAL"
#: Each leg's provisional series (NOT official; see the module docstring).
PROVISIONAL = {"bullish": sentiment.AAII_BULL_PROVISIONAL,
               "neutral": "AAII_NEUTRAL_PROVISIONAL",
               "bearish": sentiment.AAII_BEAR_PROVISIONAL}
#: (key, store symbol, label), in the order the bar stacks them, left to right.
LEGS = (("bullish", sentiment.AAII_BULL, "Bullish"),
        ("neutral", AAII_NEUTRAL, "Neutral"),
        ("bearish", sentiment.AAII_BEAR, "Bearish"))
RECENT_WEEKS = 4
HIGH_DAYS = 365
#: The percentile block's rows after the full official history, (label, days).
WINDOWS = (("Last 3 years", 3 * HIGH_DAYS), ("Last year", HIGH_DAYS))

TITLE = "AAII votes"
SUBTITLE = ("The share of AAII members bullish (green), neutral (grey) and bearish (red) "
            "on stocks over the next six months.")
#: The rest, behind the card's "How to read this" toggle (sentiment.HOW_TO_READ_LABEL).
HOW_TO_READ = ("Three blocks: the last four surveys, newest first; the average since "
               "1987 with each vote's highest week in the last year; and each recent "
               "week's bulls minus bears against its average since 1987 (dashed), with "
               "its percentile since 1987 in brackets. The newest week's percentiles "
               "are in the Percentiles card at the top of the page.")

#: Pixels per bar row. 30 until 2026-11-12, when the three grid cards (NAAIM, votes,
#: allocation) took 428px each at 1280 and did not fit a screen together ("can compress
#: vertically a bit to get more on a single screen"). At 22 a bar is 16.5px (bargap
#: 0.25), still room for the 11px text inside it.
ROW_HEIGHT = 22
NEUTRAL_COLOR = "#6b7280"   # grey that keeps white text readable
BAR_OPACITY = 0.85
#: Text inside each segment: dark on the bright green and red, white on the grey.
INSIDE_TEXT = {"bullish": "#0e1116", "neutral": "#FFFFFF", "bearish": "#0e1116",
               "stocks": "#0e1116", "bonds": "#0e1116"}
#: The segments filled with the toned-down green (this card's and the allocation
#: card's), whose ink `segment_ink` picks from the fill, and the ink for a dark one.
GREEN_KEYS = ("bullish", "stocks")
#: Every segment filled with a toned-down colour, the red and the bonds blue included.
TONED_KEYS = GREEN_KEYS + ("bearish", "bonds")
LIGHT_INK = "#FFFFFF"
#: Pixels each half adds to its rows: the title above (BLOCK_TOP), the margins, and a
#: few for the category axis's half-row padding. 44 (top 26, bottom 4), then 30 (top
#: 22), both 2026-11-12. ROW_HEIGHT stays 22: measured that day, 20px rows had Plotly
#: shrink the numbers inside the bars to about 8px and 18px rows hid them all, so the
#: trims come from the margins and the card header instead.
FIGURE_CHROME = 24
BLOCK_TOP = 18
#: The card's blocks: two side by side from VOTES_SIDE_BY_SIDE_MIN_PX, all four from
#: VOTES_ALL_ACROSS_MIN_PX, one column below. Each block needs about 310px to keep its
#: date labels and every segment's text (all 18 showed at 309 on a phone, and at 332 a
#: block at 768); three across at 768 would give each about 220. Four across waits for
#: 1400 (about 315 a block), where three had gone across from 1200: four at 1200 gave
#: each about 265. Both are Bootstrap's md and xxl breakpoints. The published page
#: uses only the first: since 2026-11-12 it sits in the other monitors' 1180px column,
#: where four across is 268 a block at any window width, and the titles ran past it.
VOTES_SIDE_BY_SIDE_MIN_PX = 768
VOTES_ALL_ACROSS_MIN_PX = 1400
#: Since 2026-11-12 each survey's card has three blocks and the percentiles card three,
#: so the published page puts three across from here: at 1100px a block is about 326px
#: in the 1180px column, over the 310 that keeps every label.
THREE_ACROSS_MIN_PX = 1100
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
    as a percentile (1-100) of every official week's, in `recent`'s order.
    `latest_pct`: vote -> (percentile 1-100, word) for the newest row's share against
    every official week's (`sentiment.percentile_of`, `sentiment.percentile_word`:
    "96th", or "highest" / "lowest"), the percentile block's first row. `window_pct`:
    (label, {vote: (percentile, word)}) per WINDOWS row, the newest row ranked against
    the window's earlier weeks, provisional included."""
    recent: pd.DataFrame
    average: pd.Series
    since: date
    highs: dict
    last: date
    provisional: tuple = ()
    spread_pct: tuple = ()
    latest_pct: dict = field(default_factory=dict)
    window_pct: tuple = ()
    #: The newest week's bulls minus bears over the same three histories as
    #: `latest_pct` / `window_pct`, keyed SPREAD_KEY: since the start (official weeks)
    #: and per WINDOWS row (every week shown, provisional included).
    spread_latest_pct: dict = field(default_factory=dict)
    spread_window_pct: tuple = ()


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
    official_spread, shown_spread = _spread_frame(frame), _spread_frame(shown)
    return Votes(recent=rows, average=frame.mean(),
                 since=frame.index[0].date(), highs=highs, last=shown.index[-1].date(),
                 provisional=late, spread_pct=spread_percentiles(frame, rows),
                 latest_pct=latest_percentiles(frame, rows.iloc[0]),
                 window_pct=window_percentiles(shown, rows.iloc[0]),
                 spread_latest_pct=latest_percentiles(
                     official_spread, shown_spread.iloc[-1], SPREAD_LEGS),
                 spread_window_pct=window_percentiles(
                     shown_spread, shown_spread.iloc[-1], legs=SPREAD_LEGS))


#: The bulls-minus-bears percentile block's one leg, in `LEGS`' shape.
SPREAD_KEY = "spread"
#: The bulls-minus-bears block's dot colour: the palette's third slot (amber on the
#: default, Non-Reportable elsewhere in the app, drawn nowhere on this page), toned
#: down by the cards' step. It first took AAII's line green, which next to the votes
#: block read as one more bullish dot ("change the bulls-bears color", 2026-11-12).
SPREAD_SLOT = 2
SPREAD_LEGS = ((SPREAD_KEY, None, "Bulls minus bears"),)


def _spread_frame(frame):
    """Bulls minus bears, in points, as a one-column frame `latest_percentiles` reads."""
    return pd.DataFrame({SPREAD_KEY: frame["bullish"] - frame["bearish"]})


def window_percentiles(shown, row, windows=WINDOWS, legs=LEGS):
    """Each window's (label, {leg: (percentile, word)}) for `row`, the newest week of
    `shown`, against the window's weeks BEFORE it: every week shown, provisional
    included, ending on the newest (`window_pct` in `Votes`)."""
    end = shown.index[-1]
    out = []
    for label, days in windows:
        window = shown[(shown.index > end - pd.Timedelta(days=days)) & (shown.index < end)]
        out.append((label, latest_percentiles(window, row, legs)))
    return tuple(out)


def spread_percentiles(official, rows):
    """Each row's bulls minus bears as a percentile of every OFFICIAL week's: the share
    of official weeks at or below it, 1 to 100. A provisional row is ranked against the
    official weeks but never joins them, as for the average and the highs."""
    history = (official["bullish"] - official["bearish"]).to_numpy()
    values = (rows["bullish"] - rows["bearish"]).to_numpy()
    return tuple(sentiment.percentile_of(history, v) for v in values)


def latest_percentiles(official, row, legs=LEGS):
    """Each leg of `row` (the newest, perhaps provisional) as a percentile word of
    every OFFICIAL row's, `sentiment.percentile_word`."""
    out = {}
    for key, *_ in legs:
        history, value = official[key].to_numpy(), float(row[key])
        out[key] = (sentiment.percentile_of(history, value),
                    sentiment.percentile_word(history, value))
    return out


ordinal = sentiment.ordinal


def read(get_bars=None):
    """The card's numbers from the store, or None when AAII is not in it."""
    official = legs(get_bars)
    return summarize(official, provisional=provisional_legs(official, get_bars))


def leg_colors(colors):
    """Bull and bear from the page's colour set, grey between. Both are toned down by
    the survey lines' own step (`sentiment.card_green`, `card_red`), so the green
    matches AAII's line and columns and the red does not outshout it."""
    return {"bullish": sentiment.card_green(colors), "neutral": NEUTRAL_COLOR,
            "bearish": sentiment.card_red(colors)}


def segment_ink(key, fill):
    """The ink printed inside a segment. The grey keeps its own. The green, red and blue
    are toned down from palette colours, and palettes disagree about how bright those
    are, so their ink is chosen from the fill as drawn: the dark ink where it still
    reads (4.8 to 1 on the default palette's green), white on a darker fill (its red
    and blue, 6.1 and 5.0 to 1)."""
    if key not in TONED_KEYS or not str(fill).startswith("#"):
        return INSIDE_TEXT[key]
    drawn = blend_over(fill, BAR_OPACITY)
    return INSIDE_TEXT[key] if relative_luminance(drawn) > INK_PIVOT else LIGHT_INK


def _bar(key, label, colors):
    """The look every segment shares: its leg's colour, its share inside, no clipping."""
    fill = leg_colors(colors)[key]
    return dict(orientation="h", name=label, legendgroup=key, showlegend=False,
                marker=dict(color=hex_to_rgba(fill, BAR_OPACITY) if fill.startswith("#")
                            else fill),
                textposition="inside", insidetextanchor="middle",
                insidetextfont=dict(color=segment_ink(key, fill), size=11),
                cliponaxis=False)


def _finish(fig, title, rows):
    """Layout for one half: fixed 0 to 100, no zoom, rows read top down, a left title."""
    fig.update_layout(
        barmode="stack", bargap=0.25, height=ROW_HEIGHT * rows + FIGURE_CHROME,
        margin=dict(l=8, r=8, t=BLOCK_TOP, b=2),
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
    """The last RECENT_WEEKS surveys, newest on top."""
    recent = votes.recent
    spread = (recent["bullish"] - recent["bearish"]).to_numpy()
    rows = [f"{d:%Y-%m-%d}" for d in recent.index]
    fig = go.Figure()
    for key, _, label in LEGS:
        bar = _bar(key, label, colors)
        vals = recent[key].round(1).to_numpy()
        fig.add_trace(go.Bar(
            x=vals, y=rows, text=[f"{v:.1f}%" for v in vals], customdata=spread,
            hovertemplate=(f"{label} " + "%{x:.1f}%  (bulls minus bears %{customdata:+.1f})"
                           "<extra>%{y}</extra>"), **bar))
    return _finish(fig, "Recent weeks", len(rows))


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
    zero and green above; the official average since the series
    began is a dashed line across them (the rows stay four, so the blocks line up)."""
    recent = votes.recent
    spread = (recent["bullish"] - recent["bearish"]).round(1)
    rows = [f"{d:%Y-%m-%d}" for d in recent.index]
    fills = leg_colors(colors)
    color = [hex_to_rgba(fills["bullish" if v >= 0 else "bearish"], BAR_OPACITY)
             for v in spread]
    shown = spread.clip(-SPREAD_LIMIT, SPREAD_LIMIT)
    fig = go.Figure(go.Bar(
        x=shown.to_numpy(), y=rows, orientation="h", showlegend=False,
        marker=dict(color=color),
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


#: The percentile block: a faint 0-100 track per row, the reading a dot on it in its
#: leg's colour, the median a dotted line. No 10/90 or 20/80 lines: those would read as
#: zones, and nothing on the page has tested a percentile threshold.
TRACK_ALPHA = 0.18
TRACK_WIDTH = 6
MARKER_SIZE = 13
#: Past this percentile the label sits left of its dot, so it stays inside the block.
LABEL_FLIP = 75
#: A little past 0 and 100, so a dot at either end is not cut in half.
PERCENTILE_X_RANGE = [-3, 103]


def percentile_figure(rows, fills, title, n_rows, since, hovers=None):
    """The percentile block shared with the allocation and NAAIM cards. `rows`: (key,
    label, value text, percentile 1-100, word) per leg, top down; `fills`: key -> the
    leg's colour; `n_rows`: the height in rows, the card's other blocks', so the blocks
    line up; `since`: the history's first year, for the hover; `hovers`: each row's
    hover text instead, for rows ranked against different histories. Not dated: a dated
    title ran 25px past its block four across at 1440, and the recent block's top row
    dates it."""
    track = hex_to_rgba(vc.TEXT_COLOR, TRACK_ALPHA)
    names = [f"{label} {value}".strip() for _, label, value, _, _ in rows]
    hovers = hovers or [None] * len(rows)
    fig = go.Figure()
    for name in names:
        fig.add_trace(go.Scatter(x=[0, 100], y=[name, name], mode="lines",
                                 line=dict(color=track, width=TRACK_WIDTH),
                                 hoverinfo="skip", showlegend=False))
    for (key, label, value, pct, word), name, hover in zip(rows, names, hovers):
        hover = hover or f"{label} {value}: {sentiment.percentile_phrase(word, since)}"
        fig.add_trace(go.Scatter(
            x=[pct], y=[name], mode="markers+text", text=[word],
            textposition="middle left" if pct > LABEL_FLIP else "middle right",
            textfont=dict(size=11, color=vc.BRIGHTER_TEXT_COLOR),
            marker=dict(color=fills[key], size=MARKER_SIZE,
                        line=dict(color=vc.BRIGHTER_TEXT_COLOR, width=1)),
            hovertemplate=f"{hover}<extra></extra>",
            cliponaxis=False, showlegend=False))
    fig.add_vline(x=50, line=dict(color=vc.TEXT_COLOR, width=1, dash="dot"))
    _finish(fig, title, n_rows)
    fig.update_xaxes(range=PERCENTILE_X_RANGE)
    return fig


#: The windows block's dots: large enough to carry "100" inside at 9px.
DOT_SIZE = 19
DOT_TEXT_SIZE = 9
#: Dots in one row closer than this many percentile points would cover each other (a
#: 19px dot spans about 8 points of a phone's 230px track, under 5 of a desktop's), so
#: `dodge` spreads them sideways to this spacing, about their shared position. The
#: number inside each dot is its percentile; the dot's place is within a few points of
#: it. On 2026-11-12 bullish and neutral were both the 8th percentile of the last year
#: (one dot until dodged), and neutral 5 and bullish 13 touched at 800px. Nudging them
#: above and below their row was tried first and ran into the next row's dots.
DOT_SPACING = 9


def dodge(values, spacing=DOT_SPACING, lo=0.0, hi=100.0):
    """Where to draw dots at `values` on one 0-100 track so none covers another: each
    group of dots closer than `spacing` is spread to `spacing` apart, centred on the
    group's mean and kept inside [lo, hi]. A dot clear of the others stays put."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    groups = [[i] for i in order]

    def placed(group):
        centre = sum(values[i] for i in group) / len(group)
        xs = [centre + (j - (len(group) - 1) / 2) * spacing for j in range(len(group))]
        shift = max(lo - xs[0], 0.0) + min(hi - xs[-1], 0.0)
        return [x + shift for x in xs]

    merged = True
    while merged:                     # merge until no two groups overlap once spread
        merged = False
        for g in range(len(groups) - 1):
            if placed(groups[g + 1])[0] - placed(groups[g])[-1] < spacing:
                groups[g:g + 2] = [groups[g] + groups[g + 1]]
                merged = True
                break
    out = [0.0] * len(values)
    for group in groups:
        for i, x in zip(group, placed(group)):
            out[i] = x
    return out


def dot_ink(fill):
    """The number printed inside a dot: dark on a light fill, white on a dark one."""
    if not str(fill).startswith("#"):
        return LIGHT_INK
    return INSIDE_TEXT["bullish"] if relative_luminance(fill) > INK_PIVOT else LIGHT_INK


#: The percentile blocks' height in rows: three histories, a little air between them.
PERCENTILE_ROWS = 3.5


def dots_figure(rows, legs, fills, values, title, n_rows=PERCENTILE_ROWS):
    """A percentile block: one track per history, top down, and on each a dot per leg
    with its percentile printed inside. `rows`: (name, {leg key: (percentile 1-100,
    word)}, what the history is in words, for the hover), top down; `legs`: (key,
    label) in drawing order; `fills`: key -> colour; `values`: key -> the reading as
    printed in the hover ("30.8%"). Dots that would cover each other are dodged
    sideways (`dodge`); the number inside is always the percentile. Shared by the
    percentiles card's NAAIM, AAII votes and AAII allocation blocks."""
    names = [name for name, *_ in rows]
    keys = [key for key, _ in legs]
    places = [dict(zip(keys, dodge([pcts[key][0] for key in keys]))) for _, pcts, _ in rows]
    track = hex_to_rgba(vc.TEXT_COLOR, TRACK_ALPHA)
    fig = go.Figure()
    for name in names:
        fig.add_trace(go.Scatter(x=[0, 100], y=[name, name], mode="lines",
                                 line=dict(color=track, width=TRACK_WIDTH),
                                 hoverinfo="skip", showlegend=False))
    for key, label in legs:
        ranks = [pcts[key] for _, pcts, _ in rows]
        hovers = [f"{label} {values[key]}: {word} "
                  f"{'of' if word in (sentiment.HIGHEST, sentiment.LOWEST) else 'percentile of'}"
                  f" {what}" for (pct, word), (_, _, what) in zip(ranks, rows)]
        fig.add_trace(go.Scatter(
            x=[place[key] for place in places], y=names, mode="markers+text", name=label,
            text=[str(pct) for pct, _ in ranks], textposition="middle center",
            textfont=dict(size=DOT_TEXT_SIZE, color=dot_ink(fills[key])),
            marker=dict(color=fills[key], size=DOT_SIZE,
                        line=dict(color=vc.BRIGHTER_TEXT_COLOR, width=1)),
            customdata=hovers, hovertemplate="%{customdata}<extra></extra>",
            cliponaxis=False, showlegend=False))
    # Under the dots: drawn above, it ran through a dot at the median ("51").
    fig.add_vline(x=50, line=dict(color=vc.TEXT_COLOR, width=1, dash="dot"), layer="below")
    _finish(fig, title, n_rows)
    fig.update_xaxes(range=PERCENTILE_X_RANGE)
    return fig


PERCENTILE_NAME = "AAII votes"
SPREAD_PERCENTILE_NAME = "AAII"


def legend_title(name, legs, fills):
    """A percentiles block's title naming its legs, each word in its dots' colour and
    bold ("AAII votes: bullish, neutral, bearish"): out of its own card the block lost
    that card's subtitle, the only place the colours were named (2026-11-12, "the aaii
    votes and aaii allocation loses there color context")."""
    words = ", ".join(f'<span style="color:{fills[key]}"><b>{label.lower()}</b></span>'
                      for key, label in legs)
    return f"{name}: {words}"


def spread_figure_percentiles(votes, palette, name=SPREAD_PERCENTILE_NAME):
    """The newest week's bulls minus bears as a percentile over the three histories, one
    dot a row in the palette's amber (SPREAD_SLOT), the tile's
    number (its 8th since 1987 on 2026-11-12) with the two windows beside it. On the
    percentiles card since 2026-11-12, where the allocation block had been ("replaced
    with an AAII bulls-bears percentile view")."""
    spread = float(votes.recent.iloc[0]["bullish"] - votes.recent.iloc[0]["bearish"])
    rows = [(f"Since {votes.since:%Y}", votes.spread_latest_pct,
             f"every week since {votes.since:%Y}")]
    rows += [(label, pcts, f"the {label.lower()}") for label, pcts in votes.spread_window_pct]
    legs = [(SPREAD_KEY, "bulls minus bears")]
    fills = {SPREAD_KEY: sentiment.card_tone(palette[SPREAD_SLOT])}
    return dots_figure(rows, legs, fills, {SPREAD_KEY: f"{spread:+.1f}"},
                       legend_title(name, legs, fills))


def latest_figure(votes, colors, name=PERCENTILE_NAME):
    """The newest week's three shares as percentiles over three histories, one row each
    (since the series began, the last three years, the last year), each row three dots
    in the votes' colours with the percentile inside. Where AAII's own card shows a raw
    share against a bar, this says whether the share is unusual, and against what. On
    the percentiles card since 2026-11-12, no longer in this card's grid."""
    newest = votes.recent.iloc[0]
    rows = [(f"Since {votes.since:%Y}", votes.latest_pct, f"every week since {votes.since:%Y}")]
    rows += [(label, pcts, f"the {label.lower()}") for label, pcts in votes.window_pct]
    legs, fills = [(key, label) for key, _, label in LEGS], leg_colors(colors)
    return dots_figure(rows, legs, fills, {key: f"{newest[key]:.1f}%" for key, *_ in LEGS},
                       legend_title(name, legs, fills))


def figures(votes, colors):
    """The card's three blocks, (recent, history, spread). The fourth, the percentile
    block, moved to the percentiles card on 2026-11-12 (`latest_figure`)."""
    return (recent_figure(votes, colors), history_figure(votes, colors),
            spread_figure(votes, colors))
