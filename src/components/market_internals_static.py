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
from components import board_traces, plot_colors, sentiment
from components import sentiment_static as surveys

TITLE = "Market Internals"
EYEBROW = "Breadth · credit · rotation · volume · daily"
H1_TICKER, H1_REST = "Market", "internals"
DESCRIPTION = ("Six market headwinds, daily: Nasdaq and NYSE net new 52-week highs, QQQ and SPY up/down "
               "volume, high-yield credit's 20-day EMA, and staples over Nasdaq against "
               "its 50-day, each with what would flip it. Beside them, Nasdaq FOMO, a "
               "junk-against-Treasuries credit gauge, the day's breadth and an ETF table.")
#: This page's name in the monitors row (`sentiment_static.SITES`, the one list).
CURRENT = "Market"
SURVEYS_URL = dict(surveys.SITES)["Surveys"]
#: Where the page is served, for the canonical link and a shared link's preview. No
#: preview image: the page publishes one HTML file and no assets.
URL = dict(surveys.SITES)[CURRENT]
SITE_NAME = "Blue Magic AI monitors"
BREADTH_ID = "breadth"
#: Every source a section of the page draws on, not only the breadth and the bars: the
#: line named two of them until 2026-11-19, after volatility, the surveys and the COT
#: had joined the page.
SOURCES = ("Sources: TradingView daily breadth series (Nasdaq and NYSE); ETF daily bars "
           "from Yahoo Finance; volatility indices (VIX, VIX3M, VXN, ICE BofA MOVE) from "
           "Cboe and Yahoo Finance; NAAIM Exposure Index; AAII sentiment and asset "
           "allocation surveys; CFTC Commitments of Traders.")
#: The chart library, pinned: an exact release, never `latest`, so a publish cannot
#: change how the page draws. 5.2.1 (2026-08-12) is the release before the newest.
LIGHTWEIGHT_CHARTS_VERSION = "5.2.1"
#: The library's NOTICE file, and the link its licence asks for beside it.
ATTRIBUTION = "TradingView Lightweight Charts™ Copyright (с) 2025 TradingView, Inc."
ATTRIBUTION_URL = "https://www.tradingview.com/"

DATA_ID = "internals-data"
HEADWINDS_ID = "headwinds"
HISTORY_ID = "history"
POSITIONING_ID = "positioning"
SENTIMENT_ID = "sentiment"
CONTEXT_ID, DETAIL_ID = "context", "detail"
#: A market's commercials chart is POSITIONING_PREFIX + its symbol in the payload.
POSITIONING_PREFIX = "cot:"
#: Payload keys of the charts, each the `data-chart` of the element it draws in. A
#: headwind's is HEADWIND_PREFIX + its key.
FOMO_KEY, APPETITE_KEY, VOLATILITY_KEY = "fomo", "appetite", "volatility"
BOND_VOLATILITY_KEY = "bond_volatility"
HIGHS_LOWS_KEY, NET_HISTORY_KEY = "highs_lows", "net_history"
HEADWIND_PREFIX = "headwind:"

_esc = html.escape


def lightweight_charts_url():
    return (f"https://unpkg.com/lightweight-charts@{LIGHTWEIGHT_CHARTS_VERSION}"
            "/dist/lightweight-charts.standalone.production.js")


def page_colors(colors):
    """The verdict pair as this family of pages draws it: the palette's green and red,
    toned down by the surveys cards' own step, so the two pages have one green."""
    return types.SimpleNamespace(bull=sentiment.card_green(colors),
                                 bear=sentiment.card_red(colors))


def ink_on(fill):
    """Text colour for a number printed on `fill`: `plot_colors.cell_text_colour`'s
    choice (dark on a light fill, bright on a dark one), with the bright one the
    family's white, not the app's cream it returns. The lookback cells printed the
    cream until 2026-11-18: the page's ink test had no positioning on its fixture."""
    ink = plot_colors.cell_text_colour(fill)
    return surveys.INK if ink == plot_colors.INK_BRIGHT else ink


def _date(stamp):
    """Nov 6, 2026 from the snapshot's 2026-11-06, the monitors' date spelling."""
    if not isinstance(stamp, str):          # a survey's date is already a date
        return surveys._date(stamp)
    return surveys._date(datetime.strptime(stamp, "%Y-%m-%d"))


def group_colors(palette=None):
    """The three trader groups' colours: the app palette's first three slots
    (`viz_config.PALETTE_SLOTS`), so a commercial is the red it is on every chart of
    the COT Analyzer."""
    if palette is None:
        import viz_config
        palette = viz_config.get_palette()
    return tuple(palette[:len(view.POSITIONING_GROUPS)])


def charts(snap, colors, positioning=(), groups=None):
    """Every chart the page draws, keyed by the `data-chart` of its element."""
    groups = groups or (group_colors() if positioning else ())
    out = {POSITIONING_PREFIX + r.symbol: view.positioning_chart(r, groups)
           for r in positioning or ()}
    if snap.fomo is not None:
        out[FOMO_KEY] = view.fomo_chart(snap.fomo, colors)
    if snap.appetite is not None:
        out[APPETITE_KEY] = view.appetite_chart(snap.appetite, colors)
    if snap.breadth is not None:
        out[HIGHS_LOWS_KEY] = view.highs_lows_chart(snap.breadth, colors)
        out[NET_HISTORY_KEY] = view.net_highs_chart(snap.breadth, colors)
    if snap.volatility is not None:
        out[VOLATILITY_KEY] = view.volatility_chart(snap.volatility, colors)
        if snap.volatility.bonds is not None:
            out[BOND_VOLATILITY_KEY] = view.bond_volatility_chart(snap.volatility.bonds)
    for h in snap.headwinds:
        out[HEADWIND_PREFIX + h.key] = view.headwind_chart(h, colors)
    return out


# ── pieces ────────────────────────────────────────────────────────────────────

def _chart(key, spec_height):
    return f'<div class="chart" data-chart="{_esc(key)}" style="height:{spec_height}px"></div>'


def _badge(text, verdict, colors):
    color = view.verdict_color(verdict, colors)
    return (f'<span class="badge" style="color:{color};'
            f'background:{plot_colors.hex_to_rgba(color, 0.14)};'
            f'border-color:{plot_colors.hex_to_rgba(color, 0.35)}">{_esc(text)}</span>')


def _how(how):
    """A closed "How to read this": a paragraph, or a tuple of points, one each."""
    if not how:
        return ""
    if isinstance(how, str):
        how = (how,)
    points = "".join(f"<li>{_esc(p)}</li>" for p in how)
    return (f'<details class="how"><summary>{_esc(sentiment.HOW_TO_READ_LABEL)}</summary>'
            f'<ul>{points}</ul></details>\n')


def _sub(subtitle, how=None):
    return f'<div class="sub">{_esc(subtitle)}</div>\n' + _how(how)


def _card(title, subtitle, how, *body):
    """A card as the surveys page builds one: title, one sentence, the rest closed."""
    head = _sub(subtitle, how) if subtitle else ""
    return (f'<section class="card"><h2>{_esc(title)}</h2>\n{head}'
            + "\n".join(body) + '</section>\n')


def _section(title, subtitle, how=None):
    """A section heading over a group of cards: a title, one sentence, the rest closed."""
    return (f'<div class="sec"><h2>{_esc(title)}</h2>\n'
            + _sub(subtitle, how) + '</div>\n')


