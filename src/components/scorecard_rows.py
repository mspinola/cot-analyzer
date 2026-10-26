"""The Scorecard: one asset class, positioning and tape, on one screen.

Modelled on the one-screen FX currency scorecards (columns are markets, rows are
readings, every cell the same kind of number), and departing from them in four
places that are written up in `docs/design/positioning-report-view-ideas.md`.

**The number is the level, the colour is the verdict.** Nothing here is sign-flipped.
A Non-Reportable index of -9 is small specs washed out, which is the bullish side
under positioning fade, so the cell reads -9 and draws the bull hue. This is the rule
`strip_traces` already states and the Heatmap's index cells already follow, and it is
the opposite of `/crowd`, where colour IS value. A reader meeting the two in one
session has to be told which is which, so the caption says so rather than leaving it
to be inferred. Flipping would be the alternative, and it costs the thing that makes
the number worth printing: a flipped cell can no longer be checked against the CFTC
file or against anybody else's table.

**A fill means a verdict exists.** `PositioningModel.setup_state` reads three
positioning indices and no price term, so the gates say nothing about whether a high
price-in-range is the bullish side. Rows the model gives no direction therefore draw
no block. They keep the neutral hue as ink, because a saturated fill carrying no
verdict pulls the same weight as one that does and inverts the card's hierarchy.

**Directionless rows are drawn as paths, not numbers.** A sparkline asserts nothing
about a distribution, which is exactly right for a row with no tested direction, and
it closes the gap `positioning-report-view-ideas.md` identifies and rejects box plots
for failing to close: a market pinned at an extreme for four months and one that
arrived this week otherwise look identical. One sparkline of the weekly closes also
carries BOTH of the rows it replaced, since where the line ends in its own range is
the range index and the slope of the last quarter is the 13-week change. Whiskers stay
out: `crucible`'s tearsheets spend that idiom on confidence intervals, and quartiles
over a series with 0.956 lag-1 autocorrelation are confidently imprecise.

**No averaged summary score.** The source format's top block is an unweighted mean of
heterogeneous rows. That is a composite, and this stack has already paid for one:
crowdmon closed with no positive result after four pre-registered tests. The top row
here is the model's gate instead, which is the only row on the surface that has been
through the ladder. Everything under it is description.

The row set is measured, not copied. Within-market Spearman against the Commercial
Index, median over 42 markets with ten years of weekly reports each, on the series
each row draws: willco +1.00 (it prints the same cell in 99.7% of weeks), the
Non-Commercial index -0.98, the range-indexed Commercial z-score +0.76, spec long
concentration -0.73. All four are off the card, because three legs of one report are
not three opinions and the Legacy legs sum to zero by construction. What survived is
in ROWS below, each carrying the figure on its label tooltip rather than on the face
of the card, where it cost more scan time than it bought.

Everything here is a pure function over a read plus a colour set, the `strip_traces`
rule, so the layout is testable without a store, a palette file or a browser.
"""

from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import quote

import cotmetrics.constants as const
from dash import html

import viz_constants as vc
from components.plot_colors import (
    INK_BRIGHT,
    INK_PIVOT,
    blend_over,
    hex_to_rgba,
    relative_luminance,
)

#: The card's one scale. A 0-100 range index maps to -SCALE..+SCALE, which is two
#: characters at most and is what lets rows of different origin sit in one column.
SCALE = 10

#: Weeks + 1 observations, matching `CotIndexer.process_lookback`'s inclusive slice so
#: a 52-week reading here and the Strip's are the same number rather than neighbours.
#: The same rule `/crowd` and `categories.build_category_frame` follow.
WINDOW = 53

