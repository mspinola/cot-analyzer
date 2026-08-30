"""The crowdedness board: every market against four windows, on one screen.

The Strip answers "where does each market sit in ONE window, and what does the model
say about it". This board answers a different question: how crowded is the same leg
against its trailing 3-month, 6-month, 12-month and full-history range, side by side.
The cross-window PATTERN on a row is the signal this page exists for, and it only
exists visually if the four readings sit in one eye-span. The printed reports this
replaces draw one panel per window, so a market's four readings are never on screen
together and the pattern has to be reconstructed from memory.

Three named patterns, worth listing because the caption teaches them:

- Persistent extreme: hot in all four windows. Crowded by any yardstick.
- Fresh push: hot at 3 months, fading as the window lengthens. Recent positioning
  build with room by historical standards.
- Unwinding: mild at 3 months, hot at 12 months and history. An old extreme that has
  stopped extending.

**Colour is the VALUE here, not the verdict, and that is a deliberate departure from
the rule the Strip and the Heatmap share.** Their rule (colour follows the row's setup
state) exists because a single positioning index only means something in the company
of the other legs the gate reads. This board is not drawing the gate's question: all
four cells are the same leg, and the object of interest is the multi-window shape,
which dies if three of four cells are washed to neutral because the model's one
window has no verdict. The bridge back to the app's vocabulary is the verdict CHIP
at the row's left edge: the same two words the Active Setups strip uses (SETUP,
NEAR), in the verdict's own hue, with the tier carried by weight alone. A full setup
is a quiet wash with full-strength text; a near setup is the same chip two steps
fainter, so the ordering reads without a legend. Weight is the only difference on
purpose: two tiers distinguished by anything louder would out-shout the cells the
page is about. The two encodings can disagree on one row, and that is the
interesting case: a market crowded on every window with no chip is a market whose
OTHER legs are blocking the gate.

The poles reuse the app's bull/bear palette slots rather than a new pair, because the
axis is the same one every other page draws: high index = Commercials accumulated =
bullish extreme, low = distributed = bearish. A neutral cell fades toward the
background so the crowded ends carry the ink, which is the board's whole reading
strategy: sweep for saturated cells, then read the row.

Everything here is a pure function over `MarketRead` values plus a colour set, so the
layout is testable without a store, a palette file or a browser.
"""

from dataclasses import dataclass

import cotmetrics.constants as const
import plotly.graph_objects as go

import viz_constants as vc
from components.plot_colors import hex_to_rgba, relative_luminance

# The chip says the same two words the Active Setups strip says, imported rather
# than restated so the app keeps one vocabulary for a verdict's tiers.
from components.strip_traces import STATE_LABELS

# The four windows, in weeks. None means the full history the store holds for that
# market, which differs per market (stitched CFTC codes included), so the actual
# week count rides on the row and the hover says it.
WINDOW_WEEKS = (13, 26, 52, None)
WINDOW_LABELS = ("3M", "6M", "12M", "Full")
# Prose for hovers and the caption, index-aligned with WINDOW_WEEKS.
WINDOW_DESC = ("13-week window", "26-week window", "52-week window", "full history")

# How the rows are ordered. Values are session-persisted control state, so they are a
# wire format: renaming one silently resets a returning reader's choice.
ORDER_CLASS = "class"
ORDER_FLAT = "flat"
ORDER_ALPHA = "alpha"

# Row geometry, matching the Strip's so the two boards read at the same density.
ROW_PX = 22
HEADER_BAND_ALPHA = 0.07
ROW_RULE_ALPHA = 0.10
TOP_CHROME_PX = 34
BOTTOM_CHROME_PX = 24
# Nearly nothing: the label column lives INSIDE the axis as text traces (see the
# label block in build_figure), not in the tick margin the Strip uses.
LEFT_MARGIN_PX = 12

