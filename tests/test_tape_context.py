"""The tape-context block on the crowd board: four ETF ratios on the board's windows.

What is worth pinning is the part that can silently come apart from the markets
above it: the ratios must be scored on the SAME window rule (weeks + 1 reports, full
history with the two-year floor), read at the SAME cadence (the Tuesday close), and
oriented so the board's colour axis keeps its meaning (defensive leg on top). The
rest is the failure mode the block must not have: a leg the store does not hold yet
is named in the caption and draws nothing, and a context row's marks carry no click
target, since there is no market page behind them.

Store-free: `_get_bars` and `_last_date` are stood in for.
"""
import cotmetrics.constants as const
import cotmetrics.models as models
import numpy as np
import pandas as pd
import pytest

import app_utils
import components.board_traces as bt
import components.tape_context as tc
from components.plot_colors import GridColors

COLORS = GridColors(bull="#34D399", bear="#FF4D4D",
                    bull_near="rgba(52,211,153,0.5)",
                    bear_near="rgba(255,77,77,0.5)")


def _daily(n=900, seed=3, start="2023-01-02"):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    return pd.DataFrame({"Close": 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))},
                        index=idx)


def _bars_for(frames):
    def get_bars(symbol, tier):
        return frames[symbol]
    return get_bars


@pytest.fixture(autouse=True)
def _fresh_cache():
    tc._context_frame.cache_clear()
    yield
    tc._context_frame.cache_clear()


# ── orientation ───────────────────────────────────────────────────────────────

def test_every_ratio_puts_the_defensive_leg_on_top():
    """The board's bull hue is the crowd washed out. Each ratio is written so its
    high end is the fearful, broad or stressed side; flipped, its colours lie."""
    tops = {r.symbol for r in tc.RATIOS}
    assert tops == {"XLP/QQQ", "RSP/SPY", "IEF/HYG", "VIX/VIX3M"}


def test_dividend_gap_ratios_read_the_total_return_tier():
    tiers = {r.symbol: r.tier for r in tc.RATIOS}
    assert tiers["XLP/QQQ"] == "total"
    assert tiers["IEF/HYG"] == "total"
    assert tiers["RSP/SPY"] == "total"
    # The vol indices distribute nothing; their equity tiers are a passthrough.
    assert tiers["VIX/VIX3M"] == "split"


# ── cadence ───────────────────────────────────────────────────────────────────

def test_weekly_close_lands_on_tuesdays_and_takes_the_last_close_on_or_before():
    idx = pd.bdate_range("2026-08-03", periods=10)   # Mon 3rd .. Fri 14th
    s = pd.Series(range(10), index=idx, dtype=float)
    # Tuesday the 11th is a holiday: no bar.
    s = s.drop(pd.Timestamp("2026-08-11"))

    weekly = tc.weekly_close(s)
    assert all(d.weekday() == 1 for d in weekly.index)
    assert weekly.loc["2026-08-04"] == 1.0            # Tuesday's own close
    assert weekly.loc["2026-08-11"] == 5.0            # Monday the 10th stands in


def test_ratio_series_aligns_the_legs_on_shared_dates():
    a = _daily(seed=1)
    b = _daily(seed=2)
    b = b.drop(b.index[100:110])                      # a hole in one leg
    get_bars = _bars_for({"XLP": a, "QQQ": b})
    ratio = tc.RATIOS[0]

    weekly = tc.ratio_series(ratio, get_bars=get_bars)
    daily = (a["Close"] / b["Close"]).dropna()
    expected = daily.resample("W-TUE").last().dropna()
    pd.testing.assert_series_equal(weekly, expected, check_names=False)
    assert weekly.name == ratio.key


# ── the window rule, shared with the markets ──────────────────────────────────

