"""The market internals page as one self-contained HTML file, internals.bluemagicai.com.

What was the app's `/internals` page until 2026-11-11 (that path now 301s here): the
snapshot (`components.market_internals`) and the titles, texts and chart data
(`components.market_internals_view`), published the way the surveys page is:
`scripts/export_internals_page.py` writes the file and dbmf-tracker's
`deploy/publish_pages.py --key internals` pushes it to a GitHub Pages repo of its own
(docs/internals-publishing.md).

**It is the surveys page's sibling, and looks it** (since 2026-11-15). The stylesheet
opens with `sentiment_static.base_css()`, the same tokens, header, readings tiles and
cards, and the page follows that page's order: the monitors row and header, a strip of
tiles with each read's number and word, then cards that open on one sentence with the
rest behind "How to read this". Before that it kept the old app page's colours, width
and three-column layout, and sat beside the surveys page as a different site.

**Charts are TradingView's Lightweight Charts**, loaded from unpkg at a pinned version
(`LIGHTWEIGHT_CHARTS_VERSION`), drawn from the plain series `market_internals_view`
embeds as JSON. Scroll and zoom are off (a quarter or a year is the whole series, and a
chart that pans steals the page's scroll on a phone); the crosshair is what the library
is here for, the value and date under the cursor. Its licence (Apache 2.0) asks for the
attribution notice and a link to tradingview.com on the page: both are in the footer
(`ATTRIBUTION`), which is why the per-chart logo is switched off. The table's
sparklines are inline SVG, nine charts not worth nine chart instances.

`generated_at` is written as `"generated_at":"..."` on purpose: publish_pages masks
that exact spelling when deciding whether anything changed, so a rebuild with no new
data pushes nothing. For the same reason no build time is visible on the page; the
as-of is the newest session the reads carry.
"""
from __future__ import annotations

import html
import types
from datetime import datetime, timezone
from pathlib import Path

import components.market_internals as mi
import components.market_internals_view as view
from components import plot_colors, sentiment
from components import sentiment_static as surveys

TITLE = "Market Internals"
EYEBROW = "Breadth · credit · rotation · volume · daily"
H1_TICKER, H1_REST = "Market", "internals"
DESCRIPTION = ("Six daily reads of the tape on one page: Nasdaq FOMO, net new 52-week "
               "highs, advancing against declining issues, high-yield credit against its "
               "20-day average, staples over Nasdaq against its 50-day, and 20-session "
               "up/down volume, with a junk-against-Treasuries credit gauge and an ETF "
               "table.")
#: This page's name in the monitors row (`sentiment_static.SITES`, the one list).
CURRENT = "Market"
SOURCES = ("Sources: TradingView daily breadth series (Nasdaq and NYSE), "
           "ETF daily bars from Yahoo Finance.")
#: The chart library, pinned: an exact release, never `latest`, so a publish cannot
#: change how the page draws. 5.2.1 (2026-08-12) is the release before the newest.
LIGHTWEIGHT_CHARTS_VERSION = "5.2.1"
#: The library's NOTICE file, and the link its licence asks for beside it.
ATTRIBUTION = "TradingView Lightweight Charts™ Copyright (с) 2025 TradingView, Inc."
ATTRIBUTION_URL = "https://www.tradingview.com/"

DATA_ID = "internals-data"
READINGS_ID = "readings"
#: Payload keys of the four charts, each the `data-chart` of the element it draws in.
FOMO_KEY, APPETITE_KEY, CREDIT_KEY, ROTATION_KEY = "fomo", "appetite", "credit", "rotation"

_esc = html.escape


def lightweight_charts_url():
    return (f"https://unpkg.com/lightweight-charts@{LIGHTWEIGHT_CHARTS_VERSION}"
            "/dist/lightweight-charts.standalone.production.js")


def page_colors(colors):
    """The verdict pair as this family of pages draws it: the palette's green and red,
    toned down by the surveys cards' own step, so the two pages have one green."""
    return types.SimpleNamespace(bull=sentiment.card_green(colors),
                                 bear=sentiment.card_red(colors))


def _date(stamp):
    """Nov 6, 2026 from the snapshot's 2026-11-06, the monitors' date spelling."""
    return surveys._date(datetime.strptime(stamp, "%Y-%m-%d"))


