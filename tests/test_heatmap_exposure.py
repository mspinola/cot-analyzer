"""The two exposure columns the heatmap joins from cotmetrics.exposure.

The join is a display concern, so these tests are store-free: `attach_spec_risk` is
fed through a monkeypatched `_spec_risk`, and the percentile styling is evaluated the
way test_heatmap_styles evaluates every other condition string. The arithmetic behind
the numbers (risk_usd, expanding percentile) is cotmetrics' to test, not this repo's.
"""
import pandas as pd
import pytest

import viz_config
from pages.analytics import heatmap
from tests.test_heatmap_styles import _evaluate


@pytest.fixture(scope="module")
def colors():
    return heatmap.grid_colors(viz_config.get_palette(None))


def _matrix(rows):
    return pd.DataFrame(rows, columns=["Asset", "Date"])


# ── the join ──────────────────────────────────────────────────────────────────

def test_rows_join_on_their_own_week(monkeypatch):
    """Each row reads its OWN date, not the page's: with no target selected the
    markets show their latest weeks, and those can differ."""
    tables = {
        "Euro": {"2026-08-18": (-9.5e6, 29.4), "2026-08-11": (-8.0e6, 31.0)},
        "Bitcoin": {"2026-08-18": (1.7e7, 93.4)},
    }
    monkeypatch.setattr(heatmap, "_spec_risk", lambda asset, newest: tables.get(asset))
    df = _matrix([("Euro", "2026-08-11"), ("Bitcoin", "2026-08-18")])
    out = heatmap.attach_spec_risk(df, "2026-08-18")
    assert list(out["Spec Risk"]) == [-8.0e6, 1.7e7]
    assert list(out["Risk %ile"]) == [31.0, 93.4]


def test_a_market_without_dollars_stays_a_row(monkeypatch):
    """A market _spec_risk cannot price (None) or a week it does not carry gets None
    in both columns rather than dropping the row or raising: the rest of the matrix
    has nothing to do with one market's missing multiplier."""
    monkeypatch.setattr(
        heatmap, "_spec_risk",
        lambda asset, newest: {"2026-08-18": (1.0, 50.0)} if asset == "Euro" else None)
    df = _matrix([("Euro", "2026-08-18"), ("MSCI EAFE", "2026-08-18"),
                  ("Euro", "1999-01-05")])
    out = heatmap.attach_spec_risk(df, "2026-08-18")
    assert list(out["Spec Risk"]) == [1.0, None, None]
    assert list(out["Risk %ile"]) == [50.0, None, None]


def test_the_computation_failing_returns_none_not_a_traceback(monkeypatch):
    """The lru-cached fetch turns ANY failure into None. One market with a broken
    price read must not take the other 41 down with it."""
    heatmap._spec_risk.cache_clear()

    def boom(*a, **k):
        raise RuntimeError("no bars")

    monkeypatch.setattr(heatmap.exposure, "market_exposure", boom)
    try:
        assert heatmap._spec_risk("Euro", "2026-08-18") is None
    finally:
        heatmap._spec_risk.cache_clear()


# ── the percentile styling ────────────────────────────────────────────────────

def _verdict(style, colors, highlight):
    if style is None:
        return None
    return "lit" if style["color"] == highlight else "dim"


@pytest.mark.parametrize("value,expected", [
    (100.0, "lit"),
    (heatmap.RISK_RANK_HIGH, "lit"),
    (heatmap.RISK_RANK_HIGH - 1, "dim"),
    (50.0, "dim"),
    (heatmap.RISK_RANK_LOW + 1, "dim"),
    (heatmap.RISK_RANK_LOW, "lit"),
    (0.0, "lit"),
])
def test_both_tails_light_the_same_way(value, expected, colors):
    """95 and up is the most-long extreme, 5 and down the most-short, and both mean
    the same thing here: at an edge of this market's own history. Direction lives in
    the $ Risk sign, so neither tail gets a bull or bear colour."""
    styles = heatmap.risk_rank_styles_for(colors, highlight="#hilite")
    assert _verdict(_evaluate(styles, value, {}), colors, "#hilite") == expected


def test_null_does_not_read_as_zero(colors):
    """JS coerces null to 0 in comparisons, and 0 is inside the lit band, so an
    unguarded condition would light exactly the markets with no percentile yet. The
    emitted condition carries the null guard; evaluated here with None the way the
    browser would see null."""
    styles = heatmap.risk_rank_styles_for(colors, highlight="#hilite")
    lit = styles[0]["condition"]
    assert "params.value != null" in lit
    # And the guard short-circuits: with value absent, the row falls to dim.
    style = _evaluate(styles, None, {})
    assert style["color"] == colors.dim
