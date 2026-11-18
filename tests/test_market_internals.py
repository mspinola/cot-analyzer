"""The market internals page: six daily reads and an ETF table, store-free.

What is pinned: each read's number reproduces from a known series (the up/down
volume ratio from QQQ's own 20 sessions to 2026-09-17, the day the view was
recreated), the published cutoffs are cotmetrics' and this page's own are named,
the headline counts reads rather than averaging them, and a symbol the store does
not hold is named as awaiting rather than drawn or raised.

Store-free: `get_bars` is injected; `_get_bars` is stood in for.
"""
import types

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


def test_fomo_change_is_on_the_day_and_the_path_is_a_year():
    values = list(np.linspace(40, 60, 300)) + [32.23, 46.66]
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


@pytest.mark.parametrize("ratio, label, verdict", [
    (1.6, "Heavy accumulation", mi.POSITIVE),
    (1.12, "Accumulation", mi.POSITIVE),
    (1.0, "Accumulation", mi.POSITIVE),      # the centre itself is net buying
    (0.99, "Distribution", mi.NEGATIVE),
    (0.8, "Distribution", mi.NEGATIVE),
    (0.60, "Heavy distribution", mi.NEGATIVE),
])
def test_updown_turns_at_agis_centre_line_with_this_pages_heavy_tiers(ratio, label, verdict):
    """The verdict turns at one, which is agi's definition rather than a tuned
    threshold: the ratio is up volume over down volume and one is where they
    balance. There is no neutral band, and a session just over one reads as net
    buying here exactly as it does there. The heavy tiers are this page's own
    emphasis and move no verdict."""
    assert mi.updown_label(ratio) == (label, verdict)
    assert mi.UPDOWN_CENTRE == 1.0


# ── assets ────────────────────────────────────────────────────────────────────

def test_asset_row_carries_the_day_change_and_a_quarter_of_closes():
    frame = _walk(100, seed=1)
    row = mi.asset_row("QQQ", frame["Close"])
    assert row.last == pytest.approx(frame["Close"].iloc[-1])
    assert row.day_change == pytest.approx(frame["Close"].iloc[-1] / frame["Close"].iloc[-2] - 1)
    assert len(row.path) == mi.PATH_SESSIONS
    assert row.quarter_change == pytest.approx(row.path[-1] / row.path[0] - 1)


# ── the headline ──────────────────────────────────────────────────────────────

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
    assert [h.key for h in snap.headwinds] == list(mi.HEADWIND_KEYS)
    count, lean = mi.headline(snap)
    assert count.endswith("of 5 headwinds on") and lean.endswith(".")


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
    # Half a net-highs sum is a different number, so that headwind is not read; the
    # other four are, and the count says four.
    assert [h.key for h in snap.headwinds] == [k for k in mi.HEADWIND_KEYS if k != "net_highs"]
    assert mi.headline(snap)[0].endswith("of 4 headwinds on")


def test_an_unset_store_awaits_everything_and_raises_nothing(monkeypatch):
    def unset(symbol, tier=None):
        raise RuntimeError("MARKETDATA_STORE is not set")
    monkeypatch.setattr(mi, "_get_bars", unset)
    snap = mi.build_snapshot()
    assert snap.fomo is None and snap.net_highs == () and snap.assets == ()
    assert set(mi._all_symbols()) <= set(snap.awaiting)
    assert snap.headwinds == () and not mi.has_reads(snap)
    assert mi.headline(snap) == ("Headwinds awaiting data", "No trend measure could be read.")
    assert mi.stale_notes(snap) == []


def test_stale_notes_name_reads_priced_before_the_newest():
    frames = _universe()
    frames[mi.FOMO_SYMBOL] = frames[mi.FOMO_SYMBOL].iloc[:-10]
    snap = mi.build_snapshot(_bars(frames))
    notes = mi.stale_notes(snap)
    assert notes == ["FOMO last read 2026-09-01"]



# ── credit appetite: context beside the reads ─────────────────────────────────

