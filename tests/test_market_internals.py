"""The market internals page: six daily reads and an ETF table, store-free.

What is pinned: each read's number reproduces from a known series (the up/down
volume ratio from QQQ's own 20 sessions to 2026-09-17, the day the view was
recreated), the published cutoffs are cotmetrics' and this page's own are named,
the headline counts reads rather than averaging them, and a symbol the store does
not hold is named as awaiting rather than drawn or raised.

Store-free: `get_bars` is injected; `_get_bars` / `_last_date` are stood in for.
"""
import numpy as np
import pandas as pd
import pytest

import components.market_internals as mi


def _series(values, start="2026-04-01"):
    idx = pd.bdate_range(start, periods=len(values), name="Date")
    return pd.DataFrame({"Close": pd.Series(values, index=idx, dtype=float)})


def _bars(frames):
    def get_bars(symbol, tier=None):
        if symbol not in frames:
            raise FileNotFoundError(symbol)
        return frames[symbol]
    return get_bars


def _walk(n, seed, start="2026-04-01", level=100.0, with_volume=False):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n, name="Date")
    close = level * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    frame = pd.DataFrame({"Close": close}, index=idx)
    if with_volume:
        frame["Volume"] = rng.integers(1_000_000, 5_000_000, n).astype(float)
    return frame


def _universe(n=120):
    """Every symbol the page reads, synthetic, so build_snapshot has a full store."""
    frames = {}
    rng = np.random.default_rng(7)
    idx = pd.bdate_range("2026-04-01", periods=n, name="Date")
    frames[mi.FOMO_SYMBOL] = pd.DataFrame(
        {"Close": rng.uniform(20, 80, n)}, index=idx)
    for i, (_, hi, lo) in enumerate(mi.NET_HIGHS_SYMBOLS):
        frames[hi] = pd.DataFrame({"Close": rng.integers(10, 200, n).astype(float)}, index=idx)
        frames[lo] = pd.DataFrame({"Close": rng.integers(10, 200, n).astype(float)}, index=idx)
    frames[mi.ADVANCING_SYMBOL] = pd.DataFrame({"Close": rng.integers(500, 4000, n).astype(float)}, index=idx)
    frames[mi.DECLINING_SYMBOL] = pd.DataFrame({"Close": rng.integers(500, 4000, n).astype(float)}, index=idx)
    for i, symbol in enumerate(mi.ASSET_SYMBOLS):
        frames[symbol] = _walk(n, seed=10 + i, with_volume=True)
    frames[mi.ROTATION_NUMER] = _walk(n, seed=30, with_volume=True)
    return frames


@pytest.fixture(autouse=True)
def _fresh_cache():
    mi._snapshot.cache_clear()
    yield
    mi._snapshot.cache_clear()


# ── FOMO ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("values, label, verdict", [
    ([50, 85], "Stretched", mi.NEGATIVE),
    ([32.23, 46.66], "Middle ground", mi.NEUTRAL),
    ([30, 20], "Washed out", mi.POSITIVE),
    ([20, 30], "Recovering", mi.POSITIVE),     # up from fear, not yet neutral
    ([50, 70], "Between zones", mi.NEUTRAL),   # the 60-80 gap the SWG does not name
])
def test_fomo_zone_labels_are_cotmetrics_zones_in_the_views_words(values, label, verdict):
    read = mi.fomo_read(_series(values)["Close"])
    assert read.label == label
    assert read.verdict == verdict


def test_fomo_change_is_on_the_day_and_the_path_is_a_month():
    values = list(np.linspace(40, 60, 40)) + [32.23, 46.66]
    read = mi.fomo_read(_series(values)["Close"])
    assert read.value == pytest.approx(46.66)
    assert read.change == pytest.approx(14.43)
    assert len(read.path[1]) == mi.FOMO_PATH_SESSIONS
    assert read.path[0][-1] == read.date


# ── net new highs ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("net, streak", [
    ([1, 2, 3], 3),
    ([-1, -2, 0, -1, -1], -2),
    ([1, -1, 0], 0),
    ([5, -3, 4, 6, 6, 6, 6, 6, 6, 6], 8),
    ([], 0),
])
def test_signed_streak_counts_the_last_sessions_sign_and_a_zero_breaks_it(net, streak):
    assert mi.signed_streak(net) == streak


