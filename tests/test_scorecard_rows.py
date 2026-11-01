"""The Scorecard's cell rules, which is where this page can go quietly wrong.

Four invariants are worth holding by test rather than by review, because each one
breaks into something that still renders and still looks plausible:

- a cell's NUMBER is its native level and is never sign-flipped, so it stays checkable
  against the CFTC file
- a cell's COLOUR is the verdict, so a low Non-Reportable reading draws the BULL hue
  while printing a negative number
- a row the model gives no direction never draws a fill, only ink
- a sparkline's endpoint is the same reading as the range index it replaced

The last one is the reason the two tape rows could be collapsed into one path at all.
If it stops holding, the card is showing a shape whose position means something other
than the number the design note claims it carries.
"""
import re

import cotmetrics.constants as const
import cotmetrics.models as models
import pytest
from cotmetrics.indicators import calculate_range_index
from dash import html
from pandas import Series

import components.scorecard_rows as sr
import viz_config
import viz_constants as vc
from components.plot_colors import (
    INK_PIVOT,
    GridColors,
    blend_over,
    grid_colors,
    relative_luminance,
)

BULL_HEX, BEAR_HEX = "#2aa198", "#FF4D4D"
COLORS = GridColors(bull=BULL_HEX, bear=BEAR_HEX,
                    bull_near="rgba(42, 161, 152, 0.5)",
                    bear_near="rgba(255, 77, 77, 0.5)")


def read(symbol="6A", state=const.SETUP_NONE, **scores):
    paths = scores.pop("paths", {})
    legs = scores.pop("legs", (sr.LegMark("Comm", 50, sr.BULL_HIGH),))
    net = scores.pop("net", ())
    return sr.MarketRead(symbol=symbol, asset=symbol, state=state, scores=scores,
                         paths=paths, legs=legs, net=net, date="2026-10-20")


