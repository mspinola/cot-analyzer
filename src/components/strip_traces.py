"""The cross-asset crowding strip: one row per market, on one screen.

The Heatmap already carries every number this draws. What it does not do is let you
see the whole board at once, because reading a grid means reading it column by column.
This is the same verdict as a picture, sorted so the crowded ends of each asset class
collect at the top and bottom of their group.

Three choices here are deliberate departures from how the printed positioning reports
this was modelled on draw the same thing, and each one is a fix for something those
reports get wrong.

**A lollipop diverging from 50, not a min..max rule.** Those reports draw each
market's window range as a bar and put a marker where the current value sits. In index
space that bar is always the full axis, because the index IS the position within the
range, so the rule would carry no information at all. Worse, drawing every market's
range at the same width invites reading two ranges as comparable when one may be eight
times the other. A stem from the neutral midpoint says the one thing that survives the
normalization: how far from neutral, and which way. It also makes the neutral majority
recede on its own, since a market sitting near 50 draws almost no ink.

**Every leg the model gates on, not one collapsed "speculator" series.** Those reports
show a single series, usually the mirror of Commercials, which quietly folds Small
Traders into the speculator leg (the Legacy legs sum to zero, so the mirror of
Commercials is Large PLUS Non-Reportable). This app has kept the legs apart everywhere
else and the gates read them separately, so the strip asks the model which legs it
gates on and draws exactly those. NPF's CS gate has no Large Spec leg, and no Large
Spec marker appears on the NPF strip.

**Colour comes from the ROW's setup state, not from each value's own level.** Same rule
the Heatmap's index cells follow, and for the same reason: a positioning index only
means something in the company of the other legs. A market whose Commercials sit at 97
with a spec leg blocking it draws small, faint and neutral-grey deep inside the bullish
band. That looks wrong until you know the rule, which is why it is written here: the
lollipop's POSITION is the level and its COLOUR is the verdict, and the two disagreeing
is the interesting case rather than a defect.

**One optional comparison per row, in dollars.** Those reports draw the same position
twice, once in contracts and once in US dollars, and the two disagree far more than a
reader expects: on this universe the same 52-week range index computed on dollar risk
(contracts x point value x price x daily volatility) correlates 0.92 with the contract
version at the median, parts from it by 30 index points at the 95th percentile, and
disagrees about whether the market is through the model's own gate band on 12% of
weeks. Silver on 2026-08-18 is the case that makes it concrete: Commercials sat at the
very bottom of their 24-week contract range and at 96 on dollars at risk, because
silver's daily volatility had fallen from 6.7% to 2.7% over the same window, so the
larger short carried a third of the money. The mark is off by default and shares its
place on the row with the six-weeks-ago mark, for the reasons at COMPARE_PRIOR.

Everything in here is a pure function over a `get_matrix_data` frame plus a colour set,
so the layout is testable without a store, a palette file or a browser.
"""

from dataclasses import dataclass

import cotmetrics.constants as const
import cotmetrics.models as models
import plotly.graph_objects as go

import viz_constants as vc
from components.plot_colors import hex_to_rgba

# Which `get_matrix_data` columns hold each model's legs.
#
# The frame names its columns for display ("Comm Index Norm"), while a model names its
# legs structurally (LEG_SMALL), so something has to join the two. It is a literal
# rather than derived from `model.leg_columns()` because that returns the indexer's
# frame columns, and this draws from the Signal Matrix, which has already renamed and
# rounded them.
#
# NPF has no Large Spec entry because its CS gate does not read that leg and the matrix
# does not carry the column. test_strip_traces holds this table to `models.MODELS` so a
# new model fails loudly here rather than silently drawing a leg short.
LEG_COLUMNS = {
    models.RAW_PF.key: {
        "comm": "Comm Index",
        models.LEG_LARGE: "Lrg Index",
        models.LEG_SMALL: "Sml Index",
    },
    models.NPF.key: {
        "comm": "Comm Index Norm",
        models.LEG_SMALL: "Sml Index Norm",
    },
}

# Where the index stood MOMENTUM_PERIOD weeks ago, per basis. The generic "Comm Move"
# follows whatever basis get_symbols_data was called with, which is the raw default, so
# under NPF it would be a raw change subtracted from a normalized level. cotmetrics
# carries the normalized twin beside it for exactly this reason.
MOVE_COLUMN = {
    models.RAW_PF.key: "Comm Move",
    models.NPF.key: "Comm Move Norm",
}

# The setup verdict each model resolved onto the row, back in get_matrix_data.
SETUP_COLUMN = {
    models.RAW_PF.key: const.SETUP_CLS_COL,
    models.NPF.key: const.SETUP_NPF_COL,
}

LEG_LABELS = {
    "comm": "Commercials",
    models.LEG_LARGE: "Large Specs",
    models.LEG_SMALL: "Small Traders",
}

# The app-wide leg colours, by palette slot. Every stacked panel in plot_traces draws
# Commercials from slot 0, Large Specs from 1 and Small Specs from 2, so a reader
# arriving from the Graphs or OI Alignment pages already knows what blue and yellow are.
# The strip used one grey for both legs before this, which made its ticks the only place
# in the app where leg identity was not a colour.
LEG_PALETTE_SLOT = {
    "comm": 0,
    models.LEG_LARGE: 1,
    models.LEG_SMALL: 2,
}

# The lollipop's proportions. The head is the datum and gets full-strength colour; the
# stem is context (how far from neutral, which way) and is knocked back for the same
# reason the old filled bars were: `grid_colors` picks colours hot enough for 11px grid
# text, and a run of pixels at that strength reads as glare. A 3-ish-px stem is far less
# ink than a half-row slab, but forty of them still add up.
STEM_ALPHA = 0.55
STEM_WIDTH = 0.14      # in row units; ~3px at ROW_PX
HEAD_SIZE = 9

