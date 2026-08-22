"""Aggregate Exposure: what a set of markets is holding, in dollars.

The one question the rest of this app cannot answer. Every other view normalizes each
market against itself, which is what lets 47 markets share one axis on the Crowding
Strip and what the positioning index has always done. None of those numbers can be
added: a percentile has no units.

This page adds. `cotmetrics.exposure` converts contracts into USD notional and then into
USD daily risk, which is the only rung that is both summable and comparable, and this
page draws the total against the set's own composite price.

It is deliberately a SET view rather than a market view. A single market's dollar
exposure is the positioning index wearing bigger numbers; the reason to convert units at
all is to make a total mean something.

Three things this page says in words because the picture cannot carry them, and all
three are failures of the printed reference it was built from:

- which markets are in the total, and which were dropped and why
- whether a retired constituent is truncating the series
- that positioning is as-of Tuesday and published the following Friday
"""
import dash
import dash_ag_grid as dag
import dash_bootstrap_components as dbc
import pandas as pd
from cotmetrics import exposure
from cotmetrics.indexer import get_indexer
from dash import Input, Output, Patch, State, callback, dcc, html, no_update

import components.exposure_traces as exposure_traces
import viz_config
import viz_constants as vc
from components.plot_colors import grid_colors, hex_to_rgba

dash.register_page(__name__, path='/exposure')

#: Short labels for the CONTROL only. The prose keeps `exposure.LEG_LABELS`, where
#: "Speculators (Large + Small)" is worth its length because a reader meeting the total
#: for the first time needs to know what is in it. In a 180px select it is three words
#: of ellipsis, and the composition line under the headline names the two halves anyway.
LEG_SHORT = {
    exposure.LEG_SPEC: "Speculators",
    exposure.LEG_COMM: "Commercials",
    exposure.LEG_LARGE: "Large Specs",
    exposure.LEG_SMALL: "Small Traders",
}

LEG_OPTIONS = [{"label": LEG_SHORT[k], "value": k}
               for k in (exposure.LEG_SPEC, exposure.LEG_COMM,
                         exposure.LEG_LARGE, exposure.LEG_SMALL)]

SCALE_OPTIONS = [
    {"label": exposure_traces.SCALE_LABELS[k], "value": k}
    for k in (exposure_traces.SCALE_LEVEL, exposure_traces.SCALE_RANK)
]

UNIT_OPTIONS = [
    {"label": "Risk", "value": exposure_traces.UNIT_RISK},
    {"label": "Notional", "value": exposure_traces.UNIT_NOTIONAL},
]

#: One style for all four control labels, because four copies of the same dict is four
#: chances for one of them to drift a font size and make the row look ragged.
CONTROL_LABEL = {**vc.label_style, "fontSize": "0.8rem",
                 "textTransform": "uppercase", "marginBottom": "2px"}


#: The markets a class starts with, by SYMBOL, where "every market in the class" is the
#: wrong opening set. Anything not listed here starts whole.
#:
#: Equities is the case that needed it, and the reasons are measured rather than
#: preferred. The class holds eight markets and three of them cost the aggregate
#: something before a reader has touched a control: MFS and MME are ICE MSCI futures
#: priced off ETFs with no contract multiplier, so they are dropped every time; NKD's
#: COT history ends 2026-03-03, so a whole-class total stops there while the rest runs
#: to the current week. Measured across the three candidate sets:
#:
#:     ES NQ YM RTY        1247 weeks, 2002-08-13 to 2026-08-18, nothing dropped
#:     + EMD               1239 weeks, 2002-11-05 to 2026-08-18, nothing dropped
#:     whole class         1109 weeks, 2002-11-05 to 2026-03-03, two dropped
#:
#: So the four majors are not a narrower view of the same thing, they are the only one
#: of the three that reaches the present with every member priced. EMD is left out on a
#: weaker argument than the others, that "US equity index positioning" is a crowd anyone
#: would recognise and mid-caps are a different question, and it is one click away.
#:
#: Keyed by symbol, not display name, because a name is a label and a symbol is what the
#: store and the specs table agree on.
DEFAULT_MEMBERS = {
    "Equities": ("ES", "NQ", "YM", "RTY"),
}


def _class_options():
    return [{"label": c, "value": c} for c in get_indexer().get_asset_classes()]


def membership(agg, names, available=None):
    """Who is in the total, who is not, and what the completeness rule cost.

    An aggregate is a claim about a set, so the set is part of the reading. This is the
    page's whole disclosure surface and it is drawn above the figure rather than under
    it, because a reader who has already formed an impression of the line is not going
    to revise it on the strength of a footnote.
    """
    included = len(agg.coverage)
    bits = [html.Span(f"{included} of {len(names)} markets summed",
                      style={"color": vc.BRIGHTER_TEXT_COLOR})]

    # A default that silently narrows the class is the same failure as a filter that
    # silently drops rows, and it is worse for being on by default: a reader who never
    # touches Markets has no reason to suspect the total is not the class. Named, not
    # counted, so they can see whether the one they came for is among them.
    left_out = sorted(set(available or ()) - set(names))
    if left_out:
        bits.append(html.Span(
            " · not included: " + ", ".join(left_out) + " (add from Markets)"))

    if agg.dropped:
        # Named, not counted. "2 markets dropped" tells a reader that something is
        # missing without telling them whether it is the one they came to look at.
        bits.append(html.Span(
            " · dropped: " + ", ".join(f"{n} ({why.split(',')[0]})"
                                       for n, why in sorted(agg.dropped.items()))))
    if "end" in agg.bounded_by:
        # The failure this exists for: a retired constituent stops the whole series and
        # the chart simply ends, with nothing on it saying the other members did not.
        last = agg.coverage.get(agg.bounded_by["end"], (None, None))[1]
        bits.append(html.Span(
            f" · series ENDS {last:%b %Y} because {agg.bounded_by['end']} does; "
            f"remove it from Markets to follow the rest",
            style={"color": vc.BRIGHTER_TEXT_COLOR}))
    if "start" in agg.bounded_by:
        first = agg.coverage.get(agg.bounded_by["start"], (None, None))[0]
        bits.append(html.Span(
            f" · starts {first:%b %Y} with {agg.bounded_by['start']}"))
    if agg.weeks_lost:
        bits.append(html.Span(
            f" · {agg.weeks_lost} week(s) not summed, where some member had no value"))
    return bits


