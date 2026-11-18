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
