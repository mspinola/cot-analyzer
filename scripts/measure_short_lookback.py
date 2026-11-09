"""Measure how the sentiment range index behaves as its window shortens.

Answers the question behind "The real-time reading" in `src/components/sentiment.py`:
would a short index window (13 or 26 weeks), gently smoothed, make a good recent view
beside the 1- and 3-year windows the page offers?

For NAAIM and AAII bulls minus bears, on the 2-week average the page draws, and from
2008 on, per window:

- pinned: the share of weeks at or below 5 or at or above 95, where the index says
  "as extreme as it gets" and stops telling weeks apart;
- move: the mean absolute week-to-week change, in index points;
- c_r4, c_r13: correlation with SPY's trailing 4- and 13-week total return.

A last row per series is the raw week's percentile in its trailing three years, an
alternative short-horizon reading. Then how often a raw week falls outside its
average's trailing range (the dots `on_index_scale` pins to the panel's edge), and the
last six weeks on every window, so what a short window would say today is visible.

Licensed data: NAAIM and AAII history are read from the local marketdata store and
nothing here writes them anywhere. Prints only summary figures and index values.

Deterministic, no randomness. Usage (from the repo root, with the store env set as
run-local.sh sets it):

    PYTHONPATH=src .venv/bin/python scripts/measure_short_lookback.py
"""

from __future__ import annotations

import os

import pandas as pd

os.environ.setdefault("COT_SKIP_BOOT_FETCH", "1")

from components import sentiment as s  # noqa: E402  (after the env default)

WINDOWS = (13, 26, 52, 156)
START = "2008-01-01"


def _row(key, label, values, r4, r13):
    j = pd.concat([values.rename("i"), r4.rename("r4"), r13.rename("r13")], axis=1).dropna()
    return dict(series=key, window=label, n=len(values),
                pinned=((values <= 5) | (values >= 95)).mean(),
                move=values.diff().abs().mean(),
                c_r4=j.i.corr(j.r4), c_r13=j.i.corr(j.r13))


def main():
    # No COT row is needed: an empty commercials series is named as awaiting, not raised.
    read = s.build_read(get_positioning=lambda: pd.Series(dtype=float))
    f = read.frame
    print("newest stored:", {k: f"{v:%Y-%m-%d}" for k, v in read.last.items()})
    r4, r13 = f["spy"].pct_change(4), f["spy"].pct_change(13)
    rows = []
    for key in ("naaim", "aaii"):
        raw = f[key].dropna()
        avg = raw.rolling(s.AVERAGE_WEEKS, min_periods=s.AVERAGE_WEEKS).mean()
        for w in WINDOWS:
            idx = s.indicators.calculate_range_index(avg, window=w + 1).dropna()
            rows.append(_row(key, f"{w} weeks", idx[idx.index >= START], r4, r13))
        pct = raw.rolling(157, min_periods=157).apply(
            lambda x: (x <= x[-1]).mean() * 100, raw=True).dropna()
        rows.append(_row(key, "raw percentile, 3y", pct[pct.index >= START], r4, r13))
    pd.set_option("display.width", 140)
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    # The raw dots' placement (sentiment.on_index_scale): how often a week as read falls
    # outside its average's trailing range, and so is pinned to the panel's edge.
    print("\nraw weeks outside the line's 0-100 (pinned to the edge), 2008 on")
    for years in s.LOOKBACK_YEARS:
        w = s.index_window(years)
        for key in ("naaim", "aaii"):
            raw = f[key].dropna()
            avg = raw.rolling(s.AVERAGE_WEEKS, min_periods=s.AVERAGE_WEEKS).mean()
            lo = avg.rolling(w, min_periods=w).min()
            hi = avg.rolling(w, min_periods=w).max()
            on = (100 * (raw - lo) / (hi - lo)).dropna()
            on = on[on.index >= START]
            print(f"  {years}y {key}: {((on < 0) | (on > 100)).mean():.1%}")
    for key in ("naaim", "aaii"):
        raw = f[key].dropna()
        avg = raw.rolling(s.AVERAGE_WEEKS, min_periods=s.AVERAGE_WEEKS).mean()
        t = pd.DataFrame({f"w{w}": s.indicators.calculate_range_index(avg, window=w + 1)
                          for w in WINDOWS})
        t["as read"] = raw
        print(f"\n{key}, last six weeks")
        print(t.tail(6).round(1).to_string())


if __name__ == "__main__":
    main()
