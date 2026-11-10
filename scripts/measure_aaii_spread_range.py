"""Measure the range of AAII's bulls minus bears, for the votes card's fixed scale.

Answers the question behind `aaii_votes.SPREAD_LIMIT`: how wide must the spread block's
axis be for a bar's length to mean the same thing every week without wasting most of
the width on weeks that almost never happen? Prints the extremes with their dates, the
mean, tail quantiles, and the share of weeks beyond a few candidate limits.

Official weeks only (`aaii_votes.legs()`), every stored week weighted equally.

Licensed data: AAII history is read from the local marketdata store and nothing here
writes it anywhere. Prints only summary figures.

Deterministic, no randomness. Usage (from the repo root, with the store env set as
run-local.sh sets it):

    PYTHONPATH=src .venv/bin/python scripts/measure_aaii_spread_range.py
"""

from __future__ import annotations

from components import aaii_votes as av

LIMITS = (40, 50, 60)


def main():
    legs = av.legs()
    if legs is None:
        raise SystemExit("measure-aaii-spread: AAII is not in the store")
    sp = legs["bullish"] - legs["bearish"]
    print(f"weeks {len(sp)}, {sp.index[0]:%Y-%m-%d} to {sp.index[-1]:%Y-%m-%d}")
    print(f"min {sp.min():.1f} ({sp.idxmin():%Y-%m-%d}), max {sp.max():.1f} "
          f"({sp.idxmax():%Y-%m-%d}), mean {sp.mean():+.1f}")
    for q in (0.01, 0.05, 0.95, 0.99):
        print(f"quantile {q:.2f}: {sp.quantile(q):+.1f}")
    for lim in LIMITS:
        print(f"beyond +-{lim}: {(sp.abs() > lim).mean():.2%}")


if __name__ == "__main__":
    main()
