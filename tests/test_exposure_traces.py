"""How the Aggregate Exposure figure is drawn.

Pure figure rules, no store and no app. The list is short on purpose: most of what makes
this view honest is arithmetic and lives in `cotmetrics.exposure`, and what is left here
is the handful of drawing decisions that would silently mislead if they drifted.
"""
import pandas as pd
from cotmetrics.exposure import LEG_SPEC

import components.exposure_traces as et
from components.plot_colors import GridColors, hex_to_rgba

# Six slots, because the figure indexes Volatility at 5. Real palettes come
# through viz_config.get_palette, which pads; a hand-written one has to be whole.
PALETTE = ["#F87171", "#60A5FA", "#FBBF24", "#34D399", "#ABB8C9", "#A78BFA"]
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
    assert "every market selected" in text
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


# ── the price axis ────────────────────────────────────────────────────────────

def series(values, start="2026-01-06"):
    return pd.Series([float(v) for v in values],
                     index=pd.date_range(start, periods=len(values), freq="W-TUE"))


def test_a_wide_price_range_gets_a_log_axis():
    """Log earns its keep by making equal PERCENTAGE moves equal distances, which only
    shows up over a wide range. Metals runs 15.2x since 1989 and is the case this exists
    for."""
    assert et.price_axis_type(series([100, 1500])) == "log"


def test_a_narrow_price_range_stays_linear():
    """Under 3x the two look alike and log only costs the reader a familiar axis.
    Currencies runs 1.4x and is the case this protects."""
    assert et.price_axis_type(series([100, 140])) == "linear"


def test_a_composite_that_touches_zero_stays_linear():
    """The composite is a mean of ratio-rebased UNADJUSTED prices, and those are not
    guaranteed positive: WTI settled at -37.63 on 2020-04-20. Plotly drops non-positive
    points from a log axis SILENTLY, so this guard is the difference between a linear
    chart and a chart with a hole nothing announces."""
    assert et.price_axis_type(series([100, -20, 500])) == "linear"
    assert et.price_axis_type(series([0, 100, 500])) == "linear"


def test_no_composite_at_all_is_linear_rather_than_an_error():
    assert et.price_axis_type(None) == "linear"
    assert et.price_axis_type(pd.Series(dtype=float)) == "linear"


# ── the percentile scale ──────────────────────────────────────────────────────

def test_the_exposure_panel_cannot_be_logged_so_it_is_ranked_instead():
    """The series is signed and crosses zero, so a log axis is not merely unhelpful
    there, it is undefined. And the breadth is real: on Metals the median absolute
    weekly figure grew 48x in risk between the 1990s and the 2020s, because dollar
    figures carry the price level. The percentile is stationary by construction."""
    df = frame([1e9, -2e9, 3e9], ranks=[10.0, 50.0, 97.0])
    fig = build(df)
    assert fig.layout.yaxis2.type in (None, "linear")

    ranked = et.build_figure(df, None, unit=et.UNIT_NOTIONAL, colors=COLORS,
                             palette=PALETTE, leg_label="Spec", scale=et.SCALE_RANK)
    subject = next(t for t in ranked.data if t.name == "Spec")
    assert list(subject.y) == [10.0, 50.0, 97.0]
    assert tuple(ranked.layout.yaxis2.range) == (0, 100)


def test_the_ranked_panel_drops_the_fill():
    """Filling to zero there would shade the distance to the BOTTOM of the
    distribution, and zero is a floor rather than the neutral the fill means on a
    signed series."""
    ranked = et.build_figure(frame([1e9, 2e9]), None, unit=et.UNIT_NOTIONAL,
                             colors=COLORS, palette=PALETTE, leg_label="Spec",
                             scale=et.SCALE_RANK)
    assert next(t for t in ranked.data if t.name == "Spec").fill is None
    assert next(t for t in build(frame([1e9, 2e9])).data
                if t.name == "Speculators").fill == "tozeroy"


def test_the_ranked_panels_mark_the_median_week_not_zero():
    """Zero is neutral on a signed series and the floor of the distribution on a rank."""
    ranked = et.build_figure(frame([1e9, 2e9]), None, unit=et.UNIT_NOTIONAL,
                             colors=COLORS, palette=PALETTE, leg_label="Spec",
                             scale=et.SCALE_RANK)
    assert any(getattr(sh, "y0", None) == 50 for sh in ranked.layout.shapes)
    assert not any(getattr(sh, "y0", None) == 0 and sh.yref == "y2"
                   for sh in ranked.layout.shapes)


