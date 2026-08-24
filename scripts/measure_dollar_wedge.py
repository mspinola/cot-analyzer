"""Measure what the dollar lens adds to the Crowding Strip's positioning index.

The strip draws one 0-100 range index per market: where this market's Commercial net
position sits inside its own tuned lookback window, in CONTRACTS (Raw PF) or as a SHARE
OF OPEN INTEREST (NPF). The printed positioning reports this page was modelled on draw
the same position a second time in US DOLLARS, and the question this script answers is
whether that second reading is a different series or the same one wearing bigger
numbers.

It holds everything constant except the unit. Same market, same leg, same window, same
statistic (`indicators.calculate_range_index`), computed on four series:

  raw       net contracts, which is what the Raw PF index reads
  norm      net contracts over open interest, which is what the NPF index reads
  notional  contracts x point value x price, the middle rung of cotmetrics.exposure
  risk      notional x daily volatility, the rung that is comparable across markets

Four things are reported, and the last two are the ones that decide whether a mark is
worth drawing rather than merely computable:

  1. how far the two readings part (correlation, and the 95th percentile of |gap|)
  2. how often they disagree about the market being through the MODEL's own gate band,
     which is the only difference between two lenses that changes an answer here
  3. whether the gap is a state or a jitter (lag-1 autocorrelation)
  4. whether the gap is just "volatility is high", tested against a range index of the
     market's own daily volatility over the same window

It also checks the one identity that decides where the dollar lens can be drawn at all:
a position's SHARE of open interest is the same number in contracts and in dollars,
because the point value, the price and the volatility all cancel between numerator and
denominator. If that holds to floating point, there is no dollar version of the NPF
basis to draw, and the dollar reading is necessarily a level reading.

Deterministic: nothing here is sampled, so a rerun against the same store reproduces
every figure exactly.

Usage (from the repo root, with the store env set as run-local.sh sets it):

    .venv/bin/python scripts/measure_dollar_wedge.py --out docs/analysis/<name>.json
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import pandas as pd
from cotmetrics import exposure, indicators, models
from cotmetrics.indexer import get_indexer

#: A gap this wide is worth reporting as a headline count. Display threshold, not a
#: statistic: it is roughly the pooled 95th percentile, so "a fifth of the axis" and
#: "unusual" happen to name the same rows.
WIDE_GAP = 20

#: Under this many weeks of overlap a per-market correlation is not worth quoting.
MIN_WEEKS = 104


def market_panel(name, lookback):
    """One market's four readings on one index, plus the volatility index behind them.

    Returns `(frame, weeks)` or `(None, reason)`. The window is the market's own tuned
    lookback under "Custom", which is what the page draws, so the dollar reading is
    measured over exactly the window the contract reading was.
    """
    indexer = get_indexer()
    instrument = indexer.get_instrument_from_name(name)
    if instrument is None:
        return None, "no instrument"
    if lookback in ("26", "52"):
        window = int(lookback)
    else:
        window = int(instrument.custom_lookback)

    weekly = indexer.get_symbols_data(name, lookback)
    if weekly.empty:
        return None, "no weekly frame"
    try:
        ex = exposure.market_exposure(name, leg=exposure.LEG_COMM, lookback=lookback,
                                      frame=weekly, symbol=instrument.symbol)
    except Exception as e:  # noqa: BLE001 - one unpriceable market is not a failure
        return None, f"{type(e).__name__}: {e}"
    if not ex["risk_usd"].notna().any():
        return None, "no contract multiplier or no bars"

    prefix = f"Comm {lookback} " if lookback in ("26", "52") else "Comm Custom "
    panel = pd.DataFrame({
        "raw": pd.to_numeric(weekly[prefix + "Idx"], errors="coerce").to_numpy(),
        "norm": pd.to_numeric(weekly[prefix + "Idx Norm"], errors="coerce").to_numpy(),
        "notional": indicators.calculate_range_index(ex["notional_usd"], window).to_numpy(),
        "risk": indicators.calculate_range_index(ex["risk_usd"], window).to_numpy(),
        "vol": indicators.calculate_range_index(ex["sigma_daily"], window).to_numpy(),
    }, index=pd.to_datetime(weekly.index))
    panel["risk_usd"] = ex["risk_usd"].to_numpy()
    panel["sigma_daily"] = ex["sigma_daily"].to_numpy()
    panel["net_contracts"] = ex["net_contracts"].to_numpy()
    return panel, window


def band(values, low, high):
    """Which of the model's three bands each reading sits in: -1, 0 or +1.

    Three, not two. A boolean "is it through a gate" calls the sharpest disagreement on
    the board a match, because a market at 0 on one lens and 96 on the other is at an
    extreme under both.
    """
    return np.where(values >= high, 1, np.where(values <= low, -1, 0))


def compare(panels, base, other, low, high):
    """Pooled per-market statistics for one pair of lenses at one model's bands."""
    rows = []
    for name, panel in panels.items():
        d = panel[[base, other, "vol"]].dropna()
        if len(d) < MIN_WEEKS:
            continue
        gap = d[base] - d[other]
        rows.append({
            "market": name,
            "weeks": int(len(d)),
            "corr": float(d[base].corr(d[other])),
            "gap_p95": float(np.percentile(gap.abs(), 95)),
            "band_disagree": float((band(d[base], low, high)
                                    != band(d[other], low, high)).mean()),
            "gap_autocorr": float(gap.autocorr(1)),
            "gap_vs_vol": float(gap.corr(d["vol"])),
        })
    frame = pd.DataFrame(rows)
    summary = {
        "markets": int(len(frame)),
        "bands": [low, high],
    }
    for column in ("corr", "gap_p95", "band_disagree", "gap_autocorr", "gap_vs_vol"):
        summary[column] = {
            "median": float(frame[column].median()),
            "p10": float(frame[column].quantile(0.10)),
            "p90": float(frame[column].quantile(0.90)),
        }
    summary["gap_vs_vol_positive"] = int((frame["gap_vs_vol"] > 0).sum())
    summary["gap_vs_vol_negative"] = int((frame["gap_vs_vol"] < 0).sum())
    return summary, frame


