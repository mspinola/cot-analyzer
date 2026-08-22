"""How the Aggregate Exposure figure is drawn.

Pure figure rules, no store and no app. The list is short on purpose: most of what makes
this view honest is arithmetic and lives in `cotmetrics.exposure`, and what is left here
is the handful of drawing decisions that would silently mislead if they drifted.
"""
import pandas as pd

import components.exposure_traces as et
from components.plot_colors import GridColors

PALETTE = ["#F87171", "#60A5FA", "#FBBF24", "#34D399", "#A78BFA"]
COLORS = GridColors(bull="#34D399", bear="#FF4D4D",
                    bull_near="rgba(52,211,153,0.4)", bear_near="rgba(255,77,77,0.4)")

#: Plotly's default colorway. A trace with no explicit colour silently takes an entry
#: from this, which is how the Crowding Strip once drew teal-green circles against a red
#: legend key. The general test at the bottom is the guard that caught the second one.
TEMPLATE_COLORWAY = {"#636efa", "#EF553B", "#00cc96", "#ab63fa", "#FFA15A"}


def frame(values, ranks=None, weeks=6):
    idx = pd.date_range("2026-01-06", periods=len(values), freq="W-TUE")
    return pd.DataFrame({
        "notional_usd": values,
        "risk_usd": [v / 100 for v in values],
        "n_markets": 3,
        "notional_pct_rank": ranks or [50.0] * len(values),
        "risk_pct_rank": ranks or [50.0] * len(values),
    }, index=idx)


def build(df, composite=None, unit=et.UNIT_NOTIONAL):
    return et.build_figure(df, composite, unit=unit, colors=COLORS, palette=PALETTE,
                           leg_label="Speculators", set_label="Equities")


# ── the axis unit ─────────────────────────────────────────────────────────────

def test_the_axis_unit_follows_the_data_rather_than_being_fixed():
    """The same page draws equity-index notional in tens of billions and a single soft
    in tens of millions. One hard-coded unit makes one of the two unreadable."""
    assert et.unit_scale([5.5e10, -2e10]) == (1e9, "bn")
    assert et.unit_scale([4.2e7, -1e7]) == (1e6, "m")
    assert et.unit_scale([300.0]) == (1.0, "")


def test_the_unit_keeps_at_least_two_digits_on_the_axis():
    """A billion-dollar peak in billions is an axis labelled 0, 0.5, 1. The same number
    in millions is 0, 250, 500, 750, 1000, which is a scale a reader can use."""
    assert et.unit_scale([1.0e9, -4e8]) == (1e6, "m")
    assert et.unit_scale([1.4e10, 0.0]) == (1e9, "bn")


def test_the_unit_is_chosen_from_the_largest_value_drawn_not_the_last():
    assert et.unit_scale([9e10, 1.0]) == (1e9, "bn")


def test_a_series_of_nothing_does_not_crash_the_scale():
    assert et.unit_scale([]) == (1.0, "")


# ── the empty case ────────────────────────────────────────────────────────────

def test_an_empty_total_says_why_rather_than_drawing_an_empty_box():
    """The completeness rule can legitimately leave nothing, and a blank chart with no
    explanation reads as a broken page rather than as an answer."""
    fig = build(pd.DataFrame())
    text = " ".join(a.text for a in fig.layout.annotations)
    assert "every market in this set" in text
    assert fig.layout.height == et.FIGURE_PX


# ── the panels ────────────────────────────────────────────────────────────────

def test_the_reference_panel_is_drawn_above_the_exposure_panel():
    """The reference is the set's own composite, and it sits on top because that is the
    stack the printed source got right."""
    composite = pd.Series([100.0, 105.0, 110.0],
                          index=pd.date_range("2026-01-06", periods=3, freq="W-TUE"))
    fig = build(frame([1e9, 2e9, 3e9]), composite)
    named = {t.name: t.yaxis for t in fig.data if t.name}
    assert named["Set composite"] == "y"
    assert named["Speculators"] == "y2"


def test_the_extreme_band_is_drawn_before_the_level_so_the_level_stays_readable():
    order = [t.name for t in build(frame([1e9] * 8)).data]
    assert order.index("Usual range") < order.index("Speculators")