#: Deliberately outside the palette's bull/bear pair. A row with no verdict must not
#: be drawable in a verdict colour by accident, so the neutral is a fixed hue that no
#: palette supplies and nothing else on the card uses. It appears as INK, never fill.
#:
#: Solarized's violet lightened: the base #6c71c4 reaches only 3.98:1 against the page
#: at FULL strength, so a partly transparent ramp built on it was unreadable at the
#: dim end (2.1:1). This clears 4.5:1 across the whole ramp while staying at least 130
#: RGB units from every shipped palette's bull and bear slot, which is what keeps it
#: from being mistaken for a verdict.
NEUTRAL_INK = "#aeb1df"

#: `direction` on a row: which end of its native scale is the bullish side, or
#: NO_DIRECTION when the model establishes none and the row must not be hued.
BULL_HIGH, BULL_LOW, NO_DIRECTION = 1, -1, 0

#: The faintest a verdict cell tints. Low enough that a +1 barely lifts off the page,
#: which is the point: the fill is what says "look here".
FILL_MIN_ALPHA = 0.12

SPARK_W, SPARK_H, SPARK_PAD = 58, 18, 2.5

#: One leg's lane in a positioning mark, and the mark's drawing width. The lane is
#: the /strip and home-card idiom: legs are told apart by WHERE they sit, never by
#: colour, which this card reserves for the verdict. signal_cards learned the same
#: lesson the hard way, since palette slot 0 (the Commercial leg's colour) is the
#: bear red, so a bullish Commercial reading drew a red dot.
#: Lane height matches the home card's, and the mark is drawn wide and scaled to the
#: cell rather than pinned at a fixed pixel width. Both were too small first time:
#: at 44x7 per lane the mark was HEIGHT-limited, so a 67px cell still drew a 44px
#: axis, 0.44px per index point, and two dots a few points apart were one smudge.
LANE_PX = 11
MARK_W = 72
#: Commercials are the leg every gate reads; the others are context for it.
COMM_DOT_R, SPEC_DOT_R = 3.0, 2.3

#: Stem widths. A bare dot has no length, so every reading drew the same amount of
#: ink whatever its value, which is why the first marks conveyed nothing. The stem
#: is `strip_traces`' lollipop: it runs from the neutral midpoint to the value, so
#: distance from neutral becomes a length the eye reads without measuring, and a
#: market sitting near 50 draws almost none. signal_cards found the spec lanes
#: unreadable as bare ticks for the same reason and restored their stems at half
#: width; the Commercial lollipop stays the heaviest mark by stem weight and head
#: size together.
COMM_STEM_PX, SPEC_STEM_PX = 2.0, 1.0
#: The head is the datum and takes full-strength colour; the stem is context and is
#: knocked back, the proportion strip_traces uses for the same two parts.
STEM_ALPHA = 0.55

#: The gate band drawn behind each lane. This is what makes a mark readable at this
#: size, and leaving it out was the real defect rather than the dimensions: precision
#: is not the question a sweep asks, "is this leg through the gate" is, and a tinted
#: zone answers that at any resolution. Alpha from signal_cards, which calibrated it
#: on screen; the zone here is one lane rather than the full strip height, so it sits
#: at the top of their range -- but no higher, because a wide band is a LOT of tint:
#: NPF's 80/20 gate puts 40% of every lane inside a zone, where Raw PF's 95/5 puts
#: 10%. Calibrated against the wide one, where the dots have to stay the thing the
#: eye lands on.
ZONE_ALPHA = 0.12
#: NOT a fainter grey. signal_cards found a near-black midline invisible on a card,
#: which "left every dot measured from nothing"; the same applies in a table cell.
AXIS_RULE = "rgba(255, 255, 255, 0.22)"
LANE_RULE = "rgba(255, 255, 255, 0.10)"

#: Minimum observations before a path is worth drawing. Below this the shape is noise
#: wearing a long name, and the cell says nothing rather than implying a trend.
SPARK_MIN_POINTS = 8