def test_the_band_is_flat_on_the_percentile_scale():
    """It IS flat, at the two percentiles it is made of, which is the point: the line
    moves in and out of a fixed range instead of the range chasing the line."""
    ranked = et.build_figure(frame([1e9] * 6, ranks=[5.0, 50.0, 95.0] * 2), None,
                             unit=et.UNIT_NOTIONAL, colors=COLORS, palette=PALETTE,
                             leg_label="Spec", scale=et.SCALE_RANK)
    band = next(t for t in ranked.data if t.name == "Usual range")
    assert set(band.y) == {et.BAND_LOW * 100}


def test_both_scales_are_offered_with_a_label_each():
    assert set(et.SCALE_LABELS) == {et.SCALE_LEVEL, et.SCALE_RANK}


def test_the_percentile_hover_still_says_how_much_money_that_was():
    """Each scale's hover carries the OTHER quantity, so neither view hides what the
    other one is for: the level cannot answer "is this a lot" on its own, and the
    percentile cannot say how much money that is."""
    ranked = et.build_figure(frame([1e9, 2e9], ranks=[10.0, 97.0]), None,
                             unit=et.UNIT_NOTIONAL, colors=COLORS, palette=PALETTE,
                             leg_label="Spec", scale=et.SCALE_RANK)
    subject = next(t for t in ranked.data if t.name == "Spec")
    assert "percentile" in subject.hovertemplate
    assert "USD" in subject.hovertemplate
    assert list(subject.y) == [10.0, 97.0]


def test_a_log_price_axis_labels_its_ticks_in_full():
    """Plotly's `D2` labels a minor tick with a bare mantissa, so a 200 renders as "2"
    directly under a "100". On a panel of index levels that is not a shorthand, it is a
    wrong number."""
    fig = et.build_figure(frame([1e9, 2e9]), series([100, 1500]),
                          unit=et.UNIT_NOTIONAL, colors=COLORS, palette=PALETTE,
                          leg_label="Spec")
    assert fig.layout.yaxis.type == "log"
    assert fig.layout.yaxis.tickmode == "array"
    assert "1,000" in fig.layout.yaxis.ticktext
    assert "200" in fig.layout.yaxis.ticktext
    assert "2" not in fig.layout.yaxis.ticktext


def test_the_log_ticks_are_one_two_and_five_a_decade_inside_the_range():
    assert et.log_ticks(series([100, 1500])) == [100, 200, 500, 1000]
    assert et.log_ticks(series([74.9, 1135.7])) == [100, 200, 500, 1000]


def test_a_range_too_narrow_for_three_ticks_falls_back_to_plotlys_default():
    """A range that narrow has no business on a log axis anyway."""
    assert et.log_ticks(series([100, 150])) is None
    assert et.log_ticks(series([100, -5])) is None
    assert et.log_ticks(None) is None


def test_a_linear_price_axis_takes_no_tick_array():
    fig = et.build_figure(frame([1e9, 2e9]), series([100, 120]),
                          unit=et.UNIT_NOTIONAL, colors=COLORS, palette=PALETTE,
                          leg_label="Spec")
    assert fig.layout.yaxis.type == "linear"
    assert fig.layout.yaxis.tickvals is None


def test_the_title_names_the_numeraire_the_axis_is_in():
    """It read "Equities - USD daily risk" over a chart whose y axis said "oz gold
    (k)"."""
    from cotmetrics.exposure import NUMERAIRE_GOLD
    gold = et.build_figure(frame([1e6, 2e6]), None, unit=et.UNIT_RISK, colors=COLORS,
                           palette=PALETTE, leg_label="Spec", set_label="Equities",
                           numeraire=NUMERAIRE_GOLD)
    assert "oz gold" in gold.layout.title.text
    assert "USD" not in gold.layout.title.text
    assert "oz gold" in gold.layout.yaxis2.title.text

    usd = build(frame([1e9, 2e9]))
    assert "USD" in usd.layout.title.text


def test_the_price_axis_names_the_numeraire_it_is_indexed_in():
    """It said "Index (=100 at start)" over a gold-denominated composite, which is the
    reference/subject mismatch this view exists to avoid, one panel up."""
    from cotmetrics.exposure import NUMERAIRE_GOLD
    gold = et.build_figure(frame([1e6, 2e6]), series([100, 90]), unit=et.UNIT_RISK,
                           colors=COLORS, palette=PALETTE, leg_label="Spec",
                           numeraire=NUMERAIRE_GOLD)
    assert "oz gold" in gold.layout.yaxis.title.text
    assert "USD" in build(frame([1e9, 2e9]), series([100, 120])).layout.yaxis.title.text


