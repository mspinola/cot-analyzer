"""The Crowding Strip draws the same verdicts the Signal Matrix does.

Two things are worth holding here, and neither is about pixels.

The first is the model/column join. `strip_traces.LEG_COLUMNS` maps a model's legs onto
the display names `get_matrix_data` uses, and nothing in the type system connects the
two. A model added without an entry would not raise: `build_rows` would draw the
commercial bar and silently omit a leg the gate reads, which is exactly the class of
error this app has already shipped once (movers.py naming the raw columns while the
model gated on the normalized twins).

The second is that colour follows the ROW's setup state rather than each bar's own
level. That looks wrong from the outside, so it is pinned: Orange Juice at (96, 0, 100)
is through two gates and blocked by the third, and its bar must be dim despite sitting
deep inside the bullish band.
"""
import cotmetrics.constants as const
import cotmetrics.models as models
import pandas as pd
import pytest

import components.strip_traces as st
from components.plot_colors import GridColors

COLORS = GridColors(bull="#00FF00", bear="#FF4D4D",
                    bull_near="rgba(0,255,0,0.5)", bear_near="rgba(255,77,77,0.5)")

# Commercials, Large Specs, Small Specs, price, open interest: the slot order every
# panel in plot_traces already draws from.
PALETTE = ["#F87171", "#60A5FA", "#FBBF24", "#34D399", "#ABB8C9"]


def matrix_row(asset, asset_class, comm, lrg, sml, state_cls=const.SETUP_NONE,
               state_npf=const.SETUP_NONE, is_equity=False, move=None):
    """One `get_matrix_data` record, named the way that function names its columns."""
    return {
        "Asset Class": asset_class, "Asset": asset,
        "Comm Index": comm, "Lrg Index": lrg, "Sml Index": sml,
        # The normalized twins carry their own values in the real frame. Same numbers
        # here keeps the fixtures readable; no test compares the two bases.
        "Comm Index Norm": comm, "Sml Index Norm": sml,
        const.SETUP_CLS_COL: state_cls, const.SETUP_NPF_COL: state_npf,
        const.IS_EQUITY_COL: is_equity, "Date": "2026-08-18",
        "Comm Move": move, "Comm Move Norm": move,
    }


def frame(*rows):
    return pd.DataFrame(list(rows))


# ── the model/column join ─────────────────────────────────────────────────────

@pytest.mark.parametrize("model", models.MODELS, ids=lambda m: m.key)
def test_every_model_can_be_drawn(model):
    """A model with no entry here would draw a blank strip, or drop a gated leg."""
    assert model.key in st.LEG_COLUMNS
    assert model.key in st.SETUP_COLUMN
    cols = st.LEG_COLUMNS[model.key]
    assert "comm" in cols
    for leg in model.spec_legs:
        assert leg in cols, f"{model.key} gates on {leg} but the strip cannot draw it"
        assert leg in st.LEG_LABELS


def test_npf_draws_no_large_spec_leg():
    """The CS gate does not read Large Specs, so the NPF strip must not imply it did."""
    rows, _ = st.build_rows(
        frame(matrix_row("Gold", "Metals", 90, 10, 12)), models.NPF)
    market = [r for r in rows if r.kind == "market"][0]
    assert [leg for leg, _, _ in market.legs] == [models.LEG_SMALL]


def test_raw_pf_draws_both_spec_legs():
    rows, _ = st.build_rows(
        frame(matrix_row("Gold", "Metals", 90, 10, 12)), models.RAW_PF)
    market = [r for r in rows if r.kind == "market"][0]
    assert [leg for leg, _, _ in market.legs] == [models.LEG_LARGE, models.LEG_SMALL]


# ── which legs count as helping the gate ──────────────────────────────────────

def test_a_spec_leg_counts_only_when_opposed_and_through_its_own_gate():
    m = models.RAW_PF
    assert st.is_gate_leg(100, 0, m, is_equity=False)      # comm long, spec short
    assert not st.is_gate_leg(100, 50, m, is_equity=False)  # spec mid-range
    assert not st.is_gate_leg(100, 100, m, is_equity=False)  # spec on the same side
    assert st.is_gate_leg(0, 100, m, is_equity=False)      # the bear mirror
    assert not st.is_gate_leg(50, 0, m, is_equity=False)   # commercials not extreme


def test_equity_spec_legs_never_count():
    """`utils.is_setup` decides an equity setup on Commercials alone, so lighting an
    equity's spec leg would claim it was consulted. The Heatmap guards the same way."""
    assert not st.is_gate_leg(100, 0, models.RAW_PF, is_equity=True)


# ── colour is the row's verdict, position is the level ────────────────────────