def test_every_weekly_series_steps():
    """COT is one observation a week. A smooth line across it implies intra-week detail
    that does not exist."""
    fig = build(frame([1e9, 2e9, 3e9]))
    stepped = [t for t in fig.data if t.name in ("Speculators", "Usual range")]
    assert stepped
    assert all(t.line.shape == "hv" for t in stepped)


def test_the_level_is_filled_to_zero_and_carries_a_zero_line():
    """Sign is already carried by which side of zero the trace sits on. Colouring it as
    well would spend a second channel on a variable that has not asked for one."""
    fig = build(frame([1e9, -2e9]))
    level = next(t for t in fig.data if t.name == "Speculators")
    assert level.fill == "tozeroy"
    assert any(getattr(s, "y0", None) == 0 for s in fig.layout.shapes)


# ── what the hover promises ───────────────────────────────────────────────────

def test_the_hover_carries_the_percentile_because_the_level_cannot_answer_is_this_a_lot():
    fig = build(frame([1e9, 2e9], ranks=[10.0, 97.0]))
    level = next(t for t in fig.data if t.name == "Speculators")
    assert "percentile" in level.hovertemplate
    assert list(level.customdata) == [10.0, 97.0]


def test_the_hover_percentile_follows_the_unit_being_drawn():
    df = frame([1e9, 2e9])
    df["risk_pct_rank"] = [11.0, 22.0]
    fig = build(df, unit=et.UNIT_RISK)
    level = next(t for t in fig.data if t.name == "Speculators")
    assert list(level.customdata) == [11.0, 22.0]


# ── the units are labelled for what they can and cannot do ────────────────────

def test_both_units_carry_a_note_and_a_rank_column():
    assert set(et.UNIT_LABELS) == set(et.UNIT_NOTES) == set(et.UNIT_RANK_COLUMN)


def test_the_notional_note_says_it_is_not_comparable_between_markets():
    """It is the rung that reads as an answer and is not: a bigger market carries bigger
    numbers whatever anyone is holding."""
    assert "not" in et.UNIT_NOTES[et.UNIT_NOTIONAL]
    assert "comparable" in et.UNIT_NOTES[et.UNIT_NOTIONAL]


# ── the colorway guard ────────────────────────────────────────────────────────

def test_no_drawn_trace_falls_through_to_the_template_colorway():
    """An unset marker or line colour is not an error in Plotly; it silently takes the
    next template colour. That is how the Crowding Strip drew teal circles against a red
    legend key, and how it did it twice."""
    composite = pd.Series([100.0, 105.0],
                          index=pd.date_range("2026-01-06", periods=2, freq="W-TUE"))
    fig = build(frame([1e9, 2e9]), composite)
    for trace in fig.data:
        line = getattr(trace, "line", None)
        colour = getattr(line, "color", None)
        if colour is None:
            # Only the two invisible band edges may go uncoloured, and only because they
            # are drawn at zero width purely to anchor a fill.
            assert getattr(line, "width", None) == 0, f"{trace.name} has no line colour"
            continue
        assert colour not in TEMPLATE_COLORWAY, f"{trace.name} took a template colour"


def test_the_band_thresholds_are_the_apps_usual_edge_of_normal():
    """Ten and ninety, the same pair every other page treats as the edge of normal, so a
    reader carries one threshold between views."""
    assert (et.BAND_LOW, et.BAND_HIGH) == (0.10, 0.90)


def test_a_percentile_needs_two_years_before_it_says_anything():
    assert et.MIN_RANK_PERIODS == 104


# ── the leg convention and the gaps ───────────────────────────────────────────

def test_the_level_takes_its_colour_from_the_leg_it_draws():
    """The app-wide slot convention: 0 Commercials, 1 Large Specs, 2 Small Traders.
    Drawing a speculator series in the Commercial red would contradict every other page,
    and the reader carries that mapping between them."""
    from cotmetrics.exposure import LEG_COMM, LEG_SMALL, LEG_SPEC
    for leg, slot in ((LEG_COMM, 0), (LEG_SPEC, 1), (LEG_SMALL, 2)):
        fig = et.build_figure(frame([1e9, 2e9]), None, unit=et.UNIT_NOTIONAL,
                              colors=COLORS, palette=PALETTE, leg_label="L", leg=leg)
        level = next(t for t in fig.data if t.name == "L")
        assert level.line.color == PALETTE[slot], leg


