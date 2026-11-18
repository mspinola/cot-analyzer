"""The published copy of the market internals page.

What is pinned: the static page says what the snapshot says (the same headline, the
same numbers through the shared view module), every figure it has an element for is
embedded and parses back, a snapshot with no reads refuses to render rather than
publishing six "awaiting" cards, a partly-served store renders with the missing
symbols named, `generated_at` carries the spelling publish_pages masks and is the only
thing a rebuild changes, and the monitors row marks this page. Store-free.
"""
import html
import json
import re

import pandas as pd
import pytest

import components.market_internals as mi
import components.market_internals_view as view
from components import market_internals_static as st
from components import sentiment_static as surveys
from routing import external_page_path
from tests.test_market_internals import _bars, _universe
from tests.test_sentiment import COLORS

#: Sessions in the synthetic store: enough for the credit appetite gauge, which needs its
#: 20-day average and then 252 previous sessions to rank against.
N = 320


def _snap(drop=()):
    frames = {k: v for k, v in _universe(N).items() if k not in drop}
    return mi.build_snapshot(_bars(frames))


def _payload(page):
    m = re.search(rf'<script type="application/json" id="{st.DATA_ID}">(.*?)</script>',
                  page, re.S)
    return json.loads(m.group(1))


def test_every_chart_element_has_its_data_and_nothing_is_embedded_unused():
    snap = _snap()
    page = st.render(snap, COLORS)
    data = _payload(page)
    wanted = set(re.findall(r'data-chart="([^"]+)"', page))
    assert wanted == set(data) == {st.FOMO_KEY, st.APPETITE_KEY,
                                   *(st.HEADWIND_PREFIX + k for k in mi.HEADWIND_KEYS)}
    for spec in data.values():
        assert spec["series"] and all(s["data"] for s in spec["series"])
        # Lightweight Charts wants ascending yyyy-mm-dd times and no missing values.
        for s in spec["series"]:
            times = [pt["time"] for pt in s["data"]]
            assert times == sorted(set(times))
            assert all(pt["value"] == pt["value"] for pt in s["data"])


def test_the_charts_are_the_view_modules_own_and_carry_their_levels():
    snap = _snap()
    colors = st.page_colors(COLORS)
    data = _payload(st.render(snap, COLORS))
    assert data[st.FOMO_KEY] == view.fomo_chart(snap.fomo, colors)
    assert [lv["value"] for lv in data[st.FOMO_KEY]["levels"]] == [80.0, 25.0]
    assert [lv["value"] for lv in data[st.APPETITE_KEY]["levels"]] == [80.0, 20.0]
    assert data[st.FOMO_KEY]["range"] == data[st.APPETITE_KEY]["range"] == [0, 100]
    by_key = {h.key: data[st.HEADWIND_PREFIX + h.key] for h in snap.headwinds}
    # A level read draws one line against the level it turns on; a read against its
    # own average draws the two lines and no level.
    assert [lv["value"] for lv in by_key["net_highs"]["levels"]] == [0.0]
    assert [lv["value"] for lv in by_key["qqq_updown"]["levels"]] == [1.0]
    assert len(by_key["net_highs"]["series"]) == 1
    for key in ("credit", "rotation"):
        assert len(by_key[key]["series"]) == 2 and by_key[key]["levels"] == []


def test_each_headwind_card_says_its_state_what_flips_it_and_for_how_long():
    snap = _snap()
    page = st.render(snap, COLORS)
    section = page.split(f'id="{st.HEADWINDS_ID}"')[1].split('<div class="sec">')[0]
    assert section.count('<section class="card hw ') == len(snap.headwinds) == 5
    for h in snap.headwinds:
        card = section.split(f'data-key="{h.key}"')[1].split("</section>")[0]
        assert f'<span class="big">{html.escape(h.display)}</span>' in card
        assert f">{view.headwind_badge(h)}</span>" in card
        assert html.escape(h.flip) in card
        assert view.headwind_streak(h) in card
        if h.versus:
            assert view.headwind_versus(h) in card
    count, lean = mi.headline(snap)
    number, _, rest = count.partition(" ")
    assert f">{number}</b> {rest}</p>" in page and lean in page