def _prov(snap, key):
    """The "provisional" chip beside a number that rests on an unconfirmed bar."""
    tag = view.provisional_tag(snap, key)
    return (f'<span class="prov" title="The evening\'s reading, not yet confirmed by the '
            f'vendor; replaced when it settles.">{_esc(tag)}</span>' if tag else "")


def _detail(text, cls="detail"):
    return f'<div class="{cls}">{_esc(text)}</div>'


def _awaiting(symbols):
    return _detail(view.awaiting_text(symbols))


def _split_bar(left_pct, colors, cls="bar"):
    return (f'<div class="{cls}">'
            f'<i style="width:{left_pct:.1f}%;background:{colors.bull}"></i>'
            f'<i style="width:{100 - left_pct:.1f}%;background:{colors.bear}"></i></div>')


# ── cards ─────────────────────────────────────────────────────────────────────

def headwind_card(h, colors, chip="", more=""):
    """One headwind: its name and state, the number, the quarter behind it, what would
    flip it and how long it has stood. The tile's left edge takes the state's colour."""
    tone = colors.bear if h.on else colors.bull
    versus = view.headwind_versus(h)
    versus_tone = colors.bull if h.versus == "better" else colors.bear
    return (
        f'<section class="card hw {"on" if h.on else "off"}" data-key="{_esc(h.key)}">'
        f'<div class="between"><span class="eyebrow">{_esc(h.title)}</span>'
        f'{_badge(view.headwind_badge(h), mi.NEGATIVE if h.on else mi.POSITIVE, colors)}</div>'
        f'<div class="row"><span class="big">{_esc(h.display)}</span>{chip}'
        + (f'<span class="detail" style="color:{versus_tone}">{_esc(versus)}</span>'
           if versus else "")
        + f'</div>{_detail(h.subtitle)}{_how(view.HEADWIND_HOWS.get(h.key))}'
        + _chart(HEADWIND_PREFIX + h.key, view.headwind_chart(h, colors)["height"])
        + _detail(h.flip)
        + f'<div class="detail" style="color:{tone}">{_esc(view.headwind_streak(h))}</div>'
        f'{more}</section>\n')


def _marks(flags, height, fill, opacity=1.0, y=0):
    return "".join(f'<rect x="{start}" y="{y}" width="{length}" height="{height}" '
                   f'fill="{fill}" fill-opacity="{opacity}"/>'
                   for start, length in view.runs(flags))


def history_card(history, colors):
    """The headwinds through time: the price, a strip per headwind, and the sessions
    all of them were on. Inline SVG stretched to the column (rectangles and one line,
    so stretching distorts nothing); the labels and years are HTML, so they stay
    legible on a phone where a scaled SVG's text would not."""
    if history is None:
        return ""
    n = len(history.dates)
    # The headwind cards' own red: a mark here and a card's "Headwind" are one thing.
    mark = colors.bear
    units = view.HISTORY_PRICE_UNITS
    most = [c == history.total - 1 for c in history.count]
    every = [c == history.total for c in history.count]
    tall, top = f"{units * 2:g}", f"{-units / 2:g}"
    fomo_bands = fomo_row = ""
    if history.fomo is not None:
        washed, stretched, first = history.fomo
        cool, warm = surveys.TONE_LOW, surveys.TONE_HIGH
        # Over the price only while the row is on (the script shows the group).
        fomo_bands = (f'<g data-band="fomo" display="none">'
                      f'{_marks(washed, tall, cool, 0.5, y=top)}'
                      f'{_marks(stretched, tall, warm, 0.5, y=top)}</g>')
        unread = (f'<rect x="0" y="0" width="{first}" height="1" fill="{surveys.PAGE_COLOR}" '
                  'fill-opacity="0.75"/>' if first else "")
        fomo_row = (
            f'<button type="button" class="hl htog" data-row="{view.HISTORY_FOMO_KEY}" '
            f'aria-pressed="false">{_esc(view.HISTORY_FOMO_LABEL)}</button>'
            f'<div class="hp off" data-strip="{view.HISTORY_FOMO_KEY}">'
            f'<svg class="hstrip" viewBox="0 0 {n} 1" preserveAspectRatio="none" '
            f'aria-hidden="true">{_marks(washed, 1, cool)}{_marks(stretched, 1, warm)}{unread}'
            '</svg></div>')
    rows = [
        f'<div class="hl">{_esc(history.price_symbol)} (log scale)</div>'
        f'<div class="hp"><svg class="hprice" viewBox="0 0 {n} {units:g}" '
        f'preserveAspectRatio="none" role="img" aria-label="{_esc(history.price_symbol)} '
        f'price with the sessions {history.total - 1} or {history.total} headwinds were on '
        f'shaded">'
        # Taller than the panel: a zoom pads the price's y range past 0 and the units.
        f'<g data-band="most">{_marks(most, tall, mark, 0.18, y=top)}</g>'
        f'<g data-band="every">{_marks(every, tall, mark, 0.45, y=top)}</g>{fomo_bands}'
        f'<polyline fill="none" stroke="{surveys.INK}" stroke-width="1.2" '
        f'vector-effect="non-scaling-stroke" points="{view.history_price_points(history)}"/>'
        '</svg></div>']
    for key, label, flags in history.rows:
        # `data-headwind` marks the rows the count is made of: the script reads each
        # one's runs back off its own rectangles, so the history is embedded once.
        rows.append(f'<button type="button" class="hl htog" data-row="{_esc(key)}" '
                    f'aria-pressed="true">{_esc(label)}</button>'
                    f'<div class="hp" data-strip="{_esc(key)}">'
                    f'<svg class="hstrip" data-row="{_esc(key)}" data-headwind '
                    f'viewBox="0 0 {n} 1" preserveAspectRatio="none" aria-hidden="true">'
                    f'{_marks(flags, 1, mark)}</svg></div>')
    rows.append(f'<div class="hl all" data-all-label>All {history.total} at once</div>'
                '<div class="hp">'
                f'<svg class="hstrip" data-row="all" viewBox="0 0 {n} 1" '
                f'preserveAspectRatio="none" aria-hidden="true">{_marks(every, 1, mark)}'
                '</svg></div>')
    rows.append(fomo_row)
    years = "".join(f'<span style="left:{fraction * 100:.2f}%">{year}</span>'
                    for fraction, year in view.history_year_ticks(history))
    months = _esc(surveys._script_json(view.history_month_starts(history)), quote=True)
    rows.append(f'<div class="hl"></div><div class="hp hyears" data-months="{months}">'
                f'{years}</div>')
    buttons = "".join(
        f'<button type="button" data-sessions="{sessions}" aria-pressed='
        f'"{"true" if label == view.HISTORY_DEFAULT_WINDOW else "false"}">{label}</button>'
        for label, sessions in view.HISTORY_WINDOWS if sessions < n)
    windows = (f'<div class="lookback hwin" role="group" aria-label="History window">'
               f'<span>Window</span>{buttons}</div>'
               # Which sessions the price is shaded on: every row that is switched on
               # at once, with or without the lighter "all but one" band.
               '<div class="lookback hshade" role="group" aria-label="Price shading">'
               '<span>Shade price</span>'
               '<button type="button" data-shade="most" aria-pressed="true">'
               'All on, and one short</button>'
               '<button type="button" data-shade="every" aria-pressed="false">'
               'Only all on at once</button></div>')
    first, steps = view.history_day_steps(history)
    return _card(view.HISTORY_TITLE, view.history_subtitle(history), view.HISTORY_HOW,
                 windows,
                 f'<div class="detail hread" data-history-read aria-live="polite">'
                 f'{_esc(view.HISTORY_READ_HINT)}</div>',
                 f'<div class="hgrid" id="{HISTORY_ID}" data-sessions="{n}" '
                 f'data-first="{first}" data-steps="{steps}" '
                 f'data-units="{units:g}" data-total="{history.total}" data-mark="{mark}">'
                 f'{"".join(rows)}</div>',
                 f'<div class="detail" data-history-summary>'
                 f'{_esc(view.history_summary(history))}</div>')


