"""Which legs the Scorecard draws, which is the model's answer and not the page's.

The card shipped with two fixed rows, Commercials and Non-Reportables. That matches
NPF's CS gate and is wrong under both CLS gates, which read the Non-Commercial leg
too, so under the model the page OPENS on it was hiding a gate input: a market with
extreme Commercials and no chip had no visible explanation. These pin the rule the
two surfaces that already had it right follow (`signal_cards.strip_legs` and
`strip_traces.LEG_COLUMNS`):

- every gate reads Commercials, so they are always lane one
- the speculator legs are exactly `model.spec_legs`
- an equity index contract gates on Commercials ALONE, whatever the model

A leg drawn that the gate does not read puts a condition on the card the verdict
never checked. A leg omitted that it does read leaves the verdict unexplained. Both
look plausible on screen, which is why they are held by test.

The third rule is the window: the dots are the matrix row's own readings, the ones
the gate evaluated, never the uniform 52-week rows. On 52 weeks 6A's Non-Reportables
drew at 27 under a blank Raw PF chip whose real blocker was that leg at 55.
"""
import cotmetrics.constants as const
import cotmetrics.models as models
import pytest

import components.scorecard_rows as sr
import viz_config
import viz_constants as vc
from components.strip_traces import LEG_COLUMNS
from pages.analytics.scorecard import _legs_for

PALETTE = viz_config.get_palette("Muted")
#: One reading per leg, the same on both bases, so a test about WHICH legs appear
#: does not depend on which basis the model reads.
READINGS = {"comm": 94.0, models.LEG_LARGE: 7.0, models.LEG_SMALL: 6.0}


def legs_for(rec, model, palette=PALETTE):
    return _legs_for(rec, model, palette)


def record(is_equity=False, readings=READINGS, **columns):
    """A Signal Matrix row: every model's leg columns filled from `readings`."""
    row = {const.IS_EQUITY_COL: is_equity}
    for table in LEG_COLUMNS.values():
        for leg, column in table.items():
            if leg in readings:
                row[column] = readings[leg]
    row.update(columns)
    return row


def shorts(legs):
    return [leg.short for leg in legs]


@pytest.mark.parametrize("model,expected", [
    (models.RAW_PF, ["Comm", "NonComm", "NonRept"]),
    (models.NPF, ["Comm", "NonRept"]),
    (models.NPF_CLS_95_5, ["Comm", "NonComm", "NonRept"]),
])
def test_the_legs_are_the_ones_the_model_gates_on(model, expected):
    assert shorts(legs_for(record(), model)) == expected


def test_npf_draws_no_non_commercial_lane():
    """Its CS gate never reads that leg. Drawing it would show a reading the verdict
    above it ignored."""
    assert vc.LEG_SHORT[models.LEG_LARGE] not in shorts(
        legs_for(record(), models.NPF))


@pytest.mark.parametrize("model", models.MODELS)
def test_an_equity_index_contract_gates_on_commercials_alone(model):
    """True under every model, so it cannot be folded into the spec_legs check."""
    assert shorts(legs_for(record(is_equity=True), model)) == ["Comm"]


@pytest.mark.parametrize("model", models.MODELS)
def test_commercials_are_always_the_first_lane(model):
    for rec in (record(), record(is_equity=True)):
        legs = legs_for(rec, model)
        assert legs[0].short == vc.LEG_SHORT[vc.LEG_COMM]
        assert legs[0].direction == sr.BULL_HIGH


@pytest.mark.parametrize("model", models.MODELS)
def test_every_speculator_leg_reads_low_as_bullish(model):
    """The mirror of Commercials, under positioning fade. The lane carries identity
    so the colour is free to carry the verdict, and the verdict needs a direction."""
    for leg in legs_for(record(), model)[1:]:
        assert leg.direction == sr.BULL_LOW


def test_a_leg_the_frame_cannot_supply_still_takes_its_lane():
    """A column missing from the frame must not silently shorten the gate's leg set,
    because then the card would claim a two-leg gate where there is a three-leg one.
    The lane stays and the dot is what goes missing."""
    legs = legs_for(record(readings={"comm": 94.0, models.LEG_SMALL: 6.0}),
                    models.RAW_PF)
    assert shorts(legs) == ["Comm", "NonComm", "NonRept"]
    assert legs[1].value is None


def test_the_values_come_from_the_matching_columns():
    legs = legs_for(record(), models.RAW_PF)
    assert [leg.value for leg in legs] == [94.0, 7.0, 6.0]


# ── the window: the gate's own readings ──────────────────────────────────────

@pytest.mark.parametrize("model", models.MODELS)
def test_each_lane_reads_the_column_the_models_gate_reads(model):
    """`LEG_COLUMNS` is the Strip's map from a model to its matrix columns, i.e. the
    model's basis on the model's tuned window. Distinct values per column prove the
    lane read THAT column and not a neighbour on the other basis."""
    columns = LEG_COLUMNS[model.key]
    rec = record()
    for n, column in enumerate(columns.values()):
        rec[column] = 10.0 + n
    legs = legs_for(rec, model)
    assert [leg.value for leg in legs] == [10.0 + n for n in range(len(columns))]


def test_raw_and_normalized_models_draw_their_own_basis():
    rec = record(**{"Comm Index": 100.0, "Comm Index Norm": 80.0})
    assert legs_for(rec, models.RAW_PF)[0].value == 100.0
    assert legs_for(rec, models.NPF)[0].value == 80.0


def test_6a_draws_the_leg_that_blocked_its_chip():
    """The case that moved the lanes off the uniform window. 6A, 2026-10-20, Raw PF:
    Commercials 100 and Non-Commercials 0 on the 80-week tuned window, but
    Non-Reportables at 55, past neutral against the bull, so no near setup. On 52
    weeks that leg read 27 and the card showed a bull-side dot under a blank chip.
    The lane must draw the 55."""
    rec = record(**{"Comm Index": 100.0, "Lrg Index": 0.0, "Sml Index": 55.0,
                    const.SETUP_CLS_COL: const.SETUP_NONE})
    nonrept = legs_for(rec, models.RAW_PF)[2]
    assert nonrept.short == vc.LEG_SHORT[models.LEG_SMALL]
    assert nonrept.value == 55.0
    assert nonrept.value > const.INDEX_NEUTRAL      # on the wrong side, visibly


# ── the colour split ─────────────────────────────────────────────────────────

def test_commercials_take_the_verdict_colour_not_their_slot():
    """Palette slot 0 IS the bear red, so colouring that lane by identity draws a
    bullish Commercial reading in red. signal_cards records the same decision at
    COMM_LANE_TAKES_LEG_COLOUR. `hue` of None means "the verdict decides"."""
    comm = legs_for(record(), models.RAW_PF)[0]
    assert comm.hue is None


@pytest.mark.parametrize("model", [models.RAW_PF, models.NPF_CLS_95_5])
def test_speculator_legs_take_the_apps_colour_for_that_leg(model):
    """So the lanes read as the same legs the Strip and the home card draw. Their
    verdict is carried by the zone the dot lands in, so identity costs nothing."""
    by_short = {leg.short: leg for leg in legs_for(record(), model)}
    assert by_short["NonComm"].hue == PALETTE[1]
    assert by_short["NonRept"].hue == PALETTE[2]


def test_the_leg_colours_follow_the_palette():
    other = viz_config.get_palette("Solarized")
    legs = legs_for(record(), models.RAW_PF, palette=other)
    assert legs[1].hue == other[1] and legs[1].hue != PALETTE[1]