def test_a_blocked_extreme_draws_the_faint_neutral_grey():
    """Orange Juice at (96, 0, 100): two legs through, Small Specs blocking outright.
    Its lollipop sits deep in the bull band but takes the faint neutral grey, not a
    verdict colour — the value is real, the verdict is withheld. Grey specifically:
    the quiet tier wore the Commercial red for a while, and that red is the bear
    verdict's own hue family, so every quiet row whispered bearish."""
    rows, _ = st.build_rows(
        frame(matrix_row("Orange Juice", "Softs", 96, 0, 100)), models.RAW_PF)
    market = [r for r in rows if r.kind == "market"][0]
    assert market.comm >= models.RAW_PF.high      # position is inside the bull band
    assert st._verdict_colour(market, COLORS) is None
    assert st._mark_colour(market, COLORS, PALETTE) == COLORS.dim


def test_a_full_setup_draws_the_verdict_colour():
    rows, _ = st.build_rows(
        frame(matrix_row("Canadian Dollar", "FX", 100, 0, 0,
                         state_cls=const.SETUP_BULL)), models.RAW_PF)
    market = [r for r in rows if r.kind == "market"][0]
    assert st._mark_colour(market, COLORS, PALETTE) == COLORS.bull


def test_a_near_setup_draws_the_faded_colour():
    rows, _ = st.build_rows(
        frame(matrix_row("Cocoa", "Softs", 3, 100, 80,
                         state_cls=const.SETUP_NEAR_BEAR)), models.RAW_PF)
    market = [r for r in rows if r.kind == "market"][0]
    assert st._mark_colour(market, COLORS, PALETTE) == COLORS.bear_near


def test_each_model_reads_its_own_verdict_column():
    """The two bands are independent, so a row can be an NPF setup and no CLS setup."""
    df = frame(matrix_row("Coffee", "Softs", 85, 40, 15,
                          state_cls=const.SETUP_NONE, state_npf=const.SETUP_BULL))
    npf = [r for r in st.build_rows(df, models.NPF)[0] if r.kind == "market"][0]
    raw = [r for r in st.build_rows(df, models.RAW_PF)[0] if r.kind == "market"][0]
    assert st._mark_colour(npf, COLORS, PALETTE) == COLORS.bull
    assert st._verdict_colour(raw, COLORS) is None


# ── grouping, ordering and what gets left out ─────────────────────────────────

def test_classes_get_a_header_and_markets_sort_by_crowding_within_them():
    df = frame(
        matrix_row("Gold", "Metals", 40, 50, 50),
        matrix_row("Copper", "Metals", 98, 2, 4),
        matrix_row("Silver", "Metals", 8, 90, 88),
        matrix_row("Euro", "FX", 55, 50, 50),
    )
    rows, _ = st.build_rows(df, models.RAW_PF)
    metals = [r.label for r in rows
              if r.asset_class == "Metals" and r.kind != "spacer"]
    assert metals == ["Metals", "Copper", "Gold", "Silver"]
    assert [r.kind for r in rows if r.asset_class == "Metals"][0] == "class"
    assert sum(1 for r in rows if r.kind == "class") == 2


def test_alphabetical_order_is_available():
    df = frame(
        matrix_row("Gold", "Metals", 40, 50, 50),
        matrix_row("Copper", "Metals", 98, 2, 4),
    )
    rows, _ = st.build_rows(df, models.RAW_PF, sort_by_index=False)
    assert [r.label for r in rows if r.kind == "market"] == ["Copper", "Gold"]


def test_markets_with_no_index_are_reported_rather_than_dropped_silently():
    """A strip showing 44 of 47 markets without saying so reads as a whole board."""
    df = frame(
        matrix_row("Gold", "Metals", 40, 50, 50),
        matrix_row("Lumber", "Softs", None, None, None),
    )
    rows, skipped = st.build_rows(df, models.RAW_PF)
    assert skipped == ["Lumber"]
    assert [r.label for r in rows if r.kind == "market"] == ["Gold"]


# ── the figure ────────────────────────────────────────────────────────────────

def test_the_figure_bands_and_ticks_come_from_the_model():
    """Ticked at the gate values, so a reader can place a bar against the rule that
    decides. The printed report this replaces draws the scale with no ticks at all."""
    df = frame(matrix_row("Gold", "Metals", 40, 50, 50))
    for model in models.MODELS:
        rows, _ = st.build_rows(df, model)
        fig = st.build_figure(rows, model, COLORS, PALETTE)
        ticks = list(fig.layout.xaxis.tickvals)
        assert ticks == [0, model.low, const.INDEX_NEUTRAL, model.high, 100]
        # x-referenced rects are the gate bands; paper-referenced ones are the class
        # header bands, which have nothing to do with the model.
        rects = [s for s in fig.layout.shapes
                 if s.type == "rect" and s.xref == "x"]
        assert {(r.x0, r.x1) for r in rects} == {(0, model.low), (model.high, 100)}