def test_window_index_frame_uses_weeks_plus_one_observations_and_the_history_floor():
    idx = pd.date_range("2020-01-07", periods=300, freq="7D")
    s = pd.Series(np.random.default_rng(0).normal(size=300), index=idx)
    out = tc.window_index_frame(s)

    assert list(out.columns) == list(bt.WINDOW_LABELS) + ["move"]
    # 13-week window: 14 observations, so the 14th row is the first with a value.
    assert out["3M"].iloc[:13].isna().all() and out["3M"].notna().iloc[13]
    assert out["12M"].iloc[:52].isna().all() and out["12M"].notna().iloc[52]
    # Full history: the two-year floor, then an expanding window.
    floor = tc.FULL_HISTORY_MIN_WEEKS
    assert out["Full"].iloc[:floor - 1].isna().all() and out["Full"].notna().iloc[floor - 1]
    assert out.attrs["history_weeks"] == 300
    assert out.attrs["start"] == "2020-01-07"
    assert out["move"].equals(out["12M"] - out["12M"].shift(const.MOMENTUM_PERIOD))


# ── reads, and the awaiting case ──────────────────────────────────────────────

def _install(monkeypatch, frames, present=None):
    present = frames.keys() if present is None else present
    monkeypatch.setattr(tc, "_get_bars", _bars_for(frames))

    def last_date(symbol):
        if symbol not in present:
            raise FileNotFoundError(symbol)
        return str(frames[symbol].index[-1].date())
    monkeypatch.setattr(tc, "_last_date", last_date)


def _all_legs():
    frames = {}
    for i, r in enumerate(tc.RATIOS):
        frames[r.numer] = _daily(seed=10 + i)
        frames[r.denom] = _daily(seed=20 + i)
    return frames


def test_context_reads_are_unlinked_chipless_rows_in_their_own_class(monkeypatch):
    _install(monkeypatch, _all_legs())
    reads, awaiting = tc.context_reads()

    assert awaiting == []
    assert [r.asset.split(" · ")[0] for r in reads] == [r.symbol for r in tc.RATIOS]
    for read in reads:
        # The ratio leads the name; the ticker slot is blank, since "VIX/VIX3M"
        # overruns a column cut for a futures symbol.
        assert read.symbol == ""
        assert read.asset_class == bt.CONTEXT_CLASS
        assert read.linked is False
        assert read.state == const.SETUP_NONE
        assert read.measure.endswith(" index")
        assert "high:" in read.note and "low:" in read.note
        assert len(read.windows) == len(bt.WINDOW_LABELS)
        assert read.windows[0] is not None
        assert read.date and pd.Timestamp(read.date).weekday() == 1


def test_a_leg_the_store_does_not_hold_is_awaited_not_drawn(monkeypatch):
    frames = _all_legs()
    del frames["VIX3M"]
    _install(monkeypatch, frames)
    reads, awaiting = tc.context_reads()

    assert awaiting == ["VIX/VIX3M"]
    assert [r.asset.split(" · ")[0] for r in reads] == ["XLP/QQQ", "RSP/SPY", "IEF/HYG"]


def test_an_unset_store_awaits_every_ratio_and_raises_nothing(monkeypatch):
    def boom(symbol):
        raise RuntimeError("MARKETDATA_STORE is not set")
    monkeypatch.setattr(tc, "_last_date", boom)
    reads, awaiting = tc.context_reads()
    assert reads == []
    assert awaiting == [r.symbol for r in tc.RATIOS]


def test_target_date_reads_the_week_the_board_shows(monkeypatch):
    _install(monkeypatch, _all_legs())
    reads, _ = tc.context_reads(target_date="2025-06-03")
    assert all(pd.Timestamp(r.date) <= pd.Timestamp("2025-06-03") for r in reads)
    assert all(pd.Timestamp(r.date) > pd.Timestamp("2025-05-20") for r in reads)


