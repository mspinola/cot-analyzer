"""Measure the null distribution of the price-against-positioning Spearman columns.

Answers the open check in cotmetrics/docs/positioning-series-properties.md §3: the
`* Spearman` columns correlate PRICE LEVELS against POSITIONING LEVELS over a short
rolling window, which is the same statistical structure §2 measured as spurious for
positioning-against-positioning, and its noise band has never been measured here.

Three nulls, because the one §3 prescribes (a synthetic independent series) fixes the
band to an arbitrary choice of drift and volatility, and the real question is what the
statistic does on THIS data:

  synthetic  a Gaussian random walk in place of price. §3's literal prescription.
  offset     real price windows against real positioning windows of the SAME market
             taken from a different, non-overlapping stretch of time. Preserves both
             series' autocorrelation and marginal shape exactly, destroys only the
             alignment. This is the strongest of the three.
  cross      real price of market A against real positioning of market B, A and B in
             different asset classes, aligned on report date.

The offset null rotates the WINDOW INDEX rather than the underlying series, so every
pair is a genuine contiguous window of real data and no wrap-around seam is introduced.
Offsets are constrained to >= W so the two windows never share a week.

Reported against the same three nulls on FIRST DIFFERENCES, which is the form §2's rule
says to use, so the two can be compared on equal footing.

Deterministic: every random draw comes from a seeded Generator. Rerunning reproduces.

Usage (from the repo root, with the store env set as run-local.sh sets it):

    .venv/bin/python scripts/measure_spearman_null.py --out docs/analysis/<name>.json
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np
import pandas as pd
from cotmetrics.CotIndexer import CotIndexer

DATE = "Report_Date_as_MM_DD_YYYY"
PRICE = "Closing Price"

# The six columns CotIndexer emits per lookback: commercial / large / small, raw and
# OI-normalised. These are the SOURCE series; the script recomputes the rolling
# correlation itself so it can run the same code path over the nulls.
POS_COLS = {
    "comm": "Comm Net Pos",
    "large": "Lrg Spec Net Pos",
    "small": "Sml Spec Net Pos",
    "comm_norm": "Comm Net Pos Norm",
    "large_norm": "Lrg Spec Net Pos Norm",
    "small_norm": "Sml Spec Net Pos Norm",
}

# 13 is the window signals.py::_append_spearman_regime_shift_signal reads; 26 and 52 are
# the configured lookbacks; 104 extends the sweep past them because §3 predicts the band
# WIDENS with window length and that ordering is the thing to check.
WINDOWS = (13, 26, 52, 104)

N_OFFSETS = 25          # offset-null draws per market/column/window
N_CROSS_PAIRS = 240     # cross-market pairs sampled across asset classes
N_SYNTH = 8             # synthetic price paths per market
SEED = 20260807


# ----------------------------------------------------------------------------------
# ranking
# ----------------------------------------------------------------------------------

def avg_rank_2d(A: np.ndarray) -> np.ndarray:
    """Average ("fractional") ranks along axis 1, matching pandas' default tie handling.

    Net positions are integers and do tie; ordinal ranking would quietly bias the
    statistic on low-turnover markets, so ties are averaged properly.
    """
    m, w = A.shape
    order = np.argsort(A, axis=1, kind="mergesort")
    S = np.take_along_axis(A, order, axis=1)

    pos = np.arange(w, dtype=float)
    starts_run = np.ones((m, w), dtype=bool)
    starts_run[:, 1:] = S[:, 1:] != S[:, :-1]
    ends_run = np.ones((m, w), dtype=bool)
    ends_run[:, :-1] = S[:, 1:] != S[:, :-1]

    first = np.maximum.accumulate(np.where(starts_run, pos, 0.0), axis=1)
    last = np.minimum.accumulate(
        np.where(ends_run, pos, float(w - 1))[:, ::-1], axis=1
    )[:, ::-1]

    avg_sorted = (first + last) / 2.0 + 1.0
    ranks = np.empty_like(avg_sorted)
    np.put_along_axis(ranks, order, avg_sorted, axis=1)
    return ranks


def rank_windows(x: np.ndarray, w: int) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Rolling windows of `x`, rank-transformed, centred and L2-normalised.

    Returns (R, complete_mask, nondegenerate_mask). Rows of R dot together directly
    into a Spearman rho, which is what makes the offset and cross nulls cheap enough to
    draw densely. The two masks let the caller recover each surviving row's original
    window-start index, which the offset null needs to enforce its time gap.
    """
    if x.shape[0] < w:
        return None
    win = np.lib.stride_tricks.sliding_window_view(x, w)
    keep = np.isfinite(win).all(axis=1)
    win = win[keep]
    if win.shape[0] == 0:
        return None
    R = avg_rank_2d(win)
    R = R - R.mean(axis=1, keepdims=True)
    norm = np.linalg.norm(R, axis=1, keepdims=True)
    # A degenerate (all-equal) window has no defined correlation. Drop it rather than
    # letting it land as a zero, which would pull every quantile toward the middle.
    ok = norm[:, 0] > 0
    return (R[ok] / norm[ok]), keep, ok