# Quiet rows are background material: the app's own neutral, `colors.dim` (DIM_TEXT's
# 0.35 white), on a smaller head with a fainter stem.
#
# This colour has been around the loop. Grey bar slabs read as disabled, so the quiet
# tier took the Commercial series red — and that put forty neutral rows in the bear
# verdict's own hue family (#F87171 beside #FF4D4D), where no amount of fading made
# "no verdict" and "bear setup" strangers. Green and red belong to the VERDICTS, the
# same vocabulary as the gate bands behind them, so neutral goes back to the word the
# Heatmap already uses for it: dim. "Disabled" was the slabs' failure, not the
# colour's — a 5px dot at 0.35 is texture — and whose series it is needs no colour to
# say, because every lollipop on this chart is Commercials and the legend and caption
# both say so. viz_constants already orders these alphas (near's 0.5 above dim's
# 0.35) so "approaching" never looks quieter than "neutral"; the smaller head keeps
# the ordering where intensity alone is hard to judge.
QUIET_STEM = "rgba(255, 255, 255, 0.16)"
QUIET_HEAD_SIZE = 5

# A tick's opacity is its ROW's tier, the same rule every other mark on the row
# follows: full strength where the model has a verdict, knocked back where it does
# not. Colour still carries which leg it is — one channel per variable.
#
# Opacity used to carry the leg's own gate state instead (bright when through its
# extreme opposite Commercials), and that spent the channel on something the axis
# already says: a gating leg is BY DEFINITION a leg sitting at its own extreme, which
# is exactly where its tick is drawn. Position carries it; the hover names it. Meanwhile
# idle ticks at 0.4 had sunk to the background tier where the quiet lollipops live,
# and the legs are DATA — where the other side of the trade sits — not chrome. Rows
# worth inspecting now light whole: verdict, name, and every leg on them.
TICK_ALPHA_LIT = 1.0
TICK_ALPHA_QUIET = 0.55

# Same two words the Active Setups strip uses, so one vocabulary across the app.
STATE_LABELS = {
    const.SETUP_BULL: "SETUP",
    const.SETUP_BEAR: "SETUP",
    const.SETUP_NEAR_BULL: "NEAR",
    const.SETUP_NEAR_BEAR: "NEAR",
}

# Row geometry, in pixels. Tight on purpose: the point of two columns is to get the
# whole board onto one screen, and every pixel per row is 50-odd pixels of scrolling.
# 22 rather than the 19 it started at: four marks share a row, and at 19px they read
# in the browser as one blurred lane. The column that the stretch bug (see
# align="start" in strip.py) accidentally spread to ~23px was the easier half of the
# page to read, which settled the number by experiment.
# ONE height for every row, because the y axis is linear over
# the row count and spreads them evenly whatever this file would prefer. Two constants
# here, a taller one for class headers, only ever made the figure taller than the rows it
# held; it did not give the header more room. Air between the classes comes from a real
# empty row instead, which the axis does honour.
ROW_PX = 22
# A hairline on the boundary between two market rows, which is what ties a row's marks
# to each other and separates them from the row above.
#
# This was an alternating filled band for a long time, and the band was calibrated twice
# on a real monitor before being abandoned: 0.035 did not read at all, 0.06 read as
# white stripes with data in the gaps, and 0.045 sat between them. The thing none of
# those numbers could fix is that a filled band is a RHYTHM. Every other row is lit, so
# an eleven-row class (Currencies is the real worst case) carries a ladder that the eye
# resolves before it resolves the data, and the treatment meant to help you read a row
# is the second-loudest element on the page after the gate zones.
#
# A rule has no rhythm: every row is treated alike and gets a floor rather than a fill.
# It is also far less ink for the same association, which is why it can sit at a higher
# alpha than the band ever could and still be quieter overall. 0.10 of the app's neutral
# white is visible as a lane edge at ROW_PX and disappears behind any actual mark.
#
# Three alternatives were drawn on the same board before this one was picked. Nothing at
# all is calmer still and fails on exactly one case, a row whose only right-hand mark is
# a lone leg tick, where the eye has 700px to cross with no guide. A hairline THROUGH
# each row (a leader from the name to the marks) is collinear with the stem, so it reads
# as the stem continuing past its head and fights the one thing the stem measures. And a
# half-strength band keeps the rhythm while losing most of the association.
ROW_RULE_ALPHA = 0.10

# The heading's own row, above the row rules and below the gate zones. It has to read as
# a label bar rather than as another market row, and it must not outrank the shading
# that means something. It is the app's neutral white rather than any verdict colour,
# for the reason the quiet tier is: red and green on this figure belong to the verdicts,
# and a class name has no verdict.
HEADER_BAND_ALPHA = 0.07

# The top margin holds only the top axis. The legend that used to sit above it inside
# the first figure is page chrome now (`legend_items` below): Plotly stacked the two
# legend groups vertically, the stack outgrew the margin arithmetic that tried to
# predict its height, and Plotly quietly pushed that one figure's margin out — which
# left the left column's rows ~40px below the right column's. A constant margin on
# every figure is what keeps the columns level, and there is nothing above the axis
# left to collide with it.
TOP_CHROME_PX = 34
BOTTOM_CHROME_PX = 46

# The axis stops just past 100. It used to run to 128 to carry two text columns, the
# index value and the gate verdict, in fixed positions where they could not collide with
# a bar end the way the printed reports' labels do. Both are gone: the bar's position
# against the banded axis already says the level, and its colour already says the
# verdict, so the columns were a second copy of two things the picture had. The exact
# numbers are still one hover away, which is what makes dropping them cheap here and
# would not on a printed page.
AXIS_MAX = 104