def _across(cards):
    """The grid class for a row of cards, so no count leaves a hole: three across,
    except five (three, then two sharing the row) and an even count (two across)."""
    n = len(cards)
    return " five" if n == 5 else " three" if n % 3 == 0 else ""


#: The page's sections in order, (anchor, label): the jump links under the title.
JUMPS = ((HEADWINDS_ID, "Headwinds"), (HISTORY_ID, "History"), (CONTEXT_ID, "Context"),
         (SENTIMENT_ID, "Sentiment"), (POSITIONING_ID, "Positioning"), (DETAIL_ID, "Detail"))


def _jumps(body):
    """Links to the sections `body` actually holds: the page is long on a phone."""
    links = "".join(f'<a href="#{anchor}">{label}</a>' for anchor, label in JUMPS
                    if f'id="{anchor}"' in body)
    return f'<nav class="jumps" aria-label="On this page">{links}</nav>' if links else ""


def headwinds_section(snap, colors):
    missing = [k for k in mi.HEADWIND_KEYS if k not in {h.key for h in snap.headwinds}]
    note = (_detail("Awaiting data for: " + ", ".join(missing).replace("_", " ") + ".")
            if missing else "")
    # The net-highs cards point at the year of counts behind them, far down the page.
    jump = f'<a class="jump" href="#{BREADTH_ID}">A year of highs and lows &darr;</a>'
    more = ({mi.net_highs_key(x): jump for x, _, _ in mi.NET_HIGHS_SYMBOLS}
            if snap.breadth is not None else {})
    share = snap.nyse_lows_share
    if share is not None:
        tone = colors.bear if share.value >= mi.NYSE_LOWS_SHARE_LINE else "var(--ink-2)"
        line = (f'<div class="detail" data-lows-share style="color:{tone}">'
                f'{_esc(view.nyse_lows_share_text(share))}</div>')
        key = mi.net_highs_key("NYSE")
        more[key] = line + more.get(key, "")
    return (_section(view.HEADWINDS_TITLE, view.HEADWINDS_SUBTITLE, view.HEADWINDS_HOW)
            + f'<div class="cards{_across(snap.headwinds)}" id="{HEADWINDS_ID}">\n'
            + "".join(headwind_card(h, colors, _prov(snap, h.key), more.get(h.key, ""))
                      for h in snap.headwinds) + f'</div>\n{note}'
            + history_card(snap.history, colors))


