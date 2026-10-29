"""The old addresses of pages that moved, and what they do with a query string.

Both are 301s to a page that still exists, so neither is interesting until it
stops working, and nothing else in the suite would notice: `reject_unknown_paths`
runs BEFORE the route, so dropping the path from `routing.EXTRA_PATHS` turns the
redirect into a 404 without touching the route itself. These pin both halves.

The query string is the half that matters for /crowd. Every weekly email ever
sent carries `/crowd?date=<week>`, and a redirect that drops the date lands the
reader on the current week while the email tells them it is that week's board.
"""
import pytest

import app_cot


@pytest.fixture(autouse=True)
def _no_visit_logging(monkeypatch):
    """Keep these requests out of the visitor queue.

    A real request through the test client runs `record_visit`, which starts the
    visit worker THREAD. That thread outlives this module and goes on draining a
    shared queue, so it logs through whatever `app_cot.utils.cot_logger` happens
    to be by then, which is test_log_noise's stub. The redirect is the subject
    here; the visit hook has its own module.
    """
    monkeypatch.setattr(app_cot, '_enqueue_visit',
                        lambda kind, path, **kwargs: None)


def _client():
    return app_cot.app.server.test_client()


def test_the_crowd_boards_old_address_redirects_to_the_landing_page():
    resp = _client().get('/crowd')
    assert resp.status_code == 301
    assert resp.headers['Location'].endswith('/')


def test_a_dated_crowd_link_from_a_weekly_email_keeps_its_week():
    resp = _client().get('/crowd?date=2026-10-20&model=raw')
    assert resp.status_code == 301
    assert resp.headers['Location'].endswith('/?date=2026-10-20&model=raw')


def test_the_market_grids_old_address_still_names_the_view_it_meant():
    resp = _client().get('/graphs')
    assert resp.status_code == 301
    assert resp.headers['Location'].endswith('/analysis?view=grid')


def test_neither_old_address_is_404d_before_its_route_runs():
    """`reject_unknown_paths` consults routing.EXTRA_PATHS, not the route table."""
    for path in ('/crowd', '/graphs'):
        assert _client().get(path).status_code == 301, path
