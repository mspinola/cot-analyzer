"""The say-against-do card: AAII's monthly bullish mean against the stocks share, each
ranked against its own prior months, and their gap. Store-free: every test injects
bars or builds frames by hand."""
import numpy as np
import pandas as pd
import pytest

from components import aaii_allocation as aa
from components import aaii_say_do as sd
from components import aaii_votes as av
from components import sentiment
from components import sentiment_static as st
from components.plot_colors import hex_to_rgba
from tests.test_aaii_votes import _payload, _reads
from tests.test_sentiment import COLORS, PALETTE, _no_cot_store  # noqa: F401 (autouse)


def _bars(n_months=48, start="2021-01-01"):
    """Weekly AAII votes and monthly allocation over the same span, as marketdata
    serves them (fractions), behind one `get_bars`."""
    weeks = pd.date_range(start, periods=n_months * 52 // 12, freq="W-THU")
    months = pd.date_range(weeks[0], periods=n_months, freq="ME")
    rng = np.random.default_rng(3)
    bull = rng.uniform(0.25, 0.5, len(weeks))
    neutral = rng.uniform(0.15, 0.35, len(weeks))
    stocks = rng.uniform(0.55, 0.72, len(months))
    bonds = rng.uniform(0.12, 0.2, len(months))
    frames = {av.LEGS[0][1]: (bull, weeks), av.LEGS[1][1]: (neutral, weeks),
              av.LEGS[2][1]: (1 - bull - neutral, weeks),
              aa.LEGS[0][1]: (stocks, months), aa.LEGS[1][1]: (bonds, months),
              aa.LEGS[2][1]: (1 - stocks - bonds, months)}
    frames = {k: pd.DataFrame({"Close": v}, index=i) for k, (v, i) in frames.items()}

    def get_bars(symbol, tier=None):
        if symbol not in frames:
            raise FileNotFoundError(symbol)
        return frames[symbol]
    return frames, get_bars


def test_bullish_is_a_monthly_mean_dated_on_the_month_end_short_months_dropped():
    weekly = pd.Series([30.0, 40.0, 50.0, 20.0, 10.0, 60.0],
                       index=pd.to_datetime(["2024-01-04", "2024-01-11", "2024-01-18",
                                             "2024-01-25", "2024-02-01", "2024-02-08"]))
    out = sd.monthly_bullish(weekly)
    # February has two readings, under MIN_WEEKS, so it is dropped rather than shown.
    assert list(out.index) == [pd.Timestamp("2024-01-31")]
    assert out.iloc[0] == pytest.approx(35.0)


def test_the_percentile_ranks_against_prior_months_only():
    s = pd.Series([1.0, 2.0, 3.0, 2.5, 0.5],
                  index=pd.date_range("2020-01-31", periods=5, freq="ME"))
    out = sd.trailing_percentile(s, n=3)
    assert out.iloc[:3].isna().all()
    # 2.5 against (1, 2, 3): two of three at or below, 67. The month is not its own history.
    assert out.iloc[3] == sentiment.percentile_of([1.0, 2.0, 3.0], 2.5) == 67
    # Below every prior month: floored at 1, never 0.
    assert out.iloc[4] == 1


def test_the_gap_is_bullish_percentile_minus_stocks_percentile_on_shared_months():
    _, get_bars = _bars()
    x = sd.read(get_bars)
    m = x.months
    # Only months both surveys cover, and the allocation's month-end dating.
    alloc = aa.legs(get_bars)
    assert set(m.index) <= set(alloc.index)
    assert x.last == m.index[-1].date()
    ranked = m.dropna(subset=["gap"])
    assert len(ranked) == len(m) - sd.WINDOW_MONTHS
    np.testing.assert_allclose(ranked["gap"], ranked["bullish_pct"] - ranked["stocks_pct"])
    assert ranked[["bullish_pct", "stocks_pct"]].stack().between(1, 100).all()


def test_either_survey_missing_means_no_card():
    frames, get_bars = _bars()
    for gone in (av.LEGS[0][1], aa.LEGS[0][1]):
        def without(symbol, tier=None, gone=gone):
            if symbol == gone:
                raise FileNotFoundError(symbol)
            return get_bars(symbol, tier)
        assert sd.read(without) is None


def test_the_figure_draws_spy_both_percentiles_and_the_gap_on_fixed_scales():
    _, get_bars = _bars()
    x = sd.read(get_bars)
    spy = _reads()[sentiment.DEFAULT_LOOKBACK].frame["spy"]
    fig = sd.figure(x, spy, COLORS)
    names = [t.name for t in fig.data]
    assert names == ["SPY", "Bullish vote", "Stocks held", "Say minus do"]
    assert [t.yaxis for t in fig.data] == ["y", "y2", "y2", "y3"]
    assert list(fig.layout.yaxis2.range) == sd.PCT_RANGE
    assert list(fig.layout.yaxis3.range) == sd.GAP_RANGE
    # The two lines are distinguishable: the votes green and the light grey.
    assert fig.data[1].line.color == sentiment.card_green(COLORS)
    assert fig.data[2].line.color == sd.DO_COLOR != fig.data[1].line.color
    # Each gap bar takes the colour of whichever line is ahead.
    gap = fig.data[3]
    say = hex_to_rgba(sentiment.card_green(COLORS), av.BAR_OPACITY)
    do = hex_to_rgba(sd.DO_COLOR, av.BAR_OPACITY)
    assert {v >= 0 for v in gap.y} == {True, False}
    assert list(gap.marker.color) == [say if v >= 0 else do for v in gap.y]
    far = sorted(sh.y0 for sh in fig.layout.shapes if sh.yref == "y3")
    assert far == [-sd.FAR_APART, sd.FAR_APART]
    # Only SPY refits on zoom; the lower panels keep their scales.
    assert fig.layout.meta == sentiment.PRICE_REFIT
    newest = x.months.dropna(subset=["gap"]).iloc[-1]
    assert f"{newest.name:%Y-%m}: {newest['gap']:+.0f}" in fig.layout.annotations[2].text


def test_without_spy_the_chart_still_draws():
    _, get_bars = _bars()
    fig = sd.figure(sd.read(get_bars), None, COLORS)
    assert [t.name for t in fig.data] == ["Bullish vote", "Stocks held", "Say minus do"]


def test_a_short_history_draws_plain_titles_and_no_summary():
    _, get_bars = _bars(n_months=20)
    x = sd.read(get_bars)
    assert x.months["gap"].isna().all()
    assert sd.summary(x) is None
    fig = sd.figure(x, None, COLORS)
    assert "<br>" not in fig.layout.annotations[1].text


def test_the_published_page_closes_with_the_card_drawn_once_and_refitted():
    _, get_bars = _bars()
    html = st.render(_reads(), COLORS, PALETTE, allocation=aa.read(get_bars),
                     say_do=sd.read(get_bars))
    assert html.count(f'<div id="{st.SAY_DO_ID}">') == 1 and sd.TITLE in html
    assert st.SAY_DO_KEY in _payload(html)
    assert html.index(f'id="{st.ALLOCATION_PRICE_ID}"') < html.index(f'id="{st.SAY_DO_ID}"') \
        < html.index('id="notes"')
    assert f"'{st.SAY_DO_ID}': '{st.SAY_DO_KEY}'" in html
    bare = st.render(_reads(), COLORS, PALETTE)
    assert f'id="{st.SAY_DO_ID}"' not in bare and st.SAY_DO_KEY not in _payload(bare)


def test_the_chart_opens_on_the_last_ten_years_with_the_rest_a_click_away():
    _, get_bars = _bars(n_months=12 * 16)
    x = sd.read(get_bars)
    fig = sd.figure(x, None, COLORS)
    last = x.months.index[-1]
    assert pd.Timestamp(fig.layout.xaxis.range[0]) == last - pd.DateOffset(years=sd.OPEN_YEARS)
    # The whole ranked history is still drawn, for the Max button.
    assert pd.Timestamp(fig.data[0].x[0]) == x.months.dropna(subset=["gap"]).index[0]
    # A history shorter than that opens on its first ranked month.
    short = sd.read(_bars()[1])
    fig = sd.figure(short, None, COLORS)
    assert pd.Timestamp(fig.layout.xaxis.range[0]) == short.months.dropna(
        subset=["gap"]).index[0]