def _rgb(hex_color):
    h = str(hex_color).lstrip("#")
    return tuple(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def _distance(a, b):
    return sum((int(x) - int(y)) ** 2 for x, y in zip(_rgb(a), _rgb(b))) ** 0.5


def _ink_alpha(style):
    return float(str(style["color"]).rsplit(",", 1)[1].rstrip(") "))


def _composited_ink(style):
    """What the browser will actually paint: the ink over the page.

    A partly transparent colour's contrast depends on what it lands on, so the
    rgba has to be composited before it can be measured.
    """
    channels = str(style["color"])[5:].split(",")[:3]
    hex_ink = "#" + "".join("%02x" % int(c) for c in channels)
    return blend_over(hex_ink, _ink_alpha(style))


def _is_fill_hue(style, hex_color):
    """Which pole a FILL leans toward. Only the gate chip fills now, and its fill is
    the pole composited over the page, so it is never equal to the pole: ask which
    one it is nearer, independent of the blend formula and of any palette's hues."""
    fill = style.get("backgroundColor")
    if fill is None:
        return False
    other = BEAR_HEX if hex_color == BULL_HEX else BULL_HEX
    return _distance(fill, hex_color) < _distance(fill, other)


def _is_hue(style, hex_color):
    """Which pole a NUMBER leans toward, read off its ink.

    Numbers no longer fill, so the pole is carried by `color` as an rgba of the hue
    itself rather than as a blend over the page.
    """
    ink = str(style.get("color", ""))
    return ink.startswith(f"rgba({', '.join(_rgb(hex_color))}")


def _lift(style):
    """How far the fill sits from the page background: the card's 'weight'."""
    return _distance(style["backgroundColor"], vc.BACKGROUND_COLOR)


def _contrast(fg, bg):
    """WCAG contrast ratio. 4.5 is the floor for normal-size text."""
    a, b = sorted((relative_luminance(fg), relative_luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


# ── the scale ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("index,expected", [
    (0, -10), (50, 0), (100, 10), (25, -5), (75, 5), (94, 9), (6, -9),
])
def test_a_range_index_maps_onto_the_cards_one_scale(index, expected):
    assert sr.score(index) == expected


def test_a_reading_outside_the_index_is_clamped_not_wrapped():
    """An out-of-range index is a caller bug. Clamping keeps the card on one scale
    instead of printing a cell that silently leaves it."""
    assert sr.score(140) == sr.SCALE
    assert sr.score(-40) == -sr.SCALE


def test_a_missing_reading_is_absent_rather_than_neutral():
    """None, not 0: a market with no reading must not print as mid-range."""
    assert sr.score(None) is None
    assert sr.score(float("nan")) is None
    assert sr.cell_text(None) == sr._EMPTY


def test_a_number_carries_its_own_sign():
    assert sr.cell_text(9) == "+9"
    assert sr.cell_text(-9) == "-9"
    assert sr.cell_text(0) == "0"


# ── colour is the verdict, not the value ─────────────────────────────────────

def test_a_low_speculator_reading_sits_left_and_draws_bullish():
    """THE invariant, now carried by the leg mark. Specs washed out is the bullish
    side under positioning fade, so the dot sits at the LOW end of its lane and takes
    the bull hue. Position and colour disagreeing is the informative case."""
    svg, _ = marks((sr.LegMark("Comm", 94, sr.BULL_HIGH),
         sr.LegMark("NonRept", 6, sr.BULL_LOW)), 2)
    dots = re.findall(r'<circle cx="([\d.]+)"[^>]*fill="([^"]+)"', svg)
    (comm_x, comm_fill), (spec_x, spec_fill) = dots
    assert float(spec_x) < float(comm_x)        # low in its range
    assert spec_fill == comm_fill == BULL_HEX   # both the bullish side


def test_a_high_non_reportable_reading_prints_positive_and_draws_bearish():
    value = sr.score(94)
    assert sr.cell_text(value) == "+9"
    assert _is_hue(sr.cell_style(value, sr.BULL_LOW, COLORS), BEAR_HEX)


def test_the_anchor_row_is_the_one_where_sign_and_colour_agree():
    assert _is_hue(sr.cell_style(9, sr.BULL_HIGH, COLORS), BULL_HEX)
    assert _is_hue(sr.cell_style(-9, sr.BULL_HIGH, COLORS), BEAR_HEX)


def test_colour_weight_follows_magnitude_not_sign():
    """Further from neutral is never quieter. With the fill gone the opacity ramp is
    nearly flat (the 4.5:1 floor leaves it 0.90 to 1.00), so the weight is what has
    to carry this, on both poles."""
    for direction in (sr.BULL_HIGH, sr.BULL_LOW):
        for value in (2, 6):
            lo = sr.cell_style(value, direction, COLORS)
            hi = sr.cell_style(value + 4, direction, COLORS)
            assert lo["fontWeight"] <= hi["fontWeight"]
            assert _ink_alpha(lo) <= _ink_alpha(hi)


# ── the numbers stay readable on every palette ───────────────────────────────

PALETTES = viz_config.get_palette_names()

#: WCAG wants 4.5:1 for text this size, and the unfilled rows clear it. A FILLED cell
#: cannot: the ink pivot is also the worst case, and with the app's own ink pair
#: (#E2E8F0 and #101418) the best any threshold can do at that point is 4.14:1. Pure
#: black and white would reach 4.58, but those inks are shared with the Crowdedness
#: Board and changing them is a wider decision than this page. So the floor here is
#: what the pair allows, and it is still a long way from the 2.5:1 it replaced.
FILLED_FLOOR = 4.0


@pytest.mark.parametrize("palette_name", PALETTES)
@pytest.mark.parametrize("value,direction", [
    (10, sr.BULL_HIGH), (-10, sr.BULL_HIGH), (10, sr.BULL_LOW), (-10, sr.BULL_LOW),
    (7, sr.BULL_HIGH), (-7, sr.BULL_HIGH),
])
def test_a_number_is_legible_as_ink_on_the_page(palette_name, value, direction):
    """The bug this pins: ink was chosen by how far the value sat from neutral, so
    the brightest cells printed white on near-white. The shipped palettes put their
    bull slot anywhere from 0.28 (Solarized) to 0.72 luminance (Vibrant, Cyberpunk,
    CMR), and the rule happened to read correctly only on the darkest one, which is
    the palette the design mock used. Every palette, both poles, worst-case weight."""
    colors = grid_colors(viz_config.get_palette(palette_name))
    style = sr.cell_style(value, direction, colors)
    assert _contrast(_composited_ink(style), vc.BACKGROUND_COLOR) >= 4.5, (
        f"{palette_name}: {style['color']} on the page")


@pytest.mark.parametrize("palette_name", PALETTES)
@pytest.mark.parametrize("state", [const.SETUP_BULL, const.SETUP_BEAR,
                                   const.SETUP_NEAR_BULL, const.SETUP_NEAR_BEAR])
def test_the_gate_chip_is_legible_on_every_palette(palette_name, state):
    """A full SETUP is the brightest fill on the card, so it fails first."""
    colors = grid_colors(viz_config.get_palette(palette_name))
    _, style = sr.setup_cell(state, colors)
    assert _contrast(style["color"], style["backgroundColor"]) >= FILLED_FLOOR, (
        f"{palette_name}/{state}: {style['color']} on {style['backgroundColor']}")


@pytest.mark.parametrize("palette_name", PALETTES)
def test_the_directionless_ink_is_legible_on_the_page(palette_name):
    """It has no fill, so it is read against the page itself."""
    colors = grid_colors(viz_config.get_palette(palette_name))
    for value in (1, 10):
        style = sr.cell_style(value, sr.NO_DIRECTION, colors)
        # The ink is NEUTRAL_INK at partial alpha over the page; compose it the way
        # the browser will before measuring.
        alpha = float(style["color"].rsplit(",", 1)[1].rstrip(") "))
        ink = blend_over(sr.NEUTRAL_INK, alpha)
        assert _contrast(ink, vc.BACKGROUND_COLOR) >= 4.5, (
            f"{palette_name}: {ink} on the page at value {value}")


# ── salience: the card's attention ordering must match its magnitudes ────────

@pytest.mark.parametrize("palette_name", PALETTES)
def test_no_number_cell_ever_fills(palette_name):
    """The card's hierarchy in one assertion.

    Once the positioning levels became lollipop marks, the single filled number row
    left was the six-week move, the least load-bearing row on the card, and it took
    all of the eye's attention while the anchor it is secondary to drew thin marks.
    A fill now means the GATE's answer and nothing else, so the Setup chip is the
    only block. Give a number back its fill and the inversion returns.
    """
    colors = grid_colors(viz_config.get_palette(palette_name))
    for direction in (sr.BULL_HIGH, sr.BULL_LOW, sr.NO_DIRECTION):
        for value in range(-10, 11):
            style = sr.cell_style(value, direction, colors)
            assert "backgroundColor" not in style, (
                f"{palette_name}: a number filled at {value}")


@pytest.mark.parametrize("palette_name", PALETTES)
def test_no_fill_is_bright_enough_to_need_the_other_ink(palette_name):
    """What makes one ink legal: the ramp is capped at the pivot, so the dark ink is
    never the better choice. If a fill crosses it, the single-ink rule above has
    become a contrast bug instead of a salience fix."""
    colors = grid_colors(viz_config.get_palette(palette_name))
    for direction in (sr.BULL_HIGH, sr.BULL_LOW):
        for value in range(-10, 11):
            style = sr.cell_style(value, direction, colors)
            fill = style.get("backgroundColor")
            if fill is not None:
                assert relative_luminance(fill) <= INK_PIVOT + 1e-6, (
                    f"{palette_name}: {fill} at {value} crosses the ink pivot")


@pytest.mark.parametrize("palette_name", PALETTES)
def test_the_gate_chip_is_the_only_thing_that_fills(palette_name):
    """It is the one row that has been through a gate, so it is the one row allowed
    to shout. One ink across all four of its states, for the salience reason: a chip
    that flipped to dark ink at full strength would recede exactly where it matters.
    """
    colors = grid_colors(viz_config.get_palette(palette_name))
    styles = [sr.setup_cell(st, colors)[1]
              for st in (const.SETUP_BULL, const.SETUP_BEAR,
                         const.SETUP_NEAR_BULL, const.SETUP_NEAR_BEAR)]
    assert all("backgroundColor" in st for st in styles)
    assert len({st["color"] for st in styles}) == 1


@pytest.mark.parametrize("palette_name", PALETTES)
def test_a_bigger_number_always_draws_a_stronger_cell(palette_name):
    """Nothing about a +10 is quieter than a +1, on either pole."""
    colors = grid_colors(viz_config.get_palette(palette_name))
    for direction in (sr.BULL_HIGH, sr.BULL_LOW):
        styles = [sr.cell_style(v, direction, colors) for v in range(1, 11)]
        weights = [st["fontWeight"] for st in styles]
        alphas = [_ink_alpha(st) for st in styles]
        assert weights == sorted(weights), f"{palette_name}: weight not monotonic"
        assert alphas == sorted(alphas), f"{palette_name}: alpha not monotonic"


# ── a fill means a verdict exists ────────────────────────────────────────────

def test_a_row_with_no_model_direction_never_draws_a_fill():
    """The gates read three positioning indices and no price term. A directionless
    row drawing a block would assert a verdict the model never rendered, and would
    compete with the rows that do carry one."""
    style = sr.cell_style(9, sr.NO_DIRECTION, COLORS)
    assert "backgroundColor" not in style
    assert sr.NEUTRAL_INK.lstrip("#") not in style["color"]  # rgba, not hex
    assert style["color"].startswith("rgba(174, 177, 223")


def test_the_neutral_ink_is_not_a_palette_colour():
    """So a directionless row cannot be drawn in a verdict colour by accident, even
    under a palette whose bull or bear happens to be close to it."""
    assert sr.NEUTRAL_INK not in (COLORS.bull, COLORS.bear)


def test_a_zero_reading_draws_no_verdict():
    assert "backgroundColor" not in sr.cell_style(0, sr.BULL_HIGH, COLORS)


@pytest.mark.parametrize("value,direction,expected", [
    (9, sr.BULL_HIGH, 1), (-9, sr.BULL_HIGH, -1),
    (9, sr.BULL_LOW, -1), (-9, sr.BULL_LOW, 1),
    (9, sr.NO_DIRECTION, 0), (0, sr.BULL_HIGH, 0), (None, sr.BULL_HIGH, 0),
])
def test_verdict_is_the_whole_colour_rule(value, direction, expected):
    assert sr.verdict(value, direction) == expected


# ── the leg mark ─────────────────────────────────────────────────────────────

BAND = models.NPF.band          # (80, 20)


def marks(legs, lanes, band=BAND):
    return sr.leg_marks(legs, COLORS, lanes, band)


def _dots(svg):
    return re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)" '
                      r'fill="([^"]+)"', svg)