# ── one market ────────────────────────────────────────────────────────────────

def test_the_price_trace_is_not_called_a_composite_for_one_market():
    """An equal-weight composite of one market is that market's price, and the legend
    saying "composite" sends a reader looking for a construction that is not there."""
    df = frame([1e9, 2e9, 3e9])
    price = pd.Series([100.0, 101.0, 102.0], index=df.index)
    fig = et.build_figure(df, price, unit=et.UNIT_NOTIONAL, colors=COLORS,
                          palette=PALETTE, leg_label="Speculators", set_label="Gold",
                          single=True)
    names = [t.name for t in fig.data]
    assert "Market price" in names
    assert "Set composite" not in names


def test_the_price_trace_is_still_a_composite_for_a_total():
    df = frame([1e9, 2e9, 3e9])
    price = pd.Series([100.0, 101.0, 102.0], index=df.index)
    fig = build(df, price)
    assert "Set composite" in [t.name for t in fig.data]


def test_the_other_lens_is_drawn_only_on_the_percentile_scale():
    """Contracts and dollars share no axis, so on the level scale a second line would be
    a second y-axis inviting a reader to measure the space between two units that have
    no common size."""
    df = frame([1e9, 2e9, 3e9])
    ranks = pd.Series([20.0, 40.0, 60.0], index=df.index)
    level = et.build_figure(df, None, unit=et.UNIT_NOTIONAL, colors=COLORS,
                            palette=PALETTE, leg_label="Specs", set_label="Gold",
                            single=True, contracts=ranks)
    assert "Contracts %ile" not in [t.name for t in level.data]
    ranked = et.build_figure(df, None, unit=et.UNIT_NOTIONAL, colors=COLORS,
                             palette=PALETTE, leg_label="Specs", set_label="Gold",
                             single=True, contracts=ranks, scale=et.SCALE_RANK)
    assert "Contracts %ile" in [t.name for t in ranked.data]


def test_the_gap_between_the_lenses_is_shaded_rather_than_left_to_the_eye():
    """Both series are weekly over twenty years, so two lines of the same shape in one
    small panel are a thicket. The fill makes the gap the object."""
    df = frame([1e9, 2e9, 3e9])
    ranks = pd.Series([20.0, 40.0, 60.0], index=df.index)
    fig = et.build_figure(df, None, unit=et.UNIT_NOTIONAL, colors=COLORS,
                          palette=PALETTE, leg_label="Specs", set_label="Gold",
                          single=True, contracts=ranks, scale=et.SCALE_RANK)
    # The wedge carries the LEG's colour, where the usual-range band beneath it is
    # neutral: it is a fact about this leg's two lenses, not about the distribution.
    wedge = hex_to_rgba(PALETTE[et.LEG_PALETTE_SLOT[LEG_SPEC]], et.LENS_FILL_ALPHA)
    assert [t.fillcolor for t in fig.data].count(wedge) == 1


# ── the volatility panel ──────────────────────────────────────────────────────

def with_vol(values, sigma=0.013):
    df = frame(values)
    df["sigma_weighted"] = sigma
    return df


def test_volatility_gets_its_own_panel_when_the_total_can_supply_one():
    fig = build(with_vol([1e9, 2e9, 3e9]))
    assert "Volatility (held-weighted)" in [t.name for t in fig.data]
    assert fig.layout.height == et.FIGURE_PX_VOL


def test_a_total_with_no_volatility_keeps_the_three_panel_figure():
    """Older cotmetrics has no such column, and a set holding nothing has no holdings to
    weight a volatility by. Neither draws an empty register."""
    fig = build(frame([1e9, 2e9, 3e9]))
    assert "Volatility (held-weighted)" not in [t.name for t in fig.data]
    assert fig.layout.height == et.FIGURE_PX


def test_a_column_of_nothing_is_not_a_panel():
    df = frame([1e9, 2e9, 3e9])
    df["sigma_weighted"] = float("nan")
    assert build(df).layout.height == et.FIGURE_PX


def test_the_volatility_axis_is_annualised_because_nobody_reads_daily_vol():
    """0.013 a day is 20.6% a year. cotmetrics keeps TRADING_DAYS for exactly this."""
    fig = build(with_vol([1e9, 2e9, 3e9]))
    vol = next(t for t in fig.data if t.name.startswith("Volatility"))
    assert round(float(vol.y[0]), 1) == 20.6


