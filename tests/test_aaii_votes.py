"""The AAII votes card: three shares as read, the recent weeks, and the history block.
Store-free: every test injects its own bars."""
import json

import numpy as np
import pandas as pd
import pytest

from components import aaii_votes as av
from components import sentiment_static as st
from tests.test_sentiment import COLORS, PALETTE, _fixtures, _no_cot_store  # noqa: F401 (autouse)

WEEKS = pd.date_range("2024-01-04", periods=120, freq="W-THU")


def _legs_bars(weeks=WEEKS, drop=None, missing=None):
    """Bull/neutral/bear fractions that sum to 1, as the store serves them. `drop` removes
    one leg's reading on those dates; `missing` removes a leg's symbol altogether."""
    rng = np.random.default_rng(7)
    bull = rng.uniform(0.25, 0.5, len(weeks))
    neutral = rng.uniform(0.15, 0.35, len(weeks))
    frames = {av.LEGS[0][1]: bull, av.LEGS[1][1]: neutral, av.LEGS[2][1]: 1 - bull - neutral}
    frames = {k: pd.DataFrame({"Close": v}, index=weeks) for k, v in frames.items()}
    if drop is not None:
        sym, dates = drop
        frames[sym] = frames[sym].drop(dates)
    if missing is not None:
        del frames[missing]

    def get_bars(symbol, tier=None):
        if symbol not in frames:
            raise FileNotFoundError(symbol)
        return frames[symbol]
    return frames, get_bars


def test_the_legs_are_percent_and_a_week_missing_one_is_dropped_not_filled():
    frames, get_bars = _legs_bars(drop=(av.AAII_NEUTRAL, WEEKS[[5]]))
    legs = av.legs(get_bars)
    assert list(legs.columns) == ["bullish", "neutral", "bearish"]
    assert WEEKS[5] not in legs.index and len(legs) == len(WEEKS) - 1
    np.testing.assert_allclose(legs.sum(axis=1), 100.0)
    assert legs.loc[WEEKS[0], "bullish"] == pytest.approx(frames[av.LEGS[0][1]]["Close"].iloc[0] * 100)


def test_no_card_without_all_three_legs():
    _, get_bars = _legs_bars(missing=av.AAII_NEUTRAL)
    assert av.legs(get_bars) is None and av.read(get_bars) is None


def test_recent_weeks_are_the_last_four_newest_first():
    _, get_bars = _legs_bars()
    votes = av.read(get_bars)
    legs = av.legs(get_bars)
    assert list(votes.recent.index) == list(legs.index[::-1][:av.RECENT_WEEKS])
    assert votes.last == legs.index[-1].date() and votes.since == legs.index[0].date()
    pd.testing.assert_series_equal(votes.average, legs.mean())


def test_the_high_is_the_largest_share_of_the_last_year_only():
    frames, get_bars = _legs_bars()
    # A bigger bullish week just over a year before the newest must not count.
    old = WEEKS[-1] - pd.Timedelta(days=av.HIGH_DAYS + 7)
    frames[av.LEGS[0][1]].loc[old, "Close"] = 0.99
    frames[av.LEGS[1][1]].loc[old, "Close"] = 0.005
    frames[av.LEGS[2][1]].loc[old, "Close"] = 0.005
    votes = av.read(get_bars)
    legs = av.legs(get_bars)
    year = legs[legs.index > legs.index[-1] - pd.Timedelta(days=av.HIGH_DAYS)]
    for key in ("bullish", "neutral", "bearish"):
        value, when = votes.highs[key]
        assert value == pytest.approx(year[key].max()) and when == year[key].idxmax().date()
    assert votes.highs["bullish"][0] < 99


def test_the_figure_stacks_the_recent_weeks_and_places_each_high_on_its_own_row():
    _, get_bars = _legs_bars()
    votes = av.read(get_bars)
    fig = av.figure(votes, COLORS)
    assert fig.layout.barmode == "stack"
    recent = [t for t in fig.data if t.yaxis == "y"]
    history = [t for t in fig.data if t.yaxis == "y2"]
    assert [t.name for t in recent] == ["Bullish", "Neutral", "Bearish"]
    dates = [f"{d:%Y-%m-%d}" for d in votes.recent.index]
    for trace, key in zip(recent, ("bullish", "neutral", "bearish")):
        assert list(trace.y) == dates
        np.testing.assert_allclose(trace.x, votes.recent[key].round(1))
    # History: the average row stacks all three; each high row holds one leg only.
    rows = list(history[0].y)
    assert rows == ["Average", "Bullish high", "Neutral high", "Bearish high"]
    assert f"Since {votes.since:%Y}" in fig.layout.annotations[1].text
    for i, (trace, key) in enumerate(zip(history, ("bullish", "neutral", "bearish"))):
        assert trace.x[0] == pytest.approx(round(votes.average[key], 1))
        filled = [j for j, v in enumerate(trace.x[1:]) if v is not None]
        assert filled == [i] and trace.x[1 + i] == pytest.approx(round(votes.highs[key][0], 1))
    dated = [a.text.strip() for a in fig.layout.annotations[2:]]
    assert dated == [f"{votes.highs[k][1]:%Y-%m-%d}" for k in ("bullish", "neutral", "bearish")]


def test_the_figure_is_a_fixed_0_to_100_with_no_zoom():
    _, get_bars = _legs_bars()
    fig = av.figure(av.read(get_bars), COLORS)
    for axis in ("xaxis", "xaxis2"):
        assert list(fig.layout[axis].range) == av.X_RANGE and fig.layout[axis].fixedrange
    assert av.X_RANGE[0] == 0 and 100.2 < av.X_RANGE[1] < 101   # rounding room, no more
    assert fig.layout.yaxis.autorange == "reversed"       # newest week on top
    assert fig.layout.yaxis.type == fig.layout.yaxis2.type == "category"   # not dates
    # No legend (it wraps at phone width): the subtitle names each colour instead.
    assert fig.layout.showlegend is False
    assert all(w in av.SUBTITLE for w in ("(green)", "(grey)", "(red)"))
    colors = av.leg_colors(COLORS)
    assert colors["bullish"] == COLORS.bull and colors["bearish"] == COLORS.bear


# ── the published page ────────────────────────────────────────────────────────

def _reads():
    from components import sentiment as s
    _, get_bars = _fixtures()
    return {y: s.build_read(get_bars, lookback_years=y) for y in s.LOOKBACK_YEARS}


def _payload(html):
    m = html.split('<script type="application/json" id="surveys-data">', 1)[1]
    return json.loads(m.split("</script>", 1)[0].replace("<\\/", "</"))


def test_the_published_page_carries_the_card_once_when_votes_are_in():
    _, get_bars = _legs_bars()
    html = st.render(_reads(), COLORS, PALETTE, votes=av.read(get_bars))
    assert html.count(f'<div id="{st.VOTES_ID}">') == 1 and av.TITLE in html
    payload = _payload(html)
    assert st.VOTES_KEY in payload and payload[st.VOTES_KEY]["layout"]["barmode"] == "stack"
    # Once, beside the lookbacks, not inside each.
    assert all(st.VOTES_KEY not in v for k, v in payload.items() if k != st.VOTES_KEY)
    # Between the index card and the columns.
    assert html.index(f'id="{st.PRICE_ID}"') < html.index(f'id="{st.VOTES_ID}"') \
        < html.index(f'id="{st.COLUMNS_ID}"')


def test_without_votes_the_page_leaves_the_card_out():
    html = st.render(_reads(), COLORS, PALETTE)
    assert f'<div id="{st.VOTES_ID}">' not in html and st.VOTES_KEY not in _payload(html)
