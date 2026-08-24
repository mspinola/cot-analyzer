"""Aggregate Exposure: what a set of markets is holding, in dollars.

The one question the rest of this app cannot answer. Every other view normalizes each
market against itself, which is what lets 47 markets share one axis on the Crowding
Strip and what the positioning index has always done. None of those numbers can be
added: a percentile has no units.

This page adds. `cotmetrics.exposure` converts contracts into USD notional and then into
USD daily risk, which is the only rung that is both summable and comparable, and this
page draws the total against the set's own composite price.

It reads ONE market as readily as forty. Summing is what dollars unlock, not what they
are for, and the tempting claim that a single market's dollars are just its positioning
index wearing bigger numbers is measurably false. Put the same 52-week range index on
net contracts and on dollar risk and the two correlate 0.92 at the median market, 0.75
on Gold, 0.71 on Gasoline, and they disagree about whether the week sits in the top or
bottom fifth on about one week in six. Nearly all of that gap is the volatility term:
notional alone tracks contracts at 0.98. So one name in Markets is a first-class
reading, and every sentence on this page says "market" or "set" according to what is
actually selected.

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
from dash import Input, Output, Patch, State, callback, clientside_callback, dcc, html, no_update

import components.exposure_traces as exposure_traces
import viz_config
import viz_constants as vc
from components.plot_colors import grid_colors, hex_to_rgba

dash.register_page(__name__, path='/exposure')

#: One implementation, used by this page's prose and by the figure's hovers.
#: It lives beside the figure because that is where 27% of its callers are.
ordinal = exposure_traces.ordinal

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

#: How far back a percentile looks. "All history" is the expanding rank the page was
#: built on and stays the default, because it is the only one that can say "the most
#: ever"; the rest are the app's own lookback vocabulary, where an index is a range over
#: a trailing window.
LOOKBACK_ALL = "all"
LOOKBACK_CUSTOM = "custom"

LOOKBACK_OPTIONS = [
    {"label": "All history", "value": LOOKBACK_ALL},
    {"label": "26 weeks", "value": "26"},
    {"label": "52 weeks", "value": "52"},
    {"label": "Custom", "value": LOOKBACK_CUSTOM},
]


def custom_window(names):
    """The tuned window these markets share, or None if they do not share one.

    `CustomLookbackWeeks` is tuned PER MARKET and the universe spends 25 distinct values
    on it, from 8 weeks to 216. A total is one summed series with one rank, so "Custom"
    only means something when every member agrees: ranking a sum of markets tuned to 10
    and 126 weeks over either number would be a choice the data does not support, and
    averaging them would invent a number nobody tuned.

    It is not a rare case. The page's own default, the four deploy equity markets, all
    carry 28, and Fixed Income and Live Stock are single-valued classes.
    """
    indexer = get_indexer()
    windows = set()
    for name in names or ():
        instrument = indexer.get_instrument_from_name(name)
        if instrument is None or not instrument.custom_lookback:
            return None
        windows.add(int(instrument.custom_lookback))
    return windows.pop() if len(windows) == 1 else None


def resolve_window(choice, names):
    """(weeks or None, what to tell the reader). None means rank against all history."""
    if choice in (None, LOOKBACK_ALL):
        return None, ""
    if choice == LOOKBACK_CUSTOM:
        weeks = custom_window(names)
        if weeks is None:
            # Refuse rather than pick. The alternative is a number nobody chose sitting
            # under a control that says the markets were tuned.
            return None, ("these markets do not share one tuned lookback, so Custom "
                          "cannot apply to their total; ranked against all history")
        return weeks, ""
    return int(choice), ""


def window_phrase(window):
    """"the last 52 weeks", or "its own history" when there is no window."""
    return f"the last {window} weeks" if window else "its own history"


def ranked_against(single, window):
    """What a percentile was measured against, as "the last 52 weeks" or "this set's
    own history".

    The subject noun stops mattering once a window is named: "the last 52 weeks" is the
    same stretch whether one market or forty is being ranked, and "this set's last 52
    weeks" would suggest the window came from the set.
    """
    if window:
        return f"the last {window} weeks"
    return f"{subject_noun(single, possessive=True)} own history"


def table_ranked_against(single, window):
    """What the contributions table's percentiles were measured against, in the words
    that fit after "against".

    Not `ranked_against`, which describes the TOTAL and so reaches for "this set's own
    history" once more than one market is selected. Every ROW of this table is one
    market whatever is selected, so the plural case wants "its own", never "this set's":
    a column headed "%ile" that said it was ranked against the set would be claiming the
    one thing the table exists to deny, which is that a member is measured on the
    total's scale.

    "Whole" rather than "own", because that phrase now has to stand next to "the last
    52 weeks" and be told apart from it. "Its own history" is true of a window too.

    Both restrictions or neither. A percentile in this table is bounded twice over and
    a reader checking one against a published figure is off by both: by the Lookback
    window, which this says, and by the set's coverage, which `set_coverage_note`
    says beside it. `aggregate_exposure` restricts every member to the weeks the TOTAL
    can price, so gold reads 88 alone and 81 in a set that starts in 2002 because
    Russell does.
    """
    if window:
        return f"the last {window} weeks"
    return "this market's whole history" if single else "its own whole history"


def set_coverage_note(single, lead="over"):
    """The second restriction on every percentile in the table, for a set only.

    A single market IS the set, so its coverage is its own history and the clause would
    be a qualification with nothing to qualify. It earns its place the moment there are
    two: adding a short-lived market shortens every other member's history and moves
    its percentile, which is arithmetic a reader has no way to guess from a column of
    numbers, and it is the reason a figure here can disagree with a published one for
    the same market and week.

    `lead` is the connective, because the three sentences that carry this clause reach
    it by different routes and one of them already said "over". The phrase itself is
    the part worth having in one place: three copies of it is three chances for one to
    drift into saying "history" and stop meaning the same restriction.
    """
    return "" if single else f", {lead} the weeks this set covers"


def weeks_compared(single, window):
    """The same thing after "higher than 97% of", which wants different words.

    "of the weeks in the last 52 weeks" says weeks twice, and "of this set's own
    history" without them makes a percentage of a history rather than of its weeks.
    """
    if window:
        return f"the last {window} weeks"
    return f"the weeks in {subject_noun(single, possessive=True)} own history"


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
    # "1 of 1 markets summed" is arithmetic about a sum with one term. The reader who
    # picked one name knows how many there are; what they want confirmed is WHICH.
    lede = (f"{names[0]} on its own" if included == 1 and len(names) == 1
            else f"{included} of {len(names)} markets summed")
    bits = [html.Span(lede, style={"color": vc.BRIGHTER_TEXT_COLOR})]

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
    "How much money one group of traders has committed to a market, or to a whole set "
    "of them, and whether that is a lot by its own standards.")


def subject_noun(single, possessive=False):
    """"this market" or "this set", from what is actually being summed.

    The page reads one name as readily as forty, so the sentences that say "its own
    history" have to agree with the Markets control above them. "This set's own
    history" printed over a single market reads as boilerplate, and a reader who
    catches one sentence not looking at the screen discounts the rest of them too.
    """
    noun = "this market" if single else "this set"
    return noun + "'s" if possessive else noun


def money(value, suffix, numeraire=None, unit=None):
    """A magnitude with its unit attached, in whichever numeraire is on.

    One function because five places print one of these and a page that said "$" on a
    chart labelled "oz gold" would be wrong in the one way this feature can be wrong.
    Sign is left to the caller: every one of them says "net long" or "net short" in
    words beside it, and a minus sign as well would be the same fact twice.
    """
    if unit in exposure_traces.SHARE_UNITS:
        # No currency mark and no ounces. A share is a ratio of two quantities in the
        # same unit, so it is the same number under either numeraire, and stamping it
        # with one would claim a denomination it does not have.
        return f"{abs(value) * 100:,.1f}% of open interest"
    magnitude = f"{abs(value):,.1f}{suffix}"
    if numeraire == exposure.NUMERAIRE_GOLD:
        return f"{magnitude} oz"
    return f"${magnitude}"


def unit_name(unit, numeraire=None):
    """The unit in PROSE: "USD daily risk", or "daily risk, in troy ounces of gold"."""
    label = exposure_traces.UNIT_LABELS[unit]
    if unit in exposure_traces.SHARE_UNITS:
        return label
    if numeraire == exposure.NUMERAIRE_GOLD:
        return label.replace("USD ", "") + ", in troy ounces of gold"
    return label


def column_name(unit, suffix, numeraire=None):
    """The same unit as a COLUMN HEADER, which has about twenty characters rather than a
    sentence. "Daily risk (k oz)", not "daily risk, in troy ounces of gold (k)"."""
    label = exposure_traces.UNIT_LABELS[unit]
    if unit in exposure_traces.SHARE_UNITS:
        return label.capitalize()
    if numeraire == exposure.NUMERAIRE_GOLD:
        stem = label.replace("USD ", "").capitalize()
        return f"{stem} ({suffix} oz)".replace("( ", "(")
    return f"{label} ({suffix})" if suffix else label


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


def headline(frame, unit, leg, when=None, numeraire=None, single=False,
             window=None):
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
    amount = money(value, suffix, numeraire, unit)
    who = exposure.LEG_LABELS[leg]

    if rank != rank:
        return (f"{who} are net {side} {amount}. Not enough history yet to say whether "
                f"that is unusual."), vc.TEXT_COLOR
    if rank >= CROWDED_HIGH:
        return (f"CROWDED {side.upper()}. {who} are net {side} {amount}, higher than "
                f"{rank:.0f}% of {weeks_compared(single, window)}.",
                vc.BRIGHTER_TEXT_COLOR)
    if rank <= CROWDED_LOW:
        # A low percentile on a signed series is the crowd at its most short, or least
        # long, for this selection. Saying "crowded short" only when the level is
        # actually negative keeps the word honest.
        word = "CROWDED SHORT" if value < 0 else "UNUSUALLY LIGHT"
        return (f"{word}. {who} are net {side} {amount}, lower than "
                f"{100 - rank:.0f}% of {weeks_compared(single, window)}.",
                vc.BRIGHTER_TEXT_COLOR)
    return (f"Within the usual range. {who} are net {side} {amount}, around the "
            f"{ordinal(rank)} percentile of "
            f"{ranked_against(single, window)}."), vc.TEXT_COLOR


#: A gap this wide between the two lenses is worth a sentence. Below it they are the
#: same reading twice and saying so every week is noise.
LENS_SPLIT = 20


def contracts_rank(agg, window=None):
    """The same expanding percentile the page ranks dollars with, run on the raw
    contract count. `None` for anything but a single market.

    Read off the MEMBER frame, never off the aggregate. The aggregate used to carry a
    summed `net_contracts` that added ES contracts to corn contracts, which is not a
    quantity and is exactly what converting to dollars exists to avoid; cotmetrics #21
    removed the column for that reason. Reading the member is what stays right either
    way, and is the only thing that could ever have been right here.

    Numeraire-free by construction, which is worth knowing when the Gold switch is on.
    The divisor is applied to the value columns only, because contracts are contracts
    whatever you price them in, so this line does not move when the dollars do.
    """
    if len(agg.members) != 1:
        return None
    frame = next(iter(agg.members.values()))
    if "net_contracts" not in frame:
        return None
    # The SAME window as the dollars it is drawn against, or the wedge between them
    # stops being a comparison of two units and becomes one of two stretches of time.
    return exposure.windowed_pct_rank(frame["net_contracts"], window,
                                      exposure_traces.MIN_RANK_PERIODS)


#: The two columns the contract lens rides on, joined onto the contribution table here
#: rather than in cotmetrics. `contribution_table` ranks the columns in
#: `exposure.TABLE_COLUMNS`, which is the two DOLLAR units, and contracts are
#: deliberately not among them: the table decomposes a total, and contracts are the one
#: unit that does not add across markets. They are a legitimate per-ROW reading all the
#: same, which is what this pair supplies.
CONTRACTS_COLUMN = "net_contracts"
CONTRACTS_RANK_COLUMN = "contracts_pct_rank"


def attach_contracts_rank(table, agg, when=None, window=None):
    """Each market's own contract count and percentile, joined onto the table by name.

    The per-market form of the sentence a single market already gets. Selecting one
    market prints "contracts put the same week at the 88th percentile against the 100th
    for the dollars"; selecting nine printed nothing of the kind, because that sentence
    reads the single member frame. The reading exists for every member, and a set is
    exactly where it earns its place: an extreme in money and an ordinary week in
    contracts is one market having grown or its volatility having moved, and a total
    cannot say which of its members that happened to.

    **The SAME rank the dollar column beside it uses**, so the two are a comparison of
    units and not of stretches of time. That was the expanding rank when this column
    shipped, because `contribution_table` had no window to follow; it takes one now, and
    the invariant is what moved rather than the choice. The two columns have to be
    passed the same `window` or the row goes back to mixing histories by the other
    route, which is the confusion this column exists to remove.

    **"Its own history" means the weeks the SET covers, not the weeks the market has.**
    `aggregate_exposure` restricts every member frame to the weeks the total can price,
    so adding a short-lived market to the selection shortens every other member's
    history and moves its percentile: Gold reads 88 on the contract count alone and 81
    inside an equities-and-metals set that starts in 2002 because Russell does. The
    dollar columns have always behaved this way and this follows them, which is the
    point; it is called out because this column is the one a reader is most likely to
    check against a published figure, and the published figure will have used the
    market's whole history.

    Returns the table unchanged when there is nothing to join, so a caller can apply it
    unconditionally.
    """
    if table is None or table.empty or not getattr(agg, "members", None):
        return table
    counts, ranks = {}, {}
    for name, frame in agg.members.items():
        if CONTRACTS_COLUMN not in frame:
            continue
        series = pd.to_numeric(frame[CONTRACTS_COLUMN], errors="coerce")
        rank = exposure.windowed_pct_rank(series, window,
                                          exposure_traces.MIN_RANK_PERIODS)
        # The same week the dollar columns were read at, and the same fallback:
        # `contribution_table` takes the last valid week when the stamp is absent, and
        # a row whose two percentiles came from different weeks is worse than a blank.
        stamp = when if (when is not None and when in series.index) else None
        if stamp is None:
            valid = series.dropna()
            if valid.empty:
                continue
            stamp = valid.index[-1]
        value, pct = series.get(stamp), rank.get(stamp)
        if value is not None and value == value:
            counts[name] = float(value)
        if pct is not None and pct == pct:
            ranks[name] = float(pct)
    if not ranks:
        return table
    table = table.copy()
    table[CONTRACTS_COLUMN] = pd.Series(counts)
    table[CONTRACTS_RANK_COLUMN] = pd.Series(ranks)
    return table


def contracts_net(agg):
    """The raw signed contract count behind `contracts_rank`, for the hover.

    A percentile has no side, and this line's whole subject is a position that has one.
    The sign is not new information: it matches the dollars in the panel above in every
    one of the 219,846 market-weeks in the store, because notional is contracts times a
    positive multiplier times a positive price, and no as-of price in the store is
    non-positive. But a reader following the dotted line should not have to reconstruct
    the side from a different trace's hover.
    """
    if len(agg.members) != 1:
        return None
    frame = next(iter(agg.members.values()))
    return frame["net_contracts"] if "net_contracts" in frame else None


#: Below this, a total is a residual between markets doing different things rather than
#: a crowd, and the word "crowded" above it needs qualifying. Chosen as the point where
#: a fifth of the gross size is cancelling out.
AGREEMENT_SPLIT = 0.80

#: A member holding this share of the gross total is the total, whatever the other names
#: on the list say.
DOMINANT_SHARE = 0.50


def lens_line(agg, unit, when=None, ranks=None):
    """What the raw contract count says about the same week, when it disagrees.

    The reason this is worth a line rather than a footnote: on the week it was written
    Large Specs in Silver sat at the 45th percentile on contracts and the 98th on
    dollar risk, and 12 of the 43 priceable markets disagreed about whether the leg was
    at a 90/10 extreme at all. The gap is not a second opinion about positioning, it is
    positioning multiplied by price and volatility, so a reader who only ever sees the
    dollars can mistake a volatility event for the crowd piling in.

    Silent when the two agree, which is most weeks: pooled across 43 markets the median
    gap is 5.4 percentile points. A sentence printed every week is a sentence nobody
    reads on the week it matters.
    """
    if ranks is None or ranks.empty or agg.frame.empty:
        return ""
    when = snap_week(agg.frame, when)
    row = week_row(agg.frame, when)
    if row is None or row.name not in ranks.index:
        return ""
    contracts, dollars = ranks[row.name], row[exposure_traces.UNIT_RANK_COLUMN[unit]]
    if contracts != contracts or dollars != dollars:
        return ""

    def extreme(v):
        return v >= CROWDED_HIGH or v <= CROWDED_LOW

    disagree = extreme(contracts) != extreme(dollars)
    if not disagree and abs(dollars - contracts) < LENS_SPLIT:
        return ""
    lens = (f"Contracts put the same week at the {ordinal(contracts)} percentile "
            f"against the {ordinal(dollars)} for the dollars")
    if not disagree:
        return lens + "."
    if extreme(dollars):
        return (lens + ", so the extreme is price and volatility acting on the "
                "position rather than more contracts.")
    return (lens + ", so the contract count reads more extreme than the money at "
            "stake does.")


def composition_line(agg, unit, leg, part_frames=None, when=None,
                     numeraire=None):
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
                    f"{money(long_side[1], suffix, numeraire)} against "
                    f"{short_side[0]} short "
                    f"{money(short_side[1], suffix, numeraire)}")
            else:
                bits.append(f"Both halves agree ({a_name} "
                            f"{money(a, suffix, numeraire)}, {b_name} "
                            f"{money(b, suffix, numeraire)})")

    # Concentration is a fact about a SET. With one market selected it can only say
    # that market is 100% of itself and that 1 of 1 markets point the same way, which
    # is true, uninformative, and reads as a page not looking at its own controls. The
    # leg split above stays, because Large against Small is a real disagreement inside
    # one market's number.
    if len(shares) > 1:
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
    if not bits:
        return ""
    return ". ".join(bits) + "."


def how_to_read(unit):
    """What each part of the picture is for, in the order a reader meets it.

    **Do not put a live percentile in this copy.** The Gold switch entry used to read
    "on the current week those speculators sit at the 98th percentile of their own
    history in dollars and the 67th in ounces", which was accurate when written and is
    a moving number frozen into static text, so it rots every Tuesday. Measured against
    the pinned store on 2026-08-24 the same pair was 97.0 and 73.1, a 23.9 point gap
    rather than 31, and the sentence had been quoting one dramatic week as though it
    were the effect. The figures here are distributional (median, ninetieth, widest)
    because those move slowly, and they are reproducible: dollar risk, speculators, the
    four-market default composite, from npf's exposure-numeraire study,
    `npf/docs/analysis/2026-08-24-exposure-numeraire-levels.md`. The headline above the
    chart is where a live reading belongs, and it already is one.

    The same study is why the tooltip's drift figures changed. It carried "Equities
    4.2x to 1.3x since 2002", inherited from a comment in `cotmetrics.exposure` that
    records no leg, no unit, no membership and no date range for it, so nothing could
    reproduce it. The replacements are measured under this page's OWN defaults.

    Written as "what you learn" rather than "what it is". A legend saying "expanding
    10th to 90th percentile" is accurate and answers a question nobody asked; what a
    reader wants is that the band is where the line normally sits, so a value outside
    it is the crowd doing something it does not usually do.
    """
    return [
        ("The number itself",
         "Contracts converted to dollars, which makes one market comparable with its "
         "own past at a different price level and makes markets sharing no units "
         "addable into one total. Here that is "
         + exposure_traces.UNIT_NOTES[unit]),
        ("One market or a whole set",
         "Markets takes one name as readily as forty, and one name is a real reading "
         "rather than a degenerate case. Dollar risk is not the positioning index "
         "wearing bigger numbers: run the same 52-week range index on net contracts "
         "and on dollar risk and they correlate 0.92 at the median market, 0.75 on "
         "Gold and 0.71 on Gasoline, and they disagree about whether the week sits in "
         "the top or bottom fifth on about one week in six. Nearly all of that is the "
         "volatility term, since notional alone tracks contracts at 0.98. Summing is "
         "what dollars make possible, not what they are for."),
        ("Where it sits in the band",
         "The shaded band is where this line normally sits, the middle 80% of its own "
         "history up to that week. A line outside it is the crowd doing something it "
         "does not usually do. The band widens over the years because dollar figures "
         "grow with the price level, which is exactly why the level alone cannot tell "
         "you whether today is a lot."),
        ("The two panels together",
         "The top panel is the price of the same selection. Exposure climbing with price "
         "is the crowd adding to a move; exposure falling while price climbs is the "
         "crowd being sold to. Those read very differently and neither is visible in "
         "one panel alone."),
        ("What it is made of",
         "A sum says nothing about whether every market agreed or one market carried "
         "it, so the table below breaks the week apart and the line under the headline "
         "scores it. The Contribution bar runs from the centre, so a market leaning "
         "against the total points the other way and is faded. The two %ile columns are "
         "each market against ITS own history, never against the total, which the bar "
         "cannot show: a market can be a small part of the total and still be at the "
         "most extreme reading it has had. Both follow the Lookback switch, the same "
         "stretch of weeks the headline above them was ranked over, so a row and the "
         "sentence over it are answering one question. With one market selected there "
         "is nothing to break apart, so the table is one row and the concentration "
         "score is dropped rather than printed as a meaningless 100%."),
        ("The Gold switch",
         "Prices everything in troy ounces instead of dollars, both panels, which is "
         "Larry Williams' WillVal applied to a whole complex: an asset measured against "
         "hard money rather than against a currency. Since 2002 the US equity composite "
         "is up 13.9 times in dollars and 1.0 times in gold. It changes the reading and "
         "not just the axis, though by less than any single week suggests: across the "
         "whole history of this composite the switch moves the percentile by about 6 "
         "points in the median week, 14 at the ninetieth, and into the mid-20s at its "
         "widest."),
        ("Why there is no inflation switch",
         "Because it was built, measured, and it did nothing. A twenty-year chart of "
         "dollars invites the question, so the obvious answer was tested: divide by a "
         "general price index and read the series in today's money. Across 43 markets it "
         "moved the percentile by one or two points and changed the headline on at most "
         "6% of weeks, clearing on none of the nine asset classes where gold clears "
         "eight. The drift you can see here is mostly the market getting bigger, and the "
         "general price level has not quite doubled while some of these markets grew "
         "twenty-fold, so there was never enough in the index to remove it."),
        ("What answers the drift instead",
         "The percentile, which is why it is on every reading here rather than left to "
         "the axis: it asks where this week sits in this set's own history, and a "
         "history that drifts upward does not fool a rank the way it fools an eye. Then "
         "the Crowding switch below, which removes the growth itself. Neither divides by "
         "a price index, and what was measured was that ONE index rather than the whole "
         "idea: a trade-weighted dollar was never tested here and would be the next "
         "thing to try if you wanted one."),
        ("The Crowding switch",
         "Divides by the same set's own open interest, so the line is the share of the "
         "market this group holds rather than the money it has at stake. It is the only "
         "control here that removes market GROWTH rather than the price level, which is "
         "what a deflator removes, and on the drift this page exists to fight it is the "
         "strongest of the three: Metals runs 24.4 times its early history in dollars "
         "and 1.8 in share, Fixed Income 14.1 and 1.0. It is a share, so it reads the "
         "same with Gold on or off."),
        ("Where Crowding does not help",
         "Softs and Currencies, where it changes almost no reading, so it is not a "
         "strict improvement on dollars and the switch is a switch rather than a "
         "default. Two more things to hold. It answers how crowded relative to the "
         "market and NOT how much money is at stake, so a set can grow its share while "
         "cutting its position if the market shrank faster. And the contribution table "
         "below stays in dollars while this is on, because per-market shares do not add "
         "up to the set's share the way dollars do."),
        ("What gold is here",
         "A hard-money benchmark: a second asset the first is being measured against, "
         "not a fixed ruler. It has run 6.6% a year since 1978 at 19% volatility and "
         "has spent long stretches falling, 63% between 1980 and 1999, so both ends of "
         "the comparison move and a change in the series can be gold rather than "
         "positioning. That is rare week to week, under 4% of weeks disagree on "
         "direction, and it is the whole point over years. Gold measured in gold is "
         "just its contract count, so a Metals total in ounces carries one "
         "self-referential market."),
        ("The dotted line, on one market",
         "The same leg's raw contract count on the same percentile, drawn under the "
         "dollars on the %ile scale. Where the two part, the money at stake moved and "
         "the position did not: dollar risk is contracts times price times volatility, "
         "so a quiet position in a market that has become expensive or violent reads as "
         "an extreme in dollars and as nothing at all in contracts. It is not a second "
         "opinion, and it is not a volatility chart either: the gap correlates only "
         "0.30 with the market's own dollar volatility and flips sign across markets, "
         "because volatility acts on a position that has a side. Most weeks the two "
         "agree, median gap 5.4 percentile points, and the sentence under the headline "
         "appears only when they do not. The shading between the two lines is the gap "
         "itself; at full range the panel shows the envelope of it, so drag across the "
         "chart to open up one episode."),
        ("The Lookback switch",
         "What a percentile is measured against. All history ranks each week among "
         "every week before it, which is the only setting that can say a thing has "
         "never been bigger; 26 and 52 weeks are the app's own lookback vocabulary, a "
         "range over a trailing window; Custom is the per-market tuned window and is "
         "available only where every selected market shares one, since the universe "
         "spends 25 different values on it from 8 weeks to 216 and a total has one "
         "rank. A window renormalises every week, so it answers "
         "\u201cextreme lately\u201d rather than \u201cextreme ever\u201d, and it "
         "hides the side: on 52 weeks a reading above 50 is a net SHORT position 12.5% "
         "of the time at the median market and 62% on the Russell, against 0.2% on all "
         "history. Everything ranked on this page moves with it: the headline, the "
         "band, the %ile scale, and both percentile columns of the table below."),
        ("The Scale switch",
         "Level plots the dollars; %ile plots where each week sat in the history up to "
         "itself, 0 to 100. On a long set the level view is dominated by recent years "
         "whatever the positioning did, because dollar figures carry the price level: "
         "on Metals since 1989 the typical weekly figure grew about 48 times between "
         "the 1990s and the 2020s. %ile puts every year on the same footing. The band "
         "goes flat at 10 and 90 there, and the hover still tells you the dollars."),
        ("The volatility panel",
         "The second factor of the number above it. Dollar risk is notional times "
         "volatility, the price panel at the top already carries the first factor, and "
         "without this one you can watch dollar risk climb with the position unchanged "
         "and have no way to find out why. On a set it is the volatility of the markets "
         "actually held, weighted by how much of each is held and by gross size so that "
         "members leaning opposite ways cannot send it to infinity; on a single market "
         "it is simply that market's own. Shown annualised because nobody reads 1.3% a "
         "day, while the arithmetic underneath uses the daily figure: a rolling 63 "
         "trading day standard deviation of percentage returns, about a quarter, "
         "needing 42 observations before it says anything."),
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


def contribution_columns(unit, palette, leg, table, numeraire=None, window=None):
    """The table's columns: both units, the percentile of the drawn one, and the bar.

    Both units on every row whichever one is drawn, because they are not substitutes:
    on the Energies complex their percentiles correlate 0.802 with a median gap of 9.6
    percentile points and a worst gap of 69. A reader should be able to see the number
    the page is not currently showing without changing a control.

    The percentile is each market's own, against ITS history, not the total's. That is
    the column the bar cannot carry: a market can be a small part of the total and be at
    the most extreme reading it has ever had, and those are different facts.

    `window` is only ever read for the tooltips: the ranking happens upstream. It is
    here because a header tooltip that names the wrong stretch of time is the same
    defect as a column that ranks over one, and both were true of this table until the
    window was threaded through.
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
            "headerName": column_name(column, suffix, numeraire),
            "field": column,
            "type": "numericColumn",
            "valueFormatter": {
                "function": f"d3.format(',.1f')(params.value / {divisor})"},
            "width": 120,
        }

    percentile = {"function": "params.value == null ? '' : "
                              "d3.format('.0f')(params.value)"}
    columns = [
        {"headerName": "Market", "field": "market", "flex": 1, "minWidth": 130},
        money(unit),
        money(other),
        {"headerName": "%ile", "field": rank, "type": "numericColumn", "width": 80,
         "valueFormatter": percentile,
         # Names the unit, now that a second percentile sits beside it: two columns
         # headed "%ile" and "Contracts %ile" leave the first one to be inferred from
         # the money columns to its left. And names the stretch, because "its own
         # history" is true of every setting of the Lookback control and so tells a
         # reader who changed it nothing.
         "headerTooltip": f"Where this week's {exposure_traces.UNIT_LABELS[unit]} sits "
                          f"against {table_ranked_against(True, window)}"
                          f"{set_coverage_note(len(table) < 2)}, 0 to 100. Follows the "
                          f"Lookback control"},
    ]
    # The other lens, per market. The dollar percentile says whether the money is
    # unusual; this says whether the POSITION is, and the two part company hard: the
    # report this table was measured against has gold at the 88th percentile in
    # contracts and the 99th in dollars in the same week, which is a market whose
    # extreme is price and volatility rather than more contracts. A single market gets
    # this as a sentence under the headline; every other selection got nothing.
    if CONTRACTS_RANK_COLUMN in table.columns:
        columns.append(
            {"headerName": "Contracts %ile", "field": CONTRACTS_RANK_COLUMN,
             "type": "numericColumn", "width": 120,
             "valueFormatter": percentile,
             # Two restrictions on "the same weeks", because a reader checking this
             # against a published figure is off by both: the Lookback window, and
             # the set's own coverage. The second is dropped on one market for the
             # same reason the column to its left drops it, which is that a single
             # market IS the set and the clause has nothing to qualify.
             "headerTooltip": "The same percentile on the raw contract count, over the "
                              "same weeks as the column to its left"
                              f"{set_coverage_note(len(table) < 2, 'which are')}. "
                              "Where it sits below that column, the money is the "
                              "extreme rather than the position",
             # A percentile has no side and this column's whole subject is a position
             # that has one, so the count rides the rowData for the hover. Same reason
             # the single-market lens line carries it.
             "tooltipValueGetter": {
                 "function": f"params.data['{CONTRACTS_COLUMN}'] == null ? null : "
                             f"d3.format('+,.0f')(params.data['{CONTRACTS_COLUMN}']) "
                             f"+ ' contracts'"}})
    # The bar is a SHARE, so one row draws it full width whatever the number is and
    # encodes nothing. Dropped for the same reason the concentration sentence is.
    if len(table) < 2:
        return columns
    return columns + [
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


def contribution_grid(table, unit, palette, leg, numeraire=None, window=None):
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
        columnDefs=contribution_columns(unit, palette, leg, table, numeraire,
                                        window=window),
        className="ag-theme-quartz-dark",
        style={"height": f"{height}px", "width": "100%", "fontSize": "12px"},
        defaultColDef={"sortable": True, "resizable": True, "suppressMenu": True},
        dashGridOptions={"rowHeight": TABLE_ROW_PX, "headerHeight": TABLE_HEADER_PX,
                         "suppressCellFocus": True, "tooltipShowDelay": 400},
        dangerously_allow_code=True,
    )