def fomo_card(read, colors, chip=""):
    if read is None:
        return _card(view.FOMO_TITLE, None, None, _awaiting([mi.FOMO_SYMBOL]))
    change = view.verdict_color(mi.POSITIVE if read.change >= 0 else mi.NEGATIVE, colors)
    return _card(
        view.FOMO_TITLE, view.FOMO_SUBTITLE, view.FOMO_HOW,
        f'<div class="row"><span class="big">{read.value:.1f}</span>'
        f'{_badge(read.label, read.verdict, colors)}{chip}'
        f'<span class="detail push" style="color:{change}">'
        f'{_esc(view.signed(read.change, ".1f"))} on the day</span></div>',
        _chart(FOMO_KEY, view.fomo_chart(read, colors)["height"]),
        _detail(f"{view.FOMO_ZONES} · {view.fomo_recent(read)}"),
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


def volatility_card(read, colors):
    """The VIX against VIX3M. No card at all without the data: this is context, and an
    "awaiting" card for it would outrank what it is."""
    if read is None:
        return ""
    change = view.verdict_color(mi.NEGATIVE if read.change >= 0 else mi.POSITIVE, colors)
    return _card(
        view.VOLATILITY_TITLE, view.VOLATILITY_SUBTITLE, view.VOLATILITY_HOW,
        f'<div class="row"><span class="big">{read.value:.1f}</span>'
        f'{_badge(view.volatility_label(read), mi.NEGATIVE if read.inverted else mi.NEUTRAL, colors)}'
        f'<span class="detail push" style="color:{change}">'
        f'{_esc(view.signed(read.change, ".1f"))} on the day</span></div>',
        _chart(VOLATILITY_KEY, view.volatility_chart(read, colors)["height"]),
        f'<div class="detail"><span class="key">— {mi.VOLATILITY_SYMBOL}</span>'
        f'<span style="color:{view.AVERAGE_COLOR}">— {mi.VOLATILITY_TERM_SYMBOL}</span></div>',
        _detail(view.volatility_status(read)),
    )


def bond_volatility_card(read, colors):
    """The MOVE index, a card beside the VIX's: its level, its year and its place in
    its own history. No card when the store does not hold it. It sat inside the VIX's
    card until 2026-11-19, which made that card half again as tall as its neighbours."""
    bonds = read.bonds if read is not None else None
    if bonds is None:
        return ""
    change = view.verdict_color(mi.NEGATIVE if bonds.change >= 0 else mi.POSITIVE, colors)
    return _card(
        view.BOND_VOLATILITY_TITLE, view.BOND_VOLATILITY_SUBTITLE, view.BOND_VOLATILITY_HOW,
        f'<div class="row"><span class="big">{bonds.value:.1f}</span>'
        f'<span class="detail push" style="color:{change}">'
        f'{_esc(view.signed(bonds.change, ".1f"))} on the day</span></div>',
        _chart(BOND_VOLATILITY_KEY, view.bond_volatility_chart(bonds)["height"]),
        _detail(view.bond_volatility_status(bonds)))


def _block(block):
    """One block: label, current reading, date, then a rail per history with the
    reading's place as a numbered dot. The dot's colour is the tier's tone (warm toward
    a high, cool toward a low), as on the surveys page's tiles."""
    rails = "".join(
        f'<div class="rl">{_esc(label)}</div>'
        f'<div class="rail"><i class="tier-{tier}" style="left:{position}%">{_esc(text)}</i></div>'
        for label, position, text, tier in block["rows"])
    note = _detail(block["note"]) if block.get("note") else ""
    return (f'<div class="pblock" data-key="{_esc(block["key"])}">'
            f'<div class="between"><span class="label">{_esc(block["label"])}</span>'
            f'<span class="foot">{_esc(block["foot"])}</span></div>'
            f'<div class="value">{_esc(block["value"])}</div>{note}'
            f'<div class="rails">{rails}</div></div>')


def sentiment_section(naaim, votes, allocation):
    """The surveys: each one's current reading over its percentile bars. Each is
    optional and left out when its store could not serve it; with none, no section."""
    blocks = view.percentile_blocks(naaim, votes, allocation, _date)
    if not blocks:
        return ""
    return (_section(view.SENTIMENT_TITLE, view.SENTIMENT_SUBTITLE, view.SENTIMENT_HOW)
            + f'<div class="pblocks" id="{SENTIMENT_ID}">'
            + "".join(_block(b) for b in blocks) + '</div>\n'
            + f'<p class="more"><a href="{SURVEYS_URL}">The surveys in full, with their '
            'history &rarr;</a></p>\n')


def _cot_cell(value, colors):
    """One lookback's commercial index, filled as the crowd board fills it: the pole's
    colour, stronger the further from 50 (`board_traces.cell_fill`)."""
    if value is None:
        return '<td class="num"><span class="cell none">&ndash;</span></td>'
    fill = board_traces.cell_fill(value, colors, background=surveys.SURFACE_COLOR)
    return (f'<td class="num"><span class="cell" style="background:{fill};'
            f'color:{ink_on(fill)}">{value:.0f}</span></td>')


def _cot_row(read, colors):
    move = read.move
    if move is None:
        change = "&ndash;"
    else:
        flat = abs(move) <= board_traces.DELTA_FLAT
        tone = surveys.MUTED if flat else colors.bull if move > 0 else colors.bear
        change = (f'<span style="color:{tone}">{"•" if flat else "▲" if move > 0 else "▼"}</span> '
                  f'{_esc(view.signed(move, ".0f"))}')
    points, end = view.positioning_spark(read)
    spark = ""
    if end is not None:
        last = read.path[-1]
        dot = colors.bull if last >= 50 else colors.bear
        w, h = view.SPARK_WIDTH, view.SPARK_HEIGHT
        spark = (f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
                 f'aria-label="{_esc(read.name)} 12-month commercial index over the last year">'
                 f'<line x1="0" x2="{w}" y1="{h / 2:g}" y2="{h / 2:g}" stroke="{surveys.MUTED}" '
                 'stroke-width="1" stroke-dasharray="2 3"/>'
                 f'<polyline fill="none" stroke="{surveys.INK_2}" stroke-width="1.2" '
                 f'points="{points}"/><circle cx="{end[0]:.1f}" cy="{end[1]:.1f}" r="2.5" '
                 f'fill="{dot}"/></svg>')
    since = f" <small>'{read.start[2:4]}</small>" if read.start else ""
    return (f'<tr data-key="{_esc(read.symbol)}"><td class="sym mono">{_esc(read.symbol)}</td>'
            f'<td class="name">{_esc(read.name)}{since}</td>'
            + "".join(_cot_cell(v, colors) for v in read.windows)
            + f'<td class="num">{change}</td><td class="num path">{spark}</td></tr>')


def positioning_section(positioning, colors, groups=None):
    """Commercials in the equity index futures: the crowd board's lookback rows,
    then each market's net position through time. No section without the COT store."""
    if not positioning:
        return ""
    head = ('<th></th><th class="name"></th>'
            + "".join(f"<th>{_esc(c)}</th>" for c in view.POSITIONING_COLUMNS)
            + f'<th>{_esc(view.POSITIONING_CHANGE)}</th>'
            f'<th class="path">{_esc(view.POSITIONING_PATH)}</th>')
    table = ('<div class="scroll"><table class="cot"><thead><tr>' + head + '</tr></thead><tbody>'
             + "".join(_cot_row(r, colors) for r in positioning) + '</tbody></table></div>')
    asof = _detail(f"Commercial index, 0 to 100 · report of {_date(positioning[0].date)}",
                   "detail small")
    groups = groups or group_colors()
    drawn = len(positioning[0].others) + 1
    legend = "".join(f'<span class="key" style="color:{color}">■ {_esc(label)}</span>'
                     for label, color in list(zip(view.POSITIONING_GROUPS, groups))[:drawn])
    charts_html = "".join(
        f'<div class="pchart"><div class="label">{_esc(r.symbol)} · {_esc(r.name)}</div>'
        + _chart(POSITIONING_PREFIX + r.symbol, view.positioning_chart(r, groups)["height"]) + '</div>'
        for r in positioning)
    return (_section(view.POSITIONING_TITLE, view.POSITIONING_SUBTITLE, view.POSITIONING_HOW)
            + f'<section class="card" id="{POSITIONING_ID}">{table}{asof}'
            '<h3>Net position by trader group, contracts · weekly, three years</h3>'
            f'<div class="detail legend">{legend}</div>'
            f'<div class="pcharts">{charts_html}</div></section>\n')


def breadth_charts(snap, colors):
    """The year behind the net-highs headwinds: the two counts, then their net. No
    cards without the counts (the headwind cards already say they are awaiting them)."""
    if snap.breadth is None:
        return ""
    b = snap.breadth
    return (f'<div class="cards" id="{BREADTH_ID}">\n'
            + _card(view.HIGHS_LOWS_TITLE, view.HIGHS_LOWS_SUBTITLE, None,
                    f'<div class="detail legend"><span class="key" style="color:{colors.bull}">'
                    f'▲ New highs {b.highs[-1]:.0f}</span><span class="key" style="color:{colors.bear}">'
                    f'▼ New lows {b.lows[-1]:.0f}</span> {_prov(snap, "net_highs")}</div>',
                    _chart(HIGHS_LOWS_KEY, view.highs_lows_chart(b, colors)["height"]))
            + _card(view.NET_HISTORY_TITLE, view.NET_HISTORY_SUBTITLE, view.NET_HISTORY_HOW,
                    '<div class="detail legend"><span class="key">— Daily</span>'
                    f'<span class="name">— {mi.NET_HIGHS_AVERAGE}-day average</span></div>',
                    _chart(NET_HISTORY_KEY, view.net_highs_chart(b, colors)["height"]))
            + '</div>\n')


_ARROWS = {1: "▲", -1: "▼", 0: "•"}


def _net_highs_row(read, colors, chip=""):
    color = view.verdict_color(read.verdict, colors)
    ink = {1: colors.bull, -1: colors.bear, 0: surveys.INK_2}
    arrows = "".join(f'<span style="color:{ink[s]}">{_ARROWS[s]}</span> '
                     for s in read.last_three)
    edge = color if read.regime else "transparent"
    return (f'<div class="between nh" style="border-left-color:{edge}"><div>'
            f'<div class="name">{_esc(read.exchange)} {chip}</div>'
            f'{_detail(f"{read.highs} highs, {read.lows} lows")}'
            f'<div>{arrows}</div></div>'
            f'<div class="right"><div class="big" style="color:{color}">'
            f'{_esc(view.signed(read.net, "d"))}</div>'
            f'<div class="gap">{_badge(read.label, read.verdict, colors)}</div></div></div>')


def breadth_card(snap, colors):
    """Net new highs on both exchanges, and the session's advancing share under them."""
    rows = [_net_highs_row(r, colors, _prov(snap, r.exchange)) for r in snap.net_highs]
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
            f'<div class="detail">{read.advancing:,} up, {read.declining:,} down '
            f'{_prov(snap, "advance_decline")}</div>',
        ]
    return _card(view.NET_HIGHS_TITLE, view.NET_HIGHS_SUBTITLE, view.NET_HIGHS_HOW, *rows)


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


