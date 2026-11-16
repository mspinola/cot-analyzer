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
    assert wanted == set(data) == {st.FOMO_KEY, st.APPETITE_KEY, st.CREDIT_KEY,
                                   st.ROTATION_KEY}
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
    assert data[st.CREDIT_KEY] == view.trend_chart(snap.credit)
    assert [lv["value"] for lv in data[st.FOMO_KEY]["levels"]] == [80.0, 25.0]
    assert [lv["value"] for lv in data[st.APPETITE_KEY]["levels"]] == [80.0, 20.0]
    assert data[st.FOMO_KEY]["range"] == data[st.APPETITE_KEY]["range"] == [0, 100]
    # The trend charts draw the line and its average; an average before its window
    # fills is dropped, never drawn at zero.
    line, average = data[st.ROTATION_KEY]["series"]
    assert len(average["data"]) <= len(line["data"])


def test_the_sparklines_are_inline_svg_one_per_table_row():
    snap = _snap()
    page = st.render(snap, COLORS)
    assert page.count('<svg class="spark"') == len(snap.assets) == len(mi.ASSET_SYMBOLS)
    xs = [float(pt.split(",")[0]) for pt in view.spark_points(snap.assets[0]).split()]
    ys = [float(pt.split(",")[1]) for pt in view.spark_points(snap.assets[0]).split()]
    assert min(xs) >= 0 and max(xs) <= view.SPARK_WIDTH
    assert min(ys) >= 0 and max(ys) <= view.SPARK_HEIGHT


def test_the_readings_strip_has_a_tile_per_read_and_one_for_credit_appetite():
    snap = _snap()
    tiles = view.tiles(snap)
    assert [t["key"] for t in tiles] == ["fomo", "net_highs", "advance", "credit",
                                         "rotation", "updown", "appetite"]
    page = st.render(snap, COLORS)
    strip = page.split(f'id="{st.READINGS_ID}"')[1].split('<div class="cards">')[0]
    assert strip.count('class="tile ') == 7
    for t in tiles:
        assert f'<div class="value">{html.escape(t["value"])}</div>' in strip
        assert f'<div class="tier">{html.escape(t["state"])}</div>' in strip
    # Only the two 0-100 reads carry the gauge.
    assert strip.count('class="gauge"') == 2
    assert tiles[-1]["context"] == "context, not counted"


def test_credit_appetite_is_drawn_and_described_but_not_counted():
    snap = _snap()
    assert snap.appetite is not None
    page = st.render(snap, COLORS)
    assert f"<h2>{html.escape(view.APPETITE_TITLE)}</h2>" in page
    assert html.escape(view.appetite_status(snap.appetite, snap.credit)) in page
    assert len(mi.read_verdicts(snap)) == 6          # the count is still of six reads
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
    assert page.count("How to read this") >= 6


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
    lean, count = mi.headline(snap)
    assert lean in page and count in page
    assert f'<span class="big">{snap.fomo.value:.1f}</span>' in page
    assert f'<span class="big">{snap.credit.value:.2f}</span>' in page
    assert f'<span class="big">{snap.rotation.value:.4f}</span>' in page
    assert view.credit_detail(snap.credit) in page
    for read in snap.net_highs:
        assert f"{read.highs} highs, {read.lows} lows" in page
    for read in snap.updown:
        assert f">{read.ratio:.2f}</span>" in page
    for row in snap.assets:
        assert f'<td class="name num">{row.last:,.2f}</td>' in page
    for title in (view.FOMO_TITLE, view.APPETITE_TITLE, view.NET_HIGHS_TITLE,
                  view.CREDIT_TITLE, view.ROTATION_TITLE, view.UPDOWN_TITLE,
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
