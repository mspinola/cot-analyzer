"""The local-only sentiment page: the gate, the weekly join, and the two views.

What is pinned: the page exists only when the local flag is explicitly on (licensed
data must not reach the public site), every series lands on the Friday of its week,
every index is cotmetrics' range index over 157 of the series' own weeks, a series
the store lacks is named rather than raised, the views draw, and the page carries no
COT pairing (measured not to move together, 2026-11-05).

Store-free: `get_bars` is injected.
"""
import importlib
from pathlib import Path

import cotmetrics.indicators as indicators
import dash
import numpy as np
import pandas as pd
import pytest

import components.sentiment as s
import local_pages
from components import exposure_traces
from components.plot_colors import GridColors, hex_to_rgba

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


def _commercials_fixture(seed=11):
    """S&P 500 commercials' net % of OI on Tuesday report dates, as the indexer keys it."""
    rng = np.random.default_rng(seed)
    tuesdays = pd.date_range("2022-01-04", periods=N_WEEKS, freq="W-TUE")
    return pd.Series(np.round(rng.uniform(-30, 10, N_WEEKS), 2), index=tuesdays,
                     name=s.COMM_COLUMN)


@pytest.fixture(autouse=True)
def _no_cot_store(monkeypatch):
    """Every read here is store-free: the commercials reader stands in for the indexer."""
    monkeypatch.setattr(s, "_positioning", _commercials_fixture)


def _fixtures(seed=7):
    rng = np.random.default_rng(seed)
    naaim = _weekly(2, rng.uniform(0, 110, N_WEEKS))            # Wednesdays
    bull = _weekly(3, rng.uniform(0.2, 0.5, N_WEEKS))           # Thursdays
    bear = _weekly(3, rng.uniform(0.2, 0.5, N_WEEKS))
    days = pd.bdate_range("2022-01-03", periods=N_WEEKS * 5, name="Date")
    spy = pd.DataFrame({"Close": 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(days))))},
                       index=days)
    frames = {s.NAAIM: naaim, s.AAII_BULL: bull, s.AAII_BEAR: bear, s.PRICE: spy}

    def get_bars(symbol, tier=None):
        if symbol not in frames:
            raise FileNotFoundError(symbol)
        return frames[symbol]
    return frames, get_bars


def test_the_frame_joins_three_series_on_fridays():
    frames, get_bars = _fixtures()
    read = s.build_read(get_bars)
    assert read.awaiting == ()
    assert (read.frame.index.weekday == 4).all()
    assert set(read.last) == {"spy", "naaim", "aaii", "comm"}
    # AAII is bulls minus bears, in percentage points
    bull, bear = frames[s.AAII_BULL]["Close"], frames[s.AAII_BEAR]["Close"]
    want = s.weekly((bull - bear) * 100.0)
    pd.testing.assert_series_equal(read.frame["aaii"].dropna(), want, check_names=False,
                                   check_freq=False)


def test_the_indexes_are_cotmetrics_range_index_over_157_of_the_series_own_weeks():
    """NAAIM and AAII are indexed on their 2-week average, with cotmetrics' own index on
    the board's weeks + 1 window."""
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    naaim = read.frame["naaim"].dropna()
    avg = naaim.rolling(s.AVERAGE_WEEKS, min_periods=s.AVERAGE_WEEKS).mean()
    pd.testing.assert_series_equal(read.frame["naaim_avg"].reindex(naaim.index), avg,
                                   check_names=False)
    want = indicators.calculate_range_index(avg, window=s.INDEX_WEEKS + 1)
    got = read.frame["naaim_idx"].reindex(naaim.index)
    pd.testing.assert_series_equal(got, want, check_names=False)
    assert got.notna().sum() == len(naaim) - (s.AVERAGE_WEEKS - 1) - s.INDEX_WEEKS
    assert got.dropna().between(0, 100).all()


def test_a_missing_series_is_named_not_raised():
    frames, _ = _fixtures()
    del frames[s.NAAIM]

    def get_bars(symbol, tier=None):
        if symbol not in frames:
            raise FileNotFoundError(symbol)
        return frames[symbol]

    read = s.build_read(get_bars)
    assert read.awaiting == (s.NAAIM,)
    assert "naaim" not in read.frame and "naaim_idx" not in read.frame
    assert "NAAIM" not in s.summary(read) and "AAII at" in s.summary(read)
    assert s.price_sentiment_figure(read, COLORS, PALETTE).data


