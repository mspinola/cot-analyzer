"""The AAII asset allocation card: three shares as stored, the recent months, the
history block and stocks against their average. Store-free: every test injects bars."""
import json

import numpy as np
import pandas as pd
import pytest

from components import aaii_allocation as aa
from components import aaii_votes as av
from components import exposure_traces, sentiment
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
    recent, history, gap, _ = aa.figures(alloc, COLORS)
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
        assert c == hex_to_rgba(sentiment.card_green(COLORS) if v >= 0
                                else sentiment.card_red(COLORS),
                                av.BAR_OPACITY)
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
    # After the two cards the lookback redraws, and after the votes.
    assert html.index(f'id="{st.COLUMNS_ID}"') < html.index(f'id="{st.VOTES_ID}"') \
        < html.index(f'id="{st.ALLOCATION_ID}"')
    # One JS loop draws every block-grid card.
    assert json.dumps([list(c) for c in st.GRID_CARDS], separators=(",", ":")) in html


def test_without_the_survey_the_page_leaves_the_card_out():
    html = st.render(_reads(), COLORS, PALETTE)
    assert f'id="{st.ALLOCATION_ID}"' not in html
    assert st.ALLOCATION_KEY not in _payload(html)


def test_share_labels_carry_no_percent_sign_so_narrow_segments_keep_them():
    _, get_bars = _alloc_bars()
    recent, history, *_ = aa.figures(aa.read(get_bars), COLORS)
    labels = [t for f in (recent, history) for tr in f.data for t in tr.text if t]
    assert labels and not any("%" in t for t in labels)
    assert "percent of portfolio" in aa.SUBTITLE


# ── allocation against price ──────────────────────────────────────────────────

#: Long enough for the gap panel's 36-month window to fill (the default fixture is not).
LONG_MONTHS = pd.date_range("2021-01-31", periods=48, freq="ME")


def _price_fig(spy=True, months=MONTHS):
    from components import sentiment as s
    _, get_bars = _alloc_bars(months)
    alloc = aa.read(get_bars)
    read = _reads()[s.DEFAULT_LOOKBACK]
    series = read.frame["spy"] if spy else None
    return alloc, series, aa.price_figure(alloc, series, COLORS)


def test_the_price_chart_stacks_every_month_under_spy():
    from components import sentiment as s
    alloc, spy, fig = _price_fig()
    assert [t.name for t in fig.data][:4] == ["SPY", "Stocks", "Bonds", "Cash"]
    assert fig.data[0].yaxis == "y"
    stacked = fig.data[1:4]
    assert all(t.yaxis == "y2" and t.stackgroup == "allocation" for t in stacked)
    for t, (key, _, _) in zip(stacked, aa.LEGS):
        assert list(pd.DatetimeIndex(t.x)) == list(alloc.months.index)
        np.testing.assert_allclose(t.y, alloc.months[key].round(1))
    # Stocks first, so they stack on the floor and their top edge is the stocks share.
    assert stacked[0].name == "Stocks"
    avg = [sh for sh in fig.layout.shapes if sh.yref == "y2"]
    assert len(avg) == 1 and avg[0].y0 == pytest.approx(alloc.average["stocks"])
    assert list(fig.layout.yaxis2.range) == aa.STACK_RANGE
    # The whole history, to a little past whichever is drawn later.
    end = max(alloc.months.index[-1], spy.dropna().index[-1])
    assert list(fig.layout.xaxis.range) == [
        alloc.months.index[0], end + pd.Timedelta(days=s.OPEN_PAD_DAYS)]
    assert fig.layout.xaxis.autorangeoptions.clipmin == f"{alloc.months.index[0]:%Y-%m-%d}"
    # Behaves like the sentiment chart: its buttons, and the price axis refits. The
    # stack keeps its fixed 0-100 scale; the gap panel refits with zero kept in view.
    assert fig.layout.xaxis.rangeselector.buttons[0].label == "3M"
    refit = fig.layout.meta[exposure_traces.REFIT_META]
    assert refit["axes"] == ["yaxis", "yaxis3"] and refit["zero"] == ["yaxis3"]
    assert refit["price_axis"] == "yaxis"
    assert {k: v for k, v in refit.items() if k not in ("axes", "zero")} == {
        k: v for k, v in s.PRICE_REFIT[exposure_traces.REFIT_META].items() if k != "axes"}
    last = alloc.months.iloc[-1]
    assert fig.layout.annotations[1].text == (
        f"AAII allocation, {alloc.last:%Y-%m}<br>Stocks {last['stocks']:.1f}, "
        f"bonds {last['bonds']:.1f}, cash {last['cash']:.1f}")


