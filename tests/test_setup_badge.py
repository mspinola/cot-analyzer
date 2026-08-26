"""The setups badge, which is the only place a card says how old a setup is.

Age earned that slot on a measurement rather than a preference: over 551 market-weeks
at or approaching a gate, tape bias, WillCo and the six-week move never once pointed
against the positioning beside them, so drawing those on a setup card restates its own
strip. Age is the reading that does not, which is why it is worth the pixels and they
are not.
"""
import cotmetrics.constants as const
import cotmetrics.models as models

import viz_config
from components.signal_cards import positioning_card

PALETTE = viz_config.get_palette(None)


def _row(setup, weeks):
    return {"asset": "Corn", "index": 97, "lrg_index": 3, "sml_index": 2,
            "delta": 4, "lrg_delta": -2, "sml_delta": 0,
            "setup": setup, "setup_weeks": weeks, "is_equity": False}


def _text(node):
    """Every string in a component tree, in order."""
    if node is None:
        return []
    if isinstance(node, str):
        return [node]
    if isinstance(node, (list, tuple)):
        return [t for n in node for t in _text(n)]
    return _text(getattr(node, "children", None))


def _titles(node):
    out = []
    if node is None or isinstance(node, str):
        return out
    if isinstance(node, (list, tuple)):
        return [t for n in node for t in _titles(n)]
    if getattr(node, "title", None):
        out.append(node.title)
    return out + _titles(getattr(node, "children", None))


def _card_text(setup, weeks, weight="featured"):
    return "".join(_text(positioning_card(_row(setup, weeks), models.NPF, PALETTE,
                                          weight=weight)))


def test_a_setup_says_how_long_it_has_been_one():
    text = _card_text(const.SETUP_BULL, 3)
    assert "SETUP" in text and "· 3w" in text


def test_an_approaching_row_is_aged_too():
    assert "· 6w" in _card_text(const.SETUP_NEAR_BEAR, 6)


def test_an_unaged_row_shows_a_bare_badge():
    """A board built before ages existed, or a row the walk could not age. The badge
    must not print a dangling separator."""
    for weeks in (0, None):
        text = _card_text(const.SETUP_BULL, weeks)
        assert "SETUP" in text
        assert "· " not in text.split("SETUP")[1][:6]


def test_a_market_with_no_setup_has_no_badge_to_age():
    text = _card_text(const.SETUP_NONE, 4, weight="screener")
    assert "SETUP" not in text and "NEAR" not in text and "4w" not in text


def test_a_capped_age_reads_as_at_least():
    """setup_age_from returns the cap when the walk reaches it, so the card must not
    present that number as exact."""
    text = _card_text(const.SETUP_BULL, const.SETUP_AGE_CAP)
    assert f"{const.SETUP_AGE_CAP}w+" in text


def test_the_age_is_explained_on_hover_and_counts_weeks_in_english():
    one = " ".join(_titles(positioning_card(_row(const.SETUP_BULL, 1), models.NPF,
                                            PALETTE)))
    many = " ".join(_titles(positioning_card(_row(const.SETUP_BULL, 5), models.NPF,
                                             PALETTE)))
    assert "1 consecutive week," in one
    assert "5 consecutive weeks," in many


def test_every_weight_ages_the_same_way():
    """One card at three weights, so the badge cannot say different things in the strip
    and in the screener below it. That divergence is the defect this card exists to
    prevent, and age is one more thing it could diverge on."""
    for weight in ("featured", "near", "screener"):
        assert "· 2w" in _card_text(const.SETUP_BULL, 2, weight=weight)