def test_credit_appetite_is_cotmetrics_gauge_with_its_divergence_days():
    from cotmetrics import indicators
    frames = _universe(320)
    junk = frames[mi.APPETITE_JUNK]["Close"]
    treasuries = frames[mi.APPETITE_TREASURY]["Close"]
    read = mi.credit_appetite_read(junk, treasuries)
    appetite = indicators.credit_appetite(junk, treasuries).dropna()
    flags = indicators.credit_divergence(junk, treasuries)
    assert read.value == appetite.iloc[-1]
    assert read.change == appetite.iloc[-1] - appetite.iloc[-2]
    assert read.zone == indicators.credit_zone(read.value)
    assert read.label == mi.APPETITE_LABELS[read.zone]
    assert read.date == "2027-06-22" == appetite.index[-1].strftime("%Y-%m-%d")
    # The path is every ranked session (at most a year), the markers the divergence
    # days that fall on it.
    assert len(read.path[0]) == len(read.path[1]) == min(len(appetite), 252)
    on_path = flags.reindex(appetite.tail(252).index).dropna()
    assert read.markers == tuple(zip(on_path.index.strftime("%Y-%m-%d"), on_path))
    assert set(dict(read.markers).values()) <= {"risk_off", "risk_on"}
    assert read.divergence == flags.iloc[-1]


def test_credit_appetite_waits_for_its_history_and_never_joins_the_count():
    """Under 20 + 252 + 1 sessions there is nothing to rank against: no read, no error.
    With one, the old verdicts and the headline are exactly what they were."""
    short = mi.build_snapshot(_bars(_universe(120)))
    assert short.appetite is None
    assert mi.APPETITE_TREASURY not in short.awaiting      # the bars are there
    frames = _universe(320)
    full = mi.build_snapshot(_bars(frames))
    assert full.appetite is not None
    without = mi.build_snapshot(_bars({**frames, mi.APPETITE_TREASURY:
                                       frames[mi.APPETITE_TREASURY].iloc[:50]}))
    assert without.appetite is None
    assert mi.read_verdicts(without) == mi.read_verdicts(full)
    assert mi.headline(without) == mi.headline(full)


def test_a_stale_credit_appetite_is_named():
    frames = _universe(320)
    frames[mi.APPETITE_TREASURY] = frames[mi.APPETITE_TREASURY].iloc[:-10]
    snap = mi.build_snapshot(_bars(frames))
    assert any(n.startswith("credit appetite last read") for n in mi.stale_notes(snap))


# ── the five headwinds (the Caruso dashboard's definitions) ───────────────────

def _days(values, start="2026-04-01"):
    return pd.Series([float(v) for v in values],
                     index=pd.bdate_range(start, periods=len(values), name="Date"))


def test_net_highs_headwind_is_both_exchanges_summed_as_a_five_day_average():
    highs = _days([50] * 10)
    nasdaq_lows = _days([10, 10, 10, 10, 10, 60, 60, 60, 60, 90])
    nyse_lows = _days([10] * 10)
    h = mi.net_highs_headwind([(highs, nasdaq_lows), (highs, nyse_lows)])
    # Daily nets: 80 x5, then 30 x4, then 0. Five-day averages end 40, 30, 24.
    assert h.display == "+24" and not h.on
    assert h.flip == "Flips at 0 · needs -24"
    assert h.streak == 6                      # every averaged session was above zero
    assert h.versus == "worse"                # 24 against 80 five sessions ago
    assert h.level == 0.0 and h.path[2] is None
    worse = mi.net_highs_headwind([(highs, _days([200] * 10)), (highs, nyse_lows)])
    assert worse.on and worse.display == "-110" and worse.flip.endswith("needs +110")
    # One leg missing: no read, never half a sum.
    assert mi.net_highs_headwind([(highs, nasdaq_lows), (highs, None)]) is None


def test_updown_headwind_is_the_reads_own_ratio_under_one():
    frame = pd.DataFrame({"Close": QQQ_CLOSES, "Volume": QQQ_VOLUMES},
                         index=pd.DatetimeIndex(QQQ_DATES, name="Date"))
    long = _walk(120, seed=5, with_volume=True)
    series = mi.updown_ratio_series(long)
    assert series.iloc[-1] == pytest.approx(mi.updown_read("X", long).ratio)
    # Every point is the 20-session read as of that day.
    assert series.iloc[-8] == pytest.approx(mi.updown_read("X", long.iloc[:-7]).ratio)
    h = mi.updown_headwind("QQQ", long)
    assert h.key == "qqq_updown" and h.on == (series.iloc[-1] < 1.0)
    assert h.display == f"{series.iloc[-1]:.2f}" and h.level == 1.0
    assert h.flip == f"Flips at 1.00 · needs {1.0 - series.iloc[-1]:+.2f}"
    assert 1 <= h.streak <= len(series)
    # A frame with only the 21 bars of one read has one ratio and no history to chart.
    assert mi.updown_headwind("QQQ", frame) is None


