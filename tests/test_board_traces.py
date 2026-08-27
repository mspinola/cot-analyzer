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

def _alpha(rgba):
    return float(rgba.rstrip(")").rsplit(",", 1)[1])


def test_chip_tiers_differ_by_weight_alone():
    """Same words as the Active Setups strip, same hue per side, and the NEAR tier
    separated from SETUP by alpha only: anything louder would out-shout the cells."""
    full = bt.verdict_chip(const.SETUP_BULL, COLORS)
    near = bt.verdict_chip(const.SETUP_NEAR_BULL, COLORS)
    assert full[0] == "SETUP" and near[0] == "NEAR"
    assert full[3] == COLORS.bull            # full tier's ink is the pole itself
    assert near[3] == COLORS.bull_near
    assert _alpha(near[1]) < _alpha(full[1])  # fill: near is the fainter one
    assert _alpha(near[2]) < _alpha(full[2])  # border too
    bear = bt.verdict_chip(const.SETUP_BEAR, COLORS)
    assert bear[0] == "SETUP" and bear[3] == COLORS.bear
    assert bt.verdict_chip(const.SETUP_NONE, COLORS) is None


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
    """The cell fills: data-referenced rounded paths with no border (chips are
    paths too, but carry a 1px border; header bands are paper-referenced rects)."""
    return [s for s in fig.layout.shapes
            if s.type == "path" and s.xref == "x" and not s.line.width]


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
    names = [t for t in fig.data if t.mode == "text"
             and t.text and t.text[0].startswith("Gold")]
    assert len(names) == 1
    # The inception tag rides inside the name string as a styled span, so it hugs
    # the name rather than sitting in a fixed column against the cells.
    assert all("'00" in text for text in names[0].text)
    heading = [t for t in fig.data
               if t.mode == "text" and tuple(t.text) == ("<b>METALS</b>",)]
    assert len(heading) == 1
    market_text_sizes = [t.textfont.size for t in fig.data
                         if t.mode == "text" and t.text
                         and t.text[0] in ("<b>GC</b>", names[0].text[0])]
    assert heading[0].textfont.size > max(market_text_sizes)


def test_since_tag_is_a_two_digit_year_or_nothing():
    assert bt.since_tag(read(start="2000-03-14")) == "'00"
    assert bt.since_tag(read(start=None)) == ""


def test_name_label_carries_the_tag_as_a_styled_span():
    label = bt.name_label(read(asset="Gold", start="2000-03-14"))
    assert label.startswith("Gold <span style=")
    assert "'00</span>" in label
    assert bt.name_label(read(asset="Gold", start=None)) == "Gold"


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


def test_both_chip_tiers_draw_and_a_quiet_row_draws_neither():
    model = models.DEFAULT_MODEL
    chip_x = (bt.CHIP_X0 + bt.CHIP_X1) / 2

    def chip_words(state):
        rows, _ = bt.build_rows([read(state=state)])
        fig = bt.build_figure(rows, model, COLORS)
        return [t.text[0] for t in fig.data
                if t.mode == "text" and t.x and t.x[0] == chip_x]

    assert chip_words(const.SETUP_BULL) == ["SETUP"]
    assert chip_words(const.SETUP_NEAR_BEAR) == ["NEAR"]
    assert chip_words(const.SETUP_NONE) == []


def test_full_history_hover_names_the_span():
    """The Full column is the one whose window differs per market, so its hover must
    say what it actually covered rather than letting four columns read as uniform."""
    r = read()
    text = bt.cell_hover(r, len(bt.WINDOW_WEEKS) - 1)
    assert "400 weekly reports" in text
    assert "2000-03-14" in text
