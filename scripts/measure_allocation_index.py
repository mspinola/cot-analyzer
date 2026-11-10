"""Measure whether AAII's allocation shares suit NAAIM's range index.

Answers the question behind "Against a trailing average" in
`src/components/aaii_allocation.py`: should the stocks, bonds and cash shares be drawn
on the 0-100 range index the sentiment page uses for NAAIM, or as each share minus its
trailing average in points?

Per window (1, 3 and 5 years of months, plus the current month, the page's convention):

- pinned: the share of months, 2008 on, at exactly 0 or 100 (the page's NAAIM note
  measures 2% at three years on the weekly 2-week average);
- zone: the share of months at or below 20 or at or above 80;
- move: the mean absolute month-to-month change, index points;
- corr between the three indexes, and each one's correlation with SPY's trailing
  12-month return (NAAIM's level against SPY's 13-week return is 0.62).

Then each share's range over the last 37 months, its gap from the mean of the prior 36
months now, and the standard deviation of that gap over the whole history, so a gap
can be read against what is usual for that share.

Licensed data: the AAII allocation history is read from the local marketdata store and
nothing here writes it anywhere. Prints only summary figures.

Deterministic, no randomness. Usage (from the repo root, with the store env set as
run-local.sh sets it):

    PYTHONPATH=src .venv/bin/python scripts/measure_allocation_index.py
"""

from __future__ import annotations

import os

import pandas as pd

os.environ.setdefault("COT_SKIP_BOOT_FETCH", "1")

from cotmetrics import indicators  # noqa: E402  (after the env default)

from components import aaii_allocation as aa  # noqa: E402
from components import sentiment as s  # noqa: E402

YEARS = (1, 3, 5)
START = "2008-01-01"


def main():
    months = aa.legs()
    if months is None:
        raise SystemExit("AAII_ALLOC_* is not in the store (MARKETDATA_STORE)")
    spy = s._close(s._get_bars, s.PRICE, s.PRICE_TIER)
    spy_m = spy.resample("ME").last().reindex(months.index)
    ret12 = spy_m.pct_change(12)
    print(f"{len(months)} months, {months.index[0]:%Y-%m} to {months.index[-1]:%Y-%m}")
    for years in YEARS:
        window = 12 * years + 1
        idx = pd.DataFrame({k: indicators.calculate_range_index(months[k], window=window)
                            for k in months}).dropna()
        recent = idx[idx.index >= START]
        print(f"\n{years}Y range index ({window} months), {START[:4]} on, n={len(recent)}")
        print("  pinned 0/100:", (((recent == 0) | (recent == 100)).mean() * 100).round(0).to_dict())
        print("  zone <=20/>=80:", (((recent <= 20) | (recent >= 80)).mean() * 100).round(0).to_dict())
        print("  mean monthly move:", recent.diff().abs().mean().round(1).to_dict())
        print("  corr with SPY 12m return:", idx.corrwith(ret12.reindex(idx.index)).round(2).to_dict())
        print("  latest:", idx.iloc[-1].round(0).to_dict())
        print("  corr between indexes:")
        print(idx.corr().round(2).to_string().replace("\n", "\n    "))
    last = months.iloc[-(aa.GAP_MONTHS + 1):]
    print(f"\nrange over the last {aa.GAP_MONTHS + 1} months:",
          {k: (round(float(last[k].min()), 1), round(float(last[k].max()), 1))
           for k in months})
    gap = aa.trailing_gap(months)
    print(f"gap from the prior {aa.GAP_MONTHS}-month mean, {months.index[-1]:%Y-%m}:",
          gap.iloc[-1].round(1).to_dict())
    print("gap standard deviation, whole history:", gap.std().round(1).to_dict())


if __name__ == "__main__":
    main()