def test_stems_diverge_from_neutral_rather_than_from_zero():
    """The stem's length is distance from neutral and its sign is direction. Zero is
    not the baseline: 0 on this index is maximally short, not the absence of a
    position."""
    df = frame(
        matrix_row("Copper", "Metals", 98, 2, 4),
        matrix_row("Gold", "Metals", 8, 90, 88),
    )
    rows, _ = st.build_rows(df, models.RAW_PF)
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)
    stem = next(t for t in fig.data if t.type == "bar")
    assert list(stem.base) == [const.INDEX_NEUTRAL] * 2
    assert list(stem.x) == [98 - const.INDEX_NEUTRAL, 8 - const.INDEX_NEUTRAL]
    assert stem.width == st.STEM_WIDTH            # a hairline, not the old half-row slab


def test_the_head_sits_at_the_value_itself():
    df = frame(
        matrix_row("Copper", "Metals", 98, 2, 4, state_cls=const.SETUP_BULL),
        matrix_row("Gold", "Metals", 8, 90, 88, state_cls=const.SETUP_BEAR),
    )
    rows, _ = st.build_rows(df, models.RAW_PF)
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)
    heads = next(t for t in fig.data
                 if t.type == "scatter" and t.marker.symbol == "circle" and t.hovertext)
    assert list(heads.x) == [98, 8]


def test_the_head_is_drawn_at_full_strength_and_the_stem_is_not():
    """The head is the datum; the stem is a run of pixels of the same colour, and forty
    of them at full strength would glare the way the old filled bars did."""
    df = frame(matrix_row("Copper", "Metals", 98, 2, 4, state_cls=const.SETUP_BULL))
    rows, _ = st.build_rows(df, models.RAW_PF)
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)
    stem = next(t for t in fig.data if t.type == "bar")
    heads = next(t for t in fig.data
                 if t.type == "scatter" and t.marker.symbol == "circle" and t.hovertext)
    assert stem.marker.color[0] == st._fill(COLORS.bull)
    assert heads.marker.color[0] == COLORS.bull


def test_the_legend_names_the_lollipop():
    groups = st.legend_items(models.RAW_PF, COLORS, PALETTE)
    assert groups[0][0] == "Lollipop: Commercial index"


def test_no_text_column_repeats_what_the_bar_already_says():
    """The index value and the gate verdict each had a fixed column, and each was a
    second copy of something the picture carried: position against the banded axis, and
    bar colour. They are on the hover instead, which a printed page could not do."""
    df = frame(matrix_row("Copper", "Metals", 100, 2, 4,
                          state_cls=const.SETUP_BULL))
    rows, _ = st.build_rows(df, models.RAW_PF)
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)
    assert not [t for t in fig.data if t.type == "scatter" and t.mode == "text"]
    assert st.AXIS_MAX < 110   # no room reserved for columns that no longer exist
    marks = next(t for t in fig.data if t.hovertext)
    assert "100" in marks.hovertext[0] and "SETUP" in marks.hovertext[0]


def test_the_legend_keys_the_colours_and_the_legs():
    groups = st.legend_items(models.RAW_PF, COLORS, PALETTE)
    named = [label for _, entries in groups for label, _, _ in entries]
    assert named == ["Bull setup", "Bear setup", "Near", "No setup", "6w ago",
                     "Large Specs", "Small Traders"]
    # "No setup" is keyed because it is a COLOUR here, not an absence: the Commercial
    # series colour, which a reader must not mistake for a verdict. The key is faded
    # exactly as the drawn mark is — a full-strength swatch would promise a red the
    # plot never draws.
    no_setup = [colour for _, entries in groups
                for label, colour, _ in entries if label == "No setup"]
    assert no_setup == [COLORS.dim]


def test_the_figure_grows_with_the_board():
    small = frame(matrix_row("Gold", "Metals", 40, 50, 50))
    big = frame(*[matrix_row(f"M{i}", "Metals", 40, 50, 50) for i in range(20)])
    h_small = st.figure_height(st.build_rows(small, models.RAW_PF)[0])
    h_big = st.figure_height(st.build_rows(big, models.RAW_PF)[0])
    assert h_big > h_small
    assert h_big - h_small == 19 * st.ROW_PX


def test_an_empty_board_still_draws():
    rows, skipped = st.build_rows(frame(), models.RAW_PF)
    assert rows == [] and skipped == []
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)
    assert fig.layout.height == st.figure_height([])


