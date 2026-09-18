"""The breadth panel under the crowd board: FOMO and net new highs, daily.

What is worth pinning: the panel is DAILY and never goes through the Tuesday collapse
(docs/analysis/2026-09-16-fomo-weekly-sampling.md is why); the zones are the
published ones and their colours keep the board's axis (crowded = bear hue, washed
out = bull hue); the classifiers see the full series before the window is cut, so
the first drawn session already knows its regime; a series the store does not hold
yields no panel and a caption, never an error. Store-free: `_get_bars` and
`_last_date` are stood in for.
"""
import cotmetrics.indicators as ind
import numpy as np
import pandas as pd
import pytest

import components.breadth_panel as bp
from components.plot_colors import GridColors

COLORS = GridColors(bull="#34D399", bear="#FF4D4D",
                    bull_near="rgba(52,211,153,0.5)",
                    bear_near="rgba(255,77,77,0.5)")


def _series(values, start="2026-06-01"):
    idx = pd.bdate_range(start, periods=len(values), name="Date")
    return pd.DataFrame({"Close": np.asarray(values, dtype=float)}, index=idx)


def _frames(n=120, seed=7):
    rng = np.random.default_rng(seed)
    fomo = np.clip(50 + np.cumsum(rng.normal(0, 9, n)), 0.5, 99.5)
    highs = rng.integers(20, 200, n).astype(float)
    lows = rng.integers(20, 200, n).astype(float)
    return {"NASDAQ_FOMO_5D": _series(fomo),
            "NASDAQ_NH52W": _series(highs), "NASDAQ_NL52W": _series(lows)}


def _bars(frames):
    return lambda symbol: frames.get(symbol, pd.DataFrame())


@pytest.fixture(autouse=True)
def _fresh_cache():
    bp._cached_read.cache_clear()
    yield
    bp._cached_read.cache_clear()


# ── the read ──────────────────────────────────────────────────────────────────
def test_read_is_daily_and_trailing_sessions_long():
    r = bp.build_read(get_bars=_bars(_frames()))
    assert len(r.fomo) == bp.SESSIONS and len(r.net) == bp.SESSIONS
    # Daily: consecutive business days, never a weekly collapse.
    assert (pd.Series(r.fomo.index).diff().dt.days.dropna() <= 3).all()
    assert r.date == "2026-11-13"


def test_classifiers_see_history_before_the_window_is_cut():
    frames = _frames()
    full = frames["NASDAQ_FOMO_5D"]["Close"]
    r = bp.build_read(get_bars=_bars(frames))
    expected = ind.fomo_zones(full).iloc[-bp.SESSIONS:]
    assert list(r.zones) == list(expected)
    net_full = frames["NASDAQ_NH52W"]["Close"] - frames["NASDAQ_NL52W"]["Close"]
    assert list(r.regime) == list(ind.net_highs_regime(net_full).iloc[-bp.SESSIONS:])


def test_target_date_ends_the_window_on_the_boards_week():
    r = bp.build_read(get_bars=_bars(_frames()), target_date="2026-09-15")
    assert r.date == "2026-09-15"
    assert r.fomo.index.max() <= pd.Timestamp("2026-09-15")


def test_both_series_are_nasdaq_and_nothing_else_is_read():
    # M-07 defines FOMO on Nasdaq and M-01's pair is Nasdaq by the author's choice; the
    # S&P variant in the store is not offered. Pinned so a toggle does not creep back.
    assert bp.FOMO[0] == "NASDAQ_FOMO_5D" and bp.NET_HIGHS == ("NASDAQ_NH52W", "NASDAQ_NL52W")
    frames = _frames()
    asked = []
    r = bp.build_read(get_bars=lambda s: asked.append(s) or frames[s])
    assert set(asked) == set(bp.SYMBOLS)
    assert r.latest == pytest.approx(float(frames["NASDAQ_FOMO_5D"]["Close"].iloc[-1]))


def test_a_missing_series_yields_no_read():
    frames = _frames()
    del frames["NASDAQ_NL52W"]
    assert bp.build_read(get_bars=_bars(frames)) is None


def test_read_names_the_awaited_symbols_and_raises_nothing(monkeypatch):
    monkeypatch.setattr(bp, "_last_date", lambda s: None)
    r, awaiting = bp.read()
    assert r is None and awaiting == ["NASDAQ_FOMO_5D", "NASDAQ_NH52W", "NASDAQ_NL52W"]
    assert "awaiting series data" in bp.caption(None, awaiting)


def test_read_is_cached_on_the_stores_last_dates(monkeypatch):
    frames = _frames()
    calls = []
    monkeypatch.setattr(bp, "_get_bars", lambda s: calls.append(s) or frames[s])
    monkeypatch.setattr(bp, "_last_date", lambda s: "2026-11-13")
    bp.read()
    bp.read()
    assert len(calls) == 3                       # one pass, three series
    monkeypatch.setattr(bp, "_last_date", lambda s: "2026-11-16")
    bp.read()
    assert len(calls) == 6                       # a new delivery invalidates


