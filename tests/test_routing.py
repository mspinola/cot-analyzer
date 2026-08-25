"""Which paths the app admits to serving.

`use_pages=True` registers a catch-all `/<path:path>`, so before this policy existed
EVERY url returned 200 with a full app shell -- including the few hundred PHP webshell
paths a scanner tries. These pin the membership test in both directions, because both
are costly: admit too much and the 200-to-everything problem is back; admit too little
and a real page 404s, which is a worse outage than the one being fixed.

Pure, like `price_store_verdict` in test_price_store_guard: the registry and route list
are passed in, so nothing here needs a Dash app or a store.
"""
import pytest

from routing import is_known_path, not_found_page

# What the live app carries, as of the page registry at the time of writing. The nested
# and the underscored ones are the interesting entries: a naive "one path segment"
# guard passes the flat ones and breaks these.
PAGES = ['/', '/aggregation', '/analysis', '/categories', '/exposure', '/graphs',
         '/heatmap', '/oi_alignment', '/positioning', '/strip', '/citpy',
         '/citpy/view', '/about', '/admin', '/options', '/raw_data']

# `app.routes` as Dash builds it: the index plus its own endpoints.
DASH_ROUTES = ['/', '/_dash-layout', '/_dash-dependencies', '/_dash-update-component',
               '/_reload-hash', '/_favicon.ico']


def known(path):
    return is_known_path(path, PAGES, DASH_ROUTES)


# ── what must keep working ────────────────────────────────────────────────────

@pytest.mark.parametrize("path", PAGES)
def test_every_registered_page_is_served(path):
    assert known(path)


@pytest.mark.parametrize("path", DASH_ROUTES)
def test_every_dash_route_is_served(path):
    """Blocking these would break the app rather than merely mislabel a probe:
    `_dash-update-component` is every callback."""
    assert known(path)


@pytest.mark.parametrize("path", ['/exposure/', '/citpy/view/', '/'])
def test_a_trailing_slash_is_the_same_page(path):
    """Dash's client-side router treats the two spellings as one page. If the guard
    disagreed, a url a person can reach by typing it would 404 while the same page
    loaded without the slash."""
    assert known(path)


@pytest.mark.parametrize("path", [
    '/assets/style.css',
    '/static/x.js',
    '/_dash-component-suites/dash/dcc/async-graph.js',
    '/_dash-component-suites/plotly/package_data/plotly.min.js',
])
def test_generated_and_static_content_is_left_to_dash(path):
    """Membership stops at the prefix. Enumerating fingerprinted asset filenames would
    have to track a hash that changes on every dependency bump."""
    assert known(path)


@pytest.mark.parametrize("path", ['/favicon.ico', '/_favicon.ico'])
def test_the_browsers_automatic_favicon_request_is_not_a_probe(path):
    """Requested by every browser without being in the page registry."""
    assert known(path)


# ── what must not ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    '/shell.php', '/wp-is.php', '/xxx.php', '/404.php', '/mail.php', '/x7.php',
    '/wp-admin/', '/.env', '/config.json', '/totally-bogus-xyz',
])
def test_scanner_traffic_is_not_served(path):
    """Real paths from one hour of this deployment's access log, every one of which
    used to return 200 and a full app shell."""
    assert not known(path)


def test_a_page_prefix_does_not_admit_everything_under_it():
    """`/exposure` being real must not make `/exposure/../etc` or an arbitrary child
    real. Only the registry decides, and no page declares a path template."""
    assert not known('/exposure/../etc')
    assert not known('/exposure/anything')


def test_an_empty_page_path_is_ignored():
    """`page_registry` entries can carry `path=None`. Such an entry must not collapse
    to '/' and quietly make the root match for the wrong reason."""
    assert not is_known_path('/nope', [None, ''], [])


# ── the body ──────────────────────────────────────────────────────────────────

def test_the_404_body_is_small_and_navigable():
    """Not the Dash shell: ~10 KB of app payload per probe is the cost being avoided,
    and the person who mistyped a url still needs a way back."""
    body = not_found_page('#1a1a1a', '#ABB8C9', '#E2E8F0')
    assert len(body) < 2000
    assert 'href="/"' in body
    assert '404' in body
