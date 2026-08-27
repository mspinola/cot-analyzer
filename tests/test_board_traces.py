"""The Crowdedness Board's layout rules, pinned.

Three things are worth holding here, and none is about pixels.

The first is the colour rule, because it is a deliberate DEPARTURE: on this board
colour follows each cell's own value, where the Strip and the Heatmap colour by the
row's setup state. The departure is only safe while the encoding stays honest, so the
monotonicity (further from neutral is never fainter) and the pole assignment (above
neutral is the bull hue, below is the bear hue) are pinned rather than trusted.

The second is the verdict bridge: the left-edge marker is the ONLY place the model's
vocabulary appears, it draws full setups alone, and a NEAR state must not produce one.

The third is the ordering contract. ORDER_FLAT is the page's "one gradient" claim, so
it must sort the whole board by crowding score with no class furniture at all, and a
market with no readable window must be dropped AND counted, never drawn empty.
"""
import cotmetrics.constants as const
import cotmetrics.models as models

import components.board_traces as bt
from components.plot_colors import GridColors, relative_luminance

COLORS = GridColors(bull="#34D399", bear="#FF4D4D",
                    bull_near="rgba(52,211,153,0.5)",
                    bear_near="rgba(255,77,77,0.5)")

BG = "#1a1a1a"


def read(asset="Gold", asset_class="Metals", windows=(80, 70, 60, 55),
         state=const.SETUP_NONE, move=4.0, path=(40, 55, 60),
         history_weeks=400, start="2000-03-14", symbol="GC"):
    return bt.MarketRead(asset=asset, asset_class=asset_class, windows=windows,
                         symbol=symbol, history_weeks=history_weeks, start=start,
                         move=move, path=path, state=state, date="2026-08-18")


# ── the window vocabulary ─────────────────────────────────────────────────────

def test_window_constants_are_aligned():
    """The three tuples are read by index in the figure, the hover and the page's
    data join; a length drift would mislabel a column silently."""
    assert len(bt.WINDOW_WEEKS) == len(bt.WINDOW_LABELS) == len(bt.WINDOW_DESC)
    # Exactly one full-history window, and it is the last column: the page's data
    # layer and the caption both assume it.
    assert [w for w in bt.WINDOW_WEEKS if w is None] == [None]
    assert bt.WINDOW_WEEKS[-1] is None


# ── the colour rule ───────────────────────────────────────────────────────────

def _distance(a, b):
    a, b = a.lstrip("#"), b.lstrip("#")
    return sum(abs(int(a[i:i + 2], 16) - int(b[i:i + 2], 16)) for i in (0, 2, 4))


def test_neutral_deadband_keeps_the_resting_fill():
    base = bt.cell_base(BG)
    for value in (50, 50 + bt.CELL_DEADBAND, 50 - bt.CELL_DEADBAND):
        assert bt.cell_fill(value, COLORS, BG) == base


def test_fill_is_monotonic_away_from_neutral():
    """Further from neutral is never fainter. This is what makes the sweep honest:
    a reader ranks cells by saturation, so saturation must rank with the value."""
    base = bt.cell_base(BG)
    for values in ([58, 70, 85, 100], [42, 30, 15, 0]):
        distances = [_distance(bt.cell_fill(v, COLORS, BG), base) for v in values]
        assert distances == sorted(distances), values
        assert distances[0] > 0  # past the deadband, a cell must move off the base


def test_fill_takes_the_row_side_pole():
    hot_bull = bt.cell_fill(98, COLORS, BG)
    hot_bear = bt.cell_fill(2, COLORS, BG)
    assert _distance(hot_bull, COLORS.bull) < _distance(hot_bull, COLORS.bear)
    assert _distance(hot_bear, COLORS.bear) < _distance(hot_bear, COLORS.bull)