# ── the x layout, in cell units ───────────────────────────────────────────────
# One abstract axis: the label columns, four cell slots, a change column, then the
# sparkline lane. All fixed numbers live here so the header ticks, the shapes and
# the traces cannot disagree about where a column is.
#
# The labels are drawn in-plot rather than as y tick labels, which is a departure
# from the Strip worth a sentence: a tick label is ONE run of text in one font, and
# this row's identity is three things with three weights (the symbol you scan for,
# the name you confirm with, the inception tag you only need when reading the Full
# column). Tick labels also cap the class headings at the same 10px as every market
# row, which made the group structure invisible at arm's length.
SYM_X = -4.55             # symbol column, left-anchored
NAME_X = -3.80            # name column, left-anchored; the inception tag rides
                          # INSIDE this trace as a styled span, so it hugs each
                          # name instead of sitting in a fixed column of its own
CELL_XS = (0.0, 1.0, 2.0, 3.0)
CELL_HALF = 0.46          # half-width of a cell; 0.5 would butt neighbours together
CELL_HALF_ROW = 0.38      # half-height in row units; the gap is the lane separator
DELTA_TRI_X = 4.35        # the direction triangle
DELTA_TEXT_X = 4.75       # the signed number
SPARK_X0, SPARK_X1 = 5.35, 8.35
SPARK_AMPLITUDE = 0.36    # half-height of the path, in row units
X_RANGE = (-4.75, 8.55)
# The verdict chip, in the gap between the name column and the first cell. Wide
# enough for "SETUP" at CHIP_TEXT_SIZE with air on both sides; shorter than a cell
# so the cells stay the biggest objects on the row.
CHIP_X0, CHIP_X1 = -1.46, -0.58
CHIP_HALF_ROW = 0.29
CHIP_TEXT_SIZE = 8
# The two tiers, by weight alone: same hue, same words, different alphas. The full
# tier's wash matches the app's INDEX_WASH register (~19%); the near tier sits at a
# fraction of it, the same faint-but-never-invisible reasoning as the Strip's
# near-tier INDEX_RAMP_ALPHA_APPROACH.
CHIP_FILL_ALPHA = 0.18
CHIP_LINE_ALPHA = 0.50
CHIP_NEAR_FILL_ALPHA = 0.06
CHIP_NEAR_LINE_ALPHA = 0.22

# The three label weights. The symbol is the thing a reader sweeps for, so it is the
# bright bold one; the name confirms it and sits a step back; the inception tag is
# reference material for the Full column and sits two steps back and smaller.
SYM_FONT = dict(size=10, family="Menlo, Consolas, monospace")
NAME_SIZE = 10
SINCE_SIZE = 9
SINCE_ALPHA = 0.45
CLASS_SIZE = 12

# Ticks over the columns. The spark gets one centred label rather than an axis of its
# own; its y scale is the same 0-100 the cells carry and the hover on the endpoint
# says the number.
HEADER_TICK_XS = CELL_XS + (DELTA_TEXT_X - 0.2, (SPARK_X0 + SPARK_X1) / 2)

# A change smaller than this many index points draws a flat dash, not a direction.
DELTA_FLAT = 1.0

# How hard a cell at the pole leans into the pole colour. 1.0 would paint the full
# verdict hue, which grid_colors picks hot enough for text ON the background; a slab
# of it per cell reads as glare, the same observation that set the Strip's STEM_ALPHA.
# 0.66 rather than the 0.82 it started at: at 0.82 a board with a crowded class was
# a wall of near-verdict colour and the numbers fought their own fills. Two thirds
# of the pole over the dark ground is the muted register the layout mockup used, it
# keeps every cell under the ink's luminance threshold so the numbers stay one
# bright colour throughout, and the monotonic ramp still separates 80 from 100.
CELL_MAX_BLEND = 0.66
# Corner rounding, in axis units (x and y are different units, so two radii). ~3px
# at the board's usual rendered size; a shape, not a style, because Plotly rects
# have no corner radius and these cells are drawn as path shapes for exactly this.
CELL_RX = 0.045
CELL_RY = 0.10
# Inside this distance of neutral a cell keeps the resting fill: a 47-row board where
# every 53 carries a wash has no quiet majority left to make the extremes loud.
CELL_DEADBAND = 6.0
# The resting fill for a neutral cell: the background lifted just enough to read as a
# cell rather than as a hole in the row.
CELL_BASE_LIFT = 0.05