@dataclass(frozen=True)
class ScoreRow:
    """A row drawn as a number, coloured by what the reading means."""

    key: str
    label: str
    #: Which end is bullish. NO_DIRECTION draws ink rather than a block.
    direction: int
    #: Within-market Spearman against the Commercial Index, on the series THIS row
    #: draws. None on the anchor row itself. Shown on hover, never on the card.
    rho: float = None
    #: The one kind of note that stays visible: it changes how the NUMBER is read.
    #: Provenance belongs in the tooltip.
    note: str = ""


@dataclass(frozen=True)
class LegMark:
    """One leg's reading inside a positioning mark.

    `direction` is that leg's own bullish end, so the dot takes the card's verdict
    colour by the same rule a number cell does: high Commercials are the bull side,
    high speculators are the bear side under positioning fade.
    """

    short: str
    value: float
    direction: int
    #: The leg's own colour, for the legs that carry one. None means "take the
    #: verdict colour", which is what Commercials do: palette slot 0 IS the bear
    #: red, so colouring that lane by identity drew a bullish reading in red.
    #: signal_cards reached the same split (COMM_LANE_TAKES_LEG_COLOUR = False).
    hue: str = None


@dataclass(frozen=True)
class SparkRow:
    """A row drawn as a path. No direction, by construction: see the module docstring."""

    key: str
    label: str
    window_note: str
    rho: float = None


#: The measured row set. Order is anchor first, then by how much the row adds.
#: Positioning levels are drawn as ONE row of marks rather than a number row per
#: leg. Which legs appear is the MODEL's answer, not this module's: every gate reads
#: Commercials, the speculator legs are exactly `model.spec_legs`, and an equity
#: index contract gates on Commercials alone. Drawing a leg the gate does not read
#: puts a condition on the card the verdict above it never checked, and omitting one
#: it does read leaves a verdict unexplained. `signal_cards.strip_legs` and
#: `strip_traces.LEG_COLUMNS` are the two surfaces that already follow this; the page
#: builds the list and hands it over in MarketRead.legs.
SCORE_ROWS = (
    ScoreRow("comm_move", "Commercial 6wk move", BULL_HIGH, rho=0.15),
)

SPARK_ROWS = (
    SparkRow("price", "Price", "52 weekly closes", rho=-0.54),
    SparkRow("oi", "Open interest", "52 weeks", rho=-0.07),
)

#: What the gate row prints, and which way it leans.
_SETUP_TEXT = {
    const.SETUP_BULL: ("SETUP", 1),
    const.SETUP_BEAR: ("SETUP", -1),
    const.SETUP_NEAR_BULL: ("near", 1),
    const.SETUP_NEAR_BEAR: ("near", -1),
}

_EMPTY = "·"


@dataclass(frozen=True)
class MarketRead:
    """One column: a market at the week the card is showing.

    `scores` and `paths` are keyed by row key. Values arrive as 0-100 range indices
    and raw series respectively; this module owns turning them into cells, so the
    page never computes a colour and this never reaches a store.
    """

    symbol: str
    asset: str
    #: The model's verdict, from the matrix frame. Its window is the model's own
    #: tuned lookback, NOT the uniform one the rows below use; the caption says so.
    state: str = const.SETUP_NONE
    scores: dict = field(default_factory=dict)
    paths: dict = field(default_factory=dict)
    #: LegMark per gated leg, Commercials first. Empty draws nothing rather than
    #: an empty axis, the sparkline rule.
    legs: tuple = ()
    date: str = ""


def score(index):
    """A 0-100 range index as an integer in -SCALE..+SCALE, or None.

    Clamped rather than wrapped: an index outside 0-100 is a caller bug, and a cell
    reading +14 would silently leave the card's one scale.
    """
    if index is None or index != index:  # NaN
        return None
    return int(max(-SCALE, min(SCALE, round((float(index) - 50) / (100 / (2 * SCALE))))))


def verdict(value, direction):
    """What the reading MEANS: +1 bullish, -1 bearish, 0 neither.

    Separate from the value on purpose. This is the whole colour rule in one place,
    and the place a row whose high end is bearish stops being a special case.
    """
    if value is None or direction == NO_DIRECTION or value == 0:
        return 0
    return 1 if value * direction > 0 else -1


