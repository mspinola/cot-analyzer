"""The NAAIM card: recent readings, their changes, the history block and the percentile
rows. Store-free: every test injects its own bars."""
import json

import numpy as np
import pandas as pd
import pytest

from components import naaim_card as nc
from components import sentiment as s
from components import sentiment_static as st
from tests.test_sentiment import COLORS, PALETTE, _fixtures, _no_cot_store  # noqa: F401 (autouse)

#: Wednesdays from 2020, about five years, then three provisional weeks after the end.
WEEKS = pd.date_range("2020-01-01", periods=260, freq="W-WED")
LATE = pd.date_range(WEEKS[-1] + pd.Timedelta(days=7), periods=3, freq="W-WED")


def _naaim_bars(provisional=True, values=None):
    rng = np.random.default_rng(11)
    vals = values if values is not None else rng.uniform(10, 110, len(WEEKS))
    frames = {s.NAAIM: pd.DataFrame({"Close": vals}, index=WEEKS)}
    if provisional:
        # The first provisional week repeats an official date: marketdata trims it,
        # and the card must not count it twice if a stale copy does not.
        idx = WEEKS[-1:].append(LATE)
        frames[s.NAAIM_PROVISIONAL] = pd.DataFrame({"Close": [1.0, 55.0, 61.0, 47.5]},
                                                   index=idx)

    def get_bars(symbol, tier=None):
        if symbol not in frames:
            raise FileNotFoundError(symbol)
        return frames[symbol]
    return frames, get_bars


def test_no_card_without_the_official_series():
    def get_bars(symbol, tier=None):
        raise FileNotFoundError(symbol)
    assert nc.read(get_bars) is None


def test_recent_weeks_take_the_provisional_ones_newest_first_with_their_changes():
    frames, get_bars = _naaim_bars()
    n = nc.read(get_bars)
    assert list(n.recent.index) == [LATE[2], LATE[1], LATE[0], WEEKS[-1]]
    assert list(n.recent) == [47.5, 61.0, 55.0, frames[s.NAAIM]["Close"].iloc[-1]]
    official = frames[s.NAAIM]["Close"]
    assert list(n.change.round(6)) == pytest.approx(
        [-13.5, 6.0, 55.0 - official.iloc[-1], official.iloc[-1] - official.iloc[-2]])
    assert n.last == LATE[-1].date() and n.provisional == tuple(LATE)
    assert n.since == WEEKS[0].date()


def test_the_long_run_numbers_stay_official_and_the_year_takes_every_week_shown():
    frames, get_bars = _naaim_bars()
    n = nc.read(get_bars)
    official = frames[s.NAAIM]["Close"]
    assert n.average == pytest.approx(official.mean())
    assert n.recent_pct[0] == s.percentile_of(official.to_numpy(), 47.5)
    shown = pd.concat([official, pd.Series([55.0, 61.0, 47.5], index=LATE)])
    year = shown[shown.index > LATE[-1] - pd.Timedelta(days=nc.YEAR_DAYS)]
    assert n.year["average"] == pytest.approx(year.mean())
    assert n.year["high"] == (year.max(), year.idxmax().date())
    assert n.year["low"] == (year.min(), year.idxmin().date())


def test_the_percentile_rows_rank_the_newest_week_against_three_histories():
    frames, get_bars = _naaim_bars()
    n = nc.read(get_bars)
    official = frames[s.NAAIM]["Close"]
    shown = pd.concat([official, pd.Series([55.0, 61.0], index=LATE[:2])])
    labels = [row[0] for row in n.latest]
    assert labels == [f"Since {WEEKS[0]:%Y}", "Last 3 years", "Last year"]
    assert n.latest[0][1:3] == (s.percentile_of(official.to_numpy(), 47.5),
                                s.percentile_word(official.to_numpy(), 47.5))
    # A window ranks against its EARLIER weeks, provisional included.
    year = shown[shown.index > LATE[-1] - pd.Timedelta(days=nc.YEAR_DAYS)]
    assert n.latest[2][1] == s.percentile_of(year.to_numpy(), 47.5)
    assert n.latest[0][3].endswith(f"percentile of every week since {WEEKS[0]:%Y}")


def test_a_record_reading_says_so_in_its_hover():
    vals = np.linspace(20, 80, len(WEEKS))
    _, get_bars = _naaim_bars(provisional=False, values=vals)
    n = nc.read(get_bars)
    assert n.latest[0][2] == s.HIGHEST
    assert n.latest[0][3] == f"highest of every week since {WEEKS[0]:%Y}"


def test_the_three_blocks_share_one_height_and_fixed_scales():
    _, get_bars = _naaim_bars()
    figs = nc.figures(nc.read(get_bars), COLORS, PALETTE)
    assert len(figs) == 3 and len({f.layout.height for f in figs}) == 1
    recent, change, history = figs
    assert list(recent.layout.xaxis.range) == nc.X_RANGE
    assert list(history.layout.xaxis.range) == nc.X_RANGE
    assert list(change.layout.xaxis.range) == [-nc.CHANGE_LIMIT, nc.CHANGE_LIMIT]
    assert recent.data[0].text[0] == f"47.5 ({s.ordinal(nc.read(get_bars).recent_pct[0])})"
    # The labels sit past the bar's end, clear of the dashed average.
    assert list(recent.data[0].textposition) == ["outside"] * 4


def test_a_long_history_bar_carries_its_date_inside():
    vals = np.full(len(WEEKS), 50.0)
    vals[-3] = 101.0
    _, get_bars = _naaim_bars(provisional=False, values=vals)
    history = nc.history_figure(nc.read(get_bars), PALETTE)
    high, low = history.layout.annotations[0], history.layout.annotations[1]
    assert high.x == 0.0 and high.text.strip() == f"{WEEKS[-3]:%Y-%m-%d}"
    assert low.x == 50.0


def _reads():
    _, get_bars = _fixtures()
    return {y: s.build_read(get_bars, lookback_years=y) for y in s.LOOKBACK_YEARS}


def _payload(html):
    m = html.split('<script type="application/json" id="surveys-data">', 1)[1]
    return json.loads(m.split("</script>", 1)[0].replace("<\\/", "</"))


def test_the_published_page_leads_with_the_naaim_card():
    from components import aaii_votes as av
    from tests.test_aaii_votes import _legs_bars
    naaim = nc.read(_naaim_bars()[1])
    html = st.render(_reads(), COLORS, PALETTE, naaim=naaim, votes=av.read(_legs_bars()[1]))
    assert html.count(f'<div id="{st.NAAIM_ID}" class="votes-grid">') == 1 and nc.TITLE in html
    assert set(_payload(html)[st.NAAIM_KEY]) == set(st.NAAIM_BLOCKS)
    # In the tiles' order: NAAIM, then AAII, both above the lookback toggle.
    assert html.index(f'id="{st.READINGS_ID}"') < html.index(f'id="{st.NAAIM_ID}"') \
        < html.index(f'id="{st.VOTES_ID}"') < html.index('class="lookback"')


def test_without_naaim_the_page_leaves_the_card_out():
    html = st.render(_reads(), COLORS, PALETTE)
    assert f'id="{st.NAAIM_ID}"' not in html and st.NAAIM_KEY not in _payload(html)