#: Where the percentile stops being "within the usual range" and starts being a
#: crowd. The same 10/90 the band draws and the same pair the rest of the app treats as
#: the edge of normal, so a reader carries one threshold between pages.
CROWDED_HIGH = 90
CROWDED_LOW = 10

#: The headline's typography, in one place because the full render and the click path
#: both write it and a style that drifted between them would flicker on every click.
HEAD_STYLE = {"fontSize": "1.05rem", "fontWeight": 600, "marginBottom": "2px"}

LEDE = (
    "How much money one group of traders has committed to a whole group of markets, "
    "and whether that is a lot by this group's own standards.")


def ordinal(n):
    """43rd, not 43th. English, so the teens are the exception rather than the rule.

    Worth a function because two different lines print a percentile and a page that
    writes "43th" in bold above a chart reads as unfinished whatever the chart does.
    """
    n = int(round(n))
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }".replace(" ", "")


def snap_week(frame, when):
    """The frame's own week nearest to `when`, or None for the latest.

    A click reports the x of the point under the cursor, which is already a real week on
    every trace here. It is snapped anyway because hover is unified across four traces
    and a band edge can report a neighbouring stamp, and because a stale selection has
    to survive the controls changing: click a 2015 week, switch to Metals, and the
    nearest Metals week is a better answer than an exception.
    """
    if frame is None or frame.empty or when is None:
        return None
    stamps = pd.DatetimeIndex(frame.index)
    target = pd.to_datetime(when)
    if getattr(target, "tzinfo", None) is not None:
        target = target.tz_localize(None)
    return stamps[abs(stamps - target).argmin()]


def week_row(frame, when=None):
    """One week of the total: the selected one, or the last."""
    if frame is None or frame.empty:
        return None
    stamp = snap_week(frame, when)
    return frame.loc[stamp] if stamp is not None else frame.iloc[-1]


def headline(frame, unit, leg, when=None):
    """The one-line answer, before any of the machinery that produced it.

    A reader arriving at a twenty-year chart of dollars has to do two conversions before
    they know anything: read the last value, then decide whether it is big. The second
    is the one nobody can do by eye on a series that drifts with the price level, which
    is this page's whole hazard, so the page does it for them and says which way.

    It describes, it does not advise. An extreme is a state, not a trigger: positioning
    can sit in the top decile for months, the effective sample is roughly a fifth of
    nominal because exceedances arrive in episodes, and this page runs no gate. The
    setup pages do that, and this one deliberately says so rather than letting a bold
    red number imply it.

    Which is also why it does NOT use the app's verdict colours. Green and red mean bull
    setup and bear setup everywhere else here, and a crowded long is neither: under a
    positioning-fade model it would read as the OPPOSITE of the green it was painted in.
    An extreme is emphasised rather than coloured, so the one channel this line spends
    is weight, on the one variable it actually measures.
    """
    if frame is None or frame.empty:
        return "", vc.TEXT_COLOR
    row = week_row(frame, when)
    if row is None:
        return "", vc.TEXT_COLOR
    rank = row[exposure_traces.UNIT_RANK_COLUMN[unit]]
    # Scaled against the WHOLE series, not the selected week, so the unit does not
    # change when a reader clicks from a big week to a small one. A number that grew
    # three orders of magnitude because you clicked left is not a comparison.
    divisor, suffix = exposure_traces.unit_scale(frame[unit])
    value = row[unit] / divisor
    side = "long" if value >= 0 else "short"
    money = f"${abs(value):,.1f}{suffix}"
    who = exposure.LEG_LABELS[leg]

    if rank != rank:
        return (f"{who} are net {side} {money}. Not enough history yet to say whether "
                f"that is unusual."), vc.TEXT_COLOR
    if rank >= CROWDED_HIGH:
        return (f"CROWDED {side.upper()}. {who} are net {side} {money}, higher than "
                f"{rank:.0f}% of the weeks in this set's own history.",
                vc.BRIGHTER_TEXT_COLOR)
    if rank <= CROWDED_LOW:
        # A low percentile on a signed series is the crowd at its most short, or least
        # long, for this set. Saying "crowded short" only when the level is actually
        # negative keeps the word honest.
        word = "CROWDED SHORT" if value < 0 else "UNUSUALLY LIGHT"
        return (f"{word}. {who} are net {side} {money}, lower than "
                f"{100 - rank:.0f}% of the weeks in this set's own history.",
                vc.BRIGHTER_TEXT_COLOR)
    return (f"Within the usual range. {who} are net {side} {money}, around the "
            f"{ordinal(rank)} percentile of this set's own history."), vc.TEXT_COLOR