def test_a_tick_takes_its_leg_colour_and_its_rows_tier_as_opacity():
    """Colour is which leg, opacity is the ROW's tier: one channel per variable.

    The leg colours are the app's, by palette slot, so blue is Large Specs on this page
    exactly as it is on every stacked panel. An earlier version coloured a gating tick
    by the row's direction, which spent colour on something the bar beside it already
    says and left the two legs indistinguishable from each other. Opacity then carried
    the leg's own gate state for a while, which spent IT on something the axis already
    says — a gating leg sits at its own extreme, which is where its tick is drawn — so
    it now follows the row like every other mark: verdict rows light whole.
    """
    large = st._leg_colour(models.LEG_LARGE, True, PALETTE)
    small = st._leg_colour(models.LEG_SMALL, True, PALETTE)
    assert large != small
    assert large.startswith("rgba(96, 165, 250")     # PALETTE[1], Large Specs
    assert small.startswith("rgba(251, 191, 36")     # PALETTE[2], Small Specs
    quiet = st._leg_colour(models.LEG_LARGE, False, PALETTE)
    assert quiet.startswith("rgba(96, 165, 250")     # same leg, same colour
    assert quiet != large                            # fainter, on a row with no verdict


def test_ticks_light_with_their_row_not_with_their_own_gate():
    """Copper is a bull setup with Large Specs at 40 — nowhere near ITS gate — and its
    tick still draws lit, because the row is worth inspecting whole. Gold's leg sits at
    an extreme, and draws quiet, because its row is quiet."""
    df = frame(
        matrix_row("Copper", "Metals", 98, 40, 2, state_cls=const.SETUP_BULL),
        matrix_row("Gold", "Metals", 55, 2, 50),
    )
    rows, _ = st.build_rows(df, models.RAW_PF)
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)
    large = next(t for t in fig.data
                 if t.type == "scatter" and t.marker.symbol == "line-ns"
                 and list(t.x) == [40, 2])
    assert list(large.marker.color) == [
        st._leg_colour(models.LEG_LARGE, True, PALETTE),
        st._leg_colour(models.LEG_LARGE, False, PALETTE)]


def test_stem_fills_are_knocked_back_but_the_head_beside_them_is_not():
    """`grid_colors` picks colours for 11px grid text. A stem is a run of pixels of it,
    so the value that reads as legible in a table reads as glare here."""
    assert st._fill("#FF4D4D") == f"rgba(255, 77, 77, {st.STEM_ALPHA})"
    # The near tier arrives already translucent; fading it again would lose it.
    assert st._fill("rgba(255,77,77,0.5)") == "rgba(255,77,77,0.5)"


def test_the_scale_is_drawn_at_both_ends_of_a_tall_strip():
    """A 50-row strip is taller than the window, so an axis only at the bottom is off
    screen for most of the reading."""
    df = frame(*[matrix_row(f"M{i}", "Metals", 40, 50, 50) for i in range(40)])
    rows, _ = st.build_rows(df, models.NPF)
    fig = st.build_figure(rows, models.NPF, COLORS, PALETTE)
    assert fig.layout.xaxis.side == "bottom"
    assert fig.layout.xaxis2.side == "top"
    assert list(fig.layout.xaxis2.tickvals) == list(fig.layout.xaxis.tickvals)


def test_the_legend_says_which_mark_is_which_leg():
    """Read cold, the figure has two kinds of mark and the numbers have no header. The
    first review of it asked all three questions in a row: what are the numbers, what
    are the ticks, is this Commercials only. The group titles are the answer."""
    titles = [title for title, _ in st.legend_items(models.RAW_PF, COLORS, PALETTE)]
    assert titles == ["Lollipop: Commercial index",
                      "Ticks: the legs this gate also reads"]


# ── filters ───────────────────────────────────────────────────────────────────

BOARD = (
    ("Copper", "Metals", 98, 2, 4, const.SETUP_BULL),
    ("Gold", "Metals", 92, 8, 40, const.SETUP_NEAR_BULL),
    ("Silver", "Metals", 55, 50, 50, const.SETUP_NONE),
    ("Cocoa", "Softs", 3, 100, 98, const.SETUP_BEAR),
    ("Coffee", "Softs", 45, 60, 60, const.SETUP_NONE),
)


def board():
    return frame(*[matrix_row(asset, cls, comm, lrg, sml, state_cls=verdict)
                   for asset, cls, comm, lrg, sml, verdict in BOARD])


def drawn(show=st.SHOW_ALL, side=st.SIDE_BOTH):
    rows, _ = st.build_rows(board(), models.RAW_PF, show=show, side=side)
    return [r.label for r in rows if r.kind == "market"]


