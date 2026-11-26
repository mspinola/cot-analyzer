"""Reproduce the figures in `components.aaii_say_do`'s docstring: how closely AAII's
monthly bullish vote and its stocks share move together, and how often their trailing
three-year percentiles sit far apart. Reads the store through the card's own `read()`,
so it measures exactly what the card draws. No forward returns are computed.

    MARKETDATA_STORE=~/code/marketdata_store COTDATA_STORE=~/code/cotdata_store \\
        PYTHONPATH=src .venv/bin/python scripts/measure_say_do.py

Measured 2026-11-26: 468 months (1987-11 to 2026-10), level correlation 0.34, 3-month
change correlation 0.37; 432 ranked months, 19.4% at |gap| >= 50 (15.3% negative,
4.2% positive).
"""
import sys

from components import aaii_say_do as sd


def main():
    x = sd.read()
    if x is None:
        print("measure-say-do: AAII votes or allocation not in the store", file=sys.stderr)
        return 1
    m = x.months
    pair = m[["bullish", "stocks"]]
    print(f"months {len(m)} ({m.index[0]:%Y-%m} to {m.index[-1]:%Y-%m})")
    print(f"level correlation {pair.corr().iloc[0, 1]:.2f}")
    print(f"3-month change correlation {pair.diff(3).corr().iloc[0, 1]:.2f}")
    g = m["gap"].dropna()
    far = sd.FAR_APART
    print(f"ranked months {len(g)}: |gap| >= {far} {(g.abs() >= far).mean():.1%} "
          f"(gap <= -{far} {(g <= -far).mean():.1%}, gap >= {far} {(g >= far).mean():.1%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
