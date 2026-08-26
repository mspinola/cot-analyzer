"""The heatmap's Setups filter, and what the collapsed asset-class control says.

The filter is a UNION across the two models, which is the only rule that cannot
contradict the grid it filters: the page reports Raw CLS 95/5 and NPF CS 80/20 side by
side and has no model selector, so filtering on one would hide rows the other block is
lit up about. The two bands are independent rather than nested, so this is not a
theoretical case.
"""
import cotmetrics.constants as const
import pandas as pd

from pages.analytics.heatmap import (
    SETUP_FILTER_ALL,
    SETUP_FILTER_GATE,
    SETUP_FILTER_NEAR,
    filter_by_setup,
)


def _df(*rows):
    """(asset, cls_state, npf_state) per row."""
    return pd.DataFrame(
        [{"Asset": a, const.SETUP_CLS_COL: c, const.SETUP_NPF_COL: n}
         for a, c, n in rows])


BOARD = _df(
    ("Both", const.SETUP_BULL, const.SETUP_BULL),
    ("CLS only", const.SETUP_BEAR, const.SETUP_NONE),
    ("NPF only", const.SETUP_NONE, const.SETUP_BEAR),
    ("CLS near only", const.SETUP_NEAR_BULL, const.SETUP_NONE),
    ("NPF near only", const.SETUP_NONE, const.SETUP_NEAR_BEAR),
    ("Neither", const.SETUP_NONE, const.SETUP_NONE),
)


def _assets(df):
    return list(df["Asset"])


# ── the union rule ────────────────────────────────────────────────────────────

def test_all_markets_filters_nothing():
    assert _assets(filter_by_setup(BOARD, SETUP_FILTER_ALL)) == _assets(BOARD)


def test_an_unknown_mode_filters_nothing():
    """The value is session-persisted, so a stale client can send anything. Falling
    through to the unfiltered grid is the safe direction: it shows more, not less."""
    for mode in (None, "", "setups", "gate "):
        assert _assets(filter_by_setup(BOARD, mode)) == _assets(BOARD)


def test_either_model_keeps_a_row_at_a_gate():
    assert _assets(filter_by_setup(BOARD, SETUP_FILTER_GATE)) == [
        "Both", "CLS only", "NPF only"]


def test_a_gate_filter_excludes_rows_that_are_only_approaching():
    kept = _assets(filter_by_setup(BOARD, SETUP_FILTER_GATE))
    assert "CLS near only" not in kept and "NPF near only" not in kept


def test_approaching_admits_both_tiers_on_either_model():
    assert _assets(filter_by_setup(BOARD, SETUP_FILTER_NEAR)) == [
        "Both", "CLS only", "NPF only", "CLS near only", "NPF near only"]


def test_a_market_neither_model_speaks_about_never_survives():
    for mode in (SETUP_FILTER_GATE, SETUP_FILTER_NEAR):
        assert "Neither" not in _assets(filter_by_setup(BOARD, mode))


def test_the_near_set_contains_the_gate_set():
    """Widening the filter may only add rows. If these ever came apart, "At or
    approaching" could hide a market that "At a gate" showed."""
    gate = set(_assets(filter_by_setup(BOARD, SETUP_FILTER_GATE)))
    assert gate <= set(_assets(filter_by_setup(BOARD, SETUP_FILTER_NEAR)))


def test_an_empty_frame_survives_every_mode():
    empty = BOARD.iloc[0:0]
    for mode in (SETUP_FILTER_ALL, SETUP_FILTER_GATE, SETUP_FILTER_NEAR):
        assert filter_by_setup(empty, mode).empty


def test_the_filter_values_are_a_wire_format():
    """They are persisted in a session-scoped control, so renaming one resets a
    returning reader's filter rather than migrating it."""
    assert (SETUP_FILTER_ALL, SETUP_FILTER_GATE, SETUP_FILTER_NEAR) == (
        "all", "gate", "near")
