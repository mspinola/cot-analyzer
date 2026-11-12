"""The percentiles card: each survey's newest reading over three histories, at the top
of the page. Store-free: every test injects its own bars."""
from components import aaii_allocation as aa
from components import aaii_votes as av
from components import naaim_card as nc
from components import percentiles_card as pc
from components import sentiment_static as st
from tests.test_aaii_allocation import _alloc_bars
from tests.test_aaii_votes import _legs_bars, _payload, _reads
from tests.test_naaim_card import _naaim_bars
from tests.test_sentiment import COLORS, PALETTE, _no_cot_store  # noqa: F401 (autouse)


def _all():
    return dict(naaim=nc.read(_naaim_bars()[1]), votes=av.read(_legs_bars()[1]),
                allocation=aa.read(_alloc_bars()[1]))


def test_the_card_leads_under_the_tiles_with_a_block_per_survey():
    html = st.render(_reads(), COLORS, PALETTE, **_all())
    assert html.count(f'<div id="{st.PERCENTILES_ID}" class="votes-grid">') == 1
    assert html.index(f'id="{st.READINGS_ID}"') < html.index(f'id="{st.PERCENTILES_ID}"') \
        < html.index(f'id="{st.NAAIM_ID}"') < html.index(f'id="{st.VOTES_ID}"') \
        < html.index(f'id="{st.ALLOCATION_ID}"')
    blocks = _payload(html)[st.PERCENTILES_KEY]
    assert list(blocks) == list(pc.BLOCKS)
    for key in pc.BLOCKS:
        assert f'data-half="{key}"' in html.split(f'id="{st.PERCENTILES_ID}"', 1)[1]
        rows = [t["y"] for t in blocks[key]["data"][:3]]
        assert [r[0] for r in rows][1:] == ["Last 3 years", "Last year"]


def test_naaim_and_votes_keep_three_blocks_and_allocation_has_its_percentiles_back():
    html = st.render(_reads(), COLORS, PALETTE, **_all())
    payload = _payload(html)
    assert set(payload[st.NAAIM_KEY]) == set(st.NAAIM_BLOCKS)
    assert set(payload[st.VOTES_KEY]) == set(st.VOTES_HALVES)
    assert set(payload[st.ALLOCATION_KEY]) == set(st.ALLOCATION_BLOCKS)
    assert len(st.NAAIM_BLOCKS) == len(st.VOTES_HALVES) == 3
    assert st.ALLOCATION_BLOCKS[-1] == "latest" and len(st.ALLOCATION_BLOCKS) == 4
    assert "allocation" not in payload[st.PERCENTILES_KEY]


def test_only_the_surveys_that_are_in_get_a_block():
    html = st.render(_reads(), COLORS, PALETTE, votes=av.read(_legs_bars()[1]))
    assert list(_payload(html)[st.PERCENTILES_KEY]) == ["votes", "bulls_bears"]
    html = st.render(_reads(), COLORS, PALETTE)
    assert f'id="{st.PERCENTILES_ID}"' not in html
    assert st.PERCENTILES_KEY not in _payload(html)


def test_the_grids_go_three_across_from_the_threshold():
    html = st.render(_reads(), COLORS, PALETTE, **_all())
    assert av.THREE_ACROSS_MIN_PX == 1100
    assert (f"@media (min-width: {av.THREE_ACROSS_MIN_PX}px) {{ .votes-grid "
            "{ grid-template-columns: repeat(3,") in html


def test_the_naaim_block_is_one_dot_a_row_with_its_percentile_inside():
    naaim = nc.read(_naaim_bars()[1])
    fig = nc.latest_figure(naaim, PALETTE)
    tracks, dots = fig.data[:3], fig.data[3:]
    assert len(tracks) == 3 and len(dots) == 1
    assert list(dots[0].text) == [str(pct) for _, pct, _, _ in naaim.latest]
    assert list(dots[0].y) == [label for label, *_ in naaim.latest]
    assert dots[0].marker.color == nc.naaim_color(PALETTE)
    assert dots[0].customdata[0].endswith(f"percentile of every week since {naaim.since:%Y}")
    violet = nc.naaim_color(PALETTE)
    assert fig.layout.annotations[0].text == (
        f'NAAIM: <span style="color:{violet}"><b>exposure</b></span>')


def test_the_median_line_is_drawn_under_the_dots():
    fig = av.latest_figure(av.read(_legs_bars()[1]), COLORS)
    assert [(sh.x0, sh.line.dash, sh.layer) for sh in fig.layout.shapes] == [(50, "dot", "below")]


def test_the_bulls_bears_block_ranks_the_spread_over_three_histories():
    import pandas as pd

    from components import sentiment as s
    _, get_bars = _legs_bars()
    votes = av.read(get_bars)
    official = av.legs(get_bars)
    spread = official["bullish"] - official["bearish"]
    newest = float(spread.iloc[-1])
    assert votes.spread_latest_pct[av.SPREAD_KEY][0] == s.percentile_of(spread.to_numpy(), newest)
    # The since-the-start rank is the spread block's top row's, and the tile's.
    assert votes.spread_latest_pct[av.SPREAD_KEY][0] == votes.spread_pct[0]
    end = spread.index[-1]
    want = [s.percentile_of(spread[(spread.index > end - pd.Timedelta(days=d))
                                   & (spread.index < end)].to_numpy(), newest)
            for _, d in av.WINDOWS]
    assert [p[av.SPREAD_KEY][0] for _, p in votes.spread_window_pct] == want
    fig = av.spread_figure_percentiles(votes, PALETTE)
    dot = fig.data[3]
    assert list(dot.text) == [str(x) for x in [votes.spread_pct[0], *want]]
    amber = s.card_tone(PALETTE[av.SPREAD_SLOT])
    # Not a green: beside the votes block it read as one more bullish dot.
    assert amber not in (av.leg_colors(COLORS)["bullish"], s.sentiment_colors(PALETTE)["aaii"])
    assert dot.marker.color == amber
    assert fig.layout.annotations[0].text == (
        f'AAII: <span style="color:{amber}"><b>bulls minus bears</b></span>')
    assert dot.customdata[0].startswith(f"bulls minus bears {newest:+.1f}:")