def charts(snap, colors):
    """Every chart the page draws, keyed by the `data-chart` of its element."""
    out = {}
    if snap.fomo is not None:
        out[FOMO_KEY] = view.fomo_chart(snap.fomo, colors)
    if snap.appetite is not None:
        out[APPETITE_KEY] = view.appetite_chart(snap.appetite, colors)
    if snap.credit is not None:
        out[CREDIT_KEY] = view.trend_chart(snap.credit)
    if snap.rotation is not None:
        out[ROTATION_KEY] = view.trend_chart(snap.rotation)
    return out


# ── pieces ────────────────────────────────────────────────────────────────────

def _chart(key, spec_height):
    return f'<div class="chart" data-chart="{_esc(key)}" style="height:{spec_height}px"></div>'


def _badge(text, verdict, colors):
    color = view.verdict_color(verdict, colors)
    return (f'<span class="badge" style="color:{color};'
            f'background:{plot_colors.hex_to_rgba(color, 0.14)};'
            f'border-color:{plot_colors.hex_to_rgba(color, 0.35)}">{_esc(text)}</span>')


def _card(title, subtitle, how, *body):
    """A card as the surveys page builds one: title, one sentence, the rest closed."""
    head = surveys._sub(subtitle, how) if subtitle else ""
    return (f'<section class="card"><h2>{_esc(title)}</h2>\n{head}'
            + "\n".join(body) + '</section>\n')


def _detail(text, cls="detail"):
    return f'<div class="{cls}">{_esc(text)}</div>'


def _awaiting(symbols):
    return _detail(view.awaiting_text(symbols))


def _split_bar(left_pct, colors, cls="bar"):
    return (f'<div class="{cls}">'
            f'<i style="width:{left_pct:.1f}%;background:{colors.bull}"></i>'
            f'<i style="width:{100 - left_pct:.1f}%;background:{colors.bear}"></i></div>')


def _tiles(tiles):
    """The readings strip, in the surveys tiles' markup (label, value, gauge where the
    read is a 0-100 scale, the read's word, context, date). The word and the left edge
    take the tile's tone; values stay in the page's ink."""
    out = []
    for t in tiles:
        gauge = (f'<div class="gauge" aria-hidden="true"><i style="left:{t["gauge"]:.0f}%">'
                 '</i></div>' if t["gauge"] is not None else "")
        out.append(f'<div class="tile {t["tone"]}" data-key="{_esc(t["key"])}">'
                   f'<div class="head"><div class="label">{_esc(t["label"])}</div></div>'
                   f'<div class="value">{_esc(t["value"])}</div>{gauge}'
                   f'<div class="tier">{_esc(t["state"])}</div>'
                   f'<div class="ctx">{_esc(t["context"])}</div>'
                   f'<div class="foot">{_esc(_date(t["date"]))}</div></div>')
    return (f'<div class="tiles" id="{READINGS_ID}" role="group" aria-label="Latest readings">'
            + "".join(out) + '</div>\n')


# ── cards ─────────────────────────────────────────────────────────────────────

def fomo_card(read, colors):
    if read is None:
        return _card(view.FOMO_TITLE, None, None, _awaiting([mi.FOMO_SYMBOL]))
    change = view.verdict_color(mi.POSITIVE if read.change >= 0 else mi.NEGATIVE, colors)
    return _card(
        view.FOMO_TITLE, view.FOMO_SUBTITLE, view.FOMO_HOW,
        f'<div class="row"><span class="big">{read.value:.1f}</span>'
        f'{_badge(read.label, read.verdict, colors)}'
        f'<span class="detail push" style="color:{change}">'
        f'{_esc(view.signed(read.change, ".1f"))} on the day</span></div>',
        _chart(FOMO_KEY, view.fomo_chart(read, colors)["height"]),
        _detail(view.FOMO_ZONES),
    )


def appetite_card(read, credit, colors):
    if read is None:
        return _card(view.APPETITE_TITLE, None, None,
                     _awaiting([mi.APPETITE_JUNK, mi.APPETITE_TREASURY]))
    change = view.verdict_color(mi.POSITIVE if read.change >= 0 else mi.NEGATIVE, colors)
    return _card(
        view.APPETITE_TITLE, view.APPETITE_SUBTITLE, view.APPETITE_HOW,
        f'<div class="row"><span class="big">{read.value:.0f}</span>'
        f'{_badge(read.label, read.tone, colors)}'
        f'<span class="detail push" style="color:{change}">'
        f'{_esc(view.signed(read.change, ".0f"))} on the day</span></div>',
        _chart(APPETITE_KEY, view.appetite_chart(read, colors)["height"]),
        _detail(view.appetite_status(read, credit)),
    )


