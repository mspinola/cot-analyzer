"""Does anything on the screener card tell a setup card what its own strip does not?

The Home page setups tier draws positioning and nothing else: a market name, the three
leg indices, and a lollipop strip showing where each leg sits inside its band. Every
other reading the app holds about that market lives on the screener card below it or a
click away on OI Alignment. The obvious way to close that gap is to lift the screener's
readings onto the setups cards, and this script exists to ask whether they would SAY
anything if you did.

The test is direction, not value. A reading that always points the same way as the
positioning that put a row on the page is a restatement of the strip beside it, however
independently it is computed. So for every market-week at or approaching a gate, each
reading is reduced to bull / bear / flat on the app's own thresholds and compared with
the side the Commercial index is on:

  tape bias   cotmetrics.synthesis.generate_exhaustive_tape_synthesis
  willco      WILLCO_ALIAS against WILLCO_MIN/MAX_THRESHOLD
  lw          LW_LRG_SENTIMENT against its thresholds, INVERTED (it is contrarian)
  move        COMM_MOMENTUM against MOMENTUM_MIN/MAX_THRESHOLD
  trend       the bullish_trend_continuing / bearish_trend_continuing flags

`flat` is counted separately from `conflict` on purpose: a reading that is usually
silent is not redundant, it is absent, and those are different reasons not to draw
something.

The counterweight is setup AGE, the one candidate reading that positioning cannot
imply: a market can sit at its gate for one week or for ten and the strip looks
identical either way. It is measured two ways, the current board's spread and the
longest run either model has ever produced, the second of which also fixes the walk cap
in cotmetrics.

Both models are measured independently. They are not nested -- a market can be an NPF
setup while its CLS legs are only close -- so a result on one is not a result on the
other.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import cotmetrics.constants as const  # noqa: E402
import cotmetrics.models as models  # noqa: E402
import pandas as pd  # noqa: E402
from cotmetrics.indexer import get_indexer  # noqa: E402
from cotmetrics.synthesis import generate_exhaustive_tape_synthesis  # noqa: E402

BULL, BEAR, FLAT = "bull", "bear", "flat"
READINGS = ("tape", "willco", "lw", "move", "trend")


def _dir(value, bull_at, bear_at, invert=False):
    """A reading reduced to the side it points, on the app's own thresholds."""
    if value is None or pd.isna(value):
        return FLAT
    if invert:
        return BULL if value <= bear_at else BEAR if value >= bull_at else FLAT
    return BULL if value >= bull_at else BEAR if value <= bear_at else FLAT


def directions(row, frame, symbol):
    tape = generate_exhaustive_tape_synthesis(
        row, symbol, df=frame).get("tape_bias", "").lower()
    up = bool(row.get("bullish_trend_continuing", False))
    down = bool(row.get("bearish_trend_continuing", False))
    return {
        "tape": BULL if tape == "bullish" else BEAR if tape == "bearish" else FLAT,
        "willco": _dir(row.get(const.WILLCO_ALIAS), const.WILLCO_MAX_THRESHOLD,
                       const.WILLCO_MIN_THRESHOLD),
        # Contrarian: a LOW Large Spec sentiment is the bullish reading.
        "lw": _dir(row.get(const.LW_LRG_SENTIMENT),
                   const.LW_LRG_SENTIMENT_MAX_THRESHOLD,
                   const.LW_LRG_SENTIMENT_MIN_THRESHOLD, invert=True),
        "move": _dir(row.get(const.COMM_MOMENTUM), const.MOMENTUM_MAX_THRESHOLD,
                     const.MOMENTUM_MIN_THRESHOLD),
        "trend": BULL if up and not down else BEAR if down and not up else FLAT,
    }


def measure(model, weeks, lookback="Custom"):
    comm_col, _, _ = model.leg_columns(lookback)
    tally = {k: {"agree": 0, "conflict": 0, "flat": 0} for k in READINGS}
    conflicts, gate_rows, ages, longest = [], 0, {}, {}

    for asset_class in get_indexer().get_asset_classes():
        for asset in get_indexer().get_assets_for_asset_class(asset_class):
            frame = get_indexer().get_symbols_data(asset, lookback, model.basis)
            if frame is None or frame.empty:
                continue
            is_equity = get_indexer().is_equity(asset)
            symbol = get_indexer().get_instrument_symbol_from_name(asset)

            states = [model.setup_state_from(frame.iloc[i], lookback, is_equity)
                      for i in range(len(frame))]

            # Longest run of consecutive gate weeks, ever. This is what the walk cap in
            # PositioningModel.setup_age_from is set against.
            run = best = 0
            for state in states:
                run = 0 if state == const.SETUP_NONE else run + 1
                best = max(best, run)
            longest[asset] = best

            if states[-1] != const.SETUP_NONE:
                ages[asset] = {
                    "state": states[-1],
                    "weeks": model.setup_age_from(frame, lookback, is_equity),
                }

            for i in range(max(0, len(frame) - weeks), len(frame)):
                if states[i] == const.SETUP_NONE:
                    continue
                index = frame.iloc[i].get(comm_col)
                if index is None or pd.isna(index):
                    continue
                gate_rows += 1
                side = BULL if index >= 50 else BEAR
                for key, pointing in directions(
                        frame.iloc[i], frame.iloc[:i + 1], symbol).items():
                    bucket = ("flat" if pointing == FLAT
                              else "agree" if pointing == side else "conflict")
                    tally[key][bucket] += 1
                    if bucket == "conflict":
                        conflicts.append({"asset": asset, "reading": key,
                                          "date": str(frame.index[i].date())})

    return {
        "model": model.title,
        "gate_market_weeks": gate_rows,
        "readings": tally,
        "conflicts": conflicts,
        "age_today": dict(sorted(ages.items(), key=lambda kv: -kv[1]["weeks"])),
        "longest_run_ever": dict(sorted(longest.items(), key=lambda kv: -kv[1])[:10]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weeks", type=int, default=52,
                        help="how many weeks back to sweep (default 52)")
    parser.add_argument("--lookback", default="Custom")
    parser.add_argument("--out", type=Path, help="write the full result as JSON")
    args = parser.parse_args()

    dates = get_indexer().get_available_dates()
    result = {
        "weeks": args.weeks,
        "lookback": args.lookback,
        "newest_data": dates[0] if dates else None,
        "asset_classes": len(list(get_indexer().get_asset_classes())),
        "markets": sum(len(get_indexer().get_assets_for_asset_class(ac))
                       for ac in get_indexer().get_asset_classes()),
        "models": [measure(m, args.weeks, args.lookback) for m in models.MODELS],
    }

    for one in result["models"]:
        print(f"\n### {one['model']}: {one['gate_market_weeks']} market-weeks at or "
              f"near a gate, last {args.weeks} weeks")
        print(f"{'reading':<10}{'agrees':>9}{'conflicts':>11}{'flat':>8}{'conflict':>11}")
        for key in READINGS:
            counts = one["readings"][key]
            total = sum(counts.values()) or 1
            print(f"{key:<10}{counts['agree']:>9}{counts['conflict']:>11}"
                  f"{counts['flat']:>8}{100 * counts['conflict'] / total:>10.1f}%")
        ages = one["age_today"]
        print("  age today: " + ", ".join(
            f"{a} {v['weeks']}w" for a, v in list(ages.items())[:6]) or "  none")
        print(f"  longest run ever: {list(one['longest_run_ever'].items())[:3]}")

    if args.out:
        args.out.write_text(json.dumps(result, indent=2))
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
