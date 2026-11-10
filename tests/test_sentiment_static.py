"""The published copy of the sentiment page (surveys.bluemagicai.com).

What is pinned: every lookback the toggle offers is embedded and parses back, the
local-only line is gone from the published notes and still on the app's, an empty read
refuses to render rather than publishing an empty page, the JSON cannot close its
script element early, `generated_at` carries the spelling publish_pages masks, and the
CDN build is the plotly.js the installed plotly.py bundles. Store-free, as test_sentiment.
"""
import json
import re

import plotly.offline
import pytest

import components.sentiment as s
from components import sentiment_static as st
from tests.test_sentiment import COLORS, PALETTE, _fixtures, _no_cot_store  # noqa: F401 (autouse)


def _reads():
    _, get_bars = _fixtures()
    return {y: s.build_read(get_bars, lookback_years=y) for y in s.LOOKBACK_YEARS}


def _payload(page):
    m = re.search(r'<script type="application/json" id="surveys-data">(.*?)</script>',
                  page, re.S)
    return json.loads(m.group(1))


def test_every_lookback_is_embedded_with_both_figures():
    page = st.render(_reads(), COLORS, PALETTE, generated_at="2026-11-09T12:00Z",
                     clientside_js="")
    data = _payload(page)
    assert set(data) == {str(y) for y in s.LOOKBACK_YEARS}
    for entry in data.values():
        assert entry["price"]["data"] and entry["columns"]["data"]
        assert entry["summary"].startswith("On the ")
    assert data["1"]["summary"] != data["3"]["summary"]


def test_the_published_notes_drop_the_local_only_line_and_the_app_keeps_it():
    reads = _reads()
    page = st.render(reads, COLORS, PALETTE, clientside_js="")
    assert "Local only" not in page and "local only" not in page
    assert any("Local only" in p for p in s.caption(reads[s.DEFAULT_LOOKBACK]))


def test_an_empty_read_refuses_to_render():
    reads = _reads()
    empty = s.SentimentRead(frame=reads[1].frame.iloc[:0], last={},
                            awaiting=(s.NAAIM,), lookback_years=1)
    with pytest.raises(ValueError, match="empty"):
        st.render({**reads, 1: empty}, COLORS, PALETTE, clientside_js="")
    with pytest.raises(ValueError, match="default lookback"):
        st.render({1: reads[1]}, COLORS, PALETTE, clientside_js="")


def test_the_json_cannot_close_its_script_element():
    assert st._script_json({"t": "</script><b>"}) == '{"t":"<\\/script><b>"}'


def test_generated_at_uses_the_spelling_publish_pages_masks():
    page = st.render(_reads(), COLORS, PALETTE, generated_at="2026-11-09T12:00Z",
                     clientside_js="")
    assert '"generated_at":"2026-11-09T12:00Z"' in page
    # Only there: a stamp anywhere else would make every rebuild look like a change.
    assert page.count("2026-11-09T12:00Z") == 1


def test_the_page_inlines_the_apps_refit_handler():
    page = st.render(_reads(), COLORS, PALETTE, clientside_js="")
    assert "autoscale_y_axes" not in page.split("surveys-data")[0]   # sanity: not in head
    full = st.render(_reads(), COLORS, PALETTE)
    assert "autoscale_y_axes: function" in full


def test_the_page_loads_the_plotly_js_its_plotly_py_bundles():
    page = st.render(_reads(), COLORS, PALETTE, clientside_js="")
    version = plotly.offline.get_plotlyjs_version()
    assert f'src="https://cdn.plot.ly/plotly-{version}.min.js"' in page


def test_a_phone_drops_two_zoom_buttons_and_keeps_the_short_ones():
    """Nine buttons overrun a phone-width plot; the page drops 2Y and 15Y there only."""
    html = st.render(_reads(), COLORS, PALETTE)
    assert f"window.matchMedia('{st.PHONE_QUERY}')" in html
    assert '["2Y","15Y"]' in html and "fitted(fig.layout)" in html
    assert not {"3M", "6M"} & set(st.PHONE_HIDDEN_RANGES)


def test_a_phone_lifts_the_zoom_buttons_above_the_top_panel_title():
    """Level with the title, the seven buttons left on a phone drew over it."""
    html = st.render(_reads(), COLORS, PALETTE)
    assert f"margin.t = (margin.t || 0) + {st.PHONE_BUTTON_LIFT_PX};" in html
    assert f"y: 1 + {st.PHONE_BUTTON_LIFT_PX} / plotH" in html


def test_the_monitor_row_matches_the_fund_pages_and_marks_this_page():
    """The same row dbmf-tracker's three templates carry (its tests/test_site_nav.py
    pins the same list), with Surveys current and the app's own Market Internals page
    linked as "Market"."""
    links = re.findall(r'<a [^>]*href="([^"]+)"[^>]*>([^<]+)</a>', st._nav())
    assert links == [("https://dbmf.bluemagicai.com/", "DBMF"),
                     ("https://ahlt.bluemagicai.com/", "AHLT"),
                     ("https://orr.bluemagicai.com/", "ORR"),
                     ("https://surveys.bluemagicai.com/", "Surveys"),
                     ("https://bluemagicai.com/internals", "Market"),
                     ("https://bluemagicai.com/", "COT Analyzer &rarr;")]
    assert re.findall(r'aria-current="page"[^>]*>([^<]+)<', st._nav()) == ["Surveys"]
    # The fund pages' placeholder for the monitor not yet published, in their slot.
    soon = re.search(r'<span class="soon"[^>]*>KISS <small>soon</small></span>', st._nav())
    assert soon and st._nav().index("ORR</a>") < soon.start() < st._nav().index("Surveys")


def test_the_header_is_the_fund_pages_header_with_the_surveys_dates():
    """Eyebrow, accent ticker in the title, and an as-of on the right naming each
    survey's newest week. No build stamp in it: publish_pages masks only the JSON
    one, so a visible stamp would force a push on every rebuild."""
    reads = _reads()
    page = st.render(reads, COLORS, PALETTE, generated_at="2026-11-09T12:00Z",
                     clientside_js="")
    head = re.search(r'<header class="top">.*?</header>', page, re.S).group(0)
    assert f'<div class="eyebrow">{st.EYEBROW}</div>' in head
    assert '<h1><span class="tk">Surveys</span> NAAIM and AAII</h1>' in head
    last = reads[s.DEFAULT_LOOKBACK].last
    for key, label in (("naaim", "NAAIM"), ("aaii", "AAII")):
        assert f"{label} <b>{st._date(last[key])}</b>" in head
    assert "2026-11-09T12:00Z" not in head
    assert page.count("<h1") == 1