def test_the_line_is_broken_across_a_real_hole_rather_than_drawn_through_it():
    """The completeness rule leaves interior holes where one member's history stops and
    restarts. A step line straight across a 168-day hole says the level held for five
    months, which is a claim the data does not make."""
    idx = pd.DatetimeIndex(["2026-01-06", "2026-01-13", "2026-06-02", "2026-06-09"])
    out = et.break_gaps(idx, [1.0, 2.0, 3.0, 4.0])
    assert out[0] == 1.0
    assert out[1] != out[1]          # NaN: the week before the hole
    assert out[2] == 3.0


def test_consecutive_weeks_are_never_broken():
    idx = pd.date_range("2026-01-06", periods=5, freq="W-TUE")
    assert et.break_gaps(idx, [1.0, 2.0, 3.0, 4.0, 5.0]) == [1.0, 2.0, 3.0, 4.0, 5.0]


# ── the leg split ─────────────────────────────────────────────────────────────

def test_a_legs_companions_are_never_its_own_mirror():
    """The distinction the whole companion panel rests on, and it is easy to get
    backwards. Commercials against the SPECULATOR TOTAL is an accounting identity:
    `Comm_net + Spec_net` is 0.000000 across all 45 priceable markets and every week in
    the store. Commercials against Large and Small SEPARATELY is not, because no one of
    the three determines another."""
    from cotmetrics.exposure import LEG_COMM, LEG_SPEC
    assert LEG_SPEC not in et.COMPANION_LEGS[LEG_COMM]
    assert LEG_COMM not in et.COMPANION_LEGS[LEG_SPEC]


def test_every_leg_has_companions_and_none_of_them_is_itself():
    """Whatever the subject, the panel beneath it is everyone else, so the zero-sum
    constraint tying the three Legacy categories is visible on the page."""
    from cotmetrics.exposure import LEG_COLUMNS
    for leg in LEG_COLUMNS:
        companions = et.COMPANION_LEGS[leg]
        assert len(companions) == 2
        assert leg not in companions


def test_only_speculators_is_the_SUM_of_its_companions():
    """A different relation from COMPANION_LEGS, and it must not collapse into it. Large
    and Small are drawn beneath Commercials because they are the rest of the report, not
    because they are what Commercials is made of, and a sentence calling them its halves
    would describe an arithmetic that does not exist."""
    from cotmetrics.exposure import LEG_COMM, LEG_LARGE, LEG_SMALL, LEG_SPEC
    assert set(et.LEG_PARTS) == {LEG_SPEC}
    assert et.LEG_PARTS[LEG_SPEC] == (LEG_LARGE, LEG_SMALL)
    for leg in (LEG_COMM, LEG_LARGE, LEG_SMALL):
        assert leg not in et.LEG_PARTS


def test_the_companions_get_their_own_panel_under_the_subject():
    """They are often an order of magnitude apart from the subject and from each other,
    so sharing its axis squashed them flat against the bottom of the band. And the
    subject's band and percentile describe the subject ALONE, so a companion crossing
    that band read as a statement about it that nothing on the page had made."""
    from cotmetrics.exposure import LEG_LARGE, LEG_SMALL, LEG_SPEC
    df = frame([1e9, 2e9])
    parts = {LEG_LARGE: pd.Series([-3e8, -4e8], index=df.index),
             LEG_SMALL: pd.Series([1.3e9, 2.4e9], index=df.index)}
    fig = et.build_figure(df, None, unit=et.UNIT_NOTIONAL, colors=COLORS,
                          palette=PALETTE, leg_label="Spec", leg=LEG_SPEC, parts=parts)
    axes = {t.name: (t.yaxis or "y") for t in fig.data}
    assert axes["Spec"] == "y2"
    assert axes["Large Speculators"] == "y3"
    assert axes["Small Traders"] == "y3"


def test_the_companion_panel_gets_its_own_zero_line():
    """It is read for sign as much as for level, and its range is its own."""
    from cotmetrics.exposure import LEG_LARGE, LEG_SPEC
    df = frame([1e9, 2e9])
    fig = et.build_figure(df, None, unit=et.UNIT_NOTIONAL, colors=COLORS,
                          palette=PALETTE, leg_label="Spec", leg=LEG_SPEC,
                          parts={LEG_LARGE: pd.Series([-3e8, -4e8], index=df.index)})
    zero_refs = {s.yref for s in fig.layout.shapes if getattr(s, "y0", None) == 0}
    assert "y2" in zero_refs
    assert "y3" in zero_refs