def test_with_neither_survey_there_is_no_summary():
    frames, _ = _fixtures()
    for symbol in (s.NAAIM, s.AAII_BULL):
        del frames[symbol]
    read = s.build_read(lambda symbol, tier=None: frames[symbol])
    assert s.summary(read) is None


def test_an_empty_store_frame_counts_as_missing():
    """A marketdata checkout that predates the registry entry returns an empty frame."""
    _, get_bars = _fixtures()

    def empty_naaim(symbol, tier=None):
        return pd.DataFrame() if symbol == s.NAAIM else get_bars(symbol, tier)

    assert s.NAAIM in s.build_read(empty_naaim).awaiting


def test_commercials_sit_on_their_reports_friday_and_name_themselves_when_absent():
    """The Tuesday report lands on that week's Friday, the day the CFTC publishes it,
    and a COT store that cannot answer is named as awaiting, never raised."""
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    comm = _commercials_fixture()
    pd.testing.assert_series_equal(read.frame["comm"].dropna(), s.weekly(comm),
                                   check_names=False, check_freq=False)
    assert read.last["comm"] == comm.index[-1].date()

    def broken():
        raise FileNotFoundError("no COT store")
    gone = s.build_read(get_bars, get_positioning=broken)
    assert gone.awaiting == (s.COMM_AWAITING,) and "comm" not in gone.frame
    assert len(s.columns_figure(gone, COLORS, PALETTE).data) == 3


# ── views and words ───────────────────────────────────────────────────────────

def test_the_summary_reads_each_surveys_latest_index():
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    line = s.summary(read)
    assert line.startswith("On the 3-year range index:")
    for key, name in (("naaim", "NAAIM"), ("aaii", "AAII")):
        idx = read.frame[f"{key}_idx"].dropna()
        # Dated like the chart title: the stored observation, not the week's Friday.
        assert f"{name} at {idx.iloc[-1]:.0f} ({read.last[key]:%Y-%m-%d})" in line
    assert "quarter behind" in line


def test_the_two_views_draw_and_no_pairing_view_remains():
    """The words-against-money pairs and the quadrant were removed: measured, the pairs
    do not move together. Nothing here may quietly bring them back."""
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    assert s.price_sentiment_figure(read, COLORS, PALETTE).data
    assert s.columns_figure(read, COLORS, PALETTE).data
    for gone in ("words_money_figure", "quadrant_figure", "joint", "PAIRS"):
        assert not hasattr(s, gone)


def test_the_caption_states_the_lag_the_index_caveat_the_study_and_the_licence():
    _, get_bars = _fixtures()
    text = " ".join(s.caption(s.build_read(get_bars)))
    assert "quarter behind" in text and "pre-registration" in text
    assert "scale shifts under the line" in text
    assert "Local only" in text and "Context, not signal" in text
    # Why there is no COT pairing: the surveys follow price, not the futures groups.
    assert "mostly follow price" in text and "a contrast, not a pairing" in text


def test_the_price_panel_opens_by_exposures_scale_rule_for_its_window():
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    axis = s.price_sentiment_figure(read, COLORS, PALETTE).layout.yaxis
    spy = read.frame["spy"].dropna()
    shown = spy[spy.index >= s.open_range(read)[0]]
    assert axis.type == exposure_traces.price_axis_type(shown)


def test_the_time_views_carry_the_apps_year_buttons():
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    for fig in (s.price_sentiment_figure(read, COLORS, PALETTE),
                s.columns_figure(read, COLORS, PALETTE)):
        labels = [b.label for b in fig.layout.xaxis.rangeselector.buttons]
        assert labels == [f"{n}Y" for n in exposure_traces.RANGE_YEARS] + ["Max"]


def test_only_the_price_axis_is_refitted_on_a_zoom():
    """The index panels are pinned to 0-100; re-fitting them would undo the index."""
    _, get_bars = _fixtures()
    meta = s.price_sentiment_figure(s.build_read(get_bars), COLORS, PALETTE).layout.meta
    refit = meta[exposure_traces.REFIT_META]
    assert refit["axes"] == ["yaxis"] and refit["price_axis"] == "yaxis"


