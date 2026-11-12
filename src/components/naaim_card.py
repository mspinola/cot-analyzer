"""NAAIM's recent weeks, as the survey reports them: the active managers' average equity
exposure, from 200% short to 200% long. A card on the sentiment page (local
`/sentiment`) and its published copy (surveys.bluemagicai.com), beside the AAII votes
and allocation cards and laid out as they are (`aaii_votes`: four blocks in a wrapping
grid, two across from a medium width). Added 2026-11-12 at the user's request ("the aaii
votes and aaii asset allocation cards provide nice visuals on the recent past of these
two surveys. create a similar card for naaim").

1. **Recent weeks.** The last four readings, newest on top, as bars on a fixed 0 to
   `X_MAX` scale, each labelled with its percentile since 2006 in brackets, against a
   dashed line at the official average since 2006.
2. **Change.** Each recent week's move from the week before, on a fixed +-`CHANGE_LIMIT`
   scale, green up (more exposure) and red down. NAAIM swings hard week to week (median
   move 7.5 points, 90th percentile 21.5, largest 42.1, 2006-2026 official weeks), and
   a reading's direction is half of what a reader takes from it.
3. **History.** The average since 2006, and the last year's average, high and low, the
   high and low dated.
4. **Percentile.** The newest reading's percentile over three histories: every official
   week since 2006 (the tile's number), and the last three years and the last year. The
   two windows say where the week sits in the recent regime, which the full history
   cannot (on 2026-11-12, 72.9 was the 51st percentile since 2006).

**Provisional weeks.** NAAIM's official series runs about a quarter behind (the free
table), and marketdata's NAAIM_EXPOSURE_PROVISIONAL carries the weeks since, read off
StockCharts' chart (`sentiment` module docstring). They reach the recent rows, drawn as
any other week (the page's footer names them, `sentiment.provisional_note`). The
average since 2006 and the since-2006 percentile stay on official weeks, as the AAII
votes card's do. The LAST-YEAR and LAST-THREE-YEARS numbers do not: they take every week
shown, provisional included, because the official series alone would end each window a
quarter before the newest week, and a "last year" that stops in August describes a year
the reader is not in. The provisional values match the official ones to a median 0.19
points over 249 shared weeks (marketdata's `scripts/read_naaim_chart.py`).

**Dates are the store's**, NAAIM's survey date (a Wednesday, a holiday week's Tuesday or
Thursday), not the Friday the rest of the page charts the week on.

**Arithmetic.** The readings are NAAIM's own. The average is a plain mean, the change a
difference, the percentiles `sentiment.percentile_of` (the share of the history at or
below the reading); a window's percentile ranks the newest week against the window's
earlier weeks. Nothing is smoothed or indexed.
"""
from dataclasses import dataclass
from datetime import date

import pandas as pd
import plotly.graph_objects as go

import viz_constants as vc
from components import aaii_votes, sentiment
from components.plot_colors import INK_PIVOT, blend_over, hex_to_rgba, relative_luminance

RECENT_WEEKS = 4
YEAR_DAYS = 365
#: The percentile block's windows, (label, days), after the full official history.
WINDOWS = (("Last 3 years", 3 * YEAR_DAYS), ("Last year", YEAR_DAYS))

TITLE = "NAAIM exposure"
SUBTITLE = ("Active managers' average stock exposure as NAAIM reports it each week, "
            "from 200% short to 200% long.")
#: The rest, behind the card's "How to read this" toggle (sentiment.HOW_TO_READ_LABEL).
HOW_TO_READ = ("Three blocks: the last four readings, newest first, each with its "
               "percentile since 2006 in brackets and the average since 2006 dashed; "
               "each week's change from the week before (green up, red down); and the "
               "average since 2006 with the last year's average, high and low. The "
               "last-year numbers include the newest weeks, which NAAIM publishes for "
               "free only after about three months. The newest reading's percentiles "
               "are in the Percentiles card at the top of the page.")

BAR_OPACITY = aaii_votes.BAR_OPACITY
#: The reading's fixed scale. NAAIM's official weeks run -3.6 (2011-10-05) to 120.6
#: (2017-12-13), 99% of them under 106.3; a week below zero draws as an empty bar with
#: its value beside it.
X_MAX = 125.0
X_RANGE = [0, X_MAX]
#: Past this reading the recent block's label goes inside its bar: "100.0 (99th)" past
#: the end would run off a phone-width block.
LABEL_INSIDE_FROM = 95.0
#: Past this reading the history block's high or low date goes inside its bar, at its
#: start; below it the date follows the bar's end (60.2's fit at 375px, 102.8's did not).
DATE_INSIDE_FROM = 80.0
#: The change block's fixed scale: the largest official move is 42.1 points.
CHANGE_LIMIT = 45.0
DARK_INK = "#0e1116"
LIGHT_INK = "#FFFFFF"


