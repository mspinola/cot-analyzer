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
