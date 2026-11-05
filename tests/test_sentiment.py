"""The local-only sentiment page: the gate, the weekly join, and the three views.

What is pinned: the page exists only when the local flag is explicitly on (licensed
data must not reach the public site), every series lands on the Friday of its week,
every index is cotmetrics' range index over 157 of the series' own weeks, a series
the store lacks is named rather than raised, and the views draw (words against money as
two pairs: NAAIM with large specs, AAII with non-reportables).

Store-free: `get_bars` and the positioning reader are injected.
"""
import importlib

import cotmetrics.indicators as indicators
import dash
import numpy as np
import pandas as pd
import pytest

import components.sentiment as s
import local_pages
from components import exposure_traces
from components.plot_colors import GridColors

COLORS = GridColors(bull="#2aa198", bear="#dc322f", bull_near="#2aa198", bear_near="#dc322f")
PALETTE = ["#F87171", "#60A5FA", "#FBBF24", "#34D399", "#ABB8C9", "#A78BFA"]


# ── the gate ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", ["1", "true", "YES", " on "])
def test_the_gate_opens_only_on_an_explicit_yes(value):
    assert local_pages.enabled({local_pages.ENV: value})


@pytest.mark.parametrize("value", ["", "0", "false", "no", "off", "ture", "2"])
def test_anything_else_keeps_the_page_off(value):
    """A typo must keep licensed data off a public server, not put it on one."""
    assert not local_pages.enabled({local_pages.ENV: value})
    assert local_pages.monitor_entries({local_pages.ENV: value}) == ()


def test_unset_is_off():
    assert not local_pages.enabled({})


def test_the_menu_entry_says_local():
    (label, href), = local_pages.monitor_entries({local_pages.ENV: "1"})
    assert href == "/sentiment" and "local" in label.lower()


def _sentiment_paths():
    return [p["path"] for p in dash.page_registry.values() if p.get("path") == "/sentiment"]


def test_the_page_registers_only_with_the_flag(monkeypatch):
    """Unregistered means 404 and no sitemap entry, through the app's existing rules."""
    module_name = "pages.analytics.sentiment"
    monkeypatch.delenv(local_pages.ENV, raising=False)
    page = importlib.import_module(module_name)
    page = importlib.reload(page)
    assert _sentiment_paths() == []

    monkeypatch.setenv(local_pages.ENV, "1")
    try:
        importlib.reload(page)
        assert _sentiment_paths() == ["/sentiment"]
    finally:
        for key in [k for k, v in dash.page_registry.items() if v.get("path") == "/sentiment"]:
            del dash.page_registry[key]


# ── dating ────────────────────────────────────────────────────────────────────

def test_every_weekday_lands_on_its_friday():
    days = pd.to_datetime(["2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30",
                           "2026-10-26"])  # Tue COT, Wed NAAIM, Thu AAII, Fri, Mon
    assert set(s.week_key(days)) == {pd.Timestamp("2026-10-30")}


def test_two_reports_in_one_week_keep_the_later():
    series = pd.Series([1.0, 2.0], index=pd.to_datetime(["2026-10-26", "2026-10-29"]))
    w = s.weekly(series)
    assert list(w) == [2.0] and w.index[0] == pd.Timestamp("2026-10-30")


# ── the frame ─────────────────────────────────────────────────────────────────

N_WEEKS = 200


def _weekly(weekday_offset, values, start="2022-01-03"):
    monday = pd.date_range(start, periods=len(values), freq="W-MON")
    return pd.DataFrame({"Close": values},
                        index=pd.DatetimeIndex(monday + pd.Timedelta(days=weekday_offset),
                                               name="Date"))