def test_fomo_is_on_the_page_but_outside_the_count():
    snap = _snap()
    page = st.render(snap, COLORS)
    uncounted = page.split(f"<h2>{view.UNCOUNTED_TITLE}</h2>")[1].split(
        f"<h2>{view.DETAIL_TITLE}</h2>")[0]
    assert f"<h2>{html.escape(view.FOMO_TITLE)}</h2>" in uncounted
    assert f"<h2>{html.escape(view.APPETITE_TITLE)}</h2>" in uncounted
    assert view.fomo_recent(snap.fomo) in uncounted
    assert view.fomo_recent(snap.fomo).count("→") == 4


def test_the_sparklines_are_inline_svg_one_per_table_row():
    snap = _snap()
    page = st.render(snap, COLORS)
    assert page.count('<svg class="spark"') == len(snap.assets) == len(mi.ASSET_SYMBOLS)
    xs = [float(pt.split(",")[0]) for pt in view.spark_points(snap.assets[0]).split()]
    ys = [float(pt.split(",")[1]) for pt in view.spark_points(snap.assets[0]).split()]
    assert min(xs) >= 0 and max(xs) <= view.SPARK_WIDTH
    assert min(ys) >= 0 and max(ys) <= view.SPARK_HEIGHT


def test_credit_appetite_is_drawn_and_described_but_not_counted():
    snap = _snap()
    assert snap.appetite is not None
    page = st.render(snap, COLORS)
    assert f"<h2>{html.escape(view.APPETITE_TITLE)}</h2>" in page
    assert html.escape(view.appetite_status(snap.appetite, snap.credit)) in page
    assert "appetite" not in mi.HEADWIND_KEYS
    without = mi.build_snapshot(_bars({k: v for k, v in _universe(N).items()
                                       if k != mi.APPETITE_TREASURY}))
    assert without.appetite is None
    assert mi.headline(without) == mi.headline(snap)


def test_the_page_opens_with_the_surveys_stylesheet():
    """One stylesheet for the family: the tokens, header, tiles and cards are the
    surveys page's own text, not a copy that can drift."""
    page = st.render(_snap(), COLORS)
    assert surveys.base_css() in page
    assert f"--page: {surveys.PAGE_COLOR}" in page
    assert f"max-width: {surveys.PAGE_MAX_WIDTH_PX}px" in page
    assert page.count("How to read this") >= 4


def test_the_chart_library_is_pinned_and_attributed():
    """An exact release from unpkg, and the licence's notice and link in the footer
    (which is why the per-chart logo may be off)."""
    page = st.render(_snap(), COLORS)
    assert re.fullmatch(r"\d+\.\d+\.\d+", st.LIGHTWEIGHT_CHARTS_VERSION)
    assert (f'<script src="https://unpkg.com/lightweight-charts@'
            f'{st.LIGHTWEIGHT_CHARTS_VERSION}/dist/') in page
    footer = page.split("<footer>")[1].split("</footer>")[0]
    assert st.ATTRIBUTION in footer and 'href="https://www.tradingview.com/"' in footer
    assert "attributionLogo: false" in page
    assert "plotly" not in page.lower()
    # Panning a chart would take the page's scroll on a phone.
    assert "handleScroll: false, handleScale: false" in page


def test_the_page_says_what_the_snapshot_says():
    snap = _snap()
    page = st.render(snap, COLORS)
    assert f'<span class="big">{snap.fomo.value:.1f}</span>' in page
    for read in snap.net_highs:
        assert f"{read.highs} highs, {read.lows} lows" in page
    for row in snap.assets:
        assert f'<td class="name num">{row.last:,.2f}</td>' in page
    for title in (view.HEADWINDS_TITLE, view.UNCOUNTED_TITLE, view.DETAIL_TITLE,
                  view.FOMO_TITLE, view.APPETITE_TITLE, view.NET_HIGHS_TITLE,
                  view.ASSETS_TITLE):
        assert f"<h2>{html.escape(title)}</h2>" in page
    assert f"<h3>{view.ADVANCE_DECLINE_TITLE}</h3>" in page
    assert html.escape(view.FOOTER) in page


def test_a_snapshot_with_no_reads_refuses_to_render(tmp_path):
    """A store that cannot be read must not replace the published page."""
    empty = mi.build_snapshot(_bars({}))
    with pytest.raises(ValueError, match="no reads"):
        st.render(empty, COLORS)
    out = tmp_path / "internals.html"
    with pytest.raises(ValueError):
        st.write(out, empty, COLORS)
    assert not out.exists()


