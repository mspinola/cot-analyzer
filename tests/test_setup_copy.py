"""Positioning prose has to agree with the gate that produced the verdict.

The copy used to be one fixed set of sentences describing the Raw PF three-leg gate.
That was false under NPF, whose CS gate never reads the Large Spec leg, and it was
already false for equity index contracts under either model, since those gate on
Commercials alone and their speculator legs may sit anywhere.
"""
import cotmetrics.constants as const
import cotmetrics.models as models

import viz_constants as vc

STATES = (const.SETUP_BULL, const.SETUP_BEAR,
          const.SETUP_NEAR_BULL, const.SETUP_NEAR_BEAR, const.SETUP_NONE)


def _all(model, is_equity=False):
    return [vc.positioning_tooltip(s, model, is_equity) for s in STATES]


# ── the leg set ───────────────────────────────────────────────────────────────

def test_each_model_names_exactly_the_legs_its_gate_reads():
    assert vc.setup_legs(models.RAW_PF) == ["Large Speculators", "Small Traders"]
    assert vc.setup_legs(models.NPF) == ["Small Traders"]


def test_equities_name_no_speculator_legs_under_any_model():
    """They gate on Commercials alone, so naming a leg would invent a condition the
    setup never checked."""
    for m in models.MODELS:
        assert vc.setup_legs(m, is_equity=True) == []
        assert vc.setup_leg_phrase(m, is_equity=True) is None


def test_npf_copy_never_mentions_the_leg_it_does_not_gate_on():
    """The whole point. NPF's CS gate drops Large Specs, so no NPF sentence may claim
    anything about them."""
    for text in _all(models.NPF) + _all(models.NPF, is_equity=True):
        assert "Large Spec" not in text


def test_equity_copy_never_asserts_speculator_crowding():
    """This was already wrong before NPF existed: DOW is a bear setup on Commercials
    alone while its Small Specs sit mid-range, and the old text said they were
    heavily accumulated."""
    for m in models.MODELS:
        for text in _all(m, is_equity=True):
            assert "Large Spec" not in text and "Small Trader" not in text
            assert "does not gate equity index setups" in text


# ── the numbers come off the model ────────────────────────────────────────────

def test_no_sentence_quotes_the_other_model_s_band():
    """Only the upper bounds are compared: RAW_PF.low is 5, which is also
    SETUP_NEAR_WIDTH, so the lower bounds legitimately collide in the near states and
    a naive "no other number" check fails on correct copy."""
    for text in _all(models.NPF, False) + _all(models.NPF, True):
        assert "95" not in text
    for text in _all(models.RAW_PF, False) + _all(models.RAW_PF, True):
        assert "80" not in text


def test_the_band_is_actually_stated():
    bull = vc.positioning_tooltip(const.SETUP_BULL, models.NPF)
    assert "80" in bull and "20" in bull
    bull_raw = vc.positioning_tooltip(const.SETUP_BULL, models.RAW_PF)
    assert "95" in bull_raw and "5" in bull_raw


def test_near_states_quote_the_near_width():
    for m in models.MODELS:
        t = vc.positioning_tooltip(const.SETUP_NEAR_BULL, m)
        assert f"within {const.SETUP_NEAR_WIDTH} points" in t


# ── it reads like English ─────────────────────────────────────────────────────

def test_no_doubled_conjunction_or_empty_slots():
    for m in models.MODELS:
        for is_eq in (False, True):
            for text in _all(m, is_eq):
                assert "and and" not in text
                assert "  " not in text
                assert " ," not in text and " ." not in text
                assert text[0].isupper() and text.rstrip().endswith(".")


def test_a_single_leg_gate_does_not_say_at_least_one_of():
    """"at least one of Small Traders" is not a sentence."""
    t = vc.positioning_tooltip(const.SETUP_NEAR_BULL, models.NPF)
    assert "at least one of" not in t
    assert "with Small Traders also within" in t


def test_a_two_leg_gate_does_say_both():
    t = vc.positioning_tooltip(const.SETUP_BULL, models.RAW_PF)
    assert "are both at or below" in t


def test_join_uses_a_comma_only_beyond_two():
    assert vc._join(["A", "B"]) == "A and B"
    assert vc._join(["A", "B", "C"]) == "A, B and C"


def test_no_internal_identifier_leaks_into_user_copy():
    """`is_setup` used to appear verbatim in a column tooltip."""
    for m in models.MODELS:
        for is_eq in (False, True):
            for text in _all(m, is_eq):
                assert "is_setup" not in text and "_" not in text