#: Below this, a total is a residual between markets doing different things rather than
#: a crowd, and the word "crowded" above it needs qualifying. Chosen as the point where
#: a fifth of the gross size is cancelling out.
AGREEMENT_SPLIT = 0.80

#: A member holding this share of the gross total is the total, whatever the other names
#: on the list say.
DOMINANT_SHARE = 0.50


def composition_line(agg, unit, leg, part_frames=None, when=None):
    """What the headline is actually made of, in one sentence under it.

    Two facts, both invisible in a sum and both measured rather than suspected.

    The leg split, when the drawn leg is Speculators. Large and Small sit on OPPOSITE
    sides 59% of weeks, and the sign of their total disagrees with one of them about a
    third of the time. So the page can say CROWDED LONG on a week where one of the two
    groups inside that number is short, which is what it did before this line existed.

    The concentration. `agreement` is |sum| / sum|.| across markets: 1.00 is unanimous,
    and a low reading means the total is what is left after markets cancelled. Beside it
    the largest single contributor, because a market holding half the gross total IS the
    total whatever else is on the list.
    """
    if agg is None or agg.frame.empty:
        return ""
    when = snap_week(agg.frame, when)
    column = exposure_traces.UNIT_RANK_COLUMN[unit].replace("_pct_rank", "_usd")
    shares = exposure.contributions(agg.members, column, when=when)
    if shares.empty:
        return ""
    divisor, suffix = exposure_traces.unit_scale(agg.frame[unit])

    bits = []
    # Only where the leg IS the sum of those two. The figure draws companions under
    # every leg, but Large and Small are the rest of the report beneath Commercials, not
    # what Commercials is made of, and calling them its halves would describe an
    # arithmetic that does not exist.
    parts = (part_frames or {}) if leg in exposure_traces.LEG_PARTS else {}
    if len(parts) == 2:
        # Named in the order they are drawn, and only when they disagree is the sentence
        # worth its length. When they agree, saying so is still worth a clause: it tells
        # a reader the headline is not one group's doing.
        told = []
        for part_leg, frame in parts.items():
            if frame is None or frame.empty:
                continue
            value = (frame.loc[when] if when in frame.index
                     else frame.iloc[-1]) / divisor
            told.append((exposure.LEG_LABELS[part_leg], value))
        if len(told) == 2:
            (a_name, a), (b_name, b) = told
            if (a >= 0) != (b >= 0):
                long_side = (a_name, a) if a >= 0 else (b_name, b)
                short_side = (b_name, b) if a >= 0 else (a_name, a)
                bits.append(
                    f"The two halves disagree: {long_side[0]} long "
                    f"${abs(long_side[1]):,.1f}{suffix} against {short_side[0]} short "
                    f"${abs(short_side[1]):,.1f}{suffix}")
            else:
                bits.append(f"Both halves agree ({a_name} ${a:,.1f}{suffix}, "
                            f"{b_name} ${b:,.1f}{suffix})")

    gross = float(sum(abs(v) for v in shares))
    score = exposure.agreement(shares)
    top_name = shares.index[0]
    top_share = abs(shares.iloc[0]) / gross if gross else float("nan")
    same_way = sum(1 for v in shares if (v >= 0) == (shares.sum() >= 0))
    if top_share == top_share and top_share >= DOMINANT_SHARE:
        bits.append(f"{top_name} alone is {top_share:.0%} of it")
    else:
        bits.append(f"{top_name} is the largest single market at {top_share:.0%}")
    if score == score:
        qualifier = (" so the total is a residual rather than a crowd"
                     if score < AGREEMENT_SPLIT else "")
        bits.append(f"{same_way} of {len(shares)} markets point the same way "
                    f"(agreement {score:.2f}){qualifier}")
    return ". ".join(bits) + "."


def how_to_read(unit):
    """What each part of the picture is for, in the order a reader meets it.

    Written as "what you learn" rather than "what it is". A legend saying "expanding
    10th to 90th percentile" is accurate and answers a question nobody asked; what a
    reader wants is that the band is where this set normally sits, so a line outside it
    is the crowd doing something it does not usually do.
    """
    return [
        ("The number itself",
         "Contracts converted to dollars, so markets that cannot otherwise be compared "
         "can be added into one total. Here that is "
         + exposure_traces.UNIT_NOTES[unit]),
        ("Where it sits in the band",
         "The shaded band is where this set normally sits, the middle 80% of its own "
         "history up to that week. A line outside it is the crowd doing something it "
         "does not usually do. The band widens over the years because dollar figures "
         "grow with the price level, which is exactly why the level alone cannot tell "
         "you whether today is a lot."),
        ("The two panels together",
         "The top panel is the same markets' own price. Exposure climbing with price "
         "is the crowd adding to a move; exposure falling while price climbs is the "
         "crowd being sold to. Those read very differently and neither is visible in "
         "one panel alone."),
        ("What it is made of",
         "A sum says nothing about whether every market agreed or one market carried "
         "it, so the table below breaks the week apart and the line under the headline "
         "scores it. The Contribution bar runs from the centre, so a market leaning "
         "against the total points the other way and is faded. The %ile column is each "
         "market against ITS own history, which the bar cannot show: a market can be a "
         "small part of the total and still be at the most extreme reading it has ever "
         "had."),
        ("The Scale switch",
         "Level plots the dollars; %ile plots where each week sat in the history up to "
         "itself, 0 to 100. On a long set the level view is dominated by recent years "
         "whatever the positioning did, because dollar figures carry the price level: "
         "on Metals since 1989 the typical weekly figure grew about 48 times between "
         "the 1990s and the 2020s. %ile puts every year on the same footing. The band "
         "goes flat at 10 and 90 there, and the hover still tells you the dollars."),
        ("The third panel",
         "The other two Legacy groups, whichever one you are looking at. The three sum "
         "to zero every week, so no group moves without another moving against it, but "
         "no single one determines another either: Large and Small sit on opposite "
         "sides 59% of weeks. They get their own panel because they are often an order "
         "of magnitude away from the subject, and because the band above belongs to the "
         "subject alone."),
        ("What it does NOT tell you",
         "This is a description, not a signal. Positioning can sit at an extreme for "
         "months, and this page runs no gate: the Strip and the setup pages do that. "
         "The figures are as-of Tuesday and published the following Friday, so no week "
         "on this chart was knowable when its price printed."),
    ]