def test_commercials_lead_and_draw_larger():
    """Commercials are the leg every gate reads; the others are context for it, the
    same weighting signal_cards gives them."""
    svg, _ = marks((sr.LegMark("Comm", 80, sr.BULL_HIGH),
                   sr.LegMark("NonRept", 20, sr.BULL_LOW)), 2)
    (_, comm_y, comm_r, _), (_, spec_y, spec_r, _) = _dots(svg)
    assert float(comm_y) < float(spec_y)     # top lane
    assert float(comm_r) > float(spec_r)


def test_a_leg_sits_where_its_index_says():
    for value, expected in ((0, 2.0), (50, sr.MARK_W / 2), (100, sr.MARK_W - 2)):
        svg, _ = marks((sr.LegMark("Comm", value, sr.BULL_HIGH),), 1)
        assert float(_dots(svg)[0][0]) == pytest.approx(expected, abs=0.1)


def test_the_row_is_as_tall_as_the_widest_market_on_the_card():
    """Every cell in the row shares a height, or the rows below stop lining up. A
    market with fewer legs draws fewer rather than being padded."""
    one, _ = marks((sr.LegMark("Comm", 50, sr.BULL_HIGH),), 3)
    three, _ = marks(tuple(sr.LegMark(n, 50, sr.BULL_HIGH)
                             for n in ("Comm", "NonComm", "NonRept")), 3)
    assert f'height="{sr.LANE_PX * 3}"' in one
    assert f'height="{sr.LANE_PX * 3}"' in three
    assert len(_dots(one)) == 1 and len(_dots(three)) == 3


