"""The sentiment page as one self-contained HTML file, published at surveys.bluemagicai.com.

The app's `/sentiment` page stays local-only (`local_pages`): the published copy is this
file, rendered from the same read and the same two figures, and pushed to its own GitHub
Pages repo by dbmf-tracker's `deploy/publish_pages.py --key surveys`, the way the DBMF,
AHLT and ORR monitors are (docs/surveys-publishing.md). Publishing NAAIM's and AAII's history was cleared against
their terms by the operator on 2026-11-09; the app's gate is unchanged, because the
deployed app is not where the publication happens.

What the static page keeps from the app, and how:

- **Both lookbacks.** The 1Y/3Y toggle redrew the charts server-side. Here every
  lookback's figures, summary and notes are embedded, and the toggle swaps them with
  `Plotly.react`; the figures carry the page's `uirevision`, so a zoom survives a flip.
- **The y-axis re-fit on zoom.** The app's own `clientside.js` is inlined and its
  `autoscale_y_axes` is called on every `plotly_relayout`, exactly as the Dash
  clientside callback calls it, so the published page cannot fit its axes by a
  different rule than the app does. It finds the plot as `#<id> .js-plotly-plot`, which
  is why each chart is drawn inside a wrapper carrying the id.
- **Not the PNG export.** It leans on html2canvas and the app's theme container; a
  reader of a static page has the browser's own screenshot.

**Card order.** The current readings lead: under the tiles come the NAAIM card and
the AAII votes and allocation cards (the newest week and month, their recent rows and
their percentiles), which the lookback toggle never changes; NAAIM first, in the
tiles' order (its card since 2026-11-12). The toggle follows, directly
above the two cards it redraws (sentiment against price, weekly columns), and the
allocation-against-price history closes the page. Until 2026-11-10 the columns sat
last, three cards below the toggle that drives them; until 2026-11-12 the votes and
allocation cards sat below the charts. The allocation survey has its own notes
(`aaii_allocation.caption`), outside `#notes`, which the toggle rewrites.

**The readings strip** replaces the app's summary sentence: one tile per survey (its
own number, its index on the lookback, its date) and one for the stocks share, so the
page leads with three numbers rather than a paragraph. Since 2026-11-12 each tile is
built to be read at a glance: its percentile against the full history in a badge at
the top right, a 0-100 gauge under the value, and one line in words ("Near its lows
since 1987"), all in the tier's colour (`sentiment.percentile_tier`: warm toward the
history's highs, cool toward its lows, plain in between), which also edges the tile.
None of that moves with the lookback, so it is drawn once. The toggle rewrites the two
survey tiles' value, crowd-state line (`sentiment.crowd_state`, the index at the
chart's 80 and 20) and date (`#readings [data-key]`); the stocks tile is static.

**Provisional weeks** are not marked anywhere on the page but its footer
(`sentiment.provisional_note`), since 2026-11-12: readers did not use the distinction.

**Card text.** Each card opens on one sentence; the rest sits in a closed
`<details>` ("How to read this").

**On a phone** (below 600px, `fitted` in the page's script) the two weekly charts open
on `sentiment.PHONE_OPEN_YEARS`, not five years, every chart is taller by what the
lifted zoom buttons take, and the price chart by its legend's extra rows as well. The
y axes are then re-fitted to the window on screen, as they are after every lookback
flip: `Plotly.react` restores a reader's zoom on x (the figures' `uirevision`) but
not the y ranges the re-fit set, so a flip after a zoom showed one year of SPY on the
five-year scale (found 2026-11-10).

The figures are serialized by plotly.py and drawn by the plotly.js release it bundles,
loaded from Plotly's CDN rather than inlined (about 4.6 MB). The version is read from the
installed plotly.py at render time (`plotly_js_url`), never pinned here: the JSON a
plotly.py writes is the format its own bundled plotly.js reads, and the CI resolver and
the publishing venv do not install the same plotly.py.

`generated_at` is written as `"generated_at":"..."` on purpose: publish_pages masks that
exact spelling when deciding whether anything changed, so a rebuild with no new data
pushes nothing.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

import plotly.offline

import viz_constants as vc
from components import aaii_allocation, aaii_votes, naaim_card, sentiment


def plotly_js_url():
    """The CDN build of the plotly.js the installed plotly.py bundles."""
    return f"https://cdn.plot.ly/plotly-{plotly.offline.get_plotlyjs_version()}.min.js"


CLIENTSIDE_JS = Path(__file__).resolve().parent.parent / "assets" / "clientside.js"

TITLE = "Surveys, NAAIM and AAII"
#: The fund pages' header, in their words: an uppercase eyebrow naming the source
#: the way theirs name the fund, then the page's ticker in the accent and what it
#: shows. "Surveys" plays the ticker, since it is what the Monitors row calls this.
EYEBROW = "NAAIM Exposure Index · AAII Sentiment Survey · weekly, against SPY"
#: The eyebrow once the allocation cards are on the page: two of AAII's surveys, one of
#: them monthly, so "weekly" no longer describes the page.
EYEBROW_ALLOCATION = ("NAAIM Exposure Index · AAII Sentiment and Asset Allocation "
                      "Surveys · against SPY")
H1_TICKER, H1_REST = "Surveys", "NAAIM and AAII"
#: The title's ticker word. Not `--accent`: that is the app's button blue, which on
#: this theme is #002b36, and on the #1a1a1a page drew "Surveys" at a contrast of
#: about 1.2 to 1, an invisible word (2026-11-10 page review). The theme's blue reads
#: at 4.8 to 1; tests hold it above 4.5.
TICKER_COLOR = vc.SOLARIZED_DARK_BLUE
#: The page, card and border colours, and the column, of the DBMF, AHLT and ORR pages
#: (dbmf-tracker's templates, dark theme), so moving between the four monitors keeps
#: the background and the header in place. Until 2026-11-12 this page took the app's
#: #1a1a1a and a 1400px column: visibly greyer, and wider, so the Monitors row jumped
#: sideways on every switch. The charts' backgrounds are transparent, so they sit on
#: whatever card colour this sets. Hand-kept in step with those templates, as the
#: Monitors row is.
PAGE_COLOR, SURFACE_COLOR, LINE_COLOR = "#0d1013", "#151a1e", "rgba(255,255,255,0.09)"
PAGE_MAX_WIDTH_PX, PAGE_GUTTER_PX = 1180, 20
#: The tiles' tier tones (`sentiment.percentile_tier`): warm toward a history's highs,
#: cool toward its lows. Neither is a series colour on this page (the votes' green and
#: red, the allocation's bonds blue is darker), so a tile never reads as one of them.
TONE_HIGH, TONE_LOW = "#e3a33b", "#6fb0e0"
DESCRIPTION = ("NAAIM exposure and AAII bulls minus bears against SPY, weekly, as range "
               "indexes with SPY's drawdowns behind them, and AAII members' monthly "
               "split between stocks, bonds and cash since 1987.")
HOME = "https://bluemagicai.com/"
#: The monitor row the DBMF, AHLT and ORR pages carry, with this page marked current.
#: Hand-kept in step with dbmf-tracker's templates (its tests/test_site_nav.py names
#: this file). Market is the market internals page, a site of its own since 2026-11-11
#: (`market_internals_static`, which draws this same row with itself current).
SITES = (("DBMF", "https://dbmf.bluemagicai.com/"),
         ("AHLT", "https://ahlt.bluemagicai.com/"),
         ("ORR", "https://orr.bluemagicai.com/"),
         ("Surveys", "https://surveys.bluemagicai.com/"),
         ("Market", "https://internals.bluemagicai.com/"))
CURRENT = "Surveys"
#: The placeholder the fund pages carry for the monitor not yet published, drawn
#: after this site in the row, as theirs is. (name, hover text); None once KISS ships.
SOON = ("KISS", "KISS ETF monitor, coming soon")
SOON_AFTER = "ORR"
SOURCES = ("Sources: NAAIM Exposure Index (naaim.org), AAII Sentiment Survey (aaii.com), "
           "SPY total return, CFTC Commitments of Traders (S&P 500 consolidated).")
#: The same line with the allocation survey named, for a page that carries its cards.
SOURCES_ALLOCATION = SOURCES.replace(
    "AAII Sentiment Survey (aaii.com)",
    "AAII Sentiment Survey and Asset Allocation Survey (aaii.com)")

#: Zoom buttons left off below 600px, where the full ladder (3M to Max, nine buttons) runs
#: past the plot's left edge and over the panel title. Seven fit, as the page had before
#: 3M and 6M were added; 2Y and 15Y sit between neighbours a phone reader can still pick.
PHONE_HIDDEN_RANGES = ("2Y", "15Y")
PHONE_QUERY = "(max-width: 600px)"
#: How far the zoom buttons rise on a phone, in px, so they sit above the top panel's
#: title rather than over it: the seven left span the plot's width (from 81 of 309 px,
#: where the title ends at 181; measured 2026-11-10 on all three range-button charts).
#: 22 cleared the one-line titles; the columns chart's two-line row header needs 32.
PHONE_BUTTON_LIFT_PX = 32
#: Extra height for the price chart on a phone, px. Its legend wraps from one row to
#: four there and Plotly takes the room out of the plot, which shrank the gap between
#: the panels under the index panel's two-line readout until it sat on SPY's line.
#: Three more rows at about 29px each (measured at 375px, 2026-11-10: with 57 the gap
#: was 27px under a 31px readout; with 90 the plot is 368px and the gap 29).
PHONE_LEGEND_ROOM_PX = 90

PRICE_ID = "price"
COLUMNS_ID = "columns"
VOTES_ID = "votes"
#: The payload key for the AAII votes figures, beside the lookback keys: the card does
#: not depend on the lookback, so it is embedded once and drawn once. Four blocks
#: (still called halves, the name from when there were two).
VOTES_KEY = "votes"
VOTES_HALVES = ("recent", "history", "spread", "latest")
#: The AAII allocation card: the same block grid, its own payload key.
ALLOCATION_ID = "allocation"
ALLOCATION_KEY = "allocation"
ALLOCATION_BLOCKS = ("recent", "history", "gap", "latest")
#: (element id, payload key) of every block-grid card, drawn once each by the same JS.
NAAIM_ID = "naaim"
NAAIM_KEY = "naaim"
NAAIM_BLOCKS = ("recent", "change", "history", "latest")

GRID_CARDS = ((NAAIM_ID, NAAIM_KEY), (VOTES_ID, VOTES_KEY), (ALLOCATION_ID, ALLOCATION_KEY))
#: The AAII allocation against SPY: one figure, not indexed, so embedded once like the
#: grid cards, but drawn and re-fitted on zoom like the price chart.
ALLOCATION_PRICE_ID = "allocation-price"
#: The allocation survey's notes, static beside the sentiment ones.
ALLOCATION_NOTES_ID = "allocation-notes"
#: The readings strip, and the stocks tile's key beside the surveys' own.
READINGS_ID = "readings"
STOCKS_KEY = "stocks"
ALLOCATION_PRICE_KEY = "allocation_price"


def survey_tiles(read):
    """The readings strip's survey tiles for one lookback: label, value, state, context,
    foot. The value is the survey's own number; the index it sits at is the context,
    led by the crowd state that index means (`sentiment.crowd_state`), then its
    percentile against every official week (`sentiment.latest_percentile`). The
    percentile does not move with the lookback; the tile carries it on every lookback
    so the toggle's redraw rewrites it with the same words."""
    n = read.lookback_years
    return [{"key": r["key"], "label": r["label"], "value": f"{r['value']:.1f}",
             "state": r["state"],
             "context": f"index {r['index']:.0f} of 100 on its {n}-year range",
             "pct": r["pct"], "rank": r["rank"], "foot": _date(r["date"])}
            for r in sentiment.readings(read)]