def test_credit_headwind_reads_the_emas_direction_and_names_the_turning_close():
    falling = mi.credit_headwind(_days([100 - 0.1 * i for i in range(60)]))
    assert falling.on and falling.display == "Falling" and falling.streak == 40
    ema = _days([100 - 0.1 * i for i in range(60)]).ewm(span=20, adjust=False).mean()
    assert falling.flip == f"Turns up on a close above {ema.iloc[-1]:.2f} (now 94.10)"
    assert falling.versus == "worse" and falling.path[2] is not None
    # Three closes back above the EMA turn it up: the price, not a threshold, decides.
    turned = mi.credit_headwind(_days([100 - 0.1 * i for i in range(57)] + [99, 99, 99]))
    assert not turned.on and turned.display == "Rising" and turned.streak == 3
    assert turned.flip.startswith("Turns down on a close below ")
    assert mi.credit_headwind(_days([100] * 10)) is None


def test_rotation_headwind_is_the_ratio_above_its_fifty_day_average():
    ratio = _days([0.10] * 60 + [0.12] * 5)
    h = mi.rotation_headwind(ratio)
    average = ratio.rolling(50).mean().iloc[-1]
    assert h.on and h.streak == 5
    assert h.display == f"{(0.12 / average - 1) * 100:+.1f}%"
    assert h.flip == f"Flips on a ratio below {average:.4f}"
    assert h.versus == "worse"                # a wider gap is worse, not better
    off = mi.rotation_headwind(_days([0.10] * 60 + [0.08] * 5))
    assert not off.on and off.flip.startswith("Flips on a ratio above ")
    assert mi.rotation_headwind(_days([0.1] * 30)) is None


def test_the_headline_counts_headwinds_and_fomo_is_not_one_of_them():
    snap = mi.build_snapshot(_bars(_universe()))
    on = sum(h.on for h in snap.headwinds)
    assert mi.headline(snap)[0] == f"{on} of 5 headwinds on"
    # FOMO, the advancing share and credit appetite cannot move the count.
    frames = _universe()
    frames[mi.FOMO_SYMBOL] = frames[mi.FOMO_SYMBOL] * 0 + 5.0       # deeply washed out
    frames[mi.ADVANCING_SYMBOL] = frames[mi.ADVANCING_SYMBOL] * 0 + 1.0
    assert mi.headline(mi.build_snapshot(_bars(frames))) == mi.headline(snap)
    assert "fomo" not in mi.HEADWIND_KEYS and len(mi.HEADWIND_KEYS) == 5


def test_the_headlines_sentence_follows_the_count():
    def snap_with(states):
        h = mi.build_snapshot(_bars(_universe())).headwinds[0]
        import dataclasses
        return types.SimpleNamespace(headwinds=tuple(dataclasses.replace(h, on=s) for s in states))
    assert mi.headline(snap_with([True] * 5)) == ("5 of 5 headwinds on", "Every headwind is on.")
    assert mi.headline(snap_with([False] * 5)) == ("0 of 5 headwinds on", "No headwind is on.")
    assert mi.headline(snap_with([True] * 3 + [False] * 2))[1] == "Most headwinds are on."
    assert mi.headline(snap_with([True] * 2 + [False] * 3))[1] == "Most headwinds are off."


def test_run_length_and_versus_are_what_the_cards_say():
    assert mi._run_length([False, True, True, True]) == 3
    assert mi._run_length([True, True, False]) == 1
    assert mi._versus(_days([1, 2, 3, 4, 5, 6]), higher_is_better=True) == "better"
    assert mi._versus(_days([1, 2, 3, 4, 5, 6]), higher_is_better=False) == "worse"
    assert mi._versus(_days([3, 2, 3, 4, 5, 3]), higher_is_better=True) is None
    assert mi._versus(_days([1, 2, 3]), higher_is_better=True) is None


# ── the history under the headwinds ───────────────────────────────────────────

def test_the_history_is_the_cards_own_states_on_the_sessions_all_five_share():
    frames = _universe(200)
    snap = mi.build_snapshot(_bars(frames))
    h = snap.history
    assert [key for key, _, _ in h.rows] == list(mi.HEADWIND_KEYS) and h.total == 5
    assert all(len(flags) == len(h.dates) == len(h.price) == len(h.count)
               for _, _, flags in h.rows)
    # The last session of every row is what that headwind's card says today.
    assert {key: flags[-1] for key, _, flags in h.rows} == {x.key: x.on for x in snap.headwinds}
    assert h.count[-1] == sum(x.on for x in snap.headwinds)
    assert h.count == tuple(sum(flags[i] for _, _, flags in h.rows)
                            for i in range(len(h.dates)))
    # It starts where the slowest headwind does: the 50-day average of the ratio.
    assert h.dates[0] == frames["QQQ"].index[mi.ROTATION_AVERAGE - 1].strftime("%Y-%m-%d")
    assert h.price_symbol == mi.HISTORY_PRICE_SYMBOL
    assert h.price[-1] == frames["QQQ"]["Close"].iloc[-1]


