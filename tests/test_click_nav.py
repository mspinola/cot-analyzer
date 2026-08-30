"""A board click resolves to the Market Detail link, or to nothing at all.

The destination rides on the clicked point's customdata (set by the Strip's head
mark and the Crowd board's hoverable traces); everything else about the click is
noise. The nothing-cases matter as much as the happy path: a click on a
decorative trace, a cleared clickData, or malformed points must stay put rather
than navigate to a broken URL.
"""

from app_utils import clicked_market_href


def test_a_click_resolves_to_the_market_detail_link():
    click = {'points': [{'customdata': 'Japanese Yen', 'x': 61, 'y': 4}]}
    assert clicked_market_href(click) == '/oi_alignment?asset=Japanese%20Yen'


def test_clicks_without_a_market_go_nowhere():
    assert clicked_market_href(None) is None
    assert clicked_market_href({}) is None
    assert clicked_market_href({'points': []}) is None
    assert clicked_market_href({'points': [{'x': 61, 'y': 4}]}) is None
    # A trace whose customdata is not a name (a list, a number) is decorative.
    assert clicked_market_href({'points': [{'customdata': 3}]}) is None
    assert clicked_market_href({'points': [{'customdata': ''}]}) is None
