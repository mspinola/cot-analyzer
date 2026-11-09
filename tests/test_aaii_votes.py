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


def test_the_two_halves_stack_the_recent_weeks_and_place_each_high_on_its_own_row():
    _, get_bars = _legs_bars()
    votes = av.read(get_bars)
    recent_fig, history_fig = av.figures(votes, COLORS)
    assert recent_fig.layout.barmode == history_fig.layout.barmode == "stack"
    recent, history = list(recent_fig.data), list(history_fig.data)
    assert [t.name for t in recent] == [t.name for t in history] == ["Bullish", "Neutral", "Bearish"]
    dates = [f"{d:%Y-%m-%d}" for d in votes.recent.index]
    for trace, key in zip(recent, ("bullish", "neutral", "bearish")):
        assert list(trace.y) == dates
        np.testing.assert_allclose(trace.x, votes.recent[key].round(1))
    assert recent_fig.layout.annotations[0].text == "Recent weeks"
    # History: the average row stacks all three; each high row holds one leg only.
    assert list(history[0].y) == ["Average", "Bullish high", "Neutral high", "Bearish high"]
    for i, (trace, key) in enumerate(zip(history, ("bullish", "neutral", "bearish"))):
        assert trace.x[0] == pytest.approx(round(votes.average[key], 1))
        filled = [j for j, v in enumerate(trace.x[1:]) if v is not None]
        assert filled == [i] and trace.x[1 + i] == pytest.approx(round(votes.highs[key][0], 1))
    *dated, title = [a.text.strip() for a in history_fig.layout.annotations]
    assert dated == [f"{votes.highs[k][1]:%Y-%m-%d}" for k in ("bullish", "neutral", "bearish")]
    assert title.startswith(f"Since {votes.since:%Y}")


def test_the_halves_are_the_same_height_so_they_line_up_side_by_side():
    _, get_bars = _legs_bars()
    recent_fig, history_fig = av.figures(av.read(get_bars), COLORS)
    assert recent_fig.layout.height == history_fig.layout.height
    assert len(recent_fig.data[0].y) == len(history_fig.data[0].y) == 4


def test_each_half_is_a_fixed_0_to_100_with_no_zoom():
    _, get_bars = _legs_bars()
    for fig in av.figures(av.read(get_bars), COLORS):
        assert list(fig.layout.xaxis.range) == av.X_RANGE and fig.layout.xaxis.fixedrange
        assert fig.layout.yaxis.autorange == "reversed"       # newest week on top
        assert fig.layout.yaxis.type == "category"            # not dates
        # No legend (it wraps at phone width): the subtitle names each colour instead.
        assert fig.layout.showlegend is False
    assert av.X_RANGE[0] == 0 and 100.2 < av.X_RANGE[1] < 101   # rounding room, no more
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
    assert html.count(f'<div id="{st.VOTES_ID}" class="votes-grid">') == 1 and av.TITLE in html
    for half in st.VOTES_HALVES:
        assert html.count(f'data-half="{half}"') == 1
    payload = _payload(html)
    assert set(payload[st.VOTES_KEY]) == set(st.VOTES_HALVES)
    assert all(f["layout"]["barmode"] == "stack" for f in payload[st.VOTES_KEY].values())
    # Once, beside the lookbacks, not inside each.
    assert all(st.VOTES_KEY not in v for k, v in payload.items() if k != st.VOTES_KEY)
    # Between the index card and the columns.
    assert html.index(f'id="{st.PRICE_ID}"') < html.index(f'id="{st.VOTES_ID}"') \
        < html.index(f'id="{st.COLUMNS_ID}"')


def test_without_votes_the_page_leaves_the_card_out():
    html = st.render(_reads(), COLORS, PALETTE)
    assert f'id="{st.VOTES_ID}"' not in html and st.VOTES_KEY not in _payload(html)


def test_the_halves_sit_side_by_side_from_the_same_width_on_both_pages():
    """The published grid goes two-wide at the constant; the app's columns at Bootstrap's
    md breakpoint, which is the same 768px."""
    html = st.render(_reads(), COLORS, PALETTE, votes=av.read(_legs_bars()[1]))
    assert av.VOTES_SIDE_BY_SIDE_MIN_PX == 768
    assert f"@media (min-width: {av.VOTES_SIDE_BY_SIDE_MIN_PX}px) {{ .votes-grid" in html