def test_a_market_with_no_gated_legs_draws_nothing():
    assert marks((), 2) == (None, None)


def test_a_missing_leg_reading_draws_no_dot_but_keeps_its_lane():
    svg, title = marks((sr.LegMark("Comm", None, sr.BULL_HIGH),
                           sr.LegMark("NonRept", 20, sr.BULL_LOW)), 2)
    assert len(_dots(svg)) == 1
    assert "Comm" not in title and "NonRept 20" in title


def test_the_numbers_are_on_hover():
    _, title = marks((sr.LegMark("Comm", 94.4, sr.BULL_HIGH),
                         sr.LegMark("NonRept", 6.2, sr.BULL_LOW)), 2)
    assert "Comm 94" in title and "NonRept 6" in title


def test_the_mark_carries_no_unescaped_hash():
    """Same data-URI trap as the sparkline: a raw '#' truncates the document."""
    svg, _ = marks((sr.LegMark("Comm", 80, sr.BULL_HIGH),), 1)
    assert "#" not in sr.mark_img(svg).src


def _stems(svg):
    """Lane stems only: the axis rule is vertical and the lane rule has no width."""
    return [m for m in re.findall(
        r'<line x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="[\d.]+" '
        r'stroke="([^"]+)" stroke-linecap="round" stroke-width="([\d.]+)"', svg)]


def test_a_leg_draws_a_stem_from_neutral_to_its_value():
    """A bare dot has no length, so every reading drew the same ink whatever its
    value, which is why the first marks conveyed nothing. The stem turns distance
    from neutral into a length the eye reads without measuring."""
    svg, _ = marks((sr.LegMark("Comm", 95, sr.BULL_HIGH),), 1)
    (x1, _, x2, _, _), = _stems(svg)
    span = sr.MARK_W - 4
    assert float(x1) == pytest.approx(2 + span * 0.5, abs=0.1)   # neutral
    assert float(x2) == pytest.approx(2 + span * 0.95, abs=0.1)  # the value


def _stem_length(svg):
    x1, _, x2, _, _ = _stems(svg)[0]
    return abs(float(x2) - float(x1))


def test_a_market_near_neutral_draws_almost_no_ink():
    """strip_traces' reason for the lollipop: the neutral majority recedes on its
    own, instead of every market drawing an equally loud mark."""
    near = _stem_length(marks((sr.LegMark("Comm", 52, sr.BULL_HIGH),), 1)[0])
    far = _stem_length(marks((sr.LegMark("Comm", 97, sr.BULL_HIGH),), 1)[0])
    assert near < 2 and far > 15


def test_the_commercial_stem_outweighs_the_speculator_stems():
    """signal_cards' finding: spec lanes need stems too or they are bare ticks on an
    empty track, but the Commercial lollipop stays the heaviest mark."""
    svg, _ = marks((sr.LegMark("Comm", 90, sr.BULL_HIGH),
                    sr.LegMark("NonRept", 10, sr.BULL_LOW)), 2)
    comm, spec = _stems(svg)
    assert float(comm[4]) > float(spec[4])


def test_a_leg_with_its_own_colour_keeps_it():
    """Speculator lanes carry the app's leg colour; their verdict is the zone the
    dot lands in, so identity here costs nothing."""
    svg, _ = marks((sr.LegMark("NonComm", 90, sr.BULL_LOW, hue="#60A5FA"),), 1)
    assert "96, 165, 250" in svg          # the stem, knocked back
    assert 'fill="#60A5FA"' in svg        # the head, full strength


def test_the_head_is_brighter_than_its_stem():
    """The head is the datum and the stem is context, the split strip_traces draws."""
    svg, _ = marks((sr.LegMark("Comm", 90, sr.BULL_HIGH),), 1)
    assert f'fill="{BULL_HEX}"' in svg
    assert f"{sr.STEM_ALPHA}" in _stems(svg)[0][3]


def _zones(svg):
    return re.findall(r'<rect x="([\d.]+)" y="\d+" width="([\d.]+)"[^>]*'
                      r'fill="rgba\((\d+), (\d+), (\d+)', svg)