def test_no_history_unless_every_headwind_can_be_read():
    frames = _universe(200)
    del frames["NYSE_NL52W"]                    # half the net-highs sum
    snap = mi.build_snapshot(_bars(frames))
    assert len(snap.headwinds) == 4 and snap.history is None


def test_stretches_join_runs_that_are_close_and_count_only_all_on_sessions():
    count = [5, 5, 4, 5] + [3] * 30 + [5] + [2] * 5 + [5, 5]
    dates = tuple(d.strftime("%Y-%m-%d") for d in pd.bdate_range("2026-01-01", periods=len(count)))
    h = mi.HeadwindHistory(dates=dates, price=(1.0,) * len(count), price_symbol="QQQ",
                           rows=(), count=tuple(count), total=5)
    assert mi.all_on_stretches(h, gap=21) == [
        (dates[0], dates[3], 3),                # the one-session dip does not split it
        (dates[34], dates[41], 3),              # six sessions apart: one stretch
    ]
    assert len(mi.all_on_stretches(h, gap=1)) == 4
    none = mi.HeadwindHistory(dates=dates, price=(1.0,) * len(count), price_symbol="QQQ",
                              rows=(), count=(4,) * len(count), total=5)
    assert mi.all_on_stretches(none) == []


# ── context: volatility and futures positioning ───────────────────────────────

def test_volatility_reads_the_term_structure_and_ranks_the_vix_on_its_own_history():
    vix = _days([15.0] * 300 + [20.0, 30.0, 32.0])
    term = _days([18.0] * 300 + [22.0, 28.0, 29.0]).iloc[40:]      # a shorter history
    read = mi.volatility_read(vix, term, nasdaq=_days([25.0] * 303))
    assert read.value == 32.0 and read.change == 2.0 and read.term == 29.0
    assert read.ratio == pytest.approx(32 / 29) and read.inverted and read.streak == 2
    # Ranked against every VIX session, not only those VIX3M shares.
    assert read.rank == (100, "highest", vix.index[0].year)
    assert read.nasdaq == 25.0
    assert len(read.path[0]) == len(read.path[1]) == len(read.path[2]) == 252
    calm = mi.volatility_read(vix.iloc[:300], term.iloc[:260])
    assert not calm.inverted and calm.streak == 260 and calm.nasdaq is None
    assert mi.volatility_read(vix, None) is None


def test_volatility_is_context_absent_without_its_series_and_never_awaited():
    frames = _universe()
    assert mi.build_snapshot(_bars(frames)).volatility is None
    assert mi.VOLATILITY_SYMBOL not in mi.build_snapshot(_bars(frames)).awaiting
    idx = frames["QQQ"].index
    frames[mi.VOLATILITY_SYMBOL] = pd.DataFrame({"Close": 20.0}, index=idx)
    frames[mi.VOLATILITY_TERM_SYMBOL] = pd.DataFrame({"Close": 22.0}, index=idx)
    with_vol = mi.build_snapshot(_bars(frames))
    assert with_vol.volatility.value == 20.0 and not with_vol.volatility.inverted
    assert mi.headline(with_vol) == mi.headline(mi.build_snapshot(_bars(_universe())))


def test_positioning_reads_large_speculators_against_their_own_history():
    weeks = pd.date_range("2000-01-04", periods=200, freq="W-TUE")

    def get(market):
        if market == "Nasdaq":
            raise KeyError(market)
        return pd.DataFrame({mi.POSITIONING_COLUMN: [float(i % 50) for i in range(199)] + [49.0],
                             mi.POSITIONING_COMM_COLUMN: [-3.0] * 200}, index=weeks)
    reads = mi.positioning_reads(get)
    assert [r.label for r in reads] == ["S&P 500 futures"]         # the failed market is left out
    (r,) = reads
    assert r.value == 49.0 and r.commercials == -3.0
    assert r.rank == (100, "highest", 2000) and r.date == weeks[-1].strftime("%Y-%m-%d")
    assert mi.positioning_reads(lambda market: pd.DataFrame()) == ()