def test_naaim_and_aaii_share_one_index_panel_between_fixed_zones():
    """One panel under SPY, both lines on it, the 20 and 80 zones drawn once each as
    dotted lines (the drawdown bands own the background)."""
    _, get_bars = _fixtures()
    fig = s.price_sentiment_figure(s.build_read(get_bars), COLORS, PALETTE)
    lines = [t for t in fig.data if t.name in ("NAAIM exposure", "AAII bulls minus bears")]
    assert len(lines) == 2 and {t.yaxis for t in lines} == {"y2"}
    lines = [sh.y0 for sh in fig.layout.shapes if sh.type == "line" and sh.yref == "y2"]
    assert sorted(lines) == [s.LO, s.HI]
    assert all(sh.line.dash == "dot" for sh in fig.layout.shapes if sh.type == "line")
    assert not [sh for sh in fig.layout.shapes if sh.type == "rect" and sh.yref != "y domain"
                and sh.yref != "y2 domain"]
    assert not any(t.mode == "markers" and len(t.x) > 1 for t in fig.data)


def test_the_time_views_open_on_the_last_five_years():
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    end = read.frame.index[-1]
    for fig in (s.price_sentiment_figure(read, COLORS, PALETTE),
                s.columns_figure(read, COLORS, PALETTE)):
        lo, hi = fig.layout.xaxis.range
        assert pd.Timestamp(lo) == end - pd.DateOffset(years=s.OPEN_YEARS)
        assert pd.Timestamp(hi) > end


def test_sentiment_stays_off_the_cot_category_slots():
    """Slots 0-2 mean commercials, large specs and non-reportables everywhere else in the
    app. NAAIM and AAII are not COT categories, so they never take one."""
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    price = {t.name: t for t in s.price_sentiment_figure(read, COLORS, PALETTE).data
             if t.name}
    for _, label in s.SERIES:
        assert price[label].line.color not in PALETTE[:3]
    assert price["NAAIM exposure"].line.color != price["AAII bulls minus bears"].line.color


# ── the index lookback toggle ─────────────────────────────────────────────────

@pytest.mark.parametrize("years", s.LOOKBACK_YEARS)
def test_every_index_follows_the_lookback(years):
    """52 x years + 1 of each series' own weeks: 53 at one year, 157 at three."""
    _, get_bars = _fixtures()
    read = s.build_read(get_bars, lookback_years=years)
    assert read.lookback_years == years
    avg = read.frame["naaim_avg"].dropna()
    pd.testing.assert_series_equal(
        read.frame["naaim_idx"].reindex(avg.index),
        indicators.calculate_range_index(avg, window=52 * years + 1), check_names=False)
    avg = read.frame["aaii_avg"].dropna()
    pd.testing.assert_series_equal(
        read.frame["aaii_idx"].reindex(avg.index),
        indicators.calculate_range_index(avg, window=52 * years + 1), check_names=False)


def test_the_default_lookback_is_three_years_the_studys_window():
    assert s.DEFAULT_LOOKBACK == 3 and s.INDEX_WINDOW == s.index_window(3) == 157


def test_the_words_follow_the_lookback():
    _, get_bars = _fixtures()
    one = s.build_read(get_bars, lookback_years=1)
    three = s.build_read(get_bars)
    assert s.summary(one).startswith("On the 1-year range index:")
    one_text, three_text = " ".join(s.caption(one)), " ".join(s.caption(three))
    assert "of the trailing year." in one_text and "trailing three years." in three_text
    assert "not the window it measured" in one_text
    assert "not the window it measured" not in three_text


def test_the_time_views_keep_the_users_zoom_across_a_lookback_change():
    _, get_bars = _fixtures()
    read = s.build_read(get_bars, lookback_years=1)
    for fig in (s.price_sentiment_figure(read, COLORS, PALETTE),
                s.columns_figure(read, COLORS, PALETTE)):
        assert fig.layout.uirevision == s.UIREVISION