def _rgb_of(hex_color):
    h = hex_color.lstrip("#")
    return tuple(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def test_each_lane_carries_the_gates_band_at_both_ends():
    """The zone is what makes the mark readable at this size. Precision is not the
    question a sweep asks; "is this leg through the gate" is, and a tinted end
    answers it at any resolution. Leaving it out was the real defect the first time,
    not the dimensions."""
    svg, _ = marks((sr.LegMark("Comm", 50, sr.BULL_HIGH),), 1, band=(80, 20))
    zones = _zones(svg)
    assert len(zones) == 2
    widths = sorted(round(float(w)) for _, w, *_ in zones)
    span = sr.MARK_W - 4
    assert widths == [round(span * 0.2), round(span * 0.2)]


def test_the_band_follows_the_model_not_the_card():
    narrow, _ = marks((sr.LegMark("Comm", 50, sr.BULL_HIGH),), 1, band=(95, 5))
    wide, _ = marks((sr.LegMark("Comm", 50, sr.BULL_HIGH),), 1, band=(80, 20))
    assert float(_zones(narrow)[0][1]) < float(_zones(wide)[0][1])


def test_a_legs_bull_end_is_tinted_bull_whichever_end_it_is():
    """Commercials reach the bull side at the HIGH end and speculators at the LOW
    end, so a setup lights every lane green whichever end its dot sits at. Tinting
    both lanes the same way round would make a bull setup read half red."""
    svg, _ = marks((sr.LegMark("Comm", 50, sr.BULL_HIGH),
                    sr.LegMark("NonRept", 50, sr.BULL_LOW)), 2, band=(80, 20))
    comm_lo, comm_hi, spec_lo, spec_hi = _zones(svg)
    bull, bear = _rgb_of(BULL_HEX), _rgb_of(BEAR_HEX)
    assert tuple(comm_hi[2:]) == bull and tuple(comm_lo[2:]) == bear
    assert tuple(spec_lo[2:]) == bull and tuple(spec_hi[2:]) == bear


def test_the_midline_is_bright_enough_to_measure_from():
    """signal_cards found a near-black midline invisible on a card, which left every
    dot measured from nothing. A table cell is the same background."""
    svg, _ = marks((sr.LegMark("Comm", 50, sr.BULL_HIGH),), 1)
    assert sr.AXIS_RULE in svg


# ── the measured row set ─────────────────────────────────────────────────────

def test_the_card_keeps_one_number_row_and_two_paths():
    """willco reproduces the Commercial Index at rho 1.00 and prints the same cell in
    99.7% of weeks; the Non-Commercial index is its near-mirror at -0.98. Both, plus
    the range-indexed z-score and spec concentration, were measured off the card. A
    row reappearing here is a claim that the measurement changed."""
    keys = {r.key for r in sr.SCORE_ROWS} | {r.key for r in sr.SPARK_ROWS}
    assert keys == {"comm_move", "price", "oi"}


def test_the_anchor_tooltip_names_itself():
    """The levels moved into the leg mark, so no numbered row is the anchor any more.
    The tooltip for a row without a correlation still has to say why."""
    assert "measured against" in sr.row_tooltip(None)


def test_every_other_row_states_what_it_adds():
    for row in sr.SCORE_ROWS[1:] + sr.SPARK_ROWS:
        assert row.rho is not None, f"{row.key} carries no correlation"
        assert abs(row.rho) < 0.7, (
            f"{row.key} at rho {row.rho} mostly restates the anchor")
        assert f"{row.rho:+.2f}" in sr.row_tooltip(row.rho)


# ── the sparkline ────────────────────────────────────────────────────────────

def test_the_endpoint_is_the_range_index_it_replaced():
    """The equivalence the two-rows-into-one collapse rests on: where the dot sits in
    the path IS the reading the number used to carry."""
    values = [10, 14, 9, 22, 31, 18, 25, 40, 12, 28, 33, 20, 26]
    _, pct = sr.sparkline(values)
    expected = calculate_range_index(Series(values), window=len(values)).iloc[-1]
    assert pct == pytest.approx(expected, abs=1)


def test_a_flat_series_draws_nothing():
    """No range means no position within it. A line through the middle of an empty
    range would read as mid-range rather than as no reading at all."""
    assert sr.sparkline([5] * 30) == (None, None)


def test_too_short_a_series_draws_nothing():
    assert sr.sparkline([1, 2, 3]) == (None, None)


def test_missing_observations_are_dropped_not_zeroed():
    svg, pct = sr.sparkline([1, 2, None, 4, 5, 6, 7, float("nan"), 9, 10])
    assert svg is not None
    assert pct == 100  # the last real value is the window high


def test_the_path_is_drawn_inside_its_box():
    svg, _ = sr.sparkline(list(range(20)))
    points = svg.split('points="')[1].split('"')[0].split()
    ys = [float(p.split(",")[1]) for p in points]
    assert min(ys) >= 0 and max(ys) <= sr.SPARK_H


def test_the_path_renders_without_a_graph_or_a_browser():
    svg, _ = sr.sparkline(list(range(20)))
    img = sr.spark_img(svg)
    assert isinstance(img, html.Img)
    assert img.src.startswith("data:image/svg+xml;utf8,")


def test_the_data_uri_carries_no_unescaped_hash():
    """A '#' opens a URI fragment, so one raw hex colour truncates the SVG at that
    point and the cell renders as a broken image with nothing raised anywhere. Caught
    in the browser the first time; pinned here so it cannot come back silently."""
    svg, _ = sr.sparkline(list(range(20)))
    assert "#" not in svg, "the SVG itself must use rgba(), not hex"
    assert "#" not in sr.spark_img(svg).src


def test_the_whole_path_survives_the_uri_encoding():
    """The closing tag is the last thing in the document, so its presence after
    encoding is the cheapest proof that nothing truncated it."""
    svg, _ = sr.sparkline(list(range(20)))
    src = sr.spark_img(svg).src
    assert src.rstrip().endswith("%3C/svg%3E") or src.rstrip().endswith("</svg>")
    assert "polyline" in src and "circle" in src


# ── the gate row ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("state,text,hex_color", [
    (const.SETUP_BULL, "SETUP ↑", BULL_HEX),
    (const.SETUP_BEAR, "SETUP ↓", BEAR_HEX),
    (const.SETUP_NEAR_BULL, "near ↑", BULL_HEX),
    (const.SETUP_NEAR_BEAR, "near ↓", BEAR_HEX),
])
def test_the_gate_row_prints_the_models_own_answer(state, text, hex_color):
    got, style = sr.setup_cell(state, COLORS)
    assert got == text
    assert _is_fill_hue(style, hex_color)


