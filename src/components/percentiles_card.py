"""The percentiles card: each survey's newest reading as a percentile over three
histories, side by side at the top of the sentiment page (local `/sentiment`) and its
published copy (surveys.bluemagicai.com), right under the tiles.

Added 2026-11-12 at the user's request ("the bottom right percentile views are the
highlight of the datasets"): until then each survey's card carried its percentile block
as its fourth, bottom-right block, the last thing read. Gathered here they are read
first and together. Three blocks: NAAIM exposure, the AAII votes, and AAII's bulls minus
bears (the tile's number), which replaced the allocation block later the same day; the
allocation block went back to its own card (`aaii_allocation.figures`), a monthly
holding rather than a weekly opinion. The NAAIM and votes cards keep their other three
blocks.

Each block (`aaii_votes.dots_figure`) has a row per history, top down: every official
reading since the series began, the last three years and the last year, and on each row
a dot per leg with its percentile (`sentiment.percentile_of`: the share of the history
at or below the reading, 1 to 100) printed inside, in the leg's colour on the card
below. The since-the-start row ranks against official readings only, as each card's
long-run numbers do. The windows rank the newest reading against the window's earlier
readings, provisional weeks included, because the official NAAIM series runs about a
quarter behind and AAII's member spreadsheet a few weeks (`naaim_card`, `aaii_votes`).

**Drift.** Some shares have trended for decades, so a full-history percentile partly
measures the trend: AAII neutral ran about 41% in the late 1980s and 28% in the 2020s,
bearish 27% and 37% (decade means).
The windows are the check: a reading extreme over the last year too is extreme now, not
only against a different era.

**Close dots** are dodged sideways about their shared place (`aaii_votes.dodge`); the
number in a dot is always its percentile.

**Layout.** The three blocks go across from `aaii_votes.THREE_ACROSS_MIN_PX`, as each
survey's own card does, two across from `VOTES_SIDE_BY_SIDE_MIN_PX`, stacked below.
"""
from components import aaii_votes, naaim_card

TITLE = "Percentiles"
SUBTITLE = ("Each survey's newest reading as a percentile (the number in each dot) of "
            "its full history, the last three years and the last year, against a "
            "dotted median at 50.")
HOW_TO_READ = ("A percentile is the share of the history at or below the reading: 96 "
               "means only 4% of readings were higher. The first row ranks against "
               "every official reading since the survey began; the last two against "
               "the last three years and the last year, including the newest weeks, "
               "which NAAIM and AAII publish in full only later. Some shares have "
               "drifted for decades (AAII neutral from about 41% in the late 1980s to "
               "28% in the 2020s), so a full-history "
               "percentile partly measures the drift; a reading that is also extreme "
               "over the last year is extreme now. Dots that would overlap are spread "
               "apart; the number in each dot is its percentile. Colours match the "
               "cards below.")
#: Block keys: NAAIM, the AAII votes, and AAII's bulls minus bears (the tile's number),
#: which replaced the allocation block on 2026-11-12 (that block went back to its card).
BLOCKS = ("naaim", "votes", "bulls_bears")


def figures(colors, palette, naaim=None, votes=None):
    """[(block key, figure)] for each survey that is in, in BLOCKS order."""
    out = []
    if naaim is not None:
        out.append(("naaim", naaim_card.latest_figure(naaim, palette)))
    if votes is not None:
        out.append(("votes", aaii_votes.latest_figure(votes, colors)))
        out.append(("bulls_bears", aaii_votes.spread_figure_percentiles(votes, palette)))
    return out