def stocks_tile(allocation):
    """The stocks share and its gap from the average since the survey began."""
    share = float(allocation.recent.iloc[0]["stocks"])
    gap = share - float(allocation.average["stocks"])
    pct = allocation.latest_pct.get("stocks")
    return {"key": STOCKS_KEY, "label": "AAII stocks allocation", "value": f"{share:.1f}%",
            "context": (f"{abs(gap):.1f} points {'above' if gap >= 0 else 'below'} its "
                        f"average since {allocation.since.year}"),
            "pct": (sentiment.percentile_phrase(pct[1], allocation.since.year)
                    if pct else None),
            "rank": (*pct, allocation.since.year) if pct else None,
            "foot": f"{allocation.last:%b %Y}"}


def _tiles(tiles):
    esc = html.escape

    def context(t):
        # A survey tile leads its context with the crowd state on its lookback, in the
        # tile's own ink: the colour is the percentile's, and two colours on one tile
        # for two scales would contradict each other as often as not.
        state = (f'<b class="state">{esc(t["state"])}</b> · ' if t.get("state") else "")
        return f'<div class="ctx">{state}<span class="rest">{esc(t["context"])}</span></div>'

    def rank(t):
        # The badge, the gauge and the tier line: the same percentile three ways, for
        # the eye (colour), the hand (position) and the reader (words).
        pct, word, since = t["rank"]
        tier, words = sentiment.percentile_tier(pct, word)
        record = word in (sentiment.HIGHEST, sentiment.LOWEST)
        badge = (f'<div class="rank" title="{esc(t["pct"])}">'
                 + (esc(word.capitalize()) if record
                    else f'{esc(word)}<small> pctl</small>') + '</div>')
        body = (f'<div class="gauge" aria-hidden="true"><i style="left:{pct}%"></i></div>'
                f'<div class="tier">{esc(words)} since {since}</div>')
        return badge, body, tier

    out = []
    for t in tiles:
        badge, body, tier = rank(t) if t.get("rank") else ("", "", sentiment.TIER_MID)
        out.append(f'<div class="tile tier-{tier}" data-key="{esc(t["key"])}">'
                   f'<div class="head"><div class="label">{esc(t["label"])}</div>{badge}</div>'
                   f'<div class="value">{esc(t["value"])}</div>'
                   + body + context(t)
                   + f'<div class="foot">{esc(t["foot"])}</div></div>')
    return (f'<div class="tiles" id="{READINGS_ID}" role="group" aria-label="Latest readings">'
            + "".join(out) + '</div>\n')


