"""Cache-Control by path class, pinned against what was measured at the origin.

Nginx passes origin headers through untouched, so this policy IS the edge's
behaviour. The rules worth pinning: fingerprinted things cache for a year and
say `immutable`, un-fingerprinted assets keep Dash's revalidation (their URL
never changes, so a long cache would be a stale file forever), the dash
endpoints refuse storage outright, and the HTML shell revalidates.
"""

from routing import cache_policy

YEAR = 'public, max-age=31536000, immutable'


def test_component_suites_cache_for_a_year_immutably():
    assert cache_policy('/_dash-component-suites/dash/deps/polyfill@7.min.js',
                        False, 'application/javascript') == YEAR


def test_fingerprinted_assets_cache_for_a_year():
    """Dash links every asset as /assets/x.css?m=<mtime>; the URL changes when
    the file does, which is what makes a year safe."""
    assert cache_policy('/assets/custom.css', True, 'text/css') == YEAR


def test_a_bare_asset_url_keeps_revalidating():
    """The same file WITHOUT the fingerprint has a URL that never changes, so a
    long cache there is a stale stylesheet forever. None means "leave Dash's
    no-cache + ETag alone"."""
    assert cache_policy('/assets/custom.css', False, 'text/css') is None


def test_the_dash_endpoints_refuse_storage():
    for path in ('/_dash-layout', '/_dash-dependencies',
                 '/_dash-update-component'):
        assert cache_policy(path, False, 'application/json') == 'no-store'


def test_documents_revalidate():
    """The shell is small and its script URLs carry the fingerprints doing the
    real caching; with no directive at all, browsers apply heuristic caching,
    and a heuristically cached layout is a stale page."""
    assert cache_policy('/', False, 'text/html; charset=utf-8') == 'no-cache'
    assert cache_policy('/heatmap', False, 'text/html; charset=utf-8') == 'no-cache'


def test_everything_else_is_left_alone():
    assert cache_policy('/_favicon.ico', False, 'image/x-icon') is None
    assert cache_policy('/_dash-component-suites-lookalike', False,
                        'text/plain') is None


def test_dated_weekly_reports_cache_for_a_day_and_the_index_does_not():
    """The dated pages are the most expensive renders the app serves and barely
    change once their week passes; the index gains a row per release and must
    not read stale on a Friday."""
    assert cache_policy('/weekly/2026-08-25', False,
                        'text/html; charset=utf-8') == 'public, max-age=86400'
    assert cache_policy('/weekly', False, 'text/html; charset=utf-8') == 'no-cache'
