"""Measure whether the sentiment page's pairs move together, and what NAAIM follows.

Answers the question behind the "Words against money" view in
`src/components/sentiment.py`: does NAAIM (active managers) move with any S&P 500 COT
group, does AAII move with non-reportables, and how much of each sentiment series is
recent price?

Levels of near-unit-root series correlate by construction (S&P 500 large-spec net has a
lag-1 autocorrelation of about 0.96), so levels are reported beside changes and the
changes are the read: cotmetrics/docs/positioning-series-properties.md §2. Changes are
reported overlapping and, for 4 weeks, non-overlapping, so the effective sample is
visible.

Licensed data: NAAIM and AAII history are read from the local marketdata store and
nothing here writes them anywhere. Prints only correlations.

Deterministic, no randomness. Usage (from the repo root, with the store env set as
run-local.sh sets it, COTMETRICS_PARAMS included):

    PYTHONPATH=src .venv/bin/python scripts/measure_sentiment_comovement.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import cotmetrics.constants as const  # noqa: E402
from cotmetrics.indexer import get_indexer  # noqa: E402

import components.sentiment as s  # noqa: E402

#: The average the removed pairing views were drawn on. Pinned here rather than read
#: from the page, which moved to two weeks afterwards, so the figures this script backs
#: (the component docstring's "No COT pairing" section) keep reproducing.
PAIRING_AVERAGE_WEEKS = 4
MARKET = "S&P 500"   # ES, full-size and micros folded in
GROUPS = {"comm": const.COMM_PCT_OI, "spec": const.LARGE_PCT_OI, "small": const.SMALL_PCT_OI}


def spearman(a, b):
    return a.rank().corr(b.rank())


def _r2(y, columns):
    """Share of y's variance an OLS fit on `columns` (plus a constant) explains."""
    x = np.column_stack([np.ones(len(y)), *columns])
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    # macOS Accelerate raises spurious divide/overflow flags in matmul on finite inputs;
    # the result is checked finite instead of trusting the flags.
    with np.errstate(all="ignore"):
        resid = y - x @ beta
    assert np.isfinite(resid).all()
    return 1 - resid.var() / y.var()


def gap_decomposition(weekly):
    """What the removed words-minus-money gap was made of, on each lookback: recent price
    (SPY's 13-week return, range-indexed on the same window), the money index alone, and
    both together. The gap is words index minus money index, as the panel drew it."""
    print("\nGap decomposition (words index minus money index), R^2")
    for years in s.LOOKBACK_YEARS:
        f = s.read(years).frame[["naaim", "aaii", "spy"]].copy()
        for words in ("naaim", "aaii"):
            avg = f[words].dropna().rolling(PAIRING_AVERAGE_WEEKS).mean().dropna()
            f[f"{words}_idx"] = s.range_index(avg, years).reindex(f.index)
        f = f.drop(columns=["naaim", "aaii"])
        for key in ("spec", "small"):
            f[f"{key}_idx"] = s.range_index(weekly[key], years).reindex(f.index)
        ret13 = f["spy"].pct_change(13).dropna()
        f["price_idx"] = s.range_index(ret13, years).reindex(f.index)
        f = f.dropna()
        for words, money in (("naaim", "spec"), ("aaii", "small")):
            gap = (f[f"{words}_idx"] - f[f"{money}_idx"]).to_numpy()
            price, cot = f["price_idx"].to_numpy(), f[f"{money}_idx"].to_numpy()
            print(f"  {years}Y {words}-{money} (n={len(f)}): price {_r2(gap, [price]):.2f}, "
                  f"money {_r2(gap, [cot]):.2f}, both {_r2(gap, [price, cot]):.2f}; "
                  f"gap~words {np.corrcoef(gap, f[f'{words}_idx'])[0, 1]:+.2f}, "
                  f"gap~-money {np.corrcoef(gap, -cot)[0, 1]:+.2f}")