def test_the_volatility_panel_follows_the_scale_switch_like_every_other_panel():
    fig = et.build_figure(with_vol([1e9, 2e9, 3e9]), None, unit=et.UNIT_NOTIONAL,
                          colors=COLORS, palette=PALETTE, leg_label="Specs",
                          set_label="Equities", scale=et.SCALE_RANK)
    assert tuple(fig.layout.yaxis4.range) == (0, 100)


def test_volatility_is_not_drawn_in_the_price_colour():
    """It started there, on the argument that volatility is a property of the price. Two
    panels apart a shared colour does not read as a shared subject, it reads as the same
    line twice. Every other slot names a trader group, so it takes the muted one."""
    df = with_vol([1e9, 2e9, 3e9])
    fig = build(df, pd.Series([100.0, 101.0, 102.0], index=df.index))
    vol = next(t for t in fig.data if t.name.startswith("Volatility"))
    price = next(t for t in fig.data if t.name == "Set composite")
    assert vol.line.color == hex_to_rgba(PALETTE[et.VOL_PALETTE_SLOT], et.VOL_ALPHA)
    assert vol.line.color != price.line.color
    assert et.VOL_PALETTE_SLOT not in et.LEG_PALETTE_SLOT.values()


def test_a_single_market_calls_it_what_it_is():
    fig = et.build_figure(with_vol([1e9, 2e9, 3e9]), None, unit=et.UNIT_NOTIONAL,
                          colors=COLORS, palette=PALETTE, leg_label="Specs",
                          set_label="Gold", single=True)
    assert "Volatility" in [t.name for t in fig.data]


def test_the_figure_records_which_axis_its_bottom_panel_is_on():
    """The row count is not fixed, so the page asks rather than counting panels."""
    assert build(with_vol([1e9, 2e9])).layout.meta[et.XREF_META] == "x4"
    assert build(frame([1e9, 2e9])).layout.meta[et.XREF_META] == "x3"


# ── zooming ───────────────────────────────────────────────────────────────────

def test_the_chart_offers_the_same_range_ladder_as_the_rest_of_the_app():
    """A reader who learned 1Y/3Y/Max on another page should not have to learn it
    again here."""
    fig = build(frame([1e9, 2e9, 3e9]))
    labels = [b.label for b in fig.layout.xaxis.rangeselector.buttons]
    assert labels == [f"{n}Y" for n in et.RANGE_YEARS] + ["Max"]


def test_the_buttons_sit_on_the_top_panel_where_they_render_above_the_figure():
    fig = build(frame([1e9, 2e9, 3e9]))
    assert not fig.layout.xaxis2.rangeselector.buttons


def test_the_figure_carries_the_rules_the_browser_needs_to_re_fit_it():
    """Plotly's autorange spans all of a trace's data rather than the part on screen, so
    the browser has to do the fitting, and it has to reach the same answer this module
    would."""
    spec = build(frame([1e9, 2e9, 3e9])).layout.meta[et.REFIT_META]
    assert spec["log_ratio_min"] == et.LOG_RATIO_MIN
    assert spec["price_axis"] == "yaxis"
    assert spec["pad"] == et.REFIT_PAD


def test_the_level_scale_fits_every_panel():
    spec = build(with_vol([1e9, 2e9, 3e9])).layout.meta[et.REFIT_META]
    assert spec["axes"] == ["yaxis", "yaxis2", "yaxis3", "yaxis4"]


def test_the_percentile_scale_fits_the_price_panel_and_nothing_else():
    """The panels below are pinned to 0-100 on purpose. Fitting them to a zoomed window
    would let the band at 10 and 90 drift off a scale that exists to stay put."""
    fig = et.build_figure(with_vol([1e9, 2e9, 3e9]), None, unit=et.UNIT_NOTIONAL,
                          colors=COLORS, palette=PALETTE, leg_label="Specs",
                          set_label="Equities", scale=et.SCALE_RANK)
    assert fig.layout.meta[et.REFIT_META]["axes"] == ["yaxis"]


def test_the_top_panel_is_the_axis_the_others_follow():
    """`shared_xaxes` makes the BOTTOM axis the master, and Plotly ignores a range set
    on a slave. The range buttons live on the top panel, so the top panel has to be the
    master or clicking 3Y does nothing at all."""
    fig = build(with_vol([1e9, 2e9, 3e9]))
    assert fig.layout.xaxis.matches is None
    assert [fig.layout[f"xaxis{n}"].matches for n in (2, 3, 4)] == ["x", "x", "x"]


