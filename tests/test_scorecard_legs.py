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
"""
import cotmetrics.constants as const
import cotmetrics.models as models
import pytest

import components.scorecard_rows as sr
import viz_constants as vc
from pages.analytics.scorecard import _legs_for

LATEST = {"comm": 94.0, "noncomm": 7.0, "nonrept": 6.0}


def record(is_equity=False):
    return {const.IS_EQUITY_COL: is_equity}


def shorts(legs):
    return [leg.short for leg in legs]


@pytest.mark.parametrize("model,expected", [
    (models.RAW_PF, ["Comm", "NonComm", "NonRept"]),
    (models.NPF, ["Comm", "NonRept"]),
    (models.NPF_CLS_95_5, ["Comm", "NonComm", "NonRept"]),
])
def test_the_legs_are_the_ones_the_model_gates_on(model, expected):
    assert shorts(_legs_for(LATEST, record(), model)) == expected


def test_npf_draws_no_non_commercial_lane():
    """Its CS gate never reads that leg. Drawing it would show a reading the verdict
    above it ignored."""
    assert vc.LEG_SHORT[models.LEG_LARGE] not in shorts(
        _legs_for(LATEST, record(), models.NPF))


@pytest.mark.parametrize("model", models.MODELS)
def test_an_equity_index_contract_gates_on_commercials_alone(model):
    """True under every model, so it cannot be folded into the spec_legs check."""
    assert shorts(_legs_for(LATEST, record(is_equity=True), model)) == ["Comm"]


@pytest.mark.parametrize("model", models.MODELS)
def test_commercials_are_always_the_first_lane(model):
    for rec in (record(), record(is_equity=True)):
        legs = _legs_for(LATEST, rec, model)
        assert legs[0].short == vc.LEG_SHORT[vc.LEG_COMM]
        assert legs[0].direction == sr.BULL_HIGH


@pytest.mark.parametrize("model", models.MODELS)
def test_every_speculator_leg_reads_low_as_bullish(model):
    """The mirror of Commercials, under positioning fade. The lane carries identity
    so the colour is free to carry the verdict, and the verdict needs a direction."""
    for leg in _legs_for(LATEST, record(), model)[1:]:
        assert leg.direction == sr.BULL_LOW


def test_a_leg_the_frame_cannot_supply_still_takes_its_lane():
    """A column missing from the frame must not silently shorten the gate's leg set,
    because then the card would claim a two-leg gate where there is a three-leg one.
    The lane stays and the dot is what goes missing."""
    legs = _legs_for({"comm": 94.0, "nonrept": 6.0}, record(), models.RAW_PF)
    assert shorts(legs) == ["Comm", "NonComm", "NonRept"]
    assert legs[1].value is None


def test_the_values_come_from_the_matching_columns():
    legs = _legs_for(LATEST, record(), models.RAW_PF)
    assert [leg.value for leg in legs] == [94.0, 7.0, 6.0]