def _fixtures(seed=7):
    rng = np.random.default_rng(seed)
    naaim = _weekly(2, rng.uniform(0, 110, N_WEEKS))            # Wednesdays
    bull = _weekly(3, rng.uniform(0.2, 0.5, N_WEEKS))           # Thursdays
    bear = _weekly(3, rng.uniform(0.2, 0.5, N_WEEKS))
    days = pd.bdate_range("2022-01-03", periods=N_WEEKS * 5, name="Date")
    spy = pd.DataFrame({"Close": 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(days))))},
                       index=days)
    tuesdays = pd.date_range("2022-01-04", periods=N_WEEKS, freq="W-TUE")
    spec = pd.DataFrame({"spec": rng.normal(0, 10, N_WEEKS),
                         "small": rng.normal(0, 3, N_WEEKS)}, index=tuesdays)
    frames = {s.NAAIM: naaim, s.AAII_BULL: bull, s.AAII_BEAR: bear, s.PRICE: spy}

    def get_bars(symbol, tier=None):
        if symbol not in frames:
            raise FileNotFoundError(symbol)
        return frames[symbol]
    return frames, get_bars, spec


def test_the_frame_joins_four_series_on_fridays():
    frames, get_bars, spec = _fixtures()
    read = s.build_read(get_bars, lambda: spec)
    assert read.awaiting == ()
    assert (read.frame.index.weekday == 4).all()
    assert set(read.last) == {"spy", "naaim", "aaii", "spec", "small"}
    # AAII is bulls minus bears, in percentage points
    bull, bear = frames[s.AAII_BULL]["Close"], frames[s.AAII_BEAR]["Close"]
    want = s.weekly((bull - bear) * 100.0)
    pd.testing.assert_series_equal(read.frame["aaii"].dropna(), want, check_names=False,
                                   check_freq=False)


def test_the_indexes_are_cotmetrics_range_index_over_157_of_the_series_own_weeks():
    """NAAIM and AAII are indexed on their 4-week average, positioning on its weekly
    value; every index is cotmetrics' own, on the board's weeks + 1 window."""
    _, get_bars, spec = _fixtures()
    read = s.build_read(get_bars, lambda: spec)
    naaim = read.frame["naaim"].dropna()
    avg = naaim.rolling(s.AVERAGE_WEEKS, min_periods=s.AVERAGE_WEEKS).mean()
    pd.testing.assert_series_equal(read.frame["naaim_avg"].reindex(naaim.index), avg,
                                   check_names=False)
    want = indicators.calculate_range_index(avg, window=s.INDEX_WEEKS + 1)
    got = read.frame["naaim_idx"].reindex(naaim.index)
    pd.testing.assert_series_equal(got, want, check_names=False)
    assert got.notna().sum() == len(naaim) - (s.AVERAGE_WEEKS - 1) - s.INDEX_WEEKS
    assert got.dropna().between(0, 100).all()
    for key in ("spec", "small"):
        weekly = read.frame[key].dropna()
        pd.testing.assert_series_equal(
            read.frame[f"{key}_idx"].reindex(weekly.index),
            indicators.calculate_range_index(weekly, window=s.INDEX_WEEKS + 1),
            check_names=False)


def test_a_missing_series_is_named_not_raised():
    frames, _, spec = _fixtures()
    del frames[s.NAAIM]

    def get_bars(symbol, tier=None):
        if symbol not in frames:
            raise FileNotFoundError(symbol)
        return frames[symbol]

    def broken():
        raise RuntimeError("no indexer")

    read = s.build_read(get_bars, broken)
    assert s.NAAIM in read.awaiting
    assert any("positioning" in a for a in read.awaiting)
    assert any("non-reportables" in a for a in read.awaiting)
    assert "naaim" not in read.frame and "spec" not in read.frame
    assert s.joint(read).empty and s.summary(read) is None


def test_an_empty_store_frame_counts_as_missing():
    """A marketdata checkout that predates the registry entry returns an empty frame."""
    _, get_bars, spec = _fixtures()

    def empty_naaim(symbol, tier=None):
        return pd.DataFrame() if symbol == s.NAAIM else get_bars(symbol, tier)

    assert s.NAAIM in s.build_read(empty_naaim, lambda: spec).awaiting


# ── words and views ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("naaim_idx,spec_idx,want", [
    (10, 90, "Words cautious, money long"),
    (90, 10, "Words long, money short"),
    (5, 5, "Both washed out"),
    (95, 95, "Both crowded long"),
    (50, 90, None),
])
def test_quadrants_name_both_extremes_and_nothing_in_between(naaim_idx, spec_idx, want):
    assert s.quadrant(naaim_idx, spec_idx) == want


