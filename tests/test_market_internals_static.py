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


def _snap(drop=()):
    frames = {k: v for k, v in _universe().items() if k not in drop}
    return mi.build_snapshot(_bars(frames))


def _payload(page):
    m = re.search(rf'<script type="application/json" id="{st.DATA_ID}">(.*?)</script>',
                  page, re.S)
    return json.loads(m.group(1))


def test_every_plot_element_has_its_figure_and_nothing_is_embedded_unused():
    snap = _snap()
    page = st.render(snap, COLORS)
    data = _payload(page)
    wanted = set(re.findall(r'data-fig="([^"]+)"', page))
    assert wanted == set(data)
    assert wanted == {st.FOMO_KEY, st.CREDIT_KEY, st.ROTATION_KEY,
                      *(st.SPARK_PREFIX + s for s in mi.ASSET_SYMBOLS)}
    for fig in data.values():
        assert fig["data"] and fig["layout"]


def test_the_figures_are_the_app_pages_own():
    """The embedded FOMO and credit figures are the shared builders' output, the ones
    `pages/analytics/internals.py` hands to dcc.Graph."""
    snap = _snap()
    data = _payload(st.render(snap, COLORS))
    assert data[st.FOMO_KEY] == json.loads(view.fomo_figure(snap.fomo, COLORS).to_json())
    assert data[st.CREDIT_KEY] == json.loads(view.trend_figure(snap.credit).to_json())


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
    for title in (view.FOMO_TITLE, view.NET_HIGHS_TITLE, view.ADVANCE_DECLINE_TITLE,
                  view.CREDIT_TITLE, view.ROTATION_TITLE, view.UPDOWN_TITLE,
                  view.ASSETS_TITLE):
        assert f"<h2>{title}</h2>" in page
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
    assert st.SPARK_PREFIX + "IBIT" not in _payload(page)
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


def test_the_header_names_the_newest_session_and_the_plotly_build():
    snap = _snap()
    page = st.render(snap, COLORS)
    assert f"Through <b>{st._date(snap.date)}</b>" in page
    assert f'<span class="tk">{st.H1_TICKER}</span> {st.H1_REST}' in page
    assert f'<script src="{surveys.plotly_js_url()}"' in page
    assert "staticPlot: true" in page


def test_the_publish_key_is_allowlisted_for_the_view_beacon():
    """publish_internals.sh sends `--key internals`; unlisted, its views are dropped."""
    assert external_page_path("internals") == "/internals"
