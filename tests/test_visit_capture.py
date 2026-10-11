"""The I/O half of visitor tracking: what gets enqueued, and what the worker writes.

`_enqueue_visit` is monkeypatched where the subject is the hook/callback plumbing, so
no thread starts and nothing is written; `_process_visit` is tested directly against a
temporary CotDatabase, which is the real consumer of the cotmetrics 0.11.0 surface and
therefore the test that would catch a floor violation.
"""
import pandas as pd
import pytest
from cotmetrics.CotDatabase import CotDatabase

import app_cot
from pages.system.admin import split_visit_rows


@pytest.fixture
def captured(monkeypatch):
    rows = []
    monkeypatch.setattr(app_cot, '_enqueue_visit',
                        lambda kind, path: rows.append((kind, path)))
    return rows


# ── what the request hook logs ────────────────────────────────────────────────

def test_a_document_load_is_a_landing(captured):
    with app_cot.app.server.test_request_context('/heatmap'):
        app_cot.record_visit()
    assert captured == [('landing', '/heatmap')]


def test_internal_and_asset_requests_are_not_visits(captured):
    for path in ['/_dash-update-component', '/_dash-component-suites/dash/x.js',
                 '/assets/style.css', '/_favicon.ico']:
        with app_cot.app.server.test_request_context(path):
            app_cot.record_visit()
    assert captured == []


# ── what the router callback logs ─────────────────────────────────────────────

def test_a_client_side_navigation_is_a_pageview(captured):
    """The half the HTTP layer cannot see: pushState navigation arrives here as a
    callback, and before this existed only entry pages were ever counted."""
    with app_cot.app.server.test_request_context('/_dash-update-component'):
        app_cot.record_pageview('/crowd')
    assert captured == [('pageview', '/crowd')]


def test_a_null_pathname_logs_nothing(captured):
    with app_cot.app.server.test_request_context('/_dash-update-component'):
        app_cot.record_pageview(None)
    assert captured == []


# ── what the external-page beacon logs ───────────────────────────────────────
#
# These go through the test client rather than calling the view, because the
# interesting half is what the OTHER hooks do with the request: the unknown-path
# guard must admit it and `record_visit` must not log it as a landing on top of
# the rows the beacon writes itself.

@pytest.fixture
def captured_rows(monkeypatch):
    rows = []
    monkeypatch.setattr(app_cot, '_enqueue_visit',
                        lambda kind, path, **kw: rows.append((kind, path, kw)))
    return rows


def test_a_dbmf_page_load_is_a_landing_plus_a_pageview(captured_rows):
    """The same pair one of this app's own document loads produces: the landing
    carries the external page's referrer, the pageview is what the admin page
    counts. No third row for the pixel request itself."""
    client = app_cot.app.server.test_client()
    resp = client.get('/seen.gif?p=dbmf&r=https%3A%2F%2Fexample.com%2Fpost')
    assert resp.status_code == 200
    assert resp.content_type == 'image/gif'
    assert resp.headers['Cache-Control'] == 'no-store'
    assert captured_rows == [
        ('landing', '/dbmf', {'referrer': 'https://example.com/post'}),
        ('pageview', '/dbmf', {}),
    ]


def test_a_direct_dbmf_visit_has_no_referrer(captured_rows):
    """`document.referrer` is '' on a direct visit; the row must say None, as the
    Referer header would, not the dbmf page's own address from this request."""
    client = app_cot.app.server.test_client()
    client.get('/seen.gif?p=dbmf&r=',
               headers={'Referer': 'https://dbmf.bluemagicai.com/'})
    assert captured_rows[0] == ('landing', '/dbmf', {'referrer': None})


def test_an_unlisted_page_gets_the_pixel_and_no_row(captured_rows):
    client = app_cot.app.server.test_client()
    for query in ['', '?p=', '?p=shell.php', '?p=DBMF']:
        resp = client.get('/seen.gif' + query)
        assert resp.status_code == 200, query
    assert captured_rows == []


def test_the_pixel_is_a_real_one_by_one_gif():
    import io

    import routing
    assert routing.PIXEL_GIF[:6] == b'GIF89a' and routing.PIXEL_GIF[-1:] == b';'
    Image = pytest.importorskip('PIL.Image')
    assert Image.open(io.BytesIO(routing.PIXEL_GIF)).size == (1, 1)