#: One row per market, so a set fits without scrolling and a long one still shows the
#: markets that matter, which are the ones at the top.
TABLE_ROW_PX = 30
TABLE_HEADER_PX = 34
TABLE_MAX_ROWS = 12


def contribution_columns(unit, palette, leg, table):
    """The table's columns: both units, the percentile of the drawn one, and the bar.

    Both units on every row whichever one is drawn, because they are not substitutes:
    on the Energies complex their percentiles correlate 0.802 with a median gap of 9.6
    percentile points and a worst gap of 69. A reader should be able to see the number
    the page is not currently showing without changing a control.

    The percentile is each market's own, against ITS history, not the total's. That is
    the column the bar cannot carry: a market can be a small part of the total and be at
    the most extreme reading it has ever had, and those are different facts.
    """
    other = (exposure_traces.UNIT_NOTIONAL if unit == exposure_traces.UNIT_RISK
             else exposure_traces.UNIT_RISK)
    rank = exposure.rank_column(unit)
    base = palette[exposure_traces.LEG_PALETTE_SLOT.get(leg, 0)]

    values = [v for v in table[unit]] if unit in table.columns else []
    max_abs = max((abs(v) for v in values if v == v), default=0.0)
    total_sign = 1 if sum(v for v in values if v == v) >= 0 else -1

    def money(column):
        divisor, suffix = exposure_traces.unit_scale(table[column]) if len(table) \
            else (1.0, "")
        return {
            "headerName": f"{exposure_traces.UNIT_LABELS[column]}"
                          + (f" ({suffix})" if suffix else ""),
            "field": column,
            "type": "numericColumn",
            "valueFormatter": {
                "function": f"d3.format(',.1f')(params.value / {divisor})"},
            "width": 120,
        }

    return [
        {"headerName": "Market", "field": "market", "flex": 1, "minWidth": 130},
        money(unit),
        money(other),
        {"headerName": "%ile", "field": rank, "type": "numericColumn", "width": 80,
         "valueFormatter": {"function": "params.value == null ? '' : "
                                        "d3.format('.0f')(params.value)"},
         "headerTooltip": "Where this market's own history puts this week, 0 to 100"},
        {"headerName": "Contribution", "field": unit, "colId": "bar",
         "cellRenderer": "ContributionBarRenderer",
         "cellRendererParams": {
             "maxAbs": max_abs,
             "totalSign": total_sign,
             "withColor": hex_to_rgba(base, exposure_traces.WITH_ALPHA),
             "againstColor": hex_to_rgba(base, exposure_traces.AGAINST_ALPHA),
         },
         "sortable": False, "flex": 1, "minWidth": 140,
         "headerTooltip": "Each market's share of the total, from the centre. "
                          "Faded bars point against it."},
    ]


def contribution_grid(table, unit, palette, leg):
    """The composition of one week, as a table rather than a chart.

    It replaced a horizontal bar figure, which drew the one column a chart is better at
    and could carry nothing else. The three columns beside the bar are the reason: the
    dollar figure a reader would otherwise have to estimate off an axis, the same figure
    in the unit they are not looking at, and each market's own percentile, which no
    contribution chart can show because it is not a share of anything.
    """
    if table is None or table.empty:
        return dag.AgGrid(id='exposure_contributions', rowData=[], columnDefs=[],
                          className="ag-theme-quartz-dark",
                          style={"height": "0px", "display": "none"})
    # Sorted by the unit being DRAWN, not by the table's own lead column. The table is
    # ordered by whichever unit comes first in cotmetrics; here the reader is looking at
    # one of them, and the market driving the number on screen should be the top row.
    if unit in table.columns:
        table = table.reindex(table[unit].abs().sort_values(ascending=False).index)
    # Plain floats, not numpy scalars: rowData is serialised to the browser, and a numpy
    # type that happens to survive today is a dependency on the encoder rather than a
    # decision.
    rows = [{"market": str(name),
             **{c: (None if row[c] != row[c] else float(row[c]))
                for c in table.columns}}
            for name, row in table.iterrows()]
    height = TABLE_HEADER_PX + TABLE_ROW_PX * min(len(rows), TABLE_MAX_ROWS)
    return dag.AgGrid(
        id='exposure_contributions',
        rowData=rows,
        columnDefs=contribution_columns(unit, palette, leg, table),
        className="ag-theme-quartz-dark",
        style={"height": f"{height}px", "width": "100%", "fontSize": "12px"},
        defaultColDef={"sortable": True, "resizable": True, "suppressMenu": True},
        dashGridOptions={"rowHeight": TABLE_ROW_PX, "headerHeight": TABLE_HEADER_PX,
                         "suppressCellFocus": True, "tooltipShowDelay": 400},
        dangerously_allow_code=True,
    )