def _sub(subtitle, how=None):
    """A card's one-sentence subtitle and, closed under it, the rest."""
    esc = html.escape
    out = f'<div class="sub">{esc(subtitle)}</div>\n'
    if how:
        out += (f'<details class="how"><summary>{esc(sentiment.HOW_TO_READ_LABEL)}</summary>'
                f'<p>{esc(how)}</p></details>\n')
    return out


def lookback_payload(read, colors, palette):
    """Everything one lookback draws, as JSON-ready values."""
    return {
        "price": json.loads(sentiment.price_sentiment_figure(read, colors, palette).to_json()),
        "columns": json.loads(sentiment.columns_figure(read, colors, palette).to_json()),
        "tiles": survey_tiles(read),
        "caption": sentiment.caption(read, local=False),
    }


def _script_json(value):
    """JSON safe inside a <script> element: no `</` can close it early."""
    return json.dumps(value, separators=(",", ":")).replace("</", "<\\/")


def _nav():
    links = []
    for name, url in SITES:
        current = ' aria-current="page"' if name == CURRENT else ""
        links.append(f'<a href="{url}"{current}>{name}</a>')
        if SOON and name == SOON_AFTER:
            links.append(f'<span class="soon" title="{html.escape(SOON[1])}">'
                         f'{html.escape(SOON[0])} <small>soon</small></span>')
    return ('<nav class="sites" aria-label="Monitors"><span class="sep">Monitors</span>'
            + "".join(links)
            + f'<a class="home" href="{HOME}">COT Analyzer &rarr;</a></nav>')


