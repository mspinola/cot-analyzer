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
import viz_constants as vc
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
        # The survey's own number sits beside its index, named, so "at 64" is never
        # read as the exposure.
        raw = s.latest_reading(read, key)
        word, since = s.latest_percentile(read, key)
        assert (f"{name} at {idx.iloc[-1]:.0f} ({s.RAW_NAME[key]} {raw:.1f}, "
                f"{s.percentile_phrase(word, since)}, {read.last[key]:%Y-%m-%d})") in line
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
        assert labels == (["3M", "6M"] + [f"{n}Y" for n in exposure_traces.RANGE_YEARS]
                          + ["Max"])
        steps = [b.step for b in fig.layout.xaxis.rangeselector.buttons]
        assert steps[:2] == ["month", "month"]


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
    # The raw weekly dots are the only multi-point marker traces (no scatter quadrant).
    assert not any(t.mode == "markers" and len(t.x) > 1 and not t.name.endswith("as read")
                   for t in fig.data)


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
    assert labels == ["3M", "6M"] + [f"{n}Y" for n in exposure_traces.RANGE_YEARS] + ["Max"]


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
    assert first_on_x2.name.startswith("NAAIM exposure") and len(first_on_x2.x) > 1
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


def test_provisional_weeks_extend_the_official_series_and_only_the_footer_names_them():
    """Since 2026-11-12 the summary, caption and dates no longer flag provisional weeks;
    one footer sentence does (`provisional_note`)."""
    frames, get_bars, full = _with_provisional()
    read = s.build_read(get_bars)
    official_end = s.weekly(frames[s.NAAIM]["Close"]).index[-1]
    assert len(read.provisional) == 6 and read.provisional[0] > official_end
    # The stale week is not spliced in: the official reading stands.
    assert read.frame.loc[official_end, "naaim"] == full["Close"].iloc[179]
    assert read.frame.loc[read.provisional[-1], "naaim"] == full["Close"].iloc[185] + 1.0
    # Filled by provisional weeks, NAAIM is not a quarter behind, so nothing says so.
    assert "provisional" not in s.summary(read) and "quarter behind" not in s.summary(read)
    text = " ".join(s.caption(read))
    assert "provisional" not in text and f"NAAIM {read.last['naaim']:%Y-%m-%d}," in text
    note = s.provisional_note(read)
    assert note.startswith("Provisional data: NAAIM's newest 6 weeks are read off")
    assert "AAII" not in note


def test_provisional_weeks_never_stand_in_for_a_missing_official_series():
    frames, get_bars, _ = _with_provisional()
    del frames[s.NAAIM]
    read = s.build_read(get_bars)
    assert read.provisional == () and "naaim" not in read.frame and s.NAAIM in read.awaiting


def test_provisional_weeks_draw_as_any_other_week():
    _, get_bars, _ = _with_provisional()
    read = s.build_read(get_bars)
    fig = s.price_sentiment_figure(read, COLORS, PALETTE)
    solid = next(t for t in fig.data if t.name == "NAAIM exposure")
    assert not any("provisional" in (t.name or "") for t in fig.data)
    assert solid.line.dash is None
    assert pd.Timestamp(solid.x[-1]) == read.provisional[-1]      # one line to the end
    assert "prov" not in fig.layout.annotations[1].text
    cols = s.columns_figure(read, COLORS, PALETTE)
    naaim = next(t for t in cols.data if t.name == "NAAIM against its average")
    assert naaim.marker.opacity is None
    assert "provisional" not in naaim.hovertemplate


def test_without_provisional_weeks_nothing_is_flagged():
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    assert read.provisional == () and "provisional" not in s.summary(read)
    assert s.provisional_note(read) is None
    # Without provisional weeks NAAIM's store really is a quarter behind, and says so.
    assert "quarter behind" in s.summary(read)
    fig = s.price_sentiment_figure(read, COLORS, PALETTE)
    assert not any("provisional" in (t.name or "") for t in fig.data)