#: Days past the snapshot's date before the page says it is old. The nightly publish
#: lands the same evening, so the longest healthy gap is a holiday weekend read just
#: before the next publish: Friday's data until Tuesday evening, under five days.
STALE_AFTER_DAYS = 5


def _stale(snap):
    """A warning the reader's own clock switches on: a page is only as fresh as its
    last publish, and a failed one leaves yesterday's page up with nothing to say so."""
    return (f'<p class="stale" role="status" hidden data-stale data-through="{_esc(snap.date)}" '
            f'data-after="{STALE_AFTER_DAYS}">This page last updated with data through '
            f'{_date(snap.date)}. Its readings are <b data-stale-days></b> days old.</p>')


def _headline(snap, colors):
    count, lean = mi.headline(snap)
    number, _, rest = count.partition(" ")
    if not number.isdigit():
        return f'<p class="count">{_esc(count)}</p><p class="lean">{_esc(lean)}</p>'
    since = view.headline_since(snap)
    if since:
        lean = f"{lean} {since}"
    return (f'<p class="count"><b style="color:{view.count_color(snap, colors)}">'
            f'{_esc(number)}</b> {_esc(rest)}</p><p class="lean">{_esc(lean)}</p>')


def render(snap, colors, generated_at=None, naaim=None, votes=None, allocation=None,
           positioning=None, palette=None):
    """The page for `snap` (`market_internals.build_snapshot()`); `colors` is the
    palette's verdict pair (`plot_colors.grid_colors`), toned here by `page_colors`.

    `naaim` (`naaim_card.read()`), `votes` (`aaii_votes.read()`) and `allocation`
    (`aaii_allocation.read()`) fill the sentiment section; `positioning`
    (`market_internals.equity_positioning()`) the positioning section. Each is
    optional, and a section is left out with nothing to show. `palette` is the app
    palette the trader groups take their colours from, the configured one when None.

    Raises ValueError when the snapshot holds no read at all, so a store that could not
    be read never replaces the published page with a row of "awaiting data" cards. A
    snapshot missing SOME reads still renders, with the missing ones named: the page's
    rule for a series that has not been delivered yet.
    """
    if snap.date is None or not mi.has_reads(snap):
        raise ValueError("the snapshot holds no reads"
                         + (f" (awaiting {', '.join(snap.awaiting)})" if snap.awaiting else ""))
    colors = page_colors(colors)
    groups = group_colors(palette) if positioning else ()
    stamp = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    context = [card for card in (
        fomo_card(snap.fomo, colors, _prov(snap, "fomo")),
        appetite_card(snap.appetite, snap.credit, colors),
        volatility_card(snap.volatility, colors),
        bond_volatility_card(snap.volatility, colors)) if card]
    uncounted = (_section(view.UNCOUNTED_TITLE, view.UNCOUNTED_SUBTITLE)
                 + f'<div class="cards{_across(context)}" id="{CONTEXT_ID}">\n'
                 + "".join(context) + '</div>\n'
                 + sentiment_section(naaim, votes, allocation)
                 + positioning_section(positioning, colors, groups))
    detail = (_section(view.DETAIL_TITLE, view.DETAIL_SUBTITLE)
              + breadth_charts(snap, colors)
              + f'<div class="cards" id="{DETAIL_ID}">\n' + breadth_card(snap, colors)
              + asset_table(snap.assets, snap.awaiting, colors) + '</div>\n')
    body = headwinds_section(snap, colors) + uncounted + detail
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(TITLE)}</title>
<meta name="description" content="{_esc(DESCRIPTION)}">
<link rel="canonical" href="{URL}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{_esc(SITE_NAME)}">
<meta property="og:title" content="{_esc(TITLE)}">
<meta property="og:description" content="{_esc(DESCRIPTION)}">
<meta property="og:url" content="{URL}">
<meta name="twitter:card" content="summary">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap">
<style>
{surveys.base_css()}/* This page's own rules, on the shared tokens above. The count leads, as the surveys
   page's tiles do; a headwind card's left edge is its state, the defensive red when it
   is on and the constructive green when it is not (the surveys cards' toned pair). */
.stale {{ color: var(--ink); font-size: 0.85rem; margin: 0 0 12px; padding: 7px 12px; border: 1px solid {surveys.TONE_HIGH};
  border-left-width: 3px; border-radius: 6px; background: var(--wash); }}
.count {{ color: var(--ink); font-size: 1.05rem; font-weight: 500; margin: 0; }}
.count b {{ font-size: 2.4rem; font-weight: 700; line-height: 1; margin-right: 4px; }}
.lean {{ font-size: 0.9rem; margin: 2px 0 16px; }}
.sec {{ margin: 18px 0 8px; }}
.sec h2 {{ color: var(--ink); font-size: 1.05rem; font-weight: 600; margin: 0 0 2px; }}
.sec .sub {{ font-size: 0.8rem; display: inline; margin-right: 10px; }}
.sec .how {{ font-size: 0.8rem; display: inline-block; }}
.sec .how[open] {{ display: block; margin-top: 2px; }}
.sec .how summary {{ cursor: pointer; width: fit-content; color: var(--ink); }}
.sec .how p {{ margin: 4px 0 0; }}
/* The history: a label column and a plot column; on a phone the label sits over its
   strip. Every SVG is one unit a session wide, so the rows line up to the session. */
.hgrid {{ display: grid; grid-template-columns: 200px minmax(0, 1fr); gap: 5px 12px; align-items: center; margin: 8px 0; }}
.hl {{ font-size: 0.78rem; }}
/* A row's name is its switch: a filled square while the row is on. */
button.htog {{ background: none; border: 0; padding: 0; margin: 0; color: var(--ink-2); font: inherit; font-size: 0.78rem;
  text-align: left; cursor: pointer; display: flex; align-items: center; gap: 7px; }}
button.htog::before {{ content: ""; flex: none; width: 9px; height: 9px; border-radius: 2px; border: 1px solid var(--ink-2); background: var(--ink-2); }}
button.htog[aria-pressed="false"] {{ color: var(--muted); }}
button.htog[aria-pressed="false"]::before {{ background: transparent; border-color: var(--muted); }}
button.htog:focus-visible {{ outline: 2px solid var(--ticker); outline-offset: 2px; }}
.hp.off svg {{ display: none; }}
.hl.all {{ color: {colors.bear}; font-weight: 600; }}
/* Sentiment and positioning: a block per series, its reading over its percentile
   rails. A rail is the 0-100 scale with a tick at the median and the reading as a
   numbered dot. */
.pblocks {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; margin-bottom: 12px; }}
.pblock {{ background: var(--surface); border: 1px solid var(--line); border-radius: 6px; padding: 10px 14px; }}
.pblock .label {{ font-size: 0.8rem; color: var(--ink-2); }}
.pblock .foot {{ font-size: 0.75rem; color: var(--muted); }}
.pblock .value {{ font-size: 1.75rem; font-weight: 600; line-height: 1.2; color: var(--ink); }}
.rails {{ display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 9px 12px; align-items: center; margin: 10px 11px 4px 0; }}
.rl {{ font-size: 0.75rem; }}
.rail {{ position: relative; height: 6px; border-radius: 3px; background: rgba(255,255,255,0.12); }}
.rail::after {{ content: ""; position: absolute; left: 50%; top: -4px; width: 1px; height: 14px; background: var(--muted); }}
.rail i {{ position: absolute; top: 50%; width: 22px; height: 22px; margin: -11px 0 0 -11px; border-radius: 50%;
  background: var(--ink-2); color: var(--page); font-size: 0.68rem; font-weight: 700; font-style: normal;
  line-height: 22px; text-align: center; box-shadow: 0 0 0 2px var(--surface); z-index: 1; }}