def _provisional(read):
    """The footer's sentence on the provisional weeks, as its own line, or nothing."""
    note = sentiment.provisional_note(read)
    return f'<p class="prov">{html.escape(note)}</p>' if note else ""


def _date(d):
    """Nov 6, 2026: the fund pages' date spelling, without a platform-specific %-d."""
    return f"{d:%b} {d.day}, {d:%Y}"


def _header(read, allocation=None):
    """The fund pages' header block: eyebrow, accent ticker in the title, and the as-of
    on the right. The as-of names the newest week each survey has (and the allocation
    survey's newest month, when its cards are on the page), and only that:
    the build stamp stays out of the visible page because the publisher compares
    rebuilds with only the JSON stamp masked, so a visible one would force a push
    every run whether or not a reader could see a change.
    """
    parts = [f"{label} <b>{_date(read.last[key])}</b>"
             for key, label in (("naaim", "NAAIM"), ("aaii", "AAII")) if key in read.last]
    if allocation is not None:
        parts.append(f"AAII allocation <b>{allocation.last:%b %Y}</b>")
    asof = ("Through " + " · ".join(parts) + "<br>"
            if parts else "")
    asof += ('<a href="https://naaim.org/" rel="noopener">naaim.org</a> · '
             '<a href="https://www.aaii.com/" rel="noopener">aaii.com</a>')
    eyebrow = EYEBROW if allocation is None else EYEBROW_ALLOCATION
    return ('<header class="top"><div>'
            f'<div class="eyebrow">{html.escape(eyebrow)}</div>'
            f'<h1><span class="tk">{html.escape(H1_TICKER)}</span> {html.escape(H1_REST)}</h1>'
            f'</div><div class="asof">{asof}</div></header>')