def test_fill_never_reaches_the_pure_pole():
    """CELL_MAX_BLEND caps the wash; the full verdict hue is text-strength colour
    and a slab of it per cell reads as glare (the Strip's STEM_ALPHA observation)."""
    assert bt.cell_fill(100, COLORS, BG).lower() != COLORS.bull.lower()
    assert bt.cell_fill(0, COLORS, BG).lower() != COLORS.bear.lower()


def test_missing_window_has_no_fill():
    assert bt.cell_fill(None, COLORS, BG) is None


def test_text_ink_follows_fill_luminance():
    dark, light = "#101418", "#e0f0e0"
    assert relative_luminance(bt.cell_text_colour(dark)) > 0.5
    assert relative_luminance(bt.cell_text_colour(light)) < 0.1


def test_delta_direction_colours():
    assert bt.delta_colour(bt.DELTA_FLAT, COLORS) == COLORS.dim
    assert bt.delta_colour(None, COLORS) == COLORS.dim
    assert bt.delta_colour(bt.DELTA_FLAT + 1, COLORS) == COLORS.bull
    assert bt.delta_colour(-(bt.DELTA_FLAT + 1), COLORS) == COLORS.bear


# ── the verdict bridge ────────────────────────────────────────────────────────

def test_only_full_setups_get_a_marker():
    assert bt._verdict_marker(const.SETUP_BULL, COLORS) == (COLORS.bull,
                                                           "triangle-up")
    assert bt._verdict_marker(const.SETUP_BEAR, COLORS) == (COLORS.bear,
                                                           "triangle-down")
    for state in (const.SETUP_NEAR_BULL, const.SETUP_NEAR_BEAR, const.SETUP_NONE):
        assert bt._verdict_marker(state, COLORS) is None


# ── ordering ──────────────────────────────────────────────────────────────────

def test_crowding_score_ignores_unfilled_windows():
    assert bt.crowding_score(read(windows=(80, None, 60, None))) == 70
    assert bt.crowding_score(read(windows=(None, None, None, None))) is None


def test_class_order_groups_and_sorts_by_score():
    rows, skipped = bt.build_rows([
        read(asset="Silver", asset_class="Metals", windows=(20, 20, 20, 20)),
        read(asset="Gold", asset_class="Metals", windows=(90, 90, 90, 90)),
        read(asset="Corn", asset_class="Grains", windows=(50, 50, 50, 50)),
    ], order=bt.ORDER_CLASS)
    assert skipped == []
    kinds = [r.kind for r in rows]
    assert kinds == ["class", "market", "market", "spacer", "class", "market"]
    # Classes in ARRIVAL order (the Signal Matrix's class order, which is how every
    # other page presents the book), markets descending by score inside each.
    assert [r.label for r in rows] == ["Metals", "Gold", "Silver",
                                      "", "Grains", "Corn"]


def test_flat_order_is_one_gradient():
    rows, _ = bt.build_rows([
        read(asset="Silver", asset_class="Metals", windows=(20, 20, 20, 20)),
        read(asset="Corn", asset_class="Grains", windows=(50, 50, 50, 50)),
        read(asset="Gold", asset_class="Metals", windows=(90, 90, 90, 90)),
    ], order=bt.ORDER_FLAT)
    assert all(r.kind == "market" for r in rows)
    assert [r.label for r in rows] == ["Gold", "Corn", "Silver"]


def test_alpha_order_keeps_classes_and_sorts_names():
    rows, _ = bt.build_rows([
        read(asset="Silver", asset_class="Metals", windows=(20, 20, 20, 20)),
        read(asset="Gold", asset_class="Metals", windows=(90, 90, 90, 90)),
    ], order=bt.ORDER_ALPHA)
    assert [r.label for r in rows] == ["Metals", "Gold", "Silver"]


def test_unreadable_market_is_dropped_and_counted():
    rows, skipped = bt.build_rows([
        read(asset="Gold"),
        read(asset="MSCI EAFE", windows=(None, None, None, None)),
    ])
    assert skipped == ["MSCI EAFE"]
    assert [r.label for r in rows if r.kind == "market"] == ["Gold"]