def rho(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    return np.clip((A * B).sum(axis=1), -1.0, 1.0)


# ----------------------------------------------------------------------------------
# data
# ----------------------------------------------------------------------------------

def load_panel(include_heldout: bool = True) -> tuple[dict, dict]:
    ci = CotIndexer()
    ci.refresh_if_stale()

    series, asset_class = {}, {}
    for cls in ci.get_asset_classes(include_heldout=include_heldout):
        for name in ci.get_assets_for_asset_class(cls, include_heldout=include_heldout):
            try:
                df = ci.get_symbols_data(name, "Custom")
            except Exception as exc:  # a market with no price history is not a failure
                print(f"  skip {name}: {exc}", file=sys.stderr)
                continue
            if df is None or df.empty or PRICE not in df.columns:
                continue
            df = df.copy()
            df[DATE] = pd.to_datetime(df[DATE])
            cols = [DATE, PRICE] + [c for c in POS_COLS.values() if c in df.columns]
            df = df[cols].sort_values(DATE).drop_duplicates(DATE).reset_index(drop=True)
            if len(df) < max(WINDOWS) + 40:
                continue
            series[name] = df
            asset_class[name] = cls
    return series, asset_class


# ----------------------------------------------------------------------------------
# measurement
# ----------------------------------------------------------------------------------

def _prep(df: pd.DataFrame, key: str, w: int, diff: bool):
    price = df[PRICE].to_numpy(dtype=float)
    col = POS_COLS[key]
    if col not in df.columns:
        return None
    posn = df[col].to_numpy(dtype=float)
    if diff:
        price, posn = np.diff(price), np.diff(posn)
    rp = rank_windows(price, w)
    rx = rank_windows(posn, w)
    if rp is None or rx is None:
        return None
    Rp, keep_p, ok_p = rp
    Rx, keep_x, ok_x = rx
    # Keep only windows complete and non-degenerate in BOTH series, so real and null
    # are measured over an identical index.
    idx_p = np.flatnonzero(keep_p)[ok_p]
    idx_x = np.flatnonzero(keep_x)[ok_x]
    common = np.intersect1d(idx_p, idx_x)
    if common.size < 3 * w:
        return None
    sel_p = np.isin(idx_p, common)
    sel_x = np.isin(idx_x, common)
    return Rp[sel_p], Rx[sel_x], common


def measure(series: dict, asset_class: dict, diff: bool, rng: np.random.Generator):
    out = {}
    for w in WINDOWS:
        acc = {k: {"real": [], "synthetic": [], "offset": [], "cross": []} for k in POS_COLS}
        prepped: dict[tuple[str, str], tuple] = {}

        for name, df in series.items():
            for key in POS_COLS:
                got = _prep(df, key, w, diff)
                if got is None:
                    continue
                Rp, Rx, common = got
                prepped[(name, key)] = (Rp, Rx, common, df[DATE].to_numpy())

                acc[key]["real"].append(rho(Rp, Rx))

                # offset null: same market, windows at least w apart in time so they
                # share no week. `common` carries the original window start indices, so
                # the time gap is measured on those rather than on row position.
                m = Rp.shape[0]
                if m > 3 * w:
                    for _ in range(N_OFFSETS):
                        k = int(rng.integers(w, m - w))
                        gap = np.abs(common[k:] - common[:-k])
                        good = gap >= w
                        if good.any():
                            acc[key]["offset"].append(rho(Rp[:-k][good], Rx[k:][good]))

                # synthetic null: §3's prescription. A driftless Gaussian random walk
                # standing in for price, positioning left real.
                n_pts = len(df) - (1 if diff else 0)
                for _ in range(N_SYNTH):
                    walk = np.cumsum(rng.standard_normal(len(df)))
                    p = np.diff(walk) if diff else walk
                    rs = rank_windows(p[:n_pts], w)
                    if rs is None:
                        continue
                    Rs, keep_s, ok_s = rs
                    idx_s = np.flatnonzero(keep_s)[ok_s]
                    shared = np.intersect1d(idx_s, common)
                    if shared.size == 0:
                        continue
                    acc[key]["synthetic"].append(
                        rho(Rs[np.isin(idx_s, shared)], Rx[np.isin(common, shared)])
                    )

        # cross null: price of A against positioning of B, different asset classes.
        names = sorted(series)
        for key in POS_COLS:
            avail = [n for n in names if (n, key) in prepped]
            if len(avail) < 2:
                continue
            drawn = 0
            guard = 0
            while drawn < N_CROSS_PAIRS and guard < N_CROSS_PAIRS * 20:
                guard += 1
                a, b = rng.choice(len(avail), size=2, replace=False)
                na, nb = avail[a], avail[b]
                if asset_class[na] == asset_class[nb]:
                    continue
                Rp_a, _, com_a, dt_a = prepped[(na, key)]
                _, Rx_b, com_b, dt_b = prepped[(nb, key)]
                # Align on the report date the window ENDS on, so the two windows cover
                # the same calendar stretch.
                end_a = pd.Series(np.arange(len(com_a)), index=dt_a[com_a + w - 1])
                end_b = pd.Series(np.arange(len(com_b)), index=dt_b[com_b + w - 1])
                j = end_a.index.intersection(end_b.index)
                if len(j) < w:
                    continue
                acc[key]["cross"].append(rho(Rp_a[end_a.loc[j].to_numpy()],
                                             Rx_b[end_b.loc[j].to_numpy()]))
                drawn += 1

        out[w] = {k: {kind: (np.concatenate(v) if v else np.array([]))
                      for kind, v in d.items()} for k, d in acc.items()}
    return out


def summarise(vals: np.ndarray) -> dict:
    if vals.size == 0:
        return {}
    a = np.abs(vals)
    return {
        "n": int(vals.size),
        "median_abs": round(float(np.median(a)), 3),
        "p90_abs": round(float(np.quantile(a, 0.90)), 3),
        "p95_abs": round(float(np.quantile(a, 0.95)), 3),
        "p99_abs": round(float(np.quantile(a, 0.99)), 3),
        "share_abs_gt_030": round(float((a > 0.30).mean()), 4),
        "share_abs_gt_050": round(float((a > 0.50).mean()), 4),
        "share_abs_gt_070": round(float((a > 0.70).mean()), 4),
        "mean_signed": round(float(vals.mean()), 3),
    }


def thinned_offset_null(series: dict, key: str, rng: np.random.Generator) -> None:
    """Robustness check: the same offset null over NON-OVERLAPPING windows only.

    Rolling windows overlap heavily, so the pooled null is not a set of independent
    draws. That does not bias a quantile of a distribution, but the claim is cheap to
    check rather than assert, and §1 of the cotmetrics doc is a standing reminder that
    serial dependence in this data is bigger than it looks.
    """
    print(f"\n=== offset null, NON-OVERLAPPING windows only ({key}) ===")
    for w in WINDOWS:
        vals = []
        for df in series.values():
            got = _prep(df, key, w, False)
            if got is None:
                continue
            Rp, Rx, _ = got
            m = Rp.shape[0]
            if m <= 3 * w:
                continue
            for _ in range(N_OFFSETS):
                k = int(rng.integers(w, m - w))
                vals.append(rho(Rp[:-k], Rx[k:])[::w])   # thin to disjoint windows
        a = np.abs(np.concatenate(vals))
        print(f"  W={w:>3} n={a.size:>7} median {np.median(a):.3f} "
              f"p90 {np.quantile(a, .9):.3f} p95 {np.quantile(a, .95):.3f}")


def market_band(series: dict, name: str, key: str, w: int,
                rng: np.random.Generator, draws: int = 400) -> None:
    """A single market's own offset null at a single window, plus its latest reading.

    This is the form a reader of the dashboard actually needs: the band for THIS market
    at ITS configured lookback, not a pooled band.
    """
    df = series.get(name)
    if df is None:
        print(f"  {name}: not in panel", file=sys.stderr)
        return
    print(f"\n=== {name}, column {key}, W={w} ===")
    for diff, label in ((False, "levels"), (True, "differences")):
        got = _prep(df, key, w, diff)
        if got is None:
            continue
        Rp, Rx, _ = got
        m = Rp.shape[0]
        real = rho(Rp, Rx)
        null = np.abs(np.concatenate([
            rho(Rp[:-k], Rx[k:])
            for k in (int(rng.integers(w, m - w)) for _ in range(draws))
        ]))
        cur = real[-1]
        p = float((null >= abs(cur)).mean())
        print(f"  {label:<12} latest rho {cur:+.3f} | own null median {np.median(null):.3f} "
              f"p90 {np.quantile(null, .9):.3f} p95 {np.quantile(null, .95):.3f} "
              f"p99 {np.quantile(null, .99):.3f}")
        print(f"  {'':<12} two-sided null p for |rho| >= {abs(cur):.3f}: {p:.3f}"
              f" | real series median {np.median(real):+.3f}")


def regime_null(series: dict, name: str, key: str, w: int,
                rng: np.random.Generator, draws: int = 2000) -> None:
    """Is a reading a DEVIATION FROM THIS MARKET'S OWN BASELINE, or ordinary wandering?

    The zero-centred nulls above answer "is rho far from zero", which is the wrong
    question for a regime-shift claim: these series have a strongly signed baseline
    (NQ commercial sits near -0.42), so the null has to reproduce that baseline and then
    ask how far the statistic wanders from it when the relationship never changes.

    Construction: paired block bootstrap of the weekly CHANGES (dPrice, dPosition),
    resampled together in blocks so the contemporaneous relationship and the short-run
    dynamics both survive, then cumulated back to levels. The relationship is constant
    by construction, so anything the statistic does here is wandering, not a shift.

    Two probabilities, and they answer different questions:
      per-week  P(a single week reaches the observed value). The right reference if the
                market was chosen in advance.
      per-path  P(a history this long EVER reaches it). The right reference if the
                market was noticed BECAUSE the reading was extreme, which is the usual
                way a dashboard reading gets looked at.

    An AR(1)-in-levels null driven by price changes was tried and REJECTED: it produces
    a rolling statistic centred on zero (mean +0.002) rather than on the observed -0.34,
    so it cannot be used to judge deviations from a baseline it does not reproduce.
    """
    df = series.get(name)
    if df is None:
        print(f"  {name}: not in panel", file=sys.stderr)
        return
    P = df[PRICE].to_numpy(dtype=float)
    X = df[POS_COLS[key]].to_numpy(dtype=float)
    ok = np.isfinite(P) & np.isfinite(X)
    P, X = P[ok], X[ok]

    def roll(p, x):
        got = rank_windows(p, w), rank_windows(x, w)
        if got[0] is None or got[1] is None:
            return np.array([])
        (Ra, ka, oa), (Rb, kb, ob) = got
        ia, ib = np.flatnonzero(ka)[oa], np.flatnonzero(kb)[ob]
        c = np.intersect1d(ia, ib)
        return rho(Ra[np.isin(ia, c)], Rb[np.isin(ib, c)])

    real = roll(P, X)
    cur = real[-1]
    print(f"\n=== {name}, column {key}, W={w}: deviation-from-baseline null ===")
    print(f"  real rolling statistic: mean {real.mean():+.3f} sd {real.std():.3f} "
          f"latest {cur:+.3f}")

    # Model-free: distinct EPISODES reaching the level, not weeks. §1 of the cotmetrics
    # doc is explicit that a week count is not a sample size here.
    for thr in (0.3, 0.5, abs(cur)):
        hot = real >= thr
        eps = int((hot & ~np.r_[False, hot[:-1]]).sum())
        print(f"  history reached >= {thr:+.3f} in {eps} distinct episodes "
              f"({int(hot.sum())} weeks of {real.size})")

    dP, dX = np.diff(P), np.diff(X)
    n = len(dP)
    print(f"  {'L':>4} {'null mean':>10} {'sd':>6} {'P(week)':>9} {'P(path)':>9} {'thr p<.05':>10}")
    for L in (13, 26, 52, 104):
        nb = int(np.ceil(n / L))
        marg, mx = [], []
        for _ in range(draws):
            st = rng.integers(0, n - L, size=nb)
            idx = np.concatenate([np.arange(s, s + L) for s in st])[:n]
            p = np.r_[P[0], P[0] + np.cumsum(dP[idx])]
            x = np.r_[X[0], X[0] + np.cumsum(dX[idx])]
            r = roll(p, x)
            marg.append(r)
            mx.append(r.max())
        marg, mx = np.concatenate(marg), np.array(mx)
        print(f"  {L:>4} {marg.mean():>+10.3f} {marg.std():>6.3f} "
              f"{float((marg >= cur).mean()):>9.4f} {float((mx >= cur).mean()):>9.4f} "
              f"{np.quantile(mx, .95):>+10.3f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="write the full result table as JSON")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--non-overlapping", action="store_true",
                    help="also run the thinned (disjoint-window) offset null")
    ap.add_argument("--market", default=None,
                    help="also print this market's own band, e.g. 'Nasdaq'")
    ap.add_argument("--market-window", type=int, default=28,
                    help="window for --market (NQ's configured Custom lookback is 28)")
    ap.add_argument("--regime-null", action="store_true",
                    help="with --market, also run the deviation-from-baseline null")
    args = ap.parse_args()

    print("loading panel...", file=sys.stderr)
    series, asset_class = load_panel()
    print(f"  {len(series)} markets, "
          f"{len(set(asset_class.values()))} asset classes", file=sys.stderr)

    report = {
        "seed": args.seed,
        "markets": sorted(series),
        "n_markets": len(series),
        "windows": list(WINDOWS),
        "basis": {},
    }

    for diff in (False, True):
        label = "differences" if diff else "levels"
        print(f"measuring {label}...", file=sys.stderr)
        res = measure(series, asset_class, diff, np.random.default_rng(args.seed))
        report["basis"][label] = {
            str(w): {k: {kind: summarise(v) for kind, v in d.items()}
                     for k, d in per_w.items()}
            for w, per_w in res.items()
        }

        print(f"\n=== {label.upper()} ===")
        hdr = f"{'W':>4} {'column':<11} {'kind':<10} {'n':>9} {'med':>6} {'p90':>6} {'p95':>6} {'>0.3':>7} {'>0.5':>7} {'>0.7':>7}"
        print(hdr)
        for w in WINDOWS:
            for key in POS_COLS:
                for kind in ("real", "offset", "cross", "synthetic"):
                    s = summarise(res[w][key][kind])
                    if not s:
                        continue
                    print(f"{w:>4} {key:<11} {kind:<10} {s['n']:>9} "
                          f"{s['median_abs']:>6.3f} {s['p90_abs']:>6.3f} {s['p95_abs']:>6.3f} "
                          f"{s['share_abs_gt_030']:>7.3f} {s['share_abs_gt_050']:>7.3f} "
                          f"{s['share_abs_gt_070']:>7.3f}")

    if args.non_overlapping:
        thinned_offset_null(series, "comm", np.random.default_rng(args.seed))
    if args.market:
        market_band(series, args.market, "comm", args.market_window,
                    np.random.default_rng(args.seed))
        if args.regime_null:
            regime_null(series, args.market, "comm", args.market_window,
                        np.random.default_rng(args.seed))

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(report, fh, indent=2)
        print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