def render(reads, colors, palette, generated_at=None, clientside_js=None, votes=None,
           allocation=None, naaim=None):
    """The page for `reads`, a {lookback years: SentimentRead} with the default included,
    `naaim` (`naaim_card.read()`), `votes` (`aaii_votes.read()`) and `allocation`
    (`aaii_allocation.read()`), each of whose cards is left out when it is None.

    Raises ValueError when the default lookback is missing or any read is empty, so a
    failed store read stops the publish rather than putting an empty page up.
    """
    if sentiment.DEFAULT_LOOKBACK not in reads:
        raise ValueError(f"no read for the default lookback ({sentiment.DEFAULT_LOOKBACK}y)")
    for years, read in reads.items():
        if read.frame.empty:
            raise ValueError(f"the {years}y read is empty (awaiting {', '.join(read.awaiting)})")
    payload = {str(y): lookback_payload(r, colors, palette) for y, r in sorted(reads.items())}
    if naaim is not None:
        payload[NAAIM_KEY] = {block: json.loads(fig.to_json()) for block, fig
                              in zip(NAAIM_BLOCKS, naaim_card.figures(naaim, colors, palette))}
    if votes is not None:
        payload[VOTES_KEY] = {half: json.loads(fig.to_json()) for half, fig
                              in zip(VOTES_HALVES, aaii_votes.figures(votes, colors))}
    if allocation is not None:
        payload[ALLOCATION_KEY] = {
            block: json.loads(fig.to_json()) for block, fig
            in zip(ALLOCATION_BLOCKS, aaii_allocation.figures(allocation, colors))}
        spy = reads[sentiment.DEFAULT_LOOKBACK].frame.get("spy")
        payload[ALLOCATION_PRICE_KEY] = json.loads(
            aaii_allocation.price_figure(allocation, spy, colors).to_json())
    default = payload[str(sentiment.DEFAULT_LOOKBACK)]
    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    js = clientside_js if clientside_js is not None else CLIENTSIDE_JS.read_text(encoding="utf-8")
    esc = html.escape

    pressed = {y: "true" if y == sentiment.DEFAULT_LOOKBACK else "false" for y in reads}
    buttons = "".join(f'<button type="button" data-years="{y}" aria-pressed="{pressed[y]}">'
                      f'{y}Y</button>' for y in sorted(reads))
    notes = "".join(f"<p>{esc(p)}</p>" for p in default["caption"])
    # The allocation survey's tile and notes are not rewritten by the lookback toggle:
    # nothing in them depends on the lookback.
    tiles = list(default["tiles"])
    allocation_notes = ""
    if allocation is not None:
        tiles.append(stocks_tile(allocation))
        allocation_notes = (f'<div class="notes" id="{ALLOCATION_NOTES_ID}">'
                            + "".join(f"<p>{esc(p)}</p>"
                                      for p in aaii_allocation.caption(allocation))
                            + '</div>\n')
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(TITLE)}</title>
<meta name="description" content="{esc(DESCRIPTION)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap">
<style>
:root {{ --page: {PAGE_COLOR}; --ink: {vc.BRIGHTER_TEXT_COLOR}; --ink-2: {vc.TEXT_COLOR};
  --muted: #7d8794; --line: {LINE_COLOR}; --surface: {SURFACE_COLOR};
  --wash: rgba(255,255,255,0.06); --accent: {vc.BLUE_BACKGROUND}; --ticker: {TICKER_COLOR};
  --sans: "Public Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace; }}
*, *::before, *::after {{ box-sizing: border-box; }}
html, body {{ background: var(--page); color: var(--ink-2); margin: 0; font-family: var(--sans); }}
body {{ padding-inline: {PAGE_GUTTER_PX}px; padding-block: 28px 56px; }}
main {{ max-width: {PAGE_MAX_WIDTH_PX}px; margin: 0 auto; }}
/* The header is the fund pages' (dbmf-tracker's templates), rule for rule, so the
   four monitors read as one set: the Monitors row, then eyebrow, accent ticker and
   title on the left and the as-of on the right. Only the theme differs, this page
   being dark on the app's own colours. */
nav.sites {{ display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; font-size: 12.5px; margin-bottom: 14px; }}
nav.sites a {{ color: var(--ink-2); text-decoration: none; padding: 3px 9px; border-radius: 6px; border: 1px solid transparent; }}
nav.sites a:hover {{ background: var(--wash); color: var(--ink); }}
nav.sites a[aria-current="page"] {{ color: var(--ink); font-weight: 600; border-color: var(--line); background: var(--surface); }}
nav.sites a:focus-visible {{ outline: 2px solid var(--ticker); outline-offset: 1px; }}
nav.sites .home {{ margin-left: auto; }}
nav.sites .sep {{ color: var(--muted); }}
nav.sites .soon {{ color: var(--muted); padding: 3px 9px; border: 1px dashed var(--line); border-radius: 6px; cursor: default; }}
nav.sites .soon small {{ font-size: 10px; letter-spacing: .06em; text-transform: uppercase; margin-left: 3px; }}
header.top {{ display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 12px 24px; margin-bottom: 14px; }}
/* The fund pages' body sets 14px/1.5 and their header inherits it; here only the header
   takes it, so the cards keep their own text metrics while the eyebrow and title land
   on the same pixels as theirs. */
nav.sites, header.top {{ line-height: 1.5; }}
.eyebrow {{ font-size: 11px; letter-spacing: .09em; text-transform: uppercase; color: var(--muted); font-weight: 600; }}
h1 {{ color: var(--ink); margin: 2px 0 0; font-size: 26px; line-height: 1.15; font-weight: 700; letter-spacing: -.01em; text-wrap: balance; }}
h1 .tk {{ font-family: var(--mono); font-weight: 600; color: var(--ticker); }}
.asof {{ color: var(--ink-2); font-size: 13px; text-align: right; }}
.asof b {{ color: var(--ink); font-weight: 600; }}
.asof a {{ color: var(--ink-2); }}
@media (max-width: 600px) {{ nav.sites .home {{ margin-left: 0; }} .asof {{ text-align: left; }} .card {{ padding: 10px 6px; }} }}
/* The readings strip: label and percentile badge, value, gauge, tier line, context,
   date. The tier (sentiment.percentile_tier) sets --tone: warm toward the history's
   highs, cool toward its lows, none in between; filled past 90 and 10, outlined past
   80 and 20. Values and words stay in the ink tokens. */
.tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin-bottom: 12px; }}
.tile {{ --tone: var(--muted); background: var(--surface); border: 1px solid var(--line); border-left: 3px solid var(--line); border-radius: 6px; padding: 10px 14px; }}
.tile.tier-top, .tile.tier-high {{ --tone: {TONE_HIGH}; }}
.tile.tier-bottom, .tile.tier-low {{ --tone: {TONE_LOW}; }}
.tile:not(.tier-mid) {{ border-left-color: var(--tone); }}
.tile .head {{ display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }}
.tile .label {{ font-size: 0.8rem; color: var(--ink-2); }}
.tile .rank {{ font-size: 0.8rem; font-weight: 600; line-height: 1.3; white-space: nowrap; padding: 1px 8px; border-radius: 999px;
  border: 1px solid var(--line); color: var(--ink-2); }}