def smoothing_table():
    """The component docstring's "Why two weeks" table: how much each display average
    (raw, 2, 4 weeks) quiets the 3-year index, and what it costs in lag."""
    print("\nDisplay smoothing on the 3-year index")
    f = s.read(s.DEFAULT_LOOKBACK).frame
    r13 = f["spy"].pct_change(13)
    for key in ("naaim", "aaii"):
        raw = f[key].dropna()
        for weeks in (1, 2, 4):
            avg = raw.rolling(weeks, min_periods=weeks).mean().dropna()
            idx = s.range_index(avg, s.DEFAULT_LOOKBACK).dropna()
            step = idx.diff().dropna()
            flips = (np.sign(step).diff().abs() == 2).mean() * 52
            print(f"  {key} {weeks}w: median weekly move {step.abs().median():4.1f}, "
                  f"direction changes {flips:4.1f}/yr, mean lag {(weeks - 1) / 2:.1f}w, "
                  f"level~SPY 13w return {avg.corr(r13.reindex(avg.index)):.2f}")


def main():
    df = get_indexer().get_symbols_data(MARKET, "52")
    weekly = {}
    for key, col in GROUPS.items():
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        series.index = pd.DatetimeIndex(series.index)
        weekly[key] = s.weekly(series.sort_index())
    frame = s.read(s.DEFAULT_LOOKBACK).frame[["naaim", "aaii", "spy"]]
    raw = frame.join(pd.DataFrame(weekly), how="inner").dropna()
    print(f"joint weeks {len(raw)}, {raw.index[0].date()} to {raw.index[-1].date()}")
    print(f"lag-1 autocorrelation: naaim {raw.naaim.autocorr():.3f}, "
          f"spec {raw.spec.autocorr():.3f}, comm {raw.comm.autocorr():.3f}")
    print(f"comm against spec: level {raw.comm.corr(raw.spec):.2f}, "
          f"4w change {raw.comm.diff(4).corr(raw.spec.diff(4)):.2f}")

    every4 = raw.iloc[::4]
    ret4 = raw.spy.pct_change(4)
    for words in ("naaim", "aaii"):
        w = raw[words]
        avg = w.rolling(PAIRING_AVERAGE_WEEKS).mean().dropna()
        print(f"\n{words.upper()} against")
        for g in GROUPS:
            x = raw[g]
            idx = {y: s.range_index(avg, y).corr(s.range_index(x, y)) for y in s.LOOKBACK_YEARS}
            print(f"  {g:5} level {spearman(w, x):+.2f} | change 1w {w.diff().corr(x.diff()):+.2f}"
                  f" 4w {w.diff(4).corr(x.diff(4)):+.2f}"
                  f" 4w non-overlapping {every4[words].diff().corr(every4[g].diff()):+.2f}"
                  f" (n={len(every4) - 1}) 13w {w.diff(13).corr(x.diff(13)):+.2f}"
                  f" | index 3Y {idx[3]:+.2f} 1Y {idx[1]:+.2f}")
        print(f"  4w change against SPY 4w return {w.diff(4).corr(ret4):+.2f}; level against "
              f"SPY trailing 13w return {w.corr(raw.spy.pct_change(13)):+.2f}")
    for g in GROUPS:
        print(f"{g:5} 4w change against SPY 4w return {raw[g].diff(4).corr(ret4):+.2f}")

    gap_decomposition(weekly)
    smoothing_table()

    print("\nNAAIM level against SPY return, by weeks the return ends BEFORE the NAAIM week")
    print("(negative = the return comes after; descriptive, not the pre-registered test)")
    ret13 = raw.spy.pct_change(13)
    for lag in (-8, -4, -2, 0, 1, 2, 4, 8, 13):
        print(f"  {lag:+3d}: 4w {raw.naaim.corr(ret4.shift(lag)):+.2f}"
              f"  13w {raw.naaim.corr(ret13.shift(lag)):+.2f}")


if __name__ == "__main__":
    main()