def test_a_near_setup_draws_fainter_than_a_setup():
    _, near = sr.setup_cell(const.SETUP_NEAR_BULL, COLORS)
    _, full = sr.setup_cell(const.SETUP_BULL, COLORS)
    assert _lift(near) < _lift(full)


def test_no_setup_draws_no_block():
    text, style = sr.setup_cell(const.SETUP_NONE, COLORS)
    assert text == sr._EMPTY
    assert "backgroundColor" not in style


# ── the table ────────────────────────────────────────────────────────────────

def _card(reads):
    """What the page renders: the scroll wrapper around the table."""
    return sr.build_table(reads, models.NPF, COLORS)


def _table(reads):
    return _card(reads).children


def _data_rows(table):
    """The rows carrying cells, with the block headings (one colSpan cell) dropped."""
    return [r for r in table.children[1].children
            if isinstance(r, html.Tr) and not getattr(r.children[0], "colSpan", None)]


def test_every_market_gets_one_column_on_every_row():
    reads = [read("6A", comm=94, comm_move=70, nonrept=6, paths={}),
             read("6E", comm=98, comm_move=40, nonrept=30, paths={}),
             read("6J", comm=7, comm_move=20, nonrept=55, paths={})]
    rows = _data_rows(_table(reads))
    # setup chip, the leg mark, the numbered rows, the paths
    assert len(rows) == 2 + len(sr.SCORE_ROWS) + len(sr.SPARK_ROWS)
    for row in rows:
        assert len(row.children) == len(reads) + 1


def test_a_market_with_no_path_still_draws_its_positioning():
    """The price store and the COT store are separate deliveries. A market whose bars
    have not landed must lose its sparklines, not its positioning."""
    rows = _data_rows(_table([read("6A", comm_move=70, paths={},
                                   legs=(sr.LegMark("Comm", 94, sr.BULL_HIGH),))]))
    assert rows[2].children[1].children == "+4"   # the 6wk move survived
    for row in rows[-len(sr.SPARK_ROWS):]:
        assert row.children[1].children == sr._EMPTY


def test_the_header_corner_reserves_the_label_column():
    """`table-layout: fixed` takes every column width from the HEADER row, so the
    corner cell has to carry the label width even though it draws nothing. Without
    it the columns divide evenly and the row labels run under the first market, which
    only shows up once a card has enough columns to squeeze them."""
    header_row = _table([read(s) for s in "ABCDEFGHI"]).children[0].children
    corner, first_market = header_row.children[0], header_row.children[1]
    assert corner.style["width"] == sr._LABEL_WIDTH
    assert "width" not in first_market.style


def test_the_header_names_the_markets():
    header_row = _table([read("6A"), read("GC")]).children[0].children
    # The empty corner, then one link per market: the symbol is the link's text.
    assert [getattr(th.children, "children", th.children)
            for th in header_row.children] == ["", "6A", "GC"]


# ── a card wider than the screen scrolls rather than compressing ─────────────

def test_a_wide_card_scrolls_inside_its_own_wrapper():
    """Nine markets on a phone would be about twenty pixels a column, which runs the
    symbols together and wraps the gate chip. The floor makes the card scroll instead.
    The overflow is on the wrapper and never on the body: a page-level overflow-x is
    what the mobile work had to undo elsewhere here, and it also kills sticky."""
    card = _card([read(s) for s in "ABCDEFGHI"])
    assert card.style["overflowX"] == "auto"
    expected = sr._label_px() + sr._MIN_COL_WIDTH * 9
    assert card.children.style["minWidth"] == f"{expected}px"


def test_a_narrow_card_needs_no_scrolling():
    """Two markets fit any screen, so the floor must stay under a phone's width or
    a two-column card would scroll for no reason."""
    card = _card([read("BTC"), read("ETH")])
    assert int(card.children.style["minWidth"].removesuffix("px")) < 375


def test_the_row_labels_stay_put_while_the_markets_scroll():
    """A horizontally scrolling table whose row names scroll away is unreadable. The
    label needs its own opaque background or the cells pass through it."""
    label = _data_rows(_table([read("6A")]))[1].children[0]
    assert label.style["position"] == "sticky"
    assert label.style["left"] == "0"
    assert label.style["backgroundColor"] == vc.BACKGROUND_COLOR