def test_without_spy_the_chart_still_draws_the_months():
    from components import sentiment as s
    alloc, _, fig = _price_fig(spy=False)
    assert [t.name for t in fig.data][:3] == ["Stocks", "Bonds", "Cash"]
    assert fig.layout.xaxis.range[1] == alloc.months.index[-1] + pd.Timedelta(
        days=s.OPEN_PAD_DAYS)


def test_the_gap_is_each_share_minus_its_prior_months_mean():
    idx = pd.date_range("2020-01-31", periods=5, freq="ME")
    months = pd.DataFrame({"stocks": [60.0, 62.0, 64.0, 70.0, 50.0],
                           "bonds": [20.0] * 5, "cash": [20.0, 18.0, 16.0, 10.0, 30.0]},
                          index=idx)
    gap = aa.trailing_gap(months, n=3)
    # NaN until three months precede it; the current month is not in its own average.
    assert gap.iloc[:3].isna().all().all()
    assert gap["stocks"].iloc[3] == pytest.approx(70.0 - 62.0)
    assert gap["stocks"].iloc[4] == pytest.approx(50.0 - (62.0 + 64.0 + 70.0) / 3)
    assert gap["bonds"].iloc[3:].tolist() == [0.0, 0.0]


def test_the_gap_panel_draws_each_share_against_its_three_year_average():
    alloc, spy, fig = _price_fig(months=LONG_MONTHS)
    gap = aa.trailing_gap(alloc.months).round(1)
    lines = [t for t in fig.data if t.yaxis == "y3"]
    assert [t.name for t in lines] == ["Stocks vs 3Y avg", "Bonds vs 3Y avg", "Cash vs 3Y avg"]
    for t, (key, _, _) in zip(lines, aa.LEGS):
        g = gap[key].dropna()
        # The first 36 months have no full window behind them and are not drawn.
        assert len(g) == len(LONG_MONTHS) - aa.GAP_MONTHS
        assert list(pd.DatetimeIndex(t.x)) == list(g.index)
        np.testing.assert_allclose(t.y, g)
        assert t.stackgroup is None
    last = gap.iloc[-1]
    assert fig.layout.annotations[2].text == (
        "Each share vs its prior 3Y average, points<br>"
        f"Stocks {last['stocks']:+.1f}, bonds {last['bonds']:+.1f}, cash {last['cash']:+.1f}")
    # Opens fitted to the whole history, zero in view, padded as the browser pads it.
    lo, hi = min(gap.min().min(), 0.0), max(gap.max().max(), 0.0)
    pad = (hi - lo) * 0.05
    assert list(fig.layout.yaxis3.range) == pytest.approx([lo - pad, hi + pad])
    assert fig.layout.yaxis3.zeroline


def test_the_cards_green_is_toned_down_and_still_carries_its_dark_text():
    """One green on the page: the cards' fill matches AAII's toned-down line, and the
    dark ink printed inside a green bar keeps 4.5 to 1 on it."""
    from components.plot_colors import blend_over, relative_luminance
    green = sentiment.card_green(COLORS)
    assert green == blend_over(COLORS.bull, sentiment.CARD_GREEN_STRENGTH) != COLORS.bull
    assert aa.leg_colors(COLORS)["stocks"] == av.leg_colors(COLORS)["bullish"] == green
    # The red and the bonds blue take the same step, so no colour outshouts another.
    assert aa.leg_colors(COLORS)["bonds"] == sentiment.card_tone(aa.BONDS_COLOR) != aa.BONDS_COLOR
    assert av.leg_colors(COLORS)["bearish"] == sentiment.card_red(COLORS) != COLORS.bear
    assert sentiment.CARD_STRENGTH == sentiment.CARD_GREEN_STRENGTH
    assert sentiment.card_tone("rgba(1, 2, 3, 0.5)") == "rgba(1, 2, 3, 0.5)"   # not a hex
    # The ink follows the fill as drawn, because palettes disagree about how bright
    # their bull slot is: dark on the default palette's green, white on a darker one.
    def ratio(fill, ink):
        pair = sorted((relative_luminance(blend_over(fill, av.BAR_OPACITY)),
                       relative_luminance(ink)), reverse=True)
        return (pair[0] + 0.05) / (pair[1] + 0.05)
    default = blend_over("#34D399", sentiment.CARD_GREEN_STRENGTH)
    assert av.segment_ink("stocks", default) == aa.INSIDE_TEXT["stocks"]
    assert av.segment_ink("bullish", green) == av.LIGHT_INK      # the fixture's is darker
    for fill in (default, green):
        for key in av.GREEN_KEYS:
            assert ratio(fill, av.segment_ink(key, fill)) >= 4.5
    # The toned red and blue are too dark as bars for the dark ink, so theirs is white,
    # on the default palette's colours and on the fixture's.
    for key, fill in (("bearish", sentiment.card_tone("#FF4D4D")),
                      ("bearish", sentiment.card_red(COLORS)),
                      ("bonds", sentiment.card_tone(aa.BONDS_COLOR))):
        assert av.segment_ink(key, fill) == av.LIGHT_INK
        assert ratio(fill, av.LIGHT_INK) >= 4.5
    # The grey keeps the ink it had.
    assert av.segment_ink("neutral", av.NEUTRAL_COLOR) == av.INSIDE_TEXT["neutral"]
    recent, *_ = aa.figures(aa.read(_alloc_bars()[1]), COLORS)
    assert recent.data[0].insidetextfont.color == av.segment_ink("stocks", green)