#: The ramp is quantised so two cells a step apart cannot differ by an invisible
#: fraction of a percent, and so the cap is expressible on the same grid.
ALPHA_STEP = 0.001


def _floor_alpha(alpha):
    return int(alpha / ALPHA_STEP) * ALPHA_STEP


@lru_cache(maxsize=32)
def fill_alpha_cap(hue, background=vc.BACKGROUND_COLOR):
    """The strongest blend of `hue` that still takes the BRIGHT ink.

    Capping the ramp here is what keeps one ink across the whole card, and that is a
    legibility rule serving a SALIENCE one. Choosing ink per cell by contrast is
    correct and still reads backwards: on a dark page a luminous glyph draws the eye
    and a dark glyph recedes, so the moment the brightest cells flip to dark ink the
    text treatment runs opposite to the fill, and a +1 in bright ink on near-black
    out-shouts a +10 in dark ink. Contrast is symmetric and salience is not, which is
    why a contrast sweep cannot catch it.

    So the fill never gets bright enough to need the other ink. Magnitude is carried
    by the fill alone, monotonically, and every number is drawn the same way.
    Measured: this lands every palette and pole at 4.11:1 or better.
    """
    if relative_luminance(blend_over(hue, 1.0, background)) <= INK_PIVOT:
        return 1.0
    low, high = 0.0, 1.0
    for _ in range(24):  # 1e-7, far finer than a hex channel resolves
        mid = (low + high) / 2
        if relative_luminance(blend_over(hue, mid, background)) <= INK_PIVOT:
            low = mid
        else:
            high = mid
    # Onto the same grid the ramp quantises to, DOWNWARD. Rounding to three places
    # can round up across the boundary, and blend_over rounds each channel to an
    # integer besides, so a cap that is under the pivot as a float can land a hair
    # over it once drawn. Step down until the colour actually drawn is under.
    cap = _floor_alpha(low)
    while cap > 0 and relative_luminance(blend_over(hue, cap, background)) > INK_PIVOT:
        cap = round(cap - ALPHA_STEP, 3)
    return cap


def cell_style(value, direction, colors):
    """The style for one score cell. Fill when there is a verdict, ink when not."""
    if value is None:
        return {"color": colors.dim}
    weight = abs(value) / SCALE
    lean = verdict(value, direction)
    if direction == NO_DIRECTION:
        # Floor at 0.70, not 0. Below it the ink drops under 4.5:1 against the page
        # and the faintest cells stop being readable at all, which is a different
        # thing from receding. Weight still reads, from the ramp and the font.
        return {"color": hex_to_rgba(NEUTRAL_INK, round(0.70 + 0.30 * weight, 2)),
                "fontWeight": 500 + 100 * round(weight)}
    if lean == 0:
        return {"color": colors.dim}
    # One ink for every cell, with the fill capped so it stays legible against it.
    # See fill_alpha_cap for why the ink must not vary: per-cell ink inverts the
    # card's attention ordering even when every cell passes a contrast check.
    hue = colors.bull if lean > 0 else colors.bear
    cap = fill_alpha_cap(hue)
    fill = blend_over(hue, _floor_alpha(FILL_MIN_ALPHA
                                       + (cap - FILL_MIN_ALPHA) * weight))
    return {"backgroundColor": fill, "color": INK_BRIGHT,
            # Reinforces the fill rather than competing with it.
            "fontWeight": 500 + 100 * round(2 * weight)}


def with_ink(style):
    """Mirror a style's `color` into the custom property the stylesheet applies.

    The app's theme sets `tbody td { color: var(--text-muted) !important }`, which
    beats an inline colour, and React cannot emit `!important` inline. So every cell
    carries its ink twice: `color`, which is correct wherever the theme rule does not
    reach, and `--scorecard-ink`, which the rule in custom.css reads. Routing every
    cell through one function is what stops the two drifting apart.
    """
    ink = style.get("color")
    return style if ink is None else {**style, "--scorecard-ink": ink}


