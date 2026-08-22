"""The cross-asset crowding strip: one row per market, on one screen.

The Heatmap already carries every number this draws. What it does not do is let you
see the whole board at once, because reading a grid means reading it column by column.
This is the same verdict as a picture, sorted so the crowded ends of each asset class
collect at the top and bottom of their group.

Three choices here are deliberate departures from how the printed positioning reports
this was modelled on draw the same thing, and each one is a fix for something those
reports get wrong.

**A diverging bar from 50, not a min..max rule.** Those reports draw each market's
window range as a bar and put a marker where the current value sits. In index space
that bar is always the full axis, because the index IS the position within the range,
so the rule would carry no information at all. Worse, drawing every market's range at
the same width invites reading two ranges as comparable when one may be eight times the
other. A bar from the neutral midpoint says the one thing that survives the
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
with a spec leg blocking it draws a dim bar deep inside the bullish band. That looks
wrong until you know the rule, which is why it is written here: the bar's POSITION is
the level and its COLOUR is the verdict, and the two disagreeing is the interesting
case rather than a defect.

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

# Fill alpha for the bars.
#
# `grid_colors` picks colours for AG Grid CELL TEXT, where 11px glyphs on a near-black
# background need to be hot to be legible at all, and it deliberately swaps several
# palette reds for a brighter one for exactly that reason. A filled bar is two orders of
# magnitude more pixels of the same colour, so the value that reads as "legible" in a
# table reads as glare here. The fill is knocked back and the small text beside it keeps
# the full-strength colour, which is the same trade the Heatmap is making, sized for the
# mark it is actually applied to.
BAR_FILL_ALPHA = 0.55

# Gate state on a tick is opacity, not colour, because colour is now carrying which leg
# it is. One channel per variable.
TICK_ALPHA_GATE = 1.0
TICK_ALPHA_IDLE = 0.4

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
# Strong enough to actually see. 0.035 was faint enough to group "without reading as
# shading", and on a real monitor over the near-black background it turned out not to
# read at all, so the marks it was meant to tie together floated free. 0.06 is about
# the faintest value that survives the screen. The gate bands stay above it in weight:
# they are a shade stronger AND saturated, so zones still outrank row bands.
ROW_BAND_ALPHA = 0.06

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
LEFT_MARGIN_PX = 140

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

# How the Commercial index is drawn.
#
# A bar from the neutral midpoint encodes the value twice: its right end is the value,
# and its length is the distance from neutral. That second reading is free to a reader
# and costs a row's worth of saturated colour, which is why the fills had to be knocked
# back at all. A mark encodes position only, which is the whole of what a bounded 0-100
# index says, and it leaves the row empty.
#
# The mark is the better default here for two reasons beyond the ink. The decision this
# page supports is "which side of the band", which is a position question rather than a
# magnitude one. And the verdict no longer needs area to be scannable, because the market
# name carries it as well now.
MARK_BAR = "bar"
MARK_DOT = "dot"


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


def build_rows(df, model, sort_by_index=True, show=SHOW_ALL, side=SIDE_BOTH):
    """`(rows, skipped)` for one Signal Matrix frame.

    Markets with no index at the selected week cannot be placed on the axis, so they
    are dropped and counted. The count is returned rather than swallowed: a strip that
    silently showed 44 of 47 markets would read as a complete board.

    Filtered-out markets are a different thing and are NOT counted here. The caller
    knows the filter it asked for, and a class left empty by one loses its header rather
    than sitting there as a heading over nothing.
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
                          else min(100.0, max(0.0, comm - move)))
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


def _bar_colour(row, colors):
    """Verdict colour for a market's bar. See the module docstring on why it is the
    row's state and not the bar's own value that decides."""
    if row.state in (const.SETUP_BULL,):
        return colors.bull
    if row.state in (const.SETUP_BEAR,):
        return colors.bear
    if row.state == const.SETUP_NEAR_BULL:
        return colors.bull_near
    if row.state == const.SETUP_NEAR_BEAR:
        return colors.bear_near
    return colors.dim