def test_the_summary_reads_the_latest_joint_week():
    _, get_bars, spec = _fixtures()
    read = s.build_read(get_bars, lambda: spec)
    j = s.joint(read)
    line = s.summary(read)
    assert f"{j.index[-1]:%Y-%m-%d}" in line
    assert f"NAAIM at {j['naaim_idx'].iloc[-1]:.0f} on its 3-year range index" in line
    assert "NAAIM's store ends" in line


def test_the_three_views_draw_and_the_latest_week_is_marked():
    _, get_bars, spec = _fixtures()
    read = s.build_read(get_bars, lambda: spec)
    assert s.price_sentiment_figure(read, COLORS, PALETTE).data
    assert s.words_money_figure(read, COLORS, PALETTE).data
    assert s.quadrant_figure(read, COLORS).data
    names = [t.name for t in s.quadrant_figure(read, COLORS).data]
    assert f"latest joint week {s.joint(read).index[-1]:%Y-%m-%d}" in names


def test_the_caption_states_the_lag_the_index_caveat_the_study_and_the_licence():
    _, get_bars, spec = _fixtures()
    text = " ".join(s.caption(s.build_read(get_bars, lambda: spec)))
    assert "quarter behind" in text and "pre-registration" in text
    assert "scale shifts under the line" in text
    assert "Local only" in text and "Context, not signal" in text
    assert "not retail" in text and "NAAIM against large specs only" in text


def test_the_price_panel_opens_by_exposures_scale_rule_for_its_window():
    _, get_bars, spec = _fixtures()
    read = s.build_read(get_bars, lambda: spec)
    axis = s.price_sentiment_figure(read, COLORS, PALETTE).layout.yaxis
    spy = read.frame["spy"].dropna()
    shown = spy[spy.index >= s.open_range(read)[0]]
    assert axis.type == exposure_traces.price_axis_type(shown)


def test_the_time_views_carry_the_apps_year_buttons():
    _, get_bars, spec = _fixtures()
    read = s.build_read(get_bars, lambda: spec)
    for fig in (s.price_sentiment_figure(read, COLORS, PALETTE),
                s.words_money_figure(read, COLORS, PALETTE)):
        labels = [b.label for b in fig.layout.xaxis.rangeselector.buttons]
        assert labels == [f"{n}Y" for n in exposure_traces.RANGE_YEARS] + ["Max"]


def test_only_the_price_axis_is_refitted_on_a_zoom():
    """The index panels are pinned to 0-100; re-fitting them would undo the index."""
    _, get_bars, spec = _fixtures()
    meta = s.price_sentiment_figure(s.build_read(get_bars, lambda: spec), COLORS, PALETTE).layout.meta
    refit = meta[exposure_traces.REFIT_META]
    assert refit["axes"] == ["yaxis"] and refit["price_axis"] == "yaxis"


def test_naaim_and_aaii_share_one_index_panel_between_fixed_zones():
    """One panel under SPY, both lines on it, the 0-20 and 80-100 zones drawn once."""
    _, get_bars, spec = _fixtures()
    fig = s.price_sentiment_figure(s.build_read(get_bars, lambda: spec), COLORS, PALETTE)
    lines = [t for t in fig.data if t.name in ("NAAIM exposure", "AAII bulls minus bears")]
    assert len(lines) == 2 and {t.yaxis for t in lines} == {"y2"}
    rects = [(sh.y0, sh.y1) for sh in fig.layout.shapes if sh.type == "rect"]
    assert rects.count((s.HI, 100)) == 1 and rects.count((0, s.LO)) == 1
    assert not any(t.mode == "markers" and len(t.x) > 1 for t in fig.data)


def test_the_time_views_open_on_the_last_five_years():
    _, get_bars, spec = _fixtures()
    read = s.build_read(get_bars, lambda: spec)
    end = read.frame.index[-1]
    for fig in (s.price_sentiment_figure(read, COLORS, PALETTE),
                s.words_money_figure(read, COLORS, PALETTE)):
        lo, hi = fig.layout.xaxis.range
        assert pd.Timestamp(lo) == end - pd.DateOffset(years=s.OPEN_YEARS)
        assert pd.Timestamp(hi) > end


