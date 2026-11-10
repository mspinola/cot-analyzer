"""The AAII votes card: three shares as read, the recent weeks, and the history block.
Store-free: every test injects its own bars."""
import json

import numpy as np
import pandas as pd
import pytest

from components import aaii_votes as av
from components import sentiment_static as st
from components.plot_colors import hex_to_rgba
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
    recent_fig, history_fig, _ = av.figures(votes, COLORS)
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


def test_the_blocks_are_the_same_height_so_they_line_up_side_by_side():
    _, get_bars = _legs_bars()
    figs = av.figures(av.read(get_bars), COLORS)
    assert len(figs) == 3 and len({f.layout.height for f in figs}) == 1
    assert [len(f.data[0].y) for f in figs] == [4, 4, 4]


def test_each_block_has_a_fixed_scale_and_no_zoom():
    _, get_bars = _legs_bars()
    *shares, spread = av.figures(av.read(get_bars), COLORS)
    assert list(spread.layout.xaxis.range) == [-av.SPREAD_LIMIT, av.SPREAD_LIMIT]
    for fig in (*shares, spread):
        if fig is not spread:
            assert list(fig.layout.xaxis.range) == av.X_RANGE
        assert fig.layout.xaxis.fixedrange
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


def test_the_blocks_go_across_at_the_same_widths_on_both_pages():
    """The published grid goes two across and three across at the constants; the app's
    columns at Bootstrap's md and xl breakpoints, which are the same 768 and 1200px."""
    html = st.render(_reads(), COLORS, PALETTE, votes=av.read(_legs_bars()[1]))
    assert (av.VOTES_SIDE_BY_SIDE_MIN_PX, av.VOTES_THREE_ACROSS_MIN_PX) == (768, 1200)
    assert (f"@media (min-width: {av.VOTES_SIDE_BY_SIDE_MIN_PX}px) {{ .votes-grid "
            "{{ grid-template-columns: repeat(2,".replace("{{", "{")) in html
    assert (f"@media (min-width: {av.VOTES_THREE_ACROSS_MIN_PX}px) {{ .votes-grid "
            "{{ grid-template-columns: repeat(3,".replace("{{", "{")) in html


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
    fig, *_ = av.figures(votes, COLORS)
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
    fig, *_ = av.figures(votes, COLORS)
    assert votes.provisional == () and fig.layout.annotations[0].text == "Recent weeks"
    assert all(t.marker.opacity is None for t in fig.data)


def test_the_app_card_puts_the_blocks_in_md_and_xl_columns():
    """Two across from Bootstrap's md (768px), three from xl (1200px), like the published
    grid."""
    import dash_bootstrap_components as dbc

    from pages.analytics import sentiment as page
    _, get_bars = _legs_bars()
    card = page._card("t", None, av.figures(av.read(get_bars), COLORS))
    row = card.children.children[-1]
    assert isinstance(row, dbc.Row) and [c.md for c in row.children] == [6, 6, 6]
    assert [c.xl for c in row.children] == [4, 4, 4]


# ── bulls minus bears ─────────────────────────────────────────────────────────

def _spread(votes):
    return av.figures(votes, COLORS)[2]


def test_the_spread_block_is_bulls_minus_bears_for_the_recent_weeks():
    _, get_bars = _legs_bars()
    votes = av.read(get_bars)
    fig = _spread(votes)
    bar = fig.data[0]
    want = (votes.recent["bullish"] - votes.recent["bearish"]).round(1)
    assert list(bar.y) == [f"{d:%Y-%m-%d}" for d in votes.recent.index]
    np.testing.assert_allclose(bar.x, want.clip(-av.SPREAD_LIMIT, av.SPREAD_LIMIT))
    labels = [a.text.strip() for a in fig.layout.annotations[1:]]
    assert [t.split(" (")[0] for t in labels] == [f"{v:+.1f}" for v in want]
    # Green at or above zero, red below: the page's bull and bear.
    for v, c in zip(want, bar.marker.color):
        assert c == hex_to_rgba(COLORS.bull if v >= 0 else COLORS.bear, av.BAR_OPACITY)


def test_the_average_line_is_the_official_average_spread():
    _, get_bars = _legs_bars()
    votes = av.read(get_bars)
    fig = _spread(votes)
    avg = round(float(votes.average["bullish"] - votes.average["bearish"]), 1)
    dashed = [s for s in fig.layout.shapes if s.line.dash == "dash"]
    assert len(dashed) == 1 and dashed[0].x0 == pytest.approx(avg)
    assert fig.layout.annotations[0].text == f"Bulls minus bears (avg {avg:+.1f} dashed)"
    assert "since 1987 (dashed)" in av.SUBTITLE