def test_each_card_exports_itself_as_a_png(monkeypatch):
    """Every card carries an export button in its header, the card body is the
    picture's container, and each button has a clientside export with no load call."""
    # Imported before the snapshot: run alone, a first import inside it registered the
    # callbacks once and the reload below again, so each was counted twice.
    monkeypatch.delenv(local_pages.ENV, raising=False)
    importlib.import_module("pages.analytics.sentiment")
    registered = list(dash._callback.GLOBAL_CALLBACK_LIST)
    monkeypatch.setenv(local_pages.ENV, "1")
    page = importlib.reload(importlib.import_module("pages.analytics.sentiment"))
    try:
        assert set(page.EXPORTS) == {"price", "naaim", "votes", "allocation",
                                     "allocation_price", "columns"}
        js = (Path(__file__).parents[1] / "src/assets/clientside.js").read_text()
        assert "export_sentiment_image: function(n_clicks, container_id, lookback)" in js
        # 1x: at 2x the PNG opened at twice the card's size and read as zoomed in.
        assert "view + '_' + (lookback || 3) + 'y', null, 1);" in js
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


def test_the_figures_are_compact():
    """Each card fits a laptop screen: the heights are the named constants, and the
    column rows keep room for their two-line headers."""
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    assert s.price_sentiment_figure(read, COLORS, PALETTE).layout.height == s.PRICE_HEIGHT
    cols = s.columns_figure(read, COLORS, PALETTE)
    assert cols.layout.height == s.COLUMNS_HEIGHT
    assert s.PRICE_HEIGHT <= 500 and s.COLUMNS_HEIGHT <= 700
    # The gap between rows, in px, holds a two-line header (about 40 px).
    gap = (cols.layout.yaxis3.domain[0] - cols.layout.yaxis4.domain[1])
    assert gap * (s.COLUMNS_HEIGHT - 62 - 32) >= 40


# ── the real-time reading ─────────────────────────────────────────────────────

def test_raw_dots_sit_on_the_lines_own_scale():
    """The dots use the AVERAGE's trailing low and high, so the average itself lands
    exactly on the line, and a week beyond the window's extremes is pinned to the edge."""
    _, get_bars = _fixtures()
    for years in s.LOOKBACK_YEARS:
        read = s.build_read(get_bars, lookback_years=years)
        for key in ("naaim", "aaii"):
            raw = read.frame[key].dropna()
            avg = raw.rolling(s.AVERAGE_WEEKS, min_periods=s.AVERAGE_WEEKS).mean()
            pd.testing.assert_series_equal(s.on_index_scale(avg, avg, years),
                                           s.range_index(avg, years), check_names=False)
            dots = read.frame[f"{key}_raw_idx"].dropna()
            assert dots.between(0, 100).all() and len(dots) > 0
            pd.testing.assert_series_equal(
                dots, s.on_index_scale(raw, avg, years).dropna().reindex(dots.index),
                check_names=False, check_freq=False)


def test_a_week_beyond_the_window_is_pinned_to_the_edge():
    idx = pd.date_range("2020-01-03", periods=60, freq="W-FRI")
    avg = pd.Series(np.linspace(10, 20, 60), idx)
    raw = avg.copy()
    raw.iloc[-1], raw.iloc[-2] = 99.0, -5.0
    got = s.on_index_scale(raw, avg, years=1)
    assert got.iloc[-1] == 100.0 and got.iloc[-2] == 0.0


def test_dots_sit_under_the_line_and_the_marker_on_the_newest_dot():
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    fig = s.price_sentiment_figure(read, COLORS, PALETTE)
    names = [t.name for t in fig.data]
    for key, label in s.SERIES:
        dots_at = names.index(f"{label}, week as read")
        assert dots_at < names.index(label)                    # drawn first, so under
        dots = fig.data[dots_at]
        assert dots.mode == "markers" and dots.hoverinfo == "skip"
        assert dots.opacity == s.RAW_DOT_OPACITY and dots.showlegend is False
        marker = fig.data[names.index(f"{label}, latest")]
        newest = read.frame[f"{key}_raw_idx"].dropna()
        assert pd.Timestamp(marker.x[0]) == newest.index[-1]
        assert marker.y[0] == newest.iloc[-1]


def test_the_crowd_state_uses_the_charts_own_lines_and_words():
    """At or past the dashed 80 and 20, decided on the index as printed, and never
    "bullish" or "bearish": the word would read as a call on the market."""
    assert s.crowd_state(s.HI) == s.crowd_state(100.0) == s.STATE_LONG
    assert s.crowd_state(s.LO) == s.crowd_state(0.0) == s.STATE_WASHED
    assert s.crowd_state(s.HI - 1) == s.crowd_state(s.LO + 1) == s.STATE_MID
    # 79.6 prints as 80, so it reads as the zone the number shown is in.
    assert s.crowd_state(79.6) == s.STATE_LONG and s.crowd_state(79.4) == s.STATE_MID
    assert s.crowd_state(20.4) == s.STATE_WASHED
    for word in (s.STATE_LONG, s.STATE_WASHED, s.STATE_MID):
        assert "bull" not in word.lower() and "bear" not in word.lower()
    _, get_bars = _fixtures()
    for r in s.readings(s.build_read(get_bars)):
        assert r["state"] == s.crowd_state(r["index"])