# The name column, sized to the text rather than to a guess.
#
# It was 140 while the class headings lived out here too, left-aligned above the market
# names. They sit centred on their own row now, so the only thing this has to hold is
# the widest instrument name in the universe. Measured in the browser at the tick font
# (10px, Plotly's default family) against every name in cotmetrics-config: the widest is
# "MSCI Emerging Mkts" at 105px, and the widest one currently PLOTTED is "Australian
# Dollar" at 83px.
#
# Sized to the first, not the second, because roles change. MSCI Emerging Mkts and S&P
# MidCap 400 are the two longest and both are `heldout` today, so a margin fitted to
# what is on screen would clip the day either is promoted to `deploy`, and it would clip
# quietly, as a shortened name rather than an error. 124 is 105 of text plus the 7px
# TICK_STANDOFF_PX leaves before the plot and 12px of air at the figure's own edge.
# Re-measure before trimming further; a name longer than that one is what breaks this.
LEFT_MARGIN_PX = 124
TICK_STANDOFF_PX = 12

# Filters. Two axes, deliberately, because they answer different questions and never
# contradict each other: SHOW is about the model's verdict, SIDE is about which half of
# its own range the market sits in. A bull setup is above neutral by construction, so no
# combination of the two can select an empty contradiction.
SHOW_ALL = "all"
SHOW_SETUPS = "setups"
SHOW_SETUPS_NEAR = "setups_near"
SHOW_STATES = {
    SHOW_ALL: None,   # no filter
    SHOW_SETUPS: set(const.SETUP_FULL_STATES),
    SHOW_SETUPS_NEAR: set(const.SETUP_FULL_STATES) | set(const.SETUP_NEAR_STATES),
}

SIDE_BOTH = "both"
SIDE_BULL = "bull"
SIDE_BEAR = "bear"

# The reference mark: ONE second position per row, and which one is a choice.
#
# A row already carries the head, its stem and a tick per gated leg. The two things
# worth putting beside them answer the same shape of question, "the same leg measured
# differently", and they compete for the same few pixels: where this index stood
# MOMENTUM_PERIOD weeks ago (differently in TIME), and where it sits when the position
# is measured in dollars at risk rather than in contracts (differently in UNIT).
#
# Drawing both was tried and is the reason this is a selector. At ROW_PX a hollow ring
# and a hollow diamond a few points apart are one smudge, and on a quiet row they are
# the same colour as well, so the row stops saying which is which. One at a time keeps
# every mark on the row nameable, and the legend and caption then only have to explain
# the comparison actually on screen.
#
# COMPARE_DOLLARS is the newer one and it is off by default, because it is the only
# thing this page draws that needs the price store: a market with no contract
# multiplier or no bars has no dollar reading at all, and the caption has to say so.
COMPARE_PRIOR = "prior"
COMPARE_DOLLARS = "dollars"
COMPARE_NONE = "none"

# The dollar mark and the line back to the head.
#
# Shape carries which comparison this is (a hollow diamond, against the prior mark's
# hollow ring), and colour stays what it is everywhere else on this row: the ROW's
# tier, verdict or quiet. Spending colour on "this one is the dollar reading" would put
# a third meaning on the one channel that already means verdict here, and the palette
# has no free slot for it anyway: slot 3 is Price AND the bull colour, slot 0 is
# Commercials AND the bear colour.
#
# The connector is what makes the pair read as one fact rather than as two marks. It is
# the opposite call from the prior mark, which deliberately has no connector, and the
# reason is that here the GAP is the subject: contracts and money disagreeing about the
# same week is the whole reason to switch this on. It also costs nothing on the rows
# with nothing to say, since a market where the two agree draws a line of zero length.
DOLLAR_SYMBOL = "diamond-open"
DOLLAR_SIZE = 8
WEDGE_ALPHA = 0.45
WEDGE_WIDTH = 1

# How the Commercial index is drawn: ONE form, a lollipop — a thin stem from the
# neutral midpoint with a full-strength head at the value.
#
# This page shipped with two switchable marks, a filled bar and a bare diamond, because
# neither had won. The bar's fill was a half-row of colour saying one number; the
# diamond scattered over an empty row and did not scan — read side by side, the bare
# marks were the harder half to interpret. The lollipop is the working part of each:
# the stem is the bar's at-a-glance answer to "how far from neutral, and which way",
# on a twentieth of the ink, and the head is the diamond's precise position, sized to
# carry the hover.


@dataclass(frozen=True)
class DollarRead:
    """The same market, the same leg and the same window, measured in MONEY.

    `index` is the range index the row's head already carries, recomputed on dollar
    risk (contracts x point value x price x daily volatility) rather than on contracts
    or on share of open interest. The rest is hover material: the level behind the
    index, the volatility that scaled it, the window it was measured over, and the
    notional index, which is drawn nowhere and is carried because it is the reading the
    printed reports use (see COMPARE_DOLLARS).
    """
    index: float
    risk_usd: float = None
    notional_index: float = None
    sigma_daily: float = None
    weeks: int = None


@dataclass(frozen=True)
class StripRow:
    """One line of the strip: an asset-class header, a market, or a blank spacer."""
    kind: str            # "class", "market" or "spacer"
    label: str
    asset_class: str
    comm: float = None
    legs: tuple = ()     # ((leg_key, value, is_gate_leg), ...)
    state: str = const.SETUP_NONE
    is_equity: bool = False
    prior: float = None  # where the index stood MOMENTUM_PERIOD weeks ago
    dollar: DollarRead = None   # the same reading in dollars at risk, or None