def cell_text(value):
    """Signed, so a column of cells reads as levels rather than magnitudes."""
    if value is None:
        return _EMPTY
    return f"{value:+d}" if value else "0"


def sparkline(values):
    """(svg source, percentile of the last point) for a path, or (None, None).

    The faint rule is the midpoint of the window's own range, so where the dot sits
    against it IS the range-index reading the number used to carry. A flat series
    draws nothing: with no range there is no position within it, and a line through
    the middle of an empty range would read as "mid-range" rather than "no range".
    """
    clean = [float(v) for v in values if v is not None and v == v]
    if len(clean) < SPARK_MIN_POINTS:
        return None, None
    low, high = min(clean), max(clean)
    span = high - low
    if span <= 0:
        return None, None

    usable = SPARK_H - 2 * SPARK_PAD
    step = (SPARK_W - 2) / (len(clean) - 1)
    points = [(1 + i * step, SPARK_PAD + usable * (1 - (v - low) / span))
              for i, v in enumerate(clean)]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    mid = SPARK_PAD + usable / 2
    end_x, end_y = points[-1]
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SPARK_W}" '
        f'height="{SPARK_H}" viewBox="0 0 {SPARK_W} {SPARK_H}">'
        f'<line x1="0" y1="{mid:.1f}" x2="{SPARK_W}" y2="{mid:.1f}" '
        f'stroke="rgba(255,255,255,0.14)" stroke-width="1"/>'
        f'<polyline points="{path}" fill="none" '
        f'stroke="{hex_to_rgba(NEUTRAL_INK, 0.85)}" stroke-width="1.3" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        # rgba(), never the hex: this ends up in a data URI, where an unescaped '#'
        # opens a fragment and silently truncates the document to a broken image.
        f'<circle cx="{end_x:.1f}" cy="{end_y:.1f}" r="1.9" '
        f'fill="{hex_to_rgba(NEUTRAL_INK, 1)}"/>'
        f"</svg>")
    return svg, int(round(100 * (clean[-1] - low) / span))


def leg_marks(legs, colors, lanes, band):
    """One market's gated legs as a tiny lane chart, or (None, None).

    Each leg gets a lane; the dot sits at that leg's index along a 0-100 axis, with a
    faint rule at the neutral midpoint. Identity is the lane, never the colour: the
    colour is the leg's own verdict, so a Commercial dot high in its range and a
    speculator dot low in its range both draw bullish, which is the same thing the
    number cells say and the reason the two can be read together.

    `lanes` is the card's widest leg count, passed in so every cell in the row is the
    same height and the rows below stay aligned. A market with fewer legs than the
    card (an equity index contract, which gates on Commercials alone) simply draws
    fewer, rather than being padded with lanes that mean nothing.
    """
    if not legs:
        return None, None
    height = LANE_PX * max(lanes, 1)
    high, low = band
    pad, span = 2, MARK_W - 4

    def at(index_value):
        return pad + span * max(0.0, min(100.0, float(index_value))) / 100

    mid_x = at(50)
    parts = []
    for i, leg in enumerate(legs):
        top = LANE_PX * i + 1
        lane_h = LANE_PX - 2
        y = LANE_PX * i + LANE_PX / 2
        # Each END of the lane is a gate extreme, tinted by what reaching it would
        # MEAN for this leg. High Commercials and low speculators are both the bull
        # side, so a setup lights every lane green whichever end its dot sits at.
        for edge_x, edge_w, is_bull_end in (
                (at(0), at(low) - at(0), leg.direction == BULL_LOW),
                (at(high), at(100) - at(high), leg.direction == BULL_HIGH)):
            hue = colors.bull if is_bull_end else colors.bear
            parts.append(
                f'<rect x="{edge_x:.1f}" y="{top}" width="{edge_w:.1f}" '
                f'height="{lane_h}" rx="1.5" '
                f'fill="{hex_to_rgba(hue, ZONE_ALPHA)}"/>')
        parts.append(f'<line x1="{pad}" y1="{y:.1f}" x2="{MARK_W - pad}" '
                     f'y2="{y:.1f}" stroke="{LANE_RULE}" stroke-width="1"/>')
        if leg.value is None or leg.value != leg.value:
            continue
        lean = verdict(score(leg.value), leg.direction)
        if leg.hue:
            hue = leg.hue
        else:
            hue = (colors.dim if lean == 0
                   else (colors.bull if lean > 0 else colors.bear))
        x = at(leg.value)
        # The stem first, so the head sits on top of it rather than behind it.
        parts.append(
            f'<line x1="{mid_x:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{y:.1f}" '
            f'stroke="{hex_to_rgba(hue, STEM_ALPHA)}" stroke-linecap="round" '
            f'stroke-width="{COMM_STEM_PX if i == 0 else SPEC_STEM_PX}"/>')
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" '
                     f'r="{COMM_DOT_R if i == 0 else SPEC_DOT_R}" fill="{hue}"/>')
    parts.append(f'<line x1="{mid_x:.1f}" y1="0" x2="{mid_x:.1f}" y2="{height}" '
                 f'stroke="{AXIS_RULE}" stroke-width="1"/>')

    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{MARK_W}" '
           f'height="{height}" viewBox="0 0 {MARK_W} {height}">'
           + "".join(parts) + "</svg>")
    title = ", ".join(
        f"{leg.short} {int(round(leg.value))}" for leg in legs
        if leg.value is not None and leg.value == leg.value)
    return svg, f"{title} (0 at the window low, 100 at its high)"