def caption(frame, unit, leg, when=None):
    """The reading, in words, including the one fact the chart cannot show.

    The publication lag is the sentence that matters. The series is plotted at its
    as-of date, which is what the number is, and drawn against a price line that was
    knowable that day. Read literally it says the positioning was knowable too, and it
    was not until the Friday. A static PDF can leave that to a footnote; this page sits
    two clicks from a setup gate.
    """
    if frame is None or frame.empty:
        return ""
    row = week_row(frame, when)
    if row is None:
        return ""
    rank = row[exposure_traces.UNIT_RANK_COLUMN[unit]]
    divisor, suffix = exposure_traces.unit_scale(frame[unit])
    value = row[unit] / divisor
    side = "net long" if value >= 0 else "net short"
    rank_text = (f"the {ordinal(rank)} percentile of its own history"
                 if rank == rank else "no percentile yet, under two years of history")
    return (
        f"{exposure.LEG_LABELS[leg]} are {side} ${abs(value):,.1f}{suffix} "
        f"({exposure_traces.UNIT_LABELS[unit]}) as of {row.name:%B %d, %Y}, "
        f"which is {rank_text}. {exposure_traces.UNIT_NOTES[unit]} "
        f"The shaded band is the 10th to 90th percentile of the history up to each "
        f"week, so it carries no look-ahead and neither does the percentile. "
        f"Positioning is as-of Tuesday and published the following Friday: it is "
        f"plotted at the Tuesday it describes, which is three days before anyone could "
        f"have acted on it. The top panel is an equal-weight composite of the same "
        f"markets, rebased to 100, and not any index you can trade."
    )