def test_a_partly_served_store_renders_and_names_what_is_missing():
    """The app page's rule: a series not delivered yet is named, not drawn or raised."""
    snap = _snap(drop=(mi.FOMO_SYMBOL, "IBIT"))
    page = st.render(snap, COLORS)
    assert view.awaiting_text([mi.FOMO_SYMBOL]) in page
    assert st.FOMO_KEY not in _payload(page)
    assert page.count('<svg class="spark"') == len(mi.ASSET_SYMBOLS) - 1
    assert "awaiting data</td>" in page
    assert f"Awaiting data for: {', '.join(snap.awaiting)}." in page


def test_a_rebuild_differs_only_in_the_stamp_publish_pages_masks():
    """publish_pages pushes nothing when the pages match with `"generated_at":"..."`
    blanked, so that must be the only place a build time appears."""
    snap = _snap()
    a = st.render(snap, COLORS, generated_at="2026-11-10T01:15Z")
    b = st.render(snap, COLORS, generated_at="2026-11-11T01:15Z")
    assert a != b and '"generated_at":"2026-11-10T01:15Z"' in a

    def mask(t):
        return re.sub(r'"generated_at":"[^"]*"', '"generated_at":""', t)
    assert mask(a) == mask(b)


def test_the_json_cannot_close_its_script_element_early():
    page = st.render(_snap(), COLORS)
    body = re.search(rf'id="{st.DATA_ID}">(.*?)</script>', page, re.S).group(1)
    assert "</" not in body


def test_the_monitor_row_is_the_surveys_pages_with_this_page_current():
    nav = st._nav()
    links = re.findall(r'<a [^>]*href="([^"]+)"[^>]*>([^<]+)</a>', nav)
    assert links == re.findall(r'<a [^>]*href="([^"]+)"[^>]*>([^<]+)</a>', surveys._nav())
    assert re.findall(r'aria-current="page"[^>]*>([^<]+)<', nav) == [st.CURRENT]
    assert st.CURRENT in [name for name, _ in surveys.SITES]


def test_the_header_names_the_newest_session():
    snap = _snap()
    page = st.render(snap, COLORS)
    assert f"Through <b>{st._date(snap.date)}</b>" in page
    assert f'<span class="tk">{st.H1_TICKER}</span> {st.H1_REST}' in page


def test_the_publish_key_is_allowlisted_for_the_view_beacon():
    """publish_internals.sh sends `--key internals`; unlisted, its views are dropped."""
    assert external_page_path("internals") == "/internals"


def test_the_page_and_its_charts_use_the_family_ink():
    """Text, chart lines and axis labels in the fund pages' white and grey
    (`sentiment_static.INK` / `INK_2`), never the app's cream."""
    import viz_constants as vc
    page = st.render(_snap(), COLORS)
    lowered = page.lower()
    assert vc.TEXT_COLOR.lower() not in lowered
    assert vc.BRIGHTER_TEXT_COLOR.lower() not in lowered
    data = _payload(page)
    assert data[st.FOMO_KEY]["series"][0]["color"] == surveys.INK
    assert f"var INK = '{surveys.INK_2}'" in page


def test_the_history_card_draws_a_strip_per_headwind_aligned_to_the_session():
    snap = _snap()
    h = snap.history
    page = st.render(snap, COLORS)
    card = page.split(f"<h2>{view.HISTORY_TITLE}</h2>")[1].split("</section>")[0]
    n = len(h.dates)
    # Every SVG is one unit a session wide, so a mark's x is its session index.
    assert card.count(f'viewBox="0 0 {n} 1"') == len(mi.HEADWIND_KEYS) + 1
    assert f'viewBox="0 0 {n} {view.HISTORY_PRICE_UNITS:g}"' in card
    for key, label, flags in h.rows:
        strip = card.split(f'data-row="{key}"')[1].split("</svg>")[0]
        assert strip.count("<rect") == len(view.runs(flags))
        assert html.escape(label) in card
    every = [c == h.total for c in h.count]
    assert card.split('data-row="all"')[1].split("</svg>")[0].count("<rect") == len(view.runs(every))
    assert html.escape(view.history_summary(h)) in card
    assert "no claim is made here about what followed" in card


