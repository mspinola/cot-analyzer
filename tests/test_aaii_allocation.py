"""The AAII asset allocation card: three shares as stored, the recent months, the
history block and stocks against their average. Store-free: every test injects bars."""
import json

import numpy as np
import pandas as pd
import pytest

from components import aaii_allocation as aa
from components import aaii_votes as av
from components import sentiment_static as st
from components.plot_colors import hex_to_rgba
from tests.test_aaii_votes import _legs_bars, _payload, _reads
from tests.test_sentiment import COLORS, PALETTE, _no_cot_store  # noqa: F401 (autouse)

MONTHS = pd.date_range("2023-01-31", periods=30, freq="ME")


def _alloc_bars(months=MONTHS, missing=None, high_old=False):
    """Stocks/bonds/cash fractions summing to 1, as marketdata serves the AAII_ALLOC_*
    series. `high_old` puts a stocks share higher than any recent one 13 months back."""
    rng = np.random.default_rng(11)
    stocks = rng.uniform(0.55, 0.72, len(months))
    bonds = rng.uniform(0.12, 0.2, len(months))
    if high_old:
        stocks[-14], bonds[-14] = 0.79, 0.1
    frames = {aa.LEGS[0][1]: stocks, aa.LEGS[1][1]: bonds,
              aa.LEGS[2][1]: 1 - stocks - bonds}
    frames = {k: pd.DataFrame({"Close": v}, index=months) for k, v in frames.items()}
    if missing:
        del frames[missing]

    def get_bars(symbol, tier=None):
        if symbol not in frames:
            raise FileNotFoundError(symbol)
        return frames[symbol]
    return frames, get_bars


def test_the_shares_are_percent_and_need_all_three():
    _, get_bars = _alloc_bars()
    legs = aa.legs(get_bars)
    assert list(legs.columns) == ["stocks", "bonds", "cash"]
    np.testing.assert_allclose(legs.sum(axis=1), 100.0)
    _, partial = _alloc_bars(missing="AAII_ALLOC_BONDS")
    assert aa.legs(partial) is None and aa.read(partial) is None


def test_recent_months_newest_first_average_and_last_years_highs():
    _, get_bars = _alloc_bars(high_old=True)
    alloc = aa.read(get_bars)
    legs = aa.legs(get_bars)
    assert list(alloc.recent.index) == list(legs.index[::-1][:aa.RECENT_MONTHS])
    pd.testing.assert_series_equal(alloc.average, legs.mean())
    year = legs[legs.index > legs.index[-1] - pd.Timedelta(days=aa.HIGH_DAYS)]
    assert len(year) == 12
    for key in ("stocks", "bonds", "cash"):
        assert alloc.highs[key] == (pytest.approx(year[key].max()), year[key].idxmax().date())
    assert alloc.highs["stocks"][0] < 79      # the older, higher month is outside the year
    assert alloc.last == MONTHS[-1].date() and alloc.since == MONTHS[0].date()


def test_the_blocks_label_months_and_line_up():
    _, get_bars = _alloc_bars()
    alloc = aa.read(get_bars)
    recent, history, gap = aa.figures(alloc, COLORS)
    months = [f"{d:%Y-%m}" for d in alloc.recent.index]
    assert list(recent.data[0].y) == months and list(gap.data[0].y) == months
    assert list(history.data[0].y) == ["Average", "Stocks high", "Bonds high", "Cash high"]
    assert len({f.layout.height for f in (recent, history, gap)}) == 1
    for trace, key in zip(recent.data, ("stocks", "bonds", "cash")):
        np.testing.assert_allclose(trace.x, alloc.recent[key].round(1))
    dated = [a.text.strip() for a in history.layout.annotations[:3]]
    assert dated == [f"{alloc.highs[k][1]:%Y-%m}" for k in ("stocks", "bonds", "cash")]


def test_stocks_against_the_average_on_a_fixed_scale():
    _, get_bars = _alloc_bars()
    alloc = aa.read(get_bars)
    gap = aa.figures(alloc, COLORS)[2]
    avg = alloc.average["stocks"]
    want = (alloc.recent["stocks"] - avg).round(1)
    bar = gap.data[0]
    np.testing.assert_allclose(bar.x, want)
    assert list(bar.text) == [f"{v:+.1f}" for v in want]
    for v, c in zip(want, bar.marker.color):
        assert c == hex_to_rgba(COLORS.bull if v >= 0 else COLORS.bear, av.BAR_OPACITY)
    assert list(gap.layout.xaxis.range) == [-aa.STOCK_GAP_LIMIT, aa.STOCK_GAP_LIMIT]
    assert gap.layout.annotations[0].text == f"Stocks vs average ({avg:.1f}%)"


def test_a_gap_beyond_the_scale_is_pinned_but_labelled_true():
    frames, get_bars = _alloc_bars()
    for sym, v in zip((aa.LEGS[0][1], aa.LEGS[1][1], aa.LEGS[2][1]), (0.99, 0.005, 0.005)):
        frames[sym].iloc[-1, 0] = v
    alloc = aa.read(get_bars)
    bar = aa.figures(alloc, COLORS)[2].data[0]
    assert bar.x[0] == aa.STOCK_GAP_LIMIT
    assert bar.text[0] == f"{99 - alloc.average['stocks']:+.1f}"


def test_the_published_page_carries_the_card_after_the_votes_card():
    _, votes_bars = _legs_bars()
    _, alloc_bars = _alloc_bars()
    html = st.render(_reads(), COLORS, PALETTE, votes=av.read(votes_bars),
                     allocation=aa.read(alloc_bars))
    assert html.count(f'<div id="{st.ALLOCATION_ID}" class="votes-grid">') == 1
    assert aa.TITLE in html
    payload = _payload(html)
    assert set(payload[st.ALLOCATION_KEY]) == set(st.ALLOCATION_BLOCKS)
    assert html.index(f'id="{st.VOTES_ID}"') < html.index(f'id="{st.ALLOCATION_ID}"') \
        < html.index(f'id="{st.COLUMNS_ID}"')
    # One JS loop draws every block-grid card.
    assert json.dumps([list(c) for c in st.GRID_CARDS], separators=(",", ":")) in html


def test_without_the_survey_the_page_leaves_the_card_out():
    html = st.render(_reads(), COLORS, PALETTE)
    assert f'id="{st.ALLOCATION_ID}"' not in html
    assert st.ALLOCATION_KEY not in _payload(html)


def test_share_labels_carry_no_percent_sign_so_narrow_segments_keep_them():
    _, get_bars = _alloc_bars()
    recent, history, _ = aa.figures(aa.read(get_bars), COLORS)
    labels = [t for f in (recent, history) for tr in f.data for t in tr.text if t]
    assert labels and not any("%" in t for t in labels)
    assert "percent of portfolio" in aa.SUBTITLE