def test_the_two_survey_colours_are_their_palette_slots_toned_down_alike():
    """The full violet was the brightest thing on the page, and with it toned down
    alone the green was. Both take the same step, still derived from the palette, so
    a palette switch repaints them."""
    from components.plot_colors import blend_over, relative_luminance
    colors = s.sentiment_colors(PALETTE)
    page = relative_luminance(vc.BACKGROUND_COLOR)
    assert s.SENTIMENT_STRENGTH["naaim"] == s.SENTIMENT_STRENGTH["aaii"] < 1
    for key in ("naaim", "aaii"):
        slot = PALETTE[s.SENTIMENT_SLOTS[key]]
        assert colors[key] == blend_over(slot, s.SENTIMENT_STRENGTH[key]) != slot
        assert relative_luminance(colors[key]) < relative_luminance(slot)
        # Still a readable mark on the page: 3 to 1 or better against the background.
        assert (relative_luminance(colors[key]) + 0.05) / (page + 0.05) >= 3.0
    assert colors["naaim"] != colors["aaii"]
    other = ["#000000"] * 3 + ["#00FF00", "#000000", "#FF00FF"]
    assert s.sentiment_colors(other) == {"naaim": blend_over("#FF00FF", 0.75),
                                         "aaii": blend_over("#00FF00", 0.75)}


def test_the_shading_keys_are_outlined_in_their_full_hue():
    """Filled as the band is (14-28%), a 12px swatch vanished into the dark page."""
    _, get_bars = _fixtures()
    fig = s.price_sentiment_figure(s.build_read(get_bars), COLORS, PALETTE)
    keys = [t for t in fig.data if (t.legendgroup or "").startswith("drawdown")]
    assert len(keys) == len(s.DRAWDOWN_LEVELS)
    for key, (_, color, alpha, label) in zip(keys, s.DRAWDOWN_LEVELS):
        assert key.name == label and key.marker.line.color == color
        assert key.marker.line.width == 1 and key.marker.color == hex_to_rgba(color, alpha)


def test_the_title_reads_out_the_latest_survey_as_published():
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    title = s.price_sentiment_figure(read, COLORS, PALETTE).layout.annotations[1].text
    naaim, aaii = s.latest_reading(read, "naaim"), s.latest_reading(read, "aaii")
    # As published AND on the panel's own scale, each named: the axis is the index.
    n_idx, a_idx = s.latest_index(read, "naaim"), s.latest_index(read, "aaii")
    assert title == (
        f"NAAIM {naaim:.1f}, index {n_idx:.0f} ({read.last['naaim']:%Y-%m-%d})<br>"
        f"AAII {aaii:.1f}, index {a_idx:.0f} ({read.last['aaii']:%Y-%m-%d})")
    assert n_idx == read.frame["naaim_idx"].dropna().iloc[-1]
    assert naaim == read.frame["naaim"].dropna().iloc[-1]


def test_a_provisional_latest_week_draws_a_filled_marker_and_filled_dots():
    _, get_bars, _ = _with_provisional()
    read = s.build_read(get_bars)
    fig = s.price_sentiment_figure(read, COLORS, PALETTE)
    line = next(t for t in fig.data if t.name == "NAAIM exposure")
    marker = next(t for t in fig.data if t.name == "NAAIM exposure, latest")
    assert marker.marker.color == line.line.color != vc.BACKGROUND_COLOR
    dots = next(t for t in fig.data if t.name == "NAAIM exposure, week as read")
    assert dots.marker.color == line.line.color


# ── provisional AAII weeks ────────────────────────────────────────────────────

