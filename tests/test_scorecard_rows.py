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
    return sr.MarketRead(symbol=symbol, asset=symbol, state=state,
                         scores=scores, paths=paths, date="2026-10-20")


def _rgb(hex_color):
    h = str(hex_color).lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _distance(a, b):
    return sum((x - y) ** 2 for x, y in zip(_rgb(a), _rgb(b))) ** 0.5


def _is_hue(style, hex_color):
    """Which pole the cell leans toward.

    A fill is the pole composited over the page, so it is never equal to the pole.
    Asking which pole it is NEARER keeps this independent of the blend formula and
    of any one palette's hues.
    """
    fill = style.get("backgroundColor")
    if fill is None:
        return False
    other = BEAR_HEX if hex_color == BULL_HEX else BULL_HEX
    return _distance(fill, hex_color) < _distance(fill, other)


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

def test_a_low_non_reportable_reading_prints_negative_and_draws_bullish():
    """THE invariant. Small specs washed out is the bullish side under positioning
    fade, so the cell reads -9 and draws the bull hue. Flipping the number to make
    sign and colour agree is what this card deliberately does not do."""
    row = next(r for r in sr.SCORE_ROWS if r.key == "nonrept")
    assert row.direction == sr.BULL_LOW
    value = sr.score(6)
    assert sr.cell_text(value) == "-9"
    assert _is_hue(sr.cell_style(value, row.direction, COLORS), BULL_HEX)


def test_a_high_non_reportable_reading_prints_positive_and_draws_bearish():
    value = sr.score(94)
    assert sr.cell_text(value) == "+9"
    assert _is_hue(sr.cell_style(value, sr.BULL_LOW, COLORS), BEAR_HEX)


def test_the_anchor_row_is_the_one_where_sign_and_colour_agree():
    assert _is_hue(sr.cell_style(9, sr.BULL_HIGH, COLORS), BULL_HEX)
    assert _is_hue(sr.cell_style(-9, sr.BULL_HIGH, COLORS), BEAR_HEX)


def test_colour_weight_follows_magnitude_not_sign():
    """Further from neutral is never fainter. The sweep is only honest if that holds
    on both poles, so check each against the page background rather than each other:
    the two hues sit at different distances from it to begin with."""
    for direction_hue in (sr.BULL_HIGH, sr.BULL_LOW):
        for value in (2, 6):
            assert (_lift(sr.cell_style(value, direction_hue, COLORS))
                    < _lift(sr.cell_style(value + 4, direction_hue, COLORS)))


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
def test_a_number_is_legible_on_its_own_fill(palette_name, value, direction):
    """The bug this pins: ink was chosen by how far the value sat from neutral, so
    the brightest cells printed white on near-white. The shipped palettes put their
    bull slot anywhere from 0.28 (Solarized) to 0.72 luminance (Vibrant, Cyberpunk,
    CMR), and the rule happened to read correctly only on the darkest one, which is
    the palette the design mock used. Every palette, both poles, worst-case weight."""
    colors = grid_colors(viz_config.get_palette(palette_name))
    style = sr.cell_style(value, direction, colors)
    assert _contrast(style["color"], style["backgroundColor"]) >= FILLED_FLOOR, (
        f"{palette_name}: {style['color']} on {style['backgroundColor']}")


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


# ── the measured row set ─────────────────────────────────────────────────────

def test_the_duplicate_rows_stayed_off_the_card():
    """willco reproduces the Commercial Index at rho 1.00 and prints the same cell in
    99.7% of weeks; the Non-Commercial index is its near-mirror at -0.98. Both, plus
    the range-indexed z-score and spec concentration, were measured off the card. A
    row reappearing here is a claim that the measurement changed."""
    keys = {r.key for r in sr.SCORE_ROWS} | {r.key for r in sr.SPARK_ROWS}
    assert keys == {"comm", "comm_move", "nonrept", "price", "oi"}


def test_the_anchor_row_carries_no_correlation_with_itself():
    anchor = sr.SCORE_ROWS[0]
    assert anchor.key == "comm"
    assert anchor.rho is None
    assert "measured against" in sr.row_tooltip(anchor.rho)


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
    assert _is_hue(style, hex_color)


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
    assert len(rows) == 1 + len(sr.SCORE_ROWS) + len(sr.SPARK_ROWS)
    for row in rows:
        assert len(row.children) == len(reads) + 1


def test_a_market_with_no_path_still_draws_its_scores():
    """The price store and the COT store are separate deliveries. A market whose bars
    have not landed must lose its sparkline, not its positioning row."""
    rows = _data_rows(_table([read("6A", comm=94, comm_move=70, nonrept=6, paths={})]))
    scored = rows[1:1 + len(sr.SCORE_ROWS)]
    assert [r.children[1].children for r in scored] == ["+9", "+4", "-9"]
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
    assert [th.children for th in header_row.children] == ["", "6A", "GC"]


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