def test_net_highs_regime_label_streak_and_arrows():
    lows = [100] * 12
    highs = [110, 120, 130, 140] + [95, 96, 97, 98, 99, 90, 92, 90]   # eight negative nets
    read = mi.net_highs_read("Nasdaq", _series(highs)["Close"], _series(lows)["Close"])
    assert (read.highs, read.lows, read.net) == (90, 100, -10)
    assert read.regime == "down" and read.streak == -8
    assert read.label == "Negative 8 days" and read.verdict == mi.NEGATIVE
    assert read.last_three == (-1, -1, -1)


def test_net_highs_without_three_agreeing_sessions_is_mixed():
    lows = [100] * 6
    highs = [90, 92, 95, 97, 96, 105]
    read = mi.net_highs_read("NYSE", _series(highs)["Close"], _series(lows)["Close"])
    assert read.net == 5 and read.regime is None
    assert read.label == "Mixed" and read.verdict == mi.NEUTRAL
    assert read.last_three == (-1, -1, 1) and read.streak == 1


# ── advancing against declining ───────────────────────────────────────────────

@pytest.mark.parametrize("adv, dec, label, verdict", [
    (3459, 1476, "Broad advance", mi.POSITIVE),
    (1000, 3000, "Broad decline", mi.NEGATIVE),
    (2000, 2000, "Mixed", mi.NEUTRAL),
])
def test_advancing_share_labels(adv, dec, label, verdict):
    read = mi.advance_decline_read(_series([adv, adv])["Close"], _series([dec, dec])["Close"])
    assert read.share == pytest.approx(adv / (adv + dec))
    assert (read.label, read.verdict) == (label, verdict)


# ── a series against its average ──────────────────────────────────────────────

def test_credit_below_a_falling_average_is_risk_off():
    values = list(np.linspace(96, 95, 30)) + [94.5]
    read = mi.trend_read("credit", "JNK", _series(values)["Close"], 20, risk_on_above=True)
    assert not read.above and not read.rising
    assert read.label == "Risk off" and read.verdict == mi.NEGATIVE
    assert read.average == pytest.approx(pd.Series(values).tail(20).mean())
    assert read.gap == pytest.approx((94.5 - read.average) / read.average)
    assert len(read.path[1]) == 31 and read.path[2][-1] == pytest.approx(read.average)


def test_credit_above_a_rising_average_is_risk_on():
    values = list(np.linspace(94, 95, 30)) + [96]
    read = mi.trend_read("credit", "JNK", _series(values)["Close"], 20, risk_on_above=True)
    assert read.above and read.rising and read.label == "Risk on"


def test_rotation_below_its_average_is_growth_leading_risk_on():
    """XLP over QQQ: the defensive leg on top, so a ratio UNDER its average is
    growth leading. The opposite orientation from the credit price."""
    values = list(np.linspace(0.12, 0.12, 60)) + [0.1165]
    read = mi.trend_read("rotation", "XLP/QQQ", _series(values)["Close"], 50, risk_on_above=False)
    assert not read.above and read.label == "Risk on" and read.verdict == mi.POSITIVE


def test_the_credit_leg_reads_the_dividend_adjusted_tier():
    """JNK distributes ~6.7% a year monthly, so an ex-dividend notch in the raw
    price reads as a break of the 20-day average. Measured on the real store: the
    raw and adjusted verdicts disagree on about a quarter of sessions in a year,
    and every disagreement in two years is raw-says-risk-off, because a downward
    notch can only push the price under its average. The rotation ratio is on the
    same tier for the dividend-gap reason. Up/down volume is NOT: there the notch
    flips almost no session (0 of QQQ's, 1 of SPY's in two years)."""
    assert mi.CREDIT_TIER == "total"
    assert mi.ROTATION_TIER == "total"
    assert mi.ASSET_TIER == "split"


def test_a_monthly_distribution_notch_alone_flips_the_credit_verdict():
    """The defect the tier change exists to prevent, in one session. A credit price
    drifting gently up sits above its 20-day average; a single drop the size of
    JNK's mean monthly instalment (0.56% of price) puts it below, with nothing about
    credit having changed. On a dividend-adjusted series that session is unchanged
    and the read stays risk on, which is why CREDIT_TIER is the total tier."""
    base = list(np.linspace(95.5, 96.0, 30))
    adjusted = mi.trend_read("credit", "JNK", _series(base + [96.0])["Close"],
                             20, risk_on_above=True)
    raw = mi.trend_read("credit", "JNK",
                        _series(base + [96.0 * (1 - 0.0056)])["Close"],
                        20, risk_on_above=True)
    assert adjusted.above and adjusted.verdict == mi.POSITIVE
    assert not raw.above and raw.verdict == mi.NEGATIVE