def test_an_explicit_referrer_wins_over_the_request_header(monkeypatch):
    monkeypatch.setattr(app_cot, '_visit_worker_started', True)
    with app_cot.app.server.test_request_context(
            '/seen.gif', headers={'User-Agent': 'Mozilla/5.0',
                                  'Referer': 'https://dbmf.bluemagicai.com/'}):
        app_cot._enqueue_visit('landing', '/dbmf', referrer=None)
        app_cot._enqueue_visit('landing', '/dbmf', referrer='https://t.co/x')
    assert app_cot._visit_queue.get_nowait()['referrer'] is None
    assert app_cot._visit_queue.get_nowait()['referrer'] == 'https://t.co/x'


# ── what reaches the queue ────────────────────────────────────────────────────

def test_the_enqueued_row_carries_identity_and_referrer(monkeypatch):
    monkeypatch.setattr(app_cot, '_visit_worker_started', True)  # no thread
    with app_cot.app.server.test_request_context(
            '/', headers={'X-Forwarded-For': '34.95.46.6, 10.0.0.1',
                          'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64)',
                          'Referer': 'https://example.com/post'}):
        app_cot._enqueue_visit('landing', '/')
    row = app_cot._visit_queue.get_nowait()
    assert row['ip'] == '34.95.46.6'
    assert row['kind'] == 'landing'
    assert row['is_bot'] is False
    assert row['referrer'] == 'https://example.com/post'
    assert len(row['visitor_id']) == 16


def test_a_pageview_never_claims_the_post_referrer(monkeypatch):
    """A callback POST's referrer is our own page url; storing it would make every
    navigation look self-referred."""
    monkeypatch.setattr(app_cot, '_visit_worker_started', True)
    with app_cot.app.server.test_request_context(
            '/_dash-update-component',
            headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'http://host/heatmap'}):
        app_cot._enqueue_visit('pageview', '/crowd')
    assert app_cot._visit_queue.get_nowait()['referrer'] is None


# ── what the worker writes ────────────────────────────────────────────────────

def _row(ip='8.8.8.8', path='/', kind='pageview'):
    return {'kind': kind, 'path': path, 'ip': ip, 'ua': 'Mozilla/5.0',
            'visitor_id': 'abcd1234abcd1234', 'is_bot': False, 'referrer': None}


def test_geo_is_looked_up_once_per_ip(tmp_path):
    db = CotDatabase(db_name=str(tmp_path / 'v.db'))
    fetches = []

    def fetch(ip):
        fetches.append(ip)
        return 'Lisbon', 'Portugal', False

    app_cot._process_visit(_row(), db=db, fetch=fetch)
    app_cot._process_visit(_row(), db=db, fetch=fetch)
    assert fetches == ['8.8.8.8']
    df = db.get_visitor_stats()
    assert list(df['country']) == ['Portugal', 'Portugal']


def test_a_residential_address_is_not_refetched_on_every_visit(tmp_path):
    """hosting=False must cache as False rather than as unknown. If it read back as
    None the row would look unanswered, and every visit a real person made would spend
    another lookup against ip-api's 45/min."""
    db = CotDatabase(db_name=str(tmp_path / 'v.db'))
    fetches = []

    def fetch(ip):
        fetches.append(ip)
        return 'Verona', 'Italy', False

    for _ in range(3):
        app_cot._process_visit(_row(), db=db, fetch=fetch)
    assert fetches == ['8.8.8.8']


def test_a_datacenter_address_is_a_bot_whatever_its_user_agent_says(tmp_path):
    """The whole point: `visitors.is_bot` sees a browser here and the address is a
    Tencent Cloud one. Measured against the real thing, not invented."""
    db = CotDatabase(db_name=str(tmp_path / 'v.db'))
    app_cot._process_visit(_row(ip='170.106.180.153'), db=db,
                           fetch=lambda ip: ('Santa Clara', 'United States', True))
    assert db.get_visitor_stats().iloc[0]['is_bot'] == 1


def test_a_residential_address_with_a_browser_agent_stays_human(tmp_path):
    db = CotDatabase(db_name=str(tmp_path / 'v.db'))
    app_cot._process_visit(_row(ip='93.70.66.30'), db=db,
                           fetch=lambda ip: ('Verona', 'Italy', False))
    assert db.get_visitor_stats().iloc[0]['is_bot'] == 0