SPARK_LINE = "rgba(255, 255, 255, 0.30)"
SPARK_MIDLINE_ALPHA = 0.10
SPARK_END_SIZE = 5

TEXT_SIZE = 10


@dataclass(frozen=True)
class MarketRead:
    """One market's four-window reading, computed by the page's data layer.

    `windows` is index-aligned with WINDOW_WEEKS; a None entry is a window the
    market's history cannot fill yet. `history_weeks` is how many weekly reports the
    full-history window actually spans, and `start` is the first report date, both
    hover material. `path` is the trailing year of the 52-week index, oldest first,
    for the sparkline. `move` is the MOMENTUM_PERIOD-week change of the 52-week
    index, the same quantity the Heatmap's change column carries.
    """
    asset: str
    asset_class: str
    windows: tuple
    symbol: str = ""
    history_weeks: int = None
    start: str = None
    move: float = None
    path: tuple = ()
    state: str = const.SETUP_NONE
    is_equity: bool = False
    date: str = None


@dataclass(frozen=True)
class BoardRow:
    """One line of the board: an asset-class header, a market, or a blank spacer."""
    kind: str                 # "class", "market" or "spacer"
    label: str
    asset_class: str
    read: MarketRead = None


def crowding_score(read):
    """The mean of the windows the market can fill, for ordering.

    The mean rather than any single window, because the board's claim is the
    cross-window picture: a market at 95 on one window and 50 on three should not
    outrank one at 80 on all four. Windows the history cannot fill simply do not
    vote. None when no window has a value, and the caller drops that market with a
    count rather than drawing an empty row.
    """
    values = [v for v in read.windows if v is not None]
    if not values:
        return None
    return sum(values) / len(values)


def build_rows(reads, order=ORDER_CLASS):
    """`(rows, skipped)` for one week's list of MarketReads.

    Markets with no value in any window cannot be placed and are dropped and counted,
    for the Strip's reason: a board silently showing 44 of 47 markets reads as a
    complete one.

    ORDER_FLAT drops the class grouping entirely and sorts the whole board by
    crowding score, so the page becomes one gradient from crowded-long at the top to
    crowded-short at the bottom. The other two orders keep the class blocks.
    """
    scored, skipped = [], []
    for read in reads:
        score = crowding_score(read)
        if score is None:
            skipped.append(read.asset)
        else:
            scored.append((score, read))

    if order == ORDER_FLAT:
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [BoardRow(kind="market", label=read.asset,
                         asset_class=read.asset_class, read=read)
                for _, read in scored], skipped

    by_class = {}
    for score, read in scored:
        by_class.setdefault(read.asset_class, []).append((score, read))

    rows = []
    # Insertion order, not alphabetical: the reads arrive in the Signal Matrix's
    # class order, which is the order every other page presents the book in.
    for asset_class, markets in by_class.items():
        if order == ORDER_ALPHA:
            markets.sort(key=lambda pair: pair[1].asset)
        else:
            markets.sort(key=lambda pair: pair[0], reverse=True)
        if rows:
            rows.append(BoardRow(kind="spacer", label="", asset_class=asset_class))
        rows.append(BoardRow(kind="class", label=asset_class,
                             asset_class=asset_class))
        rows.extend(BoardRow(kind="market", label=read.asset,
                             asset_class=asset_class, read=read)
                    for _, read in markets)
    return rows, skipped


def figure_height(rows):
    return TOP_CHROME_PX + BOTTOM_CHROME_PX + ROW_PX * max(1, len(rows))


# ── colour ────────────────────────────────────────────────────────────────────