@dataclass(frozen=True)
class Naaim:
    """`recent`: the last RECENT_WEEKS readings, newest first, indexed by survey date.
    `change`: each `recent` reading minus the week before it (NaN for the first week of
    the series). `recent_pct`: each `recent` reading's percentile (1-100) of every
    official week. `average`: the official mean. `since`: the first official week.
    `year`: {"average": float, "high": (value, date), "low": (value, date)} over the
    YEAR_DAYS ending on the newest week shown, provisional weeks included. `latest`:
    (label, percentile, word, hover) per percentile row, top down. `last`: the newest
    week shown. `provisional`: the dates in the series shown that are provisional."""
    recent: pd.Series
    change: pd.Series
    recent_pct: tuple
    average: float
    since: date
    year: dict
    latest: tuple
    last: date
    provisional: tuple = ()


def series(get_bars=None):
    """(official, provisional after its end), each a Close series or None."""
    get_bars = get_bars or sentiment._get_bars
    official = sentiment._close(get_bars, sentiment.NAAIM)
    if official is None:
        return None, None
    prov = sentiment._close(get_bars, sentiment.NAAIM_PROVISIONAL)
    if prov is not None:
        prov = prov[prov.index > official.index[-1]]
        prov = prov if not prov.empty else None
    return official, prov


def summarize(official, provisional=None, recent=RECENT_WEEKS):
    """The card's numbers, or None without an official series."""
    if official is None or official.empty:
        return None
    shown, late = official, ()
    if provisional is not None and not provisional.empty:
        shown = pd.concat([official, provisional]).sort_index()
        late = tuple(provisional.index)
    rows = shown.iloc[::-1].head(recent)
    change = shown.diff().reindex(rows.index)
    history = official.to_numpy()
    end = shown.index[-1]
    year = shown[shown.index > end - pd.Timedelta(days=YEAR_DAYS)]
    newest = float(rows.iloc[0])
    since = official.index[0].date()
    latest = [_rank(f"Since {since:%Y}", history, newest, f"every week since {since:%Y}")]
    for label, days in WINDOWS:
        window = shown[(shown.index > end - pd.Timedelta(days=days)) & (shown.index < end)]
        latest.append(_rank(label, window.to_numpy(), newest, f"the {label.lower()}"))
    return Naaim(recent=rows, change=change,
                 recent_pct=tuple(sentiment.percentile_of(history, v) for v in rows),
                 average=float(official.mean()), since=since,
                 year={"average": float(year.mean()),
                       "high": (float(year.max()), year.idxmax().date()),
                       "low": (float(year.min()), year.idxmin().date())},
                 latest=tuple(latest), last=end.date(), provisional=late)


def _rank(label, history, value, what):
    """(label, percentile, word, hover) for `value` against `history`, `what` naming
    the history in the hover ("the 51st percentile of every week since 2006")."""
    pct = sentiment.percentile_of(history, value)
    word = sentiment.percentile_word(history, value)
    record = word in (sentiment.HIGHEST, sentiment.LOWEST)
    return label, pct, word, f"{word} {'of' if record else 'percentile of'} {what}"


def read(get_bars=None):
    """The card's numbers from the store, or None when NAAIM is not in it."""
    return summarize(*series(get_bars))


def naaim_color(palette):
    """NAAIM's line colour on the page, so the card and the charts below agree."""
    return sentiment.sentiment_colors(palette)["naaim"]


def _ink(fill):
    """Dark ink on the bar where it reads, white on a darker one (`aaii_votes.segment_ink`'s rule)."""
    if not str(fill).startswith("#"):
        return LIGHT_INK
    drawn = blend_over(fill, BAR_OPACITY)
    return DARK_INK if relative_luminance(drawn) > INK_PIVOT else LIGHT_INK


def _rows(index):
    return [f"{d:%Y-%m-%d}" for d in index]


def recent_figure(naaim, palette):
    """The last RECENT_WEEKS readings, newest on top, against the official average."""
    fill = naaim_color(palette)
    vals = naaim.recent.round(1)
    rows = _rows(vals.index)
    labels = [f"{v:.1f} ({sentiment.ordinal(p)})" for v, p in zip(vals, naaim.recent_pct)]
    # Labels past the bar's end, clear of the dashed average, which ran through them
    # inside the bar (72.9 against 67.5); inside only where the end leaves no room.
    fig = go.Figure(go.Bar(
        x=vals.clip(lower=0).to_numpy(), y=rows, orientation="h", showlegend=False,
        marker=dict(color=hex_to_rgba(fill, BAR_OPACITY) if fill.startswith("#") else fill),
        text=labels, textposition=["inside" if v > LABEL_INSIDE_FROM else "outside"
                                   for v in vals],
        insidetextanchor="end", insidetextfont=dict(color=_ink(fill), size=11),
        outsidetextfont=dict(color=vc.BRIGHTER_TEXT_COLOR, size=11), cliponaxis=False,
        customdata=[sentiment.ordinal(p) for p in naaim.recent_pct],
        hovertemplate=("Exposure %{x:.1f}, %{customdata} percentile since "
                       f"{naaim.since:%Y}<extra>%{{y}}</extra>")))
    avg = round(naaim.average, 1)
    fig.add_vline(x=avg, line=dict(color=vc.TEXT_COLOR, width=1, dash="dash"))
    aaii_votes._finish(fig, f"Recent weeks (avg {avg:.1f} dashed)", len(rows))
    fig.update_xaxes(range=X_RANGE)
    return fig