def spark_img(svg):
    """The path as an <img>, so a cell costs no Graph and no extra dependency.

    A data URI rather than a dcc.Graph: eighteen of these on a card would be eighteen
    Plotly instances for a nine-point line, and `dash.html` has no Svg element.

    '#' is deliberately NOT in the safe set. In a URI it opens a fragment, so one
    unescaped hex colour truncates the document at that point and the cell renders
    as a broken image rather than as an error anything would catch.
    """
    return svg_img(svg, SPARK_H)


def mark_img(svg):
    """The leg mark, scaled to the cell rather than pinned at a pixel width.

    `height: auto` with a max width is what lets the drawing use the whole cell: the
    aspect ratio is preserved, so a wider cell buys horizontal resolution AND bigger
    dots together, and the cap stops a two-market card drawing one enormous mark.
    """
    return html.Img(
        src="data:image/svg+xml;utf8," + quote(svg, safe="/:=\"' <>,.-()"),
        style={"width": "100%", "maxWidth": f"{MARK_W}px", "height": "auto",
               "display": "block", "margin": "0 auto"},
    )


def svg_img(svg, height):
    """An inline SVG as an <img>, so a cell costs no Graph and no new dependency.

    '#' is deliberately NOT in the safe set. In a URI it opens a fragment, so one
    unescaped hex colour truncates the document at that point and the cell renders as
    a broken image rather than as an error anything would catch.
    """
    return html.Img(
        src="data:image/svg+xml;utf8," + quote(svg, safe="/:=\"' <>,.-()"),
        style={"width": "100%", "height": f"{height}px", "display": "block"},
    )


def row_tooltip(rho):
    """Where the correlation lives now. See the module docstring on scan cost."""
    if rho is None:
        return "The row every other correlation on this card is measured against."
    return (f"Correlation with the Commercial Index row: {rho:+.2f}, median across "
            f"42 markets. Only the size says how much this row adds; the sign says "
            f"which way it runs against the anchor.")


