"""The market internals page as one self-contained HTML file, for its own subdomain.

What was the app's `/internals` page until 2026-11-11 (that path now 301s here): the
snapshot (`components.market_internals`) and the titles, formats and figures
(`components.market_internals_view`) it drew, under the header the other monitors carry
(DBMF, AHLT, ORR, Surveys), so the five read as one set. Published the way the
surveys page is: `scripts/export_internals_page.py` writes the file and dbmf-tracker's
`deploy/publish_pages.py --key internals` pushes it to a GitHub Pages repo of its own
(docs/internals-publishing.md).

No JavaScript beyond drawing: the page has no controls, and its charts are static
plots with hover off, so the figures are embedded as JSON and drawn once.

The figures are serialized by plotly.py and drawn by the plotly.js release it bundles,
loaded from Plotly's CDN (`sentiment_static.plotly_js_url`, and the reason is there).

`generated_at` is written as `"generated_at":"..."` on purpose: publish_pages masks
that exact spelling when deciding whether anything changed, so a rebuild with no new
data pushes nothing. For the same reason no build time is visible on the page; the
as-of is the newest session the reads carry.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

import components.market_internals as mi
import components.market_internals_view as view
import viz_constants as vc
from components import plot_colors
from components import sentiment_static as surveys

TITLE = "Market Internals"
EYEBROW = "Breadth · credit · rotation · volume · daily"
H1_TICKER, H1_REST = "Market", "internals"
DESCRIPTION = ("Six daily reads of the tape on one page: Nasdaq FOMO, net new 52-week "
               "highs, advancing against declining issues, high-yield credit against its "
               "20-day average, staples over Nasdaq against its 50-day, and 20-session "
               "up/down volume, beside an ETF table.")
#: This page's name in the monitors row (`sentiment_static.SITES`, the one list).
CURRENT = "Market"
SOURCES = ("Sources: TradingView daily breadth series (Nasdaq and NYSE), "
           "ETF daily bars from Yahoo Finance.")

DATA_ID = "internals-data"
#: Payload keys of the three charts; a sparkline's key is SPARK_PREFIX + its symbol.
FOMO_KEY, CREDIT_KEY, ROTATION_KEY = "fomo", "credit", "rotation"
SPARK_PREFIX = "spark:"

_esc = html.escape


def _date(stamp):
    """Nov 6, 2026 from the snapshot's 2026-11-06, the monitors' date spelling."""
    return surveys._date(datetime.strptime(stamp, "%Y-%m-%d"))


def _fig(figure):
    return json.loads(figure.to_json())


def figures(snap, colors):
    """Every figure the page draws, keyed by the `data-fig` of the element it goes in."""
    out = {}
    if snap.fomo is not None:
        out[FOMO_KEY] = _fig(view.fomo_figure(snap.fomo, colors))
    if snap.credit is not None:
        out[CREDIT_KEY] = _fig(view.trend_figure(snap.credit))
    if snap.rotation is not None:
        out[ROTATION_KEY] = _fig(view.trend_figure(snap.rotation))
    for row in snap.assets:
        out[SPARK_PREFIX + row.symbol] = _fig(view.spark_figure(row, colors))
    return out


# ── pieces ────────────────────────────────────────────────────────────────────

def _plot(key, cls="plot"):
    return f'<div class="{cls}" data-fig="{_esc(key)}"></div>'


def _badge(text, verdict, colors):
    color = view.verdict_color(verdict, colors)
    return (f'<span class="badge" style="color:{color};'
            f'background:{plot_colors.hex_to_rgba(color, 0.14)};'
            f'border-color:{plot_colors.hex_to_rgba(color, 0.35)}">{_esc(text)}</span>')


def _card(title, *body):
    return f'<section class="card"><h2>{_esc(title)}</h2>\n' + "\n".join(body) + '</section>\n'


def _detail(text, cls="detail"):
    return f'<div class="{cls}">{_esc(text)}</div>'


def _awaiting_card(title, symbols):
    return _card(title, _detail(view.awaiting_text(symbols)))


def _split_bar(left_pct, colors, cls="bar"):
    return (f'<div class="{cls}">'
            f'<i style="width:{left_pct:.1f}%;background:{colors.bull}"></i>'
            f'<i style="width:{100 - left_pct:.1f}%;background:{colors.bear}"></i></div>')


# ── cards, in the app page's order ────────────────────────────────────────────

def fomo_card(read, colors):
    if read is None:
        return _awaiting_card(view.FOMO_TITLE, [mi.FOMO_SYMBOL])
    change = view.verdict_color(mi.POSITIVE if read.change >= 0 else mi.NEGATIVE, colors)
    return _card(
        view.FOMO_TITLE,
        f'<div class="row"><span class="big">{read.value:.1f}</span>'
        f'{_badge(read.label, read.verdict, colors)}'
        f'<span class="detail push" style="color:{change}">'
        f'{_esc(view.signed(read.change, ".1f"))} on the day</span></div>',
        _plot(FOMO_KEY),
        f'<div class="detail between"><span>{_esc(view.FOMO_SPAN)}</span>'
        f'<span>{_esc(view.FOMO_ZONES)}</span></div>',
    )


_ARROWS = {1: "▲", -1: "▼", 0: "•"}


def _net_highs_row(read, colors):
    color = view.verdict_color(read.verdict, colors)
    ink = {1: colors.bull, -1: colors.bear, 0: vc.TEXT_COLOR}
    arrows = "".join(f'<span style="color:{ink[s]}">{_ARROWS[s]}</span> '
                     for s in read.last_three)
    edge = color if read.regime else "transparent"
    return (f'<div class="between nh" style="border-left-color:{edge}"><div>'
            f'<div class="name">{_esc(read.exchange)}</div>'
            f'{_detail(f"{read.highs} highs, {read.lows} lows")}'
            f'<div>{arrows}</div></div>'
            f'<div class="right"><div class="big" style="color:{color}">'
            f'{_esc(view.signed(read.net, "d"))}</div>'
            f'<div class="gap">{_badge(read.label, read.verdict, colors)}</div></div></div>')


def net_highs_card(reads, awaiting, colors):
    rows = [_net_highs_row(r, colors) for r in reads]
    missing = view.net_highs_awaiting(awaiting)
    if missing:
        rows.append(_detail(view.awaiting_text(missing)))
    return _card(view.NET_HIGHS_TITLE, *rows)


def advance_decline_card(read, colors):
    if read is None:
        return _awaiting_card(view.ADVANCE_DECLINE_TITLE,
                              [mi.ADVANCING_SYMBOL, mi.DECLINING_SYMBOL])
    share = read.share * 100
    return _card(
        view.ADVANCE_DECLINE_TITLE,
        _split_bar(share, colors, "bar round"),
        f'<div class="between"><span style="color:{colors.bull}">{share:.0f}% advancing</span>'
        f'{_badge(read.label, read.verdict, colors)}'
        f'<span style="color:{colors.bear}">{100 - share:.0f}% declining</span></div>',
        _detail(f"{read.advancing:,} up, {read.declining:,} down"),
    )


def trend_card(read, title, key, value_fmt, detail, awaiting_symbols, colors):
    if read is None:
        return _awaiting_card(title, awaiting_symbols)
    line, average = view.trend_key(read)
    return _card(
        title,
        f'<div class="row"><span class="big">{format(read.value, value_fmt)}</span>'
        f'<span class="push">{_badge(read.label, read.verdict, colors)}</span></div>',
        _detail(detail(read)),
        _plot(key),
        f'<div class="detail"><span class="key">{_esc(line)}</span>'
        f'<span style="color:{view.AVERAGE_COLOR}">{_esc(average)}</span></div>',
    )


def _updown_row(read, colors):
    color = view.verdict_color(read.verdict, colors)
    total = read.up_days + read.down_days
    up_share = read.up_days / total * 100 if total else 50
    return (f'<div class="ud"><div class="between"><span class="name">{_esc(read.symbol)}</span>'
            f'<span class="big mid" style="color:{color}">{read.ratio:.2f}</span></div>'
            f'{_split_bar(up_share, colors, "bar thin")}'
            f'<div class="detail between"><span>{read.up_days} up days vs '
            f'{read.down_days} down</span>{_badge(read.label, read.verdict, colors)}</div></div>')


def updown_card(reads, awaiting, colors):
    rows = [_updown_row(r, colors) for r in reads]
    missing = [s for s in mi.UPDOWN_SYMBOLS if s in awaiting]
    if missing:
        rows.append(_detail(view.awaiting_text(missing)))
    if reads:
        rows.append(_detail(view.updown_foot(reads), "detail small"))
    return _card(view.UPDOWN_TITLE, *rows)


def asset_table(rows, awaiting, colors):
    head = "".join(f"<th>{_esc(h)}</th>" for h in view.ASSET_COLUMNS)
    body = []
    for row in rows:
        day = colors.bull if row.day_change >= 0 else colors.bear
        body.append(
            f'<tr><td class="name sym">{_esc(row.symbol)}</td>'
            f'<td class="name num">{row.last:,.2f}</td>'
            f'<td class="num" style="color:{day}">{_esc(view.pct(row.day_change))}</td>'
            f'<td class="num">{_plot(SPARK_PREFIX + row.symbol, "spark")}</td></tr>')
    for symbol in (s for s in mi.ASSET_SYMBOLS if s in awaiting):
        body.append(f'<tr><td>{_esc(symbol)}</td>'
                    f'<td colspan="3" class="detail">awaiting data</td></tr>')
    return _card(view.ASSETS_TITLE,
                 f'<table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>')


# ── the page ──────────────────────────────────────────────────────────────────

def _nav():
    links = []
    for name, url in surveys.SITES:
        current = ' aria-current="page"' if name == CURRENT else ""
        links.append(f'<a href="{url}"{current}>{name}</a>')
        if surveys.SOON and name == surveys.SOON_AFTER:
            links.append(f'<span class="soon" title="{_esc(surveys.SOON[1])}">'
                         f'{_esc(surveys.SOON[0])} <small>soon</small></span>')
    return ('<nav class="sites" aria-label="Monitors"><span class="sep">Monitors</span>'
            + "".join(links)
            + f'<a class="home" href="{surveys.HOME}">COT Analyzer &rarr;</a></nav>')


def _header(snap):
    return ('<header class="top"><div>'
            f'<div class="eyebrow">{_esc(EYEBROW)}</div>'
            f'<h1><span class="tk">{_esc(H1_TICKER)}</span> {_esc(H1_REST)}</h1>'
            f'</div><div class="asof">Through <b>{_date(snap.date)}</b></div></header>')


def _headline(snap, colors):
    lean, count = mi.headline(snap)
    return (f'<div class="lean"><span>{_esc(lean)}</span> '
            f'<span style="color:{view.headline_color(lean, colors)}">{_esc(count)}</span></div>'
            f'<div class="detail summary">{_esc("; ".join(mi.summary_sentences(snap)))}</div>')


def render(snap, colors, generated_at=None):
    """The page for `snap` (`market_internals.build_snapshot()`).

    Raises ValueError when the snapshot holds no read at all, so a store that could not
    be read never replaces the published page with six "awaiting data" cards. A snapshot
    missing SOME reads still renders, with the missing ones named: that is the app
    page's own rule for a series that has not been delivered yet.
    """
    if snap.date is None or not any(v is not None for v in mi.read_verdicts(snap)):
        raise ValueError("the snapshot holds no reads"
                         + (f" (awaiting {', '.join(snap.awaiting)})" if snap.awaiting else ""))
    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    left = (fomo_card(snap.fomo, colors)
            + net_highs_card(snap.net_highs, snap.awaiting, colors)
            + advance_decline_card(snap.advance_decline, colors))
    middle = (trend_card(snap.credit, view.CREDIT_TITLE, CREDIT_KEY, ".2f",
                         view.credit_detail, [mi.CREDIT_SYMBOL], colors)
              + trend_card(snap.rotation, view.ROTATION_TITLE, ROTATION_KEY, ".4f",
                           view.rotation_detail, [mi.ROTATION_NUMER, mi.ROTATION_DENOM],
                           colors))
    right = (asset_table(snap.assets, snap.awaiting, colors)
             + updown_card(snap.updown, snap.awaiting, colors))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(TITLE)}</title>
<meta name="description" content="{_esc(DESCRIPTION)}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap">
<style>
:root {{ --page: {vc.BACKGROUND_COLOR}; --ink: {vc.BRIGHTER_TEXT_COLOR}; --ink-2: {vc.TEXT_COLOR};
  --muted: #7d8794; --line: rgba(255,255,255,0.10); --surface: rgba(28,28,28,0.55);
  --wash: rgba(255,255,255,0.06); --ticker: {surveys.TICKER_COLOR};
  --sans: "Public Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace; }}
html, body {{ background: var(--page); color: var(--ink-2); margin: 0; font-family: var(--sans); }}
main {{ max-width: 1400px; margin: 0 auto; padding: 16px; }}
/* The monitors' header, rule for rule as on the surveys page (sentiment_static). */
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
.eyebrow {{ font-size: 11px; letter-spacing: .09em; text-transform: uppercase; color: var(--muted); font-weight: 600; }}
h1 {{ color: var(--ink); margin: 2px 0 0; font-size: 26px; line-height: 1.15; font-weight: 700; letter-spacing: -.01em; }}
h1 .tk {{ font-family: var(--mono); font-weight: 600; color: var(--ticker); }}
.asof {{ color: var(--ink-2); font-size: 13px; text-align: right; }}
.asof b {{ color: var(--ink); font-weight: 600; }}
@media (max-width: 600px) {{ nav.sites .home {{ margin-left: 0; }} .asof {{ text-align: left; }} }}
/* The cards: the app page's three columns (3, 6 and 3 of 12) from 1200px, one column
   below. Not the old app page's 992px: a quarter of that is 230px, narrower than the ETF table
   (measured 2026-11-11), so the side columns also hold a 300px floor. */
.lean {{ color: var(--ink); font-size: 1.5rem; font-weight: 500; }}
.summary {{ margin-bottom: 16px; }}
.cols {{ display: grid; grid-template-columns: minmax(0, 1fr); gap: 0 16px; }}
@media (min-width: 1200px) {{ .cols {{ grid-template-columns: minmax(300px, 1fr) minmax(0, 2fr) minmax(300px, 1fr); }} }}
.card {{ background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 16px; margin-bottom: 16px; }}
.card h2 {{ color: var(--ink-2); font-size: 0.85rem; font-weight: 400; margin: 0 0 0.4rem; }}
.big {{ color: var(--ink); font-size: 1.9rem; font-weight: 600; line-height: 1.1; }}
.big.mid {{ font-size: 1.4rem; }}
.detail {{ font-size: 0.8rem; }}
.detail.small {{ font-size: 0.72rem; }}
.name {{ color: var(--ink); }}
.row {{ display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; }}
.between {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 4px 8px; }}
.push {{ margin-left: auto; }}
.right {{ text-align: right; }}
.gap {{ margin-top: 4px; }}
.key {{ margin-right: 12px; }}
.badge {{ border: 1px solid; border-radius: 4px; padding: 2px 8px; font-size: 0.8rem; font-weight: 600; white-space: nowrap; }}
.nh {{ border-left: 3px solid transparent; padding-left: 8px; margin-bottom: 16px; align-items: flex-start; }}
.ud {{ margin-bottom: 16px; }}
.bar {{ display: flex; margin-bottom: 8px; }}
.bar i {{ display: block; height: 8px; }}
.bar.round i:first-child {{ border-radius: 4px 0 0 4px; }}
.bar.round i:last-child {{ border-radius: 0 4px 4px 0; }}
.bar.thin {{ margin: 4px 0; }}
.bar.thin i {{ height: 6px; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ font-size: 0.8rem; font-weight: 400; text-align: left; border-bottom: 1px solid var(--line); padding: 2px 0; }}
th:not(:first-child), td.num {{ text-align: right; }}
td {{ border-bottom: 1px solid var(--wash); padding: 2px 0; }}
td.sym {{ font-weight: 600; }}
.spark {{ display: inline-block; width: {view.SPARK_WIDTH}px; height: {view.SPARK_HEIGHT}px; vertical-align: middle; }}
.notes {{ font-size: 0.75rem; line-height: 1.45; }}
footer {{ color: var(--muted); font-size: 0.8rem; line-height: 1.45; border-top: 1px solid var(--line); margin-top: 18px; padding-top: 10px; }}
</style>
<script src="{surveys.plotly_js_url()}" charset="utf-8"></script>
</head>
<body>
<main>
{_nav()}
{_header(snap)}
{_headline(snap, colors)}
<div class="cols">
<div>{left}</div>
<div>{middle}</div>
<div>{right}</div>
</div>
<div class="notes">{_esc(view.caption(snap))}</div>
<footer>{_esc(SOURCES)}</footer>
</main>
<script>window.INTERNALS_META={{"generated_at":"{_esc(stamp)}"}};</script>
<script type="application/json" id="{DATA_ID}">{surveys._script_json(figures(snap, colors))}</script>
<script>
(function () {{
  var DATA = JSON.parse(document.getElementById('{DATA_ID}').textContent);
  var CONFIG = {{displayModeBar: false, responsive: true, staticPlot: true}};
  document.querySelectorAll('[data-fig]').forEach(function (el) {{
    var fig = DATA[el.dataset.fig];
    if (fig) {{ Plotly.newPlot(el, fig.data, fig.layout, CONFIG); }}
  }});
}})();
</script>
</body>
</html>
"""


def write(path, snap, colors, **kw):
    """Render and write with LF line ends, the bytes publish_pages compares."""
    Path(path).write_text(render(snap, colors, **kw), encoding="utf-8", newline="")