def test_too_short_a_series_for_the_average_is_no_read():
    assert mi.trend_read("credit", "JNK", _series([1] * 20)["Close"], 20, True) is None


# ── up/down volume ────────────────────────────────────────────────────────────

# NASDAQ:QQQ daily bars, 2026-08-19 to 2026-09-17, as the TradingView feed served
# them on 2026-09-17 (Labor Day, 2026-09-07, absent). The view read 1.12 with 11 up
# and 9 down that day; this is its reproducer.
QQQ_DATES = ["2026-08-19", "2026-08-20", "2026-08-21", "2026-08-24", "2026-08-25",
             "2026-08-26", "2026-08-27", "2026-08-28", "2026-08-31", "2026-09-01",
             "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-08", "2026-09-09",
             "2026-09-10", "2026-09-11", "2026-09-14", "2026-09-15", "2026-09-16",
             "2026-09-17"]
QQQ_CLOSES = [716.08, 710.93, 713.44, 706.32, 710.72, 711.37, 721.11, 716.43, 716.76,
              707.64, 709.24, 717.67, 718.96, 718.36, 716.31, 708.69, 714.88, 709.18,
              704.54, 704.72, 716.92]
QQQ_VOLUMES = [35801712, 33396416, 33399407, 37443142, 23869646, 20392390, 28723451,
               34105374, 32237181, 35236116, 23476207, 29449781, 32871076, 28341416,
               26763377, 31414409, 26649142, 35218978, 26631661, 35687958, 37138986]


def test_updown_ratio_reproduces_qqq_on_2026_09_17():
    frame = pd.DataFrame({"Close": QQQ_CLOSES, "Volume": QQQ_VOLUMES},
                         index=pd.DatetimeIndex(QQQ_DATES, name="Date"))
    read = mi.updown_read("QQQ", frame)
    assert read.ratio == pytest.approx(1.1225, abs=5e-4)
    assert (read.up_days, read.down_days) == (11, 9)
    assert read.label == "Accumulation" and read.verdict == mi.POSITIVE
    assert read.date == "2026-09-17"


def test_updown_window_is_the_last_twenty_completed_sessions_plus_one_for_the_first_diff():
    frame = pd.DataFrame({"Close": QQQ_CLOSES, "Volume": QQQ_VOLUMES},
                         index=pd.DatetimeIndex(QQQ_DATES, name="Date"))
    assert mi.updown_read("QQQ", frame.tail(20)) is None
    # A longer history gives the same window.
    longer = pd.concat([frame.iloc[:1].rename(index={frame.index[0]: pd.Timestamp("2026-08-18")}),
                        frame])
    assert mi.updown_read("QQQ", longer).ratio == pytest.approx(mi.updown_read("QQQ", frame).ratio)


@pytest.mark.parametrize("ratio, label", [
    (1.6, "Heavy accumulation"), (1.12, "Accumulation"), (1.0, "Balanced"),
    (0.8, "Distribution"), (0.60, "Heavy distribution"),
])
def test_updown_labels_are_this_pages_own_cutoffs(ratio, label):
    assert mi.updown_label(ratio)[0] == label


# ── assets ────────────────────────────────────────────────────────────────────

def test_asset_row_carries_the_day_change_and_a_quarter_of_closes():
    frame = _walk(100, seed=1)
    row = mi.asset_row("QQQ", frame["Close"])
    assert row.last == pytest.approx(frame["Close"].iloc[-1])
    assert row.day_change == pytest.approx(frame["Close"].iloc[-1] / frame["Close"].iloc[-2] - 1)
    assert len(row.path) == mi.PATH_SESSIONS
    assert row.quarter_change == pytest.approx(row.path[-1] / row.path[0] - 1)


# ── the headline ──────────────────────────────────────────────────────────────

def _headline_for(verdicts, monkeypatch):
    monkeypatch.setattr(mi, "read_verdicts", lambda snap: verdicts)
    return mi.headline(None)


def test_headline_counts_positive_reads_of_those_available(monkeypatch):
    P, N, Z = mi.POSITIVE, mi.NEGATIVE, mi.NEUTRAL
    assert _headline_for((Z, N, P, N, P, Z), monkeypatch) == (
        "Internals lean defensive.", "Two of six positive.")
    assert _headline_for((P, N, P, N, P, Z), monkeypatch) == (
        "Internals are mixed.", "Three of six positive.")
    assert _headline_for((P, P, P, P, N, Z), monkeypatch) == (
        "Internals lean constructive.", "Four of six positive.")
    # A read awaiting data counts on neither side, and the count says so.
    assert _headline_for((P, None, None, None, None, None), monkeypatch) == (
        "Internals lean defensive.", "One of one positive.")
    assert _headline_for((None,) * 6, monkeypatch) == (
        "Internals awaiting data.", "No reads available.")