def test_show_narrows_to_the_verdicts_worth_acting_on():
    assert set(drawn(show=st.SHOW_SETUPS)) == {"Copper", "Cocoa"}
    assert set(drawn(show=st.SHOW_SETUPS_NEAR)) == {"Copper", "Gold", "Cocoa"}
    assert len(drawn()) == len(BOARD)


def test_side_splits_on_the_neutral_midpoint():
    assert set(drawn(side=st.SIDE_BULL)) == {"Copper", "Gold", "Silver"}
    assert set(drawn(side=st.SIDE_BEAR)) == {"Cocoa", "Coffee"}


def test_the_two_filters_never_contradict_each_other():
    """A bull setup is above neutral by construction, so no combination selects an
    empty set for a reason a reader would call wrong."""
    assert drawn(show=st.SHOW_SETUPS, side=st.SIDE_BULL) == ["Copper"]
    assert drawn(show=st.SHOW_SETUPS, side=st.SIDE_BEAR) == ["Cocoa"]


def test_a_class_emptied_by_a_filter_loses_its_header():
    """Otherwise a heading sits over nothing, which reads as a class with no data."""
    rows, _ = st.build_rows(board(), models.RAW_PF, show=st.SHOW_SETUPS,
                            side=st.SIDE_BEAR)
    assert [(r.kind, r.label) for r in rows] == [("class", "Softs"),
                                                 ("market", "Cocoa")]


def test_classes_are_separated_by_a_blank_row_and_nothing_is_drawn_on_it():
    """No spacer leads the first class: that would be a gap under the legend, not
    between anything. The spacer row itself is empty. It carried a hairline rule while
    the blank row alone was the whole separation, and with the gate zones stopping at
    the block edges and the heading below the gap drawn as a bar, that rule was the
    third divider in a stack of three."""
    df = frame(
        matrix_row("Gold", "Metals", 40, 50, 50),
        matrix_row("Euro", "FX", 55, 50, 50),
        matrix_row("Cocoa", "Softs", 30, 50, 50),
    )
    rows, _ = st.build_rows(df, models.RAW_PF)
    assert [r.kind for r in rows] == ["class", "market",
                                      "spacer", "class", "market",
                                      "spacer", "class", "market"]
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)
    spacers = [i for i, r in enumerate(rows) if r.kind == "spacer"]
    assert spacers == [2, 5]
    # Nothing paints over a spacer: not a rule on it, and not a band reaching across it.
    covers = [sh for sh in fig.layout.shapes if sh.yref == "y"
              for i in spacers if min(sh.y0, sh.y1) <= i <= max(sh.y0, sh.y1)]
    assert covers == []


def test_the_gate_bands_cover_the_markets_and_nothing_else():
    """The red and green run per run-of-markets, not once down the whole figure, so the
    whole break between two classes, the blank row and the heading in it, is clean
    background. Painted through, the separator was doing its work against a continuous
    wash and the break read as weaker than the rows it was separating."""
    df = frame(
        matrix_row("Gold", "Metals", 40, 50, 50),
        matrix_row("Silver", "Metals", 60, 50, 50),
        matrix_row("Cocoa", "Softs", 30, 50, 50),
    )
    rows, _ = st.build_rows(df, models.RAW_PF)
    assert [r.kind for r in rows] == ["class", "market", "market",
                                      "spacer", "class", "market"]
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)
    bands = [sh for sh in fig.layout.shapes
             if sh.type == "rect" and sh.xref == "x"]
    # Both zones over both runs of markets: rows 1-2 and row 5, and nothing on 0, 3, 4.
    assert {(sh.y0, sh.y1) for sh in bands} == {(0.5, 2.5), (4.5, 5.5)}
    assert len(bands) == 4


def test_a_column_with_no_break_keeps_one_unbroken_band():
    """Splitting is per break, so a single-class column carries one span."""
    df = frame(matrix_row("Gold", "Metals", 40, 50, 50),
               matrix_row("Silver", "Metals", 60, 50, 50))
    rows, _ = st.build_rows(df, models.RAW_PF)
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)
    bands = [sh for sh in fig.layout.shapes
             if sh.type == "rect" and sh.xref == "x"]
    assert {(sh.y0, sh.y1) for sh in bands} == {(0.5, 2.5)}