def test_the_lookback_buttons_offer_one_and_three_years(monkeypatch):
    monkeypatch.delenv(local_pages.ENV, raising=False)
    page = importlib.import_module("pages.analytics.sentiment")
    radio = page.lookback_buttons().children[1]
    assert [o["value"] for o in radio.options] == list(s.LOOKBACK_YEARS)
    assert radio.value == s.DEFAULT_LOOKBACK
    assert page.lookback_value(1) == 1 and page.lookback_value("3") == 3
    assert page.lookback_value(None) == page.lookback_value(7) == s.DEFAULT_LOOKBACK


def test_the_page_draws_each_chart_once_per_load(monkeypatch):
    """layout() draws at the defaults, so no callback may fire on load: a second draw
    racing the first garbled the page on refresh. With no initial call, a persisted
    control would disagree with the charts, so the controls do not persist."""
    registered = list(dash._callback.GLOBAL_CALLBACK_LIST)
    monkeypatch.setenv(local_pages.ENV, "1")
    page = importlib.reload(importlib.import_module("pages.analytics.sentiment"))
    try:
        ours = [c for c in dash._callback.GLOBAL_CALLBACK_LIST[len(registered):]
                if any(i["id"] == page.LOOKBACK for i in c["inputs"])]
        assert len(ours) == 1 and all(c["prevent_initial_call"] for c in ours)
        assert getattr(page.lookback_buttons().children[1], "persistence", None) is None
    finally:
        dash._callback.GLOBAL_CALLBACK_LIST[:] = registered
        monkeypatch.delenv(local_pages.ENV)
        importlib.reload(page)
        for key in [k for k, v in dash.page_registry.items() if v.get("path") == "/sentiment"]:
            del dash.page_registry[key]


# ── weekly columns ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("years", s.LOOKBACK_YEARS)
def test_naaims_trailing_average_uses_only_prior_weeks(years):
    """The mean of the prior 52 x years weeks, this week excluded: changing this week's
    reading must not move this week's reference."""
    _, get_bars = _fixtures()
    read = s.build_read(get_bars, lookback_years=years)
    naaim = read.frame["naaim"].dropna()
    want = naaim.shift(1).rolling(52 * years, min_periods=52 * years).mean()
    pd.testing.assert_series_equal(read.frame["naaim_trail"].reindex(naaim.index), want,
                                   check_names=False)
    pd.testing.assert_series_equal(read.frame["naaim_dev"].reindex(naaim.index),
                                   naaim - want, check_names=False)
    bumped = naaim.copy()
    bumped.iloc[-1] += 50
    assert s.trailing_average(bumped, years).iloc[-1] == want.iloc[-1]


def test_the_columns_view_draws_naaim_against_its_average_and_aaii_as_read():
    """Weekly columns like the COT net-positioning chart, each on its own panel in its
    sentiment colour."""
    _, get_bars = _fixtures()
    read = s.build_read(get_bars, lookback_years=1)
    fig = s.columns_figure(read, COLORS, PALETTE)
    bars = {t.name: t for t in fig.data}
    assert {t.type for t in fig.data} == {"bar"}
    spy, comm = bars["SPY return"], bars["ES commercials"]
    naaim, aaii = bars["NAAIM against its average"], bars["AAII bulls minus bears"]
    assert (spy.yaxis, naaim.yaxis, aaii.yaxis, comm.yaxis) == ("y", "y2", "y3", "y4")
    # The contrast row is the COT chart's column in the COT chart's colour, as read.
    np.testing.assert_allclose(comm.y, read.frame["comm"].dropna().round(1).to_numpy())
    assert comm.marker.color == PALETTE[s.COMM_SLOT]
    assert "contrast" in fig.layout.annotations[3].text
    np.testing.assert_allclose(naaim.y, read.frame["naaim_dev"].dropna().round(1).to_numpy())
    np.testing.assert_allclose(aaii.y, read.frame["aaii"].dropna().round(1).to_numpy())
    colors = s.sentiment_colors(PALETTE)
    assert naaim.marker.color == colors["naaim"] and aaii.marker.color == colors["aaii"]
    assert naaim.opacity == s.COLUMN_OPACITY and fig.layout.bargap == s.COLUMN_BARGAP
    assert "1Y avg" in fig.layout.annotations[1].text
    labels = [b.label for b in fig.layout.xaxis.rangeselector.buttons]
    assert labels == [f"{n}Y" for n in exposure_traces.RANGE_YEARS] + ["Max"]