def test_the_cash_gap_line_is_a_light_grey_the_stack_keeps_its_own():
    """The stack's grey was 3.6 to 1 as a thin line; the gap panel's cash line takes a
    lighter one, validated apart from the stocks green and bonds blue."""
    _, _, fig = _price_fig(months=LONG_MONTHS)
    by_name = {t.name: t for t in fig.data}
    assert by_name["Cash vs 3Y avg"].line.color == aa.CASH_LINE_COLOR
    assert by_name["Cash"].line.color == av.NEUTRAL_COLOR
    assert by_name["Stocks vs 3Y avg"].line.color == sentiment.card_green(COLORS)
    assert by_name["Stocks"].line.color == sentiment.card_green(COLORS)
    assert by_name["Bonds vs 3Y avg"].line.color == sentiment.card_tone(aa.BONDS_COLOR)


def test_the_gap_panel_is_the_tallest_so_its_lines_read_apart():
    _, _, fig = _price_fig(months=LONG_MONTHS)
    span = [fig.layout[a].domain[1] - fig.layout[a].domain[0]
            for a in ("yaxis", "yaxis2", "yaxis3")]
    assert span[2] > span[0] and span[2] > span[1]
    plot = aa.PRICE_HEIGHT - fig.layout.margin.t - fig.layout.margin.b
    assert span[2] * plot >= 190      # px; it had about 110 and the lines ran together
    assert fig.layout.height == aa.PRICE_HEIGHT


def test_a_short_history_draws_no_gap_lines_and_a_plain_title():
    _, _, fig = _price_fig()
    assert not [t for t in fig.data if t.yaxis == "y3"]
    assert fig.layout.annotations[2].text == "Each share vs its prior 3Y average, points"


def test_the_summary_names_the_newest_month_and_the_gap_from_average():
    _, get_bars = _alloc_bars()
    alloc = aa.read(get_bars)
    row = alloc.months.iloc[-1]
    gap = row["stocks"] - alloc.average["stocks"]
    line = aa.summary(alloc)
    assert line.startswith(f"AAII asset allocation, {alloc.last:%Y-%m}: "
                           f"stocks {row['stocks']:.1f}%, bonds {row['bonds']:.1f}%, "
                           f"cash {row['cash']:.1f}%.")
    assert (f"{abs(gap):.1f} points {'above' if gap >= 0 else 'below'} their average "
            f"since {alloc.since.year} ({alloc.average['stocks']:.1f}%)") in line
    notes = aa.caption(alloc)
    assert f"({alloc.last:%Y-%m})" in notes[0] and "about a month old" in notes[0]
    assert notes[-1] == aa.FOLLOWS_NOTE and "Context, not signal" in notes[-1]