def test_history_geometry_runs_points_and_year_ticks():
    assert view.runs([False, True, True, False, True]) == [(1, 2), (4, 1)]
    assert view.runs([]) == [] and view.runs([True, True]) == [(0, 2)]
    h = _snap().history
    points = [tuple(float(v) for v in pt.split(",")) for pt in
              view.history_price_points(h).split()]
    assert points[0][0] == 0 and points[-1][0] == len(h.dates) - 1
    assert all(0 <= y <= view.HISTORY_PRICE_UNITS for _, y in points)
    assert min(y for _, y in points) == 0 or max(y for _, y in points) == view.HISTORY_PRICE_UNITS
    ticks = view.history_year_ticks(h)
    assert all(0 < fraction < 1 and int(year) % view.HISTORY_TICK_YEARS == 0
               for fraction, year in ticks)


def test_the_history_summary_counts_occurrences_and_names_the_longest():
    dates = tuple(f"2026-01-{d:02d}" for d in range(1, 11))
    h = mi.HeadwindHistory(dates=dates, price=(1.0,) * 10, price_symbol="QQQ", rows=(),
                           count=(5, 5, 5, 1, 1, 1, 1, 1, 1, 5), total=5)
    text = view.history_summary(h)
    assert text.startswith("All 5 were on at once on 4 of 10 sessions since 2026 (40%), in 1 ")
    assert "2026-01 to 2026-01 (4 sessions)" in text
    quiet = mi.HeadwindHistory(dates=dates, price=(1.0,) * 10, price_symbol="QQQ", rows=(),
                               count=(2,) * 10, total=5)
    assert view.history_summary(quiet) == "All 5 have never been on at once since 2026."


def test_a_page_without_the_history_still_renders():
    snap = _snap(drop=("NYSE_NL52W",))
    assert snap.history is None
    assert view.HISTORY_TITLE not in st.render(snap, COLORS)


def test_the_history_card_offers_windows_and_opens_on_everything():
    """1Y to Max, zooming every row together. Max is pressed as rendered, so the page
    without its script is the whole history; a window longer than the history is not
    offered."""
    snap = _snap()
    n = len(snap.history.dates)
    page = st.render(snap, COLORS)
    card = page.split(f"<h2>{view.HISTORY_TITLE}</h2>")[1].split("</section>")[0]
    offered = re.findall(r'<button type="button" data-sessions="(\d+)" aria-pressed="(\w+)">'
                         r'(\w+)</button>', card)
    assert offered == [(str(sessions), "true" if label == "Max" else "false", label)
                       for label, sessions in view.HISTORY_WINDOWS if sessions < n]
    assert ("Max" in [label for _, _, label in offered]) and len(offered) >= 2
    assert f'id="{st.HISTORY_ID}" data-sessions="{n}"' in card
    # The script zooms by viewBox and refits the price to the window on screen.
    assert "svg.setAttribute('viewBox'" in page and f"getElementById('{st.HISTORY_ID}')" in page


def test_the_axis_carries_every_month_start_for_the_script_to_label_any_window():
    h = _snap().history
    months = view.history_month_starts(h)
    assert months[0] == [0, h.dates[0][:7]]
    assert [m for _, m in months] == sorted({d[:7] for d in h.dates})
    assert all(h.dates[i][:7] == m and (i == 0 or h.dates[i - 1][:7] != m) for i, m in months)
    page = st.render(_snap(), COLORS)
    raw = re.search(r'data-months="([^"]*)"', page).group(1)
    assert json.loads(html.unescape(raw)) == months


def test_the_price_line_is_daily_where_a_zoom_will_look():
    """Weekly points are fine at nineteen years across; a one-year window needs the
    daily line, so the most recent sessions keep every point."""
    dates = tuple(d.strftime("%Y-%m-%d") for d in pd.bdate_range("2015-01-01", periods=2000))
    h = mi.HeadwindHistory(dates=dates, price=tuple(100.0 + i for i in range(2000)),
                           price_symbol="QQQ", rows=(), count=(0,) * 2000, total=5)
    xs = [int(pt.split(",")[0]) for pt in view.history_price_points(h).split()]
    recent = 2000 - view.HISTORY_DAILY_SESSIONS
    assert xs[-view.HISTORY_DAILY_SESSIONS:] == list(range(recent, 2000))
    older = [x for x in xs if x < recent]
    assert older == list(range(0, recent, view.HISTORY_PRICE_STEP))


