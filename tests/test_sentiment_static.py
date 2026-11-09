"""The published copy of the sentiment page (surveys.bluemagicai.com).

What is pinned: every lookback the toggle offers is embedded and parses back, the
local-only line is gone from the published notes and still on the app's, an empty read
refuses to render rather than publishing an empty page, the JSON cannot close its
script element early, `generated_at` carries the spelling publish_pages masks, and the
CDN build is the plotly.js plotly.py serializes for. Store-free, as test_sentiment.
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


def test_the_cdn_build_matches_plotly_py():
    assert plotly.offline.get_plotlyjs_version() == st.PLOTLY_VERSION