def trend_card(read, title, subtitle, how, key, value_fmt, detail, awaiting_symbols, colors):
    if read is None:
        return _card(title, None, None, _awaiting(awaiting_symbols))
    line, average = view.trend_key(read)
    return _card(
        title, subtitle, how,
        f'<div class="row"><span class="big">{format(read.value, value_fmt)}</span>'
        f'<span class="push">{_badge(read.label, read.verdict, colors)}</span></div>',
        _detail(detail(read)),
        _chart(key, view.trend_chart(read)["height"]),
        f'<div class="detail"><span class="key">{_esc(line)}</span>'
        f'<span style="color:{view.AVERAGE_COLOR}">{_esc(average)}</span></div>',
    )


_ARROWS = {1: "▲", -1: "▼", 0: "•"}


def _net_highs_row(read, colors):
    color = view.verdict_color(read.verdict, colors)
    ink = {1: colors.bull, -1: colors.bear, 0: surveys.INK_2}
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


def breadth_card(snap, colors):
    """Net new highs on both exchanges, and the session's advancing share under them."""
    rows = [_net_highs_row(r, colors) for r in snap.net_highs]
    missing = view.net_highs_awaiting(snap.awaiting)
    if missing:
        rows.append(_awaiting(missing))
    rows.append(f'<h3>{_esc(view.ADVANCE_DECLINE_TITLE)}</h3>')
    read = snap.advance_decline
    if read is None:
        rows.append(_awaiting([mi.ADVANCING_SYMBOL, mi.DECLINING_SYMBOL]))
    else:
        share = read.share * 100
        rows += [
            _split_bar(share, colors, "bar round"),
            f'<div class="between"><span style="color:{colors.bull}">{share:.0f}% advancing'
            f'</span>{_badge(read.label, read.verdict, colors)}'
            f'<span style="color:{colors.bear}">{100 - share:.0f}% declining</span></div>',
            _detail(f"{read.advancing:,} up, {read.declining:,} down"),
        ]
    return _card(view.NET_HIGHS_TITLE, view.NET_HIGHS_SUBTITLE, view.NET_HIGHS_HOW, *rows)


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
        rows.append(_awaiting(missing))
    if reads:
        rows.append(_detail(view.updown_foot(reads), "detail small"))
    return _card(view.UPDOWN_TITLE, view.UPDOWN_SUBTITLE, view.UPDOWN_HOW, *rows)


def _spark(row, colors):
    color = colors.bull if row.quarter_change >= 0 else colors.bear
    return (f'<svg class="spark" viewBox="0 0 {view.SPARK_WIDTH} {view.SPARK_HEIGHT}" '
            f'width="{view.SPARK_WIDTH}" height="{view.SPARK_HEIGHT}" role="img" '
            f'aria-label="{_esc(row.symbol)}, {_esc(view.pct(row.quarter_change))} over '
            f'three months"><polyline fill="none" stroke="{color}" stroke-width="1.2" '
            f'points="{view.spark_points(row)}"/></svg>')