def setup_cell(state, colors):
    """The gate's answer for one market, or an empty mark."""
    if state not in _SETUP_TEXT:
        return _EMPTY, {"color": colors.dim}
    text, lean = _SETUP_TEXT[state]
    hue = colors.bull if lean > 0 else colors.bear
    cap = fill_alpha_cap(hue)
    # The same capped ramp a score cell uses, at two fixed stops, so the chip sits in
    # the card's one ordering rather than beside it.
    strong = state in (const.SETUP_BULL, const.SETUP_BEAR)
    fill = blend_over(hue, cap if strong
                      else _floor_alpha(FILL_MIN_ALPHA + 0.35 * cap))
    return (
        f"{text} {'↑' if lean > 0 else '↓'}",
        {"backgroundColor": fill, "color": INK_BRIGHT,
         "fontWeight": 700 if strong else 600,
         "fontSize": "0.65rem", "letterSpacing": "0.3px"},
    )


#: Under `table-layout: fixed` the HEADER row sets every column's width, so this has
#: to reach the header's empty corner cell as well as the body's labels. Set on the
#: body alone, the browser divides the width evenly and the labels run under the first
#: market's column, which is invisible until a card is wide enough to squeeze them.
_LABEL_WIDTH = "180px"

#: Floor for a market column. Nine markets inside a phone's 375px would otherwise be
#: about twenty pixels each, which runs the symbols together and wraps the gate chip
#: onto two lines. Below the floor the card SCROLLS instead of compressing, and the
#: label column stays put so the row names do not scroll away with it.
_MIN_COL_WIDTH = 44

_LABEL_STYLE = {
    "width": _LABEL_WIDTH, "textAlign": "right", "fontSize": "0.72rem",
    "color": "#9fb0c2", "paddingRight": "9px", "whiteSpace": "nowrap",
    "cursor": "help", "border": "0",
    # Pinned while the markets scroll under it. Needs an opaque background of its
    # own, or the cells it is covering show through.
    "position": "sticky", "left": "0", "zIndex": 1,
    "backgroundColor": vc.BACKGROUND_COLOR,
}
_CELL_STYLE = {
    "textAlign": "center", "fontSize": "0.75rem", "fontVariantNumeric": "tabular-nums",
    "padding": "5px 2px", "borderRadius": "2px", "border": "0",
}
_HEAD_STYLE = {
    "textAlign": "center", "fontSize": "0.7rem", "fontWeight": "600",
    "color": "#E2E8F0", "padding": "5px 2px", "border": "0",
}
_BLOCK_STYLE = {
    "textAlign": "left", "fontSize": "0.62rem", "letterSpacing": "0.8px",
    "textTransform": "uppercase", "color": "#E2E8F0",
    "backgroundColor": "#262626", "padding": "4px 9px", "borderRadius": "2px",
    "border": "0",
}
_NOTE_STYLE = {"fontSize": "0.58rem", "color": "#7d8da0", "textTransform": "none",
               "letterSpacing": "0"}


def _label_px():
    return int(_LABEL_WIDTH.removesuffix("px"))


def _label(row):
    note = ([" ", html.Span(row.note, style=_NOTE_STYLE)]
            if getattr(row, "note", "") else [])
    return html.Td([row.label] + note, style=with_ink(_LABEL_STYLE),
                   title=row_tooltip(row.rho))


def _block(title, note, span):
    return html.Tr([html.Td(
        [title, " ", html.Span(note, style=_NOTE_STYLE)] if note else [title],
        colSpan=span, style=with_ink(_BLOCK_STYLE))])


def card_min_px(market_count):
    """The narrowest the card can be drawn before it starts scrolling sideways.

    Public because the PAGE decides the two-column layout and needs to know which
    cards will not fit a half column. Derived from the same two constants the table
    is built from, so the layout and the table cannot disagree about a card's width.
    """
    return _label_px() + _MIN_COL_WIDTH * market_count


#: A card wider than this is given a whole row rather than squeezed into a column.
#: It is the usable half-column at the 992px breakpoint, less the grid gap and the
#: container's padding. Only the nine-market Currencies card exceeds it today.
GRID_COLUMN_PX = 460