def _num(value):
    """A matrix cell as a float, or None. Cells arrive rounded, absent or NaN."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def is_gate_leg(comm, leg_value, model, is_equity):
    """Whether this speculator leg is currently helping the gate rather than blocking.

    A leg only counts when it is opposed to Commercials AND through its own threshold,
    which is what the gates ask of it. Equities are excluded outright because
    `utils.is_setup` decides an equity setup on Commercials alone, so colouring an
    equity's spec leg would claim it was consulted. The Heatmap's spec cells carry the
    same guard, for the same reason.
    """
    if is_equity or comm is None or leg_value is None:
        return False
    if comm >= model.high:
        return leg_value <= model.low
    if comm <= model.low:
        return leg_value >= model.high
    return False


def keeps(row, show, side):
    """Whether the filters let this market through."""
    states = SHOW_STATES.get(show)
    if states is not None and row.state not in states:
        return False
    if side == SIDE_BULL:
        return row.comm > const.INDEX_NEUTRAL
    if side == SIDE_BEAR:
        return row.comm < const.INDEX_NEUTRAL
    return True


def band_of(value, model):
    """Which of the model's three bands a 0-100 reading sits in: -1, 0 or +1.

    Three, not two. Asking only "is it through a gate" scores the sharpest
    disagreement on the board as agreement: Silver on 2026-08-18 sat at 0 on contracts
    and 96 on dollars at risk, which is both ends of the axis at once, and a boolean
    calls that a match because both are extremes.

    The bands are also why this is asked here rather than on a gap in points. Contracts
    at 98 against dollars at 90 is a wide gap the model answers the same way twice,
    while 96 against 94 under NPF straddles the line and changes the answer.
    """
    if value is None:
        return None
    if value >= model.high:
        return 1
    if value <= model.low:
        return -1
    return 0


def dollar_split(rows, model):
    """`(disagree, missing)` over the drawn market rows.

    `disagree` counts rows where the contract reading and the dollar reading are not
    on the same side of the model's gate bands, which is the one difference between
    the two lenses that changes an answer. `missing` counts markets with no dollar
    reading at all: no contract multiplier in the specs table, or no bars to price.

    Both are for the caption, and both exist for the same reason the skipped-market
    count does. A board where six rows quietly have no second mark looks exactly like
    a board where six markets agree.
    """
    markets = [r for r in rows if r.kind == "market"]
    missing = sum(1 for r in markets if r.dollar is None or r.dollar.index is None)
    disagree = sum(1 for r in markets
                   if r.dollar is not None and r.dollar.index is not None
                   and band_of(r.comm, model) != band_of(r.dollar.index, model))
    return disagree, missing


def build_rows(df, model, sort_by_index=True, show=SHOW_ALL, side=SIDE_BOTH,
               dollars=None):
    """`(rows, skipped)` for one Signal Matrix frame.

    Markets with no index at the selected week cannot be placed on the axis, so they
    are dropped and counted. The count is returned rather than swallowed: a strip that
    silently showed 44 of 47 markets would read as a complete board.

    Filtered-out markets are a different thing and are NOT counted here. The caller
    knows the filter it asked for, and a class left empty by one loses its header rather
    than sitting there as a heading over nothing.

    `dollars` is an optional `{asset: DollarRead}` table, joined onto the rows here so
    the figure stays pure over rows. It is the caller's job to have it match the week
    being drawn; this only looks a name up.
    """
    cols = LEG_COLUMNS[model.key]
    state_col = SETUP_COLUMN[model.key]
    move_col = MOVE_COLUMN[model.key]

    by_class = {}
    skipped = []
    for record in df.to_dict("records"):
        comm = _num(record.get(cols["comm"]))
        asset = record.get("Asset")
        if comm is None:
            skipped.append(asset)
            continue
        is_equity = bool(record.get(const.IS_EQUITY_COL))
        legs = []
        for leg in model.spec_legs:
            if leg not in cols:
                continue
            value = _num(record.get(cols[leg]))
            legs.append((leg, value, is_gate_leg(comm, value, model, is_equity)))
        move = _num(record.get(move_col))
        market = StripRow(kind="market", label=asset,
                          asset_class=record.get("Asset Class"),
                          comm=comm, legs=tuple(legs),
                          state=record.get(state_col) or const.SETUP_NONE,
                          is_equity=is_equity,
                          # Clamped, because the index is bounded and the change is a
                          # point difference: a market that ran from 2 to 98 would put
                          # its prior mark off the axis otherwise.
                          prior=None if move is None
                          else min(100.0, max(0.0, comm - move)),
                          # Keyed by the display name, the same key the frame and the
                          # caller's dollar table both use. A market absent from that
                          # table is one that cannot be priced, which is a state the
                          # row has to carry rather than a lookup that may fail.
                          dollar=(dollars or {}).get(asset))
        if not keeps(market, show, side):
            continue
        by_class.setdefault(market.asset_class, []).append(market)

    rows = []
    for asset_class, markets in by_class.items():
        # A blank row before each class after the first. The separator rule alone left
        # the groups touching, so the break read as a line through a continuous list
        # rather than as space between two lists. The rule now sits in the middle of the
        # gap, with air on both sides of it.
        if rows:
            rows.append(StripRow(kind="spacer", label="", asset_class=asset_class))
        # Descending, so the crowded-long end of each group sits at the top of it and
        # the crowded-short end at the bottom. The printed reports keep a fixed order
        # inside each class, which means finding the extremes is a full read of it.
        if sort_by_index:
            markets = sorted(markets, key=lambda r: r.comm, reverse=True)
        else:
            markets = sorted(markets, key=lambda r: r.label)
        rows.append(StripRow(kind="class", label=asset_class,
                             asset_class=asset_class))
        rows.extend(markets)
    return rows, skipped


def split_columns(rows, columns=2):
    """`rows` dealt into `columns` lists, breaking only between asset classes.

    A laptop is far wider than the strip needs and far shorter than 50 rows, so one
    column wastes the axis it has and scrolls for the rows it does not. Splitting keeps
    every class whole, because a class broken across a column boundary would put half
    of Metals at the bottom left and half at the top right, which is worse than
    scrolling.

    Balance is by ROW count rather than by class count: the classes are wildly uneven
    (Currencies has eleven markets, Crypto two), so dealing them evenly would leave one
    column twice the length of the other.
    """
    if columns <= 1 or not rows:
        return [rows]

    # One block per class, each carrying the spacer that precedes it. A block that ends
    # up first in a column drops that spacer, since it would be a gap under the legend
    # rather than between two classes.
    blocks, current = [], []
    for row in rows:
        if row.kind == "class" and current:
            blocks.append(current)
            current = [row]
        elif row.kind == "spacer":
            if current:
                blocks.append(current)
                current = []
            current.append(row)
        else:
            current.append(row)
    if current:
        blocks.append(current)
    # Re-attach each spacer to the block after it.
    merged = []
    for block in blocks:
        if block and block[0].kind == "spacer" and len(block) == 1:
            merged.append(block)
        elif merged and merged[-1] and merged[-1][-1].kind == "spacer":
            merged[-1] = merged[-1] + block
        else:
            merged.append(block)
    blocks = [b for b in merged if any(r.kind != "spacer" for r in b)]

    target = len(rows) / columns
    out, chunk = [], []
    for i, block in enumerate(blocks):
        blocks_left = len(blocks) - i
        # Columns still unstarted AFTER this break, which is the number the remaining
        # blocks have to fill. Counting the column we are about to close made this one
        # too many, so two classes and two columns never split at all.
        cols_after_break = columns - (len(out) + 1)
        # Start a new column when this one has had its share, provided there are still
        # enough blocks left to fill the ones that have not started yet.
        if (chunk and len(out) < columns - 1
                and len(chunk) >= target and blocks_left >= cols_after_break):
            out.append(chunk)
            chunk = []
        chunk.extend(block)
    if chunk:
        out.append(chunk)

    # A column never opens on a blank row.
    return [c[1:] if c and c[0].kind == "spacer" else c for c in out]


def figure_height(rows):
    return TOP_CHROME_PX + BOTTOM_CHROME_PX + ROW_PX * len(rows)


def _block_spans(rows):
    """The y extent of each run of MARKET rows, in row units.

    A row occupies i-0.5 to i+0.5 on the y axis (the axis runs over row indices, see
    update_yaxes), so a run from a to b covers a-0.5 to b+0.5. Class headers and blank
    spacers both end a run, which is what leaves the whole break between two classes,
    the gap and the heading in it, clear of the gate colours. Returns [] for rows with
    no markets at all, which split_columns already prevents but a hand-written caller
    can still hand over.
    """
    spans, start = [], None
    for i, row in enumerate(rows):
        if row.kind == "market":
            if start is None:
                start = i
        elif start is not None:
            spans.append((start - 0.5, i - 1 + 0.5))
            start = None
    if start is not None:
        spans.append((start - 0.5, len(rows) - 1 + 0.5))
    return spans


def _verdict_colour(row, colors):
    """The model's colour for a row it has something to say about, else None. See the
    module docstring on why it is the row's state and not the value that decides."""
    return {const.SETUP_BULL: colors.bull,
            const.SETUP_BEAR: colors.bear,
            const.SETUP_NEAR_BULL: colors.bull_near,
            const.SETUP_NEAR_BEAR: colors.bear_near}.get(row.state)