def test_large_specs_take_slot_one_and_sentiment_stays_off_slots_zero_to_two():
    """Large specs wear palette[1] on every positioning chart (plot_traces). NAAIM and
    AAII are not COT categories, so they never take a category slot, in either view."""
    _, get_bars, spec = _fixtures()
    read = s.build_read(get_bars, lambda: spec)
    words = {t.name: t for t in s.words_money_figure(read, COLORS, PALETTE).data if t.name}
    price = {t.name: t for t in s.price_sentiment_figure(read, COLORS, PALETTE).data
             if t.name}
    assert words[s.POSITIONING_LABEL].line.color == PALETTE[1]
    for _, label in s.SERIES[:2]:
        assert words[label].line.color not in PALETTE[:3]
        assert price[label].line.color == words[label].line.color
    assert price["NAAIM exposure"].line.color != price["AAII bulls minus bears"].line.color


def test_the_quadrant_window_counts_back_from_the_latest_joint_week():
    weeks = pd.date_range("2020-01-03", periods=300, freq="W-FRI")
    j = pd.DataFrame({"naaim_idx": 50.0, "spec_idx": 50.0}, index=weeks)
    w = s.quadrant_window(j, 1)
    assert w.index[-1] == j.index[-1]
    assert (w.index > j.index[-1] - pd.DateOffset(years=1)).all()
    assert len(w) < len(j) and s.quadrant_window(j, None).equals(j)


def test_the_quadrant_draws_only_the_window_and_shades_by_age():
    _, get_bars, spec = _fixtures()
    read = s.build_read(get_bars, lambda: spec)
    j = s.joint(read)
    weeks = next(t for t in s.quadrant_figure(read, COLORS, years=None).data
                 if t.name.startswith("every joint week"))
    assert len(weeks.x) == len(j)
    ages = list(weeks.marker.color)
    assert ages[0] == 0 and ages[-1] == 1 and ages == sorted(ages)
    one = next(t for t in s.quadrant_figure(read, COLORS, years=1).data
               if t.name.startswith("joint weeks, last 1 year"))
    assert len(one.x) == len(s.quadrant_window(j, 1))


def test_the_year_buttons_map_max_to_the_whole_history(monkeypatch):
    import importlib
    monkeypatch.delenv(local_pages.ENV, raising=False)
    page = importlib.import_module("pages.analytics.sentiment")
    assert page.years_value(page.MAX) is None and page.years_value(None) is None
    assert page.years_value(3) == 3
    values = [o["value"] for o in page.year_buttons().options]
    assert values == list(s.QUADRANT_YEARS) + [page.MAX]


# ── words against money: two pairs ────────────────────────────────────────────

def test_a_missing_small_trader_column_is_named_and_the_rest_still_draws():
    _, get_bars, spec = _fixtures()
    read = s.build_read(get_bars, lambda: spec[["spec"]])
    assert read.awaiting == (f"{s.POSITIONING_MARKET} non-reportables",)
    assert "small_idx" not in read.frame and s.joint(read, "aaii", "small").empty
    fig = s.words_money_figure(read, COLORS, PALETTE)
    assert [t.name for t in fig.data if t.type == "bar"] == ["NAAIM minus large specs"]


def test_words_against_money_draws_each_pair_on_its_own_panel_with_its_gap():
    """NAAIM beside large specs, AAII beside non-reportables: each pair on its own
    zoned panel, each gap on the panel under it, words minus money."""
    _, get_bars, spec = _fixtures()
    read = s.build_read(get_bars, lambda: spec)
    fig = s.words_money_figure(read, COLORS, PALETTE)
    axis = {t.name: t.yaxis for t in fig.data}
    assert axis["NAAIM exposure"] == axis[s.POSITIONING_LABEL] == "y"
    assert axis["NAAIM minus large specs"] == "y2"
    assert axis["AAII bulls minus bears"] == axis[s.SMALL_LABEL] == "y3"
    assert axis["AAII minus non-reportables"] == "y4"
    bars = {t.name: t for t in fig.data if t.type == "bar"}
    j = s.joint(read, "aaii", "small")
    np.testing.assert_allclose(bars["AAII minus non-reportables"].y,
                               (j["aaii_idx"] - j["small_idx"]).to_numpy())
    rects = [(sh.y0, sh.y1, sh.yref) for sh in fig.layout.shapes if sh.type == "rect"]
    assert {r[2] for r in rects if r[:2] == (s.HI, 100)} == {"y", "y3"}