# ── the figure ────────────────────────────────────────────────────────────────

def _cell_rects(fig):
    """The cell fills: data-referenced rects (header bands are paper-referenced)."""
    return [s for s in fig.layout.shapes
            if s.type == "rect" and s.xref == "x"]


def test_one_rect_per_filled_cell():
    rows, _ = bt.build_rows([
        read(asset="Gold", windows=(80, 70, 60, 55)),
        read(asset="Palladium", windows=(30, None, 25, None)),
    ])
    fig = bt.build_figure(rows, models.DEFAULT_MODEL, COLORS)
    assert len(_cell_rects(fig)) == 6  # 4 filled windows + 2 filled windows


def test_y_axis_runs_top_down_and_labels_live_in_plot():
    """Identity is three in-plot columns (bold symbol, muted name, dim inception
    tag) plus a heading row larger than any market text, not y tick labels. The
    tick route capped the class headings at market-row size, which is the
    too-small-to-orient-by failure this replaced."""
    rows, _ = bt.build_rows([read(asset="Gold", symbol="GC"),
                             read(asset="Silver", symbol="SI",
                                  windows=(20, 20, 20, 20))])
    fig = bt.build_figure(rows, models.DEFAULT_MODEL, COLORS)
    lo, hi = fig.layout.yaxis.range
    assert lo > hi  # reversed: row 0 at the top
    assert fig.layout.yaxis.showticklabels is False

    text_traces = {tuple(t.text) for t in fig.data if t.mode == "text"}
    assert ("<b>GC</b>", "<b>SI</b>") in text_traces
    assert ("Gold", "Silver") in text_traces
    assert ("'00", "'00") in text_traces
    heading = [t for t in fig.data
               if t.mode == "text" and tuple(t.text) == ("<b>METALS</b>",)]
    assert len(heading) == 1
    market_text_sizes = [t.textfont.size for t in fig.data
                         if t.mode == "text" and t.text
                         and t.text[0] in ("<b>GC</b>", "Gold")]
    assert heading[0].textfont.size > max(market_text_sizes)


def test_since_tag_is_a_two_digit_year_or_nothing():
    assert bt.since_tag(read(start="2000-03-14")) == "'00"
    assert bt.since_tag(read(start=None)) == ""


def test_spark_maps_high_values_above_the_midline():
    """The y axis is reversed, so a path ending high on the index must end at a
    SMALLER y than its row centre. Getting this backwards flips every sparkline."""
    row_y = 1  # header at 0, market at 1
    rows, _ = bt.build_rows([read(path=(50, 90))])
    assert rows[row_y].kind == "market"
    xs, ys = bt._spark_points(rows[row_y].read, row_y)
    assert ys[-1] < row_y  # high index, smaller y
    xs, ys = bt._spark_points(read(path=(50, 10)), row_y)
    assert ys[-1] > row_y


def test_verdict_trace_only_when_a_full_setup_exists():
    quiet, _ = bt.build_rows([read(state=const.SETUP_NEAR_BULL)])
    lit, _ = bt.build_rows([read(state=const.SETUP_BULL)])
    model = models.DEFAULT_MODEL

    def verdict_points(fig):
        return [t for t in fig.data
                if t.mode == "markers" and t.x and t.x[0] == bt.VERDICT_X]

    assert verdict_points(bt.build_figure(quiet, model, COLORS)) == []
    assert len(verdict_points(bt.build_figure(lit, model, COLORS))) == 1


def test_full_history_hover_names_the_span():
    """The Full column is the one whose window differs per market, so its hover must
    say what it actually covered rather than letting four columns read as uniform."""
    r = read()
    text = bt.cell_hover(r, len(bt.WINDOW_WEEKS) - 1)
    assert "400 weekly reports" in text
    assert "2000-03-14" in text