# ── the net-positions row ────────────────────────────────────────────────────

def _net(comm, lrg=(), sml=()):
    return (sr.NetSeries("Comm", tuple(comm)),
            sr.NetSeries("NonComm", tuple(lrg)),
            sr.NetSeries("NonRept", tuple(sml)))


def _paths(svg):
    """[(stroke, width, [(x, y_from, y_to), ...]), ...] in draw order."""
    out = []
    for d, stroke, width in re.findall(
            r'<path d="([^"]+)" stroke="([^"]+)" stroke-width="([^"]+)"', svg):
        bars = [tuple(float(n) for n in m)
                for m in re.findall(r"M([\d.]+) ([\d.]+)V([\d.]+)", d)]
        out.append((stroke, float(width), bars))
    return out


def test_the_zero_line_is_the_centre_and_the_largest_bar_reaches_the_pad():
    """The Analysis panel's symmetric axis at thumbnail size: zero stays in the
    middle whatever the range, and the window's largest reading sets the scale."""
    svg, _ = sr.net_bars(_net([-10] * 7 + [-40] + [20]))
    mid = sr.NET_H / 2
    assert f'y1="{mid:.1f}" x2=' in svg
    bars = [bar for _, _, path in _paths(svg) for bar in path]
    assert all(y_from == mid for _, y_from, _ in bars)
    assert min(bar[2] for bar in bars) == pytest.approx(mid - (mid - sr.NET_PAD) / 2)
    assert max(bar[2] for bar in bars) == pytest.approx(sr.NET_H - sr.NET_PAD)


def test_only_commercials_are_drawn_and_only_they_set_the_scale():
    """The other legs ride along for the hover and nothing else: a huge
    Non-Commercial reading must not flatten the Commercial bars."""
    alone = sr.net_bars(_net([5] * 8))[0]
    with_specs = sr.net_bars(_net([5] * 8, [-500] * 8, [1] * 8))[0]
    assert _paths(alone) == _paths(with_specs)
    assert len(_paths(alone)) == 2  # the window, then the latest week


def test_the_row_draws_in_the_neutral_ink_and_never_a_palette_colour():
    svg, _ = sr.net_bars(_net([5, -5] * 4))
    strokes = {stroke for stroke, _, _ in _paths(svg)}
    r, g, b = _rgb(sr.NEUTRAL_INK)
    assert strokes == {f"rgba({r}, {g}, {b}, 0.85)", f"rgba({r}, {g}, {b}, 1)"}


def test_the_latest_week_is_the_last_bar_at_full_ink_and_wider():
    svg, _ = sr.net_bars(_net([5] * 7 + [-3]))
    window, latest = _paths(svg)
    assert latest[1] == sr.NET_END_W > window[1]
    assert latest[2][0][0] > window[2][-1][0]
    assert latest[2][0][2] > sr.NET_H / 2  # the -3 points down


def test_a_flat_or_short_net_history_draws_nothing():
    assert sr.net_bars(_net([0] * 8, [50] * 8, [50] * 8)) == (None, None)
    assert sr.net_bars(_net([1, 2], [3, 4], [5, 6])) == (None, None)
    assert sr.net_bars(()) == (None, None)


def test_the_net_row_carries_no_unescaped_hash():
    """The data-URI trap the sparkline and the mark both guard against."""
    svg, _ = sr.net_bars(_net([5] * 8, [-5] * 8, [1] * 8))
    assert "#" not in svg
    assert "#" not in sr.net_img(svg).src


def test_the_row_has_one_height_on_every_card():
    """Fixed, like the sparklines, not scaled to the cell like the marks: a
    two-market card and a nine-market card keep the same row rhythm."""
    svg, _ = sr.net_bars(_net([5] * 8))
    assert sr.net_img(svg).style["height"] == f"{sr.NET_H}px"
    assert sr.NET_H > sr.SPARK_H


def test_all_three_legs_latest_figures_are_on_hover_in_the_rows_own_unit():
    _, latest = sr.net_bars(_net([-61852.4] * 8, [46552.6] * 8, [15299.9] * 8))
    assert latest == "Comm -61,852, NonComm +46,553, NonRept +15,300"
    _, latest = sr.net_bars(_net([-0.22] * 8, [0.165] * 8, [0.054] * 8),
                            as_share=True)
    assert latest == "Comm -22.0%, NonComm +16.5%, NonRept +5.4%"


def _rows(table):
    return table.children.children[1].children


def _label_text(row):
    label = row.children[0].children
    return label[0] if isinstance(label, list) else label


def _is_net(row):
    return str(_label_text(row)).startswith(sr.NET_ROW.label)


def test_the_card_draws_the_net_row_after_the_positioning_rows():
    reads = [read("6A", net=_net([5] * 8, [-5] * 8, [1] * 8)),
             read("6B", net=())]
    rows = _rows(sr.build_table(reads, models.RAW_PF, COLORS))
    index = next(i for i, row in enumerate(rows) if _is_net(row))
    assert _label_text(rows[index - 1]) == sr.SCORE_ROWS[-1].label
    net_row = rows[index]
    assert isinstance(net_row.children[1].children, html.Img)
    assert "Commercials as bars" in net_row.children[1].title
    assert net_row.children[2].children == "·"  # a market with no history