def layout(**kwargs):
    return html.Div([
        # `local`, like the Strip's folds: whether the explanation is wanted is a
        # standing preference, not a fact about this visit.
        #
        # Starts SHUT, like the Strip's. It started open on the argument that a dollar
        # aggregate does not explain its own shape, which was true of the page before
        # the headline and the composition line existed. Those two now say the short
        # version in three lines, so the block is reference rather than orientation, and
        # 150px of reference above the chart is the cost of explaining something to a
        # reader who has already understood it.
        dcc.Store(id='exposure_help_open', storage_type='local', data=False),
        # NOT persisted, unlike the folds. Which week you are reading is a fact about
        # this visit, and a page that reopened weeks later still describing a 2015 week
        # under a headline saying CROWDED would be lying by default.
        dcc.Store(id='exposure_selected_week'),
        dbc.Container([
            dbc.Card(dbc.CardBody([
                # One row, four controls. It was two rows of two, which cost a strip of
                # vertical space on a page whose whole subject is a tall chart, and gave
                # the two multi-selects half the width each when neither needs it: they
                # show a count once more than a couple of items are chosen, so a wider
                # box buys nothing after the second chip.
                dbc.Row([
                    dbc.Col([
                        html.Label("Asset Classes", style=CONTROL_LABEL),
                        dcc.Dropdown(id='exposure_class_selector', multi=True,
                                     persistence='session',
                                     options=_class_options(), value=["Equities"],
                                     className="cot-dropdown"),
                    ], xs=12, md=3, className="px-md-2"),

                    dbc.Col([
                        # Per-market, because the constraining member is usually not a
                        # whole class. The live case: NKD retired from the COT in March
                        # 2026 and its class did not, so a class-level control cannot
                        # recover the five months the other equity markets still have.
                        #
                        # The widest of the four because it is the only one whose value
                        # a reader needs to READ rather than recognise: it is the list
                        # the total is a claim about.
                        html.Label("Markets", style=CONTROL_LABEL),
                        dcc.Dropdown(id='exposure_member_selector', multi=True,
                                     options=[], value=[], placeholder="all",
                                     className="cot-dropdown"),
                    ], xs=12, md=3, className="px-md-2 mt-2 mt-md-0"),

                    dbc.Col([
                        html.Label("Leg", style=CONTROL_LABEL),
                        dbc.Select(id='exposure_leg_selector', options=LEG_OPTIONS,
                                   value=exposure.LEG_SPEC, size="sm",
                                   className="bg-dark text-white border-secondary"),
                    ], xs=7, md=2, className="px-md-2 mt-2 mt-md-0"),

                    dbc.Col([
                        # "Risk" and "Notional", not the full "USD risk" and "USD
                        # notional" they were. The axis, the caption and the how-to-read
                        # block all carry the units, and the two short words are what
                        # let this sit in two columns instead of three.
                        html.Label("Unit", style=CONTROL_LABEL),
                        dbc.RadioItems(id='exposure_unit_selector',
                                       persistence='session',
                                       options=UNIT_OPTIONS,
                                       value=exposure_traces.UNIT_RISK, inline=True,
                                       style={"color": vc.BRIGHTER_TEXT_COLOR,
                                              "fontSize": "0.85rem"}),
                    ], xs=5, md=2, className="px-md-2 mt-2 mt-md-0"),

                    dbc.Col([
                        # Level or percentile. Not a log toggle, which is what a broad
                        # axis usually asks for and which cannot apply here: the
                        # exposure series is signed and crosses zero, so a log axis is
                        # undefined on it. See exposure_traces.SCALE_RANK.
                        html.Label("Scale", style=CONTROL_LABEL),
                        dbc.RadioItems(id='exposure_scale_selector',
                                       persistence='session',
                                       options=SCALE_OPTIONS,
                                       value=exposure_traces.SCALE_LEVEL, inline=True,
                                       style={"color": vc.BRIGHTER_TEXT_COLOR,
                                              "fontSize": "0.85rem"}),
                    ], xs=7, md=2, className="px-md-2 mt-2 mt-md-0"),
                ], align="center"),
            ], className="py-2"), className="mb-2 shadow-sm",
                style={"backgroundColor": "rgba(30, 30, 30, 0.6)",
                       "border": "1px solid rgba(255, 255, 255, 0.1)",
                       "borderRadius": "8px"}),

            # The headline sits ABOVE the figure, not under it. A reader who has
            # already formed an impression of a twenty-year line is not going to revise
            # it on the strength of a sentence underneath, and the impression this
            # particular chart invites (recent swings look largest) is the wrong one.
            html.Div(id='exposure_headline',
                     style={"fontSize": "1.05rem", "fontWeight": 600,
                            "marginBottom": "2px"}),
            # The row hides as a unit while the latest week is showing. A permanent
            # "Back to latest" is a control that does nothing on the state it is most
            # often seen in, and the notice beside it is the thing that makes the button
            # make sense.
            html.Div([
                html.Span(id='exposure_rewind', className="me-2"),
                dbc.Button("Back to latest", id='exposure_reset', size="sm",
                           color="secondary", outline=True, className="py-0"),
            ], id='exposure_rewind_row', className="mb-1",
                style={"display": "none"}),

            html.Div(id='exposure_composition',
                     style={"color": vc.BRIGHTER_TEXT_COLOR, "fontSize": "0.85rem",
                            "marginBottom": "4px"}),
            html.Div(LEDE, style={"color": vc.TEXT_COLOR, "fontSize": "0.85rem",
                                  "marginBottom": "6px"}),

            dbc.Button(id='exposure_help_toggle', size="sm", color="secondary",
                       outline=True, className="py-0 mb-2"),
            dbc.Collapse(id='exposure_help_collapse', is_open=False, className="mb-2",
                         children=html.Div(id='exposure_help')),

            html.Div(id='exposure_membership',
                     style={"color": vc.TEXT_COLOR, "fontSize": "0.8rem",
                            "marginBottom": "6px"}),

            # `clickmode="event"`, not the default `event+select`: a click here moves
            # the reading to a week, and Plotly's box-select highlight would imply a
            # range selection the page does not offer.
            dcc.Loading(dcc.Graph(id='exposure_chart',
                                  clickData=None,
                                  config={"displayModeBar": False,
                                          "responsive": True}),
                        type="default", color=vc.TEXT_COLOR),

            html.Div(id='exposure_contrib_label',
                     style={"color": vc.TEXT_COLOR, "fontSize": "0.8rem",
                            "marginTop": "4px"}),
            html.Div(id='exposure_contributions_slot'),

            html.P(id='exposure_caption',
                   style={"color": vc.TEXT_COLOR, "fontSize": "0.85rem",
                          "fontStyle": "italic", "marginTop": "6px"}),
        ], fluid=False)
    ])


@callback(
    Output('exposure_member_selector', 'options'),
    Output('exposure_member_selector', 'value'),
    Input('exposure_class_selector', 'value'),
)
def member_options(asset_classes):
    """Every market in the chosen classes, with the ones a total should start from
    selected.

    Selected rather than left blank so the control reads as the membership of the total
    rather than as a filter over it. Adding or removing one is then a visible edit to a
    stated set, which is the only change this page wants to make easy.

    The starting set is usually the whole class and deliberately is not for Equities.
    See DEFAULT_MEMBERS for the measurements. Whenever it is narrower, the membership
    line above the figure says so by name, because a default that quietly drops markets
    is the same failure as a filter that quietly drops them.
    """
    names = _names_in(asset_classes)
    return [{"label": n, "value": n} for n in names], _default_names(asset_classes)


def _names_in(asset_classes):
    """Every market in these classes."""
    if not asset_classes:
        return []
    return sorted(i.name for i in get_indexer().instruments.values()
                  if i.asset_class in asset_classes)


def _default_names(asset_classes):
    """The markets these classes start with, which is all of them unless said otherwise."""
    if not asset_classes:
        return []
    out = []
    for instrument in get_indexer().instruments.values():
        if instrument.asset_class not in asset_classes:
            continue
        preset = DEFAULT_MEMBERS.get(instrument.asset_class)
        if preset is None or instrument.symbol in preset:
            out.append(instrument.name)
    return sorted(out)