# ── provisional weeks ─────────────────────────────────────────────────────────

def _with_provisional(n_official=118, legs=("bullish", "neutral", "bearish"), stale=True):
    """The official legs cut to `n_official` weeks; the weeks after them served as the
    provisional legs named in `legs`, plus (when `stale`) one the official legs cover."""
    frames, _ = _legs_bars()
    full = dict(frames)
    for (key, sym, _), prov in zip(av.LEGS, av.PROVISIONAL.values()):
        frames[sym] = full[sym].iloc[:n_official]
        p = full[sym].iloc[n_official:]
        if stale:
            p = pd.concat([full[sym].iloc[[n_official - 1]] * 0.5, p])
        if key in legs:
            frames[prov] = p

    def get_bars(symbol, tier=None):
        if symbol not in frames:
            raise FileNotFoundError(symbol)
        return frames[symbol]
    return frames, get_bars, full


def test_provisional_weeks_join_the_recent_rows_only_and_are_flagged():
    _, get_bars, full = _with_provisional()
    votes = av.read(get_bars)
    official = av.legs(get_bars)
    assert len(official) == 118
    want = list(WEEKS[::-1][:av.RECENT_WEEKS])
    assert list(votes.recent.index) == want                 # 2 provisional + 2 official
    assert votes.provisional == tuple(WEEKS[118:])
    assert votes.last == WEEKS[-1].date()
    # The stale provisional week is ignored: the official reading stands.
    assert votes.recent.loc[WEEKS[117], "bullish"] == pytest.approx(
        full[av.LEGS[0][1]]["Close"].iloc[117] * 100)
    # Average and highs are the official weeks' alone.
    pd.testing.assert_series_equal(votes.average, official.mean())
    assert votes.highs == av.summarize(official).highs


@pytest.mark.parametrize("legs", [("bullish", "bearish"), ("neutral",)])
def test_a_provisional_week_missing_a_leg_is_not_shown(legs):
    _, get_bars, _ = _with_provisional(legs=legs)
    votes = av.read(get_bars)
    assert votes.provisional == () and votes.last == WEEKS[117].date()


def test_provisional_weeks_never_stand_in_for_missing_official_legs():
    frames, get_bars, _ = _with_provisional()
    del frames[av.AAII_NEUTRAL]
    assert av.read(get_bars) is None


def test_provisional_rows_draw_faint_with_the_tag_beside_the_date():
    _, get_bars, _ = _with_provisional()
    votes = av.read(get_bars)
    fig, _ = av.figures(votes, COLORS)
    bull = next(t for t in fig.data if t.name == "Bullish")
    assert list(bull.y[:2]) == [f"{d:%Y-%m-%d} {av.PROVISIONAL_TAG}" for d in WEEKS[[119, 118]]]
    assert list(bull.y[2:]) == [f"{d:%Y-%m-%d}" for d in WEEKS[[117, 116]]]
    from components import sentiment as s
    np.testing.assert_allclose(bull.marker.opacity, [s.PROVISIONAL_OPACITY] * 2 + [1.0] * 2)
    # Light text on the faint rows, the leg's usual text on the others.
    assert list(bull.insidetextfont.color) == [av.PROVISIONAL_TEXT] * 2 + [av.INSIDE_TEXT["bullish"]] * 2
    assert "provisional" in fig.layout.annotations[0].text


def test_without_provisional_weeks_the_card_is_unchanged():
    _, get_bars = _legs_bars()
    votes = av.read(get_bars)
    fig, _ = av.figures(votes, COLORS)
    assert votes.provisional == () and fig.layout.annotations[0].text == "Recent weeks"
    assert all(t.marker.opacity is None for t in fig.data)


def test_the_app_card_puts_the_halves_in_two_md_columns():
    """Side by side from Bootstrap's md (768px), stacked below it, like the published grid."""
    import dash_bootstrap_components as dbc

    from pages.analytics import sentiment as page
    _, get_bars = _legs_bars()
    card = page._card("t", None, av.figures(av.read(get_bars), COLORS))
    row = card.children.children[-1]
    assert isinstance(row, dbc.Row) and [c.md for c in row.children] == [6, 6]
