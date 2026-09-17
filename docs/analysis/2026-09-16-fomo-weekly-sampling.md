# FOMO is not a weekly quantity: what a Tuesday sample keeps of the NCFD zone visits

Point-in-time measurement, 2026-09-16. Never amended. Companion to
[../design/tradingview-breadth-scoping.md](../design/tradingview-breadth-scoping.md), which
it decides one question for: whether the FOMO read can be drawn as a crowd-board tape-context
row (weekly, Tuesday close, range index) the way the four ETF ratios are.

## Data

`INDEX:NCFD` (percent of Nasdaq Composite constituents above their own 5-day average, the
series `agi/indicators/fomo.pine` reads), 300 daily bars ending 2026-09-16, pulled through
the TradingView connector's `get_ohlcv` (`symbol=INDEX:NCFD, count=300, interval=1D`) and
saved beside this note as
[2026-09-16-fomo-weekly-sampling.csv](2026-09-16-fomo-weekly-sampling.csv) (`t` is the
vendor's unix-second bar stamp, `c` the close). Session dates are the Eastern date of `t`.

Validation of the series against a published reading: the 2026-07-29 close is 48.05, and the
EDGE report of that date printed FOMO 48% (the same check `agi/import_fomo.py` documents for
the manual CSV export). The connector serves the same series the export does.

Reproducer: the script is the measurement block below, run from `cot-analyzer/.venv` with
pandas; no seed, nothing random.

```python
import pandas as pd
df = pd.read_csv("2026-09-16-fomo-weekly-sampling.csv")
df["date"] = (pd.to_datetime(df.t, unit="s", utc=True).dt.tz_convert("US/Eastern")
              .dt.normalize().dt.tz_localize(None))
s = df.set_index("date").c
weekly = s.resample("W-TUE").last().dropna()          # the board's cadence

def runs(mask):
    out, cur = [], None
    for d, m in mask.items():
        if m and cur is None: cur = [d, d]
        elif m: cur[1] = d
        elif cur: out.append(tuple(cur)); cur = None
    if cur: out.append(tuple(cur))
    return out

for name, mask in [("exhaustion >80", s > 80), ("fear <25", s < 25), ("fear <20", s < 20)]:
    ep = runs(mask)
    seen = sum(any(d.dayofweek == 1 for d in s.loc[a:b].index) for a, b in ep)
    print(name, "days", int(mask.sum()), "episodes", len(ep),
          "Tuesday closes in zone", int((mask & (s.index.dayofweek == 1)).sum()),
          "episodes with a Tuesday", f"{seen}/{len(ep)}")
print(s.diff().abs().median(), s.diff().abs().quantile(.9), s.autocorr(1), s.autocorr(5))
```

## Result

Span 2025-07-09 to 2026-09-16, 300 sessions, 63 Tuesday observations. Zones are the June
2026 Swing Trading Guide cutoffs recorded in `agi/docs/02-RULES.md` M-07 (exhaustion above
80, fear below 20 to 25).

| zone | session days in zone | episodes | median episode length | Tuesday closes in zone | episodes a Tuesday sample sees |
|---|---|---|---|---|---|
| exhaustion, > 80 | 8 | 5 | 1 day | 1 | 1 of 5 |
| fear, < 25 | 17 | 13 | 1 day | 3 | 3 of 13 |
| fear, < 20 | 8 | 8 | 1 day | 1 | 1 of 8 |

Day-to-day behaviour: median absolute daily change 8.6 points, 90th percentile 22.6 points;
lag-1 autocorrelation 0.60, lag-5 autocorrelation -0.02. A five-day share of stocks above a
five-day average has, by construction, about a week of memory, and the numbers say exactly
that.

## What it means

- **A weekly sample destroys the read.** The zone visits FOMO exists to flag last one session
  as a rule and a Tuesday close catches a fifth to a quarter of them. A tape-context row on
  the board's weekly windows would print a 12-month range index of a series whose extremes
  it almost never observes, and the index would be ordinary on precisely the days the
  indicator was extreme.
- **The range index is the wrong frame as well as the wrong cadence.** FOMO's zones are
  absolute, vendor-calibrated levels on a 0 to 100 scale. Re-normalising them against a
  trailing window replaces the published cutoffs with ones the window happens to produce.
- **Net new highs and lows are the same shape**, a daily count with a three-consecutive-day
  regime rule (`agi/indicators/nasdaq_net_highs.pine`), and inherit the same conclusion
  without a separate measurement: a Tuesday sample cannot see three consecutive days.
- **The slower breadth series are fine on the board's frame.** Share above the 200-day
  average and a smoothed put/call ratio move over weeks; a weekly range index on them
  reads as intended. The scoping doc sorts the candidates on this line.

Bottom line, in words: this is not a marginal result. FOMO drawn weekly would be wrong most
of the time it mattered, so it needs its own daily, zone-labelled rendering rather than a
fifth tape-context row.