def test_the_crosshair_axis_names_the_bottom_panel():
    """Spelled here rather than at the call site so adding a panel cannot leave the page
    drawing a crosshair against an axis that has moved."""
    assert et.CROSSHAIR_XREF == "x3"


def test_the_companions_stay_thinner_and_unfilled_even_with_a_panel_of_their_own():
    """Still context: the subject is what the percentile, the band and the headline all
    describe."""
    from cotmetrics.exposure import LEG_LARGE, LEG_SMALL, LEG_SPEC
    df = frame([1e9, 2e9])
    parts = {LEG_LARGE: pd.Series([-3e8, -4e8], index=df.index),
             LEG_SMALL: pd.Series([1.3e9, 2.4e9], index=df.index)}
    fig = et.build_figure(df, None, unit=et.UNIT_NOTIONAL, colors=COLORS,
                          palette=PALETTE, leg_label="Spec", leg=LEG_SPEC, parts=parts)
    drawn = {t.name: t for t in fig.data}
    for name in ("Large Speculators", "Small Traders"):
        assert drawn[name].fill is None
        assert drawn[name].line.width < drawn["Spec"].line.width


def test_a_part_with_no_data_is_skipped_rather_than_drawn_flat():
    from cotmetrics.exposure import LEG_LARGE, LEG_SPEC
    fig = et.build_figure(frame([1e9, 2e9]), None, unit=et.UNIT_NOTIONAL, colors=COLORS,
                          palette=PALETTE, leg_label="Spec", leg=LEG_SPEC,
                          parts={LEG_LARGE: None})
    assert "Large Speculators" not in [t.name for t in fig.data]


# ── the contributors ──────────────────────────────────────────────────────────

def test_the_largest_contributor_is_drawn_at_the_top():
    """A horizontal bar axis counts upward from the bottom, so the order has to be
    reversed or the reader meets the smallest market first."""
    values = pd.Series({"S&P 500": 3.71e8, "Nasdaq": 1.16e8, "Russell": -5.7e7})
    fig = et.build_contributions_figure(values, unit=et.UNIT_RISK, palette=PALETTE)
    assert list(fig.data[0].y)[-1] == "S&P 500"
    assert list(fig.data[0].y)[0] == "Russell"


def test_a_contributor_pointing_against_the_total_is_faded_not_recoloured():
    """"Opposite" is one variable, and the palette slot is already spending itself on
    which leg this is."""
    values = pd.Series({"S&P 500": 3.71e8, "Russell": -5.7e7})
    fig = et.build_contributions_figure(values, unit=et.UNIT_RISK, palette=PALETTE)
    colours = dict(zip(fig.data[0].y, fig.data[0].marker.color))
    assert str(et.AGAINST_ALPHA) in colours["Russell"]
    assert str(et.WITH_ALPHA) in colours["S&P 500"]


def test_against_is_judged_by_the_totals_sign_not_by_being_negative():
    """On a net-short total the negative markets are the ones AGREEING."""
    values = pd.Series({"A": -3.0e8, "B": 5.0e7})
    fig = et.build_contributions_figure(values, unit=et.UNIT_RISK, palette=PALETTE)
    colours = dict(zip(fig.data[0].y, fig.data[0].marker.color))
    assert str(et.WITH_ALPHA) in colours["A"]
    assert str(et.AGAINST_ALPHA) in colours["B"]


def test_the_bar_figure_grows_with_the_number_of_markets():
    small = et.build_contributions_figure(pd.Series({"A": 1.0e8, "B": 2.0e8}),
                                          unit=et.UNIT_RISK, palette=PALETTE)
    big = et.build_contributions_figure(
        pd.Series({c: 1.0e8 for c in "ABCDEFGHI"}), unit=et.UNIT_RISK, palette=PALETTE)
    assert big.layout.height > small.layout.height


def test_no_contributors_draws_an_empty_frame_rather_than_raising():
    fig = et.build_contributions_figure(None, unit=et.UNIT_RISK, palette=PALETTE)
    assert len(fig.data) == 0
    assert fig.layout.height == et.CONTRIB_MIN_PX