def describe_week(agg, part_frames, unit, leg, palette, when=None):
    """Everything the page says about ONE week, in one place.

    Both entry points come through here: the full render, which describes the latest
    week, and a click, which describes the one under the cursor. Written once because
    the alternative is two code paths that agree until one of them is edited, and the
    thing they would disagree about is what the numbers on screen mean.
    """
    stamp = snap_week(agg.frame, when)
    shown = stamp if stamp is not None else (
        agg.frame.index[-1] if not agg.frame.empty else None)

    table = exposure.contribution_table(agg.members, when=stamp,
                                        min_rank_periods=exposure_traces.MIN_RANK_PERIODS)
    bars = contribution_grid(table, unit, palette, leg)
    label = (f"What made it, week of {shown:%B %d, %Y}. "
             f"Percentiles are each market against its own history."
             if len(table) else "")

    head_text, head_colour = headline(agg.frame, unit, leg, when=stamp)
    return dict(
        bars=bars,
        bar_label=label,
        composition=composition_line(agg, unit, leg, part_frames, when=stamp),
        headline=head_text,
        head_style={**HEAD_STYLE, "color": head_colour},
        caption=caption(agg.frame, unit, leg, when=stamp),
        shown=shown,
    )


def rewind_notice(shown, latest):
    """Shown only while a past week is selected, because a page describing 2015 under a
    headline with no date is a page that lies quietly.

    Every figure on this page describes one week, and only the crosshair says which. The
    percentile is the one number that survives the move honestly on its own: it is
    expanding, so a past week is ranked against the history up to THAT week, which is
    what a reader looking at 2015 wants and not what a full-sample rank would give them.
    """
    if shown is None or latest is None or shown == latest:
        return "", {"display": "none"}
    return (f"Showing the week of {shown:%B %d, %Y}, not the latest.",
            {"display": "block"})


@callback(
    Output('exposure_help_open', 'data'),
    Input('exposure_help_toggle', 'n_clicks'),
    State('exposure_help_open', 'data'),
    prevent_initial_call=True,
)
def toggle_help(_n, is_open):
    return not is_open


@callback(
    Output('exposure_help_collapse', 'is_open'),
    Output('exposure_help_toggle', 'children'),
    Input('exposure_help_open', 'data'),
)
def apply_help_fold(is_open):
    return bool(is_open), ("\u25be How to read this" if is_open
                           else "\u25b8 How to read this")


@callback(
    Output('exposure_chart', 'figure'),
    Output('exposure_contributions_slot', 'children'),
    Output('exposure_contrib_label', 'children'),
    Output('exposure_composition', 'children'),
    Output('exposure_headline', 'children'),
    Output('exposure_headline', 'style'),
    Output('exposure_help', 'children'),
    Output('exposure_membership', 'children'),
    Output('exposure_caption', 'children'),
    Output('exposure_selected_week', 'data'),
    Output('exposure_rewind', 'children'),
    Output('exposure_rewind_row', 'style'),
    Input('exposure_class_selector', 'value'),
    Input('exposure_member_selector', 'value'),
    Input('exposure_leg_selector', 'value'),
    Input('exposure_unit_selector', 'value'),
    Input('exposure_scale_selector', 'value'),
    Input('session_palette_theme_asset_store', 'data'),
)
def render_exposure(asset_classes, members, leg, unit, scale, palette_name):
    palette = viz_config.get_palette(palette_name)
    colors = grid_colors(palette)
    leg = leg or exposure.LEG_SPEC
    unit = unit or exposure_traces.UNIT_RISK
    scale = scale or exposure_traces.SCALE_LEVEL

    help_block = help_children(unit)
    if not asset_classes:
        empty = exposure_traces.build_figure(None, None, unit=unit, colors=colors,
                                             palette=palette)
        no_bars = contribution_grid(None, unit, palette, leg)
        return (empty, no_bars, "", "", "",
                {**HEAD_STYLE, "color": vc.TEXT_COLOR}, help_block,
                "Select an asset class.", "", None, "", {"display": "none"})

    # An empty member list is the moment between a class change and the callback that
    # repopulates it, not a request for an empty total.
    names = list(members) if members else _names_in(asset_classes)
    agg = exposure.aggregate_exposure(names, leg=leg)
    composite = exposure.composite_price_index(
        list(agg.coverage), dates=agg.frame.index) if not agg.frame.empty else None

    # The other Legacy legs, for the companion panel. Computed over the same member
    # list rather than the same date index, so a leg whose completeness differs is
    # reindexed onto the subject in build_figure rather than silently shifted here.
    part_frames = {}
    for part_leg in exposure_traces.COMPANION_LEGS.get(leg, ()):
        part = exposure.aggregate_exposure(names, leg=part_leg)
        part_frames[part_leg] = part.frame[unit] if not part.frame.empty else None

    figure = exposure_traces.build_figure(
        agg.frame, composite, unit=unit, colors=colors, palette=palette,
        leg_label=exposure.LEG_LABELS[leg], set_label=", ".join(asset_classes),
        leg=leg, parts=part_frames, scale=scale)

    said = describe_week(agg, part_frames, unit, leg, palette)
    # A control change resets the selection: the clicked week belonged to the set that
    # was on screen when it was clicked, and silently carrying it onto a different set
    # is how a page ends up describing a week it never drew.
    return (figure, said["bars"], said["bar_label"], said["composition"],
            said["headline"], said["head_style"], help_block,
            membership(agg, names, _names_in(asset_classes)),
            said["caption"], None, "",
            {"display": "none"})