def test_the_published_page_names_the_allocation_survey_outside_its_cards():
    """Header, lead, notes and sources: until 2026-11-10 they described a weekly
    NAAIM and AAII sentiment page on which two of five cards were this survey."""
    import re
    _, alloc_bars = _alloc_bars()
    alloc = aa.read(alloc_bars)
    html = st.render(_reads(), COLORS, PALETTE, allocation=alloc)
    head = re.search(r'<header class="top">.*?</header>', html, re.S).group(0)
    assert f'<div class="eyebrow">{st.EYEBROW_ALLOCATION}</div>' in head
    assert "weekly" not in st.EYEBROW_ALLOCATION.lower()
    assert f"AAII allocation <b>{alloc.last:%b %Y}</b>" in head
    # Its tile closes the readings strip, after the two surveys' own.
    tile = st.stocks_tile(alloc)
    gap = alloc.recent.iloc[0]["stocks"] - alloc.average["stocks"]
    assert tile == {"key": st.STOCKS_KEY, "label": "AAII stocks allocation",
                    "value": f"{alloc.recent.iloc[0]['stocks']:.1f}%",
                    "context": (f"{abs(gap):.1f} points {'above' if gap >= 0 else 'below'} "
                                f"its average since {alloc.since.year}"),
                    "pct": sentiment.percentile_phrase(alloc.latest_pct["stocks"][1],
                                                       alloc.since.year),
                    "foot": f"{alloc.last:%b %Y}"}
    strip = html.split(f'id="{st.READINGS_ID}"')[1].split('<div class="lookback"')[0]
    assert strip.count('class="tile"') == 3
    assert strip.index('data-key="aaii"') < strip.index(f'data-key="{st.STOCKS_KEY}"')
    assert f'<div class="value">{tile["value"]}</div>' in strip
    notes = html.split(f'<div class="notes" id="{st.ALLOCATION_NOTES_ID}">')[1].split("</div>")[0]
    assert notes.count("<p>") == len(aa.caption(alloc)) and "Context, not signal" in notes
    # Outside the two elements the lookback toggle rewrites.
    assert html.index('id="notes"') < html.index(f'id="{st.ALLOCATION_NOTES_ID}"')
    assert "Asset Allocation Survey (aaii.com)" in html.split("<footer>")[1]
    bare = st.render(_reads(), COLORS, PALETTE)
    for gone in (f'data-key="{st.STOCKS_KEY}"', st.ALLOCATION_NOTES_ID, "Asset Allocation"):
        assert gone not in bare.split("<body>")[1].split("<script")[0]
    assert f'<div class="eyebrow">{st.EYEBROW}</div>' in bare


def test_the_published_page_draws_the_price_chart_once_and_refits_it():
    _, alloc_bars = _alloc_bars()
    html = st.render(_reads(), COLORS, PALETTE, allocation=aa.read(alloc_bars))
    assert html.count(f'<div id="{st.ALLOCATION_PRICE_ID}">') == 1 and aa.PRICE_TITLE in html
    assert st.ALLOCATION_PRICE_KEY in _payload(html)
    assert html.index(f'id="{st.COLUMNS_ID}"') < html.index(f'id="{st.ALLOCATION_ID}"') \
        < html.index(f'id="{st.ALLOCATION_PRICE_ID}"') < html.index('id="notes"')
    # Drawn outside the lookback loop, but hooked to the same refit as the price chart.
    assert f"'{st.ALLOCATION_PRICE_ID}': '{st.ALLOCATION_PRICE_KEY}'" in html
    assert "IDS.concat(Object.keys(ONCE)" in html
    bare = st.render(_reads(), COLORS, PALETTE)
    assert f'id="{st.ALLOCATION_PRICE_ID}"' not in bare
    assert st.ALLOCATION_PRICE_KEY not in _payload(bare)


def test_the_app_page_refits_the_price_chart_without_a_load_time_call(monkeypatch):
    import importlib

    import dash

    import local_pages
    # Imported before the snapshot: run alone, a first import inside it registered the
    # callbacks once and the reload below again, so each was counted twice.
    monkeypatch.delenv(local_pages.ENV, raising=False)
    importlib.import_module("pages.analytics.sentiment")
    registered = list(dash._callback.GLOBAL_CALLBACK_LIST)
    monkeypatch.setenv(local_pages.ENV, "1")
    page = importlib.reload(importlib.import_module("pages.analytics.sentiment"))
    try:
        ours = [c for c in dash._callback.GLOBAL_CALLBACK_LIST[len(registered):]
                if any(i["id"] == page.ALLOCATION_PRICE_CHART for i in c["inputs"])]
        assert len(ours) == 1 and ours[0]["prevent_initial_call"]
        assert "allocation_price" in page.EXPORTS
    finally:
        dash._callback.GLOBAL_CALLBACK_LIST[:] = registered
        monkeypatch.delenv(local_pages.ENV)
        importlib.reload(page)
        for key in [k for k, v in dash.page_registry.items() if v.get("path") == "/sentiment"]:
            del dash.page_registry[key]


def test_the_percentile_block_ranks_the_newest_month_on_every_month():
    _, get_bars = _alloc_bars()
    alloc = aa.read(get_bars)
    months = aa.legs(get_bars)
    fig = aa.figures(alloc, COLORS)[3]
    dots = fig.data[3:]
    fills = aa.leg_colors(COLORS)
    for dot, (key, _, label) in zip(dots, aa.LEGS):
        pct, word = alloc.latest_pct[key]
        assert pct == sentiment.percentile_of(months[key].to_numpy(), months[key].iloc[-1])
        assert list(dot.x) == [pct] and list(dot.text) == [word]
        assert list(dot.y) == [f"{label} {months[key].iloc[-1]:.1f}%"]
        assert dot.marker.color == fills[key]
    assert fig.layout.annotations[0].text == f"Newest month, percentile since {alloc.since:%Y}"
    assert fig.layout.height == aa.figures(alloc, COLORS)[0].layout.height