def _with_aaii_provisional(n_official=180, n_prov=2, stale=True, legs=(True, True)):
    """The fixtures with AAII's official legs cut short and the next weeks served as
    the provisional legs, plus (when `stale`) one provisional week the official legs
    already cover, which must be ignored. `legs` says which provisional legs exist."""
    frames, _ = _fixtures()
    full = {k: frames[k] for k in (s.AAII_BULL, s.AAII_BEAR)}
    for off, prov, present in ((s.AAII_BULL, s.AAII_BULL_PROVISIONAL, legs[0]),
                               (s.AAII_BEAR, s.AAII_BEAR_PROVISIONAL, legs[1])):
        frames[off] = full[off].iloc[:n_official]
        p = full[off].iloc[n_official:n_official + n_prov]
        if stale:
            p = pd.concat([full[off].iloc[[n_official - 1]] * 0.5, p])
        if present:
            frames[prov] = p

    def get_bars(symbol, tier=None):
        if symbol not in frames:
            raise FileNotFoundError(symbol)
        return frames[symbol]
    return frames, get_bars, full


def test_provisional_aaii_weeks_extend_the_official_legs_and_only_the_footer_names_them():
    frames, get_bars, full = _with_aaii_provisional()
    read = s.build_read(get_bars)
    weeks = s.provisional_weeks(read, "aaii")
    official_end = s.weekly(frames[s.AAII_BULL]["Close"]).index[-1]
    assert len(weeks) == 2 and weeks[0] > official_end
    assert read.provisional == ()                          # NAAIM's are untouched
    bull, bear = full[s.AAII_BULL]["Close"], full[s.AAII_BEAR]["Close"]
    # The stale week is not spliced in: the official reading stands.
    assert read.frame.loc[official_end, "aaii"] == pytest.approx(
        (bull.iloc[179] - bear.iloc[179]) * 100)
    assert read.frame.loc[weeks[-1], "aaii"] == pytest.approx(
        (bull.iloc[181] - bear.iloc[181]) * 100)
    assert read.last["aaii"] == bull.index[181].date()
    summ = s.summary(read)
    assert "AAII at" in summ and f"{read.last['aaii']:%Y-%m-%d})" in summ
    assert "provisional" not in summ
    text = " ".join(s.caption(read))
    assert f"AAII {read.last['aaii']:%Y-%m-%d}" in text and "provisional" not in text
    note = s.provisional_note(read)
    assert "AAII's newest 2 weeks are typed from" in note and "within 0.1 point" in note
    assert "NAAIM" not in note


def test_one_provisional_aaii_week_reads_in_the_singular():
    _, get_bars, _ = _with_aaii_provisional(n_prov=1)
    read = s.build_read(get_bars)
    assert "AAII's newest week is typed from" in s.provisional_note(read)


@pytest.mark.parametrize("legs", [(True, False), (False, True)])
def test_one_provisional_aaii_leg_alone_is_not_a_reading(legs):
    frames, get_bars, _ = _with_aaii_provisional(legs=legs)
    read = s.build_read(get_bars)
    assert s.provisional_weeks(read, "aaii") == ()
    assert read.last["aaii"] == frames[s.AAII_BULL].index[-1].date()


def test_provisional_aaii_weeks_never_stand_in_for_missing_official_legs():
    frames, get_bars, _ = _with_aaii_provisional()
    del frames[s.AAII_BEAR]
    read = s.build_read(get_bars)
    assert s.provisional_weeks(read, "aaii") == () and "aaii" not in read.frame
    assert s.AAII_BEAR in read.awaiting


def test_provisional_aaii_weeks_draw_as_any_other_week():
    _, get_bars, _ = _with_aaii_provisional()
    read = s.build_read(get_bars)
    weeks = s.provisional_weeks(read, "aaii")
    fig = s.price_sentiment_figure(read, COLORS, PALETTE)
    label = "AAII bulls minus bears"
    solid = next(t for t in fig.data if t.name == label)
    assert not any("provisional" in (t.name or "") for t in fig.data)
    assert pd.Timestamp(solid.x[-1]) == weeks[-1]
    marker = next(t for t in fig.data if t.name == f"{label}, latest")
    assert marker.marker.color == solid.line.color
    title = fig.layout.annotations[1].text
    assert f"AAII {s.latest_reading(read, 'aaii'):.1f}, index " in title
    assert title.endswith(f"({read.last['aaii']:%Y-%m-%d})") and "prov" not in title
    cols = s.columns_figure(read, COLORS, PALETTE)
    bars_ = next(t for t in cols.data if t.name == label)
    assert bars_.marker.opacity is None and bars_.customdata is None
    assert "provisional" not in bars_.hovertemplate


def test_without_provisional_aaii_weeks_the_columns_carry_no_flag():
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    cols = s.columns_figure(read, COLORS, PALETTE)
    bars_ = next(t for t in cols.data if t.name == "AAII bulls minus bears")
    assert bars_.marker.opacity is None and bars_.customdata is None