def _mark_colour(row, colors, palette):
    """Colour for a market's current mark.

    A row with a verdict takes the verdict colour. A row without one takes the app's
    COMMERCIAL colour rather than a neutral grey: the mark is Commercial positioning
    whatever the gate thinks of it, and grey said only "nothing here" while leaving the
    one series on the row unnamed by colour, which is the thing every other panel names
    by colour.
    """
    if row.state == const.SETUP_NONE:
        return palette[LEG_PALETTE_SLOT["comm"]]
    return _bar_colour(row, colors)


def _fill(colour, alpha=BAR_FILL_ALPHA):
    """A bar fill from a verdict colour.

    Only full-strength colours are knocked back. The near-setup colours arrive already
    translucent from `grid_colors`, and the neutral dim is fainter still, so fading
    those again would push a whole tier of the ramp out of sight.
    """
    return hex_to_rgba(colour, alpha) if str(colour).startswith("#") else colour


def _leg_colour(leg, gate, palette):
    """A tick's colour: the app's colour for that leg, faded unless it is gating.

    A glyph per leg was the alternative, and the row height is the argument against it.
    At 21px a tick's whole job is to say WHERE on the axis the leg sits, and a diamond
    or a star is several units wide at that scale, so the shape that carries identity
    would blur the position that carries the measurement. Colour is free here, and it is
    the convention every other panel already uses.
    """
    alpha = TICK_ALPHA_GATE if gate else TICK_ALPHA_IDLE
    return hex_to_rgba(palette[LEG_PALETTE_SLOT[leg]], alpha)


def _tick_label(row, colors):
    """The market name, lit when its row has a verdict.

    The name column is where the eye starts, and the bar that carries the verdict is
    off to the right of it, so a reader scanning names alone had no way to find the
    setups without tracking across. This is the same variable the bar colour carries,
    which is usually a reason not to draw it twice; the exception is that the two live
    at opposite ends of a wide row.
    """
    if row.state == const.SETUP_NONE:
        return row.label
    return f'<span style="color:{_bar_colour(row, colors)}">{row.label}</span>'


def _hover(row, model):
    legs = "".join(
        f"<br>{LEG_LABELS[leg]}: {value:.0f}"
        f"{' (through its gate)' if gate else ''}"
        for leg, value, gate in row.legs if value is not None)
    verdict = STATE_LABELS.get(row.state)
    tail = f"<br><br>{model.title}: {verdict}" if verdict else f"<br><br>{model.title}: no setup"
    equity = "<br>Equity index: gated on Commercials alone" if row.is_equity else ""
    return (f"<b>{row.label}</b><br>{row.asset_class}"
            f"<br>{LEG_LABELS['comm']}: {row.comm:.0f}{legs}{tail}{equity}")


def _ticks(model):
    """Ticked at the gate values, not at round numbers, because the bands are the
    reason the axis is worth reading at all."""
    return [0, model.low, const.INDEX_NEUTRAL, model.high, 100]


def _tick_text(model):
    return [str(v) for v in _ticks(model)]


# The glyph kinds legend_items hands back. The page renders them as text, so each kind
# is a character there, but the KINDS are named here because which marks exist is this
# module's fact: they mirror the symbols build_figure actually draws.
GLYPH_MARK = "mark"        # the diamond, or the bar swatch in bar mode
GLYPH_TICK = "tick"        # the line-ns symbol: quiet rows and speculator legs
GLYPH_CIRCLE = "circle"    # the hollow prior-position circle