def test_the_heading_row_carries_its_own_bar_and_its_name_is_centred():
    """The heading sits ON the row rather than out in the margin, where it was stacked
    left-aligned directly above the market labels and differed from them only in
    weight. Its bar is the only thing painted on that row, and it stays under the gate
    zones, which are the only shading on this figure that means anything."""
    df = frame(matrix_row("Gold", "Metals", 40, 50, 50),
               matrix_row("Cocoa", "Softs", 30, 50, 50))
    rows, _ = st.build_rows(df, models.RAW_PF)
    headers = [i for i, r in enumerate(rows) if r.kind == "class"]
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)

    bars = [sh for sh in fig.layout.shapes
            if sh.type == "rect" and sh.xref == "paper"
            and sh.opacity == st.HEADER_BAND_ALPHA]
    assert [sh.y0 + 0.5 for sh in bars] == headers
    assert st.HEADER_BAND_ALPHA < 0.09

    named = [a for a in fig.layout.annotations if "METALS" in a.text]
    assert len(named) == 1
    assert (named[0].xref, named[0].x, named[0].xanchor) == ("paper", 0.5, "center")
    assert named[0].xshift in (0, None)


def test_the_neutral_rule_still_runs_the_full_height():
    """It is a grid line, not a zone: a spine broken at every class stops being one
    axis a reader can sight down."""
    df = frame(matrix_row("Gold", "Metals", 40, 50, 50),
               matrix_row("Cocoa", "Softs", 30, 50, 50))
    rows, _ = st.build_rows(df, models.RAW_PF)
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)
    spine = [sh for sh in fig.layout.shapes
             if sh.type == "line" and sh.xref == "x"]
    assert len(spine) == 1
    assert (spine[0].yref, spine[0].y0, spine[0].y1) == ("paper", 0, 1)


# ── two columns ───────────────────────────────────────────────────────────────

def wide_board():
    """Uneven classes, which is the real shape: Currencies has eleven markets and
    Crypto has two."""
    rows = [matrix_row(f"C{i}", "Currencies", 50, 50, 50) for i in range(11)]
    rows += [matrix_row(f"M{i}", "Metals", 50, 50, 50) for i in range(5)]
    rows += [matrix_row(f"X{i}", "Crypto", 50, 50, 50) for i in range(2)]
    return frame(*rows)


def test_two_columns_break_only_between_classes():
    """Half of Metals at the bottom left and half at the top right is worse than
    scrolling, which is the thing this exists to avoid."""
    rows, _ = st.build_rows(wide_board(), models.RAW_PF)
    left, right = st.split_columns(rows, 2)
    for chunk in (left, right):
        assert chunk[0].kind == "class"
        classes = [r.asset_class for r in chunk if r.kind == "class"]
        # every market in the chunk belongs to a class whose header is in the chunk
        assert {r.asset_class for r in chunk if r.kind == "market"} <= set(classes)
    assert len(left) + len(right) <= len(rows)     # only spacers are dropped


def test_columns_balance_on_rows_not_on_classes():
    """Dealing the three classes evenly would put eleven markets against seven."""
    rows, _ = st.build_rows(wide_board(), models.RAW_PF)
    left, right = st.split_columns(rows, 2)
    assert abs(len(left) - len(right)) <= 4


def test_a_column_never_opens_on_a_blank_row():
    rows, _ = st.build_rows(wide_board(), models.RAW_PF)
    for chunk in st.split_columns(rows, 2):
        assert chunk[0].kind != "spacer"


def test_one_column_is_the_rows_unchanged():
    rows, _ = st.build_rows(wide_board(), models.RAW_PF)
    assert st.split_columns(rows, 1) == [rows]


def test_no_figure_draws_a_legend_of_its_own():
    """The legend is page chrome above both columns, not a trace set inside the first
    figure. Drawn inside, Plotly stacked its groups, outgrew every attempt to predict
    its height, and silently pushed that one figure's top margin out — which put the
    left column's rows ~40px below the right column's."""
    rows, _ = st.build_rows(wide_board(), models.RAW_PF)
    for chunk in st.split_columns(rows, 2):
        fig = st.build_figure(chunk, models.RAW_PF, COLORS, PALETTE)
        assert fig.layout.showlegend is False
        assert not [t for t in fig.data if t.showlegend]


def test_every_column_gets_the_same_top_margin_so_the_rows_stay_level():
    """The columns are separate figures whose rows must read as one board, so their
    margins have to be a constant nothing (legend or model) can vary."""
    rows, _ = st.build_rows(wide_board(), models.RAW_PF)
    chunks = st.split_columns(rows, 2)
    for model in models.MODELS:
        margins = {st.build_figure(c, model, COLORS, PALETTE).layout.margin.t
                   for c in chunks}
        assert margins == {st.TOP_CHROME_PX}