def test_a_spread_beyond_the_scale_is_pinned_but_labelled_true():
    frames, get_bars = _legs_bars()
    frames[av.LEGS[0][1]].iloc[-1, 0] = 0.80      # bullish 80
    frames[av.LEGS[1][1]].iloc[-1, 0] = 0.15
    frames[av.LEGS[2][1]].iloc[-1, 0] = 0.05      # bearish 5: spread +75
    bar = _spread(av.read(get_bars)).data[0]
    fig = _spread(av.read(get_bars))
    assert bar.x[0] == av.SPREAD_LIMIT
    assert fig.layout.annotations[1].text.strip().startswith("+75.0 (")


def test_provisional_weeks_draw_faint_in_the_spread_block_too():
    _, get_bars, _ = _with_provisional()
    bar = _spread(av.read(get_bars)).data[0]
    from components import sentiment as s
    np.testing.assert_allclose(bar.marker.opacity, [s.PROVISIONAL_OPACITY] * 2 + [1.0] * 2)
    assert bar.y[0].endswith(av.PROVISIONAL_TAG)



# ── percentile beside the spread ──────────────────────────────────────────────

@pytest.mark.parametrize("n, want", [(1, "1st"), (2, "2nd"), (3, "3rd"), (4, "4th"),
                                     (11, "11th"), (12, "12th"), (13, "13th"),
                                     (21, "21st"), (22, "22nd"), (23, "23rd"),
                                     (100, "100th"), (101, "101st"), (111, "111th")])
def test_ordinal(n, want):
    assert av.ordinal(n) == want


def test_each_recent_week_carries_its_spread_percentile_among_official_weeks():
    _, get_bars = _legs_bars()
    votes = av.read(get_bars)
    legs = av.legs(get_bars)
    history = (legs["bullish"] - legs["bearish"]).to_numpy()
    want = [max(1, round(float((history <= v).mean()) * 100))
            for v in (votes.recent["bullish"] - votes.recent["bearish"])]
    assert list(votes.spread_pct) == want and all(1 <= p <= 100 for p in want)


def test_a_provisional_week_is_ranked_against_official_weeks_only():
    _, get_bars, _ = _with_provisional()
    votes = av.read(get_bars)
    official = av.legs(get_bars)
    history = (official["bullish"] - official["bearish"]).to_numpy()
    newest = votes.recent.iloc[0]
    assert votes.recent.index[0] in votes.provisional
    assert votes.spread_pct[0] == max(1, round(
        float((history <= newest["bullish"] - newest["bearish"]).mean()) * 100))


def test_the_spread_label_reads_value_then_bracketed_percentile():
    _, get_bars = _legs_bars()
    votes = av.read(get_bars)
    fig = av.figures(votes, COLORS)[2]
    bar = fig.data[0]
    spread = (votes.recent["bullish"] - votes.recent["bearish"]).round(1)
    labels = [a.text.strip() for a in fig.layout.annotations[1:]]
    assert labels == [f"{v:+.1f} ({av.ordinal(p)})" for v, p in zip(spread, votes.spread_pct)]
    assert "percentile" in bar.hovertemplate


def test_spread_labels_sit_on_the_empty_side_of_zero_beyond_the_average():
    """Bearish weeks' labels start right of the dashed average, bullish weeks' end left
    of zero, so no label runs into the date labels however long the bar."""
    frames, get_bars = _legs_bars()
    frames[av.LEGS[0][1]].iloc[-1, 0], frames[av.LEGS[2][1]].iloc[-1, 0] = 0.2, 0.6   # -40
    frames[av.LEGS[0][1]].iloc[-2, 0], frames[av.LEGS[2][1]].iloc[-2, 0] = 0.6, 0.2   # +40
    votes = av.read(get_bars)
    fig = av.figures(votes, COLORS)[2]
    avg = round(float(votes.average["bullish"] - votes.average["bearish"]), 1)
    spread = (votes.recent["bullish"] - votes.recent["bearish"]).round(1)
    for v, a in zip(spread, fig.layout.annotations[1:]):
        if v < 0:
            assert a.xanchor == "left" and a.x == max(0.0, avg)
        else:
            assert a.xanchor == "right" and a.x == min(0.0, avg)
    assert "percentile since 1987 in brackets" in av.SUBTITLE


def test_the_weakest_week_on_record_reads_1st_not_0th():
    frames, get_bars = _legs_bars()
    for sym, v in zip((av.LEGS[0][1], av.LEGS[1][1], av.LEGS[2][1]), (0.01, 0.01, 0.98)):
        frames[sym].iloc[-1, 0] = v
    votes = av.read(get_bars)
    assert votes.spread_pct[0] == 1