def _blend_over(hex_color, alpha, background):
    """`hex_color` composited over `background` at `alpha`, as a hex string.

    The board needs the RESULTING colour, not an rgba string, because the cell text
    picks its own colour by the fill's luminance, and luminance of an rgba value
    depends on what it lands on.
    """
    h = str(hex_color).lstrip("#")
    b = str(background).lstrip("#")
    if len(h) != 6 or len(b) != 6:
        return hex_color
    try:
        fg = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
        bg = [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    except ValueError:
        return hex_color
    return "#{:02x}{:02x}{:02x}".format(
        *(round(bg[i] + (fg[i] - bg[i]) * alpha) for i in range(3)))


def cell_base(background=vc.BACKGROUND_COLOR):
    """The resting fill of a neutral cell."""
    return _blend_over(vc.BRIGHTER_TEXT_COLOR, CELL_BASE_LIFT, background)


def cell_fill(value, colors, background=vc.BACKGROUND_COLOR):
    """The fill for one cell: its pole colour, blended toward the background by how
    far the value sits from neutral.

    Linear in distance from neutral past the deadband, capped at CELL_MAX_BLEND. The
    monotonicity (further from neutral is never fainter) is what makes the sweep
    honest, and the test suite pins it.
    """
    if value is None:
        return None
    deviation = value - const.INDEX_NEUTRAL
    magnitude = abs(deviation)
    if magnitude <= CELL_DEADBAND:
        return cell_base(background)
    pole = colors.bull if deviation > 0 else colors.bear
    span = (const.INDEX_NEUTRAL - CELL_DEADBAND)
    alpha = min(1.0, (magnitude - CELL_DEADBAND) / span) * CELL_MAX_BLEND
    return _blend_over(pole, alpha, background)


def cell_text_colour(fill):
    """Ink for the number printed on `fill`: the app's bright text on a dark cell,
    near-black on a light one. The threshold is luminance, not blend strength,
    because palettes disagree about how bright their bull and bear slots are."""
    if relative_luminance(fill) > 0.35:
        return "#101418"
    return vc.BRIGHTER_TEXT_COLOR


def delta_colour(move, colors):
    """The direction triangle's colour: bull hue rising, bear hue falling, dim flat."""
    if move is None or abs(move) <= DELTA_FLAT:
        return colors.dim
    return colors.bull if move > 0 else colors.bear


def verdict_chip(state, colors):
    """(label, fill, border, ink) for the verdict chip, or None with no verdict.

    Both tiers draw, and WEIGHT is the only thing separating them: same hue, same
    words, a full setup at the app's wash register with full-strength ink, a near
    setup a fraction of it with the near-tier ink the Strip already uses. Anything
    louder than an alpha step between the tiers would out-shout the cells.
    """
    if state in (const.SETUP_BULL, const.SETUP_NEAR_BULL):
        pole, near_ink = colors.bull, colors.bull_near
    elif state in (const.SETUP_BEAR, const.SETUP_NEAR_BEAR):
        pole, near_ink = colors.bear, colors.bear_near
    else:
        return None
    if state in const.SETUP_FULL_STATES:
        return (STATE_LABELS[state], hex_to_rgba(pole, CHIP_FILL_ALPHA),
                hex_to_rgba(pole, CHIP_LINE_ALPHA), pole)
    return (STATE_LABELS[state], hex_to_rgba(pole, CHIP_NEAR_FILL_ALPHA),
            hex_to_rgba(pole, CHIP_NEAR_LINE_ALPHA), near_ink)


def chip_hover(read, model):
    side = ("bullish" if read.state in (const.SETUP_BULL, const.SETUP_NEAR_BULL)
            else "bearish")
    tier = "setup" if read.state in const.SETUP_FULL_STATES else "near setup"
    return f"<b>{read.asset}</b> · {model.title}: {side} {tier} on its own window"


# ── hovers ────────────────────────────────────────────────────────────────────

def _fmt(value):
    return "n/a" if value is None else f"{value:.0f}"


def cell_hover(read, window_index):
    weeks = WINDOW_WEEKS[window_index]
    value = read.windows[window_index]
    if weeks is None:
        weeks_note = (f"{read.history_weeks} weekly reports since {read.start}"
                      if read.history_weeks else "full history")
        window = f"Full history ({weeks_note})"
    else:
        window = f"{WINDOW_DESC[window_index]}"
    return (f"<b>{read.asset}</b> · {window}<br>"
            f"Commercial index {_fmt(value)}"
            f"<br><i>0 = window low · 100 = window high</i>")


def delta_hover(read):
    if read.move is None:
        return f"<b>{read.asset}</b> · {vc.MOMENTUM_LABEL}: n/a"
    return (f"<b>{read.asset}</b> · {vc.MOMENTUM_LABEL}: {read.move:+.0f}<br>"
            f"<i>{vc.MOMENTUM_UNIT_PHRASE}</i>")


def since_tag(read):
    """The inception tag beside the name: a two-digit year the mockup style of
    printed reports uses, or nothing when the start is unknown."""
    if not read.start or len(read.start) < 4:
        return ""
    return f"'{read.start[2:4]}"


def name_label(read):
    """The name column's text: the market name with the inception tag riding
    inside it as a styled span, so the tag hugs the name whatever its width.

    A separate fixed column was tried first and read as belonging to the CELLS
    (right-aligned against them), when the tag is a fact about the market. Plotly's
    text engine renders `<span style='fill:...;font-size:...'>` as a styled tspan,
    which is what lets one trace carry two weights."""
    tag = since_tag(read)
    if not tag:
        return read.asset
    ink = hex_to_rgba(vc.BRIGHTER_TEXT_COLOR, SINCE_ALPHA)
    return (f"{read.asset} <span style='fill:{ink};"
            f"font-size:{SINCE_SIZE}px'>{tag}</span>")


def spark_hover(read):
    latest = read.path[-1] if read.path else None
    return (f"<b>{read.asset}</b> · 52-week index over the trailing year<br>"
            f"latest {_fmt(latest)}")


# ── the figure ────────────────────────────────────────────────────────────────

def _spark_points(read, row_y):
    """(xs, ys) for one market's path, mapped into the sparkline lane.

    The y axis is reversed (row 0 at the top), so a HIGH index must map to a SMALLER
    y. Values are clamped to the lane rather than trusted: the path is a 0-100 index
    by construction, so a point outside it is a data error this should not amplify.
    """
    values = [v for v in read.path if v is not None]
    if len(values) < 2:
        return [], []
    n = len(values)
    xs = [SPARK_X0 + (SPARK_X1 - SPARK_X0) * i / (n - 1) for i in range(n)]
    ys = []
    for v in values:
        offset = (min(100.0, max(0.0, v)) - const.INDEX_NEUTRAL) / 50.0
        ys.append(row_y - offset * SPARK_AMPLITUDE)
    return xs, ys


def _rounded_rect(x0, x1, y0, y1, rx=CELL_RX, ry=CELL_RY):
    """An SVG path for a rectangle with quadratic corners, in data coordinates.

    Two radii because the axes are two different units; the caller's constants keep
    the rendered corner roughly square. Direction-agnostic over the reversed y axis,
    since the path visits the same four corners either way round."""
    return (f"M{x0 + rx},{y0} L{x1 - rx},{y0} Q{x1},{y0} {x1},{y0 + ry} "
            f"L{x1},{y1 - ry} Q{x1},{y1} {x1 - rx},{y1} "
            f"L{x0 + rx},{y1} Q{x0},{y1} {x0},{y1 - ry} "
            f"L{x0},{y0 + ry} Q{x0},{y0} {x0 + rx},{y0} Z")


def build_figure(rows, model, colors, background=vc.BACKGROUND_COLOR):
    """The board, as one figure. Pure over `rows`, exactly as the Strip's is."""
    fig = go.Figure()
    markets = [(i, r.read) for i, r in enumerate(rows) if r.kind == "market"]
    headers = [i for i, r in enumerate(rows) if r.kind == "class"]

    shapes = []

    # The cells. Painted as shapes rather than a heatmap trace so the per-cell fill
    # and the per-cell text colour come from ONE function, `cell_fill`, instead of a
    # colorscale that would have to replicate it. Path shapes rather than rects for
    # the corners: Plotly rects have no radius, and the rounding is doing real work
    # at this density, separating forty rows of adjacent slabs into forty pills.
    for i, read in markets:
        for w, x in enumerate(CELL_XS):
            fill = cell_fill(read.windows[w], colors, background)
            if fill is None:
                continue
            shapes.append(dict(
                type="path", xref="x", yref="y",
                path=_rounded_rect(x - CELL_HALF, x + CELL_HALF,
                                   i - CELL_HALF_ROW, i + CELL_HALF_ROW),
                fillcolor=fill, line_width=0, layer="below"))

    # The verdict chips' bodies. Shapes here beside the cells they answer to; the
    # words ride in the trace block below, where text lives.
    for i, read in markets:
        chip = verdict_chip(read.state, colors)
        if chip is None:
            continue
        shapes.append(dict(
            type="path", xref="x", yref="y",
            path=_rounded_rect(CHIP_X0, CHIP_X1,
                               i - CHIP_HALF_ROW, i + CHIP_HALF_ROW,
                               rx=0.07, ry=0.12),
            fillcolor=chip[1], line=dict(color=chip[2], width=1), layer="below"))

    # The heading bar, the Strip's treatment for the Strip's reason.
    shapes += [
        dict(type="rect", xref="paper", yref="y", x0=0, x1=1,
             y0=i - 0.5, y1=i + 0.5, layer="below",
             fillcolor=vc.BRIGHTER_TEXT_COLOR, opacity=HEADER_BAND_ALPHA,
             line_width=0)
        for i in headers
    ]

    # A midline through each sparkline lane: the 50 mark the path wiggles around.
    # Per market row rather than one long rule, so spacers and headers stay blank.
    shapes += [
        dict(type="line", xref="x", yref="y", x0=SPARK_X0, x1=SPARK_X1,
             y0=i, y1=i, layer="below",
             line=dict(color=hex_to_rgba(vc.BRIGHTER_TEXT_COLOR,
                                         SPARK_MIDLINE_ALPHA), width=1))
        for i, _ in markets
    ]
    fig.update_layout(shapes=shapes)

    # The label columns, in-plot (see the x-layout note above). The symbol and the
    # name are separate traces because a text trace carries one font; the inception
    # tag rides inside the name via `name_label`'s styled span. The class heading
    # gets its own trace at a size a tick label could never have: the group
    # structure is the first thing a reader orients by.
    if markets:
        ys = [i for i, _ in markets]
        fig.add_trace(go.Scatter(
            x=[SYM_X] * len(markets), y=ys, mode="text",
            text=[f"<b>{r.symbol}</b>" if r.symbol else "" for _, r in markets],
            textposition="middle right",
            textfont={**SYM_FONT, "color": vc.BRIGHTER_TEXT_COLOR},
            hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(
            x=[NAME_X] * len(markets), y=ys, mode="text",
            text=[name_label(r) for _, r in markets],
            textposition="middle right",
            textfont=dict(size=NAME_SIZE, color=vc.TEXT_COLOR),
            hoverinfo="skip", showlegend=False))
    if headers:
        fig.add_trace(go.Scatter(
            x=[SYM_X] * len(headers), y=headers, mode="text",
            text=[f"<b>{rows[i].label.upper()}</b>" for i in headers],
            textposition="middle right",
            textfont=dict(size=CLASS_SIZE, color=vc.BRIGHTER_TEXT_COLOR),
            hoverinfo="skip", showlegend=False))

    if markets:
        # The numbers on the cells. Split into two traces by the ink `cell_text_colour`
        # picked, because a scatter trace carries one text colour: per-point textfont
        # arrays are not portable across the plotly versions this app has shipped on.
        buckets = {}
        for i, read in markets:
            for w, x in enumerate(CELL_XS):
                value = read.windows[w]
                if value is None:
                    continue
                fill = cell_fill(value, colors, background)
                ink = cell_text_colour(fill)
                buckets.setdefault(ink, []).append(
                    (x, i, f"{value:.0f}", cell_hover(read, w), read.asset))
        # `customdata` on every hoverable trace here and below: the market's
        # name rides on the point so a click can open its detail page without
        # the server re-deriving row order from a figure it no longer holds.
        for ink, points in buckets.items():
            fig.add_trace(go.Scatter(
                x=[p[0] for p in points], y=[p[1] for p in points],
                mode="text", text=[p[2] for p in points],
                textfont=dict(size=TEXT_SIZE, color=ink),
                hovertext=[p[3] for p in points], hoverinfo="text",
                customdata=[p[4] for p in points],
                showlegend=False))

        # The change column: a direction triangle and the signed number. The triangle
        # carries the colour (marker.color takes an array), the number stays in the
        # app's text colour, which is the dataviz rule about text wearing text tokens.
        fig.add_trace(go.Scatter(
            x=[DELTA_TRI_X] * len(markets), y=[i for i, _ in markets],
            mode="markers",
            marker=dict(
                symbol=["triangle-up" if (r.move or 0) > DELTA_FLAT
                        else "triangle-down" if (r.move or 0) < -DELTA_FLAT
                        else "line-ew" for _, r in markets],
                size=7,
                color=[delta_colour(r.move, colors) for _, r in markets],
                line=dict(width=1,
                          color=[delta_colour(r.move, colors) for _, r in markets])),
            hovertext=[delta_hover(r) for _, r in markets], hoverinfo="text",
            customdata=[r.asset for _, r in markets],
            showlegend=False))
        fig.add_trace(go.Scatter(
            x=[DELTA_TEXT_X] * len(markets), y=[i for i, _ in markets],
            mode="text",
            text=["" if r.move is None else f"{r.move:+.0f}" for _, r in markets],
            textfont=dict(size=TEXT_SIZE, color=vc.TEXT_COLOR),
            hoverinfo="skip", showlegend=False))

        # The chips' words, bucketed by ink the way the cell numbers are: one trace
        # per colour, because a text trace carries one font.
        chip_buckets = {}
        for i, r in markets:
            chip = verdict_chip(r.state, colors)
            if chip is None:
                continue
            chip_buckets.setdefault(chip[3], []).append(
                (i, chip[0], chip_hover(r, model), r.asset))
        for ink, points in chip_buckets.items():
            fig.add_trace(go.Scatter(
                x=[(CHIP_X0 + CHIP_X1) / 2] * len(points),
                y=[p[0] for p in points],
                mode="text", text=[p[1] for p in points],
                textfont=dict(size=CHIP_TEXT_SIZE, color=ink),
                hovertext=[p[2] for p in points], hoverinfo="text",
                customdata=[p[3] for p in points],
                showlegend=False))

        # The sparklines: one line per market, one shared endpoint trace so the dots
        # can carry per-point colour without a trace apiece.
        end_xs, end_ys, end_colours, end_hovers, end_assets = [], [], [], [], []
        for i, read in markets:
            xs, ys = _spark_points(read, i)
            if not xs:
                continue
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines",
                line=dict(color=SPARK_LINE, width=1),
                hoverinfo="skip", showlegend=False))
            end_xs.append(xs[-1])
            end_ys.append(ys[-1])
            latest = [v for v in read.path if v is not None][-1]
            end_colours.append(colors.bull if latest >= const.INDEX_NEUTRAL
                               else colors.bear)
            end_hovers.append(spark_hover(read))
            end_assets.append(read.asset)
        if end_xs:
            fig.add_trace(go.Scatter(
                x=end_xs, y=end_ys, mode="markers",
                marker=dict(size=SPARK_END_SIZE, color=end_colours),
                hovertext=end_hovers, hoverinfo="text",
                customdata=end_assets, showlegend=False))

    n = len(rows)
    fig.update_layout(
        height=figure_height(rows),
        margin=dict(l=LEFT_MARGIN_PX, r=8, t=TOP_CHROME_PX, b=BOTTOM_CHROME_PX),
        paper_bgcolor=background,
        plot_bgcolor=background,
        showlegend=False,
        xaxis=dict(
            range=list(X_RANGE),
            side="top",
            tickvals=list(HEADER_TICK_XS),
            ticktext=list(WINDOW_LABELS) + [vc.MOMENTUM_LABEL, "52w path"],
            tickfont=dict(size=10, color=vc.TEXT_COLOR),
            showgrid=False, zeroline=False, fixedrange=True),
        yaxis=dict(
            range=[n - 0.5, -0.5],
            showticklabels=False,
            showgrid=False, zeroline=False, fixedrange=True),
        hoverlabel=dict(bgcolor="#0e1116", font=dict(color=vc.HOVER_TEXT_COLOR)),
    )
    return fig