def latest_week(panels, base, other, low, high):
    """What the board would show on the newest week each market has."""
    rows = []
    for name, panel in panels.items():
        d = panel[[base, other]].dropna()
        if d.empty:
            continue
        last = d.iloc[-1]
        rows.append({
            "market": name,
            "date": str(d.index[-1].date()),
            base: float(last[base]),
            other: float(last[other]),
            "gap": float(abs(last[base] - last[other])),
            "disagrees": bool(band(np.array([last[base]]), low, high)[0]
                              != band(np.array([last[other]]), low, high)[0]),
        })
    frame = pd.DataFrame(rows).sort_values("gap", ascending=False)
    return {
        "markets": int(len(frame)),
        "disagree": int(frame["disagrees"].sum()),
        "wide_gaps": int((frame["gap"] >= WIDE_GAP).sum()),
        "widest": frame.head(10).to_dict("records"),
    }, frame


def oi_share_identity(names):
    """The share of open interest is the same number in contracts and in dollars.

    Point value, price and volatility all cancel between a position and the market it
    sits in, so this is algebra rather than an empirical result; it is measured because
    it is the reason the dollar lens has no OI-normalised form to draw.
    """
    worst, checked = 0.0, 0
    indexer = get_indexer()
    for name in names:
        instrument = indexer.get_instrument_from_name(name)
        weekly = indexer.get_symbols_data(name, "Custom")
        try:
            ex = exposure.market_exposure(name, leg=exposure.LEG_COMM,
                                          lookback="Custom", frame=weekly,
                                          symbol=instrument.symbol)
        except Exception:  # noqa: BLE001
            continue
        if "oi_risk_usd" not in ex:
            continue
        oi = pd.to_numeric(weekly["Open_Interest_All"], errors="coerce").to_numpy()
        in_contracts = ex["net_contracts"].to_numpy() / np.where(oi > 0, oi, np.nan)
        in_dollars = (ex["risk_usd"] / ex["oi_risk_usd"]).to_numpy()
        difference = np.nanmax(np.abs(in_contracts - in_dollars))
        if difference == difference:
            worst = max(worst, float(difference))
            checked += 1
    return {"markets": checked, "max_abs_difference": worst}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lookback", default="Custom",
                        choices=("26", "52", "Custom"),
                        help="the index window, as the page's control names it")
    parser.add_argument("--out", help="write the full result to this JSON path")
    args = parser.parse_args(argv)

    indexer = get_indexer()
    names = [indexer.get_instrument_from_symbol(s).name
             for s in indexer.get_instrument_names()]

    panels, unpriced, windows = {}, {}, {}
    for name in names:
        panel, detail = market_panel(name, args.lookback)
        if panel is None:
            unpriced[name] = detail
        else:
            panels[name] = panel
            windows[name] = detail

    result = {
        "lookback": args.lookback,
        "universe": len(names),
        "priced": len(panels),
        "unpriced": unpriced,
        "windows": windows,
        "oi_share_identity": oi_share_identity(names),
        "pairs": {},
        "latest": {},
    }
    for label, base, model in (("raw_vs_risk", "raw", models.RAW_PF),
                               ("raw_vs_notional", "raw", models.RAW_PF),
                               ("norm_vs_risk", "norm", models.NPF)):
        other = "notional" if label.endswith("notional") else "risk"
        summary, _ = compare(panels, base, other, model.low, model.high)
        summary["model"] = model.key
        result["pairs"][label] = summary
        latest, _ = latest_week(panels, base, other, model.low, model.high)
        result["latest"][label] = latest

    print(json.dumps(result, indent=2, default=str))
    if args.out:
        with open(args.out, "w") as fh:
            json.dump(result, fh, indent=2, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