.tile .rank small {{ font-size: 0.7rem; font-weight: 500; }}
.tile.tier-high .rank, .tile.tier-low .rank {{ border-color: var(--tone); color: var(--tone); }}
.tile.tier-top .rank, .tile.tier-bottom .rank {{ background: var(--tone); border-color: var(--tone); color: var(--page); }}
.tile .value {{ font-size: 1.75rem; font-weight: 600; line-height: 1.2; color: var(--ink); }}
.tile .gauge {{ position: relative; height: 4px; border-radius: 2px; background: rgba(255,255,255,0.12); margin: 8px 5px 6px; }}
.tile .gauge::after {{ content: ""; position: absolute; left: 50%; top: -3px; width: 1px; height: 10px; background: var(--muted); }}
.tile .gauge i {{ position: absolute; top: 50%; width: 10px; height: 10px; margin: -5px 0 0 -5px; border-radius: 50%;
  background: var(--tone); box-shadow: 0 0 0 2px var(--surface); z-index: 1; }}
.tile.tier-mid .gauge i {{ background: var(--ink-2); }}
.tile .tier {{ font-size: 0.85rem; font-weight: 600; color: var(--ink); }}
.tile:not(.tier-mid) .tier {{ color: var(--tone); }}
.tile .ctx {{ font-size: 0.82rem; color: var(--ink-2); }}
.tile .state {{ font-weight: 600; color: var(--ink); }}
.tile .foot {{ font-size: 0.75rem; color: var(--muted); margin-top: 2px; }}
@media (max-width: 600px) {{
  .tiles {{ grid-template-columns: minmax(0, 1fr); gap: 6px; }}
  .tile {{ padding: 8px 12px; }}
  .tile .value {{ font-size: 1.5rem; }}
}}
.lookback {{ display: flex; align-items: center; gap: 6px; font-size: 0.8rem; margin-bottom: 14px; }}
.lookback button {{ background: var(--accent); color: var(--ink); border: 1px solid transparent; border-radius: 3px;
  font-size: 10px; padding: 2px 8px; cursor: pointer; }}