/* Warm toward a high, cool toward a low: how unusual a reading is, the surveys
   tiles' tones. Deliberately not green and red (tried and dropped 2026-11-18): green
   would have to mean either "the crowd is bullish" or "this is a bullish signal",
   which are opposite readings of the same dot, and the second is untested. */
.rail i.tier-top, .rail i.tier-high {{ background: {surveys.TONE_HIGH}; }}
.rail i.tier-bottom, .rail i.tier-low {{ background: {surveys.TONE_LOW}; }}
.prov {{ font-size: 0.65rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--muted);
  border: 1px dashed var(--muted); border-radius: 4px; padding: 1px 6px; white-space: nowrap; }}
.more {{ font-size: 0.8rem; margin: -4px 0 0; }}
/* Positioning: the crowd board's row, as a table. A cell is a pill filled toward its
   pole. On a phone the market's name and the year's path step aside (the symbol and
   the charts under the table say both) so every lookback fits without a sideways
   scroll nothing pointed at. */
.scroll {{ overflow-x: auto; }}
table.cot {{ min-width: 520px; }}
table.cot th {{ text-align: center; border-bottom: none; padding: 2px 6px; }}
table.cot td {{ border-bottom: none; padding: 3px 6px; white-space: nowrap; }}
table.cot td.num {{ text-align: center; }}
table.cot td small {{ color: var(--muted); }}
.mono {{ font-family: var(--mono); }}
.cell {{ display: inline-block; min-width: 64px; padding: 2px 0; border-radius: 4px; font-size: 0.82rem; font-weight: 600; text-align: center; }}
.cell.none {{ background: var(--wash); color: var(--muted); }}
@media (max-width: 700px) {{
  table.cot {{ min-width: 0; }}
  table.cot .name, table.cot .path {{ display: none; }}
  table.cot th, table.cot td {{ padding: 3px 3px; }}
  .cell {{ min-width: 40px; }}
}}
.pcharts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 4px 16px; }}
.pchart .label {{ font-size: 0.8rem; }}
.more a {{ color: var(--ink-2); }}
.hp svg {{ display: block; width: 100%; }}
.hprice {{ height: 190px; }}
.hstrip {{ height: 14px; background: var(--wash); border-radius: 2px; }}
.hyears {{ position: relative; height: 16px; font-size: 0.7rem; color: var(--muted); }}
.hyears span {{ position: absolute; transform: translateX(-50%); white-space: nowrap; }}
.hwin, .hshade {{ margin: 8px 0 0; }}
/* The session under the pointer; a fixed line so the grid does not jump as it fills.
   A sideways drag on the plots reads sessions, an up-and-down one still scrolls. */
.hread {{ margin: 8px 0 0; min-height: 1.4em; }}
.hp {{ touch-action: pan-y; }}
.card a.jump {{ font-size: 0.78rem; color: var(--ink-2); }}
@media (max-width: 700px) {{
  .hgrid {{ grid-template-columns: minmax(0, 1fr); gap: 2px; }}
  .hl {{ margin-top: 5px; font-size: 0.72rem; }}
  .hprice {{ height: 150px; }}
}}
/* A How to read this is a short list of points, one idea each. */
.how ul {{ margin: 4px 0 0; padding-left: 18px; }}
.how li {{ margin: 3px 0; line-height: 1.45; }}
.card.hw .how {{ margin: 2px 0 4px; }}
.card.hw {{ border-left: 3px solid var(--line); }}
.card.hw.on {{ border-left-color: {colors.bear}; }}
.card.hw.off {{ border-left-color: {colors.bull}; }}
.card.hw .big {{ font-size: 1.6rem; }}
/* Cards two across from 900px, the six headwinds three across from 1100px; one
   column on a phone. */