def test_spy_columns_are_the_trailing_return_coloured_by_sign():
    """SPY's panel is its total return over the 13 weeks to each Friday (point-in-time:
    truncating the history leaves earlier columns unchanged), bull up and bear down."""
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    spy = read.frame["spy"].dropna()
    want = (spy / spy.shift(s.SPY_RETURN_WEEKS) - 1).mul(100).dropna()
    got = s.spy_return(read)
    pd.testing.assert_series_equal(got, want, check_names=False)
    cut = s.SentimentRead(frame=read.frame.iloc[:-20], last=read.last, awaiting=(),
                          lookback_years=read.lookback_years)
    pd.testing.assert_series_equal(s.spy_return(cut), got.iloc[:len(s.spy_return(cut))])
    bar = next(t for t in s.columns_figure(read, COLORS, PALETTE).data
               if t.name == "SPY return")
    np.testing.assert_allclose(bar.y, got.round(1).to_numpy())
    assert list(bar.marker.color) == [s.SPY_UP if v >= 0 else COLORS.bear for v in bar.y]
    assert bar.xaxis == "x" and bar.yaxis == "y"
    # Up weeks must not wear AAII's colour two panels down.
    assert s.SPY_UP not in set(s.sentiment_colors(PALETTE).values())


def test_column_panels_open_fitted_to_the_window_with_zero_in_view():
    """The browser re-fits all three column axes (zero kept) on a button or a drag, and
    the server opens them as that fit would, not on the full history."""
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    fig = s.columns_figure(read, COLORS, PALETTE)
    refit = fig.layout.meta["refit"]
    assert refit["axes"] == refit["zero"] == list(s.COLUMN_AXES)
    t0, t1 = s.open_range(read)
    for trace in fig.data:
        axis = fig.layout[trace.yaxis.replace("y", "yaxis", 1)]
        x = pd.DatetimeIndex(trace.x)
        shown = np.asarray(trace.y, dtype=float)[(x >= t0) & (x <= t1)]
        lo, hi = axis.range
        assert lo < min(shown.min(), 0) and hi > max(shown.max(), 0)
        assert lo <= 0 <= hi


def test_only_naaims_columns_follow_the_lookback():
    _, get_bars = _fixtures()
    one = {t.name: t for t in s.columns_figure(
        s.build_read(get_bars, lookback_years=1), COLORS, PALETTE).data}
    three = {t.name: t for t in s.columns_figure(
        s.build_read(get_bars), COLORS, PALETTE).data}
    for name in ("AAII bulls minus bears", "SPY return", "ES commercials"):
        np.testing.assert_allclose(one[name].y, three[name].y)
    assert len(one["NAAIM against its average"].y) > len(three["NAAIM against its average"].y)


def test_hover_reads_on_the_dark_page():
    """A transparent page needs its own hover colours, and bar values arrive rounded
    because Plotly drops a bar template's number format."""
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    for fig in (s.price_sentiment_figure(read, COLORS, PALETTE),
                s.columns_figure(read, COLORS, PALETTE)):
        assert fig.layout.hoverlabel.bgcolor == "#0e1116"
        for bar in (t for t in fig.data if t.type == "bar"):
            assert ":" not in bar.hovertemplate.split("<extra>")[0]
            np.testing.assert_allclose(bar.y, np.round(bar.y, 1))


# ── SPY drawdown bands ────────────────────────────────────────────────────────

def test_drawdown_levels_are_measured_from_the_high_so_far():
    """Point-in-time: a week's depth uses only highs up to that week, so a later
    recovery to a new high cannot reach back and erase an earlier band."""
    weeks = pd.date_range("2024-01-05", periods=8, freq="W-FRI")
    spy = pd.Series([100, 96, 89, 79, 85, 101, 99, 120], index=weeks, dtype=float)
    assert list(s.drawdown_level(spy)) == [0, 0, 2, 3, 2, 0, 0, 0]
    assert list(s.drawdown_level(spy.iloc[:5])) == [0, 0, 2, 3, 2]