def _with_volatility(inverted=False):
    frames = _universe(N)
    idx = frames["QQQ"].index
    frames[mi.VOLATILITY_SYMBOL] = pd.DataFrame({"Close": 24.0 if inverted else 18.0}, index=idx)
    frames[mi.VOLATILITY_TERM_SYMBOL] = pd.DataFrame({"Close": 21.0}, index=idx)
    return mi.build_snapshot(_bars(frames))


def test_the_volatility_card_is_drawn_outside_the_count():
    snap = _with_volatility(inverted=True)
    page = st.render(snap, COLORS)
    uncounted = page.split(f"<h2>{view.UNCOUNTED_TITLE}</h2>")[1].split('<div class="sec">')[0]
    assert f"<h2>{html.escape(view.VOLATILITY_TITLE)}</h2>" in uncounted
    assert '<span class="big">24.0</span>' in uncounted and ">Inverted</span>" in uncounted
    assert html.escape(view.volatility_status(snap.volatility)) in uncounted
    spec = _payload(page)[st.VOLATILITY_KEY]
    assert len(spec["series"]) == 2 and spec["levels"] == []
    assert mi.headline(snap) == mi.headline(_snap())
    assert ">Normal</span>" in st.render(_with_volatility(), COLORS)
    # Without the series there is no card and no chart, not an "awaiting" one.
    plain = st.render(_snap(), COLORS)
    assert view.VOLATILITY_TITLE not in plain and st.VOLATILITY_KEY not in _payload(plain)


def test_the_sentiment_and_positioning_strip_is_the_surveys_pages_tiles():
    """The survey tiles are `sentiment_static`'s own (number, percentile badge, gauge),
    with ES and NQ commercials in the same shape after them."""
    import components.sentiment as s
    from tests.test_sentiment_static import _reads
    survey = _reads()[s.DEFAULT_LOOKBACK]
    positioning = (mi.PositioningRead("S&P 500 futures", 0.51, -6.24, 59.0, "2026-11-10"),
                   mi.PositioningRead("Nasdaq 100 futures", -16.43, 11.05, 20.0, "2026-11-10"))
    page = st.render(_snap(), COLORS, survey=survey, positioning=positioning)
    strip = page.split(f"<h2>{view.POSITIONING_TITLE}</h2>")[1].split('<div class="sec">')[0]
    tiles = surveys.survey_tiles(survey) + view.positioning_tiles(positioning, st._date)
    assert strip.count('<div class="tile ') == len(tiles) == 4
    for t in tiles:
        assert f'<div class="value">{html.escape(t["value"])}</div>' in strip
    assert '<div class="value">+0.5%</div>' in strip
    # Positioning sits on its 26-week range (the COT index), not a percentile of
    # forty years; the surveys keep their percentile.
    assert "59<small> · 26-wk index</small>" in strip and "20<small> · 26-wk index</small>" in strip
    assert "Within its 26-week range" in strip and "Near its 26-week low" in strip
    assert strip.count("<small> pctl</small>") == len(surveys.survey_tiles(survey))
    assert 'class="tile tier-low" data-key="cot_nasdaq"' in strip
    assert '<i style="left:59%">' in strip
    assert "S&amp;P 500 futures, commercials" in strip
    assert "large speculators -6.2%" in strip and "Nov 10, 2026" in strip
    assert f'href="{st.SURVEYS_URL}"' in strip and st.SURVEYS_URL.startswith("https://surveys.")
    # Context only: with none of it the section is gone and the page is otherwise whole.
    plain = st.render(_snap(), COLORS)
    assert view.POSITIONING_TITLE not in plain
    assert mi.headline(_snap())[0].partition(" ")[2] in plain


def test_the_history_marks_are_the_headwind_cards_red():
    """A mark on the strips and a card's "Headwind" are one thing, so one colour: the
    page's toned red, not the amber the strips were first drawn in."""
    page = st.render(_snap(), COLORS)
    red = st.page_colors(COLORS).bear
    card = page.split(f"<h2>{view.HISTORY_TITLE}</h2>")[1].split("</section>")[0]
    assert f'fill="{red}"' in card and surveys.TONE_HIGH not in card
    assert f".hl.all {{ color: {red};" in page