def help_children(unit):
    """`how_to_read` as markup: a definition list, not a paragraph.

    Four labelled points a reader can scan and stop at the one they wanted, where the
    same words as prose are a wall nobody reads and the fold below it is what a wall
    earns."""
    return [html.Div([
        html.Span(f"{title}. ", style={"color": vc.BRIGHTER_TEXT_COLOR,
                                       "fontWeight": 600}),
        html.Span(body, style={"color": vc.TEXT_COLOR}),
    ], style={"fontSize": "0.82rem", "marginBottom": "4px"})
        for title, body in how_to_read(unit)]


#: The crosshair marking the week being described. Dotted and half-strength, matching
#: the one on OI Alignment, so a reader who learned the gesture there recognises it here.
CROSSHAIR = {"color": "rgba(255,255,255,0.5)", "width": 1, "dash": "dot"}


@callback(
    Output('exposure_contributions_slot', 'children', allow_duplicate=True),
    Output('exposure_contrib_label', 'children', allow_duplicate=True),
    Output('exposure_composition', 'children', allow_duplicate=True),
    Output('exposure_headline', 'children', allow_duplicate=True),
    Output('exposure_headline', 'style', allow_duplicate=True),
    Output('exposure_caption', 'children', allow_duplicate=True),
    Output('exposure_chart', 'figure', allow_duplicate=True),
    Output('exposure_selected_week', 'data', allow_duplicate=True),
    Output('exposure_rewind', 'children', allow_duplicate=True),
    Output('exposure_rewind_row', 'style', allow_duplicate=True),
    Input('exposure_chart', 'clickData'),
    Input('exposure_reset', 'n_clicks'),
    State('exposure_class_selector', 'value'),
    State('exposure_member_selector', 'value'),
    State('exposure_leg_selector', 'value'),
    State('exposure_unit_selector', 'value'),
    State('session_palette_theme_asset_store', 'data'),
    State('exposure_chart', 'figure'),
    prevent_initial_call=True,
)
def select_week(click_data, _reset, asset_classes, members, leg, unit, palette_name,
                current_fig):
    """Move the whole reading to the week under the cursor, same gesture as OI Alignment.

    Everything above the chart describes one week, and until now that week was always
    the last one. Clicking a twenty-year series and having the headline stay on 2026 is
    the wrong answer twice over: the reader asked a question and the page ignored it,
    and the numbers they are looking at stop matching the words above them.

    The figure is PATCHED rather than rebuilt, so a click cannot undo a zoom. That is
    the same reason OI Alignment patches: returning a whole figure hands back the stored
    x-range with it.

    The percentile is the number that survives this move best, and for a reason worth
    knowing. It is expanding, so a week in 2015 is ranked against the history up to 2015,
    which is what a reader looking at 2015 wants. A full-sample rank would tell them
    where that week sits in a distribution half of which had not happened yet.
    """
    if not asset_classes:
        return (no_update,) * 10

    triggered = dash.callback_context.triggered
    by_reset = bool(triggered) and triggered[0]["prop_id"].startswith("exposure_reset")

    when = None
    if not by_reset:
        if not click_data or not click_data.get("points"):
            return (no_update,) * 10
        when = click_data["points"][0].get("x")
        if when is None:
            return (no_update,) * 10

    palette = viz_config.get_palette(palette_name)
    leg = leg or exposure.LEG_SPEC
    unit = unit or exposure_traces.UNIT_RISK
    names = list(members) if members else _names_in(asset_classes)

    agg = exposure.aggregate_exposure(names, leg=leg)
    if agg.frame.empty:
        return (no_update,) * 10

    part_frames = {}
    for part_leg in exposure_traces.COMPANION_LEGS.get(leg, ()):
        part = exposure.aggregate_exposure(names, leg=part_leg)
        part_frames[part_leg] = part.frame[unit] if not part.frame.empty else None

    said = describe_week(agg, part_frames, unit, leg, palette, when=when)
    latest = agg.frame.index[-1]
    notice, notice_style = rewind_notice(said["shown"], latest)

    patched = Patch()
    patched["layout"]["shapes"] = crosshair_shapes(
        ((current_fig or {}).get("layout") or {}).get("shapes"),
        None if by_reset else said["shown"])

    return (said["bars"], said["bar_label"], said["composition"], said["headline"],
            said["head_style"], said["caption"], patched,
            None if by_reset else str(said["shown"]), notice, notice_style)


def crosshair_shapes(existing, when):
    """The figure's own shapes, plus at most one crosshair.

    Rebuilt from `existing` rather than appended to. A Patch that appended would stack a
    line on every click and leave a comb across the chart after a dozen, and one that
    returned only the crosshair would delete the zero line the exposure panel is read
    against, which is the more expensive mistake because nothing about the result looks
    broken.

    The crosshair is identified by being the only paper-referenced one: the figure's own
    shapes are all bound to a data axis, so this survives new shapes being added to the
    figure without this function knowing about them.
    """
    shapes = [dict(shape) for shape in (existing or [])
              if not (shape.get("yref") == "paper" and shape.get("type") == "line")]
    if when is not None:
        shapes.append({"type": "line",
                       "xref": exposure_traces.CROSSHAIR_XREF, "yref": "paper",
                       "x0": str(when), "x1": str(when), "y0": 0, "y1": 1,
                       "line": CROSSHAIR})
    return shapes