.lookback button[aria-pressed="true"] {{ border-color: var(--ink); }}
.card {{ background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 12px 16px; margin-bottom: 12px; }}
.card h2 {{ color: var(--ink); font-size: 0.95rem; font-weight: 400; margin: 0 0 3px; }}
.card .sub {{ font-size: 0.8rem; margin-bottom: 6px; }}
.card .how {{ font-size: 0.8rem; margin: -2px 0 4px; }}
.card .how summary {{ cursor: pointer; width: fit-content; color: var(--ink); }}
.card .how p {{ margin: 4px 0 0; }}
.votes-grid {{ display: grid; grid-template-columns: minmax(0, 1fr); gap: 2px 24px; }}
@media (min-width: {aaii_votes.VOTES_SIDE_BY_SIDE_MIN_PX}px) {{ .votes-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
.notes p, footer {{ font-size: 0.8rem; line-height: 1.45; }}
footer {{ color: var(--muted); border-top: 1px solid var(--line); margin-top: 18px; padding-top: 10px; }}
footer .prov {{ margin: 0 0 6px; }}
</style>
<script src="{plotly_js_url()}" charset="utf-8"></script>
</head>
<body>
<main>
{_nav()}
{_header(reads[sentiment.DEFAULT_LOOKBACK], allocation)}
{_tiles(tiles)}{_naaim_card() if naaim is not None else ""}{_votes_card() if votes is not None else ""}{_allocation_card() if allocation is not None else ""}<div class="lookback" role="group" aria-label="Index lookback"><span>Index lookback</span>{buttons}</div>
<section class="card"><h2>{esc(sentiment.PRICE_TITLE)}</h2>
{_sub(sentiment.PRICE_SUBTITLE, sentiment.PRICE_HOW_TO_READ)}<div id="{PRICE_ID}"><div class="plot"></div></div></section>
<section class="card"><h2>{esc(sentiment.COLUMNS_TITLE)}</h2>
<div id="{COLUMNS_ID}"><div class="plot"></div></div></section>
{_allocation_price_card() if allocation is not None else ""}<div class="notes" id="notes">{notes}</div>
{allocation_notes}<footer>{_provisional(reads[sentiment.DEFAULT_LOOKBACK])}{esc(SOURCES if allocation is None else SOURCES_ALLOCATION)} Not investment advice.</footer>
</main>
<script>window.SURVEYS_META={{"generated_at":"{esc(stamp)}"}};</script>
<script type="application/json" id="surveys-data">{_script_json(payload)}</script>
<script>window.dash_clientside = {{no_update: null}};</script>
<script>
{js}
</script>
<script>
(function () {{
  var DATA = JSON.parse(document.getElementById('surveys-data').textContent);
  var CONFIG = {{displayModeBar: false, responsive: true}};
  var IDS = ['{PRICE_ID}', '{COLUMNS_ID}'];
  // Drawn once (no lookback), re-fitted on zoom like the two above.
  var ONCE = {{'{ALLOCATION_PRICE_ID}': '{ALLOCATION_PRICE_KEY}'}};
  var KEYS = {{'{PRICE_ID}': 'price', '{COLUMNS_ID}': 'columns'}};
  var refit = window.dash_clientside.clientside.autoscale_y_axes;
  var PHONE = window.matchMedia('{PHONE_QUERY}').matches;
  var HIDDEN = PHONE ? {_script_json(list(PHONE_HIDDEN_RANGES))} : [];
  // Extra height on a phone, by chart: the legend rows Plotly takes out of the plot.
  var ROOM = {{'{PRICE_ID}': {PHONE_LEGEND_ROOM_PX}}};
  function plotOf(id) {{ return document.querySelector('#' + id + ' .plot'); }}
  function fitted(layout, id) {{
    var rs = layout.xaxis && layout.xaxis.rangeselector;
    if (!PHONE || !rs) {{ return layout; }}
    var buttons = rs.buttons.filter(function (b) {{ return HIDDEN.indexOf(b.label) < 0; }});
    // Lifted above the top panel's title: on a phone the seven buttons span the plot,
    // and level with the title they drew over it. The figure grows by the lift (and
    // by its legend's extra rows), so the plot keeps the height it has on a desktop.
    var margin = Object.assign({{}}, layout.margin);
    margin.t = (margin.t || 0) + {PHONE_BUTTON_LIFT_PX};
    var height = (layout.height || 450) + {PHONE_BUTTON_LIFT_PX} + (ROOM[id] || 0);
    var plotH = height - margin.t - (margin.b || 0);
    var lifted = Object.assign({{}}, rs, {{buttons: buttons, yanchor: 'bottom',
                                          y: 1 + {PHONE_BUTTON_LIFT_PX} / plotH}});
    var out = Object.assign({{}}, layout, {{margin: margin, height: height}});
    out.xaxis = Object.assign({{}}, layout.xaxis, {{rangeselector: lifted}});
    // The weekly charts open on fewer years: five is a scribble at this width.
    if (IDS.indexOf(id) >= 0 && layout.xaxis.range) {{
      var start = new Date(layout.xaxis.range[0]);
      start.setFullYear(start.getFullYear() + {sentiment.OPEN_YEARS - sentiment.PHONE_OPEN_YEARS});
      var from = start.toISOString().slice(0, 10);
      Object.keys(out).forEach(function (k) {{
        if (k.indexOf('xaxis') === 0 && out[k].range) {{
          out[k] = Object.assign({{}}, out[k], {{range: [from, out[k].range[1]]}});
        }}
      }});
    }}
    return out;
  }}
  // Fit the y axes to the window now on screen, by the rule a zoom uses.
  function refitNow(id) {{
    var gd = plotOf(id), r = gd.layout && gd.layout.xaxis && gd.layout.xaxis.range;
    if (!r) {{ return; }}
    try {{ refit({{'xaxis.range': [r[0], r[1]]}}, id); }} catch (e) {{ console.error(e); }}
  }}
  function draw(years, first) {{
    var d = DATA[String(years)];
    IDS.forEach(function (id) {{
      var fig = d[KEYS[id]];
      var fn = first ? Plotly.newPlot : Plotly.react;
      var done = fn(plotOf(id), fig.data, fitted(fig.layout, id), CONFIG);
      // A first draw on a desktop is already fitted to its window by the server. A
      // phone opens on a shorter one, and a flip keeps the reader's x zoom but not
      // the y ranges fitted to it, so both are fitted again here.
      if (PHONE || !first) {{ Promise.resolve(done).then(function () {{ refitNow(id); }}); }}
    }});
    d.tiles.forEach(function (t) {{
      var tile = document.querySelector('#{READINGS_ID} [data-key="' + t.key + '"]');
      if (!tile) {{ return; }}
      tile.querySelector('.value').textContent = t.value;
      var state = tile.querySelector('.state');
      if (state) {{ state.textContent = t.state; }}
      tile.querySelector('.rest').textContent = t.context;
      tile.querySelector('.foot').textContent = t.foot;
    }});
    var notes = document.getElementById('notes');
    notes.textContent = '';
    d.caption.forEach(function (t) {{
      var p = document.createElement('p'); p.textContent = t; notes.appendChild(p);
    }});
    document.querySelectorAll('.lookback button').forEach(function (b) {{
      b.setAttribute('aria-pressed', b.dataset.years === String(years) ? 'true' : 'false');
    }});
  }}
  draw({sentiment.DEFAULT_LOOKBACK}, true);
  {_script_json([list(c) for c in GRID_CARDS])}.forEach(function (card) {{
    var id = card[0], blocks = DATA[card[1]];
    if (!blocks) {{ return; }}
    Object.keys(blocks).forEach(function (half) {{
      Plotly.newPlot(document.querySelector('#' + id + ' [data-half="' + half + '"]'),
                     blocks[half].data, blocks[half].layout, CONFIG);
    }});
  }});
  Object.keys(ONCE).forEach(function (id) {{
    var fig = DATA[ONCE[id]];
    if (fig) {{ Plotly.newPlot(plotOf(id), fig.data, fitted(fig.layout, id), CONFIG); }}
  }});
  IDS.concat(Object.keys(ONCE).filter(function (id) {{ return DATA[ONCE[id]]; }})).forEach(function (id) {{
    plotOf(id).on('plotly_relayout', function (ev) {{
      try {{ refit(ev, id); }} catch (e) {{ console.error(e); }}
    }});
  }});
  document.querySelectorAll('.lookback button').forEach(function (b) {{
    b.addEventListener('click', function () {{ draw(b.dataset.years, false); }});
  }});
}})();
</script>
</body>
</html>
"""


def _grid_card(title, subtitle, element_id, blocks, how=None):
    """A card of figure blocks in the wrapping grid (`.votes-grid`, named for the first
    card that used it): one across on a phone, two from 768px, four from 1400px."""
    esc = html.escape
    return (f'<section class="card"><h2>{esc(title)}</h2>\n'
            + _sub(subtitle, how)
            + f'<div id="{element_id}" class="votes-grid">'
            + "".join(f'<div class="plot" data-half="{h}"></div>' for h in blocks)
            + '</div></section>\n')


def _naaim_card():
    return _grid_card(naaim_card.TITLE, naaim_card.SUBTITLE, NAAIM_ID, NAAIM_BLOCKS,
                      naaim_card.HOW_TO_READ)


def _votes_card():
    return _grid_card(aaii_votes.TITLE, aaii_votes.SUBTITLE, VOTES_ID, VOTES_HALVES,
                      aaii_votes.HOW_TO_READ)


def _allocation_card():
    return _grid_card(aaii_allocation.TITLE, aaii_allocation.SUBTITLE, ALLOCATION_ID,
                      ALLOCATION_BLOCKS, aaii_allocation.HOW_TO_READ)


def _allocation_price_card():
    esc = html.escape
    return (f'<section class="card"><h2>{esc(aaii_allocation.PRICE_TITLE)}</h2>\n'
            + _sub(aaii_allocation.PRICE_SUBTITLE, aaii_allocation.PRICE_HOW_TO_READ)
            + f'<div id="{ALLOCATION_PRICE_ID}"><div class="plot"></div></div></section>\n')


def write(path, reads, colors, palette, **kw):
    """Render and write with LF line ends, the bytes publish_pages compares."""
    Path(path).write_text(render(reads, colors, palette, **kw), encoding="utf-8", newline="")