.cards {{ display: grid; grid-template-columns: minmax(0, 1fr); gap: 0 12px; align-items: start; }}
@media (min-width: 900px) {{ .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
@media (min-width: 1100px) {{
  .cards.three {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
  /* Five: three across, then two sharing the second row, so no slot is left empty. */
  .cards.five {{ grid-template-columns: repeat(6, minmax(0, 1fr)); }}
  .cards.five > * {{ grid-column: span 2; }}
  .cards.five > :nth-child(n+4) {{ grid-column: span 3; }}
}}
@media (min-width: 900px) and (max-width: 1099px) {{ .cards.five > :last-child {{ grid-column: 1 / -1; }} }}
/* Jump links to the sections; a target stops clear of the top edge. */
nav.jumps {{ display: flex; flex-wrap: wrap; gap: 4px 6px; font-size: 12.5px; margin: 10px 0 0; }}
nav.jumps a {{ color: var(--ink-2); text-decoration: none; padding: 3px 9px; border: 1px solid var(--line); border-radius: 6px; }}
nav.jumps a:hover {{ background: var(--wash); color: var(--ink); }}
nav.jumps a:focus-visible {{ outline: 2px solid var(--ticker); outline-offset: 1px; }}
[id] {{ scroll-margin-top: 64px; }}
/* A finger needs more than a mouse: the switches and links grow on a phone. */
@media (max-width: 700px) {{
  .lookback {{ flex-wrap: wrap; }}
  .lookback button {{ font-size: 12px; padding: 7px 12px; }}
  button.htog {{ padding: 7px 0; }}
  nav.jumps a {{ padding: 7px 11px; }}
}}
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
.key {{ margin-right: 12px; white-space: nowrap; display: inline-block; }}
/* A legend over its chart: items wrap whole, and stand clear of the top axis label. */
.legend {{ display: flex; flex-wrap: wrap; align-items: center; gap: 2px 12px; margin-bottom: 4px; }}
.legend .key {{ margin-right: 0; }}
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
{_stale(snap)}
{_headline(snap, colors)}
{_jumps(body)}
{body}<div class="notes"><p>{_esc(view.caption(snap))}</p></div>
<footer>{_esc(SOURCES)} Charts: <a href="{ATTRIBUTION_URL}" rel="noopener">{_esc(ATTRIBUTION)}</a></footer>
</main>
<script>window.INTERNALS_META={{"generated_at":"{_esc(stamp)}"}};</script>
<script>
// Old data says so. The reader's clock against the snapshot's date, in whole days.
(function () {{
  var note = document.querySelector('[data-stale]');
  if (!note) {{ return; }}
  var days = Math.floor((Date.now() - Date.parse(note.dataset.through + 'T00:00:00Z')) / 86400000);
  if (!(days > +note.dataset.after)) {{ return; }}
  note.querySelector('[data-stale-days]').textContent = days;
  note.hidden = false;
}})();
</script>
<script type="application/json" id="{DATA_ID}">{surveys._script_json(charts(snap, colors, positioning, groups))}</script>
<script>
(function () {{
  var LC = window.LightweightCharts;
  if (!LC) {{ return; }}
  var DATA = JSON.parse(document.getElementById('{DATA_ID}').textContent);
  var INK = '{surveys.INK_2}', GRID = 'rgba(255,255,255,0.06)';
  var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  document.querySelectorAll('[data-chart]').forEach(function (el) {{
    var spec = DATA[el.dataset.chart];
    if (!spec) {{ return; }}
    var format = {{type: 'price', precision: spec.decimals, minMove: Math.pow(10, -spec.decimals)}};
    // Thousands separators on the scale: 200,000, not 200000.
    var print = function (price) {{
      return price.toLocaleString('en-US', {{minimumFractionDigits: spec.decimals,
                                             maximumFractionDigits: spec.decimals}});
    }};
    var chart = LC.createChart(el, {{
      autoSize: true,
      localization: {{priceFormatter: print}},
      layout: {{background: {{type: 'solid', color: 'transparent'}}, textColor: INK,
               fontSize: 10, fontFamily: getComputedStyle(document.body).fontFamily,
               attributionLogo: false}},
      grid: {{vertLines: {{visible: false}}, horzLines: {{color: GRID}}}},
      // A fixed 0-100 scale keeps thin margins, or the axis runs on to 120.
      // Whole labels only: one at the very top or bottom edge is cut in half otherwise.
      rightPriceScale: {{borderVisible: false, entireTextOnly: true,
                        scaleMargins: spec.range ? {{top: 0.04, bottom: 0.04}} : {{top: 0.12, bottom: 0.1}}}},
      // Months and years on the time axis, never a day of the month: a wide card fits
      // more marks than a narrow one, and the extra ones were bare numbers ("15", "14")
      // that made two cards of the same quarter look like different spans.
      timeScale: {{borderVisible: false, fixLeftEdge: true, fixRightEdge: true,
                  tickMarkFormatter: function (time, type) {{
                    if (type === LC.TickMarkType.Year) {{ return String(time).slice(0, 4); }}
                    if (type === LC.TickMarkType.Month) {{ return MONTHS[+String(time).slice(5, 7) - 1]; }}
                    return '';
                  }}}},
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
      // A series is a line unless it says otherwise: bars from zero, or a line whose
      // side below its base is shaded (a headwind's zone).
      var line;
      if (s.type === 'histogram') {{
        line = chart.addSeries(LC.HistogramSeries, {{color: s.color, priceFormat: format,
          priceLineVisible: false, lastValueVisible: false}});
      }} else if (s.type === 'baseline') {{
        line = chart.addSeries(LC.BaselineSeries, {{
          baseValue: {{type: 'price', price: s.base}}, lineWidth: s.width,
          topLineColor: s.color, bottomLineColor: s.color,
          topFillColor1: s.top || 'transparent', topFillColor2: s.top || 'transparent',
          bottomFillColor1: s.shade, bottomFillColor2: s.shade,
          priceFormat: format, priceLineVisible: false, lastValueVisible: false}});
      }} else if (s.type === 'area') {{
        // Each point carries its own fill: the session's state.
        line = chart.addSeries(LC.AreaSeries, {{lineColor: s.color, lineWidth: s.width,
          topColor: 'transparent', bottomColor: 'transparent', priceFormat: format,
          priceLineVisible: false, lastValueVisible: false}});
      }} else {{
        line = chart.addSeries(LC.LineSeries, options);
      }}
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
<script>
// The history card's windows. Every row's SVG is one unit a session wide, so a window
// is a viewBox: the same x range on all of them, and on the price the y range of what
// is on screen, so a year of price is not a flat line on nineteen years' scale.
(function () {{
  var grid = document.getElementById('{HISTORY_ID}');
  if (!grid) {{ return; }}
  var N = +grid.dataset.sessions, UNITS = +grid.dataset.units;
  var svgs = [].slice.call(grid.querySelectorAll('svg'));
  var price = grid.querySelector('.hprice');
  var points = price.querySelector('polyline').getAttribute('points').split(' ')
    .map(function (p) {{ p = p.split(','); return [+p[0], +p[1]]; }});
  var axis = grid.querySelector('.hyears');
  var months = JSON.parse(axis.dataset.months);
  var NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function ticks(start, len) {{
    var years = len / 252, out = [];
    // Months inside a year and a half, quarters inside four years, then whole years
    // thinned to about ten labels.
    var every = years <= 1.5 ? 1 : years <= 4 ? 3 : 12;
    var step = Math.max(1, Math.ceil(years / 10));
    months.forEach(function (m) {{
      var i = m[0], year = +m[1].slice(0, 4), month = +m[1].slice(5, 7);
      if (i <= start || (month - 1) % every) {{ return; }}
      if (every === 12 && year % step) {{ return; }}
      var text = every === 12 ? String(year)
        : month === 1 ? "Jan '" + String(year).slice(2) : NAMES[month - 1];
      out.push([(i - start) / len, text]);
    }});
    return out;
  }}
  var win = [0, N];
  function show(sessions) {{
    var len = sessions ? Math.min(sessions, N) : N, start = N - len;
    win = [start, len];
    var low = Infinity, high = -Infinity;
    points.forEach(function (p) {{
      if (p[0] >= start) {{ low = Math.min(low, p[1]); high = Math.max(high, p[1]); }}
    }});
    var pad = (high - low || UNITS) * 0.04;
    svgs.forEach(function (svg) {{
      var y = svg === price ? [low - pad, high - low + 2 * pad] : [0, 1];
      svg.setAttribute('viewBox', start + ' ' + y[0] + ' ' + len + ' ' + y[1]);
    }});
    axis.textContent = '';
    ticks(start, len).forEach(function (t) {{
      var span = document.createElement('span');
      span.style.left = (t[0] * 100).toFixed(2) + '%';
      span.textContent = t[1];
      axis.appendChild(span);
    }});
    document.querySelectorAll('.hwin button').forEach(function (b) {{
      b.setAttribute('aria-pressed', +b.dataset.sessions === sessions ? 'true' : 'false');
    }});
  }}
  // What the reader chose, kept in this browser only. Storage can be missing or
  // refuse (a private window), and the card works the same without it.
  var KEY = 'internals.history';
  function load() {{
    try {{ return JSON.parse(localStorage.getItem(KEY)) || {{}}; }} catch (e) {{ return {{}}; }}
  }}
  function save(patch) {{
    try {{
      var state = load();
      Object.keys(patch).forEach(function (k) {{ state[k] = patch[k]; }});
      localStorage.setItem(KEY, JSON.stringify(state));
    }} catch (e) {{}}
  }}
  document.querySelectorAll('.hwin button').forEach(function (b) {{
    b.addEventListener('click', function () {{
      show(+b.dataset.sessions);
      save({{window: +b.dataset.sessions}});
    }});
  }});

  // A row's name switches it. The bottom row and the shading count the headwind rows
  // that are on, from each row's runs; FOMO is not a headwind and only shows itself.
  var MARK = grid.dataset.mark, TOTAL = +grid.dataset.total;
  var runs = {{}};
  grid.querySelectorAll('svg[data-headwind]').forEach(function (svg) {{
    runs[svg.dataset.row] = [].map.call(svg.querySelectorAll('rect'), function (r) {{
      return [+r.getAttribute('x'), +r.getAttribute('width')];
    }});
  }});
  var allStrip = grid.querySelector('svg[data-row="all"]');
  var allLabel = grid.querySelector('[data-all-label]');
  var band = function (name) {{ return price.querySelector('[data-band="' + name + '"]'); }};
  var summary = document.querySelector('[data-history-summary]');
  var whole = summary ? summary.textContent : '';
  function rects(list, height, y, opacity) {{
    return list.map(function (r) {{
      return '<rect x="' + r[0] + '" y="' + y + '" width="' + r[1] + '" height="' + height
        + '" fill="' + MARK + '" fill-opacity="' + opacity + '"/>';
    }}).join('');
  }}
  function recount() {{
    var on = [];
    grid.querySelectorAll('button.htog[aria-pressed="true"]').forEach(function (b) {{
      if (runs[b.dataset.row]) {{ on.push(b.dataset.row); }}
    }});
    var count = new Uint8Array(N);
    on.forEach(function (key) {{
      runs[key].forEach(function (r) {{ for (var i = r[0]; i < r[0] + r[1]; i++) {{ count[i]++; }} }});
    }});
    function where(target) {{
      var out = [], start = -1;
      for (var i = 0; i <= N; i++) {{
        var hit = i < N && count[i] === target;
        if (hit && start < 0) {{ start = i; }}
        if (!hit && start >= 0) {{ out.push([start, i - start]); start = -1; }}
      }}
      return out;
    }}
    var n = on.length;
    var every = n ? where(n) : [], most = n > 1 ? where(n - 1) : [];
    allStrip.innerHTML = rects(every, 1, 0, 1);
    allStrip.appendChild(cursors[svgs.indexOf(allStrip)]);    // innerHTML dropped it
    band('every').innerHTML = rects(every, UNITS * 2, -UNITS / 2, 0.45);
    band('most').innerHTML = rects(most, UNITS * 2, -UNITS / 2, 0.18);
    allLabel.textContent = n === 0 ? 'No row is on' : n === 1 ? 'The 1 row on' : 'All ' + n + ' at once';
    if (!summary) {{ return; }}
    if (n === TOTAL) {{ summary.textContent = whole; return; }}
    var sessions = every.reduce(function (sum, r) {{ return sum + r[1]; }}, 0);
    summary.textContent = n === 0 ? 'No row is on.'
      : 'The ' + n + ' selected ' + (n === 1 ? 'row was on' : 'rows were on at once') + ' on '
        + sessions.toLocaleString('en-US') + ' of ' + N.toLocaleString('en-US') + ' sessions ('
        + Math.round(sessions / N * 100) + '%).';
  }}
  // The price's shading: the rows that are on all at once, with or without the
  // lighter band for all but one of them.
  var shades = [].slice.call(document.querySelectorAll('.hshade button'));
  shades.forEach(function (b) {{
    b.addEventListener('click', function () {{
      band('most').setAttribute('display', b.dataset.shade === 'most' ? 'inline' : 'none');
      shades.forEach(function (o) {{ o.setAttribute('aria-pressed', o === b ? 'true' : 'false'); }});
      save({{shade: b.dataset.shade}});
    }});
  }});
  grid.querySelectorAll('button.htog').forEach(function (b) {{
    b.addEventListener('click', function () {{
      var on = b.getAttribute('aria-pressed') !== 'true';
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      grid.querySelector('[data-strip="' + b.dataset.row + '"]').classList.toggle('off', !on);
      var kept = load().rows || {{}};
      kept[b.dataset.row] = on;
      save({{rows: kept}});
      if (runs[b.dataset.row]) {{ recount(); return; }}
      var over = band(b.dataset.row);
      if (over) {{ over.setAttribute('display', on ? 'inline' : 'none'); }}
    }});
  }});

  // The session under the pointer: a line down every row, and its date and the rows
  // that were on in the line under the buttons. Dates are the first one plus each
  // session's days since the one before.
  var read = document.querySelector('[data-history-read]');
  var hint = read ? read.textContent : '';
  var stamp = Date.parse(grid.dataset.first + 'T00:00:00Z'), DAYS = [stamp];
  grid.dataset.steps.split(',').forEach(function (step) {{
    if (step) {{ stamp += +step * 86400000; DAYS.push(stamp); }}
  }});
  var cursors = svgs.map(function (svg) {{
    var line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    var tall = svg === price;
    line.setAttribute('y1', tall ? -UNITS : 0);
    line.setAttribute('y2', tall ? UNITS * 2 : 1);
    line.setAttribute('stroke', '{surveys.INK}');
    line.setAttribute('stroke-opacity', '0.7');
    line.setAttribute('stroke-width', '1');
    line.setAttribute('vector-effect', 'non-scaling-stroke');
    line.setAttribute('pointer-events', 'none');
    line.setAttribute('display', 'none');
    svg.appendChild(line);
    return line;
  }});
  function forget() {{
    cursors.forEach(function (line) {{ line.setAttribute('display', 'none'); }});
    if (read) {{ read.textContent = hint; }}
  }}
  function point(x) {{
    var box = price.getBoundingClientRect();
    if (!read || !box.width || x < box.left || x > box.right) {{ forget(); return; }}
    var i = Math.floor(win[0] + (x - box.left) / box.width * win[1]);
    i = Math.max(0, Math.min(N - 1, i));
    cursors.forEach(function (line) {{
      line.setAttribute('x1', i + 0.5);
      line.setAttribute('x2', i + 0.5);
      line.setAttribute('display', 'inline');
    }});
    var names = [], rows = 0;
    grid.querySelectorAll('button.htog[aria-pressed="true"]').forEach(function (b) {{
      var list = runs[b.dataset.row];
      if (!list) {{ return; }}
      rows++;
      if (list.some(function (r) {{ return i >= r[0] && i < r[0] + r[1]; }})) {{
        names.push(b.textContent);
      }}
    }});
    var day = new Date(DAYS[i]);
    read.textContent = NAMES[day.getUTCMonth()] + ' ' + day.getUTCDate() + ', ' + day.getUTCFullYear()
      + ' \u00b7 ' + names.length + ' of ' + rows + ' on'
      + (names.length ? ': ' + names.join(' \u00b7 ') : '');
  }}
  grid.addEventListener('pointermove', function (e) {{ point(e.clientX); }});
  grid.addEventListener('pointerdown', function (e) {{ point(e.clientX); }});
  grid.addEventListener('pointerleave', function (e) {{
    if (e.pointerType === 'mouse') {{ forget(); }}      // a tap's reading stays put
  }});

  // Put back what the reader left: each choice goes through its own button.
  var kept = load();
  document.querySelectorAll('.hwin button').forEach(function (b) {{
    if (+b.dataset.sessions === kept.window && b.getAttribute('aria-pressed') !== 'true') {{ b.click(); }}
  }});
  shades.forEach(function (b) {{
    if (b.dataset.shade === kept.shade && b.getAttribute('aria-pressed') !== 'true') {{ b.click(); }}
  }});
  grid.querySelectorAll('button.htog').forEach(function (b) {{
    var want = (kept.rows || {{}})[b.dataset.row];
    if (typeof want === 'boolean' && want !== (b.getAttribute('aria-pressed') === 'true')) {{ b.click(); }}
  }});
}})();
</script>
</body>
</html>
"""


def write(path, snap, colors, **kw):
    """Render and write with LF line ends, the bytes publish_pages compares."""
    Path(path).write_text(render(snap, colors, **kw), encoding="utf-8", newline="")