def asset_table(rows, awaiting, colors):
    head = "".join(f"<th>{_esc(h)}</th>" for h in view.ASSET_COLUMNS)
    body = []
    for row in rows:
        day = colors.bull if row.day_change >= 0 else colors.bear
        body.append(
            f'<tr><td class="name sym">{_esc(row.symbol)}</td>'
            f'<td class="name num">{row.last:,.2f}</td>'
            f'<td class="num" style="color:{day}">{_esc(view.pct(row.day_change))}</td>'
            f'<td class="num">{_spark(row, colors)}</td></tr>')
    for symbol in (s for s in mi.ASSET_SYMBOLS if s in awaiting):
        body.append(f'<tr><td>{_esc(symbol)}</td>'
                    f'<td colspan="3" class="detail">awaiting data</td></tr>')
    return _card(view.ASSETS_TITLE, None, None,
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
    return (f'<p class="lean">{_esc(lean)} '
            f'<b style="color:{view.headline_color(lean, colors)}">{_esc(count)}</b></p>')


def render(snap, colors, generated_at=None):
    """The page for `snap` (`market_internals.build_snapshot()`); `colors` is the
    palette's verdict pair (`plot_colors.grid_colors`), toned here by `page_colors`.

    Raises ValueError when the snapshot holds no read at all, so a store that could not
    be read never replaces the published page with a row of "awaiting data" cards. A
    snapshot missing SOME reads still renders, with the missing ones named: the page's
    rule for a series that has not been delivered yet.
    """
    if snap.date is None or not any(v is not None for v in mi.read_verdicts(snap)):
        raise ValueError("the snapshot holds no reads"
                         + (f" (awaiting {', '.join(snap.awaiting)})" if snap.awaiting else ""))
    colors = page_colors(colors)
    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    gauges = fomo_card(snap.fomo, colors) + appetite_card(snap.appetite, snap.credit, colors)
    trends = (trend_card(snap.credit, view.CREDIT_TITLE, view.CREDIT_SUBTITLE,
                         view.CREDIT_HOW, CREDIT_KEY, ".2f", view.credit_detail,
                         [mi.CREDIT_SYMBOL], colors)
              + trend_card(snap.rotation, view.ROTATION_TITLE, view.ROTATION_SUBTITLE,
                           view.ROTATION_HOW, ROTATION_KEY, ".4f", view.rotation_detail,
                           [mi.ROTATION_NUMER, mi.ROTATION_DENOM], colors))
    counts = (breadth_card(snap, colors)
              + updown_card(snap.updown, snap.awaiting, colors)
              + asset_table(snap.assets, snap.awaiting, colors))
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
{surveys.base_css()}/* This page's own rules, on the shared tokens above. A tile's tone is its read's side:
   the constructive green, the defensive red (the surveys cards' toned pair), or none. */
.tile.pos {{ --tone: {colors.bull}; }}
.tile.neg {{ --tone: {colors.bear}; }}
.tile.mid {{ border-left-color: var(--line); }}
.tile.mid .tier {{ color: var(--ink); }}
.tile.mid .gauge i {{ background: var(--ink-2); }}
.lean {{ color: var(--ink); font-size: 1.05rem; font-weight: 500; margin: 0 0 10px; }}
.lean b {{ font-weight: 600; }}
/* Cards two across from 900px (the two gauges, then the two trend charts), and the
   three without a time axis three across from 1100px; one column on a phone. */
.cards {{ display: grid; grid-template-columns: minmax(0, 1fr); gap: 0 12px; align-items: start; }}
@media (min-width: 900px) {{ .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
@media (min-width: 1100px) {{ .cards.three {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }} }}
.card h3 {{ color: var(--ink); font-size: 0.85rem; font-weight: 400; margin: 14px 0 8px; padding-top: 12px; border-top: 1px solid var(--line); }}
.chart {{ width: 100%; margin: 6px 0 4px; }}
.big {{ color: var(--ink); font-size: 1.75rem; font-weight: 600; line-height: 1.2; }}
.big.mid {{ font-size: 1.3rem; }}
.detail {{ font-size: 0.8rem; }}
.detail.small {{ font-size: 0.72rem; color: var(--muted); }}
.name {{ color: var(--ink); }}
.row {{ display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; margin-top: 4px; }}
.between {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 4px 8px; }}
.push {{ margin-left: auto; }}
.right {{ text-align: right; }}
.gap {{ margin-top: 4px; }}
.key {{ margin-right: 12px; }}
.badge {{ border: 1px solid; border-radius: 4px; padding: 2px 8px; font-size: 0.8rem; font-weight: 600; white-space: nowrap; }}
.nh {{ border-left: 3px solid transparent; padding-left: 8px; margin: 8px 0 14px; align-items: flex-start; }}
.ud {{ margin: 8px 0 14px; }}
.bar {{ display: flex; margin-bottom: 8px; }}
.bar i {{ display: block; height: 8px; }}
.bar.round i:first-child {{ border-radius: 4px 0 0 4px; }}
.bar.round i:last-child {{ border-radius: 0 4px 4px 0; }}
.bar.thin {{ margin: 4px 0; }}
.bar.thin i {{ height: 6px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
th {{ font-size: 0.8rem; font-weight: 400; text-align: left; border-bottom: 1px solid var(--line); padding: 2px 0; }}
th:not(:first-child), td.num {{ text-align: right; }}
td {{ border-bottom: 1px solid var(--wash); padding: 3px 0; }}
td.sym {{ font-weight: 600; }}
.spark {{ vertical-align: middle; }}
.notes p, footer {{ font-size: 0.8rem; line-height: 1.45; }}
footer {{ color: var(--muted); border-top: 1px solid var(--line); margin-top: 18px; padding-top: 10px; }}
footer a {{ color: var(--ink-2); }}
</style>
<script src="{lightweight_charts_url()}" charset="utf-8"></script>
</head>
<body>
<main>
{_nav()}
{_header(snap)}
{_headline(snap, colors)}
{_tiles(view.tiles(snap))}<div class="cards">
{gauges}</div>
<div class="cards">
{trends}</div>
<div class="cards three">
{counts}</div>
<div class="notes"><p>{_esc(view.caption(snap))}</p></div>
<footer>{_esc(SOURCES)} Charts: <a href="{ATTRIBUTION_URL}" rel="noopener">{_esc(ATTRIBUTION)}</a></footer>
</main>
<script>window.INTERNALS_META={{"generated_at":"{_esc(stamp)}"}};</script>
<script type="application/json" id="{DATA_ID}">{surveys._script_json(charts(snap, colors))}</script>
<script>
(function () {{
  var LC = window.LightweightCharts;
  if (!LC) {{ return; }}
  var DATA = JSON.parse(document.getElementById('{DATA_ID}').textContent);
  var INK = '{surveys.INK_2}', GRID = 'rgba(255,255,255,0.06)';
  document.querySelectorAll('[data-chart]').forEach(function (el) {{
    var spec = DATA[el.dataset.chart];
    if (!spec) {{ return; }}
    var format = {{type: 'price', precision: spec.decimals, minMove: Math.pow(10, -spec.decimals)}};
    var chart = LC.createChart(el, {{
      autoSize: true,
      layout: {{background: {{type: 'solid', color: 'transparent'}}, textColor: INK,
               fontSize: 10, fontFamily: getComputedStyle(document.body).fontFamily,
               attributionLogo: false}},
      grid: {{vertLines: {{visible: false}}, horzLines: {{color: GRID}}}},
      // A fixed 0-100 scale keeps thin margins, or the axis runs on to 120.
      rightPriceScale: {{borderVisible: false,
                        scaleMargins: spec.range ? {{top: 0.04, bottom: 0.04}} : {{top: 0.12, bottom: 0.1}}}},
      timeScale: {{borderVisible: false, fixLeftEdge: true, fixRightEdge: true}},
      // The whole series is on screen; panning would only take the page's scroll.
      handleScroll: false, handleScale: false,
      crosshair: {{mode: LC.CrosshairMode.Magnet}}
    }});
    var first = null;
    spec.series.forEach(function (s) {{
      var options = {{color: s.color, lineWidth: s.width, priceFormat: format,
                     priceLineVisible: false, lastValueVisible: false}};
      if (spec.range) {{
        options.autoscaleInfoProvider = function () {{
          return {{priceRange: {{minValue: spec.range[0], maxValue: spec.range[1]}}}};
        }};
      }}
      var line = chart.addSeries(LC.LineSeries, options);
      line.setData(s.data);
      first = first || line;
    }});
    if (!first) {{ return; }}
    spec.levels.forEach(function (level) {{
      first.createPriceLine({{price: level.value, color: level.color, lineWidth: 1,
                             lineStyle: LC.LineStyle.Dashed, axisLabelVisible: true, title: ''}});
    }});
    if (spec.markers.length) {{
      LC.createSeriesMarkers(first, spec.markers.map(function (m) {{
        return {{time: m.time, position: 'inBar', shape: 'circle', color: m.color, size: 1}};
      }}));
    }}
    chart.timeScale().fitContent();
  }});
}})();
</script>
</body>
</html>
"""


def write(path, snap, colors, **kw):
    """Render and write with LF line ends, the bytes publish_pages compares."""
    Path(path).write_text(render(snap, colors, **kw), encoding="utf-8", newline="")