def test_the_cache_is_keyed_on_the_stores_last_dates(monkeypatch):
    frames = _all_legs()
    _install(monkeypatch, frames)
    calls = []
    real = tc.ratio_series
    monkeypatch.setattr(tc, "ratio_series", lambda ratio, get_bars=None: (
        calls.append(ratio.key), real(ratio, get_bars))[1])

    tc.context_reads()
    tc.context_reads()
    assert len(calls) == len(tc.RATIOS), "a second render must be a cache hit"

    # A nightly delivery moves a leg's last date, and only that ratio recomputes.
    frames["XLP"] = pd.concat([frames["XLP"], _daily(n=5, start="2026-09-01")])
    tc.context_reads()
    assert calls.count("xlp_qqq") == 2
    assert calls.count("rsp_spy") == 1


# ── the block on the board ────────────────────────────────────────────────────

def _read(symbol, windows=(70, 60, 55, 50)):
    return bt.MarketRead(asset=symbol, asset_class=bt.CONTEXT_CLASS, symbol=symbol,
                         windows=windows, path=(40, 50, 60), move=2.0,
                         linked=False, measure=f"{symbol} index", note="high: a · low: b",
                         history_weeks=300, start="2020-01-07", date="2026-08-18")


def test_build_context_rows_keeps_the_given_order_under_its_own_heading():
    rows, skipped = bt.build_context_rows([_read("B/A"), _read("A/B")])
    assert [r.kind for r in rows] == ["spacer", "class", "market", "market"]
    assert rows[1].label == bt.CONTEXT_CLASS
    assert [r.read.symbol for r in rows[2:]] == ["B/A", "A/B"]
    assert skipped == []


def test_an_unreadable_ratio_is_skipped_and_counted_and_no_heading_stands_alone():
    rows, skipped = bt.build_context_rows([_read("X/Y", windows=(None,) * 4)])
    assert rows == []
    assert skipped == ["X/Y"]


def test_context_marks_carry_no_click_target():
    market = bt.MarketRead(asset="Gold", asset_class="Metals", symbol="GC",
                           windows=(80, 70, 60, 55), path=(40, 55, 60), move=4.0)
    rows, _ = bt.build_rows([market])
    context_rows, _ = bt.build_context_rows([_read("XLP/QQQ")])
    fig = bt.build_figure(rows + context_rows, models.MODELS[0], COLORS)

    targets = set()
    for trace in fig.data:
        if trace.customdata is not None:
            targets.update(trace.customdata)
    assert "Gold" in targets
    assert "XLP/QQQ" not in targets
    # An empty target is what makes the click safe: the router stays put on it.
    assert app_utils.clicked_market_href({"points": [{"customdata": ""}]}) is None
    assert app_utils.clicked_market_href({"points": [{"customdata": "Gold"}]})


def test_hovers_name_the_ratio_not_the_commercial_index():
    text = bt.cell_hover(_read("XLP/QQQ"), 0)
    assert "XLP/QQQ index 70" in text
    assert "Commercial index" not in text
    assert "high: a · low: b" in text
    assert "XLP/QQQ index" in bt.spark_hover(_read("XLP/QQQ"))
    # The markets' hover is unchanged.
    market = bt.MarketRead(asset="Gold", asset_class="Metals", windows=(80, 70, 60, 55))
    assert "Commercial index 80" in bt.cell_hover(market, 0)


# ── a leg that stopped updating ───────────────────────────────────────────────

def test_a_ratio_priced_well_before_the_boards_week_is_named_as_trailing():
    fresh = _read("XLP/QQQ")                                   # 2026-08-18
    stale = bt.MarketRead(asset="VIX/VIX3M · Front over 3-month vol",
                          asset_class=bt.CONTEXT_CLASS, symbol="",
                          windows=(50, 50, 50, 50), date="2026-07-14", linked=False)
    notes = tc.stale_notes([fresh, stale], report_date="2026-08-18")
    # Named by the row's name, since the ticker slot is blank on these rows.
    assert notes == ["VIX/VIX3M · Front over 3-month vol last priced 2026-07-14"]
    # Within the allowance (the equities task runs after the release) is not stale.
    assert tc.stale_notes([fresh], report_date="2026-08-25") == []
    assert tc.stale_notes([fresh, stale], report_date=None) == []