def test_a_card_with_no_net_history_draws_no_net_row():
    rows = _rows(sr.build_table([read("6A")], models.RAW_PF, COLORS))
    assert not any(_is_net(row) for row in rows)


def test_the_net_row_names_its_quantity_in_the_models_basis():
    """"Commercial net contracts" under Raw PF, "% of OI" under NPF: the label
    carries the unit rather than a note beside it, so the row says what it is."""
    reads = [read("6A", net=_net([0.2] * 8, [-0.2] * 8, [0.0] * 8))]
    for model, unit in ((models.RAW_PF, "contracts"), (models.NPF, "% of OI")):
        rows = _rows(sr.build_table(reads, model, COLORS))
        row = next(r for r in rows if _is_net(r))
        assert _label_text(row) == f"Commercial net {unit}"
        assert f"in {unit}" in row.children[1].title


# ── the faint Non-Commercial line ────────────────────────────────────────────

def _line(svg):
    """[(x, y), ...] of the speculator polyline, and its stroke, or (None, None)."""
    m = re.search(r'<polyline points="([^"]+)" fill="none" stroke="([^"]+)" '
                  r'stroke-width="([^"]+)"', svg)
    if not m:
        return None, None, None
    points = [tuple(float(n) for n in pair.split(","))
              for pair in m.group(1).split(" ")]
    return points, m.group(2), float(m.group(3))


def test_the_line_is_the_second_series_on_the_bars_scale():
    comm, specs = [10] * 8, [-5] * 7 + [-20]
    svg, _ = sr.net_bars(_net(comm, specs, [1] * 8), spec_line=True)
    points, _, _ = _line(svg)
    mid, reach = sr.NET_H / 2, sr.NET_H / 2 - sr.NET_PAD
    assert len(points) == 8
    assert points[-1][1] == pytest.approx(mid + reach)  # -20 is the window's largest
    assert points[0][1] == pytest.approx(mid + reach * 5 / 20)
    # The bars share that scale: +10 is half the reach.
    window, _ = _paths(svg)
    assert window[2][0][2] == pytest.approx(mid - reach / 2)


def test_the_line_is_off_unless_asked_for_and_the_card_asks():
    net = _net([5] * 8, [-5] * 8, [1] * 8)
    assert _line(sr.net_bars(net)[0]) == (None, None, None)
    assert _line(sr.net_bars(net, spec_line=True)[0])[0] is not None
    assert sr.SPEC_LINE is True


def test_the_line_is_fainter_and_thinner_than_the_bars():
    svg, _ = sr.net_bars(_net([5] * 8, [-5] * 8, [1] * 8), spec_line=True)
    _, stroke, width = _line(svg)
    r, g, b = _rgb(sr.NEUTRAL_INK)
    assert stroke == f"rgba({r}, {g}, {b}, {sr.SPEC_LINE_ALPHA})"
    assert sr.SPEC_LINE_ALPHA < 0.85
    assert width < sr.NET_BAR_W


def test_the_lines_last_point_is_the_latest_bar_whatever_its_length():
    svg, _ = sr.net_bars(_net([5] * 10, [-5] * 8), spec_line=True)
    points, _, _ = _line(svg)
    window, latest = _paths(svg)
    assert len(points) == 8
    assert points[-1][0] == latest[2][0][0]


def test_a_missing_second_series_draws_bars_alone():
    svg, _ = sr.net_bars((sr.NetSeries("Comm", (5,) * 8),), spec_line=True)
    assert svg is not None
    assert _line(svg) == (None, None, None)


# ── the card's width and its headers ─────────────────────────────────────────

def test_a_small_card_is_capped_rather_than_stretched_to_its_column():
    """Two markets drew 150px cells beside a four-market card's 70px ones."""
    assert sr.card_max_px(2) < sr.card_max_px(4) < sr.card_max_px(9)
    assert sr.card_max_px(12) == sr.CARD_MAX_PX  # the page-wide ceiling still holds
    assert sr.card_max_px(2) - sr._label_px() == 2 * sr._MAX_COL_WIDTH
    assert sr._MAX_COL_WIDTH >= sr.MARK_W  # a mark still gets its full width
    table = sr.build_table([read("6A"), read("6B")], models.RAW_PF, COLORS).children
    assert table.style["maxWidth"] == f"{sr.card_max_px(2)}px"


def test_each_header_links_to_the_markets_oi_alignment_page():
    """The Setups cards' convention: the symbol shows, the name is on hover, and
    the link opens the market's page in a new tab."""
    table = sr.build_table(
        [sr.MarketRead(symbol="6A", asset="Australian Dollar", date="2026-10-20")],
        models.RAW_PF, COLORS).children
    header = table.children[0].children.children[1].children
    assert isinstance(header, html.A)
    assert header.children == "6A"
    assert header.href == "/oi_alignment?asset=Australian%20Dollar"
    assert header.target == "_blank"
    assert "Australian Dollar" in header.title


def test_a_market_with_no_symbol_still_gets_a_header_and_a_link():
    header = sr.market_link(sr.MarketRead(symbol="", asset="Bitcoin"))
    assert header.children == "Bitcoin"
    assert header.href.endswith("asset=Bitcoin")