def change_figure(naaim, colors):
    """Each recent week's move from the week before, on a fixed +-CHANGE_LIMIT scale,
    the label on the empty side of zero (`aaii_votes.spread_figure`'s layout)."""
    change = naaim.change.round(1)
    rows = _rows(change.index)
    fills = aaii_votes.leg_colors(colors)
    color = [hex_to_rgba(fills["bullish" if v >= 0 else "bearish"], BAR_OPACITY)
             if pd.notna(v) else "rgba(0,0,0,0)" for v in change]
    fig = go.Figure(go.Bar(
        x=change.clip(-CHANGE_LIMIT, CHANGE_LIMIT).fillna(0).to_numpy(), y=rows,
        orientation="h", showlegend=False, marker=dict(color=color),
        customdata=[f"{v:+.1f}" if pd.notna(v) else "n/a" for v in change],
        hovertemplate="Change from the week before %{customdata}<extra>%{y}</extra>"))
    fig.add_vline(x=0, line=dict(color=vc.TEXT_COLOR, width=1))
    aaii_votes._finish(fig, "Change from the week before", len(rows))
    fig.update_xaxes(range=[-CHANGE_LIMIT, CHANGE_LIMIT])
    for row, v in zip(rows, change):
        if pd.isna(v):
            continue
        down = v < 0
        fig.add_annotation(x=0, y=row, xref="x", yref="y", xanchor="left" if down else "right",
                           text=f"  {v:+.1f}" if down else f"{v:+.1f}  ", showarrow=False,
                           font=dict(size=11, color=vc.BRIGHTER_TEXT_COLOR))
    return fig


def history_figure(naaim, palette):
    """The official average since 2006, and the last year's average, high and low, the
    high and low dated beside their bars."""
    fill = naaim_color(palette)
    year = naaim.year
    rows = ["Average", "Year average", "Year high", "Year low"]
    vals = [naaim.average, year["average"], year["high"][0], year["low"][0]]
    vals = [round(v, 1) for v in vals]
    fig = go.Figure(go.Bar(
        x=[max(v, 0.0) for v in vals], y=rows, orientation="h", showlegend=False,
        marker=dict(color=hex_to_rgba(fill, BAR_OPACITY) if fill.startswith("#") else fill),
        text=[f"{v:.1f}" for v in vals], textposition="inside", insidetextanchor="end",
        insidetextfont=dict(color=_ink(fill), size=11), cliponaxis=False,
        hovertemplate="%{y} %{text}<extra></extra>"))
    for row, key in (("Year high", "high"), ("Year low", "low")):
        value, when = year[key]
        # Past the bar's end, unless the end leaves no room: at phone width a 102.8
        # high's date ran off the block ("2026-0"), so a long bar carries its date
        # inside, at its start, the value staying at its end.
        inside = value > DATE_INSIDE_FROM
        fig.add_annotation(x=0.0 if inside else max(value, 0.0), y=row, xanchor="left",
                           showarrow=False, text=f"  {when:%Y-%m-%d}",
                           font=dict(size=10, color=_ink(fill) if inside else vc.TEXT_COLOR))
    aaii_votes._finish(fig, f"Since {naaim.since:%Y}; the last year", len(rows))
    fig.update_xaxes(range=X_RANGE)
    return fig


PERCENTILE_TITLE = "NAAIM exposure"


def latest_figure(naaim, palette, title=PERCENTILE_TITLE):
    """The newest reading as a percentile of the full official history and of the two
    windows (`aaii_votes.dots_figure`, one dot a row). On the percentiles card since
    2026-11-12."""
    rows = [(label, {"naaim": (pct, word)},
             f"every week since {naaim.since:%Y}" if i == 0 else f"the {label.lower()}")
            for i, (label, pct, word, _) in enumerate(naaim.latest)]
    return aaii_votes.dots_figure(rows, [("naaim", "NAAIM")],
                                  {"naaim": naaim_color(palette)},
                                  {"naaim": f"{naaim.recent.iloc[0]:.1f}"}, title)


def figures(naaim, colors, palette):
    """The card's three blocks, (recent, change, history). The percentile block moved to
    the percentiles card on 2026-11-12 (`latest_figure`)."""
    return (recent_figure(naaim, palette), change_figure(naaim, colors),
            history_figure(naaim, palette))