def _mark_colour(row, colors, palette):
    """Colour for a market's lollipop head: the verdict, or the app's neutral dim.

    Green and red are the model's words — bull setup and bear setup, the same pair the
    gate bands speak — so a row the model has nothing to say about must not borrow
    either. See the QUIET_STEM comment for the two colours this tier wore first and
    why each failed.
    """
    return _verdict_colour(row, colors) or colors.dim


def _stem_colour(row, colors, palette):
    """The stem is one step fainter than its head, whichever tier the head is in."""
    verdict = _verdict_colour(row, colors)
    if verdict:
        return _fill(verdict)
    return QUIET_STEM


def _fill(colour, alpha=STEM_ALPHA):
    """A stem fill from a head colour.

    Only full-strength colours are knocked back. The near-setup colours arrive already
    translucent from `grid_colors`, so fading those again would push a whole tier of
    the ramp out of sight.
    """
    return hex_to_rgba(colour, alpha) if str(colour).startswith("#") else colour


def _leg_colour(leg, lit, palette):
    """A tick's colour: the app's colour for that leg, faded on quiet rows.

    A glyph per leg was the alternative, and the row height is the argument against it.
    At 22px a tick's whole job is to say WHERE on the axis the leg sits, and a diamond
    or a star is several units wide at that scale, so the shape that carries identity
    would blur the position that carries the measurement. Colour is free here, and it is
    the convention every other panel already uses.
    """
    alpha = TICK_ALPHA_LIT if lit else TICK_ALPHA_QUIET
    return hex_to_rgba(palette[LEG_PALETTE_SLOT[leg]], alpha)


def _tick_label(row, colors):
    """The market name, lit when its row has a verdict.

    The name column is where the eye starts, and the lollipop that carries the verdict
    is off to the right of it, so a reader scanning names alone had no way to find the
    setups without tracking across. This is the same variable the head colour carries,
    which is usually a reason not to draw it twice; the exception is that the two live
    at opposite ends of a wide row.
    """
    verdict = _verdict_colour(row, colors)
    if verdict is None:
        return row.label
    return f'<span style="color:{verdict}">{row.label}</span>'


def _money(value):
    """A dollar figure at the scale a reader can hold: bn, m, or k."""
    if value is None or value != value:
        return "n/a"
    sign = "-" if value < 0 else ""
    v = abs(value)
    for unit, size in (("bn", 1e9), ("m", 1e6), ("k", 1e3)):
        if v >= size:
            return f"{sign}${v / size:,.1f}{unit}"
    return f"{sign}${v:,.0f}"


def _dollar_hover(row):
    """The dollar block of a row's hover, or "" when there is nothing to say.

    This is where the notional index lives. It is not drawn, because over a rolling
    window it is very nearly the contract count again (the two agree to a median
    correlation of 0.98, against 0.92 for dollar risk), so a second mark for it would
    sit on top of the first on most rows and say nothing. In the hover it costs one
    line and it is the reading the printed reports plot, so a reader comparing this
    board against one of those can see both numbers rather than wonder which we drew.
    """
    d = row.dollar
    if d is None or d.index is None:
        return "<br><i>No dollar reading: no contract multiplier or no bars.</i>"
    window = f" ({d.weeks}w)" if d.weeks else ""
    notional = ("" if d.notional_index is None
                else f"<br>Same, on notional: {d.notional_index:.0f}")
    sigma = ("" if d.sigma_daily is None
             else f"<br>Daily vol: {d.sigma_daily * 100:.1f}%")
    return (f"<br><br>In dollars at risk{window}: {d.index:.0f}"
            f"<br>Level: {_money(d.risk_usd)}{notional}{sigma}")


