"""Which markets a class starts with.

The page's whole discipline is that an aggregate is a claim about a set, so the set it
opens on is a decision with the same weight as any filter, and it is made once here
rather than per reader.
"""
import dash

dash.Dash(__name__, use_pages=True, pages_folder='')

from pages.analytics.exposure import DEFAULT_MEMBERS  # noqa: E402


def test_equities_starts_from_the_four_US_majors():
    """The class holds eight and three of them cost the aggregate something before a
    reader touches a control: MFS and MME have no contract multiplier so they are
    dropped every time, and NKD's COT history ends 2026-03-03 so a whole-class total
    stops there while the rest runs to the current week.

    Measured across the three candidate sets:

        ES NQ YM RTY   1247 weeks, 2002-08-13 to 2026-08-18, nothing dropped
        + EMD          1239 weeks, 2002-11-05 to 2026-08-18, nothing dropped
        whole class    1109 weeks, 2002-11-05 to 2026-03-03, two dropped

    So the majors are not a narrower view of the same thing. They are the only one of
    the three that reaches the present with every member priced.
    """
    assert DEFAULT_MEMBERS["Equities"] == ("ES", "NQ", "YM", "RTY")


def test_the_two_unpriceable_equity_markets_are_not_in_the_starting_set():
    """MFS and MME are ICE MSCI futures priced off ETF proxies, and an ETF share is not
    a contract, so they have no multiplier and contribute nothing but a dropped-market
    notice."""
    for symbol in ("MFS", "MME"):
        assert symbol not in DEFAULT_MEMBERS["Equities"]


def test_the_market_that_truncates_the_series_is_not_in_the_starting_set():
    assert "NKD" not in DEFAULT_MEMBERS["Equities"]


def test_only_the_class_that_needed_a_preset_has_one():
    """Anything not listed starts whole. A preset is a claim that the obvious set is the
    wrong one, and it should have to be argued per class rather than assumed."""
    assert set(DEFAULT_MEMBERS) == {"Equities"}