def test_the_cot_groups_wear_their_plot_traces_slots():
    """Large specs palette[1] and non-reportables palette[2], as on every positioning
    chart; the sentiment lines stay off slots 0-2."""
    _, get_bars, spec = _fixtures()
    words = {t.name: t for t in s.words_money_figure(s.build_read(get_bars, lambda: spec),
                                                     COLORS, PALETTE).data}
    assert words[s.POSITIONING_LABEL].line.color == PALETTE[1]
    assert words[s.SMALL_LABEL].line.color == PALETTE[2]


def test_the_summary_adds_the_aaii_pair():
    _, get_bars, spec = _fixtures()
    read = s.build_read(get_bars, lambda: spec)
    j = s.joint(read, "aaii", "small")
    line = s.summary(read)
    assert (f"AAII at {j['aaii_idx'].iloc[-1]:.0f}, non-reportables at "
            f"{j['small_idx'].iloc[-1]:.0f} ({j.index[-1]:%Y-%m-%d})") in line


# ── the index lookback toggle ─────────────────────────────────────────────────

@pytest.mark.parametrize("years", s.LOOKBACK_YEARS)
def test_every_index_follows_the_lookback(years):
    """52 x years + 1 of each series' own weeks: 53 at one year, 157 at three."""
    _, get_bars, spec = _fixtures()
    read = s.build_read(get_bars, lambda: spec, lookback_years=years)
    assert read.lookback_years == years
    avg = read.frame["naaim_avg"].dropna()
    pd.testing.assert_series_equal(
        read.frame["naaim_idx"].reindex(avg.index),
        indicators.calculate_range_index(avg, window=52 * years + 1), check_names=False)
    small = read.frame["small"].dropna()
    pd.testing.assert_series_equal(
        read.frame["small_idx"].reindex(small.index),
        indicators.calculate_range_index(small, window=52 * years + 1), check_names=False)


def test_the_default_lookback_is_three_years_the_studys_window():
    assert s.DEFAULT_LOOKBACK == 3 and s.INDEX_WINDOW == s.index_window(3) == 157


def test_the_words_follow_the_lookback():
    _, get_bars, spec = _fixtures()
    one = s.build_read(get_bars, lambda: spec, lookback_years=1)
    three = s.build_read(get_bars, lambda: spec)
    assert "on its 1-year range index" in s.summary(one)
    one_text, three_text = " ".join(s.caption(one)), " ".join(s.caption(three))
    assert "of the trailing year:" in one_text and "trailing three years:" in three_text
    assert "not the window it measured" in one_text
    assert "not the window it measured" not in three_text


def test_the_time_views_keep_the_users_zoom_across_a_lookback_change():
    _, get_bars, spec = _fixtures()
    read = s.build_read(get_bars, lambda: spec, lookback_years=1)
    for fig in (s.price_sentiment_figure(read, COLORS, PALETTE),
                s.words_money_figure(read, COLORS, PALETTE)):
        assert fig.layout.uirevision == s.UIREVISION


def test_the_lookback_buttons_offer_one_and_three_years(monkeypatch):
    monkeypatch.delenv(local_pages.ENV, raising=False)
    page = importlib.import_module("pages.analytics.sentiment")
    radio = page.lookback_buttons().children[1]
    assert [o["value"] for o in radio.options] == list(s.LOOKBACK_YEARS)
    assert radio.value == s.DEFAULT_LOOKBACK
    assert page.lookback_value(1) == 1 and page.lookback_value("3") == 3
    assert page.lookback_value(None) == page.lookback_value(7) == s.DEFAULT_LOOKBACK