def test_drawdown_runs_merge_consecutive_weeks():
    weeks = pd.date_range("2024-01-05", periods=8, freq="W-FRI")
    spy = pd.Series([100, 94, 94, 89, 89, 100, 94, 101], index=weeks, dtype=float)
    assert s.drawdown_runs(spy) == [(weeks[1], weeks[2], 1), (weeks[3], weeks[4], 2),
                                    (weeks[6], weeks[6], 1)]


def test_the_bands_run_behind_both_panels_one_hue_per_depth():
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    fig = s.price_sentiment_figure(read, COLORS, PALETTE)
    runs = s.drawdown_runs(read.frame["spy"])
    bands = [sh for sh in fig.layout.shapes if sh.type == "rect"]
    assert runs and len(bands) == 2 * len(runs)          # one per panel per run
    assert {sh.xref for sh in bands} == {"x", "x2"} and all(sh.layer == "below" for sh in bands)
    for (_, _, lvl), sh in zip(runs, bands[::2]):
        _, color, alpha, _ = s.DRAWDOWN_LEVELS[lvl - 1]
        assert sh.fillcolor == hex_to_rgba(color, alpha)
        assert sh.legendgroup == f"drawdown{lvl}"


def test_the_depth_keys_are_traces_and_no_band_enters_the_legend():
    """A shape in the legend makes Plotly 3.7 discard every range change on the matched
    top x axis, so the year buttons stop working. The keys are empty traces sharing the
    bands' legend group instead, one per depth, always all three."""
    _, get_bars = _fixtures()
    fig = s.price_sentiment_figure(s.build_read(get_bars), COLORS, PALETTE)
    assert fig.layout.xaxis.matches == "x2"      # the condition the bug needs
    # An empty key trace first on an axis typed it as numbers; both are pinned to dates.
    assert fig.layout.xaxis.type == fig.layout.xaxis2.type == "date"
    first_on_x2 = next(t for t in fig.data if t.xaxis == "x2")
    assert first_on_x2.name == "NAAIM exposure"
    assert not any(sh.showlegend for sh in fig.layout.shapes)
    keys = [t for t in fig.data if (t.legendgroup or "").startswith("drawdown")]
    assert [k.name for k in keys] == [label for *_, label in s.DRAWDOWN_LEVELS]
    assert [k.legendgroup for k in keys] == ["drawdown1", "drawdown2", "drawdown3"]
    for k, (_, color, alpha, _) in zip(keys, s.DRAWDOWN_LEVELS):
        assert k.marker.color == hex_to_rgba(color, alpha) and k.showlegend is not False
        assert list(k.x) == [None] and k.hoverinfo == "skip"


def test_the_depths_differ_in_hue_and_strengthen_with_depth():
    """Hue tells the depths apart and opacity still rises, so the order survives a
    reader who cannot separate amber from red."""
    assert len({color for _, color, _, _ in s.DRAWDOWN_LEVELS}) == len(s.DRAWDOWN_LEVELS)
    cuts = [cut for cut, *_ in s.DRAWDOWN_LEVELS]
    alphas = [alpha for _, _, alpha, _ in s.DRAWDOWN_LEVELS]
    assert cuts == sorted(cuts) and alphas == sorted(alphas) and len(set(alphas)) == 3


def test_each_column_row_carries_its_own_sentence():
    """The row's explanation sits in the row's header, not in one card paragraph."""
    _, get_bars = _fixtures()
    fig = s.columns_figure(s.build_read(get_bars), COLORS, PALETTE)
    titles = [a.text for a in fig.layout.annotations]
    assert len(titles) == 4 and all("<br>" in t for t in titles)
    assert "track most closely" in titles[0] and "prior 3 years" in titles[1]
    assert "lookback does not change" in titles[2] and "barely moves" in titles[3]


# ── provisional NAAIM weeks ───────────────────────────────────────────────────

def _with_provisional(n_official=180, n_prov=6, stale=True):
    """The fixtures with NAAIM's official series cut short and the rest served as
    the provisional series, plus (when `stale`) one provisional week the official
    series already covers, which must be ignored."""
    frames, _ = _fixtures()
    full = frames[s.NAAIM]
    frames[s.NAAIM] = full.iloc[:n_official]
    prov = full.iloc[n_official:n_official + n_prov] + 1.0
    if stale:
        prov = pd.concat([full.iloc[[n_official - 1]] - 50.0, prov])
    frames[s.NAAIM_PROVISIONAL] = prov

    def get_bars(symbol, tier=None):
        if symbol not in frames:
            raise FileNotFoundError(symbol)
        return frames[symbol]
    return frames, get_bars, full