def build_table(reads, model, colors):
    """The card. Pure over `reads` plus a colour set; no store, no palette file."""
    span = len(reads) + 1
    head = html.Tr([html.Th("", style={**_HEAD_STYLE, "width": _LABEL_WIDTH})]
                   + [html.Th(r.symbol or r.asset, style=_HEAD_STYLE) for r in reads])

    body = [_block("Model verdict", f"{model.title}, the only gated row", span)]
    setup_cells = []
    for read in reads:
        text, style = setup_cell(read.state, colors)
        setup_cells.append(html.Td(text, style=with_ink({**_CELL_STYLE, **style})))
    body.append(html.Tr([html.Td(
        "Setup", style=_LABEL_STYLE,
        title="The model's own verdict, on its own tuned window. Every row below "
              "is a uniform 52 weeks, so the two windows differ.")] + setup_cells))

    body.append(_block("Positioning",
                       "lane is the leg, shaded ends are the gate",
                       span))

    # The leg row: one mark per market, one lane per leg the model gates on. Lanes
    # are sized to the WIDEST market on this card so the row has one height and the
    # rows under it stay aligned.
    lanes = max((len(r.legs) for r in reads), default=0)
    if lanes:
        cells = []
        for read in reads:
            svg, title = leg_marks(read.legs, colors, lanes, model.band)
            if svg is None:
                cells.append(html.Td(_EMPTY, style=with_ink(
                    {**_CELL_STYLE, "color": colors.dim})))
            else:
                cells.append(html.Td(
                    mark_img(svg),
                    style={**_CELL_STYLE, "padding": "3px 2px", "lineHeight": "0",
                           "cursor": "help"},
                    title=title))
        # Named by the legs actually drawn, in lane order, so the mark needs no key.
        order = next((r.legs for r in reads if len(r.legs) == lanes), ())
        body.append(html.Tr([html.Td(
            " / ".join(leg.short for leg in order), style=with_ink(_LABEL_STYLE),
            title="One lane per leg this model gates on, Commercials first. The dot "
                  "sits at that leg's range index; the faint rule is the midpoint. "
                  "Colour is the leg's own verdict, so a high Commercial reading and "
                  "a low speculator reading both draw bullish.")] + cells))

    for row in SCORE_ROWS:
        cells = []
        for read in reads:
            value = score(read.scores.get(row.key))
            cells.append(html.Td(
                cell_text(value),
                style=with_ink({**_CELL_STYLE,
                                **cell_style(value, row.direction, colors)})))
        body.append(html.Tr([_label(row)] + cells))

    body.append(_block("Tape and participation",
                       "no tested direction, so shape rather than a verdict", span))
    for row in SPARK_ROWS:
        cells = []
        for read in reads:
            svg, pct = sparkline(read.paths.get(row.key, ()))
            if svg is None:
                cells.append(html.Td(_EMPTY, style=with_ink(
                    {**_CELL_STYLE, "color": colors.dim})))
            else:
                cells.append(html.Td(
                    spark_img(svg),
                    style={**_CELL_STYLE, "padding": "2px", "lineHeight": "0",
                           "cursor": "help"},
                    title=f"{row.window_note}, latest marked. {pct} of its range."))
        body.append(html.Tr([_label(row)] + cells))

    table = html.Table(
        [html.Thead(head), html.Tbody(body)],
        # The class the ink rule in custom.css hangs off. See with_ink.
        className="scorecard-card",
        style={"borderCollapse": "separate", "borderSpacing": "2px",
               "width": "100%", "tableLayout": "fixed",
               "minWidth": f"{card_min_px(len(reads))}px",
               "maxWidth": "980px", "margin": "0 auto"})
    # The scroll lives on THIS wrapper, never on the body: a page-level overflow-x
    # is what the mobile work had to undo elsewhere in this app, and it breaks
    # position: sticky for everything inside it.
    return html.Div(table, style={"overflowX": "auto", "maxWidth": "100%"})