def test_the_lens_hover_carries_the_SIDE_because_a_percentile_has_none():
    """The line's subject is a position, and a position has a side. The sign is not new
    information, since it matches the dollars above it in every market-week in the
    store, but a reader following this line should not have to reconstruct it from a
    different trace's hover."""
    df = frame([1e9, 2e9, 3e9])
    ranks = pd.Series([20.0, 40.0, 60.0], index=df.index)
    counts = pd.Series([-4616.0, 100.0, 23625.0], index=df.index)
    fig = et.build_figure(df, None, unit=et.UNIT_NOTIONAL, colors=COLORS,
                          palette=PALETTE, leg_label="Specs", set_label="Gold",
                          single=True, contracts=ranks, contract_counts=counts,
                          scale=et.SCALE_RANK)
    lens = next(t for t in fig.data if t.name == "Contracts %ile")
    # The side in WORDS beside an absolute magnitude, matching the prose above.
    assert [list(row) for row in lens.customdata] == [
        ["net short", 4616.0], ["net long", 100.0], ["net long", 23625.0]]
    assert "%{customdata[0]}" in lens.hovertemplate
    assert "contracts" in lens.hovertemplate


def test_the_side_is_words_and_the_size_is_absolute():
    """"net short -28,639" would be the fact twice, once wrongly."""
    idx = pd.date_range("2026-01-06", periods=3, freq="W-TUE")
    rows = et.side_and_size(pd.Series([-28639.0, 0.0, 3805.0], index=idx), idx)
    assert rows == [["net short", 28639.0], ["net long", 0.0], ["net long", 3805.0]]


def test_a_week_with_no_count_says_nothing_rather_than_guessing_a_side():
    idx = pd.date_range("2026-01-06", periods=2, freq="W-TUE")
    rows = et.side_and_size(pd.Series([float("nan"), 5.0], index=idx), idx)
    assert rows[0][0] == ""
    assert rows[1] == ["net long", 5.0]


def test_the_plus_format_that_plotly_silently_drops_is_not_used():
    """Measured in the browser: `%{customdata:+,.0f}` on -28639 renders "-28639",
    discarding the thousands separator along with the sign it was asked for, while
    `,.0f` renders "-28,639". A format that failed loudly would have been fine."""
    df = frame([1e9, 2e9, 3e9])
    idx = df.index
    fig = et.build_figure(df, None, unit=et.UNIT_NOTIONAL, colors=COLORS,
                          palette=PALETTE, leg_label="Specs", set_label="Gold",
                          single=True, contracts=pd.Series([20.0, 40.0, 60.0], index=idx),
                          contract_counts=pd.Series([-1.0, 2.0, 3.0], index=idx),
                          scale=et.SCALE_RANK)
    lens = next(t for t in fig.data if t.name == "Contracts %ile")
    assert "+," not in lens.hovertemplate


def test_the_lens_still_draws_without_the_counts():
    """The percentile is what the LINE is; the counts are what the hover adds. A caller
    that has only the first still gets a line rather than a traceback."""
    df = frame([1e9, 2e9, 3e9])
    ranks = pd.Series([20.0, 40.0, 60.0], index=df.index)
    fig = et.build_figure(df, None, unit=et.UNIT_NOTIONAL, colors=COLORS,
                          palette=PALETTE, leg_label="Specs", set_label="Gold",
                          single=True, contracts=ranks, scale=et.SCALE_RANK)
    lens = next(t for t in fig.data if t.name == "Contracts %ile")
    assert lens.customdata is None
    assert "customdata" not in lens.hovertemplate


def test_the_lens_is_grey_and_not_the_theme_text_colour():
    """It used vc.BRIGHTER_TEXT_COLOR, which is not neutral: viz_constants defines it as
    "#E2E8F0" and then reassigns it to Solarized base3 "#fdf6e3", a warm cream. At 55%
    on a dark ground that reads as yellow, one panel above Small Traders in amber, so a
    line that is not a trader group looked like one."""
    import viz_constants as vc
    df = frame([1e9, 2e9, 3e9])
    fig = et.build_figure(df, None, unit=et.UNIT_NOTIONAL, colors=COLORS,
                          palette=PALETTE, leg_label="Specs", set_label="Gold",
                          single=True, scale=et.SCALE_RANK,
                          contracts=pd.Series([20.0, 40.0, 60.0], index=df.index))
    lens = next(t for t in fig.data if t.name == "Contracts %ile")
    assert lens.line.color == hex_to_rgba(et.LENS_COLOR, et.LENS_ALPHA)
    assert lens.line.color != hex_to_rgba(vc.BRIGHTER_TEXT_COLOR, et.LENS_ALPHA)
    # Palette-independent: this line is the subject seen another way, not a series of
    # its own, so it claims no slot.
    assert et.LENS_COLOR not in PALETTE