def test_provisional_weeks_extend_the_official_series_and_are_flagged():
    frames, get_bars, full = _with_provisional()
    read = s.build_read(get_bars)
    official_end = s.weekly(frames[s.NAAIM]["Close"]).index[-1]
    assert len(read.provisional) == 6 and read.provisional[0] > official_end
    # The stale week is not spliced in: the official reading stands.
    assert read.frame.loc[official_end, "naaim"] == full["Close"].iloc[179]
    assert read.frame.loc[read.provisional[-1], "naaim"] == full["Close"].iloc[185] + 1.0
    assert "provisional" in s.summary(read) and "last 6 weeks" in s.summary(read)
    text = " ".join(s.caption(read))
    assert "6 weeks from" in text and "provisional" in text
    assert f"NAAIM {read.last['naaim']:%Y-%m-%d} (provisional)," in text


def test_provisional_weeks_never_stand_in_for_a_missing_official_series():
    frames, get_bars, _ = _with_provisional()
    del frames[s.NAAIM]
    read = s.build_read(get_bars)
    assert read.provisional == () and "naaim" not in read.frame and s.NAAIM in read.awaiting


def test_provisional_weeks_draw_dotted_hollow_and_faint():
    _, get_bars, _ = _with_provisional()
    read = s.build_read(get_bars)
    fig = s.price_sentiment_figure(read, COLORS, PALETTE)
    solid = next(t for t in fig.data if t.name == "NAAIM exposure")
    dotted = next(t for t in fig.data if t.name == "NAAIM exposure (provisional)")
    assert dotted.line.dash == "dot" and dotted.showlegend is False
    assert pd.Timestamp(dotted.x[0]) == pd.Timestamp(solid.x[-1])   # the segments join
    assert pd.Timestamp(solid.x[-1]) < read.provisional[0]
    assert "provisional" in fig.layout.annotations[1].text
    cols = s.columns_figure(read, COLORS, PALETTE)
    naaim = next(t for t in cols.data if t.name == "NAAIM against its average")
    faint = pd.DatetimeIndex(naaim.x).isin(read.provisional)
    assert faint.sum() == 6
    np.testing.assert_allclose(np.asarray(naaim.marker.opacity)[faint], s.PROVISIONAL_OPACITY)
    np.testing.assert_allclose(np.asarray(naaim.marker.opacity)[~faint], 1.0)


def test_without_provisional_weeks_nothing_is_flagged():
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    assert read.provisional == () and "provisional" not in s.summary(read)
    fig = s.price_sentiment_figure(read, COLORS, PALETTE)
    assert not any("provisional" in (t.name or "") for t in fig.data)


def test_each_card_exports_itself_as_a_png(monkeypatch):
    """Both cards carry an export button in their header, the card body is the
    picture's container, and each button has a clientside export with no load call."""
    registered = list(dash._callback.GLOBAL_CALLBACK_LIST)
    monkeypatch.setenv(local_pages.ENV, "1")
    page = importlib.reload(importlib.import_module("pages.analytics.sentiment"))
    try:
        assert set(page.EXPORTS) == {"price", "columns"}
        js = (Path(__file__).parents[1] / "src/assets/clientside.js").read_text()
        assert "export_sentiment_image: function(n_clicks, container_id, lookback)" in js
        for view, (container, button) in page.EXPORTS.items():
            card = page._card("t", None, {}, export=view)
            assert card.children.id == container
            ids = {getattr(c, "id", None) for c in card.children.children[0].children[1].children}
            assert button in ids
            ours = [c for c in dash._callback.GLOBAL_CALLBACK_LIST[len(registered):]
                    if any(i["id"] == button for i in c["inputs"])]
            assert len(ours) == 1 and ours[0]["prevent_initial_call"]
    finally:
        dash._callback.GLOBAL_CALLBACK_LIST[:] = registered
        monkeypatch.delenv(local_pages.ENV)
        importlib.reload(page)
        for key in [k for k, v in dash.page_registry.items() if v.get("path") == "/sentiment"]:
            del dash.page_registry[key]