def test_two_classes_do_split_into_two_columns():
    """The guard counted the column being closed as one still needing blocks, so with
    exactly as many classes as columns it never split."""
    df = frame(
        *[matrix_row(f"C{i}", "Currencies", 50, 50, 50) for i in range(9)],
        *[matrix_row(f"M{i}", "Metals", 50, 50, 50) for i in range(6)],
    )
    rows, _ = st.build_rows(df, models.RAW_PF)
    chunks = st.split_columns(rows, 2)
    assert len(chunks) == 2
    assert [c[0].label for c in chunks] == ["Currencies", "Metals"]


def test_one_class_stays_one_column():
    """Nothing to split on. A class is never broken across the boundary."""
    df = frame(*[matrix_row(f"M{i}", "Metals", 50, 50, 50) for i in range(6)])
    rows, _ = st.build_rows(df, models.RAW_PF)
    assert len(st.split_columns(rows, 2)) == 1


# ── making the verdicts findable from the name column ─────────────────────────

def test_a_market_name_lights_when_its_row_has_a_verdict():
    """The name column is where the eye starts and the bar is at the far end of the
    row, so a reader scanning names alone could not find the setups."""
    df = frame(
        matrix_row("Copper", "Metals", 98, 2, 4, state_cls=const.SETUP_BULL),
        matrix_row("Gold", "Metals", 50, 50, 50),
    )
    rows, _ = st.build_rows(df, models.RAW_PF)
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)
    labels = list(fig.layout.yaxis.ticktext)
    assert COLORS.bull in labels[0] and "Copper" in labels[0]
    assert labels[1] == "Gold"       # nothing to say, so nothing added


# ── one form for every row; colour says whose it is, or what the verdict is ───

def test_a_quiet_row_draws_the_neutral_grey_not_a_verdict_hue():
    """Every market draws the same object, and green and red belong to the verdicts
    alone. The quiet tier wore the Commercial red for a while — the series-identity
    argument — and it sat in the bear verdict's own hue family, so a board of mostly
    quiet markets read as a board of almost-bear-setups. Neutral is grey."""
    df = frame(
        matrix_row("Copper", "Metals", 98, 2, 4, state_cls=const.SETUP_BULL),
        matrix_row("Gold", "Metals", 55, 50, 50),
    )
    rows, _ = st.build_rows(df, models.RAW_PF)
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)
    heads = next(t for t in fig.data
                 if t.type == "scatter" and t.marker.symbol == "circle" and t.hovertext)
    stem = next(t for t in fig.data if t.type == "bar")
    assert list(heads.x) == [98, 55]
    assert list(heads.marker.color) == [COLORS.bull, COLORS.dim]
    assert list(stem.marker.color) == [st._fill(COLORS.bull), st.QUIET_STEM]


def test_the_quiet_tier_sits_below_both_verdict_tiers():
    """Hue separates neutral from the verdicts, and size and fade keep the ordering
    legible even where hue is weak (small marks, colour-blind readers, a palette whose
    grey drifts warm). Full setup > near > quiet, on three channels at once."""
    df = frame(
        matrix_row("Copper", "Metals", 98, 2, 4, state_cls=const.SETUP_BEAR),
        matrix_row("Silver", "Metals", 80, 30, 30, state_cls=const.SETUP_NEAR_BEAR),
        matrix_row("Gold", "Metals", 55, 50, 50),
    )
    rows, _ = st.build_rows(df, models.RAW_PF)
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)
    heads = next(t for t in fig.data
                 if t.type == "scatter" and t.marker.symbol == "circle" and t.hovertext)
    by_x = dict(zip(heads.x, zip(heads.marker.size, heads.marker.color)))
    assert by_x[98] == (st.HEAD_SIZE, COLORS.bear)
    assert by_x[80] == (st.HEAD_SIZE, COLORS.bear_near)
    assert by_x[55][0] == st.QUIET_HEAD_SIZE
    assert st.QUIET_HEAD_SIZE < st.HEAD_SIZE
    # Dim's own alpha sits below the near tier's fade, the ordering viz_constants
    # documents: "approaching" must never look quieter than "neutral".
    def alpha(c):
        return float(c.rstrip(")").rsplit(",", 1)[1])
    assert alpha(COLORS.dim) < alpha(COLORS.bear_near)


def test_the_prior_position_is_drawn_from_the_matching_basis():
    """`Comm Move` follows the raw default, so pairing it with `Comm Index Norm` under
    NPF would subtract a raw change from a normalized level. Each model reads the
    momentum column that belongs to its own basis."""
    assert st.MOVE_COLUMN[models.RAW_PF.key] == "Comm Move"
    assert st.MOVE_COLUMN[models.NPF.key] == "Comm Move Norm"
    for model in models.MODELS:
        assert model.key in st.MOVE_COLUMN


