"""Write the sentiment page as one static HTML file, for surveys.bluemagicai.com.

Reads the same stores the app does (marketdata for NAAIM, AAII and SPY, the cotmetrics
indexer for S&P 500 commercials), at every lookback the page toggles, and writes
`components.sentiment_static`'s page. Exits 1 without writing when any read is empty,
so a broken store never replaces the published page with an empty one.

Publishing is a separate step, dbmf-tracker's publish_pages.py (it adds the noindex tag,
robots.txt, the view beacon and GoatCounter, and pushes only when the page changed):

    ./scripts/publish_surveys.sh

Usage, from the repo root (run-local.sh's environment: the stores, COTMETRICS_PARAMS and
COT_VIZ_CONFIG; publish_surveys.sh sets it the same way):

    PYTHONPATH=src .venv/bin/python scripts/export_sentiment_page.py OUT.html
"""
from __future__ import annotations

import argparse
import os
import sys

os.environ.setdefault("COT_SKIP_BOOT_FETCH", "1")   # no options/price fetch at indexer boot


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out", help="the HTML file to write")
    args = ap.parse_args(argv)

    import viz_config
    from components import plot_colors, sentiment, sentiment_static

    reads = {y: sentiment.build_read(lookback_years=y) for y in sentiment.LOOKBACK_YEARS}
    for years, read in reads.items():
        if read.awaiting:
            print(f"export-sentiment: {years}y read awaiting {', '.join(read.awaiting)}",
                  file=sys.stderr)
    palette = viz_config.get_palette()
    try:
        sentiment_static.write(args.out, reads, plot_colors.grid_colors(palette), palette)
    except ValueError as e:
        print(f"export-sentiment: not written: {e}", file=sys.stderr)
        return 1
    last = reads[sentiment.DEFAULT_LOOKBACK].last
    print(f"export-sentiment: wrote {args.out} ("
          + ", ".join(f"{k} {v:%Y-%m-%d}" for k, v in last.items()) + ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