def _hover(row, model, compare=COMPARE_PRIOR):
    legs = "".join(
        f"<br>{LEG_LABELS[leg]}: {value:.0f}"
        f"{' (through its gate)' if gate else ''}"
        for leg, value, gate in row.legs if value is not None)
    verdict = STATE_LABELS.get(row.state)
    tail = f"<br><br>{model.title}: {verdict}" if verdict else f"<br><br>{model.title}: no setup"
    equity = "<br>Equity index: gated on Commercials alone" if row.is_equity else ""
    # Only when the mark is on screen. A hover naming a dollar reading with no mark
    # beside it is a claim about a comparison the reader cannot see.
    money = _dollar_hover(row) if compare == COMPARE_DOLLARS else ""
    return (f"<b>{row.label}</b><br>{row.asset_class}"
            f"<br>{LEG_LABELS['comm']}: {row.comm:.0f}{legs}{money}{tail}{equity}")


def _ticks(model):
    """Ticked at the gate values, not at round numbers, because the bands are the
    reason the axis is worth reading at all."""
    return [0, model.low, const.INDEX_NEUTRAL, model.high, 100]


def _tick_text(model):
    return [str(v) for v in _ticks(model)]


# The glyph kinds legend_items hands back. The page renders them as text, so each kind
# is a character there, but the KINDS are named here because which marks exist is this
# module's fact: they mirror the symbols build_figure actually draws.
GLYPH_MARK = "mark"        # the lollipop head
GLYPH_TICK = "tick"        # the line-ns symbol: the speculator legs
GLYPH_CIRCLE = "circle"    # the hollow prior-position circle
GLYPH_DIAMOND = "diamond"  # the hollow dollar mark


def legend_items(model, colors, palette, compare=COMPARE_PRIOR):
    """The legend, as data: `[(group title, [(label, colour, glyph), ...]), ...]`.

    This used to be empty traces inside the first figure, the idiom plot_traces uses.
    It moved out because Plotly stacked the two groups vertically and pushed that one
    figure's top margin to fit, so the column carrying the legend started ~40px below
    the other. As page chrome it is drawn once above both columns, costs the strip no
    figure height, and cannot desynchronise the margins.

    The grouping itself is the point rather than decoration. Read cold, the figure has
    two kinds of mark and no way to tell whose positioning either one is: the first
    reaction to it was "what are the numbers, what are the ticks, is this Commercials
    only?", all three of which are answered here and in the caption rather than left to
    be inferred. "No setup" is a key entry like the verdicts, because on this scheme a
    quiet row is not colourless: it is the Commercial series colour, and a reader has
    to be told that red-ish head does not mean bearish.
    """
    # The reference key names whichever comparison is on, and nothing when neither is.
    # A key for a mark the figure is not drawing is worse than no key at all: it is the
    # one place a reader goes to find out what they are looking at.
    reference = {
        COMPARE_PRIOR: [(f"{const.MOMENTUM_PERIOD}w ago", colors.dim, GLYPH_CIRCLE)],
        COMPARE_DOLLARS: [("Same, in $ at risk", colors.dim, GLYPH_DIAMOND)],
    }.get(compare, [])
    # The neutral keys are as dim as the marks they stand for: a full-strength
    # "No setup" swatch would promise a colour the plot never draws.
    return [
        ("Lollipop: Commercial index",
         [("Bull setup", colors.bull, GLYPH_MARK),
          ("Bear setup", colors.bear, GLYPH_MARK),
          ("Near", colors.bull_near, GLYPH_MARK),
          ("No setup", colors.dim, GLYPH_MARK)] + reference),
        ("Ticks: the legs this gate also reads",
         [(LEG_LABELS[leg], palette[LEG_PALETTE_SLOT[leg]], GLYPH_TICK)
          for leg in model.spec_legs if leg in LEG_LABELS]),
    ]