def test_an_autorange_is_clipped_to_the_data_so_max_then_1y_lands_on_it():
    """Marker traces make Plotly pad an autorange by about 5% a side; the clip keeps Max
    on the data, so the buttons, which count back from the axis edge, do too."""
    _, get_bars = _fixtures()
    read = s.build_read(get_bars)
    fig = s.price_sentiment_figure(read, COLORS, PALETTE)
    f = read.frame
    first = min(f[c].first_valid_index() for c in ("spy", "naaim_idx", "aaii_idx",
                                                   "naaim_raw_idx", "aaii_raw_idx"))
    want = {"clipmin": f"{first:%Y-%m-%d}", "clipmax": f"{s.open_range(read)[1]:%Y-%m-%d}"}
    for axis in ("xaxis", "xaxis2"):
        opts = fig.layout[axis].autorangeoptions
        assert {"clipmin": opts.clipmin, "clipmax": opts.clipmax} == want
        # Not min/maxallowed: with date strings Plotly 3.7 fails the autorange.
        assert opts.minallowed is None and opts.maxallowed is None


def test_the_refit_handler_clears_a_matched_axis_stale_autorange_on_a_window_fit():
    """Max then 1Y: the button ranges the top axis, the matched axis keeps autorange,
    and the price panel's log/linear switch then re-autoranged the whole group. The
    handler turns the stale flag off on numbered x axes only ('xaxis.autorange' is the
    key it reads as a reset). Behaviour checked in the browser; this pins the code."""
    js = (Path(__file__).parents[1] / "src/assets/clientside.js").read_text()
    fit = js[js.index("function fitAxes"):]
    # gd.layout, not _fullLayout: by the time the handler runs only the input layout
    # still carries the stale flag (the first version read _fullLayout and did nothing).
    assert "/^xaxis\\d+$/.test(k) && gd.layout[k] && gd.layout[k].autorange === true" in fit
    assert "update[k + '.autorange'] = false;" in fit
    assert "isFinite(t0) && isFinite(t1)" in fit      # a reset (infinite bounds) is left alone


# ── percentiles against the whole history ─────────────────────────────────────

def test_percentile_is_the_share_at_or_below_from_1_to_100():
    history = [1.0, 2.0, 3.0, 4.0, np.nan]
    assert s.percentile_of(history, 3.0) == 75        # NaN ignored; ties count as below
    assert s.percentile_of(history, 0.0) == 1         # never 0
    assert s.percentile_of(history, 9.0) == 100
    assert [s.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 96, 100)] == [
        "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "96th", "100th"]


def test_a_reading_past_every_week_is_a_record_not_a_rank():
    history = np.arange(1.0, 101.0)
    assert s.percentile_word(history, 96.0) == "96th"
    assert s.percentile_word(history, 100.0) == s.HIGHEST
    assert s.percentile_word(history, 250.0) == s.HIGHEST
    assert s.percentile_word(history, 1.0) == s.LOWEST
    assert s.percentile_phrase("96th", 1987) == "96th percentile since 1987"
    assert s.percentile_phrase(s.HIGHEST, 1987) == "highest since 1987"


def test_the_newest_reading_is_ranked_on_all_official_weeks_not_the_lookback():
    _, get_bars = _fixtures()
    for years in s.LOOKBACK_YEARS:
        read = s.build_read(get_bars, lookback_years=years)
        for key in ("naaim", "aaii"):
            history = read.frame[key].dropna()
            word, since = s.latest_percentile(read, key)
            assert since == history.index[0].year
            assert word == s.percentile_word(history.to_numpy(), history.iloc[-1])
        tile = {r["key"]: r for r in s.readings(read)}
        word, since = s.latest_percentile(read, "naaim")
        assert tile["naaim"]["pct"] == s.percentile_phrase(word, since)


def test_a_provisional_week_is_ranked_against_the_official_weeks_only():
    _, get_bars, _ = _with_aaii_provisional()
    read = s.build_read(get_bars)
    late = s.provisional_weeks(read, "aaii")
    official = s.official_history(read, "aaii")
    assert len(official) == read.frame["aaii"].dropna().size - len(late)
    assert not official.index.isin(late).any()
    word, _ = s.latest_percentile(read, "aaii")
    assert word == s.percentile_word(official.to_numpy(), s.latest_reading(read, "aaii"))