def test_the_prior_mark_sits_where_the_index_was():
    df = frame(matrix_row("Gold", "Metals", 70, 50, 50, move=12))
    rows, _ = st.build_rows(df, models.RAW_PF)
    assert [r.prior for r in rows if r.kind == "market"] == [58]
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)
    hollow = next(t for t in fig.data
                  if t.type == "scatter" and not t.showlegend
                  and t.marker.symbol == "circle-open")
    assert list(hollow.x) == [58]


def test_the_prior_mark_stays_on_the_axis():
    """The index is bounded and the move is a point difference, so a market that ran
    from one end to the other would place its prior mark off the scale."""
    df = frame(matrix_row("Gold", "Metals", 98, 50, 50, move=-40),
               matrix_row("Silver", "Metals", 2, 50, 50, move=40))
    rows, _ = st.build_rows(df, models.RAW_PF)
    assert sorted(r.prior for r in rows if r.kind == "market") == [0, 100]


def test_a_market_with_no_move_simply_has_no_prior_mark():
    df = frame(matrix_row("Gold", "Metals", 70, 50, 50, move=None))
    rows, _ = st.build_rows(df, models.RAW_PF)
    assert [r.prior for r in rows if r.kind == "market"] == [None]
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)
    # Legend keys use the same symbols, so drawn marks are the ones not in the legend.
    assert not [t for t in fig.data if t.type == "scatter" and not t.showlegend
                and t.marker.symbol == "circle-open"]


def test_market_rows_are_ruled_between_but_never_around_a_block():
    """A row carries four marks on ROW_PX pixels and nothing tied them together. This
    was an alternating band, which gave an eleven-row class a ladder the eye resolved
    before the data; a rule treats every row alike. It goes BETWEEN rows only: under the
    last market of a class it would close the block off just above the gap that already
    separates it, and above the first it would double the heading bar's bottom edge."""
    df = frame(
        matrix_row("A", "Metals", 90, 50, 50),
        matrix_row("B", "Metals", 80, 50, 50),
        matrix_row("C", "Metals", 70, 50, 50),
        matrix_row("D", "Softs", 60, 50, 50),
        matrix_row("E", "Softs", 50, 50, 50),
    )
    rows, _ = st.build_rows(df, models.RAW_PF)
    kinds = [r.kind for r in rows]
    assert kinds == ["class", "market", "market", "market",
                     "spacer", "class", "market", "market"]
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)

    rules = sorted(sh.y0 for sh in fig.layout.shapes
                   if sh.type == "line" and sh.xref == "paper")
    # A/B and B/C inside Metals, D/E inside Softs. Nothing under C or E, nothing above
    # A or D, and nothing on the spacer.
    assert rules == [1.5, 2.5, 6.5]
    assert not [sh for sh in fig.layout.shapes
                if sh.type == "rect" and sh.opacity == st.ROW_RULE_ALPHA]


def test_the_prior_mark_is_the_neutral_colour_the_legend_promises():
    """It was once drawn in the template's third default colour, a teal green, against
    a differently-coloured key. An OPEN symbol takes its outline from marker.color, and
    only marker.line.color was set, so marker.color fell through to the colorway. Held
    here as: the drawn ring and its legend key are the same colour, the quiet grey —
    history is context, not a verdict, whatever row it sits on."""
    df = frame(matrix_row("Gold", "Metals", 70, 50, 50, move=12))
    rows, _ = st.build_rows(df, models.RAW_PF)
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)
    drawn = [t for t in fig.data
             if t.type == "scatter" and t.marker.symbol == "circle-open"]
    assert drawn
    assert drawn[0].marker.color == COLORS.dim
    key = [(colour, glyph)
           for _, entries in st.legend_items(models.RAW_PF, COLORS, PALETTE)
           for label, colour, glyph in entries if label.endswith("w ago")]
    assert key == [(COLORS.dim, st.GLYPH_CIRCLE)]


def test_no_drawn_mark_falls_through_to_the_template_colourway():
    """The general form of the bug above: an unset colour is not an error, it is the
    theme's colour, and it only shows up by disagreeing with something else."""
    df = frame(
        matrix_row("Copper", "Metals", 98, 2, 4, state_cls=const.SETUP_BULL, move=8),
        matrix_row("Gold", "Metals", 55, 50, 50, move=-3),
    )
    rows, _ = st.build_rows(df, models.RAW_PF)
    fig = st.build_figure(rows, models.RAW_PF, COLORS, PALETTE)
    for trace in fig.data:
        # The empty trace that exists only to make Plotly draw the top axis has
        # nothing to colour.
        if not [v for v in (trace.x or []) if v is not None]:
            continue
        assert trace.marker.color is not None, (
            f"{trace.type}/{trace.marker.symbol} takes its colour from the theme")