def build_figure(rows, model, colors, palette, background=vc.BACKGROUND_COLOR,
                 compare=COMPARE_PRIOR):
    """The strip, as one figure.

    `rows` comes from build_rows. Nothing here reads a store, so a caller can hand it
    hand-written rows.
    """
    fig = go.Figure()

    markets = [(i, r) for i, r in enumerate(rows) if r.kind == "market"]
    headers = [(i, r) for i, r in enumerate(rows) if r.kind == "class"]

    # Bands first, so every mark lands on top of them. Only the two extremes are
    # painted: the middle is not a band, it is the absence of one.
    # 0.09 keeps the zones the strongest shading on the page, which is right because
    # they are the only shading that means anything.
    #
    # Painted per BLOCK rather than once over the whole figure, so the blank row
    # between two classes is genuinely blank. Run as one full-height rectangle the
    # colour crossed the gap, which left the separator doing its work against a
    # continuous red and a continuous green and made the break read as weaker than the
    # rows it was separating. Cutting the paint at the gap gives the eye an unbroken
    # line of background all the way across, which is the one thing on this figure that
    # says "new group" without adding any ink at all.
    shapes = [
        dict(type="rect", xref="x", yref="y", x0=x0, x1=x1, y0=y0, y1=y1,
             fillcolor=fill, opacity=0.09, layer="below", line_width=0)
        for y0, y1 in _block_spans(rows)
        for x0, x1, fill in ((0, model.low, colors.bear),
                             (model.high, 100, colors.bull))
    ]
    # The neutral rule stays full height. It is a grid line rather than a zone, and a
    # spine broken in three places stops being one axis a reader can sight down.
    shapes.append(
        dict(type="line", xref="x", yref="paper", x0=const.INDEX_NEUTRAL,
             x1=const.INDEX_NEUTRAL, y0=0, y1=1, layer="below",
             line=dict(color=vc.GRID_COLOR, width=1)))
    # A rule between adjacent market rows, so each row is a lane. See ROW_RULE_ALPHA for
    # why this is a rule rather than the alternating band it replaced.
    #
    # A row carries four marks (Commercials, its prior position, and a tick per
    # speculator leg) on ROW_PX pixels of height, and nothing tied them to each other or
    # separated them from the row above. The printed reference solves the same problem by
    # drawing each asset inside its own rectangle. That rectangle would be the whole axis
    # on every row here, because the index is 0-100 by construction, so it would be
    # identical everywhere and carry nothing; its bottom edge alone does the same work.
    #
    # BETWEEN rows, never around a block. A rule under the last market of a class would
    # close the block off just above the gap that already separates it from the next one,
    # and a rule above the first would double the heading bar's own bottom edge.
    market_ys = [i for i, r in enumerate(rows) if r.kind == "market"]
    shapes += [
        dict(type="line", xref="paper", yref="y", x0=0, x1=1, y0=i + 0.5, y1=i + 0.5,
             layer="below",
             line=dict(color=hex_to_rgba(vc.BRIGHTER_TEXT_COLOR, ROW_RULE_ALPHA),
                       width=1))
        for i in market_ys if i + 1 in set(market_ys)
    ]

    # The heading's own bar, across the full width at HEADER_BAND_ALPHA.
    #
    # This was tried once before and rejected as noise, and what makes it work now is
    # the pair of changes it arrived with: the gate zones stop at the block edges, so
    # the heading row is the only thing painted on it, and the heading sits ON the bar
    # rather than out in the label column. A quiet full-width bar in a gap that is
    # otherwise empty reads as a divider carrying a name, which is the job. The same
    # bar under the old scheme sat on top of a continuous red and green wash and read
    # as a third stripe among many.
    shapes += [
        dict(type="rect", xref="paper", yref="y", x0=0, x1=1,
             y0=i - 0.5, y1=i + 0.5, layer="below",
             fillcolor=vc.BRIGHTER_TEXT_COLOR, opacity=HEADER_BAND_ALPHA, line_width=0)
        for i, _ in headers
    ]

    # Nothing is drawn on the spacer row itself. It used to carry a hairline rule
    # through its middle, from when the blank row alone was the whole separation and the
    # gate colours ran straight through it. Two changes since then made the rule a third
    # divider in a stack of three: the zones stop at the block edges, and the heading
    # below the gap is a bar with a hard top edge. Empty space between two painted
    # blocks separates them on its own.
    fig.update_layout(shapes=shapes)

    if markets:
        # The stem: a hairline bar from neutral to the value, in the head's colour one
        # step fainter. It carries no hover of its own — a 3px target is misery to
        # hit, and the head at its end says the same thing.
        fig.add_trace(go.Bar(
            x=[r.comm - const.INDEX_NEUTRAL for _, r in markets],
            base=[const.INDEX_NEUTRAL] * len(markets),
            y=[i for i, _ in markets],
            orientation="h",
            width=STEM_WIDTH,
            marker=dict(color=[_stem_colour(r, colors, palette) for _, r in markets],
                        line_width=0),
            hoverinfo="skip",
            showlegend=False,
        ))
        # The head: the value itself, carrying the hover. One shape for every row, so
        # a quiet row reads as the same object rather than as a special case — smaller
        # and fainter on the quiet tier, so the verdicts outrank it at a glance.
        heads = [_mark_colour(r, colors, palette) for _, r in markets]
        fig.add_trace(go.Scatter(
            x=[r.comm for _, r in markets],
            y=[i for i, _ in markets],
            mode="markers",
            marker=dict(symbol="circle",
                        size=[HEAD_SIZE if _verdict_colour(r, colors) else
                              QUIET_HEAD_SIZE for _, r in markets],
                        color=heads, line=dict(width=1, color=heads)),
            hovertext=[_hover(r, model, compare) for _, r in markets],
            hoverinfo="text",
            showlegend=False,
        ))

    # Where it stood MOMENTUM_PERIOD weeks ago, as a hollow mark on the same row.
    #
    # No connector to the current mark. The reference charts that do this well draw the
    # two positions and let the row pair them, and 42 connectors is a lot of line for a
    # move that is usually a few points wide.
    prior = ([(i, r.prior) for i, r in markets if r.prior is not None]
             if compare == COMPARE_PRIOR else [])
    if prior:
        # `color`, not just `line.color`. An OPEN symbol draws its outline from
        # marker.color; marker.line is a second stroke around that. Setting only the
        # line left marker.color unset, so Plotly fell back to the template colorway
        # and drew these in its third default colour, a teal green, while the legend
        # key beside them was the colour this actually sets. Nothing errors when a
        # colour is omitted, it just quietly becomes the theme's.
        fig.add_trace(go.Scatter(
            x=[v for _, v in prior], y=[i for i, _ in prior],
            mode="markers",
            marker=dict(symbol="circle-open", size=6, color=colors.dim,
                        line=dict(width=1.2, color=colors.dim)),
            hoverinfo="skip", showlegend=False,
        ))

    # The same leg, the same window, measured in dollars at risk: a hollow diamond at
    # the dollar reading and a hairline back to the head it disagrees with.
    #
    # The line first, so the two marks sit on top of it rather than behind it. One
    # trace with None breaks between segments rather than one per row: Plotly colours a
    # line per trace, so per-row colour would mean forty traces, and a single quiet
    # neutral is the right answer anyway. The marks at either end carry the row's tier;
    # the line only has to say which two belong together.
    #
    # Ink is self-limiting here, which is the property that makes it safe to leave on
    # for the whole board: a market where money and contracts agree draws a diamond
    # around its own head and no visible line, and the rows that draw a long connector
    # are exactly the rows worth reading.
    wedge = [(i, r) for i, r in markets
             if r.dollar is not None and r.dollar.index is not None]
    if compare == COMPARE_DOLLARS and wedge:
        xs, ys = [], []
        for i, r in wedge:
            xs += [r.comm, r.dollar.index, None]
            ys += [i, i, None]
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines",
            line=dict(color=hex_to_rgba(vc.BRIGHTER_TEXT_COLOR, WEDGE_ALPHA),
                      width=WEDGE_WIDTH),
            marker=dict(color=hex_to_rgba(vc.BRIGHTER_TEXT_COLOR, WEDGE_ALPHA)),
            hoverinfo="skip", showlegend=False,
        ))
        # `color`, not only `line.color`. Same trap the prior ring documents: an OPEN
        # symbol draws its outline from marker.color, and leaving it unset takes the
        # template's colourway rather than raising.
        dollar_colours = [_mark_colour(r, colors, palette) for _, r in wedge]
        fig.add_trace(go.Scatter(
            x=[r.dollar.index for _, r in wedge], y=[i for i, _ in wedge],
            mode="markers",
            marker=dict(symbol=DOLLAR_SYMBOL, size=DOLLAR_SIZE,
                        color=dollar_colours,
                        line=dict(width=1.4, color=dollar_colours)),
            hoverinfo="skip", showlegend=False,
        ))

    # One trace per speculator leg the model gates on, so the legend names them and a
    # reader can switch one off. Drawn as a tick rather than a dot: it marks a position
    # on the same axis as the bar, and a dot would read as a second measure. Lit when
    # the ROW is (see TICK_ALPHA_LIT); the per-leg gate flag stays on the hover.
    for leg in model.spec_legs:
        points = [(i, value,
                   _leg_colour(leg, r.state != const.SETUP_NONE, palette))
                  for i, r in markets
                  for lg, value, _ in r.legs if lg == leg and value is not None]
        if not points:
            continue
        colours = [c for _, _, c in points]
        # Both, for the reason the prior mark documents: a `line-*` symbol happens to
        # draw from marker.line, so leaving marker.color unset looked fine here and was
        # one symbol change away from silently becoming a template colour.
        fig.add_trace(go.Scatter(
            x=[v for _, v, _ in points], y=[i for i, _, _ in points],
            mode="markers",
            marker=dict(symbol="line-ns", size=9, color=colours,
                        line=dict(width=1.6, color=colours)),
            hoverinfo="skip",
            showlegend=False,
        ))

    # Class headers sit centred on their own row, bold and a point larger than the
    # market names under them.
    #
    # They were left-aligned out in the margin before this, on the argument that
    # headings on one left edge are scanned by running the eye down a single line. What
    # that argument missed is that the margin is already a column of names: the heading
    # sat directly above the market labels in the same left-aligned stack, differing
    # from them only in weight, so the thing separating two classes was competing with
    # the thing naming a market. Centred, it is nowhere near that column, and the row
    # it sits on carries no marks for it to land among.
    #
    # Centred on the PLOT rather than the whole figure, so the headings line up with
    # each other and with the axis under them whatever the left margin is doing.
    #
    # A per-class tally was tried here too and is still refused: the counts said what
    # the lit market names under them already say.
    for i, row in headers:
        fig.add_annotation(
            x=0.5, xref="paper", y=i, yref="y",
            text=f"<b>{row.label.upper()}</b>", showarrow=False,
            xanchor="center", yanchor="middle",
            font=dict(size=12, color=vc.BRIGHTER_TEXT_COLOR), align="center")

    fig.update_layout(
        barmode="overlay",
        height=figure_height(rows),
        margin=dict(l=LEFT_MARGIN_PX, r=20, t=TOP_CHROME_PX, b=34),
        paper_bgcolor=background,
        plot_bgcolor=background,
        font=dict(color=vc.TEXT_COLOR),
        hoverlabel=dict(font_color=vc.HOVER_TEXT_COLOR),
        # No legend: it lives in the page above the columns (see legend_items). This is
        # belt-and-braces against a future trace accidentally opting in and pushing this
        # figure's margin out of line with its neighbour's.
        showlegend=False,
        bargap=0,
    )
    fig.update_xaxes(
        range=[-2, AXIS_MAX],
        # Ticked at the gate values, not at round numbers. The bands are the reason the
        # axis is worth reading, and the printed reports draw this scale with no ticks
        # at all, which leaves a marker at "roughly 60%" unreadable as a number.
        tickvals=_ticks(model),
        ticktext=_tick_text(model),
        tickfont=dict(size=10),
        showgrid=False, zeroline=False, side="bottom",
    )
    # The scale, twice. A 50-row strip is taller than the window it is read in, so an
    # axis drawn only at the bottom is off screen for most of the reading. The bands
    # orient a reader roughly; the ticks are what let them place a bar at 80 rather than
    # "somewhere right of centre".
    #
    # After update_xaxes, not before: that call has no selector, so it reaches every x
    # axis on the figure and would put this one back at the bottom on top of the first.
    # Plotly also only draws an overlaying axis some trace references, hence the empty
    # one.
    fig.add_trace(go.Scatter(x=[None], y=[None], xaxis="x2", mode="markers",
                             hoverinfo="skip", showlegend=False))
    fig.update_layout(xaxis2=dict(
        overlaying="x", side="top", anchor="y", range=[-2, AXIS_MAX],
        tickvals=_ticks(model), ticktext=_tick_text(model),
        tickfont=dict(size=10), showgrid=False, zeroline=False))
    fig.update_yaxes(
        range=[len(rows) - 0.5, -0.5],
        tickvals=[i for i, _ in markets],
        ticktext=[_tick_label(r, colors) for _, r in markets],
        tickfont=dict(size=10),
        # Explicit, because the margin is now sized to the text. Plotly leaves about a
        # pixel between a tick label and the plot when `ticks=""`, which went unnoticed
        # while the margin carried 35px of slack and would have put the longest name
        # flush against the heading bar once that slack was reclaimed. 12 measures out
        # as a 7px gap to the plot edge.
        ticklabelstandoff=TICK_STANDOFF_PX,
        showgrid=False, zeroline=False, ticks="",
    )
    return fig