def test_a_row_cached_before_hosting_existed_is_refetched_once(tmp_path):
    """The deployed database has geography for thousands of addresses and the flag for
    none of them. Each must cost exactly one more lookup, not one per visit."""
    db = CotDatabase(db_name=str(tmp_path / 'v.db'))
    db.cache_geo('8.8.8.8', 'Lisbon', 'Portugal')      # the pre-0.11.0 shape
    fetches = []

    def fetch(ip):
        fetches.append(ip)
        return 'Lisbon', 'Portugal', True

    app_cot._process_visit(_row(), db=db, fetch=fetch)
    app_cot._process_visit(_row(), db=db, fetch=fetch)
    assert fetches == ['8.8.8.8']
    assert db.get_cached_hosting('8.8.8.8') is True


def test_a_failed_lookup_is_not_cached(tmp_path):
    """('Lookup', 'Error') must stay retryable, or one rate-limited minute pins an
    address to Error forever."""
    db = CotDatabase(db_name=str(tmp_path / 'v.db'))
    app_cot._process_visit(_row(), db=db,
                           fetch=lambda ip: ('Lookup', 'Error', False))
    assert db.get_cached_geo('8.8.8.8') is None
    app_cot._process_visit(_row(), db=db,
                           fetch=lambda ip: ('Lisbon', 'Portugal', False))
    assert db.get_cached_geo('8.8.8.8') == ('Lisbon', 'Portugal')


def test_internal_addresses_never_reach_the_network(tmp_path):
    db = CotDatabase(db_name=str(tmp_path / 'v.db'))

    def explode(ip):
        raise AssertionError('lookup attempted for internal address')

    app_cot._process_visit(_row(ip='127.0.0.1'), db=db, fetch=explode)
    row = db.get_visitor_stats().iloc[0]
    assert (row['city'], row['country']) == ('Internal', 'Local')


# ── how the admin page reads it back ──────────────────────────────────────────

def _frame():
    return pd.DataFrame({
        'timestamp': pd.to_datetime(['2026-08-27'] * 4),
        'kind': ['pageview', 'landing', None, 'pageview'],
        'is_bot': [0, 0, None, 1],
        'visitor_id': ['aa', 'aa', None, 'bb'],
        'country': ['PT', 'PT', 'US', 'DE'],
    })


def test_views_are_pageviews_plus_legacy_rows_never_landings():
    views, _ = split_visit_rows(_frame(), 'all')
    assert list(views['kind']) == ['pageview', None, 'pageview']


def test_the_human_filter_keeps_pre_migration_rows():
    """NULL is_bot predates the column; dropping those rows would erase all history
    from the default view."""
    views, events = split_visit_rows(_frame(), 'humans')
    assert list(views['country']) == ['PT', 'US']
    assert len(events) == 3


def test_the_bot_filter_is_the_complement():
    views, _ = split_visit_rows(_frame(), 'bots')
    assert list(views['country']) == ['DE']


# ── the analytics tag ─────────────────────────────────────────────────────────

def test_goatcounter_markup_is_complete_and_spa_aware():
    html = app_cot.index_template('https://stats.example.com')
    assert 'data-goatcounter="https://stats.example.com/count"' in html
    assert 'src="https://stats.example.com/count.js"' in html
    # The SPA hook: onload counting off, pushState and popstate counted, or every
    # navigation after the first would be invisible to it.
    assert 'no_onload: true' in html
    assert 'history.pushState' in html
    assert 'popstate' in html
    # Still a whole Dash template.
    for token in ['{%metas%}', '{%title%}', '{%favicon%}', '{%css%}',
                  '{%app_entry%}', '{%config%}', '{%scripts%}', '{%renderer%}']:
        assert token in html
    # And the install surface rides every variant of it: the manifest link and
    # worker registration are what make Android's Add to Home screen a real
    # install rather than a bookmark (the pieces themselves are test_pwa's).
    assert '<link rel="manifest" href="/manifest.webmanifest">' in html
    assert 'name="theme-color"' in html
    assert 'apple-touch-icon' in html
    assert "navigator.serviceWorker.register('/sw.js')" in html


def test_without_an_origin_the_template_carries_no_tracker():
    """Opt-in stays opt-in: one builder now serves both cases (the noscript
    block rides every deployment), so the untracked default must be provably
    tracker-free rather than assumed."""
    html = app_cot.index_template(None)
    assert 'goatcounter' not in html
    assert '<noscript>' in html
