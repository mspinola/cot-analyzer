"""The news-failure scan on the deployed app answers only a browser logged in at /admin.

The page draws a licensed positioning index and paywalled headlines. Since 2026-11-21
the server may serve it (`COT_ANALYZER_PRIVATE_PAGES`), but unlinked is not private, and
a password on the path in nginx would miss the shared /_dash-update-component endpoint
that carries the page's data. So the gate is in the page itself: its layout and its
callback each ask `local_pages.allowed()`. These drive both with no session, with a
forged one, and with a real one, and check the local run still needs no login.
"""
import importlib

import dash
import flask
import pytest
from dash.exceptions import PreventUpdate

import admin_session
import local_pages
from tests.test_news_failure import _text, store  # noqa: F401 (fixture)

PATH = "/news-failure"


@pytest.fixture()
def page(monkeypatch, store):  # noqa: F811
    """The page as the server builds it: private flag on, local flag off."""
    for key, value in store.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv(local_pages.ENV, raising=False)
    monkeypatch.setenv(local_pages.PRIVATE_ENV, "1")
    registered = list(dash._callback.GLOBAL_CALLBACK_LIST)
    mod = importlib.reload(importlib.import_module("pages.analytics.news_failure"))
    try:
        yield mod
    finally:
        dash._callback.GLOBAL_CALLBACK_LIST[:] = registered
        monkeypatch.delenv(local_pages.PRIVATE_ENV)
        importlib.reload(mod)
        for key in [k for k, v in dash.page_registry.items() if v.get("path") == PATH]:
            del dash.page_registry[key]


@pytest.fixture()
def flask_app():
    app = flask.Flask(__name__)
    app.secret_key = "test"
    return app


def _as(flask_app, logged_in, fn):
    with flask_app.test_request_context(PATH):
        if logged_in:
            flask.session[admin_session.SESSION_FLAG] = True
        return fn()


@pytest.mark.parametrize("value", ["", "0", "no", "ture"])
def test_the_server_flag_is_off_unless_explicitly_on(value):
    assert not local_pages.private_enabled({local_pages.PRIVATE_ENV: value})
    assert local_pages.private_enabled({local_pages.PRIVATE_ENV: "1"})


def test_the_server_flag_registers_the_page_but_keeps_it_out_of_the_navbar(page):
    assert [p["path"] for p in dash.page_registry.values() if p.get("path") == PATH] == [PATH]
    assert local_pages.monitor_entries() == ()


def test_a_logged_out_request_gets_a_login_prompt_and_nothing_from_the_store(page, flask_app,
                                                                             monkeypatch):
    def refuse(*a, **k):
        pytest.fail("the store was read for a logged-out request")
    monkeypatch.setattr(page.nf, "available_dates", refuse)
    monkeypatch.setattr(page.nf, "markets", refuse)
    text = _text(_as(flask_app, False, page.layout))
    assert "admin page" in text and "2026-11-17" not in text


def test_a_forged_callback_request_is_refused(page, flask_app):
    """What a POST to /_dash-update-component would run, with no login behind it."""
    with pytest.raises(PreventUpdate):
        _as(flask_app, False, lambda: page._pick("2026-11-17", None, 10, None))
    with pytest.raises(PreventUpdate):
        _as(flask_app, False, lambda: page._pick(None, "SI", 0, None))


def test_a_session_that_only_claims_the_store_value_is_still_refused(page, flask_app):
    """The browser store's "AUTHORIZED" is request data; only the signed flag counts."""
    def claim():
        flask.session["session_admin_auth"] = "AUTHORIZED"
        flask.session[admin_session.SESSION_FLAG] = "true"     # not the boolean True
        return page._pick("2026-11-17", None, 10, None)
    with flask_app.test_request_context(PATH), pytest.raises(PreventUpdate):
        claim()


def test_a_logged_in_request_gets_the_board(page, flask_app):
    assert "2026-11-17" in _text(_as(flask_app, True, page.layout))
    body, date_disabled, _ = _as(flask_app, True,
                                 lambda: page._pick("2026-11-17", None, 10, None))
    assert "Every set-up" in _text(body) and date_disabled is False


def test_a_local_run_needs_no_login(monkeypatch, flask_app):
    monkeypatch.setenv(local_pages.ENV, "1")
    assert _as(flask_app, False, local_pages.allowed)
    monkeypatch.delenv(local_pages.ENV)
    assert not _as(flask_app, False, local_pages.allowed)
    assert not local_pages.allowed()          # no request at all: no


def test_the_path_stays_out_of_the_sitemap():
    import routing
    assert PATH in routing.NOINDEX_PATHS
    assert PATH not in routing.sitemap_xml("https://x.test", [PATH, "/heatmap"])
