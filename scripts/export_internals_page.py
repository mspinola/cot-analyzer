"""Write the market internals page as one static HTML file, for its own subdomain.

Reads what the app's `/internals` page reads (the marketdata store: TradingView breadth
series and ETF bars), builds the same snapshot, and writes
`components.market_internals_static`'s page. Exits 1 without writing when the snapshot
holds no read at all, so a store that could not be read never replaces the published
page. Reads the store could not serve are named on stderr and on the page.

Publishing is a separate step, dbmf-tracker's publish_pages.py (it adds the noindex tag,
robots.txt, the view beacon and GoatCounter, and pushes only when the page changed):

    ./scripts/publish_internals.sh

Usage, from the repo root (run-local.sh's environment: the stores, COTMETRICS_PARAMS and
COT_VIZ_CONFIG; publish_internals.sh sets it the same way):

    PYTHONPATH=src .venv/bin/python scripts/export_internals_page.py OUT.html
"""
from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="the HTML file to write")
    args = ap.parse_args(argv)

    import viz_config
    from components import market_internals, market_internals_static, plot_colors

    # build_snapshot, not snapshot(): one read per run, nothing to cache.
    snap = market_internals.build_snapshot()
    if snap.awaiting:
        print(f"export-internals: awaiting {', '.join(snap.awaiting)}", file=sys.stderr)
    for note in market_internals.stale_notes(snap):
        print(f"export-internals: trailing: {note}", file=sys.stderr)
    try:
        market_internals_static.write(args.out, snap,
                                      plot_colors.grid_colors(viz_config.get_palette()))
    except ValueError as e:
        print(f"export-internals: not written: {e}", file=sys.stderr)
        return 1
    lean, count = market_internals.headline(snap)
    print(f"export-internals: wrote {args.out} (through {snap.date}; {lean} {count})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