def test_volume_verdict_needs_both_etfs_to_agree():
    frame = pd.DataFrame({"Close": QQQ_CLOSES, "Volume": QQQ_VOLUMES},
                         index=pd.DatetimeIndex(QQQ_DATES, name="Date"))
    acc = mi.updown_read("QQQ", frame)
    dist = mi.UpDownRead("SPY", 0.6, 8, 12, "Heavy distribution", mi.NEGATIVE, acc.date)
    assert mi.volume_verdict((acc, acc)) == mi.POSITIVE
    assert mi.volume_verdict((dist, dist)) == mi.NEGATIVE
    assert mi.volume_verdict((acc, dist)) == mi.NEUTRAL
    assert mi.volume_verdict((acc,)) == mi.NEUTRAL


# ── assembly, and the failure mode it must not have ───────────────────────────

def test_a_full_store_yields_every_card_and_awaits_nothing():
    snap = mi.build_snapshot(_bars(_universe()))
    assert snap.fomo is not None and snap.advance_decline is not None
    assert {r.exchange for r in snap.net_highs} == {"Nasdaq", "NYSE"}
    assert snap.credit.symbol == "JNK" and snap.rotation.symbol == "XLP/QQQ"
    assert [r.symbol for r in snap.updown] == list(mi.UPDOWN_SYMBOLS)
    assert [r.symbol for r in snap.assets] == list(mi.ASSET_SYMBOLS)
    assert snap.awaiting == ()
    assert snap.date == "2026-09-15"   # 120 business days from 2026-04-01
    assert len(mi.summary_sentences(snap)) == 8
    lean, count = mi.headline(snap)
    assert lean.startswith("Internals") and count.endswith("positive.")


def test_a_symbol_the_store_does_not_hold_is_awaited_not_drawn():
    frames = _universe()
    del frames[mi.FOMO_SYMBOL]
    del frames["DIA"]
    del frames["NYSE_NL52W"]
    snap = mi.build_snapshot(_bars(frames))
    assert snap.fomo is None
    assert [r.exchange for r in snap.net_highs] == ["Nasdaq"]
    assert "DIA" not in [r.symbol for r in snap.assets]
    assert set(snap.awaiting) == {mi.FOMO_SYMBOL, "DIA", "NYSE_NL52W"}
    # The other five reads still draw, and the headline counts what was read.
    assert snap.credit is not None and snap.rotation is not None
    assert mi.headline(snap)[1].endswith("of five positive.")


def test_an_unset_store_awaits_everything_and_raises_nothing(monkeypatch):
    def unset(symbol, tier=None):
        raise RuntimeError("MARKETDATA_STORE is not set")
    monkeypatch.setattr(mi, "_get_bars", unset)
    snap = mi.build_snapshot()
    assert snap.fomo is None and snap.net_highs == () and snap.assets == ()
    assert set(mi._all_symbols()) <= set(snap.awaiting)
    assert mi.headline(snap) == ("Internals awaiting data.", "No reads available.")
    assert mi.stale_notes(snap) == []


def test_stale_notes_name_reads_priced_before_the_newest():
    frames = _universe()
    frames[mi.FOMO_SYMBOL] = frames[mi.FOMO_SYMBOL].iloc[:-10]
    snap = mi.build_snapshot(_bars(frames))
    notes = mi.stale_notes(snap)
    assert notes == ["FOMO last read 2026-09-01"]


def test_the_cache_is_keyed_on_the_stores_last_dates(monkeypatch):
    calls = []
    frames = _universe()
    monkeypatch.setattr(mi, "_get_bars", _bars(frames))
    monkeypatch.setattr(mi, "build_snapshot",
                        lambda get_bars=None: calls.append(1) or "snap")
    dates = {"2026-09-15"}
    monkeypatch.setattr(mi, "_last_date", lambda symbol: next(iter(dates)))
    assert mi.snapshot() == "snap" and mi.snapshot() == "snap"
    assert len(calls) == 1
    dates.clear()
    dates.add("2026-09-16")          # a nightly delivery moves every date
    mi.snapshot()
    assert len(calls) == 2