def caption(frame, unit, leg, when=None, numeraire=None, single=False,
            window=None, window_note=""):
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
    rank_text = (f"the {ordinal(rank)} percentile of {window_phrase(window)}"
                 if rank == rank else "no percentile yet, under two years of history")
    return (
        f"{exposure.LEG_LABELS[leg]} are {side} {money(value, suffix, numeraire, unit)} "
        f"({unit_name(unit, numeraire)}) as of {row.name:%B %d, %Y}, "
        f"which is {rank_text}. {exposure_traces.UNIT_NOTES[unit]} "
        + (f"Lookback: {window_note}. " if window_note else "")
        + (f"The shaded band is the 10th to 90th percentile of the last {window} "
           f"weeks, moving with the line rather than behind it, and neither carries "
           f"look-ahead: a trailing window ends at the week it describes. "
           if window else
           "The shaded band is the 10th to 90th percentile of the history up to each "
           "week, so it carries no look-ahead and neither does the percentile. ")
        +
        "Positioning is as-of Tuesday and published the following Friday: it is "
        "plotted at the Tuesday it describes, which is three days before anyone could "
        "have acted on it. " + (
            "The top panel is that market's own price, rebased to 100."
            if single else
            "The top panel is an equal-weight composite of the same markets, rebased "
            "to 100, and not any index you can trade.")
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
        # Where the zoom handler writes. It has nothing to say to the server; the store
        # exists because a Dash callback needs an Output and this one does its work in
        # the browser.
        dcc.Store(id='exposure_zoom_sink'),
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
                    ], xs=12, md=2, className="px-md-2"),

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
                    ], xs=12, md=2, className="px-md-2 mt-2 mt-md-0"),

                    dbc.Col([
                        html.Label("Leg", style=CONTROL_LABEL),
                        dbc.Select(id='exposure_leg_selector', options=LEG_OPTIONS,
                                   value=exposure.LEG_SPEC, size="sm",
                                   className="bg-dark text-white border-secondary"),
                    ], xs=7, md=2, className="px-md-2 mt-2 mt-md-0"),

                    dbc.Col([
                        # Beside Scale and Unit rather than beside Markets, because it
                        # decides what a percentile is measured AGAINST rather than what
                        # is in the total.
                        html.Label("Lookback", style=CONTROL_LABEL),
                        dbc.Select(id='exposure_lookback_selector',
                                   persistence='session',
                                   options=LOOKBACK_OPTIONS, value=LOOKBACK_ALL,
                                   size="sm",
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
                        # Two controls in one column because they are orthogonal and
                        # both are small. Scale is what the axis plots; Gold is what the
                        # dollars are measured against, and the interesting combination
                        # is BOTH: the percentile of the gold-denominated series is a
                        # different number from the percentile of the dollar one. On the
                        # same week, US equity speculators read 98 in USD and 67 in
                        # ounces of gold.
                        #
                        # Scale is not a log toggle, which is what a broad axis usually
                        # asks for and which cannot apply here: the exposure series is
                        # signed and crosses zero, so log is undefined on it.
                        html.Label("Scale", style=CONTROL_LABEL),
                        html.Div([
                            dbc.RadioItems(id='exposure_scale_selector',
                                           persistence='session',
                                           options=SCALE_OPTIONS,
                                           value=exposure_traces.SCALE_LEVEL,
                                           inline=True, className="me-3",
                                           style={"color": vc.BRIGHTER_TEXT_COLOR,
                                                  "fontSize": "0.85rem"}),
                            dbc.Switch(id='exposure_crowding_toggle', label="Crowding",
                                       persistence='session',
                                       value=False, className="mb-0 me-3"),
                            dbc.Tooltip(
                                "Divide by the same set's own open interest, so the line "
                                "is the share of the market it holds rather than the "
                                "money at stake. Removes market GROWTH, which no "
                                "deflator does: Metals drift 24.4x to 1.8x. It adds "
                                "nothing on Softs or Currencies, and the contribution "
                                "table below stays in dollars, because shares do not "
                                "add.",
                                target='exposure_crowding_toggle', placement="bottom"),
                            dbc.Switch(id='exposure_gold_toggle', label="Gold",
                                       persistence='session', value=False,
                                       className="mb-0",
                                       style={"color": vc.BRIGHTER_TEXT_COLOR,
                                              "fontSize": "0.85rem"}),
                        ], className="d-flex align-items-center"),
                        dbc.Tooltip(
                            "Divide by the gold price, so the series is in troy ounces "
                            "rather than dollars. Dollar figures carry the price level; "
                            "gold removes most of that drift (the equity composite's "
                            "late history runs 3.2x its early history in dollars and "
                            "0.8x in gold). Gold is an asset, not a ruler, and gold "
                            "itself in gold terms is just its contract count.",
                            target='exposure_gold_toggle', placement="bottom"),
                    ], xs=12, md=2, className="px-md-2 mt-2 mt-md-0"),
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


def describe_week(agg, part_frames, unit, leg, palette, when=None, ranks=None,
                  dollar_unit=None,
                  window=None, window_note=""):
    numeraire = getattr(agg, "numeraire", None)
    """Everything the page says about ONE week, in one place.

    Both entry points come through here: the full render, which describes the latest
    week, and a click, which describes the one under the cursor. Written once because
    the alternative is two code paths that agree until one of them is edited, and the
    thing they would disagree about is what the numbers on screen mean.
    """
    stamp = snap_week(agg.frame, when)
    shown = stamp if stamp is not None else (
        agg.frame.index[-1] if not agg.frame.empty else None)

    # The SAME window the headline, the band and the rank scale were given. The table
    # ranked expanding whatever the Lookback control said, so a reader on "52 weeks"
    # read "higher than 97% of the last 52 weeks" directly above a "%ile" column
    # measured against twenty years, with both on screen at once and nothing saying
    # they were different questions. Threading it through is the only fix: copy can
    # describe two bases, it cannot make them comparable, and the control exists
    # because the window is the reader's choice rather than the page's.
    table = exposure.contribution_table(agg.members, when=stamp, window=window,
                                        min_rank_periods=exposure_traces.MIN_RANK_PERIODS)
    # Moves with the dollar columns or not at all: the contract percentile is only a
    # second lens on the same week if the two were ranked over the same weeks.
    table = attach_contracts_rank(table, agg, when=stamp, window=window)
    # The table is per-market contributions that SUM to the total, and shares do not
    # sum. So it stays in dollars while the chart above it is a share, and the copy
    # says so rather than leaving a reader to notice the units disagree.
    bars = contribution_grid(table, dollar_unit or unit, palette, leg, numeraire,
                             window=window)
    label = ("" if not len(table) else
             f"Week of {shown:%B %d, %Y}, against {table_ranked_against(True, window)}."
             if len(table) == 1 else
             f"What made it, week of {shown:%B %d, %Y}. Percentiles are each market "
             f"against {table_ranked_against(False, window)}"
             f"{set_coverage_note(False)}.")

    # One source for the noun the copy uses, from what was actually summed rather than
    # from what was asked for: a two-name selection where one dropped for want of a
    # multiplier IS a single market, and the sentences should say so.
    single = len(agg.coverage) == 1
    head_text, head_colour = headline(agg.frame, unit, leg, when=stamp,
                                      numeraire=numeraire, single=single, window=window)
    return dict(
        bars=bars,
        bar_label=label,
        # Two sentences, not one, and never both: a set gets what its total is made
        # of, a single market gets what its other lens says. `contracts_rank` returns
        # None for a set, so the second is empty exactly where the first is not.
        composition=" ".join(part for part in (
            composition_line(agg, unit, leg, part_frames, when=stamp,
                             numeraire=numeraire),
            lens_line(agg, unit, when=stamp,
                      ranks=contracts_rank(agg, window) if ranks is None else ranks),
        ) if part),
        headline=head_text,
        head_style={**HEAD_STYLE, "color": head_colour},
        caption=caption(agg.frame, unit, leg, when=stamp, numeraire=numeraire,
                        single=single, window=window, window_note=window_note),
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


# Re-fit the axes to whatever window is on screen.
#
# Plotly's own `autorange` spans ALL of a trace's data rather than the part in view, so
# without this a two-year zoom keeps a y axis fitted to twenty years and the window is
# drawn as a flat sliver against ticks chosen for decades it is not showing. Measured on
# this page before the fix: zooming x to 2024-2026 and then asking for autorange
# returned the identical full-history range, 64 to 1,321 on Silver.
#
# Clientside because the data is already in the browser: a server callback would ship
# the whole figure back and forth on every drag. It is the SAME handler the Aggregation
# page uses, which had already solved two traps worth keeping: Plotly packs numeric
# columns as base64 rather than arrays, and `autosize` fires on first paint and on every
# window resize where the reader has asked for nothing. What this page adds travels in
# the figure, as `layout.meta.refit`, so the rules live in one place.
clientside_callback(
    "window.dash_clientside.clientside.autoscale_y_axes",
    Output('exposure_zoom_sink', 'data'),
    Input('exposure_chart', 'relayoutData'),
    State('exposure_chart', 'id'),
    prevent_initial_call=True,
)


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
    Input('exposure_lookback_selector', 'value'),
    Input('exposure_gold_toggle', 'value'),
    Input('exposure_crowding_toggle', 'value'),
    Input('session_palette_theme_asset_store', 'data'),
)
def render_exposure(asset_classes, members, leg, unit, scale, lookback, in_gold,
                    crowding, palette_name):
    palette = viz_config.get_palette(palette_name)
    colors = grid_colors(palette)
    leg = leg or exposure.LEG_SPEC
    unit = unit or exposure_traces.UNIT_RISK
    # The Crowding switch is a change of COLUMN, not a second code path. `unit` is the
    # column name everything downstream resolves against, so swapping it here gives the
    # chart, the headline, the rank, the band and the axis label their share versions at
    # once. The contribution table is the one thing that must not follow: shares do not
    # add across markets, so it keeps the dollar column and says so.
    dollar_unit = unit
    if crowding:
        unit = exposure_traces.SHARE_OF[unit]
    scale = scale or exposure_traces.SCALE_LEVEL
    numeraire = (exposure.NUMERAIRE_GOLD if in_gold else exposure.NUMERAIRE_USD)

    help_block = help_children(unit)
    if not asset_classes:
        empty = exposure_traces.build_figure(None, None, unit=unit, colors=colors,
                                             palette=palette)
        no_bars = contribution_grid(None, dollar_unit, palette, leg)
        return (empty, no_bars, "", "", "",
                {**HEAD_STYLE, "color": vc.TEXT_COLOR}, help_block,
                "Select an asset class.", "", None, "", {"display": "none"})

    # An empty member list is the moment between a class change and the callback that
    # repopulates it, not a request for an empty total.
    names = list(members) if members else _names_in(asset_classes)
    window, window_note = resolve_window(lookback, names)
    agg = exposure.aggregate_exposure(
        names, leg=leg, numeraire=numeraire, rank_window=window,
        min_rank_periods=exposure_traces.MIN_RANK_PERIODS)
    composite = exposure.composite_price_index(
        list(agg.coverage), dates=agg.frame.index,
        numeraire=numeraire) if not agg.frame.empty else None

    # The other Legacy legs, for the companion panel. Computed over the same member
    # list rather than the same date index, so a leg whose completeness differs is
    # reindexed onto the subject in build_figure rather than silently shifted here.
    part_frames = {}
    for part_leg in exposure_traces.COMPANION_LEGS.get(leg, ()):
        part = exposure.aggregate_exposure(
            names, leg=part_leg, numeraire=numeraire, rank_window=window,
            min_rank_periods=exposure_traces.MIN_RANK_PERIODS)
        part_frames[part_leg] = part.frame[unit] if not part.frame.empty else None

    ranks = contracts_rank(agg, window)
    figure = exposure_traces.build_figure(
        agg.frame, composite, unit=unit, colors=colors, palette=palette,
        leg_label=exposure.LEG_LABELS[leg],
        # One market: name IT. "Metals - Speculators, daily risk" over a chart holding
        # Gold alone labels a set the reader did not ask for.
        set_label=(names[0] if len(agg.coverage) == 1 and len(names) == 1
                   else ", ".join(asset_classes)),
        leg=leg, parts=part_frames, scale=scale, numeraire=numeraire,
        single=len(agg.coverage) == 1, contracts=ranks,
        contract_counts=contracts_net(agg), window=window)

    said = describe_week(agg, part_frames, unit, leg, palette, ranks=ranks,
                         window=window, window_note=window_note,
                         dollar_unit=dollar_unit)
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

    Labelled points a reader can scan and stop at the one they wanted, where the same
    words as prose are a wall nobody reads and the fold below it is what a wall
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
    State('exposure_scale_selector', 'value'),
    State('exposure_lookback_selector', 'value'),
    State('exposure_gold_toggle', 'value'),
    State('exposure_crowding_toggle', 'value'),
    State('session_palette_theme_asset_store', 'data'),
    State('exposure_chart', 'figure'),
    prevent_initial_call=True,
)
def select_week(click_data, _reset, asset_classes, members, leg, unit, scale, lookback,
                in_gold, crowding, palette_name, current_fig):
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
    dollar_unit = unit
    if crowding:
        unit = exposure_traces.SHARE_OF[unit]
    names = list(members) if members else _names_in(asset_classes)
    numeraire = (exposure.NUMERAIRE_GOLD if in_gold else exposure.NUMERAIRE_USD)

    window, window_note = resolve_window(lookback, names)
    agg = exposure.aggregate_exposure(
        names, leg=leg, numeraire=numeraire, rank_window=window,
        min_rank_periods=exposure_traces.MIN_RANK_PERIODS)
    if agg.frame.empty:
        return (no_update,) * 10

    part_frames = {}
    for part_leg in exposure_traces.COMPANION_LEGS.get(leg, ()):
        part = exposure.aggregate_exposure(
            names, leg=part_leg, numeraire=numeraire, rank_window=window,
            min_rank_periods=exposure_traces.MIN_RANK_PERIODS)
        part_frames[part_leg] = part.frame[unit] if not part.frame.empty else None

    said = describe_week(agg, part_frames, unit, leg, palette, when=when,
                         window=window, window_note=window_note,
                         dollar_unit=dollar_unit)
    latest = agg.frame.index[-1]
    notice, notice_style = rewind_notice(said["shown"], latest)

    patched = Patch()
    patched["layout"]["shapes"] = crosshair_shapes(
        ((current_fig or {}).get("layout") or {}).get("shapes"),
        None if by_reset else said["shown"],
        xref=bottom_axis(current_fig))

    return (said["bars"], said["bar_label"], said["composition"], said["headline"],
            said["head_style"], said["caption"], patched,
            None if by_reset else str(said["shown"]), notice, notice_style)


def bottom_axis(figure):
    """Which x axis the crosshair belongs on, asked of the figure rather than assumed.

    The row count is not fixed: the volatility panel is drawn only when the aggregate
    can supply one, so a figure is three panels or four. `build_figure` records the
    answer in `layout.meta`, and the constant is the fallback for a figure drawn before
    that existed, which is the shape a stale browser tab still holds.
    """
    meta = ((figure or {}).get("layout") or {}).get("meta") or {}
    return meta.get(exposure_traces.XREF_META) or exposure_traces.CROSSHAIR_XREF


def crosshair_shapes(existing, when, xref=None):
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
                       "xref": xref or exposure_traces.CROSSHAIR_XREF,
                       "yref": "paper",
                       "x0": str(when), "x1": str(when), "y0": 0, "y1": 1,
                       "line": CROSSHAIR})
    return shapes