def legend_items(model, colors, palette, mark=MARK_DOT):
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
    be inferred. The bar's own colour stays out of the key because it varies per row;
    the group title names it instead.
    """
    comm = palette[LEG_PALETTE_SLOT["comm"]]
    commercial = [("Bull setup", colors.bull, GLYPH_MARK),
                  ("Bear setup", colors.bear, GLYPH_MARK),
                  ("Near", colors.bull_near, GLYPH_MARK)]
    if mark != MARK_BAR:
        commercial.append(("No setup", comm, GLYPH_TICK))
    commercial.append((f"{const.MOMENTUM_PERIOD}w ago", comm, GLYPH_CIRCLE))
    return [
        (f"{'Bar' if mark == MARK_BAR else 'Diamond'}: Commercial index", commercial),
        ("Ticks: the legs this gate also reads",
         [(LEG_LABELS[leg], palette[LEG_PALETTE_SLOT[leg]], GLYPH_TICK)
          for leg in model.spec_legs if leg in LEG_LABELS]),
    ]


def build_figure(rows, model, colors, palette, background=vc.BACKGROUND_COLOR,
                 mark=MARK_DOT):
    """The strip, as one figure.

    `rows` comes from build_rows. Nothing here reads a store, so a caller can hand it
    hand-written rows.
    """
    fig = go.Figure()

    markets = [(i, r) for i, r in enumerate(rows) if r.kind == "market"]
    headers = [(i, r) for i, r in enumerate(rows) if r.kind == "class"]

    # Bands first, so every mark lands on top of them. Only the two extremes are
    # painted: the middle is not a band, it is the absence of one.
    # 0.09 keeps the zones a step above ROW_BAND_ALPHA, so the strongest shading on
    # the page is still the one that means something.
    shapes = [
        dict(type="rect", xref="x", yref="paper", x0=0, x1=model.low, y0=0, y1=1,
             fillcolor=colors.bear, opacity=0.09, layer="below", line_width=0),
        dict(type="rect", xref="x", yref="paper", x0=model.high, x1=100, y0=0, y1=1,
             fillcolor=colors.bull, opacity=0.09, layer="below", line_width=0),
        dict(type="line", xref="x", yref="paper", x0=const.INDEX_NEUTRAL,
             x1=const.INDEX_NEUTRAL, y0=0, y1=1, layer="below",
             line=dict(color=vc.GRID_COLOR, width=1)),
    ]
    # A band on every other market row.
    #
    # A row carries four marks now (Commercials, its prior position, and a tick per
    # speculator leg) on ROW_PX pixels of height, and nothing tied them to each other
    # or separated them from the row above. The printed reference solves the same problem by
    # drawing each asset inside its own rectangle. Here the rectangle would be the whole
    # axis on every row, because the index is 0-100 by construction, so it would be
    # identical everywhere and carry nothing; alternating it is the same grouping for
    # half the ink.
    #
    # The phase resets at each class header, so the first market under a heading always
    # looks the same rather than depending on how many markets the class above had.
    band_ys, ordinal = [], 0
    for i, row in enumerate(rows):
        if row.kind == "class":
            ordinal = 0
        elif row.kind == "market":
            if ordinal % 2:
                band_ys.append(i)
            ordinal += 1
    shapes += [
        dict(type="rect", xref="paper", yref="y", x0=0, x1=1,
             y0=i - 0.5, y1=i + 0.5, layer="below",
             fillcolor=vc.BRIGHTER_TEXT_COLOR, opacity=ROW_BAND_ALPHA, line_width=0)
        for i in band_ys
    ]

    # The rule goes through the middle of each spacer row, so the gap reads as a gap
    # with a line in it rather than as a line with rows crowding it.
    shapes += [
        dict(type="line", xref="paper", yref="y", x0=0, x1=1, y0=i, y1=i, layer="below",
             line=dict(color=vc.GRID_COLOR, width=1))
        for i, r in enumerate(rows) if r.kind == "spacer"
    ]
    fig.update_layout(shapes=shapes)

    if markets and mark == MARK_BAR:
        vals = [r.comm for _, r in markets]
        fig.add_trace(go.Bar(
            x=[v - const.INDEX_NEUTRAL for v in vals],
            base=[const.INDEX_NEUTRAL] * len(vals),
            y=[i for i, _ in markets],
            orientation="h",
            width=0.46,
            marker=dict(color=[_fill(_bar_colour(r, colors)) for _, r in markets],
                        line_width=0),
            hovertext=[_hover(r, model) for _, r in markets],
            hoverinfo="text",
            showlegend=False,
        ))
    elif markets:
        # Two shapes, and the shape is the verdict rather than a second colour.
        #
        # A diamond means the model has something to say about this row; a tick means it
        # does not, and a tick is the same mark the speculator legs use, so a quiet row
        # reads as three marks of one family rather than as a special case. Colour then
        # only ever says WHOSE positioning a mark is, or, where there is a verdict, what
        # it is. Full strength for both: a 9px mark is a fraction of the pixels a filled
        # bar was, so the colour that glared as a row reads as a cue here.
        for state_group, symbol, size in (
                ("verdict", "diamond", 9), ("quiet", "line-ns", 11)):
            group = [(i, r) for i, r in markets
                     if (r.state != const.SETUP_NONE) == (state_group == "verdict")]
            if not group:
                continue
            colours = [_mark_colour(r, colors, palette) for _, r in group]
            fig.add_trace(go.Scatter(
                x=[r.comm for _, r in group],
                y=[i for i, _ in group],
                mode="markers",
                marker=dict(symbol=symbol, size=size, color=colours,
                            line=dict(width=2, color=colours)),
                hovertext=[_hover(r, model) for _, r in group],
                hoverinfo="text",
                showlegend=False,
            ))

    # Where it stood MOMENTUM_PERIOD weeks ago, as a hollow mark on the same row.
    #
    # No connector to the current mark. The reference charts that do this well draw the
    # two positions and let the row pair them, and 42 connectors is a lot of line for a
    # move that is usually a few points wide.
    prior = [(i, r.prior) for i, r in markets if r.prior is not None]
    if prior:
        # `color`, not just `line.color`. An OPEN symbol draws its outline from
        # marker.color; marker.line is a second stroke around that. Setting only the
        # line left marker.color unset, so Plotly fell back to the template colorway
        # and drew these in its third default colour, a teal green, while the legend
        # key beside them was the red this actually sets. Nothing errors when a colour
        # is omitted, it just quietly becomes the theme's.
        faint_comm = hex_to_rgba(palette[LEG_PALETTE_SLOT["comm"]], 0.45)
        fig.add_trace(go.Scatter(
            x=[v for _, v in prior], y=[i for i, _ in prior],
            mode="markers",
            marker=dict(symbol="circle-open", size=6, color=faint_comm,
                        line=dict(width=1.2, color=faint_comm)),
            hoverinfo="skip", showlegend=False,
        ))

    # One trace per speculator leg the model gates on, so the legend names them and a
    # reader can switch one off. Drawn as a tick rather than a dot: it marks a position
    # on the same axis as the bar, and a dot would read as a second measure.
    for leg in model.spec_legs:
        points = [(i, value, _leg_colour(leg, gate, palette))
                  for i, r in markets
                  for lg, value, gate in r.legs if lg == leg and value is not None]
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

    # Class headers sit out in the left margin, level with the break, bold and a point
    # larger than the market names under them.
    #
    # Left-aligned rather than centred over the bars, deliberately. Headings on one left
    # edge are scanned by running the eye down a single line; centred ones move with the
    # length of each word, and over the plot area they would sit among the marks they
    # are labelling.
    #
    # Nothing behind them and nothing beside them. A shaded band and a per-class tally
    # were both tried: the band read as noise across every group, and the counts said
    # what the lit market names under them already say. The blank row above is the
    # separation, and the weight of the text is the emphasis.
    for i, row in headers:
        fig.add_annotation(
            x=0, xref="paper", y=i, yref="y", xshift=-(LEFT_MARGIN_PX - 4),
            text=f"<b>{row.label.upper()}</b>", showarrow=False,
            xanchor="left", yanchor="middle",
            font=dict(size=12, color=vc.BRIGHTER_TEXT_COLOR), align="left")

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
        showgrid=False, zeroline=False, ticks="",
    )
    return fig