def test_the_boards_default_date_means_now_and_an_older_week_cuts():
    assert bp.cut_date("2026-09-15", "2026-09-15") is None
    assert bp.cut_date(None, "2026-09-15") is None
    assert bp.cut_date("2026-09-15", None) is None
    assert bp.cut_date("2026-09-08", "2026-09-15") == "2026-09-08"
    assert bp.cut_date("2026-09-22", "2026-09-15") is None


# ── colours keep the board's axis ─────────────────────────────────────────────
def test_zone_colours_put_crowded_in_the_bear_hue_and_washed_out_in_the_bull_hue():
    assert bp.zone_color("exhaustion", COLORS) == COLORS.bear
    assert bp.zone_color("fear", COLORS) == COLORS.bull
    assert bp.zone_color("recovery", COLORS) == COLORS.bull_near
    assert bp.zone_color("neutral", COLORS) == COLORS.dim
    assert bp.zone_color(None, COLORS) == COLORS.dim
    assert bp.regime_color("up", COLORS) == COLORS.bull
    assert bp.regime_color("down", COLORS) == COLORS.bear
    assert bp.regime_color(None, COLORS) is None


# ── the figure ────────────────────────────────────────────────────────────────
def test_figure_draws_the_published_zone_bands_and_the_regime_runs():
    frames = _frames()
    frames["NASDAQ_NH52W"] = _series([300] * 6 + [10] * 6 + [300] * 108)
    frames["NASDAQ_NL52W"] = _series([10] * 6 + [300] * 6 + [10] * 108)
    r = bp.build_read(get_bars=_bars(frames))
    fig = bp.build_figure(r, COLORS)
    rects = [s for s in fig.layout.shapes if s.type == "rect"]
    zone_rects = [s for s in rects if s.yref == "y"]
    assert sorted((s.y0, s.y1) for s in zone_rects) == sorted([
        (ind.FOMO_EXHAUSTION_MIN, 100), (0, ind.FOMO_FEAR_MAX),
        (ind.FOMO_NEUTRAL[0], ind.FOMO_NEUTRAL[1])])
    regime_rects = [s for s in rects if s.yref == "y2 domain"]
    assert len(regime_rects) == len(bp._runs(r.regime)) >= 1
    assert fig.layout.height == bp.FIGURE_PX
    assert fig.layout.yaxis.range == (0, 100)


def test_figure_labels_the_last_reading_with_its_zone():
    frames = _frames()
    frames["NASDAQ_FOMO_5D"] = _series([50] * 119 + [88])
    r = bp.build_read(get_bars=_bars(frames))
    fig = bp.build_figure(r, COLORS)
    labels = [a.text for a in fig.layout.annotations if a.arrowhead is not None]
    assert any("<b>88</b> exhaustion" in t for t in labels)
    # Both panels name their universe, and it is Nasdaq on both.
    titles = [a.text or "" for a in fig.layout.annotations if a.arrowhead is None]
    assert any("FOMO, Nasdaq Composite" in t for t in titles)
    assert any("Nasdaq net new 52-week highs" in t for t in titles)


def test_hover_carries_the_zone_and_the_two_legs():
    r = bp.build_read(get_bars=_bars(_frames()))
    fig = bp.build_figure(r, COLORS)
    marker_trace = fig.data[1]
    assert all("FOMO" in h for h in marker_trace.hovertext)
    bar = [t for t in fig.data if t.type == "bar"][0]
    assert all("highs" in h and "lows" in h for h in bar.hovertext)


# ── copy ──────────────────────────────────────────────────────────────────────
def test_caption_states_the_session_the_reading_and_the_regime():
    frames = _frames()
    frames["NASDAQ_FOMO_5D"] = _series([50] * 119 + [12])
    frames["NASDAQ_NH52W"] = _series([300] * 120)
    frames["NASDAQ_NL52W"] = _series([10] * 120)
    r = bp.build_read(get_bars=_bars(frames))
    text = bp.caption(r)
    assert "2026-11-13 session" in text and "FOMO (Nasdaq Composite) 12, fear" in text
    assert "regime up (three sessions)" in text and "not a signal" in text


def test_caption_says_when_the_panel_trails_the_board():
    r = bp.build_read(get_bars=_bars(_frames()), target_date="2026-09-15")
    assert "trails the board" not in bp.caption(r, report_date="2026-09-15")
    assert "last session 2026-09-15" in bp.caption(r, report_date="2026-09-29")


def test_help_names_every_published_edge_and_no_composite():
    text = bp.help_text()
    for edge in ("80", "35", "60", "25"):
        assert edge in text
    assert "recovery" in text and "three sessions" in text
    assert "not a signal" in text or "not crowding" in text
    assert "composite" not in text.lower() or "separate" in text
